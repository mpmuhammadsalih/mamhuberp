"""TBLCUSTOMERCATEGORY — list / create / edit / delete per branch."""
from __future__ import annotations
import secrets
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from nexa_http import Blueprint, flash, redirect, render_template, request, session, url_for
from db import _detect_column, _fetch_rows, _get_connection, _get_table_columns, _table_exists, get_locations_list
from save_nonce import GLOBAL_SAVE_NONCE_SESSION_KEY, commit_form_save_nonce, reject_invalid_form_save_nonce, verify_consume_save_nonce
from master_activity_log import append_master_activity
_ADDON_ROOT = Path(__file__).resolve().parents[1]
bp = Blueprint('customer_category', __name__, template_folder=str(_ADDON_ROOT / 'views' / 'templates'))

def _sess_user_for_log() -> str:
    return str(session.get('user') or '').strip()
TABLE_CANDIDATES = ('TBLCUSTOMERCATEGORY', 'tblcustomercategory')
_CREATE_ONCE_KEY = 'cust_category_master_create_once_v1'

def _issue_create_once() -> str:
    t = secrets.token_urlsafe(24)
    session[_CREATE_ONCE_KEY] = t
    session.modified = True
    return t

def _verify_consume_create_once(submitted: Optional[str]) -> bool:
    sub = (submitted or '').strip()
    stored = session.get(_CREATE_ONCE_KEY)
    if not stored or not sub or sub != stored:
        return False
    session.pop(_CREATE_ONCE_KEY, None)
    session.modified = True
    return True
_EDIT_SAVE_ONCE_KEY = 'cust_category_master_edit_save_once_v1'

def _issue_edit_save_once(location_code: int, category_code: int) -> str:
    t = secrets.token_urlsafe(24)
    session[_EDIT_SAVE_ONCE_KEY] = {'lc': int(location_code), 'cc': int(category_code), 'tok': t}
    session.modified = True
    return t

def _verify_consume_edit_save_once(location_code: int, category_code: int, submitted: Optional[str]) -> bool:
    sub = (submitted or '').strip()
    data = session.get(_EDIT_SAVE_ONCE_KEY)
    if not isinstance(data, dict):
        return False
    try:
        if int(data.get('lc') or 0) != int(location_code) or int(data.get('cc') or 0) != int(category_code):
            return False
    except (TypeError, ValueError):
        return False
    tok = data.get('tok') or ''
    if not tok or sub != tok:
        return False
    session.pop(_EDIT_SAVE_ONCE_KEY, None)
    session.modified = True
    return True
_DELETE_ONCE_KEY = 'cust_category_master_delete_once_v1'

def _issue_delete_once(location_code: int, category_code: int) -> str:
    t = secrets.token_urlsafe(24)
    session[_DELETE_ONCE_KEY] = {'lc': int(location_code), 'cc': int(category_code), 'tok': t}
    session.modified = True
    return t

def _verify_consume_delete_once(location_code: int, category_code: int, submitted: Optional[str]) -> bool:
    sub = (submitted or '').strip()
    data = session.get(_DELETE_ONCE_KEY)
    if not isinstance(data, dict):
        return False
    try:
        if int(data.get('lc') or 0) != int(location_code) or int(data.get('cc') or 0) != int(category_code):
            return False
    except (TypeError, ValueError):
        return False
    tok = data.get('tok') or ''
    if not tok or sub != tok:
        return False
    session.pop(_DELETE_ONCE_KEY, None)
    session.modified = True
    return True

def _table() -> Optional[str]:
    for t in TABLE_CANDIDATES:
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

def _phys(tbl: str, name: str) -> Optional[str]:
    have = {c.upper() for c in _get_table_columns(tbl)}
    u = name.upper()
    return u if u in have else None

