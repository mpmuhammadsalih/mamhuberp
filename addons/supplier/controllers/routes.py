"""Supplier blueprint - Master data for SUPPLIER table."""
from pathlib import Path
import threading
import time
from nexa_http import Blueprint, g, redirect, render_template, request, session, flash, url_for
from typing import List, Dict, Any, Optional
from save_nonce import GLOBAL_SAVE_NONCE_SESSION_KEY, commit_form_save_nonce, reject_invalid_form_save_nonce, verify_consume_save_nonce
from master_name_duplicate import find_master_name_duplicate, master_name_duplicate_message
from master_activity_log import append_master_activity
from db import _get_connection, _detect_column, _get_table_columns, ensure_supplier_table, get_locations_list, get_location_info_by_dbkey, get_supplier_list, get_next_supplier_code, get_supplier_by_code, ensure_default_party_accounts, DEFAULT_PARTY_ACCOUNTS, get_all_chart_of_accounts
_ADDON_ROOT = Path(__file__).resolve().parents[1]
bp = Blueprint('supplier', __name__, template_folder=str(_ADDON_ROOT / 'views' / 'templates'))
SUPPLIER_TABLE = 'SUPPLIER'
_SUPPLIER_SAVE_LOCKS: Dict[str, threading.Lock] = {}
_SUPPLIER_SAVE_LOCKS_GUARD = threading.Lock()
_SUPPLIER_CACHE_TTL_SECONDS = 300.0
_SUPPLIER_ROUTE_CACHE: Dict[Any, Any] = {}
_SUPPLIER_ACCOUNT_NAMES = {
    'supplier_payable': 'Accounts Payable',
    'supplier_purchase': 'Purchase Expense',
    'supplier_vat_input': 'VAT Payable',
    'supplier_advance': 'Supplier Advances',
}

def _supplier_timing_log(label: str, start: float, **fields: Any) -> None:
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    extras = ' '.join(f'{k}={v}' for k, v in fields.items())
    print(f'[TIMING supplier] {label} elapsed_ms={elapsed_ms:.1f}' + (f' {extras}' if extras else ''))

def _supplier_cache_key(name: str, *parts: Any) -> Any:
    tenant = ''
    try:
        tenant = str(session.get('tenant_id') or '').strip()
    except Exception:
        tenant = ''
    return (tenant, name) + tuple(parts)

def _supplier_cache_get(key: Any) -> Any:
    cached = _SUPPLIER_ROUTE_CACHE.get(key)
    if not cached:
        return None
    ts, value = cached
    if (time.time() - ts) > _SUPPLIER_CACHE_TTL_SECONDS:
        _SUPPLIER_ROUTE_CACHE.pop(key, None)
        return None
    return value

def _supplier_cache_set(key: Any, value: Any) -> Any:
    _SUPPLIER_ROUTE_CACHE[key] = (time.time(), value)
    if len(_SUPPLIER_ROUTE_CACHE) > 100:
        for k in list(_SUPPLIER_ROUTE_CACHE.keys())[:50]:
            _SUPPLIER_ROUTE_CACHE.pop(k, None)
    return value

def _supplier_save_lock_key() -> str:
    user = str(session.get('user') or '').strip().lower()
    tenant = str(session.get('tenant_id') or '').strip().lower()
    return f'{user}:{tenant}:supplier_save'

def _release_supplier_save_lock() -> None:
    lock = getattr(g, '_supplier_save_lock', None)
    if lock is None:
        return
    try:
        lock.release()
    except RuntimeError:
        pass
    g._supplier_save_lock = None

@bp.before_request
def _supplier_save_once_lock():
    if request.method != 'POST' or request.endpoint not in {'supplier.supplier_create', 'supplier.supplier_edit'}:
        return None
    key = _supplier_save_lock_key()
    with _SUPPLIER_SAVE_LOCKS_GUARD:
        lock = _SUPPLIER_SAVE_LOCKS.setdefault(key, threading.Lock())
    if not lock.acquire(blocking=False):
        flash('Supplier save already in progress. Please wait.', 'error')
        return redirect(request.referrer or url_for('supplier.supplier_list'))
    g._supplier_save_lock = lock
    return None

@bp.after_request
def _supplier_save_once_unlock(response):
    _release_supplier_save_lock()
    return response

@bp.teardown_request
def _supplier_save_once_teardown(_exc):
    _release_supplier_save_lock()

def _sess_user_for_log() -> str:
    return str(session.get('user') or '').strip()

