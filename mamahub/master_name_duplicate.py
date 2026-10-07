"""Reject duplicate master names within the same branch (location)."""
from __future__ import annotations

from typing import Any, Dict, Optional


def normalize_master_name(name: Any) -> str:
    return str(name or '').strip().upper()


def find_master_name_duplicate(
    cur,
    *,
    table: str,
    name_col: str,
    name_value: Any,
    loc_col: Optional[str] = None,
    location_code: Optional[int] = None,
    code_col: Optional[str] = None,
    exclude_code: Optional[int] = None,
) -> Optional[int]:
    """Return the conflicting row's code when the same name exists in the branch."""
    norm = normalize_master_name(name_value)
    if not norm or not name_col or not table:
        return None
    params: Dict[str, Any] = {'norm_name': norm}
    where_parts = [f'UPPER(TRIM({name_col})) = :norm_name']
    if loc_col is not None and location_code is not None:
        where_parts.append(f'{loc_col} = :loc')
        params['loc'] = location_code
    if code_col and exclude_code is not None:
        where_parts.append(f'{code_col} <> :exclude_code')
        params['exclude_code'] = exclude_code
    select_expr = code_col or '1'
    sql = f'SELECT {select_expr} FROM {table} WHERE {" AND ".join(where_parts)} AND ROWNUM = 1'
    cur.execute(sql, params)
    row = cur.fetchone()
    if not row:
        return None
    if not code_col:
        return 0
    try:
        return int(row[0])
    except (TypeError, ValueError):
        return 0


def master_name_duplicate_message(
    entity: str,
    name: Any,
    *,
    location_code: Optional[int] = None,
    existing_code: Optional[int] = None,
) -> str:
    nm = normalize_master_name(name)
    parts = [f'A {entity} with the name "{nm}" already exists']
    if location_code is not None:
        parts.append(f'for this branch (location {location_code})')
    if existing_code is not None and int(existing_code) > 0:
        parts.append(f'(code {int(existing_code)})')
    return ' '.join(parts) + '.'
