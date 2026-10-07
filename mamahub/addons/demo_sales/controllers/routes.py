"""Flask routes for the demo_sales addon (one Blueprint = one logical app area)."""
from __future__ import annotations
from pathlib import Path
from nexa_http import Blueprint, redirect, render_template, session, url_for
from addons.demo_sales.services import dashboard as dash_svc
_ADDON_ROOT = Path(__file__).resolve().parents[1]
bp = Blueprint('demo_sales', __name__, url_prefix='/demo-sales', template_folder=str(_ADDON_ROOT / 'views' / 'templates'), static_folder=str(_ADDON_ROOT / 'static'))

@bp.before_request
def _require_login():
    if not session.get('user'):
        return redirect(url_for('auth.login'))

@bp.route('/')
def dashboard():
    data = dash_svc.get_dashboard_kpis()
    return render_template('demo_sales/dashboard.html', title='Demo Sales — Cockpit', kpi=data)

@bp.route('/orders')
def orders():
    snap = dash_svc.get_orders_snapshot()
    return render_template('demo_sales/orders.html', title='Demo Sales — Orders', orders=snap.get('rows') or [])

@bp.route('/pipeline')
def pipeline():
    pipe = dash_svc.get_pipeline_stages()
    return render_template('demo_sales/pipeline.html', title='Demo Sales — Pipeline', stages=pipe.get('stages') or [])
