"""Fiscal year master (tenant DB) — table FISCAL_YEAR."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from db import _get_connection, _safe_rows, _table_exists

FISCAL_YEAR_TABLE = 'FISCAL_YEAR'
FISCAL_YEAR_SEQ = 'FISCAL_YEAR_SEQ'


def _iso_date(val: Any) -> Optional[str]:
    if val is None or val == '':
        return None
    if hasattr(val, 'strftime'):
        return val.strftime('%Y-%m-%d')
    s = str(val).strip()[:10]
    if len(s) >= 10 and s[4] == '-':
        return s
    for fmt in ('%d/%m/%Y', '%d-%b-%Y'):
        try:
            return datetime.strptime(s[:10], fmt).strftime('%Y-%m-%d')
        except ValueError:
            pass
    return s[:10] if s else None


def _norm_loc(val: Any) -> Optional[int]:
    if val is None or str(val).strip() == '':
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _yn(val: Any, default: str = 'N') -> str:
    return 'Y' if str(val or '').strip().upper() in ('Y', '1', 'TRUE', 'YES') else 'N'


def ensure_fiscal_year_table() -> bool:
    if _table_exists(FISCAL_YEAR_TABLE):
        return True
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    CREATE TABLE {FISCAL_YEAR_TABLE} (
                        FISCAL_YEAR_ID   NUMBER NOT NULL,
                        YEAR_CODE        VARCHAR2(20) NOT NULL,
                        YEAR_NAME        VARCHAR2(100),
                        DATE_FROM        DATE NOT NULL,
                        DATE_TO          DATE NOT NULL,
                        IS_CURRENT       VARCHAR2(1) DEFAULT 'N' NOT NULL,
                        IS_CLOSED        VARCHAR2(1) DEFAULT 'N' NOT NULL,
                        LOCATIONCODE     NUMBER,
                        CREATED_BY       VARCHAR2(100),
                        CREATED_DATE     DATE DEFAULT SYSDATE,
                        MODIFIED_BY      VARCHAR2(100),
                        MODIFIED_DATE    DATE,
                        CONSTRAINT PK_FISCAL_YEAR PRIMARY KEY (FISCAL_YEAR_ID),
                        CONSTRAINT UQ_FISCAL_YEAR_CODE UNIQUE (YEAR_CODE, LOCATIONCODE)
                    )
                    """
                )
                cur.execute(
                    f"CREATE SEQUENCE {FISCAL_YEAR_SEQ} START WITH 1 INCREMENT BY 1 NOCACHE"
                )
            conn.commit()
        return True
    except Exception as ex:
        print(f'[ensure_fiscal_year_table] {ex}')
        return False


def list_fiscal_years(
    location_code: Optional[int] = None,
    include_closed: bool = True,
) -> List[Dict[str, Any]]:
    ensure_fiscal_year_table()
    if not _table_exists(FISCAL_YEAR_TABLE):
        return []
    where = ['1=1']
    params: Dict[str, Any] = {}
    if location_code is not None:
        where.append('(LOCATIONCODE IS NULL OR LOCATIONCODE = :loc)')
        params['loc'] = int(location_code)
    if not include_closed:
        where.append("NVL(UPPER(TRIM(IS_CLOSED)), 'N') = 'N'")
    rows = _safe_rows(
        f"""
        SELECT FISCAL_YEAR_ID, YEAR_CODE, YEAR_NAME, DATE_FROM, DATE_TO,
               IS_CURRENT, IS_CLOSED, LOCATIONCODE,
               CREATED_BY, CREATED_DATE, MODIFIED_BY, MODIFIED_DATE
        FROM {FISCAL_YEAR_TABLE}
        WHERE {' AND '.join(where)}
        ORDER BY DATE_FROM DESC, FISCAL_YEAR_ID DESC
        """,
        params,
    ) or []
    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append({
            'fiscal_year_id': int(r.get('fiscal_year_id') or 0),
            'year_code': str(r.get('year_code') or '').strip(),
            'year_name': str(r.get('year_name') or '').strip(),
            'date_from': _iso_date(r.get('date_from')),
            'date_to': _iso_date(r.get('date_to')),
            'is_current': _yn(r.get('is_current'), 'N'),
            'is_closed': _yn(r.get('is_closed'), 'N'),
            'locationcode': r.get('locationcode'),
            'created_by': str(r.get('created_by') or ''),
            'modified_by': str(r.get('modified_by') or ''),
        })
    return out


