"""Customer order routes."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from storefront_backend.deps import customer_user_id, require_customer
from storefront_backend.services import orders as orders_svc
from storefront_backend.utils.response import build_pagination_meta, success_response

router = APIRouter(prefix='/orders', tags=['Orders'])


@router.get('')
async def list_orders(
    claims: dict = Depends(require_customer),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    user_id = customer_user_id(claims)
    data, total = orders_svc.list_orders(user_id, page=page, page_size=page_size)
    meta = build_pagination_meta(page=page, page_size=page_size, total_records=total)
    return success_response(data=data, message='Orders retrieved successfully', meta=meta)


@router.get('/track/{order_number}')
async def track_order(order_number: str, claims: dict = Depends(require_customer)):
    user_id = customer_user_id(claims)
    data = orders_svc.track_order(user_id, order_number)
    if not data:
        raise HTTPException(status_code=404, detail='Order not found')
    return success_response(data=data, message='Order tracking retrieved')


@router.get('/{order_id}')
async def get_order(order_id: int, claims: dict = Depends(require_customer)):
    user_id = customer_user_id(claims)
    data = orders_svc.get_order(user_id, order_id)
    if not data:
        raise HTTPException(status_code=404, detail='Order not found')
    return success_response(data=data, message='Order retrieved successfully')


@router.post('/{order_id}/cancel')
async def cancel_order(
    order_id: int,
    claims: dict = Depends(require_customer),
    reason: Optional[str] = Query(None),
):
    user_id = customer_user_id(claims)
    ok, message, data = orders_svc.cancel_order(user_id, order_id, reason=reason)
    if not ok or not data:
        status = 404 if message == 'Order not found' else 400
        raise HTTPException(status_code=status, detail=message)
    return success_response(data=data, message='Order cancelled')
