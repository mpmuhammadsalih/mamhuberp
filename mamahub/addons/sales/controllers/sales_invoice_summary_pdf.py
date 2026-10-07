"""Sales invoice list — summary PDF (reportlab)."""
from __future__ import annotations

import io
import os
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Image as RLImage
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


def _billtype_label(raw: Any) -> str:
    bt = str(raw or '').strip().upper()
    if bt == 'R':
        return 'Credit'
    if bt == 'C' or not bt:
        return 'Cash'
    return str(raw or '').strip() or 'Cash'


def sales_invoice_list_summary_stats(rows: List[Dict[str, Any]], *, doc_kind: str = 'invoice') -> Dict[str, Any]:
    kind = (doc_kind or 'invoice').strip().lower()
    total_count = len(rows or [])
    total_amount = 0.0
    cash_count = 0
    cash_amount = 0.0
    credit_count = 0
    credit_amount = 0.0
    invoice_count = 0
    invoice_amount = 0.0
    return_count = 0
    return_amount = 0.0

    for r in rows or []:
        row_kind = (r.get('doc_type') or kind).strip().lower()
        if kind == 'all':
            sales_return = row_kind == 'return'
        else:
            sales_return = kind == 'return'
        try:
            amt_raw = float(r.get('netbillamount') or 0)
        except (TypeError, ValueError):
            amt_raw = 0.0
        amt = abs(amt_raw) if sales_return else amt_raw
        total_amount += amt
        if sales_return:
            return_count += 1
            return_amount += amt
        else:
            invoice_count += 1
            invoice_amount += amt
        if _billtype_label(r.get('billtype')) == 'Credit':
            credit_count += 1
            credit_amount += amt
        else:
            cash_count += 1
            cash_amount += amt

    result: Dict[str, Any] = {
        'total_count': total_count,
        'total_amount': round(total_amount, 2),
        'cash_count': cash_count,
        'cash_amount': round(cash_amount, 2),
        'credit_count': credit_count,
        'credit_amount': round(credit_amount, 2),
        'doc_kind': kind,
    }
    if kind == 'all':
        result.update({
            'invoice_count': invoice_count,
            'invoice_amount': round(invoice_amount, 2),
            'return_count': return_count,
            'return_amount': round(return_amount, 2),
            'net_amount': round(invoice_amount - return_amount, 2),
        })
    return result


def _detail_col_widths(usable_w: float, *, include_doc: bool = False) -> List[float]:
    """Detail columns: optional Doc + fixed widths + flexible customer name."""
    if include_doc:
        leading = 0.42 * inch + 0.62 * inch + 0.72 * inch + 0.82 * inch + 0.78 * inch
        trailing = 0.62 * inch + 1.0 * inch
    else:
        leading = 0.42 * inch + 0.72 * inch + 0.82 * inch + 0.78 * inch
        trailing = 0.72 * inch + 1.05 * inch
    name_w = max(1.0 * inch, usable_w - leading - trailing)
    if include_doc:
        return [
            0.42 * inch,
            0.62 * inch,
            0.72 * inch,
            0.82 * inch,
            0.78 * inch,
            name_w,
            0.62 * inch,
            1.0 * inch,
        ]
    return [
        0.42 * inch,
        0.72 * inch,
        0.82 * inch,
        0.78 * inch,
        name_w,
        0.72 * inch,
        1.05 * inch,
    ]