def get_fiscal_year_row(fiscal_year_id: int) -> Optional[Dict[str, Any]]:
    ensure_fiscal_year_table()
    if not _table_exists(FISCAL_YEAR_TABLE):
        return None
    try:
        fid = int(fiscal_year_id)
    except (TypeError, ValueError):
        return None
    rows = _safe_rows(
        f"""
        SELECT FISCAL_YEAR_ID, YEAR_CODE, YEAR_NAME, DATE_FROM, DATE_TO,
               IS_CURRENT, IS_CLOSED, LOCATIONCODE,
               CREATED_BY, CREATED_DATE, MODIFIED_BY, MODIFIED_DATE
        FROM {FISCAL_YEAR_TABLE}
        WHERE FISCAL_YEAR_ID = :id
        """,
        {'id': fid},
    )
    if not rows:
        return None
    r = rows[0]
    return {
        'fiscal_year_id': int(r.get('fiscal_year_id') or 0),
        'year_code': str(r.get('year_code') or '').strip(),
        'year_name': str(r.get('year_name') or '').strip(),
        'date_from': _iso_date(r.get('date_from')),
        'date_to': _iso_date(r.get('date_to')),
        'is_current': _yn(r.get('is_current'), 'N'),
        'is_closed': _yn(r.get('is_closed'), 'N'),
        'locationcode': r.get('locationcode'),
        'created_by': str(r.get('created_by') or ''),
        'modified_by': str(r.get('modified_by') or ''),
    }


def _check_overlap(
    date_from: str,
    date_to: str,
    locationcode: Optional[int],
    exclude_id: Optional[int] = None,
) -> Optional[str]:
    params: Dict[str, Any] = {'df': date_from, 'dt': date_to}
    if locationcode is None:
        loc_clause = 'fy.LOCATIONCODE IS NULL'
    else:
        loc_clause = 'fy.LOCATIONCODE = :loc'
        params['loc'] = int(locationcode)
    ex = ''
    if exclude_id:
        params['eid'] = int(exclude_id)
        ex = ' AND fy.FISCAL_YEAR_ID <> :eid'
    rows = _safe_rows(
        f"""
        SELECT fy.YEAR_CODE AS year_code
        FROM {FISCAL_YEAR_TABLE} fy
        WHERE {loc_clause}
          AND fy.DATE_FROM <= TO_DATE(:dt, 'YYYY-MM-DD')
          AND fy.DATE_TO >= TO_DATE(:df, 'YYYY-MM-DD')
        {ex}
        AND ROWNUM <= 1
        """,
        params,
    )
    if rows:
        return f'Date range overlaps fiscal year {rows[0].get("year_code") or ""}.'
    return None


def _next_fiscal_year_id(cur: Any) -> int:
    cur.execute(f'SELECT {FISCAL_YEAR_SEQ}.NEXTVAL FROM DUAL')
    row = cur.fetchone()
    return int((row or [0])[0])


def save_fiscal_year(
    data: Dict[str, Any],
    user: str,
    *,
    fiscal_year_id: Optional[int] = None,
) -> Tuple[bool, str, Optional[int]]:
    ensure_fiscal_year_table()
    if not _table_exists(FISCAL_YEAR_TABLE):
        return (False, 'FISCAL_YEAR table is not available.', None)

    code = str(data.get('year_code') or '').strip().upper()[:20]
    if not code:
        return (False, 'Year code is required.', None)
    name = str(data.get('year_name') or '').strip()[:100] or None
    df = _iso_date(data.get('date_from'))
    dt = _iso_date(data.get('date_to'))
    if not df or not dt:
        return (False, 'Start and end dates are required.', None)
    if df > dt:
        return (False, 'Start date must be on or before end date.', None)

    loc = _norm_loc(data.get('locationcode'))
    is_current = _yn(data.get('is_current'))
    is_closed = _yn(data.get('is_closed'))
    usr = (user or 'web')[:100]
    is_new = not fiscal_year_id or int(fiscal_year_id or 0) <= 0

    overlap = _check_overlap(df, dt, loc, None if is_new else int(fiscal_year_id))
    if overlap:
        return (False, overlap, None)

    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                if is_new:
                    fid = _next_fiscal_year_id(cur)
                    cur.execute(
                        f"""
                        INSERT INTO {FISCAL_YEAR_TABLE}
                        (FISCAL_YEAR_ID, YEAR_CODE, YEAR_NAME, DATE_FROM, DATE_TO,
                         IS_CURRENT, IS_CLOSED, LOCATIONCODE, CREATED_BY, CREATED_DATE)
                        VALUES
                        (:id, :code, :name, TO_DATE(:df, 'YYYY-MM-DD'), TO_DATE(:dt, 'YYYY-MM-DD'),
                         :cur, :closed, :loc, :usr, SYSDATE)
                        """,
                        {
                            'id': fid, 'code': code, 'name': name, 'df': df, 'dt': dt,
                            'cur': is_current, 'closed': is_closed, 'loc': loc, 'usr': usr,
                        },
                    )
                else:
                    fid = int(fiscal_year_id)
                    cur.execute(
                        f"""
                        UPDATE {FISCAL_YEAR_TABLE} SET
                            YEAR_CODE = :code,
                            YEAR_NAME = :name,
                            DATE_FROM = TO_DATE(:df, 'YYYY-MM-DD'),
                            DATE_TO = TO_DATE(:dt, 'YYYY-MM-DD'),
                            IS_CURRENT = :cur,
                            IS_CLOSED = :closed,
                            LOCATIONCODE = :loc,
                            MODIFIED_BY = :usr,
                            MODIFIED_DATE = SYSDATE
                        WHERE FISCAL_YEAR_ID = :id
                        """,
                        {
                            'id': fid, 'code': code, 'name': name, 'df': df, 'dt': dt,
                            'cur': is_current, 'closed': is_closed, 'loc': loc, 'usr': usr,
                        },
                    )
                if is_current == 'Y':
                    _clear_current_except_cur(cur, loc, fid)
            conn.commit()
        return (True, '', fid if is_new else int(fiscal_year_id))
    except Exception as ex:
        msg = str(ex)
        if 'UQ_FISCAL_YEAR_CODE' in msg.upper() or 'UNIQUE' in msg.upper():
            return (False, 'Year code already exists for this branch scope.', None)
        return (False, msg, None)


