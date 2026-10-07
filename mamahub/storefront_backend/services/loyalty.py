"""Loyalty program for storefront customers."""
from __future__ import annotations

import math
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from db import _get_connection, _safe_rows, _table_exists


def _ready() -> bool:
    return _table_exists('MH_LOYALTY_RULE') and _table_exists('MH_LOYALTY_ACCOUNT')


def _next_id(sequence: str) -> int:
    rows = _safe_rows(f'SELECT {sequence}.NEXTVAL AS id FROM DUAL', {})
    return int(rows[0]['id'])


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def get_active_rule() -> Optional[Dict[str, Any]]:
    if not _table_exists('MH_LOYALTY_RULE'):
        return None
    rows = _safe_rows(
        """
        SELECT RULE_ID AS rule_id, RULE_CODE AS rule_code, RULE_NAME AS rule_name,
               EARN_SPEND_AMOUNT AS earn_spend_amount, EARN_POINTS AS earn_points,
               REDEEM_POINTS AS redeem_points, REDEEM_VALUE AS redeem_value,
               MIN_REDEEM_POINTS AS min_redeem_points,
               MAX_REDEEM_PERCENT AS max_redeem_percent,
               POINTS_EXPIRY_DAYS AS points_expiry_days
        FROM MH_LOYALTY_RULE
        WHERE IS_ACTIVE = 1
        ORDER BY RULE_ID
        FETCH FIRST 1 ROWS ONLY
        """,
        {},
    )
    return dict(rows[0]) if rows else None


def list_tiers() -> List[Dict[str, Any]]:
    if not _table_exists('MH_LOYALTY_TIER'):
        return []
    return _safe_rows(
        """
        SELECT TIER_ID AS tier_id, TIER_CODE AS tier_code, TIER_NAME AS tier_name,
               MIN_LIFETIME_POINTS AS min_lifetime_points,
               BONUS_EARN_PERCENT AS bonus_earn_percent
        FROM MH_LOYALTY_TIER
        WHERE IS_ACTIVE = 1
        ORDER BY SORT_ORDER, MIN_LIFETIME_POINTS
        """,
        {},
    )


def get_account(user_id: int) -> Optional[Dict[str, Any]]:
    if not _table_exists('MH_LOYALTY_ACCOUNT'):
        return None
    rows = _safe_rows(
        """
        SELECT a.ACCOUNT_ID AS account_id, a.USER_ID AS user_id,
               a.MEMBERSHIP_NUMBER AS membership_number,
               a.POINTS_BALANCE AS points_balance,
               a.LIFETIME_POINTS AS lifetime_points,
               a.LIFETIME_SPEND AS lifetime_spend,
               t.TIER_CODE AS tier_code, t.TIER_NAME AS tier_name
        FROM MH_LOYALTY_ACCOUNT a
        LEFT JOIN MH_LOYALTY_TIER t ON t.TIER_ID = a.TIER_ID
        WHERE a.USER_ID = :user_id AND a.IS_ACTIVE = 1
        """,
        {'user_id': int(user_id)},
    )
    return dict(rows[0]) if rows else None


