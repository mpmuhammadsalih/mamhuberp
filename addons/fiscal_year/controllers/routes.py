"""Setup — Fiscal year master (FISCAL_YEAR)."""
from pathlib import Path
from nexa_http import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from addons.fiscal_year.fiscal_year_db import (
    delete_fiscal_year,
    ensure_fiscal_year_table,
    get_fiscal_year_row,
    list_fiscal_years,
    save_fiscal_year,
    set_fiscal_year_current,
)
from db import list_location_master_rows

_ADDON = Path(__file__).resolve().parents[1]
bp = Blueprint('fiscal_year', __name__, url_prefix='/setup', template_folder=str(_ADDON / 'views' / 'templates'))


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
        return 'setup.fiscal_year' in perms
    except Exception:
        return False


def _location_options() -> list:
    rows = list_location_master_rows() or []
    out = [{'code': '', 'label': 'All branches (company-wide)'}]
    for r in rows:
        lc = r.get('locationcode')
        nm = str(r.get('locationname') or '').strip()
        if lc is not None and str(lc).strip() != '':
            out.append({'code': str(lc), 'label': f'{lc} — {nm}' if nm else str(lc)})
    return out


def _form_from_request() -> dict:
    return {
        'year_code': (request.form.get('year_code') or '').strip(),
        'year_name': (request.form.get('year_name') or '').strip(),
        'date_from': (request.form.get('date_from') or '').strip(),
        'date_to': (request.form.get('date_to') or '').strip(),
        'is_current': 'Y' if request.form.get('is_current') else 'N',
        'is_closed': 'Y' if request.form.get('is_closed') else 'N',
        'locationcode': (request.form.get('locationcode') or '').strip(),
    }


@bp.route('/fiscal-year', methods=('GET',))
def fiscal_year_list():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _allowed():
        abort(403)
    ensure_fiscal_year_table()
    include_closed = request.args.get('closed') in ('1', 'true', 'yes', 'y')
    rows = list_fiscal_years(include_closed=include_closed)
    return render_template(
        'fiscal_year/fiscal_year_list.html',
        rows=rows,
        include_closed=include_closed,
        locations=_location_options(),
    )


@bp.route('/fiscal-year/new', methods=('GET', 'POST'))
def fiscal_year_new():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _allowed():
        abort(403)
    ensure_fiscal_year_table()
    row: dict = {}
    if request.method == 'POST':
        data = _form_from_request()
        ok, err, _fid = save_fiscal_year(data, str(session.get('user') or 'web'))
        if ok:
            flash('Fiscal year created.', 'success')
            return redirect(url_for('fiscal_year.fiscal_year_list'))
        flash(err or 'Save failed.', 'error')
        row = data
    else:
        y = __import__('datetime').date.today().year
        row = {
            'date_from': f'{y}-01-01',
            'date_to': f'{y}-12-31',
            'year_code': str(y),
            'is_current': 'N',
            'is_closed': 'N',
        }
    return render_template(
        'fiscal_year/fiscal_year_form.html',
        row=row,
        locations=_location_options(),
        is_new=True,
    )


@bp.route('/fiscal-year/edit/<int:fiscal_year_id>', methods=('GET', 'POST'))
def fiscal_year_edit(fiscal_year_id: int):
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _allowed():
        abort(403)
    ensure_fiscal_year_table()
    if request.method == 'POST':
        data = _form_from_request()
        ok, err, _fid = save_fiscal_year(
            data,
            str(session.get('user') or 'web'),
            fiscal_year_id=fiscal_year_id,
        )
        if ok:
            flash('Fiscal year saved.', 'success')
            return redirect(url_for('fiscal_year.fiscal_year_list'))
        flash(err or 'Save failed.', 'error')
        row = {**(get_fiscal_year_row(fiscal_year_id) or {}), **data}
    else:
        row = get_fiscal_year_row(fiscal_year_id)
        if not row:
            flash('Fiscal year not found.', 'error')
            return redirect(url_for('fiscal_year.fiscal_year_list'))
    return render_template(
        'fiscal_year/fiscal_year_form.html',
        row=row,
        locations=_location_options(),
        is_new=False,
        fiscal_year_id=fiscal_year_id,
    )


@bp.route('/fiscal-year/set-current', methods=('POST',))
def fiscal_year_set_current():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _allowed():
        abort(403)
    try:
        fid = int(request.form.get('fiscal_year_id') or 0)
    except (TypeError, ValueError):
        fid = 0
    ok, err = set_fiscal_year_current(fid, str(session.get('user') or 'web'))
    if ok:
        flash('Current fiscal year updated.', 'success')
    else:
        flash(err or 'Could not set current year.', 'error')
    return redirect(url_for('fiscal_year.fiscal_year_list'))


@bp.route('/fiscal-year/delete', methods=('POST',))
def fiscal_year_delete():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _allowed():
        abort(403)
    try:
        fid = int(request.form.get('fiscal_year_id') or 0)
    except (TypeError, ValueError):
        fid = 0
    ok, err = delete_fiscal_year(fid)
    if ok:
        flash('Fiscal year deleted.', 'success')
    else:
        flash(err or 'Delete failed.', 'error')
    return redirect(url_for('fiscal_year.fiscal_year_list'))
