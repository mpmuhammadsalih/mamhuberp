"""POS Billing blueprint - standard billing with barcode, itemmaster, itemalternateuommap, billhdr, billdtl."""
from pathlib import Path
import base64
import codecs
import csv
import io
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import textwrap
import time
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional, Tuple
RECEIPT_WIDTH = 48
DEFAULT_RECEIPT_DESIGN = {'page_width': 48, 'header': {'business_name': True, 'logo': True}, 'bill': {'bill_no': True, 'bill_date': True, 'bill_time': True, 'print_date': True, 'print_time': True, 'customer': True}, 'items': {'slno': True, 'item': True, 'item_ara': True, 'unit_price': True, 'qty': True, 'line_total': True}, 'summary': {'cashier': True, 'waiter': True, 'paid': True, 'currency': True, 'total_tax_ex': True, 'disc_pct': True, 'taxes': True, 'grand_total': True}, 'footer': {'message': True, 'powered_by': True, 'barcode': True}, 'labels': {'powered_by': 'POWERED BY KAPP', 'grand_total_prefix': 'T'}, 'output_encoding': 'utf-8', 'nls_lang': '', 'escpos_left_align': True, 'escpos_header_double_height': True, 'paper_width_mm': 80, 'receipt_printer_name': '', 'receipt_printer_ip': ''}
from nexa_http import Blueprint, Response, current_app, flash, has_request_context, jsonify, redirect, render_template, request, session, url_for
from db import DATABASES, add_cart_line_to_temp, build_pos_price_edited_report, build_pos_receipt_from_save_payload, build_pos_sales_list_summary, build_pos_shift_preclose_report, validate_pos_counter_dates_closed_for_sales_load, claim_next_pos_save_job, claim_pos_save_job_by_id, close_pos_counter_operation, compute_pos_settlement_payment_mode_summary, count_pos_held_bills_for_counter, count_pos_save_processing_jobs, create_pos_settlement_draft, delete_pos_counter_row, enqueue_pos_save_job, enrich_location_details_with_branch_logo, finalize_temp_bill, finish_pos_save_job, find_counter_by_systemname, find_open_counter_operation, fetch_counter_row_by_rowid, force_requeue_all_pos_save_processing_jobs, get_latest_closed_pos_date_for_counter, get_counter_name_by_code, get_counter_row_by_code, get_held_bill, get_item_warehouse_stock_qty, get_pos_bill_receipt_for_tab, get_pos_save_queue_job_detail, get_receipt_data_from_temp_bill, get_temp_bill_by_billno, get_base_locations_list, get_locations_list, get_next_countercode, get_system_config_rows, insert_pos_counter_row, is_location_warehouse_enabled, list_counter_operations_recent, list_pos_bills_canceled, list_pos_bills_held, list_pos_bills_posted, list_pos_canceled_bills_for_counter, list_pos_held_bills_for_counter, list_pos_counters_for_location, list_pos_save_queue, list_pos_settlement_drafts, list_pos_settlement_pending_by_date, list_temp_bills_for_pos_verify, list_warehouses_for_location, list_warehouse_picker_bins, mark_temp_bill_queued, open_pos_counter_operation, post_pos_settlement_draft, prepare_pos_save_queue_for_claim, release_stale_pos_save_processing_jobs, resolve_pos_settlement_default_date, resolve_pos_counter_warehouse, retry_pos_save_job, reverse_pos_settlement_gl_journal, settlement_tender_amounts_by_bill, update_pos_counter_row, verify_pos_settlement_draft, cancel_pos_settlement_draft, void_all_temp_bill, get_last_in_progress_bill, get_all_chart_of_accounts, get_pos_settlement_draft_detail, get_pos_settlement_account_defaults_from_tenders, get_pos_settlement_account_config, get_pos_tender_gl_by_code, upsert_pos_settlement_account_config, list_pos_tender_types, upsert_pos_tender_type_row, delete_pos_tender_type_row, list_pos_payment_tender_types, remove_cart_line_from_temp, get_item_by_alternate_barcode, get_item_by_code, get_item_by_manufacturer_id, get_item_alternate_uom_by_barcode, get_item_alternate_uoms, get_item_uom_pricing, get_categories, get_items_list, get_location_info_by_dbkey, get_next_bill_no, peek_next_bill_no, billhdr_exists, get_customers_master_list, get_customer_loyalty_for_picker, peek_next_customer_loyalty_code, insert_customer_loyalty_row, hold_bill, save_sales_invoice, pos_payload_credit_delta, validate_pos_credit_customer_accounts, ensure_billhdr_pos_settlement_columns, update_billhdr_pos_settlement_posting, simulate_pos_sale_stock_impact, read_pos_stock_live_snapshot, set_active_db_key, set_held_bill_in_progress, sync_cart_to_temp, update_cart_line_qty_in_temp, update_cart_line_discount_in_temp, update_cart_line_rate_in_temp, void_bill, void_cart_line_in_temp, _fetch_billhdr_rows_by_billnos, _fetch_billhdr_rows_for_pos_settlement, _is_pos_shift_credit_tender, _safe_rows, _get_table_columns, _table_exists, _shift_code_from_header, parse_billno_from_request, billno_is_valid, coerce_billno
from addons.document_numbering.document_numbering_db import DOC_TYPE_POS_INVOICE
from ..pos_page_cache import apply_pos_page_no_cache_headers, get_pos_asset_version, is_pos_html_page_path
from nexa_http import context as nexa_ctx
from nexa_http.templates_m import register_context_processor
from save_nonce import (
    commit_pos_save_nonce,
    extract_submitted_save_nonce,
    json_response_rotate_pos,
    refresh_pos_save_nonce,
    reject_invalid_pos_save_nonce,
    replay_blocked_response_pos,
)
_ADDON_ROOT = Path(__file__).resolve().parents[1]
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
bp = Blueprint('pos_billing', __name__, template_folder=str(_ADDON_ROOT / 'views' / 'templates'))
_POS_BILLING_SAVE_BUSY_KEY = '_pos_billing_save_busy_v1'


def _pos_parse_billno(raw: Any, *, empty_error: str = 'Bill number required') -> Tuple[Optional[Any], Optional[str]]:
    if raw is None or str(raw).strip() == '':
        return None, empty_error
    from db import _normalize_temp_billno
    bn, err = _normalize_temp_billno(raw)
    if err:
        if err == 'Bill number required.':
            return None, empty_error
        return None, err
    return bn, None


_POS_SETTLEMENT_POST_BUSY_KEY = '_pos_settlement_post_busy_v1'
_POS_SETTLEMENT_REVERSE_BUSY_KEY = '_pos_settlement_reverse_busy_v1'
_POS_QUEUE_WORKER_LOCK = threading.Lock()
_POS_QUEUE_WORKER_RUNNING = False
_POS_QUEUE_WORKER_THREAD: Optional[threading.Thread] = None
_POS_QUEUE_EXEC_LOCK = threading.Lock()
_POS_QUEUE_BUSY_SINCE = 0.0
_POS_QUEUE_BUSY_STALE_SEC = 300.0
_POS_TERMINAL_TAB_LOCKS: Dict[str, Dict[str, Any]] = {}
_POS_TERMINAL_TAB_LOCK_GUARD = threading.Lock()
_POS_TERMINAL_LOCK_STALE_SEC = 120.0

def _pos_terminal_lock_key(tenant_id: Optional[str], hostname_norm: str) -> str:
    return f"{tenant_id or 'default'}:{hostname_norm}"

def _pos_terminal_lock_prune(now: Optional[float] = None) -> None:
    ts = float(now if now is not None else time.time())
    stale = _POS_TERMINAL_LOCK_STALE_SEC
    dead = [
        k for k, v in _POS_TERMINAL_TAB_LOCKS.items()
        if ts - float(v.get('last_seen') or 0) > stale
    ]
    for k in dead:
        _POS_TERMINAL_TAB_LOCKS.pop(k, None)

