"""Email + WhatsApp notifications when a storefront order is placed."""
from __future__ import annotations

import logging

from storefront_backend.services import auth as auth_svc
from storefront_backend.services import email as email_svc
from storefront_backend.services import notifications as notification_svc
from storefront_backend.services import orders as orders_svc
from storefront_backend.services import whatsapp as whatsapp_svc

logger = logging.getLogger(__name__)


def _storefront_base_url() -> str:
    import os

    base = (os.getenv('STOREFRONT_BASE_URL') or 'http://localhost:5173').strip().rstrip('/')
    return base or 'http://localhost:5173'


def send_order_received_notifications(
    *,
    user_id: int,
    order_id: int,
    order_number: str,
    grand_total: float,
    currency_code: str = 'QAR',
    fulfillment_type: str = 'DELIVERY',
) -> None:
    """In-app + email + WhatsApp for a newly confirmed order."""
    try:
        notification_svc.notify_order_confirmed(
            user_id=user_id,
            order_number=order_number,
            order_id=order_id,
        )
    except Exception:  # noqa: BLE001
        logger.exception('In-app order notification failed for order %s', order_number)

    profile = auth_svc.get_profile(user_id) or {}
    order = None
    try:
        order = orders_svc.get_order(user_id, order_id)
    except Exception:  # noqa: BLE001
        logger.exception('Could not load order %s for notifications', order_number)
    items = (order or {}).get('items') or []
    first_name = str(profile.get('first_name') or '')
    email = str(profile.get('email') or '').strip()
    mobile = str(profile.get('mobile') or '').strip()
    total_label = f'{currency_code} {float(grand_total):.2f}'
    order_url = f'{_storefront_base_url()}/orders/{order_id}'
    fulfillment_label = (
        'pickup' if str(fulfillment_type).upper() == 'PICKUP' else 'delivery'
    )

    if mobile and whatsapp_svc.whatsapp_configured():
        try:
            ok, err = whatsapp_svc.send_order_confirmation_whatsapp(
                to_phone=mobile,
                first_name=first_name,
                order_number=order_number,
                total_label=total_label,
                order_url=order_url,
                fulfillment_label=fulfillment_label,
            )
            if ok:
                logger.info('Order WhatsApp sent for %s to %s', order_number, mobile)
            else:
                logger.warning('Order WhatsApp failed for %s: %s', order_number, err)
        except Exception:  # noqa: BLE001
            logger.exception('Order WhatsApp error for %s', order_number)
    elif not mobile:
        logger.warning('Order WhatsApp skipped for %s: no mobile on customer profile', order_number)
    else:
        logger.warning('Order WhatsApp skipped for %s: WhatsApp Cloud API is not configured', order_number)

    if email_svc.smtp_configured() and email_svc.order_notify_email():
        try:
            ok, err = email_svc.send_new_order_staff_email(
                order_number=order_number,
                order_id=order_id,
                grand_total=float(grand_total),
                currency_code=currency_code,
                fulfillment_type=fulfillment_type,
                customer_name=first_name,
                customer_email=email,
                items=items,
            )
            if not ok:
                logger.warning('Staff order email failed for %s: %s', order_number, err)
        except Exception:  # noqa: BLE001
            logger.exception('Staff order email error for %s', order_number)

    if not profile:
        return

    if email and email_svc.smtp_configured():
        try:
            ok, err = email_svc.send_order_confirmation_email(
                to=email,
                first_name=first_name,
                order_number=order_number,
                order_id=order_id,
                grand_total=float(grand_total),
                currency_code=currency_code,
                fulfillment_type=fulfillment_type,
                items=items,
            )
            if not ok:
                logger.warning('Order confirmation email failed for %s: %s', order_number, err)
        except Exception:  # noqa: BLE001
            logger.exception('Order confirmation email error for %s', order_number)


_CUSTOMER_STATUS_COPY = {
    'PROCESSING': ('Order accepted', 'We accepted your order {number} and started preparing it.'),
    'PICKING': ('Order being packed', 'Your order {number} is being packed now.'),
    'PACKED': ('Order ready', 'Your order {number} is ready.'),
    'OUT_FOR_DELIVERY': ('Out for delivery', 'Your order {number} is on the way.'),
    'DELIVERED': ('Order completed', 'Your order {number} has been completed. Thank you!'),
    'CANCELLED': ('Order cancelled', 'Your order {number} was cancelled.'),
}


def send_order_status_notifications(order: dict, new_status: str) -> None:
    """Tell the customer when ERP/live orders changes the order status."""
    status = (new_status or '').strip().upper()
    number = str(order.get('order_number') or '').strip()
    try:
        user_id = int(order.get('user_id') or 0)
    except (TypeError, ValueError):
        user_id = 0
    if not user_id or not number or status not in _CUSTOMER_STATUS_COPY:
        return

    title, body_tmpl = _CUSTOMER_STATUS_COPY[status]
    fulfill = str(order.get('fulfillment_type') or 'DELIVERY').upper()
    if status == 'PACKED' and fulfill == 'PICKUP':
        title, body_tmpl = 'Order ready for pickup', 'Your order {number} is ready for pickup.'
    elif status == 'PACKED':
        title, body_tmpl = 'Order packed', 'Your order {number} is packed and ready to go out.'
    elif status == 'DELIVERED' and fulfill == 'PICKUP':
        title, body_tmpl = 'Order collected', 'Your order {number} was handed over. Thank you!'
    body = body_tmpl.format(number=number)

    try:
        notification_svc.notify_order_status(
            user_id=user_id,
            order_number=number,
            order_id=int(order.get('order_id') or 0),
            title=title,
            body=body,
        )
    except Exception:  # noqa: BLE001
        logger.exception('In-app status notification failed for %s', number)

    profile = auth_svc.get_profile(user_id) or {}
    first_name = str(profile.get('first_name') or order.get('customer_first_name') or '')
    email = str(profile.get('email') or order.get('customer_email') or '').strip()
    mobile = str(profile.get('mobile') or order.get('customer_mobile') or '').strip()
    order_id = int(order.get('order_id') or 0)
    order_url = f'{_storefront_base_url()}/orders/{order_id}'
    greeting = first_name.strip() or 'there'
    wa_text = f'Hi {greeting}! {body}\nTrack: {order_url}'

    if mobile and whatsapp_svc.whatsapp_configured():
        try:
            ok, err = whatsapp_svc.send_whatsapp_message(to_phone=mobile, body=wa_text)
            if not ok:
                logger.warning('Status WhatsApp failed for %s: %s', number, err)
        except Exception:  # noqa: BLE001
            logger.exception('Status WhatsApp error for %s', number)

    if email and email_svc.smtp_configured():
        try:
            ok, err = email_svc.send_order_status_email(
                to=email,
                first_name=first_name,
                order_number=number,
                order_id=order_id,
                title=title,
                body=body,
            )
            if not ok:
                logger.warning('Status email failed for %s: %s', number, err)
        except Exception:  # noqa: BLE001
            logger.exception('Status email error for %s', number)
