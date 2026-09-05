"""Checkout orchestration — cart to order."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from db import _get_connection, _safe_rows, _table_exists

from storefront_backend.services import addresses as address_svc
from storefront_backend.services import auth as auth_svc
from storefront_backend.services import cart as cart_svc
from storefront_backend.services import delivery as delivery_svc
from storefront_backend.services import loyalty as loyalty_svc
from storefront_backend.services import notifications as notification_svc
from storefront_backend.services import order_notifications as order_notify_svc
from storefront_backend.services import orders as orders_svc
from storefront_backend.services import payment as payment_svc
from storefront_backend.services import promotions as promo_svc
from storefront_backend.services import session_store
from storefront_backend.services import tap as tap_svc
from storefront_backend.services.payment import PaymentResult

try:
    from addons.ecommerce import settings_store as ecommerce_settings
except ImportError:  # pragma: no cover
    ecommerce_settings = None


def _coupons_enabled() -> bool:
    if ecommerce_settings is None:
        return False
    return ecommerce_settings.coupons_enabled()


def _tax_rate() -> float:
    raw = os.getenv('TAX_RATE', '0').strip()
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 0.0


def _reservation_ttl_minutes() -> int:
    raw = os.getenv('RESERVATION_TTL_MINUTES', '30').strip()
    try:
        return max(5, int(raw))
    except ValueError:
        return 30


def _require_session(user_id: int) -> dict[str, Any]:
    session = session_store.get_session(user_id)
    if session:
        return session
    cart_id = cart_svc.get_active_cart_id(user_id=user_id)
    if not cart_id:
        raise ValueError('Cart is empty')
    cart = cart_svc.get_cart_for_checkout(cart_id=cart_id)
    if not cart.get('items'):
        raise ValueError('Cart is empty')
    session_store.set_session(
        user_id,
        {
            'cart_id': cart_id,
            'fulfillment_type': None,
        },
    )
    session = session_store.get_session(user_id)
    if not session:
        raise ValueError('Checkout not started. Call POST /checkout/start first.')
    return session


def _cart_coupon_discount(cart_id: int) -> float:
    if not _table_exists('MH_CART_COUPON'):
        return 0.0
    rows = _safe_rows(
        """
        SELECT NVL(SUM(DISCOUNT_AMOUNT), 0) AS discount_total
        FROM MH_CART_COUPON
        WHERE CART_ID = :cart_id
        """,
        {'cart_id': int(cart_id)},
    )
    return float(rows[0]['discount_total']) if rows else 0.0


def _reserve_cart_items(
    *,
    cart_id: int,
    user_id: int,
    items: list[dict[str, Any]],
) -> None:
    if not _table_exists('MH_INVENTORY_RESERVATION'):
        return
    expires = (
        datetime.now(timezone.utc) + timedelta(minutes=_reservation_ttl_minutes())
    ).replace(tzinfo=None)
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE MH_INVENTORY_RESERVATION
                SET RESERVATION_STATUS = 'RELEASED'
                WHERE CART_ID = :cart_id AND RESERVATION_STATUS = 'ACTIVE'
                """,
                {'cart_id': int(cart_id)},
            )
            for item in items:
                cur.execute('SELECT SEQ_MH_RESERVATION_ID.NEXTVAL AS id FROM DUAL')
                reservation_id = int((cur.fetchone() or [0])[0])
                cur.execute(
                    """
                    INSERT INTO MH_INVENTORY_RESERVATION (
                        RESERVATION_ID, CART_ID, USER_ID, LOCATION_CODE, ITEM_CODE,
                        QUANTITY, RESERVATION_STATUS, EXPIRES_AT, CREATED_AT, CREATED_BY
                    ) VALUES (
                        :reservation_id, :cart_id, :user_id, :location_code, :item_code,
                        :quantity, 'ACTIVE', :expires_at, SYSTIMESTAMP, :created_by
                    )
                    """,
                    {
                        'reservation_id': reservation_id,
                        'cart_id': int(cart_id),
                        'user_id': user_id,
                        'location_code': int(item['location_code']),
                        'item_code': int(item['item_code']),
                        'quantity': item['quantity'],
                        'expires_at': expires,
                        'created_by': user_id,
                    },
                )
        conn.commit()


