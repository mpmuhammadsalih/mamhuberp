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

    profile = auth_svc.get_profile(user_id)
    if not profile:
        return

    order = orders_svc.get_order(user_id, order_id)
    items = (order or {}).get('items') or []
    first_name = str(profile.get('first_name') or '')
    email = str(profile.get('email') or '').strip()
    mobile = str(profile.get('mobile') or '').strip()
    total_label = f'{currency_code} {float(grand_total):.2f}'
    order_url = f'{_storefront_base_url()}/orders/{order_id}'
    fulfillment_label = (
        'pickup' if str(fulfillment_type).upper() == 'PICKUP' else 'delivery'
    )

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
            if not ok:
                logger.warning('Order WhatsApp failed for %s: %s', order_number, err)
        except Exception:  # noqa: BLE001
            logger.exception('Order WhatsApp error for %s', order_number)
