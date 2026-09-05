"""MH_REVIEW queries for the ecommerce addon."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from db import _get_connection, _safe_rows, _table_exists

REVIEW_TABLE = 'MH_REVIEW'

ALLOWED_STATUSES = frozenset({'PENDING', 'APPROVED', 'REJECTED', 'HIDDEN'})
MODERATION_STATUSES = frozenset({'APPROVED', 'REJECTED', 'HIDDEN'})


def reviews_table_ready() -> bool:
    return _table_exists(REVIEW_TABLE)


def _table_missing_message() -> str:
    return (
        'MH_REVIEW table is not installed in this database. '
        'Run MamaHub schema script sql/02_tables/14_mh_reviews_cms_notifications.sql on the tenant DB.'
    )


def pending_review_count() -> int:
    if not reviews_table_ready():
        return 0
    rows = _safe_rows(
        "SELECT COUNT(*) AS cnt FROM MH_REVIEW WHERE STATUS = 'PENDING'",
        {},
    )
    return int(rows[0]['cnt']) if rows else 0


def list_reviews(
    *,
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = 'PENDING',
    search: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], int, Optional[str]]:
    if not reviews_table_ready():
        return [], 0, _table_missing_message()

    page = max(1, int(page or 1))
    page_size = max(1, min(int(page_size or 20), 100))
    offset = (page - 1) * page_size

    where = ['1=1']
    params: Dict[str, Any] = {
        'max_row': offset + page_size,
        'min_row': offset,
    }
    if status:
        status_up = status.strip().upper()
        if status_up in ALLOWED_STATUSES:
            where.append('r.STATUS = :status')
            params['status'] = status_up
    if search:
        where.append(
            "(TO_CHAR(r.ITEM_CODE) LIKE :search OR UPPER(NVL(r.TITLE, '')) LIKE :search "
            "OR UPPER(NVL(r.REVIEW_TEXT, '')) LIKE :search OR UPPER(NVL(u.EMAIL, '')) LIKE :search "
            "OR UPPER(NVL(u.FIRST_NAME || ' ' || u.LAST_NAME, '')) LIKE :search)"
        )
        params['search'] = f'%{search.strip().upper()}%'

    where_sql = ' AND '.join(where)
    count_rows = _safe_rows(
        f"""
        SELECT COUNT(*) AS cnt
        FROM MH_REVIEW r
        LEFT JOIN APP_USER u ON u.USER_ID = r.USER_ID
        WHERE {where_sql}
        """,
        params,
    )
    total = int(count_rows[0]['cnt']) if count_rows else 0

    order = 'r.CREATED_AT ASC' if (status or '').upper() == 'PENDING' else 'r.CREATED_AT DESC'
    rows = _safe_rows(
        f"""
        SELECT * FROM (
            SELECT inner_q.*, ROWNUM rnum FROM (
                SELECT
                    r.REVIEW_ID AS review_id,
                    r.USER_ID AS user_id,
                    r.LOCATION_CODE AS location_code,
                    r.ITEM_CODE AS item_code,
                    r.ORDER_ID AS order_id,
                    r.RATING AS rating,
                    r.TITLE AS title,
                    r.REVIEW_TEXT AS review_text,
                    r.IS_VERIFIED_PURCHASE AS is_verified_purchase,
                    r.HELPFUL_COUNT AS helpful_count,
                    r.STATUS AS status,
                    r.CREATED_AT AS created_at,
                    u.EMAIL AS reviewer_email,
                    u.FIRST_NAME AS reviewer_first_name,
                    u.LAST_NAME AS reviewer_last_name,
                    im.ITEMNAME AS item_name
                FROM MH_REVIEW r
                LEFT JOIN APP_USER u ON u.USER_ID = r.USER_ID
                LEFT JOIN ITEMMASTER im
                    ON im.ITEMCODE = r.ITEM_CODE
                   AND im.LOCATIONCODE = r.LOCATION_CODE
                WHERE {where_sql}
                ORDER BY {order}
            ) inner_q
            WHERE ROWNUM <= :max_row
        )
        WHERE rnum > :min_row
        """,
        params,
    )
    for row in rows:
        first = (row.get('reviewer_first_name') or '').strip()
        last = (row.get('reviewer_last_name') or '').strip()
        row['reviewer_name'] = f'{first} {last}'.strip() or row.get('reviewer_email') or 'Customer'
    return rows, total, None


def get_review(review_id: int) -> Optional[Dict[str, Any]]:
    if not reviews_table_ready():
        return None
    result = _safe_rows(
        """
        SELECT
            r.REVIEW_ID AS review_id,
            r.USER_ID AS user_id,
            r.LOCATION_CODE AS location_code,
            r.ITEM_CODE AS item_code,
            r.ORDER_ID AS order_id,
            r.RATING AS rating,
            r.TITLE AS title,
            r.REVIEW_TEXT AS review_text,
            r.IS_VERIFIED_PURCHASE AS is_verified_purchase,
            r.HELPFUL_COUNT AS helpful_count,
            r.STATUS AS status,
            r.CREATED_AT AS created_at,
            u.EMAIL AS reviewer_email,
            u.FIRST_NAME AS reviewer_first_name,
            u.LAST_NAME AS reviewer_last_name,
            im.ITEMNAME AS item_name
        FROM MH_REVIEW r
        LEFT JOIN APP_USER u ON u.USER_ID = r.USER_ID
        LEFT JOIN ITEMMASTER im
            ON im.ITEMCODE = r.ITEM_CODE
           AND im.LOCATIONCODE = r.LOCATION_CODE
        WHERE r.REVIEW_ID = :review_id
        """,
        {'review_id': int(review_id)},
    )
    if not result:
        return None
    row = dict(result[0])
    first = (row.get('reviewer_first_name') or '').strip()
    last = (row.get('reviewer_last_name') or '').strip()
    row['reviewer_name'] = f'{first} {last}'.strip() or row.get('reviewer_email') or 'Customer'
    return row


def update_review_status(review_id: int, status: str) -> Tuple[bool, str]:
    if not reviews_table_ready():
        return False, _table_missing_message()
    status_up = (status or '').strip().upper()
    if status_up not in MODERATION_STATUSES:
        return False, f'Invalid status: {status_up}'

    existing = _safe_rows(
        'SELECT REVIEW_ID FROM MH_REVIEW WHERE REVIEW_ID = :review_id',
        {'review_id': int(review_id)},
    )
    if not existing:
        return False, 'Review not found'

    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE MH_REVIEW
                    SET STATUS = :status,
                        MODIFIED_AT = SYSTIMESTAMP
                    WHERE REVIEW_ID = :review_id
                    """,
                    {'status': status_up, 'review_id': int(review_id)},
                )
            conn.commit()
        return True, f'Review marked {status_up}'
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