def _convert_reservations(cart_id: int, order_id: int) -> None:
    if not _table_exists('MH_INVENTORY_RESERVATION'):
        return
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE MH_INVENTORY_RESERVATION
                SET RESERVATION_STATUS = 'CONVERTED', ORDER_ID = :order_id
                WHERE CART_ID = :cart_id AND RESERVATION_STATUS = 'ACTIVE'
                """,
                {'cart_id': int(cart_id), 'order_id': int(order_id)},
            )
        conn.commit()


def _set_cart_status(cart_id: int, status: str) -> None:
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE MH_CART
                SET CART_STATUS = :status, MODIFIED_AT = SYSTIMESTAMP
                WHERE CART_ID = :cart_id
                """,
                {'status': status, 'cart_id': int(cart_id)},
            )
        conn.commit()


def list_payment_methods() -> list[dict[str, str]]:
    return payment_svc.list_payment_methods()


def start_checkout(*, user_id: int, guest_token: Optional[str] = None) -> dict[str, Any]:
    cart_data = cart_svc.get_cart(user_id=user_id, guest_token=guest_token)
    if not cart_data.get('items'):
        raise ValueError('Cart is empty')

    cart_id = int(cart_data['cart_id'])
    _set_cart_status(cart_id, 'CHECKOUT')

    reservation_items = [
        {
            'location_code': item['location_code'],
            'item_code': item['item_code'],
            'quantity': item['quantity'],
        }
        for item in cart_data['items']
    ]
    _reserve_cart_items(cart_id=cart_id, user_id=user_id, items=reservation_items)

    session_store.set_session(
        user_id,
        {
            'cart_id': cart_id,
            'fulfillment_type': None,
        },
    )
    return review(user_id=user_id)


def set_delivery(
    *,
    user_id: int,
    address_id: int,
    delivery_zone_id: int,
    delivery_slot_id: int,
) -> dict[str, Any]:
    _require_session(user_id)
    address = address_svc.get_address(user_id, address_id)
    if not address:
        raise ValueError('Address not found')
    zone = delivery_svc.get_zone(delivery_zone_id)
    slot = delivery_svc.get_slot(delivery_slot_id)
    if not zone or not slot:
        raise ValueError('Delivery zone or slot not found')

    session_store.update_session(
        user_id,
        {
            'fulfillment_type': 'DELIVERY',
            'address_id': address_id,
            'delivery_zone_id': delivery_zone_id,
            'delivery_slot_id': delivery_slot_id,
            'pickup_store_id': None,
        },
    )
    return {
        'fulfillment': {
            'type': 'DELIVERY',
            'address_id': address_id,
            'delivery_zone_id': delivery_zone_id,
            'delivery_slot_id': delivery_slot_id,
        },
    }


def set_pickup(*, user_id: int, pickup_store_id: int) -> dict[str, Any]:
    _require_session(user_id)
    store = delivery_svc.get_pickup_store(pickup_store_id)
    if not store:
        raise ValueError('Pickup store not found')
    session_store.update_session(
        user_id,
        {
            'fulfillment_type': 'PICKUP',
            'pickup_store_id': pickup_store_id,
            'address_id': None,
            'delivery_zone_id': None,
            'delivery_slot_id': None,
        },
    )
    return {
        'fulfillment': {
            'type': 'PICKUP',
            'pickup_store_id': pickup_store_id,
        },
    }


