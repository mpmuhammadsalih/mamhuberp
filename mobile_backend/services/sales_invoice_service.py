"""Sales invoice — delegates to ERP db layer (BILLHDR/BILLDTL) under JWT session scope."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any

from mobile_backend.operation_lock import mobile_operation_lock
from mobile_backend.services.dashboard_service import _to_float
from mobile_backend.services.stock_transfer_service import _erp_session_scope

_log = logging.getLogger(__name__)

_FUZZY_MIN_QUERY_LEN = 3
_FUZZY_MAX_QUERY_LEN = 6  # longer queries are contains-only (keyword must appear inside)
_FUZZY_SCORE_THRESHOLD = 0.78


def _location_code() -> int:
    from db import get_location_info_by_dbkey
    from nexa_http.session_wrap import session

    loc = session.get("location_code")
    if loc is not None:
        try:
            return int(loc)
        except (TypeError, ValueError):
            pass
    info = get_location_info_by_dbkey(None) or {}
    return int(info.get("locationcode") or 1)


def _read_credit_limit(row: dict[str, Any]) -> float:
    for key in (
        "CREDITLIMIT",
        "creditlimit",
        "credit_limit",
        "CreditLimit",
        "CREDIT_LIMIT",
        "CREDITLIMITAMOUNT",
        "CREDITAMOUNT",
        "CREDIT_AMT",
    ):
        if key in row and row[key] is not None:
            try:
                return float(row[key])
            except (TypeError, ValueError):
                continue
    for k, v in row.items():
        if str(k).upper().replace("_", "") == "CREDITLIMIT" and v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
    return 0.0


def _normalize_customer_row(
    row: dict[str, Any],
    *,
    include_gl: bool = True,
    gl_ctx: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base = dict(row)
    if include_gl:
        base = _apply_gl_outstanding_to_customer_row(base, ctx=gl_ctx)
    code = base.get("CODE") or base.get("code") or base.get("CUSTOMERCODE")
    name = base.get("NAME") or base.get("name") or base.get("CUSTOMERNAME") or ""
    billing = (
        base.get("CUSTOMER_BILLING_TYPE")
        or base.get("customer_billing_type")
        or "CASH"
    )
    gl_outstanding = float(
        base.get("CURRENTCREDIT")
        or base.get("current_credit")
        or base.get("OUTSTANDINGCASH")
        or base.get("outstanding")
        or 0
    )
    return {
        "code": str(code or "").strip(),
        "name": str(name or "").strip(),
        "address": str(base.get("ADDRESS") or base.get("address") or "").strip(),
        "phone": str(base.get("PHONE") or base.get("phone") or "").strip(),
        "billing_type": str(billing).strip().upper() or "CASH",
        "credit_limit": _read_credit_limit(base),
        "category_name": str(
            base.get("CATEGORYNAME") or base.get("categoryname") or base.get("category_name") or ""
        ).strip(),
        "current_credit": gl_outstanding,
        "outstanding": gl_outstanding,
        "outstanding_source": (
            str(base.get("_gl_outstanding_source") or "GL").strip() or "GL"
            if include_gl
            else "MASTER"
        ),
    }


def _apply_gl_outstanding_to_customer_row(
    row: dict[str, Any],
    *,
    ctx: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Outstanding / current credit from GL receivable (same as ERP Accounts Receivable)."""
    from db import _customer_gl_receivable_balance, _customer_gl_receivable_context

    code = row.get("CODE") or row.get("code") or row.get("CUSTOMERCODE")
    recv = row.get("RECEIVABLEACCOUNT") or row.get("receivableaccount")
    gl_ctx = ctx if ctx is not None else _customer_gl_receivable_context()
    if gl_ctx and code not in (None, ""):
        bal, src = _customer_gl_receivable_balance(code, recv, ctx=gl_ctx)
        row["OUTSTANDINGCASH"] = bal
        row["outstandingcash"] = bal
        row["CURRENTCREDIT"] = bal
        row["currentcredit"] = bal
        row["_gl_outstanding_source"] = src
    return row


def _find_customer_master_row(customer_code: str) -> dict[str, Any] | None:
    from db import get_customers_master_list

    code = str(customer_code or "").strip()
    if not code:
        return None
    rows = get_customers_master_list(
        for_picker=True,
        picker_search=code,
        picker_limit=10,
    )
    for raw in rows or []:
        row = dict(raw)
        row_code = str(row.get("CODE") or row.get("code") or "").strip()
        if row_code == code:
            return row
    return None


def _normalize_item_row(item: dict[str, Any]) -> dict[str, Any]:
    code = item.get("ITEMCODE") or item.get("itemcode") or item.get("item_code")
    name = item.get("ITEMNAME") or item.get("itemname") or item.get("item_name") or ""
    base_uom = item.get("BASEUOM") or item.get("baseuom") or item.get("base_uom") or ""
    retail = item.get("RETAILPRICE") or item.get("retailprice") or item.get("retail_price") or 0
    stock = item.get("CURRENTSTOCK") or item.get("currentstock") or item.get("current_stock") or 0
    cost = item.get("COSTPRICE") or item.get("costprice") or item.get("cost_price") or 0
    avg = item.get("AVERAGECOST") or item.get("averagecost") or item.get("average_cost") or 0
    batch = item.get("BATCH_TRACKED") or item.get("batch_tracked") or "N"
    dwh = item.get("default_warehouse_id") or item.get("DEFAULT_WAREHOUSE_ID")
    dbin = item.get("default_bin_storage_id") or item.get("DEFAULT_BIN_STORAGE_ID")
    return {
        "item_code": str(code or "").strip(),
        "item_name": str(name or "").strip(),
        "base_uom": str(base_uom or "").strip(),
        "retail_price": float(retail or 0),
        "cost_price": float(cost or 0),
        "average_cost": float(avg or 0),
        "current_stock": float(stock or 0),
        "manufacturer_id": str(item.get("MANUFACTURERID") or item.get("manufacturer_id") or "").strip(),
        "batch_tracked": str(batch).strip().upper() == "Y",
        "default_warehouse_id": int(dwh) if dwh not in (None, "") else None,
        "default_bin_storage_id": int(dbin) if dbin not in (None, "") else None,
    }


def _is_duplicate_doc_key_error(err: Any) -> bool:
    err_l = str(err or "").lower()
    return (
        "duplicate key" in err_l
        or "ora-00001" in err_l
        or "pk_billhdr" in err_l
        or "already in use" in err_l
        or "already exists" in err_l
    )


def _is_billno_retry_error(err: Any) -> bool:
    err_l = str(err or "").lower()
    return (
        _is_duplicate_doc_key_error(err)
        or "no longer reserved" in err_l
        or "invalid reserved bill number" in err_l
    )


def _resolve_billno_for_save(location_code: int, countercode: Any, requested: Any) -> tuple[Any, bool]:
    """Pick bill number for save; allocate next if taken or not reserved (mobile peek-only).

    Mobile opens with ``peek_next_bill_no`` (does not reserve). When BILLNOTABLE is off,
    ``billno_is_reserved`` is true for any unused number — using that peek without
    ``get_next_bill_no`` leaves DOC_NUMBER_SERIES stuck, so the next New shows the same no.
    New invoices never edit an existing BILLHDR row.
    """
    from addons.document_numbering.document_numbering_db import DOC_TYPE_SALES_INVOICE
    from db import (
        _use_billnotable,
        billhdr_exists,
        billno_is_reserved,
        coerce_billno,
        get_next_bill_no,
        parse_billno_from_request,
    )

    req = parse_billno_from_request(requested)
    if not req:
        return get_next_bill_no(location_code, countercode, doc_type=DOC_TYPE_SALES_INVOICE), False
    # Already posted — never reuse (avoids fake "already_posted" success on New).
    if billhdr_exists(location_code, req):
        return get_next_bill_no(location_code, countercode, doc_type=DOC_TYPE_SALES_INVOICE), True
    # Real BILLNOTABLE reservation — keep peeked number; series advances after save.
    if _use_billnotable() and billno_is_reserved(req, location_code):
        return coerce_billno(req), False
    # Peek-only: allocate so the series advances for the next New.
    allocated = get_next_bill_no(location_code, countercode, doc_type=DOC_TYPE_SALES_INVOICE)
    return allocated, str(coerce_billno(allocated)) != str(coerce_billno(req))


def _fresh_peek_billno(location_code: int, doc_type: str, *, for_order: bool = False) -> Any:
    """Peek next bill no; if already used, allocate past collisions so New shows a free number."""
    from db import (
        billhdr_exists,
        get_next_bill_no,
        get_sales_order_for_edit,
        peek_next_bill_no,
    )

    billno = peek_next_bill_no(location_code, None, doc_type=doc_type)
    for _ in range(40):
        if not billno:
            return get_next_bill_no(location_code, None, doc_type=doc_type)
        used = (
            bool(get_sales_order_for_edit(location_code, billno))
            if for_order
            else billhdr_exists(location_code, billno)
        )
        if not used:
            return billno
        # Consume past a stuck/used peek so subsequent opens move forward.
        billno = get_next_bill_no(location_code, None, doc_type=doc_type)
    return billno


def _save_with_billno_retry(
    header: dict[str, Any],
    lines: list[dict[str, Any]],
    *,
    location_code: int,
    username: str,
) -> dict[str, Any]:
    from addons.document_numbering.document_numbering_db import DOC_TYPE_SALES_INVOICE
    from db import coerce_billno, get_next_bill_no, parse_billno_from_request, save_sales_invoice

    requested = header.get("billno")
    billno, reassigned = _resolve_billno_for_save(
        location_code, header.get("countercode"), requested
    )
    from mobile_backend.services.transaction_date_helper import resolve_doc_date

    header = dict(header)
    header["billno"] = billno
    header["use_existing_billno"] = True
    bill_date = resolve_doc_date(
        "sales",
        header.get("billdate") or header.get("bill_date"),
        location_code=location_code,
        snap_out_of_range=True,
    )
    header["billdate"] = bill_date
    header["bill_date"] = bill_date
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
            gl_vno = _sales_gl_voucher_no(location_code, coerce_billno(saved_billno or billno))
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
        if not _is_billno_retry_error(last_err):
            break
        billno = get_next_bill_no(
            location_code, header.get("countercode"), doc_type=DOC_TYPE_SALES_INVOICE,
        )
        header["billno"] = billno
        reassigned = True

    body: dict[str, Any] = {"error": last_err}
    if _is_billno_retry_error(last_err):
        body["duplicate_billno"] = True
        body["suggested_billno"] = get_next_bill_no(
            location_code, header.get("countercode"), doc_type=DOC_TYPE_SALES_INVOICE,
        )
    raise ValueError(body.get("error") or "Save failed")


