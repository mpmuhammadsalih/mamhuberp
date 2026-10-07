"""Temporary Collection blueprint"""
from pathlib import Path
import base64
import csv
import hashlib
import io
import json
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple
from collections import defaultdict
from nexa_http import Blueprint, jsonify, redirect, render_template, request, session, url_for, Response
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
from db import _detect_column, _fetch_rows, _get_connection, _get_scalar, _get_table_columns, _table_exists, get_location_info_by_dbkey, is_unique_constraint_violation, get_pending_invoices, get_customer_outstanding_details_credit, insert_payment_followup_only, process_payments, process_payments_credit
from save_nonce import GLOBAL_SAVE_NONCE_SESSION_KEY, replay_blocked_response_global, verify_consume_save_nonce, json_response_rotate_global
from master_activity_log import append_master_activity, fetch_master_activity_log
_ADDON_ROOT = Path(__file__).resolve().parents[1]
bp = Blueprint('temporary_collection', __name__, template_folder=str(_ADDON_ROOT / 'views' / 'templates'))

def _resolve_location_code() -> int:
    """Resolve location_code as integer"""
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
            print(f'[DEBUG temporary_collection] Could not get location_code from LOCATIONMASTER: {e}')
            location_code_int = 1
    return int(location_code_int)

def _temporary_collection_save_response(body: Dict[str, Any], status: int=200):
    """JSON for endpoints that consume the global submit token · ``save_nonce.py``."""
    return json_response_rotate_global(body, status)
TC_COLLECTION_SAVE_FP_SESSION_KEY = 'tc_collection_save_fp_v1'
TC_BULK_SAVE_FP_SESSION_KEY = 'tc_bulk_save_pending_fp_v1'
_TEMPORARY_COLLECTION_LOG_ENTITY = 'temporary_collection'

def _tc_activity_username() -> str:
    return str(session.get('user') or '').strip() or 'unknown'

def _log_temporary_collection_append(*, action: str, summary: str, detail: Dict[str, Any]) -> None:
    try:
        append_master_activity(username=_tc_activity_username(), action=(action or 'SAVE')[:32], entity=_TEMPORARY_COLLECTION_LOG_ENTITY, summary=(summary or '')[:500], detail=detail)
    except Exception:
        pass

def _log_temporary_collection_save_success(data: Dict[str, Any], resp_body: Dict[str, Any]) -> None:
    items = data.get('collection_items') or []
    if not isinstance(items, list):
        items = []
    lines: List[Dict[str, Any]] = []
    total_amt = 0.0
    for i in items[:200]:
        if not isinstance(i, dict):
            continue
        inv = str(i.get('invoice_no') or '').strip()
        cust = str(i.get('customer_code') or '').strip()
        try:
            amt = float(i.get('amount') or 0)
        except (TypeError, ValueError):
            amt = 0.0
        total_amt += amt
        lines.append({'invoice_no': inv, 'customer_code': cust, 'amount': round(amt, 4)})
    vn = resp_body.get('voucher_numbers')
    if not isinstance(vn, dict):
        vn = {}
    sm = str(data.get('salesman_code') or '').strip()
    summary = f'SAVE Temporary Collection salesman={sm} lines={len(items)} total={round(total_amt, 2)} vouchers={len(vn)}'[:500]
    tid = (session.get('tenant_id') or '').strip() or None
    detail: Dict[str, Any] = {'kind': 'single_save', 'tenant_id': tid, 'salesman_code': sm, 'transaction_date': str(data.get('transaction_date') or '').strip(), 'remark': str(data.get('remark') or '')[:500], 'location_code': data.get('location_code'), 'line_count': len(items), 'total_amount': round(total_amt, 4), 'lines': lines[:150], 'voucher_numbers': {str(k): str(v) for k, v in list(vn.items())[:80]}}
    _log_temporary_collection_append(action='SAVE', summary=summary, detail=detail)

def _log_temporary_collection_bulk_save(data: Dict[str, Any], *, ok_count: int, skipped: int, fail_count: int, pending_found: int, results: List[Dict[str, Any]]) -> None:
    tid = (session.get('tenant_id') or '').strip() or None
    summary = f'BULK SAVE Temporary Collection ok={ok_count} skipped={skipped} failed={fail_count} pending={pending_found}'[:500]
    detail: Dict[str, Any] = {'kind': 'bulk_save_pending', 'tenant_id': tid, 'date_from': str(data.get('date_from') or '').strip(), 'date_to': str(data.get('date_to') or '').strip(), 'remark': str(data.get('remark') or '')[:300], 'saved_ok': ok_count, 'skipped_no_lines': skipped, 'failed': fail_count, 'pending_found': pending_found, 'results': (results or [])[:120]}
    _log_temporary_collection_append(action='BULK_SAVE', summary=summary, detail=detail)
TC_PAYLOAD_GUARD_TABLE = 'TC_SAVE_PAYLOAD_GUARD'
TC_PAYLOAD_GUARD_TTL_SEC = 90.0
_tc_payload_guard_lock = threading.Lock()
_tc_payload_guard_table_ready_for_db: Set[str] = set()

def _tc_payload_guard_db_key() -> str:
    """Isolate lazy DDL per tenant schema when multi-DB mode is on."""
    try:
        from nexa_http import g, has_request_context
        if has_request_context():
            tid = getattr(g, 'current_tenant_id', None)
            if tid is not None and str(tid).strip() and (str(tid).strip().lower() != 'none'):
                return str(tid).strip()
    except Exception:
        pass
    return '__default__'

def _ensure_tc_payload_guard_table() -> None:
    """Create guard table in current tenant DB if missing (DDL commits its own transaction)."""
    db_key = _tc_payload_guard_db_key()
    if db_key in _tc_payload_guard_table_ready_for_db:
        return
    with _tc_payload_guard_lock:
        if db_key in _tc_payload_guard_table_ready_for_db:
            return
        ddl = f'\n            CREATE TABLE {TC_PAYLOAD_GUARD_TABLE} (\n                FP_HASH VARCHAR2(64) PRIMARY KEY,\n                CREATED_AT DATE DEFAULT SYSDATE NOT NULL\n            )\n        '
        try:
            with _get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(ddl)
                conn.commit()
        except Exception as e:
            err = str(e)
            if 'ORA-00955' in err or '00955' in err or 'already exists' in err.lower():
                pass
            else:
                raise
        _tc_payload_guard_table_ready_for_db.add(db_key)

def _tc_payload_guard_reserve(fp_hash: str) -> bool:
    """
    Insert a guard row in its own transaction. False = duplicate (another user/session has same payload key).
    """
    _ensure_tc_payload_guard_table()
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"\n                    DELETE FROM {TC_PAYLOAD_GUARD_TABLE}\n                    WHERE CREATED_AT < SYSDATE - NUMTODSINTERVAL(:ttl, 'SECOND')\n                    ", {'ttl': TC_PAYLOAD_GUARD_TTL_SEC})
                cur.execute(f'\n                    INSERT INTO {TC_PAYLOAD_GUARD_TABLE} (FP_HASH, CREATED_AT)\n                    VALUES (:fp, SYSDATE)\n                    ', {'fp': fp_hash})
            conn.commit()
        return True
    except Exception as e:
        if is_unique_constraint_violation(e):
            return False
        raise

def _tc_payload_guard_touch(fp_hash: str) -> None:
    """Refresh CREATED_AT so TTL is measured from successful completion."""
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f'UPDATE {TC_PAYLOAD_GUARD_TABLE} SET CREATED_AT = SYSDATE WHERE FP_HASH = :fp', {'fp': fp_hash})
            conn.commit()
    except Exception as e:
        print(f'[DEBUG _tc_payload_guard_touch] {e}')

def _tc_payload_guard_release(fp_hash: str) -> None:
    """Remove reservation after a failed save so the user can retry."""
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f'DELETE FROM {TC_PAYLOAD_GUARD_TABLE} WHERE FP_HASH = :fp', {'fp': fp_hash})
            conn.commit()
    except Exception as e:
        print(f'[DEBUG _tc_payload_guard_release] {e}')

def _temporary_collection_save_payload_fingerprint(data: Dict[str, Any]) -> str:
    """Stable hash for duplicate-submit detection (identical payload within a short window)."""
    items = data.get('collection_items') or []
    norm = sorted(((str(i.get('id') or ''), str(i.get('invoice_no') or '').strip(), str(i.get('customer_code') or '').strip(), round(float(i.get('amount') or 0), 2)) for i in items))
    payload = {'salesman': str(data.get('salesman_code') or '').strip(), 'date': str(data.get('transaction_date') or '').strip(), 'remark': str(data.get('remark') or '').strip(), 'items': norm}
    raw = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()

def _detect_table(candidates: List[str]) -> Optional[str]:
    """Return first table name that exists."""
    for table_name in candidates:
        try:
            if _table_exists(table_name):
                return table_name
        except Exception:
            continue
    return None

def _get_next_pendingno() -> str:
    """Get next pending number from tbltempsettlement and tblsettlement (ensure uniqueness). Use _get_next_pendingno_inside_transaction when inside a save transaction to avoid duplicates."""
    temp_settlement_table = _detect_table(['TBLTEMPSETTLEMENT', 'tbltempsettlement'])
    settlement_table = _detect_table(['TBLSETTLEMENT', 'tblsettlement'])
    max_voucherno = 0
    if temp_settlement_table:
        pendingno_col = _detect_column(temp_settlement_table, ['PENDINGNO', 'PENDING_NO', 'PENDINGNUMBER'])
        if pendingno_col:
            query = f'SELECT MAX({pendingno_col}) AS max_pendingno FROM {temp_settlement_table}'
            try:
                result = _get_scalar(query, {})
                if result and result > 0:
                    max_voucherno = max(max_voucherno, int(result))
            except Exception as e:
                print(f'[DEBUG _get_next_pendingno] Error checking tbltempsettlement: {e}')
    if settlement_table:
        pendingno_col = _detect_column(settlement_table, ['PENDINGNO', 'PENDING_NO', 'PENDINGNUMBER'])
        voucherno_col = _detect_column(settlement_table, ['VOUCHERNO', 'VOUCHER_NO', 'voucherno'])
        if pendingno_col:
            query = f'SELECT MAX({pendingno_col}) AS max_pendingno FROM {settlement_table}'
            try:
                result = _get_scalar(query, {})
                if result and result > 0:
                    max_voucherno = max(max_voucherno, int(result))
            except Exception as e:
                print(f'[DEBUG _get_next_pendingno] Error checking tblsettlement pendingno: {e}')
        if voucherno_col and voucherno_col != pendingno_col:
            query = f'SELECT MAX({voucherno_col}) AS max_voucherno FROM {settlement_table}'
            try:
                result = _get_scalar(query, {})
                if result and result > 0:
                    max_voucherno = max(max_voucherno, int(result))
            except Exception as e:
                print(f'[DEBUG _get_next_pendingno] Error checking tblsettlement voucherno: {e}')
    if max_voucherno > 0:
        return str(max_voucherno + 1)
    return '1'

def _get_next_pendingno_inside_transaction(cur, settlement_table: str, temp_settlement_table: Optional[str], sett_pending_col: str, temp_pending_col: Optional[str]) -> int:
    """Get next pending number inside an open transaction, locking the row with max pendingno so concurrent saves get unique numbers. Returns integer (first pending no to use)."""
    max_val = 0
    try:
        lock_sql = f"SELECT {sett_pending_col} FROM (SELECT {sett_pending_col} FROM {settlement_table} WHERE {sett_pending_col} IS NOT NULL AND REGEXP_LIKE(TO_CHAR({sett_pending_col}), '^[0-9]+$') ORDER BY TO_NUMBER({sett_pending_col}) DESC) WHERE ROWNUM = 1 FOR UPDATE"
        cur.execute(lock_sql)
        row = cur.fetchone()
        if row and row[0] is not None:
            try:
                max_val = max(max_val, int(float(row[0])))
            except (ValueError, TypeError):
                pass
    except Exception as e:
        try:
            lock_sql = f'SELECT {sett_pending_col} FROM (SELECT {sett_pending_col} FROM {settlement_table} WHERE {sett_pending_col} IS NOT NULL ORDER BY {sett_pending_col} DESC) WHERE ROWNUM = 1 FOR UPDATE'
            cur.execute(lock_sql)
            row = cur.fetchone()
            if row and row[0] is not None:
                try:
                    max_val = max(max_val, int(float(row[0])))
                except (ValueError, TypeError):
                    pass
        except Exception as e2:
            print(f'[DEBUG _get_next_pendingno_inside_transaction] lock/fallback: {e}, {e2}')
    if temp_settlement_table and temp_pending_col:
        try:
            cur.execute(f'SELECT MAX({temp_pending_col}) AS mx FROM {temp_settlement_table}', {})
            r = cur.fetchone()
            if r and r[0] is not None:
                try:
                    max_val = max(max_val, int(float(r[0])))
                except (ValueError, TypeError):
                    pass
        except Exception as e:
            print(f'[DEBUG _get_next_pendingno_inside_transaction] temp max: {e}')
    return max_val + 1

def _get_customer_name(customer_code: str) -> str:
    """Get customer name from customer code."""
    if not customer_code:
        return ''
    try:
        customer_table = _detect_table(['CUSTOMER', 'CUSTOMERS', 'customer', 'customers'])
        if not customer_table:
            return customer_code
        code_col = _detect_column(customer_table, ['CUST_CODE', 'CUSTOMERCODE', 'CUSTOMER_CODE', 'cust_code', 'customercode'])
        name_col = _detect_column(customer_table, ['CUST_NAME', 'CUSTOMERNAME', 'CUSTOMER_NAME', 'cust_name', 'customername', 'NAME', 'name'])
        if not code_col:
            return customer_code
        name_sql = f'{name_col} AS name' if name_col else 'NULL AS name'
        query = f'SELECT {name_sql} FROM {customer_table} WHERE {code_col} = :code'
        _, rows = _fetch_rows(query, {'code': customer_code})
        if rows and rows[0].get('name'):
            return str(rows[0]['name']).strip()
        return customer_code
    except Exception as e:
        print(f'[ERROR _get_customer_name] {e}')
        return customer_code

def _format_pdf_date(value: Any) -> str:
    """Format any date value to dd/mmm/yyyy (e.g. 25/JAN/2025) for PDF. Returns empty string on error."""
    if value is None:
        return ''
    try:
        if hasattr(value, 'strftime'):
            return value.strftime('%d/%b/%Y').upper()
    except Exception:
        pass
    s = str(value).strip()
    if not s:
        return ''
    try:
        if 'GMT' in s or (',' in s and len(s) > 15):
            try:
                s_clean = s.replace(' GMT', '').replace(' UTC', '').strip()
                dt = datetime.strptime(s_clean, '%a, %d %b %Y %H:%M:%S')
                return dt.strftime('%d/%b/%Y').upper()
            except ValueError:
                pass
        if '/' in s:
            parts = s.split('/')
            if len(parts) == 3:
                day = parts[0].zfill(2)
                month = (parts[1][:3] if len(parts[1]) >= 3 else parts[1]).upper()
                year = parts[2]
                return f'{day}/{month}/{year}'
        if '-' in s:
            parts = s.split('-')
            if len(parts[0]) == 4:
                try:
                    dt = datetime.strptime(s[:10], '%Y-%m-%d')
                    return dt.strftime('%d/%b/%Y').upper()
                except ValueError:
                    pass
            if len(parts) == 3:
                return f'{parts[0].zfill(2)}/{parts[1][:3].upper()}/{parts[2]}'
    except Exception as e:
        print(f'[WARNING _format_pdf_date] Error formatting date: {e}, value: {value}')
        return ''
    return ''

def _generate_outstanding_invoices_pdf(customer_code: str, customer_name: str, items: List[Dict[str, Any]], report_date: Optional[datetime]=None, date_from: str='', date_to: str='', location_name: str='') -> Optional[bytes]:
    """Generate a standard PDF report of outstanding invoices for a customer (to give to customer)."""
    if not REPORTLAB_AVAILABLE:
        print('[WARNING] reportlab not available, skipping outstanding PDF generation')
        return None
    if not items:
        print('[WARNING] No outstanding items for PDF')
        return None
    report_date = report_date or datetime.now()
    try:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5 * inch, bottomMargin=0.5 * inch, leftMargin=0.4 * inch, rightMargin=0.4 * inch)
        story = []
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle('OutstandingTitle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=18, textColor=colors.HexColor('#1e3a5f'), spaceAfter=8, alignment=TA_CENTER)
        story.append(Paragraph('OUTSTANDING INVOICE DETAILS', title_style))
        story.append(Spacer(1, 0.2 * inch))
        cust_display = f'{customer_code}'
        if customer_name and customer_name != customer_code:
            cust_display = f'{customer_code} - {customer_name}'
        details_data = [['Customer:', cust_display], ['Location:', (location_name or '').strip() or 'N/A'], ['Report Date:', report_date.strftime('%d/%b/%Y %I:%M %p').upper()]]
        if date_from:
            details_data.append(['Date From:', date_from])
        if date_to:
            details_data.append(['Date To:', date_to])
        details_table = Table(details_data, colWidths=[1.2 * inch, 5 * inch])
        details_table.setStyle(TableStyle([('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'), ('FONTNAME', (1, 0), (1, -1), 'Helvetica'), ('FONTSIZE', (0, 0), (-1, -1), 11), ('BOTTOMPADDING', (0, 0), (-1, -1), 8), ('TOPPADDING', (0, 0), (-1, -1), 4)]))
        story.append(details_table)
        story.append(Spacer(1, 0.25 * inch))
        headers = ['Sl.No', 'Bill No', 'Bill Date', 'Bill Amount', 'Outstanding']
        col_widths = [0.5 * inch, 1.2 * inch, 1.1 * inch, 1.1 * inch, 1.1 * inch]
        table_data = [headers]
        total_outstanding = 0.0
        for idx, it in enumerate(items, 1):
            billno = str(it.get('billno') or '-')
            billdate = it.get('billdate') or '-'
            if billdate and hasattr(billdate, 'strftime'):
                billdate = billdate.strftime('%Y-%m-%d')
            billdate_str = _format_pdf_date(billdate) if billdate and billdate != '-' else str(billdate)
            bill_amt = float(it.get('billamount') or 0)
            out_amt = float(it.get('outstanding') or 0)
            total_outstanding += out_amt
            table_data.append([str(idx), billno, billdate_str, f'{bill_amt:.2f}', f'{out_amt:.2f}'])
        table_data.append(['', '', '', 'TOTAL', f'{total_outstanding:.2f}'])
        tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
        tbl.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#374151')), ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTNAME', (0, 1), (-1, -2), 'Helvetica'), ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, 0), 11), ('FONTSIZE', (0, 1), (-1, -1), 10), ('ALIGN', (0, 0), (2, -1), 'LEFT'), ('ALIGN', (3, 0), (-1, -1), 'RIGHT'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('BOTTOMPADDING', (0, 0), (-1, -1), 6), ('TOPPADDING', (0, 0), (-1, -1), 6), ('GRID', (0, 0), (-1, -2), 0.5, colors.HexColor('#d1d5db')), ('LINEABOVE', (0, -1), (-1, -1), 2, colors.HexColor('#1e3a5f')), ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f3f4f6'))]))
        story.append(tbl)
        story.append(Spacer(1, 0.25 * inch))
        footer_style = ParagraphStyle('FooterStyle', parent=styles['Normal'], fontName='Helvetica', fontSize=9, textColor=colors.HexColor('#6b7280'), alignment=TA_CENTER)
        footer_text = Paragraph('This is a statement of outstanding invoices as of the report date. For official receipt please use the cash receipt.', footer_style)
        story.append(footer_text)
        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()
    except Exception as e:
        print(f'[ERROR _generate_outstanding_invoices_pdf] {e}')
        import traceback
        traceback.print_exc()
        return None

def _generate_collection_pdf(collection_items: List[Dict[str, Any]], customer_groups: Dict[str, List[Dict[str, Any]]], customer_totals: Dict[str, float], voucher_numbers: Dict[str, str], transaction_date: str, salesman_code: str, salesman_name: str, remark: str, location_code: int, user_name: str, location_name: str='', status_label: Optional[str]=None) -> Optional[bytes]:
    """Generate PDF report for collection summary. Single table: billno, billdate, voucherno, customercode, customername, billamount, collectionamount. Reduced font and spacing."""
    if not REPORTLAB_AVAILABLE:
        print('[WARNING] reportlab not available, skipping PDF generation')
        return None
    try:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.35 * inch, bottomMargin=0.35 * inch, leftMargin=0.35 * inch, rightMargin=0.35 * inch)
        story = []
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontSize=12, textColor=colors.HexColor('#1f2937'), spaceAfter=4, alignment=TA_CENTER)
        title = Paragraph('Collection Summary Report', title_style)
        story.append(title)
        story.append(Spacer(1, 0.1 * inch))
        if not location_name:
            try:
                info = get_location_info_by_dbkey(str(location_code))
                if info:
                    location_name = (info.get('locationname') or '').strip()
            except Exception:
                pass
        if not location_name:
            location_name = str(location_code)
        formatted_date = _format_pdf_date(transaction_date)
        header_value_style = ParagraphStyle('HeaderValue', parent=styles['Normal'], fontSize=7, leading=8)

        def _header_para(s):
            if s is None or str(s).strip() == '':
                return 'N/A'
            s = str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            return Paragraph(s.strip(), header_value_style)
        location_para = _header_para(location_name)
        salesman_para = _header_para(f"{salesman_code} - {(salesman_name or '').strip()}")
        remark_para = _header_para(remark or 'Pending Amount')
        details_data = [['Location:', location_para, 'Salesman:', salesman_para], ['Date:', formatted_date, 'Remark:', remark_para]]
        if status_label:
            details_data.append(['Status:', status_label, '', ''])
        details_table = Table(details_data, colWidths=[0.7 * inch, 2.3 * inch, 0.85 * inch, 2.65 * inch])
        details_table.setStyle(TableStyle([('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'), ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 2), ('TOPPADDING', (0, 0), (-1, -1), 2), ('VALIGN', (0, 0), (-1, -1), 'TOP')]))
        story.append(details_table)
        story.append(Spacer(1, 0.12 * inch))
        wrap_style = ParagraphStyle('WrapName', parent=styles['Normal'], fontSize=7, leading=8)
        total_label_style = ParagraphStyle('TotalLabel', parent=styles['Normal'], fontSize=7, leading=8, fontName='Helvetica-Bold')

        def _wrap_name(s):
            if not s:
                return 'N/A'
            s = str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            return Paragraph(s, wrap_style)
        headers = ['Sl No', 'Bill No', 'Bill Date', 'Voucher No', 'Customer Code', 'Customer Name', 'Bill Amount', 'Collection Amount']
        table_data = [headers]
        grand_total_amount = 0
        grand_total_collection = 0
        slno = 0

        def _cust_sort_key(item):
            code, items = item
            name = items[0].get('customer_name', code) or code if items else code
            return (str(name).strip().upper(), str(code))
        for customer_code, customer_items in sorted(customer_groups.items(), key=_cust_sort_key):
            customer_name = customer_items[0].get('customer_name', customer_code) if customer_items else customer_code
            voucherno = voucher_numbers.get(customer_code, 'N/A')
            customer_total_amount = 0
            customer_total_collection = 0
            for item in customer_items:
                slno += 1
                invoice_no = item.get('invoice_no', '')
                amount = float(item.get('amount', 0))
                bill_date_raw = item.get('bill_date') or item.get('billdate') or transaction_date
                bill_amount = float(item.get('bill_amount') or item.get('billamount') or amount)
                formatted_bill_date = _format_pdf_date(bill_date_raw) or formatted_date
                table_data.append([str(slno), invoice_no or 'N/A', formatted_bill_date, str(voucherno), str(customer_code), _wrap_name(customer_name), f'{bill_amount:.2f}', f'{amount:.2f}'])
                customer_total_amount += bill_amount
                customer_total_collection += amount
                grand_total_amount += bill_amount
                grand_total_collection += amount
            table_data.append(['', '', '', '', '', Paragraph('Total', total_label_style), f'{customer_total_amount:.2f}', f'{customer_total_collection:.2f}'])
        col_widths = [0.4 * inch, 0.75 * inch, 0.85 * inch, 0.75 * inch, 0.9 * inch, 1.5 * inch, 0.85 * inch, 0.95 * inch]
        main_table = Table(table_data, colWidths=col_widths, repeatRows=1)
        main_table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#667eea')), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, -1), 7), ('ALIGN', (0, 0), (0, -1), 'RIGHT'), ('ALIGN', (1, 0), (5, -1), 'LEFT'), ('ALIGN', (6, 0), (-1, -1), 'RIGHT'), ('BOTTOMPADDING', (0, 0), (-1, -1), 3), ('TOPPADDING', (0, 0), (-1, -1), 3), ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')), ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')])]))
        story.append(main_table)
        total_row = [['TOTAL', '', '', '', '', '', f'{grand_total_amount:.2f}', f'{grand_total_collection:.2f}']]
        total_table = Table(total_row, colWidths=col_widths)
        total_table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e0e7ff')), ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, -1), 7), ('ALIGN', (6, 0), (-1, -1), 'RIGHT'), ('BOTTOMPADDING', (0, 0), (-1, -1), 3), ('TOPPADDING', (0, 0), (-1, -1), 3), ('LINEABOVE', (0, 0), (-1, 0), 1.5, colors.HexColor('#374151'))]))
        story.append(total_table)
        story.append(Spacer(1, 0.15 * inch))
        footer_style = ParagraphStyle('FooterStyle', parent=styles['Normal'], fontSize=7, textColor=colors.HexColor('#6b7280'), alignment=TA_RIGHT)
        footer_text = Paragraph(f"Prepared by: {user_name or 'N/A'}", footer_style)
        story.append(footer_text)
        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()
    except Exception as e:
        print(f'[ERROR _generate_collection_pdf] Error generating PDF: {e}')
        import traceback
        print(traceback.format_exc())
        return None

