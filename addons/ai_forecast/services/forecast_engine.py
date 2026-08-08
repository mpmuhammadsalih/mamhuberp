"""
AI Sales & Purchase Forecasting Engine — rule-based models (ML-ready JSON output).

Models: moving average, weighted trend, seasonal YoY, reorder point, scoring engines.
"""
from __future__ import annotations

import math
import os
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from db import _detect_column, _safe_rows

from addons.ai_forecast.services.schema import BILL_DTL_ALIAS, BILL_HDR_ALIAS, ForecastSchema

DEFAULT_LEAD_DAYS = int(os.environ.get('AI_FORECAST_LEAD_DAYS', '14') or 14)
SAFETY_DAYS = int(os.environ.get('AI_FORECAST_SAFETY_DAYS', '7') or 7)
DEAD_STOCK_DAYS = int(os.environ.get('AI_FORECAST_DEAD_DAYS', '90') or 90)


def _sf(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _si(v: Any, default: int = 0) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def _moving_average(values: List[float], window: int) -> float:
    if not values:
        return 0.0
    w = values[-window:] if window > 0 else values
    return sum(w) / len(w) if w else 0.0


def _weighted_trend_forecast(daily_series: List[Tuple[date, float]], horizon: int) -> float:
    """Recent days weighted higher (linear weights)."""
    if not daily_series or horizon <= 0:
        return 0.0
    series = sorted(daily_series, key=lambda x: x[0])[-90:]
    if not series:
        return 0.0
    weights = list(range(1, len(series) + 1))
    total_w = sum(weights)
    avg_daily = sum(v * w for (_, v), w in zip(series, weights)) / total_w if total_w else 0.0
    return avg_daily * horizon


def _growth_pct(recent: float, prior: float) -> Optional[float]:
    if prior <= 0:
        return None if recent <= 0 else 100.0
    return round(((recent - prior) / prior) * 100.0, 1)


def _classify_velocity(avg_daily: float, dead_days: int) -> str:
    if avg_daily <= 0:
        return 'dead'
    if avg_daily >= 5:
        return 'fast'
    if avg_daily >= 0.5:
        return 'medium'
    return 'slow'


def _product_score(avg_monthly_qty: float, revenue: float, turnover: float, return_ratio: float) -> int:
    score = 50.0
    score += min(25, avg_monthly_qty * 0.5)
    score += min(15, math.log10(revenue + 1) * 3)
    score += min(15, turnover * 5)
    score -= min(30, return_ratio * 100)
    return max(0, min(100, int(round(score))))


def get_daily_sales_series(schema: ForecastSchema, days: int = 90) -> List[Dict[str, Any]]:
    if not schema.has_sales():
        return []
    h, d = schema.bill_hdr, schema.bill_dtl
    bh, bd = BILL_HDR_ALIAS, BILL_DTL_ALIAS
    join = schema.bill_join_sql(bh, bd)
    if not join:
        return []
    hbd = schema.cols['h_billdate']
    qty = schema.cols['d_qty']
    rate = schema.cols.get('d_rate')
    disc = schema.cols.get('d_disc')
    amt_expr = f'SUM(ABS(NVL({bd}.{qty},0)) * NVL({bd}.{rate},0))' if rate else '0'
    if rate and disc:
        amt_expr = f'SUM(ABS(NVL({bd}.{qty},0)) * (NVL({bd}.{rate},0) - NVL({bd}.{disc},0)))'
    q = f"""
        SELECT TRUNC({bh}.{hbd}) AS sale_date,
               SUM(ABS(NVL({bd}.{qty},0))) AS qty,
               {amt_expr} AS amount,
               COUNT(DISTINCT {bh}.{schema.cols['h_billno']}) AS bills
        FROM {h} {bh}
        INNER JOIN {d} {bd} ON {join}
        WHERE {schema.bill_loc_filter(bh, bd)}
          AND {schema.bill_reset_filter(bh, bd)}
          AND {schema.bill_cancel_filter(bh)}
          AND TRUNC({bh}.{hbd}) >= TRUNC(SYSDATE) - :days
          AND NVL({bd}.{qty},0) <> 0
        GROUP BY TRUNC({bh}.{hbd})
        ORDER BY sale_date
    """
    rows = _safe_rows(q, schema.bill_query_params({'days': max(1, days)})) or []
    out = []
    for r in rows:
        sd = r.get('sale_date')
        ds = sd.strftime('%Y-%m-%d') if hasattr(sd, 'strftime') else str(sd)[:10]
        out.append({
            'date': ds,
            'qty': round(_sf(r.get('qty')), 3),
            'amount': round(_sf(r.get('amount')), 2),
            'bills': _si(r.get('bills')),
        })
    return out


def get_item_sales_velocity(schema: ForecastSchema, days: int = 90, limit: int = 500) -> List[Dict[str, Any]]:
    if not schema.has_sales():
        return []
    h, d, im = schema.bill_hdr, schema.bill_dtl, schema.item_tbl
    bh, bd = BILL_HDR_ALIAS, BILL_DTL_ALIAS
    join = schema.bill_join_sql(bh, bd)
    if not join:
        return []
    hbd = schema.cols['h_billdate']
    ic, nm = schema.cols['d_item'], schema.cols.get('im_name')
    qty = schema.cols['d_qty']
    rate = schema.cols.get('d_rate')
    im_join = ''
    name_sel = 'NULL AS itemname'
    if im and ic and schema.cols.get('im_item'):
        im_ic = schema.cols['im_item']
        im_join = f' LEFT JOIN {im} im ON {bd}.{ic} = im.{im_ic} '
        if schema.cols.get('im_loc'):
            im_join += f' AND im.{schema.cols["im_loc"]} = :loc '
        if nm:
            name_sel = f'im.{nm} AS itemname'
    rev = f'SUM(ABS(NVL({bd}.{qty},0)) * NVL({bd}.{rate},0))' if rate else '0'
    q = f"""
        SELECT {bd}.{ic} AS itemcode, {name_sel},
               SUM(CASE WHEN NVL({bd}.{qty},0) > 0 THEN NVL({bd}.{qty},0) ELSE 0 END) AS sold_qty,
               SUM(CASE WHEN NVL({bd}.{qty},0) < 0 THEN ABS(NVL({bd}.{qty},0)) ELSE 0 END) AS return_qty,
               {rev} AS revenue,
               COUNT(DISTINCT TRUNC({bh}.{hbd})) AS active_days
        FROM {h} {bh}
        INNER JOIN {d} {bd} ON {join}
        {im_join}
        WHERE {schema.bill_loc_filter(bh, bd)}
          AND {schema.bill_reset_filter(bh, bd)}
          AND {schema.bill_cancel_filter(bh)}
          AND TRUNC({bh}.{hbd}) >= TRUNC(SYSDATE) - :days
        GROUP BY {bd}.{ic}{', im.' + nm if im and nm else ''}
        ORDER BY sold_qty DESC
    """
    rows = _safe_rows(q, schema.bill_query_params({'days': max(1, days)})) or []
    span = max(1, days)
    out = []
    for r in rows[:limit]:
        sold = _sf(r.get('sold_qty'))
        ret = _sf(r.get('return_qty'))
        avg_daily = sold / span
        ret_ratio = ret / sold if sold > 0 else 0.0
        out.append({
            'itemcode': _si(r.get('itemcode')),
            'itemname': str(r.get('itemname') or '').strip(),
            'sold_qty': round(sold, 3),
            'return_qty': round(ret, 3),
            'return_ratio': round(ret_ratio, 4),
            'revenue': round(_sf(r.get('revenue')), 2),
            'avg_daily_sales': round(avg_daily, 4),
            'avg_monthly_sales': round(avg_daily * 30, 2),
            'active_days': _si(r.get('active_days')),
            'velocity_class': _classify_velocity(avg_daily, DEAD_STOCK_DAYS),
        })
    return out


def get_sales_forecast(schema: ForecastSchema, horizon_days: int = 30) -> Dict[str, Any]:
    daily = get_daily_sales_series(schema, 365)
    pairs = []
    for row in daily:
        try:
            d = datetime.strptime(row['date'][:10], '%Y-%m-%d').date()
        except ValueError:
            continue
        pairs.append((d, _sf(row.get('qty'))))

    ma7 = _moving_average([p[1] for p in pairs], 7)
    ma30 = _moving_average([p[1] for p in pairs], 30)
    ma90 = _moving_average([p[1] for p in pairs], 90)
    forecast_qty = _weighted_trend_forecast(pairs, horizon_days)

    amounts = [_sf(r.get('amount')) for r in daily]
    avg_amt_daily = _moving_average(amounts, 30)
    forecast_amount = round(avg_amt_daily * horizon_days, 2)

    # Same month previous year
    today = date.today()
    yoy_start = today.replace(year=today.year - 1, day=1) if today.month == 1 else today.replace(year=today.year - 1, month=today.month, day=1)
    yoy_end = (today.replace(year=today.year - 1) + timedelta(days=horizon_days))
    yoy_qty = sum(q for d, q in pairs if yoy_start <= d <= yoy_end)

    last7 = sum(p[1] for p in pairs if p[0] >= today - timedelta(days=7))
    last30 = sum(p[1] for p in pairs if p[0] >= today - timedelta(days=30))
    prior30 = sum(p[1] for p in pairs if today - timedelta(days=60) <= p[0] < today - timedelta(days=30))

    items = get_item_sales_velocity(schema, 90, limit=200)
    fast = [x for x in items if x['velocity_class'] == 'fast'][:15]
    slow = [x for x in items if x['velocity_class'] in ('slow', 'dead')][:15]

    return {
        'horizon_days': horizon_days,
        'daily_series': daily[-90:],
        'moving_average': {'7d': round(ma7, 3), '30d': round(ma30, 3), '90d': round(ma90, 3)},
        'predicted_qty': round(forecast_qty, 2),
        'predicted_amount': forecast_amount,
        'yoy_same_period_qty': round(yoy_qty, 2),
        'growth_pct_30d': _growth_pct(last30, prior30),
        'last_7d_qty': round(last7, 2),
        'last_30d_qty': round(last30, 2),
        'fast_moving_items': fast,
        'slow_moving_items': slow,
        'item_demand_forecast': [
            {
                'itemcode': it['itemcode'],
                'itemname': it['itemname'],
                'predicted_qty': round(it['avg_daily_sales'] * horizon_days, 2),
                'velocity_class': it['velocity_class'],
            }
            for it in items[:50]
        ],
    }


def _item_stock_map(schema: ForecastSchema) -> Dict[int, Dict[str, Any]]:
    im = schema.item_tbl
    if not im:
        return {}
    ic = schema.cols.get('im_item')
    if not ic:
        return {}
    cols = [f'{ic} AS itemcode']
    name_c = schema.cols.get('im_name')
    stock_c = schema.cols.get('im_stock')
    reorder_c = schema.cols.get('im_reorder')
    max_c = schema.cols.get('im_max')
    cost_c = schema.cols.get('im_cost')
    sup_c = schema.cols.get('im_sup')
    loc_c = schema.cols.get('im_loc')
    if name_c:
        cols.append(f'{name_c} AS itemname')
    if stock_c:
        cols.append(f'NVL({stock_c},0) AS current_stock')
    if reorder_c:
        cols.append(f'NVL({reorder_c},0) AS reorder_level')
    if max_c:
        cols.append(f'NVL({max_c},0) AS maximum_level')
    if cost_c:
        cols.append(f'NVL({cost_c},0) AS cost_price')
    if sup_c:
        cols.append(f'NVL({sup_c},0) AS supcode')
    where = [schema.item_active_filter('im')]
    params: Dict[str, Any] = {}
    if loc_c:
        where.append(f'im.{loc_c} = :loc')
        params['loc'] = schema.location_code
    q = f"SELECT {', '.join(cols)} FROM {im} im WHERE {' AND '.join(where)}"
    out: Dict[int, Dict[str, Any]] = {}
    for r in _safe_rows(q, params) or []:
        ic_v = _si(r.get('itemcode'))
        if ic_v > 0:
            out[ic_v] = r
    return out


def _pending_lpo_qty(schema: ForecastSchema) -> Dict[int, float]:
    lh, ld = schema.lpo_hdr, schema.lpo_dtl
    rh = schema.receipt_hdr
    if not lh or not ld:
        return {}
    lpo_c = schema.cols.get('ld_lpo')
    lh_lpo = schema.cols.get('lh_lpo')
    ic = schema.cols.get('ld_item')
    qty = schema.cols.get('ld_qty')
    if not all([lpo_c, lh_lpo, ic, qty]):
        return {}
    recv = ''
    if rh and schema.cols.get('rh_lpo') and schema.cols.get('lh_lpo'):
        rl, ll = schema.cols['rh_lpo'], schema.cols['lh_lpo']
        rw = [f'r.{rl} = h.{ll}']
        if schema.cols.get('rh_loc') and schema.cols.get('lh_loc'):
            rw.append(f'r.{schema.cols["rh_loc"]} = h.{schema.cols["lh_loc"]}')
        rh_del = _detect_column(rh, ['DELFLAG', 'DEL_FLAG', 'delflag']) if rh else None
        if rh_del:
            rw.append(f"NVL(r.{rh_del},'N') <> 'Y'")
        recv = f" AND NOT EXISTS (SELECT 1 FROM {rh} r WHERE {' AND '.join(rw)}) "
    hw = [f'h.{lh_lpo} = d.{lpo_c}']
    if schema.cols.get('lh_loc'):
        hw.append(f'h.{schema.cols["lh_loc"]} = :loc')
    lh_del = _detect_column(lh, ['DELFLAG', 'DEL_FLAG', 'delflag']) if lh else None
    if lh_del:
        hw.append(f"NVL(h.{lh_del},'N') <> 'Y'")
    q = f"""
        SELECT d.{ic} AS ic, SUM(NVL(d.{qty},0)) AS pq
        FROM {ld} d
        INNER JOIN {lh} h ON {' AND '.join(hw)}
        WHERE NVL(d.{qty},0) > 0 {recv}
        GROUP BY d.{ic}
    """
    return {_si(r['ic']): _sf(r.get('pq')) for r in (_safe_rows(q, {'loc': schema.location_code}) or []) if _si(r.get('ic')) > 0}


def _supplier_lead_days(schema: ForecastSchema) -> Dict[int, float]:
    rh, lh = schema.receipt_hdr, schema.lpo_hdr
    if not rh or not lh:
        return {}
    sup = schema.cols.get('rh_sup')
    lpo = schema.cols.get('rh_lpo')
    rdate = schema.cols.get('rh_date')
    ldate = schema.cols.get('lh_date')
    lno = schema.cols.get('lh_lpo')
    rloc = schema.cols.get('rh_loc')
    lloc = schema.cols.get('lh_loc')
    if not all([sup, lpo, rdate, ldate, lno]):
        return {}
    join = [f'r.{lpo} = l.{lno}', f'r.{lpo} > 0']
    if rloc and lloc:
        join.append(f'r.{rloc} = l.{lloc}')
    w = ' AND '.join(join)
    q = f"""
        SELECT r.{sup} AS sup, AVG(r.{rdate} - l.{ldate}) AS lead_days, COUNT(*) AS n
        FROM {rh} r
        INNER JOIN {lh} l ON {w}
        WHERE r.{rdate} >= TRUNC(SYSDATE) - 365
        GROUP BY r.{sup}
    """
    params: Dict[str, Any] = {}
    if rloc:
        q = q.replace('WHERE r.', f'WHERE r.{rloc} = :loc AND r.')
        params['loc'] = schema.location_code
    out: Dict[int, float] = {}
    for r in _safe_rows(q, params) or []:
        sup_v = _si(r.get('sup'))
        ld = _sf(r.get('lead_days'))
        if sup_v > 0 and ld > 0:
            out[sup_v] = ld
    return out


def get_reorder_recommendations(schema: ForecastSchema, limit: int = 100) -> List[Dict[str, Any]]:
    stock_map = _item_stock_map(schema)
    velocity = {x['itemcode']: x for x in get_item_sales_velocity(schema, 90, limit=2000)}
    pending = _pending_lpo_qty(schema)
    lead_by_sup = _supplier_lead_days(schema)
    default_lead = float(DEFAULT_LEAD_DAYS)
    safety_days = float(SAFETY_DAYS)
    recs: List[Dict[str, Any]] = []

    for ic, im in stock_map.items():
        vel = velocity.get(ic) or {}
        avg_daily = _sf(vel.get('avg_daily_sales'))
        stock = _sf(im.get('current_stock'))
        reorder_lvl = _sf(im.get('reorder_level'))
        maximum = _sf(im.get('maximum_level'))
        pending_q = _sf(pending.get(ic))
        sup = _si(im.get('supcode'))
        lead = lead_by_sup.get(sup, default_lead)
        safety_stock = avg_daily * safety_days
        reorder_point = (avg_daily * lead) + safety_stock
        if reorder_point <= 0 and reorder_lvl > 0:
            reorder_point = reorder_lvl
        available = stock + pending_q
        needs = available < reorder_point
        if maximum > 0:
            suggest = max(0.0, maximum - available)
        else:
            suggest = max(0.0, reorder_point - available + avg_daily * 14)
        if not needs and suggest <= 0:
            continue
        days_cover = round(stock / avg_daily, 1) if avg_daily > 0 else None
        recs.append({
            'itemcode': ic,
            'itemname': str(im.get('itemname') or '').strip(),
            'current_stock': round(stock, 3),
            'pending_lpo_qty': round(pending_q, 3),
            'avg_daily_sales': round(avg_daily, 4),
            'lead_days': round(lead, 1),
            'safety_stock': round(safety_stock, 2),
            'reorder_point': round(reorder_point, 2),
            'recommended_qty': round(suggest, 2) if needs or suggest > 0 else 0,
            'needs_reorder': needs,
            'days_of_cover': days_cover,
            'expected_reorder_date': (date.today() + timedelta(days=int(days_cover or 0))).isoformat() if days_cover else None,
            'risk': 'understock' if needs else 'ok',
            'velocity_class': vel.get('velocity_class', 'unknown'),
            'supcode': sup,
        })
    recs.sort(key=lambda x: (0 if x['needs_reorder'] else 1, -(x.get('recommended_qty') or 0)))
    return recs[:limit]


def get_purchase_forecast(schema: ForecastSchema) -> Dict[str, Any]:
    reorder = get_reorder_recommendations(schema, limit=150)
    understock = [r for r in reorder if r['needs_reorder']]
    overstock: List[Dict[str, Any]] = []
    stock_map = _item_stock_map(schema)
    velocity = {x['itemcode']: x for x in get_item_sales_velocity(schema, 90, limit=2000)}
    for ic, im in stock_map.items():
        stock = _sf(im.get('current_stock'))
        max_lvl = _sf(im.get('maximum_level'))
        avg_daily = _sf((velocity.get(ic) or {}).get('avg_daily_sales'))
        if max_lvl > 0 and stock > max_lvl * 1.2:
            overstock.append({
                'itemcode': ic,
                'itemname': str(im.get('itemname') or ''),
                'current_stock': round(stock, 3),
                'maximum_level': round(max_lvl, 3),
                'risk': 'overstock',
            })
        elif avg_daily > 0 and stock > avg_daily * 180:
            overstock.append({
                'itemcode': ic,
                'itemname': str(im.get('itemname') or ''),
                'current_stock': round(stock, 3),
                'days_cover': round(stock / avg_daily, 0),
                'risk': 'overstock',
            })
    return {
        'reorder_list': reorder,
        'understock_count': len(understock),
        'overstock_items': overstock[:30],
        'suggested_purchase_qty_total': round(sum(_sf(r.get('recommended_qty')) for r in understock), 2),
    }


def get_product_performance(schema: ForecastSchema, limit: int = 100) -> List[Dict[str, Any]]:
    items = get_item_sales_velocity(schema, 180, limit=limit * 2)
    stock_map = _item_stock_map(schema)
    out = []
    for it in items[:limit]:
        ic = it['itemcode']
        im = stock_map.get(ic) or {}
        stock = _sf(im.get('current_stock'))
        cost = _sf(im.get('cost_price'))
        revenue = _sf(it.get('revenue'))
        sold = _sf(it.get('sold_qty'))
        avg_monthly = _sf(it.get('avg_monthly_sales'))
        turnover = sold / stock if stock > 0 else 0.0
        gross_profit = revenue - (sold * cost) if cost > 0 else revenue * 0.3
        dead_days = DEAD_STOCK_DAYS if it['velocity_class'] == 'dead' else 0
        score = _product_score(avg_monthly, revenue, turnover, _sf(it.get('return_ratio')))
        out.append({
            **it,
            'current_stock': round(stock, 3),
            'gross_profit': round(gross_profit, 2),
            'stock_turnover': round(turnover, 3),
            'dead_stock_days': dead_days,
            'performance_score': score,
            'classification': it['velocity_class'].replace('dead', 'Dead Stock').replace('fast', 'Fast Moving').replace('slow', 'Slow Moving').replace('medium', 'Medium Moving'),
        })
    out.sort(key=lambda x: -x.get('performance_score', 0))
    return out


def get_supplier_performance(schema: ForecastSchema, limit: int = 50) -> List[Dict[str, Any]]:
    rh, rd = schema.receipt_hdr, schema.receipt_dtl
    if not rh or not rd or not schema.supplier_tbl:
        return []
    sup_c = schema.cols.get('rh_sup')
    rdate = schema.cols.get('rh_date')
    rno = schema.cols.get('rh_no')
    rd_no = schema.cols.get('rd_no')
    ic = schema.cols.get('rd_item')
    rate = schema.cols.get('rd_rate')
    qty = schema.cols.get('rd_qty')
    if not all([sup_c, rdate, rno, rd_no, ic]):
        return []
    join = f'd.{rd_no} = h.{rno}'
    if schema.cols.get('rh_loc'):
        join += f" AND h.{schema.cols['rh_loc']} = :loc"
    rate_expr = f'NVL(d.{rate},0)' if rate else '0'
    q = f"""
        SELECT h.{sup_c} AS supplier_code,
               COUNT(DISTINCT h.{rno}) AS receipt_count,
               AVG(CASE WHEN {rate_expr} > 0 THEN {rate_expr} END) AS avg_cost,
               MIN(CASE WHEN {rate_expr} > 0 THEN {rate_expr} END) AS min_cost,
               MAX(CASE WHEN {rate_expr} > 0 THEN {rate_expr} END) AS max_cost,
               COUNT(DISTINCT d.{ic}) AS item_variety
        FROM {rh} h
        INNER JOIN {rd} d ON {join}
        WHERE h.{rdate} >= TRUNC(SYSDATE) - 365
        GROUP BY h.{sup_c}
        ORDER BY receipt_count DESC
    """
    rows = _safe_rows(q, {'loc': schema.location_code}) or []
    lead_map = _supplier_lead_days(schema)
    sup_names: Dict[int, str] = {}
    if schema.cols.get('sup_code') and schema.cols.get('sup_name'):
        for r in _safe_rows(f"SELECT {schema.cols['sup_code']} AS c, {schema.cols['sup_name']} AS n FROM {schema.supplier_tbl}", {}) or []:
            sup_names[_si(r.get('c'))] = str(r.get('n') or '').strip()

    max_rc = max((_si(r.get('receipt_count')) for r in rows), default=1) or 1
    out = []
    for r in rows[:limit]:
        sc = _si(r.get('supplier_code'))
        if sc <= 0:
            continue
        rc = _si(r.get('receipt_count'))
        avg_c = _sf(r.get('avg_cost'))
        min_c = _sf(r.get('min_cost'))
        max_c = _sf(r.get('max_cost'))
        fluct = ((max_c - min_c) / avg_c * 100) if avg_c > 0 and max_c > min_c else 0
        lead = lead_map.get(sc, float(DEFAULT_LEAD_DAYS))
        freq_score = min(100, rc / max_rc * 100)
        price_score = max(0, 100 - fluct)
        delivery_score = max(0, 100 - min(100, lead / 30 * 100))
        rating = round(freq_score * 0.35 + price_score * 0.35 + delivery_score * 0.30, 1)
        out.append({
            'supplier_code': sc,
            'supplier_name': sup_names.get(sc, f'Supplier {sc}'),
            'receipt_count': rc,
            'avg_purchase_cost': round(avg_c, 4),
            'price_fluctuation_pct': round(fluct, 1),
            'avg_lead_days': round(lead, 1),
            'item_variety': _si(r.get('item_variety')),
            'rating': rating,
            'preferred': rating >= 70,
        })
    out.sort(key=lambda x: -x['rating'])
    return out


def get_customer_analysis(schema: ForecastSchema, limit: int = 50) -> Dict[str, Any]:
    if not schema.has_sales():
        return {'customers': [], 'cross_sell': []}
    h, d = schema.bill_hdr, schema.bill_dtl
    bh, bd = BILL_HDR_ALIAS, BILL_DTL_ALIAS
    join = schema.bill_join_sql(bh, bd)
    if not join:
        return {'customers': [], 'cross_sell': []}
    cust = schema.cols.get('h_customer')
    hbd = schema.cols['h_billdate']
    hbn = schema.cols['h_billno']
    h_custname = schema.cols.get('h_custname')
    net = schema.cols.get('h_net')
    qty = schema.cols.get('d_qty')
    rate = schema.cols.get('d_rate')
    amt_col = schema.cols.get('d_amt')

    if cust:
        cust_key = f'NVL({bh}.{cust}, 0)'
        cust_group = f'NVL({bh}.{cust}, 0)'
    elif h_custname:
        cust_key = f"NVL(TRIM({bh}.{h_custname}), 'WALK-IN')"
        cust_group = f"NVL(TRIM({bh}.{h_custname}), 'WALK-IN')"
    else:
        return {'customers': [], 'cross_sell': []}

    name_hdr = f"MAX(TRIM(NVL({bh}.{h_custname}, '')))" if h_custname else "''"
    if net:
        bill_amt_inner = f'MAX(NVL({bh}.{net}, 0))'
    elif amt_col:
        bill_amt_inner = f'SUM(ABS(NVL({bd}.{amt_col}, 0)))'
    elif rate and qty:
        bill_amt_inner = f'SUM(ABS(NVL({bd}.{qty}, 0)) * NVL({bd}.{rate}, 0))'
    else:
        bill_amt_inner = 'COUNT(*)'

    inner_group = [cust_group, f'{bh}.{hbn}']
    if schema.cols.get('h_reset'):
        inner_group.append(f'{bh}.{schema.cols["h_reset"]}')

    q = f"""
        SELECT customer_code,
               MAX(customer_name_hdr) AS customer_name_hdr,
               SUM(bill_amount) AS total_amount,
               COUNT(*) AS bill_count,
               COUNT(DISTINCT sale_day) AS active_days
        FROM (
            SELECT {cust_key} AS customer_code,
                   {name_hdr} AS customer_name_hdr,
                   TRUNC({bh}.{hbd}) AS sale_day,
                   {bill_amt_inner} AS bill_amount
            FROM {h} {bh}
            INNER JOIN {d} {bd} ON {join}
            WHERE {schema.bill_loc_filter(bh, bd)}
              AND {schema.bill_reset_filter(bh, bd)}
              AND {schema.bill_cancel_filter(bh)}
              AND TRUNC({bh}.{hbd}) >= TRUNC(SYSDATE) - 180
            GROUP BY {', '.join(inner_group)}, TRUNC({bh}.{hbd})
        )
        GROUP BY customer_code
        ORDER BY total_amount DESC
    """
    cust_rows = _safe_rows(q, schema.bill_query_params()) or []
    names: Dict[int, str] = {}
    if schema.customer_tbl and schema.cols.get('cust_code') and schema.cols.get('cust_name'):
        for r in _safe_rows(
            f"SELECT {schema.cols['cust_code']} AS c, {schema.cols['cust_name']} AS n FROM {schema.customer_tbl}",
            {},
        ) or []:
            names[_si(r.get('c'))] = str(r.get('n') or '').strip()

    customers = []
    for r in cust_rows[:limit]:
        cc_raw = r.get('customer_code')
        try:
            cc = _si(cc_raw)
        except (TypeError, ValueError):
            cc = 0
        hdr_name = str(r.get('customer_name_hdr') or '').strip()
        if cc == 0 and hdr_name:
            disp_name = hdr_name
        else:
            disp_name = names.get(cc, hdr_name or f'Customer {cc}')
        if cc == 0 and not hdr_name:
            disp_name = 'Walk-in / Cash'
        bills = _si(r.get('bill_count'))
        customers.append({
            'customer_code': cc,
            'customer_name': disp_name,
            'total_amount': round(_sf(r.get('total_amount')), 2),
            'bill_count': bills,
            'purchase_frequency_days': round(180 / max(1, _si(r.get('active_days'))), 1),
            'segment': 'high_value' if _sf(r.get('total_amount')) > 10000 else ('walk_in' if cc == 0 else 'regular'),
        })

    ic = schema.cols.get('d_item')
    top_items_q = f"""
        SELECT customer_code, itemcode, SUM(qty) AS qty
        FROM (
            SELECT {cust_key} AS customer_code, {bd}.{ic} AS itemcode,
                   SUM(ABS(NVL({bd}.{qty}, 0))) AS qty
            FROM {h} {bh}
            INNER JOIN {d} {bd} ON {join}
            WHERE {schema.bill_loc_filter(bh, bd)}
              AND {schema.bill_reset_filter(bh, bd)}
              AND {schema.bill_cancel_filter(bh)}
              AND TRUNC({bh}.{hbd}) >= TRUNC(SYSDATE) - 90
              AND NVL({bd}.{qty}, 0) <> 0
            GROUP BY {cust_key}, {bd}.{ic}
        )
        GROUP BY customer_code, itemcode
    """
    item_rows = _safe_rows(top_items_q, schema.bill_query_params()) or []
    by_cust: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for r in item_rows:
        try:
            ck = _si(r.get('customer_code'))
        except (TypeError, ValueError):
            ck = 0
        by_cust[ck].append({
            'itemcode': _si(r.get('itemcode')),
            'qty': round(_sf(r.get('qty')), 2),
        })
    cross_sell = []
    for cc, items in list(by_cust.items())[:20]:
        items.sort(key=lambda x: -x['qty'])
        cross_sell.append({
            'customer_code': cc,
            'top_items': items[:5],
            'cross_sell_hint': 'Frequently bought together — review basket analysis',
        })

    return {'customers': customers, 'cross_sell': cross_sell}


def get_insights_dashboard(schema: ForecastSchema) -> Dict[str, Any]:
    sales_fc = get_sales_forecast(schema, 30)
    purchase_fc = get_purchase_forecast(schema)
    products = get_product_performance(schema, 20)
    suppliers = get_supplier_performance(schema, 10)
    customers = get_customer_analysis(schema, 10)
    reorder = purchase_fc.get('reorder_list') or []

    return {
        'summary': {
            'predicted_sales_qty_30d': sales_fc.get('predicted_qty'),
            'predicted_sales_amount_30d': sales_fc.get('predicted_amount'),
            'sales_growth_pct': sales_fc.get('growth_pct_30d'),
            'last_7d_sales_qty': sales_fc.get('last_7d_qty'),
            'last_30d_sales_qty': sales_fc.get('last_30d_qty'),
            'yoy_same_period_qty': sales_fc.get('yoy_same_period_qty'),
            'understock_alerts': purchase_fc.get('understock_count'),
            'overstock_alerts': len(purchase_fc.get('overstock_items') or []),
            'suggested_purchase_qty_total': purchase_fc.get('suggested_purchase_qty_total'),
            'fast_moving_count': len(sales_fc.get('fast_moving_items') or []),
            'dead_slow_count': len(sales_fc.get('slow_moving_items') or []),
            'reorder_lines': len([r for r in reorder if _sf(r.get('recommended_qty')) > 0]),
        },
        'top_selling_items': sales_fc.get('fast_moving_items') or [],
        'low_stock_alerts': [r for r in reorder if r.get('needs_reorder')][:15],
        'overstock_warnings': purchase_fc.get('overstock_items') or [],
        'supplier_risk': [s for s in suppliers if s.get('rating', 100) < 50][:5],
        'sales_trend': sales_fc.get('daily_series') or [],
        'purchase_trend': get_purchase_trend(schema),
        'suggested_reorder': [r for r in reorder if r.get('recommended_qty', 0) > 0][:20],
        'product_leaders': products[:10],
        'top_customers': customers.get('customers') or [],
    }


def get_purchase_trend(schema: ForecastSchema, days: int = 90) -> List[Dict[str, Any]]:
    rh, rd = schema.receipt_hdr, schema.receipt_dtl
    if not rh or not rd:
        return []
    rdate = schema.cols.get('rh_date')
    rno = schema.cols.get('rh_no')
    rd_no = schema.cols.get('rd_no')
    rate = schema.cols.get('rd_rate')
    qty = schema.cols.get('rd_qty')
    if not all([rdate, rno, rd_no, qty]):
        return []
    amt = f'SUM(NVL(d.{qty},0) * NVL(d.{rate},0))' if rate else '0'
    join = f'd.{rd_no} = h.{rno}'
    w = [f'TRUNC(h.{rdate}) >= TRUNC(SYSDATE) - :days']
    params: Dict[str, Any] = {'days': days}
    if schema.cols.get('rh_loc'):
        w.append(f'h.{schema.cols["rh_loc"]} = :loc')
        params['loc'] = schema.location_code
    q = f"""
        SELECT TRUNC(h.{rdate}) AS pdate, SUM(NVL(d.{qty},0)) AS qty, {amt} AS amount
        FROM {rh} h
        INNER JOIN {rd} d ON {join}
        WHERE {' AND '.join(w)}
        GROUP BY TRUNC(h.{rdate})
        ORDER BY pdate
    """
    out = []
    for r in _safe_rows(q, params) or []:
        pd = r.get('pdate')
        out.append({
            'date': pd.strftime('%Y-%m-%d') if hasattr(pd, 'strftime') else str(pd)[:10],
            'qty': round(_sf(r.get('qty')), 2),
            'amount': round(_sf(r.get('amount')), 2),
        })
    return out


def get_report(schema: ForecastSchema, report_type: str) -> Dict[str, Any]:
    rt = (report_type or '').strip().lower().replace('-', '_')
    if rt in ('reorder', 'reorder_report'):
        return {'report': 'reorder', 'rows': get_reorder_recommendations(schema, 500)}
    if rt in ('sales_forecast', 'sales'):
        return {'report': 'sales_forecast', 'data': get_sales_forecast(schema, 30)}
    if rt in ('purchase_forecast', 'purchase'):
        return {'report': 'purchase_forecast', 'data': get_purchase_forecast(schema)}
    if rt in ('dead_stock', 'dead'):
        items = get_item_sales_velocity(schema, DEAD_STOCK_DAYS, 500)
        return {'report': 'dead_stock', 'rows': [x for x in items if x['velocity_class'] == 'dead']}
    if rt in ('fast_moving', 'fast'):
        items = get_item_sales_velocity(schema, 30, 500)
        return {'report': 'fast_moving', 'rows': [x for x in items if x['velocity_class'] == 'fast']}
    if rt in ('supplier', 'supplier_analysis'):
        return {'report': 'supplier_analysis', 'rows': get_supplier_performance(schema, 200)}
    if rt in ('customer', 'customer_pattern'):
        return {'report': 'customer_pattern', 'data': get_customer_analysis(schema, 200)}
    return {'report': rt, 'error': 'Unknown report type'}
