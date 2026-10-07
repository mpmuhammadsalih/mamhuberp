"""Employee blueprint — EMPLOYEE (or legacy EMPLOYEE1) list, view, create, edit, export."""
from __future__ import annotations
import secrets
import traceback
import time
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import csv
from nexa_http import Blueprint, Response, flash, jsonify, redirect, render_template, request, session, url_for
from db import _detect_column, _fetch_rows, _get_connection, _get_table_columns, _table_exists, get_locations_list
from save_nonce import GLOBAL_SAVE_NONCE_SESSION_KEY, verify_consume_save_nonce
from master_name_duplicate import find_master_name_duplicate, master_name_duplicate_message
from master_activity_log import append_master_activity
_ADDON_ROOT = Path(__file__).resolve().parents[1]
bp = Blueprint('employee', __name__, template_folder=str(_ADDON_ROOT / 'views' / 'templates'))

def _employee_timing_log(label: str, start: float, **fields: Any) -> None:
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    extras = ' '.join(f'{k}={v}' for k, v in fields.items())
    print(f'[TIMING employee] {label} elapsed_ms={elapsed_ms:.1f}' + (f' {extras}' if extras else ''))

def _sess_user_for_log() -> str:
    return str(session.get('user') or '').strip()
_EMPLOYEE_CREATE_ONCE_KEY = 'employee_master_create_once_v1'
_EMPLOYEE_EDIT_ONCE_KEY = 'employee_master_edit_save_once_v1'
_EMPLOYEE_TABLE_CANDIDATES = ['EMPLOYEE', 'employee', 'EMPLOYEE1', 'employee1']


def _employee_master_table() -> Optional[str]:
    return _detect_table(_EMPLOYEE_TABLE_CANDIDATES)


def _employee_table_label(tbl: Optional[str]) -> str:
    if not tbl:
        return 'Employee'
    u = str(tbl).upper()
    return 'EMPLOYEE' if u == 'EMPLOYEE' else ('EMPLOYEE1' if u == 'EMPLOYEE1' else tbl)


def _is_standard_employee_table(tbl: Optional[str]) -> bool:
    return str(tbl or '').upper() == 'EMPLOYEE'


def _row_norm_from_request_form() -> Dict[str, Any]:
    """Repopulate form after validation errors on create."""
    f = request.form
    return {
        'employeecode': _parse_int_form(f, 'employeecode', None),
        'employeename': _str_clip(f, 'employeename', 200),
        'department': _str_clip(f, 'department', 60),
        'designation': _str_clip(f, 'department', 60),
        'dateofjoining': _parse_optional_date(f, 'dateofjoining'),
        'dateoftransfer': _parse_optional_date(f, 'dateoftransfer'),
        'status': _str_clip(f, 'status', 1),
        'shiftcode': _parse_int_form(f, 'shiftcode', None),
        'time1': _str_clip(f, 'time1', 20),
        'time2': _str_clip(f, 'time2', 20),
        'time3': _str_clip(f, 'time3', 20),
        'time4': _str_clip(f, 'time4', 20),
        'pending': _str_clip(f, 'pending', 1) or 'N',
        'sex': _str_clip(f, 'sex', 1),
        'address': _str_clip(f, 'address', 500),
        'telephone': _str_clip(f, 'telephone', 30),
        'mobile': _str_clip(f, 'mobile', 30),
        'nationality': _str_clip(f, 'nationality', 60),
        'resignationflag': _str_clip(f, 'resignationflag', 1) or 'N',
        'remarks': _str_clip(f, 'remarks', 500),
    }


def _department_column(tbl: str) -> Optional[str]:
    return _phys(tbl, 'DEPARTMENT') or _phys(tbl, 'DESIGNATION')


def _employee_id_column(tbl: str) -> Optional[str]:
    return _phys(tbl, 'EMPLOYEEID') or _phys(tbl, 'EMPLOYEE_ID') or _phys(tbl, 'employeeid')


