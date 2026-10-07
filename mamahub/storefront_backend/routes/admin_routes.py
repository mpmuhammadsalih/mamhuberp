"""Admin REST API routes for the React admin SPA."""
from __future__ import annotations

from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from storefront_backend.deps import customer_user_id, require_admin
from storefront_backend.services import admin_api as admin_svc
from addons.ecommerce.services import media as media_svc
from storefront_backend.utils.response import success_response

router = APIRouter(prefix='/admin', tags=['Admin'])


class OrderStatusUpdate(BaseModel):
    status: str = Field(min_length=3, max_length=40)
    notes: Optional[str] = Field(default=None, max_length=500)


class CategorySaveRequest(BaseModel):
    mode: Literal['create', 'update']
    flag: Literal['M', 'D', 'C']
    name: str = Field(min_length=1, max_length=200)
    code: Optional[int] = Field(default=None, ge=1)
    main_code: Optional[int] = Field(default=None, ge=1)
    d_code: Optional[int] = Field(default=None, ge=1)
    location_code: Optional[int] = Field(default=None, ge=1)


class PromotionCreateBody(BaseModel):
    promotion_code: str
    promotion_name: str
    promotion_type: str
    discount_value: float
    min_order_amount: float = 0
    max_discount_amount: Optional[float] = None
    coupon_code: str
    start_date: str
    end_date: str
    usage_limit: Optional[int] = None
    usage_per_customer: int = 1


class PromotionUpdateBody(BaseModel):
    promotion_name: Optional[str] = None
    discount_value: Optional[float] = None
    min_order_amount: Optional[float] = None
    max_discount_amount: Optional[float] = None
    end_date: Optional[str] = None
    usage_limit: Optional[int] = None
    is_active: Optional[bool] = None
    coupon_is_active: Optional[bool] = None


class AssignRoleRequest(BaseModel):
    role_code: str = Field(min_length=2, max_length=50)


class MediaUpsertBody(BaseModel):
    media_id: Optional[int] = None
    placement: str
    ref_key: Optional[str] = None
    title: Optional[str] = None
    subtitle: Optional[str] = None
    image_url: str
    link_url: Optional[str] = None
    alt_text: Optional[str] = None
    sort_order: int = 0
    is_active: bool = True
    meta: Optional[dict] = None


