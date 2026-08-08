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