def _pos_terminal_tab_lock_try_acquire(
    tenant_id: Optional[str],
    hostname_norm: str,
    tab_id: str,
    user: Optional[str],
    *,
    force: bool = False,
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    key = _pos_terminal_lock_key(tenant_id, hostname_norm)
    now = time.time()
    with _POS_TERMINAL_TAB_LOCK_GUARD:
        _pos_terminal_lock_prune(now)
        cur = _POS_TERMINAL_TAB_LOCKS.get(key)
        if cur and str(cur.get('tab_id') or '') != tab_id and not force:
            if now - float(cur.get('last_seen') or 0) <= _POS_TERMINAL_LOCK_STALE_SEC:
                return (False, key, dict(cur))
        _POS_TERMINAL_TAB_LOCKS[key] = {
            'tab_id': tab_id,
            'last_seen': now,
            'user': str(user or '').strip(),
            'hostname': hostname_norm,
        }
        return (True, key, None)

def _pos_terminal_tab_lock_touch(lock_key: str, tab_id: str) -> bool:
    now = time.time()
    with _POS_TERMINAL_TAB_LOCK_GUARD:
        _pos_terminal_lock_prune(now)
        cur = _POS_TERMINAL_TAB_LOCKS.get(lock_key)
        if not cur or str(cur.get('tab_id') or '') != tab_id:
            return False
        cur['last_seen'] = now
        return True

def _pos_terminal_tab_lock_release(lock_key: str, tab_id: str) -> None:
    with _POS_TERMINAL_TAB_LOCK_GUARD:
        cur = _POS_TERMINAL_TAB_LOCKS.get(lock_key)
        if cur and str(cur.get('tab_id') or '') == tab_id:
            _POS_TERMINAL_TAB_LOCKS.pop(lock_key, None)

def _pos_timing_log(label: str, start: float, **fields: Any) -> None:
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    extras = ' '.join(f'{k}={v}' for k, v in fields.items())
    print(f'[TIMING pos_billing] {label} elapsed_ms={elapsed_ms:.1f}' + (f' {extras}' if extras else ''))

_POS_COUNTER_LIST_PREF = ['locationcode', 'countercode', 'countername', 'warehouse_id', 'store', 'onlinesale', 'systemname', 'systemip', 'approved', 'createdby', 'createddate']

def _pos_counter_ordered_columns(display_cols: Any) -> list:
    low = [str(c).lower() for c in (display_cols or [])]
    head = [c for c in _POS_COUNTER_LIST_PREF if c in low]
    tail = [c for c in low if c not in _POS_COUNTER_LIST_PREF]
    return head + tail


def _pos_bytes_looks_like_pdf(raw: Optional[bytes]) -> bool:
    if not raw or len(raw) < 5:
        return False
    return raw[:5] == b'%PDF-'


def _pos_upload_looks_like_pdf(mime: str, filename: Optional[str]) -> bool:
    m = (mime or '').lower()
    if 'pdf' in m:
        return True
    fn = (filename or '').lower()
    return fn.endswith('.pdf')


def _pos_pdf_first_page_to_png_bytes(raw_pdf: bytes, *, max_bytes_out: int) -> Optional[bytes]:
    """Rasterize first PDF page to PNG for OpenAI vision (API does not accept PDF)."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return None
    doc = None
    try:
        doc = fitz.open(stream=raw_pdf, filetype='pdf')
        if doc.page_count < 1:
            return None
        page = doc.load_page(0)
        png_bytes = b''
        for dpi in (150, 120, 96, 72):
            zoom = dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            mx = max(pix.width, pix.height)
            cap = 2400
            if mx > cap:
                sc = cap / float(mx)
                mat = fitz.Matrix(zoom * sc, zoom * sc)
                pix = page.get_pixmap(matrix=mat, alpha=False)
            png_bytes = pix.tobytes('png')
            if len(png_bytes) <= max_bytes_out:
                break
        if len(png_bytes) > max_bytes_out:
            return None
        return png_bytes
    except Exception:
        return None
    finally:
        if doc is not None:
            doc.close()

def _try_acquire_pos_billing_save_lock(lock_seconds: float=180.0) -> bool:
    now = time.time()
    raw = session.get(_POS_BILLING_SAVE_BUSY_KEY)
    try:
        until = float(raw)
        if until > now:
            return False
    except (TypeError, ValueError):
        if raw:
            return False
    session[_POS_BILLING_SAVE_BUSY_KEY] = now + float(lock_seconds)
    session.modified = True
    return True


def _persist_pos_counter_session(counter_code: int, location_code: int) -> None:
    """Remember counter + warehouse scope in Flask session."""
    session['countercode'] = int(counter_code)
    cn = get_counter_name_by_code(
        counter_code,
        db_key=session.get('tenant_id') or 'HO',
        location_code=location_code,
    )
    session['countername'] = (cn or '').strip()
    _sync_pos_counter_warehouse_session(int(counter_code), int(location_code), session['countername'])


def _apply_pos_warehouse_to_header(header: Dict[str, Any]) -> None:
    """Stamp counter warehouse on save header (session at checkout; counter row in queue worker)."""
    if header.get('pos_store') or header.get('pos_warehouse_id'):
        return
    wh_ctx: Dict[str, Any] = {}
    if has_request_context():
        wh_ctx = _pos_session_warehouse_context()
    if not wh_ctx.get('warehouse_id') and not wh_ctx.get('store'):
        try:
            cc = int(header.get('countercode') or 0)
            lc = int(header.get('location_code') or 0)
            if cc > 0 and lc > 0:
                wh_ctx = resolve_pos_counter_warehouse(cc, lc)
        except (TypeError, ValueError):
            pass
    if wh_ctx.get('store'):
        header['pos_store'] = wh_ctx['store']
    if wh_ctx.get('warehouse_id'):
        header['pos_warehouse_id'] = wh_ctx['warehouse_id']
    if wh_ctx.get('bin_loc_key'):
        header['pos_bin_loc_key'] = wh_ctx['bin_loc_key']


def _apply_pos_save_header_flags(header: Dict[str, Any]) -> None:
    """POS → save_sales_invoice: C/R billtype from customer Cash/Credit; cash skips revenue GL, COGS posts on queue save."""
    header['pos_billing_save'] = True
    header['allow_negative_batch'] = True
    _apply_pos_warehouse_to_header(header)
    try:
        cc = int(header.get('customercode') or 0)
    except (TypeError, ValueError):
        cc = 0
    header['skip_gl_posting'] = cc <= 0
    header['post_cogs_inventory_gl'] = cc <= 0


def _pos_session_warehouse_context() -> Dict[str, Any]:
    """Counter warehouse from Flask session (set when counter is bound)."""
    if not has_request_context():
        return {}
    wh_id = session.get('pos_warehouse_id')
    try:
        wh_id_int = int(float(wh_id)) if wh_id is not None and str(wh_id).strip() != '' else None
    except (TypeError, ValueError):
        wh_id_int = None
    store = str(session.get('pos_store') or session.get('pos_warehouse_code') or '').strip().upper()
    warehouse_code = str(session.get('pos_warehouse_code') or store).strip().upper()
    warehouse_name = str(session.get('pos_warehouse_name') or '').strip()
    if not warehouse_code:
        cc = _session_pos_counter_code()
        if cc:
            try:
                lc = int(_resolve_location_code() or 0)
                if lc > 0:
                    ctx = resolve_pos_counter_warehouse(cc, lc)
                    _sync_pos_counter_warehouse_session(cc, lc, str(session.get('countername') or ''))
                    warehouse_code = str(ctx.get('warehouse_code') or '').strip().upper()
                    warehouse_name = str(ctx.get('warehouse_name') or '').strip()
                    wh_id_int = ctx.get('warehouse_id')
                    store = str(ctx.get('store') or warehouse_code).strip().upper()
            except (TypeError, ValueError):
                pass
    return {
        'warehouse_id': wh_id_int,
        'warehouse_code': warehouse_code,
        'warehouse_name': warehouse_name,
        'store': store or None,
        'bin_loc_key': str(session.get('pos_bin_loc_key') or '').strip() or None,
    }


def _sync_pos_counter_warehouse_session(countercode: int, location_code: int, countername: str='') -> None:
    """Load register warehouse scope into session after counter bind / page load."""
    ctx = resolve_pos_counter_warehouse(countercode, int(location_code))
    session['pos_warehouse_id'] = ctx.get('warehouse_id')
    session['pos_warehouse_code'] = ctx.get('warehouse_code')
    session['pos_warehouse_name'] = ctx.get('warehouse_name')
    session['pos_store'] = ctx.get('store')
    session['pos_bin_loc_key'] = ctx.get('bin_loc_key')
    if countername:
        session['countername'] = countername.strip()
    session.modified = True


def _pos_counter_setup_selected_warehouse_id(counter_row: Dict[str, Any], location_code: int) -> Optional[int]:
    """Edit form: prefer ``WAREHOUSE_ID``, else match legacy ``STORE`` to ``WAREHOUSE_CODE``."""
    raw = counter_row.get('warehouse_id')
    if raw is not None and str(raw).strip() != '':
        try:
            return int(float(raw))
        except (TypeError, ValueError):
            pass
    legacy = str(counter_row.get('store') or '').strip().upper()
    if not legacy:
        return None
    for wh in list_warehouses_for_location(int(location_code), active_only=False):
        if str(wh.get('warehouse_code') or '').upper() == legacy:
            return int(wh['warehouse_id'])
    return None

def _release_pos_billing_save_lock() -> None:
    session.pop(_POS_BILLING_SAVE_BUSY_KEY, None)
    session.modified = True


def _try_acquire_pos_settlement_post_lock(lock_seconds: float = 120.0) -> bool:
    """One settlement GL post at a time per browser session (expires if handler crashes)."""
    now = time.time()
    raw = session.get(_POS_SETTLEMENT_POST_BUSY_KEY)
    try:
        until = float(raw)
        if until > now:
            return False
    except (TypeError, ValueError):
        if raw:
            return False
    session[_POS_SETTLEMENT_POST_BUSY_KEY] = now + float(lock_seconds)
    session.modified = True
    return True


def _release_pos_settlement_post_lock() -> None:
    session.pop(_POS_SETTLEMENT_POST_BUSY_KEY, None)
    session.modified = True


def _try_acquire_pos_settlement_reverse_lock(lock_seconds: float = 120.0) -> bool:
    """One settlement GL reverse at a time per browser session (expires if handler crashes)."""
    now = time.time()
    raw = session.get(_POS_SETTLEMENT_REVERSE_BUSY_KEY)
    try:
        until = float(raw)
        if until > now:
            return False
    except (TypeError, ValueError):
        if raw:
            return False
    session[_POS_SETTLEMENT_REVERSE_BUSY_KEY] = now + float(lock_seconds)
    session.modified = True
    return True


def _release_pos_settlement_reverse_lock() -> None:
    session.pop(_POS_SETTLEMENT_REVERSE_BUSY_KEY, None)
    session.modified = True


def _execute_claimed_pos_save_job(job: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[int]]:
    """Run save_sales_invoice for a queue row already in PROCESSING. Returns (ok, error, posted_billno)."""
    job_id = int(job.get('job_id') or 0)
    payload = job.get('payload') or {}
    try:
        header = payload.get('header') or {}
        lines = payload.get('lines') or []
        if not header.get('countercode') and job.get('countercode'):
            try:
                header['countercode'] = int(job.get('countercode'))
            except (TypeError, ValueError):
                pass
        if not header.get('location_code') and job.get('location_code'):
            try:
                header['location_code'] = int(job.get('location_code'))
            except (TypeError, ValueError):
                pass
        _apply_pos_save_header_flags(header)
        try:
            lc_date = int(header.get('location_code') or payload.get('location_code') or job.get('location_code') or 0)
        except (TypeError, ValueError):
            lc_date = 0
        if lc_date > 0:
            _apply_open_shift_posdate_to_pos_header_billdate(header, lc_date)
        try:
            reserved_billno = int(header.get('billno') or job.get('billno') or 0)
        except (TypeError, ValueError):
            reserved_billno = 0
        try:
            lc_chk = int(header.get('location_code') or payload.get('location_code') or job.get('location_code') or 0)
        except (TypeError, ValueError):
            lc_chk = 0
        if reserved_billno > 0 and lc_chk > 0 and billhdr_exists(lc_chk, reserved_billno):
            try:
                finalize_temp_bill(int(payload.get('temp_billno') or reserved_billno), lc_chk)
            except Exception as cleanup_exc:
                print(f'[WARN POS queue temp cleanup reconcile] job={job_id}: {cleanup_exc}')
            finish_pos_save_job(job_id, True, reserved_billno, None)
            return (True, None, reserved_billno)
        try:
            cc_chk = int(header.get('customercode') or 0)
        except (TypeError, ValueError):
            cc_chk = 0
        if cc_chk > 0:
            ok_gl, gl_msg = validate_pos_credit_customer_accounts(lc_chk, cc_chk, proposed_credit_delta=pos_payload_credit_delta(header, lines))
            if not ok_gl:
                msg = gl_msg or 'Credit sale cannot post to accounts.'
                finish_pos_save_job(job_id, False, None, msg)
                return (False, msg, None)
        ok, error, posted_billno, _stock_debug = save_sales_invoice({'header': header, 'lines': lines})
        if not ok:
            msg = error or 'Save failed'
            finish_pos_save_job(job_id, False, None, msg)
            return (False, msg, None)
        try:
            finalize_temp_bill(int(payload.get('temp_billno') or header.get('billno') or job.get('billno') or 0), int(header.get('location_code') or job.get('location_code') or 0))
        except Exception as cleanup_exc:
            print(f'[WARN POS queue temp cleanup] job={job_id}: {cleanup_exc}')
        posted_int = int(posted_billno or 0)
        finish_pos_save_job(job_id, True, posted_int, None)
        return (True, None, posted_int)
    except Exception as exc:
        msg = str(exc)
        finish_pos_save_job(job_id, False, None, msg)
        return (False, msg, None)


def _process_one_pos_queue_job(tenant_id: Optional[str]) -> bool:
    global _POS_QUEUE_BUSY_SINCE
    try:
        if tenant_id:
            set_active_db_key(tenant_id)
        acquired = _POS_QUEUE_EXEC_LOCK.acquire(timeout=0.05)
        if not acquired:
            if _POS_QUEUE_BUSY_SINCE and time.time() - _POS_QUEUE_BUSY_SINCE > _POS_QUEUE_BUSY_STALE_SEC:
                print('[POS_SAVE_QUEUE] exec lock held > stale threshold; allowing recovery claim')
                acquired = _POS_QUEUE_EXEC_LOCK.acquire(timeout=0.05)
            if not acquired:
                return False
        try:
            _POS_QUEUE_BUSY_SINCE = time.time()
            job = claim_next_pos_save_job()
            if not job:
                return False
            _execute_claimed_pos_save_job(job)
            return True
        finally:
            _POS_QUEUE_BUSY_SINCE = 0.0
            _POS_QUEUE_EXEC_LOCK.release()
    finally:
        if tenant_id:
            set_active_db_key(None)

def _pos_queue_worker(tenant_id: Optional[str]) -> None:
    global _POS_QUEUE_WORKER_RUNNING
    try:
        while True:
            processed = _process_one_pos_queue_job(tenant_id)
            if not processed:
                break
    finally:
        with _POS_QUEUE_WORKER_LOCK:
            _POS_QUEUE_WORKER_RUNNING = False

def _kick_pos_queue_worker(tenant_id: Optional[str]) -> None:
    global _POS_QUEUE_WORKER_RUNNING, _POS_QUEUE_WORKER_THREAD
    tid = (str(tenant_id).strip() if tenant_id else '') or 'HO'
    set_active_db_key(tid)
    try:
        prepare_pos_save_queue_for_claim()
        processing_cnt = count_pos_save_processing_jobs()
    except Exception as exc:
        print(f'[POS_SAVE_QUEUE] kick prep failed: {exc}')
        processing_cnt = 0
    with _POS_QUEUE_WORKER_LOCK:
        if _POS_QUEUE_WORKER_RUNNING:
            alive = _POS_QUEUE_WORKER_THREAD is not None and _POS_QUEUE_WORKER_THREAD.is_alive()
            busy_stale = bool(_POS_QUEUE_BUSY_SINCE and time.time() - _POS_QUEUE_BUSY_SINCE > _POS_QUEUE_BUSY_STALE_SEC)
            if alive and not busy_stale and processing_cnt <= 1:
                return
            print(
                f'[POS_SAVE_QUEUE] restarting worker (alive={alive} busy_stale={busy_stale} processing={processing_cnt})'
            )
            _POS_QUEUE_WORKER_RUNNING = False
        _POS_QUEUE_WORKER_RUNNING = True
        t = threading.Thread(target=_pos_queue_worker, args=(tid,), daemon=True, name='pos-save-queue-worker')
        _POS_QUEUE_WORKER_THREAD = t
        t.start()

def _get_receipt_design_path() -> str:
    try:
        instance = getattr(current_app, 'instance_path', None)
        if instance and os.path.isdir(instance):
            return os.path.join(instance, 'receipt_design.json')
    except RuntimeError:
        pass
    return os.path.join(os.path.dirname(current_app.root_path or '.'), 'instance', 'receipt_design.json')

_RECEIPT_DESIGN_CACHE_MTIME: float = -2.0
_RECEIPT_DESIGN_CACHE_VALUE: Optional[Dict[str, Any]] = None


def load_receipt_design() -> Dict[str, Any]:
    """Load receipt design config from JSON file; merge with defaults. Cached by file mtime."""
    global _RECEIPT_DESIGN_CACHE_MTIME, _RECEIPT_DESIGN_CACHE_VALUE
    path = _get_receipt_design_path()
    try:
        mtime = os.path.getmtime(path) if os.path.isfile(path) else 0.0
    except OSError:
        mtime = 0.0
    if _RECEIPT_DESIGN_CACHE_VALUE is not None and mtime == _RECEIPT_DESIGN_CACHE_MTIME:
        return dict(_RECEIPT_DESIGN_CACHE_VALUE)
    config = dict(DEFAULT_RECEIPT_DESIGN)
    try:
        if os.path.isfile(path):
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for key in ('page_width', 'header', 'bill', 'items', 'summary', 'footer', 'labels', 'output_encoding', 'nls_lang', 'escpos_left_align', 'escpos_header_double_height', 'paper_width_mm', 'receipt_printer_name', 'receipt_printer_ip'):
                if key in data:
                    if isinstance(config.get(key), dict) and isinstance(data[key], dict):
                        config[key] = {**config[key], **data[key]}
                    else:
                        config[key] = data[key]
    except Exception:
        pass
    _RECEIPT_DESIGN_CACHE_MTIME = mtime
    _RECEIPT_DESIGN_CACHE_VALUE = dict(config)
    return dict(config)


def _invalidate_receipt_design_cache() -> None:
    global _RECEIPT_DESIGN_CACHE_MTIME, _RECEIPT_DESIGN_CACHE_VALUE
    _RECEIPT_DESIGN_CACHE_MTIME = -2.0
    _RECEIPT_DESIGN_CACHE_VALUE = None

def save_receipt_design(config: Dict[str, Any]) -> bool:
    """Save receipt design config to JSON file."""
    try:
        path = _get_receipt_design_path()
        base = os.path.dirname(path)
        if base and (not os.path.isdir(base)):
            os.makedirs(base, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
        return True
    except Exception:
        return False
    finally:
        _invalidate_receipt_design_cache()

def _apply_active_connection(location_code_or_dbkey) -> None:
    key = (str(location_code_or_dbkey).strip() if location_code_or_dbkey is not None else '') or 'HO'
    set_active_db_key(key)

def _resolve_location_code() -> int:
    location_code_value = session.get('location_code')
    location_code_int = None
    if location_code_value is not None:
        try:
            if str(location_code_value).isdigit():
                location_code_int = int(location_code_value)
        except Exception:
            location_code_int = None
    if location_code_int is None:
        user_dbkey = session.get('tenant_id') or 'HO'
        try:
            location_info = get_location_info_by_dbkey(user_dbkey)
            location_code_int = location_info.get('locationcode') if location_info else 1
        except Exception:
            location_code_int = 1
    return int(location_code_int)


def _pos_settlement_branch_display() -> Tuple[int, str]:
    """Branch code and label for POS settlement screens (session tenant DB)."""
    location_code_int = _resolve_location_code()
    locations = get_locations_list() or []
    branch_display = str(location_code_int)
    for loc in locations:
        if not isinstance(loc, dict):
            continue
        loc_code = loc.get('code')
        if loc_code is None:
            loc_code = loc.get('CODE')
        try:
            if loc_code is not None and int(loc_code) == int(location_code_int):
                nm = str(loc.get('name') or loc.get('NAME') or '').strip()
                branch_display = f'{nm} ({loc_code})'.strip() if nm else str(loc_code)
                break
        except (TypeError, ValueError):
            continue
    return location_code_int, branch_display


def _billhdr_has_pos_settlement_columns() -> bool:
    cols_u = {str(c).upper() for c in (_get_table_columns('BILLHDR') or [])}
    return 'POS_SETTLEMENT_STATUS' in cols_u


def _fetch_pos_settlement_candidate_bills(
    location_code: int,
    limit: int = 500,
    settlement_scope: str = 'all',
    *,
    include_credit_sales: bool = False,
    from_dt: str = '',
    to_dt: str = '',
    fast: bool = True,
) -> List[Dict[str, Any]]:
    """POS bills from BILLHDR; optional filter by ``POS_SETTLEMENT_STATUS`` (pending / settled / cancelled / all).

    When ``include_credit_sales`` is False (default), on-account invoices (``BILLTYPE='R'`` with customer) are
    excluded — matching POS settlement scope. Set True for POS Sales List and other inclusive reports.
    """
    if not fast or not _billhdr_has_pos_settlement_columns():
        ensure_billhdr_pos_settlement_columns()
    cols = _get_table_columns('BILLHDR')
    if not cols:
        return []
    cols_u = {str(c).upper() for c in cols}
    if 'BILLNO' not in cols_u:
        return []
    base = [
        'BILLNO', 'BILLDATE', 'BILLTIME', 'NETBILLAMOUNT', 'DISCOUNTAMOUNT',
        'CUSTOMERCODE', 'CUSTOMERNAME', 'COUNTERCODE', 'LOCATIONCODE', 'BILLTYPE',
    ]
    optional = [
        'CREATEDBY', 'USERID', 'USERNAME', 'CASHAMOUNT', 'CARDAMOUNT', 'WALLETAMOUNT',
        'ONLINEAMOUNT', 'CREDITAMOUNT', 'TAXAMOUNT', 'VATAMOUNT', 'VAT', 'PAYMENTMODE', 'PAYMENTTYPE', 'PAYMODE', 'PAYTYPE',
        'POS_SETTLEMENT_STATUS', 'POS_SETTLEMENT_VOUCHER_NO', 'POS_SETTLEMENT_NOTE',
    ]
    select_cols = [c for c in base if c in cols_u]
    for c in optional:
        if c in cols_u and c not in select_cols:
            select_cols.append(c)
    use_paymode_posdate = False
    if not fast and _table_exists('POS_BILL_PAYMODE'):
        pm_cols_u = {str(c).upper() for c in (_get_table_columns('POS_BILL_PAYMODE') or [])}
        if {'LOCATIONCODE', 'BILLNO', 'POSDATE'}.issubset(pm_cols_u) and {'LOCATIONCODE', 'BILLNO'}.issubset(cols_u):
            use_paymode_posdate = True
    bh = 'b.' if use_paymode_posdate else ''
    select_exprs = [f'{bh}{c}' for c in select_cols]
    if use_paymode_posdate:
        select_exprs.append('pm_agg.POSDATE AS POSDATE')
    where_parts: List[str] = []
    params: Dict[str, Any] = {'lim': max(1, min(int(limit), 500))}
    if 'LOCATIONCODE' in cols_u:
        where_parts.append(f'{bh}LOCATIONCODE = :loc')
        params['loc'] = location_code
    if 'DELFLAG' in cols_u:
        where_parts.append(f"NVL({bh}DELFLAG, 'N') <> 'Y'")
    if 'BILLSTATUS' in cols_u:
        where_parts.append(f"NVL({bh}BILLSTATUS, ' ') <> 'V'")
    if not include_credit_sales:
        # POS settlement: skip on-account / credit invoices (save_sales_invoice sets BILLTYPE='R' when customercode>0).
        if 'BILLTYPE' in cols_u and 'CUSTOMERCODE' in cols_u:
            where_parts.append(
                f"NOT (UPPER(NVL(TRIM(TO_CHAR({bh}BILLTYPE)), ' ')) = 'R' AND NVL({bh}CUSTOMERCODE, 0) > 0)"
            )
        elif 'BILLTYPE' in cols_u:
            where_parts.append(f"UPPER(NVL(TRIM(TO_CHAR({bh}BILLTYPE)), ' ')) <> 'R'")
    scope = (settlement_scope or 'all').strip().lower()
    if scope not in ('all', 'pending', 'settled', 'cancelled'):
        scope = 'all'
    if 'POS_SETTLEMENT_STATUS' in cols_u:
        if scope == 'pending':
            where_parts.append(f"NVL({bh}POS_SETTLEMENT_STATUS, 'PENDING') = 'PENDING'")
        elif scope == 'settled':
            where_parts.append(f"{bh}POS_SETTLEMENT_STATUS = 'SETTLED'")
        elif scope == 'cancelled':
            where_parts.append(f"{bh}POS_SETTLEMENT_STATUS = 'CANCELLED'")
    if 'BILLDATE' in cols_u:
        bill_date_col = f'NVL(pm_agg.POSDATE, {bh}BILLDATE)' if use_paymode_posdate else f'{bh}BILLDATE'
        from_clean = (from_dt or '').strip()[:10]
        to_clean = (to_dt or '').strip()[:10]
        if from_clean:
            where_parts.append(f'{bill_date_col} >= TO_DATE(:from_dt, \'YYYY-MM-DD\')')
            params['from_dt'] = from_clean
        if to_clean:
            where_parts.append(f'{bill_date_col} < TO_DATE(:to_dt, \'YYYY-MM-DD\') + 1')
            params['to_dt'] = to_clean
    where_sql = ('WHERE ' + ' AND '.join(where_parts)) if where_parts else ''
    if use_paymode_posdate:
        from_sql = (
            'BILLHDR b LEFT JOIN ('
            'SELECT LOCATIONCODE, BILLNO, MIN(POSDATE) AS POSDATE '
            'FROM POS_BILL_PAYMODE WHERE LOCATIONCODE = :loc '
            'GROUP BY LOCATIONCODE, BILLNO'
            ') pm_agg ON pm_agg.LOCATIONCODE = b.LOCATIONCODE AND pm_agg.BILLNO = b.BILLNO'
        )
        order_date = f'NVL(pm_agg.POSDATE, {bh}BILLDATE)' if 'BILLDATE' in cols_u else f'{bh}BILLDATE'
        order_billno = f'{bh}BILLNO'
    else:
        from_sql = 'BILLHDR'
        order_date = 'BILLDATE' if 'BILLDATE' in cols_u else 'BILLNO'
        order_billno = 'BILLNO'
    hint = f'/*+ FIRST_ROWS({params["lim"]}) */ '
    inner = (
        f'\n        SELECT {hint}{", ".join(select_exprs)}\n'
        f'        FROM {from_sql}\n'
        f'        {where_sql}\n'
        f'        ORDER BY {order_date} DESC NULLS LAST, {order_billno} DESC\n'
        '    '
    )
    q = f'SELECT * FROM ({inner}) WHERE ROWNUM <= :lim'
    return _safe_rows(q, params) or []


def _billhdr_row_to_settlement_bill(r: Dict[str, Any]) -> Dict[str, Any]:
    rk = {str(k).lower(): v for k, v in r.items()}

    def _fmt_date(d: Any) -> str:
        if d is None:
            return ''
        if hasattr(d, 'strftime'):
            try:
                return d.strftime('%Y-%m-%d')
            except Exception:
                return str(d)
        return str(d)

    def _f(key: str) -> float:
        try:
            return float(rk.get(key) or 0)
        except (TypeError, ValueError):
            return 0.0

    billno = rk.get('billno')
    net = _f('netbillamount')
    disc = _f('discountamount')
    gross = net + disc
    tax = _f('taxamount') + _f('vatamount') + _f('vat')
    cash_amt = _f('cashamount')
    card_amt = _f('cardamount')
    wallet_amt = _f('walletamount') + _f('onlineamount')
    credit_amt = _f('creditamount')
    pay_mode = (rk.get('paymentmode') or rk.get('paymenttype') or rk.get('paymode') or rk.get('paytype') or '').strip()
    bt = str(rk.get('billtype') or '').strip().upper()
    if bt == 'R':
        pay_mode = 'Credit'
        if credit_amt <= 0:
            credit_amt = net
    elif not pay_mode:
        if cash_amt > 0 and card_amt <= 0 and wallet_amt <= 0 and credit_amt <= 0:
            pay_mode = 'Cash'
        elif card_amt > 0 and cash_amt <= 0 and wallet_amt <= 0 and credit_amt <= 0:
            pay_mode = 'Card'
        elif wallet_amt > 0 and cash_amt <= 0 and card_amt <= 0 and credit_amt <= 0:
            pay_mode = 'Wallet / Online'
        elif credit_amt > 0:
            pay_mode = 'Credit'
        elif cash_amt > 0 or card_amt > 0 or wallet_amt > 0:
            bits: List[str] = []
            if cash_amt > 0.005:
                bits.append('Cash')
            if card_amt > 0.005:
                bits.append('Card')
            if wallet_amt > 0.005:
                bits.append('Wallet')
            if credit_amt > 0.005:
                bits.append('Credit')
            pay_mode = ' + '.join(bits) if bits else 'Mixed'
        else:
            pay_mode = 'Cash'

    cashier = (
        str(rk.get('createdby') or rk.get('userid') or rk.get('username') or '').strip() or '—'
    )

    raw_settlement = str(rk.get('pos_settlement_status') or '').strip().upper()
    if raw_settlement == 'SETTLED':
        settlement_ui = 'Posted'
    elif raw_settlement == 'CANCELLED':
        settlement_ui = 'Cancelled'
    else:
        settlement_ui = 'Pending'
    posted_voucher = str(rk.get('pos_settlement_voucher_no') or '').strip()
    remarks = str(rk.get('pos_settlement_note') or '').strip()

    return {
        'billNo': str(billno) if billno is not None else '',
        'billDate': _fmt_date(rk.get('posdate') or rk.get('billdate')),
        'cashier': cashier,
        'counter': str(rk.get('countercode') if rk.get('countercode') is not None else ''),
        'customer': str(rk.get('customername') or '').strip() or str(rk.get('customercode') or ''),
        'paymentType': pay_mode,
        'grossAmount': round(gross, 2),
        'discount': round(disc, 2),
        'tax': round(tax, 2),
        'netAmount': round(net, 2),
        'cashAmount': round(cash_amt, 2),
        'cardAmount': round(card_amt, 2),
        'walletAmount': round(wallet_amt, 2),
        'creditAmount': round(credit_amt, 2),
        'settlementStatus': settlement_ui,
        'postedVoucher': posted_voucher if posted_voucher else '—',
        'remarks': remarks,
        'selected': True,
    }


_EAN13_L = ('0001101', '0011001', '0010011', '0111101', '0100011', '0110001', '0101111', '0111011', '0110111', '0001011')
_EAN13_G = ('0100111', '0110011', '0011011', '0100001', '0011101', '0111001', '0000101', '0010001', '0001001', '0010111')
_EAN13_R = ('1110010', '1100110', '1101100', '1000010', '1011100', '1001110', '1010000', '1000100', '1001000', '1110100')
_EAN13_FIRST = ('LLLLLL', 'LLGLGG', 'LLGGLG', 'LLGGGL', 'LGLLGG', 'LGGLLG', 'LGGGLL', 'LGLGLG', 'LGLGGL', 'LGGLGL')

def _ean13_check_digit(s12: str) -> int:
    """Compute EAN-13 check digit for 12-digit string (digits 1-12)."""
    s12 = ''.join((c for c in s12 if c.isdigit()))[:12].zfill(12)
    total = 0
    for i, c in enumerate(s12):
        total += int(c) * (1 if i % 2 == 0 else 3)
    return (10 - total % 10) % 10

def _to_ean13(receiptno: Any) -> str:
    """Convert receipt number to 13-digit EAN-13 (pad left with zeros, add check digit)."""
    s = ''.join((c for c in str(receiptno) if c.isdigit()))
    if not s:
        s = '0'
    s12 = s[-12:].zfill(12)
    check = _ean13_check_digit(s12)
    return s12 + str(check)

def _ean13_to_bar_pattern(ean13: str) -> str:
    """Return 102-module EAN-13 bar pattern as string of '1' (bar) and '0' (space)."""
    if len(ean13) != 13 or not all((c.isdigit() for c in ean13)):
        return ''
    first = int(ean13[0])
    left_sets = _EAN13_FIRST[first]
    out = ['101']
    for i in range(1, 7):
        d = int(ean13[i])
        pat = _EAN13_L[d] if left_sets[i - 1] == 'L' else _EAN13_G[d]
        out.append(pat)
    out.append('01010')
    for i in range(7, 13):
        d = int(ean13[i])
        out.append(_EAN13_R[d])
    out.append('101')
    return ''.join(out)

def _ascii_ean13_line(ean13: str, width: int) -> str:
    """One line of ASCII-art EAN-13 bars; number printed below. Always fits in width (never long)."""
    pattern = _ean13_to_bar_pattern(ean13)
    if not pattern:
        return ('|' * min(width, 20))[:width]
    n = len(pattern)
    if n <= width:
        line = ''.join(('|' if m == '1' else ' ' for m in pattern))
        return (line + ' ' * width)[:width]
    result = []
    for i in range(width):
        start = int(i * n / width)
        end = int((i + 1) * n / width)
        segment = pattern[start:end] if end > start else pattern[start:start + 1]
        bars = segment.count('1')
        result.append('|' if bars * 2 >= len(segment) else ' ')
    return ''.join(result)[:width]

def _ascii_barcode_line(s: str, width: int) -> str:
    """One line of ASCII-art barcode (bars) for the given string. Uses | and space. Fallback if not EAN-13."""
    if not s or width < 8:
        return '|' * min(width, 20)
    s = str(s).strip()
    result = []
    for i, c in enumerate(s):
        n = ord(c) % 11
        result.append('|' * (1 + n % 3))
        result.append(' ' * (1 + n % 2))
    line = ''.join(result)
    if len(line) > width:
        line = line[:width]
    elif len(line) < width:
        line = line + ' ' * (width - len(line))
    return line

def _fmt_num(n: float, decimals: int=0) -> str:
    """Format number with optional decimals and thousands comma (e.g. 5,000 or 15,000.00)."""
    if decimals == 0:
        s = '%d' % round(n)
    else:
        s = ('%.' + str(decimals) + 'f') % n
    if '.' in s:
        int_part, dec_part = s.split('.', 1)
        parts = []
        while len(int_part) > 3:
            parts.append(int_part[-3:])
            int_part = int_part[:-3]
        if int_part:
            parts.append(int_part)
        s = ','.join(reversed(parts)) + '.' + dec_part
    else:
        parts = []
        while len(s) > 3:
            parts.append(s[-3:])
            s = s[:-3]
        if s:
            parts.append(s)
        s = ','.join(reversed(parts))
    return s


def _receipt_points_display(v: Any) -> str:
    """Format loyalty points for receipt footer (whole number when integral)."""
    try:
        n = float(v if v is not None else 0)
    except (TypeError, ValueError):
        return '0.00'
    if abs(n - round(n)) < 1e-9:
        return '%d' % int(round(n))
    return '%.2f' % n


def _receipt_to_plain_text(receipt: Dict[str, Any], design: Optional[Dict[str, Any]]=None, *, for_escpos: bool=False, include_copy_banner: bool=False) -> str:
    """Build plain-text receipt using design config (page width, which fields to show)."""
    design = design or load_receipt_design()
    hdr = design.get('header') or {}
    bill = design.get('bill') or {}
    items_cfg = design.get('items') or {}
    footer_cfg = design.get('footer') or {}
    labels = design.get('labels') or {}
    w = min(42, max(24, min(80, int(design.get('page_width', RECEIPT_WIDTH)))))
    loc = receipt.get('location_details') or {}
    loc_name = (loc.get('locationname') or '').strip() or 'Receipt'
    loc_address = str(loc.get('address') or '').strip()
    loc_telephone = str(loc.get('telephone') or loc.get('phone') or loc.get('tel') or '').strip()
    receiptno = receipt.get('receiptno', '')
    user = (receipt.get('user') or '').strip()
    billdate = (receipt.get('billdate') or '').strip()
    billtime = (receipt.get('billtime') or '').strip()
    countercode = receipt.get('countercode') or ''
    lines = receipt.get('lines') or []
    footer = receipt.get('footer') or {}
    net_total = float(footer.get('net_total', 0))
    disc_total = float(footer.get('discount_total', 0))
    grand_total = net_total + disc_total
    message = (footer.get('message') or 'Thank you.').strip()
    extras = receipt.get('receipt_extras') if isinstance(receipt.get('receipt_extras'), dict) else {}
    try:
        tender_raw = extras.get('tender_total')
        tender_total = float(tender_raw if tender_raw is not None else net_total)
    except (TypeError, ValueError):
        tender_total = net_total
    try:
        ch_raw = extras.get('change')
        change_total = float(ch_raw if ch_raw is not None else 0)
    except (TypeError, ValueError):
        change_total = 0
    payment_label = (extras.get('payment_type_label') or '').strip()
    loyalty_only_line = (extras.get('loyalty_customer_line') or '').strip()
    total_pts_val = extras.get('total_points')

    try:
        cc_rec = int(float(receipt.get('customercode') or 0))
    except (TypeError, ValueError):
        cc_rec = 0
    bt_rec = str(receipt.get('billtype') or '').strip().upper()[:1]
    is_credit_footer = bool(extras.get('credit_sale')) or bt_rec == 'R' or (bt_rec in ('P', 'V', 'H') and cc_rec > 0)

    def center(text: Any) -> str:
        return str(text or '')[:w].center(w)

    esc_big_hdr = bool(for_escpos) and bool(design.get('escpos_header_double_height', True))

    def store_name_row(txt: str) -> str:
        row = center(txt)
        if esc_big_hdr:
            return '\x1d!\x11' + row + '\x1d!\x00'
        return row

    def rule(ch: str='-') -> str:
        return ch * w

    def two_col(left: Any, right: Any) -> str:
        left_s = str(left or '')
        right_s = str(right or '')
        gap = max(1, w - len(left_s) - len(right_s))
        return (left_s + ' ' * gap + right_s)[:w]

    def amount(v: Any) -> str:
        try:
            return f'{float(v or 0):.2f}'
        except Exception:
            return '0.00'

    def qty(v: Any) -> str:
        try:
            n = float(v or 0)
            return f'{n:.3f}' if abs(n - int(n)) > 0.0001 else f'{n:.3f}'
        except Exception:
            return '0.000'
    out = []
    if hdr.get('business_name', True):
        out.append(store_name_row(loc_name.upper()))
    if loc_address:
        for seg in textwrap.wrap(loc_address, width=max(16, w), break_long_words=True, replace_whitespace=False):
            out.append(center(seg.strip()))
    if loc_telephone:
        out.append(center('Telephone : ' + loc_telephone))
    if include_copy_banner:
        out.append(center('*** COPY ***'))
    out.append(rule('-'))
    if any((items_cfg.get(k, True) for k in ('slno', 'item', 'unit_price', 'qty', 'line_total'))):
        out.append(('%-4s %-11s %6s %5s %6s' % ('Sl.N', 'Barcode', 'Qty', 'Rate', 'Amount'))[:w])
        out.append(rule('-'))
    for line in lines:
        slno = str(line.get('slno') or '')
        barcode = str(line.get('barcode') or line.get('manufacturerid') or '').strip()
        item_name = (line.get('item') or '').strip() if items_cfg.get('item', True) else ''
        qty_str = qty(line.get('qty', 0)) if items_cfg.get('qty', True) else ''
        rate_str = amount(line.get('rate', 0)) if items_cfg.get('unit_price', True) else ''
        amount_str = amount(line.get('amount', 0)) if items_cfg.get('line_total', True) else ''
        item_ara = (line.get('item_ara') or '').strip() if items_cfg.get('item_ara', True) else ''
        out.append(('%-4s %-11s %6s %5s %6s' % (slno[:4], '', qty_str[-6:], rate_str[-5:], amount_str[-6:]))[:w])
        if barcode:
            for seg in textwrap.wrap(barcode, width=max(12, w), break_long_words=True, replace_whitespace=False):
                out.append(seg[:w])
        if item_name:
            out.append(('    ' + item_name)[:w])
        try:
            line_disc = float(line.get('disc') or line.get('discount') or line.get('itdisc') or 0)
        except (TypeError, ValueError):
            line_disc = 0
        if line_disc > 0.0005:
            try:
                qv = float(line.get('qty') or 0)
                rv = float(line.get('rate') or 0)
                gross = abs(qv * rv)
            except (TypeError, ValueError):
                gross = 0.0
            if gross < 1e-6:
                try:
                    gross = abs(float(line.get('amount') or 0)) + abs(line_disc)
                except (TypeError, ValueError):
                    gross = abs(line_disc)
            if gross > 1e-6:
                pct_txt = '%.1f%%' % (100.0 * abs(line_disc) / gross,)
            else:
                pct_txt = '0.0%%'
            out.append(('    Discount: ' + amount(line_disc) + ' (' + pct_txt + ')')[:w])
        if item_ara:
            out.append(('    ' + item_ara)[:w])
    out.append(rule('-'))
    out.append('')
    out.append(two_col('Grand Total', 'QAR ' + amount(grand_total)))
    out.append(two_col('Discount', 'QAR ' + amount(disc_total)))
    out.append(two_col('Net Total', 'QAR ' + amount(net_total)))
    out.append(rule('-'))
    out.append('')
    if is_credit_footer:
        cc_disp = str(receipt.get('customercode') if receipt.get('customercode') is not None else '').strip()
        cn_disp = str(receipt.get('customername') or '').strip()
        on_disp = str(receipt.get('orderno') or '').strip()
        out.append(two_col('Customer Code', cc_disp or '-'))
        label_cn = 'Customer Name'
        cn_nm = cn_disp if cn_disp else '-'
        rem = w - len(label_cn) - 1
        if rem >= 4 and len(cn_nm) <= rem:
            out.append(two_col(label_cn, cn_nm))
        else:
            out.append(label_cn[:w])
            wrap_w = max(16, w)
            for seg in textwrap.wrap(cn_nm, width=wrap_w, break_long_words=True, replace_whitespace=False):
                out.append(seg[:w])
        out.append(two_col('Order No', on_disp or '-'))
    else:
        out.append(two_col('Qatar Riyals QR', amount(tender_total)))
        out.append(two_col('Change Qatar Riyals QR', amount(change_total)))
    out.append('')
    out.append(rule('-'))
    pay_show = payment_label or 'Cash'
    out.append(two_col('Payment Type', pay_show))
    pts_display = _receipt_points_display(total_pts_val if total_pts_val is not None else 0)
    if loyalty_only_line:
        label_loy = 'Loyalty Customer'
        rem_loy = w - len(label_loy) - 1
        if rem_loy >= 4 and len(loyalty_only_line) <= rem_loy:
            out.append(two_col(label_loy, loyalty_only_line))
        else:
            out.append(label_loy[:w])
            wrap_loy = max(16, w)
            for seg in textwrap.wrap(loyalty_only_line, width=wrap_loy, break_long_words=True, replace_whitespace=False):
                out.append(seg[:w])
    out.append(two_col('Total Points', pts_display))
    out.append(two_col('Served By : ' + (user or '-'), ''))
    out.append('')
    out.append(('%-12s %-11s %-11s %5s' % ('Receipt', 'Date', 'Time', 'POS'))[:w])
    out.append(('%-12s %-11s %-11s %5s' % (str(receiptno)[:12], billdate[:11], billtime[:11], str(countercode)[:5]))[:w])
    out.append('')
    out.append(rule('-'))
    out.append('')
    out.append(center('شكرا لك على الشراء'))
    out.append(center('Thank you for shopping'))
    if footer_cfg.get('message', True):
        msg_clean = (message or '').strip()
        if msg_clean:
            generic = msg_clean.lower().rstrip('.!') in ('thank you', 'thanks', 'thankyou')
            if not generic:
                out.append(center(message))
    if footer_cfg.get('barcode', True):
        out.append('')
        ean13 = _to_ean13(receiptno)
        out.append(_ascii_ean13_line(ean13, w))
        out.append(center(ean13))
    return '\n'.join(out)

def _receipt_output_encoding(design: Optional[Dict[str, Any]]=None) -> str:
    """Encoding for receipt text when sending to printer (utf-8 or cp1256 from design)."""
    d = design if design is not None else load_receipt_design()
    enc = (d.get('output_encoding') or 'utf-8').strip().lower()
    if enc in ('cp1256', 'windows-1256', 'arabic'):
        return 'cp1256'
    return 'utf-8'
_ESC_POS_PREFIX = b'\x1dL\x00\x00\x1ba\x00\x1b3\x00'
_ESC_POS_PER_LINE = b'\x1dL\x00\x00\x1ba\x00'

def _resolve_branch_logo_abs_path(logo_rel: str) -> str:
    """Resolve LOCATIONMASTER LOGO_PATH (relative under static/) to an absolute file path."""
    rel = (logo_rel or '').strip().lstrip('/')
    if not rel:
        return ''
    candidate = (_PROJECT_ROOT / 'static' / rel).resolve()
    if candidate.is_file():
        return str(candidate)
    return ''

def _branch_logo_abs_from_receipt(receipt: Dict[str, Any]) -> str:
    loc = receipt.get('location_details') or {}
    logo_rel = str(loc.get('logo_path') or '').strip()
    if not logo_rel:
        return ''
    return _resolve_branch_logo_abs_path(logo_rel)

def _escpos_raster_logo_bytes(abs_path: str, max_width_px: int = 384) -> bytes:
    """Convert branch logo image to ESC/POS GS v 0 raster bytes for thermal printers."""
    try:
        import fitz
    except ImportError:
        return b''
    try:
        doc = fitz.open(abs_path)
        if doc.page_count < 1:
            return b''
        page = doc[0]
        rect = page.rect
        if rect.width <= 0 or rect.height <= 0:
            return b''
        scale = min(1.0, float(max_width_px) / float(rect.width))
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        w, h = pix.width, pix.height
        if w <= 0 or h <= 0:
            return b''
        width_bytes = (w + 7) // 8
        samples = pix.samples
        ncomp = max(1, int(len(samples) / (w * h))) if w * h else 3
        rows: List[bytes] = []
        for y in range(h):
            row_bytes = bytearray(width_bytes)
            for x in range(w):
                i = (y * w + x) * ncomp
                if ncomp >= 3:
                    lum = (samples[i] + samples[i + 1] + samples[i + 2]) // 3
                else:
                    lum = samples[i]
                if lum < 128:
                    row_bytes[x // 8] |= 1 << (7 - (x % 8))
            rows.append(bytes(row_bytes))
        data = b''.join(rows)
        xL = width_bytes & 255
        xH = (width_bytes >> 8) & 255
        yL = h & 255
        yH = (h >> 8) & 255
        return b'\x1d\x76\x30\x00' + bytes([xL, xH, yL, yH]) + data + b'\n'
    except Exception:
        return b''

def _prepend_escpos_branch_logo(payload: bytes, receipt: Dict[str, Any], design: Optional[Dict[str, Any]]=None) -> bytes:
    """Prepend centered branch logo raster when enabled in receipt design."""
    d = design if design is not None else load_receipt_design()
    hdr = d.get('header') or {}
    if hdr.get('logo') is False:
        return payload
    logo_abs = _branch_logo_abs_from_receipt(receipt)
    if not logo_abs:
        return payload
    paper_mm = int(d.get('paper_width_mm') or 80)
    max_w = max(200, int(paper_mm * 384 / 80))
    logo_bytes = _escpos_raster_logo_bytes(logo_abs, max_width_px=max_w)
    if not logo_bytes:
        return payload
    return b'\x1b@' + b'\x1ba\x01' + logo_bytes + b'\x1ba\x00' + b'\n' + payload

def _list_printers() -> list:
    """Return list of installed printer names (Windows). Empty on error or non-Windows."""
    if sys.platform != 'win32':
        return []
    try:
        import win32print
        printers = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)
        return [p[2] for p in printers]
    except Exception:
        return []

def _get_receipt_printer_name(design: Optional[Dict[str, Any]]=None) -> str:
    """Printer to use for receipts: design.receipt_printer_name if set, else Windows default."""
    d = design if design is not None else load_receipt_design()
    name = (d.get('receipt_printer_name') or '').strip()
    if name:
        return name
    if sys.platform == 'win32':
        try:
            import win32print
            return win32print.GetDefaultPrinter() or ''
        except Exception:
            pass
    return ''

def _get_default_printer_paper_size() -> Optional[Tuple[str, int, int]]:
    """Get default printer name and paper size (width_mm, length_mm). Returns (printer_name, width_mm, length_mm) or None.
    On Windows uses win32print GetPrinter(2) and DEVMODE PaperWidth/PaperLength (in 0.1mm)."""
    if sys.platform != 'win32':
        return None
    try:
        import win32print
        printer_name = win32print.GetDefaultPrinter()
        h = win32print.OpenPrinter(printer_name)
        try:
            info = win32print.GetPrinter(h, 2)
            devmode = info.get('pDevMode')
            if devmode is None:
                return (printer_name, 0, 0)
            w = getattr(devmode, 'PaperWidth', 0) or 0
            l = getattr(devmode, 'PaperLength', 0) or 0
            width_mm = int(w) // 10 if w else 0
            length_mm = int(l) // 10 if l else 0
            return (printer_name, width_mm, length_mm)
        finally:
            win32print.ClosePrinter(h)
    except Exception:
        return None

def _print_receipt_via_tcp(payload: bytes, ip: str, port: int=9100, timeout: float=10.0) -> Tuple[bool, Optional[str]]:
    """Send raw receipt bytes to printer at IP:port (e.g. 9100 JetDirect). Bypasses Windows driver."""
    ip = (ip or '').strip()
    if not ip:
        return (False, 'No printer IP')
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((ip, port))
        try:
            sock.sendall(payload)
            return (True, None)
        finally:
            sock.close()
    except socket.timeout:
        return (False, 'Printer at %s:%s timed out' % (ip, port))
    except Exception as e:
        return (False, str(e))

def _win32_send_raw_job(printer_name: str, data: bytes, datatype: Optional[str]) -> None:
    """Submit one print job via win32print (RAW or driver default when datatype is None)."""
    import win32print
    h = win32print.OpenPrinter(printer_name)
    try:
        doc_info = ('Receipt', None, datatype) if datatype else ('Receipt', None, None)
        win32print.StartDocPrinter(h, 1, doc_info)
        try:
            win32print.StartPagePrinter(h)
            win32print.WritePrinter(h, data)
            win32print.EndPagePrinter(h)
        finally:
            win32print.EndDocPrinter(h)
    finally:
        win32print.ClosePrinter(h)

def _print_receipt_to_default_printer(receipt: Dict[str, Any], design: Optional[Dict[str, Any]]=None, *, include_copy_banner: bool=False) -> Tuple[bool, Optional[str]]:
    """Send receipt to printer. Uses TCP to IP:9100 if receipt_printer_ip set (no driver margins), else Windows printer."""
    try:
        text_preview = _receipt_to_plain_text(receipt, design, for_escpos=False, include_copy_banner=include_copy_banner).lstrip('\n\r')
        enc = _receipt_output_encoding(design)
        d = design if design is not None else load_receipt_design()
        try:
            payload_plain = text_preview.encode(enc, errors='replace')
        except LookupError:
            payload_plain = text_preview.encode('utf-8', errors='replace')
        payload = payload_plain
        if d.get('escpos_left_align', True):
            text_esc = _receipt_to_plain_text(receipt, design, for_escpos=True, include_copy_banner=include_copy_banner).lstrip('\n\r')
            try:
                payload = text_esc.encode(enc, errors='replace')
            except LookupError:
                payload = text_esc.encode('utf-8', errors='replace')
            payload = _ESC_POS_PREFIX + payload
            payload = payload.replace(b'\n', b'\n' + _ESC_POS_PER_LINE)
        payload = _prepend_escpos_branch_logo(payload, receipt, d)
        printer_ip = (d.get('receipt_printer_ip') or '').strip()
        if printer_ip:
            ok, err = _print_receipt_via_tcp(payload, printer_ip)
            if ok:
                return (True, None)
        if sys.platform == 'win32':
            printer_name = _get_receipt_printer_name(d)
            if not printer_name:
                return (False, 'No receipt printer selected and no Windows default printer')
            win32_attempts: list[tuple[bytes, Optional[str]]] = [(payload, 'RAW'), (payload_plain, 'RAW'), (payload_plain, None)]
            seen: set[tuple[bytes, Optional[str]]] = set()
            for job_bytes, dtype in win32_attempts:
                key = (job_bytes, dtype)
                if key in seen:
                    continue
                seen.add(key)
                try:
                    _win32_send_raw_job(printer_name, job_bytes, dtype)
                    return (True, None)
                except Exception:
                    continue
            fd, path = tempfile.mkstemp(suffix='.txt', prefix='receipt_', text=False)
            try:
                if enc == 'cp1256':
                    file_body = text_preview.encode('cp1256', errors='replace')
                    ps_encoding = 'Default'
                else:
                    file_body = codecs.BOM_UTF8 + text_preview.encode('utf-8', errors='replace')
                    ps_encoding = 'UTF8'
                os.write(fd, file_body)
                os.close(fd)
                fd = None
                cmd = 'Get-Content -LiteralPath ' + repr(path) + ' -Raw -Encoding ' + ps_encoding + ' | Out-Printer'
                if printer_name:
                    cmd += ' -Name ' + repr(printer_name)
                subprocess.run(['powershell', '-NoProfile', '-Command', cmd], check=True, timeout=30, capture_output=True)
                return (True, None)
            finally:
                if fd is not None:
                    try:
                        os.close(fd)
                    except Exception:
                        pass
                try:
                    os.unlink(path)
                except Exception:
                    pass
        else:
            fd, path = tempfile.mkstemp(suffix='.txt', prefix='receipt_')
            try:
                os.write(fd, payload)
                os.close(fd)
                fd = None
                subprocess.run(['lp', path], check=True, timeout=30, capture_output=True)
                return (True, None)
            finally:
                if fd is not None:
                    try:
                        os.close(fd)
                    except Exception:
                        pass
                try:
                    os.unlink(path)
                except Exception:
                    pass
    except subprocess.CalledProcessError as e:
        err_parts = []
        if e.stderr:
            err_parts.append(e.stderr.decode('utf-8', errors='replace').strip())
        if e.stdout:
            err_parts.append(e.stdout.decode('utf-8', errors='replace').strip())
        err = ' | '.join((x for x in err_parts if x)) or str(e)
        return (False, err)
    except Exception as e:
        return (False, str(e))
    return (False, 'Unsupported platform')

def _pos_counter_location_candidates(location_code: Any, location_code_int: int) -> List[int]:
    seen: List[int] = []
    for raw in (location_code, location_code_int):
        try:
            if raw is not None:
                v = int(raw)
                if v not in seen:
                    seen.append(v)
        except (TypeError, ValueError):
            continue
    try:
        for row in get_base_locations_list() or []:
            try:
                v = int(row.get('code'))
                if v not in seen:
                    seen.append(v)
            except (TypeError, ValueError):
                continue
    except Exception:
        pass
    return seen


def _session_pos_counter_code() -> Optional[int]:
    """Session counter from Counter Setup (positive ``countercode`` only)."""
    raw = session.get('countercode')
    if raw is None:
        return None
    try:
        ci = int(raw)
        return ci if ci > 0 else None
    except (TypeError, ValueError):
        return None


def _countercode_query_optional() -> Optional[int]:
    cq = request.args.get('countercode')
    if cq is None or str(cq).strip() == '':
        return None
    try:
        return int(cq)
    except (TypeError, ValueError):
        return None


def _pos_resolve_hostname_candidates_from_payload(payload: Dict[str, Any]) -> List[str]:
    """Build ordered unique hostname candidates (QZ / browser bar may send several)."""
    from db import _norm_counter_hostname

    out: List[str] = []
    seen_norm: set[str] = set()

    def _push(raw: Any) -> None:
        s = str(raw or '').strip()
        if not s:
            return
        key = _norm_counter_hostname(s)
        if not key or key in seen_norm:
            return
        seen_norm.add(key)
        out.append(s)

    hn = (payload.get('hostname') or '').strip()
    if hn:
        _push(hn)
    raw_list = payload.get('hostnames')
    if isinstance(raw_list, list):
        for x in raw_list:
            _push(x)
    return out


def _pos_counter_allowed_for_session(countercode: Any, location_code: Optional[int], location_code_int: int) -> Tuple[bool, str]:
    """True if ``countercode`` exists on ``COUNTER`` for an allowed branch (tenant DB)."""
    try:
        cci = int(countercode)
    except (TypeError, ValueError):
        return (False, '')
    if cci <= 0:
        return (False, '')
    candidates = _pos_counter_location_candidates(location_code, location_code_int)
    for lc in candidates:
        try:
            rows = list_pos_counters_for_location(int(lc), db_key=None) or []
        except Exception:
            continue
        for row in rows:
            try:
                if int(row.get('countercode')) == cci:
                    return (True, str(row.get('countername') or '').strip())
            except (TypeError, ValueError):
                continue
    return (False, '')


@bp.route('/pos-billing/resolve-counter-by-hostname', methods=['POST'])
def pos_resolve_counter_by_hostname():
    """Resolve POS register from ``COUNTER.SYSTEMNAME`` vs PC hostname(s) (same normalization as Counter Operations)."""
    _t0 = time.perf_counter()
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    payload = request.get_json(silent=True) or {}
    names = _pos_resolve_hostname_candidates_from_payload(payload)
    if not names:
        return jsonify({'success': False, 'matched': False, 'error': 'hostname or hostnames required'}, 400)
    location_code_int = _resolve_location_code()
    location_info = get_location_info_by_dbkey(user_dbkey or 'HO')
    location_code = location_info.get('locationcode') if location_info else location_code_int
    candidates = _pos_counter_location_candidates(location_code, location_code_int)
    last_err = 'No counter matches this PC name in COUNTER.SYSTEMNAME for allowed branches'
    for hn in names:
        row = find_counter_by_systemname(hn, candidates)
        if row:
            _pos_timing_log('resolve_counter', _t0, matched=1, tried=len(names))
            try:
                cc_i = int(row['countercode'])
                lc_i = int(row.get('locationcode') or location_code_int or 0)
            except (TypeError, ValueError):
                cc_i = 0
                lc_i = 0
            wh_ctx: Dict[str, Any] = {}
            if cc_i > 0 and lc_i > 0:
                wh_ctx = resolve_pos_counter_warehouse(cc_i, lc_i)
            return jsonify({
                'success': True,
                'matched': True,
                'countercode': row['countercode'],
                'countername': row['countername'],
                'locationcode': row.get('locationcode'),
                'matched_hostname': hn,
                'warehouse_code': wh_ctx.get('warehouse_code') or '',
                'warehouse_name': wh_ctx.get('warehouse_name') or '',
            })
    _pos_timing_log('resolve_counter', _t0, matched=0, tried=len(names))
    return jsonify({'success': False, 'matched': False, 'error': last_err, 'tried': names}, 404)


@bp.route('/pos-billing/bind-session-counter', methods=['POST'])
def pos_bind_session_counter():
    """Persist resolved counter to Flask session (after COUNTER table match)."""
    _t0 = time.perf_counter()
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    payload = request.get_json(silent=True) or {}
    cc_raw = payload.get('countercode')
    cn_payload = str(payload.get('countername') or '').strip()
    location_code_int = _resolve_location_code()
    location_info = get_location_info_by_dbkey(user_dbkey or 'HO')
    location_code = location_info.get('locationcode') if location_info else location_code_int
    ok, cn_db = _pos_counter_allowed_for_session(cc_raw, location_code, location_code_int)
    if not ok:
        return jsonify({'success': False, 'error': 'Counter is not valid for this branch.'}, 400)
    try:
        cci = int(cc_raw)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Invalid counter code.'}, 400)
    session['countercode'] = cci
    session['countername'] = (cn_db or cn_payload).strip()
    _sync_pos_counter_warehouse_session(cci, location_code_int, session['countername'])
    wh_ctx = _pos_session_warehouse_context()
    _pos_timing_log('bind_session_counter', _t0, countercode=cci)
    return json_response_rotate_pos({
        'success': True,
        'countercode': cci,
        'countername': session['countername'],
        'warehouse_code': wh_ctx.get('warehouse_code') or '',
        'warehouse_name': wh_ctx.get('warehouse_name') or '',
    })


@bp.route('/pos-billing/refresh-save-nonce', methods=['GET', 'POST'])
def pos_refresh_save_nonce():
    """Issue a fresh POS save token (stale tab / multi-terminal recovery)."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    return json_response_rotate_pos({'success': True})


@bp.route('/pos-billing/terminal-lock/acquire', methods=['POST'])
def pos_terminal_lock_acquire():
    """One active POS Billing tab per PC (hostname). Other tabs/windows on same machine are blocked."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    payload = request.get_json(silent=True) or {}
    tab_id = str(payload.get('tab_id') or '').strip()
    if not tab_id or len(tab_id) > 80:
        return jsonify({'success': False, 'error': 'tab_id required'}, 400)
    names = _pos_resolve_hostname_candidates_from_payload(payload)
    if not names:
        return jsonify({'success': True, 'granted': True, 'mode': 'local_only'})
    from db import _norm_counter_hostname

    def _hostname_not_ipv4(raw: str) -> bool:
        s = str(raw or '').strip()
        if not s:
            return False
        parts = s.split('.')
        if len(parts) != 4:
            return True
        try:
            return not all(0 <= int(p) <= 255 for p in parts)
        except ValueError:
            return True

    hostname_norm = ''
    for raw_name in names:
        if not _hostname_not_ipv4(raw_name):
            continue
        hostname_norm = _norm_counter_hostname(raw_name)
        if hostname_norm:
            break
    if not hostname_norm:
        hostname_norm = _norm_counter_hostname(names[0])
    if not hostname_norm:
        return jsonify({'success': True, 'granted': True, 'mode': 'local_only'})
    tenant = str(session.get('tenant_id') or session.get('user') or 'default')
    force = bool(payload.get('force'))
    ok, lock_key, holder = _pos_terminal_tab_lock_try_acquire(
        tenant, hostname_norm, tab_id, session.get('user'), force=force,
    )
    if not ok:
        return jsonify({
            'success': True,
            'granted': False,
            'lock_key': lock_key,
            'hostname': hostname_norm,
            'holder_user': (holder or {}).get('user') or '',
        })
    return jsonify({
        'success': True,
        'granted': True,
        'lock_key': lock_key,
        'hostname': hostname_norm,
    })


@bp.route('/pos-billing/terminal-lock/heartbeat', methods=['POST'])
def pos_terminal_lock_heartbeat():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    payload = request.get_json(silent=True) or {}
    lock_key = str(payload.get('lock_key') or '').strip()
    tab_id = str(payload.get('tab_id') or '').strip()
    if not lock_key or not tab_id:
        return jsonify({'success': False, 'error': 'lock_key and tab_id required'}, 400)
    if _pos_terminal_tab_lock_touch(lock_key, tab_id):
        return jsonify({'success': True, 'granted': True})
    return jsonify({'success': True, 'granted': False, 'error': 'Lock lost to another POS window.'})


@bp.route('/pos-billing/terminal-lock/release', methods=['POST'])
def pos_terminal_lock_release():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    payload = request.get_json(silent=True) or {}
    lock_key = str(payload.get('lock_key') or '').strip()
    tab_id = str(payload.get('tab_id') or '').strip()
    if lock_key and tab_id:
        _pos_terminal_tab_lock_release(lock_key, tab_id)
    return jsonify({'success': True})


def _counter_ops_pos_date_iso(row: Dict[str, Any]) -> Optional[str]:
    if not row:
        return None
    r = {str(k).lower(): v for k, v in row.items()} if hasattr(row, 'items') else {}
    pd = r.get('posdate')
    if pd is None:
        return None
    try:
        if hasattr(pd, 'strftime'):
            return pd.strftime('%Y-%m-%d')
    except Exception:
        pass
    s = str(pd).strip()
    return s[:10] if len(s) >= 10 else None


def _apply_open_shift_posdate_to_pos_header_billdate(header: Dict[str, Any], location_code: int) -> None:
    """Set ``header['billdate']`` and ``header['shiftcode']`` from open ``COUNTEROPERATIONS`` for this counter.

    POS business date is the shift trading date (often retained across midnight), not necessarily server/local calendar.
    Mutates ``header`` in place when an open row exists.
    """
    try:
        cc = int(header.get('countercode') or 0)
    except (TypeError, ValueError):
        cc = 0
    if cc <= 0:
        return
    try:
        loc = int(location_code)
    except (TypeError, ValueError):
        return
    if loc <= 0:
        return
    row = find_open_counter_operation(loc, cc, db_key=None)
    if not row:
        return
    iso = _counter_ops_pos_date_iso(row)
    if iso:
        header['billdate'] = iso
    if _shift_code_from_header(header) <= 0:
        r = {str(k).lower(): v for k, v in row.items()} if isinstance(row, dict) else {}
        sc_raw = r.get('shiftcode')
        try:
            if sc_raw is not None:
                header['shiftcode'] = int(sc_raw)
        except (TypeError, ValueError):
            pass


def _pos_open_shift_status_payload(
    location_code_int: int,
    counter_code: Optional[int],
    *,
    user_dbkey: Optional[str] = None,
) -> Dict[str, Any]:
    """Shared open-shift JSON payload for POS billing UI (also embedded in last-in-progress-bill)."""
    cq = counter_code
    if cq is None or cq <= 0:
        return {
            'success': True,
            'open': False,
            'pos_date': None,
            'shiftcode': None,
            'countercode': None,
            'countername': '',
        }
    counter_name = (
        get_counter_name_by_code(cq, db_key=user_dbkey or 'HO', location_code=location_code_int) or ''
    ).strip()
    row = find_open_counter_operation(location_code_int, cq, db_key=None)
    if not row:
        return {
            'success': True,
            'open': False,
            'pos_date': None,
            'shiftcode': None,
            'countercode': cq,
            'countername': counter_name,
        }
    r = {str(k).lower(): v for k, v in row.items()} if hasattr(row, 'items') else {}
    sc_raw = r.get('shiftcode')
    try:
        shift_i = int(sc_raw) if sc_raw is not None else None
    except (TypeError, ValueError):
        shift_i = None
    return {
        'success': True,
        'open': True,
        'pos_date': _counter_ops_pos_date_iso(row),
        'shiftcode': shift_i,
        'countercode': cq,
        'countername': counter_name,
    }


@bp.route('/pos-billing/open-shift-status', methods=['GET'])
def pos_open_shift_status():
    """Whether this counter has an open COUNTEROPERATIONS row (OPENFLAG O/Y); POS bill date should match POSDATE."""
    _t0 = time.perf_counter()
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    location_code_int = _resolve_location_code()
    cq = _countercode_query_optional()
    if cq is None:
        cq = _session_pos_counter_code()
    payload = _pos_open_shift_status_payload(location_code_int, cq, user_dbkey=user_dbkey)
    open_flag = 1 if payload.get('open') else 0
    _pos_timing_log('open_shift_status', _t0, countercode=cq or 0, open=open_flag)
    return jsonify(payload)


@bp.route('/pos-billing')
def pos_billing_page():
    _t0 = time.perf_counter()
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    else:
        loc = session.get('location_code')
        if loc:
            _apply_active_connection(loc)
        elif session.get('user') == 'admin':
            _apply_active_connection('HO')
    location_code_int = _resolve_location_code()
    bill_date_value = datetime.now().strftime('%Y-%m-%d')
    location_info = get_location_info_by_dbkey(user_dbkey or 'HO')
    location_code = location_info.get('locationcode') if location_info else location_code_int
    location_name = (location_info.get('locationname') or '').strip() if location_info else ''
    username = (session.get('user') or '').strip()
    counter_code = _session_pos_counter_code()
    counter_name = (session.get('countername') or '').strip()
    if counter_code and not counter_name:
        counter_name = (
            get_counter_name_by_code(
                counter_code,
                db_key=user_dbkey or 'HO',
                location_code=location_code_int,
            )
            or ''
        ).strip()
        if counter_name:
            session['countername'] = counter_name
    if counter_code:
        try:
            _sync_pos_counter_warehouse_session(int(counter_code), location_code_int, counter_name or '')
        except (TypeError, ValueError):
            pass
    pos_needs_counter_prompt = counter_code is None
    wh_ctx = _pos_session_warehouse_context()
    resp = render_template(
        'pos_billing/pos_billing.html',
        customers=[],
        bill_date=bill_date_value,
        counter_code=counter_code,
        counter_name=counter_name,
        pos_warehouse_code=wh_ctx.get('warehouse_code') or '',
        pos_warehouse_name=wh_ctx.get('warehouse_name') or '',
        username=username,
        location_code=location_code,
        location_name=location_name,
        pos_needs_counter_prompt=pos_needs_counter_prompt,
        pos_counter_setup_url=url_for('pos_billing.pos_counter_setup_list'),
        pos_counter_operations_url=url_for('pos_billing.pos_counter_operations_page'),
        openai_configured=bool((os.environ.get('OPENAI_API_KEY') or '').strip()),
        checkout_tenders_url=url_for('pos_billing.pos_checkout_tenders_api'),
    )
    _pos_timing_log('page_render', _t0, countercode=counter_code or 0, location=location_code)
    return resp


def _pos_shop_session_context() -> Dict[str, Any]:
    """Shared session/counter/warehouse context for POS Shop page."""
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    else:
        loc = session.get('location_code')
        if loc:
            _apply_active_connection(loc)
        elif session.get('user') == 'admin':
            _apply_active_connection('HO')
    location_code_int = _resolve_location_code()
    location_info = get_location_info_by_dbkey(user_dbkey or 'HO')
    location_code = location_info.get('locationcode') if location_info else location_code_int
    location_name = (location_info.get('locationname') or '').strip() if location_info else ''
    username = (session.get('user') or '').strip()
    counter_code = _session_pos_counter_code()
    counter_name = (session.get('countername') or '').strip()
    if counter_code and not counter_name:
        counter_name = (
            get_counter_name_by_code(
                counter_code,
                db_key=user_dbkey or 'HO',
                location_code=location_code_int,
            )
            or ''
        ).strip()
        if counter_name:
            session['countername'] = counter_name
    if counter_code:
        try:
            _sync_pos_counter_warehouse_session(int(counter_code), location_code_int, counter_name or '')
        except (TypeError, ValueError):
            pass
    wh_ctx = _pos_session_warehouse_context()
    return {
        'bill_date': datetime.now().strftime('%Y-%m-%d'),
        'counter_code': counter_code,
        'counter_name': counter_name,
        'pos_warehouse_code': wh_ctx.get('warehouse_code') or '',
        'pos_warehouse_name': wh_ctx.get('warehouse_name') or '',
        'username': username,
        'location_code': location_code,
        'location_name': location_name,
        'pos_needs_counter_prompt': counter_code is None,
    }


@bp.route('/pos-billing/shop')
def pos_shop_page():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    ctx = _pos_shop_session_context()
    return render_template(
        'pos_billing/pos_shop.html',
        bill_date=ctx['bill_date'],
        counter_code=ctx['counter_code'],
        counter_name=ctx['counter_name'],
        pos_warehouse_code=ctx['pos_warehouse_code'],
        pos_warehouse_name=ctx['pos_warehouse_name'],
        username=ctx['username'],
        location_code=ctx['location_code'],
        location_name=ctx['location_name'],
        pos_needs_counter_prompt=ctx['pos_needs_counter_prompt'],
        pos_billing_url=url_for('pos_billing.pos_billing_page'),
        pos_counter_setup_url=url_for('pos_billing.pos_counter_setup_list'),
        pos_counter_operations_url=url_for('pos_billing.pos_counter_operations_page'),
        pos_sales_return_url=url_for('sales.sales_return'),
        products_url=url_for('pos_billing.pos_products'),
        categories_url=url_for('pos_billing.pos_shop_categories'),
        barcode_items_url=url_for('pos_billing.pos_barcode_items'),
        customers_picker_url=url_for('pos_billing.pos_customers_picker'),
        checkout_tenders_url=url_for('pos_billing.pos_checkout_tenders_api'),
    )


@bp.route('/pos-billing/checkout-tenders', methods=['GET'])
def pos_checkout_tenders_api():
    """Active POS payment tender types from ``POS_TENDER_TYPE`` (excludes CREDIT — billing customer)."""
    _t0 = time.perf_counter()
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    try:
        tenders = list_pos_payment_tender_types()
        _pos_timing_log('checkout_tenders', _t0, rows=len(tenders or []))
        return jsonify({'success': True, 'tenders': tenders})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}, 500)


@bp.route('/pos-billing/customers-picker', methods=['GET'])
def pos_customers_picker():
    """JSON customer rows for POS picker (capped)."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not logged in'}, 401)
    q = (request.args.get('q') or '').strip()
    try:
        lim = int(request.args.get('limit', 300))
    except (TypeError, ValueError):
        lim = 300
    lim = max(1, min(lim, 500))
    try:
        rows = get_customers_master_list(for_picker=True, picker_search=q, picker_limit=lim)
        return jsonify({'success': True, 'customers': rows})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}, 500)

