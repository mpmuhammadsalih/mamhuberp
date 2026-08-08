"""Mobile Trial Balance, Profit & Loss, Balance Sheet — wraps ERP accounts reports."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from mobile_backend.services.stock_transfer_service import _erp_session_scope


def _accounts():
    from addons.accounts.controllers import routes as accounts

    return accounts


def _parse_iso_date(raw: Any) -> str:
    s = str(raw or "").strip()[:10]
    if not s:
        return ""
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return s
    except ValueError:
        return ""


def _fmt_display(iso: str) -> str:
    if not (iso or "").strip():
        return ""
    try:
        return datetime.strptime(iso.strip()[:10], "%Y-%m-%d").strftime("%d %B %Y")
    except Exception:
        return iso


def _company_name() -> str:
    try:
        from addons.purchase.controllers.routes import _get_company_profile

        company = _get_company_profile() or {}
        name = str(company.get("name") or "").strip()
        if name:
            return name
    except Exception:
        pass
    return "Company"


def _truthy_exclude(raw: Any) -> bool:
    if raw is None:
        return True
    if isinstance(raw, bool):
        return raw
    s = str(raw).strip().lower()
    if s in ("0", "false", "no", "off", "include", "n"):
        return False
    return True


def get_trial_balance(
    *,
    date_from: str = "",
    date_to: str = "",
    exclude_closing: Any = True,
) -> dict[str, Any]:
    from db import get_trial_balance_report

    df = _parse_iso_date(date_from)
    dt = _parse_iso_date(date_to)
    excl = _truthy_exclude(exclude_closing)

    with _erp_session_scope():
        a = _accounts()
        a._apply_db()
        raw = get_trial_balance_report(
            date_from=df or None,
            date_to=dt or None,
            exclude_closing=excl,
        )
        rows = a._enrich_trial_balance_rows(raw)
        total_debit = round(sum(float(r.get("debit") or 0) for r in rows), 2)
        total_credit = round(sum(float(r.get("credit") or 0) for r in rows), 2)
        df_disp = _fmt_display(df)
        dt_disp = _fmt_display(dt)
        if df_disp and dt_disp:
            period_display = f"{df_disp} to {dt_disp}"
        elif dt_disp:
            period_display = f"Up to {dt_disp}"
        elif df_disp:
            period_display = f"From {df_disp}"
        else:
            period_display = "All dates"
        if excl:
            period_display = f"{period_display} (excluding period closing & reopen reversals)"
        return {
            "company_name": _company_name(),
            "period_display": period_display,
            "date_from": df,
            "date_to": dt,
            "rows": rows,
            "total_debit": total_debit,
            "total_credit": total_credit,
            "exclude_closing": excl,
        }


def build_trial_balance_pdf(
    *,
    date_from: str = "",
    date_to: str = "",
    exclude_closing: Any = True,
) -> tuple[bytes, str]:
    ctx = get_trial_balance(
        date_from=date_from,
        date_to=date_to,
        exclude_closing=exclude_closing,
    )
    with _erp_session_scope():
        a = _accounts()
        a._apply_db()
        pdf = a._build_trial_balance_pdf(ctx)
    if not pdf:
        raise ValueError("PDF generation is unavailable.")
    stamp = (date_to or date_from or datetime.now().strftime("%Y%m%d")).replace("-", "")[:8]
    return pdf, f"Trial_Balance_{stamp}.pdf"


def get_profit_loss(
    *,
    date_from: str = "",
    date_to: str = "",
    exclude_closing: Any = True,
) -> dict[str, Any]:
    from db import get_profit_and_loss_comparative

    df = _parse_iso_date(date_from)
    dt = _parse_iso_date(date_to)
    excl = _truthy_exclude(exclude_closing)

    with _erp_session_scope():
        a = _accounts()
        a._apply_db()
        report = get_profit_and_loss_comparative(
            date_from=df or None,
            date_to=dt or None,
            exclude_closing=excl,
        )
        dfa = str(report.get("date_from") or df or "")
        dta = str(report.get("date_to") or dt or "")
        return {
            "company_name": _company_name(),
            "period_labels": report.get("period_labels") or ["", "", ""],
            "period_ranges": report.get("period_ranges") or [],
            "revenue_rows": report.get("revenue_rows") or [],
            "expense_rows": report.get("expense_rows") or [],
            "cost_of_sales_rows": report.get("cost_of_sales_rows") or [],
            "operating_expense_rows": report.get("operating_expense_rows") or [],
            "total_revenue": report.get("total_revenue") or [0, 0, 0],
            "total_expense": report.get("total_expense") or [0, 0, 0],
            "total_cost_of_sales": report.get("total_cost_of_sales") or [0, 0, 0],
            "total_operating_expense": report.get("total_operating_expense") or [0, 0, 0],
            "gross_profit": report.get("gross_profit") or [0, 0, 0],
            "net_profit": report.get("net_profit") or [0, 0, 0],
            "date_from": dfa,
            "date_to": dta,
            "date_from_display": _fmt_display(dfa),
            "date_to_display": _fmt_display(dta),
            "exclude_closing": excl,
        }


def build_profit_loss_pdf(
    *,
    date_from: str = "",
    date_to: str = "",
    exclude_closing: Any = True,
    pdf_mode: str = "single",
) -> tuple[bytes, str]:
    ctx = get_profit_loss(
        date_from=date_from,
        date_to=date_to,
        exclude_closing=exclude_closing,
    )
    mode = str(pdf_mode or "single").strip().lower() or "single"
    with _erp_session_scope():
        a = _accounts()
        a._apply_db()
        pdf = a._build_profit_loss_pdf(ctx, mode=mode)
    if not pdf:
        raise ValueError("PDF generation is unavailable.")
    stamp = (date_to or date_from or datetime.now().strftime("%Y%m%d")).replace("-", "")[:8]
    return pdf, f"Profit_and_Loss_{stamp}.pdf"


def get_balance_sheet(*, as_of_date: str = "") -> dict[str, Any]:
    from db import get_balance_sheet_report

    as_of = _parse_iso_date(as_of_date) or datetime.now().strftime("%Y-%m-%d")

    with _erp_session_scope():
        a = _accounts()
        a._apply_db()
        report = get_balance_sheet_report(as_of_date=as_of)

        def _title_rows(rows: Any) -> list[dict[str, Any]]:
            out: list[dict[str, Any]] = []
            for row in rows or []:
                if not isinstance(row, dict):
                    continue
                r = dict(row)
                r["name"] = a._balance_sheet_display_name(r.get("name"))
                out.append(r)
            return out

        total_assets = float(report.get("total_assets") or 0)
        lpe = float(report.get("liabilities_plus_equity") or 0)
        return {
            "company_name": _company_name(),
            "as_of_date": as_of,
            "as_of_date_display": _fmt_display(as_of),
            "asset_accounts": _title_rows(report.get("assets")),
            "liability_accounts": _title_rows(report.get("liabilities")),
            "equity_accounts": _title_rows(report.get("equities")),
            "total_assets": report.get("total_assets") or 0,
            "total_liabilities": report.get("total_liabilities") or 0,
            "total_equity": report.get("total_equity") or 0,
            "liabilities_plus_equity": report.get("liabilities_plus_equity") or 0,
            "difference": round(total_assets - lpe, 2),
        }


def build_balance_sheet_pdf(
    *,
    as_of_date: str = "",
    layout: str = "single",
) -> tuple[bytes, str]:
    ctx = get_balance_sheet(as_of_date=as_of_date)
    with _erp_session_scope():
        a = _accounts()
        a._apply_db()
        pdf = a._build_balance_sheet_pdf(ctx, layout=layout or "single")
    if not pdf:
        raise ValueError("PDF generation is unavailable.")
    stamp = str(ctx.get("as_of_date") or datetime.now().strftime("%Y%m%d")).replace("-", "")[:8]
    return pdf, f"Balance_Sheet_{stamp}.pdf"
