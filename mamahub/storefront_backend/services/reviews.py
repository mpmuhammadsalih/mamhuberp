"""Product reviews for storefront."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from db import _get_connection, _safe_rows, _table_exists

from storefront_backend.deps import resolve_location_code
from storefront_backend.services import catalog as catalog_svc
from storefront_backend.utils.response import build_pagination_meta


def _ready() -> bool:
    return _table_exists('MH_REVIEW')


def _next_id() -> int:
    rows = _safe_rows('SELECT SEQ_MH_REVIEW_ID.NEXTVAL AS id FROM DUAL', {})
    return int(rows[0]['id'])


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def list_product_reviews(
    item_code: int,
    *,
    location_code: Optional[int] = None,
    page: int = 1,
    page_size: int = 10,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], Dict[str, Any]]:
    if not _ready():
        meta = build_pagination_meta(page=page, page_size=page_size, total_records=0)
        return [], meta, {'review_count': 0, 'avg_rating': 0.0}

    loc = resolve_location_code(location_code)
    page = max(1, int(page))
    page_size = max(1, min(int(page_size), 50))
    offset = (page - 1) * page_size

    count_rows = _safe_rows(
        """
        SELECT COUNT(*) AS cnt FROM MH_REVIEW
        WHERE LOCATION_CODE = :location_code AND ITEM_CODE = :item_code
          AND STATUS = 'APPROVED'
        """,
        {'location_code': loc, 'item_code': int(item_code)},
    )
    total = int(count_rows[0]['cnt']) if count_rows else 0

    rows = _safe_rows(
        """
        SELECT * FROM (
            SELECT inner_q.*, ROWNUM rnum FROM (
                SELECT r.REVIEW_ID AS review_id, r.USER_ID AS user_id,
                       r.RATING AS rating, r.TITLE AS title,
                       r.REVIEW_TEXT AS review_text,
                       r.IS_VERIFIED_PURCHASE AS is_verified_purchase,
                       r.HELPFUL_COUNT AS helpful_count,
                       r.CREATED_AT AS created_at,
                       u.FIRST_NAME AS first_name, u.LAST_NAME AS last_name
                FROM MH_REVIEW r
                JOIN APP_USER u ON u.USER_ID = r.USER_ID
                WHERE r.LOCATION_CODE = :location_code AND r.ITEM_CODE = :item_code
                  AND r.STATUS = 'APPROVED'
                ORDER BY r.CREATED_AT DESC
            ) inner_q
            WHERE ROWNUM <= :max_row
        )
        WHERE rnum > :min_row
        """,
        {
            'location_code': loc,
            'item_code': int(item_code),
            'max_row': offset + page_size,
            'min_row': offset,
        },
    )
    for row in rows:
        row['created_at'] = _iso(row.get('created_at'))
        row['is_verified_purchase'] = int(row.get('is_verified_purchase') or 0) == 1
        first = (row.get('first_name') or '').strip()
        last = (row.get('last_name') or '').strip()
        row['reviewer_name'] = f'{first} {last}'.strip() or 'Customer'

    summary_rows = _safe_rows(
        """
        SELECT COUNT(*) AS review_count,
               NVL(AVG(RATING), 0) AS avg_rating
        FROM MH_REVIEW
        WHERE LOCATION_CODE = :location_code AND ITEM_CODE = :item_code
          AND STATUS = 'APPROVED'
        """,
        {'location_code': loc, 'item_code': int(item_code)},
    )
    summary_row = summary_rows[0] if summary_rows else {}
    summary = {
        'review_count': int(summary_row.get('review_count') or 0),
        'avg_rating': round(float(summary_row.get('avg_rating') or 0), 1),
    }
    meta = build_pagination_meta(page=page, page_size=page_size, total_records=total)
    return rows, meta, summary


def submit_review(
    user_id: int,
    *,
    item_code: int,
    rating: int,
    title: Optional[str] = None,
    review_text: Optional[str] = None,
    location_code: Optional[int] = None,
    order_id: Optional[int] = None,
) -> Dict[str, Any]:
    if not _ready():
        raise ValueError('Reviews are not available')
    loc = resolve_location_code(location_code)
    product = catalog_svc.get_product(int(item_code), location_code=loc)
    if not product:
        raise ValueError('Product not found')

    is_verified = False
    if order_id:
        order_rows = _safe_rows(
            """
            SELECT ORDER_ID FROM MH_ORDER
            WHERE ORDER_ID = :order_id AND USER_ID = :user_id
            """,
            {'order_id': int(order_id), 'user_id': int(user_id)},
        )
        is_verified = bool(order_rows)

    review_id = _next_id()
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO MH_REVIEW (
                    REVIEW_ID, USER_ID, LOCATION_CODE, ITEM_CODE, ORDER_ID,
                    RATING, TITLE, REVIEW_TEXT, IS_VERIFIED_PURCHASE, STATUS, CREATED_AT
                ) VALUES (
                    :id, :user_id, :location_code, :item_code, :order_id,
                    :rating, :title, :review_text, :verified, 'PENDING', SYSTIMESTAMP
                )
                """,
                {
                    'id': review_id,
                    'user_id': int(user_id),
                    'location_code': loc,
                    'item_code': int(item_code),
                    'order_id': order_id,
                    'rating': int(rating),
                    'title': title,
                    'review_text': review_text,
                    'verified': 1 if is_verified else 0,
                },
            )
        conn.commit()
    return {'review_id': review_id, 'status': 'PENDING'}
