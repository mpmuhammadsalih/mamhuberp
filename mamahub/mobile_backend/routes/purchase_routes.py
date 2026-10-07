from typing import Any

from fastapi import APIRouter, Body, Depends, Query, Request
from fastapi.responses import Response

from mobile_backend.deps_auth import require_access_claims, require_any_permission, require_permission
from mobile_backend.deps_save import require_save_nonce, success_after_mutation
from mobile_backend.mutation_errors import failure_from_mutation_exc
from mobile_backend.services import (
    grn_ai_service,
    grn_service,
    purchase_order_service,
    purchase_return_service,
)
from mobile_backend.services.purchase_service import (
    create_goods_receipt,
    finalize_goods_receiving_without_formal_document,
    get_goods_receipt_details,
    list_goods_receipts,
    update_lpo_line_snapshot,
)
from mobile_backend.utils.response import failure, success

router = APIRouter(
    prefix="/api/v1/purchase",
    tags=["purchase"],
    dependencies=[Depends(require_access_claims)],
)

_po_write = Depends(
    require_any_permission(
        "purchase.purchase_order_add",
        "purchase.purchase_order_new",
        "purchase.purchase_order_edit",
    )
)

_po_receive = Depends(
    require_any_permission(
        "purchase.purchase_order_add",
        "purchase.purchase_order_new",
        "purchase.purchase_order_edit",
        "purchase.purchase_order_list",
        "mobile.goods_receiving",
    )
)

_po_list = Depends(
    require_any_permission(
        "purchase.purchase_order_list",
        "purchase.purchase_order_new",
        "purchase.purchase_order_edit",
        "purchase.purchase_order_add",
        "mobile.purchase_order",
    )
)


@router.get("/grn", dependencies=[Depends(require_permission("purchase.purchase_order_list"))])
def purchase_grn_list(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str = Query(""),
    status: str = Query(""),
    grn_hub: str = Query(
        "",
        description="If 'pending', 'draft', or 'posted', GRN hub tab lists (avoids extra path on older deployments).",
    ),
):
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    search = search.strip()
    status = status.strip()
    hub = grn_hub.strip().lower()
    if hub == "pending":
        rows = grn_service.list_pending_approved_pos(page=page, page_size=page_size, search=search)
        return success({"page": page, "page_size": page_size, "rows": rows})
    if hub == "draft":
        rows = grn_service.list_receipt_documents(
            page=page, page_size=page_size, search=search, inventory_tab="draft"
        )
        return success({"page": page, "page_size": page_size, "rows": rows})
    if hub == "posted":
        rows = grn_service.list_receipt_documents(
            page=page, page_size=page_size, search=search, inventory_tab="posted"
        )
        return success({"page": page, "page_size": page_size, "rows": rows})
    data = list_goods_receipts(page=page, page_size=page_size, search=search, status=status)
    return success({"page": page, "page_size": page_size, "rows": data})


@router.get(
    "/grn/load-from-lpo/{lpo_no:path}",
    dependencies=[Depends(require_permission("purchase.purchase_order_list"))],
)
def purchase_grn_load_from_lpo(lpo_no: str):
    data = grn_service.load_from_lpo(str(lpo_no).strip())
    return success(data)


@router.get(
    "/grn/next-no",
    dependencies=[Depends(require_permission("purchase.purchase_order_list"))],
)
def purchase_grn_next_no():
    return success({"receipt_no": str(grn_service.next_receipt_no())})


@router.post("/grn/ai/extract", dependencies=[_po_receive])
def purchase_grn_ai_extract(request: Request):
    """
    Multipart field ``file`` (invoice PDF/images) — same as ERP AI Extract & fill.
    Long-running; client should use an elevated timeout.
    """
    try:
        data = grn_ai_service.extract_invoice()
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="AI invoice extract failed.")
    return success(data, message="Invoice extracted")


@router.get("/grn/ai/quick-item", dependencies=[_po_receive])
def purchase_grn_ai_quick_item_lookups():
    try:
        data = grn_ai_service.quick_item_lookups()
    except Exception as exc:
        return failure(str(exc)[:300] or "Failed to load quick-item lookups.")
    return success(data)


@router.get("/grn/ai/quick-item/barcode-check", dependencies=[_po_receive])
def purchase_grn_ai_quick_item_barcode_check(barcode: str = Query("")):
    try:
        data = grn_ai_service.barcode_check(barcode)
    except Exception as exc:
        return failure(str(exc)[:300] or "Barcode check failed.")
    return success(data)