def create_account(user_id: int) -> Dict[str, Any]:
    account_id = _next_id('SEQ_MH_LOYALTY_ACCOUNT_ID')
    membership = f'MH-{uuid.uuid4().hex[:8].upper()}'
    tier_rows = _safe_rows(
        """
        SELECT TIER_ID AS tier_id FROM MH_LOYALTY_TIER
        WHERE TIER_CODE = 'BRONZE' AND IS_ACTIVE = 1
        """,
        {},
    )
    tier_id = int(tier_rows[0]['tier_id']) if tier_rows else None
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO MH_LOYALTY_ACCOUNT (
                    ACCOUNT_ID, USER_ID, MEMBERSHIP_NUMBER, TIER_ID,
                    POINTS_BALANCE, LIFETIME_POINTS, LIFETIME_SPEND, IS_ACTIVE, CREATED_AT
                ) VALUES (
                    :account_id, :user_id, :membership, :tier_id,
                    0, 0, 0, 1, SYSTIMESTAMP
                )
                """,
                {
                    'account_id': account_id,
                    'user_id': int(user_id),
                    'membership': membership,
                    'tier_id': tier_id,
                },
            )
        conn.commit()
    return get_account(user_id) or {
        'account_id': account_id,
        'user_id': user_id,
        'points_balance': 0,
        'lifetime_points': 0,
    }


def get_or_create_account(user_id: int) -> Dict[str, Any]:
    account = get_account(user_id)
    if account:
        return account
    return create_account(user_id)


def list_transactions(user_id: int, *, limit: int = 20) -> List[Dict[str, Any]]:
    if not _table_exists('MH_LOYALTY_TRANSACTION'):
        return []
    rows = _safe_rows(
        """
        SELECT * FROM (
            SELECT TRANSACTION_ID AS transaction_id,
                   TRANSACTION_TYPE AS transaction_type,
                   POINTS AS points, ORDER_ID AS order_id,
                   DESCRIPTION AS description,
                   BALANCE_AFTER AS balance_after,
                   CREATED_AT AS created_at
            FROM MH_LOYALTY_TRANSACTION
            WHERE USER_ID = :user_id
            ORDER BY CREATED_AT DESC
        ) WHERE ROWNUM <= :limit
        """,
        {'user_id': int(user_id), 'limit': int(limit)},
    )
    for row in rows:
        row['created_at'] = _iso(row.get('created_at'))
    return rows


def get_dashboard(user_id: int) -> Dict[str, Any]:
    if not _ready():
        raise ValueError('Loyalty program not configured')
    account = get_or_create_account(user_id)
    rule = get_active_rule()
    if not rule:
        raise ValueError('Loyalty program not configured')
    tiers = list_tiers()
    transactions = list_transactions(user_id, limit=20)
    next_tier = None
    lifetime = int(account.get('lifetime_points') or 0)
    for tier in tiers:
        if int(tier['min_lifetime_points']) > lifetime:
            next_tier = tier
            break
    return {
        'account': account,
        'rule': {
            'earn_spend_amount': float(rule['earn_spend_amount']),
            'earn_points': int(rule['earn_points']),
            'redeem_points': int(rule['redeem_points']),
            'redeem_value': float(rule['redeem_value']),
            'min_redeem_points': int(rule['min_redeem_points']),
            'max_redeem_percent': float(rule['max_redeem_percent']),
        },
        'tiers': tiers,
        'next_tier': next_tier,
        'transactions': transactions,
    }


def points_to_discount(points: int) -> float:
    rule = get_active_rule()
    if not rule:
        return 0.0
    redeem_pts = int(rule['redeem_points'])
    redeem_val = float(rule['redeem_value'])
    if redeem_pts <= 0:
        return 0.0
    return round((points / redeem_pts) * redeem_val, 2)


def max_redeemable_points(
    *,
    user_id: int,
    order_subtotal: float,
    existing_discount: float = 0.0,
) -> int:
    account = get_or_create_account(user_id)
    rule = get_active_rule()
    if not rule:
        return 0
    balance = int(account.get('points_balance') or 0)
    min_pts = int(rule['min_redeem_points'])
    if balance < min_pts:
        return 0
    max_pct = float(rule['max_redeem_percent']) / 100.0
    max_discount = max(order_subtotal - existing_discount, 0) * max_pct
    redeem_pts = int(rule['redeem_points'])
    redeem_val = float(rule['redeem_value'])
    if redeem_val <= 0:
        return 0
    max_pts_by_order = int(math.floor((max_discount / redeem_val) * redeem_pts))
    return max(0, min(balance, max_pts_by_order))


def validate_redeem(
    *,
    user_id: int,
    points: int,
    order_subtotal: float,
    existing_discount: float,
) -> float:
    rule = get_active_rule()
    if not rule:
        raise ValueError('Loyalty program not configured')
    min_pts = int(rule['min_redeem_points'])
    if points < min_pts:
        raise ValueError(f'Minimum {min_pts} points required to redeem')
    max_pts = max_redeemable_points(
        user_id=user_id,
        order_subtotal=order_subtotal,
        existing_discount=existing_discount,
    )
    if points > max_pts:
        raise ValueError(f'Maximum redeemable points for this order: {max_pts}')
    return points_to_discount(points)


def _resolve_tier_for_points(lifetime_points: int) -> Optional[int]:
    rows = _safe_rows(
        """
        SELECT TIER_ID AS tier_id FROM MH_LOYALTY_TIER
        WHERE IS_ACTIVE = 1 AND MIN_LIFETIME_POINTS <= :pts
        ORDER BY MIN_LIFETIME_POINTS DESC
        FETCH FIRST 1 ROWS ONLY
        """,
        {'pts': int(lifetime_points)},
    )
    return int(rows[0]['tier_id']) if rows else None


def redeem_points(
    *,
    user_id: int,
    points: int,
    order_id: int,
    description: str,
) -> None:
    account = get_or_create_account(user_id)
    balance = int(account['points_balance'])
    if points > balance:
        raise ValueError('Insufficient loyalty points')
    new_balance = balance - points
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE MH_LOYALTY_ACCOUNT
                SET POINTS_BALANCE = :balance, MODIFIED_AT = SYSTIMESTAMP
                WHERE ACCOUNT_ID = :account_id
                """,
                {'balance': new_balance, 'account_id': int(account['account_id'])},
            )
            tx_id = _next_id('SEQ_MH_LOYALTY_TRANSACTION_ID')
            cur.execute(
                """
                INSERT INTO MH_LOYALTY_TRANSACTION (
                    TRANSACTION_ID, ACCOUNT_ID, USER_ID, TRANSACTION_TYPE,
                    POINTS, ORDER_ID, DESCRIPTION, BALANCE_AFTER, CREATED_AT
                ) VALUES (
                    :id, :account_id, :user_id, 'REDEEM',
                    :points, :order_id, :description, :balance_after, SYSTIMESTAMP
                )
                """,
                {
                    'id': tx_id,
                    'account_id': int(account['account_id']),
                    'user_id': int(user_id),
                    'points': -int(points),
                    'order_id': int(order_id),
                    'description': description,
                    'balance_after': new_balance,
                },
            )
        conn.commit()