def _generate_cash_receipt_pdf(voucherno: str, customer_code: str, customer_name: str, items: List[Dict[str, Any]], pay_date: datetime, salesman_code: str, salesman_name: str, remark: str, location_code: int, location_name: str, user_name: str, include_customer_in_header: bool=True, include_customer_in_table: bool=False, status_label: Optional[str]=None, pdf_title: str='CASH RECEIPT', include_negative_amounts: bool=False, reduce_font: bool=False, use_collection_summary_style: bool=False) -> Optional[bytes]:
    """Generate PDF receipt for cash receipt. reduce_font=True uses smaller fonts. use_collection_summary_style=True (e.g. INVOICE PENDING) matches Collection Summary Report design."""
    if not REPORTLAB_AVAILABLE:
        print('[WARNING] reportlab not available, skipping PDF generation')
        return None
    if not items or len(items) == 0:
        print('[WARNING] No items provided for PDF generation')
        return None
    if not pay_date:
        print('[WARNING] Payment date is required for PDF generation')
        return None
    if use_collection_summary_style:
        title_font = 12
        details_font = 7
        table_font = 7
        wrap_font = 7
        wrap_leading = 8
        footer_font = 7
    elif reduce_font:
        title_font = 14
        details_font = 8
        table_font = 8
        wrap_font = 8
        wrap_leading = 10
        footer_font = 8
    else:
        title_font = 18
        details_font = 10
        table_font = 9
        wrap_font = 9
        wrap_leading = 11
        footer_font = 9
    try:
        buffer = io.BytesIO()
        if use_collection_summary_style:
            doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.35 * inch, bottomMargin=0.35 * inch, leftMargin=0.35 * inch, rightMargin=0.35 * inch)
        else:
            doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5 * inch, bottomMargin=0.5 * inch)
        story = []
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontSize=title_font, textColor=colors.HexColor('#1f2937'), spaceAfter=4 if use_collection_summary_style else 12, alignment=TA_CENTER)
        title = Paragraph(pdf_title, title_style)
        story.append(title)
        story.append(Spacer(1, 0.1 * inch if use_collection_summary_style else 0.2 * inch))
        formatted_date = _format_pdf_date(pay_date)
        loc_str = (location_name or str(location_code)).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        salesman_name_str = (salesman_name or '').strip().replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        remark_str = (remark or 'Pending Amount').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        if use_collection_summary_style:
            detail_para_style = ParagraphStyle('DetailCell', parent=styles['Normal'], fontSize=details_font, leading=details_font + 1)
            row1 = [Paragraph(f"<b>Receipt No:</b> {(voucherno or '').replace('<', '&lt;').replace('>', '&gt;').replace('&', '&amp;')}", detail_para_style), Paragraph(f"<b>Date:</b> {(formatted_date or '').replace('<', '&lt;').replace('>', '&gt;').replace('&', '&amp;')}", detail_para_style), Paragraph(f'<b>Location:</b> {loc_str}', detail_para_style)]
            row2 = [Paragraph(f"<b>Salesman Code:</b> {(salesman_code or '').replace('<', '&lt;').replace('>', '&gt;').replace('&', '&amp;')}", detail_para_style), Paragraph(f'<b>Salesman Name:</b> {salesman_name_str}', detail_para_style), '']
            row3 = [Paragraph(f'<b>Remark:</b> {remark_str}', detail_para_style), Paragraph(f"<b>Status:</b> {(status_label or '').replace('<', '&lt;').replace('>', '&gt;').replace('&', '&amp;')}", detail_para_style), '']
            details_data = [row1, row2, row3]
            details_table = Table(details_data, colWidths=[2 * inch, 2 * inch, 2 * inch])
            details_table.setStyle(TableStyle([('FONTSIZE', (0, 0), (-1, -1), details_font), ('ALIGN', (0, 0), (-1, -1), 'LEFT'), ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('BOTTOMPADDING', (0, 0), (-1, -1), 2), ('TOPPADDING', (0, 0), (-1, -1), 2)]))
        else:
            details_data = [['Receipt No:', voucherno], ['Date:', formatted_date], ['Location:', location_name or str(location_code)]]
            if include_customer_in_header:
                details_data.extend([['Customer Code:', customer_code], ['Customer Name:', customer_name]])
            details_data.extend([['Salesman Code:', salesman_code], ['Salesman Name:', (salesman_name or '').strip()], ['Remark:', remark or 'Pending Amount']])
            if status_label:
                details_data.append(['Status:', status_label])
            details_table = Table(details_data, colWidths=[2 * inch, 4 * inch])
            details_table.setStyle(TableStyle([('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'), ('FONTNAME', (1, 0), (1, -1), 'Helvetica'), ('FONTSIZE', (0, 0), (-1, -1), details_font), ('ALIGN', (0, 0), (0, -1), 'LEFT'), ('ALIGN', (1, 0), (1, -1), 'LEFT'), ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('BOTTOMPADDING', (0, 0), (-1, -1), 6), ('TOPPADDING', (0, 0), (-1, -1), 6)]))
        story.append(details_table)
        story.append(Spacer(1, 0.12 * inch if use_collection_summary_style else 0.3 * inch))
        if include_customer_in_table:
            headers = ['Sl. No', 'Bill No', 'Bill Date', 'Customer Code', 'Customer Name', 'Amount']
        else:
            headers = ['Sl. No', 'Bill No', 'Bill Date', 'Amount']
        table_data = [headers]
        total_paid = 0
        wrap_style = ParagraphStyle('WrapCell', parent=styles['Normal'], fontSize=wrap_font, leading=wrap_leading)
        subtotal_row_indices = []
        sl_no = 0
        for item in items:
            try:
                is_subtotal = item.get('is_subtotal') is True
                payamount = float(item.get('payamount') or item.get('amount') or 0)
                if is_subtotal:
                    customer_name = str(item.get('customername') or 'Total').strip()
                    if include_customer_in_table:
                        table_data.append(['', '', '', '', Paragraph(customer_name, wrap_style), f'{payamount:.2f}'])
                    else:
                        table_data.append(['', '', '', f'{payamount:.2f}'])
                    subtotal_row_indices.append(len(table_data) - 1)
                    continue
                if not include_negative_amounts and payamount <= 0 or (include_negative_amounts and payamount == 0):
                    continue
                sl_no += 1
                billno = str(item.get('billno', '')).strip()
                bill_date_raw = item.get('billdate') or pay_date
                formatted_bill_date = _format_pdf_date(bill_date_raw) or formatted_date
                if include_customer_in_table:
                    customer_name = str(item.get('customername') or '').strip()
                    table_data.append([str(sl_no), billno or 'N/A', formatted_bill_date, str(item.get('customercode') or '').strip(), Paragraph(customer_name, wrap_style) if customer_name else '', f'{payamount:.2f}'])
                else:
                    table_data.append([str(sl_no), billno or 'N/A', formatted_bill_date, f'{payamount:.2f}'])
                total_paid += payamount
            except Exception as item_err:
                print(f'[WARNING _generate_cash_receipt_pdf] Error processing item: {item_err}')
                continue
        if include_customer_in_table:
            table_data.append(['TOTAL', '', '', '', '', f'{total_paid:.2f}'])
        else:
            table_data.append(['TOTAL', '', '', f'{total_paid:.2f}'])
        if include_customer_in_table:
            receipt_table = Table(table_data, colWidths=[0.6 * inch, 1.1 * inch, 1.1 * inch, 1.2 * inch, 2.1 * inch, 1.3 * inch])
        else:
            receipt_table = Table(table_data, colWidths=[0.8 * inch, 1.8 * inch, 1.8 * inch, 1.8 * inch])
        if use_collection_summary_style:
            table_style_commands = [('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#667eea')), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, -1), table_font), ('ALIGN', (0, 0), (0, -1), 'RIGHT'), ('ALIGN', (1, 0), (-2, -1), 'LEFT'), ('ALIGN', (-1, 0), (-1, -1), 'RIGHT'), ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('BOTTOMPADDING', (0, 0), (-1, -1), 3), ('TOPPADDING', (0, 0), (-1, -1), 3), ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')), ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]), ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'), ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e0e7ff')), ('LINEABOVE', (0, -1), (-1, -1), 1.5, colors.HexColor('#374151'))]
            for ri in subtotal_row_indices:
                table_style_commands.append(('FONTNAME', (0, ri), (-1, ri), 'Helvetica-Bold'))
                table_style_commands.append(('LINEABOVE', (0, ri), (-1, ri), 0.5, colors.HexColor('#9ca3af')))
                table_style_commands.append(('BACKGROUND', (0, ri), (-1, ri), colors.HexColor('#f1f5f9')))
        else:
            table_style_commands = [('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e5e7eb')), ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#1f2937')), ('ALIGN', (0, 0), (-1, -1), 'LEFT'), ('ALIGN', (-1, 0), (-1, -1), 'RIGHT'), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, -1), table_font), ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('BOTTOMPADDING', (0, 0), (-1, -1), 6), ('TOPPADDING', (0, 0), (-1, -1), 6), ('GRID', (0, 0), (-1, -2), 1, colors.HexColor('#d1d5db')), ('LINEBELOW', (0, -1), (-1, -1), 2, colors.HexColor('#374151'))]
            for ri in subtotal_row_indices:
                table_style_commands.append(('FONTNAME', (0, ri), (-1, ri), 'Helvetica-Bold'))
                table_style_commands.append(('LINEABOVE', (0, ri), (-1, ri), 0.5, colors.HexColor('#9ca3af')))
        receipt_table.setStyle(TableStyle(table_style_commands))
        story.append(receipt_table)
        story.append(Spacer(1, 0.3 * inch))
        footer_style = ParagraphStyle('FooterStyle', parent=styles['Normal'], fontSize=footer_font, textColor=colors.HexColor('#6b7280'), alignment=TA_RIGHT)
        footer_text = Paragraph(f"Prepared by: {user_name or 'N/A'}", footer_style)
        story.append(footer_text)
        if len(table_data) <= 1:
            print('[WARNING _generate_cash_receipt_pdf] No valid items to include in PDF')
            return None
        try:
            doc.build(story)
            buffer.seek(0)
            pdf_bytes = buffer.getvalue()
            if not pdf_bytes or len(pdf_bytes) == 0:
                print('[ERROR _generate_cash_receipt_pdf] PDF generation returned empty bytes')
                return None
            if not pdf_bytes.startswith(b'%PDF'):
                print('[ERROR _generate_cash_receipt_pdf] Generated file does not appear to be a valid PDF')
                return None
            return pdf_bytes
        except Exception as build_err:
            print(f'[ERROR _generate_cash_receipt_pdf] Error building PDF: {build_err}')
            import traceback
            print(traceback.format_exc())
            return None
    except Exception as e:
        print(f'[ERROR _generate_cash_receipt_pdf] Error generating PDF: {e}')
        import traceback
        print(traceback.format_exc())
        return None

def _get_temporary_collections_list(date_from: str='', date_to: str='') -> List[Dict[str, Any]]:
    """Get temporary collections grouped by salesman and bill date (one row per salesman+day)."""
    online_table = _detect_table(['ONLINE_TEMPORARY_COLLECTIONS', 'online_temporary_collections', 'ONLINETEMPORARYCOLLECTIONS'])
    if not online_table:
        return []
    salesman_table = _detect_table(['SALESMAN', 'salesman', 'SALESMEN', 'salesmen'])
    location_code = _resolve_location_code()
    billdate_col = _detect_column(online_table, ['BILLDATE', 'BILL_DATE', 'billdate'])
    collection_col = _detect_column(online_table, ['COLLECTION', 'collection', 'COLLECTIONAMOUNT', 'collectionamount'])
    finalcollection_col = _detect_column(online_table, ['FINALCOLLECTION', 'FINAL_COLLECTION', 'finalcollection', 'final_collection'])
    salesman_code_col = _detect_column(online_table, ['SALESMAN_CODE', 'SALESMANCODE', 'salesman_code', 'salesmancode'])
    status_col = _detect_column(online_table, ['STATUS', 'status'])
    location_code_col = _detect_column(online_table, ['LOCATION_CODE', 'LOCATIONCODE', 'location_code', 'locationcode'])
    billno_group_col = _detect_column(online_table, ['BILLNO', 'BILL_NO', 'billno'])
    if not salesman_code_col or not billdate_col or (not collection_col):
        return []
    sm_code_col = None
    sm_name_col = None
    sm_location_col = None
    if salesman_table:
        sm_code_col = _detect_column(salesman_table, ['SALESMANCODE', 'salesmancode', 'CODE', 'code'])
        sm_name_col = _detect_column(salesman_table, ['SALESMANNAME', 'salesmanname', 'NAME', 'name'])
        sm_location_col = _detect_column(salesman_table, ['LOCATIONCODE', 'LOCATION_CODE', 'LOC_CODE', 'LOCCODE'])
    salesman_join = ''
    salesman_name_sql = 'NULL AS salesmanname'
    if salesman_table and sm_code_col and sm_name_col:
        salesman_join = f'LEFT JOIN {salesman_table} s ON h.{salesman_code_col} = s.{sm_code_col}'
        salesman_name_sql = f's.{sm_name_col} AS salesmanname'
        if sm_location_col:
            salesman_join += f' AND s.{sm_location_col} = {location_code}'
    where_clauses = []
    params = {}
    if location_code_col:
        where_clauses.append(f'h.{location_code_col} = :location_code')
        params['location_code'] = location_code
    if date_from and date_to and billdate_col:
        try:
            try:
                from_date = datetime.strptime(date_from, '%Y-%m-%d')
                to_date = datetime.strptime(date_to, '%Y-%m-%d')
                from_date_oracle = from_date.strftime('%d-%b-%Y').upper()
                to_date_oracle = to_date.strftime('%d-%b-%Y').upper()
                where_clauses.append(f"h.{billdate_col} BETWEEN TO_DATE(:date_from, 'DD-MON-YYYY') AND TO_DATE(:date_to, 'DD-MON-YYYY')")
                params['date_from'] = from_date_oracle
                params['date_to'] = to_date_oracle
                print(f'[DEBUG _get_temporary_collections_list] Filtering by date range: {from_date_oracle} to {to_date_oracle}')
            except Exception as parse_err:
                print(f'[DEBUG _get_temporary_collections_list] Date parse error: {parse_err}, trying direct format')
                where_clauses.append(f"h.{billdate_col} BETWEEN TO_DATE(:date_from, 'YYYY-MM-DD') AND TO_DATE(:date_to, 'YYYY-MM-DD')")
                params['date_from'] = date_from
                params['date_to'] = date_to
        except Exception as e:
            print(f'[DEBUG _get_temporary_collections_list] Date range filter error: {e}')
            pass
    elif date_from and billdate_col:
        try:
            try:
                from_date = datetime.strptime(date_from, '%Y-%m-%d')
                from_date_oracle = from_date.strftime('%d-%b-%Y').upper()
                where_clauses.append(f"h.{billdate_col} >= TO_DATE(:date_from, 'DD-MON-YYYY')")
                params['date_from'] = from_date_oracle
            except Exception:
                where_clauses.append(f"h.{billdate_col} >= TO_DATE(:date_from, 'YYYY-MM-DD')")
                params['date_from'] = date_from
        except Exception as e:
            print(f'[DEBUG _get_temporary_collections_list] Date from filter error: {e}')
            pass
    elif date_to and billdate_col:
        try:
            try:
                to_date = datetime.strptime(date_to, '%Y-%m-%d')
                to_date_oracle = to_date.strftime('%d-%b-%Y').upper()
                where_clauses.append(f"h.{billdate_col} <= TO_DATE(:date_to, 'DD-MON-YYYY')")
                params['date_to'] = to_date_oracle
            except Exception:
                where_clauses.append(f"h.{billdate_col} <= TO_DATE(:date_to, 'YYYY-MM-DD')")
                params['date_to'] = date_to
        except Exception as e:
            print(f'[DEBUG _get_temporary_collections_list] Date to filter error: {e}')
            pass
    else:
        transaction_date = _get_transaction_date(location_code)
        if transaction_date and billdate_col:
            try:
                if isinstance(transaction_date, str) and len(transaction_date) >= 10:
                    date_str = transaction_date[:10]
                    try:
                        parsed_date = datetime.strptime(date_str, '%Y-%m-%d')
                        transaction_date_oracle = parsed_date.strftime('%d-%b-%Y').upper()
                        where_clauses.append(f"h.{billdate_col} = TO_DATE(:transaction_date, 'DD-MON-YYYY')")
                        params['transaction_date'] = transaction_date_oracle
                        print(f'[DEBUG _get_temporary_collections_list] Filtering by transaction date: {transaction_date_oracle}')
                    except Exception as parse_err:
                        print(f'[DEBUG _get_temporary_collections_list] Date parse error: {parse_err}, using original format')
                        where_clauses.append(f"h.{billdate_col} = TO_DATE(:transaction_date, 'YYYY-MM-DD')")
                        params['transaction_date'] = transaction_date
            except Exception as e:
                print(f'[DEBUG _get_temporary_collections_list] Transaction date filter error: {e}')
                pass
    settlement_join_tb = ''
    billno_lc = billno_group_col
    customercode_lc = _detect_column(online_table, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'CUSTOMER', 'customer'])
    outstanding_lc_list = _detect_column(online_table, ['OUTSTANDING', 'outstanding'])
    fallback_bal_sql = f'NVL(h.{outstanding_lc_list}, 0)' if outstanding_lc_list else '0'
    settlement_table_list = _detect_table(['TBLSETTLEMENT', 'tblsettlement'])
    line_bal_expr = fallback_bal_sql
    if settlement_table_list and billno_lc and customercode_lc:
        sett_tb = settlement_table_list
        sett_bn = _detect_column(sett_tb, ['BILLNO', 'BILL_NO', 'billno'])
        sett_cc = _detect_column(sett_tb, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'customercode'])
        sett_fg = _detect_column(sett_tb, ['FLAG', 'flag'])
        sett_ba = _detect_column(sett_tb, ['BALANCE', 'balance'])
        sett_lc = _detect_column(sett_tb, ['LOCATIONCODE', 'LOCATION_CODE'])
        if sett_bn and sett_cc and sett_ba:
            flgx = ''
            if sett_fg:
                flgx = f" AND (sett.{sett_fg} = 'B' OR sett.{sett_fg} IS NULL)"
            locx = ''
            if sett_lc and location_code is not None:
                locx = f' AND sett.{sett_lc} = :location_code'
            settlement_join_tb = f' LEFT JOIN {sett_tb} sett ON h.{billno_lc} = sett.{sett_bn} AND h.{customercode_lc} = sett.{sett_cc}{flgx}{locx}'
            line_bal_expr = f'NVL(sett.{sett_ba}, {fallback_bal_sql})'
    sum_line_balance_sql = f'SUM({line_bal_expr}) AS sum_line_balance'
    group_by_cols = [f'h.{salesman_code_col}', f'h.{billdate_col}']
    if salesman_table and sm_name_col:
        group_by_cols.append(f's.{sm_name_col}')
    finalcollection_sql = f'SUM(NVL(h.{finalcollection_col}, 0)) AS totalfinalcollection' if finalcollection_col else f'SUM(NVL(h.{collection_col}, 0)) AS totalfinalcollection'
    status_sql = f'MIN(h.{status_col}) AS min_status' if status_col else '0 AS min_status'
    max_status_sql = f'MAX(h.{status_col}) AS max_status' if status_col else '0 AS max_status'
    billno_select_sql = 'NULL AS billno'
    query = f"\n        SELECT \n            h.{salesman_code_col} AS salesmancode,\n            {salesman_name_sql},\n            h.{billdate_col} AS billdate,\n            {billno_select_sql},\n            SUM(NVL(h.{collection_col}, 0)) AS totalcollection,\n            {finalcollection_sql},\n            {status_sql},\n            {max_status_sql},\n            {sum_line_balance_sql}\n        FROM {online_table} h\n        {salesman_join}\n        {settlement_join_tb}\n        WHERE {(' AND '.join(where_clauses) if where_clauses else '1=1')}\n        GROUP BY {', '.join(group_by_cols)}\n        ORDER BY h.{salesman_code_col}, h.{billdate_col} DESC\n    "
    try:
        print(f'[DEBUG _get_temporary_collections_list] Query: {query[:200]}...')
        print(f'[DEBUG _get_temporary_collections_list] Params: {params}')
        _, rows = _fetch_rows(query, params)
        print(f'[DEBUG _get_temporary_collections_list] Found {len(rows)} rows')
        return rows
    except Exception as e:
        import traceback
        print(f'[ERROR _get_temporary_collections_list] Error: {e}')
        print(traceback.format_exc())
        return []
    return []

def _get_transaction_date(location_code: Optional[int]=None) -> Optional[str]:
    """Get transaction date from TBLTRANSACTIONDATE where LocationCode = location_code, openflag='O', transactioncode=2. Returns date in YYYY-MM-DD format for date input."""
    transaction_table = _detect_table(['TBLTRANSACTIONDATE', 'tbltransactiondate', 'TRANSACTIONDATE', 'transactiondate'])
    if not transaction_table:
        return None
    if location_code is None:
        location_code = _resolve_location_code()
    if not location_code:
        return None
    locationcode_col = _detect_column(transaction_table, ['LOCATIONCODE', 'LOCATION_CODE', 'LOC_CODE', 'LOCCODE'])
    dateofopen_col = _detect_column(transaction_table, ['DATEOFOPEN', 'DATE_OF_OPEN', 'OPEN_DATE', 'OPENDATE'])
    openflag_col = _detect_column(transaction_table, ['OPENFLAG', 'OPEN_FLAG', 'FLAG', 'STATUS'])
    transactioncode_col = _detect_column(transaction_table, ['TRANSACTIONCODE', 'TRANSACTION_CODE', 'TRANSCODE', 'TRANS_CODE'])
    if not locationcode_col or not dateofopen_col or (not openflag_col) or (not transactioncode_col):
        return None
    query = f"\n        SELECT {dateofopen_col} AS dateofopen\n        FROM {transaction_table}\n        WHERE {locationcode_col} = :location_code\n          AND {openflag_col} = 'O'\n          AND {transactioncode_col} = 2\n    "
    try:
        _, rows = _fetch_rows(query, {'location_code': location_code})
        if rows and rows[0].get('dateofopen'):
            date_val = rows[0]['dateofopen']
            if isinstance(date_val, datetime):
                return date_val.strftime('%Y-%m-%d')
            elif hasattr(date_val, 'strftime'):
                return date_val.strftime('%Y-%m-%d')
            elif isinstance(date_val, str):
                try:
                    parsed = datetime.strptime(date_val[:10], '%Y-%m-%d')
                    return parsed.strftime('%Y-%m-%d')
                except:
                    try:
                        parsed = datetime.strptime(date_val[:10], '%d/%m/%Y')
                        return parsed.strftime('%Y-%m-%d')
                    except:
                        return date_val[:10] if len(date_val) >= 10 else None
            else:
                return None
    except Exception as e:
        print(f'[ERROR _get_transaction_date] {e}')
        import traceback
        traceback.print_exc()
    return None

def _get_salesman_info(salesman_code: str) -> Dict[str, Any]:
    """Get salesman information by code"""
    salesman_table = _detect_table(['SALESMAN', 'salesman', 'SALESMEN', 'salesmen'])
    if not salesman_table:
        return {}
    salesmancode_col = _detect_column(salesman_table, ['SALESMANCODE', 'salesmancode', 'CODE', 'code'])
    salesmanname_col = _detect_column(salesman_table, ['SALESMANNAME', 'salesmanname', 'NAME', 'name'])
    locationcode_col = _detect_column(salesman_table, ['LOCATIONCODE', 'LOCATION_CODE', 'LOC_CODE', 'LOCCODE'])
    if not salesmancode_col:
        return {}
    location_code = _resolve_location_code()
    where_clause = f'{salesmancode_col} = :salesman_code'
    if locationcode_col:
        where_clause += f' AND {locationcode_col} = :location_code'
    select_cols = [f'{salesmancode_col} AS salesmancode', f'{salesmanname_col} AS salesmanname' if salesmanname_col else 'NULL AS salesmanname']
    query = f"\n        SELECT {', '.join(select_cols)}\n        FROM {salesman_table}\n        WHERE {where_clause}\n    "
    params = {'salesman_code': salesman_code}
    if locationcode_col:
        params['location_code'] = location_code
    try:
        _, rows = _fetch_rows(query, params)
        return rows[0] if rows else {}
    except Exception as e:
        print(f'[DEBUG _get_salesman_info] Error: {e}')
        return {}

def _get_salesman_receipt_info(salesman_code: str) -> Dict[str, Any]:
    """Get salesman info for receipt page: name, outstandingamount, morepaid, unadjusted."""
    salesman_table = _detect_table(['SALESMAN', 'salesman', 'SALESMEN', 'salesmen'])
    if not salesman_table:
        return {}
    salesmancode_col = _detect_column(salesman_table, ['SALESMANCODE', 'salesmancode', 'CODE', 'code'])
    salesmanname_col = _detect_column(salesman_table, ['SALESMANNAME', 'salesmanname', 'NAME', 'name'])
    locationcode_col = _detect_column(salesman_table, ['LOCATIONCODE', 'LOCATION_CODE', 'LOC_CODE', 'LOCCODE'])
    outstanding_col = _detect_column(salesman_table, ['OUTSTANDINGAMOUNT', 'OUTSTANDING_AMOUNT', 'outstandingamount'])
    morepaid_col = _detect_column(salesman_table, ['MOREPAID', 'MORE_PAID', 'morepaid'])
    unadjusted_col = _detect_column(salesman_table, ['UNADJUSTED', 'unadjusted'])
    if not salesmancode_col:
        return {}
    location_code = _resolve_location_code()
    where_clause = f'{salesmancode_col} = :salesman_code'
    if locationcode_col:
        where_clause += f' AND {locationcode_col} = :location_code'
    select_cols = [f'{salesmancode_col} AS salesmancode', f'{salesmanname_col} AS salesmanname' if salesmanname_col else 'NULL AS salesmanname', f'NVL({outstanding_col}, 0) AS outstandingamount' if outstanding_col else '0 AS outstandingamount', f'NVL({morepaid_col}, 0) AS morepaid' if morepaid_col else '0 AS morepaid', f'NVL({unadjusted_col}, 0) AS unadjusted' if unadjusted_col else '0 AS unadjusted']
    query = f"SELECT {', '.join(select_cols)} FROM {salesman_table} WHERE {where_clause}"
    params = {'salesman_code': salesman_code}
    if locationcode_col:
        params['location_code'] = location_code
    try:
        _, rows = _fetch_rows(query, params)
        return rows[0] if rows else {}
    except Exception as e:
        print(f'[DEBUG _get_salesman_receipt_info] Error: {e}')
        return {}

