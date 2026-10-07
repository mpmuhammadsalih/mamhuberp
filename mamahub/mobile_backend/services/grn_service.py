"""Formal GRN — delegates to ERP purchase receipt logic (same as goods_receipt_form.html)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from mobile_backend.operation_lock import mobile_operation_lock
from mobile_backend.services.stock_transfer_service import _erp_session_scope


def _purchase_st():
    from addons.purchase.controllers import routes as st

    return st


def _fmt_date(val: Any) -> str:
    if isinstance(val, datetime):
        return val.strftime("%b %d, %Y")
    s = str(val or "").strip()
    if len(s) >= 10 and s[4:5] == "-":
        try:
            return datetime.strptime(s[:10], "%Y-%m-%d").strftime("%b %d, %Y")
        except ValueError:
            pass
    return s


def _line_float(row: dict[str, Any], *keys: str) -> float:
    for k in keys:
        if k not in row and k.lower() not in row and k.upper() not in row:
            # still try .get for convenience
            pass
        raw = row.get(k)
        if raw is None:
            raw = row.get(k.lower())
        if raw is None:
            raw = row.get(k.upper())
        if raw in (None, ""):
            continue
        try:
            return float(raw)
        except (TypeError, ValueError):
            continue
    return 0.0


def _lpo_receivable_qty(ln: dict[str, Any]) -> float:
    """PO ordered qty for new formal GRN (same as ERP goods_receipt_form load-from-lpo).

    Uses QUANTITY/BASEQTY. Does not subtract INQUANTITY — that column is used by the
    legacy mobile goods-receiving snapshot and would incorrectly hide lines for POs
    that still have no RECEIPTHDR.
    """
    ordered = _line_float(ln, "quantity", "qty", "orderqty", "orderedqty")
    if ordered <= 0:
        ordered = _line_float(ln, "baseqty")
    if ordered <= 0:
        # Legacy schemas that only populate INQUANTITY as the order qty.
        ordered = _line_float(ln, "inquantity", "inquanttity")
    return max(0.0, ordered)


def _map_pending_po_row(row: dict[str, Any]) -> dict[str, Any]:
    lpo = str(row.get("lpono") or "").strip()
    sup_nm = str(row.get("suppliername") or "").strip()
    sup_cd = str(row.get("suppliercode") or "").strip()
    return {
        "receipt_no": lpo,
        "supplier": sup_nm or sup_cd,
        "po_no": lpo,
        "invoice_no": "",
        "receipt_date": _fmt_date(row.get("lpodate")),
        "amount": float(row.get("amount") or 0),
        "remarks": "",
        "total_qty": 0,
        "status": "Approved",
        "approval_status": "APPROVED",
        "lr_flag": "",
        "mobile_lines_touched": 0,
        "mobile_last_saved_at": None,
    }


def _map_receipt_row(row: dict[str, Any], *, inventory_tab: str) -> dict[str, Any]:
    rn = str(row.get("receiptno") or "").strip()
    sup_nm = str(row.get("suppliername") or "").strip()
    sup_cd = str(row.get("suppliercode") or "").strip()
    status = "Draft" if inventory_tab == "draft" else "Posted"
    if inventory_tab == "posted" and row.get("inventory_posted"):
        status = "Posted"
    return {
        "receipt_no": rn,
        "supplier": sup_nm or sup_cd,
        "po_no": str(row.get("lpono") or row.get("lpo_no") or "").strip(),
        "invoice_no": str(row.get("invoiceno") or "").strip(),
        "receipt_date": _fmt_date(row.get("receiptdate")),
        "amount": float(row.get("amount") or row.get("invoiceamount") or 0),
        "remarks": "",
        "total_qty": 0,
        "status": status,
        "approval_status": str(row.get("approval_status") or "").strip(),
        "lr_flag": "",
        "mobile_lines_touched": 0,
        "mobile_last_saved_at": None,
        "can_edit": bool(row.get("can_edit", inventory_tab == "draft")),
        "can_delete": bool(row.get("can_delete", inventory_tab == "draft")),
        "inventory_posted": bool(row.get("inventory_posted")),
    }


def list_pending_approved_pos(
    page: int,
    page_size: int,
    search: str = "",
) -> list[dict[str, Any]]:
    """ERP Approved PO tab — approved LPO without RECEIPTHDR."""
    with _erp_session_scope():
        st = _purchase_st()
        st._apply_db()
        rows, _ = st._get_pending_po_for_grn_page(
            page=max(page, 1),
            per_page=min(max(page_size, 1), 100),
            search=search.strip() or None,
        )
        return [_map_pending_po_row(r) for r in rows or []]


def list_receipt_documents(
    page: int,
    page_size: int,
    search: str = "",
    *,
    inventory_tab: str = "posted",
) -> list[dict[str, Any]]:
    """ERP Draft GRN / GRN list tabs."""
    tab = (inventory_tab or "posted").strip().lower()
    with _erp_session_scope():
        st = _purchase_st()
        st._apply_db()
        rows, _ = st._get_receipt_list_page(
            page=max(page, 1),
            per_page=min(max(page_size, 1), 100),
            search=search.strip() or None,
            inventory_tab=tab,
        )
        return [_map_receipt_row(r, inventory_tab=tab) for r in rows or []]


def next_receipt_no() -> Any:
    from db import coerce_receiptno
    from mobile_backend.services.doc_peek import fresh_doc_no

    with _erp_session_scope():
        st = _purchase_st()
        st._apply_db()
        return coerce_receiptno(
            fresh_doc_no(
                peek_fn=st._receipt_next_no,
                exists_fn=st._receipt_no_exists_in_hdr,
                allocate_fn=lambda n: st._allocate_next_free_receipt_no(n),
            )
        )


def _apply_erp_stock_qty_fields(
    line: dict[str, Any],
    *,
    st: Any,
    item_code: Any,
) -> None:
    """
    Set conversionfactor / baseqty / receivedqty like ERP goods_receipt_form.

    Stock posting uses: stock_qty_base = quantity × conversionfactor + bonus
    and requires receivedqty ≈ that base qty.
    """
    from mobile_backend.services.uom_factor import apply_line_stock_base, stock_base_qty

    uom = str(line.get("uom") or line.get("unit") or "PCS").strip() or "PCS"
    qty = abs(_line_float(line, "quantity", "qty"))
    bonus = abs(_line_float(line, "bonus"))
    line["quantity"] = qty
    line["bonus"] = bonus
    baseqty = apply_line_stock_base(
        line, item_code=item_code, uom=uom, qty=qty, bonus=bonus, st=st
    )
    # Keep explicit GRN receivedqty (ERP validates against base)
    line["receivedqty"] = stock_base_qty(qty, float(line.get("conversionfactor") or 1), bonus)
    if abs(baseqty - line["receivedqty"]) > 1e-9:
        line["receivedqty"] = baseqty


def _normalize_mobile_line(
    raw: dict[str, Any],
    warehouse_id: int | None,
    st: Any,
) -> dict[str, Any]:
    item_raw = raw.get("itemcode") or raw.get("item_code")
    # Ordered qty in line UOM (not base). Prefer quantity/qty over receivedqty —
    # receivedqty may already be base from a prior ERP-shaped payload.
    qty = _line_float(raw, "quantity", "qty")
    if qty <= 0:
        # Fallback: if only received/base sent, treat as UOM qty when factor is 1 later
        qty = _line_float(raw, "receivedqty", "baseqty")
    rate = _line_float(raw, "rate")
    unit = str(raw.get("uom") or raw.get("unit") or "PCS").strip() or "PCS"
    amount = raw.get("amount")
    try:
        amount_f = float(amount) if amount is not None else qty * rate
    except (TypeError, ValueError):
        amount_f = qty * rate
    line: dict[str, Any] = {
        "itemcode": item_raw,
        "quantity": qty,
        "uom": unit,
        "rate": rate,
        "amount": amount_f,
        "discount": _line_float(raw, "discount"),
        "othercharge": _line_float(raw, "othercharge"),
        "bonus": _line_float(raw, "bonus"),
        "foc": bool(raw.get("foc")),
        "conversionfactor": raw.get("conversionfactor") or raw.get("uomfactor"),
        "barcode": str(raw.get("barcode") or "").strip(),
        "itemname": str(raw.get("itemname") or raw.get("item_name") or "").strip(),
    }
    wh_code = str(
        raw.get("warehouse_code") or raw.get("location") or raw.get("store") or ""
    ).strip()
    if wh_code:
        line["warehouse_code"] = wh_code
        line["location"] = wh_code
        line["inventorylocation"] = wh_code
    if raw.get("warehouse_id") not in (None, ""):
        line["warehouse_id"] = raw.get("warehouse_id")
    elif warehouse_id and warehouse_id > 0:
        line["warehouse_id"] = warehouse_id
    return line


def _prepare_erp_lines(
    lines: list[dict[str, Any]],
    warehouse_id: int | None,
    st: Any,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ln in lines or []:
        erp_ln = _normalize_mobile_line(ln, warehouse_id, st)
        inv_loc = st._line_warehouse_code_from_payload(erp_ln, warehouse_id)
        if not inv_loc:
            idx = len(out) + 1
            raise ValueError(
                f"Inventory location required at line {idx}. "
                "Set warehouse on the PO or pass warehouse_id in the save payload."
            )
        erp_ln["location"] = inv_loc
        erp_ln["warehouse_code"] = inv_loc
        erp_ln["inventorylocation"] = inv_loc
        code = st._coerce_grn_item_code(erp_ln.get("itemcode"))
        if code is None:
            raise ValueError(f"Invalid item code: {erp_ln.get('itemcode')!r}")
        erp_ln["itemcode"] = code
        _apply_erp_stock_qty_fields(erp_ln, st=st, item_code=code)
        out.append(erp_ln)
    if not out:
        raise ValueError("Add at least one GRN line with a valid item code.")
    return out


def _normalize_item_code(raw: Any) -> str:
    s = str(raw or "").strip()
    if not s or s in ("0", "0.0"):
        return ""
    try:
        n = float(s)
        if n == int(n):
            return str(int(n))
    except (TypeError, ValueError):
        pass
    return s


def _items_from_erp_lpo_details(details: list[dict[str, Any]], header: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for idx, ln in enumerate(details or [], start=1):
        item_code = _normalize_item_code(ln.get("itemcode") or ln.get("item_code"))
        if not item_code:
            continue
        qty = _lpo_receivable_qty(ln)
        if qty <= 0:
            continue
        rate = _line_float(ln, "rate")
        items.append(
            {
                "line_seq": idx,
                "item_code": item_code,
                "item_name": str(ln.get("itemname") or ln.get("item_name") or ""),
                "unit": str(ln.get("uom") or ln.get("unit") or "PCS"),
                "qty": qty,
                "quantity": qty,
                "ordered_qty": _line_float(ln, "quantity", "qty", "baseqty"),
                "received_qty": _line_float(ln, "inquantity", "inquanttity", "receivedqty"),
                "rate": rate,
                "warehouse_id": ln.get("warehouse_id") or header.get("warehouse_id"),
                "warehouse_code": ln.get("warehouse_code") or ln.get("location") or "",
            }
        )
    return items


def _fetch_lpo_details_without_enrich(
    st: Any,
    lpo_key: Any,
    *,
    ignore_location: bool = False,
) -> list[dict[str, Any]]:
    """Fetch LPODTL like ERP, but skip enrich (enrich exceptions were returning [])."""
    from db import (
        _detect_column,
        _detect_table,
        _fetch_rows,
        coerce_lpono,
        lpodtl_warehouse_code_column,
    )
    reset_no = int(getattr(st, "RESET_NO", 1) or 1)

    dtl = _detect_table(["LPODTL", "lpodtl"])
    if not dtl:
        return []
    lpo_col = _detect_column(dtl, ["LPONO", "LPO_NO", "lpono"])
    item_col = _detect_column(dtl, ["ITEMCODE", "ITEM_CODE", "itemcode"])
    qty_col = _detect_column(dtl, ["QUANTITY", "quantity"])
    rate_col = _detect_column(dtl, ["RATE", "rate"])
    uom_col = _detect_column(dtl, ["UNITOFMEASUREMENT", "UNIT_OF_MEASUREMENT", "unitofmeasurement"])
    loc_col = _detect_column(dtl, ["LOCATIONCODE", "LOCATION_CODE", "locationcode"])
    reset_col = _detect_column(dtl, ["RESETNO", "RESET_NO", "resetno"])
    if not lpo_col or not item_col:
        return []
    try:
        loc_code = st._resolve_location_code()
    except Exception:
        loc_code = 1
    inq_col = _detect_column(
        dtl,
        ["INQUANTITY", "IN_QUANTITY", "inquantity", "INQUANTTITY", "IN_QUANTTITY", "inquanttity", "INQTY", "IN_QTY", "inqty"],
    )
    d_base = _detect_column(dtl, ["BASEQTY", "BASE_QTY", "baseqty"])
    d_wh = _detect_column(dtl, ["WAREHOUSE_ID", "warehouse_id"])
    d_wh_code = lpodtl_warehouse_code_column(dtl)
    im_tbl = _detect_table(["ITEMMASTER", "itemmaster", "ITEM_MASTER"])
    im_code = _detect_column(im_tbl, ["ITEMCODE", "ITEM_CODE", "itemcode"]) if im_tbl else None
    im_name = _detect_column(im_tbl, ["ITEMNAME", "ITEM_NAME", "itemname"]) if im_tbl else None
    im_loc = _detect_column(im_tbl, ["LOCATIONCODE", "LOCATION_CODE", "locationcode"]) if im_tbl else None

    qty_sel = f"{dtl}.{qty_col} AS quantity" if qty_col else "0 AS quantity"
    inq_sel = f"{dtl}.{inq_col} AS inquantity" if inq_col else "NULL AS inquantity"
    rate_sel = f"{dtl}.{rate_col} AS rate" if rate_col else "0 AS rate"
    uom_sel = f"{dtl}.{uom_col} AS uom" if uom_col else "NULL AS uom"
    base_sel = f"{dtl}.{d_base} AS baseqty" if d_base else "NULL AS baseqty"
    wh_sel = f"{dtl}.{d_wh} AS warehouse_id" if d_wh else "NULL AS warehouse_id"
    whc_sel = f"{dtl}.{d_wh_code} AS warehouse_code" if d_wh_code else "NULL AS warehouse_code"

    # Match series keys (PO-000003) and bare/padded numeric forms.
    where = (
        f"({dtl}.{lpo_col} = :lpo OR TO_CHAR({dtl}.{lpo_col}) = :lpo_txt "
        f"OR UPPER(TO_CHAR({dtl}.{lpo_col})) = UPPER(:lpo_txt) "
        f"OR LTRIM(REGEXP_REPLACE(TO_CHAR({dtl}.{lpo_col}), '^[A-Za-z]+-', ''), '0') "
        f"= LTRIM(REGEXP_REPLACE(:lpo_txt, '^[A-Za-z]+-', ''), '0'))"
    )
    params: dict[str, Any] = {
        "lpo": coerce_lpono(lpo_key),
        "lpo_txt": str(lpo_key or "").strip(),
    }
    if loc_col and not ignore_location:
        where += f" AND {dtl}.{loc_col} = :loc"
        params["loc"] = loc_code
    if reset_col:
        where += f" AND {dtl}.{reset_col} = :rn"
        params["rn"] = reset_no

    name_sel = "NULL AS itemname"
    from_sql = dtl
    if im_tbl and im_code and im_name:
        name_sel = f"{im_tbl}.{im_name} AS itemname"
        join_on = f"{dtl}.{item_col} = {im_tbl}.{im_code}"
        if loc_col and im_loc and not ignore_location:
            join_on += f" AND {dtl}.{loc_col} = {im_tbl}.{im_loc}"
        from_sql = f"{dtl} LEFT JOIN {im_tbl} ON {join_on}"
    q = (
        f"SELECT {dtl}.{item_col} AS itemcode, {name_sel}, {qty_sel}, {inq_sel}, {rate_sel}, "
        f"{uom_sel}, {base_sel}, {wh_sel}, {whc_sel} "
        f"FROM {from_sql} WHERE {where} ORDER BY {dtl}.{item_col}"
    )
    try:
        _, rows = _fetch_rows(q, params)
        return list(rows or [])
    except Exception:
        return []


def _items_from_mobile_lpo_details(po_lookup: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """TO_CHAR LPODTL loader — reliable when ERP _get_lpo_details returns [] (enrich/bind issues)."""
    from mobile_backend.services.purchase_service import (
        _lpo_lookup_key_variants,
        get_goods_receipt_details,
    )

    for key in _lpo_lookup_key_variants(po_lookup):
        try:
            data = get_goods_receipt_details(key)
        except Exception:
            continue
        # Skip if this key resolved to a formal RECEIPTHDR document.
        if str(data.get("document_type") or "") == "formal_receipt":
            continue
        raw_items = data.get("items") or []
        out: list[dict[str, Any]] = []
        for idx, it in enumerate(raw_items, start=1):
            code = _normalize_item_code(it.get("item_code") or it.get("itemcode"))
            if not code:
                continue
            qty = float(it.get("qty") or it.get("quantity") or 0)
            if qty <= 0:
                continue
            out.append(
                {
                    "line_seq": idx,
                    "item_code": code,
                    "item_name": str(it.get("item_name") or it.get("itemname") or ""),
                    "unit": str(it.get("unit") or it.get("uom") or "PCS"),
                    "qty": qty,
                    "quantity": qty,
                    "ordered_qty": qty,
                    "received_qty": float(it.get("erp_received_qty") or it.get("received_qty") or 0),
                    "rate": float(it.get("rate") or 0),
                    "warehouse_id": it.get("warehouse_id"),
                    "warehouse_code": str(it.get("warehouse_code") or it.get("location") or ""),
                }
            )
        if out:
            return out, data
    return [], {}


def load_from_lpo(lpo_no: Any) -> dict[str, Any]:
    """Same as GET /purchase/receipt/api/load-from-lpo/{lpo_no}."""
    from db import coerce_receiptno, lpono_is_valid, parse_lpono_from_request

    raw_lpo = str(lpo_no or "").strip()
    with _erp_session_scope():
        st = _purchase_st()
        st._apply_db()
        lpo_key = parse_lpono_from_request(lpo_no)
        if not lpono_is_valid(lpo_key):
            raise ValueError("Invalid purchase order number")
        # Series docs are stored as PO-000003; mobile may send 000003 after stripping.
        from mobile_backend.services.purchase_service import _lpo_lookup_key_variants

        key_candidates: list[Any] = []
        for k in _lpo_lookup_key_variants(raw_lpo or str(lpo_key)):
            parsed = parse_lpono_from_request(k)
            if lpono_is_valid(parsed) and parsed not in key_candidates:
                key_candidates.append(parsed)
            if k not in key_candidates:
                key_candidates.append(k)
        if lpo_key not in key_candidates:
            key_candidates.insert(0, lpo_key)

        details: list[dict[str, Any]] = []
        header: dict[str, Any] = {}
        resolved_key = lpo_key
        for cand in key_candidates:
            hdr_try = st._get_lpo_header(cand) or {}
            dtl_try = st._get_lpo_details(cand) or []
            if not dtl_try:
                dtl_try = _fetch_lpo_details_without_enrich(st, cand)
            if not dtl_try:
                dtl_try = _fetch_lpo_details_without_enrich(st, cand, ignore_location=True)
            if hdr_try or dtl_try:
                header = hdr_try or header
                details = dtl_try or details
                resolved_key = cand
                if details:
                    break
        lpo_key = resolved_key
        st._lpo_resolve_header_warehouse(header, lpo_key, lines=details)
        # Prefer Transaction Date Setup open date for new GRNs (not calendar/PO date).
        from mobile_backend.services.transaction_date_helper import resolve_doc_date

        open_date = resolve_doc_date("grn", None, snap_out_of_range=True)
        txn = st._purchase_txn_date_context("grn")
        if not header.get("lpoamount"):
            total = 0.0
            for line in details:
                qty = _lpo_receivable_qty(line)
                rate = float(line.get("rate") or 0)
                disc = float(line.get("discount") or 0)
                foc = line.get("foc") in (True, 1, "1", "Y", "y")
                total += 0.0 if foc else max(0.0, qty * rate - disc)
            header["lpoamount"] = round(total, 2)

        items = _items_from_erp_lpo_details(details, header)
        mobile_meta: dict[str, Any] = {}
        if not items:
            # ERP detail fetch often returns [] when enrich fails; TO_CHAR path still works.
            items, mobile_meta = _items_from_mobile_lpo_details(raw_lpo or str(lpo_key))

        # Ensure supplier name is resolved (ERP attaches on header load; re-run for safety).
        try:
            st._lpo_attach_supplier_display(header)
        except Exception:
            pass
        sup_raw = header.get("suppliercode")
        if (sup_raw is None or str(sup_raw).strip() == "") and mobile_meta:
            sup_raw = mobile_meta.get("supplier") or mobile_meta.get("supplier_code")
        if sup_raw is None or str(sup_raw).strip() == "":
            sup_cd = ""
        else:
            try:
                # Oracle may return 12.0 — keep integer codes clean for save/UI.
                sup_cd = str(int(float(str(sup_raw).strip())))
            except (TypeError, ValueError):
                sup_cd = str(sup_raw).strip()
        if not header.get("suppliername") and not header.get("supplier_display") and sup_cd:
            try:
                prof = st._get_supplier_profile(sup_cd) or {}
                name = str(prof.get("name") or "").strip()
                if name:
                    header["suppliername"] = name
                    header["supplier_display"] = f"{sup_cd} - {name}"
                else:
                    header["supplier_display"] = sup_cd
            except Exception:
                header["supplier_display"] = sup_cd
        if not header.get("suppliername") and mobile_meta.get("supplier_name"):
            header["suppliername"] = str(mobile_meta.get("supplier_name") or "").strip()
            if sup_cd and header["suppliername"]:
                header["supplier_display"] = f"{sup_cd} - {header['suppliername']}"
        sup_nm = str(header.get("suppliername") or "").strip()
        sup_disp = str(header.get("supplier_display") or "").strip()
        if not sup_disp:
            sup_disp = f"{sup_cd} - {sup_nm}" if (sup_cd and sup_nm) else (sup_nm or sup_cd)
        wh_id = header.get("warehouse_id")
        try:
            wh_id_int = int(wh_id) if wh_id not in (None, "") else None
        except (TypeError, ValueError):
            wh_id_int = None
        next_no = coerce_receiptno(st._receipt_next_no())
        amount = float(header.get("lpoamount") or 0)
        if amount <= 0 and mobile_meta.get("amount") is not None:
            try:
                amount = float(mobile_meta.get("amount") or 0)
            except (TypeError, ValueError):
                pass
        if amount <= 0 and items:
            amount = round(sum(float(x.get("qty") or 0) * float(x.get("rate") or 0) for x in items), 2)

        return {
            "document_type": "lpo_bootstrap",
            "receipt_no": str(next_no),
            "next_receipt_no": str(next_no),
            "po_no": str(resolved_key if lpono_is_valid(resolved_key) else (lpo_key or raw_lpo)),
            "receipt_date": _fmt_date(open_date),
            "grn_date": _fmt_date(open_date),
            "po_date": _fmt_date(header.get("lpodate") or mobile_meta.get("po_date")),
            "open_date_from": str(txn.get("open_transaction_date_from") or open_date)[:10],
            "open_date_to": str(txn.get("open_transaction_date_to") or open_date)[:10],
            "transaction_date_blocked": bool(txn.get("transaction_date_blocked")),
            "supplier": sup_cd,
            "supplier_code": sup_cd,
            "suppliercode": sup_cd,
            "supplier_name": sup_nm or sup_disp,
            "suppliername": sup_nm or sup_disp,
            "supplier_display": sup_disp,
            "remarks": str(header.get("remarks") or mobile_meta.get("remarks") or ""),
            "amount": amount,
            "warehouse_id": wh_id_int,
            "warehouse_display": str(header.get("warehouse_display") or ""),
            "invoice_no": "",
            "invoice_date": "",
            "status": "Approved",
            "lpo_line_count": len(details or []) or len(items),
            "items": items,
            "lines": items,
        }


def get_formal_receipt(receipt_no: Any) -> dict[str, Any]:
    """Load saved RECEIPTHDR/DTL for edit/view."""
    from db import parse_receiptno_from_request, receiptno_is_valid

    with _erp_session_scope():
        st = _purchase_st()
        st._apply_db()
        rn = parse_receiptno_from_request(receipt_no)
        if not receiptno_is_valid(rn):
            raise ValueError("Invalid GRN number")
        hdr = st._get_receipt_header_for_posting(rn)
        if not hdr:
            raise ValueError("GRN not found")
        lines = st._get_receipt_details(rn) or []
        inv_posted = st._grn_is_inventory_posted(rn)
        acct_posted = st._grn_is_account_posted(rn)
        is_draft = not inv_posted and not acct_posted

        items: list[dict[str, Any]] = []
        for idx, ln in enumerate(lines, start=1):
            qty = float(ln.get("quantity") or ln.get("receivedqty") or 0)
            items.append(
                {
                    "line_seq": idx,
                    "item_code": str(ln.get("itemcode") or ""),
                    "item_name": str(ln.get("itemname") or ln.get("description") or ""),
                    "unit": str(ln.get("uom") or ln.get("unit") or "PCS"),
                    "qty": qty,
                    "rate": float(ln.get("rate") or 0),
                    "warehouse_id": ln.get("warehouse_id"),
                    "warehouse_code": ln.get("warehouse_code") or ln.get("location") or "",
                }
            )

        wh_raw = hdr.get("warehouse_id")
        try:
            wh_id = int(wh_raw) if wh_raw not in (None, "") else None
        except (TypeError, ValueError):
            wh_id = None

        return {
            "document_type": "formal_receipt",
            "receipt_no": str(rn),
            "po_no": str(hdr.get("lpono") or ""),
            "receipt_date": _fmt_date(hdr.get("receiptdate")),
            "grn_date": _fmt_date(hdr.get("receiptdate")),
            "po_date": _fmt_date(hdr.get("receiptdate")),
            "supplier": str(hdr.get("suppliercode") or ""),
            "supplier_name": str(hdr.get("suppliername") or ""),
            "invoice_no": str(hdr.get("invoiceno") or ""),
            "invoice_date": _fmt_date(hdr.get("invoicedate")),
            "remarks": str(hdr.get("remarks") or ""),
            "amount": float(hdr.get("invoiceamount") or hdr.get("amount") or 0),
            "warehouse_id": wh_id,
            "status": "Draft" if is_draft else "Posted",
            "inventory_posted": inv_posted,
            "account_posted": acct_posted,
            "can_edit": is_draft,
            "can_delete": is_draft,
            "items": items,
        }


def delete_receipt(receipt_no: Any) -> dict[str, Any]:
    """Delete a draft GRN (not inventory/account posted) — same as ERP GRN Delete."""
    from db import parse_receiptno_from_request, receiptno_is_valid

    rn_key = str(receipt_no or "").strip()
    with mobile_operation_lock(
        "grn",
        rn_key,
        busy_message="GRN is already being updated. Please wait.",
    ), _erp_session_scope():
        st = _purchase_st()
        st._apply_db()
        rn = parse_receiptno_from_request(receipt_no)
        if not receiptno_is_valid(rn):
            raise ValueError("Invalid GRN number.")
        hdr = st._get_receipt_header_for_posting(rn)
        if not hdr:
            raise ValueError("GRN not found.")
        if st._grn_is_inventory_posted(rn):
            raise ValueError("Cannot cancel: stock is already posted for this GRN.")
        if st._grn_is_account_posted(rn):
            raise ValueError(
                "Cannot cancel: this GRN is posted to accounts. Reverse the posting first."
            )
        err = st._delete_receipt(rn)
        if err:
            raise ValueError(str(err))
        return {
            "receipt_no": str(rn),
            "deleted": True,
            "message": f"GRN {rn} canceled.",
        }


def save_receipt(payload: dict[str, Any]) -> dict[str, Any]:
    """ERP-aligned save — ``save_mode`` ``grn_draft`` (no stock) or ``grn_only`` (post stock)."""
    from db import (
        billno_numeric_part,
        coerce_receiptno,
        lpono_is_valid,
        parse_lpono_from_request,
        parse_receiptno_from_request,
        receiptno_equal,
        receiptno_is_valid,
    )

    header = dict(payload.get("header") or payload)
    doc = str(
        header.get("receipt_no")
        or header.get("receiptno")
        or payload.get("receipt_no")
        or payload.get("receiptno")
        or ""
    ).strip()
    with mobile_operation_lock(
        "grn",
        doc,
        lock_seconds=180.0,
        busy_message="GRN is already being saved. Please wait.",
    ), _erp_session_scope():
        st = _purchase_st()
        st._apply_db()

        receipt_no = parse_receiptno_from_request(
            payload.get("receipt_no") or payload.get("receiptno")
        )
        if not receiptno_is_valid(receipt_no):
            receipt_no = coerce_receiptno(st._receipt_next_no())

        from mobile_backend.services.transaction_date_helper import resolve_doc_date

        receipt_date = resolve_doc_date(
            "grn",
            payload.get("receipt_date") or payload.get("receiptdate"),
            snap_out_of_range=True,
        )

        try:
            supplier_code = int(payload.get("supplier_code") or payload.get("suppliercode") or 0)
        except (TypeError, ValueError):
            supplier_code = 0
        invoice_no = str(payload.get("invoice_no") or payload.get("invoiceno") or "").strip()
        invoice_date = str(payload.get("invoice_date") or payload.get("invoicedate") or "")[:10]
        if not invoice_date:
            invoice_date = receipt_date
        discount = float(payload.get("discount") or 0)
        invoice_amount = float(payload.get("invoice_amount") or payload.get("invoiceamount") or 0)
        header_other_charge = float(payload.get("othercharge") or payload.get("other_charge") or 0)
        remarks = str(payload.get("remarks") or "").strip()

        save_mode = str(payload.get("save_mode") or "grn_draft").strip().lower()
        if save_mode not in ("grn_only", "grn_draft", "grn_invoice_posting"):
            save_mode = "grn_draft"

        post_inventory_raw = payload.get("post_inventory")
        if post_inventory_raw is not None:
            if isinstance(post_inventory_raw, str):
                post_inventory = post_inventory_raw.strip().lower() not in ("0", "false", "no", "")
            else:
                post_inventory = bool(post_inventory_raw)
        elif save_mode == "grn_draft":
            post_inventory = False
        else:
            # ERP: grn_only and grn_invoice_posting both post stock.
            post_inventory = save_mode in ("grn_only", "grn_invoice_posting")

        lpo_raw = payload.get("po_no") or payload.get("lpono")
        lpo_no: Any | None = None
        if lpo_raw not in (None, ""):
            lpo_no = parse_lpono_from_request(lpo_raw)
            if not lpono_is_valid(lpo_no):
                lpo_no = None

        wh_raw = payload.get("warehouse_id")
        warehouse_id: int | None = None
        if wh_raw not in (None, ""):
            try:
                warehouse_id = int(wh_raw)
                if warehouse_id <= 0:
                    warehouse_id = None
            except (TypeError, ValueError):
                warehouse_id = None

        if not receipt_date or not supplier_code:
            raise ValueError("Receipt date and supplier are required")
        if not invoice_no or not invoice_date:
            raise ValueError("Invoice number and invoice date are required")

        raw_lines = payload.get("lines") or payload.get("items") or []
        lines = _prepare_erp_lines(raw_lines, warehouse_id, st)

        if invoice_amount <= 0:
            invoice_amount = round(
                sum(float(ln.get("amount") or 0) for ln in lines if not ln.get("foc")),
                2,
            )

        requested_no = receipt_no
        receipt_no, receipt_reassigned = st._resolve_receipt_no_for_save(
            requested_no, supplier_code, invoice_no, invoice_date
        )
        if (
            not receipt_reassigned
            and receiptno_is_valid(requested_no)
            and st._receipt_no_exists_in_hdr(requested_no)
        ):
            if st._grn_is_account_posted(requested_no):
                raise ValueError("This GRN is posted to accounts and cannot be changed.")
            if st._grn_is_inventory_posted(requested_no):
                raise ValueError("This GRN is posted to stock. Only draft GRNs can be edited.")

        editing_existing = (
            not receipt_reassigned
            and receiptno_is_valid(requested_no)
            and st._get_receipt_header_for_posting(requested_no) is not None
        )
        if not editing_existing or receipt_reassigned:
            dup_extras = (
                [requested_no]
                if (
                    receiptno_is_valid(requested_no)
                    and not receiptno_equal(requested_no, receipt_no)
                )
                else None
            )
            dup_no = st._receipt_find_duplicate_supplier_invoice(
                supplier_code, invoice_no, receipt_no, also_except=dup_extras
            )
            if dup_no is not None:
                raise ValueError(
                    f"The same invoice number is already saved for this supplier (GRN {dup_no})."
                )

        effective_save_mode = "grn_draft" if not post_inventory else save_mode
        err: str | None = None
        for _ in range(8):
            err = st._save_receipt(
                receipt_no,
                receipt_date,
                supplier_code,
                invoice_no,
                invoice_date,
                discount,
                invoice_amount,
                remarks,
                lpo_no,
                lines,
                save_mode=effective_save_mode,
                approve_mode=save_mode,
                invoice_snapshot_json=None,
                warehouse_id=warehouse_id,
                header_other_charge=header_other_charge,
                post_inventory=post_inventory,
            )
            if not err:
                break
            err_l = str(err).lower()
            if "duplicate key" not in err_l and "pk_receipthdr" not in err_l and "already in use" not in err_l:
                break
            retry_no = st._allocate_next_free_receipt_no(receipt_no)
            if billno_numeric_part(retry_no) <= billno_numeric_part(receipt_no):
                retry_no = coerce_receiptno(billno_numeric_part(receipt_no) + 1)
                while (
                    st._receipt_no_exists_in_hdr(retry_no)
                    and billno_numeric_part(retry_no) < billno_numeric_part(receipt_no) + 100
                ):
                    retry_no = coerce_receiptno(billno_numeric_part(retry_no) + 1)
            if receiptno_equal(retry_no, receipt_no):
                break
            receipt_no = retry_no

        if err:
            raise ValueError(str(err))

        if save_mode == "grn_invoice_posting" and post_inventory:
            msg = "GRN saved. Stock and accounts (purchase invoice / AP) posted."
            accounts_posted = True
        elif post_inventory:
            msg = (
                "GRN saved. Stock and item journal updated. "
                "Use Post accounts when ready for purchase invoice / AP."
            )
            accounts_posted = False
        else:
            msg = (
                "GRN saved as draft. Stock is not posted yet — open and choose "
                "Approve & post stock when ready."
            )
            accounts_posted = False
        return {
            "receipt_no": str(receipt_no),
            "posted": post_inventory,
            "inventory_posted": post_inventory,
            "account_posted": accounts_posted,
            "save_mode": save_mode if post_inventory else "grn_draft",
            "message": msg,
        }


def post_inventory(receipt_no: Any, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Post stock for an existing draft GRN (ERP api_receipt_post_inventory)."""
    from db import lpono_is_valid, parse_lpono_from_request, parse_receiptno_from_request, receiptno_is_valid

    payload = payload or {}
    with mobile_operation_lock(
        "grn_post",
        str(receipt_no or "").strip(),
        lock_seconds=180.0,
        busy_message="GRN is already being posted. Please wait.",
    ), _erp_session_scope():
        st = _purchase_st()
        st._apply_db()
        rn = parse_receiptno_from_request(receipt_no)
        if not receiptno_is_valid(rn):
            raise ValueError("Receipt number is required")
        if st._grn_is_account_posted(rn):
            raise ValueError("This GRN is posted to accounts and cannot be changed.")
        if st._grn_is_inventory_posted(rn):
            raise ValueError("Inventory is already posted for this GRN.")
        hdr = st._get_receipt_header_for_posting(rn)
        if not hdr:
            raise ValueError("GRN not found")

        wh_raw = payload.get("warehouse_id") or hdr.get("warehouse_id")
        warehouse_id: int | None = None
        if wh_raw not in (None, ""):
            try:
                warehouse_id = int(wh_raw)
                if warehouse_id <= 0:
                    warehouse_id = None
            except (TypeError, ValueError):
                warehouse_id = None

        body_lines = payload.get("lines") or payload.get("items")
        if isinstance(body_lines, list) and body_lines:
            lines = _prepare_erp_lines(body_lines, warehouse_id, st)
        else:
            lines = st._get_receipt_details(rn) or []
            for ln in lines:
                inv_loc = st._line_warehouse_code_from_payload(ln, warehouse_id)
                if inv_loc:
                    ln["location"] = inv_loc
                    ln["warehouse_code"] = inv_loc
                    ln["inventorylocation"] = inv_loc
                code = st._coerce_grn_item_code(ln.get("itemcode") or ln.get("item_code"))
                if code is not None:
                    ln["itemcode"] = code
                    # Recompute base stock qty from UOM factor (ERP parity) even if
                    # an older mobile draft stored conversionfactor=1.
                    _apply_erp_stock_qty_fields(ln, st=st, item_code=code)

        from mobile_backend.services.transaction_date_helper import resolve_doc_date

        receipt_date = resolve_doc_date(
            "grn",
            payload.get("receipt_date") or hdr.get("receiptdate"),
            snap_out_of_range=True,
        )
        supplier_code = int(payload.get("supplier_code") or hdr.get("suppliercode") or 0)
        invoice_no = str(payload.get("invoice_no") or hdr.get("invoiceno") or "").strip()
        invoice_date = str(payload.get("invoice_date") or hdr.get("invoicedate") or "")[:10]
        discount = float(payload.get("discount") if payload.get("discount") is not None else hdr.get("discount") or 0)
        invoice_amount = float(
            payload.get("invoice_amount")
            if payload.get("invoice_amount") is not None
            else hdr.get("invoiceamount") or 0
        )
        remarks = str(payload.get("remarks") if payload.get("remarks") is not None else hdr.get("remarks") or "")
        lpo_raw = payload.get("po_no") or hdr.get("lpono")
        lpo_no: Any | None = None
        if lpo_raw not in (None, ""):
            lpo_no = parse_lpono_from_request(lpo_raw)
            if not lpono_is_valid(lpo_no):
                lpo_no = None

        err = st._save_receipt(
            rn,
            receipt_date,
            supplier_code,
            invoice_no,
            invoice_date,
            discount,
            invoice_amount,
            remarks,
            lpo_no,
            lines,
            save_mode="grn_only",
            approve_mode="grn_only",
            invoice_snapshot_json=None,
            warehouse_id=warehouse_id,
            header_other_charge=0,
            post_inventory=True,
        )
        if err:
            raise ValueError(str(err))
        return {
            "receipt_no": str(rn),
            "posted": True,
            "inventory_posted": True,
            "account_posted": False,
            "message": "Stock and item journal updated.",
        }


