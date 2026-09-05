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
        from mobile_backend.services.doc_peek import fresh_doc_no

        lpono = fresh_doc_no(
            peek_fn=p._lpo_next_no,
            exists_fn=lambda n: bool(p._lpo_no_exists_in_hdr(n) or p._get_lpo_header(n)),
            allocate_fn=lambda n: p._allocate_next_free_lpo_no(n),
        )
        # Must use Transaction Date Setup open date (not calendar today).
        txn = p._purchase_txn_date_context("purchase")
        open_date = str(
            txn.get("open_transaction_date")
            or p._purchase_open_transaction_date("purchase")
            or ""
        ).strip()[:10]
        if not open_date:
            from mobile_backend.services.transaction_date_helper import missing_setup_date_message

            raise ValueError(
                txn.get("transaction_date_error")
                or missing_setup_date_message("purchase")
            )
        wh_enabled = bool(p._po_warehouse_enabled())
        wh_rows = p._get_lpo_warehouse_picker_rows(doc_kind="purchase") if wh_enabled else []
        # Auto-select only when exactly one warehouse is available.
        default_wh = wh_rows[0] if len(wh_rows) == 1 else {}
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

    Alternate UOMs are chosen after tap via ``list_item_uoms``.
    When ``supplier_code`` is set, filters to that supplier's items (ITEMMASTER SUPCODE) —
    same as ERP PO/GRN ``supplier_items_only`` tab.
    """
    lim = max(1, min(int(limit or 60), 200))
    try:
        sup_i = int(float(str(supplier_code or "").strip() or "0"))
    except (TypeError, ValueError):
        sup_i = 0
    with _erp_session_scope():
        p = _purchase()
        p._apply_db()
        rows = p._get_items_for_location_filtered(
            search=(search or "").strip() or None,
            limit=lim,
            supplier_code=sup_i if sup_i > 0 else None,
        ) or []
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for r in rows:
            code = str(r.get("code") or r.get("itemcode") or "").strip()
            if not code or code in seen:
                continue
            seen.add(code)
            avg = _to_float(r.get("averagecost") or r.get("AVERAGECOST"))
            cprice = _to_float(r.get("costprice") or r.get("COSTPRICE"))
            cost = _to_float(r.get("cost") or r.get("costprice") or r.get("rate"))
            if avg <= 0:
                avg = cost
            if cprice <= 0:
                cprice = cost if cost > 0 else avg
            # Default add rate = cost price.
            rate = cprice if cprice > 0 else avg
            out.append(
                {
                    "item_code": code,
                    "item_name": str(r.get("name") or r.get("itemname") or "").strip(),
                    "uom": str(r.get("uom") or "NOS").strip() or "NOS",
                    "rate": rate,
                    "average_cost": avg,
                    "cost_price": cprice,
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


def list_supplier_items(
    *,
    supplier_code: str,
    search: str = "",
    limit: int = 80,
    days: int = 365,
) -> list[dict[str, Any]]:
    """Items for the Supplier items tab (Sales Customer items counterpart).

    Prefers items previously purchased from the supplier (GRN RECEIPT*), then
    fills with ITEMMASTER rows linked to the supplier (ERP SUPCODE filter).
    """
    from db.oracle_driver import cx_Oracle

    from mobile_backend.database.oracle_pool import get_connection
    from mobile_backend.request_context import get_jwt
    from mobile_backend.services.inventory_service import _pick_existing
    from mobile_backend.services.sales_service import _table_columns

    try:
        sup_i = int(float(str(supplier_code or "").strip() or "0"))
    except (TypeError, ValueError):
        sup_i = 0
    if sup_i <= 0:
        return []

    lim = max(1, min(int(limit or 80), 200))
    day_span = max(30, min(int(days or 365), 730))
    q = (search or "").strip().lower()
    claims = get_jwt()
    tenant_id = claims.get("tenant_id")
    aggregated: dict[str, dict[str, Any]] = {}

    with _erp_session_scope():
        p = _purchase()
        p._apply_db()
        loc = int(p._resolve_location_code() or 0)

        # 1) Previous GRN lines for this supplier (newest first).
        conn = get_connection(tenant_id=tenant_id)
        with conn.cursor() as cur:
            hdr = "RECEIPTHDR" if _table_columns(cur, "RECEIPTHDR") else ""
            dtl = "RECEIPTDTL" if _table_columns(cur, "RECEIPTDTL") else ""
            if hdr and dtl:
                hdr_cols = _table_columns(cur, hdr)
                dtl_cols = _table_columns(cur, dtl)
                rno_h = _pick_existing(hdr_cols, ["RECEIPTNO", "RECEIPT_NO", "GRNNO", "GRN_NO"])
                rno_d = _pick_existing(dtl_cols, ["RECEIPTNO", "RECEIPT_NO", "GRNNO", "GRN_NO"])
                date_col = _pick_existing(
                    hdr_cols, ["RECEIPTDATE", "RECEIPT_DATE", "GRNDATE", "TRNDATE", "INVOICEDATE"]
                )
                sup_col = _pick_existing(hdr_cols, ["SUPPLIERCODE", "SUPPLIER_CODE", "SUPCODE"])
                loc_h = _pick_existing(hdr_cols, ["LOCATIONCODE", "LOCATION_CODE"])
                loc_d = _pick_existing(dtl_cols, ["LOCATIONCODE", "LOCATION_CODE"])
                item_col = _pick_existing(dtl_cols, ["ITEMCODE", "ITEM_CODE", "CODE"])
                qty_col = _pick_existing(dtl_cols, ["QUANTITY", "QTY", "RECEIPTQTY"])
                rate_col = _pick_existing(dtl_cols, ["RATE", "COSTPRICE", "COST", "UNITPRICE"])
                uom_col = _pick_existing(
                    dtl_cols, ["UNITOFMEASUREMENT", "UOM", "UOMCODE", "UNIT"]
                )
                if rno_h and rno_d and date_col and sup_col and item_col and qty_col:
                    join = [f"d.{rno_d} = h.{rno_h}"]
                    if loc_h and loc_d:
                        join.append(f"d.{loc_d} = h.{loc_h}")
                    where = [
                        f"h.{sup_col} = :sup",
                        f"NVL(d.{qty_col}, 0) > 0",
                        f"TRUNC(h.{date_col}) >= TRUNC(SYSDATE) - :days + 1",
                    ]
                    params: dict[str, Any] = {"sup": sup_i, "days": day_span, "lim": lim * 8}
                    if loc_h and loc:
                        where.append(f"h.{loc_h} = :loc")
                        params["loc"] = loc
                    elif loc_d and loc:
                        where.append(f"d.{loc_d} = :loc")
                        params["loc"] = loc

                    item_cols = _table_columns(cur, "ITEMMASTER")
                    ic = _pick_existing(item_cols, ["ITEMCODE", "ITEM_CODE"]) if item_cols else None
                    name_col = (
                        _pick_existing(item_cols, ["ITEMNAME", "ITEMDESC", "ITEM_NAME", "NAME"])
                        if item_cols
                        else None
                    )
                    cost_col = (
                        _pick_existing(item_cols, ["COSTPRICE", "COST_PRICE", "COST"])
                        if item_cols
                        else None
                    )
                    avg_col = (
                        _pick_existing(
                            item_cols, ["AVERAGECOST", "AVERAGE_COST", "AVGCOST", "avgcost"]
                        )
                        if item_cols
                        else None
                    )
                    base_uom_col = (
                        _pick_existing(item_cols, ["BASEUOM", "BASE_UOM", "UOM"]) if item_cols else None
                    )
                    barcode_col = (
                        _pick_existing(item_cols, ["MANUFACTURERID", "BARCODE", "MFRID"])
                        if item_cols
                        else None
                    )
                    if item_cols and ic and name_col:
                        name_expr = f"NVL(i.{name_col}, TO_CHAR(d.{item_col}))"
                        join_item = f"LEFT JOIN itemmaster i ON i.{ic} = d.{item_col}"
                        loc_i = _pick_existing(item_cols, ["LOCATIONCODE", "LOCATION_CODE"])
                        if loc and loc_i:
                            join_item += f" AND i.{loc_i} = :iloc"
                            params["iloc"] = loc
                        if avg_col:
                            avg_expr = f"NVL(i.{avg_col}, 0)"
                        else:
                            avg_expr = "0"
                        if cost_col:
                            cprice_expr = f"NVL(i.{cost_col}, 0)"
                        else:
                            cprice_expr = "0"
                        unit_fb = f"NVL(i.{base_uom_col}, 'NOS')" if base_uom_col else "'NOS'"
                        bc_expr = f"NVL(i.{barcode_col}, '')" if barcode_col else "''"
                    else:
                        name_expr = f"TO_CHAR(d.{item_col})"
                        join_item = ""
                        avg_expr = "0"
                        cprice_expr = "0"
                        unit_fb = "'NOS'"
                        bc_expr = "''"
                    uom_expr = (
                        f"NVL(NULLIF(TRIM(d.{uom_col}), ''), {unit_fb})" if uom_col else unit_fb
                    )
                    rate_expr = f"NVL(d.{rate_col}, 0)" if rate_col else "0"
                    qty_expr = f"NVL(d.{qty_col}, 0)"
                    sql = f"""
                        SELECT * FROM (
                            SELECT d.{item_col} AS item_code,
                                   {name_expr} AS item_name,
                                   {uom_expr} AS uom,
                                   {qty_expr} AS last_qty,
                                   {rate_expr} AS last_rate,
                                   {avg_expr} AS avg_cost,
                                   {cprice_expr} AS cost_price,
                                   {bc_expr} AS barcode,
                                   TRUNC(h.{date_col}) AS receipt_date,
                                   h.{rno_h} AS receipt_no
                              FROM {dtl} d
                             INNER JOIN {hdr} h ON {" AND ".join(join)}
                              {join_item}
                             WHERE {" AND ".join(where)}
                             ORDER BY TRUNC(h.{date_col}) DESC, h.{rno_h} DESC
                        ) WHERE ROWNUM <= :lim
                    """
                    try:
                        cur.execute(sql, params)
                        rows = cur.fetchall() or []
                        cols = [d[0].lower() for d in cur.description or []]
                        for raw_row in rows:
                            raw = dict(zip(cols, raw_row))
                            code = str(raw.get("item_code") or "").strip()
                            if not code or code in aggregated:
                                continue
                            avg = _to_float(raw.get("avg_cost"))
                            cprice = _to_float(raw.get("cost_price"))
                            last_rate = _to_float(raw.get("last_rate"))
                            if avg <= 0:
                                avg = last_rate if last_rate > 0 else cprice
                            if cprice <= 0:
                                cprice = last_rate if last_rate > 0 else avg
                            # Default add rate = cost price.
                            rate = cprice if cprice > 0 else avg
                            receipt_date = raw.get("receipt_date")
                            if hasattr(receipt_date, "strftime"):
                                receipt_date_s = receipt_date.strftime("%Y-%m-%d")
                            else:
                                receipt_date_s = str(receipt_date or "")[:10]
                            aggregated[code] = {
                                "item_code": code,
                                "item_name": str(raw.get("item_name") or "").strip(),
                                "uom": str(raw.get("uom") or "NOS").strip() or "NOS",
                                "rate": rate,
                                "average_cost": avg,
                                "cost_price": cprice,
                                "barcode": str(raw.get("barcode") or "").strip(),
                                "current_stock": 0.0,
                                "last_qty": _to_float(raw.get("last_qty")),
                                "last_rate": last_rate,
                                "last_receiptdate": receipt_date_s,
                                "last_receiptno": str(raw.get("receipt_no") or "").strip(),
                            }
                    except cx_Oracle.DatabaseError:
                        pass

        # 2) ERP supplier-linked master items (SUPCODE) to fill gaps.
        if len(aggregated) < lim:
            master_rows = p._get_items_for_location_filtered(
                search=(search or "").strip() or None,
                limit=lim,
                supplier_code=sup_i,
            ) or []
            for r in master_rows:
                code = str(r.get("code") or r.get("itemcode") or "").strip()
                if not code or code in aggregated:
                    continue
                avg = _to_float(r.get("averagecost") or r.get("AVERAGECOST"))
                cprice = _to_float(r.get("costprice") or r.get("COSTPRICE"))
                cost = _to_float(r.get("cost") or r.get("costprice") or r.get("rate"))
                if avg <= 0:
                    avg = cost
                if cprice <= 0:
                    cprice = cost if cost > 0 else avg
                rate = cprice if cprice > 0 else avg
                aggregated[code] = {
                    "item_code": code,
                    "item_name": str(r.get("name") or r.get("itemname") or "").strip(),
                    "uom": str(r.get("uom") or "NOS").strip() or "NOS",
                    "rate": rate,
                    "average_cost": avg,
                    "cost_price": cprice,
                    "barcode": str(r.get("barcode") or "").strip(),
                    "current_stock": _to_float(
                        r.get("currentstock")
                        if r.get("currentstock") is not None
                        else r.get("CURRENTSTOCK") or r.get("stock")
                    ),
                    "last_qty": 0.0,
                    "last_rate": 0.0,
                    "last_receiptdate": "",
                    "last_receiptno": "",
                }
                if len(aggregated) >= lim:
                    break

        out = list(aggregated.values())
        out.sort(
            key=lambda r: (
                str(r.get("last_receiptdate") or ""),
                _to_float(r.get("last_qty")),
            ),
            reverse=True,
        )
        if q:
            out = [
                r
                for r in out
                if q in str(r.get("item_name") or "").lower()
                or q in str(r.get("item_code") or "").lower()
                or q in str(r.get("barcode") or "").lower()
            ]
        return out[:lim]


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

        from mobile_backend.services.transaction_date_helper import resolve_doc_date

        lpo_date = resolve_doc_date(
            "purchase",
            header.get("lpo_date") or header.get("lpodate"),
            snap_out_of_range=True,
        )

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
            from mobile_backend.services.uom_factor import apply_line_stock_base

            uom = str(ln.get("uom") or "NOS").strip() or "NOS"
            row: dict[str, Any] = {
                "itemcode": ic,
                "item_code": ic,
                "quantity": qty,
                "rate": rate,
                "discount": disc,
                "amount": amount,
                "uom": uom,
                "barcode": str(ln.get("barcode") or "").strip(),
                "warehouse_id": ln.get("warehouse_id") or warehouse_id,
                "factor": ln.get("factor") or ln.get("conversionfactor") or ln.get("conversion_factor"),
                "conversionfactor": ln.get("conversionfactor")
                or ln.get("conversion_factor")
                or ln.get("factor"),
            }
            apply_line_stock_base(row, item_code=ic, uom=uom, qty=qty, st=p)
            lines.append(row)
        if not lines:
            raise ValueError("Add at least one valid line item.")

        requested = lpo_no
        # Mobile New must not silently overwrite an existing PO when the peeked number
        # is already used (stuck series). Re-save/edit keeps the same LPO when header exists
        # and there is no GRN (blocked above).
        existing_hdr = p._get_lpo_header(lpo_no)
        if existing_hdr is None and p._lpo_no_exists_in_hdr(lpo_no):
            lpo_no = p._allocate_next_free_lpo_no(lpo_no)
            lpo_reassigned = True
        else:
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
