"""AI Forecasting routes — dashboard, analytics pages, JSON APIs."""
from __future__ import annotations

import csv
import io
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from nexa_http import Blueprint, Response, jsonify, redirect, render_template, request, session, url_for

from addons.ai_forecast.services.forecast_engine import (
    get_customer_analysis,
    get_insights_dashboard,
    get_product_performance,
    get_purchase_forecast,
    get_report,
    get_reorder_recommendations,
    get_sales_forecast,
    get_supplier_performance,
)
from addons.ai_forecast.services.schema import ForecastSchema
from db import get_location_info_by_dbkey

_ADDON_ROOT = Path(__file__).resolve().parents[1]
bp = Blueprint(
    'ai_forecast',
    __name__,
    url_prefix='/ai',
    template_folder=str(_ADDON_ROOT / 'views' / 'templates'),
    static_folder=str(_ADDON_ROOT / 'static'),
)


def _resolve_location_code() -> int:
    loc = session.get('location_code')
    try:
        if loc is not None and str(loc).isdigit():
            return int(loc)
    except Exception:
        pass
    try:
        info = get_location_info_by_dbkey(None)
        if info and info.get('locationcode') is not None:
            return int(info['locationcode'])
    except Exception:
        pass
    return 1


def _schema() -> ForecastSchema:
    return ForecastSchema.build(_resolve_location_code())


def _openai_configured() -> bool:
    return bool((os.environ.get('OPENAI_API_KEY') or '').strip())


def _ctx(extra: Dict[str, Any] | None = None) -> Dict[str, Any]:
    loc = _resolve_location_code()
    base = {
        'location_code': loc,
        'location_name': session.get('location_name') or '',
        'openai_configured': _openai_configured(),
    }
    if extra:
        base.update(extra)
    return base


@bp.before_request
def _require_login():
    if not session.get('user'):
        return redirect(url_for('auth.login'))


@bp.route('/')
def dashboard():
    return render_template('ai_forecast/dashboard.html', title='AI Forecast Cockpit', **_ctx())


@bp.route('/sales')
def sales_forecast_page():
    return render_template('ai_forecast/sales_forecast.html', title='Sales Forecast', **_ctx())


@bp.route('/purchase')
def purchase_forecast_page():
    return render_template('ai_forecast/purchase_forecast.html', title='Purchase Forecast', **_ctx())


@bp.route('/reorder')
def reorder_page():
    return render_template('ai_forecast/reorder.html', title='Smart Reorder', **_ctx())


@bp.route('/products')
def products_page():
    return render_template('ai_forecast/products.html', title='Product Performance', **_ctx())


@bp.route('/suppliers')
def suppliers_page():
    return render_template('ai_forecast/suppliers.html', title='Supplier Performance', **_ctx())


@bp.route('/customers')
def customers_page():
    return render_template('ai_forecast/customers.html', title='Customer Analysis', **_ctx())


AI_REPORT_TYPES: List[Dict[str, str]] = [
    {'id': 'reorder', 'label': 'Reorder Report'},
    {'id': 'sales_forecast', 'label': 'Sales Forecast'},
    {'id': 'purchase_forecast', 'label': 'Purchase Forecast'},
    {'id': 'dead_stock', 'label': 'Dead Stock'},
    {'id': 'fast_moving', 'label': 'Fast Moving'},
    {'id': 'supplier_analysis', 'label': 'Supplier Analysis'},
    {'id': 'customer_pattern', 'label': 'Customer Pattern'},
]


@bp.route('/reports')
def reports_page():
    report = (request.args.get('type') or 'reorder').strip()
    valid = {t['id'] for t in AI_REPORT_TYPES}
    if report not in valid:
        report = 'reorder'
    return render_template(
        'ai_forecast/reports.html',
        title='AI Reports',
        report_type=report,
        report_types=AI_REPORT_TYPES,
        api_report_url=url_for('ai_forecast.api_report', report_type=report),
        export_url=url_for('ai_forecast.reports_export', type=report),
        **_ctx(),
    )


@bp.route('/api/dashboard')
def api_dashboard():
    try:
        data = get_insights_dashboard(_schema())
        return jsonify({'success': True, **data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)[:500]}, 500)


@bp.route('/api/sales-forecast')
def api_sales_forecast():
    try:
        horizon = int(request.args.get('horizon') or 30)
        data = get_sales_forecast(_schema(), horizon_days=max(7, min(horizon, 365)))
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)[:500]}, 500)


@bp.route('/api/purchase-forecast')
def api_purchase_forecast():
    try:
        data = get_purchase_forecast(_schema())
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)[:500]}, 500)


