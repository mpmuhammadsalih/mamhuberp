"""Branch / Location master — LOCATIONMASTER (tenant DB)."""
from pathlib import Path
from typing import List, Tuple
import os
import secrets
from datetime import datetime
from nexa_http import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from werkzeug.utils import secure_filename
from addons.branch_location.schema import LOCATIONMASTER_DEFAULT_NAME, LOCATIONMASTER_LOGO_COLUMN, LOCATIONMASTER_UI_HIDDEN_COLUMNS
from db import LOCATIONS_TABLE, _location_master_editable_columns, ensure_location_master_branch_tracking_columns, ensure_location_master_table, get_location_master_row, insert_location_master_row, list_location_master_rows, suggest_next_location_code, update_location_master_row
_ADDON = Path(__file__).resolve().parents[1]
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
bp = Blueprint('branch_location', __name__, url_prefix='/setup', template_folder=str(_ADDON / 'views' / 'templates'))
_ALLOWED_LOGO_EXT = {'.png', '.jpg', '.jpeg', '.webp'}

def _save_branch_logo(upload, location_code: object) -> str:
    """Save uploaded logo under ``static/uploads/branch_logos/``; return relative path for ``LOGO_PATH``."""
    if not upload or not getattr(upload, 'filename', ''):
        return ''
    original = str(upload.filename or '').strip()
    ext = os.path.splitext(original)[1].lower()
    if ext not in _ALLOWED_LOGO_EXT:
        raise ValueError('Logo must be PNG, JPG, JPEG, or WEBP.')
    safe_lc = secure_filename(str(location_code or 'branch').strip()) or 'branch'
    stamp = datetime.now().strftime('%Y%m%d%H%M%S')
    filename = f'{safe_lc}_{stamp}{ext}'
    target_dir = _PROJECT_ROOT / 'static' / 'uploads' / 'branch_logos'
    target_dir.mkdir(parents=True, exist_ok=True)
    full_path = str((target_dir / filename).resolve())
    upload.save(full_path)
    return f'uploads/branch_logos/{filename}'

def _branch_logo_rel_from_row(row: dict | None) -> str:
    if not row:
        return ''
    return str(row.get('logo_path') or row.get('LOGO_PATH') or '').strip()

def _apply_branch_logo_upload(location_code: object, updates: dict) -> None:
    logo_file = request.files.get('logo')
    if not logo_file or not str(logo_file.filename or '').strip():
        return
    try:
        rel = _save_branch_logo(logo_file, location_code)
        if rel:
            updates[LOCATIONMASTER_LOGO_COLUMN] = rel
    except ValueError as e:
        flash(str(e), 'error')
    except Exception:
        flash('Failed to upload branch logo.', 'error')

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
        return 'setup.branch_location_master' in perms
    except Exception:
        return False

def _effective_table_name() -> str:
    """Physical table name from env ``LOCATIONS_TABLE`` (default LOCATIONMASTER)."""
    return (LOCATIONS_TABLE or LOCATIONMASTER_DEFAULT_NAME).strip().upper()
_SWITCH_ORDER_BRANCH = ('WAREHOUSE_ENABLE', 'BIN_TRACKING', 'BATCH_TRACKING', 'BASELOCATIONFLAG')
_SWITCH_COLSET = frozenset(_SWITCH_ORDER_BRANCH)
_AFTER_LOCATION_NAME_ORDER = ('ADDRESS', 'EMAILID', 'TELEPHONE', 'DBCODE', 'RESETNO')
_BRANCH_LIST_LEAD_COLS = ('locationcode', 'locationname', 'address', 'emailid', 'telephone', 'dbcode', 'resetno', 'manager')
_BRANCH_UI_HIDDEN_LOWER = frozenset((c.lower() for c in LOCATIONMASTER_UI_HIDDEN_COLUMNS)) | frozenset({'logo_path'})


def _branch_form_editable_columns() -> List[str]:
    """Editable LOCATIONMASTER columns shown on branch new/edit and included on save."""
    return [
        c for c in _location_master_editable_columns()
        if (c or '').strip().upper() not in LOCATIONMASTER_UI_HIDDEN_COLUMNS
        and (c or '').strip().upper() != LOCATIONMASTER_LOGO_COLUMN
    ]

def _branch_list_switch_keys() -> frozenset[str]:
    return frozenset((c.lower() for c in _SWITCH_ORDER_BRANCH))

