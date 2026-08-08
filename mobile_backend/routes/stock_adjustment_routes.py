from typing import Any

from fastapi import APIRouter, Body, Depends, Query, Request
from fastapi.responses import Response

from mobile_backend.deps_auth import require_access_claims, require_any_permission
from mobile_backend.deps_save import require_save_nonce, success_after_mutation
from mobile_backend.mutation_errors import failure_from_mutation_exc
from mobile_backend.services import stock_adjustment_service as svc
from mobile_backend.utils.response import failure, success

router = APIRouter(
    prefix="/api/v1/stock-adjustment",
    tags=["stock-adjustment"],
    dependencies=[Depends(require_access_claims)],
)

_perm = Depends(
    require_any_permission(
        "purchase.stock_adjustment_list",
        "purchase.stock_adjustment",
        "mobile.stock_adjustment",
        "mobile.inventory",
    )
)

_write = Depends(
    require_any_permission(
        "purchase.stock_adjustment",
        "purchase.stock_adjustment_list",
        "mobile.stock_adjustment",
        "mobile.inventory",
    )
)


@router.get("/adjustments", dependencies=[_perm])
def list_adjustments(
    q: str = Query(""),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=20, le=100),
):
    data = svc.list_adjustments(search=q, page=page, page_size=page_size)
    return success(data)


@router.get("/open", dependencies=[_perm])
def open_context():
    return success(svc.get_open_context())


@router.get("/warehouses", dependencies=[_perm])
def warehouses():
    return success({"warehouses": svc.list_warehouses()})


@router.get("/catalog", dependencies=[_perm])
def catalog(
    q: str = Query(""),
    limit: int = Query(80, ge=1, le=200),
):
    return success({"items": svc.list_catalog_items(search=q, limit=limit)})


@router.get("/item-uoms", dependencies=[_perm])
def item_uoms(item_code: str = Query(..., min_length=1)):
    return success({"uoms": svc.list_item_uoms(item_code)})


@router.get("/item-stock", dependencies=[_perm])
def item_stock(
    item_code: str = Query(..., min_length=1),
    store: str = Query(""),
):
    try:
        data = svc.get_item_stock(item_code=item_code, store=store)
    except ValueError as exc:
        return failure(str(exc), status_code=400)
    return success(data)


@router.post("/adjustments", dependencies=[_write, require_save_nonce])
def save_adjustment(request: Request, payload: dict[str, Any] = Body(default_factory=dict)):
    try:
        data = svc.save_adjustment(payload)
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to save stock adjustment.")
    return success_after_mutation(
        request,
        data,
        message=data.get("message") or "Stock adjustment saved",
        status_code=201,
    )


@router.get("/adjustments/{adj_no}/pdf", dependencies=[_perm])
def adjustment_pdf(adj_no: str):
    try:
        pdf_bytes, filename = svc.build_pdf(adj_no)
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


@router.get("/adjustments/{adj_no:path}", dependencies=[_perm])
def adjustment_detail(adj_no: str):
    data = svc.get_detail(adj_no)
    if not data:
        return failure("Stock adjustment not found.", status_code=404)
    return success(data)


@router.post("/adjustments/{adj_no:path}/reverse", dependencies=[_write, require_save_nonce])
def adjustment_reverse(request: Request, adj_no: str):
    try:
        data = svc.reverse_adjustment(adj_no)
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to reverse stock adjustment.")
    return success_after_mutation(
        request,
        data,
        message=data.get("message") or "Stock adjustment reversed",
    )
