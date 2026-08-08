"""HO module: Itemmaster Central."""
from pathlib import Path
import csv
import io
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from nexa_http import Blueprint, Response, flash, g, redirect, render_template, request, session, jsonify, url_for
from config.settings import is_multi_db_mode
from master_activity_log import append_master_activity, fetch_master_activity_log
from save_nonce import GLOBAL_SAVE_NONCE_SESSION_KEY, issue_save_nonce, verify_consume_save_nonce
from master_name_duplicate import find_master_name_duplicate, master_name_duplicate_message
from addons.itemmaster.controllers.routes import _grn_new_item_default_account_fields
from addons.ho.db_itemmaster_central_store import check_item_exists_by_rawabicode_for_tenant, get_item_alternate_uom_for_tenant, get_item_alternate_uoms_for_tenant, get_item_by_code_for_tenant, get_item_by_manufacturer_id_for_tenant, get_item_details_by_rawabicode_for_tenant, get_item_rawabicode_for_tenant, get_itemmaster_list_from_tenant, get_next_item_code_for_tenant, remap_itemmaster_to_tenant, save_itemmaster_with_alternate_uoms_for_tenant, _ensure_itemdeleted_table, _ensure_itemmaster_convert_columns, _ensure_itemmaster_tempitemcode_column
from addons.ho.db_supplier_central_store import get_next_supplier_code_for_tenant, get_supplier_by_code_for_tenant, get_supplier_list_from_tenant, save_supplier_in_tenant, supplier_exists_for_tenant
from addons.ho.db_item_request import _coerce_request_location_code, _ensure_item_request_temp_tables, _get_item_request_alt_rows, _get_item_request_rows_by_status, _get_item_request_status_counts, _get_item_request_temp_row, _get_item_request_temp_row_by_item_code, _get_location_dbcode_and_dbkey, _get_next_item_request_code_from_temp, _get_request_location_row_by_code, _get_request_location_row_by_locationcode, _get_request_location_rows, _item_request_can_access_temp_row, _item_request_list_branch_filter
from addons.ho.customer_alert_control import (
    ensure_customer_alert_control_table as _ensure_customer_alert_control_table,
    get_cr_ai_auto_convert_enabled as _get_cr_ai_auto_convert_enabled,
    get_customer_request_alert_poll_enabled as _get_customer_request_alert_poll_enabled,
    set_cr_ai_auto_convert_enabled as _set_cr_ai_auto_convert_enabled,
)
from db import get_active_tenants_with_network, _safe_rows_auth, get_tenant_locationcode_from_auth, get_categories, get_suppliers, get_units, get_item_properties, get_item_origins, get_all_chart_of_accounts, get_item_store_inventory, get_item_store_inventory_for_tenant, _get_tenant_connection, _detect_table, _detect_column, resolve_warehouse_master_table, resolve_legacy_store_table, list_warehouse_master_rows, _safe_rows, ensure_default_party_accounts, get_user_customer_creation, get_user_allowed_tenant_ids, get_user_tenant_id, PRIVILEGED_USERS, DEFAULT_PARTY_ACCOUNTS
_ADDON_ROOT = Path(__file__).resolve().parents[1]
bp = Blueprint('ho', __name__, template_folder=str(_ADDON_ROOT / 'views' / 'templates'))

def _get_ho_location_code() -> int:
    lc = get_tenant_locationcode_from_auth('HO')
    return lc if lc is not None and lc > 0 else 1

def _get_tenant_location_code(tenant_id: str) -> Optional[int]:
    """Return the LOCATIONCODE for the given tenant from tenant_databases (auth DB)."""
    return get_tenant_locationcode_from_auth((tenant_id or '').strip())

def _target_dbs_for_current_user(*, exclude_tenant_id: str='HO') -> List[Dict[str, Any]]:
    """Active tenant DBs filtered by the logged-in user's assigned tenant list."""
    target_dbs = get_active_tenants_with_network()
    exclude_key = (exclude_tenant_id or '').strip().lower()
    if exclude_key:
        target_dbs = [t for t in target_dbs if str(t.get('tenant_id') or '').strip().lower() != exclude_key]
    user = str(session.get('user') or '').strip()
    if not user or user.lower() == 'admin':
        return target_dbs
    allowed = get_user_allowed_tenant_ids(user)
    if not allowed:
        return target_dbs
    allowed_set = {str(t or '').strip().lower() for t in allowed if str(t or '').strip()}
    return [t for t in target_dbs if str(t.get('tenant_id') or '').strip().lower() in allowed_set]

def _get_tbllocation_store_rows() -> list:
    if resolve_warehouse_master_table():
        out = []
        seen = set()
        for r in list_warehouse_master_rows(active_only=True) or []:
            code = str(r.get('warehouse_code') or '').strip().upper()
            if not code or code in seen:
                continue
            seen.add(code)
            out.append({'code': code, 'name': str(r.get('warehouse_name') or '').strip()})
        return out
    tbl = resolve_legacy_store_table()
    if not tbl:
        return []
    code_col = _detect_column(tbl, ['DBCODE', 'dbcode', 'CODE', 'code'])
    desc_col = _detect_column(tbl, ['NAME', 'name', 'DESCRIPTION', 'description'])
    if not code_col:
        return []
    desc_expr = desc_col if desc_col else "''"
    q = f'SELECT {code_col} AS code, {desc_expr} AS name FROM {tbl} WHERE {code_col} IS NOT NULL ORDER BY {code_col}'
    try:
        rows = _safe_rows(q, {}) or []
    except Exception:
        rows = []
    out = []
    seen = set()
    for r in rows:
        code = str(r.get('code') or '').strip().upper()
        if not code or code in seen:
            continue
        seen.add(code)
        out.append({'code': code, 'name': str(r.get('name') or '').strip()})
    return out

def _safe_int(value, default=0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default

def _safe_num(value, default=0):
    try:
        text = str(value).strip()
        if text == '':
            return default
        if '.' in text:
            return float(text)
        return int(text)
    except (TypeError, ValueError):
        return default

def _safe_num_or_none(value):
    try:
        text = str(value).strip()
        if text == '':
            return None
        if '.' in text:
            return float(text)
        return int(text)
    except (TypeError, ValueError):
        return None
_ITEMMASTER_CENTRAL_ENTITY = 'itemmaster_central'
_SUPPLIER_CENTRAL_ENTITY = 'supplier_central'
_SUPPLIER_CENTRAL_SAVE_LOCKS: Dict[str, threading.Lock] = {}
_SUPPLIER_CENTRAL_SAVE_LOCKS_GUARD = threading.Lock()

def _supplier_central_save_lock_key() -> str:
    user = str(session.get('user') or '').strip().lower()
    tenant = str(session.get('tenant_id') or '').strip().lower()
    return f'{user}:{tenant}:supplier_central_save'

def _release_supplier_central_save_lock() -> None:
    lock = getattr(g, '_supplier_central_save_lock', None)
    if lock is None:
        return
    try:
        lock.release()
    except RuntimeError:
        pass
    g._supplier_central_save_lock = None

@bp.before_request
def _supplier_central_save_once_lock():
    if request.method != 'POST' or request.endpoint != 'ho.supplier_central_save':
        return None
    key = _supplier_central_save_lock_key()
    with _SUPPLIER_CENTRAL_SAVE_LOCKS_GUARD:
        lock = _SUPPLIER_CENTRAL_SAVE_LOCKS.setdefault(key, threading.Lock())
    if not lock.acquire(blocking=False):
        flash('Supplier save already in progress. Please wait.', 'error')
        return redirect(request.referrer or url_for('ho.supplier_central'))
    g._supplier_central_save_lock = lock
    return None

@bp.after_request
def _supplier_central_save_once_unlock(response):
    _release_supplier_central_save_lock()
    return response

@bp.teardown_request
def _supplier_central_save_once_teardown(_exc):
    _release_supplier_central_save_lock()

def _central_activity_normalize_val(val: Any) -> Any:
    if val is None:
        return None
    if hasattr(val, 'strftime'):
        try:
            return val.strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            return str(val)
    if isinstance(val, Decimal):
        try:
            return float(val)
        except Exception:
            return str(val)
    if isinstance(val, (bytes, bytearray)):
        try:
            return val.decode('utf-8', errors='replace')
        except Exception:
            return str(val)
    return val

def _central_activity_item_snapshot(row: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Stable dict of ITEMMASTER row fields for before/after comparison (HO audit)."""
    if not row:
        return {}
    skip = {'display_item_name'}
    out: Dict[str, Any] = {}
    for k, v in row.items():
        lk = str(k).lower()
        if lk in skip:
            continue
        out[lk] = _central_activity_normalize_val(v)
    return dict(sorted(out.items()))

def _central_activity_diff_snapshots(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    changes: Dict[str, Dict[str, Any]] = {}
    for k in sorted(set(before) | set(after)):
        bv = before.get(k)
        av = after.get(k)
        if bv != av:
            changes[k] = {'before': bv, 'after': av}
    return changes

def _central_activity_log_safe(*, username: Optional[str], action: str, summary: str, detail: Optional[Dict[str, Any]]=None) -> None:
    try:
        append_master_activity(username=username, action=action, entity=_ITEMMASTER_CENTRAL_ENTITY, summary=summary, detail=detail or {})
    except Exception:
        pass

@bp.route('/ho/itemmaster-central')
def itemmaster_central():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    ho_tenant_id = 'HO'
    ho_loc = _get_ho_location_code()
    search = (request.args.get('search') or '').strip()
    sort_by = (request.args.get('sort_by') or 'rawabicode').strip().lower()
    sort_dir = (request.args.get('sort_dir') or 'desc').strip().lower()
    page_raw = (request.args.get('page') or '1').strip()
    try:
        page = max(1, int(page_raw))
    except (TypeError, ValueError):
        page = 1
    items_per_page = 100
    items, total_count = get_itemmaster_list_from_tenant(tenant_id=ho_tenant_id, search=search if search else None, page=page, items_per_page=items_per_page, location_code=ho_loc, sort_by=sort_by, sort_dir=sort_dir)
    total_pages = (total_count + items_per_page - 1) // items_per_page if total_count > 0 else 1
    target_dbs = _target_dbs_for_current_user(exclude_tenant_id=session.get('tenant_id') or ho_tenant_id)
    return render_template(
        'ho/ho_itemmaster_central.html',
        items=items,
        search=search,
        sort_by=sort_by,
        sort_dir=sort_dir,
        current_page=page,
        total_pages=total_pages,
        total_count=total_count,
        items_per_page=items_per_page,
        source_location_code=ho_loc,
        source_tenant_id=ho_tenant_id,
        target_dbs=target_dbs,
    )

@bp.route('/ho/itemmaster-central/activity-log')
def itemmaster_central_activity_log():
    """Audit report for HO Itemmaster Central (save/update/sync, remap, delete)."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    export_raw = (request.args.get('export') or '').strip().lower()
    try:
        limit = int(request.args.get('limit') or 800)
    except (TypeError, ValueError):
        limit = 800
    limit = max(50, min(limit, 2000))
    rows = fetch_master_activity_log(entity_exact=_ITEMMASTER_CENTRAL_ENTITY, limit=limit)
    if export_raw == 'csv':
        buf = io.StringIO()
        buf.write('\ufeff')
        w = csv.writer(buf)
        w.writerow(['LOG_ID', 'LOGGED_AT', 'ACTION', 'ENTITY', 'USERNAME', 'SUMMARY', 'DETAIL_JSON'])
        for r in rows:
            dj = ''
            det = r.get('detail')
            if isinstance(det, dict):
                dj = json.dumps(det, ensure_ascii=False, default=str)
            w.writerow([r.get('log_id'), r.get('logged_at'), r.get('action'), r.get('entity'), r.get('username'), r.get('summary'), dj])
        fn = f"itemmaster_central_activity_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        return Response(buf.getvalue(), mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename="{fn}"'})
    return render_template('ho/ho_itemmaster_central_activity_log.html', rows=rows, limit=limit)

@bp.route('/ho/itemmaster-central/remap', methods=['POST'])
def itemmaster_central_remap():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    data = request.get_json(silent=True) or {}
    raw_targets = data.get('target_tenant_ids')
    if not isinstance(raw_targets, list):
        raw_targets = []
    single_target = (data.get('target_tenant_id') or '').strip()
    if single_target:
        raw_targets.append(single_target)
    target_tenant_ids = []
    for t in raw_targets:
        tid = str(t or '').strip()
        if tid and tid not in target_tenant_ids:
            target_tenant_ids.append(tid)
    if not target_tenant_ids:
        return jsonify({'success': False, 'error': 'Select at least one target DB'}, 400)
    source_tenant_id = (data.get('source_tenant_id') or 'HO').strip() or 'HO'
    src_key = source_tenant_id.strip().upper()
    target_tenant_ids = [t for t in target_tenant_ids if str(t).strip().upper() != src_key]
    if not target_tenant_ids:
        return jsonify({'success': False, 'error': 'Select at least one target DB (cannot equal source).'}, 400)
    raw_codes = data.get('item_codes') or []
    if isinstance(raw_codes, str):
        raw_codes = [x.strip() for x in raw_codes.split(',') if x.strip()]
    source_loc = data.get('source_location_code')
    if source_loc in (None, '', 0, '0'):
        source_loc = _get_ho_location_code()
    try:
        total_inserted = 0
        total_updated = 0
        per_db = []
        for target_tenant_id in target_tenant_ids:
            result = remap_itemmaster_to_tenant(item_codes=raw_codes, target_tenant_id=target_tenant_id, source_location_code=source_loc, source_tenant_id=source_tenant_id)
            total_inserted += int(result.get('inserted') or 0)
            total_updated += int(result.get('updated') or 0)
            per_db.append({'tenant_id': target_tenant_id, 'inserted': int(result.get('inserted') or 0), 'updated': int(result.get('updated') or 0), 'missing_codes': result.get('missing_codes') or []})
        codes_norm: List[int] = []
        for c in raw_codes:
            try:
                codes_norm.append(int(c))
            except (TypeError, ValueError):
                continue
        _central_activity_log_safe(username=str(session.get('user') or ''), action='REMAP', summary=f'REMAP src={source_tenant_id} loc={source_loc} items={len(codes_norm)} dbs={len(target_tenant_ids)} ins={total_inserted} upd={total_updated}'[:500], detail={'source_tenant_id': source_tenant_id, 'source_location_code': source_loc, 'target_tenant_ids': target_tenant_ids, 'item_codes': codes_norm[:800], 'per_target': per_db, 'totals': {'inserted': total_inserted, 'updated': total_updated}})
        return jsonify({'success': True, 'message': f'Remap completed for {len(target_tenant_ids)} DB(s). Inserted: {total_inserted}, Updated: {total_updated}.', 'result': {'inserted': total_inserted, 'updated': total_updated, 'targets': per_db}})
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}, 400)
    except Exception as exc:
        return jsonify({'success': False, 'error': f'Remap failed: {exc}'}, 500)

