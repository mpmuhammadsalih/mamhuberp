"""Mobile Purchase Return — wraps ERP Purchase Return Order (TEMPRETURN*) helpers."""

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


def get_open_context() -> dict[str, Any]:
    with _erp_session_scope() as username:
        p = _purchase()
        p._apply_db()
        next_no = p._return_order_next_no()
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
            "return_no": str(next_no or "").strip(),
            "return_date": open_date,
            "open_date_from": str(txn.get("open_transaction_date_from") or open_date)[:10],
            "open_date_to": str(txn.get("open_transaction_date_to") or open_date)[:10],
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


def list_returns(
    *,
    tab: str = "draft",
    search: str = "",
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    tab_key = (tab or "draft").strip().lower()
    if tab_key not in ("draft", "posted", "all", "pending"):
        tab_key = "draft"
    with _erp_session_scope():
        p = _purchase()
        p._apply_db()
        rows, total = p._get_purchase_return_list_page(
            page=max(1, int(page or 1)),
            per_page=max(20, min(int(page_size or 50), 100)),
            search=(search or "").strip() or None,
            list_tab=tab_key,
        )
        out: list[dict[str, Any]] = []
        for raw in rows or []:
            r = dict(raw or {})
            kind = str(r.get("row_kind") or "").strip().lower()
            status = str(r.get("approval_status") or "DRAFT").strip().upper()
            posted_no = str(r.get("posted_stock_no") or r.get("pr_doc_no") or "").strip()
            # Normalize ERP kinds (request_draft / pr_posted / …) for the mobile client.
            is_temp_request = kind.startswith("request") or kind in ("", "request")
            if kind in ("pr_draft",):
                ui_kind = "posted"
                if status in ("", "DRAFT"):
                    status = "DRAFT"
            elif kind in ("pr_posted", "posted", "posted_linked") or tab_key == "posted":
                ui_kind = "posted"
                status = "POSTED"
            elif is_temp_request:
                ui_kind = "request"
                if not status:
                    status = "DRAFT"
                if posted_no:
                    ui_kind = "posted"
                    status = "POSTED"
            else:
                ui_kind = "posted" if posted_no or tab_key == "posted" else "request"
            return_no = str(
                (r.get("goodsreturnno") if ui_kind == "request" else None)
                or r.get("pr_doc_no")
                or r.get("posted_stock_no")
                or r.get("goodsreturnno")
                or ""
            ).strip()
            can_edit = (
                ui_kind == "request"
                and status not in ("CANCELLED", "CANCELED", "APPROVED", "POSTED")
                and not posted_no
            )
            out.append(
                {
                    "return_no": return_no,
                    "return_date": _fmt_date(r.get("returndate")),
                    "supplier_code": str(r.get("suppliercode") or "").strip(),
                    "supplier_name": str(r.get("suppliername") or "").strip(),
                    "amount": _to_float(r.get("returnamount") or r.get("amount")),
                    "approval_status": status,
                    "row_kind": ui_kind,
                    "receipt_no": str(r.get("receiptno") or "").strip(),
                    "posted_stock_no": posted_no,
                    "can_edit": can_edit,
                }
            )
        return {
            "returns": out,
            "total_count": int(total or 0),
            "page": max(1, int(page or 1)),
            "page_size": max(20, min(int(page_size or 50), 100)),
        }


def get_request_detail(return_no: Any) -> dict[str, Any] | None:
    from db import coerce_goodsreturnno, goodsreturnno_is_valid, parse_goodsreturnno_from_request

    key = parse_goodsreturnno_from_request(return_no)
    if not goodsreturnno_is_valid(key):
        return None
    with _erp_session_scope():
        p = _purchase()
        p._apply_db()
        hdr = p._get_purchase_return_header(key)
        if not hdr:
            return None
        lines_raw = p._get_purchase_return_details(key) or []
        status = str(hdr.get("approval_status") or p._get_return_request_approval_status(key) or "DRAFT").strip().upper()
        posted = str(hdr.get("posted_stock_no") or "").strip()
        can_edit = status not in ("CANCELLED", "CANCELED", "APPROVED") and not posted
        lines: list[dict[str, Any]] = []
        for i, ln in enumerate(lines_raw, 1):
            row = dict(ln or {})
            qty = _to_float(row.get("quantity"))
            rate = _to_float(row.get("rate") or row.get("costprice"))
            disc = _to_float(row.get("discount"))
            lines.append(
                {
                    "line_no": i,
                    "item_code": str(row.get("itemcode") or "").strip(),
                    "item_name": str(row.get("itemname") or "").strip(),
                    "uom": str(row.get("uom") or "NOS").strip(),
                    "qty": qty,
                    "rate": rate,
                    "discount": disc,
                    "amount": max(0.0, qty * rate - disc),
                    "barcode": str(row.get("barcode") or "").strip(),
                    "factor": _to_float(row.get("conversionfactor") or 1, 1.0),
                    "warehouse_id": row.get("warehouse_id"),
                    "warehouse_code": str(row.get("store") or "").strip() or None,
                }
            )
        sup_code = str(hdr.get("suppliercode") or "").strip()
        sup = p._get_supplier_profile(sup_code) if hasattr(p, "_get_supplier_profile") and sup_code else {}
        return {
            "document_type": "return_request",
            "return_no": str(coerce_goodsreturnno(key)).strip(),
            "return_date": _fmt_date(hdr.get("returndate")),
            "supplier_code": sup_code,
            "supplier_name": str((sup or {}).get("name") or "").strip(),
            "receipt_no": str(hdr.get("receiptno") or "").strip(),
            "amount": _to_float(hdr.get("returnamount")),
            "discount": _to_float(hdr.get("discount")),
            "remarks": str(hdr.get("sectioninc") or hdr.get("remarks") or "").strip(),
            "approval_status": status,
            "posted_stock_no": posted,
            "can_edit": can_edit,
            "can_cancel": can_edit,
            "can_approve": can_edit and bool(lines),
            "lines": lines,
        }


def get_posted_detail(return_no: Any) -> dict[str, Any] | None:
    from db import coerce_goodsreturnno, goodsreturnno_is_valid, parse_goodsreturnno_from_request

    key = parse_goodsreturnno_from_request(return_no)
    if not goodsreturnno_is_valid(key):
        return None
    with _erp_session_scope():
        p = _purchase()
        p._apply_db()
        hdr = p._get_posted_purchase_return_header(key)
        if not hdr:
            return None
        lines_raw = p._get_posted_purchase_return_details(key) or []
        lines: list[dict[str, Any]] = []
        for i, ln in enumerate(lines_raw, 1):
            row = dict(ln or {})
            qty = _to_float(row.get("quantity"))
            rate = _to_float(row.get("rate") or row.get("costprice"))
            disc = _to_float(row.get("discount"))
            lines.append(
                {
                    "line_no": i,
                    "item_code": str(row.get("itemcode") or "").strip(),
                    "item_name": str(row.get("itemname") or "").strip(),
                    "uom": str(row.get("uom") or "NOS").strip(),
                    "qty": qty,
                    "rate": rate,
                    "discount": disc,
                    "amount": max(0.0, qty * rate - disc),
                    "barcode": str(row.get("barcode") or "").strip(),
                    "factor": _to_float(row.get("conversionfactor") or 1, 1.0),
                    "warehouse_id": row.get("warehouse_id"),
                    "warehouse_code": str(row.get("store") or "").strip() or None,
                }
            )
        return {
            "document_type": "posted_return",
            "return_no": str(coerce_goodsreturnno(key)).strip(),
            "return_date": _fmt_date(hdr.get("returndate")),
            "supplier_code": str(hdr.get("suppliercode") or "").strip(),
            "supplier_name": str(hdr.get("suppliername") or "").strip(),
            "receipt_no": str(hdr.get("receiptno") or "").strip(),
            "amount": _to_float(hdr.get("returnamount")),
            "discount": _to_float(hdr.get("discount")),
            "remarks": str(hdr.get("remarks") or hdr.get("sectioninc") or "").strip(),
            "approval_status": "POSTED",
            "posted_stock_no": str(coerce_goodsreturnno(key)).strip(),
            "can_edit": False,
            "can_cancel": False,
            "can_approve": False,
            "lines": lines,
        }


def _normalize_pr_save_mode(raw: Any) -> str:
    mode = str(raw or "pr_draft").strip().lower()
    if mode in ("draft", "pr_draft", "grn_draft"):
        return "pr_draft"
    if mode in ("inventory_only", "pr_only", "grn_only", "approved", "pr_post"):
        return "pr_only"
    if mode in ("inventory_accounts", "pr_posting", "grn_invoice_posting", "accounts"):
        return "pr_posting"
    return "pr_draft"


def save_request(payload: dict[str, Any], *, username: str = "mobile") -> dict[str, Any]:
    """Save purchase return with GRN-style modes: draft / stock only / stock + accounts."""
    from db import (
        coerce_goodsreturnno,
        goodsreturnno_is_valid,
        parse_goodsreturnno_from_request,
        parse_receiptno_from_request,
        receiptno_is_valid,
    )

    header = dict(payload.get("header") or {})
    lines_in = list(payload.get("lines") or [])
    if not lines_in:
        raise ValueError("Add at least one line item.")
    doc = str(header.get("return_no") or header.get("goodsreturnno") or "").strip()
    save_mode = _normalize_pr_save_mode(
        payload.get("save_mode") or header.get("save_mode") or "pr_draft"
    )
    post_inventory_raw = payload.get("post_inventory")
    if post_inventory_raw is None:
        post_inventory_raw = header.get("post_inventory")
    if post_inventory_raw is not None:
        if isinstance(post_inventory_raw, str):
            post_inventory = post_inventory_raw.strip().lower() not in ("0", "false", "no", "")
        else:
            post_inventory = bool(post_inventory_raw)
    else:
        post_inventory = save_mode != "pr_draft"
    post_accounts = save_mode == "pr_posting"

    with mobile_operation_lock(
        "purchase_return",
        doc,
        busy_message="Purchase return is already being saved. Please wait.",
    ), _erp_session_scope():
        p = _purchase()
        p._apply_db()

        return_no = parse_goodsreturnno_from_request(
            header.get("return_no") or header.get("goodsreturnno")
        )
        if not goodsreturnno_is_valid(return_no):
            return_no = coerce_goodsreturnno(p._return_order_next_no())

        existing = p._get_purchase_return_header(return_no)
        if existing:
            st = str(
                existing.get("approval_status")
                or p._get_return_request_approval_status(return_no)
                or "DRAFT"
            ).upper()
            if st in ("CANCELLED", "CANCELED"):
                raise ValueError("This return is canceled and cannot be changed.")
            if st == "APPROVED" or str(existing.get("posted_stock_no") or "").strip():
                raise ValueError("This return is already posted and cannot be changed.")

        return_date = str(header.get("return_date") or header.get("returndate") or "")[:10]
        open_date, txn_err = p._enforce_purchase_open_date(return_date, "purchase")
        if txn_err:
            open_date, txn_err = p._enforce_purchase_open_date("", "purchase")
        if txn_err:
            raise ValueError(txn_err)
        return_date = open_date or return_date or datetime.now().strftime("%Y-%m-%d")

        try:
            supplier_code = int(float(str(header.get("supplier_code") or header.get("suppliercode") or 0)))
        except (TypeError, ValueError):
            supplier_code = 0
        if supplier_code <= 0:
            raise ValueError("Supplier is required.")

        receipt_raw = header.get("receipt_no") or header.get("receiptno")
        receipt_no = None
        if str(receipt_raw or "").strip():
            rn = parse_receiptno_from_request(receipt_raw)
            if receiptno_is_valid(rn):
                receipt_no = rn

        remarks = str(header.get("remarks") or "").strip()
        discount = _to_float(header.get("discount"))

        lines: list[dict[str, Any]] = []
        total = 0.0
        for raw in lines_in:
            ln = dict(raw or {})
            item = ln.get("item_code") or ln.get("itemcode")
            qty = _to_float(ln.get("quantity") if ln.get("quantity") is not None else ln.get("qty"))
            rate = _to_float(ln.get("rate") or ln.get("costprice"))
            disc = _to_float(ln.get("discount"))
            if not str(item or "").strip() or qty <= 0:
                continue
            amt = max(0.0, qty * rate - disc)
            total += amt
            factor = _to_float(ln.get("factor") or ln.get("conversionfactor") or 1, 1.0)
            row: dict[str, Any] = {
                "itemcode": item,
                "item_code": item,
                "quantity": qty,
                "qty": qty,
                "rate": rate,
                "uom": str(ln.get("uom") or "NOS").strip() or "NOS",
                "discount": disc,
                "amount": amt,
                "conversionfactor": factor if factor > 0 else 1.0,
                "barcode": str(ln.get("barcode") or "").strip(),
                "costprice": rate,
            }
            wh = ln.get("warehouse_id")
            if wh not in (None, ""):
                row["warehouse_id"] = wh
            wh_code = str(ln.get("warehouse_code") or ln.get("store") or "").strip()
            if wh_code:
                row["store"] = wh_code
                row["warehouse_code"] = wh_code
            lines.append(row)

        if not lines:
            raise ValueError("Add at least one line item.")

        amount = total - discount
        err = p._save_purchase_return_order(
            return_no,
            return_date,
            supplier_code,
            receipt_no,
            amount,
            "P",
            remarks,
            lines,
            posting_date=return_date,
            discount=discount,
        )
        if err:
            raise ValueError(str(err))

        final_no = str(coerce_goodsreturnno(return_no)).strip()
        if not post_inventory:
            p._set_return_request_approval_status(
                return_no, "DRAFT", "SAVE_DRAFT", remarks or f"Saved by {username}"
            )
            return {
                "return_no": final_no,
                "approval_status": "DRAFT",
                "amount": amount,
                "save_mode": save_mode,
                "inventory_posted": False,
                "accounts_posted": False,
                "message": f"Purchase return {final_no} saved as draft. Stock is not posted yet.",
            }

        # Approve & post stock (creates RETURNHDR + inventory), same as ERP option 2/3.
        post_err, posted_no, status = p._approve_return_order_and_post_stock(
            return_no, remarks=remarks or f"Posted from mobile ({save_mode})"
        )
        if post_err:
            raise ValueError(str(post_err))

        accounts_posted = False
        if post_accounts and posted_no:
            acct_err = p._post_saved_purchase_return(
                posted_no, source_return_order_no=return_no
            )
            if acct_err:
                raise ValueError(
                    f"Purchase return {posted_no} stock posted, but accounts posting failed: {acct_err}"
                )
            accounts_posted = True

        out_no = str(coerce_goodsreturnno(posted_no or return_no)).strip()
        if accounts_posted:
            msg = f"Purchase return {out_no} saved and posted (stock + accounts)."
        else:
            msg = f"Purchase return {out_no} saved. Stock posted (use Accounts Posting for GL when needed)."
        return {
            "return_no": out_no,
            "posted_stock_no": str(posted_no or "").strip(),
            "approval_status": str(status or "POSTED").upper(),
            "amount": amount,
            "save_mode": save_mode,
            "inventory_posted": True,
            "accounts_posted": accounts_posted,
            "message": msg,
        }


def cancel_request(return_no: Any) -> dict[str, Any]:
    from db import coerce_goodsreturnno, goodsreturnno_is_valid, parse_goodsreturnno_from_request

    key = parse_goodsreturnno_from_request(return_no)
    if not goodsreturnno_is_valid(key):
        raise ValueError("Invalid return number.")
    with mobile_operation_lock(
        "purchase_return",
        str(key),
        busy_message="Purchase return is already being updated. Please wait.",
    ), _erp_session_scope():
        p = _purchase()
        p._apply_db()
        hdr = p._get_purchase_return_header(key)
        if not hdr:
            raise ValueError("Return request not found.")
        st = str(
            hdr.get("approval_status") or p._get_return_request_approval_status(key) or "DRAFT"
        ).upper()
        if st in ("CANCELLED", "CANCELED"):
            raise ValueError("Return is already canceled.")
        if st == "APPROVED" or str(hdr.get("posted_stock_no") or "").strip():
            raise ValueError("Cannot cancel: return stock is already posted.")
        p._set_return_request_approval_status(key, "CANCELLED", "CANCEL", "Canceled from mobile")
        return {
            "return_no": str(coerce_goodsreturnno(key)).strip(),
            "approval_status": "CANCELLED",
            "message": f"Purchase return {coerce_goodsreturnno(key)} canceled.",
        }


def approve_request(return_no: Any, *, remarks: str = "") -> dict[str, Any]:
    from db import coerce_goodsreturnno, goodsreturnno_is_valid, parse_goodsreturnno_from_request

    key = parse_goodsreturnno_from_request(return_no)
    if not goodsreturnno_is_valid(key):
        raise ValueError("Invalid return number.")
    with mobile_operation_lock(
        "purchase_return_post",
        str(key),
        lock_seconds=120.0,
        busy_message="Purchase return is already being posted. Please wait.",
    ), _erp_session_scope():
        p = _purchase()
        p._apply_db()
        err, posted_no, status = p._approve_return_order_and_post_stock(
            key, remarks=remarks or "Approved from mobile"
        )
        if err:
            raise ValueError(str(err))
        return {
            "return_no": str(coerce_goodsreturnno(key)).strip(),
            "posted_stock_no": str(posted_no or "").strip(),
            "approval_status": str(status or "POSTED").upper(),
            "message": f"Purchase return posted"
            + (f" as {posted_no}." if posted_no else "."),
        }


def build_request_pdf(return_no: Any) -> tuple[bytes, str]:
    from db import coerce_goodsreturnno, goodsreturnno_is_valid, parse_goodsreturnno_from_request

    key = parse_goodsreturnno_from_request(return_no)
    if not goodsreturnno_is_valid(key):
        raise ValueError("Invalid return number.")
    with _erp_session_scope():
        p = _purchase()
        p._apply_db()
        pdf_bytes, err = p._build_purchase_return_order_pdf_bytes(key)
        if err or not pdf_bytes:
            raise ValueError(str(err or "Failed to generate return PDF."))
        safe = str(coerce_goodsreturnno(key)).replace("/", "-").replace("\\", "-")
        return pdf_bytes, f"PurchaseReturnOrder_{safe}.pdf"


def build_posted_pdf(return_no: Any) -> tuple[bytes, str]:
    from db import coerce_goodsreturnno, goodsreturnno_is_valid, parse_goodsreturnno_from_request

    key = parse_goodsreturnno_from_request(return_no)
    if not goodsreturnno_is_valid(key):
        raise ValueError("Invalid return number.")
    with _erp_session_scope():
        p = _purchase()
        p._apply_db()
        pdf_bytes, err = p._build_purchase_return_pdf_bytes(key)
        if err or not pdf_bytes:
            raise ValueError(str(err or "Failed to generate return PDF."))
        safe = str(coerce_goodsreturnno(key)).replace("/", "-").replace("\\", "-")
        return pdf_bytes, f"PurchaseReturn_{safe}.pdf"