def calculate_earn_points(order_total: float) -> int:
    rule = get_active_rule()
    if not rule:
        return 0
    spend = float(rule['earn_spend_amount'])
    earn = int(rule['earn_points'])
    if spend <= 0:
        return 0
    return int(math.floor(order_total / spend) * earn)


def earn_points(
    *,
    user_id: int,
    order_id: int,
    order_total: float,
    description: str,
) -> int:
    account = get_or_create_account(user_id)
    base_points = calculate_earn_points(order_total)
    tier_code = account.get('tier_code')
    bonus_pct = 0.0
    for tier in list_tiers():
        if tier['tier_code'] == tier_code:
            bonus_pct = float(tier.get('bonus_earn_percent') or 0)
            break
    bonus = int(math.floor(base_points * bonus_pct / 100)) if bonus_pct else 0
    earned = base_points + bonus
    if earned <= 0:
        return 0

    new_balance = int(account['points_balance']) + earned
    new_lifetime = int(account['lifetime_points']) + earned
    new_spend = float(account.get('lifetime_spend') or 0) + order_total
    tier_id = _resolve_tier_for_points(new_lifetime)

    with _get_connection() as conn:
        with conn.cursor() as cur:
            params = {
                'balance': new_balance,
                'lifetime_points': new_lifetime,
                'lifetime_spend': new_spend,
                'account_id': int(account['account_id']),
            }
            tier_sql = ''
            if tier_id is not None:
                tier_sql = ', TIER_ID = :tier_id'
                params['tier_id'] = tier_id
            cur.execute(
                f"""
                UPDATE MH_LOYALTY_ACCOUNT
                SET POINTS_BALANCE = :balance,
                    LIFETIME_POINTS = :lifetime_points,
                    LIFETIME_SPEND = :lifetime_spend,
                    MODIFIED_AT = SYSTIMESTAMP
                    {tier_sql}
                WHERE ACCOUNT_ID = :account_id
                """,
                params,
            )
            tx_id = _next_id('SEQ_MH_LOYALTY_TRANSACTION_ID')
            cur.execute(
                """
                INSERT INTO MH_LOYALTY_TRANSACTION (
                    TRANSACTION_ID, ACCOUNT_ID, USER_ID, TRANSACTION_TYPE,
                    POINTS, ORDER_ID, DESCRIPTION, BALANCE_AFTER, CREATED_AT
                ) VALUES (
                    :id, :account_id, :user_id, :tx_type,
                    :points, :order_id, :description, :balance_after, SYSTIMESTAMP
                )
                """,
                {
                    'id': tx_id,
                    'account_id': int(account['account_id']),
                    'user_id': int(user_id),
                    'tx_type': 'EARN' if bonus == 0 else 'BONUS',
                    'points': earned,
                    'order_id': int(order_id),
                    'description': description,
                    'balance_after': new_balance,
                },
            )
        conn.commit()
    return earned


def checkout_loyalty_info(
    *,
    user_id: int,
    order_subtotal: float,
    existing_discount: float,
    session: Dict[str, Any],
) -> Dict[str, Any]:
    if not _ready():
        return {}
    try:
        account = get_or_create_account(user_id)
        max_pts = max_redeemable_points(
            user_id=user_id,
            order_subtotal=order_subtotal,
            existing_discount=existing_discount,
        )
        return {
            'points_balance': int(account.get('points_balance') or 0),
            'max_redeemable_points': max_pts,
            'points_redeemed': int(session.get('loyalty_points_redeemed') or 0),
            'loyalty_discount': float(session.get('loyalty_discount') or 0),
            'tier_code': account.get('tier_code'),
        }
    except Exception:  # noqa: BLE001
        return {}
