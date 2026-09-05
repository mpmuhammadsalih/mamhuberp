"""Gulf Nova retail invoice PDF layout — matches the navy/red branded design."""
from __future__ import annotations

import io
from datetime import datetime
from typing import Any, Dict, List, Optional
from xml.sax.saxutils import escape as _xml_escape

try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Flowable, Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from reportlab.pdfgen import canvas as rl_canvas
    _RL = True
except Exception:
    _RL = False
    rl_canvas = None
    Image = None
    Flowable = object  # type: ignore


NAVY = colors.HexColor('#002147')
RED = colors.HexColor('#C00000')
BORDER = colors.HexColor('#c8cdd4')
TEXT = colors.HexColor('#1a1a1a')
MUTED = colors.HexColor('#555f6b')
LIGHT = colors.HexColor('#f7f8fa')


class _BillToRibbon(Flowable):
    """Red BILL TO tag with a slanted right edge (matches mockup)."""

    def __init__(self, width=1.35 * inch, height=0.32 * inch):
        Flowable.__init__(self)
        self._w = width
        self._h = height

    def wrap(self, availWidth, availHeight):  # noqa: N802
        return (self._w, self._h)

    def draw(self):
        c = self.canv
        w, h = float(self._w), float(self._h)
        cut = min(10, w * 0.12)
        c.saveState()
        c.setFillColor(RED)
        p = c.beginPath()
        p.moveTo(0, 0)
        p.lineTo(w - cut, 0)
        p.lineTo(w, h / 2.0)
        p.lineTo(w - cut, h)
        p.lineTo(0, h)
        p.close()
        c.drawPath(p, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont('Helvetica-Bold', 9)
        c.drawString(10, h * 0.32, 'BILL TO')
        c.restoreState()


class _InvoiceTitleRule(Flowable):
    """INVOICE title with thin red rules above and below (matches mockup)."""

    def __init__(self, text: str, width: float, font_size: float = 22):
        Flowable.__init__(self)
        self._text = str(text or 'INVOICE')
        self._w = width
        self._font_size = font_size
        self._h = font_size + 16

    def wrap(self, availWidth, availHeight):  # noqa: N802
        return (self._w, self._h)

    def draw(self):
        c = self.canv
        c.saveState()
        c.setFont('Helvetica-Bold', self._font_size)
        tw = c.stringWidth(self._text, 'Helvetica-Bold', self._font_size)
        # Title + matching red rules, right-aligned in the meta column
        x = self._w - tw
        mid_y = self._h / 2.0 - 2
        c.setStrokeColor(RED)
        c.setLineWidth(1.15)
        c.line(x, self._h - 2, x + tw, self._h - 2)
        c.setFillColor(NAVY)
        c.drawString(x, mid_y - self._font_size * 0.15, self._text)
        c.setStrokeColor(RED)
        c.setLineWidth(1.15)
        c.line(x, 2, x + tw, 2)
        c.restoreState()


class _ContactIcon(Flowable):
    """Tiny red contact glyph (pin / phone / mail / web)."""

    def __init__(self, kind: str, size: float = 9):
        Flowable.__init__(self)
        self.kind = kind
        self._s = size

    def wrap(self, availWidth, availHeight):  # noqa: N802
        return (self._s + 2, self._s + 1)

    def draw(self):
        c = self.canv
        s = self._s
        c.saveState()
        c.setStrokeColor(RED)
        c.setFillColor(RED)
        c.setLineWidth(0.9)
        k = self.kind
        if k == 'pin':
            # Map-pin silhouette
            p = c.beginPath()
            p.moveTo(s * 0.5, 0.2)
            p.curveTo(s * 0.95, s * 0.45, s * 0.85, s * 0.95, s * 0.5, s * 0.95)
            p.curveTo(s * 0.15, s * 0.95, s * 0.05, s * 0.45, s * 0.5, 0.2)
            p.close()
            c.drawPath(p, stroke=0, fill=1)
            c.setFillColor(colors.white)
            c.circle(s * 0.5, s * 0.62, s * 0.16, stroke=0, fill=1)
        elif k == 'phone':
            c.roundRect(s * 0.28, s * 0.05, s * 0.44, s * 0.9, 1.5, stroke=1, fill=0)
            c.setLineWidth(0.7)
            c.line(s * 0.38, s * 0.18, s * 0.62, s * 0.18)
        elif k == 'mail':
            c.rect(s * 0.05, s * 0.22, s * 0.9, s * 0.55, stroke=1, fill=0)
            p = c.beginPath()
            p.moveTo(s * 0.05, s * 0.77)
            p.lineTo(s * 0.5, s * 0.48)
            p.lineTo(s * 0.95, s * 0.77)
            c.drawPath(p, stroke=1, fill=0)
        else:  # web
            c.circle(s * 0.5, s * 0.5, s * 0.4, stroke=1, fill=0)
            c.ellipse(s * 0.22, s * 0.1, s * 0.78, s * 0.9, stroke=1, fill=0)
            c.line(s * 0.1, s * 0.5, s * 0.9, s * 0.5)
        c.restoreState()


def _amount_words_fils(amount: float) -> str:
    from addons.reports.controllers.routes import _amount_in_words

    try:
        amt = abs(float(amount or 0))
    except (TypeError, ValueError):
        amt = 0.0
    whole = int(amt)
    fils = int(round((amt - whole) * 100))
    if fils == 100:
        whole += 1
        fils = 0
    # Reuse English words for whole, then QAR-style fils suffix.
    base = _amount_in_words(float(whole))
    # _amount_in_words ends with " Only" — strip and rebuild.
    if base.endswith(' Only'):
        base = base[: -len(' Only')]
    if fils:
        # "Forty Seven And Seventy Five Fils Only"
        fils_words = _amount_in_words(float(fils))
        if fils_words.endswith(' Only'):
            fils_words = fils_words[: -len(' Only')]
        return f'{base.replace("-", " ")} And {fils_words.replace("-", " ")} Fils Only'
    return f'{base.replace("-", " ")} Only'


def build_gulfnova_invoice_pdf(
    billno: Any,
    header: Dict[str, Any],
    lines: List[Dict[str, Any]],
    *,
    invoice_title: str = 'INVOICE',
    company_name: str = '',
    company_address: str = '',
    company_phone: str = '',
    company_email: str = '',
    company_tax: str = '',
    company_website: str = '',
    company_logo: str = '',
    arabic_font: str = 'Helvetica',
) -> Optional[bytes]:
    if not _RL:
        return None

    raw_title = str(invoice_title or 'INVOICE').strip().upper()
    if raw_title in ('SALES INVOICE', 'TAX INVOICE', 'INVOICE', ''):
        display_title = 'INVOICE'
    else:
        display_title = raw_title
    is_return = 'RETURN' in raw_title
    is_sales_order = display_title == 'SALES ORDER'
    amt_decimals = 3 if is_sales_order else 2

    customer_code = str(header.get('customercode') or '').strip()
    customer_name = str(header.get('customername') or header.get('partyname') or '').strip()
    customer_address = str(header.get('address') or '').strip()
    bill_date = str(header.get('billdate') or '')[:10]
    try:
        from addons.reports.controllers.routes import _format_pdf_date
        bill_date_display = _format_pdf_date(header.get('billdate'))
    except Exception:
        bill_date_display = bill_date
    bill_time = str(header.get('billtime') or '').strip()
    remarks = str(header.get('remarks') or '').strip()
    created_by = str(header.get('createdby') or '').strip()
    try:
        from nexa_http import session
        prepared_by = str(session.get('user') or created_by or '').strip()
    except Exception:
        prepared_by = created_by

    styles = getSampleStyleSheet()

    def S(name, **kw):
        kw.setdefault('textColor', TEXT)
        return ParagraphStyle(name, parent=styles['Normal'], **kw)

    N8 = S('gn8', fontSize=8, leading=10)
    N8M = S('gn8m', fontSize=8, leading=10, textColor=MUTED)
    N8R = S('gn8r', fontSize=8, leading=10, alignment=TA_RIGHT)
    N8C = S('gn8c', fontSize=8, leading=10, alignment=TA_CENTER)
    N8RB = S('gn8rb', fontSize=8, leading=10, alignment=TA_RIGHT, fontName='Helvetica-Bold')
    N8RRED = S('gn8rr', fontSize=8, leading=10, alignment=TA_RIGHT, textColor=RED)
    N9B = S('gn9b', fontSize=9, leading=11, fontName='Helvetica-Bold')
    WHT = S('gnw', fontSize=8.5, leading=11, alignment=TA_CENTER, textColor=colors.white, fontName='Helvetica-Bold')
    WHT_L = S('gnwl', fontSize=9, leading=11, textColor=colors.white, fontName='Helvetica-Bold')
    TITLE = S('gnt', fontSize=20, leading=24, alignment=TA_RIGHT, textColor=NAVY, fontName='Helvetica-Bold')
    CO1 = S('gnco1', fontSize=13, leading=16, textColor=colors.black, fontName='Helvetica-Bold')
    CO2 = S('gnco2', fontSize=13, leading=16, textColor=RED, fontName='Helvetica-Bold')
    CONTACT = S('gnc', fontSize=8, leading=11, textColor=TEXT)
    META_L = S('gnml', fontSize=8, leading=10, textColor=colors.HexColor('#333333'), fontName='Helvetica-Bold')
    META_V = S('gnmv', fontSize=8, leading=10, textColor=TEXT)

    # Lines
    subtotal = 0.0
    line_disc_total = 0.0
    pt_rows: List[List[Any]] = [[
        Paragraph(f'<b>{c}</b>', WHT)
        for c in ['Sl.No.', 'Item Code', 'Description', 'Qty', 'Unit', 'Unit Price', 'Discount', 'Amount']
    ]]
    for idx, row in enumerate(lines or [], 1):
        try:
            qty = float(row.get('quantity') or 0)
        except (TypeError, ValueError):
            qty = 0.0
        try:
            rate = float(row.get('rate') or 0)
        except (TypeError, ValueError):
            rate = 0.0
        try:
            itdisc = float(row.get('itdisc') or row.get('discount') or 0)
        except (TypeError, ValueError):
            itdisc = 0.0
        line_disc_total += abs(itdisc) if is_return else itdisc
        try:
            stored_amt = float(row.get('amount')) if row.get('amount') is not None else None
        except (TypeError, ValueError):
            stored_amt = None
        if stored_amt is not None and abs(stored_amt) > 1e-9:
            amount = stored_amt
        elif qty < 0 or is_return:
            amount = -(abs(qty) * rate - abs(itdisc))
        else:
            amount = qty * rate - itdisc
        subtotal += (abs(qty) * rate) if (is_return or qty < 0) else (qty * rate)
        print_qty = abs(qty) if is_return else qty
        print_disc = abs(itdisc) if is_return else itdisc
        print_amt = abs(amount) if is_return else amount
        item_code = str(row.get('itemcode') or '').strip()
        item_name = str(row.get('itemname') or row.get('itemdetails1') or row.get('item_name') or '').strip()
        desc = f'<b>{_xml_escape(item_name)}</b>' if item_name else ''
        # Sample shows numeric id under description — prefer barcode, else item code.
        under = str(row.get('barcode') or row.get('manufacturerid') or item_code or '').strip()
        if under:
            desc = (desc + '<br/>' if desc else '') + f'<font size="7" color="#888888">{_xml_escape(under)}</font>'
        pt_rows.append([
            Paragraph(str(row.get('slno') or idx), N8C),
            Paragraph(_xml_escape(item_code), N8C),
            Paragraph(desc or '—', N8),
            Paragraph(f'{print_qty:.{amt_decimals}f}', N8R),
            Paragraph(_xml_escape(str(row.get('unitofmeasurement') or row.get('uom') or '')), N8C),
            Paragraph(f'{rate:.3f}', N8R),
            Paragraph(f'{print_disc:.{amt_decimals}f}', N8RRED),
            Paragraph(f'{print_amt:.{amt_decimals}f}', N8RB),
        ])

    header_disc = float(header.get('discountamount') or 0)
    total_discount = header_disc if abs(header_disc) > 1e-9 else line_disc_total
    net_raw = header.get('netbillamount')
    try:
        if net_raw is not None and str(net_raw).strip() != '':
            net_amount = float(net_raw)
        else:
            net_amount = subtotal - total_discount
    except (TypeError, ValueError):
        net_amount = subtotal - total_discount
    if is_return:
        subtotal = abs(subtotal)
        total_discount = abs(total_discount)
        net_amount = abs(net_amount)

    W = 7.4 * inch
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=0.35 * inch,
        bottomMargin=2.55 * inch,
        leftMargin=0.45 * inch,
        rightMargin=0.45 * inch,
    )

    # Company name split
    name = str(company_name or 'Company').strip()
    parts = name.split()
    if len(parts) >= 2:
        mid = max(1, (len(parts) + 1) // 2)
        name_top = ' '.join(parts[:mid]).upper()
        name_bot = ' '.join(parts[mid:]).upper()
    else:
        name_top = name.upper()
        name_bot = ''

    logo_cell: Any = Spacer(1, 1)
    if company_logo and Image is not None:
        try:
            logo_cell = Image(company_logo, width=0.95 * inch, height=0.95 * inch, kind='proportional')
        except Exception:
            logo_cell = Spacer(1, 1)

    contact_rows: List[List[Any]] = []
    addr = company_address.replace(',', ', ').replace(',  ', ', ') if company_address else ''
    for kind, val in (
        ('pin', addr),
        ('phone', f'Tel: {company_phone}' if company_phone else ''),
        ('mail', company_email),
        ('web', company_website),
    ):
        v = str(val or '').strip()
        if not v:
            continue
        contact_rows.append([_ContactIcon(kind, 9), Paragraph(_xml_escape(v), CONTACT)])
    if company_tax:
        contact_rows.append(['', Paragraph(f'Tax / TRN: {_xml_escape(company_tax)}', N8M)])

    name_bits: List[Any] = [Paragraph(_xml_escape(name_top), CO1)]
    if name_bot:
        name_bits.append(Paragraph(_xml_escape(name_bot), CO2))
    name_bits.append(Spacer(1, 4))
    if contact_rows:
        ct = Table(contact_rows, colWidths=[0.18 * inch, 2.85 * inch])
        ct.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 2),
            ('TOPPADDING', (0, 0), (-1, -1), 1),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ]))
        name_bits.append(ct)

    co_block = name_bits
    # Logo | thin vertical divider | company block
    vdiv = Table([['']], colWidths=[1.2], rowHeights=[1.2 * inch])
    vdiv.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#b0b0b0')),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    left = Table(
        [[logo_cell, vdiv, co_block]],
        colWidths=[1.05 * inch, 0.08 * inch, 3.15 * inch],
    )
    left.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (0, 0), 0),
        ('RIGHTPADDING', (0, 0), (0, 0), 6),
        ('LEFTPADDING', (1, 0), (1, 0), 0),
        ('RIGHTPADDING', (1, 0), (1, 0), 8),
        ('LEFTPADDING', (2, 0), (2, 0), 0),
        ('RIGHTPADDING', (2, 0), (2, 0), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))

    meta_rows = [
        [Paragraph('Invoice No.', META_L), Paragraph(f':  {_xml_escape(str(billno))}', META_V)],
        [Paragraph('Invoice Date', META_L), Paragraph(f':  {_xml_escape(bill_date_display)}', META_V)],
    ]
    if bill_time:
        meta_rows.append([Paragraph('Time', META_L), Paragraph(f':  {_xml_escape(bill_time)}', META_V)])
    if created_by:
        meta_rows.append([Paragraph('Created By', META_L), Paragraph(f':  {_xml_escape(created_by)}', META_V)])
    if prepared_by:
        meta_rows.append([Paragraph('Prepared By', META_L), Paragraph(f':  {_xml_escape(prepared_by)}', META_V)])
    meta_w = 2.55 * inch
    meta_tbl = Table(meta_rows, colWidths=[1.05 * inch, 1.5 * inch])
    meta_tbl.setStyle(TableStyle([
        ('LINEBELOW', (0, 0), (-1, -1), 0.45, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('BACKGROUND', (0, 0), (-1, -1), colors.white),
    ]))
    right_w = meta_w
    title_rule = _InvoiceTitleRule(display_title, width=right_w, font_size=22)
    right = Table(
        [[title_rule], [Spacer(1, 8)], [meta_tbl]],
        colWidths=[right_w],
    )
    right.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))

    hdr = Table([[left, right]], colWidths=[W - right_w - 0.1 * inch, right_w], hAlign='LEFT')
    hdr.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
    ]))

    rule = Table([['']], colWidths=[W], rowHeights=[2.8], hAlign='LEFT')
    rule.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), NAVY)]))

    # BILL TO ribbon (slanted) + customer box
    ribbon = _BillToRibbon()
    bill_bits: List[Any] = []
    if customer_name:
        bill_bits.append(Paragraph(f'<b>{_xml_escape(customer_name)}</b>', N9B))
    if customer_code:
        bill_bits.append(Paragraph(f'Code: {_xml_escape(customer_code)}', N8))
    if customer_address:
        bill_bits.append(Paragraph(_xml_escape(customer_address), N8))
    if not bill_bits:
        bill_bits.append(Paragraph('—', N8))
    bill_box = Table([[bill_bits]], colWidths=[W], hAlign='LEFT')
    bill_box.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.7, BORDER),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('BACKGROUND', (0, 0), (-1, -1), colors.white),
    ]))

    col_w = [0.45 * inch, 0.75 * inch, 2.55 * inch, 0.55 * inch, 0.5 * inch, 0.85 * inch, 0.75 * inch, 1.0 * inch]
    lines_tbl = Table(pt_rows, repeatRows=1, colWidths=col_w, hAlign='LEFT')
    lines_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('BOX', (0, 0), (-1, -1), 0.5, BORDER),
        ('LINEBELOW', (0, 0), (-1, -2), 0.4, BORDER),
        ('LINEBELOW', (0, -1), (-1, -1), 0.5, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
    ]))

    elements: List[Any] = [
        hdr,
        Spacer(1, 8),
        rule,
        Spacer(1, 10),
        ribbon,
        Spacer(1, 4),
        bill_box,
        Spacer(1, 10),
        lines_tbl,
    ]

    printed_on = datetime.now().strftime('%d-%m-%Y %H:%M')
    amount_words = _amount_words_fils(net_amount)
    prepared_name = (created_by or prepared_by or '').strip()
    prepared_date = (bill_date_display or '').strip()

    def _draw_footer(canv, pdf_doc):
        x_left = pdf_doc.leftMargin
        x_right = pdf_doc.pagesize[0] - pdf_doc.rightMargin
        usable_w = x_right - x_left
        gap = 0.12 * inch
        box_w = (usable_w - 2 * gap) / 3.0
        box_h = 1.05 * inch
        box_y = 0.32 * inch
        totals_y = box_y + box_h + 0.14 * inch
        sum_w = 2.35 * inch
        sum_h = 0.95 * inch
        sum_x = x_left + usable_w - sum_w
        words_x = x_left + 10

        page_count = getattr(canv, '_cashbill_page_count', None)
        page_no = getattr(canv, '_pageNumber', pdf_doc.page)
        is_last = page_count is None or page_no == page_count

        canv.saveState()
        if is_last:
            # Red accent bar + amount in words
            canv.setFillColor(RED)
            canv.rect(x_left, totals_y + 8, 3.5, sum_h - 14, stroke=0, fill=1)
            canv.setFillColor(NAVY)
            canv.setFont('Helvetica-Bold', 8)
            canv.drawString(words_x, totals_y + sum_h - 14, 'Amount in Words:')
            canv.setFillColor(TEXT)
            canv.setFont('Helvetica-Bold', 10)
            words = amount_words
            wy = totals_y + sum_h - 30
            max_chars = 42
            while words and wy > totals_y + 8:
                chunk = words[:max_chars]
                if len(words) > max_chars:
                    sp = chunk.rfind(' ')
                    if sp > 12:
                        chunk = chunk[:sp]
                canv.drawString(words_x, wy, chunk)
                words = words[len(chunk):].lstrip()
                wy -= 12
            if remarks:
                canv.setFillColor(MUTED)
                canv.setFont('Helvetica', 7.5)
                canv.drawString(words_x, totals_y + 10, f'Notes: {remarks.replace(chr(10), " ")[:55]}')

            # Totals box
            row_h = sum_h / 3.0
            canv.setStrokeColor(BORDER)
            canv.setLineWidth(0.8)
            canv.setFillColor(colors.white)
            canv.rect(sum_x, totals_y, sum_w, sum_h, stroke=1, fill=1)
            rows = (
                ('Sub Total', f'{subtotal:,.{amt_decimals}f}', False),
                ('Discount', f'{total_discount:,.{amt_decimals}f}', False),
                ('GRAND TOTAL', f'{net_amount:,.{amt_decimals}f}', True),
            )
            for i, (label, value, is_gt) in enumerate(rows):
                ry = totals_y + sum_h - (i + 1) * row_h
                if is_gt:
                    canv.setFillColor(RED)
                    canv.rect(sum_x, ry, sum_w, row_h, stroke=0, fill=1)
                    canv.setFillColor(colors.white)
                    canv.setFont('Helvetica-Bold', 9)
                else:
                    canv.setStrokeColor(BORDER)
                    canv.setLineWidth(0.35)
                    canv.line(sum_x + 4, ry, sum_x + sum_w - 4, ry)
                    canv.setFillColor(MUTED)
                    canv.setFont('Helvetica', 8.5)
                ty = ry + row_h * 0.32
                canv.drawString(sum_x + 8, ty, label)
                if is_gt:
                    canv.setFillColor(colors.white)
                    font = ('Helvetica-Bold', 9)
                else:
                    canv.setFillColor(TEXT)
                    font = ('Helvetica', 8.5)
                canv.setFont(*font)
                vw = canv.stringWidth(value, *font)
                canv.drawString(sum_x + sum_w - 8 - vw, ty, value)
            canv.setStrokeColor(BORDER)
            canv.setLineWidth(0.8)
            canv.rect(sum_x, totals_y, sum_w, sum_h, stroke=1, fill=0)

        # Signature boxes every page
        titles = ('Prepared By', 'Received By', 'Authorized Signatory')
        extras = ('', '', '(Company Seal)')
        name_fills = (prepared_name, '', '')
        date_fills = (prepared_date, '', '')
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
            canv.line(bx + 8, box_y + box_h - 36, bx + box_w - 8, box_y + box_h - 36)
            canv.setFillColor(MUTED)
            canv.setFont('Helvetica', 7.5)
            nm, dt = name_fills[i], date_fills[i]
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

        canv.setFillColor(MUTED)
        canv.setFont('Helvetica', 7)
        canv.drawString(x_left, 0.12 * inch, f'Page {int(getattr(canv, "_pageNumber", pdf_doc.page) or 1)}')
        right_txt = f'Printed On: {printed_on}'
        canv.drawString(x_right - canv.stringWidth(right_txt, 'Helvetica', 7), 0.12 * inch, right_txt)
        canv.restoreState()

    class _PageCanvas(rl_canvas.Canvas):
        def __init__(self, *args, **kwargs):
            rl_canvas.Canvas.__init__(self, *args, **kwargs)
            self._saved_page_states: List[Dict[str, Any]] = []

        def showPage(self):  # type: ignore[override]
            self._saved_page_states.append(dict(self.__dict__))
            self._startPage()

        def save(self):  # type: ignore[override]
            page_count = len(self._saved_page_states)
            for state in self._saved_page_states:
                self.__dict__.update(state)
                self._cashbill_page_count = page_count
                _draw_footer(self, doc)
                rl_canvas.Canvas.showPage(self)
            rl_canvas.Canvas.save(self)

    doc.build(elements, canvasmaker=_PageCanvas)
    return buffer.getvalue()
