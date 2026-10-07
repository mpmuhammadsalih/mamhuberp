"""Catalog routes."""

from __future__ import annotations



from typing import Optional



from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse



from addons.ecommerce import settings_store
from storefront_backend.deps import customer_user_id, location_query, optional_customer

from storefront_backend.services import catalog as catalog_svc
from storefront_backend.services import item_images as item_images_svc
from storefront_backend.services import search_events as search_events_svc

from storefront_backend.utils.response import success_response



router = APIRouter(tags=['Catalog'])





@router.get('/products')

async def list_products(

    response: Response,

    location_code: int = Query(None),

    search: Optional[str] = Query(None),

    page: int = Query(1, ge=1),

    page_size: int = Query(20, ge=1, le=200),

    category_code: Optional[int] = Query(None),

    brand_code: Optional[int] = Query(None),

    stock_filter: Optional[str] = Query(None),

    age: Optional[str] = Query(None),

    interest: Optional[str] = Query(None),

    min_price: Optional[float] = Query(None),

    max_price: Optional[float] = Query(None),

    sort: Optional[str] = Query(None),

    order: Optional[str] = Query(None),

    claims: Optional[dict] = Depends(optional_customer),

):

    loc = location_code if location_code is not None else None
    if stock_filter is None:
        stock_filter = 'all' if settings_store.show_all_items_on_web() else 'in_stock'

    items, meta = catalog_svc.list_products(

        location_code=loc,

        search=search,

        page=page,

        page_size=page_size,

        category_code=category_code,

        brand_code=brand_code,

        stock_filter=stock_filter,

        age_slug=age,

        interest_slug=interest,

        min_price=min_price,

        max_price=max_price,

        sort=sort,

        order=order,

    )

    user_id = None
    if claims:
        try:
            user_id = customer_user_id(claims)
        except Exception:
            user_id = None
    search_events_svc.maybe_log_zero_result(
        query=search,
        total=int((meta or {}).get('total_records') or 0),
        page=page,
        user_id=user_id,
    )

    response.headers['Cache-Control'] = 'public, max-age=60'

    return success_response(data=items, message='Products retrieved successfully', meta=meta)





@router.get('/products/collections/{collection}')

async def get_collection(

    collection: str,

    response: Response,

    location_code: int = Query(None),

    page: int = Query(1, ge=1),

    page_size: int = Query(24, ge=1, le=200),

):

    loc = location_code if location_code is not None else None

    try:

        data, meta = catalog_svc.get_collection(

            collection,

            location_code=loc,

            page=page,

            page_size=page_size,

        )

    except ValueError as exc:

        raise HTTPException(status_code=404, detail=str(exc)) from exc

    response.headers['Cache-Control'] = 'public, max-age=300, must-revalidate'

    return success_response(data=data, message='Collection retrieved successfully', meta=meta)





@router.get('/products/images/{filename}')
async def serve_product_image(filename: str, response: Response):
    path = item_images_svc.resolve_item_image_file(filename)
    if not path:
        raise HTTPException(status_code=404, detail='Image not found')
    response.headers['Cache-Control'] = 'public, max-age=604800, immutable'
    return FileResponse(
        str(path),
        media_type=item_images_svc.item_image_content_type(filename),
    )


@router.get('/products/addons')
async def list_product_addons(
    addon_type: str = Query('gift_wrap'),
    location_code: Optional[int] = Query(None),
):
    items = catalog_svc.list_product_addons(
        location_code=location_code,
        addon_type=addon_type or 'gift_wrap',
    )
    return success_response(data=items, message='Product add-ons retrieved')


@router.get('/products/suggested')
async def list_suggested_products(
    item_code: int = Query(..., gt=0),
    location_code: Optional[int] = Query(None),
    page_size: int = Query(12, ge=1, le=24),
):
    items = catalog_svc.list_suggested_products(
        item_code,
        location_code=location_code,
        limit=page_size,
    )
    return success_response(data=items, message='Suggested products retrieved')


@router.get('/products/{item_code}')

async def get_product(item_code: int, location_code: Optional[int] = Query(None)):

    product = catalog_svc.get_product(item_code, location_code=location_code)

    if not product:

        raise HTTPException(status_code=404, detail='Product not found')

    return success_response(data=product, message='Product retrieved successfully')





@router.get('/categories/tree')

async def category_tree(response: Response, loc: int = Query(None, alias='location_code')):

    tree = catalog_svc.get_category_tree(location_code=loc)

    response.headers['Cache-Control'] = 'public, max-age=60'

    return success_response(data=tree, message='Category tree retrieved successfully')





@router.get('/brands')

async def brands(response: Response):

    data = catalog_svc.list_brands()

    response.headers['Cache-Control'] = 'public, max-age=300'

    return success_response(data=data, message='Brands retrieved successfully')





@router.get('/age-groups')

async def age_groups(response: Response):

    data = catalog_svc.list_age_groups()

    response.headers['Cache-Control'] = 'public, max-age=60'

    return success_response(data=data, message='Age groups retrieved successfully')





@router.get('/interests')

async def interests(response: Response):

    data = catalog_svc.list_interests()

    response.headers['Cache-Control'] = 'public, max-age=300'

    return success_response(data=data, message='Interests retrieved successfully')


