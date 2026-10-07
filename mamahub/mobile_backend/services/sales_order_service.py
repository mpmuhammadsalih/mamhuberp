"""Sales order — delegates to ERP QUATATIONBILLHDR/DTL under JWT session scope."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from mobile_backend.operation_lock import mobile_operation_lock
from mobile_backend.services.dashboard_service import _to_float
from mobile_backend.services.sales_invoice_service import (
    _default_warehouse_context,
    _location_code,
    _normalize_invoice_save_lines,
)
from mobile_backend.services.stock_transfer_service import _erp_session_scope


def _order_features() -> dict[str, bool]:
    from db import (
        get_sales_minus_billing_order_enabled,
        get_sales_orderno_mandatory_order_enabled,
        is_location_batch_tracking_enabled,
        is_location_bin_tracking_enabled,
        is_location_warehouse_enabled,
    )

    loc = _location_code()
    wh = bool(is_location_warehouse_enabled(loc))
    return {
        "warehouse_enabled": wh,
        "bin_tracking_enabled": wh and bool(is_location_bin_tracking_enabled(loc)),
        "batch_tracking_enabled": bool(is_location_batch_tracking_enabled(loc)),
        "orderno_mandatory": bool(get_sales_orderno_mandatory_order_enabled()),
        "minus_billing_enabled": bool(get_sales_minus_billing_order_enabled()),
    }


def _stamp_order_warehouse(
    header: dict[str, Any],
    lines: list[dict[str, Any]],
    *,
    required: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Ensure header warehouse_code + line STORE are filled so edit can reload them."""
    from db import get_warehouse_master_by_code, get_warehouse_master_by_id

    h = dict(header)
    out_lines = [dict(ln or {}) for ln in lines]

    wid_raw = h.get("warehouse_id")
    wid: int | None = None
    try:
        if wid_raw not in (None, ""):
            wid = int(float(str(wid_raw).strip()))
            if wid <= 0:
                wid = None
    except (TypeError, ValueError):
        wid = None

    wcode = str(h.get("warehouse_code") or "").strip()
    # Recover warehouse from first line STORE when header omitted it.
    if not wid and not wcode:
        for ln in out_lines:
            try:
                lw = int(float(str(ln.get("warehouse_id") or "").strip()))
                if lw > 0:
                    wid = lw
                    break
            except (TypeError, ValueError):
                pass
            sc = str(ln.get("store") or ln.get("warehouse_code") or "").strip()
            if sc:
                wcode = sc
                break

    wh_row = None
    if wid:
        wh_row = get_warehouse_master_by_id(wid)
    if not wh_row and wcode:
        wh_row = get_warehouse_master_by_code(wcode)
        if not wh_row:
            try:
                wh_row = get_warehouse_master_by_id(int(float(wcode)))
            except (TypeError, ValueError):
                wh_row = None

    if wh_row:
        try:
            wid = int(float(wh_row.get("warehouse_id") or wh_row.get("WAREHOUSE_ID") or wid or 0)) or wid
        except (TypeError, ValueError):
            pass
        wcode = str(
            wh_row.get("warehouse_code") or wh_row.get("WAREHOUSE_CODE") or wcode
        ).strip()
        h["warehouse_name"] = str(
            wh_row.get("warehouse_name") or wh_row.get("WAREHOUSE_NAME") or h.get("warehouse_name") or ""
        ).strip()

    if required and not wid and not wcode:
        raise ValueError("Select a warehouse.")

    if wid:
        h["warehouse_id"] = wid
    if wcode:
        h["warehouse_code"] = wcode

    for ln in out_lines:
        if wid and not ln.get("warehouse_id"):
            ln["warehouse_id"] = wid
        store = str(ln.get("store") or ln.get("warehouse_code") or "").strip()
        if not store and wcode:
            ln["store"] = wcode
            ln["warehouse_code"] = wcode
        elif store and not ln.get("warehouse_code"):
            ln["warehouse_code"] = store

    return h, out_lines


