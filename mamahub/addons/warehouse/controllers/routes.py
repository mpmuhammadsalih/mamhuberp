"""Warehouse Management: shelf, bin, rack (WAREHOUSE_STORAGE)."""
from pathlib import Path
import csv
import io
import re
import secrets
from datetime import datetime
from typing import Any, Dict, List, Optional
from nexa_http import Blueprint, Response, abort, flash, jsonify, redirect, render_template, request, session, url_for
from save_nonce import commit_form_save_nonce, reject_invalid_form_save_nonce
from db import WAREHOUSE_MASTER_TYPES, WAREHOUSE_STORAGE_TYPES, WAREHOUSE_MASTER_TABLE, _branch_location_for_warehouse, _get_connection, apply_bin_stock_delta, build_visual_stock_report_payload, delete_warehouse_storage, ensure_wms_warehouse_master_table, flatten_stock_verification_export_rows, flatten_visual_stock_audit_rows, get_bin_stock_list, get_location_info_by_dbkey, get_location_master_name_by_code, get_stock_bin_transfer_header, get_stock_bin_transfer_lines, get_stock_bin_transfers_list, get_stock_verification_report, get_warehouse_master_by_id, get_warehouse_location_sites, get_warehouse_stock_for_branch, get_warehouse_stock_list, get_warehouse_storage_flat, get_warehouse_storage_rows, get_warehouse_storage_tree, insert_warehouse_master_row, insert_warehouse_storage, list_warehouse_master_rows, next_warehouse_master_code, post_stock_bin_transfer, rebuild_warehouse_stock_from_bin_stock_cur, resolve_warehouse_id, resolve_warehouse_master_table, resolve_warehouse_loc_key_for_location_code, set_bin_stock_quantity, update_warehouse_master_row, update_warehouse_storage, warehouse_master_uses_new_schema
_ADDON_ROOT = Path(__file__).resolve().parents[1]
bp = Blueprint('warehouse', __name__, template_folder=str(_ADDON_ROOT / 'views' / 'templates'))

def _warehouse_branch_label(location_code: Any, location_name: Optional[str]=None) -> str:
    """Display branch as ``code — name`` from LOCATIONMASTER."""
    try:
        lc = int(location_code or 0)
    except (TypeError, ValueError):
        return ''
    if lc <= 0:
        return ''
    nm = str(location_name or '').strip()
    if not nm:
        nm = get_location_master_name_by_code(lc)
    return f'{lc} — {nm}' if nm else str(lc)


def _session_location_code() -> int:
    v = session.get('location_code')
    if v is not None:
        try:
            if str(v).isdigit():
                return int(v)
        except (TypeError, ValueError):
            pass
    try:
        info = get_location_info_by_dbkey(None) or {}
        loc = info.get('locationcode')
        if loc is not None:
            return int(loc) if isinstance(loc, (int, float)) else int(str(loc).strip())
    except Exception:
        pass
    return 1

def _site_key_allowed(sites: list, key: str) -> bool:
    k = (key or '').strip()
    if not k or not sites:
        return False
    for s in sites:
        sk = str(s.get('key', '')).strip()
        if sk == k:
            return True
        try:
            if s.get('warehouse_id') is not None and str(int(s['warehouse_id'])) == k:
                return True
        except (TypeError, ValueError):
            pass
        wc = str(s.get('warehouse_code') or '').strip()
        if wc and wc == k:
            return True
    return False

def _filter_warehouse_sites_for_session(sites: list) -> list:
    """Keep warehouses for the logged-in branch so bin/warehouse stock screens match GRN data."""
    if not sites:
        return []
    try:
        lc = int(_session_location_code())
    except (TypeError, ValueError):
        return list(sites)
    out: List[Dict[str, Any]] = []
    for s in sites:
        if not s:
            continue
        try:
            wid = int(s.get('warehouse_id') or s.get('key') or 0)
        except (TypeError, ValueError):
            out.append(s)
            continue
        if wid <= 0:
            out.append(s)
            continue
        wh = get_warehouse_master_by_id(wid)
        if not wh:
            out.append(s)
            continue
        try:
            wh_lc = int(wh.get('locationcode') or wh.get('LOCATIONCODE') or 0)
        except (TypeError, ValueError):
            wh_lc = 0
        if wh_lc <= 0 or wh_lc == lc:
            out.append(s)
    return out if out else list(sites)


def _pick_location_site(sites: list) -> tuple:
    """
    Choose (site_key, location_name, source) from ``?wh=`` / ``?loc=`` or session match.
    ``site_key`` is ``str(WAREHOUSE_ID)`` on new schema, else legacy store code.
    """
    if not sites:
        return ('', '', '')
    loc_param = (request.args.get('wh') or request.args.get('loc') or '').strip()
    if loc_param and _site_key_allowed(sites, loc_param):
        for s in sites:
            sk = str(s.get('key', '')).strip()
            if sk == loc_param or (str(s.get('warehouse_code') or '').strip() == loc_param):
                return (sk, str(s.get('name') or '').strip() or sk, str(s.get('source') or ''))
            try:
                if s.get('warehouse_id') is not None and str(int(s['warehouse_id'])) == loc_param:
                    return (str(int(s['warehouse_id'])), str(s.get('name') or '').strip() or sk, str(s.get('source') or ''))
            except (TypeError, ValueError):
                pass
    sess = _session_location_code()
    sess_s = str(sess).strip()
    for s in sites:
        if str(s.get('key', '')).strip() == sess_s:
            return (str(s['key']).strip(), str(s.get('name') or '').strip() or sess_s, str(s.get('source') or ''))
    rk = resolve_warehouse_loc_key_for_location_code(sess)
    if rk:
        for s in sites:
            if str(s.get('key', '')).strip() == rk:
                return (rk, str(s.get('name') or '').strip() or rk, str(s.get('source') or ''))
    s0 = sites[0]
    return (str(s0.get('key', '')).strip(), str(s0.get('name') or '').strip() or str(s0.get('key')), str(s0.get('source') or ''))

