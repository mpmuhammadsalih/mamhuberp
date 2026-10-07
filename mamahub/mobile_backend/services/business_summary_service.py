"""Mobile Business Summary — wraps ERP Daily Business Summary engine."""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 180
_summary_cache: dict[tuple[str, str, str, str], tuple[float, dict[str, Any]]] = {}


def _cache_key(tenant_id: str, date_from: str, date_to: str, branch: str) -> tuple[str, str, str, str]:
    return (
        tenant_id or "default",
        date_from.strip(),
        date_to.strip(),
        branch.strip(),
    )


def _read_cache(key: tuple[str, str, str, str]) -> dict[str, Any] | None:
    entry = _summary_cache.get(key)
    if not entry:
        return None
    expires_at, payload = entry
    if time.time() >= expires_at:
        _summary_cache.pop(key, None)
        return None
    return payload


def _write_cache(key: tuple[str, str, str, str], payload: dict[str, Any]) -> None:
    _summary_cache[key] = (time.time() + _CACHE_TTL_SECONDS, payload)
    if len(_summary_cache) > 64:
        oldest = min(_summary_cache.items(), key=lambda item: item[1][0])[0]
        _summary_cache.pop(oldest, None)


def _request_tenant_id() -> str:
    try:
        from mobile_backend.request_context import get_jwt

        return str(get_jwt().get("tenant_id") or "").strip()
    except Exception:
        return ""


def _kpi_value(kpis: list[Any], kpi_id: str) -> float:
    for k in kpis:
        if isinstance(k, dict) and str(k.get("id") or "") == kpi_id:
            try:
                return float(k.get("value") or 0)
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def _set_kpi(kpis: list[Any], kpi_id: str, value: float, label: str | None = None) -> None:
    for k in kpis:
        if isinstance(k, dict) and str(k.get("id") or "") == kpi_id:
            k["value"] = round(float(value), 2)
            if label:
                k["label"] = label
            return
    kpis.append(
        {
            "id": kpi_id,
            "label": label or kpi_id,
            "value": round(float(value), 2),
            "format": "currency",
            "icon": "bi-cart-check",
        }
    )


def _reconcile_sales_from_billhdr(payload: dict[str, Any], date_from: str, date_to: str) -> None:
    """If engine sales are 0, fill from live BILLHDR invoice list (same as Sales Invoices)."""
    kpis = list(payload.get("kpis") or [])
    if _kpi_value(kpis, "total_sales") > 0 or _kpi_value(kpis, "net_sales") > 0:
        payload["kpis"] = kpis
        return
    try:
        from mobile_backend.services import sales_invoice_service as sis

        rows = (
            sis.list_invoices(
                date_from=(date_from or "")[:10],
                date_to=(date_to or "")[:10],
                limit=100,
            )
            or []
        )
    except Exception:
        logger.debug("business summary BILLHDR reconcile failed", exc_info=True)
        payload["kpis"] = kpis
        return

    if not rows:
        payload["kpis"] = kpis
        return

    total = round(sum(float(r.get("net_amount") or 0) for r in rows), 2)
    cash = round(
        sum(
            float(r.get("net_amount") or 0)
            for r in rows
            if str(r.get("billing_type") or "").upper() != "CREDIT"
        ),
        2,
    )
    credit = round(
        sum(
            float(r.get("net_amount") or 0)
            for r in rows
            if str(r.get("billing_type") or "").upper() == "CREDIT"
        ),
        2,
    )
    sales_return = _kpi_value(kpis, "sales_return")
    net = round(total - sales_return, 2)

    _set_kpi(kpis, "total_sales", total, "Total Sales")
    _set_kpi(kpis, "net_sales", net, "Net Sales")
    _set_kpi(kpis, "cash_sales", cash, "Cash Sales")
    _set_kpi(kpis, "credit_sales", credit, "Credit Sales")
    payload["kpis"] = kpis
    payload["sales_source"] = "billhdr"

    financial = dict(payload.get("financial") or {})
    financial["sales"] = total
    financial["net_sales"] = net
    if not financial.get("gross_profit"):
        financial["gross_profit"] = max(0.0, net - float(financial.get("net_purchases") or 0))
        if net:
            financial["gross_profit_pct"] = round(
                float(financial["gross_profit"]) / net * 100.0, 2
            )
    payload["financial"] = financial

    # Drop the misleading "No sales found" warning once reconciled.
    warnings = [
        w
        for w in (payload.get("warnings") or [])
        if "No sales found" not in str(w)
    ]
    payload["warnings"] = warnings

    tx = list(payload.get("transaction_summary") or [])
    replaced = False
    for row in tx:
        if isinstance(row, dict) and str(row.get("transaction") or "").strip().lower() == "sales":
            row["count"] = len(rows)
            row["amount"] = total
            replaced = True
            break
    if not replaced:
        tx.insert(
            0,
            {
                "transaction": "Sales",
                "count": len(rows),
                "amount": total,
                "percentage": 0,
            },
        )
    payload["transaction_summary"] = tx