def _normalize_invoice_save_header(
    header: dict[str, Any],
    *,
    location_code: int,
    username: str,
) -> dict[str, Any]:
    from db import resolve_customer_billtype

    h = dict(header)
    h["location_code"] = location_code
    h.setdefault("createdby", username)
    h["skip_gl_posting"] = False
    h["use_existing_billno"] = bool(h.get("use_existing_billno", True))

    cc_raw = h.get("customercode") or h.get("customer_code")
    try:
        cc = int(float(str(cc_raw).strip()))
        h["customercode"] = cc
    except (TypeError, ValueError):
        cc = 0

    billing = str(
        h.get("customer_billing_type") or h.get("billing_type") or "CASH"
    ).strip().upper()
    h["customer_billing_type"] = billing
    h["billtype"] = resolve_customer_billtype(cc, h) if cc > 0 else "C"

    wh_raw = h.get("warehouse_id")
    if wh_raw is not None and str(wh_raw).strip():
        try:
            h["warehouse_id"] = int(float(str(wh_raw).strip()))
        except (TypeError, ValueError):
            pass

    return h


def _normalize_invoice_save_lines(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in lines:
        ln = dict(raw or {})
        ic = ln.get("item_code")
        try:
            ln["item_code"] = int(float(str(ic).strip()))
        except (TypeError, ValueError):
            pass
        qty = float(ln.get("quantity") or 0)
        rate = float(ln.get("rate") or 0)
        disc = float(ln.get("discount") or 0)
        if ln.get("amount") is None:
            ln["amount"] = qty * rate - disc
        cost = float(ln.get("cost") or ln.get("costprice") or 0)
        if cost > 0:
            ln["cost"] = cost
            ln["costprice"] = cost
        # AVERAGECOST must stay base-UOM (ITEMMASTER). Never copy alt/pack cost into it.
        avg = float(ln.get("average_cost") or ln.get("averagecost") or 0)
        if avg > 0:
            # If client sent pack cost as averagecost (avg ≈ cost and factor>1), clear it
            # so ERP resolves ITEMMASTER.AVERAGECOST.
            try:
                factor = float(
                    ln.get("conversion_factor")
                    or ln.get("conversionfactor")
                    or ln.get("factor")
                    or 0
                )
            except (TypeError, ValueError):
                factor = 0.0
            if factor <= 0:
                try:
                    bq = abs(float(ln.get("base_qty") or 0))
                    q = abs(float(ln.get("quantity") or 0))
                    if q > 1e-12 and bq > 0:
                        factor = bq / q
                except (TypeError, ValueError):
                    factor = 0.0
            if cost > 0 and factor > 1.0 + 1e-9 and abs(avg - cost) <= max(0.01, cost * 0.001):
                avg = 0.0
        if avg > 0:
            ln["average_cost"] = avg
            ln["averagecost"] = avg
        else:
            ln.pop("average_cost", None)
            ln.pop("averagecost", None)
        # Prefer ERP UOM map; client conversion_factor / base_qty used only as fallback.
        from mobile_backend.services.uom_factor import apply_line_stock_base, client_uom_factor

        if client_uom_factor(ln) <= 0 and ln.get("base_qty") not in (None, ""):
            try:
                bq = abs(float(ln.get("base_qty") or 0))
                if bq > 0 and abs(qty) > 1e-12:
                    # Infer factor from client base when factor not sent
                    ln["conversion_factor"] = bq / abs(qty)
            except (TypeError, ValueError):
                pass
        apply_line_stock_base(ln, item_code=ln.get("item_code"), uom=str(ln.get("uom") or "NOS"), qty=qty)
        out.append(ln)
    return out


def _validate_customer_gl_before_save(
    location_code: int,
    customer_code: Any,
    *,
    net_amount: float,
    billing_type: str,
) -> None:
    """Ensure customer GL mappings (and credit limit when applicable) before posting accounts."""
    from db import validate_pos_credit_customer_accounts

    try:
        cc = int(customer_code or 0)
    except (TypeError, ValueError):
        cc = 0
    if cc <= 0:
        return
    bt = (billing_type or "CASH").strip().upper()
    if bt == "CREDIT":
        chk = check_credit_limit(str(cc), float(net_amount or 0), bt)
        if not chk.get("ok"):
            raise ValueError(chk.get("error") or "Credit limit check failed.")
        return
    ok, err = validate_pos_credit_customer_accounts(
        location_code,
        cc,
        proposed_credit_delta=None,
    )
    if not ok:
        raise ValueError(err or "Customer account validation failed.")


def _sales_gl_voucher_no(location_code: int, billno: int, *, is_return: bool = False) -> str:
    prefix = "SR" if is_return else "SI"
    return f"{prefix}-{location_code}-{billno}"[:30]


def _sales_features() -> dict[str, bool]:
    from db import (
        get_sales_direct_posting_enabled,
        get_sales_minus_billing_invoice_enabled,
        get_sales_orderno_mandatory_invoice_enabled,
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
        # Sales Accounts Configuration → Order No mandatory (invoice).
        "orderno_mandatory": bool(get_sales_orderno_mandatory_invoice_enabled()),
        # Sales Accounts Configuration → minus billing (allow sell below stock).
        "minus_billing_enabled": bool(get_sales_minus_billing_invoice_enabled()),
        # Sales Accounts Configuration → cash direct post to tender Cash/Bank GL.
        "direct_posting_enabled": bool(get_sales_direct_posting_enabled()),
    }


def _default_warehouse_context(username: str, *, module: str = "sales") -> dict[str, Any]:
    """User preference warehouse, or the only available warehouse for this module."""
    from db import get_warehouse_master_by_id
    from db.user_warehouse_prefs import (
        apply_user_warehouse_filter,
        build_warehouse_picker_rows,
        get_user_default_warehouse_id,
        warehouse_display_label,
    )

    mod = (module or "sales").strip() or "sales"
    wid = get_user_default_warehouse_id(username, mod)
    if not wid:
        try:
            loc = _location_code()
            rows = build_warehouse_picker_rows(int(loc), search="", limit=50) or []
            filtered = apply_user_warehouse_filter(username, mod, rows) or []
            if len(filtered) == 1:
                sole = filtered[0] or {}
                raw = sole.get("code") if sole.get("code") is not None else sole.get("warehouse_id")
                try:
                    cand = int(float(str(raw).strip()))
                    if cand > 0:
                        wid = cand
                except (TypeError, ValueError):
                    wid = None
        except Exception:
            wid = None

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
            if not out["default_warehouse_label"]:
                code = out["default_warehouse_code"]
                name = out["default_warehouse_name"]
                out["default_warehouse_label"] = (
                    f"{code} — {name}" if code and name else (code or name or str(wid))
                )
        except (TypeError, ValueError):
            pass
    return out


def _invoice_list_sources(cur: Any) -> list[tuple[str, frozenset[str]]]:
    """Live BILLHDR only (mobile sales source of truth)."""
    from mobile_backend.services.dashboard_service import _billhdr_column_names

    live_cols = _billhdr_column_names(cur)
    if not live_cols:
        return []
    return [("billhdr b", live_cols)]


def list_invoices(
    *,
    search: str = "",
    limit: int = 50,
    days: int = 90,
    date_from: str = "",
    date_to: str = "",
    customer_code: str = "",
    billing_type: str = "",
) -> list[dict[str, Any]]:
    """Recent sales invoices from live BILLHDR only (newest date first)."""
    from db.oracle_driver import cx_Oracle

    from db import billno_is_valid, coerce_billno
    from mobile_backend.database.oracle_pool import get_connection
    from mobile_backend.request_context import get_jwt
    from mobile_backend.services.dashboard_service import _to_float
    from mobile_backend.services.inventory_service import _pick_existing
    from mobile_backend.services.sales_service import _amount_expr

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
            sources = _invoice_list_sources(cur)
            if not sources:
                return []

            by_bill: dict[str, dict[str, Any]] = {}
            fetch_lim = max(lim * 3, lim)

            for fc, cols in sources:
                dc = _pick_existing(cols, ["BILLDATE", "BILL_DATE", "TXNDATE", "TRANSACTIONDATE", "DOCDATE"])
                amt = _amount_expr(cols)
                billno_col = _pick_existing(cols, ["BILLNO", "BILL_NO"])
                if not dc or not amt or not billno_col:
                    continue

                cust_col = _pick_existing(
                    cols, ["CUSTOMERCODE", "CUSTOMER_CODE", "CUSTCODE", "CUST_CODE"]
                )
                cust_name_col = _pick_existing(
                    cols, ["CUSTOMERNAME", "CUSTOMER_NAME", "CUSTNAME", "CUST_NAME"]
                )
                billtype_col = _pick_existing(cols, ["BILLTYPE", "BILL_TYPE"])
                orderno_col = _pick_existing(cols, ["ORDERNO", "ORDER_NO"])
                loc_col = _pick_existing(cols, ["LOCATIONCODE", "LOCATION_CODE"])
                return_col = _pick_existing(cols, ["RETURNFLAG", "RETURN_FLAG"])
                delflag_col = _pick_existing(cols, ["DELFLAG", "DEL_FLAG"])
                status_col = _pick_existing(cols, ["BILLSTATUS", "BILL_STATUS"])

                where: list[str] = []
                params: dict[str, Any] = {"lim": fetch_lim}

                if delflag_col:
                    where.append(f"NVL(b.{delflag_col}, 'N') NOT IN ('Y', 'y')")
                if status_col:
                    where.append(f"NVL(b.{status_col}, ' ') <> 'V'")
                if return_col:
                    where.append(f"NVL(b.{return_col}, 'N') <> 'Y'")
                where.append(f"({amt}) >= 0")

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
                         ORDER BY TRUNC(b.{dc}) DESC, b.{billno_col} DESC
                    )
                    WHERE ROWNUM <= :lim
                """
                try:
                    cur.execute(sql, params)
                    rows = cur.fetchall() or []
                except cx_Oracle.DatabaseError:
                    continue

                col_names = [d[0].lower() for d in cur.description or []]
                for row in rows:
                    raw = dict(zip(col_names, row))
                    billno = coerce_billno(raw.get("billno"))
                    if not billno_is_valid(billno):
                        continue
                    key = str(billno)
                    if key in by_bill:
                        continue  # prefer live BILLHDR row already stored
                    billdate = raw.get("billdate")
                    if hasattr(billdate, "strftime"):
                        billdate_s = billdate.strftime("%Y-%m-%d")
                    else:
                        billdate_s = str(billdate or "")[:10]

                    bt = str(raw.get("billtype") or "").strip().upper()
                    billing = "CREDIT" if bt.startswith("R") else "CASH"
                    by_bill[key] = {
                        "billno": billno,
                        "billdate": billdate_s,
                        "customer_code": str(raw.get("customer_code") or "").strip(),
                        "customer_name": str(raw.get("customer_name") or "").strip(),
                        "orderno": str(raw.get("orderno") or "").strip(),
                        "net_amount": _to_float(raw.get("net_amount")),
                        "billtype": bt[:1] if bt else "C",
                        "billing_type": billing,
                    }

            def _sort_key(item: dict[str, Any]) -> tuple:
                d = str(item.get("billdate") or "")
                bn = str(item.get("billno") or "")
                digits = "".join(ch for ch in bn if ch.isdigit())
                try:
                    bn_num = int(digits) if digits else 0
                except ValueError:
                    bn_num = 0
                return (d, bn_num, bn)

            out = sorted(by_bill.values(), key=_sort_key, reverse=True)
            return out[:lim]


def _bill_hdr_dtl_pairs(cur: Any) -> list[tuple[str, str]]:
    """Prefer history tables when present (matches invoice list source)."""
    from mobile_backend.services.sales_service import _table_columns

    pairs: list[tuple[str, str]] = []
    for hdr, dtl in (("BILLHDRHISTORY", "BILLDTLHISTORY"), ("BILLHDR", "BILLDTL")):
        if _table_columns(cur, hdr) and _table_columns(cur, dtl):
            pairs.append((hdr.lower(), dtl.lower()))
    return pairs


def get_invoice_detail(billno: Any) -> dict[str, Any] | None:
    """Load one posted sales invoice header + line items."""
    from db import billno_is_valid, coerce_billno, parse_billno_from_request
    from db.oracle_driver import cx_Oracle

    from mobile_backend.database.oracle_pool import get_connection
    from mobile_backend.request_context import get_jwt
    from mobile_backend.services.inventory_service import _pick_existing
    from mobile_backend.services.sales_service import _table_columns

    bn = parse_billno_from_request(billno)
    if not billno_is_valid(bn):
        return None

    claims = get_jwt()
    tenant_id = claims.get("tenant_id")

    with _erp_session_scope():
        loc = _location_code()
        conn = get_connection(tenant_id=tenant_id)
        with conn.cursor() as cur:
            for hdr_table, dtl_table in _bill_hdr_dtl_pairs(cur):
                hdr_cols = _table_columns(cur, hdr_table.upper())
                dtl_cols = _table_columns(cur, dtl_table.upper())
                if not hdr_cols or not dtl_cols:
                    continue

                billno_hdr = _pick_existing(hdr_cols, ["BILLNO", "BILL_NO"]) or "BILLNO"
                billno_dtl = _pick_existing(dtl_cols, ["BILLNO", "BILL_NO"]) or "BILLNO"
                date_col = _pick_existing(
                    hdr_cols,
                    ["BILLDATE", "BILL_DATE", "SALESDATE", "TRNDATE", "INVOICEDATE"],
                )
                amt_col = _pick_existing(
                    hdr_cols,
                    ["NETBILLAMOUNT", "NETAMOUNT", "NET_AMOUNT", "TOTALAMOUNT", "BILLAMOUNT"],
                )
                cust_col = _pick_existing(hdr_cols, ["CUSTOMERCODE", "CUSTOMER_CODE", "CUSTCODE"])
                cust_name_col = _pick_existing(
                    hdr_cols,
                    ["CUSTOMERNAME", "CUSTOMER_NAME", "CUSTNAME"],
                )
                billtype_col = _pick_existing(hdr_cols, ["BILLTYPE", "BILL_TYPE"])
                orderno_col = _pick_existing(hdr_cols, ["ORDERNO", "ORDER_NO"])
                loc_hdr = _pick_existing(hdr_cols, ["LOCATIONCODE", "LOCATION_CODE"])
                loc_dtl = _pick_existing(dtl_cols, ["LOCATIONCODE", "LOCATION_CODE"])

                hdr_where = [f"h.{billno_hdr} = :bn"]
                params: dict[str, Any] = {"bn": bn}
                if loc_hdr and loc:
                    hdr_where.append(f"h.{loc_hdr} = :loc")
                    params["loc"] = int(loc)

                hdr_select = [
                    f"h.{billno_hdr} AS billno",
                    f"TRUNC(h.{date_col}) AS billdate" if date_col else "CAST(NULL AS DATE) AS billdate",
                ]
                if amt_col:
                    hdr_select.append(f"NVL(h.{amt_col}, 0) AS net_amount")
                else:
                    hdr_select.append("0 AS net_amount")
                if cust_col:
                    hdr_select.append(f"h.{cust_col} AS customer_code")
                if cust_name_col:
                    hdr_select.append(f"h.{cust_name_col} AS customer_name")
                if billtype_col:
                    hdr_select.append(f"h.{billtype_col} AS billtype")
                if orderno_col:
                    hdr_select.append(f"h.{orderno_col} AS orderno")

                hdr_sql = f"""
                    SELECT {", ".join(hdr_select)}
                      FROM {hdr_table} h
                     WHERE {" AND ".join(hdr_where)}
                """
                try:
                    cur.execute(hdr_sql, params)
                    hrow = cur.fetchone()
                except cx_Oracle.DatabaseError:
                    continue
                if not hrow:
                    continue

                hcols = [d[0].lower() for d in cur.description or []]
                hdr = dict(zip(hcols, hrow))
                billdate = hdr.get("billdate")
                if hasattr(billdate, "strftime"):
                    billdate_s = billdate.strftime("%Y-%m-%d")
                else:
                    billdate_s = str(billdate or "")[:10]
                bt = str(hdr.get("billtype") or "").strip().upper()
                billing = "CREDIT" if bt.startswith("R") else "CASH"

                line_no_col = _pick_existing(
                    dtl_cols,
                    ["SLNO", "SL_NO", "LINENO", "LINE_NO", "SERIALNO"],
                )
                item_col = _pick_existing(dtl_cols, ["ITEMCODE", "ITEM_CODE", "CODE"])
                qty_col = _pick_existing(dtl_cols, ["QUANTITY", "QTY", "BILLQTY", "BILL_QTY"])
                uom_col = _pick_existing(
                    dtl_cols,
                    ["UNITOFMEASUREMENT", "UOM", "UOMCODE", "UNIT"],
                )
                rate_col = _pick_existing(dtl_cols, ["RATE", "SELLRATE", "PRICE", "UNITPRICE"])
                disc_col = _pick_existing(dtl_cols, ["ITDISC", "DISCOUNT", "DISC", "ITEMDISC"])
                net_col = _pick_existing(
                    dtl_cols,
                    ["NETAMOUNT", "NET_AMOUNT", "LINEAMOUNT", "AMOUNT", "TOTAL"],
                )
                if not item_col:
                    continue

                if net_col:
                    amt_expr = f"NVL(d.{net_col}, 0)"
                elif qty_col and rate_col:
                    disc_expr = f"NVL(d.{disc_col}, 0)" if disc_col else "0"
                    amt_expr = f"NVL(d.{qty_col}, 0) * NVL(d.{rate_col}, 0) - {disc_expr}"
                else:
                    amt_expr = "0"

                qty_expr = f"NVL(d.{qty_col}, 0)" if qty_col else "0"
                rate_expr = f"NVL(d.{rate_col}, 0)" if rate_col else "0"
                disc_expr = f"NVL(d.{disc_col}, 0)" if disc_col else "0"
                uom_expr = f"NVL(d.{uom_col}, '')" if uom_col else "''"
                line_expr = (
                    f"NVL(d.{line_no_col}, 0) AS line_no"
                    if line_no_col
                    else f"ROW_NUMBER() OVER (ORDER BY d.{item_col}) AS line_no"
                )

                item_cols = _table_columns(cur, "ITEMMASTER")
                item_table = "itemmaster" if item_cols else None
                ic = _pick_existing(item_cols, ["ITEMCODE", "ITEM_CODE"]) if item_cols else None
                name_col = _pick_existing(
                    item_cols,
                    ["ITEMNAME", "ITEMDESC", "ITEM_NAME", "NAME"],
                ) if item_cols else None
                if item_table and ic and name_col:
                    name_expr = f"NVL(i.{name_col}, TO_CHAR(d.{item_col}))"
                    join_item = f"LEFT JOIN {item_table} i ON i.{ic} = d.{item_col}"
                else:
                    name_expr = f"TO_CHAR(d.{item_col})"
                    join_item = ""

                dtl_where = [f"d.{billno_dtl} = :bn"]
                dtl_params: dict[str, Any] = {"bn": bn}
                if loc_dtl and loc:
                    dtl_where.append(f"d.{loc_dtl} = :loc")
                    dtl_params["loc"] = int(loc)

                order_by = f"d.{line_no_col}" if line_no_col else f"d.{item_col}"
                line_sql = f"""
                    SELECT {line_expr},
                           TO_CHAR(d.{item_col}) AS item_code,
                           {name_expr} AS item_name,
                           {uom_expr} AS uom,
                           {qty_expr} AS qty,
                           {rate_expr} AS rate,
                           {disc_expr} AS discount,
                           {amt_expr} AS amount
                      FROM {dtl_table} d
                      {join_item}
                     WHERE {" AND ".join(dtl_where)}
                     ORDER BY {order_by}
                """
                try:
                    cur.execute(line_sql, dtl_params)
                    lrows = cur.fetchall() or []
                except cx_Oracle.DatabaseError:
                    lrows = []

                lcols = [d[0].lower() for d in cur.description or []]
                lines: list[dict[str, Any]] = []
                for lrow in lrows:
                    raw = dict(zip(lcols, lrow))
                    lines.append(
                        {
                            "line_no": int(float(raw.get("line_no") or 0)),
                            "item_code": str(raw.get("item_code") or "").strip(),
                            "item_name": str(raw.get("item_name") or "").strip(),
                            "uom": str(raw.get("uom") or "").strip(),
                            "qty": _to_float(raw.get("qty")),
                            "rate": _to_float(raw.get("rate")),
                            "discount": _to_float(raw.get("discount")),
                            "amount": _to_float(raw.get("amount")),
                        }
                    )

                return {
                    "billno": coerce_billno(hdr.get("billno") or bn),
                    "billdate": billdate_s,
                    "customer_code": str(hdr.get("customer_code") or "").strip(),
                    "customer_name": str(hdr.get("customer_name") or "").strip(),
                    "orderno": str(hdr.get("orderno") or "").strip(),
                    "net_amount": _to_float(hdr.get("net_amount")),
                    "billtype": bt[:1] if bt else "C",
                    "billing_type": billing,
                    "lines": lines,
                }
    return None


def get_customer_last_sale(*, customer_code: str, days: int = 365) -> dict[str, Any] | None:
    """Most recent posted sales invoice for a customer, with line items (for reorder)."""
    cust = (customer_code or "").strip()
    if not cust or cust in ("0", "00"):
        raise ValueError("A customer is required to reorder the last sale.")

    rows = list_invoices(
        customer_code=cust,
        limit=1,
        days=max(30, min(int(days or 365), 730)),
    )
    if not rows:
        return None
    billno = rows[0].get("billno")
    if billno is None or str(billno).strip() == "":
        return None
    detail = get_invoice_detail(billno)
    if not detail:
        return None
    lines = [
        ln
        for ln in (detail.get("lines") or [])
        if str(ln.get("item_code") or "").strip() and _to_float(ln.get("qty")) > 0
    ]
    if not lines:
        return None
    return {
        "billno": detail.get("billno"),
        "billdate": detail.get("billdate"),
        "customer_code": detail.get("customer_code") or cust,
        "customer_name": detail.get("customer_name") or "",
        "net_amount": detail.get("net_amount"),
        "billing_type": detail.get("billing_type"),
        "line_count": len(lines),
        "lines": lines,
    }


def list_customer_previous_items(
    *,
    customer_code: str,
    warehouse_id: str | None = None,
    limit: int = 80,
    days: int = 365,
) -> list[dict[str, Any]]:
    """Distinct items previously sold to a customer (newest activity first).

    Used by Sales / Sales Order item picker \"Customer items\" tab.
    """
    from db.oracle_driver import cx_Oracle

    from mobile_backend.database.oracle_pool import get_connection
    from mobile_backend.request_context import get_jwt
    from mobile_backend.services.inventory_service import _pick_existing
    from mobile_backend.services.sales_service import _table_columns

    cust = (customer_code or "").strip()
    if not cust or cust in ("0", "00"):
        return []

    lim = max(1, min(int(limit or 80), 200))
    day_span = max(30, min(int(days or 365), 730))
    wh_raw = (warehouse_id or "").strip()
    claims = get_jwt()
    tenant_id = claims.get("tenant_id")

    aggregated: dict[str, dict[str, Any]] = {}

    with _erp_session_scope():
        loc = _location_code()
        conn = get_connection(tenant_id=tenant_id)
        with conn.cursor() as cur:
            pairs = _bill_hdr_dtl_pairs(cur)
            if not pairs:
                return []

            for hdr_table, dtl_table in pairs:
                hdr_cols = _table_columns(cur, hdr_table.upper())
                dtl_cols = _table_columns(cur, dtl_table.upper())
                if not hdr_cols or not dtl_cols:
                    continue

                billno_h = _pick_existing(hdr_cols, ["BILLNO", "BILL_NO"]) or "BILLNO"
                billno_d = _pick_existing(dtl_cols, ["BILLNO", "BILL_NO"]) or "BILLNO"
                date_col = _pick_existing(
                    hdr_cols,
                    ["BILLDATE", "BILL_DATE", "SALESDATE", "TRNDATE", "INVOICEDATE"],
                )
                cust_col = _pick_existing(hdr_cols, ["CUSTOMERCODE", "CUSTOMER_CODE", "CUSTCODE"])
                loc_h = _pick_existing(hdr_cols, ["LOCATIONCODE", "LOCATION_CODE"])
                loc_d = _pick_existing(dtl_cols, ["LOCATIONCODE", "LOCATION_CODE"])
                item_col = _pick_existing(dtl_cols, ["ITEMCODE", "ITEM_CODE", "CODE"])
                qty_col = _pick_existing(dtl_cols, ["QUANTITY", "QTY", "BILLQTY"])
                rate_col = _pick_existing(dtl_cols, ["RATE", "SELLRATE", "PRICE", "UNITPRICE"])
                uom_col = _pick_existing(
                    dtl_cols,
                    ["UNITOFMEASUREMENT", "UOM", "UOMCODE", "UNIT"],
                )
                delflag = _pick_existing(hdr_cols, ["DELFLAG", "DEL_FLAG"])
                status_col = _pick_existing(hdr_cols, ["BILLSTATUS", "BILL_STATUS"])
                return_col = _pick_existing(hdr_cols, ["RETURNFLAG", "RETURN_FLAG"])
                if not cust_col or not item_col or not qty_col or not date_col:
                    continue

                join = [f"d.{billno_d} = h.{billno_h}"]
                if loc_h and loc_d:
                    join.append(f"d.{loc_d} = h.{loc_h}")

                where = [
                    f"TRIM(TO_CHAR(h.{cust_col})) = :cust",
                    f"NVL(d.{qty_col}, 0) > 0",
                    f"TRUNC(h.{date_col}) >= TRUNC(SYSDATE) - :days + 1",
                ]
                params: dict[str, Any] = {"cust": cust, "days": day_span, "lim": lim * 8}
                if loc_h and loc:
                    where.append(f"h.{loc_h} = :loc")
                    params["loc"] = int(loc)
                elif loc_d and loc:
                    where.append(f"d.{loc_d} = :loc")
                    params["loc"] = int(loc)
                if delflag:
                    where.append(f"NVL(h.{delflag}, 'N') NOT IN ('Y', 'y')")
                if status_col:
                    where.append(f"NVL(h.{status_col}, ' ') <> 'V'")
                if return_col:
                    where.append(f"NVL(h.{return_col}, 'N') <> 'Y'")

                item_cols = _table_columns(cur, "ITEMMASTER")
                ic = _pick_existing(item_cols, ["ITEMCODE", "ITEM_CODE"]) if item_cols else None
                name_col = (
                    _pick_existing(item_cols, ["ITEMNAME", "ITEMDESC", "ITEM_NAME", "NAME"])
                    if item_cols
                    else None
                )
                retail_col = (
                    _pick_existing(item_cols, ["RETAILPRICE", "RETAIL_PRICE", "SELLPRICE"])
                    if item_cols
                    else None
                )
                base_uom_col = (
                    _pick_existing(item_cols, ["BASEUOM", "BASE_UOM", "UOM"]) if item_cols else None
                )
                brand_col = _pick_existing(item_cols, ["BRAND", "MICRO"]) if item_cols else None
                barcode_col = (
                    _pick_existing(item_cols, ["MANUFACTURERID", "BARCODE", "MFRID"])
                    if item_cols
                    else None
                )

                if item_cols and ic and name_col:
                    name_expr = f"NVL(i.{name_col}, TO_CHAR(d.{item_col}))"
                    join_item = f"LEFT JOIN itemmaster i ON i.{ic} = d.{item_col}"
                    if loc and _pick_existing(item_cols, ["LOCATIONCODE", "LOCATION_CODE"]):
                        loc_i = _pick_existing(item_cols, ["LOCATIONCODE", "LOCATION_CODE"])
                        join_item += f" AND i.{loc_i} = :iloc"
                        params["iloc"] = int(loc)
                    retail_expr = f"NVL(i.{retail_col}, 0)" if retail_col else "0"
                    unit_fallback = f"NVL(i.{base_uom_col}, 'PCS')" if base_uom_col else "'PCS'"
                    brand_expr = f"NVL(i.{brand_col}, '')" if brand_col else "''"
                    barcode_expr = f"NVL(i.{barcode_col}, '')" if barcode_col else "''"
                else:
                    name_expr = f"TO_CHAR(d.{item_col})"
                    join_item = ""
                    retail_expr = "0"
                    unit_fallback = "'PCS'"
                    brand_expr = "''"
                    barcode_expr = "''"

                uom_expr = f"NVL(NULLIF(TRIM(d.{uom_col}), ''), {unit_fallback})" if uom_col else unit_fallback
                rate_expr = f"NVL(d.{rate_col}, 0)" if rate_col else "0"

                sql = f"""
                    SELECT * FROM (
                        SELECT d.{item_col} AS item_code,
                               {name_expr} AS item_name,
                               {uom_expr} AS unit,
                               {rate_expr} AS last_rate,
                               {retail_expr} AS retail_price,
                               NVL(d.{qty_col}, 0) AS last_qty,
                               TRUNC(h.{date_col}) AS billdate,
                               h.{billno_h} AS billno,
                               {brand_expr} AS brand,
                               {barcode_expr} AS barcode
                          FROM {dtl_table} d
                         INNER JOIN {hdr_table} h ON {" AND ".join(join)}
                          {join_item}
                         WHERE {" AND ".join(where)}
                         ORDER BY TRUNC(h.{date_col}) DESC, h.{billno_h} DESC
                    ) WHERE ROWNUM <= :lim
                """
                try:
                    cur.execute(sql, params)
                    rows = cur.fetchall() or []
                except cx_Oracle.DatabaseError:
                    continue

                cols = [d[0].lower() for d in cur.description or []]
                for raw_row in rows:
                    raw = dict(zip(cols, raw_row))
                    code = str(raw.get("item_code") or "").strip()
                    if not code:
                        continue
                    billdate = raw.get("billdate")
                    if hasattr(billdate, "strftime"):
                        billdate_s = billdate.strftime("%Y-%m-%d")
                    else:
                        billdate_s = str(billdate or "")[:10]
                    existing = aggregated.get(code)
                    if existing is None:
                        rate = _to_float(raw.get("retail_price"))
                        if rate <= 0:
                            rate = _to_float(raw.get("last_rate"))
                        aggregated[code] = {
                            "item_code": code,
                            "item_name": str(raw.get("item_name") or "").strip(),
                            "unit": str(raw.get("unit") or "PCS").strip() or "PCS",
                            "rate": rate,
                            "stock": 0.0,
                            "brand": str(raw.get("brand") or "").strip(),
                            "barcode": str(raw.get("barcode") or "").strip(),
                            "last_qty": _to_float(raw.get("last_qty")),
                            "last_rate": _to_float(raw.get("last_rate")),
                            "last_billdate": billdate_s,
                            "last_billno": str(raw.get("billno") or "").strip(),
                            "times_ordered": 1,
                        }
                    else:
                        existing["times_ordered"] = int(existing.get("times_ordered") or 1) + 1
                        # Keep newest bill fields (query is newest-first; first write wins).

            # Overlay warehouse stock when requested.
            if wh_raw.isdigit() and aggregated:
                try:
                    stock_map = _warehouse_stock_qty_map(int(wh_raw), int(loc or 0))
                    for code, row in aggregated.items():
                        row["stock"] = stock_map.get(code, 0.0)
                except Exception:
                    pass
            elif aggregated:
                # Fall back to item master current stock via catalog normalize when possible.
                for code in list(aggregated.keys())[:lim]:
                    try:
                        item = None
                        from db import get_item_by_code

                        if code.isdigit():
                            item = get_item_by_code(int(code), loc)
                        if item:
                            stk = item.get("CURRENTSTOCK") or item.get("currentstock") or 0
                            retail = item.get("RETAILPRICE") or item.get("retailprice") or 0
                            cost = item.get("COSTPRICE") or item.get("costprice") or 0
                            avg = item.get("AVERAGECOST") or item.get("averagecost") or 0
                            aggregated[code]["stock"] = _to_float(stk)
                            if _to_float(retail) > 0:
                                aggregated[code]["rate"] = _to_float(retail)
                            aggregated[code]["cost_price"] = _to_float(cost)
                            aggregated[code]["average_cost"] = _to_float(avg)
                            name = item.get("ITEMNAME") or item.get("itemname")
                            if name and not aggregated[code].get("item_name"):
                                aggregated[code]["item_name"] = str(name).strip()
                    except Exception:
                        continue

    out = list(aggregated.values())
    out.sort(
        key=lambda r: (
            str(r.get("last_billdate") or ""),
            int(r.get("times_ordered") or 0),
        ),
        reverse=True,
    )
    return out[:lim]


def get_invoice_open_context(*, peek_billno: bool = True) -> dict[str, Any]:
    from addons.document_numbering.document_numbering_db import DOC_TYPE_SALES_INVOICE
    from db import get_location_info_by_dbkey, get_next_bill_no
    from mobile_backend.services.transaction_date_helper import (
        missing_setup_date_message,
        open_context as txn_open_context,
    )

    with _erp_session_scope() as username:
        loc = _location_code()
        txn = txn_open_context("sales", location_code=loc)
        bill_date = str(txn.get("preferred_date") or "")[:10]
        if not bill_date:
            raise ValueError(txn.get("transaction_date_error") or missing_setup_date_message("sales"))
        if peek_billno:
            billno = _fresh_peek_billno(loc, DOC_TYPE_SALES_INVOICE)
            reserved = False
        else:
            billno = get_next_bill_no(loc, None, doc_type=DOC_TYPE_SALES_INVOICE)
            reserved = True
        info = get_location_info_by_dbkey(None) or {}
        features = _sales_features()
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


def list_customers(
    *,
    search: str = "",
    limit: int = 50,
    billing_type: str = "",
) -> list[dict[str, Any]]:
    """Customer picker rows — master data only; GL outstanding loaded on selection."""
    from db import get_customers_master_list, normalize_customer_billing_type

    lim = max(1, min(int(limit or 50), 200))
    q = (search or "").strip()
    bt_raw = (billing_type or "").strip().upper()
    bt = normalize_customer_billing_type(bt_raw) if bt_raw else ""
    if bt_raw and bt not in ("CASH", "CREDIT"):
        bt = ""
    with _erp_session_scope():
        rows = get_customers_master_list(
            for_picker=True,
            picker_search=q,
            picker_limit=lim,
            picker_billing_type=bt,
        )
        out: list[dict[str, Any]] = []
        for raw in rows or []:
            row = _normalize_customer_row(dict(raw), include_gl=False)
            # Safety net when schema has no billing column to filter in SQL.
            if bt and str(row.get("billing_type") or "").strip().upper() != bt:
                continue
            out.append(row)
        return out


def get_customer_outstanding(customer_code: str) -> dict[str, Any]:
    """Fresh GL receivable outstanding for one customer (Accounts Receivable parity)."""
    from db import _customer_gl_receivable_context

    with _erp_session_scope():
        raw = _find_customer_master_row(customer_code)
        if not raw:
            raise ValueError("Customer not found.")
        gl_ctx = _customer_gl_receivable_context()
        return _normalize_customer_row(raw, gl_ctx=gl_ctx)


def lookup_item(query: str) -> dict[str, Any]:
    from db import (
        get_item_by_alternate_barcode,
        get_item_by_code,
        get_item_by_manufacturer_id,
    )

    q = (query or "").strip()
    if not q:
        raise ValueError("Item code or barcode is required.")

    with _erp_session_scope():
        loc = _location_code()
        item = None
        if q.isdigit():
            try:
                item = get_item_by_code(int(q), loc)
            except Exception:
                item = None
        if not item:
            item = get_item_by_manufacturer_id(q, loc)
        if not item:
            item = get_item_by_alternate_barcode(q, loc)
        if not item:
            raise ValueError("Item not found.")
        return _normalize_item_row(dict(item))


def list_item_uoms(item_code: str) -> list[dict[str, Any]]:
    from db import get_item_alternate_uoms, get_item_by_code

    code = (item_code or "").strip()
    if not code.isdigit():
        raise ValueError("Invalid item code.")
    with _erp_session_scope():
        loc = _location_code()
        item = get_item_by_code(int(code), loc)
        if not item:
            raise ValueError("Item not found.")
        base_uom = str(item.get("BASEUOM") or item.get("baseuom") or "").strip()
        uoms: list[dict[str, Any]] = []
        if base_uom:
            uoms.append({"code": base_uom, "name": base_uom, "is_base": True})
        for alt in get_item_alternate_uoms(loc, int(code)) or []:
            alt_code = str(alt.get("alternateuomcode") or "").strip()
            if not alt_code:
                continue
            if base_uom and alt_code.upper() == base_uom.upper():
                continue
            uoms.append(
                {
                    "code": alt_code,
                    "name": alt_code,
                    "is_base": False,
                    "conversion_factor": alt.get("conversionfactor"),
                }
            )
        return uoms


def get_uom_pricing(item_code: str, uom_code: str, *, price_mode: str = "retail") -> dict[str, Any]:
    from db import get_item_uom_pricing

    ic = (item_code or "").strip()
    uc = (uom_code or "").strip()
    if not ic.isdigit() or not uc:
        raise ValueError("Item code and UOM are required.")
    with _erp_session_scope():
        loc = _location_code()
        pricing = get_item_uom_pricing(loc, int(ic), uc, (price_mode or "retail").lower())
        if not pricing:
            raise ValueError("UOM not available for this item.")
        return {
            "uom_code": str(pricing.get("uom_code") or uc),
            "is_base": bool(pricing.get("is_base")),
            "conversion_factor": float(pricing.get("conversion_factor") or 1),
            "rate": float(pricing.get("rate") or 0),
            "cost_price": float(pricing.get("cost_price") or 0),
            "average_cost": float(pricing.get("average_cost") or 0),
        }


def get_item_last_sale(item_code: str, *, customer_code: str = "") -> dict[str, Any] | None:
    """Most recent posted sale line for an item (customer-scoped when customer_code set)."""
    from db.oracle_driver import cx_Oracle

    from mobile_backend.database.oracle_pool import get_connection
    from mobile_backend.request_context import get_jwt
    from mobile_backend.services.inventory_service import _pick_existing
    from mobile_backend.services.sales_service import _table_columns

    ic = (item_code or "").strip()
    if not ic.isdigit():
        raise ValueError("Invalid item code.")
    cust = (customer_code or "").strip()
    item_i = int(ic)

    claims = get_jwt()
    tenant_id = claims.get("tenant_id")

    with _erp_session_scope():
        loc = _location_code()
        conn = get_connection(tenant_id=tenant_id)
        with conn.cursor() as cur:
            pairs = _bill_hdr_dtl_pairs(cur)
            if not pairs:
                return None

            best: dict[str, Any] | None = None
            scoped_best: dict[str, Any] | None = None

            for hdr_table, dtl_table in pairs:
                hdr_cols = _table_columns(cur, hdr_table.upper())
                dtl_cols = _table_columns(cur, dtl_table.upper())
                if not hdr_cols or not dtl_cols:
                    continue

                billno_h = _pick_existing(hdr_cols, ["BILLNO", "BILL_NO"]) or "BILLNO"
                billno_d = _pick_existing(dtl_cols, ["BILLNO", "BILL_NO"]) or "BILLNO"
                date_col = _pick_existing(
                    hdr_cols,
                    ["BILLDATE", "BILL_DATE", "SALESDATE", "TRNDATE", "INVOICEDATE"],
                )
                cust_col = _pick_existing(hdr_cols, ["CUSTOMERCODE", "CUSTOMER_CODE", "CUSTCODE"])
                cust_name_col = _pick_existing(
                    hdr_cols,
                    ["CUSTOMERNAME", "CUSTOMER_NAME", "CUSTNAME"],
                )
                loc_h = _pick_existing(hdr_cols, ["LOCATIONCODE", "LOCATION_CODE"])
                loc_d = _pick_existing(dtl_cols, ["LOCATIONCODE", "LOCATION_CODE"])
                item_col = _pick_existing(dtl_cols, ["ITEMCODE", "ITEM_CODE", "CODE"])
                qty_col = _pick_existing(dtl_cols, ["QUANTITY", "QTY", "BILLQTY"])
                rate_col = _pick_existing(dtl_cols, ["RATE", "SELLRATE", "PRICE", "UNITPRICE"])
                uom_col = _pick_existing(
                    dtl_cols,
                    ["UNITOFMEASUREMENT", "UOM", "UOMCODE", "UNIT"],
                )
                disc_col = _pick_existing(dtl_cols, ["ITDISC", "DISCOUNT", "DISC", "ITEMDISC"])
                delflag = _pick_existing(hdr_cols, ["DELFLAG", "DEL_FLAG"])
                status_col = _pick_existing(hdr_cols, ["BILLSTATUS", "BILL_STATUS"])
                return_col = _pick_existing(hdr_cols, ["RETURNFLAG", "RETURN_FLAG"])
                if not item_col or not qty_col or not rate_col:
                    continue

                join = [f"d.{billno_d} = h.{billno_h}"]
                if loc_h and loc_d:
                    join.append(f"d.{loc_d} = h.{loc_h}")

                where = [f"d.{item_col} = :item", f"NVL(d.{qty_col}, 0) > 0"]
                params: dict[str, Any] = {"item": item_i}
                if loc_d and loc:
                    where.append(f"d.{loc_d} = :loc")
                    params["loc"] = int(loc)
                elif loc_h and loc:
                    where.append(f"h.{loc_h} = :loc")
                    params["loc"] = int(loc)
                if delflag:
                    where.append(f"NVL(h.{delflag}, 'N') NOT IN ('Y', 'y')")
                if status_col:
                    where.append(f"NVL(h.{status_col}, ' ') <> 'V'")
                if return_col:
                    where.append(f"NVL(h.{return_col}, 'N') <> 'Y'")

                order_expr = (
                    f"h.{date_col} DESC NULLS LAST, h.{billno_h} DESC"
                    if date_col
                    else f"h.{billno_h} DESC"
                )
                date_sel = (
                    f"TO_CHAR(TRUNC(h.{date_col}), 'YYYY-MM-DD')"
                    if date_col
                    else "CAST(NULL AS VARCHAR2(10))"
                )
                cust_sel = f"TO_CHAR(h.{cust_col})" if cust_col else "CAST(NULL AS VARCHAR2(40))"
                name_sel = f"NVL(h.{cust_name_col}, '')" if cust_name_col else "CAST('' AS VARCHAR2(200))"
                uom_sel = f"NVL(d.{uom_col}, '')" if uom_col else "CAST('' AS VARCHAR2(40))"
                disc_sel = f"NVL(d.{disc_col}, 0)" if disc_col else "0"

                def _fetch_one(extra_where: list[str], extra_params: dict[str, Any]) -> dict[str, Any] | None:
                    sql = f"""
                        SELECT * FROM (
                            SELECT TO_CHAR(h.{billno_h}) AS billno,
                                   {date_sel} AS billdate,
                                   {cust_sel} AS customer_code,
                                   {name_sel} AS customer_name,
                                   NVL(d.{qty_col}, 0) AS qty,
                                   {uom_sel} AS uom,
                                   NVL(d.{rate_col}, 0) AS rate,
                                   {disc_sel} AS discount
                              FROM {dtl_table} d
                              INNER JOIN {hdr_table} h ON {" AND ".join(join)}
                             WHERE {" AND ".join(where + extra_where)}
                             ORDER BY {order_expr}
                        )
                        WHERE ROWNUM <= 1
                    """
                    bind = dict(params)
                    bind.update(extra_params)
                    try:
                        cur.execute(sql, bind)
                        row = cur.fetchone()
                    except cx_Oracle.DatabaseError:
                        return None
                    if not row:
                        return None
                    cols = [d[0].lower() for d in cur.description or []]
                    return dict(zip(cols, row))

                # Prefer last sale for selected customer, then any customer.
                if cust and cust_col and scoped_best is None:
                    scoped_best = _fetch_one(
                        [f"TRIM(TO_CHAR(h.{cust_col})) = :cust"],
                        {"cust": cust},
                    )
                if best is None:
                    best = _fetch_one([], {})

            row = scoped_best or best
            if not row:
                return None

            qty = _to_float(row.get("qty"))
            rate = _to_float(row.get("rate"))
            disc = _to_float(row.get("discount"))
            cust_code = str(row.get("customer_code") or "").strip()
            cust_name = str(row.get("customer_name") or "").strip()
            scoped = scoped_best is not None and row is scoped_best
            if scoped and not cust_name:
                cust_name = cust
            return {
                "billno": str(row.get("billno") or "").strip(),
                "billdate": str(row.get("billdate") or "")[:10],
                "customer_code": cust_code or (cust if scoped else ""),
                "customer_name": cust_name,
                "qty": abs(qty),
                "uom": str(row.get("uom") or "").strip(),
                "rate": rate,
                "discount": disc,
                "net_rate": max(rate - disc, 0.0),
                "for_selected_customer": scoped,
            }


def _normalize_catalog_row(row: dict[str, Any], stock: float | None = None) -> dict[str, Any]:
    ic = row.get("itemcode") or row.get("ITEMCODE") or row.get("item_code")
    name = (
        row.get("display_item_name")
        or row.get("itemname")
        or row.get("ITEMNAME")
        or row.get("item_name")
        or ""
    )
    unit = row.get("unit") or row.get("baseuom") or row.get("BASEUOM") or "PCS"
    rate = row.get("retailprice") or row.get("RETAILPRICE") or row.get("rate") or 0
    stk = stock if stock is not None else row.get("stock") or row.get("STOCK") or row.get("qty") or 0
    cost = (
        row.get("costprice")
        or row.get("COSTPRICE")
        or row.get("cost_price")
        or row.get("cost")
        or 0
    )
    avg = (
        row.get("averagecost")
        or row.get("AVERAGECOST")
        or row.get("average_cost")
        or row.get("avgcost")
        or 0
    )
    return {
        "item_code": str(ic or "").strip(),
        "item_name": str(name or "").strip(),
        "unit": str(unit or "PCS").strip(),
        "rate": _to_float(rate),
        "stock": _to_float(stk),
        "brand": str(row.get("brand") or row.get("micro") or "").strip(),
        "barcode": str(row.get("manufacturerid") or row.get("MANUFACTURERID") or "").strip(),
        "cost_price": _to_float(cost),
        "average_cost": _to_float(avg),
    }


def _norm_alnum(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def _catalog_fuzzy_score(query: str, *parts: str) -> float:
    """Typo score for short queries only (e.g. ``chich`` → ``CHICKEN``).

    Full keywords like ``chicken`` use contains-match elsewhere — they must appear
    inside name/code/barcode, not merely share a ``CHI`` stem with CHILDREN/CHIPS.
    """
    q = _norm_alnum(query)
    if not (_FUZZY_MIN_QUERY_LEN <= len(q) <= _FUZZY_MAX_QUERY_LEN):
        return 0.0
    hay = " ".join(str(p or "") for p in parts).upper()
    words = re.findall(r"[A-Z0-9]+", hay)
    if not words:
        return 0.0
    best = 0.0
    stem3 = q[:3]
    for word in words:
        if len(word) < 3:
            continue
        # Keyword (or the item token) literally inside the other side.
        if q in word or word in q:
            best = max(best, 0.96 if q in word else 0.9)
            continue
        ratio = SequenceMatcher(None, q, word).ratio()
        if len(word) >= len(q):
            ratio = max(ratio, SequenceMatcher(None, q, word[: len(q) + 2]).ratio())
        # Strong edit similarity (chcken↔chicken).
        if ratio >= 0.85:
            best = max(best, ratio)
            continue
        # Short typo with same 3-letter stem and similar length (chich↔chicken).
        if (
            word.startswith(stem3)
            and abs(len(word) - len(q)) <= 2
            and ratio >= 0.62
        ):
            best = max(best, 0.80)
    return best


def _catalog_fuzzy_seeds(query: str) -> list[str]:
    """Seeds for broader LIKE pulls — only for short typo queries."""
    q = _norm_alnum(query)
    if not (_FUZZY_MIN_QUERY_LEN <= len(q) <= _FUZZY_MAX_QUERY_LEN):
        return []
    seeds: list[str] = []
    for n in (4, 3):
        if len(q) >= n:
            s = q[:n]
            if s not in seeds:
                seeds.append(s)
    return seeds


def _should_fuzzy_fallback(query: str, exact_count: int) -> bool:
    """Fuzzy only when contains-search found nothing and the query looks like a typo."""
    if exact_count > 0:
        return False
    q = _norm_alnum(query)
    return _FUZZY_MIN_QUERY_LEN <= len(q) <= _FUZZY_MAX_QUERY_LEN


def _merge_exact_then_fuzzy(
    exact: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    *,
    query: str,
    limit: int,
) -> list[dict[str, Any]]:
    if not _should_fuzzy_fallback(query, len(exact)):
        return exact[:limit]
    seen = {str(r.get("item_code") or "").strip() for r in exact}
    scored: list[tuple[float, dict[str, Any]]] = []
    for row in candidates:
        code = str(row.get("item_code") or "").strip()
        if not code or code in seen:
            continue
        score = _catalog_fuzzy_score(
            query,
            code,
            str(row.get("item_name") or ""),
            str(row.get("barcode") or ""),
        )
        if score >= _FUZZY_SCORE_THRESHOLD:
            scored.append((score, row))
    scored.sort(key=lambda x: (-x[0], str(x[1].get("item_name") or "").upper()))
    out = list(exact)
    for _, row in scored:
        out.append(row)
        if len(out) >= limit:
            break
    return out[:limit]


def list_catalog_items(
    *,
    search: str = "",
    warehouse_id: str | None = None,
    customer_code: str | None = None,
    limit: int = 60,
    username: str = "mobile",
    for_return: bool = False,
    for_order: bool = False,
) -> list[dict[str, Any]]:
    """E-commerce style product list — warehouse stock when warehouse selected, else ERP item popup."""
    try:
        return _list_catalog_items_impl(
            search=search,
            warehouse_id=warehouse_id,
            customer_code=customer_code,
            limit=limit,
            username=username,
            for_return=for_return,
            for_order=for_order,
        )
    except Exception as exc:
        _log.exception("list_catalog_items failed")
        raise ValueError(f"Could not load product catalog: {exc}") from exc


def _warehouse_stock_qty_map(
    warehouse_id: int,
    location_code: int,
) -> dict[str, float]:
    """item_code → qty for one warehouse (includes zero rows when present)."""
    from db import get_warehouse_stock_list

    out: dict[str, float] = {}
    for ws in get_warehouse_stock_list(
        warehouse_id, location_code, include_zero=True, limit=8000
    ) or []:
        ic = ws.get("itemcode") or ws.get("ITEMCODE")
        if ic is None:
            continue
        try:
            code = str(int(ic))
        except (TypeError, ValueError):
            continue
        out[code] = _to_float(ws.get("qty") or ws.get("QTY"))
    return out


def _apply_warehouse_stock_overlay(
    rows: list[dict[str, Any]],
    stock_map: dict[str, float],
) -> list[dict[str, Any]]:
    for row in rows:
        code = str(row.get("item_code") or "").strip()
        if not code:
            continue
        row["stock"] = stock_map.get(code, 0.0)
    return rows


def _list_catalog_items_impl(
    *,
    search: str = "",
    warehouse_id: str | None = None,
    customer_code: str | None = None,
    limit: int = 60,
    username: str = "mobile",
    for_return: bool = False,
    for_order: bool = False,
) -> list[dict[str, Any]]:
    """Product catalog for Sales Invoice / Order / Return.

    ERP Sales Accounts Configuration:
    - Minus billing OFF → only items with stock (warehouse stock-first when WH selected)
    - Minus billing ON  → full item master (zero / never-stocked included); WH qty is info only
    - Sales Return      → always full item master
    Invoice uses MINUSBILLING; Order uses MINUSBILLING_ORDER.
    """
    from db import (
        get_item_by_code,
        get_item_popup_items,
        get_sales_minus_billing_invoice_enabled,
        get_sales_minus_billing_order_enabled,
        get_warehouse_stock_list,
    )

    features = _sales_features()
    wh_raw = (warehouse_id or "").strip()
    q_raw = (search or "").strip()
    search_tokens = [t for t in q_raw.upper().split() if t]

    with _erp_session_scope() as user:
        loc = _location_code()
        if for_return:
            enforce = False
        elif for_order:
            enforce = not get_sales_minus_billing_order_enabled()
        else:
            enforce = not get_sales_minus_billing_invoice_enabled()

        # Full-master lists (return / minus billing) allow a higher cap.
        lim = max(1, min(int(limit or 60), 500 if (for_return or not enforce) else 100))
        uname = user or username
        wh_id = int(wh_raw) if wh_raw.isdigit() else None

        # Minus billing OFF + warehouse: stock-first list (in-stock items only).
        if features["warehouse_enabled"] and wh_id is not None and enforce:
            wid = wh_id
            pool_cap = lim * 8 if search_tokens else lim * 4
            ws_rows = get_warehouse_stock_list(
                wid, loc, include_zero=False, limit=max(pool_cap, 80)
            )
            exact: list[dict[str, Any]] = []
            pool: list[dict[str, Any]] = []
            for ws in ws_rows or []:
                ic = ws.get("itemcode") or ws.get("ITEMCODE")
                if ic is None:
                    continue
                try:
                    ic_int = int(ic)
                except (TypeError, ValueError):
                    continue
                qty = _to_float(ws.get("qty") or ws.get("QTY"))
                if qty <= 0.0001:
                    continue
                item = get_item_by_code(ic_int, loc) or {}
                name = str(
                    item.get("ITEMNAME") or item.get("itemname") or ws.get("itemname") or ""
                ).strip()
                barcode = str(
                    item.get("MANUFACTURERID") or item.get("manufacturerid") or ""
                ).strip()
                row = {
                    "item_code": str(ic_int),
                    "item_name": name or f"Item {ic_int}",
                    "unit": str(
                        item.get("BASEUOM") or item.get("baseuom") or "PCS"
                    ).strip(),
                    "rate": _to_float(
                        item.get("RETAILPRICE") or item.get("retailprice")
                    ),
                    "stock": qty,
                    "brand": "",
                    "barcode": barcode,
                    "cost_price": _to_float(
                        item.get("COSTPRICE") or item.get("costprice")
                    ),
                    "average_cost": _to_float(
                        item.get("AVERAGECOST") or item.get("averagecost")
                    ),
                }
                pool.append(row)
                if search_tokens:
                    hay = f"{ic_int} {name} {barcode}".upper()
                    if all(t in hay for t in search_tokens):
                        exact.append(row)
                        if len(exact) >= lim:
                            break
                else:
                    exact.append(row)
                    if len(exact) >= lim:
                        break
            if not search_tokens:
                return exact[:lim]
            if exact or not _should_fuzzy_fallback(q_raw, len(exact)):
                return exact[:lim]
            return _merge_exact_then_fuzzy(exact, pool, query=q_raw, limit=lim)

        # Minus billing ON / return / no warehouse filter: full ITEMMASTER list.
        # Do not pass warehouse_id into the popup query — that would hide items never
        # stocked at the warehouse. Overlay WH qty afterward for display.
        rows = get_item_popup_items(
            location_code=loc,
            filter_key="all",
            search=q_raw,
            price_mode="retail",
            customer_code=(customer_code or "").strip() or None,
            enforce_stock_positive=enforce,
            limit=lim,
            user_id=uname,
            warehouse_id=None,
        )
        exact = [_normalize_catalog_row(dict(r)) for r in rows or []][:lim]
        stock_map: dict[str, float] = {}
        if features["warehouse_enabled"] and wh_id is not None and not enforce:
            stock_map = _warehouse_stock_qty_map(wh_id, loc)
            _apply_warehouse_stock_overlay(exact, stock_map)

        if not q_raw or exact or not _should_fuzzy_fallback(q_raw, len(exact)):
            return exact

        cand_map: dict[str, dict[str, Any]] = {}
        for seed in _catalog_fuzzy_seeds(q_raw):
            if seed.upper() == q_raw.upper():
                continue
            seed_rows = get_item_popup_items(
                location_code=loc,
                filter_key="all",
                search=seed,
                price_mode="retail",
                customer_code=(customer_code or "").strip() or None,
                enforce_stock_positive=enforce,
                limit=min(lim * 3, 180),
                user_id=uname,
                warehouse_id=None,
            )
            for raw in seed_rows or []:
                row = _normalize_catalog_row(dict(raw))
                code = str(row.get("item_code") or "").strip()
                if code and code not in cand_map:
                    cand_map[code] = row
        if stock_map:
            _apply_warehouse_stock_overlay(list(cand_map.values()), stock_map)
        return _merge_exact_then_fuzzy(
            exact,
            list(cand_map.values()),
            query=q_raw,
            limit=lim,
        )


def list_warehouses(*, search: str = "", limit: int = 100) -> list[dict[str, Any]]:
    from db.user_warehouse_prefs import apply_user_warehouse_filter, build_warehouse_picker_rows
    from nexa_http.session_wrap import session

    lim = max(1, min(int(limit or 100), 300))
    with _erp_session_scope() as username:
        if not _sales_features()["warehouse_enabled"]:
            return []
        loc = _location_code()
        rows = build_warehouse_picker_rows(int(loc), search=(search or "").strip(), limit=lim)
        uname = username or session.get("user")
        filtered = apply_user_warehouse_filter(uname, "sales", rows)
        out: list[dict[str, Any]] = []
        for r in filtered or []:
            wid = r.get("code") or r.get("warehouse_id")
            out.append(
                {
                    "warehouse_id": str(wid or "").strip(),
                    "warehouse_code": str(r.get("store") or r.get("warehouse_code") or "").strip(),
                    "warehouse_name": str(r.get("name") or r.get("warehouse_name") or "").strip(),
                    "label": str(r.get("label") or r.get("name") or wid or "").strip(),
                }
            )
        return out


def list_warehouse_bins(warehouse_id: str) -> list[dict[str, Any]]:
    from db import list_warehouse_picker_bins

    wh = (warehouse_id or "").strip()
    if not wh:
        return []
    with _erp_session_scope():
        if not _sales_features()["bin_tracking_enabled"]:
            return []
        rows = list_warehouse_picker_bins(wh) or []
        out: list[dict[str, Any]] = []
        for row in rows:
            if not row:
                continue
            sid = row.get("storage_id")
            code = str(row.get("code") or "").strip()
            if sid is None or not code:
                continue
            out.append(
                {
                    "storage_id": int(sid),
                    "code": code,
                    "name": str(row.get("name") or "").strip(),
                    "warehouse_id": str(row.get("warehouse_id") or row.get("loc_key") or wh).strip(),
                }
            )
        return out


def list_item_bins_for_warehouse(item_code: str, warehouse_id: str) -> dict[str, Any]:
    from db import get_bin_stock_list, get_item_by_code, list_warehouse_picker_bins

    ic = (item_code or "").strip()
    wh = (warehouse_id or "").strip()
    if not ic.isdigit() or not wh:
        raise ValueError("Item code and warehouse are required.")
    with _erp_session_scope():
        if not _sales_features()["bin_tracking_enabled"]:
            return {"bins": [], "default_bin_storage_id": None}
        loc = _location_code()
        item_code_int = int(ic)
        warehouse_id_int = int(float(wh))
        rows = get_bin_stock_list(str(warehouse_id_int), loc, item_code=item_code_int, include_zero=False) or []
        bins: list[dict[str, Any]] = []
        seen: set[int] = set()
        for r in rows:
            try:
                sid = int(float(r.get("storage_id") or 0))
            except (TypeError, ValueError):
                continue
            if sid <= 0 or sid in seen:
                continue
            seen.add(sid)
            bins.append(
                {
                    "storage_id": sid,
                    "code": str(r.get("bin_code") or "").strip(),
                    "name": str(r.get("bin_name") or "").strip(),
                    "stock": float(r.get("qty") or 0),
                }
            )
        item_row = get_item_by_code(item_code_int, loc) or {}
        default_bin_raw = item_row.get("default_bin_storage_id")
        try:
            default_bin_id = int(float(default_bin_raw)) if default_bin_raw not in (None, "") else 0
        except (TypeError, ValueError):
            default_bin_id = 0
        if default_bin_id > 0 and default_bin_id not in seen:
            for pick in list_warehouse_picker_bins(warehouse_id_int) or []:
                try:
                    psid = int(float(pick.get("storage_id") or 0))
                except (TypeError, ValueError):
                    continue
                if psid != default_bin_id:
                    continue
                bins.append(
                    {
                        "storage_id": psid,
                        "code": str(pick.get("code") or "").strip(),
                        "name": str(pick.get("name") or "").strip(),
                        "stock": 0.0,
                    }
                )
                break
        return {"bins": bins, "default_bin_storage_id": default_bin_id or None}


def list_batch_lots(item_code: str) -> list[dict[str, Any]]:
    from db import get_item_lot_stock_list

    ic = (item_code or "").strip()
    if not ic.isdigit():
        raise ValueError("Invalid item code.")
    with _erp_session_scope():
        if not _sales_features()["batch_tracking_enabled"]:
            return []
        loc = _location_code()
        rows = get_item_lot_stock_list(loc, itemcode=int(ic)) or []
        out: list[dict[str, Any]] = []
        for r in rows:
            blocked = str(r.get("lot_blocked") or "N").strip().upper() == "Y"
            if blocked:
                continue
            try:
                qv = float(r.get("qty") or 0)
            except (TypeError, ValueError):
                qv = 0.0
            if qv <= 0.0001:
                continue
            out.append(
                {
                    "lot_id": r.get("lot_id"),
                    "batch_no": str(r.get("batch_no") or "").strip(),
                    "expiry_date": str(r.get("expiry_date") or "").strip(),
                    "qty": qv,
                }
            )
        return out


def check_credit_limit(customer_code: str, net_amount: float, billing_type: str) -> dict[str, Any]:
    bt = (billing_type or "CASH").strip().upper()
    from db import _customer_gl_receivable_context, validate_pos_credit_customer_accounts

    with _erp_session_scope():
        loc = _location_code()
        raw = _find_customer_master_row(customer_code)
        if not raw:
            return {
                "ok": False,
                "error": "Customer not found.",
                "billing_type": bt,
                "outstanding_source": "GL",
            }
        snap = _normalize_customer_row(raw, gl_ctx=_customer_gl_receivable_context())
        outstanding = float(snap.get("current_credit") or 0)
        limit = float(snap.get("credit_limit") or 0)
        base = {
            "billing_type": bt,
            "gl_outstanding": outstanding,
            "credit_limit": limit,
            "outstanding_source": snap.get("outstanding_source", "GL"),
        }
        if bt != "CREDIT":
            return {"ok": True, **base}
        ok, err = validate_pos_credit_customer_accounts(
            loc,
            customer_code,
            proposed_credit_delta=None,
        )
        if not ok:
            return {"ok": False, "error": err, **base}
        net = float(net_amount or 0)
        projected = outstanding + net
        if limit > 0 and projected > limit + 1e-6:
            return {
                "ok": False,
                **base,
                "projected_outstanding": projected,
                "error": (
                    f"Credit limit exceeded. GL outstanding {outstanding:.2f}, "
                    f"limit {limit:.2f}, this bill {net:.2f}."
                ),
            }
        return {"ok": True, **base, "projected_outstanding": projected}


def _normalize_payment_tender_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "tender_code": str(row.get("tender_code") or "").strip().upper(),
        "tender_name": str(row.get("tender_name") or row.get("tender_code") or "").strip(),
        "category": str(row.get("category") or "").strip().upper(),
        "sort_order": int(row.get("sort_order") or 0),
        "icon_key": str(row.get("icon_key") or "").strip(),
    }


def _default_payment_tender_rows() -> list[dict[str, Any]]:
    """Same fallback as POS checkout (``DEFAULT_CHECKOUT_TENDERS`` / seed rows), excluding CREDIT."""
    from db import POS_TENDER_TYPE_SEED_ROWS

    out: list[dict[str, Any]] = []
    for row in POS_TENDER_TYPE_SEED_ROWS:
        code = str(row.get("tender_code") or "").strip().upper()
        cat = str(row.get("category") or "").strip().upper()
        if not code or code == "CREDIT" or cat == "CREDIT":
            continue
        out.append(_normalize_payment_tender_row(row))
    out.sort(key=lambda x: (int(x.get("sort_order") or 0), str(x.get("tender_code") or "")))
    return out


def _list_pos_payment_tenders_raw(tenant_id: str) -> list[dict[str, Any]]:
    """Read ``POS_TENDER_TYPE`` via explicit tenant pool (matches list_invoices pattern)."""
    from db import POS_TENDER_TYPE_TABLE, _TABLE_EXISTS_CACHE, ensure_pos_tender_type_table, set_active_db_key
    from mobile_backend.database.oracle_pool import get_connection

    tid = str(tenant_id or "").strip()
    if not tid:
        return []

    set_active_db_key(tid)
    try:
        _TABLE_EXISTS_CACHE.pop(POS_TENDER_TYPE_TABLE, None)
    except Exception:
        pass

    if not ensure_pos_tender_type_table():
        return []

    conn = get_connection(tenant_id=tid)
    tbl = POS_TENDER_TYPE_TABLE
    q = (
        f"SELECT TENDER_CODE, TENDER_NAME, CATEGORY, GL_ACCOUNT_CODE, STATUS, "
        f"SORT_ORDER, ICON_KEY FROM {tbl} "
        f"WHERE UPPER(NVL(TRIM(STATUS), 'ACTIVE')) = 'ACTIVE' "
        f"ORDER BY SORT_ORDER, TENDER_CODE"
    )
    try:
        with conn.cursor() as cur:
            cur.execute(q)
            if not cur.description:
                return []
            cols = [str(c[0]).lower() for c in cur.description]
            raw_rows = cur.fetchall()
    except Exception:
        return []

    out: list[dict[str, Any]] = []
    for raw in raw_rows:
        rk = {cols[i]: raw[i] for i in range(len(cols))}
        code = str(rk.get("tender_code") or "").strip().upper()
        cat = str(rk.get("category") or "").strip().upper()
        if not code or code == "CREDIT" or cat == "CREDIT":
            continue
        out.append(
            {
                "tender_code": code,
                "tender_name": str(rk.get("tender_name") or code).strip(),
                "category": cat,
                "gl_account_code": str(rk.get("gl_account_code") or "").strip(),
                "status": str(rk.get("status") or "ACTIVE").strip().upper(),
                "sort_order": int(rk.get("sort_order") or 0),
                "icon_key": str(rk.get("icon_key") or "").strip(),
            }
        )
    return out


def list_payment_tenders() -> list[dict[str, Any]]:
    """Active POS payment tenders (excludes on-account CREDIT). Falls back to POS seed defaults."""
    from db import POS_TENDER_TYPE_TABLE, list_pos_payment_tender_types
    from mobile_backend.request_context import get_jwt

    claims = get_jwt()
    tenant_id = str(claims.get("tenant_id") or "").strip() or None

    rows: list[dict[str, Any]] = []
    with _erp_session_scope():
        try:
            from db import _TABLE_EXISTS_CACHE

            _TABLE_EXISTS_CACHE.pop(POS_TENDER_TYPE_TABLE, None)
        except Exception:
            pass
        rows = list_pos_payment_tender_types() or []

    if not rows and tenant_id:
        rows = _list_pos_payment_tenders_raw(tenant_id)

    if not rows:
        rows = [
            {
                "tender_code": r["tender_code"],
                "tender_name": r["tender_name"],
                "category": r["category"],
                "sort_order": r["sort_order"],
                "icon_key": r["icon_key"],
            }
            for r in _default_payment_tender_rows()
        ]

    return [_normalize_payment_tender_row(r) for r in rows if isinstance(r, dict)]


def _tender_meta_map(tenders: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(t.get("tender_code") or "").strip().upper(): t
        for t in tenders
        if str(t.get("tender_code") or "").strip()
    }


def _is_cash_category_tender(code: str, meta: dict[str, dict[str, Any]]) -> bool:
    cd = str(code or "").strip().upper()
    if cd == "CASH":
        return True
    cat = str((meta.get(cd) or {}).get("category") or "").strip().upper()
    return cat == "CASH"


def _aggregate_legacy_payment_buckets(
    amounts: dict[str, float],
    meta: dict[str, dict[str, Any]],
) -> dict[str, float]:
    cash = card = wallet = loyalty = points = 0.0
    for code, amt in amounts.items():
        if amt < 0.005:
            continue
        cd = str(code).strip().upper()
        cat = str((meta.get(cd) or {}).get("category") or "").strip().upper()
        if cd == "LOYALTY":
            loyalty += amt
        elif cd == "POINTS":
            points += amt
        elif cat == "CASH" or cd == "CASH":
            cash += amt
        elif cat == "CARD":
            card += amt
        elif cat in ("WALLET", "VOUCHER"):
            wallet += amt
        else:
            wallet += amt
    return {
        "cash": round(cash, 2),
        "card": round(card, 2),
        "wallet": round(wallet, 2),
        "loyalty": round(loyalty, 2),
        "points": round(points, 2),
    }


def _net_amounts_after_change(
    amounts: dict[str, float],
    change_due: float,
    meta: dict[str, dict[str, Any]],
) -> dict[str, float]:
    out = {str(k).upper(): round(float(v), 2) for k, v in amounts.items() if float(v) >= 0.005}
    remaining = max(0.0, round(float(change_due or 0), 2))
    if remaining < 0.005:
        return out
    cash_codes = sorted(
        [c for c in out if _is_cash_category_tender(c, meta)],
        key=lambda c: (0 if c == "CASH" else 1, c),
    )
    for code in cash_codes:
        if remaining < 0.005:
            break
        amt = out.get(code) or 0.0
        if amt < 0.005:
            continue
        deduct = min(amt, remaining)
        net = round(amt - deduct, 2)
        if net >= 0.005:
            out[code] = net
        else:
            out.pop(code, None)
        remaining = round(remaining - deduct, 2)
    return out


def _normalize_mobile_payment_header(header: dict[str, Any], net_amount: float) -> dict[str, Any]:
    """Map POS-style payment_modes to BILLHDR legacy columns and POS_BILL_PAYMODE rows."""
    from db import list_pos_payment_tender_types

    billing = str(
        header.get("customer_billing_type") or header.get("billing_type") or "CASH"
    ).strip().upper()
    if billing == "CREDIT":
        header.pop("record_payment_modes", None)
        header.pop("payment_modes", None)
        return header

    net = round(float(net_amount or 0), 2)
    tenders = list_payment_tenders()
    meta = {str(t.get("tender_code") or "").upper(): t for t in tenders if t.get("tender_code")}

    amounts: dict[str, float] = {}
    raw_modes = header.get("payment_modes")
    if isinstance(raw_modes, list):
        for row in raw_modes:
            if not isinstance(row, dict):
                continue
            code = str(row.get("code") or row.get("paymode") or "").strip().upper()
            try:
                amt = float(row.get("amount") or 0)
            except (TypeError, ValueError):
                amt = 0.0
            if code and amt >= 0.005:
                amounts[code] = round(amt, 2)

    if not amounts and net > 0.005:
        amounts["CASH"] = net

    total_paid = round(sum(amounts.values()), 2)
    if net > 0.005 and total_paid + 1e-6 < net:
        raise ValueError(
            f"Payment total {total_paid:.2f} is less than invoice net {net:.2f}."
        )

    change = max(0.0, round(total_paid - net, 2))
    save_amounts = _net_amounts_after_change(amounts, change, meta)

    payment_modes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for t in tenders:
        code = str(t.get("tender_code") or "").strip().upper()
        amt = save_amounts.get(code, 0.0)
        if amt >= 0.005:
            payment_modes.append(
                {"code": code[:30], "amount": amt, "reference": ""}
            )
            seen.add(code)
    for code, amt in save_amounts.items():
        if amt >= 0.005 and code not in seen:
            payment_modes.append(
                {"code": code[:30], "amount": amt, "reference": ""}
            )

    leg = _aggregate_legacy_payment_buckets(save_amounts, meta)
    h = dict(header)
    h["cashamount"] = leg["cash"]
    h["cardamount"] = leg["card"]
    h["walletamount"] = leg["wallet"]
    h["loyaltyamount"] = leg["loyalty"]
    h["pointsamount"] = leg["points"]
    h["payment_modes"] = payment_modes
    h["record_payment_modes"] = True
    if change >= 0.01:
        rem = str(h.get("remarks") or "").strip()
        h["remarks"] = (f"{rem}; " if rem else "") + f"Change: {change:.2f}"
    return h


def save_invoice(payload: dict[str, Any], *, username: str) -> dict[str, Any]:
    from db import _validate_sales_doc_save_lines, ensure_gl_tables

    header = dict(payload.get("header") or {})
    lines = list(payload.get("lines") or [])
    if not lines:
        raise ValueError("Add at least one line item.")
    order_no = str(header.get("orderno") or header.get("order_no") or "").strip()
    walk_in_early = bool(header.get("walk_in") or header.get("is_walk_in"))
    if (
        _sales_features()["orderno_mandatory"]
        and not order_no
        and not walk_in_early
    ):
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
            raise ValueError("Credit sale requires a customer.")
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
        raise ValueError("Select a customer or choose walk-in cash sale.")
    else:
        header["customercode"] = cc

    # Amount / shape only — UOM factor resolved again inside ERP session below.
    lines = _normalize_invoice_save_lines(lines)
    line_err = _validate_sales_doc_save_lines(lines, doc_label="sales invoice")
    if line_err:
        raise ValueError(line_err)

    billing = str(
        header.get("customer_billing_type") or header.get("billing_type") or "CASH"
    ).strip().upper()

    net = 0.0
    for ln in lines:
        qty = float(ln.get("quantity") or 0)
        rate = float(ln.get("rate") or 0)
        disc = float(ln.get("discount") or 0)
        net += qty * rate - disc

    doc = str(header.get("billno") or header.get("orderno") or "").strip()
    from mobile_backend.services.transaction_date_helper import resolve_doc_date

    with mobile_operation_lock(
        "sales_invoice",
        doc,
        lock_seconds=180.0,
        busy_message="Sales invoice is already being saved. Please wait.",
    ), _erp_session_scope() as user:
        # Re-apply factor with tenant location session (stock uses base_qty).
        lines = _normalize_invoice_save_lines(lines)
        loc = _location_code()
        if not ensure_gl_tables():
            raise ValueError(
                "General ledger is not configured. Sales invoice cannot post to accounts."
            )
        bill_date = resolve_doc_date(
            "sales",
            header.get("billdate") or header.get("bill_date"),
            location_code=loc,
            snap_out_of_range=True,
        )
        header["billdate"] = bill_date
        header["bill_date"] = bill_date
        header = _normalize_invoice_save_header(
            header,
            location_code=loc,
            username=user or username,
        )
        header["billdate"] = bill_date
        header["bill_date"] = bill_date
        _validate_customer_gl_before_save(
            loc,
            header.get("customercode"),
            net_amount=net,
            billing_type=billing,
        )
        header = _normalize_mobile_payment_header(header, net)
        return _save_with_billno_retry(header, lines, location_code=loc, username=user or username)


def build_invoice_pdf(billno: Any) -> tuple[bytes, str]:
    """ERP cashbilldup invoice PDF (same layout as desktop Sales Invoice print)."""
    from addons.reports.controllers.routes import _generate_cashbilldup_pdf
    from addons.reports.invoice_templates import get_saved_invoice_template
    from db import billno_is_valid, get_sales_print_data, parse_billno_from_request

    bn = parse_billno_from_request(billno)
    if not billno_is_valid(bn):
        raise ValueError("Invalid bill number.")

    with _erp_session_scope():
        loc = _location_code()
        header, lines = get_sales_print_data(bn, loc)
        if not header:
            raise ValueError("Invoice not found for PDF.")
        if not header.get("locationcode"):
            header["locationcode"] = loc
        pdf_bytes = _generate_cashbilldup_pdf(
            billno=bn,
            header=header,
            lines=lines or [],
            invoice_title="INVOICE",
            template=get_saved_invoice_template(),
        )
        if not pdf_bytes:
            raise ValueError("Failed to generate invoice PDF. Check reportlab on the server.")
        safe = str(bn).replace("/", "-").replace("\\", "-")
        filename = f"invoice_{safe}.pdf"
        return pdf_bytes, filename