def apply_coupon(*, user_id: int, coupon_code: str) -> dict[str, Any]:
    if not _coupons_enabled():
        raise ValueError('Coupons are not enabled for this store')
    ok, message, data = cart_svc.apply_coupon(coupon_code=coupon_code, user_id=user_id)
    if not ok or not data:
        raise ValueError(message)
    session = session_store.get_session(user_id)
    if session:
        promo = data.get('coupon') or {}
        session_store.update_session(
            user_id,
            {
                'coupon_code': promo.get('coupon_code'),
                'coupon_id': promo.get('coupon_id'),
            },
        )
        return review(user_id=user_id)
    return data


def apply_loyalty_points(*, user_id: int, points: int) -> dict[str, Any]:
    _require_session(user_id)
    cart_data = cart_svc.get_cart(user_id=user_id)
    subtotal = float(cart_data['summary']['subtotal'])
    discount = float(cart_data['summary'].get('discount_total') or 0)
    discount_amount = loyalty_svc.validate_redeem(
        user_id=user_id,
        points=points,
        order_subtotal=subtotal,
        existing_discount=discount,
    )
    session_store.update_session(
        user_id,
        {
            'loyalty_points_redeemed': points,
            'loyalty_discount': discount_amount,
        },
    )
    return review(user_id=user_id)


def _compute_pricing(session: dict[str, Any], cart_data: dict[str, Any]) -> dict[str, Any]:
    subtotal = float(cart_data['summary']['subtotal'])
    discount = float(cart_data['summary'].get('discount_total') or 0)
    loyalty_discount = float(session.get('loyalty_discount') or 0)
    delivery_fee = 0.0

    if session.get('fulfillment_type') == 'DELIVERY':
        zone = delivery_svc.get_zone(int(session['delivery_zone_id']))
        if zone:
            delivery_fee = float(zone.get('delivery_fee') or 0)
            threshold = zone.get('free_delivery_threshold')
            if threshold and subtotal - discount >= float(threshold):
                delivery_fee = 0.0

    taxable = max(subtotal - discount - loyalty_discount, 0)
    tax_total = round(taxable * _tax_rate(), 2)
    grand_total = round(taxable + tax_total + delivery_fee, 2)
    return {
        'subtotal': subtotal,
        'discount_total': discount,
        'loyalty_discount': loyalty_discount,
        'delivery_fee': delivery_fee,
        'tax_total': tax_total,
        'grand_total': grand_total,
    }


def _cart_item_name(item: dict[str, Any]) -> str:
    product = item.get('product') or {}
    name = product.get('item_name')
    if name and str(name).strip():
        return str(name).strip()
    return f"Item {item.get('item_code')}"


def review(*, user_id: int) -> dict[str, Any]:
    session = session_store.get_session(user_id) or {}
    cart_data = cart_svc.get_cart(user_id=user_id)
    pricing = _compute_pricing(session, cart_data)

    fulfillment: dict[str, Any] = {'type': session.get('fulfillment_type')}
    if session.get('fulfillment_type') == 'DELIVERY':
        fulfillment.update({
            'address_id': session.get('address_id'),
            'delivery_zone_id': session.get('delivery_zone_id'),
            'delivery_slot_id': session.get('delivery_slot_id'),
        })
    elif session.get('fulfillment_type') == 'PICKUP':
        fulfillment['pickup_store_id'] = session.get('pickup_store_id')

    loyalty_info = loyalty_svc.checkout_loyalty_info(
        user_id=user_id,
        order_subtotal=pricing['subtotal'],
        existing_discount=pricing['discount_total'],
        session=session,
    )

    payload = {
        'cart': cart_data,
        'fulfillment': fulfillment,
        'pricing': {
            **pricing,
            'currency_code': cart_data['summary']['currency_code'],
        },
        'payment_methods': list_payment_methods(),
        'coupons_enabled': _coupons_enabled(),
    }
    if loyalty_info:
        payload['loyalty'] = loyalty_info
    return payload


