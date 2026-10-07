"""WhatsApp messaging via Meta Cloud API."""
from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple

import requests


def phone_to_e164(phone: str) -> str:
    """Normalize a Qatar/local phone to E.164 (e.g. +974XXXXXXXX)."""
    if not phone:
        return ''
    cleaned = str(phone).strip().replace(' ', '').replace('-', '')
    if cleaned.startswith('+'):
        cleaned = cleaned[1:]
    if cleaned.startswith('00'):
        cleaned = cleaned[2:]
    if cleaned.startswith('974'):
        return '+' + cleaned
    if len(cleaned) == 8 and cleaned.isdigit():
        return '+974' + cleaned
    if cleaned.isdigit():
        return '+' + cleaned
    return ''


def _phone_to_wa_recipient(phone: str) -> str:
    """Meta recipient — digits with country code, no plus."""
    return phone_to_e164(phone).lstrip('+')


def whatsapp_configured() -> bool:
    return bool(
        os.getenv('WHATSAPP_CLOUD_TOKEN', '').strip()
        and os.getenv('WHATSAPP_PHONE_NUMBER_ID', '').strip()
    )


def _meta_api_base() -> str:
    version = (os.getenv('WHATSAPP_API_VERSION') or 'v21.0').strip()
    phone_id = os.getenv('WHATSAPP_PHONE_NUMBER_ID', '').strip()
    return f'https://graph.facebook.com/{version}/{phone_id}/messages'


def _meta_headers() -> Dict[str, str]:
    token = os.getenv('WHATSAPP_CLOUD_TOKEN', '').strip()
    return {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    }


def _meta_post(payload: Dict[str, Any]) -> Tuple[bool, str]:
    try:
        response = requests.post(
            _meta_api_base(),
            headers=_meta_headers(),
            json=payload,
            timeout=30,
        )
        data = response.json() if response.content else {}
        if response.ok:
            message_id = (
                (data.get('messages') or [{}])[0].get('id')
                if isinstance(data.get('messages'), list)
                else None
            )
            return True, str(message_id or 'sent')
        err = data.get('error') if isinstance(data, dict) else None
        if isinstance(err, dict):
            code = err.get('code')
            sub = err.get('error_subcode')
            msg = err.get('message') or err.get('error_user_msg') or str(err)
            parts = [str(msg)]
            if code is not None:
                parts.append(f'code={code}')
            if sub is not None:
                parts.append(f'sub={sub}')
            return False, ' '.join(parts)
        return False, response.text or f'HTTP {response.status_code}'
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def _send_template(
    *,
    to_phone: str,
    template_name: str,
    language_code: str,
    body_params: List[str],
) -> Tuple[bool, str]:
    recipient = _phone_to_wa_recipient(to_phone)
    if not recipient or len(recipient) < 10:
        return False, 'Invalid phone number for WhatsApp.'
    components: List[Dict[str, Any]] = []
    if body_params:
        components.append({
            'type': 'body',
            'parameters': [{'type': 'text', 'text': str(value)} for value in body_params],
        })
    payload: Dict[str, Any] = {
        'messaging_product': 'whatsapp',
        'to': recipient,
        'type': 'template',
        'template': {
            'name': template_name,
            'language': {'code': language_code},
        },
    }
    if components:
        payload['template']['components'] = components
    return _meta_post(payload)


def _send_text(*, to_phone: str, body: str) -> Tuple[bool, str]:
    recipient = _phone_to_wa_recipient(to_phone)
    if not recipient or len(recipient) < 10:
        return False, 'Invalid phone number for WhatsApp.'
    payload = {
        'messaging_product': 'whatsapp',
        'to': recipient,
        'type': 'text',
        'text': {'body': body or ' '},
    }
    return _meta_post(payload)


def send_whatsapp_message(*, to_phone: str, body: str) -> Tuple[bool, str]:
    """Send a plain-text WhatsApp message (24-hour customer service window only)."""
    if not whatsapp_configured():
        return False, 'WhatsApp not configured (WHATSAPP_CLOUD_TOKEN / WHATSAPP_PHONE_NUMBER_ID).'
    return _send_text(to_phone=to_phone, body=body)


def send_order_confirmation_whatsapp(
    *,
    to_phone: str,
    first_name: str,
    order_number: str,
    total_label: str,
    order_url: str,
    fulfillment_label: str,
) -> Tuple[bool, str]:
    """Send order confirmation via Meta template (or plain text if no template set)."""
    if not whatsapp_configured():
        return False, 'WhatsApp not configured (WHATSAPP_CLOUD_TOKEN / WHATSAPP_PHONE_NUMBER_ID).'

    greeting = (first_name or '').strip() or 'there'
    template_name = (os.getenv('WHATSAPP_ORDER_TEMPLATE_NAME') or '').strip()
    language_code = (os.getenv('WHATSAPP_ORDER_TEMPLATE_LANG') or 'en').strip()

    if template_name:
        body_params: List[str] = []
        if template_name.lower() != 'hello_world':
            body_params = [greeting, order_number, total_label, order_url]
        return _send_template(
            to_phone=to_phone,
            template_name=template_name,
            language_code=language_code,
            body_params=body_params,
        )

    body = (
        f'Hi {greeting}! Your MamaHub order {order_number} is confirmed.\n'
        f'Total: {total_label} ({fulfillment_label}).\n'
        f'Track: {order_url}'
    )
    ok, err = _send_text(to_phone=to_phone, body=body)
    if not ok and 'template' in err.lower():
        return False, (
            f'{err} — Create an approved template in Meta and set '
            'WHATSAPP_ORDER_TEMPLATE_NAME in .env.'
        )
    return ok, err