def _branch_list_display_columns(keys_lower: set[str]) -> List[str]:
    """Primary keys/info first, then switch columns (form order), then remaining alphabetically."""
    out: List[str] = []
    for c in _BRANCH_LIST_LEAD_COLS:
        if c in keys_lower and c not in out:
            out.append(c)
    for c in (x.lower() for x in _SWITCH_ORDER_BRANCH):
        if c in keys_lower and c not in out:
            out.append(c)
    for c in sorted(keys_lower):
        if c not in out and c not in _BRANCH_UI_HIDDEN_LOWER:
            out.append(c)
    return [c for c in out if c not in _BRANCH_UI_HIDDEN_LOWER]

def _branch_location_form_layout(editable_columns: List[str]) -> Tuple[bool, List[str], List[str], List[str]]:
    """LOCATIONNAME beside code; **ADDRESS**, **EMAILID**, **TELEPHONE**, **DBCODE**, **RESETNO** next (when present); then **Y/N toggles**; remainder sorted alphabetically."""
    colset = {(c or '').strip().upper() for c in editable_columns or []}
    switch_cols = [x for x in _SWITCH_ORDER_BRANCH if x in colset]
    after_name = [x for x in _AFTER_LOCATION_NAME_ORDER if x in colset]
    skip = _SWITCH_COLSET | {'LOCATIONNAME'} | set(after_name)
    others = sorted((c for c in colset if c not in skip))
    return ('LOCATIONNAME' in colset, switch_cols, after_name, others)

def _branch_switch_value_from_form(col_upper: str, form) -> str | None:
    """Map LOCATIONMASTER switches from ``request.form`` (``Y``/``N`` or ``1``/``0`` for numeric flags). Returns ``None`` if ``col_upper`` is not a switch."""
    cu = (col_upper or '').strip().upper()
    if cu == 'BATCH_TRACKING':
        return 'Y' if form.get('batch_tracking') else 'N'
    if cu == 'BIN_TRACKING':
        return 'Y' if form.get('bin_tracking') else 'N'
    if cu == 'WAREHOUSE_ENABLE':
        return 'Y' if form.get('warehouse_enable') else 'N'
    if cu == 'BASELOCATIONFLAG':
        return 'Y' if form.get('baselocationflag') else 'N'
    return None

def _bootstrap_table() -> None:
    """Ensure tenant LOCATIONMASTER/table exists (auto-create DDL if missing)."""
    ok, msg, created = ensure_location_master_table()
    if not ok and msg:
        flash(msg[:900], 'error')
    elif created:
        flash('Created branch/location table "%s" — you can add rows below.' % _effective_table_name(), 'success')
    ensure_location_master_branch_tracking_columns()

def _norm_lc(val) -> object:
    if val is None or str(val).strip() == '':
        return None
    s = str(val).strip()
    try:
        if '.' in s:
            return float(s)
        return int(s)
    except ValueError:
        return s
_BLM_NEW_ONCE = '_blm_new_once'

def _blm_issue_new_once_token() -> str:
    t = secrets.token_urlsafe(24)
    session[_BLM_NEW_ONCE] = t
    session.modified = True
    return t

def _blm_verify_and_consume_new_once(submitted: str | None) -> bool:
    sub = (submitted or '').strip()
    stored = session.get(_BLM_NEW_ONCE)
    if not stored or not sub or sub != stored:
        return False
    session.pop(_BLM_NEW_ONCE, None)
    session.modified = True
    return True

def _blm_edit_once_session_key(lc: object) -> str:
    return '_blm_edit_once_%s' % str(lc)

def _blm_issue_edit_once_token(lc: object) -> str:
    k = _blm_edit_once_session_key(lc)
    t = secrets.token_urlsafe(24)
    session[k] = t
    session.modified = True
    return t

def _blm_verify_and_consume_edit_once(lc: object, submitted: str | None) -> bool:
    sub = (submitted or '').strip()
    k = _blm_edit_once_session_key(lc)
    stored = session.get(k)
    if not stored or not sub or sub != stored:
        return False
    session.pop(k, None)
    session.modified = True
    return True

@bp.route('/branch-location', methods=('GET',))
def branch_location_master():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _allowed():
        abort(403)
    _bootstrap_table()
    rows = list_location_master_rows()
    if rows:
        allk = {str(kk).lower() for r in rows for kk in r.keys()}
        display_cols = _branch_list_display_columns(allk)
    else:
        try:
            exist_lower = {c.lower() for c in _location_master_editable_columns() or []}
            exist_lower.add('locationcode')
        except Exception:
            exist_lower = {'locationcode', 'locationname'}
        display_cols = _branch_list_display_columns(exist_lower)
    branch_show_logo_col = LOCATIONMASTER_LOGO_COLUMN in {c.upper() for c in (_location_master_editable_columns() or [])}
    return render_template('branch_location/branch_location_list.html', rows=rows, display_cols=display_cols, branch_list_switch_set=_branch_list_switch_keys(), loc_table=_effective_table_name(), branch_show_logo_col=branch_show_logo_col)

