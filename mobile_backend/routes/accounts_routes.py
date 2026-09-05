from typing import Any

from fastapi import APIRouter, Body, Depends, Query, Request
from fastapi.responses import Response

from mobile_backend.deps_auth import require_access_claims, require_any_permission
from mobile_backend.deps_save import require_save_nonce, success_after_mutation
from mobile_backend.mutation_errors import failure_from_mutation_exc
from mobile_backend.request_context import get_jwt
from mobile_backend.services import ar_ap_service
from mobile_backend.services import cash_payment_voucher_service as cpv
from mobile_backend.services import financial_statements_service as fs
from mobile_backend.services import journal_entry_service as je
from mobile_backend.services import party_ledger_service
from mobile_backend.services import pos_settlement_service as pss
from mobile_backend.utils.response import failure, success

router = APIRouter(
    prefix="/api/v1/accounts",
    tags=["accounts"],
    dependencies=[Depends(require_access_claims)],
)

_cpv_perm = Depends(
    require_any_permission(
        "accounts.cash_payment_voucher",
        "accounts.cash_payment_voucher_list",
        "mobile.cash_payment_voucher",
        "mobile.accounts",
    )
)

_tb_perm = Depends(
    require_any_permission(
        "accounts.trial_balance",
        "mobile.trial_balance",
        "mobile.accounts",
    )
)
_pl_perm = Depends(
    require_any_permission(
        "accounts.profit_loss",
        "mobile.profit_loss",
        "mobile.accounts",
    )
)
_bs_perm = Depends(
    require_any_permission(
        "accounts.balance_sheet",
        "mobile.balance_sheet",
        "mobile.accounts",
    )
)
_ar_perm = Depends(
    require_any_permission(
        "accounts.accounts_receivable",
        "mobile.accounts_receivable",
        "mobile.accounts",
    )
)
_ap_perm = Depends(
    require_any_permission(
        "accounts.accounts_payable",
        "mobile.accounts_payable",
        "mobile.accounts",
    )
)
_cust_ledger_perm = Depends(
    require_any_permission(
        "accounts.customer_ledger_page",
        "accounts.customer_ledger",
        "mobile.customer_ledger",
        "mobile.accounts",
    )
)
_supp_ledger_perm = Depends(
    require_any_permission(
        "accounts.supplier_ledger_page",
        "accounts.supplier_ledger",
        "mobile.supplier_ledger",
        "mobile.accounts",
    )
)
_je_perm = Depends(
    require_any_permission(
        "accounts.journal_entry",
        "mobile.journal_entry",
        "mobile.accounts",
    )
)
_pos_settlement_perm = Depends(
    require_any_permission(
        "pos_billing.pos_settlement_posting_page",
        "pos_billing.pos_settlement_posting_workflow_page",
        "mobile.pos_settlement",
        "mobile.accounts",
    )
)


def _username() -> str:
    claims = get_jwt()
    return str(claims.get("sub") or "mobile").strip() or "mobile"


@router.get("/cash-payment-vouchers/open", dependencies=[_cpv_perm])
def cpv_open():
    return success(cpv.get_open_context())


@router.get("/cash-payment-vouchers/expense-children", dependencies=[_cpv_perm])
def cpv_expense_children(parent_code: str = Query(..., min_length=1)):
    return success({"accounts": cpv.list_expense_children(parent_code)})


@router.post(
    "/cash-payment-vouchers/expense-sub-accounts",
    dependencies=[_cpv_perm, require_save_nonce],
)
def cpv_create_expense_sub_account(request: Request, payload: dict[str, Any] = Body(default_factory=dict)):
    """Create a postable expense sub-account under a parent (Chart of Accounts)."""
    try:
        data = cpv.create_expense_sub_account(payload)
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to create expense sub-account.")
    return success_after_mutation(
        request,
        data,
        message=data.get("message") or "Expense sub-account created",
        status_code=201,
    )


@router.get("/cash-payment-vouchers", dependencies=[_cpv_perm])
def cpv_list(
    q: str = Query(""),
    status: str = Query("all"),
    limit: int = Query(100, ge=1, le=500),
):
    return success(cpv.list_vouchers(search=q, status=status, limit=limit))