@bp.route('/ho/itemmaster-central/delete-item', methods=['POST'])
def itemmaster_central_delete_item():
    """Remove item from each tenant DB; per DB: alternates + ITEMMASTER (+ ITEMDELETED on HO only) in one commit."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    data = request.get_json(silent=True) or {}
    password = str(data.get('password') or '').strip()
    if password != '123':
        return jsonify({'success': False, 'error': 'Invalid delete password'}, 403)
    item_code = _safe_int(data.get('item_code'), 0)
    if item_code <= 0:
        return jsonify({'success': False, 'error': 'Invalid item code'}, 400)
    ho_tenant_id = 'HO'
    user_name = str(session.get('user') or '')[:100]
    try:
        tenant_rows = _safe_rows_auth("SELECT tenant_id, locationcode FROM tenant_databases WHERE tenant_id IS NOT NULL AND NVL(active_flag,'Y')='Y'", {}) or []
        tenant_loc_map = {}
        for row in tenant_rows:
            tid = str(row.get('tenant_id') or '').strip()
            if not tid:
                continue
            try:
                tenant_loc_map[tid] = int(row.get('locationcode') or 1)
            except (TypeError, ValueError):
                tenant_loc_map[tid] = 1
        if ho_tenant_id not in tenant_loc_map:
            return jsonify({'success': False, 'error': 'HO tenant is not configured'}, 400)

        def _delete_item_in_tenant(tenant_id: str, tenant_loc: int, code: int, *, item_deleted_audit_user: Optional[str] = None):
            """Delete ITEMMASTER row (and ITEMALTERNATEUOMMAP when present) in one transaction.

            When ``item_deleted_audit_user`` is set, append ITEMDELETED audit row on the same connection before commit (HO only).
            """
            with _get_tenant_connection(tenant_id) as conn:
                try:
                    with conn.cursor() as cur:
                        cur.execute("SELECT column_name FROM user_tab_columns WHERE table_name = 'ITEMMASTER'")
                        cols = {str(r[0]).upper() for r in cur.fetchall() or []}
                        if 'ITEMCODE' not in cols:
                            conn.rollback()
                            return {'exists': False, 'deleted': 0, 'item_name': ''}
                        has_loc = 'LOCATIONCODE' in cols
                        has_name = 'ITEMNAME' in cols
                        item_name_expr = 'ITEMNAME' if has_name else "''"
                        if has_loc:
                            cur.execute(f'SELECT {item_name_expr} FROM ITEMMASTER WHERE LOCATIONCODE = :loc AND ITEMCODE = :icode', {'loc': tenant_loc, 'icode': code})
                        else:
                            cur.execute(f'SELECT {item_name_expr} FROM ITEMMASTER WHERE ITEMCODE = :icode', {'icode': code})
                        row = cur.fetchone()
                        if not row:
                            conn.rollback()
                            return {'exists': False, 'deleted': 0, 'item_name': ''}
                        item_name = str((row[0] if row else '') or '')[:200]
                        cur.execute("SELECT COUNT(*) FROM user_tables WHERE table_name = 'ITEMALTERNATEUOMMAP'")
                        has_alt = int((cur.fetchone() or [0])[0] or 0) > 0
                        if has_alt:
                            if has_loc:
                                cur.execute('DELETE FROM ITEMALTERNATEUOMMAP WHERE LOCATIONCODE = :loc AND ITEMCODE = :icode', {'loc': tenant_loc, 'icode': code})
                            else:
                                cur.execute('DELETE FROM ITEMALTERNATEUOMMAP WHERE ITEMCODE = :icode', {'icode': code})
                        if has_loc:
                            cur.execute('DELETE FROM ITEMMASTER WHERE LOCATIONCODE = :loc AND ITEMCODE = :icode', {'loc': tenant_loc, 'icode': code})
                        else:
                            cur.execute('DELETE FROM ITEMMASTER WHERE ITEMCODE = :icode', {'icode': code})
                        deleted_rows = int(cur.rowcount or 0)
                        if deleted_rows <= 0:
                            conn.rollback()
                            return {'exists': True, 'deleted': 0, 'item_name': item_name}
                        if item_deleted_audit_user:
                            cur.execute('\n                                INSERT INTO ITEMDELETED (ITEMCODE, ITEMNAME, DELETEDUSER, DELETEDDATE)\n                                VALUES (:icode, :iname, :u, SYSDATE)\n                                ', {'icode': code, 'iname': item_name, 'u': item_deleted_audit_user})
                    conn.commit()
                    return {'exists': True, 'deleted': 1, 'item_name': item_name}
                except Exception:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    raise
        _ensure_itemdeleted_table(ho_tenant_id)
        ho_loc = tenant_loc_map[ho_tenant_id]
        ho_result = _delete_item_in_tenant(ho_tenant_id, ho_loc, item_code, item_deleted_audit_user=user_name)
        if not ho_result.get('exists'):
            return jsonify({'success': False, 'error': 'Item not found in HO'}, 404)
        if int(ho_result.get('deleted') or 0) <= 0:
            return jsonify({'success': False, 'error': 'Delete failed in HO'}, 500)
        item_name = str(ho_result.get('item_name') or '')[:200]
        deleted_dbs = [ho_tenant_id]
        failed_dbs = []
        for tenant_id, tenant_loc in tenant_loc_map.items():
            if tenant_id == ho_tenant_id:
                continue
            try:
                result = _delete_item_in_tenant(tenant_id, tenant_loc, item_code)
                if int(result.get('deleted') or 0) > 0:
                    deleted_dbs.append(tenant_id)
            except Exception:
                failed_dbs.append(tenant_id)
        if failed_dbs:
            return jsonify({'success': False, 'error': f"Deleted from {len(deleted_dbs)} DB(s), but failed in: {', '.join(failed_dbs)}", 'deleted_dbs': deleted_dbs, 'failed_dbs': failed_dbs}, 500)
        _central_activity_log_safe(username=user_name, action='DELETE', summary=f'DELETE item={item_code} from {len(deleted_dbs)} DB(s)', detail={'item_code': item_code, 'item_name': item_name, 'deleted_dbs': deleted_dbs})
        return jsonify({'success': True, 'message': f'Item {item_code} deleted from {len(deleted_dbs)} DB(s).', 'deleted_dbs': deleted_dbs})
    except Exception as exc:
        return jsonify({'success': False, 'error': f'Delete failed: {exc}'}, 500)

@bp.route('/ho/itemmaster-central/save-item', methods=['POST'])
def itemmaster_central_save_item():
    """Create or update HO item + alternates, then HO-only follow-up in one DB transaction.

    Phases: (1) ``save_itemmaster_with_alternate_uoms_for_tenant`` — transactional ITEMMASTER + ITEMALTERNATEUOMMAP on HO.
    (2) Single HO connection: tenant-target flag columns on ITEMMASTER, optional TEMPITEMCODE + ITEMMASTERTEMP approval.
    (3) ``remap_itemmaster_to_tenant`` per selected branch — one transaction per target DB (cross-DB atomicity not possible).
    """
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    try:
        form = request.form
        temp_item_code_raw = (form.get('temp_item_code') or '').strip()
        save_mode = (form.get('save_mode') or '').strip().lower()
        target_tenant_ids = []
        for t in form.getlist('target_tenant_ids'):
            tid = str(t or '').strip()
            if tid and tid not in target_tenant_ids:
                target_tenant_ids.append(tid)
        single_target = (form.get('target_tenant_id') or '').strip()
        if single_target and single_target not in target_tenant_ids:
            target_tenant_ids.append(single_target)
        existing_target_tenant_ids = []
        for t in str(form.get('existing_target_tenant_ids') or '').split(','):
            tid = str(t or '').strip()
            if tid and tid not in existing_target_tenant_ids:
                existing_target_tenant_ids.append(tid)
        ho_tenant_id = 'HO'
        ho_loc = _get_ho_location_code()
        rows = _safe_rows_auth('SELECT tenant_id, locationcode FROM tenant_databases', {})
        by_tid = {str(r.get('tenant_id') or ''): r for r in rows or []}
        if ho_tenant_id not in by_tid:
            return jsonify({'success': False, 'error': 'HO tenant is not configured'}, 400)
        missing_tenants = [t for t in target_tenant_ids if t not in by_tid]
        if missing_tenants:
            return jsonify({'success': False, 'error': f"Target tenant not found: {', '.join(missing_tenants)}"}, 400)
        allowed_target_ids = {str(t.get('tenant_id') or '').strip() for t in _target_dbs_for_current_user(exclude_tenant_id=ho_tenant_id) if str(t.get('tenant_id') or '').strip()}
        forbidden_tenants = [t for t in target_tenant_ids if t not in allowed_target_ids]
        if forbidden_tenants:
            return jsonify({'success': False, 'error': f"Target tenant not assigned to user: {', '.join(forbidden_tenants)}"}, 403)
        is_new = form.get('is_new', 'true').lower() == 'true'
        is_update_mode = not is_new and save_mode == 'update'
        if is_new and (not target_tenant_ids):
            return jsonify({'success': False, 'error': 'Select at least one target DB'}, 400)
        if is_update_mode:
            existing_set = {str(t or '').strip() for t in existing_target_tenant_ids if str(t or '').strip()}
            invalid_for_update = [t for t in target_tenant_ids if t not in existing_set]
            if invalid_for_update:
                return jsonify({'success': False, 'error': 'For new DB mapping, use Remap. Update can sync only already fetched DBs.'}, 400)
        item_code_raw = (form.get('item_code') or '').strip()
        if is_new:
            if not item_code_raw:
                item_code_raw = str(get_next_item_code_for_tenant(ho_tenant_id, ho_loc))
            else:
                try:
                    if get_item_by_code_for_tenant(ho_tenant_id, int(item_code_raw), ho_loc):
                        item_code_raw = str(get_next_item_code_for_tenant(ho_tenant_id, ho_loc))
                except Exception:
                    item_code_raw = str(get_next_item_code_for_tenant(ho_tenant_id, ho_loc))
        elif not item_code_raw:
            return jsonify({'success': False, 'error': 'Item code is required'}, 400)
        manufacturer_id = (form.get('manufacturer_id') or '').strip() or str(item_code_raw)
        item_data = {'location_code': ho_loc, 'item_code': item_code_raw, 'manufacturer_id': manufacturer_id, 'created_by': session.get('user') or '', 'item_name': form.get('item_name'), 'main_category': form.get('main_category'), 'department_code': form.get('department_code'), 'category_code': form.get('category_code'), 'brand_code': form.get('brand_code'), 'size_code': form.get('size_code'), 'color_code': form.get('color_code'), 'base_uom': form.get('base_uom'), 'sup_code': form.get('sup_code'), 'cost_price': form.get('cost_price'), 'retail_price': form.get('retail_price'), 'wholesale_price': form.get('wholesale_price'), 'third_price': form.get('third_price'), 'branch_price': form.get('branch_price'), 'maximum_level': form.get('maximum_level'), 'reorder_level': form.get('reorder_level'), 'company_code': form.get('company_code'), 'item_name_ara': form.get('item_name_ara'), 'description': form.get('description'), 'own_product': 'Y' if str(form.get('own_product') or '').strip().upper() in ('Y', 'ON', '1', 'TRUE') else 'N', 'vat_percent': form.get('vat_percent'), 'discount_flag': 'Y' if form.get('discount_flag') else 'N', 'property_code': form.get('property_code'), 'origin_code': form.get('origin_code'), 'quantity_limit': form.get('quantity_limit'), 'packing': form.get('packing'), 'ministry_factor': form.get('ministry_factor'), 'ministry_unit': form.get('ministry_unit'), 'rebate': form.get('rebate'), 'sales_account': form.get('sales_account'), 'purchase_account': form.get('purchase_account'), 'inventory_account': form.get('inventory_account'), 'cogs_account': form.get('cogs_account')}
        user_lc = str(session.get('user') or '').strip().lower()
        if user_lc != 'admin':
            try:
                _chart_accounts_acct = get_all_chart_of_accounts()
            except Exception:
                _chart_accounts_acct = []
            _acct_defaults_locked = _grn_new_item_default_account_fields(_chart_accounts_acct)
            item_data['sales_account'] = str(_safe_num(_acct_defaults_locked.get('sales_code'), 4100))
            item_data['purchase_account'] = str(_safe_num(_acct_defaults_locked.get('purchase_code'), 5001))
            item_data['inventory_account'] = str(_safe_num(_acct_defaults_locked.get('inventory_code'), 1300))
            item_data['cogs_account'] = str(_safe_num(_acct_defaults_locked.get('cogs_code'), 5100))
        old_row_for_log: Optional[Dict[str, Any]] = None
        alts_before_log: List[Dict[str, Any]] = []
        if not is_new:
            try:
                _icode_log = int(item_code_raw)
                old_row_for_log = get_item_by_code_for_tenant(ho_tenant_id, _icode_log, ho_loc)
                alts_before_log = list(get_item_alternate_uoms_for_tenant(ho_tenant_id, _icode_log, ho_loc) or [])
            except Exception:
                old_row_for_log = None
                alts_before_log = []
        item_code_int = int(item_code_raw)

        def _num(v):
            try:
                return float(v) if v not in (None, '') else 0
            except (ValueError, TypeError):
                return 0
        temp_item_code_prefix = str(_safe_int(temp_item_code_raw, 0)) if temp_item_code_raw else ''

        def _remap_temp_variant_barcode(raw_barcode: str) -> str:
            barcode = str(raw_barcode or '').strip()
            if not (barcode and temp_item_code_prefix):
                return barcode
            m = re.match('^\\s*(\\d+)\\s*[-]?\\s*[lL]\\s*(\\d+)\\s*$', barcode)
            if m:
                src_code = str(_safe_int(m.group(1), 0))
                suffix = str(_safe_int(m.group(2), 0))
                if src_code == temp_item_code_prefix and suffix and (suffix != '0'):
                    return f'{item_code_int}L{suffix}'
            upper_barcode = barcode.upper().replace(' ', '')
            upper_prefix = f'{temp_item_code_prefix}L'
            if upper_barcode.startswith(upper_prefix):
                suffix = upper_barcode[len(upper_prefix):]
                if suffix.isdigit():
                    return f'{item_code_int}L{int(suffix)}'
            return barcode
        existing_alt_rows = get_item_alternate_uoms_for_tenant(ho_tenant_id, item_code_int, ho_loc) or []
        max_alt_suffix = 0
        alt_prefix = f'{item_code_int}L'
        for row in existing_alt_rows:
            raw_alt = str(row.get('manufacturerid') or row.get('manufacturer_id') or '').strip()
            if not raw_alt.startswith(alt_prefix):
                continue
            suffix = raw_alt[len(alt_prefix):]
            try:
                max_alt_suffix = max(max_alt_suffix, int(suffix))
            except (ValueError, TypeError):
                continue

        def _next_alt_barcode() -> str:
            nonlocal max_alt_suffix
            max_alt_suffix += 1
            return f'{item_code_int}L{max_alt_suffix}'
        alternate_payloads: List[Dict[str, Any]] = []
        variant_json_raw = (form.get('alternate_uoms_json') or '').strip()
        variant_rows = []
        if variant_json_raw:
            try:
                parsed = json.loads(variant_json_raw)
                if isinstance(parsed, list):
                    variant_rows = parsed
            except Exception:
                variant_rows = []
        if variant_rows:
            for vr in variant_rows:
                if not isinstance(vr, dict):
                    continue
                alternate_uom_code = str(vr.get('alternate_uom_code') or '').strip()
                conversion_factor_raw = str(vr.get('conversion_factor') or '').strip()
                if not alternate_uom_code or not conversion_factor_raw:
                    continue
                try:
                    conversion_factor = float(conversion_factor_raw)
                except (ValueError, TypeError):
                    conversion_factor = 0
                try:
                    master_cost = float(item_data.get('cost_price') or 0)
                except (ValueError, TypeError):
                    master_cost = 0
                alternate_cost = round(conversion_factor * master_cost, 3)
                alternate_barcode = str(vr.get('manufacturer_id') or '').strip()
                alternate_barcode = _remap_temp_variant_barcode(alternate_barcode)
                if not alternate_barcode:
                    alternate_barcode = _next_alt_barcode()
                alt_row = {'location_code': ho_loc, 'item_code': item_code_int, 'slno': str(vr.get('slno') or '').strip(), 'alternate_uom_code': alternate_uom_code, 'manufacturer_id': alternate_barcode, 'base_uom': item_data.get('base_uom') or '', 'conversion_factor': conversion_factor, 'cost_price': alternate_cost, 'wholesale_price': _num(vr.get('wholesale_price')), 'retail_price': _num(vr.get('retail_price')), 'third_price': _num(vr.get('third_price')), 'branch_price': _num(vr.get('branch_price'))}
                if vr.get('mirror_itemmaster'):
                    alt_row['mirror_itemmaster'] = True
                    alt_row['item_manufacturer_id'] = str(item_data.get('manufacturer_id') or manufacturer_id or item_code_int).strip()
                alternate_payloads.append(alt_row)
            if variant_rows and len(alternate_payloads) == 0:
                return jsonify({'success': False, 'error': 'Variant list has invalid rows. Please check Alternate UOM and Conversion Factor.'}, 400)
        else:
            alternate_uom_code = (form.get('alternate_uom_code') or '').strip()
            conversion_factor_raw = (form.get('alternate_conversion_factor') or '').strip()
            if alternate_uom_code and conversion_factor_raw:
                try:
                    conversion_factor = float(conversion_factor_raw)
                except (ValueError, TypeError):
                    conversion_factor = 0
                try:
                    master_cost = float(item_data.get('cost_price') or 0)
                except (ValueError, TypeError):
                    master_cost = 0
                alternate_cost = round(conversion_factor * master_cost, 3)
                alternate_barcode = (form.get('alternate_barcode') or '').strip()
                alternate_barcode = _remap_temp_variant_barcode(alternate_barcode)
                if not alternate_barcode:
                    alternate_barcode = _next_alt_barcode()
                alternate_payloads.append({'location_code': ho_loc, 'item_code': item_code_int, 'slno': (form.get('alternate_slno') or '').strip(), 'alternate_uom_code': alternate_uom_code, 'manufacturer_id': alternate_barcode, 'base_uom': item_data.get('base_uom') or '', 'conversion_factor': conversion_factor, 'cost_price': alternate_cost, 'wholesale_price': _num(form.get('alternate_wholesale_price')), 'retail_price': _num(form.get('alternate_retail_price')), 'third_price': _num(form.get('alternate_third_price')), 'branch_price': _num(form.get('alternate_branch_price'))})
        _, txn_err = save_itemmaster_with_alternate_uoms_for_tenant(item_data, is_new, alternate_payloads, ho_tenant_id)
        if txn_err:
            return jsonify({'success': False, 'error': txn_err}, 400)
        existing_image = ''
        if old_row_for_log:
            existing_image = str(
                old_row_for_log.get('image_path')
                or old_row_for_log.get('IMAGE_PATH')
                or ''
            ).strip()
        try:
            from addons.itemmaster.controllers.routes import apply_item_image_from_request

            img_err = apply_item_image_from_request(
                item_code=item_code_int,
                location_code=ho_loc,
                existing_path=existing_image,
                tenant_id=ho_tenant_id,
            )
            if img_err:
                return jsonify({'success': False, 'error': img_err}, 400)
        except Exception as img_exc:
            return jsonify({'success': False, 'error': f'Item image: {img_exc}'}, 400)
        try:
            if temp_item_code_raw:
                _ensure_itemmaster_tempitemcode_column(ho_tenant_id)
            tenant_codes = [str(t or '').strip().upper() for t in by_tid.keys() if str(t or '').strip()]
            selected_codes = {str(t or '').strip().upper() for t in target_tenant_ids if str(t or '').strip()}
            with _get_tenant_connection(ho_tenant_id) as conn:
                try:
                    with conn.cursor() as cur:
                        cur.execute("SELECT column_name FROM user_tab_columns WHERE table_name = 'ITEMMASTER'")
                        item_cols = {str(r[0]).upper() for r in cur.fetchall() or []}
                        flag_cols = [c for c in tenant_codes if c in item_cols]
                        for col in flag_cols:
                            cur.execute(f'\n                            UPDATE ITEMMASTER\n                            SET {col} = :v\n                            WHERE LOCATIONCODE = :loc\n                              AND ITEMCODE = :icode\n                            ', {'v': 'Y' if col in selected_codes else 'N', 'loc': ho_loc, 'icode': item_code_int})
                        if temp_item_code_raw:
                            cur.execute('\n                        UPDATE ITEMMASTER\n                        SET TEMPITEMCODE = :temp_item_code\n                        WHERE LOCATIONCODE = :location_code\n                          AND ITEMCODE = :item_code\n                        ', {'temp_item_code': _safe_int(temp_item_code_raw, 0), 'location_code': ho_loc, 'item_code': item_code_int})
                            cur.execute("\n                        UPDATE ITEMMASTERTEMP\n                        SET STATUS = 'APPROVED',\n                            UPDATEDBY = :u,\n                            UPDATEDDATE = SYSDATE\n                        WHERE ITEMCODE = :icode\n                        ", {'u': (session.get('user') or '')[:100], 'icode': _safe_int(temp_item_code_raw, 0)})
                    conn.commit()
                except Exception:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    raise
        except Exception:
            pass
        sync_rows = []
        total_inserted = 0
        total_updated = 0
        total_alt_inserted = 0
        total_alt_updated = 0
        sync_target_tenant_ids = list(target_tenant_ids)
        if is_update_mode:
            existing_set = {str(t or '').strip() for t in existing_target_tenant_ids if str(t or '').strip()}
            sync_target_tenant_ids = [t for t in target_tenant_ids if t in existing_set]
        sync_target_tenant_ids = [t for t in sync_target_tenant_ids if str(t or '').strip().upper() != ho_tenant_id.upper()]
        for target_tenant_id in sync_target_tenant_ids:
            result = remap_itemmaster_to_tenant(item_codes=[item_code_int], target_tenant_id=target_tenant_id, source_location_code=ho_loc, source_tenant_id=ho_tenant_id, itemmaster_update_only=is_update_mode)
            ins = int(result.get('inserted') or 0)
            upd = int(result.get('updated') or 0)
            total_inserted += ins
            total_updated += upd
            ains = int(result.get('alt_inserted') or 0)
            aupd = int(result.get('alt_updated') or 0)
            total_alt_inserted += ains
            total_alt_updated += aupd
            sync_rows.append({'tenant_id': target_tenant_id, 'inserted': ins, 'updated': upd, 'alt_inserted': ains, 'alt_updated': aupd})
        new_row_for_log: Optional[Dict[str, Any]] = None
        alts_after_log: List[Dict[str, Any]] = []
        try:
            new_row_for_log = get_item_by_code_for_tenant(ho_tenant_id, item_code_int, ho_loc)
            alts_after_log = list(get_item_alternate_uoms_for_tenant(ho_tenant_id, item_code_int, ho_loc) or [])
        except Exception:
            pass
        before_snap = _central_activity_item_snapshot(old_row_for_log)
        after_snap = _central_activity_item_snapshot(new_row_for_log)
        field_changes = _central_activity_diff_snapshots(before_snap, after_snap)
        act_label = 'CREATE' if is_new else 'UPDATE'
        _central_activity_log_safe(username=str(session.get('user') or ''), action=act_label, summary=f'{act_label} item={item_code_int} HO loc={ho_loc} branch_sync={len(sync_target_tenant_ids)} ins={total_inserted} upd={total_updated} alt_ins={total_alt_inserted} alt_upd={total_alt_updated}'[:500], detail={'item_code': item_code_int, 'ho_location_code': ho_loc, 'mode': act_label, 'save_mode': save_mode or '', 'target_tenant_selection': target_tenant_ids, 'branch_sync_targets': sync_target_tenant_ids, 'sync_per_tenant': sync_rows, 'sync_totals': {'inserted': total_inserted, 'updated': total_updated, 'alt_inserted': total_alt_inserted, 'alt_updated': total_alt_updated}, 'from_item_request': bool(temp_item_code_raw), 'temp_item_code': temp_item_code_raw or None, 'itemmaster_field_changes': field_changes, 'alternate_uoms_before': alts_before_log[:80], 'alternate_uoms_after': alts_after_log[:80]})
        return jsonify({'success': True, 'item_code': item_code_int, 'from_request': bool(temp_item_code_raw), 'redirect_url': url_for('ho.item_request', tab='pending') if temp_item_code_raw else url_for('ho.itemmaster_central'), 'message': f'Item saved in HO and synced to {len(sync_target_tenant_ids)} DB(s). Inserted: {total_inserted}, Updated: {total_updated}, Alt Inserted: {total_alt_inserted}, Alt Updated: {total_alt_updated}.', 'targets': sync_rows})
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}, 400)
    except Exception as exc:
        return jsonify({'success': False, 'error': f'Save failed: {exc}'}, 500)

@bp.route('/ho/itemmaster-central/itemmaster')
def itemmaster_central_form():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    ho_tenant_id = 'HO'
    ho_loc = _get_ho_location_code()
    session_location_code = session.get('location_code') if session.get('location_code') is not None else ho_loc
    brands = get_categories('B')
    sizes = get_categories('Z')
    colors = get_categories('L')
    main_categories = get_categories('M')
    suppliers = get_suppliers()
    units = get_units()
    item_properties = get_item_properties()
    item_origins = get_item_origins()
    try:
        chart_accounts = get_all_chart_of_accounts()
    except Exception:
        chart_accounts = []
    grn_new_item_default_accounts = _grn_new_item_default_account_fields(chart_accounts)
    store_popup_rows = _get_tbllocation_store_rows()
    item_code = (request.args.get('item_code') or '').strip()
    manufacturer_id = (request.args.get('manufacturer_id') or '').strip()
    temp_item_code = (request.args.get('temp_item_code') or '').strip()
    selected_target_tenants = [str(t or '').strip() for t in request.args.getlist('target_tenant_ids') if str(t or '').strip()]
    legacy_single = (request.args.get('target_tenant_id') or '').strip()
    if legacy_single and legacy_single not in selected_target_tenants:
        selected_target_tenants.append(legacy_single)
    _auto_select_first = temp_item_code and (not selected_target_tenants)
    item_data = None
    from_temp_request = False
    if item_code:
        try:
            item_data = get_item_by_code_for_tenant(ho_tenant_id, int(item_code), ho_loc)
        except Exception:
            item_data = None
    elif manufacturer_id:
        item_data = get_item_by_manufacturer_id_for_tenant(ho_tenant_id, manufacturer_id, ho_loc)
    elif temp_item_code:
        temp_row = _get_item_request_temp_row_by_item_code(ho_tenant_id, _safe_int(temp_item_code, 0))
        if temp_row:
            next_code = get_next_item_code_for_tenant(ho_tenant_id, ho_loc)
            temp_row['itemcode'] = next_code
            temp_row['tempitemcode'] = _safe_int(temp_item_code, 0)
            temp_row['discountflag'] = 'N'
            next_code_str = str(_safe_int(next_code, 0))
            current_barcode = str(temp_row.get('manufacturerid') or temp_row.get('manufacturer_id') or '').strip()
            if not current_barcode and next_code_str:
                temp_row['manufacturerid'] = next_code_str
                temp_row['manufacturer_id'] = next_code_str
            temp_row['sales_account'] = _safe_int(temp_row.get('salesaccount'), 4100)
            temp_row['purchase_account'] = _safe_int(temp_row.get('purchaseaccount'), 5001)
            temp_row['inventory_account'] = _safe_int(temp_row.get('inventoryaccount'), 1300)
            temp_row['cogs_account'] = _safe_int(temp_row.get('cogsaccount'), 5100)
            for _pk in ('costprice', 'retailprice', 'wholesaleprice', 'thirdprice', 'branchprice'):
                _pv = temp_row.get(_pk)
                if _pv is None or _pv == '':
                    continue
                try:
                    temp_row[_pk] = float(_pv)
                except (TypeError, ValueError):
                    pass
            item_data = temp_row
            from_temp_request = True

    def _map_temp_alt_barcode_for_prefill(barcode_value: str, temp_code: str, new_code: str) -> str:
        barcode = str(barcode_value or '').strip()
        tcode = str(temp_code or '').strip()
        ncode = str(new_code or '').strip()
        if not (barcode and tcode and ncode):
            return barcode
        if barcode == tcode:
            return ncode
        m = re.match('^\\s*(\\d+)\\s*[-]?\\s*[lL]\\s*(\\d+)\\s*$', barcode)
        if m and str(_safe_int(m.group(1), 0)) == tcode:
            seq = _safe_int(m.group(2), 0)
            if seq > 0:
                return f'{ncode}L{seq}'
        compact = barcode.replace(' ', '')
        if compact.upper().startswith((tcode + 'L').upper()):
            suffix = compact[len(tcode) + 1:]
            if suffix.isdigit():
                return f'{ncode}L{int(suffix)}'
        return barcode
    departments = get_categories('D')
    categories = get_categories('C')
    alternate_uom = None
    alternate_uoms = []
    store_inventory_rows = []
    if item_data and item_data.get('itemcode'):
        try:
            if from_temp_request and temp_item_code:
                req_src_row = _get_item_request_temp_row_by_item_code(ho_tenant_id, _safe_int(temp_item_code, 0))
                req_loc = req_src_row.get('locationcode') if req_src_row else None
                alternate_uoms = _get_item_request_alt_rows(ho_tenant_id, req_loc, _safe_int(temp_item_code, 0))
                mapped_uoms = []
                for alt in alternate_uoms or []:
                    row = dict(alt or {})
                    row['manufacturerid'] = _map_temp_alt_barcode_for_prefill(row.get('manufacturerid'), str(_safe_int(temp_item_code, 0)), str(_safe_int(item_data.get('itemcode'), 0)))
                    mapped_uoms.append(row)
                alternate_uoms = mapped_uoms
                alternate_uom = alternate_uoms[0] if alternate_uoms else None
            else:
                alternate_uom = get_item_alternate_uom_for_tenant(ho_tenant_id, ho_loc, int(item_data.get('itemcode')))
                alternate_uoms = get_item_alternate_uoms_for_tenant(ho_tenant_id, ho_loc, int(item_data.get('itemcode')))
        except Exception:
            alternate_uom = None
            alternate_uoms = []
        try:
            icode = int(item_data.get('itemcode'))
            store_inventory_rows = get_item_store_inventory_for_tenant(ho_tenant_id, ho_loc, icode, include_zero_stock=True)
            if not store_inventory_rows and (not is_multi_db_mode()):
                store_inventory_rows = get_item_store_inventory(ho_loc, icode)
        except Exception:
            store_inventory_rows = []
    target_dbs = _target_dbs_for_current_user(exclude_tenant_id=ho_tenant_id)
    if _auto_select_first and target_dbs:
        preferred_tenant = ''
        try:
            preferred_tenant = str((item_data or {}).get('branch') or '').strip().upper()
        except Exception:
            preferred_tenant = ''
        picked = ''
        if preferred_tenant:
            for t in target_dbs:
                tid = str((t or {}).get('tenant_id') or '').strip().upper()
                if tid == preferred_tenant:
                    picked = str((t or {}).get('tenant_id') or '').strip()
                    break
        if not picked:
            picked = str(target_dbs[0].get('tenant_id') or '').strip()
        selected_target_tenants = [picked] if picked else []
    target_loc_map = {}
    for t in target_dbs:
        try:
            target_loc_map[str(t.get('tenant_id') or '').strip()] = int(t.get('locationcode') or ho_loc)
        except (TypeError, ValueError):
            target_loc_map[str(t.get('tenant_id') or '').strip()] = ho_loc
    item_rawabicode = ''
    target_rawabi_checks = []
    existing_rawabi_tenants = []
    rawabi_detail_rows = []
    if item_data and item_data.get('itemcode'):
        try:
            item_rawabicode = get_item_rawabicode_for_tenant(ho_tenant_id, int(item_data.get('itemcode')), ho_loc)
        except Exception:
            item_rawabicode = ''
        if item_rawabicode:
            ho_detail = get_item_details_by_rawabicode_for_tenant(ho_tenant_id, item_rawabicode, ho_loc)
            if ho_detail:
                rawabi_detail_rows.append({'dbname': 'HO', 'rawabicode': ho_detail.get('rawabicode'), 'manufacturerid': ho_detail.get('manufacturerid'), 'itemname': ho_detail.get('itemname'), 'baseuom': ho_detail.get('baseuom'), 'costprice': ho_detail.get('costprice'), 'retailprice': ho_detail.get('retailprice'), 'currentstock': ho_detail.get('currentstock')})
        for t in target_dbs:
            tid_clean = str((t or {}).get('tenant_id') or '').strip()
            if not tid_clean:
                continue
            target_display = (t or {}).get('display_name') or tid_clean
            exists_info = check_item_exists_by_rawabicode_for_tenant(tenant_id=tid_clean, rawabicode=item_rawabicode, location_code=target_loc_map.get(tid_clean, ho_loc))
            exists_flag = bool(exists_info.get('exists'))
            if exists_flag:
                existing_rawabi_tenants.append(tid_clean)
                if tid_clean not in selected_target_tenants:
                    selected_target_tenants.append(tid_clean)
            target_rawabi_checks.append({'tenant_id': tid_clean, 'exists': exists_flag, 'itemcode': exists_info.get('itemcode'), 'itemname': exists_info.get('itemname')})
            if exists_flag:
                detail = get_item_details_by_rawabicode_for_tenant(tenant_id=tid_clean, rawabicode=item_rawabicode, location_code=target_loc_map.get(tid_clean, ho_loc))
                if detail:
                    rawabi_detail_rows.append({'dbname': target_display, 'rawabicode': detail.get('rawabicode'), 'manufacturerid': detail.get('manufacturerid'), 'itemname': detail.get('itemname'), 'baseuom': detail.get('baseuom'), 'costprice': detail.get('costprice'), 'retailprice': detail.get('retailprice'), 'currentstock': detail.get('currentstock')})
    return render_template('ho/itemmaster.html', categories=categories, brands=brands, sizes=sizes, colors=colors, main_categories=main_categories, departments=departments, suppliers=suppliers, units=units, item_properties=item_properties, item_origins=item_origins, item_data=item_data, alternate_uom=alternate_uom, alternate_uoms=alternate_uoms, store_inventory_rows=store_inventory_rows, location_code=session_location_code, chart_accounts=chart_accounts, grn_new_item_default_accounts=grn_new_item_default_accounts, store_popup_rows=store_popup_rows, ho_mode=True, target_dbs=target_dbs, itemmaster_save_url=url_for('ho.itemmaster_central_save_item'), itemmaster_view_url=url_for('ho.itemmaster_central_form'), itemmaster_next_code_url=url_for('ho.itemmaster_central_next_code'), itemmaster_list_url=url_for('ho.itemmaster_central'), hide_store_inventory_panel=from_temp_request, itemmaster_force_is_new=from_temp_request, temp_item_code=temp_item_code if from_temp_request else '', ho_source_location_code=ho_loc, selected_target_tenants=selected_target_tenants, item_rawabicode=item_rawabicode, target_rawabi_checks=target_rawabi_checks, existing_rawabi_tenants=existing_rawabi_tenants, rawabi_detail_rows=rawabi_detail_rows, itemmaster_from_item_request=from_temp_request)

@bp.route('/ho/itemmaster-central/itemmaster/next-code', methods=['GET'])
def itemmaster_central_next_code():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    try:
        next_code = get_next_item_code_for_tenant('HO', _get_ho_location_code())
        return jsonify({'success': True, 'item_code': next_code})
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}, 400)
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}, 500)

def _supplier_central_activity_safe(*, username: Optional[str], action: str, summary: str, detail: Optional[Dict[str, Any]]=None) -> None:
    try:
        append_master_activity(username=username, action=action, entity=_SUPPLIER_CENTRAL_ENTITY, summary=summary, detail=detail or {})
    except Exception:
        pass

def _supplier_central_redirect(supplier_code: Optional[int]=None):
    if supplier_code:
        return redirect(url_for('ho.supplier_central_form', supplier_code=supplier_code))
    return redirect(url_for('ho.supplier_central_form'))

def _supplier_central_form_data() -> Dict[str, Any]:
    form = request.form
    return {'suppliername': (form.get('suppliername') or '').strip(), 'suppliertype': (form.get('suppliertype') or '').strip(), 'address': (form.get('address') or '').strip(), 'telephone': (form.get('telephone') or '').strip(), 'fax': (form.get('fax') or '').strip(), 'mobile': (form.get('mobile') or '').strip(), 'emailid': (form.get('emailid') or '').strip(), 'contactperson': (form.get('contactperson') or '').strip(), 'supplierid': (form.get('supplierid') or '').strip(), 'payableaccount': _safe_num_or_none(form.get('payableaccount')), 'purchaseaccount': _safe_num_or_none(form.get('purchaseaccount')), 'vatinputaccount': _safe_num_or_none(form.get('vatinputaccount')), 'advanceaccount': _safe_num_or_none(form.get('advanceaccount')), 'flag': (form.get('flag') or 'Y').strip()[:1] or 'Y', 'supplierlocation': (form.get('supplierlocation') or '').strip(), 'supref': (form.get('supref') or '').strip(), 'suppliercr': (form.get('suppliercr') or '').strip(), 'creationflag': (form.get('creationflag') or 'B').strip()[:1] or 'B'}

@bp.route('/ho/supplier-central')
def supplier_central():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    ho_loc = _get_ho_location_code()
    search = (request.args.get('search') or '').strip()
    suppliers = get_supplier_list_from_tenant('HO', location_code=ho_loc, search=search if search else None, limit=500)
    return render_template('ho/ho_supplier_central.html', suppliers=suppliers, search=search, source_location_code=ho_loc)

@bp.route('/ho/supplier-central/supplier')
def supplier_central_form():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    ho_tenant_id = 'HO'
    ho_loc = _get_ho_location_code()
    supplier_code = _safe_int(request.args.get('supplier_code'), 0)
    supplier = None
    if supplier_code:
        supplier = get_supplier_by_code_for_tenant(ho_tenant_id, ho_loc, supplier_code)
        if not supplier:
            flash('Supplier not found.', 'error')
            return redirect(url_for('ho.supplier_central'))
    try:
        chart_accounts = get_all_chart_of_accounts()
    except Exception:
        chart_accounts = []
    try:
        default_accounts = ensure_default_party_accounts()
    except Exception:
        default_accounts = DEFAULT_PARTY_ACCOUNTS.copy()
    target_dbs = _target_dbs_for_current_user(exclude_tenant_id=ho_tenant_id)
    selected_target_tenants: List[str] = []
    if supplier and supplier_code:
        for t in target_dbs:
            tid = str(t.get('tenant_id') or '').strip()
            if not tid:
                continue
            target_loc = _safe_int(t.get('locationcode'), ho_loc)
            try:
                if supplier_exists_for_tenant(tid, target_loc, supplier_code):
                    selected_target_tenants.append(tid)
            except Exception:
                continue
    return render_template('ho/supplier_central_form.html', supplier=supplier, chart_accounts=chart_accounts, default_accounts=default_accounts, target_dbs=target_dbs, selected_target_tenants=selected_target_tenants, location_code=ho_loc, location_name='HO', next_supplier_code=supplier_code or get_next_supplier_code_for_tenant(ho_tenant_id, ho_loc), is_edit=bool(supplier))

@bp.route('/ho/supplier-central/save', methods=['POST'])
def supplier_central_save():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    submitted = (request.form.get('save_nonce') or '').strip()
    if not verify_consume_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY, submitted):
        flash('Duplicate or invalid submit. Reload the supplier form and try again.', 'error')
        return _supplier_central_redirect(_safe_int(request.form.get('suppliercode'), 0))
    ho_loc = _get_ho_location_code()
    is_new = str(request.form.get('is_new') or 'true').strip().lower() == 'true'
    supplier_code = _safe_int(request.form.get('suppliercode'), 0)
    if is_new or not supplier_code:
        supplier_code = get_next_supplier_code_for_tenant('HO', ho_loc)
    supplier_data = _supplier_central_form_data()
    if not supplier_data['suppliername']:
        flash('Supplier name is required.', 'error')
        return _supplier_central_redirect(None if is_new else supplier_code)
    for key, label in (('payableaccount', 'Payable Account'), ('purchaseaccount', 'Purchase Account'), ('vatinputaccount', 'Input VAT Account'), ('advanceaccount', 'Advance Account')):
        if not supplier_data.get(key):
            flash(f'{label} is required.', 'error')
            return _supplier_central_redirect(None if is_new else supplier_code)
    target_tenant_ids: List[str] = []
    for raw_tid in request.form.getlist('target_tenant_ids'):
        tid = str(raw_tid or '').strip()
        if tid and tid.upper() != 'HO' and (tid not in target_tenant_ids):
            target_tenant_ids.append(tid)
    if is_new and (not target_tenant_ids):
        flash('Select at least one target DB.', 'error')
        return _supplier_central_redirect()
    tenant_rows = _safe_rows_auth('SELECT tenant_id, locationcode FROM tenant_databases', {}) or []
    by_tenant = {str(r.get('tenant_id') or '').strip(): r for r in tenant_rows}
    missing_tenants = [tid for tid in target_tenant_ids if tid not in by_tenant]
    if missing_tenants:
        flash(f"Target tenant not found: {', '.join(missing_tenants)}", 'error')
        return _supplier_central_redirect(None if is_new else supplier_code)
    allowed_target_ids = {str(t.get('tenant_id') or '').strip() for t in _target_dbs_for_current_user(exclude_tenant_id='HO') if str(t.get('tenant_id') or '').strip()}
    forbidden_tenants = [tid for tid in target_tenant_ids if tid not in allowed_target_ids]
    if forbidden_tenants:
        flash(f"Target tenant not assigned to user: {', '.join(forbidden_tenants)}", 'error')
        return _supplier_central_redirect(None if is_new else supplier_code)
    sync_rows = []
    try:
        ho_result = save_supplier_in_tenant('HO', location_code=ho_loc, supplier_code=supplier_code, supplier_data=supplier_data)
        sync_rows.append({'tenant_id': 'HO', 'location_code': ho_loc, 'action': ho_result.get('action')})
        for tid in target_tenant_ids:
            target_loc = _safe_int((by_tenant.get(tid) or {}).get('locationcode'), ho_loc)
            result = save_supplier_in_tenant(tid, location_code=target_loc, supplier_code=supplier_code, supplier_data=supplier_data)
            sync_rows.append({'tenant_id': tid, 'location_code': target_loc, 'action': result.get('action')})
        flash(f'Supplier {supplier_code} saved to {len(sync_rows)} DB(s).', 'success')
        _supplier_central_activity_safe(username=str(session.get('user') or ''), action='CREATE' if is_new else 'UPDATE', summary=f"supplier_code={supplier_code}, name={supplier_data['suppliername'][:120]}, dbs={len(sync_rows)}", detail={'suppliercode': supplier_code, 'suppliername': supplier_data['suppliername'], 'targets': sync_rows})
        return redirect(url_for('ho.supplier_central_form', supplier_code=supplier_code))
    except Exception as exc:
        flash(f'Error saving supplier central: {exc}', 'error')
        return _supplier_central_redirect(None if is_new else supplier_code)

@bp.route('/ho/item-request')
def item_request():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    ho_tenant_id = 'HO'
    _ensure_item_request_temp_tables(ho_tenant_id)
    selected_tab = (request.args.get('tab') or 'pending').strip().lower()
    if selected_tab not in ('pending', 'approved', 'rejected'):
        selected_tab = 'pending'
    ir_branch_filter = _item_request_list_branch_filter()
    rows = _get_item_request_rows_by_status(ho_tenant_id, selected_tab, branch_filter=ir_branch_filter)
    counts = _get_item_request_status_counts(ho_tenant_id, branch_filter=ir_branch_filter)
    branch_info = _ho_get_all_branch_info()
    return render_template('ho/ho_item_request_list.html', selected_tab=selected_tab, rows=rows, counts=counts, branch_info=branch_info, ir_branch_scoped=ir_branch_filter is not None, ir_branch_scope_code=str(ir_branch_filter or '').strip(), ir_allow_convert_item=ir_branch_filter is None)

@bp.route('/ho/item-request/convert/<int:item_code>', methods=['POST'])
def item_request_convert(item_code: int):
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    ho_tenant_id = 'HO'
    _ensure_item_request_temp_tables(ho_tenant_id)
    if _item_request_list_branch_filter() is not None:
        return jsonify({'success': False, 'error': 'Convert Item is only available for headquarters users.'}, 403)
    temp_item_code = int(item_code)
    temp_row = _get_item_request_temp_row_by_item_code(ho_tenant_id, temp_item_code)
    if not temp_row:
        return jsonify({'success': False, 'error': 'Item request not found'}, 404)
    st = str(temp_row.get('status') or 'PENDING').strip().upper()
    if st != 'PENDING':
        return jsonify({'success': False, 'error': 'Only pending requests can be converted.'}, 400)
    return jsonify({'success': True, 'message': 'Request data loaded in Central Itemmaster page.', 'redirect_url': url_for('ho.itemmaster_central_form', temp_item_code=temp_item_code)})

@bp.route('/ho/item-request/reject/<int:item_code>', methods=['POST'])
def item_request_reject(item_code: int):
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    ho_tenant_id = 'HO'
    _ensure_item_request_temp_tables(ho_tenant_id)
    temp_item_code = int(item_code)
    payload = {}
    try:
        if request.is_json and request.json and isinstance(request.json, dict):
            payload = request.json
    except Exception:
        payload = {}
    reason = str(payload.get('reason') or request.form.get('reason') or '').strip()
    reason = reason[:500] if reason else ''
    temp_row = _get_item_request_temp_row_by_item_code(ho_tenant_id, temp_item_code)
    if not temp_row:
        return jsonify({'success': False, 'error': 'Item request not found'}, 404)
    if not _item_request_can_access_temp_row(temp_row):
        return jsonify({'success': False, 'error': 'Access denied.'}, 403)
    st = str(temp_row.get('status') or 'PENDING').strip().upper()
    if st != 'PENDING':
        return jsonify({'success': False, 'error': 'Only pending requests can be rejected.'}, 400)
    user = str(session.get('user') or '').strip()[:100]
    bf_reject = _item_request_list_branch_filter()
    try:
        with _get_tenant_connection(ho_tenant_id) as conn:
            with conn.cursor() as cur:
                branch_clause = ''
                rej_params: Dict[str, Any] = {'cmt': reason or None, 'u': user, 'icode': temp_item_code}
                if bf_reject is not None:
                    branch_clause = " AND UPPER(NVL(BRANCH,'')) = :brf"
                    rej_params['brf'] = str(bf_reject).strip().upper()
                cur.execute(f"\n                    UPDATE ITEMMASTERTEMP\n                    SET STATUS = 'REJECTED',\n                        REJECTCOMMENT = :cmt,\n                        UPDATEDBY = :u,\n                        UPDATEDDATE = SYSDATE\n                    WHERE ITEMCODE = :icode\n                      AND UPPER(NVL(STATUS, 'PENDING')) = 'PENDING'\n                      {branch_clause}\n                    ", rej_params)
                if int(cur.rowcount or 0) < 1:
                    return jsonify({'success': False, 'error': 'Reject failed (record may have changed).'}, 409)
            conn.commit()
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}, 500)
    return jsonify({'success': True, 'message': 'Item request rejected.'})

@bp.route('/ho/item-request/itemmaster')
def item_request_form():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    ho_tenant_id = 'HO'
    ho_loc = _get_ho_location_code()
    session_location_code = session.get('location_code') if session.get('location_code') is not None else ho_loc
    current_tenant_id = (session.get('tenant_id') or '').strip()
    ir_branch_name = _ho_get_branch_name_by_dbkey(ho_tenant_id, current_tenant_id)
    _ensure_item_request_temp_tables(ho_tenant_id)
    location_popup_rows = _get_request_location_rows(ho_tenant_id)
    default_location_row = None
    request_location_code = ''
    brands = get_categories('B')
    sizes = get_categories('Z')
    colors = get_categories('L')
    main_categories = get_categories('M')
    departments = get_categories('D')
    categories = get_categories('C')
    suppliers = get_suppliers()
    units = get_units()
    item_properties = get_item_properties()
    item_origins = get_item_origins()
    try:
        chart_accounts = get_all_chart_of_accounts()
    except Exception:
        chart_accounts = []
    grn_new_item_default_accounts = _grn_new_item_default_account_fields(chart_accounts)
    store_popup_rows = location_popup_rows
    item_code = (request.args.get('item_code') or '').strip()
    manufacturer_id = (request.args.get('manufacturer_id') or '').strip()
    item_data = _get_item_request_temp_row(tenant_id=ho_tenant_id, location_code=request_location_code, item_code=item_code, manufacturer_id=manufacturer_id)
    if item_data:
        saved_loc = str(item_data.get('locationcode') or '').strip()
        matched_loc_row = _get_request_location_row_by_code(ho_tenant_id, saved_loc) or _get_request_location_row_by_locationcode(ho_tenant_id, saved_loc)
        if matched_loc_row:
            item_data['locationcode'] = str(matched_loc_row.get('code') or '').strip().upper()
            if not str(item_data.get('branch') or '').strip():
                item_data['branch'] = str(matched_loc_row.get('dbkey') or '').strip().upper()
            request_location_code = item_data['locationcode']
            default_location_row = matched_loc_row
    if item_code and item_data and (not _item_request_can_access_temp_row(item_data)):
        flash('You do not have access to this item request.', 'error')
        return redirect(url_for('ho.item_request'))
    alternate_uoms = []
    alternate_uom = None
    if item_data and item_data.get('itemcode'):
        alt_loc = item_data.get('locationcode', request_location_code)
        alternate_uoms = _get_item_request_alt_rows(ho_tenant_id, alt_loc, _safe_int(item_data.get('itemcode'), 0))
        alternate_uom = alternate_uoms[0] if alternate_uoms else None
    return render_template('ho/itemmaster.html', categories=categories, brands=brands, sizes=sizes, colors=colors, main_categories=main_categories, departments=departments, suppliers=suppliers, units=units, item_properties=item_properties, item_origins=item_origins, item_data=item_data, alternate_uom=alternate_uom, alternate_uoms=alternate_uoms, store_inventory_rows=[], location_code=session_location_code, chart_accounts=chart_accounts, store_popup_rows=store_popup_rows, ho_mode=False, item_request_mode=True, item_request_default_dbocode=request_location_code, item_request_default_branch=str((default_location_row or {}).get('dbkey') or '').strip().upper(), ir_tenant_id=current_tenant_id, ir_branch_name=ir_branch_name, itemmaster_page_title='Item Request', itemmaster_save_url=url_for('ho.item_request_save_item'), itemmaster_view_url=url_for('ho.item_request_form'), itemmaster_next_code_url=url_for('ho.item_request_next_code'), itemmaster_list_url=url_for('ho.item_request', tab='pending'), grn_new_item_default_accounts=grn_new_item_default_accounts)

@bp.route('/ho/item-request/itemmaster/next-code', methods=['GET'])
def item_request_next_code():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    try:
        ho_tenant_id = 'HO'
        ho_loc = _get_ho_location_code()
        ho_dbcode, _ho_dbkey = _get_location_dbcode_and_dbkey(ho_tenant_id, ho_loc)
        next_code = _get_next_item_request_code_from_temp(ho_tenant_id, ho_dbcode, ho_loc)
        return jsonify({'success': True, 'item_code': next_code})
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}, 400)
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}, 500)

@bp.route('/ho/item-request/save-item', methods=['POST'])
def item_request_save_item():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    try:
        form = request.form
        ho_tenant_id = 'HO'
        ho_loc = _get_ho_location_code()
        _ensure_item_request_temp_tables(ho_tenant_id)
        session_tenant_id = (session.get('tenant_id') or '').strip().upper()
        selected_dbocode = str(form.get('dbocode') or '').strip()
        selected_loc_row = _get_request_location_row_by_code(ho_tenant_id, selected_dbocode) if selected_dbocode else None
        if not selected_loc_row and session_tenant_id:
            all_loc_rows = _get_request_location_rows(ho_tenant_id)
            for _r in all_loc_rows:
                if str(_r.get('dbkey') or '').strip().upper() == session_tenant_id:
                    selected_loc_row = _r
                    break
        if not selected_loc_row:
            all_loc_rows = _get_request_location_rows(ho_tenant_id)
            selected_loc_row = all_loc_rows[0] if all_loc_rows else None
        selected_dbocode = str((selected_loc_row or {}).get('code') or '').strip() or str(ho_loc)
        selected_branch_dbkey = session_tenant_id or str((selected_loc_row or {}).get('dbkey') or '').strip().upper()
        try:
            _chart_accounts_acct = get_all_chart_of_accounts()
        except Exception:
            _chart_accounts_acct = []
        _acct_defaults_locked = _grn_new_item_default_account_fields(_chart_accounts_acct)
        locked_sales_acct = _safe_num(_acct_defaults_locked.get('sales_code'), 4100)
        locked_purchase_acct = _safe_num(_acct_defaults_locked.get('purchase_code'), 5001)
        locked_inventory_acct = _safe_num(_acct_defaults_locked.get('inventory_code'), 1300)
        locked_cogs_acct = _safe_num(_acct_defaults_locked.get('cogs_code'), 5100)
        is_new = form.get('is_new', 'true').lower() == 'true'
        item_code_raw = (form.get('item_code') or '').strip()
        if is_new:
            if not item_code_raw:
                item_code_raw = str(_get_next_item_request_code_from_temp(ho_tenant_id, selected_dbocode, ho_loc))
            else:
                existing = _get_item_request_temp_row(ho_tenant_id, selected_dbocode, item_code=item_code_raw)
                if existing:
                    item_code_raw = str(_get_next_item_request_code_from_temp(ho_tenant_id, selected_dbocode, ho_loc))
        elif not item_code_raw:
            return jsonify({'success': False, 'error': 'Item code is required'}, 400)
        item_code_int = _safe_int(item_code_raw, 0)
        if item_code_int <= 0:
            return jsonify({'success': False, 'error': 'Invalid item code'}, 400)
        manufacturer_id = (form.get('manufacturer_id') or '').strip()
        rawabi_value = (form.get('rawabicode') or '').strip() or manufacturer_id
        created_by = (session.get('user') or '').strip()[:100]
        params = {'item_code': item_code_int, 'rawabicode': rawabi_value, 'manufacturer_id': manufacturer_id, 'item_name': str(form.get('item_name') or '').upper(), 'item_name_ara': form.get('item_name_ara') or '', 'description': form.get('description') or '', 'own_product': 'Y' if str(form.get('own_product') or '').strip().upper() in ('Y', 'ON', '1', 'TRUE') else 'N', 'category_code': _safe_num(form.get('category_code'), 0), 'brand_code': _safe_num(form.get('brand_code'), 0), 'size_code': _safe_num(form.get('size_code'), 0), 'color_code': _safe_num(form.get('color_code'), 0), 'base_uom': form.get('base_uom') or '', 'cost_price': _safe_num(form.get('cost_price'), 0), 'retail_price': _safe_num(form.get('retail_price'), 0), 'wholesale_price': _safe_num(form.get('wholesale_price'), 0), 'third_price': _safe_num(form.get('third_price'), 0), 'branch_price': _safe_num(form.get('branch_price'), 0), 'maximum_level': _safe_num(form.get('maximum_level'), 0), 'reorder_level': _safe_num(form.get('reorder_level'), 0), 'discount_flag': 'N', 'company_code': _safe_num_or_none(form.get('company_code')), 'sup_code': _safe_num(form.get('sup_code'), 0), 'department_code': _safe_num(form.get('department_code'), 0), 'main_category': _safe_num(form.get('main_category'), 0), 'rebate': _safe_num(form.get('rebate'), 0), 'property_code': _safe_num(form.get('property_code') or form.get('property'), 0), 'origin_code': _safe_num(form.get('origin_code') or form.get('origin'), 0), 'quantity_limit': _safe_num(form.get('quantity_limit'), 0), 'packing': form.get('packing') or '', 'ministry_factor': _safe_num(form.get('ministry_factor'), 0), 'ministry_unit': form.get('ministry_unit') or '', 'vat_percent': _safe_num(form.get('vat_percent'), 0), 'sales_account': locked_sales_acct, 'purchase_account': locked_purchase_acct, 'inventory_account': locked_inventory_acct, 'cogs_account': locked_cogs_acct, 'store': (form.get('store') or '').strip().upper()[:30], 'branch_dbkey': selected_branch_dbkey, 'status': 'PENDING', 'created_by': created_by, 'updated_by': created_by}
        variant_json_raw = (form.get('alternate_uoms_json') or '').strip()
        variant_rows: List[Any] = []
        if variant_json_raw:
            try:
                parsed = json.loads(variant_json_raw)
                if isinstance(parsed, list):
                    variant_rows = parsed
            except Exception:
                variant_rows = []
        if not variant_rows:
            fallback_uom = (form.get('alternate_uom_code') or '').strip()
            fallback_factor = (form.get('alternate_conversion_factor') or '').strip()
            if fallback_uom and fallback_factor:
                variant_rows = [{'slno': (form.get('alternate_slno') or '').strip(), 'manufacturer_id': (form.get('alternate_barcode') or '').strip(), 'alternate_uom_code': fallback_uom, 'conversion_factor': fallback_factor, 'cost_price': form.get('alternate_cost_price'), 'wholesale_price': form.get('alternate_wholesale_price'), 'retail_price': form.get('alternate_retail_price'), 'third_price': form.get('alternate_third_price'), 'branch_price': form.get('alternate_branch_price')}]
        valid_rows: List[Dict[str, Any]] = []
        for vr in variant_rows:
            if not isinstance(vr, dict):
                continue
            uom_code = str(vr.get('alternate_uom_code') or '').strip()
            factor_raw = str(vr.get('conversion_factor') or '').strip()
            if not uom_code or not factor_raw:
                continue
            valid_rows.append(vr)
        if variant_rows and (not valid_rows):
            return jsonify({'success': False, 'error': 'Variant list has invalid rows. Please check Alternate UOM and Conversion Factor.'}, 400)
        with _get_tenant_connection(ho_tenant_id) as conn:
            try:
                with conn.cursor() as cur:
                    loc_for_item_temp = _coerce_request_location_code(cur, 'ITEMMASTERTEMP', selected_dbocode, ho_loc)
                    loc_for_alt_temp = _coerce_request_location_code(cur, 'ITEMALTERNATEUOMMAPTEMP', selected_dbocode, ho_loc)
                    params['location_code'] = loc_for_item_temp
                    cur.execute("\n                    MERGE INTO ITEMMASTERTEMP t\n                    USING (\n                        SELECT :location_code AS locationcode, :item_code AS itemcode FROM dual\n                    ) s\n                    ON (t.LOCATIONCODE = s.locationcode AND t.ITEMCODE = s.itemcode)\n                    WHEN MATCHED THEN UPDATE SET\n                        RAWABICODE = :rawabicode,\n                        MANUFACTURERID = :manufacturer_id,\n                        ITEMNAME = :item_name,\n                        ITEMNAMEARA = :item_name_ara,\n                        DESCRIPTION = :description,\n                        OWNPRODUCT = :own_product,\n                        CATEGORYCODE = :category_code,\n                        BRANDCODE = :brand_code,\n                        SIZECODE = :size_code,\n                        COLORCODE = :color_code,\n                        BASEUOM = :base_uom,\n                        COSTPRICE = :cost_price,\n                        RETAILPRICE = :retail_price,\n                        WHOLESALEPRICE = :wholesale_price,\n                        THIRDPRICE = :third_price,\n                        BRANCHPRICE = :branch_price,\n                        MAXIMUMLEVEL = :maximum_level,\n                        REORDERLEVEL = :reorder_level,\n                        DISCOUNTFLAG = :discount_flag,\n                        COMPANYCODE = :company_code,\n                        SUPCODE = :sup_code,\n                        \n                        DEPARTMENTCODE = :department_code,\n                        MAINCATEGORY = :main_category,\n                        REBATE = :rebate,\n                        PROPERTY = :property_code,\n                        ORIGIN = :origin_code,\n                        QUANTITYLIMIT = :quantity_limit,\n                        PACKING = :packing,\n                        MINISTRYFACTOR = :ministry_factor,\n                        MINISTRYUNIT = :ministry_unit,\n                        VATPERCENT = :vat_percent,\n                        SALESACCOUNT = :sales_account,\n                        PURCHASEACCOUNT = :purchase_account,\n                        INVENTORYACCOUNT = :inventory_account,\n                        COGSACCOUNT = :cogs_account,\n                        STORE = :store,\n                        BRANCH = :branch_dbkey,\n                        STATUS = :status,\n                        UPDATEDBY = :updated_by,\n                        UPDATEDDATE = SYSDATE\n                    WHEN NOT MATCHED THEN INSERT (\n                        LOCATIONCODE, ITEMCODE, RAWABICODE, MANUFACTURERID, ITEMNAME, ITEMNAMEARA, DESCRIPTION, OWNPRODUCT,\n                        CATEGORYCODE, BRANDCODE, SIZECODE, COLORCODE, BASEUOM,\n                        COSTPRICE, RETAILPRICE, WHOLESALEPRICE, THIRDPRICE, BRANCHPRICE,\n                        MAXIMUMLEVEL, REORDERLEVEL, DISCOUNTFLAG, COMPANYCODE, SUPCODE,\n                        DEPARTMENTCODE, MAINCATEGORY, REBATE, PROPERTY, ORIGIN, QUANTITYLIMIT, PACKING,\n                        MINISTRYFACTOR, MINISTRYUNIT, VATPERCENT, SALESACCOUNT, PURCHASEACCOUNT, INVENTORYACCOUNT, COGSACCOUNT,\n                        STORE, BRANCH, STATUS, ITEMFLAG, CREATIONFLAG, CREATEDBY, CREATEDDATE, UPDATEDBY, UPDATEDDATE\n                    ) VALUES (\n                        :location_code, :item_code, :rawabicode, :manufacturer_id, :item_name, :item_name_ara, :description, :own_product,\n                        :category_code, :brand_code, :size_code, :color_code, :base_uom,\n                        :cost_price, :retail_price, :wholesale_price, :third_price, :branch_price,\n                        :maximum_level, :reorder_level, :discount_flag, :company_code, :sup_code,\n                        :department_code, :main_category, :rebate, :property_code, :origin_code, :quantity_limit, :packing,\n                        :ministry_factor, :ministry_unit, :vat_percent, :sales_account, :purchase_account, :inventory_account, :cogs_account,\n                        :store, :branch_dbkey, :status, 'Y', 'B', :created_by, SYSDATE, :updated_by, SYSDATE\n                    )\n                    ", params)
                    cur.execute('\n                    DELETE FROM ITEMALTERNATEUOMMAPTEMP\n                    WHERE LOCATIONCODE = :loc\n                      AND ITEMCODE = :icode\n                    ', {'loc': loc_for_alt_temp, 'icode': item_code_int})
                    for idx, vr in enumerate(valid_rows, start=1):
                        slno = _safe_int(vr.get('slno'), 0)
                        if slno <= 0:
                            slno = idx
                        alt_barcode = str(vr.get('manufacturer_id') or '').strip()
                        if not alt_barcode:
                            alt_barcode = f'{item_code_int}L{idx}'
                        cur.execute('\n                        INSERT INTO ITEMALTERNATEUOMMAPTEMP (\n                            LOCATIONCODE, SLNO, ITEMCODE, ALTERNATEUOMCODE, MANUFACTURERID,\n                            CONVERSIONFACTOR, COSTPRICE, WHOLESALEPRICE, RETAILPRICE, THIRDPRICE, BRANCHPRICE\n                        ) VALUES (\n                            :location_code, :slno, :item_code, :alternate_uom_code, :manufacturer_id,\n                            :conversion_factor, :cost_price, :wholesale_price, :retail_price, :third_price, :branch_price\n                        )\n                        ', {'location_code': loc_for_alt_temp, 'slno': int(slno), 'item_code': item_code_int, 'alternate_uom_code': str(vr.get('alternate_uom_code') or '').strip(), 'manufacturer_id': alt_barcode, 'conversion_factor': _safe_num(vr.get('conversion_factor'), 0), 'cost_price': _safe_num(vr.get('cost_price'), 0), 'wholesale_price': _safe_num(vr.get('wholesale_price'), 0), 'retail_price': _safe_num(vr.get('retail_price'), 0), 'third_price': _safe_num(vr.get('third_price'), 0), 'branch_price': _safe_num(vr.get('branch_price'), 0)})
                conn.commit()
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise
        return jsonify({'success': True, 'item_code': item_code_int, 'message': 'Item request saved successfully!'})
    except Exception as exc:
        return jsonify({'success': False, 'error': f'Save failed: {exc}'}, 500)

def _ho_table_exists(table: str) -> bool:
    try:
        with _get_tenant_connection('HO') as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT COUNT(*) FROM user_tables WHERE table_name = :t', {'t': table.upper()})
                return int((cur.fetchone() or [0])[0] or 0) > 0
    except Exception:
        return False

def _ho_detect_column(table: str, candidates: list) -> str | None:
    try:
        with _get_tenant_connection('HO') as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT column_name FROM user_tab_columns WHERE table_name = :t', {'t': table.upper()})
                existing = {str(r[0]).upper() for r in cur.fetchall() or []}
                for c in candidates:
                    if c.upper() in existing:
                        return c.upper()
    except Exception:
        pass
    return None

def _ho_fetch_popup_list(table_candidates: list, code_candidates: list, name_candidates: list, where_extra: str='', params: dict | None=None) -> list:
    """Generic popup list fetcher from HO DB using table/column auto-detection."""
    tbl = next((t for t in table_candidates if _ho_table_exists(t)), None)
    if not tbl:
        return []
    code_col = _ho_detect_column(tbl, code_candidates)
    name_col = _ho_detect_column(tbl, name_candidates)
    if not code_col:
        return []
    sel = f'{code_col} AS code, {name_col} AS name' if name_col else f'{code_col} AS code, NULL AS name'
    order = f'ORDER BY {(name_col if name_col else code_col)}'
    where = f'WHERE {where_extra}' if where_extra else ''
    try:
        with _get_tenant_connection('HO') as conn:
            with conn.cursor() as cur:
                cur.execute(f'SELECT {sel} FROM {tbl} {where} {order}', params or {})
                rows = cur.fetchall() or []
                return [{'code': r[0], 'name': str(r[1] or '') if r[1] is not None else ''} for r in rows]
    except Exception:
        return []

def _get_ho_chart_of_accounts() -> list:
    """Fetch Chart of Accounts from HO DB (same query pattern as get_all_chart_of_accounts)."""
    tbl_candidates = ['CHARTOFACCOUNTS', 'CHART_OF_ACCOUNTS', 'COA']
    tbl = next((t for t in tbl_candidates if _ho_table_exists(t)), None)
    if not tbl:
        return []
    code_col = _ho_detect_column(tbl, ['CODE', 'ACCOUNTCODE', 'ACCOUNT_CODE'])
    name_col = _ho_detect_column(tbl, ['NAME', 'ACCOUNTNAME', 'ACCOUNT_NAME'])
    postable_col = _ho_detect_column(tbl, ['IS_POSTABLE', 'ISPOSTABLE', 'POSTABLE'])
    if not code_col:
        return []
    postable_filter = f"WHERE {postable_col} = 'Y'" if postable_col else ''
    try:
        with _get_tenant_connection('HO') as conn:
            with conn.cursor() as cur:
                name_expr = f'{name_col} AS name' if name_col else 'NULL AS name'
                cur.execute(f'SELECT {code_col} AS code, {name_expr} FROM {tbl} {postable_filter} ORDER BY {code_col}')
                rows = cur.fetchall() or []
                return [{'code': r[0], 'name': str(r[1] or '') if r[1] is not None else ''} for r in rows]
    except Exception:
        return []

@bp.route('/ho/api/salesman-list')
def ho_api_salesman_list():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    data = _ho_fetch_popup_list(table_candidates=['SALESMAN', 'TBSALESMAN', 'TBRSALESMAN'], code_candidates=['SALESMANCODE', 'CODE'], name_candidates=['SALESMANNAME', 'NAME'])
    return jsonify({'success': True, 'salesmen': data})

@bp.route('/ho/api/category-list')
def ho_api_category_list():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    data = _ho_fetch_popup_list(table_candidates=['TBLCUSTOMERCATEGORY', 'CUSTOMERCATEGORY'], code_candidates=['CATEGORYCODE', 'CODE'], name_candidates=['CATEGORYNAME', 'NAME'])
    return jsonify({'success': True, 'categories': data})

@bp.route('/ho/api/route-list')
def ho_api_route_list():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    data = _ho_fetch_popup_list(table_candidates=['TBLROUTES', 'TBLROUTE', 'ROUTES'], code_candidates=['ROUTENO', 'CODE'], name_candidates=['ROUTENAME', 'NAME'])
    return jsonify({'success': True, 'routes': data})

@bp.route('/ho/api/employee-list')
def ho_api_employee_list():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    pending_col = _ho_detect_column('EMPLOYEE1', ['PENDING']) or _ho_detect_column('EMPLOYEE', ['PENDING'])
    where_extra = f"UPPER(TRIM({pending_col})) = 'Y'" if pending_col else ''
    data = _ho_fetch_popup_list(table_candidates=['EMPLOYEE1', 'EMPLOYEE'], code_candidates=['EMPLOYEECODE', 'EMPCODE', 'CODE'], name_candidates=['EMPLOYEENAME', 'EMPNAME', 'NAME'], where_extra=where_extra)
    return jsonify({'success': True, 'employees': data})

@bp.route('/ho/api/chart-of-accounts')
def ho_api_chart_of_accounts():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    return jsonify({'success': True, 'accounts': _get_ho_chart_of_accounts()})

@bp.route('/ho/api/location-list')
def ho_api_location_list():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    return jsonify({'success': True, 'locations': _get_ho_all_locations('HO')})
CUSTOMER_TEMP_TABLE = 'CUSTOMERTEMP'
CUSTOMER_ALERT_TABLE = 'CR_ALERT_CONTROL'
_CR_SCHEMA_ENSURE_TTL_SEC = 300
_cr_schema_ensure_cache: dict[str, float] = {}
_cr_assigned_cols_cache: dict[str, tuple[bool, float]] = {}
_CR_FORM_CACHE_TTL_SEC = 180
_cr_chart_accounts_cache: dict[str, tuple[list, float]] = {}
_cr_default_accounts_cache: dict[str, tuple[dict, float]] = {}

def _cr_should_skip_schema_ensure(cache_key: str) -> bool:
    last_ok = _cr_schema_ensure_cache.get(cache_key, 0.0)
    return time.time() - last_ok < _CR_SCHEMA_ENSURE_TTL_SEC

def _cr_mark_schema_ensure_ok(cache_key: str) -> None:
    _cr_schema_ensure_cache[cache_key] = time.time()

def _cr_perf_ms(start_ts: float) -> int:
    return int((time.perf_counter() - start_ts) * 1000)

def _cr_get_cached_form_accounts(tenant_key: str, get_all_chart_of_accounts_fn, ensure_default_party_accounts_fn, default_party_accounts: dict) -> tuple[list, dict]:
    now = time.time()
    tkey = (tenant_key or '__NO_TENANT__').strip().upper()
    cached_chart = _cr_chart_accounts_cache.get(tkey)
    cached_defaults = _cr_default_accounts_cache.get(tkey)
    chart_fresh = bool(cached_chart and now - cached_chart[1] < _CR_FORM_CACHE_TTL_SEC)
    defaults_fresh = bool(cached_defaults and now - cached_defaults[1] < _CR_FORM_CACHE_TTL_SEC)
    if chart_fresh and defaults_fresh:
        return (list(cached_chart[0]), dict(cached_defaults[0]))
    chart_accounts = []
    default_accounts = dict(default_party_accounts or {})
    try:
        chart_accounts = get_all_chart_of_accounts_fn()
    except Exception:
        chart_accounts = []
    try:
        default_accounts = ensure_default_party_accounts_fn()
    except Exception:
        default_accounts = dict(default_party_accounts or {})
    _cr_chart_accounts_cache[tkey] = (list(chart_accounts or []), now)
    _cr_default_accounts_cache[tkey] = (dict(default_accounts or {}), now)
    return (list(chart_accounts or []), dict(default_accounts or {}))

def _ensure_customer_request_temp_table(tenant_id: str) -> None:
    """Create CUSTOMERTEMP in HO DB if it does not exist; also add any missing columns."""
    cache_key = f'{tenant_id}:customer_temp:v2'
    if _cr_should_skip_schema_ensure(cache_key):
        return
    with _get_tenant_connection(tenant_id) as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT COUNT(*) FROM user_tables WHERE table_name = :t', {'t': CUSTOMER_TEMP_TABLE})
            exists = int((cur.fetchone() or [0])[0] or 0) > 0
            if not exists:
                cur.execute(f"\n                    CREATE TABLE {CUSTOMER_TEMP_TABLE} (\n                        CUSTOMERCODE  NUMBER(10)    NOT NULL,\n                        LOCATIONCODE  NUMBER(6),\n                        CUSTOMERNAME  VARCHAR2(200) NOT NULL,\n                        CUSTOMERTYPE  VARCHAR2(10),\n                        DESIGNATION   VARCHAR2(100),\n                        SEX           CHAR(1),\n                        ADDRESS       VARCHAR2(200),\n                        NATIONALITY   VARCHAR2(100),\n                        TELEPHONE     VARCHAR2(15),\n                        FAX           VARCHAR2(15),\n                        MOBILE        VARCHAR2(15),\n                        EMAIL         VARCHAR2(150),\n                        WHATSAPP      VARCHAR2(20),\n                        QATARID       VARCHAR2(50),\n                        CREDITLIMIT   NUMBER(18,3),\n                        CREDITTERMS   NUMBER(10),\n                        SALESMANCODE  NUMBER(10),\n                        INVOICECODE   NUMBER(5),\n                        FLAG          VARCHAR2(1),\n                        CLOSED        VARCHAR2(1),\n                        COUNTERSALE   VARCHAR2(1),\n                        CUSTOMERCATEGORY NUMBER(10),\n                        BYSALESMAN    NUMBER(10),\n                        ROUTENO       NUMBER(10),\n                        STREET        VARCHAR2(200),\n                        ZONE          VARCHAR2(100),\n                        POBOX         VARCHAR2(50),\n                        CRNO          VARCHAR2(250),\n                        RECEIVABLEACCOUNT  NUMBER(10),\n                        SALESACCOUNT       NUMBER(10),\n                        VATOUTPUTACCOUNT   NUMBER(10),\n                        ADVANCEACCOUNT     NUMBER(10),\n                        EMPLOYEECODE  NUMBER(10),\n                        REASON        VARCHAR2(500),\n                        OTHERREASON   VARCHAR2(500),\n                        CLOSEDREASON  VARCHAR2(500),\n                        STATUS        VARCHAR2(20) DEFAULT 'PENDING',\n                        ALERTACKBY    VARCHAR2(100),\n                        ALERTACKDATE  DATE,\n                        CREATEDBY     VARCHAR2(100),\n                        CREATEDDATE   DATE,\n                        UPDATEDBY     VARCHAR2(100),\n                        UPDATEDDATE   DATE,\n                        CONSTRAINT PK_CUSTOMERTEMP PRIMARY KEY (CUSTOMERCODE)\n                    )\n                ")
            cur.execute('SELECT column_name FROM user_tab_columns WHERE table_name = :t', {'t': CUSTOMER_TEMP_TABLE})
            existing_cols = {str(r[0]).upper() for r in cur.fetchall() or []}
            required_extra = {'EMAIL': 'VARCHAR2(150)', 'WHATSAPP': 'VARCHAR2(20)', 'QATARID': 'VARCHAR2(50)', 'EMPLOYEECODE': 'NUMBER(10)', 'REASON': 'VARCHAR2(500)', 'OTHERREASON': 'VARCHAR2(500)', 'CLOSEDREASON': 'VARCHAR2(500)', 'STATUS': "VARCHAR2(20) DEFAULT 'PENDING'", 'ALERTACKBY': 'VARCHAR2(100)', 'ALERTACKDATE': 'DATE', 'COUNTERSALE': 'VARCHAR2(1)', 'CREATEDBY': 'VARCHAR2(100)', 'CREATEDDATE': 'DATE', 'UPDATEDBY': 'VARCHAR2(100)', 'UPDATEDDATE': 'DATE', 'LOCATIONCODE': 'NUMBER(10)', 'CUSTOMERNAME': 'VARCHAR2(250)', 'SALESMANCODE': 'NUMBER(10)', 'MOBILENO': 'VARCHAR2(20)', 'TELEPHONENO': 'VARCHAR2(20)', 'INVOICECODE': 'NUMBER(5)', 'FLAG': 'VARCHAR2(1)', 'CLOSED': 'VARCHAR2(1)', 'CUSTOMERCATEGORY': 'NUMBER(10)', 'BYSALESMAN': 'NUMBER(10)', 'ROUTENO': 'NUMBER(10)', 'RECEIVABLEACCOUNT': 'NUMBER(10)', 'SALESACCOUNT': 'NUMBER(10)', 'VATOUTPUTACCOUNT': 'NUMBER(10)', 'ADVANCEACCOUNT': 'NUMBER(10)', 'STREET': 'VARCHAR2(200)', 'ZONE': 'VARCHAR2(100)', 'POBOX': 'VARCHAR2(50)', 'CRNO': 'VARCHAR2(250)', 'BRANCH': 'VARCHAR2(50)', 'ASSIGNEDCODE': 'NUMBER(10)', 'ASSIGNEDCCODE': 'VARCHAR2(20)', 'REJECTCOMMENT': 'VARCHAR2(1000)', 'AI_DUP_FLAG': "CHAR(1) DEFAULT 'N'"}
            for col, col_def in required_extra.items():
                if col not in existing_cols:
                    try:
                        cur.execute(f'ALTER TABLE {CUSTOMER_TEMP_TABLE} ADD {col} {col_def}')
                    except Exception:
                        pass
        conn.commit()
    _cr_mark_schema_ensure_ok(cache_key)

def _customer_temp_has_assigned_cols(tenant_id: str) -> bool:
    cache_key = f'{tenant_id}:assigned_cols'
    cached = _cr_assigned_cols_cache.get(cache_key)
    now = time.time()
    if cached and now - cached[1] < _CR_SCHEMA_ENSURE_TTL_SEC:
        return bool(cached[0])
    has_assigned = False
    try:
        with _get_tenant_connection(tenant_id) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM user_tab_columns WHERE table_name=:t AND column_name='ASSIGNEDCODE'", {'t': CUSTOMER_TEMP_TABLE})
                has_assigned = (cur.fetchone() or [0])[0] > 0
    except Exception:
        has_assigned = False
    _cr_assigned_cols_cache[cache_key] = (has_assigned, now)
    return has_assigned

def _get_next_customer_request_code(tenant_id: str) -> int:
    """Return MAX(CUSTOMERCODE)+1 from CUSTOMERTEMP in the HO DB."""
    try:
        with _get_tenant_connection(tenant_id) as conn:
            with conn.cursor() as cur:
                cur.execute(f'SELECT NVL(MAX(CUSTOMERCODE),0)+1 FROM {CUSTOMER_TEMP_TABLE}')
                row = cur.fetchone()
                return int((row or [1])[0] or 1)
    except Exception:
        return 1

def _ho_get_location_name_direct(tenant_id: str, location_code) -> str:
    """Fetch LOCATIONNAME from HO LOCATIONMASTER for a given LOCATIONCODE."""
    if not location_code:
        return ''
    try:
        lc = int(str(location_code).strip())
    except (ValueError, TypeError):
        return ''
    try:
        with _get_tenant_connection(tenant_id) as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT LOCATIONNAME FROM LOCATIONMASTER WHERE LOCATIONCODE = :lc', {'lc': lc})
                row = cur.fetchone()
                return str(row[0] or '').strip() if row else ''
    except Exception as e:
        print(f'[_ho_get_location_name_direct] ERROR lc={location_code}: {e}')
        return ''

def _ho_get_branch_info_by_dbkey(ho_tenant_id: str, dbkey: str) -> dict:
    """Return {name, dbcode} for the LOCATIONS row whose DBKEY matches the given tenant id.
    Reuses _get_request_location_rows which is already proven for the item-request popup.
    'code'  in location rows = DBCODE (branch code)
    'name'  in location rows = NAME   (branch name)
    """
    empty = {'name': '', 'dbcode': ''}
    if not dbkey:
        return empty
    dk_upper = dbkey.strip().upper()
    try:
        for row in _get_request_location_rows(ho_tenant_id) or []:
            if str(row.get('dbkey') or '').strip().upper() == dk_upper:
                return {'name': str(row.get('name') or '').strip(), 'dbcode': str(row.get('code') or '').strip()}
    except Exception as e:
        print(f'[_ho_get_branch_info_by_dbkey] ERROR dbkey={dbkey}: {e}')
    return empty

def _ho_get_branch_name_by_dbkey(ho_tenant_id: str, dbkey: str) -> str:
    """Convenience wrapper — returns branch NAME only."""
    return _ho_get_branch_info_by_dbkey(ho_tenant_id, dbkey).get('name', '')

def _ho_get_all_branch_info(_ho_tenant_id_unused: str='HO') -> dict:
    """Return {tenant_id -> {name, dbcode}} from auth DB tenant_databases table."""
    result = {}
    try:
        rows = _safe_rows_auth('SELECT tenant_id, locationname, locationcode FROM tenant_databases WHERE tenant_id IS NOT NULL', {}) or []
        for row in rows:
            tid = str(row.get('tenant_id') or '').strip().upper()
            if tid:
                result[tid] = {'name': str(row.get('locationname') or '').strip(), 'dbcode': str(row.get('locationcode') or '').strip()}
    except Exception as e:
        print(f'[_ho_get_all_branch_info] ERROR: {e}')
    return result

def _get_ho_all_locations(tenant_id: str) -> list:
    """Return all {code, name} rows from HO LOCATIONMASTER."""
    try:
        with _get_tenant_connection(tenant_id) as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT LOCATIONCODE, LOCATIONNAME FROM LOCATIONMASTER ORDER BY LOCATIONCODE')
                rows = cur.fetchall() or []
                return [{'code': r[0], 'name': str(r[1] or '').strip()} for r in rows]
    except Exception as e:
        print(f'[_get_ho_all_locations] ERROR: {e}')
        return []

def _get_customer_request_status_counts(tenant_id: str, branch_scope: str='') -> dict:
    counts = {'pending': 0, 'rejected': 0, 'converted': 0}
    try:
        with _get_tenant_connection(tenant_id) as conn:
            with conn.cursor() as cur:
                where = []
                params = {}
                if branch_scope:
                    where.append("UPPER(NVL(BRANCH,'')) = :br")
                    params['br'] = str(branch_scope).strip().upper()
                where_sql = 'WHERE ' + ' AND '.join(where) if where else ''
                cur.execute(f"\n                    SELECT UPPER(NVL(STATUS,'PENDING')) AS ST, COUNT(*)\n                    FROM {CUSTOMER_TEMP_TABLE}\n                    {where_sql}\n                    GROUP BY UPPER(NVL(STATUS,'PENDING'))\n                    ", params)
                for st, cnt in cur.fetchall() or []:
                    key = str(st or '').strip().lower()
                    if key == 'converting':
                        counts['pending'] += int(cnt or 0)
                    elif key in counts:
                        counts[key] = int(cnt or 0)
    except Exception as e:
        print(f'[_get_customer_request_status_counts] ERROR: {e}')
    return counts

def _get_customer_request_rows_by_status(tenant_id: str, status_key: str, search: str='', branch: str='', branch_scope: str='', invoice_filter: str='', date_from: str='', date_to: str='') -> list:
    status_map = {'pending': 'PENDING', 'approved': 'APPROVED', 'rejected': 'REJECTED', 'converted': 'CONVERTED'}
    status_val = status_map.get(status_key, 'PENDING')
    try:
        with _get_tenant_connection(tenant_id) as conn:
            with conn.cursor() as cur:
                has_assigned = _customer_temp_has_assigned_cols(tenant_id)
                assigned_sel = ', ASSIGNEDCODE, ASSIGNEDCCODE' if has_assigned else ', NULL AS ASSIGNEDCODE, NULL AS ASSIGNEDCCODE'
                if status_key == 'pending':
                    where = ["UPPER(NVL(STATUS,'PENDING')) IN ('PENDING', 'CONVERTING')"]
                    params: dict = {}
                else:
                    where = ["UPPER(NVL(STATUS,'PENDING')) = :st"]
                    params: dict = {'st': status_val}
                if search:
                    where.append('(UPPER(CUSTOMERNAME) LIKE :srch OR TRIM(TO_CHAR(CUSTOMERCODE)) LIKE :srch)')
                    params['srch'] = f'%{search.upper()}%'
                if branch:
                    where.append("UPPER(NVL(BRANCH,'')) = :br")
                    params['br'] = branch.upper()
                if branch_scope:
                    where.append("UPPER(NVL(BRANCH,'')) = :br_scope")
                    params['br_scope'] = branch_scope.upper()
                if invoice_filter:
                    where.append('INVOICECODE = :inv')
                    params['inv'] = int(invoice_filter)
                if date_from:
                    where.append("TRUNC(CREATEDDATE) >= TO_DATE(:df,'YYYY-MM-DD')")
                    params['df'] = date_from
                if date_to:
                    where.append("TRUNC(CREATEDDATE) <= TO_DATE(:dt,'YYYY-MM-DD')")
                    params['dt'] = date_to
                where_sql = ' AND '.join(where)
                cur.execute(f"\n                    SELECT\n                        CUSTOMERCODE, CUSTOMERNAME, MOBILE, TELEPHONE,\n                        INVOICECODE, BRANCH,\n                        UPPER(NVL(STATUS,'PENDING')) AS STATUS,\n                        ALERTACKBY, ALERTACKDATE,\n                        REJECTCOMMENT,\n                        CREATEDBY, CREATEDDATE, UPDATEDBY, UPDATEDDATE\n                        {assigned_sel}\n                    FROM {CUSTOMER_TEMP_TABLE}\n                    WHERE {where_sql}\n                    ORDER BY NVL(UPDATEDDATE,CREATEDDATE) DESC, CUSTOMERCODE DESC\n                ", params)
                rows = cur.fetchall() or []
                cols = [str(c[0]).lower() for c in cur.description or []]
                return [dict(zip(cols, r)) for r in rows]
    except Exception as e:
        print(f'[_get_customer_request_rows_by_status] ERROR: {e}')
        return []

def _get_customer_request_row(tenant_id: str, customercode: int) -> dict:
    try:
        with _get_tenant_connection(tenant_id) as conn:
            with conn.cursor() as cur:
                cur.execute(f'SELECT * FROM {CUSTOMER_TEMP_TABLE} WHERE CUSTOMERCODE = :cc', {'cc': customercode})
                row = cur.fetchone()
                if not row:
                    return {}
                cols = [str(c[0]).lower() for c in cur.description or []]
                return dict(zip(cols, row))
    except Exception:
        return {}

def _tenant_ccode_numeric_max(tenant_id: str) -> int:
    """Largest numeric part of CCODE (e.g. C400001 -> 400001) in tenant's CUSTOMER-ish table."""
    tid = str(tenant_id or '').strip()
    if not tid:
        return 0
    try:
        with _get_tenant_connection(tid) as conn:
            with conn.cursor() as cur:
                tbl = _detect_customer_table(cur)
                if not tbl:
                    return 0
                cur.execute("SELECT COUNT(*) FROM user_tab_columns WHERE table_name=:t AND column_name='CCODE'", {'t': tbl})
                if not cur.fetchone()[0]:
                    return 0
                cur.execute(f"\n                    SELECT NVL(MAX(\n                        CASE WHEN REGEXP_LIKE(TRIM(CCODE), '^[Cc][0-9]+$')\n                             THEN TO_NUMBER(SUBSTR(TRIM(CCODE), 2))\n                             ELSE 0 END\n                    ), 0) FROM {tbl}\n                    ")
                val = cur.fetchone()[0]
                return int(val) if val else 0
    except Exception:
        return 0

