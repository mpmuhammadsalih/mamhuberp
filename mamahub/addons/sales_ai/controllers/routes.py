"""Sales AI dashboard routes."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from nexa_http import Blueprint, jsonify, redirect, render_template, request, session, url_for

from addons.sales_ai.services.sales_ai_engine import (
    build_sales_ai_dashboard,
    get_sales_ai_filter_options,
    parse_sales_ai_filters,
)
from db import get_location_info_by_dbkey

_ADDON_ROOT = Path(__file__).resolve().parents[1]
bp = Blueprint(
    'sales_ai',
    __name__,
    url_prefix='/sales-ai',
    template_folder=str(_ADDON_ROOT / 'views' / 'templates'),
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


def _apply_tenant():
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        from db import _apply_active_connection
        _apply_active_connection(user_dbkey)


def _openai_configured() -> bool:
    return bool((os.environ.get('OPENAI_API_KEY') or '').strip())


@bp.before_request
def _require_login():
    if not session.get('user'):
        return redirect(url_for('auth.login'))


@bp.route('/')
def dashboard():
    _apply_tenant()
    loc = _resolve_location_code()
    filters = parse_sales_ai_filters(dict(request.args))
    if not filters.get('date_from'):
        filters['date_from'] = f"{datetime.now().year}-01-01"
    if not filters.get('date_to'):
        filters['date_to'] = datetime.now().strftime('%Y-%m-%d')
    filters['locationcode'] = filters.get('branch') or loc
    options = get_sales_ai_filter_options(filters['locationcode'])
    return render_template(
        'sales_ai/dashboard.html',
        title='Sales AI Dashboard',
        filters=filters,
        options=options,
        location_code=loc,
        location_name=session.get('location_name') or '',
        openai_configured=_openai_configured(),
        api_data_url=url_for('sales_ai.api_dashboard'),
        api_narrative_url=url_for('sales_ai.api_narrative') if _openai_configured() else '',
    )


@bp.route('/api/dashboard', methods=['GET'])
def api_dashboard():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    _apply_tenant()
    payload = build_sales_ai_dashboard(dict(request.args))
    return jsonify(payload)


@bp.route('/api/narrative', methods=['POST'])
def api_narrative():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    if not _openai_configured():
        return jsonify({'success': False, 'error': 'OPENAI_API_KEY is not configured.'}), 503
    _apply_tenant()
    try:
        from openai import OpenAI

        payload = build_sales_ai_dashboard(dict(request.args))
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
                        'You are an ERP sales analyst. Summarize the JSON dashboard in markdown: '
                        'KPI highlights, forecast outlook, category/brand focus, salesperson coaching, '
                        'and top 5 daily actions. Use numbers from JSON only.'
                    ),
                },
                {'role': 'user', 'content': blob},
            ],
            max_tokens=900,
        )
        text = (completion.choices[0].message.content or '').strip()
        return jsonify({'success': True, 'narrative': text})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)[:400]}), 500