@router.post("/cash-payment-vouchers/save", dependencies=[_cpv_perm, require_save_nonce])
def cpv_save(request: Request, payload: dict[str, Any] = Body(default_factory=dict)):
    try:
        data = cpv.save_draft(payload, username=_username())
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to save cash payment voucher.")
    return success_after_mutation(
        request,
        data,
        message=data.get("message") or "Cash Payment Voucher saved",
    )


@router.post("/cash-payment-vouchers/post", dependencies=[_cpv_perm, require_save_nonce])
def cpv_post(request: Request, payload: dict[str, Any] = Body(default_factory=dict)):
    try:
        data = cpv.post_voucher(payload, username=_username())
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to post cash payment voucher.")
    return success_after_mutation(
        request,
        data,
        message=data.get("message") or "Cash Payment Voucher posted",
    )


@router.get("/cash-payment-vouchers/{voucher_no}/pdf", dependencies=[_cpv_perm])
def cpv_pdf(voucher_no: str):
    try:
        pdf_bytes, filename = cpv.build_pdf(voucher_no)
    except ValueError as exc:
        return failure(str(exc), status_code=400)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/cash-payment-vouchers/{voucher_no:path}", dependencies=[_cpv_perm])
def cpv_detail(voucher_no: str):
    data = cpv.get_detail(voucher_no)
    if not data:
        return failure("Cash Payment Voucher not found.", status_code=404)
    return success(data)


@router.get("/journals/open", dependencies=[_je_perm])
def journal_open():
    try:
        return success(je.get_open_context())
    except Exception as exc:
        return failure(str(exc) or "Failed to load journal context.", status_code=400)


@router.get("/journals/accounts", dependencies=[_je_perm])
def journal_accounts(
    q: str = Query(""),
    limit: int = Query(200, ge=1, le=500),
):
    try:
        rows = je.list_accounts(q=q, limit=limit)
    except Exception as exc:
        return failure(str(exc) or "Failed to list accounts.", status_code=400)
    return success({"accounts": rows})


@router.get("/journals/parties/customers", dependencies=[_je_perm])
def journal_customers(
    q: str = Query(""),
    limit: int = Query(80, ge=1, le=200),
):
    try:
        rows = je.list_customers(q=q, limit=limit)
    except Exception as exc:
        return failure(str(exc) or "Failed to list customers.", status_code=400)
    return success({"parties": rows})


@router.get("/journals/parties/suppliers", dependencies=[_je_perm])
def journal_suppliers(
    q: str = Query(""),
    limit: int = Query(80, ge=1, le=200),
):
    try:
        rows = je.list_suppliers(q=q, limit=limit)
    except Exception as exc:
        return failure(str(exc) or "Failed to list suppliers.", status_code=400)
    return success({"parties": rows})


@router.get("/journals", dependencies=[_je_perm])
def journal_list(
    q: str = Query(""),
    status: str = Query("all"),
    source: str = Query("all"),
    date_from: str = Query(""),
    date_to: str = Query(""),
    limit: int = Query(100, ge=1, le=500),
):
    try:
        data = je.list_journals(
            search=q,
            status=status,
            source=source,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
        )
    except Exception as exc:
        return failure(str(exc) or "Failed to list journals.", status_code=400)
    return success(data)


@router.post("/journals/draft", dependencies=[_je_perm, require_save_nonce])
def journal_save_draft(request: Request, payload: dict[str, Any] = Body(default_factory=dict)):
    try:
        data = je.save_draft(payload, username=_username())
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to save journal draft.")
    return success_after_mutation(
        request,
        data,
        message=data.get("message") or "Journal draft saved",
    )


@router.post("/journals/post", dependencies=[_je_perm, require_save_nonce])
def journal_post(request: Request, payload: dict[str, Any] = Body(default_factory=dict)):
    try:
        data = je.post_journal(payload, username=_username())
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to post journal.")
    return success_after_mutation(
        request,
        data,
        message=data.get("message") or "Journal posted",
    )