@bp.route('/pos-billing/loyalty-customers-picker', methods=['GET'])
def pos_loyalty_customers_picker():
    """JSON loyalty customer rows from CUSTOMERLOYALTY for POS modal (capped)."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not logged in'}, 401)
    q = (request.args.get('q') or '').strip()
    try:
        lim = int(request.args.get('limit', 300))
    except (TypeError, ValueError):
        lim = 300
    lim = max(1, min(lim, 500))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    location_code_int = _resolve_location_code()
    try:
        rows = get_customer_loyalty_for_picker(location_code_int, picker_search=q, picker_limit=lim)
        return jsonify({'success': True, 'customers': rows})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}, 500)

@bp.route('/pos-billing/loyalty-customer-next-code', methods=['GET'])
def pos_loyalty_customer_next_code():
    """Suggested next CUSTOMERCODE on CUSTOMERLOYALTY for current location."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not logged in'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    location_code_int = _resolve_location_code()
    n = peek_next_customer_loyalty_code(location_code_int)
    if n is None:
        return jsonify({'success': False, 'error': 'CUSTOMERLOYALTY not available for this database.'}, 400)
    return jsonify({'success': True, 'next_code': n})

@bp.route('/pos-billing/loyalty-customer-create', methods=['POST'])
def pos_loyalty_customer_create():
    """Create one CUSTOMERLOYALTY row from POS (JSON body)."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    location_code_int = _resolve_location_code()
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({'success': False, 'error': 'Invalid JSON'}, 400)
    ok, err = insert_customer_loyalty_row(location_code_int, payload)
    if not ok:
        return jsonify({'success': False, 'error': err or 'Save failed'}, 400)
    try:
        cc = int(payload.get('customercode') or payload.get('customer_code') or 0)
    except (TypeError, ValueError):
        cc = 0
    name_raw = (payload.get('customername') or payload.get('name') or '').strip()
    name_upper = name_raw.upper()[:40] if len(name_raw) > 40 else name_raw.upper()
    try:
        tp_echo = round(
            float(
                payload.get('totalpoints')
                if payload.get('totalpoints') is not None
                else (payload.get('points') or 0)
            ),
            2,
        )
    except (TypeError, ValueError):
        tp_echo = 0.0
    crd_raw = payload.get('cardno')
    cardno_echo = None
    if crd_raw is not None and str(crd_raw).strip() != '':
        try:
            cardno_echo = int(crd_raw)
        except (TypeError, ValueError):
            cardno_echo = None
    return jsonify({'success': True, 'customercode': cc, 'customername': name_upper, 'totalpoints': tp_echo, 'cardno': cardno_echo})

def _pos_counter_setup_resolve_location(locations: Any, location_code: Any, *, strict: bool=False) -> Tuple[str, Any]:
    """Return ``(display_label, canonical_location_code)`` for header display.

    When ``strict`` is True (edit existing row), do not fall back to the first location in the list
    if the row's code is missing from ``locations`` — keeps the row's branch code visible.
    """
    locked_location_code = location_code
    locked_location_label = str(location_code)
    matched = False
    for loc in locations or []:
        code = loc.get('code')
        name = (loc.get('name') or '').strip()
        if code == location_code or str(code) == str(location_code):
            locked_location_code = code
            locked_location_label = f'{code} — {name}' if name else str(code)
            matched = True
            break
    if not matched and locations and not strict:
        loc0 = locations[0]
        locked_location_code = loc0.get('code')
        nm = (loc0.get('name') or '').strip()
        locked_location_label = f'{locked_location_code} — {nm}' if nm else str(locked_location_code)
    return locked_location_label, locked_location_code


@bp.route('/pos-billing/tender-types')
def pos_tender_types_page():
    """Map POS paymode codes (CASH, CARD, VISA, …) to GL accounts — used by settlement when bills have POS_BILL_PAYMODE detail."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    api_bootstrap_url = url_for('pos_billing.pos_tender_types_api_bootstrap')
    api_save_url = url_for('pos_billing.pos_tender_types_api_save')
    api_delete_url = url_for('pos_billing.pos_tender_types_api_delete')
    return render_template(
        'pos_billing/pos_tender_types.html',
        api_bootstrap_url=api_bootstrap_url,
        api_save_url=api_save_url,
        api_delete_url=api_delete_url,
    )


@bp.route('/pos-billing/tender-types/api/bootstrap', methods=['GET'])
def pos_tender_types_api_bootstrap():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    try:
        tenders = list_pos_tender_types(active_only=False)
        coa = get_all_chart_of_accounts() or []
        accounts_out: List[Dict[str, Any]] = []
        for r in coa:
            if not isinstance(r, dict):
                continue
            if str(r.get('status') or 'ACTIVE').strip().upper() != 'ACTIVE':
                continue
            code = str(r.get('code') or '').strip()
            if not code:
                continue
            accounts_out.append({'code': code[:20], 'name': str(r.get('name') or '').strip()[:200]})
        accounts_out.sort(key=lambda x: str(x.get('code') or ''))
        return jsonify({'success': True, 'tenders': tenders, 'accounts': accounts_out})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}, 500)


@bp.route('/pos-billing/tender-types/api/save', methods=['POST'])
def pos_tender_types_api_save():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    payload = request.get_json(silent=True) or {}
    try:
        sort_o = int(payload.get('sort_order') or 0)
    except (TypeError, ValueError):
        sort_o = 0
    ok, err = upsert_pos_tender_type_row(
        tender_code=str(payload.get('tender_code') or ''),
        tender_name=str(payload.get('tender_name') or ''),
        category=str(payload.get('category') or ''),
        gl_account_code=str(payload.get('gl_account_code') or ''),
        status=str(payload.get('status') or 'ACTIVE'),
        sort_order=sort_o,
        icon_key=str(payload.get('icon_key') or ''),
    )
    if not ok:
        return jsonify({'success': False, 'error': err or 'Save failed'}, 400)
    try:
        tenders = list_pos_tender_types(active_only=False)
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}, 500)
    return jsonify({'success': True, 'tenders': tenders})


@bp.route('/pos-billing/tender-types/api/delete', methods=['POST'])
def pos_tender_types_api_delete():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    payload = request.get_json(silent=True) or {}
    ok, err = delete_pos_tender_type_row(str(payload.get('tender_code') or ''))
    if not ok:
        return jsonify({'success': False, 'error': err or 'Delete failed'}, 400)
    try:
        tenders = list_pos_tender_types(active_only=False)
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}, 500)
    return jsonify({'success': True, 'tenders': tenders})


def _pos_active_coa_options() -> List[Dict[str, Any]]:
    coa = get_all_chart_of_accounts() or []
    accounts_out: List[Dict[str, Any]] = []
    for r in coa:
        if not isinstance(r, dict):
            continue
        if str(r.get('status') or 'ACTIVE').strip().upper() != 'ACTIVE':
            continue
        code = str(r.get('code') or '').strip()
        if not code:
            continue
        accounts_out.append({'code': code[:20], 'name': str(r.get('name') or '').strip()[:200]})
    accounts_out.sort(key=lambda x: str(x.get('code') or ''))
    return accounts_out


