"""Item Master blueprint"""
from pathlib import Path
import copy
import io
import json
import csv
import logging
import pickle
import tempfile
import difflib
import os
import re
import secrets
import threading
import time
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set, Tuple
from nexa_http import Blueprint, Response, current_app, flash, jsonify, redirect, render_template, request, session, url_for
from werkzeug.utils import secure_filename
from config.settings import is_multi_db_mode
from master_activity_log import append_master_activity, fetch_master_activity_log
from save_nonce import GLOBAL_SAVE_NONCE_SESSION_KEY, commit_form_save_nonce, extract_submitted_save_nonce, get_or_issue_global_save_nonce, issue_save_nonce, json_response_rotate_global, reject_invalid_form_save_nonce, replay_blocked_response_global, verify_consume_save_nonce
from addons.itemmaster.db_branch_item_store import save_itemmaster_with_alternate_uoms
from db import get_items_list, get_items_kpis, get_categories, get_category_lookup_label, get_category_master_tree, get_category_master_flat, update_category_master_name, insert_category_main, insert_brand, insert_category_lookup, insert_category_dept, insert_category_micro, get_suppliers, get_supplier_by_code, get_units, get_all_unit_of_measurement, get_units_for_itemmaster_dropdown, get_uom_lookup_display, insert_unit_of_measurement, update_unit_of_measurement, delete_unit_of_measurement, get_item_properties, get_item_origins, get_item_property_lookup_display, get_item_origin_lookup_display, insert_item_property_row, update_item_property_row, insert_item_origin_row, update_item_origin_row, get_item_by_code, try_get_itemmaster_detail_view, get_item_by_manufacturer_id, get_item_by_alternate_barcode, get_item_alternate_uom, get_item_alternate_uom_by_barcode, get_item_alternate_uoms, get_next_alternate_barcode, get_next_item_code, get_tenant_locationcode_from_auth, get_location_info_by_dbkey, get_all_chart_of_accounts, get_chart_of_account_by_code, get_all_item_accounts, get_category_pricepercentage_by_code, get_item_store_inventory, get_item_ledger_tab, get_item_costing_method_details, get_itemmaster_bin_tracking_panel_data, list_warehouse_picker_bins, get_warehouse_storage_rows, ensure_itemmaster_inventory_extension_columns, ensure_itemmaster_image_path_column, set_item_batch_tracked, set_item_weight_item, set_item_default_bin_storage_id, set_item_staging_bin_storage_id, set_item_image_path, is_location_batch_tracking_enabled, is_location_warehouse_enabled, is_location_bin_tracking_enabled, CHART_OF_ACCOUNTS_TABLE, _detect_table, _detect_column, resolve_warehouse_master_table, resolve_legacy_store_table, list_warehouse_master_rows, get_warehouse_master_by_id, _fetch_rows, _get_connection, _safe_rows, _table_exists, ensure_chart_of_accounts_table, import_category_master_from_excel_rows, import_itemmaster_from_excel_rows, import_itemmaster_prices_from_excel_rows, import_itemmaster_costprice_from_excel_rows, count_itemmaster_missing_itemnameara, fetch_itemmaster_missing_itemnameara_batch, update_itemmaster_itemnameara_if_empty, count_category_missing_nameara, fetch_category_missing_nameara_batch, update_category_nameara_if_empty, ensure_category_nameara_column, count_itemmaster_missing_base_alternate, bulk_sync_itemmaster_base_alternate_batch, _im_import_row_dict, format_location_prefix_item_barcode, suggest_location_prefix_item_barcode, barcode_taken_in_location
_IM_AI_ARABIC_BATCH_DEFAULT = 25
_IM_AI_ARABIC_BATCH_MAX = 100
_IM_BASE_ALT_BATCH_DEFAULT = 50
_IM_BASE_ALT_BATCH_MAX = 200
_IM_STORE_STOCK_IMPORT_BATCH_DEFAULT = 100
_IM_STORE_STOCK_IMPORT_BATCH_MAX = 500
_IM_PRICE_IMPORT_MAX_ROWS = 10000
_IM_PRICE_IMPORT_MAX_FILE_BYTES = 10 * 1024 * 1024
_IM_COST_IMPORT_BATCH_SIZE = 50
_ADDON_ROOT = Path(__file__).resolve().parents[1]
bp = Blueprint('itemmaster', __name__, template_folder=str(_ADDON_ROOT / 'views' / 'templates'))
_UOM_CREATE_ONCE_KEY = 'itemmaster_uom_create_once_v1'
_UOM_EDIT_ONCE_KEY = 'itemmaster_uom_edit_save_once_v1'
_UOM_DELETE_ONCE_KEY = 'itemmaster_uom_delete_once_v1'
_ALLOWED_ITEM_IMAGE_EXT = {'.png', '.jpg', '.jpeg', '.webp', '.gif'}


def _delete_item_image_file(rel_path: str) -> None:
    rel = str(rel_path or '').strip().replace('\\', '/')
    if not rel.startswith('uploads/itemmaster/'):
        return
    try:
        full = os.path.join(current_app.root_path, 'static', rel.replace('/', os.sep))
        if os.path.isfile(full):
            os.remove(full)
    except Exception:
        pass


def _save_item_image_upload(upload: Any, *, location_code: int, item_code: int) -> str:
    """Save under static/uploads/itemmaster; return path for static url_for."""
    if not upload or not getattr(upload, 'filename', ''):
        return ''
    original = str(upload.filename or '').strip()
    ext = os.path.splitext(original)[1].lower()
    if ext not in _ALLOWED_ITEM_IMAGE_EXT:
        raise ValueError('Item image must be PNG, JPG, JPEG, WEBP, or GIF.')
    try:
        ic = int(item_code)
    except (TypeError, ValueError):
        ic = 0
    if ic <= 0:
        raise ValueError('Item code is required before uploading an image.')
    stamp = datetime.now().strftime('%Y%m%d%H%M%S')
    filename = f'item_{int(location_code)}_{ic}_{stamp}{ext}'
    target_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'itemmaster')
    os.makedirs(target_dir, exist_ok=True)
    full_path = os.path.join(target_dir, filename)
    upload.save(full_path)
    return f'uploads/itemmaster/{filename}'


def apply_item_image_from_request(
    *,
    item_code: int,
    location_code: int,
    existing_path: str = '',
    tenant_id: Optional[str] = None,
) -> Optional[str]:
    """Persist item image upload/remove from multipart form. Returns error message or None."""
    remove = str(request.form.get('remove_item_image') or '').strip().lower() in ('1', 'true', 'yes', 'y', 'on')
    upload = request.files.get('item_image')
    has_upload = bool(upload and str(getattr(upload, 'filename', '') or '').strip())
    existing = str(existing_path or '').strip()
    if not remove and not has_upload:
        return None
    ensure_itemmaster_image_path_column()
    db_key = str(tenant_id).strip() if tenant_id else None
    new_path = existing
    if remove:
        new_path = ''
    elif has_upload:
        try:
            new_path = _save_item_image_upload(upload, location_code=int(location_code), item_code=int(item_code))
        except ValueError as exc:
            return str(exc)
    ok, err = set_item_image_path(
        int(item_code),
        int(location_code),
        new_path or None,
        db_key=db_key,
    )
    if not ok:
        if has_upload and new_path:
            _delete_item_image_file(new_path)
        return err or 'Could not save item image.'
    if (remove or has_upload) and existing and existing != new_path:
        _delete_item_image_file(existing)
    return None

# In-process cache for view-only item open (per worker). See ITEMMASTER_ITEM_CACHE_SECONDS in .env.
_itemmaster_open_cache: Dict[Tuple[str, int, int], Tuple[float, Dict[str, Any], Optional[Dict[str, str]], Dict[str, str]]] = {}
_itemmaster_open_cache_lock = threading.Lock()
_ITEMMASTER_OPEN_CACHE_MAX = 400
_itemmaster_lookup_cache: Dict[Tuple[str, int, str], Tuple[float, List[Dict[str, Any]]]] = {}
_itemmaster_lookup_cache_lock = threading.Lock()
_ITEMMASTER_LOOKUP_CACHE_MAX = 80


def _itemmaster_item_cache_ttl_seconds() -> float:
    try:
        return max(0.0, float(os.getenv('ITEMMASTER_ITEM_CACHE_SECONDS') or '0'))
    except ValueError:
        return 0.0


def _itemmaster_timing_log_enabled() -> bool:
    return (os.getenv('ITEMMASTER_TIMING_LOG') or '').strip().lower() in ('1', 'true', 'yes')


def _itemmaster_timing_log(label: str, start: float, **fields: Any) -> None:
    """Print compact timing diagnostics when ITEMMASTER_TIMING_LOG=1."""
    if not _itemmaster_timing_log_enabled():
        return
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    extras = ' '.join(f'{k}={v}' for k, v in fields.items())
    print(f'[TIMING itemmaster] {label} elapsed_ms={elapsed_ms:.1f}' + (f' {extras}' if extras else ''))


def _itemmaster_lookup_cache_ttl_seconds() -> float:
    try:
        return max(0.0, float(os.getenv('ITEMMASTER_LOOKUP_CACHE_SECONDS') or '60'))
    except ValueError:
        return 60.0


def _itemmaster_lookup_cache_get(key: Tuple[str, int, str]) -> Optional[List[Dict[str, Any]]]:
    ttl = _itemmaster_lookup_cache_ttl_seconds()
    if ttl <= 0:
        return None
    now = time.monotonic()
    with _itemmaster_lookup_cache_lock:
        row = _itemmaster_lookup_cache.get(key)
        if not row:
            return None
        ts, data = row
        if now - ts > ttl:
            del _itemmaster_lookup_cache[key]
            return None
        return copy.deepcopy(data)


def _itemmaster_lookup_cache_set(key: Tuple[str, int, str], data: List[Dict[str, Any]]) -> None:
    ttl = _itemmaster_lookup_cache_ttl_seconds()
    if ttl <= 0:
        return
    with _itemmaster_lookup_cache_lock:
        while len(_itemmaster_lookup_cache) >= _ITEMMASTER_LOOKUP_CACHE_MAX:
            del _itemmaster_lookup_cache[next(iter(_itemmaster_lookup_cache))]
        _itemmaster_lookup_cache[key] = (time.monotonic(), copy.deepcopy(data or []))


def _itemmaster_open_cache_get(key: Tuple[str, int, int]) -> Optional[Tuple[Dict[str, Any], Optional[Dict[str, str]], Dict[str, str]]]:
    ttl = _itemmaster_item_cache_ttl_seconds()
    if ttl <= 0:
        return None
    now = time.monotonic()
    with _itemmaster_open_cache_lock:
        row = _itemmaster_open_cache.get(key)
        if not row:
            return None
        ts, item_data, detail_lbl, im_lbl = row
        if now - ts > ttl:
            del _itemmaster_open_cache[key]
            return None
        return (
            copy.deepcopy(item_data),
            copy.deepcopy(detail_lbl) if detail_lbl is not None else None,
            copy.deepcopy(im_lbl),
        )


def _itemmaster_open_cache_set(key: Tuple[str, int, int], item_data: Dict[str, Any], detail_lbl: Optional[Dict[str, str]], im_lbl: Dict[str, str]) -> None:
    ttl = _itemmaster_item_cache_ttl_seconds()
    if ttl <= 0 or not item_data:
        return
    with _itemmaster_open_cache_lock:
        while len(_itemmaster_open_cache) >= _ITEMMASTER_OPEN_CACHE_MAX:
            del _itemmaster_open_cache[next(iter(_itemmaster_open_cache))]
        _itemmaster_open_cache[key] = (
            time.monotonic(),
            copy.deepcopy(item_data),
            copy.deepcopy(detail_lbl) if detail_lbl is not None else None,
            copy.deepcopy(im_lbl),
        )


def _itemmaster_open_cache_invalidate_key(key: Tuple[str, int, int]) -> None:
    with _itemmaster_open_cache_lock:
        _itemmaster_open_cache.pop(key, None)


def _issue_uom_create_once() -> str:
    t = secrets.token_urlsafe(24)
    session[_UOM_CREATE_ONCE_KEY] = t
    session.modified = True
    return t

def _verify_consume_uom_create_once(submitted: Optional[str]) -> bool:
    sub = (submitted or '').strip()
    stored = session.get(_UOM_CREATE_ONCE_KEY)
    if not stored or not sub or sub != stored:
        return False
    session.pop(_UOM_CREATE_ONCE_KEY, None)
    session.modified = True
    return True

def _issue_uom_edit_once(unit_code: str) -> str:
    c = (unit_code or '').strip().upper()
    t = secrets.token_urlsafe(24)
    session[_UOM_EDIT_ONCE_KEY] = {'c': c, 'tok': t}
    session.modified = True
    return t

def _verify_consume_uom_edit_once(unit_code: str, submitted: Optional[str]) -> bool:
    sub = (submitted or '').strip()
    data = session.get(_UOM_EDIT_ONCE_KEY)
    if not isinstance(data, dict):
        return False
    if ((data.get('c') or '') or '').strip().upper() != (unit_code or '').strip().upper():
        return False
    tok = (data.get('tok') or '').strip()
    if not tok or tok != sub:
        return False
    session.pop(_UOM_EDIT_ONCE_KEY, None)
    session.modified = True
    return True

def _issue_uom_delete_once(unit_code: str) -> str:
    c = (unit_code or '').strip().upper()
    t = secrets.token_urlsafe(24)
    session[_UOM_DELETE_ONCE_KEY] = {'c': c, 'tok': t}
    session.modified = True
    return t

def _verify_consume_uom_delete_once(unit_code: str, submitted: Optional[str]) -> bool:
    sub = (submitted or '').strip()
    data = session.get(_UOM_DELETE_ONCE_KEY)
    if not isinstance(data, dict):
        return False
    if ((data.get('c') or '') or '').strip().upper() != (unit_code or '').strip().upper():
        return False
    tok = (data.get('tok') or '').strip()
    if not tok or tok != sub:
        return False
    session.pop(_UOM_DELETE_ONCE_KEY, None)
    session.modified = True
    return True

def _uom_json_ok(body_extra: Optional[Dict[str, Any]]=None):
    out: Dict[str, Any] = {'ok': True}
    if body_extra:
        out.update(body_extra)
    out['save_nonce'] = issue_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY)
    return jsonify(out)

def _uom_json_nonce_error(code: int, msg: str):
    return (jsonify({'ok': False, 'error': msg, 'save_nonce': issue_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY)}), code)
_CM_CREATE_M_KEY = 'itemmaster_cm_create_m_v1'
_CM_CREATE_D_KEY = 'itemmaster_cm_create_d_v1'
_CM_CREATE_C_KEY = 'itemmaster_cm_create_c_v1'
_CM_EDIT_KEY = 'itemmaster_cm_edit_once_v1'
_CM_IMPORT_MAX_ROWS = 2000
_IM_IMPORT_MAX_ROWS = 50000
_IM_IMPORT_MAX_FILE_BYTES = 50 * 1024 * 1024  # allow larger workbooks for high row counts
_IM_IMPORT_BATCH_SIZE = 250
_IM_IMPORT_STAGING_DIR = Path(tempfile.gettempdir()) / 'nexa_itemmaster_import'

def _parse_xlsx_first_sheet(raw: bytes, max_rows: int) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """First sheet: row 1 = headers, row 2+ = data. Returns list of header→value dicts."""
    try:
        from openpyxl import load_workbook
    except ImportError:
        return ([], 'Excel import requires openpyxl (pip install openpyxl).')
    try:
        bio = io.BytesIO(raw)
        wb = load_workbook(bio, read_only=True, data_only=True)
        try:
            ws = wb.active
            rows_it = ws.iter_rows(values_only=True)
            first = next(rows_it, None)
            if first is None:
                return ([], 'The worksheet is empty.')
            headers: List[str] = []
            for c in first:
                if c is None:
                    headers.append('')
                else:
                    s = str(c).strip()
                    headers.append(s if s else '')
            out_rows: List[Dict[str, Any]] = []
            for row in rows_it:
                if len(out_rows) >= max_rows:
                    break
                rd: Dict[str, Any] = {}
                for i, h in enumerate(headers):
                    if not h:
                        continue
                    v = row[i] if i < len(row) else None
                    rd[h] = v
                out_rows.append(rd)
            return (out_rows, None)
        finally:
            try:
                wb.close()
            except Exception:
                pass
    except Exception as e:
        return ([], str(e))

def _category_master_parse_xlsx(raw: bytes) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    return _parse_xlsx_first_sheet(raw, _CM_IMPORT_MAX_ROWS)

def _itemmaster_parse_xlsx(raw: bytes) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    return _parse_xlsx_first_sheet(raw, _IM_IMPORT_MAX_ROWS)


def _im_import_stage_path(token: str, suffix: str) -> Path:
    _IM_IMPORT_STAGING_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r'[^a-zA-Z0-9_-]', '', (token or ''))[:48]
    return _IM_IMPORT_STAGING_DIR / f'{safe}.{suffix}'


def _im_import_cleanup_staging(token: str) -> None:
    for suffix in ('rows.pkl', 'state.pkl'):
        try:
            p = _im_import_stage_path(token, suffix)
            if p.is_file():
                p.unlink()
        except Exception:
            pass


def _im_import_count_data_rows(rows: List[Dict[str, Any]]) -> int:
    n = 0
    for raw in rows or []:
        nf = _im_import_row_dict(raw)
        if not nf:
            continue
        if any(v not in (None, '') and str(v).strip() != '' for v in nf.values()):
            n += 1
    return n

def _issue_cm_create_m() -> str:
    t = secrets.token_urlsafe(24)
    session[_CM_CREATE_M_KEY] = t
    session.modified = True
    return t

def _verify_consume_cm_create_m(submitted: Optional[str]) -> bool:
    sub = (submitted or '').strip()
    stored = session.get(_CM_CREATE_M_KEY)
    if not stored or not sub or sub != stored:
        return False
    session.pop(_CM_CREATE_M_KEY, None)
    session.modified = True
    return True

def _issue_cm_create_d(main_code: int) -> str:
    mc = int(main_code)
    t = secrets.token_urlsafe(24)
    session[_CM_CREATE_D_KEY] = {'main': mc, 'tok': t}
    session.modified = True
    return t

def _verify_consume_cm_create_d(main_code: int, submitted: Optional[str]) -> bool:
    sub = (submitted or '').strip()
    data = session.get(_CM_CREATE_D_KEY)
    if not isinstance(data, dict):
        return False
    try:
        if int(data.get('main') or 0) != int(main_code):
            return False
    except (TypeError, ValueError):
        return False
    tok = (data.get('tok') or '').strip()
    if not tok or tok != sub:
        return False
    session.pop(_CM_CREATE_D_KEY, None)
    session.modified = True
    return True

def _issue_cm_create_c(d_code: int) -> str:
    dc = int(d_code)
    t = secrets.token_urlsafe(24)
    session[_CM_CREATE_C_KEY] = {'d': dc, 'tok': t}
    session.modified = True
    return t

def _verify_consume_cm_create_c(d_code: int, submitted: Optional[str]) -> bool:
    sub = (submitted or '').strip()
    data = session.get(_CM_CREATE_C_KEY)
    if not isinstance(data, dict):
        return False
    try:
        if int(data.get('d') or 0) != int(d_code):
            return False
    except (TypeError, ValueError):
        return False
    tok = (data.get('tok') or '').strip()
    if not tok or tok != sub:
        return False
    session.pop(_CM_CREATE_C_KEY, None)
    session.modified = True
    return True

def _issue_cm_edit_once(flag: str, code: int) -> str:
    fl = (flag or '').strip().upper()[:1]
    cd = int(code)
    t = secrets.token_urlsafe(24)
    session[_CM_EDIT_KEY] = {'fl': fl, 'code': cd, 'tok': t}
    session.modified = True
    return t

def _verify_consume_cm_edit_once(flag: str, code: int, submitted: Optional[str]) -> bool:
    sub = (submitted or '').strip()
    fl = (flag or '').strip().upper()[:1]
    data = session.get(_CM_EDIT_KEY)
    if not isinstance(data, dict):
        return False
    if (data.get('fl') or '').strip().upper()[:1] != fl:
        return False
    try:
        if int(data.get('code') or 0) != int(code):
            return False
    except (TypeError, ValueError):
        return False
    tok = (data.get('tok') or '').strip()
    if not tok or tok != sub:
        return False
    session.pop(_CM_EDIT_KEY, None)
    session.modified = True
    return True
_AI_ITEM_MATCH_MIN_SCORE = 0.3

def _resolve_itemmaster_location_code() -> int:
    """Location code for session / LOCATIONMASTER (CATEGORY.LOCATIONCODE, etc.)."""
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
            try:
                return int(loc) if isinstance(loc, (int, float)) else int(str(loc).strip())
            except (TypeError, ValueError):
                pass
    except Exception:
        pass
    return 1

def _sess_user_for_log() -> str:
    return str(session.get('user') or '').strip() or 'unknown'
_ITEMMASTER_BRANCH_ENTITY = 'itemmaster_branch'
_BRANCH_IM_PRICE_HINT_SUBSTR = ('price', 'cost', 'rebate', 'vat', 'discount', 'margin', 'account', 'limit')

def _branch_im_normalize_activity_val(val: Any) -> Any:
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

