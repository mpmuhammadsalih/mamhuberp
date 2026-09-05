"""Review routes."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from storefront_backend.deps import customer_user_id, require_customer
from storefront_backend.services import reviews as reviews_svc
from storefront_backend.utils.response import success_response

router = APIRouter(prefix='/reviews', tags=['Reviews'])


class ReviewCreateBody(BaseModel):
    item_code: int
    rating: int = Field(ge=1, le=5)
    title: Optional[str] = Field(default=None, max_length=200)
    review_text: Optional[str] = Field(default=None, max_length=2000)
    location_code: Optional[int] = None
    order_id: Optional[int] = None


@router.get('/products/{item_code}')
async def list_product_reviews(
    item_code: int,
    location_code: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
):
    rows, meta, summary = reviews_svc.list_product_reviews(
        item_code,
        location_code=location_code,
        page=page,
        page_size=page_size,
    )
    return success_response(
        data={'reviews': rows, 'summary': summary},
        message='Reviews retrieved',
        meta=meta,
    )


@router.post('')
async def submit_review(payload: ReviewCreateBody, claims: dict = Depends(require_customer)):
    user_id = customer_user_id(claims)
    try:
        data = reviews_svc.submit_review(
            user_id,
            item_code=payload.item_code,
            rating=payload.rating,
            title=payload.title,
            review_text=payload.review_text,
            location_code=payload.location_code,
            order_id=payload.order_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return success_response(data=data, message='Review submitted for moderation')