@bp.route('/pos-billing/accounts-configuration')
def pos_accounts_configuration_page():
    """Configure non-tender POS settlement GL accounts."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    return render_template(
        'pos_billing/pos_accounts_configuration.html',
        api_bootstrap_url=url_for('pos_billing.pos_accounts_configuration_api_bootstrap'),
        api_save_url=url_for('pos_billing.pos_accounts_configuration_api_save'),
        settlement_url=url_for('pos_billing.pos_settlement_posting_page'),
        tender_types_url=url_for('pos_billing.pos_tender_types_page'),
    )


@bp.route('/pos-billing/accounts-configuration/api/bootstrap', methods=['GET'])
def pos_accounts_configuration_api_bootstrap():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    try:
        cfg = get_pos_settlement_account_config()
        accounts = []
        for key in ('EXPENSE', 'SHORT', 'EXCESS', 'SALES_REVENUE', 'TAX'):
            row = cfg.get(key) or {}
            accounts.append(
                {
                    'config_key': key,
                    'label': row.get('label') or key.replace('_', ' ').title(),
                    'account_code': row.get('account_code') or '',
                    'normal_side': row.get('normal_side') or ('Cr' if key in ('SALES_REVENUE', 'TAX', 'EXCESS') else 'Dr'),
                }
            )
        return jsonify({'success': True, 'accounts': accounts, 'coa': _pos_active_coa_options()})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}, 500)


@bp.route('/pos-billing/accounts-configuration/api/save', methods=['POST'])
def pos_accounts_configuration_api_save():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    payload = request.get_json(silent=True) or {}
    ok, err = upsert_pos_settlement_account_config(payload, updated_by=str(session.get('user') or ''))
    if not ok:
        return jsonify({'success': False, 'error': err or 'Save failed'}, 400)
    try:
        cfg = get_pos_settlement_account_config()
        return jsonify({'success': True, 'accounts': list(cfg.values())})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}, 500)


@bp.route('/pos-billing/counter-setup')
def pos_counter_setup_list():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    display_cols, rows = get_system_config_rows()
    columns = _pos_counter_ordered_columns(display_cols)
    return render_template('pos_billing/pos_counter_setup_list.html', columns=columns, rows=rows)

@bp.route('/pos-billing/counter-setup/new', methods=['GET'])
def pos_counter_setup_new():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    try:
        next_code = int(get_next_countercode())
    except (TypeError, ValueError):
        next_code = 1
    locations = get_locations_list()
    default_location = _resolve_location_code()
    if not locations:
        locations = [{'code': default_location, 'name': 'Current session location'}]
    locked_location_label, locked_location_code = _pos_counter_setup_resolve_location(locations, default_location)
    branch_warehouses = list_warehouses_for_location(locked_location_code)
    warehouse_required = bool(is_location_warehouse_enabled(locked_location_code) and branch_warehouses)
    return render_template(
        'pos_billing/pos_counter_setup_new.html',
        next_code=next_code,
        locations=locations,
        default_location=default_location,
        locked_location_code=locked_location_code,
        locked_location_label=locked_location_label,
        branch_warehouses=branch_warehouses,
        warehouse_required=warehouse_required,
    )

@bp.route('/pos-billing/counter-setup/new', methods=['POST'])
def pos_counter_setup_create():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    try:
        locationcode = int((request.form.get('locationcode') or '').strip())
    except (TypeError, ValueError):
        flash('Select a valid location code.', 'error')
        return redirect(url_for('pos_billing.pos_counter_setup_new'))
    countername = (request.form.get('countername') or '').strip()
    onlinesale = 'Y' if (request.form.get('onlinesale') == 'Y') else 'N'
    systemname = (request.form.get('systemname') or '').strip()
    systemip = (request.form.get('systemip') or '').strip()
    store = (request.form.get('store') or '').strip()
    warehouse_id_raw = (request.form.get('warehouse_id') or '').strip()
    warehouse_id: Optional[int] = None
    if warehouse_id_raw:
        try:
            warehouse_id = int(warehouse_id_raw)
        except (TypeError, ValueError):
            flash('Select a valid warehouse.', 'error')
            return redirect(url_for('pos_billing.pos_counter_setup_new'))
    createdby = (session.get('user') or '').strip()
    ok, err, _ = insert_pos_counter_row(locationcode=locationcode, countername=countername, onlinesale=onlinesale, systemname=systemname, systemip=systemip, store=store or None, createdby=createdby, warehouse_id=warehouse_id)
    if ok:
        session.pop('countercode', None)
        session.pop('countername', None)
        for k in ('pos_warehouse_id', 'pos_warehouse_code', 'pos_warehouse_name', 'pos_store', 'pos_bin_loc_key'):
            session.pop(k, None)
        session.modified = True
        flash('Counter saved.', 'success')
        return redirect(url_for('pos_billing.pos_counter_setup_list'))
    flash(err or 'Save failed.', 'error')
    return redirect(url_for('pos_billing.pos_counter_setup_new'))

@bp.route('/pos-billing/counter-setup/edit', methods=['GET'])
def pos_counter_setup_edit():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    rowid = (request.args.get('rowid') or '').strip()
    if not rowid:
        flash('Missing counter row.', 'error')
        return redirect(url_for('pos_billing.pos_counter_setup_list'))
    counter_row = fetch_counter_row_by_rowid(rowid)
    if not counter_row:
        flash('Counter not found.', 'error')
        return redirect(url_for('pos_billing.pos_counter_setup_list'))
    locations = get_locations_list()
    default_location = _resolve_location_code()
    if not locations:
        locations = [{'code': default_location, 'name': 'Current session location'}]
    try:
        locked_location_code = int(counter_row.get('locationcode'))
    except (TypeError, ValueError):
        locked_location_code = default_location
    locked_location_label, locked_location_code = _pos_counter_setup_resolve_location(locations, locked_location_code, strict=True)
    branch_warehouses = list_warehouses_for_location(locked_location_code)
    warehouse_required = bool(is_location_warehouse_enabled(locked_location_code) and branch_warehouses)
    selected_warehouse_id = _pos_counter_setup_selected_warehouse_id(counter_row, locked_location_code)
    return render_template(
        'pos_billing/pos_counter_setup_edit.html',
        counter_row=counter_row,
        rowid=str(counter_row.get('rowid') or rowid).strip(),
        locations=locations,
        locked_location_code=locked_location_code,
        locked_location_label=locked_location_label,
        branch_warehouses=branch_warehouses,
        warehouse_required=warehouse_required,
        selected_warehouse_id=selected_warehouse_id,
    )

@bp.route('/pos-billing/counter-setup/edit', methods=['POST'])
def pos_counter_setup_update():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    rowid = (request.form.get('rowid') or '').strip()
    if not rowid:
        flash('Missing counter row.', 'error')
        return redirect(url_for('pos_billing.pos_counter_setup_list'))
    countername = (request.form.get('countername') or '').strip()
    onlinesale = 'Y' if (request.form.get('onlinesale') == 'Y') else 'N'
    systemname = (request.form.get('systemname') or '').strip()
    systemip = (request.form.get('systemip') or '').strip()
    store = (request.form.get('store') or '').strip()
    warehouse_id_raw = (request.form.get('warehouse_id') or '').strip()
    warehouse_id: Optional[int] = None
    if warehouse_id_raw:
        try:
            warehouse_id = int(warehouse_id_raw)
        except (TypeError, ValueError):
            flash('Select a valid warehouse.', 'error')
            return redirect(url_for('pos_billing.pos_counter_setup_edit', rowid=rowid))
    ok, err = update_pos_counter_row(
        row_id=rowid,
        countername=countername,
        onlinesale=onlinesale,
        systemname=systemname,
        systemip=systemip,
        store=store or None,
        warehouse_id=warehouse_id,
    )
    if ok:
        flash('Counter updated.', 'success')
        session.pop('countercode', None)
        session.pop('countername', None)
        for k in ('pos_warehouse_id', 'pos_warehouse_code', 'pos_warehouse_name', 'pos_store', 'pos_bin_loc_key'):
            session.pop(k, None)
        session.modified = True
        return redirect(url_for('pos_billing.pos_counter_setup_list'))
    flash(err or 'Update failed.', 'error')
    return redirect(url_for('pos_billing.pos_counter_setup_edit', rowid=rowid))

@bp.route('/pos-billing/counter-setup/delete', methods=['POST'])
def pos_counter_setup_delete():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    rowid = (request.form.get('rowid') or '').strip()
    if not rowid:
        flash('Missing counter row.', 'error')
        return redirect(url_for('pos_billing.pos_counter_setup_list'))
    pre = fetch_counter_row_by_rowid(rowid)
    del_cc = None
    try:
        del_cc = int(pre.get('countercode')) if pre else None
    except (TypeError, ValueError):
        del_cc = None
    ok, err = delete_pos_counter_row(row_id=rowid)
    if ok:
        flash('Counter deleted.', 'success')
        try:
            if del_cc is not None and session.get('countercode') is not None:
                if int(session.get('countercode')) == del_cc:
                    session.pop('countercode', None)
                    session.pop('countername', None)
                    session.modified = True
        except (TypeError, ValueError):
            pass
    else:
        flash(err or 'Delete failed.', 'error')
    return redirect(url_for('pos_billing.pos_counter_setup_list'))

@bp.route('/pos-billing/counter-setup/next-code', methods=['GET'])
def pos_counter_setup_next_code():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    try:
        n = int(get_next_countercode())
    except (TypeError, ValueError):
        n = 1
    return jsonify({'success': True, 'next_code': n})


def _norm_co_rows(rows: Any) -> list:
    out = []
    for r in rows or []:
        if isinstance(r, dict):
            out.append({str(k).lower(): v for k, v in r.items()})
        else:
            out.append(r)
    return out


@bp.route('/pos-billing/counter-operations')
def pos_counter_operations_page():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    base_locs = get_base_locations_list()
    if base_locs:
        try:
            location_code_int = int(base_locs[0]['code'])
        except (TypeError, ValueError):
            location_code_int = _resolve_location_code()
        locations = base_locs
    else:
        location_code_int = _resolve_location_code()
        locations = [{'code': location_code_int, 'name': 'Session location (no BASELOCATIONFLAG=Y in LOCATIONMASTER)'}]
    counters = list_pos_counters_for_location(location_code_int, db_key=None)
    initial_counter_code = None
    sess_cc = _session_pos_counter_code()
    if sess_cc is not None:
        for c in counters or []:
            try:
                if int(c.get('countercode')) == int(sess_cc):
                    initial_counter_code = int(sess_cc)
                    break
            except (TypeError, ValueError):
                continue
    history_limit = 500
    history_all = _norm_co_rows(list_counter_operations_recent(location_code_int, limit=history_limit, db_key=None))

    def _row_open(r: Dict[str, Any]) -> bool:
        fl = str((r or {}).get('openflag') or '').strip().upper()
        # O = open, C = closed; legacy Y/N still supported for older rows
        return bool(fl.startswith('O') or fl.startswith('Y'))

    history_opened = [r for r in history_all if _row_open(r)]
    history_closed = [r for r in history_all if not _row_open(r)]
    location_name = ''
    for loc in locations:
        try:
            if int(loc.get('code')) == int(location_code_int):
                location_name = str(loc.get('name') or '').strip()
                break
        except (TypeError, ValueError):
            continue
    today_iso = date.today().isoformat()
    # Counter Operations selects the register via picker / QZ hostname; do not block entry when Flask session
    # lacks countercode (Counter Setup save/update clears session by design).
    pos_needs_counter_prompt = False
    pos_counter_setup_url = url_for('pos_billing.pos_counter_setup_list')
    return render_template(
        'pos_billing/pos_counter_operations.html',
        location_code=location_code_int,
        location_name=location_name,
        locations=locations,
        counters=counters,
        initial_counter_code=initial_counter_code,
        history_opened=history_opened,
        history_closed=history_closed,
        history_limit=history_limit,
        today_iso=today_iso,
        open_api_url=url_for('pos_billing.pos_counter_operations_open'),
        close_api_url=url_for('pos_billing.pos_counter_operations_close'),
        shift_bills_api_url=url_for('pos_billing.pos_counter_operations_shift_bills'),
        held_bill_open_api_url=url_for('pos_billing.pos_counter_operations_held_bill_open'),
        held_bill_cancel_api_url=url_for('pos_billing.pos_counter_operations_held_bill_cancel'),
        preclose_report_api_url=url_for('pos_billing.pos_counter_operations_preclose_report'),
        preclose_report_pdf_url=url_for('pos_billing.pos_counter_operations_preclose_report_pdf'),
        pos_billing_url=url_for('pos_billing.pos_billing_page'),
        pos_needs_counter_prompt=pos_needs_counter_prompt,
        pos_counter_setup_url=pos_counter_setup_url,
    )


@bp.route('/pos-billing/counter-operations/open', methods=['POST'])
def pos_counter_operations_open():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    if not _try_acquire_pos_billing_save_lock():
        return json_response_rotate_pos({'success': False, 'error': 'A POS save is already in progress for this session. Please wait.', 'save_session_locked': True}, 423)
    try:
        submitted_nonce = extract_submitted_save_nonce(request)
        if not reject_invalid_pos_save_nonce(submitted_nonce):
            return replay_blocked_response_pos()
        user_dbkey = session.get('tenant_id')
        if user_dbkey:
            _apply_active_connection(user_dbkey)
        payload = request.get_json(silent=True) or {}
        try:
            location_code = int(payload.get('location_code'))
            counter_code = int(payload.get('counter_code'))
            shift_code = int(payload.get('shift_code') or 1)
        except (TypeError, ValueError):
            return json_response_rotate_pos({'success': False, 'error': 'Invalid location, counter, or shift'}, 400)
        raw_date = (payload.get('pos_date') or '').strip()
        try:
            pos_d = datetime.strptime(raw_date[:10], '%Y-%m-%d').date() if raw_date else date.today()
        except ValueError:
            return json_response_rotate_pos({'success': False, 'error': 'Invalid POS date (use YYYY-MM-DD)'}, 400)
        opened_by = (session.get('user') or '').strip()
        existing_open = find_open_counter_operation(location_code, counter_code, db_key=None)
        if existing_open:
            try:
                _persist_pos_counter_session(int(counter_code), int(location_code))
            except (TypeError, ValueError):
                pass
            return json_response_rotate_pos(
                {
                    'success': True,
                    'already_open': True,
                    'open': _norm_co_rows([existing_open])[0],
                    'message': 'Counter already has an open shift. Existing POS date loaded.',
                }
            )
        if not commit_pos_save_nonce(submitted_nonce):
            return replay_blocked_response_pos()
        ok, err = open_pos_counter_operation(location_code=location_code, counter_code=counter_code, pos_date=pos_d, shift_code=shift_code, opened_by=opened_by, db_key=None)
        if not ok:
            return json_response_rotate_pos({'success': False, 'error': err or 'Open failed'}, 400)
        open_row = find_open_counter_operation(location_code, counter_code, db_key=None)
        try:
            _persist_pos_counter_session(int(counter_code), int(location_code))
        except (TypeError, ValueError):
            try:
                session['countercode'] = int(counter_code)
                session.modified = True
            except (TypeError, ValueError):
                pass
        return json_response_rotate_pos({'success': True, 'open': _norm_co_rows([open_row])[0] if open_row else None})
    finally:
        _release_pos_billing_save_lock()


@bp.route('/pos-billing/counter-operations/shift-bills', methods=['GET'])
def pos_counter_operations_shift_bills():
    """Held and canceled bills for the selected counter on POS date (shift close guard)."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    try:
        location_code = int(request.args.get('location_code') or _resolve_location_code())
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Invalid location'}, 400)
    counter_code = None
    for _arg in ('counter_code', 'countercode'):
        try:
            counter_code = int(request.args.get(_arg))
            break
        except (TypeError, ValueError):
            continue
    if counter_code is None:
        counter_code = _session_pos_counter_code()
    if counter_code is None or int(counter_code) <= 0:
        return jsonify({'success': False, 'error': 'Select a counter or assign one in Counter setup'}, 400)
    counter_code = int(counter_code)
    raw_date = (request.args.get('pos_date') or '').strip()
    pos_d = None
    if raw_date:
        try:
            pos_d = datetime.strptime(raw_date[:10], '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'success': False, 'error': 'Invalid POS date (use YYYY-MM-DD)'}, 400)
    open_row = find_open_counter_operation(location_code, counter_code, db_key=None)
    shift_open = open_row is not None
    shift_code = None
    if open_row:
        shift_pos_iso = _counter_ops_pos_date_iso(open_row)
        if shift_pos_iso:
            try:
                pos_d = datetime.strptime(shift_pos_iso[:10], '%Y-%m-%d').date()
            except ValueError:
                pass
        r_open = {str(k).lower(): v for k, v in open_row.items()} if isinstance(open_row, dict) else {}
        try:
            sc = int(r_open.get('shiftcode') or 0)
            if sc >= 0:
                shift_code = sc
        except (TypeError, ValueError):
            shift_code = None
    if pos_d is None:
        pos_d = date.today()

    def _norm_bill_rows(rows: Any) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for r in rows or []:
            if not isinstance(r, dict):
                continue
            out.append({str(k).lower(): v for k, v in r.items()})
        return out

    held_raw = list_pos_held_bills_for_counter(location_code, counter_code, pos_d, limit=200, db_key=None)
    canceled_raw = list_pos_canceled_bills_for_counter(location_code, counter_code, pos_d, limit=200, db_key=None)
    held_count = count_pos_held_bills_for_counter(location_code, counter_code, pos_d, db_key=None)
    last_closed = get_latest_closed_pos_date_for_counter(location_code, counter_code, db_key=None)
    min_open_pos_date = None
    if last_closed is not None:
        min_open_pos_date = (last_closed + timedelta(days=1)).isoformat()
    return jsonify(
        {
            'success': True,
            'location_code': location_code,
            'counter_code': counter_code,
            'pos_date': pos_d.isoformat(),
            'held': _norm_bill_rows(held_raw),
            'canceled': _norm_bill_rows(canceled_raw),
            'held_count': held_count,
            'can_close_shift': held_count <= 0,
            'last_closed_pos_date': last_closed.isoformat() if last_closed else None,
            'min_open_pos_date': min_open_pos_date,
            'shift_open': shift_open,
            'shift_code': shift_code,
        }
    )


def _shift_preclose_to_plain_text(report: Dict[str, Any], design: Optional[Dict[str, Any]] = None) -> str:
    """Thermal-style pre-close / shift-close report (matches legacy TIME CHECK layout)."""
    design = design or load_receipt_design()
    w = min(42, max(24, min(80, int(design.get('page_width', RECEIPT_WIDTH)))))
    is_final = bool(report.get('is_final'))

    def center(text: Any) -> str:
        return str(text or '')[:w].center(w)

    def rule(ch: str = '-') -> str:
        return ch * w

    def two_col(left: Any, right: Any) -> str:
        left_s = str(left or '')
        right_s = str(right or '')
        gap = max(1, w - len(left_s) - len(right_s))
        return (left_s + ' ' * gap + right_s)[:w]

    def amount(v: Any) -> str:
        try:
            return f'{float(v or 0):.2f}'
        except (TypeError, ValueError):
            return '0.00'

    loc_name = str(report.get('location_name') or 'Store').strip().upper()
    phones = str(report.get('location_phones') or '').strip()
    out: List[str] = []
    out.append(center(loc_name))
    if phones:
        out.append(center(phones))
    out.append('')
    if is_final:
        out.append(center('*** SHIFT CLOSE COPY ***'))
        out.append(center('Final shift close'))
    else:
        out.append(center('*** X REPORT COPY ***'))
        out.append(center('Interim report (not final)'))
    out.append(two_col('Counter day :', str(report.get('pos_date_display') or '')))
    out.append(rule())
    cc = report.get('counter_code')
    cn = str(report.get('counter_name') or '').strip()
    counter_disp = str(cc) if cc is not None else ''
    if cn:
        counter_disp = (counter_disp + ' ' + cn).strip()
    out.append(two_col('Counter', counter_disp or '—'))
    cashier = str(report.get('cashier') or '').strip()
    if cashier:
        out.append(two_col('Cashier', cashier))
    out.append(two_col('Check Time', str(report.get('check_time_display') or '')))
    out.append(rule())
    out.append(two_col('Direct customer', amount(report.get('direct_customer'))))
    out.append(two_col('Credit', amount(report.get('credit_sales'))))
    out.append(two_col('Total Sales', amount(report.get('total_sales'))))
    out.append(two_col('Total Discount', amount(report.get('total_discount') or report.get('discount_lines'))))
    out.append(two_col('Sales returns', amount(report.get('sales_returns'))))
    out.append(two_col('Total Cancel', amount(report.get('total_cancel'))))
    out.append(rule())
    tender_rows = report.get('tender_breakdown') or []
    credit_tender_codes = frozenset({'CREDIT', 'ON_ACCOUNT', 'ONACCOUNT', 'CREDIT_ON_ACCOUNT', 'ACCOUNT'})
    cash_row: Optional[Dict[str, Any]] = None
    for row in tender_rows:
        if not isinstance(row, dict):
            continue
        code_u = str(row.get('code') or '').strip().upper()
        if code_u in credit_tender_codes:
            continue
        try:
            amt = float(row.get('amount') or 0)
        except (TypeError, ValueError):
            amt = 0.0
        if abs(amt) <= 0.0005:
            continue
        if row.get('is_cash') or str(row.get('code') or '').strip().upper() == 'CASH':
            cash_row = row
            continue
        label = str(row.get('label') or row.get('code') or '—').strip()
        out.append(two_col(label, amount(amt)))
    if cash_row is not None:
        out.append(two_col('Cash in Box', amount(cash_row.get('amount'))))
    else:
        out.append(two_col('Cash in Box', amount(report.get('cash_in_box'))))
    coll_total = report.get('collection_total')
    if coll_total is None:
        coll_total = sum(
            float(row.get('amount') or 0)
            for row in tender_rows
            if isinstance(row, dict)
            and not _is_pos_shift_credit_tender(str(row.get('code') or ''))
        )
    try:
        coll_f = float(coll_total or 0)
    except (TypeError, ValueError):
        coll_f = 0.0
    if abs(coll_f) > 0.0005:
        out.append(two_col('Total collection', amount(coll_f)))
    out.append(rule())
    if is_final:
        out.append(center('Shift closed.'))
    else:
        out.append(center('Use Close for official final print.'))
    out.append(center(f"Bills: {int(report.get('bill_count') or 0)}"))
    return '\n'.join(out)


def _pos_hold_cancel_slip_snapshot(
    location_code: int,
    billno: int,
) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    """Read temp bill header/lines for hold/cancel slip (call before void removes temp)."""
    ok, err, raw_header, _raw_detail_rows, shaped_lines, _dtl_order = get_temp_bill_by_billno(
        location_code, billno,
    )
    if not ok or not raw_header:
        return (False, err or 'Temp bill not found.', None)
    item_count = 0
    line_total = 0.0
    for line in shaped_lines or []:
        if int(line.get('item_flag') or 1) == 0:
            continue
        qty = float(line.get('quantity') or 0)
        if abs(qty) < 1e-9:
            continue
        item_count += 1
        rate = float(line.get('rate') or 0)
        disc = float(line.get('discount') or 0)
        line_total += qty * rate - disc
    amount = raw_header.get('netbillamount')
    if amount is None:
        amount = raw_header.get('billamount')
    try:
        amount_f = float(amount if amount is not None else line_total)
    except (TypeError, ValueError):
        amount_f = line_total
    return (
        True,
        None,
        {
            'billno': billno,
            'amount': round(amount_f, 2),
            'item_count': item_count,
        },
    )


def _build_pos_hold_cancel_slip_text(
    action: str,
    *,
    billno: int,
    user: str,
    user_dbkey: Optional[str],
    snapshot: Optional[Dict[str, Any]] = None,
) -> str:
    """Narrow POS slip for bill hold or full cancel (void-all)."""
    design = load_receipt_design()
    w = min(42, max(24, min(80, int(design.get('page_width', RECEIPT_WIDTH)))))
    snap = snapshot or {}
    try:
        amount_f = float(snap.get('amount') or 0)
    except (TypeError, ValueError):
        amount_f = 0.0
    item_count = int(snap.get('item_count') or 0)
    billno_disp = str(snap.get('billno') or billno)
    now = datetime.now()
    date_disp = now.strftime('%d/%m/%Y')
    time_disp = now.strftime('%H:%M:%S')
    loc_info = get_location_info_by_dbkey(user_dbkey or 'HO')
    loc_name = str((loc_info or {}).get('locationname') or 'Store').strip().upper()
    act = (action or '').strip().upper()
    title = '*** BILL HELD ***' if act == 'HOLD' else '*** BILL CANCELED ***'

    def center(text: Any) -> str:
        return str(text or '')[:w].center(w)

    def rule(ch: str = '-') -> str:
        return ch * w

    def two_col(left: Any, right: Any) -> str:
        left_s = str(left or '')
        right_s = str(right or '')
        gap = max(1, w - len(left_s) - len(right_s))
        return (left_s + ' ' * gap + right_s)[:w]

    out: List[str] = []
    out.append(center(title))
    out.append(center(loc_name))
    out.append('')
    out.append(two_col('Bill No:', billno_disp))
    out.append(two_col('User:', str(user or '').strip() or '—'))
    out.append(two_col('Date:', date_disp))
    out.append(two_col('Time:', time_disp))
    out.append(two_col('Items:', str(item_count)))
    out.append(two_col('Amount:', f'{amount_f:.2f}'))
    out.append('')
    if act == 'HOLD':
        out.append(center('HELD BILL'))
    else:
        out.append(center('CANCELED BILL'))
    out.append(center(f'Bill No {billno_disp}'))
    out.append('')
    out.append(rule())
    return '\n'.join(out)


def _fetch_shift_preclose_report_from_request() -> Tuple[Optional[Dict[str, Any]], Optional[str], int]:
    """Build shift pre-close / X Report payload from current request query args."""
    try:
        location_code = int(request.args.get('location_code') or _resolve_location_code())
    except (TypeError, ValueError):
        return (None, 'Invalid location', 400)
    counter_code = None
    for _arg in ('counter_code', 'countercode'):
        try:
            counter_code = int(request.args.get(_arg))
            break
        except (TypeError, ValueError):
            continue
    if counter_code is None:
        counter_code = _session_pos_counter_code()
    if counter_code is None or int(counter_code) <= 0:
        return (None, 'Select a counter', 400)
    counter_code = int(counter_code)
    raw_date = (request.args.get('pos_date') or '').strip()
    pos_d = None
    if raw_date:
        try:
            pos_d = datetime.strptime(raw_date[:10], '%Y-%m-%d').date()
        except ValueError:
            return (None, 'Invalid POS date (use YYYY-MM-DD)', 400)
    open_row = find_open_counter_operation(location_code, counter_code, db_key=None)
    if open_row and pos_d is None:
        shift_pos_iso = _counter_ops_pos_date_iso(open_row)
        if shift_pos_iso:
            try:
                pos_d = datetime.strptime(shift_pos_iso[:10], '%Y-%m-%d').date()
            except ValueError:
                pass
    if pos_d is None:
        pos_d = date.today()
    is_final = str(request.args.get('final') or '').strip().lower() in ('1', 'true', 'yes', 'y')
    cashier = (session.get('user') or '').strip()
    try:
        emp = session.get('employeecode')
        if emp is not None and str(emp).strip() != '':
            cashier = f'{cashier} {emp}'.strip()
    except (TypeError, ValueError):
        pass
    report = build_pos_shift_preclose_report(
        location_code,
        counter_code,
        pos_d,
        db_key=None,
        cashier=cashier,
        is_final=is_final,
    )
    if not report.get('ok'):
        return (None, report.get('error') or 'Report failed', 400)
    return (report, None, 200)


def _shift_preclose_pdf_bytes(report: Dict[str, Any]) -> Optional[bytes]:
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_RIGHT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except Exception:
        return None

    def text(value: Any) -> str:
        return str(value if value is not None else '').strip()

    def money(value: Any) -> str:
        try:
            return f'{float(value or 0):,.2f}'
        except (TypeError, ValueError):
            return '0.00'

    is_final = bool(report.get('is_final'))
    cc = report.get('counter_code')
    cn = text(report.get('counter_name'))
    counter_disp = str(cc) if cc is not None else ''
    if cn:
        counter_disp = (counter_disp + ' ' + cn).strip()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=0.45 * inch,
        bottomMargin=0.35 * inch,
        leftMargin=0.45 * inch,
        rightMargin=0.45 * inch,
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle('xrep_title', parent=styles['Heading1'], alignment=TA_CENTER, fontSize=16, leading=19, spaceAfter=4)
    subtitle = ParagraphStyle('xrep_sub', parent=styles['Normal'], alignment=TA_CENTER, fontSize=10, leading=12, textColor=colors.HexColor('#475569'), spaceAfter=10)
    section = ParagraphStyle('xrep_section', parent=styles['Normal'], fontSize=9.5, leading=12, spaceBefore=6, spaceAfter=4)
    right = ParagraphStyle('xrep_right', parent=styles['Normal'], alignment=TA_RIGHT, fontSize=9, leading=11)

    banner = 'SHIFT CLOSE COPY' if is_final else 'X REPORT COPY'
    banner_sub = 'Final shift close' if is_final else 'Interim report (not final)'
    story: List[Any] = []
    loc_name = text(report.get('location_name') or 'Store')
    if loc_name:
        story.append(Paragraph(loc_name.upper(), title))
    phones = text(report.get('location_phones'))
    if phones:
        story.append(Paragraph(phones, subtitle))
    story.extend([
        Paragraph(f'<b>{banner}</b>', title),
        Paragraph(banner_sub, subtitle),
    ])

    meta_rows = [
        ['Counter day', text(report.get('pos_date_display'))],
        ['Counter', counter_disp or '—'],
        ['Cashier', text(report.get('cashier')) or '—'],
        ['Check time', text(report.get('check_time_display'))],
    ]
    meta = Table(meta_rows, colWidths=[1.45 * inch, 4.55 * inch])
    meta.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.35, colors.HexColor('#cbd5e1')),
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f1f5f9')),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('PADDING', (0, 0), (-1, -1), 6),
    ]))
    story.extend([meta, Spacer(1, 8), Paragraph('<b>Sales summary</b>', section)])

    summary_rows = [
        ['Direct customer', money(report.get('direct_customer'))],
        ['Credit', money(report.get('credit_sales'))],
        ['Total sales', money(report.get('total_sales'))],
        ['Total discount', money(report.get('total_discount') or report.get('discount_lines'))],
        ['Sales returns', money(report.get('sales_returns'))],
        ['Total cancel', money(report.get('total_cancel'))],
    ]
    summary = Table(summary_rows, colWidths=[2.8 * inch, 3.2 * inch])
    summary.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.35, colors.HexColor('#cbd5e1')),
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f8fafc')),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('PADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(summary)

    tender_rows = report.get('tender_breakdown') or []
    credit_tender_codes = frozenset({'CREDIT', 'ON_ACCOUNT', 'ONACCOUNT', 'CREDIT_ON_ACCOUNT', 'ACCOUNT'})
    cash_row: Optional[Dict[str, Any]] = None
    tender_data: List[List[Any]] = [['Tender', Paragraph('Amount', right)]]
    for row in tender_rows:
        if not isinstance(row, dict):
            continue
        code_u = str(row.get('code') or '').strip().upper()
        if code_u in credit_tender_codes:
            continue
        try:
            amt = float(row.get('amount') or 0)
        except (TypeError, ValueError):
            amt = 0.0
        if abs(amt) <= 0.0005:
            continue
        if row.get('is_cash') or code_u == 'CASH':
            cash_row = row
            continue
        label = text(row.get('label') or row.get('code') or '—')
        tender_data.append([label, Paragraph(money(amt), right)])
    if cash_row is not None:
        tender_data.append(['Cash in box', Paragraph(money(cash_row.get('amount')), right)])
    else:
        tender_data.append(['Cash in box', Paragraph(money(report.get('cash_in_box')), right)])
    coll_total = report.get('collection_total')
    if coll_total is None:
        coll_total = sum(
            float(row.get('amount') or 0)
            for row in tender_rows
            if isinstance(row, dict)
            and not _is_pos_shift_credit_tender(str(row.get('code') or ''))
        )
    try:
        coll_f = float(coll_total or 0)
    except (TypeError, ValueError):
        coll_f = 0.0
    if abs(coll_f) > 0.0005:
        tender_data.append(['Total collection', Paragraph(f'<b>{money(coll_f)}</b>', right)])

    if len(tender_data) > 1:
        tender_table = Table(tender_data, colWidths=[2.8 * inch, 3.2 * inch])
        tender_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.35, colors.HexColor('#cbd5e1')),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e0f2fe')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        story.extend([Spacer(1, 8), Paragraph('<b>Collections</b>', section), tender_table])

    footer = 'Shift closed.' if is_final else 'Use Close shift for the official final print.'
    story.extend([
        Spacer(1, 10),
        Paragraph(footer, subtitle),
        Paragraph(f"Bills: {int(report.get('bill_count') or 0)}", subtitle),
    ])
    doc.build(story)
    return buffer.getvalue()


def _co_verify_held_bill_for_counter(billno: int, location_code: int, counter_code: int) -> Tuple[bool, str]:
    """Ensure bill is held (H) and belongs to the given counter."""
    ok, err, header, _lines = get_held_bill(billno, location_code)
    if not ok:
        return (False, err or 'Held bill not found.')
    try:
        bill_cc = int(header.get('countercode') or 0) if header else 0
    except (TypeError, ValueError):
        bill_cc = 0
    if bill_cc != int(counter_code):
        return (False, 'Held bill belongs to a different counter.')
    return (True, '')


@bp.route('/pos-billing/counter-operations/preclose-report/pdf', methods=['GET'])
def pos_counter_operations_preclose_report_pdf():
    """PDF copy of X Report / shift-close report."""
    if not session.get('user'):
        return Response('Not authenticated', status=401, mimetype='text/plain')
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    report, err, status = _fetch_shift_preclose_report_from_request()
    if err or not report:
        return Response(err or 'Report failed', status=status or 400, mimetype='text/plain')
    pdf_bytes = _shift_preclose_pdf_bytes(report)
    if not pdf_bytes:
        return Response('PDF generation failed (reportlab not available).', status=500, mimetype='text/plain')
    is_final = bool(report.get('is_final'))
    cc = report.get('counter_code') or 'counter'
    pos_d = str(report.get('pos_date') or '')[:10].replace('-', '')
    prefix = 'shift_close' if is_final else 'x_report'
    filename = f"{prefix}_{cc}_{pos_d or datetime.now().strftime('%Y%m%d')}_{datetime.now().strftime('%H%M%S')}.pdf"
    return Response(pdf_bytes, mimetype='application/pdf', headers={'Content-Disposition': f'inline; filename="{filename}"'})


