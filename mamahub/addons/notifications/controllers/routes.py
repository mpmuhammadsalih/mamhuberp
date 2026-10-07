"""Notifications blueprint: user-facing alerts and lists (e.g. my outstanding due)."""
from pathlib import Path
from nexa_http import Blueprint, redirect, render_template, session, url_for
from db import get_employee_outstanding_details
_ADDON_ROOT = Path(__file__).resolve().parents[1]
bp = Blueprint('notifications', __name__, template_folder=str(_ADDON_ROOT / 'views' / 'templates'))

@bp.route('/notifications/outstanding-due', methods=['GET'])
def outstanding_due():
    """Outstanding due details for the current user (session employeecode) from tblsettlement."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    employeecode = session.get('employeecode')
    if not employeecode:
        return render_template('notifications/notifications_outstanding_due.html', rows=[], employeecode=None, no_employeecode=True)
    rows = get_employee_outstanding_details(str(employeecode).strip(), 'all', salesmancode=None, customercode=None, date_from=None, date_to=None, expecteddate_from=None, expecteddate_to=None)
    return render_template('notifications/notifications_outstanding_due.html', rows=rows, employeecode=str(employeecode).strip(), no_employeecode=False)
