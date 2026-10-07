"""Salesman blueprint — master list / new / edit for SALESMAN."""
from __future__ import annotations
import secrets
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from nexa_http import Blueprint, flash, redirect, render_template, request, session, url_for
from db import _detect_column, _fetch_rows, _get_connection, _get_table_columns, _table_exists, get_locations_list
from save_nonce import GLOBAL_SAVE_NONCE_SESSION_KEY, commit_form_save_nonce, reject_invalid_form_save_nonce, verify_consume_save_nonce
from master_name_duplicate import find_master_name_duplicate, master_name_duplicate_message
from master_activity_log import append_master_activity
_ADDON_ROOT = Path(__file__).resolve().parents[1]
bp = Blueprint('salesman', __name__, template_folder=str(_ADDON_ROOT / 'views' / 'templates'))

def _sess_user_for_log() -> str:
    return str(session.get('user') or '').strip()
SALESMAN_TABLE_CANDIDATES = ('SALESMAN', 'salesman', 'SALESMEN', 'salesmen')
_SALESMAN_CREATE_ONCE_KEY = 'salesman_master_create_once_v1'

def _issue_salesman_create_once() -> str:
    t = secrets.token_urlsafe(24)
    session[_SALESMAN_CREATE_ONCE_KEY] = t
    session.modified = True
    return t

def _verify_consume_salesman_create_once(submitted: Optional[str]) -> bool:
    sub = (submitted or '').strip()
    stored = session.get(_SALESMAN_CREATE_ONCE_KEY)
    if not stored or not sub or sub != stored:
        return False
    session.pop(_SALESMAN_CREATE_ONCE_KEY, None)
    session.modified = True
    return True
_SALESMAN_EDIT_ONCE_KEY = 'salesman_master_edit_save_once_v1'

def _issue_salesman_edit_once(location_code: int, salesman_code: int) -> str:
    t = secrets.token_urlsafe(24)
    session[_SALESMAN_EDIT_ONCE_KEY] = {'lc': int(location_code), 'sc': int(salesman_code), 'tok': t}
    session.modified = True
    return t

def _verify_consume_salesman_edit_once(location_code: int, salesman_code: int, submitted: Optional[str]) -> bool:
    sub = (submitted or '').strip()
    data = session.get(_SALESMAN_EDIT_ONCE_KEY)
    if not isinstance(data, dict):
        return False
    try:
        if int(data.get('lc') or 0) != int(location_code) or int(data.get('sc') or 0) != int(salesman_code):
            return False
    except (TypeError, ValueError):
        return False
    tok = data.get('tok') or ''
    if not tok or sub != tok:
        return False
    session.pop(_SALESMAN_EDIT_ONCE_KEY, None)
    session.modified = True
    return True
_SALESMAN_DELETE_ONCE_KEY = 'salesman_master_delete_once_v1'

def _issue_salesman_delete_once(location_code: int, salesman_code: int) -> str:
    t = secrets.token_urlsafe(24)
    session[_SALESMAN_DELETE_ONCE_KEY] = {'lc': int(location_code), 'sc': int(salesman_code), 'tok': t}
    session.modified = True
    return t

def _verify_consume_salesman_delete_once(location_code: int, salesman_code: int, submitted: Optional[str]) -> bool:
    sub = (submitted or '').strip()
    data = session.get(_SALESMAN_DELETE_ONCE_KEY)
    if not isinstance(data, dict):
        return False
    try:
        if int(data.get('lc') or 0) != int(location_code) or int(data.get('sc') or 0) != int(salesman_code):
            return False
    except (TypeError, ValueError):
        return False
    tok = data.get('tok') or ''
    if not tok or sub != tok:
        return False
    session.pop(_SALESMAN_DELETE_ONCE_KEY, None)
    session.modified = True
    return True

def _salesman_table() -> Optional[str]:
    for t in SALESMAN_TABLE_CANDIDATES:
        if _table_exists(t):
            return t
    return None

def _resolve_location_code() -> int:
    loc = session.get('location_code')
    try:
        if loc is not None and str(loc).isdigit():
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
    return 1

def _location_name(location_code: int) -> str:
    for row in get_locations_list() or []:
        if int(row.get('code') or 0) == int(location_code):
            return str(row.get('name') or '').strip()
    return ''