def _get_next_salesman_voucher_no() -> int:
    """Get next voucher number: max(VOUCHERNO)+1 from TBLSALESMANSETTLEMENT."""
    tbl = _detect_table(['TBLSALESMANSETTLEMENT', 'tblsalesmansettlement'])
    if not tbl:
        return 1
    voucherno_col = _detect_column(tbl, ['VOUCHERNO', 'VOUCHER_NO', 'voucherno'])
    loc_col = _detect_column(tbl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    if not voucherno_col:
        return 1
    location_code = _resolve_location_code()
    where = f'{loc_col} = :location_code' if loc_col else '1=1'
    q = f'SELECT NVL(MAX({voucherno_col}), 0) + 1 AS nextno FROM {tbl} WHERE {where}'
    params = {'location_code': location_code} if loc_col else {}
    try:
        _, rows = _fetch_rows(q, params)
        return int(rows[0]['nextno']) if rows else 1
    except Exception as e:
        print(f'[DEBUG _get_next_salesman_voucher_no] Error: {e}')
        return 1

def _get_payment_reasons() -> List[Dict[str, Any]]:
    """Get payment reasons from tblpaymentreason (code, reason) for current location."""
    tbl = _detect_table(['TBLPAYMENTREASON', 'tblpaymentreason', 'PAYMENTREASON', 'paymentreason'])
    if not tbl:
        return []
    code_col = _detect_column(tbl, ['CODE', 'code'])
    reason_col = _detect_column(tbl, ['REASON', 'reason'])
    loc_col = _detect_column(tbl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    if not code_col or not reason_col:
        return []
    where = f'AND {loc_col} = :location_code' if loc_col else ''
    q = f'SELECT {code_col} AS code, {reason_col} AS reason FROM {tbl} WHERE 1=1 {where} ORDER BY {code_col}'
    params = {'location_code': _resolve_location_code()} if loc_col else {}
    try:
        _, rows = _fetch_rows(q, params)
        return rows
    except Exception as e:
        print(f'[DEBUG _get_payment_reasons] Error: {e}')
        return []

def _get_salesman_settlements_list(salesman_code: str) -> List[Dict[str, Any]]:
    """List TBLSALESMANSETTLEMENT rows for salesman: voucherno, date, type (REMARKS), remarks (REMARKS1), amount, totalamount (FINALOUTSTANDING). Order by VOUCHERNO DESC."""
    tbl = _detect_table(['TBLSALESMANSETTLEMENT', 'tblsalesmansettlement'])
    if not tbl:
        return []
    voucherno_col = _detect_column(tbl, ['VOUCHERNO', 'VOUCHER_NO', 'voucherno'])
    voucherdate_col = _detect_column(tbl, ['VOUCHERDATE', 'VOUCHER_DATE', 'voucherdate'])
    voucheramount_col = _detect_column(tbl, ['VOUCHERAMOUNT', 'VOUCHER_AMOUNT', 'voucheramount'])
    remarks_col = _detect_column(tbl, ['REMARKS', 'REMARK', 'remarks'])
    remarks1_col = _detect_column(tbl, ['REMARKS1', 'REMARKS_1', 'remarks1'])
    finalout_col = _detect_column(tbl, ['FINALOUTSTANDING', 'FINAL_OUTSTANDING', 'finaloutstanding'])
    salesmancode_col = _detect_column(tbl, ['SALESMANCODE', 'SALESMAN_CODE', 'salesmancode'])
    loc_col = _detect_column(tbl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    if not salesmancode_col or not voucherno_col:
        return []
    location_code = _resolve_location_code()
    where = f'{salesmancode_col} = :salesman_code'
    if loc_col:
        where += f' AND {loc_col} = :location_code'
    cols = [f'{voucherno_col} AS voucherno', f'{voucherdate_col} AS voucherdate' if voucherdate_col else 'NULL AS voucherdate', f'{remarks_col} AS type' if remarks_col else 'NULL AS type', f'{remarks1_col} AS remarks' if remarks1_col else 'NULL AS remarks', f'{voucheramount_col} AS amount' if voucheramount_col else 'NULL AS amount', f'{finalout_col} AS totalamount' if finalout_col else 'NULL AS totalamount']
    q = f"SELECT {', '.join(cols)} FROM {tbl} WHERE {where} ORDER BY {voucherno_col} DESC"
    params = {'salesman_code': salesman_code}
    if loc_col:
        params['location_code'] = location_code
    try:
        _, rows = _fetch_rows(q, params)
        return rows
    except Exception as e:
        print(f'[DEBUG _get_salesman_settlements_list] Error: {e}')
        return []

def _save_salesman_receipt(voucherno: int, voucherdate: str, salesmancode: str, typecode: int, typename: str, amount: float, remark: str, previous_outstanding: float) -> Optional[str]:
    """
    Insert into TBLSALESMANSETTLEMENT and update SALESMAN per VB logic.
    Type 1=discount (no salesman update), 2=short (outstanding+=amount), 3=settle (outstanding-=amount),
    4=morepaid (morepaid+=amount), 5=unadjusted (unadjusted+=amount).
    Returns None on success, error message on failure.
    """
    tbl_settle = _detect_table(['TBLSALESMANSETTLEMENT', 'tblsalesmansettlement'])
    salesman_table = _detect_table(['SALESMAN', 'salesman', 'SALESMEN', 'salesmen'])
    if not tbl_settle or not salesman_table:
        return 'Required tables not found'
    loc_col = _detect_column(tbl_settle, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    voucherno_col = _detect_column(tbl_settle, ['VOUCHERNO', 'VOUCHER_NO', 'voucherno'])
    voucherdate_col = _detect_column(tbl_settle, ['VOUCHERDATE', 'VOUCHER_DATE', 'voucherdate'])
    voucheramount_col = _detect_column(tbl_settle, ['VOUCHERAMOUNT', 'VOUCHER_AMOUNT', 'voucheramount'])
    salesmancode_col_settle = _detect_column(tbl_settle, ['SALESMANCODE', 'SALESMAN_CODE', 'salesmancode'])
    remarks_col = _detect_column(tbl_settle, ['REMARKS', 'REMARK', 'remarks'])
    remarks1_col = _detect_column(tbl_settle, ['REMARKS1', 'REMARKS_1', 'remarks1'])
    prevout_col = _detect_column(tbl_settle, ['PREVIOUSOUTSTANDING', 'PREVIOUS_OUTSTANDING', 'previousoutstanding'])
    finalout_col = _detect_column(tbl_settle, ['FINALOUTSTANDING', 'FINAL_OUTSTANDING', 'finaloutstanding'])
    sm_code_col = _detect_column(salesman_table, ['SALESMANCODE', 'salesmancode', 'CODE', 'code'])
    sm_out_col = _detect_column(salesman_table, ['OUTSTANDINGAMOUNT', 'OUTSTANDING_AMOUNT', 'outstandingamount'])
    sm_morepaid_col = _detect_column(salesman_table, ['MOREPAID', 'MORE_PAID', 'morepaid'])
    sm_unadj_col = _detect_column(salesman_table, ['UNADJUSTED', 'unadjusted'])
    if not all([loc_col, voucherno_col, voucherdate_col, voucheramount_col, salesmancode_col_settle]):
        return 'Required columns not found in TBLSALESMANSETTLEMENT'
    location_code = _resolve_location_code()
    try:
        from datetime import datetime as dt
        d = dt.strptime(voucherdate[:10], '%Y-%m-%d')
        voucherdate_fmt = d.strftime('%d-%b-%Y').upper()
    except Exception:
        voucherdate_fmt = voucherdate[:10]
    if typecode == 1:
        final_out = previous_outstanding
        amt_ins = amount
    elif typecode == 2:
        final_out = previous_outstanding + amount
        amt_ins = amount
    elif typecode == 4:
        final_out = previous_outstanding + amount
        amt_ins = amount
    elif typecode == 5:
        final_out = previous_outstanding + amount
        amt_ins = amount
    else:
        final_out = previous_outstanding - amount
        amt_ins = -amount
    ins_cols = [loc_col, voucherno_col, voucherdate_col, voucheramount_col, salesmancode_col_settle]
    ins_vals = [str(location_code), str(voucherno), f"TO_DATE('{voucherdate_fmt}', 'DD-MON-YYYY')", str(amt_ins), str(salesmancode)]
    if remarks_col:
        ins_cols.append(remarks_col)
        ins_vals.append(f"'{typename.replace(chr(39), chr(39) + chr(39))}'")
    if remarks1_col:
        ins_cols.append(remarks1_col)
        ins_vals.append(f"'{remark.replace(chr(39), chr(39) + chr(39))}'")
    if prevout_col:
        ins_cols.append(prevout_col)
        ins_vals.append(str(previous_outstanding))
    if finalout_col:
        ins_cols.append(finalout_col)
        ins_vals.append(str(final_out))
    insert_sql = f"INSERT INTO {tbl_settle} ({', '.join(ins_cols)}) VALUES ({', '.join(ins_vals)})"
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(insert_sql)
                if typecode == 2 or typecode == 3:
                    if sm_out_col:
                        loc_col_sm = _detect_column(salesman_table, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
                        up = f'UPDATE {salesman_table} SET {sm_out_col} = NVL({sm_out_col}, 0) + :delta WHERE {sm_code_col} = :sc'
                        up_params = {'delta': amount if typecode == 2 else -amount, 'sc': salesmancode}
                        if loc_col_sm:
                            up += f' AND {loc_col_sm} = :loc'
                            up_params['loc'] = location_code
                        cur.execute(up, up_params)
                elif typecode == 4 and sm_morepaid_col:
                    up = f'UPDATE {salesman_table} SET {sm_morepaid_col} = NVL({sm_morepaid_col}, 0) + :delta WHERE {sm_code_col} = :sc'
                    loc_col_sm = _detect_column(salesman_table, ['LOCATIONCODE', 'locationcode'])
                    if loc_col_sm:
                        up += f' AND {loc_col_sm} = :loc'
                        cur.execute(up, {'delta': amount, 'sc': salesmancode, 'loc': location_code})
                    else:
                        cur.execute(up, {'delta': amount, 'sc': salesmancode})
                elif typecode == 5 and sm_unadj_col:
                    up = f'UPDATE {salesman_table} SET {sm_unadj_col} = NVL({sm_unadj_col}, 0) + :delta WHERE {sm_code_col} = :sc'
                    loc_col_sm = _detect_column(salesman_table, ['LOCATIONCODE', 'locationcode'])
                    if loc_col_sm:
                        up += f' AND {loc_col_sm} = :loc'
                        cur.execute(up, {'delta': amount, 'sc': salesmancode, 'loc': location_code})
                    else:
                        cur.execute(up, {'delta': amount, 'sc': salesmancode})
            conn.commit()
    except Exception as e:
        import traceback
        print(f'[ERROR _save_salesman_receipt] {e}')
        traceback.print_exc()
        return str(e)
    return None

def _generate_salesman_receipt_pdf(location_code: int, location_name: str, receiptno: str, receiptdate: str, salesmancode: str, salesman_name: str, amount: float, reason: str, remarks: str) -> Optional[bytes]:
    """Generate PDF for salesman receipt (single voucher). Fields: locationcode, locationname, receiptno, receiptdate, salesmancode, salesman name, amount, reason, remarks."""
    if not REPORTLAB_AVAILABLE:
        print('[WARNING] reportlab not available, skipping salesman receipt PDF')
        return None
    try:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5 * inch, bottomMargin=0.5 * inch)
        story = []
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle('SalesmanReceiptTitle', parent=styles['Heading1'], fontSize=18, textColor=colors.HexColor('#1f2937'), spaceAfter=12, alignment=TA_CENTER)
        story.append(Paragraph('Salesman Receipt', title_style))
        story.append(Spacer(1, 0.2 * inch))
        receipt_date_str = _format_pdf_date(receiptdate) if receiptdate else receiptdate or ''
        details_data = [['Location Code:', str(location_code)], ['Location Name:', (location_name or '').strip() or str(location_code)], ['Receipt No:', str(receiptno)], ['Receipt Date:', receipt_date_str], ['Salesman Code:', str(salesmancode)], ['Salesman Name:', (salesman_name or '').strip() or '-'], ['Amount:', str(amount)], ['Reason:', (reason or '').strip() or '-'], ['Remarks:', (remarks or '').strip() or '-']]
        details_table = Table(details_data, colWidths=[2 * inch, 4 * inch])
        details_table.setStyle(TableStyle([('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'), ('FONTNAME', (1, 0), (1, -1), 'Helvetica'), ('FONTSIZE', (0, 0), (-1, -1), 10), ('ALIGN', (0, 0), (0, -1), 'LEFT'), ('ALIGN', (1, 0), (1, -1), 'LEFT'), ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]))
        story.append(details_table)
        doc.build(story)
        pdf_bytes = buffer.getvalue()
        return pdf_bytes if pdf_bytes else None
    except Exception as e:
        print(f'[ERROR _generate_salesman_receipt_pdf] {e}')
        import traceback
        traceback.print_exc()
        return None

def _get_invoice_details_from_online(salesman_code: str, date_from: Optional[str]=None, date_to: Optional[str]=None, use_date_range: bool=False, status_filter: Optional[int]=None, exact_bill_date: Optional[str]=None, all_statuses: bool=False) -> List[Dict[str, Any]]:
    """Fetch invoice details from online_temporary_collections. status_filter: 0=pending, 1=completed, None→0 unless all_statuses.
    When all_statuses is True, do not filter by status (matches list aggregates that sum all lines for salesman+bill date)."""
    online_table = _detect_table(['ONLINE_TEMPORARY_COLLECTIONS', 'online_temporary_collections', 'ONLINETEMPORARYCOLLECTIONS'])
    if not online_table:
        print(f'[DEBUG _get_invoice_details_from_online] Table not found: ONLINE_TEMPORARY_COLLECTIONS')
        return []
    print(f'[DEBUG _get_invoice_details_from_online] Using table: {online_table}')
    customer_table = _detect_table(['CUSTOMER', 'CUSTOMERS', 'customers', 'customer'])
    salesman_table = _detect_table(['SALESMAN', 'salesman', 'SALESMEN', 'salesmen'])
    settlement_table = _detect_table(['TBLSETTLEMENT', 'tblsettlement'])
    location_code = _resolve_location_code()
    customercode_col = _detect_column(online_table, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'CUSTOMER', 'customer'])
    billno_col = _detect_column(online_table, ['BILLNO', 'BILL_NO', 'billno'])
    billdate_col = _detect_column(online_table, ['BILLDATE', 'BILL_DATE', 'billdate'])
    outstanding_col = _detect_column(online_table, ['OUTSTANDING', 'outstanding'])
    collection_col = _detect_column(online_table, ['COLLECTION', 'collection'])
    id_col = _detect_column(online_table, ['ID', 'id', 'LINENO', 'LINE_NO', 'LINEID', 'LINE_ID', 'SERIALNO', 'SRNO', 'RECNO', 'REC_ID', 'TEMP_ID', 'ONLINERECID'])
    salesman_code_col = _detect_column(online_table, ['SALESMAN_CODE', 'SALESMANCODE', 'salesman_code', 'salesmancode'])
    status_col = _detect_column(online_table, ['STATUS', 'status'])
    location_code_col = _detect_column(online_table, ['LOCATION_CODE', 'LOCATIONCODE', 'location_code', 'locationcode'])
    if not customercode_col or not billno_col:
        print(f'[DEBUG _get_invoice_details_from_online] Missing required columns: customercode_col={customercode_col}, billno_col={billno_col}')
        return []
    print(f'[DEBUG _get_invoice_details_from_online] Columns detected - customercode: {customercode_col}, billno: {billno_col}, salesman_code: {salesman_code_col}, status: {status_col}')
    customer_code_col = None
    customer_name_col = None
    customer_location_col = None
    if customer_table:
        customer_code_col = _detect_column(customer_table, ['CUST_CODE', 'CUSTOMERCODE', 'CUSTOMER_CODE', 'CODE', 'code'])
        customer_name_col = _detect_column(customer_table, ['CUST_NAME', 'CUSTOMERNAME', 'CUSTOMER_NAME', 'NAME', 'name'])
        customer_location_col = _detect_column(customer_table, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode', 'location_code'])
    sm_code_col = None
    sm_name_col = None
    sm_location_col = None
    if salesman_table:
        sm_code_col = _detect_column(salesman_table, ['SALESMANCODE', 'salesmancode', 'CODE', 'code'])
        sm_name_col = _detect_column(salesman_table, ['SALESMANNAME', 'salesmanname', 'NAME', 'name'])
        sm_location_col = _detect_column(salesman_table, ['LOCATIONCODE', 'LOCATION_CODE', 'LOC_CODE', 'LOCCODE'])
    customer_join = ''
    name_sql = 'NULL AS customername'
    salesman_join = ''
    salesman_name_sql = 'NULL AS salesmanname'
    if customer_table and customer_code_col and customer_name_col:
        customer_join = f'LEFT JOIN {customer_table} c ON h.{customercode_col} = c.{customer_code_col}'
        name_sql = f'c.{customer_name_col} AS customername'
        if customer_location_col:
            customer_join += f' AND c.{customer_location_col} = {location_code}'
    if salesman_table and salesman_code_col and sm_code_col and sm_name_col:
        salesman_join = f'LEFT JOIN {salesman_table} s ON h.{salesman_code_col} = s.{sm_code_col}'
        salesman_name_sql = f's.{sm_name_col} AS salesmanname'
        if sm_location_col:
            salesman_join += f' AND s.{sm_location_col} = {location_code}'
    settlement_join = ''
    balance_sql = 'NULL AS balance'
    if settlement_table:
        sett_billno = _detect_column(settlement_table, ['BILLNO', 'BILL_NO', 'billno'])
        sett_cust = _detect_column(settlement_table, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'customercode'])
        sett_flag = _detect_column(settlement_table, ['FLAG', 'flag'])
        sett_balance = _detect_column(settlement_table, ['BALANCE', 'balance'])
        sett_loc = _detect_column(settlement_table, ['LOCATIONCODE', 'LOCATION_CODE'])
        if sett_billno and sett_cust and sett_flag and sett_balance:
            settlement_join = f"LEFT JOIN {settlement_table} sett ON h.{billno_col} = sett.{sett_billno} AND h.{customercode_col} = sett.{sett_cust} AND (sett.{sett_flag} = 'B' OR sett.{sett_flag} IS NULL)"
            if sett_loc:
                settlement_join += f' AND sett.{sett_loc} = {location_code}'
            balance_sql = f'NVL(sett.{sett_balance}, 0) AS balance'
    select_cols = [f'h.{customercode_col} AS customercode', name_sql, f'h.{billno_col} AS billno', f'h.{billdate_col} AS billdate' if billdate_col else 'NULL AS billdate', f'h.{outstanding_col} AS outstanding' if outstanding_col else '0 AS outstanding', balance_sql, f'h.{collection_col} AS collection' if collection_col else '0 AS collection', f'h.{id_col} AS id' if id_col else 'NULL AS id', f'h.{salesman_code_col} AS salesmancode' if salesman_code_col else 'NULL AS salesmancode', salesman_name_sql]
    where_clauses: List[str] = []
    params: Dict[str, Any] = {}
    if status_col and (not all_statuses):
        status_val = 0 if status_filter is None else int(status_filter)
        where_clauses.append(f'h.{status_col} = :status_val')
        params['status_val'] = status_val
    if salesman_code_col:
        where_clauses.append(f'h.{salesman_code_col} = :salesman_code')
        params['salesman_code'] = salesman_code
    if location_code_col:
        where_clauses.append(f'h.{location_code_col} = :location_code')
        params['location_code'] = location_code
    if exact_bill_date and billdate_col:
        try:
            datetime.strptime(exact_bill_date.strip()[:10], '%Y-%m-%d')
            eb = exact_bill_date.strip()[:10]
            where_clauses.append(f"TRUNC(h.{billdate_col}) = TO_DATE(:exact_bill_date, 'YYYY-MM-DD')")
            params['exact_bill_date'] = eb
            print(f'[DEBUG _get_invoice_details_from_online] exact_bill_date={eb}')
        except Exception as eb_err:
            print(f'[DEBUG _get_invoice_details_from_online] Invalid exact_bill_date: {eb_err}')
    if use_date_range and date_from and date_to and billdate_col:
        try:
            dt_from = datetime.strptime(date_from, '%Y-%m-%d')
            dt_to = datetime.strptime(date_to, '%Y-%m-%d')
            date_from_oracle = dt_from.strftime('%d-%b-%Y').upper()
            date_to_oracle = dt_to.strftime('%d-%b-%Y').upper()
            where_clauses.append(f"h.{billdate_col} BETWEEN TO_DATE(:date_from, 'DD-MON-YYYY') AND TO_DATE(:date_to, 'DD-MON-YYYY')")
            params['date_from'] = date_from_oracle
            params['date_to'] = date_to_oracle
        except Exception as e:
            print(f'[DEBUG _get_invoice_details_from_online] Date conversion error: {e}')
            where_clauses.append(f"h.{billdate_col} BETWEEN TO_DATE(:date_from, 'DD-MON-YYYY') AND TO_DATE(:date_to, 'DD-MON-YYYY')")
            params['date_from'] = date_from
            params['date_to'] = date_to
    elif billdate_col and 'exact_bill_date' not in params:
        transaction_date = _get_transaction_date(location_code)
        if transaction_date:
            try:
                if isinstance(transaction_date, str) and len(transaction_date) >= 10:
                    date_str = transaction_date[:10]
                    try:
                        parsed_date = datetime.strptime(date_str, '%Y-%m-%d')
                        transaction_date_oracle = parsed_date.strftime('%d-%b-%Y').upper()
                        where_clauses.append(f"h.{billdate_col} = TO_DATE(:transaction_date, 'DD-MON-YYYY')")
                        params['transaction_date'] = transaction_date_oracle
                        print(f'[DEBUG _get_invoice_details_from_online] Filtering by transaction date: {transaction_date_oracle}')
                    except Exception as parse_err:
                        print(f'[DEBUG _get_invoice_details_from_online] Date parse error: {parse_err}, using original format')
                        where_clauses.append(f"h.{billdate_col} = TO_DATE(:transaction_date, 'YYYY-MM-DD')")
                        params['transaction_date'] = transaction_date
            except Exception as e:
                print(f'[DEBUG _get_invoice_details_from_online] Transaction date filter error: {e}')
                pass
    query = f"\n        SELECT {', '.join(select_cols)}\n        FROM {online_table} h\n        {customer_join}\n        {salesman_join}\n        {settlement_join}\n        WHERE {' AND '.join(where_clauses)}\n        ORDER BY h.{billno_col}\n    "
    try:
        print(f'[DEBUG _get_invoice_details_from_online] Query: {query[:200]}...')
        print(f'[DEBUG _get_invoice_details_from_online] Params: {params}')
        _, rows = _fetch_rows(query, params)
        print(f'[DEBUG _get_invoice_details_from_online] Found {len(rows)} rows')
        return rows
    except Exception as e:
        import traceback
        print(f'[ERROR _get_invoice_details_from_online] Error: {e}')
        print(traceback.format_exc())
        return []

def _get_customer_summary(salesman_code: str, date_from: Optional[str]=None, date_to: Optional[str]=None, use_date_range: bool=False) -> List[Dict[str, Any]]:
    """Get customer summary from online_temporary_collections"""
    online_table = _detect_table(['ONLINE_TEMPORARY_COLLECTIONS', 'online_temporary_collections', 'ONLINETEMPORARYCOLLECTIONS'])
    if not online_table:
        return []
    customer_table = _detect_table(['CUSTOMER', 'CUSTOMERS', 'customers', 'customer'])
    location_code = _resolve_location_code()
    customercode_col = _detect_column(online_table, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'CUSTOMER', 'customer'])
    billno_col = _detect_column(online_table, ['BILLNO', 'BILL_NO', 'billno'])
    billdate_col = _detect_column(online_table, ['BILLDATE', 'BILL_DATE', 'billdate'])
    collection_col = _detect_column(online_table, ['COLLECTION', 'collection'])
    salesman_code_col = _detect_column(online_table, ['SALESMAN_CODE', 'SALESMANCODE', 'salesman_code', 'salesmancode'])
    status_col = _detect_column(online_table, ['STATUS', 'status'])
    location_code_col = _detect_column(online_table, ['LOCATION_CODE', 'LOCATIONCODE', 'location_code', 'locationcode'])
    if not customercode_col:
        return []
    customer_code_col = None
    customer_name_col = None
    customer_location_col = None
    if customer_table:
        customer_code_col = _detect_column(customer_table, ['CUST_CODE', 'CUSTOMERCODE', 'CUSTOMER_CODE', 'CODE', 'code'])
        customer_name_col = _detect_column(customer_table, ['CUST_NAME', 'CUSTOMERNAME', 'CUSTOMER_NAME', 'NAME', 'name'])
        customer_location_col = _detect_column(customer_table, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode', 'location_code'])
    customer_join = ''
    name_sql = 'NULL AS customername'
    if customer_table and customer_code_col and customer_name_col:
        customer_join = f'LEFT JOIN {customer_table} c ON h.{customercode_col} = c.{customer_code_col}'
        name_sql = f'c.{customer_name_col} AS customername'
        if customer_location_col:
            customer_join += f' AND c.{customer_location_col} = {location_code}'
    select_cols = [f'h.{customercode_col} AS customercode', name_sql, f'COUNT(h.{billno_col}) AS billcount', f'SUM(NVL(h.{collection_col}, 0)) AS totalcollection' if collection_col else '0 AS totalcollection']
    where_clauses = [f'h.{status_col} = 0' if status_col else '1=1']
    params = {}
    if salesman_code_col:
        where_clauses.append(f'h.{salesman_code_col} = :salesman_code')
        params['salesman_code'] = salesman_code
    if location_code_col:
        where_clauses.append(f'h.{location_code_col} = :location_code')
        params['location_code'] = location_code
    if use_date_range and date_from and date_to and billdate_col:
        try:
            dt_from = datetime.strptime(date_from, '%Y-%m-%d')
            dt_to = datetime.strptime(date_to, '%Y-%m-%d')
            date_from_oracle = dt_from.strftime('%d-%b-%Y').upper()
            date_to_oracle = dt_to.strftime('%d-%b-%Y').upper()
            where_clauses.append(f"h.{billdate_col} BETWEEN TO_DATE(:date_from, 'DD-MON-YYYY') AND TO_DATE(:date_to, 'DD-MON-YYYY')")
            params['date_from'] = date_from_oracle
            params['date_to'] = date_to_oracle
        except Exception as e:
            print(f'[DEBUG _get_customer_summary] Date conversion error: {e}')
            where_clauses.append(f"h.{billdate_col} BETWEEN TO_DATE(:date_from, 'DD-MON-YYYY') AND TO_DATE(:date_to, 'DD-MON-YYYY')")
            params['date_from'] = date_from
            params['date_to'] = date_to
    elif billdate_col:
        transaction_date = _get_transaction_date(location_code)
        if transaction_date:
            try:
                if '/' in transaction_date:
                    date_parts = transaction_date.split('/')
                    if len(date_parts) == 3:
                        transaction_date_oracle = f'{date_parts[0]}-{date_parts[1][:3].upper()}-{date_parts[2]}'
                    else:
                        transaction_date_oracle = transaction_date.replace('/', '-')
                else:
                    transaction_date_oracle = transaction_date
                where_clauses.append(f"h.{billdate_col} = TO_DATE(:transaction_date, 'DD-MON-YYYY')")
                params['transaction_date'] = transaction_date_oracle
            except Exception as e:
                print(f'[DEBUG _get_customer_summary] Transaction date conversion error: {e}')
                where_clauses.append(f"h.{billdate_col} = TO_DATE(:transaction_date, 'DD-MON-YYYY')")
                params['transaction_date'] = transaction_date
    query = f"\n        SELECT {', '.join(select_cols)}\n        FROM {online_table} h\n        {customer_join}\n        WHERE {' AND '.join(where_clauses)}\n        GROUP BY h.{customercode_col}, {name_sql}\n        ORDER BY {name_sql}\n    "
    try:
        _, rows = _fetch_rows(query, params)
        return rows
    except Exception as e:
        print(f'[DEBUG _get_customer_summary] Error: {e}')
        return []

def _get_cash_receipt_list(date_from: str='', date_to: str='', limit: int=100) -> List[Dict[str, Any]]:
    """Get list from tblsettlement where flag = 'R' (cash receipts). Optional date_from/date_to filter. Returns at most limit rows (default 100)."""
    settle_table = _detect_table(['TBLSETTLEMENT', 'tblsettlement'])
    if not settle_table:
        return []
    flag_col = _detect_column(settle_table, ['FLAG', 'FLAG_CODE', 'status'])
    billno_col = _detect_column(settle_table, ['BILLNO', 'BILL_NO', 'billno'])
    pendingno_col = _detect_column(settle_table, ['PENDINGNO', 'PENDING_NO', 'pendingno'])
    billdate_col = _detect_column(settle_table, ['BILLDATE', 'BILL_DATE', 'billdate'])
    cust_col = _detect_column(settle_table, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'CUSTCODE', 'customercode'])
    paidamt_col = _detect_column(settle_table, ['PAIDAMOUNT', 'PAID_AMOUNT', 'PAIDAMT', 'PAID', 'paidamount'])
    paidate_col = _detect_column(settle_table, ['PAIDATE', 'PAID_DATE', 'PAYMENTDATE', 'PAIDATE', 'paidate'])
    billamount_col = _detect_column(settle_table, ['BILLAMOUNT', 'BILL_AMOUNT', 'billamount'])
    if not flag_col:
        return []
    date_col = paidate_col or billdate_col or (billno_col if billno_col else None)
    amount_col = billamount_col or paidamt_col or _detect_column(settle_table, ['AMOUNT', 'amount'])
    customer_table = _detect_table(['CUSTOMER', 'CUSTOMERS', 'customers', 'customer'])
    customer_code_col = _detect_column(customer_table, ['CUST_CODE', 'CUSTOMERCODE', 'CUSTOMER_CODE', 'CODE']) if customer_table else None
    customer_name_col = _detect_column(customer_table, ['CUSTOMERNAME', 'CUST_NAME', 'CUSTOMER_NAME', 'NAME']) if customer_table else None
    location_code = _resolve_location_code()
    loc_col = _detect_column(settle_table, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    customer_join = ''
    customername_sql = 'NULL AS customername'
    if customer_table and customer_code_col and customer_name_col and cust_col:
        customer_join = f'LEFT JOIN {customer_table} c ON s.{cust_col} = c.{customer_code_col}'
        customername_sql = f'c.{customer_name_col} AS customername'
        loc_cust = _detect_column(customer_table, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
        if loc_cust:
            customer_join += f' AND c.{loc_cust} = {location_code}'
    where_parts = [f"s.{flag_col} = 'R'"]
    params = {}
    if loc_col:
        where_parts.append(f's.{loc_col} = :location_code')
        params['location_code'] = location_code
    if date_col and (date_from or date_to):
        try:
            if date_from and date_from.strip():
                params['date_from'] = date_from.strip()[:10]
                where_parts.append(f"TRUNC(s.{date_col}) >= TO_DATE(:date_from, 'YYYY-MM-DD')")
            if date_to and date_to.strip():
                params['date_to'] = date_to.strip()[:10]
                where_parts.append(f"TRUNC(s.{date_col}) <= TO_DATE(:date_to, 'YYYY-MM-DD')")
        except Exception:
            pass
    date_sql = f's.{date_col}' if date_col else 's.ROWID'
    amount_sql = f'NVL(s.{amount_col}, 0) AS amount' if amount_col else '0 AS amount'
    billno_sql = f's.{billno_col} AS billno' if billno_col else 'NULL AS billno'
    pendingno_sql = f's.{pendingno_col} AS pendingno' if pendingno_col else 'NULL AS pendingno'
    billdate_sql = f's.{billdate_col} AS billdate' if billdate_col else 'NULL AS billdate'
    paidate_sql = f's.{paidate_col} AS paidate' if paidate_col else 'NULL AS paidate'
    cust_sql = f's.{cust_col} AS customercode' if cust_col else 'NULL AS customercode'
    order_by_billno = f's.{billno_col} DESC' if billno_col else 's.ROWID'
    limit_val = max(1, min(int(limit), 10000)) if limit else 100
    params['limit'] = limit_val
    query = f"\n        SELECT * FROM (\n            SELECT\n                ROW_NUMBER() OVER (ORDER BY {date_sql} DESC, {order_by_billno}) AS slno,\n                {billno_sql},\n                {pendingno_sql},\n                {billdate_sql},\n                {paidate_sql},\n                {cust_sql},\n                {customername_sql},\n                {amount_sql}\n            FROM {settle_table} s\n            {customer_join}\n            WHERE {' AND '.join(where_parts)}\n        ) WHERE ROWNUM <= :limit\n        ORDER BY slno\n    "
    try:
        _, rows = _fetch_rows(query, params)
        return rows
    except Exception as e:
        print(f'[ERROR _get_cash_receipt_list] {e}')
        import traceback
        traceback.print_exc()
        return []

def _get_credit_receipt_list(date_from: str='', date_to: str='', limit: int=100) -> List[Dict[str, Any]]:
    """Get list from tblcreditsettlement where flag = 'R' (credit receipts). Same structure as _get_cash_receipt_list."""
    settle_table = _detect_table(['TBLCREDITSETTLEMENT', 'tblcreditsettlement'])
    if not settle_table:
        return []
    flag_col = _detect_column(settle_table, ['FLAG', 'FLAG_CODE', 'status'])
    billno_col = _detect_column(settle_table, ['BILLNO', 'BILL_NO', 'billno'])
    pendingno_col = _detect_column(settle_table, ['PENDINGNO', 'PENDING_NO', 'pendingno'])
    billdate_col = _detect_column(settle_table, ['BILLDATE', 'BILL_DATE', 'billdate'])
    cust_col = _detect_column(settle_table, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'CUSTCODE', 'customercode'])
    paidamt_col = _detect_column(settle_table, ['PAIDAMOUNT', 'PAID_AMOUNT', 'PAIDAMT', 'PAID', 'paidamount'])
    paidate_col = _detect_column(settle_table, ['PAIDATE', 'PAID_DATE', 'PAYMENTDATE', 'PAIDATE', 'paidate'])
    billamount_col = _detect_column(settle_table, ['BILLAMOUNT', 'BILL_AMOUNT', 'billamount'])
    if not flag_col:
        return []
    date_col = paidate_col or billdate_col or (billno_col if billno_col else None)
    amount_col = billamount_col or paidamt_col or _detect_column(settle_table, ['AMOUNT', 'amount'])
    customer_table = _detect_table(['CUSTOMER', 'CUSTOMERS', 'customers', 'customer'])
    customer_code_col = _detect_column(customer_table, ['CUST_CODE', 'CUSTOMERCODE', 'CUSTOMER_CODE', 'CODE']) if customer_table else None
    customer_name_col = _detect_column(customer_table, ['CUSTOMERNAME', 'CUST_NAME', 'CUSTOMER_NAME', 'NAME']) if customer_table else None
    location_code = _resolve_location_code()
    loc_col = _detect_column(settle_table, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    customer_join = ''
    customername_sql = 'NULL AS customername'
    if customer_table and customer_code_col and customer_name_col and cust_col:
        customer_join = f'LEFT JOIN {customer_table} c ON s.{cust_col} = c.{customer_code_col}'
        customername_sql = f'c.{customer_name_col} AS customername'
        loc_cust = _detect_column(customer_table, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
        if loc_cust:
            customer_join += f' AND c.{loc_cust} = {location_code}'
    where_parts = [f"s.{flag_col} = 'R'"]
    params = {}
    if loc_col:
        where_parts.append(f's.{loc_col} = :location_code')
        params['location_code'] = location_code
    if date_col and (date_from or date_to):
        try:
            if date_from and date_from.strip():
                params['date_from'] = date_from.strip()[:10]
                where_parts.append(f"TRUNC(s.{date_col}) >= TO_DATE(:date_from, 'YYYY-MM-DD')")
            if date_to and date_to.strip():
                params['date_to'] = date_to.strip()[:10]
                where_parts.append(f"TRUNC(s.{date_col}) <= TO_DATE(:date_to, 'YYYY-MM-DD')")
        except Exception:
            pass
    date_sql = f's.{date_col}' if date_col else 's.ROWID'
    amount_sql = f'NVL(s.{amount_col}, 0) AS amount' if amount_col else '0 AS amount'
    billno_sql = f's.{billno_col} AS billno' if billno_col else 'NULL AS billno'
    pendingno_sql = f's.{pendingno_col} AS pendingno' if pendingno_col else 'NULL AS pendingno'
    billdate_sql = f's.{billdate_col} AS billdate' if billdate_col else 'NULL AS billdate'
    paidate_sql = f's.{paidate_col} AS paidate' if paidate_col else 'NULL AS paidate'
    cust_sql = f's.{cust_col} AS customercode' if cust_col else 'NULL AS customercode'
    order_by_billno = f's.{billno_col} DESC' if billno_col else 's.ROWID'
    limit_val = max(1, min(int(limit), 10000)) if limit else 100
    params['limit'] = limit_val
    query = f"\n        SELECT * FROM (\n            SELECT\n                ROW_NUMBER() OVER (ORDER BY {date_sql} DESC, {order_by_billno}) AS slno,\n                {billno_sql},\n                {pendingno_sql},\n                {billdate_sql},\n                {paidate_sql},\n                {cust_sql},\n                {customername_sql},\n                {amount_sql}\n            FROM {settle_table} s\n            {customer_join}\n            WHERE {' AND '.join(where_parts)}\n        ) WHERE ROWNUM <= :limit\n        ORDER BY slno\n    "
    try:
        _, rows = _fetch_rows(query, params)
        return rows
    except Exception as e:
        print(f'[ERROR _get_credit_receipt_list] {e}')
        import traceback
        traceback.print_exc()
        return []

def _get_temp_settlement_receipt_list(receipt_no: Optional[str]=None, customer_code: Optional[str]=None) -> List[Dict[str, Any]]:
    """Get list from tbltempsettlement WHERE flag = 'R'. Map pendingno -> receiptno, againstno -> billno. If receipt_no given, filter by pendingno. If customer_code given (when opening from Cash Receipt List), filter by customercode too."""
    temp_table = _detect_table(['TBLTEMPSETTLEMENT', 'tbltempsettlement'])
    if not temp_table:
        return []
    flag_col = _detect_column(temp_table, ['FLAG', 'flag'])
    pendingno_col = _detect_column(temp_table, ['PENDINGNO', 'PENDING_NO', 'pendingno'])
    againstno_col = _detect_column(temp_table, ['AGAINSTNO', 'AGAINST_NO', 'againstno'])
    cust_col = _detect_column(temp_table, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'customercode'])
    paidamt_col = _detect_column(temp_table, ['PAIDAMOUNT', 'PAID_AMOUNT', 'paidamount'])
    paiddate_col = _detect_column(temp_table, ['PAIDDATE', 'PAID_DATE', 'paiddate'])
    billamount_col = _detect_column(temp_table, ['BILLAMOUNT', 'BILL_AMOUNT', 'billamount'])
    if not flag_col:
        return []
    amount_col = paidamt_col or billamount_col or _detect_column(temp_table, ['AMOUNT', 'amount'])
    date_col = paiddate_col
    receiptno_sql = f't.{pendingno_col} AS receiptno' if pendingno_col else 'NULL AS receiptno'
    billno_sql = f't.{againstno_col} AS billno' if againstno_col else 'NULL AS billno'
    cust_sql = f't.{cust_col} AS customercode' if cust_col else 'NULL AS customercode'
    amount_sql = f'NVL(t.{amount_col}, 0) AS amount' if amount_col else '0 AS amount'
    date_sql = f't.{date_col}' if date_col else 't.ROWID'
    order_col = pendingno_col or 't.ROWID'
    customer_table = _detect_table(['CUSTOMER', 'CUSTOMERS', 'customers', 'customer'])
    customer_code_col = _detect_column(customer_table, ['CUST_CODE', 'CUSTOMERCODE', 'CUSTOMER_CODE', 'CODE']) if customer_table else None
    customer_name_col = _detect_column(customer_table, ['CUSTOMERNAME', 'CUST_NAME', 'CUSTOMER_NAME', 'NAME']) if customer_table else None
    customer_join = ''
    customername_sql = 'NULL AS customername'
    if customer_table and cust_col and customer_code_col and customer_name_col:
        customer_join = f'LEFT JOIN {customer_table} c ON t.{cust_col} = c.{customer_code_col}'
        customername_sql = f'c.{customer_name_col} AS customername'
    where_parts = [f"t.{flag_col} = 'R'"]
    params: Dict[str, Any] = {}
    if receipt_no is not None and str(receipt_no).strip() and pendingno_col:
        where_parts.append(f't.{pendingno_col} = :receipt_no')
        rn = str(receipt_no).strip()
        try:
            params['receipt_no'] = int(rn) if rn.isdigit() else rn
        except (ValueError, TypeError):
            params['receipt_no'] = rn
    if customer_code is not None and str(customer_code).strip() and cust_col:
        where_parts.append(f't.{cust_col} = :customer_code')
        params['customer_code'] = str(customer_code).strip()
    query_sql = f"\n        SELECT\n            ROW_NUMBER() OVER (ORDER BY {date_sql} DESC, t.{order_col}) AS slno,\n            {receiptno_sql},\n            {billno_sql},\n            {cust_sql},\n            {customername_sql},\n            {amount_sql},\n            {(f't.{date_col} AS paiddate' if date_col else 'NULL AS paiddate')}\n        FROM {temp_table} t\n        {customer_join}\n        WHERE {' AND '.join(where_parts)}\n        ORDER BY {date_sql} DESC, t.{order_col}\n    "
    try:
        _, rows = _fetch_rows(query_sql, params)
        return rows
    except Exception as e:
        print(f'[ERROR _get_temp_settlement_receipt_list] {e}')
        import traceback
        traceback.print_exc()
        return []

def _get_temp_cr_settlement_receipt_list(receipt_no: Optional[str]=None, customer_code: Optional[str]=None) -> List[Dict[str, Any]]:
    """Get list from tblcrsettlement WHERE flag = 'R'. Same as _get_temp_settlement_receipt_list but for credit."""
    temp_table = _detect_table(['TBLCRSETTLEMENT', 'tblcrsettlement'])
    if not temp_table:
        return []
    flag_col = _detect_column(temp_table, ['FLAG', 'flag'])
    pendingno_col = _detect_column(temp_table, ['PENDINGNO', 'PENDING_NO', 'pendingno'])
    againstno_col = _detect_column(temp_table, ['AGAINSTNO', 'AGAINST_NO', 'againstno'])
    cust_col = _detect_column(temp_table, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'customercode'])
    paidamt_col = _detect_column(temp_table, ['PAIDAMOUNT', 'PAID_AMOUNT', 'paidamount'])
    paiddate_col = _detect_column(temp_table, ['PAIDDATE', 'PAID_DATE', 'paiddate'])
    billamount_col = _detect_column(temp_table, ['BILLAMOUNT', 'BILL_AMOUNT', 'billamount'])
    if not flag_col:
        return []
    amount_col = paidamt_col or billamount_col or _detect_column(temp_table, ['AMOUNT', 'amount'])
    date_col = paiddate_col
    receiptno_sql = f't.{pendingno_col} AS receiptno' if pendingno_col else 'NULL AS receiptno'
    billno_sql = f't.{againstno_col} AS billno' if againstno_col else 'NULL AS billno'
    cust_sql = f't.{cust_col} AS customercode' if cust_col else 'NULL AS customercode'
    amount_sql = f'NVL(t.{amount_col}, 0) AS amount' if amount_col else '0 AS amount'
    date_sql = f't.{date_col}' if date_col else 't.ROWID'
    order_col = pendingno_col or 't.ROWID'
    customer_table = _detect_table(['CUSTOMER', 'CUSTOMERS', 'customers', 'customer'])
    customer_code_col = _detect_column(customer_table, ['CUST_CODE', 'CUSTOMERCODE', 'CUSTOMER_CODE', 'CODE']) if customer_table else None
    customer_name_col = _detect_column(customer_table, ['CUSTOMERNAME', 'CUST_NAME', 'CUSTOMER_NAME', 'NAME']) if customer_table else None
    customer_join = ''
    customername_sql = 'NULL AS customername'
    if customer_table and cust_col and customer_code_col and customer_name_col:
        customer_join = f'LEFT JOIN {customer_table} c ON t.{cust_col} = c.{customer_code_col}'
        customername_sql = f'c.{customer_name_col} AS customername'
    where_parts = [f"t.{flag_col} = 'R'"]
    params: Dict[str, Any] = {}
    if receipt_no is not None and str(receipt_no).strip() and pendingno_col:
        where_parts.append(f't.{pendingno_col} = :receipt_no')
        rn = str(receipt_no).strip()
        try:
            params['receipt_no'] = int(rn) if rn.isdigit() else rn
        except (ValueError, TypeError):
            params['receipt_no'] = rn
    if customer_code is not None and str(customer_code).strip() and cust_col:
        where_parts.append(f't.{cust_col} = :customer_code')
        params['customer_code'] = str(customer_code).strip()
    query_sql = f"\n        SELECT\n            ROW_NUMBER() OVER (ORDER BY {date_sql} DESC, t.{order_col}) AS slno,\n            {receiptno_sql},\n            {billno_sql},\n            {cust_sql},\n            {customername_sql},\n            {amount_sql},\n            {(f't.{date_col} AS paiddate' if date_col else 'NULL AS paiddate')}\n        FROM {temp_table} t\n        {customer_join}\n        WHERE {' AND '.join(where_parts)}\n        ORDER BY {date_sql} DESC, t.{order_col}\n    "
    try:
        _, rows = _fetch_rows(query_sql, params)
        return rows
    except Exception as e:
        print(f'[ERROR _get_temp_cr_settlement_receipt_list] {e}')
        import traceback
        traceback.print_exc()
        return []

def _get_cash_customers_for_receipt() -> List[Dict[str, Any]]:
    """Get list of customers with invoice code = 1 (cash / invoice method) for receipt creation, including outstanding balance."""
    customer_table = _detect_table(['CUSTOMER', 'CUSTOMERS', 'customers', 'customer'])
    if not customer_table:
        return []
    code_col = _detect_column(customer_table, ['CUST_CODE', 'CUSTOMERCODE', 'CUSTOMER_CODE', 'CODE'])
    name_col = _detect_column(customer_table, ['CUSTOMERNAME', 'CUST_NAME', 'CUSTOMER_NAME', 'NAME'])
    invoice_col = _detect_column(customer_table, ['INVOICECODE', 'INVOICE_CODE', 'INVOICETYPE', 'TYPECODE'])
    if not code_col or not name_col:
        return []
    where_invoice = f"AND ({invoice_col} = '1' OR {invoice_col} = 1)" if invoice_col else ''
    location_code = _resolve_location_code()
    loc_col = _detect_column(customer_table, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    loc_where = f'AND c.{loc_col} = :location_code' if loc_col else ''
    settlement_table = _detect_table(['TBLSETTLEMENT', 'tblsettlement'])
    balance_col = None
    settlement_customer_col = None
    if settlement_table:
        balance_col = _detect_column(settlement_table, ['BALANCE', 'balance', 'OUTSTANDING', 'outstanding'])
        settlement_customer_col = _detect_column(settlement_table, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'CUSTCODE', 'CUST_CODE', 'CUSTOMER', 'customer'])
    if settlement_table and balance_col and settlement_customer_col:
        flag_col = _detect_column(settlement_table, ['FLAG', 'FLAG_CODE', 'flag'])
        flag_condition = f"AND s.{flag_col} = 'B'" if flag_col else ''
        query = f'\n            SELECT \n                c.{code_col} AS code, \n                c.{name_col} AS name,\n                NVL(SUM(s.{balance_col}), 0) AS outstanding\n            FROM {customer_table} c\n            INNER JOIN {settlement_table} s ON s.{settlement_customer_col} = c.{code_col} AND s.{balance_col} > 0 {flag_condition}\n            WHERE 1=1 {where_invoice} {loc_where}\n            GROUP BY c.{code_col}, c.{name_col}\n            HAVING NVL(SUM(s.{balance_col}), 0) > 0\n            ORDER BY c.{name_col}\n        '
    else:
        query = f'\n            SELECT c.{code_col} AS code, c.{name_col} AS name, 0 AS outstanding\n            FROM {customer_table} c\n            WHERE 1=1 {where_invoice} {loc_where}\n            ORDER BY c.{name_col}\n        '
    params: Dict[str, Any] = {}
    if loc_col:
        params['location_code'] = location_code
    try:
        _, rows = _fetch_rows(query, params)
        return rows or []
    except Exception as e:
        print(f'[ERROR _get_cash_customers_for_receipt] {e}')
        import traceback
        traceback.print_exc()
        return []

def _get_credit_customers_for_receipt() -> List[Dict[str, Any]]:
    """Get list of customers with customercode, customername, outstanding from tblcreditsettlement.
    Outstanding = SUM(balance) WHERE flag <> 'R' (exclude receipt rows)."""
    customer_table = _detect_table(['CUSTOMER', 'CUSTOMERS', 'customers', 'customer'])
    if not customer_table:
        return []
    code_col = _detect_column(customer_table, ['CUST_CODE', 'CUSTOMERCODE', 'CUSTOMER_CODE', 'CODE'])
    name_col = _detect_column(customer_table, ['CUSTOMERNAME', 'CUST_NAME', 'CUSTOMER_NAME', 'NAME'])
    if not code_col or not name_col:
        return []
    location_code = _resolve_location_code()
    loc_col = _detect_column(customer_table, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    loc_where = f'AND c.{loc_col} = :location_code' if loc_col else ''
    settlement_table = _detect_table(['TBLCREDITSETTLEMENT', 'tblcreditsettlement'])
    balance_col = None
    settlement_customer_col = None
    flag_col = None
    if settlement_table:
        balance_col = _detect_column(settlement_table, ['BALANCE', 'balance', 'OUTSTANDING', 'outstanding'])
        settlement_customer_col = _detect_column(settlement_table, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'CUSTCODE', 'CUST_CODE', 'CUSTOMER', 'customer'])
        flag_col = _detect_column(settlement_table, ['FLAG', 'FLAG_CODE', 'flag'])
    if settlement_table and balance_col and settlement_customer_col and flag_col:
        flag_not_R = f"(s.{flag_col} <> 'R' OR s.{flag_col} IS NULL)"
        query = f'\n            SELECT\n                c.{code_col} AS code,\n                c.{name_col} AS name,\n                NVL(SUM(s.{balance_col}), 0) AS outstanding\n            FROM {customer_table} c\n            INNER JOIN {settlement_table} s ON s.{settlement_customer_col} = c.{code_col} AND {flag_not_R} AND NVL(s.{balance_col}, 0) <> 0\n            WHERE 1=1 {loc_where}\n            GROUP BY c.{code_col}, c.{name_col}\n            HAVING NVL(SUM(s.{balance_col}), 0) <> 0\n            ORDER BY c.{name_col}\n        '
    elif settlement_table and balance_col and settlement_customer_col:
        query = f'\n            SELECT\n                c.{code_col} AS code,\n                c.{name_col} AS name,\n                NVL(SUM(s.{balance_col}), 0) AS outstanding\n            FROM {customer_table} c\n            INNER JOIN {settlement_table} s ON s.{settlement_customer_col} = c.{code_col} AND NVL(s.{balance_col}, 0) <> 0\n            WHERE 1=1 {loc_where}\n            GROUP BY c.{code_col}, c.{name_col}\n            HAVING NVL(SUM(s.{balance_col}), 0) <> 0\n            ORDER BY c.{name_col}\n        '
    else:
        query = f'\n            SELECT c.{code_col} AS code, c.{name_col} AS name, 0 AS outstanding\n            FROM {customer_table} c\n            WHERE 1=1 {loc_where}\n            ORDER BY c.{name_col}\n        '
    params: Dict[str, Any] = {}
    if loc_col:
        params['location_code'] = location_code
    try:
        _, rows = _fetch_rows(query, params)
        return rows or []
    except Exception as e:
        print(f'[ERROR _get_credit_customers_for_receipt] {e}')
        import traceback
        traceback.print_exc()
        try:
            fallback_query = f'\n                SELECT c.{code_col} AS code, c.{name_col} AS name, 0 AS outstanding\n                FROM {customer_table} c\n                WHERE 1=1 {loc_where}\n                ORDER BY c.{name_col}\n            '
            _, rows = _fetch_rows(fallback_query, params)
            return rows or []
        except Exception as e2:
            print(f'[ERROR _get_credit_customers_for_receipt fallback] {e2}')
            return []

def _get_salesmen_list() -> List[Dict[str, Any]]:
    """Get list of all salesmen for filter dropdown."""
    salesman_table = _detect_table(['SALESMAN', 'SALESMANMASTER', 'SALESMEN', 'SALESMANMST'])
    if not salesman_table:
        return []
    code_col = _detect_column(salesman_table, ['SALESMANCODE', 'salesmancode', 'CODE', 'code'])
    name_col = _detect_column(salesman_table, ['SALESMANNAME', 'salesmanname', 'NAME', 'name'])
    if not code_col:
        return []
    name_sql = f'{name_col} AS name' if name_col else 'NULL AS name'
    query = f'\n        SELECT {code_col} AS code, {name_sql}\n        FROM {salesman_table}\n        ORDER BY {code_col}\n    '
    try:
        _, rows = _fetch_rows(query, {})
        return rows or []
    except Exception as e:
        print(f'[ERROR _get_salesmen_list] {e}')
        return []

def _get_employees_list() -> List[Dict[str, Any]]:
    """Get list of employees (code, name) for C/O Employee dropdown. Table: EMPLOYEE1, filter: pending = 'Y'."""
    employee_table = _detect_table(['EMPLOYEE1', 'employee1'])
    if not employee_table:
        return []
    code_col = _detect_column(employee_table, ['EMPLOYEECODE', 'EMPLOYEE_CODE', 'employeecode'])
    name_col = _detect_column(employee_table, ['EMPLOYEENAME', 'EMPLOYEE_NAME', 'employeename'])
    if not code_col:
        return []
    name_sql = f'{name_col} AS name' if name_col else 'NULL AS name'
    pending_col = _detect_column(employee_table, ['PENDING', 'pending'])
    location_code = _resolve_location_code()
    loc_col = _detect_column(employee_table, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    where_parts = []
    params = {}
    if pending_col:
        where_parts.append(f"{pending_col} = 'Y'")
    if loc_col:
        where_parts.append(f'{loc_col} = :location_code')
        params['location_code'] = location_code
    where_sql = ' WHERE ' + ' AND '.join(where_parts) if where_parts else ''
    query = f'\n        SELECT {code_col} AS code, {name_sql}\n        FROM {employee_table}\n        {where_sql}\n        ORDER BY {code_col}\n    '
    try:
        _, rows = _fetch_rows(query, params)
        return rows or []
    except Exception as e:
        print(f'[ERROR _get_employees_list] {e}')
        return []

@bp.route('/accounts/cash-receipt')
def cash_receipt_list():
    """Cash Receipt List - from tblsettlement where flag = 'R'"""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    has_filter = 'date_from' in request.args or 'date_to' in request.args
    if has_filter and (date_from or date_to):
        receipts = _get_cash_receipt_list(date_from=date_from, date_to=date_to, limit=10000)
    else:
        receipts = _get_cash_receipt_list()
    return render_template('temporary_collection/cash_receipt_list.html', receipts=receipts, date_from=date_from, date_to=date_to, has_filter=has_filter)

def _generate_cash_receipt_list_pdf(receipts: List[Dict[str, Any]], date_from: str='', date_to: str='', location_name: str='', user_name: str='', title: str='Cash Receipt List') -> Optional[bytes]:
    """Generate PDF report for receipt list (cash or credit)."""
    if not REPORTLAB_AVAILABLE:
        print('[WARNING] reportlab not available, skipping PDF generation')
        return None
    if not receipts or len(receipts) == 0:
        print('[WARNING] No receipts to generate PDF')
        return None
    try:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5 * inch, bottomMargin=0.5 * inch)
        story = []
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontSize=16, textColor=colors.HexColor('#1f2937'), spaceAfter=12, alignment=TA_CENTER)
        title = Paragraph(title, title_style)
        story.append(title)
        story.append(Spacer(1, 0.2 * inch))
        details_data = [['Location:', location_name or 'N/A']]
        if date_from:
            details_data.append(['Date From:', date_from])
        if date_to:
            details_data.append(['Date To:', date_to])
        if not date_from and (not date_to):
            details_data.append(['Period:', 'All Records'])
        details_table = Table(details_data, colWidths=[2 * inch, 4 * inch])
        details_table.setStyle(TableStyle([('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'), ('FONTNAME', (1, 0), (1, -1), 'Helvetica'), ('FONTSIZE', (0, 0), (-1, -1), 10), ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]))
        story.append(details_table)
        story.append(Spacer(1, 0.3 * inch))
        headers = ['Sl.No', 'Date', 'Receipt No', 'Customer Code', 'Customer Name', 'Amount']
        table_data = [headers]
        wrap_style = ParagraphStyle('WrapCell', parent=styles['Normal'], fontSize=9, leading=11, wordWrap='CJK')
        total_amount = 0
        for idx, receipt in enumerate(receipts, 1):
            receipt_date = receipt.get('paidate') or receipt.get('billdate') or ''
            formatted_date = _format_pdf_date(receipt_date) if receipt_date else 'N/A'
            receipt_no = str(receipt.get('billno') or receipt.get('pendingno') or '-')
            customer_code = str(receipt.get('customercode') or '-')
            customer_name = str(receipt.get('customername') or '-')
            amount = float(receipt.get('amount') or 0)
            customer_name_para = Paragraph(customer_name, wrap_style) if customer_name and customer_name != '-' else customer_name
            table_data.append([str(idx), formatted_date, receipt_no, customer_code, customer_name_para, f'{amount:.2f}'])
            total_amount += amount
        table_data.append(['TOTAL', '', '', '', '', f'{total_amount:.2f}'])
        receipt_table = Table(table_data, colWidths=[0.5 * inch, 1.2 * inch, 1.2 * inch, 1.2 * inch, 2.5 * inch, 1.2 * inch], repeatRows=1)
        receipt_table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#667eea')), ('TEXTCOLOR', (0, 0), (-1, 0), colors.black), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, -1), 9), ('ALIGN', (0, 0), (-1, -1), 'LEFT'), ('ALIGN', (-1, 0), (-1, -1), 'RIGHT'), ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('BOTTOMPADDING', (0, 0), (-1, -1), 6), ('TOPPADDING', (0, 0), (-1, -1), 6), ('GRID', (0, 0), (-1, -2), 1, colors.HexColor('#d1d5db')), ('LINEBELOW', (0, -1), (-1, -1), 2, colors.HexColor('#374151'))]))
        story.append(receipt_table)
        story.append(Spacer(1, 0.3 * inch))
        footer_style = ParagraphStyle('FooterStyle', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#6b7280'), alignment=TA_RIGHT)
        print_datetime = datetime.now().strftime('%d/%b/%Y %I:%M %p').upper()
        footer_text = Paragraph(f"Prepared by: {user_name or 'N/A'}<br/>Printed on: {print_datetime}", footer_style)
        story.append(footer_text)
        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()
    except Exception as e:
        print(f'[ERROR _generate_cash_receipt_list_pdf] Error generating PDF: {e}')
        import traceback
        print(traceback.format_exc())
        return None

@bp.route('/accounts/cash-receipt/print-pdf', methods=['GET'])
def cash_receipt_list_print_pdf():
    """API: Generate PDF report for cash receipt list"""
    if not session.get('user'):
        return Response('Not authenticated', status=401, mimetype='text/plain')
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    try:
        if date_from or date_to:
            receipts = _get_cash_receipt_list(date_from=date_from, date_to=date_to, limit=10000)
        else:
            receipts = _get_cash_receipt_list(limit=10000)
        if not receipts:
            return Response('No receipts found', status=404, mimetype='text/plain')
        location_name = ''
        try:
            loc_info = get_location_info_by_dbkey(None)
            if loc_info:
                location_name = (loc_info.get('locationname') or '').strip()
        except Exception as e:
            print(f'[DEBUG cash_receipt_list_print_pdf] Error fetching location name: {e}')
        pdf_data = _generate_cash_receipt_list_pdf(receipts=receipts, date_from=date_from, date_to=date_to, location_name=location_name, user_name=session.get('user', ''))
        if not pdf_data:
            return Response('Failed to generate PDF', status=500, mimetype='text/plain')
        return Response(pdf_data, mimetype='application/pdf', headers={'Content-Disposition': f"inline; filename=cash_receipt_list_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"})
    except Exception as e:
        print(f'[ERROR cash_receipt_list_print_pdf] {e}')
        import traceback
        print(traceback.format_exc())
        return Response(f'Error: {str(e)}', status=500, mimetype='text/plain')

@bp.route('/accounts/cash-receipt/print-single', methods=['GET'])
def cash_receipt_print_single():
    """API: Generate PDF for a single cash receipt by receipt number"""
    if not session.get('user'):
        return Response('Not authenticated', status=401, mimetype='text/plain')
    receipt_no = request.args.get('receipt_no', '').strip()
    if not receipt_no:
        return Response('Receipt number required', status=400, mimetype='text/plain')
    try:
        settlement_table = _detect_table(['TBLSETTLEMENT', 'tblsettlement'])
        if not settlement_table:
            return Response('TBLSETTLEMENT table not found', status=500, mimetype='text/plain')
        flag_col = _detect_column(settlement_table, ['FLAG', 'FLAG_CODE', 'status'])
        pendingno_col = _detect_column(settlement_table, ['PENDINGNO', 'PENDING_NO', 'pendingno'])
        billno_col = _detect_column(settlement_table, ['BILLNO', 'BILL_NO', 'billno'])
        cust_col = _detect_column(settlement_table, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'CUSTCODE', 'customercode'])
        paidamt_col = _detect_column(settlement_table, ['PAIDAMOUNT', 'PAID_AMOUNT', 'PAIDAMT', 'PAID', 'paidamount'])
        paidate_col = _detect_column(settlement_table, ['PAIDATE', 'PAID_DATE', 'PAYMENTDATE', 'PAIDATE', 'paidate'])
        salesman_code_col = _detect_column(settlement_table, ['SALESMANCODE', 'SALESMAN_CODE', 'salesmancode'])
        remark_col = _detect_column(settlement_table, ['REMARKS', 'REMARK', 'remarks', 'remark'])
        location_code = _resolve_location_code()
        if not flag_col or not pendingno_col:
            return Response('Required columns not found', status=500, mimetype='text/plain')
        select_cols = [f's.{pendingno_col} AS pendingno', f's.{billno_col} AS billno' if billno_col else 'NULL AS billno', f's.{cust_col} AS customercode' if cust_col else 'NULL AS customercode', f's.{paidamt_col} AS paidamount' if paidamt_col else '0 AS paidamount', f's.{paidate_col} AS paidate' if paidate_col else 'NULL AS paidate']
        if salesman_code_col:
            select_cols.append(f's.{salesman_code_col} AS salesman_code')
        else:
            select_cols.append('NULL AS salesman_code')
        if remark_col:
            select_cols.append(f's.{remark_col} AS remark')
        else:
            select_cols.append('NULL AS remark')
        receipt_query = f"\n            SELECT \n                {', '.join(select_cols)}\n            FROM {settlement_table} s\n            WHERE s.{pendingno_col} = :receipt_no \n              AND s.{flag_col} = 'R'\n        "
        try:
            receipt_no_int = int(receipt_no) if receipt_no.isdigit() else receipt_no
        except:
            receipt_no_int = receipt_no
        _, receipt_rows = _fetch_rows(receipt_query, {'receipt_no': receipt_no_int})
        if not receipt_rows or len(receipt_rows) == 0:
            return Response('Receipt not found', status=404, mimetype='text/plain')
        receipt = receipt_rows[0]
        customer_code = str(receipt.get('customercode') or '').strip()
        voucherno = str(receipt.get('pendingno') or receipt.get('billno') or receipt_no)
        salesman_code = str(receipt.get('salesman_code') or '').strip()
        remark = str(receipt.get('remark') or 'Pending Amount').strip()
        pay_date_raw = receipt.get('paidate')
        if pay_date_raw:
            if isinstance(pay_date_raw, str):
                try:
                    pay_date = datetime.strptime(pay_date_raw[:10], '%Y-%m-%d')
                except:
                    pay_date = datetime.now()
            else:
                pay_date = pay_date_raw
        else:
            pay_date = datetime.now()
        temp_table = _detect_table(['TBLTEMPSETTLEMENT', 'tbltempsettlement'])
        items = []
        if temp_table:
            temp_pendingno_col = _detect_column(temp_table, ['PENDINGNO', 'PENDING_NO', 'pendingno'])
            temp_againstno_col = _detect_column(temp_table, ['AGAINSTNO', 'AGAINST_NO', 'againstno'])
            temp_paidamt_col = _detect_column(temp_table, ['PAIDAMOUNT', 'PAID_AMOUNT', 'paidamount'])
            temp_billdate_col = _detect_column(temp_table, ['BILLDATE', 'BILL_DATE', 'billdate'])
            if temp_pendingno_col and temp_againstno_col:
                item_select_cols = [f't.{temp_againstno_col} AS billno']
                if temp_paidamt_col:
                    item_select_cols.append(f't.{temp_paidamt_col} AS payamount')
                else:
                    item_select_cols.append('0 AS payamount')
                if temp_billdate_col:
                    item_select_cols.append(f't.{temp_billdate_col} AS billdate')
                else:
                    item_select_cols.append('NULL AS billdate')
                items_query = f"\n                    SELECT \n                        {', '.join(item_select_cols)}\n                    FROM {temp_table} t\n                    WHERE t.{temp_pendingno_col} = :receipt_no\n                      AND t.FLAG = 'R'\n                    ORDER BY t.{temp_againstno_col}\n                "
                try:
                    _, item_rows = _fetch_rows(items_query, {'receipt_no': receipt_no_int})
                    for item_row in item_rows:
                        items.append({'billno': str(item_row.get('billno') or ''), 'payamount': float(item_row.get('payamount') or 0), 'billdate': item_row.get('billdate')})
                except Exception as e:
                    print(f'[DEBUG cash_receipt_print_single] Error fetching items: {e}')
        if not items:
            items.append({'billno': str(receipt.get('billno') or voucherno), 'payamount': float(receipt.get('paidamount') or 0), 'billdate': pay_date})
        customer_name = _get_customer_name(customer_code)
        salesman_name = ''
        location_name = ''
        try:
            salesman_info = _get_salesman_info(salesman_code)
            if salesman_info:
                salesman_name = (salesman_info.get('salesmanname') or '').strip()
        except Exception as e:
            print(f'[DEBUG cash_receipt_print_single] Error fetching salesman name: {e}')
        try:
            loc_info = get_location_info_by_dbkey(None)
            if loc_info:
                location_name = (loc_info.get('locationname') or '').strip()
        except Exception as e:
            print(f'[DEBUG cash_receipt_print_single] Error fetching location name: {e}')
        pdf_data = _generate_cash_receipt_pdf(voucherno=voucherno, customer_code=customer_code, customer_name=customer_name, items=items, pay_date=pay_date, salesman_code=salesman_code, salesman_name=salesman_name, remark=remark, location_code=location_code, location_name=location_name, user_name=session.get('user', ''), include_customer_in_header=True, include_customer_in_table=False, pdf_title='CASH RECEIPT')
        if not pdf_data:
            return Response('Failed to generate PDF', status=500, mimetype='text/plain')
        return Response(pdf_data, mimetype='application/pdf', headers={'Content-Disposition': f"inline; filename=cash_receipt_{receipt_no}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"})
    except Exception as e:
        print(f'[ERROR cash_receipt_print_single] {e}')
        import traceback
        print(traceback.format_exc())
        return Response(f'Error: {str(e)}', status=500, mimetype='text/plain')

def _voucherno_exists(voucherno: str) -> bool:
    """Check if voucher number already exists in tblsettlement (check all records, no flag filter)."""
    if not voucherno:
        return False
    settlement_table = _detect_table(['TBLSETTLEMENT', 'tblsettlement'])
    if not settlement_table:
        return False
    pendingno_col = _detect_column(settlement_table, ['PENDINGNO', 'PENDING_NO', 'PENDINGNUMBER', 'pendingno'])
    if not pendingno_col:
        return False
    query = f'SELECT 1 FROM {settlement_table} WHERE {pendingno_col} = :voucherno'
    try:
        result = _get_scalar(query, {'voucherno': voucherno})
        return result is not None
    except Exception as e:
        print(f'[ERROR _voucherno_exists] {e}')
        return False

def _get_next_unique_voucherno(start_voucherno: str) -> str:
    """Get next unique voucher number. If start_voucherno exists, use max+1 (single query)."""
    if not start_voucherno:
        return _get_next_voucherno()
    if not _voucherno_exists(start_voucherno):
        return start_voucherno
    return _get_next_voucherno()

def _get_next_voucherno() -> str:
    """Get next voucher number: max(pendingno) + 1 from tblsettlement (all rows, no flag filter), or 1000 if empty."""
    settlement_table = _detect_table(['TBLSETTLEMENT', 'tblsettlement'])
    if not settlement_table:
        return '1000'
    pendingno_col = _detect_column(settlement_table, ['PENDINGNO', 'PENDING_NO', 'PENDINGNUMBER', 'pendingno'])
    if not pendingno_col:
        return '1000'
    query = f'SELECT MAX({pendingno_col}) AS max_pendingno FROM {settlement_table}'
    try:
        result = _get_scalar(query, {})
        if result is not None and result != '':
            try:
                max_val = int(result) if isinstance(result, (int, float)) else int(str(result).strip())
                return str(max_val + 1)
            except (ValueError, TypeError):
                return '1000'
        else:
            return '1000'
    except Exception as e:
        print(f'[ERROR _get_next_voucherno] {e}')
        return '1000'

def _voucherno_exists_credit(voucherno: str) -> bool:
    """Check if voucher number already exists in tblcreditsettlement."""
    if not voucherno:
        return False
    settlement_table = _detect_table(['TBLCREDITSETTLEMENT', 'tblcreditsettlement'])
    if not settlement_table:
        return False
    pendingno_col = _detect_column(settlement_table, ['PENDINGNO', 'PENDING_NO', 'PENDINGNUMBER', 'pendingno'])
    if not pendingno_col:
        return False
    query = f'SELECT 1 FROM {settlement_table} WHERE {pendingno_col} = :voucherno'
    try:
        result = _get_scalar(query, {'voucherno': voucherno})
        return result is not None
    except Exception as e:
        print(f'[ERROR _voucherno_exists_credit] {e}')
        return False

def _get_next_voucherno_credit() -> str:
    """Get next voucher number from tblcreditsettlement (max(pendingno) + 1), or 1000 if empty."""
    settlement_table = _detect_table(['TBLCREDITSETTLEMENT', 'tblcreditsettlement'])
    if not settlement_table:
        return '1000'
    pendingno_col = _detect_column(settlement_table, ['PENDINGNO', 'PENDING_NO', 'PENDINGNUMBER', 'pendingno'])
    if not pendingno_col:
        return '1000'
    query = f'SELECT MAX({pendingno_col}) AS max_pendingno FROM {settlement_table}'
    try:
        result = _get_scalar(query, {})
        if result is not None and result != '':
            try:
                max_val = int(result) if isinstance(result, (int, float)) else int(str(result).strip())
                return str(max_val + 1)
            except (ValueError, TypeError):
                return '1000'
        return '1000'
    except Exception as e:
        print(f'[ERROR _get_next_voucherno_credit] {e}')
        return '1000'

@bp.route('/accounts/cash-receipt/new')
def cash_receipt_new():
    """New receipt page: select customer (invoice code 1), then their outstanding invoices to make payments."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    customers = _get_cash_customers_for_receipt()
    salesmen = _get_salesmen_list()
    employees = _get_employees_list()
    payment_date = _get_transaction_date()
    voucherno = _get_next_voucherno()
    return render_template('temporary_collection/cash_receipt_new.html', customers=customers, salesmen=salesmen, employees=employees, payment_date=payment_date, voucherno=voucherno)

@bp.route('/accounts/cash-receipt/outstanding')
def cash_receipt_outstanding():
    """API: Get outstanding invoices for a customer using same method as Customer Outstanding Details. Supports date_from, date_to, and salesman_code filters."""
    if not session.get('user'):
        return jsonify({'error': 'Not authenticated'}, 401)
    customer_code = request.args.get('customer_code', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    salesman_code = request.args.get('salesman_code', '').strip()
    if not customer_code:
        return jsonify({'items': [], 'total_outstanding': 0.0})
    try:
        from db import get_customer_outstanding_details, _get_scalar, _detect_column
        rows = get_customer_outstanding_details(customer_code, 'all')
        if date_from or date_to:
            from datetime import datetime
            filtered_rows = []
            for r in rows or []:
                billdate = r.get('billdate')
                if not billdate:
                    continue
                if isinstance(billdate, str):
                    try:
                        billdate = datetime.strptime(billdate[:10], '%Y-%m-%d').date()
                    except:
                        continue
                elif hasattr(billdate, 'date'):
                    billdate = billdate.date()
                elif hasattr(billdate, 'strftime'):
                    try:
                        billdate = datetime.strptime(billdate.strftime('%Y-%m-%d'), '%Y-%m-%d').date()
                    except:
                        continue
                else:
                    continue
                if date_from:
                    try:
                        from_date = datetime.strptime(date_from[:10], '%Y-%m-%d').date()
                        if billdate < from_date:
                            continue
                    except:
                        pass
                if date_to:
                    try:
                        to_date = datetime.strptime(date_to[:10], '%Y-%m-%d').date()
                        if billdate > to_date:
                            continue
                    except:
                        pass
                filtered_rows.append(r)
            rows = filtered_rows
        if salesman_code and salesman_code.strip():
            rows = [r for r in rows or [] if (r.get('salesmancode') or '').strip() == salesman_code.strip()]
        items = [{'billno': r.get('billno') or '', 'billdate': r.get('billdate').strftime('%Y-%m-%d') if r.get('billdate') and hasattr(r.get('billdate'), 'strftime') else str(r.get('billdate') or ''), 'billamount': float(r.get('billamount') or 0), 'paidamount': float(r.get('paidamount') or 0), 'outstanding': float(r.get('outstanding') or 0), 'salesmancode': r.get('salesmancode') or '', 'salesmanname': r.get('salesmanname') or '', 'employeecode': r.get('employeecode') or '', 'employeename': r.get('employeename') or ''} for r in rows or [] if float(r.get('outstanding') or 0) > 0]
        total_outstanding = sum((float(item.get('outstanding', 0) or 0) for item in items))
        return jsonify({'items': items, 'total_outstanding': total_outstanding})
    except Exception as e:
        print(f'[ERROR cash_receipt_outstanding] {e}')
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e), 'items': [], 'total_outstanding': 0.0}, 500)

def _get_outstanding_items_for_pdf(customer_code: str, date_from: str='', date_to: str='', salesman_code: str='') -> List[Dict[str, Any]]:
    """Fetch outstanding items with same logic as cash_receipt_outstanding (for PDF report)."""
    from db import get_customer_outstanding_details
    rows = get_customer_outstanding_details(customer_code, 'all')
    if date_from or date_to:
        from datetime import datetime
        filtered_rows = []
        for r in rows or []:
            billdate = r.get('billdate')
            if not billdate:
                continue
            if isinstance(billdate, str):
                try:
                    billdate = datetime.strptime(billdate[:10], '%Y-%m-%d').date()
                except Exception:
                    continue
            elif hasattr(billdate, 'date'):
                billdate = billdate.date()
            elif hasattr(billdate, 'strftime'):
                try:
                    billdate = datetime.strptime(billdate.strftime('%Y-%m-%d'), '%Y-%m-%d').date()
                except Exception:
                    continue
            else:
                continue
            if date_from:
                try:
                    from_date = datetime.strptime(date_from[:10], '%Y-%m-%d').date()
                    if billdate < from_date:
                        continue
                except Exception:
                    pass
            if date_to:
                try:
                    to_date = datetime.strptime(date_to[:10], '%Y-%m-%d').date()
                    if billdate > to_date:
                        continue
                except Exception:
                    pass
            filtered_rows.append(r)
        rows = filtered_rows
    if salesman_code and salesman_code.strip():
        rows = [r for r in rows or [] if (r.get('salesmancode') or '').strip() == salesman_code.strip()]
    items = [{'billno': r.get('billno') or '', 'billdate': r.get('billdate').strftime('%Y-%m-%d') if r.get('billdate') and hasattr(r.get('billdate'), 'strftime') else str(r.get('billdate') or ''), 'billamount': float(r.get('billamount') or 0), 'paidamount': float(r.get('paidamount') or 0), 'outstanding': float(r.get('outstanding') or 0), 'salesmancode': r.get('salesmancode') or '', 'salesmanname': r.get('salesmanname') or '', 'employeecode': r.get('employeecode') or '', 'employeename': r.get('employeename') or ''} for r in rows or [] if float(r.get('outstanding') or 0) > 0]
    return items

@bp.route('/accounts/cash-receipt/outstanding-pdf', methods=['GET'])
def cash_receipt_outstanding_pdf():
    """Generate PDF report of outstanding invoices for the given customer (same filters as outstanding API)."""
    if not session.get('user'):
        return Response('Not authenticated', status=401, mimetype='text/plain')
    customer_code = request.args.get('customer_code', '').strip()
    if not customer_code:
        return Response('customer_code is required', status=400, mimetype='text/plain')
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    salesman_code = request.args.get('salesman_code', '').strip()
    try:
        items = _get_outstanding_items_for_pdf(customer_code, date_from=date_from, date_to=date_to, salesman_code=salesman_code)
        if not items:
            return Response('No outstanding invoices for this customer.', status=404, mimetype='text/plain')
        customer_name = _get_customer_name(customer_code)
        location_code = _resolve_location_code()
        location_name = ''
        try:
            info = get_location_info_by_dbkey(None)
            if info:
                location_name = (info.get('locationname') or '').strip()
            if not location_name and location_code:
                info = get_location_info_by_dbkey(str(location_code))
                if info:
                    location_name = (info.get('locationname') or '').strip()
        except Exception:
            pass
        pdf_bytes = _generate_outstanding_invoices_pdf(customer_code=customer_code, customer_name=customer_name, items=items, report_date=datetime.now(), date_from=date_from, date_to=date_to, location_name=location_name)
        if not pdf_bytes:
            return Response('Failed to generate PDF.', status=500, mimetype='text/plain')
        filename = f"outstanding_invoices_{customer_code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        return Response(pdf_bytes, mimetype='application/pdf', headers={'Content-Disposition': f'inline; filename="{filename}"'})
    except Exception as e:
        print(f'[ERROR cash_receipt_outstanding_pdf] {e}')
        import traceback
        traceback.print_exc()
        return Response(f'Error: {e}', status=500, mimetype='text/plain')

def _check_status_after_payment(billnos: List[str]) -> None:
    """Check and update status for each billno after payment. If balance = 0, set status='PAID', PFLAG='Y'; else status='PENDING', PFLAG='N'. Single SELECT for all billnos."""
    if not billnos:
        return
    settlement_table = _detect_table(['TBLSETTLEMENT', 'tblsettlement'])
    if not settlement_table:
        return
    billno_col = _detect_column(settlement_table, ['BILLNO', 'BILL_NO', 'billno'])
    balance_col = _detect_column(settlement_table, ['BALANCE', 'balance', 'OUTSTANDING', 'outstanding'])
    status_col = _detect_column(settlement_table, ['STATUS', 'status'])
    pflag_col = _detect_column(settlement_table, ['PFLAG', 'P_FLAG', 'pflag'])
    if not billno_col or not balance_col:
        return
    billnos_clean = [b for b in billnos if b]
    if not billnos_clean:
        return
    placeholders = ', '.join([f':b{i}' for i in range(len(billnos_clean))])
    params = {f'b{i}': b for i, b in enumerate(billnos_clean)}
    balance_query = f'SELECT {billno_col} AS billno, NVL({balance_col}, 0) AS balance FROM {settlement_table} WHERE {billno_col} IN ({placeholders})'
    try:
        _, rows = _fetch_rows(balance_query, params)
    except Exception as e:
        print(f'[ERROR _check_status_after_payment] {e}')
        return
    balance_by_billno = {}
    for r in rows or []:
        bn = str(r.get('billno', '')).strip()
        if bn:
            balance_by_billno[bn] = float(r.get('balance') or 0)
    with _get_connection() as conn:
        with conn.cursor() as cur:
            for billno in billnos_clean:
                balance_val = balance_by_billno.get(billno)
                if balance_val is None:
                    continue
                updates = []
                if balance_val == 0:
                    if status_col:
                        updates.append(f"{status_col} = 'PAID'")
                    if pflag_col:
                        updates.append(f"{pflag_col} = 'Y'")
                else:
                    if status_col:
                        updates.append(f"{status_col} = 'PENDING'")
                    if pflag_col:
                        updates.append(f"{pflag_col} = 'N'")
                if updates:
                    update_query = f"UPDATE {settlement_table} SET {', '.join(updates)} WHERE {billno_col} = :billno"
                    cur.execute(update_query, {'billno': billno})
            conn.commit()

@bp.route('/accounts/cash-receipt/save', methods=['POST'])
def cash_receipt_save():
    """API: Save new receipt - insert tblsettlement (flag R), tbltempsettlement, update outstanding rows. Matches VB code logic."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    data = request.get_json(silent=True) or {}
    submitted_nonce = (data.get('save_nonce') or '').strip()
    if not verify_consume_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY, submitted_nonce):
        return replay_blocked_response_global()
    try:
        loc_info = get_location_info_by_dbkey(None)
        expected_locationcode = loc_info.get('locationcode') if loc_info else None
    except Exception:
        expected_locationcode = None
    payload_location_code = data.get('location_code')
    if payload_location_code is not None and expected_locationcode is not None:
        try:
            payload_loc = int(payload_location_code) if str(payload_location_code).isdigit() else None
            if payload_loc is not None and payload_loc != int(expected_locationcode):
                return json_response_rotate_global({'success': False, 'error': 'Location code mismatch. Do not save.'}, 400)
        except (ValueError, TypeError):
            return json_response_rotate_global({'success': False, 'error': 'Location code mismatch. Do not save.'}, 400)
    voucherno = (data.get('voucherno') or '').strip()
    paydate_str = (data.get('paydate') or '').strip()
    customer_code = (data.get('customer_code') or '').strip()
    salesman_code = (data.get('salesman_code') or '').strip()
    remark = (data.get('remark') or '').strip()
    raw_items = data.get('items') or []
    if not voucherno or not paydate_str:
        return json_response_rotate_global({'success': False, 'error': 'Please Click New Button'}, 400)
    if not paydate_str:
        return json_response_rotate_global({'success': False, 'error': 'Please Open Receipt Day'}, 400)
    if not salesman_code:
        return json_response_rotate_global({'success': False, 'error': 'Please select a salesman'}, 400)
    original_voucherno = voucherno
    latest_voucherno = _get_next_voucherno()
    if latest_voucherno:
        voucherno = latest_voucherno
        if original_voucherno and original_voucherno != voucherno:
            print(f'[INFO cash_receipt_save] Using latest voucher number {voucherno} instead of requested {original_voucherno}')
    items = []
    for it in raw_items:
        billno = (it.get('billno') or '').strip()
        amount = float(it.get('amount') or it.get('payamount') or 0)
        if not billno or amount == 0:
            continue
        items.append({'billno': billno, 'payamount': amount, 'salesmancode': (it.get('salesmancode') or '').strip()})
    if not items:
        return json_response_rotate_global({'success': False, 'error': 'Please Check Data'}, 400)
    if not remark:
        remark = 'Pending Amount'
    try:
        pay_date = datetime.strptime(paydate_str[:10], '%Y-%m-%d')
    except (ValueError, TypeError):
        return json_response_rotate_global({'success': False, 'error': 'Invalid payment date'}, 400)
    try:
        location_code = _resolve_location_code()
        puser = session.get('user', '')
        meta = {'voucherno': voucherno, 'paydate': pay_date, 'locationcode': location_code, 'remark': remark, 'puser': puser, 'salesmancode': salesman_code}
        process_payments(customer_code, items, meta)
        response_data = {'success': True, 'message': 'Receipt saved.', 'receipt_no': voucherno}
        if voucherno != original_voucherno:
            response_data['voucherno_changed'] = True
            response_data['original_voucherno'] = original_voucherno
            response_data['message'] = f'Receipt saved. Voucher number changed from {original_voucherno} to {voucherno} (original already exists).'
        try:
            items_with_dates = items.copy()
            customer_name = _get_customer_name(customer_code)
            salesman_name = ''
            location_name = ''
            try:
                salesman_info = _get_salesman_info(salesman_code)
                if salesman_info:
                    salesman_name = (salesman_info.get('salesmanname') or '').strip()
            except Exception as e:
                print(f'[DEBUG cash_receipt_save] Error fetching salesman name: {e}')
            try:
                loc_info = get_location_info_by_dbkey(None)
                if loc_info:
                    location_name = (loc_info.get('locationname') or '').strip()
            except Exception as e:
                print(f'[DEBUG cash_receipt_save] Error fetching location name: {e}')
            pdf_data = None
            pdf_error = None
            try:
                if not REPORTLAB_AVAILABLE:
                    pdf_error = 'PDF library (reportlab) is not available'
                    print(f'[WARNING cash_receipt_save] {pdf_error}')
                elif not items_with_dates or len(items_with_dates) == 0:
                    pdf_error = 'No items to generate PDF'
                    print(f'[WARNING cash_receipt_save] {pdf_error}')
                else:
                    pdf_data = _generate_cash_receipt_pdf(voucherno=voucherno, customer_code=customer_code, customer_name=customer_name, items=items_with_dates, pay_date=pay_date, salesman_code=salesman_code, salesman_name=salesman_name, remark=remark, location_code=location_code, location_name=location_name, user_name=puser)
                    if pdf_data:
                        try:
                            import base64
                            response_data['pdf_base64'] = base64.b64encode(pdf_data).decode('utf-8')
                            response_data['pdf_filename'] = f"cash_receipt_{voucherno}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                        except Exception as encode_err:
                            pdf_error = f'PDF encoding error: {str(encode_err)}'
                            print(f'[ERROR cash_receipt_save] {pdf_error}')
                    else:
                        pdf_error = 'PDF generation returned empty data'
                        print(f'[WARNING cash_receipt_save] {pdf_error}')
            except Exception as e:
                pdf_error = f'PDF generation error: {str(e)}'
                print(f'[ERROR cash_receipt_save] {pdf_error}')
                import traceback
                traceback.print_exc()
            if pdf_error:
                response_data['pdf_error'] = pdf_error
        except Exception as e:
            print(f'[ERROR cash_receipt_save] Error in PDF preparation: {e}')
        return json_response_rotate_global(response_data)
    except Exception as e:
        print(f'[ERROR cash_receipt_save] {e}')
        import traceback
        traceback.print_exc()
        return json_response_rotate_global({'success': False, 'error': str(e)}, 500)

@bp.route('/accounts/cash-receipt/update-co-employee', methods=['POST'])
def cash_receipt_update_co_employee():
    """API: Update employeecode, required expecteddate and optional remarks in tblsettlement for selected billnos (flag 'B' invoice rows)."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    data = request.get_json(silent=True) or {}
    employeecode_raw = data.get('employeecode')
    billnos = data.get('billnos') or []
    expecteddate_raw = data.get('expecteddate')
    remarks_raw = (data.get('remarks') or '').strip()
    if not billnos or employeecode_raw is None:
        return jsonify({'success': False, 'error': 'employeecode and billnos are required'}, 400)
    if not expecteddate_raw or not str(expecteddate_raw).strip():
        return jsonify({'success': False, 'error': 'expecteddate is required'}, 400)
    try:
        employeecode = int(employeecode_raw) if employeecode_raw not in (None, '') else 0
    except (ValueError, TypeError):
        employeecode = 0
    billnos_clean = [str(b).strip() for b in billnos if str(b).strip()]
    if not billnos_clean:
        return jsonify({'success': False, 'error': 'No valid bill numbers selected'}, 400)
    settlement_table = _detect_table(['TBLSETTLEMENT', 'tblsettlement'])
    if not settlement_table:
        return jsonify({'success': False, 'error': 'TBLSETTLEMENT table not found'}, 500)
    billno_col = _detect_column(settlement_table, ['BILLNO', 'BILL_NO', 'billno'])
    flag_col = _detect_column(settlement_table, ['FLAG', 'flag'])
    emp_col = _detect_column(settlement_table, ['EMPLOYEECODE', 'EMPLOYEE_CODE', 'employeecode'])
    exp_col = _detect_column(settlement_table, ['EXPECTEDDATE', 'EXPECTED_DATE', 'expecteddate', 'expected_date', 'EXPECTED', 'expected'])
    remark_col = _detect_column(settlement_table, ['REMARKS', 'REMARK', 'remarks', 'remark'])
    if not billno_col or not flag_col:
        return jsonify({'success': False, 'error': 'Required columns not found in TBLSETTLEMENT'}, 500)
    if not emp_col:
        return jsonify({'success': False, 'error': 'EMPLOYEECODE column not found in TBLSETTLEMENT'}, 500)
    set_parts = [f'{emp_col} = :emp']
    params = {f'b{i}': b for i, b in enumerate(billnos_clean)}
    params['emp'] = employeecode
    expecteddate_oracle = None
    if expecteddate_raw and isinstance(expecteddate_raw, str) and expecteddate_raw.strip():
        expecteddate_str = expecteddate_raw.strip()[:10]
        if exp_col and len(expecteddate_str) >= 10 and ('-' in expecteddate_str):
            try:
                from datetime import datetime as _dt
                d = _dt.strptime(expecteddate_str, '%Y-%m-%d')
                expecteddate_oracle = d.strftime('%d/%b/%Y').upper()
                set_parts.append(f"{exp_col} = TO_DATE(:expecteddate, 'DD/MON/YYYY')")
                params['expecteddate'] = expecteddate_oracle
            except ValueError:
                pass
    if remark_col and remarks_raw:
        set_parts.append(f'{remark_col} = :remarks')
        params['remarks'] = remarks_raw[:500] if remarks_raw else None
    placeholders = ', '.join([f':b{i}' for i in range(len(billnos_clean))])
    update_sql = f"UPDATE {settlement_table} SET {', '.join(set_parts)} WHERE {billno_col} IN ({placeholders}) AND ({flag_col} = 'B' OR {flag_col} IS NULL)"
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(update_sql, params)
                updated = cur.rowcount
            conn.commit()
        created_by = session.get('user')
        expecteddate_str = None
        if expecteddate_raw and isinstance(expecteddate_raw, str) and expecteddate_raw.strip():
            expecteddate_str = expecteddate_raw.strip()[:10]
        for b in billnos_clean:
            try:
                insert_payment_followup_only(billno=b, expecteddate=expecteddate_str, remarks=remarks_raw or None, created_by=created_by)
            except Exception as ins_err:
                print(f'[WARN cash_receipt_update_co_employee] insert_payment_followup_only for billno={b}: {ins_err}')
        return jsonify({'success': True, 'updated': updated, 'message': f'Updated C/O Employee and expected date for {updated} invoice(s).'})
    except Exception as e:
        print(f'[ERROR cash_receipt_update_co_employee] {e}')
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}, 500)

@bp.route('/accounts/cash-receipt/temp-settlement')
def cash_receipt_temp_settlement():
    """Temp settlement detail: tbltempsettlement WHERE flag = 'R'. If receipt_no in query, filter by pendingno. When opening from list, check receipt_no and customer_code."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    receipt_no = request.args.get('receipt_no', '').strip() or None
    customer_code = request.args.get('customer_code', '').strip() or None
    rows = _get_temp_settlement_receipt_list(receipt_no=receipt_no, customer_code=customer_code)
    return render_template('temporary_collection/temp_settlement_receipt_list.html', rows=rows, receipt_no=receipt_no, customer_code=customer_code)
RESET_RECEIPT_PASSWORD = '123'

@bp.route('/accounts/cash-receipt/temp-settlement/reset', methods=['POST'])
def cash_receipt_temp_settlement_reset():
    """Reset (revise) receipt: archive to REVISE tables, reverse payments on tblsettlement, delete from TBLTEMPSETTLEMENT and TBLSETTLEMENT. Requires password."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    data = request.get_json(silent=True) or {}
    receipt_no = str(data.get('receipt_no') or '').strip()
    customer_code = str(data.get('customer_code') or '').strip()
    password = str(data.get('password') or '').strip()
    if password != RESET_RECEIPT_PASSWORD:
        return jsonify({'success': False, 'error': 'Invalid password'}, 400)
    if not receipt_no or not customer_code:
        return jsonify({'success': False, 'error': 'Please Check Voucher No'}, 400)
    location_code = _resolve_location_code()
    current_user = session.get('user', '')
    remark_revise = f'REVISED RECEIPTNO :{receipt_no}'
    try:
        settlement_table = _detect_table(['TBLSETTLEMENT', 'tblsettlement'])
        temp_table = _detect_table(['TBLTEMPSETTLEMENT', 'tbltempsettlement'])
        settle_revise_table = _detect_table(['TBLSETTLEMENTREVISE', 'tblsettlementrevise'])
        temp_revise_table = _detect_table(['TBLTEMPSETTLEMENTREVISE', 'tbltempsettlementrevise'])
        if not settlement_table or not temp_table:
            return jsonify({'success': False, 'error': 'Required tables not found'}, 500)
        receipt_no_param = int(receipt_no) if receipt_no.isdigit() else receipt_no
        with _get_connection() as conn:
            with conn.cursor() as cur:
                flag_col = _detect_column(settlement_table, ['FLAG', 'flag'])
                pendingno_col = _detect_column(settlement_table, ['PENDINGNO', 'PENDING_NO', 'pendingno'])
                billno_col = _detect_column(settlement_table, ['BILLNO', 'BILL_NO', 'billno'])
                billdate_col = _detect_column(settlement_table, ['BILLDATE', 'BILL_DATE', 'billdate'])
                billamount_col = _detect_column(settlement_table, ['BILLAMOUNT', 'BILL_AMOUNT', 'billamount'])
                cust_col = _detect_column(settlement_table, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'customercode'])
                remark_col = _detect_column(settlement_table, ['REMARK', 'REMARKS', 'remark'])
                loc_col = _detect_column(settlement_table, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
                sett_salesmancode_col = _detect_column(settlement_table, ['SALESMANCODE', 'SALESMAN_CODE', 'salesmancode'])
                sett_balance_col = _detect_column(settlement_table, ['BALANCE', 'balance', 'OUTSTANDING', 'outstanding'])
                sett_paidamt_col = _detect_column(settlement_table, ['PAIDAMOUNT', 'PAID_AMOUNT', 'PAIDAMT', 'paidamount'])
                if not all([flag_col, pendingno_col, cust_col]):
                    return jsonify({'success': False, 'error': 'Settlement columns not found'}, 500)
                summary_select = f"{pendingno_col}, {billno_col}, {billdate_col}, {billamount_col}, {remark_col or 'NULL'}"
                if sett_salesmancode_col:
                    summary_select += f', {sett_salesmancode_col}'
                if sett_balance_col:
                    summary_select += f', NVL({sett_balance_col}, 0)'
                if sett_paidamt_col:
                    summary_select += f', NVL({sett_paidamt_col}, 0)'
                summary_query = f"\n                    SELECT {summary_select}\n                    FROM {settlement_table}\n                    WHERE {pendingno_col} = :rn AND {cust_col} = :cc AND {flag_col} = 'R'\n                "
                cur.execute(summary_query, {'rn': receipt_no_param, 'cc': customer_code})
                summary_row = cur.fetchone()
                if not summary_row:
                    return jsonify({'success': False, 'error': 'Receipt not found'}, 404)
                summary_pendingno, summary_billno, summary_billdate, summary_billamount, summary_remark = (summary_row[0], summary_row[1], summary_row[2], summary_row[3], summary_row[4] if len(summary_row) > 4 else None)
                summary_salesmancode = (summary_row[5] if sett_salesmancode_col and len(summary_row) > 5 else None) or ''
                billdate_oracle = summary_billdate
                if billdate_oracle and hasattr(billdate_oracle, 'strftime'):
                    billdate_oracle = billdate_oracle.strftime('%d/%b/%Y').upper()
                elif not billdate_oracle:
                    billdate_oracle = datetime.now().strftime('%d/%b/%Y').upper()
                total_amount = float(summary_billamount) if summary_billamount is not None else 0
                temp_pendingno_col = _detect_column(temp_table, ['PENDINGNO', 'PENDING_NO', 'pendingno'])
                temp_againstno_col = _detect_column(temp_table, ['AGAINSTNO', 'AGAINST_NO', 'againstno'])
                temp_paidamt_col = _detect_column(temp_table, ['PAIDAMOUNT', 'PAID_AMOUNT', 'paidamount'])
                temp_cust_col = _detect_column(temp_table, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'customercode'])
                temp_flag_col = _detect_column(temp_table, ['FLAG', 'flag'])
                temp_paiddate_col = _detect_column(temp_table, ['PAIDDATE', 'PAID_DATE', 'paiddate'])
                temp_puser_col = _detect_column(temp_table, ['PUSER', 'puser', 'P_USER'])
                temp_remarks_col = _detect_column(temp_table, ['REMARKS', 'REMARK', 'remarks', 'remark'])
                temp_salesmancode_col = _detect_column(temp_table, ['SALESMANCODE', 'SALESMAN_CODE', 'salesmancode'])
                if not all([temp_pendingno_col, temp_againstno_col, temp_cust_col, temp_flag_col]):
                    return jsonify({'success': False, 'error': 'Temp settlement columns not found'}, 500)
                temp_select = f't.{temp_againstno_col} AS againstno, NVL(t.{temp_paidamt_col}, 0) AS paidamount'
                if temp_salesmancode_col:
                    temp_select += f', t.{temp_salesmancode_col} AS salesmancode'
                temp_query = f"\n                    SELECT {temp_select}\n                    FROM {temp_table} t\n                    WHERE t.{temp_pendingno_col} = :rn AND t.{temp_cust_col} = :cc AND t.{temp_flag_col} = 'R'\n                "
                cur.execute(temp_query, {'rn': receipt_no_param, 'cc': customer_code})
                temp_rows = cur.fetchall()
                if not temp_rows or len(temp_rows) == 0:
                    return jsonify({'success': False, 'error': 'Please Check Data'}, 400)
                if not summary_salesmancode and temp_salesmancode_col and (len(temp_rows[0]) > 2):
                    summary_salesmancode = str(temp_rows[0][2] or '').strip()
                if settle_revise_table and loc_col and remark_col:
                    rev_loc = _detect_column(settle_revise_table, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
                    rev_pending = _detect_column(settle_revise_table, ['PENDINGNO', 'PENDING_NO', 'pendingno'])
                    rev_billno = _detect_column(settle_revise_table, ['BILLNO', 'BILL_NO', 'billno'])
                    rev_billdate = _detect_column(settle_revise_table, ['BILLDATE', 'BILL_DATE', 'billdate'])
                    rev_billamount = _detect_column(settle_revise_table, ['BILLAMOUNT', 'BILL_AMOUNT', 'billamount'])
                    rev_cust = _detect_column(settle_revise_table, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'customercode'])
                    rev_remark = _detect_column(settle_revise_table, ['REMARK', 'REMARKS', 'remark'])
                    rev_flag = _detect_column(settle_revise_table, ['FLAG', 'flag'])
                    rev_salesman = _detect_column(settle_revise_table, ['SALESMANCODE', 'SALESMAN_CODE', 'salesmancode'])
                    if all([rev_loc, rev_pending, rev_billno, rev_cust, rev_flag]):
                        rev_cols = [rev_loc, rev_pending, rev_billno]
                        rev_vals = [':loc', ':pendingno', ':billno']
                        if rev_billdate:
                            rev_cols.append(rev_billdate)
                            rev_vals.append("TO_DATE(:billdate, 'DD/MON/YYYY')")
                        if rev_billamount:
                            rev_cols.append(rev_billamount)
                            rev_vals.append(':billamount')
                        rev_cols.extend([rev_cust, rev_remark, rev_flag])
                        rev_vals.extend([':customercode', ':remark', "'R'"])
                        rev_params = {'loc': location_code, 'pendingno': receipt_no, 'billno': receipt_no, 'billdate': billdate_oracle, 'billamount': total_amount, 'customercode': customer_code, 'remark': remark_revise}
                        if rev_salesman:
                            rev_cols.append(rev_salesman)
                            rev_vals.append(':salesmancode')
                            rev_params['salesmancode'] = summary_salesmancode or ''
                        cur.execute(f"INSERT INTO {settle_revise_table} ({', '.join(rev_cols)}) VALUES ({', '.join(rev_vals)})", rev_params)
                if temp_revise_table:
                    rev_loc = _detect_column(temp_revise_table, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
                    rev_pending = _detect_column(temp_revise_table, ['PENDINGNO', 'PENDING_NO', 'pendingno'])
                    rev_cust = _detect_column(temp_revise_table, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'customercode'])
                    rev_status = _detect_column(temp_revise_table, ['STATUS', 'status'])
                    rev_pflag = _detect_column(temp_revise_table, ['PFLAG', 'P_FLAG', 'pflag'])
                    rev_paidamt = _detect_column(temp_revise_table, ['PAIDAMOUNT', 'PAID_AMOUNT', 'paidamount'])
                    rev_balance = _detect_column(temp_revise_table, ['BALANCE', 'balance'])
                    rev_againstno = _detect_column(temp_revise_table, ['AGAINSTNO', 'AGAINST_NO', 'againstno'])
                    rev_paiddate = _detect_column(temp_revise_table, ['PAIDDATE', 'PAID_DATE', 'paiddate'])
                    rev_flag = _detect_column(temp_revise_table, ['FLAG', 'flag'])
                    rev_puser = _detect_column(temp_revise_table, ['PUSER', 'puser', 'P_USER'])
                    rev_remarks = _detect_column(temp_revise_table, ['REMARKS', 'REMARK', 'remarks', 'remark'])
                    rev_salesman = _detect_column(temp_revise_table, ['SALESMANCODE', 'SALESMAN_CODE', 'salesmancode'])
                    rev_billamount = _detect_column(temp_revise_table, ['BILLAMOUNT', 'BILL_AMOUNT', 'billamount'])
                    rev_version = _detect_column(temp_revise_table, ['VERSION', 'version'])
                    if all([rev_loc, rev_pending, rev_cust, rev_status, rev_paidamt, rev_againstno, rev_flag]):
                        for row in temp_rows:
                            againstno_val, paidamt_val = (row[0], float(row[1]))
                            ins_cols = [rev_loc, rev_pending, rev_cust, rev_status, rev_paidamt, rev_againstno, rev_flag]
                            ins_vals = [':loc', ':pendingno', ':customercode', "'PAID'", ':paidamount', ':againstno', "'R'"]
                            if rev_pflag:
                                ins_cols.append(rev_pflag)
                                ins_vals.append("'N'")
                            if rev_balance:
                                ins_cols.append(rev_balance)
                                ins_vals.append(':bal_rev')
                            if rev_paiddate:
                                ins_cols.append(rev_paiddate)
                                ins_vals.append("TO_DATE(:paiddate, 'DD/MON/YYYY')")
                            if rev_puser:
                                ins_cols.append(rev_puser)
                                ins_vals.append(':puser')
                            if rev_remarks:
                                ins_cols.append(rev_remarks)
                                ins_vals.append(':remarks')
                            if rev_salesman:
                                ins_cols.append(rev_salesman)
                                ins_vals.append(':salesmancode')
                            if rev_billamount:
                                ins_cols.append(rev_billamount)
                                ins_vals.append('0')
                            if rev_version:
                                ins_cols.append(rev_version)
                                ins_vals.append('20')
                            params_rev = {'loc': location_code, 'pendingno': receipt_no, 'customercode': customer_code, 'paidamount': paidamt_val, 'againstno': againstno_val, 'paiddate': billdate_oracle, 'puser': current_user, 'remarks': remark_revise, 'salesmancode': ''}
                            if rev_balance:
                                params_rev['bal_rev'] = paidamt_val
                            cur.execute(f"INSERT INTO {temp_revise_table} ({', '.join(ins_cols)}) VALUES ({', '.join(ins_vals)})", params_rev)
                settle_paidamt = _detect_column(settlement_table, ['PAIDAMOUNT', 'PAID_AMOUNT', 'paidamount'])
                settle_balance = _detect_column(settlement_table, ['BALANCE', 'balance'])
                settle_billno = _detect_column(settlement_table, ['BILLNO', 'BILL_NO', 'billno'])
                settle_status = _detect_column(settlement_table, ['STATUS', 'status'])
                settle_pflag = _detect_column(settlement_table, ['PFLAG', 'P_FLAG', 'pflag'])
                if all([settle_paidamt, settle_balance, settle_billno, cust_col, flag_col]):
                    set_parts = [f'{settle_paidamt} = {settle_paidamt} - :amt', f'{settle_balance} = {settle_balance} + :amt']
                    if settle_status:
                        set_parts.append(f"{settle_status} = 'PENDING'")
                    if settle_pflag:
                        set_parts.append(f"{settle_pflag} = 'N'")
                    reverse_sql = f"UPDATE {settlement_table} SET {', '.join(set_parts)} WHERE {settle_billno} = :billno AND {cust_col} = :cc AND {flag_col} = 'B'"
                    for row in temp_rows:
                        againstno_val, paidamt_val = (row[0], float(row[1]))
                        cur.execute(reverse_sql, {'amt': paidamt_val, 'billno': againstno_val, 'cc': customer_code})
                cur.execute(f'DELETE FROM {temp_table} WHERE {temp_pendingno_col} = :rn AND {temp_cust_col} = :cc', {'rn': receipt_no_param, 'cc': customer_code})
                cur.execute(f"DELETE FROM {settlement_table} WHERE {pendingno_col} = :rn AND {cust_col} = :cc AND {flag_col} = 'R'", {'rn': receipt_no_param, 'cc': customer_code})
                conn.commit()
        return jsonify({'success': True, 'message': f'Revised Receipt No {receipt_no}'})
    except Exception as e:
        print(f'[ERROR cash_receipt_temp_settlement_reset] {e}')
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}, 500)

@bp.route('/accounts/credit-receipt')
def credit_receipt_list():
    """Credit Receipt List - from tblcreditsettlement where flag = 'R'."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    has_filter = 'date_from' in request.args or 'date_to' in request.args
    if has_filter and (date_from or date_to):
        receipts = _get_credit_receipt_list(date_from=date_from, date_to=date_to, limit=10000)
    else:
        receipts = _get_credit_receipt_list()
    return render_template('temporary_collection/credit_receipt_list.html', receipts=receipts, date_from=date_from, date_to=date_to, has_filter=has_filter)

@bp.route('/accounts/credit-receipt/print-pdf', methods=['GET'])
def credit_receipt_list_print_pdf():
    """Print Credit Receipt list as PDF."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    if date_from or date_to:
        receipts = _get_credit_receipt_list(date_from=date_from, date_to=date_to, limit=10000)
    else:
        receipts = _get_credit_receipt_list(limit=10000)
    location_name = ''
    try:
        loc_info = get_location_info_by_dbkey(None)
        if loc_info:
            location_name = (loc_info.get('locationname') or '').strip()
    except Exception:
        pass
    pdf_data = _generate_cash_receipt_list_pdf(receipts=receipts, date_from=date_from, date_to=date_to, location_name=location_name, user_name=session.get('user', ''), title='Credit Receipt List')
    if not pdf_data:
        return Response('PDF generation failed', status=500, mimetype='text/plain')
    return Response(pdf_data, mimetype='application/pdf', headers={'Content-Disposition': f"inline; filename=credit_receipt_list_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"})

@bp.route('/accounts/credit-receipt/print-single', methods=['GET'])
def credit_receipt_print_single():
    """Print single Credit Receipt by receipt_no and customer_code."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    receipt_no = request.args.get('receipt_no', '').strip()
    customer_code = request.args.get('customer_code', '').strip()
    if not receipt_no or not customer_code:
        return Response('receipt_no and customer_code required', status=400, mimetype='text/plain')
    rows = _get_temp_cr_settlement_receipt_list(receipt_no=receipt_no, customer_code=customer_code)
    if not rows:
        return Response('Receipt not found', status=404, mimetype='text/plain')
    items = []
    for r in rows:
        items.append({'billno': r.get('billno') or '', 'payamount': float(r.get('amount') or 0), 'salesmancode': (r.get('salesmancode') or '').strip()})
    pay_date = datetime.now().date()
    if rows and rows[0].get('paiddate'):
        try:
            d = rows[0]['paiddate']
            pay_date = d.date() if hasattr(d, 'date') else datetime.strptime(str(d)[:10], '%Y-%m-%d').date()
        except Exception:
            pass
    customer_name = _get_customer_name(customer_code)
    salesman_code = (rows[0].get('salesmancode') or '').strip() if rows else ''
    salesman_name = ''
    try:
        si = _get_salesman_info(salesman_code)
        if si:
            salesman_name = (si.get('salesmanname') or '').strip()
    except Exception:
        pass
    location_name = ''
    try:
        loc_info = get_location_info_by_dbkey(None)
        if loc_info:
            location_name = (loc_info.get('locationname') or '').strip()
    except Exception:
        pass
    pdf_data = _generate_cash_receipt_pdf(voucherno=receipt_no, customer_code=customer_code, customer_name=customer_name, items=items, pay_date=pay_date, salesman_code=salesman_code, salesman_name=salesman_name, remark='', location_code=_resolve_location_code(), location_name=location_name, user_name=session.get('user', ''), pdf_title='CREDIT RECEIPT', include_negative_amounts=True)
    if not pdf_data:
        return Response('PDF generation failed', status=500, mimetype='text/plain')
    return Response(pdf_data, mimetype='application/pdf', headers={'Content-Disposition': f"inline; filename=credit_receipt_{receipt_no}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"})

def _serialize_customer_for_json(c: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure customer dict is JSON-serializable (e.g. Decimal -> float)."""
    from decimal import Decimal
    code = c.get('code')
    name = c.get('name')
    out = c.get('outstanding')
    if isinstance(out, Decimal):
        out = float(out)
    elif out is not None and (not isinstance(out, (int, float))):
        try:
            out = float(out)
        except (TypeError, ValueError):
            out = 0.0
    return {'code': str(code) if code is not None else '', 'name': str(name) if name is not None else '', 'outstanding': float(out) if out is not None else 0.0}

@bp.route('/accounts/credit-receipt/api/customers', methods=['GET'])
def credit_receipt_api_customers():
    """API: Get customers for Credit Receipt popup: customercode, customername, outstanding (SUM(balance) WHERE flag <> 'R')."""
    if not session.get('user'):
        return jsonify({'error': 'Not authenticated', 'customers': []}, 401)
    try:
        customers = _get_credit_customers_for_receipt()
        serialized = [_serialize_customer_for_json(c) for c in customers]
        return jsonify({'customers': serialized})
    except Exception as e:
        print(f'[ERROR credit_receipt_api_customers] {e}')
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e), 'customers': []}, 500)

@bp.route('/accounts/credit-receipt/new')
def credit_receipt_new():
    """New Credit Receipt page: select customer, then outstanding from tblcreditsettlement."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    customers = _get_credit_customers_for_receipt()
    salesmen = _get_salesmen_list()
    employees = _get_employees_list()
    payment_date = _get_transaction_date()
    voucherno = _get_next_voucherno_credit()
    return render_template('temporary_collection/credit_receipt_new.html', customers=customers, salesmen=salesmen, employees=employees, payment_date=payment_date, voucherno=voucherno)

@bp.route('/accounts/credit-receipt/outstanding')
def credit_receipt_outstanding():
    """API: Get outstanding for a customer from GL / accounts (get_customer_outstanding_details_credit)."""
    if not session.get('user'):
        return jsonify({'error': 'Not authenticated'}, 401)
    customer_code = request.args.get('customer_code', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    salesman_code = request.args.get('salesman_code', '').strip()
    if not customer_code:
        return jsonify({'items': [], 'total_outstanding': 0.0})
    try:
        rows = get_customer_outstanding_details_credit(customer_code, 'all')
        if date_from or date_to:
            from datetime import datetime
            filtered_rows = []
            for r in rows or []:
                billdate = r.get('billdate')
                if not billdate:
                    continue
                if isinstance(billdate, str):
                    try:
                        billdate = datetime.strptime(billdate[:10], '%Y-%m-%d').date()
                    except Exception:
                        continue
                elif hasattr(billdate, 'date'):
                    billdate = billdate.date()
                elif hasattr(billdate, 'strftime'):
                    try:
                        billdate = datetime.strptime(billdate.strftime('%Y-%m-%d'), '%Y-%m-%d').date()
                    except Exception:
                        continue
                else:
                    continue
                if date_from:
                    try:
                        from_date = datetime.strptime(date_from[:10], '%Y-%m-%d').date()
                        if billdate < from_date:
                            continue
                    except Exception:
                        pass
                if date_to:
                    try:
                        to_date = datetime.strptime(date_to[:10], '%Y-%m-%d').date()
                        if billdate > to_date:
                            continue
                    except Exception:
                        pass
                filtered_rows.append(r)
            rows = filtered_rows
        if salesman_code and salesman_code.strip():
            rows = [r for r in rows or [] if (r.get('salesmancode') or '').strip() == salesman_code.strip()]
        items = [{'billno': r.get('billno') or '', 'billdate': r.get('billdate').strftime('%Y-%m-%d') if r.get('billdate') and hasattr(r.get('billdate'), 'strftime') else str(r.get('billdate') or ''), 'billamount': float(r.get('billamount') or 0), 'paidamount': float(r.get('paidamount') or 0), 'outstanding': float(r.get('outstanding') or 0), 'salesmancode': r.get('salesmancode') or '', 'salesmanname': r.get('salesmanname') or '', 'employeecode': r.get('employeecode') or '', 'employeename': r.get('employeename') or ''} for r in rows or [] if float(r.get('outstanding') or 0) != 0]
        total_outstanding = sum((float(item.get('outstanding', 0) or 0) for item in items))
        return jsonify({'items': items, 'total_outstanding': total_outstanding})
    except Exception as e:
        print(f'[ERROR credit_receipt_outstanding] {e}')
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e), 'items': [], 'total_outstanding': 0.0}, 500)

