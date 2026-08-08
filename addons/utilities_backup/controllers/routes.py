"""Utilities — database backup (schema DDL export)."""
import io
from pathlib import Path

from config.settings import is_multi_db_mode
from nexa_http import Blueprint, abort, flash, redirect, render_template, request, send_file, session, url_for

from addons.utilities_backup.services.backup import (
    datapump_command_hint,
    export_schema_ddl,
    list_backup_files,
    resolve_backup_targets,
    resolve_download_path,
    save_backup_file,
)

_ADDON = Path(__file__).resolve().parents[1]
bp = Blueprint('utilities_backup', __name__, url_prefix='/utilities', template_folder=str(_ADDON / 'views' / 'templates'))


def _allowed() -> bool:
    u = (session.get('user') or '').strip().lower()
    if u in ('admin', 'super'):
        return True
    try:
        from permissions import get_role_permissions
        from db import get_user_role_id
        rid = get_user_role_id(session.get('user'))
        if not rid:
            return False
        perms = get_role_permissions(rid) or []
        return 'utilities.backup' in perms
    except Exception:
        return False


@bp.route('/backup', methods=('GET', 'POST'))
def backup_page():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _allowed():
        abort(403)

    targets = resolve_backup_targets(dict(session))
    default_target = targets[0]['key'] if targets else 'business'
    expdp_hint = ''

    if request.method == 'POST':
        action = (request.form.get('action') or '').strip()
        target_key = (request.form.get('target') or default_target).strip()
        if action == 'export_schema':
            try:
                sql_text, fname = export_schema_ddl(target_key, dict(session))
                save_backup_file(sql_text, fname)
                flash(f'Schema backup saved as {fname}.', 'success')
                return redirect(url_for('utilities_backup.backup_download', filename=fname))
            except Exception as ex:
                flash(f'Schema export failed: {ex}', 'error')
        elif action == 'show_expdp':
            try:
                expdp_hint = datapump_command_hint(target_key, dict(session))
            except Exception as ex:
                flash(f'Could not build Data Pump command: {ex}', 'error')
        else:
            flash('Unknown action.', 'error')

    backups = list_backup_files()
    return render_template(
        'backup.html',
        title='Database backup',
        targets=targets,
        default_target=default_target,
        backups=backups,
        expdp_hint=expdp_hint,
        is_multi_db=is_multi_db_mode(),
    )


@bp.route('/backup/download/<path:filename>', methods=('GET',))
def backup_download(filename: str):
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _allowed():
        abort(403)
    path = resolve_download_path(filename)
    if not path:
        abort(404)
    return send_file(
        io.BytesIO(path.read_bytes()),
        mimetype='application/octet-stream',
        as_attachment=True,
        download_name=path.name,
    )