def _tbllocation_text_columns_ordered(text_cols_upper: List[str], *, name_u: Optional[str], description_u: Optional[str]) -> List[str]:
    """NAME first (if present), DESCRIPTION second, remaining alphabetically."""
    cols = [(c or '').strip().upper() for c in text_cols_upper or [] if c]
    seen = set()
    ordered: List[str] = []
    for want in ((name_u or '').strip().upper(), (description_u or '').strip().upper()):
        if want and want in cols and (want not in seen):
            ordered.append(want)
            seen.add(want)
    for c in sorted(cols):
        if c not in seen:
            ordered.append(c)
            seen.add(c)
    return ordered

def _tbllocation_name_description_under_location_banner(text_ordered_upper: List[str], *, name_u: Optional[str], description_u: Optional[str]) -> tuple[List[str], List[str]]:
    """NAME then DESCRIPTION first (below location-code banner); remaining columns unchanged."""
    nu = (name_u or '').strip().upper()
    du = (description_u or '').strip().upper()
    have = set(text_ordered_upper)
    prio: List[str] = []
    if nu and nu in have:
        prio.append(nu)
    if du and du in have and (du != nu):
        prio.append(du)
    tail = [c for c in text_ordered_upper if c not in prio]
    return (prio, tail)
_WLOC_NEW_ONCE = '_wloc_new_once'

def _wloc_issue_new_once_token() -> str:
    t = secrets.token_urlsafe(24)
    session[_WLOC_NEW_ONCE] = t
    session.modified = True
    return t

def _wloc_verify_and_consume_new_once(submitted: str | None) -> bool:
    sub = (submitted or '').strip()
    stored = session.get(_WLOC_NEW_ONCE)
    if not stored or not sub or sub != stored:
        return False
    session.pop(_WLOC_NEW_ONCE, None)
    session.modified = True
    return True

def _wloc_edit_once_session_key(lc: object, ck: object | None) -> str:
    if ck is None or str(ck).strip() == '':
        return '_wloc_edit_once_%s' % str(lc)
    return '_wloc_edit_once_%s|%s' % (str(lc), str(ck))

def _wloc_issue_edit_once_token(lc: object, ck: object | None) -> str:
    k = _wloc_edit_once_session_key(lc, ck)
    t = secrets.token_urlsafe(24)
    session[k] = t
    session.modified = True
    return t

def _wloc_verify_and_consume_edit_once(lc: object, ck: object | None, submitted: str | None) -> bool:
    sub = (submitted or '').strip()
    k = _wloc_edit_once_session_key(lc, ck)
    stored = session.get(k)
    if not stored or not sub or sub != stored:
        return False
    session.pop(k, None)
    session.modified = True
    return True

def _wh_existing_code_map(loc_key: str, storage_type: str) -> Dict[str, Dict[str, Any]]:
    rows = get_warehouse_storage_rows(loc_key, storage_type) or []
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        code = str((row or {}).get('code') or '').strip().upper()
        if code and code not in out:
            out[code] = row
    return out

