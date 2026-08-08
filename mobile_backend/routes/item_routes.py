from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, Path, Query, Request
from fastapi.responses import FileResponse

from mobile_backend.deps_auth import require_access_claims, require_any_permission
from mobile_backend.deps_save import require_save_nonce, success_after_mutation
from mobile_backend.mutation_errors import failure_from_mutation_exc
from mobile_backend.request_context import get_jwt
from mobile_backend.services import item_master_service as items
from mobile_backend.utils.response import failure, success

router = APIRouter(
    prefix="/api/v1/item",
    tags=["item"],
    dependencies=[Depends(require_access_claims)],
)

_master_perm = Depends(
    require_any_permission(
        "itemmaster.productlist",
        "itemmaster.itemmaster",
        "itemmaster.itemmaster_save",
        "mobile.items",
        "mobile.item",
    )
)


@router.get("/masters/open", dependencies=[_master_perm])
def item_masters_open():
    try:
        data = items.get_open_context()
    except Exception as exc:
        return failure(str(exc) or "Failed to open item form.", status_code=400)
    return success(data)


@router.get("/masters", dependencies=[_master_perm])
def item_masters_list(
    q: str = Query(""),
    limit: int = Query(100, ge=1, le=300),
    category_code: Optional[int] = Query(None),
    brand_code: Optional[int] = Query(None),
    supplier_code: Optional[int] = Query(None),
    stock_filter: str = Query(""),
):
    try:
        data = items.list_items(
            search=q,
            limit=limit,
            category_code=category_code,
            brand_code=brand_code,
            supplier_code=supplier_code,
            stock_filter=stock_filter,
        )
    except Exception as exc:
        return failure(str(exc) or "Failed to list items.", status_code=400)
    return success(data)


@router.get("/masters/{item_code}", dependencies=[_master_perm])
def item_masters_detail(item_code: int = Path(..., ge=1)):
    try:
        data = items.get_item_detail(item_code)
    except Exception as exc:
        return failure(str(exc) or "Failed to load item.", status_code=400)
    return success(data)


@router.get("/masters/{item_code}/image", dependencies=[_master_perm])
def item_masters_image(item_code: int = Path(..., ge=1)):
    try:
        path, mime = items.resolve_item_image_file(item_code)
    except FileNotFoundError as exc:
        return failure(str(exc) or "Image not found.", status_code=404)
    except Exception as exc:
        return failure(str(exc) or "Failed to load image.", status_code=400)
    return FileResponse(path, media_type=mime, filename=path.name)


@router.post("/masters", dependencies=[_master_perm, require_save_nonce])
def item_masters_create(request: Request, payload: dict[str, Any] = Body(default_factory=dict)):
    claims = get_jwt()
    username = str(claims.get("sub") or "mobile").strip() or "mobile"
    try:
        data = items.create_item(payload, username=username)
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to save item.")
    return success_after_mutation(
        request,
        data,
        message=data.get("message") or "Item saved",
        status_code=201,
    )


@router.put("/masters/{item_code}", dependencies=[_master_perm, require_save_nonce])
def item_masters_update(
    request: Request,
    item_code: int = Path(..., ge=1),
    payload: dict[str, Any] = Body(default_factory=dict),
):
    claims = get_jwt()
    username = str(claims.get("sub") or "mobile").strip() or "mobile"
    try:
        data = items.update_item(item_code, payload, username=username)
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to update item.")
    return success_after_mutation(
        request,
        data,
        message=data.get("message") or "Item updated",
    )
