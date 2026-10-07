"""Accounts Receivable / Payable — wraps ERP GL party balances + open documents + post."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from mobile_backend.database.transaction import oracle_transaction
from mobile_backend.operation_lock import mobile_operation_lock
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


def _fmt_date(raw: Any) -> str:
    if raw is None:
        return ""
    if hasattr(raw, "strftime"):
        try:
            return raw.strftime("%Y-%m-%d")
        except Exception:
            pass
    s = str(raw).strip()
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    return s


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


def _normalize_ar_row(row: dict[str, Any]) -> dict[str, Any]:
    code = _norm_code(row.get("customercode"))
    bal = round(_to_float(row.get("receivable_balance")), 2)
    return {
        "party_code": code,
        "party_name": str(row.get("customername") or "").strip(),
        "location_code": str(row.get("locationcode") or "").strip(),
        "gl_account": _norm_code(row.get("receivableaccount")),
        "balance": bal,
        "balance_source": str(row.get("balance_source") or "").strip(),
        "party_in_gl": bool(str(row.get("party_code_in_gl_dtl") or "").strip()),
    }


def _normalize_ap_row(row: dict[str, Any]) -> dict[str, Any]:
    code = _norm_code(row.get("suppliercode"))
    bal = round(_to_float(row.get("payable_balance")), 2)
    return {
        "party_code": code,
        "party_name": str(row.get("suppliername") or "").strip(),
        "location_code": str(row.get("locationcode") or "").strip(),
        "gl_account": _norm_code(row.get("payableaccount")),
        "balance": bal,
        "balance_source": str(row.get("balance_source") or "").strip(),
        "party_in_gl": bool(str(row.get("party_code_in_gl_dtl") or "").strip()),
    }


def _normalize_open_doc(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "voucher_no": str(row.get("voucher_no") or "").strip(),
        "voucher_date": _fmt_date(row.get("voucher_date")),
        "orderno": str(row.get("orderno") or "").strip(),
        "reference_no": str(row.get("reference_no") or "").strip(),
        "narration": str(row.get("narration") or "").strip(),
        "source": str(row.get("source") or "").strip(),
        "invoice_amount": round(_to_float(row.get("invoice_amount")), 2),
        "allocated_amount": round(_to_float(row.get("allocated_amount")), 2),
        "open_amount": round(_to_float(row.get("open_amount")), 2),
        "is_payable": bool(row.get("is_payable")),
        "is_credit": bool(row.get("is_credit")),
        "balance_hint": str(row.get("balance_hint") or "").strip(),
    }


def _list_totals(rows: list[dict[str, Any]]) -> dict[str, Any]:
    outstanding = round(sum(_to_float(r.get("balance")) for r in rows), 2)
    positive_count = sum(1 for r in rows if _to_float(r.get("balance")) > 0)
    return {
        "count": len(rows),
        "outstanding": outstanding,
        "positive_count": positive_count,
    }


def list_receivables(
    *,
    search: str = "",
    balance: str = "positive",
    date_from: str = "",
    date_to: str = "",
) -> dict[str, Any]:
    """Customer AR balances — same source as ERP Accounts Receivable."""
    df = _parse_iso_date(date_from)
    dt = _parse_iso_date(date_to)
    if df and dt and df > dt:
        df, dt = dt, df
    q = (search or "").strip()
    bf = (balance or "positive").strip().lower() or "positive"

    with _erp_session_scope():
        accounts = _accounts()
        raw = accounts._accounts_receivable_party_tagged_rows(
            date_from=df or None,
            date_to=dt or None,
        )
        filtered = accounts._filter_party_balance_rows(
            raw,
            search=q,
            balance_filter=bf,
            party="customer",
        )
        rows = [_normalize_ar_row(dict(r)) for r in filtered or []]
        rows.sort(key=lambda r: (-abs(_to_float(r.get("balance"))), r.get("party_name") or ""))
        return {
            "rows": rows,
            "totals": _list_totals(rows),
            "filters": {
                "q": q,
                "balance": bf,
                "date_from": df,
                "date_to": dt,
            },
        }


def list_payables(
    *,
    search: str = "",
    balance: str = "positive",
    date_from: str = "",
    date_to: str = "",
) -> dict[str, Any]:
    """Supplier AP balances — same source as ERP Accounts Payable."""
    df = _parse_iso_date(date_from)
    dt = _parse_iso_date(date_to)
    if df and dt and df > dt:
        df, dt = dt, df
    q = (search or "").strip()
    bf = (balance or "positive").strip().lower() or "positive"

    with _erp_session_scope():
        accounts = _accounts()
        raw = accounts._accounts_payable_party_tagged_rows(
            date_from=df or None,
            date_to=dt or None,
        )
        filtered = accounts._filter_party_balance_rows(
            raw,
            search=q,
            balance_filter=bf,
            party="supplier",
        )
        rows = [_normalize_ap_row(dict(r)) for r in filtered or []]
        rows.sort(key=lambda r: (-abs(_to_float(r.get("balance"))), r.get("party_name") or ""))
        return {
            "rows": rows,
            "totals": _list_totals(rows),
            "filters": {
                "q": q,
                "balance": bf,
                "date_from": df,
                "date_to": dt,
            },
        }


def get_receivable_detail(customer_code: str) -> dict[str, Any] | None:
    from db import (
        get_accounts_receivable_summary,
        get_customer_master_by_code,
        get_customer_open_invoices_for_payment,
    )

    code = _norm_code(customer_code)
    if not code:
        raise ValueError("Customer code is required.")

    with _erp_session_scope():
        master = get_customer_master_by_code(code) or {}
        name = str(
            master.get("customername")
            or master.get("CUSTOMERNAME")
            or master.get("name")
            or ""
        ).strip()
        gl_account = _norm_code(
            master.get("receivableaccount") or master.get("RECEIVABLEACCOUNT")
        )
        location = str(master.get("locationcode") or master.get("LOCATIONCODE") or "").strip()

        bal = 0.0
        bal_src = ""
        for row in get_accounts_receivable_summary() or []:
            if _norm_code(row.get("customercode")) == code:
                bal = round(_to_float(row.get("receivable_balance")), 2)
                bal_src = str(row.get("balance_source") or "").strip()
                if not name:
                    name = str(row.get("customername") or "").strip()
                if not gl_account:
                    gl_account = _norm_code(row.get("receivableaccount"))
                if not location:
                    location = str(row.get("locationcode") or "").strip()
                break

        open_docs = [
            _normalize_open_doc(dict(r))
            for r in (get_customer_open_invoices_for_payment(code) or [])
        ]
        open_total = round(
            sum(_to_float(d.get("open_amount")) for d in open_docs if d.get("is_payable")),
            2,
        )
        credit_total = round(
            sum(abs(_to_float(d.get("open_amount"))) for d in open_docs if d.get("is_credit")),
            2,
        )

        if not name and not open_docs and abs(bal) < 0.005:
            return None

        return {
            "party_type": "CUSTOMER",
            "party_code": code,
            "party_name": name or code,
            "location_code": location,
            "gl_account": gl_account,
            "balance": bal,
            "balance_source": bal_src,
            "open_payable_total": open_total,
            "open_credit_total": credit_total,
            "open_documents": open_docs,
        }


def get_payable_detail(supplier_code: str) -> dict[str, Any] | None:
    from db import (
        get_accounts_payable_summary,
        get_supplier_master_by_code,
        get_supplier_open_invoices_for_payment,
    )

    code = _norm_code(supplier_code)
    if not code:
        raise ValueError("Supplier code is required.")

    with _erp_session_scope():
        master = get_supplier_master_by_code(code) or {}
        name = str(
            master.get("suppliername")
            or master.get("SUPPLIERNAME")
            or master.get("name")
            or ""
        ).strip()
        gl_account = _norm_code(
            master.get("payableaccount") or master.get("PAYABLEACCOUNT")
        )
        location = str(master.get("locationcode") or master.get("LOCATIONCODE") or "").strip()

        bal = 0.0
        bal_src = ""
        for row in get_accounts_payable_summary() or []:
            if _norm_code(row.get("suppliercode")) == code:
                bal = round(_to_float(row.get("payable_balance")), 2)
                bal_src = str(row.get("balance_source") or "").strip()
                if not name:
                    name = str(row.get("suppliername") or "").strip()
                if not gl_account:
                    gl_account = _norm_code(row.get("payableaccount"))
                if not location:
                    location = str(row.get("locationcode") or "").strip()
                break

        open_docs = [
            _normalize_open_doc(dict(r))
            for r in (get_supplier_open_invoices_for_payment(code) or [])
        ]
        open_total = round(
            sum(_to_float(d.get("open_amount")) for d in open_docs if d.get("is_payable")),
            2,
        )
        credit_total = round(
            sum(abs(_to_float(d.get("open_amount"))) for d in open_docs if d.get("is_credit")),
            2,
        )

        if not name and not open_docs and abs(bal) < 0.005:
            return None

        return {
            "party_type": "SUPPLIER",
            "party_code": code,
            "party_name": name or code,
            "location_code": location,
            "gl_account": gl_account,
            "balance": bal,
            "balance_source": bal_src,
            "open_payable_total": open_total,
            "open_credit_total": credit_total,
            "open_documents": open_docs,
        }


def list_cash_bank_accounts() -> list[dict[str, Any]]:
    """Cash/Bank postable accounts used on ERP AR/AP receipt forms."""
    with _erp_session_scope():
        rows = _accounts()._cached_cash_bank_accounts() or []
        out: list[dict[str, Any]] = []
        for r in rows:
            code = _norm_code(r.get("code"))
            if not code:
                continue
            name = str(r.get("name") or "").strip()
            out.append(
                {
                    "code": code,
                    "name": name,
                    "label": f"{code} — {name}" if name else code,
                }
            )
        return out


def get_receipt_open_context(customer_code: str) -> dict[str, Any]:
    detail = get_receivable_detail(customer_code)
    if not detail:
        raise ValueError("Customer receivable not found.")
    with _erp_session_scope():
        payment_date = datetime.now().strftime("%Y-%m-%d")
        period_err = _accounts()._accounts_period_closed_error(payment_date)
        if period_err:
            # Prefer next open date hint from ERP context when available.
            try:
                ctx = _accounts()._accounts_closed_period_context(None)
                payment_date = str(ctx.get("payment_date") or payment_date)[:10]
            except Exception:
                pass
    return {
        **detail,
        "cash_bank_accounts": list_cash_bank_accounts(),
        "payment_date": payment_date,
        "kind": "receivable",
    }


def get_payment_open_context(supplier_code: str) -> dict[str, Any]:
    detail = get_payable_detail(supplier_code)
    if not detail:
        raise ValueError("Supplier payable not found.")
    with _erp_session_scope():
        payment_date = datetime.now().strftime("%Y-%m-%d")
        try:
            ctx = _accounts()._accounts_closed_period_context(None)
            payment_date = str(ctx.get("payment_date") or payment_date)[:10]
        except Exception:
            pass
    return {
        **detail,
        "cash_bank_accounts": list_cash_bank_accounts(),
        "payment_date": payment_date,
        "kind": "payable",
    }


def _parse_allocations_payload(
    open_docs_raw: list[dict[str, Any]],
    allocations_in: list[Any],
) -> tuple[list[dict[str, Any]], float, float]:
    from db import parse_open_document_payment_allocations

    vouchers: list[str] = []
    amounts: list[str] = []
    for raw in allocations_in or []:
        if not isinstance(raw, dict):
            continue
        vno = str(raw.get("invoice_voucher_no") or raw.get("voucher_no") or "").strip()
        try:
            amt = round(float(raw.get("allocate_amount") or raw.get("allocated_amount") or 0), 2)
        except (TypeError, ValueError):
            amt = 0.0
        if not vno or amt <= 0:
            continue
        vouchers.append(vno)
        amounts.append(str(amt))

    allocations, invoice_total, credit_total, errors = parse_open_document_payment_allocations(
        open_docs_raw, vouchers, amounts
    )
    if errors:
        raise ValueError(errors[0])
    return allocations, invoice_total, credit_total


def post_receivable_receipt(payload: dict[str, Any], *, username: str) -> dict[str, Any]:
    """Post customer receipt to GL (SOURCE=AR_RECEIPT) — same rules as ERP."""
    from db import (
        DEFAULT_PARTY_ACCOUNTS,
        create_gl_journal_entry,
        ensure_ar_payment_tables,
        ensure_gl_tables,
        get_ar_discount_allowed_account,
        get_chart_of_account_by_code,
        get_customer_master_by_code,
        get_customer_open_invoices_for_payment,
        save_customer_payment_allocations,
    )
    from db import _norm_gl_account_code  # type: ignore

    body = dict(payload or {})
    code = _norm_code(body.get("customer_code") or body.get("party_code"))
    if not code:
        raise ValueError("Customer is required.")

    payment_date = _parse_iso_date(body.get("payment_date")) or datetime.now().strftime("%Y-%m-%d")
    debit_account = str(body.get("cash_bank_account") or body.get("debit_account") or "").strip()
    remarks = str(body.get("remarks") or "").strip()
    reference_no = str(body.get("reference_no") or "").strip()
    try:
        discount_amount = round(max(0.0, float(body.get("discount_amount") or 0)), 2)
    except (TypeError, ValueError):
        discount_amount = 0.0

    with mobile_operation_lock(
        "ar_receipt",
        code,
        lock_seconds=120.0,
        busy_message="Customer receipt is already being posted. Please wait.",
    ), _erp_session_scope() as user:
        accounts = _accounts()
        period_err = accounts._accounts_period_closed_error(payment_date)
        if period_err:
            raise ValueError(period_err)

        cust = get_customer_master_by_code(code) or {}
        receivable_account = _norm_gl_account_code(
            cust.get("receivableaccount")
            or DEFAULT_PARTY_ACCOUNTS.get("customer_receivable")
            or "1200"
        )
        if not receivable_account:
            raise ValueError("Customer receivable account is missing.")

        open_rows = get_customer_open_invoices_for_payment(code) or []
        allocations, invoice_total, credit_total = _parse_allocations_payload(
            open_rows, list(body.get("allocations") or [])
        )
        if invoice_total <= 0 and credit_total <= 0:
            raise ValueError("Select at least one open invoice or customer credit to apply.")
        if credit_total > invoice_total + 0.009:
            raise ValueError("Credits applied cannot exceed total selected on invoices.")

        max_discount = round(max(0.0, invoice_total - credit_total), 2)
        if discount_amount > max_discount + 0.009:
            raise ValueError(
                f"Settlement discount cannot exceed net after credits ({max_discount:.2f})."
            )
        discount_account = get_ar_discount_allowed_account() if discount_amount > 0.009 else ""
        if discount_amount > 0.009 and (
            not discount_account or not get_chart_of_account_by_code(discount_account)
        ):
            raise ValueError(
                "Discount Allowed account is not configured. "
                f"Set AR_DISCOUNT_ALLOWED_ACCOUNT (default "
                f"{DEFAULT_PARTY_ACCOUNTS.get('ar_discount_allowed') or '5010'}) in Chart of Accounts."
            )

        net_cash = round(max(0.0, invoice_total - credit_total - discount_amount), 2)
        if net_cash > 0 and not debit_account:
            raise ValueError("Cash/Bank account is required when net receipt is greater than zero.")
        if net_cash > 0:
            debit_account = _norm_gl_account_code(debit_account)
            if not get_chart_of_account_by_code(debit_account):
                raise ValueError("Selected Cash/Bank account is invalid.")

        # Collected amount must match net cash (ERP rule).
        collected_raw = body.get("collected_amount")
        if collected_raw is None or str(collected_raw).strip() == "":
            collected_amount = net_cash
        else:
            try:
                collected_amount = round(float(collected_raw), 2)
            except (TypeError, ValueError) as exc:
                raise ValueError("Collected Amount is invalid.") from exc
        if collected_amount < 0:
            raise ValueError("Collected Amount cannot be negative.")
        if round(collected_amount, 2) != net_cash:
            raise ValueError(
                f"Collected Amount ({collected_amount:.2f}) must equal Net Cash Receipt ({net_cash:.2f})."
            )

        ensure_gl_tables()
        ensure_ar_payment_tables()
        alloc_note = ""
        if allocations:
            alloc_note = " | Applied: " + ", ".join(
                f"{a['invoice_voucher_no']}:{a['allocated_amount']:.2f}" for a in allocations
            )
        if discount_amount > 0.009:
            alloc_note += f" | Discount: {discount_amount:.2f}"

        party_line = {"party_type": "CUSTOMER", "party_code": str(code)}
        gl_lines: list[dict[str, Any]] = []
        if net_cash > 0:
            gl_lines.append(
                {
                    "account_code": debit_account,
                    "debit": net_cash,
                    "credit": 0,
                    "remarks": f"Customer {code} receipt",
                }
            )
        if discount_amount > 0.009:
            gl_lines.append(
                {
                    "account_code": discount_account,
                    "debit": discount_amount,
                    "credit": 0,
                    "remarks": f"Customer {code} settlement discount",
                }
            )
        if invoice_total > 0:
            gl_lines.append(
                {
                    "account_code": receivable_account,
                    "debit": 0,
                    "credit": invoice_total,
                    "remarks": f"Customer {code} invoices",
                    **party_line,
                }
            )
        if credit_total > 0:
            gl_lines.append(
                {
                    "account_code": receivable_account,
                    "debit": credit_total,
                    "credit": 0,
                    "remarks": f"Customer {code} credits applied",
                    **party_line,
                }
            )

        from db import _get_connection

        with _get_connection() as conn:
            with oracle_transaction(conn):
                voucher_no = create_gl_journal_entry(
                    voucher_date=payment_date,
                    reference_no=reference_no or f"AR-{code}",
                    narration=(remarks or f"Customer receipt {code}") + alloc_note,
                    lines=gl_lines,
                    created_by=str(user or username or ""),
                    source="AR_RECEIPT",
                    conn=conn,
                    commit=False,
                )
                if allocations:
                    save_customer_payment_allocations(
                        payment_voucher_no=voucher_no,
                        customer_code=code,
                        allocations=allocations,
                        created_by=str(user or username or ""),
                        conn=conn,
                        commit=False,
                    )
        return {
            "voucher_no": voucher_no,
            "customer_code": code,
            "net_cash": net_cash,
            "invoice_total": invoice_total,
            "credit_total": credit_total,
            "discount_amount": discount_amount,
            "message": f"Customer receipt posted. Voucher: {voucher_no}",
            "pdf_url": f"/api/v1/accounts/receivables/vouchers/{voucher_no}/pdf",
        }


def post_payable_payment(payload: dict[str, Any], *, username: str) -> dict[str, Any]:
    """Post supplier payment to GL (SOURCE=AP_RECEIPT) — same rules as ERP."""
    from db import (
        DEFAULT_PARTY_ACCOUNTS,
        create_gl_journal_entry,
        ensure_ap_payment_tables,
        ensure_gl_tables,
        get_ap_discount_received_account,
        get_chart_of_account_by_code,
        get_supplier_master_by_code,
        get_supplier_open_invoices_for_payment,
        save_supplier_payment_allocations,
    )
    from db import _norm_gl_account_code  # type: ignore

    body = dict(payload or {})
    code = _norm_code(body.get("supplier_code") or body.get("party_code"))
    if not code:
        raise ValueError("Supplier is required.")

    payment_date = _parse_iso_date(body.get("payment_date")) or datetime.now().strftime("%Y-%m-%d")
    credit_account = str(body.get("cash_bank_account") or body.get("credit_account") or "").strip()
    remarks = str(body.get("remarks") or "").strip()
    reference_no = str(body.get("reference_no") or "").strip()
    try:
        discount_amount = round(max(0.0, float(body.get("discount_amount") or 0)), 2)
    except (TypeError, ValueError):
        discount_amount = 0.0

    with mobile_operation_lock(
        "ap_payment",
        code,
        lock_seconds=120.0,
        busy_message="Supplier payment is already being posted. Please wait.",
    ), _erp_session_scope() as user:
        accounts = _accounts()
        period_err = accounts._accounts_period_closed_error(payment_date)
        if period_err:
            raise ValueError(period_err)

        supplier = get_supplier_master_by_code(code) or {}
        payable_account = _norm_gl_account_code(supplier.get("payableaccount"))
        if not payable_account:
            raise ValueError("Supplier payable account is missing.")

        open_rows = get_supplier_open_invoices_for_payment(code) or []
        allocations, invoice_total, credit_total = _parse_allocations_payload(
            open_rows, list(body.get("allocations") or [])
        )
        if invoice_total <= 0 and credit_total <= 0:
            raise ValueError("Select at least one open invoice or supplier credit to apply.")
        if credit_total > invoice_total + 0.009:
            raise ValueError("Credits applied cannot exceed total selected on invoices.")

        max_discount = round(max(0.0, invoice_total - credit_total), 2)
        if discount_amount > max_discount + 0.009:
            raise ValueError(
                f"Settlement discount cannot exceed net after credits ({max_discount:.2f})."
            )
        discount_account = get_ap_discount_received_account() if discount_amount > 0.009 else ""
        if discount_amount > 0.009 and (
            not discount_account or not get_chart_of_account_by_code(discount_account)
        ):
            raise ValueError(
                "Discount Received account is not configured. "
                f"Set AP_DISCOUNT_RECEIVED_ACCOUNT (default "
                f"{DEFAULT_PARTY_ACCOUNTS.get('ap_discount_received') or '4010'}) in Chart of Accounts."
            )

        net_cash = round(max(0.0, invoice_total - credit_total - discount_amount), 2)
        if net_cash > 0 and not credit_account:
            raise ValueError("Cash/Bank account is required when net payment is greater than zero.")
        if net_cash > 0:
            credit_account = _norm_gl_account_code(credit_account)
            if not get_chart_of_account_by_code(credit_account):
                raise ValueError("Selected Cash/Bank account is invalid.")

        amount_raw = body.get("amount")
        if amount_raw is None or str(amount_raw).strip() == "":
            amount = net_cash
        else:
            try:
                amount = round(float(amount_raw), 2)
            except (TypeError, ValueError) as exc:
                raise ValueError("Payment amount is invalid.") from exc
        if round(amount, 2) != net_cash:
            raise ValueError(
                f"Payment amount must equal net cash after credits and discount ({net_cash:.2f})."
            )

        ensure_gl_tables()
        ensure_ap_payment_tables()
        alloc_note = ""
        if allocations:
            alloc_note = " | Applied: " + ", ".join(
                f"{a['invoice_voucher_no']}:{a['allocated_amount']:.2f}" for a in allocations
            )
        if discount_amount > 0.009:
            alloc_note += f" | Discount: {discount_amount:.2f}"

        party_line = {"party_type": "SUPPLIER", "party_code": str(code)}
        gl_lines: list[dict[str, Any]] = []
        if invoice_total > 0:
            gl_lines.append(
                {
                    "account_code": payable_account,
                    "debit": invoice_total,
                    "credit": 0,
                    "remarks": f"Supplier {code} invoices",
                    **party_line,
                }
            )
        if credit_total > 0:
            gl_lines.append(
                {
                    "account_code": payable_account,
                    "debit": 0,
                    "credit": credit_total,
                    "remarks": f"Supplier {code} credits applied",
                    **party_line,
                }
            )
        if discount_amount > 0.009:
            gl_lines.append(
                {
                    "account_code": discount_account,
                    "debit": 0,
                    "credit": discount_amount,
                    "remarks": f"Supplier {code} settlement discount",
                }
            )
        if net_cash > 0:
            gl_lines.append(
                {
                    "account_code": credit_account,
                    "debit": 0,
                    "credit": net_cash,
                    "remarks": f"Supplier {code} payment",
                }
            )

        from db import _get_connection

        with _get_connection() as conn:
            with oracle_transaction(conn):
                voucher_no = create_gl_journal_entry(
                    voucher_date=payment_date,
                    reference_no=reference_no or f"AP-{code}",
                    narration=(remarks or f"Supplier payment {code}") + alloc_note,
                    lines=gl_lines,
                    created_by=str(user or username or ""),
                    source="AP_RECEIPT",
                    conn=conn,
                    commit=False,
                )
                if allocations:
                    save_supplier_payment_allocations(
                        payment_voucher_no=voucher_no,
                        supplier_code=code,
                        allocations=allocations,
                        created_by=str(user or username or ""),
                        conn=conn,
                        commit=False,
                    )
        return {
            "voucher_no": voucher_no,
            "supplier_code": code,
            "net_cash": net_cash,
            "invoice_total": invoice_total,
            "credit_total": credit_total,
            "discount_amount": discount_amount,
            "message": f"Supplier payment posted. Voucher: {voucher_no}",
            "pdf_url": f"/api/v1/accounts/payables/vouchers/{voucher_no}/pdf",
        }


def build_receivable_receipt_pdf(voucher_no: str) -> tuple[bytes, str]:
    """ERP customer receipt voucher PDF (SOURCE=AR_RECEIPT)."""
    from datetime import datetime as _dt

    from db import (
        ensure_gl_tables,
        get_ar_payment_allocations_by_payment_voucher,
        get_customer_master_by_code,
        get_gl_voucher_detail,
    )

    vno = str(voucher_no or "").strip()
    if not vno:
        raise ValueError("Voucher number is required.")

    with _erp_session_scope():
        try:
            ensure_gl_tables()
        except Exception:
            pass
        detail = get_gl_voucher_detail(vno)
        if not detail:
            raise ValueError("Voucher not found.")
        if str(detail.get("source") or "").strip().upper() != "AR_RECEIPT":
            raise ValueError("Not a customer receipt voucher.")
        customer_code = ""
        for ln in detail.get("lines") or []:
            if str(ln.get("party_type") or "").strip().upper() == "CUSTOMER":
                customer_code = str(ln.get("party_code") or "").strip()
                break
        customer_label = customer_code or "—"
        if customer_code:
            cm = get_customer_master_by_code(customer_code) or {}
            nm = str(cm.get("customername") or "").strip()
            if nm:
                customer_label = f"{customer_code} — {nm}"
        alloc_rows = get_ar_payment_allocations_by_payment_voucher(
            vno, customer_code=customer_code
        )
        pdf_bytes = _accounts()._build_supplier_payment_voucher_pdf(
            detail,
            supplier_label=customer_label,
            allocations=alloc_rows or [],
            voucher_title="CUSTOMER RECEIPT VOUCHER",
            party_field_label="Customer",
        )
        if not pdf_bytes:
            raise ValueError("PDF generation failed (reportlab not available).")
        safe = "".join(c for c in vno if c.isalnum() or c in ("-", "_"))[:44] or "receipt"
        filename = f"customer_receipt_{safe}_{_dt.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        return pdf_bytes, filename


def build_payable_payment_pdf(voucher_no: str) -> tuple[bytes, str]:
    """ERP supplier payment voucher PDF (SOURCE=AP_RECEIPT)."""
    from datetime import datetime as _dt

    from db import (
        ensure_gl_tables,
        get_ap_payment_allocations_by_payment_voucher,
        get_gl_voucher_detail,
        get_supplier_master_by_code,
    )

    vno = str(voucher_no or "").strip()
    if not vno:
        raise ValueError("Voucher number is required.")

    with _erp_session_scope():
        try:
            ensure_gl_tables()
        except Exception:
            pass
        detail = get_gl_voucher_detail(vno)
        if not detail:
            raise ValueError("Voucher not found.")
        if str(detail.get("source") or "").strip().upper() != "AP_RECEIPT":
            raise ValueError("Not a supplier payment voucher.")
        supplier_code = ""
        for ln in detail.get("lines") or []:
            if str(ln.get("party_type") or "").strip().upper() == "SUPPLIER":
                supplier_code = str(ln.get("party_code") or "").strip()
                break
        supplier_label = supplier_code or "—"
        if supplier_code:
            sm = get_supplier_master_by_code(supplier_code) or {}
            nm = str(sm.get("suppliername") or "").strip()
            if nm:
                supplier_label = f"{supplier_code} — {nm}"
        alloc_rows = get_ap_payment_allocations_by_payment_voucher(
            vno, supplier_code=supplier_code
        )
        pdf_bytes = _accounts()._build_supplier_payment_voucher_pdf(
            detail,
            supplier_label=supplier_label,
            allocations=alloc_rows or [],
        )
        if not pdf_bytes:
            raise ValueError("PDF generation failed (reportlab not available).")
        safe = "".join(c for c in vno if c.isalnum() or c in ("-", "_"))[:44] or "payment"
        filename = f"supplier_payment_{safe}_{_dt.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        return pdf_bytes, filename