def get_order_open_context(*, peek_billno: bool = True) -> dict[str, Any]:
    from addons.document_numbering.document_numbering_db import DOC_TYPE_SALES_ORDER
    from db import get_location_info_by_dbkey, get_next_bill_no
    from mobile_backend.services.transaction_date_helper import (
        missing_setup_date_message,
        open_context as txn_open_context,
    )

    with _erp_session_scope() as username:
        loc = _location_code()
        txn = txn_open_context("sales_order", location_code=loc)
        bill_date = str(txn.get("preferred_date") or "")[:10]
        if not bill_date:
            raise ValueError(
                txn.get("transaction_date_error") or missing_setup_date_message("sales_order")
            )
        if peek_billno:
            from mobile_backend.services.sales_invoice_service import _fresh_peek_billno

            billno = _fresh_peek_billno(loc, DOC_TYPE_SALES_ORDER, for_order=True)
            reserved = False
        else:
            billno = get_next_bill_no(loc, None, doc_type=DOC_TYPE_SALES_ORDER)
            reserved = True
        info = get_location_info_by_dbkey(None) or {}
        features = _order_features()
        wh_ctx = _default_warehouse_context(username) if features["warehouse_enabled"] else {}
        return {
            "billno": billno,
            "bill_date": bill_date,
            "bill_date_from": str(txn.get("open_date_from") or bill_date)[:10],
            "bill_date_to": str(txn.get("open_date_to") or bill_date)[:10],
            "open_date_from": str(txn.get("open_date_from") or bill_date)[:10],
            "open_date_to": str(txn.get("open_date_to") or bill_date)[:10],
            "transaction_date_blocked": bool(txn.get("transaction_date_blocked")),
            "bill_time": datetime.now().strftime("%H:%M:%S"),
            "location_code": loc,
            "location_name": str(info.get("locationname") or "").strip(),
            "reserved": reserved,
            "created_by": username,
            "features": features,
            **wh_ctx,
        }


def list_orders(
    *,
    search: str = "",
    limit: int = 50,
    days: int = 90,
    date_from: str = "",
    date_to: str = "",
    customer_code: str = "",
    billing_type: str = "",
    status_tab: str = "order",
) -> list[dict[str, Any]]:
    """Recent sales orders from quotation header tables."""
    from db import get_sales_orders_list

    lim = max(1, min(int(limit or 50), 100))
    day_span = max(7, min(int(days or 90), 365))
    q = (search or "").strip()
    df = (date_from or "").strip()[:10]
    dt = (date_to or "").strip()[:10]
    cust_filter = (customer_code or "").strip()
    bill_filter = (billing_type or "").strip().upper()
    tab = (status_tab or "order").strip().lower()
    if tab not in ("order", "invoiced", "cancelled", "all"):
        tab = "order"

    if not df and not dt:
        end = datetime.now().date()
        start = end - timedelta(days=day_span - 1)
        df = start.strftime("%Y-%m-%d")
        dt = end.strftime("%Y-%m-%d")

    with _erp_session_scope():
        loc = _location_code()
        rows = get_sales_orders_list(
            location_code=loc,
            search=q,
            date_from=df,
            date_to=dt,
            status_tab=tab,
        ) or []

        out: list[dict[str, Any]] = []
        for raw in rows:
            r = dict(raw or {})
            if cust_filter:
                if str(r.get("customercode") or "").strip() != cust_filter:
                    continue
            bt = str(r.get("billtype") or "").strip().upper()
            billing = "CREDIT" if bt.startswith("R") else "CASH"
            if bill_filter == "CREDIT" and billing != "CREDIT":
                continue
            if bill_filter in ("CASH", "CARD") and billing != "CASH":
                continue

            billdate = r.get("billdate")
            if hasattr(billdate, "strftime"):
                billdate_s = billdate.strftime("%Y-%m-%d")
            else:
                billdate_s = str(billdate or "")[:10]

            status = str(r.get("billstatus") or "P").strip().upper()
            out.append(
                {
                    "billno": str(r.get("billno") or "").strip(),
                    "billdate": billdate_s,
                    "customer_code": str(r.get("customercode") or "").strip(),
                    "customer_name": str(r.get("customername") or "").strip(),
                    "orderno": str(r.get("orderno") or "").strip(),
                    "net_amount": _to_float(r.get("netbillamount")),
                    "billtype": bt[:1] if bt else "C",
                    "billing_type": billing,
                    "billstatus": status,
                    "remarks": str(r.get("remarks") or "").strip(),
                    "created_by": str(r.get("createdby") or "").strip(),
                }
            )
            if len(out) >= lim:
                break
        return out


