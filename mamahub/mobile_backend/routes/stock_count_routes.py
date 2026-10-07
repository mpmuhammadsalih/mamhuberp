from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from mobile_backend.deps_auth import require_access_claims, require_any_permission
from mobile_backend.deps_save import require_save_nonce, success_after_mutation
from mobile_backend.mutation_errors import failure_from_mutation_exc
from mobile_backend.services import stock_count_service as svc
from mobile_backend.utils.response import success

router = APIRouter(
    prefix="/api/v1/stock-count",
    tags=["stock-count"],
    dependencies=[Depends(require_access_claims)],
)

_STOCK_COUNT_PERMS = (
    "itemmaster.productlist",
    "warehouse.warehouse_stock_verification",
    "warehouse.warehouse_stock_counting",
    "purchase.stock_adjustment_list",
)
_stock_count_perm = Depends(require_any_permission(*_STOCK_COUNT_PERMS))


class SessionBody(BaseModel):
    locationcode: int = Field(..., ge=0)
    warehouse_id: int | None = None
    storage_id: int | None = None
    remarks: str = ""


class LineBody(BaseModel):
    locationcode: int = Field(..., ge=0)
    itemcode: str | int
    counted_qty: float
    system_qty: float = 0
    uom: str = ""
    barcode: str = ""
    warehouse_id: int | None = None
    storage_id: int | None = None
    retail_price: float | None = None
    update_retail_price: bool = False


@router.get(
    "/sessions",
    dependencies=[_stock_count_perm],
)
def list_sessions(
    locationcode: int = Query(
        0,
        ge=0,
        description="Branch/location filter; 0 = all locations (default)",
    ),
    limit: int = Query(50, ge=1, le=100),
    status: str = Query(
        "OPEN",
        max_length=20,
        description="OPEN = all non-POSTED (DRAFT, PENDING, …); or exact STATUS value",
    ),
    available_for_user: bool = Query(
        False,
        description="Deprecated — ignored; all open counts are listed for every user",
    ),
):
    loc_filter = None if locationcode == 0 else locationcode
    rows = svc.list_sessions(
        loc_filter,
        limit=limit,
        status=status,
        available_for_user=available_for_user,
    )
    return success({"rows": rows})


@router.post(
    "/sessions",
    dependencies=[_stock_count_perm, require_save_nonce],
)
def create_or_get_draft(
    request: Request,
    body: SessionBody,
    force_new: bool = Query(False, description="If true, always start a new COUNT_NO"),
):
    try:
        if force_new:
            data = svc.create_new_session(
                body.locationcode,
                warehouse_id=body.warehouse_id,
                storage_id=body.storage_id,
                remarks=body.remarks,
            )
            return success_after_mutation(request, data, message="New stock count started")
        data = svc.ensure_draft_session(
            body.locationcode,
            warehouse_id=body.warehouse_id,
            storage_id=body.storage_id,
            remarks=body.remarks,
        )
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to start stock count.")
    return success_after_mutation(request, data, message="Stock count session ready")


@router.get(
    "/sessions/current",
    dependencies=[_stock_count_perm],
)
def get_current_draft(locationcode: int = Query(..., ge=0)):
    data = svc.get_current_draft(locationcode)
    return success(data or {})


@router.post(
    "/sessions/{count_no}/claim",
    dependencies=[_stock_count_perm, require_save_nonce],
)
def claim_session(request: Request, count_no: int, body: SessionBody):
    """Legacy endpoint — returns the count without assignment locking."""
    try:
        data = svc.claim_session(body.locationcode, count_no)
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to open stock count.")
    return success_after_mutation(request, data, message="Count ready")


@router.get(
    "/sessions/{count_no}",
    dependencies=[_stock_count_perm],
)
def get_session(count_no: int, locationcode: int = Query(..., ge=0)):
    data = svc.get_session(locationcode, count_no)
    return success(data)


@router.put(
    "/sessions/{count_no}/lines",
    dependencies=[_stock_count_perm, require_save_nonce],
)
def upsert_line(request: Request, count_no: int, body: LineBody):
    try:
        data = svc.upsert_line(
            body.locationcode,
            count_no,
            itemcode=body.itemcode,
            counted_qty=body.counted_qty,
            system_qty=body.system_qty,
            uom=body.uom,
            barcode=body.barcode,
            warehouse_id=body.warehouse_id,
            storage_id=body.storage_id,
            retail_price=body.retail_price,
            update_retail_price=body.update_retail_price,
        )
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to save count line.")
    return success_after_mutation(request, data, message="Line saved")


@router.delete(
    "/sessions/{count_no}/lines/{line_no}",
    dependencies=[_stock_count_perm, require_save_nonce],
)
def delete_line(
    request: Request,
    count_no: int,
    line_no: int,
    locationcode: int = Query(..., ge=0),
):
    try:
        svc.delete_line(locationcode, count_no, line_no)
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to remove count line.")
    return success_after_mutation(request, message="Line removed")


@router.delete(
    "/sessions/{count_no}/lines",
    dependencies=[_stock_count_perm, require_save_nonce],
)
def delete_line_by_item(
    request: Request,
    count_no: int,
    locationcode: int = Query(..., ge=0),
    itemcode: str = Query(...),
):
    try:
        svc.delete_line_by_itemcode(locationcode, count_no, itemcode)
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to remove count line.")
    return success_after_mutation(request, message="Line removed")


@router.post(
    "/sessions/{count_no}/post",
    dependencies=[_stock_count_perm, require_save_nonce],
)
def post_session(request: Request, count_no: int, body: SessionBody):
    """Set STATUS to POSTED on STOCK_COUNT_HDR."""
    try:
        data = svc.post_session(body.locationcode, count_no)
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to post stock count.")
    return success_after_mutation(request, data, message="Stock count posted")
