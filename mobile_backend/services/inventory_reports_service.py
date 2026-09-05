"""Mobile inventory reports — wraps ERP report engines (same as desktop hubs)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from mobile_backend.services.stock_transfer_service import _erp_session_scope


def _loc() -> int:
    from db import get_location_info_by_dbkey

    try:
        info = get_location_info_by_dbkey(None) or {}
        return int(info.get("locationcode") or 1)
    except Exception:
        return 1


def _default_range(date_from: str, date_to: str, *, days: int = 30) -> tuple[str, str]:
    df = (date_from or "").strip()
    dt = (date_to or "").strip()
    today = date.today()
    if not dt:
        dt = today.isoformat()
    if not df:
        df = (today - timedelta(days=max(1, days - 1))).isoformat()
    return df, dt


def _json_safe(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, dict):
        return {str(k): _json_safe(val) for k, val in v.items()}
    if isinstance(v, (list, tuple)):
        return [_json_safe(x) for x in v]
    if hasattr(v, "isoformat"):
        try:
            return v.isoformat()
        except Exception:
            return str(v)
    try:
        if hasattr(v, "as_tuple"):  # Decimal
            return float(v)
    except Exception:
        pass
    return str(v)


def warehouse_summary(*, search: str = "") -> dict[str, Any]:
    from addons.reports.inventory_reports_logic import get_warehouse_summary_report_rows

    with _erp_session_scope():
        loc = _loc()
        rows, summary = get_warehouse_summary_report_rows(loc, search=search or "")
        return {
            "location_code": loc,
            "rows": [_json_safe(dict(r)) for r in (rows or [])],
            "summary": _json_safe(dict(summary or {})),
        }


def supplier_balance(*, search: str = "", min_balance: float = 0.0) -> dict[str, Any]:
    from addons.reports.inventory_reports_logic import get_supplier_balance_report_rows

    with _erp_session_scope():
        rows, summary = get_supplier_balance_report_rows(
            search=search or "",
            min_balance=float(min_balance or 0),
        )
        return {
            "rows": [_json_safe(dict(r)) for r in (rows or [])],
            "summary": _json_safe(dict(summary or {})),
        }


def inventory_aging(
    *,
    as_on_date: str = "",
    search: str = "",
    warehouse_id: str = "",
) -> dict[str, Any]:
    from addons.reports.stock_aging_logic import build_stock_aging_payload

    with _erp_session_scope():
        loc = _loc()
        as_on = (as_on_date or "").strip() or date.today().isoformat()
        filters: dict[str, Any] = {
            "locationcode": loc,
            "branch": loc,
            "as_on_date": as_on,
            "search": (search or "").strip(),
        }
        wid = (warehouse_id or "").strip()
        if wid.isdigit():
            filters["warehouse_id"] = int(wid)
        payload = build_stock_aging_payload(filters)
        # Trim heavy chart payloads for mobile list UX.
        rows = payload.get("rows") or []
        if len(rows) > 500:
            rows = rows[:500]
        return {
            "location_code": loc,
            "as_on_date": as_on,
            "success": bool(payload.get("success")),
            "error": payload.get("error"),
            "rows": [_json_safe(dict(r) if isinstance(r, dict) else {"value": r}) for r in rows],
            "summary": _json_safe(dict(payload.get("summary") or {})),
            "insights": _json_safe(payload.get("insights") or []),
            "buckets": _json_safe(payload.get("buckets") or []),
        }


def stock_summary(
    *,
    search: str = "",
    warehouse_id: str = "",
    include_zero: bool = False,
    limit: int = 200,
) -> dict[str, Any]:
    from db import get_inventory_valuation_report

    with _erp_session_scope():
        loc = _loc()
        wid = None
        wraw = (warehouse_id or "").strip()
        if wraw.isdigit():
            wid = int(wraw)
        lim = max(1, min(int(limit or 200), 500))
        payload = get_inventory_valuation_report(
            loc,
            warehouse_id=wid,
            search=(search or "").strip() or None,
            include_zero=bool(include_zero),
            limit=lim,
            offset=0,
        )
        data = dict(payload or {})
        rows = data.get("rows") or data.get("items") or []
        summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
        if not summary:
            summary = {
                "item_count": data.get("total_count") or len(rows),
                "total_qty": sum(float(r.get("qty") or 0) for r in rows if isinstance(r, dict)),
                "total_value": sum(float(r.get("stockvalue") or 0) for r in rows if isinstance(r, dict)),
            }
        return {
            "location_code": loc,
            "warehouse_id": wid or 0,
            "warehouse_label": data.get("warehouse_label") or "",
            "rows": [_json_safe(dict(r) if isinstance(r, dict) else {"value": r}) for r in rows],
            "summary": _json_safe(dict(summary)),
        }


def stock_ledger(
    *,
    date_from: str = "",
    date_to: str = "",
    search: str = "",
    item_code: str = "",
    report_mode: str = "detail",
    limit: int = 500,
) -> dict[str, Any]:
    from addons.reports.controllers import routes as reports_mod

    df, dt = _default_range(date_from, date_to, days=14)
    mode = (report_mode or "detail").strip().lower()
    if mode not in ("summary", "summary_stock", "detail"):
        mode = "detail"
    cap = max(1, min(int(limit or 500), 2000))

    with _erp_session_scope():
        loc = _loc()
        rows, err = reports_mod._get_stock_report_datewise_rows(
            date_from=df,
            date_to=dt,
            search=search or "",
            itemcode=item_code or "",
            category_code="",
            transtype="",
            report_mode=mode,
            row_cap=cap,
        )
        if err:
            raise ValueError(str(err))
        return {
            "location_code": loc,
            "date_from": df,
            "date_to": dt,
            "report_mode": mode,
            "rows": [_json_safe(dict(r)) for r in (rows or [])],
            "count": len(rows or []),
        }


def inventory_history(
    *,
    date_from: str = "",
    date_to: str = "",
    search: str = "",
    item_code: str = "",
    limit: int = 500,
) -> dict[str, Any]:
    """Transaction history from ITEMJOURNAL (same source as ERP item journal / stock detail)."""
    return stock_ledger(
        date_from=date_from,
        date_to=date_to,
        search=search,
        item_code=item_code,
        report_mode="detail",
        limit=limit,
    )
