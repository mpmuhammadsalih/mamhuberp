"""Mobile Stock Adjustment — wraps ERP STKADJHDR/STKADJDTL helpers."""

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


def _fmt_date(v: Any) -> str:
    if v is None:
        return ""
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d")
    return str(v or "")[:10]


def _status_from_row(remarks: str, *, reversed_by: Any = None, is_reversal: bool = False) -> str:
    if is_reversal or str(remarks or "").upper().startswith("REVERSAL OF STOCK ADJUSTMENT"):
        return "REVERSAL"
    if reversed_by not in (None, "", 0, "0"):
        return "REVERSED"
    return "POSTED"


def get_open_context() -> dict[str, Any]:
    with _erp_session_scope() as username:
        p = _purchase()
        p._apply_db()
        from mobile_backend.services.doc_peek import fresh_doc_no
        from mobile_backend.services.transaction_date_helper import (
            missing_setup_date_message,
            open_context as txn_open_context,
        )

        def _adj_exists(n: Any) -> bool:
            try:
                return bool(p._get_stock_adjustment_payload(n))
            except Exception:
                return False

        next_no = fresh_doc_no(
            peek_fn=lambda: p._stock_adjustment_next_no(allocate=False),
            exists_fn=_adj_exists,
            allocate_fn=lambda _n: p._stock_adjustment_next_no(allocate=True),
        )

        txn = txn_open_context("stock_adjustment")
        open_date = str(txn.get("preferred_date") or "")[:10]
        if not open_date:
            raise ValueError(
                txn.get("transaction_date_error")
                or missing_setup_date_message("stock_adjustment")
            )
        opening_mode = False
        try:
            from db import get_stk_adj_opening_stock_mode_enabled

            opening_mode = bool(get_stk_adj_opening_stock_mode_enabled())
        except Exception:
            opening_mode = False
        stores = p._get_transfer_store_options(skip_tbllocation_maintenance=True) or []
        default_store = ""
        if stores:
            default_store = str(stores[0].get("code") or "").strip()
        return {
            "adj_no": str(next_no or "").strip(),
            "adj_date": open_date,
            "open_date_from": str(txn.get("open_date_from") or open_date)[:10],
            "open_date_to": str(txn.get("open_date_to") or open_date)[:10],
            "transaction_date_blocked": bool(txn.get("transaction_date_blocked")),
            "created_by": username,
            "opening_stock_mode": opening_mode,
            "default_store": default_store,
        }