def _resolve_location_code() -> int:
    loc = session.get('location_code')
    try:
        if loc is not None and str(loc).isdigit():
            return int(loc)
    except Exception:
        pass
    try:
        info = get_location_info_by_dbkey(None)
        if info and info.get('locationcode') is not None:
            return int(info['locationcode'])
    except Exception:
        pass
    return 1

def _location_name(location_code: int) -> str:
    locations = _cached_locations_list()
    for loc in locations or []:
        if loc.get('code') == location_code:
            return (loc.get('name') or str(location_code)).strip()
    return str(location_code)

def _cached_locations_list() -> List[Dict[str, Any]]:
    key = _supplier_cache_key('locations')
    cached = _supplier_cache_get(key)
    if cached is not None:
        return cached
    try:
        return _supplier_cache_set(key, get_locations_list() or [])
    except Exception:
        return []

def _supplier_default_accounts() -> Dict[str, str]:
    # Avoid running COA/schema setup on every form open; setup is still enforced on save.
    return dict(DEFAULT_PARTY_ACCOUNTS)

def _supplier_account_display_map(defaults: Dict[str, Any], supplier: Optional[Dict[str, Any]]=None) -> Dict[str, str]:
    def _code(key: str, supplier_key: str) -> str:
        value = ''
        if supplier:
            value = str(supplier.get(supplier_key) or '').strip()
        if not value:
            value = str((defaults or {}).get(key) or '').strip()
        return value

    def _label(code: str, key: str) -> str:
        if not code:
            return ''
        name = _SUPPLIER_ACCOUNT_NAMES.get(key) or ''
        return f'{code} - {name}' if name else code

    return {
        'payable': _label(_code('supplier_payable', 'payableaccount'), 'supplier_payable'),
        'purchase': _label(_code('supplier_purchase', 'purchaseaccount'), 'supplier_purchase'),
        'vat_input': _label(_code('supplier_vat_input', 'vatinputaccount'), 'supplier_vat_input'),
        'advance': _label(_code('supplier_advance', 'advanceaccount'), 'supplier_advance'),
    }

def _supplier_chart_accounts_for_session() -> List[Dict[str, Any]]:
    try:
        return get_all_chart_of_accounts() or []
    except Exception:
        return []

def _column_exists(table: str, col: str) -> bool:
    cols = _get_table_columns(table)
    return col.upper() in cols

def _parse_int(v: Any, default: int) -> int:
    if v is None or (isinstance(v, str) and (not v.strip())):
        return default
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default

def _parse_decimal(v: Any, default: float) -> float:
    if v is None or (isinstance(v, str) and (not v.strip())):
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default

@bp.route('/master/supplier')
def supplier_list():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    try:
        ensure_supplier_table()
    except Exception:
        pass
    location_code = None
    try:
        location_code = _resolve_location_code()
    except Exception:
        pass
    location_filter = request.args.get('location', '').strip()
    if location_filter.isdigit():
        location_code = int(location_filter)
    search_term = request.args.get('search', '').strip()
    suppliers = get_supplier_list(location_code=location_code, search=search_term or None, limit=100)
    locations = get_locations_list()
    location_name = _location_name(location_code) if location_code else ''
    return render_template('supplier/supplier_list.html', suppliers=suppliers, locations=locations, location_code=location_code, location_name=location_name, search_term=search_term)

@bp.route('/master/supplier/new', methods=['GET', 'POST'])
def supplier_create():
    _t0 = time.perf_counter()
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    location_code = _resolve_location_code()
    location_name = _location_name(location_code)
    next_code = get_next_supplier_code(location_code)
    if request.method == 'POST':
        try:
            ensure_supplier_table()
        except Exception:
            pass
        return _supplier_save(location_code=location_code, supplier_code=None, is_new=True)
    locations = _cached_locations_list()
    chart_accounts = _supplier_chart_accounts_for_session()
    default_accounts = _supplier_default_accounts()
    account_display = _supplier_account_display_map(default_accounts)

    def _pf_arg(key: str, maxlen: int) -> str:
        return (request.args.get(key) or '').strip()[:maxlen]
    prefill_suppliername = (request.args.get('prefill_name') or request.args.get('prefill_suppliername') or '').strip()[:40]
    resp = render_template('supplier/supplier_form.html', supplier=None, prefill_suppliername=prefill_suppliername, prefill_address=_pf_arg('prefill_address', 200), prefill_telephone=_pf_arg('prefill_telephone', 15), prefill_fax=_pf_arg('prefill_fax', 15), prefill_mobile=_pf_arg('prefill_mobile', 15), prefill_emailid=_pf_arg('prefill_emailid', 150), prefill_contactperson=_pf_arg('prefill_contactperson', 40), prefill_supref=_pf_arg('prefill_supref', 50), prefill_suppliertype=_pf_arg('prefill_suppliertype', 25), prefill_suppliercr=_pf_arg('prefill_suppliercr', 250), location_code=location_code, location_name=location_name, next_supplier_code=next_code, locations=locations, chart_accounts=chart_accounts, default_accounts=default_accounts, account_display=account_display, is_edit=False, accounts_locked=str(session.get('user') or '').strip().lower() != 'admin')
    _supplier_timing_log('form_new_total', _t0, next_code=next_code)
    return resp

