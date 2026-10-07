"""Stock physical count — STOCK_COUNT_HDR / STOCK_COUNT_DTL (tenant ERP schema)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from mobile_backend.request_context import get_jwt
from mobile_backend.database.oracle_pool import get_connection
from mobile_backend.database.transaction import oracle_transaction
from mobile_backend.operation_lock import mobile_operation_lock
from mobile_backend.services.purchase_service import (
    _coerce_grn_mobile_ext_location_id as _coerce_location,
    _pick_existing,
    _table_columns,
    _table_exists,
)

_HDR = "STOCK_COUNT_HDR"
_DTL = "STOCK_COUNT_DTL"
_JOURNAL = "STOCK_COUNT_JOURNAL"
_PRICE_HDR = "STOCK_COUNT_PRICE_HDR"
_PRICE_UPD = "STOCK_COUNT_PRICE_UPDATE"
_DRAFT_STATUS = "DRAFT"
_PRICE_STATUS_PENDING = "PENDING"
_PRICE_STATUS_APPLIED = "APPLIED"
_POSTED_STATUSES = frozenset({"POSTED"})
_PRIVILEGED_USERS = {"admin", "super"}


def _claims_context() -> tuple[dict[str, Any], str | None, str]:
    claims = get_jwt()
    tenant_id = claims.get("tenant_id")
    username = str(claims.get("sub") or "").strip() or "mobile"
    return claims, tenant_id, username


def _coerce_optional_int(raw: Any) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    try:
        return int(raw)
    except (TypeError, ValueError):
        try:
            s = str(raw).strip()
            if not s:
                return None
            return int(float(s)) if "." in s else int(s)
        except (TypeError, ValueError):
            return None


def _lookup_location_warehouse(cur: Any, locationcode: int) -> int | None:
    """Default warehouse for a branch/location when the count header has none."""
    if not _table_exists(cur, "LOCATIONMASTER"):
        return None
    cols = _table_columns(cur, "LOCATIONMASTER")
    loc_col = _pick_existing(cols, ["LOCATIONCODE", "LOCATION_CODE"])
    wh_col = _pick_existing(
        cols,
        ["WAREHOUSE_ID", "WAREHOUSEID", "WH_ID", "DEFAULT_WAREHOUSE_ID", "DEFAULT_WH_ID"],
    )
    if not loc_col or not wh_col:
        return None
    cur.execute(
        f"SELECT {wh_col} FROM LOCATIONMASTER WHERE {loc_col} = :loc",
        {"loc": locationcode},
    )
    row = cur.fetchone()
    return _coerce_optional_int(row[0]) if row else None


def _lookup_item_barcode(cur: Any, itemcode: int) -> str:
    """Barcode from ITEMMASTER when mobile did not send one (often MANUFACTURERID)."""
    if not _table_exists(cur, "ITEMMASTER"):
        return ""
    cols = _table_columns(cur, "ITEMMASTER")
    code_col = _pick_existing(cols, ["ITEMCODE", "CODE", "ITEM_CODE"])
    bar_col = _pick_existing(
        cols,
        ["BARCODE", "MANUFACTURERID", "EAN", "UPC", "ITEM_BARCODE", "BAR_CODE"],
    )
    if not code_col or not bar_col:
        return ""
    cur.execute(
        f"""
        SELECT TRIM(TO_CHAR({bar_col}))
          FROM ITEMMASTER
         WHERE {code_col} = :ic
        """,
        {"ic": itemcode},
    )
    row = cur.fetchone()
    if not row or row[0] is None:
        return ""
    return str(row[0]).strip()[:80]


def _resolve_barcode(cur: Any, itemcode: int, explicit: str) -> str:
    val = (explicit or "").strip()
    if val:
        return val[:80]
    return _lookup_item_barcode(cur, itemcode)


def _item_retail_price_column(cur: Any) -> str | None:
    if not _table_exists(cur, "ITEMMASTER"):
        return None
    cols = _table_columns(cur, "ITEMMASTER")
    return _pick_existing(
        cols,
        [
            "RETAILPRICE",
            "RETAIL_PRICE",
            "RETAILPRICE1",
            "MRP",
            "SELLINGPRICE",
            "SELLING_PRICE",
            "SALE_PRICE",
            "UNITPRICE",
        ],
    )


def _lookup_item_retail_price(cur: Any, itemcode: int) -> float | None:
    price_col = _item_retail_price_column(cur)
    if not price_col:
        return None
    cols = _table_columns(cur, "ITEMMASTER")
    code_col = _pick_existing(cols, ["ITEMCODE", "CODE", "ITEM_CODE"])
    if not code_col:
        return None
    cur.execute(
        f"SELECT {price_col} FROM ITEMMASTER WHERE {code_col} = :ic",
        {"ic": itemcode},
    )
    row = cur.fetchone()
    if not row or row[0] is None:
        return None
    try:
        return float(row[0])
    except (TypeError, ValueError):
        return None


def _fresh_table_exists(cur: Any, table_name: str) -> bool:
    """Uncached check — avoids stale False after runtime DDL (e.g. STOCK_COUNT_PRICE_UPDATE)."""
    t = table_name.upper()
    cur.execute(
        "SELECT COUNT(*) FROM user_tables WHERE table_name = :t",
        {"t": t},
    )
    return int(cur.fetchone()[0] or 0) > 0


def _fresh_dtl_retail_columns(cur: Any) -> bool:
    if not _fresh_table_exists(cur, _DTL):
        return False
    cur.execute(
        """
        SELECT COUNT(*) FROM user_tab_columns
         WHERE table_name = :t
           AND column_name IN ('OLD_RETAIL_PRICE', 'NEW_RETAIL_PRICE')
        """,
        {"t": _DTL},
    )
    return int(cur.fetchone()[0] or 0) >= 2


def _dtl_has_retail_columns(cur: Any) -> bool:
    return _fresh_dtl_retail_columns(cur)


def _dtl_has_counted_by(cur: Any) -> bool:
    if not _fresh_table_exists(cur, _DTL):
        return False
    cur.execute(
        """
        SELECT COUNT(*) FROM user_tab_columns
         WHERE table_name = :t AND column_name = 'COUNTED_BY'
        """,
        {"t": _DTL},
    )
    return int(cur.fetchone()[0] or 0) > 0


def _fresh_table_columns(cur: Any, table_name: str) -> set[str]:
    """Uncached column list (price tables may differ from purchase_service cache)."""
    t = table_name.upper()
    cur.execute(
        """
        SELECT column_name FROM user_tab_columns WHERE table_name = :t
        """,
        {"t": t},
    )
    return {str(row[0]).upper() for row in cur.fetchall() or []}


def _price_hdr_schema(cur: Any) -> dict[str, str] | None:
    """Map STOCK_COUNT_PRICE_HDR columns (ERP may use SOURCE_COUNT_NO + BATCH_NO)."""
    if not _fresh_table_exists(cur, _PRICE_HDR):
        return None
    cols = _fresh_table_columns(cur, _PRICE_HDR)
    count_col = _pick_existing(cols, ["SOURCE_COUNT_NO", "COUNT_NO", "COUNTNO"])
    if not count_col:
        return None
    loc_col = _pick_existing(cols, ["LOCATIONCODE", "LOCATION_CODE"]) or "LOCATIONCODE"
    out: dict[str, str] = {"loc": loc_col, "count": count_col}
    for key, candidates in (
        ("batch", ["BATCH_NO"]),
        ("count_date", ["BATCH_DATE", "COUNT_DATE"]),
        ("warehouse", ["WAREHOUSE_ID"]),
        ("status", ["STATUS"]),
        ("remarks", ["REMARKS"]),
        ("created_by", ["CREATED_BY"]),
        ("created_at", ["CREATED_AT"]),
        ("posted_by", ["APPLIED_BY", "POSTED_BY"]),
        ("posted_at", ["APPLIED_AT", "POSTED_AT"]),
        ("pdt_device_id", ["PDT_DEVICE_ID"]),
    ):
        picked = _pick_existing(cols, candidates)
        if picked:
            out[key] = picked
    if "status" not in out:
        out["status"] = "STATUS"
    return out


def _price_upd_schema(cur: Any) -> dict[str, str] | None:
    if not _fresh_table_exists(cur, _PRICE_UPD):
        return None
    cols = _fresh_table_columns(cur, _PRICE_UPD)
    loc_col = _pick_existing(cols, ["LOCATIONCODE", "LOCATION_CODE"]) or "LOCATIONCODE"
    count_col = _pick_existing(cols, ["COUNT_NO", "SOURCE_COUNT_NO"])
    out: dict[str, str] = {"loc": loc_col}
    if count_col:
        out["count"] = count_col
    batch_col = _pick_existing(cols, ["BATCH_NO"])
    if batch_col:
        out["batch"] = batch_col
    return out


def _price_table_has_batch_no(cur: Any, table_name: str) -> bool:
    if table_name == _PRICE_HDR:
        ph = _price_hdr_schema(cur)
        return bool(ph and ph.get("batch"))
    if table_name == _PRICE_UPD:
        pu = _price_upd_schema(cur)
        return bool(pu and pu.get("batch"))
    if not _fresh_table_exists(cur, table_name):
        return False
    return "BATCH_NO" in _table_columns(cur, table_name)


def _next_price_batch_no(cur: Any) -> int:
    try:
        cur.execute("SELECT SEQ_STOCK_COUNT_PRICE_BATCH.NEXTVAL FROM dual")
        return int(cur.fetchone()[0])
    except Exception:
        n = 0
        if _fresh_table_exists(cur, _PRICE_HDR):
            cur.execute(f"SELECT NVL(MAX(BATCH_NO), 0) FROM {_PRICE_HDR}")
            n = max(n, int(cur.fetchone()[0] or 0))
        if _fresh_table_exists(cur, _PRICE_UPD):
            cur.execute(f"SELECT NVL(MAX(BATCH_NO), 0) FROM {_PRICE_UPD}")
            n = max(n, int(cur.fetchone()[0] or 0))
        return n + 1


def _ensure_price_hdr(
    cur: Any,
    *,
    loc: int,
    count_no: int,
    username: str,
    warehouse_id: int | None = None,
) -> int | None:
    """One price-update header per stock count; returns BATCH_NO when column exists."""
    ph = _price_hdr_schema(cur)
    if not ph:
        return None
    user = username[:50]
    loc_col = ph["loc"]
    count_col = ph["count"]
    batch_col = ph.get("batch")
    batch_no: int | None = None
    if batch_col:
        cur.execute(
            f"""
            SELECT {batch_col} FROM {_PRICE_HDR}
             WHERE {loc_col} = :loc AND {count_col} = :count_no
            """,
            {"loc": loc, "count_no": count_no},
        )
        row = cur.fetchone()
        if row and row[0] is not None:
            batch_no = int(row[0])
        if batch_no is None:
            batch_no = _next_price_batch_no(cur)

    merge_updates: list[str] = []
    if ph.get("warehouse") and warehouse_id is not None:
        merge_updates.append(f"{ph['warehouse']} = NVL(:warehouse_id, h.{ph['warehouse']})")
    if batch_col and batch_no is not None:
        merge_updates.append(f"{batch_col} = NVL(h.{batch_col}, :batch_no)")
    if not merge_updates:
        merge_updates.append(f"{ph['status']} = :price_status")
    matched_set = ", ".join(merge_updates)

    ins_cols = [loc_col, count_col]
    ins_vals = [":loc", ":count_no"]
    if ph.get("count_date"):
        ins_cols.append(ph["count_date"])
        ins_vals.append("TRUNC(SYSDATE)")
    if ph.get("warehouse"):
        ins_cols.append(ph["warehouse"])
        ins_vals.append(":warehouse_id")
    ins_cols.append(ph["status"])
    ins_vals.append(":price_status")
    if ph.get("created_by"):
        ins_cols.append(ph["created_by"])
        ins_vals.append(":upd_by")
    if ph.get("created_at"):
        ins_cols.append(ph["created_at"])
        ins_vals.append("SYSTIMESTAMP")
    if batch_col and batch_no is not None:
        ins_cols.append(batch_col)
        ins_vals.append(":batch_no")

    binds: dict[str, Any] = {
        "loc": loc,
        "count_no": count_no,
        "price_status": _PRICE_STATUS_PENDING,
    }
    if ph.get("warehouse"):
        binds["warehouse_id"] = warehouse_id
    if ph.get("created_by"):
        binds["upd_by"] = user
    if batch_col and batch_no is not None:
        binds["batch_no"] = batch_no

    cur.execute(
        f"""
        MERGE INTO {_PRICE_HDR} h
        USING (
            SELECT :loc AS {loc_col}, :count_no AS {count_col} FROM dual
        ) s
        ON (h.{loc_col} = s.{loc_col} AND h.{count_col} = s.{count_col})
        WHEN MATCHED THEN
          UPDATE SET {matched_set}
           WHERE UPPER(TRIM(h.{ph['status']})) NOT IN ('APPLIED', 'POSTED')
        WHEN NOT MATCHED THEN
          INSERT ({', '.join(ins_cols)})
          VALUES ({', '.join(ins_vals)})
        """,
        binds,
    )
    return batch_no


def _get_price_hdr(cur: Any, loc: int, count_no: int) -> dict[str, Any] | None:
    ph = _price_hdr_schema(cur)
    if not ph:
        return None
    pu = _price_upd_schema(cur)
    loc_col = ph["loc"]
    count_col = ph["count"]
    select_cols = [f"h.{loc_col}", f"h.{count_col}"]
    field_keys: list[str] = ["locationcode", "count_no"]
    for key in ("count_date", "warehouse", "status", "remarks", "created_by", "created_at", "posted_by", "posted_at", "pdt_device_id", "batch"):
        col = ph.get(key)
        if col and col not in (loc_col, count_col):
            select_cols.append(f"h.{col}")
            field_keys.append(key if key != "batch" else "batch_no")

    if pu and ph.get("batch") and pu.get("batch"):
        line_cnt_sql = f"""
               (SELECT COUNT(*)
                  FROM {_PRICE_UPD} d
                 WHERE d.{pu['batch']} = h.{ph['batch']}) AS LINE_CNT"""
    elif pu and pu.get("count"):
        line_cnt_sql = f"""
               (SELECT COUNT(*)
                  FROM {_PRICE_UPD} d
                 WHERE d.{pu['loc']} = h.{loc_col}
                   AND d.{pu['count']} = h.{count_col}) AS LINE_CNT"""
    else:
        line_cnt_sql = "0 AS LINE_CNT"

    cur.execute(
        f"""
        SELECT {', '.join(select_cols)},
               {line_cnt_sql}
          FROM {_PRICE_HDR} h
         WHERE h.{loc_col} = :loc AND h.{count_col} = :cn
        """,
        {"loc": loc, "cn": count_no},
    )
    row = cur.fetchone()
    if not row:
        return None

    out: dict[str, Any] = {"line_count": int(row[-1] or 0)}
    for i, key in enumerate(field_keys):
        val = row[i]
        if key == "locationcode":
            out[key] = int(val or 0)
        elif key == "count_no":
            out[key] = int(val or 0)
        elif key in ("batch_no", "warehouse"):
            out[key] = _coerce_optional_int(val)
        elif key in ("count_date", "created_at", "posted_at"):
            out[key] = val.isoformat() if isinstance(val, datetime) else (str(val or "") if val is not None else None)
        else:
            out[key] = val if val is not None else ("" if key in ("remarks", "status", "created_by", "posted_by", "pdt_device_id") else None)
    if "count_no" not in out:
        out["count_no"] = count_no
    if "locationcode" not in out:
        out["locationcode"] = loc
    return out


def _mark_price_hdr_applied(
    cur: Any, loc: int, count_no: int, username: str, *, batch_no: int | None = None
) -> None:
    ph = _price_hdr_schema(cur)
    if not ph:
        return
    pu = _price_upd_schema(cur)
    loc_col = ph["loc"]
    count_col = ph["count"]
    user = username[:50]
    if batch_no is not None and pu and pu.get("batch"):
        detail_exists = f"""
               SELECT 1 FROM {_PRICE_UPD} d
                WHERE d.{pu['batch']} = :batch_no
                  AND UPPER(TRIM(d.STATUS)) = :pending_st
        """
        binds: dict[str, Any] = {
            "loc": loc,
            "cn": count_no,
            "batch_no": batch_no,
            "applied_st": _PRICE_STATUS_APPLIED,
            "pending_st": _PRICE_STATUS_PENDING,
            "upd_by": user,
        }
    elif pu and pu.get("count"):
        detail_exists = f"""
               SELECT 1 FROM {_PRICE_UPD} d
                WHERE d.{pu['loc']} = :loc
                  AND d.{pu['count']} = :cn
                  AND UPPER(TRIM(d.STATUS)) = :pending_st
        """
        binds = {
            "loc": loc,
            "cn": count_no,
            "applied_st": _PRICE_STATUS_APPLIED,
            "pending_st": _PRICE_STATUS_PENDING,
            "upd_by": user,
        }
    else:
        return

    posted_by = ph.get("posted_by", "POSTED_BY")
    posted_at = ph.get("posted_at", "POSTED_AT")
    cur.execute(
        f"""
        UPDATE {_PRICE_HDR}
           SET {ph['status']} = :applied_st,
               {posted_by} = :upd_by,
               {posted_at} = SYSTIMESTAMP
         WHERE {loc_col} = :loc
           AND {count_col} = :cn
           AND EXISTS ({detail_exists})
        """,
        binds,
    )


def _upsert_price_update_row(
    cur: Any,
    *,
    loc: int,
    count_no: int,
    line_no: int,
    itemcode: int,
    old_retail: float | None,
    new_retail: float,
    username: str,
    batch_no: int | None = None,
) -> None:
    if not _fresh_table_exists(cur, _PRICE_UPD):
        return
    has_batch = _price_table_has_batch_no(cur, _PRICE_UPD)
    batch_set = ", BATCH_NO = :batch_no" if has_batch and batch_no is not None else ""
    batch_ins_col = ", BATCH_NO" if has_batch and batch_no is not None else ""
    batch_ins_val = ", :batch_no" if has_batch and batch_no is not None else ""
    binds: dict[str, Any] = {
        "loc": loc,
        "count_no": count_no,
        "itemcode": itemcode,
        "line_no": line_no,
        "old_retail": old_retail,
        "new_retail": new_retail,
        "price_status": _PRICE_STATUS_PENDING,
        "upd_by": username[:50],
    }
    if has_batch and batch_no is not None:
        binds["batch_no"] = batch_no
    cur.execute(
        f"""
        MERGE INTO {_PRICE_UPD} t
        USING (
            SELECT :loc AS LOCATIONCODE,
                   :count_no AS COUNT_NO,
                   :itemcode AS ITEMCODE
              FROM dual
        ) s
        ON (t.LOCATIONCODE = s.LOCATIONCODE
            AND t.COUNT_NO = s.COUNT_NO
            AND t.ITEMCODE = s.ITEMCODE)
        WHEN MATCHED THEN
          UPDATE SET LINE_NO = :line_no,
                     OLD_RETAIL_PRICE = :old_retail,
                     NEW_RETAIL_PRICE = :new_retail,
                     STATUS = :price_status,
                     UPDATED_BY = :upd_by,
                     UPDATED_AT = SYSTIMESTAMP{batch_set}
        WHEN NOT MATCHED THEN
          INSERT (
              LOCATIONCODE, COUNT_NO, ITEMCODE, LINE_NO,
              OLD_RETAIL_PRICE, NEW_RETAIL_PRICE, STATUS, UPDATED_BY, UPDATED_AT
              {batch_ins_col}
          ) VALUES (
              :loc, :count_no, :itemcode, :line_no,
              :old_retail, :new_retail, :price_status, :upd_by, SYSTIMESTAMP
              {batch_ins_val}
          )
        """,
        binds,
    )


def _apply_pending_retail_prices(cur: Any, loc: int, count_no: int, username: str) -> int:
    """Copy PENDING price rows to ITEMMASTER; mark APPLIED. Returns rows applied."""
    price_col = _item_retail_price_column(cur)
    if not price_col or not _fresh_table_exists(cur, _PRICE_UPD):
        return 0
    cols = _table_columns(cur, "ITEMMASTER")
    code_col = _pick_existing(cols, ["ITEMCODE", "CODE", "ITEM_CODE"])
    if not code_col:
        return 0

    batch_no: int | None = None
    ph = _price_hdr_schema(cur)
    if ph and ph.get("batch"):
        cur.execute(
            f"""
            SELECT {ph['batch']} FROM {_PRICE_HDR}
             WHERE {ph['loc']} = :loc AND {ph['count']} = :cn
            """,
            {"loc": loc, "cn": count_no},
        )
        brow = cur.fetchone()
        if brow and brow[0] is not None:
            batch_no = int(brow[0])

    pu = _price_upd_schema(cur)
    if batch_no is not None and pu and pu.get("batch"):
        pending_sql = f"""
        SELECT ITEMCODE, NEW_RETAIL_PRICE
          FROM {_PRICE_UPD}
         WHERE BATCH_NO = :batch_no
           AND UPPER(TRIM(STATUS)) = :st
           AND NEW_RETAIL_PRICE IS NOT NULL
        """
        pending_binds: dict[str, Any] = {"batch_no": batch_no, "st": _PRICE_STATUS_PENDING}
        upd_where = f"{pu['batch']} = :batch_no AND UPPER(TRIM(STATUS)) = :pending_st"
    elif pu and pu.get("count"):
        pending_sql = f"""
        SELECT ITEMCODE, NEW_RETAIL_PRICE
          FROM {_PRICE_UPD}
         WHERE {pu['loc']} = :loc
           AND {pu['count']} = :cn
           AND UPPER(TRIM(STATUS)) = :st
           AND NEW_RETAIL_PRICE IS NOT NULL
        """
        pending_binds = {"loc": loc, "cn": count_no, "st": _PRICE_STATUS_PENDING}
        upd_where = f"""
               {pu['loc']} = :loc
               AND {pu['count']} = :cn
               AND UPPER(TRIM(STATUS)) = :pending_st
        """
    else:
        return 0

    cur.execute(pending_sql, pending_binds)
    rows = cur.fetchall()
    applied = 0
    for itemcode, new_price in rows:
        ic = int(itemcode)
        np = float(new_price)
        cur.execute(
            f"UPDATE ITEMMASTER SET {price_col} = :np WHERE {code_col} = :ic",
            {"np": np, "ic": ic},
        )
        if cur.rowcount:
            applied += 1
    if rows:
        applied_binds: dict[str, Any] = {
            "applied_st": _PRICE_STATUS_APPLIED,
            "pending_st": _PRICE_STATUS_PENDING,
            "upd_by": username[:50],
        }
        if batch_no is not None and pu and pu.get("batch"):
            applied_binds["batch_no"] = batch_no
        elif pu and pu.get("count"):
            applied_binds["loc"] = loc
            applied_binds["cn"] = count_no
        else:
            return applied
        cur.execute(
            f"""
            UPDATE {_PRICE_UPD}
               SET STATUS = :applied_st,
                   UPDATED_BY = :upd_by,
                   UPDATED_AT = SYSTIMESTAMP
             WHERE {upd_where}
            """,
            applied_binds,
        )
        _mark_price_hdr_applied(cur, loc, count_no, username, batch_no=batch_no)
    return applied


def _line_retail_from_row(row: tuple, *, base_index: int) -> dict[str, Any]:
    """Extra line fields when DTL select includes OLD_RETAIL_PRICE, NEW_RETAIL_PRICE."""
    old_v = row[base_index] if len(row) > base_index else None
    new_v = row[base_index + 1] if len(row) > base_index + 1 else None
    out: dict[str, Any] = {}
    if old_v is not None:
        try:
            out["old_retail_price"] = float(old_v)
        except (TypeError, ValueError):
            pass
    if new_v is not None:
        try:
            out["new_retail_price"] = float(new_v)
        except (TypeError, ValueError):
            pass
    return out


def _resolve_warehouse_id(
    cur: Any,
    locationcode: int,
    hdr: dict[str, Any],
    explicit: int | None,
) -> int | None:
    """Request body → count header → location master."""
    if explicit is not None:
        return _coerce_optional_int(explicit)
    hdr_wh = _coerce_optional_int(hdr.get("warehouse_id"))
    if hdr_wh is not None:
        return hdr_wh
    return _lookup_location_warehouse(cur, locationcode)


def _coerce_item_code(raw: Any) -> int:
    if raw is None:
        raise ValueError("itemcode is required")
    if isinstance(raw, bool):
        raise ValueError("invalid itemcode")
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        return int(raw)
    s = str(raw).strip()
    if not s:
        raise ValueError("itemcode is required")
    try:
        return int(float(s)) if "." in s else int(s)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"itemcode must be numeric: {raw!r}") from exc


def _invalidate_table_exists_cache(cur: Any, table_name: str) -> None:
    from mobile_backend.services.purchase_service import (
        _CACHE_LOCK,
        _TABLE_EXISTS_CACHE,
        _oracle_username_upper,
    )

    key = (_oracle_username_upper(cur), table_name.upper())
    with _CACHE_LOCK:
        _TABLE_EXISTS_CACHE.pop(key, None)


def _create_stock_count_tables(cur: Any) -> None:
    """Create STOCK_COUNT_HDR / STOCK_COUNT_DTL (same DDL as ERP warehouse module)."""
    cur.execute(
        "SELECT COUNT(*) FROM user_tables WHERE table_name = :t",
        {"t": _HDR},
    )
    if int((cur.fetchone() or [0])[0] or 0) == 0:
        cur.execute(
            f"""
            CREATE TABLE {_HDR} (
                LOCATIONCODE   NUMBER(6) NOT NULL,
                COUNT_NO       NUMBER(10) NOT NULL,
                COUNT_DATE     DATE DEFAULT TRUNC(SYSDATE) NOT NULL,
                WAREHOUSE_ID   NUMBER(12),
                STORAGE_ID     NUMBER(12),
                STATUS         VARCHAR2(20) DEFAULT 'DRAFT' NOT NULL,
                REMARKS        VARCHAR2(500),
                PDT_DEVICE_ID  VARCHAR2(50),
                CREATED_BY     VARCHAR2(50),
                CREATED_AT     TIMESTAMP(6) DEFAULT SYSTIMESTAMP,
                POSTED_BY      VARCHAR2(50),
                POSTED_AT      TIMESTAMP(6),
                CONSTRAINT PK_STOCK_COUNT_HDR PRIMARY KEY (LOCATIONCODE, COUNT_NO)
            )
            """
        )
    cur.execute(
        "SELECT COUNT(*) FROM user_tables WHERE table_name = :t",
        {"t": _DTL},
    )
    if int((cur.fetchone() or [0])[0] or 0) == 0:
        cur.execute(
            f"""
            CREATE TABLE {_DTL} (
                LOCATIONCODE   NUMBER(6) NOT NULL,
                COUNT_NO       NUMBER(10) NOT NULL,
                LINE_NO        NUMBER(8) NOT NULL,
                ITEMCODE       NUMBER(12) NOT NULL,
                BARCODE        VARCHAR2(80),
                UOM            VARCHAR2(20),
                SYSTEM_QTY     NUMBER(18,6) DEFAULT 0,
                COUNTED_QTY    NUMBER(18,6) DEFAULT 0,
                VARIANCE_QTY   NUMBER(18,6) DEFAULT 0,
                STORAGE_ID     NUMBER(12),
                WAREHOUSE_ID   NUMBER(12),
                COUNTED_BY     VARCHAR2(50),
                AVERAGE_COST   NUMBER(18,6),
                STOCK_VALUE    NUMBER(18,2),
                PDT_SCAN_AT    TIMESTAMP(6),
                CONSTRAINT PK_STOCK_COUNT_DTL PRIMARY KEY (LOCATIONCODE, COUNT_NO, LINE_NO)
            )
            """
        )
    cur.execute(
        "SELECT COUNT(*) FROM user_indexes WHERE index_name = 'IX_STOCK_COUNT_HDR_STAT'"
    )
    if int((cur.fetchone() or [0])[0] or 0) == 0:
        cur.execute(
            f"CREATE INDEX IX_STOCK_COUNT_HDR_STAT ON {_HDR} (STATUS, COUNT_DATE)"
        )
    _invalidate_table_exists_cache(cur, _HDR)
    _invalidate_table_exists_cache(cur, _DTL)


def _require_tables(cur: Any) -> None:
    if _table_exists(cur, _HDR) and _table_exists(cur, _DTL):
        return
    try:
        _create_stock_count_tables(cur)
    except Exception as exc:
        raise ValueError(
            f"{_HDR} and {_DTL} must exist in the tenant schema. "
            "Create them in Oracle before using mobile stock counting."
        ) from exc
    if not _table_exists(cur, _HDR) or not _table_exists(cur, _DTL):
        raise ValueError(
            f"{_HDR} and {_DTL} must exist in the tenant schema. "
            "Create them in Oracle before using mobile stock counting."
        )


def _log_stock_count_journal(cur: Any, **kwargs: Any) -> None:
    """Append audit row via ERP journal helper (creates table on first use)."""
    try:
        from addons.warehouse.stock_count_db import log_stock_count_journal

        log_stock_count_journal(cur, **kwargs)
    except Exception:
        pass


def _is_editable_status(status: str) -> bool:
    """Any non-POSTED header (ERP may use DRAFT, PENDING, OPEN, etc.)."""
    st = (status or "").strip().upper()
    return st not in _POSTED_STATUSES


def _hdr_row_to_dict(row: tuple) -> dict[str, Any]:
    status = str(row[5] or "").strip().upper()
    return {
        "locationcode": int(row[0]),
        "count_no": int(row[1]),
        "count_date": row[2],
        "warehouse_id": _coerce_optional_int(row[3]),
        "storage_id": row[4],
        "status": status,
        "remarks": row[6],
        "pdt_device_id": row[7],
        "created_by": row[8],
        "created_at": row[9],
        "posted_by": row[10],
        "posted_at": row[11],
    }


def _assert_draft_hdr(cur: Any, locationcode: int, count_no: int) -> dict[str, Any]:
    cur.execute(
        f"""
        SELECT LOCATIONCODE, COUNT_NO, COUNT_DATE, WAREHOUSE_ID, STORAGE_ID,
               STATUS, REMARKS, PDT_DEVICE_ID, CREATED_BY, CREATED_AT, POSTED_BY, POSTED_AT
          FROM {_HDR}
         WHERE LOCATIONCODE = :loc AND COUNT_NO = :cn
        """,
        {"loc": locationcode, "cn": count_no},
    )
    row = cur.fetchone()
    if not row:
        raise ValueError(f"Stock count {count_no} not found for location {locationcode}")
    hdr = _hdr_row_to_dict(row)
    if not _is_editable_status(hdr["status"]):
        raise ValueError(
            f"Stock count {count_no} is {hdr['status']}; only open (non-POSTED) counts can be edited"
        )
    return hdr


def _assert_draft_hdr_locked(
    cur: Any,
    locationcode: int,
    count_no: int,
    username: str,
    *,
    auto_claim: bool = True,
) -> dict[str, Any]:
    """Lock count header row (FOR UPDATE) and verify it is still editable."""
    _ = username
    _ = auto_claim
    cur.execute(
        f"""
        SELECT LOCATIONCODE, COUNT_NO, COUNT_DATE, WAREHOUSE_ID, STORAGE_ID,
               STATUS, REMARKS, PDT_DEVICE_ID, CREATED_BY, CREATED_AT, POSTED_BY, POSTED_AT
          FROM {_HDR}
         WHERE LOCATIONCODE = :loc AND COUNT_NO = :cn
           FOR UPDATE
        """,
        {"loc": locationcode, "cn": count_no},
    )
    row = cur.fetchone()
    if not row:
        raise ValueError(f"Stock count {count_no} not found for location {locationcode}")
    hdr = _hdr_row_to_dict(row)
    if not _is_editable_status(hdr["status"]):
        raise ValueError(
            f"Stock count {count_no} is {hdr['status']}; only open (non-POSTED) counts can be edited"
        )
    return hdr


def _commit_or_rollback(conn: Any) -> None:
    """Deprecated — use oracle_transaction instead."""
    conn.commit()


def _rollback_quiet(conn: Any) -> None:
    try:
        conn.rollback()
    except Exception:
        pass


def _insert_new_hdr(
    cur: Any,
    *,
    loc: int,
    username: str,
    warehouse_id: int | None,
    storage_id: int | None,
    remarks: str,
    pdt_device_id: str,
) -> int:
    cur.execute(
        f"SELECT NVL(MAX(COUNT_NO), 0) + 1 FROM {_HDR} WHERE LOCATIONCODE = :loc",
        {"loc": loc},
    )
    count_no = int(cur.fetchone()[0] or 1)
    cur.execute(
        f"""
        INSERT INTO {_HDR} (
            LOCATIONCODE, COUNT_NO, COUNT_DATE, WAREHOUSE_ID, STORAGE_ID,
            STATUS, REMARKS, PDT_DEVICE_ID, CREATED_BY, CREATED_AT
        ) VALUES (
            :loc, :count_no, TRUNC(SYSDATE), :warehouse_id, :storage_id,
            :status, :remarks, :device, :created_by, SYSTIMESTAMP
        )
        """,
        {
            "loc": loc,
            "count_no": count_no,
            "warehouse_id": warehouse_id,
            "storage_id": storage_id,
            "status": _DRAFT_STATUS,
            "remarks": (remarks or "")[:500],
            "device": (pdt_device_id or "")[:50],
            "created_by": username[:50],
        },
    )
    _log_stock_count_journal(
        cur,
        location_code=loc,
        count_no=count_no,
        action="CREATE",
        changed_by=username[:50],
        source="MOBILE",
        warehouse_id=warehouse_id,
        storage_id=storage_id,
        pdt_device_id=(pdt_device_id or "")[:50],
        remarks=(remarks or "")[:500],
    )
    return count_no


def _is_privileged(username: str) -> bool:
    return username.strip().lower() in _PRIVILEGED_USERS


def _row_to_summary(row: tuple, *, current_user: str = "") -> dict[str, Any]:
    created_by = str(row[7] or "").strip()
    last_counted_by = str(row[10] or "").strip() if len(row) > 10 else ""
    assigned_to = last_counted_by or created_by
    user = current_user.strip().lower()
    is_mine = bool(user) and assigned_to.strip().lower() == user
    return {
        "locationcode": int(row[0]),
        "count_no": int(row[1]),
        "warehouse_id": _coerce_optional_int(row[2]),
        "count_date": row[3].isoformat() if isinstance(row[3], datetime) else str(row[3] or ""),
        "status": str(row[4] or ""),
        "remarks": row[5] or "",
        "assigned_to": assigned_to,
        "created_by": created_by,
        "created_at": row[8].isoformat() if isinstance(row[8], datetime) else None,
        "line_count": int(row[9] or 0),
        "is_unassigned": not assigned_to,
        "is_mine": is_mine,
    }


def list_sessions(
    locationcode: int | None = None,
    *,
    limit: int = 50,
    status: str = "OPEN",
    available_for_user: bool = False,
) -> list[dict[str, Any]]:
    """List stock count headers. Default: all non-POSTED counts (DRAFT, PENDING, …)."""
    _ = available_for_user
    _, tenant_id, username = _claims_context()
    lim = max(1, min(int(limit), 100))
    conn = get_connection(tenant_id=tenant_id)
    with conn.cursor() as cur:
        _require_tables(cur)
        binds: dict[str, Any] = {"lim": lim}
        where_parts = ["1=1"]

        if locationcode is not None and int(locationcode) != 0:
            loc = _coerce_location(locationcode)
            where_parts.append("h.LOCATIONCODE = :loc")
            binds["loc"] = loc

        st = (status or "").strip().upper()
        if st in ("", "OPEN", "ACTIVE"):
            where_parts.append(
                "(h.STATUS IS NULL OR UPPER(TRIM(h.STATUS)) NOT IN ('POSTED'))"
            )
        else:
            where_parts.append("UPPER(TRIM(h.STATUS)) = :status")
            binds["status"] = st


        where_sql = " AND ".join(where_parts)

        last_counter_sel = ""
        if _dtl_has_counted_by(cur):
            last_counter_sel = f""",
                   (SELECT d.COUNTED_BY
                      FROM {_DTL} d
                     WHERE d.LOCATIONCODE = h.LOCATIONCODE
                       AND d.COUNT_NO = h.COUNT_NO
                       AND d.COUNTED_BY IS NOT NULL
                     ORDER BY d.PDT_SCAN_AT DESC NULLS LAST
                     FETCH FIRST 1 ROW ONLY) AS LAST_COUNTED_BY"""

        cur.execute(
            f"""
            SELECT h.LOCATIONCODE,
                   h.COUNT_NO,
                   h.WAREHOUSE_ID,
                   h.COUNT_DATE,
                   h.STATUS,
                   h.REMARKS,
                   h.PDT_DEVICE_ID,
                   h.CREATED_BY,
                   h.CREATED_AT,
                   (SELECT COUNT(*)
                      FROM {_DTL} d
                     WHERE d.LOCATIONCODE = h.LOCATIONCODE
                       AND d.COUNT_NO = h.COUNT_NO) AS LINE_CNT
                   {last_counter_sel}
              FROM {_HDR} h
             WHERE {where_sql}
             ORDER BY h.LOCATIONCODE, h.COUNT_NO DESC
             FETCH FIRST :lim ROWS ONLY
            """,
            binds,
        )
        rows = []
        for row in cur.fetchall():
            rows.append(_row_to_summary(row, current_user=username))
        return rows


def claim_session(locationcode: int, count_no: int) -> dict[str, Any]:
    """Legacy no-op — all users may open any open count."""
    loc = _coerce_location(locationcode)
    return get_session(loc, int(count_no))


def create_new_session(
    locationcode: int,
    *,
    warehouse_id: int | None = None,
    storage_id: int | None = None,
    remarks: str = "",
    pdt_device_id: str = "",
) -> dict[str, Any]:
    """Always allocate a new COUNT_NO (does not reuse an existing DRAFT)."""
    _, tenant_id, username = _claims_context()
    loc = _coerce_location(locationcode)
    with mobile_operation_lock(
        "stock_count_create",
        str(loc),
        busy_message="Stock count is already being started. Please wait.",
    ):
        conn = get_connection(tenant_id=tenant_id)
        with oracle_transaction(conn):
            with conn.cursor() as cur:
                _require_tables(cur)
                count_no = _insert_new_hdr(
                    cur,
                    loc=loc,
                    username=username,
                    warehouse_id=warehouse_id,
                    storage_id=storage_id,
                    remarks=remarks,
                    pdt_device_id=pdt_device_id,
                )
    return get_session(loc, count_no)


def ensure_draft_session(
    locationcode: int,
    *,
    warehouse_id: int | None = None,
    storage_id: int | None = None,
    remarks: str = "",
    pdt_device_id: str = "",
) -> dict[str, Any]:
    """Return existing DRAFT header for location or create a new COUNT_NO."""
    _, tenant_id, username = _claims_context()
    loc = _coerce_location(locationcode)
    with mobile_operation_lock(
        "stock_count_create",
        str(loc),
        busy_message="Stock count is already being started. Please wait.",
    ):
        conn = get_connection(tenant_id=tenant_id)
        with conn.cursor() as cur:
            _require_tables(cur)
            cur.execute(
                f"""
                SELECT COUNT_NO FROM {_HDR}
                 WHERE LOCATIONCODE = :loc AND UPPER(TRIM(STATUS)) = :st
                 ORDER BY COUNT_NO DESC
                """,
                {"loc": loc, "st": _DRAFT_STATUS},
            )
            existing = cur.fetchone()
            if existing:
                return get_session(loc, int(existing[0]))

        with oracle_transaction(conn):
            with conn.cursor() as cur:
                _require_tables(cur)
                count_no = _insert_new_hdr(
                    cur,
                    loc=loc,
                    username=username,
                    warehouse_id=warehouse_id,
                    storage_id=storage_id,
                    remarks=remarks,
                    pdt_device_id=pdt_device_id,
                )
        return get_session(loc, count_no)


def get_current_draft(locationcode: int) -> dict[str, Any] | None:
    _, tenant_id, _ = _claims_context()
    loc = _coerce_location(locationcode)
    conn = get_connection(tenant_id=tenant_id)
    with conn.cursor() as cur:
        _require_tables(cur)
        cur.execute(
            f"""
            SELECT COUNT_NO FROM {_HDR}
             WHERE LOCATIONCODE = :loc AND UPPER(TRIM(STATUS)) = :st
             ORDER BY COUNT_NO DESC
            """,
            {"loc": loc, "st": _DRAFT_STATUS},
        )
        row = cur.fetchone()
        if not row:
            return None
        return get_session(loc, int(row[0]))


def get_session(locationcode: int, count_no: int) -> dict[str, Any]:
    _, tenant_id, _ = _claims_context()
    loc = _coerce_location(locationcode)
    cn = int(count_no)
    conn = get_connection(tenant_id=tenant_id)
    with conn.cursor() as cur:
        _require_tables(cur)
        cur.execute(
            f"""
            SELECT LOCATIONCODE, COUNT_NO, COUNT_DATE, WAREHOUSE_ID, STORAGE_ID,
                   STATUS, REMARKS, PDT_DEVICE_ID, CREATED_BY, CREATED_AT, POSTED_BY, POSTED_AT
              FROM {_HDR}
             WHERE LOCATIONCODE = :loc AND COUNT_NO = :cn
            """,
            {"loc": loc, "cn": cn},
        )
        hrow = cur.fetchone()
        if not hrow:
            raise ValueError(f"Stock count {cn} not found for location {loc}")

        retail_sel = ""
        if _dtl_has_retail_columns(cur):
            retail_sel = ", OLD_RETAIL_PRICE, NEW_RETAIL_PRICE"
        counted_by_sel = ", COUNTED_BY" if _dtl_has_counted_by(cur) else ""
        cur.execute(
            f"""
            SELECT LINE_NO, ITEMCODE, BARCODE, UOM, SYSTEM_QTY, COUNTED_QTY, VARIANCE_QTY,
                   WAREHOUSE_ID, STORAGE_ID, PDT_SCAN_AT{retail_sel}{counted_by_sel}
              FROM {_DTL}
             WHERE LOCATIONCODE = :loc AND COUNT_NO = :cn
             ORDER BY LINE_NO
            """,
            {"loc": loc, "cn": cn},
        )
        lines = []
        for row in cur.fetchall():
            line = {
                "line_no": int(row[0]),
                "itemcode": row[1],
                "itemcode_display": str(row[1]),
                "barcode": row[2] or "",
                "uom": row[3] or "",
                "system_qty": float(row[4] or 0),
                "counted_qty": float(row[5] or 0),
                "variance_qty": float(row[6] or 0),
                "warehouse_id": _coerce_optional_int(row[7]),
                "storage_id": row[8],
                "pdt_scan_at": row[9].isoformat() if row[9] else None,
            }
            idx = 10
            if retail_sel:
                line.update(_line_retail_from_row(row, base_index=idx))
                idx += 2
            if counted_by_sel:
                line["counted_by"] = str(row[idx] or "").strip()
            lines.append(line)

        payload = {
            "locationcode": int(hrow[0]),
            "count_no": int(hrow[1]),
            "count_date": hrow[2].isoformat() if isinstance(hrow[2], datetime) else str(hrow[2] or ""),
            "warehouse_id": _coerce_optional_int(hrow[3]),
            "storage_id": hrow[4],
            "status": str(hrow[5] or ""),
            "remarks": hrow[6] or "",
            "pdt_device_id": hrow[7] or "",
            "created_by": hrow[8] or "",
            "created_at": hrow[9].isoformat() if isinstance(hrow[9], datetime) else None,
            "posted_by": hrow[10],
            "posted_at": hrow[11].isoformat() if isinstance(hrow[11], datetime) else None,
            "lines": lines,
        }
        try:
            price_hdr = _get_price_hdr(cur, loc, cn)
            if price_hdr:
                payload["price_header"] = price_hdr
        except Exception:
            pass
        return payload


def upsert_line(
    locationcode: int,
    count_no: int,
    *,
    itemcode: Any,
    counted_qty: float,
    system_qty: float,
    uom: str = "",
    barcode: str = "",
    warehouse_id: int | None = None,
    storage_id: int | None = None,
    retail_price: float | None = None,
    update_retail_price: bool = False,
) -> dict[str, Any]:
    _, tenant_id, username = _claims_context()
    loc = _coerce_location(locationcode)
    cn = int(count_no)
    ic = _coerce_item_code(itemcode)
    counted = float(counted_qty)
    system = float(system_qty)
    variance = counted - system

    conn = get_connection(tenant_id=tenant_id)
    line_no = 0
    barcode_val = ""
    wh_id: int | None = None
    old_retail: float | None = None
    new_retail: float | None = None
    dtl_retail = False
    dtl_counted_by = False
    counted_by_val = (username or "")[:50]
    with mobile_operation_lock(
        "stock_count_line",
        f"{loc}:{cn}:{ic}",
        busy_message="This count line is already being saved. Please wait.",
    ), oracle_transaction(conn):
        with conn.cursor() as cur:
            _require_tables(cur)
            hdr = _assert_draft_hdr_locked(cur, loc, cn, username, auto_claim=True)
            wh_id = _resolve_warehouse_id(cur, loc, hdr, warehouse_id)
            barcode_val = _resolve_barcode(cur, ic, barcode)
            dtl_retail = _dtl_has_retail_columns(cur)
            dtl_counted_by = _dtl_has_counted_by(cur)
            counted_by_val = (username or "")[:50]
            if update_retail_price and retail_price is not None:
                old_retail = _lookup_item_retail_price(cur, ic)
                new_retail = float(retail_price)

            storage_match = (
                " AND NVL(STORAGE_ID, -1) = NVL(:storage_id, -1) " if storage_id is not None else ""
            )
            binds_find: dict[str, Any] = {"loc": loc, "count_no": cn, "itemcode": ic}
            if storage_id is not None:
                binds_find["storage_id"] = storage_id

            cur.execute(
                f"""
                SELECT LINE_NO FROM {_DTL}
                 WHERE LOCATIONCODE = :loc AND COUNT_NO = :count_no AND ITEMCODE = :itemcode
                 {storage_match}
                   FOR UPDATE
                """,
                binds_find,
            )
            existing = cur.fetchone()

            uom_val = (uom or "")[:20]

            if existing:
                line_no = int(existing[0])
                old_counted: float | None = None
                old_system: float | None = None
                old_variance: float | None = None
                cur.execute(
                    f"""
                    SELECT COUNTED_QTY, SYSTEM_QTY, VARIANCE_QTY
                      FROM {_DTL}
                     WHERE LOCATIONCODE = :loc AND COUNT_NO = :count_no AND LINE_NO = :line_no
                    """,
                    {"loc": loc, "count_no": cn, "line_no": line_no},
                )
                old_row = cur.fetchone()
                if old_row:
                    old_counted = float(old_row[0] or 0)
                    old_system = float(old_row[1] or 0)
                    old_variance = float(old_row[2] or 0)
                    system = old_system
                variance = counted - system
                retail_set = ""
                retail_binds: dict[str, Any] = {}
                if dtl_retail and new_retail is not None:
                    retail_set = ", OLD_RETAIL_PRICE = :old_retail, NEW_RETAIL_PRICE = :new_retail"
                    retail_binds = {"old_retail": old_retail, "new_retail": new_retail}
                counted_by_set = ", COUNTED_BY = :counted_by" if dtl_counted_by else ""
                cur.execute(
                    f"""
                    UPDATE {_DTL}
                       SET BARCODE = :barcode,
                           UOM = :uom,
                           COUNTED_QTY = :counted_qty,
                           VARIANCE_QTY = :variance_qty,
                           WAREHOUSE_ID = :warehouse_id,
                           STORAGE_ID = :storage_id,
                           PDT_SCAN_AT = SYSTIMESTAMP
                           {counted_by_set}
                           {retail_set}
                     WHERE LOCATIONCODE = :loc AND COUNT_NO = :count_no AND LINE_NO = :line_no
                    """,
                    {
                        "loc": loc,
                        "count_no": cn,
                        "line_no": line_no,
                        "barcode": barcode_val,
                        "uom": uom_val,
                        "counted_qty": counted,
                        "variance_qty": variance,
                        "warehouse_id": wh_id,
                        "storage_id": storage_id,
                        **({"counted_by": counted_by_val} if dtl_counted_by else {}),
                        **retail_binds,
                    },
                )
                _log_stock_count_journal(
                    cur,
                    location_code=loc,
                    count_no=cn,
                    action="UPDATE",
                    line_no=line_no,
                    itemcode=ic,
                    old_counted_qty=old_counted,
                    new_counted_qty=counted,
                    old_system_qty=old_system,
                    new_system_qty=system,
                    old_variance_qty=old_variance,
                    new_variance_qty=variance,
                    barcode=barcode_val,
                    uom=uom_val,
                    warehouse_id=wh_id,
                    storage_id=storage_id,
                    counted_by=counted_by_val,
                    changed_by=counted_by_val,
                    source="MOBILE",
                )
            else:
                cur.execute(
                    f"""
                    SELECT NVL(MAX(LINE_NO), 0) + 1 FROM {_DTL}
                     WHERE LOCATIONCODE = :loc AND COUNT_NO = :count_no
                    """,
                    {"loc": loc, "count_no": cn},
                )
                line_no = int(cur.fetchone()[0] or 1)
                variance = counted - system
                retail_cols = ""
                retail_vals = ""
                retail_ins: dict[str, Any] = {}
                if dtl_retail and new_retail is not None:
                    retail_cols = ", OLD_RETAIL_PRICE, NEW_RETAIL_PRICE"
                    retail_vals = ", :old_retail, :new_retail"
                    retail_ins = {"old_retail": old_retail, "new_retail": new_retail}
                counted_by_col = ", COUNTED_BY" if dtl_counted_by else ""
                counted_by_val_sql = ", :counted_by" if dtl_counted_by else ""
                cur.execute(
                    f"""
                    INSERT INTO {_DTL} (
                        LOCATIONCODE, COUNT_NO, LINE_NO, ITEMCODE, BARCODE, UOM,
                        SYSTEM_QTY, COUNTED_QTY, VARIANCE_QTY, WAREHOUSE_ID, STORAGE_ID, PDT_SCAN_AT
                        {counted_by_col}
                        {retail_cols}
                    ) VALUES (
                        :loc, :count_no, :line_no, :itemcode, :barcode, :uom,
                        :system_qty, :counted_qty, :variance_qty, :warehouse_id, :storage_id, SYSTIMESTAMP
                        {counted_by_val_sql}
                        {retail_vals}
                    )
                    """,
                    {
                        "loc": loc,
                        "count_no": cn,
                        "line_no": line_no,
                        "itemcode": ic,
                        "barcode": barcode_val,
                        "uom": uom_val,
                        "system_qty": system,
                        "counted_qty": counted,
                        "variance_qty": variance,
                        "warehouse_id": wh_id,
                        "storage_id": storage_id,
                        **({"counted_by": counted_by_val} if dtl_counted_by else {}),
                        **retail_ins,
                    },
                )
                _log_stock_count_journal(
                    cur,
                    location_code=loc,
                    count_no=cn,
                    action="INSERT",
                    line_no=line_no,
                    itemcode=ic,
                    new_counted_qty=counted,
                    new_system_qty=system,
                    new_variance_qty=variance,
                    barcode=barcode_val,
                    uom=uom_val,
                    warehouse_id=wh_id,
                    storage_id=storage_id,
                    counted_by=counted_by_val,
                    changed_by=counted_by_val,
                    source="MOBILE",
                )

            if new_retail is not None:
                price_batch_no = _ensure_price_hdr(
                    cur,
                    loc=loc,
                    count_no=cn,
                    username=username,
                    warehouse_id=wh_id,
                )
                _upsert_price_update_row(
                    cur,
                    loc=loc,
                    count_no=cn,
                    line_no=line_no,
                    itemcode=ic,
                    old_retail=old_retail,
                    new_retail=new_retail,
                    username=username,
                    batch_no=price_batch_no,
                )

    return {
        "line_no": line_no,
        "itemcode": ic,
        "itemcode_display": str(ic),
        "counted_qty": counted,
        "system_qty": system,
        "variance_qty": variance,
        "warehouse_id": wh_id,
        "uom": uom,
        "barcode": barcode_val,
        "counted_by": counted_by_val if dtl_counted_by else "",
        "old_retail_price": old_retail,
        "new_retail_price": new_retail,
        "update_retail_price": new_retail is not None,
    }


def _delete_price_update_for_item(cur: Any, loc: int, count_no: int, itemcode: int) -> None:
    if not _fresh_table_exists(cur, _PRICE_UPD):
        return
    cur.execute(
        f"""
        DELETE FROM {_PRICE_UPD}
         WHERE LOCATIONCODE = :loc AND COUNT_NO = :cn AND ITEMCODE = :ic
        """,
        {"loc": loc, "cn": count_no, "ic": itemcode},
    )


def delete_line_by_itemcode(locationcode: int, count_no: int, itemcode: Any) -> None:
    _, tenant_id, username = _claims_context()
    loc = _coerce_location(locationcode)
    cn = int(count_no)
    ic = _coerce_item_code(itemcode)
    conn = get_connection(tenant_id=tenant_id)
    with mobile_operation_lock(
        "stock_count_line",
        f"{loc}:{cn}:{ic}",
        busy_message="This count line is already being updated. Please wait.",
    ), oracle_transaction(conn):
        with conn.cursor() as cur:
            _require_tables(cur)
            _assert_draft_hdr_locked(cur, loc, cn, username, auto_claim=False)
            cur.execute(
                f"""
                SELECT LINE_NO, COUNTED_QTY, SYSTEM_QTY, VARIANCE_QTY, BARCODE, UOM,
                       WAREHOUSE_ID, STORAGE_ID
                  FROM {_DTL}
                 WHERE LOCATIONCODE = :loc AND COUNT_NO = :cn AND ITEMCODE = :ic
                """,
                {"loc": loc, "cn": cn, "ic": ic},
            )
            for old in cur.fetchall() or []:
                _log_stock_count_journal(
                    cur,
                    location_code=loc,
                    count_no=cn,
                    action="DELETE",
                    line_no=int(old[0]),
                    itemcode=ic,
                    old_counted_qty=float(old[1] or 0),
                    old_system_qty=float(old[2] or 0),
                    old_variance_qty=float(old[3] or 0),
                    barcode=str(old[4] or ""),
                    uom=str(old[5] or ""),
                    warehouse_id=_coerce_optional_int(old[6]),
                    storage_id=old[7],
                    changed_by=username[:50],
                    source="MOBILE",
                )
            cur.execute(
                f"""
                DELETE FROM {_DTL}
                 WHERE LOCATIONCODE = :loc AND COUNT_NO = :cn AND ITEMCODE = :ic
                """,
                {"loc": loc, "cn": cn, "ic": ic},
            )
            _delete_price_update_for_item(cur, loc, cn, ic)


def delete_line(locationcode: int, count_no: int, line_no: int) -> None:
    _, tenant_id, username = _claims_context()
    loc = _coerce_location(locationcode)
    cn = int(count_no)
    ln = int(line_no)
    conn = get_connection(tenant_id=tenant_id)
    with mobile_operation_lock(
        "stock_count_line",
        f"{loc}:{cn}:ln:{ln}",
        busy_message="This count line is already being updated. Please wait.",
    ), oracle_transaction(conn):
        with conn.cursor() as cur:
            _require_tables(cur)
            _assert_draft_hdr_locked(cur, loc, cn, username, auto_claim=False)
            cur.execute(
                f"""
                SELECT ITEMCODE FROM {_DTL}
                 WHERE LOCATIONCODE = :loc AND COUNT_NO = :cn AND LINE_NO = :ln
                """,
                {"loc": loc, "cn": cn, "ln": ln},
            )
            item_row = cur.fetchone()
            if not item_row:
                raise ValueError("Line not found")
            ic = int(item_row[0])
            cur.execute(
                f"""
                SELECT COUNTED_QTY, SYSTEM_QTY, VARIANCE_QTY, BARCODE, UOM,
                       WAREHOUSE_ID, STORAGE_ID
                  FROM {_DTL}
                 WHERE LOCATIONCODE = :loc AND COUNT_NO = :cn AND LINE_NO = :ln
                """,
                {"loc": loc, "cn": cn, "ln": ln},
            )
            old = cur.fetchone()
            if old:
                _log_stock_count_journal(
                    cur,
                    location_code=loc,
                    count_no=cn,
                    action="DELETE",
                    line_no=ln,
                    itemcode=ic,
                    old_counted_qty=float(old[0] or 0),
                    old_system_qty=float(old[1] or 0),
                    old_variance_qty=float(old[2] or 0),
                    barcode=str(old[3] or ""),
                    uom=str(old[4] or ""),
                    warehouse_id=_coerce_optional_int(old[5]),
                    storage_id=old[6],
                    changed_by=username[:50],
                    source="MOBILE",
                )
            cur.execute(
                f"""
                DELETE FROM {_DTL}
                 WHERE LOCATIONCODE = :loc AND COUNT_NO = :cn AND LINE_NO = :ln
                """,
                {"loc": loc, "cn": cn, "ln": ln},
            )
            _delete_price_update_for_item(cur, loc, cn, ic)


def post_session(locationcode: int, count_no: int) -> dict[str, Any]:
    """Post count to inventory (warehouse stock, item journal, GL) via shared ERP logic."""
    _, tenant_id, username = _claims_context()
    loc = _coerce_location(locationcode)
    cn = int(count_no)
    with mobile_operation_lock(
        "stock_count_post",
        f"{loc}:{cn}",
        lock_seconds=300.0,
        busy_message="Stock count is already being posted. Please wait.",
    ):
        conn = get_connection(tenant_id=tenant_id)
        with oracle_transaction(conn):
            with conn.cursor() as cur:
                _require_tables(cur)
                _assert_draft_hdr_locked(cur, loc, cn, username, auto_claim=False)
                _apply_pending_retail_prices(cur, loc, cn, username)

        from addons.warehouse.stock_count_db import post_stock_count_to_inventory

        ok, err, _meta = post_stock_count_to_inventory(loc, cn, posted_by=username)
        if not ok:
            raise ValueError(err or "Post failed")
    return get_session(loc, cn)
