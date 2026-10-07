"""Sales blueprint"""
from pathlib import Path
import base64
import csv
import io
import json
import os
import re
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple
from nexa_http import Blueprint, abort, flash, jsonify, redirect, render_template, request, send_file, session, url_for
from addons.document_numbering.document_numbering_db import (
    DOC_TYPE_POS_INVOICE,
    DOC_TYPE_SALES_INVOICE,
    DOC_TYPE_SALES_ORDER,
    DOC_TYPE_SALES_RETURN,
)
from db import get_sales_minus_billing_invoice_enabled, get_sales_minus_billing_order_enabled, set_sales_minus_billing, get_sales_orderno_mandatory_invoice_enabled, get_sales_orderno_mandatory_return_enabled, get_sales_orderno_mandatory_order_enabled, set_sales_orderno_mandatory, get_sales_direct_posting_enabled, get_sales_direct_posting_return_enabled, set_sales_direct_posting, _resolve_sales_header_billtype, get_company_profile, get_customers_master_list, get_customer_loyalty_for_picker, get_item_by_alternate_barcode, get_item_by_code, get_item_by_manufacturer_id, get_item_alternate_uoms, get_item_popup_items, get_item_store_inventory, get_item_store_rows_from_itemmaster, get_customer_item_history, get_item_history, get_customer_category, get_item_uom_pricing, get_location_info_by_dbkey, get_next_bill_no, get_next_quatation_bill_no, peek_next_bill_no, get_sales_order_for_edit, get_sales_invoice_for_edit, get_sales_orders_list, get_sales_invoices_list, get_sales_returns_list, get_invoice_type_flag, get_sessions, get_tenant_by_id, get_item_lot_stock_list, save_sales_invoice, save_sales_order, cancel_sales_order, mark_sales_order_invoiced, find_invoice_billno_for_source_sales_order, _validate_sales_doc_save_lines, get_location_sales_feature_flags, is_location_warehouse_enabled, is_location_bin_tracking_enabled, is_location_batch_tracking_enabled, list_warehouse_master_rows, list_warehouse_picker_bins, get_bin_stock_list, resolve_warehouse_master_table, get_warehouse_master_store_picker_rows, billhdr_exists, billno_is_reserved, coerce_billno, billno_is_valid, billno_equal, parse_billno_from_request
from save_nonce import GLOBAL_SAVE_NONCE_SESSION_KEY, extract_submitted_save_nonce, issue_save_nonce, json_response_keep_global_nonce, json_response_rotate_global, replay_blocked_response_global, verify_consume_save_nonce
from addons.sales.controllers import credit_note_ops as _scn_ops
from addons.sales.controllers.sales_invoice_summary_pdf import (
    build_sales_invoice_summary_pdf,
    sales_invoice_list_summary_stats,
)
_SALES_DOC_SAVE_BUSY_KEY = '_sales_doc_save_busy_v1'
_SALES_BATCH_INVOICE_RUN_KEY = '_sales_batch_invoice_run_v1'
_SALES_BATCH_INVOICE_OPEN_DATE_KEY = '_sales_batch_invoice_open_date_v1'


def _json_for_script(val: Any) -> str:
    """JSON for embedding in <script> (dates/decimals safe)."""
    from datetime import date
    from decimal import Decimal

    def default(o: Any) -> Any:
        if isinstance(o, datetime):
            return o.isoformat()
        if isinstance(o, date):
            return o.isoformat()
        if isinstance(o, Decimal):
            return float(o)
        raise TypeError(f'Object of type {type(o).__name__} is not JSON serializable')

    return json.dumps(val, default=default)

def _try_acquire_sales_doc_save_lock(lock_seconds: float=600.0) -> bool:
    now = time.time()
    raw = session.get(_SALES_DOC_SAVE_BUSY_KEY)
    if raw is not None:
        try:
            until = float(raw)
            if until <= now:
                session.pop(_SALES_DOC_SAVE_BUSY_KEY, None)
                raw = None
        except (TypeError, ValueError):
            session.pop(_SALES_DOC_SAVE_BUSY_KEY, None)
            raw = None
    if raw is not None:
        try:
            if float(raw) > now:
                return False
        except (TypeError, ValueError):
            return False
    session[_SALES_DOC_SAVE_BUSY_KEY] = now + float(lock_seconds)
    session.modified = True
    return True

def _release_sales_doc_save_lock() -> None:
    session.pop(_SALES_DOC_SAVE_BUSY_KEY, None)
    session.modified = True


def _extend_sales_doc_save_lock(lock_seconds: float = 180.0) -> None:
    session[_SALES_DOC_SAVE_BUSY_KEY] = time.time() + float(lock_seconds)
    session.modified = True


def _end_batch_invoice_run() -> None:
    session.pop(_SALES_BATCH_INVOICE_RUN_KEY, None)
    session.pop(_SALES_BATCH_INVOICE_OPEN_DATE_KEY, None)
    _release_sales_doc_save_lock()


def _touch_batch_invoice_run(run_id: str) -> bool:
    if str(session.get(_SALES_BATCH_INVOICE_RUN_KEY) or '') != str(run_id or '').strip():
        return False
    _extend_sales_doc_save_lock()
    return True


def _is_duplicate_doc_key_error(err: Any) -> bool:
    err_l = str(err or '').lower()
    return (
        'duplicate key' in err_l
        or 'ora-00001' in err_l
        or 'pk_billhdr' in err_l
        or 'already in use' in err_l
        or 'already exists' in err_l
    )


def _sales_billtype_label(raw: Any) -> str:
    """Map BILLHDR.BILLTYPE to display label (R=Credit, C=Cash)."""
    bt = str(raw or '').strip().upper()
    if bt == 'R':
        return 'Credit'
    if bt == 'C' or not bt:
        return 'Cash'
    return str(raw or '').strip() or 'Cash'


def _sales_default_bill_date() -> str:
    """Today's date for sales order and other screens not tied to TBLTRANSACTIONDATE."""
    return datetime.now().strftime('%Y-%m-%d')


_SALES_INVOICE_TXN_CODE = 1
_SALES_RETURN_TXN_CODE = 3


def _sales_open_bill_range(location_code: int, *, is_return: bool = False) -> Optional[Dict[str, str]]:
    """Open business date range from TBLTRANSACTIONDATE (Transaction Date Setup)."""
    try:
        from addons.transaction_date_setup.transaction_date_db import get_open_transaction_date_range

        tc = _SALES_RETURN_TXN_CODE if is_return else _SALES_INVOICE_TXN_CODE
        return get_open_transaction_date_range(int(location_code), tc)
    except Exception:
        return None


def _sales_open_bill_date(location_code: int, *, is_return: bool = False) -> Optional[str]:
    """Preferred open business date (inside From–To range)."""
    rng = _sales_open_bill_range(location_code, is_return=is_return)
    if not rng:
        return None
    return rng.get('preferred') or rng.get('date_from')


def _sales_transaction_date_block_message(*, is_return: bool = False) -> str:
    doc = 'Sales Return' if is_return else 'Sales Invoice'
    try:
        setup_url = url_for('transaction_date_setup.transaction_date_setup_page')
    except Exception:
        setup_url = '/setup/transaction-date'
    return (
        f'Setup date is missing for {doc}. '
        f'No open From–To date range in Transaction Date Setup ({setup_url}). '
        f'Open a date range before posting.'
    )


def _sales_bill_date_context(*, is_return: bool = False) -> Dict[str, Any]:
    """Template context for Sales Invoice / Sales Return bill date from setup."""
    lc = _resolve_location_code()
    rng = _sales_open_bill_range(lc, is_return=is_return)
    open_date = (rng or {}).get('preferred') or (rng or {}).get('date_from') or ''
    date_from = (rng or {}).get('date_from') or open_date
    date_to = (rng or {}).get('date_to') or date_from
    try:
        setup_url = url_for('transaction_date_setup.transaction_date_setup_page')
    except Exception:
        setup_url = '/setup/transaction-date'
    return {
        'bill_date': open_date,
        'bill_date_from': date_from,
        'bill_date_to': date_to,
        'transaction_date_open': bool(rng),
        'transaction_date_blocked': not bool(rng),
        'transaction_date_error': None if rng else _sales_transaction_date_block_message(is_return=is_return),
        'transaction_date_setup_url': setup_url,
        'location_code': lc,
    }


def _enforce_sales_open_bill_date(
    header: Dict[str, Any],
    location_code: int,
    *,
    is_return: bool = False,
) -> Tuple[Optional[str], Optional[str]]:
    """Require bill date inside the open From–To range; default to preferred when blank."""
    rng = _sales_open_bill_range(location_code, is_return=is_return)
    if not rng:
        return None, _sales_transaction_date_block_message(is_return=is_return)
    preferred = rng.get('preferred') or rng.get('date_from') or ''
    submitted = str(header.get('billdate') or header.get('bill_date') or '').strip()[:10]
    if not submitted:
        return preferred, None
    a = rng.get('date_from') or preferred
    b = rng.get('date_to') or a
    if a <= submitted <= b:
        return submitted, None
    if a == b:
        return None, f'Bill date must be {a}.'
    return None, f'Bill date must be between {a} and {b}.'


def _parse_sales_order_billnos(*raw_values: Optional[str]) -> List[Any]:
    """Parse comma/semicolon-separated sales order bill numbers (deduped, order preserved)."""
    seen: Set[str] = set()
    out: List[Any] = []
    for raw in raw_values:
        for part in str(raw or '').replace(';', ',').split(','):
            token = part.strip()
            if not token:
                continue
            billno = parse_billno_from_request(token)
            if not billno_is_valid(billno):
                continue
            key = str(coerce_billno(billno))
            if key in seen:
                continue
            seen.add(key)
            out.append(coerce_billno(billno))
    return out


