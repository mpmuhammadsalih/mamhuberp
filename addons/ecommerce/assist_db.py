"""Queries for ecommerce Assist (abandoned carts, checkout, idle logins, failed searches)."""
from __future__ import annotations

from typing import Any, Dict, List

from db import _safe_rows, _table_exists

from storefront_backend.services.schema_bootstrap import ensure_cart_schema, ensure_search_event_schema


def _cart_ready() -> bool:
    if _table_exists('MH_CART') and _table_exists('MH_CART_ITEM'):
        return True
    try:
        ensure_cart_schema()
    except Exception:
        return False
    return _table_exists('MH_CART') and _table_exists('MH_CART_ITEM')


def _orders_ready() -> bool:
    return _table_exists('MH_ORDER')


def _users_ready() -> bool:
    return _table_exists('APP_USER')


def list_abandoned_carts(*, idle_minutes: int = 15, limit: int = 50) -> List[Dict[str, Any]]:
    if not _cart_ready() or not _users_ready():
        return []
    paid_filter = ''
    if _orders_ready():
        paid_filter = """
          AND NOT EXISTS (
            SELECT 1 FROM MH_ORDER o
            WHERE o.USER_ID = c.USER_ID
              AND o.CREATED_AT >= NVL(c.MODIFIED_AT, c.CREATED_AT)
              AND NVL(o.PAYMENT_STATUS, 'PENDING') NOT IN ('FAILED', 'CANCELLED')
              AND o.ORDER_STATUS NOT IN ('CANCELLED')
          )
        """
    return _safe_rows(
        f"""
        SELECT * FROM (
            SELECT
                c.CART_ID AS cart_id,
                c.USER_ID AS user_id,
                c.CART_STATUS AS cart_status,
                NVL(c.MODIFIED_AT, c.CREATED_AT) AS last_activity,
                u.FIRST_NAME AS first_name,
                u.LAST_NAME AS last_name,
                u.EMAIL AS email,
                u.MOBILE AS mobile,
                NVL(SUM(i.QUANTITY * i.UNIT_PRICE), 0) AS cart_total,
                COUNT(i.CART_ITEM_ID) AS item_count
            FROM MH_CART c
            JOIN APP_USER u ON u.USER_ID = c.USER_ID
              AND u.USER_TYPE = 'CUSTOMER'
              AND u.IS_ACTIVE = 1
            JOIN MH_CART_ITEM i ON i.CART_ID = c.CART_ID AND i.LINE_STATUS = 'ACTIVE'
            WHERE c.USER_ID IS NOT NULL
              AND c.CART_STATUS = 'ACTIVE'
              AND NVL(c.MODIFIED_AT, c.CREATED_AT) < SYSTIMESTAMP - NUMTODSINTERVAL(:idle, 'MINUTE')
              {paid_filter}
            GROUP BY
                c.CART_ID, c.USER_ID, c.CART_STATUS, NVL(c.MODIFIED_AT, c.CREATED_AT),
                u.FIRST_NAME, u.LAST_NAME, u.EMAIL, u.MOBILE
            HAVING COUNT(i.CART_ITEM_ID) > 0
            ORDER BY NVL(c.MODIFIED_AT, c.CREATED_AT) DESC
        )
        WHERE ROWNUM <= :limit
        """,
        {'idle': max(5, int(idle_minutes)), 'limit': max(1, min(int(limit), 100))},
    )


