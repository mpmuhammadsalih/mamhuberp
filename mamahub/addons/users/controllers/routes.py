"""Users blueprint"""
from pathlib import Path
import csv
import io
from datetime import datetime
from typing import List, Optional
from nexa_http import Blueprint, jsonify, redirect, render_template, request, session, flash, url_for, Response
from db import create_user, get_all_roles, get_tenant_list, get_users_with_roles, get_user_by_username, update_user_role, update_user_account, user_exists, resolve_role_id_canonical
from db.user_warehouse_prefs import warehouse_prefs_from_mapping, warehouse_display_label, list_warehouse_picker_rows_for_tenant

def _normalize_allowed_tenant_ids_csv(raw_csv: str) -> Optional[str]:
    """Restrict to IDs present in Tenants maintenance; preserves master casing. Empty/unrestricted → None."""
    tenants = get_tenant_list() or []
    code_map = {}
    for t in tenants:
        cid = str(t.get('tenant_id') or '').strip()
        if not cid:
            continue
        code_map[cid.lower()] = cid
    parts_in = [p.strip() for p in (raw_csv or '').replace(';', ',').split(',') if p.strip()]
    out: List[str] = []
    seen = set()
    for p in parts_in:
        canon = code_map.get(p.lower())
        if not canon:
            continue
        lk = canon.lower()
        if lk not in seen:
            seen.add(lk)
            out.append(canon)
    if not out:
        return None
    return ','.join(out)[:2000]
_ADDON_ROOT = Path(__file__).resolve().parents[1]
bp = Blueprint('users', __name__, template_folder=str(_ADDON_ROOT / 'views' / 'templates'))

def _get_available_locations():
    """Single database: location list from get_locations_list or empty."""
    from db import get_locations_list
    rows = get_locations_list()
    return [str(r.get('code') or r.get('name') or '').strip() for r in rows if r.get('code') or r.get('name')]

@bp.route('/users')
def user_list():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    location_filter = request.args.get('location', '').strip() or None
    tenant_filter = request.args.get('tenant_id', '').strip() or None
    role_filter = request.args.get('role_id', '').strip() or None
    search_filter = request.args.get('search', '').strip() or None
    users = get_users_with_roles(location_filter=location_filter, tenant_filter=tenant_filter, role_filter=role_filter, search_filter=search_filter)
    available_locations = _get_available_locations()
    available_roles = get_all_roles()
    available_tenants = get_tenant_list()
    return render_template('users/user_list.html', users=users, location_filter=location_filter, tenant_filter=tenant_filter, role_filter=role_filter, search_filter=search_filter, available_locations=available_locations, available_roles=available_roles, available_tenants=available_tenants)