def _sales_orders_convert_payload(
    location_code: int,
    order_billnos: List[Any],
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Load one or more pending sales orders and merge into a new sales invoice payload."""
    if not order_billnos:
        return None, 'No sales orders selected.'
    merged_lines: List[Dict[str, Any]] = []
    hdr_base: Optional[Dict[str, Any]] = None
    customer_code: Optional[str] = None
    order_nos: List[str] = []
    remarks_parts: List[str] = []
    for order_billno in order_billnos:
        order = get_sales_order_for_edit(location_code, order_billno)
        if not order:
            return None, f'Sales order {order_billno} not found.'
        hdr = dict(order.get('header') or {})
        st = str(hdr.get('billstatus') or 'P').strip().upper()
        if st == 'V':
            return None, f'Sales order {order_billno} is cancelled and cannot be converted.'
        if st == 'I':
            return None, f'Sales order {order_billno} is already invoiced.'
        cc = str(hdr.get('customercode') or '').strip()
        if customer_code is None:
            customer_code = cc
            hdr_base = hdr
        elif cc != customer_code:
            return None, 'Selected sales orders must belong to the same customer.'
        merged_lines.extend(order.get('lines') or [])
        order_no = str(hdr.get('orderno') or '').strip()
        if order_no and order_no not in order_nos:
            order_nos.append(order_no)
        remark = str(hdr.get('remarks') or '').strip()
        if remark and remark not in remarks_parts:
            remarks_parts.append(remark)
    if not hdr_base or not merged_lines:
        return None, 'No lines to convert.'
    hdr_out = dict(hdr_base)
    hdr_out.pop('billno', None)
    hdr_out['source_order_billnos'] = order_billnos
    hdr_out['source_order_billno'] = order_billnos[0]
    hdr_out['orderno'] = ', '.join(str(n) for n in order_billnos)[:80]
    so_note = 'From SO #' + ', #'.join(str(n) for n in order_billnos)
    existing_remarks = str(hdr_out.get('remarks') or '').strip()
    extra_remarks = '; '.join(remarks_parts)
    combined_remarks = '; '.join(filter(None, [existing_remarks, extra_remarks]))
    if order_nos:
        cust_refs = ', '.join(order_nos)
        po_note = f'Customer order ref {cust_refs}'
        if po_note.lower() not in combined_remarks.lower():
            combined_remarks = '; '.join(filter(None, [combined_remarks, po_note])).strip('; ')
    if so_note.lower() not in combined_remarks.lower():
        combined_remarks = '; '.join(filter(None, [combined_remarks, so_note])).strip('; ')
    hdr_out['remarks'] = combined_remarks
    return {'header': hdr_out, 'lines': merged_lines}, None


def _sales_order_convert_payload(location_code: int, order_billno: Any) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Load a pending sales order for conversion into a new sales invoice."""
    return _sales_orders_convert_payload(location_code, [order_billno])


def _sales_billno_path_segment(billno: Any) -> str:
    """URL path segment for formatted bill numbers (e.g. SI-000010, SO-000002)."""
    from urllib.parse import quote
    return quote(str(billno or '').strip(), safe='')


def _sales_order_pdf_url(billno: Any) -> str:
    return f'/sales-order/pdf/{_sales_billno_path_segment(billno)}'


def _sales_invoice_to_return_payload(
    location_code: int,
    invoice_billno: Any,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Load a posted sales invoice into a Sales Return form payload (header + lines)."""
    bno = coerce_billno(invoice_billno)
    if not billno_is_valid(bno):
        return None, 'Invoice bill number is required.'
    inv = get_sales_invoice_for_edit(location_code, bno)
    if not inv:
        return None, f'Sales invoice {bno} not found.'
    hdr = dict(inv.get('header') or {})
    lines = list(inv.get('lines') or [])
    st = str(hdr.get('billstatus') or 'P').strip().upper()
    if st == 'V':
        return None, f'Sales invoice {bno} is voided and cannot be returned.'
    delflag = str(hdr.get('delflag') or 'N').strip().upper()
    if delflag in ('Y', '1', 'T', 'TRUE'):
        return None, f'Sales invoice {bno} is deleted and cannot be returned.'
    rf = str(hdr.get('returnflag') or 'N').strip().upper()
    try:
        net = float(hdr.get('netbillamount') or 0)
    except (TypeError, ValueError):
        net = 0.0
    if rf == 'Y' or net < 0:
        return None, f'Bill {bno} is a sales return, not a sales invoice.'
    if not lines:
        return None, f'Sales invoice {bno} has no lines.'
    try:
        if int(hdr.get('customercode') or 0) <= 0:
            return None, f'Sales invoice {bno} has no customer.'
    except (TypeError, ValueError):
        return None, f'Sales invoice {bno} has invalid customer.'
    hdr_out = dict(hdr)
    hdr_out.pop('billno', None)
    hdr_out.pop('billdate', None)
    hdr_out.pop('billtime', None)
    hdr_out.pop('netbillamount', None)
    hdr_out.pop('returnflag', None)
    hdr_out.pop('delflag', None)
    hdr_out['source_invoice_billno'] = bno
    # Unique return reference (invoice billno is already used as SI #; reusing it
    # as ORDERNO can conflict / confuse save). Keep original SO/order ref in remarks.
    orig_ord = str(hdr.get('orderno') or '').strip()
    hdr_out['orderno'] = f'R{bno}'[:80]
    # BILLHDR.DISCOUNTAMOUNT is the sum of line ITDISC — already on each line.
    # Do not put it into additional_discount (that double-counts and changes net).
    hdr_out.pop('discountamount', None)
    hdr_out.pop('additional_discount', None)
    si_note = f'From SI #{bno}'
    if orig_ord and orig_ord.upper() not in (f'R{bno}'.upper(), str(bno)):
        si_note = f'{si_note}; Order ref {orig_ord}'
    existing_remarks = str(hdr_out.get('remarks') or '').strip()
    if si_note.lower() not in existing_remarks.lower():
        hdr_out['remarks'] = '; '.join(filter(None, [existing_remarks, si_note])).strip('; ')
    # Sales Return UI uses negative qty/amount (same as manually added lines).
    clean_lines: List[Dict[str, Any]] = []
    for ln in lines:
        if not isinstance(ln, dict):
            continue
        row = dict(ln)
        try:
            qty_mag = abs(float(row.get('quantity') or 0))
        except (TypeError, ValueError):
            qty_mag = 0.0
        if qty_mag <= 0:
            continue
        row['quantity'] = -qty_mag
        try:
            base_mag = abs(float(row.get('base_qty') if row.get('base_qty') is not None else qty_mag))
        except (TypeError, ValueError):
            base_mag = qty_mag
        row['base_qty'] = -base_mag
        try:
            disc_mag = abs(float(row.get('discount') or 0))
        except (TypeError, ValueError):
            disc_mag = 0.0
        row['discount'] = disc_mag
        try:
            rate_val = round(abs(float(row.get('rate') or 0)), 3)
        except (TypeError, ValueError):
            rate_val = 0.0
        row['rate'] = rate_val
        try:
            amt_mag = abs(float(row.get('amount') or 0))
        except (TypeError, ValueError):
            amt_mag = 0.0
        if amt_mag <= 1e-9:
            amt_mag = round(qty_mag * rate_val - disc_mag, 2)
            if amt_mag < 0:
                amt_mag = 0.0
        else:
            amt_mag = round(amt_mag, 2)
        # Exact negation of invoice line net (do not recompute via qty*rate-disc on save).
        row['amount'] = -amt_mag
        clean_lines.append(row)
    if not clean_lines:
        return None, f'Sales invoice {bno} has no returnable lines.'
    return {'header': hdr_out, 'lines': clean_lines}, None


def _source_order_billnos_from_header(header: Dict[str, Any]) -> List[Any]:
    raw_list = header.get('source_order_billnos')
    if isinstance(raw_list, list):
        return _parse_sales_order_billnos(','.join(str(x) for x in raw_list))
    if isinstance(raw_list, str):
        parsed = _parse_sales_order_billnos(raw_list)
        if parsed:
            return parsed
    raw_single = header.get('source_order_billno')
    if raw_single not in (None, ''):
        return _parse_sales_order_billnos(str(raw_single))
    return []


def _mark_converted_sales_orders(
    location_code: int,
    header: Dict[str, Any],
    invoice_billno: Any,
) -> Tuple[List[Any], Optional[str]]:
    marked: List[Any] = []
    warnings: List[str] = []
    for order_billno in _source_order_billnos_from_header(header):
        ok_mark, mark_err = mark_sales_order_invoiced(location_code, order_billno, invoice_billno)
        if ok_mark:
            marked.append(order_billno)
        elif mark_err:
            warnings.append(f'SO {order_billno}: {mark_err}')
    if warnings:
        return marked, '; '.join(warnings)
    return marked, None


def _prepare_sales_order_invoice_save(
    location_code: int,
    order_billno: Any,
    *,
    open_date: str,
    username: str,
    employeecode: Any = 0,
    countercode: Any = 0,
) -> Tuple[Optional[Dict[str, Any]], Optional[List[Dict[str, Any]]], Optional[str]]:
    """Build sales invoice header/lines from one pending sales order."""
    payload, err = _sales_order_convert_payload(location_code, order_billno)
    if err or not payload:
        return None, None, err or f'Sales order {order_billno} could not be loaded.'
    hdr = dict(payload.get('header') or {})
    lines = list(payload.get('lines') or [])
    if not lines:
        return None, None, f'Sales order {order_billno} has no lines.'
    try:
        if int(hdr.get('customercode') or 0) <= 0:
            return None, None, f'Sales order {order_billno} has no customer.'
    except (TypeError, ValueError):
        return None, None, f'Sales order {order_billno} has invalid customer.'
    customer_order_ref = str(hdr.get('orderno') or '').strip()
    order_no = str(order_billno).strip()
    hdr['orderno'] = order_no[:80]
    if customer_order_ref and customer_order_ref.upper() != order_no.upper():
        existing_remarks = str(hdr.get('remarks') or '').strip()
        po_note = f'Customer order ref {customer_order_ref}'
        if po_note.lower() not in existing_remarks.lower():
            hdr['remarks'] = '; '.join(filter(None, [existing_remarks, po_note])).strip('; ')
    hdr['location_code'] = location_code
    # Invoice Each / batch invoice: use the sales order bill date (not today's open date).
    raw_order_bd = hdr.get('billdate') if hdr.get('billdate') not in (None, '') else hdr.get('bill_date')
    if hasattr(raw_order_bd, 'strftime'):
        order_billdate = raw_order_bd.strftime('%Y-%m-%d')
    else:
        order_billdate = str(raw_order_bd or '').strip()[:10]
    if order_billdate:
        hdr['billdate'] = order_billdate
        resolved_bd, txn_err = _enforce_sales_open_bill_date(hdr, location_code, is_return=False)
        if txn_err:
            return None, None, f'Sales order {order_billno}: {txn_err}'
        hdr['billdate'] = resolved_bd or order_billdate
    else:
        hdr['billdate'] = open_date
    hdr['billtime'] = datetime.now().strftime('%H:%M:%S')
    hdr['createdby'] = username
    hdr['employeecode'] = employeecode
    hdr['countercode'] = countercode
    hdr['source_order_billno'] = order_billno
    hdr['source_order_billnos'] = [order_billno]
    line_err = _validate_sales_doc_save_lines(lines, doc_label='sales invoice')
    if line_err:
        return None, None, f'Sales order {order_billno}: {line_err}'
    return hdr, lines, None


def _invoice_one_sales_order(
    location_code: int,
    order_billno: Any,
    *,
    open_date: str,
    username: str,
    employeecode: Any = 0,
    countercode: Any = 0,
) -> Dict[str, Any]:
    """Post one sales invoice from a pending sales order."""
    hdr, lines, prep_err = _prepare_sales_order_invoice_save(
        location_code,
        order_billno,
        open_date=open_date,
        username=username,
        employeecode=employeecode,
        countercode=countercode,
    )
    if prep_err or not hdr or not lines:
        return {
            'order_billno': order_billno,
            'success': False,
            'error': prep_err or 'Prepare failed.',
        }
    existing_inv = find_invoice_billno_for_source_sales_order(location_code, order_billno)
    if existing_inv:
        marked_orders, mark_warning = _mark_converted_sales_orders(
            location_code,
            {'source_order_billno': order_billno, 'source_order_billnos': [order_billno]},
            coerce_billno(existing_inv),
        )
        row: Dict[str, Any] = {
            'order_billno': order_billno,
            'success': True,
            'invoice_billno': existing_inv,
            'already_invoiced': True,
            'pdf_url': url_for(
                'reports.crystal_reports_open_report',
                report_name='cashbilldup',
                billno=existing_inv,
            ),
            'stock_posted': False,
        }
        if marked_orders:
            row['marked_order_billnos'] = marked_orders
        if mark_warning:
            row['mark_warning'] = mark_warning
        return row
    ok, error, invoice_billno, stock_debug, billno_reassigned, req_no = _save_sales_doc_with_billno_retry(
        hdr,
        lines,
        location_code=location_code,
        doc_type=DOC_TYPE_SALES_INVOICE,
    )
    if not ok or not invoice_billno:
        return {
            'order_billno': order_billno,
            'success': False,
            'error': error or 'Save failed.',
        }
    marked_orders, mark_warning = _mark_converted_sales_orders(
        location_code,
        hdr,
        coerce_billno(invoice_billno),
    )
    row: Dict[str, Any] = {
        'order_billno': order_billno,
        'success': True,
        'invoice_billno': invoice_billno,
        'requested_billno': req_no,
        'billno_reassigned': billno_reassigned,
        'pdf_url': url_for(
            'reports.crystal_reports_open_report',
            report_name='cashbilldup',
            billno=invoice_billno,
        ),
        'stock_posted': bool((stock_debug or {}).get('stock_posted')),
    }
    if marked_orders:
        row['marked_order_billnos'] = marked_orders
    if mark_warning:
        row['mark_warning'] = mark_warning
    return row


def _batch_invoice_sales_orders(
    location_code: int,
    order_billnos: List[Any],
    *,
    username: str,
    employeecode: Any = 0,
    countercode: Any = 0,
) -> Dict[str, Any]:
    """Create one posted sales invoice per sales order."""
    open_date, txn_err = _enforce_sales_open_bill_date({}, location_code, is_return=False)
    if txn_err:
        return {
            'success': False,
            'error': txn_err,
            'transaction_date_blocked': True,
            'success_count': 0,
            'fail_count': len(order_billnos),
            'total_count': len(order_billnos),
            'results': [],
        }
    results: List[Dict[str, Any]] = []
    success_count = 0
    fail_count = 0
    for order_billno in order_billnos:
        result_row = _invoice_one_sales_order(
            location_code,
            order_billno,
            open_date=open_date or '',
            username=username,
            employeecode=employeecode,
            countercode=countercode,
        )
        results.append(result_row)
        if result_row.get('success'):
            success_count += 1
        else:
            fail_count += 1
    return {
        'success': success_count > 0,
        'success_count': success_count,
        'fail_count': fail_count,
        'total_count': len(order_billnos),
        'results': results,
    }


def _sales_list_tab(raw: Optional[str] = None) -> str:
    tab = (raw if raw is not None else request.args.get('tab') or 'invoice').strip().lower()
    if tab == 'return':
        return 'return'
    if tab == 'all':
        return 'all'
    return 'invoice'


def _sales_order_list_tab(raw: Optional[str] = None) -> str:
    tab = (raw if raw is not None else request.args.get('tab') or 'order').strip().lower()
    if tab in ('order', 'invoiced', 'cancelled', 'all'):
        return tab
    return 'order'


def _sales_list_date_defaults() -> Tuple[str, str]:
    today = datetime.now().date().strftime('%Y-%m-%d')
    return today, today


def _sales_list_customer_options(rows: List[Dict[str, Any]]) -> List[Tuple[str, str]]:
    seen: Dict[str, str] = {}
    for row in rows or []:
        code = str(row.get('customercode') or '').strip()
        if not code or code in seen:
            continue
        name = str(row.get('customername') or '').strip()
        seen[code] = name or code
    return sorted(seen.items(), key=lambda item: (item[1] or item[0]).upper())


def _sales_list_rows_unfiltered(
    location_code: int,
    search: str,
    date_from: str,
    date_to: str,
    tab: str,
) -> List[Dict[str, Any]]:
    return _sales_list_rows(location_code, search, date_from, date_to, tab, customer_code='')


def _sales_list_rows(
    location_code: int,
    search: str,
    date_from: str,
    date_to: str,
    tab: str,
    customer_code: str = '',
    perms: Optional[List[Any]] = None,
) -> List[Dict[str, Any]]:
    if tab == 'return':
        rows = get_sales_returns_list(
            location_code=location_code,
            search=search,
            date_from=date_from,
            date_to=date_to,
            customer_code=customer_code,
        )
        for r in rows:
            r['doc_type'] = 'return'
        return rows
    if tab == 'all':
        combined: List[Dict[str, Any]] = []
        if _sales_list_menu_allowed('invoice', perms):
            for r in get_sales_invoices_list(
                location_code=location_code,
                search=search,
                date_from=date_from,
                date_to=date_to,
                customer_code=customer_code,
            ):
                row = dict(r)
                row['doc_type'] = 'invoice'
                combined.append(row)
        if _sales_list_menu_allowed('return', perms):
            for r in get_sales_returns_list(
                location_code=location_code,
                search=search,
                date_from=date_from,
                date_to=date_to,
                customer_code=customer_code,
            ):
                row = dict(r)
                row['doc_type'] = 'return'
                combined.append(row)

        def _sort_key(row: Dict[str, Any]) -> Tuple[Any, Any]:
            bd = row.get('billdate')
            if bd is not None and hasattr(bd, 'strftime'):
                bd_key = bd.strftime('%Y-%m-%d')
            else:
                bd_key = str(bd or '')[:10]
            try:
                bno = int(row.get('billno') or 0)
            except (TypeError, ValueError):
                bno = 0
            return (bd_key, bno)

        combined.sort(key=_sort_key, reverse=True)
        return combined
    rows = get_sales_invoices_list(
        location_code=location_code,
        search=search,
        date_from=date_from,
        date_to=date_to,
        customer_code=customer_code,
    )
    for r in rows:
        r['doc_type'] = 'invoice'
    return rows


def _sales_list_role_permissions() -> List[Any]:
    """Load role permissions once per list request (shared by tab checks)."""
    from db import get_role_permissions, get_user_role_id

    user = session.get('user')
    if not user:
        return []
    if str(user).strip().lower() in ('admin', 'super'):
        return ['*']
    rid = get_user_role_id(str(user))
    return get_role_permissions(rid) if rid else []


def _sales_list_menu_allowed(tab: str, perms: Optional[List[Any]] = None) -> bool:
    from permissions import is_menu_path_allowed

    user = session.get('user')
    if not user:
        return False
    if str(user).strip().lower() in ('admin', 'super'):
        return True
    if perms is None:
        perms = _sales_list_role_permissions()
    if tab == 'all':
        return is_menu_path_allowed('sales.sales_invoice', perms) or is_menu_path_allowed('sales.sales_return', perms)
    path = 'sales.sales_return' if tab == 'return' else 'sales.sales_invoice'
    return is_menu_path_allowed(path, perms)


def _sales_summary_pdf_context() -> Dict[str, str]:
    company = get_company_profile() or {}
    branch_label = str(session.get('location_name') or '').strip()
    logo_path = ''
    try:
        tid = str(session.get('tenant_id') or '').strip()
        if tid:
            tenant = get_tenant_by_id(tid) or {}
            logo_rel = str(tenant.get('logo_path') or '').strip()
            if logo_rel:
                project_root = Path(__file__).resolve().parents[3]
                candidate = (project_root / 'static' / logo_rel).resolve()
                if candidate.exists():
                    logo_path = str(candidate)
    except Exception:
        pass
    return {
        'company_name': str(company.get('company_name') or company.get('legal_name') or branch_label or ''),
        'company_address': str(company.get('address1') or company.get('address') or ''),
        'company_phone': str(company.get('phone') or ''),
        'company_email': str(company.get('email') or ''),
        'branch_label': branch_label,
        'logo_path': logo_path,
    }


def _next_free_billno_for_save(
    location_code: int,
    countercode: Any,
    requested: Any,
    *,
    doc_type: str = DOC_TYPE_SALES_INVOICE,
) -> Tuple[Any, bool]:
    """Next unused bill number without incrementing DOC_NUMBER_SERIES (counter advances on save only)."""
    from addons.document_numbering.document_numbering_db import (
        _compute_next_series_no,
        format_document_no,
        get_document_series_by_type,
    )
    from db import _billno_storage_from_series

    req = parse_billno_from_request(requested)
    if billno_is_valid(req) and not billhdr_exists(location_code, req):
        return req, False

    series = get_document_series_by_type(doc_type, location_code=location_code)
    if not series:
        n = get_next_bill_no(location_code, countercode, doc_type=doc_type)
        return n, bool(billno_is_valid(req) and not billno_equal(n, req))

    start = max(1, int(series.get('starting_no') or 1))
    last = max(0, int(series.get('last_no_used') or 0))
    inc = max(1, int(series.get('increment_by') or 1))
    n = _compute_next_series_no(start, last, inc)
    for _ in range(100):
        formatted = format_document_no(series, n)
        candidate = _billno_storage_from_series(n, formatted)
        if not billhdr_exists(location_code, candidate):
            reassigned = bool(billno_is_valid(req) and not billno_equal(candidate, req))
            return candidate, reassigned
        n += inc
    raise RuntimeError('Could not find a free bill number. Click New and try again.')


def _resolve_sales_billno_for_save(
    location_code: int,
    countercode: Any,
    requested: Any,
    *,
    doc_type: str = DOC_TYPE_SALES_INVOICE,
) -> Tuple[Any, bool]:
    """Pick a free bill number for save (peeked number if still unused, else next free)."""
    return _next_free_billno_for_save(
        location_code, countercode, requested, doc_type=doc_type,
    )


def _save_sales_doc_with_billno_retry(
    header: Dict[str, Any],
    lines: List[Dict[str, Any]],
    *,
    location_code: int,
    doc_type: str = DOC_TYPE_SALES_INVOICE,
) -> Tuple[bool, str, Optional[Any], Dict[str, Any], bool, Any]:
    requested = header.get('billno')
    req_no = parse_billno_from_request(requested)
    try:
        billno, reassigned = _resolve_sales_billno_for_save(
            location_code, header.get('countercode'), requested, doc_type=doc_type,
        )
    except RuntimeError as e:
        return (False, str(e) or 'Could not allocate bill number.', None, {}, False, req_no)
    header = dict(header)
    header['billno'] = billno
    header['use_existing_billno'] = True
    last_err = ''
    for _ in range(8):
        ok, error, saved_billno, stock_debug = save_sales_invoice({'header': header, 'lines': lines})
        if ok:
            if (stock_debug or {}).get('already_posted'):
                try:
                    billno, reassigned = _next_free_billno_for_save(
                        location_code, header.get('countercode'), None, doc_type=doc_type,
                    )
                except RuntimeError as e:
                    return (False, str(e) or 'Could not allocate bill number.', None, {}, reassigned, req_no)
                header['billno'] = billno
                reassigned = True
                continue
            final_no = coerce_billno(saved_billno or billno or '')
            really_reassigned = bool(billno_is_valid(req_no) and billno_is_valid(final_no) and not billno_equal(final_no, req_no))
            return (True, '', final_no, stock_debug or {}, really_reassigned, req_no)
        last_err = error or 'Save failed'
        if not _is_duplicate_doc_key_error(last_err) and 'already used' not in last_err.lower() and 'no longer reserved' not in last_err.lower():
            break
        try:
            billno, reassigned = _next_free_billno_for_save(
                location_code, header.get('countercode'), billno, doc_type=doc_type,
            )
        except RuntimeError as e:
            return (False, str(e) or 'Could not allocate bill number.', None, {}, reassigned, req_no)
        header['billno'] = billno
        reassigned = True
    return (False, last_err, None, {}, reassigned, req_no)
_ADDON_ROOT = Path(__file__).resolve().parents[1]
bp = Blueprint('sales', __name__, template_folder=str(_ADDON_ROOT / 'views' / 'templates'))

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
        try:
            location_info = get_location_info_by_dbkey(None)
            location_code_int = location_info.get('locationcode')
            if location_code_int is None:
                location_code_int = 1
        except Exception as e:
            print(f'[DEBUG sales] Could not get location_code from LOCATIONMASTER: {e}')
            location_code_int = 1
    return int(location_code_int)

def _sales_warehouse_enabled() -> bool:
    try:
        return bool(is_location_warehouse_enabled(int(_resolve_location_code())))
    except Exception:
        return False

def _sales_bin_tracking_enabled() -> bool:
    try:
        loc = int(_resolve_location_code())
        return bool(_sales_warehouse_enabled() and is_location_bin_tracking_enabled(loc))
    except Exception:
        return False

def _sales_warehouse_picker_rows(search: str='', limit: int=300, *, doc_kind: str='sales', username: Optional[str]=None) -> List[Dict[str, str]]:
    """Active warehouses for sales header — ``code`` is ``WAREHOUSE_ID`` (same as purchase order)."""
    from db.user_warehouse_prefs import apply_user_warehouse_filter, build_warehouse_picker_rows

    loc = _resolve_location_code()
    rows = build_warehouse_picker_rows(int(loc), search=search, limit=limit)
    uname = username if username is not None else session.get('user')
    return apply_user_warehouse_filter(uname, doc_kind, rows)

def _sales_batch_tracking_enabled() -> bool:
    try:
        return bool(is_location_batch_tracking_enabled(int(_resolve_location_code())))
    except Exception:
        return False

def _sales_default_warehouse_context(doc_kind: str='sales') -> Dict[str, Any]:
    from db.user_warehouse_prefs import (
        get_user_default_warehouse_id,
        warehouse_display_label,
        warehouse_has_positive_stock,
    )

    wid = get_user_default_warehouse_id(session.get('user'), doc_kind)
    loc = _resolve_location_code()
    # Prefer a stocked warehouse when the configured default has only zero qty.
    if wid and not warehouse_has_positive_stock(int(wid), loc):
        for row in _sales_warehouse_picker_rows(limit=50, doc_kind=doc_kind, username=''):
            try:
                cand = int(row.get('code') or 0)
            except (TypeError, ValueError):
                cand = 0
            if cand > 0 and warehouse_has_positive_stock(cand, loc):
                wid = cand
                break
    label = warehouse_display_label(wid) if wid else ''
    wh_code = ''
    wh_name = ''
    if wid:
        try:
            from db import get_warehouse_master_by_id
            wh = get_warehouse_master_by_id(int(wid))
            if wh:
                wh_code = str(wh.get('warehouse_code') or '').strip()
                wh_name = str(wh.get('warehouse_name') or '').strip()
        except Exception:
            pass
    return {
        'default_warehouse_id': wid,
        'default_warehouse_code': wh_code,
        'default_warehouse_name': wh_name,
        'default_warehouse_label': label,
        'warehouse_doc_kind': doc_kind,
    }

def _sales_template_context(**extra: Any) -> Dict[str, Any]:
    loc = _resolve_location_code()
    try:
        flags = get_location_sales_feature_flags(loc)
    except Exception:
        flags = {
            'warehouse_enabled': _sales_warehouse_enabled(),
            'bin_tracking_enabled': _sales_bin_tracking_enabled(),
            'batch_tracking_enabled': _sales_batch_tracking_enabled(),
        }
    wh_on = bool(flags.get('warehouse_enabled'))
    bin_on = bool(flags.get('bin_tracking_enabled')) if wh_on else False
    batch_on = bool(flags.get('batch_tracking_enabled'))
    doc_kind = str(extra.pop('warehouse_doc_kind', 'sales') or 'sales')
    ctx: Dict[str, Any] = {
        'customers': [],
        # UOMs load on demand via item APIs; do not query UNITOFMEASUREMENT on every form open.
        'units': [],
        'sessions': [],
        'warehouse_enabled': wh_on,
        'bin_tracking_enabled': bin_on,
        'batch_tracking_enabled': batch_on,
        'si_table_colspan': (10 if wh_on else 11) + (1 if wh_on else 0) + (1 if bin_on else 0) + (1 if batch_on else 0),
        'sales_warehouses_api': url_for('sales.api_sales_warehouses') if wh_on else None,
        'sales_warehouses_picker': url_for('sales.sales_warehouses_picker') if wh_on else None,
        'sales_warehouse_bins_api': url_for('sales.api_sales_warehouse_bins') if bin_on else None,
        'sales_item_bin_inventory_api': url_for('sales.sales_item_bin_inventory') if bin_on else None,
        'openai_configured': bool((os.environ.get('OPENAI_API_KEY') or '').strip()),
        'minus_billing_enabled': False,
        'location_code': loc,
    }
    if wh_on:
        ctx.update(_sales_default_warehouse_context(doc_kind))
    ctx.update(extra)
    return ctx

@bp.route('/sales/api/warehouses')
def api_sales_warehouses():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    q = (request.args.get('q') or '').strip()
    try:
        lim = int(request.args.get('limit', 300))
    except (TypeError, ValueError):
        lim = 300
    doc_kind = (request.args.get('doc_kind') or 'sales').strip().lower() or 'sales'
    try:
        rows = _sales_warehouse_picker_rows(search=q, limit=lim, doc_kind=doc_kind)
        return jsonify({'success': True, 'warehouses': rows})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc), 'warehouses': []}, 500)

@bp.route('/sales/warehouses-picker', methods=['GET'])
def sales_warehouses_picker():
    """JSON warehouse rows for sales pickers (search + cap; same pattern as customers-picker)."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not logged in'}, 401)
    q = (request.args.get('q') or '').strip()
    try:
        lim = int(request.args.get('limit', 300))
    except (TypeError, ValueError):
        lim = 300
    doc_kind = (request.args.get('doc_kind') or 'sales').strip().lower() or 'sales'
    try:
        rows = _sales_warehouse_picker_rows(search=q, limit=lim, doc_kind=doc_kind)
        return jsonify({'success': True, 'warehouses': rows})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}, 500)

