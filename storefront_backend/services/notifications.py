"""In-app notifications."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from db import _get_connection, _safe_rows, _table_exists


def _ready() -> bool:
    return _table_exists('MH_NOTIFICATION')


def _next_id() -> int:
    rows = _safe_rows('SELECT SEQ_MH_NOTIFICATION_ID.NEXTVAL AS id FROM DUAL', {})
    return int(rows[0]['id'])


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def create_notification(
    *,
    user_id: int,
    notification_type: str,
    title: str,
    body: Optional[str] = None,
    ref_entity: Optional[str] = None,
    ref_entity_id: Optional[int] = None,
) -> Optional[int]:
    if not _ready():
        return None
    notification_id = _next_id()
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO MH_NOTIFICATION (
                    NOTIFICATION_ID, USER_ID, CHANNEL, NOTIFICATION_TYPE,
                    TITLE, BODY, REF_ENTITY, REF_ENTITY_ID, IS_READ, CREATED_AT
                ) VALUES (
                    :id, :user_id, 'IN_APP', :ntype,
                    :title, :body, :ref_entity, :ref_entity_id, 0, SYSTIMESTAMP
                )
                """,
                {
                    'id': notification_id,
                    'user_id': int(user_id),
                    'ntype': notification_type,
                    'title': title,
                    'body': body,
                    'ref_entity': ref_entity,
                    'ref_entity_id': ref_entity_id,
                },
            )
        conn.commit()
    return notification_id


def notify_order_confirmed(*, user_id: int, order_number: str, order_id: int) -> None:
    create_notification(
        user_id=user_id,
        notification_type='ORDER_CONFIRMED',
        title='Order confirmed',
        body=f'Your order {order_number} has been placed successfully.',
        ref_entity='ORDER',
        ref_entity_id=order_id,
    )


def list_for_user(user_id: int, *, unread_only: bool = False, limit: int = 50) -> List[Dict[str, Any]]:
    if not _ready():
        return []
    where = 'USER_ID = :user_id'
    if unread_only:
        where += ' AND IS_READ = 0'
    rows = _safe_rows(
        f"""
        SELECT * FROM (
            SELECT NOTIFICATION_ID AS notification_id,
                   NOTIFICATION_TYPE AS notification_type,
                   TITLE AS title, BODY AS body,
                   REF_ENTITY AS ref_entity, REF_ENTITY_ID AS ref_entity_id,
                   IS_READ AS is_read, CREATED_AT AS created_at
            FROM MH_NOTIFICATION
            WHERE {where}
            ORDER BY CREATED_AT DESC
        ) WHERE ROWNUM <= :limit
        """,
        {'user_id': int(user_id), 'limit': int(limit)},
    )
    for row in rows:
        row['is_read'] = int(row.get('is_read') or 0) == 1
        row['created_at'] = _iso(row.get('created_at'))
    return rows


def unread_count(user_id: int) -> int:
    if not _ready():
        return 0
    rows = _safe_rows(
        """
        SELECT COUNT(*) AS cnt FROM MH_NOTIFICATION
        WHERE USER_ID = :user_id AND IS_READ = 0
        """,
        {'user_id': int(user_id)},
    )
    return int(rows[0]['cnt']) if rows else 0


def mark_read(user_id: int, notification_id: int) -> None:
    if not _ready():
        return
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE MH_NOTIFICATION
                SET IS_READ = 1, READ_AT = SYSTIMESTAMP
                WHERE NOTIFICATION_ID = :id AND USER_ID = :user_id
                """,
                {'id': int(notification_id), 'user_id': int(user_id)},
            )
        conn.commit()


def mark_all_read(user_id: int) -> None:
    if not _ready():
        return
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE MH_NOTIFICATION
                SET IS_READ = 1, READ_AT = SYSTIMESTAMP
                WHERE USER_ID = :user_id AND IS_READ = 0
                """,
                {'user_id': int(user_id)},
            )
        conn.commit()
