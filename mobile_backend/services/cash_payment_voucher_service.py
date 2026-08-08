"""Mobile Cash Payment Voucher — wraps ERP accounts CPV helpers."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from mobile_backend.operation_lock import mobile_operation_lock
from mobile_backend.services.stock_transfer_service import _erp_session_scope


def _accounts():
    from addons.accounts.controllers import routes as accounts

    return accounts


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def _fmt_date(v: Any) -> str:
    if v is None:
        return ""
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d")
    return str(v or "")[:10]


def _acc_scope():
    """ERP accounts session + ensure tables."""
    a = _accounts()
    a._apply_db()
    try:
        from db import ensure_gl_tables

        ensure_gl_tables()
    except Exception:
        pass
    a._cpv_ensure_tables()
    return a


def get_open_context() -> dict[str, Any]:
    with _erp_session_scope() as username:
        a = _acc_scope()
        period = a._accounts_closed_period_context()
        voucher_date = str(period.get("default_voucher_date") or datetime.now().strftime("%Y-%m-%d"))[:10]
        ctx = a._cpv_account_context()
        voucher_no = a._cpv_next_voucher_no(voucher_date)
        return {
            "voucher_no": voucher_no,
            "voucher_date": voucher_date,
            "created_by": username,
            "default_petty_cash": str(ctx.get("default_petty_cash") or "").strip(),
            "default_expense_parent": str(ctx.get("default_expense_parent") or "").strip(),
            "petty_accounts": [
                {
                    "code": str(x.get("code") or "").strip(),
                    "name": str(x.get("name") or "").strip(),
                    "type": str(x.get("type") or "").strip(),
                }
                for x in (ctx.get("petty_accounts") or [])
            ],
            "expense_parent_accounts": [
                {
                    "code": str(x.get("code") or "").strip(),
                    "name": str(x.get("name") or "").strip(),
                }
                for x in (ctx.get("expense_parent_accounts") or [])
            ],
            "closed_periods": period.get("closed_periods") or [],
        }


def list_expense_children(parent_code: str) -> list[dict[str, Any]]:
    parent = str(parent_code or "").strip()
    with _erp_session_scope():
        a = _acc_scope()
        ctx = a._cpv_account_context()
        out: list[dict[str, Any]] = []
        for acc in ctx.get("accounts") or []:
            if (
                str(acc.get("parent_code") or "").strip() == parent
                and acc.get("is_postable")
                and str(acc.get("status") or "ACTIVE").upper() == "ACTIVE"
            ):
                out.append(
                    {
                        "code": str(acc.get("code") or "").strip(),
                        "name": str(acc.get("name") or "").strip(),
                    }
                )
        out.sort(key=lambda r: r["code"])
        return out


def list_vouchers(
    *,
    search: str = "",
    status: str = "all",
    limit: int = 100,
) -> dict[str, Any]:
    with _erp_session_scope():
        a = _acc_scope()
        rows = a._cpv_list_rows(
            search=(search or "").strip(),
            status=(status or "all").strip().lower(),
            limit=max(1, min(int(limit or 100), 500)),
        )
        out: list[dict[str, Any]] = []
        for r in rows or []:
            st = str(r.get("status") or "DRAFT").strip().upper()
            out.append(
                {
                    "voucher_no": str(r.get("voucher_no") or "").strip(),
                    "voucher_date": _fmt_date(r.get("voucher_date")),
                    "petty_cash_account": str(r.get("petty_cash_account") or "").strip(),
                    "reference_no": str(r.get("reference_no") or "").strip(),
                    "narration": str(r.get("narration") or "").strip(),
                    "status": st,
                    "gl_voucher_no": str(r.get("gl_voucher_no") or "").strip(),
                    "total_amount": _to_float(r.get("total_amount")),
                    "line_count": int(r.get("line_count") or 0),
                    "created_by": str(r.get("created_by") or "").strip(),
                    "can_edit": st == "DRAFT",
                    "can_post": st == "DRAFT",
                }
            )
        return {"vouchers": out}


def get_detail(voucher_no: str) -> dict[str, Any] | None:
    with _erp_session_scope():
        a = _acc_scope()
        vno = str(voucher_no or "").strip()
        hdr = a._cpv_get_voucher(vno)
        if not hdr:
            return None
        ctx = a._cpv_account_context()
        by_code = {str(x.get("code") or "").strip(): x for x in (ctx.get("accounts") or [])}
        status = str(hdr.get("status") or "DRAFT").strip().upper()
        lines: list[dict[str, Any]] = []
        total = 0.0
        for ln in hdr.get("lines") or []:
            code = str(ln.get("account_code") or "").strip()
            amt = _to_float(ln.get("amount"))
            total += amt
            acc = by_code.get(code) or {}
            lines.append(
                {
                    "line_no": int(ln.get("line_no") or 0),
                    "account_code": code,
                    "account_name": str(acc.get("name") or "").strip(),
                    "description": str(ln.get("description") or "").strip(),
                    "amount": amt,
                }
            )
        petty = str(hdr.get("petty_cash_account") or "").strip()
        parent = str(hdr.get("expense_parent_account") or "").strip()
        return {
            "voucher_no": str(hdr.get("voucher_no") or "").strip(),
            "voucher_date": _fmt_date(hdr.get("voucher_date")),
            "petty_cash_account": petty,
            "petty_cash_name": str((by_code.get(petty) or {}).get("name") or "").strip(),
            "expense_parent_account": parent,
            "expense_parent_name": str((by_code.get(parent) or {}).get("name") or "").strip(),
            "reference_no": str(hdr.get("reference_no") or "").strip(),
            "narration": str(hdr.get("narration") or "").strip(),
            "status": status,
            "gl_voucher_no": str(hdr.get("gl_voucher_no") or "").strip(),
            "created_by": str(hdr.get("created_by") or "").strip(),
            "posted_by": str(hdr.get("posted_by") or "").strip(),
            "total_amount": round(total, 2),
            "can_edit": status == "DRAFT",
            "can_post": status == "DRAFT",
            "lines": lines,
        }


def _validate_payload(a: Any, payload: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    header = dict(payload.get("header") or payload)
    lines_in = list(payload.get("lines") or [])

    voucher_date = str(header.get("voucher_date") or "")[:10]
    if not voucher_date:
        period = a._accounts_closed_period_context()
        voucher_date = str(period.get("default_voucher_date") or datetime.now().strftime("%Y-%m-%d"))[:10]

    voucher_no = str(header.get("voucher_no") or "").strip()
    if not voucher_no:
        voucher_no = a._cpv_next_voucher_no(voucher_date)
    voucher_no = voucher_no[:30]

    data = {
        "voucher_no": voucher_no,
        "voucher_date": voucher_date,
        "petty_cash_account": str(header.get("petty_cash_account") or "").strip()[:20],
        "expense_parent_account": str(header.get("expense_parent_account") or "").strip()[:20],
        "reference_no": str(header.get("reference_no") or "").strip()[:50],
        "narration": str(header.get("narration") or "").strip()[:1000],
        "attachment_path": str(header.get("attachment_path") or "").strip()[:500],
    }

    lines: list[dict[str, Any]] = []
    for raw in lines_in:
        ln = dict(raw or {})
        code = str(ln.get("account_code") or ln.get("account") or "").strip()[:20]
        desc = str(ln.get("description") or "").strip()[:250]
        amount = _to_float(ln.get("amount"))
        if not code and amount <= 0 and not desc:
            continue
        lines.append(
            {
                "line_no": len(lines) + 1,
                "account_code": code,
                "description": desc,
                "amount": amount,
            }
        )

    errors: list[str] = []
    if not data["petty_cash_account"]:
        errors.append("Petty Cash Account is required.")
    if not data["expense_parent_account"]:
        errors.append("Expense Parent Account is required.")
    if not lines:
        errors.append("At least one expense line is required.")

    period_err = a._accounts_period_closed_error(data.get("voucher_date"))
    if period_err:
        errors.append(period_err)

    account_ctx = a._cpv_account_context()
    account_by_code = {x["code"]: x for x in (account_ctx.get("accounts") or [])}
    expense_children = {
        x["code"]
        for x in (account_ctx.get("accounts") or [])
        if x.get("parent_code") == data["expense_parent_account"]
        and x.get("is_postable")
        and str(x.get("status") or "ACTIVE").upper() == "ACTIVE"
    }
    if data["petty_cash_account"] and data["petty_cash_account"] not in account_by_code:
        errors.append("Selected Petty Cash Account is not in Chart of Accounts.")
    for line in lines:
        if not line["account_code"]:
            errors.append(f"Line {line['line_no']}: Expense Sub Account is required.")
        elif line["account_code"] not in expense_children:
            errors.append(
                f"Line {line['line_no']}: Select only a child account under the selected Expense Parent Account."
            )
        if line["amount"] <= 0:
            errors.append(f"Line {line['line_no']}: Amount must be greater than zero.")

    existing = a._cpv_get_voucher(voucher_no)
    if existing and str(existing.get("status") or "").upper() == "POSTED":
        errors.append("Posted cash payment vouchers cannot be edited.")

    if errors:
        raise ValueError("; ".join(errors))
    return data, lines


def save_draft(payload: dict[str, Any], *, username: str = "mobile") -> dict[str, Any]:
    header = dict(payload.get("header") or payload)
    doc = str(header.get("voucher_no") or "").strip()
    with mobile_operation_lock(
        "cpv",
        doc,
        busy_message="Cash Payment Voucher is already being saved. Please wait.",
    ):
        with _erp_session_scope() as user:
            a = _acc_scope()
            data, lines = _validate_payload(a, payload)
            # ERP helper owns Oracle commit/rollback for this document.
            a._cpv_save_draft_voucher(data, lines, user or username)
            total = round(sum(float(x["amount"] or 0) for x in lines), 2)
            return {
                "voucher_no": data["voucher_no"],
                "status": "DRAFT",
                "total_amount": total,
                "message": f"Cash Payment Voucher saved as draft: {data['voucher_no']}",
            }


def post_voucher(payload: dict[str, Any], *, username: str = "mobile") -> dict[str, Any]:
    header = dict(payload.get("header") or payload)
    doc = str(header.get("voucher_no") or "").strip()
    with mobile_operation_lock(
        "cpv",
        doc,
        lock_seconds=120.0,
        busy_message="Cash Payment Voucher is already being posted. Please wait.",
    ):
        with _erp_session_scope() as user:
            a = _acc_scope()
            data, lines = _validate_payload(a, payload)
            existing = a._cpv_get_voucher(data["voucher_no"])
            if existing and str(existing.get("status") or "").upper() == "POSTED":
                raise ValueError("This cash payment voucher is already posted.")
            # ERP helper posts draft + GL in one Oracle transaction.
            gl_voucher_no = a._cpv_post_voucher(data, lines, user or username)
            total = round(sum(float(x["amount"] or 0) for x in lines), 2)
            return {
                "voucher_no": data["voucher_no"],
                "status": "POSTED",
                "gl_voucher_no": str(gl_voucher_no or "").strip(),
                "total_amount": total,
                "message": f"Cash Payment Voucher posted. GL Voucher No: {gl_voucher_no}",
            }


def build_pdf(voucher_no: str) -> tuple[bytes, str]:
    with _erp_session_scope():
        a = _acc_scope()
        vno = str(voucher_no or "").strip()
        voucher = a._cpv_get_voucher(vno)
        if not voucher:
            raise ValueError("Cash Payment Voucher not found.")
        if str(voucher.get("status") or "").strip().upper() != "POSTED":
            raise ValueError("Cash Payment Voucher PDF is available after posting.")
        from db import get_all_chart_of_accounts

        accounts = get_all_chart_of_accounts() or []
        by_code = {str(x.get("code") or "").strip(): str(x.get("name") or "").strip() for x in accounts}
        vdate = str(voucher.get("voucher_date") or "")[:10]
        display_date = a._pdf_date_mdy(vdate)
        item_lines: list[dict[str, Any]] = []
        total = 0.0
        for line in voucher.get("lines") or []:
            amt = _to_float(line.get("amount"))
            if amt <= 0:
                continue
            total += amt
            item_lines.append(
                {
                    "date": display_date,
                    "description": a._voucher_item_description(line, by_code),
                    "amount": amt,
                }
            )
        petty_code = str(voucher.get("petty_cash_account") or "").strip()
        pdf_bytes = a._build_petty_cash_style_voucher_pdf(
            voucher_no=str(voucher.get("voucher_no") or ""),
            voucher_date=vdate,
            voucher_title="Cash Payment Voucher",
            party_field_label="Particulars",
            party_name=a._voucher_party_from_lines(
                voucher.get("lines") or [], str(voucher.get("narration") or "")
            ),
            item_lines=item_lines,
            total_amount=total,
            created_by=str(voucher.get("created_by") or ""),
            verified_by=str(voucher.get("posted_by") or ""),
            approved_by="",
            debit_account_label="Debit Account",
            debit_account_name=a._voucher_account_summary_from_lines(
                voucher.get("lines") or [], by_code
            ),
            credit_account_label="Credit Account",
            credit_account_name=a._voucher_account_label(petty_code, by_code),
            reference_no=str(voucher.get("reference_no") or ""),
        )
        if not pdf_bytes:
            raise ValueError("PDF generation failed (reportlab not available).")
        safe = "".join(c for c in vno if c.isalnum() or c in ("-", "_"))[:44] or "cash_payment"
        return pdf_bytes, f"CashPayment_{safe}.pdf"