def build_sales_invoice_summary_pdf(
    rows: List[Dict[str, Any]],
    *,
    date_from: str = '',
    date_to: str = '',
    search: str = '',
    company_name: str = '',
    company_address: str = '',
    company_phone: str = '',
    company_email: str = '',
    branch_label: str = '',
    logo_path: str = '',
    billtype_label_fn: Optional[Callable[[Any], str]] = None,
    doc_kind: str = 'invoice',
) -> Tuple[Optional[bytes], Optional[str]]:
    if not REPORTLAB_AVAILABLE:
        return None, 'PDF library (reportlab) is not available.'
    label_fn = billtype_label_fn or _billtype_label
    kind = (doc_kind or 'invoice').strip().lower()
    sales_return = kind == 'return'
    sales_all = kind == 'all'
    stats = sales_invoice_list_summary_stats(rows, doc_kind=doc_kind)
    styles = getSampleStyleSheet()
    BLUE = colors.HexColor('#1a56a4')
    BLUE_LIGHT = colors.HexColor('#e8f0fb')
    BORDER = colors.HexColor('#b0b8c4')
    GRAY_ROW = colors.HexColor('#f7f8fa')
    TEXT = colors.HexColor('#1a1a1a')
    PAD = 5

    def _s(name: str, **kw):
        base = kw.pop('parent', styles['Normal'])
        kw.setdefault('textColor', TEXT)
        return ParagraphStyle(name, parent=base, **kw)

    N8 = _s('si8', fontSize=8, leading=11, alignment=TA_LEFT)
    N9 = _s('si9', fontSize=9, leading=12, alignment=TA_LEFT)
    N9R = _s('si9r', fontSize=9, leading=12, alignment=TA_RIGHT)
    N9C = _s('si9c', fontSize=9, leading=12, alignment=TA_CENTER)
    HDR = _s('sihdr', fontSize=15, leading=18, alignment=TA_CENTER, textColor=BLUE, fontName='Helvetica-Bold')
    SUB = _s('sisub', fontSize=9, leading=12, alignment=TA_CENTER, textColor=colors.HexColor('#555f6b'))
    TITLE = _s('sititle', fontSize=12, leading=16, alignment=TA_CENTER, textColor=BLUE, fontName='Helvetica-Bold')
    WHT = _s('siwht', fontSize=9, leading=12, alignment=TA_CENTER, textColor=colors.white, fontName='Helvetica-Bold')
    WHT_R = _s('siwhtR', fontSize=9, leading=12, alignment=TA_RIGHT, textColor=colors.white, fontName='Helvetica-Bold')
    TOT_R = _s('sitotR', fontSize=9, leading=12, fontName='Helvetica-Bold', alignment=TA_RIGHT)
    SUM_L = _s('sisumL', fontSize=9, leading=12, fontName='Helvetica-Bold', alignment=TA_LEFT)
    SUM_R = _s('sisumR', fontSize=9, leading=12, fontName='Helvetica-Bold', alignment=TA_RIGHT)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=0.45 * inch,
        bottomMargin=0.4 * inch,
        leftMargin=0.5 * inch,
        rightMargin=0.5 * inch,
    )
    usable_w = doc.width
    elements: List[Any] = []

    logo_cell: Any = ''
    if logo_path and os.path.exists(logo_path):
        try:
            logo_cell = RLImage(logo_path, width=1.2 * inch, height=0.55 * inch)
            logo_cell.hAlign = 'LEFT'
        except Exception:
            logo_cell = ''

    co_lines = [Paragraph(company_name or branch_label or 'Company', HDR)]
    if company_address:
        co_lines.append(Paragraph(company_address, SUB))
    if branch_label and branch_label != company_name:
        co_lines.append(Paragraph(f'Branch: {branch_label}', SUB))
    if company_phone:
        co_lines.append(Paragraph(f'Tel: {company_phone}', SUB))
    if company_email:
        co_lines.append(Paragraph(f'Email: {company_email}', SUB))

    hdr_tbl = Table(
        [[logo_cell, co_lines, '']],
        colWidths=[1.3 * inch, usable_w - 2.6 * inch, 1.3 * inch],
    )
    hdr_tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    hdr_tbl.hAlign = 'LEFT'
    elements.append(hdr_tbl)

    rule = Table([['']], colWidths=[usable_w])
    rule.setStyle(TableStyle([
        ('LINEBELOW', (0, 0), (0, 0), 1.5, BLUE),
        ('TOPPADDING', (0, 0), (0, 0), 0),
        ('BOTTOMPADDING', (0, 0), (0, 0), 4),
    ]))
    rule.hAlign = 'LEFT'
    elements.append(rule)
    elements.append(Spacer(1, 6))
    report_title = 'Sales — Combined Summary Report' if sales_all else (
        'Sales Return — Summary Report' if sales_return else 'Sales Invoice — Summary Report'
    )
    elements.append(Paragraph(report_title, TITLE))
    elements.append(Spacer(1, 4))

    date_range_parts: List[str] = []
    if date_from:
        date_range_parts.append(f'From: {date_from}')
    if date_to:
        date_range_parts.append(f'To: {date_to}')
    if not date_range_parts:
        date_range_parts.append('All Dates')
    if search:
        date_range_parts.append(f'Search: {search}')
    generated_on = datetime.now().strftime('%d-%m-%Y %H:%M')
    info_text = '  |  '.join(date_range_parts) + f'  |  Generated: {generated_on}  |  Records: {stats["total_count"]}'
    elements.append(Paragraph(info_text, SUB))
    elements.append(Spacer(1, 10))

    sum_label_w = 1.55 * inch
    sum_value_w = 1.05 * inch
    sum_col_widths = [
        sum_label_w, sum_value_w,
        sum_label_w, usable_w - (2 * sum_label_w + 2 * sum_value_w),
    ]
    total_label = 'Total Records' if sales_all else ('Total Returns' if sales_return else 'Total Invoices')
    if sales_all:
        summary_data = [
            [
                Paragraph(total_label, SUM_L), Paragraph(str(stats['total_count']), SUM_R),
                Paragraph('Sales Invoice', SUM_L), Paragraph(f'{stats["invoice_count"]}  ·  {stats["invoice_amount"]:,.2f}', SUM_R),
            ],
            [
                Paragraph('Sales Return', SUM_L), Paragraph(f'{stats["return_count"]}  ·  {stats["return_amount"]:,.2f}', SUM_R),
                Paragraph('Net Sales', SUM_L), Paragraph(f'{stats["net_amount"]:,.2f}', SUM_R),
            ],
            [
                Paragraph('Cash Bills', SUM_L), Paragraph(str(stats['cash_count']), SUM_R),
                Paragraph('Cash Amount', SUM_L), Paragraph(f'{stats["cash_amount"]:,.2f}', SUM_R),
            ],
            [
                Paragraph('Credit Bills', SUM_L), Paragraph(str(stats['credit_count']), SUM_R),
                Paragraph('Credit Amount', SUM_L), Paragraph(f'{stats["credit_amount"]:,.2f}', SUM_R),
            ],
        ]
    else:
        summary_data = [
            [
                Paragraph(total_label, SUM_L), Paragraph(str(stats['total_count']), SUM_R),
                Paragraph('Total Amount', SUM_L), Paragraph(f'{stats["total_amount"]:,.2f}', SUM_R),
            ],
            [
                Paragraph('Cash Invoices', SUM_L), Paragraph(str(stats['cash_count']), SUM_R),
                Paragraph('Cash Amount', SUM_L), Paragraph(f'{stats["cash_amount"]:,.2f}', SUM_R),
            ],
            [
                Paragraph('Credit Invoices', SUM_L), Paragraph(str(stats['credit_count']), SUM_R),
                Paragraph('Credit Amount', SUM_L), Paragraph(f'{stats["credit_amount"]:,.2f}', SUM_R),
            ],
        ]
    sum_tbl = Table(summary_data, colWidths=sum_col_widths)
    sum_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), BLUE_LIGHT),
        ('GRID', (0, 0), (-1, -1), 0.4, BORDER),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('ALIGN', (3, 0), (3, -1), 'RIGHT'),
    ]))
    sum_tbl.hAlign = 'LEFT'
    elements.append(sum_tbl)
    elements.append(Spacer(1, 12))

    detail_col_widths = _detail_col_widths(usable_w, include_doc=sales_all)
    name_col_idx = 5 if sales_all else 4
    amount_col_idx = len(detail_col_widths) - 1
    span_end = amount_col_idx - 1

    if sales_all:
        tbl_header = [
            Paragraph('Sl.No', WHT),
            Paragraph('Doc', WHT),
            Paragraph('Bill No', WHT),
            Paragraph('Date', WHT),
            Paragraph('Cust Code', WHT),
            Paragraph('Customer Name', WHT),
            Paragraph('Type', WHT),
            Paragraph('Amount', WHT_R),
        ]
    else:
        tbl_header = [
            Paragraph('Sl.No', WHT),
            Paragraph('Bill No', WHT),
            Paragraph('Date', WHT),
            Paragraph('Cust Code', WHT),
            Paragraph('Customer Name', WHT),
            Paragraph('Type', WHT),
            Paragraph('Amount', WHT_R),
        ]
    table_data: List[List[Any]] = [tbl_header]
    grand_total = 0.0
    for idx, r in enumerate(rows or [], 1):
        row_is_return = sales_return or (r.get('doc_type') or '').strip().lower() == 'return'
        try:
            amt_raw = float(r.get('netbillamount') or 0)
        except (TypeError, ValueError):
            amt_raw = 0.0
        amt = abs(amt_raw) if row_is_return else amt_raw
        grand_total += amt
        billdate = r.get('billdate')
        if billdate is not None and hasattr(billdate, 'strftime'):
            d_s = billdate.strftime('%Y-%m-%d')
        else:
            d_s = str(billdate or '')[:10]
        cust_name = str(r.get('customername') or '-').strip() or '-'
        if sales_all:
            doc_label = 'Return' if row_is_return else 'Invoice'
            table_data.append([
                Paragraph(str(idx), N9C),
                Paragraph(doc_label, N9C),
                Paragraph(str(r.get('billno') or '-'), N9C),
                Paragraph(d_s or '-', N9C),
                Paragraph(str(r.get('customercode') or '-'), N9C),
                Paragraph(cust_name, N8),
                Paragraph(label_fn(r.get('billtype')), N9C),
                Paragraph(f'{amt:,.2f}', N9R),
            ])
        else:
            table_data.append([
                Paragraph(str(idx), N9C),
                Paragraph(str(r.get('billno') or '-'), N9C),
                Paragraph(d_s or '-', N9C),
                Paragraph(str(r.get('customercode') or '-'), N9C),
                Paragraph(cust_name, N8),
                Paragraph(label_fn(r.get('billtype')), N9C),
                Paragraph(f'{amt:,.2f}', N9R),
            ])

    total_row_idx = len(table_data)
    total_row: List[Any] = [Paragraph('Total', TOT_R)]
    total_row.extend([''] * (amount_col_idx - 1))
    total_row.append(Paragraph(f'{grand_total:,.2f}', TOT_R))
    table_data.append(total_row)

    dt = Table(table_data, colWidths=detail_col_widths, repeatRows=1)
    dt.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), BLUE),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('ROWBACKGROUND', (0, 1), (-1, -2), [colors.white, GRAY_ROW]),
        ('BACKGROUND', (0, -1), (-1, -1), BLUE_LIGHT),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('SPAN', (0, total_row_idx), (span_end, total_row_idx)),
        ('LINEABOVE', (0, -1), (-1, -1), 1.0, BLUE),
        ('GRID', (0, 0), (-1, -1), 0.4, BORDER),
        ('LINEBELOW', (0, 0), (-1, 0), 1.0, BLUE),
        ('TOPPADDING', (0, 0), (-1, -1), PAD),
        ('BOTTOMPADDING', (0, 0), (-1, -1), PAD),
        ('LEFTPADDING', (0, 0), (-1, -1), PAD),
        ('RIGHTPADDING', (0, 0), (-1, -1), PAD),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (0, -2), 'CENTER'),
        ('ALIGN', (1, 0), (4 if sales_all else 3, -2), 'CENTER'),
        ('ALIGN', (amount_col_idx - 1, 0), (amount_col_idx - 1, -2), 'CENTER'),
        ('ALIGN', (amount_col_idx, 0), (amount_col_idx, -1), 'RIGHT'),
        ('ALIGN', (0, -1), (0, -1), 'RIGHT'),
        ('ALIGN', (name_col_idx, 1), (name_col_idx, -2), 'LEFT'),
    ]))
    dt.hAlign = 'LEFT'
    elements.append(dt)

    footer_label = 'Sales Combined Summary' if sales_all else (
        'Sales Return Summary' if sales_return else 'Sales Invoice Summary'
    )
    footer_name = company_name or branch_label or footer_label

    def add_page_footer(canvas, doc_obj):
        canvas.saveState()
        canvas.setFont('Helvetica', 7.5)
        canvas.setFillColor(colors.HexColor('#888888'))
        w, _h = A4
        canvas.drawCentredString(w / 2, 0.25 * inch, f'{footer_label}  —  {footer_name}  —  Page {doc_obj.page}')
        canvas.restoreState()

    doc.build(elements, onFirstPage=add_page_footer, onLaterPages=add_page_footer)
    return buffer.getvalue(), None
