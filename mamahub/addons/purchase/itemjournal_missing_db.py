"""Scan posted transactions for item journal lines that were never inserted."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from db import (
    _detect_column,
    _detect_table,
    _get_connection,
    _journal_average_cost_for_line,
    _journal_row_exists_any,
    _sql_ident_col,
    _table_exists,
    _vat_percent_for_item,
    item_lot_id_for_batch_at_location_cur,
    receiptdtl_warehouse_code_column,
)


def _matches_missing_filters(
    row: Dict[str, Any],
    *,
    transtype_filter: Optional[str] = None,
    search: Optional[str] = None,
    item_code: Optional[str] = None,
) -> bool:
    item_code_f = str(item_code or '').strip().upper()
    if item_code_f:
        if str(row.get('itemcode') or '').strip().upper() != item_code_f:
            return False
    tt_f = str(transtype_filter or '').strip()
    if tt_f:
        disp = str(row.get('transtype') or '').strip() or '(none)'
        if disp != tt_f:
            return False
    s = str(search or '').strip().upper()
    if not s:
        return True
    hay = ' '.join(
        str(row.get(k) or '')
        for k in (
            'itemcode', 'source_no', 'source_doc', 'transtype',
            'warehouse_code', 'receiptno',
        )
    ).upper()
    return s in hay


def scan_missing_itemjournal_lines(
    *,
    location_code: int,
    limit: int = 800,
    transtype_filter: Optional[str] = None,
    search: Optional[str] = None,
    item_code: Optional[str] = None,
    include_grn: bool = True,
    include_sales: bool = True,
    include_purchase_return: bool = True,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    """
    Compare posted GRN / sales / purchase-return lines against item journal tables.

    Returns (display_rows, trans_type_summary, list_totals) where summary counts all
    missing lines by TRANSTYPE and list_totals reflects the active filters.
    """
    cap = max(1, min(int(limit or 800), 2000))
    by_tt: Dict[str, int] = defaultdict(int)
    display_rows: List[Dict[str, Any]] = []
    filtered_count = 0
    filtered_qty = 0.0
    filtered_amount = 0.0
    avg_cache: Dict[int, float] = {}

    def _consider(row: Dict[str, Any]) -> None:
        nonlocal filtered_count, filtered_qty, filtered_amount
        tt = str(row.get('transtype') or '').strip() or '(none)'
        by_tt[tt] += 1
        if not _matches_missing_filters(
            row,
            transtype_filter=transtype_filter,
            search=search,
            item_code=item_code,
        ):
            return
        filtered_count += 1
        filtered_qty += float(row.get('qty') or 0)
        filtered_amount += float(row.get('amount') or 0)
        if len(display_rows) < cap:
            display_rows.append(row)

    conn = _get_connection()
    with conn.cursor() as cur:
        if include_grn:
            _scan_missing_grn(cur, conn, location_code, avg_cache, _consider)
        if include_sales:
            _scan_missing_sales(cur, conn, location_code, avg_cache, _consider)
        if include_purchase_return:
            _scan_missing_purchase_return(cur, conn, location_code, avg_cache, _consider)

    summary = [
        {'transtype': tt, 'line_count': cnt}
        for tt, cnt in sorted(by_tt.items(), key=lambda x: x[0])
    ]
    list_totals = {
        'line_count': filtered_count,
        'total_qty': round(filtered_qty, 4),
        'total_amount': round(filtered_amount, 4),
    }
    return display_rows, summary, list_totals


def _scan_missing_grn(
    cur: Any,
    conn: Any,
    location_code: int,
    avg_cache: Dict[int, float],
    consider,
) -> None:
    rh = _detect_table(['RECEIPTHDR', 'receipthdr'])
    rd = _detect_table(['RECEIPTDTL', 'receiptdtl'])
    if not rh or not rd or not _table_exists('TBLGRNPOSTINGHDR'):
        return
    h_loc = _sql_ident_col(_detect_column(rh, ['LOCATIONCODE', 'locationcode']))
    h_reset = _sql_ident_col(_detect_column(rh, ['RESETNO', 'resetno']))
    h_no = _sql_ident_col(_detect_column(rh, ['RECEIPTNO', 'receiptno']))
    d_loc = _sql_ident_col(_detect_column(rd, ['LOCATIONCODE', 'locationcode']))
    d_reset = _sql_ident_col(_detect_column(rd, ['RESETNO', 'resetno']))
    d_no = _sql_ident_col(_detect_column(rd, ['RECEIPTNO', 'receiptno']))
    d_item = _sql_ident_col(_detect_column(rd, ['ITEMCODE', 'itemcode']))
    d_qty = _sql_ident_col(_detect_column(rd, ['QUANTITY', 'quantity']))
    d_rcv = _sql_ident_col(_detect_column(rd, ['RECEIVEDQTY', 'receivedqty']))
    d_rate = _sql_ident_col(_detect_column(rd, ['RATE', 'rate']))
    d_uom = _sql_ident_col(_detect_column(rd, ['UNITOFMEASUREMENT', 'UOM', 'unitofmeasurement', 'uom']))
    d_amt = _sql_ident_col(_detect_column(rd, ['AMOUNT', 'amount']))
    d_disc = _sql_ident_col(_detect_column(rd, ['DISCOUNT', 'discount']))
    d_base = _sql_ident_col(_detect_column(rd, ['BASEQTY', 'baseqty']))
    d_inv = _sql_ident_col(receiptdtl_warehouse_code_column(rd))
    d_wh = _sql_ident_col(_detect_column(rd, ['WAREHOUSE_ID', 'warehouse_id']))
    d_batch = _sql_ident_col(_detect_column(rd, ['BATCH_NO', 'BATCHNO', 'batch_no']))
    d_expiry = _sql_ident_col(_detect_column(rd, ['EXPIRY_DATE', 'EXPIRYDATE', 'expiry_date']))
    d_sl = _sql_ident_col(_detect_column(rd, ['SLNO', 'slno', 'LINENO', 'lineno']))
    if not (h_loc and h_no and d_no and d_item):
        return
    join_h = f'h.{h_no} = d.{d_no} AND h.{h_loc} = d.{d_loc}'
    if h_reset and d_reset:
        join_h += f' AND NVL(h.{h_reset},1) = NVL(d.{d_reset},1)'
    h_rn_expr = f'NVL(h.{h_reset},1)' if h_reset else '1'
    p_reset_match = f'p.RESETNO = NVL(h.{h_reset},1)' if h_reset else 'p.RESETNO = 1'
    sql_rc = (
        f'SELECT DISTINCT h.{h_loc} AS lc, {h_rn_expr} AS rn, h.{h_no} AS rno '
        f'FROM {rh} h INNER JOIN {rd} d ON {join_h} '
        f'INNER JOIN TBLGRNPOSTINGHDR p ON p.LOCATIONCODE = h.{h_loc} '
        f'AND {p_reset_match} AND p.RECEIPTNO = h.{h_no} '
        f'WHERE h.{h_loc} = :lc'
    )
    cur.execute(sql_rc, {'lc': int(location_code)})
    for lc, rn, rno in cur.fetchall() or []:
        try:
            loc_i = int(lc)
            reset_i = int(rn or 1)
            rno_i = int(rno)
        except (TypeError, ValueError):
            continue
        ln_sel = f'NVL(d.{d_sl}, ROW_NUMBER() OVER (ORDER BY d.ROWID))' if d_sl else 'ROW_NUMBER() OVER (ORDER BY d.ROWID)'
        if d_rcv and d_qty:
            qty_sel = f'NVL(d.{d_rcv}, NVL(d.{d_qty},0))'
        elif d_rcv:
            qty_sel = f'NVL(d.{d_rcv}, 0)'
        elif d_qty:
            qty_sel = f'NVL(d.{d_qty}, 0)'
        else:
            qty_sel = '0'
        inv_sel = f"NVL(TRIM(d.{d_inv}), '')" if d_inv else "''"
        amt_sel = f'NVL(d.{d_amt}, 0)' if d_amt else '0'
        disc_sel = f'NVL(d.{d_disc}, 0)' if d_disc else '0'
        base_sel = f'NVL(d.{d_base}, 0)' if d_base else '0'
        uom_sel = f"NVL(d.{d_uom}, 'NOS')" if d_uom else "'NOS'"
        rate_sel = f'NVL(d.{d_rate},0)' if d_rate else '0'
        wh_sel = f'd.{d_wh}' if d_wh else 'NULL'
        bn_sel = f'd.{d_batch}' if d_batch else 'NULL'
        exp_sel = f'd.{d_expiry}' if d_expiry else 'NULL'
        line_sql = (
            f'SELECT {ln_sel} AS ln, d.{d_item} AS itemcode, {qty_sel} AS qty, {rate_sel} AS rate, '
            f'{uom_sel} AS uom, {amt_sel} AS amount, {disc_sel} AS discount, {base_sel} AS baseqty, '
            f'{inv_sel} AS invloc, {wh_sel} AS warehouse_id, {bn_sel} AS batch_no, {exp_sel} AS expiry_date '
            f'FROM {rd} d WHERE d.{d_no} = :rno AND d.{d_loc} = :loc '
            + (f' AND NVL(d.{d_reset},1) = :rn ' if d_reset else '')
        )
        lp = {'rno': rno_i, 'loc': loc_i, 'rn': reset_i} if d_reset else {'rno': rno_i, 'loc': loc_i}
        cur.execute(line_sql, lp)
        for row in cur.fetchall() or []:
            if len(row) >= 13:
                ln, icode, qty, rate, uom, amt, disc, baseqty, invloc, wh_id, batch_no, expiry_date = row[:13]
            elif len(row) >= 10:
                ln, icode, qty, rate, uom, amt, disc, baseqty, invloc, wh_id = row[:10]
                batch_no, expiry_date = None, None
            else:
                ln, icode, qty, rate, uom, amt, disc, baseqty, invloc = row[:9]
                wh_id, batch_no, expiry_date = None, None, None
            try:
                lineno = int(ln or 0)
                item_int = int(icode)
            except (TypeError, ValueError):
                continue
            if lineno <= 0:
                continue
            if _journal_row_exists_any(cur, conn, loc_i, reset_i, rno_i, lineno, 'GRN', str(rno_i)):
                continue
            qty_f = abs(float(qty or 0))
            rate_f = float(rate or 0)
            disc_f = float(disc or 0)
            base_f = abs(float(baseqty or 0))
            if base_f <= 0 and qty_f > 0:
                base_f = qty_f
            if d_amt and amt is not None:
                amt_f = float(amt or 0)
            else:
                amt_f = max(0.0, qty_f * rate_f - disc_f)
            avg_f = _journal_average_cost_for_line(cur, loc_i, {'item': item_int}, item_cache=avg_cache)
            consider({
                'locationcode': loc_i,
                'resetno': reset_i,
                'receiptno': rno_i,
                'lineno': lineno,
                'itemcode': item_int,
                'itemname': '',
                'uom': str(uom or 'NOS'),
                'qty': round(base_f, 3),
                'rate': rate_f,
                'averagecost': round(avg_f, 4) if avg_f > 0 else 0.0,
                'amount': round(amt_f, 3),
                'warehouse_code': str(invloc or '').strip() or None,
                'warehouse_id': wh_id,
                'batch_no': str(batch_no or '').strip() or None,
                'expiry_date': expiry_date,
                'lot_id': item_lot_id_for_batch_at_location_cur(
                    cur, loc_i, item_int, str(batch_no or '').strip() or None,
                ),
                'storage_id': None,
                'transtype': 'PURCHASE',
                'source_doc': 'GRN',
                'source_no': str(rno_i),
                'createddate': None,
                'cust_supplier': None,
            })


def _scan_missing_sales(
    cur: Any,
    conn: Any,
    location_code: int,
    avg_cache: Dict[int, float],
    consider,
) -> None:
    bh = _detect_table(['BILLHDR', 'billhdr'])
    bd = _detect_table(['BILLDTL', 'billdtl'])
    if not bh or not bd:
        return
    b_loc = _sql_ident_col(_detect_column(bh, ['LOCATIONCODE', 'locationcode']))
    b_reset = _sql_ident_col(_detect_column(bh, ['RESETNO', 'resetno']))
    b_no = _sql_ident_col(_detect_column(bh, ['BILLNO', 'billno']))
    b_type = _sql_ident_col(_detect_column(bh, ['BILLTYPE', 'billtype']))
    b_del = _sql_ident_col(_detect_column(bh, ['DELFLAG', 'delflag']))
    d_loc = _sql_ident_col(_detect_column(bd, ['LOCATIONCODE', 'locationcode']))
    d_reset = _sql_ident_col(_detect_column(bd, ['RESETNO', 'resetno']))
    d_no = _sql_ident_col(_detect_column(bd, ['BILLNO', 'billno']))
    d_sl = _sql_ident_col(_detect_column(bd, ['SLNO', 'slno', 'LINENO', 'lineno']))
    d_item = _sql_ident_col(_detect_column(bd, ['ITEMCODE', 'itemcode']))
    d_qty = _sql_ident_col(_detect_column(bd, ['QUANTITY', 'quantity']))
    d_rate = _sql_ident_col(_detect_column(bd, ['RATE', 'rate']))
    d_uom = _sql_ident_col(_detect_column(bd, ['UNITOFMEASUREMENT', 'UOM', 'unitofmeasurement', 'uom']))
    d_disc = _sql_ident_col(_detect_column(bd, ['ITDISC', 'itdisc', 'DISCOUNT', 'discount']))
    d_base = _sql_ident_col(_detect_column(bd, ['BASEQTY', 'baseqty']))
    d_store = _sql_ident_col(_detect_column(bd, ['STORE', 'store']))
    d_vatp = _sql_ident_col(_detect_column(bd, ['VATPERCENT', 'vatpercent']))
    d_vatamt = _sql_ident_col(_detect_column(bd, ['VATAMOUNT', 'vatamount']))
    if not (b_loc and b_no and d_no and d_item):
        return
    join_b = f'h.{b_no} = d.{d_no} AND h.{b_loc} = d.{d_loc}'
    if b_reset and d_reset:
        join_b += f' AND NVL(h.{b_reset},1) = NVL(d.{d_reset},1)'
    b_rn_expr = f'NVL(h.{b_reset},1)' if b_reset else '1'
    wh = [f"NVL(h.{b_del}, 'N') <> 'Y'" if b_del else '1=1', f'h.{b_loc} = :lc']
    if b_type:
        sql_b = (
            f"SELECT h.{b_loc} AS lc, {b_rn_expr} AS rn, h.{b_no} AS bno, "
            f"CASE WHEN UPPER(NVL(h.{b_type},'C')) LIKE 'R%' THEN 1 ELSE 0 END AS is_ret "
            f"FROM {bh} h INNER JOIN {bd} d ON {join_b} WHERE {' AND '.join(wh)} "
            f"GROUP BY h.{b_loc}, {b_rn_expr}, h.{b_no}, "
            f"CASE WHEN UPPER(NVL(h.{b_type},'C')) LIKE 'R%' THEN 1 ELSE 0 END"
        )
    else:
        sql_b = (
            f"SELECT h.{b_loc} AS lc, {b_rn_expr} AS rn, h.{b_no} AS bno, 0 AS is_ret "
            f"FROM {bh} h INNER JOIN {bd} d ON {join_b} WHERE {' AND '.join(wh)} "
            f"GROUP BY h.{b_loc}, {b_rn_expr}, h.{b_no}"
        )
    cur.execute(sql_b, {'lc': int(location_code)})
    for bill_row in cur.fetchall() or []:
        if len(bill_row) >= 4:
            lc, rn, bno, is_ret = bill_row[0], bill_row[1], bill_row[2], int(bill_row[3] or 0)
        else:
            lc, rn, bno, is_ret = bill_row[0], bill_row[1], bill_row[2], 0
        try:
            loc_i = int(lc)
            reset_i = int(rn or 1)
            bno_i = int(bno)
        except (TypeError, ValueError):
            continue
        ln_b = f'NVL(d.{d_sl}, ROW_NUMBER() OVER (ORDER BY d.ROWID))' if d_sl else 'ROW_NUMBER() OVER (ORDER BY d.ROWID)'
        st_sel = f"NVL(TRIM(d.{d_store}),'')" if d_store else "''"
        if d_vatp and d_vatamt:
            vat_sel = f', NVL(d.{d_vatp},0) AS vatp, NVL(d.{d_vatamt},0) AS vatamt'
        elif d_vatp:
            vat_sel = f', NVL(d.{d_vatp},0) AS vatp, 0 AS vatamt'
        elif d_vatamt:
            vat_sel = f', 0 AS vatp, NVL(d.{d_vatamt},0) AS vatamt'
        else:
            vat_sel = ', 0 AS vatp, 0 AS vatamt'
        b_qty = f'NVL(d.{d_qty},0)' if d_qty else '0'
        b_rate = f'NVL(d.{d_rate},0)' if d_rate else '0'
        b_uom = f"NVL(d.{d_uom},'NOS')" if d_uom else "'NOS'"
        b_disc = f'NVL(d.{d_disc},0)' if d_disc else '0'
        if d_base and d_qty:
            b_base = f'NVL(d.{d_base}, NVL(d.{d_qty},0))'
        elif d_base:
            b_base = f'NVL(d.{d_base}, 0)'
        elif d_qty:
            b_base = f'NVL(d.{d_qty}, 0)'
        else:
            b_base = '0'
        line_sql = (
            f'SELECT {ln_b} AS ln, d.{d_item} AS itemcode, {b_qty} AS qty, {b_rate} AS rate, '
            f'{b_uom} AS uom, {b_disc} AS disc, {b_base} AS baseqty, {st_sel} AS st {vat_sel} '
            f'FROM {bd} d WHERE d.{d_no} = :bno AND d.{d_loc} = :loc '
            + (f' AND NVL(d.{d_reset},1) = :rn ' if d_reset else '')
        )
        lpb = {'bno': bno_i, 'loc': loc_i, 'rn': reset_i} if d_reset else {'bno': bno_i, 'loc': loc_i}
        cur.execute(line_sql, lpb)
        for row in cur.fetchall() or []:
            if len(row) >= 10:
                ln, icode, qty, rate, uom, disc, baseqty, st, vatp_l, vatamt_l = row[:10]
            else:
                ln, icode, qty, rate, uom, disc, baseqty, st = row[:8]
                vatp_l, vatamt_l = 0.0, 0.0
            try:
                lineno = int(ln or 0)
                item_int = int(icode)
            except (TypeError, ValueError):
                continue
            if lineno <= 0:
                continue
            src_doc = 'BILL RETURN' if is_ret else 'BILL'
            ttype = 'SALES RETURN' if is_ret else 'SALES'
            if _journal_row_exists_any(cur, conn, loc_i, reset_i, bno_i, lineno, src_doc, str(bno_i)):
                continue
            qty_f = float(qty or 0)
            rate_f = float(rate or 0)
            disc_f = float(disc or 0)
            base_f = abs(float(baseqty or 0))
            amt_f = max(0.0, abs(qty_f) * rate_f - disc_f)
            vatp = float(vatp_l or 0) if d_vatp else _vat_percent_for_item(cur, loc_i, item_int)
            if len(row) >= 10 and d_vatamt:
                vat_amt = float(vatamt_l or 0)
            else:
                vat_amt = round(amt_f * vatp / 100.0, 3)
            qty_out = round(abs(base_f) if is_ret else -abs(base_f), 3) if base_f else 0.0
            amount_val = round(amt_f if is_ret else -amt_f, 3)
            avg_f = _journal_average_cost_for_line(cur, loc_i, {'item': item_int}, item_cache=avg_cache)
            consider({
                'locationcode': loc_i,
                'resetno': reset_i,
                'receiptno': bno_i,
                'lineno': lineno,
                'itemcode': item_int,
                'itemname': '',
                'uom': str(uom or 'NOS'),
                'qty': qty_out,
                'rate': rate_f,
                'averagecost': round(avg_f, 4) if avg_f > 0 else 0.0,
                'amount': amount_val,
                'warehouse_code': str(st or '').strip() or None,
                'warehouse_id': None,
                'batch_no': None,
                'expiry_date': None,
                'lot_id': None,
                'storage_id': None,
                'transtype': ttype,
                'source_doc': src_doc,
                'source_no': str(bno_i),
                'createddate': None,
                'cust_supplier': None,
            })


def _scan_missing_purchase_return(
    cur: Any,
    conn: Any,
    location_code: int,
    avg_cache: Dict[int, float],
    consider,
) -> None:
    rth = _detect_table(['RETURNHDR', 'returnhdr'])
    rtd = _detect_table(['RETURNDTL', 'returndtl'])
    if not rth or not rtd or not _table_exists('TBLPRPOSTINGHDR'):
        return
    h_loc = _sql_ident_col(_detect_column(rth, ['LOCATIONCODE', 'locationcode']))
    h_reset = _sql_ident_col(_detect_column(rth, ['RESETNO', 'resetno']))
    h_no = _sql_ident_col(_detect_column(rth, ['GOODSRETURNNO', 'goodsreturnno']))
    h_type = _sql_ident_col(_detect_column(rth, ['RETURNTYPE', 'returntype']))
    d_loc = _sql_ident_col(_detect_column(rtd, ['LOCATIONCODE', 'locationcode']))
    d_reset = _sql_ident_col(_detect_column(rtd, ['RESETNO', 'resetno']))
    d_no = _sql_ident_col(_detect_column(rtd, ['GOODSRETURNNO', 'goodsreturnno']))
    d_item = _sql_ident_col(_detect_column(rtd, ['ITEMCODE', 'itemcode']))
    d_qty = _sql_ident_col(_detect_column(rtd, ['QUANTITY', 'quantity']))
    d_rate = _sql_ident_col(_detect_column(rtd, ['RATE', 'rate']))
    d_uom = _sql_ident_col(_detect_column(rtd, ['UOM', 'uom']))
    d_disc = _sql_ident_col(_detect_column(rtd, ['DISCOUNT', 'discount']))
    d_conv = _sql_ident_col(_detect_column(rtd, ['CONVERSIONFACTOR', 'UOMFACTOR', 'conversionfactor']))
    d_store = _sql_ident_col(_detect_column(rtd, ['STORE', 'store']))
    d_sl = _sql_ident_col(_detect_column(rtd, ['SLNO', 'slno', 'LINENO', 'lineno']))
    if not (h_loc and h_no and d_no and d_item):
        return
    join_h = f'h.{h_no} = d.{d_no} AND h.{h_loc} = d.{d_loc}'
    if h_reset and d_reset:
        join_h += f' AND NVL(h.{h_reset},1) = NVL(d.{d_reset},1)'
    type_filter = ''
    if h_type:
        type_filter = f" AND (UPPER(NVL(h.{h_type},' ')) LIKE '%P%' OR UPPER(NVL(h.{h_type},' ')) LIKE '%R%')"
    pr_rn_expr = f'NVL(h.{h_reset},1)' if h_reset else '1'
    pr_p_reset = f'p.RESETNO = NVL(h.{h_reset},1)' if h_reset else 'p.RESETNO = 1'
    sql_pr = (
        f'SELECT DISTINCT h.{h_loc} AS lc, {pr_rn_expr} AS rn, h.{h_no} AS grn '
        f'FROM {rth} h INNER JOIN {rtd} d ON {join_h} '
        f'INNER JOIN TBLPRPOSTINGHDR p ON p.LOCATIONCODE = h.{h_loc} '
        f'AND {pr_p_reset} AND p.GOODSRETURNNO = h.{h_no} '
        f'WHERE h.{h_loc} = :lc {type_filter}'
    )
    cur.execute(sql_pr, {'lc': int(location_code)})
    for lc, rn, grn in cur.fetchall() or []:
        try:
            loc_i = int(lc)
            reset_i = int(rn or 1)
            grn_i = int(grn)
        except (TypeError, ValueError):
            continue
        pr_ln = f'NVL(d.{d_sl}, ROW_NUMBER() OVER (ORDER BY d.ROWID))' if d_sl else 'ROW_NUMBER() OVER (ORDER BY d.ROWID)'
        pr_cf = f'NVL(d.{d_conv},0)' if d_conv else '0'
        pr_st = f"NVL(TRIM(d.{d_store}),'')" if d_store else "''"
        pr_disc = f'NVL(d.{d_disc},0)' if d_disc else '0'
        pr_uom = f"NVL(d.{d_uom},'NOS')" if d_uom else "'NOS'"
        pr_rate = f'NVL(d.{d_rate},0)' if d_rate else '0'
        pr_qty = f'NVL(d.{d_qty},0)' if d_qty else '0'
        line_sql = (
            f'SELECT {pr_ln} AS ln, d.{d_item} AS itemcode, {pr_qty} AS qty, {pr_rate} AS rate, '
            f'{pr_uom} AS uom, {pr_disc} AS disc, {pr_cf} AS cf, {pr_st} AS st '
            f'FROM {rtd} d WHERE d.{d_no} = :g AND d.{d_loc} = :loc '
            + (f' AND NVL(d.{d_reset},1) = :rn ' if d_reset else '')
        )
        lpp = {'g': grn_i, 'loc': loc_i, 'rn': reset_i} if d_reset else {'g': grn_i, 'loc': loc_i}
        cur.execute(line_sql, lpp)
        for row in cur.fetchall() or []:
            ln, icode, qty, rate, uom, disc, cf, st = row
            try:
                lineno = int(ln or 0)
                item_int = int(icode)
            except (TypeError, ValueError):
                continue
            if lineno <= 0:
                continue
            if _journal_row_exists_any(cur, conn, loc_i, reset_i, grn_i, lineno, 'RETURN', str(grn_i)):
                continue
            qty_f = abs(float(qty or 0))
            rate_f = float(rate or 0)
            disc_f = float(disc or 0)
            cf_f = float(cf or 0)
            if cf_f <= 0:
                cf_f = 1.0
            qty_out_base = -abs(qty_f * cf_f)
            amt_out = -max(0.0, qty_f * rate_f - disc_f)
            avg_f = _journal_average_cost_for_line(cur, loc_i, {'item': item_int}, item_cache=avg_cache)
            consider({
                'locationcode': loc_i,
                'resetno': reset_i,
                'receiptno': grn_i,
                'lineno': lineno,
                'itemcode': item_int,
                'itemname': '',
                'uom': str(uom or 'NOS'),
                'qty': round(qty_out_base, 3),
                'rate': rate_f,
                'averagecost': round(avg_f, 4) if avg_f > 0 else 0.0,
                'amount': round(amt_out, 3),
                'warehouse_code': str(st or '').strip() or None,
                'warehouse_id': None,
                'batch_no': None,
                'expiry_date': None,
                'lot_id': None,
                'storage_id': None,
                'transtype': 'PURCHASE_RETURN',
                'source_doc': 'RETURN',
                'source_no': str(grn_i),
                'createddate': None,
                'cust_supplier': None,
            })