def _branch_im_activity_item_snapshot(row: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not row:
        return {}
    skip = {'display_item_name'}
    out: Dict[str, Any] = {}
    for k, v in row.items():
        lk = str(k).lower()
        if lk in skip:
            continue
        out[lk] = _branch_im_normalize_activity_val(v)
    return dict(sorted(out.items()))

def _branch_im_activity_diff(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    changes: Dict[str, Dict[str, Any]] = {}
    for k in sorted(set(before) | set(after)):
        bv = before.get(k)
        av = after.get(k)
        if bv != av:
            changes[k] = {'before': bv, 'after': av}
    return changes

def _branch_im_price_related_changes(field_changes: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for k, v in field_changes.items():
        lk = str(k).lower()
        if any((h in lk for h in _BRANCH_IM_PRICE_HINT_SUBSTR)):
            out[k] = v
    return out

def _log_branch_itemmaster_save(*, is_new: bool, location_code_int: int, saved_item_code: Any, old_row_for_log: Optional[Dict[str, Any]], alts_before_log: List[Dict[str, Any]]) -> None:
    try:
        try:
            _final_ic = int(str(saved_item_code).strip())
        except (TypeError, ValueError):
            _final_ic = 0
        new_row_for_log: Optional[Dict[str, Any]] = None
        alts_after_log: List[Dict[str, Any]] = []
        if _final_ic > 0:
            try:
                new_row_for_log = get_item_by_code(_final_ic, location_code_int)
                alts_after_log = list(get_item_alternate_uoms(location_code_int, _final_ic) or [])
            except Exception:
                pass
        before_snap = _branch_im_activity_item_snapshot(old_row_for_log)
        after_snap = _branch_im_activity_item_snapshot(new_row_for_log)
        fc = _branch_im_activity_diff(before_snap, after_snap)
        act_lbl = 'CREATE' if is_new else 'UPDATE'
        tid = (session.get('tenant_id') or '').strip() or None
        _dbk = f', dbkey={tid}' if tid else ''
        append_master_activity(username=_sess_user_for_log(), action=act_lbl, entity=_ITEMMASTER_BRANCH_ENTITY, summary=f'{act_lbl} branch item={_final_ic} loc={location_code_int}{_dbk}'[:500], detail={'tenant_id': tid, 'location_code': location_code_int, 'mode': act_lbl, 'item_code': _final_ic, 'itemmaster_field_changes': fc, 'price_related_changes': _branch_im_price_related_changes(fc), 'alternate_uoms_before': alts_before_log[:80], 'alternate_uoms_after': alts_after_log[:80]})
    except Exception:
        pass
_IM_INDEX_LOCK = threading.Lock()
_IM_INDEX_DONE_KEYS: Set[str] = set()

def _im_oracle_index_exists(cur: Any, index_name: str) -> bool:
    cur.execute('SELECT 1 FROM USER_INDEXES WHERE INDEX_NAME = UPPER(TRIM(:n))', {'n': index_name})
    return cur.fetchone() is not None

def _itemmaster_index_specs() -> List[Tuple[str, str, List[str]]]:
    """(index_name, table, columns) for Item Master–related queries."""
    out: List[Tuple[str, str, List[str]]] = []
    im = _detect_table(['ITEMMASTER', 'itemmaster', 'ITEM_MASTER'])
    if im:
        lc = _detect_column(im, ['LOCATIONCODE', 'LOCATION_CODE', 'LOC_CODE', 'LOCCODE'])
        ic = _detect_column(im, ['ITEMCODE', 'ITEM_CODE', 'itemcode'])
        mfg = _detect_column(im, ['MANUFACTURERID', 'MANUFACTURER_ID', 'BARCODE'])
        rawabi = _detect_column(im, ['RAWABICODE', 'RAWABI_CODE', 'rawabicode'])
        if lc and ic:
            out.append(('IM_MST_LOC_ITEM', im, [lc, ic]))
        if lc and mfg:
            out.append(('IM_MST_LOC_MFG', im, [lc, mfg]))
        if lc and rawabi:
            out.append(('IM_MST_LOC_RAWABI', im, [lc, rawabi]))
        bc = _detect_column(im, ['BRANDCODE', 'BRAND_CODE', 'brandcode'])
        ctc = _detect_column(im, ['CATEGORYCODE', 'CATEGORY_CODE', 'categorycode'])
        isc = _detect_column(im, ['SUPCODE', 'SUPPLIERCODE', 'SUP_CODE', 'supcode'])
        if lc and bc:
            out.append(('IM_MST_LOC_BRAND', im, [lc, bc]))
        if lc and ctc:
            out.append(('IM_MST_LOC_CAT', im, [lc, ctc]))
        if lc and isc:
            out.append(('IM_MST_LOC_SUP', im, [lc, isc]))
    alt = _detect_table(['ITEMALTERNATEUOMMAP', 'itemalternateuommap', 'ITEM_ALTERNATE_UOM_MAP'])
    if alt:
        alc = _detect_column(alt, ['LOCATIONCODE', 'LOCATION_CODE', 'LOC_CODE'])
        amfg = _detect_column(alt, ['MANUFACTURERID', 'MANUFACTURER_ID'])
        if alc and amfg:
            out.append(('IM_ALT_LOC_MFG', alt, [alc, amfg]))
    cat = _detect_table(['CATEGORY', 'category'])
    if cat:
        flag_c = _detect_column(cat, ['FLAG', 'flag']) or 'FLAG'
        code_c = _detect_column(cat, ['CODE', 'code']) or 'CODE'
        loc_c = _detect_column(cat, ['LOCATIONCODE', 'LOCATION_CODE', 'LOCCODE'])
        cols = [flag_c, code_c]
        if loc_c:
            cols = [flag_c, loc_c, code_c]
        out.append(('IM_CAT_LOOKUP', cat, cols))
    sup = _detect_table(['SUPPLIER', 'supplier'])
    if sup:
        sc = _detect_column(sup, ['SUPPLIERCODE', 'SUPPLIER_CODE', 'SUP_CODE', 'CODE'])
        sloc = _detect_column(sup, ['LOCATIONCODE', 'LOCATION_CODE'])
        if sc and sloc:
            out.append(('IM_SUP_LOC_CODE', sup, [sloc, sc]))
        elif sc:
            out.append(('IM_SUP_CODE', sup, [sc]))
    u_tbl = _detect_table(['UNITOFMEASUREMENT', 'unitofmeasurement', 'UnitOfMeasurement', 'UNIT_OF_MEASUREMENT'])
    if u_tbl:
        uc = _detect_column(u_tbl, ['UNITCODE', 'UOMCODE', 'CODE', 'UNIT_CODE', 'UOM'])
        if uc:
            out.append(('IM_UOM_CODE', u_tbl, [uc]))
    prop_tbl = _detect_table(['TBLITEMPROPERTY', 'tblitemproperty', 'TBL_ITEM_PROPERTY'])
    if prop_tbl:
        pc = _detect_column(prop_tbl, ['PROPERTYCODE', 'PROPERTY_CODE', 'CODE', 'PROPERTYID'])
        if pc:
            out.append(('IM_PROP_CODE', prop_tbl, [pc]))
    ori_tbl = _detect_table(['TBLITEMORIGIN', 'tblitemorigin', 'TBL_ITEM_ORIGIN'])
    if ori_tbl:
        oc = _detect_column(ori_tbl, ['ORIGINCODE', 'ORIGIN_CODE', 'CODE', 'ORIGINID'])
        if oc:
            out.append(('IM_ORIG_CODE', ori_tbl, [oc]))
    try:
        ensure_chart_of_accounts_table()
        coa_t = CHART_OF_ACCOUNTS_TABLE
        if _table_exists(coa_t):
            cc = _detect_column(coa_t, ['CODE', 'ACCOUNT_CODE', 'ACCOUNTCODE'])
            if cc:
                out.append(('IM_COA_CODE', coa_t, [cc]))
    except Exception:
        pass
    loc_tbl = resolve_warehouse_master_table()
    if loc_tbl:
        code_col = _detect_column(loc_tbl, ['DBCODE', 'LOCATIONCODE', 'CODE', 'STORE'])
        if code_col:
            out.append(('IM_TBLLOC_CODE', loc_tbl, [code_col]))
    return out

def _itemmaster_plan_index_ddls() -> List[str]:
    ddls: List[str] = []
    for idx_name, tbl, cols in _itemmaster_index_specs():
        if tbl and cols and all(cols):
            ddls.append('CREATE INDEX {} ON {} ({})'.format(idx_name, tbl, ', '.join(cols)))
    return ddls

def _ensure_itemmaster_performance_indexes(force: bool=False) -> None:
    """Create helpful Oracle indexes for Item Master lookups (idempotent)."""
    try:
        tenant_key = str(session.get('tenant_id') or session.get('location_code') or '').strip()
    except Exception:
        tenant_key = ''
    specs = _itemmaster_index_specs()
    if not specs:
        return
    try:
        with _get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT SYS_CONTEXT('USERENV','CURRENT_SCHEMA') FROM dual")
            schema_tag = str(cur.fetchone()[0] or '').strip().upper()
            cache_key = '{}|{}'.format(tenant_key, schema_tag)
            with _IM_INDEX_LOCK:
                if not force and cache_key in _IM_INDEX_DONE_KEYS:
                    return
            for idx_name, tbl, cols in specs:
                if not tbl or not cols or (not all(cols)):
                    continue
                if _im_oracle_index_exists(cur, idx_name):
                    continue
                try:
                    cur.execute('CREATE INDEX {} ON {} ({})'.format(idx_name, tbl, ', '.join(cols)))
                except Exception as exc:
                    msg = str(exc)
                    if 'ORA-00955' in msg or 'ORA-01408' in msg or 'ORA-00957' in msg:
                        continue
                    print('[itemmaster] CREATE INDEX {} skipped: {}'.format(idx_name, msg))
            conn.commit()
        with _IM_INDEX_LOCK:
            _IM_INDEX_DONE_KEYS.add(cache_key)
    except Exception as exc:
        print('[itemmaster] performance indexes skipped: {}'.format(exc))

def _im_bind_preview_dict(params: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in (params or {}).items():
        if isinstance(v, Decimal):
            out[k] = str(v)
        elif hasattr(v, 'isoformat'):
            try:
                out[k] = v.isoformat()
            except Exception:
                out[k] = str(v)
        else:
            out[k] = v
    return out

def _im_sql_wrap_rownum_limit(inner_sql: str, limit: int=500) -> str:
    lim = max(1, min(int(limit), 5000))
    return 'SELECT * FROM (\n{}\n) im_cfg_wrapped WHERE ROWNUM <= {}'.format(inner_sql.strip(), lim)

def _im_build_sql_categories(flag: str, location_code: Optional[int]) -> Tuple[str, Dict[str, Any]]:
    cat_tbl = _detect_table(['CATEGORY', 'category']) or 'CATEGORY'
    where_conditions = ['FLAG = :flag']
    params: Dict[str, Any] = {'flag': (flag or 'B').strip().upper()[:1]}
    if location_code is not None:
        where_conditions.append('LOCATIONCODE = :loc_code')
        params['loc_code'] = int(location_code)
    q = f"SELECT CODE, NAME, ID FROM {cat_tbl} WHERE {' AND '.join(where_conditions)} ORDER BY CODE"
    return (q.strip(), params)

def _im_build_sql_suppliers() -> Tuple[str, Dict[str, Any]]:
    sup = _detect_table(['SUPPLIER', 'supplier']) or 'SUPPLIER'
    sc = _detect_column(sup, ['SUPPLIERCODE', 'SUPPLIER_CODE', 'SUP_CODE', 'CODE']) or 'SUPPLIERCODE'
    sn = _detect_column(sup, ['SUPPLIERNAME', 'SUPPLIER_NAME', 'NAME']) or 'SUPPLIERNAME'
    q = f'SELECT {sc} AS CODE, {sn} AS NAME FROM {sup} ORDER BY {sc}'
    return (q.strip(), {})

def _im_build_sql_units() -> Tuple[str, Dict[str, Any]]:
    tbl = _detect_table(['UNITOFMEASUREMENT', 'unitofmeasurement', 'UnitOfMeasurement', 'UNIT_OF_MEASUREMENT'])
    if not tbl:
        return ('', {})
    code_col = _detect_column(tbl, ['UNITCODE', 'UOMCODE', 'CODE', 'UNIT_CODE', 'UOM'])
    name_col = _detect_column(tbl, ['UNITNAME', 'UOMNAME', 'NAME', 'UNIT_NAME', 'DESCRIPTION'])
    if not code_col:
        return ('', {})
    ne = name_col if name_col else 'TO_CHAR(' + code_col + ')'
    q = f'SELECT {code_col} AS CODE, {ne} AS NAME FROM {tbl} ORDER BY {code_col}'
    return (q.strip(), {})

def _im_build_sql_item_properties() -> Tuple[str, Dict[str, Any]]:
    tbl = _detect_table(['TBLITEMPROPERTY', 'tblitemproperty', 'TBL_ITEM_PROPERTY'])
    if not tbl:
        return ('', {})
    code_col = _detect_column(tbl, ['PROPERTYCODE', 'PROPERTY_CODE', 'CODE', 'PROPERTYID'])
    if not code_col:
        return ('', {})
    name_col = _detect_column(tbl, ['PROPERTYNAME', 'PROPERTY_NAME', 'NAME', 'DESCRIPTION'])
    name_expr = name_col if name_col else 'TO_CHAR(' + code_col + ')'
    q = f'\n        SELECT {code_col} AS code, {name_expr} AS name\n        FROM {tbl}\n        WHERE {code_col} IS NOT NULL\n        ORDER BY {code_col}\n    '
    return (q.strip(), {})

def _im_build_sql_item_origins() -> Tuple[str, Dict[str, Any]]:
    tbl = _detect_table(['TBLITEMORIGIN', 'tblitemorigin', 'TBL_ITEM_ORIGIN'])
    if not tbl:
        return ('', {})
    code_col = _detect_column(tbl, ['ORIGINCODE', 'ORIGIN_CODE', 'CODE', 'ORIGINID'])
    if not code_col:
        return ('', {})
    name_col = _detect_column(tbl, ['ORIGINNAME', 'ORIGIN_NAME', 'NAME', 'DESCRIPTION'])
    name_expr = name_col if name_col else 'TO_CHAR(' + code_col + ')'
    q = f'\n        SELECT {code_col} AS code, {name_expr} AS name\n        FROM {tbl}\n        WHERE {code_col} IS NOT NULL\n        ORDER BY {code_col}\n    '
    return (q.strip(), {})

def _im_build_sql_coa_list() -> Tuple[str, Dict[str, Any]]:
    try:
        ensure_chart_of_accounts_table()
    except Exception:
        return ('', {})
    t = CHART_OF_ACCOUNTS_TABLE
    if not _table_exists(t):
        return ('', {})
    code_col = _detect_column(t, ['CODE', 'ACCOUNT_CODE', 'ACCOUNTCODE'])
    if not code_col:
        return ('', {})
    name_col = _detect_column(t, ['NAME', 'ACCOUNT_NAME', 'ACCOUNTNAME'])
    name_sel = name_col if name_col else 'CAST(NULL AS VARCHAR2(1))'
    q = f'SELECT {code_col} AS code, {name_sel} AS name FROM {t} ORDER BY {code_col}'
    return (q.strip(), {})

def _im_build_sql_tbllocation_stores() -> Tuple[str, Dict[str, Any]]:
    tbl = resolve_warehouse_master_table()
    if not tbl:
        return ('', {})
    code_col = _detect_column(tbl, ['DBCODE', 'dbcode', 'LOCATIONCODE', 'locationcode', 'CODE', 'code', 'STORE', 'store'])
    if not code_col:
        return ('', {})
    desc_col = _detect_column(tbl, ['DESCRIPTION', 'description', 'LOCATION', 'location', 'LOCATIONNAME', 'locationname', 'NAME', 'name'])
    desc_expr = desc_col if desc_col else "''"
    q = f'SELECT {code_col} AS code, {desc_expr} AS name FROM {tbl} WHERE {code_col} IS NOT NULL ORDER BY {code_col}'
    return (q.strip(), {})

def _im_build_sql_next_item_code(location_code: int) -> Tuple[str, Dict[str, Any]]:
    im = _detect_table(['ITEMMASTER', 'itemmaster', 'ITEM_MASTER']) or 'ITEMMASTER'
    ic = _detect_column(im, ['ITEMCODE', 'ITEM_CODE']) or 'ITEMCODE'
    lc = _detect_column(im, ['LOCATIONCODE', 'LOCATION_CODE']) or 'LOCATIONCODE'
    q = f'\n        SELECT NVL(MAX({ic}), 999) + 1 AS next_code\n        FROM {im}\n        WHERE {lc} = :location_code\n    '
    return (q.strip(), {'location_code': int(location_code)})

def _im_build_sql_item_load_short(item_code: int, location_code: int) -> Tuple[str, Dict[str, Any]]:
    im = _detect_table(['ITEMMASTER', 'itemmaster', 'ITEM_MASTER']) or 'ITEMMASTER'
    ic = _detect_column(im, ['ITEMCODE', 'ITEM_CODE']) or 'ITEMCODE'
    lc = _detect_column(im, ['LOCATIONCODE', 'LOCATION_CODE']) or 'LOCATIONCODE'
    name_c = _detect_column(im, ['ITEMNAME', 'ITEM_NAME']) or 'ITEMNAME'
    mfg_c = _detect_column(im, ['MANUFACTURERID', 'MANUFACTURER_ID']) or 'MANUFACTURERID'
    q = f'\n        SELECT {ic} AS itemcode, {name_c} AS itemname, {mfg_c} AS manufacturerid\n        FROM {im} im\n        WHERE im.{ic} = :item_code AND im.{lc} = :location_code\n    '
    return (q.strip(), {'item_code': int(item_code), 'location_code': int(location_code)})

def _im_build_sql_mfg_lookup(manufacturer_id: str, location_code: int) -> Tuple[str, Dict[str, Any]]:
    im = _detect_table(['ITEMMASTER', 'itemmaster', 'ITEM_MASTER']) or 'ITEMMASTER'
    ic = _detect_column(im, ['ITEMCODE', 'ITEM_CODE']) or 'ITEMCODE'
    lc = _detect_column(im, ['LOCATIONCODE', 'LOCATION_CODE']) or 'LOCATIONCODE'
    mfg = _detect_column(im, ['MANUFACTURERID', 'MANUFACTURER_ID']) or 'MANUFACTURERID'
    q = f'\n        SELECT {ic} AS itemcode\n        FROM {im}\n        WHERE {mfg} = :manufacturer_id AND {lc} = :location_code\n    '
    return (q.strip(), {'manufacturer_id': manufacturer_id, 'location_code': int(location_code)})

def _im_build_sql_alt_barcode_lookup(manufacturer_id: str, location_code: int) -> Tuple[str, Dict[str, Any]]:
    alt = _detect_table(['ITEMALTERNATEUOMMAP', 'itemalternateuommap', 'ITEM_ALTERNATE_UOM_MAP'])
    if not alt:
        return ('', {})
    ic = _detect_column(alt, ['ITEMCODE', 'ITEM_CODE']) or 'ITEMCODE'
    lc = _detect_column(alt, ['LOCATIONCODE', 'LOCATION_CODE']) or 'LOCATIONCODE'
    mfg = _detect_column(alt, ['MANUFACTURERID', 'MANUFACTURER_ID']) or 'MANUFACTURERID'
    q = f'\n        SELECT {ic} AS itemcode\n        FROM {alt}\n        WHERE {mfg} = :manufacturer_id AND {lc} = :location_code\n    '
    return (q.strip(), {'manufacturer_id': manufacturer_id, 'location_code': int(location_code)})

def _im_build_sql_ai_template_like(location_code: int, word: str) -> Tuple[str, Dict[str, Any]]:
    tbl = _detect_table(['ITEMMASTER', 'itemmaster', 'ITEM_MASTER'])
    if not tbl:
        return ('', {})
    itemcode_col = _detect_column(tbl, ['ITEMCODE', 'ITEM_CODE'])
    itemname_col = _detect_column(tbl, ['ITEMNAME', 'ITEM_NAME'])
    location_col = _detect_column(tbl, ['LOCATIONCODE', 'LOCATION_CODE', 'LOC_CODE'])
    if not all([itemcode_col, itemname_col, location_col]):
        return ('', {})
    w = (word or 'X').strip()[:80] or 'X'
    q = f'SELECT * FROM (  SELECT {itemcode_col} AS itemcode, {itemname_col} AS itemname   FROM {tbl}   WHERE {location_col} = :loc     AND UPPER({itemname_col}) LIKE :w1     AND {itemcode_col} IS NOT NULL   ORDER BY {itemcode_col} DESC) WHERE ROWNUM <= 400'
    return (q.strip(), {'loc': int(location_code), 'w1': '%{}%'.format(w.upper())})

def _im_build_sql_product_grid_sample(location_code: Optional[int]) -> Tuple[str, Dict[str, Any]]:
    """Same shape as db.get_items_list with no extra filters (product list page)."""
    im_tbl = _detect_table(['ITEMMASTER', 'itemmaster', 'ITEM_MASTER']) or 'ITEMMASTER'
    where_conditions: List[str] = []
    params: Dict[str, Any] = {}
    if location_code is not None:
        where_conditions.append('im.LOCATIONCODE = :location_code')
        params['location_code'] = int(location_code)
    where_clause = 'WHERE ' + ' AND '.join(where_conditions) if where_conditions else ''
    _sql_cat_name = "(SELECT NVL(MAX(cat.NAME), '') FROM CATEGORY cat WHERE cat.CODE = im.CATEGORYCODE AND cat.FLAG = 'C')"
    _sql_brand_name = "(SELECT NVL(MAX(brand.NAME), '') FROM CATEGORY brand WHERE brand.CODE = im.BRANDCODE AND brand.FLAG = 'B')"
    _sql_supp_name = "(SELECT NVL(MAX(sup.SUPPLIERNAME), '') FROM SUPPLIER sup WHERE sup.SUPPLIERCODE = im.SUPCODE AND sup.LOCATIONCODE = im.LOCATIONCODE)"
    q = f'\n        SELECT\n            im.LOCATIONCODE,\n            im.ITEMCODE,\n            im.MANUFACTURERID,\n            im.ITEMNAME,\n            im.BASEUOM,\n            NVL(im.COSTPRICE, 0) AS COSTPRICE,\n            NVL(im.AVERAGECOST, 0) AS AVERAGECOST,\n            NVL(im.CURRENTSTOCK, 0) AS CURRENTSTOCK,\n            NVL(im.RETAILPRICE, 0) AS RETAILPRICE,\n            NVL(im.WHOLESALEPRICE, 0) AS WHOLESALEPRICE,\n            {_sql_cat_name} AS CATEGORYNAME,\n            {_sql_brand_name} AS BRANDNAME,\n            {_sql_supp_name} AS SUPPLIERNAME\n        FROM {im_tbl} im\n        {where_clause}\n        ORDER BY im.ITEMCODE DESC\n    '
    return (q.strip(), params)
try:
    import requests
except Exception:
    requests = None
_AR_WORD_MAP = {'WATER': 'ماء', 'JUICE': 'عصير', 'MILK': 'حليب', 'YOGURT': 'زبادي', 'BREAD': 'خبز', 'RICE': 'أرز', 'SUGAR': 'سكر', 'SALT': 'ملح', 'TEA': 'شاي', 'COFFEE': 'قهوة', 'OIL': 'زيت', 'FLOUR': 'دقيق', 'CHICKEN': 'دجاج', 'BEEF': 'لحم بقري', 'FISH': 'سمك', 'EGG': 'بيض', 'SOAP': 'صابون', 'SHAMPOO': 'شامبو', 'DETERGENT': 'منظف', 'BISCUIT': 'بسكويت', 'CHOCOLATE': 'شوكولاتة', 'BOTTLE': 'زجاجة', 'BOX': 'علبة', 'PACK': 'عبوة', 'KG': 'كجم', 'G': 'جم', 'L': 'لتر', 'ML': 'مل'}
_AR_CHAR_MAP = {'a': 'ا', 'b': 'ب', 'c': 'ك', 'd': 'د', 'e': 'ي', 'f': 'ف', 'g': 'ج', 'h': 'ه', 'i': 'ي', 'j': 'ج', 'k': 'ك', 'l': 'ل', 'm': 'م', 'n': 'ن', 'o': 'و', 'p': 'ب', 'q': 'ق', 'r': 'ر', 's': 'س', 't': 'ت', 'u': 'و', 'v': 'ف', 'w': 'و', 'x': 'كس', 'y': 'ي', 'z': 'ز', '0': '٠', '1': '١', '2': '٢', '3': '٣', '4': '٤', '5': '٥', '6': '٦', '7': '٧', '8': '٨', '9': '٩'}
_NONE_LIKE_TEXTS = {'none', 'null', 'undefined', 'nan'}

def _is_arabic_text(text: str) -> bool:
    return bool(re.search('[\\u0600-\\u06FF]', str(text or '')))

def _match_unit_for_grn_prefill(units: Optional[List[Any]], uom_hint: str) -> Tuple[Optional[Any], str]:
    u = (uom_hint or '').strip().upper()
    if not u or not units:
        return (None, '')
    for unit in units:
        c = str(unit.get('code') or '').strip().upper()
        n = str(unit.get('name') or '').strip().upper()
        if not c and (not n):
            continue
        if c == u or n == u:
            code = unit.get('code')
            name = str(unit.get('name') or '')
            disp = f'{code} - {name}' if code is not None else name
            return (code, disp)
    return (None, '')

def _supplier_display_for_prefill(suppliers: Optional[List[Any]], sup_code: int) -> str:
    if not sup_code or not suppliers:
        return ''
    for s in suppliers:
        try:
            sc = int(float(s.get('code')))
        except (TypeError, ValueError):
            continue
        if sc == sup_code:
            nm = str(s.get('name') or '')
            return f'{sc} - {nm}' if nm else str(sc)
    return str(sup_code)

def _coa_display_for_code(chart_accounts: Optional[List[Dict[str, Any]]], code: str, fallback_name: str) -> str:
    """Build 'CODE - Name' from COA list; else 'CODE - fallback' (matches itemmaster.js default GL)."""
    want = str(code or '').strip()
    for acc in chart_accounts or []:
        c = acc.get('code')
        if c is None:
            continue
        sc = str(c).strip()
        if sc == want:
            nm = (acc.get('name') or '').strip()
            return f'{c} - {nm}' if nm else str(c)
        try:
            if int(float(sc)) == int(float(want)):
                nm = (acc.get('name') or '').strip()
                return f'{c} - {nm}' if nm else str(c)
        except (TypeError, ValueError):
            continue
    return f'{want} - {fallback_name}'

def _grn_new_item_default_account_fields(chart_accounts: Optional[List[Dict[str, Any]]]) -> Dict[str, str]:
    """Default Sales / Purchase / Inventory / COGS for new item from GRN when resetForNewItem() is skipped in JS."""
    return {'sales_code': '4100', 'sales_display': _coa_display_for_code(chart_accounts, '4100', 'Sales Revenue'), 'purchase_code': '5001', 'purchase_display': _coa_display_for_code(chart_accounts, '5001', 'Purchase Expense'), 'inventory_code': '1300', 'inventory_display': _coa_display_for_code(chart_accounts, '1300', 'Inventory'), 'cogs_code': '5100', 'cogs_display': _coa_display_for_code(chart_accounts, '5100', 'Cost of Goods Sold')}

def _clean_none_text(value) -> str:
    if value is None:
        return ''
    txt = str(value).strip()
    if not txt:
        return ''
    return '' if txt.lower() in _NONE_LIKE_TEXTS else txt


def _normalize_lookup_code(value) -> str:
    """Normalize lookup codes for JSON/JS (integer string, no trailing .0)."""
    if value is None:
        return ''
    txt = str(value).strip()
    if not txt or txt.lower() in _NONE_LIKE_TEXTS:
        return ''
    try:
        return str(int(float(txt)))
    except (TypeError, ValueError):
        return txt


def _supplier_lookup_display(location_code_int: int, sup_code: Any) -> str:
    """Resolve supplier code to ``CODE - Name`` for Item Master AI/copy labels."""
    sc = _normalize_lookup_code(sup_code)
    if not sc:
        return ''
    try:
        sup = get_supplier_by_code(int(location_code_int), int(float(sc)))
        if sup:
            nm = (sup.get('suppliername') or sup.get('name') or '').strip()
            return f'{sc} - {nm}'.strip(' -') if nm else sc
    except (TypeError, ValueError):
        pass
    return sc


def _ai_general_payload_from_item_details(d: Dict[str, Any], location_code_int: int) -> Dict[str, Any]:
    """General-tab AI suggestions from a matched item, including lookup display labels."""
    loc = int(location_code_int)
    mc = _normalize_lookup_code(d.get('maincategory'))
    dept = _normalize_lookup_code(d.get('departmentcode'))
    cat = _normalize_lookup_code(d.get('categorycode'))
    brand = _normalize_lookup_code(d.get('brandcode'))
    sup = _normalize_lookup_code(d.get('supcode'))
    return {
        'item_name_ara': _clean_none_text(d.get('itemnameara')),
        'description': _clean_none_text(d.get('description')),
        'main_category': mc,
        'main_category_display': get_category_lookup_label('M', mc, loc) if mc else '',
        'department_code': dept,
        'department_display': get_category_lookup_label('D', dept, loc) if dept else '',
        'category_code': cat,
        'category_display': get_category_lookup_label('C', cat, loc) if cat else '',
        'brand_code': brand,
        'brand_display': get_category_lookup_label('B', brand, loc) if brand else '',
        'sup_code': sup,
        'supplier_display': _supplier_lookup_display(loc, sup) if sup else '',
        'base_uom': _clean_none_text(d.get('baseuom')),
        'default_warehouse_id': d.get('default_warehouse_id'),
    }

def _clean_none_in_dict(row: dict) -> dict:
    cleaned = dict(row or {})
    for k, v in list(cleaned.items()):
        if isinstance(v, str) or v is None:
            cleaned[k] = _clean_none_text(v)
    return cleaned

def _basic_arabic_suggest(item_name: str) -> str:
    """Fallback Arabic suggestion via term mapping + transliteration."""
    src = str(item_name or '').strip()
    if not src:
        return ''
    if _is_arabic_text(src):
        return src
    tokens = re.split('(\\s+|[-_/()])', src.upper())
    out = []
    for tk in tokens:
        if not tk:
            continue
        if re.fullmatch('\\s+|[-_/()]', tk):
            out.append(tk)
            continue
        mapped = _AR_WORD_MAP.get(tk)
        if mapped:
            out.append(mapped)
            continue
        out.append(''.join((_AR_CHAR_MAP.get(ch.lower(), ch) for ch in tk)))
    return ''.join(out).strip()

def _normalize_barcode_for_web_lookup(raw: str) -> str:
    digits = re.sub(r'\D', '', str(raw or ''))
    if len(digits) < 8:
        return ''
    return digits[:20]


def _pick_first_text(*values: Any) -> str:
    for v in values:
        t = _clean_none_text(v)
        if t:
            return t
    return ''


def _barcode_lookup_variants(raw: str) -> List[str]:
    """Distinct barcode strings to try against MANUFACTURERID (trim, digits-only)."""
    bc = str(raw or '').strip()
    if not bc:
        return []
    out: List[str] = []
    seen: Set[str] = set()

    def _add(v: str) -> None:
        v = str(v or '').strip()
        if not v or v in seen:
            return
        seen.add(v)
        out.append(v)

    _add(bc)
    digits = re.sub(r'\D', '', bc)
    if len(digits) >= 8:
        _add(digits)
    return out


def _item_header_by_manufacturer_id(manufacturer_id: str, location_code: int) -> Optional[Dict[str, Any]]:
    """Lightweight barcode existence check (avoids full item load)."""
    loc = int(location_code)
    for mfg in _barcode_lookup_variants(manufacturer_id):
        hit = _item_header_by_manufacturer_id_one(mfg, loc)
        if hit:
            return hit
    return None


def _item_header_by_manufacturer_id_one(mfg: str, location_code: int) -> Optional[Dict[str, Any]]:
    if not mfg:
        return None
    try:
        rows = _safe_rows(
            """
            SELECT ITEMCODE, ITEMNAME
            FROM ITEMMASTER
            WHERE UPPER(TRIM(MANUFACTURERID)) = UPPER(TRIM(:mfg)) AND LOCATIONCODE = :loc
            AND ROWNUM = 1
            """,
            {'mfg': mfg, 'loc': int(location_code)},
        ) or []
        if rows:
            r0 = rows[0]
            return {
                'itemcode': r0.get('itemcode') or r0.get('ITEMCODE'),
                'itemname': _clean_none_text(r0.get('itemname') or r0.get('ITEMNAME')),
            }
        digits = re.sub(r'\D', '', mfg)
        if len(digits) >= 8:
            rows = _safe_rows(
                """
                SELECT ITEMCODE, ITEMNAME
                FROM ITEMMASTER
                WHERE REGEXP_REPLACE(MANUFACTURERID, '[^0-9]', '') = :digits
                AND LOCATIONCODE = :loc
                AND ROWNUM = 1
                """,
                {'digits': digits, 'loc': int(location_code)},
            ) or []
            if rows:
                r0 = rows[0]
                return {
                    'itemcode': r0.get('itemcode') or r0.get('ITEMCODE'),
                    'itemname': _clean_none_text(r0.get('itemname') or r0.get('ITEMNAME')),
                }
        rows = _safe_rows(
            """
            SELECT ITEMCODE
            FROM ITEMALTERNATEUOMMAP
            WHERE UPPER(TRIM(MANUFACTURERID)) = UPPER(TRIM(:mfg)) AND LOCATIONCODE = :loc
            AND ROWNUM = 1
            """,
            {'mfg': mfg, 'loc': int(location_code)},
        ) or []
        if rows:
            r0 = rows[0]
            ic = r0.get('itemcode') or r0.get('ITEMCODE')
            hdr = _safe_rows(
                """
                SELECT ITEMCODE, ITEMNAME
                FROM ITEMMASTER
                WHERE ITEMCODE = :ic AND LOCATIONCODE = :loc
                AND ROWNUM = 1
                """,
                {'ic': ic, 'loc': int(location_code)},
            ) or []
            if hdr:
                return {
                    'itemcode': hdr[0].get('itemcode') or hdr[0].get('ITEMCODE'),
                    'itemname': _clean_none_text(hdr[0].get('itemname') or hdr[0].get('ITEMNAME')),
                }
            return {'itemcode': ic, 'itemname': ''}
    except Exception as exc:
        print(f'[WARN _item_header_by_manufacturer_id] {exc}')
    return None


def _load_item_details_by_barcode_loose(barcode_raw: str, location_code: int) -> Optional[Dict[str, Any]]:
    """Full item row from ITEMMASTER by barcode on header or alternate UOM (tolerant match)."""
    loc = int(location_code)
    for variant in _barcode_lookup_variants(barcode_raw):
        try:
            item = get_item_by_manufacturer_id(variant, loc)
            if item:
                return item
            item = get_item_by_alternate_barcode(variant, loc)
            if item:
                return item
        except Exception as exc:
            print(f'[WARN _load_item_details_by_barcode_loose] {variant}: {exc}')
        hdr = _item_header_by_manufacturer_id_one(variant, loc)
        if hdr and hdr.get('itemcode') is not None:
            try:
                ic = int(float(str(hdr.get('itemcode'))))
                item = get_item_by_code(ic, loc)
                if item:
                    return item
            except (TypeError, ValueError):
                pass
    return None


def _product_dict_from_openfoodfacts_payload(p: Dict[str, Any], barcode: str) -> Optional[Dict[str, Any]]:
    if not isinstance(p, dict):
        return None
    name = _pick_first_text(
        p.get('product_name'),
        p.get('product_name_en'),
        p.get('generic_name_en'),
        p.get('generic_name'),
        p.get('abbreviated_product_name'),
    )
    brand = _pick_first_text(p.get('brands'))
    qty = _pick_first_text(p.get('quantity'))
    categories = _pick_first_text(p.get('categories_tags_en'), p.get('categories'))
    desc_parts = [x for x in (brand, qty, categories) if x]
    description = ' · '.join(desc_parts[:4])
    if not name and not brand:
        return None
    item_name = name or brand
    if name and brand and brand.upper() not in name.upper():
        item_name = f'{brand} {name}'.strip()
    if qty and qty not in item_name:
        item_name = f'{item_name} {qty}'.strip()
    return {
        'item_name': item_name[:500],
        'description': (description or item_name)[:500],
        'brand': brand[:200],
        'quantity': qty[:80],
        'categories': categories[:300],
        'image_url': _pick_first_text(p.get('image_front_url'), p.get('image_url'))[:500],
        'source': 'openfoodfacts',
        'barcode': barcode,
    }


def _fetch_openfoodfacts_product(barcode: str) -> Optional[Dict[str, Any]]:
    if not requests:
        return None
    headers = {'User-Agent': 'NexaDynamics-ItemMaster/1.0 (barcode lookup)'}
    timeout = (4, 8)
    for path in (f'https://world.openfoodfacts.org/api/v0/product/{barcode}.json',
                 f'https://world.openfoodfacts.org/api/v2/product/{barcode}.json'):
        try:
            resp = requests.get(path, headers=headers, timeout=timeout)
            if resp.status_code >= 400:
                continue
            data = resp.json() if resp.content else {}
            if int(data.get('status') or 0) != 1:
                continue
            row = _product_dict_from_openfoodfacts_payload(data.get('product') or {}, barcode)
            if row:
                return row
        except Exception as exc:
            print(f'[WARN _fetch_openfoodfacts_product] {barcode} {path}: {exc}')
    return None


def _fetch_upcitemdb_product(barcode: str) -> Optional[Dict[str, Any]]:
    if not requests:
        return None
    try:
        resp = requests.get(
            'https://api.upcitemdb.com/prod/trial/lookup',
            params={'upc': barcode},
            headers={'Accept': 'application/json', 'User-Agent': 'NexaDynamics-ItemMaster/1.0'},
            timeout=(4, 8),
        )
        if resp.status_code >= 400:
            print(f'[WARN _fetch_upcitemdb_product] HTTP {resp.status_code} for {barcode}')
            return None
        payload = resp.json() if resp.content else {}
        items = payload.get('items') if isinstance(payload, dict) else None
        if not isinstance(items, list) or not items:
            return None
        it = items[0] if isinstance(items[0], dict) else {}
        title = _pick_first_text(it.get('title'), it.get('description'))
        brand = _pick_first_text(it.get('brand'))
        if not title and not brand:
            return None
        item_name = title or brand
        if title and brand and brand.upper() not in title.upper():
            item_name = f'{brand} {title}'.strip()
        return {
            'item_name': item_name[:500],
            'description': _pick_first_text(it.get('description'), item_name)[:500],
            'brand': brand[:200],
            'quantity': '',
            'categories': _pick_first_text(it.get('category'))[:300],
            'image_url': _pick_first_text(it.get('images', [''])[0] if isinstance(it.get('images'), list) and it.get('images') else '')[:500],
            'source': 'upcitemdb',
            'barcode': barcode,
        }
    except Exception as exc:
        print(f'[WARN _fetch_upcitemdb_product] {barcode}: {exc}')
        return None


def _ai_barcode_product_guess(barcode: str) -> Optional[Dict[str, Any]]:
    """Fallback when public barcode APIs are blocked or empty (requires OPENAI_API_KEY)."""
    api_key = (os.environ.get('OPENAI_API_KEY') or '').strip()
    if not api_key or not requests:
        return None
    model = os.environ.get('OPENAI_ITEMMASTER_MODEL', 'gpt-4o-mini')
    try:
        resp = requests.post(
            'https://api.openai.com/v1/chat/completions',
            headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
            json={
                'model': model,
                'temperature': 0.1,
                'response_format': {'type': 'json_object'},
                'messages': [
                    {
                        'role': 'system',
                        'content': (
                            'Identify retail products from EAN/UPC barcodes. '
                            'Reply JSON only: {"found":true|false,"item_name":"","brand":"","description":""}. '
                            'Set found false if you are not confident.'
                        ),
                    },
                    {'role': 'user', 'content': f'Barcode: {barcode}'},
                ],
            },
            timeout=18,
        )
        if resp.status_code >= 400:
            print(f'[WARN _ai_barcode_product_guess] HTTP {resp.status_code}')
            return None
        data = resp.json()
        choices = data.get('choices') or []
        if not choices:
            return None
        raw = str((choices[0].get('message') or {}).get('content') or '').strip()
        if not raw:
            return None
        parsed = json.loads(raw)
        if not isinstance(parsed, dict) or not parsed.get('found'):
            return None
        item_name = _pick_first_text(parsed.get('item_name'), parsed.get('title'))
        brand = _pick_first_text(parsed.get('brand'))
        if not item_name and not brand:
            return None
        name = item_name or brand
        if item_name and brand and brand.upper() not in item_name.upper():
            name = f'{brand} {item_name}'.strip()
        desc = _pick_first_text(parsed.get('description'), name)
        return {
            'item_name': name[:500],
            'description': desc[:500],
            'brand': brand[:200],
            'quantity': '',
            'categories': '',
            'image_url': '',
            'source': 'openai',
            'barcode': barcode,
        }
    except Exception as exc:
        print(f'[WARN _ai_barcode_product_guess] {exc}')
        return None


def _fetch_web_product_by_barcode(barcode: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """Lookup product metadata: Open Food Facts → UPCItemDB → OpenAI (if configured)."""
    code = _normalize_barcode_for_web_lookup(barcode)
    if not code:
        return (False, 'Enter a valid barcode (at least 8 digits).', None)
    if not requests:
        return (False, 'Web lookup is unavailable (requests library not installed).', None)
    web_errors: List[str] = []
    for fetcher in (_fetch_openfoodfacts_product, _fetch_upcitemdb_product):
        try:
            row = fetcher(code)
            if row:
                return (True, '', row)
        except Exception as exc:
            web_errors.append(str(exc))
    ai_row = _ai_barcode_product_guess(code)
    if ai_row:
        return (True, '', ai_row)
    if web_errors:
        return (
            False,
            'Could not reach product databases from this server (check outbound HTTPS / firewall). '
            'OpenAI fallback also did not return a match.',
            None,
        )
    if (os.environ.get('OPENAI_API_KEY') or '').strip():
        return (False, f'No product found for barcode {code} (web + AI).', None)
    return (
        False,
        f'No product found on the web for barcode {code}. Add OPENAI_API_KEY for AI fallback when public APIs are blocked.',
        None,
    )


def _translate_item_name_to_arabic(item_name: str) -> Tuple[str, str]:
    """Return (arabic_text, source) using OpenAI when configured, else term-map fallback."""
    return _translate_text_to_arabic(item_name, context='product')


def _translate_category_name_to_arabic(category_name: str) -> Tuple[str, str]:
    """Return (arabic_text, source) for retail category names."""
    return _translate_text_to_arabic(category_name, context='category')


def _translate_text_to_arabic(text: str, *, context: str = 'product') -> Tuple[str, str]:
    src = str(text or '').strip()
    if not src:
        return ('', 'empty')
    ai_text = _ai_arabic_suggest(src, context=context)
    if ai_text:
        return (ai_text, 'ai')
    if context == 'category':
        fallback = _basic_arabic_suggest(src)
    else:
        fallback = _basic_arabic_suggest(src)
    if fallback:
        return (fallback, 'fallback')
    return ('', 'none')


def _ai_arabic_suggest(text: str, *, context: str = 'product') -> str:
    """Optional AI translation using OpenAI when API key is configured."""
    api_key = (os.environ.get('OPENAI_API_KEY') or '').strip()
    if not api_key or requests is None:
        return ''
    if context == 'category':
        system = (
            'You translate retail product category names (toy store departments) to natural Arabic. '
            'Return ONLY Arabic text, no explanation.'
        )
    elif context == 'product_description':
        system = (
            'You translate e-commerce product descriptions to natural Arabic for Qatar. '
            'Keep the same tone and line breaks. Return ONLY Arabic text, no explanation.'
        )
    elif context == 'product_specs':
        system = (
            'You translate product specification text to Arabic. Preserve line breaks and '
            'Label: value format on each line. Keep emoji characters. Return ONLY Arabic text.'
        )
    else:
        system = 'You translate item names to natural retail Arabic. Return ONLY Arabic text, no explanation.'
    try:
        resp = requests.post('https://api.openai.com/v1/chat/completions', headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}, json={'model': os.environ.get('OPENAI_ITEMMASTER_MODEL', 'gpt-4o-mini'), 'temperature': 0.2, 'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': str(text or '').strip()}]}, timeout=10)
        if resp.status_code >= 400:
            return ''
        data = resp.json()
        choices = data.get('choices') or []
        content = ''
        if choices:
            msg = choices[0].get('message') or {}
            content = str(msg.get('content') or '').strip()
        if content and _is_arabic_text(content):
            return content
        return ''
    except Exception:
        return ''


def _ai_arabic_suggest_item_name(item_name: str) -> str:
    return _ai_arabic_suggest(item_name, context='product')

def _normalize_item_name_for_match(text: str) -> str:
    cleaned = re.sub('[^A-Za-z0-9]+', ' ', str(text or '').upper()).strip()
    return re.sub('\\s+', ' ', cleaned)

def _tokenize_item_words(text: str):
    norm = _normalize_item_name_for_match(text)
    if not norm:
        return []
    return [w for w in norm.split(' ') if w]

def _split_core_variant_tokens(text: str):
    """Split name tokens into semantic core words vs pack/size variant words."""
    tokens = _tokenize_item_words(text)
    core = []
    variant = []
    variant_keywords = {'PCS', 'PC', 'PACK', 'PK', 'BOX', 'BAG', 'BOTTLE', 'CAN', 'X', 'ML', 'L', 'LTR', 'LITRE', 'G', 'GM', 'GRAM', 'KG', 'DOZEN', 'DZ'}
    short_noise_tokens = {'FG', 'BG', 'RG', 'PR', 'NO', 'NOS'}
    for tk in tokens:
        has_alpha = bool(re.search('[A-Z]', tk))
        has_digit = bool(re.search('\\d', tk))
        letters_only = re.sub('[^A-Z]', '', tk)
        if not has_alpha and has_digit or has_digit:
            variant.append(tk)
            continue
        if letters_only in short_noise_tokens:
            variant.append(tk)
            continue
        if len(letters_only) <= 2 and letters_only not in {'TEA'}:
            variant.append(tk)
            continue
        if letters_only in variant_keywords:
            variant.append(tk)
            continue
        core.append(letters_only or tk)
    return (core, variant)

def _best_token_matches(source_tokens: List[str], target_tokens: List[str], min_ratio: float=0.82):
    """
    Fuzzy one-to-one token matcher.
    Returns list of matched pairs: [(source_token, target_token, ratio), ...]
    """
    src = [str(t or '').strip().upper() for t in source_tokens or [] if str(t or '').strip()]
    tgt = [str(t or '').strip().upper() for t in target_tokens or [] if str(t or '').strip()]
    if not src or not tgt:
        return []
    used_target = set()
    pairs = []
    for s in src:
        best_idx = -1
        best_ratio = 0.0
        for idx, t in enumerate(tgt):
            if idx in used_target:
                continue
            if s == t:
                ratio = 1.0
            else:
                ratio = difflib.SequenceMatcher(None, s, t).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_idx = idx
        if best_idx >= 0 and best_ratio >= min_ratio:
            used_target.add(best_idx)
            pairs.append((s, tgt[best_idx], best_ratio))
    return pairs

def _find_best_item_template_by_name(location_code: int, item_name: str):
    """Find best matching previous item using weighted core/variant scoring."""
    tbl = _detect_table(['ITEMMASTER', 'itemmaster', 'ITEM_MASTER'])
    if not tbl:
        return None
    itemcode_col = _detect_column(tbl, ['ITEMCODE', 'itemcode', 'ITEM_CODE'])
    itemname_col = _detect_column(tbl, ['ITEMNAME', 'itemname', 'ITEM_NAME'])
    location_col = _detect_column(tbl, ['LOCATIONCODE', 'locationcode', 'LOCATION_CODE', 'DBOCODE', 'dbocode'])
    if not all([itemcode_col, itemname_col, location_col]):
        return None
    input_core_words, input_variant_words = _split_core_variant_tokens(item_name)
    input_core_set = set(input_core_words)
    input_variant_set = set(input_variant_words)
    if not input_core_set and (not input_variant_set):
        return None
    first_word = input_core_words[0] if input_core_words else input_variant_words[0] if input_variant_words else ''
    like_query = f'SELECT * FROM (  SELECT {itemcode_col} AS itemcode, {itemname_col} AS itemname   FROM {tbl}   WHERE {location_col} = :loc     AND UPPER({itemname_col}) LIKE :w1     AND {itemcode_col} IS NOT NULL   ORDER BY {itemcode_col} DESC) WHERE ROWNUM <= 400'
    all_query = f'SELECT * FROM (  SELECT {itemcode_col} AS itemcode, {itemname_col} AS itemname   FROM {tbl}   WHERE {location_col} = :loc     AND {itemcode_col} IS NOT NULL     AND {itemname_col} IS NOT NULL   ORDER BY {itemcode_col} DESC) WHERE ROWNUM <= 400'
    rows = _safe_rows(like_query, {'loc': location_code, 'w1': f'%{first_word}%'}) or []
    if not rows:
        rows = _safe_rows(all_query, {'loc': location_code}) or []
    if not rows:
        return None

    def _coverage(matched_count: int, total_count: int) -> float:
        return matched_count / total_count if total_count > 0 else 1.0
    scored = []
    for r in rows:
        cand_name = str(r.get('itemname') or '').strip()
        cand_core_words, cand_variant_words = _split_core_variant_tokens(cand_name)
        cand_core_set = set(cand_core_words)
        cand_variant_set = set(cand_variant_words)
        if not cand_core_set and (not cand_variant_set):
            continue
        core_pairs = _best_token_matches(sorted(input_core_set), sorted(cand_core_set), min_ratio=0.8)
        variant_pairs = _best_token_matches(sorted(input_variant_set), sorted(cand_variant_set), min_ratio=0.92)
        matched_core_count = len(core_pairs)
        if input_core_set and matched_core_count == 0:
            continue
        core_input_cov = _coverage(matched_core_count, len(input_core_set))
        core_cand_cov = _coverage(matched_core_count, len(cand_core_set))
        core_score = 0.7 * core_input_cov + 0.3 * core_cand_cov
        matched_variant_count = len(variant_pairs)
        variant_input_cov = _coverage(matched_variant_count, len(input_variant_set))
        variant_cand_cov = _coverage(matched_variant_count, len(cand_variant_set))
        variant_score = 0.5 * variant_input_cov + 0.5 * variant_cand_cov
        score = 0.8 * core_score + 0.2 * variant_score
        if cand_core_words and input_core_words and (cand_core_words[0] == input_core_words[0]):
            score += 0.05
        score = min(score, 1.0)
        try:
            itemcode_num = int(str(r.get('itemcode') or '0').strip())
        except Exception:
            itemcode_num = 0
        matched_words = []
        for s, t, ratio in core_pairs + variant_pairs:
            if s == t:
                matched_words.append(s)
            else:
                matched_words.append(f'{s}~{t}')
        total_input_words = len(input_core_set) + len(input_variant_set)
        total_match_words = len(matched_words)
        scored.append((score, matched_core_count, total_match_words, total_input_words, itemcode_num, matched_words, r))
    if not scored:
        return None
    scored.sort(key=lambda x: (x[0], x[1], x[2], x[4]), reverse=True)
    best_score, _, best_match_count, best_input_count, _, best_words, best = scored[0]
    try:
        best_item_code = int(str(best.get('itemcode') or '').strip())
    except Exception:
        return None
    details = get_item_by_code(best_item_code, location_code)
    if not details:
        return None
    return {'score': round(float(best_score), 4), 'word_match_count': int(best_match_count), 'input_word_count': int(best_input_count), 'matched_words': best_words, 'details': details}

def _get_tbllocation_store_rows() -> list:
    """Warehouse picker rows for Item Master — ``code`` is ``WAREHOUSE_ID``."""
    if resolve_warehouse_master_table():
        out = []
        seen = set()
        for r in list_warehouse_master_rows(active_only=True) or []:
            try:
                wid = int(r.get('warehouse_id'))
            except (TypeError, ValueError):
                continue
            if wid <= 0 or wid in seen:
                continue
            seen.add(wid)
            wh_code = str(r.get('warehouse_code') or '').strip()
            wh_name = str(r.get('warehouse_name') or '').strip()
            out.append({'code': str(wid), 'warehouse_code': wh_code, 'name': wh_name or wh_code or str(wid)})
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


def _itemmaster_attach_warehouse_display(item_data: Optional[Dict[str, Any]]) -> None:
    """Set ``default_warehouse_display`` on item row for UI (code — name)."""
    if not item_data:
        return
    wid = item_data.get('default_warehouse_id')
    if wid is None or str(wid).strip() == '':
        item_data['default_warehouse_display'] = ''
        return
    try:
        wh = get_warehouse_master_by_id(int(wid))
    except (TypeError, ValueError):
        wh = None
    if wh:
        code = str(wh.get('warehouse_code') or '').strip()
        name = str(wh.get('warehouse_name') or '').strip()
        item_data['default_warehouse_display'] = (f'{code} — {name}' if code and name else code or name or str(wid))
    else:
        item_data['default_warehouse_display'] = str(wid)


def _normalize_lookup_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in rows or []:
        code = row.get('code')
        if code is None:
            code = row.get('unitcode')
        out.append({
            'code': code,
            'name': row.get('name') or row.get('unitname') or row.get('suppliername') or '',
            'id': row.get('id'),
            'warehouse_code': row.get('warehouse_code') or '',
        })
    return out


def _itemmaster_lookup_rows(kind: str, location_code: int) -> List[Dict[str, Any]]:
    clean_kind = (kind or '').strip().lower()
    tenant = (session.get('tenant_id') or '').strip()
    key = (tenant, int(location_code or 1), clean_kind)
    cached = _itemmaster_lookup_cache_get(key)
    if cached is not None:
        return cached
    if clean_kind == 'maincategory':
        rows = _normalize_lookup_rows(get_categories('M'))
    elif clean_kind == 'brand':
        rows = _normalize_lookup_rows(get_categories('B'))
    elif clean_kind == 'size':
        rows = _normalize_lookup_rows(get_categories('Z'))
    elif clean_kind == 'color':
        rows = _normalize_lookup_rows(get_categories('L'))
    elif clean_kind in ('baseuom', 'alternateuom', 'ministryunit', 'uom'):
        rows = _normalize_lookup_rows(get_units_for_itemmaster_dropdown(int(location_code)))
    elif clean_kind == 'supplier':
        rows = _normalize_lookup_rows(get_suppliers())
    elif clean_kind == 'property':
        rows = _normalize_lookup_rows(get_item_properties())
    elif clean_kind == 'origin':
        rows = _normalize_lookup_rows(get_item_origins())
    elif clean_kind in ('store', 'warehouse', 'requestlocation'):
        rows = _normalize_lookup_rows(_get_tbllocation_store_rows())
    else:
        rows = []
    _itemmaster_lookup_cache_set(key, rows)
    return rows


@bp.route('/itemmaster/api/bootstrap', methods=['GET'])
def api_itemmaster_bootstrap():
    """One small bootstrap payload for Item Master lookup popups."""
    _t0 = time.perf_counter()
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    loc = _resolve_itemmaster_location_code()
    kinds_raw = (request.args.get('kinds') or '').strip()
    kinds = [k.strip() for k in kinds_raw.split(',') if k.strip()] if kinds_raw else [
        'mainCategory', 'brand', 'size', 'color', 'baseUom', 'alternateUom',
        'ministryUnit', 'supplier', 'property', 'origin', 'warehouse',
    ]
    data: Dict[str, List[Dict[str, Any]]] = {}
    for kind in kinds:
        _tk = time.perf_counter()
        data[kind] = _itemmaster_lookup_rows(kind, int(loc))
        _itemmaster_timing_log('api_bootstrap_kind', _tk, kind=kind, rows=len(data.get(kind) or []), loc=loc)
    total_rows = sum(len(v or []) for v in data.values())
    _itemmaster_timing_log('api_bootstrap_total', _t0, kinds=','.join(kinds), total_rows=total_rows, loc=loc)
    return jsonify({'success': True, 'location_code': loc, 'lookups': data})


@bp.route('/itemmaster/api/default-bins', methods=['GET'])
def api_itemmaster_default_bins():
    """Default-bin picker rows for the currently selected Item Master warehouse."""
    _t0 = time.perf_counter()
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    wh = (request.args.get('wh') or request.args.get('default_warehouse_id') or request.args.get('store') or '').strip()
    if not wh:
        return jsonify({'success': True, 'warehouse_id': '', 'bins': []})
    try:
        rows = list_warehouse_picker_bins(wh) or []
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}, 500)
    bins: List[Dict[str, Any]] = []
    for row in rows:
        if not row:
            continue
        sid = row.get('storage_id')
        code = str(row.get('code') or '').strip()
        if sid is None or not code:
            continue
        bins.append({
            'storage_id': sid,
            'code': code,
            'name': str(row.get('name') or '').strip(),
            'warehouse_id': str(row.get('warehouse_id') or row.get('loc_key') or wh).strip(),
            'storage_type': str(row.get('storage_type') or '').strip(),
        })
    _itemmaster_timing_log('api_default_bins', _t0, warehouse_id=wh, rows=len(bins))
    return jsonify({'success': True, 'warehouse_id': wh, 'bins': bins})


