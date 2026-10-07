"""System configuration blueprint"""
from pathlib import Path
import subprocess
from nexa_http import Blueprint, redirect, render_template, request, session, flash, url_for
from db import get_dbkeys_list, get_system_config, get_system_config_by_rowid, get_system_config_list, get_system_config_rows, get_next_countercode, save_system_config, delete_system_config_row, get_location_name_by_dbkey, get_locations_list, set_active_db_key, set_active_db_host
_ADDON_ROOT = Path(__file__).resolve().parents[1]
bp = Blueprint('system_config', __name__, template_folder=str(_ADDON_ROOT / 'views' / 'templates'))
DEFAULT_DB_KEY = 'HO'

def _get_bios_serial() -> str:
    try:
        result = subprocess.run(['powershell', '-NoProfile', '-Command', '(Get-CimInstance -ClassName Win32_BIOS).SerialNumber'], capture_output=True, text=True, check=False)
        return (result.stdout or '').strip()
    except Exception:
        return ''

@bp.route('/system-config', methods=['GET', 'POST'])
def system_config():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    db_key = DEFAULT_DB_KEY
    set_active_db_key(db_key)
    set_active_db_host(None)
    locations = get_dbkeys_list()
    if not locations:
        locations = get_locations_list()
    if not locations:
        locations = [{'code': 'default', 'name': 'Default'}]
    location_map = {str(loc.get('code')): loc.get('name') or '' for loc in locations}
    branch_codes = sorted(location_map.keys())
    if request.method == 'POST':
        row_id = (request.form.get('rowid') or '').strip()
        if not row_id:
            flash('Row ID is required.', 'error')
            return redirect(url_for('system_config.system_config_list'))
        payload = {'countername': (request.form.get('countername') or '').strip(), 'dblocation': (request.form.get('dblocation') or '').strip(), 'approved': (request.form.get('approved') or '').strip(), 'rowid': row_id}
        try:
            save_system_config(payload, db_key)
            flash('Counter configuration updated.', 'success')
            return redirect(url_for('system_config.system_config_list'))
        except ValueError as exc:
            flash(str(exc), 'error')
            return redirect(url_for('system_config.system_config', edit=row_id))
    edit_row_id = (request.args.get('edit') or '').strip()
    if not edit_row_id:
        flash('Please select a counter to edit.', 'error')
        return redirect(url_for('system_config.system_config_list'))
    config = get_system_config_by_rowid(edit_row_id, db_key)
    if not config:
        flash('Counter not found.', 'error')
        return redirect(url_for('system_config.system_config_list'))
    return render_template('system_config/system_config.html', config=config, locations=locations, branch_codes=branch_codes)

@bp.route('/system-config/list', methods=['GET'])
def system_config_list():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    db_key = DEFAULT_DB_KEY
    set_active_db_key(db_key)
    set_active_db_host(None)
    list_columns, config_list = get_system_config_rows(db_key)
    return render_template('system_config/system_config_list.html', config_list=config_list, list_columns=list_columns)

@bp.route('/system-config/delete', methods=['POST'])
def delete_system_config():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    db_key = DEFAULT_DB_KEY
    set_active_db_key(db_key)
    set_active_db_host(None)
    row_id = (request.form.get('rowid') or '').strip()
    if row_id:
        delete_system_config_row(row_id, db_key)
        flash('System configuration deleted.', 'success')
    else:
        flash('Nothing to delete.', 'warning')
    return redirect(url_for('system_config.system_config_list'))
