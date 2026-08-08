"""Setup — DBA Tools: list tables, show lock status, release table locks."""
from __future__ import annotations

from pathlib import Path

from nexa_http import Blueprint, abort, jsonify, redirect, render_template, request, session, url_for

from addons.dba_tools.dba_db import list_tables_with_lock_status, unlock_table
from db import get_role_permissions, get_user_role_id

_ADDON = Path(__file__).resolve().parents[1]
bp = Blueprint(
    'dba_tools',
    __name__,
    url_prefix='/setup',
    template_folder=str(_ADDON / 'views' / 'templates'),
)

_PERM = 'setup.dba_tools'


def _is_admin() -> bool:
    return (session.get('user') or '').strip().lower() in ('admin', 'super')


def _allowed() -> bool:
    if _is_admin():
        return True
    try:
        rid = get_user_role_id(session.get('user'))
        if not rid:
            return False
        perms = get_role_permissions(rid) or []
        return _PERM in perms
    except Exception:
        return False


@bp.route('/dba', methods=['GET'])
def dba_page():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _allowed():
        abort(403)
    return render_template(
        'dba_tools/dba.html',
        title='DBA — Table Locks',
        api_tables_url=url_for('dba_tools.dba_api_tables'),
        api_unlock_url=url_for('dba_tools.dba_api_unlock'),
        can_unlock=_is_admin(),
    )


@bp.route('/dba/api/tables', methods=['GET'])
def dba_api_tables():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    if not _allowed():
        return jsonify({'success': False, 'error': 'Forbidden'}, 403)
    search = (request.args.get('search') or '').strip()
    try:
        payload = list_tables_with_lock_status(search=search)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}, 500)
    return jsonify({'success': True, **payload})


@bp.route('/dba/api/unlock', methods=['POST'])
def dba_api_unlock():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    # Releasing locks kills sessions — restrict to admin/super only.
    if not _is_admin():
        return jsonify({'success': False, 'error': 'Only admin can release locks.'}, 403)
    data = request.get_json(silent=True) or {}
    table_name = str(data.get('table_name') or '').strip()
    if not table_name:
        return jsonify({'success': False, 'error': 'Table name is required.'}, 400)
    try:
        result = unlock_table(table_name)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}, 500)
    status = 200 if result.get('success') else 400
    return jsonify(result, status)
