"""Dashboard blueprint"""
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional
import io
from nexa_http import Blueprint, jsonify, redirect, render_template, session, request, url_for, Response
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, A4, landscape
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
from db import _fetch_rows, _get_connection, _detect_column, _get_table_columns, _table_exists
_ADDON_ROOT = Path(__file__).resolve().parents[1]
bp = Blueprint('dashboard', __name__, template_folder=str(_ADDON_ROOT / 'views' / 'templates'))

def _detect_table(candidates: list) -> str:
    """Return first table name that exists."""
    for table_name in candidates:
        try:
            if _get_table_columns(table_name):
                return table_name
        except Exception:
            continue
    return ''

@bp.route('/')
def index():
    if session.get('user'):
        return redirect(url_for('dashboard.dashboard'))
    return redirect(url_for('auth.login'))

@bp.route('/dashboard')
def dashboard():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    return render_template('dashboard/dashboard.html')

@bp.route('/dbkey/switch', methods=['POST'])
def switch_dbkey():
    """Switch current tenant (multi-DB). Allowed for admin or users with multilocations_view. Sets session tenant_id and clears location so next request refetches."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    from db import get_user_multilocations_view, get_tenant_list, get_user_allowed_tenant_ids
    can_switch = session.get('user') == 'admin' or get_user_multilocations_view(session.get('user')) == 'Y'
    if not can_switch:
        return redirect(url_for('dashboard.dashboard'))
    new_dbkey = (request.form.get('dbkey') or '').strip()
    if not new_dbkey:
        return redirect(url_for('dashboard.dashboard'))
    tenants = get_tenant_list()
    tenant_ids = [str(t.get('tenant_id') or '').strip() for t in tenants if t.get('tenant_id')]
    tenant_ids_lower = [tid.lower() for tid in tenant_ids]
    if new_dbkey.lower() not in tenant_ids_lower:
        return redirect(url_for('dashboard.dashboard'))
    match_idx = tenant_ids_lower.index(new_dbkey.lower())
    new_dbkey = tenant_ids[match_idx]
    u = session.get('user')
    if u and str(u).strip().lower() != 'admin':
        allowed = get_user_allowed_tenant_ids(str(u))
        if allowed:
            allow_set = {a.lower() for a in allowed}
            if new_dbkey.lower() not in allow_set:
                return redirect(url_for('dashboard.dashboard'))
    session['tenant_id'] = new_dbkey
    session.pop('location_name', None)
    session.pop('location_code', None)
    return redirect(url_for('dashboard.dashboard'))