def get_business_summary(
    *,
    date_from: str = "",
    date_to: str = "",
    branch: str = "",
) -> dict[str, Any]:
    from addons.business_summary.services.business_summary_engine import (
        _reset_sales_ctx,
        build_business_summary_dashboard,
    )
    from db import get_location_info_by_dbkey

    tenant_id = _request_tenant_id()
    branch_resolved = branch.strip()
    raw: dict[str, Any] = {"profile": "mobile"}

    if date_from.strip():
        raw["date_from"] = date_from.strip()
    if date_to.strip():
        raw["date_to"] = date_to.strip()

    if branch_resolved:
        raw["branch"] = branch_resolved
    else:
        try:
            info = get_location_info_by_dbkey(None) or {}
            loc = info.get("locationcode")
            if loc is not None:
                raw["branch"] = loc
                branch_resolved = str(loc)
        except Exception:
            logger.debug("Could not resolve default branch for business summary", exc_info=True)

    cache_key = _cache_key(tenant_id, date_from, date_to, branch_resolved)
    cached = _read_cache(cache_key)
    if cached is not None:
        return cached

    # Drop stale BILLHDRHISTORY context from a previous process load.
    _reset_sales_ctx()
    payload = build_business_summary_dashboard(raw)

    if not payload.get("success"):
        msg = "Business summary unavailable"
        warnings = payload.get("warnings") or []
        if warnings:
            msg = str(warnings[0])[:300]
        raise RuntimeError(msg)

    df = str(raw.get("date_from") or date_from or "")[:10]
    dt = str(raw.get("date_to") or date_to or df)[:10]
    _reconcile_sales_from_billhdr(payload, df, dt)

    warnings = list(payload.get("warnings") or [])
    kpis = payload.get("kpis") or []
    net_sales = next((k for k in kpis if k.get("id") == "net_sales"), {})
    sales_count = next((k for k in kpis if k.get("id") == "total_sales"), {})
    if float(net_sales.get("value") or 0) == 0 and float(sales_count.get("value") or 0) == 0:
        branch_filter = (payload.get("filters") or {}).get("branch")
        branch_note = f" branch {branch_filter}" if branch_filter else ""
        if not any("Sales tables" in str(w) for w in warnings):
            warnings.insert(
                0,
                f"No sales found for {raw.get('date_from', '')} to {raw.get('date_to', '')}{branch_note}. "
                "Try This month, pick another branch in ERP, or confirm bills exist in that period.",
            )

    result = {
        "generated_at": payload.get("generated_at") or "",
        "filters": payload.get("filters") or {},
        "warnings": warnings,
        "sales_source": payload.get("sales_source") or "",
        "kpis": payload.get("kpis") or [],
        "charts": payload.get("charts") or {},
        "transaction_summary": payload.get("transaction_summary") or [],
        "financial": payload.get("financial") or {},
        "inventory": payload.get("inventory") or {},
        "profile": payload.get("profile") or "mobile",
    }
    _write_cache(cache_key, result)
    return result
