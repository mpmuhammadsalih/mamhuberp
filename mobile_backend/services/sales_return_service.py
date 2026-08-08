"""Sales return — BILLHDR/BILLDTL with RETURNFLAG / negative qty (ERP sales return)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from mobile_backend.operation_lock import mobile_operation_lock
from mobile_backend.services.dashboard_service import _to_float
from mobile_backend.services import sales_invoice_service as inv
from mobile_backend.services.stock_transfer_service import _erp_session_scope


def _location_code() -> int:
    return inv._location_code()


def _return_features() -> dict[str, bool]:
    from db import (
        get_sales_orderno_mandatory_return_enabled,
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
        "orderno_mandatory": bool(get_sales_orderno_mandatory_return_enabled()),
    }


def _default_warehouse_context(username: str) -> dict[str, Any]:
    from db import get_warehouse_master_by_id
    from db.user_warehouse_prefs import get_user_default_warehouse_id, warehouse_display_label

    wid = get_user_default_warehouse_id(username, "sales_return")
    out: dict[str, Any] = {
        "default_warehouse_id": wid,
        "default_warehouse_code": "",
        "default_warehouse_name": "",
        "default_warehouse_label": warehouse_display_label(wid) if wid else "",
    }
    if wid:
        try:
            wh = get_warehouse_master_by_id(int(wid)) or {}
            out["default_warehouse_code"] = str(wh.get("warehouse_code") or "").strip()
            out["default_warehouse_name"] = str(wh.get("warehouse_name") or "").strip()
        except (TypeError, ValueError):
            pass
    return out


def list_returns(
    *,
    search: str = "",
    limit: int = 50,
    days: int = 90,
    date_from: str = "",
    date_to: str = "",
    customer_code: str = "",
    billing_type: str = "",
) -> list[dict[str, Any]]:
    """Recent sales returns from BILLHDR (RETURNFLAG / negative net)."""
    from db.oracle_driver import cx_Oracle

    from mobile_backend.database.oracle_pool import get_connection
    from mobile_backend.request_context import get_jwt
    from mobile_backend.services.inventory_service import _pick_existing
    from mobile_backend.services.sales_service import _resolve_schema

    lim = max(1, min(int(limit or 50), 100))
    day_span = max(7, min(int(days or 90), 365))
    q = (search or "").strip()
    df = (date_from or "").strip()[:10]
    dt = (date_to or "").strip()[:10]
    cust_filter = (customer_code or "").strip()
    bill_filter = (billing_type or "").strip().upper()

    claims = get_jwt()
    tenant_id = claims.get("tenant_id")

    with _erp_session_scope():
        loc = _location_code()
        conn = get_connection(tenant_id=tenant_id)
        with conn.cursor() as cur:
            schema = _resolve_schema(cur)
            if not schema:
                return []

            cols = schema["cols"]
            fc = schema["from_clause"]
            dc = schema["date_col"]
            amt = schema["amt_expr"]
            from db import billno_is_valid, coerce_billno

            billno_col = schema["billno_col"]
            cust_col = schema.get("cust_col")
            cust_name_col = _pick_existing(
                cols,
                ["CUSTOMERNAME", "CUSTOMER_NAME", "CUSTNAME", "CUST_NAME"],
            )
            billtype_col = _pick_existing(cols, ["BILLTYPE", "BILL_TYPE"])
            orderno_col = _pick_existing(cols, ["ORDERNO", "ORDER_NO"])
            loc_col = _pick_existing(cols, ["LOCATIONCODE", "LOCATION_CODE"])
            return_col = _pick_existing(cols, ["RETURNFLAG", "RETURN_FLAG"])
            delflag_col = _pick_existing(cols, ["DELFLAG", "DEL_FLAG"])
            status_col = _pick_existing(cols, ["BILLSTATUS", "BILL_STATUS"])

            where: list[str] = []
            params: dict[str, Any] = {"lim": lim}

            if delflag_col:
                where.append(f"NVL(b.{delflag_col}, 'N') NOT IN ('Y', 'y')")
            if status_col:
                where.append(f"NVL(b.{status_col}, ' ') <> 'V'")

            return_match: list[str] = []
            if return_col:
                return_match.append(f"NVL(b.{return_col}, 'N') = 'Y'")
            return_match.append(f"({amt}) < 0")
            where.append("(" + " OR ".join(return_match) + ")")

            if df or dt:
                if df:
                    where.append(f"TRUNC(b.{dc}) >= TRUNC(TO_DATE(:date_from, 'YYYY-MM-DD'))")
                    params["date_from"] = df
                if dt:
                    where.append(f"TRUNC(b.{dc}) <= TRUNC(TO_DATE(:date_to, 'YYYY-MM-DD'))")
                    params["date_to"] = dt
            else:
                where.append(f"TRUNC(b.{dc}) >= TRUNC(SYSDATE) - :days + 1")
                params["days"] = day_span

            if billtype_col:
                if bill_filter == "CREDIT":
                    where.append(
                        f"UPPER(SUBSTR(TRIM(TO_CHAR(b.{billtype_col})), 1, 1)) = 'R'"
                    )
                elif bill_filter in ("CASH", "CARD"):
                    where.append(
                        f"UPPER(SUBSTR(TRIM(TO_CHAR(b.{billtype_col})), 1, 1)) = 'C'"
                    )
                else:
                    where.append(
                        f"UPPER(SUBSTR(TRIM(TO_CHAR(b.{billtype_col})), 1, 1)) IN ('C', 'R')"
                    )

            if cust_filter and cust_col:
                where.append(f"TRIM(TO_CHAR(b.{cust_col})) = :cust_code")
                params["cust_code"] = cust_filter

            if loc_col and loc:
                where.append(f"b.{loc_col} = :loc")
                params["loc"] = int(loc)

            if q:
                params["sw"] = f"%{q}%"
                parts = [f"TO_CHAR(b.{billno_col}) LIKE :sw"]
                if cust_col:
                    parts.append(f"TO_CHAR(b.{cust_col}) LIKE :sw")
                if cust_name_col:
                    parts.append(f"UPPER(b.{cust_name_col}) LIKE UPPER(:sw)")
                if orderno_col:
                    parts.append(f"UPPER(b.{orderno_col}) LIKE UPPER(:sw)")
                where.append(f"({' OR '.join(parts)})")

            select_parts = [
                f"b.{billno_col} AS billno",
                f"TRUNC(b.{dc}) AS billdate",
                f"{amt} AS net_amount",
            ]
            if cust_col:
                select_parts.append(f"b.{cust_col} AS customer_code")
            if cust_name_col:
                select_parts.append(f"b.{cust_name_col} AS customer_name")
            if billtype_col:
                select_parts.append(f"b.{billtype_col} AS billtype")
            if orderno_col:
                select_parts.append(f"b.{orderno_col} AS orderno")

            sql = f"""
                SELECT * FROM (
                    SELECT {", ".join(select_parts)}
                      FROM {fc}
                     WHERE {" AND ".join(where)}
                     ORDER BY b.{dc} DESC, b.{billno_col} DESC
                )
                WHERE ROWNUM <= :lim
            """

            try:
                cur.execute(sql, params)
                rows = cur.fetchall() or []
            except cx_Oracle.DatabaseError:
                return []

            col_names = [d[0].lower() for d in cur.description or []]
            out: list[dict[str, Any]] = []
            for row in rows:
                raw = dict(zip(col_names, row))
                billno = coerce_billno(raw.get("billno"))
                if not billno_is_valid(billno):
                    continue
                billdate = raw.get("billdate")
                if hasattr(billdate, "strftime"):
                    billdate_s = billdate.strftime("%Y-%m-%d")
                else:
                    billdate_s = str(billdate or "")[:10]

                bt = str(raw.get("billtype") or "").strip().upper()
                billing = "CREDIT" if bt.startswith("R") else "CASH"
                net = _to_float(raw.get("net_amount"))

                out.append(
                    {
                        "billno": billno,
                        "billdate": billdate_s,
                        "customer_code": str(raw.get("customer_code") or "").strip(),
                        "customer_name": str(raw.get("customer_name") or "").strip(),
                        "orderno": str(raw.get("orderno") or "").strip(),
                        "net_amount": net,
                        "billtype": bt[:1] if bt else "C",
                        "billing_type": billing,
                    }
                )
            return out


def get_return_detail(billno: Any) -> dict[str, Any] | None:
    """Reuse invoice detail loader (same BILLHDR/BILLDTL shape)."""
    return inv.get_invoice_detail(billno)


def get_return_open_context(*, peek_billno: bool = True) -> dict[str, Any]:
    from addons.document_numbering.document_numbering_db import DOC_TYPE_SALES_RETURN
    from db import get_location_info_by_dbkey, get_next_bill_no, get_open_bill_date, peek_next_bill_no

    with _erp_session_scope() as username:
        loc = _location_code()
        open_dt = get_open_bill_date(loc)
        bill_date = open_dt.strftime("%Y-%m-%d") if open_dt else datetime.now().strftime("%Y-%m-%d")
        if peek_billno:
            billno = peek_next_bill_no(loc, None, doc_type=DOC_TYPE_SALES_RETURN)
            reserved = False
        else:
            billno = get_next_bill_no(loc, None, doc_type=DOC_TYPE_SALES_RETURN)
            reserved = True
        info = get_location_info_by_dbkey(None) or {}
        features = _return_features()
        wh_ctx = _default_warehouse_context(username) if features["warehouse_enabled"] else {}
        return {
            "billno": billno,
            "bill_date": bill_date,
            "bill_time": datetime.now().strftime("%H:%M:%S"),
            "location_code": loc,
            "location_name": str(info.get("locationname") or "").strip(),
            "reserved": reserved,
            "created_by": username,
            "features": features,
            **wh_ctx,
        }


def _negate_return_lines(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in lines:
        row = dict(raw or {})
        try:
            qty = abs(float(row.get("quantity") or 0))
        except (TypeError, ValueError):
            qty = 0.0
        if qty <= 0:
            item = str(row.get("item_code") or "").strip()
            raise ValueError(
                f"Line quantity must be greater than zero{f' (item {item})' if item else ''}."
            )
        try:
            base_raw = row.get("base_qty")
            base_qty = abs(float(base_raw if base_raw is not None else qty))
        except (TypeError, ValueError):
            base_qty = qty
        row["quantity"] = -qty
        row["base_qty"] = -base_qty
        amount_raw = row.get("amount")
        if amount_raw is not None:
            try:
                row["amount"] = -abs(float(amount_raw))
            except (TypeError, ValueError):
                pass
        else:
            try:
                rate = abs(float(row.get("rate") or 0))
                disc = abs(float(row.get("discount") or 0))
                row["amount"] = -(qty * rate - disc)
            except (TypeError, ValueError):
                pass
        try:
            row["discount"] = abs(float(row.get("discount") or 0))
        except (TypeError, ValueError):
            row["discount"] = 0.0
        try:
            row["rate"] = abs(float(row.get("rate") or 0))
        except (TypeError, ValueError):
            pass
        out.append(row)
    return out


def _resolve_return_billno(location_code: int, countercode: Any, requested: Any) -> tuple[Any, bool]:
    from addons.document_numbering.document_numbering_db import DOC_TYPE_SALES_RETURN
    from db import billhdr_exists, billno_is_reserved, coerce_billno, get_next_bill_no, parse_billno_from_request

    req = parse_billno_from_request(requested)
    if not req:
        return get_next_bill_no(location_code, countercode, doc_type=DOC_TYPE_SALES_RETURN), False
    if billhdr_exists(location_code, req):
        return req, False
    if not billno_is_reserved(req, location_code):
        return get_next_bill_no(location_code, countercode, doc_type=DOC_TYPE_SALES_RETURN), True
    return coerce_billno(req), False


def _save_return_with_billno_retry(
    header: dict[str, Any],
    lines: list[dict[str, Any]],
    *,
    location_code: int,
    username: str,
) -> dict[str, Any]:
    from addons.document_numbering.document_numbering_db import DOC_TYPE_SALES_RETURN
    from db import coerce_billno, get_next_bill_no, parse_billno_from_request, save_sales_invoice

    requested = header.get("billno")
    billno, reassigned = _resolve_return_billno(
        location_code, header.get("countercode"), requested
    )
    header = dict(header)
    header["billno"] = billno
    header["use_existing_billno"] = True
    header["is_sales_return"] = True
    header.setdefault("billdate", datetime.now().strftime("%Y-%m-%d"))
    header.setdefault("billtime", datetime.now().strftime("%H:%M:%S"))
    header.setdefault("createdby", username)
    header["location_code"] = location_code

    last_err = ""
    req_no = parse_billno_from_request(requested) or billno
    for _ in range(8):
        ok, error, saved_billno, stock_debug = save_sales_invoice(
            {"header": header, "lines": lines},
        )
        if ok:
            msg = None
            if reassigned:
                msg = (
                    f"Bill number {req_no} was already taken or not reserved. "
                    f"Saved as bill {saved_billno}."
                )
            gl_vno = inv._sales_gl_voucher_no(
                location_code, coerce_billno(saved_billno or billno), is_return=True
            )
            return {
                "billno": saved_billno,
                "requested_billno": req_no,
                "billno_reassigned": reassigned,
                "stock_posted": bool((stock_debug or {}).get("stock_posted")),
                "stock_affected_items": int((stock_debug or {}).get("stock_affected_items") or 0),
                "gl_posted": True,
                "gl_voucher_no": gl_vno,
                "accounts_posted": True,
                "message": msg,
            }
        last_err = error or "Save failed"
        if not inv._is_billno_retry_error(last_err):
            break
        billno = get_next_bill_no(
            location_code, header.get("countercode"), doc_type=DOC_TYPE_SALES_RETURN,
        )
        header["billno"] = billno
        reassigned = True

    body: dict[str, Any] = {"error": last_err}
    if inv._is_billno_retry_error(last_err):
        body["duplicate_billno"] = True
        body["suggested_billno"] = get_next_bill_no(
            location_code, header.get("countercode"), doc_type=DOC_TYPE_SALES_RETURN,
        )
    raise ValueError(body.get("error") or "Save failed")


def save_return(payload: dict[str, Any], *, username: str) -> dict[str, Any]:
    from db import _validate_sales_doc_save_lines, ensure_gl_tables

    header = dict(payload.get("header") or {})
    raw_lines = list(payload.get("lines") or [])
    if not raw_lines:
        raise ValueError("Add at least one line item.")

    order_no = str(header.get("orderno") or header.get("order_no") or "").strip()
    if _return_features()["orderno_mandatory"] and not order_no:
        raise ValueError("Order No is required.")
    header["orderno"] = order_no[:80] if order_no else ""

    billing = str(
        header.get("customer_billing_type") or header.get("billing_type") or "CASH"
    ).strip().upper()
    walk_in = bool(header.get("walk_in") or header.get("is_walk_in"))

    cust_raw = header.get("customercode") if header.get("customercode") is not None else header.get("customer_code")
    try:
        cc = int(float(str(cust_raw).strip())) if cust_raw not in (None, "") else 0
    except (TypeError, ValueError):
        cc = 0

    if billing == "CREDIT":
        if cc <= 0:
            raise ValueError("Credit return requires a customer.")
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
        raise ValueError("Select a customer or choose walk-in cash return.")
    else:
        header["customercode"] = cc

    lines = inv._normalize_invoice_save_lines(raw_lines)
    lines = _negate_return_lines(lines)
    line_err = _validate_sales_doc_save_lines(lines, doc_label="sales return")
    if line_err:
        raise ValueError(line_err)

    billing = str(
        header.get("customer_billing_type") or header.get("billing_type") or "CASH"
    ).strip().upper()

    # Magnitude for payment / display (UI sends positive qty).
    net_mag = 0.0
    for ln in lines:
        qty = abs(float(ln.get("quantity") or 0))
        rate = abs(float(ln.get("rate") or 0))
        disc = abs(float(ln.get("discount") or 0))
        net_mag += qty * rate - disc

    doc = str(header.get("billno") or header.get("orderno") or "").strip()
    with mobile_operation_lock(
        "sales_return",
        doc,
        lock_seconds=180.0,
        busy_message="Sales return is already being saved. Please wait.",
    ), _erp_session_scope() as user:
        loc = _location_code()
        if not ensure_gl_tables():
            raise ValueError(
                "General ledger is not configured. Sales return cannot post to accounts."
            )
        header = inv._normalize_invoice_save_header(
            header,
            location_code=loc,
            username=user or username,
        )
        header["is_sales_return"] = True
        # Returns reverse receivable — skip credit-limit block.
        if billing != "CREDIT" and cc > 0:
            from db import validate_pos_credit_customer_accounts

            ok, err = validate_pos_credit_customer_accounts(
                loc, cc, proposed_credit_delta=None
            )
            if not ok:
                raise ValueError(err or "Customer account validation failed.")
        header = inv._normalize_mobile_payment_header(header, net_mag)
        return _save_return_with_billno_retry(
            header, lines, location_code=loc, username=user or username
        )


def load_from_invoice(invoice_billno: Any) -> dict[str, Any]:
    """Load a posted sales invoice into a sales-return form payload."""
    from db import (
        billno_is_valid,
        coerce_billno,
        get_sales_invoice_for_edit,
        parse_billno_from_request,
    )

    bno = parse_billno_from_request(invoice_billno)
    if not billno_is_valid(bno):
        raise ValueError("Invoice bill number is required.")

    with _erp_session_scope():
        loc = _location_code()
        inv_doc = get_sales_invoice_for_edit(loc, bno)
        if not inv_doc:
            raise ValueError(f"Sales invoice {bno} not found.")
        hdr = dict(inv_doc.get("header") or {})
        lines = list(inv_doc.get("lines") or [])
        st = str(hdr.get("billstatus") or "P").strip().upper()
        if st == "V":
            raise ValueError(f"Sales invoice {bno} is voided and cannot be returned.")
        delflag = str(hdr.get("delflag") or "N").strip().upper()
        if delflag in ("Y", "1", "T", "TRUE"):
            raise ValueError(f"Sales invoice {bno} is deleted and cannot be returned.")
        rf = str(hdr.get("returnflag") or "N").strip().upper()
        try:
            net = float(hdr.get("netbillamount") or 0)
        except (TypeError, ValueError):
            net = 0.0
        if rf == "Y" or net < 0:
            raise ValueError(f"Bill {bno} is a sales return, not a sales invoice.")
        if not lines:
            raise ValueError(f"Sales invoice {bno} has no lines.")
        try:
            if int(hdr.get("customercode") or 0) <= 0:
                raise ValueError(f"Sales invoice {bno} has no customer.")
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Sales invoice {bno} has invalid customer.") from exc

        hdr_out = dict(hdr)
        for key in (
            "billno",
            "billdate",
            "billtime",
            "netbillamount",
            "returnflag",
            "delflag",
            "discountamount",
            "additional_discount",
        ):
            hdr_out.pop(key, None)
        hdr_out["source_invoice_billno"] = bno
        orig_ord = str(hdr.get("orderno") or "").strip()
        hdr_out["orderno"] = f"R{bno}"[:80]
        si_note = f"From SI #{bno}"
        if orig_ord and orig_ord.upper() not in (f"R{bno}".upper(), str(bno)):
            si_note = f"{si_note}; Order ref {orig_ord}"
        existing_remarks = str(hdr_out.get("remarks") or "").strip()
        if si_note.lower() not in existing_remarks.lower():
            hdr_out["remarks"] = "; ".join(filter(None, [existing_remarks, si_note])).strip("; ")

        clean_lines: list[dict[str, Any]] = []
        for ln in lines:
            if not isinstance(ln, dict):
                continue
            row = dict(ln)
            try:
                qty_mag = abs(float(row.get("quantity") or 0))
            except (TypeError, ValueError):
                qty_mag = 0.0
            if qty_mag <= 0:
                continue
            # UI uses positive qty; save endpoint will negate.
            row["quantity"] = qty_mag
            try:
                base_mag = abs(float(row.get("base_qty") if row.get("base_qty") is not None else qty_mag))
            except (TypeError, ValueError):
                base_mag = qty_mag
            row["base_qty"] = base_mag
            try:
                row["discount"] = abs(float(row.get("discount") or 0))
            except (TypeError, ValueError):
                row["discount"] = 0.0
            try:
                row["rate"] = round(abs(float(row.get("rate") or 0)), 3)
            except (TypeError, ValueError):
                row["rate"] = 0.0
            try:
                amt_mag = abs(float(row.get("amount") or 0))
            except (TypeError, ValueError):
                amt_mag = 0.0
            if amt_mag <= 1e-9:
                amt_mag = round(qty_mag * float(row["rate"]) - float(row["discount"]), 2)
                if amt_mag < 0:
                    amt_mag = 0.0
            row["amount"] = round(amt_mag, 2)
            clean_lines.append(row)
        if not clean_lines:
            raise ValueError(f"Sales invoice {bno} has no returnable lines.")

        bt = str(hdr_out.get("billtype") or "C").strip().upper()[:1]
        billing = "CREDIT" if bt == "R" else "CASH"
        return {
            "header": {
                "customercode": hdr_out.get("customercode"),
                "customer_code": hdr_out.get("customercode"),
                "customername": hdr_out.get("customername") or "",
                "customer_name": hdr_out.get("customername") or "",
                "address": hdr_out.get("address") or "",
                "orderno": hdr_out.get("orderno") or "",
                "remarks": hdr_out.get("remarks") or "",
                "billtype": bt or "C",
                "customer_billing_type": billing,
                "source_invoice_billno": coerce_billno(bno),
                "warehouse_id": hdr_out.get("warehouse_id"),
            },
            "lines": clean_lines,
            "source_invoice_billno": coerce_billno(bno),
        }


def build_return_pdf(billno: Any) -> tuple[bytes, str]:
    """ERP cashbilldup PDF titled as sales return."""
    from addons.reports.controllers.routes import _generate_cashbilldup_pdf
    from db import billno_is_valid, get_sales_print_data, parse_billno_from_request

    bn = parse_billno_from_request(billno)
    if not billno_is_valid(bn):
        raise ValueError("Invalid bill number.")

    with _erp_session_scope():
        loc = _location_code()
        header, lines = get_sales_print_data(bn, loc)
        if not header:
            raise ValueError("Sales return not found for PDF.")
        pdf_bytes = _generate_cashbilldup_pdf(
            billno=bn,
            header=header,
            lines=lines or [],
            invoice_title="SALES RETURN",
        )
        if not pdf_bytes:
            raise ValueError("Failed to generate sales return PDF. Check reportlab on the server.")
        safe = str(bn).replace("/", "-").replace("\\", "-")
        filename = f"sales_return_{safe}.pdf"
        return pdf_bytes, filename
