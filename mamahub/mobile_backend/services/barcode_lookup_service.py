"""POS-style item lookup for mobile scan (MANUFACTURERID + alternate UOM barcodes)."""

from __future__ import annotations

from typing import Any

from mobile_backend.services.stock_transfer_service import _erp_session_scope


def resolve_location_code(override: int | None = None) -> int:
    if override is not None and int(override) > 0:
        return int(override)
    from db import get_location_info_by_dbkey
    from nexa_http.session_wrap import session

    loc = session.get("location_code")
    if loc is not None:
        try:
            return int(loc)
        except (TypeError, ValueError):
            pass
    info = get_location_info_by_dbkey(None) or {}
    return int(info.get("locationcode") or 1)


def _item_to_inventory_dict(item: dict[str, Any], *, scan_query: str) -> dict[str, Any]:
    code = item.get("ITEMCODE") or item.get("itemcode") or item.get("item_code")
    name = item.get("ITEMNAME") or item.get("itemname") or item.get("item_name") or ""
    uom = (
        item.get("BASEUOM")
        or item.get("baseuom")
        or item.get("unitofmeasurement")
        or item.get("UNITOFMEASUREMENT")
        or item.get("uom")
        or "PCS"
    )
    mfr = str(
        item.get("MANUFACTURERID")
        or item.get("manufacturerid")
        or item.get("manufacturer_id")
        or scan_query
        or ""
    ).strip()
    retail = float(item.get("RETAILPRICE") or item.get("retailprice") or item.get("retail_price") or 0)
    stock = float(item.get("CURRENTSTOCK") or item.get("currentstock") or item.get("current_stock") or 0)
    return {
        "itemcode": str(code or "").strip(),
        "itemname": str(name or "").strip(),
        "unit": str(uom or "").strip() or "PCS",
        "qty_on_hand": stock,
        "barcode": mfr,
        "retail_price": retail,
    }


def lookup_item_row(query: str, *, locationcode: int | None = None) -> dict[str, Any]:
    """Same resolution order as ERP POS / sales invoice scan."""
    from db import (
        get_item_by_alternate_barcode,
        get_item_by_code,
        get_item_by_manufacturer_id,
    )

    q = (query or "").strip()
    if not q:
        raise ValueError("Item code or barcode is required.")

    with _erp_session_scope():
        loc = resolve_location_code(locationcode)
        item = None
        if q.isdigit():
            try:
                item = get_item_by_code(int(q), loc)
            except Exception:
                item = None
        if not item:
            item = get_item_by_manufacturer_id(q, loc)
        if not item:
            item = get_item_by_alternate_barcode(q, loc)
        if not item:
            raise ValueError("Item not found.")
        return _item_to_inventory_dict(dict(item), scan_query=q)


def lookup_queries(queries: list[str], *, locationcode: int | None = None) -> tuple[str, dict[str, Any]] | None:
    seen: set[str] = set()
    for raw in queries:
        q = (raw or "").strip()
        if not q:
            continue
        key = q.upper()
        if key in seen:
            continue
        seen.add(key)
        try:
            row = lookup_item_row(q, locationcode=locationcode)
            return q, row
        except ValueError:
            continue
    return None


def lookup_storage_row(query: str, *, locationcode: int | None = None) -> dict[str, Any]:
    """Resolve shelf/bin/rack by STORAGE_BARCODE or CODE (ERP Barcode Management — Shelf)."""
    from db import (
        WAREHOUSE_STORAGE_TABLE,
        _detect_column,
        _get_table_columns,
        _safe_rows,
        _table_exists,
        ensure_warehouse_storage_table,
        get_warehouse_storage_by_id,
    )

    q = (query or "").strip()
    if not q:
        raise ValueError("Shelf / bin barcode is required.")

    with _erp_session_scope():
        loc = resolve_location_code(locationcode)
        ensure_warehouse_storage_table()
        if not _table_exists(WAREHOUSE_STORAGE_TABLE):
            raise ValueError("Warehouse storage (shelves/bins) is not configured.")

        cols = {c.upper() for c in (_get_table_columns(WAREHOUSE_STORAGE_TABLE) or [])}
        loc_col = _detect_column(WAREHOUSE_STORAGE_TABLE, ["LOCATIONCODE", "locationcode"])
        code_col = _detect_column(WAREHOUSE_STORAGE_TABLE, ["CODE", "code"])
        bc_col = "STORAGE_BARCODE" if "STORAGE_BARCODE" in cols else None
        if not code_col:
            raise ValueError("Storage CODE column missing.")

        where_bits = [f"UPPER(TRIM({code_col})) = :qu"]
        if bc_col:
            where_bits.insert(0, f"UPPER(TRIM(NVL({bc_col}, ''))) = :qu")
        where_sql = " OR ".join(where_bits)

        def _find(exact: bool, use_loc: bool) -> list[dict[str, Any]]:
            params: dict[str, Any] = {}
            if exact:
                params["qu"] = q.upper()
                clause = where_sql
            else:
                params["like"] = f"%{q.upper()}%"
                soft = [f"UPPER(TRIM({code_col})) LIKE :like"]
                if bc_col:
                    soft.insert(0, f"UPPER(TRIM(NVL({bc_col}, ''))) LIKE :like")
                clause = " OR ".join(soft)
            sql = (
                f"SELECT STORAGE_ID AS storage_id FROM {WAREHOUSE_STORAGE_TABLE} "
                f"WHERE ({clause})"
            )
            if use_loc and loc_col:
                params["loc"] = loc
                sql += f" AND {loc_col} = :loc"
            sql += " AND ROWNUM = 1"
            return _safe_rows(sql, params) or []

        rows = (
            _find(True, True)
            or _find(True, False)
            or _find(False, True)
            or _find(False, False)
        )
        if not rows:
            raise ValueError("Shelf / bin not found for that barcode.")

        try:
            sid = int(rows[0].get("storage_id") or 0)
        except (TypeError, ValueError):
            sid = 0
        if sid <= 0:
            raise ValueError("Shelf / bin not found for that barcode.")

        row = get_warehouse_storage_by_id(sid) or {}
        stype = str(row.get("storage_type") or "").strip().upper() or "BIN"
        code = str(row.get("code") or "").strip()
        name = str(row.get("name") or "").strip() or code
        barcode = str(row.get("storage_barcode") or "").strip() or code
        parent_code = ""
        try:
            pid = int(row.get("parent_storage_id") or 0)
        except (TypeError, ValueError):
            pid = 0
        if pid > 0:
            parent = get_warehouse_storage_by_id(pid) or {}
            parent_code = str(parent.get("code") or parent.get("name") or "").strip()
        path_bits = [b for b in (parent_code, code) if b]
        path = " › ".join(path_bits) if path_bits else code
        try:
            wid = int(row.get("warehouse_id") or 0) or None
        except (TypeError, ValueError):
            wid = None
        try:
            row_loc = int(row.get("locationcode") or loc or 0) or loc
        except (TypeError, ValueError):
            row_loc = loc
        return {
            "storage_id": sid,
            "storage_type": stype,
            "code": code,
            "name": name,
            "status": str(row.get("status") or "").strip(),
            "barcode": barcode,
            "print_value": barcode,
            "path": path,
            "warehouse_id": wid,
            "location_code": row_loc,
            "label_title": name,
            "label_subtitle": f"{stype} · {path}",
        }
