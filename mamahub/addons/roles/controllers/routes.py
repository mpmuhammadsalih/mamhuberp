"""Roles and permissions management blueprint"""
from pathlib import Path
from nexa_http import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from db import create_role, delete_role, ensure_ho_roles, get_all_roles, get_role_by_id, get_role_permissions, get_role_quick_access, get_next_role_id, update_role, resolve_role_id_canonical
from permissions import get_menu_groups, get_mobile_menu_groups, get_role_editor_menu_paths
_ADDON_ROOT = Path(__file__).resolve().parents[1]
bp = Blueprint('roles', __name__, template_folder=str(_ADDON_ROOT / 'views' / 'templates'))

def _sync_ho_roles_if_needed() -> None:
    """Idempotent HO + Master Request seed roles; also covers missed/failed app bootstrap."""
    try:
        ensure_ho_roles()
    except Exception as e:
        try:
            current_app.logger.warning('ensure_ho_roles (roles addon): %s', e)
        except Exception:
            pass

@bp.route('/roles')
def roles_list():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    _sync_ho_roles_if_needed()
    roles = get_all_roles()
    return render_template('roles/roles_list.html', roles=roles)

@bp.route('/roles/create', methods=['GET', 'POST'])
def roles_create():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    _sync_ho_roles_if_needed()
    menu_groups = get_menu_groups()
    mobile_menu_groups = get_mobile_menu_groups()
    next_role_id = get_next_role_id()
    if request.method == 'POST':
        role_id = (request.form.get('role_id') or '').strip() or next_role_id
        role_name = (request.form.get('role_name') or '').strip()
        description = (request.form.get('description') or '').strip()
        menu_permissions = request.form.getlist('menu_permissions')
        quick_access_paths = request.form.getlist('quick_access_permissions')
        quick_access_paths = [p for p in quick_access_paths if p in menu_permissions]
        try:
            create_role(role_id, role_name, description, menu_permissions, quick_access_paths)
            flash('Role created.', 'success')
            return redirect(url_for('roles.roles_list'))
        except ValueError as exc:
            flash(str(exc), 'error')
    return render_template(
        'roles/roles_form.html',
        role=None,
        menu_groups=menu_groups,
        mobile_menu_groups=mobile_menu_groups,
        selected_permissions=[],
        selected_quick_access=[],
        orphan_permissions=[],
        next_role_id=next_role_id,
    )

@bp.route('/roles/<role_id>/edit', methods=['GET', 'POST'])
def roles_edit(role_id: str):
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    _sync_ho_roles_if_needed()
    role = get_role_by_id(role_id)
    if not role:
        flash('Role not found.', 'error')
        return redirect(url_for('roles.roles_list'))
    menu_groups = get_menu_groups()
    mobile_menu_groups = get_mobile_menu_groups()
    canon_role_id = role['role_id']
    selected_permissions = get_role_permissions(canon_role_id)
    selected_quick_access = get_role_quick_access(canon_role_id)
    editor_paths = get_role_editor_menu_paths()
    orphan_permissions = sorted(p for p in selected_permissions if p not in editor_paths)
    if request.method == 'POST':
        role_name = (request.form.get('role_name') or '').strip()
        description = (request.form.get('description') or '').strip()
        menu_permissions = request.form.getlist('menu_permissions')
        quick_access_paths = request.form.getlist('quick_access_permissions')
        quick_access_paths = [p for p in quick_access_paths if p in menu_permissions]
        try:
            update_role(role_id=canon_role_id, role_name=role_name, description=description, menu_permissions=menu_permissions, quick_access_paths=quick_access_paths)
            flash('Role updated.', 'success')
            return redirect(url_for('roles.roles_list'))
        except ValueError as exc:
            flash(str(exc), 'error')
    return render_template(
        'roles/roles_form.html',
        role=role,
        menu_groups=menu_groups,
        mobile_menu_groups=mobile_menu_groups,
        selected_permissions=selected_permissions,
        selected_quick_access=selected_quick_access,
        orphan_permissions=orphan_permissions,
    )

@bp.route('/roles/<role_id>/delete', methods=['POST'])
def roles_delete(role_id: str):
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    canon_role_id = resolve_role_id_canonical(role_id) or role_id
    try:
        delete_role(canon_role_id)
        flash('Role deleted.', 'success')
    except ValueError as exc:
        flash(str(exc), 'error')
    return redirect(url_for('roles.roles_list'))