@router.post("/journals/{voucher_no:path}/reverse", dependencies=[_je_perm, require_save_nonce])
def journal_reverse(
    request: Request,
    voucher_no: str,
    payload: dict[str, Any] = Body(default_factory=dict),
):
    body = dict(payload or {})
    try:
        data = je.reverse_journal(
            voucher_no,
            voucher_date=str(body.get("voucher_date") or ""),
            remarks=str(body.get("remarks") or ""),
            username=_username(),
        )
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to reverse journal.")
    return success_after_mutation(
        request,
        data,
        message=data.get("message") or "Journal reversed",
    )


@router.get("/journals/{voucher_no:path}/pdf", dependencies=[_je_perm])
def journal_pdf(voucher_no: str):
    try:
        pdf_bytes, filename = je.build_pdf(voucher_no)
    except ValueError as exc:
        return failure(str(exc), status_code=400)
    except Exception as exc:
        return failure(str(exc) or "Failed to build journal PDF.", status_code=400)
    return _pdf_response(pdf_bytes, filename)


@router.get("/journals/{voucher_no:path}", dependencies=[_je_perm])
def journal_detail(voucher_no: str):
    try:
        data = je.get_detail(voucher_no)
    except Exception as exc:
        return failure(str(exc) or "Failed to load journal.", status_code=400)
    if not data:
        return failure("Journal entry not found.", status_code=404)
    return success(data)


def _pdf_response(pdf_bytes: bytes, filename: str) -> Response:
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/trial-balance", dependencies=[_tb_perm])
def trial_balance(
    date_from: str = Query(""),
    date_to: str = Query(""),
    exclude_closing: bool = Query(True),
):
    try:
        data = fs.get_trial_balance(
            date_from=date_from,
            date_to=date_to,
            exclude_closing=exclude_closing,
        )
    except Exception as exc:
        return failure(str(exc) or "Failed to load trial balance.", status_code=400)
    return success(data)


@router.get("/trial-balance/pdf", dependencies=[_tb_perm])
def trial_balance_pdf(
    date_from: str = Query(""),
    date_to: str = Query(""),
    exclude_closing: bool = Query(True),
):
    try:
        pdf_bytes, filename = fs.build_trial_balance_pdf(
            date_from=date_from,
            date_to=date_to,
            exclude_closing=exclude_closing,
        )
    except Exception as exc:
        return failure(str(exc) or "Failed to build trial balance PDF.", status_code=400)
    return _pdf_response(pdf_bytes, filename)


@router.get("/profit-loss", dependencies=[_pl_perm])
def profit_loss(
    date_from: str = Query(""),
    date_to: str = Query(""),
    exclude_closing: bool = Query(True),
):
    try:
        data = fs.get_profit_loss(
            date_from=date_from,
            date_to=date_to,
            exclude_closing=exclude_closing,
        )
    except Exception as exc:
        return failure(str(exc) or "Failed to load profit & loss.", status_code=400)
    return success(data)


@router.get("/profit-loss/pdf", dependencies=[_pl_perm])
def profit_loss_pdf(
    date_from: str = Query(""),
    date_to: str = Query(""),
    exclude_closing: bool = Query(True),
    pdf_mode: str = Query("single"),
):
    try:
        pdf_bytes, filename = fs.build_profit_loss_pdf(
            date_from=date_from,
            date_to=date_to,
            exclude_closing=exclude_closing,
            pdf_mode=pdf_mode,
        )
    except Exception as exc:
        return failure(str(exc) or "Failed to build profit & loss PDF.", status_code=400)
    return _pdf_response(pdf_bytes, filename)


@router.get("/balance-sheet", dependencies=[_bs_perm])
def balance_sheet(as_of_date: str = Query("")):
    try:
        data = fs.get_balance_sheet(as_of_date=as_of_date)
    except Exception as exc:
        return failure(str(exc) or "Failed to load balance sheet.", status_code=400)
    return success(data)


@router.get("/balance-sheet/pdf", dependencies=[_bs_perm])
def balance_sheet_pdf(
    as_of_date: str = Query(""),
    layout: str = Query("single"),
):
    try:
        pdf_bytes, filename = fs.build_balance_sheet_pdf(
            as_of_date=as_of_date,
            layout=layout,
        )
    except Exception as exc:
        return failure(str(exc) or "Failed to build balance sheet PDF.", status_code=400)
    return _pdf_response(pdf_bytes, filename)