@router.post("/grn/ai/quick-item/suggest", dependencies=[_po_receive])
def purchase_grn_ai_quick_item_suggest(payload: dict[str, Any] = Body(default_factory=dict)):
    """AI autofill for GRN quick-create (barcode web + similar-item template). Read-only."""
    try:
        data = grn_ai_service.suggest_item_fields(payload)
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="AI item suggest failed.")
    return success(data)


@router.post("/grn/ai/quick-item", dependencies=[_po_write, require_save_nonce])
def purchase_grn_ai_quick_item_create(
    request: Request,
    payload: dict[str, Any] = Body(default_factory=dict),
):
    try:
        data = grn_ai_service.create_quick_item(payload)
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to create item.")
    return success_after_mutation(request, data, message="Item saved")


@router.post("/grn/save", dependencies=[_po_write, require_save_nonce])
def purchase_grn_save(request: Request, payload: dict[str, Any] = Body(default_factory=dict)):
    """ERP-aligned GRN save (draft or post stock)."""
    try:
        data = grn_service.save_receipt(payload)
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to save GRN.")
    return success_after_mutation(request, data, message=data.get("message") or "Saved Successfully")


@router.post("/grn/post-inventory", dependencies=[_po_write, require_save_nonce])
def purchase_grn_post_inventory(request: Request, payload: dict[str, Any] = Body(default_factory=dict)):
    rn = payload.get("receipt_no") or payload.get("receiptno")
    try:
        data = grn_service.post_inventory(rn, payload)
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to post GRN stock.")
    return success_after_mutation(request, data, message=data.get("message") or "Stock posted")


@router.post("/grn/post-accounts", dependencies=[_po_write, require_save_nonce])
def purchase_grn_post_accounts(request: Request, payload: dict[str, Any] = Body(default_factory=dict)):
    """Post purchase invoice / AP for an inventory-posted GRN."""
    rn = payload.get("receipt_no") or payload.get("receiptno")
    try:
        data = grn_service.post_accounts(rn)
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to post GRN accounts.")
    return success_after_mutation(request, data, message=data.get("message") or "Accounts posted")


@router.post("/grn/{receipt_no}/cancel", dependencies=[_po_write, require_save_nonce])
def purchase_grn_cancel(request: Request, receipt_no: str):
    """Cancel/delete a draft GRN (not stock- or account-posted). Frees the linked PO for Pending."""
    try:
        data = grn_service.delete_receipt(receipt_no)
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to cancel GRN.")
    return success_after_mutation(
        request,
        data,
        message=data.get("message") or "GRN canceled",
    )


@router.get(
    "/grn/{receipt_no}/pdf",
    dependencies=[Depends(require_permission("purchase.purchase_order_list"))],
)
def purchase_grn_pdf(receipt_no: str):
    """Download ERP-style GRN PDF (same layout as desktop receipt print)."""
    try:
        pdf_bytes, filename = grn_service.build_receipt_pdf(receipt_no)
    except ValueError as exc:
        return failure(str(exc), status_code=404)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.get(
    "/grn/{receipt_no:path}",
    dependencies=[Depends(require_permission("purchase.purchase_order_list"))],
)
def purchase_grn_details(receipt_no: str, source: str = Query("", description="'lpo' = load PO for new GRN")):
    key = str(receipt_no or "").strip()
    if source.strip().lower() == "lpo":
        data = grn_service.load_from_lpo(key)
        return success(data)
    try:
        data = grn_service.get_formal_receipt(key)
        return success(data)
    except ValueError:
        pass
    data = get_goods_receipt_details(receipt_no=key)
    return success(data)


@router.post("/grn", dependencies=[_po_write, require_save_nonce])
def purchase_grn_create(request: Request, payload: dict[str, Any] = Body(default_factory=dict)):
    """Legacy create — prefer POST /grn/save with save_mode."""
    try:
        if payload.get("save_mode") or payload.get("post_inventory") is not None:
            data = grn_service.save_receipt(payload)
            return success_after_mutation(
                request, data, message=data.get("message") or "Saved Successfully", status_code=201
            )
        data = create_goods_receipt(payload)
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to save GRN.")
    return success_after_mutation(request, data, message="Saved Successfully", status_code=201)