def list_failed_checkouts(*, limit: int = 50) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if _cart_ready() and _users_ready():
        rows.extend(
            _safe_rows(
                """
                SELECT * FROM (
                    SELECT
                        c.CART_ID AS cart_id,
                        NULL AS order_id,
                        NULL AS order_number,
                        c.USER_ID AS user_id,
                        'CHECKOUT' AS kind,
                        NVL(c.MODIFIED_AT, c.CREATED_AT) AS last_activity,
                        u.FIRST_NAME AS first_name,
                        u.LAST_NAME AS last_name,
                        u.EMAIL AS email,
                        u.MOBILE AS mobile,
                        NVL(SUM(i.QUANTITY * i.UNIT_PRICE), 0) AS amount,
                        COUNT(i.CART_ITEM_ID) AS item_count
                    FROM MH_CART c
                    JOIN APP_USER u ON u.USER_ID = c.USER_ID
                      AND u.USER_TYPE = 'CUSTOMER'
                      AND u.IS_ACTIVE = 1
                    JOIN MH_CART_ITEM i ON i.CART_ID = c.CART_ID AND i.LINE_STATUS = 'ACTIVE'
                    WHERE c.USER_ID IS NOT NULL
                      AND c.CART_STATUS = 'CHECKOUT'
                    GROUP BY
                        c.CART_ID, c.USER_ID, NVL(c.MODIFIED_AT, c.CREATED_AT),
                        u.FIRST_NAME, u.LAST_NAME, u.EMAIL, u.MOBILE
                    ORDER BY NVL(c.MODIFIED_AT, c.CREATED_AT) DESC
                )
                WHERE ROWNUM <= :limit
                """,
                {'limit': max(1, min(int(limit), 100))},
            )
        )
    if _orders_ready() and _users_ready():
        rows.extend(
            _safe_rows(
                """
                SELECT * FROM (
                    SELECT
                        o.CART_ID AS cart_id,
                        o.ORDER_ID AS order_id,
                        o.ORDER_NUMBER AS order_number,
                        o.USER_ID AS user_id,
                        'UNPAID_ORDER' AS kind,
                        NVL(o.MODIFIED_AT, o.CREATED_AT) AS last_activity,
                        u.FIRST_NAME AS first_name,
                        u.LAST_NAME AS last_name,
                        u.EMAIL AS email,
                        u.MOBILE AS mobile,
                        NVL(o.GRAND_TOTAL, 0) AS amount,
                        (SELECT COUNT(*) FROM MH_ORDER_ITEM oi WHERE oi.ORDER_ID = o.ORDER_ID) AS item_count
                    FROM MH_ORDER o
                    JOIN APP_USER u ON u.USER_ID = o.USER_ID
                      AND u.USER_TYPE = 'CUSTOMER'
                      AND u.IS_ACTIVE = 1
                    WHERE (
                        UPPER(NVL(o.PAYMENT_STATUS, 'PENDING')) IN ('PENDING', 'AWAITING_PAYMENT', 'FAILED')
                        OR UPPER(NVL(o.ORDER_STATUS, 'PENDING')) IN ('PENDING', 'AWAITING_PAYMENT')
                    )
                      AND UPPER(NVL(o.ORDER_STATUS, 'PENDING')) <> 'CANCELLED'
                    ORDER BY NVL(o.MODIFIED_AT, o.CREATED_AT) DESC
                )
                WHERE ROWNUM <= :limit
                """,
                {'limit': max(1, min(int(limit), 100))},
            )
        )
    rows.sort(key=lambda r: str(r.get('last_activity') or ''), reverse=True)
    return rows[: max(1, min(int(limit), 100))]


def list_idle_logins(*, hours: int = 72, limit: int = 50) -> List[Dict[str, Any]]:
    if not _users_ready():
        return []
    cart_filter = ''
    if _cart_ready():
        cart_filter = """
          AND NOT EXISTS (
            SELECT 1 FROM MH_CART c
            JOIN MH_CART_ITEM i ON i.CART_ID = c.CART_ID AND i.LINE_STATUS = 'ACTIVE'
            WHERE c.USER_ID = u.USER_ID
              AND c.CART_STATUS IN ('ACTIVE', 'CHECKOUT')
          )
        """
    order_filter = ''
    if _orders_ready():
        order_filter = """
          AND NOT EXISTS (
            SELECT 1 FROM MH_ORDER o
            WHERE o.USER_ID = u.USER_ID
              AND o.CREATED_AT >= u.LAST_LOGIN_AT
              AND o.ORDER_STATUS NOT IN ('CANCELLED')
          )
        """
    return _safe_rows(
        f"""
        SELECT * FROM (
            SELECT
                u.USER_ID AS user_id,
                u.FIRST_NAME AS first_name,
                u.LAST_NAME AS last_name,
                u.EMAIL AS email,
                u.MOBILE AS mobile,
                u.LAST_LOGIN_AT AS last_login_at,
                u.CREATED_AT AS created_at
            FROM APP_USER u
            WHERE u.USER_TYPE = 'CUSTOMER'
              AND u.IS_ACTIVE = 1
              AND u.LAST_LOGIN_AT IS NOT NULL
              AND u.LAST_LOGIN_AT > SYSTIMESTAMP - NUMTODSINTERVAL(:hours, 'HOUR')
              {cart_filter}
              {order_filter}
            ORDER BY u.LAST_LOGIN_AT DESC
        )
        WHERE ROWNUM <= :limit
        """,
        {'hours': max(1, int(hours)), 'limit': max(1, min(int(limit), 100))},
    )


def list_zero_searches(*, limit: int = 50) -> List[Dict[str, Any]]:
    try:
        ensure_search_event_schema()
    except Exception:
        return []
    if not _table_exists('MH_SEARCH_EVENT'):
        return []
    user_join = ''
    user_cols = """
                NULL AS first_name,
                NULL AS last_name,
                NULL AS email,
                NULL AS mobile,
    """
    if _users_ready():
        user_join = 'LEFT JOIN APP_USER u ON u.USER_ID = e.USER_ID'
        user_cols = """
                u.FIRST_NAME AS first_name,
                u.LAST_NAME AS last_name,
                u.EMAIL AS email,
                u.MOBILE AS mobile,
        """
    return _safe_rows(
        f"""
        SELECT * FROM (
            SELECT
                e.EVENT_ID AS event_id,
                e.USER_ID AS user_id,
                e.QUERY_TEXT AS query_text,
                e.CREATED_AT AS created_at,
                {user_cols}
                1 AS one
            FROM MH_SEARCH_EVENT e
            {user_join}
            WHERE e.RESULT_COUNT = 0
            ORDER BY e.CREATED_AT DESC
        )
        WHERE ROWNUM <= :limit
        """,
        {'limit': max(1, min(int(limit), 100))},
    )