@bp.route('/api/reorder')
def api_reorder():
    try:
        rows = get_reorder_recommendations(_schema(), limit=int(request.args.get('limit') or 200))
        return jsonify({'success': True, 'rows': rows})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)[:500]}, 500)


@bp.route('/api/products')
def api_products():
    try:
        rows = get_product_performance(_schema(), limit=int(request.args.get('limit') or 100))
        return jsonify({'success': True, 'rows': rows})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)[:500]}, 500)


@bp.route('/api/suppliers')
def api_suppliers():
    try:
        rows = get_supplier_performance(_schema(), limit=int(request.args.get('limit') or 100))
        return jsonify({'success': True, 'rows': rows})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)[:500]}, 500)


@bp.route('/api/customers')
def api_customers():
    try:
        data = get_customer_analysis(_schema(), limit=int(request.args.get('limit') or 100))
        return jsonify({'success': True, **data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)[:500]}, 500)


@bp.route('/api/reports/<report_type>')
def api_report(report_type: str):
    try:
        data = get_report(_schema(), report_type)
        if data.get('error'):
            return jsonify({'success': False, **data}, 400)
        rows = data.get('rows') or []
        if isinstance(data.get('data'), dict):
            nested = data['data']
            if 'item_demand_forecast' in nested:
                rows = nested.get('item_demand_forecast') or rows
            elif 'customers' in nested:
                rows = nested.get('customers') or rows
            elif 'reorder_list' in nested:
                rows = nested.get('reorder_list') or rows
        return jsonify({
            'success': True,
            'report_type': report_type,
            'row_count': len(rows) if isinstance(rows, list) else 0,
            **data,
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)[:500]}, 500)


def _report_rows_for_export(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    if payload.get('rows'):
        return list(payload['rows'])
    data = payload.get('data')
    if not isinstance(data, dict):
        return []
    for key in ('item_demand_forecast', 'customers', 'reorder_list', 'overstock_items', 'fast_moving_items'):
        if data.get(key):
            return list(data[key])
    return []


@bp.route('/reports/export')
def reports_export():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    report_type = (request.args.get('type') or 'reorder').strip()
    try:
        payload = get_report(_schema(), report_type)
        if payload.get('error'):
            return Response(payload['error'], status=400, mimetype='text/plain')
        rows = _report_rows_for_export(payload)
        if not rows and isinstance(payload.get('data'), dict):
            buf = io.StringIO()
            buf.write('\ufeff')
            w = csv.writer(buf)
            w.writerow(['section', 'key', 'value'])
            for k, v in payload['data'].items():
                if isinstance(v, (list, dict)):
                    w.writerow(['data', k, json.dumps(v, default=str)[:32000]])
                else:
                    w.writerow(['data', k, v])
            content = buf.getvalue()
        else:
            buf = io.StringIO()
            buf.write('\ufeff')
            if rows:
                keys: List[str] = []
                for row in rows:
                    if isinstance(row, dict):
                        for k in row.keys():
                            if k not in keys:
                                keys.append(k)
                w = csv.DictWriter(buf, fieldnames=keys, extrasaction='ignore')
                w.writeheader()
                for row in rows:
                    if isinstance(row, dict):
                        w.writerow({k: row.get(k) for k in keys})
            else:
                buf.write('No rows\n')
            content = buf.getvalue()
        fname = f"ai_report_{report_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        return Response(content, mimetype='text/csv; charset=utf-8', headers={
            'Content-Disposition': f'attachment; filename={fname}',
        })
    except Exception as e:
        return Response(str(e)[:500], status=500, mimetype='text/plain')


@bp.route('/api/insights/narrative', methods=['POST'])
def api_insights_narrative():
    if not _openai_configured():
        return jsonify({'success': False, 'error': 'OPENAI_API_KEY is not configured.'}, 503)
    try:
        from openai import OpenAI

        payload = get_insights_dashboard(_schema())
        blob = json.dumps(payload, default=str)[:24000]
        model = (os.environ.get('OPENAI_MODEL') or 'gpt-4o-mini').strip()
        client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY', '').strip(), timeout=60.0)
        completion = client.chat.completions.create(
            model=model,
            temperature=0.25,
            messages=[
                {
                    'role': 'system',
                    'content': (
                        'You are an ERP forecasting analyst. Summarize the JSON insights in markdown: '
                        'sales outlook, purchase/reorder priorities, risks, and top 5 actions. Use numbers from JSON only.'
                    ),
                },
                {'role': 'user', 'content': blob},
            ],
            max_tokens=800,
        )
        text = (completion.choices[0].message.content or '').strip()
        return jsonify({'success': True, 'narrative': text})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)[:400]}, 500)