@bp.route('/master/supplier/<int:location_code>/<int:supplier_code>/edit', methods=['GET', 'POST'])
def supplier_edit(location_code: int, supplier_code: int):
    _t0 = time.perf_counter()
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    try:
        ensure_supplier_table()
    except Exception:
        pass
    supplier = get_supplier_by_code(location_code, supplier_code)
    if not supplier:
        flash('Supplier not found.', 'error')
        return redirect(url_for('supplier.supplier_list'))
    location_name = _location_name(location_code)
    if request.method == 'POST':
        return _supplier_save(location_code=location_code, supplier_code=supplier_code, is_new=False)
    locations = _cached_locations_list()
    chart_accounts = _supplier_chart_accounts_for_session()
    default_accounts = _supplier_default_accounts()
    account_display = _supplier_account_display_map(default_accounts, supplier)
    resp = render_template('supplier/supplier_form.html', supplier=supplier, prefill_suppliername='', prefill_address='', prefill_telephone='', prefill_fax='', prefill_mobile='', prefill_emailid='', prefill_contactperson='', prefill_supref='', prefill_suppliertype='', prefill_suppliercr='', location_code=location_code, location_name=location_name, next_supplier_code=supplier_code, locations=locations, chart_accounts=chart_accounts, default_accounts=default_accounts, account_display=account_display, is_edit=True, accounts_locked=str(session.get('user') or '').strip().lower() != 'admin')
    _supplier_timing_log('form_edit_total', _t0, supplier_code=supplier_code)
    return resp

