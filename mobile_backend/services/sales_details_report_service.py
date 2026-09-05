"""Mobile Sales Details report — same BILLHDR/BILLDTL item lines as ERP."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from io import BytesIO
from typing import Any

logger = logging.getLogger(__name__)


def _to_float(v: Any, default: float = 0.0) -> float:
    if v is None or (isinstance(v, str) and not str(v).strip()):
        return default
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def _parse_iso(s: str | None) -> date | None:
    raw = str(s or "").strip()[:10]
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


def _default_range(date_from: str, date_to: str) -> tuple[str, str]:
    d_to = _parse_iso(date_to) or date.today()
    d_from = _parse_iso(date_from) or (d_to - timedelta(days=29))
    if d_from > d_to:
        d_from, d_to = d_to, d_from
    return d_from.isoformat(), d_to.isoformat()


def _fmt_date(v: Any) -> str:
    if v is None:
        return ""
    if hasattr(v, "strftime"):
        try:
            return v.strftime("%Y-%m-%d")
        except Exception:
            pass
    return str(v)[:10]


def _fmt_time(v: Any) -> str:
    if v is None:
        return ""
    if hasattr(v, "strftime"):
        try:
            return v.strftime("%H:%M:%S")
        except Exception:
            pass
    s = str(v or "").strip()
    if " " in s and len(s) > 10:
        return s.split(" ", 1)[1][:8]
    return s[:8]


def _bill_type_label(raw: Any) -> str:
    bt = str(raw or "").strip().upper()[:1]
    if bt == "C":
        return "CASH"
    if bt == "R":
        return "CREDIT"
    if bt == "D":
        return "CARD"
    return bt or ""


def _normalize_row(raw: dict[str, Any]) -> dict[str, Any]:
    r = dict(raw or {})
    qty = _to_float(r.get("quantity"))
    rate = _to_float(r.get("rate"))
    line_disc = _to_float(r.get("linediscount"))
    line_amt = _to_float(r.get("lineamount") if r.get("lineamount") is not None else r.get("amount"))
    return {
        "billno": str(r.get("billno") or "").strip(),
        "billdate": _fmt_date(r.get("billdate")),
        "billtime": _fmt_time(r.get("billtime")),
        "billtype": str(r.get("billtype") or "").strip(),
        "billing_type": _bill_type_label(r.get("billtype")),
        "customercode": str(r.get("customercode") if r.get("customercode") is not None else "").strip(),
        "customername": str(r.get("customername") or "").strip(),
        "orderno": str(r.get("orderno") or "").strip(),
        "netbillamount": round(_to_float(r.get("netbillamount")), 2),
        "hdr_discount": round(_to_float(r.get("hdr_discount")), 2),
        "hdr_remarks": str(r.get("hdr_remarks") or "").strip(),
        "salesmancode": str(r.get("salesmancode") if r.get("salesmancode") is not None else "").strip(),
        "countercode": str(r.get("countercode") if r.get("countercode") is not None else "").strip(),
        "billstatus": str(r.get("billstatus") or "").strip(),
        "slno": str(r.get("slno") if r.get("slno") is not None else "").strip(),
        "itemcode": str(r.get("itemcode") or "").strip(),
        "storecode": str(r.get("storecode") or "").strip(),
        "itemname": str(r.get("itemname") or "").strip(),
        "uom": str(r.get("uom") or "").strip(),
        "quantity": round(qty, 4),
        "rate": round(rate, 4),
        "linediscount": round(line_disc, 4),
        "lineamount": round(line_amt, 4),
    }


def get_sales_details(
    *,
    date_from: str = "",
    date_to: str = "",
    bill_no: str = "",
    order_no: str = "",
    customer_code: str = "",
    bill_type: str = "",
    txn_kind: str = "all",
    item_code: str = "",
    limit: int = 500,
) -> dict[str, Any]:
    """Item-wise sales invoice lines (ERP Sales Details Report)."""
    from addons.reports.controllers import routes as erp_reports
    from mobile_backend.services.stock_transfer_service import _erp_session_scope

    df, dt = _default_range(date_from, date_to)
    lim = max(1, min(int(limit or 500), 2000))
    bn_raw = str(bill_no or "").strip()
    bill_no_i = int(bn_raw) if bn_raw.isdigit() else None
    cust_raw = str(customer_code or "").strip()
    customer_i = int(cust_raw) if cust_raw.isdigit() else None
    item_raw = str(item_code or "").strip()
    item_i = int(item_raw) if item_raw.isdigit() else None
    tk = str(txn_kind or "all").strip().lower()
    if tk not in ("all", "sale", "salesreturn"):
        tk = "all"
    bt = str(bill_type or "").strip().upper()[:1]

    with _erp_session_scope():
        raw_rows = erp_reports._get_sales_detail_rows(
            date_from=df,
            date_to=dt,
            bill_no=bill_no_i,
            customer_code=customer_i,
            bill_type=bt,
            item_code=item_i,
            txn_kind=tk,
            order_no=str(order_no or "").strip(),
        ) or []

    rows = [_normalize_row(r) for r in raw_rows]
    rows = rows[:lim]
    total_qty = round(sum(_to_float(r.get("quantity")) for r in rows), 3)
    total_line = round(sum(_to_float(r.get("lineamount")) for r in rows), 2)
    bills = {str(r.get("billno") or "") for r in rows if r.get("billno")}

    return {
        "date_from": df,
        "date_to": dt,
        "period_label": df if df == dt else f"{df} → {dt}",
        "filters": {
            "bill_no": bn_raw,
            "order_no": str(order_no or "").strip(),
            "customer_code": cust_raw,
            "bill_type": bt,
            "txn_kind": tk,
            "item_code": item_raw,
        },
        "rows": rows,
        "summary": {
            "row_count": len(rows),
            "bill_count": len(bills),
            "total_qty": total_qty,
            "total_amount": total_line,
        },
    }


def list_sales_detail_customers(*, search: str = "", limit: int = 300) -> list[dict[str, Any]]:
    from addons.reports.controllers import routes as erp_reports
    from mobile_backend.services.stock_transfer_service import _erp_session_scope

    with _erp_session_scope():
        rows = erp_reports._get_sales_detail_customer_options(
            search=(search or "").strip(), limit=max(50, min(int(limit or 300), 800))
        ) or []
    out: list[dict[str, Any]] = []
    for r in rows:
        code = str(r.get("customercode") if r.get("customercode") is not None else "").strip()
        name = str(r.get("customername") or "").strip()
        if not code:
            continue
        out.append({"code": code, "name": name, "label": f"{code} — {name}" if name else code})
    return out


def list_sales_detail_items(*, search: str = "", limit: int = 300) -> list[dict[str, Any]]:
    from addons.reports.controllers import routes as erp_reports
    from mobile_backend.services.stock_transfer_service import _erp_session_scope

    with _erp_session_scope():
        rows = erp_reports._get_sales_detail_item_options(
            search=(search or "").strip(), limit=max(50, min(int(limit or 300), 800))
        ) or []
    out: list[dict[str, Any]] = []
    for r in rows:
        code = str(r.get("itemcode") or "").strip()
        name = str(r.get("itemname") or "").strip()
        if not code:
            continue
        out.append({"code": code, "name": name, "label": f"{code} — {name}" if name else code})
    return out


def _pdf_table(title: str, subtitle: str, headers: list[str], data: list[list[str]]) -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except Exception as exc:
        raise ValueError("PDF generation failed (reportlab not available).") from exc

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=10 * mm,
        rightMargin=10 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )
    styles = getSampleStyleSheet()
    story: list[Any] = [
        Paragraph(title, styles["Heading1"]),
        Paragraph(subtitle, styles["Normal"]),
        Spacer(1, 5 * mm),
    ]
    table_data = [headers] + data
    col_w = (landscape(A4)[0] - 20 * mm) / max(len(headers), 1)
    tbl = Table(table_data, colWidths=[col_w] * len(headers), repeatRows=1)
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1565C0")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CFD8DC")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F7FA")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    story.append(tbl)
    doc.build(story)
    return buf.getvalue()


def build_sales_details_pdf(
    *,
    date_from: str = "",
    date_to: str = "",
    bill_no: str = "",
    order_no: str = "",
    customer_code: str = "",
    bill_type: str = "",
    txn_kind: str = "all",
    item_code: str = "",
    limit: int = 800,
) -> tuple[bytes, str]:
    data = get_sales_details(
        date_from=date_from,
        date_to=date_to,
        bill_no=bill_no,
        order_no=order_no,
        customer_code=customer_code,
        bill_type=bill_type,
        txn_kind=txn_kind,
        item_code=item_code,
        limit=limit,
    )
    headers = [
        "Bill No",
        "Date",
        "Type",
        "Customer",
        "Item",
        "Name",
        "Qty",
        "Rate",
        "Line Disc",
        "Line Amt",
    ]
    body = [
        [
            str(r.get("billno") or ""),
            str(r.get("billdate") or ""),
            str(r.get("billing_type") or r.get("billtype") or ""),
            str(r.get("customername") or r.get("customercode") or "")[:28],
            str(r.get("itemcode") or ""),
            str(r.get("itemname") or "")[:32],
            f"{_to_float(r.get('quantity')):,.3f}".rstrip("0").rstrip("."),
            f"{_to_float(r.get('rate')):,.4f}".rstrip("0").rstrip("."),
            f"{_to_float(r.get('linediscount')):,.2f}",
            f"{_to_float(r.get('lineamount')):,.2f}",
        ]
        for r in data.get("rows") or []
    ]
    sm = data.get("summary") or {}
    subtitle = (
        f"Period: {data.get('period_label') or ''} · "
        f"{int(sm.get('row_count') or 0)} lines · "
        f"{int(sm.get('bill_count') or 0)} bills · "
        f"Total {_to_float(sm.get('total_amount')):,.2f}"
    )
    pdf = _pdf_table("Sales Details Report", subtitle, headers, body)
    stamp = str(data.get("date_to") or date.today().isoformat()).replace("-", "")
    return pdf, f"Sales_Details_{stamp}.pdf"