@bp.route('/sales/api/form-settings', methods=['GET'])
def sales_api_form_settings():
    """Live Sales Invoice / Sales Return form flags (avoids stale page after config change)."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    return jsonify({
        'success': True,
        'order_no_mandatory_invoice': get_sales_orderno_mandatory_invoice_enabled(),
        'order_no_mandatory_return': get_sales_orderno_mandatory_return_enabled(),
        'order_no_mandatory_order': get_sales_orderno_mandatory_order_enabled(),
    })

@bp.route('/sales')
def sales_invoice():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    location_code_int = _resolve_location_code()
    from_orders_raw = (request.args.get('from_orders') or '').strip()
    from_order_raw = (request.args.get('from_order') or '').strip()
    order_billnos = _parse_sales_order_billnos(from_orders_raw)
    if not order_billnos and from_order_raw:
        order_billnos = _parse_sales_order_billnos(from_order_raw)
    if not order_billnos and from_order_raw:
        bn = parse_billno_from_request(from_order_raw)
        if billno_is_valid(bn):
            order_billnos = [coerce_billno(bn)]
    initial_order = None
    convert_from_orders: List[Any] = []
    convert_error = None
    if order_billnos:
        convert_from_orders = order_billnos
        initial_order, convert_error = _sales_orders_convert_payload(location_code_int, order_billnos)
    initial_bill_no = None
    if not initial_order:
        try:
            initial_bill_no = peek_next_bill_no(
                location_code_int, _session_countercode_optional(), doc_type=DOC_TYPE_SALES_INVOICE,
            )
        except Exception as e:
            print(f'[WARN sales_invoice] Could not peek initial bill no: {e}')
    return render_template(
        'sales/sales.html',
        **_sales_template_context(
            **_sales_bill_date_context(is_return=False),
            page_title='Sales Invoice',
            next_bill_base='/sales',
            save_base='/sales',
            print_base='/sales',
            enable_print='1',
            draft_key='sales_draft',
            warehouse_doc_kind='sales',
            minus_billing_enabled=get_sales_minus_billing_invoice_enabled(),
            order_no_mandatory=get_sales_orderno_mandatory_invoice_enabled(),
            list_url=url_for('sales.sales_invoice_list', tab='invoice'),
            initial_bill_no=initial_bill_no,
            initial_order=initial_order,
            initial_order_json=_json_for_script(initial_order) if initial_order else 'null',
            convert_from_orders=convert_from_orders,
            convert_from_orders_json=_json_for_script(convert_from_orders or []),
            convert_error=convert_error,
        ),
    )

@bp.route('/sales/load-from-order/<path:billno>', methods=['GET'])
def sales_load_from_order(billno: str):
    """Load a pending sales order as JSON for sales invoice conversion."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    location_code_int = _resolve_location_code()
    bn = parse_billno_from_request(billno)
    if not billno_is_valid(bn):
        return jsonify({'success': False, 'error': 'Invalid sales order number.'}, 400)
    payload, err = _sales_orders_convert_payload(location_code_int, [bn])
    if err or not payload:
        return jsonify({'success': False, 'error': err or 'Sales order not found.'}, 404)
    return jsonify({
        'success': True,
        'order': payload,
        'source_order_billno': bn,
        'source_order_billnos': [bn],
    })

