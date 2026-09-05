"""Inventory report helpers — warehouse summary and related aggregates."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from db import (
    WAREHOUSE_STOCK_TABLE,
    _detect_column,
    _detect_table,
    _fetch_rows,
    _safe_rows,
    ensure_warehouse_stock_table,
    get_accounts_payable_summary,
    get_warehouse_stock_for_branch,
    list_warehouse_master_rows,
    resolve_warehouse_master_table,
)


def get_supplier_balance_report_rows(*, search: str = '', min_balance: float = 0.0) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Supplier outstanding payables for inventory Supplier Balance report."""
    rows = get_accounts_payable_summary() or []
    q = (search or '').strip().upper()
    out: List[Dict[str, Any]] = []
    total = 0.0
    with_balance = 0
    for r in rows:
        bal = float(r.get('payable_balance') or 0)
        if bal <= float(min_balance or 0) - 1e-09:
            continue
        code = str(r.get('suppliercode') or '').strip()
        name = str(r.get('suppliername') or '').strip()
        if q and q not in code.upper() and q not in name.upper():
            continue
        row = dict(r)
        row['payable_balance'] = round(bal, 3)
        out.append(row)
        total += bal
        if bal > 0:
            with_balance += 1
    out.sort(key=lambda x: (-float(x.get('payable_balance') or 0), str(x.get('suppliername') or '')))
    summary = {
        'supplier_count': len(out),
        'total_outstanding': round(total, 3),
        'with_balance_count': with_balance,
    }
    return out, summary