def post_accounts(receipt_no: Any) -> dict[str, Any]:
    """Post purchase invoice / AP for a stock-posted GRN (ERP PI post)."""
    from db import parse_receiptno_from_request, receiptno_is_valid

    with mobile_operation_lock(
        "grn_accounts",
        str(receipt_no or "").strip(),
        lock_seconds=180.0,
        busy_message="GRN accounts posting is already in progress. Please wait.",
    ), _erp_session_scope():
        st = _purchase_st()
        st._apply_db()
        rn = parse_receiptno_from_request(receipt_no)
        if not receiptno_is_valid(rn):
            raise ValueError("Receipt number is required")
        if not st._get_receipt_header_for_posting(rn):
            raise ValueError("GRN not found")
        if st._grn_is_account_posted(rn):
            raise ValueError("This GRN is already posted to accounts.")
        if not st._grn_is_inventory_posted(rn):
            raise ValueError("Post stock first, then post accounts.")

        err = st._post_grn_from_saved_receipt(rn, force_posting=True)
        if err:
            raise ValueError(str(err))
        return {
            "receipt_no": str(rn),
            "inventory_posted": True,
            "account_posted": True,
            "message": f"Accounts posted for GRN {rn}.",
        }


def build_receipt_pdf(receipt_no: Any) -> tuple[bytes, str]:
    """ERP GRN PDF (same ReportLab layout as desktop receipt print)."""
    from db import coerce_receiptno, parse_receiptno_from_request, receiptno_is_valid

    with _erp_session_scope():
        st = _purchase_st()
        st._apply_db()
        rn = parse_receiptno_from_request(receipt_no)
        if not receiptno_is_valid(rn):
            raise ValueError("Invalid GRN number.")
        pdf_bytes, err = st._build_grn_pdf_bytes(rn)
        if err or not pdf_bytes:
            raise ValueError(str(err or "Failed to generate GRN PDF."))
        safe = str(coerce_receiptno(rn) or rn).replace("/", "-").replace("\\", "-")
        return pdf_bytes, f"GRN_{safe}.pdf"
