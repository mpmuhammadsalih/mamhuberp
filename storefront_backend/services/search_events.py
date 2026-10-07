"""Log storefront searches that returned no products (for ecommerce Assist)."""
from __future__ import annotations

import logging
from typing import Optional

from db import _get_connection, _safe_rows, _table_exists

from storefront_backend.services.schema_bootstrap import ensure_search_event_schema

logger = logging.getLogger(__name__)


def _norm_query(query: str) -> str:
    return ' '.join((query or '').strip().lower().split())[:200]


def maybe_log_zero_result(
    *,
    query: Optional[str],
    total: int,
    page: int = 1,
    user_id: Optional[int] = None,
) -> None:
    text = (query or '').strip()
    if page != 1 or not text or int(total or 0) > 0:
        return
    try:
        ensure_search_event_schema()
        if not _table_exists('MH_SEARCH_EVENT'):
            return
        norm = _norm_query(text)
        if not norm:
            return
        params = {'norm': norm}
        recent_sql = """
            SELECT EVENT_ID AS event_id
            FROM MH_SEARCH_EVENT
            WHERE QUERY_NORM = :norm
              AND CREATED_AT > SYSTIMESTAMP - NUMTODSINTERVAL(2, 'HOUR')
        """
        if user_id is not None:
            recent_sql += ' AND USER_ID = :user_id'
            params['user_id'] = int(user_id)
        else:
            recent_sql += ' AND USER_ID IS NULL'
        recent_sql += ' FETCH FIRST 1 ROWS ONLY'
        if _safe_rows(recent_sql, params):
            return
        rows = _safe_rows('SELECT SEQ_MH_SEARCH_EVENT_ID.NEXTVAL AS id FROM DUAL', {})
        event_id = int(rows[0]['id'])
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO MH_SEARCH_EVENT (
                        EVENT_ID, USER_ID, QUERY_TEXT, QUERY_NORM, RESULT_COUNT, CREATED_AT
                    ) VALUES (
                        :event_id, :user_id, :query_text, :query_norm, 0, SYSTIMESTAMP
                    )
                    """,
                    {
                        'event_id': event_id,
                        'user_id': int(user_id) if user_id is not None else None,
                        'query_text': text[:200],
                        'query_norm': norm,
                    },
                )
            conn.commit()
    except Exception:
        logger.exception('Failed to log zero-result search')