@bp.route('/sales/invoice-templates', methods=['GET'])
def sales_invoice_templates():
    """Gallery of selectable sales invoice PDF layouts."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    from addons.reports.invoice_templates import get_saved_invoice_template, list_invoice_templates

    return render_template(
        'sales/invoice_templates.html',
        page_title='Invoice Templates',
        templates=list_invoice_templates(),
        current_template=get_saved_invoice_template(),
        preview_url=url_for('reports.invoice_template_preview'),
        prefer_url=url_for('sales.sales_invoice_template_prefer'),
    )


@bp.route('/sales/invoice-templates/prefer', methods=['GET', 'POST'])
def sales_invoice_template_prefer():
    """Get or set the tenant-wide sales invoice PDF template (web + mobile)."""
    if not session.get('user'):
        return jsonify({'success': False, 'message': 'Login required'}), 401
    from addons.reports.invoice_templates import get_saved_invoice_template_info, set_saved_invoice_template

    if request.method == 'GET':
        info = get_saved_invoice_template_info()
        return jsonify({'success': True, 'template': info['template'], 'saved': bool(info.get('saved'))})

    data = request.get_json(silent=True) or {}
    raw = data.get('template') if isinstance(data, dict) else None
    if raw is None:
        raw = request.form.get('template') or request.args.get('template')
    try:
        key = set_saved_invoice_template(raw)
    except Exception as exc:
        return jsonify({'success': False, 'message': str(exc)}), 500
    return jsonify({'success': True, 'template': key, 'saved': True})


@bp.route('/sales/accounts-configuration', methods=['GET', 'POST'])
def sales_accounts_configuration():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if request.method == 'POST':
        invoice_enabled = str(request.form.get('minus_billing_invoice') or '').strip() == 'Y'
        order_enabled = str(request.form.get('minus_billing_order') or '').strip() == 'Y'
        orderno_mandatory_invoice = str(request.form.get('orderno_mandatory_invoice') or '').strip() == 'Y'
        orderno_mandatory_return = str(request.form.get('orderno_mandatory_return') or '').strip() == 'Y'
        orderno_mandatory_order = str(request.form.get('orderno_mandatory_order') or '').strip() == 'Y'
        direct_posting_invoice = str(request.form.get('direct_posting_invoice') or '').strip() == 'Y'
        direct_posting_return = str(request.form.get('direct_posting_return') or '').strip() == 'Y'
        ok_mb, err_mb = set_sales_minus_billing(
            invoice_enabled, order_enabled, updated_by=session.get('user') or 'web',
        )
        ok_on, err_on = set_sales_orderno_mandatory(
            orderno_mandatory_invoice, orderno_mandatory_return, orderno_mandatory_order,
            updated_by=session.get('user') or 'web',
        )
        ok_dp, err_dp = set_sales_direct_posting(
            direct_posting_invoice,
            return_enabled=direct_posting_return,
            updated_by=session.get('user') or 'web',
        )
        if ok_mb and ok_on and ok_dp:
            flash('Sales accounts configuration saved.', 'success')
        else:
            parts = [p for p in (err_mb, err_on, err_dp) if p]
            flash(f'Save failed: {"; ".join(parts) or "Unknown error"}', 'error')
        return redirect(url_for('sales.sales_accounts_configuration'))
    return render_template(
        'sales/sales_accounts_configuration.html',
        page_title='Sales Accounts Configuration',
        minus_billing_invoice_enabled=get_sales_minus_billing_invoice_enabled(),
        minus_billing_order_enabled=get_sales_minus_billing_order_enabled(),
        orderno_mandatory_invoice_enabled=get_sales_orderno_mandatory_invoice_enabled(),
        orderno_mandatory_return_enabled=get_sales_orderno_mandatory_return_enabled(),
        orderno_mandatory_order_enabled=get_sales_orderno_mandatory_order_enabled(),
        direct_posting_invoice_enabled=get_sales_direct_posting_enabled(),
        direct_posting_return_enabled=get_sales_direct_posting_return_enabled(),
    )

@bp.route('/sales/list')
def sales_invoice_list():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    tab = _sales_list_tab()
    role_perms = _sales_list_role_permissions()
    if not _sales_list_menu_allowed(tab, role_perms):
        if tab == 'return' and _sales_list_menu_allowed('invoice', role_perms):
            return redirect(url_for('sales.sales_invoice_list', tab='invoice'))
        if tab == 'invoice' and _sales_list_menu_allowed('return', role_perms):
            return redirect(url_for('sales.sales_invoice_list', tab='return'))
        abort(403)
    location_code_int = _resolve_location_code()
    search = (request.args.get('search') or '').strip()
    date_from = (request.args.get('date_from') or '').strip()
    date_to = (request.args.get('date_to') or '').strip()
    customer_code = (request.args.get('customer_code') or '').strip()
    if not date_from and (not date_to):
        date_from, date_to = _sales_list_date_defaults()
    rows = _sales_list_rows(
        location_code_int, search, date_from, date_to, tab, customer_code, perms=role_perms
    )
    # Avoid a second full BILLHDR scan when the customer filter is empty.
    if customer_code:
        customer_options = _sales_list_customer_options(
            _sales_list_rows_unfiltered(location_code_int, search, date_from, date_to, tab)
        )
    else:
        customer_options = _sales_list_customer_options(rows)
    summary = sales_invoice_list_summary_stats(rows, doc_kind=tab)
    return render_template(
        'sales/sales_invoice_list.html',
        invoices=rows,
        active_tab=tab,
        can_invoice=_sales_list_menu_allowed('invoice', role_perms),
        can_return=_sales_list_menu_allowed('return', role_perms),
        search=search,
        date_from=date_from,
        date_to=date_to,
        customer_code=customer_code,
        customer_options=customer_options,
        summary=summary,
    )

@bp.route('/sales/export')
def sales_invoice_export():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    tab = _sales_list_tab()
    if not _sales_list_menu_allowed(tab):
        abort(403)
    location_code_int = _resolve_location_code()
    search = (request.args.get('search') or '').strip()
    date_from = (request.args.get('date_from') or '').strip()
    date_to = (request.args.get('date_to') or '').strip()
    customer_code = (request.args.get('customer_code') or '').strip()
    rows = _sales_list_rows(location_code_int, search, date_from, date_to, tab, customer_code)
    output = io.StringIO()
    writer = csv.writer(output)
    include_doc = tab == 'all'
    if include_doc:
        writer.writerow(['Doc Type', 'Bill No', 'Bill Date', 'Customer Code', 'Customer Name', 'Order No', 'Total Amount', 'Discount Amount', 'Net Amount', 'Status', 'Pay Type', 'Created By', 'Remarks'])
    else:
        writer.writerow(['Bill No', 'Bill Date', 'Customer Code', 'Customer Name', 'Order No', 'Total Amount', 'Discount Amount', 'Net Amount', 'Status', 'Bill Type', 'Created By', 'Remarks'])
    for row in rows:
        billdate = row.get('billdate')
        if hasattr(billdate, 'strftime'):
            billdate = billdate.strftime('%Y-%m-%d')
        elif billdate:
            billdate = str(billdate)[:10]
        else:
            billdate = ''
        row_is_return = tab == 'return' or (row.get('doc_type') or '').strip().lower() == 'return'
        try:
            amt_raw = float(row.get('netbillamount') or 0)
        except (TypeError, ValueError):
            amt_raw = 0.0
        try:
            disc_raw = float(row.get('discountamount') or 0)
        except (TypeError, ValueError):
            disc_raw = 0.0
        try:
            total_raw = float(row.get('totalamount') if row.get('totalamount') is not None else (amt_raw + disc_raw))
        except (TypeError, ValueError):
            total_raw = amt_raw + disc_raw
        amt = abs(amt_raw) if row_is_return else amt_raw
        disc = abs(disc_raw) if row_is_return else disc_raw
        total_amt = abs(total_raw) if row_is_return else total_raw
        base = [
            row.get('billno') or '',
            billdate,
            row.get('customercode') or '',
            row.get('customername') or '',
            row.get('orderno') or '',
            total_amt,
            disc,
            amt,
            row.get('billstatus') or '',
            _sales_billtype_label(row.get('billtype')),
            row.get('createdby') or '',
            row.get('remarks') or '',
        ]
        if include_doc:
            doc_label = 'Sales Return' if row_is_return else 'Sales Invoice'
            writer.writerow([doc_label] + base)
        else:
            writer.writerow(base)
    data = io.BytesIO(output.getvalue().encode('utf-8-sig'))
    if tab == 'return':
        prefix = 'sales_return_list'
    elif tab == 'all':
        prefix = 'sales_all_list'
    else:
        prefix = 'sales_invoice_list'
    return send_file(data, mimetype='text/csv', as_attachment=True, download_name=f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")

@bp.route('/sales/summary-pdf')
def sales_invoice_summary_pdf():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    tab = _sales_list_tab()
    if not _sales_list_menu_allowed(tab):
        abort(403)
    location_code_int = _resolve_location_code()
    search = (request.args.get('search') or '').strip()
    date_from = (request.args.get('date_from') or '').strip()
    date_to = (request.args.get('date_to') or '').strip()
    customer_code = (request.args.get('customer_code') or '').strip()
    rows = _sales_list_rows(location_code_int, search, date_from, date_to, tab, customer_code)
    ctx = _sales_summary_pdf_context()
    pdf_bytes, err = build_sales_invoice_summary_pdf(
        rows,
        date_from=date_from,
        date_to=date_to,
        search=search,
        company_name=ctx['company_name'],
        company_address=ctx['company_address'],
        company_phone=ctx['company_phone'],
        company_email=ctx['company_email'],
        branch_label=ctx['branch_label'],
        logo_path=ctx['logo_path'],
        billtype_label_fn=_sales_billtype_label,
        doc_kind=tab,
    )
    if err:
        return (err, 500)
    if tab == 'return':
        fname = 'sales_return_summary.pdf'
    elif tab == 'all':
        fname = 'sales_combined_summary.pdf'
    else:
        fname = 'sales_invoice_summary.pdf'
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=False,
        download_name=fname,
    )

@bp.route('/sales/customers-picker', methods=['GET'])
def sales_customers_picker():
    """JSON customer rows for sales pickers (capped; avoids huge HTML pages)."""
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

@bp.route('/sales/loyalty-customers-picker', methods=['GET'])
def sales_loyalty_customers_picker():
    """JSON loyalty customer rows from CUSTOMERLOYALTY for sales invoice picker."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not logged in'}, 401)
    q = (request.args.get('q') or '').strip()
    try:
        lim = int(request.args.get('limit', 300))
    except (TypeError, ValueError):
        lim = 300
    lim = max(1, min(lim, 500))
    location_code_int = _resolve_location_code()
    try:
        rows = get_customer_loyalty_for_picker(location_code_int, picker_search=q, picker_limit=lim)
        return jsonify({'success': True, 'customers': rows})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}, 500)

