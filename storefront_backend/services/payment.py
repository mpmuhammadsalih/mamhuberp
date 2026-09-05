"""Payment processing for storefront checkout."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from uuid import uuid4


@dataclass(frozen=True)
class PaymentResult:
    success: bool
    payment_status: str
    transaction_id: Optional[str] = None
    failure_reason: Optional[str] = None
    payment_method: str = 'COD'


SUPPORTED_METHODS = frozenset({'COD', 'CARD_ON_DELIVERY', 'MOCK', 'CARD', 'TAP'})


def list_payment_methods() -> list[dict[str, str]]:
    methods = [
        {
            'code': 'COD',
            'label': 'Cash on delivery',
            'description': 'Pay with cash when your order arrives',
        },
    ]
    try:
        from storefront_backend.services import tap as tap_svc

        if tap_svc.tap_configured():
            methods.append(
                {
                    'code': 'TAP',
                    'label': 'Online payment',
                    'description': 'Pay securely now with Visa, Mastercard, or mada via Tap',
                }
            )
    except ImportError:
        pass
    return methods


def process_payment(
    payment_method: str,
    *,
    amount: float,
    order_number: str,
) -> PaymentResult:
    method = (payment_method or 'COD').upper()
    if method not in SUPPORTED_METHODS:
        raise ValueError(
            f'Unsupported payment method: {payment_method}. '
            f'Supported: {", ".join(sorted(SUPPORTED_METHODS))}'
        )

    if method == 'TAP':
        return PaymentResult(
            success=False,
            payment_status='FAILED',
            failure_reason='Online card payment must be completed through Tap checkout.',
            payment_method=method,
        )

    if method == 'COD':
        return PaymentResult(
            success=True,
            payment_status='PENDING',
            transaction_id=f'COD-{order_number}',
            payment_method=method,
        )

    if method == 'CARD_ON_DELIVERY':
        return PaymentResult(
            success=True,
            payment_status='PENDING',
            transaction_id=f'COD-CARD-{order_number}',
            payment_method=method,
        )

    if method == 'MOCK':
        return PaymentResult(
            success=True,
            payment_status='PAID',
            transaction_id=f'MOCK-{order_number}',
            payment_method=method,
        )

    # Legacy simulated online card gateway (admin / tests)
    cents = round(amount * 100) % 100
    if cents == 99:
        return PaymentResult(
            success=False,
            payment_status='FAILED',
            transaction_id=f'CARD-{uuid4().hex[:12].upper()}',
            failure_reason='Card declined (simulated)',
            payment_method=method,
        )

    return PaymentResult(
        success=True,
        payment_status='PAID',
        transaction_id=f'CARD-{uuid4().hex[:12].upper()}',
        payment_method=method,
    )