@bp.route('/users/export', methods=['GET'])
def user_export():
    """Export user list to Excel (CSV format), with applied list filters."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    location_filter = request.args.get('location', '').strip() or None
    tenant_filter = request.args.get('tenant_id', '').strip() or None
    role_filter = request.args.get('role_id', '').strip() or None
    search_filter = request.args.get('search', '').strip() or None
    users = get_users_with_roles(location_filter=location_filter, tenant_filter=tenant_filter, role_filter=role_filter, search_filter=search_filter)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Username', 'Employee Code', 'Tenant', 'Location', 'Role', 'Need Counter', 'Transit Only', 'Customer Creation', 'Status'])
    for u in users:
        role = (u.get('role_name') or u.get('role_id') or 'No role assigned') if u.get('role_id') else 'No role assigned'
        needcounter = 'Yes' if (u.get('needcounter') or 'N') == 'Y' else 'No'
        transit_only = 'Yes' if (u.get('transit_only') or 'N') == 'Y' else 'No'
        customer_creation = 'Yes' if (u.get('customer_creation') or 'N') == 'Y' else 'No'
        status = 'Active' if (u.get('active_flag') or 'Y') == 'Y' else 'Inactive'
        writer.writerow([u.get('username') or '', u.get('employeecode') or '', u.get('tenant_id') or '', u.get('location') or '', role, needcounter, transit_only, customer_creation, status])
    output.seek(0)
    filename = f"user_list_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename={filename}'})

@bp.route('/users/create', methods=['GET', 'POST'])
def user_create():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    available_roles = get_all_roles()
    available_tenants = get_tenant_list()
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        employeecode = request.form.get('employeecode', '').strip()
        needcounter = (request.form.get('needcounter') or '').strip()
        role_id = (request.form.get('role_id') or '').strip() or None
        tenant_id = (request.form.get('tenant_id') or '').strip() or None
        multilocations_view = (request.form.get('multilocations_view') or 'N').strip().upper()
        transit_only = 'Y' if (request.form.get('transit_only') or '').strip().upper() == 'Y' else 'N'
        customer_creation = 'Y' if (request.form.get('customer_creation') or '').strip().upper() == 'Y' else 'N'
        if multilocations_view not in ('Y', 'N'):
            multilocations_view = 'N'
        allowed_tid_csv = _normalize_allowed_tenant_ids_csv(request.form.get('allowed_tenant_ids') or '') if multilocations_view == 'Y' else None
        if not employeecode:
            flash('Employee Code is required.', 'error')
        elif employeecode.upper() != 'ADMIN' and (not employeecode.isdigit()):
            flash('Employee Code must be numeric.', 'error')
        elif not needcounter or needcounter not in ['Y', 'N']:
            flash('Need Counter is required. Please select Yes or No.', 'error')
        else:
            try:
                wh_prefs = warehouse_prefs_from_mapping(request.form)
                create_user(
                    username, password, employeecode, needcounter,
                    tenant_id=tenant_id, multilocations_view=multilocations_view, transit_only=transit_only,
                    customer_creation=customer_creation, allowed_tenant_ids=allowed_tid_csv,
                    **{f'default_wh_{k}': v for k, v in wh_prefs.items()},
                )
                if role_id:
                    update_user_role(username, role_id)
                flash('User created.', 'success')
                return redirect(url_for('users.user_list'))
            except ValueError as exc:
                flash(str(exc), 'error')
    return render_template(
        'users/user_create.html',
        available_roles=available_roles,
        available_tenants=available_tenants,
        employee_picker_api_url=url_for('users.api_employees_for_picker'),
        warehouses_api_url=url_for('users.api_user_warehouses'),
    )

@bp.route('/users/<username>/role', methods=['GET', 'POST'])
def user_edit_role(username: str):
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    roles = get_all_roles()
    available_tenants = get_tenant_list()
    if request.method == 'POST':
        role_id = (request.form.get('role_id') or '').strip() or None
        password = (request.form.get('password') or '').strip()
        needcounter = (request.form.get('needcounter') or 'N').strip().upper()
        if needcounter not in {'Y', 'N'}:
            needcounter = 'N'
        active_flag = (request.form.get('active_flag') or 'Y').strip().upper()
        if active_flag not in {'Y', 'N'}:
            active_flag = 'Y'
        tenant_id = (request.form.get('tenant_id') or '').strip() or None
        multilocations_view = (request.form.get('multilocations_view') or 'N').strip().upper()
        transit_only = 'Y' if (request.form.get('transit_only') or '').strip().upper() == 'Y' else 'N'
        customer_creation = 'Y' if (request.form.get('customer_creation') or '').strip().upper() == 'Y' else 'N'
        if multilocations_view not in ('Y', 'N'):
            multilocations_view = 'N'
        allowed_tid_csv = _normalize_allowed_tenant_ids_csv(request.form.get('allowed_tenant_ids') or '') if multilocations_view == 'Y' else None
        try:
            update_user_role(username, role_id)
            wh_prefs = warehouse_prefs_from_mapping(request.form)
            update_user_account(
                username=username, password=password or None, active_flag=active_flag, needcounter=needcounter,
                tenant_id=tenant_id, multilocations_view=multilocations_view, transit_only=transit_only,
                customer_creation=customer_creation, allowed_tenant_ids=allowed_tid_csv if multilocations_view == 'Y' else None,
                default_wh_sales=wh_prefs.get('sales'), default_wh_sales_return=wh_prefs.get('sales_return'),
                default_wh_purchase=wh_prefs.get('purchase'), default_wh_purchase_return=wh_prefs.get('purchase_return'),
                update_warehouse_prefs=True,
            )
        except ValueError as exc:
            flash(str(exc), 'error')
            user_row = get_user_by_username(username)
            return render_template('users/user_role_edit.html', user_row=user_row, roles=roles, available_tenants=available_tenants, warehouses_api_url=url_for('users.api_user_warehouses'))
        flash('User updated.', 'success')
        return redirect(url_for('users.user_list'))
    user_row = get_user_by_username(username)
    if user_row and user_row.get('role_id'):
        canon = resolve_role_id_canonical(user_row['role_id'])
        if canon:
            user_row['role_id'] = canon
    if user_row:
        for field in ('default_wh_sales', 'default_wh_sales_return', 'default_wh_purchase', 'default_wh_purchase_return'):
            wid_val = user_row.get(field)
            user_row[f'{field}_display'] = warehouse_display_label(wid_val) if wid_val not in (None, '') else ''
    return render_template('users/user_role_edit.html', user_row=user_row, roles=roles, available_tenants=available_tenants, warehouses_api_url=url_for('users.api_user_warehouses'))

@bp.route('/users/api/employees', methods=['GET'])
def api_employees_for_picker():
    """Employee master rows for Users create form picker (current branch)."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    from addons.employee.controllers import routes as employee_routes

    search = (request.args.get('q') or request.args.get('search') or '').strip().lower()
    location_code = employee_routes._resolve_session_location_code()
    try:
        limit = max(20, min(int(request.args.get('limit') or 500), 2000))
    except (TypeError, ValueError):
        limit = 500
    rows = employee_routes._get_employee_list(location_code, None, page=1, items_per_page=limit) or []
    items = []
    for row in rows:
        code = row.get('employeecode')
        if code is None:
            continue
        name = str(row.get('employeename') or '').strip()
        designation = str(row.get('designation') or '').strip()
        code_str = str(code).strip()
        if search and search not in code_str.lower() and search not in name.lower() and search not in designation.lower():
            continue
        items.append({
            'employeecode': code_str,
            'employeename': name,
            'designation': designation,
        })
    return jsonify({'success': True, 'items': items, 'count': len(items)})


@bp.route('/users/api/warehouses', methods=['GET'])
def api_user_warehouses():
    """Warehouse picker rows for user create/edit (scoped to selected tenant)."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    tenant_id = (request.args.get('tenant_id') or '').strip()
    search = (request.args.get('q') or request.args.get('search') or '').strip()
    try:
        limit = max(20, min(int(request.args.get('limit') or 500), 2000))
    except (TypeError, ValueError):
        limit = 500
    try:
        rows = list_warehouse_picker_rows_for_tenant(tenant_id or None, search=search, limit=limit)
        return jsonify({'success': True, 'warehouses': rows, 'count': len(rows)})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc), 'warehouses': []}), 500


@bp.route('/users/check-username', methods=['GET'])
def check_username():
    if not session.get('user'):
        return ({'exists': False, 'error': 'Unauthorized'}, 401)
    username = (request.args.get('username') or '').strip()
    if not username:
        return {'exists': False}
    return {'exists': user_exists(username)}
