"""Search routes."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from storefront_backend.services import catalog as catalog_svc
from storefront_backend.utils.response import success_response

router = APIRouter(prefix='/search', tags=['Search'])


@router.get('/products')
async def search_products(
    q: str = Query(..., min_length=1),
    location_code: Optional[int] = Query(None),
    brand_code: Optional[int] = Query(None),
    category_code: Optional[int] = Query(None),
    age: Optional[str] = Query(None),
    interest: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    items, meta = catalog_svc.list_products(
        location_code=location_code,
        search=q,
        brand_code=brand_code,
        category_code=category_code,
        age_slug=age,
        interest_slug=interest,
        page=page,
        page_size=page_size,
        sort='itemname',
        order='asc',
    )
    return success_response(
        data={'query': q, 'results': items},
        message='Search completed successfully',
        meta=meta,
    )


@router.get('/suggest')
async def search_suggestions(
    q: str = Query(..., min_length=1, max_length=80),
    limit: int = Query(8, ge=1, le=20),
):
    items, _ = catalog_svc.list_products(
        search=q,
        page=1,
        page_size=limit,
        sort='itemname',
        order='asc',
    )
    suggestions = [
        {
            'item_code': i.get('item_code'),
            'item_name': i.get('item_name'),
            'brand_name': i.get('brand_name'),
            'primary_image_url': i.get('primary_image_url'),
        }
        for i in items
    ]
    return success_response(
        data={'query': q, 'suggestions': suggestions},
        message='Suggestions retrieved',
    )