def _detect_customer_table(cur) -> Optional[str]:
    """Return the customer table name that has a CUSTOMERCODE column, or None.
    Tries preferred names first, then falls back to any table with CUSTOMERCODE.
    """
    for tbl in ('CUSTOMER', 'CUSTOMERMASTER', 'CUSTMASTER', 'CUSTOMERFILE', 'CUSTFILE'):
        cur.execute("SELECT COUNT(*) FROM user_tab_columns WHERE table_name=:t AND column_name='CUSTOMERCODE'", {'t': tbl})
        if cur.fetchone()[0]:
            return tbl
    cur.execute("SELECT table_name FROM (  SELECT t.table_name FROM user_tables t   WHERE EXISTS (    SELECT 1 FROM user_tab_columns c     WHERE c.table_name = t.table_name AND c.column_name = 'CUSTOMERCODE'  ) AND t.table_name LIKE '%CUST%'   ORDER BY t.table_name) WHERE ROWNUM = 1")
    row = cur.fetchone()
    return row[0] if row else None

def _cc_next_code(target_tenant: str=None):
    """Return (next_customercode int, next_ccode str) where:
    - CUSTOMERCODE = MAX(CUSTOMERCODE)+1 from the target branch DB
                     (auto-detects whichever table has CUSTOMERCODE column)
    - CCODE        = global MAX numeric part of CCODE across ALL tenant DBs + 1
    """
    all_tenants = get_active_tenants_with_network()
    next_customercode = 1
    if target_tenant:
        try:
            with _get_tenant_connection(target_tenant) as conn:
                with conn.cursor() as cur:
                    tbl = _detect_customer_table(cur)
                    if tbl:
                        cur.execute(f'SELECT NVL(MAX(CUSTOMERCODE), 0) + 1 FROM {tbl}')
                        val = cur.fetchone()[0]
                        if val:
                            next_customercode = int(val)
        except Exception:
            pass
    tenant_ids = [str(t.get('tenant_id') or '').strip() for t in all_tenants or [] if str(t.get('tenant_id') or '').strip()]
    global_ccode_max = 0
    if len(tenant_ids) <= 1:
        for tid in tenant_ids:
            m = _tenant_ccode_numeric_max(tid)
            if m > global_ccode_max:
                global_ccode_max = m
    else:
        workers = min(16, len(tenant_ids))
        try:
            with ThreadPoolExecutor(max_workers=workers) as ex:
                futures = [ex.submit(_tenant_ccode_numeric_max, tid) for tid in tenant_ids]
                for fut in as_completed(futures):
                    try:
                        m = fut.result()
                        if m > global_ccode_max:
                            global_ccode_max = m
                    except Exception:
                        pass
        except Exception:
            for tid in tenant_ids:
                m = _tenant_ccode_numeric_max(tid)
                if m > global_ccode_max:
                    global_ccode_max = m
    next_ccode_num = global_ccode_max + 1
    return (next_customercode, f'C{next_ccode_num}')

