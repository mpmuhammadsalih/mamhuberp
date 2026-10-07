"""APP_USER customer queries for the ecommerce addon."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from db import _get_connection, _safe_rows, _table_exists

from storefront_backend.services.schema_bootstrap import (
    _invalidate_app_user_cache,
    ensure_app_user_schema,
)

USER_TABLE = 'APP_USER'
ACCOUNT_STATUSES = frozenset({'ACTIVE', 'INACTIVE', 'LOCKED', 'PENDING'})


def customers_table_ready() -> bool:
    if _table_exists(USER_TABLE):
        return True
    try:
        ensure_app_user_schema()
    except Exception:
        _invalidate_app_user_cache()
        return False
    return _table_exists(USER_TABLE)


def customer_count() -> int:
    if not customers_table_ready():
        return 0
    rows = _safe_rows(
        """
        SELECT COUNT(*) AS cnt
        FROM APP_USER
        WHERE USER_TYPE = 'CUSTOMER' AND IS_ACTIVE = 1
        """,
        {},
    )
    return int(rows[0]['cnt']) if rows else 0


def list_customers(
    *,
    page: int = 1,
    page_size: int = 20,
    search: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    if not customers_table_ready():
        return [], 0

    page = max(1, int(page or 1))
    page_size = max(1, min(int(page_size or 20), 100))
    offset = (page - 1) * page_size

    where = ["USER_TYPE = 'CUSTOMER'", 'IS_ACTIVE = 1']
    params: Dict[str, Any] = {
        'max_row': offset + page_size,
        'min_row': offset,
    }
    if search:
        where.append(
            "(UPPER(EMAIL) LIKE :search OR UPPER(FIRST_NAME || ' ' || LAST_NAME) LIKE :search)"
        )
        params['search'] = f'%{search.strip().upper()}%'

    where_sql = ' AND '.join(where)
    count_rows = _safe_rows(
        f"SELECT COUNT(*) AS cnt FROM APP_USER WHERE {where_sql}",
        params,
    )
    total = int(count_rows[0]['cnt']) if count_rows else 0

    rows = _safe_rows(
        f"""
        SELECT * FROM (
            SELECT inner_q.*, ROWNUM rnum FROM (
                SELECT
                    USER_ID AS user_id,
                    EMAIL AS email,
                    FIRST_NAME AS first_name,
                    LAST_NAME AS last_name,
                    ACCOUNT_STATUS AS account_status,
                    MOBILE AS mobile,
                    CREATED_AT AS created_at,
                    LAST_LOGIN_AT AS last_login_at
                FROM APP_USER
                WHERE {where_sql}
                ORDER BY USER_ID DESC
            ) inner_q
            WHERE ROWNUM <= :max_row
        )
        WHERE rnum > :min_row
        """,
        params,
    )
    return rows, total


def get_customer(user_id: int) -> Optional[Dict[str, Any]]:
    if not customers_table_ready():
        return None
    rows = _safe_rows(
        """
        SELECT
            USER_ID AS user_id,
            USERNAME AS username,
            EMAIL AS email,
            FIRST_NAME AS first_name,
            LAST_NAME AS last_name,
            MOBILE AS mobile,
            ACCOUNT_STATUS AS account_status,
            EMAIL_VERIFIED AS email_verified,
            MOBILE_VERIFIED AS mobile_verified,
            PREFERRED_LANGUAGE AS preferred_language,
            CREATED_AT AS created_at,
            LAST_LOGIN_AT AS last_login_at
        FROM APP_USER
        WHERE USER_ID = :user_id
          AND USER_TYPE = 'CUSTOMER'
          AND IS_ACTIVE = 1
        """,
        {'user_id': int(user_id)},
    )
    return dict(rows[0]) if rows else None


def update_customer_account_status(user_id: int, status: str) -> Tuple[bool, str]:
    """Set APP_USER.ACCOUNT_STATUS for a storefront customer."""
    if not customers_table_ready():
        return False, 'Customer table not available'
    new_status = (status or '').strip().upper()
    if new_status not in ACCOUNT_STATUSES:
        return False, f'Invalid status. Allowed: {", ".join(sorted(ACCOUNT_STATUSES))}'
    existing = get_customer(user_id)
    if not existing:
        return False, 'Customer not found'
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE APP_USER
                    SET ACCOUNT_STATUS = :status,
                        MODIFIED_AT = SYSTIMESTAMP
                    WHERE USER_ID = :user_id
                      AND USER_TYPE = 'CUSTOMER'
                      AND IS_ACTIVE = 1
                    """,
                    {'user_id': int(user_id), 'status': new_status},
                )
                if cur.rowcount <= 0:
                    return False, 'Customer not found'
            conn.commit()
        labels = {
            'ACTIVE': 'Customer activated',
            'INACTIVE': 'Customer suspended',
            'LOCKED': 'Customer account locked',
            'PENDING': 'Customer marked pending',
        }
        return True, labels.get(new_status, 'Account status updated')
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def list_customer_orders(user_id: int, *, limit: int = 50) -> List[Dict[str, Any]]:
    from addons.ecommerce import orders_db

    if not orders_db.orders_tables_ready():
        return []
    return _safe_rows(
        """
        SELECT
            o.ORDER_ID AS order_id,
            o.ORDER_NUMBER AS order_number,
            o.ORDER_STATUS AS order_status,
            o.GRAND_TOTAL AS grand_total,
            o.CURRENCY_CODE AS currency_code,
            o.CREATED_AT AS created_at
        FROM MH_ORDER o
        WHERE o.USER_ID = :user_id
        ORDER BY o.ORDER_ID DESC
        FETCH FIRST :limit ROWS ONLY
        """,
        {'user_id': int(user_id), 'limit': max(1, min(int(limit or 50), 200))},
    )


def customer_order_summary(user_id: int) -> Dict[str, Any]:
    from addons.ecommerce import orders_db

    if not orders_db.orders_tables_ready():
        return {'order_count': 0, 'total_spent': 0.0, 'last_order_at': None}
    rows = _safe_rows(
        """
        SELECT
            COUNT(*) AS order_count,
            NVL(SUM(GRAND_TOTAL), 0) AS total_spent,
            MAX(CREATED_AT) AS last_order_at
        FROM MH_ORDER
        WHERE USER_ID = :user_id
        """,
        {'user_id': int(user_id)},
    )
    row = rows[0] if rows else {}
    return {
        'order_count': int(row.get('order_count') or 0),
        'total_spent': float(row.get('total_spent') or 0),
        'last_order_at': row.get('last_order_at'),
    }