@bp.route('/productlist/api/kpis', methods=['GET'])
def api_productlist_kpis():
    """Deferred KPI aggregate for product list (keeps first paint light)."""
    _t0 = time.perf_counter()
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    flt = _productlist_filters_from_request()
    loc = _resolve_itemmaster_location_code()
    kpis = get_items_kpis(
        location_code=loc,
        search=flt.get('search'),
        stock_filter=flt.get('stock_filter'),
        brand_code=flt.get('brand_code'),
        category_code=flt.get('category_code'),
        supplier_code=flt.get('supplier_code'),
        item_codes=flt.get('item_codes'),
    )
    _itemmaster_timing_log('api_productlist_kpis', _t0, loc=loc, search=bool(flt.get('search')))
    return jsonify({'success': True, 'kpis': kpis})


@bp.route('/productlist/api/items', methods=['GET'])
def api_productlist_items():
    """Fast paginated item list for async refresh/search."""
    _t0 = time.perf_counter()
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    search = (request.args.get('search') or '').strip()
    stock_filter = request.args.get('stockFilter') or None
    if stock_filter == 'all':
        stock_filter = None
    brand_code_raw = request.args.get('brandCode')
    category_code_raw = request.args.get('categoryCode')
    supplier_code = request.args.get('supplierCode') or None
    sort_column = (request.args.get('sort') or '').strip()
    sort_order = (request.args.get('order') or '').strip()
    try:
        page = max(1, int(request.args.get('page') or 1))
    except (TypeError, ValueError):
        page = 1
    try:
        per_page = max(20, min(int(request.args.get('per_page') or 50), 200))
    except (TypeError, ValueError):
        per_page = 50
    def _int_or_none(raw: Any) -> Optional[int]:
        try:
            return int(raw) if raw not in (None, '') else None
        except (TypeError, ValueError):
            return None
    item_codes: Optional[List[int]] = None
    item_codes_raw = (request.args.get('itemCodes') or '').strip()
    if item_codes_raw:
        item_codes = []
        for part in item_codes_raw.split(','):
            try:
                item_codes.append(int(part.strip()))
            except (TypeError, ValueError):
                continue
    loc = _resolve_itemmaster_location_code()
    items, total_count = get_items_list(
        location_code=loc,
        search=search or None,
        stock_filter=stock_filter,
        brand_code=_int_or_none(brand_code_raw),
        category_code=_int_or_none(category_code_raw),
        supplier_code=supplier_code if supplier_code else None,
        item_codes=item_codes,
        order_by=sort_column if sort_column else None,
        order_direction=sort_order if sort_order else None,
        page=page,
        items_per_page=per_page,
    )
    _itemmaster_timing_log('api_productlist_items', _t0, loc=loc, page=page, per_page=per_page, rows=len(items or []), total=total_count, search=bool(search))
    return jsonify({
        'success': True,
        'items': items,
        'total_count': total_count,
        'page': page,
        'items_per_page': per_page,
        'total_pages': (total_count + per_page - 1) // per_page if total_count > 0 else 1,
    })


