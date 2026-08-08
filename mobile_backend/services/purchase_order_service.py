"""Mobile Purchase Order (LPO) — wraps ERP purchase helpers under JWT session scope."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from mobile_backend.operation_lock import mobile_operation_lock
from mobile_backend.services.stock_transfer_service import _erp_session_scope


def _purchase():
    from addons.purchase.controllers import routes as purchase

    return purchase


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def get_open_context() -> dict[str, Any]:
    with _erp_session_scope() as username:
        p = _purchase()
        p._apply_db()
        lpono = p._lpo_next_no()
        # Must use Transaction Date Setup open date (not calendar today).
        txn = p._purchase_txn_date_context("purchase")
        open_date = str(
            txn.get("open_transaction_date")
            or p._purchase_open_transaction_date("purchase")
            or datetime.now().strftime("%Y-%m-%d")
        ).strip()[:10]
        wh_enabled = bool(p._po_warehouse_enabled())
        wh_rows = p._get_lpo_warehouse_picker_rows(doc_kind="purchase") if wh_enabled else []
        default_wh = wh_rows[0] if wh_rows else {}
        return {
            "lpono": str(lpono or "").strip(),
            "lpo_date": open_date,
            "open_date_from": str(txn.get("open_transaction_date_from") or open_date)[:10],
            "open_date_to": str(txn.get("open_transaction_date_to") or open_date)[:10],
            "transaction_date_blocked": bool(txn.get("transaction_date_blocked")),
            "created_by": username,
            "features": {"warehouse_enabled": wh_enabled},
            "default_warehouse_id": default_wh.get("code") or default_wh.get("warehouse_id"),
            "default_warehouse_code": str(
                default_wh.get("store") or default_wh.get("warehouse_code") or ""
            ).strip(),
            "default_warehouse_name": str(
                default_wh.get("name") or default_wh.get("warehouse_name") or ""
            ).strip(),
            "default_warehouse_label": str(
                default_wh.get("label") or default_wh.get("name") or ""
            ).strip(),
        }


def list_orders(
    *,
    tab: str = "draft",
    search: str = "",
    page: int = 1,
    page_size: int = 50,
    date_from: str = "",
    date_to: str = "",
) -> dict[str, Any]:
    tab_key = (tab or "draft").strip().lower()
    if tab_key not in ("draft", "approved", "canceled", "cancelled"):
        tab_key = "draft"
    if tab_key == "cancelled":
        tab_key = "canceled"

    with _erp_session_scope():
        p = _purchase()
        p._apply_db()
        rows, total = p._get_lpo_list_page(
            page=max(1, int(page or 1)),
            per_page=max(20, min(int(page_size or 50), 100)),
            tab=tab_key,
            search=(search or "").strip() or None,
            date_from=(date_from or "").strip()[:10] or None,
            date_to=(date_to or "").strip()[:10] or None,
        )
        out: list[dict[str, Any]] = []
        for raw in rows or []:
            r = dict(raw or {})
            d = r.get("lpodate")
            if hasattr(d, "strftime"):
                date_s = d.strftime("%Y-%m-%d")
            else:
                date_s = str(d or "")[:10]
            out.append(
                {
                    "lpono": str(r.get("lpono") or "").strip(),
                    "lpo_date": date_s,
                    "supplier_code": str(r.get("suppliercode") or "").strip(),
                    "supplier_name": str(r.get("suppliername") or "").strip(),
                    "amount": _to_float(r.get("amount") or r.get("lpoamount")),
                    "approval_status": str(r.get("approval_status") or "DRAFT").strip().upper(),
                }
            )
        return {
            "orders": out,
            "total_count": int(total or 0),
            "page": max(1, int(page or 1)),
            "page_size": max(20, min(int(page_size or 50), 100)),
        }


def get_order_detail(lpo_no: Any) -> dict[str, Any] | None:
    from db import lpono_is_valid, parse_lpono_from_request

    key = parse_lpono_from_request(lpo_no)
    if not lpono_is_valid(key):
        return None

    with _erp_session_scope():
        p = _purchase()
        p._apply_db()
        hdr = p._get_lpo_header(key)
        if not hdr:
            return None
        lines_raw = p._get_lpo_details(key) or []
        status = str(p._get_po_approval_status(key) or "DRAFT").strip().upper()
        sup_code = str(hdr.get("suppliercode") or "").strip()
        sup = p._get_supplier_profile(sup_code) if sup_code else {}
        d = hdr.get("lpodate")
        if hasattr(d, "strftime"):
            date_s = d.strftime("%Y-%m-%d")
        else:
            date_s = str(d or "")[:10]

        lines: list[dict[str, Any]] = []
        for i, ln in enumerate(lines_raw, 1):
            row = dict(ln or {})
            qty = _to_float(row.get("quantity"))
            rate = _to_float(row.get("rate"))
            disc = _to_float(row.get("discount"))
            lines.append(
                {
                    "line_no": i,
                    "item_code": str(row.get("itemcode") or row.get("item_code") or "").strip(),
                    "item_name": str(row.get("itemname") or row.get("item_name") or "").strip(),
                    "uom": str(row.get("uom") or "NOS").strip(),
                    "qty": qty,
                    "rate": rate,
                    "discount": disc,
                    "amount": _to_float(row.get("amount"), qty * rate - disc),
                    "barcode": str(row.get("barcode") or "").strip(),
                    "warehouse_id": row.get("warehouse_id"),
                    "warehouse_code": str(row.get("warehouse_code") or "").strip() or None,
                }
            )

        return {
            "lpono": str(key).strip(),
            "lpo_date": date_s,
            "supplier_code": sup_code,
            "supplier_name": str(sup.get("name") or "").strip(),
            "discount": _to_float(hdr.get("discount")),
            "other_charge": _to_float(hdr.get("othercharge")),
            "amount": _to_float(hdr.get("lpoamount")),
            "remarks": str(hdr.get("remarks") or "").strip(),
            "warehouse_id": hdr.get("warehouse_id"),
            "approval_status": status,
            "has_grn": (has_grn := bool(p._po_has_receipt_for_lpo(key))),
            "can_edit": status not in ("CANCELLED", "CANCELED") and not has_grn,
            "lines": lines,
        }


def list_suppliers(*, search: str = "", limit: int = 80) -> list[dict[str, Any]]:
    lim = max(1, min(int(limit or 80), 200))
    q = (search or "").strip().upper()
    with _erp_session_scope():
        p = _purchase()
        p._apply_db()
        rows = p._get_suppliers() or []
        out: list[dict[str, Any]] = []
        for r in rows:
            code = str(r.get("code") or "").strip()
            name = str(r.get("name") or "").strip()
            if not code:
                continue
            if q and q not in code.upper() and q not in name.upper():
                continue
            out.append({"code": code, "name": name or code})
            if len(out) >= lim:
                break
        return out


def list_catalog_items(*, search: str = "", limit: int = 60, supplier_code: str = "") -> list[dict[str, Any]]:
    """List one row per ITEMMASTER item (base UOM) for the PO catalog.

    Alternate UOMs are chosen after tap via ``list_item_uoms``. ``supplier_code`` is
    accepted for API compatibility but ignored (ITEMMASTER.SUPCODE is sparse).
    """
    lim = max(1, min(int(limit or 60), 200))
    with _erp_session_scope():
        p = _purchase()
        p._apply_db()
        # Prefer ITEMMASTER directly — alternate-UOM map expands one item into many rows.
        rows = p._get_items_for_location_filtered(
            search=(search or "").strip() or None,
            limit=lim,
            supplier_code=None,
        ) or []
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for r in rows:
            code = str(r.get("code") or r.get("itemcode") or "").strip()
            if not code or code in seen:
                continue
            seen.add(code)
            out.append(
                {
                    "item_code": code,
                    "item_name": str(r.get("name") or r.get("itemname") or "").strip(),
                    "uom": str(r.get("uom") or "NOS").strip() or "NOS",
                    "rate": _to_float(r.get("cost") or r.get("costprice") or r.get("rate")),
                    "barcode": str(r.get("barcode") or "").strip(),
                    "current_stock": _to_float(
                        r.get("currentstock")
                        if r.get("currentstock") is not None
                        else r.get("CURRENTSTOCK") or r.get("stock")
                    ),
                }
            )
            if len(out) >= lim:
                break
        return out


def list_item_uoms(item_code: str) -> list[dict[str, Any]]:
    """UOM dropdown options: ITEMMASTER base UOM first, then alternate map UOMs."""
    try:
        ic = int(float(str(item_code).strip()))
    except (TypeError, ValueError):
        return []
    if ic <= 0:
        return []
    with _erp_session_scope():
        p = _purchase()
        p._apply_db()
        out: list[dict[str, Any]] = []
        seen: set[str] = set()

        def _add(uom: str, rate: float, barcode: str = "", factor: float = 1.0) -> None:
            key = (uom or "").strip().upper()
            if not key or key in seen:
                return
            seen.add(key)
            out.append(
                {
                    "uom": (uom or "").strip(),
                    "rate": float(rate or 0),
                    "barcode": (barcode or "").strip(),
                    "factor": float(factor or 1) if float(factor or 0) > 0 else 1.0,
                }
            )

        # Always include ITEMMASTER.BASEUOM (catalog base) even when alt-map omits it.
        try:
            from db import _detect_column, _detect_table, _fetch_rows

            im = _detect_table(["ITEMMASTER", "itemmaster", "ITEM_MASTER"])
            if im:
                code_col = _detect_column(im, ["ITEMCODE", "ITEM_CODE", "itemcode"])
                uom_col = _detect_column(im, ["BASEUOM", "BASE_UOM", "baseuom"])
                cost_col = _detect_column(im, ["COSTPRICE", "COST_PRICE", "costprice", "COST", "cost"])
                bc_col = _detect_column(
                    im, ["MANUFACTURERID", "MANUFACTURER_ID", "manufacturerid", "BARCODE", "barcode"]
                )
                loc_col = _detect_column(im, ["LOCATIONCODE", "LOCATION_CODE", "locationcode"])
                if code_col and uom_col:
                    loc = int(p._resolve_location_code())
                    where = f"{code_col} = :item"
                    params: dict[str, Any] = {"item": ic}
                    if loc_col:
                        where += f" AND {loc_col} = :loc"
                        params["loc"] = loc
                    cost_sql = f"NVL({cost_col}, 0)" if cost_col else "0"
                    bc_sql = f"NVL(TRIM({bc_col}), '')" if bc_col else "''"
                    q = (
                        f"SELECT TRIM({uom_col}) AS uom, {cost_sql} AS cost, {bc_sql} AS barcode "
                        f"FROM {im} WHERE {where} AND ROWNUM = 1"
                    )
                    _, im_rows = _fetch_rows(q, params)
                    if im_rows:
                        r0 = im_rows[0]
                        _add(
                            str(r0.get("uom") or "").strip() or "NOS",
                            _to_float(r0.get("cost")),
                            str(r0.get("barcode") or "").strip(),
                            1.0,
                        )
        except Exception:
            pass

        for r in p._get_item_uoms_with_cost(ic) or []:
            uom = str(r.get("uom") or "").strip()
            if not uom:
                continue
            _add(
                uom,
                _to_float(r.get("cost") or r.get("costprice") or r.get("rate")),
                str(r.get("barcode") or "").strip(),
                _to_float(r.get("factor") or r.get("uomfactor") or 1, 1.0),
            )

        if not out:
            _add("NOS", 0.0)
        return out


def list_warehouses(*, search: str = "", limit: int = 100) -> list[dict[str, Any]]:
    lim = max(1, min(int(limit or 100), 300))
    q = (search or "").strip().lower()
    with _erp_session_scope():
        p = _purchase()
        p._apply_db()
        if not p._po_warehouse_enabled():
            return []
        rows = p._get_lpo_warehouse_picker_rows(doc_kind="purchase") or []
        out: list[dict[str, Any]] = []
        for r in rows:
            wid = str(r.get("code") or r.get("warehouse_id") or "").strip()
            wcode = str(r.get("store") or r.get("warehouse_code") or "").strip()
            wname = str(r.get("name") or r.get("warehouse_name") or "").strip()
            label = str(r.get("label") or wname or wcode or wid).strip()
            if q and q not in f"{wid} {wcode} {wname} {label}".lower():
                continue
            out.append(
                {
                    "warehouse_id": wid,
                    "warehouse_code": wcode,
                    "warehouse_name": wname,
                    "label": label,
                }
            )
            if len(out) >= lim:
                break
        return out


def save_order(payload: dict[str, Any], *, username: str) -> dict[str, Any]:
    from db import (
        ensure_lpono_varchar_columns,
        ensure_purchase_approval_docno_varchar,
        lpono_is_valid,
        parse_lpono_from_request,
    )

    header = dict(payload.get("header") or {})
    lines_in = list(payload.get("lines") or [])
    if not lines_in:
        raise ValueError("Add at least one line item.")

    approval_save_as = str(header.get("approval_save_as") or "draft").strip().lower()
    if approval_save_as not in ("draft", "approved"):
        approval_save_as = "draft"
    doc = str(header.get("lpono") or header.get("lpo_no") or "").strip()

    with mobile_operation_lock(
        "purchase_order",
        doc,
        lock_seconds=120.0,
        busy_message="Purchase order is already being saved. Please wait.",
    ), _erp_session_scope() as user:
        p = _purchase()
        p._apply_db()
        ensure_lpono_varchar_columns()
        ensure_purchase_approval_docno_varchar()

        lpo_no = parse_lpono_from_request(header.get("lpono") or header.get("lpo_no"))
        if not lpono_is_valid(lpo_no):
            lpo_no = p._lpo_next_no()
        if p._get_po_approval_status(lpo_no) == "CANCELLED":
            raise ValueError("This purchase order is canceled and cannot be changed.")
        # Approved/draft POs may be re-saved; block once any GRN (draft or posted) exists.
        if p._get_lpo_header(lpo_no) and p._po_has_receipt_for_lpo(lpo_no):
            raise ValueError("This purchase order has a GRN and cannot be changed.")

        lpo_date = str(header.get("lpo_date") or header.get("lpodate") or "")[:10]
        open_date, txn_err = p._enforce_purchase_open_date(lpo_date, "purchase")
        if txn_err:
            # Mobile may send calendar today / old edit date — snap to preferred open date.
            open_date, txn_err = p._enforce_purchase_open_date("", "purchase")
        if txn_err:
            raise ValueError(txn_err)
        lpo_date = open_date or lpo_date or datetime.now().strftime("%Y-%m-%d")

        try:
            supplier_code = int(float(str(header.get("supplier_code") or header.get("suppliercode") or 0)))
        except (TypeError, ValueError):
            supplier_code = 0
        if supplier_code <= 0:
            raise ValueError("Supplier is required.")

        discount = _to_float(header.get("discount"))
        other_charge = _to_float(header.get("other_charge") or header.get("othercharge"))
        remarks = str(header.get("remarks") or "").strip()

        warehouse_id = None
        wh_raw = header.get("warehouse_id")
        if wh_raw not in (None, ""):
            try:
                warehouse_id = int(float(str(wh_raw).strip()))
                if warehouse_id <= 0:
                    warehouse_id = None
            except (TypeError, ValueError):
                warehouse_id = None
        if p._po_warehouse_enabled() and warehouse_id is None:
            raise ValueError("Select a warehouse.")

        lines: list[dict[str, Any]] = []
        for raw in lines_in:
            ln = dict(raw or {})
            try:
                ic = int(float(str(ln.get("item_code") or ln.get("itemcode") or 0)))
            except (TypeError, ValueError):
                ic = 0
            if ic <= 0:
                continue
            qty = _to_float(ln.get("quantity") or ln.get("qty"))
            if qty <= 0:
                raise ValueError(f"Item {ic}: quantity must be greater than zero.")
            rate = _to_float(ln.get("rate"))
            disc = _to_float(ln.get("discount"))
            amount = _to_float(ln.get("amount"), qty * rate - disc)
            uom = str(ln.get("uom") or "NOS").strip() or "NOS"
            lines.append(
                {
                    "itemcode": ic,
                    "item_code": ic,
                    "quantity": qty,
                    "rate": rate,
                    "discount": disc,
                    "amount": amount,
                    "uom": uom,
                    "barcode": str(ln.get("barcode") or "").strip(),
                    "warehouse_id": ln.get("warehouse_id") or warehouse_id,
                    "baseqty": _to_float(ln.get("base_qty") or ln.get("baseqty") or qty, qty),
                }
            )
        if not lines:
            raise ValueError("Add at least one valid line item.")

        requested = lpo_no
        lpo_no, lpo_reassigned = p._resolve_lpo_no_for_save(requested)
        err = None
        for _ in range(8):
            try:
                err = p._save_lpo(
                    lpo_no,
                    lpo_date,
                    supplier_code,
                    discount,
                    other_charge,
                    remarks,
                    lines,
                    warehouse_id=warehouse_id,
                )
            except Exception as e:
                err = str(e) or "Save failed"
            if not err:
                break
            if not p._is_duplicate_doc_key_error(err):
                break
            retry_no = p._allocate_next_free_lpo_no(lpo_no)
            if str(retry_no) == str(lpo_no):
                break
            lpo_no = retry_no
            lpo_reassigned = True
        if err:
            raise ValueError(err)

        if approval_save_as == "approved":
            p._set_po_approval_status(lpo_no, "APPROVED", "SAVE_APPROVED", remarks or "Saved as approved")
            approval_out = "APPROVED"
        else:
            p._set_po_approval_status(lpo_no, "DRAFT", "SAVE_DRAFT", remarks or "Saved as draft")
            approval_out = "DRAFT"

        try:
            from db import _get_connection
            from addons.document_numbering.document_numbering_db import (
                DOC_TYPE_LPO,
                advance_document_series_after_save_cur,
            )
            from mobile_backend.database.transaction import oracle_transaction

            with _get_connection() as conn:
                with oracle_transaction(conn):
                    with conn.cursor() as cur:
                        advance_document_series_after_save_cur(
                            cur,
                            DOC_TYPE_LPO,
                            lpo_no,
                            location_code=p._resolve_location_code(),
                            reset_no=getattr(p, "RESET_NO", 1),
                            user=str(user or username or "mobile"),
                        )
        except Exception:
            pass

        msg = f"Purchase order saved ({approval_out})."
        if lpo_reassigned:
            msg = f"LPO {requested} was in use. Saved as {lpo_no}."
        return {
            "lpono": str(lpo_no).strip(),
            "requested_lpono": str(requested).strip(),
            "lpono_reassigned": bool(lpo_reassigned),
            "approval_status": approval_out,
            "message": msg,
        }


def cancel_order(lpo_no: Any) -> dict[str, Any]:
    from db import lpono_is_valid, parse_lpono_from_request

    key = parse_lpono_from_request(lpo_no)
    if not lpono_is_valid(key):
        raise ValueError("Invalid purchase order number.")

    with mobile_operation_lock(
        "purchase_order",
        str(key),
        busy_message="Purchase order is already being updated. Please wait.",
    ), _erp_session_scope():
        p = _purchase()
        p._apply_db()
        if not p._get_lpo_header(key):
            raise ValueError("Purchase order not found.")
        if p._get_po_approval_status(key) == "CANCELLED":
            raise ValueError("Purchase order is already canceled.")
        if p._po_has_receipt_for_lpo(key):
            raise ValueError("Cannot cancel: a goods receipt exists for this PO.")
        p._set_po_approval_status(key, "CANCELLED", "CANCEL", "Canceled from mobile")
        return {
            "lpono": str(key).strip(),
            "approval_status": "CANCELLED",
            "message": f"Purchase order {key} canceled.",
        }


def build_order_pdf(lpo_no: Any) -> tuple[bytes, str]:
    """ERP purchase-order PDF (same ReportLab layout as desktop PO print/share)."""
    from db import coerce_lpono, lpono_is_valid, parse_lpono_from_request

    key = parse_lpono_from_request(lpo_no)
    if not lpono_is_valid(key):
        raise ValueError("Invalid purchase order number.")

    with _erp_session_scope():
        p = _purchase()
        p._apply_db()
        pdf_bytes, err = p._build_lpo_pdf_bytes(key)
        if err or not pdf_bytes:
            raise ValueError(str(err or "Failed to generate purchase order PDF."))
        safe = str(coerce_lpono(key) or key).replace("/", "-").replace("\\", "-")
        return pdf_bytes, f"PO_{safe}.pdf"
