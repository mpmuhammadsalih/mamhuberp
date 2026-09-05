"""Coupon validation for storefront checkout."""
from __future__ import annotations

from typing import Any, Dict, Optional

from db import _get_connection, _safe_rows, _table_exists


def _coupons_ready() -> bool:
    return _table_exists('MH_COUPON') and _table_exists('MH_PROMOTION')


def get_coupon(coupon_code: str) -> Optional[Dict[str, Any]]:
    if not _coupons_ready():
        return None
    rows = _safe_rows(
        """
        SELECT c.COUPON_ID AS coupon_id,
               c.COUPON_CODE AS coupon_code,
               p.PROMOTION_NAME AS promotion_name,
               p.PROMOTION_TYPE AS promotion_type,
               p.DISCOUNT_VALUE AS discount_value,
               p.MIN_ORDER_AMOUNT AS min_order_amount,
               p.MAX_DISCOUNT_AMOUNT AS max_discount_amount,
               p.USAGE_LIMIT AS usage_limit,
               p.USAGE_PER_CUSTOMER AS usage_per_customer
        FROM MH_COUPON c
        JOIN MH_PROMOTION p ON p.PROMOTION_ID = c.PROMOTION_ID
        WHERE UPPER(c.COUPON_CODE) = UPPER(:coupon_code)
          AND c.IS_ACTIVE = 1
          AND p.IS_ACTIVE = 1
          AND p.START_DATE <= SYSTIMESTAMP
          AND p.END_DATE >= SYSTIMESTAMP
        """,
        {'coupon_code': coupon_code.strip()},
    )
    return dict(rows[0]) if rows else None


def _count_total_usage(coupon_id: int) -> int:
    rows = _safe_rows(
        'SELECT COUNT(*) AS cnt FROM MH_COUPON_USAGE WHERE COUPON_ID = :coupon_id',
        {'coupon_id': coupon_id},
    )
    return int(rows[0]['cnt']) if rows else 0


def _count_user_usage(coupon_id: int, user_id: int) -> int:
    rows = _safe_rows(
        """
        SELECT COUNT(*) AS cnt FROM MH_COUPON_USAGE
        WHERE COUPON_ID = :coupon_id AND USER_ID = :user_id
        """,
        {'coupon_id': coupon_id, 'user_id': user_id},
    )
    return int(rows[0]['cnt']) if rows else 0


def calculate_discount(coupon: Dict[str, Any], subtotal: float) -> float:
    promo_type = str(coupon.get('promotion_type') or '').upper()
    value = float(coupon.get('discount_value') or 0)
    max_discount = coupon.get('max_discount_amount')

    if promo_type == 'PERCENTAGE':
        discount = round(subtotal * value / 100, 2)
    elif promo_type == 'FIXED':
        discount = round(min(value, subtotal), 2)
    else:
        discount = 0.0

    if max_discount is not None:
        discount = min(discount, float(max_discount))
    return max(discount, 0.0)


def validate_coupon(
    coupon_code: str,
    *,
    user_id: Optional[int],
    subtotal: float,
) -> Dict[str, Any]:
    coupon = get_coupon(coupon_code)
    if not coupon:
        raise ValueError('Invalid coupon code')

    min_order = float(coupon.get('min_order_amount') or 0)
    if subtotal < min_order:
        raise ValueError(
            f'Minimum order amount of QAR {min_order:.2f} required for this coupon'
        )

    usage_limit = coupon.get('usage_limit')
    if usage_limit is not None and _count_total_usage(int(coupon['coupon_id'])) >= int(usage_limit):
        raise ValueError('Coupon usage limit reached')

    if user_id is not None:
        per_customer = int(coupon.get('usage_per_customer') or 1)
        if _count_user_usage(int(coupon['coupon_id']), user_id) >= per_customer:
            raise ValueError('You have already used this coupon')

    discount = calculate_discount(coupon, subtotal)
    return {
        'coupon_code': coupon['coupon_code'],
        'coupon_id': int(coupon['coupon_id']),
        'promotion_name': coupon.get('promotion_name'),
        'promotion_type': coupon.get('promotion_type'),
        'discount_amount': discount,
    }


def list_public_coupons() -> list[Dict[str, Any]]:
    if not _coupons_ready():
        return []
    try:
        from addons.ecommerce import settings_store

        if not settings_store.coupons_enabled():
            return []
    except ImportError:
        return []
    return _safe_rows(
        """
        SELECT c.COUPON_ID AS coupon_id,
               c.COUPON_CODE AS coupon_code,
               p.PROMOTION_NAME AS promotion_name,
               p.PROMOTION_TYPE AS promotion_type,
               p.DISCOUNT_VALUE AS discount_value,
               p.MIN_ORDER_AMOUNT AS min_order_amount,
               p.MAX_DISCOUNT_AMOUNT AS max_discount_amount
        FROM MH_COUPON c
        JOIN MH_PROMOTION p ON p.PROMOTION_ID = c.PROMOTION_ID
        WHERE c.IS_ACTIVE = 1 AND p.IS_ACTIVE = 1
          AND p.START_DATE <= SYSTIMESTAMP
          AND p.END_DATE >= SYSTIMESTAMP
        ORDER BY p.PROMOTION_NAME
        """,
        {},
    )


def record_coupon_usage(coupon_id: int, user_id: int, order_id: int) -> None:
    if not _table_exists('MH_COUPON_USAGE'):
        return
    rows = _safe_rows('SELECT SEQ_MH_COUPON_USAGE_ID.NEXTVAL AS id FROM DUAL', {})
    usage_id = int(rows[0]['id'])
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO MH_COUPON_USAGE (USAGE_ID, COUPON_ID, USER_ID, ORDER_ID)
                VALUES (:usage_id, :coupon_id, :user_id, :order_id)
                """,
                {
                    'usage_id': usage_id,
                    'coupon_id': coupon_id,
                    'user_id': user_id,
                    'order_id': order_id,
                },
            )
        conn.commit()
