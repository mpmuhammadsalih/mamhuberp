"""Setup — Document numbering series for all transactions."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from nexa_http import Blueprint, abort, flash, redirect, render_template, request, session, url_for

from addons.document_numbering.document_numbering_db import (
    ensure_doc_number_series_table,
    list_document_series,
    list_module_names,
    save_document_series_bulk,
    seed_default_document_series,
    sync_last_numbers_from_database,
)
from db import list_location_master_rows

_ADDON = Path(__file__).resolve().parents[1]
bp = Blueprint(
    'document_numbering',
    __name__,
    url_prefix='/setup',
    template_folder=str(_ADDON / 'views' / 'templates'),
)


def _allowed() -> bool:
    u = (session.get('user') or '').strip().lower()
    if u in ('admin', 'super'):
        return True
    try:
        from db import get_user_role_id
        from permissions import get_role_permissions

        rid = get_user_role_id(session.get('user'))
        if not rid:
            return False
        perms = get_role_permissions(rid) or []
        return 'setup.document_numbering' in perms
    except Exception:
        return False


def _location_options() -> list:
    rows = list_location_master_rows() or []
    out = [{'code': '', 'label': 'All branches'}]
    for r in rows:
        lc = r.get('locationcode')
        nm = str(r.get('locationname') or '').strip()
        if lc is not None and str(lc).strip() != '':
            out.append({'code': str(lc), 'label': f'{lc} — {nm}' if nm else str(lc)})
    return out


def _parse_filter_location() -> Optional[int]:
    raw = (request.args.get('location') or request.form.get('filter_location') or '').strip()
    if not raw:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _rows_from_form() -> list:
    series_ids = request.form.getlist('series_id')
    rows = []
    for sid in series_ids:
        try:
            series_id = int(sid)
        except (TypeError, ValueError):
            continue
        prefix = (request.form.get(f'prefix_{series_id}') or '').strip()
        rows.append({
            'series_id': series_id,
            'prefix': prefix,
            'suffix': (request.form.get(f'suffix_{series_id}') or '').strip(),
            'starting_no': request.form.get(f'starting_no_{series_id}') or 1,
            'last_no_used': request.form.get(f'last_no_used_{series_id}') or 0,
            'increment_by': request.form.get(f'increment_by_{series_id}') or 1,
            'padding': request.form.get(f'padding_{series_id}') or 0,
            'allow_manual': 'Y' if request.form.get(f'allow_manual_{series_id}') else 'N',
            'use_date_prefix': 'Y' if request.form.get(f'use_date_prefix_{series_id}') else 'N',
            'date_format': (request.form.get(f'date_format_{series_id}') or 'YYYYMMDD').strip(),
            'is_active': 'Y' if request.form.get(f'is_active_{series_id}') else 'N',
            'notes': (request.form.get(f'notes_{series_id}') or '').strip(),
        })
    return rows


@bp.route('/document-numbering', methods=['GET', 'POST'])
def document_numbering_page():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _allowed():
        abort(403)

    ensure_doc_number_series_table()
    seeded = seed_default_document_series(str(session.get('user') or 'web'))
    if seeded:
        flash(f'Initialized {seeded} default document series.', 'info')

    module_filter = (request.args.get('module') or request.form.get('filter_module') or '').strip()
    location_filter = _parse_filter_location()
    user = str(session.get('user') or 'web')

    if request.method == 'POST':
        action = (request.form.get('action') or 'save').strip().lower()
        if action == 'sync':
            ok, err, count = sync_last_numbers_from_database(
                location_code=location_filter,
                user=user,
            )
            if ok:
                flash(f'Synced last numbers from database for {count} series.', 'success')
            else:
                flash(err or 'Sync failed.', 'error')
        else:
            ok, err, count = save_document_series_bulk(_rows_from_form(), user)
            if ok:
                flash(f'Saved {count} document series.', 'success')
            else:
                flash(err or 'Save failed.', 'error')
        q = []
        if module_filter:
            q.append(f'module={module_filter}')
        if location_filter is not None:
            q.append(f'location={location_filter}')
        suffix = f'?{"&".join(q)}' if q else ''
        return redirect(url_for('document_numbering.document_numbering_page') + suffix)

    rows = list_document_series(
        module_name=module_filter or None,
        location_code=location_filter,
    )
    modules = list_module_names()
    active_count = sum(1 for r in rows if (r.get('is_active') or 'Y').upper() == 'Y')

    return render_template(
        'document_numbering/document_numbering.html',
        rows=rows,
        modules=modules,
        module_filter=module_filter,
        location_filter=location_filter if location_filter is not None else '',
        locations=_location_options(),
        active_count=active_count,
    )