@router.get("/receivables", dependencies=[_ar_perm])
def accounts_receivables_list(
    q: str = Query(""),
    balance: str = Query("positive"),
    date_from: str = Query(""),
    date_to: str = Query(""),
):
    """ERP Accounts Receivable — customer GL party balances."""
    try:
        data = ar_ap_service.list_receivables(
            search=q,
            balance=balance,
            date_from=date_from,
            date_to=date_to,
        )
    except Exception as exc:
        return failure(str(exc) or "Failed to load receivables.", status_code=400)
    return success(data)


@router.get("/receivables/{customer_code}/receipt-open", dependencies=[_ar_perm])
def accounts_receivable_receipt_open(customer_code: str):
    try:
        data = ar_ap_service.get_receipt_open_context(customer_code)
    except ValueError as exc:
        return failure(str(exc), status_code=404)
    except Exception as exc:
        return failure(str(exc) or "Failed to open customer receipt.", status_code=400)
    return success(data)


@router.post(
    "/receivables/{customer_code}/receipts",
    dependencies=[_ar_perm, require_save_nonce],
)
def accounts_receivable_receipt_post(
    request: Request,
    customer_code: str,
    payload: dict[str, Any] = Body(default_factory=dict),
):
    body = dict(payload or {})
    body.setdefault("customer_code", customer_code)
    try:
        data = ar_ap_service.post_receivable_receipt(body, username=_username())
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to post customer receipt.")
    return success_after_mutation(
        request,
        data,
        message=data.get("message") or "Customer receipt posted",
    )


@router.get("/receivables/vouchers/{voucher_no:path}/pdf", dependencies=[_ar_perm])
def accounts_receivable_voucher_pdf(voucher_no: str):
    try:
        pdf_bytes, filename = ar_ap_service.build_receivable_receipt_pdf(voucher_no)
    except ValueError as exc:
        return failure(str(exc), status_code=404)
    except Exception as exc:
        return failure(str(exc) or "Failed to build receipt PDF.", status_code=400)
    return _pdf_response(pdf_bytes, filename)


@router.get("/receivables/{customer_code}", dependencies=[_ar_perm])
def accounts_receivable_detail(customer_code: str):
    try:
        data = ar_ap_service.get_receivable_detail(customer_code)
    except ValueError as exc:
        return failure(str(exc), status_code=400)
    except Exception as exc:
        return failure(str(exc) or "Failed to load receivable detail.", status_code=400)
    if not data:
        return failure("Customer receivable not found.", status_code=404)
    return success(data)


@router.get("/payables", dependencies=[_ap_perm])
def accounts_payables_list(
    q: str = Query(""),
    balance: str = Query("positive"),
    date_from: str = Query(""),
    date_to: str = Query(""),
):
    """ERP Accounts Payable — supplier GL party balances."""
    try:
        data = ar_ap_service.list_payables(
            search=q,
            balance=balance,
            date_from=date_from,
            date_to=date_to,
        )
    except Exception as exc:
        return failure(str(exc) or "Failed to load payables.", status_code=400)
    return success(data)


@router.get("/payables/{supplier_code}/payment-open", dependencies=[_ap_perm])
def accounts_payable_payment_open(supplier_code: str):
    try:
        data = ar_ap_service.get_payment_open_context(supplier_code)
    except ValueError as exc:
        return failure(str(exc), status_code=404)
    except Exception as exc:
        return failure(str(exc) or "Failed to open supplier payment.", status_code=400)
    return success(data)


@router.post(
    "/payables/{supplier_code}/payments",
    dependencies=[_ap_perm, require_save_nonce],
)
def accounts_payable_payment_post(
    request: Request,
    supplier_code: str,
    payload: dict[str, Any] = Body(default_factory=dict),
):
    body = dict(payload or {})
    body.setdefault("supplier_code", supplier_code)
    try:
        data = ar_ap_service.post_payable_payment(body, username=_username())
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to post supplier payment.")
    return success_after_mutation(
        request,
        data,
        message=data.get("message") or "Supplier payment posted",
    )