def _get_outstanding_items_for_pdf_credit(customer_code: str, date_from: str='', date_to: str='', salesman_code: str='') -> List[Dict[str, Any]]:
    """Fetch outstanding items with same logic as credit_receipt_outstanding (for PDF report)."""
    rows = get_customer_outstanding_details_credit(customer_code, 'all')
    if date_from or date_to:
        from datetime import datetime
        filtered_rows = []
        for r in rows or []:
            billdate = r.get('billdate')
            if not billdate:
                continue
            if isinstance(billdate, str):
                try:
                    billdate = datetime.strptime(billdate[:10], '%Y-%m-%d').date()
                except Exception:
                    continue
            elif hasattr(billdate, 'date'):
                billdate = billdate.date()
            elif hasattr(billdate, 'strftime'):
                try:
                    billdate = datetime.strptime(billdate.strftime('%Y-%m-%d'), '%Y-%m-%d').date()
                except Exception:
                    continue
            else:
                continue
            if date_from:
                try:
                    from_date = datetime.strptime(date_from[:10], '%Y-%m-%d').date()
                    if billdate < from_date:
                        continue
                except Exception:
                    pass
            if date_to:
                try:
                    to_date = datetime.strptime(date_to[:10], '%Y-%m-%d').date()
                    if billdate > to_date:
                        continue
                except Exception:
                    pass
            filtered_rows.append(r)
        rows = filtered_rows
    if salesman_code and salesman_code.strip():
        rows = [r for r in rows or [] if (r.get('salesmancode') or '').strip() == salesman_code.strip()]
    items = [{'billno': r.get('billno') or '', 'billdate': r.get('billdate').strftime('%Y-%m-%d') if r.get('billdate') and hasattr(r.get('billdate'), 'strftime') else str(r.get('billdate') or ''), 'billamount': float(r.get('billamount') or 0), 'paidamount': float(r.get('paidamount') or 0), 'outstanding': float(r.get('outstanding') or 0), 'salesmancode': r.get('salesmancode') or '', 'salesmanname': r.get('salesmanname') or '', 'employeecode': r.get('employeecode') or '', 'employeename': r.get('employeename') or ''} for r in rows or [] if float(r.get('outstanding') or 0) != 0]
    return items