def _productlist_filters_from_request() -> Dict[str, Any]:
    """Shared list filters for product list page, API, and export."""
    search = (request.args.get('search') or '').strip()
    stock_filter = (request.args.get('stockFilter') or '').strip() or None
    if stock_filter == 'all':
        stock_filter = None
    brand_code_raw = (request.args.get('brandCode') or '').strip()
    category_code_raw = (request.args.get('categoryCode') or '').strip()
    supplier_code = (request.args.get('supplierCode') or '').strip() or None
    sort_column = (request.args.get('sort') or '').strip()
    sort_order = (request.args.get('order') or '').strip()
    item_codes_str = (request.args.get('itemCodes') or '').strip()
    item_codes: Optional[List[int]] = None
    if item_codes_str:
        try:
            item_codes = [int(code.strip()) for code in item_codes_str.split(',') if code.strip()]
        except ValueError:
            item_codes = None

    def _int_or_none(raw: Any) -> Optional[int]:
        try:
            return int(raw) if raw not in (None, '') else None
        except (TypeError, ValueError):
            return None

    return {
        'search': search or None,
        'stock_filter': stock_filter,
        'brand_code': _int_or_none(brand_code_raw),
        'category_code': _int_or_none(category_code_raw),
        'supplier_code': supplier_code,
        'item_codes': item_codes,
        'order_by': sort_column or None,
        'order_direction': sort_order or None,
    }


def _productlist_item_status_label(item: Dict[str, Any]) -> str:
    try:
        stock_qty = float(item.get('currentstock') or 0)
    except (TypeError, ValueError):
        stock_qty = 0.0
    if str(item.get('itemflag') or 'Y').strip().upper() == 'N':
        return 'Inactive'
    if stock_qty <= 0:
        return 'Low Stock'
    return 'Active'


@bp.route('/productlist/export')
def productlist_export():
    """Export full item list (all matching rows, not only current page) as CSV."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    _t0 = time.perf_counter()
    flt = _productlist_filters_from_request()
    loc = _resolve_itemmaster_location_code()
    items, total_count = get_items_list(
        loc,
        flt['search'],
        stock_filter=flt['stock_filter'],
        brand_code=flt['brand_code'],
        category_code=flt['category_code'],
        supplier_code=flt['supplier_code'],
        item_codes=flt['item_codes'],
        order_by=flt['order_by'],
        order_direction=flt['order_direction'],
        page=None,
        items_per_page=None,
        include_lookup_names=True,
    )
    buf = io.StringIO()
    buf.write('\ufeff')
    w = csv.writer(buf)
    w.writerow([
        'Sl.No', 'Item Code', 'Barcode', 'Item Name', 'UOM', 'Cost', 'Avg Cost', 'Retail',
        'Stock', 'Status', 'Category', 'Brand', 'Supplier',
    ])
    for idx, item in enumerate(items or [], start=1):
        w.writerow([
            idx,
            item.get('itemcode') or '',
            item.get('manufacturerid') or '',
            item.get('itemname') or '',
            item.get('baseuom') or '',
            f"{float(item.get('costprice') or 0):.2f}",
            f"{float(item.get('averagecost') or 0):.2f}",
            f"{float(item.get('retailprice') or 0):.2f}",
            f"{float(item.get('currentstock') or 0):.3f}",
            _productlist_item_status_label(item),
            item.get('categoryname') or '',
            item.get('brandname') or '',
            item.get('suppliername') or '',
        ])
    fn = f"product_list_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    _itemmaster_timing_log('productlist_export', _t0, loc=loc, rows=len(items or []), total=total_count)
    return Response(buf.getvalue(), mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename="{fn}"'})


@bp.route('/productlist/api/item-quick-update', methods=['POST'])
def api_productlist_item_quick_update():
    """Quick edit for safe ITEMMASTER fields from the product-list preview drawer."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    payload = request.get_json(silent=True) or {}
    def _str(name: str, default: str='') -> str:
        return str(payload.get(name, default) or '').strip()
    def _num(name: str) -> float:
        raw = _str(name, '0').replace(',', '')
        try:
            return round(float(raw or 0), 2)
        except (TypeError, ValueError):
            return 0.0
    try:
        item_code = int(float(_str('item_code')))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Invalid item code'}, 400)
    if item_code <= 0:
        return jsonify({'success': False, 'error': 'Invalid item code'}, 400)
    item_name = _str('item_name')
    base_uom = _str('base_uom')
    if not item_name:
        return jsonify({'success': False, 'error': 'Item name is required'}, 400)
    if not base_uom:
        return jsonify({'success': False, 'error': 'UOM is required'}, 400)
    item_flag = 'N' if _str('item_flag', 'Y').upper() == 'N' else 'Y'
    loc = _resolve_itemmaster_location_code()
    updated = {
        'itemcode': item_code,
        'itemname': item_name.upper(),
        'manufacturerid': _str('manufacturer_id'),
        'baseuom': base_uom,
        'costprice': _num('cost_price'),
        'averagecost': _num('average_cost'),
        'retailprice': _num('retail_price'),
        'wholesaleprice': _num('wholesale_price'),
        'itemflag': item_flag,
    }
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE ITEMMASTER
                       SET ITEMNAME = :itemname,
                           MANUFACTURERID = :manufacturerid,
                           BASEUOM = :baseuom,
                           COSTPRICE = :costprice,
                           AVERAGECOST = :averagecost,
                           RETAILPRICE = :retailprice,
                           WHOLESALEPRICE = :wholesaleprice,
                           ITEMFLAG = :itemflag
                     WHERE ITEMCODE = :itemcode
                       AND LOCATIONCODE = :locationcode
                    """,
                    {
                        **updated,
                        'locationcode': loc,
                    },
                )
                if int(cur.rowcount or 0) <= 0:
                    conn.rollback()
                    return jsonify({'success': False, 'error': 'Item not found for this location'}, 404)
            conn.commit()
        return jsonify({'success': True, 'item': updated})
    except Exception as e:
        print(f'[ERROR api_productlist_item_quick_update] {e}')
        return jsonify({'success': False, 'error': str(e)}, 500)


@bp.route('/itemmaster/api/variants', methods=['GET'])
def api_itemmaster_variants():
    """Load alternate UOM rows only when the Variant tab is opened."""
    _t0 = time.perf_counter()
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    try:
        item_code = int(float(str(request.args.get('item_code') or '').strip()))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Invalid item code'}, 400)
    if item_code <= 0:
        return jsonify({'success': False, 'error': 'Invalid item code'}, 400)
    loc = _resolve_itemmaster_location_code()
    try:
        rows = get_item_alternate_uoms(int(loc), int(item_code)) or []
        _itemmaster_timing_log('api_variants', _t0, loc=loc, item_code=item_code, rows=len(rows))
        return jsonify({'success': True, 'rows': rows})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}, 500)


@bp.route('/itemmaster/api/inventory-details', methods=['GET'])
def api_itemmaster_inventory_details():
    """Load store inventory/bin quantities only when the Inventory tab is opened."""
    _t0 = time.perf_counter()
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    try:
        item_code = int(float(str(request.args.get('item_code') or '').strip()))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Invalid item code'}, 400)
    if item_code <= 0:
        return jsonify({'success': False, 'error': 'Invalid item code'}, 400)
    loc = _resolve_itemmaster_location_code()
    try:
        _ts = time.perf_counter()
        store_rows = get_item_store_inventory(int(loc), int(item_code)) or []
        _itemmaster_timing_log('api_inventory_store_rows', _ts, loc=loc, item_code=item_code, rows=len(store_rows))
    except Exception:
        store_rows = []
    try:
        _tp = time.perf_counter()
        panel = get_itemmaster_bin_tracking_panel_data(int(loc), filter_item_code=int(item_code), lightweight=False)
        _itemmaster_timing_log('api_inventory_bin_panel', _tp, loc=loc, item_code=item_code, rows=len(panel.get('bin_stock_rows') or []), show=bool(panel.get('show')))
    except Exception:
        panel = {'bin_stock_rows': []}
    _itemmaster_timing_log('api_inventory_total', _t0, loc=loc, item_code=item_code, store_rows=len(store_rows), bin_rows=len(panel.get('bin_stock_rows') or []))
    return jsonify({
        'success': True,
        'store_inventory_rows': store_rows,
        'bin_stock_rows': panel.get('bin_stock_rows') or [],
        'bin_panel': {
            'show': bool(panel.get('show')),
            'loc_key': panel.get('loc_key'),
            'hint': panel.get('hint') or '',
        },
    })


@bp.route('/itemmaster/api/code-labels', methods=['GET'])
def api_itemmaster_code_labels():
    """Resolve current edit-field codes to display labels after the page opens."""
    _t0 = time.perf_counter()
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    loc = _resolve_itemmaster_location_code()
    def _arg(name: str) -> Any:
        return (request.args.get(name) or '').strip()
    item_data = {
        'maincategory': _arg('maincategory'),
        'departmentcode': _arg('departmentcode'),
        'categorycode': _arg('categorycode'),
        'brandcode': _arg('brandcode'),
        'sizecode': _arg('sizecode'),
        'colorcode': _arg('colorcode'),
        'baseuom': _arg('baseuom'),
        'ministryunit': _arg('ministryunit'),
        'property': _arg('property'),
        'origin': _arg('origin'),
        'supcode': _arg('supcode'),
        'sales_account': _arg('sales_account'),
        'purchase_account': _arg('purchase_account'),
        'inventory_account': _arg('inventory_account'),
        'cogs_account': _arg('cogs_account'),
    }
    try:
        labels = _build_itemmaster_view_labels(item_data, None, int(loc))
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}, 500)
    _itemmaster_timing_log('api_code_labels', _t0, loc=loc, labels=len(labels or {}))
    return jsonify({'success': True, 'labels': labels})

@bp.route('/itemmaster/data-config', methods=['GET', 'POST'])
def itemmaster_data_config():
    """SQL used by Item Master / product list + optional preview execution and index DDL (tenant DB)."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if str(session.get('user') or '').strip().lower() != 'admin':
        flash('Data config is available only for the admin user.', 'warning')
        return redirect(url_for('itemmaster.productlist'))
    default_loc = _resolve_itemmaster_location_code()
    try:
        row_limit = int((request.values.get('row_limit') or '500').strip())
    except (TypeError, ValueError):
        row_limit = 500
    row_limit = max(1, min(row_limit, 5000))
    try:
        cfg_loc = int((request.values.get('location_code') or str(default_loc)).strip())
    except (TypeError, ValueError):
        cfg_loc = default_loc
    category_flag = (request.values.get('category_flag') or 'B').strip().upper()[:1]
    if category_flag not in ('B', 'M', 'C', 'D', 'Z', 'L'):
        category_flag = 'B'
    cat_use_location = (request.values.get('cat_use_location') or '').strip().lower() in ('1', 'on', 'true', 'yes')
    cat_loc = cfg_loc if cat_use_location else None
    try:
        sample_item_code = int((request.values.get('sample_item_code') or '1').strip())
    except (TypeError, ValueError):
        sample_item_code = 1
    sample_mfg = (request.values.get('sample_mfg_id') or 'SAMPLE').strip()[:120]
    ai_word = (request.values.get('ai_word') or 'ITEM').strip()[:80] or 'ITEM'
    bundles: Dict[str, Tuple[str, Dict[str, Any]]] = {'categories': _im_build_sql_categories(category_flag, cat_loc), 'suppliers': _im_build_sql_suppliers(), 'units': _im_build_sql_units(), 'properties': _im_build_sql_item_properties(), 'origins': _im_build_sql_item_origins(), 'coa': _im_build_sql_coa_list(), 'stores': _im_build_sql_tbllocation_stores(), 'next_code': _im_build_sql_next_item_code(cfg_loc), 'item_load': _im_build_sql_item_load_short(sample_item_code, cfg_loc), 'mfg_lookup': _im_build_sql_mfg_lookup(sample_mfg, cfg_loc), 'alt_barcode': _im_build_sql_alt_barcode_lookup(sample_mfg, cfg_loc), 'ai_template': _im_build_sql_ai_template_like(cfg_loc, ai_word), 'product_grid': _im_build_sql_product_grid_sample(cfg_loc)}
    panel_meta = [('categories', '1 · CATEGORY lookups (get_categories)'), ('suppliers', '2 · SUPPLIER list'), ('units', '3 · UNITOFMEASUREMENT list'), ('properties', '4 · TBLITEMPROPERTY list'), ('origins', '5 · TBLITEMORIGIN list'), ('coa', '6 · Chart of accounts list'), ('stores', '7 · WAREHOUSE_MASTER / store popup'), ('next_code', '8 · Next ITEMCODE (MAX per branch)'), ('item_load', '9 · Load item header (short SELECT)'), ('mfg_lookup', '10 · ITEMMASTER by MANUFACTURERID'), ('alt_barcode', '11 · ITEMALTERNATEUOMMAP barcode'), ('ai_template', '12 · AI general-fill candidate scan (ITEMNAME LIKE)'), ('product_grid', '13 · Product list grid (no extra filters)')]
    im_cfg_panels = []
    for sid, title in panel_meta:
        sq, pr = bundles[sid]
        im_cfg_panels.append({'id': sid, 'title': title, 'sql': sq or '', 'params_json': json.dumps(_im_bind_preview_dict(pr), indent=2), 'has_sql': bool(sq)})
    index_ddls = _itemmaster_plan_index_ddls()
    wrapped_preview_hint = 'Execute wraps your SELECT as SELECT * FROM ( … ) WHERE ROWNUM <= {}'.format(row_limit)
    exec_kind = (request.values.get('execute') or '').strip().lower()
    exec_rows: Optional[List[Dict[str, Any]]] = None
    exec_cols: Optional[List[str]] = None
    exec_label = ''
    exec_error: Optional[str] = None
    if request.method == 'POST' and exec_kind:
        try:
            if exec_kind == 'indexes':
                exec_label = 'Performance indexes (DDL)'
                _ensure_itemmaster_performance_indexes(force=True)
                flash('CREATE INDEX statements were attempted on this tenant schema (existing indexes skipped; privileges/errors logged server-side).', 'info')
            else:
                pair = bundles.get(exec_kind)
                if pair and pair[0]:
                    labels = dict(panel_meta)
                    exec_label = labels.get(exec_kind, exec_kind)
                    wrapped = _im_sql_wrap_rownum_limit(pair[0], row_limit)
                    exec_cols, exec_rows = _fetch_rows(wrapped, dict(pair[1]))
                else:
                    exec_error = 'Could not build SQL for this action.'
        except Exception as exc:
            exec_error = str(exc)
    if exec_cols is None and exec_rows and (len(exec_rows) > 0):
        exec_cols = list(exec_rows[0].keys())
    last_execute = exec_kind if request.method == 'POST' else ''
    ai_arabic_missing_count = 0
    try:
        ai_arabic_missing_count = count_itemmaster_missing_itemnameara(cfg_loc)
    except Exception:
        ai_arabic_missing_count = 0
    cat_ai_arabic_missing_count = 0
    has_category_nameara = False
    try:
        has_category_nameara = ensure_category_nameara_column()
        if has_category_nameara:
            cat_ai_arabic_missing_count = count_category_missing_nameara(cfg_loc)
    except Exception:
        cat_ai_arabic_missing_count = 0
        has_category_nameara = False
    has_openai = bool((os.environ.get('OPENAI_API_KEY') or '').strip())
    base_alt_missing_count = 0
    try:
        base_alt_missing_count = count_itemmaster_missing_base_alternate(cfg_loc)
    except Exception:
        base_alt_missing_count = 0
    missing_account_count = 0
    try:
        from db import count_itemmaster_missing_accounts
        missing_account_count = count_itemmaster_missing_accounts(cfg_loc)
    except Exception:
        missing_account_count = 0
    return render_template(
        'itemmaster/itemmaster_data_config.html',
        title='Item Master · Data config',
        row_limit=row_limit,
        cfg_loc=cfg_loc,
        category_flag=category_flag,
        cat_use_location=cat_use_location,
        sample_item_code=sample_item_code,
        sample_mfg=sample_mfg,
        ai_word=ai_word,
        im_cfg_panels=im_cfg_panels,
        index_ddls=index_ddls,
        wrapped_preview_hint=wrapped_preview_hint,
        exec_label=exec_label,
        exec_error=exec_error,
        exec_cols=exec_cols or [],
        exec_rows=exec_rows if exec_rows is not None else [],
        last_execute=last_execute,
        ai_arabic_missing_count=ai_arabic_missing_count,
        cat_ai_arabic_missing_count=cat_ai_arabic_missing_count,
        has_category_nameara=has_category_nameara,
        has_openai=has_openai,
        ai_arabic_batch_default=_IM_AI_ARABIC_BATCH_DEFAULT,
        base_alt_missing_count=base_alt_missing_count,
        base_alt_batch_default=_IM_BASE_ALT_BATCH_DEFAULT,
        missing_account_count=missing_account_count,
        account_backfill_batch_default=250,
        price_import_max_rows=_IM_PRICE_IMPORT_MAX_ROWS,
        cost_import_batch_size=_IM_COST_IMPORT_BATCH_SIZE,
        store_stock_import_batch_default=_IM_STORE_STOCK_IMPORT_BATCH_DEFAULT,
    )


def _itemmaster_data_config_admin_json_guard():
    if not session.get('user'):
        return jsonify({'ok': False, 'error': 'Not logged in'}, 401)
    if str(session.get('user') or '').strip().lower() != 'admin':
        return jsonify({'ok': False, 'error': 'Available only for the admin user.'}, 403)
    return None


@bp.route('/itemmaster/data-config/missing-accounts-count', methods=['GET'])
def itemmaster_data_config_missing_accounts_count():
    """Count ITEMMASTER rows with missing account defaults for the branch."""
    denied = _itemmaster_data_config_admin_json_guard()
    if denied is not None:
        return denied
    try:
        loc = int((request.args.get('location_code') or _resolve_itemmaster_location_code()))
    except (TypeError, ValueError):
        loc = _resolve_itemmaster_location_code()
    from db import count_itemmaster_missing_accounts
    cnt = count_itemmaster_missing_accounts(loc)
    return jsonify({'ok': True, 'location_code': loc, 'missing_count': cnt})


@bp.route('/itemmaster/data-config/backfill-missing-accounts', methods=['POST'])
def itemmaster_data_config_backfill_missing_accounts():
    """Fill missing ITEMMASTER account columns with defaults in one bounded batch."""
    denied = _itemmaster_data_config_admin_json_guard()
    if denied is not None:
        return denied
    data = request.get_json(silent=True) or {}
    try:
        loc = int(data.get('location_code') or _resolve_itemmaster_location_code())
    except (TypeError, ValueError):
        loc = _resolve_itemmaster_location_code()
    try:
        batch_size = int(data.get('batch_size') or 250)
    except (TypeError, ValueError):
        batch_size = 250
    batch_size = max(1, min(batch_size, 1000))
    from db import bulk_update_itemmaster_missing_accounts_batch
    result = bulk_update_itemmaster_missing_accounts_batch(loc, limit=batch_size)
    if not isinstance(result, dict):
        result = {'errors': [str(result)], 'processed': 0, 'updated': 0}
    from db import count_itemmaster_missing_accounts
    remaining = result.get('remaining')
    if remaining is None:
        try:
            remaining = count_itemmaster_missing_accounts(loc)
        except Exception:
            remaining = 0
    try:
        processed = int(result.get('processed') or 0)
    except (TypeError, ValueError):
        processed = 0
    try:
        updated = int(result.get('updated') or 0)
    except (TypeError, ValueError):
        updated = 0
    try:
        remaining_i = int(remaining or 0)
    except (TypeError, ValueError):
        remaining_i = 0
    result['processed'] = processed
    result['updated'] = updated
    result['remaining'] = remaining_i
    result['done'] = bool(result.get('done')) or remaining_i <= 0 or processed <= 0
    if remaining_i > 0 and processed <= 0 and not result.get('errors'):
        result['errors'] = [
            'Missing account rows exist, but Oracle updated 0 rows in this batch. '
            'Try Refresh count; if it stays above 0, check ITEMMASTER account column types/permissions.'
        ]
    result['ok'] = not bool(result.get('errors'))
    result['success'] = bool(result['ok'])
    result['location_code'] = loc
    return jsonify(result, 200 if result['ok'] else 500)


