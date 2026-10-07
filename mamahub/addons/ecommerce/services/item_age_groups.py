"""Assign ITEMMASTER items to MH_AGE_GROUP for Shop by age on the app."""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from db import _get_connection, _safe_rows, _table_exists
from storefront_backend.services.schema_bootstrap import (
    ensure_age_group_schema,
    ensure_item_age_group_schema,
)


def list_age_groups() -> List[Dict[str, Any]]:
    ensure_age_group_schema()
    if not _table_exists('MH_AGE_GROUP'):
        return []
    return _safe_rows(
        """
        SELECT
            AGE_GROUP_ID AS age_group_id,
            AGE_GROUP_NAME AS age_group_name,
            SLUG AS slug
        FROM MH_AGE_GROUP
        WHERE IS_ACTIVE = 1
        ORDER BY SORT_ORDER, AGE_GROUP_NAME
        """,
        {},
    )


def get_item_age_group_ids(item_code: int) -> List[int]:
    ensure_item_age_group_schema()
    if not _table_exists('MH_ITEM_AGE_GROUP'):
        return []
    rows = _safe_rows(
        """
        SELECT AGE_GROUP_ID AS age_group_id
        FROM MH_ITEM_AGE_GROUP
        WHERE ITEM_CODE = :item_code
        """,
        {'item_code': int(item_code)},
    )
    ids: List[int] = []
    for row in rows:
        try:
            ids.append(int(row.get('age_group_id')))
        except (TypeError, ValueError):
            continue
    return ids


def save_item_age_groups(item_code: int, age_group_ids: List[Any]) -> Tuple[bool, str]:
    ensure_item_age_group_schema()
    if not _table_exists('MH_ITEM_AGE_GROUP'):
        return False, 'Age group table is not available.'

    ic = int(item_code)
    raw_values = [str(raw or '').strip().lower() for raw in (age_group_ids or [])]
    assign_all = any(raw in ('all', 'all-ages', '*') for raw in raw_values)

    wanted: List[int] = []
    seen = set()
    if assign_all:
        for row in list_age_groups():
            try:
                ag_id = int(row.get('age_group_id'))
            except (TypeError, ValueError):
                continue
            if ag_id > 0 and ag_id not in seen:
                seen.add(ag_id)
                wanted.append(ag_id)
    else:
        for raw in age_group_ids or []:
            try:
                ag_id = int(raw)
            except (TypeError, ValueError):
                continue
            if ag_id <= 0 or ag_id in seen:
                continue
            seen.add(ag_id)
            wanted.append(ag_id)

    if wanted:
        placeholders = ', '.join(f':ag{i}' for i in range(len(wanted)))
        params = {f'ag{i}': ag_id for i, ag_id in enumerate(wanted)}
        valid_rows = _safe_rows(
            f"""
            SELECT AGE_GROUP_ID AS age_group_id
            FROM MH_AGE_GROUP
            WHERE IS_ACTIVE = 1 AND AGE_GROUP_ID IN ({placeholders})
            """,
            params,
        )
        valid = {int(row['age_group_id']) for row in valid_rows}
        wanted = [ag_id for ag_id in wanted if ag_id in valid]

    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('DELETE FROM MH_ITEM_AGE_GROUP WHERE ITEM_CODE = :ic', {'ic': ic})
                for ag_id in wanted:
                    cur.execute(
                        'INSERT INTO MH_ITEM_AGE_GROUP (ITEM_CODE, AGE_GROUP_ID) VALUES (:ic, :ag)',
                        {'ic': ic, 'ag': ag_id},
                    )
            conn.commit()
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
    return True, 'Age groups saved.'
