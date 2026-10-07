"""Setup — Transaction date (TBLTRANSACTIONDATE)."""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from nexa_http import Blueprint, abort, jsonify, redirect, render_template, request, session, url_for

from addons.transaction_date_setup.transaction_date_db import (
    TXN_DATE_MODULES,
    build_setup_payload,
    close_transaction_date_setup,
    save_transaction_date_setup,
)
from db import get_role_permissions, get_user_role_id, list_location_master_rows

_ADDON = Path(__file__).resolve().parents[1]
bp = Blueprint(
    'transaction_date_setup',
    __name__,
    url_prefix='/setup',
    template_folder=str(_ADDON / 'views' / 'templates'),
)


def _allowed() -> bool:
    u = (session.get('user') or '').strip().lower()
    if u in ('admin', 'super'):
        return True
    try:
        rid = get_user_role_id(session.get('user'))
        if not rid:
            return False
        perms = get_role_permissions(rid) or []
        return 'setup.transaction_date_setup' in perms
    except Exception:
        return False


def _is_txn_date_admin() -> bool:
    """Admin/super, or roles with ``setup.transaction_date_change_any``, may open
    past/closed business days (TDS rules only).

    Does not bypass Period Closing — closed accounting months stay locked.
    """
    u = (session.get('user') or '').strip().lower()
    if u in ('admin', 'super'):
        return True
    try:
        rid = get_user_role_id(session.get('user'))
        if not rid:
            return False
        perms = get_role_permissions(rid) or []
        return 'setup.transaction_date_change_any' in perms
    except Exception:
        return False


def _location_options() -> list:
    rows = list_location_master_rows() or []
    out = []
    for r in rows:
        lc = r.get('locationcode')
        nm = str(r.get('locationname') or '').strip()
        if lc is not None and str(lc).strip() != '':
            out.append({'code': int(lc), 'label': f'{lc} — {nm}' if nm else str(lc)})
    return out


def _resolve_location_from_request() -> int:
    raw = (request.args.get('location_code') or request.form.get('location_code') or '').strip()
    if not raw:
        raw = str(session.get('location_code') or '').strip()
    try:
        return int(raw)
    except (TypeError, ValueError):
        opts = _location_options()
        if opts:
            return int(opts[0]['code'])
        return 1


@bp.route('/transaction-date', methods=['GET'])
def transaction_date_setup_page():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _allowed():
        abort(403)
    locations = _location_options()
    location_code = _resolve_location_from_request()
    return render_template(
        'transaction_date_setup/transaction_date_setup.html',
        title='Transaction Date Setup',
        locations=locations,
        location_code=location_code,
        modules=TXN_DATE_MODULES,
        api_bootstrap_url=url_for('transaction_date_setup.transaction_date_api_bootstrap'),
        api_save_url=url_for('transaction_date_setup.transaction_date_api_save'),
        api_close_url=url_for('transaction_date_setup.transaction_date_api_close'),
        is_txn_date_admin=_is_txn_date_admin(),
    )


@bp.route('/transaction-date/api/bootstrap', methods=['GET'])
def transaction_date_api_bootstrap():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    if not _allowed():
        return jsonify({'success': False, 'error': 'Forbidden'}, 403)
    try:
        lc = int(request.args.get('location_code') or _resolve_location_from_request())
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Invalid location'}, 400)
    payload = build_setup_payload(lc, allow_any_date=_is_txn_date_admin())
    return jsonify({'success': True, **payload})


@bp.route('/transaction-date/api/save', methods=['POST'])
def transaction_date_api_save():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    if not _allowed():
        return jsonify({'success': False, 'error': 'Forbidden'}, 403)
    data = request.get_json(silent=True) or {}
    try:
        lc = int(data.get('location_code') or _resolve_location_from_request())
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Invalid location'}, 400)
    mode = str(data.get('mode') or 'all').strip().lower()
    if mode not in ('all', 'separate'):
        return jsonify({'success': False, 'error': 'Mode must be all or separate.'}, 400)
    all_date = str(data.get('all_date') or '').strip()
    all_date_from = str(data.get('all_date_from') or data.get('all_from') or all_date or '').strip()
    all_date_to = str(data.get('all_date_to') or data.get('all_to') or all_date_from or '').strip()
    module_dates = data.get('module_dates') if isinstance(data.get('module_dates'), dict) else {}
    module_date_from = data.get('module_date_from') if isinstance(data.get('module_date_from'), dict) else {}
    module_date_to = data.get('module_date_to') if isinstance(data.get('module_date_to'), dict) else {}
    module_codes = {mod['key']: int(mod['default_code']) for mod in TXN_DATE_MODULES}
    opened_by = (session.get('user') or 'SYSTEM').strip()
    ok, msg, warnings = save_transaction_date_setup(
        lc,
        mode=mode,
        all_date=all_date or all_date_from,
        all_date_from=all_date_from,
        all_date_to=all_date_to,
        module_dates=module_dates,
        module_date_from={str(k): str(v) for k, v in module_date_from.items()},
        module_date_to={str(k): str(v) for k, v in module_date_to.items()},
        module_codes=module_codes,
        opened_by=opened_by,
        skip_restrictions=_is_txn_date_admin(),
    )
    if not ok:
        return jsonify({'success': False, 'error': msg, 'warnings': warnings}, 400)
    payload = build_setup_payload(lc, allow_any_date=_is_txn_date_admin())
    return jsonify({'success': True, 'message': msg, 'warnings': warnings, **payload})


@bp.route('/transaction-date/api/close', methods=['POST'])
def transaction_date_api_close():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    if not _allowed():
        return jsonify({'success': False, 'error': 'Forbidden'}, 403)
    data = request.get_json(silent=True) or {}
    try:
        lc = int(data.get('location_code') or _resolve_location_from_request())
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Invalid location'}, 400)
    mode = str(data.get('mode') or 'all').strip().lower()
    if mode not in ('all', 'separate'):
        return jsonify({'success': False, 'error': 'Mode must be all or separate.'}, 400)
    raw_keys = data.get('module_keys')
    module_keys: Optional[List[str]] = None
    if isinstance(raw_keys, list):
        module_keys = [str(k).strip() for k in raw_keys if str(k).strip()]
    closed_by = (session.get('user') or 'SYSTEM').strip()
    ok, msg, warnings = close_transaction_date_setup(
        lc,
        mode=mode,
        module_keys=module_keys,
        closed_by=closed_by,
    )
    if not ok:
        return jsonify({'success': False, 'error': msg, 'warnings': warnings}, 400)
    payload = build_setup_payload(lc, allow_any_date=_is_txn_date_admin())
    return jsonify({'success': True, 'message': msg, 'warnings': warnings, **payload})