@bp.route('/itemmaster/data-config/ai-arabic-missing-count', methods=['GET'])
def itemmaster_data_config_ai_arabic_missing_count():
    """Count ITEMMASTER rows with empty ITEMNAMEARA for the branch."""
    denied = _itemmaster_data_config_admin_json_guard()
    if denied is not None:
        return denied
    try:
        loc = int((request.args.get('location_code') or _resolve_itemmaster_location_code()))
    except (TypeError, ValueError):
        loc = _resolve_itemmaster_location_code()
    cnt = count_itemmaster_missing_itemnameara(loc)
    return jsonify({'ok': True, 'location_code': loc, 'missing_count': cnt, 'has_openai': bool((os.environ.get('OPENAI_API_KEY') or '').strip())})


@bp.route('/itemmaster/data-config/ai-arabic-bulk', methods=['POST'])
def itemmaster_data_config_ai_arabic_bulk():
    """Translate ITEMNAME → ITEMNAMEARA (AI/fallback) for rows where Arabic is null/empty."""
    denied = _itemmaster_data_config_admin_json_guard()
    if denied is not None:
        return denied
    payload = request.get_json(silent=True) or {}
    try:
        loc = int(payload.get('location_code') or _resolve_itemmaster_location_code())
    except (TypeError, ValueError):
        loc = _resolve_itemmaster_location_code()
    try:
        offset = max(0, int(payload.get('offset') or 0))
    except (TypeError, ValueError):
        offset = 0
    try:
        batch_size = int(payload.get('batch_size') or _IM_AI_ARABIC_BATCH_DEFAULT)
    except (TypeError, ValueError):
        batch_size = _IM_AI_ARABIC_BATCH_DEFAULT
    batch_size = max(1, min(batch_size, _IM_AI_ARABIC_BATCH_MAX))
    rows = fetch_itemmaster_missing_itemnameara_batch(loc, offset, batch_size)
    updated = skipped = failed = 0
    errors: List[str] = []
    samples: List[Dict[str, Any]] = []
    for row in rows:
        ic = int(row.get('itemcode') or 0)
        name = str(row.get('itemname') or '').strip()
        if not ic or not name:
            skipped += 1
            continue
        ara, src = _translate_item_name_to_arabic(name)
        if not ara:
            failed += 1
            if len(errors) < 30:
                errors.append(f'Item {ic}: could not translate "{name[:60]}".')
            continue
        try:
            if update_itemmaster_itemnameara_if_empty(loc, ic, ara):
                updated += 1
                if len(samples) < 8:
                    samples.append({'itemcode': ic, 'itemname': name[:80], 'itemnameara': ara[:80], 'source': src})
            else:
                skipped += 1
        except Exception as exc:
            failed += 1
            if len(errors) < 30:
                errors.append(f'Item {ic}: {exc}')
    remaining = count_itemmaster_missing_itemnameara(loc)
    next_offset = offset + len(rows)
    done = len(rows) < batch_size or remaining <= 0
    return jsonify({
        'ok': True,
        'location_code': loc,
        'processed': len(rows),
        'updated': updated,
        'skipped': skipped,
        'failed': failed,
        'errors': errors,
        'samples': samples,
        'remaining': remaining,
        'next_offset': next_offset,
        'done': done,
        'has_openai': bool((os.environ.get('OPENAI_API_KEY') or '').strip()),
    })


@bp.route('/itemmaster/data-config/ai-category-arabic-missing-count', methods=['GET'])
def itemmaster_data_config_ai_category_arabic_missing_count():
    """Count CATEGORY rows with empty NAMEARA for the branch."""
    denied = _itemmaster_data_config_admin_json_guard()
    if denied is not None:
        return denied
    try:
        loc = int((request.args.get('location_code') or _resolve_itemmaster_location_code()))
    except (TypeError, ValueError):
        loc = _resolve_itemmaster_location_code()
    ready = ensure_category_nameara_column()
    cnt = count_category_missing_nameara(loc) if ready else 0
    return jsonify({
        'ok': True,
        'location_code': loc,
        'missing_count': cnt,
        'has_nameara_column': ready,
        'has_openai': bool((os.environ.get('OPENAI_API_KEY') or '').strip()),
    })


@bp.route('/itemmaster/data-config/ai-category-arabic-bulk', methods=['POST'])
def itemmaster_data_config_ai_category_arabic_bulk():
    """Translate CATEGORY.NAME → NAMEARA (AI/fallback) where Arabic is null/empty."""
    denied = _itemmaster_data_config_admin_json_guard()
    if denied is not None:
        return denied
    if not ensure_category_nameara_column():
        return jsonify({'ok': False, 'error': 'CATEGORY.NAMEARA column is not available.'}, 500)
    payload = request.get_json(silent=True) or {}
    try:
        loc = int(payload.get('location_code') or _resolve_itemmaster_location_code())
    except (TypeError, ValueError):
        loc = _resolve_itemmaster_location_code()
    try:
        offset = max(0, int(payload.get('offset') or 0))
    except (TypeError, ValueError):
        offset = 0
    try:
        batch_size = int(payload.get('batch_size') or _IM_AI_ARABIC_BATCH_DEFAULT)
    except (TypeError, ValueError):
        batch_size = _IM_AI_ARABIC_BATCH_DEFAULT
    batch_size = max(1, min(batch_size, _IM_AI_ARABIC_BATCH_MAX))
    rows = fetch_category_missing_nameara_batch(loc, offset, batch_size)
    updated = skipped = failed = 0
    errors: List[str] = []
    samples: List[Dict[str, Any]] = []
    for row in rows:
        code = int(row.get('code') or 0)
        flag = str(row.get('flag') or '').strip().upper()[:1]
        name = str(row.get('name') or '').strip()
        if not code or not name or flag not in ('M', 'D', 'C'):
            skipped += 1
            continue
        ara, src = _translate_category_name_to_arabic(name)
        if not ara:
            failed += 1
            if len(errors) < 30:
                errors.append(f'{flag}/{code}: could not translate "{name[:60]}".')
            continue
        try:
            if update_category_nameara_if_empty(loc, code, flag, ara):
                updated += 1
                if len(samples) < 8:
                    samples.append({
                        'code': code,
                        'flag': flag,
                        'name': name[:80],
                        'nameara': ara[:80],
                        'source': src,
                    })
            else:
                skipped += 1
        except Exception as exc:
            failed += 1
            if len(errors) < 30:
                errors.append(f'{flag}/{code}: {exc}')
    remaining = count_category_missing_nameara(loc)
    next_offset = offset + len(rows)
    done = len(rows) < batch_size or remaining <= 0
    return jsonify({
        'ok': True,
        'location_code': loc,
        'processed': len(rows),
        'updated': updated,
        'skipped': skipped,
        'failed': failed,
        'errors': errors,
        'samples': samples,
        'remaining': remaining,
        'next_offset': next_offset,
        'done': done,
        'has_openai': bool((os.environ.get('OPENAI_API_KEY') or '').strip()),
    })


@bp.route('/itemmaster/data-config/base-alternate-missing-count', methods=['GET'])
def itemmaster_data_config_base_alternate_missing_count():
    """Count ITEMMASTER rows without a base IS_BASE row in ITEMALTERNATEUOMMAP."""
    denied = _itemmaster_data_config_admin_json_guard()
    if denied is not None:
        return denied
    try:
        loc = int((request.args.get('location_code') or _resolve_itemmaster_location_code()))
    except (TypeError, ValueError):
        loc = _resolve_itemmaster_location_code()
    cnt = count_itemmaster_missing_base_alternate(loc)
    return jsonify({'ok': True, 'location_code': loc, 'missing_count': cnt})


@bp.route('/itemmaster/data-config/base-alternate-bulk', methods=['POST'])
def itemmaster_data_config_base_alternate_bulk():
    """Create or refresh IS_BASE rows in ITEMALTERNATEUOMMAP from ITEMMASTER."""
    denied = _itemmaster_data_config_admin_json_guard()
    if denied is not None:
        return denied
    payload = request.get_json(silent=True) or {}
    try:
        loc = int(payload.get('location_code') or _resolve_itemmaster_location_code())
    except (TypeError, ValueError):
        loc = _resolve_itemmaster_location_code()
    try:
        offset = max(0, int(payload.get('offset') or 0))
    except (TypeError, ValueError):
        offset = 0
    try:
        batch_size = int(payload.get('batch_size') or _IM_BASE_ALT_BATCH_DEFAULT)
    except (TypeError, ValueError):
        batch_size = _IM_BASE_ALT_BATCH_DEFAULT
    batch_size = max(1, min(batch_size, _IM_BASE_ALT_BATCH_MAX))
    missing_only = bool(payload.get('missing_only', True))
    if str(payload.get('missing_only', '')).strip().lower() in ('0', 'false', 'no'):
        missing_only = False
    try:
        result = bulk_sync_itemmaster_base_alternate_batch(
            loc, offset, batch_size, missing_only=missing_only,
        )
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}, 500)
    result['ok'] = True
    result['location_code'] = loc
    result['missing_only'] = missing_only
    return jsonify(result)


@bp.route('/itemmaster/data-config/store-stock-import-map', methods=['GET'])
def itemmaster_data_config_store_stock_import_map():
    """Preview STOREn → WHnnn mappings for store stock import."""
    denied = _itemmaster_data_config_admin_json_guard()
    if denied is not None:
        return denied
    try:
        loc = int((request.args.get('location_code') or _resolve_itemmaster_location_code()))
    except (TypeError, ValueError):
        loc = _resolve_itemmaster_location_code()
    from db import build_itemmaster_store_warehouse_import_map, count_itemmaster_rows_for_store_stock_import
    plan = build_itemmaster_store_warehouse_import_map(loc)
    total = count_itemmaster_rows_for_store_stock_import(loc)
    return jsonify({
        'ok': bool(plan.get('ok')),
        'location_code': loc,
        'total_items': total,
        'mappings': plan.get('mappings') or [],
        'mapping_errors': plan.get('errors') or [],
        'store_columns': plan.get('store_columns') or [],
    })


@bp.route('/itemmaster/data-config/store-stock-import', methods=['POST'])
def itemmaster_data_config_store_stock_import():
    """Import ITEMMASTER STOREn qty into WAREHOUSE_STOCK (STORE1→WH001, …)."""
    denied = _itemmaster_data_config_admin_json_guard()
    if denied is not None:
        return denied
    payload = request.get_json(silent=True) or {}
    try:
        loc = int(payload.get('location_code') or _resolve_itemmaster_location_code())
    except (TypeError, ValueError):
        loc = _resolve_itemmaster_location_code()
    try:
        offset = max(0, int(payload.get('offset') or 0))
    except (TypeError, ValueError):
        offset = 0
    try:
        batch_size = int(payload.get('batch_size') or _IM_STORE_STOCK_IMPORT_BATCH_DEFAULT)
    except (TypeError, ValueError):
        batch_size = _IM_STORE_STOCK_IMPORT_BATCH_DEFAULT
    batch_size = max(1, min(batch_size, _IM_STORE_STOCK_IMPORT_BATCH_MAX))
    from db import import_itemmaster_store_stock_to_warehouse_batch
    try:
        result = import_itemmaster_store_stock_to_warehouse_batch(
            loc,
            offset,
            batch_size,
            updated_by=str(session.get('user') or ''),
        )
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}, 500)
    try:
        items_n = int(result.get('items') or result.get('processed') or 0)
    except (TypeError, ValueError):
        items_n = 0
    if items_n <= 0:
        result['done'] = True
        result['remaining'] = 0
    result['ok'] = not bool(result.get('errors'))
    result['success'] = bool(result.get('ok'))
    result['location_code'] = loc
    return jsonify(result, 200 if result.get('ok') else 500)


@bp.route('/itemmaster/data-config/price-import-template.xlsx', methods=['GET'])
def itemmaster_data_config_price_import_template():
    """Download Excel template for barcode-based price updates."""
    denied = _itemmaster_data_config_admin_json_guard()
    if denied is not None:
        return denied
    try:
        from openpyxl import Workbook
    except ImportError:
        return jsonify({'ok': False, 'error': 'Excel template requires openpyxl (pip install openpyxl).'}, 500)
    wb = Workbook()
    ws = wb.active
    ws.title = 'Price Update'
    ws.append([
        'Barcode',
        'LocationCode',
        'CostPrice',
        'RetailPrice',
        'WholesalePrice',
        'ThirdPrice',
        'BranchPrice',
    ])
    ws.append(['1234567890123', '', 10.5, 15.0, 12.0, '', ''])
    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    fname = f'itemmaster_price_update_template_{datetime.now().strftime("%Y%m%d")}.xlsx'
    return Response(
        bio.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename="{fname}"'},
    )


@bp.route('/itemmaster/data-config/price-import', methods=['POST'])
def itemmaster_data_config_price_import():
    """Import retail/wholesale/etc. prices by barcode from Excel."""
    denied = _itemmaster_data_config_admin_json_guard()
    if denied is not None:
        return denied
    try:
        loc = int((request.form.get('location_code') or request.args.get('location_code') or _resolve_itemmaster_location_code()))
    except (TypeError, ValueError):
        loc = _resolve_itemmaster_location_code()
    fobj = request.files.get('excel_file') or request.files.get('file')
    if not fobj or not getattr(fobj, 'filename', None):
        return jsonify({'ok': False, 'error': 'Choose an Excel file (.xlsx).'}, 400)
    fname = str(fobj.filename or '').lower()
    if not fname.endswith(('.xlsx', '.xlsm')):
        return jsonify({'ok': False, 'error': 'Please upload a .xlsx or .xlsm file.'}, 400)
    raw = fobj.read()
    if not isinstance(raw, bytes):
        raw = bytes(raw) if raw else b''
    if len(raw) > _IM_PRICE_IMPORT_MAX_FILE_BYTES:
        return jsonify({'ok': False, 'error': 'File too large (max 10 MB).'}, 400)
    rows, perr = _parse_xlsx_first_sheet(raw, _IM_PRICE_IMPORT_MAX_ROWS)
    if perr:
        return jsonify({'ok': False, 'error': perr}, 400)
    result = import_itemmaster_prices_from_excel_rows(loc, rows, max_rows=_IM_PRICE_IMPORT_MAX_ROWS)
    errs = result.get('errors') or []
    return jsonify({
        'ok': True,
        'partial': bool(errs),
        'location_code': loc,
        'updated': result.get('updated', 0),
        'failed': result.get('failed', 0),
        'processed': result.get('processed', 0),
        'errors': errs[:100],
        'error_count': len(errs),
    })


@bp.route('/itemmaster/data-config/cost-import-template.xlsx', methods=['GET'])
def itemmaster_data_config_cost_import_template():
    """Download Excel template for item-code bulk COSTPRICE updates."""
    denied = _itemmaster_data_config_admin_json_guard()
    if denied is not None:
        return denied
    try:
        from openpyxl import Workbook
    except ImportError:
        return jsonify({'ok': False, 'error': 'Excel template requires openpyxl (pip install openpyxl).'}, 500)
    wb = Workbook()
    ws = wb.active
    ws.title = 'Cost Update'
    ws.append(['ItemCode', 'LocationCode', 'CostPrice'])
    ws.append([1001, '', 12.5])
    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    fname = f'itemmaster_costprice_update_template_{datetime.now().strftime("%Y%m%d")}.xlsx'
    return Response(
        bio.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename="{fname}"'},
    )


@bp.route('/itemmaster/data-config/cost-import', methods=['POST'])
def itemmaster_data_config_cost_import():
    """Import COSTPRICE by item code from Excel (ITEMMASTER + base alternate row). Batched to avoid proxy timeouts."""
    denied = _itemmaster_data_config_admin_json_guard()
    if denied is not None:
        return denied
    try:
        batch_offset = max(0, int((request.form.get('batch_offset') or '0').strip()))
    except (TypeError, ValueError):
        batch_offset = 0
    import_token = (request.form.get('import_token') or '').strip()
    if batch_offset > 0 and not import_token:
        return jsonify({'ok': False, 'error': 'Import session expired. Start the import again from the beginning.'}, 409)
    try:
        loc = int((request.form.get('location_code') or request.args.get('location_code') or _resolve_itemmaster_location_code()))
    except (TypeError, ValueError):
        loc = _resolve_itemmaster_location_code()
    rows: List[Dict[str, Any]] = []
    try:
        if batch_offset <= 0:
            fobj = request.files.get('excel_file') or request.files.get('file')
            if not fobj or not getattr(fobj, 'filename', None):
                return jsonify({'ok': False, 'error': 'Choose an Excel file (.xlsx).'}, 400)
            fname = str(fobj.filename or '').lower()
            if not fname.endswith(('.xlsx', '.xlsm')):
                return jsonify({'ok': False, 'error': 'Please upload a .xlsx or .xlsm file.'}, 400)
            raw = fobj.read()
            if not isinstance(raw, bytes):
                raw = bytes(raw) if raw else b''
            if len(raw) > _IM_PRICE_IMPORT_MAX_FILE_BYTES:
                return jsonify({'ok': False, 'error': 'File too large (max 10 MB).'}, 400)
            rows, perr = _parse_xlsx_first_sheet(raw, _IM_PRICE_IMPORT_MAX_ROWS)
            if perr:
                return jsonify({'ok': False, 'error': perr}, 400)
            import_token = secrets.token_hex(16)
            rows_path = _im_import_stage_path(import_token, 'cost_rows.pkl')
            with open(rows_path, 'wb') as fh:
                pickle.dump(rows, fh, protocol=pickle.HIGHEST_PROTOCOL)
            state_path = _im_import_stage_path(import_token, 'cost_state.pkl')
            if state_path.is_file():
                state_path.unlink()
        else:
            rows_path = _im_import_stage_path(import_token, 'cost_rows.pkl')
            if not rows_path.is_file():
                return jsonify({
                    'ok': False,
                    'error': 'Import session expired or server was restarted. Upload the file again.',
                }, 409)
            with open(rows_path, 'rb') as fh:
                rows = pickle.load(fh)
        import_state: Dict[str, Any] = {}
        state_path = _im_import_stage_path(import_token, 'cost_state.pkl')
        if state_path.is_file():
            with open(state_path, 'rb') as fh:
                import_state = pickle.load(fh)
        if batch_offset <= 0:
            import_state['row_total'] = _im_import_count_data_rows(rows)
            import_state['location_code'] = loc
        loc = int(import_state.get('location_code') or loc)
        result = import_itemmaster_costprice_from_excel_rows(
            loc,
            rows,
            max_rows=_IM_PRICE_IMPORT_MAX_ROWS,
            row_offset=batch_offset,
            row_limit=_IM_COST_IMPORT_BATCH_SIZE,
            import_state=import_state,
        )
        import_state = result.get('import_state') or import_state
        with open(state_path, 'wb') as fh:
            pickle.dump(import_state, fh, protocol=pickle.HIGHEST_PROTOCOL)
        processed_total = int(import_state.get('processed_total') or 0)
        row_total = int(import_state.get('row_total') or 0)
        cap = min(row_total, _IM_PRICE_IMPORT_MAX_ROWS) if row_total else _IM_PRICE_IMPORT_MAX_ROWS
        done = processed_total >= cap or int(result.get('batch_processed') or 0) == 0 and batch_offset > 0
        if done:
            for suffix in ('cost_rows.pkl', 'cost_state.pkl'):
                try:
                    p = _im_import_stage_path(import_token, suffix)
                    if p.is_file():
                        p.unlink()
                except Exception:
                    pass
        errs = result.get('errors') or []
        return jsonify({
            'ok': True,
            'partial': bool(errs),
            'location_code': loc,
            'updated': int(result.get('updated') or 0),
            'failed': int(result.get('failed') or 0),
            'processed': processed_total,
            'errors': errs[:100],
            'error_count': len(errs),
            'import_token': import_token,
            'batch_offset': batch_offset,
            'next_batch_offset': batch_offset + _IM_COST_IMPORT_BATCH_SIZE if not done else batch_offset,
            'done': done,
            'processed_total': processed_total,
            'row_total': row_total,
        })
    except Exception as exc:
        if import_token:
            for suffix in ('cost_rows.pkl', 'cost_state.pkl'):
                try:
                    p = _im_import_stage_path(import_token, suffix)
                    if p.is_file():
                        p.unlink()
                except Exception:
                    pass
        logging.getLogger(__name__).exception('itemmaster_data_config_cost_import failed')
        return jsonify({'ok': False, 'error': str(exc) or 'Import failed.'}, 500)


@bp.route('/productlist')
def productlist():
    """Product List page"""
    _t0 = time.perf_counter()
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    location_code_int = session.get('location_code')
    if location_code_int is None:
        try:
            location_info = get_location_info_by_dbkey(None)
            location_code_int = location_info.get('locationcode')
            if location_code_int is not None:
                session['location_code'] = location_code_int
        except Exception as e:
            print(f'[DEBUG productlist] Could not get location_code from LOCATIONMASTER: {e}')
            location_code_int = None
    search = request.args.get('search', '').strip()
    stock_filter = request.args.get('stockFilter', '').strip() or None
    brand_code = request.args.get('brandCode', '').strip()
    category_code = request.args.get('categoryCode', '').strip()
    supplier_code = request.args.get('supplierCode', '').strip()
    item_codes_str = request.args.get('itemCodes', '').strip()
    item_codes = None
    if item_codes_str:
        try:
            item_codes = [int(code.strip()) for code in item_codes_str.split(',') if code.strip()]
        except ValueError:
            item_codes = None
    brand_code_int = int(brand_code) if brand_code and brand_code.isdigit() else None
    category_code_int = int(category_code) if category_code and category_code.isdigit() else None
    sort_column = request.args.get('sort', '').strip()
    sort_order = request.args.get('order', '').strip()
    page = request.args.get('page', '1')
    try:
        page = int(page)
        if page < 1:
            page = 1
    except ValueError:
        page = 1
    items_per_page = 50
    _t_query = time.perf_counter()
    items, total_count = get_items_list(location_code_int, search if search else None, limit=None, stock_filter=stock_filter, brand_code=brand_code_int, category_code=category_code_int, supplier_code=supplier_code if supplier_code else None, item_codes=item_codes, order_by=sort_column if sort_column else None, order_direction=sort_order if sort_order else None, page=page, items_per_page=items_per_page)
    _t_render = time.perf_counter()
    # KPIs (especially inventory value) are deferred to /productlist/api/kpis so first paint is fast.
    item_kpis = {
        'total_items': int(total_count or 0),
        'active_items': None,
        'inactive_items': None,
        'low_stock_items': None,
        'inventory_value': None,
        'deferred': True,
    }
    total_pages = (total_count + items_per_page - 1) // items_per_page if total_count > 0 else 1
    is_admin = str(session.get('user') or '').strip().lower() == 'admin'
    im_import_nonce = get_or_issue_global_save_nonce() if is_admin else ''
    resp = render_template(
        'itemmaster/productlist.html',
        items=items,
        search=search,
        location_code=location_code_int,
        current_page=page,
        total_pages=total_pages,
        total_count=total_count,
        items_per_page=items_per_page,
        item_kpis=item_kpis,
        im_import_nonce=im_import_nonce,
        productlist_items_api_url=url_for('itemmaster.api_productlist_items'),
        productlist_kpis_api_url=url_for('itemmaster.api_productlist_kpis'),
    )
    if _itemmaster_timing_log_enabled():
        _t_end = time.perf_counter()
        query_ms = (_t_render - _t_query) * 1000.0
        render_ms = (_t_end - _t_render) * 1000.0
        total_ms = (_t_end - _t0) * 1000.0
        has_filters = bool(stock_filter or brand_code_int or category_code_int or supplier_code or item_codes)
        print(
            f'[TIMING itemmaster] productlist loc={location_code_int} page={page} rows={len(items or [])} '
            f'total={total_count} search={1 if search else 0} filters={1 if has_filters else 0} '
            f'query_ms={query_ms:.1f} kpi_ms=0.0(deferred) render_ms={render_ms:.1f} total_ms={total_ms:.1f}'
        )
    return resp