@bp.route('/pos-billing/counter-operations/preclose-report', methods=['GET'])
def pos_counter_operations_preclose_report():
    """Pre-close TIME CHECK or final shift-close totals for counter + POS date."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    report, err, status = _fetch_shift_preclose_report_from_request()
    if err:
        return jsonify({'success': False, 'error': err}, status)
    design = load_receipt_design()
    receipt_text = _shift_preclose_to_plain_text(report, design)
    return jsonify({'success': True, 'report': report, 'receipt_text': receipt_text})


@bp.route('/pos-billing/counter-operations/held-bill/open', methods=['POST'])
def pos_counter_operations_held_bill_open():
    """Verify held bill and redirect to POS Billing; till JS retrieves hold (H→P) on load."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    payload = request.get_json(silent=True) or {}
    try:
        location_code = int(payload.get('location_code') or _resolve_location_code())
        counter_code = int(payload.get('counter_code'))
        billno = int(payload.get('billno'))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Invalid location, counter, or bill number'}, 400)
    if billno <= 0 or counter_code <= 0:
        return jsonify({'success': False, 'error': 'Invalid counter or bill number'}, 400)
    ok_verify, verr = _co_verify_held_bill_for_counter(billno, location_code, counter_code)
    if not ok_verify:
        return jsonify({'success': False, 'error': verr}, 400)
    try:
        _persist_pos_counter_session(int(counter_code), int(location_code))
    except (TypeError, ValueError):
        pass
    billing_url = url_for('pos_billing.pos_billing_page') + '?billno=' + str(billno)
    return jsonify({'success': True, 'billno': billno, 'redirect_url': billing_url})


@bp.route('/pos-billing/counter-operations/held-bill/cancel', methods=['POST'])
def pos_counter_operations_held_bill_cancel():
    """Void held bill: copy to canceled tables and remove from temp."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    payload = request.get_json(silent=True) or {}
    try:
        location_code = int(payload.get('location_code') or _resolve_location_code())
        counter_code = int(payload.get('counter_code'))
        billno = int(payload.get('billno'))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Invalid location, counter, or bill number'}, 400)
    if billno <= 0 or counter_code <= 0:
        return jsonify({'success': False, 'error': 'Invalid counter or bill number'}, 400)
    ok_verify, verr = _co_verify_held_bill_for_counter(billno, location_code, counter_code)
    if not ok_verify:
        return jsonify({'success': False, 'error': verr}, 400)
    ok, err = void_all_temp_bill(billno, location_code)
    if not ok:
        return jsonify({'success': False, 'error': err or 'Cancel failed'}, 400)
    return jsonify({'success': True, 'billno': billno})


@bp.route('/pos-billing/counter-operations/close', methods=['POST'])
def pos_counter_operations_close():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    payload = request.get_json(silent=True) or {}
    try:
        location_code = int(payload.get('location_code'))
        counter_code = int(payload.get('counter_code'))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Invalid location or counter'}, 400)
    closed_by = (session.get('user') or '').strip()
    ok, err = close_pos_counter_operation(location_code=location_code, counter_code=counter_code, closed_by=closed_by, db_key=None)
    if not ok:
        return jsonify({'success': False, 'error': err or 'Close failed'}, 400)
    return jsonify({'success': True})


@bp.route('/pos-billing/bills')
def pos_bills_page():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    location_code_int = _resolve_location_code()
    today = datetime.now().strftime('%Y-%m-%d')
    date_from = (request.args.get('from') or request.args.get('from_dt') or '').strip()[:10] or today
    date_to = (request.args.get('to') or request.args.get('to_dt') or '').strip()[:10] or today
    list_limit = 500

    def _norm_rows(rows: Any) -> list:
        out = []
        for r in rows or []:
            if isinstance(r, dict):
                out.append({str(k).lower(): v for k, v in r.items()})
            else:
                out.append(r)
        return out

    posted_rows = _norm_rows(list_pos_bills_posted(
        location_code_int, limit=list_limit, from_dt=date_from, to_dt=date_to, pos_only=True,
    ))
    held_rows = _norm_rows(list_pos_bills_held(
        location_code_int, limit=list_limit, from_dt=date_from, to_dt=date_to,
    ))
    canceled_rows = _norm_rows(list_pos_bills_canceled(
        location_code_int, limit=list_limit, from_dt=date_from, to_dt=date_to,
    ))
    detail_url = url_for('pos_billing.pos_bills_detail')
    print_url = url_for('pos_billing.pos_receipt_print')
    return render_template(
        'pos_billing/pos_bills.html',
        location_code=location_code_int,
        date_from=date_from,
        date_to=date_to,
        posted_rows=posted_rows,
        held_rows=held_rows,
        canceled_rows=canceled_rows,
        detail_url=detail_url,
        print_url=print_url,
    )


@bp.route('/pos-billing/settlement-posting')
def pos_settlement_posting_page():
    """List open drafts and posted batches for this branch (menu default)."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    location_code_int, branch_display = _pos_settlement_branch_display()
    api_settlement_drafts_url = url_for('pos_billing.pos_settlement_posting_api_drafts')
    api_settlement_pending_by_date_url = url_for('pos_billing.pos_settlement_posting_api_pending_by_date')
    api_settlement_draft_mutation_url = url_for('pos_billing.pos_settlement_posting_api_draft_mutation')
    workflow_url = url_for('pos_billing.pos_settlement_posting_workflow_page')
    settlement_pdf_url = url_for('pos_billing.pos_settlement_posting_pdf')
    return render_template(
        'pos_billing/pos_settlement_posting_list.html',
        location_code=location_code_int,
        branch_display=branch_display,
        api_settlement_drafts_url=api_settlement_drafts_url,
        api_settlement_pending_by_date_url=api_settlement_pending_by_date_url,
        api_settlement_draft_mutation_url=api_settlement_draft_mutation_url,
        workflow_url=workflow_url,
        settlement_pdf_url=settlement_pdf_url,
    )


@bp.route('/pos-billing/settlement-posting/new')
def pos_settlement_posting_workflow_page():
    """Cashier-wise bills, verify/post settlement (opened from list via New or Open)."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    location_code_int, branch_display = _pos_settlement_branch_display()
    default_settlement_date = resolve_pos_settlement_default_date(location_code_int).isoformat()
    _draft_raw = request.args.get('draft')
    initial_draft_id = None
    if _draft_raw not in (None, ''):
        try:
            initial_draft_id = int(str(_draft_raw).strip())
        except (TypeError, ValueError):
            initial_draft_id = None
    initial_from_date = (request.args.get('from') or '').strip()[:10] or None
    initial_to_date = (request.args.get('to') or '').strip()[:10] or None
    if initial_from_date and len(initial_from_date) != 10:
        initial_from_date = None
    if initial_to_date and len(initial_to_date) != 10:
        initial_to_date = None
    if initial_from_date and not initial_to_date:
        initial_to_date = initial_from_date
    api_bills_url = url_for('pos_billing.pos_settlement_posting_api_bills')
    api_counters_url = url_for('pos_billing.pos_settlement_posting_api_counters')
    api_settlement_drafts_url = url_for('pos_billing.pos_settlement_posting_api_drafts')
    api_settlement_coa_url = url_for('pos_billing.pos_settlement_posting_api_coa')
    api_settlement_tender_defaults_url = url_for('pos_billing.pos_settlement_posting_api_tender_defaults')
    api_settlement_payment_mode_summary_url = url_for('pos_billing.pos_settlement_posting_api_payment_mode_summary')
    api_settlement_draft_generate_url = url_for('pos_billing.pos_settlement_posting_api_draft_generate')
    api_settlement_draft_mutation_url = url_for('pos_billing.pos_settlement_posting_api_draft_mutation')
    api_settlement_reverse_gl_url = url_for('pos_billing.pos_settlement_posting_api_settlement_reverse_gl')
    settlement_list_url = url_for('pos_billing.pos_settlement_posting_page')
    api_validate_pos_closed_url = url_for('pos_billing.pos_validate_pos_date_closed_api')
    closed_periods: list = []
    try:
        from addons.accounts.period_closing_db import list_closed_periods, resolve_open_voucher_date
        closed_periods = list_closed_periods(location_code_int)
        default_settlement_date = resolve_open_voucher_date(default_settlement_date, location_code_int)
    except Exception:
        closed_periods = []
    return render_template(
        'pos_billing/pos_settlement_posting.html',
        location_code=location_code_int,
        branch_display=branch_display,
        default_settlement_date=default_settlement_date,
        api_bills_url=api_bills_url,
        api_counters_url=api_counters_url,
        api_settlement_drafts_url=api_settlement_drafts_url,
        api_settlement_coa_url=api_settlement_coa_url,
        api_settlement_tender_defaults_url=api_settlement_tender_defaults_url,
        api_settlement_payment_mode_summary_url=api_settlement_payment_mode_summary_url,
        api_settlement_draft_generate_url=api_settlement_draft_generate_url,
        api_settlement_draft_mutation_url=api_settlement_draft_mutation_url,
        api_settlement_reverse_gl_url=api_settlement_reverse_gl_url,
        api_validate_pos_closed_url=api_validate_pos_closed_url,
        settlement_list_url=settlement_list_url,
        initial_draft_id=initial_draft_id,
        initial_from_date=initial_from_date,
        initial_to_date=initial_to_date,
        closed_periods=closed_periods,
    )


def _pos_settlement_pdf_bytes(detail: Dict[str, Any], *, branch_display: str = '') -> Optional[bytes]:
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_RIGHT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except Exception:
        return None

    def text(value: Any) -> str:
        return str(value if value is not None else '').strip()

    def money(value: Any) -> str:
        try:
            return f'{float(value or 0):,.2f}'
        except Exception:
            return '0.00'

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.45 * inch, bottomMargin=0.35 * inch, leftMargin=0.4 * inch, rightMargin=0.4 * inch)
    styles = getSampleStyleSheet()
    title = ParagraphStyle('psp_pdf_title', parent=styles['Heading1'], alignment=TA_CENTER, fontSize=15, leading=18, spaceAfter=6)
    normal = ParagraphStyle('psp_pdf_normal', parent=styles['Normal'], fontSize=8.5, leading=11)
    small = ParagraphStyle('psp_pdf_small', parent=styles['Normal'], fontSize=7.5, leading=9)
    right = ParagraphStyle('psp_pdf_right', parent=normal, alignment=TA_RIGHT)
    story: List[Any] = [Paragraph('POS SETTLEMENT VOUCHER', title)]

    meta = detail.get('meta') if isinstance(detail.get('meta'), dict) else {}
    lines = detail.get('journal_lines') if isinstance(detail.get('journal_lines'), list) else []
    bill_nos = detail.get('bill_nos') if isinstance(detail.get('bill_nos'), list) else []
    debit_total = sum(float((ln or {}).get('debit') or 0) for ln in lines if isinstance(ln, dict))
    credit_total = sum(float((ln or {}).get('credit') or 0) for ln in lines if isinstance(ln, dict))
    summary_rows = [
        ['Draft ID', text(detail.get('draft_id')), 'GL Voucher', text(detail.get('voucher_no'))],
        ['Voucher Date', text(detail.get('voucher_date')), 'Status', text(detail.get('status'))],
        ['Branch', text(branch_display or detail.get('location_code')), 'Bills', str(len(bill_nos))],
        ['Reference', text(detail.get('reference_no')), 'Approved By', text(meta.get('approved_by'))],
    ]
    summary = Table(summary_rows, colWidths=[1.15 * inch, 2.05 * inch, 1.15 * inch, 2.05 * inch])
    summary.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.35, colors.HexColor('#cbd5e1')),
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f1f5f9')),
        ('BACKGROUND', (2, 0), (2, -1), colors.HexColor('#f1f5f9')),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('PADDING', (0, 0), (-1, -1), 5),
    ]))
    story.extend([summary, Spacer(1, 8)])

    narration = text(detail.get('narration') or meta.get('remarks_panel'))
    if narration:
        story.extend([Paragraph('<b>Narration</b>', normal), Paragraph(narration, normal), Spacer(1, 8)])

    cash_rows = [
        ['Opening Cash', money(meta.get('opening_cash')), 'Expenses', money(meta.get('expenses'))],
        ['Actual Cash', money(meta.get('actual_cash')), 'Cash Variance', money(meta.get('cash_variance_sum'))],
    ]
    cash_table = Table(cash_rows, colWidths=[1.35 * inch, 1.85 * inch, 1.35 * inch, 1.85 * inch])
    cash_table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.35, colors.HexColor('#cbd5e1')),
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f8fafc')),
        ('BACKGROUND', (2, 0), (2, -1), colors.HexColor('#f8fafc')),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('ALIGN', (3, 0), (3, -1), 'RIGHT'),
        ('PADDING', (0, 0), (-1, -1), 5),
    ]))
    story.extend([Paragraph('<b>Cash Settlement</b>', normal), cash_table, Spacer(1, 8)])

    journal_data: List[Any] = [['#', 'Dr/Cr', 'Account', 'Account Name / Remarks', 'Debit', 'Credit']]
    for idx, ln in enumerate(lines, start=1):
        if not isinstance(ln, dict):
            continue
        dr = float(ln.get('debit') or 0)
        cr = float(ln.get('credit') or 0)
        journal_data.append([
            str(idx),
            'Dr' if dr > 0 else 'Cr',
            text(ln.get('account_code')),
            Paragraph(text(ln.get('account_name') or ln.get('remarks')), small),
            Paragraph(money(dr), right),
            Paragraph(money(cr), right),
        ])
    journal_data.append(['', '', '', Paragraph('<b>Total</b>', small), Paragraph(f'<b>{money(debit_total)}</b>', right), Paragraph(f'<b>{money(credit_total)}</b>', right)])
    journal_table = Table(journal_data, colWidths=[0.35 * inch, 0.48 * inch, 0.9 * inch, 2.9 * inch, 0.85 * inch, 0.85 * inch], repeatRows=1)
    journal_table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.35, colors.HexColor('#cbd5e1')),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e0f2fe')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7.5),
        ('ALIGN', (0, 1), (2, -1), 'CENTER'),
        ('ALIGN', (4, 1), (5, -1), 'RIGHT'),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f8fafc')),
        ('PADDING', (0, 0), (-1, -1), 4),
    ]))
    story.extend([Paragraph('<b>Journal Posting</b>', normal), journal_table, Spacer(1, 8)])

    if bill_nos:
        bill_date_by_no: Dict[int, str] = {}
        try:
            loc = int(detail.get('location_code') or 0)
            clean_nos = []
            for x in bill_nos:
                try:
                    n = int(x)
                    if n > 0:
                        clean_nos.append(n)
                except (TypeError, ValueError):
                    continue
            if loc > 0 and clean_nos:
                for r in _fetch_billhdr_rows_for_pos_settlement(loc, clean_nos[:500]) or []:
                    if not isinstance(r, dict):
                        continue
                    rk = {str(k).lower(): v for k, v in r.items()}
                    try:
                        bn = int(rk.get('billno') or 0)
                    except (TypeError, ValueError):
                        bn = 0
                    if bn <= 0:
                        continue
                    bdt = rk.get('billdate')
                    if bdt is not None and hasattr(bdt, 'strftime'):
                        try:
                            bill_date_by_no[bn] = bdt.strftime('%Y-%m-%d')
                        except Exception:
                            bill_date_by_no[bn] = str(bdt)[:10]
                    else:
                        bill_date_by_no[bn] = str(bdt or '')[:10]
        except Exception:
            bill_date_by_no = {}

        bill_data: List[Any] = [['#', 'Bill No', 'Bill Date']]
        shown = bill_nos[:200]
        for idx, bn_raw in enumerate(shown, start=1):
            try:
                bn = int(bn_raw)
            except (TypeError, ValueError):
                bn = 0
            bill_data.append([
                str(idx),
                text(bn_raw),
                text(bill_date_by_no.get(bn) or '—'),
            ])
        if len(bill_nos) > len(shown):
            bill_data.append(['', f'… +{len(bill_nos) - len(shown)} more', ''])
        bill_table = Table(bill_data, colWidths=[0.45 * inch, 1.6 * inch, 1.6 * inch], repeatRows=1)
        bill_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.35, colors.HexColor('#cbd5e1')),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f1f5f9')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 7.5),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('PADDING', (0, 0), (-1, -1), 4),
        ]))
        story.extend([Paragraph('<b>Settled Bills</b>', normal), bill_table])

    doc.build(story)
    return buffer.getvalue()


@bp.route('/pos-billing/settlement-posting/pdf', methods=['GET'])
def pos_settlement_posting_pdf():
    if not session.get('user'):
        return Response('Not authenticated', status=401, mimetype='text/plain')
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    location_code_int, branch_display = _pos_settlement_branch_display()
    loc_raw = (request.args.get('location_code') or '').strip()
    if loc_raw.isdigit():
        location_code_int = int(loc_raw)
    try:
        draft_id = int(request.args.get('draft_id') or 0)
    except (TypeError, ValueError):
        draft_id = 0
    if draft_id <= 0:
        return Response('draft_id is required.', status=400, mimetype='text/plain')
    detail = get_pos_settlement_draft_detail(draft_id, location_code_int)
    if not detail:
        return Response('POS settlement batch not found.', status=404, mimetype='text/plain')
    if str(detail.get('status') or '').strip().upper() != 'POSTED':
        return Response('POS Settlement PDF is available after posting.', status=400, mimetype='text/plain')
    pdf_bytes = _pos_settlement_pdf_bytes(detail, branch_display=branch_display)
    if not pdf_bytes:
        return Response('PDF generation failed (reportlab not available).', status=500, mimetype='text/plain')
    safe_v = ''.join((c for c in str(detail.get('voucher_no') or draft_id) if c.isalnum() or c in ('-', '_')))[:44] or 'pos_settlement'
    filename = f"pos_settlement_{safe_v}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return Response(pdf_bytes, mimetype='application/pdf', headers={'Content-Disposition': f'inline; filename="{filename}"'})


@bp.route('/pos-billing/pos-sales-list')
def pos_sales_list_page():
    """POS bills worksheet: same filters / grid as settlement workflow without posting UI."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    location_code_int, branch_display = _pos_settlement_branch_display()
    api_bills_url = url_for('pos_billing.pos_settlement_posting_api_bills')
    api_counters_url = url_for('pos_billing.pos_settlement_posting_api_counters')
    settlement_workflow_url = url_for('pos_billing.pos_settlement_posting_workflow_page')
    api_summary_url = url_for('pos_billing.pos_sales_list_summary_api')
    return render_template(
        'pos_billing/pos_sales_list.html',
        location_code=location_code_int,
        branch_display=branch_display,
        api_bills_url=api_bills_url,
        api_counters_url=api_counters_url,
        api_summary_url=api_summary_url,
        settlement_workflow_url=settlement_workflow_url,
    )


@bp.route('/pos-billing/pos-sales-list/summary', methods=['GET'])
def pos_sales_list_summary_api():
    """X Report style totals for POS Sales List filters (date range, counter, shift)."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    location_code_int = _resolve_location_code()
    loc_raw = (request.args.get('location_code') or '').strip()
    if loc_raw.isdigit():
        location_code_int = int(loc_raw)
    from_dt = (request.args.get('from') or '').strip()[:10]
    to_dt = (request.args.get('to') or '').strip()[:10]
    from_d = None
    to_d = None
    if from_dt:
        try:
            from_d = datetime.strptime(from_dt, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'success': False, 'error': 'Invalid from date (YYYY-MM-DD)'}, 400)
    if to_dt:
        try:
            to_d = datetime.strptime(to_dt, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'success': False, 'error': 'Invalid to date (YYYY-MM-DD)'}, 400)
    counter_code = None
    for _arg in ('counter_code', 'countercode'):
        raw = (request.args.get(_arg) or '').strip()
        if raw.isdigit() and int(raw) > 0:
            counter_code = int(raw)
            break
    shift_code = (request.args.get('shift_code') or request.args.get('shift') or '').strip()
    summary = build_pos_sales_list_summary(
        location_code_int,
        from_date=from_d,
        to_date=to_d,
        counter_code=counter_code,
        shift_code=shift_code or None,
        db_key=None,
    )
    if not summary.get('ok'):
        return jsonify({'success': False, 'error': summary.get('error') or 'Summary failed'}, 400)
    return jsonify({'success': True, 'summary': summary})


@bp.route('/pos-billing/price-edited-report')
def pos_price_edited_report_page():
    """Report of POS bill lines where unit price was changed from catalog (OLDPRICE vs RATE)."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    location_code_int, branch_display = _pos_settlement_branch_display()
    today = datetime.now().strftime('%Y-%m-%d')
    api_url = url_for('pos_billing.pos_price_edited_report_api')
    export_url = url_for('pos_billing.pos_price_edited_report_export')
    api_counters_url = url_for('pos_billing.pos_settlement_posting_api_counters')
    return render_template(
        'pos_billing/pos_price_edited_report.html',
        location_code=location_code_int,
        branch_display=branch_display,
        default_from=today,
        default_to=today,
        api_url=api_url,
        export_url=export_url,
        api_counters_url=api_counters_url,
    )


@bp.route('/pos-billing/price-edited-report/data', methods=['GET'])
def pos_price_edited_report_api():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    location_code_int = _resolve_location_code()
    loc_raw = (request.args.get('location_code') or '').strip()
    if loc_raw.isdigit():
        location_code_int = int(loc_raw)
    from_dt = (request.args.get('from') or '').strip()[:10]
    to_dt = (request.args.get('to') or '').strip()[:10]
    from_d = None
    to_d = None
    if from_dt:
        try:
            from_d = datetime.strptime(from_dt, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'success': False, 'error': 'Invalid from date (YYYY-MM-DD)'}, 400)
    if to_dt:
        try:
            to_d = datetime.strptime(to_dt, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'success': False, 'error': 'Invalid to date (YYYY-MM-DD)'}, 400)
    counter_code = None
    for _arg in ('counter_code', 'countercode'):
        raw = (request.args.get(_arg) or '').strip()
        if raw.isdigit() and int(raw) > 0:
            counter_code = int(raw)
            break
    shift_code = (request.args.get('shift_code') or request.args.get('shift') or '').strip()
    report = build_pos_price_edited_report(
        location_code_int,
        from_date=from_d,
        to_date=to_d,
        counter_code=counter_code,
        shift_code=shift_code or None,
        db_key=None,
    )
    if not report.get('ok'):
        return jsonify({'success': False, 'error': report.get('error') or 'Report failed'}, 400)
    return jsonify({'success': True, 'report': report})


@bp.route('/pos-billing/price-edited-report/export', methods=['GET'])
def pos_price_edited_report_export():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    location_code_int = _resolve_location_code()
    from_dt = (request.args.get('from') or '').strip()[:10]
    to_dt = (request.args.get('to') or '').strip()[:10]
    from_d = None
    to_d = None
    if from_dt:
        try:
            from_d = datetime.strptime(from_dt, '%Y-%m-%d').date()
        except ValueError:
            from_d = None
    if to_dt:
        try:
            to_d = datetime.strptime(to_dt, '%Y-%m-%d').date()
        except ValueError:
            to_d = None
    counter_code = None
    raw_cc = (request.args.get('counter_code') or request.args.get('countercode') or '').strip()
    if raw_cc.isdigit() and int(raw_cc) > 0:
        counter_code = int(raw_cc)
    shift_code = (request.args.get('shift_code') or request.args.get('shift') or '').strip()
    report = build_pos_price_edited_report(
        location_code_int,
        from_date=from_d,
        to_date=to_d,
        counter_code=counter_code,
        shift_code=shift_code or None,
    )
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Bill No', 'Bill Date', 'Counter', 'Cashier', 'Sl', 'Item Code', 'Item Name', 'UOM', 'Qty', 'Original Price', 'Edited Price', 'Difference', 'Line Impact'])
    for r in report.get('rows') or []:
        writer.writerow([
            r.get('billno') or '',
            r.get('billdate') or '',
            r.get('countercode') or '',
            r.get('createdby') or '',
            r.get('slno') or '',
            r.get('itemcode') or '',
            r.get('itemname') or '',
            r.get('uom') or '',
            r.get('quantity') or '',
            r.get('original_rate') or '',
            r.get('edited_rate') or '',
            r.get('rate_diff') or '',
            r.get('line_impact') or '',
        ])
    output.seek(0)
    filename = f"pos_price_edited_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename="{filename}"'})


@bp.route('/pos-billing/validate-pos-date-closed', methods=['GET'])
def pos_validate_pos_date_closed_api():
    """Check Counter Operations shift is closed for counter + POS date range before loading sales."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    location_code_int = _resolve_location_code()
    loc_raw = (request.args.get('location_code') or '').strip()
    if loc_raw.isdigit():
        location_code_int = int(loc_raw)
    from_dt = (request.args.get('from') or '').strip()[:10]
    to_dt = (request.args.get('to') or '').strip()[:10]
    from_d = None
    to_d = None
    if from_dt:
        try:
            from_d = datetime.strptime(from_dt, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'success': False, 'error': 'Invalid from date (YYYY-MM-DD)'}, 400)
    if to_dt:
        try:
            to_d = datetime.strptime(to_dt, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'success': False, 'error': 'Invalid to date (YYYY-MM-DD)'}, 400)
    counter_code = None
    for _arg in ('counter_code', 'countercode'):
        raw = (request.args.get(_arg) or '').strip()
        if raw.isdigit() and int(raw) > 0:
            counter_code = int(raw)
            break
    shift_raw = (request.args.get('shift_code') or request.args.get('shift') or '').strip()
    result = validate_pos_counter_dates_closed_for_sales_load(
        location_code_int,
        counter_code,
        from_d,
        to_d,
        shift_code=shift_raw or None,
        db_key=None,
    )
    if not result.get('ok'):
        return jsonify({'success': False, 'error': result.get('error') or 'Validation failed'}, 400)
    return jsonify(
        {
            'success': True,
            'valid': bool(result.get('valid')),
            'message': result.get('message') or '',
            'counter_code': result.get('counter_code'),
            'unclosed_dates': result.get('unclosed_dates') or result.get('unclosed_items') or [],
            'unclosed_items': result.get('unclosed_items') or result.get('unclosed_dates') or [],
        }
    )


@bp.route('/pos-billing/settlement-posting/api/counters', methods=['GET'])
def pos_settlement_posting_api_counters():
    """Counters from ``COUNTER`` / POS setup for the branch (tenant DB). Used by settlement posting counter picker."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    location_code_int = _resolve_location_code()
    loc_raw = (request.args.get('location_code') or '').strip()
    if loc_raw.isdigit():
        location_code_int = int(loc_raw)
    try:
        rows = list_pos_counters_for_location(location_code_int, user_dbkey) or []
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}, 500)
    out: List[Dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        cc = r.get('countercode')
        nm = str(r.get('countername') or '').strip()
        try:
            cci = int(cc)
        except (TypeError, ValueError):
            continue
        out.append({'countercode': cci, 'countername': nm})
    return jsonify({'success': True, 'counters': out, 'location_code': location_code_int})


@bp.route('/pos-billing/settlement-posting/api/bills', methods=['GET'])
def pos_settlement_posting_api_bills():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    location_code_int = _resolve_location_code()
    loc_raw = (request.args.get('location_code') or '').strip()
    if loc_raw.isdigit():
        location_code_int = int(loc_raw)
    try:
        lim = int(request.args.get('limit', 500))
    except (TypeError, ValueError):
        lim = 500
    from_dt = (request.args.get('from') or '').strip()
    to_dt = (request.args.get('to') or '').strip()
    settlement_scope = (request.args.get('settlement_scope') or 'all').strip().lower()
    if settlement_scope not in ('all', 'pending', 'settled', 'cancelled'):
        settlement_scope = 'all'
    inc_cred_raw = (request.args.get('include_credit') or '').strip().lower()
    include_credit_sales = inc_cred_raw in ('1', 'true', 'yes', 'y', 'all')
    fast_raw = (request.args.get('fast') or '1').strip().lower()
    fast = fast_raw not in ('0', 'false', 'no', 'off')
    t0 = time.perf_counter()
    try:
        raw_rows = _fetch_pos_settlement_candidate_bills(
            location_code_int,
            limit=lim,
            settlement_scope=settlement_scope,
            include_credit_sales=include_credit_sales,
            from_dt=from_dt,
            to_dt=to_dt,
            fast=fast,
        )
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}, 500)
    tender_by_bill = settlement_tender_amounts_by_bill(location_code_int, raw_rows or [])
    bills: List[Dict[str, Any]] = []
    for r in raw_rows or []:
        if not isinstance(r, dict):
            continue
        bill = _billhdr_row_to_settlement_bill(r)
        try:
            bn = int(bill.get('billNo') or 0)
        except (TypeError, ValueError):
            bn = 0
        if bn > 0:
            bill['tenderAmounts'] = tender_by_bill.get(bn) or {}
        else:
            bill['tenderAmounts'] = {}
        bills.append(bill)
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 1)
    _pos_timing_log('settlement_api_bills', t0, rows=len(bills), fast=int(fast), loc=location_code_int)
    return jsonify(
        {
            'success': True,
            'bills': bills,
            'location_code': location_code_int,
            'settlement_scope': settlement_scope,
            'include_credit_sales': include_credit_sales,
            'fast': fast,
            'elapsed_ms': elapsed_ms,
        }
    )


@bp.route('/pos-billing/settlement-posting/api/update-status', methods=['POST'])
def pos_settlement_posting_api_update_status():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    location_code_int = _resolve_location_code()
    loc_raw = (request.args.get('location_code') or '').strip()
    if loc_raw.isdigit():
        location_code_int = int(loc_raw)
    payload = request.get_json(silent=True) or {}
    bill_nos = payload.get('bill_nos') if isinstance(payload.get('bill_nos'), list) else payload.get('billnos')
    if bill_nos is None:
        bill_nos = []
    status_raw = str(payload.get('status') or '').strip().upper()
    status_map = {'POSTED': 'SETTLED', 'SETTLED': 'SETTLED', 'PENDING': 'PENDING', 'CANCELLED': 'CANCELLED'}
    st = status_map.get(status_raw, '')
    if not st:
        return jsonify({'success': False, 'error': 'Invalid status (use SETTLED, PENDING, or CANCELLED).'}, 400)
    voucher_no = str(payload.get('voucher_no') or '').strip()
    remarks = str(payload.get('remarks') or '').strip()
    ok, err = update_billhdr_pos_settlement_posting(location_code_int, bill_nos, status=st, voucher_no=voucher_no, remarks=remarks)
    if not ok:
        return jsonify({'success': False, 'error': err or 'Update failed'}, 400)
    return jsonify({'success': True, 'location_code': location_code_int, 'status': st})