class MediaFetchFromWebBody(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    subtitle: Optional[str] = Field(default=None, max_length=200)
    ref_key: Optional[str] = Field(default=None, max_length=100)
    placement: Optional[str] = Field(default=None, max_length=50)
    source_url: Optional[str] = Field(default=None, max_length=2000)


class MediaSearchFromWebBody(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    subtitle: Optional[str] = Field(default=None, max_length=200)
    ref_key: Optional[str] = Field(default=None, max_length=100)
    placement: Optional[str] = Field(default=None, max_length=50)
    limit: Optional[int] = Field(default=12, ge=4, le=20)


class _UploadAdapter:
    def __init__(self, upload: UploadFile, content: bytes) -> None:
        self.filename = upload.filename
        self._content = content

    def read(self) -> bytes:
        return self._content


@router.get('/dashboard')
def admin_dashboard(_admin: Annotated[dict, Depends(require_admin)]):
    return success_response(data=admin_svc.get_dashboard(), message='Dashboard loaded')


@router.get('/orders')
def admin_list_orders(
    _admin: Annotated[dict, Depends(require_admin)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
):
    data, meta = admin_svc.list_orders(page=page, page_size=page_size, status=status)
    return success_response(data=data, message='Orders retrieved', meta=meta)


@router.get('/orders/{order_id}')
def admin_get_order(order_id: int, _admin: Annotated[dict, Depends(require_admin)]):
    order = admin_svc.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail='Order not found')
    return success_response(data=order, message='Order retrieved')


@router.patch('/orders/{order_id}/status')
def admin_update_order_status(
    order_id: int,
    payload: OrderStatusUpdate,
    admin: Annotated[dict, Depends(require_admin)],
):
    ok, message, order = admin_svc.update_order_status(
        order_id,
        payload.status,
        notes=payload.notes,
        updated_by=customer_user_id(admin),
    )
    if not ok or not order:
        raise HTTPException(status_code=400, detail=message)
    return success_response(data=order, message=message)


@router.get('/products')
def admin_list_products(
    _admin: Annotated[dict, Depends(require_admin)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
):
    data, meta = admin_svc.list_products(page=page, page_size=page_size, search=search)
    return success_response(data=data, message='Products retrieved', meta=meta)


@router.get('/products/{item_code}')
def admin_get_product(item_code: int, _admin: Annotated[dict, Depends(require_admin)]):
    product = admin_svc.get_product(item_code)
    if not product:
        raise HTTPException(status_code=404, detail='Product not found')
    return success_response(data=product, message='Product retrieved')


@router.get('/promotions')
def admin_list_promotions(_admin: Annotated[dict, Depends(require_admin)]):
    return success_response(data=admin_svc.list_promotions(), message='Promotions retrieved')


@router.post('/promotions')
def admin_create_promotion(
    payload: PromotionCreateBody,
    _admin: Annotated[dict, Depends(require_admin)],
):
    ok, message, promo = admin_svc.create_promotion(payload.model_dump())
    if not ok or not promo:
        raise HTTPException(status_code=400, detail=message)
    return success_response(data=promo, message=message)


@router.patch('/promotions/{promotion_id}')
def admin_update_promotion(
    promotion_id: int,
    payload: PromotionUpdateBody,
    _admin: Annotated[dict, Depends(require_admin)],
):
    ok, message, promo = admin_svc.update_promotion(
        promotion_id,
        payload.model_dump(exclude_unset=True),
    )
    if not ok or not promo:
        raise HTTPException(status_code=400, detail=message)
    return success_response(data=promo, message=message)


@router.get('/inventory')
def admin_list_inventory(
    _admin: Annotated[dict, Depends(require_admin)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    low_stock_only: bool = Query(False),
    search: Optional[str] = Query(None),
):
    data, meta = admin_svc.list_inventory(
        page=page,
        page_size=page_size,
        low_stock_only=low_stock_only,
        search=search,
    )
    return success_response(data=data, message='Inventory retrieved', meta=meta)


@router.get('/users')
def admin_list_users(
    _admin: Annotated[dict, Depends(require_admin)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    data, meta = admin_svc.list_staff_users(page=page, page_size=page_size)
    return success_response(data=data, message='Users retrieved', meta=meta)


@router.get('/roles')
def admin_list_roles(_admin: Annotated[dict, Depends(require_admin)]):
    return success_response(data=admin_svc.list_roles(), message='Roles retrieved')


@router.post('/users/{user_id}/roles')
def admin_assign_role(
    user_id: int,
    payload: AssignRoleRequest,
    _admin: Annotated[dict, Depends(require_admin)],
):
    ok, message, data = admin_svc.assign_user_role(user_id, payload.role_code)
    if not ok or not data:
        raise HTTPException(status_code=400, detail=message)
    return success_response(data=data, message=message)


@router.get('/customers')
def admin_list_customers(
    _admin: Annotated[dict, Depends(require_admin)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    data, meta = admin_svc.list_customers(page=page, page_size=page_size)
    return success_response(data=data, message='Customers retrieved', meta=meta)


@router.get('/media')
def admin_list_media(
    _admin: Annotated[dict, Depends(require_admin)],
    placement: Optional[str] = Query(None),
):
    return success_response(data=admin_svc.list_media(placement=placement), message='Media retrieved')


@router.post('/media/upload')
async def admin_upload_media(
    _admin: Annotated[dict, Depends(require_admin)],
    file: UploadFile = File(...),
):
    content = await file.read()
    ok, message, image_url = media_svc.save_upload(_UploadAdapter(file, content))
    if not ok or not image_url:
        raise HTTPException(status_code=400, detail=message)
    filename = image_url.rsplit('/', 1)[-1]
    return success_response(
        data={'filename': filename, 'image_url': image_url},
        message=message,
    )


@router.post('/media/search-from-web')
def admin_search_media_from_web(
    payload: MediaSearchFromWebBody,
    _admin: Annotated[dict, Depends(require_admin)],
):
    result = media_svc.search_images_from_web_by_title(
        payload.title,
        subtitle=payload.subtitle or '',
        ref_key=payload.ref_key or '',
        placement=payload.placement or '',
        limit=payload.limit or 12,
    )
    if not result.get('ok'):
        raise HTTPException(status_code=422, detail=result.get('error') or 'Web search failed.')
    return success_response(
        data={
            'query': result.get('query'),
            'candidates': result.get('candidates') or [],
        },
        message=str(result.get('message') or 'Image options found'),
    )


@router.post('/media/fetch-from-web')
def admin_fetch_media_from_web(
    payload: MediaFetchFromWebBody,
    _admin: Annotated[dict, Depends(require_admin)],
):
    result = media_svc.fetch_image_from_web_by_title(
        payload.title,
        subtitle=payload.subtitle or '',
        ref_key=payload.ref_key or '',
        placement=payload.placement or '',
        source_url=payload.source_url,
    )
    if not result.get('ok'):
        raise HTTPException(status_code=422, detail=result.get('error') or 'Web fetch failed.')
    return success_response(
        data={'image_url': result.get('image_url'), 'query': result.get('query')},
        message=str(result.get('message') or 'Image fetched from web'),
    )


@router.post('/media')
def admin_upsert_media(payload: MediaUpsertBody, _admin: Annotated[dict, Depends(require_admin)]):
    ok, message, row = admin_svc.upsert_media(payload.model_dump())
    if not ok or not row:
        raise HTTPException(status_code=400, detail=message)
    return success_response(data=row, message=message)


@router.delete('/media/{media_id}')
def admin_delete_media(media_id: int, _admin: Annotated[dict, Depends(require_admin)]):
    ok, message = admin_svc.deactivate_media(media_id)
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    return success_response(data={'media_id': media_id}, message=message)


@router.post('/categories')
def admin_save_category(payload: CategorySaveRequest, _admin: Annotated[dict, Depends(require_admin)]):
    ok, message, data = admin_svc.save_category(payload.model_dump())
    if not ok or not data:
        raise HTTPException(status_code=400, detail=message)
    return success_response(data=data, message=message)