@bp.route('/itemmaster/import-template', methods=['GET'])
def itemmaster_import_template():
    """Sample ITEMMASTER Excel for admin bulk import."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if str(session.get('user') or '').strip().lower() != 'admin':
        flash('Excel template is available only for the admin user.', 'warning')
        return redirect(url_for('itemmaster.productlist'))
    try:
        from openpyxl import Workbook
    except ImportError:
        flash('openpyxl is required for Excel templates.', 'error')
        return redirect(url_for('itemmaster.productlist'))
    wb = Workbook()
    ws = wb.active
    ws.title = 'Items'
    ws.append(['Action', 'LOCATIONCODE', 'ITEMCODE', 'ITEMNAME', 'MANUFACTURERID', 'CATEGORYCODE', 'BRANDCODE', 'SIZECODE', 'COLORCODE', 'BASEUOM', 'COSTPRICE', 'RETAILPRICE', 'WHOLESALEPRICE', 'THIRDPRICE', 'BRANCHPRICE', 'MAXIMUMLEVEL', 'REORDERLEVEL', 'DISCOUNTFLAG', 'SUPCODE', 'DEPARTMENTCODE', 'MAINCATEGORY', 'REBATE', 'ITEMNAMEARA', 'DESCRIPTION', 'PROPERTY', 'ORIGIN', 'QUANTITYLIMIT', 'VATPERCENT', 'DEFAULT_WAREHOUSE_ID'])
    ws.append(['CREATE', '', '', 'EXAMPLE IMPORT ITEM', 'BARCODE123', 0, 0, 0, 0, 'PCS', 10, 15, 14, 13, 12, 0, 0, 'N', 0, 0, 0, 0, '', '', 0, 0, 0, 0, ''])
    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    return Response(bio.getvalue(), mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers={'Content-Disposition': 'attachment; filename=itemmaster_import_template.xlsx'})

@bp.route('/itemmaster/import-excel', methods=['POST'])
def itemmaster_import_excel():
    """Bulk create/update ITEMMASTER from .xlsx (admin only). Processes in batches to avoid proxy timeouts."""
    if not session.get('user'):
        return jsonify({'ok': False, 'error': 'Not logged in'}, 401)
    if str(session.get('user') or '').strip().lower() != 'admin':
        return jsonify({'ok': False, 'error': 'Excel import is available only for the admin user.'}, 403)
    try:
        batch_offset = max(0, int((request.form.get('batch_offset') or '0').strip()))
    except (TypeError, ValueError):
        batch_offset = 0
    import_token = (request.form.get('import_token') or '').strip()
    nonce = extract_submitted_save_nonce(request)
    if batch_offset <= 0:
        if not verify_consume_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY, nonce):
            return jsonify({
                'ok': False,
                'error': 'Invalid or expired save token. Reload Item Master list, then import again (do not use an old browser tab).',
                'replay_blocked': True,
                'save_nonce': issue_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY),
            }, 409)
    else:
        if not import_token:
            return jsonify({
                'ok': False,
                'error': 'Import session expired. Start the import again from the beginning.',
                'save_nonce': issue_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY),
            }, 409)
    rows: List[Dict[str, Any]] = []
    try:
        if batch_offset <= 0:
            fobj = request.files.get('excel_file') or request.files.get('file')
            if not fobj or not getattr(fobj, 'filename', None):
                return jsonify({'ok': False, 'error': 'Choose an Excel file (.xlsx).', 'save_nonce': issue_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY)}, 400)
            fname = str(fobj.filename or '').lower()
            if not fname.endswith(('.xlsx', '.xlsm')):
                return jsonify({'ok': False, 'error': 'Please upload a .xlsx or .xlsm file.', 'save_nonce': issue_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY)}, 400)
            raw = fobj.read()
            if not isinstance(raw, bytes):
                raw = bytes(raw) if raw else b''
            if len(raw) > _IM_IMPORT_MAX_FILE_BYTES:
                return jsonify({'ok': False, 'error': 'File too large (max 50 MB).', 'save_nonce': issue_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY)}, 400)
            rows, perr = _itemmaster_parse_xlsx(raw)
            if perr:
                return jsonify({'ok': False, 'error': perr, 'save_nonce': issue_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY)}, 400)
            import_token = secrets.token_hex(16)
            rows_path = _im_import_stage_path(import_token, 'rows.pkl')
            with open(rows_path, 'wb') as fh:
                pickle.dump(rows, fh, protocol=pickle.HIGHEST_PROTOCOL)
            state_path = _im_import_stage_path(import_token, 'state.pkl')
            if state_path.is_file():
                state_path.unlink()
        else:
            rows_path = _im_import_stage_path(import_token, 'rows.pkl')
            if not rows_path.is_file():
                return jsonify({
                    'ok': False,
                    'error': 'Import session expired or server was restarted. Upload the file again.',
                    'save_nonce': issue_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY),
                }, 409)
            with open(rows_path, 'rb') as fh:
                rows = pickle.load(fh)
        import_state: Dict[str, Any] = {}
        state_path = _im_import_stage_path(import_token, 'state.pkl')
        if state_path.is_file():
            with open(state_path, 'rb') as fh:
                import_state = pickle.load(fh)
        if batch_offset <= 0:
            import_state['row_total'] = _im_import_count_data_rows(rows)
        loc = _resolve_itemmaster_location_code()
        result = import_itemmaster_from_excel_rows(
            loc,
            rows,
            max_rows=_IM_IMPORT_MAX_ROWS,
            row_offset=batch_offset,
            row_limit=_IM_IMPORT_BATCH_SIZE,
            import_state=import_state,
        )
        import_state = result.get('import_state') or import_state
        with open(state_path, 'wb') as fh:
            pickle.dump(import_state, fh, protocol=pickle.HIGHEST_PROTOCOL)
        processed_total = int(import_state.get('processed_total') or 0)
        row_total = int(import_state.get('row_total') or 0)
        cap = min(row_total, _IM_IMPORT_MAX_ROWS) if row_total else _IM_IMPORT_MAX_ROWS
        done = processed_total >= cap or int(result.get('batch_processed') or 0) == 0 and batch_offset > 0
        if done:
            _im_import_cleanup_staging(import_token)
        errs = result.get('errors') or []
        return jsonify({
            'ok': True,
            'partial': bool(errs),
            'created': int(result.get('created') or 0),
            'updated': int(result.get('updated') or 0),
            'skipped': int(result.get('skipped') or 0),
            'errors': errs[:50],
            'error_count': len(errs),
            'import_token': import_token,
            'batch_offset': batch_offset,
            'next_batch_offset': batch_offset + _IM_IMPORT_BATCH_SIZE if not done else batch_offset,
            'done': done,
            'processed_total': processed_total,
            'row_total': row_total,
            'save_nonce': issue_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY),
        })
    except Exception as exc:
        if import_token:
            _im_import_cleanup_staging(import_token)
        return jsonify({
            'ok': False,
            'error': f'Import failed: {exc}',
            'save_nonce': issue_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY),
        }, 500)

@bp.route('/category-master')
def category_master_list():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    loc = _resolve_itemmaster_location_code()
    tree = get_category_master_tree(location_code=loc)
    flat = get_category_master_flat(tree, location_code=loc)
    cm_create_m_once = _issue_cm_create_m()
    is_admin = str(session.get('user') or '').strip().lower() == 'admin'
    cm_import_nonce = get_or_issue_global_save_nonce() if is_admin else ''
    return render_template('itemmaster/category_master_list.html', tree=tree, flat_rows=flat, cm_create_m_once=cm_create_m_once, is_admin_user=is_admin, cm_import_nonce=cm_import_nonce)

@bp.route('/category-master/issue-once', methods=['GET'])
def category_master_issue_once():
    """One-shot tokens for Category Master create-D/C and edits (paired with fresh save_nonce)."""
    if not session.get('user'):
        return jsonify({'ok': False, 'error': 'Not logged in'}, 401)
    intent = (request.args.get('intent') or '').strip().lower()
    once: Optional[str] = None
    if intent == 'create_d':
        try:
            mc = int(request.args.get('main_code') or 0)
        except (TypeError, ValueError):
            mc = 0
        if mc <= 0:
            return jsonify({'ok': False, 'error': 'main_code is required for create_d.'}, 400)
        once = _issue_cm_create_d(mc)
    elif intent == 'create_c':
        try:
            dc = int(request.args.get('d_code') or 0)
        except (TypeError, ValueError):
            dc = 0
        if dc <= 0:
            return jsonify({'ok': False, 'error': 'd_code is required for create_c.'}, 400)
        once = _issue_cm_create_c(dc)
    elif intent == 'edit':
        fl = (request.args.get('flag') or '').strip().upper()[:1]
        if fl not in ('M', 'D', 'C'):
            return jsonify({'ok': False, 'error': 'flag must be M, D, or C.'}, 400)
        try:
            cd = int(request.args.get('code') or 0)
        except (TypeError, ValueError):
            cd = 0
        if cd <= 0:
            return jsonify({'ok': False, 'error': 'Valid code is required.'}, 400)
        once = _issue_cm_edit_once(fl, cd)
    else:
        return jsonify({'ok': False, 'error': 'intent must be create_d, create_c, or edit.'}, 400)
    return jsonify({'ok': True, 'once': once, 'save_nonce': issue_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY)})

@bp.route('/category-master/save', methods=['POST'])
def category_master_save():
    if not session.get('user'):
        return jsonify({'ok': False, 'error': 'Not logged in'}, 401)
    data = request.get_json(silent=True) or {}
    sub = extract_submitted_save_nonce(request)
    if not verify_consume_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY, sub):
        return _uom_json_nonce_error(409, 'Duplicate or invalid submit. Reload the Category Master page if this persists.')
    mode = (data.get('mode') or '').strip().lower()
    flag = (data.get('flag') or '').strip().upper()[:1]
    loc = _resolve_itemmaster_location_code()
    if mode == 'update':
        try:
            code = int(data.get('code') or 0)
        except (TypeError, ValueError):
            return _uom_json_nonce_error(400, 'Valid code is required')
        if code <= 0 or flag not in ('M', 'D', 'C'):
            return _uom_json_nonce_error(400, 'Code and level (M/D/C) are required')
        once_e = (data.get('cm_edit_once') or '').strip()
        if not _verify_consume_cm_edit_once(flag, code, once_e):
            return _uom_json_nonce_error(400, 'That save was skipped (duplicate submit or session lock). Choose Edit again.')
        name = (data.get('name') or '').strip()
        ok, err = update_category_master_name(code, flag, name, location_code=loc)
        if not ok:
            return _uom_json_nonce_error(400, err or 'Update failed')
        append_master_activity(username=_sess_user_for_log(), action='UPDATE', entity='item_category_master', summary=f"location={loc}, flag={flag}, code={code}, name={(name or '')[:120]}", detail={'locationcode': loc, 'flag': flag, 'code': code, 'name': name})
        return _uom_json_ok()
    if mode != 'create':
        return _uom_json_nonce_error(400, 'Invalid mode')
    name = (data.get('name') or '').strip()
    if flag == 'M':
        once_m = (data.get('cm_create_m_once') or '').strip()
        if not _verify_consume_cm_create_m(once_m):
            return _uom_json_nonce_error(400, 'That save was skipped (duplicate submit or session lock). Reload Category Master.')
        ok, err, new_code = insert_category_main(name, loc)
        if not ok:
            return _uom_json_nonce_error(400, err or 'Insert failed')
        append_master_activity(username=_sess_user_for_log(), action='CREATE', entity='item_category_master', summary=f"location={loc}, flag=M, code={new_code}, name={(name or '')[:120]}", detail={'locationcode': loc, 'flag': 'M', 'code': new_code, 'name': name})
        return _uom_json_ok({'code': new_code})
    if flag == 'D':
        try:
            main_code = int(data.get('main_code') or 0)
        except (TypeError, ValueError):
            main_code = 0
        if main_code <= 0:
            return _uom_json_nonce_error(400, 'Main category code is required')
        once_d = (data.get('cm_create_d_once') or '').strip()
        if not _verify_consume_cm_create_d(main_code, once_d):
            return _uom_json_nonce_error(400, 'Session lock missing or reused. Choose + Category again.')
        ok, err, new_code = insert_category_dept(name, main_code, loc)
        if not ok:
            return _uom_json_nonce_error(400, err or 'Insert failed')
        append_master_activity(username=_sess_user_for_log(), action='CREATE', entity='item_category_master', summary=f"location={loc}, flag=D, code={new_code}, main={main_code}, name={(name or '')[:120]}", detail={'locationcode': loc, 'flag': 'D', 'code': new_code, 'main_code': main_code, 'name': name})
        return _uom_json_ok({'code': new_code})
    if flag == 'C':
        try:
            d_code = int(data.get('d_code') or 0)
        except (TypeError, ValueError):
            d_code = 0
        if d_code <= 0:
            return _uom_json_nonce_error(400, 'Category (D) code is required')
        once_c = (data.get('cm_create_c_once') or '').strip()
        if not _verify_consume_cm_create_c(d_code, once_c):
            return _uom_json_nonce_error(400, 'Session lock missing or reused. Choose + Micro again.')
        main_c = data.get('main_code')
        try:
            main_opt = int(main_c) if main_c is not None and str(main_c).strip() != '' else None
        except (TypeError, ValueError):
            main_opt = None
        ok, err, new_code = insert_category_micro(name, d_code, loc, main_opt)
        if not ok:
            return _uom_json_nonce_error(400, err or 'Insert failed')
        append_master_activity(username=_sess_user_for_log(), action='CREATE', entity='item_category_master', summary=f"location={loc}, flag=C, code={new_code}, d_code={d_code}, name={(name or '')[:120]}", detail={'locationcode': loc, 'flag': 'C', 'code': new_code, 'd_code': d_code, 'main_code': main_opt, 'name': name})
        return _uom_json_ok({'code': new_code})
    return _uom_json_nonce_error(400, 'Invalid flag')

@bp.route('/category-master/import-template', methods=['GET'])
def category_master_import_template():
    """Sample .xlsx for Category Master import (admin only)."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if str(session.get('user') or '').strip().lower() != 'admin':
        flash('Excel import template is available only for the admin user.', 'warning')
        return redirect(url_for('itemmaster.category_master_list'))
    try:
        from openpyxl import Workbook
    except ImportError:
        flash('openpyxl is required for Excel templates.', 'error')
        return redirect(url_for('itemmaster.category_master_list'))
    wb = Workbook()
    ws = wb.active
    ws.title = 'Categories'
    hdr = ['Action', 'LOCATIONCODE', 'CODE', 'NAME', 'FLAG', 'CATEGORYTYPE', 'ID', 'POINTS', 'ZONE', 'YEAR', 'DISCOUNT', 'INVOICEAMOUNT', 'VOUCHERAMOUNT', 'VOUCHERFLAG', 'PICKSTORE', 'PRICEPERCENTAGE', 'Main_Code', 'Category_Code']
    ws.append(hdr)
    ws.append(['CREATE', '', 101, 'FULL ROW MAIN', 'M', '', '', '', '', 0, 0, '', '', '', '', '', '', ''])
    ws.append(['CREATE', '', '', 'AUTO CODE MAIN', 'M', '', '', '', '', '', '', '', '', '', '', '', '', ''])
    ws.append(['UPDATE', '', 101, 'RENAMED', 'M', '', '', '', '', '', '', '', '', '', '', '', '', ''])
    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    return Response(bio.getvalue(), mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers={'Content-Disposition': 'attachment; filename=category_master_import_template.xlsx'})

@bp.route('/category-master/import-excel', methods=['POST'])
def category_master_import_excel():
    """Bulk create/update M/D/C rows from .xlsx (admin only)."""
    if not session.get('user'):
        return jsonify({'ok': False, 'error': 'Not logged in'}, 401)
    if str(session.get('user') or '').strip().lower() != 'admin':
        return jsonify({'ok': False, 'error': 'Excel import is available only for the admin user.'}, 403)
    nonce = (request.form.get('save_nonce') or '').strip()
    if not verify_consume_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY, nonce):
        return jsonify({'ok': False, 'error': 'Invalid or expired form token. Reload Category Master and try again.', 'save_nonce': issue_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY)}, 409)
    fobj = request.files.get('excel_file') or request.files.get('file')
    if not fobj or not getattr(fobj, 'filename', None):
        return jsonify({'ok': False, 'error': 'Choose an Excel file (.xlsx).', 'save_nonce': issue_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY)}, 400)
    fname = str(fobj.filename or '').lower()
    if not fname.endswith(('.xlsx', '.xlsm')):
        return jsonify({'ok': False, 'error': 'Please upload a .xlsx or .xlsm file.', 'save_nonce': issue_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY)}, 400)
    raw = fobj.read()
    if not isinstance(raw, bytes):
        raw = bytes(raw) if raw else b''
    if len(raw) > 5 * 1024 * 1024:
        return jsonify({'ok': False, 'error': 'File too large (max 5 MB).', 'save_nonce': issue_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY)}, 400)
    rows, perr = _category_master_parse_xlsx(raw)
    if perr:
        return jsonify({'ok': False, 'error': perr, 'save_nonce': issue_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY)}, 400)
    loc = _resolve_itemmaster_location_code()
    result = import_category_master_from_excel_rows(loc, rows, max_rows=_CM_IMPORT_MAX_ROWS)
    errs = result.get('errors') or []
    append_master_activity(username=_sess_user_for_log(), action='IMPORT', entity='item_category_master', summary=f"location={loc}, excel rows={len(rows)}, M+{int(result.get('created_m') or 0)} D+{int(result.get('created_d') or 0)} C+{int(result.get('created_c') or 0)}, BZL +{int(result.get('created_b') or 0)}/{int(result.get('created_z') or 0)}/{int(result.get('created_l') or 0)}, upd={int(result.get('updated') or 0)}, errors={len(errs)}"[:500], detail={'locationcode': loc, 'row_count': len(rows), 'created_m': int(result.get('created_m') or 0), 'created_d': int(result.get('created_d') or 0), 'created_c': int(result.get('created_c') or 0), 'created_b': int(result.get('created_b') or 0), 'created_z': int(result.get('created_z') or 0), 'created_l': int(result.get('created_l') or 0), 'updated': int(result.get('updated') or 0), 'error_count': len(errs), 'errors_preview': errs[:20]})
    return jsonify({'ok': True, 'partial': bool(errs), 'created_m': int(result.get('created_m') or 0), 'created_d': int(result.get('created_d') or 0), 'created_c': int(result.get('created_c') or 0), 'created_b': int(result.get('created_b') or 0), 'created_z': int(result.get('created_z') or 0), 'created_l': int(result.get('created_l') or 0), 'updated': int(result.get('updated') or 0), 'errors': errs[:50], 'save_nonce': issue_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY)})

@bp.route('/brand-master')
def brand_master_list():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    loc = _resolve_itemmaster_location_code()
    rows_brand = get_categories('B', location_code=loc) or get_categories('B')
    rows_shelf = get_categories('Z', location_code=loc) or get_categories('Z')
    rows_color = get_categories('L', location_code=loc) or get_categories('L')
    return render_template('itemmaster/brand_master_list.html', rows_brand=rows_brand, rows_shelf=rows_shelf, rows_color=rows_color)

@bp.route('/brand-master/save', methods=['POST'])
def brand_master_save():
    if not session.get('user'):
        return jsonify({'ok': False, 'error': 'Not logged in'}, 401)
    data = request.get_json(silent=True) or {}
    mode = (data.get('mode') or '').strip().lower()
    loc = _resolve_itemmaster_location_code()
    fl = (data.get('flag') or 'B').strip().upper()[:1]
    if fl not in ('B', 'Z', 'L'):
        return jsonify({'ok': False, 'error': 'Invalid type (B, Z, or L required)'}, 400)
    if mode == 'update':
        try:
            code = int(data.get('code') or 0)
        except (TypeError, ValueError):
            return jsonify({'ok': False, 'error': 'Valid code is required'}, 400)
        if code <= 0:
            return jsonify({'ok': False, 'error': 'Code is required'}, 400)
        name = (data.get('name') or '').strip()
        ok, err = update_category_master_name(code, fl, name, location_code=loc)
        if not ok:
            return jsonify({'ok': False, 'error': err or 'Update failed'}, 400)
        lbl = {'B': 'brand', 'Z': 'shelf', 'L': 'color'}.get(fl, fl)
        append_master_activity(username=_sess_user_for_log(), action='UPDATE', entity='item_brand_master', summary=f"location={loc}, type={lbl}, code={code}, name={(name or '')[:120]}", detail={'locationcode': loc, 'flag': fl, 'code': code, 'name': name})
        return jsonify({'ok': True})
    if mode == 'create':
        name = (data.get('name') or '').strip()
        ok, err, new_code = insert_category_lookup(name, loc, fl)
        if not ok:
            return jsonify({'ok': False, 'error': err or 'Insert failed'}, 400)
        lbl = {'B': 'brand', 'Z': 'shelf', 'L': 'color'}.get(fl, fl)
        append_master_activity(username=_sess_user_for_log(), action='CREATE', entity='item_brand_master', summary=f"location={loc}, type={lbl}, code={new_code}, name={(name or '')[:120]}", detail={'locationcode': loc, 'flag': fl, 'code': new_code, 'name': name})
        return jsonify({'ok': True, 'code': new_code})
    return jsonify({'ok': False, 'error': 'Invalid mode'}, 400)

@bp.route('/itemmaster/units')
def unit_of_measurement_list():
    """UNITOFMEASUREMENT maintenance (Inventory menu)."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    loc_u = session.get('location_code')
    lc_arg: Optional[int] = None
    if loc_u is not None and str(loc_u).strip() != '':
        try:
            lc_arg = int(float(str(loc_u).strip()))
        except (TypeError, ValueError):
            lc_arg = None
    if lc_arg is None or lc_arg <= 0:
        tenant_sid = (session.get('tenant_id') or '').strip()
        if is_multi_db_mode() and tenant_sid:
            auth_lc = get_tenant_locationcode_from_auth(tenant_sid)
            if auth_lc is not None and auth_lc > 0:
                lc_arg = auth_lc
    if lc_arg is None or lc_arg <= 0:
        lc_arg = 1
    rows = get_all_unit_of_measurement(lc_arg)
    create_once = _issue_uom_create_once()
    return render_template(
        'itemmaster/unit_of_measurement_list.html',
        rows=rows,
        uom_create_once=create_once,
        location_code=lc_arg,
        global_save_nonce=get_or_issue_global_save_nonce(),
    )

@bp.route('/itemmaster/units/issue-once', methods=['GET'])
def unit_of_measurement_issue_once():
    """Issue one-time token for edit/delete UoM (paired with save_nonce)."""
    if not session.get('user'):
        return jsonify({'ok': False, 'error': 'Not logged in'}, 401)
    intent = (request.args.get('intent') or '').strip().lower()
    code = (request.args.get('code') or '').strip().upper()
    if intent == 'edit' and code:
        once = _issue_uom_edit_once(code)
    elif intent == 'delete' and code:
        once = _issue_uom_delete_once(code)
    else:
        return jsonify({'ok': False, 'error': 'Use intent=edit|delete and a unit code.'}, 400)
    return jsonify({'ok': True, 'once': once, 'save_nonce': issue_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY)})

@bp.route('/itemmaster/units/save', methods=['POST'])
def unit_of_measurement_save():
    """Create / update / delete unit of measurement (JSON)."""
    if not session.get('user'):
        return jsonify({'ok': False, 'error': 'Not logged in'}, 401)
    data = request.get_json(silent=True) or {}
    sub = extract_submitted_save_nonce(request)
    if not reject_invalid_form_save_nonce(sub):
        return _uom_json_nonce_error(409, 'Duplicate or invalid submit. Reload the Units page if this persists.')
    mode = (data.get('mode') or '').strip().lower()
    if mode == 'create':
        code = (data.get('code') or '').strip()
        name = (data.get('name') or '').strip()
        once_c = (data.get('uom_create_once') or '').strip()
        if not _verify_consume_uom_create_once(once_c):
            return _uom_json_nonce_error(400, 'That save was skipped (duplicate submit or session lock). Reload the Units page.')
        ok, err = insert_unit_of_measurement(code, name)
        if not ok:
            return _uom_json_nonce_error(400, err or 'Insert failed')
        if not commit_form_save_nonce(sub):
            return _uom_json_nonce_error(409, 'Save token expired. Reload the Units page and try again.')
        append_master_activity(username=_sess_user_for_log(), action='CREATE', entity='unit_of_measurement', summary=f"code={code}, name={(name or '')[:120]}", detail={'code': code, 'name': name})
        return _uom_json_ok({'uom_create_once': _issue_uom_create_once()})
    if mode == 'update':
        code = (data.get('code') or '').strip()
        name = (data.get('name') or '').strip()
        once_e = (data.get('uom_edit_once') or '').strip()
        if not _verify_consume_uom_edit_once(code, once_e):
            return _uom_json_nonce_error(400, 'That save was skipped (duplicate submit or session lock). Choose Edit again.')
        ok, err = update_unit_of_measurement(code, name)
        if not ok:
            return _uom_json_nonce_error(400, err or 'Update failed')
        if not commit_form_save_nonce(sub):
            return _uom_json_nonce_error(409, 'Save token expired. Reload the Units page and try again.')
        append_master_activity(username=_sess_user_for_log(), action='UPDATE', entity='unit_of_measurement', summary=f"code={code}, name={(name or '')[:120]}", detail={'code': code, 'name': name})
        return _uom_json_ok()
    if mode == 'delete':
        code = (data.get('code') or '').strip()
        once_d = (data.get('uom_delete_once') or '').strip()
        if not _verify_consume_uom_delete_once(code, once_d):
            return _uom_json_nonce_error(400, 'That delete was skipped (duplicate submit or session lock). Try Delete again.')
        ok, err = delete_unit_of_measurement(code)
        if not ok:
            return _uom_json_nonce_error(400, err or 'Delete failed')
        if not commit_form_save_nonce(sub):
            return _uom_json_nonce_error(409, 'Save token expired. Reload the Units page and try again.')
        append_master_activity(username=_sess_user_for_log(), action='DELETE', entity='unit_of_measurement', summary=f'code={code}', detail={'code': code})
        return _uom_json_ok({'uom_create_once': _issue_uom_create_once()})
    return _uom_json_nonce_error(400, 'Invalid mode')

@bp.route('/itemmaster/property-origin')
def item_property_origin_list():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    rows_property = get_item_properties()
    rows_origin = get_item_origins()
    return render_template('itemmaster/item_property_origin_list.html', rows_property=rows_property, rows_origin=rows_origin)

@bp.route('/itemmaster/property-origin/save', methods=['POST'])
def item_property_origin_save():
    if not session.get('user'):
        return jsonify({'ok': False, 'error': 'Not logged in'}, 401)
    data = request.get_json(silent=True) or {}
    mode = (data.get('mode') or '').strip().lower()
    kind = (data.get('kind') or '').strip().lower()
    if kind not in ('property', 'origin'):
        return jsonify({'ok': False, 'error': 'Invalid kind (property or origin)'}, 400)
    if mode == 'update':
        try:
            code = data.get('code')
            if code is None or str(code).strip() == '':
                return jsonify({'ok': False, 'error': 'Code is required'}, 400)
        except (TypeError, ValueError):
            return jsonify({'ok': False, 'error': 'Valid code is required'}, 400)
        name = (data.get('name') or '').strip()
        if kind == 'property':
            ok, err = update_item_property_row(code, name)
            ent_key = 'item_property'
        else:
            ok, err = update_item_origin_row(code, name)
            ent_key = 'item_origin'
        if not ok:
            return jsonify({'ok': False, 'error': err or 'Update failed'}, 400)
        append_master_activity(username=_sess_user_for_log(), action='UPDATE', entity=ent_key, summary=f"code={code}, name={(name or '')[:120]}", detail={'kind': kind, 'code': code, 'name': name})
        return jsonify({'ok': True})
    if mode == 'create':
        name = (data.get('name') or '').strip()
        if kind == 'property':
            ok, err, new_code = insert_item_property_row(name)
            ent_key = 'item_property'
        else:
            ok, err, new_code = insert_item_origin_row(name)
            ent_key = 'item_origin'
        if not ok:
            return jsonify({'ok': False, 'error': err or 'Insert failed'}, 400)
        append_master_activity(username=_sess_user_for_log(), action='CREATE', entity=ent_key, summary=f"code={new_code}, name={(name or '')[:120]}", detail={'kind': kind, 'code': new_code, 'name': name})
        return jsonify({'ok': True, 'code': new_code})
    return jsonify({'ok': False, 'error': 'Invalid mode'}, 400)

@bp.route('/itemmaster/api/category-price-percentage', methods=['GET'])
def api_category_price_percentage():
    """JSON: PRICEPERCENTAGE from CATEGORY (FLAG='C') for Item Master selling-price markup from cost."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    code_raw = (request.args.get('code') or '').strip()
    try:
        code = int(float(code_raw))
    except (TypeError, ValueError):
        return Response(json.dumps({'success': True, 'pricepercentage': 0}, default=str), mimetype='application/json')
    if code <= 0:
        return Response(json.dumps({'success': True, 'pricepercentage': 0}, default=str), mimetype='application/json')
    try:
        loc = _resolve_itemmaster_location_code()
        pct = get_category_pricepercentage_by_code(code, loc)
        return Response(json.dumps({'success': True, 'pricepercentage': pct}, default=str), mimetype='application/json')
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}, 500)

