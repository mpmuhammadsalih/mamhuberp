from typing import Any

from fastapi import APIRouter, Body, Depends, Query, Request
from fastapi.responses import Response

from mobile_backend.deps_auth import require_access_claims, require_any_permission, require_permission
from mobile_backend.deps_save import require_save_nonce, success_after_mutation
from mobile_backend.mutation_errors import failure_from_mutation_exc
from mobile_backend.services import (
    sales_invoice_service,
    sales_order_service,
    sales_return_service,
    sales_service,
)
from mobile_backend.utils.response import failure, success

router = APIRouter(
    prefix="/api/v1/sales",
    tags=["sales"],
    dependencies=[Depends(require_access_claims)],
)

_invoice_perm = Depends(require_permission("sales.sales_invoice"))
_return_perm = Depends(require_permission("sales.sales_return"))
_order_perm = Depends(
    require_any_permission("sales.sales_order", "sales.sales_order_list")
)
_sales_doc_perm = Depends(
    require_any_permission(
        "sales.sales_invoice",
        "sales.sales_order",
        "sales.sales_order_list",
        "sales.sales_return",
    )
)


@router.get("/summary", dependencies=[_invoice_perm])
def sales_summary():
    return success({"message": "Sales endpoints ready"})


_SALES_REPORT_PERMS = (
    "sales_summary.sales_summary",
    "reports.sales_details",
    "reports.margin_report",
    "sales.sales_invoice",
)


@router.get(
    "/reports",
    dependencies=[Depends(require_any_permission(*_SALES_REPORT_PERMS))],
)
def sales_reports(
    days: int = Query(30, ge=1, le=90),
    date_from: str = Query(""),
    date_to: str = Query(""),
):
    return success(sales_service.get_sales_reports(days=days, date_from=date_from, date_to=date_to))


@router.get("/invoices", dependencies=[_invoice_perm])
def sales_invoices_list(
    q: str = Query(""),
    limit: int = Query(50, ge=1, le=100),
    days: int = Query(90, ge=7, le=365),
    date_from: str = Query(""),
    date_to: str = Query(""),
    customer_code: str = Query(""),
    billing_type: str = Query(""),
):
    rows = sales_invoice_service.list_invoices(
        search=q,
        limit=limit,
        days=days,
        date_from=date_from,
        date_to=date_to,
        customer_code=customer_code,
        billing_type=billing_type,
    )
    return success({"invoices": rows})


@router.get("/invoices/{billno}/pdf", dependencies=[_invoice_perm])
def sales_invoice_pdf(billno: str):
    """Download ERP-style sales invoice PDF (cashbilldup layout)."""
    try:
        pdf_bytes, filename = sales_invoice_service.build_invoice_pdf(billno)
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


@router.get("/invoices/{billno}", dependencies=[_invoice_perm])
def sales_invoice_detail(billno: str):
    data = sales_invoice_service.get_invoice_detail(billno)
    if not data:
        return failure("Invoice not found.", status_code=404)
    return success(data)


@router.get("/invoice/open", dependencies=[_invoice_perm])
def sales_invoice_open(peek: bool = Query(True, description="Peek bill no without reserving")):
    return success(sales_invoice_service.get_invoice_open_context(peek_billno=peek))


@router.get("/invoice/next-billno", dependencies=[_invoice_perm])
def sales_invoice_next_billno(peek: bool = Query(False)):
    return success(sales_invoice_service.get_invoice_open_context(peek_billno=peek))


@router.get("/invoice/customers", dependencies=[_sales_doc_perm])
def sales_invoice_customers(
    q: str = Query(""),
    limit: int = Query(50, ge=1, le=200),
):
    rows = sales_invoice_service.list_customers(search=q, limit=limit)
    return success({"customers": rows})


@router.get("/invoice/customer-outstanding", dependencies=[_sales_doc_perm])
def sales_invoice_customer_outstanding(
    customer_code: str = Query(..., min_length=1),
):
    data = sales_invoice_service.get_customer_outstanding(customer_code)
    return success(data)


@router.get("/invoice/item-info", dependencies=[_sales_doc_perm])
def sales_invoice_item_info(query: str = Query(..., min_length=1)):
    item = sales_invoice_service.lookup_item(query)
    return success({"item": item})


@router.get("/invoice/item-uoms", dependencies=[_sales_doc_perm])
def sales_invoice_item_uoms(item_code: str = Query(..., min_length=1)):
    uoms = sales_invoice_service.list_item_uoms(item_code)
    return success({"uoms": uoms})