@router.get("/payables/vouchers/{voucher_no:path}/pdf", dependencies=[_ap_perm])
def accounts_payable_voucher_pdf(voucher_no: str):
    try:
        pdf_bytes, filename = ar_ap_service.build_payable_payment_pdf(voucher_no)
    except ValueError as exc:
        return failure(str(exc), status_code=404)
    except Exception as exc:
        return failure(str(exc) or "Failed to build payment PDF.", status_code=400)
    return _pdf_response(pdf_bytes, filename)


@router.get("/payables/{supplier_code}", dependencies=[_ap_perm])
def accounts_payable_detail(supplier_code: str):
    try:
        data = ar_ap_service.get_payable_detail(supplier_code)
    except ValueError as exc:
        return failure(str(exc), status_code=400)
    except Exception as exc:
        return failure(str(exc) or "Failed to load payable detail.", status_code=400)
    if not data:
        return failure("Supplier payable not found.", status_code=404)
    return success(data)


@router.get("/customer-ledger/parties", dependencies=[_cust_ledger_perm])
def customer_ledger_parties(
    q: str = Query(""),
    limit: int = Query(80, ge=1, le=200),
):
    try:
        rows = party_ledger_service.list_customer_parties(search=q, limit=limit)
    except Exception as exc:
        return failure(str(exc) or "Failed to list customers.", status_code=400)
    return success({"parties": rows})


@router.get("/customer-ledger/{customer_code}/pdf", dependencies=[_cust_ledger_perm])
def customer_ledger_pdf(
    customer_code: str,
    date_from: str = Query(""),
    date_to: str = Query(""),
):
    try:
        pdf_bytes, filename = party_ledger_service.build_customer_ledger_pdf(
            customer_code, date_from=date_from, date_to=date_to
        )
    except ValueError as exc:
        return failure(str(exc), status_code=400)
    except Exception as exc:
        return failure(str(exc) or "Failed to build customer ledger PDF.", status_code=400)
    return _pdf_response(pdf_bytes, filename)


@router.get("/customer-ledger/{customer_code}", dependencies=[_cust_ledger_perm])
def customer_ledger_statement(
    customer_code: str,
    date_from: str = Query(""),
    date_to: str = Query(""),
):
    try:
        data = party_ledger_service.get_customer_ledger_statement(
            customer_code, date_from=date_from, date_to=date_to
        )
    except ValueError as exc:
        return failure(str(exc), status_code=400)
    except Exception as exc:
        return failure(str(exc) or "Failed to load customer ledger.", status_code=400)
    return success(data)


@router.get("/supplier-ledger/parties", dependencies=[_supp_ledger_perm])
def supplier_ledger_parties(
    q: str = Query(""),
    limit: int = Query(80, ge=1, le=200),
):
    try:
        rows = party_ledger_service.list_supplier_parties(search=q, limit=limit)
    except Exception as exc:
        return failure(str(exc) or "Failed to list suppliers.", status_code=400)
    return success({"parties": rows})


@router.get("/supplier-ledger/{supplier_code}/pdf", dependencies=[_supp_ledger_perm])
def supplier_ledger_pdf(
    supplier_code: str,
    date_from: str = Query(""),
    date_to: str = Query(""),
):
    try:
        pdf_bytes, filename = party_ledger_service.build_supplier_ledger_pdf(
            supplier_code, date_from=date_from, date_to=date_to
        )
    except ValueError as exc:
        return failure(str(exc), status_code=400)
    except Exception as exc:
        return failure(str(exc) or "Failed to build supplier ledger PDF.", status_code=400)
    return _pdf_response(pdf_bytes, filename)


@router.get("/supplier-ledger/{supplier_code}", dependencies=[_supp_ledger_perm])
def supplier_ledger_statement(
    supplier_code: str,
    date_from: str = Query(""),
    date_to: str = Query(""),
):
    try:
        data = party_ledger_service.get_supplier_ledger_statement(
            supplier_code, date_from=date_from, date_to=date_to
        )
    except ValueError as exc:
        return failure(str(exc), status_code=400)
    except Exception as exc:
        return failure(str(exc) or "Failed to load supplier ledger.", status_code=400)
    return success(data)


