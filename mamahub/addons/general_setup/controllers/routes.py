"""Setup — General organization options."""
from __future__ import annotations

from pathlib import Path

from nexa_http import Blueprint, abort, flash, redirect, render_template, request, session, url_for

from addons.ho.customer_alert_control import (
    get_customer_request_alert_poll_enabled,
    get_transaction_recording_enabled,
    set_customer_request_alert_poll_enabled,
    set_transaction_recording_enabled,
)

_ADDON = Path(__file__).resolve().parents[1]
bp = Blueprint(
    'general_setup',
    __name__,
    url_prefix='/setup',
    template_folder=str(_ADDON / 'views' / 'templates'),
)


def _allowed() -> bool:
    u = (session.get('user') or '').strip().lower()
    if u in ('admin', 'super'):
        return True
    try:
        from db import get_user_role_id
        from permissions import get_role_permissions

        rid = get_user_role_id(session.get('user'))
        if not rid:
            return False
        perms = get_role_permissions(rid) or []
        return 'setup.general_setup_page' in perms
    except Exception:
        return False


@bp.route('/general-setup', methods=['GET', 'POST'])
def general_setup_page():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _allowed():
        abort(403)

    if request.method == 'POST':
        poll_enabled = request.form.get('customer_request_alert_poll') == 'Y'
        recording_enabled = request.form.get('transaction_recording_enabled') == 'Y'
        user = session.get('user') or 'web'
        try:
            set_customer_request_alert_poll_enabled('HO', poll_enabled, user)
            set_transaction_recording_enabled('HO', recording_enabled, user)
            flash('General setup saved.', 'success')
        except Exception as exc:
            flash(f'Save failed: {exc}', 'error')
        return redirect(url_for('general_setup.general_setup_page'))

    poll_enabled = get_customer_request_alert_poll_enabled('HO')
    recording_enabled = get_transaction_recording_enabled('HO')
    return render_template(
        'general_setup/general_setup.html',
        title='General Setup',
        customer_request_alert_poll_enabled=poll_enabled,
        transaction_recording_enabled=recording_enabled,
    )
