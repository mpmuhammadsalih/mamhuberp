from mobile_backend.request_context import get_jwt

from mobile_backend.database.oracle_pool import get_connection
import re


def _pick_existing(columns: set[str], candidates: list[str]) -> str | None:
    for name in candidates:
        if name.upper() in columns:
            return name.upper()
    return None


def _strip_barcode_symbols(value: str) -> str:
    """Code 39 start/stop (*), spaces, dashes — common on retail labels."""
    t = value.strip().upper().replace(" ", "").replace("-", "")
    if len(t) >= 2 and t.startswith("*") and t.endswith("*"):
        t = t[1:-1]
    return t


def _numeric_itemcode_core(search: str) -> str | None:
    """When search is digits (optional leading zeros / trailing .0), return normalized core."""
    cleaned = _strip_barcode_symbols(search)
    if re.fullmatch(r"\d+\.0+", cleaned):
        cleaned = cleaned.split(".", 1)[0]
    if not re.fullmatch(r"\d+", cleaned):
        digits = re.sub(r"\D", "", cleaned)
        if not digits:
            return None
        cleaned = digits
    return cleaned.lstrip("0") or "0"


def _build_inventory_search_where(
    *,
    code_col: str,
    name_col: str | None,
    barcode_col: str | None,
    search: str,
    binds: dict,
    alias: str = "i",
) -> str:
    normalized = _strip_barcode_symbols(search)
    if not normalized:
        return "1=1"

    code_expr = f"TRIM(TO_CHAR({alias}.{code_col}))"
    code_digits = f"LTRIM({code_expr}, '0')"
    wh_parts: list[str] = []

    pat = f"%{normalized}%"
    binds["srch"] = pat
    wh_parts.append(f"UPPER({code_expr}) LIKE :srch")

    numeric_core = _numeric_itemcode_core(normalized)
    if numeric_core is not None:
        binds["srch_core_pat"] = f"%{numeric_core}%"
        wh_parts.append(f"NVL({code_digits}, '0') LIKE :srch_core_pat")
        binds["srch_core_eq"] = numeric_core
        wh_parts.append(f"NVL({code_digits}, '0') = :srch_core_eq")
        binds["srch_num"] = int(numeric_core)
        wh_parts.append(f"{alias}.{code_col} = :srch_num")

    if name_col:
        wh_parts.append(f"UPPER(TRIM(TO_CHAR({alias}.{name_col}))) LIKE :srch")
    if barcode_col:
        wh_parts.append(f"UPPER(TRIM(TO_CHAR({alias}.{barcode_col}))) LIKE :srch")
        digits_only = re.sub(r"\D", "", normalized)
        if digits_only:
            binds["barcode_digits_pat"] = f"%{digits_only}%"
            wh_parts.append(
                f"REGEXP_REPLACE(UPPER(TRIM(TO_CHAR({alias}.{barcode_col}))), '[^0-9]', '') "
                f"LIKE :barcode_digits_pat"
            )
            barcode_core = digits_only.lstrip("0") or "0"
            binds["barcode_core_eq"] = barcode_core
            wh_parts.append(
                f"NVL(LTRIM(REGEXP_REPLACE(UPPER(TRIM(TO_CHAR({alias}.{barcode_col}))), "
                f"'[^0-9]', ''), '0'), '0') = :barcode_core_eq"
            )

    return "(" + " OR ".join(wh_parts) + ")"


def _itemmaster_select_exprs(item_cols: set[str]) -> dict[str, str]:
    code_col = _pick_existing(item_cols, ["ITEMCODE", "CODE", "ITEM_CODE"])
    name_col = _pick_existing(item_cols, ["ITEMNAME", "ITEMDESC", "ITEM_NAME"])
    unit_col = _pick_existing(item_cols, ["BASEUOM", "UNIT", "UOM", "UNITCODE", "UNIT_CODE"])
    barcode_col = _pick_existing(
        item_cols,
        ["BARCODE", "MANUFACTURERID", "EAN", "UPC", "ITEM_BARCODE", "BAR_CODE"],
    )
    retail_col = _pick_existing(
        item_cols,
        [
            "RETAILPRICE",
            "RETAIL_PRICE",
            "RETAILPRICE1",
            "MRP",
            "SELLINGPRICE",
            "SELLING_PRICE",
            "SALE_PRICE",
        ],
    )
    if not code_col:
        raise ValueError("ITEMMASTER must have ITEMCODE/CODE column")
    return {
        "code_col": code_col,
        "name_col": name_col,
        "unit_col": unit_col,
        "barcode_col": barcode_col,
        "retail_col": retail_col,
        "select_name_expr": f"im.{name_col}" if name_col else "CAST(NULL AS VARCHAR2(200))",
        "select_unit_expr": f"im.{unit_col}" if unit_col else "CAST(NULL AS VARCHAR2(50))",
        "select_barcode_expr": (
            f"TRIM(TO_CHAR(im.{barcode_col}))" if barcode_col else "CAST(NULL AS VARCHAR2(80))"
        ),
        "select_retail_expr": f"NVL(im.{retail_col}, 0)" if retail_col else "0",
    }


def _rows_to_inventory(rows) -> list[dict]:
    return [
        {
            "itemcode": row[0],
            "itemname": row[1] or "",
            "unit": row[2] or "",
            "qty_on_hand": float(row[3] or 0),
            "barcode": row[4] or "",
            "retail_price": float(row[5] or 0),
        }
        for row in rows
    ]