@bp.route('/sales-return')
def sales_return():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    location_code_int = _resolve_location_code()
    initial_bill_no = None
    try:
        initial_bill_no = get_next_bill_no(
            location_code_int, _session_countercode_optional(), doc_type=DOC_TYPE_SALES_RETURN,
        )
    except Exception as e:
        print(f'[WARN sales_return] Could not reserve initial bill no: {e}')
    initial_order = None
    convert_error = None
    from_invoice_raw = (request.args.get('from_invoice') or request.args.get('invoice_billno') or '').strip()
    if from_invoice_raw:
        initial_order, convert_error = _sales_invoice_to_return_payload(
            location_code_int, parse_billno_from_request(from_invoice_raw),
        )
    return render_template(
        'sales/sales_return.html',
        **_sales_template_context(
            **_sales_bill_date_context(is_return=True),
            page_title='Sales Return',
            next_bill_base='/sales-return',
            save_base='/sales-return',
            print_base='/sales-return',
            enable_print='1',
            draft_key='sales_return_draft',
            is_sales_return=True,
            warehouse_doc_kind='sales_return',
            initial_bill_no=initial_bill_no,
            initial_order=initial_order,
            convert_error=convert_error,
            from_invoice_billno=parse_billno_from_request(from_invoice_raw) if from_invoice_raw else None,
            list_url=url_for('sales.sales_invoice_list', tab='return'),
            order_no_mandatory=get_sales_orderno_mandatory_return_enabled(),
        ),
    )


@bp.route('/sales-return/load-from-invoice/<path:billno>', methods=['GET'])
def sales_return_load_from_invoice(billno: str):
    """Load a posted sales invoice into Sales Return form payload."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    location_code_int = _resolve_location_code()
    bn = parse_billno_from_request(billno)
    payload, err = _sales_invoice_to_return_payload(location_code_int, bn)
    if err or not payload:
        return jsonify({'success': False, 'error': err or 'Invoice not found.'}, 404)
    return jsonify({
        'success': True,
        'header': payload.get('header') or {},
        'lines': payload.get('lines') or [],
        'source_invoice_billno': bn,
    })


@bp.route('/sales-return/list')
def sales_return_list():
    return redirect(url_for('sales.sales_invoice_list', tab='return'))

@bp.route('/sales-order')
def sales_order():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    location_code_int = _resolve_location_code()
    order_billno = (request.args.get('billno') or '').strip()
    initial_order = None
    if order_billno:
        initial_order = get_sales_order_for_edit(location_code_int, parse_billno_from_request(order_billno))
    initial_bill_no = None
    if not initial_order:
        try:
            initial_bill_no = peek_next_bill_no(
                location_code_int, _session_countercode_optional(), doc_type=DOC_TYPE_SALES_ORDER,
            )
        except Exception as e:
            print(f'[WARN sales_order] Could not peek initial bill no: {e}')
    convert_error = None
    if order_billno and not initial_order:
        convert_error = f'Sales order {order_billno} not found.'
    # Prefill bill date from the order when editing only if it is inside the open range.
    bill_ctx = _sales_bill_date_context(is_return=False)
    if initial_order and isinstance(initial_order.get('header'), dict):
        order_bd = str((initial_order.get('header') or {}).get('billdate') or '').strip()[:10]
        d_from = str(bill_ctx.get('bill_date_from') or '').strip()[:10]
        d_to = str(bill_ctx.get('bill_date_to') or d_from).strip()[:10]
        if order_bd and d_from and d_to and d_from <= order_bd <= d_to:
            bill_ctx['bill_date'] = order_bd
    return render_template(
        'sales/sales.html',
        **_sales_template_context(
            **bill_ctx,
            page_title='Sales Order',
            next_bill_base='/sales-order',
            save_base='/sales-order',
            print_base='/sales-order',
            enable_print='1',
            draft_key='sales_order_draft',
            warehouse_doc_kind='sales',
            minus_billing_enabled=get_sales_minus_billing_order_enabled(),
            order_no_mandatory=get_sales_orderno_mandatory_order_enabled(),
            initial_order=initial_order,
            initial_order_json=_json_for_script(initial_order) if initial_order else 'null',
            convert_error=convert_error,
            initial_bill_no=initial_bill_no,
            list_url=url_for('sales.sales_order_list'),
        ),
    )

@bp.route('/sales-order/load/<path:billno>', methods=['GET'])
def sales_order_load(billno: str):
    """Load one sales order as JSON for edit (fallback when embedded payload is missing)."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    location_code_int = _resolve_location_code()
    bn = parse_billno_from_request(billno)
    if not billno_is_valid(bn):
        return jsonify({'success': False, 'error': 'Invalid sales order number.'}, 400)
    order = get_sales_order_for_edit(location_code_int, bn)
    if not order:
        return jsonify({'success': False, 'error': f'Sales order {bn} not found.'}, 404)
    return jsonify({'success': True, 'order': order, 'billno': bn})


@bp.route('/sales-order/list')
def sales_order_list():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    location_code_int = _resolve_location_code()
    tab = _sales_order_list_tab()
    search = (request.args.get('search') or '').strip()
    date_from = (request.args.get('date_from') or '').strip()
    date_to = (request.args.get('date_to') or '').strip()
    if not date_from and (not date_to):
        date_from, date_to = _sales_list_date_defaults()
    orders = get_sales_orders_list(
        location_code=location_code_int,
        search=search,
        date_from=date_from,
        date_to=date_to,
        status_tab=tab,
    )
    return render_template(
        'sales/sales_order_list.html',
        orders=orders,
        active_tab=tab,
        search=search,
        date_from=date_from,
        date_to=date_to,
    )

@bp.route('/sales-order/export')
def sales_order_export():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    location_code_int = _resolve_location_code()
    tab = _sales_order_list_tab()
    search = (request.args.get('search') or '').strip()
    date_from = (request.args.get('date_from') or '').strip()
    date_to = (request.args.get('date_to') or '').strip()
    orders = get_sales_orders_list(
        location_code=location_code_int,
        search=search,
        date_from=date_from,
        date_to=date_to,
        status_tab=tab,
    )
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Bill No', 'Bill Date', 'Customer Code', 'Customer Name', 'Order No', 'Net Amount', 'Status', 'Remarks'])
    for row in orders:
        billdate = row.get('billdate')
        if hasattr(billdate, 'strftime'):
            billdate = billdate.strftime('%Y-%m-%d')
        elif billdate:
            billdate = str(billdate)[:10]
        else:
            billdate = ''
        writer.writerow([row.get('billno') or '', billdate, row.get('customercode') or '', row.get('customername') or '', row.get('orderno') or '', row.get('netbillamount') or 0, row.get('billstatus') or '', row.get('remarks') or ''])
    data = io.BytesIO(output.getvalue().encode('utf-8-sig'))
    return send_file(data, mimetype='text/csv', as_attachment=True, download_name=f"sales_order_list_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")

def _session_countercode_optional():
    countercode = session.get('countercode')
    try:
        return int(countercode) if countercode is not None else None
    except (TypeError, ValueError):
        return None

def _json_next_billno(location_code_int: int, *, doc_type: str = DOC_TYPE_SALES_INVOICE):
    """Reserve (default) or peek next bill number — shared by sales invoice, return, and order."""
    countercode = _session_countercode_optional()
    peek_only = (request.args.get('peek') or '').strip().lower() in ('1', 'true', 'yes')
    if peek_only:
        next_billno = _peek_next_billno_after_save(location_code_int, doc_type=doc_type)
        if not billno_is_valid(next_billno):
            next_billno = peek_next_bill_no(location_code_int, countercode, doc_type=doc_type)
        return jsonify({'success': True, 'billno': next_billno, 'reserved': False})
    try:
        next_billno = get_next_bill_no(location_code_int, countercode, lock_wait_seconds=3, doc_type=doc_type)
    except RuntimeError as e:
        return jsonify({'success': False, 'error': str(e), 'billno_busy': True}, 503)
    return jsonify({'success': True, 'billno': next_billno, 'reserved': True})


def _peek_next_billno_after_save(location_code_int: int, *, doc_type: str, after_billno: Any = None) -> Any:
    """Next unused bill number for a fresh form after a successful save."""
    try:
        peek = peek_next_bill_no(location_code_int, _session_countercode_optional(), doc_type=doc_type)
        if (
            billno_is_valid(peek)
            and (not billno_is_valid(after_billno) or not billno_equal(peek, after_billno))
            and not billhdr_exists(location_code_int, peek)
        ):
            return peek
        nxt, _ = _next_free_billno_for_save(
            location_code_int,
            _session_countercode_optional(),
            after_billno if billno_is_valid(after_billno) else peek,
            doc_type=doc_type,
        )
        return nxt
    except Exception as e:
        print(f'[WARN _peek_next_billno_after_save] {e}')
        return None

@bp.route('/sales/next-billno', methods=['GET'])
def sales_next_billno():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    location_code_int = _resolve_location_code()
    return _json_next_billno(location_code_int, doc_type=DOC_TYPE_SALES_INVOICE)

@bp.route('/sales-return/next-billno', methods=['GET'])
def sales_return_next_billno():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    location_code_int = _resolve_location_code()
    return _json_next_billno(location_code_int, doc_type=DOC_TYPE_SALES_RETURN)

@bp.route('/sales/ai-screenshot-lines', methods=['POST'])
def sales_ai_screenshot_lines():
    """Same AI line extraction as POS (image / PDF / pasted text → ITEMMASTER match)."""
    from addons.pos_billing.controllers.routes import pos_ai_screenshot_lines
    return pos_ai_screenshot_lines()


@bp.route('/sales/ai-snoonu-customer', methods=['GET'])
def sales_ai_snoonu_customer():
    """Fetch (or create) the SNOONU bill-to customer for Sales Invoice."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        from addons.pos_billing.controllers.routes import _apply_active_connection
        _apply_active_connection(user_dbkey)
    try:
        from addons.sales.services.snoonu_invoice import ensure_snoonu_bill_customer
        return jsonify(ensure_snoonu_bill_customer())
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}, 400)
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}, 500)


@bp.route('/sales/ai-snoonu-invoice', methods=['POST'])
def sales_ai_snoonu_invoice():
    """Import a Snoonu invoice: bill to SNOONU, create loyalty by mobile, fill item/qty/amount."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    if not (os.environ.get('OPENAI_API_KEY') or '').strip():
        return jsonify({'success': False, 'error': 'OPENAI_API_KEY is not configured on the server.'}, 503)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        from addons.pos_billing.controllers.routes import _apply_active_connection
        _apply_active_connection(user_dbkey)
    text = ''
    raw = None
    mime = 'image/png'
    filename = ''
    upload = request.files.get('image') or request.files.get('file')
    if upload and (upload.filename or '').strip():
        raw = upload.read()
        mime = str(getattr(upload, 'content_type', None) or getattr(upload, 'mimetype', None) or 'image/png')
        filename = str(upload.filename or '')
        text = str(request.form.get('text') or '').strip()
    else:
        payload = request.get_json(silent=True) or {}
        text = str(payload.get('text') or request.form.get('text') or '').strip()
        b64 = payload.get('image_base64')
        if isinstance(b64, str) and b64.strip():
            try:
                raw = base64.b64decode(b64.split(',', 1)[-1].strip())
            except Exception:
                return jsonify({'success': False, 'error': 'Invalid image_base64.'}, 400)
            mime = str(payload.get('mime') or 'image/png')
    try:
        from addons.sales.services.snoonu_invoice import import_snoonu_invoice
        data = import_snoonu_invoice(text=text, image_bytes=raw, mime=mime, filename=filename)
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}, 400)
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}, 500)
    if not data.get('success') and data.get('already_saved'):
        return jsonify(data, 409)
    return jsonify(data)