def _clear_current_except_cur(cur: Any, locationcode: Optional[int], keep_id: int) -> None:
    if locationcode is None:
        cur.execute(
            f"""
            UPDATE {FISCAL_YEAR_TABLE} SET IS_CURRENT = 'N'
            WHERE FISCAL_YEAR_ID <> :id AND LOCATIONCODE IS NULL
            """,
            {'id': int(keep_id)},
        )
    else:
        cur.execute(
            f"""
            UPDATE {FISCAL_YEAR_TABLE} SET IS_CURRENT = 'N'
            WHERE FISCAL_YEAR_ID <> :id
              AND (LOCATIONCODE IS NULL OR LOCATIONCODE = :loc)
            """,
            {'id': int(keep_id), 'loc': int(locationcode)},
        )


def set_fiscal_year_current(fiscal_year_id: int, user: str) -> Tuple[bool, str]:
    row = get_fiscal_year_row(fiscal_year_id)
    if not row:
        return (False, 'Fiscal year not found.')
    if row.get('is_closed') == 'Y':
        return (False, 'Closed fiscal years cannot be set as current.')
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                _clear_current_except_cur(cur, _norm_loc(row.get('locationcode')), int(fiscal_year_id))
                cur.execute(
                    f"""
                    UPDATE {FISCAL_YEAR_TABLE}
                    SET IS_CURRENT = 'Y', MODIFIED_BY = :u, MODIFIED_DATE = SYSDATE
                    WHERE FISCAL_YEAR_ID = :id
                    """,
                    {'id': int(fiscal_year_id), 'u': (user or 'web')[:100]},
                )
            conn.commit()
        return (True, '')
    except Exception as ex:
        return (False, str(ex))


def delete_fiscal_year(fiscal_year_id: int) -> Tuple[bool, str]:
    ensure_fiscal_year_table()
    row = get_fiscal_year_row(fiscal_year_id)
    if not row:
        return (False, 'Fiscal year not found.')
    if row.get('is_current') == 'Y':
        return (False, 'Cannot delete the current fiscal year. Set another year as current first.')
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f'DELETE FROM {FISCAL_YEAR_TABLE} WHERE FISCAL_YEAR_ID = :id',
                    {'id': int(fiscal_year_id)},
                )
            conn.commit()
        return (True, '')
    except Exception as ex:
        return (False, str(ex))


def get_current_fiscal_year(location_code: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Return the active fiscal year row (company-wide or branch-specific)."""
    ensure_fiscal_year_table()
    if not _table_exists(FISCAL_YEAR_TABLE):
        return None
    params: Dict[str, Any] = {}
    loc_filter = ''
    if location_code is not None:
        loc_filter = """
            AND (LOCATIONCODE = :loc OR LOCATIONCODE IS NULL)
        """
        params['loc'] = int(location_code)
    rows = _safe_rows(
        f"""
        SELECT * FROM (
            SELECT FISCAL_YEAR_ID, YEAR_CODE, YEAR_NAME, DATE_FROM, DATE_TO,
                   IS_CURRENT, IS_CLOSED, LOCATIONCODE
            FROM {FISCAL_YEAR_TABLE}
            WHERE NVL(UPPER(TRIM(IS_CURRENT)), 'N') = 'Y'
            {loc_filter}
            ORDER BY CASE WHEN LOCATIONCODE IS NOT NULL THEN 0 ELSE 1 END, DATE_FROM DESC
        ) WHERE ROWNUM <= 1
        """,
        params,
    )
    if not rows:
        return None
    r = rows[0]
    return {
        'fiscal_year_id': int(r.get('fiscal_year_id') or 0),
        'year_code': str(r.get('year_code') or '').strip(),
        'year_name': str(r.get('year_name') or '').strip(),
        'date_from': _iso_date(r.get('date_from')),
        'date_to': _iso_date(r.get('date_to')),
        'locationcode': r.get('locationcode'),
    }
