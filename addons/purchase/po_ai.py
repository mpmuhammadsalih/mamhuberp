"""
Purchase Order AI assistant — reorder, supplier, price, duplicate detection,
pre-approval validation, delivery prediction, and natural-language PO parsing.

Rule-based analysis runs without OpenAI; narrative summaries use OpenAI when configured.
"""
from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from db import _detect_column, _detect_table, _fetch_rows, _safe_rows, _table_exists

from addons.purchase.grn_validation import _item_avg_grn_qty, _item_last_costs, _parse_date, _risk_level

SALES_VELOCITY_DAYS = int(os.environ.get('PO_AI_SALES_VELOCITY_DAYS', '90') or 90)
DUPLICATE_PO_DAYS = int(os.environ.get('PO_AI_DUP_PO_DAYS', '14') or 14)
PRICE_VARIANCE_WARN_PCT = float(os.environ.get('PO_AI_PRICE_VARIANCE_WARN_PCT', '15') or 15)
PRICE_VARIANCE_BLOCK_PCT = float(os.environ.get('PO_AI_PRICE_VARIANCE_BLOCK_PCT', '35') or 35)
QTY_OVER_REORDER_RATIO = float(os.environ.get('PO_AI_QTY_OVER_REORDER_RATIO', '3.0') or 3.0)