def get_order_detail(billno: Any) -> dict[str, Any] | None:
    from db import billno_is_valid, get_sales_order_for_edit, parse_billno_from_request

    bn = parse_billno_from_request(billno)
    if not billno_is_valid(bn):
        return None

    with _erp_session_scope():
        loc = _location_code()
        data = get_sales_order_for_edit(loc, bn)
        if not data:
            return None
        hdr = dict(data.get("header") or {})
        lines_raw = list(data.get("lines") or [])

        billdate = hdr.get("billdate")
        if hasattr(billdate, "strftime"):
            billdate_s = billdate.strftime("%Y-%m-%d")
        else:
            billdate_s = str(billdate or "")[:10]

        bt = str(hdr.get("billtype") or "").strip().upper()
        billing = "CREDIT" if bt.startswith("R") else "CASH"
        lines: list[dict[str, Any]] = []
        for i, ln in enumerate(lines_raw, 1):
            row = dict(ln or {})
            wh_id = row.get("warehouse_id")
            try:
                wh_id_s = str(int(float(wh_id))) if wh_id not in (None, "") else ""
            except (TypeError, ValueError):
                wh_id_s = str(wh_id or "").strip()
            store = str(row.get("store") or row.get("warehouse_code") or "").strip()
            lines.append(
                {
                    "line_no": int(float(row.get("slno") or row.get("line_no") or i)),
                    "item_code": str(row.get("item_code") or row.get("itemcode") or "").strip(),
                    "item_name": str(
                        row.get("item_name") or row.get("itemname") or row.get("itemdetails1") or ""
                    ).strip(),
                    "uom": str(row.get("uom") or row.get("unitofmeasurement") or "").strip(),
                    "qty": _to_float(row.get("quantity") or row.get("qty")),
                    "rate": _to_float(row.get("rate")),
                    "discount": _to_float(row.get("discount") or row.get("itdisc")),
                    "amount": _to_float(row.get("amount")),
                    "cost": _to_float(row.get("cost")),
                    "base_qty": _to_float(row.get("base_qty") or row.get("quantity") or row.get("qty")),
                    "barcode": str(row.get("barcode") or "").strip(),
                    "warehouse_id": wh_id_s or None,
                    "warehouse_code": str(row.get("warehouse_code") or store).strip() or None,
                    "warehouse_name": str(row.get("warehouse_name") or "").strip() or None,
                    "store": store or None,
                }
            )

        wh_hdr_id = hdr.get("warehouse_id")
        try:
            wh_hdr_s = str(int(float(wh_hdr_id))) if wh_hdr_id not in (None, "") else ""
        except (TypeError, ValueError):
            wh_hdr_s = str(wh_hdr_id or "").strip()
        wh_hdr_code = str(hdr.get("warehouse_code") or "").strip()
        wh_hdr_name = str(hdr.get("warehouse_name") or "").strip()

        # Fall back to first line store/warehouse when header has none (common on older SO rows).
        if not wh_hdr_s and not wh_hdr_code:
            for ln in lines:
                if ln.get("warehouse_id"):
                    wh_hdr_s = str(ln.get("warehouse_id") or "").strip()
                    wh_hdr_code = str(ln.get("warehouse_code") or ln.get("store") or "").strip()
                    wh_hdr_name = str(ln.get("warehouse_name") or "").strip()
                    break
                if ln.get("warehouse_code") or ln.get("store"):
                    wh_hdr_code = str(ln.get("warehouse_code") or ln.get("store") or "").strip()
                    wh_hdr_name = str(ln.get("warehouse_name") or "").strip()
                    break

        if (not wh_hdr_s or not wh_hdr_name) and wh_hdr_code:
            try:
                from db import get_warehouse_master_by_code, get_warehouse_master_by_id

                wh_row = get_warehouse_master_by_code(wh_hdr_code)
                if not wh_row:
                    try:
                        wh_row = get_warehouse_master_by_id(int(float(wh_hdr_code)))
                    except (TypeError, ValueError):
                        wh_row = None
                if wh_row:
                    try:
                        wh_hdr_s = str(
                            int(float(wh_row.get("warehouse_id") or wh_row.get("WAREHOUSE_ID") or 0))
                        )
                        if wh_hdr_s == "0":
                            wh_hdr_s = ""
                    except (TypeError, ValueError):
                        pass
                    wh_hdr_code = str(
                        wh_row.get("warehouse_code") or wh_row.get("WAREHOUSE_CODE") or wh_hdr_code
                    ).strip()
                    wh_hdr_name = str(
                        wh_row.get("warehouse_name") or wh_row.get("WAREHOUSE_NAME") or wh_hdr_name
                    ).strip()
            except Exception:
                pass

        return {
            "billno": str(hdr.get("billno") or bn).strip(),
            "billdate": billdate_s,
            "billtime": str(hdr.get("billtime") or "").strip(),
            "customer_code": str(hdr.get("customercode") or "").strip(),
            "customer_name": str(hdr.get("customername") or "").strip(),
            "orderno": str(hdr.get("orderno") or "").strip(),
            "net_amount": _to_float(hdr.get("netbillamount")),
            "billtype": bt[:1] if bt else "C",
            "billing_type": billing,
            "billstatus": str(hdr.get("billstatus") or "P").strip().upper(),
            "remarks": str(hdr.get("remarks") or "").strip(),
            "address": str(hdr.get("address") or "").strip(),
            "warehouse_id": wh_hdr_s or None,
            "warehouse_code": wh_hdr_code or None,
            "warehouse_name": wh_hdr_name or None,
            "lines": lines,
        }