def _is_ora_00001_unique_violation(exc: BaseException) -> bool:
    """True if Oracle rejected the statement because a unique / PK constraint was violated."""
    if exc is None:
        return False
    s = str(exc)
    if 'ORA-00001' in s:
        return True
    a0 = exc.args[0] if getattr(exc, 'args', None) else None
    if a0 is not None and getattr(a0, 'code', None) == 1:
        return True
    return False

def _get_customers_from_tenant(tenant_id: str, search: str=None, page: int=1, per_page: int=100, *, locationcode_eq: Optional[int]=None, invoicecode_eq: Optional[str]=None, flag_eq: Optional[str]=None):
    """Return (rows, total) from the given tenant DB ``CUSTOMER`` table only.

    Optional SQL filters apply when the corresponding columns exist (used by HO Customer Central list).
    """
    tbl = 'CUSTOMER'
    offset = (page - 1) * per_page
    try:
        with _get_tenant_connection(tenant_id) as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT column_name FROM user_tab_columns WHERE UPPER(table_name)=UPPER(:t) ORDER BY column_id', {'t': tbl})
                all_cols_uc = {str(r[0]).upper() for r in cur.fetchall() or [] if r and r[0] is not None}
                base_params: dict = {}
                where_parts: List[str] = []
                if search:
                    qparts = ['UPPER(CUSTOMERNAME) LIKE :q', 'UPPER(TO_CHAR(CUSTOMERCODE)) LIKE :q']
                    if 'CCODE' in all_cols_uc:
                        qparts.append('UPPER(TRIM(TO_CHAR(CCODE))) LIKE :q')
                    where_parts.append('(' + ' OR '.join(qparts) + ')')
                    base_params['q'] = f'%{search.upper()}%'
                if locationcode_eq is not None and 'LOCATIONCODE' in all_cols_uc:
                    where_parts.append('LOCATIONCODE = :loc_eq')
                    base_params['loc_eq'] = int(locationcode_eq)
                if invoicecode_eq and str(invoicecode_eq).strip() and ('INVOICECODE' in all_cols_uc):
                    try:
                        base_params['inv_eq'] = int(str(invoicecode_eq).strip())
                        where_parts.append('INVOICECODE = :inv_eq')
                    except (TypeError, ValueError):
                        pass
                if flag_eq and str(flag_eq).strip() and ('FLAG' in all_cols_uc):
                    where_parts.append('FLAG = :flag_eq')
                    base_params['flag_eq'] = str(flag_eq).strip().upper()[:1]
                where_rest = ''
                if where_parts:
                    where_rest = ' AND ' + ' AND '.join(where_parts)
                count_sql = f'SELECT COUNT(*) FROM {tbl} WHERE 1=1{where_rest}'
                cur.execute(count_sql, dict(base_params))
                total_raw = cur.fetchone()[0]
                total = int(total_raw or 0)
                sel_cols = ['CUSTOMERCODE']
                if 'CCODE' in all_cols_uc:
                    sel_cols.append('CCODE')
                sel_cols.append('CUSTOMERNAME')
                for c in ['LOCATIONCODE', 'MOBILE', 'TELEPHONE', 'INVOICECODE', 'FLAG', 'CUSTOMERCATEGORY', 'SALESMANCODE', 'CREATEDDATE']:
                    if c in all_cols_uc:
                        sel_cols.append(c)
                data_sql = f"\n                    SELECT {', '.join(sel_cols)}\n                    FROM (\n                        SELECT t.*, ROWNUM rn FROM (\n                            SELECT {', '.join(sel_cols)} FROM {tbl}\n                            WHERE 1=1{where_rest}\n                            ORDER BY CUSTOMERCODE DESC\n                        ) t WHERE ROWNUM <= :off_lim\n                    ) WHERE rn > :off\n                "
                data_params = dict(base_params)
                data_params['off'] = offset
                data_params['off_lim'] = offset + per_page
                cur.execute(data_sql, data_params)
                cols = [d[0].lower() for d in cur.description]
                rows = [dict(zip(cols, r)) for r in cur.fetchall()]
                return (rows, total)
    except Exception:
        return ([], 0)