def _list_rows(location_code: Optional[int], search: Optional[str]) -> List[Dict[str, Any]]:
    tbl = _table()
    if not tbl:
        return []
    loc_col = _detect_column(tbl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    cc_col = _detect_column(tbl, ['CATEGORYCODE', 'categorycode'])
    name_col = _detect_column(tbl, ['CATEGORYNAME', 'categoryname'])
    if not cc_col:
        return []
    parts = [f'c.{loc_col} AS locationcode' if loc_col else 'NULL AS locationcode', f'c.{cc_col} AS categorycode', f'c.{name_col} AS categoryname' if name_col else 'NULL AS categoryname']
    where_parts: List[str] = []
    params: Dict[str, Any] = {}
    if location_code is not None and loc_col:
        where_parts.append(f'c.{loc_col} = :location_code')
        params['location_code'] = location_code
    if search:
        clauses = [f'TO_CHAR(c.{cc_col}) LIKE :q']
        params['q'] = f'%{search}%'
        if name_col:
            clauses.append(f'UPPER(c.{name_col}) LIKE UPPER(:qn)')
            params['qn'] = f'%{search}%'
        where_parts.append('(' + ' OR '.join(clauses) + ')')
    where_sql = ' WHERE ' + ' AND '.join(where_parts) if where_parts else ''
    order_by = f'c.{name_col}' if name_col else f'c.{cc_col}'
    q = f"SELECT {', '.join(parts)} FROM {tbl} c{where_sql} ORDER BY {order_by}"
    try:
        _, rows = _fetch_rows(q, params)
        return rows or []
    except Exception as ex:
        print(f'[customer_category list] {ex}')
        return []

def _get_row(tbl: str, location_code: int, category_code: int) -> Optional[Dict[str, Any]]:
    loc_col = _detect_column(tbl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    cc_col = _detect_column(tbl, ['CATEGORYCODE', 'categorycode'])
    if not loc_col or not cc_col:
        return None
    cols = _get_table_columns(tbl)
    selects = ', '.join(cols)
    q = f'SELECT {selects} FROM {tbl} WHERE {loc_col} = :lc AND {cc_col} = :cc'
    try:
        _, rows = _fetch_rows(q, {'lc': location_code, 'cc': category_code})
        if not rows:
            return None
        return dict(rows[0])
    except Exception as ex:
        print(f'[customer_category get_row] {ex}')
        return None

def _normalize_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {str(k).lower(): v for k, v in (row or {}).items()}

def _next_category_code(location_code: int) -> int:
    tbl = _table()
    if not tbl:
        return 1
    loc_col = _detect_column(tbl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    cc_col = _detect_column(tbl, ['CATEGORYCODE', 'categorycode'])
    if not loc_col or not cc_col:
        return 1
    q = f'SELECT NVL(MAX({cc_col}), 0) + 1 AS nxt FROM {tbl} WHERE {loc_col} = :lc'
    try:
        _, rows = _fetch_rows(q, {'lc': location_code})
        if rows:
            return int(rows[0].get('nxt') or 1)
    except Exception as ex:
        print(f'[customer_category next_code] {ex}')
    return 1

def _save_from_form(*, location_code: int, category_code: int, is_new: bool) -> Tuple[bool, str]:
    tbl = _table()
    if not tbl:
        return (False, 'TBLCUSTOMERCATEGORY not found.')
    loc_col = _detect_column(tbl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    cc_col = _detect_column(tbl, ['CATEGORYCODE', 'categorycode'])
    if not loc_col or not cc_col:
        return (False, 'LOCATIONCODE or CATEGORYCODE column missing.')
    form = dict(request.form)
    name_u = _phys(tbl, 'CATEGORYNAME')
    values: Dict[str, Any] = {}
    if name_u:
        values[name_u] = _str_clip(form, 'categoryname', 150)
    if name_u and (not str(values.get(name_u) or '').strip()):
        return (False, 'Category name is required.')
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                if is_new:
                    insert_order = [loc_col, cc_col]
                    if name_u:
                        insert_order.append(name_u)
                    params = {'lc': location_code, 'cc': category_code}
                    val_sql = [':lc', ':cc']
                    for c in insert_order[2:]:
                        pn = 'p_' + c.lower()
                        val_sql.append(f':{pn}')
                        params[pn] = values.get(c)
                    sql_ins = f"INSERT INTO {tbl} ({', '.join(insert_order)}) VALUES ({', '.join(val_sql)})"
                    cur.execute(sql_ins, params)
                else:
                    set_parts: List[str] = []
                    params_u: Dict[str, Any] = {'lc': location_code, 'cc': category_code}
                    for col, val in values.items():
                        if col in (loc_col, cc_col):
                            continue
                        tag = 'u_' + col.lower()
                        set_parts.append(f'{col} = :{tag}')
                        params_u[tag] = val
                    if set_parts:
                        sql = f"UPDATE {tbl} SET {', '.join(set_parts)} WHERE {loc_col} = :lc AND {cc_col} = :cc"
                        cur.execute(sql, params_u)
                conn.commit()
        return (True, '')
    except Exception as ex:
        err = str(ex)
        print(f'[customer_category save] {err}')
        return (False, err[:900])

@bp.route('/master/customer-category')
def category_list():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    location_code = _resolve_location_code()
    search = (request.args.get('search') or '').strip()
    rows = _list_rows(location_code, search or None)
    loc_name = _location_name(location_code)
    return render_template('customer_category/category_list.html', categories=rows, search_term=search, location_code=location_code, location_name=loc_name)

@bp.route('/master/customer-category/new', methods=['GET', 'POST'])
def category_create():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _table():
        flash('TBLCUSTOMERCATEGORY table not found. Create it in the database first.', 'error')
        return redirect(url_for('customer_category.category_list'))
    session_loc = _resolve_location_code()
    pref = (request.args.get('pref_loc') or '').strip()
    if pref.isdigit():
        session_loc = int(pref)
    locations = get_locations_list()
    if request.method == 'POST':
        sub = (request.form.get('save_nonce') or '').strip()
        if not reject_invalid_form_save_nonce(sub):
            flash('Duplicate or invalid submit. Reload the form and try again.', 'error')
            return redirect(url_for('customer_category.category_create'))
        once = (request.form.get('category_create_once') or '').strip()
        if not _verify_consume_create_once(once):
            flash('That save was skipped (duplicate submit or session lock). Open New Category again and submit only once.', 'warning')
            return redirect(url_for('customer_category.category_create'))
        loc = _parse_int_form(request.form, 'locationcode', session_loc) or session_loc
        next_code = _next_category_code(int(loc))
        ok, err = _save_from_form(location_code=int(loc), category_code=int(next_code), is_new=True)
        if ok:
            if not commit_form_save_nonce(sub):
                flash('Duplicate or invalid submit. Reload the form and try again.', 'error')
                return redirect(url_for('customer_category.category_create'))
            flash('Customer category created.', 'success')
            append_master_activity(username=_sess_user_for_log(), action='CREATE', entity='customer_category', summary=f'location={int(loc)}, category_code={int(next_code)}', detail={'locationcode': int(loc), 'categorycode': int(next_code)})
            return redirect(url_for('customer_category.category_list'))
        flash(err or 'Save failed.', 'error')
    next_code = _next_category_code(session_loc)
    loc_name = _location_name(session_loc)
    create_once = _issue_create_once()
    return render_template('customer_category/category_form.html', row_norm={}, location_code=session_loc, location_name=loc_name, next_category_code=next_code, locations=locations, is_edit=False, category_create_once=create_once)

@bp.route('/master/customer-category/<int:location_code>/<int:category_code>/edit', methods=['GET', 'POST'])
def category_edit(location_code: int, category_code: int):
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    tbl = _table()
    if not tbl:
        flash('TBLCUSTOMERCATEGORY table not found.', 'error')
        return redirect(url_for('customer_category.category_list'))
    row = _get_row(tbl, location_code, category_code)
    if not row:
        flash('Category not found.', 'error')
        return redirect(url_for('customer_category.category_list'))
    row_n = _normalize_row(row)
    locations = get_locations_list()
    loc_name = _location_name(location_code)
    if request.method == 'POST':
        sub = (request.form.get('save_nonce') or '').strip()
        if not reject_invalid_form_save_nonce(sub):
            flash('Duplicate or invalid submit. Reload the form and try again.', 'error')
            return redirect(url_for('customer_category.category_edit', location_code=location_code, category_code=category_code))
        once_edit = (request.form.get('category_edit_once') or '').strip()
        if not _verify_consume_edit_save_once(location_code, category_code, once_edit):
            flash('That save was skipped (duplicate submit or session lock). Open Edit again and submit only once.', 'warning')
            return redirect(url_for('customer_category.category_edit', location_code=location_code, category_code=category_code))
        ok, err = _save_from_form(location_code=location_code, category_code=category_code, is_new=False)
        if ok:
            if not commit_form_save_nonce(sub):
                flash('Duplicate or invalid submit. Reload the form and try again.', 'error')
                return redirect(url_for('customer_category.category_edit', location_code=location_code, category_code=category_code))
            flash('Customer category updated.', 'success')
            append_master_activity(username=_sess_user_for_log(), action='UPDATE', entity='customer_category', summary=f'location={location_code}, category_code={category_code}', detail={'locationcode': location_code, 'categorycode': category_code})
            return redirect(url_for('customer_category.category_list'))
        flash(err or 'Save failed.', 'error')
    category_edit_once = _issue_edit_save_once(location_code, category_code)
    category_delete_once = _issue_delete_once(location_code, category_code)
    return render_template('customer_category/category_form.html', row_norm=row_n, location_code=location_code, location_name=loc_name, next_category_code=category_code, locations=locations, is_edit=True, category_edit_once=category_edit_once, category_delete_once=category_delete_once)

@bp.route('/master/customer-category/<int:location_code>/<int:category_code>/delete', methods=['POST'])
def category_delete(location_code: int, category_code: int):
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    sub = (request.form.get('save_nonce') or '').strip()
    if not verify_consume_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY, sub):
        flash('Duplicate or invalid submit.', 'error')
        return redirect(url_for('customer_category.category_list'))
    once_del = (request.form.get('category_delete_once') or '').strip()
    if not _verify_consume_delete_once(location_code, category_code, once_del):
        flash('That delete was skipped (duplicate submit or session lock). Open Edit again to delete.', 'warning')
        return redirect(url_for('customer_category.category_edit', location_code=location_code, category_code=category_code))
    tbl = _table()
    if not tbl:
        flash('TBLCUSTOMERCATEGORY table not found.', 'error')
        return redirect(url_for('customer_category.category_list'))
    loc_col = _detect_column(tbl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    cc_col = _detect_column(tbl, ['CATEGORYCODE', 'categorycode'])
    if not loc_col or not cc_col:
        flash('Required columns not found.', 'error')
        return redirect(url_for('customer_category.category_list'))
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f'DELETE FROM {tbl} WHERE {loc_col} = :loc AND {cc_col} = :cc', {'loc': location_code, 'cc': category_code})
            conn.commit()
        flash('Customer category deleted.', 'success')
        append_master_activity(username=_sess_user_for_log(), action='DELETE', entity='customer_category', summary=f'location={location_code}, category_code={category_code}', detail={'locationcode': location_code, 'categorycode': category_code})
    except Exception as ex:
        flash(f'Delete failed: {str(ex)[:500]}', 'error')
    return redirect(url_for('customer_category.category_list'))
