"""Customer / Supplier sub-ledgers — wraps ERP get_*_ledger + PDF builders."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from mobile_backend.services.dashboard_service import _to_float
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


def _norm_code(raw: Any) -> str:
    s = str(raw or "").strip()
    if not s:
        return ""
    try:
        f = float(s)
        if f.is_integer():
            return str(int(f))
    except (TypeError, ValueError):
        pass
    return s


def _default_dates(date_from: str, date_to: str) -> tuple[str, str]:
    df = _parse_iso_date(date_from)
    dt = _parse_iso_date(date_to)
    if not df and not dt:
        df = f"{datetime.now().year}-01-01"
        dt = datetime.now().strftime("%Y-%m-%d")
    elif df and not dt:
        dt = datetime.now().strftime("%Y-%m-%d")
    elif not df and dt:
        df = "2000-01-01"
    if df and dt and df > dt:
        df, dt = dt, df
    return df, dt


def _normalize_line(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "voucher_date": str(row.get("voucher_date") or "")[:10],
        "voucher_no": str(row.get("voucher_no") or "").strip(),
        "reference_no": str(row.get("reference_no") or "").strip(),
        "narration": str(row.get("narration") or "").strip(),
        "source": str(row.get("source") or "").strip(),
        "remarks": str(row.get("remarks") or "").strip(),
        "account_code": str(row.get("account_code") or "").strip(),
        "debit": round(_to_float(row.get("debit")), 2),
        "credit": round(_to_float(row.get("credit")), 2),
        "running_balance": round(_to_float(row.get("running_balance")), 2),
    }


def list_customer_parties(*, search: str = "", limit: int = 80) -> list[dict[str, Any]]:
    from db import get_customers_for_journal_party_select

    lim = max(1, min(int(limit or 80), 200))
    q = (search or "").strip().lower()
    with _erp_session_scope():
        rows = get_customers_for_journal_party_select(limit=20000) or []
        out: list[dict[str, Any]] = []
        for r in rows:
            code = _norm_code(r.get("customercode"))
            name = str(r.get("customername") or "").strip()
            if not code:
                continue
            if q and q not in code.lower() and q not in name.lower():
                continue
            out.append(
                {
                    "party_code": code,
                    "party_name": name or code,
                    "gl_account": _norm_code(r.get("receivableaccount")),
                }
            )
            if len(out) >= lim:
                break
        return out


def list_supplier_parties(*, search: str = "", limit: int = 80) -> list[dict[str, Any]]:
    from db import get_supplier_list

    lim = max(1, min(int(limit or 80), 200))
    q = (search or "").strip()
    with _erp_session_scope():
        rows = get_supplier_list(location_code=None, search=q or None, limit=lim, row_cap=lim * 4) or []
        out: list[dict[str, Any]] = []
        for r in rows:
            code = _norm_code(r.get("suppliercode"))
            name = str(r.get("suppliername") or "").strip()
            if not code:
                continue
            out.append(
                {
                    "party_code": code,
                    "party_name": name or code,
                    "gl_account": _norm_code(r.get("payableaccount")),
                }
            )
            if len(out) >= lim:
                break
        return out


def get_customer_ledger_statement(
    customer_code: str,
    *,
    date_from: str = "",
    date_to: str = "",
) -> dict[str, Any]:
    from db import get_customer_ledger, get_customer_master_by_code

    code = _norm_code(customer_code)
    if not code:
        raise ValueError("Customer code is required.")
    df, dt = _default_dates(date_from, date_to)

    with _erp_session_scope():
        master = get_customer_master_by_code(code) or {}
        name = str(master.get("customername") or master.get("CUSTOMERNAME") or "").strip()
        gl_account = _norm_code(
            master.get("receivableaccount") or master.get("RECEIVABLEACCOUNT")
        )
        ledger = get_customer_ledger(
            code,
            date_from=df or None,
            date_to=dt or None,
            gl_account_code=None,
            asset_accounts_only=True,
        )
        lines = [_normalize_line(dict(ln)) for ln in (ledger.get("lines") or [])]
        return {
            "party_type": "CUSTOMER",
            "party_code": code,
            "party_name": name or code,
            "gl_account": gl_account,
            "date_from": str(ledger.get("date_from") or df or ""),
            "date_to": str(ledger.get("date_to") or dt or ""),
            "opening_balance": round(_to_float(ledger.get("opening_balance")), 2),
            "total_debit": round(_to_float(ledger.get("total_debit")), 2),
            "total_credit": round(_to_float(ledger.get("total_credit")), 2),
            "closing_balance": round(_to_float(ledger.get("closing_balance")), 2),
            "asset_only": bool(ledger.get("asset_only")),
            "lines": lines,
        }


def get_supplier_ledger_statement(
    supplier_code: str,
    *,
    date_from: str = "",
    date_to: str = "",
) -> dict[str, Any]:
    from db import get_supplier_ledger, get_supplier_master_by_code

    code = _norm_code(supplier_code)
    if not code:
        raise ValueError("Supplier code is required.")
    df, dt = _default_dates(date_from, date_to)

    with _erp_session_scope():
        master = get_supplier_master_by_code(code) or {}
        name = str(master.get("suppliername") or master.get("SUPPLIERNAME") or "").strip()
        gl_account = _norm_code(
            master.get("payableaccount") or master.get("PAYABLEACCOUNT")
        )
        ledger = get_supplier_ledger(
            code,
            date_from=df or None,
            date_to=dt or None,
            gl_account_code=None,
            liability_accounts_only=True,
        )
        lines = [_normalize_line(dict(ln)) for ln in (ledger.get("lines") or [])]
        return {
            "party_type": "SUPPLIER",
            "party_code": code,
            "party_name": name or code,
            "gl_account": gl_account,
            "date_from": str(ledger.get("date_from") or df or ""),
            "date_to": str(ledger.get("date_to") or dt or ""),
            "opening_balance": round(_to_float(ledger.get("opening_balance")), 2),
            "total_debit": round(_to_float(ledger.get("total_debit")), 2),
            "total_credit": round(_to_float(ledger.get("total_credit")), 2),
            "closing_balance": round(_to_float(ledger.get("closing_balance")), 2),
            "liability_only": bool(ledger.get("liability_only")),
            "lines": lines,
        }


def build_customer_ledger_pdf(
    customer_code: str,
    *,
    date_from: str = "",
    date_to: str = "",
) -> tuple[bytes, str]:
    from db import get_customer_ledger, get_customer_master_by_code

    code = _norm_code(customer_code)
    if not code:
        raise ValueError("Customer code is required.")
    df, dt = _default_dates(date_from, date_to)

    with _erp_session_scope():
        cust = get_customer_master_by_code(code) or {
            "customercode": code,
            "customername": "—",
            "receivableaccount": "—",
        }
        ledger = get_customer_ledger(
            code,
            date_from=df or None,
            date_to=dt or None,
            gl_account_code=None,
            asset_accounts_only=True,
        )
        pdf_df = str(ledger.get("date_from") or df or "—")
        pdf_dt = str(ledger.get("date_to") or dt or "—")
        pdf_bytes = _accounts()._build_customer_ledger_pdf(cust, ledger, pdf_df, pdf_dt)
        if not pdf_bytes:
            raise ValueError("Failed to generate customer ledger PDF.")
        safe = "".join(c for c in code if c.isalnum() or c in ("-", "_"))[:28] or "customer"
        filename = f"customer_ledger_{safe}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        return pdf_bytes, filename


def build_supplier_ledger_pdf(
    supplier_code: str,
    *,
    date_from: str = "",
    date_to: str = "",
) -> tuple[bytes, str]:
    from db import get_supplier_ledger, get_supplier_master_by_code

    code = _norm_code(supplier_code)
    if not code:
        raise ValueError("Supplier code is required.")
    df, dt = _default_dates(date_from, date_to)

    with _erp_session_scope():
        sup = get_supplier_master_by_code(code) or {
            "suppliercode": code,
            "suppliername": "—",
            "payableaccount": "—",
        }
        ledger = get_supplier_ledger(
            code,
            date_from=df or None,
            date_to=dt or None,
            gl_account_code=None,
            liability_accounts_only=True,
        )
        pdf_df = str(ledger.get("date_from") or df or "—")
        pdf_dt = str(ledger.get("date_to") or dt or "—")
        pdf_bytes = _accounts()._build_supplier_ledger_pdf(sup, ledger, pdf_df, pdf_dt)
        if not pdf_bytes:
            raise ValueError("Failed to generate supplier ledger PDF.")
        safe = "".join(c for c in code if c.isalnum() or c in ("-", "_"))[:28] or "supplier"
        filename = f"supplier_ledger_{safe}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        return pdf_bytes, filename
