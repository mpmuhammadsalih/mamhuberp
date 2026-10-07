"""Store transfer (STKTRFHDR/DTL) — delegates to ERP purchase module logic."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator, List, Optional

from mobile_backend.operation_lock import mobile_operation_lock
from mobile_backend.request_context import get_jwt


def _claims() -> tuple[str, str | None]:
    claims = get_jwt()
    username = str(claims.get("sub") or "").strip() or "mobile"
    tenant_id = claims.get("tenant_id")
    tid = str(tenant_id).strip() if tenant_id not in (None, "") else None
    return username, tid


def _resolve_item_code_for_barcode(st: Any, barcode: str) -> int | None:
    """Resolve item code from manufacturer or alternate UOM barcode."""
    from db import get_item_by_alternate_barcode, get_item_by_manufacturer_id

    bc = (barcode or "").strip()
    if not bc:
        return None
    try:
        loc = int(st._resolve_location_code())
    except Exception:
        return None
    item = get_item_by_manufacturer_id(bc, loc)
    if not item:
        item = get_item_by_alternate_barcode(bc, loc)
    if not item:
        return None
    try:
        ic = int(float(item.get("ITEMCODE") or item.get("itemcode") or 0))
    except Exception:
        ic = 0
    return ic if ic > 0 else None


@contextmanager
def _erp_session_scope() -> Iterator[str]:
    """Run ERP store-transfer helpers with session user/tenant/location from JWT."""
    from db import get_location_info_by_dbkey, set_active_db_key
    from mobile_backend.request_context import get_current_request
    from nexa_http import context as nexa_ctx

    username, tenant_id = _claims()
    req = get_current_request()
    backup: dict[str, Any] = {}
    if req is not None:
        backup = dict(getattr(req, "session", {}) or {})
        sess = req.session
        sess.clear()
        sess["user"] = username
        if tenant_id:
            sess["tenant_id"] = tenant_id
            set_active_db_key(tenant_id)
        try:
            info = get_location_info_by_dbkey(None) or {}
            loc = info.get("locationcode")
            if loc is not None:
                sess["location_code"] = int(loc)
            name = info.get("locationname")
            if name:
                sess["location_name"] = str(name)
        except Exception:
            sess["location_code"] = 1
        # Keep g in sync — _resolve_db_connect_config prefers g.current_tenant_id.
        g = getattr(req.state, "nexa_g", None)
        if g is not None:
            g.current_tenant_id = tenant_id
            g.current_location_code = sess.get("location_code")
        # ERP helpers (reports, etc.) read nexa_http.session — keep both request contexts aligned.
        nexa_token = None
        if nexa_ctx.get_current_request() is None:
            nexa_token = nexa_ctx.bind_request(req)
        try:
            yield username
        finally:
            if nexa_token is not None:
                nexa_ctx.reset_request(nexa_token)
            sess.clear()
            sess.update(backup)
        return

    # Fallback when no Starlette request is bound (tests/scripts).
    from nexa_http.session_wrap import session

    backup = dict(session)
    try:
        session.clear()
        session["user"] = username
        if tenant_id:
            session["tenant_id"] = tenant_id
            set_active_db_key(tenant_id)
        try:
            info = get_location_info_by_dbkey(None) or {}
            loc = info.get("locationcode")
            if loc is not None:
                session["location_code"] = int(loc)
            name = info.get("locationname")
            if name:
                session["location_name"] = str(name)
        except Exception:
            session["location_code"] = 1
        yield username
    finally:
        session.clear()
        session.update(backup)


def _purchase_st():
    from addons.purchase.controllers import routes as st

    return st


def _status_label(code: str) -> str:
    c = (code or "").strip().upper()
    if c == "C":
        return "Created"
    if c in ("T", "P"):
        return "In transit"
    if c == "A":
        return "Approved"
    return c or "—"


def list_stores() -> list[dict[str, str]]:
    with _erp_session_scope():
        st = _purchase_st()
        from db import get_user_transit_only

        stores = st._get_transfer_store_options()
        user = str(get_jwt().get("sub") or "")
        if get_user_transit_only(user) == "Y":
            transit = {
                str(r.get("code") or "").strip().upper()
                for r in st._get_transfer_approval_store_options()
                if str(r.get("code") or "").strip()
            }
            stores = [s for s in stores if str(s.get("code") or "").strip().upper() in transit]
        return [{"code": str(s.get("code") or "").strip(), "description": str(s.get("description") or "").strip()} for s in stores]


def list_transfers(
    *,
    bucket: str = "all",
    from_store: str = "",
    to_store: str = "",
    limit: int = 50,
) -> list[dict[str, Any]]:
    bucket = (bucket or "all").strip().lower()
    lim = max(1, min(int(limit), 100))
    fs = (from_store or "").strip().upper() or None
    ts = (to_store or "").strip().upper() or None

    with _erp_session_scope() as user:
        st = _purchase_st()
        st._apply_db()
        wf = st._resolve_store_transfer_workflow_filter(None, user)
        cap = lim
        if bucket == "created":
            rows = st._get_store_transfer_rows(
                "C", allowed_stores=None, from_store=fs, to_store=ts, row_limit=cap
            )
        elif bucket in ("transit", "pending_approve"):
            rows = st._get_store_transfer_rows(
                "T,P", allowed_stores=None, from_store=fs, to_store=ts, row_limit=cap
            )
        elif bucket in ("completed", "approved"):
            today = datetime.now().strftime("%Y-%m-%d")
            rows = st._get_store_transfer_rows(
                "A",
                allowed_stores=None,
                date_from=today,
                date_to=today,
                from_store=fs,
                to_store=ts,
                row_limit=cap,
            )
        else:
            pending = st._get_store_transfer_rows(
                "C,T,P", allowed_stores=None, from_store=fs, to_store=ts, row_limit=cap
            )
            today = datetime.now().strftime("%Y-%m-%d")
            done = st._get_store_transfer_rows(
                "A",
                allowed_stores=None,
                date_from=today,
                date_to=today,
                from_store=fs,
                to_store=ts,
                row_limit=cap,
            )
            rows = st._merge_store_transfer_rows_flat([pending, done], cap)
        rows = st._filter_store_transfer_rows_by_workflow(rows, wf, user)
        out: list[dict[str, Any]] = []
        for r in rows or []:
            d = st._store_transfer_row_api_dict(r)
            d["status_label"] = _status_label(d.get("status") or "")
            # Always expose transferno as string for mobile (ST-000001 / legacy numeric).
            d["transferno"] = str(d.get("transferno") or "").strip()
            d.pop("url_view", None)
            d.pop("url_pdf", None)
            out.append(d)
        return out


def get_transfer(transfer_no: Any) -> dict[str, Any] | None:
    from db.inventory_doc_numbers import parse_transferno_from_request, transferno_is_valid

    with _erp_session_scope():
        st = _purchase_st()
        st._apply_db()
        key = parse_transferno_from_request(transfer_no)
        if not transferno_is_valid(key):
            return None
        payload = st._get_store_transfer_payload(key)
    if not payload:
        return None
    header = dict(payload.get("header") or {})
    # Keep transferno as stored (ST-000001 / numeric) for mobile clients.
    if "transferno" in header:
        header["transferno"] = str(header.get("transferno") or "").strip() or header.get("transferno")
    header["status_label"] = _status_label(str(header.get("status") or ""))
    lines = []
    for ln in payload.get("lines") or []:
        row = dict(ln)
        lines.append(row)
    return {"header": header, "lines": lines}


def search_items(
    *,
    from_store: str,
    search: str = "",
    limit: int = 40,
    exact_barcode: str | None = None,
    exact_item_code: int | None = None,
) -> list[dict[str, Any]]:
    store = (from_store or "").strip().upper()
    if not store:
        return []
    bc = (exact_barcode or "").strip()
    try:
        ic = int(exact_item_code) if exact_item_code is not None else 0
    except (TypeError, ValueError):
        ic = 0
    with _erp_session_scope():
        st = _purchase_st()
        st._apply_db()
        lim = min(max(limit, 1), 100)
        if ic > 0:
            rows = st._get_transfer_items_for_store(
                from_store=store,
                search=None,
                limit=min(lim, 50),
                exact_item_code=ic,
            )
        elif bc:
            rows = st._get_transfer_items_for_store(
                from_store=store,
                search=None,
                limit=min(lim, 50),
                exact_barcode=bc,
            )
            if not rows:
                alt_ic = _resolve_item_code_for_barcode(st, bc)
                if alt_ic:
                    rows = st._get_transfer_items_for_store(
                        from_store=store,
                        search=None,
                        limit=min(lim, 50),
                        exact_item_code=alt_ic,
                    )
        else:
            rows = st._get_transfer_items_for_store(
                from_store=store,
                search=(search or "").strip() or None,
                limit=lim,
            )
    out: list[dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        try:
            item_code = int(float(row.get("itemcode") or 0))
        except Exception:
            item_code = 0
        if item_code <= 0:
            continue
        try:
            avail = float(row.get("availableqty") or 0)
        except Exception:
            avail = 0.0
        try:
            actual = float(row.get("actualqty") or avail)
        except Exception:
            actual = avail
        try:
            pending = float(row.get("pendingqty") or 0)
        except Exception:
            pending = 0.0
        out.append(
            {
                "itemcode": item_code,
                "itemname": str(row.get("itemname") or "").strip(),
                "uom": str(row.get("uom") or "NOS").strip() or "NOS",
                "availableqty": avail,
                "actualqty": actual,
                "pendingqty": pending,
                "barcode": str(row.get("barcode") or "").strip(),
            }
        )
    return out


def item_stock(*, item_code: int, store: str) -> dict[str, Any]:
    with _erp_session_scope():
        st = _purchase_st()
        st._apply_db()
        from db import get_item_store_inventory

        loc = st._resolve_location_code()
        rows = get_item_store_inventory(loc, int(item_code))
        store_u = (store or "").strip().upper()
        current_qty = 0.0
        if store_u:
            for r in rows or []:
                rs = str(r.get("store") or r.get("itemlocation") or "").strip().upper()
                if rs == store_u:
                    current_qty = float(r.get("stock") or 0)
                    break
        pending_qty = 0.0
        try:
            pending_qty = float(
                st._get_pending_approve_transfer_qty_map(store_u, [int(item_code)]).get(
                    int(item_code), 0.0
                )
            )
        except Exception:
            pending_qty = 0.0
        adjusted = max(0.0, current_qty - pending_qty)
        dec = getattr(st, "_STORE_TRANSFER_STOCK_DECIMALS", 3)
        return {
            "current_qty": round(adjusted, dec),
            "actual_qty": round(current_qty, dec),
            "pending_qty": round(pending_qty, dec),
            "store": store_u,
        }


def next_transfer_no() -> Any:
    from db.inventory_doc_numbers import coerce_transferno

    with _erp_session_scope():
        st = _purchase_st()
        st._apply_db()
        return coerce_transferno(st._store_transfer_next_no())


def get_open_context() -> dict[str, Any]:
    """Next transfer no + preferred date from Transaction Date Setup (Transfer)."""
    from db.inventory_doc_numbers import coerce_transferno
    from mobile_backend.services.transaction_date_helper import (
        missing_setup_date_message,
        open_context as txn_open_context,
    )

    with _erp_session_scope() as username:
        st = _purchase_st()
        st._apply_db()
        txn = txn_open_context("transfer")
        preferred = str(txn.get("preferred_date") or "")[:10]
        if not preferred:
            raise ValueError(
                txn.get("transaction_date_error")
                or missing_setup_date_message("transfer")
            )
        # Allocate a candidate, then skip any number already on STKTRFHDR (stuck / race).
        transfer_no = coerce_transferno(st._store_transfer_next_no())
        transfer_no = _allocate_transfer_no(st, transfer_no, update_existing=False)
        return {
            "transfer_no": str(transfer_no),
            "transfer_date": preferred,
            "open_date_from": str(txn.get("open_date_from") or preferred)[:10],
            "open_date_to": str(txn.get("open_date_to") or preferred)[:10],
            "transaction_date_blocked": bool(txn.get("transaction_date_blocked")),
            "created_by": username,
        }


def _allocate_transfer_no(st: Any, transfer_no: Any, *, update_existing: bool) -> Any:
    """Use requested number for edits; for new saves, skip numbers already in STKTRFHDR."""
    from db.inventory_doc_numbers import coerce_transferno, transferno_is_valid

    tn = coerce_transferno(transfer_no)

    if update_existing and transferno_is_valid(tn):
        return tn

    if not transferno_is_valid(tn):
        tn = coerce_transferno(st._store_transfer_next_no())

    # Match ERP web: re-peek next series value instead of tn += 1 (breaks ST- prefixes).
    attempts = 0
    while transferno_is_valid(tn) and st._store_transfer_header_exists(tn) and attempts < 500:
        tn = coerce_transferno(st._store_transfer_next_no())
        attempts += 1

    if attempts >= 500 and st._store_transfer_header_exists(tn):
        raise ValueError("Could not allocate a free transfer number. Try again.")

    return tn


def save_transfer(payload: dict[str, Any]) -> dict[str, Any]:
    from db.inventory_doc_numbers import coerce_transferno, transferno_is_valid

    data = payload or {}
    transfer_no = coerce_transferno(data.get("transfer_no"))
    transfer_date = str(data.get("transfer_date") or "").strip()
    from_store = str(data.get("from_store") or "").strip()
    to_store = str(data.get("to_store") or "").strip()
    remarks = str(data.get("remarks") or "").strip()
    lines = data.get("lines") or []
    update_existing = bool(data.get("update_existing"))

    if not lines:
        raise ValueError("Add at least one line")
    if not from_store or not to_store:
        raise ValueError("From Store and To Store are required")

    with mobile_operation_lock(
        "stock_transfer",
        str(transfer_no or ""),
        lock_seconds=120.0,
        busy_message="Stock transfer is already being saved. Please wait.",
    ), _erp_session_scope():
        from mobile_backend.services.transaction_date_helper import resolve_doc_date

        transfer_date = resolve_doc_date(
            "transfer",
            transfer_date,
            snap_out_of_range=True,
        )
        st = _purchase_st()
        st._apply_db()
        from mobile_backend.services.uom_factor import apply_line_stock_base

        norm_lines: list[dict[str, Any]] = []
        for raw in lines:
            ln = dict(raw or {})
            item = ln.get("item_code") or ln.get("itemcode")
            uom = str(ln.get("uom") or "NOS").strip() or "NOS"
            try:
                tq = float(ln.get("transfer_qty") or ln.get("quantity") or ln.get("qty") or 0)
            except (TypeError, ValueError):
                tq = 0.0
            if not str(item or "").strip() or abs(tq) < 1e-12:
                continue
            ln["transfer_qty"] = tq
            ln["uom"] = uom
            apply_line_stock_base(
                ln, item_code=item, uom=uom, qty=tq, st=st
            )
            norm_lines.append(ln)
        if not norm_lines:
            raise ValueError("Add at least one line")
        lines = norm_lines
        requested_no = transfer_no
        transfer_no = _allocate_transfer_no(
            st,
            transfer_no,
            update_existing=update_existing,
        )
        err = st._save_store_transfer_request(
            transfer_no, transfer_date, from_store, to_store, remarks, lines
        )
        if err:
            raise ValueError(err)
    out: dict[str, Any] = {"transfer_no": str(transfer_no)}
    if (
        not update_existing
        and transferno_is_valid(requested_no)
        and str(transfer_no) != str(requested_no)
    ):
        out["transfer_no_reassigned"] = True
        out["requested_transfer_no"] = str(requested_no)
    return out


def post_transfer(transfer_no: Any) -> dict[str, Any]:
    from db.inventory_doc_numbers import parse_transferno_from_request, transferno_is_valid

    key = parse_transferno_from_request(transfer_no)
    if not transferno_is_valid(key):
        raise ValueError("Invalid transfer number.")
    with mobile_operation_lock(
        "stock_transfer_post",
        str(key),
        lock_seconds=120.0,
        busy_message="Stock transfer is already being posted. Please wait.",
    ), _erp_session_scope():
        st = _purchase_st()
        st._apply_db()
        err = st._post_store_transfer_to_transit(key)
        if err:
            raise ValueError(err)
    return {"transfer_no": str(key)}


def approve_transfer(transfer_no: Any) -> dict[str, Any]:
    from db.inventory_doc_numbers import parse_transferno_from_request, transferno_is_valid

    key = parse_transferno_from_request(transfer_no)
    if not transferno_is_valid(key):
        raise ValueError("Invalid transfer number.")
    with mobile_operation_lock(
        "stock_transfer_approve",
        str(key),
        lock_seconds=120.0,
        busy_message="Stock transfer is already being approved. Please wait.",
    ), _erp_session_scope():
        st = _purchase_st()
        st._apply_db()
        err = st._approve_store_transfer(key)
        if err:
            raise ValueError(err)
    return {"transfer_no": str(key)}


def build_transfer_pdf(transfer_no: Any, *, duplicate: bool = False) -> tuple[bytes, str]:
    """ERP store-transfer PDF (same layout as desktop transfer print)."""
    from db.inventory_doc_numbers import parse_transferno_from_request, transferno_is_valid

    with _erp_session_scope():
        st = _purchase_st()
        st._apply_db()
        key = parse_transferno_from_request(transfer_no)
        if not transferno_is_valid(key):
            raise ValueError("Invalid transfer number.")
        copy_label = "DUPLICATE" if duplicate else "ORIGINAL"
        pdf_bytes, err = st._build_store_transfer_pdf_bytes(key, copy_label=copy_label)
        if err or not pdf_bytes:
            raise ValueError(str(err or "Failed to generate stock transfer PDF."))
        safe_name = str(key).replace("/", "_").replace("\\", "_")
        return pdf_bytes, f"store_transfer_{safe_name}.pdf"