@bp.route('/ho/customer-central')
def customer_central():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    search = (request.args.get('search') or '').strip()
    tenant_filter = (request.args.get('tenant') or '').strip()
    invoice_filter = (request.args.get('invoice') or '').strip()
    status_filter = (request.args.get('status') or '').strip()
    page_raw = request.args.get('page') or '1'
    try:
        page = max(1, int(page_raw))
    except (TypeError, ValueError):
        page = 1
    per_page = 100
    all_tenants = get_active_tenants_with_network()
    loc_code_for_branch: Optional[int] = None
    if tenant_filter:
        for tm in all_tenants:
            if str(tm.get('tenant_id') or '').strip() == tenant_filter:
                lc = tm.get('locationcode')
                if lc is not None:
                    try:
                        loc_code_for_branch = int(lc)
                    except (TypeError, ValueError):
                        loc_code_for_branch = None
                break
    rows_ho, total_count = _get_customers_from_tenant('HO', search=search or None, page=page, per_page=per_page, locationcode_eq=loc_code_for_branch, invoicecode_eq=invoice_filter or None, flag_eq=status_filter or None)
    loc_to_branch: Dict[int, Dict[str, str]] = {}
    for tm in all_tenants:
        lc_raw = tm.get('locationcode')
        if lc_raw is None:
            continue
        try:
            li = int(lc_raw)
        except (TypeError, ValueError):
            continue
        tid = str(tm.get('tenant_id') or '').strip() or '?'
        loc_to_branch[li] = {'tenant_id': tid, 'tenant_name': str(tm.get('display_name') or tid)}
    for r in rows_ho:
        lc_row = r.get('locationcode')
        li = None
        try:
            li = int(lc_row) if lc_row is not None else None
        except (TypeError, ValueError):
            li = None
        info = loc_to_branch.get(li) if li is not None else None
        if info:
            r['tenant_id'] = info['tenant_id']
            r['tenant_name'] = info['tenant_name']
        else:
            r['tenant_id'] = 'HO'
            r['tenant_name'] = '—'
    total_pages = max(1, (total_count + per_page - 1) // per_page)
    return render_template('ho/ho_customer_central.html', rows=rows_ho, search=search, tenant_filter=tenant_filter, invoice_filter=invoice_filter, status_filter=status_filter, all_tenants=all_tenants, current_page=page, total_pages=total_pages, total_count=total_count)

@bp.route('/ho/customer-central/form')
def customer_central_form():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    from_cr = (request.args.get('from_cr') or '').strip()
    prefill = {}
    if from_cr and from_cr.isdigit():
        try:
            ho_tenant_id = 'HO'
            with _get_tenant_connection(ho_tenant_id) as conn:
                with conn.cursor() as cur:
                    cur.execute(f'SELECT * FROM {CUSTOMER_TEMP_TABLE} WHERE CUSTOMERCODE = :cc', {'cc': int(from_cr)})
                    cols = [d[0].lower() for d in cur.description]
                    row = cur.fetchone()
                    if row:
                        prefill = dict(zip(cols, row))
        except Exception:
            prefill = {}
    target_tenant = (request.args.get('tenant') or prefill.get('branch') or '').strip()
    all_tenants = get_active_tenants_with_network()
    next_code, next_ccode = _cc_next_code(target_tenant or None)
    prefill_names = {}
    if prefill and target_tenant:
        try:
            with _get_tenant_connection(target_tenant) as conn:
                with conn.cursor() as cur:

                    def _lookup(tbl, code_col, name_col, val):
                        if not val:
                            return ''
                        try:
                            cur.execute(f'SELECT {name_col} FROM {tbl} WHERE {code_col}=:v', {'v': val})
                            r = cur.fetchone()
                            return r[0] if r else ''
                        except Exception:
                            return ''
                    sm_code = prefill.get('salesmancode')
                    for sm_tbl in ('SALESMAN1', 'SALESMAN'):
                        name = _lookup(sm_tbl, 'SALESMANCODE', 'SALESMANNAME', sm_code)
                        if name:
                            prefill_names['salesman'] = name
                            break
                    cat_code = prefill.get('customercategory')
                    for cat_tbl in ('TBLCUSTOMERCATEGORY', 'CUSTOMERCATEGORY'):
                        name = _lookup(cat_tbl, 'CATEGORYCODE', 'CATEGORYNAME', cat_code)
                        if name:
                            prefill_names['customercategory'] = name
                            break
                    bs_code = prefill.get('bysalesman')
                    for sm_tbl in ('SALESMAN1', 'SALESMAN'):
                        name = _lookup(sm_tbl, 'SALESMANCODE', 'SALESMANNAME', bs_code)
                        if name:
                            prefill_names['bysalesman'] = name
                            break
                    rt_code = prefill.get('routeno')
                    for rt_tbl in ('TBLROUTES', 'ROUTEMASTER', 'ROUTES'):
                        name = _lookup(rt_tbl, 'ROUTENO', 'ROUTENAME', rt_code)
                        if name:
                            prefill_names['routeno'] = name
                            break
                    emp_code = prefill.get('employeecode')
                    try:
                        name = _lookup('EMPLOYEE1', 'EMPLOYEECODE', 'EMPLOYEENAME', emp_code)
                        if name:
                            prefill_names['employee'] = name
                    except Exception:
                        pass
        except Exception:
            pass
    api_salesman_url = url_for('ho.cc_api_salesman_list')
    api_category_url = url_for('ho.cc_api_category_list')
    api_route_url = url_for('ho.cc_api_route_list')
    api_employee_url = url_for('ho.cc_api_employee_list')
    api_chart_accounts_url = url_for('ho.cc_api_chart_accounts_list')
    try:
        from db import get_all_chart_of_accounts, ensure_default_party_accounts, DEFAULT_PARTY_ACCOUNTS
        chart_accounts = get_all_chart_of_accounts()
    except Exception:
        chart_accounts = []
    try:
        from db import ensure_default_party_accounts
        default_accounts = ensure_default_party_accounts()
    except Exception:
        default_accounts = {}
    return render_template('ho/ho_customer_central_form.html', prefill=prefill, prefill_names=prefill_names, from_cr=from_cr, target_tenant=target_tenant, all_tenants=all_tenants, next_code=next_code, next_ccode=next_ccode, chart_accounts=chart_accounts, default_accounts=default_accounts, api_salesman_url=api_salesman_url, api_category_url=api_category_url, api_route_url=api_route_url, api_employee_url=api_employee_url, api_chart_accounts_url=api_chart_accounts_url)

def _ho_update_customertemp_from_central(from_cr: int, base_col_map: Dict[str, Any], saved_codes: Dict[str, Dict[str, Any]], saved_tenants: List[str], username: str, cr_success_comment: Optional[str]=None) -> None:
    """Mirror Customer Central form data into the linked CUSTOMERTEMP row so the request reflects the latest values."""

    def _mark_converted_only(cur: Any) -> None:
        """Always set STATUS when branch save succeeded; avoids leaving the request stuck on PENDING."""
        cur.execute(f"UPDATE {CUSTOMER_TEMP_TABLE} SET STATUS='CONVERTED', UPDATEDBY=:u, UPDATEDDATE=SYSDATE WHERE CUSTOMERCODE=:cc", {'u': str(username or '')[:100], 'cc': from_cr})
    try:
        _ensure_customer_request_temp_table('HO')
        with _get_tenant_connection('HO') as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT column_name FROM user_tab_columns WHERE table_name = :t', {'t': CUSTOMER_TEMP_TABLE})
                temp_cols = {str(r[0]).upper() for r in cur.fetchall() or []}
                if not temp_cols or 'CUSTOMERCODE' not in temp_cols:
                    return
                skip = {'CUSTOMERCODE', 'CUSTOMERSTATUS', 'CREATEDSTATUS', 'DUEDAYS', 'CURRENTCREDITAMOUNT'}
                updates: Dict[str, Any] = {}
                for col, val in base_col_map.items():
                    c = str(col).upper()
                    if c in skip or c not in temp_cols:
                        continue
                    updates[c] = val
                if 'BRANCH' in temp_cols and saved_tenants:
                    updates['BRANCH'] = str(saved_tenants[0] or '').strip()[:50]
                if saved_tenants:
                    sc = saved_codes.get(saved_tenants[0]) or {}
                    if 'ASSIGNEDCODE' in temp_cols and sc.get('code') is not None:
                        updates['ASSIGNEDCODE'] = sc['code']
                    if 'ASSIGNEDCCODE' in temp_cols and sc.get('ccode') is not None:
                        updates['ASSIGNEDCCODE'] = str(sc.get('ccode') or '')[:20]
                if 'STATUS' in temp_cols:
                    updates['STATUS'] = 'CONVERTED'
                if 'LOCATIONCODE' in temp_cols:
                    updates['LOCATIONCODE'] = _get_ho_location_code()
                if 'OTHERREASON' in temp_cols:
                    o_base = str(updates.get('OTHERREASON') or base_col_map.get('OTHERREASON') or '').strip()
                    cmt = (cr_success_comment or '').strip()
                    if cmt:
                        updates['OTHERREASON'] = f'{o_base} {cmt}'.strip()[:500]
                    else:
                        updates['OTHERREASON'] = o_base[:500]
                if 'UPDATEDBY' in temp_cols:
                    updates['UPDATEDBY'] = str(username or '')[:100]
                if not updates:
                    if 'STATUS' in temp_cols:
                        _mark_converted_only(cur)
                    conn.commit()
                    return
                set_parts: List[str] = []
                params: Dict[str, Any] = {'cc': from_cr}
                for i, (col, val) in enumerate(updates.items()):
                    bind = f'b{i}'
                    set_parts.append(f'{col} = :{bind}')
                    params[bind] = val
                set_parts.append('UPDATEDDATE = SYSDATE')
                sql = f"UPDATE {CUSTOMER_TEMP_TABLE} SET {', '.join(set_parts)} WHERE CUSTOMERCODE = :cc"
                try:
                    cur.execute(sql, params)
                except Exception as ex_full:
                    import traceback
                    print(f'[_ho_update_customertemp_from_central] full row update failed for CUSTOMERCODE={from_cr}: {ex_full}; applying STATUS=CONVERTED only.')
                    traceback.print_exc()
                    if 'STATUS' in temp_cols:
                        _mark_converted_only(cur)
            conn.commit()
    except Exception:
        import traceback
        traceback.print_exc()
        try:
            _ensure_customer_request_temp_table('HO')
            with _get_tenant_connection('HO') as conn:
                with conn.cursor() as cur:
                    cur.execute('SELECT column_name FROM user_tab_columns WHERE table_name = :t', {'t': CUSTOMER_TEMP_TABLE})
                    has_status = any((str(r[0]).upper() == 'STATUS' for r in cur.fetchall() or []))
                    if has_status:
                        _mark_converted_only(cur)
                conn.commit()
        except Exception:
            import traceback
            traceback.print_exc()

def _cc_parse_int_account(raw: Any) -> int:
    try:
        if raw is None or (isinstance(raw, str) and (not str(raw).strip())):
            return 0
        return int(float(str(raw).strip()))
    except Exception:
        return 0

def _cc_account_value_or_default(raw: Any, default_key: str) -> int:
    n = _cc_parse_int_account(raw)
    if n:
        return n
    try:
        d = DEFAULT_PARTY_ACCOUNTS.get(default_key) if isinstance(DEFAULT_PARTY_ACCOUNTS, dict) else None
        if d is not None and str(d).strip():
            return int(float(str(d).strip()))
    except Exception:
        pass
    return 0

def _cc_validate_mandatory_gl_accounts(base: Dict[str, Any]) -> Optional[str]:
    """Return an error message if any of the four customer GL account codes is missing (<= 0)."""
    for key, label in (('RECEIVABLEACCOUNT', 'Receivable (A/R)'), ('SALESACCOUNT', 'Sales'), ('VATOUTPUTACCOUNT', 'VAT output'), ('ADVANCEACCOUNT', 'Customer advance')):
        v = base.get(key)
        try:
            n = int(v) if v is not None and str(v).strip() not in ('', 'None') else 0
        except Exception:
            n = 0
        if n <= 0:
            return f'{label} account is required (assign account codes in Customer Central or set party defaults in the system).'
    return None

def _cc_apply_account_column_aliases(cur: Any, cust_tbl: str, col_map: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map the four standard customer GL fields to whatever columns exist on this table
    (e.g. legacy ACCOUNTCODE for A/R when RECEIVABLEACCOUNT is absent).
    """
    out = dict(col_map or {})

    def has_col(c: str) -> bool:
        t = (cust_tbl or '').upper()
        cu = (c or '').upper()
        try:
            cur.execute('SELECT COUNT(*) FROM user_tab_columns WHERE UPPER(table_name) = :t AND UPPER(column_name) = :c', {'t': t, 'c': cu})
            return int((cur.fetchone() or [0])[0] or 0) > 0
        except Exception:
            return False
    specs: List[Tuple[str, Tuple[str, ...]]] = [('RECEIVABLEACCOUNT', ('RECEIVABLEACCOUNT', 'RECEIVABLE_AC', 'ACCOUNTCODE', 'ARACCOUNT', 'CUSTRECEIVABLEACCOUNT')), ('SALESACCOUNT', ('SALESACCOUNT', 'SALES_ACCOUNT', 'SALESACC')), ('VATOUTPUTACCOUNT', ('VATOUTPUTACCOUNT', 'OUTPUTVATACCOUNT', 'OUTPUT_VAT', 'VATOUTACCOUNT')), ('ADVANCEACCOUNT', ('ADVANCEACCOUNT', 'ADVANCE_ACCOUNT', 'CUSTADVANCEACCOUNT', 'PREPAYMENTACCOUNT'))]
    for std, candidates in specs:
        if std not in out:
            continue
        val = out.get(std)
        if val is None:
            continue
        target: Optional[str] = None
        for cand in candidates:
            if has_col(cand):
                target = cand
                break
        if not target:
            continue
        if target.upper() != std.upper():
            out[target] = val
            del out[std]
    return out

def _ho_execute_central_customer_saves(base_col_map: Dict[str, Any], target_tenants: List[str], username: str, from_cr: Optional[str], cr_success_comment: Optional[str]=None) -> Dict[str, Any]:
    """Insert into each target tenant CUSTOMER + HO mirror; optionally mark CUSTOMERTEMP CONVERTED.
    If ``cr_success_comment`` is set (e.g. AI auto-convert), it is appended to OTHERREASON on CUSTOMERTEMP."""
    saved: List[str] = []
    saved_codes: Dict[str, Dict[str, Any]] = {}
    errors: List[str] = []
    new_ccode: Any = ''
    new_code = 0
    for target_tenant in target_tenants:
        try:
            with _get_tenant_connection(target_tenant) as conn:
                with conn.cursor() as cur:
                    cust_tbl = _detect_customer_table(cur)
                    if not cust_tbl:
                        errors.append(f'{target_tenant}: customer table not found.')
                        continue

                    def _col_exists(col, _tbl=cust_tbl):
                        cur.execute('SELECT COUNT(*) FROM user_tab_columns WHERE table_name=:t AND column_name=:c', {'t': _tbl, 'c': col.upper()})
                        return cur.fetchone()[0] > 0
                    has_created = _col_exists('CREATEDDATE')
                    target_loc_code = _get_tenant_location_code(target_tenant)
                    branch_col_map = dict(base_col_map)
                    if target_loc_code is not None:
                        branch_col_map['LOCATIONCODE'] = target_loc_code
                    if _col_exists('CUSTOMERNAME'):
                        loc_for_dup = target_loc_code if _col_exists('LOCATIONCODE') else None
                        loc_col_dup = 'LOCATIONCODE' if _col_exists('LOCATIONCODE') else None
                        code_col_dup = 'CUSTOMERCODE' if _col_exists('CUSTOMERCODE') else None
                        dup_code = find_master_name_duplicate(
                            cur,
                            table=cust_tbl,
                            name_col='CUSTOMERNAME',
                            name_value=branch_col_map.get('CUSTOMERNAME'),
                            loc_col=loc_col_dup,
                            location_code=loc_for_dup,
                            code_col=code_col_dup,
                        )
                        if dup_code is not None:
                            errors.append(
                                f"{target_tenant}: {master_name_duplicate_message('customer', branch_col_map.get('CUSTOMERNAME'), location_code=loc_for_dup, existing_code=dup_code)}"
                            )
                            continue
                    for ins_try in range(12):
                        new_code, new_ccode = _cc_next_code(target_tenant)
                        col_map = {'CUSTOMERCODE': new_code, 'CCODE': new_ccode, **branch_col_map}
                        if _col_exists('CCODE'):
                            c_raw = col_map.get('CCODE')
                            if c_raw is None or str(c_raw).strip() == '':
                                col_map['CCODE'] = new_ccode
                            if not str(col_map.get('CCODE') or '').strip():
                                raise ValueError('C Code (CCODE) is required; could not assign a value.')
                        col_map = _cc_apply_account_column_aliases(cur, cust_tbl, col_map)
                        valid_cols = {c: v for c, v in col_map.items() if _col_exists(c)}
                        cols_str = ', '.join(valid_cols.keys())
                        placeholders = ', '.join((f':p_{i}' for i in range(len(valid_cols))))
                        params = {f'p_{i}': v for i, v in enumerate(valid_cols.values())}
                        if has_created:
                            ins_sql = f'INSERT INTO {cust_tbl} ({cols_str}, CREATEDDATE) VALUES ({placeholders}, SYSDATE)'
                        else:
                            ins_sql = f'INSERT INTO {cust_tbl} ({cols_str}) VALUES ({placeholders})'
                        try:
                            cur.execute(ins_sql, params)
                            break
                        except Exception as ex_ins:
                            if not _is_ora_00001_unique_violation(ex_ins) or ins_try >= 11:
                                raise
                conn.commit()
            saved.append(target_tenant)
            saved_codes[target_tenant] = {'code': new_code, 'ccode': new_ccode}
        except Exception as exc:
            import traceback
            traceback.print_exc()
            errors.append(f'{target_tenant}: {exc}')
    if saved:
        try:
            with _get_tenant_connection('HO') as ho_conn:
                with ho_conn.cursor() as ho_cur:
                    ho_tbl = _detect_customer_table(ho_cur)
                    if ho_tbl:

                        def _ho_col_exists(col):
                            ho_cur.execute('SELECT COUNT(*) FROM user_tab_columns WHERE table_name=:t AND column_name=:c', {'t': ho_tbl, 'c': col.upper()})
                            return ho_cur.fetchone()[0] > 0
                        ho_has_created = _ho_col_exists('CREATEDDATE')
                        if _ho_col_exists('CUSTOMERNAME'):
                            ho_loc = _get_ho_location_code()
                            dup_code = find_master_name_duplicate(
                                ho_cur,
                                table=ho_tbl,
                                name_col='CUSTOMERNAME',
                                name_value=base_col_map.get('CUSTOMERNAME'),
                                loc_col='LOCATIONCODE' if _ho_col_exists('LOCATIONCODE') else None,
                                location_code=ho_loc,
                                code_col='CUSTOMERCODE' if _ho_col_exists('CUSTOMERCODE') else None,
                            )
                            if dup_code is not None:
                                raise ValueError(
                                    master_name_duplicate_message(
                                        'customer',
                                        base_col_map.get('CUSTOMERNAME'),
                                        location_code=ho_loc,
                                        existing_code=dup_code,
                                    )
                                )
                        for ho_try in range(12):
                            ho_cur.execute(f'SELECT NVL(MAX(CUSTOMERCODE), 0) + 1 FROM {ho_tbl}')
                            ho_code = int(ho_cur.fetchone()[0])
                            ho_col_map = {'CUSTOMERCODE': ho_code, 'CCODE': new_ccode, **base_col_map, 'CUSTOMERSTATUS': 'Y', 'CREATEDSTATUS': 'Y'}
                            ho_col_map['LOCATIONCODE'] = _get_ho_location_code()
                            if _ho_col_exists('CCODE'):
                                hcc_raw = ho_col_map.get('CCODE')
                                if hcc_raw is None or str(hcc_raw).strip() == '':
                                    ho_col_map['CCODE'] = new_ccode
                                if not str(ho_col_map.get('CCODE') or '').strip():
                                    raise ValueError('HO central customer mirror requires C Code (CCODE).')
                            ho_col_map = _cc_apply_account_column_aliases(ho_cur, ho_tbl, ho_col_map)
                            ho_valid = {c: v for c, v in ho_col_map.items() if _ho_col_exists(c)}
                            ho_cols = ', '.join(ho_valid.keys())
                            ho_ph = ', '.join((f':hp_{i}' for i in range(len(ho_valid))))
                            ho_prm = {f'hp_{i}': v for i, v in enumerate(ho_valid.values())}
                            if ho_has_created:
                                ho_sql = f'INSERT INTO {ho_tbl} ({ho_cols}, CREATEDDATE) VALUES ({ho_ph}, SYSDATE)'
                            else:
                                ho_sql = f'INSERT INTO {ho_tbl} ({ho_cols}) VALUES ({ho_ph})'
                            try:
                                ho_cur.execute(ho_sql, ho_prm)
                                break
                            except Exception as ex_ho:
                                if not _is_ora_00001_unique_violation(ex_ho) or ho_try >= 11:
                                    raise
                ho_conn.commit()
        except Exception:
            import traceback
            traceback.print_exc()
    if saved and from_cr and from_cr.isdigit():
        _ho_update_customertemp_from_central(int(from_cr), base_col_map, saved_codes, saved, username, cr_success_comment=cr_success_comment)
    return {'saved': saved, 'saved_codes': saved_codes, 'errors': errors}

def _validate_customer_central_form_like_branch_master(form: Any) -> Optional[str]:
    """Match mandatory rules on the normal customer master form (customer_save)."""
    fd = form

    def digits(s: Any) -> str:
        return ''.join((c for c in str(s or '') if c.isdigit()))
    if not (fd.get('customername') or '').strip():
        return 'Customer name is required.'
    if not (fd.get('address') or '').strip():
        return 'Address is required.'
    tel_d = digits(fd.get('telephone'))
    mob_d = digits(fd.get('mobile'))
    if len(tel_d) != 8:
        return 'Telephone is required (exactly 8 digits).'
    if len(mob_d) != 8:
        return 'Mobile is required (exactly 8 digits).'
    qid = (fd.get('qatarid') or '').strip()
    if qid and len(digits(qid)) != 11:
        return 'Qatar ID must be exactly 11 digits when provided.'
    try:
        ic = int(fd.get('invoicecode') or 0)
    except (TypeError, ValueError):
        ic = 0
    if ic not in (1, 2):
        return 'Invoice Code (Cash / Credit) is required.'

    def gv(acc: str) -> int:
        try:
            return int(fd.get(acc) or 0)
        except (TypeError, ValueError):
            return 0
    ra, sa, va, aa = (gv('receivableaccount'), gv('salesaccount'), gv('vatoutputaccount'), gv('advanceaccount'))
    if not ra or not sa or (not va) or (not aa):
        return 'All customer related accounts are required.'
    if ic == 2:
        try:
            cl = float(fd.get('creditlimit') or 0)
            ct = float(fd.get('creditterm') or fd.get('creditterms') or 0)
        except (TypeError, ValueError):
            cl = ct = 0.0
        if not cl or cl <= 0:
            return 'Credit Limit is required for Credit customers.'
        if not ct or ct <= 0:
            return 'Credit Term (Days) is required for Credit customers.'
    return None

@bp.route('/ho/customer-central/save', methods=['POST'])
def customer_central_save():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    from nexa_http import flash
    username = session.get('user', 'SYSTEM')
    form = request.form
    target_tenants = [t.strip() for t in form.getlist('target_tenants') if t.strip()]
    from_cr = (form.get('from_cr') or '').strip()
    if not target_tenants:
        flash('Please select at least one target branch.', 'error')
        return redirect(url_for('ho.customer_central_form'))
    vcentral = _validate_customer_central_form_like_branch_master(form)
    if vcentral:
        flash(vcentral, 'error')
        if from_cr and from_cr.isdigit():
            return redirect(url_for('ho.customer_central_form', from_cr=from_cr))
        return redirect(url_for('ho.customer_central_form'))

    def fi(k, d=0):
        try:
            return int(form.get(k) or d)
        except:
            return d

    def fs(k, n=200):
        return (form.get(k) or '').strip()[:n]
    base_col_map = {'CUSTOMERNAME': fs('customername').upper(), 'CUSTOMERTYPE': fs('customertype', 1) or 'P', 'DESIGNATION': fs('designation', 100), 'SEX': fs('sex', 1) or 'M', 'ADDRESS': fs('address'), 'NATIONALITY': fs('nationality', 100), 'TELEPHONE': fs('telephone', 15), 'FAX': fs('fax', 15), 'MOBILE': fs('mobile', 15), 'EMAIL': fs('email', 150), 'WHATSAPP': fs('whatsapp', 20), 'QATARID': fs('qatarid', 50), 'CREDITLIMIT': fi('creditlimit'), 'CREDITTERMS': fi('creditterm'), 'DUEDAYS': fi('creditterm'), 'CURRENTCREDITAMOUNT': 0, 'SALESMANCODE': fi('salesmancode'), 'INVOICECODE': fi('invoicecode', 1), 'FLAG': fs('flag', 1) or 'Y', 'CLOSED': fs('closed', 1) or 'N', 'COUNTERSALE': 'Y' if form.get('countersale') == 'Y' else 'N', 'CUSTOMERCATEGORY': fi('customercategory'), 'BYSALESMAN': fi('bysalesman'), 'ROUTENO': fi('routeno'), 'LOCATIONCODE': fi('locationcode'), 'STREET': fs('street'), 'ZONE': fs('zone', 100), 'POBOX': fs('pobox', 50), 'CRNO': fs('crno', 250), 'RECEIVABLEACCOUNT': _cc_account_value_or_default(form.get('receivableaccount'), 'customer_receivable'), 'SALESACCOUNT': _cc_account_value_or_default(form.get('salesaccount'), 'customer_sales'), 'VATOUTPUTACCOUNT': _cc_account_value_or_default(form.get('vatoutputaccount'), 'customer_vat_output'), 'ADVANCEACCOUNT': _cc_account_value_or_default(form.get('advanceaccount'), 'customer_advance'), 'EMPLOYEECODE': fi('employeecode') or None, 'REASON': fs('reason'), 'OTHERREASON': fs('otherreason'), 'CLOSEDREASON': fs('closedreason'), 'CUSTOMERSTATUS': 'Y', 'CREATEDSTATUS': 'Y'}
    ccode_in = (form.get('ccode') or '').strip()
    if not ccode_in:
        flash('C Code is required. Select a target branch and click Next C Code (or use the pre-filled code), then save.', 'error')
        if from_cr and from_cr.isdigit():
            return redirect(url_for('ho.customer_central_form', from_cr=from_cr))
        return redirect(url_for('ho.customer_central_form'))
    base_col_map['CCODE'] = ccode_in[:20]
    acc_err = _cc_validate_mandatory_gl_accounts(base_col_map)
    if acc_err:
        flash(acc_err, 'error')
        if from_cr and from_cr.isdigit():
            return redirect(url_for('ho.customer_central_form', from_cr=from_cr))
        return redirect(url_for('ho.customer_central_form'))
    out = _ho_execute_central_customer_saves(base_col_map, target_tenants, username, from_cr)
    saved = out['saved']
    saved_codes = out['saved_codes']
    errors = out['errors']
    if saved:
        flash(f"Customer saved to: {', '.join(saved)}." + (f" Errors: {'; '.join(errors)}" if errors else ''), 'success')
    else:
        flash(f"Failed to save: {'; '.join(errors)}", 'error')
    if from_cr:
        return redirect(url_for('ho.customer_request', tab='converted'))
    return redirect(url_for('ho.customer_central'))

def _customer_central_search_duplicate_customers(raw_name: str, exact_vals: Optional[Dict[str, str]]=None) -> List[Dict[str, Any]]:
    """Search all tenant DBs for name / contact overlaps; sets matched_fields on exact equality."""
    if exact_vals is None:
        exact_vals = {}
    ALWAYS_FETCH = ['CUSTOMERCODE', 'CCODE', 'CUSTOMERNAME', 'MOBILE', 'TELEPHONE', 'WHATSAPP', 'CRNO', 'QATARID', 'INVOICECODE', 'FLAG']
    all_tenants = get_active_tenants_with_network()
    results: List[Dict[str, Any]] = []
    for t in all_tenants:
        tid = t.get('tenant_id', '')
        if not tid:
            continue
        try:
            with _get_tenant_connection(tid) as conn:
                with conn.cursor() as cur:
                    cust_tbl = _detect_customer_table(cur)
                    if not cust_tbl:
                        continue
                    cur.execute('SELECT column_name FROM user_tab_columns WHERE table_name=:t', {'t': cust_tbl})
                    existing_cols = {r[0] for r in cur.fetchall()}
                    sel = [c for c in ALWAYS_FETCH if c in existing_cols]
                    SEARCH_COLS = [c for c in ('CUSTOMERNAME', 'TELEPHONE', 'MOBILE', 'WHATSAPP', 'QATARID', 'CRNO') if c in existing_cols]
                    search_values: Dict[str, str] = {}
                    if raw_name:
                        search_values['sv_name'] = raw_name.upper()
                    for fld, val in exact_vals.items():
                        if val:
                            search_values[f'sv_{fld}'] = val.upper()
                    params: Dict[str, str] = {}
                    mix_clauses: List[str] = []
                    for pkey, sval in search_values.items():
                        like_key = f'{pkey}_like'
                        params[like_key] = f'%{sval}%'
                        col_clauses = [f'UPPER(TRIM({col})) LIKE :{like_key}' for col in SEARCH_COLS]
                        if col_clauses:
                            mix_clauses.append(f"({' OR '.join(col_clauses)})")
                    where_sql = ' OR '.join(mix_clauses) if mix_clauses else '1=0'
                    cur.execute(f"SELECT {', '.join(sel)} FROM {cust_tbl} WHERE {where_sql} ORDER BY CUSTOMERCODE", params)
                    col_names = [d[0].lower() for d in cur.description]
                    for row in cur.fetchall() or []:
                        rec = dict(zip(col_names, row))
                        rec['tenant_id'] = tid
                        rec['tenant_name'] = t.get('display_name') or tid
                        matched_fields: List[str] = []
                        all_search_vals = [raw_name.upper()] + [v for v in exact_vals.values() if v]
                        for db_col in ('customername', 'telephone', 'mobile', 'whatsapp', 'qatarid', 'crno'):
                            _v = rec.get(db_col)
                            db_val = ('' if _v is None else str(_v)).strip().upper()
                            if not db_val:
                                continue
                            for sv in all_search_vals:
                                if sv and db_val == sv:
                                    matched_fields.append(db_col)
                                    break
                        rec['matched_fields'] = matched_fields
                        results.append(rec)
        except Exception as _ex:
            import traceback
            print(f'[duplicate search] tenant={tid} error: {_ex}')
            traceback.print_exc()
            continue
    results.sort(key=lambda r: (0 if r.get('matched_fields') else 1, str(r.get('tenant_id', '')), str(r.get('customername', ''))))
    return results

@bp.route('/ho/customer-central/check-name', methods=['POST'])
def customer_central_check_name():
    """Search all tenant DBs for customers matching the given name (fuzzy).
    Also accepts exact-match fields (telephone, mobile, whatsappno, crno, qatarid)
    so the client can flag exact-field duplicates.
    """
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    data = request.get_json(silent=True) or {}
    raw_name = (data.get('name') or '').strip()
    if not raw_name:
        return jsonify({'success': False, 'error': 'Name is required'}, 400)
    exact_vals = {'telephone': (data.get('telephone') or '').strip().upper(), 'mobile': (data.get('mobile') or '').strip().upper(), 'whatsapp': (data.get('whatsapp') or '').strip().upper(), 'crno': (data.get('crno') or '').strip().upper(), 'qatarid': (data.get('qatarid') or '').strip().upper()}
    results = _customer_central_search_duplicate_customers(raw_name, exact_vals)
    return jsonify({'success': True, 'count': len(results), 'results': results})

@bp.route('/ho/customer-central/next-code')
def customer_central_next_code():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    tenant = (request.args.get('tenant') or '').strip()
    if not tenant:
        return jsonify({'success': False, 'error': 'tenant required'}, 400)
    code, ccode = _cc_next_code(tenant or None)
    return jsonify({'success': True, 'next_code': code, 'ccode': ccode})

def _user_can_customer_request_ai_auto(username: str) -> bool:
    u = (username or '').strip()
    if not u:
        return False
    if u.lower() in {x.lower() for x in PRIVILEGED_USERS}:
        return True
    return get_user_customer_creation(u) == 'Y'

def _cr_temp_row_to_base_col_map(req: dict) -> Dict[str, Any]:
    """Map CUSTOMERTEMP row (lowercase keys) to the same field dict as customer central save."""

    def gv(k: str) -> Any:
        v = req.get(k)
        if v is None:
            v = req.get(k.lower())
        return v

    def fs(k: str, n: int=200) -> str:
        return str(gv(k) or '').strip()[:n]

    def fi(k: str, d: int=0) -> int:
        try:
            v = gv(k)
            if v is None or (isinstance(v, str) and (not str(v).strip())):
                return d
            return int(v)
        except Exception:
            return d
    ct = (fs('customertype', 10) or 'P').strip().upper()
    if ct in ('STAFF', 'S'):
        ct_char = 'S'
    else:
        ct_char = 'P'
    sex = (fs('sex', 1) or 'M').upper()[:1]
    if sex not in ('M', 'F'):
        sex = 'M'
    cs_raw = str(gv('countersale') or '').strip().upper()
    countersale = 'Y' if cs_raw == 'Y' else 'N'
    emp = fi('employeecode')
    out: Dict[str, Any] = {'CUSTOMERNAME': fs('customername').upper(), 'CUSTOMERTYPE': ct_char, 'DESIGNATION': fs('designation', 100), 'SEX': sex, 'ADDRESS': fs('address'), 'NATIONALITY': fs('nationality', 100), 'TELEPHONE': fs('telephone', 15), 'FAX': fs('fax', 15), 'MOBILE': fs('mobile', 15), 'EMAIL': fs('email', 150), 'WHATSAPP': fs('whatsapp', 20), 'QATARID': fs('qatarid', 50), 'CREDITLIMIT': fi('creditlimit'), 'CREDITTERMS': fi('creditterms'), 'DUEDAYS': fi('creditterms'), 'CURRENTCREDITAMOUNT': 0, 'SALESMANCODE': fi('salesmancode'), 'INVOICECODE': fi('invoicecode', 1), 'FLAG': (fs('flag', 1) or 'Y')[:1], 'CLOSED': (fs('closed', 1) or 'N')[:1], 'COUNTERSALE': countersale, 'CUSTOMERCATEGORY': fi('customercategory'), 'BYSALESMAN': fi('bysalesman'), 'ROUTENO': fi('routeno'), 'LOCATIONCODE': fi('locationcode'), 'STREET': fs('street'), 'ZONE': fs('zone', 100), 'POBOX': fs('pobox', 50), 'CRNO': fs('crno', 250), 'RECEIVABLEACCOUNT': _cc_account_value_or_default(gv('receivableaccount'), 'customer_receivable'), 'SALESACCOUNT': _cc_account_value_or_default(gv('salesaccount'), 'customer_sales'), 'VATOUTPUTACCOUNT': _cc_account_value_or_default(gv('vatoutputaccount'), 'customer_vat_output'), 'ADVANCEACCOUNT': _cc_account_value_or_default(gv('advanceaccount'), 'customer_advance'), 'EMPLOYEECODE': emp if emp else None, 'REASON': fs('reason'), 'OTHERREASON': fs('otherreason'), 'CLOSEDREASON': fs('closedreason'), 'CUSTOMERSTATUS': 'Y', 'CREATEDSTATUS': 'Y'}
    ac_ccode = gv('assignedccode')
    if ac_ccode is not None and str(ac_ccode).strip():
        out['CCODE'] = str(ac_ccode).strip()[:20]
    return out

def _customer_request_next_pending_code_for_ai(ho_tenant_id: str) -> Optional[int]:
    _ensure_customer_request_temp_table(ho_tenant_id)
    with _get_tenant_connection(ho_tenant_id) as conn:
        with conn.cursor() as cur:
            for sql in (f"SELECT MIN(CUSTOMERCODE) FROM {CUSTOMER_TEMP_TABLE} WHERE UPPER(NVL(STATUS,'PENDING'))='PENDING' AND NVL(AI_DUP_FLAG,'N')<>'Y'", f"SELECT MIN(CUSTOMERCODE) FROM {CUSTOMER_TEMP_TABLE} WHERE UPPER(NVL(STATUS,'PENDING'))='PENDING'"):
                try:
                    cur.execute(sql)
                    row = cur.fetchone()
                    if row and row[0] is not None:
                        return int(row[0])
                except Exception:
                    continue
    return None

def _customer_request_revert_converting_to_pending(ho_tenant_id: str, customercode: int, username: str) -> None:
    """If AI auto-convert failed after claim, put the row back to PENDING for retry or manual action."""
    try:
        u = str(username or '')[:100]
        _ensure_customer_request_temp_table(ho_tenant_id)
        with _get_tenant_connection(ho_tenant_id) as conn:
            with conn.cursor() as cur:
                cur.execute(f"UPDATE {CUSTOMER_TEMP_TABLE} SET STATUS = 'PENDING', UPDATEDBY = :u, UPDATEDDATE = SYSDATE WHERE CUSTOMERCODE = :cc AND UPPER(NVL(STATUS,'')) = 'CONVERTING'", {'u': u, 'cc': int(customercode)})
            conn.commit()
    except Exception as e:
        print(f'[_customer_request_revert_converting_to_pending] {e}')

def _customer_request_claim_next_pending_for_ai(ho_tenant_id: str, username: str) -> Optional[int]:
    """Atomically reserve one PENDING request for AI processing (status CONVERTING).
    Stops duplicate branch CUSTOMER rows when multiple browser tabs (or pollers) POST ai-process
    for the same pending request."""
    u = str(username or '')[:100]
    _ensure_customer_request_temp_table(ho_tenant_id)

    def _sub_min(extra_sql: str) -> str:
        wh = "UPPER(NVL(x.STATUS,'PENDING'))='PENDING'"
        if extra_sql.strip():
            wh = f'{wh} {extra_sql.strip()}'
        return f'SELECT MIN(x.CUSTOMERCODE) FROM {CUSTOMER_TEMP_TABLE} x WHERE {wh}'
    for extra_sql in ("AND NVL(x.AI_DUP_FLAG,'N')<>'Y'", ''):
        sub_min = _sub_min(extra_sql)
        upd_base = f"UPDATE {CUSTOMER_TEMP_TABLE} t SET t.STATUS = 'CONVERTING', t.UPDATEDBY = :u, t.UPDATEDDATE = SYSDATE WHERE t.CUSTOMERCODE = ({sub_min}) AND UPPER(NVL(t.STATUS,'PENDING'))='PENDING'"
        try:
            with _get_tenant_connection(ho_tenant_id) as conn:
                with conn.cursor() as cur:
                    cc_out = cur.var(int)
                    try:
                        cur.execute(f'{upd_base} RETURNING t.CUSTOMERCODE INTO :cc_out', {'u': u, 'cc_out': cc_out})
                    except Exception as ex_r:
                        cur.execute(upd_base, {'u': u})
                        n = int(cur.rowcount or 0)
                        conn.commit()
                        if n <= 0:
                            if extra_sql:
                                break
                            return None
                        cur.execute(f"SELECT MIN(CUSTOMERCODE) FROM {CUSTOMER_TEMP_TABLE} WHERE UPPER(NVL(STATUS,'PENDING'))='CONVERTING' AND UPDATEDBY = :u", {'u': u})
                        r2 = cur.fetchone()
                        if r2 and r2[0] is not None:
                            return int(r2[0])
                        if extra_sql:
                            break
                        return None
                    n = int(cur.rowcount or 0)
                    conn.commit()
                    if n <= 0:
                        if extra_sql:
                            break
                        return None
                    raw = cc_out.getvalue()
                    if raw is None:
                        if extra_sql:
                            break
                        return None
                    if isinstance(raw, (list, tuple)):
                        return int(raw[0]) if len(raw) else None
                    return int(raw)
        except Exception as ex:
            if extra_sql:
                print(f'[_customer_request_claim_next_pending_for_ai] AI_DUP pass: {ex}')
                continue
            print(f'[_customer_request_claim_next_pending_for_ai] {ex}')
            return None
    return None

def _customer_request_reject_ai_duplicate(ho_tenant_id: str, customercode: int, username: str, duplicate_rows: List[Dict[str, Any]]) -> str:
    """Set STATUS=REJECTED, REJECTCOMMENT with branch/code detail, AI_DUP_FLAG=Y. Returns the comment text."""
    exact_rows = [r for r in duplicate_rows or [] if r.get('matched_fields') or []]
    detail_parts: List[str] = []
    for r in exact_rows[:6]:
        tid = str(r.get('tenant_id') or '').strip()
        tname = str(r.get('tenant_name') or tid or '').strip()
        cust_code = r.get('customercode')
        cname = str(r.get('customername') or '').strip()
        fields = ', '.join(r.get('matched_fields') or [])
        detail_parts.append(f'branch {tname or tid} ({tid}) customer {cust_code}' + (f' — matched: {fields}' if fields else '') + (f' [{cname[:40]}]' if cname else ''))
    if detail_parts:
        cmt = 'AI rejected: duplicate in same branch (tenant) database. ' + ' | '.join(detail_parts)
    else:
        cmt = 'AI rejected: duplicate in same branch tenant (exact field match in that branch).'
    if len(cmt) > 1000:
        cmt = cmt[:997] + '...'
    try:
        with _get_tenant_connection(ho_tenant_id) as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute(f"UPDATE {CUSTOMER_TEMP_TABLE} SET STATUS='REJECTED', REJECTCOMMENT=SUBSTR(:cmt, 1, 1000), AI_DUP_FLAG='Y', UPDATEDBY=:u, UPDATEDDATE=SYSDATE WHERE CUSTOMERCODE=:cc", {'cmt': cmt, 'u': username, 'cc': customercode})
                except Exception:
                    cur.execute(f"UPDATE {CUSTOMER_TEMP_TABLE} SET STATUS='REJECTED', REJECTCOMMENT=SUBSTR(:cmt, 1, 1000), UPDATEDBY=:u, UPDATEDDATE=SYSDATE WHERE CUSTOMERCODE=:cc", {'cmt': cmt, 'u': username, 'cc': customercode})
            conn.commit()
    except Exception as e:
        print(f'[_customer_request_reject_ai_duplicate] {e}')
    return cmt

def _customer_request_process_ai_once(username: str) -> Dict[str, Any]:
    """One pending request: duplicate check on the request's branch tenant only; exact match there → AI reject; else central save."""
    ho = 'HO'
    if not _user_can_customer_request_ai_auto(username):
        return {'ok': False, 'error': 'forbidden'}
    if not _get_cr_ai_auto_convert_enabled(ho):
        return {'ok': True, 'action': 'idle', 'message': 'AI auto-convert is off (organization setting).'}
    cc = _customer_request_claim_next_pending_for_ai(ho, username)
    if not cc:
        return {'ok': True, 'action': 'idle', 'message': 'No pending requests.'}
    req = _get_customer_request_row(ho, int(cc)) or {}
    if not req:
        _customer_request_revert_converting_to_pending(ho, int(cc), username)
        return {'ok': True, 'action': 'skip', 'customercode': cc, 'message': 'Request row not found after claim.'}
    st = str(req.get('status') or '').strip().upper()
    if st != 'CONVERTING':
        return {'ok': True, 'action': 'skip', 'customercode': cc, 'message': 'Request is not reserved for AI (concurrent change or data lag).'}
    raw_name = str(req.get('customername') or '').strip()
    if not raw_name:
        _customer_request_revert_converting_to_pending(ho, int(cc), username)
        return {'ok': True, 'action': 'skip', 'customercode': cc, 'message': 'Missing customer name.'}
    branch = str(req.get('branch') or '').strip()
    if not branch:
        _customer_request_revert_converting_to_pending(ho, int(cc), username)
        return {'ok': True, 'action': 'skip', 'customercode': cc, 'message': 'Missing branch (tenant) on request.'}
    exact_vals = {'telephone': str(req.get('telephone') or '').strip().upper(), 'mobile': str(req.get('mobile') or '').strip().upper(), 'whatsapp': str(req.get('whatsapp') or '').strip().upper(), 'crno': str(req.get('crno') or '').strip().upper(), 'qatarid': str(req.get('qatarid') or '').strip().upper()}
    dups = _customer_central_search_duplicate_customers(raw_name, exact_vals)
    branch_key = branch.strip().upper()
    same_tenant_dups = [r for r in dups if str(r.get('tenant_id') or '').strip().upper() == branch_key]
    exact_dups = [r for r in same_tenant_dups if r.get('matched_fields') or []]
    if exact_dups:
        cmt = _customer_request_reject_ai_duplicate(ho, int(cc), username, exact_dups)
        return {'ok': True, 'action': 'ai_rejected', 'customercode': cc, 'message': cmt, 'duplicates': len(exact_dups)}
    base_map = _cr_temp_row_to_base_col_map(req)
    acc_err = _cc_validate_mandatory_gl_accounts(base_map)
    if acc_err:
        _customer_request_revert_converting_to_pending(ho, int(cc), username)
        return {'ok': False, 'action': 'error', 'customercode': cc, 'error': acc_err, 'message': acc_err}
    out = _ho_execute_central_customer_saves(base_map, [branch], username, str(cc), cr_success_comment='AI Converted')
    if out.get('saved'):
        return {'ok': True, 'action': 'converted', 'customercode': cc, 'message': f'Saved to {branch} and central (auto).', 'tenants': out['saved']}
    err_txt = '; '.join(out.get('errors') or [])
    _customer_request_revert_converting_to_pending(ho, int(cc), username)
    return {'ok': False, 'action': 'error', 'customercode': cc, 'error': err_txt or 'Save failed.'}

def _cc_fetch_chart_of_accounts_for_tenant(tenant: str) -> List[Dict[str, Any]]:
    """Postable Chart of Accounts rows from a tenant DB for Customer Central pickers."""
    tid = (tenant or '').strip()
    if not tid:
        return []
    tbl_candidates = ['CHARTOFACCOUNTS', 'CHART_OF_ACCOUNTS', 'COA']
    tbl = next((t for t in tbl_candidates if _cc_table_exists(tid, t)), None)
    if not tbl:
        return []
    code_col = _cc_detect_column(tid, tbl, ['CODE', 'ACCOUNTCODE', 'ACCOUNT_CODE'])
    name_col = _cc_detect_column(tid, tbl, ['NAME', 'ACCOUNTNAME', 'ACCOUNT_NAME'])
    type_col = _cc_detect_column(tid, tbl, ['TYPE', 'ACCOUNTTYPE', 'GROUPTYPE'])
    postable_col = _cc_detect_column(tid, tbl, ['IS_POSTABLE', 'ISPOSTABLE', 'POSTABLE'])
    if not code_col:
        return []
    wh = f"WHERE {postable_col} = 'Y'" if postable_col else ''
    nexpr = name_col if name_col else 'CAST(NULL AS VARCHAR2(240))'
    texpr = type_col if type_col else 'CAST(NULL AS VARCHAR2(240))'
    try:
        with _get_tenant_connection(tid) as conn:
            with conn.cursor() as cur:
                cur.execute(f'SELECT {code_col} AS code, {nexpr} AS name, {texpr} AS typ FROM {tbl} {wh} ORDER BY {code_col}')
                rows = cur.fetchall() or []
                out = []
                for r in rows:
                    out.append({'code': r[0], 'name': str(r[1] or '') if len(r) > 1 and r[1] is not None else '', 'type': str(r[2] or '') if len(r) > 2 and r[2] is not None else ''})
                return out
    except Exception as ex:
        print(f'[_cc_fetch_chart_of_accounts_for_tenant] {tid}: {ex}')
        return []

def _cc_branch_query(tenant: str, sql: str, params: dict=None):
    """Run a query against a specific tenant DB and return list of dicts."""
    with _get_tenant_connection(tenant) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or {})
            cols = [d[0].lower() for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall() or []]

def _cc_table_exists(tenant: str, table: str) -> bool:
    try:
        with _get_tenant_connection(tenant) as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT COUNT(*) FROM user_tables WHERE table_name = :t', {'t': table.upper()})
                return int((cur.fetchone() or [0])[0] or 0) > 0
    except Exception:
        return False

def _cc_detect_column(tenant: str, table: str, candidates: list) -> str | None:
    try:
        with _get_tenant_connection(tenant) as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT column_name FROM user_tab_columns WHERE table_name = :t', {'t': table.upper()})
                existing = {str(r[0]).upper() for r in cur.fetchall() or []}
                for c in candidates:
                    if c.upper() in existing:
                        return c.upper()
    except Exception:
        pass
    return None

def _cc_fetch_popup_list(tenant: str, table_candidates: list, code_candidates: list, name_candidates: list, where_extra: str='') -> list:
    """Generic popup list fetcher from a tenant DB using table/column detection.

    Uses a single DB connection to avoid connection spikes (ORA-12516).
    """
    try:
        with _get_tenant_connection(tenant) as conn:
            with conn.cursor() as cur:
                existing_tables = set()
                cur.execute('SELECT table_name FROM user_tables')
                for r in cur.fetchall() or []:
                    if r and r[0]:
                        existing_tables.add(str(r[0]).upper())
                tbl = next((t for t in table_candidates if str(t).upper() in existing_tables), None)
                if not tbl:
                    return []
                cur.execute('SELECT column_name FROM user_tab_columns WHERE table_name = :t', {'t': str(tbl).upper()})
                existing_cols = {str(r[0]).upper() for r in cur.fetchall() or []}
                code_col = next((c.upper() for c in code_candidates if c.upper() in existing_cols), None)
                name_col = next((c.upper() for c in name_candidates if c.upper() in existing_cols), None)
                if not code_col:
                    return []
                sel = f'{code_col} AS code, {name_col} AS name' if name_col else f'{code_col} AS code, NULL AS name'
                order = f'ORDER BY {(name_col if name_col else code_col)}'
                where = f'WHERE {where_extra}' if where_extra else ''
                cur.execute(f'SELECT {sel} FROM {tbl} {where} {order}')
                rows = cur.fetchall() or []
                return [{'code': r[0], 'name': str(r[1] or '') if r[1] is not None else ''} for r in rows]
    except Exception:
        return []

def _resolve_effective_tenant(preferred_tenant: str='') -> str:
    """Resolve tenant from explicit value, session, then user mapping."""
    tenant = (preferred_tenant or '').strip()
    if tenant:
        return tenant
    tenant = str(session.get('tenant_id') or '').strip()
    if tenant:
        return tenant
    user = str(session.get('user') or '').strip()
    if user:
        try:
            return str(get_user_tenant_id(user) or '').strip()
        except Exception:
            return ''
    return ''

@bp.route('/ho/customer-central/api/salesman-list')
def cc_api_salesman_list():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    tenant = _resolve_effective_tenant(request.args.get('tenant'))
    if not tenant:
        return jsonify({'success': False, 'salesmen': []})
    try:
        rows = _cc_fetch_popup_list(tenant=tenant, table_candidates=['SALESMAN1', 'SALESMAN', 'TBSALESMAN', 'TBRSALESMAN'], code_candidates=['SALESMANCODE', 'CODE'], name_candidates=['SALESMANNAME', 'NAME'])
        print(f'[cc_api_salesman_list] tenant={tenant} rows={len(rows)}')
        return jsonify({'success': True, 'salesmen': rows})
    except Exception as e:
        print(f'[cc_api_salesman_list] tenant={tenant} error={e}')
        return jsonify({'success': False, 'error': str(e)}, 500)

@bp.route('/ho/customer-central/api/category-list')
def cc_api_category_list():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    tenant = _resolve_effective_tenant(request.args.get('tenant'))
    if not tenant:
        return jsonify({'success': False, 'categories': []})
    try:
        rows = _cc_fetch_popup_list(tenant=tenant, table_candidates=['TBLCUSTOMERCATEGORY', 'CUSTOMERCATEGORY', 'CUSTOMER_CATEGORY'], code_candidates=['CATEGORYCODE', 'CODE'], name_candidates=['CATEGORYNAME', 'NAME'])
        print(f'[cc_api_category_list] tenant={tenant} rows={len(rows)}')
        return jsonify({'success': True, 'categories': rows})
    except Exception as e:
        print(f'[cc_api_category_list] tenant={tenant} error={e}')
        return jsonify({'success': False, 'error': str(e)}, 500)

@bp.route('/ho/customer-central/api/route-list')
def cc_api_route_list():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    tenant = _resolve_effective_tenant(request.args.get('tenant'))
    if not tenant:
        return jsonify({'success': False, 'routes': []})
    try:
        rows = _cc_fetch_popup_list(tenant=tenant, table_candidates=['TBLROUTES', 'ROUTEMASTER', 'ROUTES'], code_candidates=['ROUTENO', 'CODE'], name_candidates=['ROUTENAME', 'NAME'])
        print(f'[cc_api_route_list] tenant={tenant} rows={len(rows)}')
        return jsonify({'success': True, 'routes': rows})
    except Exception as e:
        print(f'[cc_api_route_list] tenant={tenant} error={e}')
        return jsonify({'success': False, 'error': str(e)}, 500)

@bp.route('/ho/customer-central/api/employee-list')
def cc_api_employee_list():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    tenant = _resolve_effective_tenant(request.args.get('tenant'))
    if not tenant:
        return jsonify({'success': False, 'employees': []})
    try:
        rows = _cc_fetch_popup_list(tenant=tenant, table_candidates=['EMPLOYEE1', 'EMPLOYEE'], code_candidates=['EMPLOYEECODE', 'CODE'], name_candidates=['EMPLOYEENAME', 'NAME'])
        print(f'[cc_api_employee_list] tenant={tenant} rows={len(rows)}')
        return jsonify({'success': True, 'employees': rows})
    except Exception as e:
        print(f'[cc_api_employee_list] tenant={tenant} error={e}')
        return jsonify({'success': False, 'error': str(e)}, 500)

@bp.route('/ho/customer-central/api/chart-of-accounts-branch')
def cc_api_chart_accounts_list():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    tenant = _resolve_effective_tenant(request.args.get('tenant'))
    if not tenant:
        return jsonify({'success': False, 'error': 'tenant_required', 'accounts': []}, 400)
    rows = _cc_fetch_chart_of_accounts_for_tenant(tenant)
    return jsonify({'success': True, 'accounts': rows})

@bp.route('/ho/customer-request')
def customer_request():
    t0 = time.perf_counter()
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    ho_tenant_id = 'HO'
    t_ensure = time.perf_counter()
    _ensure_customer_request_temp_table(ho_tenant_id)
    ensure_ms = _cr_perf_ms(t_ensure)
    selected_tab = (request.args.get('tab') or 'pending').strip().lower()
    if selected_tab not in ('pending', 'rejected', 'converted'):
        selected_tab = 'pending'
    search = (request.args.get('search') or '').strip()
    branch_filter = (request.args.get('branch') or '').strip()
    invoice_filter = (request.args.get('invoice') or '').strip()
    date_from = (request.args.get('date_from') or '').strip()
    date_to = (request.args.get('date_to') or '').strip()
    current_user = str(session.get('user') or '').strip()
    current_tenant = _resolve_effective_tenant().upper()
    is_privileged = current_user.lower() in {u.lower() for u in PRIVILEGED_USERS}
    can_customer_creation = get_user_customer_creation(current_user) == 'Y'
    if is_privileged or can_customer_creation:
        tenant_scope = ''
    else:
        tenant_scope = current_tenant or '__NO_TENANT__'
    t_rows = time.perf_counter()
    rows = _get_customer_request_rows_by_status(ho_tenant_id, selected_tab, search=search, branch=branch_filter, branch_scope=tenant_scope, invoice_filter=invoice_filter, date_from=date_from, date_to=date_to)
    rows_ms = _cr_perf_ms(t_rows)
    t_counts = time.perf_counter()
    counts = _get_customer_request_status_counts(ho_tenant_id, branch_scope=tenant_scope)
    counts_ms = _cr_perf_ms(t_counts)
    t_ai = time.perf_counter()
    _ensure_customer_alert_control_table(ho_tenant_id)
    cr_ai_auto_convert = _get_cr_ai_auto_convert_enabled(ho_tenant_id)
    _ = _cr_perf_ms(t_ai)
    t_branch = time.perf_counter()
    try:
        branch_list = _safe_rows_auth("SELECT tenant_id, locationname FROM tenant_databases WHERE tenant_id != 'HO' ORDER BY locationname", {}) or []
    except Exception:
        branch_list = []
    branch_ms = _cr_perf_ms(t_branch)
    print(f"[perf][customer_request] total_ms={_cr_perf_ms(t0)} ensure_ms={ensure_ms} rows_ms={rows_ms} counts_ms={counts_ms} branch_ms={branch_ms} rows={len(rows)} tab={selected_tab} user={current_user or '-'}")
    return render_template('ho/ho_customer_request_list.html', selected_tab=selected_tab, rows=rows, counts=counts, search=search, branch_filter=branch_filter, invoice_filter=invoice_filter, date_from=date_from, date_to=date_to, branch_list=branch_list, cr_ai_auto_convert=cr_ai_auto_convert)

@bp.route('/ho/customer-request/new')
def customer_request_form():
    t0 = time.perf_counter()
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    from db import get_all_chart_of_accounts, ensure_default_party_accounts, DEFAULT_PARTY_ACCOUNTS
    ho_tenant_id = 'HO'
    current_tenant_id = _resolve_effective_tenant()
    t_ensure = time.perf_counter()
    _ensure_customer_request_temp_table(ho_tenant_id)
    ensure_ms = _cr_perf_ms(t_ensure)
    customercode = request.args.get('customercode', '').strip()
    view_only = request.args.get('view', '0').strip() == '1'
    temp_row = {}
    t_row = time.perf_counter()
    if customercode and customercode.isdigit():
        temp_row = _get_customer_request_row(ho_tenant_id, int(customercode))
    row_ms = _cr_perf_ms(t_row)
    t_next = time.perf_counter()
    next_code = _get_next_customer_request_code(ho_tenant_id) if not temp_row else ''
    next_ms = _cr_perf_ms(t_next)
    saved_loc_code = str(temp_row.get('locationcode') or session.get('location_code') or '').strip()
    saved_loc_name = ''
    t_loc = time.perf_counter()
    if saved_loc_code:
        try:
            loc_rows = _safe_rows('SELECT LOCATIONNAME FROM LOCATIONMASTER WHERE LOCATIONCODE = :lc', {'lc': saved_loc_code})
            saved_loc_name = loc_rows[0]['locationname'] if loc_rows else ''
        except Exception as e:
            print(f'[customer_request_form] location name lookup error: {e}')
    loc_ms = _cr_perf_ms(t_loc)
    chart_accounts = []
    default_accounts = {}
    accounts_ms = 0
    if not temp_row and current_tenant_id:
        t_acc = time.perf_counter()
        try:
            chart_accounts, default_accounts = _cr_get_cached_form_accounts(tenant_key=current_tenant_id, get_all_chart_of_accounts_fn=get_all_chart_of_accounts, ensure_default_party_accounts_fn=ensure_default_party_accounts, default_party_accounts=dict(DEFAULT_PARTY_ACCOUNTS))
        except Exception:
            chart_accounts = []
            default_accounts = dict(DEFAULT_PARTY_ACCOUNTS)
        accounts_ms = _cr_perf_ms(t_acc)
    elif not temp_row:
        default_accounts = dict(DEFAULT_PARTY_ACCOUNTS)
    t_names = time.perf_counter()
    from addons.customer.controllers.routes import _get_salesman_name, _get_category_name, _get_route_name, _get_employee_name
    salesman_name = _get_salesman_name(temp_row.get('salesmancode')) if temp_row else ''
    by_salesman_name = _get_salesman_name(temp_row.get('bysalesman')) if temp_row else ''
    category_name = _get_category_name(temp_row.get('customercategory')) if temp_row else ''
    route_name = _get_route_name(temp_row.get('routeno')) if temp_row else ''
    employee_name = _get_employee_name(temp_row.get('employeecode')) if temp_row else ''
    names_ms = _cr_perf_ms(t_names)
    t_branch_name = time.perf_counter()
    branch_name = _ho_get_branch_name_by_dbkey(ho_tenant_id, current_tenant_id)
    branch_name_ms = _cr_perf_ms(t_branch_name)
    row_status = str(temp_row.get('status') or 'PENDING').strip().upper() if temp_row else 'PENDING'
    if view_only:
        back_tab = 'rejected' if row_status == 'REJECTED' else 'converted'
    else:
        back_tab = 'pending'
    cr_reject_comment = (temp_row.get('rejectcomment') or '').strip() if temp_row else ''
    if current_tenant_id:
        api_salesman_url = url_for('ho.cc_api_salesman_list', tenant=current_tenant_id)
        api_category_url = url_for('ho.cc_api_category_list', tenant=current_tenant_id)
        api_route_url = url_for('ho.cc_api_route_list', tenant=current_tenant_id)
        api_employee_url = url_for('ho.cc_api_employee_list', tenant=current_tenant_id)
    else:
        api_salesman_url = url_for('ho.ho_api_salesman_list')
        api_category_url = url_for('ho.ho_api_category_list')
        api_route_url = url_for('ho.ho_api_route_list')
        api_employee_url = url_for('ho.ho_api_employee_list')
    preload_salesmen = []
    preload_categories = []
    preload_routes = []
    preload_employees = []
    if current_tenant_id:
        try:
            preload_salesmen = _cc_fetch_popup_list(tenant=current_tenant_id, table_candidates=['SALESMAN1', 'SALESMAN', 'TBSALESMAN', 'TBRSALESMAN'], code_candidates=['SALESMANCODE', 'CODE'], name_candidates=['SALESMANNAME', 'NAME'])
            preload_categories = _cc_fetch_popup_list(tenant=current_tenant_id, table_candidates=['TBLCUSTOMERCATEGORY', 'CUSTOMERCATEGORY', 'CUSTOMER_CATEGORY'], code_candidates=['CATEGORYCODE', 'CODE'], name_candidates=['CATEGORYNAME', 'NAME'])
            preload_routes = _cc_fetch_popup_list(tenant=current_tenant_id, table_candidates=['TBLROUTES', 'ROUTEMASTER', 'ROUTES'], code_candidates=['ROUTENO', 'CODE'], name_candidates=['ROUTENAME', 'NAME'])
            preload_employees = _cc_fetch_popup_list(tenant=current_tenant_id, table_candidates=['EMPLOYEE1', 'EMPLOYEE'], code_candidates=['EMPLOYEECODE', 'CODE'], name_candidates=['EMPLOYEENAME', 'NAME'])
        except Exception:
            pass
    print(f"[perf][customer_request_form] total_ms={_cr_perf_ms(t0)} ensure_ms={ensure_ms} row_ms={row_ms} next_ms={next_ms} loc_ms={loc_ms} accounts_ms={accounts_ms} names_ms={names_ms} branch_name_ms={branch_name_ms} edit={('Y' if temp_row else 'N')} user={session.get('user') or '-'}")
    return render_template('ho/customer_form.html', customer=temp_row if temp_row else None, location_code=saved_loc_code, location_name=saved_loc_name, next_customer_code=customercode or str(next_code), locations=[], chart_accounts=chart_accounts, default_accounts=default_accounts, is_edit=bool(temp_row), salesman_name=salesman_name, by_salesman_name=by_salesman_name, category_name=category_name, route_name=route_name, employee_name=employee_name, customer_request_mode=True, customer_request_view_only=view_only, customer_request_customercode=int(customercode) if customercode and customercode.isdigit() else None, customer_request_save_url=url_for('ho.customer_request_save'), customer_request_list_url=url_for('ho.customer_request', tab=back_tab), cr_branch_name=branch_name, cr_tenant_id=current_tenant_id, cr_reject_comment=cr_reject_comment, api_salesman_url=api_salesman_url, api_category_url=api_category_url, api_route_url=api_route_url, api_employee_url=api_employee_url, api_request_accounts_url=url_for('ho.customer_request_accounts_api'), api_location_url=url_for('ho.ho_api_location_list'), preload_salesmen=preload_salesmen, preload_categories=preload_categories, preload_routes=preload_routes, preload_employees=preload_employees)

@bp.route('/ho/customer-request/api/accounts')
def customer_request_accounts_api():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    from db import get_all_chart_of_accounts, ensure_default_party_accounts, DEFAULT_PARTY_ACCOUNTS
    tenant_id = _resolve_effective_tenant()
    try:
        chart_accounts, default_accounts = _cr_get_cached_form_accounts(tenant_key=tenant_id, get_all_chart_of_accounts_fn=get_all_chart_of_accounts, ensure_default_party_accounts_fn=ensure_default_party_accounts, default_party_accounts=dict(DEFAULT_PARTY_ACCOUNTS))
        return jsonify({'success': True, 'tenant': tenant_id, 'chart_accounts': chart_accounts, 'default_accounts': default_accounts})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}, 500)

