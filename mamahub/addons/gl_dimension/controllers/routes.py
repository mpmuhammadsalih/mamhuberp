"""Setup — GL dimension value master (GL_DIMENSION_VALUE)."""
from pathlib import Path
from nexa_http import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from db import GL_DIMENSION_TYPES, delete_gl_dimension_value, ensure_gl_dimension_value_table, get_gl_dimension_value_row, list_gl_dimension_values, normalize_gl_dimension_type, upsert_gl_dimension_value
_ADDON = Path(__file__).resolve().parents[1]
bp = Blueprint('gl_dimension', __name__, url_prefix='/setup', template_folder=str(_ADDON / 'views' / 'templates'))

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
        return 'setup.gl_dimension_master' in perms
    except Exception:
        return False

def _dim_type_label(code: str) -> str:
    return {'COST_CENTER': 'Cost center', 'DEPARTMENT': 'Department', 'PROJECT': 'Project'}.get((code or '').upper(), code or '')

@bp.route('/gl-dimensions', methods=('GET',))
def gl_dimension_list():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _allowed():
        abort(403)
    ensure_gl_dimension_value_table()
    filter_type = (request.args.get('dim_type') or '').strip().upper() or None
    include_inactive = request.args.get('inactive') in ('1', 'true', 'yes', 'y')
    try:
        if filter_type:
            normalize_gl_dimension_type(filter_type)
    except ValueError:
        flash('Invalid dimension type filter.', 'error')
        filter_type = None
    rows = list_gl_dimension_values(dim_type=filter_type, include_inactive=include_inactive)
    return render_template('gl_dimension/dimension_list.html', rows=rows, filter_type=filter_type or '', include_inactive=include_inactive, dim_types=GL_DIMENSION_TYPES, dim_type_label=_dim_type_label)

@bp.route('/gl-dimensions/new', methods=('GET', 'POST'))
def gl_dimension_new():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _allowed():
        abort(403)
    ensure_gl_dimension_value_table()
    row: dict = {}
    if request.method == 'POST':
        dt = (request.form.get('dim_type') or '').strip()
        dc = (request.form.get('dim_code') or '').strip()
        nm = (request.form.get('dim_name') or '').strip()
        act = 'Y' if request.form.get('active') else 'N'
        try:
            so = int(request.form.get('sort_order') or '0')
        except ValueError:
            so = 0
        ok, err = upsert_gl_dimension_value(dt, dc, dim_name=nm or None, active=act, sort_order=so)
        if ok:
            flash('Dimension value saved.', 'success')
            return redirect(url_for('gl_dimension.gl_dimension_list', dim_type=normalize_gl_dimension_type(dt)))
        flash(err or 'Save failed.', 'error')
        row = {'dim_type': dt, 'dim_code': dc, 'dim_name': nm, 'active': act, 'sort_order': so}
    return render_template('gl_dimension/dimension_new.html', row=row, dim_types=GL_DIMENSION_TYPES, dim_type_label=_dim_type_label)

@bp.route('/gl-dimensions/edit', methods=('GET', 'POST'))
def gl_dimension_edit():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _allowed():
        abort(403)
    ensure_gl_dimension_value_table()
    if request.method == 'GET':
        dt = (request.args.get('dim_type') or '').strip()
        dc = (request.args.get('dim_code') or '').strip()
    else:
        dt = (request.form.get('dim_type') or '').strip()
        dc = (request.form.get('dim_code') or '').strip()
    try:
        n_dt = normalize_gl_dimension_type(dt)
    except ValueError:
        flash('Invalid dimension type.', 'error')
        return redirect(url_for('gl_dimension.gl_dimension_list'))
    row = get_gl_dimension_value_row(n_dt, dc)
    if not row and request.method == 'GET':
        flash('Dimension value not found.', 'error')
        return redirect(url_for('gl_dimension.gl_dimension_list'))
    if request.method == 'POST':
        nm = (request.form.get('dim_name') or '').strip()
        act = 'Y' if request.form.get('active') else 'N'
        try:
            so = int(request.form.get('sort_order') or '0')
        except ValueError:
            so = 0
        ok, err = upsert_gl_dimension_value(n_dt, dc, dim_name=nm or None, active=act, sort_order=so)
        if ok:
            flash('Dimension value updated.', 'success')
            return redirect(url_for('gl_dimension.gl_dimension_list', dim_type=n_dt))
        flash(err or 'Save failed.', 'error')
    if not row:
        row = {'dim_type': n_dt, 'dim_code': dc, 'dim_name': '', 'active': 'Y', 'sort_order': 0}
    return render_template('gl_dimension/dimension_edit.html', row=row, dim_types=GL_DIMENSION_TYPES, dim_type_label=_dim_type_label)

@bp.route('/gl-dimensions/delete', methods=('POST',))
def gl_dimension_delete():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _allowed():
        abort(403)
    dt = (request.form.get('dim_type') or '').strip()
    dc = (request.form.get('dim_code') or '').strip()
    ok, err = delete_gl_dimension_value(dt, dc)
    if ok:
        flash('Dimension value deleted.', 'success')
    else:
        flash(err or 'Delete failed.', 'error')
    try:
        redir_type = normalize_gl_dimension_type(dt)
    except ValueError:
        redir_type = None
    return redirect(url_for('gl_dimension.gl_dimension_list', dim_type=redir_type or None))