def _supplier_save(location_code: int, supplier_code: Optional[int], is_new: bool):
    submitted = (request.form.get('save_nonce') or '').strip()
    if not reject_invalid_form_save_nonce(submitted):
        flash('Duplicate or invalid submit. Reload the supplier form and try again.', 'error')
        if is_new:
            return redirect(url_for('supplier.supplier_create'))
        return redirect(url_for('supplier.supplier_edit', location_code=location_code, supplier_code=supplier_code or 0))
    try:
        ensure_supplier_table()
    except Exception:
        pass
    form = request.form
    suppliername = (form.get('suppliername') or '').strip()
    if not suppliername:
        flash('Supplier name is required.', 'error')
        if is_new:
            return redirect(url_for('supplier.supplier_create'))
        return redirect(url_for('supplier.supplier_edit', location_code=location_code, supplier_code=supplier_code or 0))
    suppliertype = (form.get('suppliertype') or '').strip()[:25]
    address = (form.get('address') or '').strip()[:200]
    telephone = (form.get('telephone') or '').strip()[:15]
    fax = (form.get('fax') or '').strip()[:15]
    mobile = (form.get('mobile') or '').strip()[:15]
    emailid = (form.get('emailid') or '').strip()[:150]
    contactperson = (form.get('contactperson') or '').strip()[:40]
    supplierid = (form.get('supplierid') or '').strip()[:3]
    defaults = {}
    try:
        defaults = ensure_default_party_accounts()
    except Exception:
        defaults = {}
    payableaccount = _parse_int(form.get('payableaccount'), 0) or _parse_int(defaults.get('supplier_payable'), 0) or None
    purchaseaccount = _parse_int(form.get('purchaseaccount'), 0) or _parse_int(defaults.get('supplier_purchase'), 0) or None
    vatinputaccount = _parse_int(form.get('vatinputaccount'), 0) or _parse_int(defaults.get('supplier_vat_input'), 0) or None
    advanceaccount = _parse_int(form.get('advanceaccount'), 0) or _parse_int(defaults.get('supplier_advance'), 0) or None
    if str(session.get('user') or '').strip().lower() != 'admin' and (not is_new) and supplier_code:
        existing = get_supplier_by_code(location_code, int(supplier_code))
        if existing:
            purchaseaccount = _parse_int(existing.get('purchaseaccount'), 0) or purchaseaccount
            vatinputaccount = _parse_int(existing.get('vatinputaccount'), 0) or vatinputaccount
            advanceaccount = _parse_int(existing.get('advanceaccount'), 0) or advanceaccount
    if not payableaccount:
        flash('Payable Account is required.', 'error')
        if is_new:
            return redirect(url_for('supplier.supplier_create'))
        return redirect(url_for('supplier.supplier_edit', location_code=location_code, supplier_code=supplier_code or 0))
    if not purchaseaccount:
        flash('Purchase Account is required.', 'error')
        if is_new:
            return redirect(url_for('supplier.supplier_create'))
        return redirect(url_for('supplier.supplier_edit', location_code=location_code, supplier_code=supplier_code or 0))
    if not vatinputaccount:
        flash('Input VAT Account is required.', 'error')
        if is_new:
            return redirect(url_for('supplier.supplier_create'))
        return redirect(url_for('supplier.supplier_edit', location_code=location_code, supplier_code=supplier_code or 0))
    if not advanceaccount:
        flash('Advance Account is required.', 'error')
        if is_new:
            return redirect(url_for('supplier.supplier_create'))
        return redirect(url_for('supplier.supplier_edit', location_code=location_code, supplier_code=supplier_code or 0))
    flag = (form.get('flag') or '').strip()[:1] or 'Y'
    supplierlocation = (form.get('supplierlocation') or '').strip()[:30]
    supref = (form.get('supref') or '').strip()[:50]
    suppliercr = (form.get('suppliercr') or '').strip()[:250]
    creationflag = (form.get('creationflag') or 'B').strip()[:1] or 'B'
    loc_col = _detect_column(SUPPLIER_TABLE, ['LOCATIONCODE', 'locationcode'])
    code_col = _detect_column(SUPPLIER_TABLE, ['SUPPLIERCODE', 'suppliercode'])
    name_col = _detect_column(SUPPLIER_TABLE, ['SUPPLIERNAME', 'suppliername'])
    if not loc_col or not code_col or (not name_col):
        flash('Supplier table structure error.', 'error')
        return redirect(url_for('supplier.supplier_list'))
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                dup_code = find_master_name_duplicate(
                    cur,
                    table=SUPPLIER_TABLE,
                    name_col=name_col,
                    name_value=suppliername,
                    loc_col=loc_col,
                    location_code=location_code,
                    code_col=code_col,
                    exclude_code=None if is_new else supplier_code,
                )
                if dup_code is not None:
                    flash(
                        master_name_duplicate_message(
                            'supplier',
                            suppliername,
                            location_code=location_code,
                            existing_code=dup_code,
                        ),
                        'error',
                    )
                    if is_new:
                        return redirect(url_for('supplier.supplier_create'))
                    return redirect(url_for('supplier.supplier_edit', location_code=location_code, supplier_code=supplier_code or 0))
    except Exception as dup_exc:
        print(f'[WARN _supplier_save duplicate check] {dup_exc}')
    if not commit_form_save_nonce(submitted):
        flash('Duplicate or invalid submit. Reload the supplier form and try again.', 'error')
        if is_new:
            return redirect(url_for('supplier.supplier_create'))
        return redirect(url_for('supplier.supplier_edit', location_code=location_code, supplier_code=supplier_code or 0))
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                if is_new:
                    code = get_next_supplier_code(location_code)
                    all_cols = [loc_col, code_col, 'SUPPLIERNAME', 'SUPPLIERTYPE', 'ADDRESS', 'TELEPHONE', 'FAX', 'MOBILE', 'EMAILID', 'CONTACTPERSON', 'SUPPLIERID', 'PAYABLEACCOUNT', 'PURCHASEACCOUNT', 'VATINPUTACCOUNT', 'ADVANCEACCOUNT', 'FLAG', 'SUPPLIERLOCATION', 'SUPREF', 'SUPPLIERCR', 'CREATIONFLAG']
                    col_list = [c for c in all_cols if _column_exists(SUPPLIER_TABLE, c)]
                    ph_map = {loc_col: ':loc', code_col: ':code', 'SUPPLIERNAME': ':suppliername', 'SUPPLIERTYPE': ':suppliertype', 'ADDRESS': ':address', 'TELEPHONE': ':telephone', 'FAX': ':fax', 'MOBILE': ':mobile', 'EMAILID': ':emailid', 'CONTACTPERSON': ':contactperson', 'SUPPLIERID': ':supplierid', 'PAYABLEACCOUNT': ':payableaccount', 'PURCHASEACCOUNT': ':purchaseaccount', 'VATINPUTACCOUNT': ':vatinputaccount', 'ADVANCEACCOUNT': ':advanceaccount', 'FLAG': ':flag', 'SUPPLIERLOCATION': ':supplierlocation', 'SUPREF': ':supref', 'SUPPLIERCR': ':suppliercr', 'CREATIONFLAG': ':creationflag'}
                    placeholders = ', '.join((ph_map.get(c, 'NULL') for c in col_list))
                    cols_str = ', '.join(col_list)
                    all_insert_params = {'loc': location_code, 'code': code, 'suppliername': suppliername, 'suppliertype': suppliertype or None, 'address': address or None, 'telephone': telephone or None, 'fax': fax or None, 'mobile': mobile or None, 'emailid': emailid or None, 'contactperson': contactperson or None, 'supplierid': supplierid or None, 'payableaccount': payableaccount, 'purchaseaccount': purchaseaccount, 'vatinputaccount': vatinputaccount, 'advanceaccount': advanceaccount, 'flag': flag, 'supplierlocation': supplierlocation or None, 'supref': supref or None, 'suppliercr': suppliercr or None, 'creationflag': creationflag}
                    bind_names = {(ph_map.get(c, '') or '').replace(':', '').strip() for c in col_list if (ph_map.get(c, '') or '').startswith(':')}
                    insert_params = {k: v for k, v in all_insert_params.items() if k in bind_names}
                    ins_sql = f'INSERT INTO {SUPPLIER_TABLE} ({cols_str}) VALUES ({placeholders})'
                    cur.execute(ins_sql, insert_params)
                    conn.commit()
                    flash('Supplier saved successfully.', 'success')
                    nm = (suppliername or '').strip()[:120]
                    append_master_activity(username=_sess_user_for_log(), action='CREATE', entity='supplier', summary=f'location={location_code}, supplier_code={code}, name={nm}', detail={'locationcode': location_code, 'suppliercode': code, 'suppliername': nm})
                    return redirect(url_for('supplier.supplier_list'))
                else:
                    val_by_param = {'suppliername': suppliername, 'suppliertype': suppliertype or None, 'address': address or None, 'telephone': telephone or None, 'fax': fax or None, 'mobile': mobile or None, 'emailid': emailid or None, 'contactperson': contactperson or None, 'supplierid': supplierid or None, 'payableaccount': payableaccount, 'purchaseaccount': purchaseaccount, 'vatinputaccount': vatinputaccount, 'advanceaccount': advanceaccount, 'flag': flag, 'supplierlocation': supplierlocation or None, 'supref': supref or None, 'suppliercr': suppliercr or None, 'creationflag': creationflag}
                    set_parts = []
                    upd_params = {'loc': location_code, 'code': supplier_code}
                    for col, param in [('SUPPLIERNAME', 'suppliername'), ('SUPPLIERTYPE', 'suppliertype'), ('ADDRESS', 'address'), ('TELEPHONE', 'telephone'), ('FAX', 'fax'), ('MOBILE', 'mobile'), ('EMAILID', 'emailid'), ('CONTACTPERSON', 'contactperson'), ('SUPPLIERID', 'supplierid'), ('PAYABLEACCOUNT', 'payableaccount'), ('FLAG', 'flag'), ('PURCHASEACCOUNT', 'purchaseaccount'), ('VATINPUTACCOUNT', 'vatinputaccount'), ('ADVANCEACCOUNT', 'advanceaccount'), ('SUPPLIERLOCATION', 'supplierlocation'), ('SUPREF', 'supref'), ('SUPPLIERCR', 'suppliercr'), ('CREATIONFLAG', 'creationflag')]:
                        if _column_exists(SUPPLIER_TABLE, col):
                            set_parts.append(f'{col} = :{param}')
                            upd_params[param] = val_by_param[param]
                    if not set_parts:
                        flash('No updatable columns found.', 'error')
                        return redirect(url_for('supplier.supplier_list'))
                    upd_sql = f"UPDATE {SUPPLIER_TABLE} SET {', '.join(set_parts)} WHERE {loc_col} = :loc AND {code_col} = :code"
                    cur.execute(upd_sql, upd_params)
                    conn.commit()
                    flash('Supplier updated successfully.', 'success')
                    nm = (suppliername or '').strip()[:120]
                    append_master_activity(username=_sess_user_for_log(), action='UPDATE', entity='supplier', summary=f'location={location_code}, supplier_code={supplier_code}, name={nm}', detail={'locationcode': location_code, 'suppliercode': supplier_code, 'suppliername': nm})
                    return redirect(url_for('supplier.supplier_list'))
    except Exception as e:
        print(f'[ERROR _supplier_save] {e}')
        import traceback
        traceback.print_exc()
        flash(f'Error saving supplier: {str(e)}', 'error')
    if is_new:
        return redirect(url_for('supplier.supplier_create'))
    return redirect(url_for('supplier.supplier_edit', location_code=location_code, supplier_code=supplier_code or 0))