def _apply_fulfillment_from_confirm(
    *,
    user_id: int,
    pickup_store_id: Optional[int] = None,
    address_id: Optional[int] = None,
    delivery_zone_id: Optional[int] = None,
    delivery_slot_id: Optional[int] = None,
) -> None:
    if pickup_store_id:
        store = delivery_svc.get_pickup_store(int(pickup_store_id))
        if not store:
            raise ValueError('Pickup store not found')
        session_store.update_session(
            user_id,
            {
                'fulfillment_type': 'PICKUP',
                'pickup_store_id': int(pickup_store_id),
                'address_id': None,
                'delivery_zone_id': None,
                'delivery_slot_id': None,
            },
        )
        return

    if address_id and delivery_zone_id and delivery_slot_id:
        address = address_svc.get_address(user_id, int(address_id))
        if not address:
            raise ValueError('Address not found')
        zone = delivery_svc.get_zone(int(delivery_zone_id))
        slot = delivery_svc.get_slot(int(delivery_slot_id))
        if not zone or not slot:
            raise ValueError('Delivery zone or slot not found')
        session_store.update_session(
            user_id,
            {
                'fulfillment_type': 'DELIVERY',
                'address_id': int(address_id),
                'delivery_zone_id': int(delivery_zone_id),
                'delivery_slot_id': int(delivery_slot_id),
                'pickup_store_id': None,
            },
        )


def _post_confirm_tasks(
    *,
    user_id: int,
    order_id: int,
    order_number: str,
    session_snapshot: dict[str, Any],
    grand_total: float,
) -> None:
    coupon_id = session_snapshot.get('coupon_id')
    if coupon_id:
        try:
            promo_svc.record_coupon_usage(int(coupon_id), user_id, order_id)
        except Exception:  # noqa: BLE001
            pass

    loyalty_redeemed = int(session_snapshot.get('loyalty_points_redeemed') or 0)
    if loyalty_redeemed > 0:
        try:
            loyalty_svc.redeem_points(
                user_id=user_id,
                points=loyalty_redeemed,
                order_id=order_id,
                description=f'Redeemed on order {order_number}',
            )
        except Exception:  # noqa: BLE001
            pass

    try:
        earned = loyalty_svc.earn_points(
            user_id=user_id,
            order_id=order_id,
            order_total=float(grand_total),
            description=f'Earned from order {order_number}',
        )
        if earned > 0:
            notification_svc.create_notification(
                user_id=user_id,
                notification_type='LOYALTY_EARNED',
                title='Points earned!',
                body=f'You earned {earned} loyalty points from order {order_number}.',
                ref_entity='ORDER',
                ref_entity_id=order_id,
            )
    except Exception:  # noqa: BLE001
        pass

    try:
        order_notify_svc.send_order_received_notifications(
            user_id=user_id,
            order_id=order_id,
            order_number=order_number,
            grand_total=float(grand_total),
            currency_code=str(session_snapshot.get('currency_code') or 'QAR'),
            fulfillment_type=str(session_snapshot.get('fulfillment_type') or 'DELIVERY'),
        )
    except Exception:  # noqa: BLE001
        pass