@router.get("/grn-hub/pending", dependencies=[Depends(require_permission("purchase.purchase_order_list"))])
def purchase_grn_hub_pending(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str = Query(""),
):
    """ERP Approved PO tab — approved LPO without RECEIPTHDR."""
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    rows = grn_service.list_pending_approved_pos(page=page, page_size=page_size, search=search.strip())
    return success({"page": page, "page_size": page_size, "rows": rows})


@router.get("/grn-hub/draft", dependencies=[Depends(require_permission("purchase.purchase_order_list"))])
def purchase_grn_hub_draft(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str = Query(""),
):
    rows = grn_service.list_receipt_documents(
        page=page, page_size=page_size, search=search.strip(), inventory_tab="draft"
    )
    return success({"page": page, "page_size": page_size, "rows": rows})


@router.get("/grn-hub/posted", dependencies=[Depends(require_permission("purchase.purchase_order_list"))])
def purchase_grn_hub_posted(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str = Query(""),
):
    rows = grn_service.list_receipt_documents(
        page=page, page_size=page_size, search=search.strip(), inventory_tab="posted"
    )
    return success({"page": page, "page_size": page_size, "rows": rows})


@router.get("/orders", dependencies=[_po_list])
def purchase_orders_list(
    q: str = Query(""),
    tab: str = Query("draft"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=20, le=100),
    date_from: str = Query(""),
    date_to: str = Query(""),
):
    data = purchase_order_service.list_orders(
        tab=tab,
        search=q,
        page=page,
        page_size=page_size,
        date_from=date_from,
        date_to=date_to,
    )
    return success(data)


@router.get("/order/open", dependencies=[_po_list])
def purchase_order_open():
    return success(purchase_order_service.get_open_context())


@router.get("/order/suppliers", dependencies=[_po_list])
def purchase_order_suppliers(
    q: str = Query(""),
    limit: int = Query(80, ge=1, le=200),
):
    return success({"suppliers": purchase_order_service.list_suppliers(search=q, limit=limit)})


@router.get("/order/catalog", dependencies=[_po_list])
def purchase_order_catalog(
    q: str = Query(""),
    limit: int = Query(60, ge=1, le=200),
    supplier_code: str = Query(""),
):
    return success(
        {
            "items": purchase_order_service.list_catalog_items(
                search=q, limit=limit, supplier_code=supplier_code
            )
        }
    )


@router.get("/order/supplier-items", dependencies=[_po_list])
def purchase_order_supplier_items(
    supplier_code: str = Query(..., min_length=1),
    q: str = Query(""),
    limit: int = Query(80, ge=1, le=200),
    days: int = Query(365, ge=30, le=730),
):
    """Supplier items tab — prior GRN purchases + master items linked to supplier."""
    rows = purchase_order_service.list_supplier_items(
        supplier_code=supplier_code,
        search=q,
        limit=limit,
        days=days,
    )
    return success({"items": rows, "count": len(rows)})


@router.get("/order/item-uoms", dependencies=[_po_list])
def purchase_order_item_uoms(item_code: str = Query(..., min_length=1)):
    return success({"uoms": purchase_order_service.list_item_uoms(item_code)})


@router.get("/order/warehouses", dependencies=[_po_list])
def purchase_order_warehouses(
    q: str = Query(""),
    limit: int = Query(100, ge=1, le=300),
):
    return success({"warehouses": purchase_order_service.list_warehouses(search=q, limit=limit)})


@router.post("/order/save", dependencies=[_po_write, require_save_nonce])
def purchase_order_save(request: Request, payload: dict[str, Any] = Body(default_factory=dict)):
    from mobile_backend.request_context import get_jwt

    claims = get_jwt()
    username = str(claims.get("sub") or "mobile").strip()
    try:
        data = purchase_order_service.save_order(payload, username=username)
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to save purchase order.")
    return success_after_mutation(
        request,
        data,
        message=data.get("message") or "Purchase order saved",
    )


@router.get("/orders/{lpo_no}/pdf", dependencies=[_po_list])
def purchase_order_pdf(lpo_no: str):
    """Download ERP-style purchase order PDF (same layout as desktop PO print)."""
    try:
        pdf_bytes, filename = purchase_order_service.build_order_pdf(lpo_no)
    except ValueError as exc:
        return failure(str(exc), status_code=404)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/orders/{lpo_no:path}", dependencies=[_po_list])
