"""MH_PROMOTION / MH_COUPON queries for the ecommerce addon."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from db import _get_connection, _safe_rows, _table_exists

PROMOTION_TABLE = 'MH_PROMOTION'
COUPON_TABLE = 'MH_COUPON'

PROMOTION_TYPES = frozenset({'PERCENTAGE', 'FIXED', 'FREE_DELIVERY'})


def promotions_tables_ready() -> bool:
    if _table_exists(PROMOTION_TABLE) and _table_exists(COUPON_TABLE):
        return True
    try:
        from storefront_backend.services.schema_bootstrap import ensure_promotion_schema

        ensure_promotion_schema()
    except Exception:  # noqa: BLE001
        return False
    return _table_exists(PROMOTION_TABLE) and _table_exists(COUPON_TABLE)


def _table_missing_message() -> str:
    return (
        'MH_PROMOTION tables are not installed in this database. '
        'Run MamaHub schema script sql/02_tables/13_mh_promotions.sql on the tenant DB.'
    )


def active_promotion_count() -> int:
    if not promotions_tables_ready():
        return 0
    rows = _safe_rows(
        """
        SELECT COUNT(*) AS cnt
        FROM MH_PROMOTION p
        JOIN MH_COUPON c ON c.PROMOTION_ID = p.PROMOTION_ID
        WHERE p.IS_ACTIVE = 1
          AND c.IS_ACTIVE = 1
          AND p.START_DATE <= SYSTIMESTAMP
          AND p.END_DATE >= SYSTIMESTAMP
        """,
        {},
    )
    return int(rows[0]['cnt']) if rows else 0


def list_promotions(*, search: Optional[str] = None) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    if not promotions_tables_ready():
        return [], _table_missing_message()

    where = ['1=1']
    params: Dict[str, Any] = {}
    if search:
        where.append(
            "(UPPER(c.COUPON_CODE) LIKE :search OR UPPER(p.PROMOTION_NAME) LIKE :search "
            "OR UPPER(p.PROMOTION_CODE) LIKE :search)"
        )
        params['search'] = f'%{search.strip().upper()}%'

    where_sql = ' AND '.join(where)
    rows = _safe_rows(
        f"""
        SELECT
            c.COUPON_ID AS coupon_id,
            c.COUPON_CODE AS coupon_code,
            c.IS_ACTIVE AS coupon_active,
            p.PROMOTION_ID AS promotion_id,
            p.PROMOTION_CODE AS promotion_code,
            p.PROMOTION_NAME AS promotion_name,
            p.PROMOTION_TYPE AS promotion_type,
            p.DISCOUNT_VALUE AS discount_value,
            p.MIN_ORDER_AMOUNT AS min_order_amount,
            p.MAX_DISCOUNT_AMOUNT AS max_discount_amount,
            p.START_DATE AS start_date,
            p.END_DATE AS end_date,
            p.USAGE_LIMIT AS usage_limit,
            p.USAGE_PER_CUSTOMER AS usage_per_customer,
            p.IS_ACTIVE AS promotion_active,
            (SELECT COUNT(*) FROM MH_COUPON_USAGE u WHERE u.COUPON_ID = c.COUPON_ID) AS usage_count
        FROM MH_COUPON c
        JOIN MH_PROMOTION p ON p.PROMOTION_ID = c.PROMOTION_ID
        WHERE {where_sql}
        ORDER BY p.CREATED_AT DESC, c.COUPON_CODE
        """,
        params,
    )
    return rows, None


def get_promotion(promotion_id: int) -> Optional[Dict[str, Any]]:
    if not promotions_tables_ready():
        return None
    rows = _safe_rows(
        """
        SELECT
            c.COUPON_ID AS coupon_id,
            c.COUPON_CODE AS coupon_code,
            c.IS_ACTIVE AS coupon_active,
            p.PROMOTION_ID AS promotion_id,
            p.PROMOTION_CODE AS promotion_code,
            p.PROMOTION_NAME AS promotion_name,
            p.PROMOTION_TYPE AS promotion_type,
            p.DISCOUNT_VALUE AS discount_value,
            p.MIN_ORDER_AMOUNT AS min_order_amount,
            p.MAX_DISCOUNT_AMOUNT AS max_discount_amount,
            p.START_DATE AS start_date,
            p.END_DATE AS end_date,
            p.USAGE_LIMIT AS usage_limit,
            p.USAGE_PER_CUSTOMER AS usage_per_customer,
            p.IS_ACTIVE AS promotion_active
        FROM MH_PROMOTION p
        JOIN MH_COUPON c ON c.PROMOTION_ID = p.PROMOTION_ID
        WHERE p.PROMOTION_ID = :promotion_id
        """,
        {'promotion_id': int(promotion_id)},
    )
    return dict(rows[0]) if rows else None


def create_promotion_with_coupon(data: Dict[str, Any]) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    if not promotions_tables_ready():
        return False, _table_missing_message(), None

    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT SEQ_MH_PROMOTION_ID.NEXTVAL AS id FROM DUAL')
                promotion_id = int((cur.fetchone() or [0])[0])
                cur.execute('SELECT SEQ_MH_COUPON_ID.NEXTVAL AS id FROM DUAL')
                coupon_id = int((cur.fetchone() or [0])[0])
                cur.execute(
                    """
                    INSERT INTO MH_PROMOTION (
                        PROMOTION_ID, PROMOTION_CODE, PROMOTION_NAME, PROMOTION_TYPE,
                        DISCOUNT_VALUE, MIN_ORDER_AMOUNT, MAX_DISCOUNT_AMOUNT,
                        START_DATE, END_DATE, USAGE_LIMIT, USAGE_PER_CUSTOMER, IS_ACTIVE, CREATED_AT
                    ) VALUES (
                        :promotion_id, :promotion_code, :promotion_name, :promotion_type,
                        :discount_value, :min_order_amount, :max_discount_amount,
                        :start_date, :end_date, :usage_limit, :usage_per_customer, 1, SYSTIMESTAMP
                    )
                    """,
                    {
                        'promotion_id': promotion_id,
                        'promotion_code': data['promotion_code'].strip().upper(),
                        'promotion_name': data['promotion_name'].strip(),
                        'promotion_type': data['promotion_type'].strip().upper(),
                        'discount_value': data['discount_value'],
                        'min_order_amount': data.get('min_order_amount', 0) or 0,
                        'max_discount_amount': data.get('max_discount_amount'),
                        'start_date': data['start_date'],
                        'end_date': data['end_date'],
                        'usage_limit': data.get('usage_limit'),
                        'usage_per_customer': data.get('usage_per_customer', 1) or 1,
                    },
                )
                cur.execute(
                    """
                    INSERT INTO MH_COUPON (
                        COUPON_ID, PROMOTION_ID, COUPON_CODE, IS_ACTIVE, CREATED_AT
                    ) VALUES (
                        :coupon_id, :promotion_id, :coupon_code, 1, SYSTIMESTAMP
                    )
                    """,
                    {
                        'coupon_id': coupon_id,
                        'promotion_id': promotion_id,
                        'coupon_code': data['coupon_code'].strip().upper(),
                    },
                )
            conn.commit()
        promo = get_promotion(promotion_id)
        return True, 'Promotion created', promo
    except Exception as exc:  # noqa: BLE001
        return False, str(exc), None


def update_promotion(
    promotion_id: int,
    *,
    coupon_id: int,
    data: Dict[str, Any],
) -> Tuple[bool, str]:
    if not promotions_tables_ready():
        return False, _table_missing_message()

    promo_sets: List[str] = []
    promo_params: Dict[str, Any] = {'promotion_id': int(promotion_id)}
    field_map = {
        'promotion_name': 'PROMOTION_NAME',
        'discount_value': 'DISCOUNT_VALUE',
        'min_order_amount': 'MIN_ORDER_AMOUNT',
        'max_discount_amount': 'MAX_DISCOUNT_AMOUNT',
        'end_date': 'END_DATE',
        'usage_limit': 'USAGE_LIMIT',
    }
    for key, column in field_map.items():
        if key in data:
            promo_sets.append(f'{column} = :{key}')
            promo_params[key] = data[key]

    if 'is_active' in data and data['is_active'] is not None:
        promo_sets.append('IS_ACTIVE = :is_active')
        promo_params['is_active'] = 1 if data['is_active'] else 0

    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                if promo_sets:
                    cur.execute(
                        f"UPDATE MH_PROMOTION SET {', '.join(promo_sets)} "
                        f'WHERE PROMOTION_ID = :promotion_id',
                        promo_params,
                    )
                if 'coupon_is_active' in data and data['coupon_is_active'] is not None:
                    cur.execute(
                        """
                        UPDATE MH_COUPON SET IS_ACTIVE = :is_active
                        WHERE COUPON_ID = :coupon_id
                        """,
                        {
                            'coupon_id': int(coupon_id),
                            'is_active': 1 if data['coupon_is_active'] else 0,
                        },
                    )
            conn.commit()
        return True, 'Promotion updated'
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def toggle_promotion_active(promotion_id: int) -> Tuple[bool, str]:
    promo = get_promotion(promotion_id)
    if not promo:
        return False, 'Promotion not found'
    currently_active = int(promo.get('promotion_active') or 0) == 1
    new_active = not currently_active
    return update_promotion(
        promotion_id,
        coupon_id=int(promo['coupon_id']),
        data={'is_active': new_active, 'coupon_is_active': new_active},
    )


def format_datetime_local(value: Any) -> str:
    if value is None:
        return ''
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text:
            return ''
        text = text.replace('T', ' ')
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
            try:
                dt = datetime.strptime(text[:19] if fmt != '%Y-%m-%d' else text[:10], fmt)
                break
            except ValueError:
                dt = None
        if dt is None:
            return text[:16].replace(' ', 'T')
    return dt.strftime('%Y-%m-%dT%H:%M')
