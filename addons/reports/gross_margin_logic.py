"""Gross Margin Analysis dashboard — profitability KPIs, charts, drill-down, AI insights (tenant DB)."""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from db import (
    DATABASES,
    _detect_column,
    _detect_table,
    _safe_rows,
    get_locations_list,
    resolve_warehouse_master_table,
)
from addons.reports.stock_aging_logic import get_stock_aging_drilldown

logger = logging.getLogger(__name__)


def _f(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def margin_status_label(pct: Optional[float]) -> str:
    if pct is None:
        return 'Loss'
    p = float(pct)
    if p < 0:
        return 'Loss'
    if p > 30:
        return 'Excellent Margin'
    if p >= 15:
        return 'Good Margin'
    if p >= 5:
        return 'Low Margin'
    return 'Loss'


def margin_color_class(pct: Optional[float]) -> str:
    if pct is None:
        return 'gma-margin--red'
    p = float(pct)
    if p < 0:
        return 'gma-margin--dark-red'
    if p > 30:
        return 'gma-margin--green'
    if p >= 15:
        return 'gma-margin--yellow'
    if p >= 5:
        return 'gma-margin--orange'
    return 'gma-margin--red'


def _map_grid_row(r: Dict[str, Any], salesman_names: Dict[str, str]) -> Dict[str, Any]:
    qty = _f(r.get('quantity'))
    sales = _f(r.get('line_sales'))
    cost = _f(r.get('cogs'))
    profit = _f(r.get('gross_margin'))
    pct = r.get('margin_pct')
    pct_f = float(pct) if pct is not None and str(pct).strip() != '' else None
    rate = _f(r.get('rate'))
    unit_cost = _f(r.get('unit_cost'))
    sm_code = str(r.get('salesmancode') or r.get('SALESMANCODE') or '').strip()
    return {
        'invoice_no': r.get('billno'),
        'invoice_date': r.get('bill_date') or r.get('billdate'),
        'customer_code': r.get('customercode'),
        'customer': r.get('customername') or '',
        'salesman_code': sm_code,
        'salesman': salesman_names.get(sm_code, sm_code) if sm_code else '',
        'item_code': r.get('itemcode'),
        'item_name': r.get('itemname') or '',
        'category': r.get('categoryname') or '',
        'brand': r.get('brandcode') or '',
        'qty': round(qty, 3),
        'sales_rate': round(rate, 4),
        'cost_rate': round(unit_cost, 4),
        'sales_amount': round(sales, 2),
        'cost_amount': round(cost, 2),
        'profit_amount': round(profit, 2),
        'margin_pct': pct_f,
        'status': margin_status_label(pct_f),
        'margin_class': margin_color_class(pct_f),
        'billtype': r.get('billtype'),
        'slno': r.get('slno'),
    }


def _load_salesman_names(codes: List[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    codes = [c for c in codes if c and c.isdigit()]
    if not codes:
        return out
    tbl = _detect_table(['SALESMAN', 'salesman', 'SALESMEN'])
    if not tbl:
        return out
    code_col = _detect_column(tbl, ['SALESMANCODE', 'salesmancode', 'CODE'])
    name_col = _detect_column(tbl, ['SALESMANNAME', 'salesmanname', 'NAME'])
    if not code_col or not name_col:
        return out
    uniq = list(dict.fromkeys(codes))[:200]
    placeholders = ', '.join(f':c{i}' for i in range(len(uniq)))
    params = {f'c{i}': int(c) for i, c in enumerate(uniq)}
    try:
        rows = _safe_rows(
            f"SELECT {code_col} AS code, {name_col} AS name FROM {tbl} "
            f"WHERE {code_col} IN ({placeholders})",
            params,
        ) or []
        for row in rows:
            k = str(row.get('code') or row.get('CODE') or '').strip()
            out[k] = str(row.get('name') or row.get('NAME') or k).strip()
    except Exception:
        logger.debug('salesman name lookup failed', exc_info=True)
    return out


def _aggregate_rows(
    grid: List[Dict[str, Any]],
    key_fn: Callable[[Dict[str, Any]], str],
    label_fn: Callable[[Dict[str, Any]], str],
) -> List[Dict[str, Any]]:
    buckets: Dict[str, Dict[str, Any]] = {}
    for r in grid:
        key = key_fn(r) or '(blank)'
        if key not in buckets:
            buckets[key] = {
                'key': key,
                'label': label_fn(r),
                'sales_amount': 0.0,
                'cost_amount': 0.0,
                'profit_amount': 0.0,
                'qty': 0.0,
                'line_count': 0,
            }
        b = buckets[key]
        b['sales_amount'] += _f(r.get('sales_amount'))
        b['cost_amount'] += _f(r.get('cost_amount'))
        b['profit_amount'] += _f(r.get('profit_amount'))
        b['qty'] += _f(r.get('qty'))
        b['line_count'] += 1
    result = []
    for b in buckets.values():
        sales = b['sales_amount']
        profit = b['profit_amount']
        pct = round(100.0 * profit / sales, 2) if abs(sales) > 1e-6 else None
        b['margin_pct'] = pct
        b['status'] = margin_status_label(pct)
        b['margin_class'] = margin_color_class(pct)
        for k in ('sales_amount', 'cost_amount', 'profit_amount', 'qty'):
            b[k] = round(b[k], 2)
        result.append(b)
    result.sort(key=lambda x: _f(x.get('profit_amount')), reverse=True)
    return result


def _top_n_chart(rows: List[Dict[str, Any]], n: int = 20) -> Dict[str, Any]:
    labels = [str(r.get('label') or r.get('key') or '')[:40] for r in rows[:n]]
    profits = [_f(r.get('profit_amount')) for r in rows[:n]]
    margins = [r.get('margin_pct') for r in rows[:n]]
    return {'labels': labels, 'profit': profits, 'margin_pct': margins}


def _build_kpis(grid: List[Dict[str, Any]], branch_label: str) -> Dict[str, Any]:
    total_sales = sum(_f(r.get('sales_amount')) for r in grid)
    total_cost = sum(_f(r.get('cost_amount')) for r in grid)
    gross_profit = sum(_f(r.get('profit_amount')) for r in grid)
    margin_pct = round(100.0 * gross_profit / total_sales, 2) if abs(total_sales) > 1e-6 else None

    by_item: Dict[str, Dict[str, float]] = defaultdict(lambda: {'profit': 0.0, 'sales': 0.0, 'name': ''})
    for r in grid:
        ic = str(r.get('item_code') or '')
        by_item[ic]['profit'] += _f(r.get('profit_amount'))
        by_item[ic]['sales'] += _f(r.get('sales_amount'))
        by_item[ic]['name'] = r.get('item_name') or ic
    item_margins = []
    for ic, v in by_item.items():
        if not ic:
            continue
        pct = round(100.0 * v['profit'] / v['sales'], 2) if abs(v['sales']) > 1e-6 else None
        item_margins.append((ic, v['name'], pct, v['profit']))

    highest = lowest = None
    if item_margins:
        item_margins.sort(key=lambda x: (x[2] if x[2] is not None else -999), reverse=True)
        hi = item_margins[0]
        lo = item_margins[-1]
        highest = {'item_code': hi[0], 'item_name': hi[1], 'margin_pct': hi[2], 'profit': round(hi[3], 2)}
        lowest = {'item_code': lo[0], 'item_name': lo[1], 'margin_pct': lo[2], 'profit': round(lo[3], 2)}

    loss_lines = [r for r in grid if _f(r.get('profit_amount')) < -0.01]
    loss_items = len({r.get('item_code') for r in loss_lines if r.get('item_code')})

    by_cust: Dict[str, Dict[str, Any]] = defaultdict(lambda: {'profit': 0.0, 'name': ''})
    for r in grid:
        cc = str(r.get('customer_code') or r.get('customer') or '')
        by_cust[cc]['profit'] += _f(r.get('profit_amount'))
        by_cust[cc]['name'] = r.get('customer') or cc
    top_cust = None
    if by_cust:
        best = max(by_cust.items(), key=lambda x: x[1]['profit'])
        top_cust = {
            'customer_code': best[0],
            'customer_name': best[1]['name'],
            'profit': round(best[1]['profit'], 2),
        }

    return {
        'total_sales': round(total_sales, 2),
        'total_cost': round(total_cost, 2),
        'gross_profit': round(gross_profit, 2),
        'margin_pct': margin_pct,
        'highest_margin_item': highest,
        'lowest_margin_item': lowest,
        'loss_making_items': loss_items,
        'loss_making_lines': len(loss_lines),
        'top_customer_by_profit': top_cust,
        'branch_label': branch_label,
        'line_count': len(grid),
    }


def _build_insights(
    grid: List[Dict[str, Any]],
    summary_item: List[Dict[str, Any]],
    summary_category: List[Dict[str, Any]],
    monthly_trend: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    insights: List[Dict[str, Any]] = []

    below_cost = [r for r in grid if _f(r.get('profit_amount')) < -0.5]
    if below_cost:
        sample = ', '.join(
            f"{r.get('item_code')} ({r.get('invoice_no')})" for r in below_cost[:5]
        )
        insights.append({
            'severity': 'high',
            'title': 'Items sold below cost',
            'message': f'{len(below_cost)} line(s) with negative gross margin. Examples: {sample}. Review pricing and average cost.',
        })

    high_disc = [r for r in grid if _f(r.get('sales_amount')) > 0 and _f(r.get('margin_pct') or 0) < 5]
    by_cust_disc: Dict[str, int] = defaultdict(int)
    for r in high_disc:
        by_cust_disc[str(r.get('customer') or '')] += 1
    if by_cust_disc:
        worst = max(by_cust_disc.items(), key=lambda x: x[1])
        if worst[1] >= 3:
            insights.append({
                'severity': 'medium',
                'title': 'Customers with thin margins',
                'message': f'Customer "{worst[0]}" has {worst[1]} low-margin lines — verify discounts and price lists.',
            })

    if summary_item:
        top3 = summary_item[:3]
        insights.append({
            'severity': 'info',
            'title': 'Most profitable items',
            'message': 'Top performers: ' + ', '.join(
                f"{x.get('label')} ({x.get('profit_amount'):,.0f})" for x in top3
            ),
        })

    if summary_category:
        top_cat = summary_category[0]
        insights.append({
            'severity': 'info',
            'title': 'Most profitable category',
            'message': f"{top_cat.get('label')} — profit {top_cat.get('profit_amount'):,.2f}, margin {top_cat.get('margin_pct')}%",
        })

    if len(monthly_trend) >= 3:
        margs = [(_f(x.get('margin_pct')), x.get('label')) for x in monthly_trend]
        recent = margs[-3:]
        if all(r[0] is not None for r in recent):
            if recent[-1][0] < recent[0][0] - 3:
                insights.append({
                    'severity': 'medium',
                    'title': 'Declining margin trend',
                    'message': f'Margin fell from {recent[0][0]}% ({recent[0][1]}) to {recent[-1][0]}% ({recent[-1][1]}). Review cost increases and selling prices.',
                })

    for r in grid:
        if _f(r.get('qty')) <= 0 or _f(r.get('sales_rate')) <= 0:
            continue
        uc = _f(r.get('cost_rate'))
        if uc <= 0:
            continue
        min_price = round(uc * 1.15, 4)
        if _f(r.get('sales_rate')) < min_price and _f(r.get('profit_amount')) < 0:
            insights.append({
                'severity': 'medium',
                'title': 'Suggested minimum selling price',
                'message': f"Item {r.get('item_code')}: cost {uc:.2f} — minimum 15% margin price ≈ {min_price:.2f} (current rate {r.get('sales_rate'):.2f}).",
            })
            break

    profitable = [x for x in summary_item if _f(x.get('margin_pct') or 0) > 25][:5]
    if profitable:
        insights.append({
            'severity': 'info',
            'title': 'Suggested selling price focus',
            'message': 'Maintain premium pricing on: ' + ', '.join(x.get('label', '') for x in profitable),
        })

    if not insights:
        insights.append({
            'severity': 'info',
            'title': 'Margin profile stable',
            'message': 'No critical margin alerts for the selected filters. Adjust date range or branch for deeper analysis.',
        })
    return insights[:12]


def get_gross_margin_filter_options(location_code: Optional[int] = None) -> Dict[str, Any]:
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
                pass
    categories: List[Dict[str, Any]] = []
    brands: List[Dict[str, Any]] = []
    salesmen: List[Dict[str, Any]] = []
    im = _detect_table(['ITEMMASTER', 'itemmaster'])
    if im:
        icat = _detect_column(im, ['CATEGORYCODE', 'categorycode'])
        ibrand = _detect_column(im, ['BRANDCODE', 'brandcode'])
        iloc = _detect_column(im, ['LOCATIONCODE', 'locationcode'])
        params: Dict[str, Any] = {}
        loc_sql = ''
        if iloc and loc is not None:
            loc_sql = f' AND im.{iloc} = :loc '
            params['loc'] = int(loc)
        if icat:
            try:
                categories = _safe_rows(
                    f"SELECT DISTINCT im.{icat} AS code FROM {im} im WHERE im.{icat} IS NOT NULL {loc_sql} ORDER BY 1",
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
    sm_tbl = _detect_table(['SALESMAN', 'salesman'])
    if sm_tbl:
        sc = _detect_column(sm_tbl, ['SALESMANCODE', 'CODE'])
        sn = _detect_column(sm_tbl, ['SALESMANNAME', 'NAME'])
        if sc:
            cols = [f'{sc} AS code']
            if sn:
                cols.append(f'{sn} AS name')
            try:
                salesmen = _safe_rows(f"SELECT {', '.join(cols)} FROM {sm_tbl} ORDER BY {sc}", {}) or []
            except Exception:
                pass
    cust_tbl = _detect_table(['CUSTOMER', 'customer'])
    customers: List[Dict[str, Any]] = []
    if cust_tbl:
        cc = _detect_column(cust_tbl, ['CUSTOMERCODE', 'CODE'])
        cn = _detect_column(cust_tbl, ['CUSTOMERNAME', 'NAME'])
        if cc:
            cols = [f'{cc} AS code']
            if cn:
                cols.append(f'{cn} AS name')
            try:
                customers = _safe_rows(
                    f"SELECT * FROM (SELECT {', '.join(cols)} FROM {cust_tbl} ORDER BY {cc}) WHERE ROWNUM <= 500",
                    {},
                ) or []
            except Exception:
                pass
    return {
        'companies': companies,
        'branches': branches,
        'warehouses': warehouses,
        'categories': categories,
        'brands': brands,
        'salesmen': salesmen,
        'customers': customers,
    }


def get_item_margin_trend(
    item_code: str,
    *,
    date_from: str,
    date_to: str,
    location_code: int,
) -> List[Dict[str, Any]]:
    from addons.reports.controllers.routes import _get_margin_report_rows

    rows, err = _get_margin_report_rows(
        date_from=date_from,
        date_to=date_to,
        itemcode=item_code,
        report_mode='month',
        row_cap=36,
        location_code=location_code,
    )
    if err:
        return []
    out = []
    for r in rows:
        period = r.get('period') or r.get('bill_month') or ''
        out.append({
            'period': period,
            'label': period,
            'sales_amount': _f(r.get('sales')),
            'cost_amount': _f(r.get('cogs')),
            'profit_amount': _f(r.get('margin')),
            'margin_pct': r.get('margin_pct'),
        })
    return out


def get_gross_margin_drilldown(
    item_code: str,
    location_code: int,
    *,
    date_from: str = '',
    date_to: str = '',
    limit: int = 50,
) -> Dict[str, Any]:
    data = get_stock_aging_drilldown(item_code, location_code, limit=limit)
    trend = []
    if date_from and date_to:
        trend = get_item_margin_trend(
            item_code,
            date_from=date_from,
            date_to=date_to,
            location_code=location_code,
        )
    data['margin_trend'] = trend
    return data


def build_gross_margin_dashboard(filters: Dict[str, Any]) -> Dict[str, Any]:
    from addons.reports.controllers.routes import (
        _default_report_date_range,
        _get_margin_report_rows,
    )

    date_from = (filters.get('date_from') or '').strip()
    date_to = (filters.get('date_to') or '').strip()
    date_from, date_to = _default_report_date_range(date_from, date_to)
    loc = int(filters.get('locationcode') or filters.get('branch') or 1)

    branch_label = str(loc)
    for b in get_locations_list() or []:
        if str(b.get('locationcode') or b.get('code')) == str(loc):
            branch_label = f"{loc} {b.get('locationname') or b.get('name') or ''}".strip()
            break

    rows, err = _get_margin_report_rows(
        date_from=date_from,
        date_to=date_to,
        search=(filters.get('search') or '').strip(),
        itemcode=(filters.get('item_code') or filters.get('itemcode') or '').strip(),
        category_code=(filters.get('category_code') or '').strip(),
        brand_code=(filters.get('brand_code') or '').strip(),
        customer_code=(filters.get('customer_code') or '').strip(),
        salesman_code=(filters.get('salesman_code') or '').strip(),
        report_mode='detail',
        row_cap=int(filters.get('max_rows') or 12000),
        location_code=loc,
    )
    if err:
        return {
            'success': False,
            'error': err,
            'generated_at': datetime.now().isoformat(timespec='seconds'),
        }

    sm_codes = list({str(r.get('salesmancode') or '').strip() for r in rows if r.get('salesmancode')})
    sm_names = _load_salesman_names(sm_codes)
    grid = [_map_grid_row(r, sm_names) for r in rows]

    kpis = _build_kpis(grid, branch_label)
    summary_item = _aggregate_rows(
        grid,
        lambda r: str(r.get('item_code') or ''),
        lambda r: f"{r.get('item_code')} — {r.get('item_name') or ''}".strip(' —'),
    )
    summary_category = _aggregate_rows(grid, lambda r: str(r.get('category') or '(none)'), lambda r: str(r.get('category') or '(none)'))
    summary_brand = _aggregate_rows(grid, lambda r: str(r.get('brand') or '(none)'), lambda r: str(r.get('brand') or '(none)'))
    summary_customer = _aggregate_rows(
        grid,
        lambda r: str(r.get('customer_code') or r.get('customer') or ''),
        lambda r: str(r.get('customer') or r.get('customer_code') or ''),
    )
    summary_salesman = _aggregate_rows(
        grid,
        lambda r: str(r.get('salesman_code') or r.get('salesman') or ''),
        lambda r: str(r.get('salesman') or r.get('salesman_code') or ''),
    )
    summary_branch = [{
        'key': str(loc),
        'label': branch_label,
        'sales_amount': kpis['total_sales'],
        'cost_amount': kpis['total_cost'],
        'profit_amount': kpis['gross_profit'],
        'margin_pct': kpis['margin_pct'],
        'qty': round(sum(_f(r.get('qty')) for r in grid), 2),
        'line_count': len(grid),
        'status': margin_status_label(kpis.get('margin_pct')),
        'margin_class': margin_color_class(kpis.get('margin_pct')),
    }]
    summary_invoice = _aggregate_rows(
        grid,
        lambda r: str(r.get('invoice_no') or ''),
        lambda r: f"#{r.get('invoice_no')} {r.get('invoice_date') or ''}".strip(),
    )

    month_rows, _ = _get_margin_report_rows(
        date_from=date_from,
        date_to=date_to,
        itemcode=(filters.get('item_code') or filters.get('itemcode') or '').strip(),
        category_code=(filters.get('category_code') or '').strip(),
        brand_code=(filters.get('brand_code') or '').strip(),
        customer_code=(filters.get('customer_code') or '').strip(),
        salesman_code=(filters.get('salesman_code') or '').strip(),
        report_mode='month',
        row_cap=60,
        location_code=loc,
    )
    monthly_trend = []
    for r in month_rows or []:
        monthly_trend.append({
            'key': r.get('period'),
            'label': r.get('period'),
            'sales_amount': _f(r.get('sales')),
            'cost_amount': _f(r.get('cogs')),
            'profit_amount': _f(r.get('margin')),
            'margin_pct': r.get('margin_pct'),
        })
    monthly_trend.sort(key=lambda x: str(x.get('label') or ''))

    profitable_items = [x for x in summary_item if _f(x.get('profit_amount')) > 0]
    loss_items = sorted(
        [x for x in summary_item if _f(x.get('profit_amount')) < 0],
        key=lambda x: _f(x.get('profit_amount')),
    )

    charts = {
        'top_profitable_items': _top_n_chart(profitable_items, 20),
        'top_loss_items': _top_n_chart(loss_items, 20),
        'margin_by_category': {
            'labels': [str(x.get('label'))[:32] for x in summary_category[:15]],
            'margin_pct': [x.get('margin_pct') for x in summary_category[:15]],
            'profit': [_f(x.get('profit_amount')) for x in summary_category[:15]],
        },
        'margin_by_salesman': {
            'labels': [str(x.get('label'))[:24] for x in summary_salesman[:12]],
            'margin_pct': [x.get('margin_pct') for x in summary_salesman[:12]],
        },
        'margin_trend_month': {
            'labels': [str(x.get('label')) for x in monthly_trend],
            'margin_pct': [x.get('margin_pct') for x in monthly_trend],
            'profit': [_f(x.get('profit_amount')) for x in monthly_trend],
            'sales': [_f(x.get('sales_amount')) for x in monthly_trend],
        },
        'margin_by_customer': {
            'labels': [str(x.get('label'))[:28] for x in summary_customer[:15]],
            'margin_pct': [x.get('margin_pct') for x in summary_customer[:15]],
            'profit': [_f(x.get('profit_amount')) for x in summary_customer[:15]],
        },
    }

    insights = _build_insights(grid, summary_item, summary_category, monthly_trend)

    return {
        'success': True,
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'filters': {**filters, 'date_from': date_from, 'date_to': date_to, 'locationcode': loc},
        'kpis': kpis,
        'grid': grid,
        'summaries': {
            'item': summary_item,
            'category': summary_category,
            'brand': summary_brand,
            'customer': summary_customer,
            'salesman': summary_salesman,
            'branch': summary_branch,
            'invoice': summary_invoice,
        },
        'charts': charts,
        'insights': insights,
        'advanced': {
            'by_customer': summary_customer,
            'by_item': summary_item,
            'by_category': summary_category,
            'by_brand': summary_brand,
            'by_branch': summary_branch,
            'by_salesman': summary_salesman,
            'by_invoice': summary_invoice,
        },
    }