def purchase_order_detail(lpo_no: str):
    data = purchase_order_service.get_order_detail(lpo_no)
    if not data:
        return failure("Purchase order not found.", status_code=404)
    return success(data)


@router.post("/orders/{lpo_no:path}/cancel", dependencies=[_po_write, require_save_nonce])
def purchase_order_cancel(request: Request, lpo_no: str):
    try:
        data = purchase_order_service.cancel_order(lpo_no)
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to cancel purchase order.")
    return success_after_mutation(
        request,
        data,
        message=data.get("message") or "Purchase order canceled",
    )


@router.get("/returns", dependencies=[_po_list])
def purchase_returns_list(
    q: str = Query(""),
    tab: str = Query("draft"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=20, le=100),
):
    data = purchase_return_service.list_returns(
        tab=tab,
        search=q,
        page=page,
        page_size=page_size,
    )
    return success(data)


@router.get("/return/open", dependencies=[_po_list])
def purchase_return_open():
    return success(purchase_return_service.get_open_context())


@router.post("/return/save", dependencies=[_po_write, require_save_nonce])
def purchase_return_save(request: Request, payload: dict[str, Any] = Body(default_factory=dict)):
    from mobile_backend.request_context import get_jwt

    claims = get_jwt()
    username = str(claims.get("sub") or "mobile").strip()
    try:
        data = purchase_return_service.save_request(payload, username=username)
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to save purchase return.")
    return success_after_mutation(
        request,
        data,
        message=data.get("message") or "Purchase return saved",
    )


@router.get("/returns/{return_no}/pdf", dependencies=[_po_list])
def purchase_return_pdf(return_no: str, kind: str = Query("request")):
    """PDF for return request (TEMP) or posted stock return."""
    try:
        if (kind or "request").strip().lower() == "posted":
            pdf_bytes, filename = purchase_return_service.build_posted_pdf(return_no)
        else:
            pdf_bytes, filename = purchase_return_service.build_request_pdf(return_no)
    except ValueError as exc:
        return failure(str(exc), status_code=404)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/returns/{return_no:path}", dependencies=[_po_list])
def purchase_return_detail(return_no: str, kind: str = Query("request")):
    if (kind or "request").strip().lower() == "posted":
        data = purchase_return_service.get_posted_detail(return_no)
    else:
        data = purchase_return_service.get_request_detail(return_no)
        if not data:
            data = purchase_return_service.get_posted_detail(return_no)
    if not data:
        return failure("Purchase return not found.", status_code=404)
    return success(data)


@router.post("/returns/{return_no:path}/cancel", dependencies=[_po_write, require_save_nonce])
def purchase_return_cancel(request: Request, return_no: str):
    try:
        data = purchase_return_service.cancel_request(return_no)
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to cancel purchase return.")
    return success_after_mutation(
        request,
        data,
        message=data.get("message") or "Purchase return canceled",
    )


@router.post("/returns/{return_no:path}/approve", dependencies=[_po_write, require_save_nonce])
def purchase_return_approve(
    request: Request,
    return_no: str,
    payload: dict[str, Any] = Body(default_factory=dict),
):
    try:
        data = purchase_return_service.approve_request(
            return_no,
            remarks=str(payload.get("remarks") or "").strip(),
        )
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to post purchase return.")
    return success_after_mutation(
        request,
        data,
        message=data.get("message") or "Purchase return posted",
    )


@router.api_route(
    "/po/{po_no:path}/finalize-receiving",
    methods=["POST"],
    dependencies=[_po_receive, require_save_nonce],
)
def purchase_po_finalize_receiving(request: Request, po_no: str):
    """Mark Goods Receiving complete on LPOHDR (no RECEIPTHDR). Formal GRN: POST /grn/save."""
    try:
        data = finalize_goods_receiving_without_formal_document(po_no=str(po_no))
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to finalize receiving.")
    return success_after_mutation(request, data)


@router.api_route(
    "/po/{po_no:path}/line",
    methods=["PATCH", "POST"],
    dependencies=[_po_receive, require_save_nonce],
)
def purchase_po_line_patch(request: Request, po_no: str, payload: dict[str, Any] = Body(default_factory=dict)):
    try:
        data = update_lpo_line_snapshot(po_no=po_no, payload=payload)
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to save receiving line.")
    return success_after_mutation(request, data, message="Line saved")