@router.get("/invoice/uom-info", dependencies=[_sales_doc_perm])
def sales_invoice_uom_info(
    item_code: str = Query(..., min_length=1),
    uom_code: str = Query(..., min_length=1),
    price_mode: str = Query("retail"),
):
    pricing = sales_invoice_service.get_uom_pricing(item_code, uom_code, price_mode=price_mode)
    return success({"pricing": pricing})


@router.get("/invoice/item-last-sale", dependencies=[_sales_doc_perm])
def sales_invoice_item_last_sale(
    item_code: str = Query(..., min_length=1),
    customer_code: str = Query(""),
):
    data = sales_invoice_service.get_item_last_sale(
        item_code,
        customer_code=customer_code,
    )
    return success({"last_sale": data})


@router.get("/invoice/catalog", dependencies=[_sales_doc_perm])
def sales_invoice_catalog(
    q: str = Query(""),
    warehouse_id: str = Query(""),
    customer_code: str = Query(""),
    limit: int = Query(60, ge=1, le=500),
    for_return: bool = Query(
        False,
        description="Sales return catalog: include zero-stock / full item master",
    ),
):
    from mobile_backend.request_context import get_jwt

    claims = get_jwt()
    username = str(claims.get("sub") or "mobile").strip()
    rows = sales_invoice_service.list_catalog_items(
        search=q,
        warehouse_id=warehouse_id or None,
        customer_code=customer_code or None,
        limit=limit,
        username=username,
        for_return=for_return,
    )
    return success({"items": rows})


@router.get("/invoice/warehouses", dependencies=[_sales_doc_perm])
def sales_invoice_warehouses(
    q: str = Query(""),
    limit: int = Query(100, ge=1, le=300),
):
    rows = sales_invoice_service.list_warehouses(search=q, limit=limit)
    return success({"warehouses": rows})


@router.get("/invoice/warehouse-bins", dependencies=[_sales_doc_perm])
def sales_invoice_warehouse_bins(warehouse_id: str = Query(..., min_length=1)):
    bins = sales_invoice_service.list_warehouse_bins(warehouse_id)
    return success({"warehouse_id": warehouse_id, "bins": bins})


@router.get("/invoice/item-bins", dependencies=[_sales_doc_perm])
def sales_invoice_item_bins(
    item_code: str = Query(..., min_length=1),
    warehouse_id: str = Query(..., min_length=1),
):
    data = sales_invoice_service.list_item_bins_for_warehouse(item_code, warehouse_id)
    return success(data)


@router.get("/invoice/batch-lots", dependencies=[_sales_doc_perm])
def sales_invoice_batch_lots(item_code: str = Query(..., min_length=1)):
    lots = sales_invoice_service.list_batch_lots(item_code)
    return success({"lots": lots})


@router.get("/invoice/credit-check", dependencies=[_sales_doc_perm])
def sales_invoice_credit_check(
    customer_code: str = Query(..., min_length=1),
    net_amount: float = Query(..., ge=0),
    billing_type: str = Query("CREDIT"),
):
    data = sales_invoice_service.check_credit_limit(customer_code, net_amount, billing_type)
    return success(data)


@router.get("/invoice/payment-tenders", dependencies=[_invoice_perm])
def sales_invoice_payment_tenders():
    tenders = sales_invoice_service.list_payment_tenders()
    return success({"tenders": tenders})


@router.post("/invoice/save", dependencies=[_invoice_perm, require_save_nonce])
def sales_invoice_save(request: Request, payload: dict[str, Any] = Body(default_factory=dict)):
    from mobile_backend.request_context import get_jwt

    claims = get_jwt()
    username = str(claims.get("sub") or "mobile").strip()
    try:
        data = sales_invoice_service.save_invoice(payload, username=username)
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to save sales invoice.")
    return success_after_mutation(
        request,
        data,
        message=data.get("message") or "Sales invoice saved",
    )


@router.get("/returns", dependencies=[_return_perm])
def sales_returns_list(
    q: str = Query(""),
    limit: int = Query(50, ge=1, le=100),
    days: int = Query(90, ge=7, le=365),
    date_from: str = Query(""),
    date_to: str = Query(""),
    customer_code: str = Query(""),
    billing_type: str = Query(""),
):
    rows = sales_return_service.list_returns(
        search=q,
        limit=limit,
        days=days,
        date_from=date_from,
        date_to=date_to,
        customer_code=customer_code,
        billing_type=billing_type,
    )
    return success({"returns": rows})