# ---- POS Settlement (ERP POS Settlement Posting) ----


@router.get("/pos-settlements/open", dependencies=[_pos_settlement_perm])
def pos_settlement_open():
    try:
        return success(pss.get_open_context())
    except Exception as exc:
        return failure(str(exc) or "Failed to open POS settlement.", status_code=400)


@router.get("/pos-settlements/pending-by-date", dependencies=[_pos_settlement_perm])
def pos_settlement_pending_by_date(limit: int = Query(90, ge=1, le=366)):
    try:
        return success(pss.list_pending_by_date(limit=limit))
    except Exception as exc:
        return failure(str(exc) or "Failed to list pending settlements.", status_code=400)


@router.get("/pos-settlements/drafts", dependencies=[_pos_settlement_perm])
def pos_settlement_drafts(limit: int = Query(40, ge=1, le=200)):
    try:
        return success(pss.list_drafts(limit=limit))
    except Exception as exc:
        return failure(str(exc) or "Failed to list settlement drafts.", status_code=400)


@router.get("/pos-settlements/bills", dependencies=[_pos_settlement_perm])
def pos_settlement_bills(
    from_date: str = Query("", alias="from"),
    to_date: str = Query("", alias="to"),
    settlement_scope: str = Query("pending"),
    limit: int = Query(500, ge=1, le=500),
):
    try:
        return success(
            pss.list_bills(
                from_date=from_date,
                to_date=to_date,
                settlement_scope=settlement_scope,
                limit=limit,
            )
        )
    except Exception as exc:
        return failure(str(exc) or "Failed to list settlement bills.", status_code=400)


@router.post("/pos-settlements/payment-mode-summary", dependencies=[_pos_settlement_perm])
def pos_settlement_payment_mode_summary(payload: dict[str, Any] = Body(default_factory=dict)):
    try:
        bill_nos = payload.get("bill_nos") if isinstance(payload.get("bill_nos"), list) else []
        return success(pss.payment_mode_summary(bill_nos))
    except Exception as exc:
        return failure(str(exc) or "Failed to compute payment summary.", status_code=400)


@router.get("/pos-settlements/drafts/{draft_id}", dependencies=[_pos_settlement_perm])
def pos_settlement_draft_get(draft_id: int):
    try:
        return success(pss.get_draft(draft_id))
    except Exception as exc:
        return failure(str(exc) or "Failed to load settlement draft.", status_code=400)


@router.post("/pos-settlements/drafts/generate", dependencies=[_pos_settlement_perm, require_save_nonce])
def pos_settlement_draft_generate(request: Request, payload: dict[str, Any] = Body(default_factory=dict)):
    try:
        data = pss.generate_draft(payload, username=_username())
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to create settlement draft.")
    return success_after_mutation(
        request,
        data,
        message=data.get("message") or "Settlement draft created",
        status_code=201,
    )


@router.post("/pos-settlements/drafts/{draft_id}/verify", dependencies=[_pos_settlement_perm, require_save_nonce])
def pos_settlement_draft_verify(request: Request, draft_id: int):
    try:
        data = pss.verify_draft(draft_id)
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to verify settlement.")
    return success_after_mutation(request, data, message=data.get("message") or "Settlement verified")


@router.post("/pos-settlements/drafts/{draft_id}/cancel", dependencies=[_pos_settlement_perm, require_save_nonce])
def pos_settlement_draft_cancel(request: Request, draft_id: int):
    try:
        data = pss.cancel_draft(draft_id)
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to cancel settlement.")
    return success_after_mutation(request, data, message=data.get("message") or "Settlement cancelled")


@router.post("/pos-settlements/drafts/{draft_id}/post", dependencies=[_pos_settlement_perm, require_save_nonce])
def pos_settlement_draft_post(
    request: Request,
    draft_id: int,
    payload: dict[str, Any] = Body(default_factory=dict),
):
    body = dict(payload or {})
    body["draft_id"] = draft_id
    try:
        data = pss.post_draft(body, username=_username())
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to post settlement.")
    return success_after_mutation(request, data, message=data.get("message") or "Settlement posted")