@bp.route('/ho/customer-request/save', methods=['POST'])
def customer_request_save():
    t0 = time.perf_counter()
    if not session.get('user'):
        from nexa_http import flash
        return redirect(url_for('auth.login'))
    from nexa_http import flash
    ho_tenant_id = 'HO'
    current_tenant_id = _resolve_effective_tenant()
    t_ensure = time.perf_counter()
    _ensure_customer_request_temp_table(ho_tenant_id)
    ensure_ms = _cr_perf_ms(t_ensure)
    form = request.form
    submitted = (form.get('save_nonce') or '').strip()
    if not verify_consume_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY, submitted):
        issue_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY)
        flash('Duplicate or invalid submit. Reload the form and try again.', 'error')
        cc_raw = (form.get('cr_edit_code') or '').strip()
        if cc_raw and cc_raw.isdigit():
            return redirect(url_for('ho.customer_request_form', customercode=cc_raw))
        return redirect(url_for('ho.customer_request_form'))
    username = session.get('user', 'SYSTEM')
    t_parse = time.perf_counter()
    customername = (form.get('customername') or '').strip().upper()[:200]
    if not customername:
        print(f"[perf][customer_request_save] total_ms={_cr_perf_ms(t0)} ensure_ms={ensure_ms} parse_ms={_cr_perf_ms(t_parse)} validation=customername_missing user={username or '-'}")
        issue_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY)
        flash('Customer name is required.', 'error')
        cc_raw = (form.get('cr_edit_code') or '').strip()
        if cc_raw and cc_raw.isdigit():
            return redirect(url_for('ho.customer_request_form', customercode=cc_raw))
        return redirect(url_for('ho.customer_request_form'))
    cc_raw = (form.get('cr_edit_code') or '').strip()
    is_new = not (cc_raw and cc_raw.isdigit())

    def fi(k, d=None):
        return _safe_int(form.get(k), d)

    def fs(k, n=500):
        return (form.get(k) or '').strip()[:n]
    ho_locationcode_for_temp = _get_ho_location_code()
    fields = {'locationcode': ho_locationcode_for_temp, 'customername': customername, 'customertype': 'S' if fs('customertype') == 'STAFF' else 'P', 'designation': fs('designation', 100), 'sex': 'M' if fs('sex') == 'MALE' else 'F', 'address': fs('address', 200), 'nationality': fs('nationality', 100), 'telephone': fs('telephone', 15), 'fax': fs('fax', 15), 'mobile': fs('mobile', 15), 'email': fs('email', 150), 'whatsapp': fs('whatsapp', 20), 'qatarid': fs('qatarid', 50), 'creditlimit': fi('creditlimit', 0), 'creditterms': fi('creditterm', 0), 'salesmancode': fi('salesmancode', 0), 'invoicecode': fi('invoicecode', 0), 'flag': (fs('flag', 1) or 'Y').upper()[:1], 'closed': (fs('closed', 1) or 'N').upper()[:1], 'countersale': 'Y' if form.get('countersale') == 'Y' else 'N', 'customercategory': fi('customercategory', 0), 'bysalesman': fi('bysalesman', 0), 'routeno': fi('routeno', 0), 'street': fs('street', 200), 'zone': fs('zone', 100), 'pobox': fs('pobox', 50), 'crno': fs('crno', 250), 'receivableaccount': fi('receivableaccount', 0), 'salesaccount': fi('salesaccount', 0), 'vatoutputaccount': fi('vatoutputaccount', 0), 'advanceaccount': fi('advanceaccount', 0), 'employeecode': fi('employeecode'), 'reason': fs('reason'), 'otherreason': fs('otherreason'), 'closedreason': fs('closedreason'), 'branch': current_tenant_id}
    parse_ms = _cr_perf_ms(t_parse)
    if is_new:
        from db import DEFAULT_PARTY_ACCOUNTS as _cr_party_accounts, get_all_chart_of_accounts as _cr_get_all_coa, ensure_default_party_accounts as _cr_ensure_party_accounts
        party = dict(_cr_party_accounts or {})
        l_recv = str(party.get('customer_receivable') or '1200').strip()
        l_sales = str(party.get('customer_sales') or '4100').strip()
        l_vat = str(party.get('customer_vat_output') or '2200').strip()
        l_adv = str(party.get('customer_advance') or '2130').strip()
        tk = str(current_tenant_id or '').strip()
        if tk:
            try:
                _, _dacct = _cr_get_cached_form_accounts(tenant_key=tk, get_all_chart_of_accounts_fn=_cr_get_all_coa, ensure_default_party_accounts_fn=_cr_ensure_party_accounts, default_party_accounts=dict(party))
                if _dacct.get('customer_receivable'):
                    l_recv = str(_dacct.get('customer_receivable')).strip()
                if _dacct.get('customer_sales'):
                    l_sales = str(_dacct.get('customer_sales')).strip()
                if _dacct.get('customer_vat_output'):
                    l_vat = str(_dacct.get('customer_vat_output')).strip()
                if _dacct.get('customer_advance'):
                    l_adv = str(_dacct.get('customer_advance')).strip()
            except Exception:
                pass
        fields['receivableaccount'] = _safe_int(l_recv, _safe_int(party.get('customer_receivable', '1200'), 1200))
        fields['salesaccount'] = _safe_int(l_sales, _safe_int(party.get('customer_sales', '4100'), 4100))
        fields['vatoutputaccount'] = _safe_int(l_vat, _safe_int(party.get('customer_vat_output', '2200'), 2200))
        fields['advanceaccount'] = _safe_int(l_adv, _safe_int(party.get('customer_advance', '2130'), 2130))
    try:
        t_db = time.perf_counter()
        with _get_tenant_connection(ho_tenant_id) as conn:
            with conn.cursor() as cur:
                if is_new:
                    customercode = _get_next_customer_request_code(ho_tenant_id)
                    cur.execute(f"\n                        INSERT INTO {CUSTOMER_TEMP_TABLE} (\n                            CUSTOMERCODE, LOCATIONCODE, CUSTOMERNAME, CUSTOMERTYPE, DESIGNATION, SEX,\n                            ADDRESS, NATIONALITY, TELEPHONE, FAX, MOBILE, EMAIL, WHATSAPP, QATARID,\n                            CREDITLIMIT, CREDITTERMS, SALESMANCODE, INVOICECODE, FLAG, CLOSED, COUNTERSALE,\n                            CUSTOMERCATEGORY, BYSALESMAN, ROUTENO, STREET, ZONE, POBOX, CRNO,\n                            RECEIVABLEACCOUNT, SALESACCOUNT, VATOUTPUTACCOUNT, ADVANCEACCOUNT,\n                            EMPLOYEECODE, REASON, OTHERREASON, CLOSEDREASON, BRANCH,\n                            STATUS, ALERTACKBY, ALERTACKDATE, CREATEDBY, CREATEDDATE\n                        ) VALUES (\n                            :cc, :locationcode, :customername, :customertype, :designation, :sex,\n                            :address, :nationality, :telephone, :fax, :mobile, :email, :whatsapp, :qatarid,\n                            :creditlimit, :creditterms, :salesmancode, :invoicecode, :flag, :closed, :countersale,\n                            :customercategory, :bysalesman, :routeno, :street, :zone, :pobox, :crno,\n                            :receivableaccount, :salesaccount, :vatoutputaccount, :advanceaccount,\n                            :employeecode, :reason, :otherreason, :closedreason, :branch,\n                            'PENDING', NULL, NULL, :createdby, SYSDATE\n                        )\n                    ", {'cc': customercode, 'createdby': username, **fields})
                else:
                    customercode = int(cc_raw)
                    cur.execute(f'\n                        UPDATE {CUSTOMER_TEMP_TABLE} SET\n                            LOCATIONCODE=:locationcode,\n                            CUSTOMERNAME=:customername, CUSTOMERTYPE=:customertype,\n                            DESIGNATION=:designation, SEX=:sex, ADDRESS=:address,\n                            NATIONALITY=:nationality, TELEPHONE=:telephone, FAX=:fax,\n                            MOBILE=:mobile, EMAIL=:email, WHATSAPP=:whatsapp, QATARID=:qatarid,\n                            CREDITLIMIT=:creditlimit, CREDITTERMS=:creditterms,\n                            SALESMANCODE=:salesmancode, INVOICECODE=:invoicecode,\n                            FLAG=:flag, CLOSED=:closed, COUNTERSALE=:countersale,\n                            CUSTOMERCATEGORY=:customercategory, BYSALESMAN=:bysalesman,\n                            ROUTENO=:routeno, STREET=:street, ZONE=:zone, POBOX=:pobox, CRNO=:crno,\n                            RECEIVABLEACCOUNT=:receivableaccount, SALESACCOUNT=:salesaccount,\n                            VATOUTPUTACCOUNT=:vatoutputaccount, ADVANCEACCOUNT=:advanceaccount,\n                            EMPLOYEECODE=:employeecode, REASON=:reason,\n                            OTHERREASON=:otherreason, CLOSEDREASON=:closedreason,\n                            BRANCH=:branch,\n                            ALERTACKBY=NULL, ALERTACKDATE=NULL,\n                            UPDATEDBY=:updatedby, UPDATEDDATE=SYSDATE\n                        WHERE CUSTOMERCODE=:cc\n                    ', {'cc': customercode, 'updatedby': username, **fields})
            conn.commit()
        db_ms = _cr_perf_ms(t_db)
        print(f"[perf][customer_request_save] total_ms={_cr_perf_ms(t0)} ensure_ms={ensure_ms} parse_ms={parse_ms} db_ms={db_ms} mode={('insert' if is_new else 'update')} code={customercode} user={username or '-'}")
        flash('Customer request saved successfully.', 'success')
    except Exception as exc:
        print(f"[perf][customer_request_save] total_ms={_cr_perf_ms(t0)} ensure_ms={ensure_ms} parse_ms={parse_ms} mode={('insert' if is_new else 'update')} error={exc} user={username or '-'}")
        issue_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY)
        flash(f'Error saving customer request: {exc}', 'error')
        return redirect(url_for('ho.customer_request_form') + (f'?customercode={cc_raw}' if not is_new else ''))
    return redirect(url_for('ho.customer_request', tab='pending'))