@router.get("/returns/{billno}/pdf", dependencies=[_return_perm])
def sales_return_pdf(billno: str):
    try:
        pdf_bytes, filename = sales_return_service.build_return_pdf(billno)
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


@router.get("/returns/{billno}", dependencies=[_return_perm])
def sales_return_detail(billno: str):
    data = sales_return_service.get_return_detail(billno)
    if not data:
        return failure("Sales return not found.", status_code=404)
    return success(data)


@router.get("/return/open", dependencies=[_return_perm])
def sales_return_open(peek: bool = Query(True, description="Peek bill no without reserving")):
    return success(sales_return_service.get_return_open_context(peek_billno=peek))


@router.get("/return/load-from-invoice/{billno}", dependencies=[_return_perm])
def sales_return_load_from_invoice(billno: str):
    try:
        data = sales_return_service.load_from_invoice(billno)
    except ValueError as exc:
        return failure(str(exc), status_code=404)
    return success(data)


@router.post("/return/save", dependencies=[_return_perm, require_save_nonce])
def sales_return_save(request: Request, payload: dict[str, Any] = Body(default_factory=dict)):
    from mobile_backend.request_context import get_jwt

    claims = get_jwt()
    username = str(claims.get("sub") or "mobile").strip()
    try:
        data = sales_return_service.save_return(payload, username=username)
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to save sales return.")
    return success_after_mutation(
        request,
        data,
        message=data.get("message") or "Sales return saved",
    )


@router.get("/orders", dependencies=[_order_perm])
def sales_orders_list(
    q: str = Query(""),
    limit: int = Query(50, ge=1, le=100),
    days: int = Query(90, ge=7, le=365),
    date_from: str = Query(""),
    date_to: str = Query(""),
    customer_code: str = Query(""),
    billing_type: str = Query(""),
    status_tab: str = Query("order"),
):
    rows = sales_order_service.list_orders(
        search=q,
        limit=limit,
        days=days,
        date_from=date_from,
        date_to=date_to,
        customer_code=customer_code,
        billing_type=billing_type,
        status_tab=status_tab,
    )
    return success({"orders": rows})


@router.get("/orders/{billno}", dependencies=[_order_perm])
def sales_order_detail(billno: str):
    data = sales_order_service.get_order_detail(billno)
    if not data:
        return failure("Sales order not found.", status_code=404)
    return success(data)


@router.get("/order/open", dependencies=[_order_perm])
def sales_order_open(peek: bool = Query(True, description="Peek bill no without reserving")):
    return success(sales_order_service.get_order_open_context(peek_billno=peek))


@router.post("/order/save", dependencies=[_order_perm, require_save_nonce])
def sales_order_save(request: Request, payload: dict[str, Any] = Body(default_factory=dict)):
    from mobile_backend.request_context import get_jwt

    claims = get_jwt()
    username = str(claims.get("sub") or "mobile").strip()
    try:
        data = sales_order_service.save_order(payload, username=username)
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to save sales order.")
    return success_after_mutation(
        request,
        data,
        message=data.get("message") or "Sales order saved",
    )


@router.post(
    "/orders/{billno}/convert",
    dependencies=[
        Depends(
            require_any_permission(
                "sales.sales_invoice",
                "sales.sales_order",
                "sales.sales_order_list",
                "sales.sales_order_batch_invoice",
            )
        ),
        require_save_nonce,
    ],
)
def sales_order_convert_to_invoice(request: Request, billno: str):
    """Convert a pending sales order into a posted sales invoice."""
    from mobile_backend.request_context import get_jwt

    claims = get_jwt()
    username = str(claims.get("sub") or "mobile").strip()
    try:
        data = sales_order_service.convert_order_to_invoice(billno, username=username)
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to convert sales order.")
    return success_after_mutation(
        request,
        data,
        message=data.get("message") or "Converted to sale",
    )


@router.post(
    "/orders/{billno}/cancel",
    dependencies=[
        Depends(
            require_any_permission(
                "sales.sales_order",
                "sales.sales_order_list",
                "sales.sales_order_cancel",
            )
        ),
        require_save_nonce,
    ],
)
def sales_order_cancel(request: Request, billno: str):
    """Cancel a pending sales order."""
    try:
        data = sales_order_service.cancel_order(billno)
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to cancel sales order.")
    return success_after_mutation(
        request,
        data,
        message=data.get("message") or "Sales order cancelled",
    )
