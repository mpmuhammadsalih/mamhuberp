"""Reports blueprint"""
from pathlib import Path
import base64
import csv
import io
import json
import logging
import os
import re
import uuid
import zipfile
from xml.sax.saxutils import escape as _xml_escape
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from nexa_http import Blueprint, jsonify, redirect, render_template, request, session, url_for, send_file
from nexa_http import Response
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, KeepTogether
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas as rl_canvas
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    rl_canvas = None
    Image = None
    KeepTogether = None
try:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
    from cryptography.x509.oid import NameOID
    CRYPTOGRAPHY_AVAILABLE = True
except Exception:
    CRYPTOGRAPHY_AVAILABLE = False
logger = logging.getLogger(__name__)
from global_lookup import (
    apply_session_db_connection,
    normalize_customer_code as _normalize_report_customer_code,
    resolve_category_label as _resolve_report_category_label,
    resolve_customer_label as _resolve_report_customer_label,
    resolve_item_label as _resolve_report_item_label,
    search_categories as _search_report_categories,
    search_customers as _search_report_customers,
    search_lookup,
)
from db import DATABASES, _detect_column, _detect_table, _fetch_rows, resolve_warehouse_master_table, _safe_rows, itemjournal_warehouse_code_column, _safe_rows_auth, delete_smart_list_ai_chat, delete_sales_print_tables, get_smart_list_ai_chat_messages, get_smart_list_ai_chat_sessions, get_customer_ledger_customers, get_customer_branch_filter_options, get_customer_outstanding_aging_credit, get_customer_outstanding_aging_credit_three_month, get_customer_outstanding_cash_three_month_specs, get_customer_outstanding_details_cash, get_customer_outstanding_details_credit, get_location_info_by_dbkey, get_route_outstanding_aging, get_route_outstanding_details, get_sales_print_data, get_salesmen_list, rename_smart_list_ai_chat, save_smart_list_ai_message, set_active_db_host, set_active_db_key, _get_table_columns, _oracle_itemmaster_col_name_from_dbcode_label, _bill_history_return_predicate, parse_billno_from_request, billno_is_valid, parse_lpono_from_request, lpono_is_valid, coerce_lpono, parse_receiptno_from_request, receiptno_is_valid, coerce_receiptno
_ADDON_ROOT = Path(__file__).resolve().parents[1]
bp = Blueprint('reports', __name__, template_folder=str(_ADDON_ROOT / 'views' / 'templates'))
_LOG_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs', 'app.log')
_QZ_CERT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'qz-certs')
_QZ_CERT_FILE = os.environ.get('QZ_CERT_FILE', os.path.join(_QZ_CERT_DIR, 'digital-certificate.pem'))
_QZ_KEY_FILE = os.environ.get('QZ_PRIVATE_KEY_FILE', os.path.join(_QZ_CERT_DIR, 'private-key.pem'))

def _apply_active_connection(location_code: str) -> None:
    """Apply active database connection based on location_code"""
    if location_code in DATABASES:
        db_config = DATABASES[location_code]
        print(f"[DEBUG _apply_active_connection] Connecting to {location_code}: {db_config['user']}@{db_config['dsn']}")
        set_active_db_key(location_code)
        set_active_db_host(None)
    else:
        set_active_db_key('HO')
        set_active_db_host(None)

def _ensure_qz_cert_files(force_regenerate: bool=False) -> Tuple[bool, str]:
    if not force_regenerate and os.path.isfile(_QZ_CERT_FILE) and os.path.isfile(_QZ_KEY_FILE):
        return (True, '')
    if not CRYPTOGRAPHY_AVAILABLE:
        return (False, 'cryptography package not available for QZ certificate generation.')
    try:
        os.makedirs(_QZ_CERT_DIR, exist_ok=True)
        if force_regenerate:
            stamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
            if os.path.isfile(_QZ_CERT_FILE):
                os.replace(_QZ_CERT_FILE, f'{_QZ_CERT_FILE}.{stamp}.bak')
            if os.path.isfile(_QZ_KEY_FILE):
                os.replace(_QZ_KEY_FILE, f'{_QZ_KEY_FILE}.{stamp}.bak')
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name([x509.NameAttribute(NameOID.COUNTRY_NAME, 'AE'), x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'Nexus Erp'), x509.NameAttribute(NameOID.COMMON_NAME, 'Nexus Erp QZ Printing')])
        cert = x509.CertificateBuilder().subject_name(subject).issuer_name(issuer).public_key(private_key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(datetime.utcnow() - timedelta(days=1)).not_valid_after(datetime.utcnow() + timedelta(days=3650)).add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True).sign(private_key, hashes.SHA256())
        with open(_QZ_KEY_FILE, 'wb') as key_file:
            key_file.write(private_key.private_bytes(encoding=serialization.Encoding.PEM, format=serialization.PrivateFormat.PKCS8, encryption_algorithm=serialization.NoEncryption()))
        with open(_QZ_CERT_FILE, 'wb') as cert_file:
            cert_file.write(cert.public_bytes(serialization.Encoding.PEM))
        return (True, '')
    except Exception as exc:
        logger.exception('QZ cert generation failed: %s', exc)
        return (False, str(exc))

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
        user_dbkey = session.get('tenant_id') or location_code_value or 'HO'
        try:
            location_info = get_location_info_by_dbkey(user_dbkey)
            location_code_int = location_info.get('locationcode')
            if location_code_int is None:
                location_code_int = 1
        except Exception as e:
            print(f'[DEBUG reports] Could not get location_code from LOCATIONMASTER: {e}')
            location_code_int = 1
    return int(location_code_int)


def _parse_report_billno(raw: Any) -> Tuple[Optional[Any], str]:
    """Parse billno from URL/form/API (numeric legacy or formatted e.g. SI-000005)."""
    bn = parse_billno_from_request(raw)
    if not billno_is_valid(bn):
        return (None, 'Enter a valid Bill No')
    return (bn, '')

def _default_report_date_range(date_from: str, date_to: str) -> Tuple[str, str]:
    """If both range inputs are blank, default to today so filters match Store/Purchase detail UX."""
    df = (date_from or '').strip()
    dt = (date_to or '').strip()
    if not df and (not dt):
        today = datetime.now().strftime('%Y-%m-%d')
        return (today, today)
    return (df, dt)

def _format_pdf_date(value: Any) -> str:
    """Format date for PDF display (YYYY-MM-DD or object)."""
    if value is None:
        return ''
    if isinstance(value, str):
        return value[:10] if len(value) >= 10 else value
    if hasattr(value, 'strftime'):
        return value.strftime('%Y-%m-%d')
    return str(value)
_ARABIC_PDF_FONT_NAME = 'RgcArabicPdfFont'
_ARABIC_PDF_FONT_READY = False

def _ensure_arabic_pdf_font() -> str:
    """Register an Arabic-capable font for reportlab if available."""
    global _ARABIC_PDF_FONT_READY
    if not REPORTLAB_AVAILABLE:
        return 'Helvetica'
    if _ARABIC_PDF_FONT_READY:
        return _ARABIC_PDF_FONT_NAME
    candidates = ['C:\\Windows\\Fonts\\arial.ttf', 'C:\\Windows\\Fonts\\tahoma.ttf', 'C:\\Windows\\Fonts\\segoeui.ttf']
    for fp in candidates:
        try:
            if os.path.isfile(fp):
                pdfmetrics.registerFont(TTFont(_ARABIC_PDF_FONT_NAME, fp))
                _ARABIC_PDF_FONT_READY = True
                return _ARABIC_PDF_FONT_NAME
        except Exception:
            continue
    return 'Helvetica'

def _format_arabic_for_pdf(text: str) -> str:
    """Best-effort Arabic shaping fallback for reportlab text flow."""
    txt = str(text or '').strip()
    if not txt:
        return ''
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(txt))
    except Exception:
        return f'\u202b{txt}\u202c'

def _amount_in_words(amount: float) -> str:
    """Convert a money amount to English words.

    Whole amounts: 'Three Hundred Fifteen Only'
    With fraction: 'Three Hundred Fifteen and 25/100 Only'
    """
    try:
        amt = abs(float(amount or 0))
    except (TypeError, ValueError):
        amt = 0.0
    whole = int(amt)
    cents = int(round((amt - whole) * 100))
    if cents == 100:
        whole += 1
        cents = 0
    ones = [
        '', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine',
        'Ten', 'Eleven', 'Twelve', 'Thirteen', 'Fourteen', 'Fifteen', 'Sixteen',
        'Seventeen', 'Eighteen', 'Nineteen',
    ]
    tens = ['', '', 'Twenty', 'Thirty', 'Forty', 'Fifty', 'Sixty', 'Seventy', 'Eighty', 'Ninety']

    def _under_1000(n: int) -> str:
        if n <= 0:
            return ''
        parts: List[str] = []
        h = n // 100
        r = n % 100
        if h:
            parts.append(ones[h] + ' Hundred')
        if r:
            if r < 20:
                parts.append(ones[r])
            else:
                t = tens[r // 10]
                o = ones[r % 10]
                parts.append(t + ('-' + o if o else ''))
        return ' '.join(parts)

    if whole == 0:
        words = 'Zero'
    else:
        chunks = []
        scales = ['', 'Thousand', 'Million', 'Billion']
        n = whole
        scale_i = 0
        while n > 0 and scale_i < len(scales):
            chunk = n % 1000
            if chunk:
                label = _under_1000(chunk)
                if scales[scale_i]:
                    label = f'{label} {scales[scale_i]}'
                chunks.append(label)
            n //= 1000
            scale_i += 1
        words = ' '.join(reversed(chunks))
    prefix = 'Minus ' if float(amount or 0) < 0 else ''
    if cents:
        return f'{prefix}{words} and {cents:02d}/100 Only'
    return f'{prefix}{words} Only'


def _generate_cashbilldup_pdf(billno: int, header: Dict[str, Any], lines: List[Dict[str, Any]], invoice_title: str='INVOICE') -> Optional[bytes]:
    """Generate Sales Invoice / Return / Order PDF in a professional invoice layout."""
    if not REPORTLAB_AVAILABLE:
        return None
    try:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            topMargin=0.4 * inch,
            bottomMargin=1.55 * inch,
            leftMargin=0.45 * inch,
            rightMargin=0.45 * inch,
        )
        styles = getSampleStyleSheet()
        arabic_font = _ensure_arabic_pdf_font()
        BLUE = colors.HexColor('#1a3a6b')
        BORDER = colors.HexColor('#c5cdd8')
        GRAY_ROW = colors.HexColor('#f5f7fa')
        TEXT = colors.HexColor('#1a1a1a')
        MUTED = colors.HexColor('#555f6b')
        PAD = 4
        W = 7.4 * inch

        def _s(name, **kw):
            base = kw.pop('parent', styles['Normal'])
            kw.setdefault('textColor', TEXT)
            return ParagraphStyle(name, parent=base, **kw)

        N8 = _s('si8', fontSize=8, leading=10)
        N8M = _s('si8m', fontSize=8, leading=10, textColor=MUTED)
        N9 = _s('si9', fontSize=9, leading=11)
        N9B = _s('si9b', fontSize=9, leading=11, fontName='Helvetica-Bold')
        N8R = _s('si8r', fontSize=8, leading=10, alignment=TA_RIGHT)
        N8C = _s('si8c', fontSize=8, leading=10, alignment=TA_CENTER)
        WHT = _s('siwht', fontSize=8.5, leading=11, alignment=TA_CENTER, textColor=colors.white, fontName='Helvetica-Bold')
        WHT_L = _s('siwhtl', fontSize=9, leading=11, textColor=colors.white, fontName='Helvetica-Bold')
        TITLE = _s('sititle', fontSize=18, leading=22, alignment=TA_RIGHT, textColor=BLUE, fontName='Helvetica-Bold')
        CO_NAME = _s('sicomp', fontSize=13, leading=16, textColor=BLUE, fontName='Helvetica-Bold')

        # Sample uses INVOICE (not TAX INVOICE). Keep RETURN / ORDER titles as-is.
        raw_title = str(invoice_title or 'INVOICE').strip().upper()
        if raw_title in ('SALES INVOICE', 'TAX INVOICE', 'INVOICE', ''):
            display_title = 'INVOICE'
        else:
            display_title = raw_title
        # Sales returns store qty/amounts as negative — print absolute values (no "-" sign).
        is_sales_return_pdf = 'RETURN' in raw_title

        customer_code = str(header.get('customercode') or '')
        customer_name = str(header.get('customername') or '')
        customer_address = str(header.get('address') or '')
        customer_phone = str(header.get('telephone') or header.get('phone') or header.get('customer_phone') or '').strip()
        customer_mobile = str(header.get('mobile') or header.get('customer_mobile') or '').strip()
        bill_date_display = _format_pdf_date(header.get('billdate'))
        bill_time = str(header.get('billtime') or '')
        remarks = str(header.get('remarks') or '')
        order_no = str(header.get('orderno') or '').strip()
        try:
            sess_user = session.get('user')
            sess_loc_name = session.get('location_name')
        except Exception:
            sess_user = None
            sess_loc_name = None
        created_by = str(header.get('createdby') or '').strip()
        prepared_by = str(sess_user or '').strip()

        company_name = str(sess_loc_name or 'Nexus Erp')
        company_address = ''
        company_phone = ''
        company_email = ''
        company_tax = ''
        company_logo = ''

        try:
            from db import get_company_profile
            cp = get_company_profile() or {}
            cp_name = str(cp.get('company_name') or cp.get('COMPANY_NAME') or cp.get('legal_name') or cp.get('LEGAL_NAME') or '').strip()
            if cp_name:
                company_name = cp_name
            addr_parts = [
                str(cp.get('address1') or cp.get('ADDRESS1') or '').strip(),
                str(cp.get('address2') or cp.get('ADDRESS2') or '').strip(),
                ', '.join(p for p in [
                    str(cp.get('city') or cp.get('CITY') or '').strip(),
                    str(cp.get('state_region') or cp.get('STATE_REGION') or '').strip(),
                    str(cp.get('postal_code') or cp.get('POSTAL_CODE') or '').strip(),
                ] if p),
                str(cp.get('country') or cp.get('COUNTRY') or '').strip(),
            ]
            company_address = ', '.join(p for p in addr_parts if p)
            company_phone = str(cp.get('phone') or cp.get('PHONE') or '').strip() or company_phone
            company_email = str(cp.get('email') or cp.get('EMAIL') or '').strip() or company_email
            company_tax = str(cp.get('tax_id') or cp.get('TAX_ID') or '').strip()
            logo_rel = str(cp.get('logo_path') or cp.get('LOGO_PATH') or '').strip()
            if logo_rel:
                for base in (
                    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'static'),
                    os.path.join(os.getcwd(), 'static'),
                ):
                    cand = os.path.abspath(os.path.join(base, logo_rel.replace('/', os.sep)))
                    if os.path.isfile(cand):
                        company_logo = cand
                        break
        except Exception:
            pass

        try:
            loc_tbl = 'LOCATIONMASTER'
            loc_code_col = _detect_column(loc_tbl, ['LOCATIONCODE', 'locationcode'])
            addr_col = _detect_column(loc_tbl, ['ADDRESS', 'ADDRESS1', 'LOCATIONADDRESS', 'locationaddress'])
            phone_col = _detect_column(loc_tbl, ['PHONE', 'TELEPHONE', 'MOBILE', 'TELNO', 'telno'])
            email_col = _detect_column(loc_tbl, ['EMAIL', 'EMAILID', 'EMAIL_ID', 'MAIL', 'EMAILADDRESS'])
            tax_col = _detect_column(loc_tbl, ['GSTIN', 'GSTNO', 'TAXNO', 'TAX_ID', 'CRNO', 'TRN'])
            sel_cols = ['LOCATIONNAME']
            if addr_col:
                sel_cols.append(addr_col)
            if phone_col:
                sel_cols.append(phone_col)
            if email_col:
                sel_cols.append(email_col)
            if tax_col:
                sel_cols.append(tax_col)
            where_parts = ["BASELOCATIONFLAG = 'Y'"]
            params: Dict[str, Any] = {}
            loc_code_val = header.get('locationcode')
            if loc_code_col and loc_code_val not in (None, '', 'None'):
                where_parts = [f'{loc_code_col} = :loc']
                params['loc'] = loc_code_val
            loc_rows = _safe_rows(f"SELECT {', '.join(sel_cols)} FROM {loc_tbl} WHERE {' AND '.join(where_parts)}", params)
            if loc_rows:
                lr = loc_rows[0]
                if not company_name or company_name == 'Nexus Erp':
                    company_name = str(lr.get('locationname') or company_name).strip() or company_name
                if not company_address and addr_col:
                    company_address = str(lr.get(addr_col.lower()) or '').strip()
                if not company_phone and phone_col:
                    company_phone = str(lr.get(phone_col.lower()) or '').strip()
                if not company_email and email_col:
                    company_email = str(lr.get(email_col.lower()) or '').strip()
                if not company_tax and tax_col:
                    company_tax = str(lr.get(tax_col.lower()) or '').strip()
        except Exception:
            pass

        if customer_code and (not customer_phone or not customer_mobile):
            try:
                cust_tbl = 'CUSTOMERS'
                cust_code_col = _detect_column(cust_tbl, ['CUSTOMERCODE', 'CUST_CODE', 'CODE'])
                cust_phone_col = _detect_column(cust_tbl, ['PHONE', 'TELEPHONE', 'TELNO', 'PHONE1', 'LANDLINE'])
                cust_mobile_col = _detect_column(cust_tbl, ['MOBILE', 'MOBILENO', 'MOBILE_NO', 'MOBNO', 'MOBILE1'])
                select_cols = []
                if cust_phone_col:
                    select_cols.append(cust_phone_col)
                if cust_mobile_col and cust_mobile_col not in select_cols:
                    select_cols.append(cust_mobile_col)
                if cust_code_col and select_cols:
                    c_rows = _safe_rows(f"SELECT {', '.join(select_cols)} FROM {cust_tbl} WHERE {cust_code_col} = :cc", {'cc': customer_code})
                    if c_rows:
                        c0 = c_rows[0]
                        if not customer_phone and cust_phone_col:
                            customer_phone = str(c0.get(cust_phone_col.lower()) or '').strip()
                        if not customer_mobile and cust_mobile_col:
                            customer_mobile = str(c0.get(cust_mobile_col.lower()) or '').strip()
            except Exception:
                pass

        cust_phone_display = customer_phone or customer_mobile
        if customer_phone and customer_mobile and customer_phone != customer_mobile:
            cust_phone_display = f'{customer_phone} / {customer_mobile}'

        subtotal = 0.0
        line_disc_total = 0.0
        pt_rows = []
        header_cols = ['Sl.No.', 'Item Code', 'Description', 'Qty', 'Unit', 'Unit Price', 'Discount', 'Amount']
        pt_rows.append([Paragraph(f'<b>{c}</b>', WHT) for c in header_cols])

        for idx, row in enumerate(lines or [], 1):
            qty = float(row.get('quantity') or 0)
            rate = float(row.get('rate') or 0)
            itdisc = float(row.get('itdisc') or row.get('discount') or 0)
            # Sales return lines: qty negative, ITDISC stored positive — accumulate abs for print.
            line_disc_total += abs(itdisc) if is_sales_return_pdf else itdisc
            try:
                stored_amt = float(row.get('amount')) if row.get('amount') is not None else None
            except (TypeError, ValueError):
                stored_amt = None
            if stored_amt is not None and abs(stored_amt) > 1e-9:
                amount = stored_amt
            elif qty < 0 or is_sales_return_pdf:
                amount = -(abs(qty) * rate - abs(itdisc))
            else:
                amount = qty * rate - itdisc
            # Gross for returns uses absolute qty so subtotal prints positive before abs().
            subtotal += (abs(qty) * rate) if (is_sales_return_pdf or qty < 0) else (qty * rate)
            print_qty = abs(qty) if is_sales_return_pdf else qty
            print_disc = abs(itdisc) if is_sales_return_pdf else itdisc
            print_amt = abs(amount) if is_sales_return_pdf else amount
            item_name = str(row.get('itemname') or row.get('itemdetails1') or row.get('item_name') or '')
            item_name_ara = str(row.get('itemnameara') or row.get('item_name_ara') or '').strip()
            item_name_cell = _xml_escape(item_name)
            if item_name_ara:
                ara_text = _xml_escape(_format_arabic_for_pdf(item_name_ara))
                if item_name_cell:
                    item_name_cell = f'{item_name_cell}<br/><font name="{arabic_font}" size="7.5">{ara_text}</font>'
                else:
                    item_name_cell = f'<font name="{arabic_font}" size="7.5">{ara_text}</font>'
            item_barcode = str(row.get('barcode') or row.get('manufacturerid') or '').strip()
            if item_barcode:
                bc_text = f'<font size="7.5" color="#333333">{_xml_escape(item_barcode)}</font>'
                item_name_cell = f'{item_name_cell}<br/>{bc_text}' if item_name_cell else bc_text
            pt_rows.append([
                Paragraph(str(row.get('slno') or idx), N8C),
                Paragraph(_xml_escape(str(row.get('itemcode') or '')), N8C),
                Paragraph(item_name_cell or '', N8),
                Paragraph(f'{print_qty:.2f}', N8R),
                Paragraph(_xml_escape(str(row.get('unitofmeasurement') or row.get('uom') or '')), N8C),
                Paragraph(f'{rate:.3f}', N8R),
                Paragraph(f'{print_disc:.2f}', N8R),
                Paragraph(f'{print_amt:.2f}', N8R),
            ])

        header_disc = float(header.get('discountamount') or 0)
        total_discount = header_disc if abs(header_disc) > 1e-9 else line_disc_total
        # Do not use `or` — negative NETBILLAMOUNT (sales return) is truthy, but
        # treat missing/blank as fall back to computed net.
        net_raw = header.get('netbillamount')
        try:
            if net_raw is not None and str(net_raw).strip() != '':
                net_amount = float(net_raw)
            else:
                net_amount = subtotal - total_discount
        except (TypeError, ValueError):
            net_amount = subtotal - total_discount
        if is_sales_return_pdf:
            subtotal = abs(subtotal)
            total_discount = abs(total_discount)
            net_amount = abs(net_amount)

        elements: List[Any] = []

        # 1. HEADER: company left + title/meta right
        co_bits = [Paragraph(_xml_escape(company_name), CO_NAME)]
        if company_address:
            co_bits.append(Paragraph(_xml_escape(company_address), N8M))
        if company_phone:
            co_bits.append(Paragraph(f'Tel: {_xml_escape(company_phone)}', N8M))
        if company_email:
            co_bits.append(Paragraph(f'Email: {_xml_escape(company_email)}', N8M))
        if company_tax:
            co_bits.append(Paragraph(f'Tax / GST No.: {_xml_escape(company_tax)}', N8M))

        left_header_content: Any = co_bits
        if company_logo and Image is not None:
            try:
                logo_img = Image(company_logo, width=0.55 * inch, height=0.55 * inch, kind='proportional')
                left_header_content = Table(
                    [[logo_img, co_bits]],
                    colWidths=[0.65 * inch, 3.55 * inch],
                )
                left_header_content.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 0),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 2),
                    ('TOPPADDING', (0, 0), (-1, -1), 0),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
                ]))
            except Exception:
                left_header_content = co_bits

        meta_rows = [
            [Paragraph('<b>Invoice No.</b>', N8M), Paragraph(f':  {_xml_escape(str(billno))}', N8)],
            [Paragraph('<b>Invoice Date</b>', N8M), Paragraph(f':  {_xml_escape(bill_date_display)}', N8)],
        ]
        if bill_time:
            meta_rows.append([Paragraph('<b>Time</b>', N8M), Paragraph(f':  {_xml_escape(bill_time)}', N8)])
        if order_no:
            meta_rows.append([Paragraph('<b>PO / Reference</b>', N8M), Paragraph(f':  {_xml_escape(order_no)}', N8)])
        if created_by:
            meta_rows.append([Paragraph('<b>Created By</b>', N8M), Paragraph(f':  {_xml_escape(created_by)}', N8)])
        if prepared_by:
            meta_rows.append([Paragraph('<b>Prepared By</b>', N8M), Paragraph(f':  {_xml_escape(prepared_by)}', N8)])
        meta_tbl = Table(meta_rows, colWidths=[1.05 * inch, 2.0 * inch])
        meta_tbl.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 1),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ]))
        right_header = [Paragraph(_xml_escape(display_title), TITLE), Spacer(1, 4), meta_tbl]

        hdr_outer = Table([[left_header_content, right_header]], colWidths=[4.2 * inch, 3.2 * inch], hAlign='LEFT')
        hdr_outer.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))
        elements.append(hdr_outer)
        elements.append(Spacer(1, 6))
        rule = Table([['']], colWidths=[W], rowHeights=[2.2], hAlign='LEFT')
        rule.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), BLUE)]))
        elements.append(rule)
        elements.append(Spacer(1, 8))

        # 2. BILL TO
        bill_body_lines = []
        if customer_name:
            bill_body_lines.append(Paragraph(f'<b>{_xml_escape(customer_name)}</b>', N9))
        if customer_code:
            bill_body_lines.append(Paragraph(f'Code: {_xml_escape(customer_code)}', N8))
        if customer_address:
            bill_body_lines.append(Paragraph(_xml_escape(customer_address), N8))
        if cust_phone_display:
            bill_body_lines.append(Paragraph(f'Phone: {_xml_escape(cust_phone_display)}', N8))
        if not bill_body_lines:
            bill_body_lines.append(Paragraph('—', N8))

        # 3. ITEMS TABLE — define widths first so BILL TO matches exactly
        col_w = [0.45 * inch, 0.75 * inch, 2.55 * inch, 0.55 * inch, 0.5 * inch, 0.85 * inch, 0.75 * inch, 1.0 * inch]
        items_w = sum(col_w)

        bill_inner = Table(
            [[Paragraph('BILL TO', WHT_L)], [bill_body_lines]],
            colWidths=[items_w],
            hAlign='LEFT',
        )
        bill_inner.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), BLUE),
            ('BACKGROUND', (0, 1), (-1, 1), colors.white),
            ('BOX', (0, 0), (-1, -1), 0.6, BORDER),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (0, 0), 5),
            ('BOTTOMPADDING', (0, 0), (0, 0), 5),
            ('TOPPADDING', (0, 1), (0, 1), 6),
            ('BOTTOMPADDING', (0, 1), (0, 1), 6),
        ]))
        elements.append(bill_inner)
        elements.append(Spacer(1, 8))

        lines_tbl = Table(pt_rows, repeatRows=1, colWidths=col_w, hAlign='LEFT')
        lines_tbl.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), BLUE),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.4, BORDER),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, GRAY_ROW]),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), PAD + 1),
            ('BOTTOMPADDING', (0, 0), (-1, -1), PAD + 1),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ]))
        elements.append(lines_tbl)
        elements.append(Spacer(1, 8))

        # 4. AMOUNT IN WORDS + TOTALS
        words_bits = [
            Paragraph('<b>Amount in Words:</b>', N8M),
            Paragraph(_xml_escape(_amount_in_words(net_amount)), N9B),
        ]
        if remarks:
            words_bits.append(Spacer(1, 4))
            words_bits.append(Paragraph('<b>Remarks:</b>', N8M))
            words_bits.append(Paragraph(_xml_escape(remarks).replace('\n', '<br/>'), N8))

        SL = _s('sisl', fontSize=9, leading=11, alignment=TA_LEFT, textColor=MUTED)
        SR = _s('sisr', fontSize=9, leading=11, alignment=TA_RIGHT)
        GT_L = _s('sigtl', fontSize=10, leading=13, alignment=TA_LEFT, textColor=BLUE, fontName='Helvetica-Bold')
        GT_R = _s('sigtr', fontSize=10, leading=13, alignment=TA_RIGHT, textColor=BLUE, fontName='Helvetica-Bold')
        sum_rows = [
            [Paragraph('Sub Total', SL), Paragraph(f'{subtotal:,.2f}', SR)],
            [Paragraph('Discount', SL), Paragraph(f'{total_discount:,.2f}', SR)],
            [Paragraph('GRAND TOTAL', GT_L), Paragraph(f'{net_amount:,.2f}', GT_R)],
        ]
        # Equal label/value columns; box width matches last 3 item columns (Unit Price+Discount+Amount)
        sum_col = 1.15 * inch
        sum_tbl = Table(sum_rows, colWidths=[sum_col, sum_col])
        sum_tbl.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 0.7, BLUE),
            ('LINEBELOW', (0, 0), (-1, -2), 0.3, BORDER),
            ('LINEABOVE', (0, -1), (-1, -1), 1.0, BLUE),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#eef3fb')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))

        sum_w = sum_col * 2
        words_w = items_w - sum_w
        bottom_row = Table([[words_bits, sum_tbl]], colWidths=[words_w, sum_w], hAlign='LEFT')
        bottom_row.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ]))
        elements.append(bottom_row)

        printed_on = datetime.now().strftime('%d-%m-%Y %H:%M')
        prepared_name = (created_by or prepared_by or '').strip()
        prepared_date = (bill_date_display or '').strip()

        def _draw_page_footer(canv, pdf_doc):
            """Fixed footer: Prepared By / Received By / Authorized Signatory boxes + page meta."""
            x_left = pdf_doc.leftMargin
            x_right = pdf_doc.pagesize[0] - pdf_doc.rightMargin
            usable_w = x_right - x_left
            gap = 0.12 * inch
            box_w = (usable_w - 2 * gap) / 3.0
            box_h = 1.05 * inch
            box_y = 0.32 * inch
            titles = ('Prepared By', 'Received By', 'Authorized Signatory')
            extras = ('', '', '(Company Seal)')
            # Pre-fill Prepared By name (and date) from the bill creator / bill date.
            name_fills = (prepared_name, '', '')
            date_fills = (prepared_date, '', '')

            canv.saveState()
            for i, title in enumerate(titles):
                bx = x_left + i * (box_w + gap)
                canv.setStrokeColor(BORDER)
                canv.setFillColor(colors.white)
                canv.setLineWidth(0.6)
                canv.rect(bx, box_y, box_w, box_h, stroke=1, fill=1)

                canv.setFillColor(TEXT)
                canv.setFont('Helvetica-Bold', 8)
                canv.drawString(bx + 8, box_y + box_h - 14, title)

                canv.setStrokeColor(MUTED)
                canv.setLineWidth(0.4)
                line_y = box_y + box_h - 36
                canv.line(bx + 8, line_y, bx + box_w - 8, line_y)

                canv.setFillColor(MUTED)
                canv.setFont('Helvetica', 7.5)
                nm = name_fills[i]
                dt = date_fills[i]
                if nm:
                    canv.setFillColor(TEXT)
                    canv.setFont('Helvetica', 8)
                    canv.drawString(bx + 8, box_y + 28, f'Name: {nm}'[:48])
                else:
                    canv.drawString(bx + 8, box_y + 28, 'Name: ____________________')
                if dt:
                    canv.setFillColor(TEXT)
                    canv.setFont('Helvetica', 8)
                    canv.drawString(bx + 8, box_y + 14, f'Date: {dt}'[:48])
                else:
                    canv.setFillColor(MUTED)
                    canv.setFont('Helvetica', 7.5)
                    canv.drawString(bx + 8, box_y + 14, 'Date: ____________________')
                if extras[i]:
                    canv.setFillColor(MUTED)
                    canv.setFont('Helvetica', 7.5)
                    canv.drawString(bx + 8, box_y + 4, extras[i])

            meta_y = 0.12 * inch
            canv.setFillColor(MUTED)
            canv.setFont('Helvetica', 7)
            canv.drawString(x_left, meta_y, f'Page {pdf_doc.page}')
            right_txt = f'Printed On: {printed_on}'
            right_w = canv.stringWidth(right_txt, 'Helvetica', 7)
            canv.drawString(x_right - right_w, meta_y, right_txt)
            canv.restoreState()

        doc.build(elements, onFirstPage=_draw_page_footer, onLaterPages=_draw_page_footer)
        return buffer.getvalue()
    except Exception as e:
        logger.exception('Cashbilldup PDF generation failed: %s', e)
        return None

def _build_cashbilldup_raw_text(billno: int, header: Dict[str, Any], lines: List[Dict[str, Any]]) -> str:
    """Build plain text bill for dotmatrix/thermal direct printing."""
    row_width = 48
    out: List[str] = []
    out.append('CASH BILL DUPLICATE')
    out.append('-' * row_width)
    out.append(f'Bill No : {billno}')
    out.append(f"Date    : {_format_pdf_date(header.get('billdate'))}")
    out.append(f"Time    : {str(header.get('billtime') or '')}")
    out.append(f"Customer: {str(header.get('customername') or header.get('customercode') or '')}")
    out.append('-' * row_width)
    out.append('SL ITEMCODE   UOM   QTY     RATE      AMT')
    out.append('-' * row_width)
    for r in lines or []:
        sl = str(r.get('slno') or '')[:2].rjust(2)
        code = str(r.get('itemcode') or '')[:10].ljust(10)
        uom = str(r.get('unitofmeasurement') or '')[:4].ljust(4)
        qty = f"{float(r.get('quantity') or 0):.2f}".rjust(6)
        rate = f"{float(r.get('rate') or 0):.3f}".rjust(9)
        disc = float(r.get('itdisc') or 0)
        amount = float(r.get('quantity') or 0) * float(r.get('rate') or 0) - disc
        amt = f'{amount:.2f}'.rjust(8)
        out.append(f'{sl} {code} {uom} {qty} {rate} {amt}')
    out.append('-' * row_width)
    out.append(f"Discount : {float(header.get('discountamount') or 0):.3f}")
    out.append(f"Net Amt  : {float(header.get('netbillamount') or 0):.3f}")
    out.append('-' * row_width)
    out.append('')
    out.append('')
    return '\n'.join(out)

@bp.route('/sales/print', methods=['GET'])
def sales_print():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    billno_raw = (request.args.get('billno') or '').strip()
    billno, err = _parse_report_billno(billno_raw)
    if billno is None:
        return redirect(url_for('sales.sales_invoice'))
    return redirect(url_for('reports.crystal_reports_open_report', report_name='cashbilldup', billno=billno_raw))

@bp.route('/sales/print-complete', methods=['POST'])
def sales_print_complete():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    payload: Dict[str, Any] = request.get_json(silent=True) or {}
    billno, err = _parse_report_billno(payload.get('billno'))
    if billno is None:
        return jsonify({'success': False, 'error': err or 'Invalid billno'}, 400)
    location_code_int = _resolve_location_code()
    delete_sales_print_tables(billno, location_code_int)
    return jsonify({'success': True})

@bp.route('/reports/route-outstanding', methods=['GET'])
def route_outstanding():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    rows = get_route_outstanding_aging()
    return render_template('reports/route_outstanding.html', rows=rows)

@bp.route('/reports/route-outstanding/details', methods=['GET'])
def route_outstanding_details():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    bucket = (request.args.get('bucket') or 'all').strip()
    routecode = (request.args.get('routecode') or '').strip() or None
    rows = get_route_outstanding_details(routecode, bucket)
    bucket_labels = {'all': 'All Periods', '30': '0-30', '60': '31-60', '90': '61-90', '120': '91-120', '120p': '120+'}
    all_periods_url = url_for('reports.route_outstanding_details', bucket='all', routecode=routecode or '')
    empty_help = '<li><strong>Bucket 0-30</strong> shows only invoices whose <strong>bill date</strong> is within the last 30 days. If all outstanding for this route are older, try <a href="' + all_periods_url + '" style="color:#007bff;">All Periods</a>.</li><li>Route filter uses <strong>customers</strong> table route column linked to <strong>tblroute</strong> (e.g. routecode = ' + (routecode or '?') + ").</li><li>Only rows with <strong>balance &gt; 0</strong> and <strong>flag = 'B'</strong> are shown.</li>" if bucket == '30' else ''
    return render_template('reports/outstanding_details.html', report_type='route', bucket=bucket, bucket_label=bucket_labels.get(bucket, bucket), entity_type_label='Route', entity_label=routecode or '', back_url=url_for('reports.route_outstanding'), export_url=url_for('reports.route_outstanding_details_export', bucket=bucket, routecode=routecode or ''), rows=rows, empty_help=empty_help)

def _get_collection_comparison_data(num_months: int=6) -> List[Dict[str, Any]]:
    """Last N months: total invoice amount (tblsettlement flag='B', billdate, billamount) and total collection amount (tbltempsettlement flag='R', paiddate, paidamount). Returns list of {month_label, month_key, invoice_amount, collection_amount}."""
    settlement_table = _detect_table(['TBLSETTLEMENT', 'tblsettlement'])
    temp_table = _detect_table(['TBLTEMPSETTLEMENT', 'tbltempsettlement'])
    if not settlement_table or not temp_table:
        return []
    flag_s = _detect_column(settlement_table, ['FLAG', 'flag'])
    billdate_s = _detect_column(settlement_table, ['BILLDATE', 'BILL_DATE', 'billdate'])
    billamount_s = _detect_column(settlement_table, ['BILLAMOUNT', 'BILL_AMOUNT', 'billamount'])
    flag_t = _detect_column(temp_table, ['FLAG', 'flag'])
    paiddate_t = _detect_column(temp_table, ['PAIDDATE', 'PAID_DATE', 'paiddate'])
    paidamount_t = _detect_column(temp_table, ['PAIDAMOUNT', 'PAID_AMOUNT', 'paidamount'])
    if not all([flag_s, billdate_s, billamount_s]) or not all([flag_t, paiddate_t, paidamount_t]):
        return []
    n = max(1, min(int(num_months), 24))
    inv_sql = f"\n        SELECT TO_CHAR({settlement_table}.{billdate_s}, 'YYYY-MM') AS month_key,\n               NVL(SUM({settlement_table}.{billamount_s}), 0) AS invoice_amount\n        FROM {settlement_table}\n        WHERE {settlement_table}.{flag_s} = 'B'\n          AND {settlement_table}.{billdate_s} >= ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -:n_months)\n        GROUP BY TO_CHAR({settlement_table}.{billdate_s}, 'YYYY-MM')\n        ORDER BY 1\n    "
    coll_sql = f"\n        SELECT TO_CHAR({temp_table}.{paiddate_t}, 'YYYY-MM') AS month_key,\n               NVL(SUM({temp_table}.{paidamount_t}), 0) AS collection_amount\n        FROM {temp_table}\n        WHERE {temp_table}.{flag_t} = 'R'\n          AND {temp_table}.{paiddate_t} >= ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -:n_months)\n        GROUP BY TO_CHAR({temp_table}.{paiddate_t}, 'YYYY-MM')\n        ORDER BY 1\n    "
    try:
        inv_rows = _safe_rows(inv_sql, {'n_months': n}) or []
        coll_rows = _safe_rows(coll_sql, {'n_months': n}) or []
    except Exception as e:
        logger.exception('Collection comparison query error: %s', e)
        return []
    from datetime import date
    today = date.today()
    cur = today.replace(day=1)
    months = []
    for _ in range(n):
        months.append(cur.strftime('%Y-%m'))
        if cur.month == 1:
            cur = cur.replace(year=cur.year - 1, month=12)
        else:
            cur = cur.replace(month=cur.month - 1)
    months = list(reversed(months))
    inv_by_month = {str(r.get('MONTH_KEY') or r.get('month_key') or ''): float(r.get('INVOICE_AMOUNT') or r.get('invoice_amount') or 0) for r in inv_rows}
    coll_by_month = {str(r.get('MONTH_KEY') or r.get('month_key') or ''): float(r.get('COLLECTION_AMOUNT') or r.get('collection_amount') or 0) for r in coll_rows}
    result = []
    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    for mk in sorted(months):
        try:
            y, m = mk.split('-')
            label = f'{month_names[int(m) - 1]} {y}'
        except Exception:
            label = mk
        result.append({'month_key': mk, 'month_label': label, 'invoice_amount': inv_by_month.get(mk, 0.0), 'collection_amount': coll_by_month.get(mk, 0.0)})
    return result

@bp.route('/reports/collection-comparison', methods=['GET'])
def collection_comparison():
    """Collection Comparison: last 2 months – total invoice amount (tblsettlement flag B) and total collection amount (tbltempsettlement flag R)."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    rows = _get_collection_comparison_data(num_months=6)
    return render_template('reports/collection_comparison.html', rows=rows)

def _get_collection_report_data(billdate_from: Optional[str]=None, billdate_to: Optional[str]=None, paiddate_from: Optional[str]=None, paiddate_to: Optional[str]=None) -> Tuple[List[Dict[str, Any]], int, List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Collection report: bills from tblsettlement (flag='B') where BILLDATE between billdate_from and billdate_to;
    corresponding paid amount from tbltempsettlement (flag='R') linked by AGAINSTNO = BILLNO where PAIDDATE between paiddate_from and paiddate_to.
    SALESMANCODE, CUSTOMERCODE and EMPLOYEECODE are taken from tblsettlement only (the bill row, flag='B'), not from tbltempsettlement.
    Returns (detail rows, bills_count, summary_by_month, summary_by_salesman, summary_by_customer, summary_by_employee)."""
    settlement_table = _detect_table(['TBLSETTLEMENT', 'tblsettlement'])
    temp_table = _detect_table(['TBLTEMPSETTLEMENT', 'tbltempsettlement'])
    if not settlement_table or not temp_table:
        return ([], 0, [], [], [], [])
    flag_s = _detect_column(settlement_table, ['FLAG', 'flag'])
    billno_s = _detect_column(settlement_table, ['BILLNO', 'BILL_NO', 'billno'])
    billdate_s = _detect_column(settlement_table, ['BILLDATE', 'BILL_DATE', 'billdate'])
    billamount_s = _detect_column(settlement_table, ['BILLAMOUNT', 'BILL_AMOUNT', 'billamount'])
    cust_s = _detect_column(settlement_table, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'customercode'])
    sm_s = _detect_column(settlement_table, ['SALESMANCODE', 'SALESMAN_CODE', 'salesmancode'])
    emp_s = _detect_column(settlement_table, ['EMPLOYEECODE', 'EMPLOYEE_CODE', 'employeecode'])
    customer_table = _detect_table(['CUSTOMER', 'CUSTOMERS', 'customer', 'customers'])
    salesman_table = _detect_table(['SALESMAN', 'salesman', 'SALESMEN', 'salesmen'])
    employee_table = None
    emp_code_col = None
    emp_name_col = None
    for et in ['EMPLOYEE1', 'employee1', 'EMPLOYEE', 'employee']:
        resolved = _detect_table([et])
        if not resolved:
            continue
        ec = _detect_column(resolved, ['EMPLOYEECODE', 'EMPLOYEE_CODE', 'employeecode'])
        if ec:
            employee_table = resolved
            emp_code_col = ec
            emp_name_col = _detect_column(resolved, ['EMPLOYEENAME', 'EMPLOYEE_NAME', 'employeename'])
            break
    cust_code_c = _detect_column(customer_table, ['CUST_CODE', 'CUSTOMERCODE', 'CUSTOMER_CODE', 'CODE', 'code']) if customer_table else None
    cust_name_c = _detect_column(customer_table, ['CUST_NAME', 'CUSTOMERNAME', 'CUSTOMER_NAME', 'NAME', 'name']) if customer_table else None
    sm_code_s = _detect_column(salesman_table, ['SALESMANCODE', 'salesmancode', 'CODE', 'code']) if salesman_table else None
    sm_name_s = _detect_column(salesman_table, ['SALESMANNAME', 'salesmanname', 'NAME', 'name']) if salesman_table else None
    customer_join = ''
    salesman_join = ''
    employee_join = ''
    customer_name_sql = 'NULL AS customername'
    salesman_name_sql = 'NULL AS salesmanname'
    employee_name_sql = 'NULL AS employeename'
    customer_group = ''
    salesman_group = ''
    employee_group = ''
    if customer_table and cust_s and cust_code_c and cust_name_c:
        customer_join = f' LEFT JOIN {customer_table} c ON TRIM(TO_CHAR(s.{cust_s})) = TRIM(TO_CHAR(c.{cust_code_c}))'
        customer_name_sql = f'c.{cust_name_c} AS customername'
        customer_group = f', c.{cust_name_c}'
    if salesman_table and sm_s and sm_code_s and sm_name_s:
        salesman_join = f' LEFT JOIN {salesman_table} sm ON TRIM(TO_CHAR(s.{sm_s})) = TRIM(TO_CHAR(sm.{sm_code_s}))'
        salesman_name_sql = f'sm.{sm_name_s} AS salesmanname'
        salesman_group = f', sm.{sm_name_s}'
    if employee_table and emp_s and emp_code_col:
        employee_join = f' LEFT JOIN {employee_table} emp ON TRIM(TO_CHAR(s.{emp_s})) = TRIM(TO_CHAR(emp.{emp_code_col}))'
        if emp_name_col:
            employee_name_sql = f'emp.{emp_name_col} AS employeename'
            employee_group = f', emp.{emp_name_col}'
    flag_t = _detect_column(temp_table, ['FLAG', 'flag'])
    againstno_t = _detect_column(temp_table, ['AGAINSTNO', 'AGAINST_NO', 'againstno'])
    paiddate_t = _detect_column(temp_table, ['PAIDDATE', 'PAID_DATE', 'paiddate'])
    paidamount_t = _detect_column(temp_table, ['PAIDAMOUNT', 'PAID_AMOUNT', 'paidamount'])
    if not all([flag_s, billno_s, billdate_s, billamount_s]) or not all([flag_t, againstno_t, paiddate_t, paidamount_t]):
        return ([], 0, [], [], [], [])
    if not billdate_from or not billdate_to or (not paiddate_from) or (not paiddate_to):
        return ([], 0, [], [], [], [])
    billdate_from = str(billdate_from).strip()[:10]
    billdate_to = str(billdate_to).strip()[:10]
    paiddate_from = str(paiddate_from).strip()[:10]
    paiddate_to = str(paiddate_to).strip()[:10]
    params = {'billdate_from': billdate_from, 'billdate_to': billdate_to, 'paiddate_from': paiddate_from, 'paiddate_to': paiddate_to}
    bills_count = 0
    try:
        count_sql = f"\n            SELECT COUNT(*) AS cnt FROM {settlement_table} s\n            WHERE s.{flag_s} = 'B'\n              AND TRUNC(s.{billdate_s}) >= TO_DATE(:billdate_from, 'YYYY-MM-DD')\n              AND TRUNC(s.{billdate_s}) <= TO_DATE(:billdate_to, 'YYYY-MM-DD')\n        "
        count_rows = _safe_rows(count_sql, {'billdate_from': billdate_from, 'billdate_to': billdate_to}) or []
        if count_rows:
            bills_count = int(count_rows[0].get('CNT') or count_rows[0].get('cnt') or 0)
    except Exception as e:
        logger.exception('Collection report count query error: %s', e)
    sql = f"\n        SELECT s.{billno_s} AS billno,\n               s.{billdate_s} AS billdate,\n               {customer_name_sql},\n               {salesman_name_sql},\n               {employee_name_sql},\n               NVL(s.{billamount_s}, 0) AS billamount,\n               NVL(SUM(t.{paidamount_t}), 0) AS paid_amount\n               {(f', s.{cust_s} AS customer_code' if cust_s else '')}\n               {(f', s.{sm_s} AS salesman_code' if sm_s else '')}\n               {(f', s.{emp_s} AS employee_code' if emp_s else '')}\n        FROM {settlement_table} s\n        {customer_join}\n        {salesman_join}\n        {employee_join}\n        LEFT JOIN {temp_table} t ON TRIM(TO_CHAR(t.{againstno_t})) = TRIM(TO_CHAR(s.{billno_s}))\n           AND t.{flag_t} = 'R'\n           AND TRUNC(t.{paiddate_t}) >= TO_DATE(:paiddate_from, 'YYYY-MM-DD')\n           AND TRUNC(t.{paiddate_t}) <= TO_DATE(:paiddate_to, 'YYYY-MM-DD')\n        WHERE s.{flag_s} = 'B'\n          AND TRUNC(s.{billdate_s}) >= TO_DATE(:billdate_from, 'YYYY-MM-DD')\n          AND TRUNC(s.{billdate_s}) <= TO_DATE(:billdate_to, 'YYYY-MM-DD')\n        GROUP BY s.{billno_s}, s.{billdate_s}, s.{billamount_s}\n               {(f', s.{cust_s}' if cust_s else '')}\n               {(f', s.{sm_s}' if sm_s else '')}\n               {(f', s.{emp_s}' if emp_s else '')}\n               {customer_group}\n               {salesman_group}\n               {employee_group}\n        ORDER BY s.{billdate_s}, s.{billno_s}\n    "
    try:
        rows = _safe_rows(sql, params) or []
        out = []
        month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        for r in rows:
            billno = r.get('BILLNO') or r.get('billno')
            billdate_raw = r.get('BILLDATE') or r.get('billdate')
            if hasattr(billdate_raw, 'strftime'):
                billdate = billdate_raw.strftime('%Y-%m-%d')
            elif billdate_raw:
                billdate = str(billdate_raw)[:10]
            else:
                billdate = ''
            billamount = float(r.get('BILLAMOUNT') or r.get('billamount') or 0)
            paid_amount = float(r.get('PAID_AMOUNT') or r.get('paid_amount') or 0)
            customer_code = r.get('CUSTOMER_CODE') or r.get('customer_code')
            salesman_code = r.get('SALESMAN_CODE') or r.get('salesman_code')
            employee_code = r.get('EMPLOYEE_CODE') or r.get('employee_code')
            customer_name = r.get('CUSTOMERNAME') or r.get('customername')
            salesman_name = r.get('SALESMANNAME') or r.get('salesmanname')
            employee_name = r.get('EMPLOYEENAME') or r.get('employeename')
            out.append({'billno': billno, 'billdate': billdate, 'customername': str(customer_name).strip() if customer_name is not None else '', 'salesmanname': str(salesman_name).strip() if salesman_name is not None else '', 'employeename': str(employee_name).strip() if employee_name is not None else '', 'billamount': billamount, 'paid_amount': paid_amount, 'customer_code': str(customer_code).strip() if customer_code is not None else '', 'salesman_code': str(salesman_code).strip() if salesman_code is not None else '', 'employee_code': str(employee_code).strip() if employee_code is not None else ''})
        by_month: Dict[str, Dict[str, Any]] = {}
        by_salesman: Dict[str, Dict[str, Any]] = {}
        by_customer: Dict[str, Dict[str, Any]] = {}
        by_employee: Dict[str, Dict[str, Any]] = {}
        for o in out:
            if o['billdate']:
                mk = o['billdate'][:7]
                if mk not in by_month:
                    try:
                        y, m = mk.split('-')
                        by_month[mk] = {'month_key': mk, 'month_label': f'{month_names[int(m) - 1]} {y}', 'billamount': 0.0, 'paid_amount': 0.0}
                    except Exception:
                        by_month[mk] = {'month_key': mk, 'month_label': mk, 'billamount': 0.0, 'paid_amount': 0.0}
                by_month[mk]['billamount'] += o['billamount']
                by_month[mk]['paid_amount'] += o['paid_amount']
            sm = (str(o.get('salesman_code') or '') or '').strip() or '(Blank)'
            if sm not in by_salesman:
                by_salesman[sm] = {'salesman_code': sm, 'salesmanname': (o.get('salesmanname') or '').strip() or '', 'billamount': 0.0, 'paid_amount': 0.0}
            by_salesman[sm]['billamount'] += o['billamount']
            by_salesman[sm]['paid_amount'] += o['paid_amount']
            cust = (str(o.get('customer_code') or '') or '').strip() or '(Blank)'
            if cust not in by_customer:
                by_customer[cust] = {'customer_code': cust, 'customername': (o.get('customername') or '').strip() or '', 'billamount': 0.0, 'paid_amount': 0.0}
            by_customer[cust]['billamount'] += o['billamount']
            by_customer[cust]['paid_amount'] += o['paid_amount']
            emp = (str(o.get('employee_code') or '') or '').strip() or '(Blank)'
            if emp not in by_employee:
                by_employee[emp] = {'employee_code': emp, 'employeename': (o.get('employeename') or '').strip() or '', 'billamount': 0.0, 'paid_amount': 0.0}
            by_employee[emp]['billamount'] += o['billamount']
            by_employee[emp]['paid_amount'] += o['paid_amount']
        summary_by_month = [{'month_key': k, 'month_label': v['month_label'], 'billamount': v['billamount'], 'paid_amount': v['paid_amount'], 'variance': v['billamount'] - v['paid_amount']} for k, v in sorted(by_month.items())]
        summary_by_salesman = [{'salesman_code': k, 'salesmanname': v['salesmanname'], 'billamount': v['billamount'], 'paid_amount': v['paid_amount'], 'variance': v['billamount'] - v['paid_amount']} for k, v in sorted(by_salesman.items())]
        summary_by_customer = [{'customer_code': k, 'customername': v['customername'], 'billamount': v['billamount'], 'paid_amount': v['paid_amount'], 'variance': v['billamount'] - v['paid_amount']} for k, v in sorted(by_customer.items())]
        summary_by_employee = [{'employee_code': k, 'employeename': v['employeename'], 'billamount': v['billamount'], 'paid_amount': v['paid_amount'], 'variance': v['billamount'] - v['paid_amount']} for k, v in sorted(by_employee.items())]
        return (out, bills_count, summary_by_month, summary_by_salesman, summary_by_customer, summary_by_employee)
    except Exception as e:
        logger.exception('Collection report query error: %s', e)
        return ([], bills_count, [], [], [], [])

def _get_collection_report_diagnostic(billdate_from: str, billdate_to: str, paiddate_from: str, paiddate_to: str) -> Dict[str, Any]:
    """When bills exist but no payment matches: count temp payments in paid date range and return sample AGAINSTNO / BILLNO for debugging."""
    out = {'temp_count': 0, 'sample_againstno': [], 'sample_billno': []}
    settlement_table = _detect_table(['TBLSETTLEMENT', 'tblsettlement'])
    temp_table = _detect_table(['TBLTEMPSETTLEMENT', 'tbltempsettlement'])
    if not settlement_table or not temp_table:
        return out
    flag_s = _detect_column(settlement_table, ['FLAG', 'flag'])
    billno_s = _detect_column(settlement_table, ['BILLNO', 'BILL_NO', 'billno'])
    billdate_s = _detect_column(settlement_table, ['BILLDATE', 'BILL_DATE', 'billdate'])
    flag_t = _detect_column(temp_table, ['FLAG', 'flag'])
    againstno_t = _detect_column(temp_table, ['AGAINSTNO', 'AGAINST_NO', 'againstno'])
    paiddate_t = _detect_column(temp_table, ['PAIDDATE', 'PAID_DATE', 'paiddate'])
    if not all([flag_s, billno_s, billdate_s]) or not all([flag_t, againstno_t, paiddate_t]):
        return out
    params_temp = {'paiddate_from': paiddate_from, 'paiddate_to': paiddate_to}
    params_sett = {'billdate_from': billdate_from, 'billdate_to': billdate_to}
    try:
        count_sql = f"\n            SELECT COUNT(*) AS cnt FROM {temp_table}\n            WHERE {flag_t} = 'R'\n              AND TRUNC({paiddate_t}) >= TO_DATE(:paiddate_from, 'YYYY-MM-DD')\n              AND TRUNC({paiddate_t}) <= TO_DATE(:paiddate_to, 'YYYY-MM-DD')\n        "
        r = (_safe_rows(count_sql, params_temp) or [{}])[0]
        out['temp_count'] = int(r.get('CNT') or r.get('cnt') or 0)
        sample_temp_sql = f"\n            SELECT * FROM (\n                SELECT t.{againstno_t} AS againstno FROM {temp_table} t\n                WHERE t.{flag_t} = 'R'\n                  AND TRUNC(t.{paiddate_t}) >= TO_DATE(:paiddate_from, 'YYYY-MM-DD')\n                  AND TRUNC(t.{paiddate_t}) <= TO_DATE(:paiddate_to, 'YYYY-MM-DD')\n                  AND ROWNUM <= 10\n            )\n        "
        temp_rows = _safe_rows(sample_temp_sql, params_temp) or []
        out['sample_againstno'] = [str(x.get('AGAINSTNO') or x.get('againstno') or '').strip() for x in temp_rows if (x.get('AGAINSTNO') or x.get('againstno')) is not None]
        sample_sett_sql = f"\n            SELECT * FROM (\n                SELECT s.{billno_s} AS billno FROM {settlement_table} s\n                WHERE s.{flag_s} = 'B'\n                  AND TRUNC(s.{billdate_s}) >= TO_DATE(:billdate_from, 'YYYY-MM-DD')\n                  AND TRUNC(s.{billdate_s}) <= TO_DATE(:billdate_to, 'YYYY-MM-DD')\n                  AND ROWNUM <= 10\n            )\n        "
        sett_rows = _safe_rows(sample_sett_sql, params_sett) or []
        out['sample_billno'] = [str(x.get('BILLNO') or x.get('billno') or '').strip() for x in sett_rows if (x.get('BILLNO') or x.get('billno')) is not None]
    except Exception as e:
        logger.exception('Collection report diagnostic error: %s', e)
    return out

@bp.route('/reports/collection-report', methods=['GET'])
def collection_report():
    """Collection report: bill amount vs paid amount. Filter 1: BILLDATE between dates. Filter 2: PAIDDATE between dates. Link by AGAINSTNO = BILLNO."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    billdate_from = (request.args.get('billdate_from') or '').strip() or None
    billdate_to = (request.args.get('billdate_to') or '').strip() or None
    paiddate_from = (request.args.get('paiddate_from') or '').strip() or None
    paiddate_to = (request.args.get('paiddate_to') or '').strip() or None
    pending_only = request.args.get('pending_only') in ('1', 'on', 'yes', 'true')
    rows = []
    bills_in_range_count = 0
    summary_by_month = []
    summary_by_salesman = []
    summary_by_customer = []
    summary_by_employee = []
    diagnostic = {}
    if billdate_from and billdate_to and paiddate_from and paiddate_to:
        rows, bills_in_range_count, summary_by_month, summary_by_salesman, summary_by_customer, summary_by_employee = _get_collection_report_data(billdate_from=billdate_from, billdate_to=billdate_to, paiddate_from=paiddate_from, paiddate_to=paiddate_to)
        if pending_only and rows:
            rows = [r for r in rows if float(r.get('billamount') or 0) - float(r.get('paid_amount') or 0) != 0]
            month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
            by_month = {}
            by_salesman = {}
            by_customer = {}
            by_employee = {}
            for o in rows:
                if o.get('billdate'):
                    mk = o['billdate'][:7]
                    if mk not in by_month:
                        try:
                            y, m = mk.split('-')
                            by_month[mk] = {'month_key': mk, 'month_label': f'{month_names[int(m) - 1]} {y}', 'billamount': 0.0, 'paid_amount': 0.0}
                        except Exception:
                            by_month[mk] = {'month_key': mk, 'month_label': mk, 'billamount': 0.0, 'paid_amount': 0.0}
                    by_month[mk]['billamount'] += float(o.get('billamount') or 0)
                    by_month[mk]['paid_amount'] += float(o.get('paid_amount') or 0)
                sm = (str(o.get('salesman_code') or '') or '').strip() or '(Blank)'
                if sm not in by_salesman:
                    by_salesman[sm] = {'salesman_code': sm, 'salesmanname': (o.get('salesmanname') or '').strip() or '', 'billamount': 0.0, 'paid_amount': 0.0}
                by_salesman[sm]['billamount'] += float(o.get('billamount') or 0)
                by_salesman[sm]['paid_amount'] += float(o.get('paid_amount') or 0)
                cust = (str(o.get('customer_code') or '') or '').strip() or '(Blank)'
                if cust not in by_customer:
                    by_customer[cust] = {'customer_code': cust, 'customername': (o.get('customername') or '').strip() or '', 'billamount': 0.0, 'paid_amount': 0.0}
                by_customer[cust]['billamount'] += float(o.get('billamount') or 0)
                by_customer[cust]['paid_amount'] += float(o.get('paid_amount') or 0)
                emp = (str(o.get('employee_code') or '') or '').strip() or '(Blank)'
                if emp not in by_employee:
                    by_employee[emp] = {'employee_code': emp, 'employeename': (o.get('employeename') or '').strip() or '', 'billamount': 0.0, 'paid_amount': 0.0}
                by_employee[emp]['billamount'] += float(o.get('billamount') or 0)
                by_employee[emp]['paid_amount'] += float(o.get('paid_amount') or 0)
            summary_by_month = [{'month_key': k, 'month_label': v['month_label'], 'billamount': v['billamount'], 'paid_amount': v['paid_amount'], 'variance': v['billamount'] - v['paid_amount']} for k, v in sorted(by_month.items())]
            summary_by_salesman = [{'salesman_code': k, 'salesmanname': v['salesmanname'], 'billamount': v['billamount'], 'paid_amount': v['paid_amount'], 'variance': v['billamount'] - v['paid_amount']} for k, v in sorted(by_salesman.items())]
            summary_by_customer = [{'customer_code': k, 'customername': v['customername'], 'billamount': v['billamount'], 'paid_amount': v['paid_amount'], 'variance': v['billamount'] - v['paid_amount']} for k, v in sorted(by_customer.items())]
            summary_by_employee = [{'employee_code': k, 'employeename': v['employeename'], 'billamount': v['billamount'], 'paid_amount': v['paid_amount'], 'variance': v['billamount'] - v['paid_amount']} for k, v in sorted(by_employee.items())]
        if bills_in_range_count > 0 and (not rows):
            diagnostic = _get_collection_report_diagnostic(billdate_from=billdate_from, billdate_to=billdate_to, paiddate_from=paiddate_from, paiddate_to=paiddate_to)
    return render_template('reports/collection_report.html', rows=rows, bills_in_range_count=bills_in_range_count, summary_by_month=summary_by_month, summary_by_salesman=summary_by_salesman, summary_by_customer=summary_by_customer, summary_by_employee=summary_by_employee, diagnostic=diagnostic, billdate_from=billdate_from or '', billdate_to=billdate_to or '', paiddate_from=paiddate_from or '', paiddate_to=paiddate_to or '', pending_only=pending_only)
_LPO_DETAILS_RESET_NO = 1

def _default_purchase_report_date_range(date_from: str, date_to: str) -> Tuple[str, str]:
    """Blank range → month-to-date so Purchase Details opens with useful rows."""
    df = (date_from or '').strip()
    dt = (date_to or '').strip()
    if not df and not dt:
        today = datetime.now()
        return (today.replace(day=1).strftime('%Y-%m-%d'), today.strftime('%Y-%m-%d'))
    return (df, dt)

def _get_purchase_detail_rows_from_lpo(date_from: Optional[str]=None, date_to: Optional[str]=None, lpo_no: Optional[Any]=None, supplier_code: Optional[int]=None, item_code: Optional[int]=None) -> List[Dict[str, Any]]:
    """Saved LPO header + line detail rows."""
    hdr = _detect_table(['LPOHDR', 'lpohdr'])
    dtl = _detect_table(['LPODTL', 'lpodtl'])
    if not hdr or not dtl:
        return []
    h_no = _detect_column(hdr, ['LPONO', 'LPO_NO', 'lpono'])
    h_date = _detect_column(hdr, ['LPODATE', 'LPO_DATE', 'lpodate'])
    h_sup = _detect_column(hdr, ['SUPPLIERCODE', 'SUPPLIER_CODE', 'suppliercode'])
    h_amt = _detect_column(hdr, ['LPOAMOUNT', 'LPO_AMOUNT', 'lpoamount'])
    h_disc = _detect_column(hdr, ['DISCOUNT', 'discount'])
    h_other = _detect_column(hdr, ['OTHERCHARGE', 'OTHER_CHARGE', 'othercharge'])
    h_rem = _detect_column(hdr, ['REMARKS', 'remarks'])
    h_loc = _detect_column(hdr, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    h_reset = _detect_column(hdr, ['RESETNO', 'RESET_NO', 'resetno'])
    h_del = _detect_column(hdr, ['DELFLAG', 'DEL_FLAG', 'delflag'])
    d_lpo = _detect_column(dtl, ['LPONO', 'LPO_NO', 'lpono'])
    d_lineno = _detect_column(dtl, ['LINENO', 'LINE_NO', 'lineno', 'SLNO', 'slno'])
    d_item = _detect_column(dtl, ['ITEMCODE', 'ITEM_CODE', 'itemcode'])
    d_barcode = _detect_column(dtl, ['MANUFACTURERID', 'MANUFACTURER_ID', 'manufacturerid', 'BARCODE', 'barcode'])
    d_qty = _detect_column(dtl, ['QUANTITY', 'quantity'])
    d_rate = _detect_column(dtl, ['RATE', 'rate'])
    d_bonus = _detect_column(dtl, ['BONUS', 'bonus'])
    d_ldisc = _detect_column(dtl, ['DISCOUNT', 'discount'])
    d_amt = _detect_column(dtl, ['AMOUNT', 'amount'])
    d_foc = _detect_column(dtl, ['FOC', 'foc'])
    d_other = _detect_column(dtl, ['OTHERCHARGE', 'OTHER_CHARGE', 'othercharge'])
    d_land = _detect_column(dtl, ['LANDINGCOST', 'LANDING_COST', 'landingcost'])
    d_uom = _detect_column(dtl, ['UNITOFMEASUREMENT', 'UNIT_OF_MEASUREMENT', 'unitofmeasurement', 'UOM', 'uom'])
    d_base = _detect_column(dtl, ['BASEQTY', 'BASE_QTY', 'baseqty'])
    d_name = _detect_column(dtl, ['ITEMNAME', 'ITEM_NAME', 'itemname'])
    d_loc = _detect_column(dtl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    d_reset = _detect_column(dtl, ['RESETNO', 'RESET_NO', 'resetno'])
    if not h_no or not h_date or (not d_lpo) or (not d_item):
        return []
    on_parts = [f'h.{h_no} = d.{d_lpo}']
    if h_loc and d_loc:
        on_parts.append(f'h.{h_loc} = d.{d_loc}')
    if h_reset and d_reset:
        on_parts.append(f'NVL(h.{h_reset}, 0) = NVL(d.{d_reset}, 0)')
    where_parts: List[str] = []
    params: Dict[str, Any] = {}
    if h_loc:
        where_parts.append(f'h.{h_loc} = :loc')
        params['loc'] = _resolve_location_code()
    if h_reset:
        where_parts.append(f'NVL(h.{h_reset}, :rn) = :rn')
        params['rn'] = _LPO_DETAILS_RESET_NO
    if h_del:
        where_parts.append(f"NVL(h.{h_del}, 'N') = 'N'")
    if lpo_no is not None and lpono_is_valid(lpo_no):
        where_parts.append(f'h.{h_no} = :lpo')
        params['lpo'] = coerce_lpono(lpo_no)
    if date_from:
        where_parts.append(f"TRUNC(h.{h_date}) >= TO_DATE(:df, 'YYYY-MM-DD')")
        params['df'] = date_from
    if date_to:
        where_parts.append(f"TRUNC(h.{h_date}) <= TO_DATE(:dt, 'YYYY-MM-DD')")
        params['dt'] = date_to
    if supplier_code is not None and supplier_code > 0 and h_sup:
        where_parts.append(f'h.{h_sup} = :sup')
        params['sup'] = int(supplier_code)
    if item_code:
        where_parts.append(f'd.{d_item} = :item_code')
        params['item_code'] = int(item_code)
    sup_tbl = _detect_table(['SUPPLIER', 'supplier', 'SUPPLIERS'])
    sup_code_col = _detect_column(sup_tbl, ['SUPPLIERCODE', 'SUPPLIER_CODE', 'suppliercode']) if sup_tbl else None
    sup_name_col = _detect_column(sup_tbl, ['SUPPLIERNAME', 'SUPPLIER_NAME', 'suppliername']) if sup_tbl else None
    join_sup = ''
    sup_name_expr = "''"
    if sup_tbl and h_sup and sup_code_col and sup_name_col:
        join_sup = f' LEFT JOIN {sup_tbl} s ON h.{h_sup} = s.{sup_code_col} '
        sup_name_expr = f"NVL(s.{sup_name_col}, '')"
    im = _detect_table(['ITEMMASTER', 'itemmaster'])
    im_item = _detect_column(im, ['ITEMCODE', 'ITEM_CODE', 'itemcode']) if im else None
    im_name = _detect_column(im, ['ITEMNAME', 'ITEM_NAME', 'itemname']) if im else None
    im_loc = _detect_column(im, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode']) if im else None
    join_im = ''
    item_name_expr = f"{(f'd.{d_name}' if d_name else 'CAST(NULL AS VARCHAR2(1))')}"
    if im and im_item and im_name:
        im_on = f'd.{d_item} = im.{im_item}'
        if im_loc and h_loc:
            im_on += f' AND im.{im_loc} = h.{h_loc}'
        join_im = f' LEFT JOIN {im} im ON {im_on} '
        if d_name:
            item_name_expr = f"NVL(NULLIF(TRIM(d.{d_name}), ''), im.{im_name})"
        else:
            item_name_expr = f"NVL(im.{im_name}, '')"
    pa_tbl = _detect_table(['PURCHASE_APPROVAL_TXN', 'purchase_approval_txn'])
    pa_doc = _detect_column(pa_tbl, ['DOC_NO', 'DOCNO', 'doc_no']) if pa_tbl else None
    pa_type = _detect_column(pa_tbl, ['DOC_TYPE', 'DOCTYPE', 'doc_type']) if pa_tbl else None
    pa_loc_c = _detect_column(pa_tbl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode']) if pa_tbl else None
    pa_stat = _detect_column(pa_tbl, ['STATUS', 'status']) if pa_tbl else None
    appr_expr = 'CAST(NULL AS VARCHAR2(120))'
    if pa_tbl and pa_doc and pa_stat and h_no:
        type_pred = f"UPPER(NVL(pa2.{pa_type}, '')) = 'LPO' AND " if pa_type else ''
        loc_pred = f'pa2.{pa_loc_c} = h.{h_loc} AND ' if (pa_loc_c and h_loc) else ''
        appr_expr = (
            f"(SELECT NVL(pa2.{pa_stat}, '') FROM {pa_tbl} pa2 "
            f"WHERE {type_pred}{loc_pred}TO_CHAR(pa2.{pa_doc}) = TO_CHAR(h.{h_no}) AND ROWNUM = 1)"
        )
    sl_expr = f'd.{d_lineno}' if d_lineno else '1'
    rem_expr = f'h.{h_rem}' if h_rem else "CAST('' AS VARCHAR2(1))"
    q = f"""
        SELECT
            h.{h_no} AS lpono,
            h.{h_date} AS lpodate,
            {(f'h.{h_sup}' if h_sup else 'CAST(NULL AS NUMBER)')} AS suppliercode,
            {sup_name_expr} AS suppliername,
            NVL({(f'h.{h_amt}' if h_amt else '0')}, 0) AS lpoamount,
            NVL({(f'h.{h_disc}' if h_disc else '0')}, 0) AS hdr_discount,
            NVL({(f'h.{h_other}' if h_other else '0')}, 0) AS hdr_othercharge,
            {rem_expr} AS hdr_remarks,
            {appr_expr} AS approval_status,
            {sl_expr} AS slno,
            d.{d_item} AS itemcode,
            {(f"NVL(d.{d_barcode}, '')" if d_barcode else "CAST('' AS VARCHAR2(1))")} AS barcode,
            {item_name_expr} AS itemname,
            {(f"NVL(d.{d_uom}, '')" if d_uom else "CAST('' AS VARCHAR2(1))")} AS uom,
            NVL({(f'd.{d_qty}' if d_qty else '0')}, 0) AS quantity,
            NVL({(f'd.{d_rate}' if d_rate else '0')}, 0) AS rate,
            NVL({(f'd.{d_bonus}' if d_bonus else '0')}, 0) AS bonus,
            NVL({(f'd.{d_ldisc}' if d_ldisc else '0')}, 0) AS linediscount,
            NVL({(f'd.{d_amt}' if d_amt else '0')}, 0) AS amount,
            NVL({(f'd.{d_base}' if d_base else '0')}, 0) AS baseqty,
            {(f'd.{d_foc}' if d_foc else '0')} AS foc_raw,
            NVL({(f'd.{d_other}' if d_other else '0')}, 0) AS line_othercharge,
            NVL({(f'd.{d_land}' if d_land else '0')}, 0) AS landingcost
        FROM {hdr} h
        INNER JOIN {dtl} d ON {' AND '.join(on_parts)}
        {join_sup}
        {join_im}
        WHERE {(' AND '.join(where_parts) if where_parts else '1=1')}
        ORDER BY h.{h_no} DESC, {sl_expr} ASC
    """
    try:
        return _safe_rows(q, params) or []
    except Exception as e:
        logger.exception('Purchase details LPO query failed: %s', e)
        if appr_expr != 'CAST(NULL AS VARCHAR2(120))':
            q2 = q.replace(appr_expr, 'CAST(NULL AS VARCHAR2(120))')
            try:
                return _safe_rows(q2, params) or []
            except Exception as e2:
                logger.exception('Purchase details LPO retry failed: %s', e2)
        return []

def _get_grn_detail_rows(date_from: Optional[str]=None, date_to: Optional[str]=None, receipt_no: Optional[Any]=None, lpo_no: Optional[Any]=None, supplier_code: Optional[int]=None, item_code: Optional[int]=None) -> List[Dict[str, Any]]:
    """GRN (RECEIPTHDR/RECEIPTDTL) line details."""
    hdr = _detect_table(['RECEIPTHDR', 'receipthdr'])
    dtl = _detect_table(['RECEIPTDTL', 'receiptdtl'])
    if not hdr or not dtl:
        return []
    h_no = _detect_column(hdr, ['RECEIPTNO', 'RECEIPT_NO', 'receiptno'])
    h_date = _detect_column(hdr, ['RECEIPTDATE', 'RECEIPT_DATE', 'receiptdate'])
    h_sup = _detect_column(hdr, ['SUPPLIERCODE', 'SUPPLIER_CODE', 'suppliercode'])
    h_amt = _detect_column(hdr, ['INVOICEAMOUNT', 'INVOICE_AMOUNT', 'invoiceamount', 'RECEIPTAMOUNT', 'receiptamount', 'NETAMOUNT', 'GRNAMOUNT'])
    h_disc = _detect_column(hdr, ['DISCOUNT', 'discount'])
    h_other = _detect_column(hdr, ['OTHERCHARGE', 'OTHER_CHARGE', 'othercharge'])
    h_rem = _detect_column(hdr, ['REMARKS', 'remarks'])
    h_lpo = _detect_column(hdr, ['LPONO', 'LPO_NO', 'lpono'])
    h_inv = _detect_column(hdr, ['INVOICENO', 'INVOICE_NO', 'invoiceno'])
    h_inv_date = _detect_column(hdr, ['INVOICEDATE', 'INVOICE_DATE', 'invoicedate'])
    h_post = _detect_column(hdr, ['POSTINGDATE', 'POSTING_DATE', 'postingdate'])
    h_wh = _detect_column(hdr, ['WAREHOUSE_ID', 'warehouse_id'])
    h_inv_posted = _detect_column(hdr, ['INVENTORY_POSTED', 'INVENTORY_POSTED_FLAG', 'inventory_posted'])
    h_loc = _detect_column(hdr, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    h_reset = _detect_column(hdr, ['RESETNO', 'RESET_NO', 'resetno'])
    h_del = _detect_column(hdr, ['DELFLAG', 'DEL_FLAG', 'delflag'])
    d_no = _detect_column(dtl, ['RECEIPTNO', 'RECEIPT_NO', 'receiptno'])
    d_lineno = _detect_column(dtl, ['LINENO', 'LINE_NO', 'lineno', 'SLNO', 'slno'])
    d_item = _detect_column(dtl, ['ITEMCODE', 'ITEM_CODE', 'itemcode'])
    d_barcode = _detect_column(dtl, ['MANUFACTURERID', 'MANUFACTURER_ID', 'manufacturerid', 'BARCODE', 'barcode'])
    d_qty = _detect_column(dtl, ['QUANTITY', 'QTY', 'quantity', 'RECEIPTQTY'])
    d_rate = _detect_column(dtl, ['RATE', 'rate', 'COSTPRICE'])
    d_bonus = _detect_column(dtl, ['BONUS', 'bonus'])
    d_ldisc = _detect_column(dtl, ['DISCOUNT', 'discount', 'ITDISC', 'LINEDISCOUNT'])
    d_amt = _detect_column(dtl, ['AMOUNT', 'LINEAMOUNT', 'lineamount', 'NETAMOUNT'])
    d_foc = _detect_column(dtl, ['FOC', 'foc'])
    d_other = _detect_column(dtl, ['OTHERCHARGE', 'OTHER_CHARGE', 'othercharge'])
    d_land = _detect_column(dtl, ['LANDINGCOST', 'LANDING_COST', 'landingcost'])
    d_uom = _detect_column(dtl, ['UNITOFMEASUREMENT', 'UNIT_OF_MEASUREMENT', 'unitofmeasurement', 'UOM', 'uom'])
    d_base = _detect_column(dtl, ['BASEQTY', 'BASE_QTY', 'baseqty'])
    d_name = _detect_column(dtl, ['ITEMNAME', 'ITEM_NAME', 'itemname'])
    d_batch = _detect_column(dtl, ['BATCH_NO', 'BATCHNO', 'batch_no', 'batchno'])
    d_mfg = _detect_column(dtl, ['MFG_DATE', 'MFGDATE', 'mfg_date', 'mfgdate'])
    d_exp = _detect_column(dtl, ['EXPIRY_DATE', 'EXPIRYDATE', 'expiry_date', 'expirydate'])
    d_wh = _detect_column(dtl, ['WAREHOUSE_ID', 'warehouse_id'])
    d_loc = _detect_column(dtl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    d_reset = _detect_column(dtl, ['RESETNO', 'RESET_NO', 'resetno'])
    if not h_no or not h_date or not d_no or not d_item:
        return []
    on_parts = [f'h.{h_no} = d.{d_no}']
    if h_loc and d_loc:
        on_parts.append(f'h.{h_loc} = d.{d_loc}')
    if h_reset and d_reset:
        on_parts.append(f'NVL(h.{h_reset}, 0) = NVL(d.{d_reset}, 0)')
    where_parts: List[str] = []
    params: Dict[str, Any] = {}
    if h_loc:
        where_parts.append(f'h.{h_loc} = :loc')
        params['loc'] = _resolve_location_code()
    if h_reset:
        where_parts.append(f'NVL(h.{h_reset}, :rn) = :rn')
        params['rn'] = _LPO_DETAILS_RESET_NO
    if h_del:
        where_parts.append(f"NVL(h.{h_del}, 'N') = 'N'")
    if receipt_no is not None and receiptno_is_valid(receipt_no):
        where_parts.append(f'h.{h_no} = :receipt_no')
        params['receipt_no'] = coerce_receiptno(receipt_no)
    if lpo_no is not None and lpono_is_valid(lpo_no) and h_lpo:
        where_parts.append(f'h.{h_lpo} = :lpo_no')
        params['lpo_no'] = coerce_lpono(lpo_no)
    if date_from:
        where_parts.append(f"TRUNC(h.{h_date}) >= TO_DATE(:df, 'YYYY-MM-DD')")
        params['df'] = date_from
    if date_to:
        where_parts.append(f"TRUNC(h.{h_date}) <= TO_DATE(:dt, 'YYYY-MM-DD')")
        params['dt'] = date_to
    if supplier_code is not None and supplier_code > 0 and h_sup:
        where_parts.append(f'h.{h_sup} = :sup')
        params['sup'] = int(supplier_code)
    if item_code:
        where_parts.append(f'd.{d_item} = :item_code')
        params['item_code'] = int(item_code)
    sup_tbl = _detect_table(['SUPPLIER', 'supplier', 'SUPPLIERS'])
    sup_code_col = _detect_column(sup_tbl, ['SUPPLIERCODE', 'SUPPLIER_CODE', 'suppliercode']) if sup_tbl else None
    sup_name_col = _detect_column(sup_tbl, ['SUPPLIERNAME', 'SUPPLIER_NAME', 'suppliername']) if sup_tbl else None
    join_sup = ''
    sup_name_expr = "''"
    if sup_tbl and h_sup and sup_code_col and sup_name_col:
        join_sup = f' LEFT JOIN {sup_tbl} s ON h.{h_sup} = s.{sup_code_col} '
        sup_name_expr = f"NVL(s.{sup_name_col}, '')"
    im = _detect_table(['ITEMMASTER', 'itemmaster'])
    im_item = _detect_column(im, ['ITEMCODE', 'ITEM_CODE', 'itemcode']) if im else None
    im_name = _detect_column(im, ['ITEMNAME', 'ITEM_NAME', 'itemname']) if im else None
    im_loc = _detect_column(im, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode']) if im else None
    join_im = ''
    item_name_expr = f"{(f'd.{d_name}' if d_name else 'CAST(NULL AS VARCHAR2(1))')}"
    if im and im_item and im_name:
        im_on = f'd.{d_item} = im.{im_item}'
        if im_loc and h_loc:
            im_on += f' AND im.{im_loc} = h.{h_loc}'
        join_im = f' LEFT JOIN {im} im ON {im_on} '
        if d_name:
            item_name_expr = f"NVL(NULLIF(TRIM(d.{d_name}), ''), im.{im_name})"
        else:
            item_name_expr = f"NVL(im.{im_name}, '')"
    wh_tbl = resolve_warehouse_master_table()
    wh_id_col = _detect_column(wh_tbl, ['WAREHOUSE_ID', 'warehouse_id']) if wh_tbl else None
    wh_name_col = _detect_column(wh_tbl, ['WAREHOUSE_NAME', 'WAREHOUSENAME', 'warehouse_name', 'warehousename', 'NAME', 'name']) if wh_tbl else None
    join_wh = ''
    wh_name_expr = "CAST('' AS VARCHAR2(120))"
    wh_ref = f'h.{h_wh}' if h_wh else (f'd.{d_wh}' if d_wh else None)
    if wh_tbl and wh_id_col and wh_name_col and wh_ref:
        join_wh = f' LEFT JOIN {wh_tbl} wh ON {wh_ref} = wh.{wh_id_col} '
        wh_name_expr = f"NVL(wh.{wh_name_col}, '')"
    sl_expr = f'd.{d_lineno}' if d_lineno else '1'
    rem_expr = f'h.{h_rem}' if h_rem else "CAST('' AS VARCHAR2(1))"
    qty_e = f'NVL(d.{d_qty}, 0)' if d_qty else '0'
    rate_e = f'NVL(d.{d_rate}, 0)' if d_rate else '0'
    disc_e = f'NVL(d.{d_ldisc}, 0)' if d_ldisc else '0'
    if d_amt:
        line_amt_expr = f'NVL(d.{d_amt}, 0)'
    else:
        line_amt_expr = f'({qty_e} * {rate_e} - {disc_e})'
    inv_posted_expr = f"h.{h_inv_posted}" if h_inv_posted else "CAST(NULL AS VARCHAR2(10))"
    q = f"""
        SELECT
            h.{h_no} AS receiptno,
            h.{h_date} AS receiptdate,
            {(f'h.{h_lpo}' if h_lpo else 'CAST(NULL AS VARCHAR2(30))')} AS lpono,
            {(f"h.{h_inv}" if h_inv else "CAST('' AS VARCHAR2(1))")} AS invoiceno,
            {(f'h.{h_inv_date}' if h_inv_date else 'CAST(NULL AS DATE)')} AS invoicedate,
            {(f'h.{h_post}' if h_post else 'CAST(NULL AS DATE)')} AS postingdate,
            {inv_posted_expr} AS inventory_posted,
            {(f'h.{h_wh}' if h_wh else (f'd.{d_wh}' if d_wh else 'CAST(NULL AS NUMBER)'))} AS warehouse_id,
            {wh_name_expr} AS warehouse_name,
            {(f'h.{h_sup}' if h_sup else 'CAST(NULL AS NUMBER)')} AS suppliercode,
            {sup_name_expr} AS suppliername,
            NVL({(f'h.{h_amt}' if h_amt else '0')}, 0) AS receiptamount,
            NVL({(f'h.{h_disc}' if h_disc else '0')}, 0) AS hdr_discount,
            NVL({(f'h.{h_other}' if h_other else '0')}, 0) AS hdr_othercharge,
            {rem_expr} AS hdr_remarks,
            {sl_expr} AS slno,
            d.{d_item} AS itemcode,
            {(f"NVL(d.{d_barcode}, '')" if d_barcode else "CAST('' AS VARCHAR2(1))")} AS barcode,
            {item_name_expr} AS itemname,
            {(f"NVL(d.{d_uom}, '')" if d_uom else "CAST('' AS VARCHAR2(1))")} AS uom,
            {qty_e} AS quantity,
            {rate_e} AS rate,
            NVL({(f'd.{d_bonus}' if d_bonus else '0')}, 0) AS bonus,
            {disc_e} AS linediscount,
            {line_amt_expr} AS amount,
            NVL({(f'd.{d_base}' if d_base else '0')}, 0) AS baseqty,
            {(f'd.{d_foc}' if d_foc else '0')} AS foc_raw,
            NVL({(f'd.{d_other}' if d_other else '0')}, 0) AS line_othercharge,
            NVL({(f'd.{d_land}' if d_land else '0')}, 0) AS landingcost,
            {(f"NVL(d.{d_batch}, '')" if d_batch else "CAST('' AS VARCHAR2(1))")} AS batch_no,
            {(f'd.{d_mfg}' if d_mfg else 'CAST(NULL AS DATE)')} AS mfg_date,
            {(f'd.{d_exp}' if d_exp else 'CAST(NULL AS DATE)')} AS expiry_date
        FROM {hdr} h
        INNER JOIN {dtl} d ON {' AND '.join(on_parts)}
        {join_sup}
        {join_im}
        {join_wh}
        WHERE {(' AND '.join(where_parts) if where_parts else '1=1')}
        ORDER BY h.{h_no} DESC, {sl_expr} ASC
    """
    try:
        return _safe_rows(q, params) or []
    except Exception as e:
        logger.exception('GRN details query failed: %s', e)
        if join_wh:
            q2 = q.replace(join_wh, '').replace(wh_name_expr, "CAST('' AS VARCHAR2(120))")
            try:
                return _safe_rows(q2, params) or []
            except Exception as e2:
                logger.exception('GRN details retry failed: %s', e2)
        return []

def _get_purchase_detail_rows(date_from: Optional[str]=None, date_to: Optional[str]=None, lpo_no: Optional[Any]=None, supplier_code: Optional[int]=None, item_code: Optional[int]=None) -> List[Dict[str, Any]]:
    """Purchase line details from saved LPO (LPOHDR / LPODTL) only."""
    return _get_purchase_detail_rows_from_lpo(
        date_from=date_from, date_to=date_to, lpo_no=lpo_no,
        supplier_code=supplier_code, item_code=item_code,
    )

def _get_purchase_detail_supplier_options(search: str='', limit: int=300) -> List[Dict[str, Any]]:
    tbl = _detect_table(['SUPPLIER', 'supplier', 'SUPPLIERS'])
    if not tbl:
        return []
    code_col = _detect_column(tbl, ['SUPPLIERCODE', 'SUPPLIER_CODE', 'suppliercode'])
    name_col = _detect_column(tbl, ['SUPPLIERNAME', 'SUPPLIER_NAME', 'suppliername'])
    if not code_col:
        return []
    cap = min(max(int(limit or 300), 50), 800)
    name_sel = f'{name_col} AS suppliername' if name_col else "'' AS suppliername"
    where = ['1=1']
    params: Dict[str, Any] = {}
    q_text = str(search or '').strip().upper()
    if q_text:
        params['q'] = f'%{q_text}%'
        if name_col:
            where.append(f"(TO_CHAR({code_col}) LIKE :q OR UPPER(NVL({name_col}, '')) LIKE :q)")
        else:
            where.append(f'TO_CHAR({code_col}) LIKE :q')
    q = f"""
        SELECT * FROM (
            SELECT DISTINCT {code_col} AS suppliercode, {name_sel}
            FROM {tbl}
            WHERE {' AND '.join(where)}
            ORDER BY {code_col}
        ) WHERE ROWNUM <= {cap}
    """
    try:
        _, rows = _fetch_rows(q, params)
    except Exception:
        return []
    out: List[Dict[str, Any]] = []
    for r in rows or []:
        try:
            c = int(float(r.get('suppliercode') or 0))
        except (TypeError, ValueError):
            continue
        if c <= 0:
            continue
        out.append({'suppliercode': c, 'suppliername': str(r.get('suppliername') or '').strip()})
    return out

def _purchase_detail_item_options_from_dtl(dtl: str, search: str='', limit: int=300) -> List[Dict[str, str]]:
    d_item = _detect_column(dtl, ['ITEMCODE', 'ITEM_CODE', 'itemcode'])
    d_loc = _detect_column(dtl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    d_reset = _detect_column(dtl, ['RESETNO', 'RESET_NO', 'resetno'])
    if not d_item:
        return []
    where = ['1=1']
    params: Dict[str, Any] = {}
    if d_loc:
        where.append(f'd.{d_loc} = :loc')
        params['loc'] = _resolve_location_code()
    if d_reset:
        where.append(f'NVL(d.{d_reset}, :rn) = :rn')
        params['rn'] = _LPO_DETAILS_RESET_NO
    im = _detect_table(['ITEMMASTER', 'itemmaster'])
    im_item = _detect_column(im, ['ITEMCODE', 'ITEM_CODE', 'itemcode']) if im else None
    im_name = _detect_column(im, ['ITEMNAME', 'ITEM_NAME', 'itemname']) if im else None
    im_loc = _detect_column(im, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode']) if im else None
    q_text = str(search or '').strip().upper()
    if q_text:
        params['q'] = f'%{q_text}%'
        if im and im_item and im_name:
            where.append(f"(TO_CHAR(d.{d_item}) LIKE :q OR UPPER(NVL(im.{im_name},'')) LIKE :q)")
        else:
            where.append(f'TO_CHAR(d.{d_item}) LIKE :q')
    cap = min(max(int(limit or 300), 50), 500)
    if im and im_item and im_name:
        im_on = f'd.{d_item} = im.{im_item}'
        if im_loc and d_loc:
            im_on += f' AND d.{d_loc} = im.{im_loc}'
        inner_from = f'{dtl} d LEFT JOIN {im} im ON {im_on}'
        name_sel = f"NVL(im.{im_name}, '')"
    else:
        inner_from = f'{dtl} d'
        name_sel = "''"
    q = f"""
        SELECT * FROM (
            SELECT DISTINCT d.{d_item} AS itemcode, {name_sel} AS itemname
            FROM {inner_from}
            WHERE {' AND '.join(where)}
            ORDER BY d.{d_item}
        ) WHERE ROWNUM <= {cap}
    """
    try:
        rows = _safe_rows(q, params) or []
    except Exception:
        return []
    out: List[Dict[str, str]] = []
    for r in rows:
        code = str(r.get('itemcode') or '').strip()
        if not code:
            continue
        out.append({'itemcode': code, 'itemname': str(r.get('itemname') or '').strip()})
    return out

def _get_purchase_detail_item_options(search: str='', limit: int=300) -> List[Dict[str, str]]:
    dtl = _detect_table(['LPODTL', 'lpodtl'])
    if not dtl:
        return []
    return _purchase_detail_item_options_from_dtl(dtl, search=search, limit=limit)

def _get_grn_detail_item_options(search: str='', limit: int=300) -> List[Dict[str, str]]:
    dtl = _detect_table(['RECEIPTDTL', 'receiptdtl'])
    if not dtl:
        return []
    return _purchase_detail_item_options_from_dtl(dtl, search=search, limit=limit)
_PURCHASE_RETURN_DETAILS_RESET_NO = 1

def _get_purchase_return_detail_rows(date_from: Optional[str]=None, date_to: Optional[str]=None, goods_return_no: Optional[int]=None, supplier_code: Optional[int]=None, receipt_no: Optional[int]=None, return_type: Optional[str]=None, item_code: Optional[int]=None) -> List[Dict[str, Any]]:
    """Purchase return header + line detail (RETURNHDR / RETURNDTL) for the reporting tenant/location."""
    hdr = _detect_table(['RETURNHDR', 'returnhdr'])
    dtl = _detect_table(['RETURNDTL', 'returndtl'])
    if not hdr or not dtl:
        return []
    h_no = _detect_column(hdr, ['GOODSRETURNNO', 'goodsreturnno'])
    h_date = _detect_column(hdr, ['RETURNDATE', 'returndate'])
    h_type = _detect_column(hdr, ['RETURNTYPE', 'returntype'])
    h_sup = _detect_column(hdr, ['SUPPLIERCODE', 'suppliercode'])
    h_receipt = _detect_column(hdr, ['RECEIPTNO', 'receiptno'])
    h_amt = _detect_column(hdr, ['RETURNAMOUNT', 'returnamount'])
    h_rem = _detect_column(hdr, ['REMARKS', 'remarks'])
    h_loc = _detect_column(hdr, ['LOCATIONCODE', 'locationcode'])
    h_reset = _detect_column(hdr, ['RESETNO', 'resetno'])
    h_del = _detect_column(hdr, ['DELFLAG', 'delflag'])
    d_grn = _detect_column(dtl, ['GOODSRETURNNO', 'goodsreturnno'])
    d_lineno = _detect_column(dtl, ['LINENO', 'LINE_NO', 'lineno', 'SLNO', 'slno'])
    d_item = _detect_column(dtl, ['ITEMCODE', 'itemcode'])
    d_barcode = _detect_column(dtl, ['MANUFACTURERID', 'MANUFACTURER_ID', 'manufacturerid', 'BARCODE', 'barcode'])
    d_uom = _detect_column(dtl, ['UOM', 'uom'])
    d_qty = _detect_column(dtl, ['QUANTITY', 'quantity'])
    d_rate = _detect_column(dtl, ['RATE', 'rate'])
    d_disc = _detect_column(dtl, ['DISCOUNT', 'discount'])
    d_amt = _detect_column(dtl, ['AMOUNT', 'LINEAMOUNT', 'amount'])
    d_store_code = _detect_column(dtl, ['STORECODE', 'storecode'])
    d_store = _detect_column(dtl, ['STORE', 'store'])
    d_line_rem = _detect_column(dtl, ['REMARKS', 'remarks'])
    d_avg_cost = _detect_column(dtl, ['AVERAGECOST', 'averagecost'])
    d_conv = _detect_column(dtl, ['CONVERSIONFACTOR', 'CONVERSION_FACTOR', 'UOMFACTOR', 'UOM_FACTOR', 'conversionfactor', 'uomfactor'])
    d_lot = _detect_column(dtl, ['LOT_ID', 'LOTID', 'lot_id'])
    d_loc = _detect_column(dtl, ['LOCATIONCODE', 'locationcode'])
    d_reset = _detect_column(dtl, ['RESETNO', 'resetno'])
    if not h_no or not h_date or (not d_grn) or (not d_item):
        return []
    on_parts = [f'h.{h_no} = d.{d_grn}']
    if h_loc and d_loc:
        on_parts.append(f'h.{h_loc} = d.{d_loc}')
    if h_reset and d_reset:
        on_parts.append(f'NVL(h.{h_reset}, 0) = NVL(d.{d_reset}, 0)')
    where_parts: List[str] = []
    params: Dict[str, Any] = {}
    if h_loc:
        where_parts.append(f'h.{h_loc} = :loc')
        params['loc'] = _resolve_location_code()
    if h_reset:
        where_parts.append(f'NVL(h.{h_reset}, :rn) = :rn')
        params['rn'] = _PURCHASE_RETURN_DETAILS_RESET_NO
    if h_del:
        where_parts.append(f"NVL(h.{h_del}, 'N') = 'N'")
    if goods_return_no:
        where_parts.append(f'h.{h_no} = :grn')
        params['grn'] = int(goods_return_no)
    if date_from:
        where_parts.append(f"TRUNC(h.{h_date}) >= TO_DATE(:df, 'YYYY-MM-DD')")
        params['df'] = date_from
    if date_to:
        where_parts.append(f"TRUNC(h.{h_date}) <= TO_DATE(:dt, 'YYYY-MM-DD')")
        params['dt'] = date_to
    if supplier_code is not None and supplier_code > 0 and h_sup:
        where_parts.append(f'h.{h_sup} = :sup')
        params['sup'] = int(supplier_code)
    if receipt_no is not None and receipt_no > 0 and h_receipt:
        where_parts.append(f'h.{h_receipt} = :rcp')
        params['rcp'] = int(receipt_no)
    rt = (return_type or '').strip().upper()[:1]
    if rt and h_type:
        where_parts.append(f"NVL(h.{h_type}, 'P') = :rtype")
        params['rtype'] = rt
    if item_code:
        where_parts.append(f'd.{d_item} = :item_code')
        params['item_code'] = int(item_code)
    sup_tbl = _detect_table(['SUPPLIER', 'supplier', 'SUPPLIERS'])
    sup_code_col = _detect_column(sup_tbl, ['SUPPLIERCODE', 'SUPPLIER_CODE', 'suppliercode']) if sup_tbl else None
    sup_name_col = _detect_column(sup_tbl, ['SUPPLIERNAME', 'SUPPLIER_NAME', 'suppliername']) if sup_tbl else None
    join_sup = ''
    sup_name_expr = "''"
    if sup_tbl and h_sup and sup_code_col and sup_name_col:
        join_sup = f' LEFT JOIN {sup_tbl} s ON h.{h_sup} = s.{sup_code_col} '
        sup_name_expr = f"NVL(s.{sup_name_col}, '')"
    im = _detect_table(['ITEMMASTER', 'itemmaster'])
    im_item = _detect_column(im, ['ITEMCODE', 'ITEM_CODE', 'itemcode']) if im else None
    im_name = _detect_column(im, ['ITEMNAME', 'ITEM_NAME', 'itemname']) if im else None
    im_loc = _detect_column(im, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode']) if im else None
    join_im = ''
    item_name_expr = 'CAST(NULL AS VARCHAR2(4000))'
    if im and im_item and im_name:
        im_on = f'd.{d_item} = im.{im_item}'
        if im_loc and h_loc:
            im_on += f' AND im.{im_loc} = h.{h_loc}'
        join_im = f' LEFT JOIN {im} im ON {im_on} '
        item_name_expr = f"NVL(im.{im_name}, '')"
    qty_e = f'NVL(d.{d_qty}, 0)' if d_qty else '0'
    rate_e = f'NVL(d.{d_rate}, 0)' if d_rate else '0'
    disc_e = f'NVL(d.{d_disc}, 0)' if d_disc else '0'
    if d_amt:
        line_amt_expr = f'NVL(d.{d_amt}, 0)'
    else:
        line_amt_expr = f'({qty_e} * {rate_e} - {disc_e})'
    sl_expr = f'd.{d_lineno}' if d_lineno else '1'
    q = f"""\n        SELECT\n            h.{h_no} AS goodsreturnno,\n            h.{h_date} AS returndate,\n            {(f"NVL(h.{h_type}, 'P')" if h_type else "'P'")} AS returntype,\n            {(f'h.{h_sup}' if h_sup else 'CAST(NULL AS NUMBER)')} AS suppliercode,\n            {sup_name_expr} AS suppliername,\n            {(f'h.{h_receipt}' if h_receipt else 'CAST(NULL AS NUMBER)')} AS receiptno,\n            NVL({(f'h.{h_amt}' if h_amt else '0')}, 0) AS returnamount,\n            {(f'h.{h_rem}' if h_rem else "''")} AS hdr_remarks,\n            {sl_expr} AS slno,\n            d.{d_item} AS itemcode,\n            {(f"NVL(d.{d_barcode}, '')" if d_barcode else "''")} AS barcode,\n            {item_name_expr} AS itemname,\n            {(f"NVL(d.{d_uom}, '')" if d_uom else "''")} AS uom,\n            NVL({(f'd.{d_qty}' if d_qty else '0')}, 0) AS quantity,\n            NVL({(f'd.{d_rate}' if d_rate else '0')}, 0) AS rate,\n            NVL({(f'd.{d_disc}' if d_disc else '0')}, 0) AS linediscount,\n            {line_amt_expr} AS lineamount,\n            NVL({(f'd.{d_store_code}' if d_store_code else '0')}, 0) AS storecode,\n            {(f"NVL(d.{d_store}, '')" if d_store else "''")} AS storename,\n            {(f"NVL(d.{d_line_rem}, '')" if d_line_rem else "''")} AS line_remarks,\n            NVL({(f'd.{d_avg_cost}' if d_avg_cost else '0')}, 0) AS averagecost,\n            NVL({(f'd.{d_conv}' if d_conv else '1')}, 1) AS conversionfactor,\n            {(f'd.{d_lot}' if d_lot else 'CAST(NULL AS NUMBER)')} AS lot_id\n        FROM {hdr} h\n        INNER JOIN {dtl} d ON {' AND '.join(on_parts)}\n        {join_sup}\n        {join_im}\n        WHERE {(' AND '.join(where_parts) if where_parts else '1=1')}\n        ORDER BY h.{h_no} DESC, {sl_expr} ASC\n    """
    try:
        return _safe_rows(q, params) or []
    except Exception as e:
        logger.exception('Purchase return details report failed: %s', e)
        return []

def _get_purchase_return_detail_item_options(search: str='', limit: int=300) -> List[Dict[str, str]]:
    dtl = _detect_table(['RETURNDTL', 'returndtl'])
    if not dtl:
        return []
    d_item = _detect_column(dtl, ['ITEMCODE', 'itemcode'])
    d_loc = _detect_column(dtl, ['LOCATIONCODE', 'locationcode'])
    d_reset = _detect_column(dtl, ['RESETNO', 'resetno'])
    if not d_item:
        return []
    where = ['1=1']
    params: Dict[str, Any] = {}
    if d_loc:
        where.append(f'{d_loc} = :loc')
        params['loc'] = _resolve_location_code()
    if d_reset:
        where.append(f'NVL({d_reset}, :rn) = :rn')
        params['rn'] = _PURCHASE_RETURN_DETAILS_RESET_NO
    im = _detect_table(['ITEMMASTER', 'itemmaster'])
    im_item = _detect_column(im, ['ITEMCODE', 'ITEM_CODE', 'itemcode']) if im else None
    im_name = _detect_column(im, ['ITEMNAME', 'ITEM_NAME', 'itemname']) if im else None
    im_loc = _detect_column(im, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode']) if im else None
    q_text = str(search or '').strip().upper()
    if q_text:
        params['q'] = f'%{q_text}%'
        if im and im_item and im_name and im_loc and d_loc:
            where.append(f"(TO_CHAR(d.{d_item}) LIKE :q OR UPPER(NVL(im.{im_name},'')) LIKE :q)")
        else:
            where.append(f'TO_CHAR(d.{d_item}) LIKE :q')
    cap = min(max(int(limit or 300), 50), 500)
    if im and im_item and im_name and im_loc and d_loc:
        inner_from = f'\n            {dtl} d\n            LEFT JOIN {im} im ON d.{d_item} = im.{im_item} AND d.{d_loc} = im.{im_loc}\n        '
        name_sel = f"NVL(im.{im_name}, '')"
    else:
        inner_from = f'{dtl} d'
        name_sel = "''"
    q = f"\n        SELECT * FROM (\n            SELECT DISTINCT\n                d.{d_item} AS itemcode,\n                {name_sel} AS itemname\n            FROM {inner_from}\n            WHERE {' AND '.join(where)}\n            ORDER BY d.{d_item}\n        )\n        WHERE ROWNUM <= {cap}\n    "
    try:
        rows = _safe_rows(q, params) or []
    except Exception:
        return []
    out: List[Dict[str, str]] = []
    for r in rows:
        code = str(r.get('itemcode') or '').strip()
        if not code:
            continue
        out.append({'itemcode': code, 'itemname': str(r.get('itemname') or '').strip()})
    return out
_SALES_DETAILS_RESET_NO = 1
_LAST_TX_GRN_RESET_NO = 1

def _sales_detail_hdr_dtl_tables() -> Tuple[str, str]:
    """Sales details report uses BILLHDR / BILLDTL only."""
    ht = _detect_table(['BILLHDR', 'billhdr'])
    dt = _detect_table(['BILLDTL', 'billdtl'])
    if ht and dt:
        return (ht, dt)
    return ('', '')

def _last_tx_detect_sales_tables() -> Tuple[str, str]:
    """Prefer posted history tables so last dates reflect full activity."""
    ht = _detect_table(['BILLHDRHISTORY', 'billhdrhistory'])
    dt = _detect_table(['BILLDTLHISTORY', 'billdtlhistory'])
    if ht and dt:
        return (ht, dt)
    return _sales_detail_hdr_dtl_tables()

def _last_tx_bill_agg_subquery(qty_positive: bool, date_from: str='', date_to: str='') -> Optional[str]:
    ht, dt = _last_tx_detect_sales_tables()
    if not ht or not dt:
        return None
    h_no = _detect_column(ht, ['BILLNO', 'billno'])
    h_date = _detect_column(ht, ['BILLDATE', 'billdate'])
    h_loc = _detect_column(ht, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    h_reset = _detect_column(ht, ['RESETNO', 'RESET_NO', 'resetno'])
    h_del = _detect_column(ht, ['DELFLAG', 'DEL_FLAG', 'delflag'])
    h_status = _detect_column(ht, ['BILLSTATUS', 'BILL_STATUS', 'billstatus'])
    d_bill = _detect_column(dt, ['BILLNO', 'billno'])
    d_item = _detect_column(dt, ['ITEMCODE', 'ITEM_CODE', 'itemcode'])
    d_loc = _detect_column(dt, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    d_reset = _detect_column(dt, ['RESETNO', 'RESET_NO', 'resetno'])
    d_qty = _detect_column(dt, ['QUANTITY', 'quantity'])
    if not h_no or not h_date or (not d_bill) or (not d_item):
        return None
    on_parts = [f'h.{h_no} = d.{d_bill}']
    if h_loc and d_loc:
        on_parts.append(f'h.{h_loc} = d.{d_loc}')
    if h_reset and d_reset:
        on_parts.append(f'h.{h_reset} = d.{d_reset}')
    where_parts: List[str] = []
    if h_loc:
        where_parts.append(f'h.{h_loc} = :lt_loc')
    if h_reset:
        where_parts.append(f'h.{h_reset} = :lt_rn_bill')
    if h_del:
        where_parts.append(f"NVL(h.{h_del}, 'N') <> 'Y'")
    if h_status:
        where_parts.append(f"(h.{h_status} IS NULL OR UPPER(TRIM(h.{h_status})) <> 'V')")
    if date_from:
        where_parts.append(f"TRUNC(h.{h_date}) >= TO_DATE(:lt_df, 'YYYY-MM-DD')")
    if date_to:
        where_parts.append(f"TRUNC(h.{h_date}) <= TO_DATE(:lt_dt, 'YYYY-MM-DD')")
    if d_qty:
        where_parts.append(f'NVL(d.{d_qty}, 0) >= 0' if qty_positive else f'NVL(d.{d_qty}, 0) < 0')
    else:
        where_parts.append(_bill_history_return_predicate('h', ht, sales_return=not qty_positive))
    inner = f"\n        SELECT d.{d_item} AS ic, MAX(TRUNC(h.{h_date})) AS dt\n        FROM {ht} h\n        INNER JOIN {dt} d ON {' AND '.join(on_parts)}\n        WHERE {' AND '.join(where_parts)}\n        GROUP BY d.{d_item}\n    ".strip()
    return inner

def _last_tx_receipt_agg_subquery(date_from: str='', date_to: str='') -> Optional[str]:
    rh = _detect_table(['RECEIPTHDR', 'receipthdr'])
    rd = _detect_table(['RECEIPTDTL', 'receiptdtl'])
    if not rh or not rd:
        return None
    h_loc = _detect_column(rh, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    h_no = _detect_column(rh, ['RECEIPTNO', 'RECEIPT_NO', 'receiptno'])
    h_date = _detect_column(rh, ['RECEIPTDATE', 'RECEIPT_DATE', 'receiptdate', 'CREATEDDATE', 'createddate'])
    h_reset = _detect_column(rh, ['RESETNO', 'RESET_NO', 'resetno'])
    h_del = _detect_column(rh, ['DELFLAG', 'DEL_FLAG', 'delflag'])
    d_loc = _detect_column(rd, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    d_no = _detect_column(rd, ['RECEIPTNO', 'RECEIPT_NO', 'receiptno'])
    d_item = _detect_column(rd, ['ITEMCODE', 'ITEM_CODE', 'itemcode'])
    if not h_no or not h_date or (not d_no) or (not d_item):
        return None
    join_cond = [f'd.{d_no} = h.{h_no}']
    if h_loc and d_loc:
        join_cond.append(f'd.{d_loc} = h.{h_loc}')
    where_parts: List[str] = []
    if h_loc:
        where_parts.append(f'h.{h_loc} = :lt_loc')
    if h_reset:
        where_parts.append(f'h.{h_reset} = :lt_rn_rcpt')
    if h_del:
        where_parts.append(f"NVL(h.{h_del}, 'N') <> 'Y'")
    if date_from:
        where_parts.append(f"TRUNC(h.{h_date}) >= TO_DATE(:lt_df, 'YYYY-MM-DD')")
    if date_to:
        where_parts.append(f"TRUNC(h.{h_date}) <= TO_DATE(:lt_dt, 'YYYY-MM-DD')")
    inner = f"\n        SELECT d.{d_item} AS ic, MAX(TRUNC(h.{h_date})) AS dt\n        FROM {rd} d\n        INNER JOIN {rh} h ON {' AND '.join(join_cond)}\n        WHERE {' AND '.join(where_parts)}\n        GROUP BY d.{d_item}\n    ".strip()
    return inner

def _last_tx_purchase_return_agg_subquery(date_from: str='', date_to: str='') -> Optional[str]:
    hdr = _detect_table(['RETURNHDR', 'returnhdr'])
    dtl = _detect_table(['RETURNDTL', 'returndtl'])
    if not hdr or not dtl:
        return None
    h_no = _detect_column(hdr, ['GOODSRETURNNO', 'goodsreturnno'])
    h_date = _detect_column(hdr, ['RETURNDATE', 'returndate'])
    h_loc = _detect_column(hdr, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    h_reset = _detect_column(hdr, ['RESETNO', 'RESET_NO', 'resetno'])
    h_del = _detect_column(hdr, ['DELFLAG', 'DEL_FLAG', 'delflag'])
    d_grn = _detect_column(dtl, ['GOODSRETURNNO', 'goodsreturnno'])
    d_item = _detect_column(dtl, ['ITEMCODE', 'ITEM_CODE', 'itemcode'])
    d_loc = _detect_column(dtl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    d_reset = _detect_column(dtl, ['RESETNO', 'RESET_NO', 'resetno'])
    if not h_no or not h_date or (not d_grn) or (not d_item):
        return None
    on_parts = [f'h.{h_no} = d.{d_grn}']
    if h_loc and d_loc:
        on_parts.append(f'h.{h_loc} = d.{d_loc}')
    if h_reset and d_reset:
        on_parts.append(f'h.{h_reset} = d.{d_reset}')
    where_parts: List[str] = []
    if h_loc:
        where_parts.append(f'h.{h_loc} = :lt_loc')
    if h_reset:
        where_parts.append(f'h.{h_reset} = :lt_rn_pret')
    if h_del:
        where_parts.append(f"NVL(h.{h_del}, 'N') <> 'Y'")
    if date_from:
        where_parts.append(f"TRUNC(h.{h_date}) >= TO_DATE(:lt_df, 'YYYY-MM-DD')")
    if date_to:
        where_parts.append(f"TRUNC(h.{h_date}) <= TO_DATE(:lt_dt, 'YYYY-MM-DD')")
    inner = f"\n        SELECT d.{d_item} AS ic, MAX(TRUNC(h.{h_date})) AS dt\n        FROM {hdr} h\n        INNER JOIN {dtl} d ON {' AND '.join(on_parts)}\n        WHERE {' AND '.join(where_parts)}\n        GROUP BY d.{d_item}\n    ".strip()
    return inner

def _get_last_transactions_category_options() -> List[Dict[str, Any]]:
    im = _detect_table(['ITEMMASTER', 'itemmaster'])
    if not im:
        return []
    im_cat = _detect_column(im, ['CATEGORYCODE', 'CATEGORY_CODE', 'categorycode'])
    im_loc = _detect_column(im, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    if not im_cat:
        return []
    cat = _detect_table(['CATEGORY', 'category'])
    cat_code = _detect_column(cat, ['CODE', 'CATEGORYCODE', 'categorycode']) if cat else None
    cat_name = _detect_column(cat, ['NAME', 'CATEGORYNAME', 'categoryname']) if cat else None
    cat_flag = _detect_column(cat, ['FLAG', 'flag']) if cat else None
    join_cat = ''
    name_expr = "''"
    if cat and cat_code and cat_name:
        join_cat = f' LEFT JOIN {cat} c ON c.{cat_code} = im.{im_cat} '
        if cat_flag:
            join_cat += f" AND c.{cat_flag} = 'C' "
        name_expr = f"NVL(c.{cat_name}, '')"
    params: Dict[str, Any] = {}
    where = [f'im.{im_cat} IS NOT NULL']
    if im_loc:
        where.append(f'im.{im_loc} = :loc')
        params['loc'] = _resolve_location_code()
    q = f"\n        SELECT * FROM (\n            SELECT DISTINCT im.{im_cat} AS categorycode, {name_expr} AS categoryname\n            FROM {im} im\n            {join_cat}\n            WHERE {' AND '.join(where)}\n            ORDER BY im.{im_cat}\n        )\n        WHERE ROWNUM <= 2000\n    "
    try:
        return _safe_rows(q, params) or []
    except Exception:
        return []

def _get_last_transactions_report_rows(search: str='', row_cap: int=6000, date_from: str='', date_to: str='', transaction_types: Optional[List[str]]=None, category_code: str='') -> List[Dict[str, Any]]:
    """ITEMMASTER row plus last sale, sale return, GRN purchase, and purchase return dates for current location."""
    loc = _resolve_location_code()
    im = _detect_table(['ITEMMASTER', 'itemmaster'])
    if not im:
        return []
    ic = _detect_column(im, ['ITEMCODE', 'ITEM_CODE', 'itemcode'])
    iloc = _detect_column(im, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    iname = _detect_column(im, ['ITEMNAME', 'ITEM_NAME', 'itemname'])
    ibase = _detect_column(im, ['BASEUOM', 'BASE_UOM', 'UNITOFMEASUREMENT', 'UOM', 'baseuom'])
    icost = _detect_column(im, ['COSTPRICE', 'COST_PRICE', 'costprice'])
    istock = _detect_column(im, ['CURRENTSTOCK', 'CURRENT_STOCK', 'currentstock', 'STOCK', 'stock'])
    icat = _detect_column(im, ['CATEGORYCODE', 'CATEGORY_CODE', 'categorycode'])
    if not ic or not iloc:
        return []
    try:
        im_cols = {str(c).upper() for c in _get_table_columns(im) or []}
    except Exception:
        im_cols = set()
    raw_col = _detect_column(im, ['RAWABICODE', 'rawabicode']) if 'RAWABICODE' in im_cols else None
    mfg_col = _detect_column(im, ['MANUFACTURERID', 'MANUFACTURER_ID', 'manufacturerid']) if 'MANUFACTURERID' in im_cols else None
    raw_sel = f'TRIM(TO_CHAR(im.{raw_col}))' if raw_col else 'CAST(NULL AS VARCHAR2(240))'
    mfg_sel = f'TRIM(TO_CHAR(im.{mfg_col}))' if mfg_col else 'CAST(NULL AS VARCHAR2(240))'
    name_sel = f'im.{iname}' if iname else 'CAST(NULL AS VARCHAR2(400))'
    base_sel = f'im.{ibase}' if ibase else 'CAST(NULL AS VARCHAR2(40))'
    cost_sel = f'NVL(im.{icost}, 0)' if icost else '0'
    stock_sel = f'NVL(im.{istock}, 0)' if istock else '0'
    cat_code_sel = f'im.{icat}' if icat else 'CAST(NULL AS NUMBER)'
    cat_tbl = _detect_table(['CATEGORY', 'category'])
    cat_code = _detect_column(cat_tbl, ['CODE', 'CATEGORYCODE', 'categorycode']) if cat_tbl else None
    cat_name = _detect_column(cat_tbl, ['NAME', 'CATEGORYNAME', 'categoryname']) if cat_tbl else None
    cat_flag = _detect_column(cat_tbl, ['FLAG', 'flag']) if cat_tbl else None
    join_cat = ''
    cat_name_sel = 'CAST(NULL AS VARCHAR2(240))'
    if icat and cat_tbl and cat_code and cat_name:
        join_cat = f'LEFT JOIN {cat_tbl} cat ON cat.{cat_code} = im.{icat}'
        if cat_flag:
            join_cat += f" AND cat.{cat_flag} = 'C'"
        cat_name_sel = f'cat.{cat_name}'
    selected = {str(t or '').strip().lower() for t in transaction_types or [] if str(t or '').strip()}
    valid_types = {'sale', 'purchase', 'purchase_return', 'sale_return'}
    if not selected:
        selected = set(valid_types)
    selected &= valid_types
    sq_sale = _last_tx_bill_agg_subquery(True, date_from, date_to) if 'sale' in selected else None
    sq_sret = _last_tx_bill_agg_subquery(False, date_from, date_to) if 'sale_return' in selected else None
    sq_grn = _last_tx_receipt_agg_subquery(date_from, date_to) if 'purchase' in selected else None
    sq_pret = _last_tx_purchase_return_agg_subquery(date_from, date_to) if 'purchase_return' in selected else None
    sale_sel = 'CAST(NULL AS VARCHAR2(10)) AS last_sale_date'
    sret_sel = 'CAST(NULL AS VARCHAR2(10)) AS last_sale_return_date'
    grn_sel = 'CAST(NULL AS VARCHAR2(10)) AS last_purchase_date'
    pret_sel = 'CAST(NULL AS VARCHAR2(10)) AS last_purchase_return_date'
    joins: List[str] = []
    if sq_sale:
        joins.append(f'LEFT JOIN ({sq_sale}) lt_sale ON lt_sale.ic = im.{ic}')
        sale_sel = "TO_CHAR(lt_sale.dt, 'YYYY-MM-DD') AS last_sale_date"
    if sq_sret:
        joins.append(f'LEFT JOIN ({sq_sret}) lt_sret ON lt_sret.ic = im.{ic}')
        sret_sel = "TO_CHAR(lt_sret.dt, 'YYYY-MM-DD') AS last_sale_return_date"
    if sq_grn:
        joins.append(f'LEFT JOIN ({sq_grn}) lt_grn ON lt_grn.ic = im.{ic}')
        grn_sel = "TO_CHAR(lt_grn.dt, 'YYYY-MM-DD') AS last_purchase_date"
    if sq_pret:
        joins.append(f'LEFT JOIN ({sq_pret}) lt_pret ON lt_pret.ic = im.{ic}')
        pret_sel = "TO_CHAR(lt_pret.dt, 'YYYY-MM-DD') AS last_purchase_return_date"
    params: Dict[str, Any] = {'lt_loc': loc, 'lt_cap': min(max(int(row_cap or 6000), 1), 15000)}
    if sq_sale or sq_sret:
        params['lt_rn_bill'] = _SALES_DETAILS_RESET_NO
    if sq_grn:
        params['lt_rn_rcpt'] = _LAST_TX_GRN_RESET_NO
    if sq_pret:
        params['lt_rn_pret'] = _PURCHASE_RETURN_DETAILS_RESET_NO
    if date_from:
        params['lt_df'] = date_from
    if date_to:
        params['lt_dt'] = date_to
    search_sql = ''
    qtxt = str(search or '').strip()
    if qtxt:
        like = f'%{qtxt.upper()}%'
        params['lt_q'] = like
        parts = [f'TO_CHAR(im.{ic}) LIKE :lt_q']
        if iname:
            parts.append(f'UPPER(im.{iname}) LIKE :lt_q')
        if raw_col:
            parts.append(f'UPPER(TRIM(TO_CHAR(im.{raw_col}))) LIKE :lt_q')
        if mfg_col:
            parts.append(f'UPPER(TRIM(TO_CHAR(im.{mfg_col}))) LIKE :lt_q')
        search_sql = ' AND (' + ' OR '.join(parts) + ') '
    category_sql = ''
    cat_filter = str(category_code or '').strip()
    if cat_filter and icat:
        category_sql = f' AND TO_CHAR(im.{icat}) = :lt_category '
        params['lt_category'] = cat_filter
    activity_parts: List[str] = []
    if sq_sale:
        activity_parts.append('lt_sale.dt IS NOT NULL')
    if sq_grn:
        activity_parts.append('lt_grn.dt IS NOT NULL')
    if sq_pret:
        activity_parts.append('lt_pret.dt IS NOT NULL')
    if sq_sret:
        activity_parts.append('lt_sret.dt IS NOT NULL')
    activity_sql = ' AND (' + ' OR '.join(activity_parts) + ') ' if activity_parts else ' AND 1=0 '
    join_sql = '\n'.join(joins)
    q = f"\n        SELECT * FROM (\n            SELECT\n                {raw_sel} AS rawabicode,\n                {mfg_sel} AS manufacturerid,\n                im.{ic} AS itemcode,\n                {name_sel} AS itemname,\n                {base_sel} AS baseuom,\n                {cost_sel} AS costprice,\n                {stock_sel} AS currentstock,\n                ({cost_sel} * {stock_sel}) AS stockvalue,\n                {cat_code_sel} AS categorycode,\n                NVL({cat_name_sel}, '') AS categoryname,\n                {sale_sel},\n                {grn_sel},\n                {pret_sel},\n                {sret_sel}\n            FROM {im} im\n            {join_cat}\n            {join_sql}\n            WHERE im.{iloc} = :lt_loc\n            {search_sql}\n            {category_sql}\n            {activity_sql}\n            ORDER BY im.{ic}\n        )\n        WHERE ROWNUM <= :lt_cap\n    "
    try:
        return _safe_rows(q, params) or []
    except Exception as e:
        logger.exception('Last transactions report failed: %s', e)
        return []

def _get_sales_detail_rows(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    bill_no: Optional[int] = None,
    customer_code: Optional[int] = None,
    bill_type: str = '',
    item_code: Optional[int] = None,
    txn_kind: str = '',
    order_no: str = '',
) -> List[Dict[str, Any]]:
    hdr, dtl = _sales_detail_hdr_dtl_tables()
    if not hdr or not dtl:
        return []
    h_no = _detect_column(hdr, ['BILLNO', 'billno'])
    h_date = _detect_column(hdr, ['BILLDATE', 'billdate'])
    h_time = _detect_column(hdr, ['BILLTIME', 'billtime'])
    h_type = _detect_column(hdr, ['BILLTYPE', 'billtype'])
    h_cust = _detect_column(hdr, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'customercode'])
    h_custname = _detect_column(hdr, ['CUSTOMERNAME', 'CUSTOMER_NAME', 'customername'])
    h_net = _detect_column(hdr, ['NETBILLAMOUNT', 'NET_BILL_AMOUNT', 'netbillamount'])
    h_disc = _detect_column(hdr, ['DISCOUNTAMOUNT', 'DISCOUNT_AMOUNT', 'discountamount'])
    h_rem = _detect_column(hdr, ['REMARKS', 'remarks'])
    h_orderno = _detect_column(hdr, ['ORDERNO', 'ORDER_NO', 'orderno'])
    h_salesman = _detect_column(hdr, ['SALESMANCODE', 'SALESMAN_CODE', 'salesmancode'])
    h_counter = _detect_column(hdr, ['COUNTERCODE', 'COUNTER_CODE', 'countercode'])
    h_status = _detect_column(hdr, ['BILLSTATUS', 'BILL_STATUS', 'billstatus'])
    h_loc = _detect_column(hdr, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    h_reset = _detect_column(hdr, ['RESETNO', 'RESET_NO', 'resetno'])
    h_del = _detect_column(hdr, ['DELFLAG', 'DEL_FLAG', 'delflag'])
    d_bill = _detect_column(dtl, ['BILLNO', 'billno'])
    d_sl = _detect_column(dtl, ['SLNO', 'slno'])
    d_item = _detect_column(dtl, ['ITEMCODE', 'ITEM_CODE', 'itemcode'])
    d_uom = _detect_column(dtl, ['UNITOFMEASUREMENT', 'UNIT_OF_MEASUREMENT', 'unitofmeasurement', 'UOM', 'uom'])
    d_qty = _detect_column(dtl, ['QUANTITY', 'quantity'])
    d_rate = _detect_column(dtl, ['RATE', 'rate'])
    d_disc = _detect_column(dtl, ['ITDISC', 'itdisc', 'DISCOUNT', 'discount'])
    d_amt = _detect_column(dtl, ['AMOUNT', 'amount', 'LINEAMOUNT', 'lineamount'])
    d_store = _detect_column(dtl, ['STORE', 'store'])
    d_det = _detect_column(dtl, ['ITEMDETAILS1', 'ITEM_DETAILS1', 'itemdetails1', 'ITEMNAME', 'itemname'])
    d_loc = _detect_column(dtl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    d_reset = _detect_column(dtl, ['RESETNO', 'RESET_NO', 'resetno'])
    if not h_no or not h_date or (not d_bill) or (not d_item):
        return []
    on_parts = [f'h.{h_no} = d.{d_bill}']
    if h_loc and d_loc:
        on_parts.append(f'h.{h_loc} = d.{d_loc}')
    if h_reset and d_reset:
        on_parts.append(f'h.{h_reset} = d.{d_reset}')
    where_parts: List[str] = []
    params: Dict[str, Any] = {}
    if h_loc:
        where_parts.append(f'h.{h_loc} = :loc')
        params['loc'] = _resolve_location_code()
    if h_reset:
        where_parts.append(f'h.{h_reset} = :rn')
        params['rn'] = _SALES_DETAILS_RESET_NO
    if h_del:
        where_parts.append(f"NVL(h.{h_del}, 'N') = 'N'")
    if h_status:
        where_parts.append(f"(h.{h_status} IS NULL OR UPPER(TRIM(h.{h_status})) <> 'V')")
    if bill_no:
        where_parts.append(f'h.{h_no} = :bno')
        params['bno'] = int(bill_no)
    order_q = str(order_no or '').strip()
    if order_q and h_orderno:
        where_parts.append(f"UPPER(TRIM(NVL(h.{h_orderno}, ''))) LIKE :ord")
        params['ord'] = f'%{order_q.upper()}%'
    if date_from:
        where_parts.append(f"TRUNC(h.{h_date}) >= TO_DATE(:df, 'YYYY-MM-DD')")
        params['df'] = date_from
    if date_to:
        where_parts.append(f"TRUNC(h.{h_date}) <= TO_DATE(:dt, 'YYYY-MM-DD')")
        params['dt'] = date_to
    bt = (bill_type or '').strip().upper()[:1]
    if bt and h_type:
        where_parts.append(f"UPPER(TRIM(NVL(h.{h_type}, ''))) = :bt")
        params['bt'] = bt
    tk = (txn_kind or '').strip().lower()
    if tk in ('sale', 'sales', 's'):
        tk = 'sale'
    elif tk in ('salesreturn', 'sales_return', 'return', 'sr', 'r'):
        tk = 'salesreturn'
    else:
        tk = 'all'
    if tk != 'all' and h_net:
        net_expr = f'NVL(h.{h_net}, 0)'
        if tk == 'sale':
            where_parts.append(f'{net_expr} > 0')
        else:
            where_parts.append(f'{net_expr} < 0')
    if customer_code is not None and customer_code >= 0 and h_cust:
        where_parts.append(f'h.{h_cust} = :cust')
        params['cust'] = int(customer_code)
    if item_code:
        where_parts.append(f'd.{d_item} = :item_code')
        params['item_code'] = int(item_code)
    cust_tbl = _detect_table(['CUSTOMERS', 'customers', 'CUSTOMER', 'customer'])
    cust_code_col = _detect_column(cust_tbl, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'customercode', 'CUST_CODE', 'cust_code']) if cust_tbl else None
    cust_name_col = _detect_column(cust_tbl, ['CUSTOMERNAME', 'CUSTOMER_NAME', 'customername', 'CUST_NAME', 'cust_name', 'NAME', 'name']) if cust_tbl else None
    join_cust = ''
    cust_disp = "''"
    if cust_tbl and cust_code_col and cust_name_col and h_cust:
        join_cust = f' LEFT JOIN {cust_tbl} c ON h.{h_cust} = c.{cust_code_col} '
        if h_custname:
            cust_disp = f"NVL(NULLIF(TRIM(h.{h_custname}), ''), NVL(c.{cust_name_col}, ''))"
        else:
            cust_disp = f"NVL(c.{cust_name_col}, '')"
    elif h_custname:
        cust_disp = f"NVL(TRIM(h.{h_custname}), '')"
    im = _detect_table(['ITEMMASTER', 'itemmaster'])
    im_item = _detect_column(im, ['ITEMCODE', 'ITEM_CODE', 'itemcode']) if im else None
    im_name = _detect_column(im, ['ITEMNAME', 'ITEM_NAME', 'itemname']) if im else None
    im_loc = _detect_column(im, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode']) if im else None
    join_im = ''
    item_name_expr = f"{(f'd.{d_det}' if d_det else 'CAST(NULL AS VARCHAR2(1))')}"
    if im and im_item and im_name:
        im_on = f'd.{d_item} = im.{im_item}'
        if im_loc and h_loc:
            im_on += f' AND im.{im_loc} = h.{h_loc}'
        join_im = f' LEFT JOIN {im} im ON {im_on} '
        if d_det:
            item_name_expr = f"NVL(NULLIF(TRIM(d.{d_det}), ''), im.{im_name})"
        else:
            item_name_expr = f"NVL(im.{im_name}, '')"
    if d_amt:
        line_amt_expr = f'NVL(d.{d_amt}, 0)'
    else:
        qx = f'NVL(d.{d_qty}, 0)' if d_qty else '0'
        rx = f'NVL(d.{d_rate}, 0)' if d_rate else '0'
        dx = f'NVL(d.{d_disc}, 0)' if d_disc else '0'
        line_amt_expr = f'({qx} * {rx} - {dx})'
    sl_expr = f'd.{d_sl}' if d_sl else '0'
    orderno_sel = f"NVL(TRIM(h.{h_orderno}), '')" if h_orderno else "''"
    q = f"""\n        SELECT\n            h.{h_no} AS billno,\n            h.{h_date} AS billdate,\n            {(f'h.{h_time}' if h_time else 'CAST(NULL AS VARCHAR2(20))')} AS billtime,\n            {(f'h.{h_type}' if h_type else "''")} AS billtype,\n            {(f'h.{h_cust}' if h_cust else 'CAST(NULL AS NUMBER)')} AS customercode,\n            {cust_disp} AS customername,\n            {orderno_sel} AS orderno,\n            NVL({(f'h.{h_net}' if h_net else '0')}, 0) AS netbillamount,\n            NVL({(f'h.{h_disc}' if h_disc else '0')}, 0) AS hdr_discount,\n            {(f'h.{h_rem}' if h_rem else "''")} AS hdr_remarks,\n            {(f'h.{h_salesman}' if h_salesman else 'CAST(NULL AS NUMBER)')} AS salesmancode,\n            {(f'h.{h_counter}' if h_counter else 'CAST(NULL AS NUMBER)')} AS countercode,\n            {(f'h.{h_status}' if h_status else "''")} AS billstatus,\n            {sl_expr} AS slno,\n            d.{d_item} AS itemcode,\n            {(f"NVL(d.{d_store}, '')" if d_store else "''")} AS storecode,\n            {item_name_expr} AS itemname,\n            {(f"NVL(d.{d_uom}, '')" if d_uom else "''")} AS uom,\n            NVL({(f'd.{d_qty}' if d_qty else '0')}, 0) AS quantity,\n            NVL({(f'd.{d_rate}' if d_rate else '0')}, 0) AS rate,\n            NVL({(f'd.{d_disc}' if d_disc else '0')}, 0) AS linediscount,\n            ({line_amt_expr}) AS lineamount\n        FROM {hdr} h\n        INNER JOIN {dtl} d ON {' AND '.join(on_parts)}\n        {join_cust}\n        {join_im}\n        WHERE {(' AND '.join(where_parts) if where_parts else '1=1')}\n        ORDER BY h.{h_no} DESC, {sl_expr} ASC\n    """
    try:
        return _safe_rows(q, params) or []
    except Exception as e:
        logger.exception('Sales details report failed: %s', e)
        return []

def _get_sales_detail_customer_options(search: str = '', limit: int = 300) -> List[Dict[str, Any]]:
    tbl = _detect_table(['CUSTOMERS', 'customers', 'CUSTOMER', 'customer'])
    if not tbl:
        return []
    code_col = _detect_column(tbl, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'customercode', 'CUST_CODE', 'cust_code'])
    name_col = _detect_column(tbl, ['CUSTOMERNAME', 'CUSTOMER_NAME', 'customername', 'CUST_NAME', 'cust_name', 'NAME', 'name'])
    if not code_col:
        return []
    cap = min(max(int(limit or 300), 50), 800)
    name_sel = f'{name_col} AS customername' if name_col else "'' AS customername"
    where = ['1=1']
    params: Dict[str, Any] = {}
    q_text = str(search or '').strip().upper()
    if q_text:
        params['q'] = f'%{q_text}%'
        if name_col:
            where.append(f"(TO_CHAR({code_col}) LIKE :q OR UPPER(NVL({name_col}, '')) LIKE :q)")
        else:
            where.append(f'TO_CHAR({code_col}) LIKE :q')
    q = f"""
        SELECT * FROM (
            SELECT DISTINCT {code_col} AS customercode, {name_sel}
            FROM {tbl}
            WHERE {' AND '.join(where)}
            ORDER BY {code_col}
        ) WHERE ROWNUM <= {cap}
    """
    try:
        _, rows = _fetch_rows(q, params)
    except Exception:
        return []
    out: List[Dict[str, Any]] = []
    for r in rows or []:
        try:
            c = int(float(r.get('customercode') or 0))
        except (TypeError, ValueError):
            continue
        if c < 0:
            continue
        out.append({'customercode': c, 'customername': str(r.get('customername') or '').strip()})
    return out

def _get_sales_detail_item_options(search: str='', limit: int=300) -> List[Dict[str, str]]:
    hdr, dtl = _sales_detail_hdr_dtl_tables()
    if not dtl:
        return []
    d_item = _detect_column(dtl, ['ITEMCODE', 'ITEM_CODE', 'itemcode'])
    d_loc = _detect_column(dtl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    d_reset = _detect_column(dtl, ['RESETNO', 'RESET_NO', 'resetno'])
    if not d_item:
        return []
    where = ['1=1']
    params: Dict[str, Any] = {}
    if d_loc:
        where.append(f'{d_loc} = :loc')
        params['loc'] = _resolve_location_code()
    if d_reset:
        where.append(f'{d_reset} = :rn')
        params['rn'] = _SALES_DETAILS_RESET_NO
    im = _detect_table(['ITEMMASTER', 'itemmaster'])
    im_item = _detect_column(im, ['ITEMCODE', 'ITEM_CODE', 'itemcode']) if im else None
    im_name = _detect_column(im, ['ITEMNAME', 'ITEM_NAME', 'itemname']) if im else None
    im_loc = _detect_column(im, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode']) if im else None
    q_text = str(search or '').strip().upper()
    if q_text:
        params['q'] = f'%{q_text}%'
        if im and im_item and im_name and im_loc and d_loc:
            where.append(f"(TO_CHAR(d.{d_item}) LIKE :q OR UPPER(NVL(im.{im_name},'')) LIKE :q)")
        else:
            where.append(f'TO_CHAR(d.{d_item}) LIKE :q')
    cap = min(max(int(limit or 300), 50), 500)
    if im and im_item and im_name and im_loc and d_loc:
        inner_from = f'\n            {dtl} d\n            LEFT JOIN {im} im ON d.{d_item} = im.{im_item} AND d.{d_loc} = im.{im_loc}\n        '
        name_sel = f"NVL(im.{im_name}, '')"
    else:
        inner_from = f'{dtl} d'
        name_sel = "''"
    q = f"\n        SELECT * FROM (\n            SELECT DISTINCT d.{d_item} AS itemcode, {name_sel} AS itemname\n            FROM {inner_from}\n            WHERE {' AND '.join(where)}\n            ORDER BY d.{d_item}\n        )\n        WHERE ROWNUM <= {cap}\n    "
    try:
        rows = _safe_rows(q, params) or []
    except Exception:
        return []
    out: List[Dict[str, str]] = []
    for r in rows:
        code = str(r.get('itemcode') or '').strip()
        if not code:
            continue
        out.append({'itemcode': code, 'itemname': str(r.get('itemname') or '').strip()})
    return out

def _get_store_transfer_detail_rows(date_from: Optional[str]=None, date_to: Optional[str]=None, transfer_no: Optional[int]=None, from_store: str='', to_store: str='', status: str='', item_code: Optional[int]=None) -> List[Dict[str, Any]]:
    hdr = _detect_table(['STKTRFHDR', 'stktrfhdr'])
    dtl = _detect_table(['STKTRFDTL', 'stktrfdtl'])
    if not hdr or not dtl:
        return []
    h_no = _detect_column(hdr, ['TRANSFERNO', 'transferno']) or 'TRANSFERNO'
    h_date = _detect_column(hdr, ['TRANSFERDATE', 'transferdate']) or 'TRANSFERDATE'
    h_from = _detect_column(hdr, ['FROMSTORE', 'fromstore'])
    h_to = _detect_column(hdr, ['TOSTORE', 'tostore'])
    h_status = _detect_column(hdr, ['STATUS', 'status'])
    h_rem = _detect_column(hdr, ['REMARKS', 'remarks'])
    h_created = _detect_column(hdr, ['CREATEDBY', 'createdby', 'CREATED_BY'])
    h_transferred = _detect_column(hdr, ['TRANSFERREDBY', 'transferedby', 'TRANSFERRED_BY', 'TRANSFERBY', 'transferby'])
    h_approved = _detect_column(hdr, ['APPROVEDBY', 'approvedby', 'APPROVED_BY'])
    h_loc = _detect_column(hdr, ['LOCATIONCODE', 'locationcode', 'LOCATION_CODE'])
    d_no = _detect_column(dtl, ['TRANSFERNO', 'transferno']) or 'TRANSFERNO'
    d_sl = _detect_column(dtl, ['SLNO', 'slno']) or 'SLNO'
    d_item = _detect_column(dtl, ['ITEMCODE', 'itemcode'])
    d_name = _detect_column(dtl, ['ITEMNAME', 'itemname'])
    d_uom = _detect_column(dtl, ['UNITOFMEASUREMENT', 'unitofmeasurement'])
    d_avail = _detect_column(dtl, ['AVAILABLEQTY', 'availableqty'])
    d_qty = _detect_column(dtl, ['TRANSFERQTY', 'transferqty'])
    d_base = _detect_column(dtl, ['BASEQTY', 'baseqty'])
    d_rem = _detect_column(dtl, ['LINEREMARKS', 'lineremarks'])
    d_loc = _detect_column(dtl, ['LOCATIONCODE', 'locationcode', 'LOCATION_CODE'])
    if not d_item:
        return []
    where = [f'h.{h_no} = d.{d_no}']
    params: Dict[str, Any] = {}
    if h_loc and d_loc:
        where.append(f'h.{h_loc} = d.{d_loc}')
        where.append(f'h.{h_loc} = :loc')
        params['loc'] = _resolve_location_code()
    elif h_loc:
        where.append(f'h.{h_loc} = :loc')
        params['loc'] = _resolve_location_code()
    if transfer_no:
        where.append(f'h.{h_no} = :tno')
        params['tno'] = int(transfer_no)
    if date_from:
        where.append(f"TRUNC(h.{h_date}) >= TO_DATE(:df, 'YYYY-MM-DD')")
        params['df'] = date_from
    if date_to:
        where.append(f"TRUNC(h.{h_date}) <= TO_DATE(:dt, 'YYYY-MM-DD')")
        params['dt'] = date_to
    from_filter_expr = f'h.{h_from}' if h_from else "''"
    to_filter_expr = f'h.{h_to}' if h_to else "''"
    status_filter_expr = f'h.{h_status}' if h_status else "'C'"
    if from_store:
        where.append(f"UPPER(TRIM(NVL({from_filter_expr}, ''))) = :fs")
        params['fs'] = str(from_store).strip().upper()
    if to_store:
        where.append(f"UPPER(TRIM(NVL({to_filter_expr}, ''))) = :ts")
        params['ts'] = str(to_store).strip().upper()
    status_val = (status or '').strip().upper()[:1]
    if status_val:
        where.append(f"UPPER(TRIM(NVL({status_filter_expr}, 'C'))) = :st")
        params['st'] = status_val
    if item_code:
        where.append(f'd.{d_item} = :item_code')
        params['item_code'] = int(item_code)
    q = f"""\n        SELECT\n            h.{h_no} AS transferno,\n            h.{h_date} AS transferdate,\n            {(f'h.{h_from}' if h_from else "''")} AS fromstore,\n            {(f'h.{h_to}' if h_to else "''")} AS tostore,\n            {(f'h.{h_status}' if h_status else "'C'")} AS status,\n            {(f'h.{h_created}' if h_created else "''")} AS createdby,\n            {(f'h.{h_transferred}' if h_transferred else "''")} AS transferredby,\n            {(f'h.{h_approved}' if h_approved else "''")} AS approvedby,\n            {(f'h.{h_rem}' if h_rem else "''")} AS remarks,\n            d.{d_sl} AS slno,\n            d.{d_item} AS itemcode,\n            {(f'd.{d_name}' if d_name else "''")} AS itemname,\n            {(f'd.{d_uom}' if d_uom else "''")} AS uom,\n            NVL({(f'd.{d_avail}' if d_avail else '0')}, 0) AS availableqty,\n            NVL({(f'd.{d_qty}' if d_qty else '0')}, 0) AS transferqty,\n            NVL({(f'd.{d_base}' if d_base else '0')}, 0) AS baseqty,\n            {(f'd.{d_rem}' if d_rem else "''")} AS lineremarks\n        FROM {hdr} h\n        JOIN {dtl} d ON {' AND '.join(where)}\n        ORDER BY h.{h_no} DESC, d.{d_sl} ASC\n    """
    try:
        return _safe_rows(q, params) or []
    except Exception as e:
        logger.exception('Store transfer details report failed: %s', e)
        return []

def _get_store_transfer_detail_store_options() -> List[Dict[str, str]]:
    tbl = resolve_warehouse_master_table()
    if not tbl:
        return []
    code_col = _detect_column(tbl, ['DBCODE', 'dbcode'])
    desc_col = _detect_column(tbl, ['DESCRIPTION', 'description', 'LOCATION', 'location', 'LOCATIONNAME', 'locationname', 'NAME', 'name'])
    if not code_col:
        return []
    desc_expr = f'{desc_col} AS description' if desc_col else "'' AS description"
    q = f'SELECT {code_col} AS dbcode, {desc_expr} FROM {tbl} ORDER BY {code_col}'
    try:
        _, rows = _fetch_rows(q, {})
    except Exception:
        return []
    out: List[Dict[str, str]] = []
    seen: set = set()
    for r in rows:
        code = str(r.get('dbcode') or '').strip().upper()
        if not code or code in seen:
            continue
        seen.add(code)
        out.append({'code': code, 'description': str(r.get('description') or '').strip()})
    return out

def _get_store_transfer_detail_item_options(search: str='', limit: int=300) -> List[Dict[str, str]]:
    dtl = _detect_table(['STKTRFDTL', 'stktrfdtl'])
    if not dtl:
        return []
    d_item = _detect_column(dtl, ['ITEMCODE', 'itemcode'])
    d_name = _detect_column(dtl, ['ITEMNAME', 'itemname'])
    d_loc = _detect_column(dtl, ['LOCATIONCODE', 'locationcode', 'LOCATION_CODE'])
    if not d_item:
        return []
    where = ['1=1']
    params: Dict[str, Any] = {}
    if d_loc:
        where.append(f'{d_loc} = :loc')
        params['loc'] = _resolve_location_code()
    q_text = str(search or '').strip().upper()
    if q_text:
        params['q'] = f'%{q_text}%'
        if d_name:
            where.append(f"(TO_CHAR({d_item}) LIKE :q OR UPPER(NVL({d_name}, '')) LIKE :q)")
        else:
            where.append(f'TO_CHAR({d_item}) LIKE :q')
    cap = min(max(int(limit or 300), 50), 500)
    q = f"""\n        SELECT * FROM (\n            SELECT DISTINCT\n                {d_item} AS itemcode,\n                {(d_name if d_name else "''")} AS itemname\n            FROM {dtl}\n            WHERE {' AND '.join(where)}\n            ORDER BY {d_item}\n        )\n        WHERE ROWNUM <= {cap}\n    """
    try:
        rows = _safe_rows(q, params) or []
    except Exception:
        return []
    out: List[Dict[str, str]] = []
    for r in rows:
        code = str(r.get('itemcode') or '').strip()
        if not code:
            continue
        out.append({'itemcode': code, 'itemname': str(r.get('itemname') or '').strip()})
    return out

@bp.route('/reports/store-transfer-details', methods=['GET'])
def store_transfer_details():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    date_from = (request.args.get('date_from') or '').strip()
    date_to = (request.args.get('date_to') or '').strip()
    date_from, date_to = _default_report_date_range(date_from, date_to)
    transfer_no_raw = (request.args.get('transfer_no') or '').strip()
    from_store = (request.args.get('from_store') or '').strip().upper()
    to_store = (request.args.get('to_store') or '').strip().upper()
    status = (request.args.get('status') or '').strip().upper()[:1]
    item_code_raw = (request.args.get('item_code') or '').strip()
    transfer_no: Optional[int] = None
    if transfer_no_raw and transfer_no_raw.isdigit():
        transfer_no = int(transfer_no_raw)
    item_code: Optional[int] = None
    if item_code_raw and item_code_raw.isdigit():
        item_code = int(item_code_raw)
    rows = _get_store_transfer_detail_rows(date_from=date_from or None, date_to=date_to or None, transfer_no=transfer_no, from_store=from_store, to_store=to_store, status=status, item_code=item_code)
    store_options = _get_store_transfer_detail_store_options()
    selected_item_label = ''
    if item_code_raw:
        for opt in _get_store_transfer_detail_item_options(search=item_code_raw, limit=100):
            if str(opt.get('itemcode') or '').strip() == item_code_raw:
                name = str(opt.get('itemname') or '').strip()
                selected_item_label = f'{item_code_raw} - {name}' if name else item_code_raw
                break
    return render_template('reports/store_transfer_details_report.html', rows=rows, store_options=store_options, filters={'date_from': date_from, 'date_to': date_to, 'transfer_no': transfer_no_raw, 'from_store': from_store, 'to_store': to_store, 'status': status, 'item_code': item_code_raw, 'item_label': selected_item_label})

@bp.route('/reports/store-transfer-details/api/items', methods=['GET'])
def store_transfer_details_items_api():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    search = (request.args.get('search') or '').strip()
    items = _get_store_transfer_detail_item_options(search=search, limit=300)
    return jsonify({'success': True, 'items': items})

@bp.route('/reports/store-transfer-details/export-excel', methods=['GET'])
def store_transfer_details_export_excel():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    date_from = (request.args.get('date_from') or '').strip()
    date_to = (request.args.get('date_to') or '').strip()
    date_from, date_to = _default_report_date_range(date_from, date_to)
    transfer_no_raw = (request.args.get('transfer_no') or '').strip()
    from_store = (request.args.get('from_store') or '').strip().upper()
    to_store = (request.args.get('to_store') or '').strip().upper()
    status = (request.args.get('status') or '').strip().upper()[:1]
    item_code_raw = (request.args.get('item_code') or '').strip()
    transfer_no: Optional[int] = int(transfer_no_raw) if transfer_no_raw.isdigit() else None
    item_code: Optional[int] = int(item_code_raw) if item_code_raw.isdigit() else None
    rows = _get_store_transfer_detail_rows(date_from=date_from or None, date_to=date_to or None, transfer_no=transfer_no, from_store=from_store, to_store=to_store, status=status, item_code=item_code)
    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output)
    writer.writerow(['Transfer No', 'Date', 'Status', 'From Store', 'To Store', 'Created By', 'Transferred By', 'Approved By', 'Header Remarks', 'Sl No', 'Item Code', 'Item Name', 'UOM', 'Available Qty', 'Transfer Qty', 'Base Qty', 'Line Remarks'])
    for r in rows:
        dtv = r.get('transferdate')
        dt = dtv.strftime('%Y-%m-%d %H:%M:%S') if hasattr(dtv, 'strftime') else str(dtv or '')
        st = str(r.get('status') or '').strip().upper()
        st_label = 'Created' if st == 'C' else 'Transferred' if st in {'T', 'P'} else 'Approved' if st == 'A' else st
        writer.writerow([r.get('transferno') or '', dt, st_label, r.get('fromstore') or '', r.get('tostore') or '', r.get('createdby') or '', r.get('transferredby') or '', r.get('approvedby') or '', r.get('remarks') or '', r.get('slno') or '', r.get('itemcode') or '', r.get('itemname') or '', r.get('uom') or '', f"{float(r.get('availableqty') or 0):.3f}", f"{float(r.get('transferqty') or 0):.3f}", f"{float(r.get('baseqty') or 0):.3f}", r.get('lineremarks') or ''])
    filename = f"store_transfer_details_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename={filename}'})

@bp.route('/reports/purchase-details', methods=['GET'])
def purchase_details():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    date_from = (request.args.get('date_from') or '').strip()
    date_to = (request.args.get('date_to') or '').strip()
    date_from, date_to = _default_purchase_report_date_range(date_from, date_to)
    lpo_no_raw = (request.args.get('lpo_no') or '').strip()
    supplier_raw = (request.args.get('supplier_code') or '').strip()
    item_code_raw = (request.args.get('item_code') or '').strip()
    lpo_no: Optional[Any] = parse_lpono_from_request(lpo_no_raw) if lpo_no_raw and lpono_is_valid(lpo_no_raw) else None
    supplier_code: Optional[int] = None
    if supplier_raw.isdigit():
        supplier_code = int(supplier_raw)
    item_code: Optional[int] = int(item_code_raw) if item_code_raw.isdigit() else None
    rows = _get_purchase_detail_rows(date_from=date_from or None, date_to=date_to or None, lpo_no=lpo_no, supplier_code=supplier_code, item_code=item_code)
    selected_supplier_label = ''
    if supplier_raw:
        for opt in _get_purchase_detail_supplier_options(search=supplier_raw, limit=100):
            if str(opt.get('suppliercode') or '').strip() == supplier_raw:
                name = str(opt.get('suppliername') or '').strip()
                selected_supplier_label = f'{supplier_raw} — {name}' if name else supplier_raw
                break
        if not selected_supplier_label:
            selected_supplier_label = supplier_raw
    selected_item_label = ''
    if item_code_raw:
        for opt in _get_purchase_detail_item_options(search=item_code_raw, limit=100):
            if str(opt.get('itemcode') or '').strip() == item_code_raw:
                name = str(opt.get('itemname') or '').strip()
                selected_item_label = f'{item_code_raw} — {name}' if name else item_code_raw
                break
    return render_template(
        'reports/purchase_details_report.html',
        rows=rows,
        filters={
            'date_from': date_from,
            'date_to': date_to,
            'lpo_no': lpo_no_raw,
            'supplier_code': supplier_raw,
            'supplier_label': selected_supplier_label,
            'item_code': item_code_raw,
            'item_label': selected_item_label,
        },
    )

@bp.route('/reports/purchase-details/api/suppliers', methods=['GET'])
def purchase_details_suppliers_api():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    search = (request.args.get('search') or '').strip()
    suppliers = _get_purchase_detail_supplier_options(search=search, limit=300)
    return jsonify({'success': True, 'suppliers': suppliers})

@bp.route('/reports/purchase-details/api/items', methods=['GET'])
def purchase_details_items_api():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    search = (request.args.get('search') or '').strip()
    items = _get_purchase_detail_item_options(search=search, limit=300)
    return jsonify({'success': True, 'items': items})

@bp.route('/reports/purchase-details/export-excel', methods=['GET'])
def purchase_details_export_excel():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    date_from = (request.args.get('date_from') or '').strip()
    date_to = (request.args.get('date_to') or '').strip()
    date_from, date_to = _default_purchase_report_date_range(date_from, date_to)
    lpo_no_raw = (request.args.get('lpo_no') or '').strip()
    supplier_raw = (request.args.get('supplier_code') or '').strip()
    item_code_raw = (request.args.get('item_code') or '').strip()
    lpo_no: Optional[Any] = parse_lpono_from_request(lpo_no_raw) if lpo_no_raw and lpono_is_valid(lpo_no_raw) else None
    supplier_code: Optional[int] = int(supplier_raw) if supplier_raw.isdigit() else None
    item_code: Optional[int] = int(item_code_raw) if item_code_raw.isdigit() else None
    rows = _get_purchase_detail_rows(date_from=date_from or None, date_to=date_to or None, lpo_no=lpo_no, supplier_code=supplier_code, item_code=item_code)

    def _foc_label(v: Any) -> str:
        s = str(v).strip().upper()
        if s in ('1', 'Y', 'TRUE'):
            return 'Y'
        return 'N'
    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output)
    writer.writerow(['LPO No', 'LPO Date', 'Supplier Code', 'Supplier Name', 'Approval Status', 'LPO Amount', 'Hdr Discount', 'Hdr Other Charge', 'Header Remarks', 'Sl No', 'Item Code', 'Barcode', 'Item Name', 'UOM', 'Quantity', 'Rate', 'Bonus', 'Line Discount', 'Line Amount', 'Base Qty', 'FOC', 'Line Other Charge', 'Landing Cost'])
    for r in rows:
        dtv = r.get('lpodate')
        dt = dtv.strftime('%Y-%m-%d %H:%M:%S') if hasattr(dtv, 'strftime') else str(dtv or '')
        writer.writerow([r.get('lpono') or '', dt, r.get('suppliercode') or '', r.get('suppliername') or '', r.get('approval_status') or '', f"{float(r.get('lpoamount') or 0):.4f}", f"{float(r.get('hdr_discount') or 0):.4f}", f"{float(r.get('hdr_othercharge') or 0):.4f}", r.get('hdr_remarks') or '', r.get('slno') or '', r.get('itemcode') or '', r.get('barcode') or '', r.get('itemname') or '', r.get('uom') or '', f"{float(r.get('quantity') or 0):.4f}", f"{float(r.get('rate') or 0):.4f}", f"{float(r.get('bonus') or 0):.4f}", f"{float(r.get('linediscount') or 0):.4f}", f"{float(r.get('amount') or 0):.4f}", f"{float(r.get('baseqty') or 0):.4f}", _foc_label(r.get('foc_raw')), f"{float(r.get('line_othercharge') or 0):.4f}", f"{float(r.get('landingcost') or 0):.4f}"])
    filename = f"purchase_details_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename={filename}'})

def _grn_inventory_posted_label(val: Any) -> str:
    s = str(val or '').strip().upper()
    if s in ('1', 'Y', 'TRUE', 'P', 'POSTED'):
        return 'Posted'
    if s in ('0', 'N', 'FALSE', 'D', 'DRAFT'):
        return 'Draft'
    return s

def _fmt_report_date(val: Any) -> str:
    if val is None:
        return ''
    if hasattr(val, 'strftime'):
        return val.strftime('%Y-%m-%d')
    return str(val or '')[:10]

@bp.route('/reports/grn-details', methods=['GET'])
def grn_details():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    date_from = (request.args.get('date_from') or '').strip()
    date_to = (request.args.get('date_to') or '').strip()
    date_from, date_to = _default_purchase_report_date_range(date_from, date_to)
    receipt_no_raw = (request.args.get('receipt_no') or '').strip()
    lpo_no_raw = (request.args.get('lpo_no') or '').strip()
    supplier_raw = (request.args.get('supplier_code') or '').strip()
    item_code_raw = (request.args.get('item_code') or '').strip()
    receipt_no: Optional[Any] = parse_receiptno_from_request(receipt_no_raw) if receipt_no_raw and receiptno_is_valid(receipt_no_raw) else None
    lpo_no: Optional[Any] = parse_lpono_from_request(lpo_no_raw) if lpo_no_raw and lpono_is_valid(lpo_no_raw) else None
    supplier_code: Optional[int] = int(supplier_raw) if supplier_raw.isdigit() else None
    item_code: Optional[int] = int(item_code_raw) if item_code_raw.isdigit() else None
    rows = _get_grn_detail_rows(
        date_from=date_from or None, date_to=date_to or None,
        receipt_no=receipt_no, lpo_no=lpo_no,
        supplier_code=supplier_code, item_code=item_code,
    )
    selected_supplier_label = ''
    if supplier_raw:
        for opt in _get_purchase_detail_supplier_options(search=supplier_raw, limit=100):
            if str(opt.get('suppliercode') or '').strip() == supplier_raw:
                name = str(opt.get('suppliername') or '').strip()
                selected_supplier_label = f'{supplier_raw} — {name}' if name else supplier_raw
                break
        if not selected_supplier_label:
            selected_supplier_label = supplier_raw
    selected_item_label = ''
    if item_code_raw:
        for opt in _get_grn_detail_item_options(search=item_code_raw, limit=100):
            if str(opt.get('itemcode') or '').strip() == item_code_raw:
                name = str(opt.get('itemname') or '').strip()
                selected_item_label = f'{item_code_raw} — {name}' if name else item_code_raw
                break
    return render_template(
        'reports/grn_details_report.html',
        rows=rows,
        filters={
            'date_from': date_from,
            'date_to': date_to,
            'receipt_no': receipt_no_raw,
            'lpo_no': lpo_no_raw,
            'supplier_code': supplier_raw,
            'supplier_label': selected_supplier_label,
            'item_code': item_code_raw,
            'item_label': selected_item_label,
        },
    )

@bp.route('/reports/grn-details/api/suppliers', methods=['GET'])
def grn_details_suppliers_api():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    search = (request.args.get('search') or '').strip()
    suppliers = _get_purchase_detail_supplier_options(search=search, limit=300)
    return jsonify({'success': True, 'suppliers': suppliers})

@bp.route('/reports/grn-details/api/items', methods=['GET'])
def grn_details_items_api():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    search = (request.args.get('search') or '').strip()
    items = _get_grn_detail_item_options(search=search, limit=300)
    return jsonify({'success': True, 'items': items})

@bp.route('/reports/grn-details/export-excel', methods=['GET'])
def grn_details_export_excel():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    date_from = (request.args.get('date_from') or '').strip()
    date_to = (request.args.get('date_to') or '').strip()
    date_from, date_to = _default_purchase_report_date_range(date_from, date_to)
    receipt_no_raw = (request.args.get('receipt_no') or '').strip()
    lpo_no_raw = (request.args.get('lpo_no') or '').strip()
    supplier_raw = (request.args.get('supplier_code') or '').strip()
    item_code_raw = (request.args.get('item_code') or '').strip()
    receipt_no: Optional[Any] = parse_receiptno_from_request(receipt_no_raw) if receipt_no_raw and receiptno_is_valid(receipt_no_raw) else None
    lpo_no: Optional[Any] = parse_lpono_from_request(lpo_no_raw) if lpo_no_raw and lpono_is_valid(lpo_no_raw) else None
    supplier_code: Optional[int] = int(supplier_raw) if supplier_raw.isdigit() else None
    item_code: Optional[int] = int(item_code_raw) if item_code_raw.isdigit() else None
    rows = _get_grn_detail_rows(
        date_from=date_from or None, date_to=date_to or None,
        receipt_no=receipt_no, lpo_no=lpo_no,
        supplier_code=supplier_code, item_code=item_code,
    )

    def _foc_label(v: Any) -> str:
        s = str(v).strip().upper()
        if s in ('1', 'Y', 'TRUE'):
            return 'Y'
        return 'N'
    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output)
    writer.writerow([
        'Receipt No', 'Receipt Date', 'LPO No', 'Invoice No', 'Invoice Date', 'Posting Date', 'Inventory Posted',
        'Warehouse', 'Supplier Code', 'Supplier Name', 'Receipt Amount', 'Hdr Discount', 'Hdr Other Charge',
        'Header Remarks', 'Sl No', 'Item Code', 'Barcode', 'Item Name', 'UOM', 'Quantity', 'Rate', 'Bonus',
        'Line Discount', 'Line Amount', 'Base Qty', 'FOC', 'Line Other Charge', 'Landing Cost', 'Batch', 'Mfg Date', 'Expiry Date',
    ])
    for r in rows:
        wh = str(r.get('warehouse_name') or '').strip()
        if not wh and r.get('warehouse_id') is not None:
            wh = str(r.get('warehouse_id') or '')
        writer.writerow([
            r.get('receiptno') or '',
            _fmt_report_date(r.get('receiptdate')),
            r.get('lpono') or '',
            r.get('invoiceno') or '',
            _fmt_report_date(r.get('invoicedate')),
            _fmt_report_date(r.get('postingdate')),
            _grn_inventory_posted_label(r.get('inventory_posted')),
            wh,
            r.get('suppliercode') or '',
            r.get('suppliername') or '',
            f"{float(r.get('receiptamount') or 0):.4f}",
            f"{float(r.get('hdr_discount') or 0):.4f}",
            f"{float(r.get('hdr_othercharge') or 0):.4f}",
            r.get('hdr_remarks') or '',
            r.get('slno') or '',
            r.get('itemcode') or '',
            r.get('barcode') or '',
            r.get('itemname') or '',
            r.get('uom') or '',
            f"{float(r.get('quantity') or 0):.4f}",
            f"{float(r.get('rate') or 0):.4f}",
            f"{float(r.get('bonus') or 0):.4f}",
            f"{float(r.get('linediscount') or 0):.4f}",
            f"{float(r.get('amount') or 0):.4f}",
            f"{float(r.get('baseqty') or 0):.4f}",
            _foc_label(r.get('foc_raw')),
            f"{float(r.get('line_othercharge') or 0):.4f}",
            f"{float(r.get('landingcost') or 0):.4f}",
            r.get('batch_no') or '',
            _fmt_report_date(r.get('mfg_date')),
            _fmt_report_date(r.get('expiry_date')),
        ])
    filename = f"grn_details_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename={filename}'})

def _purchase_return_type_label(code: Any) -> str:
    c = str(code or '').strip().upper()[:1]
    if c == 'P':
        return 'Purchase return'
    if c == 'D':
        return 'Debit note'
    return c or ''

@bp.route('/reports/purchase-return-details', methods=['GET'])
def purchase_return_details():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    date_from = (request.args.get('date_from') or '').strip()
    date_to = (request.args.get('date_to') or '').strip()
    date_from, date_to = _default_purchase_report_date_range(date_from, date_to)
    grn_raw = (request.args.get('goods_return_no') or '').strip()
    receipt_raw = (request.args.get('receipt_no') or '').strip()
    supplier_raw = (request.args.get('supplier_code') or '').strip()
    return_type_raw = (request.args.get('return_type') or '').strip().upper()[:1]
    item_code_raw = (request.args.get('item_code') or '').strip()
    goods_return_no: Optional[int] = int(grn_raw) if grn_raw.isdigit() else None
    receipt_no: Optional[int] = int(receipt_raw) if receipt_raw.isdigit() else None
    supplier_code: Optional[int] = None
    if supplier_raw.isdigit():
        supplier_code = int(supplier_raw)
    item_code: Optional[int] = int(item_code_raw) if item_code_raw.isdigit() else None
    return_type_f = return_type_raw if return_type_raw else None
    rows = _get_purchase_return_detail_rows(date_from=date_from or None, date_to=date_to or None, goods_return_no=goods_return_no, supplier_code=supplier_code, receipt_no=receipt_no, return_type=return_type_f, item_code=item_code)
    selected_supplier_label = ''
    if supplier_raw:
        for opt in _get_purchase_detail_supplier_options(search=supplier_raw, limit=100):
            if str(opt.get('suppliercode') or '').strip() == supplier_raw:
                name = str(opt.get('suppliername') or '').strip()
                selected_supplier_label = f'{supplier_raw} — {name}' if name else supplier_raw
                break
        if not selected_supplier_label:
            selected_supplier_label = supplier_raw
    selected_item_label = ''
    if item_code_raw:
        for opt in _get_purchase_return_detail_item_options(search=item_code_raw, limit=100):
            if str(opt.get('itemcode') or '').strip() == item_code_raw:
                name = str(opt.get('itemname') or '').strip()
                selected_item_label = f'{item_code_raw} — {name}' if name else item_code_raw
                break
    return render_template(
        'reports/purchase_return_details_report.html',
        rows=rows,
        filters={
            'date_from': date_from,
            'date_to': date_to,
            'goods_return_no': grn_raw,
            'receipt_no': receipt_raw,
            'supplier_code': supplier_raw,
            'supplier_label': selected_supplier_label,
            'return_type': return_type_raw,
            'item_code': item_code_raw,
            'item_label': selected_item_label,
        },
    )

@bp.route('/reports/purchase-return-details/api/suppliers', methods=['GET'])
def purchase_return_details_suppliers_api():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    search = (request.args.get('search') or '').strip()
    suppliers = _get_purchase_detail_supplier_options(search=search, limit=300)
    return jsonify({'success': True, 'suppliers': suppliers})

@bp.route('/reports/purchase-return-details/api/items', methods=['GET'])
def purchase_return_details_items_api():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    search = (request.args.get('search') or '').strip()
    items = _get_purchase_return_detail_item_options(search=search, limit=300)
    return jsonify({'success': True, 'items': items})

@bp.route('/reports/purchase-return-details/export-excel', methods=['GET'])
def purchase_return_details_export_excel():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    date_from = (request.args.get('date_from') or '').strip()
    date_to = (request.args.get('date_to') or '').strip()
    date_from, date_to = _default_purchase_report_date_range(date_from, date_to)
    grn_raw = (request.args.get('goods_return_no') or '').strip()
    receipt_raw = (request.args.get('receipt_no') or '').strip()
    supplier_raw = (request.args.get('supplier_code') or '').strip()
    return_type_raw = (request.args.get('return_type') or '').strip().upper()[:1]
    item_code_raw = (request.args.get('item_code') or '').strip()
    goods_return_no: Optional[int] = int(grn_raw) if grn_raw.isdigit() else None
    receipt_no: Optional[int] = int(receipt_raw) if receipt_raw.isdigit() else None
    supplier_code: Optional[int] = int(supplier_raw) if supplier_raw.isdigit() else None
    item_code: Optional[int] = int(item_code_raw) if item_code_raw.isdigit() else None
    return_type_f = return_type_raw if return_type_raw else None
    rows = _get_purchase_return_detail_rows(date_from=date_from or None, date_to=date_to or None, goods_return_no=goods_return_no, supplier_code=supplier_code, receipt_no=receipt_no, return_type=return_type_f, item_code=item_code)
    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output)
    writer.writerow(['Goods Return No', 'Return Date', 'Return Type', 'Return Type Label', 'Supplier Code', 'Supplier Name', 'Receipt No', 'Return Amount', 'Header Remarks', 'Sl No', 'Item Code', 'Barcode', 'Item Name', 'UOM', 'Quantity', 'Rate', 'Line Discount', 'Line Amount', 'Store Code', 'Store Name', 'Line Remarks', 'Average Cost', 'Conversion Factor', 'Lot Id'])
    for r in rows:
        dtv = r.get('returndate')
        dt = dtv.strftime('%Y-%m-%d %H:%M:%S') if hasattr(dtv, 'strftime') else str(dtv or '')
        rtc = r.get('returntype') or ''
        writer.writerow([r.get('goodsreturnno') or '', dt, rtc, _purchase_return_type_label(rtc), r.get('suppliercode') or '', r.get('suppliername') or '', r.get('receiptno') or '', f"{float(r.get('returnamount') or 0):.4f}", r.get('hdr_remarks') or '', r.get('slno') or '', r.get('itemcode') or '', r.get('barcode') or '', r.get('itemname') or '', r.get('uom') or '', f"{float(r.get('quantity') or 0):.4f}", f"{float(r.get('rate') or 0):.4f}", f"{float(r.get('linediscount') or 0):.4f}", f"{float(r.get('lineamount') or 0):.4f}", r.get('storecode') or '', r.get('storename') or '', r.get('line_remarks') or '', f"{float(r.get('averagecost') or 0):.4f}", f"{float(r.get('conversionfactor') or 0):.6f}", r.get('lot_id') or ''])
    filename = f"purchase_return_details_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename={filename}'})

@bp.route('/reports/sales-details', methods=['GET'])
def sales_details():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    date_from = (request.args.get('date_from') or '').strip()
    date_to = (request.args.get('date_to') or '').strip()
    date_from, date_to = _default_report_date_range(date_from, date_to)
    bill_no_raw = (request.args.get('bill_no') or '').strip()
    order_no_raw = (request.args.get('order_no') or '').strip()
    customer_raw = (request.args.get('customer_code') or '').strip()
    bill_type = (request.args.get('bill_type') or '').strip()
    txn_kind = (request.args.get('txn_kind') or 'all').strip().lower()
    if txn_kind not in ('all', 'sale', 'salesreturn'):
        txn_kind = 'all'
    item_code_raw = (request.args.get('item_code') or '').strip()
    bill_no: Optional[int] = int(bill_no_raw) if bill_no_raw.isdigit() else None
    customer_code: Optional[int] = None
    if customer_raw.isdigit():
        customer_code = int(customer_raw)
    item_code: Optional[int] = int(item_code_raw) if item_code_raw.isdigit() else None
    rows = _get_sales_detail_rows(
        date_from=date_from or None,
        date_to=date_to or None,
        bill_no=bill_no,
        customer_code=customer_code,
        bill_type=bill_type,
        item_code=item_code,
        txn_kind=txn_kind,
        order_no=order_no_raw,
    )
    selected_customer_label = ''
    if customer_raw:
        for opt in _get_sales_detail_customer_options(search=customer_raw, limit=100):
            if str(opt.get('customercode') or '').strip() == customer_raw:
                name = str(opt.get('customername') or '').strip()
                selected_customer_label = f'{customer_raw} — {name}' if name else customer_raw
                break
        if not selected_customer_label:
            selected_customer_label = customer_raw
    selected_item_label = ''
    if item_code_raw:
        for opt in _get_sales_detail_item_options(search=item_code_raw, limit=100):
            if str(opt.get('itemcode') or '').strip() == item_code_raw:
                name = str(opt.get('itemname') or '').strip()
                selected_item_label = f'{item_code_raw} — {name}' if name else item_code_raw
                break
    return render_template(
        'reports/sales_details_report.html',
        rows=rows,
        filters={
            'date_from': date_from,
            'date_to': date_to,
            'bill_no': bill_no_raw,
            'order_no': order_no_raw,
            'customer_code': customer_raw,
            'customer_label': selected_customer_label,
            'bill_type': bill_type,
            'txn_kind': txn_kind,
            'item_code': item_code_raw,
            'item_label': selected_item_label,
        },
    )

@bp.route('/reports/sales-details/api/customers', methods=['GET'])
def sales_details_customers_api():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    search = (request.args.get('search') or '').strip()
    customers = _get_sales_detail_customer_options(search=search, limit=300)
    return jsonify({'success': True, 'customers': customers})

@bp.route('/reports/sales-details/api/items', methods=['GET'])
def sales_details_items_api():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    search = (request.args.get('search') or '').strip()
    items = _get_sales_detail_item_options(search=search, limit=300)
    return jsonify({'success': True, 'items': items})

@bp.route('/reports/sales-details/export-excel', methods=['GET'])
def sales_details_export_excel():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    date_from = (request.args.get('date_from') or '').strip()
    date_to = (request.args.get('date_to') or '').strip()
    date_from, date_to = _default_report_date_range(date_from, date_to)
    bill_no_raw = (request.args.get('bill_no') or '').strip()
    order_no_raw = (request.args.get('order_no') or '').strip()
    customer_raw = (request.args.get('customer_code') or '').strip()
    bill_type = (request.args.get('bill_type') or '').strip()
    txn_kind = (request.args.get('txn_kind') or 'all').strip().lower()
    if txn_kind not in ('all', 'sale', 'salesreturn'):
        txn_kind = 'all'
    item_code_raw = (request.args.get('item_code') or '').strip()
    bill_no: Optional[int] = int(bill_no_raw) if bill_no_raw.isdigit() else None
    customer_code: Optional[int] = int(customer_raw) if customer_raw.isdigit() else None
    item_code: Optional[int] = int(item_code_raw) if item_code_raw.isdigit() else None
    rows = _get_sales_detail_rows(
        date_from=date_from or None,
        date_to=date_to or None,
        bill_no=bill_no,
        customer_code=customer_code,
        bill_type=bill_type,
        item_code=item_code,
        txn_kind=txn_kind,
        order_no=order_no_raw,
    )
    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output)
    writer.writerow(['Bill No', 'Bill Date', 'Bill Time', 'Bill Type', 'Customer Code', 'Customer Name', 'Order No', 'Net Bill Amount', 'Hdr Discount', 'Header Remarks', 'Salesman Code', 'Counter Code', 'Bill Status', 'Sl No', 'Item Code', 'Store', 'Item Name', 'UOM', 'Quantity', 'Rate', 'Line Discount', 'Line Amount'])
    for r in rows:
        dtv = r.get('billdate')
        dt = dtv.strftime('%Y-%m-%d %H:%M:%S') if hasattr(dtv, 'strftime') else str(dtv or '')
        ttv = r.get('billtime')
        tt = ttv.strftime('%H:%M:%S') if hasattr(ttv, 'strftime') else str(ttv or '')
        writer.writerow([r.get('billno') or '', dt, tt, r.get('billtype') or '', r.get('customercode') if r.get('customercode') is not None else '', r.get('customername') or '', r.get('orderno') or '', f"{float(r.get('netbillamount') or 0):.4f}", f"{float(r.get('hdr_discount') or 0):.4f}", r.get('hdr_remarks') or '', r.get('salesmancode') if r.get('salesmancode') is not None else '', r.get('countercode') if r.get('countercode') is not None else '', r.get('billstatus') or '', r.get('slno') or '', r.get('itemcode') or '', r.get('storecode') or '', r.get('itemname') or '', r.get('uom') or '', f"{float(r.get('quantity') or 0):.4f}", f"{float(r.get('rate') or 0):.4f}", f"{float(r.get('linediscount') or 0):.4f}", f"{float(r.get('lineamount') or 0):.4f}"])
    filename = f"sales_details_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename={filename}'})

def _margin_sales_hdr_dtl_tables() -> Tuple[str, str]:
    """Margin report uses BILLHDR / BILLDTL only (not history tables)."""
    return _sales_detail_hdr_dtl_tables()

_MARGIN_REPORT_MODES = frozenset({'item', 'bill', 'detail', 'month', 'year'})

def _normalize_margin_report_mode(raw: Optional[str]) -> str:
    mode = (raw or 'item').strip().lower()
    return mode if mode in _MARGIN_REPORT_MODES else 'item'


def _margin_unit_cost_sql(
    *,
    d_avg_col: Optional[str],
    d_cost_col: Optional[str],
    im_avg_expr: str,
    im_cost_expr: str,
) -> str:
    """
    Unit cost for margin COGS: AVERAGECOST (line, then ITEMMASTER), else COSTPRICE (line, then item).
    NULLIF(..., 0) so zero average falls through to cost — same rule as POS / sales posting.
    """
    parts: List[str] = []
    if d_avg_col:
        parts.append(f'NULLIF(NVL(d.{d_avg_col}, 0), 0)')
    parts.append(f'NULLIF(NVL({im_avg_expr}, 0), 0)')
    if d_cost_col:
        parts.append(f'NULLIF(NVL(d.{d_cost_col}, 0), 0)')
    parts.append(f'NULLIF(NVL({im_cost_expr}, 0), 0)')
    if not parts:
        return '0'
    expr = parts[-1]
    for prior in reversed(parts[:-1]):
        expr = f'NVL({prior}, {expr})'
    return expr


def _compute_margin_grid_totals(rows: List[Dict[str, Any]], report_mode: str) -> Dict[str, Any]:
    mode = _normalize_margin_report_mode(report_mode)
    sales = cogs = margin = 0.0
    qty = 0.0
    for r in rows or []:
        sales += _to_float(r.get('sales') if mode != 'detail' else r.get('line_sales'))
        cogs += _to_float(r.get('cogs'))
        margin += _to_float(r.get('margin') if mode != 'detail' else r.get('gross_margin'))
        if mode == 'detail':
            qty += _to_float(r.get('quantity'))
        elif mode in ('item', 'month', 'year'):
            qty += _to_float(r.get('total_qty'))
    margin_pct = round(100.0 * margin / sales, 2) if abs(sales) > 1e-6 else None
    return {
        'row_count': len(rows or []),
        'total_qty': round(qty, 3),
        'sales': round(sales, 2),
        'cogs': round(cogs, 2),
        'margin': round(margin, 2),
        'margin_pct': margin_pct,
    }

def _get_margin_report_rows(
    *,
    date_from: str,
    date_to: str,
    search: str = '',
    itemcode: str = '',
    category_code: str = '',
    brand_code: str = '',
    customer_code: str = '',
    salesman_code: str = '',
    bill_type: str = '',
    bill_no: str = '',
    report_mode: str = 'item',
    row_cap: int = 8000,
    location_code: Optional[int] = None,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    hdr, dtl = _margin_sales_hdr_dtl_tables()
    if not hdr or not dtl:
        return ([], 'Sales tables BILLHDR / BILLDTL not found.')
    mode = _normalize_margin_report_mode(report_mode)
    cap = min(max(int(row_cap or 8000), 1), 20000)
    h_no = _detect_column(hdr, ['BILLNO', 'billno'])
    h_date = _detect_column(hdr, ['BILLDATE', 'billdate'])
    h_type = _detect_column(hdr, ['BILLTYPE', 'billtype'])
    h_cust = _detect_column(hdr, ['CUSTOMERCODE', 'customercode'])
    h_custname = _detect_column(hdr, ['CUSTOMERNAME', 'customername'])
    h_salesman = _detect_column(hdr, ['SALESMANCODE', 'SALESMAN_CODE', 'salesmancode'])
    h_loc = _detect_column(hdr, ['LOCATIONCODE', 'locationcode'])
    h_reset = _detect_column(hdr, ['RESETNO', 'resetno'])
    h_del = _detect_column(hdr, ['DELFLAG', 'delflag'])
    h_status = _detect_column(hdr, ['BILLSTATUS', 'billstatus'])
    d_bill = _detect_column(dtl, ['BILLNO', 'billno'])
    d_sl = _detect_column(dtl, ['SLNO', 'slno'])
    d_item = _detect_column(dtl, ['ITEMCODE', 'itemcode'])
    d_uom = _detect_column(dtl, ['UNITOFMEASUREMENT', 'unitofmeasurement', 'UOM'])
    d_qty = _detect_column(dtl, ['QUANTITY', 'quantity'])
    d_base = _detect_column(dtl, ['BASEQTY', 'baseqty'])
    d_rate = _detect_column(dtl, ['RATE', 'rate'])
    d_disc = _detect_column(dtl, ['ITDISC', 'itdisc', 'DISCOUNT'])
    d_cost = _detect_column(dtl, ['COST', 'cost', 'COSTPRICE'])
    d_avg = _detect_column(dtl, ['AVERAGECOST', 'averagecost'])
    d_det = _detect_column(dtl, ['ITEMDETAILS1', 'itemdetails1', 'ITEMNAME'])
    d_loc = _detect_column(dtl, ['LOCATIONCODE', 'locationcode'])
    d_reset = _detect_column(dtl, ['RESETNO', 'resetno'])
    if not h_no or not h_date or not d_bill or not d_item:
        return ([], 'Required bill header/detail columns not found.')
    on_parts = [f'h.{h_no} = d.{d_bill}']
    if h_loc and d_loc:
        on_parts.append(f'h.{h_loc} = d.{d_loc}')
    if h_reset and d_reset:
        on_parts.append(f'h.{h_reset} = d.{d_reset}')
    loc_code = int(location_code) if location_code is not None else _resolve_location_code()
    params: Dict[str, Any] = {'mr_loc': loc_code, 'mr_cap': cap}
    where_parts: List[str] = []
    if h_loc:
        where_parts.append(f'h.{h_loc} = :mr_loc')
    if h_reset:
        where_parts.append(f'h.{h_reset} = :mr_rn')
        params['mr_rn'] = _SALES_DETAILS_RESET_NO
    if h_del:
        where_parts.append(f"NVL(h.{h_del}, 'N') = 'N'")
    if h_status:
        where_parts.append(f"(h.{h_status} IS NULL OR UPPER(TRIM(h.{h_status})) <> 'V')")
    if date_from:
        where_parts.append(f"TRUNC(h.{h_date}) >= TO_DATE(:mr_df, 'YYYY-MM-DD')")
        params['mr_df'] = date_from
    if date_to:
        where_parts.append(f"TRUNC(h.{h_date}) <= TO_DATE(:mr_dt, 'YYYY-MM-DD')")
        params['mr_dt'] = date_to
    bt = (bill_type or '').strip().upper()[:1]
    if bt and h_type:
        where_parts.append(f"UPPER(TRIM(NVL(h.{h_type}, ''))) = :mr_bt")
        params['mr_bt'] = bt
    cc = _normalize_report_customer_code(customer_code)
    if cc.isdigit() and int(cc) > 0 and h_cust:
        where_parts.append(f'h.{h_cust} = :mr_cust')
        params['mr_cust'] = int(cc)
    bno = (bill_no or '').strip()
    if bno.isdigit():
        where_parts.append(f'h.{h_no} = :mr_bno')
        params['mr_bno'] = int(bno)
    icode = (itemcode or '').strip()
    if icode:
        where_parts.append(f'TO_CHAR(d.{d_item}) = :mr_itemcode')
        params['mr_itemcode'] = icode
    im = _detect_table(['ITEMMASTER', 'itemmaster'])
    im_item = _detect_column(im, ['ITEMCODE', 'itemcode']) if im else None
    im_name = _detect_column(im, ['ITEMNAME', 'itemname']) if im else None
    im_loc = _detect_column(im, ['LOCATIONCODE', 'locationcode']) if im else None
    im_uom = _detect_column(im, ['BASEUOM', 'baseuom', 'UNITOFMEASUREMENT']) if im else None
    im_cost = _detect_column(im, ['COSTPRICE', 'costprice']) if im else None
    im_avg = _detect_column(im, ['AVERAGECOST', 'averagecost']) if im else None
    im_cat = _detect_column(im, ['CATEGORYCODE', 'categorycode']) if im else None
    im_brand = _detect_column(im, ['BRANDCODE', 'brandcode']) if im else None
    join_im = ''
    item_name_expr = f"NVL(d.{d_det}, '')" if d_det else "CAST(NULL AS VARCHAR2(400))"
    uom_expr = f"NVL(d.{d_uom}, '')" if d_uom else "CAST(NULL AS VARCHAR2(40))"
    im_cost_expr = '0'
    im_avg_expr = '0'
    cat_name_expr = "CAST(NULL AS VARCHAR2(240))"
    join_cat = ''
    if im and im_item and im_name:
        im_on = f'd.{d_item} = im.{im_item}'
        if im_loc and h_loc:
            im_on += f' AND im.{im_loc} = h.{h_loc}'
        join_im = f'LEFT JOIN {im} im ON {im_on}'
        if d_det:
            item_name_expr = f"NVL(NULLIF(TRIM(d.{d_det}), ''), im.{im_name})"
        else:
            item_name_expr = f'im.{im_name}'
        if im_uom and d_uom:
            uom_expr = f'NVL(d.{d_uom}, im.{im_uom})'
        elif im_uom:
            uom_expr = f'im.{im_uom}'
        if im_cost:
            im_cost_expr = f'NVL(im.{im_cost}, 0)'
        if im_avg:
            im_avg_expr = f'NVL(im.{im_avg}, 0)'
    cat_tbl = _detect_table(['CATEGORY', 'category'])
    cat_code = _detect_column(cat_tbl, ['CODE', 'CATEGORYCODE', 'categorycode']) if cat_tbl else None
    cat_name = _detect_column(cat_tbl, ['NAME', 'CATEGORYNAME', 'categoryname']) if cat_tbl else None
    cat_flag = _detect_column(cat_tbl, ['FLAG', 'flag']) if cat_tbl else None
    if im and im_cat and cat_tbl and cat_code and cat_name:
        join_cat = f'LEFT JOIN {cat_tbl} cat ON cat.{cat_code} = im.{im_cat}'
        if cat_flag:
            join_cat += f" AND cat.{cat_flag} = 'C'"
        cat_name_expr = f'NVL(cat.{cat_name}, \'\')'
    cat_filter = (category_code or '').strip()
    if cat_filter and im and im_cat:
        where_parts.append(f'TO_CHAR(im.{im_cat}) = :mr_category')
        params['mr_category'] = cat_filter
    brand_filter = (brand_code or '').strip()
    if brand_filter and im and im_brand:
        where_parts.append(f'TO_CHAR(im.{im_brand}) = :mr_brand')
        params['mr_brand'] = brand_filter
    sm_filter = (salesman_code or '').strip()
    if sm_filter.isdigit() and h_salesman:
        where_parts.append(f'TO_CHAR(h.{h_salesman}) = :mr_sm')
        params['mr_sm'] = sm_filter
    qtxt = (search or '').strip()
    if qtxt:
        like = f'%{qtxt.upper()}%'
        params['mr_q'] = like
        parts = [f'TO_CHAR(d.{d_item}) LIKE :mr_q']
        if d_det:
            parts.append(f'UPPER(d.{d_det}) LIKE :mr_q')
        if im and im_name:
            parts.append(f'UPPER(im.{im_name}) LIKE :mr_q')
        where_parts.append('(' + ' OR '.join(parts) + ')')
    qty_expr = f'NVL(d.{d_qty}, 0)' if d_qty else '0'
    base_expr = f'NVL(d.{d_base}, {qty_expr})' if d_base else qty_expr
    rate_expr = f'NVL(d.{d_rate}, 0)' if d_rate else '0'
    disc_expr = f'NVL(d.{d_disc}, 0)' if d_disc else '0'
    unit_cost_expr = _margin_unit_cost_sql(
        d_avg_col=d_avg,
        d_cost_col=d_cost,
        im_avg_expr=im_avg_expr,
        im_cost_expr=im_cost_expr,
    )
    line_sales_expr = f'({qty_expr} * {rate_expr} - {disc_expr})'
    cogs_expr = f'({base_expr} * ({unit_cost_expr}))'
    margin_expr = f'({line_sales_expr} - {cogs_expr})'
    cust_disp = f"NVL(TRIM(h.{h_custname}), '')" if h_custname else "''"
    sm_expr = f'h.{h_salesman}' if h_salesman else 'CAST(NULL AS NUMBER)'
    brand_expr = f'TO_CHAR(im.{im_brand})' if im and im_brand else "''"
    sl_expr = f'd.{d_sl}' if d_sl else '0'
    where_sql = ' AND '.join(where_parts) if where_parts else '1=1'
    lines_sql = f"""
        SELECT
            h.{h_no} AS billno,
            h.{h_date} AS billdate,
            {(f'h.{h_type}' if h_type else "''")} AS billtype,
            {(f'h.{h_cust}' if h_cust else 'CAST(NULL AS NUMBER)')} AS customercode,
            {cust_disp} AS customername,
            {sm_expr} AS salesmancode,
            {brand_expr} AS brandcode,
            d.{d_item} AS itemcode,
            {item_name_expr} AS itemname,
            {uom_expr} AS uom,
            {cat_name_expr} AS categoryname,
            {qty_expr} AS quantity,
            {rate_expr} AS rate,
            {disc_expr} AS linediscount,
            {unit_cost_expr} AS unit_cost,
            {line_sales_expr} AS line_sales,
            {cogs_expr} AS cogs,
            {margin_expr} AS gross_margin,
            {sl_expr} AS slno
        FROM {hdr} h
        INNER JOIN {dtl} d ON {' AND '.join(on_parts)}
        {join_im}
        {join_cat}
        WHERE {where_sql}
    """
    try:
        if mode == 'detail':
            q = f"""
                SELECT * FROM (
                    SELECT
                        billno,
                        TO_CHAR(TRUNC(billdate), 'YYYY-MM-DD') AS bill_date,
                        billtype,
                        customercode,
                        customername,
                        salesmancode,
                        brandcode,
                        itemcode,
                        itemname,
                        uom,
                        categoryname,
                        slno,
                        ROUND(quantity, 3) AS quantity,
                        ROUND(rate, 4) AS rate,
                        ROUND(linediscount, 2) AS linediscount,
                        ROUND(unit_cost, 4) AS unit_cost,
                        ROUND(line_sales, 2) AS line_sales,
                        ROUND(cogs, 2) AS cogs,
                        ROUND(gross_margin, 2) AS gross_margin,
                        CASE WHEN ABS(line_sales) > 1e-6 THEN ROUND(100 * gross_margin / line_sales, 2) END AS margin_pct
                    FROM ({lines_sql})
                    ORDER BY billdate DESC, billno DESC, slno ASC
                )
                WHERE ROWNUM <= :mr_cap
            """
            return (_safe_rows(q, params) or [], None)
        if mode == 'bill':
            q = f"""
                SELECT * FROM (
                    SELECT
                        billno,
                        TO_CHAR(TRUNC(MAX(billdate)), 'YYYY-MM-DD') AS bill_date,
                        MAX(billtype) AS billtype,
                        MAX(customercode) AS customercode,
                        MAX(customername) AS customername,
                        COUNT(*) AS line_count,
                        ROUND(SUM(line_sales), 2) AS sales,
                        ROUND(SUM(cogs), 2) AS cogs,
                        ROUND(SUM(gross_margin), 2) AS margin,
                        CASE WHEN ABS(SUM(line_sales)) > 1e-6 THEN ROUND(100 * SUM(gross_margin) / SUM(line_sales), 2) END AS margin_pct
                    FROM ({lines_sql})
                    GROUP BY billno
                    ORDER BY MAX(billdate) DESC, billno DESC
                )
                WHERE ROWNUM <= :mr_cap
            """
            return (_safe_rows(q, params) or [], None)
        margin_agg = """
            ROUND(SUM(line_sales), 2) AS sales,
            ROUND(SUM(cogs), 2) AS cogs,
            ROUND(SUM(gross_margin), 2) AS margin,
            CASE WHEN ABS(SUM(line_sales)) > 1e-6 THEN ROUND(100 * SUM(gross_margin) / SUM(line_sales), 2) END AS margin_pct
        """
        if mode == 'month':
            q = f"""
                SELECT * FROM (
                    SELECT
                        TO_CHAR(TRUNC(billdate), 'YYYY-MM') AS period,
                        TO_CHAR(MIN(TRUNC(billdate)), 'YYYY-MM-DD') AS period_from,
                        TO_CHAR(MAX(TRUNC(billdate)), 'YYYY-MM-DD') AS period_to,
                        COUNT(DISTINCT billno) AS bill_count,
                        COUNT(*) AS line_count,
                        ROUND(SUM(quantity), 3) AS total_qty,
                        {margin_agg}
                    FROM ({lines_sql})
                    GROUP BY TO_CHAR(TRUNC(billdate), 'YYYY-MM')
                    ORDER BY TO_CHAR(TRUNC(billdate), 'YYYY-MM') DESC
                )
                WHERE ROWNUM <= :mr_cap
            """
            return (_safe_rows(q, params) or [], None)
        if mode == 'year':
            q = f"""
                SELECT * FROM (
                    SELECT
                        TO_CHAR(TRUNC(billdate), 'YYYY') AS period,
                        TO_CHAR(MIN(TRUNC(billdate)), 'YYYY-MM-DD') AS period_from,
                        TO_CHAR(MAX(TRUNC(billdate)), 'YYYY-MM-DD') AS period_to,
                        COUNT(DISTINCT billno) AS bill_count,
                        COUNT(*) AS line_count,
                        ROUND(SUM(quantity), 3) AS total_qty,
                        {margin_agg}
                    FROM ({lines_sql})
                    GROUP BY TO_CHAR(TRUNC(billdate), 'YYYY')
                    ORDER BY TO_CHAR(TRUNC(billdate), 'YYYY') DESC
                )
                WHERE ROWNUM <= :mr_cap
            """
            return (_safe_rows(q, params) or [], None)
        q = f"""
            SELECT * FROM (
                SELECT
                    itemcode,
                    MAX(itemname) AS itemname,
                    MAX(uom) AS uom,
                    MAX(categoryname) AS categoryname,
                    ROUND(SUM(quantity), 3) AS total_qty,
                    COUNT(DISTINCT billno) AS bill_count,
                    {margin_agg}
                FROM ({lines_sql})
                GROUP BY itemcode
                ORDER BY SUM(gross_margin) DESC, itemcode
            )
            WHERE ROWNUM <= :mr_cap
        """
        return (_safe_rows(q, params) or [], None)
    except Exception as e:
        logger.exception('Margin report failed: %s', e)
        return ([], str(e))

@bp.route('/reports/api/customer-search', methods=['GET'])
def report_customer_search():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not logged in'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    q = (request.args.get('q') or request.args.get('search') or '').strip()
    try:
        lim = int(request.args.get('limit', 8))
    except (TypeError, ValueError):
        lim = 8
    try:
        rows = _search_report_customers(q, limit=lim)
        return jsonify({'success': True, 'rows': rows})
    except Exception as exc:
        logger.exception('Report customer search failed: %s', exc)
        return jsonify({'success': False, 'error': str(exc)}, 500)

@bp.route('/reports/api/category-search', methods=['GET'])
def report_category_search():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not logged in'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    q = (request.args.get('q') or request.args.get('search') or '').strip()
    try:
        lim = int(request.args.get('limit', 8))
    except (TypeError, ValueError):
        lim = 8
    try:
        rows = _search_report_categories(q, limit=lim)
        return jsonify({'success': True, 'rows': rows})
    except Exception as exc:
        logger.exception('Report category search failed: %s', exc)
        return jsonify({'success': False, 'error': str(exc)}, 500)

@bp.route('/reports/margin-report', methods=['GET'])
def margin_report():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    date_from = (request.args.get('date_from') or '').strip()
    date_to = (request.args.get('date_to') or '').strip()
    date_from, date_to = _default_report_date_range(date_from, date_to)
    search = (request.args.get('search') or '').strip()
    itemcode = (request.args.get('itemcode') or '').strip()
    if itemcode:
        search = ''
    category_code = (request.args.get('category_code') or '').strip()
    customer_code = _normalize_report_customer_code(request.args.get('customer_code'))
    bill_type = (request.args.get('bill_type') or '').strip()
    bill_no = (request.args.get('bill_no') or '').strip()
    report_mode = _normalize_margin_report_mode(request.args.get('report_mode'))
    cap_raw = (request.args.get('max_rows') or '').strip()
    try:
        row_cap = int(cap_raw) if cap_raw.isdigit() else 8000
    except (TypeError, ValueError):
        row_cap = 8000
    rows, err = _get_margin_report_rows(
        date_from=date_from,
        date_to=date_to,
        search=search,
        itemcode=itemcode,
        category_code=category_code,
        customer_code=customer_code,
        bill_type=bill_type,
        bill_no=bill_no,
        report_mode=report_mode,
        row_cap=row_cap,
    )
    grid_totals = _compute_margin_grid_totals(rows, report_mode)
    return render_template(
        'reports/margin_report.html',
        rows=rows,
        grid_totals=grid_totals,
        error_message=err or '',
        filters={
            'date_from': date_from,
            'date_to': date_to,
            'search': search,
            'itemcode': itemcode,
            'item_label': _resolve_report_item_label(itemcode),
            'category_code': category_code,
            'category_label': _resolve_report_category_label(category_code),
            'customer_code': customer_code,
            'customer_label': _resolve_report_customer_label(customer_code),
            'bill_type': bill_type,
            'bill_no': bill_no,
            'report_mode': report_mode,
            'max_rows': str(row_cap),
        },
    )

@bp.route('/reports/margin-report/export-excel', methods=['GET'])
def margin_report_export_excel():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    date_from = (request.args.get('date_from') or '').strip()
    date_to = (request.args.get('date_to') or '').strip()
    date_from, date_to = _default_report_date_range(date_from, date_to)
    search = (request.args.get('search') or '').strip()
    itemcode = (request.args.get('itemcode') or '').strip()
    if itemcode:
        search = ''
    category_code = (request.args.get('category_code') or '').strip()
    customer_code = _normalize_report_customer_code(request.args.get('customer_code'))
    bill_type = (request.args.get('bill_type') or '').strip()
    bill_no = (request.args.get('bill_no') or '').strip()
    report_mode = _normalize_margin_report_mode(request.args.get('report_mode'))
    cap_raw = (request.args.get('max_rows') or '').strip()
    try:
        row_cap = int(cap_raw) if cap_raw.isdigit() else 8000
    except (TypeError, ValueError):
        row_cap = 8000
    rows, err = _get_margin_report_rows(
        date_from=date_from,
        date_to=date_to,
        search=search,
        itemcode=itemcode,
        category_code=category_code,
        customer_code=customer_code,
        bill_type=bill_type,
        bill_no=bill_no,
        report_mode=report_mode,
        row_cap=row_cap,
    )
    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output)
    if report_mode == 'detail':
        writer.writerow(['SLNO', 'BILLNO', 'BILL_DATE', 'BILL_TYPE', 'CUSTOMER', 'CUSTOMER_NAME', 'ITEMCODE', 'ITEMNAME', 'UOM', 'CATEGORY', 'LINE_SLNO', 'QTY', 'RATE', 'DISCOUNT', 'UNIT_COST', 'SALES', 'COGS', 'MARGIN', 'MARGIN_PCT'])
        for idx, r in enumerate(rows, start=1):
            writer.writerow([
                idx,
                r.get('billno') or '',
                r.get('bill_date') or '',
                r.get('billtype') or '',
                r.get('customercode') if r.get('customercode') is not None else '',
                r.get('customername') or '',
                r.get('itemcode') if r.get('itemcode') is not None else '',
                r.get('itemname') or '',
                r.get('uom') or '',
                r.get('categoryname') or '',
                r.get('slno') or '',
                f"{_to_float(r.get('quantity')):.3f}",
                f"{_to_float(r.get('rate')):.4f}",
                f"{_to_float(r.get('linediscount')):.2f}",
                f"{_to_float(r.get('unit_cost')):.4f}",
                f"{_to_float(r.get('line_sales')):.2f}",
                f"{_to_float(r.get('cogs')):.2f}",
                f"{_to_float(r.get('gross_margin')):.2f}",
                '' if r.get('margin_pct') is None else f"{_to_float(r.get('margin_pct')):.2f}",
            ])
    elif report_mode == 'bill':
        writer.writerow(['SLNO', 'BILLNO', 'BILL_DATE', 'BILL_TYPE', 'CUSTOMER', 'CUSTOMER_NAME', 'LINES', 'SALES', 'COGS', 'MARGIN', 'MARGIN_PCT'])
        for idx, r in enumerate(rows, start=1):
            writer.writerow([
                idx,
                r.get('billno') or '',
                r.get('bill_date') or '',
                r.get('billtype') or '',
                r.get('customercode') if r.get('customercode') is not None else '',
                r.get('customername') or '',
                r.get('line_count') or '',
                f"{_to_float(r.get('sales')):.2f}",
                f"{_to_float(r.get('cogs')):.2f}",
                f"{_to_float(r.get('margin')):.2f}",
                '' if r.get('margin_pct') is None else f"{_to_float(r.get('margin_pct')):.2f}",
            ])
    elif report_mode in ('month', 'year'):
        period_hdr = 'MONTH' if report_mode == 'month' else 'YEAR'
        writer.writerow(['SLNO', period_hdr, 'FROM_DATE', 'TO_DATE', 'BILLS', 'LINES', 'TOTAL_QTY', 'SALES', 'COGS', 'MARGIN', 'MARGIN_PCT'])
        for idx, r in enumerate(rows, start=1):
            writer.writerow([
                idx,
                r.get('period') or '',
                r.get('period_from') or '',
                r.get('period_to') or '',
                r.get('bill_count') or '',
                r.get('line_count') or '',
                f"{_to_float(r.get('total_qty')):.3f}",
                f"{_to_float(r.get('sales')):.2f}",
                f"{_to_float(r.get('cogs')):.2f}",
                f"{_to_float(r.get('margin')):.2f}",
                '' if r.get('margin_pct') is None else f"{_to_float(r.get('margin_pct')):.2f}",
            ])
    else:
        writer.writerow(['SLNO', 'ITEMCODE', 'ITEMNAME', 'UOM', 'CATEGORY', 'TOTAL_QTY', 'BILL_COUNT', 'SALES', 'COGS', 'MARGIN', 'MARGIN_PCT'])
        for idx, r in enumerate(rows, start=1):
            writer.writerow([
                idx,
                r.get('itemcode') if r.get('itemcode') is not None else '',
                r.get('itemname') or '',
                r.get('uom') or '',
                r.get('categoryname') or '',
                f"{_to_float(r.get('total_qty')):.3f}",
                r.get('bill_count') or '',
                f"{_to_float(r.get('sales')):.2f}",
                f"{_to_float(r.get('cogs')):.2f}",
                f"{_to_float(r.get('margin')):.2f}",
                '' if r.get('margin_pct') is None else f"{_to_float(r.get('margin_pct')):.2f}",
            ])
    if rows:
        gt = _compute_margin_grid_totals(rows, report_mode)
        if report_mode == 'detail':
            writer.writerow(['TOTAL', '', '', '', '', '', '', '', '', '', '', f"{_to_float(gt.get('total_qty')):.3f}", '', '', '', f"{_to_float(gt.get('sales')):.2f}", f"{_to_float(gt.get('cogs')):.2f}", f"{_to_float(gt.get('margin')):.2f}", '' if gt.get('margin_pct') is None else f"{_to_float(gt.get('margin_pct')):.2f}"])
        elif report_mode == 'bill':
            writer.writerow(['TOTAL', '', '', '', '', '', '', f"{_to_float(gt.get('sales')):.2f}", f"{_to_float(gt.get('cogs')):.2f}", f"{_to_float(gt.get('margin')):.2f}", '' if gt.get('margin_pct') is None else f"{_to_float(gt.get('margin_pct')):.2f}"])
        elif report_mode in ('month', 'year'):
            writer.writerow(['TOTAL', '', '', '', '', '', f"{_to_float(gt.get('total_qty')):.3f}", f"{_to_float(gt.get('sales')):.2f}", f"{_to_float(gt.get('cogs')):.2f}", f"{_to_float(gt.get('margin')):.2f}", '' if gt.get('margin_pct') is None else f"{_to_float(gt.get('margin_pct')):.2f}"])
        else:
            writer.writerow(['TOTAL', '', '', '', '', f"{_to_float(gt.get('total_qty')):.3f}", '', f"{_to_float(gt.get('sales')):.2f}", f"{_to_float(gt.get('cogs')):.2f}", f"{_to_float(gt.get('margin')):.2f}", '' if gt.get('margin_pct') is None else f"{_to_float(gt.get('margin_pct')):.2f}"])
    if err:
        writer.writerow([])
        writer.writerow(['ERROR', err])
    filename = f"margin_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename={filename}'})

def _fmt_last_tx_date(val: Any) -> str:
    if val is None:
        return ''
    if hasattr(val, 'strftime'):
        try:
            return val.strftime('%Y-%m-%d')
        except Exception:
            pass
    s = str(val).strip()
    return s[:10] if len(s) >= 10 else s

@bp.route('/reports/last-transactions', methods=['GET'])
def last_transactions_report():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    search = (request.args.get('search') or '').strip()
    date_from = (request.args.get('date_from') or '').strip()
    date_to = (request.args.get('date_to') or '').strip()
    category_code = (request.args.get('category_code') or '').strip()
    transaction_scope = (request.args.get('transaction_scope') or 'all').strip().lower()
    if transaction_scope in ('sale', 'purchase', 'purchase_return', 'sale_return'):
        tx_types = [transaction_scope]
    else:
        tx_types = ['sale', 'purchase', 'purchase_return', 'sale_return']
        transaction_scope = 'all'
    cap_raw = (request.args.get('max_rows') or '').strip()
    try:
        row_cap = int(cap_raw) if cap_raw.isdigit() else 6000
    except (TypeError, ValueError):
        row_cap = 6000
    rows = _get_last_transactions_report_rows(search=search, row_cap=row_cap, date_from=date_from, date_to=date_to, transaction_types=tx_types, category_code=category_code)
    category_options = _get_last_transactions_category_options()
    return render_template('reports/last_transactions_report.html', rows=rows, category_options=category_options, filters={'search': search, 'max_rows': str(row_cap), 'date_from': date_from, 'date_to': date_to, 'category_code': category_code, 'transaction_scope': transaction_scope, 'transaction_types': tx_types})

@bp.route('/reports/last-transactions/export-excel', methods=['GET'])
def last_transactions_report_export_excel():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    search = (request.args.get('search') or '').strip()
    date_from = (request.args.get('date_from') or '').strip()
    date_to = (request.args.get('date_to') or '').strip()
    category_code = (request.args.get('category_code') or '').strip()
    transaction_scope = (request.args.get('transaction_scope') or 'all').strip().lower()
    if transaction_scope in ('sale', 'purchase', 'purchase_return', 'sale_return'):
        tx_types = [transaction_scope]
    else:
        tx_types = ['sale', 'purchase', 'purchase_return', 'sale_return']
        transaction_scope = 'all'
    cap_raw = (request.args.get('max_rows') or '').strip()
    try:
        row_cap = int(cap_raw) if cap_raw.isdigit() else 6000
    except (TypeError, ValueError):
        row_cap = 6000
    rows = _get_last_transactions_report_rows(search=search, row_cap=row_cap, date_from=date_from, date_to=date_to, transaction_types=tx_types, category_code=category_code)
    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output)
    writer.writerow(['SLNO', 'RAWABICODE', 'MANUFACTURERID', 'ITEMCODE', 'ITEMNAME', 'BASEUOM', 'COSTPRICE', 'CURRENTSTOCK', 'STOCKVALUE', 'CATEGORYCODE', 'CATEGORYNAME', 'LAST_SALE_DATE', 'LAST_PURCHASE_DATE', 'LAST_PURCHASE_RETURN_DATE', 'LAST_SALE_RETURN_DATE'])
    for idx, r in enumerate(rows, start=1):
        writer.writerow([idx, r.get('rawabicode') or '', r.get('manufacturerid') or '', r.get('itemcode') if r.get('itemcode') is not None else '', r.get('itemname') or '', r.get('baseuom') or '', f"{float(r.get('costprice') or 0):.4f}", f"{float(r.get('currentstock') or 0):.4f}", f"{float(r.get('stockvalue') or 0):.4f}", r.get('categorycode') if r.get('categorycode') is not None else '', r.get('categoryname') or '', _fmt_last_tx_date(r.get('last_sale_date')), _fmt_last_tx_date(r.get('last_purchase_date')), _fmt_last_tx_date(r.get('last_purchase_return_date')), _fmt_last_tx_date(r.get('last_sale_return_date'))])
    filename = f"last_transactions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename={filename}'})

def _compute_stock_datewise_grid_totals(rows: List[Dict[str, Any]], report_mode: str) -> Dict[str, Any]:
    """Sum numeric columns for grid footer (movement cols always; opening/closing only for summary_stock)."""
    mode = (report_mode or 'summary').strip().lower()
    totals: Dict[str, float] = {}
    qty_keys = ('qty_in', 'qty_out', 'net_qty', 'opening_stock', 'closing_stock')
    for r in rows or []:
        if mode == 'detail':
            for k in ('qty_in', 'qty_out', 'net_qty', 'amount', 'line_value'):
                totals[k] = totals.get(k, 0.0) + _to_float(r.get(k))
        elif mode == 'summary_stock':
            for k in ('opening_stock', 'opening_value', 'qty_in', 'value_in', 'qty_out', 'value_out', 'net_qty', 'net_value', 'closing_stock', 'closing_value'):
                totals[k] = totals.get(k, 0.0) + _to_float(r.get(k))
        else:
            for k in ('qty_in', 'value_in', 'qty_out', 'value_out', 'net_qty', 'net_value'):
                totals[k] = totals.get(k, 0.0) + _to_float(r.get(k))
    out: Dict[str, Any] = {'row_count': len(rows or []), 'show_opening_closing': mode == 'summary_stock'}
    for k, v in totals.items():
        out[k] = round(v, 3 if k in qty_keys else 2)
    return out

def _detect_itemjournal_table() -> Optional[str]:
    return _detect_table(['ITEMJOURNEL', 'itemjournel', 'ITEMJOURNAL', 'itemjournal'])

def _default_stock_datewise_range(date_from: str, date_to: str) -> Tuple[str, str]:
    df = (date_from or '').strip()
    dt = (date_to or '').strip()
    if not df and (not dt):
        dt = datetime.now().strftime('%Y-%m-%d')
        df = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    return (df, dt)

def _stock_datewise_transtype_clause(transtype: str, alias: str = 'j') -> Tuple[str, Dict[str, Any]]:
    tt = (transtype or '').strip().upper()
    if not tt:
        return ('', {})
    mapping = {
        'SALES': f"UPPER(TRIM(NVL({alias}.TRANSTYPE, ''))) = 'SALES'",
        'SALES RETURN': f"UPPER(TRIM(NVL({alias}.TRANSTYPE, ''))) = 'SALES RETURN'",
        'PURCHASE': f"UPPER(TRIM(NVL({alias}.TRANSTYPE, ''))) = 'PURCHASE'",
        'PURCHASE_RETURN': f"UPPER(TRIM(NVL({alias}.TRANSTYPE, ''))) = 'PURCHASE_RETURN'",
    }
    clause = mapping.get(tt)
    if clause:
        return (clause, {})
    return (f"UPPER(TRIM(NVL({alias}.TRANSTYPE, ''))) = :srd_tt", {'srd_tt': tt})

def _get_stock_report_datewise_rows(
    *,
    date_from: str,
    date_to: str,
    search: str = '',
    itemcode: str = '',
    category_code: str = '',
    transtype: str = '',
    report_mode: str = 'summary',
    row_cap: int = 8000,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Stock movement from ITEMJOURNEL / ITEMJOURNAL. summary = per item per day; detail = journal lines."""
    jtbl = _detect_itemjournal_table()
    if not jtbl:
        return ([], 'ITEMJOURNAL / ITEMJOURNEL table not found.')
    loc = _resolve_location_code()
    df, dt = _default_stock_datewise_range(date_from, date_to)
    if not df or not dt:
        return ([], 'Date from and date to are required.')
    mode = (report_mode or 'summary').strip().lower()
    if mode not in ('summary', 'summary_stock', 'detail'):
        mode = 'summary'
    cap = min(max(int(row_cap or 8000), 1), 20000)
    params: Dict[str, Any] = {'srd_loc': loc, 'srd_df': df, 'srd_dt': dt, 'srd_cap': cap}
    tt_sql, tt_params = _stock_datewise_transtype_clause(transtype)
    params.update(tt_params)
    im = _detect_table(['ITEMMASTER', 'itemmaster'])
    im_ic = _detect_column(im, ['ITEMCODE', 'itemcode']) if im else None
    im_loc = _detect_column(im, ['LOCATIONCODE', 'locationcode']) if im else None
    im_name = _detect_column(im, ['ITEMNAME', 'itemname']) if im else None
    im_cat = _detect_column(im, ['CATEGORYCODE', 'categorycode']) if im else None
    im_uom = _detect_column(im, ['BASEUOM', 'baseuom', 'UNITOFMEASUREMENT']) if im else None
    im_cost = _detect_column(im, ['COSTPRICE', 'COST_PRICE', 'costprice']) if im else None
    cost_im2_sel = f'NVL(im2.{im_cost}, 0)' if im and im_cost else '0'
    cost_im_sel = f'NVL(im.{im_cost}, 0)' if im and im_cost else '0'
    line_value_expr = 'NVL(j.AMOUNT, NVL(j.QTY, 0) * NVL(j.RATE, 0))'
    agg_value_in = f"SUM(CASE WHEN NVL(j.QTY, 0) > 0 THEN ABS({line_value_expr}) ELSE 0 END)"
    agg_value_out = f"SUM(CASE WHEN NVL(j.QTY, 0) < 0 THEN ABS({line_value_expr}) ELSE 0 END)"
    agg_value_net = f'SUM({line_value_expr})'
    jcols = {str(c).upper() for c in (_get_table_columns(jtbl) or [])}
    j_wh_code_col = itemjournal_warehouse_code_column(jtbl)
    j_wh_id_col = _detect_column(jtbl, ['WAREHOUSE_ID', 'warehouse_id'])
    j_itemname = 'ITEMNAME' if 'ITEMNAME' in jcols else None
    join_im = ''
    itemname_sel = "CAST(NULL AS VARCHAR2(400))"
    uom_sel = f'j.UOM'
    if im and im_ic and im_loc:
        join_im = f'LEFT JOIN {im} im ON im.{im_ic} = j.ITEMCODE AND im.{im_loc} = j.LOCATIONCODE'
        if im_name:
            if j_itemname:
                itemname_sel = f"NVL(im.{im_name}, NVL(j.{j_itemname}, ''))"
            else:
                itemname_sel = f"NVL(im.{im_name}, '')"
        if im_uom:
            uom_sel = f"NVL(j.UOM, im.{im_uom})"
    elif j_itemname:
        itemname_sel = f'NVL(j.{j_itemname}, \'\')'
    filter_parts = [
        'j.LOCATIONCODE = :srd_loc',
        "TRUNC(j.CREATEDDATE) >= TO_DATE(:srd_df, 'YYYY-MM-DD')",
        "TRUNC(j.CREATEDDATE) <= TO_DATE(:srd_dt, 'YYYY-MM-DD')",
    ]
    if tt_sql:
        filter_parts.append(tt_sql)
    qtxt = str(search or '').strip()
    if qtxt:
        like = f'%{qtxt.upper()}%'
        params['srd_q'] = like
        search_bits = ['TO_CHAR(j.ITEMCODE) LIKE :srd_q']
        if im and im_name:
            search_bits.append(f'UPPER(im.{im_name}) LIKE :srd_q')
        if j_itemname:
            search_bits.append(f'UPPER(j.{j_itemname}) LIKE :srd_q')
        filter_parts.append('(' + ' OR '.join(search_bits) + ')')
    icode = str(itemcode or '').strip()
    if icode:
        filter_parts.append('TO_CHAR(j.ITEMCODE) = :srd_itemcode')
        params['srd_itemcode'] = icode
    cat_filter = str(category_code or '').strip()
    if cat_filter and im and im_cat:
        filter_parts.append(f'TO_CHAR(im.{im_cat}) = :srd_category')
        params['srd_category'] = cat_filter
    where_sql = ' AND '.join(filter_parts)
    try:
        if mode == 'detail':
            q = f"""
                SELECT * FROM (
                    SELECT
                        TO_CHAR(TRUNC(j.CREATEDDATE), 'YYYY-MM-DD') AS stock_date,
                        TO_CHAR(j.CREATEDDATE, 'HH24:MI:SS') AS stock_time,
                        j.ITEMCODE AS itemcode,
                        {itemname_sel} AS itemname,
                        {uom_sel} AS uom,
                        NVL(j.TRANSTYPE, '') AS transtype,
                        NVL(j.SOURCE_DOC, '') AS source_doc,
                        NVL(j.SOURCE_NO, '') AS source_no,
                        CASE WHEN NVL(j.QTY, 0) > 0 THEN NVL(j.QTY, 0) ELSE 0 END AS qty_in,
                        CASE WHEN NVL(j.QTY, 0) < 0 THEN ABS(NVL(j.QTY, 0)) ELSE 0 END AS qty_out,
                        NVL(j.QTY, 0) AS net_qty,
                        NVL(j.RATE, 0) AS rate,
                        NVL(j.AMOUNT, 0) AS amount,
                        ROUND(ABS({line_value_expr}), 2) AS line_value,
                        {cost_im_sel} AS costprice,
                        {f"NVL(j.{j_wh_code_col}, '')" if j_wh_code_col else "''"} AS warehouse_code,
                        {f"NVL(j.{j_wh_id_col}, '')" if j_wh_id_col else "''"} AS warehouse_id
                    FROM {jtbl} j
                    {join_im}
                    WHERE {where_sql}
                    ORDER BY j.CREATEDDATE DESC, j.ITEMCODE, j.RECEIPTNO, j.LINENO
                )
                WHERE ROWNUM <= :srd_cap
            """
            return (_safe_rows(q, params) or [], None)
        if mode == 'summary_stock':
            if not im:
                im2_join = ''
                name_outer = "CAST(NULL AS VARCHAR2(400))"
                uom_outer = "CAST(NULL AS VARCHAR2(40))"
            else:
                im2_join = f'LEFT JOIN {im} im2 ON im2.{im_ic} = m.itemcode AND im2.{im_loc} = :srd_loc'
                name_outer = f"NVL(im2.{im_name}, '')" if im_name else "CAST(NULL AS VARCHAR2(400))"
                uom_outer = f"NVL(im2.{im_uom}, '')" if im_uom else "CAST(NULL AS VARCHAR2(40))"
            q = f"""
                SELECT * FROM (
                    SELECT
                        m.itemcode,
                        {name_outer} AS itemname,
                        {uom_outer} AS uom,
                        {cost_im2_sel} AS costprice,
                        ROUND(NVL(op.opening_stock, 0), 3) AS opening_stock,
                        ROUND(NVL(m.qty_in, 0), 3) AS qty_in,
                        ROUND(NVL(m.qty_out, 0), 3) AS qty_out,
                        ROUND(NVL(m.net_qty, 0), 3) AS net_qty,
                        ROUND(NVL(cl.closing_stock, 0), 3) AS closing_stock,
                        ROUND(NVL(op.opening_stock, 0) * {cost_im2_sel}, 2) AS opening_value,
                        ROUND(NVL(m.value_in, 0), 2) AS value_in,
                        ROUND(NVL(m.value_out, 0), 2) AS value_out,
                        ROUND(NVL(m.net_value, 0), 2) AS net_value,
                        ROUND(NVL(cl.closing_stock, 0) * {cost_im2_sel}, 2) AS closing_value
                    FROM (
                        SELECT
                            j.ITEMCODE AS itemcode,
                            SUM(CASE WHEN NVL(j.QTY, 0) > 0 THEN NVL(j.QTY, 0) ELSE 0 END) AS qty_in,
                            SUM(CASE WHEN NVL(j.QTY, 0) < 0 THEN ABS(NVL(j.QTY, 0)) ELSE 0 END) AS qty_out,
                            SUM(NVL(j.QTY, 0)) AS net_qty,
                            {agg_value_in} AS value_in,
                            {agg_value_out} AS value_out,
                            {agg_value_net} AS net_value
                        FROM {jtbl} j
                        {join_im}
                        WHERE {where_sql}
                        GROUP BY j.ITEMCODE
                    ) m
                    LEFT JOIN (
                        SELECT
                            j3.ITEMCODE AS itemcode,
                            SUM(NVL(j3.QTY, 0)) AS opening_stock
                        FROM {jtbl} j3
                        WHERE j3.LOCATIONCODE = :srd_loc
                          AND TRUNC(j3.CREATEDDATE) < TO_DATE(:srd_df, 'YYYY-MM-DD')
                        GROUP BY j3.ITEMCODE
                    ) op ON op.itemcode = m.itemcode
                    LEFT JOIN (
                        SELECT
                            j4.ITEMCODE AS itemcode,
                            SUM(NVL(j4.QTY, 0)) AS closing_stock
                        FROM {jtbl} j4
                        WHERE j4.LOCATIONCODE = :srd_loc
                          AND TRUNC(j4.CREATEDDATE) <= TO_DATE(:srd_dt, 'YYYY-MM-DD')
                        GROUP BY j4.ITEMCODE
                    ) cl ON cl.itemcode = m.itemcode
                    {im2_join}
                    ORDER BY {name_outer if im and im_name else 'm.itemcode'}, m.itemcode
                )
                WHERE ROWNUM <= :srd_cap
            """
            return (_safe_rows(q, params) or [], None)
        if not im:
            im2_join = ''
            name_outer = "CAST(NULL AS VARCHAR2(400))"
            uom_outer = "CAST(NULL AS VARCHAR2(40))"
        else:
            im2_join = f'LEFT JOIN {im} im2 ON im2.{im_ic} = m.itemcode AND im2.{im_loc} = :srd_loc'
            name_outer = f"NVL(im2.{im_name}, '')" if im_name else "CAST(NULL AS VARCHAR2(400))"
            uom_outer = f"NVL(im2.{im_uom}, '')" if im_uom else "CAST(NULL AS VARCHAR2(40))"
        q = f"""
            SELECT * FROM (
                SELECT
                    TO_CHAR(m.stock_date, 'YYYY-MM-DD') AS stock_date,
                    m.itemcode,
                    {name_outer} AS itemname,
                    {uom_outer} AS uom,
                    {cost_im2_sel} AS costprice,
                    ROUND(NVL(m.qty_in, 0), 3) AS qty_in,
                    ROUND(NVL(m.qty_out, 0), 3) AS qty_out,
                    ROUND(NVL(m.net_qty, 0), 3) AS net_qty,
                    ROUND(NVL(c.closing_stock, 0), 3) AS closing_stock,
                    ROUND(NVL(c.closing_stock, 0) - NVL(m.net_qty, 0), 3) AS opening_stock,
                    ROUND((NVL(c.closing_stock, 0) - NVL(m.net_qty, 0)) * {cost_im2_sel}, 2) AS opening_value,
                    ROUND(NVL(m.value_in, 0), 2) AS value_in,
                    ROUND(NVL(m.value_out, 0), 2) AS value_out,
                    ROUND(NVL(m.net_value, 0), 2) AS net_value,
                    ROUND(NVL(c.closing_stock, 0) * {cost_im2_sel}, 2) AS closing_value
                FROM (
                    SELECT
                        j.ITEMCODE AS itemcode,
                        TRUNC(j.CREATEDDATE) AS stock_date,
                        SUM(CASE WHEN NVL(j.QTY, 0) > 0 THEN NVL(j.QTY, 0) ELSE 0 END) AS qty_in,
                        SUM(CASE WHEN NVL(j.QTY, 0) < 0 THEN ABS(NVL(j.QTY, 0)) ELSE 0 END) AS qty_out,
                        SUM(NVL(j.QTY, 0)) AS net_qty,
                        {agg_value_in} AS value_in,
                        {agg_value_out} AS value_out,
                        {agg_value_net} AS net_value
                    FROM {jtbl} j
                    {join_im}
                    WHERE {where_sql}
                    GROUP BY j.ITEMCODE, TRUNC(j.CREATEDDATE)
                ) m
                LEFT JOIN (
                    SELECT
                        itemcode,
                        stock_date,
                        SUM(day_net) OVER (
                            PARTITION BY itemcode
                            ORDER BY stock_date
                            ROWS UNBOUNDED PRECEDING
                        ) AS closing_stock
                    FROM (
                        SELECT
                            j2.ITEMCODE AS itemcode,
                            TRUNC(j2.CREATEDDATE) AS stock_date,
                            SUM(NVL(j2.QTY, 0)) AS day_net
                        FROM {jtbl} j2
                        WHERE j2.LOCATIONCODE = :srd_loc
                          AND TRUNC(j2.CREATEDDATE) <= TO_DATE(:srd_dt, 'YYYY-MM-DD')
                        GROUP BY j2.ITEMCODE, TRUNC(j2.CREATEDDATE)
                    )
                ) c ON c.itemcode = m.itemcode AND c.stock_date = m.stock_date
                {im2_join}
                ORDER BY m.stock_date DESC, m.itemcode
            )
            WHERE ROWNUM <= :srd_cap
        """
        rows = _safe_rows(q, params) or []
        return (rows, None)
    except Exception as e:
        logger.exception('Stock report datewise failed: %s', e)
        return ([], str(e))

@bp.route('/reports/stock-report-datewise', methods=['GET'])
def stock_report_datewise():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    date_from = (request.args.get('date_from') or '').strip()
    date_to = (request.args.get('date_to') or '').strip()
    date_from, date_to = _default_stock_datewise_range(date_from, date_to)
    search = (request.args.get('search') or '').strip()
    itemcode = (request.args.get('itemcode') or '').strip()
    category_code = (request.args.get('category_code') or '').strip()
    transtype = (request.args.get('transtype') or '').strip()
    report_mode = (request.args.get('report_mode') or 'summary').strip().lower()
    if report_mode not in ('summary', 'summary_stock', 'detail'):
        report_mode = 'summary'
    cap_raw = (request.args.get('max_rows') or '').strip()
    try:
        row_cap = int(cap_raw) if cap_raw.isdigit() else 8000
    except (TypeError, ValueError):
        row_cap = 8000
    rows, err = _get_stock_report_datewise_rows(
        date_from=date_from,
        date_to=date_to,
        search=search,
        itemcode=itemcode,
        category_code=category_code,
        transtype=transtype,
        report_mode=report_mode,
        row_cap=row_cap,
    )
    category_options = _get_last_transactions_category_options()
    journal_table = _detect_itemjournal_table() or ''
    grid_totals = _compute_stock_datewise_grid_totals(rows, report_mode)
    return render_template(
        'reports/stock_report_datewise.html',
        rows=rows,
        grid_totals=grid_totals,
        error_message=err or '',
        journal_table=journal_table,
        category_options=category_options,
        filters={
            'date_from': date_from,
            'date_to': date_to,
            'search': search,
            'itemcode': itemcode,
            'item_label': _resolve_report_item_label(itemcode),
            'category_code': category_code,
            'transtype': transtype,
            'report_mode': report_mode,
            'max_rows': str(row_cap),
        },
    )

@bp.route('/reports/stock-report-datewise/export-excel', methods=['GET'])
def stock_report_datewise_export_excel():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    date_from = (request.args.get('date_from') or '').strip()
    date_to = (request.args.get('date_to') or '').strip()
    date_from, date_to = _default_stock_datewise_range(date_from, date_to)
    search = (request.args.get('search') or '').strip()
    itemcode = (request.args.get('itemcode') or '').strip()
    category_code = (request.args.get('category_code') or '').strip()
    transtype = (request.args.get('transtype') or '').strip()
    report_mode = (request.args.get('report_mode') or 'summary').strip().lower()
    if report_mode not in ('summary', 'summary_stock', 'detail'):
        report_mode = 'summary'
    cap_raw = (request.args.get('max_rows') or '').strip()
    try:
        row_cap = int(cap_raw) if cap_raw.isdigit() else 8000
    except (TypeError, ValueError):
        row_cap = 8000
    rows, err = _get_stock_report_datewise_rows(
        date_from=date_from,
        date_to=date_to,
        search=search,
        itemcode=itemcode,
        category_code=category_code,
        transtype=transtype,
        report_mode=report_mode,
        row_cap=row_cap,
    )
    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output)
    if report_mode == 'detail':
        writer.writerow(['SLNO', 'DATE', 'TIME', 'ITEMCODE', 'ITEMNAME', 'UOM', 'COSTPRICE', 'TRANSTYPE', 'SOURCE_DOC', 'SOURCE_NO', 'QTY_IN', 'QTY_OUT', 'NET_QTY', 'RATE', 'AMOUNT', 'LINE_VALUE', 'WAREHOUSE_CODE', 'WAREHOUSE_ID'])
        for idx, r in enumerate(rows, start=1):
            writer.writerow([
                idx,
                r.get('stock_date') or '',
                r.get('stock_time') or '',
                r.get('itemcode') if r.get('itemcode') is not None else '',
                r.get('itemname') or '',
                r.get('uom') or '',
                f"{_to_float(r.get('costprice')):.4f}",
                r.get('transtype') or '',
                r.get('source_doc') or '',
                r.get('source_no') or '',
                f"{_to_float(r.get('qty_in')):.3f}",
                f"{_to_float(r.get('qty_out')):.3f}",
                f"{_to_float(r.get('net_qty')):.3f}",
                f"{_to_float(r.get('rate')):.4f}",
                f"{_to_float(r.get('amount')):.4f}",
                f"{_to_float(r.get('line_value')):.2f}",
                r.get('warehouse_code') or '',
                r.get('warehouse_id') if r.get('warehouse_id') is not None else '',
            ])
    elif report_mode == 'summary_stock':
        writer.writerow(['SLNO', 'ITEMCODE', 'ITEMNAME', 'UOM', 'COSTPRICE', 'OPENING_STOCK', 'QTY_IN', 'QTY_OUT', 'NET_QTY', 'CLOSING_STOCK', 'OPENING_VALUE', 'VALUE_IN', 'VALUE_OUT', 'NET_VALUE', 'CLOSING_VALUE'])
        for idx, r in enumerate(rows, start=1):
            writer.writerow([
                idx,
                r.get('itemcode') if r.get('itemcode') is not None else '',
                r.get('itemname') or '',
                r.get('uom') or '',
                f"{_to_float(r.get('costprice')):.4f}",
                f"{_to_float(r.get('opening_stock')):.3f}",
                f"{_to_float(r.get('qty_in')):.3f}",
                f"{_to_float(r.get('qty_out')):.3f}",
                f"{_to_float(r.get('net_qty')):.3f}",
                f"{_to_float(r.get('closing_stock')):.3f}",
                f"{_to_float(r.get('opening_value')):.2f}",
                f"{_to_float(r.get('value_in')):.2f}",
                f"{_to_float(r.get('value_out')):.2f}",
                f"{_to_float(r.get('net_value')):.2f}",
                f"{_to_float(r.get('closing_value')):.2f}",
            ])
    else:
        writer.writerow(['SLNO', 'DATE', 'ITEMCODE', 'ITEMNAME', 'UOM', 'COSTPRICE', 'OPENING_STOCK', 'QTY_IN', 'QTY_OUT', 'NET_QTY', 'CLOSING_STOCK', 'OPENING_VALUE', 'VALUE_IN', 'VALUE_OUT', 'NET_VALUE', 'CLOSING_VALUE'])
        for idx, r in enumerate(rows, start=1):
            writer.writerow([
                idx,
                r.get('stock_date') or '',
                r.get('itemcode') if r.get('itemcode') is not None else '',
                r.get('itemname') or '',
                r.get('uom') or '',
                f"{_to_float(r.get('costprice')):.4f}",
                f"{_to_float(r.get('opening_stock')):.3f}",
                f"{_to_float(r.get('qty_in')):.3f}",
                f"{_to_float(r.get('qty_out')):.3f}",
                f"{_to_float(r.get('net_qty')):.3f}",
                f"{_to_float(r.get('closing_stock')):.3f}",
                f"{_to_float(r.get('opening_value')):.2f}",
                f"{_to_float(r.get('value_in')):.2f}",
                f"{_to_float(r.get('value_out')):.2f}",
                f"{_to_float(r.get('net_value')):.2f}",
                f"{_to_float(r.get('closing_value')):.2f}",
            ])
    if rows:
        gt = _compute_stock_datewise_grid_totals(rows, report_mode)
        if report_mode == 'detail':
            writer.writerow([
                'TOTAL',
                '',
                '',
                '',
                '',
                '',
                '',
                '',
                '',
                '',
                f"{_to_float(gt.get('qty_in')):.3f}",
                f"{_to_float(gt.get('qty_out')):.3f}",
                f"{_to_float(gt.get('net_qty')):.3f}",
                '',
                f"{_to_float(gt.get('amount')):.4f}",
                f"{_to_float(gt.get('line_value')):.2f}",
                '',
            ])
        elif report_mode == 'summary_stock':
            writer.writerow([
                'TOTAL',
                '',
                '',
                '',
                '',
                f"{_to_float(gt.get('opening_stock')):.3f}",
                f"{_to_float(gt.get('opening_value')):.2f}",
                f"{_to_float(gt.get('qty_in')):.3f}",
                f"{_to_float(gt.get('value_in')):.2f}",
                f"{_to_float(gt.get('qty_out')):.3f}",
                f"{_to_float(gt.get('value_out')):.2f}",
                f"{_to_float(gt.get('net_qty')):.3f}",
                f"{_to_float(gt.get('net_value')):.2f}",
                f"{_to_float(gt.get('closing_stock')):.3f}",
                f"{_to_float(gt.get('closing_value')):.2f}",
            ])
        else:
            writer.writerow([
                'TOTAL',
                '',
                '',
                '',
                '',
                '',
                '',
                '',
                f"{_to_float(gt.get('qty_in')):.3f}",
                f"{_to_float(gt.get('value_in')):.2f}",
                f"{_to_float(gt.get('qty_out')):.3f}",
                f"{_to_float(gt.get('value_out')):.2f}",
                f"{_to_float(gt.get('net_qty')):.3f}",
                f"{_to_float(gt.get('net_value')):.2f}",
                '',
                '',
            ])
    if err:
        writer.writerow([])
        writer.writerow(['ERROR', err])
    filename = f"stock_report_datewise_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename={filename}'})

@bp.route('/reports/smart-list')
def smart_list():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    return render_template('reports/smart_list.html')

@bp.route('/reports/smart-list/api/tables')
def smart_list_tables():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    q = "\n        SELECT OBJECT_NAME AS name, OBJECT_TYPE AS obj_type\n        FROM USER_OBJECTS\n        WHERE OBJECT_TYPE IN ('TABLE', 'VIEW')\n        ORDER BY OBJECT_TYPE, OBJECT_NAME\n    "
    try:
        _, rows = _fetch_rows(q, {})
        items = [{'name': str(r.get('name') or ''), 'type': str(r.get('obj_type') or '')} for r in rows]
        return jsonify({'success': True, 'items': items})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}, 500)

@bp.route('/reports/smart-list/api/columns')
def smart_list_columns():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    table = (request.args.get('table') or '').strip().upper()
    if not table:
        return jsonify({'success': False, 'error': 'table param required'}, 400)
    q = '\n        SELECT COLUMN_NAME, DATA_TYPE\n        FROM USER_TAB_COLUMNS\n        WHERE TABLE_NAME = :tbl\n        ORDER BY COLUMN_ID\n    '
    try:
        _, rows = _fetch_rows(q, {'tbl': table})
        cols = [{'name': str(r.get('column_name') or ''), 'type': str(r.get('data_type') or '')} for r in rows]
        return jsonify({'success': True, 'columns': cols})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}, 500)

def _smart_list_build_query(primary_table: str, joins: List[Dict], fields: List[Dict], filters: List[Dict], order_by: List[Dict], limit: int) -> tuple:
    """Build and validate a multi-table SELECT query with optional JOINs.
    Returns (sql, bind_params, col_aliases, error).
    Table aliases: primary → t0, first join → t1, second join → t2, …
    Each field/filter/order_by item must carry a 'table_alias' key (t0/t1/…).
    """
    primary_table = primary_table.strip().upper()
    alias_table: Dict[str, str] = {'t0': primary_table}
    for i, j in enumerate(joins or []):
        jt = str(j.get('table') or '').strip().upper()
        if jt:
            alias_table[f't{i + 1}'] = jt
    for alias, tname in alias_table.items():
        try:
            _, rows = _fetch_rows("SELECT OBJECT_NAME FROM USER_OBJECTS WHERE OBJECT_TYPE IN ('TABLE','VIEW') AND OBJECT_NAME = :t", {'t': tname})
            if not rows:
                return (None, {}, [], f'Table/View not found: {tname}')
        except Exception as exc:
            return (None, {}, [], str(exc))
    valid_cols: Dict[str, set] = {}
    for alias, tname in alias_table.items():
        try:
            _, col_rows = _fetch_rows('SELECT COLUMN_NAME FROM USER_TAB_COLUMNS WHERE TABLE_NAME = :tbl', {'tbl': tname})
            valid_cols[alias] = {str(r.get('column_name') or '').upper() for r in col_rows}
        except Exception as exc:
            return (None, {}, [], str(exc))
    has_joins = any((str(j.get('table') or '').strip() for j in joins or []))

    def _col_ref(talias: str, col: str) -> str:
        """Full table-aliased reference — used in SELECT, JOIN ON, WHERE, ORDER BY."""
        return f'{talias}."{col}"'

    def _gb_ref(talias: str, col: str) -> str:
        """GROUP BY reference.
        Single-table: bare "COL" avoids Oracle inline-view alias confusion.
        Multi-table:  table-qualified t0."COL" to disambiguate."""
        if has_joins:
            return f'{talias}."{col}"'
        return f'"{col}"'
    agg_allowed = {'COUNT', 'SUM', 'MIN', 'MAX', 'AVG', 'COUNT DISTINCT'}
    select_parts: List[str] = []
    group_by_parts: List[str] = []
    col_aliases: List[str] = []
    has_agg = any((str(f.get('aggregate') or '').strip().upper() in agg_allowed for f in fields))
    for f in fields:
        talias = str(f.get('table_alias') or 't0').strip()
        col = str(f.get('column') or '').strip().upper()
        alias = str(f.get('alias') or col).strip()
        agg = str(f.get('aggregate') or '').strip().upper()
        if talias not in valid_cols:
            return (None, {}, [], f'Unknown table alias: {talias}')
        if col not in valid_cols[talias]:
            return (None, {}, [], f'Invalid column: {col} (table alias {talias})')
        safe_alias = alias.replace('"', '').replace("'", '')[:60] or col
        ref = _col_ref(talias, col)
        if agg == 'COUNT DISTINCT':
            expr = f'COUNT(DISTINCT {ref})'
        elif agg in {'COUNT', 'SUM', 'MIN', 'MAX', 'AVG'}:
            expr = f'{agg}({ref})'
        else:
            expr = ref
            if has_agg:
                group_by_parts.append(_gb_ref(talias, col))
        select_parts.append(f'{expr} AS "{safe_alias}"')
        col_aliases.append(safe_alias)
    from_clause = f'"{primary_table}" t0'
    join_clauses: List[str] = []
    valid_join_types = {'INNER', 'LEFT', 'RIGHT', 'FULL'}
    for i, j in enumerate(joins or []):
        jtype = str(j.get('join_type') or 'INNER').strip().upper()
        if jtype not in valid_join_types:
            jtype = 'INNER'
        jtable = alias_table.get(f't{i + 1}', '')
        left_alias = str(j.get('left_alias') or 't0').strip()
        left_col = str(j.get('left_col') or '').strip().upper()
        right_col = str(j.get('right_col') or '').strip().upper()
        right_alias = f't{i + 1}'
        if not jtable or not left_col or (not right_col):
            return (None, {}, [], f'Incomplete join definition for t{i + 1}')
        if left_alias not in valid_cols or left_col not in valid_cols.get(left_alias, set()):
            return (None, {}, [], f'Invalid join left column: {left_col}')
        if right_col not in valid_cols.get(right_alias, set()):
            return (None, {}, [], f'Invalid join right column: {right_col}')
        join_clauses.append(f'{jtype} JOIN "{jtable}" {right_alias} ON {_col_ref(left_alias, left_col)} = {_col_ref(right_alias, right_col)}')
    ops_ok = {'=', '!=', '>', '<', '>=', '<=', 'LIKE', 'NOT LIKE', 'IS NULL', 'IS NOT NULL', 'IN'}
    bind_params: Dict[str, Any] = {}
    where_parts: List[str] = []
    for i, f in enumerate(filters or []):
        talias = str(f.get('table_alias') or 't0').strip()
        col = str(f.get('column') or '').strip().upper()
        op = str(f.get('operator') or '=').strip().upper()
        val = f.get('value')
        if talias not in valid_cols or col not in valid_cols.get(talias, set()) or op not in ops_ok:
            continue
        ref = _col_ref(talias, col)
        if op in ('IS NULL', 'IS NOT NULL'):
            where_parts.append(f'{ref} {op}')
        elif op == 'IN':
            vals = [v.strip() for v in str(val or '').split(',') if v.strip()]
            if vals:
                ph = [f':fv{i}_{j}' for j in range(len(vals))]
                for j, v in enumerate(vals):
                    bind_params[f'fv{i}_{j}'] = v
                where_parts.append(f"{ref} IN ({', '.join(ph)})")
        elif op in ('LIKE', 'NOT LIKE'):
            bind_params[f'fv{i}'] = str(val or '')
            where_parts.append(f'{ref} {op} :fv{i}')
        else:
            bind_params[f'fv{i}'] = val
            where_parts.append(f'{ref} {op} :fv{i}')
    order_parts: List[str] = []
    for o in order_by or []:
        talias = str(o.get('table_alias') or 't0').strip()
        col = str(o.get('column') or '').strip().upper()
        direction = 'DESC' if str(o.get('direction') or '').upper() == 'DESC' else 'ASC'
        if talias in valid_cols and col in valid_cols[talias]:
            order_parts.append(f'{_col_ref(talias, col)} {direction}')
    sql = f"SELECT {', '.join(select_parts)} FROM {from_clause}"
    if join_clauses:
        sql += ' ' + ' '.join(join_clauses)
    if where_parts:
        sql += f" WHERE {' AND '.join(where_parts)}"
    if group_by_parts:
        sql += f" GROUP BY {', '.join(group_by_parts)}"
    if order_parts:
        sql += f" ORDER BY {', '.join(order_parts)}"
    sql = f'SELECT * FROM ({sql}) SL_W WHERE ROWNUM <= {int(limit)}'
    return (sql, bind_params, col_aliases, None)

@bp.route('/reports/smart-list/api/run', methods=['POST'])
def smart_list_run():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    data = request.get_json(silent=True) or {}
    primary_table = (data.get('table') or '').strip().upper()
    joins = data.get('joins') or []
    fields = data.get('fields') or []
    filters = data.get('filters') or []
    order_by = data.get('order_by') or []
    limit = min(int(data.get('limit') or 500), 5000)
    if not primary_table or not fields:
        return jsonify({'success': False, 'error': 'Table and at least one field required'}, 400)
    sql, bind_params, col_aliases, err = _smart_list_build_query(primary_table, joins, fields, filters, order_by, limit)
    if err:
        return jsonify({'success': False, 'error': err}, 400)
    try:
        _, rows = _fetch_rows(sql, bind_params)
        result_rows = [['' if v is None else str(v) for v in r.values()] for r in rows]
        return jsonify({'success': True, 'columns': col_aliases, 'rows': result_rows, 'count': len(result_rows), 'sql': sql})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc), 'sql': sql}, 500)

def _smart_list_user_name() -> str:
    raw_user = session.get('user')
    if isinstance(raw_user, dict):
        return str(raw_user.get('username') or raw_user.get('user') or '').strip()
    return str(raw_user or '').strip()

@bp.route('/reports/smart-list/api/ai/history/list')
def smart_list_ai_history_list():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_name = _smart_list_user_name()
    tenant_id = str(session.get('tenant_id') or '').strip() or None
    if not user_name:
        return jsonify({'success': True, 'sessions': []})
    if tenant_id:
        _apply_active_connection(tenant_id)
    limit = min(max(int(request.args.get('limit') or 20), 1), 50)
    rows = get_smart_list_ai_chat_sessions(user_name=user_name, tenant_id=tenant_id, limit=limit)
    return jsonify({'success': True, 'sessions': rows})

@bp.route('/reports/smart-list/api/ai/history/<chat_id>')
def smart_list_ai_history_get(chat_id: str):
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_name = _smart_list_user_name()
    tenant_id = str(session.get('tenant_id') or '').strip() or None
    if not user_name:
        return jsonify({'success': True, 'chat_id': chat_id, 'messages': []})
    if tenant_id:
        _apply_active_connection(tenant_id)
    rows = get_smart_list_ai_chat_messages(user_name=user_name, tenant_id=tenant_id, chat_id=str(chat_id or '').strip(), limit=500)
    msgs = [{'role': str(r.get('role') or ''), 'content': str(r.get('content') or '')} for r in rows]
    return jsonify({'success': True, 'chat_id': chat_id, 'messages': msgs})

@bp.route('/reports/smart-list/api/ai/history/<chat_id>', methods=['DELETE'])
def smart_list_ai_history_delete(chat_id: str):
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_name = _smart_list_user_name()
    tenant_id = str(session.get('tenant_id') or '').strip() or None
    if not user_name:
        return jsonify({'success': False, 'error': 'Invalid user'}, 400)
    if tenant_id:
        _apply_active_connection(tenant_id)
    deleted = delete_smart_list_ai_chat(user_name=user_name, tenant_id=tenant_id, chat_id=str(chat_id or '').strip())
    return jsonify({'success': True, 'deleted': deleted, 'chat_id': chat_id})

@bp.route('/reports/smart-list/api/ai/history/<chat_id>/title', methods=['POST'])
def smart_list_ai_history_rename(chat_id: str):
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_name = _smart_list_user_name()
    tenant_id = str(session.get('tenant_id') or '').strip() or None
    if not user_name:
        return jsonify({'success': False, 'error': 'Invalid user'}, 400)
    if tenant_id:
        _apply_active_connection(tenant_id)
    data = request.get_json(silent=True) or {}
    title = str(data.get('title') or '').strip()
    updated = rename_smart_list_ai_chat(user_name=user_name, tenant_id=tenant_id, chat_id=str(chat_id or '').strip(), title=title)
    return jsonify({'success': True, 'updated': updated, 'chat_id': chat_id, 'title': title})

@bp.route('/reports/smart-list/api/ai', methods=['POST'])
def smart_list_ai():
    """AI chat assistant with live DB tool-use: the AI can run SELECT queries directly."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    import os as _os, json as _json, re as _re
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(override=True)
    api_key = _os.environ.get('OPENAI_API_KEY', '').strip()
    if not api_key:
        return jsonify({'success': False, 'error': 'OPENAI_API_KEY is not configured. Please add it to the .env file.'}, 503)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    data = request.get_json(silent=True) or {}
    messages = data.get('messages') or []
    chat_id = str(data.get('chat_id') or '').strip()
    latest_user_message = str(data.get('latest_user_message') or '').strip()
    schema = data.get('schema') or []
    knowledge_base = str(data.get('knowledge_base') or '').strip()
    if not latest_user_message:
        for _m in reversed(messages):
            if str(_m.get('role') or '') == 'user':
                latest_user_message = str(_m.get('content') or '').strip()
                break
    if not chat_id:
        chat_id = f'chat_{uuid.uuid4().hex[:24]}'
    user_name = _smart_list_user_name()
    tbls = [s['name'] for s in schema if s.get('type') == 'TABLE'][:80]
    vws = [s['name'] for s in schema if s.get('type') == 'VIEW'][:40]
    schema_text = ''
    if tbls:
        schema_text += '\n\nAvailable Tables: ' + ', '.join(tbls)
    if vws:
        schema_text += '\n\nAvailable Views: ' + ', '.join(vws)
    kb_text = f'\n\n--- Business Knowledge Base (user-provided) ---\n{knowledge_base}' if knowledge_base else ''
    system_prompt = "You are an expert ERP database assistant for RGC Dynamics, an Oracle-based ERP system. You have LIVE access to the database through the run_sql tool. When a user asks about data, counts, totals, lists, or reports — USE the run_sql tool to fetch real data and answer with actual numbers/rows. Do NOT just generate SQL without running it when the user wants an answer. Use get_columns tool to explore a table's columns before querying if needed. If you get ORA-00904 (invalid identifier) or ORA-00942 (table/view not found), you MUST verify columns/objects for all FROM/JOIN tables/views before retrying SQL. Always use Oracle SQL syntax (ROWNUM not LIMIT, SYSDATE not NOW(), TO_DATE for dates). For every user message, first provide a one-line corrected/rephrased version of the user's request (fix grammar/spelling, keep original intent) in the format: 'Corrected request: ...'. Then provide the actual answer/result. If a query fails, include the exact Oracle/database error message (including ORA code) in your response before suggesting a fix. Keep responses concise unless the user explicitly asks for complete/full/all data. If user asks complete/full data, return all fetched rows (up to tool limit) in a markdown table. Format any SQL you show in ```sql blocks." + schema_text + kb_text
    tools = [{'type': 'function', 'function': {'name': 'run_sql', 'description': 'Run a SELECT query on the database and return actual rows. Use this to answer any question about real data.', 'parameters': {'type': 'object', 'properties': {'sql': {'type': 'string', 'description': 'Oracle SELECT query to execute'}, 'limit': {'type': 'integer', 'description': 'Max rows to return (default 200, max 200)', 'default': 200}}, 'required': ['sql']}}}, {'type': 'function', 'function': {'name': 'get_columns', 'description': 'Get column names and data types for a table or view.', 'parameters': {'type': 'object', 'properties': {'table_name': {'type': 'string', 'description': 'Table or view name (uppercase)'}}, 'required': ['table_name']}}}]
    _BLOCKED_AI = {'INSERT', 'UPDATE', 'DELETE', 'DROP', 'TRUNCATE', 'ALTER', 'CREATE', 'RENAME', 'MERGE', 'REPLACE', 'EXECUTE', 'EXEC', 'CALL', 'GRANT', 'REVOKE', 'COMMIT', 'ROLLBACK', 'SAVEPOINT'}

    def _run_tool_sql(sql: str, limit: int=200):
        """Returns (text_for_ai, structured_dict_for_grid)."""
        sql = sql.strip()
        stripped = _re.sub('--[^\\n]*', ' ', sql)
        stripped = _re.sub('/\\*.*?\\*/', ' ', stripped, flags=_re.DOTALL).strip()
        if ';' in stripped:
            return ('ERROR: Semicolons not allowed', None)
        fw = (stripped.split() or [''])[0].upper()
        if fw not in ('SELECT', 'WITH'):
            return ('ERROR: Only SELECT/WITH allowed', None)
        tokens = set(_re.findall('\\b[A-Za-z_]+\\b', stripped.upper()))
        bad = tokens & _BLOCKED_AI
        if bad:
            return (f"ERROR: Blocked keywords: {', '.join(sorted(bad))}", None)
        limit = min(int(limit or 200), 200)
        wrapped = f'SELECT * FROM ({sql}) AI_Q WHERE ROWNUM <= {limit}'
        try:
            _, rows = _fetch_rows(wrapped, {})
            if not rows:
                return ('Query returned 0 rows.', {'columns': [], 'rows': [], 'count': 0})
            cols = list(rows[0].keys())
            result_rows = [['' if v is None else str(v) for v in r.values()] for r in rows]
            lines = [' | '.join(cols), '-' * 40]
            for r in result_rows:
                lines.append(' | '.join(r))
            capped = len(result_rows) >= limit
            if capped:
                lines.append('')
                lines.append(f'NOTE: Result is capped at {limit} rows for AI context size. Use SQL Editor for full dataset export/view.')
            text = '\n'.join(lines)
            return (text, {'columns': cols, 'rows': result_rows, 'count': len(result_rows), 'capped': capped, 'cap': limit})
        except Exception as exc:
            err = str(exc)
            guidance = _sql_error_guidance(sql, err)
            if guidance:
                return (f'ERROR: {err}\n\n{guidance}', None)
            return (f'ERROR: {err}', None)

    def _get_tool_columns(table_name: str) -> str:
        tbl = table_name.strip().upper()
        try:
            _, rows = _fetch_rows('SELECT COLUMN_NAME, DATA_TYPE FROM USER_TAB_COLUMNS WHERE TABLE_NAME = :t ORDER BY COLUMN_ID', {'t': tbl})
            if not rows:
                return f'No columns found for {tbl} (table may not exist)'
            return '\n'.join((f"{r.get('column_name')} ({r.get('data_type')})" for r in rows))
        except Exception as exc:
            return f'ERROR: {exc}'

    def _extract_sql_objects(sql: str):
        txt = _re.sub('--[^\\n]*', ' ', sql or '')
        txt = _re.sub('/\\*.*?\\*/', ' ', txt, flags=_re.DOTALL)
        matches = _re.findall('\\b(?:FROM|JOIN)\\s+([A-Za-z0-9_$.\\"#]+)', txt, flags=_re.IGNORECASE)
        out = []
        seen = set()
        for m in matches:
            token = (m or '').strip().rstrip(',')
            token = token.replace('"', '')
            if '.' in token:
                token = token.split('.')[-1]
            token = token.upper()
            if token and token not in seen:
                seen.add(token)
                out.append(token)
        return out

    def _is_identifier_or_object_error(err_text: str) -> bool:
        low = str(err_text or '').lower()
        return 'ora-00904' in low or 'ora-00942' in low

    def _sql_error_guidance(sql: str, err_text: str) -> str:
        if not _is_identifier_or_object_error(err_text):
            return ''
        objects = _extract_sql_objects(sql)[:8]
        if not objects:
            return ''
        lines = ['Auto-check (FROM/JOIN tables/views):']
        for obj in objects:
            try:
                _, obj_rows = _fetch_rows("SELECT OBJECT_TYPE FROM USER_OBJECTS WHERE OBJECT_NAME = :n AND OBJECT_TYPE IN ('TABLE','VIEW')", {'n': obj})
                if not obj_rows:
                    lines.append(f'- {obj}: NOT FOUND in USER_OBJECTS (TABLE/VIEW).')
                    continue
                obj_type = (obj_rows[0].get('object_type') or '').upper()
                _, col_rows = _fetch_rows('SELECT COLUMN_NAME FROM USER_TAB_COLUMNS WHERE TABLE_NAME = :t ORDER BY COLUMN_ID', {'t': obj})
                if not col_rows:
                    lines.append(f'- {obj} ({obj_type}): object exists but no columns visible.')
                    continue
                col_names = [str(r.get('column_name') or '').upper() for r in col_rows if r.get('column_name')]
                preview = ', '.join(col_names[:25])
                if len(col_names) > 25:
                    preview += ', ...'
                lines.append(f'- {obj} ({obj_type}) columns: {preview}')
            except Exception as exc:
                lines.append(f'- {obj}: metadata check failed ({exc})')
        lines.append('Use only the exact columns above and retry.')
        return '\n'.join(lines)
    openai_messages = [{'role': 'system', 'content': system_prompt}]
    for m in messages[-20:]:
        role = 'user' if m.get('role') == 'user' else 'assistant'
        content = str(m.get('content') or '').strip()
        if content:
            openai_messages.append({'role': role, 'content': content})
    try:
        from openai import OpenAI as _OpenAI
        client = _OpenAI(api_key=api_key)
        model = _os.environ.get('OPENAI_MODEL', 'gpt-4o-mini').strip()
        tool_calls_log = []
        last_sql_error_message = ''
        MAX_STEPS = 10
        for _step in range(MAX_STEPS):
            t_choice = 'none' if _step == MAX_STEPS - 1 else 'auto'
            resp = client.chat.completions.create(model=model, messages=openai_messages, tools=tools, tool_choice=t_choice, max_tokens=1500, temperature=0.3)
            msg = resp.choices[0].message
            if not msg.tool_calls:
                reply_text = msg.content or ''
                if last_sql_error_message:
                    low_reply = reply_text.lower()
                    low_err = last_sql_error_message.lower()
                    if low_err not in low_reply:
                        reply_text = f'Oracle error from last attempt: {last_sql_error_message}\n\n{reply_text}'
                if user_name and chat_id:
                    try:
                        if latest_user_message:
                            save_smart_list_ai_message(msg_id=f'm_{uuid.uuid4().hex[:30]}', chat_id=chat_id, user_name=user_name, tenant_id=user_dbkey, role='user', content=latest_user_message)
                        save_smart_list_ai_message(msg_id=f'm_{uuid.uuid4().hex[:30]}', chat_id=chat_id, user_name=user_name, tenant_id=user_dbkey, role='assistant', content=reply_text)
                    except Exception as save_exc:
                        logger.warning('Smart List AI history save failed: %s', save_exc)
                return jsonify({'success': True, 'reply': reply_text, 'tool_calls': tool_calls_log, 'chat_id': chat_id})
            openai_messages.append(msg)
            for tc in msg.tool_calls:
                fn = tc.function.name
                args = _json.loads(tc.function.arguments or '{}')
                if fn == 'run_sql':
                    sql_run = args.get('sql', '')
                    lim_run = int(args.get('limit') or 200)
                    result, grid_data = _run_tool_sql(sql_run, lim_run)
                    entry = {'type': 'sql', 'sql': sql_run, 'result_preview': result[:600]}
                    if isinstance(result, str) and result.startswith('ERROR:'):
                        err_full = result.replace('ERROR:', '', 1).strip()
                        last_sql_error_message = (err_full.splitlines()[0] or err_full).strip()
                        entry['error'] = last_sql_error_message
                        if _is_identifier_or_object_error(err_full):
                            auto_objects = _extract_sql_objects(sql_run)[:8]
                            auto_lines = []
                            for obj in auto_objects:
                                auto_cols = _get_tool_columns(obj)
                                tool_calls_log.append({'type': 'columns', 'table': obj, 'result_preview': auto_cols[:500], 'auto': True})
                                auto_lines.append(f'{obj}:\n{auto_cols}')
                            if auto_lines:
                                result = f'{result}\n\nAuto-ran get_columns after SQL error for detected FROM/JOIN objects:\n\n' + '\n\n'.join(auto_lines)
                    if grid_data:
                        entry['grid'] = grid_data
                        if grid_data.get('capped'):
                            entry['capped'] = True
                            entry['cap'] = int(grid_data.get('cap') or 200)
                    tool_calls_log.append(entry)
                elif fn == 'get_columns':
                    tbl_name = args.get('table_name', '')
                    result = _get_tool_columns(tbl_name)
                    tool_calls_log.append({'type': 'columns', 'table': tbl_name, 'result_preview': result[:500]})
                else:
                    result = 'Unknown tool'
                openai_messages.append({'role': 'tool', 'tool_call_id': tc.id, 'content': result})
        return jsonify({'success': True, 'reply': 'Done.', 'tool_calls': tool_calls_log, 'chat_id': chat_id})
    except Exception as exc:
        err = str(exc)
        if 'api_key' in err.lower() or 'authentication' in err.lower():
            err = 'Invalid OpenAI API key. Please check OPENAI_API_KEY in your .env file.'
        return jsonify({'success': False, 'error': err}, 500)

@bp.route('/reports/smart-list/api/sql', methods=['POST'])
def smart_list_sql():
    """Run a raw SELECT query typed by the user. Only SELECT statements allowed."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    data = request.get_json(silent=True) or {}
    raw = (data.get('sql') or '').strip()
    limit = min(int(data.get('limit') or 500), 5000)
    if not raw:
        return jsonify({'success': False, 'error': 'No SQL provided'}, 400)
    import re as _re
    stripped = _re.sub('--[^\\n]*', ' ', raw)
    stripped = _re.sub('/\\*.*?\\*/', ' ', stripped, flags=_re.DOTALL)
    stripped = stripped.strip()
    if ';' in stripped:
        return jsonify({'success': False, 'error': 'Semicolons are not allowed'}, 400)
    first_word = (stripped.split() or [''])[0].upper()
    if first_word not in ('SELECT', 'WITH'):
        return jsonify({'success': False, 'error': 'Only SELECT / WITH queries are allowed'}, 400)
    _BLOCKED = {'INSERT', 'UPDATE', 'DELETE', 'DROP', 'TRUNCATE', 'ALTER', 'CREATE', 'RENAME', 'MERGE', 'REPLACE', 'EXECUTE', 'EXEC', 'CALL', 'GRANT', 'REVOKE', 'COMMIT', 'ROLLBACK', 'SAVEPOINT'}
    tokens = set(_re.findall('\\b[A-Za-z_]+\\b', stripped.upper()))
    blocked_found = tokens & _BLOCKED
    if blocked_found:
        return jsonify({'success': False, 'error': f"Blocked keyword(s): {', '.join(sorted(blocked_found))}"}, 400)
    safe_sql = f'SELECT * FROM ({raw}) SL_SQL WHERE ROWNUM <= {limit}'
    try:
        _, rows = _fetch_rows(safe_sql, {})
        if not rows:
            return jsonify({'success': True, 'columns': [], 'rows': [], 'count': 0, 'sql': safe_sql})
        col_aliases = list(rows[0].keys())
        result_rows = [['' if v is None else str(v) for v in r.values()] for r in rows]
        return jsonify({'success': True, 'columns': col_aliases, 'rows': result_rows, 'count': len(result_rows), 'sql': safe_sql})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc), 'sql': safe_sql}, 500)

@bp.route('/reports/smart-list/api/export')
def smart_list_export():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    import json as _json
    limit = min(int(request.args.get('limit') or 5000), 50000)
    raw_sql = (request.args.get('sql_query') or '').strip()
    if raw_sql:
        import re as _re2
        _s2 = _re2.sub('--[^\\n]*', ' ', raw_sql)
        _s2 = _re2.sub('/\\*.*?\\*/', ' ', _s2, flags=_re2.DOTALL).strip()
        if ';' in _s2:
            return Response('Semicolons are not allowed', status=400)
        _fw2 = (_s2.split() or [''])[0].upper()
        if _fw2 not in ('SELECT', 'WITH'):
            return Response('Only SELECT / WITH queries are allowed', status=400)
        _BLK2 = {'INSERT', 'UPDATE', 'DELETE', 'DROP', 'TRUNCATE', 'ALTER', 'CREATE', 'RENAME', 'MERGE', 'REPLACE', 'EXECUTE', 'EXEC', 'CALL', 'GRANT', 'REVOKE', 'COMMIT', 'ROLLBACK', 'SAVEPOINT'}
        _tk2 = set(_re2.findall('\\b[A-Za-z_]+\\b', _s2.upper()))
        if _tk2 & _BLK2:
            return Response(f"Blocked keyword(s): {', '.join(sorted(_tk2 & _BLK2))}", status=400)
        sql = f'SELECT * FROM ({raw_sql}) SL_SQL WHERE ROWNUM <= {limit}'
        try:
            _, rows = _fetch_rows(sql, {})
        except Exception as exc:
            return Response(f'Query failed: {exc}', status=500)
        col_aliases = list(rows[0].keys()) if rows else []
    else:
        primary_table = (request.args.get('table') or '').strip().upper()
        joins = _json.loads(request.args.get('joins') or '[]')
        fields = _json.loads(request.args.get('fields') or '[]')
        filters = _json.loads(request.args.get('filters') or '[]')
        order_by = _json.loads(request.args.get('order_by') or '[]')
        if not primary_table or not fields:
            return Response('Table and fields required', status=400)
        sql, bind_params, col_aliases, err = _smart_list_build_query(primary_table, joins, fields, filters, order_by, limit)
        if err:
            return Response(f'Error: {err}', status=400)
        try:
            _, rows = _fetch_rows(sql, bind_params)
        except Exception as exc:
            return Response(f'Query failed: {exc}', status=500)
    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output)
    writer.writerow(col_aliases)
    for r in rows:
        writer.writerow(['' if v is None else str(v) for v in r.values()])
    fname = f"smart_list_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename={fname}'})

@bp.route('/reports/crystal-reports', methods=['GET'])
def crystal_reports():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    billno = (request.args.get('billno') or '').strip()
    error = (request.args.get('error') or '').strip()
    return render_template('reports/crystal_reports.html', billno=billno, error=error)

@bp.route('/qz/certificate', methods=['GET'])
def qz_certificate():
    if not session.get('user'):
        return Response('Unauthorized', status=401, mimetype='text/plain')
    ok, err = _ensure_qz_cert_files()
    if not ok:
        return Response(f'Certificate error: {err}', status=500, mimetype='text/plain')
    try:
        with open(_QZ_CERT_FILE, 'r', encoding='utf-8') as f:
            cert_text = f.read()
        return Response(cert_text, mimetype='text/plain')
    except Exception as exc:
        return Response(f'Certificate load failed: {exc}', status=500, mimetype='text/plain')

@bp.route('/qz/certificate/download', methods=['GET'])
def qz_certificate_download():
    if not session.get('user'):
        return Response('Unauthorized', status=401, mimetype='text/plain')
    ok, err = _ensure_qz_cert_files()
    if not ok:
        return Response(f'Certificate error: {err}', status=500, mimetype='text/plain')
    try:
        return send_file(_QZ_CERT_FILE, mimetype='application/x-pem-file', as_attachment=True, download_name='rgc-qz-certificate.pem')
    except Exception as exc:
        return Response(f'Certificate download failed: {exc}', status=500, mimetype='text/plain')

@bp.route('/qz/certificate/regenerate', methods=['POST'])
def qz_certificate_regenerate():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    ok, err = _ensure_qz_cert_files(force_regenerate=True)
    if not ok:
        return jsonify({'success': False, 'error': f'Certificate error: {err}'}, 500)
    return jsonify({'success': True, 'message': 'QZ certificate regenerated successfully.'})

@bp.route('/qz/cert-info', methods=['GET'])
def qz_cert_info():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    ok, err = _ensure_qz_cert_files()
    if not ok:
        return jsonify({'success': False, 'error': f'Certificate error: {err}'}, 500)
    if not CRYPTOGRAPHY_AVAILABLE:
        return jsonify({'success': False, 'error': 'cryptography package not available'}, 500)
    try:
        with open(_QZ_CERT_FILE, 'rb') as f:
            cert_bytes = f.read()
        cert = x509.load_pem_x509_certificate(cert_bytes)
        subject = cert.subject.rfc4514_string()
        issuer = cert.issuer.rfc4514_string()
        fingerprint_hex = cert.fingerprint(hashes.SHA256()).hex()
        return jsonify({'success': True, 'subject': subject, 'issuer': issuer, 'valid_from': cert.not_valid_before.strftime('%Y-%m-%d %H:%M:%S'), 'valid_to': cert.not_valid_after.strftime('%Y-%m-%d %H:%M:%S'), 'fingerprint_sha256': fingerprint_hex, 'cert_file': _QZ_CERT_FILE})
    except Exception as exc:
        logger.exception('QZ cert-info failed: %s', exc)
        return jsonify({'success': False, 'error': f'QZ cert-info failed: {exc}'}, 500)

@bp.route('/qz/sign', methods=['POST'])
def qz_sign():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    ok, err = _ensure_qz_cert_files()
    if not ok:
        return jsonify({'success': False, 'error': f'Certificate error: {err}'}, 500)
    payload = request.get_json(silent=True) or {}
    request_to_sign = str(payload.get('request') or '').strip()
    if not request_to_sign:
        return jsonify({'success': False, 'error': 'Missing request payload'}, 400)
    try:
        with open(_QZ_KEY_FILE, 'rb') as f:
            private_key = serialization.load_pem_private_key(f.read(), password=None)
        signature = private_key.sign(request_to_sign.encode('utf-8'), padding.PKCS1v15(), hashes.SHA512())
        signature_b64 = base64.b64encode(signature).decode('utf-8')
        return jsonify({'success': True, 'signature': signature_b64})
    except Exception as exc:
        logger.exception('QZ signing failed: %s', exc)
        return jsonify({'success': False, 'error': f'QZ signing failed: {exc}'}, 500)

def _resolve_crystal_report_file(report_name: str) -> Optional[str]:
    base_name = str(report_name or '').strip().lower()
    if not base_name:
        return None
    root_dir = os.path.dirname(os.path.dirname(__file__))
    crystal_dir = os.path.join(root_dir, 'crystalreports')
    if not os.path.isdir(crystal_dir):
        return None
    for fname in os.listdir(crystal_dir):
        full = os.path.join(crystal_dir, fname)
        if not os.path.isfile(full):
            continue
        stem, ext = os.path.splitext(fname)
        if stem.strip().lower() == base_name and ext.strip().lower() in {'.rpt', '.rptr'}:
            return full
    return None

@bp.route('/reports/crystal-reports/cashbilldup', methods=['POST'])
def crystal_reports_cashbilldup():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    billno_raw = (request.form.get('billno') or '').strip()
    billno, err = _parse_report_billno(billno_raw)
    if billno is None:
        return redirect(url_for('reports.crystal_reports', billno=billno_raw, error=err))
    return redirect(url_for('reports.crystal_reports_open_report', report_name='cashbilldup', billno=billno_raw))

@bp.route('/reports/crystal-reports/cashbilldup/print-payload', methods=['GET'])
def crystal_reports_cashbilldup_print_payload():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    billno_raw = (request.args.get('billno') or '').strip()
    billno, err = _parse_report_billno(billno_raw)
    if billno is None:
        return jsonify({'success': False, 'error': err}, 400)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    location_code_int = _resolve_location_code()
    header, lines = get_sales_print_data(billno, location_code_int)
    if not header:
        return jsonify({'success': False, 'error': 'Bill data not found'}, 404)
    raw_text = _build_cashbilldup_raw_text(billno=billno, header=header, lines=lines)
    pdf_url = url_for('reports.crystal_reports_open_report', report_name='cashbilldup', billno=billno, _external=True)
    return jsonify({'success': True, 'billno': billno, 'raw_text': raw_text, 'pdf_url': pdf_url, 'report_name': 'cashbilldup'})

@bp.route('/reports/crystal-reports/cashbilldup/qz-pdf', methods=['GET'])
def crystal_reports_cashbilldup_qz_pdf():
    """GRN-style invoice PDF as base64 for QZ Tray `{ type: 'pdf', format: 'base64' }` printing."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    if not REPORTLAB_AVAILABLE:
        return jsonify({'success': False, 'error': 'PDF library not available'}, 503)
    billno_raw = (request.args.get('billno') or '').strip()
    billno, err = _parse_report_billno(billno_raw)
    if billno is None:
        return jsonify({'success': False, 'error': err}, 400)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    location_code_int = _resolve_location_code()
    header, lines = get_sales_print_data(billno, location_code_int)
    if not header:
        return jsonify({'success': False, 'error': 'Bill data not found'}, 404)
    pdf_bytes = _generate_cashbilldup_pdf(billno=billno, header=header, lines=lines, invoice_title='INVOICE')
    if not pdf_bytes:
        return jsonify({'success': False, 'error': 'Failed to generate PDF'}, 500)
    pdf_b64 = base64.b64encode(pdf_bytes).decode('ascii')
    return jsonify({'success': True, 'billno': billno, 'pdf_base64': pdf_b64})

@bp.route('/reports/crystal-reports/open/<report_name>', methods=['GET'])
def crystal_reports_open_report(report_name: str):
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    billno_raw = (request.args.get('billno') or '').strip()
    billno, err = _parse_report_billno(billno_raw)
    if billno is None:
        return redirect(url_for('reports.crystal_reports', billno=billno_raw, error=err))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    report_key = str(report_name or '').strip().lower()
    if report_key in {'cashbilldup', 'salesreturn'}:
        location_code_int = _resolve_location_code()
        header, lines = get_sales_print_data(billno, location_code_int)
        if not header:
            return redirect(url_for('reports.crystal_reports', billno=billno_raw, error='Bill data not found'))
        pdf_title = 'SALES RETURN' if report_key == 'salesreturn' else 'INVOICE'
        pdf_bytes = _generate_cashbilldup_pdf(billno=billno, header=header, lines=lines, invoice_title=pdf_title)
        if not pdf_bytes:
            return redirect(url_for('reports.crystal_reports', billno=billno_raw, error='Failed to generate PDF'))
        filename_prefix = 'salesreturn' if report_key == 'salesreturn' else 'cashbilldup'
        filename = f"{filename_prefix}_{billno}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        return send_file(io.BytesIO(pdf_bytes), mimetype='application/pdf', as_attachment=False, download_name=filename, max_age=0)
    rpt_file = _resolve_crystal_report_file(report_name)
    if not rpt_file:
        return redirect(url_for('reports.crystal_reports', billno=billno_raw, error=f'{report_name} report not found in crystalreports folder'))
    return send_file(rpt_file, as_attachment=False, download_name=os.path.basename(rpt_file), mimetype='application/octet-stream')

def _to_float(v: Any, default: float=0.0) -> float:
    try:
        return float(v if v is not None else default)
    except Exception:
        return default

def _read_system_logs(hours: int=48, level: str='', q: str='') -> List[Dict[str, Any]]:
    """Read log file and return rows within time window."""
    if not os.path.exists(_LOG_FILE_PATH):
        return []
    hours = max(1, min(int(hours or 48), 720))
    level = (level or '').strip().upper()
    q = (q or '').strip().lower()
    cutoff = datetime.now() - timedelta(hours=hours)
    ts_re = re.compile('^(\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2}(?:,\\d{1,6})?) \\[([A-Z]+)\\] ([^:]+): (.*)$')
    rows: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    with open(_LOG_FILE_PATH, 'r', encoding='utf-8', errors='replace') as f:
        for raw in f:
            line = raw.rstrip('\n')
            m = ts_re.match(line)
            if m:
                ts_text, lvl, logger_name, msg = m.groups()
                try:
                    if ',' in ts_text:
                        ts = datetime.strptime(ts_text, '%Y-%m-%d %H:%M:%S,%f')
                    else:
                        ts = datetime.strptime(ts_text, '%Y-%m-%d %H:%M:%S')
                except Exception:
                    continue
                if ts < cutoff:
                    current = None
                    continue
                current = {'timestamp': ts_text, 'level': lvl, 'logger': logger_name, 'message': msg}
                rows.append(current)
            elif current:
                current['message'] = f"{current.get('message', '')}\n{line}"
    if level:
        rows = [r for r in rows if (r.get('level') or '').upper() == level]
    if q:
        rows = [r for r in rows if q in str(r.get('message') or '').lower() or q in str(r.get('logger') or '').lower()]
    rows = list(reversed(rows))
    if len(rows) > 5000:
        rows = rows[:5000]
    return rows

@bp.route('/reports/system-logs', methods=['GET'])
def system_logs():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    hours_raw = (request.args.get('hours') or '48').strip()
    level = (request.args.get('level') or '').strip().upper()
    q = (request.args.get('q') or '').strip()
    try:
        hours = max(1, min(int(hours_raw), 720))
    except Exception:
        hours = 48
    rows = _read_system_logs(hours=hours, level=level, q=q)
    return render_template('reports/system_logs.html', rows=rows, filters={'hours': str(hours), 'level': level, 'q': q})

def _detect_stock_report_supplier_col(item_table: str) -> Optional[str]:
    return _detect_column(item_table, ['SUPPLIERNAME', 'SUPPLIER_NAME', 'suppliername', 'supplier_name'])

def _stock_report_qty_column_label(filters: Dict[str, Any]) -> str:
    """Header for the qty column: selected **TBLLOCATION.DBCODE** when store filter is set, else aggregate **currentstock**."""
    s = (filters.get('storecode') or '').strip().upper()
    return s if s else 'Current Stock'

def _stock_report_tbllocation_store_pick_rows(locationcode: Optional[str]=None) -> List[Dict[str, str]]:
    """Stores from **TBLLOCATION**: prefer **DBCODE** rows only when DBCODE exists; else CODE + description."""
    tbl = resolve_warehouse_master_table()
    if not tbl:
        return []
    dbcode_col = _detect_column(tbl, ['DBCODE', 'dbcode'])
    code_fallback = _detect_column(tbl, ['CODE', 'code'])
    if dbcode_col:
        key_col = dbcode_col
    elif code_fallback:
        key_col = code_fallback
    else:
        return []
    lc_col = _detect_column(tbl, ['LOCATIONCODE', 'locationcode'])
    desc_col = _detect_column(tbl, ['DESCRIPTION', 'description', 'NAME', 'name', 'LOCATIONNAME', 'locationname'])
    where_parts = [f'TRIM({key_col}) IS NOT NULL', f'NVL(LENGTH(TRIM({key_col})), 0) > 0']
    params: Dict[str, Any] = {}
    loc_f = (locationcode or '').strip()
    if loc_f and lc_col:
        where_parts.append(f'TO_CHAR({lc_col}) = :lc')
        params['lc'] = loc_f
    desc_expr = desc_col if desc_col else 'CAST(NULL AS VARCHAR2(1))'
    q = f"SELECT DISTINCT TRIM({key_col}) AS code, TRIM({desc_expr}) AS description FROM {tbl} WHERE {' AND '.join(where_parts)} ORDER BY 1"
    try:
        raw = _safe_rows(q, params) or []
    except Exception:
        logger.exception('Stock report TBLLOCATION store list failed')
        return []
    out: List[Dict[str, str]] = []
    seen: set = set()
    for r in raw:
        code = str(r.get('code') or '').strip().upper()
        if not code or code in seen:
            continue
        seen.add(code)
        desc = str(r.get('description') or '').strip()
        label = f'{code} — {desc}' if desc else code
        out.append({'code': code, 'label': label})
    return out

def _normalize_stock_report_cost_method(raw: Optional[str]) -> str:
    k = (raw or '').strip().lower().replace(' ', '_').replace('-', '_')
    if k in ('average', 'avg', 'average_cost', 'averagecost'):
        return 'average'
    return 'last_purchase'

def _stock_report_cost_column_label(filters: Dict[str, Any]) -> str:
    if _normalize_stock_report_cost_method(filters.get('cost_method')) == 'average':
        return 'Average Cost'
    return 'Cost Price'

def _stock_report_cost_sql_expr(im_tbl: Optional[str], im_alias: str, imd_tbl: str, details_alias: str, cost_method: str) -> str:
    """Unit cost for stock value: last purchase = COSTPRICE; average = AVERAGECOST with COSTPRICE fallback."""
    use_avg = _normalize_stock_report_cost_method(cost_method) == 'average'
    im_cost = _detect_column(im_tbl, ['COSTPRICE', 'costprice', 'CostPrice']) if im_tbl else None
    im_avg = _detect_column(im_tbl, ['AVERAGECOST', 'AVERAGE_COST', 'averagecost', 'AVGCOST', 'avgcost']) if im_tbl else None
    d_cost = _detect_column(imd_tbl, ['COSTPRICE', 'costprice', 'CostPrice'])
    d_avg = _detect_column(imd_tbl, ['AVERAGECOST', 'AVERAGE_COST', 'averagecost', 'AVGCOST', 'avgcost'])
    if im_tbl:
        if use_avg:
            if im_avg and im_cost:
                return f'NVL({im_alias}.{im_avg}, NVL({im_alias}.{im_cost}, 0))'
            if im_avg:
                return f'NVL({im_alias}.{im_avg}, 0)'
            if im_cost:
                return f'NVL({im_alias}.{im_cost}, 0)'
        elif im_cost:
            return f'NVL({im_alias}.{im_cost}, 0)'
    if use_avg:
        if d_avg and d_cost:
            return f'NVL({details_alias}.{d_avg}, NVL({details_alias}.{d_cost}, 0))'
        if d_avg:
            return f'NVL({details_alias}.{d_avg}, 0)'
    if d_cost:
        return f'NVL({details_alias}.{d_cost}, 0)'
    return '0'

def _stock_report_filters_from_request(args, *, include_summary_by: bool=False) -> Dict[str, Any]:
    _sr_pol = (args.get('stock_polarity') or '').strip().lower()
    _sr_pol = _sr_pol if _sr_pol in ('plus', 'minus') else ''
    filters: Dict[str, Any] = {'days': args.get('days') or '30', 'locationcode': args.get('locationcode') or '', 'storecode': (args.get('storecode') or '').strip().upper(), 'rawabicode': args.get('rawabicode') or '', 'itemcode': args.get('itemcode') or '', 'itemname': args.get('itemname') or '', 'suppliername': args.get('suppliername') or '', 'unit': args.get('unit') or '', 'brandname': args.get('brandname') or '', 'microcategoryname': args.get('microcategoryname') or '', 'categoryname': args.get('categoryname') or '', 'propertyname': args.get('propertyname') or '', 'min_stock': args.get('min_stock') or '', 'max_stock': args.get('max_stock') or '', 'min_avgdaily': args.get('min_avgdaily') or '', 'max_avgdaily': args.get('max_avgdaily') or '', 'min_days': args.get('min_days') or '', 'max_days': args.get('max_days') or '', 'stock_polarity': _sr_pol, 'cost_method': _normalize_stock_report_cost_method(args.get('cost_method'))}
    if include_summary_by:
        filters['summary_by'] = _normalize_stock_report_summary_by(args.get('summary_by'))
    return filters

def _oracle_db_object_valid(name: str, object_type: str='VIEW') -> bool:
    obj = (name or '').strip().upper()
    if not obj:
        return False
    rows = _safe_rows('SELECT status FROM user_objects WHERE object_name = :n AND object_type = :t AND ROWNUM = 1', {'n': obj, 't': (object_type or 'VIEW').strip().upper()})
    if not rows:
        return False
    return str(rows[0].get('status') or '').upper() == 'VALID'

def _stock_report_barcode_sql(tbl: str, alias: str) -> str:
    """Barcode column for stock report (prefers BARCODE / MANUFACTURERID over RAWABICODE)."""
    for candidates in (
        ['BARCODE', 'barcode'],
        ['MANUFACTURERID', 'MANUFACTURER_ID', 'manufacturerid'],
        ['RAWABICODE', 'rawabicode'],
    ):
        col = _detect_column(tbl, list(candidates))
        if col:
            return f"NVL(TRIM(TO_CHAR({alias}.{col})), '')"
    return "''"


def _stock_report_itemmaster_details_subquery(im_tbl: str) -> str:
    """Inline MASTER rows when ITEMMASTERDETAILS view is missing or INVALID (e.g. dropped MARKETITEM)."""
    from db.itemmaster_core import _itemmaster_stock_qty_sql
    try:
        im_cols_set = {c.upper() for c in (_get_table_columns(im_tbl) or [])}
    except Exception:
        im_cols_set = set()
    stock_expr = _itemmaster_stock_qty_sql(im_cols_set, 'im')
    cost_col = _detect_column(im_tbl, ['COSTPRICE', 'costprice'])
    avg_col = _detect_column(im_tbl, ['AVERAGECOST', 'AVERAGE_COST', 'averagecost', 'AVGCOST', 'avgcost'])
    cost_sel = f'im.{cost_col}' if cost_col else 'CAST(NULL AS NUMBER)'
    avg_sel = f'im.{avg_col}' if avg_col else 'CAST(NULL AS NUMBER)'
    sup_tbl = _detect_table(['SUPPLIER', 'supplier'])
    sup_join = ''
    sup_name = "CAST(NULL AS VARCHAR2(1))"
    if sup_tbl:
        sup_code = _detect_column(sup_tbl, ['SUPPLIERCODE', 'suppliercode'])
        im_sup = _detect_column(im_tbl, ['SUPCODE', 'SUPPLIERCODE', 'suppliercode'])
        sup_name_col = _detect_column(sup_tbl, ['SUPPLIERNAME', 'suppliername'])
        if sup_code and im_sup and sup_name_col:
            sup_join = f'LEFT JOIN {sup_tbl} sup ON im.{im_sup} = sup.{sup_code}'
            sup_name = f'sup.{sup_name_col}'
    cat_tbl = _detect_table(['CATEGORY', 'category']) or 'CATEGORY'
    prop_tbl = _detect_table(['TBLITEMPROPERTY', 'tblitemproperty'])
    micro_join = f"LEFT JOIN (SELECT code, NAME FROM {cat_tbl} WHERE flag = 'C') microcat ON im.categorycode = microcat.code" if _detect_column(im_tbl, ['CATEGORYCODE', 'categorycode']) else ''
    brand_join = f"LEFT JOIN (SELECT code, NAME FROM {cat_tbl} WHERE flag = 'B') brand ON im.brandcode = brand.code" if _detect_column(im_tbl, ['BRANDCODE', 'brandcode']) else ''
    dept_join = f"LEFT JOIN (SELECT code, NAME FROM {cat_tbl} WHERE flag = 'D') dept ON im.departmentcode = dept.code" if _detect_column(im_tbl, ['DEPARTMENTCODE', 'departmentcode']) else ''
    prop_join = ''
    prop_name = "CAST(NULL AS VARCHAR2(1))"
    if prop_tbl:
        prop_code_im = _detect_column(im_tbl, ['PROPERTY', 'property'])
        prop_code_tbl = _detect_column(prop_tbl, ['CODE', 'code'])
        prop_name_col = _detect_column(prop_tbl, ['NAME', 'name'])
        if prop_code_im and prop_code_tbl and prop_name_col:
            prop_join = f'LEFT JOIN (SELECT {prop_code_tbl} AS code, {prop_name_col} AS NAME FROM {prop_tbl}) prop ON im.{prop_code_im} = prop.code'
            prop_name = 'prop.NAME'
    baseuom = _detect_column(im_tbl, ['BASEUOM', 'baseuom']) or 'BASEUOM'
    barcode_sel = _stock_report_barcode_sql(im_tbl, 'im')
    return f"""(SELECT DISTINCT
                im.locationcode AS locationcode,
                im.rawabicode AS rawabicode,
                {barcode_sel} AS barcode,
                im.itemcode AS itemcode,
                im.itemname AS itemname,
                im.{baseuom} AS unit,
                {cost_sel} AS costprice,
                {avg_sel} AS averagecost,
                NVL({sup_name}, '') AS suppliername,
                NVL(brand.NAME, '') AS brandname,
                NVL(microcat.NAME, '') AS microcategoryname,
                NVL(dept.NAME, '') AS categoryname,
                NVL({prop_name}, '') AS propertyname,
                ({stock_expr}) AS currentstock,
                'MASTER' AS tables
            FROM {im_tbl} im
            {sup_join}
            {micro_join}
            {brand_join}
            {dept_join}
            {prop_join})"""

def _stock_report_item_details_source() -> Tuple[str, str]:
    """(FROM expression, table name for column detection). Uses ITEMMASTER when the details view is invalid."""
    view_tbl = _detect_table(['ITEMMASTERDETAILS', 'itemmasterdetails'])
    if view_tbl and _oracle_db_object_valid(view_tbl, 'VIEW'):
        return (view_tbl, view_tbl)
    im_tbl = _detect_table(['ITEMMASTER', 'itemmaster', 'ITEM_MASTER']) or 'ITEMMASTER'
    return (_stock_report_itemmaster_details_subquery(im_tbl), im_tbl)

def _stock_report_bill_movement_left_join() -> str:
    """Sales movement for avg daily / days remaining — uses detected BILL*HISTORY tables."""
    empty = '\n            LEFT JOIN (SELECT CAST(NULL AS NUMBER) AS itemcode, 0 AS baseqty FROM DUAL WHERE 1=0) d ON d.itemcode = i.itemcode'
    ht, dt = _last_tx_detect_sales_tables()
    if not ht or not dt:
        return empty
    h_no = _detect_column(ht, ['BILLNO', 'billno'])
    h_date = _detect_column(ht, ['BILLDATE', 'billdate'])
    h_cust = _detect_column(ht, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'customercode'])
    d_bill = _detect_column(dt, ['BILLNO', 'billno'])
    d_item = _detect_column(dt, ['ITEMCODE', 'ITEM_CODE', 'itemcode'])
    d_qty = _detect_column(dt, ['BASEQTY', 'BASE_QTY', 'baseqty', 'QUANTITY', 'quantity'])
    if not h_no or not h_date or not d_bill or not d_item:
        return empty
    qty_expr = f'NVL(d.{d_qty}, 0)' if d_qty else '0'
    join_h = f'h.{h_no} = d.{d_bill} AND h.{h_date} >= SYSDATE - :days_back'
    cust_join = ''
    where_parts: List[str] = []
    cust_tbl = _detect_table(['CUSTOMER', 'customer', 'CUSTOMERMASTER', 'customermaster'])
    if cust_tbl and h_cust:
        c_code = _detect_column(cust_tbl, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'customercode'])
        c_xfer = _detect_column(cust_tbl, ['TRANSFERBRANCH', 'transferbranch', 'TRANSFER_BRANCH'])
        if c_code:
            cust_join = f'LEFT JOIN {cust_tbl} cust ON cust.{c_code} = h.{h_cust}'
        if c_xfer:
            where_parts.append(f"NVL(cust.{c_xfer}, 'N') = 'N'")
    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ''
    return f"""
            LEFT JOIN (
                SELECT d.{d_item} AS itemcode, {qty_expr} AS baseqty
                FROM {dt} d
                INNER JOIN {ht} h ON {join_h}
                {cust_join}
                {where_sql}
            ) d ON d.itemcode = i.itemcode"""

def _stock_report_resolve_store_qty_parts(store_dbcode: Optional[str], imd_tbl: str, cost_method: str='last_purchase') -> Tuple[str, str, str, str]:
    """
    Prefer qty and cost from ITEMMASTER only (alias **im**) via LEFT JOIN on item + location.

    Returns (qty_sql, join_im_sql, grp_qty_expr, cost_sql). Expressions use **im** when joined.

    If ITEMMASTER is missing or cannot join on item/location keys, falls back to ITEMMASTERDETAILS (**i**)
    for currentstock/costprice (same behaviour as older builds).
    """
    no_join = ''

    def _upper_map(names: List[str]) -> Dict[str, str]:
        return {(n or '').upper(): n for n in names if n}
    im_tbl = _detect_table(['ITEMMASTER', 'itemmaster', 'ITEM_MASTER'])
    im_ic = _detect_column(im_tbl, ['ITEMCODE', 'ITEM_CODE', 'itemcode']) if im_tbl else None
    im_lc = _detect_column(im_tbl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode']) if im_tbl else None
    imd_ic = _detect_column(imd_tbl, ['ITEMCODE', 'ITEM_CODE', 'itemcode'])
    imd_lc = _detect_column(imd_tbl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    details_fallback_qty = 'NVL(i.currentstock, 0)'
    details_fallback_grp = 'i.currentstock'
    details_fallback_cost = _stock_report_cost_sql_expr(None, 'im', imd_tbl, 'i', cost_method)

    def _legacy_qty_join_cost() -> Tuple[str, str, str, str]:
        raw_l = (store_dbcode or '').strip().upper()
        if not raw_l:
            return (details_fallback_qty, no_join, details_fallback_grp, details_fallback_cost)
        col_l = _oracle_itemmaster_col_name_from_dbcode_label(raw_l)
        if not col_l:
            return (details_fallback_qty, no_join, details_fallback_grp, details_fallback_cost)
        try:
            imd_cols_l = _upper_map(_get_table_columns(imd_tbl) or [])
        except Exception:
            imd_cols_l = {}
        if col_l.upper() in imd_cols_l:
            cn_l = imd_cols_l[col_l.upper()]
            expr_l = f'NVL(i.{cn_l}, 0)'
            return (expr_l, no_join, expr_l, details_fallback_cost)
        im_tbl_l = _detect_table(['ITEMMASTER', 'itemmaster', 'ITEM_MASTER'])
        if not im_tbl_l:
            return (details_fallback_qty, no_join, details_fallback_grp, details_fallback_cost)
        try:
            im_cols_l = _upper_map(_get_table_columns(im_tbl_l) or [])
        except Exception:
            im_cols_l = {}
        if col_l.upper() not in im_cols_l:
            return (details_fallback_qty, no_join, details_fallback_grp, details_fallback_cost)
        im_cn_l = im_cols_l[col_l.upper()]
        im_ic_l = _detect_column(im_tbl_l, ['ITEMCODE', 'ITEM_CODE', 'itemcode'])
        im_lc_l = _detect_column(im_tbl_l, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
        imd_ic_l = _detect_column(imd_tbl, ['ITEMCODE', 'ITEM_CODE', 'itemcode'])
        imd_lc_l = _detect_column(imd_tbl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
        if not (im_ic_l and im_lc_l and imd_ic_l and imd_lc_l):
            return (details_fallback_qty, no_join, details_fallback_grp, details_fallback_cost)
        join_sql_l = f'LEFT JOIN {im_tbl_l} im ON im.{im_ic_l} = i.{imd_ic_l} AND im.{im_lc_l} = i.{imd_lc_l}'
        expr_l = f'NVL(im.{im_cn_l}, 0)'
        cost_sql_l = _stock_report_cost_sql_expr(im_tbl_l, 'im', imd_tbl, 'i', cost_method)
        return (expr_l, join_sql_l, expr_l, cost_sql_l)
    if not (im_tbl and im_ic and im_lc and imd_ic and imd_lc):
        return _legacy_qty_join_cost()
    join_sql = f'LEFT JOIN {im_tbl} im ON im.{im_ic} = i.{imd_ic} AND im.{im_lc} = i.{imd_lc}'
    cost_sql = _stock_report_cost_sql_expr(im_tbl, 'im', imd_tbl, 'i', cost_method)
    try:
        im_cols_set = {c.upper() for c in (_get_table_columns(im_tbl) or [])}
    except Exception:
        im_cols_set = set()
    from db.itemmaster_core import _itemmaster_stock_qty_sql
    default_qty_sql = _itemmaster_stock_qty_sql(im_cols_set, table_alias='im')
    raw = (store_dbcode or '').strip().upper()
    if not raw:
        return (default_qty_sql, join_sql, default_qty_sql, cost_sql)
    col = _oracle_itemmaster_col_name_from_dbcode_label(raw)
    try:
        im_cols = _upper_map(_get_table_columns(im_tbl) or [])
    except Exception:
        im_cols = {}
    if col and col.upper() in im_cols:
        cn = im_cols[col.upper()]
        qty_sql = f'NVL(im.{cn}, 0)'
        return (qty_sql, join_sql, qty_sql, cost_sql)
    return (default_qty_sql, join_sql, default_qty_sql, cost_sql)

def _get_stock_report_rows(filters: Dict[str, Any]) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {}
    days = (filters.get('days') or '30').strip()
    try:
        days_int = max(1, min(int(days), 3650))
    except Exception:
        days_int = 30
    locationcode = (filters.get('locationcode') or '').strip()
    rawabicode = (filters.get('rawabicode') or '').strip()
    itemcode = (filters.get('itemcode') or '').strip()
    itemname = (filters.get('itemname') or '').strip()
    suppliername = (filters.get('suppliername') or '').strip()
    unit = (filters.get('unit') or '').strip()
    brandname = (filters.get('brandname') or '').strip()
    microcategoryname = (filters.get('microcategoryname') or '').strip()
    categoryname = (filters.get('categoryname') or '').strip()
    propertyname = (filters.get('propertyname') or '').strip()
    min_stock = (filters.get('min_stock') or '').strip()
    max_stock = (filters.get('max_stock') or '').strip()
    min_avgdaily = (filters.get('min_avgdaily') or '').strip()
    max_avgdaily = (filters.get('max_avgdaily') or '').strip()
    min_days = (filters.get('min_days') or '').strip()
    max_days = (filters.get('max_days') or '').strip()
    storecode_f = (filters.get('storecode') or '').strip().upper()
    stock_polarity = (filters.get('stock_polarity') or '').strip().lower()
    if stock_polarity not in ('plus', 'minus'):
        stock_polarity = ''
    outer_where: List[str] = ['1=1']
    if locationcode:
        outer_where.append('TO_CHAR(R.locationcode) = :locationcode')
        params['locationcode'] = locationcode
    if rawabicode:
        outer_where.append("UPPER(NVL(R.barcode, '')) LIKE UPPER(:rawabicode)")
        params['rawabicode'] = f'%{rawabicode}%'
    if itemcode:
        outer_where.append('TO_CHAR(R.itemcode) = :itemcode')
        params['itemcode'] = itemcode
    if itemname:
        outer_where.append("UPPER(NVL(R.itemname, '')) LIKE UPPER(:itemname)")
        params['itemname'] = f'%{itemname}%'
    if suppliername:
        outer_where.append("UPPER(TRIM(NVL(R.suppliername, ''))) LIKE UPPER(:suppliername)")
        params['suppliername'] = f'%{suppliername.strip()}%'
    if unit:
        outer_where.append("UPPER(NVL(R.unit, '')) = UPPER(:unit)")
        params['unit'] = unit
    if brandname:
        outer_where.append("UPPER(TRIM(NVL(R.brandname, ''))) LIKE UPPER(:brandname)")
        params['brandname'] = f'%{brandname.strip()}%'
    if microcategoryname:
        outer_where.append("UPPER(TRIM(NVL(R.microcategoryname, ''))) LIKE UPPER(:microcategoryname)")
        params['microcategoryname'] = f'%{microcategoryname.strip()}%'
    if categoryname:
        outer_where.append("UPPER(TRIM(NVL(R.categoryname, ''))) LIKE UPPER(:categoryname)")
        params['categoryname'] = f'%{categoryname.strip()}%'
    if propertyname:
        outer_where.append("UPPER(TRIM(NVL(R.propertyname, ''))) LIKE UPPER(:propertyname)")
        params['propertyname'] = f'%{propertyname.strip()}%'
    if min_stock:
        outer_where.append('NVL(R.currentstock, 0) >= :min_stock')
        params['min_stock'] = _to_float(min_stock)
    if max_stock:
        outer_where.append('NVL(R.currentstock, 0) <= :max_stock')
        params['max_stock'] = _to_float(max_stock)
    if min_avgdaily:
        outer_where.append('R.avgdaily >= :min_avgdaily')
        params['min_avgdaily'] = _to_float(min_avgdaily)
    if max_avgdaily:
        outer_where.append('R.avgdaily <= :max_avgdaily')
        params['max_avgdaily'] = _to_float(max_avgdaily)
    if min_days:
        outer_where.append('R.stockremainingdays >= :min_days')
        params['min_days'] = _to_float(min_days)
    if max_days:
        outer_where.append('R.stockremainingdays <= :max_days')
        params['max_days'] = _to_float(max_days)
    if stock_polarity == 'plus':
        outer_where.append('NVL(R.currentstock, 0) > 0')
    elif stock_polarity == 'minus':
        outer_where.append('NVL(R.currentstock, 0) < 0')
    imd_from, imd_cols_tbl = _stock_report_item_details_source()
    cost_method = _normalize_stock_report_cost_method(filters.get('cost_method'))
    qty_sql, join_im_stores, grp_qty, cost_sql = _stock_report_resolve_store_qty_parts(storecode_f, imd_cols_tbl, cost_method)
    bill_mov_sql = _stock_report_bill_movement_left_join()
    barcode_expr = 'i.barcode' if imd_from.strip().startswith('(') else _stock_report_barcode_sql(imd_cols_tbl, 'i')
    query = f"\n        SELECT\n            R.locationcode,\n            R.barcode,\n            R.itemcode,\n            R.itemname,\n            R.suppliername,\n            R.unit,\n            R.costprice,\n            R.brandname,\n            R.microcategoryname,\n            R.categoryname,\n            R.propertyname,\n            R.currentstock,\n            ROUND(NVL(R.costprice, 0) * NVL(R.currentstock, 0), 2) AS stockvalue,\n            R.totalqty,\n            R.avgdaily,\n            R.stockremainingdays\n        FROM (\n            SELECT\n                i.locationcode,\n                {barcode_expr} AS barcode,\n                i.itemcode,\n                i.itemname,\n                i.unit,\n                ({cost_sql}) AS costprice,\n                i.brandname,\n                i.microcategoryname,\n                i.categoryname,\n                i.propertyname,\n                i.suppliername,\n                ({qty_sql}) AS currentstock,\n                ROUND(NVL(SUM(d.baseqty), 0), 3) AS totalqty,\n                ROUND(NVL(SUM(d.baseqty) / :days_div, 0), 2) AS avgdaily,\n                CASE\n                    WHEN NVL(SUM(d.baseqty) / :days_div, 0) = 0 THEN 0\n                    ELSE ROUND( ({qty_sql}) / (SUM(d.baseqty) / :days_div), 2)\n                END AS stockremainingdays\n            FROM {imd_from} i\n            {join_im_stores}\n            {bill_mov_sql}\n            WHERE i.tables = 'MASTER'\n            GROUP BY\n                i.locationcode,\n                {barcode_expr},\n                i.itemcode,\n                i.itemname,\n                i.unit,\n                ({cost_sql}),\n                i.brandname,\n                i.microcategoryname,\n                i.categoryname,\n                i.propertyname,\n                i.suppliername,\n                ({grp_qty})\n        ) R\n        WHERE {' AND '.join(outer_where)}\n        ORDER BY R.itemname, R.itemcode\n    "
    params['days_back'] = days_int
    params['days_div'] = days_int
    rows = _safe_rows(query, params)
    return rows or []

def _get_stock_report_pdf_location_meta(filters: Dict[str, Any]) -> Dict[str, str]:
    """Lookup LOCATIONMASTER row for PDF letterhead: filter location, else base branch."""
    empty = {'locationname': '', 'address': '', 'email': ''}
    try:
        loc_tbl = 'LOCATIONMASTER'
        loc_code_col = _detect_column(loc_tbl, ['LOCATIONCODE', 'locationcode'])
        name_col = _detect_column(loc_tbl, ['LOCATIONNAME', 'locationname', 'LOCNAME', 'locname'])
        addr_col = _detect_column(loc_tbl, ['ADDRESS', 'ADDRESS1', 'LOCATIONADDRESS', 'locationaddress'])
        email_col = _detect_column(loc_tbl, ['EMAIL', 'EMAILID', 'EMAIL_ID', 'MAIL', 'EMAILADDRESS'])
        base_flag_col = _detect_column(loc_tbl, ['BASELOCATIONFLAG', 'baselocationflag'])
        sel_sql = []
        sel_sql.append(f"NVL(TRIM({name_col}), '') AS loc_name" if name_col else "'' AS loc_name")
        sel_sql.append(f"NVL(TRIM({addr_col}), '') AS loc_addr" if addr_col else "'' AS loc_addr")
        sel_sql.append(f"NVL(TRIM({email_col}), '') AS loc_email" if email_col else "'' AS loc_email")
        filter_loc = (filters.get('locationcode') or '').strip()
        params: Dict[str, Any] = {}
        where_parts: List[str] = []
        if filter_loc and loc_code_col:
            where_parts.append(f'TO_CHAR({loc_code_col}) = :lc')
            params['lc'] = filter_loc
        elif base_flag_col:
            where_parts.append(f"NVL({base_flag_col}, 'N') = 'Y'")
        else:
            where_parts.append('1=1')
        order_clause = f'{loc_code_col} ASC' if loc_code_col else '1 ASC'
        q = f"SELECT * FROM (SELECT {', '.join(sel_sql)} FROM {loc_tbl} WHERE {' AND '.join(where_parts)} ORDER BY {order_clause}) WHERE ROWNUM = 1"
        lr = _safe_rows(q, params) or []
        if not lr and filter_loc and base_flag_col:
            q2 = f"SELECT * FROM (SELECT {', '.join(sel_sql)} FROM {loc_tbl} WHERE NVL({base_flag_col}, 'N') = 'Y' ORDER BY {order_clause}) WHERE ROWNUM = 1"
            lr = _safe_rows(q2, {}) or []
        if not lr:
            return empty
        row = lr[0]
        return {'locationname': str(row.get('loc_name') or '').strip(), 'address': str(row.get('loc_addr') or '').strip(), 'email': str(row.get('loc_email') or '').strip()}
    except Exception:
        logger.exception('Stock report PDF location meta lookup failed')
        return empty
if REPORTLAB_AVAILABLE:

    class _StockReportNumberedCanvas(rl_canvas.Canvas):
        """Footer: centered Page N of M."""

        def __init__(self, *args: Any, **kwargs: Any):
            rl_canvas.Canvas.__init__(self, *args, **kwargs)
            self._saved_page_states: List[Dict[str, Any]] = []

        def showPage(self) -> None:
            self._saved_page_states.append(dict(self.__dict__))
            self._startPage()

        def save(self) -> None:
            page_count = len(self._saved_page_states)
            for state in self._saved_page_states:
                self.__dict__.update(state)
                self._draw_footer(page_count)
                rl_canvas.Canvas.showPage(self)
            rl_canvas.Canvas.save(self)

        def _draw_footer(self, page_count: int) -> None:
            self.saveState()
            self.setFont('Helvetica', 8)
            self.setFillColor(colors.HexColor('#374151'))
            pw = float(self._pagesize[0])
            self.drawCentredString(pw / 2.0, 0.28 * inch, 'Page %d of %d' % (self._pageNumber, page_count))
            self.restoreState()

def _trunc_stock_pdf_cell(val: Any, max_len: int) -> str:
    s = str(val if val is not None else '').strip()
    if len(s) > max_len:
        return s[:max_len - 1] + '…'
    return s

def _build_stock_report_pdf(rows: List[Dict[str, Any]], filters: Dict[str, Any], *, pdf_subtitle: str='', include_totals_row: bool=False) -> Optional[bytes]:
    """Landscape A4 grid PDF for tenant Stock Report (same columns as CSV export)."""
    if not REPORTLAB_AVAILABLE:
        return None
    try:
        buffer = io.BytesIO()
        page_sz = landscape(A4)
        doc = SimpleDocTemplate(buffer, pagesize=page_sz, canvasmaker=_StockReportNumberedCanvas, topMargin=0.42 * inch, bottomMargin=0.52 * inch, leftMargin=0.28 * inch, rightMargin=0.28 * inch)
        pw = float(page_sz[0])
        usable_w = pw - float(doc.leftMargin) - float(doc.rightMargin)
        styles = getSampleStyleSheet()
        loc_hdr_name = ParagraphStyle('sr_pdf_loc_name', parent=styles['Normal'], fontSize=11, leading=13, alignment=TA_CENTER, spaceAfter=2, textColor=colors.HexColor('#0f172a'))
        loc_hdr_line = ParagraphStyle('sr_pdf_loc_line', parent=styles['Normal'], fontSize=8, leading=10, alignment=TA_CENTER, textColor=colors.HexColor('#374151'), spaceAfter=2)
        title_st = ParagraphStyle('sr_pdf_title', parent=styles['Heading1'], fontSize=13, alignment=TA_CENTER, spaceAfter=6, textColor=colors.HexColor('#0f172a'))
        subtitle_st = ParagraphStyle('sr_pdf_subtitle', parent=styles['Normal'], fontSize=9, leading=11, alignment=TA_CENTER, spaceAfter=4, textColor=colors.HexColor('#475569'))
        meta_st = ParagraphStyle('sr_pdf_meta', parent=styles['Normal'], fontSize=8, alignment=TA_LEFT, textColor=colors.HexColor('#374151'))
        hdr_center = ParagraphStyle('sr_pdf_th_c', parent=styles['Normal'], fontSize=5.5, leading=6.5, alignment=TA_CENTER, textColor=colors.HexColor('#111827'))
        hdr_right = ParagraphStyle('sr_pdf_th_r', parent=styles['Normal'], fontSize=5.5, leading=6.5, alignment=TA_RIGHT, textColor=colors.HexColor('#111827'))
        cell_left = ParagraphStyle('sr_pdf_td_l', parent=styles['Normal'], fontSize=5, leading=5.9, alignment=TA_LEFT, splitLongWords=1)
        cell_right = ParagraphStyle('sr_pdf_td_r', parent=styles['Normal'], fontSize=5, leading=5.9, alignment=TA_RIGHT, splitLongWords=1)
        story: List[Any] = []
        loc_meta = _get_stock_report_pdf_location_meta(filters)
        letterhead_name = (loc_meta.get('locationname') or '').strip() or str(session.get('location_name') or '').strip()
        if letterhead_name:
            story.append(Paragraph('<b>%s</b>' % _xml_escape(letterhead_name), loc_hdr_name))
        _addr = loc_meta.get('address') or ''
        if _addr:
            story.append(Paragraph(_xml_escape(_addr).replace('\n', '<br/>'), loc_hdr_line))
        _em = loc_meta.get('email') or ''
        if _em:
            story.append(Paragraph(_xml_escape(_em), loc_hdr_line))
        story.append(Spacer(1, 0.08 * inch))
        story.append(Paragraph(_xml_escape('Stock Report'), title_st))
        if (pdf_subtitle or '').strip():
            story.append(Paragraph(_xml_escape(pdf_subtitle.strip()), subtitle_st))
        parts: List[str] = []
        days_v = (filters.get('days') or '').strip() or '30'
        parts.append(f'Days: {_xml_escape(days_v)}')
        loc = (filters.get('locationcode') or '').strip()
        if loc:
            parts.append(f'Location code: {_xml_escape(loc)}')
        for key, lab in (('rawabicode', 'Barcode'), ('itemcode', 'Item'), ('itemname', 'Item name'), ('suppliername', 'Supplier'), ('unit', 'Unit'), ('brandname', 'Brand'), ('microcategoryname', 'Micro'), ('categoryname', 'Category'), ('propertyname', 'Property'), ('storecode', 'Store DBCODE'), ('min_stock', 'Min stock'), ('max_stock', 'Max stock'), ('min_avgdaily', 'Min avg daily'), ('max_avgdaily', 'Max avg daily'), ('min_days', 'Min days'), ('max_days', 'Max days')):
            v = (filters.get(key) or '').strip()
            if v:
                parts.append(f'{lab}: {_xml_escape(_trunc_stock_pdf_cell(v, 96))}')
        sp_pdf = (filters.get('stock_polarity') or '').strip().lower()
        if sp_pdf == 'plus':
            parts.append('Stock view: Plus only (qty greater than zero)')
        elif sp_pdf == 'minus':
            parts.append('Stock view: Minus only (qty below zero)')
        parts.append(f'Cost method: {_xml_escape(_stock_report_cost_column_label(filters))}')
        user_lbl = str(session.get('user') or '').strip()
        gen_ts = datetime.now().strftime('%Y-%m-%d %H:%M')
        meta_html = ' | '.join(parts) if parts else _xml_escape('(no filters)')
        meta_html += '<br/>'
        meta_html += _xml_escape(f"Generated: {gen_ts} | Rows: {len(rows)} | User: {user_lbl or '—'}")
        story.append(Paragraph(meta_html, meta_st))
        story.append(Spacer(1, 0.12 * inch))
        qty_hdr_pdf = _trunc_stock_pdf_cell(_stock_report_qty_column_label(filters), 14)
        cost_hdr_pdf = 'Avg.Cost' if _normalize_stock_report_cost_method(filters.get('cost_method')) == 'average' else 'Cost'
        hdr_labels = ['Loc.', 'Barcode', 'Item Cd.', 'Item Name', 'Supplier', 'UOM', cost_hdr_pdf, 'Brand', 'Micro', 'Cat.', 'Prop.', qty_hdr_pdf, 'Stk Val.', 'Tot.Qty', 'Avg/D', 'Days']
        hdr_row: List[Any] = []
        for i, h in enumerate(hdr_labels):
            st = hdr_right if i in (6, 11, 12, 13, 14, 15) else hdr_center
            hdr_row.append(Paragraph('<b>%s</b>' % _xml_escape(h), st))
        w_fracs = [0.047, 0.057, 0.051, 0.148, 0.092, 0.033, 0.045, 0.047, 0.06, 0.054, 0.049, 0.047, 0.05, 0.038, 0.041, 0.041]
        sfrac = sum(w_fracs)
        col_widths = [usable_w * (f / sfrac) for f in w_fracs]
        data: List[List[Any]] = [hdr_row]

        def _pl(txt: str, mx: int) -> Paragraph:
            return Paragraph(_xml_escape(_trunc_stock_pdf_cell(txt, mx)), cell_left)

        def _pr(txt: str) -> Paragraph:
            return Paragraph(_xml_escape(txt), cell_right)
        if not rows:
            empty_row = [Paragraph('', cell_left) for _ in range(16)]
            empty_row[0] = Paragraph(_xml_escape('No matching items for this selection.'), cell_left)
            data.append(empty_row)
            if include_totals_row:
                sum_qty = 0.0
                sum_val = 0.0
                sum_tot = 0.0
                total_row_z: List[Any] = [Paragraph('', cell_left) for _ in range(16)]
                total_row_z[3] = Paragraph('<b>%s</b>' % _xml_escape('TOTAL'), cell_left)
                total_row_z[11] = _pr(f'{sum_qty:.3f}')
                total_row_z[12] = _pr(f'{sum_val:.2f}')
                total_row_z[13] = _pr(f'{sum_tot:.3f}')
                total_row_z[14] = _pr('')
                total_row_z[15] = _pr('')
                data.append(total_row_z)
        else:
            for r in rows:
                data.append([_pl(str(r.get('locationcode') or ''), 14), _pl(str(r.get('barcode') or ''), 28), _pl(str(r.get('itemcode') or ''), 18), _pl(str(r.get('itemname') or ''), 220), _pl(str(r.get('suppliername') or ''), 120), _pl(str(r.get('unit') or ''), 14), _pr(f"{_to_float(r.get('costprice')):.3f}"), _pl(str(r.get('brandname') or ''), 40), _pl(str(r.get('microcategoryname') or ''), 90), _pl(str(r.get('categoryname') or ''), 90), _pl(str(r.get('propertyname') or ''), 70), _pr(f"{_to_float(r.get('currentstock')):.3f}"), _pr(f"{_to_float(r.get('stockvalue')):.2f}"), _pr(f"{_to_float(r.get('totalqty')):.3f}"), _pr(f"{_to_float(r.get('avgdaily')):.2f}"), _pr(f"{_to_float(r.get('stockremainingdays')):.2f}")])
            if include_totals_row:
                sum_qty = sum((_to_float(r.get('currentstock')) for r in rows))
                sum_val = sum((_to_float(r.get('stockvalue')) for r in rows))
                sum_tot = sum((_to_float(r.get('totalqty')) for r in rows))
                total_row: List[Any] = [Paragraph('', cell_left) for _ in range(16)]
                total_row[3] = Paragraph('<b>%s</b>' % _xml_escape('TOTAL'), cell_left)
                total_row[11] = _pr(f'{sum_qty:.3f}')
                total_row[12] = _pr(f'{sum_val:.2f}')
                total_row[13] = _pr(f'{sum_tot:.3f}')
                total_row[14] = _pr('')
                total_row[15] = _pr('')
                data.append(total_row)
        tbl = Table(data, repeatRows=1, colWidths=col_widths)
        pad = 3
        ts = [('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e5e7eb')), ('BOTTOMPADDING', (0, 0), (-1, 0), 5), ('TOPPADDING', (0, 0), (-1, 0), 5), ('LEFTPADDING', (0, 0), (-1, -1), pad), ('RIGHTPADDING', (0, 0), (-1, -1), pad), ('TOPPADDING', (0, 1), (-1, -1), 3), ('BOTTOMPADDING', (0, 1), (-1, -1), 3), ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#9ca3af')), ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'), ('VALIGN', (0, 1), (-1, -1), 'TOP'), ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#fafafa')])]
        last_i = len(data) - 1
        if not rows:
            ts.append(('SPAN', (0, 1), (15, 1)))
            ts.append(('ALIGN', (0, 1), (15, 1), 'CENTER'))
            ts.append(('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#f3f4f6')))
            if include_totals_row and last_i >= 2:
                ts.append(('BACKGROUND', (0, last_i), (-1, last_i), colors.HexColor('#fef9c3')))
                ts.append(('LINEABOVE', (0, last_i), (-1, last_i), 0.75, colors.HexColor('#64748b')))
        elif include_totals_row and last_i >= 1:
            ts.append(('BACKGROUND', (0, last_i), (-1, last_i), colors.HexColor('#fef9c3')))
            ts.append(('LINEABOVE', (0, last_i), (-1, last_i), 0.75, colors.HexColor('#64748b')))
        tbl.setStyle(TableStyle(ts))
        story.append(tbl)
        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()
    except Exception:
        logger.exception('Stock report PDF generation failed')
        return None

def _build_stock_report_summary_pdf(rows: List[Dict[str, Any]], filters: Dict[str, Any], *, summary_dimension_label: str) -> Optional[bytes]:
    """Portrait A4 PDF for the grouped summary grid (same query as Export Micro CSV)."""
    if not REPORTLAB_AVAILABLE:
        return None
    try:
        buffer = io.BytesIO()
        page_sz = A4
        doc = SimpleDocTemplate(buffer, pagesize=page_sz, canvasmaker=_StockReportNumberedCanvas, topMargin=0.42 * inch, bottomMargin=0.52 * inch, leftMargin=0.35 * inch, rightMargin=0.35 * inch)
        pw = float(page_sz[0])
        usable_w = pw - float(doc.leftMargin) - float(doc.rightMargin)
        styles = getSampleStyleSheet()
        loc_hdr_name = ParagraphStyle('sr_sum_pdf_loc_name', parent=styles['Normal'], fontSize=11, leading=13, alignment=TA_CENTER, spaceAfter=2, textColor=colors.HexColor('#0f172a'))
        loc_hdr_line = ParagraphStyle('sr_sum_pdf_loc_line', parent=styles['Normal'], fontSize=8, leading=10, alignment=TA_CENTER, textColor=colors.HexColor('#374151'))
        title_st = ParagraphStyle('sr_sum_pdf_title', parent=styles['Heading1'], fontSize=13, alignment=TA_CENTER, spaceAfter=6, textColor=colors.HexColor('#0f172a'))
        subtitle_st = ParagraphStyle('sr_sum_pdf_subtitle', parent=styles['Normal'], fontSize=9, leading=11, alignment=TA_CENTER, spaceAfter=4, textColor=colors.HexColor('#475569'))
        meta_st = ParagraphStyle('sr_sum_pdf_meta', parent=styles['Normal'], fontSize=8, alignment=TA_LEFT, textColor=colors.HexColor('#374151'))
        hdr_center = ParagraphStyle('sr_sum_pdf_th_c', parent=styles['Normal'], fontSize=6, leading=7, alignment=TA_CENTER, textColor=colors.HexColor('#111827'))
        hdr_right = ParagraphStyle('sr_sum_pdf_th_r', parent=styles['Normal'], fontSize=6, leading=7, alignment=TA_RIGHT, textColor=colors.HexColor('#111827'))
        cell_left = ParagraphStyle('sr_sum_pdf_td_l', parent=styles['Normal'], fontSize=6, leading=7, alignment=TA_LEFT, splitLongWords=1)
        cell_right = ParagraphStyle('sr_sum_pdf_td_r', parent=styles['Normal'], fontSize=6, leading=7, alignment=TA_RIGHT, splitLongWords=1)
        story: List[Any] = []
        loc_meta = _get_stock_report_pdf_location_meta(filters)
        letterhead_name = (loc_meta.get('locationname') or '').strip() or str(session.get('location_name') or '').strip()
        if letterhead_name:
            story.append(Paragraph('<b>%s</b>' % _xml_escape(letterhead_name), loc_hdr_name))
        _addr = loc_meta.get('address') or ''
        if _addr:
            story.append(Paragraph(_xml_escape(_addr).replace('\n', '<br/>'), loc_hdr_line))
        _em = loc_meta.get('email') or ''
        if _em:
            story.append(Paragraph(_xml_escape(_em), loc_hdr_line))
        story.append(Spacer(1, 0.08 * inch))
        story.append(Paragraph(_xml_escape('Stock Report — Summary'), title_st))
        story.append(Paragraph(_xml_escape(f'Grouped by {summary_dimension_label}'), subtitle_st))
        parts: List[str] = []
        days_v = (filters.get('days') or '').strip() or '30'
        parts.append(f'Days: {_xml_escape(days_v)}')
        loc = (filters.get('locationcode') or '').strip()
        if loc:
            parts.append(f'Location code: {_xml_escape(loc)}')
        for key, lab in (('rawabicode', 'Raw ABI'), ('itemcode', 'Item'), ('itemname', 'Item name'), ('suppliername', 'Supplier'), ('unit', 'Unit'), ('brandname', 'Brand'), ('microcategoryname', 'Micro'), ('categoryname', 'Category'), ('propertyname', 'Property'), ('storecode', 'Store DBCODE'), ('min_stock', 'Min stock'), ('max_stock', 'Max stock'), ('min_avgdaily', 'Min avg daily'), ('max_avgdaily', 'Max avg daily'), ('min_days', 'Min days'), ('max_days', 'Max days')):
            v = (filters.get(key) or '').strip()
            if v:
                parts.append(f'{lab}: {_xml_escape(_trunc_stock_pdf_cell(v, 96))}')
        sp_pdf = (filters.get('stock_polarity') or '').strip().lower()
        if sp_pdf == 'plus':
            parts.append('Stock view: Plus only (qty greater than zero)')
        elif sp_pdf == 'minus':
            parts.append('Stock view: Minus only (qty below zero)')
        user_lbl = str(session.get('user') or '').strip()
        gen_ts = datetime.now().strftime('%Y-%m-%d %H:%M')
        meta_html = ' | '.join(parts) if parts else _xml_escape('(no filters)')
        meta_html += '<br/>'
        meta_html += _xml_escape(f"Generated: {gen_ts} | Rows: {len(rows)} | User: {user_lbl or '—'}")
        story.append(Paragraph(meta_html, meta_st))
        story.append(Spacer(1, 0.12 * inch))
        dim_hdr = _trunc_stock_pdf_cell(summary_dimension_label, 26)
        hdr_labels = [dim_hdr, 'Tot.Qty', 'Stk Val.', 'Avg/D', 'Days']
        hdr_row: List[Any] = []
        for i, h in enumerate(hdr_labels):
            st = hdr_right if i > 0 else hdr_center
            hdr_row.append(Paragraph('<b>%s</b>' % _xml_escape(h), st))
        w_fracs = [0.34, 0.165, 0.185, 0.155, 0.155]
        sfrac = sum(w_fracs)
        col_widths = [usable_w * (f / sfrac) for f in w_fracs]
        data: List[List[Any]] = [hdr_row]

        def _pl(txt: str, mx: int) -> Paragraph:
            return Paragraph(_xml_escape(_trunc_stock_pdf_cell(txt, mx)), cell_left)

        def _pr(txt: str) -> Paragraph:
            return Paragraph(_xml_escape(txt), cell_right)
        if not rows:
            empty_row = [Paragraph('', cell_left) for _ in range(5)]
            empty_row[0] = Paragraph(_xml_escape('No matching summary rows for this selection.'), cell_left)
            data.append(empty_row)
        else:
            for r in rows:
                data.append([_pl(str(r.get('summary_name') or ''), 220), _pr(f"{_to_float(r.get('totalqty')):.3f}"), _pr(f"{_to_float(r.get('stockvalue')):.2f}"), _pr(f"{_to_float(r.get('avgdailyvalue')):.2f}"), _pr(f"{_to_float(r.get('stockremainingdays')):.2f}")])
            sum_tot = sum((_to_float(r.get('totalqty')) for r in rows))
            sum_val = sum((_to_float(r.get('stockvalue')) for r in rows))
            total_row: List[Any] = [Paragraph('<b>%s</b>' % _xml_escape('TOTAL'), cell_left)]
            total_row.append(_pr(f'{sum_tot:.3f}'))
            total_row.append(_pr(f'{sum_val:.2f}'))
            total_row.append(Paragraph('', cell_right))
            total_row.append(Paragraph('', cell_right))
            data.append(total_row)
        tbl = Table(data, repeatRows=1, colWidths=col_widths)
        pad = 4
        ts = [('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e5e7eb')), ('BOTTOMPADDING', (0, 0), (-1, 0), 5), ('TOPPADDING', (0, 0), (-1, 0), 5), ('LEFTPADDING', (0, 0), (-1, -1), pad), ('RIGHTPADDING', (0, 0), (-1, -1), pad), ('TOPPADDING', (0, 1), (-1, -1), 4), ('BOTTOMPADDING', (0, 1), (-1, -1), 4), ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#9ca3af')), ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'), ('VALIGN', (0, 1), (-1, -1), 'TOP'), ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#fafafa')])]
        last_i = len(data) - 1
        if not rows:
            ts.append(('SPAN', (0, 1), (4, 1)))
            ts.append(('ALIGN', (0, 1), (4, 1), 'CENTER'))
            ts.append(('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#f3f4f6')))
        elif last_i >= 1:
            ts.append(('BACKGROUND', (0, last_i), (-1, last_i), colors.HexColor('#fef9c3')))
            ts.append(('LINEABOVE', (0, last_i), (-1, last_i), 0.75, colors.HexColor('#64748b')))
        tbl.setStyle(TableStyle(ts))
        story.append(tbl)
        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()
    except Exception:
        logger.exception('Stock report summary PDF generation failed')
        return None
_STOCK_REPORT_PDF_KIND_SET = frozenset({'total', 'plus_stock', 'minus_stock', 'zero_stock'})

def _parse_stock_report_pdf_kinds(raw_list: List[str]) -> List[str]:
    ordered: List[str] = []
    for x in raw_list:
        k = (x or '').strip().lower().replace('-', '_')
        if k == 'minus':
            k = 'minus_stock'
        if k == 'zero':
            k = 'zero_stock'
        if k == 'plus':
            k = 'plus_stock'
        if k in _STOCK_REPORT_PDF_KIND_SET and k not in ordered:
            ordered.append(k)
    return ordered

def _stock_report_rows_for_pdf_kind(base_rows: List[Dict[str, Any]], kind: str) -> List[Dict[str, Any]]:
    if kind == 'total':
        return list(base_rows)
    if kind == 'plus_stock':
        return [r for r in base_rows if _to_float(r.get('currentstock')) > 0]
    if kind == 'minus_stock':
        return [r for r in base_rows if _to_float(r.get('currentstock')) < 0]
    if kind == 'zero_stock':
        return [r for r in base_rows if abs(_to_float(r.get('currentstock'))) < 1e-09]
    return []

def _stock_report_pdf_kind_options(kind: str) -> Tuple[str, bool]:
    """Returns (subtitle, include_totals_row). All variants include a totals row when there are rows."""
    if kind == 'total':
        return ('Full list — totals row below the grid.', True)
    if kind == 'plus_stock':
        return ('Plus stock only (quantity greater than zero).', True)
    if kind == 'minus_stock':
        return ('Minus stock only (quantity below zero).', True)
    if kind == 'zero_stock':
        return ('Zero stock only (quantity equals zero).', True)
    return ('', True)

def _get_stock_report_filter_options(locationcode: Optional[str]=None) -> Dict[str, Any]:
    imd_from, _imd_cols = _stock_report_item_details_source()
    where_parts = ["I.tables = 'MASTER'"]
    params: Dict[str, Any] = {}
    locationcode = (locationcode or '').strip()
    if locationcode:
        where_parts.append('TO_CHAR(I.locationcode) = :locationcode')
        params['locationcode'] = locationcode
    q = f"\n        SELECT\n            NVL(I.itemname, '') AS itemname,\n            NVL(I.suppliername, '') AS suppliername,\n            NVL(I.unit, '') AS unit,\n            NVL(I.brandname, '') AS brandname,\n            NVL(I.microcategoryname, '') AS microcategoryname,\n            NVL(I.categoryname, '') AS categoryname,\n            NVL(I.propertyname, '') AS propertyname\n        FROM {imd_from} I\n        WHERE {' AND '.join(where_parts)}\n    "
    rows = _safe_rows(q, params) or []

    def _uniq(key: str) -> List[str]:
        vals = sorted({str(r.get(key) or '').strip() for r in rows if str(r.get(key) or '').strip()})
        return vals
    where_loc = ["I.tables = 'MASTER'", 'I.locationcode IS NOT NULL']
    params_loc: Dict[str, Any] = {}
    if locationcode:
        where_loc.append('TO_CHAR(I.locationcode) = :locationcode')
        params_loc['locationcode'] = locationcode
    q_loc = f"\n        SELECT DISTINCT TO_CHAR(I.locationcode) AS locationcode\n        FROM {imd_from} I\n        WHERE {' AND '.join(where_loc)}\n    "
    loc_rows = _safe_rows(q_loc, params_loc) or []
    locationcodes = sorted({str(r.get('locationcode') or '').strip() for r in loc_rows if str(r.get('locationcode') or '').strip()})
    stores_pick = _stock_report_tbllocation_store_pick_rows(locationcode)
    return {'locationcodes': locationcodes, 'stores': stores_pick, 'itemnames': _uniq('itemname'), 'suppliernames': _uniq('suppliername'), 'units': _uniq('unit'), 'brandnames': _uniq('brandname'), 'microcategories': _uniq('microcategoryname'), 'categories': _uniq('categoryname'), 'properties': _uniq('propertyname')}
_STOCK_REPORT_SUMMARY_BY_KEYS = frozenset({'microcategory', 'brand', 'category', 'supplier', 'unit', 'property'})

def _normalize_stock_report_summary_by(raw: Optional[str]) -> str:
    k = (raw or '').strip().lower().replace('-', '_')
    if k in ('micro', 'micro_cat', 'micro_category'):
        k = 'microcategory'
    return k if k in _STOCK_REPORT_SUMMARY_BY_KEYS else 'microcategory'

def _stock_report_summary_dimension_label(summary_by: str) -> str:
    sb = _normalize_stock_report_summary_by(summary_by)
    return {'microcategory': 'Micro Category', 'brand': 'Brand', 'category': 'Category', 'supplier': 'Supplier', 'unit': 'Unit', 'property': 'Property'}.get(sb, 'Micro Category')

def _get_stock_report_micro_summary(filters: Dict[str, Any], *, item_rows: Optional[List[Dict[str, Any]]]=None) -> List[Dict[str, Any]]:
    """Grouped metrics over the same rows as the item grid (stock value sums match the grid)."""
    rows = item_rows if item_rows is not None else _get_stock_report_rows(filters)
    if not rows:
        return []
    days = (filters.get('days') or '30').strip()
    try:
        days_int = max(1, min(int(days), 3650))
    except Exception:
        days_int = 30
    days_f = float(days_int)
    summary_by = _normalize_stock_report_summary_by(filters.get('summary_by'))
    key_field = {'microcategory': 'microcategoryname', 'brand': 'brandname', 'category': 'categoryname', 'supplier': 'suppliername', 'unit': 'unit', 'property': 'propertyname'}.get(summary_by, 'microcategoryname')
    buckets: Dict[str, Dict[str, float]] = {}
    for r in rows:
        raw_dim = r.get(key_field)
        dim_key = str(raw_dim if raw_dim is not None else '').strip()
        if dim_key not in buckets:
            buckets[dim_key] = {'stockvalue': 0.0, 'totalqty': 0.0, 'movement_cost': 0.0}
        b = buckets[dim_key]
        tq = _to_float(r.get('totalqty'))
        cp = _to_float(r.get('costprice'))
        b['stockvalue'] += _to_float(r.get('stockvalue'))
        b['totalqty'] += tq
        b['movement_cost'] += tq * cp
    out: List[Dict[str, Any]] = []
    for dim_key in sorted(buckets.keys()):
        b = buckets[dim_key]
        mov = b['movement_cost']
        avgdailyvalue = round(mov / days_f, 2) if days_int else 0.0
        if abs(mov) < 1e-12:
            stockremainingdays = 0.0
        else:
            daily_mov = mov / days_f
            stockremainingdays = round(b['stockvalue'] / daily_mov, 2)
        out.append({'summary_name': dim_key, 'stockvalue': round(b['stockvalue'], 2), 'totalqty': round(b['totalqty'], 3), 'avgdailyvalue': avgdailyvalue, 'stockremainingdays': stockremainingdays})
    return out

@bp.route('/reports/stock-report', methods=['GET'])
def stock_report():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    filters = _stock_report_filters_from_request(request.args, include_summary_by=True)
    report_error = ''
    try:
        rows = _get_stock_report_rows(filters)
        micro_summary_rows = _get_stock_report_micro_summary(filters, item_rows=rows)
        options = _get_stock_report_filter_options(filters.get('locationcode'))
    except Exception as e:
        logger.exception('Stock report failed: %s', e)
        rows = []
        micro_summary_rows = []
        options = {'locationcodes': [], 'stores': [], 'itemnames': [], 'suppliernames': [], 'units': [], 'brandnames': [], 'microcategories': [], 'categories': [], 'properties': []}
        report_error = 'Stock report could not load data. Check database tables (ITEMMASTERDETAILS, ITEMMASTER, BILL history) or contact support.'
    _sum_label = _stock_report_summary_dimension_label(filters['summary_by'])
    return render_template('reports/stock_report.html', rows=rows, micro_summary_rows=micro_summary_rows, filters=filters, options=options, summary_dimension_label=_sum_label, cost_column_label=_stock_report_cost_column_label(filters), export_url=url_for('reports.stock_report_export', **filters), stock_report_pdf_url=url_for('reports.stock_report_pdf'), micro_export_url=url_for('reports.stock_report_micro_export', **filters), summary_pdf_url=url_for('reports.stock_report_summary_pdf', **filters), report_error=report_error)

@bp.route('/reports/stock-report/export', methods=['GET'])
def stock_report_export():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    filters = _stock_report_filters_from_request(request.args)
    rows = _get_stock_report_rows(filters)
    output = io.StringIO()
    writer = csv.writer(output)
    qty_csv_hdr = _stock_report_qty_column_label(filters)
    cost_csv_hdr = _stock_report_cost_column_label(filters)
    writer.writerow(['Location', 'Barcode', 'Item Code', 'Item Name', 'Supplier Name', 'Unit', cost_csv_hdr, 'Brand', 'Micro Category', 'Category', 'Property', qty_csv_hdr, 'Stock Value', 'Total Qty', 'Avg Daily', 'Stock Remaining Days'])
    for r in rows:
        writer.writerow([r.get('locationcode', ''), r.get('barcode', ''), r.get('itemcode', ''), r.get('itemname', ''), r.get('suppliername', ''), r.get('unit', ''), f"{_to_float(r.get('costprice')):.3f}", r.get('brandname', ''), r.get('microcategoryname', ''), r.get('categoryname', ''), r.get('propertyname', ''), f"{_to_float(r.get('currentstock')):.3f}", f"{_to_float(r.get('stockvalue')):.2f}", f"{_to_float(r.get('totalqty')):.3f}", f"{_to_float(r.get('avgdaily')):.2f}", f"{_to_float(r.get('stockremainingdays')):.2f}"])
    output.seek(0)
    return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition': 'attachment; filename=stock_report.csv'})

@bp.route('/reports/stock-report/pdf', methods=['GET'])
def stock_report_pdf():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    if not REPORTLAB_AVAILABLE:
        return Response('PDF is not available (install reportlab).', status=500, mimetype='text/plain')
    filters = _stock_report_filters_from_request(request.args)
    kinds = _parse_stock_report_pdf_kinds(request.args.getlist('pdf_kind'))
    if not kinds:
        kinds = ['total']
    base_rows = _get_stock_report_rows(filters)
    fnames = {'total': 'stock_report_total', 'plus_stock': 'stock_report_plus_stock', 'minus_stock': 'stock_report_minus_stock', 'zero_stock': 'stock_report_zero_stock'}

    def _bytes_for_kind(kind: str) -> Optional[bytes]:
        subtitle, inc_tot = _stock_report_pdf_kind_options(kind)
        rows_k = _stock_report_rows_for_pdf_kind(base_rows, kind)
        return _build_stock_report_pdf(rows_k, filters, pdf_subtitle=subtitle, include_totals_row=inc_tot)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    if len(kinds) == 1:
        k0 = kinds[0]
        pdf_bytes = _bytes_for_kind(k0)
        if not pdf_bytes:
            return Response('Failed to generate PDF.', status=500, mimetype='text/plain')
        filename = f"{fnames.get(k0, 'stock_report')}_{ts}.pdf"
        return Response(pdf_bytes, mimetype='application/pdf', headers={'Content-Disposition': f'inline; filename="{filename}"'})
    zip_buf = io.BytesIO()
    try:
        with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for kind in kinds:
                pdf_bytes = _bytes_for_kind(kind)
                if not pdf_bytes:
                    return Response(f'Failed to generate PDF ({kind}).', status=500, mimetype='text/plain')
                base_fn = fnames.get(kind, f'stock_report_{kind}')
                zf.writestr(f'{base_fn}_{ts}.pdf', pdf_bytes)
    except Exception:
        logger.exception('Stock report PDF ZIP failed')
        return Response('Failed to build ZIP.', status=500, mimetype='text/plain')
    zip_buf.seek(0)
    return Response(zip_buf.getvalue(), mimetype='application/zip', headers={'Content-Disposition': f'attachment; filename="stock_reports_{ts}.zip"'})

@bp.route('/reports/stock-report/micro-export', methods=['GET'])
def stock_report_micro_export():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    filters = _stock_report_filters_from_request(request.args, include_summary_by=True)
    rows = _get_stock_report_micro_summary(filters)
    output = io.StringIO()
    writer = csv.writer(output)
    grp_hdr = _stock_report_summary_dimension_label(filters['summary_by'])
    writer.writerow([grp_hdr, 'Total Qty', 'Stock Value', 'Avg Daily Value', 'Stock Remaining Days'])
    for r in rows:
        writer.writerow([r.get('summary_name', ''), f"{_to_float(r.get('totalqty')):.3f}", f"{_to_float(r.get('stockvalue')):.2f}", f"{_to_float(r.get('avgdailyvalue')):.2f}", f"{_to_float(r.get('stockremainingdays')):.2f}"])
    output.seek(0)
    return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition': 'attachment; filename=stock_report_microcategory_summary.csv'})

@bp.route('/reports/stock-report/summary-pdf', methods=['GET'])
def stock_report_summary_pdf():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    if not REPORTLAB_AVAILABLE:
        return Response('PDF is not available (install reportlab).', status=500, mimetype='text/plain')
    filters = _stock_report_filters_from_request(request.args, include_summary_by=True)
    summary_rows = _get_stock_report_micro_summary(filters)
    dim_label = _stock_report_summary_dimension_label(filters['summary_by'])
    pdf_bytes = _build_stock_report_summary_pdf(summary_rows, filters, summary_dimension_label=dim_label)
    if not pdf_bytes:
        return Response('Failed to generate summary PDF.', status=500, mimetype='text/plain')
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'stock_report_summary_{ts}.pdf'
    return Response(pdf_bytes, mimetype='application/pdf', headers={'Content-Disposition': f'inline; filename="{filename}"'})

@bp.route('/reports/route-outstanding/export', methods=['GET'])
def route_outstanding_export():
    """Export route outstanding summary to Excel (CSV format)."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    rows = get_route_outstanding_aging()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Route Code', 'Route Name', '0-30', '31-60', '61-90', '91-120', '120+', 'Total'])
    for row in rows:
        total = (row.get('d30') or 0) + (row.get('d60') or 0) + (row.get('d90') or 0) + (row.get('d120') or 0) + (row.get('d120p') or 0)
        writer.writerow([row.get('routecode', ''), row.get('routename', ''), f"{row.get('d30') or 0:.2f}", f"{row.get('d60') or 0:.2f}", f"{row.get('d90') or 0:.2f}", f"{row.get('d120') or 0:.2f}", f"{row.get('d120p') or 0:.2f}", f'{total:.2f}'])
    total_d30 = sum((row.get('d30') or 0 for row in rows))
    total_d60 = sum((row.get('d60') or 0 for row in rows))
    total_d90 = sum((row.get('d90') or 0 for row in rows))
    total_d120 = sum((row.get('d120') or 0 for row in rows))
    total_d120p = sum((row.get('d120p') or 0 for row in rows))
    grand_total = total_d30 + total_d60 + total_d90 + total_d120 + total_d120p
    writer.writerow(['Total', '', f'{total_d30:.2f}', f'{total_d60:.2f}', f'{total_d90:.2f}', f'{total_d120:.2f}', f'{total_d120p:.2f}', f'{grand_total:.2f}'])
    output.seek(0)
    return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition': 'attachment; filename=route_outstanding_summary.csv'})

@bp.route('/reports/route-outstanding/details/export', methods=['GET'])
def route_outstanding_details_export():
    """Export route outstanding details to Excel (CSV format)."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    bucket = (request.args.get('bucket') or 'all').strip()
    routecode = (request.args.get('routecode') or '').strip() or None
    rows = get_route_outstanding_details(routecode, bucket)
    bucket_labels = {'all': 'All_Periods', '30': '0-30', '60': '31-60', '90': '61-90', '120': '91-120', '120p': '120+'}
    bucket_label = bucket_labels.get(bucket, bucket)
    filename = f'route_outstanding_details_{bucket_label}'
    if routecode:
        filename += f'_{routecode}'
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['SL No', 'Bill No', 'Bill Date', 'Customer Code', 'Customer Name', 'Route Code', 'Route Name', 'Salesman Code', 'Salesman Name', 'Employee Code', 'Employee Name', 'Expected Date', 'Remarks', 'Bill Amount', 'Paid Amount', 'Outstanding'])
    for row in rows:
        billdate_str = row['billdate'].strftime('%d-%m-%Y') if row.get('billdate') and hasattr(row['billdate'], 'strftime') else str(row.get('billdate', ''))[:10]
        expecteddate_str = row['expecteddate'].strftime('%d-%m-%Y') if row.get('expecteddate') and hasattr(row.get('expecteddate'), 'strftime') else str(row.get('expecteddate', ''))[:10] if row.get('expecteddate') else ''
        writer.writerow([row.get('slno', ''), row.get('billno', ''), billdate_str, row.get('customercode', ''), row.get('customername', ''), row.get('routecode', ''), row.get('routename', ''), row.get('salesmancode', ''), row.get('salesmanname', ''), row.get('employeecode', ''), row.get('employeename', ''), expecteddate_str, row.get('remarks', ''), f"{row.get('billamount') or 0:.2f}", f"{row.get('paidamount') or 0:.2f}", f"{row.get('outstanding') or 0:.2f}"])
    total_bill = sum((row.get('billamount') or 0 for row in rows))
    total_paid = sum((row.get('paidamount') or 0 for row in rows))
    total_outstanding = sum((row.get('outstanding') or 0 for row in rows))
    writer.writerow(['Total', '', '', '', '', '', '', '', '', '', '', '', '', f'{total_bill:.2f}', f'{total_paid:.2f}', f'{total_outstanding:.2f}'])
    output.seek(0)
    return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename={filename}.csv'})

@bp.route('/reports/customer-outstanding-cr', methods=['GET'])
def customer_outstanding_cr():
    """Customer Outstanding Credit from GL / accounts (open receivable vouchers)."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    branchflag = (request.args.get('branchflag') or '').strip() or None
    transferbranch = (request.args.get('transferbranch') or '').strip() or None
    credit_rows = get_customer_outstanding_aging_credit(branchflag=branchflag, transferbranch=transferbranch)
    filter_options = get_customer_branch_filter_options()
    return render_template('reports/customer_outstanding_cr.html', credit_rows=credit_rows, filter_options=filter_options, sel_branchflag=branchflag or '', sel_transferbranch=transferbranch or '')

@bp.route('/reports/customer-outstanding-cr/month', methods=['GET'])
def customer_outstanding_cr_month():
    """Credit outstanding by voucher-date calendar month (GL / accounts); branch filters like CR aging."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    branchflag = (request.args.get('branchflag') or '').strip() or None
    transferbranch = (request.args.get('transferbranch') or '').strip() or None
    rows = get_customer_outstanding_aging_credit_three_month(branchflag=branchflag, transferbranch=transferbranch)
    filter_options = get_customer_branch_filter_options()
    month_specs = get_customer_outstanding_cash_three_month_specs()
    footer_by_attr = {attr: sum((float(r.get(attr) or 0) for r in rows or [])) for attr, _, _ in month_specs}
    footer_grand = sum(footer_by_attr.values())
    return render_template('reports/customer_outstanding_cr_month.html', rows=rows, filter_options=filter_options, sel_branchflag=branchflag or '', sel_transferbranch=transferbranch or '', month_specs=month_specs, footer_by_attr=footer_by_attr, footer_grand=footer_grand)

@bp.route('/reports/customer-outstanding-cr/month/export', methods=['GET'])
def customer_outstanding_cr_month_export():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    branchflag = (request.args.get('branchflag') or '').strip() or None
    transferbranch = (request.args.get('transferbranch') or '').strip() or None
    rows = get_customer_outstanding_aging_credit_three_month(branchflag=branchflag, transferbranch=transferbranch)
    specs = get_customer_outstanding_cash_three_month_specs()
    output = io.StringIO()
    writer = csv.writer(output)
    header = ['Customer Code', 'Customer Name'] + [lab for _, lab, _ in specs] + ['Total']
    writer.writerow(header)
    for row in rows:
        total = sum((float(row.get(attr) or 0) for attr, _, _ in specs))
        writer.writerow([row.get('customercode', ''), row.get('customername', '')] + [f'{float(row.get(attr) or 0):.2f}' for attr, _, _ in specs] + [f'{total:.2f}'])
    sums = [sum((float(r.get(attr) or 0) for r in rows)) for attr, _, _ in specs]
    grand = sum(sums)
    writer.writerow(['Total', ''] + [f'{s:.2f}' for s in sums] + [f'{grand:.2f}'])
    output.seek(0)
    sfx = []
    if branchflag:
        sfx.append(f'bf_{branchflag}')
    if transferbranch:
        sfx.append(f'tb_{transferbranch}')
    suffix = '_' + '_'.join(sfx) if sfx else ''
    return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename=customer_outstanding_credit_by_month{suffix}.csv'})

@bp.route('/reports/customer-outstanding-cr/export/summary', methods=['GET'])
def customer_outstanding_cr_export_summary():
    """Export customer outstanding credit summary list to Excel (CSV format)."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    branchflag = (request.args.get('branchflag') or '').strip() or None
    transferbranch = (request.args.get('transferbranch') or '').strip() or None
    rows = get_customer_outstanding_aging_credit(branchflag=branchflag, transferbranch=transferbranch)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Sl.No', 'Customer Code', 'Customer Name', '0-30', '31-60', '61-90', '91-120', '120+', 'Total'])
    td30 = td60 = td90 = td120 = td120p = 0.0
    for idx, row in enumerate(rows or [], start=1):
        d30 = float(row.get('d30') or 0)
        d60 = float(row.get('d60') or 0)
        d90 = float(row.get('d90') or 0)
        d120 = float(row.get('d120') or 0)
        d120p = float(row.get('d120p') or 0)
        total = d30 + d60 + d90 + d120 + d120p
        td30 += d30
        td60 += d60
        td90 += d90
        td120 += d120
        td120p += d120p
        writer.writerow([idx, row.get('customercode', ''), row.get('customername', ''), f'{d30:.2f}', f'{d60:.2f}', f'{d90:.2f}', f'{d120:.2f}', f'{d120p:.2f}', f'{total:.2f}'])
    grand_total = td30 + td60 + td90 + td120 + td120p
    writer.writerow(['Total', '', '', f'{td30:.2f}', f'{td60:.2f}', f'{td90:.2f}', f'{td120:.2f}', f'{td120p:.2f}', f'{grand_total:.2f}'])
    output.seek(0)
    fname = 'customer_outstanding_credit_summary.csv'
    return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename={fname}'})
_BUCKET_LABELS = {'all': 'All Periods', '30': '0-30', '60': '31-60', '90': '61-90', '120': '91-120', '120p': '120+'}

def _cr_credit_export_bucket_slug(bucket: str) -> str:
    """Filename-safe label including calendar-month buckets for credit exports."""
    base = _BUCKET_LABELS.get(bucket)
    if base:
        return base.replace(' ', '_')
    for _attr, lab, bkt in get_customer_outstanding_cash_three_month_specs():
        if bkt == bucket:
            return lab.replace(' ', '_')
    return str(bucket or 'bucket').replace(' ', '_')

@bp.route('/reports/customer-outstanding-cr/details/cash', methods=['GET'])
def customer_outstanding_cr_details_cash():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    bucket = (request.args.get('bucket') or 'all').strip()
    customer_code = (request.args.get('customer_code') or '').strip() or None
    branchflag = (request.args.get('branchflag') or '').strip() or None
    transferbranch = (request.args.get('transferbranch') or '').strip() or None
    rows = get_customer_outstanding_details_cash(customer_code, bucket, branchflag=branchflag, transferbranch=transferbranch)
    return render_template('reports/outstanding_details.html', report_type='customer', bucket=bucket, bucket_label=_BUCKET_LABELS.get(bucket, bucket), entity_type_label='Customer', entity_label=customer_code or '', back_url=url_for('reports.customer_outstanding_cr'), export_url=url_for('reports.customer_outstanding_cr_export_cash', bucket=bucket, customer_code=customer_code or '', branchflag=branchflag or '', transferbranch=transferbranch or ''), rows=rows, empty_help='')

@bp.route('/reports/customer-outstanding-cr/details/credit', methods=['GET'])
def customer_outstanding_cr_details_credit():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    bucket = (request.args.get('bucket') or 'all').strip()
    customer_code = (request.args.get('customer_code') or '').strip() or None
    branchflag = (request.args.get('branchflag') or '').strip() or None
    transferbranch = (request.args.get('transferbranch') or '').strip() or None
    rows = get_customer_outstanding_details_credit(customer_code, bucket, branchflag=branchflag, transferbranch=transferbranch)
    bucket_label = _BUCKET_LABELS.get(bucket, bucket)
    for _attr, lab, bkt in get_customer_outstanding_cash_three_month_specs():
        if bkt == bucket:
            bucket_label = lab
            break
    src = (request.args.get('src') or '').strip()
    back_kw: Dict[str, Any] = {}
    if branchflag:
        back_kw['branchflag'] = branchflag
    if transferbranch:
        back_kw['transferbranch'] = transferbranch
    back_url = url_for('reports.customer_outstanding_cr_month', **back_kw) if src == 'month' else url_for('reports.customer_outstanding_cr')
    return render_template('reports/outstanding_details.html', report_type='customer', bucket=bucket, bucket_label=bucket_label, entity_type_label='Customer', entity_label=customer_code or '', back_url=back_url, export_url=url_for('reports.customer_outstanding_cr_export_credit', bucket=bucket, customer_code=customer_code or '', branchflag=branchflag or '', transferbranch=transferbranch or ''), rows=rows, empty_help='')

def _write_outstanding_csv(rows: list, writer: Any) -> None:
    writer.writerow(['SL No', 'Bill No', 'Bill Date', 'Customer Code', 'Customer Name', 'Salesman Code', 'Salesman Name', 'Bill Amount', 'Paid Amount', 'Outstanding'])
    for row in rows:
        bd = row['billdate'].strftime('%d-%m-%Y') if row.get('billdate') and hasattr(row['billdate'], 'strftime') else str(row.get('billdate', ''))[:10]
        writer.writerow([row.get('slno', ''), row.get('billno', ''), bd, row.get('customercode', ''), row.get('customername', ''), row.get('salesmancode', ''), row.get('salesmanname', ''), f"{row.get('billamount') or 0:.2f}", f"{row.get('paidamount') or 0:.2f}", f"{row.get('outstanding') or 0:.2f}"])
    writer.writerow(['Total', '', '', '', '', '', '', f"{sum((r.get('billamount') or 0 for r in rows)):.2f}", f"{sum((r.get('paidamount') or 0 for r in rows)):.2f}", f"{sum((r.get('outstanding') or 0 for r in rows)):.2f}"])

@bp.route('/reports/customer-outstanding-cr/export/cash', methods=['GET'])
def customer_outstanding_cr_export_cash():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    bucket = (request.args.get('bucket') or 'all').strip()
    customer_code = (request.args.get('customer_code') or '').strip() or None
    branchflag = (request.args.get('branchflag') or '').strip() or None
    transferbranch = (request.args.get('transferbranch') or '').strip() or None
    rows = get_customer_outstanding_details_cash(customer_code, bucket, branchflag=branchflag, transferbranch=transferbranch)
    output = io.StringIO()
    _write_outstanding_csv(rows, csv.writer(output))
    output.seek(0)
    fname = f'customer_outstanding_cash_{_BUCKET_LABELS.get(bucket, bucket)}.csv'
    return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename={fname}'})

@bp.route('/reports/customer-outstanding-cr/export/credit', methods=['GET'])
def customer_outstanding_cr_export_credit():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    bucket = (request.args.get('bucket') or 'all').strip()
    customer_code = (request.args.get('customer_code') or '').strip() or None
    branchflag = (request.args.get('branchflag') or '').strip() or None
    transferbranch = (request.args.get('transferbranch') or '').strip() or None
    rows = get_customer_outstanding_details_credit(customer_code, bucket, branchflag=branchflag, transferbranch=transferbranch)
    output = io.StringIO()
    _write_outstanding_csv(rows, csv.writer(output))
    output.seek(0)
    fname = f'customer_outstanding_credit_{_cr_credit_export_bucket_slug(bucket)}.csv'
    return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename={fname}'})

from addons.reports.stock_aging_logic import (
    DEFAULT_BUCKETS,
    build_stock_aging_payload,
    get_stock_aging_drilldown,
    get_stock_aging_filter_options,
    parse_aging_buckets,
    resolve_branch_from_session,
)


def _stock_aging_filters_from_request(args) -> Dict[str, Any]:
    loc = resolve_branch_from_session(session, args)
    return {
        'company': (args.get('company') or session.get('tenant_id') or 'HO').strip(),
        'locationcode': loc,
        'branch': str(loc),
        'warehouse_id': (args.get('warehouse_id') or '').strip(),
        'category_code': (args.get('category_code') or '').strip(),
        'brand_code': (args.get('brand_code') or '').strip(),
        'supplier_code': (args.get('supplier_code') or '').strip(),
        'item_code': (args.get('item_code') or '').strip(),
        'item_name': (args.get('item_name') or '').strip(),
        'search': (args.get('search') or '').strip(),
        'as_on_date': (args.get('as_on_date') or datetime.now().strftime('%Y-%m-%d')).strip(),
        'aging_method': (args.get('aging_method') or 'last_movement').strip(),
        'cost_method': (args.get('cost_method') or 'average').strip(),
        'include_zero': (args.get('include_zero') or '').strip(),
        'buckets_json': (args.get('buckets_json') or '').strip(),
        'max_rows': (args.get('max_rows') or '8000').strip(),
    }


@bp.route('/reports/stock-aging', methods=['GET'])
def stock_aging_report():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    filters = _stock_aging_filters_from_request(request.args)
    options = get_stock_aging_filter_options(filters['locationcode'])
    return render_template(
        'reports/stock_aging.html',
        filters=filters,
        options=options,
        default_buckets=DEFAULT_BUCKETS,
        api_data_url=url_for('reports.stock_aging_api_data'),
        api_drilldown_url=url_for('reports.stock_aging_api_drilldown'),
        export_excel_url=url_for('reports.stock_aging_export_excel'),
        export_pdf_url=url_for('reports.stock_aging_export_pdf'),
    )


@bp.route('/reports/stock-aging/api/data', methods=['GET'])
def stock_aging_api_data():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    filters = _stock_aging_filters_from_request(request.args)
    payload = build_stock_aging_payload(filters)
    return jsonify(payload)


@bp.route('/reports/stock-aging/api/drilldown', methods=['GET'])
def stock_aging_api_drilldown():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    item_code = (request.args.get('itemcode') or request.args.get('item_code') or '').strip()
    if not item_code:
        return jsonify({'success': False, 'error': 'itemcode required'}), 400
    loc = resolve_branch_from_session(session, request.args)
    data = get_stock_aging_drilldown(item_code, loc)
    return jsonify({'success': True, 'itemcode': item_code, 'data': data})


@bp.route('/reports/stock-aging/export-excel', methods=['GET'])
def stock_aging_export_excel():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    filters = _stock_aging_filters_from_request(request.args)
    payload = build_stock_aging_payload(filters)
    rows = payload.get('rows') or []
    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output)
    writer.writerow([
        'Item Code', 'Barcode', 'Item Name', 'Category', 'Brand', 'Supplier', 'UOM',
        'Current Stock', 'Average Cost', 'Stock Value', 'Last Purchase', 'Last Receipt',
        'Last Sales', 'Last Movement', 'Age Days', 'Aging Bucket', 'Status',
    ])
    for r in rows:
        writer.writerow([
            r.get('itemcode'), r.get('barcode'), r.get('itemname'), r.get('category'),
            r.get('brand'), r.get('supplier'), r.get('uom'), r.get('currentstock'),
            r.get('averagecost'), r.get('stockvalue'), r.get('last_purchase_date'),
            r.get('last_receipt_date'), r.get('last_sales_date'), r.get('last_movement_date'),
            r.get('age_days'), r.get('aging_bucket'), r.get('status'),
        ])
    output.seek(0)
    fname = f"stock_aging_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(output.getvalue(), mimetype='text/csv; charset=utf-8', headers={'Content-Disposition': f'attachment; filename={fname}'})


@bp.route('/reports/stock-aging/export-pdf', methods=['GET'])
def stock_aging_export_pdf():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not REPORTLAB_AVAILABLE:
        flash('PDF export requires ReportLab.', 'warning')
        return redirect(url_for('reports.stock_aging_report', **request.args))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    filters = _stock_aging_filters_from_request(request.args)
    payload = build_stock_aging_payload(filters)
    rows = (payload.get('rows') or [])[:500]
    summary = payload.get('summary') or {}
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=24, rightMargin=24, topMargin=24, bottomMargin=24)
    styles = getSampleStyleSheet()
    story = [
        Paragraph('Stock Aging Analysis', styles['Title']),
        Spacer(1, 8),
        Paragraph(
            f"As on {filters.get('as_on_date')} | Rows {summary.get('row_count', 0)} | "
            f"Total value {summary.get('total_inventory_value', 0):,.2f}",
            styles['Normal'],
        ),
        Spacer(1, 12),
    ]
    table_data = [['Code', 'Name', 'Stock', 'Value', 'Age', 'Bucket', 'Status']]
    for r in rows:
        table_data.append([
            str(r.get('itemcode') or ''),
            str(r.get('itemname') or '')[:28],
            str(r.get('currentstock') or ''),
            str(r.get('stockvalue') or ''),
            str(r.get('age_days') or ''),
            str(r.get('aging_bucket') or '')[:14],
            str(r.get('status') or ''),
        ])
    tbl = Table(table_data, repeatRows=1)
    tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
    ]))
    story.append(tbl)
    doc.build(story)
    buf.seek(0)
    fname = f"stock_aging_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return send_file(buf, mimetype='application/pdf', as_attachment=True, download_name=fname)


from addons.reports.integrity_dashboard_logic import (
    build_integrity_dashboard,
    get_integrity_filter_options,
    get_item_movement_drilldown,
    get_journal_drilldown,
    get_stock_gl_variance_drilldown,
    get_stock_item_drilldown,
    resolve_branch_from_session as _integrity_resolve_branch,
)


def _integrity_filters_from_request(args) -> Dict[str, Any]:
    loc = _integrity_resolve_branch(session, args)
    return {
        'company': (args.get('company') or session.get('tenant_id') or 'HO').strip(),
        'locationcode': loc,
        'branch': str(loc),
        'warehouse_id': (args.get('warehouse_id') or '').strip(),
        'financial_year': (args.get('financial_year') or str(datetime.now().year)).strip(),
        'date_from': (args.get('date_from') or '').strip(),
        'date_to': (args.get('date_to') or '').strip(),
        'module': (args.get('module') or 'ALL').strip(),
        'account_code': (args.get('account_code') or '').strip(),
        'item_code': (args.get('item_code') or '').strip(),
        'customer_code': (args.get('customer_code') or '').strip(),
        'supplier_code': (args.get('supplier_code') or '').strip(),
    }


@bp.route('/reports/integrity-dashboard', methods=['GET'])
def integrity_dashboard_page():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    filters = _integrity_filters_from_request(request.args)
    if not filters.get('date_from'):
        filters['date_from'] = f"{datetime.now().year}-01-01"
    if not filters.get('date_to'):
        filters['date_to'] = datetime.now().strftime('%Y-%m-%d')
    options = get_integrity_filter_options(filters['locationcode'])
    return render_template(
        'reports/integrity_dashboard.html',
        title='Accounting & Inventory Integrity Dashboard',
        filters=filters,
        options=options,
        api_data_url=url_for('reports.integrity_dashboard_api_data'),
        api_journal_url=url_for('reports.integrity_dashboard_api_journal'),
        api_item_movement_url=url_for('reports.integrity_dashboard_api_item_movement'),
        api_stock_item_url=url_for('reports.integrity_dashboard_api_stock_item'),
        api_stock_gl_drill_url=url_for('reports.integrity_dashboard_api_stock_gl_drill'),
        export_excel_url=url_for('reports.integrity_dashboard_export_excel'),
        export_pdf_url=url_for('reports.integrity_dashboard_export_pdf'),
    )


@bp.route('/reports/integrity-dashboard/api/data', methods=['GET'])
def integrity_dashboard_api_data():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    try:
        payload = build_integrity_dashboard(_integrity_filters_from_request(request.args))
        return jsonify(payload)
    except Exception as e:
        logger.exception('integrity dashboard audit failed')
        return jsonify({'success': False, 'error': str(e)[:500]}, 500)


@bp.route('/reports/integrity-dashboard/api/journal', methods=['GET'])
def integrity_dashboard_api_journal():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    vno = (request.args.get('voucher_no') or request.args.get('journal_no') or '').strip()
    if not vno:
        return jsonify({'success': False, 'error': 'voucher_no required'}), 400
    loc = _integrity_resolve_branch(session, request.args)
    data = get_journal_drilldown(vno, loc)
    return jsonify({'success': True, **data})


@bp.route('/reports/integrity-dashboard/api/item-movement', methods=['GET'])
def integrity_dashboard_api_item_movement():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    ic = (request.args.get('item_code') or '').strip()
    if not ic:
        return jsonify({'success': False, 'error': 'item_code required'}), 400
    f = _integrity_filters_from_request(request.args)
    rows = get_item_movement_drilldown(ic, f['locationcode'], f.get('date_from') or '', f.get('date_to') or '')
    return jsonify({'success': True, 'rows': rows})


@bp.route('/reports/integrity-dashboard/api/stock-item', methods=['GET'])
def integrity_dashboard_api_stock_item():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    ic = (request.args.get('item_code') or '').strip()
    loc = _integrity_resolve_branch(session, request.args)
    rows = get_stock_item_drilldown(ic, loc)
    return jsonify({'success': True, 'rows': rows})


@bp.route('/reports/integrity-dashboard/api/stock-gl-drill', methods=['GET'])
def integrity_dashboard_api_stock_gl_drill():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    f = _integrity_filters_from_request(request.args)
    payload = get_stock_gl_variance_drilldown(
        f,
        warehouse_id=(request.args.get('warehouse_id') or '').strip(),
        row_type=(request.args.get('row_type') or 'total').strip().lower(),
        warehouse_label=(request.args.get('warehouse_label') or '').strip(),
    )
    return jsonify({'success': True, **payload})


@bp.route('/reports/integrity-dashboard/export-excel', methods=['GET'])
def integrity_dashboard_export_excel():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    payload = build_integrity_dashboard(_integrity_filters_from_request(request.args))
    output = io.StringIO()
    output.write('\ufeff')
    w = csv.writer(output)
    w.writerow(['Accounting & Inventory Integrity Audit'])
    w.writerow(['Generated', payload.get('generated_at', '')])
    summary = payload.get('summary') or {}
    w.writerow([])
    w.writerow(['Audit Summary'])
    for k, v in summary.items():
        w.writerow([k, v])
    w.writerow([])
    w.writerow(['Posting Verification'])
    w.writerow(['Document No', 'Date', 'Module', 'Voucher', 'Expected', 'Actual', 'Status'])
    for r in (payload.get('posting_verification') or {}).get('rows') or []:
        w.writerow([
            r.get('document_no'), r.get('document_date'), r.get('module'),
            r.get('voucher_no'), r.get('expected_entries'), r.get('actual_entries'), r.get('status'),
        ])
    w.writerow([])
    w.writerow(['Unbalanced Journals'])
    w.writerow(['Journal', 'Date', 'Debit', 'Credit', 'Difference'])
    for r in (payload.get('unbalanced_journals') or {}).get('rows') or []:
        w.writerow([r.get('journal_no'), r.get('date'), r.get('debit'), r.get('credit'), r.get('difference')])
    output.seek(0)
    fname = f"integrity_audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(output.getvalue(), mimetype='text/csv; charset=utf-8', headers={
        'Content-Disposition': f'attachment; filename={fname}',
    })


@bp.route('/reports/integrity-dashboard/export-pdf', methods=['GET'])
def integrity_dashboard_export_pdf():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not REPORTLAB_AVAILABLE:
        flash('PDF export requires ReportLab.', 'warning')
        return redirect(url_for('reports.integrity_dashboard_page', **request.args))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    payload = build_integrity_dashboard(_integrity_filters_from_request(request.args))
    summary = payload.get('summary') or {}
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=24, rightMargin=24, topMargin=24, bottomMargin=24)
    styles = getSampleStyleSheet()
    story = [
        Paragraph('Accounting &amp; Inventory Integrity Dashboard', styles['Title']),
        Spacer(1, 8),
        Paragraph(
            f"Checked: {summary.get('total_transactions_checked', 0)} | "
            f"Failed: {summary.get('failed_postings', 0)} | "
            f"Unbalanced: {summary.get('unbalanced_journals', 0)} | "
            f"Inventory variance: {summary.get('inventory_variance', 0):,.2f}",
            styles['Normal'],
        ),
        Spacer(1, 12),
    ]
    post_rows = (payload.get('posting_verification') or {}).get('rows') or []
    table_data = [['Doc', 'Date', 'Module', 'Voucher', 'Status']]
    for r in post_rows[:80]:
        if r.get('status') != 'ok':
            table_data.append([
                str(r.get('document_no') or '')[:12],
                str(r.get('document_date') or '')[:10],
                str(r.get('module') or '')[:16],
                str(r.get('voucher_no') or '')[:18],
                str(r.get('status') or ''),
            ])
    if len(table_data) > 1:
        tbl = Table(table_data, repeatRows=1)
        tbl.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTSIZE', (0, 0), (-1, -1), 7),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
        ]))
        story.append(tbl)
    doc.build(story)
    buf.seek(0)
    fname = f"integrity_audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return send_file(buf, mimetype='application/pdf', as_attachment=True, download_name=fname)


from addons.reports.gross_margin_logic import (
    build_gross_margin_dashboard,
    get_gross_margin_drilldown,
    get_gross_margin_filter_options,
)
from addons.reports.integrity_dashboard_logic import (
    resolve_branch_from_session as _gross_margin_resolve_branch,
)


def _gross_margin_filters_from_request(args) -> Dict[str, Any]:
    loc = _gross_margin_resolve_branch(session, args)
    return {
        'locationcode': loc,
        'branch': str(loc),
        'date_from': (args.get('date_from') or '').strip(),
        'date_to': (args.get('date_to') or '').strip(),
        'customer_code': (args.get('customer_code') or '').strip(),
        'salesman_code': (args.get('salesman_code') or '').strip(),
        'item_code': (args.get('item_code') or args.get('itemcode') or '').strip(),
        'category_code': (args.get('category_code') or '').strip(),
        'brand_code': (args.get('brand_code') or '').strip(),
        'warehouse_id': (args.get('warehouse_id') or '').strip(),
        'search': (args.get('search') or '').strip(),
        'max_rows': (args.get('max_rows') or '12000').strip(),
    }


@bp.route('/reports/gross-margin', methods=['GET'])
def gross_margin_dashboard_page():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    filters = _gross_margin_filters_from_request(request.args)
    if not filters.get('date_from'):
        filters['date_from'] = f"{datetime.now().year}-01-01"
    if not filters.get('date_to'):
        filters['date_to'] = datetime.now().strftime('%Y-%m-%d')
    options = get_gross_margin_filter_options(filters['locationcode'])
    return render_template(
        'reports/gross_margin_dashboard.html',
        title='Gross Margin Analysis',
        filters=filters,
        options=options,
        api_data_url=url_for('reports.gross_margin_api_data'),
        api_drilldown_url=url_for('reports.gross_margin_api_drilldown'),
        export_excel_url=url_for('reports.gross_margin_export_excel'),
        export_pdf_url=url_for('reports.gross_margin_export_pdf'),
    )


@bp.route('/reports/gross-margin/api/data', methods=['GET'])
def gross_margin_api_data():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    payload = build_gross_margin_dashboard(_gross_margin_filters_from_request(request.args))
    return jsonify(payload)


@bp.route('/reports/gross-margin/api/drilldown', methods=['GET'])
def gross_margin_api_drilldown():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    item_code = (request.args.get('item_code') or request.args.get('itemcode') or '').strip()
    if not item_code:
        return jsonify({'success': False, 'error': 'item_code required'}), 400
    f = _gross_margin_filters_from_request(request.args)
    data = get_gross_margin_drilldown(
        item_code,
        f['locationcode'],
        date_from=f.get('date_from') or '',
        date_to=f.get('date_to') or '',
    )
    return jsonify({'success': True, 'item_code': item_code, 'data': data})


@bp.route('/reports/gross-margin/export-excel', methods=['GET'])
def gross_margin_export_excel():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    payload = build_gross_margin_dashboard(_gross_margin_filters_from_request(request.args))
    grid = payload.get('grid') or []
    output = io.StringIO()
    output.write('\ufeff')
    w = csv.writer(output)
    w.writerow(['Gross Margin Analysis'])
    w.writerow(['Generated', payload.get('generated_at', '')])
    kpis = payload.get('kpis') or {}
    w.writerow([])
    w.writerow(['KPI', 'Value'])
    for k, v in kpis.items():
        if isinstance(v, dict):
            w.writerow([k, json.dumps(v, default=str)])
        else:
            w.writerow([k, v])
    w.writerow([])
    w.writerow([
        'Invoice No', 'Invoice Date', 'Customer', 'Salesman', 'Item Code', 'Item Name',
        'Qty', 'Sales Rate', 'Cost Rate', 'Sales Amount', 'Cost Amount', 'Profit', 'Margin %', 'Status',
    ])
    for r in grid:
        w.writerow([
            r.get('invoice_no'), r.get('invoice_date'), r.get('customer'), r.get('salesman'),
            r.get('item_code'), r.get('item_name'), r.get('qty'), r.get('sales_rate'), r.get('cost_rate'),
            r.get('sales_amount'), r.get('cost_amount'), r.get('profit_amount'), r.get('margin_pct'),
            r.get('status'),
        ])
    output.seek(0)
    fname = f"gross_margin_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(output.getvalue(), mimetype='text/csv; charset=utf-8', headers={
        'Content-Disposition': f'attachment; filename={fname}',
    })


@bp.route('/reports/gross-margin/export-pdf', methods=['GET'])
def gross_margin_export_pdf():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not REPORTLAB_AVAILABLE:
        flash('PDF export requires ReportLab.', 'warning')
        return redirect(url_for('reports.gross_margin_dashboard_page', **request.args))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    payload = build_gross_margin_dashboard(_gross_margin_filters_from_request(request.args))
    kpis = payload.get('kpis') or {}
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=24, rightMargin=24, topMargin=24, bottomMargin=24)
    styles = getSampleStyleSheet()
    story = [
        Paragraph('Gross Margin Analysis', styles['Title']),
        Spacer(1, 8),
        Paragraph(
            f"Sales: {kpis.get('total_sales', 0):,.2f} | Cost: {kpis.get('total_cost', 0):,.2f} | "
            f"Gross Profit: {kpis.get('gross_profit', 0):,.2f} | Margin: {kpis.get('margin_pct')}%",
            styles['Normal'],
        ),
        Spacer(1, 12),
    ]
    grid = (payload.get('grid') or [])[:60]
    table_data = [['Invoice', 'Date', 'Item', 'Sales', 'Cost', 'Profit', 'Margin %']]
    for r in grid:
        table_data.append([
            str(r.get('invoice_no') or '')[:10],
            str(r.get('invoice_date') or '')[:10],
            str(r.get('item_code') or '')[:12],
            f"{_to_float(r.get('sales_amount')):,.0f}",
            f"{_to_float(r.get('cost_amount')):,.0f}",
            f"{_to_float(r.get('profit_amount')):,.0f}",
            str(r.get('margin_pct') or ''),
        ])
    if len(table_data) > 1:
        tbl = Table(table_data, repeatRows=1)
        tbl.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTSIZE', (0, 0), (-1, -1), 7),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
        ]))
        story.append(tbl)
    doc.build(story)
    buf.seek(0)
    fname = f"gross_margin_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return send_file(buf, mimetype='application/pdf', as_attachment=True, download_name=fname)