@bp.route('/branch-location/new', methods=('GET', 'POST'))
def branch_location_new():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _allowed():
        abort(403)
    _bootstrap_table()
    editable = _branch_form_editable_columns()
    suggested = suggest_next_location_code()
    row: dict = {}
    if request.method == 'POST':
        if not _blm_verify_and_consume_new_once(request.form.get('blm_once')):
            flash('That save was skipped (duplicate submit or session lock). Use Add location again, or submit this form only once.', 'warning')
            row = {'locationcode': request.form.get('locationcode') or ''}
            lc = {k.lower(): v for k, v in request.form.items()}
            for col in editable:
                sv = _branch_switch_value_from_form(col, request.form)
                if sv is not None:
                    row[col.lower()] = sv
                else:
                    row[col.lower()] = (lc.get(col.lower()) or '').strip()
        else:
            data = {'LOCATIONCODE': request.form.get('locationcode')}
            for col in editable:
                sv = _branch_switch_value_from_form(col, request.form)
                if sv is not None:
                    data[col] = sv
                else:
                    data[col] = request.form.get(col.lower())
            lc_new = data.get('LOCATIONCODE')
            logo_updates = {}
            _apply_branch_logo_upload(lc_new, logo_updates)
            if logo_updates:
                data.update(logo_updates)
            ok, err = insert_location_master_row(data)
            if ok:
                flash('Location created.', 'success')
                return redirect(url_for('branch_location.branch_location_master'))
            flash(err or 'Create failed.', 'error')
            row = {'locationcode': request.form.get('locationcode') or ''}
            lc = {k.lower(): v for k, v in request.form.items()}
            for col in editable:
                sv = _branch_switch_value_from_form(col, request.form)
                if sv is not None:
                    row[col.lower()] = sv
                else:
                    row[col.lower()] = (lc.get(col.lower()) or '').strip()
        blm_form_once = _blm_issue_new_once_token()
    elif suggested is not None:
        row['locationcode'] = suggested
        blm_form_once = _blm_issue_new_once_token()
    else:
        blm_form_once = _blm_issue_new_once_token()
    has_locname, switch_cols, after_name_cols, other_cols = _branch_location_form_layout(editable)
    return render_template('branch_location/branch_location_new.html', row=row, editable_columns=editable, suggested_code=suggested, has_branch_locationname=has_locname, branch_switch_cols=switch_cols, branch_after_name_cols=after_name_cols, branch_other_cols=other_cols, blm_form_once=blm_form_once, branch_logo_path=_branch_logo_rel_from_row(row))

@bp.route('/branch-location/edit/<path:location_code>', methods=('GET', 'POST'))
def branch_location_edit(location_code):
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _allowed():
        abort(403)
    _bootstrap_table()
    lc = _norm_lc(location_code)
    if lc is None:
        flash('Invalid location code.', 'error')
        return redirect(url_for('branch_location.branch_location_master'))
    editable = _branch_form_editable_columns()
    if request.method == 'POST':
        if not _blm_verify_and_consume_edit_once(lc, request.form.get('blm_once')):
            flash('That save was skipped (duplicate submit or session lock). Submit this form only once.', 'warning')
        else:
            updates = {}
            for col in editable:
                sv = _branch_switch_value_from_form(col, request.form)
                if sv is not None:
                    updates[col] = sv
                else:
                    updates[col] = request.form.get(col.lower())
            _apply_branch_logo_upload(lc, updates)
            ok, err = update_location_master_row(lc, updates)
            if ok:
                flash('Location saved.', 'success')
                return redirect(url_for('branch_location.branch_location_master'))
            flash(err or 'Save failed.', 'error')
    row = get_location_master_row(lc)
    if not row:
        flash('Location not found.', 'error')
        return redirect(url_for('branch_location.branch_location_master'))
    blm_form_once = _blm_issue_edit_once_token(lc)
    has_locname, switch_cols, after_name_cols, other_cols = _branch_location_form_layout(editable)
    return render_template('branch_location/branch_location_edit.html', location_code_value=lc, row=row, editable_columns=editable, has_branch_locationname=has_locname, branch_switch_cols=switch_cols, branch_after_name_cols=after_name_cols, branch_other_cols=other_cols, blm_form_once=blm_form_once, branch_logo_path=_branch_logo_rel_from_row(row))
