from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from mobile_backend.deps_auth import require_access_claims, require_any_permission
from mobile_backend.services import barcode_lookup_service, label_ai_service
from mobile_backend.services.inventory_service import get_item_store_stock, list_inventory
from mobile_backend.utils.response import failure, success

router = APIRouter(
    prefix="/api/v1/inventory",
    tags=["inventory"],
    dependencies=[Depends(require_access_claims)],
)

_perm = Depends(require_any_permission("itemmaster.productlist", "mobile.stock_lookup"))

_scan_perm = Depends(
    require_any_permission(
        "itemmaster.productlist",
        "mobile.stock_lookup",
        "warehouse.warehouse_stock_counting",
        "warehouse.warehouse_stock_counting_mobile",
        "warehouse.warehouse_stock_verification",
        "sales.sales_invoice",
    )
)


class LabelScanBody(BaseModel):
    image_base64: str = Field(..., min_length=32)
    mime: str = "image/jpeg"
    locationcode: int | None = Field(None, ge=0)


@router.get("", dependencies=[_perm])
def inventory_list(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str = Query("", max_length=200),
    warehouse_id: int | None = Query(
        None,
        ge=1,
        description="When set, returns items from WAREHOUSE_STOCK for this warehouse",
    ),
    locationcode: int | None = Query(
        None,
        ge=0,
        description="Optional branch filter with warehouse_id",
    ),
    include_zero: bool = Query(
        True,
        description="Include zero-qty warehouse stock rows (default true for stock count)",
    ),
):
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    loc = None if locationcode in (None, 0) else locationcode
    data = list_inventory(
        page=page,
        page_size=page_size,
        search=search or "",
        warehouse_id=warehouse_id,
        locationcode=loc,
        include_zero=include_zero,
    )
    return success({
        "page": page,
        "page_size": page_size,
        "warehouse_id": warehouse_id,
        "rows": data,
    })


@router.get("/lookup", dependencies=[_scan_perm])
def inventory_lookup_item(
    query: str = Query(..., min_length=1, max_length=120),
    locationcode: int | None = Query(None, ge=0),
):
    """POS-style scan lookup (MANUFACTURERID, alternate barcode, item code)."""
    try:
        loc = None if locationcode in (None, 0) else locationcode
        item = barcode_lookup_service.lookup_item_row(query, locationcode=loc)
    except ValueError as exc:
        return failure(str(exc), status_code=404)
    return success({"item": item, "query": query.strip()})


_barcode_print_perm = Depends(
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


@router.get("/storage-lookup", dependencies=[_barcode_print_perm])
def inventory_lookup_storage(
    query: str = Query(..., min_length=1, max_length=120),
    locationcode: int | None = Query(None, ge=0),
):
    """Shelf / bin / rack lookup by STORAGE_BARCODE or CODE for label reprint."""
    try:
        loc = None if locationcode in (None, 0) else locationcode
        storage = barcode_lookup_service.lookup_storage_row(query, locationcode=loc)
    except ValueError as exc:
        return failure(str(exc), status_code=404)
    return success({"storage": storage, "query": query.strip()})


@router.get("/label-scan/status", dependencies=[_scan_perm])
def inventory_label_scan_status():
    return success({"openai_configured": label_ai_service.openai_configured()})


@router.post("/label-scan", dependencies=[_scan_perm])
def inventory_label_scan(body: LabelScanBody):
    """AI reads printed barcode text from a label photo (same OpenAI key as ERP POS)."""
    if not label_ai_service.openai_configured():
        return failure(
            "OPENAI_API_KEY is not configured on the server (same as ERP POS).",
            status_code=503,
        )
    try:
        raw, mime = label_ai_service.decode_image_base64(body.image_base64)
        loc = None if body.locationcode in (None, 0) else body.locationcode
        data = label_ai_service.scan_label_and_lookup(raw, mime=body.mime or mime, locationcode=loc)
    except ValueError as exc:
        return failure(str(exc), status_code=400)
    except Exception as exc:
        return failure(str(exc), status_code=500)
    return success(data)


@router.get("/{item_code}/stores", dependencies=[_perm])
def inventory_item_stores(item_code: int):
    rows = get_item_store_stock(item_code)
    return success({"item_code": int(item_code), "stores": rows})
