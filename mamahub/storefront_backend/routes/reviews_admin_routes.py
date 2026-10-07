"""Admin review moderation routes."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from storefront_backend.deps import require_admin
from storefront_backend.services import admin_api as admin_svc
from storefront_backend.utils.response import success_response

router = APIRouter(prefix='/reviews/admin', tags=['Admin Reviews'])


class ReviewStatusBody(BaseModel):
    status: str = Field(min_length=3, max_length=20)


@router.get('/pending')
def list_pending_reviews(
    _admin: Annotated[dict, Depends(require_admin)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    data, meta = admin_svc.list_pending_reviews(page=page, page_size=page_size)
    return success_response(data=data, message='Pending reviews retrieved', meta=meta)


@router.patch('/{review_id}/status')
def update_review_status(
    review_id: int,
    payload: ReviewStatusBody,
    _admin: Annotated[dict, Depends(require_admin)],
):
    ok, message = admin_svc.moderate_review(review_id, payload.status)
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    return success_response(data={'review_id': review_id, 'status': payload.status.upper()}, message=message)
