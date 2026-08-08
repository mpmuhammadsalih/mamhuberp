from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from mobile_backend.deps_auth import require_access_claims, require_any_permission
from mobile_backend.deps_save import require_save_nonce, success_after_mutation
from mobile_backend.mutation_errors import failure_from_mutation_exc
from mobile_backend.services import stock_transfer_service as svc
from mobile_backend.utils.response import success

router = APIRouter(
    prefix="/api/v1/stock-transfer",
    tags=["stock-transfer"],
    dependencies=[Depends(require_access_claims)],
)

_perm = Depends(
    require_any_permission(
        "purchase.stock_transfer",
        "purchase.stock_transfer_items",
        "mobile.stock_transfer",
    )
)


class TransferLineBody(BaseModel):
    item_code: int
    item_name: str = ""
    uom: str = "NOS"
    available_qty: float = 0
    transfer_qty: float = Field(..., gt=0)
    remarks: str = ""
    lot_id: str = ""
    batch_no: str = ""
    mfg_date: str = ""
    expiry_date: str = ""
    from_storage_id: str = ""
    to_storage_id: str = ""


class SaveTransferBody(BaseModel):
    transfer_no: int = 0
    transfer_date: str
    from_store: str
    to_store: str
    remarks: str = ""
    lines: list[TransferLineBody]
    update_existing: bool = False


@router.get("/stores", dependencies=[_perm])
def stores_route():
    return success({"stores": svc.list_stores()})


@router.get("/transfers", dependencies=[_perm])
def list_transfers_route(
    bucket: str = Query("all", description="all | created | transit | completed"),
    from_store: str = Query(""),
    to_store: str = Query(""),
    limit: int = Query(50, ge=1, le=100),
):
    rows = svc.list_transfers(
        bucket=bucket,
        from_store=from_store.strip(),
        to_store=to_store.strip(),
        limit=limit,
    )
    return success({"rows": rows})


@router.get("/transfers/next-no", dependencies=[_perm])
def next_no_route():
    return success({"transfer_no": svc.next_transfer_no()})


@router.get("/transfers/{transfer_no}", dependencies=[_perm])
def get_transfer_route(transfer_no: int):
    data = svc.get_transfer(transfer_no)
    if not data:
        return success(None, message="Transfer not found")
    return success(data)


@router.get("/items", dependencies=[_perm])
def search_items_route(
    from_store: str = Query(..., min_length=1),
    search: str = Query(""),
    exact_barcode: str = Query(""),
    exact_item_code: int = Query(0, ge=0),
    limit: int = Query(40, ge=1, le=100),
):
    ic = int(exact_item_code) if exact_item_code > 0 else None
    bc = exact_barcode.strip() or None
    items = svc.search_items(
        from_store=from_store,
        search=search,
        limit=limit,
        exact_barcode=bc,
        exact_item_code=ic,
    )
    return success({"items": items})


@router.get("/item-stock", dependencies=[_perm])
def item_stock_route(
    item_code: int = Query(..., ge=1),
    store: str = Query(..., min_length=1),
):
    return success(svc.item_stock(item_code=item_code, store=store))


@router.post("/transfers", dependencies=[_perm, require_save_nonce])
def save_transfer_route(request: Request, body: SaveTransferBody):
    payload: dict[str, Any] = body.model_dump()
    payload["lines"] = [ln.model_dump() for ln in body.lines]
    try:
        data = svc.save_transfer(payload)
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to save stock transfer.")
    return success_after_mutation(request, data, message="Transfer saved")


@router.post("/transfers/{transfer_no}/transfer", dependencies=[_perm, require_save_nonce])
def post_transfer_route(request: Request, transfer_no: int):
    try:
        data = svc.post_transfer(transfer_no)
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to post stock transfer.")
    return success_after_mutation(request, data, message="Transferred to transit")


@router.post("/transfers/{transfer_no}/approve", dependencies=[_perm, require_save_nonce])
def approve_transfer_route(request: Request, transfer_no: int):
    try:
        data = svc.approve_transfer(transfer_no)
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to approve stock transfer.")
    return success_after_mutation(request, data, message="Transfer approved")
