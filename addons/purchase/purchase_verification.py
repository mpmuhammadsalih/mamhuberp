"""Post-save verification for Goods Receipt (GRN) and Purchase Return documents."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from db import (
    ITEM_LOT_TABLE,
    STOCK_VERIFICATION_TOL,
    _detect_column,
    _detect_table,
    _fetch_rows,
    _table_exists,
    billno_numeric_part,
    coerce_goodsreturnno,
    coerce_receiptno,
    ensure_receiptdtl_previous_cost_columns,
    ensure_receiptdtl_foc_column,
    is_item_batch_tracked,
)

RESET_NO = 1
PV_TOL = STOCK_VERIFICATION_TOL


def _grn_posting_receiptno(receipt_no: Any) -> int:
    """Numeric RECEIPTNO for TBLGRNPOSTING / legacy NUMBER FK tables."""
    n = billno_numeric_part(receipt_no)
    if n > 0:
        return n
    try:
        return max(0, int(receipt_no or 0))
    except (TypeError, ValueError):
        return 0


def _doc_no_sort_key(val: Any) -> int:
    """Numeric sort key for GRN/PR document numbers (supports VARCHAR prefixes)."""
    n = billno_numeric_part(val)
    if n > 0:
        return n
    try:
        return int(val or 0)
    except (TypeError, ValueError):
        return 0


def _journal_source_no(val: Any) -> int:
    """ITEMJOURNAL.SOURCE_NO is stored as NUMBER — use numeric tail of formatted doc no."""
    return _doc_no_sort_key(val)


def _near(a: float, b: float, tol: float = PV_TOL) -> bool:
    return abs(float(a or 0) - float(b or 0)) <= tol


def _f(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _norm_foc(v: Any) -> bool:
    return v in (True, 1, '1', 'Y', 'y', 'TRUE', 'True')


def _status_from_issues(issues: List[Dict[str, Any]]) -> str:
    if any(i.get('severity') == 'err' for i in issues):
        return 'err'
    if any(i.get('severity') == 'warn' for i in issues):
        return 'warn'
    return 'ok'


def _issue(code: str, message: str, severity: str = 'err', **extra: Any) -> Dict[str, Any]:
    row: Dict[str, Any] = {'code': code, 'message': message, 'severity': severity}
    row.update(extra)
    return row


def _item_journal_tbl() -> Optional[str]:
    return _detect_table(['ITEMJOURNAL', 'itemjournal', 'ITEMJOURNEL', 'itemjournel'])


def _fetch_item_journal_for_doc(
    location_code: int,
    source_doc: str,
    source_no: Any,
) -> List[Dict[str, Any]]:
    tbl = _item_journal_tbl()
    if not tbl:
        return []
    loc_col = _detect_column(tbl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    reset_col = _detect_column(tbl, ['RESETNO', 'RESET_NO', 'resetno'])
    sd_col = _detect_column(tbl, ['SOURCE_DOC', 'SOURCEDOC', 'source_doc'])
    sn_col = _detect_column(tbl, ['SOURCE_NO', 'SOURCENO', 'source_no'])
    lineno_col = _detect_column(tbl, ['LINENO', 'LINE_NO', 'lineno'])
    item_col = _detect_column(tbl, ['ITEMCODE', 'ITEM_CODE', 'itemcode'])
    qty_col = _detect_column(tbl, ['QTY', 'QUANTITY', 'qty'])
    rate_col = _detect_column(tbl, ['RATE', 'rate'])
    amt_col = _detect_column(tbl, ['AMOUNT', 'amount'])
    uom_col = _detect_column(tbl, ['UOM', 'uom'])
    wh_col = _detect_column(tbl, ['WAREHOUSE_ID', 'warehouse_id'])
    stor_col = _detect_column(tbl, ['STORAGE_ID', 'storage_id'])
    lot_col = _detect_column(tbl, ['LOT_ID', 'LOTID', 'lot_id'])
    bn_col = _detect_column(tbl, ['BATCH_NO', 'BATCHNO', 'batch_no'])
    tt_col = _detect_column(tbl, ['TRANSTYPE', 'TRANS_TYPE', 'transtype'])
    if not item_col or not sd_col or not sn_col:
        return []
    cols = [
        f'{lineno_col} AS lineno' if lineno_col else 'NULL AS lineno',
        f'{item_col} AS itemcode',
        f'{qty_col} AS qty' if qty_col else '0 AS qty',
        f'{rate_col} AS rate' if rate_col else '0 AS rate',
        f'{amt_col} AS amount' if amt_col else '0 AS amount',
        f'{uom_col} AS uom' if uom_col else 'NULL AS uom',
        f'{wh_col} AS warehouse_id' if wh_col else 'NULL AS warehouse_id',
        f'{stor_col} AS storage_id' if stor_col else 'NULL AS storage_id',
        f'{lot_col} AS lot_id' if lot_col else 'NULL AS lot_id',
        f'{bn_col} AS batch_no' if bn_col else 'NULL AS batch_no',
        f'{tt_col} AS transtype' if tt_col else 'NULL AS transtype',
    ]
    where = [f'UPPER(TRIM({sd_col})) = :sd', f'{sn_col} = :sno']
    params: Dict[str, Any] = {'sd': str(source_doc or '').strip().upper(), 'sno': _journal_source_no(source_no)}
    if loc_col:
        where.append(f'{loc_col} = :loc')
        params['loc'] = int(location_code)
    if reset_col:
        where.append(f'{reset_col} = :rn')
        params['rn'] = RESET_NO
    order = lineno_col or item_col
    q = f"SELECT {', '.join(cols)} FROM {tbl} WHERE {' AND '.join(where)} ORDER BY {order}"
    try:
        _, rows = _fetch_rows(q, params)
        return rows or []
    except Exception:
        return []


def _fetch_itemmaster_costs(
    location_code: int,
    item_codes: List[int],
) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    if not item_codes:
        return out
    im_tbl = _detect_table(['ITEMMASTER', 'itemmaster', 'ITEM_MASTER'])
    if not im_tbl:
        return out
    ic = _detect_column(im_tbl, ['ITEMCODE', 'ITEM_CODE', 'itemcode'])
    il = _detect_column(im_tbl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    st = _detect_column(im_tbl, ['CURRENTSTOCK', 'CURRENT_STOCK', 'currentstock'])
    av = _detect_column(im_tbl, ['AVERAGECOST', 'AVERAGE_COST', 'averagecost', 'AVGCOST'])
    la = _detect_column(im_tbl, ['LANDINGCOST', 'LANDING_COST', 'landingcost'])
    co = _detect_column(im_tbl, ['COSTPRICE', 'COST_PRICE', 'costprice', 'COST'])
    nm = _detect_column(im_tbl, ['ITEMNAME', 'ITEM_NAME', 'itemname'])
    if not ic:
        return out
    binds = []
    params: Dict[str, Any] = {}
    for i, code in enumerate(sorted(set(int(c) for c in item_codes if int(c) > 0))):
        k = f'ic{i}'
        binds.append(f':{k}')
        params[k] = code
    if il:
        params['loc'] = int(location_code)
        where = f'{ic} IN ({", ".join(binds)}) AND {il} = :loc'
    else:
        where = f'{ic} IN ({", ".join(binds)})'
    sel = [
        f'{ic} AS itemcode',
        f'NVL({st}, 0) AS currentstock' if st else '0 AS currentstock',
        f'NVL({av}, 0) AS averagecost' if av else '0 AS averagecost',
        f'NVL({la}, 0) AS landingcost' if la else '0 AS landingcost',
        f'NVL({co}, 0) AS costprice' if co else '0 AS costprice',
        f'{nm} AS itemname' if nm else 'NULL AS itemname',
    ]
    try:
        _, rows = _fetch_rows(f'SELECT {", ".join(sel)} FROM {im_tbl} WHERE {where}', params)
        for r in rows or []:
            try:
                icode = int(r.get('itemcode') or 0)
            except (TypeError, ValueError):
                continue
            if icode > 0:
                out[icode] = r
    except Exception:
        pass
    return out


def _grn_previous_stock_for_item(lines: List[Dict[str, Any]], item_code: int) -> Optional[float]:
    """Stored PREVIOUSSTOCK from RECEIPTDTL at post time, if present."""
    ic = int(item_code)
    for ln in lines:
        if int(_f(ln.get('itemcode'))) != ic:
            continue
        if 'previousstock' not in ln:
            return None
        raw = ln.get('previousstock')
        if raw is None:
            continue
        return _f(raw)
    return None


def _grn_weighted_landing(lines: List[Dict[str, Any]], item_code: int) -> Tuple[float, float]:
    """Return (total_base_qty, weighted_landing) for item on receipt (FOC @ 0 landing)."""
    total_q = 0.0
    total_v = 0.0
    for ln in lines:
        try:
            ic = int(ln.get('itemcode') or 0)
        except (TypeError, ValueError):
            continue
        if ic != int(item_code):
            continue
        bq = _f(ln.get('baseqty') or ln.get('receivedqty') or ln.get('quantity'))
        land = _f(ln.get('landingcost'))
        if _norm_foc(ln.get('foc')):
            land = 0.0
        total_q += bq
        total_v += bq * land
    if total_q <= PV_TOL:
        return 0.0, 0.0
    return total_q, total_v / total_q


def _expected_avg_after_grn(
    prev_avg: float,
    prev_stock_before_receipt: float,
    receipt_base_qty: float,
    receipt_landing: float,
) -> float:
    """Expected ITEMMASTER avg if prev_stock_before = stock before this receipt was applied."""
    q0 = max(0.0, prev_stock_before_receipt)
    a0 = max(0.0, prev_avg)
    nq = max(0.0, receipt_base_qty)
    nl = max(0.0, receipt_landing)
    if nq <= PV_TOL:
        return round(a0, 3)
    qty_after = q0 + nq
    if qty_after <= PV_TOL:
        return round(nl, 3)
    return round((q0 * a0 + nq * nl) / qty_after, 3)


def _fetch_grn_header(receipt_no: int, location_code: int) -> Optional[Dict[str, Any]]:
    tbl = _detect_table(['RECEIPTHDR', 'receipthdr'])
    if not tbl:
        return None
    no_col = _detect_column(tbl, ['RECEIPTNO', 'RECEIPT_NO', 'receiptno'])
    date_col = _detect_column(tbl, ['RECEIPTDATE', 'RECEIPT_DATE', 'receiptdate'])
    sup_col = _detect_column(tbl, ['SUPPLIERCODE', 'SUPPLIER_CODE', 'suppliercode'])
    amt_col = _detect_column(tbl, ['INVOICEAMOUNT', 'INVOICE_AMOUNT', 'invoiceamount'])
    inv_col = _detect_column(tbl, ['INVOICENO', 'INVOICE_NO', 'invoiceno'])
    lpo_col = _detect_column(tbl, ['LPONO', 'LPO_NO', 'lpono'])
    wh_col = _detect_column(tbl, ['WAREHOUSE_ID', 'warehouse_id'])
    mode_col = _detect_column(tbl, ['APPROVE_MODE', 'APPROVEMODE', 'POSTMODE', 'SAVE_MODE'])
    loc_col = _detect_column(tbl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    reset_col = _detect_column(tbl, ['RESETNO', 'RESET_NO', 'resetno'])
    del_col = _detect_column(tbl, ['DELFLAG', 'DEL_FLAG', 'delflag'])
    if not no_col:
        return None
    cols = [
        f'{no_col} AS receiptno',
        f'{date_col} AS receiptdate' if date_col else 'NULL AS receiptdate',
        f'{sup_col} AS suppliercode' if sup_col else 'NULL AS suppliercode',
        f'{amt_col} AS invoiceamount' if amt_col else '0 AS invoiceamount',
        f'{inv_col} AS invoiceno' if inv_col else 'NULL AS invoiceno',
        f'{lpo_col} AS lpono' if lpo_col else 'NULL AS lpono',
        f'{wh_col} AS warehouse_id' if wh_col else 'NULL AS warehouse_id',
        f'{mode_col} AS approve_mode' if mode_col else 'NULL AS approve_mode',
    ]
    where = [f'{no_col} = :rno']
    params: Dict[str, Any] = {'rno': coerce_receiptno(receipt_no)}
    if loc_col:
        where.append(f'{loc_col} = :loc')
        params['loc'] = int(location_code)
    if reset_col:
        where.append(f'{reset_col} = :rn')
        params['rn'] = RESET_NO
    if del_col:
        where.append(f"NVL({del_col}, 'N') = 'N'")
    try:
        _, rows = _fetch_rows(f'SELECT {", ".join(cols)} FROM {tbl} WHERE {" AND ".join(where)}', params)
        if not rows:
            return None
        r = rows[0]
        d = r.get('receiptdate')
        if d and hasattr(d, 'strftime'):
            r['receiptdate'] = d.strftime('%Y-%m-%d')
        elif d:
            r['receiptdate'] = str(d)[:10]
        return r
    except Exception:
        return None


def _fetch_grn_lines(receipt_no: int, location_code: int) -> List[Dict[str, Any]]:
    tbl = _detect_table(['RECEIPTDTL', 'receiptdtl'])
    if not tbl:
        return []
    ensure_receiptdtl_previous_cost_columns(tbl)
    ensure_receiptdtl_foc_column(tbl)
    no_col = _detect_column(tbl, ['RECEIPTNO', 'RECEIPT_NO', 'receiptno'])
    item_col = _detect_column(tbl, ['ITEMCODE', 'ITEM_CODE', 'itemcode'])
    lineno_col = _detect_column(tbl, ['LINENO', 'LINE_NO', 'lineno'])
    qty_col = _detect_column(tbl, ['QUANTITY', 'quantity'])
    rcv_col = _detect_column(tbl, ['RECEIVEDQTY', 'RECEIVED_QTY', 'receivedqty'])
    base_col = _detect_column(tbl, ['BASEQTY', 'BASE_QTY', 'baseqty'])
    rate_col = _detect_column(tbl, ['RATE', 'rate'])
    amt_col = _detect_column(tbl, ['AMOUNT', 'amount'])
    land_col = _detect_column(tbl, ['LANDINGCOST', 'LANDING_COST', 'landingcost'])
    avg_col = _detect_column(tbl, ['AVERAGECOST', 'AVERAGE_COST', 'averagecost', 'AVGCOST'])
    prev_stock_col = _detect_column(tbl, ['PREVIOUSSTOCK', 'PREVIOUS_STOCK', 'previousstock'])
    prev_avg_col = _detect_column(tbl, ['PREVIOUSAVGCOST', 'PREVIOUS_AVG_COST', 'previousavgcost'])
    prev_land_col = _detect_column(tbl, ['PREVIOUSLANDINGCOST', 'PREVIOUS_LANDING_COST', 'previouslandingcost'])
    foc_col = _detect_column(tbl, ['FOC', 'foc'])
    uom_col = _detect_column(tbl, ['UNITOFMEASUREMENT', 'UNIT_OF_MEASUREMENT', 'unitofmeasurement', 'UOM', 'uom'])
    wh_col = _detect_column(tbl, ['WAREHOUSE_ID', 'warehouse_id'])
    stor_col = _detect_column(tbl, ['STORAGE_ID', 'storage_id'])
    bn_col = _detect_column(tbl, ['BATCH_NO', 'BATCHNO', 'batch_no'])
    loc_col = _detect_column(tbl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    reset_col = _detect_column(tbl, ['RESETNO', 'RESET_NO', 'resetno'])
    if not no_col or not item_col:
        return []
    cols = [
        f'{lineno_col} AS lineno' if lineno_col else 'NULL AS lineno',
        f'{item_col} AS itemcode',
        f'{qty_col} AS quantity' if qty_col else '0 AS quantity',
        f'{rcv_col} AS receivedqty' if rcv_col else 'NULL AS receivedqty',
        f'{base_col} AS baseqty' if base_col else 'NULL AS baseqty',
        f'{rate_col} AS rate' if rate_col else '0 AS rate',
        f'{amt_col} AS amount' if amt_col else '0 AS amount',
        f'{land_col} AS landingcost' if land_col else 'NULL AS landingcost',
        f'{avg_col} AS averagecost' if avg_col else 'NULL AS averagecost',
        f'{prev_stock_col} AS previousstock' if prev_stock_col else 'NULL AS previousstock',
        f'{prev_avg_col} AS previousavgcost' if prev_avg_col else 'NULL AS previousavgcost',
        f'{prev_land_col} AS previouslandingcost' if prev_land_col else 'NULL AS previouslandingcost',
        f'{foc_col} AS foc' if foc_col else '0 AS foc',
        f'{uom_col} AS uom' if uom_col else 'NULL AS uom',
        f'{wh_col} AS warehouse_id' if wh_col else 'NULL AS warehouse_id',
        f'{stor_col} AS storage_id' if stor_col else 'NULL AS storage_id',
        f'{bn_col} AS batch_no' if bn_col else 'NULL AS batch_no',
    ]
    where = [f'{no_col} = :rno']
    params: Dict[str, Any] = {'rno': coerce_receiptno(receipt_no)}
    if loc_col:
        where.append(f'{loc_col} = :loc')
        params['loc'] = int(location_code)
    if reset_col:
        where.append(f'{reset_col} = :rn')
        params['rn'] = RESET_NO
    order = lineno_col or item_col
    try:
        _, rows = _fetch_rows(f'SELECT {", ".join(cols)} FROM {tbl} WHERE {" AND ".join(where)} ORDER BY {order}', params)
        for r in rows or []:
            bq = _f(r.get('baseqty'))
            if bq <= PV_TOL:
                bq = _f(r.get('receivedqty') or r.get('quantity'))
            r['baseqty'] = bq
            r['foc'] = _norm_foc(r.get('foc'))
        return rows or []
    except Exception:
        return []


def _fetch_pr_header(goods_return_no: int, location_code: int) -> Optional[Dict[str, Any]]:
    tbl = _detect_table(['RETURNHDR', 'returnhdr'])
    if not tbl:
        return None
    no_col = _detect_column(tbl, ['GOODSRETURNNO', 'goodsreturnno'])
    date_col = _detect_column(tbl, ['RETURNDATE', 'returndate'])
    sup_col = _detect_column(tbl, ['SUPPLIERCODE', 'suppliercode'])
    amt_col = _detect_column(tbl, ['RETURNAMOUNT', 'returnamount'])
    rcpt_col = _detect_column(tbl, ['RECEIPTNO', 'receiptno'])
    type_col = _detect_column(tbl, ['RETURNTYPE', 'returntype'])
    loc_col = _detect_column(tbl, ['LOCATIONCODE', 'locationcode'])
    reset_col = _detect_column(tbl, ['RESETNO', 'resetno'])
    del_col = _detect_column(tbl, ['DELFLAG', 'delflag'])
    if not no_col:
        return None
    cols = [
        f'{no_col} AS goodsreturnno',
        f'{date_col} AS returndate' if date_col else 'NULL AS returndate',
        f'{sup_col} AS suppliercode' if sup_col else 'NULL AS suppliercode',
        f'{amt_col} AS returnamount' if amt_col else '0 AS returnamount',
        f'{rcpt_col} AS receiptno' if rcpt_col else 'NULL AS receiptno',
        f'{type_col} AS returntype' if type_col else 'NULL AS returntype',
    ]
    where = [f'{no_col} = :grn']
    params: Dict[str, Any] = {'grn': coerce_goodsreturnno(goods_return_no)}
    if loc_col:
        where.append(f'{loc_col} = :loc')
        params['loc'] = int(location_code)
    if reset_col:
        where.append(f'{reset_col} = :rn')
        params['rn'] = RESET_NO
    if del_col:
        where.append(f"NVL({del_col}, 'N') = 'N'")
    try:
        _, rows = _fetch_rows(f'SELECT {", ".join(cols)} FROM {tbl} WHERE {" AND ".join(where)}', params)
        if not rows:
            return None
        r = rows[0]
        d = r.get('returndate')
        if d and hasattr(d, 'strftime'):
            r['returndate'] = d.strftime('%Y-%m-%d')
        elif d:
            r['returndate'] = str(d)[:10]
        return r
    except Exception:
        return None


def _fetch_pr_lines(goods_return_no: int, location_code: int) -> List[Dict[str, Any]]:
    tbl = _detect_table(['RETURNDTL', 'returndtl'])
    if not tbl:
        return []
    no_col = _detect_column(tbl, ['GOODSRETURNNO', 'goodsreturnno'])
    item_col = _detect_column(tbl, ['ITEMCODE', 'itemcode'])
    sl_col = _detect_column(tbl, ['SLNO', 'slno', 'LINENO', 'lineno'])
    qty_col = _detect_column(tbl, ['QUANTITY', 'quantity'])
    rate_col = _detect_column(tbl, ['RATE', 'rate'])
    avg_col = _detect_column(tbl, ['AVERAGECOST', 'averagecost'])
    uom_col = _detect_column(tbl, ['UOM', 'uom'])
    conv_col = _detect_column(tbl, ['CONVERSIONFACTOR', 'CONVERSION_FACTOR', 'UOMFACTOR', 'conversionfactor'])
    wh_col = _detect_column(tbl, ['WAREHOUSE_ID', 'warehouse_id'])
    stor_col = _detect_column(tbl, ['STORAGE_ID', 'storage_id'])
    lot_col = _detect_column(tbl, ['LOT_ID', 'LOTID', 'lot_id'])
    loc_col = _detect_column(tbl, ['LOCATIONCODE', 'locationcode'])
    reset_col = _detect_column(tbl, ['RESETNO', 'resetno'])
    if not no_col or not item_col:
        return []
    cols = [
        f'{sl_col} AS lineno' if sl_col else 'NULL AS lineno',
        f'{item_col} AS itemcode',
        f'{qty_col} AS quantity' if qty_col else '0 AS quantity',
        f'{rate_col} AS rate' if rate_col else '0 AS rate',
        f'{avg_col} AS averagecost' if avg_col else 'NULL AS averagecost',
        f'{uom_col} AS uom' if uom_col else 'NULL AS uom',
        f'{conv_col} AS conversionfactor' if conv_col else 'NULL AS conversionfactor',
        f'{wh_col} AS warehouse_id' if wh_col else 'NULL AS warehouse_id',
        f'{stor_col} AS storage_id' if stor_col else 'NULL AS storage_id',
        f'{lot_col} AS lot_id' if lot_col else 'NULL AS lot_id',
    ]
    where = [f'{no_col} = :grn']
    params: Dict[str, Any] = {'grn': coerce_goodsreturnno(goods_return_no)}
    if loc_col:
        where.append(f'{loc_col} = :loc')
        params['loc'] = int(location_code)
    if reset_col:
        where.append(f'{reset_col} = :rn')
        params['rn'] = RESET_NO
    order = sl_col or item_col
    try:
        _, rows = _fetch_rows(f'SELECT {", ".join(cols)} FROM {tbl} WHERE {" AND ".join(where)} ORDER BY {order}', params)
        for r in rows or []:
            cf = _f(r.get('conversionfactor') or 1)
            if cf <= 0:
                cf = 1.0
            r['baseqty'] = _f(r.get('quantity')) * cf
        return rows or []
    except Exception:
        return []


def grn_gl_voucher_no(location_code: int, receipt_no: Any) -> str:
    return f'GRN-{int(location_code)}-{coerce_receiptno(receipt_no)}'[:30]


def fetch_grn_posting_hdr_amounts(location_code: int, receipt_no: int) -> Dict[str, float]:
    """TBLGRNPOSTINGHDR subtotal / VAT / total for a posted GRN."""
    out = {'subtotal': 0.0, 'vat': 0.0, 'total': 0.0}
    post_tbl = _detect_table(['TBLGRNPOSTINGHDR', 'tblgrnpostinghdr'])
    if not post_tbl:
        return out
    p_loc = _detect_column(post_tbl, ['LOCATIONCODE', 'locationcode'])
    p_reset = _detect_column(post_tbl, ['RESETNO', 'resetno'])
    p_no = _detect_column(post_tbl, ['RECEIPTNO', 'receiptno'])
    sub_col = _detect_column(post_tbl, ['SUBTOTAL', 'subtotal'])
    vat_col = _detect_column(post_tbl, ['VATAMOUNT', 'VAT_AMOUNT', 'vatamount'])
    tot_col = _detect_column(post_tbl, ['TOTALAMOUNT', 'TOTAL_AMOUNT', 'totalamount'])
    if not (p_loc and p_no):
        return out
    cols = []
    if sub_col:
        cols.append(f'NVL({sub_col}, 0) AS subtotal')
    else:
        cols.append('0 AS subtotal')
    if vat_col:
        cols.append(f'NVL({vat_col}, 0) AS vat')
    else:
        cols.append('0 AS vat')
    if tot_col:
        cols.append(f'NVL({tot_col}, 0) AS total')
    else:
        cols.append('0 AS total')
    wh = [f'{p_loc} = :loc', f'{p_no} = :rno']
    params: Dict[str, Any] = {'loc': int(location_code), 'rno': _grn_posting_receiptno(receipt_no)}
    if p_reset:
        wh.append(f'NVL({p_reset}, 1) = :rn')
        params['rn'] = RESET_NO
    try:
        _, rows = _fetch_rows(
            f'SELECT {", ".join(cols)} FROM {post_tbl} WHERE {" AND ".join(wh)} AND ROWNUM = 1',
            params,
        )
        if rows:
            out['subtotal'] = _f(rows[0].get('subtotal'))
            out['vat'] = _f(rows[0].get('vat'))
            out['total'] = _f(rows[0].get('total'))
    except Exception:
        pass
    return out


def fetch_gl_voucher_credit_total(voucher_no: str) -> float:
    """Supplier payable credit on GRN GL voucher (posted invoice total incl. VAT)."""
    vno = str(voucher_no or '').strip()
    if not vno:
        return 0.0
    gl_tbl = _detect_table(['GL_VOUCHER_DTL', 'gl_voucher_dtl'])
    if not gl_tbl:
        return 0.0
    v_col = _detect_column(gl_tbl, ['VOUCHER_NO', 'voucher_no'])
    cr_col = _detect_column(gl_tbl, ['CREDIT', 'credit'])
    if not (v_col and cr_col):
        return 0.0
    try:
        _, rows = _fetch_rows(
            f'SELECT NVL(MAX({cr_col}), 0) AS gl_total FROM {gl_tbl} WHERE {v_col} = :vno',
            {'vno': vno},
        )
        return _f(rows[0].get('gl_total')) if rows else 0.0
    except Exception:
        return 0.0


def grn_financial_is_posted(location_code: int, receipt_no: int) -> bool:
    if fetch_gl_voucher_credit_total(grn_gl_voucher_no(location_code, receipt_no)) > 0.0005:
        return True
    return fetch_grn_posting_hdr_amounts(location_code, receipt_no).get('total', 0.0) > 0.0005


def enrich_grn_posting_amount_audit(row: Dict[str, Any], location_code: int) -> Dict[str, Any]:
    """Add posted vs GRN invoice amount fields for Purchase Invoice dashboard rows."""
    rno = row.get('receiptno')
    posting_rno = _grn_posting_receiptno(rno)
    inv = _f(row.get('totalamount') or row.get('invoiceamount') or 0)
    post = fetch_grn_posting_hdr_amounts(location_code, posting_rno)
    sub = _f(post.get('subtotal'))
    vat = _f(post.get('vat'))
    tot = _f(post.get('total'))
    gl = fetch_gl_voucher_credit_total(grn_gl_voucher_no(location_code, rno))
    tol = max(1.0, abs(inv) * 0.02)
    mismatch = False
    notes: List[str] = []
    financially_posted = tot > 0.0005 or gl > 0.0005
    if financially_posted:
        if inv > 0.0005 and not _near(inv, sub, tol):
            mismatch = True
            notes.append(f'GRN invoice {inv:.2f} vs posted subtotal {sub:.2f}')
        if tot > 0.0005 and gl > 0.0005 and not _near(tot, gl, 0.05):
            mismatch = True
            notes.append(f'Posted total {tot:.2f} vs GL credit {gl:.2f}')
    row['invoice_amount'] = round(inv, 2)
    row['posted_subtotal'] = round(sub, 2)
    row['posted_vat'] = round(vat, 2)
    row['posted_total'] = round(tot if tot > 0 else gl, 2)
    row['gl_posted_total'] = round(gl, 2)
    row['variance'] = round(inv - sub, 2)
    row['amount_mismatch'] = mismatch
    row['amount_mismatch_note'] = '; '.join(notes)
    row['financially_posted'] = financially_posted
    return row


def _lot_exists(location_code: int, item_code: int, batch_no: str) -> bool:
    if not batch_no or not _table_exists(ITEM_LOT_TABLE):
        return False
    try:
        _, rows = _fetch_rows(
            f"""
            SELECT 1 AS ok FROM {ITEM_LOT_TABLE}
            WHERE LOCATIONCODE = :loc AND ITEMCODE = :ic
              AND UPPER(TRIM(BATCH_NO)) = UPPER(TRIM(:bn))
            """,
            {'loc': int(location_code), 'ic': int(item_code), 'bn': str(batch_no).strip()},
        )
        return bool(rows)
    except Exception:
        return False


def verify_grn_document(receipt_no: Any, location_code: int) -> Dict[str, Any]:
    issues: List[Dict[str, Any]] = []
    header = _fetch_grn_header(receipt_no, location_code)
    lines = _fetch_grn_lines(receipt_no, location_code)
    journal = _fetch_item_journal_for_doc(location_code, 'GRN', receipt_no)

    if not header:
        return {
            'doc_type': 'GRN',
            'doc_no': coerce_receiptno(receipt_no),
            'status': 'err',
            'header': None,
            'lines': [],
            'journal': [],
            'item_audits': [],
            'issues': [_issue('NO_HEADER', 'Receipt header not found.')],
            'summary': {'line_count': 0, 'journal_count': 0, 'issue_count': 1},
        }
    if not lines:
        issues.append(_issue('NO_LINES', 'Receipt has no detail lines.'))

    item_codes = sorted({int(_f(ln.get('itemcode'))) for ln in lines if int(_f(ln.get('itemcode') or 0)) > 0})
    im_map = _fetch_itemmaster_costs(location_code, item_codes)

    line_base_by_item: Dict[int, float] = defaultdict(float)
    line_amt_sum = 0.0
    line_checks: List[Dict[str, Any]] = []

    for ln in lines:
        ic = int(_f(ln.get('itemcode')))
        bq = _f(ln.get('baseqty'))
        line_base_by_item[ic] += bq
        if not _norm_foc(ln.get('foc')):
            line_amt_sum += _f(ln.get('amount'))
        lc_issues: List[str] = []
        if not _norm_foc(ln.get('foc')) and bq > PV_TOL:
            exp_land = _f(ln.get('amount')) / bq if _f(ln.get('amount')) > 0 else _f(ln.get('rate'))
            if not _near(_f(ln.get('landingcost')), exp_land, 0.05):
                lc_issues.append('Line landing cost differs from amount÷base qty')
        bn = str(ln.get('batch_no') or '').strip()
        if bn and is_item_batch_tracked(ic, location_code):
            if not _lot_exists(location_code, ic, bn):
                issues.append(_issue(
                    'LOT_MISSING', f'Item {ic} line batch {bn!r}: no ITEM_LOT row found.',
                    lineno=ln.get('lineno'), itemcode=ic,
                ))
        line_checks.append({
            'lineno': ln.get('lineno'),
            'itemcode': ic,
            'uom': ln.get('uom'),
            'baseqty': bq,
            'rate': _f(ln.get('rate')),
            'amount': _f(ln.get('amount')),
            'foc': _norm_foc(ln.get('foc')),
            'landingcost': _f(ln.get('landingcost')),
            'averagecost': _f(ln.get('averagecost')),
            'previousavgcost': _f(ln.get('previousavgcost')),
            'previouslandingcost': _f(ln.get('previouslandingcost')),
            'warehouse_id': ln.get('warehouse_id'),
            'storage_id': ln.get('storage_id'),
            'batch_no': bn or None,
            'line_issues': lc_issues,
        })

    hdr_amt = _f(header.get('invoiceamount'))
    if hdr_amt > 0 and line_amt_sum > 0 and not _near(hdr_amt, line_amt_sum, max(1.0, hdr_amt * 0.02)):
        issues.append(_issue(
            'AMOUNT_MISMATCH',
            f'Header invoice amount ({hdr_amt:.2f}) differs from paid line total ({line_amt_sum:.2f}).',
            severity='warn',
        ))

    post_amt = fetch_grn_posting_hdr_amounts(location_code, receipt_no)
    post_sub = _f(post_amt.get('subtotal'))
    post_vat = _f(post_amt.get('vat'))
    post_tot = _f(post_amt.get('total'))
    gl_tot = fetch_gl_voucher_credit_total(grn_gl_voucher_no(location_code, receipt_no))
    if grn_financial_is_posted(location_code, receipt_no):
        tol_hdr = max(1.0, abs(hdr_amt) * 0.02)
        if hdr_amt > 0.0005 and post_sub > 0.0005 and not _near(hdr_amt, post_sub, tol_hdr):
            issues.append(_issue(
                'POSTED_INVOICE_MISMATCH',
                f'GRN invoice amount ({hdr_amt:.2f}) differs from posted subtotal ({post_sub:.2f}). '
                f'Posted total incl. VAT is {post_tot:.2f}' + (f' (VAT {post_vat:.2f}).' if post_vat > 0 else '.'),
                severity='warn',
            ))
        if post_tot > 0.0005 and gl_tot > 0.0005 and not _near(post_tot, gl_tot, 0.05):
            issues.append(_issue(
                'POSTED_GL_MISMATCH',
                f'Posted total ({post_tot:.2f}) differs from GL supplier credit ({gl_tot:.2f}).',
                severity='err',
            ))
        elif hdr_amt > 0.0005 and post_tot > 0.0005 and post_vat > 0.0005 and _near(hdr_amt, post_sub, tol_hdr):
            exp_tot = round(hdr_amt + post_vat, 2)
            if not _near(post_tot, exp_tot, max(1.0, abs(post_tot) * 0.02)):
                issues.append(_issue(
                    'POSTED_VAT_TOTAL',
                    f'Posted total ({post_tot:.2f}) differs from GRN amount + VAT ({exp_tot:.2f}).',
                    severity='warn',
                ))

    if not journal:
        issues.append(_issue('NO_JOURNAL', 'No ITEMJOURNAL rows with SOURCE_DOC=GRN for this receipt.'))
    else:
        j_qty_by_item: Dict[int, float] = defaultdict(float)
        j_has_reversal = False
        for j in journal:
            ic = int(_f(j.get('itemcode')))
            q = _f(j.get('qty'))
            tt = str(j.get('transtype') or '').strip().upper()
            j_qty_by_item[ic] += q
            if tt == 'REVERSAL' or q < -PV_TOL:
                j_has_reversal = True
        if j_has_reversal:
            issues.append(_issue(
                'JOURNAL_REVERSAL',
                'Journal includes reversal rows from a GRN re-save (normal after edit). Net qty is checked below.',
                severity='warn',
            ))
        elif any(_f(j.get('qty')) < -PV_TOL for j in journal):
            issues.append(_issue('JOURNAL_SIGN', 'GRN journal should have positive quantities.'))
        for ic, doc_bq in line_base_by_item.items():
            jq = j_qty_by_item.get(ic, 0.0)
            if not _near(doc_bq, jq):
                issues.append(_issue(
                    'JOURNAL_QTY',
                    f'Item {ic}: receipt base qty {doc_bq:.3f} vs journal net sum {jq:.3f}.',
                    itemcode=ic, doc_qty=doc_bq, journal_qty=jq,
                ))

    item_audits: List[Dict[str, Any]] = []
    for ic in item_codes:
        im = im_map.get(ic) or {}
        cur_stock = _f(im.get('currentstock'))
        cur_avg = _f(im.get('averagecost'))
        cur_land = _f(im.get('landingcost'))
        if cur_land <= 0:
            cur_land = cur_avg
        rec_qty, rec_land = _grn_weighted_landing(lines, ic)
        prev_avg = 0.0
        prev_land = 0.0
        for ln in lines:
            if int(_f(ln.get('itemcode'))) == ic:
                if _f(ln.get('previousavgcost')) > 0:
                    prev_avg = _f(ln.get('previousavgcost'))
                if _f(ln.get('previouslandingcost')) > 0:
                    prev_land = _f(ln.get('previouslandingcost'))
                elif prev_avg > 0:
                    prev_land = prev_avg
                break
        stock_before_derived = cur_stock - rec_qty
        stock_before_snap = _grn_previous_stock_for_item(lines, ic)
        stock_before = stock_before_snap if stock_before_snap is not None else stock_before_derived
        stock_before_from_snapshot = stock_before_snap is not None
        expected_avg = _expected_avg_after_grn(prev_avg, stock_before, rec_qty, rec_land)
        expected_land = rec_land if rec_qty > PV_TOL else prev_land
        avg_ok = _near(cur_avg, expected_avg, 0.05) if rec_qty > PV_TOL else True
        land_ok = _near(cur_land, expected_land, 0.05) if rec_qty > PV_TOL else True
        ia_issues: List[str] = []
        if stock_before < -PV_TOL:
            issues.append(_issue(
                'NEG_STOCK_BEFORE',
                f'Item {ic}: stock before this receipt was negative ({stock_before:.3f}) — often from sales/issues before GRN.',
                itemcode=ic, severity='warn',
            ))
            ia_issues.append('Negative stock before receipt')
        if cur_stock < -PV_TOL:
            issues.append(_issue('NEG_STOCK', f'Item {ic}: current stock is negative ({cur_stock:.3f}).', itemcode=ic))
            ia_issues.append('Negative current stock')
        if rec_qty > PV_TOL and not avg_ok:
            issues.append(_issue(
                'AVG_COST',
                f'Item {ic}: ITEMMASTER avg {cur_avg:.3f} vs expected {expected_avg:.3f} (before avg {prev_avg:.3f}, receipt landing {rec_land:.3f}).',
                itemcode=ic, severity='warn',
            ))
            ia_issues.append('Average cost mismatch')
        if rec_qty > PV_TOL and not land_ok:
            issues.append(_issue(
                'LANDING_COST',
                f'Item {ic}: ITEMMASTER landing {cur_land:.3f} vs receipt blended {expected_land:.3f}.',
                itemcode=ic, severity='warn',
            ))
            ia_issues.append('Landing cost mismatch')
        item_audits.append({
            'itemcode': ic,
            'itemname': im.get('itemname'),
            'stock_before_receipt': round(stock_before, 3),
            'stock_before_from_snapshot': stock_before_from_snapshot,
            'stock_before_derived': round(stock_before_derived, 3),
            'receipt_base_qty': round(rec_qty, 3),
            'stock_after_receipt': round(cur_stock, 3),
            'previous_avgcost': round(prev_avg, 3),
            'previous_landingcost': round(prev_land, 3),
            'receipt_blended_landing': round(rec_land, 3),
            'expected_avgcost': round(expected_avg, 3),
            'current_avgcost': round(cur_avg, 3),
            'current_landingcost': round(cur_land, 3),
            'avg_ok': avg_ok,
            'landing_ok': land_ok,
            'issues': ia_issues,
        })

    posting_tbl = _detect_table(['TBLGRNPOSTINGHDR', 'tblgrnpostinghdr'])
    if posting_tbl and str(header.get('approve_mode') or '').lower().find('invoice') >= 0:
        try:
            _, prow = _fetch_rows(
                f'SELECT 1 AS ok FROM {posting_tbl} WHERE LOCATIONCODE = :loc AND RESETNO = :rn AND RECEIPTNO = :rno',
                {'loc': int(location_code), 'rn': RESET_NO, 'rno': _grn_posting_receiptno(receipt_no)},
            )
            if not prow:
                issues.append(_issue('NO_GL_POST', 'Invoice posting mode but TBLGRNPOSTINGHDR row missing.', severity='warn'))
        except Exception:
            pass

    status = _status_from_issues(issues)
    return {
        'doc_type': 'GRN',
        'doc_no': coerce_receiptno(receipt_no),
        'status': status,
        'header': header,
        'lines': line_checks,
        'journal': journal,
        'item_audits': item_audits,
        'issues': issues,
        'summary': {
            'line_count': len(lines),
            'journal_count': len(journal),
            'issue_count': len(issues),
            'error_count': sum(1 for i in issues if i.get('severity') == 'err'),
            'warn_count': sum(1 for i in issues if i.get('severity') == 'warn'),
        },
    }


def verify_purchase_return_document(goods_return_no: Any, location_code: int) -> Dict[str, Any]:
    issues: List[Dict[str, Any]] = []
    header = _fetch_pr_header(goods_return_no, location_code)
    lines = _fetch_pr_lines(goods_return_no, location_code)
    journal = _fetch_item_journal_for_doc(location_code, 'RETURN', goods_return_no)

    if not header:
        return {
            'doc_type': 'PR',
            'doc_no': billno_numeric_part(goods_return_no) or goods_return_no,
            'status': 'err',
            'header': None,
            'lines': [],
            'journal': [],
            'item_audits': [],
            'issues': [_issue('NO_HEADER', 'Purchase return header not found.')],
            'summary': {'line_count': 0, 'journal_count': 0, 'issue_count': 1},
        }
    if not lines:
        issues.append(_issue('NO_LINES', 'Return has no detail lines.'))

    item_codes = sorted({int(_f(ln.get('itemcode'))) for ln in lines if int(_f(ln.get('itemcode') or 0)) > 0})
    im_map = _fetch_itemmaster_costs(location_code, item_codes)

    line_base_by_item: Dict[int, float] = defaultdict(float)
    line_checks: List[Dict[str, Any]] = []
    for ln in lines:
        ic = int(_f(ln.get('itemcode')))
        bq = _f(ln.get('baseqty'))
        line_base_by_item[ic] += bq
        line_checks.append({
            'lineno': ln.get('lineno'),
            'itemcode': ic,
            'uom': ln.get('uom'),
            'baseqty': bq,
            'rate': _f(ln.get('rate')),
            'averagecost': _f(ln.get('averagecost')),
            'warehouse_id': ln.get('warehouse_id'),
            'storage_id': ln.get('storage_id'),
            'lot_id': ln.get('lot_id'),
        })

    if not journal:
        issues.append(_issue('NO_JOURNAL', 'No ITEMJOURNAL rows with SOURCE_DOC=RETURN for this return.'))
    else:
        j_qty_by_item: Dict[int, float] = defaultdict(float)
        for j in journal:
            ic = int(_f(j.get('itemcode')))
            j_qty_by_item[ic] += _f(j.get('qty'))
        for ic, doc_bq in line_base_by_item.items():
            jq = j_qty_by_item.get(ic, 0.0)
            if not _near(-doc_bq, jq):
                issues.append(_issue(
                    'JOURNAL_QTY',
                    f'Item {ic}: return base qty {doc_bq:.3f} vs journal sum {jq:.3f} (expect negative).',
                    itemcode=ic, doc_qty=doc_bq, journal_qty=jq,
                ))
            if jq > PV_TOL:
                issues.append(_issue('JOURNAL_SIGN', f'Item {ic}: purchase return journal qty should be negative.', itemcode=ic))

    item_audits: List[Dict[str, Any]] = []
    for ic in item_codes:
        im = im_map.get(ic) or {}
        cur_stock = _f(im.get('currentstock'))
        cur_avg = _f(im.get('averagecost'))
        ret_qty = line_base_by_item.get(ic, 0.0)
        ia_issues: List[str] = []
        if cur_stock < -PV_TOL:
            issues.append(_issue('NEG_STOCK', f'Item {ic}: current stock is negative ({cur_stock:.3f}).', itemcode=ic))
            ia_issues.append('Negative stock')
        item_audits.append({
            'itemcode': ic,
            'itemname': im.get('itemname'),
            'return_base_qty': round(ret_qty, 3),
            'current_stock': round(cur_stock, 3),
            'current_avgcost': round(cur_avg, 3),
            'note': 'Purchase return reduces stock only; average cost unchanged on save.',
            'issues': ia_issues,
        })

    posting_tbl = _detect_table(['TBLPRPOSTINGHDR', 'tblprpostinghdr'])
    if posting_tbl:
        try:
            _, prow = _fetch_rows(
                f'SELECT 1 AS ok FROM {posting_tbl} WHERE LOCATIONCODE = :loc AND RESETNO = :rn AND GOODSRETURNNO = :grn',
                {'loc': int(location_code), 'rn': RESET_NO, 'grn': billno_numeric_part(goods_return_no)},
            )
            if not prow:
                issues.append(_issue('NO_FIN_POST', 'No TBLPRPOSTINGHDR row (financial posting may be pending).', severity='warn'))
        except Exception:
            pass

    status = _status_from_issues(issues)
    return {
        'doc_type': 'PR',
        'doc_no': billno_numeric_part(goods_return_no) or goods_return_no,
        'status': status,
        'header': header,
        'lines': line_checks,
        'journal': journal,
        'item_audits': item_audits,
        'issues': issues,
        'summary': {
            'line_count': len(lines),
            'journal_count': len(journal),
            'issue_count': len(issues),
            'error_count': sum(1 for i in issues if i.get('severity') == 'err'),
            'warn_count': sum(1 for i in issues if i.get('severity') == 'warn'),
        },
    }


def verify_document_detail(doc_type: str, doc_no: Any, location_code: int) -> Dict[str, Any]:
    dt = str(doc_type or '').strip().upper()
    if dt in ('GRN', 'RECEIPT', 'R'):
        return verify_grn_document(doc_no, int(location_code))
    if dt in ('PR', 'RETURN', 'P'):
        return verify_purchase_return_document(doc_no, int(location_code))
    return {'success': False, 'error': 'Invalid doc_type (use GRN or PR).'}


def _list_grn_documents(
    location_code: int,
    *,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    tbl = _detect_table(['RECEIPTHDR', 'receipthdr'])
    if not tbl:
        return []
    no_col = _detect_column(tbl, ['RECEIPTNO', 'RECEIPT_NO', 'receiptno'])
    date_col = _detect_column(tbl, ['RECEIPTDATE', 'RECEIPT_DATE', 'receiptdate'])
    sup_col = _detect_column(tbl, ['SUPPLIERCODE', 'SUPPLIER_CODE', 'suppliercode'])
    amt_col = _detect_column(tbl, ['INVOICEAMOUNT', 'INVOICE_AMOUNT', 'invoiceamount'])
    inv_col = _detect_column(tbl, ['INVOICENO', 'INVOICE_NO', 'invoiceno'])
    loc_col = _detect_column(tbl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    del_col = _detect_column(tbl, ['DELFLAG', 'DEL_FLAG', 'delflag'])
    if not no_col:
        return []
    cols = [
        f"'GRN' AS doc_type",
        f'{no_col} AS doc_no',
        f'{date_col} AS doc_date' if date_col else 'NULL AS doc_date',
        f'{sup_col} AS suppliercode' if sup_col else 'NULL AS suppliercode',
        f'{amt_col} AS amount' if amt_col else '0 AS amount',
        f'{inv_col} AS reference' if inv_col else 'NULL AS reference',
    ]
    where = ['1=1']
    params: Dict[str, Any] = {}
    if loc_col:
        where.append(f'{loc_col} = :loc')
        params['loc'] = int(location_code)
    if del_col:
        where.append(f"NVL({del_col}, 'N') = 'N'")
    if date_col and date_from:
        where.append(f'TRUNC({date_col}) >= TO_DATE(:df, \'YYYY-MM-DD\')')
        params['df'] = date_from[:10]
    if date_col and date_to:
        where.append(f'TRUNC({date_col}) <= TO_DATE(:dt, \'YYYY-MM-DD\')')
        params['dt'] = date_to[:10]
    if search:
        sp = search.strip().upper().replace('*', '%')
        if '%' not in sp:
            sp = f'%{sp}%'
        params['search'] = sp
        bits = [f'TO_CHAR({no_col}) LIKE :search']
        if inv_col:
            bits.append(f'UPPER({inv_col}) LIKE :search')
        where.append('(' + ' OR '.join(bits) + ')')
    q = f"SELECT {', '.join(cols)} FROM {tbl} WHERE {' AND '.join(where)} ORDER BY {no_col} DESC"
    try:
        _, rows = _fetch_rows(q, params)
        out = rows or []
        for r in out:
            d = r.get('doc_date')
            if d and hasattr(d, 'strftime'):
                r['doc_date'] = d.strftime('%Y-%m-%d')
            elif d:
                r['doc_date'] = str(d)[:10]
        return out[: max(1, min(int(limit or 200), 500))]
    except Exception:
        return []


def _list_pr_documents(
    location_code: int,
    *,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    tbl = _detect_table(['RETURNHDR', 'returnhdr'])
    if not tbl:
        return []
    no_col = _detect_column(tbl, ['GOODSRETURNNO', 'goodsreturnno'])
    date_col = _detect_column(tbl, ['RETURNDATE', 'returndate'])
    sup_col = _detect_column(tbl, ['SUPPLIERCODE', 'suppliercode'])
    amt_col = _detect_column(tbl, ['RETURNAMOUNT', 'returnamount'])
    rcpt_col = _detect_column(tbl, ['RECEIPTNO', 'receiptno'])
    type_col = _detect_column(tbl, ['RETURNTYPE', 'returntype'])
    loc_col = _detect_column(tbl, ['LOCATIONCODE', 'locationcode'])
    del_col = _detect_column(tbl, ['DELFLAG', 'delflag'])
    if not no_col:
        return []
    cols = [
        "'PR' AS doc_type",
        f'{no_col} AS doc_no',
        f'{date_col} AS doc_date' if date_col else 'NULL AS doc_date',
        f'{sup_col} AS suppliercode' if sup_col else 'NULL AS suppliercode',
        f'{amt_col} AS amount' if amt_col else '0 AS amount',
        f'{rcpt_col} AS reference' if rcpt_col else 'NULL AS reference',
    ]
    where = ['1=1']
    params: Dict[str, Any] = {}
    if loc_col:
        where.append(f'{loc_col} = :loc')
        params['loc'] = int(location_code)
    if del_col:
        where.append(f"NVL({del_col}, 'N') = 'N'")
    if type_col:
        where.append(f"NVL({type_col}, 'P') = 'P'")
    if date_col and date_from:
        where.append(f'TRUNC({date_col}) >= TO_DATE(:df, \'YYYY-MM-DD\')')
        params['df'] = date_from[:10]
    if date_col and date_to:
        where.append(f'TRUNC({date_col}) <= TO_DATE(:dt, \'YYYY-MM-DD\')')
        params['dt'] = date_to[:10]
    if search:
        sp = search.strip().upper().replace('*', '%')
        if '%' not in sp:
            sp = f'%{sp}%'
        params['search'] = sp
        where.append(f'TO_CHAR({no_col}) LIKE :search')
    q = f"SELECT {', '.join(cols)} FROM {tbl} WHERE {' AND '.join(where)} ORDER BY {no_col} DESC"
    try:
        _, rows = _fetch_rows(q, params)
        out = rows or []
        for r in out:
            d = r.get('doc_date')
            if d and hasattr(d, 'strftime'):
                r['doc_date'] = d.strftime('%Y-%m-%d')
            elif d:
                r['doc_date'] = str(d)[:10]
        return out[: max(1, min(int(limit or 200), 500))]
    except Exception:
        return []


def _quick_verify(doc_type: str, doc_no: Any, location_code: int) -> Tuple[str, int, str]:
    """Lightweight status for document list (journal + qty only)."""
    dt = str(doc_type or '').upper()
    if dt == 'GRN':
        lines = _fetch_grn_lines(doc_no, location_code)
        journal = _fetch_item_journal_for_doc(location_code, 'GRN', doc_no)
        src = 'GRN'
        sign_ok = lambda q: q >= -PV_TOL
        expect = lambda bq, jq: _near(bq, jq)
    else:
        lines = _fetch_pr_lines(doc_no, location_code)
        journal = _fetch_item_journal_for_doc(location_code, 'RETURN', doc_no)
        src = 'RETURN'
        sign_ok = lambda q: q <= PV_TOL
        expect = lambda bq, jq: _near(-bq, jq)

    if not lines:
        return 'err', 1, 'No lines'
    issues = 0
    msgs: List[str] = []
    if not journal:
        return 'err', 1, 'No journal'
    by_item: Dict[int, float] = defaultdict(float)
    for ln in lines:
        by_item[int(_f(ln.get('itemcode')))] += _f(ln.get('baseqty'))
    jq_map: Dict[int, float] = defaultdict(float)
    for j in journal:
        q = _f(j.get('qty'))
        if not sign_ok(q):
            issues += 1
            msgs.append('Journal sign')
            break
        jq_map[int(_f(j.get('itemcode')))] += q
    for ic, bq in by_item.items():
        if not expect(bq, jq_map.get(ic, 0.0)):
            issues += 1
            msgs.append(f'Qty item {ic}')
            break
    if issues:
        return 'err', issues, '; '.join(msgs[:3])
    return 'ok', 0, ''


def list_purchase_verification_documents(
    location_code: int,
    *,
    doc_type: str = 'all',
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    search: Optional[str] = None,
    mismatch_only: bool = False,
    limit: int = 100,
) -> Dict[str, Any]:
    dt = str(doc_type or 'all').strip().lower()
    rows: List[Dict[str, Any]] = []
    if dt in ('all', 'grn'):
        rows.extend(_list_grn_documents(location_code, date_from=date_from, date_to=date_to, search=search, limit=limit))
    if dt in ('all', 'pr'):
        rows.extend(_list_pr_documents(location_code, date_from=date_from, date_to=date_to, search=search, limit=limit))
    rows.sort(key=lambda r: (str(r.get('doc_date') or ''), _doc_no_sort_key(r.get('doc_no'))), reverse=True)
    rows = rows[: max(1, min(int(limit or 100), 300))]

    ok_c = warn_c = err_c = 0
    out_rows: List[Dict[str, Any]] = []
    for r in rows:
        dtype = str(r.get('doc_type') or 'GRN')
        dno = r.get('doc_no')
        st, ic, msg = _quick_verify(dtype, dno, location_code)
        if mismatch_only and st == 'ok':
            continue
        row = dict(r)
        row['status'] = st
        row['issue_count'] = ic
        row['issue_summary'] = msg
        out_rows.append(row)
        if st == 'ok':
            ok_c += 1
        elif st == 'warn':
            warn_c += 1
        else:
            err_c += 1

    return {
        'rows': out_rows,
        'summary': {
            'total': len(out_rows),
            'ok': ok_c,
            'warn': warn_c,
            'err': err_c,
        },
    }


def flatten_verification_export_rows(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Flat rows for CSV export from list API payload."""
    out: List[Dict[str, Any]] = []
    for r in payload.get('rows') or []:
        out.append({
            'doc_type': r.get('doc_type'),
            'doc_no': r.get('doc_no'),
            'doc_date': r.get('doc_date'),
            'suppliercode': r.get('suppliercode'),
            'amount': r.get('amount'),
            'reference': r.get('reference'),
            'status': r.get('status'),
            'issue_count': r.get('issue_count'),
            'issue_summary': r.get('issue_summary'),
        })
    return out