@bp.route('/sales-return/ai-screenshot-lines', methods=['POST'])
def sales_return_ai_screenshot_lines():
    """Same AI line extraction as sales invoice (return screen)."""
    return sales_ai_screenshot_lines()

@bp.route('/sales/item-info', methods=['GET'])
def sales_item_info():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    query = (request.args.get('query') or '').strip()
    if not query:
        return jsonify({'success': False, 'error': 'Missing query'}, 400)
    location_code_int = _resolve_location_code()
    item_data = None
    if query.isdigit():
        try:
            item_data = get_item_by_code(int(query), location_code_int)
        except Exception:
            item_data = None
    if not item_data:
        item_data = get_item_by_manufacturer_id(query, location_code_int)
    if not item_data:
        item_data = get_item_by_alternate_barcode(query, location_code_int)
    if not item_data:
        return jsonify({'success': False, 'error': 'Item not found'}, 404)
    return jsonify({'success': True, 'item': item_data})

@bp.route('/sales-return/item-info', methods=['GET'])
def sales_return_item_info():
    return sales_item_info()

@bp.route('/sales/uom-info', methods=['GET'])
def sales_uom_info():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
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

@bp.route('/sales-return/uom-info', methods=['GET'])
def sales_return_uom_info():
    return sales_uom_info()

@bp.route('/sales/item-uoms', methods=['GET'])
def sales_item_uoms():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    item_code = (request.args.get('item_code') or '').strip()
    if not item_code:
        return jsonify({'success': False, 'error': 'Missing item code'}, 400)
    location_code_int = _resolve_location_code()
    try:
        item = get_item_by_code(int(item_code), location_code_int)
    except Exception:
        item = None
    if not item:
        return jsonify({'success': False, 'error': 'Item not found'}, 404)
    base_uom = (item.get('baseuom') or '').strip()
    uoms = []
    if base_uom:
        uoms.append({'code': base_uom, 'name': base_uom, 'is_base': True})
    alternates = get_item_alternate_uoms(location_code_int, int(item_code))
    for alt in alternates:
        alt_code = (alt.get('alternateuomcode') or '').strip()
        if not alt_code:
            continue
        if base_uom and alt_code.upper() == base_uom.upper():
            continue
        uoms.append({'code': alt_code, 'name': alt_code, 'is_base': False, 'conversion_factor': alt.get('conversionfactor')})
    return jsonify({'success': True, 'uoms': uoms})

@bp.route('/sales-return/item-uoms', methods=['GET'])
def sales_return_item_uoms():
    return sales_item_uoms()

@bp.route('/sales/item-inventory', methods=['GET'])
def sales_item_inventory():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    item_code = (request.args.get('item_code') or '').strip()
    if not item_code:
        return jsonify({'success': False, 'error': 'Missing item code'}, 400)
    location_code_int = _resolve_location_code()
    try:
        item_code_int = int(item_code)
    except Exception:
        return jsonify({'success': False, 'error': 'Invalid item code'}, 400)
    if _sales_warehouse_enabled():
        rows = get_item_store_inventory(location_code_int, item_code_int)
    else:
        rows = get_item_store_rows_from_itemmaster(item_code_int, location_code_int) or []
        if not rows:
            rows = get_item_store_inventory(location_code_int, item_code_int)
    best = None
    if rows:
        best_row = max(rows, key=lambda row: float(row.get('stock') or 0))
        best = {'store': best_row.get('store'), 'stock': best_row.get('stock')}
    return jsonify({'success': True, 'items': rows, 'best': best})

@bp.route('/sales/api/warehouse-bins')
def api_sales_warehouse_bins():
    """BIN + STAGING rows for a warehouse (sales line picker)."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    wh = (request.args.get('wh') or request.args.get('warehouse_id') or '').strip()
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
    return jsonify({'success': True, 'warehouse_id': wh, 'bins': bins})

@bp.route('/sales/item-bin-inventory', methods=['GET'])
def sales_item_bin_inventory():
    """Bins with stock for an item at a warehouse (sales line auto-select / picker)."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    if not _sales_bin_tracking_enabled():
        return jsonify({'success': True, 'bins': []})
    item_code = (request.args.get('item_code') or '').strip()
    wh_raw = (request.args.get('warehouse_id') or request.args.get('wh') or '').strip()
    if not item_code or not wh_raw:
        return jsonify({'success': False, 'error': 'Missing item code or warehouse'}, 400)
    location_code_int = _resolve_location_code()
    try:
        item_code_int = int(item_code)
        warehouse_id_int = int(float(wh_raw))
    except Exception:
        return jsonify({'success': False, 'error': 'Invalid item code or warehouse'}, 400)
    rows = get_bin_stock_list(str(warehouse_id_int), location_code_int, item_code=item_code_int, include_zero=False) or []
    bins: List[Dict[str, Any]] = []
    seen: Set[int] = set()
    for r in rows:
        try:
            sid = int(float(r.get('storage_id') or 0))
        except (TypeError, ValueError):
            continue
        if sid <= 0 or sid in seen:
            continue
        seen.add(sid)
        try:
            stock = float(r.get('qty') or 0)
        except (TypeError, ValueError):
            stock = 0.0
        bins.append({
            'storage_id': sid,
            'code': str(r.get('bin_code') or '').strip(),
            'name': str(r.get('bin_name') or '').strip(),
            'stock': stock,
        })
    item_row = get_item_by_code(item_code_int, location_code_int) or {}
    default_bin_raw = item_row.get('default_bin_storage_id')
    try:
        default_bin_id = int(float(default_bin_raw)) if default_bin_raw not in (None, '') else 0
    except (TypeError, ValueError):
        default_bin_id = 0
    if default_bin_id > 0 and default_bin_id not in seen:
        for pick in list_warehouse_picker_bins(warehouse_id_int) or []:
            try:
                psid = int(float(pick.get('storage_id') or 0))
            except (TypeError, ValueError):
                continue
            if psid != default_bin_id:
                continue
            bins.append({
                'storage_id': psid,
                'code': str(pick.get('code') or '').strip(),
                'name': str(pick.get('name') or '').strip(),
                'stock': 0.0,
            })
            break
    return jsonify({'success': True, 'bins': bins, 'default_bin_storage_id': default_bin_id or None})

@bp.route('/sales-return/item-bin-inventory', methods=['GET'])
def sales_return_item_bin_inventory():
    return sales_item_bin_inventory()

@bp.route('/sales-return/api/warehouse-bins')
def sales_return_api_warehouse_bins():
    return api_sales_warehouse_bins()

@bp.route('/sales-return/item-inventory', methods=['GET'])
def sales_return_item_inventory():
    return sales_item_inventory()

@bp.route('/sales/invoice-type', methods=['GET'])
def sales_invoice_type():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    invoice_code = (request.args.get('invoice_code') or '').strip()
    flag, name = get_invoice_type_flag(invoice_code)
    return jsonify({'success': True, 'flag': flag, 'name': name})

@bp.route('/sales-return/invoice-type', methods=['GET'])
def sales_return_invoice_type():
    return sales_invoice_type()

@bp.route('/sales/item-popup-items', methods=['GET'])
def sales_item_popup_items():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    try:
        filter_key = (request.args.get('filter') or 'all').strip()
        search = (request.args.get('search') or '').strip()
        price_mode = (request.args.get('price_mode') or 'retail').strip().lower()
        customer_code = (request.args.get('customer_code') or '').strip()
        bill_no = (request.args.get('bill_no') or '').strip()
        seed_item_code = (request.args.get('seed_item_code') or '').strip()
        is_sales_return = str(request.args.get('is_sales_return') or '').strip() in {'1', 'true', 'yes', 'y', 'on'}
        location_code_int = _resolve_location_code()
        # The page sends its own minus-billing state (Sales Invoice and Sales Order are
        # controlled separately). Fall back to the location's MINUSBILLING flag when the
        # param is absent (e.g. older cached page).
        minus_param = (request.args.get('minus_billing') or '').strip()
        if minus_param in {'0', '1'}:
            minus_allowed = minus_param == '1'
        else:
            location_info = get_location_info_by_dbkey(session.get('tenant_id'))
            minusbilling = str(location_info.get('minusbilling') or '').strip().upper()
            minus_allowed = minusbilling != 'N'
        customer_related_filters = {'customer_item', 'customer_category', 'own_prod_cust_category', 'customer_category_not_sold'}
        # Sales Invoice / Sales Order: always list stock > 0 only (Sales Return keeps all items).
        enforce_stock_positive = (
            not is_sales_return
            and (filter_key not in customer_related_filters)
            and (filter_key != 'veg')
        )
        customer_category = None
        if customer_code:
            customer_category = get_customer_category(customer_code)
        raw_limit = (request.args.get('limit') or '').strip()
        popup_limit = int(raw_limit) if raw_limit.isdigit() else None
        warehouse_id_int = None
        # Scope to selected warehouse whenever stock-positive listing is required.
        if _sales_warehouse_enabled() and enforce_stock_positive:
            wh_raw = (request.args.get('warehouse_id') or '').strip()
            if wh_raw.isdigit():
                warehouse_id_int = int(wh_raw)
        elif _sales_warehouse_enabled() and not minus_allowed:
            wh_raw = (request.args.get('warehouse_id') or '').strip()
            if wh_raw.isdigit():
                warehouse_id_int = int(wh_raw)
        items = get_item_popup_items(
            location_code=location_code_int,
            filter_key=filter_key,
            search=search,
            price_mode=price_mode,
            customer_code=customer_code,
            bill_no=bill_no,
            seed_item_code=seed_item_code,
            customer_category=customer_category,
            user_id=session.get('user'),
            enforce_stock_positive=enforce_stock_positive,
            limit=popup_limit,
            warehouse_id=warehouse_id_int,
        )
        return jsonify({'success': True, 'items': items})
    except Exception as e:
        print(f'[ERROR sales_item_popup_items] {e}')
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)[:400], 'items': []}, 500)

@bp.route('/sales-return/item-popup-items', methods=['GET'])
def sales_return_item_popup_items():
    return sales_item_popup_items()

@bp.route('/sales/item-history', methods=['GET'])
def sales_item_history():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    history_type = (request.args.get('type') or 'customer_item').strip().lower()
    item_code = (request.args.get('item_code') or '').strip()
    customer_code = (request.args.get('customer_code') or '').strip()
    if not item_code or not item_code.isdigit():
        return jsonify({'success': False, 'error': 'Select item first.'}, 400)
    location_code_int = _resolve_location_code()
    item_code_int = int(item_code)
    if history_type == 'customer_item':
        if not customer_code:
            return jsonify({'success': False, 'error': 'Select customer first.'}, 400)
        rows = get_customer_item_history(location_code_int, customer_code, item_code_int)
    else:
        rows = get_item_history(location_code_int, item_code_int)
    return jsonify({'success': True, 'items': rows})

@bp.route('/sales-return/item-history', methods=['GET'])
def sales_return_item_history():
    return sales_item_history()