@bp.route('/pos-billing/settlement-posting/api/coa', methods=['GET'])
def pos_settlement_posting_api_coa():
    """Active chart-of-accounts rows for settlement account pickers (tenant DB)."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    try:
        rows = get_all_chart_of_accounts() or []
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}, 500)
    accounts: List[Dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        if str(r.get('status') or 'ACTIVE').strip().upper() != 'ACTIVE':
            continue
        code = str(r.get('code') or '').strip()
        if not code:
            continue
        accounts.append(
            {
                'code': code[:20],
                'name': str(r.get('name') or '').strip()[:200],
                'type': str(r.get('type') or '').strip()[:40],
                'parent_code': str(r.get('parent_code') or '').strip()[:20],
                'parent_name': str(r.get('parent_name') or '').strip()[:200],
                'is_postable': bool(r.get('is_postable')),
            }
        )
    accounts.sort(key=lambda x: str(x.get('code') or ''))
    return jsonify({'success': True, 'accounts': accounts})


@bp.route('/pos-billing/settlement-posting/api/tender-defaults', methods=['GET'])
def pos_settlement_posting_api_tender_defaults():
    """Settlement GL defaults: clearing from active POS tenders + fixed ``sales_acc`` (see ``_pos_settlement_default_sales_account_code``)."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    try:
        defs = get_pos_settlement_account_defaults_from_tenders()
        defs['tender_gl_by_code'] = get_pos_tender_gl_by_code(active_only=True)
        tender_rows = list_pos_tender_types(active_only=True) or []
        defs['tender_types'] = [
            {
                'code': str(tr.get('tender_code') or '').strip().upper(),
                'name': str(tr.get('tender_name') or '').strip(),
                'sort_order': int(tr.get('sort_order') or 0),
            }
            for tr in tender_rows
            if str(tr.get('tender_code') or '').strip()
        ]
        return jsonify({'success': True, 'accounts': defs})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}, 500)


@bp.route('/pos-billing/settlement-posting/api/payment-mode-summary', methods=['POST'])
def pos_settlement_posting_api_payment_mode_summary():
    """Payment mode totals for selected bills: amounts match settlement draft logic; labels from ``POS_TENDER_TYPE``."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    location_code_int = _resolve_location_code()
    loc_raw = (request.args.get('location_code') or '').strip()
    if loc_raw.isdigit():
        location_code_int = int(loc_raw)
    payload = request.get_json(silent=True) or {}
    bill_nos = payload.get('bill_nos') if isinstance(payload.get('bill_nos'), list) else []
    try:
        summary = compute_pos_settlement_payment_mode_summary(location_code_int, bill_nos)
        return jsonify({'success': True, **summary})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}, 500)


@bp.route('/pos-billing/settlement-posting/api/drafts', methods=['GET'])
def pos_settlement_posting_api_drafts():
    """Recent POS settlement drafts for this branch (DRAFT / VERIFIED / POSTED)."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    location_code_int = _resolve_location_code()
    loc_raw = (request.args.get('location_code') or '').strip()
    if loc_raw.isdigit():
        location_code_int = int(loc_raw)
    try:
        lim = int(request.args.get('limit', 40))
    except (TypeError, ValueError):
        lim = 40
    try:
        drafts = list_pos_settlement_drafts(location_code_int, limit=lim)
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}, 500)
    return jsonify({'success': True, 'drafts': drafts, 'location_code': location_code_int})


@bp.route('/pos-billing/settlement-posting/api/pending-by-date', methods=['GET'])
def pos_settlement_posting_api_pending_by_date():
    """Pending POS bills grouped by bill date for the settlement list tab."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    location_code_int = _resolve_location_code()
    loc_raw = (request.args.get('location_code') or '').strip()
    if loc_raw.isdigit():
        location_code_int = int(loc_raw)
    try:
        lim = int(request.args.get('limit', 90))
    except (TypeError, ValueError):
        lim = 90
    try:
        days = list_pos_settlement_pending_by_date(location_code_int, limit_days=lim)
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}, 500)
    return jsonify({'success': True, 'days': days, 'location_code': location_code_int})


@bp.route('/pos-billing/settlement-posting/api/draft/generate', methods=['POST'])
def pos_settlement_posting_api_draft_generate():
    """Create a draft settlement row + journal lines from selected pending bills."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    location_code_int = _resolve_location_code()
    loc_raw = (request.args.get('location_code') or '').strip()
    if loc_raw.isdigit():
        location_code_int = int(loc_raw)
    payload = request.get_json(silent=True) or {}
    bill_nos = payload.get('bill_nos') if isinstance(payload.get('bill_nos'), list) else []
    accounts = payload.get('accounts') if isinstance(payload.get('accounts'), dict) else {}
    meta = payload.get('meta') if isinstance(payload.get('meta'), dict) else {}
    created_by = str(session.get('user') or '').strip()[:100]
    ok, err, draft_id = create_pos_settlement_draft(
        location_code_int,
        bill_nos,
        accounts=accounts,
        meta=meta,
        created_by=created_by,
    )
    if not ok:
        return jsonify({'success': False, 'error': err or 'Draft create failed'}, 400)
    detail = get_pos_settlement_draft_detail(int(draft_id or 0), location_code_int)
    return jsonify({'success': True, 'draft_id': draft_id, 'detail': detail, 'location_code': location_code_int})


@bp.route('/pos-billing/settlement-posting/api/draft/mutation', methods=['POST'])
def pos_settlement_posting_api_draft_mutation():
    """Verify or post a settlement draft (JSON body: action, draft_id, …)."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    location_code_int = _resolve_location_code()
    loc_raw = (request.args.get('location_code') or '').strip()
    if loc_raw.isdigit():
        location_code_int = int(loc_raw)
    payload = request.get_json(silent=True) or {}
    action = str(payload.get('action') or '').strip().lower()
    try:
        draft_id = int(payload.get('draft_id') or 0)
    except (TypeError, ValueError):
        draft_id = 0
    if draft_id <= 0:
        return jsonify({'success': False, 'error': 'Invalid draft_id'}, 400)
    created_by = str(session.get('user') or '').strip()[:50]
    if action == 'get':
        detail = get_pos_settlement_draft_detail(draft_id, location_code_int)
        if not detail:
            return jsonify({'success': False, 'error': 'Draft not found for this branch.'}, 404)
        bill_nos = detail.get('bill_nos') if isinstance(detail.get('bill_nos'), list) else []
        bills: List[Dict[str, Any]] = []
        try:
            # Draft open must load the exact draft bills (no credit / eligibility filters).
            raw_rows = _fetch_billhdr_rows_by_billnos(location_code_int, bill_nos)
            tender_by_bill = settlement_tender_amounts_by_bill(location_code_int, raw_rows or [])
            for r in raw_rows or []:
                if not isinstance(r, dict):
                    continue
                bill = _billhdr_row_to_settlement_bill(r)
                try:
                    bn = int(bill.get('billNo') or 0)
                except (TypeError, ValueError):
                    bn = 0
                bill['tenderAmounts'] = (tender_by_bill.get(bn) or {}) if bn > 0 else {}
                bills.append(bill)
        except Exception as exc:
            return jsonify({'success': False, 'error': f'Could not load draft bills: {exc}'}, 500)
        return jsonify({
            'success': True,
            'detail': detail,
            'bills': bills,
            'bill_nos': bill_nos,
            'location_code': location_code_int,
        })
    if action == 'verify':
        ok, err = verify_pos_settlement_draft(draft_id, location_code_int)
        if not ok:
            return jsonify({'success': False, 'error': err or 'Verify failed'}, 400)
        detail = get_pos_settlement_draft_detail(draft_id, location_code_int)
        return jsonify({'success': True, 'detail': detail})
    if action == 'cancel':
        ok, err = cancel_pos_settlement_draft(draft_id, location_code_int)
        if not ok:
            return jsonify({'success': False, 'error': err or 'Cancel failed'}, 400)
        detail = get_pos_settlement_draft_detail(draft_id, location_code_int)
        return jsonify({'success': True, 'detail': detail})
    if action == 'post':
        if not _try_acquire_pos_settlement_post_lock():
            return json_response_rotate_pos(
                {'success': False, 'error': 'A settlement post is already in progress for this session. Please wait.', 'save_session_locked': True},
                423,
            )
        try:
            submitted_nonce = extract_submitted_save_nonce(request)
            if not reject_invalid_pos_save_nonce(submitted_nonce):
                return replay_blocked_response_pos()
            voucher_date = str(payload.get('voucher_date') or '').strip()[:10] or None
            narration_extra = str(payload.get('narration_extra') or '').strip()[:500]
            remarks_bills = str(payload.get('remarks') or payload.get('remarks_bills') or '').strip()[:500]
            cc = str(payload.get('cost_center') or '').strip()[:40]
            dimension_defaults: Optional[Dict[str, Any]] = None
            if cc:
                dimension_defaults = {'cost_center': cc}
            try:
                from addons.accounts.period_closing_db import is_period_closed_for_date
                _pc_msg = is_period_closed_for_date(voucher_date, location_code_int)
                if _pc_msg:
                    return json_response_rotate_pos({'success': False, 'error': _pc_msg}, 400)
            except Exception:
                pass
            if not commit_pos_save_nonce(submitted_nonce):
                return replay_blocked_response_pos()
            ok, err, voucher_no = post_pos_settlement_draft(
                draft_id,
                location_code_int,
                voucher_date=voucher_date,
                narration_extra=narration_extra,
                remarks_bills=remarks_bills,
                created_by=created_by,
                dimension_defaults=dimension_defaults,
            )
            if not ok:
                body: Dict[str, Any] = {'success': False, 'error': err or 'Post failed'}
                if voucher_no:
                    body['voucher_no'] = voucher_no
                return json_response_rotate_pos(body, 400)
            detail = get_pos_settlement_draft_detail(draft_id, location_code_int)
            return json_response_rotate_pos(
                {'success': True, 'voucher_no': voucher_no, 'detail': detail, 'location_code': location_code_int},
            )
        finally:
            _release_pos_settlement_post_lock()
    return jsonify({'success': False, 'error': 'Invalid action (use get, verify, cancel, or post).'}, 400)


@bp.route('/pos-billing/settlement-posting/api/settlement-reverse-gl', methods=['POST'])
def pos_settlement_posting_api_settlement_reverse_gl():
    """Reverse GL vouchers linked to selected posted bills, then reset settlement to pending."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    if not _try_acquire_pos_settlement_reverse_lock():
        return json_response_rotate_pos(
            {'success': False, 'error': 'A settlement reverse is already in progress for this session. Please wait.', 'save_session_locked': True},
            423,
        )
    try:
        submitted_nonce = extract_submitted_save_nonce(request)
        if not reject_invalid_pos_save_nonce(submitted_nonce):
            return replay_blocked_response_pos()
        location_code_int = _resolve_location_code()
        loc_raw = (request.args.get('location_code') or '').strip()
        if loc_raw.isdigit():
            location_code_int = int(loc_raw)
        payload = request.get_json(silent=True) or {}
        bill_nos = payload.get('bill_nos') if isinstance(payload.get('bill_nos'), list) else []
        remarks = str(payload.get('remarks') or '').strip()[:500]
        cc = str(payload.get('cost_center') or '').strip()[:40]
        dimension_defaults: Optional[Dict[str, Any]] = None
        if cc:
            dimension_defaults = {'cost_center': cc}
        created_by = str(session.get('user') or '').strip()[:50]
        if not commit_pos_save_nonce(submitted_nonce):
            return replay_blocked_response_pos()
        ok, err, rev_list = reverse_pos_settlement_gl_journal(
            location_code_int,
            bill_nos,
            remarks=remarks,
            created_by=created_by,
            dimension_defaults=dimension_defaults,
        )
        if not ok:
            return json_response_rotate_pos({'success': False, 'error': err or 'Reverse failed'}, 400)
        return json_response_rotate_pos({'success': True, 'reversal_vouchers': rev_list, 'location_code': location_code_int})
    finally:
        _release_pos_settlement_reverse_lock()


@bp.route('/pos-billing/bills/detail', methods=['GET'])
def pos_bills_detail():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    tab = (request.args.get('tab') or 'posted').strip().lower()
    if tab not in ('posted', 'held', 'canceled'):
        return jsonify({'success': False, 'error': 'Invalid tab'}, 400)
    billno_raw = (request.args.get('billno') or '').strip()
    if not billno_raw.isdigit():
        return jsonify({'success': False, 'error': 'Invalid bill number'}, 400)
    billno = int(billno_raw)
    loc_raw = (request.args.get('location_code') or '').strip()
    if loc_raw.isdigit():
        location_code_int = int(loc_raw)
    else:
        location_code_int = _resolve_location_code()
    nls_lang = (request.headers.get('X-NLS-Lang') or request.args.get('nls_lang') or '').strip()
    receipt = get_pos_bill_receipt_for_tab(tab, billno, location_code_int, user_dbkey=session.get('tenant_id'), nls_lang=nls_lang or None)
    if not receipt:
        return jsonify({'success': False, 'error': 'Bill not found or not available for this tab'}, 404)
    receipt_text = ''
    if tab == 'held':
        ok_snap, _snap_err, snap = _pos_hold_cancel_slip_snapshot(location_code_int, billno)
        if ok_snap and snap:
            receipt_text = _build_pos_hold_cancel_slip_text(
                'HOLD',
                billno=billno,
                user=str(receipt.get('user') or session.get('user') or '').strip(),
                user_dbkey=session.get('tenant_id'),
                snapshot=snap,
            )
    elif tab == 'canceled':
        lines = receipt.get('lines') or []
        item_count = 0
        for line in lines:
            try:
                qty = float(line.get('qty') or 0)
            except (TypeError, ValueError):
                qty = 0.0
            if abs(qty) >= 1e-9:
                item_count += 1
        footer = receipt.get('footer') or {}
        try:
            amount_f = float(footer.get('net_total') or 0)
        except (TypeError, ValueError):
            amount_f = 0.0
        receipt_text = _build_pos_hold_cancel_slip_text(
            'CANCEL',
            billno=billno,
            user=str(receipt.get('user') or session.get('user') or '').strip(),
            user_dbkey=session.get('tenant_id'),
            snapshot={'billno': billno, 'amount': round(amount_f, 2), 'item_count': item_count},
        )
    if not receipt_text:
        design = load_receipt_design()
        receipt_text = _receipt_to_plain_text(receipt, design, include_copy_banner=(tab == 'posted'))
    return jsonify({'success': True, 'tab': tab, 'billno': billno, 'location_code': location_code_int, 'receipt': receipt, 'receipt_text': receipt_text})


@bp.route('/pos-billing/receipt-design')
def pos_receipt_design_page():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    config = load_receipt_design()
    return render_template('pos_billing/pos_receipt_design.html', config=config)
DEMO_RECEIPT = {'location_details': {'locationname': 'OTO Restaurant', 'locationcode': 1}, 'receiptno': '9', 'user': 'kapp', 'billdate': '10/10/2022', 'billtime': '21:02:48', 'customername': 'Klaxy', 'lines': [{'slno': 1, 'item': 'Hot Chocolate', 'item_ara': 'شوكولاتة ساخنة', 'uom': 'CUP', 'qty': 3, 'rate': 5000, 'amount': 15000}, {'slno': 2, 'item': 'Cappuccino', 'item_ara': 'قهوة بحلب', 'uom': 'CUP', 'qty': 1, 'rate': 3500, 'amount': 3500}, {'slno': 3, 'item': 'Americano', 'item_ara': '', 'uom': 'PCS', 'qty': 5, 'rate': 3000, 'amount': 15000}, {'slno': 4, 'item': 'Chicken Pulao', 'item_ara': 'بيلاو دجاج', 'uom': 'PLT', 'qty': 1, 'rate': 12000, 'amount': 12000}], 'footer': {'net_total': 45500, 'discount_total': 0, 'message': 'Thank you.'}}

@bp.route('/pos-billing/receipt-design/printers', methods=['GET'])
def pos_receipt_design_printers():
    """Return list of installed printer names (Windows). Use one as receipt printer so thermal works while A4 stays default."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    printers = _list_printers()
    default = ''
    if sys.platform == 'win32':
        try:
            import win32print
            default = win32print.GetDefaultPrinter() or ''
        except Exception:
            pass
    return jsonify({'success': True, 'printers': printers, 'default_printer': default})

@bp.route('/pos-billing/receipt-design/printer-paper-size', methods=['GET'])
def pos_receipt_design_printer_paper_size():
    """Return default printer name and paper size. Uses design paper_width_mm (default 80mm) when printer does not report size."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    design = load_receipt_design()
    paper_width_mm = max(58, min(120, int(design.get('paper_width_mm') or 80)))
    result = _get_default_printer_paper_size()
    if result is None:
        return jsonify({'success': True, 'printer_name': None, 'width_mm': paper_width_mm, 'length_mm': 0, 'size_label': '%s mm (3.15" wide) – from design (printer size not reported)' % paper_width_mm, 'from_design': True})
    printer_name, width_mm, length_mm = result
    if not width_mm and (not length_mm):
        width_mm = paper_width_mm
        size_label = '%s mm (3.15" wide) – from design (printer did not report size)' % paper_width_mm
        from_design = True
    else:
        size_label = '%s × %s mm' % (width_mm or paper_width_mm, length_mm)
        from_design = False
    return jsonify({'success': True, 'printer_name': printer_name, 'width_mm': width_mm or paper_width_mm, 'length_mm': length_mm, 'size_label': size_label, 'from_design': from_design})

@bp.route('/pos-billing/receipt-design/test-print', methods=['POST'])
def pos_receipt_design_test_print():
    """Print a test receipt using current (or posted) design and demo data."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    payload = request.get_json(silent=True) or {}
    config = dict(DEFAULT_RECEIPT_DESIGN)
    if 'page_width' in payload:
        try:
            config['page_width'] = max(24, min(80, int(payload['page_width'])))
        except (TypeError, ValueError):
            config['page_width'] = RECEIPT_WIDTH
    for section in ('header', 'bill', 'items', 'summary', 'footer'):
        if section in payload and isinstance(payload[section], dict):
            config[section] = {**config.get(section, {}), **payload[section]}
    if 'labels' in payload and isinstance(payload['labels'], dict):
        config['labels'] = {**config.get('labels', {}), **payload['labels']}
    if 'output_encoding' in payload and isinstance(payload['output_encoding'], str):
        enc = payload['output_encoding'].strip().lower()
        config['output_encoding'] = 'cp1256' if enc in ('cp1256', 'windows-1256', 'arabic') else 'utf-8'
    if 'nls_lang' in payload and isinstance(payload['nls_lang'], str):
        config['nls_lang'] = payload['nls_lang'].strip()
    if 'escpos_left_align' in payload:
        config['escpos_left_align'] = bool(payload['escpos_left_align'])
    if 'paper_width_mm' in payload:
        try:
            config['paper_width_mm'] = max(58, min(120, int(payload['paper_width_mm'])))
        except (TypeError, ValueError):
            config['paper_width_mm'] = 80
    if 'receipt_printer_name' in payload and isinstance(payload['receipt_printer_name'], str):
        config['receipt_printer_name'] = payload['receipt_printer_name'].strip()
    if 'receipt_printer_ip' in payload and isinstance(payload['receipt_printer_ip'], str):
        config['receipt_printer_ip'] = payload['receipt_printer_ip'].strip()
    demo_receipt = dict(DEMO_RECEIPT)
    demo_receipt['location_details'] = enrich_location_details_with_branch_logo(
        demo_receipt.get('location_details') or {},
        _resolve_location_code(),
    )
    print_ok, print_err = _print_receipt_to_default_printer(demo_receipt, config)
    if print_ok:
        return jsonify({'success': True, 'receipt_printed': True})
    return jsonify({'success': False, 'error': print_err or 'Print failed'}, 500)

@bp.route('/pos-billing/receipt-design/config', methods=['GET', 'POST'])
def pos_receipt_design_config():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    if request.method == 'GET':
        config = load_receipt_design()
        return jsonify({'success': True, 'config': config})
    payload = request.get_json(silent=True) or {}
    config = dict(DEFAULT_RECEIPT_DESIGN)
    if 'page_width' in payload:
        try:
            config['page_width'] = max(24, min(80, int(payload['page_width'])))
        except (TypeError, ValueError):
            config['page_width'] = RECEIPT_WIDTH
    for section in ('header', 'bill', 'items', 'summary', 'footer'):
        if section in payload and isinstance(payload[section], dict):
            config[section] = {**config.get(section, {}), **payload[section]}
    if 'labels' in payload and isinstance(payload['labels'], dict):
        config['labels'] = {**config.get('labels', {}), **payload['labels']}
    if 'output_encoding' in payload and isinstance(payload['output_encoding'], str):
        enc = payload['output_encoding'].strip().lower()
        config['output_encoding'] = 'cp1256' if enc in ('cp1256', 'windows-1256', 'arabic') else 'utf-8'
    if 'nls_lang' in payload and isinstance(payload['nls_lang'], str):
        config['nls_lang'] = payload['nls_lang'].strip()
    if 'escpos_left_align' in payload:
        config['escpos_left_align'] = bool(payload['escpos_left_align'])
    if 'paper_width_mm' in payload:
        try:
            config['paper_width_mm'] = max(58, min(120, int(payload['paper_width_mm'])))
        except (TypeError, ValueError):
            config['paper_width_mm'] = 80
    if 'receipt_printer_name' in payload and isinstance(payload['receipt_printer_name'], str):
        config['receipt_printer_name'] = payload['receipt_printer_name'].strip()
    if 'receipt_printer_ip' in payload and isinstance(payload['receipt_printer_ip'], str):
        config['receipt_printer_ip'] = payload['receipt_printer_ip'].strip()
    if save_receipt_design(config):
        return jsonify({'success': True, 'config': config})
    return jsonify({'success': False, 'error': 'Failed to save'}, 500)


@bp.route('/pos-billing/next-billno', methods=['GET'])
def pos_next_billno():
    """Display-only next bill number. POS checkout reserves via last-in-progress-bill (TEMPBILLHDR)."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    countercode = _countercode_query_optional()
    location_code_int = _resolve_location_code()
    peek_only = (request.args.get('reserve') or '').strip().lower() not in ('1', 'true', 'yes')
    if peek_only:
        next_billno = peek_next_bill_no(location_code_int, countercode, doc_type=DOC_TYPE_POS_INVOICE)
        return jsonify({'success': True, 'billno': next_billno, 'reserved': False})
    try:
        next_billno = get_next_bill_no(location_code_int, countercode, doc_type=DOC_TYPE_POS_INVOICE)
    except RuntimeError as e:
        return jsonify({'success': False, 'error': str(e)}, 503)
    return jsonify({'success': True, 'billno': next_billno, 'reserved': True})

_POS_SCAN_LOOKUP_SQL = """
            SELECT * FROM (
                SELECT x.* FROM (
                    SELECT
                        1 AS match_priority,
                        im.ITEMCODE AS itemcode,
                        im.RAWABICODE AS rawabicode,
                        im.ITEMNAME AS itemname,
                        NVL(NULLIF(TRIM(alt.MANUFACTURERID), ''), im.MANUFACTURERID) AS manufacturerid,
                        im.BASEUOM AS baseuom,
                        im.COSTPRICE AS costprice,
                        im.RETAILPRICE AS retailprice,
                        im.WHOLESALEPRICE AS wholesaleprice,
                        im.THIRDPRICE AS thirdprice,
                        im.BRANCHPRICE AS branchprice,
                        im.VATPERCENT AS vatpercent,
                        im.ITEMFLAG AS itemflag,
                        NVL(alt.ALTERNATEUOMCODE, im.BASEUOM) AS barcode_uom,
                        NVL(alt.RETAILPRICE, im.RETAILPRICE) AS barcode_retail_price
                    FROM ITEMALTERNATEUOMMAP alt
                    JOIN ITEMMASTER im
                      ON im.LOCATIONCODE = alt.LOCATIONCODE
                     AND im.ITEMCODE = alt.ITEMCODE
                    WHERE alt.LOCATIONCODE = :loc
                      AND UPPER(TRIM(NVL(TO_CHAR(alt.MANUFACTURERID), ''))) = UPPER(TRIM(:query))
                    UNION ALL
                    SELECT
                        2 AS match_priority,
                        im.ITEMCODE AS itemcode,
                        im.RAWABICODE AS rawabicode,
                        im.ITEMNAME AS itemname,
                        im.MANUFACTURERID AS manufacturerid,
                        im.BASEUOM AS baseuom,
                        im.COSTPRICE AS costprice,
                        im.RETAILPRICE AS retailprice,
                        im.WHOLESALEPRICE AS wholesaleprice,
                        im.THIRDPRICE AS thirdprice,
                        im.BRANCHPRICE AS branchprice,
                        im.VATPERCENT AS vatpercent,
                        im.ITEMFLAG AS itemflag,
                        NVL(im.BASEUOM, 'PCS') AS barcode_uom,
                        NVL(im.RETAILPRICE, 0) AS barcode_retail_price
                    FROM ITEMMASTER im
                    WHERE im.LOCATIONCODE = :loc
                      AND UPPER(TRIM(NVL(TO_CHAR(im.MANUFACTURERID), ''))) = UPPER(TRIM(:query))
                    UNION ALL
                    SELECT
                        3 AS match_priority,
                        im.ITEMCODE AS itemcode,
                        im.RAWABICODE AS rawabicode,
                        im.ITEMNAME AS itemname,
                        im.MANUFACTURERID AS manufacturerid,
                        im.BASEUOM AS baseuom,
                        im.COSTPRICE AS costprice,
                        im.RETAILPRICE AS retailprice,
                        im.WHOLESALEPRICE AS wholesaleprice,
                        im.THIRDPRICE AS thirdprice,
                        im.BRANCHPRICE AS branchprice,
                        im.VATPERCENT AS vatpercent,
                        im.ITEMFLAG AS itemflag,
                        NVL(im.BASEUOM, 'PCS') AS barcode_uom,
                        NVL(im.RETAILPRICE, 0) AS barcode_retail_price
                    FROM ITEMMASTER im
                    WHERE im.LOCATIONCODE = :loc
                      AND REGEXP_LIKE(TRIM(:query), '^[0-9]+$')
                      AND (
                          (:query_num IS NOT NULL AND im.ITEMCODE = :query_num)
                          OR TRIM(TO_CHAR(im.ITEMCODE)) = TRIM(:query)
                      )
                    UNION ALL
                    SELECT
                        4 AS match_priority,
                        im.ITEMCODE AS itemcode,
                        im.RAWABICODE AS rawabicode,
                        im.ITEMNAME AS itemname,
                        im.MANUFACTURERID AS manufacturerid,
                        im.BASEUOM AS baseuom,
                        im.COSTPRICE AS costprice,
                        im.RETAILPRICE AS retailprice,
                        im.WHOLESALEPRICE AS wholesaleprice,
                        im.THIRDPRICE AS thirdprice,
                        im.BRANCHPRICE AS branchprice,
                        im.VATPERCENT AS vatpercent,
                        im.ITEMFLAG AS itemflag,
                        NVL(im.BASEUOM, 'PCS') AS barcode_uom,
                        NVL(im.RETAILPRICE, 0) AS barcode_retail_price
                    FROM ITEMMASTER im
                    WHERE im.LOCATIONCODE = :loc
                      AND LENGTH(TRIM(:query_name)) >= 2
                      AND UPPER(TRIM(im.ITEMNAME)) = UPPER(TRIM(:query_name))
                    UNION ALL
                    SELECT
                        5 AS match_priority,
                        im.ITEMCODE AS itemcode,
                        im.RAWABICODE AS rawabicode,
                        im.ITEMNAME AS itemname,
                        im.MANUFACTURERID AS manufacturerid,
                        im.BASEUOM AS baseuom,
                        im.COSTPRICE AS costprice,
                        im.RETAILPRICE AS retailprice,
                        im.WHOLESALEPRICE AS wholesaleprice,
                        im.THIRDPRICE AS thirdprice,
                        im.BRANCHPRICE AS branchprice,
                        im.VATPERCENT AS vatpercent,
                        im.ITEMFLAG AS itemflag,
                        NVL(im.BASEUOM, 'PCS') AS barcode_uom,
                        NVL(im.RETAILPRICE, 0) AS barcode_retail_price
                    FROM ITEMMASTER im
                    WHERE im.LOCATIONCODE = :loc
                      AND LENGTH(TRIM(:query_name)) >= 3
                      AND UPPER(TRIM(im.ITEMNAME)) LIKE UPPER(TRIM(:query_name)) || '%'
                      AND UPPER(TRIM(im.ITEMNAME)) <> UPPER(TRIM(:query_name))
                    UNION ALL
                    SELECT
                        6 AS match_priority,
                        im.ITEMCODE AS itemcode,
                        im.RAWABICODE AS rawabicode,
                        im.ITEMNAME AS itemname,
                        im.MANUFACTURERID AS manufacturerid,
                        im.BASEUOM AS baseuom,
                        im.COSTPRICE AS costprice,
                        im.RETAILPRICE AS retailprice,
                        im.WHOLESALEPRICE AS wholesaleprice,
                        im.THIRDPRICE AS thirdprice,
                        im.BRANCHPRICE AS branchprice,
                        im.VATPERCENT AS vatpercent,
                        im.ITEMFLAG AS itemflag,
                        NVL(im.BASEUOM, 'PCS') AS barcode_uom,
                        NVL(im.RETAILPRICE, 0) AS barcode_retail_price
                    FROM ITEMMASTER im
                    WHERE im.LOCATIONCODE = :loc
                      AND LENGTH(TRIM(:query_name)) >= 5
                      AND UPPER(TRIM(im.ITEMNAME)) LIKE '%' || UPPER(TRIM(:query_name)) || '%'
                      AND UPPER(TRIM(im.ITEMNAME)) NOT LIKE UPPER(TRIM(:query_name)) || '%'
                ) x
                ORDER BY x.match_priority, LENGTH(TRIM(x.itemname))
            )
            WHERE ROWNUM = 1
            """


def _pos_query_name_bind(query: str) -> str:
    """Strip LIKE wildcards from a name query so ITEMNAME branches stay safe."""
    q = re.sub(r'[%_\\]', '', (query or '').strip())
    return q[:200] if q else ''