def save_order(payload: dict[str, Any], *, username: str) -> dict[str, Any]:
    from addons.document_numbering.document_numbering_db import DOC_TYPE_SALES_ORDER
    from db import (
        _resolve_sales_header_billtype,
        _validate_sales_doc_save_lines,
        get_next_bill_no,
        parse_billno_from_request,
        resolve_customer_billtype,
        save_sales_order,
    )

    header = dict(payload.get("header") or {})
    lines = list(payload.get("lines") or [])
    if not lines:
        raise ValueError("Add at least one line item.")

    order_no = str(header.get("orderno") or header.get("order_no") or "").strip()
    walk_in = bool(header.get("walk_in") or header.get("is_walk_in"))
    features = None
    doc = str(header.get("billno") or order_no or "").strip()

    with mobile_operation_lock(
        "sales_order",
        doc,
        lock_seconds=120.0,
        busy_message="Sales order is already being saved. Please wait.",
    ), _erp_session_scope() as user:
        loc = _location_code()
        features = _order_features()
        if features["orderno_mandatory"] and not order_no and not walk_in:
            raise ValueError("Order No is required.")
        header["orderno"] = order_no[:80] if order_no else ""

        billing = str(
            header.get("customer_billing_type") or header.get("billing_type") or "CASH"
        ).strip().upper()
        cust_raw = (
            header.get("customercode")
            if header.get("customercode") is not None
            else header.get("customer_code")
        )
        try:
            cc = int(float(str(cust_raw).strip())) if cust_raw not in (None, "") else 0
        except (TypeError, ValueError):
            cc = 0

        if billing == "CREDIT":
            if cc <= 0:
                raise ValueError("Credit order requires a customer.")
        elif walk_in:
            cc = 0
            header["customercode"] = 0
            header["customer_code"] = 0
            header["customer_billing_type"] = "CASH"
            header["billtype"] = "C"
            header["walk_in"] = True
            if not str(header.get("customername") or header.get("customer_name") or "").strip():
                header["customername"] = "Walk-in"
        elif cc <= 0:
            raise ValueError("Select a customer or choose walk-in cash order.")
        else:
            header["customercode"] = cc

        lines = _normalize_invoice_save_lines(lines)
        line_err = _validate_sales_doc_save_lines(lines, doc_label="sales order")
        if line_err:
            raise ValueError(line_err)

        from mobile_backend.services.transaction_date_helper import resolve_doc_date

        header["location_code"] = loc
        bill_date = resolve_doc_date(
            "sales_order",
            header.get("billdate") or header.get("bill_date"),
            location_code=loc,
            snap_out_of_range=True,
        )
        header["billdate"] = bill_date
        header["bill_date"] = bill_date
        header.setdefault("createdby", user or username)
        header.setdefault("billtime", datetime.now().strftime("%H:%M:%S"))
        header.setdefault("sessioncode", 0)
        header.setdefault("countercode", 0)
        header.setdefault("employeecode", 0)
        header["customer_billing_type"] = billing
        if cc > 0:
            header["billtype"] = resolve_customer_billtype(cc, header)
        else:
            header["billtype"] = "C"
        bt, billtype_err = _resolve_sales_header_billtype(header)
        if billtype_err:
            raise ValueError(billtype_err)
        header["billtype"] = bt
        header["customer_billing_type"] = "CREDIT" if bt == "R" else "CASH"

        # Persist warehouse on quotation lines via STORE (SO has no WAREHOUSE_ID column).
        header, lines = _stamp_order_warehouse(header, lines, required=features["warehouse_enabled"])

        requested = parse_billno_from_request(header.get("billno"))
        editing = bool(header.get("use_existing_billno"))
        if not requested:
            header["billno"] = get_next_bill_no(
                loc, header.get("countercode"), doc_type=DOC_TYPE_SALES_ORDER
            )
            editing = False
        else:
            header["billno"] = requested
            # Editing an existing pending order (reuse bill no / replace lines).
            if editing or header.get("use_existing_billno"):
                header["use_existing_billno"] = True
                editing = True

        ok, error, billno = save_sales_order({"header": header, "lines": lines})
        if not ok:
            raise ValueError(error or "Save failed")
        return {
            "billno": billno,
            "requested_billno": requested or billno,
            "billno_reassigned": bool(
                requested and str(requested) != str(billno)
            ),
            "message": "Sales order updated" if editing else None,
            "gl_posted": False,
            "accounts_posted": False,
        }