@bp.route('/itemmaster/api/item-accounts', methods=['GET'])
def api_item_accounts():
    """JSON: full chart of accounts for Item Master account pickers (same data as list, for client fetch)."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    try:
        accounts = get_all_item_accounts()
        return Response(json.dumps({'success': True, 'accounts': accounts}, default=str), mimetype='application/json')
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}, 500)

@bp.route('/itemmaster/api/item-costing', methods=['GET'])
def api_item_costing():
    """JSON costing method summary and calculation notes for Item Master."""
    if not session.get('user'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}, 401)
    item_raw = (request.args.get('item_code') or '').strip()
    try:
        item_code = int(item_raw)
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': 'item_code is required'}, 400)
    loc = _resolve_itemmaster_location_code()
    try:
        payload = get_item_costing_method_details(loc, item_code)
        return Response(json.dumps(payload, default=str), mimetype='application/json')
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}, 500)


@bp.route('/itemmaster/api/item-ledger', methods=['GET'])
def api_item_ledger():
    """JSON ledger lines for Item Master popup (purchase / purchase return / sale / sale return / stock adjustment)."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    item_raw = (request.args.get('item_code') or '').strip()
    barcode_raw = (request.args.get('barcode') or '').strip()
    tab = (request.args.get('tab') or 'purchase').strip().lower()
    lim_raw = (request.args.get('limit') or '400').strip()
    try:
        limit_n = max(1, min(int(lim_raw), 2000))
    except (TypeError, ValueError):
        limit_n = 400
    loc = _resolve_itemmaster_location_code()
    item_code: Optional[int] = None
    item_name = ''
    resolved_barcode = ''
    if item_raw:
        try:
            item_code = int(item_raw)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'Invalid item_code'}, 400)
    if item_code is None and barcode_raw:
        item = _load_item_details_by_barcode_loose(barcode_raw, loc)
        if not item:
            return jsonify({'success': False, 'error': f'No item found for barcode {barcode_raw}'}, 404)
        try:
            item_code = int(float(str(item.get('itemcode') or item.get('ITEMCODE') or '')))
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': f'Item for barcode {barcode_raw} has no valid item code'}, 404)
        item_name = str(item.get('itemname') or item.get('ITEMNAME') or '').strip()
        resolved_barcode = barcode_raw.strip()
    if item_code is None:
        return jsonify({'success': False, 'error': 'item_code or barcode is required'}, 400)
    if not item_name:
        try:
            hdr = get_item_by_code(item_code, loc)
            if hdr:
                item_name = str(hdr.get('itemname') or hdr.get('ITEMNAME') or '').strip()
        except Exception:
            pass
    try:
        rows = get_item_ledger_tab(loc, item_code, tab, limit=limit_n)
        return Response(
            json.dumps({
                'success': True,
                'tab': tab,
                'item_code': item_code,
                'item_name': item_name,
                'barcode': resolved_barcode or barcode_raw,
                'rows': rows,
            }, default=str),
            mimetype='application/json',
        )
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}, 500)

def _itemmaster_coa_display_label(code: Any) -> str:
    if code is None or str(code).strip() == '':
        return ''
    acc = get_chart_of_account_by_code(str(code).strip())
    if acc:
        c = acc.get('code')
        n = (acc.get('name') or '').strip()
        return f'{c} - {n}'.strip(' -') if n else str(c)
    return str(code).strip()


def _build_itemmaster_view_labels(item_data: Dict[str, Any], alternate_uom: Optional[Dict[str, Any]], location_code_int: int) -> Dict[str, str]:
    loc = int(location_code_int)
    labels: Dict[str, str] = {
        'main_category': get_category_lookup_label('M', item_data.get('maincategory'), loc),
        'department': get_category_lookup_label('D', item_data.get('departmentcode'), loc),
        'category': get_category_lookup_label('C', item_data.get('categorycode'), loc),
        'brand': get_category_lookup_label('B', item_data.get('brandcode'), loc),
        'size': get_category_lookup_label('Z', item_data.get('sizecode'), loc),
        'color': get_category_lookup_label('L', item_data.get('colorcode'), loc),
        'base_uom': get_uom_lookup_display(item_data.get('baseuom'), loc),
        'ministry_unit': get_uom_lookup_display(item_data.get('ministryunit'), loc),
        'property': get_item_property_lookup_display(item_data.get('property')),
        'origin': get_item_origin_lookup_display(item_data.get('origin')),
        'sales_account': _itemmaster_coa_display_label(item_data.get('sales_account')),
        'purchase_account': _itemmaster_coa_display_label(item_data.get('purchase_account')),
        'inventory_account': _itemmaster_coa_display_label(item_data.get('inventory_account')),
        'cogs_account': _itemmaster_coa_display_label(item_data.get('cogs_account')),
        'alternate_uom': '',
        'supplier': '',
    }
    try:
        sc = item_data.get('supcode')
        if sc is not None and str(sc).strip() not in ('', '0'):
            sup = get_supplier_by_code(loc, int(float(str(sc))))
            if sup:
                nm = sup.get('suppliername') or sup.get('name') or ''
                labels['supplier'] = f'{sc} - {nm}'.strip(' -') if nm else str(sc)
            else:
                labels['supplier'] = str(sc)
    except (TypeError, ValueError):
        labels['supplier'] = str(item_data.get('supcode') or '')
    if alternate_uom and alternate_uom.get('alternateuomcode'):
        labels['alternate_uom'] = get_uom_lookup_display(alternate_uom.get('alternateuomcode'), loc)
    return labels


def _fast_itemmaster_code_labels(item_data: Dict[str, Any], alternate_uom: Optional[Dict[str, Any]]=None) -> Dict[str, str]:
    """Cheap edit-mode labels: display codes immediately; popup bootstrap resolves names when opened."""
    def _txt(key: str) -> str:
        value = item_data.get(key) if item_data else ''
        if value is None or str(value).strip() in ('', '0'):
            return ''
        return str(value).strip()
    labels = {
        'main_category': _txt('maincategory'),
        'department': _txt('departmentcode'),
        'category': _txt('categorycode'),
        'brand': _txt('brandcode'),
        'size': _txt('sizecode'),
        'color': _txt('colorcode'),
        'base_uom': _txt('baseuom'),
        'ministry_unit': _txt('ministryunit'),
        'property': _txt('property'),
        'origin': _txt('origin'),
        'sales_account': _txt('sales_account'),
        'purchase_account': _txt('purchase_account'),
        'inventory_account': _txt('inventory_account'),
        'cogs_account': _txt('cogs_account'),
        'supplier': _txt('supcode'),
        'alternate_uom': '',
    }
    if alternate_uom and alternate_uom.get('alternateuomcode'):
        labels['alternate_uom'] = str(alternate_uom.get('alternateuomcode') or '').strip()
    return labels


def _empty_itemmaster_bin_panel() -> Dict[str, Any]:
    return {
        'show': False,
        'loc_key': None,
        'bins': [],
        'bin_stock_rows': [],
        'hint': '',
        'inv_batch_tracking_enabled': False,
        'inv_warehouse_enabled': False,
        'inv_bin_tracking_enabled': False,
        'inv_default_bin_enabled': False,
    }


@bp.route('/itemmaster')
def itemmaster():
    """Item Master form page"""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    _im_t0 = time.perf_counter()
    _im_step_t = _im_t0
    location_code_value = session.get('location_code')
    location_code_int = None
    if location_code_value is not None:
        try:
            if str(location_code_value).isdigit():
                location_code_int = int(location_code_value)
        except Exception:
            location_code_int = None
    if location_code_int is None:
        try:
            location_info = get_location_info_by_dbkey(None)
            location_code_int = location_info.get('locationcode')
            if location_code_int is None:
                location_code_int = 1
        except Exception as e:
            print(f'[DEBUG itemmaster] Could not get location_code from LOCATIONMASTER: {e}')
            location_code_int = 1
    _itemmaster_timing_log('open_location_resolve', _im_step_t, loc=location_code_int)
    _im_step_t = time.perf_counter()
    try:
        ensure_itemmaster_inventory_extension_columns()
    except Exception:
        pass
    edit_mode = (request.args.get('edit') or '').strip().lower() in ('1', 'true', 'yes')
    from_grn_ai = (request.args.get('from_grn_ai') or '').strip().lower() in ('1', 'true', 'yes', 'on')
    has_prefill_qs = any(
        (request.args.get(k) or '').strip()
        for k in request.args
        if str(k).lower().startswith('prefill_')
    )
    prefill_itemname = _clean_none_text(request.args.get('prefill_itemname', ''))[:500]
    prefill_description = _clean_none_text(request.args.get('prefill_description', ''))[:500]
    prefill_item_code_invoice = _clean_none_text(request.args.get('prefill_item_code_invoice', ''))[:80]
    prefill_barcode = _clean_none_text(request.args.get('prefill_barcode', ''))[:80]
    prefill_uom_hint = _clean_none_text(request.args.get('prefill_uom', ''))[:30]

    def _pf_float_arg(key: str, default: float=0.0) -> float:
        try:
            return float((request.args.get(key) or '').strip() or default)
        except (TypeError, ValueError):
            return default
    prefill_sup_code = 0
    try:
        sc_arg = (request.args.get('prefill_sup_code') or '').strip()
        if sc_arg:
            prefill_sup_code = int(float(sc_arg))
    except (TypeError, ValueError):
        prefill_sup_code = 0
    prefill_unit_price = _pf_float_arg('prefill_unit_price', 0.0) if from_grn_ai else 0.0
    prefill_line_qty = _pf_float_arg('prefill_line_qty', 0.0) if from_grn_ai else 0.0
    prefill_line_total = _pf_float_arg('prefill_line_total', 0.0) if from_grn_ai else 0.0
    if from_grn_ai:
        prefill_cost = prefill_unit_price
        if prefill_unit_price <= 0 and prefill_line_qty > 0 and (prefill_line_total > 0):
            prefill_cost = prefill_line_total / prefill_line_qty
        prefill_retail = 0.0
    else:
        prefill_cost = 0.0
        prefill_retail = 0.0
    item_code = _clean_none_text(request.args.get('item_code', ''))
    manufacturer_id = _clean_none_text(request.args.get('manufacturer_id', ''))
    rawabicode = _clean_none_text(request.args.get('rawabicode', ''))
    item_data = None
    alternate_uom = None
    alternate_uoms = []
    store_inventory_rows = []
    detail_labels_from_view: Optional[Dict[str, str]] = None
    im_view_labels: Dict[str, str] = {}
    im_view_labels_ready = False
    _from_item_open_cache = False
    item_open_cache_key: Optional[Tuple[str, int, int]] = None
    if item_code:
        ic_int: Optional[int] = None
        try:
            ic_int = int(item_code)
        except (ValueError, TypeError):
            ic_int = None
        if ic_int is not None and (not edit_mode) and (not from_grn_ai) and (not has_prefill_qs):
            item_open_cache_key = ((session.get('tenant_id') or '').strip(), int(location_code_int), ic_int)
            cached_open = _itemmaster_open_cache_get(item_open_cache_key)
            if cached_open:
                item_data, detail_labels_from_view, im_view_labels = cached_open
                im_view_labels_ready = bool(detail_labels_from_view)
                _from_item_open_cache = True
        if not _from_item_open_cache:
            if ic_int is not None:
                vd = try_get_itemmaster_detail_view(ic_int, int(location_code_int))
                if vd:
                    item_data, detail_labels_from_view = vd
            if not item_data and ic_int is not None:
                try:
                    item_data = get_item_by_code(ic_int, location_code_int)
                except Exception:
                    pass
            if not item_data:
                try:
                    item_data = get_item_by_manufacturer_id(item_code, location_code_int)
                except Exception:
                    pass
    elif manufacturer_id:
        item_data = get_item_by_manufacturer_id(manufacturer_id, location_code_int)
        if item_data and item_data.get('itemcode'):
            item_code = str(item_data.get('itemcode'))
        if not item_data:
            item_data = get_item_by_alternate_barcode(manufacturer_id, location_code_int)
            if item_data and item_data.get('itemcode'):
                item_code = str(item_data.get('itemcode'))
    elif rawabicode:
        try:
            tbl = _detect_table(['ITEMMASTER', 'itemmaster', 'ITEM_MASTER'])
            rawabi_col = _detect_column(tbl, ['RAWABICODE', 'rawabicode', 'RAWABI_CODE']) if tbl else None
            itemcode_col = _detect_column(tbl, ['ITEMCODE', 'itemcode', 'ITEM_CODE']) if tbl else None
            loc_col = _detect_column(tbl, ['LOCATIONCODE', 'locationcode', 'LOCATION_CODE']) if tbl else None
            if tbl and rawabi_col and itemcode_col:
                q = f'SELECT {itemcode_col} AS itemcode FROM {tbl} WHERE TRIM(TO_CHAR({rawabi_col})) = TRIM(:rawabi) '
                params = {'rawabi': rawabicode}
                if loc_col and location_code_int is not None:
                    q += f'AND {loc_col} = :loc '
                    params['loc'] = int(location_code_int)
                q += f'ORDER BY {itemcode_col} DESC'
                rows = _safe_rows(q, params) or []
                if not rows and loc_col and (location_code_int is not None):
                    q2 = f'SELECT {itemcode_col} AS itemcode FROM {tbl} WHERE TRIM(TO_CHAR({rawabi_col})) = TRIM(:rawabi) ORDER BY {itemcode_col} DESC'
                    rows = _safe_rows(q2, {'rawabi': rawabicode}) or []
                if rows:
                    found_code = int(str(rows[0].get('itemcode') or '0').strip())
                    if found_code > 0:
                        item_data = get_item_by_code(found_code, location_code_int)
                        if item_data and item_data.get('itemcode'):
                            item_code = str(item_data.get('itemcode'))
        except Exception:
            item_data = None
    if item_data:
        # Detail-view / cache already include DEFAULT_WAREHOUSE_ID — avoid a second full item fetch.
        if (
            item_data.get('default_warehouse_id') in (None, '')
            and detail_labels_from_view is None
            and not _from_item_open_cache
        ):
            try:
                _ic_wh = int(item_data.get('itemcode') or item_code or 0)
            except (TypeError, ValueError):
                _ic_wh = 0
            if _ic_wh > 0:
                try:
                    _wh_row = get_item_by_code(_ic_wh, int(location_code_int))
                    if _wh_row and _wh_row.get('default_warehouse_id') not in (None, ''):
                        item_data['default_warehouse_id'] = _wh_row.get('default_warehouse_id')
                except Exception:
                    pass
        _itemmaster_attach_warehouse_display(item_data)
    _itemmaster_timing_log(
        'open_item_lookup',
        _im_step_t,
        loc=location_code_int,
        item_code=(item_code or '-'),
        manufacturer_id=bool(manufacturer_id),
        rawabicode=bool(rawabicode),
        found=1 if item_data else 0,
        cache_hit=1 if _from_item_open_cache else 0,
    )
    _im_step_t = time.perf_counter()
    if item_data:
        item_data = _clean_none_in_dict(item_data)
        for key in ('maincategory', 'departmentcode', 'categorycode', 'brandcode', 'property', 'origin', 'sizecode', 'colorcode'):
            value = item_data.get(key)
            if value is None:
                continue
            try:
                item_data[key] = int(str(value).strip())
            except (ValueError, TypeError):
                pass

    lookup_attempted = bool((item_code or '').strip() or (manufacturer_id or '').strip() or (rawabicode or '').strip())
    missed_lookup = lookup_attempted and item_data is None
    full_edit = bool(edit_mode or from_grn_ai or has_prefill_qs or (item_data is None) or missed_lookup)
    itemmaster_view_only = bool(item_data is not None and not full_edit)
    _itemmaster_timing_log('open_mode_decision', _im_step_t, full_edit=1 if full_edit else 0, view_only=1 if itemmaster_view_only else 0, missed_lookup=1 if missed_lookup else 0)
    _im_step_t = time.perf_counter()

    if item_data:
        skip_alt_uom = bool(itemmaster_view_only and (detail_labels_from_view is not None or _from_item_open_cache))
        if not skip_alt_uom:
            try:
                if manufacturer_id:
                    alternate_uom = get_item_alternate_uom_by_barcode(location_code_int, manufacturer_id)
                if not alternate_uom:
                    alternate_uom = get_item_alternate_uom(location_code_int, int(item_data.get('itemcode')))
            except (ValueError, TypeError):
                alternate_uom = None
        # Load all alternate UOM rows for existing items (edit, view, and prefill).
        if item_data.get('itemcode'):
            try:
                alternate_uoms = get_item_alternate_uoms(location_code_int, int(item_data.get('itemcode')))
            except (ValueError, TypeError):
                alternate_uoms = []
        if (not itemmaster_view_only) and (not edit_mode):
            try:
                store_inventory_rows = get_item_store_inventory(location_code_int, int(item_data.get('itemcode')))
            except (ValueError, TypeError):
                store_inventory_rows = []
    _itemmaster_timing_log(
        'open_item_related_data',
        _im_step_t,
        alt_uoms=len(alternate_uoms or []),
        store_rows=len(store_inventory_rows or []),
        has_alt=1 if alternate_uom else 0,
    )
    _im_step_t = time.perf_counter()

    brands: List[Dict[str, Any]] = []
    sizes: List[Dict[str, Any]] = []
    colors: List[Dict[str, Any]] = []
    main_categories: List[Dict[str, Any]] = []
    departments: List[Dict[str, Any]] = []
    categories: List[Dict[str, Any]] = []
    suppliers: List[Dict[str, Any]] = []
    units: List[Dict[str, Any]] = []
    item_properties: List[Dict[str, Any]] = []
    item_origins: List[Dict[str, Any]] = []
    chart_accounts: List[Dict[str, Any]] = []
    store_popup_rows: List[Dict[str, Any]] = []
    grn_new_item_default_accounts = None
    prefill_base_uom_code: Optional[Any] = None
    prefill_base_uom_display = ''
    prefill_sup_display = ''

    if full_edit:
        if item_data:
            if detail_labels_from_view is not None:
                im_view_labels = dict(detail_labels_from_view)
                im_view_labels_ready = True
            else:
                im_view_labels = _fast_itemmaster_code_labels(item_data, alternate_uom)
        # First paint stays light. Lookup popup rows are loaded by one bootstrap API on demand.
        if from_grn_ai:
            suppliers = _itemmaster_lookup_rows('supplier', int(location_code_int))
            units = _itemmaster_lookup_rows('baseUom', int(location_code_int))
            try:
                chart_accounts = get_all_chart_of_accounts()
            except Exception:
                chart_accounts = []
        if from_grn_ai and prefill_uom_hint:
            prefill_base_uom_code, prefill_base_uom_display = _match_unit_for_grn_prefill(units, prefill_uom_hint)
        prefill_sup_display = _supplier_display_for_prefill(suppliers, prefill_sup_code) if from_grn_ai and prefill_sup_code else ''

        def _normalize_code_rows(rows):
            for row in rows:
                value = row.get('code')
                if value is None:
                    continue
                try:
                    row['code'] = int(str(value).strip())
                except (ValueError, TypeError):
                    pass
        for rows in (brands, sizes, colors, main_categories, departments, categories, item_properties, item_origins):
            _normalize_code_rows(rows)
    elif item_data and not _from_item_open_cache:
        if detail_labels_from_view is not None:
            im_view_labels = dict(detail_labels_from_view)
            im_view_labels_ready = True
        elif itemmaster_view_only:
            im_view_labels = _fast_itemmaster_code_labels(item_data, alternate_uom)
        else:
            im_view_labels = _build_itemmaster_view_labels(item_data, alternate_uom, int(location_code_int))
            im_view_labels_ready = True
    _itemmaster_timing_log(
        'open_labels_and_prefill_lookups',
        _im_step_t,
        labels=len(im_view_labels or {}),
        detail_labels=1 if detail_labels_from_view is not None else 0,
        suppliers=len(suppliers or []),
        units=len(units or []),
        accounts=len(chart_accounts or []),
        full_edit=1 if full_edit else 0,
    )
    _im_step_t = time.perf_counter()

    if (
        item_open_cache_key is not None
        and itemmaster_view_only
        and item_data
        and not _from_item_open_cache
    ):
        try:
            ic_row = int(item_data.get('itemcode'))
        except (TypeError, ValueError):
            ic_row = 0
        if ic_row > 0 and ic_row == item_open_cache_key[2]:
            _itemmaster_open_cache_set(item_open_cache_key, item_data, detail_labels_from_view, im_view_labels)
    if from_grn_ai and (not item_data) and full_edit:
        grn_new_item_default_accounts = _grn_new_item_default_account_fields(chart_accounts)
    bin_panel_item_code: Optional[int] = None
    ensure_bin_storage_ids: Optional[List[Any]] = None
    if item_data:
        try:
            bin_panel_item_code = int(item_data.get('itemcode'))
        except (TypeError, ValueError):
            bin_panel_item_code = None
        _eb: List[Any] = []
        for _eb_key in ('default_bin_storage_id', 'staging_bin_storage_id'):
            _eb_val = item_data.get(_eb_key)
            if _eb_val is None or str(_eb_val).strip() == '':
                continue
            _eb.append(_eb_val)
        if _eb:
            ensure_bin_storage_ids = _eb
    bin_wh_ref: Optional[Any] = None
    if item_data and item_data.get('default_warehouse_id') not in (None, ''):
        bin_wh_ref = item_data.get('default_warehouse_id')
    if itemmaster_view_only:
        itemmaster_bin_panel = _empty_itemmaster_bin_panel()
    else:
        itemmaster_bin_panel = get_itemmaster_bin_tracking_panel_data(
            location_code_int,
            filter_item_code=bin_panel_item_code,
            lightweight=bool(edit_mode),
            ensure_bin_storage_ids=ensure_bin_storage_ids,
            load_bins=(not bool(edit_mode)) or bool(bin_wh_ref),
            warehouse_ref=bin_wh_ref,
        )
    _itemmaster_timing_log(
        'open_bin_panel',
        _im_step_t,
        loc=location_code_int,
        item_code=bin_panel_item_code or '-',
        skipped=1 if itemmaster_view_only else 0,
        lightweight=1 if bool(edit_mode) else 0,
        load_bins=0 if bool(edit_mode or itemmaster_view_only) else 1,
        bin_rows=len((itemmaster_bin_panel or {}).get('bin_stock_rows') or []),
    )
    t_pre_render = time.perf_counter()
    # View-only: pre-fill variant editor from first alternate row. Edit mode: leave editor empty; grid loads via API / row Edit click.
    alternate_uom_editor = alternate_uom if itemmaster_view_only else None
    resp = render_template('itemmaster/itemmaster.html', categories=categories, brands=brands, sizes=sizes, colors=colors, main_categories=main_categories, departments=departments, suppliers=suppliers, units=units, item_properties=item_properties, item_origins=item_origins, item_data=item_data, prefill_itemname=prefill_itemname, prefill_from_grn_ai=from_grn_ai, prefill_description=prefill_description, prefill_item_code_invoice=prefill_item_code_invoice, prefill_barcode=prefill_barcode, prefill_cost=prefill_cost, prefill_retail=prefill_retail, prefill_base_uom_code=prefill_base_uom_code, prefill_base_uom_display=prefill_base_uom_display, prefill_sup_code=prefill_sup_code, prefill_sup_display=prefill_sup_display, alternate_uom=alternate_uom_editor, alternate_uoms=alternate_uoms, store_inventory_rows=store_inventory_rows, location_code=location_code_int, chart_accounts=chart_accounts, store_popup_rows=store_popup_rows, grn_new_item_default_accounts=grn_new_item_default_accounts, itemmaster_bin_panel=itemmaster_bin_panel, itemmaster_ai_arabic_url=url_for('itemmaster.itemmaster_ai_arabic_name'), itemmaster_ai_general_fill_url=url_for('itemmaster.itemmaster_ai_general_fill'), itemmaster_ai_barcode_web_url=url_for('itemmaster.itemmaster_ai_barcode_web'), itemmaster_bootstrap_url=url_for('itemmaster.api_itemmaster_bootstrap'), itemmaster_view_only=itemmaster_view_only, im_view_labels=im_view_labels, im_view_labels_ready=im_view_labels_ready)
    if _itemmaster_timing_log_enabled():
        t_end = time.perf_counter()
        server_ms = (t_pre_render - _im_t0) * 1000.0
        render_ms = (t_end - t_pre_render) * 1000.0
        total_ms = (t_end - _im_t0) * 1000.0
        ic_log = (item_code or '-').strip() or '-'
        print(
            f'[TIMING itemmaster] item_code={ic_log} view_only={1 if itemmaster_view_only else 0} '
            f'cache_hit={1 if _from_item_open_cache else 0} full_edit={1 if full_edit else 0} '
            f'server_ms={server_ms:.1f} render_ms={render_ms:.1f} total_ms={total_ms:.1f}'
        )
    return resp

