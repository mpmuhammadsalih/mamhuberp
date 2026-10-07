"""Checkout routes."""
from __future__ import annotations

import json
from typing import Annotated, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from storefront_backend.deps import customer_user_id, guest_cart_token, require_customer
from storefront_backend.services import checkout as checkout_svc
from storefront_backend.utils.response import success_response

router = APIRouter(prefix='/checkout', tags=['Checkout'])


class CheckoutDeliveryBody(BaseModel):
    address_id: int = Field(gt=0)
    delivery_zone_id: int = Field(gt=0)
    delivery_slot_id: int = Field(gt=0)


class CheckoutPickupBody(BaseModel):
    pickup_store_id: int = Field(gt=0)


class CouponApplyBody(BaseModel):
    coupon_code: str = Field(min_length=2, max_length=50)


class LoyaltyRedeemBody(BaseModel):
    points: int = Field(ge=10)


class GiftWrapBody(BaseModel):
    gift_wrap_code: str = Field(min_length=1, max_length=40)


class CheckoutConfirmBody(BaseModel):
    customer_notes: Optional[str] = Field(default=None, max_length=1000)
    payment_method: str = Field(default='COD', max_length=30)
    pickup_store_id: Optional[int] = Field(default=None, gt=0)
    address_id: Optional[int] = Field(default=None, gt=0)
    delivery_zone_id: Optional[int] = Field(default=None, gt=0)
    delivery_slot_id: Optional[int] = Field(default=None, gt=0)
    gift_wrap_code: Optional[str] = Field(default=None, max_length=40)


class TapInitBody(CheckoutConfirmBody):
    pass


class TapCompleteBody(BaseModel):
    tap_id: str = Field(min_length=5)


def _handle(exc: Exception) -> HTTPException:
    message = str(exc)
    status = 404 if 'not found' in message.lower() else 400
    return HTTPException(status_code=status, detail=message)


@router.post('/start')
def start_checkout(
    claims: dict = Depends(require_customer),
    guest_token: Annotated[Optional[str], Depends(guest_cart_token)] = None,
):
    user_id = customer_user_id(claims)
    try:
        data = checkout_svc.start_checkout(user_id=user_id, guest_token=guest_token)
    except ValueError as exc:
        raise _handle(exc) from exc
    return success_response(data=data, message='Checkout started')


@router.post('/delivery')
def set_delivery(payload: CheckoutDeliveryBody, claims: dict = Depends(require_customer)):
    user_id = customer_user_id(claims)
    try:
        data = checkout_svc.set_delivery(
            user_id=user_id,
            address_id=payload.address_id,
            delivery_zone_id=payload.delivery_zone_id,
            delivery_slot_id=payload.delivery_slot_id,
        )
    except ValueError as exc:
        raise _handle(exc) from exc
    return success_response(data=data, message='Delivery options saved')


@router.post('/pickup')
def set_pickup(payload: CheckoutPickupBody, claims: dict = Depends(require_customer)):
    user_id = customer_user_id(claims)
    try:
        data = checkout_svc.set_pickup(user_id=user_id, pickup_store_id=payload.pickup_store_id)
    except ValueError as exc:
        raise _handle(exc) from exc
    return success_response(data=data, message='Pickup store selected')


@router.post('/coupon')
async def apply_coupon(payload: CouponApplyBody, claims: dict = Depends(require_customer)):
    user_id = customer_user_id(claims)
    try:
        data = checkout_svc.apply_coupon(user_id=user_id, coupon_code=payload.coupon_code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return success_response(data=data, message='Coupon applied')


@router.post('/gift-wrap')
def set_gift_wrap(payload: GiftWrapBody, claims: dict = Depends(require_customer)):
    user_id = customer_user_id(claims)
    try:
        data = checkout_svc.set_gift_wrap(user_id=user_id, gift_wrap_code=payload.gift_wrap_code)
    except ValueError as exc:
        raise _handle(exc) from exc
    return success_response(data=data, message='Gift wrap saved')


@router.post('/loyalty-points')
async def apply_loyalty_points(payload: LoyaltyRedeemBody, claims: dict = Depends(require_customer)):
    user_id = customer_user_id(claims)
    try:
        data = checkout_svc.apply_loyalty_points(user_id=user_id, points=payload.points)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return success_response(data=data, message='Loyalty points applied')


@router.get('/review')
def review_checkout(claims: dict = Depends(require_customer)):
    user_id = customer_user_id(claims)
    data = checkout_svc.review(user_id=user_id)
    return success_response(data=data, message='Checkout review')


@router.get('/payment-methods')
async def list_payment_methods():
    data = checkout_svc.list_payment_methods()
    return success_response(data=data, message='Payment methods retrieved')


@router.post('/confirm')
def confirm_checkout(
    payload: CheckoutConfirmBody,
    background_tasks: BackgroundTasks,
    claims: dict = Depends(require_customer),
):
    user_id = customer_user_id(claims)
    if (payload.payment_method or 'COD').upper() == 'TAP':
        raise HTTPException(
            status_code=400,
            detail='Use POST /checkout/payment/tap/init for online card payment.',
        )
    try:
        data, side_effects = checkout_svc.place_order(
            user_id=user_id,
            customer_notes=payload.customer_notes,
            payment_method=payload.payment_method,
            pickup_store_id=payload.pickup_store_id,
            address_id=payload.address_id,
            delivery_zone_id=payload.delivery_zone_id,
            delivery_slot_id=payload.delivery_slot_id,
            gift_wrap_code=payload.gift_wrap_code,
        )
        background_tasks.add_task(checkout_svc.complete_order_side_effects, **side_effects)
    except ValueError as exc:
        raise _handle(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return success_response(data=data, message='Order placed successfully')


@router.post('/payment/tap/init')
def init_tap_payment(payload: TapInitBody, claims: dict = Depends(require_customer)):
    user_id = customer_user_id(claims)
    try:
        data = checkout_svc.init_tap_payment(
            user_id=user_id,
            customer_notes=payload.customer_notes,
            pickup_store_id=payload.pickup_store_id,
            address_id=payload.address_id,
            delivery_zone_id=payload.delivery_zone_id,
            delivery_slot_id=payload.delivery_slot_id,
            gift_wrap_code=payload.gift_wrap_code,
        )
    except ValueError as exc:
        raise _handle(exc) from exc
    return success_response(data=data, message='Tap checkout started')


@router.post('/payment/tap/complete')
def complete_tap_payment(
    payload: TapCompleteBody,
    background_tasks: BackgroundTasks,
    claims: dict = Depends(require_customer),
):
    user_id = customer_user_id(claims)
    try:
        data, side_effects = checkout_svc.complete_tap_payment(
            charge_id=payload.tap_id,
            user_id=user_id,
        )
        if side_effects:
            background_tasks.add_task(checkout_svc.complete_order_side_effects, **side_effects)
    except ValueError as exc:
        raise _handle(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return success_response(data=data, message='Payment confirmed')


@router.post('/payment/tap/webhook')
async def tap_payment_webhook(request: Request, background_tasks: BackgroundTasks):
    raw = await request.body()
    try:
        payload = json.loads(raw.decode('utf-8') or '{}')
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail='Invalid JSON body') from exc
    hashstring = request.headers.get('hashstring') or request.headers.get('Hashstring') or ''
    try:
        result = checkout_svc.handle_tap_webhook(charge=payload, hashstring=hashstring)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result:
        _data, side_effects = result
        background_tasks.add_task(checkout_svc.complete_order_side_effects, **side_effects)
    return success_response(data={'received': True}, message='Webhook processed')