def convert_order_to_invoice(order_billno: Any, *, username: str) -> dict[str, Any]:
    """Post a sales invoice from one pending sales order (ERP Invoice Each)."""
    from db import (
        billno_is_valid,
        find_invoice_billno_for_source_sales_order,
        get_sales_order_for_edit,
        mark_sales_order_invoiced,
        parse_billno_from_request,
    )
    from mobile_backend.services.transaction_date_helper import resolve_doc_date
    from mobile_backend.services import sales_invoice_service

    bn = parse_billno_from_request(order_billno)
    if not billno_is_valid(bn):
        raise ValueError("Invalid sales order number.")

    with mobile_operation_lock(
        "sales_order_convert",
        str(bn),
        lock_seconds=180.0,
        busy_message="Sales order is already being converted. Please wait.",
    ), _erp_session_scope() as user:
        loc = _location_code()
        existing = find_invoice_billno_for_source_sales_order(loc, bn)
        if existing:
            mark_sales_order_invoiced(loc, bn, existing)
            return {
                "order_billno": str(bn).strip(),
                "invoice_billno": str(existing).strip(),
                "already_invoiced": True,
                "message": f"Order already converted to invoice {existing}.",
            }

        order = get_sales_order_for_edit(loc, bn)
        if not order:
            raise ValueError(f"Sales order {bn} not found.")
        hdr = dict(order.get("header") or {})
        lines = list(order.get("lines") or [])
        st = str(hdr.get("billstatus") or "P").strip().upper()
        if st == "V":
            raise ValueError(f"Sales order {bn} is cancelled and cannot be converted.")
        if st == "I":
            raise ValueError(f"Sales order {bn} is already invoiced.")
        if not lines:
            raise ValueError(f"Sales order {bn} has no lines.")

        try:
            cc = int(float(str(hdr.get("customercode") or 0).strip() or 0))
        except (TypeError, ValueError):
            cc = 0
        if cc <= 0:
            raise ValueError(
                f"Sales order {bn} has no customer. Add a customer before converting to sale."
            )

        bt = str(hdr.get("billtype") or "").strip().upper()
        billing = "CREDIT" if bt.startswith("R") else "CASH"

        customer_order_ref = str(hdr.get("orderno") or "").strip()
        remarks = str(hdr.get("remarks") or "").strip()
        so_note = f"From SO #{bn}"
        if so_note.lower() not in remarks.lower():
            remarks = "; ".join(filter(None, [remarks, so_note])).strip("; ")
        if customer_order_ref and customer_order_ref.upper() != str(bn).upper():
            po_note = f"Customer order ref {customer_order_ref}"
            if po_note.lower() not in remarks.lower():
                remarks = "; ".join(filter(None, [remarks, po_note])).strip("; ")

        billdate = resolve_doc_date(
            "sales",
            hdr.get("billdate"),
            location_code=loc,
            snap_out_of_range=True,
        )

        inv_header: dict[str, Any] = {
            "customercode": cc,
            "customer_code": cc,
            "customername": str(hdr.get("customername") or "").strip(),
            "customer_name": str(hdr.get("customername") or "").strip(),
            "customer_billing_type": billing,
            "billing_type": billing,
            "billtype": bt[:1] if bt else "C",
            "orderno": str(bn).strip()[:80],
            "remarks": remarks,
            "address": str(hdr.get("address") or "").strip(),
            "billdate": billdate,
            "billtime": datetime.now().strftime("%H:%M:%S"),
            "source_order_billno": bn,
            "source_order_billnos": [bn],
            "createdby": user or username,
        }
        if hdr.get("warehouse_id") is not None:
            inv_header["warehouse_id"] = hdr.get("warehouse_id")
        if hdr.get("warehouse_code"):
            inv_header["warehouse_code"] = hdr.get("warehouse_code")

        inv_lines: list[dict[str, Any]] = []
        for ln in lines:
            row = dict(ln or {})
            inv_lines.append(
                {
                    "item_code": row.get("item_code"),
                    "item_name": row.get("item_name") or "",
                    "uom": row.get("uom") or "",
                    "quantity": row.get("quantity") or row.get("qty") or 0,
                    "rate": row.get("rate") or 0,
                    "discount": row.get("discount") or 0,
                    "amount": row.get("amount"),
                    "base_qty": row.get("base_qty"),
                    "conversion_factor": row.get("conversion_factor")
                    or row.get("conversionfactor")
                    or row.get("factor"),
                    "cost": row.get("cost") or 0,
                    "barcode": row.get("barcode") or "",
                    "store": row.get("store") or "",
                    "warehouse_id": row.get("warehouse_id"),
                    "warehouse_code": row.get("warehouse_code") or row.get("store") or "",
                }
            )

    # save_invoice opens its own ERP session scope
    saved = sales_invoice_service.save_invoice(
        {"header": inv_header, "lines": inv_lines},
        username=username,
    )
    invoice_billno = saved.get("billno")
    if not invoice_billno:
        raise ValueError("Invoice save did not return a bill number.")

    mark_warning = None
    with _erp_session_scope():
        loc = _location_code()
        ok_mark, mark_err = mark_sales_order_invoiced(loc, bn, invoice_billno)
        if not ok_mark:
            mark_warning = mark_err or "Could not mark sales order as invoiced."

    msg = saved.get("message") or f"Converted to sale {invoice_billno}."
    if mark_warning:
        msg = f"{msg} Warning: {mark_warning}"

    return {
        "order_billno": str(bn).strip(),
        "invoice_billno": str(invoice_billno).strip(),
        "already_invoiced": False,
        "billno_reassigned": bool(saved.get("billno_reassigned")),
        "gl_posted": bool(saved.get("gl_posted")),
        "accounts_posted": bool(saved.get("accounts_posted")),
        "message": msg,
        "order_mark_warning": mark_warning,
    }