def _pos_lookup_item_row(location_code_int: int, query: str) -> Optional[Dict[str, Any]]:
    """Resolve scan/query via ITEMMASTER (MANUFACTURERID, ITEMCODE, ITEMNAME) and ITEMALTERNATEUOMMAP (MANUFACTURERID)."""
    query = (query or '').strip()
    if not query:
        return None
    query_num = None
    if query.isdigit():
        try:
            query_num = int(query)
        except (TypeError, ValueError):
            query_num = None
    query_name = _pos_query_name_bind(query)
    try:
        rows = _safe_rows(
            _POS_SCAN_LOOKUP_SQL,
            {'loc': location_code_int, 'query': query, 'query_num': query_num, 'query_name': query_name},
        )
    except Exception:
        return None
    if not rows:
        return None
    item_data = dict(rows[0])
    wh_ctx = _pos_session_warehouse_context()
    pos_store = wh_ctx.get('store')
    pos_wh_id = wh_ctx.get('warehouse_id')
    item_defaults: Dict[str, Any] = {}
    try:
        item_defaults = get_item_by_code(int(item_data.get('itemcode') or 0), location_code_int) or {}
        if pos_store:
            item_data['store'] = pos_store
            item_data['default_store'] = pos_store
        else:
            item_data['store'] = (item_defaults.get('store') or 'STORE1')
        if pos_wh_id and item_defaults.get('default_bin_storage_id'):
            item_data['default_bin_storage_id'] = item_defaults.get('default_bin_storage_id')
        elif pos_wh_id:
            bins = list_warehouse_picker_bins(str(pos_wh_id)) or []
            first_bin = next((b for b in bins if str((b or {}).get('status') or 'ACTIVE').strip().upper() == 'ACTIVE'), None)
            if first_bin:
                try:
                    item_data['default_bin_storage_id'] = int(float(first_bin.get('storage_id') or 0)) or None
                except (TypeError, ValueError):
                    pass
        else:
            item_data['default_bin_storage_id'] = item_defaults.get('default_bin_storage_id')
        item_data['batch_tracked'] = item_defaults.get('batch_tracked') or 'N'
    except Exception:
        item_data['store'] = pos_store or item_data.get('store') or 'STORE1'
        item_data['default_bin_storage_id'] = item_data.get('default_bin_storage_id')
        item_data['batch_tracked'] = item_data.get('batch_tracked') or 'N'
    item_data['baseuom'] = (item_data.get('baseuom') or '').strip() or 'PCS'
    item_data['barcode_uom'] = (item_data.get('barcode_uom') or item_data['baseuom'] or 'PCS').strip()
    item_data['barcode_retail_price'] = float(item_data.get('barcode_retail_price') or item_data.get('retailprice') or 0)
    item_data['costprice'] = float(item_data.get('costprice') or 0)
    item_data['averagecost'] = 0.0
    item_data['item_factor'] = 1.0
    try:
        avg_rows = _safe_rows(
            'SELECT NVL(AVERAGECOST, 0) AS averagecost, NVL(COSTPRICE, 0) AS costprice FROM ITEMMASTER WHERE LOCATIONCODE = :loc AND ITEMCODE = :itemcode',
            {'loc': location_code_int, 'itemcode': item_data.get('itemcode')},
        ) or []
        if avg_rows:
            item_data['averagecost'] = float(avg_rows[0].get('averagecost') or 0)
            item_data['costprice'] = float(avg_rows[0].get('costprice') or item_data['costprice'] or 0)
    except Exception:
        pass
    if item_data['barcode_uom'].upper() != item_data['baseuom'].upper():
        try:
            factor_rows = _safe_rows(
                '\n                SELECT NVL(CONVERSIONFACTOR, 1) AS item_factor, NVL(COSTPRICE, 0) AS alt_costprice\n                FROM ITEMALTERNATEUOMMAP\n                WHERE LOCATIONCODE = :loc\n                  AND ITEMCODE = :itemcode\n                  AND UPPER(TRIM(ALTERNATEUOMCODE)) = :uom\n            ',
                {'loc': location_code_int, 'itemcode': item_data.get('itemcode'), 'uom': item_data['barcode_uom'].upper()},
            ) or []
            if factor_rows:
                item_data['item_factor'] = float(factor_rows[0].get('item_factor') or 1)
                item_data['alt_costprice'] = float(factor_rows[0].get('alt_costprice') or 0)
        except Exception:
            pass
    item_data['conversion_factor'] = item_data['item_factor']
    try:
        cs_raw = item_defaults.get('CURRENTSTOCK') if item_defaults else None
        if cs_raw is None:
            cs_raw = item_defaults.get('currentstock') if item_defaults else None
        if pos_wh_id:
            wh_qty = get_item_warehouse_stock_qty(location_code_int, int(pos_wh_id), int(item_data.get('itemcode') or 0))
            item_data['currentstock'] = float(wh_qty if wh_qty is not None else 0)
        else:
            item_data['currentstock'] = float(cs_raw or 0)
    except Exception:
        item_data['currentstock'] = 0.0
    try:
        rp_sys = item_defaults.get('RETAILPRICE') if item_defaults else None
        if rp_sys is None and item_defaults:
            rp_sys = item_defaults.get('retailprice')
        if rp_sys is None:
            rp_sys = item_data.get('retailprice')
        item_data['system_retail_price'] = float(rp_sys or 0)
    except Exception:
        item_data['system_retail_price'] = float(item_data.get('retailprice') or 0)
    return item_data


def _pos_ai_fallback_lines_from_text(text: str) -> List[Dict[str, Any]]:
    """When the model returns [] or unparseable JSON, derive barcode lines from plain pasted text (e.g. ``12481``)."""
    t = (text or '').strip()
    if not t:
        return []
    seen: set = set()
    out: List[Dict[str, Any]] = []

    def add_token(tok: str) -> None:
        tok = tok.strip()
        if not tok or len(tok) > 40:
            return
        if not re.match(r'^[A-Za-z0-9][A-Za-z0-9.\-]*$', tok):
            return
        k = tok.upper()
        if k in seen:
            return
        seen.add(k)
        out.append({'barcode': tok, 'qty': 1})

    collapsed = ''.join(t.split())
    if '\n' not in t and '\t' not in t and '\r' not in t:
        if re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.\-]{2,39}', collapsed):
            add_token(collapsed)
            return out

    for line in t.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = re.split(r'[\t,;|]+', line)
        first = parts[0].strip() if parts else ''
        if first:
            add_token(first)

    if not out:
        for m in re.finditer(r'\b\d{3,14}\b', t):
            add_token(m.group(0))

    return out


def _pos_ai_parse_json_array(text: str) -> List[Dict[str, Any]]:
    raw = (text or '').strip()
    if raw.startswith('```'):
        raw = re.sub(r'^```\w*\s*', '', raw, count=1)
        raw = re.sub(r'\s*```\s*$', '', raw, count=1)
    raw = raw.strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = None
        m = re.search(r'\[[\s\S]*\]', raw)
        if m:
            try:
                data = json.loads(m.group(0))
            except json.JSONDecodeError:
                data = None
        if data is None:
            mobj = re.search(r'\{[\s\S]*\}', raw)
            if not mobj:
                raise
            data = json.loads(mobj.group(0))
    if isinstance(data, dict):
        if 'lines' in data and isinstance(data['lines'], list):
            data = data['lines']
        else:
            data = [data]
    if not isinstance(data, list):
        raise ValueError('AI response is not a JSON array')
    out: List[Dict[str, Any]] = []
    for row in data:
        if isinstance(row, dict):
            out.append(row)
    return out


def _pos_queries_from_ai_row(row: Dict[str, Any]) -> List[str]:
    seen = set()
    ordered: List[str] = []
    for key in ('barcode', 'manufacturer_id', 'manufacturerid', 'ean', 'upc'):
        v = row.get(key)
        if v is None:
            continue
        s = str(v).strip()
        if not s:
            continue
        k = s.upper()
        if k not in seen:
            seen.add(k)
            ordered.append(s)
    ic = row.get('item_code')
    if ic is None:
        ic = row.get('itemcode')
    if ic is not None:
        s = str(ic).strip()
        if s:
            k = s.upper()
            if k not in seen:
                seen.add(k)
                ordered.append(s)
    for key in ('item_name', 'itemname', 'name', 'product_name', 'description', 'product'):
        v = row.get(key)
        if v is None:
            continue
        s = str(v).strip()
        if len(s) < 2:
            continue
        k = s.upper()
        if k not in seen:
            seen.add(k)
            ordered.append(s)
    return ordered


@bp.route('/pos-billing/item-info', methods=['GET'])
def pos_item_info():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    query = (request.args.get('query') or '').strip()
    if not query:
        return jsonify({'success': False, 'error': 'Missing query'}, 400)
    location_code_int = _resolve_location_code()
    try:
        item_data = _pos_lookup_item_row(location_code_int, query)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}, 500)
    if not item_data:
        return jsonify({'success': False, 'error': 'Item not found'}, 404)
    return jsonify({'success': True, 'item': item_data})


@bp.route('/pos-billing/ai-screenshot-lines', methods=['POST'])
def pos_ai_screenshot_lines():
    """Vision model reads a shelf/packing screenshot → barcodes; resolve via ITEMMASTER + ITEMALTERNATEUOMMAP."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    api_key = (os.environ.get('OPENAI_API_KEY') or '').strip()
    if not api_key:
        return jsonify({'success': False, 'error': 'OPENAI_API_KEY is not configured on the server.'}, 503)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    location_code_int = _resolve_location_code()

    max_bytes = 6 * 1024 * 1024
    max_text_chars = 32000
    raw: Optional[bytes] = None
    mime = 'image/png'
    upload_filename = ''
    f = request.files.get('image')
    if f:
        raw = f.read()
        ct = getattr(f, 'content_type', None) or getattr(f, 'mimetype', None) or ''
        mime = str(ct).strip() or mime
        upload_filename = str(getattr(f, 'filename', None) or '')
    else:
        payload_json = request.get_json(silent=True) or {}
        b64 = payload_json.get('image_base64')
        if isinstance(b64, str) and b64.strip():
            try:
                raw = base64.b64decode(b64.split(',', 1)[-1].strip())
            except Exception:
                return jsonify({'success': False, 'error': 'Invalid image_base64'}, 400)
            mime = str(payload_json.get('mime') or 'image/png').strip() or mime

    text_blob = ''
    if request.form:
        ft = request.form.get('text')
        if isinstance(ft, str) and ft.strip():
            text_blob = ft.strip()
    if not text_blob:
        payload_for_text = request.get_json(silent=True) or {}
        pt = payload_for_text.get('text')
        if isinstance(pt, str) and pt.strip():
            text_blob = pt.strip()
    if len(text_blob) > max_text_chars:
        text_blob = text_blob[:max_text_chars]

    if not raw and not text_blob:
        return jsonify(
            {
                'success': False,
                'error': 'Send image or PDF (multipart ``image`` or JSON ``image_base64``) and/or pasted ``text`` (form field or JSON ``text``).',
            },
            400,
        )

    if raw:
        if len(raw) > max_bytes:
            return jsonify({'success': False, 'error': f'Upload too large (max {max_bytes // (1024 * 1024)} MB).'}, 400)
        if _pos_upload_looks_like_pdf(mime, upload_filename) or _pos_bytes_looks_like_pdf(raw):
            png_out = _pos_pdf_first_page_to_png_bytes(raw, max_bytes_out=max_bytes)
            if not png_out:
                return jsonify(
                    {
                        'success': False,
                        'error': 'Could not convert PDF to image (invalid or password-protected PDF, or output too large). Try PNG/JPEG or a smaller PDF; only the first page is used.',
                    },
                    400,
                )
            raw = png_out
            mime = 'image/png'
        if len(raw) > max_bytes:
            return jsonify({'success': False, 'error': f'File too large after conversion (max {max_bytes // (1024 * 1024)} MB).'}, 400)
        if not mime.startswith('image/'):
            mime = 'image/jpeg'

    model = (os.environ.get('OPENAI_VISION_MODEL') or os.environ.get('OPENAI_MODEL') or 'gpt-4o-mini').strip()
    sys_prompt = (
        'You read retail product photos, POS screenshots, pasted receipt lines, spreadsheet fragments '
        '(tabs/commas/columns), or plain text lists. Extract distinct purchasable lines. '
        'For each line output JSON object with: '
        '"barcode" (string: visible machine-readable code — EAN/UPC when present, otherwise internal shelf/POS codes '
        'that match Oracle ITEMMASTER.MANUFACTURERID or ITEMCODE when printed), '
        '"item_code" (integer ERP item code ONLY if clearly printed as ITEMCODE/SKU number distinct from barcode), '
        '"item_name" (string: visible product name or description as printed — English or Arabic — used to find '
        'ITEMMASTER.ITEMNAME when barcode is missing or unclear; omit if unknown), '
        '"qty" (number, default 1). '
        'If the input is only one code (e.g. "12481"), output exactly one line with that value as "barcode". '
        'Never return an empty array [] when the pasted text contains any alphanumeric code or digit sequence '
        'that could be a SKU/barcode. '
        'Prefer explicit printed numbers for barcode; omit duplicate lines. '
        'Reply with ONLY valid JSON: an array [...]. No markdown, no commentary.'
    )
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, timeout=90.0)
        if raw:
            b64url = base64.b64encode(raw).decode('ascii')
            data_uri = f'data:{mime};base64,{b64url}'
            user_prompt = 'Extract line items from this image as specified.'
            if text_blob:
                user_prompt += (
                    '\n\nThe user also pasted this text (may overlap or add detail — merge sensibly, no duplicate lines):\n'
                    + text_blob
                )
            messages = [
                {'role': 'system', 'content': sys_prompt},
                {
                    'role': 'user',
                    'content': [
                        {'type': 'text', 'text': user_prompt},
                        {'type': 'image_url', 'image_url': {'url': data_uri}},
                    ],
                },
            ]
        else:
            messages = [
                {'role': 'system', 'content': sys_prompt},
                {
                    'role': 'user',
                    'content': (
                        'Extract line items from the pasted content below. It may be table columns, POS receipt lines, '
                        'SKU lists, or messy copy from Excel/email/browsers. Infer qty when obvious (default 1).\n'
                        'When a product title or description appears without a barcode, set "item_name" to that text '
                        '(server matches ITEMMASTER.ITEMNAME).\n'
                        'Return at least one JSON object whenever there is a visible code or number string (even a '
                        'single token like 12481).\n\n---\n\n'
                        + text_blob
                    ),
                },
            ]

        completion = client.chat.completions.create(
            model=model,
            temperature=0.1,
            messages=messages,
            max_tokens=1800,
        )
        ai_text = (completion.choices[0].message.content or '').strip()
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}, 500)

    parse_err: Optional[str] = None
    try:
        extracted = _pos_ai_parse_json_array(ai_text)
    except Exception as exc:
        extracted = []
        parse_err = str(exc)

    if not extracted and text_blob.strip():
        extracted = _pos_ai_fallback_lines_from_text(text_blob)

    if not extracted and parse_err:
        return jsonify({'success': False, 'error': f'Could not parse AI JSON: {parse_err}', 'raw_text': ai_text[:2000]}, 422)

    results: List[Dict[str, Any]] = []
    for row in extracted:
        qty_raw = row.get('qty')
        try:
            qty = float(qty_raw) if qty_raw is not None else 1.0
        except (TypeError, ValueError):
            qty = 1.0
        if qty <= 0:
            qty = 1.0
        if qty > 99999:
            qty = 99999.0

        queries = _pos_queries_from_ai_row(row)
        matched: Optional[Dict[str, Any]] = None
        query_used = ''
        for q in queries:
            hit = _pos_lookup_item_row(location_code_int, q)
            if hit:
                matched = hit
                query_used = q
                break
        if matched:
            results.append({'matched': True, 'qty': qty, 'query_used': query_used, 'ai': row, 'item': matched})
        else:
            results.append(
                {
                    'matched': False,
                    'qty': qty,
                    'queries_tried': queries,
                    'ai': row,
                    'item': None,
                }
            )

    return jsonify({'success': True, 'extracted': extracted, 'results': results})

@bp.route('/pos-billing/shop-categories', methods=['GET'])
def pos_shop_categories():
    """Category tabs for POS Shop (ITEMMASTER micro-categories)."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    location_code_int = _resolve_location_code()
    try:
        rows = get_categories('C', location_code=location_code_int) or []
        categories = []
        for r in rows:
            code = r.get('code')
            name = (r.get('name') or '').strip()
            if code is None or not name:
                continue
            categories.append({'code': int(code), 'name': name})
        return jsonify({'success': True, 'categories': categories})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}, 500)


@bp.route('/pos-billing/products', methods=['GET'])
def pos_products():
    """Return product list for POS catalog (search, pagination)."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    search = (request.args.get('search') or '').strip()
    category_code = None
    raw_cat = (request.args.get('category_code') or '').strip()
    if raw_cat and raw_cat.isdigit():
        category_code = int(raw_cat)
    try:
        page = int((request.args.get('page') or '1').strip())
    except (TypeError, ValueError):
        page = 1
    if page < 1:
        page = 1
    try:
        per_page = int((request.args.get('per_page') or '48').strip())
    except (TypeError, ValueError):
        per_page = 48
    if per_page < 1:
        per_page = 48
    per_page = min(per_page, 120)
    location_code_int = _resolve_location_code()
    try:
        rows, total_count = get_items_list(
            location_code=location_code_int,
            search=search or None,
            category_code=category_code,
            page=page,
            items_per_page=per_page,
        )
        return jsonify({'success': True, 'products': rows, 'total_count': total_count})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}, 500)

@bp.route('/pos-billing/barcode-items', methods=['GET'])
def pos_barcode_items():
    """Search POS item/barcode popup rows from ITEMMASTER and alternate UOM barcodes."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    search = (request.args.get('search') or '').strip()
    location_code_int = _resolve_location_code()
    try:
        limit = int(request.args.get('limit') or 80)
    except (TypeError, ValueError):
        limit = 80
    limit = max(20, min(limit, 120))
    try:
        if not search:
            rows = _safe_rows("\n                SELECT * FROM (\n                    SELECT\n                        TO_CHAR(im.ITEMCODE) AS query_value,\n                        TO_CHAR(NVL(im.MANUFACTURERID, im.ITEMCODE)) AS barcode,\n                        im.ITEMCODE AS itemcode,\n                        im.ITEMNAME AS itemname,\n                        NVL(im.BASEUOM, 'PCS') AS uom,\n                        NVL(im.RETAILPRICE, 0) AS price,\n                        NVL(im.COSTPRICE, 0) AS cost,\n                        'BASE' AS source_type\n                    FROM ITEMMASTER im\n                    WHERE im.LOCATIONCODE = :loc\n                    ORDER BY im.ITEMCODE DESC\n                )\n                WHERE ROWNUM <= :lim\n                ", {'loc': location_code_int, 'lim': limit})
        else:
            search_up = search.upper().replace('*', '%')
            contains_pattern = search_up if '%' in search_up else f'%{search_up}%'
            prefix_pattern = search_up if '%' in search_up else f'{search_up}%'
            rows = _safe_rows("\n                SELECT * FROM (\n                    SELECT * FROM (\n                        SELECT\n                            CASE\n                                WHEN TO_CHAR(im.ITEMCODE) = :exact THEN 1\n                                WHEN UPPER(NVL(im.MANUFACTURERID, '')) = :exact THEN 2\n                                WHEN TO_CHAR(im.ITEMCODE) LIKE :prefix_q THEN 3\n                                WHEN UPPER(NVL(im.MANUFACTURERID, '')) LIKE :prefix_q THEN 4\n                                ELSE 8\n                            END AS match_priority,\n                            TO_CHAR(im.ITEMCODE) AS query_value,\n                            TO_CHAR(NVL(im.MANUFACTURERID, im.ITEMCODE)) AS barcode,\n                            im.ITEMCODE AS itemcode,\n                            im.ITEMNAME AS itemname,\n                            NVL(im.BASEUOM, 'PCS') AS uom,\n                            NVL(im.RETAILPRICE, 0) AS price,\n                            NVL(im.COSTPRICE, 0) AS cost,\n                            'BASE' AS source_type\n                        FROM ITEMMASTER im\n                        WHERE im.LOCATIONCODE = :loc\n                          AND (\n                            TO_CHAR(im.ITEMCODE) LIKE :prefix_q\n                            OR UPPER(NVL(im.MANUFACTURERID, '')) LIKE :prefix_q\n                            OR UPPER(NVL(im.ITEMNAME, '')) LIKE :contains_q\n                          )\n                        UNION ALL\n                        SELECT\n                            CASE\n                                WHEN UPPER(TO_CHAR(alt.MANUFACTURERID)) = :exact THEN 1\n                                WHEN UPPER(TO_CHAR(alt.MANUFACTURERID)) LIKE :prefix_q THEN 3\n                                ELSE 8\n                            END AS match_priority,\n                            TO_CHAR(NVL(NULLIF(TRIM(alt.MANUFACTURERID), ''), im.MANUFACTURERID)) AS query_value,\n                            TO_CHAR(NVL(NULLIF(TRIM(alt.MANUFACTURERID), ''), im.MANUFACTURERID)) AS barcode,\n                            im.ITEMCODE AS itemcode,\n                            im.ITEMNAME AS itemname,\n                            NVL(alt.ALTERNATEUOMCODE, im.BASEUOM) AS uom,\n                            NVL(alt.RETAILPRICE, im.RETAILPRICE) AS price,\n                            NVL(alt.COSTPRICE, im.COSTPRICE) AS cost,\n                            'ALT' AS source_type\n                        FROM ITEMALTERNATEUOMMAP alt\n                        JOIN ITEMMASTER im\n                          ON im.LOCATIONCODE = alt.LOCATIONCODE\n                         AND im.ITEMCODE = alt.ITEMCODE\n                        WHERE alt.LOCATIONCODE = :loc\n                          AND (\n                            UPPER(TO_CHAR(alt.MANUFACTURERID)) LIKE :prefix_q\n                            OR UPPER(NVL(alt.ALTERNATEUOMCODE, '')) LIKE :prefix_q\n                            OR TO_CHAR(im.ITEMCODE) LIKE :prefix_q\n                            OR UPPER(NVL(im.ITEMNAME, '')) LIKE :contains_q\n                          )\n                    )\n                    ORDER BY match_priority, itemname, itemcode, source_type\n                )\n                WHERE ROWNUM <= :lim\n                ", {'loc': location_code_int, 'exact': search_up, 'prefix_q': prefix_pattern, 'contains_q': contains_pattern, 'lim': limit})
        out = []
        for r in rows or []:
            cost = float(r.get('cost') or 0)
            out.append({'query': r.get('query_value'), 'barcode': r.get('barcode'), 'itemcode': r.get('itemcode'), 'itemname': r.get('itemname'), 'uom': r.get('uom'), 'price': float(r.get('price') or 0), 'cost': cost, 'costprice': cost, 'averagecost': 0.0, 'item_factor': 1.0, 'conversion_factor': 1.0, 'source': r.get('source_type')})
        return jsonify({'success': True, 'items': out})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}, 500)

@bp.route('/pos-billing/sample-test-barcode', methods=['GET'])
def pos_sample_test_barcode():
    """Return one random barcode from ITEMMASTER for POS testing (prefers unique MANUFACTURERID rows first).

    Uses DBMS_RANDOM so repeated taps typically yield different items when multiple qualify.
    """
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    location_code_int = _resolve_location_code()
    try:
        rows = _safe_rows(
            '\n            SELECT * FROM (\n                SELECT TRIM(im.MANUFACTURERID) AS barcode,\n                       MIN(im.ITEMCODE) AS itemcode,\n                       MIN(im.ITEMNAME) AS itemname\n                FROM ITEMMASTER im\n                WHERE im.LOCATIONCODE = :loc\n                  AND im.MANUFACTURERID IS NOT NULL\n                  AND LENGTH(TRIM(im.MANUFACTURERID)) > 0\n                GROUP BY TRIM(im.MANUFACTURERID)\n                HAVING COUNT(*) = 1\n                ORDER BY DBMS_RANDOM.VALUE\n            )\n            WHERE ROWNUM <= 1\n            ',
            {'loc': location_code_int},
        )
        if not rows:
            rows = _safe_rows(
                '\n                SELECT * FROM (\n                    SELECT TO_CHAR(NVL(NULLIF(TRIM(im.MANUFACTURERID), \'\'), im.ITEMCODE)) AS barcode,\n                           im.ITEMCODE AS itemcode,\n                           im.ITEMNAME AS itemname\n                    FROM ITEMMASTER im\n                    WHERE im.LOCATIONCODE = :loc\n                    ORDER BY DBMS_RANDOM.VALUE\n                )\n                WHERE ROWNUM <= 1\n                ',
                {'loc': location_code_int},
            )
        if not rows:
            return jsonify({'success': False, 'error': 'No items in ITEMMASTER for this location.'}, 404)
        r0 = rows[0]
        bc = str(r0.get('barcode') or '').strip()
        if not bc:
            return jsonify({'success': False, 'error': 'Could not resolve a barcode value.'}, 404)
        return jsonify(
            {
                'success': True,
                'barcode': bc,
                'itemcode': r0.get('itemcode'),
                'itemname': (r0.get('itemname') or '').strip() if r0.get('itemname') is not None else '',
            }
        )
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}, 500)

@bp.route('/pos-billing/item-uoms', methods=['GET'])
def pos_item_uoms():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    item_code = (request.args.get('item_code') or '').strip()
    if not item_code or not item_code.isdigit():
        return jsonify({'success': False, 'error': 'Missing item code'}, 400)
    location_code_int = _resolve_location_code()
    item = get_item_by_code(int(item_code), location_code_int)
    if not item:
        return jsonify({'success': False, 'error': 'Item not found'}, 404)
    base_uom = (item.get('baseuom') or '').strip()
    uoms = []
    if base_uom:
        uoms.append({'code': base_uom, 'name': base_uom, 'is_base': True})
    for alt in get_item_alternate_uoms(location_code_int, int(item_code)):
        alt_code = (alt.get('alternateuomcode') or '').strip()
        if not alt_code or (base_uom and alt_code.upper() == base_uom.upper()):
            continue
        uoms.append({'code': alt_code, 'name': alt_code, 'is_base': False, 'conversion_factor': alt.get('conversionfactor')})
    return jsonify({'success': True, 'uoms': uoms})

@bp.route('/pos-billing/uom-info', methods=['GET'])
def pos_uom_info():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    item_code = (request.args.get('item_code') or '').strip()
    uom_code = (request.args.get('uom_code') or '').strip()
    price_mode = (request.args.get('price_mode') or 'retail').strip().lower()
    if not item_code or not uom_code:
        return jsonify({'success': False, 'error': 'Missing item or uom'}, 400)
    location_code_int = _resolve_location_code()
    pricing = get_item_uom_pricing(location_code_int, int(item_code), uom_code, price_mode)
    if not pricing:
        return jsonify({'success': False, 'error': 'UOM not available'}, 404)
    return jsonify({'success': True, 'pricing': pricing})

@bp.route('/pos-billing/cart-sync', methods=['POST'])
def pos_cart_sync():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    payload: Dict[str, Any] = request.get_json(silent=True) or {}
    header = payload.get('header') or {}
    lines = payload.get('lines') or []
    location_code_int = _resolve_location_code()
    header['location_code'] = location_code_int
    header.setdefault('billdate', datetime.now().strftime('%Y-%m-%d'))
    header.setdefault('billtime', datetime.now().strftime('%H:%M:%S'))
    header.setdefault('createdby', session.get('user'))
    _apply_open_shift_posdate_to_pos_header_billdate(header, location_code_int)
    if header.get('employeecode') is None and session.get('employeecode') is not None:
        try:
            header['employeecode'] = int(session.get('employeecode') or 0)
        except (TypeError, ValueError):
            pass
    billno, err = _pos_parse_billno(header.get('billno'), empty_error='Bill number required for cart sync')
    if err:
        return jsonify({'success': False, 'error': err}, 400)
    header['billno'] = billno
    ok, error = sync_cart_to_temp({'header': header, 'lines': lines})
    if not ok:
        return jsonify({'success': False, 'error': error or 'Sync failed'}, 400)
    return jsonify({'success': True, 'billno': billno})

@bp.route('/pos-billing/cart-line-add', methods=['POST'])
def pos_cart_line_add():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    payload = request.get_json(silent=True) or {}
    header = payload.get('header') or {}
    line = payload.get('line') or {}
    location_code_int = _resolve_location_code()
    header['location_code'] = location_code_int
    header.setdefault('billdate', datetime.now().strftime('%Y-%m-%d'))
    header.setdefault('billtime', datetime.now().strftime('%H:%M:%S'))
    header.setdefault('createdby', session.get('user'))
    _apply_open_shift_posdate_to_pos_header_billdate(header, location_code_int)
    if header.get('employeecode') is None and session.get('employeecode') is not None:
        try:
            header['employeecode'] = int(session.get('employeecode') or 0)
        except (TypeError, ValueError):
            pass
    billno, err = _pos_parse_billno(header.get('billno'))
    if err:
        return jsonify({'success': False, 'error': err}, 400)
    header['billno'] = billno
    ok, error, slno = add_cart_line_to_temp(header, line)
    if not ok:
        return jsonify({'success': False, 'error': error or 'Add failed'}, 400)
    return jsonify({'success': True, 'billno': billno, 'slno': slno})

@bp.route('/pos-billing/cart-line-void', methods=['POST'])
def pos_cart_line_void():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    payload = request.get_json(silent=True) or {}
    header = payload.get('header') or {}
    slno = payload.get('slno')
    location_code_int = _resolve_location_code()
    if slno is None:
        return jsonify({'success': False, 'error': 'Bill number and slno required'}, 400)
    billno, err = _pos_parse_billno(header.get('billno'))
    if err:
        return jsonify({'success': False, 'error': err}, 400)
    try:
        slno = int(slno)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Invalid billno or slno'}, 400)
    ok, error = void_cart_line_in_temp(location_code_int, billno, slno)
    if not ok:
        return jsonify({'success': False, 'error': error or 'Void failed'}, 400)
    return jsonify({'success': True})

@bp.route('/pos-billing/cart-line-update', methods=['POST'])
def pos_cart_line_update():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    payload = request.get_json(silent=True) or {}
    header = payload.get('header') or {}
    slno = payload.get('slno')
    quantity = payload.get('quantity')
    discount = payload.get('discount')
    rate = payload.get('rate')
    location_code_int = _resolve_location_code()
    if slno is None or (quantity is None and discount is None and rate is None):
        return jsonify({'success': False, 'error': 'Bill number and slno are required; send quantity, rate, and/or discount.'}, 400)
    billno, err = _pos_parse_billno(header.get('billno'))
    if err:
        return jsonify({'success': False, 'error': err}, 400)
    try:
        slno = int(slno)
        if quantity is not None:
            quantity = float(quantity)
        if discount is not None:
            discount = float(discount)
        if rate is not None:
            rate = float(rate)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Invalid billno, slno, quantity, rate or discount'}, 400)
    if quantity is not None:
        ok, error = update_cart_line_qty_in_temp(location_code_int, billno, slno, quantity)
        if not ok:
            return jsonify({'success': False, 'error': error or 'Quantity update failed'}, 400)
    if rate is not None:
        ok, error = update_cart_line_rate_in_temp(location_code_int, billno, slno, rate)
        if not ok:
            return jsonify({'success': False, 'error': error or 'Price update failed'}, 400)
    if discount is not None:
        ok, error = update_cart_line_discount_in_temp(location_code_int, billno, slno, discount)
        if not ok:
            return jsonify({'success': False, 'error': error or 'Discount update failed'}, 400)
    return jsonify({'success': True})

