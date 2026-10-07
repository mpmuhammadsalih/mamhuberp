"""MH_COMPARE_STORE — reusable names for product price comparison."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from db import _get_connection, _safe_rows, _table_exists

from addons.ecommerce.schema_bootstrap import ensure_compare_store_schema

STORE_TABLE = 'MH_COMPARE_STORE'
_NAME_MAX = 80
_URL_MAX = 500


def compare_stores_ready() -> bool:
    if _table_exists(STORE_TABLE):
        return True
    try:
        return bool(ensure_compare_store_schema())
    except Exception:  # noqa: BLE001
        return False


def _clean_name(value: Any) -> str:
    return ' '.join(str(value or '').split()).strip()[:_NAME_MAX]


def _clean_website(value: Any) -> Optional[str]:
    text = str(value or '').strip()
    if not text:
        return None
    if text.startswith('//'):
        text = f'https:{text}'
    lower = text.lower()
    if not (lower.startswith('http://') or lower.startswith('https://')):
        text = f'https://{text}'
    return text[:_URL_MAX]


def list_compare_stores(*, active_only: bool = False) -> List[Dict[str, Any]]:
    if not compare_stores_ready():
        return []
    where = 'WHERE IS_ACTIVE = 1' if active_only else ''
    return _safe_rows(
        f"""
        SELECT
            STORE_ID AS store_id,
            STORE_NAME AS store_name,
            WEBSITE_URL AS website_url,
            IS_ACTIVE AS is_active,
            SORT_ORDER AS sort_order
        FROM {STORE_TABLE}
        {where}
        ORDER BY SORT_ORDER, LOWER(STORE_NAME), STORE_ID
        """,
        {},
    )


def get_compare_store(store_id: int) -> Optional[Dict[str, Any]]:
    if not compare_stores_ready() or int(store_id or 0) <= 0:
        return None
    rows = _safe_rows(
        f"""
        SELECT
            STORE_ID AS store_id,
            STORE_NAME AS store_name,
            WEBSITE_URL AS website_url,
            IS_ACTIVE AS is_active,
            SORT_ORDER AS sort_order
        FROM {STORE_TABLE}
        WHERE STORE_ID = :store_id
        """,
        {'store_id': int(store_id)},
    )
    return dict(rows[0]) if rows else None


def find_store_id_by_name(name: str) -> Optional[int]:
    cleaned = _clean_name(name)
    if not cleaned or not compare_stores_ready():
        return None
    rows = _safe_rows(
        f"""
        SELECT STORE_ID AS store_id
        FROM {STORE_TABLE}
        WHERE IS_ACTIVE = 1 AND LOWER(STORE_NAME) = LOWER(:name)
        """,
        {'name': cleaned},
    )
    if not rows:
        return None
    try:
        return int(rows[0].get('store_id') or 0) or None
    except (TypeError, ValueError):
        return None


def _name_taken(name: str, *, exclude_id: Optional[int] = None) -> bool:
    params: Dict[str, Any] = {'name': name}
    extra = ''
    if exclude_id:
        extra = 'AND STORE_ID <> :exclude_id'
        params['exclude_id'] = int(exclude_id)
    rows = _safe_rows(
        f"""
        SELECT STORE_ID AS store_id
        FROM {STORE_TABLE}
        WHERE IS_ACTIVE = 1 AND LOWER(STORE_NAME) = LOWER(:name) {extra}
        """,
        params,
    )
    return bool(rows)


def create_compare_store(*, store_name: str, website_url: str = '') -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    if not compare_stores_ready():
        return False, 'Compare store master is not available in this database.', None
    name = _clean_name(store_name)
    if not name:
        return False, 'Enter a store name.', None
    if _name_taken(name):
        return False, f'“{name}” is already in the store master.', None
    website = _clean_website(website_url)
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT SEQ_MH_COMPARE_STORE_ID.NEXTVAL AS id FROM DUAL')
                store_id = int((cur.fetchone() or [0])[0])
                cur.execute(
                    f"""
                    INSERT INTO {STORE_TABLE} (
                        STORE_ID, STORE_NAME, WEBSITE_URL, IS_ACTIVE, SORT_ORDER, CREATED_AT
                    ) VALUES (
                        :store_id, :store_name, :website_url, 1, :sort_order, SYSTIMESTAMP
                    )
                    """,
                    {
                        'store_id': store_id,
                        'store_name': name,
                        'website_url': website,
                        'sort_order': store_id,
                    },
                )
            conn.commit()
        return True, f'Store “{name}” added.', get_compare_store(store_id)
    except Exception as exc:  # noqa: BLE001
        return False, str(exc), None


def update_compare_store(
    store_id: int,
    *,
    store_name: str,
    website_url: str = '',
) -> Tuple[bool, str]:
    if not compare_stores_ready():
        return False, 'Compare store master is not available in this database.'
    row = get_compare_store(store_id)
    if not row:
        return False, 'Store not found.'
    name = _clean_name(store_name)
    if not name:
        return False, 'Enter a store name.'
    if _name_taken(name, exclude_id=int(store_id)):
        return False, f'“{name}” is already in the store master.'
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    UPDATE {STORE_TABLE}
                    SET STORE_NAME = :store_name,
                        WEBSITE_URL = :website_url
                    WHERE STORE_ID = :store_id
                    """,
                    {
                        'store_id': int(store_id),
                        'store_name': name,
                        'website_url': _clean_website(website_url),
                    },
                )
            conn.commit()
        return True, f'Store “{name}” saved.'
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def toggle_compare_store(store_id: int) -> Tuple[bool, str]:
    if not compare_stores_ready():
        return False, 'Compare store master is not available in this database.'
    row = get_compare_store(store_id)
    if not row:
        return False, 'Store not found.'
    active = 0 if int(row.get('is_active') or 0) == 1 else 1
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    UPDATE {STORE_TABLE}
                    SET IS_ACTIVE = :is_active
                    WHERE STORE_ID = :store_id
                    """,
                    {'store_id': int(store_id), 'is_active': active},
                )
            conn.commit()
        label = row.get('store_name') or 'Store'
        return True, f'“{label}” {"activated" if active else "deactivated"}.'
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
