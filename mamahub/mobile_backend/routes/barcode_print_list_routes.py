from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from mobile_backend.deps_auth import require_access_claims, require_any_permission
from mobile_backend.deps_save import require_save_nonce, success_after_mutation
from mobile_backend.mutation_errors import failure_from_mutation_exc
from mobile_backend.services import barcode_print_list_service as svc
from mobile_backend.utils.response import failure, success

router = APIRouter(
    prefix="/api/v1/barcode-print-lists",
    tags=["barcode-print-lists"],
    dependencies=[Depends(require_access_claims)],
)

_perm = Depends(
    require_any_permission(
        "itemmaster.productlist",
        "mobile.stock_lookup",
        "mobile.barcode_scanning",
        "barcode_management.product",
        "barcode_management.shelf",
        "warehouse.warehouse_stock_counting",
        "warehouse.warehouse_stock_counting_mobile",
    )
)


class PrintListLineBody(BaseModel):
    itemcode: int | str | None = None
    itemname: str = ""
    barcode: str = Field(..., min_length=1, max_length=80)
    uom: str = "PCS"
    retail_price: float = 0
    print_qty: int = Field(1, ge=1, le=999)
    storage_id: int | None = None
    storage_type: str = ""
    storage_code: str = ""
    storage_name: str = ""
    path_text: str = ""


class PrintListSaveBody(BaseModel):
    locationcode: int | None = Field(None, ge=0)
    print_no: int | None = Field(None, ge=1)
    list_type: str = Field("PRODUCT", max_length=20)
    status: str = Field("READY", max_length=20)
    remarks: str = Field("", max_length=500)
    source: str = Field("MOBILE", max_length=40)
    source_ref: str = Field("", max_length=80)
    lines: list[PrintListLineBody] = Field(default_factory=list)


@router.get("", dependencies=[_perm])
def list_print_lists(
    locationcode: int = Query(0, ge=0),
    list_type: str = Query("", max_length=20),
    limit: int = Query(50, ge=1, le=100),
):
    loc = None if locationcode in (None, 0) else locationcode
    lt = (list_type or "").strip() or None
    rows = svc.list_documents(locationcode=loc, list_type=lt, limit=limit)
    return success({"rows": rows})


@router.get("/{print_no}", dependencies=[_perm])
def get_print_list(
    print_no: int,
    locationcode: int = Query(0, ge=0),
):
    try:
        loc = None if locationcode in (None, 0) else locationcode
        doc = svc.get_document(print_no, locationcode=loc)
    except ValueError as exc:
        return failure(str(exc), status_code=404)
    return success({"document": doc})


@router.post("", dependencies=[_perm, require_save_nonce])
def save_print_list(request: Request, body: PrintListSaveBody):
    try:
        data = svc.save_document(body.model_dump())
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to save print list.")
    pno = data.get("print_no")
    return success_after_mutation(
        request,
        {"document": data},
        message=f"Print list #{pno} saved",
    )
