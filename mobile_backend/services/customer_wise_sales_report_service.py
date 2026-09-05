"""Mobile Customer Wise Sales — same BILLHDR aggregates as ERP Customer Wise Sales."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any


def _to_float(v: Any, default: float = 0.0) -> float:
    if v is None or (isinstance(v, str) and not str(v).strip()):
        return default
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def _to_int(v: Any, default: int = 0) -> int:
    try:
        if v is None or v == "":
            return default
        return int(float(str(v).strip()))
    except (TypeError, ValueError):
        return default


def _parse_iso(s: str | None) -> date | None:
    raw = str(s or "").strip()[:10]
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


def _default_range(date_from: str, date_to: str) -> tuple[str, str]:
    d_to = _parse_iso(date_to) or date.today()
    d_from = _parse_iso(date_from) or (d_to - timedelta(days=29))
    if d_from > d_to:
        d_from, d_to = d_to, d_from
    return d_from.isoformat(), d_to.isoformat()


def _normalize_row(raw: dict[str, Any]) -> dict[str, Any]:
    code = raw.get("customercode")
    return {
        "customer_code": str(code if code is not None else "").strip(),
        "customer_name": str(raw.get("customername") or "").strip(),
        "bill_count": _to_int(raw.get("billcount")),
        "sales_amount": round(_to_float(raw.get("salesamount")), 2),
        "return_bill_count": _to_int(raw.get("return_billcount")),
        "sales_return": round(_to_float(raw.get("sales_return")), 2),
        "total_bill_count": _to_int(raw.get("total_billcount")),
        "total_sale": round(_to_float(raw.get("total_sale")), 2),
    }


def get_customer_wise_sales(
    *,
    date_from: str = "",
    date_to: str = "",
    customer_code: str = "",
    bill_type: str = "",
) -> dict[str, Any]:
    """Customer aggregates matching ERP Customer Wise Sales report."""
    from addons.reports.controllers import routes as erp_reports
    from mobile_backend.services.stock_transfer_service import _erp_session_scope

    df, dt = _default_range(date_from, date_to)
    cust_raw = str(customer_code or "").strip()
    customer_i = int(cust_raw) if cust_raw.isdigit() else None
    bt = str(bill_type or "").strip().upper()[:1]

    with _erp_session_scope():
        rows_raw, totals_raw = erp_reports._get_customer_wise_sales_rows(
            date_from=df,
            date_to=dt,
            customer_code=customer_i,
            bill_type=bt,
        )

    rows = [_normalize_row(r) for r in (rows_raw or [])]
    totals = {
        "customer_count": len(rows),
        "bill_count": _to_int((totals_raw or {}).get("billcount")),
        "sales_amount": round(_to_float((totals_raw or {}).get("salesamount")), 2),
        "return_bill_count": _to_int((totals_raw or {}).get("return_billcount")),
        "sales_return": round(_to_float((totals_raw or {}).get("sales_return")), 2),
        "total_bill_count": _to_int((totals_raw or {}).get("total_billcount")),
        "total_sale": round(_to_float((totals_raw or {}).get("total_sale")), 2),
    }
    return {
        "date_from": df,
        "date_to": dt,
        "period_label": df if df == dt else f"{df} → {dt}",
        "filters": {
            "customer_code": cust_raw,
            "bill_type": bt,
        },
        "rows": rows,
        "summary": totals,
    }
