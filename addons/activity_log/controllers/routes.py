"""Master activity log list (tenant DB)."""
from pathlib import Path
from nexa_http import Blueprint, redirect, render_template, request, session, url_for
from master_activity_log import fetch_master_activity_log
_ADDON_ROOT = Path(__file__).resolve().parents[1]
bp = Blueprint('activity_log', __name__, template_folder=str(_ADDON_ROOT / 'views' / 'templates'))
MASTER_ACTIVITY_ENTITY_FILTERS = [('customer', 'Customer'), ('supplier', 'Vendor'), ('salesman', 'Salesman'), ('route', 'Route'), ('customer_category', 'Cust. category'), ('employee', 'Employee'), ('session_master', 'Session'), ('item_category_master', 'Inventory category'), ('item_brand_master', 'Brand / shelf / color'), ('unit_of_measurement', 'Unit of measurement'), ('item_property', 'Item property'), ('item_origin', 'Item origin'), ('itemmaster_central', 'Itemmaster Central (HO)'), ('itemmaster_branch', 'Item Master (branch)'), ('temporary_collection', 'Temporary Collection')]

@bp.route('/master/activity-log')
def activity_log_page():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    ent = (request.args.get('entity') or '').strip()[:96] or None
    match_raw = (request.args.get('match') or '').strip().lower()
    use_exact = match_raw == 'exact'
    limit = 600
    if ent:
        if use_exact:
            rows = fetch_master_activity_log(entity_exact=ent, limit=limit)
        else:
            rows = fetch_master_activity_log(entity_prefix=ent, limit=limit)
    else:
        rows = fetch_master_activity_log(limit=limit)
    return render_template('activity_log/activity_log.html', rows=rows, filter_entity=ent or '', filter_match_exact=use_exact, entity_filters=MASTER_ACTIVITY_ENTITY_FILTERS)