def _risk_level_po(score: int) -> str:
    return _risk_level(score)


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _parse_po_lines(raw_lines: List[Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for i, ln in enumerate(raw_lines or [], start=1):
        if not isinstance(ln, dict):
            continue
        ic = _safe_int(ln.get('itemcode') or ln.get('item_code'))
        if ic <= 0:
            continue
        qty = _safe_float(ln.get('quantity') or ln.get('qty'))
        base = _safe_float(ln.get('baseqty') or ln.get('base_qty'))
        if base <= 0:
            base = qty
        out.append({
            'line': i,
            'itemcode': ic,
            'itemname': str(ln.get('itemname') or ln.get('item_name') or '').strip(),
            'barcode': str(ln.get('barcode') or ln.get('manufacturerid') or '').strip(),
            'quantity': qty,
            'baseqty': base,
            'rate': _safe_float(ln.get('rate')),
            'uom': str(ln.get('uom') or ln.get('unitofmeasurement') or 'NOS').strip() or 'NOS',
            'amount': _safe_float(ln.get('amount')),
        })
    return out


def _item_master_batch(item_codes: List[int], location_code: int) -> Dict[int, Dict[str, Any]]:
    if not item_codes:
        return {}
    im = _detect_table(['ITEMMASTER', 'itemmaster'])
    if not im:
        return {}
    ic = _detect_column(im, ['ITEMCODE', 'ITEM_CODE', 'itemcode'])
    nm = _detect_column(im, ['ITEMNAME', 'ITEM_NAME', 'itemname'])
    loc = _detect_column(im, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    reorder = _detect_column(im, ['REORDERLEVEL', 'REORDER_LEVEL', 'reorderlevel'])
    maximum = _detect_column(im, ['MAXIMUMLEVEL', 'MAXIMUM_LEVEL', 'maximumlevel'])
    stock = _detect_column(im, ['CURRENTSTOCK', 'CURRENT_STOCK', 'currentstock'])
    cost = _detect_column(im, ['COSTPRICE', 'COST_PRICE', 'costprice'])
    sup = _detect_column(im, ['SUPCODE', 'SUPPLIERCODE', 'SUPPLIER_CODE', 'supcode'])
    if not ic:
        return {}
    in_list = ', '.join(str(int(x)) for x in sorted(set(item_codes)))
    cols = [f'{ic} AS itemcode']
    cols.append(f'{nm} AS itemname' if nm else 'NULL AS itemname')
    cols.append(f'NVL({reorder},0) AS reorder_level' if reorder else '0 AS reorder_level')
    cols.append(f'NVL({maximum},0) AS maximum_level' if maximum else '0 AS maximum_level')
    cols.append(f'NVL({stock},0) AS current_stock' if stock else '0 AS current_stock')
    cols.append(f'NVL({cost},0) AS cost_price' if cost else '0 AS cost_price')
    cols.append(f'NVL({sup},0) AS default_supplier' if sup else '0 AS default_supplier')
    where = [f'{ic} IN ({in_list})']
    params: Dict[str, Any] = {}
    if loc:
        where.append(f'{loc} = :loc')
        params['loc'] = location_code
    q = f"SELECT {', '.join(cols)} FROM {im} WHERE {' AND '.join(where)}"
    out: Dict[int, Dict[str, Any]] = {}
    try:
        for r in _safe_rows(q, params) or []:
            ic_v = _safe_int(r.get('itemcode'))
            if ic_v > 0:
                out[ic_v] = r
    except Exception:
        pass
    return out


def _sales_velocity(item_codes: List[int], location_code: int, days: int = SALES_VELOCITY_DAYS) -> Dict[int, float]:
    """Average daily sales qty (base units) per item over recent history."""
    if not item_codes:
        return {}
    dtl = _detect_table(['BILLDTLHISTORY', 'billdtlhistory', 'BILLDTL', 'billdtl'])
    hdr = _detect_table(['BILLHDRHISTORY', 'billhdrhistory', 'BILLHDR', 'billhdr'])
    if not dtl:
        return {}
    ic = _detect_column(dtl, ['ITEMCODE', 'ITEM_CODE', 'itemcode'])
    qty = _detect_column(dtl, ['QUANTITY', 'quantity'])
    bill = _detect_column(dtl, ['BILLNO', 'BILL_NO', 'billno'])
    if not ic or not qty or not bill:
        return {}
    in_list = ', '.join(str(int(x)) for x in sorted(set(item_codes)))
    date_col = None
    loc_col = None
    join = ''
    if hdr:
        h_bill = _detect_column(hdr, ['BILLNO', 'BILL_NO', 'billno'])
        date_col = _detect_column(hdr, ['BILLDATE', 'BILL_DATE', 'billdate'])
        loc_col = _detect_column(hdr, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
        if h_bill:
            join = f' INNER JOIN {hdr} h ON d.{bill} = h.{h_bill} '
    alias = 'd'
    where = [f'{alias}.{ic} IN ({in_list})', f'NVL({alias}.{qty},0) > 0']
    params: Dict[str, Any] = {'days': max(7, days)}
    if date_col and join:
        where.append(f'h.{date_col} >= TRUNC(SYSDATE) - :days')
        if loc_col:
            where.append(f'h.{loc_col} = :loc')
            params['loc'] = location_code
    q = f"""
        SELECT {alias}.{ic} AS ic, SUM(ABS(NVL({alias}.{qty},0))) AS sqty
        FROM {dtl} {alias}{join}
        WHERE {' AND '.join(where)}
        GROUP BY {alias}.{ic}
    """
    out: Dict[int, float] = {}
    span = max(1, days)
    try:
        for r in _safe_rows(q, params) or []:
            ic_v = _safe_int(r.get('ic'))
            sq = _safe_float(r.get('sqty'))
            if ic_v > 0 and sq > 0:
                out[ic_v] = sq / span
    except Exception:
        pass
    return out


def _pending_po_qty(item_codes: List[int], location_code: int, reset_no: int, exclude_lpo: int = 0) -> Dict[int, float]:
    """Open PO qty not yet received (approved/draft LPO without GRN)."""
    if not item_codes:
        return {}
    hdr = _detect_table(['LPOHDR', 'lpohdr'])
    dtl = _detect_table(['LPODTL', 'lpodtl'])
    rh = _detect_table(['RECEIPTHDR', 'receipthdr'])
    if not hdr or not dtl:
        return {}
    h_no = _detect_column(hdr, ['LPONO', 'LPO_NO', 'lpono'])
    h_loc = _detect_column(hdr, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    h_reset = _detect_column(hdr, ['RESETNO', 'RESET_NO', 'resetno'])
    h_del = _detect_column(hdr, ['DELFLAG', 'DEL_FLAG', 'delflag'])
    d_lpo = _detect_column(dtl, ['LPONO', 'LPO_NO', 'lpono'])
    d_ic = _detect_column(dtl, ['ITEMCODE', 'ITEM_CODE', 'itemcode'])
    d_qty = _detect_column(dtl, ['INQUANTITY', 'INQUANTTITY', 'QUANTITY', 'quantity'])
    d_loc = _detect_column(dtl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    d_reset = _detect_column(dtl, ['RESETNO', 'RESET_NO', 'resetno'])
    if not all([h_no, d_lpo, d_ic, d_qty]):
        return {}
    in_list = ', '.join(str(int(x)) for x in sorted(set(item_codes)))
    where = [f'd.{d_ic} IN ({in_list})', f'NVL(d.{d_qty},0) > 0']
    params: Dict[str, Any] = {'loc': location_code, 'rn': reset_no}
    if d_loc:
        where.append(f'd.{d_loc} = :loc')
    if d_reset:
        where.append(f'NVL(d.{d_reset},1) = :rn')
    if exclude_lpo > 0:
        where.append(f'd.{d_lpo} <> :excl')
        params['excl'] = exclude_lpo
    if h_del:
        where.append(f"NVL(h.{h_del},'N') <> 'Y'")
    recv_filter = ''
    if rh and _detect_column(rh, ['LPONO', 'LPO_NO', 'lpono']):
        r_lpo = _detect_column(rh, ['LPONO', 'LPO_NO', 'lpono'])
        r_loc = _detect_column(rh, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
        r_del = _detect_column(rh, ['DELFLAG', 'DEL_FLAG', 'delflag'])
        rw = [f'r.{r_lpo} = h.{h_no}']
        if r_loc and h_loc:
            rw.append(f'r.{r_loc} = h.{h_loc}')
        if r_del:
            rw.append(f"NVL(r.{r_del},'N') <> 'Y'")
        recv_filter = f' AND NOT EXISTS (SELECT 1 FROM {rh} r WHERE {" AND ".join(rw)}) '
    hw = [f'h.{h_no} = d.{d_lpo}']
    if h_loc:
        hw.append(f'h.{h_loc} = :loc')
    if h_reset:
        hw.append(f'NVL(h.{h_reset},1) = :rn')
    q = f"""
        SELECT d.{d_ic} AS ic, SUM(NVL(d.{d_qty},0)) AS pq
        FROM {dtl} d
        INNER JOIN {hdr} h ON {' AND '.join(hw)}
        WHERE {' AND '.join(where)}{recv_filter}
        GROUP BY d.{d_ic}
    """
    out: Dict[int, float] = {}
    try:
        for r in _safe_rows(q, params) or []:
            ic_v = _safe_int(r.get('ic'))
            if ic_v > 0:
                out[ic_v] = _safe_float(r.get('pq'))
    except Exception:
        pass
    return out


def _compute_reorder_suggestions(
    item_codes: List[int],
    location_code: int,
    reset_no: int,
    exclude_lpo: int = 0,
    lead_days: int = 14,
) -> List[Dict[str, Any]]:
    master = _item_master_batch(item_codes, location_code)
    velocity = _sales_velocity(item_codes, location_code)
    pending = _pending_po_qty(item_codes, location_code, reset_no, exclude_lpo)
    suggestions: List[Dict[str, Any]] = []
    for ic in item_codes:
        m = master.get(ic) or {}
        stock = _safe_float(m.get('current_stock'))
        reorder = _safe_float(m.get('reorder_level'))
        maximum = _safe_float(m.get('maximum_level'))
        daily = _safe_float(velocity.get(ic))
        pend = _safe_float(pending.get(ic))
        lead_demand = daily * max(1, lead_days)
        if maximum > 0:
            target = maximum
        elif reorder > 0:
            target = max(reorder, lead_demand)
        elif daily > 0:
            target = lead_demand * 2
        else:
            target = 0.0
        suggested = max(0.0, target - stock - pend)
        if suggested <= 0 and stock <= reorder and reorder > 0:
            suggested = max(0.0, reorder - stock - pend)
        reason_parts: List[str] = []
        if stock <= reorder and reorder > 0:
            reason_parts.append('below reorder level')
        if pend > 0:
            reason_parts.append(f'{pend:.0g} already on open PO')
        if daily > 0:
            reason_parts.append(f'~{daily * 30:.0g}/mo sales')
        suggestions.append({
            'itemcode': ic,
            'itemname': str(m.get('itemname') or '').strip(),
            'current_stock': round(stock, 3),
            'reorder_level': round(reorder, 3),
            'maximum_level': round(maximum, 3),
            'pending_po_qty': round(pend, 3),
            'avg_daily_sales': round(daily, 4),
            'suggested_qty': round(suggested, 3) if suggested > 0.0001 else 0,
            'reason': '; '.join(reason_parts) or 'stock review',
        })
    suggestions.sort(key=lambda x: (-1 if x.get('suggested_qty', 0) > 0 else 0, -x.get('suggested_qty', 0)))
    return suggestions


def _supplier_stats_for_items(item_codes: List[int], location_code: int) -> Dict[int, List[Dict[str, Any]]]:
    """Per item: list of suppliers with order count, avg rate, avg lead days."""
    if not item_codes:
        return {}
    dtl = _detect_table(['RECEIPTDTL', 'receiptdtl'])
    hdr = _detect_table(['RECEIPTHDR', 'receipthdr'])
    if not dtl or not hdr:
        return {}
    d_ic = _detect_column(dtl, ['ITEMCODE', 'ITEM_CODE', 'itemcode'])
    d_rate = _detect_column(dtl, ['RATE', 'rate'])
    d_qty = _detect_column(dtl, ['QUANTITY', 'quantity'])
    d_no = _detect_column(dtl, ['RECEIPTNO', 'RECEIPT_NO', 'receiptno'])
    h_no = _detect_column(hdr, ['RECEIPTNO', 'RECEIPT_NO', 'receiptno'])
    h_sup = _detect_column(hdr, ['SUPPLIERCODE', 'SUPPLIER_CODE', 'suppliercode'])
    h_loc = _detect_column(hdr, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    h_date = _detect_column(hdr, ['RECEIPTDATE', 'RECEIPT_DATE', 'receiptdate'])
    h_lpo = _detect_column(hdr, ['LPONO', 'LPO_NO', 'lpono'])
    if not all([d_ic, d_no, h_no, h_sup]):
        return {}
    in_list = ', '.join(str(int(x)) for x in sorted(set(item_codes)))
    join = f'd.{d_no} = h.{h_no}'
    if h_loc and _detect_column(dtl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode']):
        d_loc = _detect_column(dtl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
        join += f' AND d.{d_loc} = h.{h_loc}'
    where = [f'd.{d_ic} IN ({in_list})', f'NVL(h.{h_sup},0) > 0']
    params: Dict[str, Any] = {'loc': location_code}
    if h_loc:
        where.append(f'h.{h_loc} = :loc')
    rate_expr = f'NVL(d.{d_rate},0)' if d_rate else '0'
    qty_expr = f'NVL(d.{d_qty},0)' if d_qty else '1'
    q = f"""
        SELECT d.{d_ic} AS ic, h.{h_sup} AS sup,
               COUNT(*) AS cnt,
               AVG(CASE WHEN {rate_expr} > 0 THEN {rate_expr} END) AS avg_rate,
               MIN(CASE WHEN {rate_expr} > 0 THEN {rate_expr} END) AS min_rate
        FROM {dtl} d
        INNER JOIN {hdr} h ON {join}
        WHERE {' AND '.join(where)}
        GROUP BY d.{d_ic}, h.{h_sup}
    """
    sup_tbl = _detect_table(['SUPPLIER', 'supplier'])
    sup_code = _detect_column(sup_tbl, ['SUPPLIERCODE', 'SUPPLIER_CODE', 'suppliercode']) if sup_tbl else None
    sup_name = _detect_column(sup_tbl, ['SUPPLIERNAME', 'SUPPLIER_NAME', 'suppliername']) if sup_tbl else None
    sup_names: Dict[int, str] = {}
    if sup_tbl and sup_code and sup_name:
        try:
            for r in _safe_rows(f'SELECT {sup_code} AS sc, {sup_name} AS sn FROM {sup_tbl}', {}) or []:
                sup_names[_safe_int(r.get('sc'))] = str(r.get('sn') or '').strip()
        except Exception:
            pass
    lead_by_sup: Dict[Tuple[int, int], float] = {}
    if h_lpo and h_date:
        lpo_hdr = _detect_table(['LPOHDR', 'lpohdr'])
        if lpo_hdr:
            l_no = _detect_column(lpo_hdr, ['LPONO', 'LPO_NO', 'lpono'])
            l_date = _detect_column(lpo_hdr, ['LPODATE', 'LPO_DATE', 'lpodate'])
            l_loc = _detect_column(lpo_hdr, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
            if l_no and l_date:
                lw = [f'h.{h_lpo} = l.{l_no}', f'h.{h_lpo} > 0']
                if l_loc and h_loc:
                    lw.append(f'l.{l_loc} = h.{h_loc}')
                lq = f"""
                    SELECT h.{h_sup} AS sup, AVG(h.{h_date} - l.{l_date}) AS avg_lead
                    FROM {hdr} h
                    INNER JOIN {lpo_hdr} l ON {' AND '.join(lw)}
                    WHERE h.{h_loc} = :loc AND h.{h_sup} > 0
                    GROUP BY h.{h_sup}
                """
                try:
                    for r in _safe_rows(lq, params) or []:
                        sup_v = _safe_int(r.get('sup'))
                        lead_by_sup[(0, sup_v)] = _safe_float(r.get('avg_lead'))
                except Exception:
                    pass
    raw: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    try:
        rows = _safe_rows(q, params) or []
    except Exception:
        rows = []
    max_cnt = 1
    min_rate_global: Dict[int, float] = {}
    for r in rows:
        ic_v = _safe_int(r.get('ic'))
        sup_v = _safe_int(r.get('sup'))
        cnt = _safe_int(r.get('cnt'))
        max_cnt = max(max_cnt, cnt)
        avg_r = _safe_float(r.get('avg_rate'))
        min_r = _safe_float(r.get('min_rate'))
        if ic_v > 0 and sup_v > 0:
            prev = min_rate_global.get(ic_v)
            if prev is None or (min_r > 0 and min_r < prev):
                min_rate_global[ic_v] = min_r
            raw[ic_v].append({
                'supplier_code': sup_v,
                'supplier_name': sup_names.get(sup_v, f'Supplier {sup_v}'),
                'order_count': cnt,
                'avg_rate': round(avg_r, 4),
                'min_rate': round(min_r, 4),
                'avg_lead_days': round(lead_by_sup.get((0, sup_v), 0), 1),
            })
    out: Dict[int, List[Dict[str, Any]]] = {}
    for ic_v, lst in raw.items():
        best_min = min_rate_global.get(ic_v) or 0
        scored: List[Dict[str, Any]] = []
        max_lead = max((_safe_float(x.get('avg_lead_days')) for x in lst), default=1) or 1
        for row in lst:
            price_score = 100.0
            if best_min > 0 and row.get('min_rate'):
                price_score = max(0, 100 - ((_safe_float(row['min_rate']) - best_min) / best_min) * 100)
            hist_score = min(100, (_safe_float(row['order_count']) / max_cnt) * 100)
            lead = _safe_float(row.get('avg_lead_days'))
            delivery_score = 100 - (lead / max_lead * 100) if max_lead > 0 and lead > 0 else 50
            total = price_score * 0.45 + hist_score * 0.30 + delivery_score * 0.25
            scored.append({**row, 'score': round(total, 1)})
        scored.sort(key=lambda x: -x.get('score', 0))
        out[ic_v] = scored[:5]
    return out


def _price_comparisons(lines: List[Dict[str, Any]], supplier_code: int, location_code: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for ln in lines:
        ic = ln['itemcode']
        rate = ln['rate']
        last_r, avg_r, sup_r = _item_last_costs(ic, location_code, supplier_code)
        ref = sup_r or last_r or avg_r
        var_pct = None
        severity = 'ok'
        if ref and ref > 0 and rate > 0:
            var_pct = round(((rate - ref) / ref) * 100, 1)
            if abs(var_pct) >= PRICE_VARIANCE_BLOCK_PCT:
                severity = 'high'
            elif abs(var_pct) >= PRICE_VARIANCE_WARN_PCT:
                severity = 'warn'
        out.append({
            'line': ln.get('line'),
            'itemcode': ic,
            'itemname': ln.get('itemname'),
            'current_rate': round(rate, 4),
            'last_purchase_rate': round(last_r, 4) if last_r else None,
            'avg_purchase_rate': round(avg_r, 4) if avg_r else None,
            'supplier_last_rate': round(sup_r, 4) if sup_r else None,
            'reference_rate': round(ref, 4) if ref else None,
            'variance_pct': var_pct,
            'severity': severity,
        })
    return out


def _find_duplicate_pos(
    supplier_code: int,
    lines: List[Dict[str, Any]],
    location_code: int,
    reset_no: int,
    exclude_lpo: int = 0,
    total_amount: float = 0,
) -> List[Dict[str, Any]]:
    if supplier_code <= 0 or not lines:
        return []
    hdr = _detect_table(['LPOHDR', 'lpohdr'])
    dtl = _detect_table(['LPODTL', 'lpodtl'])
    if not hdr or not dtl:
        return []
    h_no = _detect_column(hdr, ['LPONO', 'LPO_NO', 'lpono'])
    h_sup = _detect_column(hdr, ['SUPPLIERCODE', 'SUPPLIER_CODE', 'suppliercode'])
    h_date = _detect_column(hdr, ['LPODATE', 'LPO_DATE', 'lpodate'])
    h_amt = _detect_column(hdr, ['LPOAMOUNT', 'LPO_AMOUNT', 'lpoamount', 'TOTALAMOUNT', 'TOTAL_AMOUNT'])
    h_loc = _detect_column(hdr, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    h_reset = _detect_column(hdr, ['RESETNO', 'RESET_NO', 'resetno'])
    d_lpo = _detect_column(dtl, ['LPONO', 'LPO_NO', 'lpono'])
    d_ic = _detect_column(dtl, ['ITEMCODE', 'ITEM_CODE', 'itemcode'])
    if not all([h_no, h_sup, h_date, d_lpo, d_ic]):
        return []
    cur_items = {ln['itemcode'] for ln in lines}
    where = [f'h.{h_sup} = :sup', f'h.{h_date} >= TRUNC(SYSDATE) - :days']
    params: Dict[str, Any] = {'sup': supplier_code, 'days': DUPLICATE_PO_DAYS, 'loc': location_code, 'rn': reset_no}
    if h_loc:
        where.append(f'h.{h_loc} = :loc')
    if h_reset:
        where.append(f'NVL(h.{h_reset},1) = :rn')
    if exclude_lpo > 0:
        where.append(f'h.{h_no} <> :excl')
        params['excl'] = exclude_lpo
    amt_sel = f', NVL(h.{h_amt},0) AS amt' if h_amt else ', 0 AS amt'
    q = f"""
        SELECT h.{h_no} AS lpono, h.{h_date} AS lpodate{amt_sel}
        FROM {hdr} h
        WHERE {' AND '.join(where)}
        ORDER BY h.{h_date} DESC
        FETCH FIRST 30 ROWS ONLY
    """
    dupes: List[Dict[str, Any]] = []
    try:
        cand_rows = _safe_rows(q, params) or []
    except Exception:
        cand_rows = []
    for cr in cand_rows:
        lpo_no = _safe_int(cr.get('lpono'))
        if lpo_no <= 0:
            continue
        try:
            item_rows = _safe_rows(
                f'SELECT {d_ic} AS ic FROM {dtl} WHERE {d_lpo} = :lpo',
                {'lpo': lpo_no},
            ) or []
        except Exception:
            continue
        other_items = {_safe_int(r.get('ic')) for r in item_rows if _safe_int(r.get('ic')) > 0}
        if not other_items:
            continue
        overlap = len(cur_items & other_items)
        union = len(cur_items | other_items) or 1
        overlap_pct = round(overlap / union * 100, 1)
        cand_amt = _safe_float(cr.get('amt'))
        amt_match = total_amount > 0 and cand_amt > 0 and abs(cand_amt - total_amount) / total_amount <= 0.05
        suspicious = overlap_pct >= 70 or (overlap >= 3 and overlap_pct >= 50) or amt_match
        if not suspicious:
            continue
        d = cr.get('lpodate')
        ds = d.strftime('%Y-%m-%d') if hasattr(d, 'strftime') else str(d)[:10]
        reasons: List[str] = []
        if overlap_pct >= 70:
            reasons.append(f'{overlap_pct}% item overlap')
        elif overlap >= 3:
            reasons.append(f'{overlap} shared items')
        if amt_match:
            reasons.append('similar total amount')
        dupes.append({
            'lpono': lpo_no,
            'lpodate': ds,
            'overlap_pct': overlap_pct,
            'shared_items': overlap,
            'amount': round(cand_amt, 2),
            'reason': '; '.join(reasons),
            'severity': 'high' if overlap_pct >= 85 or amt_match else 'warn',
        })
    return dupes[:10]


def _predict_delivery(supplier_code: int, location_code: int) -> Dict[str, Any]:
    hdr = _detect_table(['RECEIPTHDR', 'receipthdr'])
    lpo_hdr = _detect_table(['LPOHDR', 'lpohdr'])
    if not hdr or not lpo_hdr or supplier_code <= 0:
        return {'supplier_code': supplier_code, 'avg_lead_days': None, 'predicted_date': None, 'sample_size': 0}
    h_sup = _detect_column(hdr, ['SUPPLIERCODE', 'SUPPLIER_CODE', 'suppliercode'])
    h_lpo = _detect_column(hdr, ['LPONO', 'LPO_NO', 'lpono'])
    h_loc = _detect_column(hdr, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    h_date = _detect_column(hdr, ['RECEIPTDATE', 'RECEIPT_DATE', 'receiptdate'])
    l_no = _detect_column(lpo_hdr, ['LPONO', 'LPO_NO', 'lpono'])
    l_date = _detect_column(lpo_hdr, ['LPODATE', 'LPO_DATE', 'lpodate'])
    l_loc = _detect_column(lpo_hdr, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    if not all([h_sup, h_lpo, h_date, l_no, l_date]):
        return {'supplier_code': supplier_code, 'avg_lead_days': None, 'predicted_date': None, 'sample_size': 0}
    join = [f'h.{h_lpo} = l.{l_no}', f'h.{h_sup} = :sup', f'h.{h_lpo} > 0']
    params: Dict[str, Any] = {'sup': supplier_code, 'loc': location_code}
    if h_loc and l_loc:
        join.append(f'h.{h_loc} = l.{l_loc}')
        join.append(f'h.{h_loc} = :loc')
    q = f"""
        SELECT AVG(h.{h_date} - l.{l_date}) AS avg_lead, COUNT(*) AS n
        FROM {hdr} h
        INNER JOIN {lpo_hdr} l ON {' AND '.join(join)}
        WHERE h.{h_date} >= TRUNC(SYSDATE) - 365
    """
    avg_lead = None
    n = 0
    try:
        rows = _safe_rows(q, params) or []
        if rows:
            avg_lead = _safe_float(rows[0].get('avg_lead'))
            n = _safe_int(rows[0].get('n'))
            if avg_lead <= 0:
                avg_lead = None
    except Exception:
        pass
    predicted = None
    if avg_lead and avg_lead > 0:
        predicted = (date.today() + timedelta(days=int(round(avg_lead)))).isoformat()
    return {
        'supplier_code': supplier_code,
        'avg_lead_days': round(avg_lead, 1) if avg_lead else None,
        'predicted_date': predicted,
        'sample_size': n,
    }


def validate_po_pre_approval(
    payload: Dict[str, Any],
    location_code: int,
    reset_no: int = 1,
) -> Dict[str, Any]:
    """Validate PO before approval — rule-based risk score."""
    passed: List[str] = []
    warnings: List[str] = []
    errors: List[str] = []
    suggestions: List[str] = []
    line_issues: List[Dict[str, Any]] = []

    supplier_code = _safe_int(payload.get('suppliercode') or payload.get('supplier_code'))
    exclude_lpo = _safe_int(payload.get('lpono') or payload.get('lpo_no'))
    lines = _parse_po_lines(payload.get('lines') or [])
    approval_save_as = str(payload.get('approval_save_as') or '').strip().lower()
    wants_approved = approval_save_as == 'approved'

    if wants_approved and supplier_code <= 0:
        errors.append('Supplier is required before approval.')
    if wants_approved and not lines:
        errors.append('Add at least one line before approval.')
    if not payload.get('lpodate'):
        warnings.append('LPO date is missing.')

    total = sum(ln.get('amount') or ln.get('rate', 0) * ln.get('quantity', 0) for ln in lines)
    dupes = _find_duplicate_pos(supplier_code, lines, location_code, reset_no, exclude_lpo, total)
    for d in dupes:
        msg = f'Possible duplicate PO #{d["lpono"]} ({d["lpodate"]}): {d["reason"]}.'
        if d.get('severity') == 'high':
            warnings.append(msg)
        else:
            warnings.append(msg)

    master = _item_master_batch([ln['itemcode'] for ln in lines], location_code)
    price_rows = _price_comparisons(lines, supplier_code, location_code)

    for ln in lines:
        idx = ln.get('line')
        ic = ln['itemcode']
        if ln['quantity'] <= 0:
            errors.append(f'Line {idx}: quantity must be positive.')
        if ln['rate'] <= 0 and not payload.get('allow_zero_rate'):
            warnings.append(f'Line {idx}: zero rate on item {ic}.')
        m = master.get(ic) or {}
        reorder = _safe_float(m.get('reorder_level'))
        stock = _safe_float(m.get('current_stock'))
        avg_q = _item_avg_grn_qty(ic, location_code)
        if avg_q and ln['baseqty'] > avg_q * QTY_OVER_REORDER_RATIO:
            warnings.append(f'Line {idx}: qty {ln["baseqty"]:.3g} is {ln["baseqty"]/avg_q:.1f}× typical PO qty ({avg_q:.3g}).')
        if reorder > 0 and ln['baseqty'] > reorder * QTY_OVER_REORDER_RATIO:
            warnings.append(f'Line {idx}: qty exceeds {QTY_OVER_REORDER_RATIO}× reorder level ({reorder:.3g}).')

    for pr in price_rows:
        if pr.get('severity') == 'high':
            warnings.append(
                f'Line {pr["line"]}: rate {pr["current_rate"]} vs ref {pr["reference_rate"]} ({pr["variance_pct"]:+.1f}%).'
            )
            line_issues.append({'line': pr['line'], 'itemcode': pr['itemcode'], 'code': 'price_variance', 'severity': 'warning', 'variance_pct': pr['variance_pct']})
        elif pr.get('severity') == 'warn':
            warnings.append(
                f'Line {pr["line"]}: price {pr["variance_pct"]:+.1f}% vs last purchase.'
            )

    if supplier_code > 0 and lines:
        passed.append(f'{len(lines)} line(s) ready for review.')
    if not dupes:
        passed.append('No duplicate PO patterns detected in recent history.')

    risk_score = min(100, len(errors) * 35 + len(warnings) * 8 + len([d for d in dupes if d.get('severity') == 'high']) * 15)
    return {
        'success': True,
        'risk_score': risk_score,
        'risk_level': _risk_level_po(risk_score),
        'confidence': max(0, 100 - len(errors) * 30 - len(warnings) * 6),
        'blocking': len(errors) > 0,
        'passed': passed,
        'warnings': warnings,
        'errors': errors,
        'suggestions': suggestions,
        'line_issues': line_issues,
        'duplicates': dupes,
        'price_comparisons': price_rows,
        'actions': {
            'can_approve': len(errors) == 0,
            'can_save_draft': True,
            'needs_review': risk_score > 30,
        },
    }


def build_po_insights(
    payload: Dict[str, Any],
    location_code: int,
    reset_no: int = 1,
) -> Dict[str, Any]:
    """Full structured insights for the PO AI panel."""
    supplier_code = _safe_int(payload.get('suppliercode') or payload.get('supplier_code'))
    exclude_lpo = _safe_int(payload.get('lpono') or payload.get('lpo_no'))
    lines = _parse_po_lines(payload.get('lines') or [])
    item_codes = [ln['itemcode'] for ln in lines]
    total = sum(ln.get('amount') or ln.get('rate', 0) * ln.get('quantity', 0) for ln in lines)

    reorder = _compute_reorder_suggestions(item_codes, location_code, reset_no, exclude_lpo) if item_codes else []
    supplier_recs = _supplier_stats_for_items(item_codes, location_code) if item_codes else {}
    price_cmp = _price_comparisons(lines, supplier_code, location_code) if lines else []
    dupes = _find_duplicate_pos(supplier_code, lines, location_code, reset_no, exclude_lpo, total) if lines else []
    delivery = _predict_delivery(supplier_code, location_code) if supplier_code > 0 else {}
    validation = validate_po_pre_approval(payload, location_code, reset_no)

    line_insights: List[Dict[str, Any]] = []
    for ln in lines:
        ic = ln['itemcode']
        rec_suppliers = supplier_recs.get(ic) or []
        best_sup = rec_suppliers[0] if rec_suppliers else None
        reorder_row = next((r for r in reorder if r['itemcode'] == ic), None)
        price_row = next((p for p in price_cmp if p['itemcode'] == ic), None)
        line_insights.append({
            'line': ln.get('line'),
            'itemcode': ic,
            'itemname': ln.get('itemname'),
            'quantity': ln.get('quantity'),
            'rate': ln.get('rate'),
            'reorder': reorder_row,
            'best_supplier': best_sup,
            'price': price_row,
            'alt_suppliers': rec_suppliers[1:3] if len(rec_suppliers) > 1 else [],
        })

    return {
        'success': True,
        'summary': {
            'line_count': len(lines),
            'total_amount': round(total, 2),
            'supplier_code': supplier_code,
            'risk_score': validation.get('risk_score'),
            'risk_level': validation.get('risk_level'),
        },
        'reorder_suggestions': reorder,
        'supplier_recommendations': supplier_recs,
        'price_comparisons': price_cmp,
        'duplicate_pos': dupes,
        'delivery_prediction': delivery,
        'validation': validation,
        'line_insights': line_insights,
    }


def generate_po_ai_narrative(context: Dict[str, Any]) -> str:
    """OpenAI narrative summary for insights panel."""
    api_key = (os.environ.get('OPENAI_API_KEY') or '').strip()
    if not api_key:
        return ''
    model = (os.environ.get('OPENAI_MODEL') or 'gpt-4o-mini').strip()
    blob = json.dumps(context, default=str, ensure_ascii=False)
    if len(blob) > 24000:
        blob = blob[:24000] + '…'
    sys_prompt = (
        'You are a senior ERP purchasing analyst. Given JSON with reorder suggestions, supplier scores, '
        'price comparisons, duplicate PO flags, delivery prediction, and validation results, write concise markdown '
        'for a buyer on the Purchase Order screen. Use sections: ### Overview, ### Reorder & stock, ### Supplier & price, '
        '### Risks & duplicates, ### Delivery, ### Recommendations. Be specific with numbers from JSON only; '
        'do not invent data. Keep under 450 words.'
    )
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, timeout=60.0)
        completion = client.chat.completions.create(
            model=model,
            temperature=0.25,
            messages=[
                {'role': 'system', 'content': sys_prompt},
                {'role': 'user', 'content': blob},
            ],
            max_tokens=900,
        )
        return (completion.choices[0].message.content or '').strip()
    except Exception:
        return ''


def _lookup_item_for_nl(location_code: int, query: str) -> Optional[Dict[str, Any]]:
    q = (query or '').strip()
    if not q:
        return None
    im = _detect_table(['ITEMMASTER', 'itemmaster'])
    if not im:
        return None
    ic = _detect_column(im, ['ITEMCODE', 'ITEM_CODE', 'itemcode'])
    nm = _detect_column(im, ['ITEMNAME', 'ITEM_NAME', 'itemname'])
    bc = _detect_column(im, ['MANUFACTURERID', 'manufacturerid', 'RAWABICODE', 'rawabicode'])
    loc = _detect_column(im, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    uom = _detect_column(im, ['BASEUOM', 'BASE_UOM', 'baseuom'])
    cost = _detect_column(im, ['COSTPRICE', 'COST_PRICE', 'costprice'])
    if not ic:
        return None
    params: Dict[str, Any] = {'loc': location_code}
    if q.isdigit():
        w = [f'{ic} = :qnum']
        params['qnum'] = int(q)
    else:
        w = []
        if bc:
            w.append(f'UPPER(TRIM(TO_CHAR({bc}))) = UPPER(:q)')
            params['q'] = q
        if nm and not w:
            w.append(f'UPPER({nm}) LIKE UPPER(:likeq)')
            params['likeq'] = f'%{q[:40]}%'
        if not w:
            return None
    if loc:
        w.append(f'{loc} = :loc')
    sel = [f'{ic} AS itemcode']
    sel.append(f'{nm} AS itemname' if nm else 'NULL AS itemname')
    sel.append(f'{bc} AS barcode' if bc else 'NULL AS barcode')
    sel.append(f'{uom} AS baseuom' if uom else "'NOS' AS baseuom")
    sel.append(f'NVL({cost},0) AS costprice' if cost else '0 AS costprice')
    rows = _safe_rows(f"SELECT {', '.join(sel)} FROM {im} WHERE {' AND '.join(w)} AND ROWNUM = 1", params) or []
    return rows[0] if rows else None


def parse_natural_language_po(text: str, location_code: int, supplier_code: int = 0) -> Dict[str, Any]:
    """Parse natural language into PO lines via OpenAI + item master lookup."""
    api_key = (os.environ.get('OPENAI_API_KEY') or '').strip()
    if not api_key:
        return {'success': False, 'error': 'OPENAI_API_KEY is not configured.'}
    raw = (text or '').strip()
    if len(raw) < 8:
        return {'success': False, 'error': 'Enter a longer description (e.g. "Order 50 boxes of item 1234 from usual supplier").'}
    model = (os.environ.get('OPENAI_MODEL') or 'gpt-4o-mini').strip()
    sys_prompt = (
        'Extract a purchase order intent from user text. Return JSON only:\n'
        '{"supplier_hint":"","remarks":"","lines":[{"item_code":"","barcode":"","description":"","quantity":0,"uom":"NOS","rate":null}]}\n'
        'item_code if mentioned as number; quantity as number; rate only if explicitly stated.'
    )
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, timeout=60.0)
        completion = client.chat.completions.create(
            model=model,
            temperature=0.1,
            response_format={'type': 'json_object'},
            messages=[
                {'role': 'system', 'content': sys_prompt},
                {'role': 'user', 'content': raw[:8000]},
            ],
            max_tokens=1200,
        )
        content = (completion.choices[0].message.content or '').strip()
        parsed = json.loads(content)
    except json.JSONDecodeError as e:
        return {'success': False, 'error': f'AI returned invalid JSON: {e}'}
    except Exception as e:
        err = str(e)
        if 'api key' in err.lower():
            return {'success': False, 'error': 'OPENAI_API_KEY is not configured.'}
        return {'success': False, 'error': err[:400]}

    ai_lines = parsed.get('lines') if isinstance(parsed.get('lines'), list) else []
    matched: List[Dict[str, Any]] = []
    unmatched: List[Dict[str, Any]] = []
    for i, al in enumerate(ai_lines):
        if not isinstance(al, dict):
            continue
        ic_raw = str(al.get('item_code') or al.get('itemcode') or '').strip()
        bc = str(al.get('barcode') or '').strip()
        desc = str(al.get('description') or al.get('item_name') or '').strip()
        qty = _safe_float(al.get('quantity'), 1.0)
        if qty <= 0:
            qty = 1.0
        uom = str(al.get('uom') or 'NOS').strip() or 'NOS'
        rate = al.get('rate')
        rate_f = _safe_float(rate) if rate not in (None, '') else None
        lookup_q = ic_raw or bc or desc
        item = _lookup_item_for_nl(location_code, lookup_q)
        if not item and bc:
            item = _lookup_item_for_nl(location_code, bc)
        if not item and desc:
            item = _lookup_item_for_nl(location_code, desc[:60])
        row = {
            'ai_index': i,
            'ai': al,
            'qty': qty,
            'uom': uom,
            'rate': rate_f if rate_f and rate_f > 0 else _safe_float(item.get('costprice') if item else 0),
            'matched': bool(item),
            'item': item,
        }
        if item:
            matched.append(row)
        else:
            unmatched.append(row)

    return {
        'success': True,
        'supplier_hint': str(parsed.get('supplier_hint') or '').strip(),
        'remarks': str(parsed.get('remarks') or '').strip(),
        'matched': matched,
        'unmatched': unmatched,
        'parsed': parsed,
    }