def _wh_int_range(raw: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        val = int(raw)
    except (TypeError, ValueError):
        val = default
    return max(minimum, min(maximum, val))

def _wh_store_prefix_for_key(loc_key: str, fallback_index: int) -> str:
    """
    STORE1 -> S01, STORE12 -> S12, otherwise use the selected order (S01, S02...).
    Keeps the generated code readable across multiple stores.
    """
    k = (loc_key or '').strip().upper()
    m = re.search(r'(\d+)$', k)
    if m:
        try:
            n = int(m.group(1))
            if 0 < n <= 999:
                return f'S{n:02d}'
        except (TypeError, ValueError):
            pass
    return f'S{max(1, min(999, int(fallback_index or 1))):02d}'

def _generate_standard_warehouse_layout_for_site(loc_key: str, racks_count: int, shelves_per_rack: int, bins_per_shelf: int, *, store_prefix: str='') -> Dict[str, Any]:
    """
    Idempotently create S01-R01 -> S01-R01-SH01 -> S01-R01-SH01-B01 style layout for one site.
    Existing codes are reused so rerunning the generator does not duplicate rows.
    """
    lk = (loc_key or '').strip()
    pref = (store_prefix or '').strip().upper()
    result: Dict[str, Any] = {
        'loc_key': lk,
        'store_prefix': pref,
        'created': {'rack': 0, 'shelf': 0, 'bin': 0},
        'skipped': {'rack': 0, 'shelf': 0, 'bin': 0},
        'errors': [],
    }
    if not lk:
        result['errors'].append('Missing warehouse site key.')
        return result

    racks_by_code = _wh_existing_code_map(lk, 'RACK')
    shelves_by_code = _wh_existing_code_map(lk, 'SHELF')
    bins_by_code = _wh_existing_code_map(lk, 'BIN')

    def sid_from(row: Optional[Dict[str, Any]]) -> Optional[int]:
        if not row:
            return None
        try:
            sid = int(row.get('storage_id') or 0)
        except (TypeError, ValueError):
            return None
        return sid if sid > 0 else None

    for rno in range(1, racks_count + 1):
        rack_base = f'R{rno:02d}'
        rack_code = f'{pref}-{rack_base}' if pref else rack_base
        rack_row = racks_by_code.get(rack_code)
        rack_id = sid_from(rack_row)
        if rack_id:
            result['skipped']['rack'] += 1
        else:
            ok, err, new_id = insert_warehouse_storage(lk, 'RACK', rack_code, rack_code, remarks='Auto layout')
            if not ok or not new_id:
                result['errors'].append(f'{lk} {rack_code}: {err or "rack create failed"}')
                continue
            rack_id = int(new_id)
            racks_by_code[rack_code] = {'storage_id': rack_id, 'code': rack_code}
            result['created']['rack'] += 1

        for sno in range(1, shelves_per_rack + 1):
            shelf_code = f'{rack_code}-SH{sno:02d}'
            shelf_row = shelves_by_code.get(shelf_code)
            shelf_id = sid_from(shelf_row)
            if shelf_id:
                result['skipped']['shelf'] += 1
            else:
                ok, err, new_id = insert_warehouse_storage(lk, 'SHELF', shelf_code, shelf_code, remarks='Auto layout', parent_storage_id=rack_id)
                if not ok or not new_id:
                    result['errors'].append(f'{lk} {shelf_code}: {err or "shelf create failed"}')
                    continue
                shelf_id = int(new_id)
                shelves_by_code[shelf_code] = {'storage_id': shelf_id, 'code': shelf_code}
                result['created']['shelf'] += 1

            for bno in range(1, bins_per_shelf + 1):
                bin_code = f'{shelf_code}-B{bno:02d}'
                if bin_code in bins_by_code:
                    result['skipped']['bin'] += 1
                    continue
                ok, err, new_id = insert_warehouse_storage(lk, 'BIN', bin_code, bin_code, remarks='Auto layout', parent_storage_id=shelf_id)
                if not ok or not new_id:
                    result['errors'].append(f'{lk} {bin_code}: {err or "bin create failed"}')
                    continue
                bins_by_code[bin_code] = {'storage_id': int(new_id), 'code': bin_code}
                result['created']['bin'] += 1
    return result

@bp.route('/warehouse/storage')
def warehouse_storage_list():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    sites = get_warehouse_location_sites()
    loc_key, loc_name, loc_source = _pick_location_site(sites)
    rows_shelf = get_warehouse_storage_rows(loc_key, 'SHELF') if loc_key else []
    rows_bin = get_warehouse_storage_rows(loc_key, 'BIN') if loc_key else []
    rows_rack = get_warehouse_storage_rows(loc_key, 'RACK') if loc_key else []
    storage_tree = get_warehouse_storage_tree(loc_key) if loc_key else []
    flat_rows = get_warehouse_storage_flat(loc_key, tree=storage_tree) if loc_key else []
    return render_template('warehouse/warehouse_storage_list.html', location_sites=sites, selected_loc_key=loc_key, selected_loc_name=loc_name, location_source=loc_source, session_location_code=_session_location_code(), rows_shelf=rows_shelf, rows_bin=rows_bin, rows_rack=rows_rack, storage_tree=storage_tree, flat_rows=flat_rows, storage_types=WAREHOUSE_STORAGE_TYPES)

@bp.route('/warehouse/storage/save', methods=['POST'])
def warehouse_storage_save():
    if not session.get('user'):
        return jsonify({'ok': False, 'error': 'Not logged in'}, 401)
    try:
        return _warehouse_storage_save_impl()
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return jsonify({'ok': False, 'error': str(exc) or 'Save failed.'}, 500)


def _warehouse_storage_save_impl():
    data: Dict[str, Any] = request.get_json(silent=True) or {}
    mode = (data.get('mode') or '').strip().lower()
    if mode == 'bulk_standard':
        sites = get_warehouse_location_sites()
        raw_keys = data.get('location_keys')
        if not isinstance(raw_keys, list):
            one = (data.get('location_key') or '').strip()
            raw_keys = [one] if one else []
        keys: List[str] = []
        seen_keys: set[str] = set()
        for raw in raw_keys:
            k = str(raw or '').strip()
            if not k or k in seen_keys:
                continue
            if not _site_key_allowed(sites, k):
                return jsonify({'ok': False, 'error': f'Invalid warehouse location: {k}'}, 400)
            keys.append(k)
            seen_keys.add(k)
        if not keys:
            return jsonify({'ok': False, 'error': 'Choose at least one warehouse location.'}, 400)
        racks_count = _wh_int_range(data.get('racks'), 5, 1, 50)
        shelves_per_rack = _wh_int_range(data.get('shelves_per_rack'), 3, 1, 50)
        bins_per_shelf = _wh_int_range(data.get('bins_per_shelf'), 6, 1, 100)
        include_store_prefix = bool(data.get('include_store_prefix', True))
        results = [
            _generate_standard_warehouse_layout_for_site(
                k,
                racks_count,
                shelves_per_rack,
                bins_per_shelf,
                store_prefix=_wh_store_prefix_for_key(k, idx) if include_store_prefix else '',
            )
            for idx, k in enumerate(keys, start=1)
        ]
        totals = {'rack': 0, 'shelf': 0, 'bin': 0}
        skipped = {'rack': 0, 'shelf': 0, 'bin': 0}
        errors: List[str] = []
        for res in results:
            for typ in totals:
                totals[typ] += int((res.get('created') or {}).get(typ) or 0)
                skipped[typ] += int((res.get('skipped') or {}).get(typ) or 0)
            errors.extend([str(x) for x in (res.get('errors') or [])])
        return jsonify({'ok': True, 'created': totals, 'skipped': skipped, 'errors': errors[:50], 'results': results})
    if mode == 'create':
        sites = get_warehouse_location_sites()
        lk = (data.get('location_key') or '').strip()
        if not _site_key_allowed(sites, lk):
            return jsonify({'ok': False, 'error': 'Invalid or missing warehouse location.'}, 400)
        st = (data.get('storage_type') or '').strip().upper()
        if st not in WAREHOUSE_STORAGE_TYPES:
            return jsonify({'ok': False, 'error': 'Invalid storage type.'}, 400)
        code = (data.get('code') or '').strip()
        name = (data.get('name') or '').strip()
        remarks = (data.get('remarks') or '').strip()
        parent_int = None
        praw = data.get('parent_storage_id', None)
        if praw is not None and str(praw).strip() != '':
            try:
                parent_int = int(praw)
            except (TypeError, ValueError):
                return jsonify({'ok': False, 'error': 'Invalid parent shelf id.'}, 400)
        ok, err, new_id = insert_warehouse_storage(lk, st, code, name, remarks=remarks, parent_storage_id=parent_int)
        if not ok:
            return jsonify({'ok': False, 'error': err or 'Insert failed.'}, 400)
        return jsonify({'ok': True, 'storage_id': new_id})
    if mode == 'update':
        try:
            sid = int(data.get('storage_id') or 0)
        except (TypeError, ValueError):
            return jsonify({'ok': False, 'error': 'Valid storage_id is required.'}, 400)
        if sid <= 0:
            return jsonify({'ok': False, 'error': 'storage_id is required.'}, 400)
        name = (data.get('name') or '').strip()
        status = (data.get('status') or 'ACTIVE').strip()
        remarks = (data.get('remarks') or '').strip()
        do_parent = bool(data.get('update_parent'))
        parent_int = None
        if do_parent:
            praw = data.get('parent_storage_id', None)
            if praw is not None and str(praw).strip() != '':
                try:
                    parent_int = int(praw)
                except (TypeError, ValueError):
                    return jsonify({'ok': False, 'error': 'Invalid parent shelf id.'}, 400)
        ok, err = update_warehouse_storage(sid, name, status, remarks=remarks, parent_storage_id=parent_int, update_parent=do_parent)
        if not ok:
            return jsonify({'ok': False, 'error': err or 'Update failed.'}, 400)
        return jsonify({'ok': True})
    if mode == 'delete':
        try:
            sid = int(data.get('storage_id') or 0)
        except (TypeError, ValueError):
            return jsonify({'ok': False, 'error': 'Valid storage_id is required.'}, 400)
        if sid <= 0:
            return jsonify({'ok': False, 'error': 'storage_id is required.'}, 400)
        ok, err = delete_warehouse_storage(sid)
        if not ok:
            return jsonify({'ok': False, 'error': err or 'Delete failed.'}, 400)
        return jsonify({'ok': True})
    return jsonify({'ok': False, 'error': 'Invalid mode.'}, 400)

def _session_username() -> str:
    u = session.get('user')
    if u is None:
        return ''
    if isinstance(u, dict):
        return str(u.get('username') or u.get('name') or u.get('id') or '')
    return str(u)

def _allowed_warehouse_locations() -> bool:
    u = _session_username().strip().lower()
    if u in ('admin', 'super'):
        return True
    try:
        from permissions import is_menu_path_allowed
        from db import get_role_permissions, get_user_role_id
        rid = get_user_role_id(_session_username())
        if not rid:
            return False
        perms = get_role_permissions(rid) or []
        warehouse_menus = (
            'warehouse.warehouse_locations',
            'warehouse.warehouse_storage_list',
            'warehouse.warehouse_bin_stock',
            'warehouse.warehouse_visual_stock',
            'warehouse.warehouse_stock_verification',
            'warehouse.warehouse_stock_counting',
            'warehouse.warehouse_stock_counting_mobile',
            'warehouse.warehouse_stock_count_price',
        )
        return any(is_menu_path_allowed(p, perms) for p in warehouse_menus)
    except Exception:
        return False

def _bootstrap_warehouse_master_ui() -> None:
    ok, msg, created = ensure_wms_warehouse_master_table()
    if not ok and msg:
        flash(msg[:900], 'error')
    elif created:
        flash('Created table WAREHOUSE_MASTER — add warehouse location / store rows below.', 'success')

def _bootstrap_tbllocation_ui() -> None:
    """Legacy alias."""
    _bootstrap_warehouse_master_ui()

def _wh_form_bool(name: str) -> bool:
    return bool(request.form.get(name))

def _wh_row_from_form() -> Dict[str, Any]:
    return {
        'warehouse_code': (request.form.get('warehouse_code') or '').strip().upper(),
        'warehouse_name': (request.form.get('warehouse_name') or '').strip(),
        'locationcode': _session_location_code(),
        'warehouse_type': (request.form.get('warehouse_type') or 'WAREHOUSE').strip().upper(),
        'address': (request.form.get('address') or '').strip(),
        'contact_person': (request.form.get('contact_person') or '').strip(),
        'phone_no': (request.form.get('phone_no') or '').strip(),
        'allow_negative_stock': 'Y' if _wh_form_bool('allow_negative_stock') else 'N',
        'batch_enabled': 'Y' if _wh_form_bool('batch_enabled') else 'N',
        'bin_enabled': 'Y' if _wh_form_bool('bin_enabled') else 'N',
        'is_active': 'Y' if _wh_form_bool('is_active') else 'N',
        'remarks': (request.form.get('remarks') or '').strip(),
        'created_by': str(session.get('user') or '')[:50] or None,
        'updated_by': str(session.get('user') or '')[:50] or None,
    }

@bp.route('/warehouse/locations')
def warehouse_locations_list():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _allowed_warehouse_locations():
        abort(403)
    _bootstrap_warehouse_master_ui()
    rows = list_warehouse_master_rows()
    return render_template('warehouse/warehouse_locations_list.html', rows=rows, warehouse_types=WAREHOUSE_MASTER_TYPES)

@bp.route('/warehouse/locations/new', methods=('GET', 'POST'))
def warehouse_locations_new():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _allowed_warehouse_locations():
        abort(403)
    _bootstrap_warehouse_master_ui()
    if not resolve_warehouse_master_table():
        flash('WAREHOUSE_MASTER table is not available.', 'error')
        return redirect(url_for('warehouse.warehouse_locations_list'))
    next_code, alloc_err = next_warehouse_master_code()
    row: Dict[str, Any] = {'locationcode': _session_location_code(), 'warehouse_type': 'WAREHOUSE', 'batch_enabled': 'Y', 'bin_enabled': 'Y', 'is_active': 'Y'}
    if request.method == 'POST':
        sub = (request.form.get('save_nonce') or '').strip()
        if not reject_invalid_form_save_nonce(sub):
            flash('Duplicate or invalid submit. Open Add Warehouse again and submit once.', 'error')
            return redirect(url_for('warehouse.warehouse_locations_new'))
        if not _wloc_verify_and_consume_new_once(request.form.get('wloc_once')):
            flash('That save was skipped (duplicate submit or session lock). Open Add Warehouse again, or submit only once.', 'warning')
            return redirect(url_for('warehouse.warehouse_locations_new'))
        row = _wh_row_from_form()
        if not row.get('warehouse_code'):
            row['warehouse_code'] = (next_code or '').strip().upper()
        if not row.get('warehouse_name'):
            row['warehouse_name'] = row.get('warehouse_code') or ''
        ok, err = insert_warehouse_master_row(row)
        if ok:
            if not commit_form_save_nonce(sub):
                flash('Duplicate or invalid submit. Open Add Warehouse again and submit once.', 'error')
                return redirect(url_for('warehouse.warehouse_locations_new'))
            wh_code = row.get('warehouse_code')
            flash('Warehouse %(c)s created.' % {'c': wh_code}, 'success')
            return redirect(url_for('warehouse.warehouse_locations_list'))
        flash(err or 'Create failed.', 'error')
    wloc_form_once = _wloc_issue_new_once_token()
    return render_template('warehouse/warehouse_locations_new.html', row=row, warehouse_types=WAREHOUSE_MASTER_TYPES, next_warehouse_code=next_code, alloc_error=alloc_err, location_readonly_label=_warehouse_branch_label(_session_location_code()), wloc_form_once=wloc_form_once)

@bp.route('/warehouse/locations/edit', methods=('GET', 'POST'))
def warehouse_locations_edit():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _allowed_warehouse_locations():
        abort(403)
    _bootstrap_warehouse_master_ui()
    wid = request.args.get('id') or request.form.get('warehouse_id')
    if not wid:
        flash('Missing warehouse id.', 'error')
        return redirect(url_for('warehouse.warehouse_locations_list'))
    if request.method == 'POST':
        sub = (request.form.get('save_nonce') or '').strip()
        if not reject_invalid_form_save_nonce(sub):
            flash('Duplicate or invalid submit. Reload the page and submit once.', 'error')
            return redirect(url_for('warehouse.warehouse_locations_edit', id=wid))
        if not _wloc_verify_and_consume_edit_once(wid, None, request.form.get('wloc_once')):
            flash('That save was skipped (duplicate submit or session lock). Submit only once.', 'warning')
            return redirect(url_for('warehouse.warehouse_locations_edit', id=wid))
        data = _wh_row_from_form()
        updates = {k: v for k, v in data.items() if k not in ('warehouse_code', 'created_by')}
        ok, err = update_warehouse_master_row(wid, updates)
        if ok:
            if not commit_form_save_nonce(sub):
                flash('Duplicate or invalid submit. Reload the page and submit once.', 'error')
                return redirect(url_for('warehouse.warehouse_locations_edit', id=wid))
            flash('Warehouse updated.', 'success')
            return redirect(url_for('warehouse.warehouse_locations_list'))
        flash(err or 'Save failed.', 'error')
    row = get_warehouse_master_by_id(wid)
    if not row:
        flash('Warehouse not found.', 'error')
        return redirect(url_for('warehouse.warehouse_locations_list'))
    wloc_form_once = _wloc_issue_edit_once_token(wid, None)
    lc = row.get('locationcode') or row.get('LOCATIONCODE')
    branch_label = _warehouse_branch_label(lc, row.get('locationname') or row.get('LOCATIONNAME'))
    return render_template('warehouse/warehouse_locations_edit.html', row=row, warehouse_types=WAREHOUSE_MASTER_TYPES, branch_label=branch_label, wloc_form_once=wloc_form_once)

def _bss_page_summary(stock_rows: List[Dict[str, Any]], transfers: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Dashboard KPIs for bin stock screen (aligned with batch/lot inquiry style)."""
    total = 0.0
    items: set = set()
    bins: set = set()
    for r in stock_rows or []:
        try:
            total += float(r.get('qty') or 0)
        except (TypeError, ValueError):
            pass
        ic = r.get('itemcode')
        if ic is not None and str(ic).strip() != '':
            items.add(str(ic).strip())
        sid = r.get('storage_id')
        bc = r.get('bin_code')
        key = sid if sid is not None else bc
        if key is not None:
            bins.add(str(key))
    return {'total_qty': round(total, 4), 'line_count': len(stock_rows or []), 'item_count': len(items), 'bin_positions': len(bins), 'recent_transfers': len(transfers or [])}


def _bss_warehouse_summary(wh_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Branch-level ``WAREHOUSE_STOCK`` KPIs when no warehouse site is picked."""
    total = 0.0
    items: set = set()
    whs: set = set()
    for r in wh_rows or []:
        try:
            total += float(r.get('qty') or 0)
        except (TypeError, ValueError):
            pass
        ic = r.get('itemcode')
        if ic is not None and str(ic).strip() != '':
            items.add(str(ic).strip())
        wid = r.get('warehouse_id')
        if wid is not None:
            whs.add(str(wid))
    return {
        'wh_total_qty': round(total, 4),
        'wh_line_count': len(wh_rows or []),
        'wh_item_count': len(items),
        'wh_warehouse_count': len(whs),
    }


def _vsp_opts_from_request() -> Dict[str, Any]:
    args = request.args
    include_zero_qty = str(args.get('include_zero') or '').strip().lower() in ('1', 'true', 'yes', 'on')
    totals_basis = (args.get('basis') or 'separate').strip().lower()
    if totals_basis not in ('store', 'warehouse', 'separate'):
        totals_basis = 'separate'
    raw_lots = str(args.get('lots', '1')).strip().lower()
    attach_bin_lots = raw_lots not in ('0', 'false', 'no', 'off')
    return {'include_zero_qty': include_zero_qty, 'totals_basis': totals_basis, 'attach_bin_lots': attach_bin_lots}


def _vsp_warehouse_site_display_label(loc_key: str, loc_name: str) -> Optional[str]:
    k = (loc_key or '').strip()
    if not k:
        return None
    n = (loc_name or '').strip()
    if n and n.upper() != k.upper():
        return '%s — %s' % (n, k)
    return k


_VSP_EXPORT_FIELDNAMES = (
    'branch_location_code',
    'warehouse_loc_key',
    'wh_site_label',
    'theoretical_basis',
    'tree',
    'store',
    'rack',
    'shelf',
    'bin',
    'storage_id',
    'itemcode',
    'itemname',
    'qty',
    'lot_id',
    'batch_no',
    'expiry_date',
)


@bp.route('/warehouse/visual-stock')
def warehouse_visual_stock():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _allowed_warehouse_locations():
        abort(403)
    sites = get_warehouse_location_sites()
    loc_key, loc_name, loc_source = _pick_location_site(sites)
    loc_code = _session_location_code()
    opts = _vsp_opts_from_request()
    wsl = _vsp_warehouse_site_display_label(loc_key, loc_name)
    payload = build_visual_stock_report_payload(loc_code, wh_loc_key=loc_key or None, warehouse_site_label=wsl, **opts)
    return render_template('warehouse/visual_stock_report.html', location_sites=sites, selected_loc_key=loc_key, selected_loc_name=loc_name, location_source=loc_source, session_location_code=loc_code, vsp_payload=payload)


@bp.route('/warehouse/visual-stock/export.csv')
def warehouse_visual_stock_export_csv():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _allowed_warehouse_locations():
        abort(403)
    sites = get_warehouse_location_sites()
    loc_key, loc_name, loc_source = _pick_location_site(sites)
    loc_code = _session_location_code()
    opts = _vsp_opts_from_request()
    wsl = _vsp_warehouse_site_display_label(loc_key, loc_name)
    payload = build_visual_stock_report_payload(loc_code, wh_loc_key=loc_key or None, warehouse_site_label=wsl, **opts)
    rows = flatten_visual_stock_audit_rows(payload)
    buf = io.StringIO()
    wrt = csv.DictWriter(buf, fieldnames=list(_VSP_EXPORT_FIELDNAMES))
    wrt.writeheader()
    for r in rows:
        wrt.writerow({k: r.get(k, '') for k in _VSP_EXPORT_FIELDNAMES})
    fname = 'visual-stock-b%s-%s.csv' % (loc_code, datetime.now().strftime('%Y%m%d-%H%M%S'))
    return Response(buf.getvalue().encode('utf-8-sig'), headers={'Content-Disposition': 'attachment; filename="%s"' % fname}, media_type='text/csv; charset=utf-8')


def _stock_verification_opts_from_request() -> Dict[str, Any]:
    args = request.args
    include_zero = str(args.get('include_zero') or '').strip().lower() in ('1', 'true', 'yes', 'on')
    mismatches_only = str(args.get('mismatch') or args.get('mismatches_only') or '').strip().lower() in ('1', 'true', 'yes', 'on')
    search = (args.get('q') or args.get('search') or '').strip()
    item_code: Optional[int] = None
    raw_ic = (args.get('item') or args.get('itemcode') or '').strip()
    if raw_ic.isdigit():
        try:
            item_code = int(raw_ic)
        except (TypeError, ValueError):
            item_code = None
    warehouse_id: Optional[int] = None
    raw_wh = (args.get('warehouse_id') or args.get('wh') or '').strip()
    if raw_wh.isdigit():
        try:
            warehouse_id = int(raw_wh)
        except (TypeError, ValueError):
            warehouse_id = None
    try:
        page = int(args.get('page') or 1)
    except (TypeError, ValueError):
        page = 1
    page = max(1, page)
    try:
        per_page = int(args.get('per_page') or args.get('limit') or 200)
    except (TypeError, ValueError):
        per_page = 200
    per_page = max(50, min(per_page, 500))
    offset = (page - 1) * per_page
    return {
        'include_zero': include_zero,
        'mismatches_only': mismatches_only,
        'search': search,
        'item_code': item_code,
        'warehouse_id': warehouse_id,
        'page': page,
        'per_page': per_page,
        'offset': offset,
    }


_SV_EXPORT_FIELDNAMES = (
    'location_code', 'warehouse_id', 'warehouse_label', 'itemcode', 'itemname',
    'itemmaster_qty', 'warehouse_branch_total', 'warehouse_qty', 'bin_qty',
    'lot_qty', 'lot_bin_qty', 'lot_unalloc_qty', 'lot_at_warehouse_qty',
    'itemjournal_qty', 'itemjournal_branch_qty',
    'delta_im_wh', 'delta_im_ij', 'delta_wh_bin', 'delta_wh_lot', 'delta_wh_ij',
    'status', 'issues',
)


@bp.route('/warehouse/stock-verification')
def warehouse_stock_verification():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _allowed_warehouse_locations():
        abort(403)
    loc_code = _session_location_code()
    opts = _stock_verification_opts_from_request()
    warehouses = [
        {'warehouse_id': r.get('warehouse_id'), 'warehouse_code': r.get('warehouse_code'), 'warehouse_name': r.get('warehouse_name')}
        for r in (list_warehouse_master_rows(active_only=True) or [])
        if int(r.get('locationcode') or 0) == int(loc_code)
    ]
    return render_template(
        'warehouse/stock_verification.html',
        session_location_code=loc_code,
        warehouses=warehouses,
        opts=opts,
    )


@bp.route('/warehouse/stock-verification/export.csv')
def warehouse_stock_verification_export_csv():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _allowed_warehouse_locations():
        abort(403)
    loc_code = _session_location_code()
    opts = _stock_verification_opts_from_request()
    payload = get_stock_verification_report(
        loc_code,
        opts.get('warehouse_id'),
        include_zero=opts['include_zero'],
        mismatches_only=opts['mismatches_only'],
        item_code=opts.get('item_code'),
        search=opts.get('search'),
        limit=0,
        offset=0,
    )
    rows = flatten_stock_verification_export_rows(payload)
    buf = io.StringIO()
    wrt = csv.DictWriter(buf, fieldnames=list(_SV_EXPORT_FIELDNAMES))
    wrt.writeheader()
    for r in rows:
        wrt.writerow({k: r.get(k, '') for k in _SV_EXPORT_FIELDNAMES})
    fname = 'stock-verification-b%s-%s.csv' % (loc_code, datetime.now().strftime('%Y%m%d-%H%M%S'))
    return Response(buf.getvalue().encode('utf-8-sig'), headers={'Content-Disposition': 'attachment; filename="%s"' % fname}, media_type='text/csv; charset=utf-8')


@bp.route('/warehouse/api/stock-verification')
def warehouse_stock_verification_api():
    if not session.get('user'):
        return jsonify({'ok': False, 'error': 'Not logged in'}, 401)
    if not _allowed_warehouse_locations():
        return jsonify({'ok': False, 'error': 'Forbidden'}, 403)
    loc_code = _session_location_code()
    opts = _stock_verification_opts_from_request()
    payload = get_stock_verification_report(
        loc_code,
        opts.get('warehouse_id'),
        include_zero=opts['include_zero'],
        mismatches_only=opts['mismatches_only'],
        item_code=opts.get('item_code'),
        search=opts.get('search'),
        limit=opts['per_page'],
        offset=opts['offset'],
    )
    return jsonify({'ok': True, **payload})


@bp.route('/warehouse/api/visual-stock')
def warehouse_visual_stock_api():
    if not session.get('user'):
        return jsonify({'ok': False, 'error': 'Not logged in'}, 401)
    if not _allowed_warehouse_locations():
        return jsonify({'ok': False, 'error': 'Forbidden'}, 403)
    sites = get_warehouse_location_sites()
    loc_key, loc_name, loc_source = _pick_location_site(sites)
    loc_code = _session_location_code()
    opts = _vsp_opts_from_request()
    wsl = _vsp_warehouse_site_display_label(loc_key, loc_name)
    payload = build_visual_stock_report_payload(loc_code, wh_loc_key=loc_key or None, warehouse_site_label=wsl, **opts)
    payload['site'] = {'key': loc_key, 'name': loc_name, 'source': loc_source}
    return jsonify({'ok': True, **payload})


@bp.route('/warehouse/bin-stock')
def warehouse_bin_stock():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    sites = _filter_warehouse_sites_for_session(get_warehouse_location_sites())
    loc_key, loc_name, loc_source = _pick_location_site(sites)
    rows_bin: List[Dict[str, Any]] = []
    stock_rows: List[Dict[str, Any]] = []
    transfers: List[Dict[str, Any]] = []
    loc_code = _session_location_code()
    if loc_key:
        wid_pick = resolve_warehouse_id(loc_key)
        if wid_pick:
            loc_code = _branch_location_for_warehouse(int(wid_pick), loc_code)
        br = get_warehouse_storage_rows(loc_key, 'BIN') or []
        sr = get_warehouse_storage_rows(loc_key, 'STAGING') or []
        for r in sr:
            if r and (not (r.get('storage_type') or '').strip()):
                r['storage_type'] = 'STAGING'
        merged = list(br) + list(sr)
        merged.sort(key=lambda x: str((x or {}).get('code') or '').upper())
        rows_bin = merged
        stock_rows = get_bin_stock_list(loc_key, loc_code) or []
        transfers = get_stock_bin_transfers_list(loc_key, 30) or []
    selected_wid: Optional[int] = None
    if loc_key:
        try:
            selected_wid = int(resolve_warehouse_id(loc_key) or 0) or None
        except (TypeError, ValueError):
            selected_wid = None
    wh_stock_rows = get_warehouse_stock_for_branch(
        loc_code,
        warehouse_id=selected_wid,
        limit=2000,
    ) or []
    if loc_key and selected_wid and not wh_stock_rows and stock_rows:
        user = str(session.get('user') or 'web')[:200]
        try:
            with _get_connection() as conn:
                with conn.cursor() as cur:
                    err = rebuild_warehouse_stock_from_bin_stock_cur(
                        cur, int(selected_wid), int(loc_code), updated_by=user,
                    )
                    if err:
                        raise RuntimeError(err)
                conn.commit()
            wh_stock_rows = get_warehouse_stock_for_branch(
                loc_code, warehouse_id=selected_wid, limit=2000,
            ) or get_warehouse_stock_list(int(selected_wid), loc_code, limit=2000) or []
        except Exception:
            pass
    bss_summary = {**_bss_warehouse_summary(wh_stock_rows), **_bss_page_summary(stock_rows, transfers)}
    return render_template(
        'warehouse/warehouse_bin_stock.html',
        location_sites=sites,
        selected_loc_key=loc_key,
        selected_loc_name=loc_name,
        selected_warehouse_id=selected_wid,
        location_source=loc_source,
        session_location_code=loc_code,
        bin_rows=rows_bin,
        stock_rows=stock_rows,
        warehouse_stock_rows=wh_stock_rows,
        transfers=transfers,
        bss_summary=bss_summary,
    )

@bp.route('/warehouse/bin-stock/transfer/<int:transfer_id>/lines')
def warehouse_bin_transfer_lines_json(transfer_id: int):
    if not session.get('user'):
        return jsonify({'ok': False, 'error': 'Not logged in'}, 401)
    sites = get_warehouse_location_sites()
    hdr = get_stock_bin_transfer_header(transfer_id)
    if not hdr:
        return jsonify({'ok': False, 'error': 'Transfer not found.'}, 404)
    hk = str(hdr.get('warehouse_id') or hdr.get('loc_key') or '').strip()
    if not _site_key_allowed(sites, hk):
        return jsonify({'ok': False, 'error': 'Access denied.'}, 403)
    lines = get_stock_bin_transfer_lines(transfer_id) or []
    return jsonify({'ok': True, 'lines': lines, 'header': hdr})

@bp.route('/warehouse/bin-stock/save', methods=['POST'])
def warehouse_bin_stock_save():
    if not session.get('user'):
        return jsonify({'ok': False, 'error': 'Not logged in'}, 401)
    data: Dict[str, Any] = request.get_json(silent=True) or {}
    mode = (data.get('mode') or '').strip().lower()
    loc_code = _session_location_code()
    user = _session_username()
    if mode == 'transfer':
        sites = get_warehouse_location_sites()
        lk = (data.get('location_key') or '').strip()
        if not _site_key_allowed(sites, lk):
            return jsonify({'ok': False, 'error': 'Invalid or missing warehouse location.'}, 400)
        try:
            from_id = int(data.get('from_storage_id') or 0)
            to_id = int(data.get('to_storage_id') or 0)
        except (TypeError, ValueError):
            return jsonify({'ok': False, 'error': 'Invalid from or to bin.'}, 400)
        raw_lines = data.get('lines')
        if not isinstance(raw_lines, list):
            raw_lines = []
        if len(raw_lines) == 0:
            ic = data.get('itemcode')
            qn = data.get('qty')
            if ic is not None and qn is not None:
                raw_lines = [{'itemcode': ic, 'qty': qn}]
        ok, err, tid = post_stock_bin_transfer(lk, from_id, to_id, raw_lines, loc_code, created_by=user, remarks=(data.get('remarks') or '').strip())
        if not ok:
            return jsonify({'ok': False, 'error': err or 'Transfer failed.'}, 400)
        return jsonify({'ok': True, 'transfer_id': tid})
    if mode == 'delta':
        sites = get_warehouse_location_sites()
        lk = (data.get('location_key') or '').strip()
        if not _site_key_allowed(sites, lk):
            return jsonify({'ok': False, 'error': 'Invalid or missing warehouse location.'}, 400)
        try:
            sid = int(data.get('storage_id') or 0)
            ic = int(data.get('itemcode') or 0)
            delta = float(data.get('delta') or 0)
        except (TypeError, ValueError):
            return jsonify({'ok': False, 'error': 'Invalid bin, item, or quantity change.'}, 400)
        ok, err = apply_bin_stock_delta(lk, sid, ic, delta, loc_code, updated_by=user)
        if not ok:
            return jsonify({'ok': False, 'error': err or 'Adjust failed.'}, 400)
        return jsonify({'ok': True})
    if mode == 'set':
        sites = get_warehouse_location_sites()
        lk = (data.get('location_key') or '').strip()
        if not _site_key_allowed(sites, lk):
            return jsonify({'ok': False, 'error': 'Invalid or missing warehouse location.'}, 400)
        try:
            sid = int(data.get('storage_id') or 0)
            ic = int(data.get('itemcode') or 0)
            nq = float(data.get('qty') or 0)
        except (TypeError, ValueError):
            return jsonify({'ok': False, 'error': 'Invalid bin, item, or quantity.'}, 400)
        ok, err = set_bin_stock_quantity(lk, sid, ic, nq, loc_code, updated_by=user)
        if not ok:
            return jsonify({'ok': False, 'error': err or 'Set quantity failed.'}, 400)
        return jsonify({'ok': True})
    return jsonify({'ok': False, 'error': 'Invalid mode. Use transfer, delta, or set.'}, 400)


from addons.warehouse.controllers.stock_count_routes import register as _register_stock_count_routes
_register_stock_count_routes(bp)
from addons.warehouse.controllers.stock_count_price_routes import register as _register_stock_count_price_routes
_register_stock_count_price_routes(bp)