@bp.route('/sales/api/batch-lots-for-line', methods=['GET'])
def sales_api_batch_lots_for_line():
    """Lots available for a sales line (location + item); blocked lots excluded from pick list."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    raw = (request.args.get('item_code') or '').strip()
    if not raw.isdigit():
        return jsonify({'success': False, 'error': 'Invalid item code'}, 400)
    item_code_int = int(raw)
    location_code_int = _resolve_location_code()
    rows = get_item_lot_stock_list(location_code_int, itemcode=item_code_int) or []
    out = []
    for r in rows:
        blocked = str(r.get('lot_blocked') or 'N').strip().upper() == 'Y'
        if blocked:
            continue
        try:
            qv = float(r.get('qty') or 0)
        except (TypeError, ValueError):
            qv = 0.0
        if qv <= 0.0001:
            continue
        out.append({'lot_id': r.get('lot_id'), 'batch_no': r.get('batch_no'), 'expiry_date': r.get('expiry_date'), 'qty': qv, 'qty_unalloc': r.get('qty_unalloc'), 'qty_binned': r.get('qty_binned')})
    return jsonify({'success': True, 'lots': out})

@bp.route('/sales-return/api/batch-lots-for-line', methods=['GET'])
def sales_return_api_batch_lots_for_line():
    return sales_api_batch_lots_for_line()

@bp.route('/sales-order/api/batch-lots-for-line', methods=['GET'])
def sales_order_api_batch_lots_for_line():
    return sales_api_batch_lots_for_line()

@bp.route('/sales/save', methods=['POST'])
def sales_save():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    if not _try_acquire_sales_doc_save_lock():
        return json_response_rotate_global({'success': False, 'error': 'Another save is still in progress for this session. Please wait.', 'save_session_locked': True}, 423)
    try:
        if not verify_consume_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY, extract_submitted_save_nonce(request)):
            return replay_blocked_response_global()
        payload: Dict[str, Any] = request.get_json(silent=True) or {}
        header = payload.get('header') or {}
        lines = payload.get('lines') or []
        if not lines:
            return json_response_rotate_global({'success': False, 'error': 'No items to save'}, 400)
        order_no = str(header.get('orderno') or header.get('order_no') or '').strip()
        if get_sales_orderno_mandatory_invoice_enabled() and not order_no:
            return json_response_rotate_global({'success': False, 'error': 'Order No is required.'}, 400)
        header['orderno'] = order_no[:80] if order_no else ''
        line_err = _validate_sales_doc_save_lines(lines, doc_label='sales invoice')
        if line_err:
            return json_response_rotate_global({'success': False, 'error': line_err}, 400)
        location_code_int = _resolve_location_code()
        open_date, txn_err = _enforce_sales_open_bill_date(header, location_code_int, is_return=False)
        if txn_err:
            return json_response_rotate_global(
                {'success': False, 'error': txn_err, 'transaction_date_blocked': True},
                400,
            )
        header['location_code'] = location_code_int
        header['billdate'] = open_date
        header.setdefault('billtime', datetime.now().strftime('%H:%M:%S'))
        header.setdefault('createdby', session.get('user'))
        requested_billno = header.get('billno')
        ok, error, billno, stock_debug, billno_reassigned, req_no = _save_sales_doc_with_billno_retry(
            header, lines, location_code=location_code_int, doc_type=DOC_TYPE_SALES_INVOICE,
        )
        if not ok:
            body: Dict[str, Any] = {'success': False, 'error': error or 'Save failed'}
            if _is_duplicate_doc_key_error(error):
                body['duplicate_doc_key'] = True
                body['duplicate_billno'] = True
                body['suggested_billno'] = peek_next_bill_no(
                    location_code_int, header.get('countercode'), doc_type=DOC_TYPE_SALES_INVOICE,
                )
            return json_response_rotate_global(body, 400)
        msg = None
        really_reassigned = bool(billno_reassigned and billno and req_no and not billno_equal(billno, req_no))
        if really_reassigned:
            msg = f'Bill number {req_no} was already in use. Saved as bill {billno}.'
        resp: Dict[str, Any] = {
            'success': True,
            'billno': billno,
            'requested_billno': req_no,
            'billno_reassigned': really_reassigned,
            'next_billno': _peek_next_billno_after_save(
                location_code_int, doc_type=DOC_TYPE_SALES_INVOICE, after_billno=billno,
            ),
            'pdf_url': url_for('reports.crystal_reports_open_report', report_name='cashbilldup', billno=billno),
            'stock_posted': bool((stock_debug or {}).get('stock_posted')),
            'stock_affected_items': int((stock_debug or {}).get('stock_affected_items') or 0),
        }
        if msg:
            resp['message'] = msg
        if billno:
            marked_orders, mark_warning = _mark_converted_sales_orders(
                location_code_int,
                header,
                coerce_billno(billno),
            )
            if marked_orders:
                resp['source_order_billnos'] = marked_orders
                resp['source_order_billno'] = marked_orders[0]
            if mark_warning:
                resp['order_mark_warning'] = (
                    mark_warning if not marked_orders
                    else f'Invoice saved. Some sales orders were not marked invoiced: {mark_warning}'
                )
        return json_response_rotate_global(resp)
    finally:
        _release_sales_doc_save_lock()

@bp.route('/sales-return/save', methods=['POST'])
def sales_return_save():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    if not _try_acquire_sales_doc_save_lock():
        return json_response_rotate_global({'success': False, 'error': 'Another save is still in progress for this session. Please wait.', 'save_session_locked': True}, 423)
    try:
        if not verify_consume_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY, extract_submitted_save_nonce(request)):
            return replay_blocked_response_global()
        payload: Dict[str, Any] = request.get_json(silent=True) or {}
        header = payload.get('header') or {}
        raw_lines = payload.get('lines') or []
        lines = []
        for line in raw_lines:
            row = dict(line or {})
            try:
                qty = abs(float(row.get('quantity') or 0))
            except Exception:
                qty = 0.0
            if qty <= 0:
                item = str(row.get('item_code') or row.get('itemcode') or '').strip()
                return json_response_rotate_global({
                    'success': False,
                    'error': f'Line quantity must be greater than zero{f" (item {item})" if item else ""}.',
                }, 400)
            try:
                base_qty_raw = row.get('base_qty')
                base_qty = abs(float(base_qty_raw if base_qty_raw is not None else qty))
            except Exception:
                base_qty = qty
            row['quantity'] = -qty
            row['base_qty'] = -base_qty
            amount_raw = row.get('amount')
            if amount_raw is not None:
                try:
                    row['amount'] = -abs(float(amount_raw))
                except Exception:
                    pass
            lines.append(row)
        if not lines:
            return json_response_rotate_global({'success': False, 'error': 'No items to save'}, 400)
        order_no = str(header.get('orderno') or header.get('order_no') or '').strip()
        if get_sales_orderno_mandatory_return_enabled() and not order_no:
            return json_response_rotate_global({'success': False, 'error': 'Order No is required.'}, 400)
        header['orderno'] = order_no[:80] if order_no else ''
        line_err = _validate_sales_doc_save_lines(lines, doc_label='sales return')
        if line_err:
            return json_response_rotate_global({'success': False, 'error': line_err}, 400)
        location_code_int = _resolve_location_code()
        open_date, txn_err = _enforce_sales_open_bill_date(header, location_code_int, is_return=True)
        if txn_err:
            return json_response_rotate_global(
                {'success': False, 'error': txn_err, 'transaction_date_blocked': True},
                400,
            )
        header['location_code'] = location_code_int
        header['billdate'] = open_date
        header.setdefault('billtime', datetime.now().strftime('%H:%M:%S'))
        header.setdefault('createdby', session.get('user'))
        header['is_sales_return'] = True
        bt, billtype_err = _resolve_sales_header_billtype(header)
        if billtype_err:
            return json_response_rotate_global({'success': False, 'error': billtype_err}, 400)
        header['billtype'] = bt
        header['customer_billing_type'] = 'CREDIT' if bt == 'R' else 'CASH'
        requested_billno = header.get('billno')
        ok, error, billno, stock_debug, billno_reassigned, req_no = _save_sales_doc_with_billno_retry(
            header, lines, location_code=location_code_int, doc_type=DOC_TYPE_SALES_RETURN,
        )
        if not ok:
            body: Dict[str, Any] = {'success': False, 'error': error or 'Save failed'}
            if _is_duplicate_doc_key_error(error):
                body['duplicate_doc_key'] = True
                body['duplicate_billno'] = True
                body['suggested_billno'] = peek_next_bill_no(
                    location_code_int, header.get('countercode'), doc_type=DOC_TYPE_SALES_RETURN,
                )
            return json_response_rotate_global(body, 400)
        msg = None
        really_reassigned = bool(billno_reassigned and billno and req_no and not billno_equal(billno, req_no))
        if really_reassigned:
            msg = f'Bill number {req_no} was already in use. Saved as bill {billno}.'
        resp: Dict[str, Any] = {
            'success': True,
            'billno': billno,
            'requested_billno': req_no,
            'billno_reassigned': really_reassigned,
            'next_billno': _peek_next_billno_after_save(
                location_code_int, doc_type=DOC_TYPE_SALES_RETURN, after_billno=billno,
            ),
            'pdf_url': url_for('reports.crystal_reports_open_report', report_name='salesreturn', billno=billno),
            'stock_posted': bool((stock_debug or {}).get('stock_posted')),
            'stock_affected_items': int((stock_debug or {}).get('stock_affected_items') or 0),
        }
        if msg:
            resp['message'] = msg
        return json_response_rotate_global(resp)
    finally:
        _release_sales_doc_save_lock()

@bp.route('/sales-order/next-billno', methods=['GET'])
def sales_order_next_billno():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    location_code_int = _resolve_location_code()
    return _json_next_billno(location_code_int, doc_type=DOC_TYPE_SALES_ORDER)

@bp.route('/sales-order/save', methods=['POST'])
def sales_order_save():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    if not _try_acquire_sales_doc_save_lock():
        return json_response_rotate_global({'success': False, 'error': 'Another save is still in progress for this session. Please wait.', 'save_session_locked': True}, 423)
    try:
        if not verify_consume_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY, extract_submitted_save_nonce(request)):
            return replay_blocked_response_global()
        payload: Dict[str, Any] = request.get_json(silent=True) or {}
        header = payload.get('header') or {}
        lines = payload.get('lines') or []
        if not lines:
            return json_response_rotate_global({'success': False, 'error': 'No items to save'}, 400)
        order_no = str(header.get('orderno') or header.get('order_no') or '').strip()
        if get_sales_orderno_mandatory_order_enabled() and not order_no:
            return json_response_rotate_global({'success': False, 'error': 'Order No is required.'}, 400)
        header['orderno'] = order_no[:80] if order_no else ''
        line_err = _validate_sales_doc_save_lines(lines, doc_label='sales order')
        if line_err:
            return json_response_rotate_global({'success': False, 'error': line_err}, 400)
        location_code_int = _resolve_location_code()
        open_date, txn_err = _enforce_sales_open_bill_date(header, location_code_int, is_return=False)
        if txn_err:
            return json_response_rotate_global({'success': False, 'error': txn_err}, 400)
        header['location_code'] = location_code_int
        header['billdate'] = open_date
        header.setdefault('billtime', datetime.now().strftime('%H:%M:%S'))
        header.setdefault('createdby', session.get('user'))
        header.setdefault('employeecode', session.get('employeecode') or 0)
        header.setdefault('countercode', session.get('countercode') or 0)
        bt, billtype_err = _resolve_sales_header_billtype(header)
        if billtype_err:
            return json_response_rotate_global({'success': False, 'error': billtype_err}, 400)
        header['billtype'] = bt
        header['customer_billing_type'] = 'CREDIT' if bt == 'R' else 'CASH'
        ok, error, billno = save_sales_order({'header': header, 'lines': lines})
        if not ok:
            return json_response_rotate_global({'success': False, 'error': error or 'Save failed'}, 400)
        return json_response_rotate_global({
            'success': True,
            'billno': billno,
            'next_billno': _peek_next_billno_after_save(
                location_code_int, doc_type=DOC_TYPE_SALES_ORDER, after_billno=billno,
            ),
            'pdf_url': _sales_order_pdf_url(billno),
        })
    finally:
        _release_sales_doc_save_lock()

@bp.route('/sales-order/pdf/<path:billno>')
def sales_order_pdf(billno: str):
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    from addons.reports.controllers.routes import _generate_cashbilldup_pdf
    location_code_int = _resolve_location_code()
    bn = parse_billno_from_request(billno)
    order = get_sales_order_for_edit(location_code_int, bn)
    if not order:
        return jsonify({'success': False, 'error': 'Sales order not found'}, 404)
    hdr = order.get('header') or {}
    lines: List[Dict[str, Any]] = []
    total_discount = 0.0
    total_amount = 0.0
    for ln in order.get('lines') or []:
        try:
            qty = float(ln.get('quantity') or 0)
        except (TypeError, ValueError):
            qty = 0.0
        try:
            rate = float(ln.get('rate') or 0)
        except (TypeError, ValueError):
            rate = 0.0
        try:
            disc = float(ln.get('discount') or 0)
        except (TypeError, ValueError):
            disc = 0.0
        total_discount += disc
        total_amount += qty * rate - disc
        lines.append({
            'itemcode': ln.get('item_code'),
            'itemname': ln.get('item_name'),
            'uom': ln.get('uom'),
            'unitofmeasurement': ln.get('uom'),
            'quantity': ln.get('quantity'),
            'rate': ln.get('rate'),
            'discount': ln.get('discount'),
            'itdisc': ln.get('discount') or 0,
            'amount': ln.get('amount'),
        })
    # Sales order PDF displays amounts to 3 decimals (list + form use 3 as well).
    header = {
        'customercode': hdr.get('customercode'),
        'customername': hdr.get('customername'),
        'billdate': hdr.get('billdate'),
        'billtime': hdr.get('billtime'),
        'remarks': hdr.get('remarks'),
        'address': hdr.get('address') or '',
        'locationcode': location_code_int,
        'orderno': hdr.get('orderno') or '',
        'discountamount': round(total_discount, 3),
        'netbillamount': round(total_amount, 3),
    }
    pdf_bytes = _generate_cashbilldup_pdf(
        billno=bn,
        header=header,
        lines=lines,
        invoice_title='SALES ORDER',
        template=request.args.get('template') or 'classic',
    )
    if not pdf_bytes:
        return jsonify({'success': False, 'error': 'Failed to generate PDF'}, 400)
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=False,
        download_name=f'sales_order_{bn}.pdf',
    )


@bp.route('/sales-order/<path:billno>/cancel', methods=['POST'])
def sales_order_cancel(billno: str):
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    location_code_int = _resolve_location_code()
    bn = parse_billno_from_request(billno)
    ok, error = cancel_sales_order(location_code_int, bn)
    if not ok:
        return json_response_rotate_global({'success': False, 'error': error or 'Cancel failed'}, 400)
    return json_response_rotate_global({'success': True, 'billno': bn})


@bp.route('/sales-order/batch-invoice', methods=['POST'])
def sales_order_batch_invoice():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    if not _try_acquire_sales_doc_save_lock():
        return json_response_rotate_global(
            {'success': False, 'error': 'Another save is still in progress for this session. Please wait.', 'save_session_locked': True},
            423,
        )
    try:
        if not verify_consume_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY, extract_submitted_save_nonce(request)):
            return replay_blocked_response_global()
        payload: Dict[str, Any] = request.get_json(silent=True) or {}
        raw_orders = payload.get('order_billnos') or payload.get('billnos') or []
        if isinstance(raw_orders, list):
            order_billnos = _parse_sales_order_billnos(','.join(str(x) for x in raw_orders))
        else:
            order_billnos = _parse_sales_order_billnos(str(raw_orders or ''))
        if not order_billnos:
            return json_response_rotate_global({'success': False, 'error': 'No sales orders selected.'}, 400)
        location_code_int = _resolve_location_code()
        result = _batch_invoice_sales_orders(
            location_code_int,
            order_billnos,
            username=str(session.get('user') or ''),
            employeecode=session.get('employeecode') or 0,
            countercode=session.get('countercode') or 0,
        )
        status = 400 if not result.get('success') else 200
        if result.get('transaction_date_blocked'):
            status = 400
        return json_response_rotate_global(result, status)
    finally:
        _release_sales_doc_save_lock()


@bp.route('/sales-order/batch-invoice/step', methods=['POST'])
def sales_order_batch_invoice_step():
    """Invoice one sales order as part of a guarded multi-step batch (save-once + session lock)."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    payload: Dict[str, Any] = request.get_json(silent=True) or {}
    order_billno = parse_billno_from_request(payload.get('order_billno'))
    try:
        batch_index = int(payload.get('batch_index') or 0)
    except (TypeError, ValueError):
        batch_index = 0
    try:
        batch_total = int(payload.get('batch_total') or 0)
    except (TypeError, ValueError):
        batch_total = 0
    batch_finalize = bool(payload.get('batch_finalize'))
    run_id = str(payload.get('batch_run_id') or '').strip()
    location_code_int = _resolve_location_code()
    username = str(session.get('user') or '')

    if batch_index == 0:
        _end_batch_invoice_run()
        if not _try_acquire_sales_doc_save_lock():
            return json_response_keep_global_nonce(
                {
                    'success': False,
                    'error': 'Another save is still in progress for this session. Please wait.',
                    'save_session_locked': True,
                },
                423,
            )
        if not verify_consume_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY, extract_submitted_save_nonce(request)):
            _release_sales_doc_save_lock()
            return replay_blocked_response_global()
        run_id = uuid.uuid4().hex
        session[_SALES_BATCH_INVOICE_RUN_KEY] = run_id
        session.modified = True
        open_date, txn_err = _enforce_sales_open_bill_date({}, location_code_int, is_return=False)
        if txn_err:
            _end_batch_invoice_run()
            return json_response_rotate_global(
                {'success': False, 'error': txn_err, 'transaction_date_blocked': True},
                400,
            )
        session[_SALES_BATCH_INVOICE_OPEN_DATE_KEY] = open_date
        session.modified = True
    else:
        if not _touch_batch_invoice_run(run_id):
            return json_response_keep_global_nonce(
                {
                    'success': False,
                    'error': 'Batch invoice session expired or was interrupted. Please try again.',
                    'batch_run_expired': True,
                },
                409,
            )

    open_date = str(session.get(_SALES_BATCH_INVOICE_OPEN_DATE_KEY) or '')
    if not billno_is_valid(order_billno):
        if batch_finalize:
            _end_batch_invoice_run()
            return json_response_rotate_global({'success': False, 'error': 'Invalid sales order number.'}, 400)
        return json_response_keep_global_nonce({'success': False, 'error': 'Invalid sales order number.'}, 400)

    try:
        result_row = _invoice_one_sales_order(
            location_code_int,
            order_billno,
            open_date=open_date,
            username=username,
            employeecode=session.get('employeecode') or 0,
            countercode=session.get('countercode') or 0,
        )
    except Exception as exc:
        _end_batch_invoice_run()
        err_msg = str(exc) or 'Invoice failed.'
        return json_response_rotate_global(
            {
                'success': False,
                'error': err_msg,
                'batch_run_id': run_id,
                'batch_index': batch_index,
                'batch_total': batch_total,
                'batch_finalize': batch_finalize,
                'result': {
                    'order_billno': order_billno,
                    'success': False,
                    'error': err_msg,
                },
            },
            400,
        )
    body: Dict[str, Any] = {
        'success': bool(result_row.get('success')),
        'batch_run_id': run_id,
        'batch_index': batch_index,
        'batch_total': batch_total,
        'batch_finalize': batch_finalize,
        'result': result_row,
        'progress_done': batch_index + 1,
        'progress_total': batch_total,
    }
    if batch_finalize:
        _end_batch_invoice_run()
        return json_response_rotate_global(body)
    if batch_index == 0:
        return json_response_rotate_global(body)
    _extend_sales_doc_save_lock()
    return json_response_keep_global_nonce(body, 200)