@bp.route('/ho/customer-request/convert/<int:customercode>', methods=['POST'])
def customer_request_convert(customercode: int):
    """Read from CUSTOMERTEMP (HO) and insert into the branch's CUSTOMER table."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    ho_tenant_id = 'HO'
    username = session.get('user', 'SYSTEM')
    try:
        req = None
        with _get_tenant_connection(ho_tenant_id) as h_conn:
            with h_conn.cursor() as cur:
                cur.execute(f'SELECT * FROM {CUSTOMER_TEMP_TABLE} WHERE CUSTOMERCODE = :cc', {'cc': customercode})
                cols = [d[0].lower() for d in cur.description]
                row = cur.fetchone()
                if row:
                    req = dict(zip(cols, row))
        if not req:
            return jsonify({'success': False, 'error': 'Customer request not found.'}, 404)
        branch_tenant_id = (req.get('branch') or '').strip()
        if not branch_tenant_id:
            return jsonify({'success': False, 'error': 'Branch not set on this request.'}, 400)
        base_map = _cr_temp_row_to_base_col_map(req)
        acc_err = _cc_validate_mandatory_gl_accounts(base_map)
        if acc_err:
            return jsonify({'success': False, 'error': acc_err}, 400)
        with _get_tenant_connection(branch_tenant_id) as b_conn:
            with b_conn.cursor() as cur:
                for cand in ('CUSTOMER', 'CUSTOMERMASTER', 'CUSTMASTER'):
                    cur.execute('SELECT COUNT(*) FROM user_tables WHERE table_name = :t', {'t': cand})
                    if cur.fetchone()[0]:
                        cust_tbl = cand
                        break
                else:
                    return jsonify({'success': False, 'error': 'Customer table not found in branch DB.'}, 500)

                def _col_exists(tbl, col):
                    cur.execute('SELECT COUNT(*) FROM user_tab_columns WHERE table_name=:t AND column_name=:c', {'t': tbl.upper(), 'c': col.upper()})
                    return cur.fetchone()[0] > 0
                loc_col = 'LOCATIONCODE' if _col_exists(cust_tbl, 'LOCATIONCODE') else None
                code_col = 'CUSTOMERCODE'
                cur.execute(f'SELECT NVL(MAX({code_col}), 0) + 1 FROM {cust_tbl}')
                new_code = cur.fetchone()[0]
                col_map = {'CUSTOMERCODE': new_code, 'CUSTOMERNAME': str(req.get('customername') or '').strip().upper()[:250], 'CUSTOMERTYPE': req.get('customertype') or 'P', 'DESIGNATION': req.get('designation') or '', 'SEX': req.get('sex') or 'M', 'ADDRESS': req.get('address') or '', 'NATIONALITY': req.get('nationality') or '', 'TELEPHONE': req.get('telephone') or '', 'FAX': req.get('fax') or '', 'MOBILE': req.get('mobile') or '', 'EMAIL': req.get('email') or '', 'WHATSAPP': req.get('whatsapp') or '', 'QATARID': req.get('qatarid') or '', 'CREDITLIMIT': req.get('creditlimit') or 0, 'CREDITTERMS': req.get('creditterms') or 0, 'DUEDAYS': req.get('creditterms') or 0, 'CURRENTCREDITAMOUNT': 0, 'SALESMANCODE': req.get('salesmancode') or 0, 'INVOICECODE': req.get('invoicecode') or 1, 'FLAG': req.get('flag') or 'Y', 'CLOSED': req.get('closed') or 'N', 'COUNTERSALE': req.get('countersale') or 'N', 'CUSTOMERCATEGORY': req.get('customercategory') or 0, 'BYSALESMAN': req.get('bysalesman') or 0, 'ROUTENO': req.get('routeno') or 0, 'STREET': req.get('street') or '', 'ZONE': req.get('zone') or '', 'POBOX': req.get('pobox') or '', 'CRNO': req.get('crno') or '', 'RECEIVABLEACCOUNT': _cc_account_value_or_default(req.get('receivableaccount'), 'customer_receivable'), 'SALESACCOUNT': _cc_account_value_or_default(req.get('salesaccount'), 'customer_sales'), 'VATOUTPUTACCOUNT': _cc_account_value_or_default(req.get('vatoutputaccount'), 'customer_vat_output'), 'ADVANCEACCOUNT': _cc_account_value_or_default(req.get('advanceaccount'), 'customer_advance'), 'EMPLOYEECODE': req.get('employeecode')}
                if loc_col:
                    col_map[loc_col] = req.get('locationcode') or 0
                if _col_exists(cust_tbl, 'CCODE'):
                    assigned = str(req.get('assignedccode') or '').strip()
                    if assigned:
                        col_map['CCODE'] = assigned[:20]
                    else:
                        _, nxt_cc = _cc_next_code(branch_tenant_id)
                        col_map['CCODE'] = nxt_cc
                        if not str(col_map.get('CCODE') or '').strip():
                            return jsonify({'success': False, 'error': 'C Code (CCODE) could not be assigned.'}, 400)
                col_map = _cc_apply_account_column_aliases(cur, cust_tbl, col_map)
                valid_cols = {c: v for c, v in col_map.items() if _col_exists(cust_tbl, c)}
                has_created = _col_exists(cust_tbl, 'CREATEDDATE')
                cols_str = ', '.join(valid_cols.keys())
                placeholders = ', '.join((f':p_{i}' for i in range(len(valid_cols))))
                params = {f'p_{i}': v for i, v in enumerate(valid_cols.values())}
                if has_created:
                    ins_sql = f'INSERT INTO {cust_tbl} ({cols_str}, CREATEDDATE) VALUES ({placeholders}, SYSDATE)'
                else:
                    ins_sql = f'INSERT INTO {cust_tbl} ({cols_str}) VALUES ({placeholders})'
                cur.execute(ins_sql, params)
            b_conn.commit()
        with _get_tenant_connection(ho_tenant_id) as h_conn:
            with h_conn.cursor() as cur:
                cur.execute(f"UPDATE {CUSTOMER_TEMP_TABLE} SET STATUS='CONVERTED', UPDATEDBY=:u, UPDATEDDATE=SYSDATE WHERE CUSTOMERCODE=:cc", {'u': username, 'cc': customercode})
            h_conn.commit()
        return jsonify({'success': True, 'message': 'Customer converted to central successfully.'})
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(exc)}, 500)

@bp.route('/ho/customer-request/approve/<int:customercode>', methods=['POST'])
def customer_request_approve(customercode: int):
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    ho_tenant_id = 'HO'
    try:
        with _get_tenant_connection(ho_tenant_id) as conn:
            with conn.cursor() as cur:
                cur.execute(f"UPDATE {CUSTOMER_TEMP_TABLE} SET STATUS='APPROVED', UPDATEDBY=:u, UPDATEDDATE=SYSDATE WHERE CUSTOMERCODE=:cc", {'u': session.get('user', 'SYSTEM'), 'cc': customercode})
            conn.commit()
        return jsonify({'success': True, 'message': 'Request approved.'})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}, 500)

@bp.route('/ho/api/customer-request-ai-process', methods=['POST'])
def customer_request_ai_process():
    """Process one pending customer request: duplicate check, then central save (branch + HO)."""
    if not session.get('user'):
        return jsonify({'ok': False, 'error': 'Unauthorized'}, 401)
    username = str(session.get('user') or '')
    data = _customer_request_process_ai_once(username)
    if data.get('error') == 'forbidden':
        return jsonify(data, 403)
    return jsonify(data)

@bp.route('/ho/api/customer-request-ai-auto-convert', methods=['POST'])
def customer_request_ai_auto_convert_set():
    """Organization-wide: turn AI auto-convert on or off for all users (stored in HO CR_ALERT_CONTROL)."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    current_user = str(session.get('user') or '').strip()
    is_privileged = current_user.lower() in {u.lower() for u in PRIVILEGED_USERS}
    can_customer_creation = get_user_customer_creation(current_user) == 'Y'
    if not (is_privileged or can_customer_creation):
        return jsonify({'success': False, 'error': 'Forbidden'}, 403)
    data = request.get_json(silent=True) or request.form or {}
    en = data.get('enabled')
    if isinstance(en, str):
        enabled = en.strip().lower() in ('1', 'true', 'y', 'yes', 'on')
    else:
        enabled = bool(en)
    try:
        _set_cr_ai_auto_convert_enabled('HO', enabled, current_user)
        on = _get_cr_ai_auto_convert_enabled('HO')
        return jsonify({'success': True, 'ai_auto_convert': 'Y' if on else 'N'})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}, 500)

