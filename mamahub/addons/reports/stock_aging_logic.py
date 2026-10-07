"""Stock Aging Analysis — queries, KPIs, charts, drill-down, AI insights (tenant DB)."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from db import (
    DATABASES,
    _bill_history_return_predicate,
    _detect_column,
    _detect_table,
    _get_table_columns,
    _safe_rows,
    get_location_info_by_dbkey,
    get_locations_list,
    itemjournal_warehouse_code_column,
    resolve_warehouse_master_table,
)

logger = logging.getLogger(__name__)

_SALES_RESET_NO = 1
_GRN_RESET_NO = 1

DEFAULT_BUCKETS: List[Dict[str, Any]] = [
    {'id': 'b1', 'label': '0-30 Days', 'min_days': 0, 'max_days': 30},
    {'id': 'b2', 'label': '31-60 Days', 'min_days': 31, 'max_days': 60},
    {'id': 'b3', 'label': '61-90 Days', 'min_days': 61, 'max_days': 90},
    {'id': 'b4', 'label': '91-180 Days', 'min_days': 91, 'max_days': 180},
    {'id': 'b5', 'label': '181-365 Days', 'min_days': 181, 'max_days': 365},
    {'id': 'b6', 'label': 'Above 365 Days', 'min_days': 366, 'max_days': None},
]


def parse_aging_buckets(raw: Optional[str]) -> List[Dict[str, Any]]:
    if not raw:
        return list(DEFAULT_BUCKETS)
    try:
        data = json.loads(raw)
        if not isinstance(data, list) or not data:
            return list(DEFAULT_BUCKETS)
        out: List[Dict[str, Any]] = []
        for i, b in enumerate(data):
            if not isinstance(b, dict):
                continue
            label = str(b.get('label') or f'Bucket {i + 1}').strip()
            try:
                mn = int(b.get('min_days', 0))
            except (TypeError, ValueError):
                mn = 0
            mx = b.get('max_days')
            if mx is not None and str(mx).strip() != '':
                try:
                    mx = int(mx)
                except (TypeError, ValueError):
                    mx = None
            else:
                mx = None
            out.append({'id': str(b.get('id') or f'custom_{i}'), 'label': label, 'min_days': mn, 'max_days': mx})
        return out or list(DEFAULT_BUCKETS)
    except Exception:
        return list(DEFAULT_BUCKETS)


def bucket_for_age(age_days: int, buckets: List[Dict[str, Any]]) -> str:
    for b in buckets:
        mn = int(b.get('min_days') or 0)
        mx = b.get('max_days')
        if mx is None:
            if age_days >= mn:
                return str(b.get('label') or '')
        elif mn <= age_days <= int(mx):
            return str(b.get('label') or '')
    return 'Unclassified'


def classify_movement_status(
    *,
    current_stock: float,
    age_days: int,
    last_sales_date: Optional[str],
    slow_days: int = 90,
    non_move_days: int = 180,
    dead_days: int = 365,
) -> str:
    if current_stock <= 0.0001:
        return 'Inactive'
    if age_days >= dead_days:
        return 'Dead Stock'
    if age_days >= non_move_days or not last_sales_date:
        return 'Non Moving'
    if age_days >= slow_days:
        return 'Slow Moving'
    return 'Fast Moving'


def _parse_date(s: str) -> Optional[datetime]:
    s = (s or '').strip()
    if not s:
        return None
    for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y'):
        try:
            return datetime.strptime(s[:10], fmt)
        except ValueError:
            continue
    return None


def _age_days(as_on: str, ref_date: Optional[str]) -> int:
    a = _parse_date(as_on)
    r = _parse_date(ref_date or '')
    if not a:
        a = datetime.now()
    if not r:
        return 9999
    return max(0, (a.date() - r.date()).days)


def _detect_journal_table() -> Optional[str]:
    return _detect_table(['ITEMJOURNEL', 'itemjournel', 'ITEMJOURNAL', 'itemjournal'])


def _journal_last_movement_subquery() -> Optional[str]:
    jtbl = _detect_journal_table()
    if not jtbl:
        return None
    jcols = {str(c).upper() for c in (_get_table_columns(jtbl) or [])}
    j_item = 'ITEMCODE' if 'ITEMCODE' in jcols else None
    j_loc = 'LOCATIONCODE' if 'LOCATIONCODE' in jcols else None
    j_dt = next((c for c in ('CREATEDDATE', 'JOURNALDATE', 'TRANSDATE', 'DATE') if c in jcols), None)
    if not j_item or not j_loc or not j_dt:
        return None
    return (
        f"SELECT j.{j_item} AS ic, MAX(TRUNC(j.{j_dt})) AS dt "
        f"FROM {jtbl} j WHERE j.{j_loc} = :sa_loc GROUP BY j.{j_item}"
    )


def _sales_last_date_subquery() -> Optional[str]:
    ht = _detect_table(['BILLHDRHISTORY', 'billhdrhistory']) or _detect_table(['BILLHDR', 'billhdr'])
    dt = _detect_table(['BILLDTLHISTORY', 'billdtlhistory']) or _detect_table(['BILLDTL', 'billdtl'])
    if not ht or not dt:
        return None
    h_no = _detect_column(ht, ['BILLNO', 'billno'])
    h_date = _detect_column(ht, ['BILLDATE', 'billdate'])
    h_loc = _detect_column(ht, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    h_reset = _detect_column(ht, ['RESETNO', 'RESET_NO', 'resetno'])
    h_del = _detect_column(ht, ['DELFLAG', 'DEL_FLAG', 'delflag'])
    h_status = _detect_column(ht, ['BILLSTATUS', 'BILL_STATUS', 'billstatus'])
    d_bill = _detect_column(dt, ['BILLNO', 'billno'])
    d_item = _detect_column(dt, ['ITEMCODE', 'ITEM_CODE', 'itemcode'])
    d_loc = _detect_column(dt, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    d_reset = _detect_column(dt, ['RESETNO', 'RESET_NO', 'resetno'])
    d_qty = _detect_column(dt, ['QUANTITY', 'quantity'])
    if not h_no or not h_date or not d_bill or not d_item:
        return None
    on_parts = [f'h.{h_no} = d.{d_bill}']
    if h_loc and d_loc:
        on_parts.append(f'h.{h_loc} = d.{d_loc}')
    if h_reset and d_reset:
        on_parts.append(f'h.{h_reset} = d.{d_reset}')
    where = []
    if h_loc:
        where.append(f'h.{h_loc} = :sa_loc')
    if h_reset:
        where.append(f'h.{h_reset} = :sa_rn_bill')
    if h_del:
        where.append(f"NVL(h.{h_del}, 'N') <> 'Y'")
    if h_status:
        where.append(f"(h.{h_status} IS NULL OR UPPER(TRIM(h.{h_status})) <> 'V')")
    if d_qty:
        where.append(f'NVL(d.{d_qty}, 0) >= 0')
    else:
        where.append(_bill_history_return_predicate('h', ht, sales_return=False))
    return (
        f"SELECT d.{d_item} AS ic, MAX(TRUNC(h.{h_date})) AS dt "
        f"FROM {ht} h INNER JOIN {dt} d ON {' AND '.join(on_parts)} "
        f"WHERE {' AND '.join(where)} GROUP BY d.{d_item}"
    )


def _receipt_last_date_subquery() -> Optional[str]:
    rh = _detect_table(['RECEIPTHDR', 'receipthdr'])
    rd = _detect_table(['RECEIPTDTL', 'receiptdtl'])
    if not rh or not rd:
        return None
    h_loc = _detect_column(rh, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    h_no = _detect_column(rh, ['RECEIPTNO', 'RECEIPT_NO', 'receiptno'])
    h_date = _detect_column(rh, ['RECEIPTDATE', 'RECEIPT_DATE', 'receiptdate', 'CREATEDDATE'])
    h_reset = _detect_column(rh, ['RESETNO', 'RESET_NO', 'resetno'])
    h_del = _detect_column(rh, ['DELFLAG', 'DEL_FLAG', 'delflag'])
    d_no = _detect_column(rd, ['RECEIPTNO', 'RECEIPT_NO', 'receiptno'])
    d_item = _detect_column(rd, ['ITEMCODE', 'ITEM_CODE', 'itemcode'])
    d_loc = _detect_column(rd, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    if not h_no or not h_date or not d_no or not d_item:
        return None
    join_cond = [f'd.{d_no} = h.{h_no}']
    if h_loc and d_loc:
        join_cond.append(f'd.{d_loc} = h.{h_loc}')
    where = []
    if h_loc:
        where.append(f'h.{h_loc} = :sa_loc')
    if h_reset:
        where.append(f'h.{h_reset} = :sa_rn_rcpt')
    if h_del:
        where.append(f"NVL(h.{h_del}, 'N') <> 'Y'")
    return (
        f"SELECT d.{d_item} AS ic, MAX(TRUNC(h.{h_date})) AS dt "
        f"FROM {rd} d INNER JOIN {rh} h ON {' AND '.join(join_cond)} "
        f"WHERE {' AND '.join(where)} GROUP BY d.{d_item}"
    )


def get_stock_aging_filter_options(location_code: Optional[int] = None) -> Dict[str, Any]:
    loc = location_code
    companies = [{'code': k, 'name': k} for k in sorted(DATABASES.keys())]
    branches = get_locations_list() or []
    warehouses: List[Dict[str, Any]] = []
    wh_tbl = resolve_warehouse_master_table()
    if wh_tbl and loc is not None:
        wh_loc = _detect_column(wh_tbl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
        wh_id = _detect_column(wh_tbl, ['WAREHOUSE_ID', 'warehouse_id'])
        wh_code = _detect_column(wh_tbl, ['WAREHOUSE_CODE', 'warehouse_code'])
        wh_name = _detect_column(wh_tbl, ['WAREHOUSE_NAME', 'warehouse_name'])
        if wh_loc and wh_code:
            cols = [f'{wh_code} AS warehouse_code']
            if wh_id:
                cols.append(f'{wh_id} AS warehouse_id')
            if wh_name:
                cols.append(f'{wh_name} AS warehouse_name')
            try:
                warehouses = _safe_rows(
                    f"SELECT {', '.join(cols)} FROM {wh_tbl} WHERE {wh_loc} = :loc ORDER BY {wh_code}",
                    {'loc': int(loc)},
                ) or []
            except Exception:
                warehouses = []
    im = _detect_table(['ITEMMASTER', 'itemmaster'])
    categories: List[Dict[str, Any]] = []
    brands: List[Dict[str, Any]] = []
    suppliers: List[Dict[str, Any]] = []
    if im:
        icat = _detect_column(im, ['CATEGORYCODE', 'categorycode'])
        iloc = _detect_column(im, ['LOCATIONCODE', 'locationcode'])
        ibrand = _detect_column(im, ['BRANDCODE', 'brandcode'])
        isup = _detect_column(im, ['SUPCODE', 'SUPPLIERCODE', 'suppliercode'])
        params: Dict[str, Any] = {}
        loc_sql = ''
        if iloc and loc is not None:
            loc_sql = f' AND im.{iloc} = :loc '
            params['loc'] = int(loc)
        if icat:
            cat = _detect_table(['CATEGORY', 'category'])
            cat_code = _detect_column(cat, ['CODE', 'CATEGORYCODE']) if cat else None
            cat_name = _detect_column(cat, ['NAME', 'CATEGORYNAME']) if cat else None
            join = f'LEFT JOIN {cat} c ON c.{cat_code} = im.{icat}' if cat and cat_code and cat_name else ''
            name_expr = f"NVL(c.{cat_name}, '')" if cat and cat_name else "''"
            try:
                categories = _safe_rows(
                    f"SELECT DISTINCT im.{icat} AS code, {name_expr} AS name FROM {im} im {join} "
                    f"WHERE im.{icat} IS NOT NULL {loc_sql} ORDER BY im.{icat}",
                    params,
                ) or []
            except Exception:
                pass
        if ibrand:
            try:
                brands = _safe_rows(
                    f"SELECT DISTINCT im.{ibrand} AS code FROM {im} im WHERE im.{ibrand} IS NOT NULL {loc_sql} ORDER BY 1",
                    params,
                ) or []
            except Exception:
                pass
        if isup:
            try:
                suppliers = _safe_rows(
                    f"SELECT DISTINCT im.{isup} AS code FROM {im} im WHERE im.{isup} IS NOT NULL {loc_sql} ORDER BY 1",
                    params,
                ) or []
            except Exception:
                pass
    return {
        'companies': companies,
        'branches': branches,
        'warehouses': warehouses,
        'categories': categories,
        'brands': brands,
        'suppliers': suppliers,
        'aging_methods': [
            {'id': 'last_movement', 'label': 'Last Movement Date'},
            {'id': 'last_sales', 'label': 'Last Sales Date'},
            {'id': 'last_receipt', 'label': 'Last Receipt Date'},
            {'id': 'last_purchase', 'label': 'Last Purchase Date'},
        ],
        'default_buckets': DEFAULT_BUCKETS,
    }


def get_stock_aging_rows(filters: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    loc = int(filters.get('locationcode') or filters.get('branch') or 1)
    as_on = (filters.get('as_on_date') or datetime.now().strftime('%Y-%m-%d')).strip()
    aging_method = (filters.get('aging_method') or 'last_movement').strip().lower()
    cost_method = (filters.get('cost_method') or 'average').strip().lower()
    include_zero = str(filters.get('include_zero') or '').lower() in ('1', 'true', 'y', 'yes')
    row_cap = min(max(int(filters.get('max_rows') or 8000), 1), 20000)
    buckets = parse_aging_buckets(filters.get('buckets_json'))

    im = _detect_table(['ITEMMASTER', 'itemmaster'])
    if not im:
        return ([], 'ITEMMASTER table not found.')
    ic = _detect_column(im, ['ITEMCODE', 'itemcode'])
    iloc = _detect_column(im, ['LOCATIONCODE', 'locationcode'])
    iname = _detect_column(im, ['ITEMNAME', 'itemname'])
    ibase = _detect_column(im, ['BASEUOM', 'baseuom', 'UNITOFMEASUREMENT'])
    icost = _detect_column(im, ['COSTPRICE', 'costprice'])
    iavg = _detect_column(im, ['AVERAGECOST', 'AVGCOST', 'averagecost'])
    istock = _detect_column(im, ['CURRENTSTOCK', 'CURRENT_STOCK', 'currentstock', 'STOCK'])
    icat = _detect_column(im, ['CATEGORYCODE', 'categorycode'])
    ibrand = _detect_column(im, ['BRANDCODE', 'brandcode'])
    isup = _detect_column(im, ['SUPCODE', 'SUPPLIERCODE', 'suppliercode'])
    iactive = _detect_column(im, ['ACTIVE', 'FLAG', 'ITEMSTATUS', 'active'])
    if not ic or not iloc:
        return ([], 'ITEMMASTER missing ITEMCODE or LOCATIONCODE.')

    try:
        im_cols = {str(c).upper() for c in _get_table_columns(im) or []}
    except Exception:
        im_cols = set()
    raw_col = _detect_column(im, ['RAWABICODE', 'rawabicode']) if 'RAWABICODE' in im_cols else None

    cost_sel = f'NVL(im.{iavg}, NVL(im.{icost}, 0))' if iavg and cost_method == 'average' else (
        f'NVL(im.{icost}, 0)' if icost else '0'
    )
    stock_sel = f'NVL(im.{istock}, 0)' if istock else '0'
    name_sel = f'im.{iname}' if iname else "''"
    uom_sel = f'im.{ibase}' if ibase else "''"
    barcode_sel = f'TRIM(TO_CHAR(im.{raw_col}))' if raw_col else "''"

    cat_tbl = _detect_table(['CATEGORY', 'category'])
    cat_code = _detect_column(cat_tbl, ['CODE', 'CATEGORYCODE']) if cat_tbl else None
    cat_name = _detect_column(cat_tbl, ['NAME', 'CATEGORYNAME']) if cat_tbl else None
    join_cat = ''
    cat_name_sel = "''"
    if icat and cat_tbl and cat_code and cat_name:
        join_cat = f'LEFT JOIN {cat_tbl} cat ON cat.{cat_code} = im.{icat}'
        cat_name_sel = f'NVL(cat.{cat_name}, \'\')'

    brand_tbl = _detect_table(['BRAND', 'brand'])
    join_brand = ''
    brand_name_sel = "''"
    if ibrand and brand_tbl:
        b_code = _detect_column(brand_tbl, ['CODE', 'BRANDCODE', 'brandcode'])
        b_name = _detect_column(brand_tbl, ['NAME', 'BRANDNAME', 'brandname'])
        if b_code and b_name:
            join_brand = f'LEFT JOIN {brand_tbl} br ON br.{b_code} = im.{ibrand}'
            brand_name_sel = f'NVL(br.{b_name}, \'\')'

    sup_tbl = _detect_table(['SUPPLIER', 'supplier', 'SUPPLIERMASTER'])
    join_sup = ''
    sup_name_sel = "''"
    if isup and sup_tbl:
        s_code = _detect_column(sup_tbl, ['CODE', 'SUPPLIERCODE', 'SUPCODE', 'suppliercode'])
        s_name = _detect_column(sup_tbl, ['NAME', 'SUPPLIERNAME', 'suppliername'])
        if s_code and s_name:
            join_sup = f'LEFT JOIN {sup_tbl} sup ON sup.{s_code} = im.{isup}'
            sup_name_sel = f'NVL(sup.{s_name}, \'\')'

    joins: List[str] = []
    sq_sale = _sales_last_date_subquery()
    sq_rcpt = _receipt_last_date_subquery()
    sq_move = _journal_last_movement_subquery()
    sale_sel = 'CAST(NULL AS DATE) AS last_sales_dt'
    rcpt_sel = 'CAST(NULL AS DATE) AS last_receipt_dt'
    move_sel = 'CAST(NULL AS DATE) AS last_movement_dt'
    if sq_sale:
        joins.append(f'LEFT JOIN ({sq_sale}) sa_sale ON sa_sale.ic = im.{ic}')
        sale_sel = 'sa_sale.dt AS last_sales_dt'
    if sq_rcpt:
        joins.append(f'LEFT JOIN ({sq_rcpt}) sa_rcpt ON sa_rcpt.ic = im.{ic}')
        rcpt_sel = 'sa_rcpt.dt AS last_receipt_dt'
    if sq_move:
        joins.append(f'LEFT JOIN ({sq_move}) sa_move ON sa_move.ic = im.{ic}')
        move_sel = 'sa_move.dt AS last_movement_dt'

    params: Dict[str, Any] = {'sa_loc': loc, 'sa_cap': row_cap}
    if sq_sale:
        params['sa_rn_bill'] = _SALES_RESET_NO
    if sq_rcpt:
        params['sa_rn_rcpt'] = _GRN_RESET_NO

    where = [f'im.{iloc} = :sa_loc']
    if not include_zero and istock:
        where.append(f'NVL(im.{istock}, 0) <> 0')

    for key, col in (
        ('category_code', icat),
        ('brand_code', ibrand),
        ('supplier_code', isup),
    ):
        val = str(filters.get(key) or '').strip()
        if val and col:
            where.append(f'TO_CHAR(im.{col}) = :sa_{key}')
            params[f'sa_{key}'] = val

    item_code = str(filters.get('item_code') or '').strip()
    if item_code:
        where.append(f'TO_CHAR(im.{ic}) = :sa_item_code')
        params['sa_item_code'] = item_code

    item_name = str(filters.get('item_name') or '').strip()
    if item_name and iname:
        where.append(f'UPPER(im.{iname}) LIKE :sa_item_name')
        params['sa_item_name'] = f'%{item_name.upper()}%'

    search = str(filters.get('search') or '').strip()
    if search:
        params['sa_q'] = f'%{search.upper()}%'
        parts = [f'UPPER(TO_CHAR(im.{ic})) LIKE :sa_q']
        if iname:
            parts.append(f'UPPER(im.{iname}) LIKE :sa_q')
        if raw_col:
            parts.append(f'UPPER(TRIM(TO_CHAR(im.{raw_col}))) LIKE :sa_q')
        where.append('(' + ' OR '.join(parts) + ')')

    warehouse_id = str(filters.get('warehouse_id') or '').strip()
    wh_join = ''
    if warehouse_id and _detect_table(['WAREHOUSE_STOCK', 'warehouse_stock']):
        ws = 'WAREHOUSE_STOCK'
        ws_item = _detect_column(ws, ['ITEMCODE', 'itemcode'])
        ws_loc = _detect_column(ws, ['LOCATIONCODE', 'locationcode'])
        ws_wh = _detect_column(ws, ['WAREHOUSE_ID', 'warehouse_id'])
        ws_qty = _detect_column(ws, ['QTY', 'quantity'])
        if ws_item and ws_loc and ws_wh and ws_qty:
            wh_join = (
                f' INNER JOIN {ws} ws ON ws.{ws_item} = im.{ic} AND ws.{ws_loc} = im.{iloc} '
                f' AND TO_CHAR(ws.{ws_wh}) = :sa_wh AND NVL(ws.{ws_qty}, 0) <> 0 '
            )
            params['sa_wh'] = warehouse_id
            stock_sel = f'NVL(ws.{ws_qty}, 0)'

    active_sel = f"NVL(im.{iactive}, 'Y')" if iactive else "'Y'"

    ref_expr = move_sel.replace(' AS last_movement_dt', '')
    if aging_method == 'last_sales':
        ref_expr = sale_sel.replace(' AS last_sales_dt', '')
    elif aging_method in ('last_receipt', 'last_purchase'):
        ref_expr = rcpt_sel.replace(' AS last_receipt_dt', '')

    q = f"""
        SELECT * FROM (
            SELECT
                im.{ic} AS itemcode,
                {barcode_sel} AS barcode,
                {name_sel} AS itemname,
                {cat_name_sel} AS category,
                {brand_name_sel} AS brand,
                {sup_name_sel} AS supplier,
                {uom_sel} AS uom,
                {stock_sel} AS currentstock,
                {cost_sel} AS averagecost,
                ({cost_sel} * {stock_sel}) AS stockvalue,
                TO_CHAR({rcpt_sel.replace(' AS last_receipt_dt', '')}, 'YYYY-MM-DD') AS last_purchase_date,
                TO_CHAR({rcpt_sel.replace(' AS last_receipt_dt', '')}, 'YYYY-MM-DD') AS last_receipt_date,
                TO_CHAR({sale_sel.replace(' AS last_sales_dt', '')}, 'YYYY-MM-DD') AS last_sales_date,
                TO_CHAR({move_sel.replace(' AS last_movement_dt', '')}, 'YYYY-MM-DD') AS last_movement_date,
                {active_sel} AS active_flag
            FROM {im} im
            {join_cat}
            {join_brand}
            {join_sup}
            {wh_join}
            {' '.join(joins)}
            WHERE {' AND '.join(where)}
            ORDER BY ({cost_sel} * {stock_sel}) DESC NULLS LAST, im.{ic}
        )
        WHERE ROWNUM <= :sa_cap
    """
    try:
        raw_rows = _safe_rows(q, params) or []
    except Exception as e:
        logger.exception('Stock aging query failed: %s', e)
        return ([], str(e))

    out: List[Dict[str, Any]] = []
    for r in raw_rows:
        stock = float(r.get('currentstock') or 0)
        avg_cost = float(r.get('averagecost') or 0)
        stock_value = float(r.get('stockvalue') or 0)
        if aging_method == 'last_sales':
            ref = r.get('last_sales_date')
        elif aging_method in ('last_receipt', 'last_purchase'):
            ref = r.get('last_receipt_date') or r.get('last_purchase_date')
        else:
            ref = r.get('last_movement_date')
        age = _age_days(as_on, ref)
        status = classify_movement_status(
            current_stock=stock,
            age_days=age,
            last_sales_date=r.get('last_sales_date'),
        )
        bucket = bucket_for_age(age, buckets)
        row = dict(r)
        row['age_days'] = age
        row['aging_bucket'] = bucket
        row['status'] = status
        row['stockvalue'] = round(stock_value, 2)
        row['averagecost'] = round(avg_cost, 4)
        row['currentstock'] = round(stock, 3)
        out.append(row)
    return (out, None)


def compute_stock_aging_summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    total_value = 0.0
    total_qty = 0.0
    slow_val = non_val = dead_val = 0.0
    active_items = inactive_items = 0
    for r in rows:
        sv = float(r.get('stockvalue') or 0)
        sq = float(r.get('currentstock') or 0)
        total_value += sv
        total_qty += sq
        st = str(r.get('status') or '')
        if st == 'Slow Moving':
            slow_val += sv
        elif st == 'Non Moving':
            non_val += sv
        elif st == 'Dead Stock':
            dead_val += sv
        if sq > 0.0001:
            active_items += 1
        else:
            inactive_items += 1
    return {
        'total_inventory_value': round(total_value, 2),
        'total_stock_quantity': round(total_qty, 3),
        'slow_moving_value': round(slow_val, 2),
        'non_moving_value': round(non_val, 2),
        'dead_stock_value': round(dead_val, 2),
        'total_active_items': active_items,
        'total_inactive_items': inactive_items,
        'row_count': len(rows),
    }


def compute_stock_aging_charts(
    rows: List[Dict[str, Any]],
    buckets: List[Dict[str, Any]],
    location_code: int,
    as_on_date: str,
) -> Dict[str, Any]:
    bucket_labels = [str(b.get('label')) for b in buckets]
    bucket_values = {lbl: 0.0 for lbl in bucket_labels}
    for r in rows:
        lbl = str(r.get('aging_bucket') or '')
        if lbl in bucket_values:
            bucket_values[lbl] += float(r.get('stockvalue') or 0)

    dead_items = sorted(
        [r for r in rows if r.get('status') == 'Dead Stock'],
        key=lambda x: float(x.get('stockvalue') or 0),
        reverse=True,
    )[:20]
    slow_items = sorted(
        [r for r in rows if r.get('status') == 'Slow Moving'],
        key=lambda x: float(x.get('stockvalue') or 0),
        reverse=True,
    )[:20]

    by_supplier: Dict[str, float] = {}
    by_category: Dict[str, float] = {}
    for r in rows:
        sup = str(r.get('supplier') or 'Unknown').strip() or 'Unknown'
        cat = str(r.get('category') or 'Unknown').strip() or 'Unknown'
        v = float(r.get('stockvalue') or 0)
        by_supplier[sup] = by_supplier.get(sup, 0) + v
        by_category[cat] = by_category.get(cat, 0) + v

    sup_sorted = sorted(by_supplier.items(), key=lambda x: x[1], reverse=True)[:15]
    cat_sorted = sorted(by_category.items(), key=lambda x: x[1], reverse=True)[:15]

    trend = _inventory_activity_trend(location_code, as_on_date)

    return {
        'bucket_chart': {'labels': bucket_labels, 'values': [round(bucket_values.get(l, 0), 2) for l in bucket_labels]},
        'dead_stock_top20': {
            'labels': [str(x.get('itemcode')) for x in dead_items],
            'values': [float(x.get('stockvalue') or 0) for x in dead_items],
        },
        'slow_moving_top20': {
            'labels': [str(x.get('itemcode')) for x in slow_items],
            'values': [float(x.get('stockvalue') or 0) for x in slow_items],
        },
        'by_supplier': {'labels': [x[0] for x in sup_sorted], 'values': [round(x[1], 2) for x in sup_sorted]},
        'by_category': {'labels': [x[0] for x in cat_sorted], 'values': [round(x[1], 2) for x in cat_sorted]},
        'inventory_trend': trend,
    }


def _inventory_activity_trend(location_code: int, as_on_date: str) -> Dict[str, Any]:
    jtbl = _detect_journal_table()
    if not jtbl:
        return {'labels': [], 'values': [], 'note': 'ITEMJOURNAL not available'}
    jcols = {str(c).upper() for c in (_get_table_columns(jtbl) or [])}
    j_dt = next((c for c in ('CREATEDDATE', 'JOURNALDATE', 'TRANSDATE') if c in jcols), None)
    j_loc = 'LOCATIONCODE' if 'LOCATIONCODE' in jcols else None
    if not j_dt or not j_loc:
        return {'labels': [], 'values': [], 'note': 'Journal date column missing'}
    as_on = (as_on_date or datetime.now().strftime('%Y-%m-%d'))[:10]
    q = f"""
        SELECT TO_CHAR(TRUNC(j.{j_dt}), 'YYYY-MM') AS ym,
               SUM(ABS(NVL(j.AMOUNT, NVL(j.QTY, 0) * NVL(j.RATE, 0)))) AS activity_value
        FROM {jtbl} j
        WHERE j.{j_loc} = :loc
          AND TRUNC(j.{j_dt}) >= ADD_MONTHS(TO_DATE(:as_on, 'YYYY-MM-DD'), -6)
          AND TRUNC(j.{j_dt}) <= TO_DATE(:as_on, 'YYYY-MM-DD')
        GROUP BY TO_CHAR(TRUNC(j.{j_dt}), 'YYYY-MM')
        ORDER BY 1
    """
    try:
        rows = _safe_rows(q, {'loc': location_code, 'as_on': as_on}) or []
        return {
            'labels': [str(r.get('ym') or '') for r in rows],
            'values': [round(float(r.get('activity_value') or 0), 2) for r in rows],
            'note': 'Journal activity value by month (proxy for inventory movement trend)',
        }
    except Exception as e:
        logger.warning('Stock aging trend query failed: %s', e)
        return {'labels': [], 'values': [], 'note': str(e)}


def generate_stock_aging_insights(rows: List[Dict[str, Any]], summary: Dict[str, Any]) -> List[Dict[str, str]]:
    insights: List[Dict[str, str]] = []
    dead_val = float(summary.get('dead_stock_value') or 0)
    total_val = float(summary.get('total_inventory_value') or 0)
    if dead_val > 0 and total_val > 0:
        pct = 100 * dead_val / total_val
        insights.append({
            'severity': 'high' if pct > 15 else 'medium',
            'title': 'Dead stock exposure',
            'message': f'Dead stock value is {dead_val:,.2f} ({pct:.1f}% of total inventory). Review liquidation or write-off for items above 365 days.',
        })
    no_sales = [r for r in rows if float(r.get('currentstock') or 0) > 0 and not r.get('last_sales_date')]
    if no_sales:
        top = sorted(no_sales, key=lambda x: float(x.get('stockvalue') or 0), reverse=True)[:5]
        codes = ', '.join(str(x.get('itemcode')) for x in top)
        insights.append({
            'severity': 'high',
            'title': 'Stock with no sales history',
            'message': f'{len(no_sales)} items have on-hand stock but no recorded sales. Top value: {codes}.',
        })
    overstock = sorted(
        [r for r in rows if float(r.get('currentstock') or 0) > 0 and int(r.get('age_days') or 0) < 30],
        key=lambda x: float(x.get('stockvalue') or 0),
        reverse=True,
    )[:3]
    if overstock:
        insights.append({
            'severity': 'low',
            'title': 'Recently received high-value stock',
            'message': 'Monitor sell-through on recent receipts to avoid future slow-moving inventory.',
        })
    slow_val = float(summary.get('slow_moving_value') or 0)
    if slow_val > 0:
        insights.append({
            'severity': 'medium',
            'title': 'Slow-moving inventory',
            'message': f'Slow-moving stock value totals {slow_val:,.2f}. Consider promotions, bundle offers, or inter-branch transfers.',
        })
    by_sup: Dict[str, float] = {}
    for r in rows:
        if r.get('status') in ('Dead Stock', 'Non Moving'):
            sup = str(r.get('supplier') or 'Unknown')
            by_sup[sup] = by_sup.get(sup, 0) + float(r.get('stockvalue') or 0)
    if by_sup:
        worst = max(by_sup.items(), key=lambda x: x[1])
        insights.append({
            'severity': 'medium',
            'title': 'Supplier performance (aged stock)',
            'message': f'Supplier "{worst[0]}" carries {worst[1]:,.2f} in non-moving/dead stock. Review MOQ and replenishment terms.',
        })
    carrying = total_val * 0.18 / 12
    if total_val > 0:
        insights.append({
            'severity': 'info',
            'title': 'Estimated carrying cost',
            'message': f'At ~18% annual carrying cost, monthly inventory holding cost is approximately {carrying:,.2f} on {total_val:,.2f} stock value.',
        })
    reorder = sorted(
        [r for r in rows if r.get('status') == 'Fast Moving' and float(r.get('currentstock') or 0) < 5],
        key=lambda x: float(x.get('currentstock') or 0),
    )[:5]
    if reorder:
        insights.append({
            'severity': 'info',
            'title': 'Suggested reorder candidates',
            'message': 'Fast-moving items with low on-hand quantity: ' + ', '.join(str(x.get('itemcode')) for x in reorder) + '.',
        })
    liquidate = sorted(
        [r for r in rows if r.get('status') == 'Dead Stock'],
        key=lambda x: float(x.get('stockvalue') or 0),
        reverse=True,
    )[:8]
    if liquidate:
        insights.append({
            'severity': 'high',
            'title': 'Suggested liquidation items',
            'message': 'Prioritize clearance for: ' + ', '.join(str(x.get('itemcode')) for x in liquidate) + '.',
        })
    if not insights:
        insights.append({
            'severity': 'info',
            'title': 'No critical alerts',
            'message': 'Current filters show balanced aging profile. Refine warehouse or category filters for deeper analysis.',
        })
    return insights


def get_stock_aging_drilldown(item_code: str, location_code: int, limit: int = 50) -> Dict[str, Any]:
    ic = str(item_code or '').strip()
    loc = int(location_code)
    cap = min(max(int(limit or 50), 5), 200)
    out: Dict[str, Any] = {
        'receipts': [],
        'purchases': [],
        'sales': [],
        'movements': [],
        'cost_history': [],
    }
    rh = _detect_table(['RECEIPTHDR', 'receipthdr'])
    rd = _detect_table(['RECEIPTDTL', 'receiptdtl'])
    if rh and rd:
        h_no = _detect_column(rh, ['RECEIPTNO', 'receiptno'])
        h_date = _detect_column(rh, ['RECEIPTDATE', 'receiptdate', 'CREATEDDATE'])
        h_loc = _detect_column(rh, ['LOCATIONCODE', 'locationcode'])
        h_sup = _detect_column(rh, ['SUPPLIERCODE', 'SUPPLIER', 'suppliercode'])
        d_no = _detect_column(rd, ['RECEIPTNO', 'receiptno'])
        d_item = _detect_column(rd, ['ITEMCODE', 'itemcode'])
        d_qty = _detect_column(rd, ['QUANTITY', 'quantity', 'RECEIVEDQTY'])
        d_cost = _detect_column(rd, ['COST', 'RATE', 'cost', 'rate'])
        if h_no and h_date and d_item:
            sup_sel = f'h.{h_sup}' if h_sup else 'NULL'
            qty_sel = f'NVL(d.{d_qty}, 0)' if d_qty else '0'
            cost_sel = f'NVL(d.{d_cost}, 0)' if d_cost else '0'
            wh = [f'd.{d_item} = :ic']
            if h_loc:
                wh.append(f'h.{h_loc} = :loc')
            try:
                out['receipts'] = _safe_rows(
                    f"""SELECT * FROM (
                        SELECT h.{h_no} AS receipt_no, TO_CHAR(h.{h_date}, 'YYYY-MM-DD') AS dt,
                               {sup_sel} AS supplier, {qty_sel} AS qty, {cost_sel} AS cost
                        FROM {rh} h INNER JOIN {rd} d ON d.{d_no} = h.{h_no}
                        WHERE {' AND '.join(wh)} ORDER BY h.{h_date} DESC
                    ) WHERE ROWNUM <= :cap""",
                    {'ic': ic, 'loc': loc, 'cap': cap},
                ) or []
            except Exception:
                pass
            out['purchases'] = list(out['receipts'])

    ht = _detect_table(['BILLHDRHISTORY', 'billhdrhistory']) or _detect_table(['BILLHDR', 'billhdr'])
    dt = _detect_table(['BILLDTLHISTORY', 'billdtlhistory']) or _detect_table(['BILLDTL', 'billdtl'])
    if ht and dt:
        h_no = _detect_column(ht, ['BILLNO', 'billno'])
        h_date = _detect_column(ht, ['BILLDATE', 'billdate'])
        h_loc = _detect_column(ht, ['LOCATIONCODE', 'locationcode'])
        d_bill = _detect_column(dt, ['BILLNO', 'billno'])
        d_item = _detect_column(dt, ['ITEMCODE', 'itemcode'])
        d_qty = _detect_column(dt, ['QUANTITY', 'quantity'])
        d_rate = _detect_column(dt, ['RATE', 'rate'])
        if h_no and h_date and d_item:
            wh = [f'd.{d_item} = :ic', f'NVL(d.{d_qty}, 0) >= 0']
            if h_loc:
                wh.append(f'h.{h_loc} = :loc')
            try:
                out['sales'] = _safe_rows(
                    f"""SELECT * FROM (
                        SELECT h.{h_no} AS invoice_no, TO_CHAR(h.{h_date}, 'YYYY-MM-DD') AS dt,
                               NVL(d.{d_qty}, 0) AS qty, NVL(d.{d_rate}, 0) AS selling_price
                        FROM {ht} h INNER JOIN {dt} d ON d.{d_bill} = h.{h_no}
                        WHERE {' AND '.join(wh)} ORDER BY h.{h_date} DESC
                    ) WHERE ROWNUM <= :cap""",
                    {'ic': ic, 'loc': loc, 'cap': cap},
                ) or []
            except Exception:
                pass

    jtbl = _detect_journal_table()
    if jtbl:
        jcols = {str(c).upper() for c in (_get_table_columns(jtbl) or [])}
        j_dt = next((c for c in ('CREATEDDATE', 'JOURNALDATE', 'TRANSDATE') if c in jcols), None)
        if j_dt and 'ITEMCODE' in jcols and 'LOCATIONCODE' in jcols:
            ref = 'SOURCE_NO' if 'SOURCE_NO' in jcols else ('RECEIPTNO' if 'RECEIPTNO' in jcols else 'NULL')
            tt = 'TRANSTYPE' if 'TRANSTYPE' in jcols else 'NULL'
            try:
                rows = _safe_rows(
                    f"""SELECT * FROM (
                        SELECT TO_CHAR(j.{j_dt}, 'YYYY-MM-DD') AS dt, j.{tt} AS transaction_type,
                               {ref} AS reference_no,
                               CASE WHEN NVL(j.QTY, 0) > 0 THEN j.QTY ELSE 0 END AS qty_in,
                               CASE WHEN NVL(j.QTY, 0) < 0 THEN ABS(j.QTY) ELSE 0 END AS qty_out,
                               j.QTY AS line_qty
                        FROM {jtbl} j
                        WHERE j.ITEMCODE = :ic AND j.LOCATIONCODE = :loc
                        ORDER BY j.{j_dt} DESC
                    ) WHERE ROWNUM <= :cap""",
                    {'ic': ic, 'loc': loc, 'cap': cap},
                ) or []
                balance = 0.0
                for r in reversed(rows):
                    balance += float(r.get('line_qty') or 0)
                rows_display = []
                balance_run = 0.0
                for r in reversed(rows):
                    balance_run += float(r.get('line_qty') or 0)
                    rows_display.append({
                        'dt': r.get('dt'),
                        'transaction_type': r.get('transaction_type'),
                        'reference_no': r.get('reference_no'),
                        'qty_in': r.get('qty_in'),
                        'qty_out': r.get('qty_out'),
                        'balance_qty': round(balance_run, 3),
                    })
                out['movements'] = list(reversed(rows_display))
            except Exception:
                pass

    im = _detect_table(['ITEMMASTER', 'itemmaster'])
    if im:
        icol = _detect_column(im, ['ITEMCODE', 'itemcode'])
        iloc = _detect_column(im, ['LOCATIONCODE', 'locationcode'])
        icost = _detect_column(im, ['COSTPRICE', 'costprice'])
        iavg = _detect_column(im, ['AVERAGECOST', 'averagecost'])
        if icol and iloc and (icost or iavg):
            try:
                row = (_safe_rows(
                    f'SELECT NVL({icost}, 0) AS prev_cost, NVL({iavg}, 0) AS new_cost FROM {im} '
                    f'WHERE {icol} = :ic AND {iloc} = :loc AND ROWNUM = 1',
                    {'ic': ic, 'loc': loc},
                ) or [None])[0]
                if row:
                    out['cost_history'] = [{
                        'previous_cost': row.get('prev_cost'),
                        'new_cost': row.get('new_cost'),
                        'change_date': datetime.now().strftime('%Y-%m-%d'),
                        'note': 'Current master costs; full cost audit trail requires cost change log table.',
                    }]
            except Exception:
                pass
    return out


def build_stock_aging_payload(filters: Dict[str, Any]) -> Dict[str, Any]:
    buckets = parse_aging_buckets(filters.get('buckets_json'))
    rows, err = get_stock_aging_rows(filters)
    summary = compute_stock_aging_summary(rows)
    loc = int(filters.get('locationcode') or filters.get('branch') or 1)
    charts = compute_stock_aging_charts(rows, buckets, loc, filters.get('as_on_date') or '')
    insights = generate_stock_aging_insights(rows, summary)
    return {
        'success': err is None,
        'error': err,
        'rows': rows,
        'summary': summary,
        'charts': charts,
        'insights': insights,
        'buckets': buckets,
        'filters': filters,
    }


def resolve_branch_from_session(session_obj: Any, request_args: Any = None) -> int:
    loc = None
    if request_args:
        br = (request_args.get('branch') or request_args.get('locationcode') or '').strip()
        if br.isdigit():
            loc = int(br)
    if loc is None and session_obj:
        sc = session_obj.get('location_code')
        if sc is not None and str(sc).strip().isdigit():
            loc = int(sc)
    if loc is None and session_obj:
        dbkey = session_obj.get('tenant_id') or 'HO'
        try:
            info = get_location_info_by_dbkey(dbkey)
            loc = int(info.get('locationcode') or 1)
        except Exception:
            loc = 1
    return int(loc or 1)