def _list_warehouse_inventory(
    page: int,
    page_size: int,
    search: str,
    *,
    warehouse_id: int,
    locationcode: int | None,
    include_zero: bool,
    tenant_id,
) -> list[dict]:
    from db import WAREHOUSE_STOCK_TABLE, ensure_warehouse_stock_table

    if not ensure_warehouse_stock_table():
        return []

    start_row = ((page - 1) * page_size) + 1
    end_row = page * page_size

    conn = get_connection(tenant_id=tenant_id)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM user_tab_columns
            WHERE table_name = 'ITEMMASTER'
            """
        )
        item_cols = {str(row[0]).upper() for row in cur.fetchall()}
        meta = _itemmaster_select_exprs(item_cols)
        code_col = meta["code_col"]

        scope_parts = ["ws.WAREHOUSE_ID = :wid"]
        binds: dict = {
            "wid": int(warehouse_id),
            "start_row": start_row,
            "end_row": end_row,
        }
        if not include_zero:
            scope_parts.append("NVL(ws.QTY, 0) <> 0")

        search_clause = _build_inventory_search_where(
            code_col=code_col,
            name_col=meta["name_col"],
            barcode_col=meta["barcode_col"],
            search=search,
            binds=binds,
            alias="im",
        )

        sql = f"""
            SELECT itemcode, itemname, unit, qty_on_hand, barcode, retail_price
            FROM (
                SELECT
                    ws.ITEMCODE AS itemcode,
                    {meta["select_name_expr"]} AS itemname,
                    {meta["select_unit_expr"]} AS unit,
                    NVL(ws.QTY, 0) AS qty_on_hand,
                    {meta["select_barcode_expr"]} AS barcode,
                    {meta["select_retail_expr"]} AS retail_price,
                    ROW_NUMBER() OVER (ORDER BY ws.ITEMCODE) rn
                FROM {WAREHOUSE_STOCK_TABLE} ws
                LEFT JOIN itemmaster im ON ws.ITEMCODE = im.{code_col}
                WHERE {" AND ".join(scope_parts)} AND ({search_clause})
            )
            WHERE rn BETWEEN :start_row AND :end_row
        """
        cur.execute(sql, binds)
        return _rows_to_inventory(cur.fetchall())


def list_inventory(
    page: int,
    page_size: int,
    search: str = "",
    *,
    warehouse_id: int | None = None,
    locationcode: int | None = None,
    include_zero: bool = True,
) -> list[dict]:
    claims = get_jwt()
    tenant_id = claims.get("tenant_id")
    if warehouse_id is not None:
        return _list_warehouse_inventory(
            page,
            page_size,
            search,
            warehouse_id=int(warehouse_id),
            locationcode=locationcode,
            include_zero=include_zero,
            tenant_id=tenant_id,
        )

    start_row = ((page - 1) * page_size) + 1
    end_row = page * page_size

    conn = get_connection(tenant_id=tenant_id)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM user_tab_columns
            WHERE table_name = 'ITEMMASTER'
            """
        )
        item_cols = {str(row[0]).upper() for row in cur.fetchall()}
        meta = _itemmaster_select_exprs(item_cols)
        code_col = meta["code_col"]
        qty_col = _pick_existing(
            item_cols,
            ["CURRENTSTOCK", "CURRENT_STOCK", "QTY_ON_HAND", "STOCK", "QTY", "BALANCEQTY"],
        )
        select_qty_expr = f"NVL(i.{qty_col}, 0)" if qty_col else "0"

        binds: dict = {
            "start_row": start_row,
            "end_row": end_row,
        }

        where_clause = _build_inventory_search_where(
            code_col=code_col,
            name_col=meta["name_col"],
            barcode_col=meta["barcode_col"],
            search=search,
            binds=binds,
            alias="i",
        )

        sql = f"""
            SELECT itemcode, itemname, unit, qty_on_hand, barcode, retail_price
            FROM (
                SELECT
                    i.{code_col} AS itemcode,
                    {meta["select_name_expr"].replace("im.", "i.")} AS itemname,
                    {meta["select_unit_expr"].replace("im.", "i.")} AS unit,
                    {select_qty_expr} AS qty_on_hand,
                    {meta["select_barcode_expr"].replace("im.", "i.")} AS barcode,
                    {meta["select_retail_expr"].replace("im.", "i.")} AS retail_price,
                    ROW_NUMBER() OVER (ORDER BY i.{code_col}) rn
                FROM itemmaster i
                WHERE {where_clause}
            )
            WHERE rn BETWEEN :start_row AND :end_row
        """

        cur.execute(sql, binds)
        return _rows_to_inventory(cur.fetchall())


def _resolve_location_code() -> int:
    from db import get_location_info_by_dbkey

    try:
        info = get_location_info_by_dbkey(None) or {}
        loc = info.get("locationcode")
        if loc is not None:
            return int(loc)
    except Exception:
        pass
    return 1


def get_item_store_stock(item_code: int) -> list[dict]:
    from db import get_item_store_inventory

    loc = _resolve_location_code()
    rows = get_item_store_inventory(loc, int(item_code)) or []
    out: list[dict] = []
    for row in rows:
        store = str(row.get("store") or row.get("code") or "").strip()
        if not store:
            continue
        out.append(
            {
                "store": store,
                "description": str(row.get("description") or "").strip(),
                "qty": float(row.get("stock") or 0),
            }
        )
    out.sort(key=lambda r: (-r["qty"], r["store"]))
    return out