@bp.route('/accounts/credit-receipt/outstanding-pdf', methods=['GET'])
def credit_receipt_outstanding_pdf():
    """Generate PDF report of outstanding invoices for the given customer (same design as cash receipt outstanding PDF)."""
    if not session.get('user'):
        return Response('Not authenticated', status=401, mimetype='text/plain')
    customer_code = request.args.get('customer_code', '').strip()
    if not customer_code:
        return Response('customer_code is required', status=400, mimetype='text/plain')
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    salesman_code = request.args.get('salesman_code', '').strip()
    try:
        items = _get_outstanding_items_for_pdf_credit(customer_code, date_from=date_from, date_to=date_to, salesman_code=salesman_code)
        if not items:
            return Response('No outstanding invoices for this customer.', status=404, mimetype='text/plain')
        customer_name = _get_customer_name(customer_code)
        location_code = _resolve_location_code()
        location_name = ''
        try:
            info = get_location_info_by_dbkey(None)
            if info:
                location_name = (info.get('locationname') or '').strip()
            if not location_name and location_code:
                info = get_location_info_by_dbkey(str(location_code))
                if info:
                    location_name = (info.get('locationname') or '').strip()
        except Exception:
            pass
        pdf_bytes = _generate_outstanding_invoices_pdf(customer_code=customer_code, customer_name=customer_name, items=items, report_date=datetime.now(), date_from=date_from, date_to=date_to, location_name=location_name)
        if not pdf_bytes:
            return Response('Failed to generate PDF.', status=500, mimetype='text/plain')
        filename = f"outstanding_invoices_credit_{customer_code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        return Response(pdf_bytes, mimetype='application/pdf', headers={'Content-Disposition': f'inline; filename="{filename}"'})
    except Exception as e:
        print(f'[ERROR credit_receipt_outstanding_pdf] {e}')
        import traceback
        traceback.print_exc()
        return Response(f'Error: {e}', status=500, mimetype='text/plain')

