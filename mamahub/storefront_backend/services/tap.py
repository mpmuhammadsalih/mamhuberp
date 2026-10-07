"""Tap Payments gateway — https://developers.tap.company"""
from __future__ import annotations

import hashlib
import hmac
import os
import threading
import time
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Optional, Tuple

import requests

_API_BASE = 'https://api.tap.company/v2'
_PENDING_LOCK = threading.Lock()
_pending: dict[str, tuple[dict[str, Any], float]] = {}
_completed: dict[str, int] = {}


def tap_configured() -> bool:
    return bool(os.getenv('TAP_SECRET_KEY', '').strip())


def _secret_key() -> str:
    key = os.getenv('TAP_SECRET_KEY', '').strip()
    if not key:
        raise ValueError('Tap Payments is not configured (TAP_SECRET_KEY).')
    return key


def default_currency() -> str:
    return (os.getenv('TAP_CURRENCY') or 'QAR').strip().upper()


def _storefront_base() -> str:
    base = (os.getenv('STOREFRONT_BASE_URL') or 'http://localhost:5173').strip().rstrip('/')
    return base or 'http://localhost:5173'


def _pending_ttl_seconds() -> int:
    raw = os.getenv('TAP_PENDING_TTL_SECONDS', '3600').strip()
    try:
        return max(300, int(raw))
    except ValueError:
        return 3600


def _format_amount(amount: float, currency: str) -> str:
    """ISO decimal places per Tap webhook hash rules."""
    decimals = 3 if currency in {'BHD', 'KWD', 'OMR', 'JOD'} else 2
    quant = Decimal(str(amount)).quantize(Decimal(10) ** -decimals, rounding=ROUND_HALF_UP)
    return format(quant, f'.{decimals}f')


def _headers() -> dict[str, str]:
    return {
        'Authorization': f'Bearer {_secret_key()}',
        'Content-Type': 'application/json',
    }


def _api_post(path: str, payload: dict[str, Any]) -> Tuple[bool, str, Optional[dict[str, Any]]]:
    try:
        response = requests.post(f'{_API_BASE}{path}', headers=_headers(), json=payload, timeout=30)
        data = response.json() if response.content else {}
        if response.ok:
            return True, '', data if isinstance(data, dict) else {}
        err = data.get('errors') or data.get('error') or data
        if isinstance(err, list) and err:
            message = str(err[0].get('description') or err[0])
        elif isinstance(err, dict):
            message = str(err.get('description') or err.get('message') or err)
        else:
            message = response.text or f'HTTP {response.status_code}'
        return False, message, None
    except Exception as exc:  # noqa: BLE001
        return False, str(exc), None


def _api_get(path: str) -> Tuple[bool, str, Optional[dict[str, Any]]]:
    try:
        response = requests.get(f'{_API_BASE}{path}', headers=_headers(), timeout=30)
        data = response.json() if response.content else {}
        if response.ok:
            return True, '', data if isinstance(data, dict) else {}
        err = data.get('errors') or data.get('error') or data
        if isinstance(err, list) and err:
            message = str(err[0].get('description') or err[0])
        elif isinstance(err, dict):
            message = str(err.get('description') or err.get('message') or err)
        else:
            message = response.text or f'HTTP {response.status_code}'
        return False, message, None
    except Exception as exc:  # noqa: BLE001
        return False, str(exc), None


def store_pending(charge_id: str, payload: dict[str, Any]) -> None:
    with _PENDING_LOCK:
        _pending[charge_id] = (dict(payload), time.time() + _pending_ttl_seconds())


def get_pending(charge_id: str) -> Optional[dict[str, Any]]:
    with _PENDING_LOCK:
        entry = _pending.get(charge_id)
        if not entry:
            return None
        value, expires_at = entry
        if expires_at <= time.time():
            _pending.pop(charge_id, None)
            return None
        return dict(value)


def mark_completed(charge_id: str, order_id: int) -> None:
    with _PENDING_LOCK:
        _completed[charge_id] = int(order_id)
        _pending.pop(charge_id, None)