def cancel_order(order_billno: Any) -> dict[str, Any]:
    """Cancel a pending sales order (BILLSTATUS=V)."""
    from db import (
        billno_is_valid,
        cancel_sales_order,
        get_sales_order_for_edit,
        parse_billno_from_request,
    )

    bn = parse_billno_from_request(order_billno)
    if not billno_is_valid(bn):
        raise ValueError("Invalid sales order number.")

    with mobile_operation_lock(
        "sales_order",
        str(bn),
        busy_message="Sales order is already being updated. Please wait.",
    ), _erp_session_scope():
        loc = _location_code()
        order = get_sales_order_for_edit(loc, bn)
        if not order:
            raise ValueError(f"Sales order {bn} not found.")
        st = str((order.get("header") or {}).get("billstatus") or "P").strip().upper()
        if st == "V":
            raise ValueError(f"Sales order {bn} is already cancelled.")
        if st == "I":
            raise ValueError(f"Sales order {bn} is invoiced and cannot be cancelled.")
        ok, err = cancel_sales_order(loc, bn)
        if not ok:
            raise ValueError(err or "Cancel failed.")
        return {
            "billno": str(bn).strip(),
            "billstatus": "V",
            "message": f"Sales order {bn} cancelled.",
        }


def build_order_pdf(billno: Any) -> tuple[bytes, str]:
    """ERP cashbilldup sales-order PDF (same layout as desktop Sales Order print)."""
    from addons.reports.controllers.routes import _generate_cashbilldup_pdf
    from addons.reports.invoice_templates import get_saved_invoice_template
    from db import billno_is_valid, get_sales_order_for_edit, parse_billno_from_request

    bn = parse_billno_from_request(billno)
    if not billno_is_valid(bn):
        raise ValueError("Invalid bill number.")

    with _erp_session_scope():
        loc = _location_code()
        order = get_sales_order_for_edit(loc, bn)
        if not order:
            raise ValueError("Sales order not found for PDF.")
        hdr = order.get("header") or {}
        lines: list[dict[str, Any]] = []
        total_discount = 0.0
        total_amount = 0.0
        for ln in order.get("lines") or []:
            qty = _to_float(ln.get("quantity"))
            rate = _to_float(ln.get("rate"))
            disc = _to_float(ln.get("discount"))
            total_discount += disc
            total_amount += qty * rate - disc
            lines.append(
                {
                    "itemcode": ln.get("item_code"),
                    "itemname": ln.get("item_name"),
                    "uom": ln.get("uom"),
                    "unitofmeasurement": ln.get("uom"),
                    "quantity": ln.get("quantity"),
                    "rate": ln.get("rate"),
                    "discount": ln.get("discount"),
                    "itdisc": ln.get("discount") or 0,
                    "amount": ln.get("amount"),
                }
            )
        header = {
            "customercode": hdr.get("customercode"),
            "partyname": hdr.get("customername"),
            "billdate": hdr.get("billdate"),
            "billtime": hdr.get("billtime"),
            "remarks": hdr.get("remarks"),
            "address": hdr.get("address") or "",
            "locationcode": loc,
            "orderno": hdr.get("orderno") or "",
            "discountamount": round(total_discount, 3),
            "netbillamount": round(total_amount, 3),
        }
        pdf_bytes = _generate_cashbilldup_pdf(
            billno=bn,
            header=header,
            lines=lines,
            invoice_title="SALES ORDER",
            template=get_saved_invoice_template(),
        )
        if not pdf_bytes:
            raise ValueError("Failed to generate sales order PDF. Check reportlab on the server.")
        safe = str(bn).replace("/", "-").replace("\\", "-")
        return pdf_bytes, f"sales_order_{safe}.pdf"