def place_order(
    *,
    user_id: int,
    customer_notes: Optional[str] = None,
    payment_method: str = 'COD',
    pickup_store_id: Optional[int] = None,
    address_id: Optional[int] = None,
    delivery_zone_id: Optional[int] = None,
    delivery_slot_id: Optional[int] = None,
    payment_result: Optional[PaymentResult] = None,
    preallocated_order_id: Optional[int] = None,
    preallocated_order_number: Optional[str] = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    _require_session(user_id)

    if pickup_store_id or (address_id and delivery_zone_id and delivery_slot_id):
        _apply_fulfillment_from_confirm(
            user_id=user_id,
            pickup_store_id=pickup_store_id,
            address_id=address_id,
            delivery_zone_id=delivery_zone_id,
            delivery_slot_id=delivery_slot_id,
        )

    session = session_store.get_session(user_id)
    if not session or not session.get('fulfillment_type'):
        raise ValueError('Select delivery or pickup before confirming')

    cart_id = int(session['cart_id'])
    cart_data = cart_svc.get_cart_for_checkout(cart_id=cart_id)
    if not cart_data.get('items'):
        raise ValueError('Checkout session invalid')

    pricing = _compute_pricing(session, cart_data)
    address_snapshot = None
    resolved_address_id = session.get('address_id')

    if session['fulfillment_type'] == 'DELIVERY':
        address = address_svc.get_address(user_id, int(resolved_address_id))
        if not address:
            raise ValueError('Delivery address required')
        address_snapshot = address_svc.serialize_address_snapshot(address)

    order_id = int(preallocated_order_id or orders_svc.allocate_order_id())
    order_number = preallocated_order_number or orders_svc.format_order_number(order_id)

    method = (payment_method or 'COD').upper()
    if method == 'TAP' and payment_result is None:
        raise ValueError('Use POST /checkout/payment/tap/init for online card payment.')

    if payment_result is not None:
        payment = payment_result
    else:
        payment = payment_svc.process_payment(
            method,
            amount=float(pricing['grand_total']),
            order_number=order_number,
        )
    if not payment.success:
        raise ValueError(payment.failure_reason or 'Payment was declined')

    order_items = [
        {
            'location_code': int(item['location_code']),
            'item_code': int(item['item_code']),
            'item_name': _cart_item_name(item),
            'quantity': item['quantity'],
            'unit_price': item['unit_price'],
            'discount_amount': 0,
            'line_total': item['line_total'],
        }
        for item in cart_data['items']
    ]

    orders_svc.create_confirmed_order_batch(
        order_id=order_id,
        order_number=order_number,
        user_id=user_id,
        header={
            'cart_id': cart_id,
            'location_code': int(cart_data['location_code']),
            'order_status': 'CONFIRMED',
            'fulfillment_type': session['fulfillment_type'],
            'payment_status': payment.payment_status,
            'subtotal': pricing['subtotal'],
            'discount_total': pricing['discount_total'] + pricing.get('loyalty_discount', 0),
            'tax_total': pricing['tax_total'],
            'delivery_fee': pricing['delivery_fee'],
            'grand_total': pricing['grand_total'],
            'currency_code': cart_data['summary']['currency_code'],
            'coupon_code': session.get('coupon_code'),
            'delivery_zone_id': session.get('delivery_zone_id'),
            'delivery_slot_id': session.get('delivery_slot_id'),
            'pickup_store_id': session.get('pickup_store_id'),
            'address_id': resolved_address_id,
            'address_snapshot': address_snapshot,
            'customer_notes': customer_notes,
        },
        items=order_items,
        status_notes=f'Order placed — {payment.payment_method} {payment.transaction_id}',
        finalize_cart_id=cart_id,
    )

    session_snapshot = dict(session)
    session_snapshot['currency_code'] = cart_data['summary']['currency_code']
    session_store.delete_session(user_id)

    response = {
        'order_id': order_id,
        'order_number': order_number,
        'order_status': 'CONFIRMED',
        'payment_status': payment.payment_status,
        'fulfillment_type': session['fulfillment_type'],
        'grand_total': pricing['grand_total'],
        'currency_code': cart_data['summary']['currency_code'],
        'item_count': len(order_items),
        'created_at': None,
        'payment': {
            'method': payment.payment_method,
            'status': payment.payment_status,
            'transaction_id': payment.transaction_id,
        },
    }
    side_effects = {
        'user_id': user_id,
        'order_id': order_id,
        'order_number': order_number,
        'session_snapshot': session_snapshot,
        'grand_total': float(pricing['grand_total']),
    }
    return response, side_effects


def complete_order_side_effects(**kwargs: Any) -> None:
    _post_confirm_tasks(**kwargs)


def confirm(
    *,
    user_id: int,
    customer_notes: Optional[str] = None,
    payment_method: str = 'COD',
    pickup_store_id: Optional[int] = None,
    address_id: Optional[int] = None,
    delivery_zone_id: Optional[int] = None,
    delivery_slot_id: Optional[int] = None,
) -> dict[str, Any]:
    method = (payment_method or 'COD').upper()
    if method == 'TAP':
        raise ValueError('Use POST /checkout/payment/tap/init for online card payment.')
    response, side_effects = place_order(
        user_id=user_id,
        customer_notes=customer_notes,
        payment_method=payment_method,
        pickup_store_id=pickup_store_id,
        address_id=address_id,
        delivery_zone_id=delivery_zone_id,
        delivery_slot_id=delivery_slot_id,
    )
    complete_order_side_effects(**side_effects)
    return response


def _order_response_from_detail(order: dict[str, Any]) -> dict[str, Any]:
    return {
        'order_id': int(order['order_id']),
        'order_number': str(order['order_number']),
        'order_status': str(order.get('order_status') or 'CONFIRMED'),
        'payment_status': str(order.get('payment_status') or 'PAID'),
        'fulfillment_type': str(order.get('fulfillment_type') or 'DELIVERY'),
        'grand_total': float(order.get('grand_total') or 0),
        'currency_code': str(order.get('currency_code') or 'QAR'),
        'item_count': len(order.get('items') or []),
        'created_at': order.get('created_at'),
        'payment': {
            'method': 'TAP',
            'status': str(order.get('payment_status') or 'PAID'),
            'transaction_id': None,
        },
    }


def init_tap_payment(
    *,
    user_id: int,
    customer_notes: Optional[str] = None,
    pickup_store_id: Optional[int] = None,
    address_id: Optional[int] = None,
    delivery_zone_id: Optional[int] = None,
    delivery_slot_id: Optional[int] = None,
) -> dict[str, Any]:
    if not tap_svc.tap_configured():
        raise ValueError('Tap Payments is not configured.')

    _require_session(user_id)

    if pickup_store_id or (address_id and delivery_zone_id and delivery_slot_id):
        _apply_fulfillment_from_confirm(
            user_id=user_id,
            pickup_store_id=pickup_store_id,
            address_id=address_id,
            delivery_zone_id=delivery_zone_id,
            delivery_slot_id=delivery_slot_id,
        )

    session = session_store.get_session(user_id)
    if not session or not session.get('fulfillment_type'):
        raise ValueError('Select delivery or pickup before paying')

    cart_id = int(session['cart_id'])
    cart_data = cart_svc.get_cart_for_checkout(cart_id=cart_id)
    if not cart_data.get('items'):
        raise ValueError('Checkout session invalid')

    pricing = _compute_pricing(session, cart_data)
    profile = auth_svc.get_profile(user_id) or {}
    order_id = orders_svc.allocate_order_id()
    order_number = orders_svc.format_order_number(order_id)
    currency = str(cart_data['summary']['currency_code'] or tap_svc.default_currency())

    ok, err, charge = tap_svc.create_checkout_charge(
        amount=float(pricing['grand_total']),
        currency=currency,
        order_number=order_number,
        order_id=order_id,
        user_id=user_id,
        customer={
            'first_name': profile.get('first_name'),
            'last_name': profile.get('last_name'),
            'email': profile.get('email'),
            'mobile': profile.get('mobile'),
        },
        description=f'MamaHub order {order_number}',
    )
    if not ok or not charge:
        raise ValueError(err or 'Could not start Tap payment')

    charge_id = str(charge.get('id') or '')
    redirect_url = tap_svc.charge_redirect_url(charge)
    if not charge_id or not redirect_url:
        raise ValueError('Tap did not return a checkout URL. Try again.')

    tap_svc.store_pending(
        charge_id,
        {
            'user_id': user_id,
            'order_id': order_id,
            'order_number': order_number,
            'customer_notes': customer_notes,
            'pickup_store_id': pickup_store_id,
            'address_id': address_id,
            'delivery_zone_id': delivery_zone_id,
            'delivery_slot_id': delivery_slot_id,
            'expected_amount': float(pricing['grand_total']),
            'currency': currency,
            'session_snapshot': dict(session),
        },
    )
    session_store.update_session(user_id, {'tap_charge_id': charge_id})

    return {
        'charge_id': charge_id,
        'redirect_url': redirect_url,
        'order_number': order_number,
        'amount': float(pricing['grand_total']),
        'currency_code': currency,
    }


def complete_tap_payment(
    *,
    charge_id: str,
    user_id: Optional[int] = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    charge_id = (charge_id or '').strip()
    if not charge_id:
        raise ValueError('Missing Tap charge id')

    existing_order_id = tap_svc.get_completed_order_id(charge_id)
    if existing_order_id and user_id:
        order = orders_svc.get_order(int(user_id), existing_order_id)
        if order:
            return _order_response_from_detail(order), {}

    pending = tap_svc.get_pending(charge_id)
    ok, err, charge = tap_svc.retrieve_charge(charge_id)
    if not ok or not charge:
        raise ValueError(err or 'Could not verify Tap payment')

    metadata = charge.get('metadata') if isinstance(charge.get('metadata'), dict) else {}
    owner_id = int((pending or {}).get('user_id') or metadata.get('user_id') or 0)
    if user_id and owner_id and int(user_id) != owner_id:
        raise ValueError('This payment belongs to a different account.')

    if not tap_svc.is_paid_charge(charge):
        status = str(charge.get('status') or 'UNKNOWN')
        raise ValueError(f'Payment not completed (status: {status}).')

    expected_amount = float((pending or {}).get('expected_amount') or charge.get('amount') or 0)
    paid_amount = float(charge.get('amount') or 0)
    if abs(expected_amount - paid_amount) > 0.05:
        raise ValueError('Payment amount does not match checkout total.')

    if not owner_id:
        raise ValueError('Could not resolve customer for this payment.')

    if pending and pending.get('session_snapshot'):
        session_store.set_session(owner_id, dict(pending['session_snapshot']))

    payment = PaymentResult(
        success=True,
        payment_status='PAID',
        transaction_id=charge_id,
        payment_method='TAP',
    )

    pre_id = (pending or {}).get('order_id') or metadata.get('order_id')
    pre_number = (pending or {}).get('order_number') or metadata.get('order_number')

    response, side_effects = place_order(
        user_id=owner_id,
        customer_notes=(pending or {}).get('customer_notes'),
        payment_method='TAP',
        pickup_store_id=(pending or {}).get('pickup_store_id'),
        address_id=(pending or {}).get('address_id'),
        delivery_zone_id=(pending or {}).get('delivery_zone_id'),
        delivery_slot_id=(pending or {}).get('delivery_slot_id'),
        payment_result=payment,
        preallocated_order_id=int(pre_id) if pre_id else None,
        preallocated_order_number=str(pre_number) if pre_number else None,
    )
    tap_svc.mark_completed(charge_id, int(response['order_id']))
    return response, side_effects


def handle_tap_webhook(*, charge: dict[str, Any], hashstring: str) -> Optional[tuple[dict[str, Any], dict[str, Any]]]:
    if not tap_svc.verify_webhook_hashstring(charge, hashstring):
        raise ValueError('Invalid Tap webhook signature')
    charge_id = str(charge.get('id') or '')
    if not charge_id or not tap_svc.is_paid_charge(charge):
        return None
    if tap_svc.get_completed_order_id(charge_id):
        return None
    return complete_tap_payment(charge_id=charge_id)