@bp.route('/accounts/credit-receipt/update-co-employee', methods=['POST'])
def credit_receipt_update_co_employee():
    """API: Update employeecode, expecteddate and remarks in tblcreditsettlement for selected billnos (flag 'B')."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    data = request.get_json(silent=True) or {}
    employeecode_raw = data.get('employeecode')
    billnos = data.get('billnos') or []
    expecteddate_raw = data.get('expecteddate')
    remarks_raw = (data.get('remarks') or '').strip()
    if not billnos or employeecode_raw is None:
        return jsonify({'success': False, 'error': 'employeecode and billnos are required'}, 400)
    if not expecteddate_raw or not str(expecteddate_raw).strip():
        return jsonify({'success': False, 'error': 'expecteddate is required'}, 400)
    try:
        employeecode = int(employeecode_raw) if employeecode_raw not in (None, '') else 0
    except (ValueError, TypeError):
        employeecode = 0
    billnos_clean = [str(b).strip() for b in billnos if str(b).strip()]
    if not billnos_clean:
        return jsonify({'success': False, 'error': 'No valid bill numbers selected'}, 400)
    settlement_table = _detect_table(['TBLCREDITSETTLEMENT', 'tblcreditsettlement'])
    if not settlement_table:
        return jsonify({'success': False, 'error': 'TBLCREDITSETTLEMENT table not found'}, 500)
    billno_col = _detect_column(settlement_table, ['BILLNO', 'BILL_NO', 'billno'])
    flag_col = _detect_column(settlement_table, ['FLAG', 'flag'])
    emp_col = _detect_column(settlement_table, ['EMPLOYEECODE', 'EMPLOYEE_CODE', 'employeecode'])
    exp_col = _detect_column(settlement_table, ['EXPECTEDDATE', 'EXPECTED_DATE', 'expecteddate', 'expected_date', 'EXPECTED', 'expected'])
    remark_col = _detect_column(settlement_table, ['REMARKS', 'REMARK', 'remarks', 'remark'])
    if not billno_col or not flag_col or (not emp_col):
        return jsonify({'success': False, 'error': 'Required columns not found in TBLCREDITSETTLEMENT'}, 500)
    set_parts = [f'{emp_col} = :emp']
    params = {f'b{i}': b for i, b in enumerate(billnos_clean)}
    params['emp'] = employeecode
    if expecteddate_raw and isinstance(expecteddate_raw, str) and expecteddate_raw.strip() and exp_col:
        expecteddate_str = expecteddate_raw.strip()[:10]
        if len(expecteddate_str) >= 10 and '-' in expecteddate_str:
            try:
                from datetime import datetime as _dt
                d = _dt.strptime(expecteddate_str, '%Y-%m-%d')
                expecteddate_oracle = d.strftime('%d/%b/%Y').upper()
                set_parts.append(f"{exp_col} = TO_DATE(:expecteddate, 'DD/MON/YYYY')")
                params['expecteddate'] = expecteddate_oracle
            except ValueError:
                pass
    if remark_col and remarks_raw:
        set_parts.append(f'{remark_col} = :remarks')
        params['remarks'] = remarks_raw[:500] if remarks_raw else None
    placeholders = ', '.join([f':b{i}' for i in range(len(billnos_clean))])
    update_sql = f"UPDATE {settlement_table} SET {', '.join(set_parts)} WHERE {billno_col} IN ({placeholders}) AND ({flag_col} = 'B' OR {flag_col} IS NULL)"
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(update_sql, params)
                updated = cur.rowcount
            conn.commit()
        return jsonify({'success': True, 'updated': updated, 'message': f'Updated C/O Employee and expected date for {updated} invoice(s).'})
    except Exception as e:
        print(f'[ERROR credit_receipt_update_co_employee] {e}')
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}, 500)

@bp.route('/accounts/credit-receipt/save', methods=['POST'])
def credit_receipt_save():
    """API: Save Credit Receipt - insert tblcreditsettlement (flag R), tblcrsettlement, update outstanding."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    data = request.get_json(silent=True) or {}
    submitted_nonce = (data.get('save_nonce') or '').strip()
    if not verify_consume_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY, submitted_nonce):
        return replay_blocked_response_global()
    try:
        loc_info = get_location_info_by_dbkey(None)
        expected_locationcode = loc_info.get('locationcode') if loc_info else None
    except Exception:
        expected_locationcode = None
    payload_location_code = data.get('location_code')
    if payload_location_code is not None and expected_locationcode is not None:
        try:
            payload_loc = int(payload_location_code) if str(payload_location_code).isdigit() else None
            if payload_loc is not None and payload_loc != int(expected_locationcode):
                return json_response_rotate_global({'success': False, 'error': 'Location code mismatch. Do not save.'}, 400)
        except (ValueError, TypeError):
            return json_response_rotate_global({'success': False, 'error': 'Location code mismatch. Do not save.'}, 400)
    voucherno = (data.get('voucherno') or '').strip()
    paydate_str = (data.get('paydate') or '').strip()
    customer_code = (data.get('customer_code') or '').strip()
    salesman_code = (data.get('salesman_code') or '').strip()
    remark = (data.get('remark') or '').strip()
    raw_items = data.get('items') or []
    if not voucherno or not paydate_str:
        return json_response_rotate_global({'success': False, 'error': 'Please Click New Button'}, 400)
    if not salesman_code:
        return json_response_rotate_global({'success': False, 'error': 'Please select a salesman'}, 400)
    original_voucherno = voucherno
    if _voucherno_exists_credit(voucherno):
        voucherno = _get_next_voucherno_credit()
        print(f'[INFO credit_receipt_save] Voucher number {original_voucherno} already exists, using {voucherno} instead')
    items = []
    for it in raw_items:
        billno = (it.get('billno') or '').strip()
        amount = float(it.get('amount') or it.get('payamount') or 0)
        if not billno or amount == 0:
            continue
        items.append({'billno': billno, 'payamount': amount, 'salesmancode': (it.get('salesmancode') or '').strip()})
    if not items:
        return json_response_rotate_global({'success': False, 'error': 'Please Check Data'}, 400)
    if not remark:
        remark = 'Pending Amount'
    try:
        pay_date = datetime.strptime(paydate_str[:10], '%Y-%m-%d')
    except (ValueError, TypeError):
        return json_response_rotate_global({'success': False, 'error': 'Invalid payment date'}, 400)
    try:
        location_code = _resolve_location_code()
        puser = session.get('user', '')
        meta = {'voucherno': voucherno, 'paydate': pay_date, 'locationcode': location_code, 'remark': remark, 'puser': puser, 'salesmancode': salesman_code}
        process_payments_credit(customer_code, items, meta)
        response_data = {'success': True, 'message': 'Receipt saved.', 'receipt_no': voucherno}
        if voucherno != original_voucherno:
            response_data['voucherno_changed'] = True
            response_data['original_voucherno'] = original_voucherno
            response_data['message'] = f'Receipt saved. Voucher number changed from {original_voucherno} to {voucherno} (original already exists).'
        try:
            items_with_dates = items.copy()
            customer_name = _get_customer_name(customer_code)
            salesman_name = ''
            location_name = ''
            try:
                si = _get_salesman_info(salesman_code)
                if si:
                    salesman_name = (si.get('salesmanname') or '').strip()
            except Exception:
                pass
            try:
                loc_info = get_location_info_by_dbkey(None)
                if loc_info:
                    location_name = (loc_info.get('locationname') or '').strip()
            except Exception:
                pass
            pdf_data = None
            pdf_error = None
            try:
                if REPORTLAB_AVAILABLE and items_with_dates:
                    pdf_data = _generate_cash_receipt_pdf(voucherno=voucherno, customer_code=customer_code, customer_name=customer_name, items=items_with_dates, pay_date=pay_date, salesman_code=salesman_code, salesman_name=salesman_name, remark=remark, location_code=location_code, location_name=location_name, user_name=puser, pdf_title='CREDIT RECEIPT', include_negative_amounts=True)
                    if pdf_data:
                        import base64
                        response_data['pdf_base64'] = base64.b64encode(pdf_data).decode('utf-8')
                        response_data['pdf_filename'] = f"credit_receipt_{voucherno}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            except Exception as e:
                pdf_error = str(e)
                response_data['pdf_error'] = pdf_error
        except Exception:
            pass
        return json_response_rotate_global(response_data)
    except Exception as e:
        print(f'[ERROR credit_receipt_save] {e}')
        import traceback
        traceback.print_exc()
        return json_response_rotate_global({'success': False, 'error': str(e)}, 500)

@bp.route('/accounts/credit-receipt/temp-settlement')
def credit_receipt_temp_settlement():
    """Credit temp settlement detail: tblcrsettlement WHERE flag = 'R'."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    receipt_no = request.args.get('receipt_no', '').strip() or None
    customer_code = request.args.get('customer_code', '').strip() or None
    rows = _get_temp_cr_settlement_receipt_list(receipt_no=receipt_no, customer_code=customer_code)
    return render_template('temporary_collection/temp_settlement_receipt_list.html', rows=rows, receipt_no=receipt_no, customer_code=customer_code, is_credit=True)

@bp.route('/accounts/credit-receipt/temp-settlement/reset', methods=['POST'])
def credit_receipt_temp_settlement_reset():
    """Reset (revise) Credit Receipt: archive to REVISE tables, reverse on tblcreditsettlement, delete from tblcrsettlement and tblcreditsettlement."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    data = request.get_json(silent=True) or {}
    receipt_no = str(data.get('receipt_no') or '').strip()
    customer_code = str(data.get('customer_code') or '').strip()
    password = str(data.get('password') or '').strip()
    if password != RESET_RECEIPT_PASSWORD:
        return jsonify({'success': False, 'error': 'Invalid password'}, 400)
    if not receipt_no or not customer_code:
        return jsonify({'success': False, 'error': 'Please Check Voucher No'}, 400)
    location_code = _resolve_location_code()
    current_user = session.get('user', '')
    remark_revise = f'REVISED RECEIPTNO :{receipt_no}'
    settlement_table = _detect_table(['TBLCREDITSETTLEMENT', 'tblcreditsettlement'])
    temp_table = _detect_table(['TBLCRSETTLEMENT', 'tblcrsettlement'])
    settle_revise_table = _detect_table(['TBLCREDITSETTLEMENTREVISE', 'tblcreditsettlementrevise'])
    temp_revise_table = _detect_table(['TBLCRSETTLEMENTREVISE', 'tblcrsettlementrevise'])
    if not settlement_table or not temp_table:
        return jsonify({'success': False, 'error': 'Required tables not found'}, 500)
    receipt_no_param = int(receipt_no) if receipt_no.isdigit() else receipt_no
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                flag_col = _detect_column(settlement_table, ['FLAG', 'flag'])
                pendingno_col = _detect_column(settlement_table, ['PENDINGNO', 'PENDING_NO', 'pendingno'])
                billno_col = _detect_column(settlement_table, ['BILLNO', 'BILL_NO', 'billno'])
                billdate_col = _detect_column(settlement_table, ['BILLDATE', 'BILL_DATE', 'billdate'])
                billamount_col = _detect_column(settlement_table, ['BILLAMOUNT', 'BILL_AMOUNT', 'billamount'])
                cust_col = _detect_column(settlement_table, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'customercode'])
                if not all([flag_col, pendingno_col, cust_col]):
                    return jsonify({'success': False, 'error': 'Settlement columns not found'}, 500)
                summary_query = f"SELECT {pendingno_col}, {billno_col}, {billdate_col}, {billamount_col} FROM {settlement_table} WHERE {pendingno_col} = :rn AND {cust_col} = :cc AND {flag_col} = 'R'"
                cur.execute(summary_query, {'rn': receipt_no_param, 'cc': customer_code})
                summary_row = cur.fetchone()
                if not summary_row:
                    return jsonify({'success': False, 'error': 'Receipt not found'}, 404)
                summary_billdate, summary_billamount = (summary_row[2], summary_row[3])
                billdate_oracle = summary_billdate.strftime('%d/%b/%Y').upper() if summary_billdate and hasattr(summary_billdate, 'strftime') else datetime.now().strftime('%d/%b/%Y').upper()
                temp_pendingno_col = _detect_column(temp_table, ['PENDINGNO', 'PENDING_NO', 'pendingno'])
                temp_againstno_col = _detect_column(temp_table, ['AGAINSTNO', 'AGAINST_NO', 'againstno'])
                temp_paidamt_col = _detect_column(temp_table, ['PAIDAMOUNT', 'PAID_AMOUNT', 'paidamount'])
                temp_cust_col = _detect_column(temp_table, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'customercode'])
                temp_flag_col = _detect_column(temp_table, ['FLAG', 'flag'])
                settle_paidamt = _detect_column(settlement_table, ['PAIDAMOUNT', 'PAID_AMOUNT', 'paidamount'])
                settle_balance = _detect_column(settlement_table, ['BALANCE', 'balance'])
                settle_billno_col = _detect_column(settlement_table, ['BILLNO', 'BILL_NO', 'billno'])
                settle_status = _detect_column(settlement_table, ['STATUS', 'status'])
                settle_pflag = _detect_column(settlement_table, ['PFLAG', 'P_FLAG', 'pflag'])
                if not all([temp_pendingno_col, temp_againstno_col, temp_cust_col, temp_flag_col]):
                    return jsonify({'success': False, 'error': 'Temp settlement columns not found'}, 500)
                cur.execute(f"SELECT t.{temp_againstno_col} AS againstno, NVL(t.{temp_paidamt_col}, 0) AS paidamount FROM {temp_table} t WHERE t.{temp_pendingno_col} = :rn AND t.{temp_cust_col} = :cc AND t.{temp_flag_col} = 'R'", {'rn': receipt_no_param, 'cc': customer_code})
                temp_rows = cur.fetchall()
                if not temp_rows:
                    return jsonify({'success': False, 'error': 'Please Check Data'}, 400)
                if settle_paidamt and settle_balance and settle_billno_col and cust_col and flag_col:
                    set_parts = [f'{settle_paidamt} = {settle_paidamt} - :amt', f'{settle_balance} = {settle_balance} + :amt']
                    if settle_status:
                        set_parts.append(f"{settle_status} = 'PENDING'")
                    if settle_pflag:
                        set_parts.append(f"{settle_pflag} = 'N'")
                    reverse_sql = f"UPDATE {settlement_table} SET {', '.join(set_parts)} WHERE {settle_billno_col} = :billno AND {cust_col} = :cc AND {flag_col} = 'B'"
                    for row in temp_rows:
                        cur.execute(reverse_sql, {'amt': float(row[1]), 'billno': row[0], 'cc': customer_code})
                cur.execute(f'DELETE FROM {temp_table} WHERE {temp_pendingno_col} = :rn AND {temp_cust_col} = :cc', {'rn': receipt_no_param, 'cc': customer_code})
                cur.execute(f"DELETE FROM {settlement_table} WHERE {pendingno_col} = :rn AND {cust_col} = :cc AND {flag_col} = 'R'", {'rn': receipt_no_param, 'cc': customer_code})
                conn.commit()
        return jsonify({'success': True, 'message': f'Revised Receipt No {receipt_no}'})
    except Exception as e:
        print(f'[ERROR credit_receipt_temp_settlement_reset] {e}')
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}, 500)

