"""Wishlist routes."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from storefront_backend.deps import customer_user_id, require_customer
from storefront_backend.services import wishlist as wishlist_svc
from storefront_backend.utils.response import success_response

router = APIRouter(prefix='/wishlist', tags=['Wishlist'])


class WishlistItemAddBody(BaseModel):
    item_code: int
    location_code: Optional[int] = None


@router.get('')
async def get_wishlist(claims: dict = Depends(require_customer)):
    user_id = customer_user_id(claims)
    data = wishlist_svc.get_wishlist(user_id)
    return success_response(data=data, message='Wishlist retrieved successfully')


@router.post('/items')
async def add_wishlist_item(payload: WishlistItemAddBody, claims: dict = Depends(require_customer)):
    user_id = customer_user_id(claims)
    ok, message, data = wishlist_svc.add_item(
        user_id,
        item_code=payload.item_code,
        location_code=payload.location_code,
    )
    if not ok or not data:
        raise HTTPException(status_code=400, detail=message)
    return success_response(data=data, message=message)


@router.delete('/items/{wishlist_item_id}')
async def remove_wishlist_item(wishlist_item_id: int, claims: dict = Depends(require_customer)):
    user_id = customer_user_id(claims)
    ok, message, data = wishlist_svc.remove_item(user_id, wishlist_item_id)
    if not ok or not data:
        status = 404 if 'not found' in message.lower() else 400
        raise HTTPException(status_code=status, detail=message)
    return success_response(data=data, message=message)


@router.post('/items/{wishlist_item_id}/move-to-cart')
async def move_wishlist_item_to_cart(wishlist_item_id: int, claims: dict = Depends(require_customer)):
    user_id = customer_user_id(claims)
    ok, message, wishlist, cart = wishlist_svc.move_to_cart(user_id, wishlist_item_id)
    if not ok or not wishlist or not cart:
        status = 404 if 'not found' in message.lower() else 400
        raise HTTPException(status_code=status, detail=message)
    return success_response(
        data={'wishlist': wishlist, 'cart': cart},
        message='Item moved to cart',
    )
