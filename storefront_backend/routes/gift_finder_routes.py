"""Gift finder routes."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from storefront_backend.services import catalog as catalog_svc
from storefront_backend.utils.response import success_response

router = APIRouter(prefix='/gift-finder', tags=['Gift Finder'])


@router.get('')
async def find_gifts(
    age: Optional[str] = Query(None),
    interest: Optional[str] = Query(None),
    brand_code: Optional[int] = Query(None),
    min_price: Optional[float] = Query(None, ge=0),
    max_price: Optional[float] = Query(None, ge=0),
    occasion: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
):
    items, meta = catalog_svc.list_products(
        age_slug=age,
        interest_slug=interest,
        brand_code=brand_code,
        stock_filter='greater',
        min_price=min_price,
        max_price=max_price,
        page=page,
        page_size=page_size,
        sort='retailprice',
        order='asc',
    )
    return success_response(
        data={
            'filters': {
                'age': age,
                'interest': interest,
                'brand_code': brand_code,
                'min_price': min_price,
                'max_price': max_price,
                'occasion': occasion,
            },
            'results': items,
        },
        message='Gift recommendations retrieved',
        meta=meta,
    )
