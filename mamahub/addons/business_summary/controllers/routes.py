"""Daily Business Summary dashboard routes."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from nexa_http import Blueprint, jsonify, redirect, render_template, request, session, url_for

from addons.business_summary.services.business_summary_engine import (
    build_business_summary_dashboard,
    get_business_summary_filter_options,
    parse_business_summary_filters,
)
from db import get_location_info_by_dbkey, set_active_db_key, set_active_db_host, DATABASES

_ADDON_ROOT = Path(__file__).resolve().parents[1]
bp = Blueprint(
    'business_summary',
    __name__,
    url_prefix='/business-summary',
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


def _normalize_db_key(db_key: str) -> str:
    key = str(db_key or '').strip().upper()
    if key == 'TESTDB':
        return 'TESDB'
    return key


def _apply_tenant():
    dbkey = _normalize_db_key(
        request.args.get('dbkey') or session.get('tenant_id') or session.get('dbkey') or ''
    )
    if dbkey and dbkey in DATABASES:
        set_active_db_key(dbkey)
        set_active_db_host(None)
    elif session.get('tenant_id'):
        key = _normalize_db_key(session.get('tenant_id'))
        if key in DATABASES:
            set_active_db_key(key)
        else:
            set_active_db_key('HO')
        set_active_db_host(None)


@bp.before_request
def _require_login():
    if not session.get('user'):
        return redirect(url_for('auth.login'))


@bp.route('/')
def dashboard():
    _apply_tenant()
    loc = _resolve_location_code()
    filters = parse_business_summary_filters(dict(request.args))
    if not request.args.get('date_from'):
        filters['date_from'] = datetime.now().replace(day=1).strftime('%Y-%m-%d')
    if not request.args.get('date_to'):
        filters['date_to'] = datetime.now().strftime('%Y-%m-%d')
    if not filters.get('branch'):
        filters['branch'] = loc
    options = get_business_summary_filter_options(filters.get('branch') or loc)
    return render_template(
        'business_summary/dashboard.html',
        title='Daily Business Summary',
        filters=filters,
        options=options,
        location_code=loc,
        location_name=session.get('location_name') or '',
        api_data_url=url_for('business_summary.api_dashboard'),
    )


@bp.route('/api/dashboard', methods=['GET'])
def api_dashboard():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    _apply_tenant()
    try:
        payload = build_business_summary_dashboard(dict(request.args))
        return jsonify(payload)
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)[:500]}), 500