@bp.route('/accounts/temporary-collection/list')
def temporary_collection_list():
    """Temporary Collection List Page"""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    if not date_from and (not date_to):
        today = datetime.now().strftime('%Y-%m-%d')
        return redirect(url_for('temporary_collection.temporary_collection_list', date_from=today, date_to=today))
    collections_list = _get_temporary_collections_list(date_from=date_from, date_to=date_to)
    for _rr in collections_list:
        _rr['list_tab'] = _tcl_list_tab_from_aggregate(_rr.get('min_status'), _rr.get('sum_line_balance'))
    return render_template('temporary_collection/temporary_collection_list.html', collections=collections_list, date_from=date_from, date_to=date_to)

@bp.route('/accounts/temporary-collection/activity-log')
def temporary_collection_activity_log():
    """Audit report for Temporary Collection saves (NEXA_MASTER_ACTIVITY_LOG, entity temporary_collection)."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    export_raw = (request.args.get('export') or '').strip().lower()
    try:
        limit = int(request.args.get('limit') or 800)
    except (TypeError, ValueError):
        limit = 800
    limit = max(50, min(limit, 2000))
    rows = fetch_master_activity_log(entity_exact=_TEMPORARY_COLLECTION_LOG_ENTITY, limit=limit)
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
        fn = f"temporary_collection_activity_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        return Response(buf.getvalue(), mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename="{fn}"'})
    return render_template('temporary_collection/temporary_collection_activity_log.html', rows=rows, limit=limit)

def _tcl_list_tab_from_aggregate(min_status_val: Any, _sum_line_balance_val: Any) -> str:
    """Map aggregates (per salesman + bill date) on ONLINE_TEMPORARY_COLLECTIONS lines to UI tab key.

    Line STATUS meanings in ONLINE_TEMPORARY_COLLECTIONS (typically numeric): 0=pending, 1=completed, 2=rejected.

    Tabs:
    - pending: MIN(status)==0 — at least one line still awaiting collection / not finalized.
    - rejected: MIN(status)==2 — no open pending (0); all lines rejected (assuming values are 0,1,2 only).
    - completed: MIN(status)==1 — all lines completed (single Completed tab; ``sum_line_balance`` unused).
    """
    try:
        ms = int(min_status_val) if min_status_val is not None else 0
    except (ValueError, TypeError):
        ms = 0
    if ms == 0:
        return 'pending'
    if ms >= 2:
        return 'rejected'
    return 'completed'

def _tcl_list_row_to_json(r: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize one row from _get_temporary_collections_list for JSON (list auto-refresh)."""
    ms = int(r.get('min_status') or 0)
    sm_code = str(r.get('salesmancode') or '').strip()
    sn = str(r.get('salesmanname') or '').strip() or '-'
    bill_raw = r.get('billdate')
    bill_iso = _bill_date_collection_value_to_iso(bill_raw) or ''
    if bill_raw is None:
        bill_disp = '-'
    elif isinstance(bill_raw, datetime):
        bill_disp = bill_raw.strftime('%d/%b/%Y').upper()
    elif isinstance(bill_raw, str):
        bds = bill_raw.strip()
        bill_disp = bds if bds else '-'
    else:
        try:
            bill_disp = bill_raw.strftime('%d/%b/%Y').upper()
        except Exception:
            bill_disp = str(bill_raw).strip() or '-'
    try:
        tot = float(r.get('totalcollection') or 0)
    except (TypeError, ValueError):
        tot = 0.0
    try:
        fin_raw = r.get('totalfinalcollection')
        fin = float(fin_raw) if fin_raw is not None else tot
    except (TypeError, ValueError):
        fin = tot
    try:
        sb = float(r.get('sum_line_balance')) if r.get('sum_line_balance') is not None else 0.0
    except (TypeError, ValueError):
        sb = 0.0
    try:
        xmax = int(r.get('max_status') if r.get('max_status') is not None else ms)
    except (ValueError, TypeError):
        xmax = ms
    lt = _tcl_list_tab_from_aggregate(ms, sb)
    return {'salesman_code': sm_code, 'salesman_name': sn, 'bill_date_iso': bill_iso, 'bill_date_display': bill_disp, 'bill_no': '', 'total_collection': round(tot, 2), 'final_collection': round(fin, 2), 'min_status': ms, 'max_status': xmax, 'sum_line_balance': round(sb, 2), 'list_tab': lt}

def _cash_credit_receipt_row_to_json(r: Dict[str, Any]) -> Dict[str, Any]:
    """JSON shape for cash/credit receipt list (matches receipt_list templates + client rebuild)."""
    billno_raw = r.get('billno')
    billno = str(billno_raw).strip() if billno_raw is not None else ''
    pend_raw = r.get('pendingno')
    receipt_no = str(pend_raw).strip() if pend_raw not in (None, '') else billno or ''
    paidate = r.get('paidate')
    billdate = r.get('billdate')
    primary = paidate if paidate is not None else billdate
    date_iso = _bill_date_collection_value_to_iso(primary) or ''
    date_disp = '-'
    if isinstance(primary, datetime):
        date_disp = primary.strftime('%d/%b/%Y').upper()
    elif primary is not None:
        s = str(primary).strip()
        if s:
            di = _bill_date_collection_value_to_iso(primary)
            if di:
                try:
                    date_disp = datetime.strptime(di[:10], '%Y-%m-%d').strftime('%d/%b/%Y').upper()
                except Exception:
                    date_disp = s
            else:
                date_disp = s
    try:
        amt = float(r.get('amount') or 0)
    except (TypeError, ValueError):
        amt = 0.0
    cust = str(r.get('customercode') or '').strip()
    nm = str(r.get('customername') or '').strip() or '-'
    return {'billno': billno or None, 'pendingno': str(pend_raw) if pend_raw not in (None, '') else None, 'receipt_no': receipt_no, 'display_date': date_disp, 'sort_date_iso': date_iso, 'customercode': cust, 'customername': nm, 'amount': round(amt, 2)}

@bp.route('/accounts/cash-receipt/api/list-rows', methods=['GET'])
def api_cash_receipt_list_rows():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    has_filter = 'date_from' in request.args or 'date_to' in request.args
    if has_filter and (date_from or date_to):
        receipts = _get_cash_receipt_list(date_from=date_from, date_to=date_to, limit=10000)
    else:
        receipts = _get_cash_receipt_list(limit=10000)
    rows = [_cash_credit_receipt_row_to_json(r) for r in receipts or []]
    return jsonify({'success': True, 'rows': rows})

@bp.route('/accounts/credit-receipt/api/list-rows', methods=['GET'])
def api_credit_receipt_list_rows():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    has_filter = 'date_from' in request.args or 'date_to' in request.args
    if has_filter and (date_from or date_to):
        receipts = _get_credit_receipt_list(date_from=date_from, date_to=date_to, limit=10000)
    else:
        receipts = _get_credit_receipt_list(limit=10000)
    rows = [_cash_credit_receipt_row_to_json(r) for r in receipts or []]
    return jsonify({'success': True, 'rows': rows})

@bp.route('/accounts/temporary-collection/api/list-rows', methods=['GET'])
def api_temporary_collection_list_rows():
    """JSON rows for the same list as Temporary Collection List (for in-page refresh without full reload)."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    cols = _get_temporary_collections_list(date_from=date_from, date_to=date_to)
    rows = [_tcl_list_row_to_json(r) for r in cols]
    return jsonify({'success': True, 'rows': rows})

@bp.route('/accounts/temporary-collection/print-pdf', methods=['GET'])
def temporary_collection_list_print_pdf():
    """API: Generate Collection Summary PDF for a list row (salesman + date + status). Returns JSON with pdf_base64 and pdf_filename."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    salesman_code = request.args.get('salesman_code', '').strip()
    billdate = request.args.get('billdate', '').strip()
    status_str = request.args.get('status', '0').strip()
    if not salesman_code:
        return jsonify({'success': False, 'error': 'Salesman code is required'}, 400)
    try:
        status_filter = int(status_str) if status_str in ('0', '1') else 0
    except ValueError:
        status_filter = 0
    date_from = date_to = billdate if billdate else None
    use_date_range = bool(billdate)
    invoices = _get_invoice_details_from_online(salesman_code, date_from=date_from, date_to=date_to, use_date_range=use_date_range, status_filter=status_filter)
    if not invoices:
        return jsonify({'success': False, 'error': 'No invoice data found for this salesman and date'}, 400)
    try:
        customer_groups = defaultdict(list)
        customer_totals = defaultdict(float)
        collection_items = []
        for inv in invoices:
            cust_code = str(inv.get('customercode') or '').strip()
            amount = float(inv.get('finalcollection') or inv.get('collection') or 0)
            if amount <= 0:
                continue
            billno = inv.get('billno') or ''
            billdate_raw = inv.get('billdate') or billdate
            outstanding = float(inv.get('outstanding') or inv.get('collection') or 0)
            item = {'invoice_no': billno, 'customer_code': cust_code, 'customer_name': inv.get('customername') or cust_code, 'amount': amount, 'id': inv.get('id'), 'salesman_code': inv.get('salesmancode') or salesman_code, 'bill_date': billdate_raw, 'bill_amount': outstanding or amount, 'billamount': outstanding or amount}
            collection_items.append(item)
            customer_groups[cust_code].append({'invoice_no': billno, 'amount': amount, 'bill_date': billdate_raw, 'bill_amount': outstanding or amount, 'billamount': outstanding or amount, 'customer_name': inv.get('customername') or cust_code})
            customer_totals[cust_code] += amount
        voucher_numbers = {c: 'N/A' for c in customer_groups}
        transaction_date = billdate[:10] if billdate and len(billdate) >= 10 else billdate or ''
        if not transaction_date:
            try:
                transaction_date = _get_transaction_date(_resolve_location_code()) or ''
            except Exception:
                transaction_date = ''
        salesman_name = ''
        try:
            sm_info = _get_salesman_info(salesman_code)
            if sm_info:
                salesman_name = (sm_info.get('salesmanname') or '').strip()
        except Exception:
            pass
        location_code = _resolve_location_code()
        location_name = ''
        try:
            loc_info = get_location_info_by_dbkey(None)
            if loc_info:
                location_name = (loc_info.get('locationname') or '').strip()
        except Exception:
            pass
        if not location_name:
            location_name = str(location_code)
        user_name = session.get('user', '')
        status_label = 'Completed' if status_filter == 1 else 'Pending'
        pdf_data = _generate_collection_pdf(collection_items=collection_items, customer_groups=dict(customer_groups), customer_totals=dict(customer_totals), voucher_numbers=voucher_numbers, transaction_date=transaction_date, salesman_code=salesman_code, salesman_name=salesman_name, remark='Pending Amount', location_code=location_code, user_name=user_name, location_name=location_name, status_label=status_label)
        if not pdf_data:
            return jsonify({'success': False, 'error': 'Failed to generate PDF'}, 500)
        return jsonify({'success': True, 'pdf_base64': base64.b64encode(pdf_data).decode('utf-8'), 'pdf_filename': f"temporary_collection_{salesman_code}_{transaction_date.replace('-', '') or 'report'}.pdf"})
    except Exception as e:
        import traceback
        print(f'[ERROR temporary_collection_list_print_pdf] {e}')
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}, 500)

@bp.route('/accounts/salesman-receipt')
def salesman_receipt():
    """Salesman Receipt page - voucher entry for salesman settlement (TBLSALESMANSETTLEMENT)."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    transaction_date = _get_transaction_date()
    next_voucherno = _get_next_salesman_voucher_no()
    payment_reasons = _get_payment_reasons()
    return render_template('temporary_collection/salesman_receipt.html', transaction_date=transaction_date, next_voucherno=next_voucherno, payment_reasons=payment_reasons)

@bp.route('/accounts/salesman-receipt/api/transaction-date', methods=['GET'])
def api_salesman_receipt_transaction_date():
    if not session.get('user'):
        return jsonify({'error': 'Not authenticated'}, 401)
    try:
        transaction_date = _get_transaction_date()
        return jsonify({'success': True, 'transaction_date': transaction_date})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}, 500)

@bp.route('/accounts/salesman-receipt/api/next-voucherno', methods=['GET'])
def api_salesman_receipt_next_voucherno():
    if not session.get('user'):
        return jsonify({'error': 'Not authenticated'}, 401)
    try:
        nextno = _get_next_salesman_voucher_no()
        return jsonify({'success': True, 'voucherno': nextno})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}, 500)

@bp.route('/accounts/salesman-receipt/api/salesman', methods=['GET'])
def api_salesman_receipt_salesman():
    """Get salesman receipt info (name, outstanding, morepaid, unadjusted)."""
    if not session.get('user'):
        return jsonify({'error': 'Not authenticated'}, 401)
    salesman_code = request.args.get('code', '').strip()
    if not salesman_code:
        return jsonify({'success': False, 'error': 'Salesman code required'}, 400)
    info = _get_salesman_receipt_info(salesman_code)
    if not info:
        return jsonify({'success': False, 'error': 'Salesman not found'}, 404)
    return jsonify({'success': True, 'salesman': info})

@bp.route('/accounts/salesman-receipt/api/payment-reasons', methods=['GET'])
def api_salesman_receipt_payment_reasons():
    if not session.get('user'):
        return jsonify({'error': 'Not authenticated'}, 401)
    reasons = _get_payment_reasons()
    return jsonify({'success': True, 'payment_reasons': reasons})

@bp.route('/accounts/salesman-receipt/api/settlements', methods=['GET'])
def api_salesman_receipt_settlements():
    if not session.get('user'):
        return jsonify({'error': 'Not authenticated'}, 401)
    salesman_code = request.args.get('salesman_code', '').strip()
    if not salesman_code:
        return jsonify({'success': False, 'error': 'Salesman code required'}, 400)
    rows = _get_salesman_settlements_list(salesman_code)
    return jsonify({'success': True, 'settlements': rows})

@bp.route('/accounts/salesman-receipt/api/save', methods=['POST'])
def api_salesman_receipt_save():
    if not session.get('user'):
        return jsonify({'error': 'Not authenticated'}, 401)
    data = request.get_json(silent=True) or {}
    submitted_nonce = (data.get('save_nonce') or '').strip()
    if not verify_consume_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY, submitted_nonce):
        return replay_blocked_response_global()
    voucherno = data.get('voucherno')
    try:
        voucherno = int(voucherno)
    except (TypeError, ValueError):
        return json_response_rotate_global({'success': False, 'error': 'Invalid voucher number'}, 400)
    voucherdate = (data.get('voucherdate') or '').strip()
    salesmancode = (data.get('salesman_code') or '').strip()
    typecode = data.get('typecode')
    try:
        typecode = int(typecode) if typecode not in (None, '') else 0
    except (TypeError, ValueError):
        typecode = 0
    typename = (data.get('typename') or '').strip()
    amount = float(data.get('amount') or 0)
    remark = (data.get('remark') or '').strip()
    previous_outstanding = float(data.get('previous_outstanding') or 0)
    if not voucherdate:
        return json_response_rotate_global({'success': False, 'error': 'Please enter voucher date'}, 400)
    if not salesmancode or not typename or (not remark):
        return json_response_rotate_global({'success': False, 'error': 'Please check data (salesman, type, amount, remark)'}, 400)
    if amount <= 0 and typecode in (2, 3):
        return json_response_rotate_global({'success': False, 'error': 'Please check amount'}, 400)
    err = _save_salesman_receipt(voucherno=voucherno, voucherdate=voucherdate, salesmancode=salesmancode, typecode=typecode, typename=typename, amount=amount, remark=remark, previous_outstanding=previous_outstanding)
    if err:
        return json_response_rotate_global({'success': False, 'error': err}, 400)
    nextno = _get_next_salesman_voucher_no()
    pdf_base64 = None
    try:
        location_code = _resolve_location_code()
        location_name = ''
        try:
            loc_info = get_location_info_by_dbkey(None)
            if loc_info:
                location_name = (loc_info.get('locationname') or '').strip()
        except Exception:
            pass
        if not location_name:
            location_name = str(location_code)
        salesman_info = _get_salesman_info(salesmancode)
        salesman_name = (salesman_info.get('salesmanname') or '').strip() if salesman_info else ''
        pdf_bytes = _generate_salesman_receipt_pdf(location_code=location_code, location_name=location_name, receiptno=str(voucherno), receiptdate=voucherdate, salesmancode=salesmancode, salesman_name=salesman_name, amount=amount, reason=typename, remarks=remark)
        if pdf_bytes:
            pdf_base64 = base64.b64encode(pdf_bytes).decode('ascii')
    except Exception as pdf_err:
        print(f'[ERROR api_salesman_receipt_save] PDF generation: {pdf_err}')
    return json_response_rotate_global({'success': True, 'next_voucherno': nextno, 'pdf_base64': pdf_base64})

@bp.route('/accounts/temporary-collection')
def temporary_collection():
    """Temporary Collection page"""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    salesman_code = request.args.get('salesman_code', '').strip()
    location_code = _resolve_location_code()
    transaction_date = _get_transaction_date(location_code)
    return render_template('temporary_collection/temporary_collection.html', transaction_date=transaction_date, location_code=location_code, salesman_code=salesman_code)

@bp.route('/accounts/temporary-collection/api/next-voucherno', methods=['GET'])
def api_next_voucherno():
    """API: Get next voucher number"""
    if not session.get('user'):
        return jsonify({'error': 'Not authenticated'}, 401)
    try:
        voucherno = _get_next_pendingno()
        return jsonify({'success': True, 'voucherno': voucherno})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}, 500)

@bp.route('/accounts/temporary-collection/api/transaction-date', methods=['GET'])
def api_transaction_date():
    """API: Get transaction date"""
    if not session.get('user'):
        return jsonify({'error': 'Not authenticated'}, 401)
    try:
        location_code = _resolve_location_code()
        transaction_date = _get_transaction_date(location_code)
        return jsonify({'success': True, 'transaction_date': transaction_date})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}, 500)

@bp.route('/accounts/temporary-collection/api/salesman', methods=['GET'])
def api_salesman():
    """API: Get salesman information"""
    if not session.get('user'):
        return jsonify({'error': 'Not authenticated'}, 401)
    salesman_code = request.args.get('salesman_code', '').strip()
    if not salesman_code:
        return jsonify({'success': False, 'error': 'Salesman code required'}, 400)
    try:
        salesman_info = _get_salesman_info(salesman_code)
        if not salesman_info:
            return jsonify({'success': False, 'error': 'Salesman not found'}, 404)
        return jsonify({'success': True, 'salesman': salesman_info})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}, 500)

@bp.route('/accounts/temporary-collection/api/invoice-details', methods=['GET'])
def api_invoice_details():
    """API: Get invoice details from online_temporary_collections"""
    if not session.get('user'):
        return jsonify({'error': 'Not authenticated'}, 401)
    salesman_code = request.args.get('salesman_code', '').strip()
    date_from = request.args.get('date_from', '').strip() or None
    date_to = request.args.get('date_to', '').strip() or None
    use_date_range = request.args.get('use_date_range', 'false').lower() == 'true'
    bill_date_q = request.args.get('bill_date', '').strip()
    exact_bill: Optional[str] = None
    if bill_date_q and len(bill_date_q) >= 10:
        try:
            datetime.strptime(bill_date_q.strip()[:10], '%Y-%m-%d')
            exact_bill = bill_date_q.strip()[:10]
        except Exception:
            exact_bill = None
    line_raw = (request.args.get('line_status') or request.args.get('online_status') or '').strip()
    line_status_sel: Optional[int] = None
    if line_raw in ('0', '1', '2'):
        line_status_sel = int(line_raw)
    if line_status_sel is not None:
        all_statuses = False
        status_kw: Optional[int] = line_status_sel
    else:
        all_statuses = bool(exact_bill)
        status_kw = None
    if not salesman_code:
        return jsonify({'success': False, 'error': 'Salesman code required'}, 400)
    try:
        invoices = _get_invoice_details_from_online(salesman_code, date_from, date_to, use_date_range, status_filter=status_kw, exact_bill_date=exact_bill, all_statuses=all_statuses)
        print(f'[DEBUG api_invoice_details] Found {len(invoices)} invoices for salesman {salesman_code}')
        return jsonify({'success': True, 'invoices': invoices})
    except Exception as e:
        import traceback
        print(f'[ERROR api_invoice_details] Error: {e}')
        print(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}, 500)

@bp.route('/accounts/temporary-collection/api/salesman-list', methods=['GET'])
def api_salesman_list():
    """API: Get list of salesmen"""
    if not session.get('user'):
        return jsonify({'error': 'Not authenticated'}, 401)
    try:
        salesman_table = _detect_table(['SALESMAN', 'salesman', 'SALESMEN', 'salesmen'])
        if not salesman_table:
            return jsonify({'success': False, 'error': 'Salesman table not found'}, 500)
        salesmancode_col = _detect_column(salesman_table, ['SALESMANCODE', 'salesmancode', 'CODE', 'code'])
        salesmanname_col = _detect_column(salesman_table, ['SALESMANNAME', 'salesmanname', 'NAME', 'name'])
        locationcode_col = _detect_column(salesman_table, ['LOCATIONCODE', 'LOCATION_CODE', 'LOC_CODE', 'LOCCODE'])
        if not salesmancode_col:
            return jsonify({'success': False, 'error': 'Salesman code column not found'}, 500)
        location_code = _resolve_location_code()
        where_clause = ''
        params = {}
        if locationcode_col:
            where_clause = f'WHERE {locationcode_col} = :location_code'
            params['location_code'] = location_code
        select_cols = [f'{salesmancode_col} AS code', f'{salesmanname_col} AS name' if salesmanname_col else 'NULL AS name']
        query = f"\n            SELECT {', '.join(select_cols)}\n            FROM {salesman_table}\n            {where_clause}\n            ORDER BY {(salesmanname_col if salesmanname_col else salesmancode_col)}\n        "
        _, rows = _fetch_rows(query, params)
        return jsonify({'success': True, 'salesmen': rows})
    except Exception as e:
        import traceback
        print(f'[ERROR api_salesman_list] {e}')
        print(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}, 500)

@bp.route('/accounts/temporary-collection/api/customer-summary', methods=['GET'])
def api_customer_summary():
    """API: Get customer summary"""
    if not session.get('user'):
        return jsonify({'error': 'Not authenticated'}, 401)
    salesman_code = request.args.get('salesman_code', '').strip()
    date_from = request.args.get('date_from', '').strip() or None
    date_to = request.args.get('date_to', '').strip() or None
    use_date_range = request.args.get('use_date_range', 'false').lower() == 'true'
    if not salesman_code:
        return jsonify({'success': False, 'error': 'Salesman code required'}, 400)
    try:
        summary = _get_customer_summary(salesman_code, date_from, date_to, use_date_range)
        return jsonify({'success': True, 'summary': summary})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}, 500)

def _bill_date_collection_value_to_iso(val: Any) -> Optional[str]:
    """Normalize bill date from grouped list rows to YYYY-MM-DD."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.strftime('%Y-%m-%d')
    if isinstance(val, str):
        vs = val.strip()
        if len(vs) >= 10 and vs[4] == '-':
            return vs[:10]
        try:
            return datetime.strptime(vs[:10], '%d/%m/%Y').strftime('%Y-%m-%d')
        except Exception:
            pass
    return None

def _online_rows_to_bulk_collection_items(invoices: List[Dict[str, Any]], salesman_code: str, transaction_iso_hint: str) -> List[Dict[str, Any]]:
    """Same eligibility rules as the collection screen Save (positive amount, skip over-collected rows)."""
    out: List[Dict[str, Any]] = []
    for item in invoices or []:
        try:
            coll = float(item.get('finalcollection') if item.get('finalcollection') is not None else item.get('collection') or 0)
        except (TypeError, ValueError):
            coll = 0.0
        try:
            balance = float(item.get('balance') or 0)
        except (TypeError, ValueError):
            balance = 0.0
        if coll > 0 and balance < coll:
            continue
        if coll <= 0:
            continue
        bn = str(item.get('billno') or '').strip()
        cc = str(item.get('customercode') or '').strip()
        if not bn or not cc:
            continue
        bid = str(item.get('id') or '').strip()
        try:
            outst = float(item.get('outstanding') if item.get('outstanding') not in (None, '') else coll)
        except (TypeError, ValueError):
            outst = coll
        out.append({'invoice_no': bn, 'customer_code': cc, 'customer_name': item.get('customername') or '', 'amount': coll, 'id': bid, 'salesman_code': str(item.get('salesmancode') or salesman_code).strip(), 'bill_date': item.get('billdate'), 'bill_amount': outst})
    return out