@bp.route('/ho/api/customer-request-pending-count')
def customer_request_pending_count():
    """Return pending count + latest pending request code (used for sound/badge alerts)."""
    if not session.get('user'):
        return jsonify({'count': 0}, 401)
    ho_tenant_id = 'HO'
    poll_enabled = _get_customer_request_alert_poll_enabled(ho_tenant_id)
    if not poll_enabled:
        return jsonify({
            'count': 0,
            'latest_code': 0,
            'last_ack_code': 0,
            'ai_auto_convert': 'N',
            'poll_enabled': 'N',
        })
    current_user = str(session.get('user') or '').strip()
    is_privileged = current_user.lower() in {u.lower() for u in PRIVILEGED_USERS}
    can_customer_creation = get_user_customer_creation(current_user) == 'Y'
    if not (is_privileged or can_customer_creation):
        return jsonify({'count': 0, 'latest_code': 0, 'last_ack_code': 0, 'ai_auto_convert': 'N', 'poll_enabled': 'Y'})
    try:
        _ensure_customer_request_temp_table(ho_tenant_id)
        _ensure_customer_alert_control_table(ho_tenant_id)
        with _get_tenant_connection(ho_tenant_id) as conn:
            with conn.cursor() as cur:
                cur.execute(f"\n                    SELECT\n                        COUNT(*) AS cnt,\n                        MAX(CUSTOMERCODE) AS latest_code\n                    FROM {CUSTOMER_TEMP_TABLE}\n                    WHERE UPPER(NVL(STATUS,'PENDING')) IN ('PENDING', 'CONVERTING')\n                      AND ALERTACKDATE IS NULL\n                    ")
                row = cur.fetchone()
                count = int(row[0]) if row and row[0] is not None else 0
                latest_code = int(row[1]) if row and row[1] is not None else 0
                cur.execute(f'SELECT LAST_ACK_CODE FROM {CUSTOMER_ALERT_TABLE} WHERE ID = 1')
                ack_row = cur.fetchone()
                last_ack_code = int(ack_row[0]) if ack_row and ack_row[0] is not None else 0
        ai_on = _get_cr_ai_auto_convert_enabled(ho_tenant_id)
        return jsonify({
            'count': count,
            'latest_code': latest_code,
            'last_ack_code': last_ack_code,
            'ai_auto_convert': 'Y' if ai_on else 'N',
            'poll_enabled': 'Y',
        })
    except Exception as exc:
        print(f'[customer_request_pending_count] ERROR: {exc}')
        return jsonify({'count': 0, 'latest_code': 0, 'last_ack_code': 0, 'ai_auto_convert': 'N', 'poll_enabled': 'Y'})

@bp.route('/ho/api/customer-request-alert-dismiss', methods=['POST'])
def customer_request_alert_dismiss():
    """Acknowledge current customer request alerts globally for all users."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    current_user = str(session.get('user') or '').strip()
    is_privileged = current_user.lower() in {u.lower() for u in PRIVILEGED_USERS}
    can_customer_creation = get_user_customer_creation(current_user) == 'Y'
    if not (is_privileged or can_customer_creation):
        return jsonify({'success': False, 'error': 'Forbidden'}, 403)
    ho_tenant_id = 'HO'
    payload = request.get_json(silent=True) or {}
    ack_code_raw = payload.get('latest_code')
    try:
        ack_code = int(ack_code_raw) if ack_code_raw is not None else None
    except Exception:
        ack_code = None
    try:
        _ensure_customer_request_temp_table(ho_tenant_id)
        _ensure_customer_alert_control_table(ho_tenant_id)
        with _get_tenant_connection(ho_tenant_id) as conn:
            with conn.cursor() as cur:
                if ack_code is None:
                    cur.execute(f"SELECT MAX(CUSTOMERCODE) FROM {CUSTOMER_TEMP_TABLE} WHERE UPPER(NVL(STATUS,'PENDING'))='PENDING'")
                    row = cur.fetchone()
                    ack_code = int(row[0]) if row and row[0] is not None else 0
                cur.execute(f'\n                    UPDATE {CUSTOMER_ALERT_TABLE}\n                    SET LAST_ACK_CODE = GREATEST(NVL(LAST_ACK_CODE, 0), :ack_code),\n                        UPDATEDBY = :u,\n                        UPDATEDDATE = SYSDATE\n                    WHERE ID = 1\n                    ', {'ack_code': int(ack_code or 0), 'u': str(session.get('user') or 'SYSTEM')})
            conn.commit()
        return jsonify({'success': True, 'ack_code': int(ack_code or 0)})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}, 500)

@bp.route('/ho/customer-request/reopen/<int:customercode>', methods=['POST'])
def customer_request_reopen(customercode: int):
    """Move a rejected/converted request back to PENDING status."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    ho_tenant_id = 'HO'
    redirect_after = (request.form.get('redirect') or '').strip()
    try:
        _ensure_customer_request_temp_table(ho_tenant_id)
        with _get_tenant_connection(ho_tenant_id) as conn:
            with conn.cursor() as cur:
                cur.execute(f"UPDATE {CUSTOMER_TEMP_TABLE} SET STATUS='PENDING', REJECTCOMMENT=NULL, ALERTACKBY=NULL, ALERTACKDATE=NULL, UPDATEDBY=:u, UPDATEDDATE=SYSDATE WHERE CUSTOMERCODE=:cc", {'u': session.get('user', 'SYSTEM'), 'cc': customercode})
            conn.commit()
        if redirect_after:
            flash('Request moved back to Pending.', 'success')
            return redirect(url_for('ho.customer_request', tab='pending'))
        return jsonify({'success': True, 'message': 'Request moved to pending.'})
    except Exception as exc:
        if redirect_after:
            flash(f'Error: {exc}', 'error')
            return redirect(url_for('ho.customer_request', tab='rejected'))
        return jsonify({'success': False, 'error': str(exc)}, 500)

@bp.route('/ho/customer-request/ack-alert/<int:customercode>', methods=['POST'])
def customer_request_ack_alert(customercode: int):
    """Acknowledge alert for a single pending request."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    ho_tenant_id = 'HO'
    try:
        _ensure_customer_request_temp_table(ho_tenant_id)
        with _get_tenant_connection(ho_tenant_id) as conn:
            with conn.cursor() as cur:
                cur.execute(f"UPDATE {CUSTOMER_TEMP_TABLE} SET ALERTACKBY=:u, ALERTACKDATE=SYSDATE, UPDATEDBY=:u, UPDATEDDATE=SYSDATE WHERE CUSTOMERCODE=:cc AND UPPER(NVL(STATUS,'PENDING'))='PENDING'", {'u': session.get('user', 'SYSTEM'), 'cc': customercode})
            conn.commit()
        return jsonify({'success': True, 'message': 'Alert acknowledged.'})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}, 500)

@bp.route('/ho/customer-request/reject/<int:customercode>', methods=['POST'])
def customer_request_reject(customercode: int):
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    ho_tenant_id = 'HO'
    comment = (request.form.get('comment') or request.json.get('comment') if request.is_json else request.form.get('comment') or '').strip()
    redirect_after = (request.form.get('redirect') or '').strip()
    try:
        _ensure_customer_request_temp_table(ho_tenant_id)
        with _get_tenant_connection(ho_tenant_id) as conn:
            with conn.cursor() as cur:
                cur.execute(f"UPDATE {CUSTOMER_TEMP_TABLE} SET STATUS='REJECTED', REJECTCOMMENT=:cmt, UPDATEDBY=:u, UPDATEDDATE=SYSDATE WHERE CUSTOMERCODE=:cc", {'cmt': comment or None, 'u': session.get('user', 'SYSTEM'), 'cc': customercode})
            conn.commit()
        if redirect_after:
            flash('Request rejected.', 'success')
            return redirect(url_for('ho.customer_request'))
        return jsonify({'success': True, 'message': 'Request rejected.'})
    except Exception as exc:
        if redirect_after:
            flash(f'Error: {exc}', 'error')
            return redirect(url_for('ho.customer_request'))
        return jsonify({'success': False, 'error': str(exc)}, 500)
