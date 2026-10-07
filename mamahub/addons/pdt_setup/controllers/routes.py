"""PDT roles setup and PDT user creation (dedicated pdt_* auth tables)."""
from pathlib import Path

from nexa_http import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for

from db import get_tenant_list, user_exists
from db.pdt_auth import (
    PDT_ROLE_ID_PREFIX,
    create_pdt_role,
    create_pdt_user,
    delete_pdt_role,
    ensure_default_pdt_operator_role,
    get_all_pdt_roles,
    get_next_pdt_role_id,
    get_pdt_role_by_id,
    get_pdt_role_permissions,
    get_pdt_role_quick_access,
    get_pdt_users_with_roles,
    pdt_role_exists,
    pdt_user_exists,
    update_pdt_role,
)
from permissions import (
    get_pdt_menu_groups,
    is_pdt_role_id,
    validate_pdt_menu_permissions,
)

_ADDON_ROOT = Path(__file__).resolve().parents[1]
bp = Blueprint('pdt', __name__, template_folder=str(_ADDON_ROOT / 'views' / 'templates'))


def _require_login():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    return None


def _guard_pdt_role(role_id: str):
    if not pdt_role_exists(role_id):
        flash('PDT role not found.', 'error')
        return redirect(url_for('pdt.pdt_roles_list'))
    return None


@bp.route('/pdt/roles')
def pdt_roles_list():
    redir = _require_login()
    if redir:
        return redir
    ensure_default_pdt_operator_role()
    return render_template('pdt/pdt_roles_list.html', roles=get_all_pdt_roles())


@bp.route('/pdt/roles/create', methods=['GET', 'POST'])
def pdt_roles_create():
    redir = _require_login()
    if redir:
        return redir
    ensure_default_pdt_operator_role()
    menu_groups = get_pdt_menu_groups()
    next_role_id = get_next_pdt_role_id()
    if request.method == 'POST':
        role_id = (request.form.get('role_id') or '').strip().upper() or next_role_id
        if not is_pdt_role_id(role_id):
            flash(f'PDT role ID must start with {PDT_ROLE_ID_PREFIX}.', 'error')
        else:
            role_name = (request.form.get('role_name') or '').strip()
            description = (request.form.get('description') or '').strip()
            try:
                menu_permissions = validate_pdt_menu_permissions(request.form.getlist('menu_permissions'))
                quick_access_paths = [
                    p for p in request.form.getlist('quick_access_permissions')
                    if p in menu_permissions
                ]
                create_pdt_role(role_id, role_name, description, menu_permissions, quick_access_paths)
                flash('PDT role created.', 'success')
                return redirect(url_for('pdt.pdt_roles_list'))
            except ValueError as exc:
                flash(str(exc), 'error')
    return render_template(
        'pdt/pdt_roles_form.html',
        role=None,
        menu_groups=menu_groups,
        selected_permissions=[],
        selected_quick_access=[],
        next_role_id=next_role_id,
    )


@bp.route('/pdt/roles/<role_id>/edit', methods=['GET', 'POST'])
def pdt_roles_edit(role_id: str):
    redir = _require_login()
    if redir:
        return redir
    guard = _guard_pdt_role(role_id)
    if guard:
        return guard
    role = get_pdt_role_by_id(role_id)
    if not role:
        flash('Role not found.', 'error')
        return redirect(url_for('pdt.pdt_roles_list'))
    menu_groups = get_pdt_menu_groups()
    selected_permissions = get_pdt_role_permissions(role_id)
    selected_quick_access = get_pdt_role_quick_access(role_id)
    if request.method == 'POST':
        role_name = (request.form.get('role_name') or '').strip()
        description = (request.form.get('description') or '').strip()
        try:
            menu_permissions = validate_pdt_menu_permissions(request.form.getlist('menu_permissions'))
            quick_access_paths = [
                p for p in request.form.getlist('quick_access_permissions')
                if p in menu_permissions
            ]
            update_pdt_role(
                role_id=role_id,
                role_name=role_name,
                description=description,
                menu_permissions=menu_permissions,
                quick_access_paths=quick_access_paths,
            )
            flash('PDT role updated.', 'success')
            return redirect(url_for('pdt.pdt_roles_list'))
        except ValueError as exc:
            flash(str(exc), 'error')
    return render_template(
        'pdt/pdt_roles_form.html',
        role=role,
        menu_groups=menu_groups,
        selected_permissions=selected_permissions,
        selected_quick_access=selected_quick_access,
        next_role_id=None,
    )


@bp.route('/pdt/roles/<role_id>/delete', methods=['POST'])
def pdt_roles_delete(role_id: str):
    redir = _require_login()
    if redir:
        return redir
    guard = _guard_pdt_role(role_id)
    if guard:
        return guard
    try:
        delete_pdt_role(role_id)
        flash('PDT role deleted.', 'success')
    except ValueError as exc:
        flash(str(exc), 'error')
    return redirect(url_for('pdt.pdt_roles_list'))


@bp.route('/pdt/users')
def pdt_users_list():
    redir = _require_login()
    if redir:
        return redir
    ensure_default_pdt_operator_role()
    return render_template(
        'pdt/pdt_users_list.html',
        users=get_pdt_users_with_roles(),
        pdt_roles=get_all_pdt_roles(),
    )


@bp.route('/pdt/users/create', methods=['GET', 'POST'])
def pdt_user_create():
    redir = _require_login()
    if redir:
        return redir
    ensure_default_pdt_operator_role()
    pdt_roles = get_all_pdt_roles()
    available_tenants = get_tenant_list() or []
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        employeecode = (request.form.get('employeecode') or '').strip()
        role_id = (request.form.get('role_id') or '').strip()
        tenant_id = (request.form.get('tenant_id') or '').strip() or None
        if not pdt_roles:
            flash('Create a PDT role first.', 'error')
        elif not role_id or not pdt_role_exists(role_id):
            flash('Select a valid PDT role.', 'error')
        elif not employeecode:
            flash('Employee Code is required.', 'error')
        elif not employeecode.isdigit():
            flash('Employee Code must be numeric.', 'error')
        else:
            try:
                create_pdt_user(username, password, employeecode, role_id, tenant_id=tenant_id)
                flash('PDT user created.', 'success')
                return redirect(url_for('pdt.pdt_users_list'))
            except ValueError as exc:
                flash(str(exc), 'error')
    return render_template(
        'pdt/pdt_user_create.html',
        pdt_roles=pdt_roles,
        available_tenants=available_tenants,
    )


@bp.route('/pdt/users/check-username', methods=['GET'])
def check_username():
    if not session.get('user'):
        return jsonify({'exists': False, 'error': 'Unauthorized'}), 401
    username = (request.args.get('username') or '').strip()
    if not username:
        return jsonify({'exists': False})
    return jsonify({'exists': pdt_user_exists(username) or user_exists(username)})