def get_completed_order_id(charge_id: str) -> Optional[int]:
    with _PENDING_LOCK:
        return _completed.get(charge_id)


def create_checkout_charge(
    *,
    amount: float,
    currency: str,
    order_number: str,
    order_id: int,
    user_id: int,
    customer: dict[str, Any],
    description: str = 'MamaHub order',
) -> Tuple[bool, str, Optional[dict[str, Any]]]:
    redirect_url = f'{_storefront_base()}/checkout/payment/return'
    webhook_url = os.getenv('TAP_WEBHOOK_URL', '').strip()
    if not webhook_url:
        webhook_url = f'{_storefront_base().rstrip("/")}/api/v1/checkout/payment/tap/webhook'
        # Tap cannot post to localhost — production URL should be set explicitly.
        if 'localhost' in webhook_url or '127.0.0.1' in webhook_url:
            webhook_url = ''

    phone = str(customer.get('phone') or customer.get('mobile') or '').strip()
    phone_country = '974'
    phone_number = phone
    if phone.startswith('+974'):
        phone_number = phone[4:]
    elif phone.startswith('974') and len(phone) > 8:
        phone_number = phone[3:]

    payload: dict[str, Any] = {
        'amount': float(amount),
        'currency': currency,
        'threeDSecure': True,
        'save_card': False,
        'customer_initiated': True,
        'description': description,
        'metadata': {
            'user_id': str(user_id),
            'order_id': str(order_id),
            'order_number': order_number,
        },
        'reference': {
            'transaction': order_number,
            'order': order_number,
        },
        'customer': {
            'first_name': str(customer.get('first_name') or 'Customer'),
            'last_name': str(customer.get('last_name') or ''),
            'email': str(customer.get('email') or f'customer{user_id}@mamahub.local'),
            'phone': {
                'country_code': phone_country,
                'number': phone_number or '00000000',
            },
        },
        'source': {'id': os.getenv('TAP_SOURCE_ID', 'src_all').strip() or 'src_all'},
        'redirect': {'url': redirect_url},
    }
    if webhook_url:
        payload['post'] = {'url': webhook_url}

    ok, err, data = _api_post('/charges', payload)
    if not ok or not data:
        return False, err or 'Failed to create Tap charge', None
    return True, '', data


def retrieve_charge(charge_id: str) -> Tuple[bool, str, Optional[dict[str, Any]]]:
    charge_id = (charge_id or '').strip()
    if not charge_id:
        return False, 'Missing Tap charge id', None
    return _api_get(f'/charges/{charge_id}')


def charge_redirect_url(charge: dict[str, Any]) -> str:
    transaction = charge.get('transaction') or {}
    if isinstance(transaction, dict):
        url = transaction.get('url') or ''
        if url:
            return str(url)
    redirect = charge.get('redirect') or {}
    if isinstance(redirect, dict):
        return str(redirect.get('url') or '')
    return ''


def is_paid_charge(charge: dict[str, Any]) -> bool:
    return str(charge.get('status') or '').upper() == 'CAPTURED'


def verify_webhook_hashstring(charge: dict[str, Any], hashstring_header: str) -> bool:
    if not hashstring_header:
        return False
    charge_id = str(charge.get('id') or '')
    currency = str(charge.get('currency') or default_currency()).upper()
    amount = _format_amount(float(charge.get('amount') or 0), currency)
    reference = charge.get('reference') or {}
    gateway_reference = str(reference.get('gateway') or '') if isinstance(reference, dict) else ''
    payment_reference = str(reference.get('payment') or '') if isinstance(reference, dict) else ''
    status = str(charge.get('status') or '')
    transaction = charge.get('transaction') or {}
    created = str(transaction.get('created') or '') if isinstance(transaction, dict) else ''
    to_hash = (
        f'x_id{charge_id}x_amount{amount}x_currency{currency}'
        f'x_gateway_reference{gateway_reference}x_payment_reference{payment_reference}'
        f'x_status{status}x_created{created}'
    )
    digest = hmac.new(
        _secret_key().encode('utf-8'),
        to_hash.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(digest, hashstring_header.strip())
