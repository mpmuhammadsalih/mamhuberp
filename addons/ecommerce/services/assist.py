"""Ecommerce Assist — WhatsApp, in-app notify, and staff chat follow-up."""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple
from urllib.parse import quote

from addons.ecommerce import assist_db
from storefront_backend.services import inbox as inbox_svc
from storefront_backend.services.whatsapp import phone_to_e164


def _display_name(row: Dict[str, Any]) -> str:
    name = f"{row.get('first_name') or ''} {row.get('last_name') or ''}".strip()
    return name or (row.get('email') or 'there')


def _whatsapp_href(mobile: Optional[str], message: str) -> Optional[str]:
    e164 = phone_to_e164(mobile or '')
    if not e164:
        return None
    digits = e164.lstrip('+')
    return f'https://wa.me/{digits}?text={quote(message)}'


def _attach_chat(row: Dict[str, Any], message: str) -> Dict[str, Any]:
    out = dict(row)
    out['customer_name'] = _display_name(row)
    out['assist_message'] = message
    out['whatsapp_href'] = _whatsapp_href(row.get('mobile'), message)
    out['can_in_app'] = bool(row.get('user_id'))
    return out


def send_assist_notification(user_id: int, message: str) -> Tuple[bool, str]:
    uid, err = inbox_svc.parse_assist_user_id(user_id)
    if not uid:
        return False, err
    try:
        inbox_svc.send_in_app_notification(uid, message)
    except ValueError as exc:
        return False, str(exc)
    except Exception:
        return False, 'Could not send the in-app notification.'
    return True, 'In-app notification sent. The customer will see it in Messages.'


def open_assist_chat(staff_username: str, user_id: int, message: str) -> Tuple[bool, str, Optional[int]]:
    uid, err = inbox_svc.parse_assist_user_id(user_id)
    if not uid:
        return False, err, None
    try:
        conversation_id = inbox_svc.open_staff_customer_chat(staff_username, uid, message)
    except ValueError as exc:
        return False, str(exc), None
    except Exception:
        return False, 'Could not open shop chat for this customer.', None
    return True, 'Chat opened.', conversation_id


def get_assist_board() -> Dict[str, Any]:
    carts = []
    for row in assist_db.list_abandoned_carts():
        name = _display_name(row)
        total = float(row.get('cart_total') or 0)
        items = int(row.get('item_count') or 0)
        carts.append(
            _attach_chat(
                row,
                f'Hi {name}, this is MamaHub. You left {items} item(s) in your cart '
                f'(about QAR {total:.0f}). I can help you finish the order — reply here.',
            )
        )

    checkouts = []
    for row in assist_db.list_failed_checkouts():
        name = _display_name(row)
        amount = float(row.get('amount') or 0)
        order_no = (row.get('order_number') or '').strip()
        extra = f' (order {order_no})' if order_no else ''
        checkouts.append(
            _attach_chat(
                row,
                f'Hi {name}, this is MamaHub. It looks like payment did not finish{extra}'
                f'{f" for QAR {amount:.0f}" if amount else ""}. I can help you complete checkout.',
            )
        )

    idle = []
    for row in assist_db.list_idle_logins():
        name = _display_name(row)
        idle.append(
            _attach_chat(
                row,
                f'Hi {name}, welcome to MamaHub! Looking for a toy or a gift? '
                'Tell me the age or occasion and I will help you find it.',
            )
        )

    searches = []
    for row in assist_db.list_zero_searches():
        name = _display_name(row)
        query = (row.get('query_text') or '').strip() or 'that item'
        searches.append(
            _attach_chat(
                row,
                f'Hi {name}, you searched for "{query}" on MamaHub and we may not have shown a match. '
                'Tell me what you need and I will help you find it.',
            )
        )

    return {
        'abandoned_carts': carts,
        'failed_checkouts': checkouts,
        'idle_logins': idle,
        'zero_searches': searches,
        'counts': {
            'carts': len(carts),
            'checkouts': len(checkouts),
            'idle': len(idle),
            'searches': len(searches),
            'total': len(carts) + len(checkouts) + len(idle) + len(searches),
        },
    }