def _temporary_collection_save_run(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Execute temporary-collection save POST payload; returns (body dict, HTTP status). No nonce rotation."""
    transaction_date = data.get('transaction_date', '').strip()
    salesman_code = data.get('salesman_code', '').strip()
    remark = data.get('remark', 'Pending Amount').strip() or 'Pending Amount'
    collection_items = data.get('collection_items', [])
    if not transaction_date or not salesman_code:
        return ({'success': False, 'error': 'Date and salesman code are required'}, 400)
    if not collection_items:
        return ({'success': False, 'error': 'No collection items provided'}, 400)
    location_code = _resolve_location_code()
    current_user = session.get('user', '')
    try:
        settlement_table = _detect_table(['TBLSETTLEMENT', 'tblsettlement'])
        temp_settlement_table = _detect_table(['TBLTEMPSETTLEMENT', 'tbltempsettlement'])
        online_table = _detect_table(['ONLINE_TEMPORARY_COLLECTIONS', 'online_temporary_collections', 'ONLINETEMPORARYCOLLECTIONS'])
        if not settlement_table or not temp_settlement_table:
            return ({'success': False, 'error': 'Required tables not found'}, 500)
        try:
            if '/' in transaction_date:
                date_parts = transaction_date.split('/')
                if len(date_parts) == 3:
                    month = date_parts[1][:3].upper()
                    oracle_date = f'{date_parts[0]}/{month}/{date_parts[2]}'
                else:
                    oracle_date = transaction_date
            elif '-' in transaction_date:
                dt = datetime.strptime(transaction_date, '%Y-%m-%d')
                oracle_date = dt.strftime('%d/%b/%Y').upper()
            else:
                oracle_date = transaction_date
        except Exception as e:
            print(f'[DEBUG api_save] Date conversion error: {e}, using original: {transaction_date}')
            oracle_date = transaction_date
        customer_groups = defaultdict(list)
        customer_totals = defaultdict(float)
        invoice_data_map = {}
        invoice_numbers = []
        for item in collection_items:
            invoice_no = str(item.get('invoice_no', '')).strip()
            customer_code = str(item.get('customer_code', '')).strip()
            amount = float(item.get('amount', 0))
            if not invoice_no or not customer_code or amount <= 0:
                continue
            invoice_numbers.append(invoice_no)
            item_with_data = item.copy()
            customer_groups[customer_code].append(item_with_data)
            customer_totals[customer_code] += amount
        if invoice_numbers and settlement_table:
            with _get_connection() as check_conn:
                with check_conn.cursor() as check_cur:
                    check_billno_col = _detect_column(settlement_table, ['BILLNO', 'BILL_NO'])
                    check_flag_col = _detect_column(settlement_table, ['FLAG', 'flag'])
                    if check_billno_col and check_flag_col:
                        missing_invoices = []
                        for invoice_no in invoice_numbers:
                            try:
                                check_query = f"SELECT COUNT(*) FROM {settlement_table} WHERE {check_billno_col} = :billno AND {check_flag_col} = 'B'"
                                check_cur.execute(check_query, {'billno': invoice_no})
                                count = check_cur.fetchone()[0]
                                if count == 0:
                                    missing_invoices.append(invoice_no)
                            except Exception as e:
                                print(f'[DEBUG api_save] Error checking invoice {invoice_no}: {e}')
                                missing_invoices.append(invoice_no)
                        if missing_invoices:
                            missing_list = ', '.join(missing_invoices)
                            return ({'success': False, 'error': f"The following bill numbers are not found in TBLSETTLEMENT with FLAG='B'. Please make them temporary first: {missing_list}"}, 400)
        fp_shared = _temporary_collection_save_payload_fingerprint(data)
        if not _tc_payload_guard_reserve(fp_shared):
            return ({'success': False, 'error': 'Duplicate save blocked: another session submitted this same collection recently. Refresh and confirm before retrying.', 'duplicate_submit_shared': True}, 409)

        def _run_save_transaction():
            with _get_connection() as conn:
                with conn.cursor() as cur:
                    settlement_cols = _get_table_columns(settlement_table)
                    locationcode_col = _detect_column(settlement_table, ['LOCATIONCODE', 'LOCATION_CODE'])
                    pendingno_col = _detect_column(settlement_table, ['PENDINGNO', 'PENDING_NO'])
                    billno_col = _detect_column(settlement_table, ['BILLNO', 'BILL_NO'])
                    billdate_col = _detect_column(settlement_table, ['BILLDATE', 'BILL_DATE'])
                    billamount_col = _detect_column(settlement_table, ['BILLAMOUNT', 'BILL_AMOUNT'])
                    customercode_col = _detect_column(settlement_table, ['CUSTOMERCODE', 'CUSTOMER_CODE'])
                    remark_col = _detect_column(settlement_table, ['REMARK', 'remark'])
                    flag_col = _detect_column(settlement_table, ['FLAG', 'flag'])
                    onlineflag_col = _detect_column(settlement_table, ['ONLINEFLAG', 'ONLINE_FLAG', 'onlineflag'])
                    paidamount_col = _detect_column(settlement_table, ['PAIDAMOUNT', 'PAID_AMOUNT', 'paidamount'])
                    balance_col = _detect_column(settlement_table, ['BALANCE', 'balance'])
                    paiddate_col = _detect_column(settlement_table, ['PAIDDATE', 'PAID_DATE', 'paiddate'])
                    puser_col = _detect_column(settlement_table, ['PUSER', 'puser', 'P_USER'])
                    voucherno_col = _detect_column(settlement_table, ['VOUCHERNO', 'VOUCHER_NO', 'voucherno'])
                    status_col = _detect_column(settlement_table, ['STATUS', 'status'])
                    pflag_col = _detect_column(settlement_table, ['PFLAG', 'P_FLAG', 'pflag'])
                    settlement_salesmancode_col = _detect_column(settlement_table, ['SALESMANCODE', 'SALESMAN_CODE', 'salesmancode'])
                    sett_createdby = _detect_column(settlement_table, ['CREATEDBY', 'CREATED_BY', 'createdby', 'created_by', 'CREATED_BY_USER', 'created_by_user'])
                    sett_created_at = _detect_column(settlement_table, ['CREATED_AT', 'CREATEDAT', 'created_at', 'createdat'])
                    existing_settlement_cols_upper = [c.upper() for c in settlement_cols] if settlement_cols else []
                    if not sett_createdby and 'CREATEDBY' not in existing_settlement_cols_upper:
                        try:
                            cur.execute(f'ALTER TABLE {settlement_table} ADD CREATEDBY VARCHAR2(50)')
                            sett_createdby = _detect_column(settlement_table, ['CREATEDBY', 'CREATED_BY', 'createdby', 'created_by'])
                        except Exception as e:
                            print(f'[DEBUG api_save] Error creating CREATEDBY column: {e}')
                    if not sett_created_at and 'CREATED_AT' not in existing_settlement_cols_upper:
                        try:
                            cur.execute(f'ALTER TABLE {settlement_table} ADD CREATED_AT DATE')
                            import db as _db
                            if hasattr(_db, '_TABLE_COLUMNS_CACHE') and isinstance(getattr(_db, '_TABLE_COLUMNS_CACHE'), dict):
                                _db._TABLE_COLUMNS_CACHE.pop(settlement_table.upper(), None)
                            sett_created_at = _detect_column(settlement_table, ['CREATED_AT', 'CREATEDAT', 'created_at', 'createdat'])
                        except Exception as e:
                            print(f'[DEBUG api_save] Error creating CREATED_AT column: {e}')
                    temp_locationcode_col = _detect_column(temp_settlement_table, ['LOCATIONCODE', 'LOCATION_CODE'])
                    temp_pendingno_col = _detect_column(temp_settlement_table, ['PENDINGNO', 'PENDING_NO'])
                    temp_customercode_col = _detect_column(temp_settlement_table, ['CUSTOMERCODE', 'CUSTOMER_CODE'])
                    temp_status_col = _detect_column(temp_settlement_table, ['STATUS', 'status'])
                    temp_paidamount_col = _detect_column(temp_settlement_table, ['PAIDAMOUNT', 'PAID_AMOUNT', 'paidamount'])
                    temp_againstno_col = _detect_column(temp_settlement_table, ['AGAINSTNO', 'AGAINST_NO', 'againstno'])
                    temp_paiddate_col = _detect_column(temp_settlement_table, ['PAIDDATE', 'PAID_DATE', 'paiddate'])
                    temp_flag_col = _detect_column(temp_settlement_table, ['FLAG', 'flag'])
                    temp_puser_col = _detect_column(temp_settlement_table, ['PUSER', 'puser', 'P_USER'])
                    temp_remarks_col = _detect_column(temp_settlement_table, ['REMARKS', 'remarks', 'REMARK', 'remark'])
                    temp_salesmancode_col = _detect_column(temp_settlement_table, ['SALESMANCODE', 'SALESMAN_CODE', 'salesmancode'])
                    temp_billamount_col = _detect_column(temp_settlement_table, ['BILLAMOUNT', 'BILL_AMOUNT', 'billamount'])
                    temp_version_col = _detect_column(temp_settlement_table, ['VERSION', 'version'])
                    temp_created_at_col = _detect_column(temp_settlement_table, ['CREATED_AT', 'CREATEDAT', 'created_at', 'createdat'])
                    temp_settlement_cols = _get_table_columns(temp_settlement_table)
                    temp_settlement_cols_upper = [c.upper() for c in temp_settlement_cols] if temp_settlement_cols else []
                    if not temp_created_at_col and 'CREATED_AT' not in temp_settlement_cols_upper:
                        try:
                            cur.execute(f'ALTER TABLE {temp_settlement_table} ADD CREATED_AT DATE')
                            import db as _db
                            if hasattr(_db, '_TABLE_COLUMNS_CACHE') and isinstance(getattr(_db, '_TABLE_COLUMNS_CACHE'), dict):
                                _db._TABLE_COLUMNS_CACHE.pop(temp_settlement_table.upper(), None)
                            temp_created_at_col = _detect_column(temp_settlement_table, ['CREATED_AT', 'CREATEDAT', 'created_at', 'createdat'])
                        except Exception as e:
                            print(f'[DEBUG api_save] Error creating CREATED_AT column in {temp_settlement_table}: {e}')
                    online_status_col = None
                    online_id_col = None
                    online_billno_col = None
                    online_customercode_col = None
                    online_billdate_col = None
                    online_salesman_col = None
                    online_location_col = None
                    if online_table:
                        online_status_col = _detect_column(online_table, ['STATUS', 'status'])
                        online_id_col = _detect_column(online_table, ['ID', 'id', 'LINENO', 'LINE_NO', 'LINEID', 'LINE_ID', 'SERIALNO', 'SRNO', 'RECNO', 'REC_ID', 'TEMP_ID', 'ONLINERECID'])
                        online_billno_col = _detect_column(online_table, ['BILLNO', 'BILL_NO', 'billno'])
                        online_customercode_col = _detect_column(online_table, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'CUSTOMER', 'customer'])
                        online_billdate_col = _detect_column(online_table, ['BILLDATE', 'BILL_DATE', 'billdate'])
                        online_salesman_col = _detect_column(online_table, ['SALESMAN_CODE', 'SALESMANCODE', 'salesman_code', 'salesmancode'])
                        online_location_col = _detect_column(online_table, ['LOCATION_CODE', 'LOCATIONCODE', 'location_code', 'locationcode'])
                    voucher_numbers = {}
                    customer_index = 0
                    for customer_code, customer_items in customer_groups.items():
                        customer_total = customer_totals[customer_code]
                        customer_index += 1
                        next_pending_int = _get_next_pendingno_inside_transaction(cur, settlement_table, temp_settlement_table, pendingno_col, temp_pendingno_col)
                        customer_voucherno = str(next_pending_int)
                        voucher_numbers[customer_code] = customer_voucherno
                        print(f'[DEBUG api_save] Customer {customer_index} ({customer_code}): pendingno {customer_voucherno}')
                        if all([locationcode_col, pendingno_col, billno_col, billdate_col, billamount_col, customercode_col, flag_col]):
                            insert_cols = [locationcode_col, pendingno_col, billno_col, billdate_col, billamount_col, customercode_col, flag_col]
                            insert_vals = [':location_code', ':pendingno', ':billno', f"TO_DATE(:billdate, 'DD/MON/YYYY')", ':billamount', ':customercode', "'R'"]
                            if voucherno_col and voucherno_col != pendingno_col:
                                insert_cols.append(voucherno_col)
                                insert_vals.append(':voucherno')
                            if settlement_salesmancode_col:
                                insert_cols.append(settlement_salesmancode_col)
                                insert_vals.append(':salesmancode')
                            if remark_col:
                                insert_cols.append(remark_col)
                                insert_vals.append(':remark')
                            if onlineflag_col:
                                insert_cols.append(onlineflag_col)
                                insert_vals.append("'O'")
                            if sett_createdby:
                                insert_cols.append(sett_createdby)
                                insert_vals.append(':createdby')
                            if sett_created_at:
                                insert_cols.append(sett_created_at)
                                insert_vals.append('SYSDATE')
                            insert_params = {'location_code': location_code, 'pendingno': customer_voucherno, 'billno': customer_voucherno, 'billdate': oracle_date, 'billamount': customer_total, 'customercode': customer_code, 'remark': remark}
                            if voucherno_col and voucherno_col != pendingno_col:
                                insert_params['voucherno'] = customer_voucherno
                            if settlement_salesmancode_col:
                                insert_params['salesmancode'] = salesman_code
                            if sett_createdby:
                                insert_params['createdby'] = current_user
                            insert_query = f"\n                                INSERT INTO {settlement_table} ({', '.join(insert_cols)})\n                                VALUES ({', '.join(insert_vals)})\n                            "
                            cur.execute(insert_query, insert_params)
                        for item in customer_items:
                            invoice_no = str(item.get('invoice_no', '')).strip()
                            amount = float(item.get('amount', 0))
                            item_id = str(item.get('id', '')).strip()
                            item_salesman_code = str(item.get('salesman_code', salesman_code)).strip()
                            if not invoice_no or amount <= 0:
                                continue
                            if online_table and online_status_col and online_billno_col and online_customercode_col:
                                online_finalcollection_col = _detect_column(online_table, ['FINALCOLLECTION', 'FINAL_COLLECTION', 'finalcollection', 'final_collection'])
                                oupdate_set = [f'{online_status_col} = 1']
                                oupdate_params: Dict[str, Any] = {'billno': invoice_no, 'customercode': customer_code}
                                if online_finalcollection_col:
                                    oupdate_set.append(f'{online_finalcollection_col} = :finalcollection')
                                    oupdate_params['finalcollection'] = amount
                                owhere_parts = [f'{online_billno_col} = :billno', f'{online_customercode_col} = :customercode']
                                if item_id and online_id_col:
                                    owhere_parts.append(f'{online_id_col} = :id')
                                    oupdate_params['id'] = item_id
                                else:
                                    if online_salesman_col:
                                        owhere_parts.append(f'{online_salesman_col} = :oc_sm')
                                        oupdate_params['oc_sm'] = item_salesman_code
                                    bd_iso = _bill_date_collection_value_to_iso(item.get('bill_date'))
                                    if not bd_iso:
                                        bd_iso = _bill_date_collection_value_to_iso(transaction_date)
                                    if online_billdate_col and bd_iso:
                                        owhere_parts.append(f"TRUNC({online_billdate_col}) = TO_DATE(:oc_bd, 'YYYY-MM-DD')")
                                        oupdate_params['oc_bd'] = bd_iso[:10]
                                    if online_location_col:
                                        owhere_parts.append(f'{online_location_col} = :oc_loc')
                                        oupdate_params['oc_loc'] = location_code
                                online_update_query = f"\n                                    UPDATE {online_table}\n                                    SET {', '.join(oupdate_set)}\n                                    WHERE {' AND '.join(owhere_parts)}\n                                "
                                cur.execute(online_update_query, oupdate_params)
                                try:
                                    rc_online = int(cur.rowcount or 0)
                                except (TypeError, ValueError):
                                    rc_online = -1
                                if rc_online == 0:
                                    print(f"[WARN api_save] ONLINE_TEMPORARY_COLLECTIONS update matched 0 rows (billno={invoice_no}, customer={customer_code}, id={('yes' if item_id else 'no')})")
                            if all([temp_locationcode_col, temp_pendingno_col, temp_customercode_col, temp_status_col, temp_paidamount_col, temp_flag_col]):
                                temp_insert_cols = [temp_locationcode_col, temp_pendingno_col, temp_customercode_col, temp_status_col, temp_paidamount_col, temp_flag_col]
                                temp_insert_vals = [':location_code', ':pendingno', ':customercode', "'PAID'", ':paidamount', "'R'"]
                                if temp_againstno_col:
                                    temp_insert_cols.append(temp_againstno_col)
                                    temp_insert_vals.append(':againstno')
                                if temp_paiddate_col:
                                    temp_insert_cols.append(temp_paiddate_col)
                                    temp_insert_vals.append(f"TO_DATE(:paiddate, 'DD/MON/YYYY')")
                                if temp_puser_col:
                                    temp_insert_cols.append(temp_puser_col)
                                    temp_insert_vals.append(':puser')
                                if temp_remarks_col:
                                    temp_insert_cols.append(temp_remarks_col)
                                    temp_insert_vals.append(':remarks')
                                if temp_salesmancode_col:
                                    temp_insert_cols.append(temp_salesmancode_col)
                                    temp_insert_vals.append(':salesmancode')
                                if temp_billamount_col:
                                    temp_insert_cols.append(temp_billamount_col)
                                    temp_insert_vals.append('0')
                                if temp_version_col:
                                    temp_insert_cols.append(temp_version_col)
                                    temp_insert_vals.append('25')
                                if temp_created_at_col:
                                    temp_insert_cols.append(temp_created_at_col)
                                    temp_insert_vals.append('SYSDATE')
                                temp_insert_query = f"\n                                    INSERT INTO {temp_settlement_table} ({', '.join(temp_insert_cols)})\n                                    VALUES ({', '.join(temp_insert_vals)})\n                                "
                                temp_params = {'location_code': location_code, 'pendingno': customer_voucherno, 'customercode': customer_code, 'paidamount': amount, 'againstno': invoice_no, 'paiddate': oracle_date, 'puser': current_user, 'remarks': remark, 'salesmancode': item_salesman_code}
                                cur.execute(temp_insert_query, temp_params)
                            if paidamount_col and balance_col and billno_col and flag_col and customercode_col:
                                update_set = [f'{paidamount_col} = :paidamount', f'{balance_col} = ({balance_col} - :paidamount)']
                                update_params = {'paidamount': amount, 'billno': invoice_no, 'customercode': customer_code}
                                if paiddate_col:
                                    update_set.append(f"{paiddate_col} = TO_DATE(:paiddate, 'DD/MON/YYYY')")
                                    update_params['paiddate'] = oracle_date
                                if puser_col:
                                    update_set.append(f'{puser_col} = :puser')
                                    update_params['puser'] = current_user
                                if voucherno_col:
                                    update_set.append(f'{voucherno_col} = :voucherno')
                                    update_params['voucherno'] = customer_voucherno
                                if remark_col:
                                    update_set.append(f'{remark_col} = :remark')
                                    update_params['remark'] = remark
                                update_query = f"\n                                    UPDATE {settlement_table}\n                                    SET {', '.join(update_set)}\n                                    WHERE {billno_col} = :billno\n                                      AND {flag_col} = 'B'\n                                      AND {customercode_col} = :customercode\n                                "
                                cur.execute(update_query, update_params)
                                if status_col and pflag_col and balance_col and voucherno_col:
                                    status_update_query = f"\n                                        UPDATE {settlement_table}\n                                        SET {status_col} = 'PAID', {pflag_col} = 'Y'\n                                        WHERE {balance_col} = 0\n                                          AND {voucherno_col} = :voucherno\n                                          AND {billno_col} = :billno\n                                          AND {flag_col} = 'B'\n                                          AND {customercode_col} = :customercode\n                                    "
                                    cur.execute(status_update_query, {'voucherno': customer_voucherno, 'billno': invoice_no, 'customercode': customer_code})
                        conn.commit()
                        print(f'[DEBUG api_save] Committed customer {customer_index} ({customer_code})')
                    print(f'[DEBUG api_save] All {customer_index} customer(s) saved')
                    salesman_name = ''
                    location_name = ''
                    try:
                        salesman_info = _get_salesman_info(salesman_code)
                        if salesman_info:
                            salesman_name = (salesman_info.get('salesmanname') or '').strip()
                    except Exception as e:
                        print(f'[DEBUG api_save] Error fetching salesman name: {e}')
                    try:
                        loc_info = get_location_info_by_dbkey(None)
                        if loc_info:
                            location_name = (loc_info.get('locationname') or '').strip()
                    except Exception as e:
                        print(f'[DEBUG api_save] Error fetching location name: {e}')
                    pdf_data = None
                    try:
                        pdf_data = _generate_collection_pdf(collection_items=collection_items, customer_groups=customer_groups, customer_totals=customer_totals, voucher_numbers=voucher_numbers, transaction_date=oracle_date, salesman_code=salesman_code, salesman_name=salesman_name, remark=remark, location_code=location_code, user_name=current_user, location_name=location_name, status_label='Completed')
                    except Exception as e:
                        print(f'[ERROR api_save] PDF generation error: {e}')
                        import traceback
                        print(traceback.format_exc())
                    response_data = {'success': True, 'message': 'Collection saved successfully'}
                    if voucher_numbers:
                        response_data['voucher_numbers'] = voucher_numbers
                    if pdf_data:
                        import base64
                        response_data['pdf_base64'] = base64.b64encode(pdf_data).decode('utf-8')
                        response_data['pdf_filename'] = f"collection_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                    return (response_data, 200)
        try:
            tc_save_response_tuple = _run_save_transaction()
        except BaseException:
            _tc_payload_guard_release(fp_shared)
            raise
        _tc_payload_guard_touch(fp_shared)
        try:
            _rb, _rst = tc_save_response_tuple
            if _rst == 200 and isinstance(_rb, dict) and _rb.get('success'):
                _log_temporary_collection_save_success(data, _rb)
        except Exception:
            pass
        return tc_save_response_tuple
    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f'[ERROR _temporary_collection_save_run] {error_msg}')
        print(traceback.format_exc())
        return ({'success': False, 'error': f'Error saving collection: {error_msg}', 'error_type': type(e).__name__}, 500)

@bp.route('/accounts/temporary-collection/api/save', methods=['POST'])
def api_save():
    """API: Save collection data (POST body must include one-time ``save_nonce`` from page load or prior response)."""
    if not session.get('user'):
        return jsonify({'error': 'Not authenticated'}, 401)
    data = request.get_json(silent=True) or {}
    submitted_nonce = (data.get('save_nonce') or '').strip()
    if not verify_consume_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY, submitted_nonce):
        return replay_blocked_response_global()
    try:
        location_info = get_location_info_by_dbkey(None)
        if not location_info or location_info.get('locationcode') is None:
            return _temporary_collection_save_response({'success': False, 'error': "Location (locationcode) could not be resolved. Please ensure LOCATIONMASTER has a row with BASELOCATIONFLAG='Y'."}, 400)
        expected_locationcode = location_info.get('locationcode')
    except Exception as e:
        print(f'[DEBUG api_save] locationcode check failed: {e}')
        return _temporary_collection_save_response({'success': False, 'error': 'Location (locationcode) could not be resolved.'}, 400)
    payload_location_code = data.get('location_code')
    if payload_location_code is not None and expected_locationcode is not None:
        try:
            payload_loc = int(payload_location_code) if str(payload_location_code).isdigit() else None
            if payload_loc is not None and payload_loc != int(expected_locationcode):
                return _temporary_collection_save_response({'success': False, 'error': 'Location code mismatch. Do not save.'}, 400)
        except (ValueError, TypeError):
            return _temporary_collection_save_response({'success': False, 'error': 'Location code mismatch. Do not save.'}, 400)
    fp = _temporary_collection_save_payload_fingerprint(data)
    now_ts = time.time()
    prev = session.get(TC_COLLECTION_SAVE_FP_SESSION_KEY)
    if isinstance(prev, dict) and prev.get('fp') == fp and (now_ts - float(prev.get('t', 0)) < 90.0):
        return _temporary_collection_save_response({'success': False, 'error': 'Duplicate save blocked: the same collection was just submitted. If it already saved, use Back.'}, 409)
    body, status = _temporary_collection_save_run(data)
    if status == 200 and isinstance(body, dict) and body.get('success'):
        session[TC_COLLECTION_SAVE_FP_SESSION_KEY] = {'fp': fp, 't': time.time()}
        session.modified = True
    return _temporary_collection_save_response(body, status)

def _bulk_save_pending_payload_fingerprint(data: Dict[str, Any]) -> str:
    """Stable hash from request body (checked rows + dates) — used when ``selected`` is sent."""
    date_from = str(data.get('date_from') or '').strip()
    date_to = str(data.get('date_to') or '').strip()
    sel_raw = data.get('selected')
    norm: List[Tuple[str, str]] = []
    if isinstance(sel_raw, list):
        for it in sel_raw:
            if not isinstance(it, dict):
                continue
            sm = str(it.get('salesman_code') or '').strip()
            bd_iso = _bill_date_collection_value_to_iso(str(it.get('bill_date') or '').strip())
            if sm and bd_iso:
                norm.append((sm, bd_iso))
    norm.sort()
    payload: Dict[str, Any] = {'m': 'sel', 'df': date_from, 'dt': date_to, 'rows': norm}
    raw = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()

def _bulk_save_pending_session_fingerprint(data: Dict[str, Any], date_from: str, date_to: str, pending: List[Dict[str, Any]]) -> str:
    """
    Bulk duplicate session key: save-all uses resolved pending groups so new salesman/day rows
    change the hash; selected mode uses request ``selected`` list only.
    """
    if data.get('selected') is not None:
        return _bulk_save_pending_payload_fingerprint(data)
    norm: List[Tuple[str, str]] = []
    for r in pending:
        sm = str(r.get('salesmancode') or '').strip()
        bd_iso = _bill_date_collection_value_to_iso(r.get('billdate'))
        if sm and bd_iso:
            norm.append((sm, bd_iso))
    norm.sort()
    payload: Dict[str, Any] = {'m': 'all', 'df': date_from, 'dt': date_to, 'groups': norm}
    raw = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()

@bp.route('/accounts/temporary-collection/api/save-all-pending', methods=['POST'])
def api_save_all_pending():
    """Run the same settle/save logic as Temporary Collection Save for each pending salesman+date group (one nonce for the bulk request)."""
    if not session.get('user'):
        return jsonify({'error': 'Not authenticated'}, 401)
    data = request.get_json(silent=True) or {}
    submitted_nonce = (data.get('save_nonce') or '').strip()
    if not verify_consume_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY, submitted_nonce):
        return replay_blocked_response_global()
    try:
        location_info = get_location_info_by_dbkey(None)
        if not location_info or location_info.get('locationcode') is None:
            return _temporary_collection_save_response({'success': False, 'error': 'Location could not be resolved.', 'replay_blocked': False}, 400)
        expected_locationcode = location_info.get('locationcode')
    except Exception:
        return _temporary_collection_save_response({'success': False, 'error': 'Location could not be resolved.', 'replay_blocked': False}, 400)
    payload_location_code = data.get('location_code')
    if payload_location_code is not None and expected_locationcode is not None:
        try:
            payload_loc = int(payload_location_code) if str(payload_location_code).isdigit() else None
            if payload_loc is not None and payload_loc != int(expected_locationcode):
                return _temporary_collection_save_response({'success': False, 'error': 'Location code mismatch. Do not save.'}, 400)
        except (ValueError, TypeError):
            return _temporary_collection_save_response({'success': False, 'error': 'Location code mismatch. Do not save.'}, 400)
    sel_raw = data.get('selected')
    if not isinstance(sel_raw, list) or len(sel_raw) == 0:
        return _temporary_collection_save_response({'success': False, 'error': 'Select at least one pending salesman row (salesman + date) to save.', 'replay_blocked': False}, 400)
    date_from = (data.get('date_from') or '').strip()
    date_to = (data.get('date_to') or '').strip()
    cols = _get_temporary_collections_list(date_from=date_from, date_to=date_to)
    pending = [r for r in cols if int(r.get('min_status') or 0) == 0]
    sel_keys: Set[Tuple[str, str]] = set()
    for it in sel_raw:
        if not isinstance(it, dict):
            continue
        sm = str(it.get('salesman_code') or '').strip()
        bd_iso = _bill_date_collection_value_to_iso(str(it.get('bill_date') or '').strip())
        if sm and bd_iso:
            sel_keys.add((sm, bd_iso))
    if not sel_keys:
        return _temporary_collection_save_response({'success': False, 'error': 'No valid salesman + date pairs in selection.', 'replay_blocked': False}, 400)
    filtered: List[Dict[str, Any]] = []
    for r in pending:
        sm = str(r.get('salesmancode') or '').strip()
        bd_iso_r = _bill_date_collection_value_to_iso(r.get('billdate'))
        if sm and bd_iso_r and ((sm, bd_iso_r) in sel_keys):
            filtered.append(r)
    pending = filtered
    bulk_fp = _bulk_save_pending_session_fingerprint(data, date_from, date_to, pending)
    now_ts = time.time()
    prev_bulk = session.get(TC_BULK_SAVE_FP_SESSION_KEY)
    if isinstance(prev_bulk, dict) and prev_bulk.get('fp') == bulk_fp and (now_ts - float(prev_bulk.get('t', 0)) < 90.0):
        return _temporary_collection_save_response({'success': False, 'error': 'Duplicate bulk save blocked: the same pending save was just submitted. Refresh the list if needed.', 'bulk': True}, 409)
    results = []
    ok_count = 0
    skipped = 0
    fail_count = 0
    for row in pending:
        sm = str(row.get('salesmancode') or '').strip()
        bill_iso = _bill_date_collection_value_to_iso(row.get('billdate'))
        if not sm or not bill_iso:
            skipped += 1
            results.append({'salesman_code': sm or None, 'bill_date': bill_iso, 'ok': False, 'skipped': True, 'detail': 'Missing salesman or bill date'})
            continue
        invoices = _get_invoice_details_from_online(sm, date_from=None, date_to=None, use_date_range=False, status_filter=0, exact_bill_date=bill_iso)
        coll_items = _online_rows_to_bulk_collection_items(invoices, sm, bill_iso)
        if not coll_items:
            skipped += 1
            results.append({'salesman_code': sm, 'bill_date': bill_iso, 'ok': False, 'skipped': True, 'detail': 'No payable lines (empty or filtered)'})
            continue
        payload = {'transaction_date': bill_iso, 'salesman_code': sm, 'remark': (data.get('remark') or 'Pending Amount').strip() or 'Pending Amount', 'collection_items': coll_items}
        body, st = _temporary_collection_save_run(payload)
        if st == 200 and body.get('success'):
            ok_count += 1
            results.append({'salesman_code': sm, 'bill_date': bill_iso, 'ok': True})
        else:
            fail_count += 1
            results.append({'salesman_code': sm, 'bill_date': bill_iso, 'ok': False, 'error': (body or {}).get('error') or 'Save failed', 'status': st})
    if ok_count > 0:
        session[TC_BULK_SAVE_FP_SESSION_KEY] = {'fp': bulk_fp, 't': time.time()}
        session.modified = True
    try:
        _log_temporary_collection_bulk_save(data, ok_count=ok_count, skipped=skipped, fail_count=fail_count, pending_found=len(pending), results=results)
    except Exception:
        pass
    return json_response_rotate_global({'success': True, 'bulk': True, 'selected_filter': sel_raw is not None, 'pending_found': len(pending), 'saved_ok': ok_count, 'skipped_no_lines': skipped, 'failed': fail_count, 'results': results}, 200)

def api_query():
    """API: Query existing voucher data"""
    if not session.get('user'):
        return jsonify({'error': 'Not authenticated'}, 401)
    voucherno = request.args.get('voucherno', '').strip()
    if not voucherno:
        return jsonify({'success': False, 'error': 'Voucher number required'}, 400)
    try:
        temp_settlement_table = _detect_table(['TBLTEMPSETTLEMENT', 'tbltempsettlement'])
        if not temp_settlement_table:
            return jsonify({'success': False, 'error': 'Table not found'}, 500)
        pendingno_col = _detect_column(temp_settlement_table, ['PENDINGNO', 'PENDING_NO'])
        if not pendingno_col:
            return jsonify({'success': False, 'error': 'Column not found'}, 500)
        customercode_col = _detect_column(temp_settlement_table, ['CUSTOMERCODE', 'CUSTOMER_CODE'])
        paidamount_col = _detect_column(temp_settlement_table, ['PAIDAMOUNT', 'PAID_AMOUNT', 'paidamount'])
        againstno_col = _detect_column(temp_settlement_table, ['AGAINSTNO', 'AGAINST_NO', 'againstno'])
        salesmancode_col = _detect_column(temp_settlement_table, ['SALESMANCODE', 'SALESMAN_CODE', 'salesmancode'])
        query = f'\n            SELECT \n                {customercode_col} AS customercode,\n                {paidamount_col} AS paidamount,\n                {againstno_col} AS againstno,\n                {salesmancode_col} AS salesmancode\n            FROM {temp_settlement_table}\n            WHERE {pendingno_col} = :voucherno\n        '
        _, rows = _fetch_rows(query, {'voucherno': voucherno})
        customer_table = _detect_table(['CUSTOMER', 'CUSTOMERS', 'customers', 'customer'])
        if customer_table:
            customer_code_col = _detect_column(customer_table, ['CUST_CODE', 'CUSTOMERCODE', 'CUSTOMER_CODE', 'CODE'])
            customer_name_col = _detect_column(customer_table, ['CUST_NAME', 'CUSTOMERNAME', 'CUSTOMER_NAME', 'NAME'])
            if customer_code_col and customer_name_col:
                for row in rows:
                    cust_code = row.get('customercode')
                    if cust_code:
                        cust_query = f'\n                            SELECT {customer_name_col} AS customername\n                            FROM {customer_table}\n                            WHERE {customer_code_col} = :customercode\n                        '
                        try:
                            _, cust_rows = _fetch_rows(cust_query, {'customercode': cust_code})
                            if cust_rows:
                                row['customername'] = cust_rows[0].get('customername', '')
                        except Exception:
                            row['customername'] = ''
        return jsonify({'success': True, 'items': rows})
    except Exception as e:
        import traceback
        print(f'[ERROR api_query] {e}')
        print(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}, 500)