def _parse_int(form: Dict[str, Any], key: str, default: Optional[int]=None) -> Optional[int]:
    raw = (form.get(key) or '').strip()
    if raw == '':
        return default
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return default

def _parse_float(form: Dict[str, Any], key: str, default: Optional[float]=None) -> Optional[float]:
    raw = (form.get(key) or '').strip()
    if raw == '':
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default

def _str_clip(form: Dict[str, Any], key: str, max_len: Optional[int]) -> str:
    s = (form.get(key) or '').strip()
    if max_len is not None and len(s) > max_len:
        return s[:max_len]
    return s

def _salesman_rows(location_code: Optional[int], search: Optional[str]) -> List[Dict[str, Any]]:
    tbl = _salesman_table()
    if not tbl:
        return []
    loc_col = _detect_column(tbl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    code_col = _detect_column(tbl, ['SALESMANCODE', 'salesmancode'])
    name_col = _detect_column(tbl, ['SALESMANNAME', 'salesmanname'])
    tel_col = _detect_column(tbl, ['TELEPHONE', 'telephone'])
    type_col = _detect_column(tbl, ['TYPE', 'type'])
    flag_col = _detect_column(tbl, ['FLAG', 'flag'])
    rt_col = _detect_column(tbl, ['ROUTECODE', 'routecode'])
    emp_col = _detect_column(tbl, ['EMPLOYEECODE', 'employeecode'])
    if not code_col:
        return []
    parts: List[str] = []
    parts.append(f's.{loc_col} AS locationcode' if loc_col else 'NULL AS locationcode')
    parts.append(f's.{code_col} AS salesmancode')
    parts.append(f's.{name_col} AS salesmanname' if name_col else 'NULL AS salesmanname')
    parts.append(f's.{tel_col} AS telephone' if tel_col else 'NULL AS telephone')
    parts.append(f's.{type_col} AS type' if type_col else 'NULL AS type')
    parts.append(f's.{flag_col} AS flag' if flag_col else 'NULL AS flag')
    parts.append(f's.{rt_col} AS routecode' if rt_col else 'NULL AS routecode')
    parts.append(f's.{emp_col} AS employeecode' if emp_col else 'NULL AS employeecode')
    where_parts: List[str] = []
    params: Dict[str, Any] = {}
    if location_code is not None and loc_col:
        where_parts.append(f's.{loc_col} = :location_code')
        params['location_code'] = location_code
    if search and name_col and code_col:
        where_parts.append(f'(UPPER(s.{name_col}) LIKE UPPER(:q) OR TO_CHAR(s.{code_col}) LIKE :q2)')
        params['q'] = f'%{search}%'
        params['q2'] = f'%{search}%'
    where_sql = ' WHERE ' + ' AND '.join(where_parts) if where_parts else ''
    order_by = f's.{name_col}' if name_col else f's.{code_col}'
    q = f"SELECT {', '.join(parts)} FROM {tbl} s{where_sql} ORDER BY {order_by}"
    try:
        _, rows = _fetch_rows(q, params)
        return rows or []
    except Exception as ex:
        print(f'[salesman_list] {ex}')
        return []

def _get_salesman_row(tbl: str, location_code: int, salesman_code: int) -> Optional[Dict[str, Any]]:
    loc_col = _detect_column(tbl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    code_col = _detect_column(tbl, ['SALESMANCODE', 'salesmancode'])
    if not loc_col or not code_col:
        return None
    cols = _get_table_columns(tbl)
    selects = ', '.join(cols)
    q = f'SELECT {selects} FROM {tbl} WHERE {loc_col} = :lc AND {code_col} = :sc'
    try:
        _, rows = _fetch_rows(q, {'lc': location_code, 'sc': salesman_code})
        if not rows:
            return None
        return dict(rows[0])
    except Exception as ex:
        print(f'[get_salesman_row] {ex}')
        return None

def _normalize_row_keys(row: Dict[str, Any]) -> Dict[str, Any]:
    return {str(k).lower(): v for k, v in (row or {}).items()}

def _get_next_salesman_code(location_code: int) -> int:
    tbl = _salesman_table()
    if not tbl:
        return 1
    loc_col = _detect_column(tbl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    code_col = _detect_column(tbl, ['SALESMANCODE', 'salesmancode'])
    if not loc_col or not code_col:
        return 1
    q = f'SELECT NVL(MAX({code_col}), 0) + 1 AS nxt FROM {tbl} WHERE {loc_col} = :lc'
    try:
        _, rows = _fetch_rows(q, {'lc': location_code})
        if rows:
            return int(rows[0].get('nxt') or 1)
    except Exception as ex:
        print(f'[next_salesman_code] {ex}')
    return 1

def _phys(tbl: str, name: str) -> Optional[str]:
    have = {c.upper() for c in _get_table_columns(tbl)}
    u = name.upper()
    return u if u in have else None

def _save_salesman_from_form(*, location_code: int, salesman_code: int, is_new: bool) -> Tuple[bool, str]:
    tbl = _salesman_table()
    if not tbl:
        return (False, 'SALESMAN table not found.')
    loc_col = _detect_column(tbl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    code_col = _detect_column(tbl, ['SALESMANCODE', 'salesmancode'])
    if not loc_col or not code_col:
        return (False, 'LOCATIONCODE or SALESMANCODE column missing.')
    form = dict(request.form)
    name_u = _phys(tbl, 'SALESMANNAME')
    tel_u = _phys(tbl, 'TELEPHONE')
    type_u = _phys(tbl, 'TYPE')
    h1_u = _phys(tbl, 'HELPERCODE1')
    h2_u = _phys(tbl, 'HELPERCODE2')
    oa_u = _phys(tbl, 'OUTSTANDINGAMOUNT')
    op_u = _phys(tbl, 'OPENING')
    rt_u = _phys(tbl, 'ROUTECODE')
    emp_u = _phys(tbl, 'EMPLOYEECODE')
    mp_u = _phys(tbl, 'MOREPAID')
    flag_u = _phys(tbl, 'FLAG')
    un_u = _phys(tbl, 'UNADJUSTED')
    pwd_u = _phys(tbl, 'PASSWORD')
    ver_u = _phys(tbl, 'VERSION')
    store_u = _phys(tbl, 'STORE')
    values: Dict[str, Any] = {}
    if name_u:
        values[name_u] = _str_clip(form, 'salesmanname', 200)
    if tel_u:
        values[tel_u] = _str_clip(form, 'telephone', 30)
    if type_u:
        tv = _str_clip(form, 'type', 1)
        values[type_u] = (tv[:1] if tv else ' ')[:1]
    if h1_u:
        values[h1_u] = _parse_int(form, 'helpercode1')
    if h2_u:
        values[h2_u] = _parse_int(form, 'helpercode2')
    if oa_u:
        values[oa_u] = _parse_float(form, 'outstandingamount', 0.0)
    if op_u:
        values[op_u] = _parse_float(form, 'opening', 0.0)
    if rt_u:
        values[rt_u] = _parse_int(form, 'routecode')
    if emp_u:
        values[emp_u] = _parse_int(form, 'employeecode')
    if mp_u:
        values[mp_u] = _parse_float(form, 'morepaid', 0.0)
    if flag_u:
        fg = (_str_clip(form, 'flag', 1) or 'N').upper()[:1]
        values[flag_u] = fg if fg in ('Y', 'N') else 'N'
    if un_u:
        values[un_u] = _parse_float(form, 'unadjusted', 0.0)
    if store_u:
        values[store_u] = _str_clip(form, 'store', 60)
    if ver_u and (not is_new):
        vr = _parse_int(form, 'version')
        if vr is not None:
            values[ver_u] = vr
    pwd_raw = _str_clip(form, 'password', 80)
    if pwd_u and pwd_raw:
        values[pwd_u] = pwd_raw
    if name_u and (not str(values.get(name_u) or '').strip()):
        return (False, 'Salesman name is required.')
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
                        code_col=code_col,
                        exclude_code=None if is_new else salesman_code,
                    )
                    if dup_code is not None:
                        return (
                            False,
                            master_name_duplicate_message(
                                'salesman',
                                values.get(name_u),
                                location_code=location_code,
                                existing_code=dup_code,
                            ),
                        )
                if is_new:
                    if flag_u:
                        values.setdefault(flag_u, 'N')
                    if un_u:
                        values.setdefault(un_u, 0.0)
                    if ver_u:
                        values.setdefault(ver_u, 1)
                    if type_u:
                        values.setdefault(type_u, ' ')
                    insert_order = [loc_col, code_col]
                    if name_u:
                        insert_order.append(name_u)
                    for c in (tel_u, type_u, h1_u, h2_u, oa_u, op_u, rt_u, emp_u, mp_u, flag_u, un_u, pwd_u, ver_u, store_u):
                        if c and c not in insert_order and (c in values):
                            insert_order.append(c)
                    params = {'lc': location_code, 'sc': salesman_code}
                    val_sql = [':lc', ':sc']
                    for c in insert_order[2:]:
                        pn = 'p_' + c.lower()
                        val_sql.append(f':{pn}')
                        params[pn] = values.get(c)
                    sql_ins = f"INSERT INTO {tbl} ({', '.join(insert_order)}) VALUES ({', '.join(val_sql)})"
                    cur.execute(sql_ins, params)
                else:
                    set_parts: List[str] = []
                    params_u: Dict[str, Any] = {'lc': location_code, 'sc': salesman_code}
                    for col, val in values.items():
                        if col in (loc_col, code_col):
                            continue
                        tag = 'u_' + col.lower()
                        set_parts.append(f'{col} = :{tag}')
                        params_u[tag] = val
                    if not set_parts:
                        pass
                    else:
                        sql = f"UPDATE {tbl} SET {', '.join(set_parts)} WHERE {loc_col} = :lc AND {code_col} = :sc"
                        cur.execute(sql, params_u)
                conn.commit()
        return (True, '')
    except Exception as ex:
        err = str(ex)
        print(f'[salesman save] {err}')
        return (False, err[:900])

@bp.route('/master/salesman')
def salesman_list():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    location_code = _resolve_location_code()
    search = (request.args.get('search') or '').strip()
    rows = _salesman_rows(location_code, search or None)
    loc_name = _location_name(location_code)
    return render_template('salesman/salesman_list.html', salesmen=rows, search_term=search, location_code=location_code, location_name=loc_name)

@bp.route('/master/salesman/new', methods=['GET', 'POST'])
def salesman_create():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _salesman_table():
        flash('SALESMAN table not found. Create the table in the database first.', 'error')
        return redirect(url_for('salesman.salesman_list'))
    session_loc = _resolve_location_code()
    pref = (request.args.get('pref_loc') or '').strip()
    if pref.isdigit():
        session_loc = int(pref)
    locations = get_locations_list()
    if request.method == 'POST':
        sub = (request.form.get('save_nonce') or '').strip()
        if not reject_invalid_form_save_nonce(sub):
            flash('Duplicate or invalid submit. Reload the form and try again.', 'error')
            return redirect(url_for('salesman.salesman_create'))
        once = (request.form.get('salesman_create_once') or '').strip()
        if not _verify_consume_salesman_create_once(once):
            flash('That save was skipped (duplicate submit or session lock). Open New Salesman again and submit only once.', 'warning')
            return redirect(url_for('salesman.salesman_create'))
        loc = _parse_int(request.form, 'locationcode', session_loc) or session_loc
        next_code = _get_next_salesman_code(int(loc))
        ok, err = _save_salesman_from_form(location_code=int(loc), salesman_code=int(next_code), is_new=True)
        if ok:
            if not commit_form_save_nonce(sub):
                flash('Duplicate or invalid submit. Reload the form and try again.', 'error')
                return redirect(url_for('salesman.salesman_create'))
            flash('Salesman created.', 'success')
            append_master_activity(username=_sess_user_for_log(), action='CREATE', entity='salesman', summary=f'location={int(loc)}, salesman_code={int(next_code)}', detail={'locationcode': int(loc), 'salesmancode': int(next_code)})
            return redirect(url_for('salesman.salesman_list'))
        flash(err or 'Save failed.', 'error')
    next_code = _get_next_salesman_code(session_loc)
    loc_name = _location_name(session_loc)
    salesman_create_once = _issue_salesman_create_once()
    return render_template('salesman/salesman_form.html', salesman_norm={}, location_code=session_loc, location_name=loc_name, next_salesman_code=next_code, locations=locations, is_edit=False, salesman_create_once=salesman_create_once)

@bp.route('/master/salesman/<int:location_code>/<int:salesman_code>/edit', methods=['GET', 'POST'])
def salesman_edit(location_code: int, salesman_code: int):
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    tbl = _salesman_table()
    if not tbl:
        flash('SALESMAN table not found.', 'error')
        return redirect(url_for('salesman.salesman_list'))
    row = _get_salesman_row(tbl, location_code, salesman_code)
    if not row:
        flash('Salesman not found.', 'error')
        return redirect(url_for('salesman.salesman_list'))
    sm = _normalize_row_keys(row)
    locations = get_locations_list()
    loc_name = _location_name(location_code)
    if request.method == 'POST':
        sub = (request.form.get('save_nonce') or '').strip()
        if not reject_invalid_form_save_nonce(sub):
            flash('Duplicate or invalid submit. Reload the form and try again.', 'error')
            return redirect(url_for('salesman.salesman_edit', location_code=location_code, salesman_code=salesman_code))
        once_edit = (request.form.get('salesman_edit_once') or '').strip()
        if not _verify_consume_salesman_edit_once(location_code, salesman_code, once_edit):
            flash('That save was skipped (duplicate submit or session lock). Open Edit again and submit only once.', 'warning')
            return redirect(url_for('salesman.salesman_edit', location_code=location_code, salesman_code=salesman_code))
        ok, err = _save_salesman_from_form(location_code=location_code, salesman_code=salesman_code, is_new=False)
        if ok:
            if not commit_form_save_nonce(sub):
                flash('Duplicate or invalid submit. Reload the form and try again.', 'error')
                return redirect(url_for('salesman.salesman_edit', location_code=location_code, salesman_code=salesman_code))
            flash('Salesman updated.', 'success')
            append_master_activity(username=_sess_user_for_log(), action='UPDATE', entity='salesman', summary=f'location={location_code}, salesman_code={salesman_code}', detail={'locationcode': location_code, 'salesmancode': salesman_code})
            return redirect(url_for('salesman.salesman_list'))
        flash(err or 'Save failed.', 'error')
    salesman_edit_once = _issue_salesman_edit_once(location_code, salesman_code)
    salesman_delete_once = _issue_salesman_delete_once(location_code, salesman_code)
    return render_template('salesman/salesman_form.html', salesman_norm=sm, location_code=location_code, location_name=loc_name, next_salesman_code=salesman_code, locations=locations, is_edit=True, salesman_edit_once=salesman_edit_once, salesman_delete_once=salesman_delete_once)

@bp.route('/master/salesman/<int:location_code>/<int:salesman_code>/delete', methods=['POST'])
def salesman_delete(location_code: int, salesman_code: int):
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    sub = (request.form.get('save_nonce') or '').strip()
    if not verify_consume_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY, sub):
        flash('Duplicate or invalid submit.', 'error')
        return redirect(url_for('salesman.salesman_list'))
    once_del = (request.form.get('salesman_delete_once') or '').strip()
    if not _verify_consume_salesman_delete_once(location_code, salesman_code, once_del):
        flash('That delete was skipped (duplicate submit or session lock). Open Edit again to delete.', 'warning')
        return redirect(url_for('salesman.salesman_edit', location_code=location_code, salesman_code=salesman_code))
    tbl = _salesman_table()
    if not tbl:
        flash('SALESMAN table not found.', 'error')
        return redirect(url_for('salesman.salesman_list'))
    loc_col = _detect_column(tbl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    code_col = _detect_column(tbl, ['SALESMANCODE', 'salesmancode'])
    if not loc_col or not code_col:
        flash('Required columns not found.', 'error')
        return redirect(url_for('salesman.salesman_list'))
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f'DELETE FROM {tbl} WHERE {loc_col} = :loc AND {code_col} = :sc', {'loc': location_code, 'sc': salesman_code})
            conn.commit()
        flash('Salesman deleted.', 'success')
        append_master_activity(username=_sess_user_for_log(), action='DELETE', entity='salesman', summary=f'location={location_code}, salesman_code={salesman_code}', detail={'locationcode': location_code, 'salesmancode': salesman_code})
    except Exception as ex:
        flash(f'Delete failed: {str(ex)[:500]}', 'error')
    return redirect(url_for('salesman.salesman_list'))
