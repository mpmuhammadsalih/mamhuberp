"""Fixed Asset Sale PDF (ReportLab)."""
from __future__ import annotations

import io
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    REPORTLAB_AVAILABLE = True
except Exception:
    REPORTLAB_AVAILABLE = False

from addons.fixed_assets.fixed_assets_db import get_fa_sale
from nexa_http import session


def _fmt_date(raw: Any) -> str:
    if raw is None:
        return ''
    if hasattr(raw, 'strftime'):
        return raw.strftime('%d-%m-%Y')
    s = str(raw or '').strip()
    if len(s) >= 10:
        try:
            return datetime.strptime(s[:10], '%Y-%m-%d').strftime('%d-%m-%Y')
        except Exception:
            return s[:10]
    return s


def _money(v: Any) -> str:
    try:
        return f'{float(v or 0):,.2f}'
    except (TypeError, ValueError):
        return '0.00'


def _company_profile() -> Dict[str, str]:
    try:
        from addons.purchase.controllers.routes import _get_company_profile
        return _get_company_profile() or {}
    except Exception:
        return {}


def build_fa_sale_pdf(sale_id: int) -> Tuple[Optional[bytes], Optional[str]]:
    if not REPORTLAB_AVAILABLE:
        return None, 'PDF library (reportlab) is not available.'
    sale = get_fa_sale(int(sale_id))
    if not sale:
        return None, 'Sale not found.'
    lines: List[Dict[str, Any]] = sale.get('lines') or []
    company = _company_profile()
    company_name = str(company.get('name') or session.get('location_name') or 'Company')
    company_address = str(company.get('address') or '').strip()
    company_phone = str(company.get('phone') or '').strip()
    company_email = str(company.get('email') or '').strip()
    username = str(sale.get('posted_by') or sale.get('created_by') or session.get('user') or '')
    sale_no = str(sale.get('sale_no') or '')
    sale_date = _fmt_date(sale.get('sale_date'))
    status = str(sale.get('status') or '').upper()
    voucher_no = str(sale.get('gl_voucher_no') or '')
    remarks = str(sale.get('remarks') or '')
    proceeds_ac = str(sale.get('proceeds_account') or '')
    party_type = str(sale.get('proceeds_party_type') or '').strip()
    party_code = str(sale.get('proceeds_party_code') or '').strip()
    party_bits = [proceeds_ac]
    if party_type and party_code:
        party_bits.append(f'{party_type} {party_code}')
    proceeds_label = ' / '.join([b for b in party_bits if b])

    total_cost = float(sale.get('total_cost') or 0)
    total_accum = float(sale.get('total_accum') or 0)
    total_nbv = float(sale.get('total_nbv') or 0)
    total_proceeds = float(sale.get('total_proceeds') or 0)
    total_gain = float(sale.get('total_gain_loss') or 0)

    styles = getSampleStyleSheet()
    BLUE = colors.HexColor('#1a56a4')
    BLUE_LIGHT = colors.HexColor('#e8f0fb')
    BORDER = colors.HexColor('#b0b8c4')
    GRAY_ROW = colors.HexColor('#f7f8fa')
    TEXT = colors.HexColor('#1a1a1a')
    PAD = 5
    LEFT_M = 0.4 * inch
    RIGHT_M = 0.4 * inch
    # Single content width for header / lines / totals / signatures
    W = A4[0] - LEFT_M - RIGHT_M

    def _s(name: str, **kw: Any) -> ParagraphStyle:
        base = kw.pop('parent', styles['Normal'])
        kw.setdefault('textColor', TEXT)
        return ParagraphStyle(name, parent=base, **kw)

    N9 = _s('fas9', fontSize=9, leading=12)
    N9R = _s('fas9r', fontSize=9, leading=12, alignment=TA_RIGHT)
    LBL = _s('faslbl', fontSize=8, leading=11, textColor=colors.HexColor('#555f6b'))
    SUB = _s('fassub', fontSize=9, leading=12, alignment=TA_CENTER, textColor=colors.HexColor('#555f6b'))
    WHT = _s('faswht', fontSize=8, leading=11, alignment=TA_CENTER, textColor=colors.white)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=0.45 * inch,
        bottomMargin=0.45 * inch,
        leftMargin=LEFT_M,
        rightMargin=RIGHT_M,
    )
    elements: List[Any] = []

    company_lines = [
        Paragraph(f'<b>{company_name}</b>', _s('fascn', fontSize=11, leading=14, alignment=TA_CENTER, textColor=BLUE))
    ]
    if company_address:
        company_lines.append(Paragraph(company_address, SUB))
    if company_phone:
        company_lines.append(Paragraph(f'Tel: {company_phone}', SUB))
    if company_email:
        company_lines.append(Paragraph(f'Email: {company_email}', SUB))
    title_tbl = Table([[company_lines]], colWidths=[W], hAlign='LEFT')
    title_tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (0, 0), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), PAD),
        ('BOTTOMPADDING', (0, 0), (-1, -1), PAD),
    ]))
    elements.append(title_tbl)
    elements.append(Spacer(1, 2))
    elements.append(Paragraph('<b>FIXED ASSET SALE</b>', _s('fast1', fontSize=13, leading=16, alignment=TA_CENTER, textColor=BLUE)))
    elements.append(Spacer(1, 4))
    rule_tbl = Table([['']], colWidths=[W], rowHeights=[2], hAlign='LEFT')
    rule_tbl.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), BLUE)]))
    elements.append(rule_tbl)
    elements.append(Spacer(1, 6))

    def _info_row(label: str, value: Any) -> list:
        return [Paragraph(label, LBL), Paragraph(str(value or '—'), N9)]

    LEFT_W = W * 0.55
    RIGHT_W = W - LEFT_W
    left_rows = [
        _info_row('Proceeds Account', proceeds_label),
        _info_row('Remarks', remarks or '—'),
        _info_row('GL Voucher', voucher_no or '—'),
    ]
    right_rows = [
        _info_row('Sale No', sale_no),
        _info_row('Sale Date', sale_date),
        _info_row('Status', status or '—'),
        _info_row('Prepared By', username or '—'),
    ]
    while len(right_rows) < len(left_rows):
        right_rows.append(_info_row('', ''))
    while len(left_rows) < len(right_rows):
        left_rows.append(_info_row('', ''))

    LBL_W = 1.35 * inch
    VAL_W = LEFT_W - LBL_W
    LBL_W2 = 1.1 * inch
    VAL_W2 = RIGHT_W - LBL_W2
    left_tbl = Table(left_rows, colWidths=[LBL_W, VAL_W])
    right_tbl = Table(right_rows, colWidths=[LBL_W2, VAL_W2])
    for t in (left_tbl, right_tbl):
        t.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 8.5),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LINEBELOW', (0, 0), (-1, -2), 0.3, colors.HexColor('#dde3ea')),
            ('TOPPADDING', (0, 0), (-1, -1), PAD),
            ('BOTTOMPADDING', (0, 0), (-1, -1), PAD),
            ('LEFTPADDING', (0, 0), (-1, -1), PAD),
            ('RIGHTPADDING', (0, 0), (-1, -1), PAD),
        ]))
    info_outer = Table([[left_tbl, right_tbl]], colWidths=[LEFT_W, RIGHT_W], hAlign='LEFT')
    info_outer.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.5, BORDER),
        ('LINEBEFORE', (1, 0), (1, 0), 0.5, BORDER),
        ('BACKGROUND', (0, 0), (-1, -1), BLUE_LIGHT),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(info_outer)
    elements.append(Spacer(1, 8))

    def _hcell(txt: str) -> Paragraph:
        return Paragraph(f'<b>{txt}</b>', WHT)

    def _dcell(txt: Any, align: str = 'LEFT') -> Paragraph:
        st = N9R if align == 'RIGHT' else N9
        return Paragraph(str(txt), st)

    headers = ['Sl', 'Asset No', 'Asset Name', 'Cost', 'Accum', 'NBV', 'Proceeds', 'Gain/Loss']
    pt_rows = [[_hcell(c) for c in headers]]
    for idx, ln in enumerate(lines, start=1):
        pt_rows.append([
            _dcell(idx, 'RIGHT'),
            _dcell(ln.get('asset_no') or ''),
            _dcell(ln.get('asset_name') or ''),
            _dcell(_money(ln.get('acquisition_cost')), 'RIGHT'),
            _dcell(_money(ln.get('accum_dep')), 'RIGHT'),
            _dcell(_money(ln.get('nbv')), 'RIGHT'),
            _dcell(_money(ln.get('proceeds_amount')), 'RIGHT'),
            _dcell(_money(ln.get('gain_loss_amount')), 'RIGHT'),
        ])
    if not lines:
        pt_rows.append([_dcell('No asset lines', 'LEFT')] + [_dcell('')] * 7)

    # Same total width as header / totals (fractions of W)
    col_frac = [0.045, 0.115, 0.265, 0.11, 0.11, 0.11, 0.12, 0.125]
    col_w = [W * f for f in col_frac]
    col_w[-1] = W - sum(col_w[:-1])
    pt = Table(pt_rows, repeatRows=1, colWidths=col_w, hAlign='LEFT')
    pt.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), BLUE),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.4, BORDER),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, GRAY_ROW]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), PAD),
        ('BOTTOMPADDING', (0, 0), (-1, -1), PAD),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(pt)
    elements.append(Spacer(1, 8))

    SL = _s('fassl', fontSize=9, leading=12, alignment=TA_RIGHT, textColor=colors.HexColor('#333'))
    SR = _s('fassr', fontSize=9, leading=12, alignment=TA_RIGHT)
    gain_label = 'Gain' if total_gain >= 0 else 'Loss'
    sum_rows = [
        [Paragraph('Total Cost', SL), Paragraph(_money(total_cost), SR)],
        [Paragraph('Total Accum. Dep', SL), Paragraph(_money(total_accum), SR)],
        [Paragraph('Total NBV', SL), Paragraph(_money(total_nbv), SR)],
        [Paragraph('Total Proceeds', SL), Paragraph(_money(total_proceeds), SR)],
        [Paragraph(f'<b>Total {gain_label}</b>', SL), Paragraph(f'<b>{_money(abs(total_gain))}</b>', SR)],
    ]
    sum_tbl = Table(sum_rows, colWidths=[W - 1.7 * inch, 1.7 * inch], hAlign='LEFT')
    sum_tbl.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.5, BORDER),
        ('LINEBELOW', (0, 0), (-1, -2), 0.3, colors.HexColor('#dde3ea')),
        ('BACKGROUND', (0, -1), (-1, -1), BLUE_LIGHT),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), PAD),
        ('BOTTOMPADDING', (0, 0), (-1, -1), PAD),
        ('LEFTPADDING', (0, 0), (-1, -1), PAD),
        ('RIGHTPADDING', (0, 0), (-1, -1), PAD),
    ]))
    elements.append(sum_tbl)
    elements.append(Spacer(1, 18))

    sig = Table(
        [[
            Paragraph('Prepared By', LBL),
            Paragraph('Verified By', LBL),
            Paragraph('Approved By', LBL),
        ], [
            Paragraph(username or '______________', N9),
            Paragraph('______________', N9),
            Paragraph('______________', N9),
        ]],
        colWidths=[W / 3.0] * 3,
        hAlign='LEFT',
    )
    sig.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(sig)

    doc.build(elements)
    return buffer.getvalue(), None