@bp.route('/sales-order/batch-invoice/cancel', methods=['POST'])
def sales_order_batch_invoice_cancel():
    """Release batch-invoice session lock when the client aborts mid-run."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    payload: Dict[str, Any] = request.get_json(silent=True) or {}
    run_id = str(payload.get('batch_run_id') or '').strip()
    force = bool(payload.get('force'))
    active_run = str(session.get(_SALES_BATCH_INVOICE_RUN_KEY) or '')
    if (run_id and active_run == run_id) or (force and (active_run or session.get(_SALES_DOC_SAVE_BUSY_KEY))):
        _end_batch_invoice_run()
    elif force:
        _release_sales_doc_save_lock()
    return json_response_rotate_global({'success': True})


# --- Sales Credit Note (customer CRHDR/CRDTL) ---


def _scn_header_for_form(header: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Map CRHDR fields to purchase-return form keys (returndate, sectioninc)."""
    if not header:
        return None
    out = dict(header)
    if out.get('crdate') and not out.get('returndate'):
        out['returndate'] = out['crdate']
    if out.get('remarks') is not None and out.get('sectioninc') is None:
        out['sectioninc'] = out['remarks']
    return out


def _scn_form_template_kwargs(**extra: Any) -> Dict[str, Any]:
    """Same shell as purchase debit note form (popups, line grid, tools)."""
    ctx: Dict[str, Any] = {
        'warehouse_enabled': False,
        'warehouse_options': [],
        'items': [],
        'suppliers': [],
        'doc_label': 'Sales Credit Note',
        'list_label': 'Credit Note List',
        'list_url': url_for('sales.sales_credit_note_list'),
        'save_api_url': url_for('sales.sales_credit_note_save'),
        'next_no_api_url': url_for('sales.sales_credit_note_next_no_api'),
        'refresh_save_nonce_url': url_for('sales.sales_credit_note_refresh_save_nonce'),
        'show_load_return_order': False,
    }
    ctx.update(extra)
    return ctx


@bp.route('/sales/credit-note')
def sales_credit_note_list():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    loc = _resolve_location_code()
    rows = _scn_ops.get_sales_credit_note_list(loc)
    return render_template('sales/sales_credit_note_list.html', rows=rows)


@bp.route('/sales/credit-note/new')
def sales_credit_note_new():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    loc = _resolve_location_code()
    bill_date_value = _sales_default_bill_date()
    return render_template(
        'sales/sales_credit_note_form.html',
        **_scn_form_template_kwargs(
            return_no=_scn_ops.credit_note_next_no(loc),
            query_mode=False,
            load_header=None,
            load_details=[],
        ),
    )


@bp.route('/sales/credit-note/query/<int:cr_no>')
def sales_credit_note_query(cr_no: int):
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    loc = _resolve_location_code()
    header = _scn_ops.get_sales_credit_note_header(cr_no, loc)
    if not header:
        return redirect(url_for('sales.sales_credit_note_list'))
    return render_template(
        'sales/sales_credit_note_form.html',
        **_scn_form_template_kwargs(
            return_no=cr_no,
            query_mode=True,
            load_header=_scn_header_for_form(header),
            load_details=_scn_ops.get_sales_credit_note_details(cr_no, loc),
        ),
    )


@bp.route('/sales/credit-note/edit/<int:cr_no>')
def sales_credit_note_edit(cr_no: int):
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    loc = _resolve_location_code()
    header = _scn_ops.get_sales_credit_note_header(cr_no, loc)
    if not header:
        return redirect(url_for('sales.sales_credit_note_list'))
    return render_template(
        'sales/sales_credit_note_form.html',
        **_scn_form_template_kwargs(
            return_no=cr_no,
            query_mode=False,
            load_header=_scn_header_for_form(header),
            load_details=_scn_ops.get_sales_credit_note_details(cr_no, loc),
        ),
    )


@bp.route('/sales/credit-note/api/items')
def sales_credit_note_items():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    search = (request.args.get('search') or '').strip()
    try:
        limit = int(request.args.get('limit') or 200)
        limit = min(max(limit, 50), 500)
    except (TypeError, ValueError):
        limit = 200
    try:
        from addons.purchase.controllers.routes import _get_items_with_alternate_uoms_filtered
        rows = _get_items_with_alternate_uoms_filtered(search=search or None, limit=limit, supplier_code=None)
    except Exception as ex:
        return jsonify({'success': False, 'error': str(ex), 'items': []}, 500)
    return jsonify({'success': True, 'items': rows})


@bp.route('/sales/credit-note/api/item-uoms/<int:item_code>')
def sales_credit_note_item_uoms(item_code: int):
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    try:
        from addons.purchase.controllers.routes import _get_item_uoms_with_cost
        uoms = _get_item_uoms_with_cost(int(item_code))
    except Exception as ex:
        return jsonify({'success': False, 'error': str(ex)}, 500)
    return jsonify({'success': True, 'uoms': uoms})


@bp.route('/sales/credit-note/api/next-no')
def sales_credit_note_next_no_api():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    loc = _resolve_location_code()
    return jsonify({'success': True, 'crno': _scn_ops.credit_note_next_no(loc)})


@bp.route('/sales/credit-note/api/refresh-save-nonce', methods=['GET'])
def sales_credit_note_refresh_save_nonce():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    return jsonify({'success': True, 'save_nonce': issue_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY)})


@bp.route('/sales/credit-note/api/save', methods=['POST'])
def sales_credit_note_save():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    if not _try_acquire_sales_doc_save_lock():
        return json_response_rotate_global({
            'success': False,
            'error': 'Another save is still in progress for this session. Please wait.',
            'save_session_locked': True,
        }, 423)
    try:
        if not verify_consume_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY, extract_submitted_save_nonce(request)):
            return replay_blocked_response_global()
        data = request.get_json(silent=True) or {}
        loc = _resolve_location_code()
        try:
            cr_no = int(data.get('crno') or 0)
        except (TypeError, ValueError):
            cr_no = 0
        cr_date = (data.get('crdate') or '')[:10]
        try:
            customer_code = int(data.get('customercode') or 0)
        except (TypeError, ValueError):
            customer_code = 0
        remarks = (data.get('remarks') or '').strip()
        cr_amount = float(data.get('cramount') or 0)
        lines = data.get('lines') or []
        if not cr_no or not cr_date or customer_code <= 0:
            return json_response_rotate_global({'success': False, 'error': 'Credit Note No, Date and Customer are required'}, 400)
        if not lines:
            return json_response_rotate_global({'success': False, 'error': 'Add at least one line'}, 400)
        err = _scn_ops.save_sales_credit_note(
            loc_code=loc,
            cr_no=cr_no,
            cr_date=cr_date,
            customer_code=customer_code,
            cr_amount=cr_amount,
            remarks=remarks,
            lines=lines,
            created_by=str(session.get('user') or 'web'),
        )
        if err:
            return json_response_rotate_global({'success': False, 'error': err}, 400)
        return json_response_rotate_global({
            'success': True,
            'crno': cr_no,
            'message': 'Credit note saved. Customer receivable and GL updated.',
            'next_crno': _scn_ops.credit_note_next_no(loc),
            'list_url': url_for('sales.sales_credit_note_list'),
        })
    finally:
        _release_sales_doc_save_lock()
