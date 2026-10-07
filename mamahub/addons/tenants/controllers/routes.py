"""Tenants blueprint - create and list tenant databases (auth DB)."""
from pathlib import Path
import os
from datetime import datetime
from nexa_http import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.utils import secure_filename
from db import create_tenant, get_tenant_by_id, get_tenants_list, update_tenant
_ADDON_ROOT = Path(__file__).resolve().parents[1]
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
bp = Blueprint('tenants', __name__, template_folder=str(_ADDON_ROOT / 'views' / 'templates'))
_ALLOWED_LOGO_EXT = {'.png', '.jpg', '.jpeg', '.webp'}

def _save_tenant_logo(upload, tenant_id: str) -> str:
    if not upload or not getattr(upload, 'filename', ''):
        return ''
    original = str(upload.filename or '').strip()
    ext = os.path.splitext(original)[1].lower()
    if ext not in _ALLOWED_LOGO_EXT:
        raise ValueError('Logo must be PNG, JPG, JPEG, or WEBP.')
    safe_tenant = secure_filename((tenant_id or 'tenant').strip()) or 'tenant'
    stamp = datetime.now().strftime('%Y%m%d%H%M%S')
    filename = f'{safe_tenant}_{stamp}{ext}'
    target_dir = _PROJECT_ROOT / 'static' / 'uploads' / 'tenant_logos'
    target_dir.mkdir(parents=True, exist_ok=True)
    full_path = str((target_dir / filename).resolve())
    upload.save(full_path)
    return f'uploads/tenant_logos/{filename}'

@bp.route('/tenants')
def tenant_list():
    """List all tenants."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    tenants = get_tenants_list()
    return render_template('tenants/tenant_list.html', tenants=tenants)

@bp.route('/tenants/create', methods=['GET', 'POST'])
def tenant_create():
    """Create a new tenant (database connection)."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if request.method == 'POST':
        tenant_id = (request.form.get('tenant_id') or '').strip()
        ip = (request.form.get('ip') or '').strip()
        port = (request.form.get('port') or '').strip()
        service_name = (request.form.get('service_name') or '').strip()
        display_name = (request.form.get('display_name') or '').strip() or None
        network_link = (request.form.get('network_link') or '').strip() or None
        username = (request.form.get('username') or '').strip() or None
        password = (request.form.get('password') or '').strip() or None
        loc_str = (request.form.get('locationcode') or '').strip()
        locationcode = None
        if loc_str:
            try:
                locationcode = int(loc_str)
            except ValueError:
                flash('Location code must be a number.', 'error')
                return render_template('tenants/tenant_create.html')
        active_flag = (request.form.get('active_flag') or 'Y').strip().upper()
        if active_flag not in ('Y', 'N'):
            active_flag = 'Y'
        logo_path = ''
        logo_file = request.files.get('logo')
        if logo_file and str(logo_file.filename or '').strip():
            try:
                logo_path = _save_tenant_logo(logo_file, tenant_id)
            except ValueError as exc:
                flash(str(exc), 'error')
                return render_template('tenants/tenant_create.html')
            except Exception:
                flash('Failed to upload tenant logo.', 'error')
                return render_template('tenants/tenant_create.html')
        try:
            create_tenant(tenant_id=tenant_id, ip=ip, port=port, service_name=service_name, display_name=display_name, network_link=network_link, username=username, password=password, logo_path=logo_path or None, locationcode=locationcode, active_flag=active_flag)
            flash('Tenant created successfully.', 'success')
            return redirect(url_for('tenants.tenant_list'))
        except ValueError as exc:
            flash(str(exc), 'error')
        except Exception as exc:
            flash(f'Could not create tenant: {exc}', 'error')
    return render_template('tenants/tenant_create.html')

@bp.route('/tenants/<tenant_id>/edit', methods=['GET', 'POST'])
def tenant_edit(tenant_id: str):
    """Edit an existing tenant (database connection)."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    tenant = get_tenant_by_id(tenant_id)
    if not tenant:
        flash('Tenant not found.', 'error')
        return redirect(url_for('tenants.tenant_list'))
    if request.method == 'POST':
        ip = (request.form.get('ip') or '').strip()
        port = (request.form.get('port') or '').strip()
        service_name = (request.form.get('service_name') or '').strip()
        display_name = (request.form.get('display_name') or '').strip() or None
        network_link = (request.form.get('network_link') or '').strip() or None
        username = (request.form.get('username') or '').strip() or None
        password_raw = (request.form.get('password') or '').strip()
        password = password_raw if password_raw else None
        loc_str = (request.form.get('locationcode') or '').strip()
        locationcode = None
        if loc_str:
            try:
                locationcode = int(loc_str)
            except ValueError:
                flash('Location code must be a number.', 'error')
                tenant = dict(tenant or {})
                tenant['ip'] = ip
                tenant['port'] = port
                tenant['service_name'] = service_name
                tenant['display_name'] = display_name
                tenant['network_link'] = network_link
                tenant['username'] = username
                tenant['locationcode'] = loc_str or None
                tenant['active_flag'] = request.form.get('active_flag') or 'Y'
                return render_template('tenants/tenant_edit.html', tenant=tenant)
        active_flag = (request.form.get('active_flag') or 'Y').strip().upper()
        if active_flag not in ('Y', 'N'):
            active_flag = 'Y'
        logo_path = None
        logo_file = request.files.get('logo')
        if logo_file and str(logo_file.filename or '').strip():
            try:
                logo_path = _save_tenant_logo(logo_file, tenant_id)
            except ValueError as exc:
                flash(str(exc), 'error')
                tenant = dict(tenant or {})
                tenant['ip'] = ip
                tenant['port'] = port
                tenant['service_name'] = service_name
                tenant['display_name'] = display_name
                tenant['network_link'] = network_link
                tenant['username'] = username
                tenant['locationcode'] = locationcode
                tenant['active_flag'] = active_flag
                return render_template('tenants/tenant_edit.html', tenant=tenant)
            except Exception:
                flash('Failed to upload tenant logo.', 'error')
                tenant = dict(tenant or {})
                tenant['ip'] = ip
                tenant['port'] = port
                tenant['service_name'] = service_name
                tenant['display_name'] = display_name
                tenant['network_link'] = network_link
                tenant['username'] = username
                tenant['locationcode'] = locationcode
                tenant['active_flag'] = active_flag
                return render_template('tenants/tenant_edit.html', tenant=tenant)
        try:
            update_tenant(tenant_id=tenant_id, ip=ip, port=port, service_name=service_name, display_name=display_name, network_link=network_link, username=username, password=password, logo_path=logo_path, locationcode=locationcode, active_flag=active_flag)
            flash('Tenant updated successfully.', 'success')
            return redirect(url_for('tenants.tenant_list'))
        except ValueError as exc:
            flash(str(exc), 'error')
            tenant = dict(get_tenant_by_id(tenant_id) or tenant or {})
            tenant['ip'] = ip
            tenant['port'] = port
            tenant['service_name'] = service_name
            tenant['display_name'] = display_name
            tenant['network_link'] = network_link
            tenant['username'] = username
            tenant['locationcode'] = locationcode
            tenant['active_flag'] = active_flag
    return render_template('tenants/tenant_edit.html', tenant=tenant)