def list_adjustments(
    *,
    search: str = "",
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    with _erp_session_scope():
        p = _purchase()
        p._apply_db()
        lim = max(50, min(int(page_size or 50) * max(1, int(page or 1)), 300))
        rows = p._get_stock_adjustment_list(search=(search or "").strip(), limit=lim) or []
        rev_map = {}
        try:
            rev_map = p._stock_adjustment_reversal_map() or {}
        except Exception:
            rev_map = {}
        out: list[dict[str, Any]] = []
        for raw in rows:
            r = dict(raw or {})
            adj_no = str(r.get("adjno") or r.get("adj_no") or "").strip()
            remarks = str(r.get("remarks") or "").strip()
            try:
                adj_key = int(float(adj_no)) if str(adj_no).replace(".", "", 1).isdigit() else adj_no
            except (TypeError, ValueError):
                adj_key = adj_no
            reversed_by = rev_map.get(adj_key) or rev_map.get(str(adj_key))
            is_reversal = remarks.upper().startswith("REVERSAL OF STOCK ADJUSTMENT") or remarks.upper().startswith(
                "[OPENING_STOCK] REVERSAL"
            )
            status = _status_from_row(remarks, reversed_by=reversed_by, is_reversal=is_reversal)
            can_reverse = status == "POSTED"
            out.append(
                {
                    "adj_no": adj_no,
                    "adj_date": _fmt_date(r.get("adjdate") or r.get("adj_date")),
                    "remarks": remarks,
                    "created_by": str(r.get("createdby") or r.get("created_by") or "").strip(),
                    "stock_value": _to_float(r.get("stock_value")),
                    "status": status,
                    "reversed_by": str(reversed_by or "").strip() if reversed_by else "",
                    "can_reverse": can_reverse,
                }
            )
        page_i = max(1, int(page or 1))
        size = max(20, min(int(page_size or 50), 100))
        start = (page_i - 1) * size
        page_rows = out[start : start + size]
        return {
            "adjustments": page_rows,
            "total_count": len(out),
            "page": page_i,
            "page_size": size,
        }


def get_detail(adj_no: Any) -> dict[str, Any] | None:
    with _erp_session_scope():
        p = _purchase()
        p._apply_db()
        from db.inventory_doc_numbers import adjno_is_valid, coerce_adjno, parse_adjno_from_request

        key = parse_adjno_from_request(adj_no)
        if not adjno_is_valid(key):
            return None
        payload = p._get_stock_adjustment_payload(key)
        if not payload:
            return None
        header = dict(payload.get("header") or {})
        lines_raw = list(payload.get("lines") or [])
        remarks = str(header.get("remarks") or "").strip()
        rev_of = None
        try:
            rev_of = p._stock_adjustment_reversal_of(key)
        except Exception:
            rev_of = None
        is_reversal = remarks.upper().startswith("REVERSAL OF STOCK ADJUSTMENT")
        status = _status_from_row(remarks, reversed_by=rev_of, is_reversal=is_reversal)
        block = None
        try:
            block = p._stock_adjustment_reverse_block_reason(key)
        except Exception:
            block = None
        can_reverse = not bool(block) and status == "POSTED"
        lines: list[dict[str, Any]] = []
        for i, ln in enumerate(lines_raw, 1):
            row = dict(ln or {})
            lines.append(
                {
                    "line_no": i,
                    "item_code": str(row.get("item_code") or "").strip(),
                    "item_name": str(row.get("item_name") or "").strip(),
                    "uom": str(row.get("uom") or "NOS").strip() or "NOS",
                    "store": str(row.get("store") or "").strip(),
                    "current_qty": _to_float(row.get("current_qty")),
                    "adjust_qty": _to_float(row.get("adjust_qty")),
                    "new_qty": _to_float(row.get("new_qty")),
                    "base_qty": _to_float(row.get("base_qty")),
                    "cost": _to_float(row.get("cost")),
                }
            )
        return {
            "adj_no": str(coerce_adjno(key)).strip(),
            "adj_date": str(header.get("adj_date") or "")[:10],
            "remarks": remarks,
            "opening_stock": bool(header.get("opening_stock")),
            "status": status,
            "reversed_by": str(rev_of or "").strip() if rev_of else "",
            "can_reverse": can_reverse,
            "reverse_block_reason": str(block or "").strip(),
            "lines": lines,
        }


def list_warehouses() -> list[dict[str, Any]]:
    with _erp_session_scope():
        p = _purchase()
        p._apply_db()
        stores = p._get_transfer_store_options(skip_tbllocation_maintenance=True) or []
        codes = [
            str(s.get("code") or "").strip().upper()
            for s in stores
            if str(s.get("code") or "").strip()
        ]
        allow_neg: dict[str, bool] = {}
        try:
            _, wh_row_map = p._batch_warehouse_store_maps(codes)
            for wh in (wh_row_map or {}).values():
                code = str(wh.get("warehouse_code") or wh.get("WAREHOUSE_CODE") or "").strip().upper()
                if not code:
                    continue
                allow_neg[code] = (
                    str(wh.get("allow_negative_stock") or wh.get("ALLOW_NEGATIVE_STOCK") or "N")
                    .strip()
                    .upper()
                    == "Y"
                )
        except Exception:
            allow_neg = {}
        out: list[dict[str, Any]] = []
        for s in stores:
            code = str(s.get("code") or "").strip().upper()
            if not code:
                continue
            out.append(
                {
                    "code": code,
                    "name": str(s.get("description") or "").strip(),
                    "allow_negative_stock": allow_neg.get(code, False),
                }
            )
        return out


def list_catalog_items(*, search: str = "", limit: int = 80) -> list[dict[str, Any]]:
    with _erp_session_scope():
        p = _purchase()
        p._apply_db()
        lim = max(20, min(int(limit or 80), 200))
        rows = p._get_items_for_location_filtered(
            search=(search or "").strip() or None,
            limit=lim,
            supplier_code=None,
        )
        loc = p._resolve_location_code()
        codes: list[int] = []
        for r in rows or []:
            try:
                codes.append(int(float(str(r.get("code") or "").strip())))
            except (TypeError, ValueError):
                pass
        summary: dict[Any, Any] = {}
        try:
            from db import get_storeinventory_stock_summary_for_items

            summary = get_storeinventory_stock_summary_for_items(loc, codes) or {}
        except Exception:
            summary = {}
        out: list[dict[str, Any]] = []
        for r in rows or []:
            raw = r.get("code")
            try:
                ic = int(float(str(raw).strip()))
            except (TypeError, ValueError):
                ic = 0
            srow = summary.get(ic) if ic else None
            tot = _to_float((srow or {}).get("total"))
            out.append(
                {
                    "item_code": str(raw or "").strip(),
                    "item_name": str(r.get("name") or "").strip(),
                    "uom": str(r.get("uom") or "NOS").strip() or "NOS",
                    "barcode": str(r.get("barcode") or "").strip(),
                    "cost": _to_float(r.get("cost")),
                    "current_stock": tot,
                    "best_store": str((srow or {}).get("best_store") or "").strip(),
                }
            )
        return out


def list_item_uoms(item_code: str) -> list[dict[str, Any]]:
    with _erp_session_scope():
        p = _purchase()
        p._apply_db()
        try:
            ic = int(float(str(item_code).strip()))
        except (TypeError, ValueError):
            return []
        rows = p._get_item_uoms_with_cost(ic) or []
        out: list[dict[str, Any]] = []
        for r in rows:
            factor = _to_float(r.get("factor") or r.get("conversionfactor") or 1, 1.0)
            out.append(
                {
                    "uom": str(r.get("uom") or "NOS").strip() or "NOS",
                    "rate": _to_float(r.get("cost") or r.get("rate") or r.get("costprice")),
                    "barcode": str(r.get("barcode") or "").strip(),
                    "factor": factor if factor > 0 else 1.0,
                }
            )
        return out


def get_item_stock(*, item_code: str, store: str = "") -> dict[str, Any]:
    with _erp_session_scope():
        p = _purchase()
        p._apply_db()
        from db import get_item_store_inventory, get_item_store_rows_from_itemmaster

        try:
            ic = int(float(str(item_code).strip()))
        except (TypeError, ValueError):
            raise ValueError("Invalid item code.")
        loc = p._resolve_location_code()
        store_u = (store or "").strip().upper()
        rows = get_item_store_inventory(loc, ic) or []
        if not rows:
            try:
                rows = get_item_store_rows_from_itemmaster(ic, loc) or []
            except Exception:
                rows = []
        current_qty = 0.0
        if store_u:
            for r in rows:
                rs = str(r.get("store") or r.get("itemlocation") or "").strip().upper()
                if rs == store_u:
                    current_qty = _to_float(r.get("stock"))
                    break
        elif rows:
            best = max(rows, key=lambda x: _to_float(x.get("stock")))
            current_qty = _to_float(best.get("stock"))
            store_u = str(best.get("store") or best.get("itemlocation") or "").strip().upper()
        return {
            "item_code": str(ic),
            "store": store_u,
            "current_qty": current_qty,
            "stores": [
                {
                    "store": str(r.get("store") or r.get("itemlocation") or "").strip(),
                    "stock": _to_float(r.get("stock")),
                }
                for r in rows
            ],
        }


def save_adjustment(payload: dict[str, Any]) -> dict[str, Any]:
    header = dict(payload.get("header") or payload)
    lines_in = list(payload.get("lines") or [])
    if not lines_in:
        raise ValueError("Add at least one line.")
    doc = str(header.get("adj_no") or header.get("adjno") or "").strip()

    with mobile_operation_lock(
        "stock_adjustment",
        doc,
        lock_seconds=180.0,
        busy_message="Stock adjustment is already being saved. Please wait.",
    ):
        with _erp_session_scope():
            p = _purchase()
            p._apply_db()
            from db import get_stk_adj_opening_stock_mode_enabled
            from db.inventory_doc_numbers import adjno_is_valid, coerce_adjno, parse_adjno_from_request

            adj_no = parse_adjno_from_request(header.get("adj_no") or header.get("adjno"))
            if not adjno_is_valid(adj_no):
                adj_no = coerce_adjno(p._stock_adjustment_next_no(allocate=False))

            from mobile_backend.services.transaction_date_helper import resolve_doc_date

            adj_date = resolve_doc_date(
                "stock_adjustment",
                header.get("adj_date") or header.get("adjdate"),
                snap_out_of_range=True,
            )
            remarks = str(header.get("remarks") or "").strip()
            opening_stock = bool(header.get("opening_stock"))
            if "opening_stock" not in header:
                try:
                    opening_stock = bool(get_stk_adj_opening_stock_mode_enabled())
                except Exception:
                    opening_stock = False

            lines: list[dict[str, Any]] = []
            for raw in lines_in:
                ln = dict(raw or {})
                item = ln.get("item_code") or ln.get("itemcode")
                if not str(item or "").strip():
                    continue
                adj_qty = _to_float(
                    ln.get("adjust_qty") if ln.get("adjust_qty") is not None else ln.get("adjustqty")
                )
                if abs(adj_qty) < 1e-09:
                    continue
                from mobile_backend.services.uom_factor import apply_line_stock_base

                uom = str(ln.get("uom") or "NOS").strip() or "NOS"
                current_qty = _to_float(
                    ln.get("current_qty") if ln.get("current_qty") is not None else ln.get("currentqty")
                )
                new_qty = ln.get("new_qty")
                if new_qty in (None, ""):
                    new_qty = current_qty + adj_qty
                else:
                    new_qty = _to_float(new_qty)
                row: dict[str, Any] = {
                    "item_code": item,
                    "item_name": str(ln.get("item_name") or ln.get("itemname") or "").strip(),
                    "uom": uom,
                    "store": str(ln.get("store") or ln.get("warehouse_code") or "").strip().upper(),
                    "current_qty": current_qty,
                    "adjust_qty": adj_qty,
                    "new_qty": new_qty,
                    "cost": _to_float(ln.get("cost") or ln.get("rate") or ln.get("costprice")),
                    "remarks": str(ln.get("remarks") or ln.get("line_remarks") or "").strip(),
                    "factor": ln.get("factor") or ln.get("conversionfactor"),
                    "conversionfactor": ln.get("conversionfactor") or ln.get("factor"),
                }
                # ERP posts stock with base_qty; always recompute from UOM map (ignore stale client 1).
                base = apply_line_stock_base(
                    row, item_code=item, uom=uom, qty=adj_qty, st=p, signed=True
                )
                row["base_qty"] = base
                lines.append(row)
            if not lines:
                raise ValueError("Add at least one line with a non-zero adjust quantity.")

            # ERP finalize owns commit (stock + journal + GL).
            resp_body, status = p._stock_adjustment_finalize_save(
                adj_no,
                adj_date,
                remarks,
                lines,
                opening_stock=opening_stock,
            )
            if not resp_body.get("success"):
                err = str(resp_body.get("error") or "Failed to save stock adjustment.")
                raise ValueError(err)
            return {
                "adj_no": str(resp_body.get("adj_no") or coerce_adjno(adj_no)).strip(),
                "needs_approval": bool(resp_body.get("needs_approval")),
                "gl_voucher_no": str(resp_body.get("gl_voucher_no") or "").strip() or None,
                "message": str(resp_body.get("message") or "Stock adjustment saved."),
                "status": "PENDING" if resp_body.get("needs_approval") else "POSTED",
            }


def reverse_adjustment(adj_no: Any) -> dict[str, Any]:
    with mobile_operation_lock(
        "stock_adjustment_reverse",
        str(adj_no or "").strip(),
        lock_seconds=180.0,
        busy_message="Stock adjustment reverse is already in progress. Please wait.",
    ):
        with _erp_session_scope() as username:
            p = _purchase()
            p._apply_db()
            from db.inventory_doc_numbers import adjno_is_valid, coerce_adjno, parse_adjno_from_request

            key = parse_adjno_from_request(adj_no)
            if not adjno_is_valid(key):
                raise ValueError("Invalid adjustment number.")
            ok, err, rev_no = p._reverse_stock_adjustment(key, user=username)
            if not ok:
                raise ValueError(str(err or "Could not reverse stock adjustment."))
            return {
                "source_adj_no": str(coerce_adjno(key)).strip(),
                "adj_no": str(coerce_adjno(rev_no)).strip(),
                "message": f"Reversed as SA-{coerce_adjno(rev_no)}.",
            }


def build_pdf(adj_no: Any) -> tuple[bytes, str]:
    with _erp_session_scope():
        p = _purchase()
        p._apply_db()
        from db.inventory_doc_numbers import adjno_is_valid, coerce_adjno, parse_adjno_from_request

        key = parse_adjno_from_request(adj_no)
        if not adjno_is_valid(key):
            raise ValueError("Invalid adjustment number.")
        pdf_bytes, err = p._build_stock_adjustment_pdf_bytes(key)
        if err or not pdf_bytes:
            raise ValueError(str(err or "Failed to generate PDF."))
        safe = str(coerce_adjno(key)).replace("/", "-").replace("\\", "-")
        return pdf_bytes, f"StockAdjustment_{safe}.pdf"
