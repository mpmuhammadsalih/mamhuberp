"""All-transactions Summary / Details reports for mobile Reports hub."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from io import BytesIO
from typing import Any

logger = logging.getLogger(__name__)

# Canonical type keys used by filters + details rows.
TX_TYPES: list[tuple[str, str]] = [
    ("sales_invoice", "Sales Invoice"),
    ("sales_return", "Sales Return"),
    ("sales_order", "Sales Order"),
    ("purchase_order", "Purchase Order"),
    ("grn", "GRN / Goods Received"),
    ("purchase_return", "Purchase Return"),
    ("stock_adjustment", "Stock Adjustment"),
    ("stock_transfer", "Stock Transfer"),
    ("cash_payment", "Cash Payment Voucher"),
    ("journal", "Journal Entry"),
]

_TX_LABEL = {k: v for k, v in TX_TYPES}


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


def _period_label(df: str, dt: str) -> str:
    if df == dt:
        return df
    return f"{df} → {dt}"


def _selected_types(raw: str) -> set[str] | None:
    """None = all types; else subset of known keys."""
    parts = [p.strip().lower() for p in str(raw or "").split(",") if p.strip()]
    if not parts or "all" in parts:
        return None
    known = {k for k, _ in TX_TYPES}
    sel = {p for p in parts if p in known}
    return sel or None


def transaction_type_options() -> list[dict[str, str]]:
    return [{"code": k, "label": v} for k, v in TX_TYPES]


def _summary_counts_from_documents(
    *,
    date_from: str,
    date_to: str,
    keys: set[str],
) -> dict[str, tuple[int, float]]:
    """Doc counts + header totals for types not covered accurately by business summary."""
    out: dict[str, tuple[int, float]] = {}
    if not keys:
        return out

    # Prefer header totals (one amount per voucher) over summing every line.
    if "cash_payment" in keys:
        try:
            from db import get_gl_voucher_reversal_no
            from mobile_backend.services import cash_payment_voucher_service as cpv

            listed = cpv.list_vouchers(search="", status="all", limit=500) or {}
            docs = 0
            total = 0.0
            for inv in listed.get("vouchers") or []:
                st = str(inv.get("status") or "").strip().upper()
                if st == "REVERSED":
                    continue
                ddate = str(inv.get("voucher_date") or "")[:10]
                if not _in_date_range(ddate, date_from, date_to):
                    continue
                # Already reversed in GL (e.g. petrol CPV reversed before CPV status sync).
                glv = str(inv.get("gl_voucher_no") or "").strip()
                if glv and get_gl_voucher_reversal_no(glv):
                    continue
                docs += 1
                total += _to_float(inv.get("total_amount"))
            out["cash_payment"] = (docs, total)
        except Exception:
            logger.debug("summary cash_payment failed", exc_info=True)

    if "journal" in keys:
        try:
            from mobile_backend.services import journal_entry_service as je

            listed = je.list_journals(
                search="",
                status="all",
                date_from=date_from,
                date_to=date_to,
                limit=500,
            ) or {}
            docs = 0
            total = 0.0
            for inv in listed.get("vouchers") or []:
                docs += 1
                total += _to_float(inv.get("total_debit") or inv.get("total_credit"))
            out["journal"] = (docs, total)
        except Exception:
            logger.debug("summary journal failed", exc_info=True)

    if "sales_order" in keys:
        try:
            from mobile_backend.services import sales_order_service as so

            listed = so.list_orders(
                search="",
                limit=500,
                date_from=date_from,
                date_to=date_to,
                status_tab="all",
            ) or []
            docs = 0
            total = 0.0
            for inv in listed:
                docs += 1
                total += _to_float(
                    inv.get("net_amount")
                    or inv.get("netamount")
                    or inv.get("total")
                    or inv.get("amount")
                )
            out["sales_order"] = (docs, total)
        except Exception:
            logger.debug("summary sales_order failed", exc_info=True)

    if "stock_transfer" in keys:
        try:
            from addons.reports.controllers import routes as erp_reports
            from mobile_backend.services.stock_transfer_service import _erp_session_scope

            with _erp_session_scope():
                raw_rows = erp_reports._get_store_transfer_detail_rows(
                    date_from=date_from, date_to=date_to
                ) or []
            by_doc: dict[str, float] = {}
            for raw in raw_rows:
                r = dict(raw or {})
                dno = str(
                    r.get("transferno") or r.get("transfer_no") or r.get("stno") or ""
                ).strip()
                if not dno:
                    continue
                qty = _to_float(r.get("transferqty") or r.get("quantity") or r.get("qty"))
                rate = _to_float(r.get("rate") or r.get("cost") or r.get("unitcost"))
                line_amt = _to_float(r.get("amount") or r.get("lineamount"))
                if line_amt <= 0 and rate > 0 and qty > 0:
                    line_amt = rate * qty
                # Do not treat quantity as money when cost is unknown.
                by_doc[dno] = by_doc.get(dno, 0.0) + line_amt
            out["stock_transfer"] = (len(by_doc), sum(by_doc.values()))
        except Exception:
            logger.debug("summary stock_transfer failed", exc_info=True)

    # Remaining keys: aggregate unique docs from item-wise details (header-safe).
    remaining = {k for k in keys if k not in out}
    if remaining:
        try:
            details = get_transaction_details(
                date_from=date_from,
                date_to=date_to,
                transaction_types=",".join(sorted(remaining)),
                limit=1000,
                search="",
            )
            by_type: dict[str, dict[str, float]] = {}
            for row in details.get("rows") or []:
                key = str(row.get("transaction_type") or "").strip().lower()
                if key not in remaining:
                    continue
                dno = str(row.get("doc_no") or "").strip()
                if not dno:
                    continue
                bucket = by_type.setdefault(key, {})
                # Keep max line sum per doc when lines are item-wise (avoid double-count
                # only matters for journals — those are handled above).
                bucket[dno] = bucket.get(dno, 0.0) + _to_float(row.get("amount"))
            for key, docs_map in by_type.items():
                out[key] = (len(docs_map), float(sum(docs_map.values())))
        except Exception:
            logger.debug("summary remaining from details failed", exc_info=True)

    return out


def get_transaction_summary(
    *,
    date_from: str = "",
    date_to: str = "",
    transaction_types: str = "",
) -> dict[str, Any]:
    """Counts/amounts by transaction type for the period (business summary + extras)."""
    from mobile_backend.services import business_summary_service as bss

    df, dt = _default_range(date_from, date_to)
    sel = _selected_types(transaction_types)

    payload = bss.get_business_summary(date_from=df, date_to=dt) or {}
    kpis = payload.get("kpis") or []
    kpi_map: dict[str, float] = {}
    for k in kpis:
        if isinstance(k, dict) and k.get("id"):
            kpi_map[str(k["id"])] = _to_float(k.get("value"))

    # Map business-summary rows → our canonical keys.
    bs_rows = list(payload.get("transaction_summary") or [])
    mapped: dict[str, dict[str, Any]] = {}

    def _put(key: str, count: int, amount: float) -> None:
        label = _TX_LABEL.get(key, key)
        prev = mapped.get(key)
        if prev:
            prev["count"] = int(prev.get("count") or 0) + int(count or 0)
            prev["amount"] = round(_to_float(prev.get("amount")) + _to_float(amount), 2)
        else:
            mapped[key] = {
                "transaction_type": key,
                "transaction": label,
                "count": int(count or 0),
                "amount": round(_to_float(amount), 2),
            }

    # Business-summary labels that map 1:1 to document types.
    # Do NOT map "Goods Issue" → stock_transfer (ITEMJOURNAL outbound ≠ store transfers)
    # or "Expenses" → cash_payment (P&L expenses ≠ CPV vouchers).
    name_to_key = {
        "sales": "sales_invoice",
        "sales return": "sales_return",
        "purchase (grn)": "grn",
        "purchase order": "purchase_order",
        "purchase return": "purchase_return",
        "stock adjustment": "stock_adjustment",
    }
    for raw in bs_rows:
        r = dict(raw or {})
        name = str(r.get("transaction") or "").strip().lower()
        key = name_to_key.get(name)
        if not key:
            continue
        _put(key, int(r.get("count") or 0), _to_float(r.get("amount")))

    # Split sales into cash/credit when KPIs available (shown as related totals).
    cash_sales = round(_to_float(kpi_map.get("cash_sales")), 2)
    credit_sales = round(_to_float(kpi_map.get("credit_sales")), 2)

    # Types that must come from real document lists (not BS KPI proxies).
    doc_backed = {"sales_order", "stock_transfer", "cash_payment", "journal"}
    if sel:
        doc_backed &= sel

    bs_empty = not any(
        int(r.get("count") or 0) > 0 or _to_float(r.get("amount")) for r in mapped.values()
    )
    enrich_keys = set(doc_backed)
    if bs_empty:
        enrich_keys = set(sel) if sel else {k for k, _ in TX_TYPES}

    if enrich_keys:
        try:
            from_docs = _summary_counts_from_documents(
                date_from=df,
                date_to=dt,
                keys=enrich_keys,
            )
            for key, (count, amount) in from_docs.items():
                mapped[key] = {
                    "transaction_type": key,
                    "transaction": _TX_LABEL.get(key, key),
                    "count": int(count),
                    "amount": round(_to_float(amount), 2),
                }
        except Exception:
            logger.debug("transaction summary enrich from documents failed", exc_info=True)

    rows = list(mapped.values())
    if sel:
        rows = [r for r in rows if r.get("transaction_type") in sel]
    rows = [
        r
        for r in rows
        if int(r.get("count") or 0) > 0 or abs(_to_float(r.get("amount"))) > 0.005
    ]
    # Stable order by TX_TYPES
    order = {k: i for i, (k, _) in enumerate(TX_TYPES)}
    rows.sort(key=lambda r: order.get(str(r.get("transaction_type")), 99))

    total_count = sum(int(r.get("count") or 0) for r in rows)
    total_amount = round(sum(_to_float(r.get("amount")) for r in rows), 2)
    denom = total_amount or 1.0
    for r in rows:
        r["percentage"] = round(_to_float(r.get("amount")) / denom * 100, 1)

    return {
        "date_from": df,
        "date_to": dt,
        "period_label": _period_label(df, dt),
        "branch_name": str(payload.get("branch_name") or payload.get("location_name") or "").strip(),
        "transaction_types": sorted(sel) if sel else ["all"],
        "type_options": transaction_type_options(),
        "cash_sales": cash_sales,
        "credit_sales": credit_sales,
        "rows": rows,
        "summary": {
            "total_count": total_count,
            "total_amount": total_amount,
            "type_count": len(rows),
        },
    }


def _in_date_range(doc_date: str, df: str, dt: str) -> bool:
    d = str(doc_date or "").strip()[:10]
    if not d:
        return True
    if df and d < df:
        return False
    if dt and d > dt:
        return False
    return True


def _match_search(hay: str, q: str) -> bool:
    if not q:
        return True
    return q in (hay or "").upper()


def _fmt_doc_date(v: Any) -> str:
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d")
    return str(v or "")[:10]


def _item_row(
    *,
    tx_type: str,
    doc_no: Any,
    doc_date: Any,
    party: Any = "",
    item_code: Any = "",
    item_name: Any = "",
    uom: Any = "",
    qty: Any = 0,
    rate: Any = 0,
    amount: Any = 0,
    status: Any = "",
    billing_type: Any = "",
    ref: Any = "",
    slno: Any = "",
) -> dict[str, Any]:
    bt = str(billing_type or "").strip().upper()
    if bt in ("R",) or bt.startswith("R"):
        bt = "CREDIT"
    elif bt in ("C",) or bt.startswith("C"):
        bt = "CASH"
    return {
        "transaction_type": tx_type,
        "transaction": _TX_LABEL.get(tx_type, tx_type),
        "doc_no": str(doc_no or "").strip(),
        "doc_date": _fmt_doc_date(doc_date),
        "party_name": str(party or "").strip(),
        "item_code": str(item_code or "").strip(),
        "item_name": str(item_name or "").strip(),
        "uom": str(uom or "").strip(),
        "qty": round(_to_float(qty), 3),
        "rate": round(_to_float(rate), 4),
        "amount": round(_to_float(amount), 2),
        "status": str(status or "").strip(),
        "billing_type": bt,
        "reference": str(ref or "").strip(),
        "slno": str(slno or "").strip(),
    }


def get_transaction_details(
    *,
    date_from: str = "",
    date_to: str = "",
    transaction_types: str = "",
    search: str = "",
    limit: int = 300,
) -> dict[str, Any]:
    """Item-wise lines across sales / purchase / stock documents."""
    from addons.reports.controllers import routes as erp_reports
    from mobile_backend.services import sales_order_service as so
    from mobile_backend.services import stock_adjustment_service as sa
    from mobile_backend.services.stock_transfer_service import _erp_session_scope

    df, dt = _default_range(date_from, date_to)
    sel = _selected_types(transaction_types)
    q = (search or "").strip().upper()
    lim = max(1, min(int(limit or 300), 1000))
    want = lambda key: sel is None or key in sel
    rows: list[dict[str, Any]] = []

    def accept(row: dict[str, Any]) -> bool:
        if not _in_date_range(str(row.get("doc_date") or ""), df, dt):
            return False
        if not q:
            return True
        hay = " ".join(
            [
                str(row.get("doc_no") or ""),
                str(row.get("party_name") or ""),
                str(row.get("item_code") or ""),
                str(row.get("item_name") or ""),
                str(row.get("transaction") or ""),
                str(row.get("status") or ""),
                str(row.get("billing_type") or ""),
                str(row.get("reference") or ""),
            ]
        ).upper()
        return q in hay

    with _erp_session_scope():
        if want("sales_invoice"):
            try:
                for raw in erp_reports._get_sales_detail_rows(
                    date_from=df, date_to=dt, txn_kind="sale"
                ) or []:
                    r = dict(raw or {})
                    row = _item_row(
                        tx_type="sales_invoice",
                        doc_no=r.get("billno"),
                        doc_date=r.get("billdate"),
                        party=r.get("customername"),
                        item_code=r.get("itemcode"),
                        item_name=r.get("itemname"),
                        uom=r.get("uom"),
                        qty=r.get("quantity"),
                        rate=r.get("rate"),
                        amount=r.get("lineamount") or r.get("amount") or r.get("netamount"),
                        status=r.get("billstatus"),
                        billing_type=r.get("billtype"),
                        ref=r.get("orderno"),
                        slno=r.get("slno"),
                    )
                    if accept(row):
                        rows.append(row)
            except Exception:
                logger.warning("tx itemwise sales_invoice failed", exc_info=True)

        if want("sales_return"):
            try:
                for raw in erp_reports._get_sales_detail_rows(
                    date_from=df, date_to=dt, txn_kind="salesreturn"
                ) or []:
                    r = dict(raw or {})
                    row = _item_row(
                        tx_type="sales_return",
                        doc_no=r.get("billno"),
                        doc_date=r.get("billdate"),
                        party=r.get("customername"),
                        item_code=r.get("itemcode"),
                        item_name=r.get("itemname"),
                        uom=r.get("uom"),
                        qty=r.get("quantity"),
                        rate=r.get("rate"),
                        amount=r.get("lineamount") or r.get("amount") or r.get("netamount"),
                        status=r.get("billstatus"),
                        billing_type=r.get("billtype"),
                        ref=r.get("orderno"),
                        slno=r.get("slno"),
                    )
                    if accept(row):
                        rows.append(row)
            except Exception:
                logger.warning("tx itemwise sales_return failed", exc_info=True)

        if want("purchase_order"):
            try:
                for raw in erp_reports._get_purchase_detail_rows(date_from=df, date_to=dt) or []:
                    r = dict(raw or {})
                    row = _item_row(
                        tx_type="purchase_order",
                        doc_no=r.get("lpono"),
                        doc_date=r.get("lpodate"),
                        party=r.get("suppliername") or r.get("suppliercode"),
                        item_code=r.get("itemcode"),
                        item_name=r.get("itemname"),
                        uom=r.get("uom"),
                        qty=r.get("quantity"),
                        rate=r.get("rate"),
                        amount=r.get("amount"),
                        status=r.get("approval_status"),
                        ref=r.get("suppliercode"),
                        slno=r.get("slno"),
                    )
                    if accept(row):
                        rows.append(row)
            except Exception:
                logger.debug("tx itemwise purchase_order failed", exc_info=True)

        if want("grn"):
            try:
                for raw in erp_reports._get_grn_detail_rows(date_from=df, date_to=dt) or []:
                    r = dict(raw or {})
                    row = _item_row(
                        tx_type="grn",
                        doc_no=r.get("receiptno"),
                        doc_date=r.get("receiptdate"),
                        party=r.get("suppliername") or r.get("suppliercode"),
                        item_code=r.get("itemcode"),
                        item_name=r.get("itemname"),
                        uom=r.get("uom"),
                        qty=r.get("quantity"),
                        rate=r.get("rate"),
                        amount=r.get("amount"),
                        status="POSTED",
                        ref=r.get("lpono") or r.get("invoiceno"),
                        slno=r.get("slno"),
                    )
                    if accept(row):
                        rows.append(row)
            except Exception:
                logger.debug("tx itemwise grn failed", exc_info=True)

        if want("purchase_return"):
            try:
                for raw in erp_reports._get_purchase_return_detail_rows(
                    date_from=df, date_to=dt
                ) or []:
                    r = dict(raw or {})
                    row = _item_row(
                        tx_type="purchase_return",
                        doc_no=r.get("goodsreturnno") or r.get("returnno"),
                        doc_date=r.get("returndate"),
                        party=r.get("suppliername") or r.get("suppliercode"),
                        item_code=r.get("itemcode"),
                        item_name=r.get("itemname"),
                        uom=r.get("uom"),
                        qty=r.get("quantity"),
                        rate=r.get("rate"),
                        amount=r.get("amount") or r.get("lineamount"),
                        status=r.get("returntype"),
                        ref=r.get("receiptno"),
                        slno=r.get("slno") or r.get("lineno"),
                    )
                    if accept(row):
                        rows.append(row)
            except Exception:
                logger.debug("tx itemwise purchase_return failed", exc_info=True)

        if want("stock_transfer"):
            try:
                for raw in erp_reports._get_store_transfer_detail_rows(
                    date_from=df, date_to=dt
                ) or []:
                    r = dict(raw or {})
                    party = f"{r.get('from_store') or r.get('fromstore') or ''} → {r.get('to_store') or r.get('tostore') or ''}".strip(
                        " →"
                    )
                    row = _item_row(
                        tx_type="stock_transfer",
                        doc_no=r.get("transferno") or r.get("transfer_no") or r.get("stno"),
                        doc_date=r.get("transferdate") or r.get("transfer_date") or r.get("stdate"),
                        party=party,
                        item_code=r.get("itemcode"),
                        item_name=r.get("itemname"),
                        uom=r.get("uom"),
                        qty=r.get("transferqty") or r.get("quantity") or r.get("qty"),
                        rate=r.get("rate") or r.get("cost") or 0,
                        amount=(
                            _to_float(r.get("amount") or r.get("lineamount"))
                            or (
                                _to_float(r.get("rate") or r.get("cost"))
                                * _to_float(r.get("transferqty") or r.get("quantity") or r.get("qty"))
                            )
                        ),
                        status=r.get("status"),
                        slno=r.get("slno") or r.get("lineno"),
                    )
                    if accept(row):
                        rows.append(row)
            except Exception:
                logger.debug("tx itemwise stock_transfer failed", exc_info=True)

    # Sales orders / stock adjustments: expand listed docs into item lines.
    if want("sales_order"):
        try:
            for inv in so.list_orders(
                search=search, limit=min(lim, 80), date_from=df, date_to=dt, status_tab="all"
            ) or []:
                doc_no = inv.get("billno") or inv.get("orderno")
                detail = so.get_order_detail(doc_no) if doc_no else None
                if not detail:
                    continue
                hdr = detail if "lines" in detail else detail.get("header") or detail
                lines = detail.get("lines") or detail.get("items") or []
                party = (
                    (hdr or {}).get("customer_name")
                    or (hdr or {}).get("customername")
                    or inv.get("customer_name")
                )
                ddate = (
                    (hdr or {}).get("billdate")
                    or (hdr or {}).get("orderdate")
                    or inv.get("billdate")
                )
                status = (hdr or {}).get("status") or inv.get("status")
                billing = (hdr or {}).get("billing_type") or inv.get("billing_type")
                for ln in lines:
                    l = dict(ln or {})
                    row = _item_row(
                        tx_type="sales_order",
                        doc_no=doc_no,
                        doc_date=ddate,
                        party=party,
                        item_code=l.get("item_code") or l.get("itemcode"),
                        item_name=l.get("item_name") or l.get("itemname"),
                        uom=l.get("uom") or l.get("unit"),
                        qty=l.get("qty") or l.get("quantity"),
                        rate=l.get("rate"),
                        amount=l.get("amount") or l.get("line_amount") or l.get("net_amount"),
                        status=status,
                        billing_type=billing,
                        slno=l.get("slno") or l.get("line_no"),
                    )
                    if accept(row):
                        rows.append(row)
        except Exception:
            logger.debug("tx itemwise sales_order failed", exc_info=True)

    if want("stock_adjustment"):
        try:
            data = sa.list_adjustments(search=search, page=1, page_size=min(lim, 80)) or {}
            for inv in data.get("adjustments") or data.get("rows") or []:
                doc_no = inv.get("adjno") or inv.get("adj_no") or inv.get("doc_no")
                if not doc_no:
                    continue
                detail = None
                try:
                    detail = sa.get_detail(doc_no)
                except Exception:
                    detail = None
                lines = (detail or {}).get("lines") or (detail or {}).get("items") or []
                ddate = inv.get("adj_date") or inv.get("adjdate") or (detail or {}).get("adj_date")
                if not _in_date_range(str(ddate or "")[:10], df, dt):
                    continue
                party = inv.get("warehouse_name") or inv.get("store") or ""
                status = inv.get("status")
                if not lines:
                    row = _item_row(
                        tx_type="stock_adjustment",
                        doc_no=doc_no,
                        doc_date=ddate,
                        party=party,
                        amount=inv.get("stock_value") or inv.get("net_amount") or inv.get("total_amount") or 0,
                        status=status,
                        ref=inv.get("remarks"),
                    )
                    if accept(row):
                        rows.append(row)
                    continue
                for ln in lines:
                    l = dict(ln or {})
                    qty = l.get("adjust_qty") or l.get("qty") or l.get("quantity") or l.get("adj_qty")
                    rate = l.get("rate") or l.get("cost")
                    amount = l.get("amount") or l.get("line_amount")
                    if amount in (None, ""):
                        amount = _to_float(qty) * _to_float(rate)
                    row = _item_row(
                        tx_type="stock_adjustment",
                        doc_no=doc_no,
                        doc_date=ddate,
                        party=party or l.get("store") or "",
                        item_code=l.get("item_code") or l.get("itemcode"),
                        item_name=l.get("item_name") or l.get("itemname"),
                        uom=l.get("uom") or l.get("unit"),
                        qty=qty,
                        rate=rate,
                        amount=amount,
                        status=status,
                        slno=l.get("slno") or l.get("line_no"),
                    )
                    if accept(row):
                        rows.append(row)
        except Exception:
            logger.debug("tx itemwise stock_adjustment failed", exc_info=True)

    if want("cash_payment"):
        try:
            from db import get_gl_voucher_reversal_no
            from mobile_backend.services import cash_payment_voucher_service as cpv

            listed = cpv.list_vouchers(search=search, status="all", limit=min(lim, 80)) or {}
            for inv in listed.get("vouchers") or []:
                if str(inv.get("status") or "").strip().upper() == "REVERSED":
                    continue
                glv = str(inv.get("gl_voucher_no") or "").strip()
                if glv and get_gl_voucher_reversal_no(glv):
                    continue
                doc_no = inv.get("voucher_no")
                if not doc_no:
                    continue
                detail = None
                try:
                    detail = cpv.get_detail(str(doc_no))
                except Exception:
                    detail = None
                ddate = (detail or {}).get("voucher_date") or inv.get("voucher_date")
                if not _in_date_range(str(ddate or "")[:10], df, dt):
                    continue
                party = (detail or {}).get("narration") or inv.get("narration") or ""
                status = (detail or {}).get("status") or inv.get("status")
                lines = (detail or {}).get("lines") or []
                if not lines:
                    row = _item_row(
                        tx_type="cash_payment",
                        doc_no=doc_no,
                        doc_date=ddate,
                        party=party,
                        amount=inv.get("total_amount") or 0,
                        status=status,
                        ref=inv.get("reference_no"),
                    )
                    if accept(row):
                        rows.append(row)
                    continue
                for ln in lines:
                    l = dict(ln or {})
                    row = _item_row(
                        tx_type="cash_payment",
                        doc_no=doc_no,
                        doc_date=ddate,
                        party=party,
                        item_code=l.get("account_code"),
                        item_name=l.get("account_name") or l.get("description"),
                        qty=1,
                        rate=l.get("amount"),
                        amount=l.get("amount"),
                        status=status,
                        ref=l.get("description") or inv.get("reference_no"),
                        slno=l.get("line_no"),
                    )
                    if accept(row):
                        rows.append(row)
        except Exception:
            logger.debug("tx itemwise cash_payment failed", exc_info=True)

    if want("journal"):
        try:
            from mobile_backend.services import journal_entry_service as je

            listed = je.list_journals(
                search=search,
                status="all",
                date_from=df,
                date_to=dt,
                limit=min(lim, 80),
            ) or {}
            for inv in listed.get("vouchers") or []:
                doc_no = inv.get("voucher_no") or inv.get("draft_id")
                if not doc_no:
                    continue
                detail = None
                try:
                    detail = je.get_detail(str(doc_no))
                except Exception:
                    detail = None
                ddate = (detail or {}).get("voucher_date") or inv.get("voucher_date")
                if not _in_date_range(str(ddate or "")[:10], df, dt):
                    continue
                party = (detail or {}).get("narration") or inv.get("narration") or ""
                status = (detail or {}).get("status") or inv.get("status")
                lines = (detail or {}).get("lines") or []
                if not lines:
                    row = _item_row(
                        tx_type="journal",
                        doc_no=doc_no,
                        doc_date=ddate,
                        party=party,
                        amount=inv.get("total_debit") or inv.get("total_credit") or 0,
                        status=status,
                        ref=inv.get("reference_no"),
                    )
                    if accept(row):
                        rows.append(row)
                    continue
                for ln in lines:
                    l = dict(ln or {})
                    debit = _to_float(l.get("debit"))
                    credit = _to_float(l.get("credit"))
                    amount = debit if debit else credit
                    row = _item_row(
                        tx_type="journal",
                        doc_no=doc_no,
                        doc_date=ddate,
                        party=l.get("party_name") or party,
                        item_code=l.get("account_code"),
                        item_name=l.get("account_name") or l.get("remarks"),
                        qty=1,
                        rate=amount,
                        amount=amount,
                        status=status,
                        ref=l.get("remarks") or inv.get("reference_no"),
                        slno=l.get("line_no"),
                    )
                    if accept(row):
                        rows.append(row)
        except Exception:
            logger.debug("tx itemwise journal failed", exc_info=True)

    rows.sort(
        key=lambda r: (
            str(r.get("doc_date") or ""),
            str(r.get("doc_no") or ""),
            str(r.get("slno") or ""),
        ),
        reverse=True,
    )
    rows = rows[:lim]
    total_amount = round(sum(_to_float(r.get("amount")) for r in rows), 2)
    total_qty = round(sum(_to_float(r.get("qty")) for r in rows), 3)
    doc_count = len({str(r.get("doc_no") or "") for r in rows if r.get("doc_no")})

    return {
        "date_from": df,
        "date_to": dt,
        "period_label": _period_label(df, dt),
        "transaction_types": sorted(sel) if sel else ["all"],
        "type_options": transaction_type_options(),
        "search": (search or "").strip(),
        "row_kind": "itemwise",
        "rows": rows,
        "summary": {
            "row_count": len(rows),
            "doc_count": doc_count,
            "total_qty": total_qty,
            "total_amount": total_amount,
        },
    }


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
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )
    styles = getSampleStyleSheet()
    story: list[Any] = [
        Paragraph(title, styles["Heading1"]),
        Paragraph(subtitle, styles["Normal"]),
        Spacer(1, 6 * mm),
    ]
    table_data = [headers] + data
    col_w = (landscape(A4)[0] - 24 * mm) / max(len(headers), 1)
    tbl = Table(table_data, colWidths=[col_w] * len(headers), repeatRows=1)
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1565C0")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CFD8DC")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F7FA")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(tbl)
    doc.build(story)
    return buf.getvalue()


def build_transaction_summary_pdf(
    *,
    date_from: str = "",
    date_to: str = "",
    transaction_types: str = "",
) -> tuple[bytes, str]:
    data = get_transaction_summary(
        date_from=date_from,
        date_to=date_to,
        transaction_types=transaction_types,
    )
    headers = ["Transaction", "Count", "Amount", "%"]
    body = [
        [
            str(r.get("transaction") or ""),
            str(int(r.get("count") or 0)),
            f"{_to_float(r.get('amount')):,.2f}",
            f"{_to_float(r.get('percentage')):.1f}",
        ]
        for r in data.get("rows") or []
    ]
    sm = data.get("summary") or {}
    body.append(
        [
            "TOTAL",
            str(int(sm.get("total_count") or 0)),
            "",
            "100.0" if body else "0.0",
        ]
    )
    subtitle = (
        f"Period: {data.get('period_label') or ''} · "
        f"Cash {_to_float(data.get('cash_sales')):,.2f} · "
        f"Credit {_to_float(data.get('credit_sales')):,.2f}"
    )
    pdf = _pdf_table("All Transactions — Summary", subtitle, headers, body)
    stamp = str(data.get("date_to") or date.today().isoformat()).replace("-", "")
    return pdf, f"Transactions_Summary_{stamp}.pdf"


def build_transaction_details_pdf(
    *,
    date_from: str = "",
    date_to: str = "",
    transaction_types: str = "",
    search: str = "",
    limit: int = 300,
) -> tuple[bytes, str]:
    data = get_transaction_details(
        date_from=date_from,
        date_to=date_to,
        transaction_types=transaction_types,
        search=search,
        limit=limit,
    )
    headers = [
        "Date",
        "Type",
        "Doc No",
        "Item",
        "Name",
        "Qty",
        "Rate",
        "Amount",
        "Party",
    ]
    body = [
        [
            str(r.get("doc_date") or ""),
            str(r.get("transaction") or ""),
            str(r.get("doc_no") or ""),
            str(r.get("item_code") or ""),
            str(r.get("item_name") or "")[:36],
            f"{_to_float(r.get('qty')):,.3f}".rstrip("0").rstrip("."),
            f"{_to_float(r.get('rate')):,.4f}".rstrip("0").rstrip("."),
            f"{_to_float(r.get('amount')):,.2f}",
            str(r.get("party_name") or "")[:28],
        ]
        for r in data.get("rows") or []
    ]
    sm = data.get("summary") or {}
    subtitle = (
        f"Period: {data.get('period_label') or ''} · "
        f"{int(sm.get('row_count') or 0)} item lines · "
        f"{int(sm.get('doc_count') or 0)} docs · "
        f"Qty {_to_float(sm.get('total_qty')):,.3f}"
    )
    pdf = _pdf_table("All Transactions — Item-wise Details", subtitle, headers, body)
    stamp = str(data.get("date_to") or date.today().isoformat()).replace("-", "")
    return pdf, f"Transactions_Details_{stamp}.pdf"