@bp.route('/itemmaster/save', methods=['POST'])
def itemmaster_save():
    """Save item master data"""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    if not verify_consume_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY, extract_submitted_save_nonce(request)):
        return replay_blocked_response_global()
    location_code_int = _itemmaster_session_location_code()
    is_new = request.form.get('is_new', 'true').lower() == 'true'
    item_code = request.form.get('item_code', '').strip()
    if is_new:
        if not item_code:
            item_code = str(get_next_item_code(location_code_int))
        else:
            try:
                existing_item = get_item_by_code(int(item_code), location_code_int)
                if existing_item:
                    item_code = str(get_next_item_code(location_code_int))
            except Exception:
                item_code = str(get_next_item_code(location_code_int))
    elif not item_code:
        return json_response_rotate_global({'success': False, 'error': 'Item code is required'}, 400)
    try:
        ic_for_barcode = int(float(str(item_code).strip().split(' - ', 1)[0]))
    except (TypeError, ValueError):
        ic_for_barcode = 0
    manufacturer_id = _clean_none_text(request.form.get('manufacturer_id'))
    if not manufacturer_id and ic_for_barcode > 0:
        manufacturer_id = format_location_prefix_item_barcode(location_code_int, ic_for_barcode) or str(item_code)
    elif not manufacturer_id:
        manufacturer_id = str(item_code)
    exclude_barcode_item: Optional[int] = None if is_new else ic_for_barcode
    if manufacturer_id and barcode_taken_in_location(
        manufacturer_id, location_code_int, exclude_item_code=exclude_barcode_item,
    ):
        return json_response_rotate_global({
            'success': False,
            'error': 'Barcode already exists in Itemmaster or alternate UOM. Please use another barcode.',
        }, 400)
    item_data = {'location_code': location_code_int, 'item_code': item_code, 'manufacturer_id': manufacturer_id, 'item_name': _clean_none_text(request.form.get('item_name')).upper(), 'main_category': request.form.get('main_category'), 'department_code': request.form.get('department_code'), 'category_code': request.form.get('category_code'), 'brand_code': request.form.get('brand_code'), 'size_code': request.form.get('size_code'), 'color_code': request.form.get('color_code'), 'base_uom': request.form.get('base_uom'), 'sup_code': request.form.get('sup_code'), 'cost_price': request.form.get('cost_price'), 'retail_price': request.form.get('retail_price'), 'wholesale_price': request.form.get('wholesale_price'), 'third_price': request.form.get('third_price'), 'branch_price': request.form.get('branch_price'), 'maximum_level': request.form.get('maximum_level'), 'reorder_level': request.form.get('reorder_level'), 'company_code': request.form.get('company_code'), 'item_name_ara': request.form.get('item_name_ara'), 'description': request.form.get('description'), 'vat_percent': request.form.get('vat_percent'), 'discount_flag': 'Y' if request.form.get('discount_flag') else 'N', 'item_flag': 'Y' if request.form.get('item_active') else 'N', 'property_code': request.form.get('property_code'), 'origin_code': request.form.get('origin_code'), 'quantity_limit': request.form.get('quantity_limit'), 'packing': request.form.get('packing'), 'ministry_factor': request.form.get('ministry_factor'), 'ministry_unit': request.form.get('ministry_unit'), 'rebate': request.form.get('rebate'), 'sales_account': request.form.get('sales_account'), 'purchase_account': request.form.get('purchase_account'), 'inventory_account': request.form.get('inventory_account'), 'cogs_account': request.form.get('cogs_account'), 'daily_limit': request.form.get('daily_limit'), 'slow_moving': 'Y' if request.form.get('slow_moving') else 'N', 'own_product': 'Y' if request.form.get('own_product') else 'N', 'special_item': 'Y' if request.form.get('special_item') else 'N', 'below_cost': 'Y' if request.form.get('below_cost') else 'N', 'market_item': 'Y' if request.form.get('market_item') else 'N', 'row_material': 'Y' if request.form.get('row_material') else 'N', 'discount_limit': request.form.get('discount_limit'), 'margin_limit_percent': request.form.get('margin_limit_percent'), 'below_cost_reason': request.form.get('below_cost_reason'), 'default_warehouse_id': request.form.get('default_warehouse_id'), 'is_weight_item': 'Y' if request.form.get('is_weight_item') else 'N'}
    item_data = _clean_none_in_dict(item_data)
    old_row_for_log: Optional[Dict[str, Any]] = None
    alts_before_log: List[Dict[str, Any]] = []
    try:
        _icode_pre = int(str(item_code).strip())
    except (TypeError, ValueError):
        _icode_pre = 0
    if not is_new and _icode_pre > 0:
        try:
            old_row_for_log = get_item_by_code(_icode_pre, location_code_int)
            alts_before_log = list(get_item_alternate_uoms(location_code_int, _icode_pre) or [])
        except Exception:
            old_row_for_log = None
            alts_before_log = []
    if str(session.get('user') or '').strip().lower() != 'admin':
        if old_row_for_log:
            for form_key, row_keys in (
                ('sales_account', ('salesaccount', 'sales_account')),
                ('purchase_account', ('purchaseaccount', 'purchase_account')),
                ('inventory_account', ('inventoryaccount', 'inventory_account')),
                ('cogs_account', ('cogsaccount', 'cogs_account')),
            ):
                val = None
                for rk in row_keys:
                    if old_row_for_log.get(rk) not in (None, ''):
                        val = old_row_for_log.get(rk)
                        break
                if val not in (None, ''):
                    item_data[form_key] = val
        else:
            try:
                acct_defs = _grn_new_item_default_account_fields(get_all_chart_of_accounts())
            except Exception:
                acct_defs = {}
            for form_key, def_key in (
                ('sales_account', 'sales_code'),
                ('purchase_account', 'purchase_code'),
                ('inventory_account', 'inventory_code'),
                ('cogs_account', 'cogs_code'),
            ):
                if acct_defs.get(def_key):
                    item_data[form_key] = acct_defs.get(def_key)
    try:
        try:
            alt_item_code = int(float(str(item_code).strip().split(' - ', 1)[0]))
        except (TypeError, ValueError):
            alt_item_code = 0
        if alt_item_code <= 0:
            return json_response_rotate_global({'success': False, 'error': 'Item code is invalid for save.'}, 400)

        def _num(val):
            try:
                return float(val) if val not in (None, '') else 0
            except (ValueError, TypeError):
                return 0
        variant_json_raw = (request.form.get('alternate_uoms_json') or '').strip()
        variant_rows = []
        if variant_json_raw:
            try:
                parsed = json.loads(variant_json_raw)
                if isinstance(parsed, list):
                    variant_rows = parsed
            except Exception:
                variant_rows = []
        alternate_payloads: List[Dict[str, Any]] = []
        print(f'[DEBUG itemmaster_save] variant_rows_received={len(variant_rows)}')
        if variant_rows:
            for idx, vr in enumerate(variant_rows, start=1):
                if not isinstance(vr, dict):
                    print(f'[DEBUG itemmaster_save] variant_row_{idx}: skipped (not object)')
                    continue
                alternate_uom_code = str(vr.get('alternate_uom_code') or '').strip()
                conversion_factor_raw = str(vr.get('conversion_factor') or '').strip()
                if not alternate_uom_code or not conversion_factor_raw:
                    print(f"[DEBUG itemmaster_save] variant_row_{idx}: skipped (uom='{alternate_uom_code}', factor='{conversion_factor_raw}')")
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
                if not alternate_barcode:
                    alternate_barcode = get_next_alternate_barcode(location_code_int, alt_item_code)
                print(f"[DEBUG itemmaster_save] variant_row_{idx}: queued (slno='{str(vr.get('slno') or '').strip()}', uom='{alternate_uom_code}', barcode='{alternate_barcode}', factor={conversion_factor})")
                alt_row = {'location_code': location_code_int, 'item_code': alt_item_code, 'slno': str(vr.get('slno') or '').strip(), 'alternate_uom_code': alternate_uom_code, 'manufacturer_id': alternate_barcode, 'base_uom': item_data.get('base_uom') or '', 'conversion_factor': conversion_factor, 'cost_price': alternate_cost, 'wholesale_price': _num(vr.get('wholesale_price')), 'retail_price': _num(vr.get('retail_price')), 'third_price': _num(vr.get('third_price')), 'branch_price': _num(vr.get('branch_price')), 'description': str(vr.get('description') or item_data.get('description') or '')[:500]}
                if vr.get('mirror_itemmaster') or vr.get('is_base'):
                    alt_row['mirror_itemmaster'] = True
                    alt_row['is_base'] = True
                    alt_row['item_manufacturer_id'] = str(item_data.get('manufacturer_id') or manufacturer_id or alt_item_code).strip()
                    alt_row['description'] = str(item_data.get('description') or item_data.get('item_name') or '')[:500]
                else:
                    alt_row['is_base'] = False
                alternate_payloads.append(alt_row)
            if variant_rows and len(alternate_payloads) == 0:
                print('[DEBUG itemmaster_save] variant_rows processed=0 (all skipped)')
                return json_response_rotate_global({'success': False, 'error': 'Variant list has invalid rows. Please check Alternate UOM and Conversion Factor.'}, 400)
        else:
            alternate_uom_code = (request.form.get('alternate_uom_code') or '').strip()
            conversion_factor_raw = (request.form.get('alternate_conversion_factor') or '').strip()
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
                alternate_barcode = (request.form.get('alternate_barcode') or '').strip()
                if not alternate_barcode:
                    alternate_barcode = get_next_alternate_barcode(location_code_int, alt_item_code)
                print(f"[DEBUG itemmaster_save] fallback_variant: queued (slno='{(request.form.get('alternate_slno') or '').strip()}', uom='{alternate_uom_code}', barcode='{alternate_barcode}', factor={conversion_factor})")
                alternate_payloads.append({'location_code': location_code_int, 'item_code': alt_item_code, 'slno': (request.form.get('alternate_slno') or '').strip(), 'alternate_uom_code': alternate_uom_code, 'manufacturer_id': alternate_barcode, 'base_uom': item_data.get('base_uom') or '', 'conversion_factor': conversion_factor, 'cost_price': alternate_cost, 'wholesale_price': _num(request.form.get('alternate_wholesale_price')), 'retail_price': _num(request.form.get('alternate_retail_price')), 'third_price': _num(request.form.get('alternate_third_price')), 'branch_price': _num(request.form.get('alternate_branch_price'))})
        ensure_itemmaster_inventory_extension_columns()
        saved_item_code, txn_err = save_itemmaster_with_alternate_uoms(item_data, is_new, alternate_payloads)
        if txn_err:
            return json_response_rotate_global({'success': False, 'error': txn_err}, 400)
        if saved_item_code is None or saved_item_code is False:
            return json_response_rotate_global({'success': False, 'error': 'Failed to save item master record.'}, 500)
        print(f'[DEBUG itemmaster_save] transactional save OK item_code={saved_item_code}, is_new={is_new}, alternate_rows={len(alternate_payloads)}')
        try:
            _sic = int(float(str(saved_item_code).strip()))
        except (TypeError, ValueError):
            _sic = 0
        if _sic > 0:
            _weight_item = (request.form.get('is_weight_item') or '').strip().upper() == 'Y'
            set_item_weight_item(_sic, location_code_int, _weight_item)
            if is_location_batch_tracking_enabled(location_code_int):
                _tracked = (request.form.get('batch_tracked') or '').strip().upper() == 'Y'
                set_item_batch_tracked(_sic, location_code_int, _tracked)
            if is_location_warehouse_enabled(location_code_int) and is_location_bin_tracking_enabled(location_code_int):
                _selected_wh = (request.form.get('default_warehouse_id') or '').strip()
                _raw_sid = (request.form.get('default_bin_storage_id') or '').strip()
                if not _raw_sid:
                    set_item_default_bin_storage_id(_sic, location_code_int, None)
                else:
                    try:
                        _sid_int = int(_raw_sid)
                    except (TypeError, ValueError):
                        pass
                    else:
                        if not _selected_wh:
                            return json_response_rotate_global({'success': False, 'error': 'Select a default warehouse before choosing default bin.'}, 400)
                        try:
                            _store_bins = get_warehouse_storage_rows(_selected_wh, 'BIN') or []
                            _valid_sid = any(str((b or {}).get('storage_id') or '').strip() == str(_sid_int) for b in _store_bins)
                        except Exception:
                            _valid_sid = False
                        if not _valid_sid:
                            return json_response_rotate_global({'success': False, 'error': 'Default bin must belong to the selected warehouse.'}, 400)
                        set_item_default_bin_storage_id(_sic, location_code_int, _sid_int)
                if 'staging_bin_storage_id' in request.form:
                    _raw_stage = (request.form.get('staging_bin_storage_id') or '').strip()
                    if not _raw_stage:
                        set_item_staging_bin_storage_id(_sic, location_code_int, None)
                    else:
                        try:
                            set_item_staging_bin_storage_id(_sic, location_code_int, int(_raw_stage))
                        except (TypeError, ValueError):
                            pass
        if _sic > 0:
            existing_image = ''
            if old_row_for_log:
                existing_image = str(
                    old_row_for_log.get('image_path')
                    or old_row_for_log.get('IMAGE_PATH')
                    or ''
                ).strip()
            img_err = apply_item_image_from_request(
                item_code=_sic,
                location_code=location_code_int,
                existing_path=existing_image,
            )
            if img_err:
                return json_response_rotate_global({'success': False, 'error': img_err}, 400)
        print(f'[DEBUG itemmaster_save] variant_rows_processed={len(alternate_payloads)}')
        _log_branch_itemmaster_save(is_new=is_new, location_code_int=location_code_int, saved_item_code=saved_item_code, old_row_for_log=old_row_for_log, alts_before_log=alts_before_log)
        try:
            _inv_tenant = (session.get('tenant_id') or '').strip()
            if _sic > 0:
                _itemmaster_open_cache_invalidate_key((_inv_tenant, int(location_code_int), _sic))
        except Exception:
            pass
        return json_response_rotate_global({'success': True, 'message': 'Item saved successfully!', 'item_code': saved_item_code})
    except ValueError as e:
        return json_response_rotate_global({'success': False, 'error': str(e)}, 400)
    except Exception as e:
        print(f'[ERROR itemmaster_save] {e}')
        import traceback
        traceback.print_exc()
        err = str(e)
        if 'ORA-00001' in err and 'UK_ITEMALTERNATEUOMMAP_MANUF' in err.upper():
            return json_response_rotate_global({
                'success': False,
                'error': (
                    'This barcode is already used on another item in this branch. '
                    'Use a different barcode, or contact your administrator if the item data needs correction.'
                ),
            }, 400)
        return json_response_rotate_global({'success': False, 'error': 'Database error: ' + err}, 500)

@bp.route('/itemmaster/activity-log')
def itemmaster_activity_log():
    """Audit report for branch Item Master saves (entity itemmaster_branch)."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    export_raw = (request.args.get('export') or '').strip().lower()
    try:
        limit = int(request.args.get('limit') or 800)
    except (TypeError, ValueError):
        limit = 800
    limit = max(50, min(limit, 2000))
    rows = fetch_master_activity_log(entity_exact=_ITEMMASTER_BRANCH_ENTITY, limit=limit)
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
        fn = f"itemmaster_branch_activity_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        return Response(buf.getvalue(), mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename="{fn}"'})
    return render_template('itemmaster/itemmaster_branch_activity_log.html', rows=rows, limit=limit)

def _itemmaster_session_location_code() -> int:
    raw_lc = session.get('location_code')
    location_code_int: Optional[int] = None
    if raw_lc is not None and str(raw_lc).strip() != '':
        try:
            location_code_int = int(raw_lc) if isinstance(raw_lc, (int, float)) else int(str(raw_lc).strip())
        except (TypeError, ValueError):
            try:
                location_code_int = int(float(str(raw_lc).strip()))
            except (TypeError, ValueError):
                location_code_int = None
    if location_code_int is None or location_code_int <= 0:
        tenant_sid = (session.get('tenant_id') or '').strip()
        if is_multi_db_mode() and tenant_sid:
            auth_lc = get_tenant_locationcode_from_auth(tenant_sid)
            if auth_lc is not None and auth_lc > 0:
                location_code_int = auth_lc
    if location_code_int is None or location_code_int <= 0:
        location_code_int = 1
    return int(location_code_int)


@bp.route('/itemmaster/next-code', methods=['GET'])
def itemmaster_next_code():
    """Get next available item code"""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    location_code_int = _itemmaster_session_location_code()
    try:
        next_code = get_next_item_code(location_code_int)
        return jsonify({'success': True, 'item_code': next_code})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}, 500)


@bp.route('/itemmaster/api/suggest-barcode', methods=['GET'])
def itemmaster_api_suggest_barcode():
    """Suggest 13-digit barcode: prefix 12 + zero-padded middle + item code (duplicate-safe)."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    item_code_raw = (request.args.get('item_code') or '').strip()
    if not item_code_raw.isdigit():
        return jsonify({'success': False, 'error': 'Valid item_code is required.'}, 400)
    try:
        item_code_int = int(item_code_raw)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Valid item_code is required.'}, 400)
    location_code_int = _itemmaster_session_location_code()
    loc_override = (request.args.get('location_code') or '').strip()
    if loc_override.isdigit():
        location_code_int = int(loc_override)
    exclude_ic: Optional[int] = None
    exclude_raw = (request.args.get('exclude_item_code') or '').strip()
    if exclude_raw.isdigit():
        exclude_ic = int(exclude_raw)
    barcode, err = suggest_location_prefix_item_barcode(
        location_code_int, item_code_int, exclude_item_code=exclude_ic,
    )
    if err:
        return jsonify({'success': False, 'error': err}, 400)
    return jsonify({
        'success': True,
        'barcode': barcode,
        'location_code': location_code_int,
        'item_code': item_code_int,
        'format': '12 + zero-padded middle + item code (13 digits)',
    })

@bp.route('/itemmaster/verify', methods=['GET'])
def itemmaster_verify():
    """Verify item code exists in current db/location"""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    item_code = request.args.get('item_code', '').strip()
    if not item_code.isdigit():
        return jsonify({'success': False, 'error': 'Valid item_code is required'}, 400)
    location_code = request.args.get('location_code', '').strip() or session.get('location_code') or 'HO'
    try:
        location_code_int = int(location_code) if str(location_code).isdigit() else 1
    except Exception:
        location_code_int = 1
    try:
        item = get_item_by_code(int(item_code), location_code_int)
        return jsonify({'success': True, 'exists': bool(item), 'item_code': item_code, 'location_code': location_code_int, 'item_name': item.get('itemname') if item else None})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}, 500)

@bp.route('/itemmaster/ai-arabic-name', methods=['POST'])
def itemmaster_ai_arabic_name():
    """Suggest Arabic item name from Item Name (AI if configured, otherwise fallback)."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    payload = request.get_json(silent=True) or {}
    item_name = str(payload.get('item_name') or '').strip()
    if not item_name:
        return jsonify({'success': False, 'error': 'Item name is required'}, 400)
    ai_text = _ai_arabic_suggest(item_name)
    if ai_text:
        return jsonify({'success': True, 'arabic_name': ai_text, 'source': 'ai'})
    fallback = _basic_arabic_suggest(item_name)
    return jsonify({'success': True, 'arabic_name': fallback, 'source': 'fallback'})

@bp.route('/itemmaster/ai-barcode-web', methods=['POST'])
def itemmaster_ai_barcode_web():
    """Fetch product title/brand from public barcode databases when AI Mode is used."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    try:
        payload = request.get_json(silent=True) or {}
        barcode_raw = str(payload.get('barcode') or payload.get('manufacturer_id') or '').strip()
        if not barcode_raw:
            return jsonify({'success': False, 'error': 'Barcode is required'}, 400)
        location_code = session.get('location_code') or '1'
        try:
            location_code_int = int(location_code) if str(location_code).isdigit() else 1
        except Exception:
            location_code_int = 1
        local_item = _load_item_details_by_barcode_loose(barcode_raw, location_code_int)
        if local_item:
            g = _ai_general_payload_from_item_details(local_item, location_code_int)
            ic = local_item.get('itemcode')
            iname = _clean_none_text(local_item.get('itemname'))
            ara = _clean_none_text(local_item.get('itemnameara'))
            desc = _clean_none_text(local_item.get('description')) or iname
            try:
                ic_out: Any = int(float(str(ic)))
            except (TypeError, ValueError):
                ic_out = ic
            return jsonify({
                'success': True,
                'found': True,
                'already_in_master': True,
                'already_exists': True,
                'source': 'master',
                'item_code': ic_out,
                'item_name': iname,
                'general': g,
                'product': {
                    'item_name': iname,
                    'description': desc,
                    'brand': g.get('brand_display') or '',
                    'barcode': str(barcode_raw).strip(),
                    'source': 'master',
                    'item_name_ara': ara,
                },
                'message': (
                    f'Loaded from Item Master (item {ic_out}). '
                    'This barcode already exists — use that item on the GRN line instead of creating a duplicate.'
                ),
            })
        found, err, product = _fetch_web_product_by_barcode(barcode_raw)
        if not found or not product:
            return jsonify({'success': True, 'found': False, 'message': err or 'Product not found on the web.'})
        return jsonify({'success': True, 'found': True, 'product': product, 'source': product.get('source') or 'web'})
    except Exception as exc:
        print(f'[ERROR itemmaster_ai_barcode_web] {exc}')
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': f'Web lookup failed: {exc}',
            'hint': 'If this persists, the app server may be unable to reach openfoodfacts.org or api.upcitemdb.com (firewall/proxy).',
        })


@bp.route('/itemmaster/ai-general-fill', methods=['POST'])
def itemmaster_ai_general_fill():
    """Fill general defaults from closest previous item by name."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    payload = request.get_json(silent=True) or {}
    item_name = str(payload.get('item_name') or '').strip()
    if not item_name:
        return jsonify({'success': False, 'error': 'Item name is required'}, 400)
    location_code = session.get('location_code') or '1'
    try:
        location_code_int = int(location_code) if str(location_code).isdigit() else 1
    except Exception:
        location_code_int = 1
    try:
        best = _find_best_item_template_by_name(location_code_int, item_name)
        if not best:
            return jsonify({'success': True, 'found': False, 'message': 'No similar item found'})
        if float(best.get('score') or 0) < _AI_ITEM_MATCH_MIN_SCORE:
            return jsonify({'success': True, 'found': False, 'message': f'Best match is below required threshold ({int(_AI_ITEM_MATCH_MIN_SCORE * 100)}%).', 'match_score': best.get('score'), 'word_match_count': best.get('word_match_count'), 'input_word_count': best.get('input_word_count'), 'matched_words': best.get('matched_words') or []})
        d = best.get('details') or {}
        return jsonify({'success': True, 'found': True, 'match_score': best.get('score'), 'word_match_count': best.get('word_match_count'), 'input_word_count': best.get('input_word_count'), 'matched_words': best.get('matched_words') or [], 'matched_item_code': d.get('itemcode'), 'matched_item_name': d.get('itemname'), 'general': _ai_general_payload_from_item_details(d, location_code_int), 'additional': {'property': _clean_none_text(d.get('property')), 'origin': _clean_none_text(d.get('origin')), 'rebate': _clean_none_text(d.get('rebate')), 'packing': _clean_none_text(d.get('packing')), 'size_code': _clean_none_text(d.get('sizecode')), 'color_code': _clean_none_text(d.get('colorcode')), 'ministry_factor': _clean_none_text(d.get('ministryfactor')), 'ministry_unit': _clean_none_text(d.get('ministryunit'))}})
    except Exception as exc:
        return jsonify({'success': False, 'error': f'AI general fill failed: {exc}'}, 500)