@bp.route('/pos-billing/cart-line-remove', methods=['POST'])
def pos_cart_line_remove():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    payload = request.get_json(silent=True) or {}
    header = payload.get('header') or {}
    slno = payload.get('slno')
    location_code_int = _resolve_location_code()
    if slno is None:
        return jsonify({'success': False, 'error': 'Bill number and slno required'}, 400)
    billno, err = _pos_parse_billno(header.get('billno'))
    if err:
        return jsonify({'success': False, 'error': err}, 400)
    try:
        slno = int(slno)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Invalid billno or slno'}, 400)
    ok, error = remove_cart_line_from_temp(location_code_int, billno, slno)
    if not ok:
        return jsonify({'success': False, 'error': error or 'Remove failed'}, 400)
    return jsonify({'success': True})

@bp.route('/pos-billing/void-all', methods=['POST'])
def pos_void_all():
    """Void current bill: copy to TBLCANCELEDHDR/TBLCANCELEDDTL with BILLTYPE='V', remove from temp."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    payload = request.get_json(silent=True) or {}
    billno, err = _pos_parse_billno(payload.get('billno'))
    if err:
        return jsonify({'success': False, 'error': err}, 400)
    location_code_int = _resolve_location_code()
    username = str(session.get('user') or '').strip()
    slip_text = ''
    ok_snap, _snap_err, snap = _pos_hold_cancel_slip_snapshot(location_code_int, billno)
    if ok_snap and snap:
        slip_text = _build_pos_hold_cancel_slip_text(
            'CANCEL',
            billno=billno,
            user=username,
            user_dbkey=user_dbkey,
            snapshot=snap,
        )
    ok, error = void_all_temp_bill(billno, location_code_int)
    if not ok:
        return jsonify({'success': False, 'error': error or 'Void all failed'}, 400)
    resp: Dict[str, Any] = {'success': True, 'billno': billno}
    if slip_text:
        resp['slip_text'] = slip_text
        resp['item_count'] = snap.get('item_count') if snap else 0
        resp['amount'] = snap.get('amount') if snap else 0
    return jsonify(resp)

@bp.route('/pos-billing/hold', methods=['POST'])
def pos_hold():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    payload = request.get_json(silent=True) or {}
    billno, err = _pos_parse_billno(payload.get('billno'))
    if err:
        return jsonify({'success': False, 'error': err}, 400)
    location_code_int = _resolve_location_code()
    username = str(session.get('user') or '').strip()
    slip_text = ''
    ok_snap, _snap_err, snap = _pos_hold_cancel_slip_snapshot(location_code_int, billno)
    if ok_snap and snap:
        slip_text = _build_pos_hold_cancel_slip_text(
            'HOLD',
            billno=billno,
            user=username,
            user_dbkey=user_dbkey,
            snapshot=snap,
        )
    ok, error = hold_bill(billno, location_code_int)
    if not ok:
        return jsonify({'success': False, 'error': error or 'Hold failed'}, 400)
    resp: Dict[str, Any] = {'success': True, 'billno': billno}
    if slip_text:
        resp['slip_text'] = slip_text
        resp['item_count'] = snap.get('item_count') if snap else 0
        resp['amount'] = snap.get('amount') if snap else 0
    return jsonify(resp)

@bp.route('/pos-billing/held-bill', methods=['GET'])
def pos_held_bill():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    billno, err = _pos_parse_billno(request.args.get('billno'))
    if err:
        return jsonify({'success': False, 'error': err}, 400)
    location_code_int = _resolve_location_code()
    ok, error, header, lines = get_held_bill(billno, location_code_int)
    if not ok:
        return jsonify({'success': False, 'error': error or 'Held bill not found'}, 404)
    return jsonify({'success': True, 'header': header or {}, 'lines': lines or []})

@bp.route('/pos-billing/last-in-progress-bill', methods=['GET'])
def pos_last_in_progress_bill():
    """Return the last bill with BILLTYPE='P' from TEMPBILLHDR/TEMPBILLDTL for this location (and counter)."""
    _t0 = time.perf_counter()
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    location_code_int = _resolve_location_code()
    counter_code = _countercode_query_optional()
    if counter_code is None:
        counter_code = 0
    createdby = (session.get('user') or '').strip()
    try:
        employeecode = int(session.get('employeecode') or 0)
    except (TypeError, ValueError):
        employeecode = 0
    ok, error, header, lines = get_last_in_progress_bill(location_code_int, counter_code, createdby=createdby, employeecode=employeecode)
    if not ok:
        _pos_timing_log('last_in_progress_bill', _t0, ok=0, countercode=counter_code)
        return jsonify({'success': False, 'error': error or 'Failed to load'}, 500)
    cc_shift = counter_code if counter_code and int(counter_code) > 0 else _session_pos_counter_code()
    shift_payload = _pos_open_shift_status_payload(location_code_int, cc_shift, user_dbkey=user_dbkey)
    if not header:
        _pos_timing_log('last_in_progress_bill', _t0, ok=1, header=0, countercode=counter_code, lines=0)
        return jsonify({'success': True, 'header': None, 'lines': [], 'shift': shift_payload})
    _pos_timing_log('last_in_progress_bill', _t0, ok=1, header=1, countercode=counter_code, lines=len(lines or []), billno=header.get('billno'))
    return jsonify({'success': True, 'header': header, 'lines': lines, 'shift': shift_payload})

@bp.route('/pos-billing/retrieve-hold', methods=['POST'])
def pos_retrieve_hold():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    payload = request.get_json(silent=True) or {}
    billno, err = _pos_parse_billno(payload.get('billno'))
    if err:
        return jsonify({'success': False, 'error': err}, 400)
    location_code_int = _resolve_location_code()
    ok, error = set_held_bill_in_progress(billno, location_code_int)
    if not ok:
        return jsonify({'success': False, 'error': error or 'Retrieve failed'}, 400)
    return jsonify({'success': True, 'billno': billno})

@bp.route('/pos-billing/save', methods=['POST'])
def pos_save():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    if not _try_acquire_pos_billing_save_lock():
        return json_response_rotate_pos({'success': False, 'error': 'A POS save is already in progress for this session. Please wait.', 'save_session_locked': True}, 423)
    save_http_t0 = time.perf_counter()
    try:
        submitted_nonce = extract_submitted_save_nonce(request)
        if not reject_invalid_pos_save_nonce(submitted_nonce):
            return replay_blocked_response_pos()
        user_dbkey = session.get('tenant_id')
        if user_dbkey:
            _apply_active_connection(user_dbkey)
        payload: Dict[str, Any] = request.get_json(silent=True) or {}
        header = payload.get('header') or {}
        lines = payload.get('lines') or []
        if not lines:
            return json_response_rotate_pos({'success': False, 'error': 'No items to save'}, 400)
        location_code_int = _resolve_location_code()
        header['location_code'] = location_code_int
        header.setdefault('billdate', datetime.now().strftime('%Y-%m-%d'))
        header.setdefault('billtime', datetime.now().strftime('%H:%M:%S'))
        header.setdefault('createdby', session.get('user'))
        sess_cc = _session_pos_counter_code()
        if sess_cc and not header.get('countercode'):
            header['countercode'] = sess_cc
        _apply_open_shift_posdate_to_pos_header_billdate(header, location_code_int)
        _apply_pos_save_header_flags(header)
        try:
            cc_chk = int(header.get('customercode') or 0)
        except (TypeError, ValueError):
            cc_chk = 0
        if cc_chk > 0:
            ok_gl, gl_msg = validate_pos_credit_customer_accounts(location_code_int, cc_chk, proposed_credit_delta=pos_payload_credit_delta(header, lines))
            if not ok_gl:
                return json_response_rotate_pos(
                    {'success': False, 'error': gl_msg or 'Credit sale cannot post to accounts.', 'pos_credit_accounts_error': True},
                    400,
                )
        if header.get('employeecode') is None and session.get('employeecode') is not None:
            try:
                header['employeecode'] = int(session.get('employeecode') or 0)
            except (TypeError, ValueError):
                pass
        billno, err = _pos_parse_billno(header.get('billno'))
        if err:
            return json_response_rotate_pos({'success': False, 'error': err}, 400)
        if not commit_pos_save_nonce(submitted_nonce):
            return replay_blocked_response_pos()
        pos_route_t0 = time.perf_counter()
        if billno:
            design = load_receipt_design()
            receipt_data = build_pos_receipt_from_save_payload(
                location_code_int,
                session.get('tenant_id'),
                header,
                lines,
                receipt_extras=payload.get('receipt_extras') if isinstance(payload.get('receipt_extras'), dict) else None,
            )
            print(f'[POS_SAVE_ROUTE_TIMING billno={billno}] receipt_from_payload={time.perf_counter() - pos_route_t0:.3f}s')
            header['billno'] = billno
            header['use_existing_billno'] = True
            queue_payload = {
                'header': header,
                'lines': lines,
                'receipt_extras': payload.get('receipt_extras') if isinstance(payload.get('receipt_extras'), dict) else {},
                'temp_billno': billno,
            }
            ok, error, job_id = enqueue_pos_save_job(
                queue_payload,
                location_code_int,
                billno,
                created_by=session.get('user') or '',
                countercode=header.get('countercode') or 0,
            )
            if not ok:
                return json_response_rotate_pos({'success': False, 'error': error or 'Save failed'}, 400)
            mark_temp_bill_queued(location_code_int, billno)
            _kick_pos_queue_worker(user_dbkey)
            print(f'[POS_SAVE_ROUTE_TIMING billno={billno}] enqueue_job={job_id} total={time.perf_counter() - pos_route_t0:.3f}s')
            resp = {
                'success': True,
                'queued': True,
                'queue_job_id': job_id,
                'queue_status': 'PENDING',
                'billno': billno,
                'stock_posted': False,
                'stock_affected_items': 0,
            }
            if receipt_data is not None:
                receipt_data['billno'] = billno
                rex = payload.get('receipt_extras')
                if isinstance(rex, dict):
                    receipt_data['receipt_extras'] = rex
                resp['receipt'] = receipt_data
                resp['receipt_text'] = _receipt_to_plain_text(receipt_data, design)
            return json_response_rotate_pos(resp)
        ok, error, job_id = enqueue_pos_save_job({'header': header, 'lines': lines, 'receipt_extras': payload.get('receipt_extras') or {}}, location_code_int, coerce_billno(header.get('billno') or 0), created_by=session.get('user') or '', countercode=header.get('countercode') or 0)
        if not ok:
            return json_response_rotate_pos({'success': False, 'error': error or 'Save failed'}, 400)
        _kick_pos_queue_worker(user_dbkey)
        return json_response_rotate_pos({
            'success': True,
            'queued': True,
            'queue_job_id': job_id,
            'queue_status': 'PENDING',
            'billno': header.get('billno'),
            'stock_posted': False,
            'stock_affected_items': 0,
        })
    finally:
        print(
            f"[POS_SAVE_HTTP_TIMING] handler_total={time.perf_counter() - save_http_t0:.3f}s "
            f"user={(session.get('user') or '')!r}"
        )
        _release_pos_billing_save_lock()

@bp.route('/pos-billing/client-checkout-timing', methods=['POST'])
def pos_client_checkout_timing():
    """Browser reports checkout phase timings (DevTools / ?posCheckoutTiming=1) for server log lines."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    payload = request.get_json(silent=True) or {}
    try:
        line = json.dumps(payload, default=str, ensure_ascii=False)
        if len(line) > 2400:
            line = line[:2400] + '…'
    except Exception:
        line = str(payload)[:2400]
    print(
        f"[POS_CLIENT_CHECKOUT_TIMING] user={(session.get('user') or '')!r} "
        f"tenant={(session.get('tenant_id') or '')!r} {line}"
    )
    return jsonify({'success': True})


def _pos_verify_header_defaults(payload_header: Dict[str, Any]) -> Dict[str, Any]:
    h = dict(payload_header or {})
    h.setdefault('billdate', datetime.now().strftime('%Y-%m-%d'))
    h.setdefault('billtime', datetime.now().strftime('%H:%M:%S'))
    h.setdefault('createdby', session.get('user'))
    h.setdefault('billtype', 'C')
    if h.get('employeecode') is None and session.get('employeecode') is not None:
        try:
            h['employeecode'] = int(session.get('employeecode') or 0)
        except (TypeError, ValueError):
            pass
    return h


def _pos_verify_first_int(*vals: Any, default: int = 0) -> int:
    """Pick first value that coerces to int (TEMP headers may store codes as strings or usernames)."""
    for val in vals:
        if val is None:
            continue
        if isinstance(val, bool):
            continue
        if isinstance(val, int):
            return val
        try:
            s = str(val).strip()
            if not s:
                continue
            return int(float(s))
        except (TypeError, ValueError, OverflowError):
            continue
    return default


def _pos_verify_coerce_float(val: Any, default: float = 0.0) -> float:
    try:
        if val is None or val == '':
            return default
        return float(val)
    except (TypeError, ValueError):
        return default


def _pos_verify_checkout_payload_from_temp(header: Dict[str, Any], lines: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Map TEMPBILLHDR/TEMPBILLDTL-style rows to POS save / simulate JSON."""
    ch_lines: List[Dict[str, Any]] = []
    for ln in lines or []:
        if _pos_verify_first_int(ln.get('item_flag'), default=1) == 0:
            continue
        try:
            qty = float(ln.get('quantity') or 0)
        except (TypeError, ValueError):
            qty = 0.0
        if abs(qty) < 1e-09:
            continue
        ch_lines.append(
            {
                'item_code': ln.get('item_code'),
                'item_name': ln.get('item_name') or '',
                'manufacturerid': ln.get('manufacturerid') or ln.get('barcode') or '',
                'uom': ln.get('uom'),
                'quantity': ln.get('quantity'),
                'rate': ln.get('rate'),
                'discount': ln.get('discount'),
                'base_qty': ln.get('base_qty'),
                'cost': ln.get('cost'),
                'costprice': ln.get('costprice'),
                'averagecost': ln.get('averagecost'),
                'item_factor': ln.get('item_factor') or 1,
            }
        )
    h = dict(header or {})
    checkout_header: Dict[str, Any] = {
        'billno': h.get('billno'),
        'countercode': _pos_verify_first_int(h.get('countercode')),
        'billdate': h.get('billdate'),
        'billtime': h.get('billtime'),
        'billtype': 'C',
        'customercode': _pos_verify_first_int(h.get('customercode')),
        'loyaltycustomercode': _pos_verify_first_int(h.get('loyaltycustomercode')),
        'discountamount': _pos_verify_coerce_float(h.get('discountamount')),
        'netbillamount': _pos_verify_coerce_float(h.get('netbillamount')),
        'createdby': h.get('createdby') or session.get('user'),
        'employeecode': _pos_verify_first_int(h.get('employeecode'), session.get('employeecode')),
        'resetno': _pos_verify_first_int(h.get('resetno'), 1),
        'salesmancode': _pos_verify_first_int(h.get('salesmancode')),
    }
    return checkout_header, ch_lines


@bp.route('/pos-billing/credit-sale-precheck', methods=['POST'])
def pos_credit_sale_precheck():
    """Dry-run POS credit checks (GL mapping + credit limit vs proposed delta). Does not post invoices."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    payload = request.get_json(silent=True) or {}
    try:
        cc = int(payload.get('customercode') or 0)
    except (TypeError, ValueError):
        cc = 0
    location_code_int = _resolve_location_code()
    if cc <= 0:
        return jsonify({'success': True, 'skipped': True, 'accounts_ok': True, 'detail': 'No billing customer code on request; skipped.'})
    delta_raw = payload.get('proposed_credit_delta')
    if delta_raw is None:
        delta_raw = payload.get('net_total')
    try:
        delta_f = float(delta_raw if delta_raw is not None else 0)
    except (TypeError, ValueError):
        delta_f = 0.0
    ok_gl, gl_msg = validate_pos_credit_customer_accounts(location_code_int, cc, proposed_credit_delta=delta_f)
    return jsonify({'success': True, 'skipped': False, 'accounts_ok': bool(ok_gl), 'detail': gl_msg})


@bp.route('/pos-billing/verify', methods=['GET'])
def pos_verify_page():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    openai_configured = bool((os.environ.get('OPENAI_API_KEY') or '').strip())
    return render_template('pos_billing/pos_verify.html', title='POS Verify', openai_configured=openai_configured)


@bp.route('/pos-billing/verify/simulate', methods=['POST'])
def pos_verify_simulate_api():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    payload = request.get_json(silent=True) or {}
    header = _pos_verify_header_defaults(payload.get('header') or {})
    lines = payload.get('lines') or []
    strict = bool(payload.get('strict'))
    header['location_code'] = _resolve_location_code()
    _apply_open_shift_posdate_to_pos_header_billdate(header, header['location_code'])
    header['allow_negative_batch'] = not strict
    ok, msg, sim = simulate_pos_sale_stock_impact(header, lines)
    return jsonify({'success': True, 'simulation_ok': bool(ok), 'simulation_message': msg or None, **sim})


@bp.route('/pos-billing/verify/live-stock', methods=['POST'])
def pos_verify_live_stock_api():
    """Read-only live ITEMMASTER / store / bin / batch quantities for current checkout lines."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    payload = request.get_json(silent=True) or {}
    header = _pos_verify_header_defaults(payload.get('header') or {})
    lines = payload.get('lines') or []
    header['location_code'] = _resolve_location_code()
    _apply_open_shift_posdate_to_pos_header_billdate(header, header['location_code'])
    ok, msg, snap = read_pos_stock_live_snapshot(header, lines)
    body = {'success': bool(ok), 'error': msg or None, **snap}
    if not ok:
        return jsonify(body, 400)
    return jsonify(body)


@bp.route('/pos-billing/verify/ai-insights', methods=['POST'])
def pos_verify_ai_api():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    api_key = (os.environ.get('OPENAI_API_KEY') or '').strip()
    if not api_key:
        return jsonify({'success': False, 'error': 'OPENAI_API_KEY is not configured on the server.'}, 503)
    payload = request.get_json(silent=True) or {}
    sim = payload.get('simulation') or {}
    bill_ctx = payload.get('bill')
    live_snap = payload.get('live_db_snapshot') or payload.get('live_db')
    if not sim:
        return jsonify({'success': False, 'error': 'Run simulation first.'}, 400)
    try:
        bundle: Dict[str, Any] = {'simulation': sim}
        if bill_ctx:
            bundle['bill'] = bill_ctx
        if live_snap:
            bundle['live_db_snapshot'] = live_snap
        blob = json.dumps(bundle, default=str, ensure_ascii=False)
        max_chars = 28000 if live_snap else 16000
        if len(blob) > max_chars:
            blob = blob[:max_chars] + '…'
    except Exception:
        blob = str({'bill': bill_ctx, 'simulation': sim, 'live_db_snapshot': live_snap})[:28000]
    model = (os.environ.get('OPENAI_MODEL') or 'gpt-4o-mini').strip()
    sys_intro = (
        'You are a senior retail POS & inventory analyst. JSON may include `bill`, `simulation`, and optionally `live_db_snapshot`. '
        'Use markdown with separate sections — never skip **Store** because batch/bin are empty:\n'
        '### Store — For each `simulation.lines[]` line, lead with `store_breakdown` (pos_store_code, branch_location_code, store_inventory_row, '
        'itemmaster_store_qty, itemmaster_company_stock, notes). Also reference legacy fields `store`, `store_inventory_before`/`after`, '
        '`itemmaster_store_col_before`/`after`, `current_stock_itemmaster`/`after_stock_itemmaster`. Explain: POS store code; optional row from '
        '`simulation.flags.store_inventory_table`; ITEMMASTER per-store column qty vs company CURRENTSTOCK. If data is missing, use `store_breakdown.notes` '
        'and `simulation.flags` — do not claim “no store information” without citing those.\n'
        '### Batch and bin — From `batch_allocations`, `alt_batches`, `default_bin_stock`. If empty, say whether batch/bin tracking is off (`simulation.flags`) '
        'or item is non-batch; do not imply store is unknown for that reason.\n'
        '### Live DB compare — When `live_db_snapshot` is present: compare projected AFTER fields to `store_breakdown` / `store_inventory_live` / '
        '`itemmaster_store_column_live` / batches_live / default_bin_live per line.\n'
        '### Recommendations. Never invent quantities not in JSON.'
    )
    if not live_snap:
        sys_intro = (
            'You are a senior retail POS & inventory analyst. JSON may include `bill` and `simulation`. '
            'Use markdown with separate sections — always include **Store** before batch/bin:\n'
            '### Store — Per `simulation.lines[]`: prioritize `store_breakdown`, then `store`, `store_inventory_*`, `itemmaster_store_col_*`, '
            'and company stock `current_stock_itemmaster`/`after_stock_itemmaster`. Explain layers and cite `store_breakdown.notes` when rows are missing.\n'
            '### Batch and bin — From batch_allocations, alt_batches, default_bin_stock; explain empties using `simulation.flags`.\n'
            '### Bill recap — Risks from `bill` when present.\n'
            '### Recommendations. Never invent quantities not in JSON.'
        )
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, timeout=60.0)
        completion = client.chat.completions.create(
            model=model,
            temperature=0.25,
            messages=[
                {'role': 'system', 'content': sys_intro},
                {'role': 'user', 'content': blob},
            ],
            max_tokens=1550 if live_snap else 1250,
        )
        text = (completion.choices[0].message.content or '').strip()
        return jsonify({'success': True, 'insights': text})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}, 500)


@bp.route('/pos-billing/verify/temp-bills', methods=['GET'])
def pos_verify_temp_bills_api():
    """List TEMPBILLHDR summaries for POS Verify (tenant DB)."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    try:
        lim = int(request.args.get('limit') or 150)
    except (TypeError, ValueError):
        lim = 150
    rows = list_temp_bills_for_pos_verify(_resolve_location_code(), lim)
    return jsonify({'success': True, 'bills': rows})


@bp.route('/pos-billing/verify/temp-bill', methods=['GET'])
def pos_verify_temp_bill_detail_api():
    """Load one temp bill as checkout header/lines for simulate/save."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    try:
        billno = int(request.args.get('billno') or 0)
    except (TypeError, ValueError):
        billno = 0
    if billno == 0:
        return jsonify({'success': False, 'error': 'billno required'}, 400)
    location_code_int = _resolve_location_code()
    ok, err, raw_hdr, raw_dtl_rows, bill_lines, dtl_col_order = get_temp_bill_by_billno(location_code_int, billno)
    if not ok:
        return jsonify({'success': False, 'error': err or 'Load failed'}, 400)
    ch_header, ch_lines = _pos_verify_checkout_payload_from_temp(raw_hdr or {}, bill_lines or [])
    return jsonify(
        {
            'success': True,
            'billno': billno,
            'header': ch_header,
            'lines': ch_lines,
            'bill_lines': bill_lines,
            'raw_header': raw_hdr,
            'raw_lines': raw_dtl_rows,
            'tempbilldtl_column_order': dtl_col_order or [],
        }
    )


@bp.route('/pos-billing/save-queue', methods=['GET'])
def pos_save_queue_page():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    return render_template('pos_billing/pos_save_queue.html')

@bp.route('/pos-billing/save-queue/api', methods=['GET'])
def pos_save_queue_api():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id') or 'HO'
    _apply_active_connection(user_dbkey)
    prepare_pos_save_queue_for_claim()
    try:
        limit = int(request.args.get('limit') or 100)
    except (TypeError, ValueError):
        limit = 100
    jobs = list_pos_save_queue(limit)
    if any(str(j.get('status') or '').upper() == 'PENDING' for j in jobs):
        _kick_pos_queue_worker(user_dbkey)
    processing_cnt = sum(1 for j in jobs if str(j.get('status') or '').upper() == 'PROCESSING')
    return jsonify({
        'success': True,
        'jobs': jobs,
        'processing_count': processing_cnt,
        'stale_minutes': 5,
    })

@bp.route('/pos-billing/save-queue/job/<int:job_id>', methods=['GET'])
def pos_save_queue_job_detail_api(job_id: int):
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    ok, err, detail = get_pos_save_queue_job_detail(job_id)
    if not ok:
        return jsonify({'success': False, 'error': err or 'Not found'}, 404)
    return jsonify({'success': True, 'job': detail})

@bp.route('/pos-billing/save-queue/retry', methods=['POST'])
def pos_save_queue_retry():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    payload = request.get_json(silent=True) or {}
    try:
        job_id = int(payload.get('job_id') or 0)
    except (TypeError, ValueError):
        job_id = 0
    if job_id <= 0:
        return jsonify({'success': False, 'error': 'Invalid job id'}, 400)
    unstick = bool(payload.get('unstick'))
    ok, err = retry_pos_save_job(job_id, unstick_processing=unstick)
    if not ok:
        return jsonify({'success': False, 'error': err or 'Retry failed'}, 400)
    _kick_pos_queue_worker(user_dbkey)
    return jsonify({'success': True})


@bp.route('/pos-billing/save-queue/post-now', methods=['POST'])
def pos_save_queue_post_now():
    """Post one queue job immediately (skips FIFO wait for that row)."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    payload = request.get_json(silent=True) or {}
    try:
        job_id = int(payload.get('job_id') or 0)
    except (TypeError, ValueError):
        job_id = 0
    if job_id <= 0:
        return jsonify({'success': False, 'error': 'Invalid job id'}, 400)
    ok = False
    err = None
    posted_billno = None
    user_dbkey = user_dbkey or 'HO'
    try:
        set_active_db_key(user_dbkey)
        acquired = _POS_QUEUE_EXEC_LOCK.acquire(timeout=120)
        if not acquired:
            return jsonify({'success': False, 'error': 'Another POS post is still running. Try Unstick all or wait a minute.'}, 423)
        try:
            global _POS_QUEUE_BUSY_SINCE
            _POS_QUEUE_BUSY_SINCE = time.time()
            job = claim_pos_save_job_by_id(job_id)
            if not job:
                return jsonify({'success': False, 'error': 'Job not found or not postable (must be PENDING or FAILED). Another job may be posting.'}, 404)
            ok, err, posted_billno = _execute_claimed_pos_save_job(job)
        finally:
            _POS_QUEUE_BUSY_SINCE = 0.0
            _POS_QUEUE_EXEC_LOCK.release()
    finally:
        set_active_db_key(None)
    if ok:
        return jsonify({'success': True, 'posted_billno': posted_billno, 'job_id': job_id})
    return jsonify({'success': False, 'error': err or 'Post failed', 'job_id': job_id}, 400)


@bp.route('/pos-billing/save-queue/reconcile', methods=['POST'])
def pos_save_queue_reconcile():
    """Mark a FAILED queue job as POSTED when BILLHDR already has this bill (no re-insert)."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    payload = request.get_json(silent=True) or {}
    try:
        job_id = int(payload.get('job_id') or 0)
    except (TypeError, ValueError):
        job_id = 0
    if job_id <= 0:
        return jsonify({'success': False, 'error': 'Invalid job id'}, 400)
    ok, err, detail = get_pos_save_queue_job_detail(job_id)
    if not ok or not detail:
        return jsonify({'success': False, 'error': err or 'Job not found'}, 404)
    status = str(detail.get('status') or '').upper()
    if status not in ('FAILED', 'PENDING', 'PROCESSING'):
        return jsonify({'success': False, 'error': f'Job is already {status}.'}, 400)
    try:
        loc = int(detail.get('locationcode') or 0)
        billno = int(detail.get('billno') or 0)
    except (TypeError, ValueError):
        loc, billno = 0, 0
    if loc <= 0 or billno <= 0:
        return jsonify({'success': False, 'error': 'Invalid job location or bill number.'}, 400)
    if not billhdr_exists(loc, billno):
        return jsonify({'success': False, 'error': f'Bill {billno} is not in BILLHDR yet. Use Post now to save it.'}, 400)
    finish_pos_save_job(job_id, True, billno, None)
    return jsonify({'success': True, 'job_id': job_id, 'posted_billno': billno, 'reconciled': True})


@bp.route('/pos-billing/save-queue/unstick-all', methods=['POST'])
def pos_save_queue_unstick_all():
    """Reset every PROCESSING row to PENDING and restart the background worker."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id') or 'HO'
    _apply_active_connection(user_dbkey)
    n = force_requeue_all_pos_save_processing_jobs()
    global _POS_QUEUE_WORKER_RUNNING, _POS_QUEUE_BUSY_SINCE
    with _POS_QUEUE_WORKER_LOCK:
        _POS_QUEUE_WORKER_RUNNING = False
    _POS_QUEUE_BUSY_SINCE = 0.0
    _kick_pos_queue_worker(user_dbkey)
    return jsonify({'success': True, 'requeued': n})


@bp.route('/pos-billing/save-queue/kick', methods=['POST'])
def pos_save_queue_kick():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    _kick_pos_queue_worker(user_dbkey)
    return jsonify({'success': True})

@bp.route('/pos-billing/receipt-print', methods=['POST'])
def pos_receipt_print():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    payload: Dict[str, Any] = request.get_json(silent=True) or {}
    receipt = payload.get('receipt') or {}
    if not isinstance(receipt, dict) or not receipt:
        return jsonify({'success': False, 'error': 'Receipt data required'}, 400)
    design = load_receipt_design()
    ok, err = _print_receipt_to_default_printer(receipt, design, include_copy_banner=True)
    if not ok:
        return jsonify({'success': False, 'error': err or 'Print failed'}, 500)
    return jsonify({'success': True, 'receipt_printed': True})

@bp.route('/pos-billing/void', methods=['POST'])
def pos_void():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    payload = request.get_json(silent=True) or {}
    billno = payload.get('billno')
    if not billno:
        return jsonify({'success': False, 'error': 'Bill number required'}, 400)
    try:
        billno = int(billno)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Invalid bill number'}, 400)
    location_code_int = _resolve_location_code()
    ok, error = void_bill(billno, location_code_int)
    if not ok:
        return jsonify({'success': False, 'error': error or 'Void failed'}, 400)
    return jsonify({'success': True})


@register_context_processor
def _inject_pos_asset_version():
    req = nexa_ctx.get_current_request()
    if req is None or not is_pos_html_page_path(req.url.path):
        return {}
    return {'pos_asset_version': get_pos_asset_version()}


@bp.after_request
def _pos_html_page_no_cache(response):
    req = nexa_ctx.get_current_request()
    if req is None or not is_pos_html_page_path(req.url.path):
        return response
    media = (getattr(response, 'media_type', None) or '').lower()
    if 'html' in media or type(response).__name__ == 'TemplateResponse':
        return apply_pos_page_no_cache_headers(response)
    return response