def _employeecode_exists(tbl: str, location_code: int, employeecode: int) -> bool:
    loc_col = _detect_column(tbl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    ec_col = _detect_column(tbl, ['EMPLOYEECODE', 'EMPLOYEE_CODE', 'employeecode'])
    if not ec_col:
        return False
    where = [f'{ec_col} = :ec']
    params: Dict[str, Any] = {'ec': employeecode}
    if loc_col:
        where.append(f'{loc_col} = :lc')
        params['lc'] = location_code
    try:
        _, rows = _fetch_rows(f"SELECT 1 AS x FROM {tbl} WHERE {' AND '.join(where)} AND ROWNUM = 1", params)
        return bool(rows)
    except Exception as e:
        print(f'[_employeecode_exists] {e}')
        return False

def _issue_edit_once(employeecode: int) -> str:
    t = secrets.token_urlsafe(24)
    session[_EMPLOYEE_EDIT_ONCE_KEY] = {'ec': int(employeecode), 'tok': t}
    session.modified = True
    return t

def _verify_consume_edit_once(employeecode: int, submitted: Optional[str]) -> bool:
    sub = (submitted or '').strip()
    data = session.get(_EMPLOYEE_EDIT_ONCE_KEY)
    if not isinstance(data, dict):
        return False
    try:
        if int(data.get('ec') or 0) != int(employeecode):
            return False
    except (TypeError, ValueError):
        return False
    got = data.get('tok') or ''
    if not got or sub != got:
        return False
    session.pop(_EMPLOYEE_EDIT_ONCE_KEY, None)
    session.modified = True
    return True

def _issue_create_once() -> str:
    t = secrets.token_urlsafe(24)
    session[_EMPLOYEE_CREATE_ONCE_KEY] = t
    session.modified = True
    return t

def _verify_consume_create_once(submitted: Optional[str]) -> bool:
    sub = (submitted or '').strip()
    stored = session.get(_EMPLOYEE_CREATE_ONCE_KEY)
    if not stored or not sub or sub != stored:
        return False
    session.pop(_EMPLOYEE_CREATE_ONCE_KEY, None)
    session.modified = True
    return True

def _detect_table(candidates: List[str]) -> Optional[str]:
    for table_name in candidates:
        try:
            if _table_exists(table_name):
                return table_name
        except Exception:
            continue
    return None

def _resolve_session_location_code() -> Optional[int]:
    loc = session.get('location_code')
    try:
        if loc is not None and str(loc).strip().isdigit():
            return int(loc)
    except (TypeError, ValueError):
        pass
    try:
        from db import get_location_info_by_dbkey
        info = get_location_info_by_dbkey(None)
        if info and info.get('locationcode') is not None:
            return int(info['locationcode'])
    except Exception:
        pass
    return None

def _location_name(location_code: int) -> str:
    for row in get_locations_list() or []:
        if int(row.get('code') or 0) == int(location_code):
            return str(row.get('name') or '').strip()
    return ''

def _phys(tbl: str, name: str) -> Optional[str]:
    have = {c.upper() for c in _get_table_columns(tbl)}
    u = name.upper()
    return u if u in have else None

def _normalize_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {str(k).lower(): v for k, v in (row or {}).items()}

def _parse_int_form(form: Dict[str, Any], key: str, default: Optional[int]=None) -> Optional[int]:
    raw = (form.get(key) or '').strip()
    if raw == '':
        return default
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return default

def _str_clip(form: Dict[str, Any], key: str, max_len: Optional[int]) -> str:
    s = (form.get(key) or '').strip()
    if max_len is not None and len(s) > max_len:
        return s[:max_len]
    return s

def _parse_optional_date(form: Dict[str, Any], key: str) -> Optional[datetime]:
    raw = (form.get(key) or '').strip()
    if not raw:
        return None
    for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%Y/%m/%d'):
        try:
            return datetime.strptime(raw[:10], fmt)
        except ValueError:
            continue
    return None

def _date_for_input(val: Any) -> str:
    if val is None:
        return ''
    if isinstance(val, datetime):
        return val.strftime('%Y-%m-%d')
    s = str(val).strip()
    if len(s) >= 10 and s[4] == '-' and (s[7] == '-'):
        return s[:10]
    return s[:10] if len(s) >= 10 else ''

def _get_employee_list(location_code: Optional[int]=None, pending_filter: Optional[str]=None, *, page: Optional[int]=None, items_per_page: Optional[int]=None) -> List[Dict[str, Any]]:
    employee_table = _employee_master_table()
    if not employee_table:
        return []
    locationcode_col = _detect_column(employee_table, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    employeecode_col = _detect_column(employee_table, ['EMPLOYEECODE', 'EMPLOYEE_CODE', 'employeecode'])
    employeename_col = _detect_column(employee_table, ['EMPLOYEENAME', 'EMPLOYEE_NAME', 'employeename'])
    department_col = _department_column(employee_table)
    pending_col = _detect_column(employee_table, ['PENDING', 'pending'])
    if not employeecode_col or not employeename_col:
        return []
    where_clauses: List[str] = []
    params: Dict[str, Any] = {}
    if location_code is not None and locationcode_col:
        where_clauses.append(f'{locationcode_col} = :location_code')
        params['location_code'] = location_code
    if pending_filter and pending_col:
        if pending_filter.upper() in {'Y', 'N'}:
            where_clauses.append(f'{pending_col} = :pending_filter')
            params['pending_filter'] = pending_filter.upper()
    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ''
    select_cols = [f'{employeecode_col} AS employeecode', f'{employeename_col} AS employeename']
    if department_col:
        select_cols.append(f'{department_col} AS designation')
    else:
        select_cols.append('NULL AS designation')
    if pending_col:
        select_cols.append(f'{pending_col} AS pending')
    else:
        select_cols.append("'N' AS pending")
    eid_col = _employee_id_column(employee_table)
    if eid_col:
        select_cols.append(f'{eid_col} AS employeeid')
    if locationcode_col:
        select_cols.append(f'{locationcode_col} AS locationcode')
    inner_query = f"\n        SELECT {', '.join(select_cols)}\n        FROM {employee_table}\n        {where_sql}\n        ORDER BY {employeecode_col}\n    "
    if page is not None and items_per_page is not None:
        page_val = max(1, int(page or 1))
        per_page = max(1, min(int(items_per_page or 50), 500))
        offset = (page_val - 1) * per_page
        params['max_row'] = offset + per_page
        params['min_row'] = offset
        query = f"""
            SELECT * FROM (
                SELECT a.*, ROWNUM rnum FROM (
                    {inner_query}
                ) a WHERE ROWNUM <= :max_row
            ) WHERE rnum > :min_row
        """
    else:
        query = inner_query
    try:
        _, rows = _fetch_rows(query, params)
        return rows or []
    except Exception as e:
        print(f'[ERROR _get_employee_list] {e}')
        print(traceback.format_exc())
        return []

def _get_employee_kpis(location_code: Optional[int]=None, pending_filter: Optional[str]=None) -> Dict[str, int]:
    """List-page KPIs: total employees and rows with designation filled."""
    _ = pending_filter
    zero = {'total': 0, 'designation': 0}
    employee_table = _employee_master_table()
    if not employee_table:
        return zero
    locationcode_col = _detect_column(employee_table, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    designation_col = _department_column(employee_table)
    where_clauses: List[str] = []
    params: Dict[str, Any] = {}
    if location_code is not None and locationcode_col:
        where_clauses.append(f'{locationcode_col} = :location_code')
        params['location_code'] = location_code
    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ''
    des_sql = designation_col or 'NULL'
    query = f"""
        SELECT
            COUNT(*) AS total_cnt,
            SUM(CASE WHEN TRIM(TO_CHAR({des_sql})) IS NOT NULL THEN 1 ELSE 0 END) AS designation_cnt
        FROM {employee_table}
        {where_sql}
    """
    try:
        _, rows = _fetch_rows(query, params)
        row = rows[0] if rows else {}
        return {
            'total': int(row.get('total_cnt') or 0),
            'designation': int(row.get('designation_cnt') or 0),
        }
    except Exception as e:
        print(f'[ERROR _get_employee_kpis] {e}')
        return zero

def _json_employee_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'employeecode': row.get('employeecode'),
        'employeeid': row.get('employeeid'),
        'employeename': row.get('employeename') or '',
        'designation': row.get('designation') or '',
        'locationcode': row.get('locationcode'),
    }

def _get_employee_full_row(tbl: str, location_code: Optional[int], employeecode: int) -> Optional[Dict[str, Any]]:
    loc_col = _detect_column(tbl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    ec_col = _detect_column(tbl, ['EMPLOYEECODE', 'EMPLOYEE_CODE', 'employeecode'])
    if not ec_col:
        return None
    cols = _get_table_columns(tbl)
    col_sql = ', '.join(cols)
    where_parts = [f'{ec_col} = :ec']
    params: Dict[str, Any] = {'ec': employeecode}
    if location_code is not None and loc_col:
        where_parts.append(f'{loc_col} = :lc')
        params['lc'] = location_code
    q = f"SELECT {col_sql} FROM {tbl} WHERE {' AND '.join(where_parts)}"
    try:
        _, rows = _fetch_rows(q, params)
        if rows:
            return dict(rows[0])
        if location_code is not None and loc_col:
            return _get_employee_full_row(tbl, None, employeecode)
        return None
    except Exception as e:
        print(f'[ERROR _get_employee_full_row] {e}')
        return None

def _get_employee_by_code(employeecode: int, location_code: Optional[int]=None) -> Optional[Dict[str, Any]]:
    """Summary row for list compatibility."""
    employee_table = _employee_master_table()
    if not employee_table:
        return None
    row = _get_employee_full_row(employee_table, location_code, employeecode)
    if not row:
        return None
    n = _normalize_row(row)
    dept = n.get('department') or n.get('designation')
    return {'employeecode': n.get('employeecode'), 'employeename': n.get('employeename'), 'designation': dept, 'pending': n.get('pending') or 'N', 'locationcode': n.get('locationcode')}

def _next_employee_code(location_code: int) -> int:
    """Suggested next code for the form (user may enter a different value manually)."""
    tbl = _employee_master_table()
    if not tbl:
        return 1
    loc_col = _detect_column(tbl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    ec_col = _detect_column(tbl, ['EMPLOYEECODE', 'EMPLOYEE_CODE', 'employeecode'])
    if not loc_col or not ec_col:
        return 1
    q = f'SELECT NVL(MAX({ec_col}), 0) + 1 AS nxt FROM {tbl} WHERE {loc_col} = :lc'
    try:
        _, rows = _fetch_rows(q, {'lc': location_code})
        if rows:
            return int(rows[0].get('nxt') or 1)
    except Exception as e:
        print(f'[next_employee_code] {e}')
    return 1


def _next_employee_id(location_code: int) -> Optional[int]:
    """System ID (EMPLOYEEID) — auto-assigned on create when the column exists."""
    tbl = _employee_master_table()
    if not tbl:
        return None
    eid_col = _employee_id_column(tbl)
    if not eid_col:
        return None
    loc_col = _detect_column(tbl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    where_sql = ''
    params: Dict[str, Any] = {}
    if loc_col:
        where_sql = f' WHERE {loc_col} = :lc'
        params['lc'] = location_code
    q = f'SELECT NVL(MAX({eid_col}), 0) + 1 AS nxt FROM {tbl}{where_sql}'
    try:
        _, rows = _fetch_rows(q, params)
        if rows:
            return int(rows[0].get('nxt') or 1)
    except Exception as e:
        print(f'[_next_employee_id] {e}')
    return 1


def _save_employee_from_form(*, location_code: int, employeecode: int, is_new: bool, employee_id: Optional[int] = None) -> Tuple[bool, str]:
    tbl = _employee_master_table()
    if not tbl:
        return (False, 'Employee table not found (expected EMPLOYEE or EMPLOYEE1).')
    loc_col = _detect_column(tbl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    ec_col = _detect_column(tbl, ['EMPLOYEECODE', 'EMPLOYEE_CODE', 'employeecode'])
    eid_col = _employee_id_column(tbl)
    if not loc_col or not ec_col:
        return (False, 'LOCATIONCODE or EMPLOYEECODE missing.')
    form = dict(request.form)
    name_u = _phys(tbl, 'EMPLOYEENAME')
    dept_u = _department_column(tbl)
    doj_u = _phys(tbl, 'DATEOFJOINING')
    status_u = _phys(tbl, 'STATUS')
    dot_u = _phys(tbl, 'DATEOFTRANSFER')
    shift_u = _phys(tbl, 'SHIFTCODE')
    t1 = _phys(tbl, 'TIME1')
    t2 = _phys(tbl, 'TIME2')
    t3 = _phys(tbl, 'TIME3')
    t4 = _phys(tbl, 'TIME4')
    pend_u = _phys(tbl, 'PENDING')
    sex_u = _phys(tbl, 'SEX')
    addr_u = _phys(tbl, 'ADDRESS')
    tel_u = _phys(tbl, 'TELEPHONE')
    mob_u = _phys(tbl, 'MOBILE')
    resign_u = _phys(tbl, 'RESIGNATIONFLAG')
    remarks_u = _phys(tbl, 'REMARKS')
    nat_u = _phys(tbl, 'NATIONALITY')
    values: Dict[str, Any] = {}
    if name_u:
        values[name_u] = _str_clip(form, 'employeename', 200)
    if dept_u:
        values[dept_u] = _str_clip(form, 'department', 60)
    if doj_u:
        dj = _parse_optional_date(form, 'dateofjoining')
        values[doj_u] = dj
    if status_u:
        st = _str_clip(form, 'status', 1)
        values[status_u] = (st[:1] if st else ' ')[:1]
    if dot_u:
        values[dot_u] = _parse_optional_date(form, 'dateoftransfer')
    if shift_u:
        values[shift_u] = _parse_int_form(form, 'shiftcode')
    if t1:
        values[t1] = _str_clip(form, 'time1', 20)
    if t2:
        values[t2] = _str_clip(form, 'time2', 20)
    if t3:
        values[t3] = _str_clip(form, 'time3', 20)
    if t4:
        values[t4] = _str_clip(form, 'time4', 20)
    if pend_u:
        pg = (_str_clip(form, 'pending', 1) or 'N').upper()[:1]
        values[pend_u] = pg if pg in ('Y', 'N') else 'N'
    if sex_u:
        sx = (_str_clip(form, 'sex', 1) or '').upper()[:1]
        values[sex_u] = sx if sx in ('M', 'F') else ''
    if addr_u:
        values[addr_u] = _str_clip(form, 'address', 500)
    if tel_u:
        values[tel_u] = _str_clip(form, 'telephone', 30)
    if mob_u:
        values[mob_u] = _str_clip(form, 'mobile', 30)
    if nat_u:
        values[nat_u] = _str_clip(form, 'nationality', 60)
    if remarks_u:
        values[remarks_u] = _str_clip(form, 'remarks', 500)
    if resign_u:
        rf = (_str_clip(form, 'resignationflag', 1) or 'N').upper()[:1]
        values[resign_u] = rf if rf in ('Y', 'N') else 'N'
    if name_u and (not str(values.get(name_u) or '').strip()):
        return (False, 'Employee name is required.')
    if is_new and eid_col:
        eid_val = employee_id if employee_id is not None else _next_employee_id(location_code)
        if eid_val is None or int(eid_val) <= 0:
            return (False, 'Could not assign employee ID.')
        values[eid_col] = int(eid_val)
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                if name_u:
                    dup_code = find_master_name_duplicate(
                        cur,
                        table=tbl,
                        name_col=name_u,
                        name_value=values.get(name_u),
                        loc_col=loc_col,
                        location_code=location_code,
                        code_col=ec_col,
                        exclude_code=None if is_new else employeecode,
                    )
                    if dup_code is not None:
                        return (
                            False,
                            master_name_duplicate_message(
                                'employee',
                                values.get(name_u),
                                location_code=location_code,
                                existing_code=dup_code,
                            ),
                        )
                if is_new:
                    if pend_u:
                        values.setdefault(pend_u, 'N')
                    if status_u:
                        values.setdefault(status_u, ' ')
                    if resign_u:
                        values.setdefault(resign_u, 'N')
                    insert_order = [loc_col, ec_col]
                    if eid_col and eid_col in values:
                        insert_order.append(eid_col)
                    if name_u:
                        insert_order.append(name_u)
                    extra_cols = (
                        dept_u, doj_u, status_u, dot_u, shift_u, t1, t2, t3, t4, pend_u,
                        sex_u, addr_u, tel_u, mob_u, nat_u, remarks_u, resign_u,
                    )
                    for c in extra_cols:
                        if c and c not in insert_order and (c in values):
                            insert_order.append(c)
                    params_i: Dict[str, Any] = {'lc': location_code, 'ec': employeecode}
                    val_sql = [':lc', ':ec']
                    for c in insert_order[2:]:
                        pn = 'p_' + c.lower().replace('/', '_')
                        val_sql.append(f':{pn}')
                        params_i[pn] = values.get(c)
                    sql_ins = f"INSERT INTO {tbl} ({', '.join(insert_order)}) VALUES ({', '.join(val_sql)})"
                    cur.execute(sql_ins, params_i)
                else:
                    set_parts: List[str] = []
                    params_u: Dict[str, Any] = {'lc': location_code, 'ec': employeecode}
                    for col, val in values.items():
                        if col in (loc_col, ec_col, eid_col):
                            continue
                        tag = 'u_' + col.lower().replace('/', '_')
                        set_parts.append(f'{col} = :{tag}')
                        params_u[tag] = val
                    if set_parts:
                        sql = f"UPDATE {tbl} SET {', '.join(set_parts)} WHERE {loc_col} = :lc AND {ec_col} = :ec"
                        cur.execute(sql, params_u)
                conn.commit()
        return (True, '')
    except Exception as ex:
        err = str(ex)
        print(f'[employee save] {err}')
        return (False, err[:900])

@bp.route('/master/employee')
def employee_list():
    _t0 = time.perf_counter()
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    location_code = _resolve_session_location_code()
    _step = time.perf_counter()
    tbl = _employee_master_table()
    show_employee_id = bool(tbl and _employee_id_column(tbl))
    resp = render_template('employee/employee_list.html', employees=[], employee_kpis={'total': 0, 'designation': 0}, current_page=0, total_pages=1, total_count=0, items_per_page=50, employee_items_api_url=url_for('employee.employee_list_api_items'), show_employee_id=show_employee_id)
    _employee_timing_log('list_render', _step, rows=0)
    _employee_timing_log('list_total', _t0, shell=1)
    return resp

@bp.route('/master/employee/api/items')
def employee_list_api_items():
    _t0 = time.perf_counter()
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    location_code = _resolve_session_location_code()
    try:
        page = max(1, int(request.args.get('page') or 1))
    except (TypeError, ValueError):
        page = 1
    try:
        per_page = max(20, min(int(request.args.get('per_page') or 50), 500))
    except (TypeError, ValueError):
        per_page = 50
    rows = _get_employee_list(location_code, None, page=page, items_per_page=per_page)
    try:
        total_count = max(0, int(request.args.get('total_count') or 0))
    except (TypeError, ValueError):
        total_count = 0
    kpis = None
    if total_count <= 0:
        kpis = _get_employee_kpis(location_code)
        total_count = int((kpis or {}).get('total') or 0)
    total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 1
    _employee_timing_log('api_items', _t0, page=page, per_page=per_page, rows=len(rows or []), total=total_count)
    return jsonify({'success': True, 'items': [_json_employee_row(r) for r in rows or []], 'kpis': kpis, 'total_count': total_count, 'page': page, 'items_per_page': per_page, 'total_pages': total_pages})

@bp.route('/master/employee/new', methods=['GET', 'POST'])
def employee_create():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    tbl = _employee_master_table()
    if not tbl:
        flash('Employee table not found (expected EMPLOYEE or EMPLOYEE1).', 'error')
        return redirect(url_for('employee.employee_list'))
    session_loc = _resolve_session_location_code() or 1
    pref = (request.args.get('pref_loc') or '').strip()
    if pref.isdigit():
        session_loc = int(pref)
    locations = get_locations_list()
    has_employee_id = bool(_employee_id_column(tbl))
    suggested_code = _next_employee_code(session_loc)
    suggested_id = _next_employee_id(session_loc) if has_employee_id else None
    if request.method == 'POST':
        sub = (request.form.get('save_nonce') or '').strip()
        if not verify_consume_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY, sub):
            flash('Duplicate or invalid submit. Reload the form and try again.', 'error')
            return redirect(url_for('employee.employee_create'))
        loc = _parse_int_form(request.form, 'locationcode', session_loc) or session_loc
        ec = _parse_int_form(request.form, 'employeecode', None)
        if ec is None or ec <= 0:
            flash('Employee code is required (enter a positive number).', 'error')
            create_once = _issue_create_once()
            row_norm = _row_norm_from_request_form()
            return render_template('employee/employee_form.html', row_norm=row_norm, location_code=loc, location_name=_location_name(int(loc)), next_employeecode=suggested_code, suggested_employee_id=suggested_id, locations=locations, is_edit=False, employee_create_once=create_once, employee_table=tbl, has_employee_id=has_employee_id, is_standard_employee=_is_standard_employee_table(tbl))
        if _employeecode_exists(tbl, int(loc), int(ec)):
            flash(f'Employee code {ec} already exists for this branch.', 'error')
            create_once = _issue_create_once()
            row_norm = _row_norm_from_request_form()
            row_norm['employeecode'] = ec
            return render_template('employee/employee_form.html', row_norm=row_norm, location_code=loc, location_name=_location_name(int(loc)), next_employeecode=suggested_code, suggested_employee_id=suggested_id, locations=locations, is_edit=False, employee_create_once=create_once, employee_table=tbl, has_employee_id=has_employee_id, is_standard_employee=_is_standard_employee_table(tbl))
        once = (request.form.get('employee_create_once') or '').strip()
        if not _verify_consume_create_once(once):
            flash('That save was skipped (duplicate submit or session lock). Open New Employee again and submit only once.', 'warning')
            return redirect(url_for('employee.employee_create'))
        new_eid = _next_employee_id(int(loc)) if has_employee_id else None
        ok, err = _save_employee_from_form(location_code=int(loc), employeecode=int(ec), is_new=True, employee_id=new_eid)
        if ok:
            flash('Employee created.', 'success')
            detail = {'locationcode': int(loc), 'employeecode': int(ec)}
            if new_eid is not None:
                detail['employeeid'] = int(new_eid)
            append_master_activity(username=_sess_user_for_log(), action='CREATE', entity='employee', summary=f'location={int(loc)}, employeecode={int(ec)}', detail=detail)
            return redirect(url_for('employee.employee_list'))
        flash(err or 'Save failed.', 'error')
        create_once = _issue_create_once()
        row_norm = _row_norm_from_request_form()
        row_norm['employeecode'] = ec
        return render_template('employee/employee_form.html', row_norm=row_norm, location_code=loc, location_name=_location_name(int(loc)), next_employeecode=suggested_code, suggested_employee_id=suggested_id, locations=locations, is_edit=False, employee_create_once=create_once, employee_table=tbl, has_employee_id=has_employee_id, is_standard_employee=_is_standard_employee_table(tbl))
    loc_name = _location_name(session_loc)
    create_once = _issue_create_once()
    return render_template('employee/employee_form.html', row_norm={}, location_code=session_loc, location_name=loc_name, next_employeecode=suggested_code, suggested_employee_id=suggested_id, locations=locations, is_edit=False, employee_create_once=create_once, employee_table=tbl, has_employee_id=has_employee_id, is_standard_employee=_is_standard_employee_table(tbl))

@bp.route('/master/employee/<int:employeecode>/view')
def employee_view(employeecode: int):
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    session_loc = _resolve_session_location_code()
    tbl = _employee_master_table()
    if not tbl:
        flash('Employee table not found (expected EMPLOYEE or EMPLOYEE1).', 'error')
        return redirect(url_for('employee.employee_list'))
    full = _get_employee_full_row(tbl, session_loc, employeecode)
    if not full:
        flash('Employee not found.', 'error')
        return redirect(url_for('employee.employee_list'))
    employee = _normalize_row(full)
    if not employee.get('department') and employee.get('designation'):
        employee['department'] = employee.get('designation')
    summary = _get_employee_by_code(employeecode, session_loc)
    has_employee_id = bool(_employee_id_column(tbl))
    return render_template('employee/employee_view.html', employee=employee, summary=summary, employee_table=tbl, has_employee_id=has_employee_id, is_standard_employee=_is_standard_employee_table(tbl))

@bp.route('/master/employee/<int:employeecode>/edit', methods=['GET', 'POST'])
def employee_edit(employeecode: int):
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    session_loc = _resolve_session_location_code()
    tbl = _employee_master_table()
    if not tbl:
        flash('Employee table not found.', 'error')
        return redirect(url_for('employee.employee_list'))
    full = _get_employee_full_row(tbl, session_loc, employeecode)
    if not full:
        flash('Employee not found.', 'error')
        return redirect(url_for('employee.employee_list'))
    row_n = _normalize_row(full)
    if not row_n.get('department') and row_n.get('designation'):
        row_n['department'] = row_n.get('designation')
    try:
        row_loc = row_n.get('locationcode')
        location_code = int(row_loc) if row_loc is not None and str(row_loc).strip() != '' else None
    except (TypeError, ValueError):
        location_code = None
    if location_code is None:
        flash('Employee row has no location code.', 'error')
        return redirect(url_for('employee.employee_list'))
    locations = get_locations_list()
    loc_name = _location_name(int(location_code))
    if request.method == 'POST':
        sub = (request.form.get('save_nonce') or '').strip()
        if not verify_consume_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY, sub):
            flash('Duplicate or invalid submit. Reload the form and try again.', 'error')
            return redirect(url_for('employee.employee_edit', employeecode=employeecode))
        once_edit = (request.form.get('employee_edit_once') or '').strip()
        if not _verify_consume_edit_once(employeecode, once_edit):
            flash('That save was skipped (duplicate submit or session lock). Open Edit again and submit only once.', 'warning')
            return redirect(url_for('employee.employee_edit', employeecode=employeecode))
        ok, err = _save_employee_from_form(location_code=int(location_code), employeecode=int(employeecode), is_new=False)
        if ok:
            flash('Employee updated.', 'success')
            append_master_activity(username=_sess_user_for_log(), action='UPDATE', entity='employee', summary=f'location={location_code}, employeecode={employeecode}', detail={'locationcode': int(location_code), 'employeecode': int(employeecode)})
            return redirect(url_for('employee.employee_list'))
        flash(err or 'Save failed.', 'error')
    employee_edit_once = _issue_edit_once(employeecode)
    has_employee_id = bool(_employee_id_column(tbl))
    return render_template('employee/employee_form.html', row_norm=row_n, location_code=location_code, location_name=loc_name, next_employeecode=employeecode, suggested_employee_id=row_n.get('employeeid'), locations=locations, is_edit=True, employee_edit_once=employee_edit_once, employee_table=tbl, has_employee_id=has_employee_id, is_standard_employee=_is_standard_employee_table(tbl))

@bp.route('/master/employee/export', methods=['GET'])
def employee_export():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    location_code = _resolve_session_location_code()
    employees = _get_employee_list(location_code, None)
    output = StringIO()
    writer = csv.writer(output)
    tbl = _employee_master_table()
    include_id = bool(tbl and _employee_id_column(tbl))
    header = ['Sl.No', 'Employee ID', 'Employee Code', 'Employee Name', 'Designation'] if include_id else ['Sl.No', 'Employee Code', 'Employee Name', 'Designation']
    writer.writerow(header)
    for idx, employee in enumerate(employees, start=1):
        if include_id:
            writer.writerow([idx, employee.get('employeeid') or '', employee.get('employeecode') or '', employee.get('employeename') or '', employee.get('designation') or ''])
        else:
            writer.writerow([idx, employee.get('employeecode') or '', employee.get('employeename') or '', employee.get('designation') or ''])
    output.seek(0)
    filename = f"employee_list_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename={filename}'})