def get_warehouse_summary_report_rows(location_code: int, *, search: str = '') -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Per-warehouse on-hand totals for branch ``location_code``."""
    try:
        loc = int(location_code)
    except (TypeError, ValueError):
        return [], {}
    if not ensure_warehouse_stock_table():
        return _warehouse_summary_from_master_only(loc, search=search)

    wm_tbl = resolve_warehouse_master_table()
    im_tbl = _detect_table(['ITEMMASTER', 'itemmaster', 'ITEM_MASTER'])
    if wm_tbl:
        rows = _warehouse_summary_sql(loc, wm_tbl, im_tbl)
        if rows:
            return _filter_warehouse_summary_rows(rows, search)

    stock_rows = get_warehouse_stock_for_branch(loc, include_zero=False, limit=50000) or []
    wh_names = _warehouse_name_map(loc)
    agg: Dict[int, Dict[str, Any]] = defaultdict(lambda: {
        'warehouse_id': 0,
        'warehouse_code': '',
        'warehouse_name': '',
        'item_count': 0,
        'total_qty': 0.0,
        'stock_value': 0.0,
        '_items': set(),
    })
    item_codes: set[int] = set()
    for r in stock_rows:
        try:
            wid = int(r.get('warehouse_id') or 0)
        except (TypeError, ValueError):
            continue
        if wid <= 0:
            continue
        try:
            ic = int(r.get('itemcode') or 0)
        except (TypeError, ValueError):
            ic = 0
        qty = float(r.get('qty') or 0)
        bucket = agg[wid]
        bucket['warehouse_id'] = wid
        bucket['warehouse_code'] = str(r.get('warehouse_code') or wh_names.get(wid, {}).get('code') or wid)
        bucket['warehouse_name'] = str(wh_names.get(wid, {}).get('name') or '')
        bucket['total_qty'] += qty
        if ic > 0:
            bucket['_items'].add(ic)
            item_codes.add(ic)
    costs = _item_cost_map(loc, item_codes, im_tbl)
    for wid, bucket in agg.items():
        bucket['item_count'] = len(bucket['_items'])
        val = 0.0
        for ic in bucket['_items']:
            for r in stock_rows:
                if int(r.get('warehouse_id') or 0) != wid:
                    continue
                if int(r.get('itemcode') or 0) != ic:
                    continue
                val += float(r.get('qty') or 0) * float(costs.get(ic, 0))
        bucket['stock_value'] = round(val, 3)
        bucket['total_qty'] = round(float(bucket['total_qty'] or 0), 4)
        bucket.pop('_items', None)
    rows_out = sorted(agg.values(), key=lambda x: (str(x.get('warehouse_code') or ''), int(x.get('warehouse_id') or 0)))
    return _filter_warehouse_summary_rows(rows_out, search)


def _warehouse_summary_from_master_only(location_code: int, *, search: str = '') -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for wh in list_warehouse_master_rows(active_only=True) or []:
        try:
            loc = int(wh.get('locationcode') or wh.get('LOCATIONCODE') or 0)
        except (TypeError, ValueError):
            loc = 0
        if loc != int(location_code):
            continue
        try:
            wid = int(wh.get('warehouse_id') or wh.get('WAREHOUSE_ID') or 0)
        except (TypeError, ValueError):
            wid = 0
        rows.append({
            'warehouse_id': wid,
            'warehouse_code': str(wh.get('warehouse_code') or wh.get('WAREHOUSE_CODE') or '').strip(),
            'warehouse_name': str(wh.get('warehouse_name') or wh.get('WAREHOUSE_NAME') or wh.get('name') or '').strip(),
            'item_count': 0,
            'total_qty': 0.0,
            'stock_value': 0.0,
        })
    return _filter_warehouse_summary_rows(rows, search)


def _warehouse_summary_sql(location_code: int, wm_tbl: str, im_tbl: Optional[str]) -> List[Dict[str, Any]]:
    wm_id = _detect_column(wm_tbl, ['WAREHOUSE_ID', 'warehouse_id']) or 'WAREHOUSE_ID'
    wm_code = _detect_column(wm_tbl, ['WAREHOUSE_CODE', 'warehouse_code']) or 'WAREHOUSE_CODE'
    wm_name = _detect_column(wm_tbl, ['WAREHOUSE_NAME', 'warehouse_name', 'NAME', 'name'])
    wm_loc = _detect_column(wm_tbl, ['LOCATIONCODE', 'locationcode']) or 'LOCATIONCODE'
    cost_expr = '0'
    im_join = ''
    if im_tbl:
        im_code = _detect_column(im_tbl, ['ITEMCODE', 'itemcode']) or 'ITEMCODE'
        im_loc = _detect_column(im_tbl, ['LOCATIONCODE', 'locationcode'])
        im_avg = _detect_column(im_tbl, ['AVERAGECOST', 'averagecost', 'AVGCOST'])
        im_cost = _detect_column(im_tbl, ['COSTPRICE', 'costprice', 'COST'])
        if im_avg or im_cost:
            cost_expr = f'NVL(im.{im_avg or im_cost}, NVL(im.{im_cost or im_avg}, 0))'
            im_join = f' LEFT JOIN {im_tbl} im ON im.{im_code} = ws.ITEMCODE'
            if im_loc:
                im_join += f' AND im.{im_loc} = ws.LOCATIONCODE'
    name_sel = f'wm.{wm_name} AS warehouse_name' if wm_name else "'' AS warehouse_name"
    q = f"""
        SELECT ws.WAREHOUSE_ID AS warehouse_id,
               TRIM(wm.{wm_code}) AS warehouse_code,
               {name_sel},
               COUNT(DISTINCT ws.ITEMCODE) AS item_count,
               SUM(NVL(ws.QTY, 0)) AS total_qty,
               SUM(NVL(ws.QTY, 0) * {cost_expr}) AS stock_value
        FROM {WAREHOUSE_STOCK_TABLE} ws
        INNER JOIN {wm_tbl} wm ON wm.{wm_id} = ws.WAREHOUSE_ID AND wm.{wm_loc} = :loc
        {im_join}
        WHERE ws.LOCATIONCODE = :loc AND NVL(ws.QTY, 0) <> 0
        GROUP BY ws.WAREHOUSE_ID, TRIM(wm.{wm_code}){f', wm.{wm_name}' if wm_name else ''}
        ORDER BY TRIM(wm.{wm_code})
    """
    try:
        _, rows = _fetch_rows(q, {'loc': int(location_code)})
        out: List[Dict[str, Any]] = []
        for r in rows or []:
            out.append({
                'warehouse_id': int(r.get('warehouse_id') or 0),
                'warehouse_code': str(r.get('warehouse_code') or '').strip(),
                'warehouse_name': str(r.get('warehouse_name') or '').strip(),
                'item_count': int(r.get('item_count') or 0),
                'total_qty': round(float(r.get('total_qty') or 0), 4),
                'stock_value': round(float(r.get('stock_value') or 0), 3),
            })
        return out
    except Exception:
        return []


def _warehouse_name_map(location_code: int) -> Dict[int, Dict[str, str]]:
    out: Dict[int, Dict[str, str]] = {}
    for wh in list_warehouse_master_rows(active_only=True) or []:
        try:
            loc = int(wh.get('locationcode') or wh.get('LOCATIONCODE') or 0)
            wid = int(wh.get('warehouse_id') or wh.get('WAREHOUSE_ID') or 0)
        except (TypeError, ValueError):
            continue
        if loc != int(location_code) or wid <= 0:
            continue
        out[wid] = {
            'code': str(wh.get('warehouse_code') or wh.get('WAREHOUSE_CODE') or '').strip(),
            'name': str(wh.get('warehouse_name') or wh.get('WAREHOUSE_NAME') or wh.get('name') or '').strip(),
        }
    return out


def _item_cost_map(location_code: int, item_codes: set[int], im_tbl: Optional[str]) -> Dict[int, float]:
    if not im_tbl or not item_codes:
        return {}
    im_code = _detect_column(im_tbl, ['ITEMCODE', 'itemcode'])
    im_loc = _detect_column(im_tbl, ['LOCATIONCODE', 'locationcode'])
    im_avg = _detect_column(im_tbl, ['AVERAGECOST', 'averagecost'])
    im_cost = _detect_column(im_tbl, ['COSTPRICE', 'costprice', 'COST'])
    if not im_code:
        return {}
    in_list = ', '.join(str(i) for i in sorted(item_codes))
    cost_col = im_avg or im_cost
    if not cost_col:
        return {}
    where = f'{im_code} IN ({in_list})'
    params: Dict[str, Any] = {}
    if im_loc:
        where += f' AND {im_loc} = :loc'
        params['loc'] = int(location_code)
    rows = _safe_rows(f'SELECT {im_code} AS ic, NVL({cost_col}, 0) AS cost FROM {im_tbl} WHERE {where}', params)
    out: Dict[int, float] = {}
    for r in rows or []:
        try:
            out[int(r.get('ic') or 0)] = float(r.get('cost') or 0)
        except (TypeError, ValueError):
            pass
    return out


def _filter_warehouse_summary_rows(rows: List[Dict[str, Any]], search: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    q = (search or '').strip().upper()
    filtered = rows
    if q:
        filtered = [
            r for r in rows
            if q in str(r.get('warehouse_code') or '').upper()
            or q in str(r.get('warehouse_name') or '').upper()
        ]
    total_qty = sum(float(r.get('total_qty') or 0) for r in filtered)
    total_value = sum(float(r.get('stock_value') or 0) for r in filtered)
    total_items = sum(int(r.get('item_count') or 0) for r in filtered)
    summary = {
        'warehouse_count': len(filtered),
        'total_qty': round(total_qty, 4),
        'total_value': round(total_value, 3),
        'total_item_lines': total_items,
    }
    return filtered, summary
