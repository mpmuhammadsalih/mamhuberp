"""Cart routes."""
from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from storefront_backend.deps import customer_user_id, guest_cart_token, optional_customer
from storefront_backend.services import cart as cart_svc
from storefront_backend.utils.response import success_response

router = APIRouter(prefix='/cart', tags=['Cart'])


class CartItemAddBody(BaseModel):
    item_code: int
    quantity: float = Field(gt=0)
    location_code: Optional[int] = None


class CartItemUpdateBody(BaseModel):
    quantity: float = Field(gt=0)


class CartCouponBody(BaseModel):
    coupon_code: str = Field(min_length=2, max_length=50)


@router.get('')
def get_cart(
    claims: Optional[dict] = Depends(optional_customer),
    guest_token: Annotated[Optional[str], Depends(guest_cart_token)] = None,
    location_code: Optional[int] = Query(None),
):
    user_id = customer_user_id(claims) if claims else None
    data = cart_svc.get_cart(user_id=user_id, guest_token=guest_token, location_code=location_code)
    return success_response(data=data, message='Cart retrieved successfully')


@router.post('/items')
def add_cart_item(
    payload: CartItemAddBody,
    claims: Optional[dict] = Depends(optional_customer),
    guest_token: Annotated[Optional[str], Depends(guest_cart_token)] = None,
):
    user_id = customer_user_id(claims) if claims else None
    ok, message, data = cart_svc.add_item(
        item_code=payload.item_code,
        quantity=payload.quantity,
        user_id=user_id,
        guest_token=guest_token,
        location_code=payload.location_code,
    )
    if not ok or not data:
        raise HTTPException(status_code=400, detail=message)
    return success_response(data=data, message=message)


@router.post('/coupon')
def apply_cart_coupon(
    payload: CartCouponBody,
    claims: Optional[dict] = Depends(optional_customer),
    guest_token: Annotated[Optional[str], Depends(guest_cart_token)] = None,
):
    user_id = customer_user_id(claims) if claims else None
    ok, message, data = cart_svc.apply_coupon(
        coupon_code=payload.coupon_code,
        user_id=user_id,
        guest_token=guest_token,
    )
    if not ok or not data:
        raise HTTPException(status_code=400, detail=message)
    return success_response(data=data, message=message)


@router.patch('/items/{cart_item_id}')
def update_cart_item(
    cart_item_id: int,
    payload: CartItemUpdateBody,
    claims: Optional[dict] = Depends(optional_customer),
    guest_token: Annotated[Optional[str], Depends(guest_cart_token)] = None,
):
    user_id = customer_user_id(claims) if claims else None
    ok, message, data = cart_svc.update_item_quantity(
        cart_item_id=cart_item_id,
        quantity=payload.quantity,
        user_id=user_id,
        guest_token=guest_token,
    )
    if not ok or not data:
        raise HTTPException(status_code=400, detail=message)
    return success_response(data=data, message=message)


@router.delete('/items/{cart_item_id}')
def remove_cart_item(
    cart_item_id: int,
    claims: Optional[dict] = Depends(optional_customer),
    guest_token: Annotated[Optional[str], Depends(guest_cart_token)] = None,
):
    user_id = customer_user_id(claims) if claims else None
    ok, message, data = cart_svc.remove_item(
        cart_item_id=cart_item_id,
        user_id=user_id,
        guest_token=guest_token,
    )
    if not ok or not data:
        raise HTTPException(status_code=400, detail=message)
    return success_response(data=data, message=message)
