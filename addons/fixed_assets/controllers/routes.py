"""Fixed assets — categories, register, depreciation."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from nexa_http import Blueprint, abort, flash, jsonify, redirect, render_template, request, send_file, session, url_for

from global_lookup import resolve_lookup_label
from addons.fixed_assets.fa_save_guard import (
    FaSaveBlocked,
    FaSaveReplay,
    fa_form_save_guard,
    fa_post_action_guard,
    reissue_fa_save_nonce,
)
from addons.fixed_assets.fixed_assets_db import (
    RUN_POSTED,
    create_depreciation_run,
    create_fa_transfer,
    delete_fa_category,
    ensure_fixed_assets_tables,
    get_depreciation_run,
    get_fa_asset,
    get_fa_category,
    get_fa_disposal,
    get_fa_sale,
    format_credit_lookup_label,
    list_depreciation_run_lines,
    list_depreciation_runs,
    list_fa_assets,
    list_fa_assets_eligible,
    list_fa_categories,
    list_fa_disposals,
    list_fa_sales,
    list_fa_transfers,
    post_depreciation_run,
    post_fa_acquisition,
    post_fa_disposal,
    post_fa_sale,
    preview_depreciation,
    save_fa_asset,
    save_fa_asset_register_batch,
    save_fa_disposal,
    save_fa_disposal_and_post,
    save_fa_sale,
    save_fa_sale_and_post,
    upsert_fa_category,
)
from db import get_locations_list

_ADDON = Path(__file__).resolve().parents[1]
bp = Blueprint('fixed_assets', __name__, url_prefix='/accounts/fixed-assets', template_folder=str(_ADDON / 'views' / 'templates'))


def _user() -> str:
    return str(session.get('user') or 'web')


def _category_kpis(rows: list) -> dict:
    total = len(rows or [])
    active = sum(1 for r in rows or [] if str(r.get('active') or 'Y').upper() == 'Y')
    inactive = total - active
    lives = [int(r.get('useful_life_months') or 0) for r in rows or [] if int(r.get('useful_life_months') or 0) > 0]
    avg_life = round(sum(lives) / len(lives)) if lives else 0
    return {'total': total, 'active': active, 'inactive': inactive, 'avg_life': avg_life}


def _asset_kpis(rows: list) -> dict:
    total = len(rows or [])
    posted = sum(1 for r in rows or [] if str(r.get('posted_acq') or 'N').upper() == 'Y')
    total_cost = round(sum(float(r.get('acquisition_cost') or 0) for r in rows or []), 2)
    total_nbv = round(sum(float(r.get('nbv') or 0) for r in rows or []), 2)
    return {'total': total, 'posted': posted, 'total_cost': total_cost, 'total_nbv': total_nbv}


def _depreciation_kpis(preview_lines: list, runs: list) -> dict:
    preview_total = round(sum(float(ln.get('dep_amount') or 0) for ln in preview_lines or []), 2)
    posted_runs = sum(1 for r in runs or [] if str(r.get('status') or '').upper() == RUN_POSTED)
    return {'preview_total': preview_total, 'posted_runs': posted_runs}


def _allowed(*menu_paths: str) -> bool:
    u = (session.get('user') or '').strip().lower()
    if u in ('admin', 'super'):
        return True
    try:
        from permissions import is_menu_path_allowed
        from db import get_role_permissions, get_user_role_id

        rid = get_user_role_id(session.get('user'))
        if not rid:
            return True
        perms = get_role_permissions(rid) or []
        return any(is_menu_path_allowed(p, perms) for p in menu_paths)
    except Exception:
        return False


def _require_login():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    ensure_fixed_assets_tables()
    return None


@bp.route('/categories', methods=('GET',))
def fa_category_list():
    redir = _require_login()
    if redir:
        return redir
    if not _allowed('fixed_assets.fa_category_list'):
        abort(403)
    include_inactive = request.args.get('inactive') in ('1', 'true', 'yes')
    rows = list_fa_categories(include_inactive=include_inactive)
    return render_template(
        'fixed_assets/category_list.html',
        rows=rows,
        include_inactive=include_inactive,
        fa_nav_active='categories',
        fa_kpis=_category_kpis(rows),
    )


@bp.route('/categories/form', methods=('GET', 'POST'))
def fa_category_form():
    redir = _require_login()
    if redir:
        return redir
    if not _allowed('fixed_assets.fa_category_list'):
        abort(403)
    category_id = None
    row: dict = {}
    if request.method == 'GET' and request.args.get('id'):
        try:
            category_id = int(request.args.get('id') or 0)
        except ValueError:
            category_id = 0
        existing = get_fa_category(category_id) if category_id else None
        if not existing:
            flash('Category not found.', 'error')
            return redirect(url_for('fixed_assets.fa_category_list'))
        row = existing
    elif request.method == 'POST':
        try:
            category_id = int(request.form.get('category_id') or 0) or None
        except ValueError:
            category_id = None
        ok, err = upsert_fa_category(
            category_id=category_id,
            code=request.form.get('code') or '',
            name=request.form.get('name') or '',
            asset_account=request.form.get('asset_account') or '',
            accum_dep_account=request.form.get('accum_dep_account') or '',
            dep_expense_account=request.form.get('dep_expense_account') or '',
            gain_on_disposal_account=request.form.get('gain_on_disposal_account') or '',
            loss_on_disposal_account=request.form.get('loss_on_disposal_account') or '',
            useful_life_months=int(request.form.get('useful_life_months') or '60'),
            active='Y' if request.form.get('active') else 'N',
            user=_user(),
        )
        if ok:
            flash('Category saved.', 'success')
            return redirect(url_for('fixed_assets.fa_category_list'))
        flash(err or 'Save failed.', 'error')
        row = {
            'category_id': category_id,
            'code': request.form.get('code'),
            'name': request.form.get('name'),
            'asset_account': request.form.get('asset_account'),
            'accum_dep_account': request.form.get('accum_dep_account'),
            'dep_expense_account': request.form.get('dep_expense_account'),
            'gain_on_disposal_account': request.form.get('gain_on_disposal_account'),
            'loss_on_disposal_account': request.form.get('loss_on_disposal_account'),
            'useful_life_months': request.form.get('useful_life_months'),
            'active': 'Y' if request.form.get('active') else 'N',
        }
    account_labels = {
        'asset_account': resolve_lookup_label('gl_account', row.get('asset_account') or ''),
        'accum_dep_account': resolve_lookup_label('gl_account', row.get('accum_dep_account') or ''),
        'dep_expense_account': resolve_lookup_label('gl_account', row.get('dep_expense_account') or ''),
        'gain_on_disposal_account': resolve_lookup_label('gl_account', row.get('gain_on_disposal_account') or ''),
        'loss_on_disposal_account': resolve_lookup_label('gl_account', row.get('loss_on_disposal_account') or ''),
    }
    edit_mode = bool(row.get('category_id'))
    return render_template(
        'fixed_assets/category_form.html',
        row=row,
        account_labels=account_labels,
        edit_mode=edit_mode,
        fa_nav_active='categories',
    )


@bp.route('/categories/delete', methods=('POST',))
def fa_category_delete():
    redir = _require_login()
    if redir:
        return redir
    if not _allowed('fixed_assets.fa_category_list'):
        abort(403)
    try:
        cid = int(request.form.get('category_id') or 0)
    except ValueError:
        cid = 0
    ok, err = delete_fa_category(cid)
    flash('Category deleted.' if ok else (err or 'Delete failed.'), 'success' if ok else 'error')
    return redirect(url_for('fixed_assets.fa_category_list'))


@bp.route('/assets', methods=('GET',))
def fa_asset_list():
    redir = _require_login()
    if redir:
        return redir
    if not _allowed('fixed_assets.fa_asset_list'):
        abort(403)
    status = (request.args.get('status') or '').strip().upper() or None
    category_id = None
    if request.args.get('category_id'):
        try:
            category_id = int(request.args.get('category_id'))
        except ValueError:
            category_id = None
    rows = list_fa_assets(status=status, category_id=category_id)
    categories = list_fa_categories()
    return render_template(
        'fixed_assets/asset_list.html',
        rows=rows,
        categories=categories,
        filter_status=status or '',
        filter_category_id=category_id,
        fa_nav_active='assets',
        fa_kpis=_asset_kpis(rows),
    )


@bp.route('/assets/form', methods=('GET', 'POST'))
def fa_asset_form():
    redir = _require_login()
    if redir:
        return redir
    if not _allowed('fixed_assets.fa_asset_list'):
        abort(403)
    asset_id = None
    row: dict = {}
    batch_lines: list = []
    if request.method == 'GET' and request.args.get('id'):
        try:
            asset_id = int(request.args.get('id') or 0)
        except ValueError:
            asset_id = 0
        existing = get_fa_asset(asset_id) if asset_id else None
        if not existing:
            flash('Asset not found.', 'error')
            return redirect(url_for('fixed_assets.fa_asset_list'))
        row = existing
        ad = row.get('acquisition_date')
        if hasattr(ad, 'strftime'):
            row['acquisition_date'] = ad.strftime('%Y-%m-%d')
    elif request.method == 'GET':
        row['acquisition_date'] = datetime.now().strftime('%Y-%m-%d')
    elif request.method == 'POST':
        try:
            with fa_form_save_guard():
                try:
                    asset_id = int(request.form.get('asset_id') or 0) or None
                except ValueError:
                    asset_id = None
                if asset_id:
                    ok, err, aid = save_fa_asset(
                        asset_id=asset_id,
                        name=request.form.get('name') or '',
                        category_id=int(request.form.get('category_id') or 0),
                        acquisition_date=request.form.get('acquisition_date') or '',
                        acquisition_cost=float(request.form.get('acquisition_cost') or 0),
                        salvage_value=float(request.form.get('salvage_value') or 0),
                        location_code=int(request.form.get('location_code') or 0) or None,
                        custodian=request.form.get('custodian') or '',
                        serial_no=request.form.get('serial_no') or '',
                        remarks=request.form.get('remarks') or '',
                        credit_account=request.form.get('credit_account') or '',
                        credit_party_type=request.form.get('credit_party_type') or '',
                        credit_party_code=request.form.get('credit_party_code') or '',
                        user=_user(),
                    )
                    if ok and aid:
                        flash('Asset saved.', 'success')
                        return redirect(url_for('fixed_assets.fa_asset_list'))
                    flash(err or 'Save failed.', 'error')
                    row = dict(request.form)
                    row['asset_id'] = asset_id
                else:
                    batch_lines = _parse_asset_register_lines_from_form()
                    if not batch_lines:
                        flash('Add at least one asset line.', 'error')
                    else:
                        acq_date = request.form.get('acquisition_date') or ''
                        credit_account = request.form.get('credit_account') or ''
                        credit_party_type = request.form.get('credit_party_type') or ''
                        credit_party_code = request.form.get('credit_party_code') or ''
                        remarks = request.form.get('remarks') or ''
                        try:
                            default_loc = int(request.form.get('default_location_code') or 0) or None
                        except (TypeError, ValueError):
                            default_loc = None
                        save_action = (request.form.get('save_action') or 'draft').strip().lower()
                        post_acq = save_action == 'post'
                        ok, err, saved_ids = save_fa_asset_register_batch(
                            lines=batch_lines,
                            acquisition_date=acq_date,
                            location_code=default_loc,
                            remarks=remarks,
                            credit_account=credit_account,
                            credit_party_type=credit_party_type,
                            credit_party_code=credit_party_code,
                            post_acq=post_acq,
                            user=_user(),
                        )
                        if ok and saved_ids:
                            if post_acq:
                                flash(f'Registered {len(saved_ids)} asset(s) and posted acquisition to GL.', 'success')
                            else:
                                flash(
                                    f'Saved {len(saved_ids)} asset(s) as draft. Post from the asset register when ready.',
                                    'success',
                                )
                            return redirect(url_for('fixed_assets.fa_asset_list'))
                        flash(err or 'Save failed.', 'error')
                    row = {
                        'acquisition_date': request.form.get('acquisition_date') or '',
                        'default_location_code': request.form.get('default_location_code') or '',
                        'remarks': request.form.get('remarks') or '',
                        'credit_account': request.form.get('credit_account') or '',
                        'credit_party_type': request.form.get('credit_party_type') or '',
                        'credit_party_code': request.form.get('credit_party_code') or '',
                    }
                    batch_lines = batch_lines or _parse_asset_register_lines_from_form()
        except FaSaveBlocked as ex:
            flash(str(ex), 'warning')
            try:
                asset_id = int(request.form.get('asset_id') or 0) or None
            except ValueError:
                asset_id = None
            if asset_id:
                row = dict(request.form)
                row['asset_id'] = asset_id
            else:
                batch_lines = _parse_asset_register_lines_from_form()
                row = {
                    'acquisition_date': request.form.get('acquisition_date') or '',
                    'default_location_code': request.form.get('default_location_code') or '',
                    'remarks': request.form.get('remarks') or '',
                    'credit_account': request.form.get('credit_account') or '',
                    'credit_party_type': request.form.get('credit_party_type') or '',
                    'credit_party_code': request.form.get('credit_party_code') or '',
                }
        except FaSaveReplay as ex:
            flash(str(ex), 'error')
            try:
                asset_id = int(request.form.get('asset_id') or 0) or None
            except ValueError:
                asset_id = None
            if asset_id:
                row = dict(request.form)
                row['asset_id'] = asset_id
            else:
                batch_lines = _parse_asset_register_lines_from_form()
                row = {
                    'acquisition_date': request.form.get('acquisition_date') or '',
                    'default_location_code': request.form.get('default_location_code') or '',
                    'remarks': request.form.get('remarks') or '',
                    'credit_account': request.form.get('credit_account') or '',
                    'credit_party_type': request.form.get('credit_party_type') or '',
                    'credit_party_code': request.form.get('credit_party_code') or '',
                }
    categories = list_fa_categories()
    locations = get_locations_list() or []
    save_nonce_kw = {}
    if request.method == 'POST':
        save_nonce_kw['global_save_nonce'] = reissue_fa_save_nonce()
    if asset_id or row.get('asset_id'):
        posted = str(row.get('posted_acq') or 'N').upper() == 'Y'
        credit_lookup_label = format_credit_lookup_label(
            row.get('credit_account'),
            row.get('credit_party_type'),
            row.get('credit_party_code'),
        )
        return render_template(
            'fixed_assets/asset_form.html',
            row=row,
            categories=categories,
            locations=locations,
            credit_lookup_label=credit_lookup_label,
            edit_mode=bool(row.get('asset_id')),
            posted=posted,
            fa_nav_active='assets',
            **save_nonce_kw,
        )
    display_lines = _fa_register_lines_for_display(
        batch_lines, categories=categories, locations=locations,
    )
    total_cost = round(sum(float(ln.get('acquisition_cost') or 0) for ln in display_lines), 2)
    total_salvage = round(sum(float(ln.get('salvage_value') or 0) for ln in display_lines), 2)
    credit_lookup_label = format_credit_lookup_label(
        row.get('credit_account'),
        row.get('credit_party_type'),
        row.get('credit_party_code'),
    )
    return render_template(
        'fixed_assets/asset_register_form.html',
        row=row,
        lines=display_lines,
        categories=categories,
        locations=locations,
        category_options=_fa_register_category_maps(categories),
        location_options=_fa_register_location_maps(locations),
        credit_lookup_label=credit_lookup_label,
        fa_total_cost=total_cost,
        fa_total_salvage=total_salvage,
        fa_nav_active='assets',
        **save_nonce_kw,
    )


@bp.route('/assets/post-acquisition', methods=('POST',))
def fa_asset_post_acquisition():
    redir = _require_login()
    if redir:
        return redir
    if not _allowed('fixed_assets.fa_asset_list'):
        abort(403)
    try:
        aid = int(request.form.get('asset_id') or 0)
    except ValueError:
        aid = 0
    try:
        with fa_post_action_guard():
            ok, err, vno = post_fa_acquisition(aid, user=_user())
    except FaSaveBlocked as ex:
        flash(str(ex), 'warning')
        ok = False
        err = str(ex)
        vno = None
    if ok:
        flash(f'Acquisition posted — voucher {vno}.', 'success')
    else:
        flash(err or 'Post failed.', 'error')
    if aid:
        return redirect(url_for('fixed_assets.fa_asset_form', id=aid))
    return redirect(url_for('fixed_assets.fa_asset_list'))


@bp.route('/depreciation', methods=('GET',))
def fa_depreciation_page():
    redir = _require_login()
    if redir:
        return redir
    if not _allowed('fixed_assets.fa_depreciation'):
        abort(403)
    period = (request.args.get('period') or datetime.now().strftime('%Y%m')).strip()
    runs = list_depreciation_runs()
    preview_lines = []
    preview_err = ''
    run = None
    run_lines = []
    if request.args.get('preview') == '1':
        ok, preview_err, preview_lines = preview_depreciation(period)
        if not ok:
            preview_lines = []
    run_id = request.args.get('run_id')
    if run_id:
        try:
            run = get_depreciation_run(int(run_id))
            if run:
                run_lines = list_depreciation_run_lines(int(run_id))
        except ValueError:
            run = None
    return render_template(
        'fixed_assets/depreciation_run.html',
        period=period,
        runs=runs,
        preview_lines=preview_lines,
        preview_err=preview_err,
        run=run,
        run_lines=run_lines,
        fa_nav_active='depreciation',
        fa_kpis=_depreciation_kpis(preview_lines, runs),
    )


@bp.route('/depreciation/preview', methods=('POST',))
def fa_depreciation_preview():
    redir = _require_login()
    if redir:
        return redir
    if not _allowed('fixed_assets.fa_depreciation'):
        abort(403)
    period = (request.form.get('period') or '').strip()
    return redirect(url_for('fixed_assets.fa_depreciation_page', period=period, preview='1'))


@bp.route('/depreciation/create-run', methods=('POST',))
def fa_depreciation_create_run():
    redir = _require_login()
    if redir:
        return redir
    if not _allowed('fixed_assets.fa_depreciation'):
        abort(403)
    period = (request.form.get('period') or '').strip()
    ok, err, run_id = create_depreciation_run(period, user=_user())
    if ok and run_id:
        flash('Depreciation run created (draft).', 'success')
        return redirect(url_for('fixed_assets.fa_depreciation_page', run_id=run_id))
    flash(err or 'Could not create run.', 'error')
    return redirect(url_for('fixed_assets.fa_depreciation_page', period=period))


@bp.route('/depreciation/post', methods=('POST',))
def fa_depreciation_post():
    redir = _require_login()
    if redir:
        return redir
    if not _allowed('fixed_assets.fa_depreciation'):
        abort(403)
    try:
        run_id = int(request.form.get('run_id') or 0)
    except ValueError:
        run_id = 0
    ok, err, vno = post_depreciation_run(run_id, user=_user())
    if ok:
        flash(f'Depreciation posted — voucher {vno}.', 'success')
    else:
        flash(err or 'Post failed.', 'error')
    return redirect(url_for('fixed_assets.fa_depreciation_page', run_id=run_id))


@bp.route('/api/preview', methods=('GET',))
def fa_api_preview():
    if not session.get('user'):
        return jsonify({'ok': False, 'error': 'Unauthorized'}), 401
    if not _allowed('fixed_assets.fa_depreciation'):
        return jsonify({'ok': False, 'error': 'Forbidden'}), 403
    period = (request.args.get('period') or '').strip()
    ok, err, lines = preview_depreciation(period)
    return jsonify({'ok': ok, 'error': err, 'lines': lines, 'total': round(sum(float(l.get('dep_amount') or 0) for l in lines), 2)})


def _disposal_kpis(rows: list) -> dict:
    total = len(rows or [])
    posted = sum(1 for r in rows or [] if str(r.get('status') or '').upper() == 'POSTED')
    draft = total - posted
    return {'total': total, 'posted': posted, 'draft': draft}


def _transfer_kpis(rows: list) -> dict:
    return {'total': len(rows or [])}


def _parse_asset_register_lines_from_form() -> list:
    names = request.form.getlist('line_name[]') or request.form.getlist('line_name')
    cats = request.form.getlist('line_category_id[]') or request.form.getlist('line_category_id')
    costs = request.form.getlist('line_cost[]') or request.form.getlist('line_cost')
    salvages = request.form.getlist('line_salvage[]') or request.form.getlist('line_salvage')
    serials = request.form.getlist('line_serial[]') or request.form.getlist('line_serial')
    custodians = request.form.getlist('line_custodian[]') or request.form.getlist('line_custodian')
    lines = []
    for i, raw_name in enumerate(names):
        name = str(raw_name or '').strip()
        if not name:
            continue
        try:
            cid = int(cats[i] if i < len(cats) else 0)
        except (TypeError, ValueError):
            continue
        if cid <= 0:
            continue
        try:
            cost = float(costs[i] if i < len(costs) else 0)
        except (TypeError, ValueError):
            cost = 0.0
        try:
            salvage = float(salvages[i] if i < len(salvages) else 0)
        except (TypeError, ValueError):
            salvage = 0.0
        lines.append({
            'name': name,
            'category_id': cid,
            'acquisition_cost': cost,
            'salvage_value': salvage,
            'serial_no': str(serials[i] if i < len(serials) else '').strip(),
            'custodian': str(custodians[i] if i < len(custodians) else '').strip(),
        })
    return lines


def _fa_register_category_maps(categories: list) -> dict:
    return {
        str(c.get('category_id')): f"{c.get('code') or ''} — {c.get('name') or ''}".strip(' —')
        for c in (categories or [])
        if c.get('category_id') is not None
    }


def _fa_register_location_maps(locations: list) -> dict:
    return {
        str(loc.get('code')): f"{loc.get('code') or ''} — {loc.get('name') or ''}".strip(' —')
        for loc in (locations or [])
        if loc.get('code') is not None
    }


def _fa_register_lines_for_display(lines: list, *, categories: list, locations: list) -> list:
    cat_map = _fa_register_category_maps(categories)
    out = []
    for ln in lines or []:
        cid = ln.get('category_id')
        out.append({
            **ln,
            'category_label': cat_map.get(str(cid), str(cid or '')),
        })
    return out


def _parse_sale_lines_from_form() -> list:
    asset_ids = request.form.getlist('line_asset_id[]') or request.form.getlist('line_asset_id')
    proceeds_list = request.form.getlist('line_proceeds[]') or request.form.getlist('line_proceeds')
    lines = []
    for i, raw_aid in enumerate(asset_ids):
        try:
            aid = int(raw_aid or 0)
        except (TypeError, ValueError):
            continue
        if aid <= 0:
            continue
        raw_pr = proceeds_list[i] if i < len(proceeds_list) else 0
        try:
            pr = float(raw_pr or 0)
        except (TypeError, ValueError):
            pr = 0.0
        lines.append({'asset_id': aid, 'proceeds_amount': pr})
    return lines


@bp.route('/disposals', methods=('GET',))
def fa_disposal_list():
    redir = _require_login()
    if redir:
        return redir
    if not _allowed('fixed_assets.fa_disposal_list'):
        abort(403)
    rows = list_fa_disposals()
    return render_template(
        'fixed_assets/disposal_list.html',
        rows=rows,
        fa_nav_active='disposal',
        fa_kpis=_disposal_kpis(rows),
        sale_mode=False,
    )


@bp.route('/disposals/form', methods=('GET', 'POST'))
def fa_disposal_form():
    redir = _require_login()
    if redir:
        return redir
    if not _allowed('fixed_assets.fa_disposal_list'):
        abort(403)
    disposal_id = None
    row: dict = {}
    selected_asset = None
    save_nonce_kw: dict = {}
    if request.method == 'GET':
        if request.args.get('id'):
            try:
                disposal_id = int(request.args.get('id') or 0)
            except ValueError:
                disposal_id = 0
            existing = get_fa_disposal(disposal_id) if disposal_id else None
            if not existing:
                flash('Disposal not found.', 'error')
                return redirect(url_for('fixed_assets.fa_disposal_list'))
            row = existing
            dd = row.get('disposal_date')
            if hasattr(dd, 'strftime'):
                row['disposal_date'] = dd.strftime('%Y-%m-%d')
            selected_asset = get_fa_asset(int(row.get('asset_id') or 0))
        elif request.args.get('asset_id'):
            try:
                selected_asset = get_fa_asset(int(request.args.get('asset_id') or 0))
            except ValueError:
                selected_asset = None
            if selected_asset:
                row['asset_id'] = selected_asset.get('asset_id')
    elif request.method == 'POST':
        save_nonce_kw = {}
        try:
            with fa_form_save_guard():
                try:
                    disposal_id = int(request.form.get('disposal_id') or 0) or None
                except ValueError:
                    disposal_id = None
                save_action = (request.form.get('save_action') or 'draft').strip().lower()
                post_now = save_action == 'post'
                common = dict(
                    disposal_id=disposal_id,
                    asset_id=int(request.form.get('asset_id') or 0),
                    disposal_date=request.form.get('disposal_date') or '',
                    disposal_type=request.form.get('disposal_type') or 'SALE',
                    proceeds_amount=float(request.form.get('proceeds_amount') or 0),
                    proceeds_account=request.form.get('proceeds_account') or '',
                    proceeds_party_type=request.form.get('proceeds_party_type') or '',
                    proceeds_party_code=request.form.get('proceeds_party_code') or '',
                    remarks=request.form.get('remarks') or '',
                    user=_user(),
                )
                if post_now:
                    ok, err, did, vno = save_fa_disposal_and_post(**common)
                    if ok and did:
                        flash(f'Disposal saved and posted (voucher {vno}).', 'success')
                        return redirect(url_for('fixed_assets.fa_disposal_form', id=did))
                else:
                    ok, err, did = save_fa_disposal(**common)
                    if ok and did:
                        flash('Disposal saved as draft. Post when ready from the form or disposal list.', 'success')
                        return redirect(url_for('fixed_assets.fa_disposal_form', id=did))
                flash(err or 'Save failed.', 'error')
                row = dict(request.form)
                row['disposal_id'] = disposal_id
                selected_asset = get_fa_asset(int(request.form.get('asset_id') or 0)) if request.form.get('asset_id') else None
        except FaSaveBlocked as ex:
            flash(str(ex), 'warning')
            try:
                disposal_id = int(request.form.get('disposal_id') or 0) or None
            except ValueError:
                disposal_id = None
            row = dict(request.form)
            row['disposal_id'] = disposal_id
            selected_asset = get_fa_asset(int(request.form.get('asset_id') or 0)) if request.form.get('asset_id') else None
        except FaSaveReplay as ex:
            flash(str(ex), 'error')
            try:
                disposal_id = int(request.form.get('disposal_id') or 0) or None
            except ValueError:
                disposal_id = None
            row = dict(request.form)
            row['disposal_id'] = disposal_id
            selected_asset = get_fa_asset(int(request.form.get('asset_id') or 0)) if request.form.get('asset_id') else None
        save_nonce_kw['global_save_nonce'] = reissue_fa_save_nonce()
    eligible_assets = list_fa_assets_eligible(for_disposal=True)
    if row.get('asset_id') and disposal_id:
        aid = int(row.get('asset_id') or 0)
        if not any(int(a.get('asset_id') or 0) == aid for a in eligible_assets):
            ex = get_fa_asset(aid)
            if ex:
                eligible_assets = [ex] + eligible_assets
    posted = str(row.get('status') or '').upper() == 'POSTED'
    proceeds_label = format_credit_lookup_label(
        row.get('proceeds_account'),
        row.get('proceeds_party_type'),
        row.get('proceeds_party_code'),
    )
    if selected_asset is None and row.get('asset_id'):
        selected_asset = get_fa_asset(int(row.get('asset_id') or 0))
    tpl_kw = save_nonce_kw if request.method == 'POST' else {}
    return render_template(
        'fixed_assets/disposal_form.html',
        row=row,
        eligible_assets=eligible_assets,
        selected_asset=selected_asset,
        proceeds_lookup_label=proceeds_label,
        edit_mode=bool(row.get('disposal_id')),
        posted=posted,
        fa_nav_active='disposal',
        sale_mode=False,
        list_endpoint='fixed_assets.fa_disposal_list',
        form_endpoint='fixed_assets.fa_disposal_form',
        post_endpoint='fixed_assets.fa_disposal_post',
        **tpl_kw,
    )


@bp.route('/disposals/post', methods=('POST',))
def fa_disposal_post():
    redir = _require_login()
    if redir:
        return redir
    if not _allowed('fixed_assets.fa_disposal_list'):
        abort(403)
    try:
        did = int(request.form.get('disposal_id') or 0)
    except ValueError:
        did = 0
    try:
        with fa_post_action_guard():
            ok, err, vno = post_fa_disposal(did, user=_user())
    except FaSaveBlocked as ex:
        flash(str(ex), 'warning')
        ok = False
        err = str(ex)
        vno = None
    if ok:
        flash(f'Disposal posted — voucher {vno}.', 'success')
    else:
        flash(err or 'Post failed.', 'error')
    if did:
        return redirect(url_for('fixed_assets.fa_disposal_form', id=did))
    return redirect(url_for('fixed_assets.fa_disposal_list'))


@bp.route('/sales', methods=('GET',))
def fa_sale_list():
    redir = _require_login()
    if redir:
        return redir
    if not _allowed('fixed_assets.fa_sale_list'):
        abort(403)
    rows = list_fa_sales()
    return render_template(
        'fixed_assets/sale_list.html',
        rows=rows,
        fa_nav_active='sale',
        fa_kpis=_disposal_kpis(rows),
    )


@bp.route('/sales/form', methods=('GET', 'POST'))
def fa_sale_form():
    redir = _require_login()
    if redir:
        return redir
    if not _allowed('fixed_assets.fa_sale_list'):
        abort(403)
    sale_id = None
    row: dict = {}
    lines: list = []
    save_nonce_kw: dict = {}
    if request.method == 'GET':
        if request.args.get('id'):
            try:
                sale_id = int(request.args.get('id') or 0)
            except ValueError:
                sale_id = 0
            existing = get_fa_sale(sale_id) if sale_id else None
            if not existing:
                flash('Sale not found.', 'error')
                return redirect(url_for('fixed_assets.fa_sale_list'))
            row = existing
            sd = row.get('sale_date')
            if hasattr(sd, 'strftime'):
                row['sale_date'] = sd.strftime('%Y-%m-%d')
            lines = row.get('lines') or []
        else:
            row['sale_date'] = datetime.now().strftime('%Y-%m-%d')
    elif request.method == 'POST':
        save_nonce_kw = {}
        try:
            with fa_form_save_guard():
                try:
                    sale_id = int(request.form.get('sale_id') or 0) or None
                except ValueError:
                    sale_id = None
                lines = _parse_sale_lines_from_form()
                save_action = (request.form.get('save_action') or 'draft').strip().lower()
                post_now = save_action == 'post'
                common = dict(
                    sale_id=sale_id,
                    sale_date=request.form.get('sale_date') or '',
                    proceeds_account=request.form.get('proceeds_account') or '',
                    proceeds_party_type=request.form.get('proceeds_party_type') or '',
                    proceeds_party_code=request.form.get('proceeds_party_code') or '',
                    remarks=request.form.get('remarks') or '',
                    lines=lines,
                    user=_user(),
                )
                if post_now:
                    ok, err, sid, vno = save_fa_sale_and_post(**common)
                    if ok and sid:
                        flash(f'Sale saved and posted (voucher {vno}).', 'success')
                        return redirect(url_for('fixed_assets.fa_sale_form', id=sid, pdf=1))
                else:
                    ok, err, sid = save_fa_sale(**common)
                    if ok and sid:
                        flash('Sale saved as draft. Post when ready from the form or sale list.', 'success')
                        return redirect(url_for('fixed_assets.fa_sale_form', id=sid))
                flash(err or 'Save failed.', 'error')
                row = {
                    'sale_id': sale_id,
                    'sale_date': request.form.get('sale_date') or '',
                    'proceeds_account': request.form.get('proceeds_account') or '',
                    'proceeds_party_type': request.form.get('proceeds_party_type') or '',
                    'proceeds_party_code': request.form.get('proceeds_party_code') or '',
                    'remarks': request.form.get('remarks') or '',
                }
                rebuilt = []
                for ln in lines:
                    asset = get_fa_asset(int(ln.get('asset_id') or 0))
                    if not asset:
                        continue
                    cost = round(float(asset.get('acquisition_cost') or 0), 2)
                    accum = round(float(asset.get('accum_dep') or 0), 2)
                    nbv = round(cost - accum, 2)
                    pr = round(float(ln.get('proceeds_amount') or 0), 2)
                    rebuilt.append({
                        'asset_id': asset.get('asset_id'),
                        'asset_no': asset.get('asset_no'),
                        'asset_name': asset.get('name'),
                        'acquisition_cost': cost,
                        'accum_dep': accum,
                        'nbv': nbv,
                        'proceeds_amount': pr,
                        'gain_loss_amount': round(pr - nbv, 2),
                    })
                lines = rebuilt
        except FaSaveBlocked as ex:
            flash(str(ex), 'warning')
            try:
                sale_id = int(request.form.get('sale_id') or 0) or None
            except ValueError:
                sale_id = None
            lines = _parse_sale_lines_from_form()
            row = {
                'sale_id': sale_id,
                'sale_date': request.form.get('sale_date') or '',
                'proceeds_account': request.form.get('proceeds_account') or '',
                'proceeds_party_type': request.form.get('proceeds_party_type') or '',
                'proceeds_party_code': request.form.get('proceeds_party_code') or '',
                'remarks': request.form.get('remarks') or '',
            }
        except FaSaveReplay as ex:
            flash(str(ex), 'error')
            try:
                sale_id = int(request.form.get('sale_id') or 0) or None
            except ValueError:
                sale_id = None
            lines = _parse_sale_lines_from_form()
            row = {
                'sale_id': sale_id,
                'sale_date': request.form.get('sale_date') or '',
                'proceeds_account': request.form.get('proceeds_account') or '',
                'proceeds_party_type': request.form.get('proceeds_party_type') or '',
                'proceeds_party_code': request.form.get('proceeds_party_code') or '',
                'remarks': request.form.get('remarks') or '',
            }
        save_nonce_kw['global_save_nonce'] = reissue_fa_save_nonce()
    if sale_id and not lines and row.get('lines'):
        lines = row.get('lines') or []
    # Include assets already on this draft so they remain selectable when editing
    eligible_assets = list_fa_assets_eligible(for_disposal=True)
    for ln in lines or []:
        aid = int(ln.get('asset_id') or 0)
        if aid and not any(int(a.get('asset_id') or 0) == aid for a in eligible_assets):
            ex = get_fa_asset(aid)
            if ex:
                eligible_assets = [ex] + eligible_assets
    posted = str(row.get('status') or '').upper() == 'POSTED'
    proceeds_label = format_credit_lookup_label(
        row.get('proceeds_account'),
        row.get('proceeds_party_type'),
        row.get('proceeds_party_code'),
    )
    total_proceeds = round(sum(float(l.get('proceeds_amount') or 0) for l in lines or []), 2)
    total_cost = round(sum(float(l.get('acquisition_cost') or 0) for l in lines or []), 2)
    total_accum = round(sum(float(l.get('accum_dep') or 0) for l in lines or []), 2)
    total_nbv = round(sum(float(l.get('nbv') or 0) for l in lines or []), 2)
    total_gain = round(total_proceeds - total_nbv, 2)
    return render_template(
        'fixed_assets/sale_form.html',
        row=row,
        lines=lines or [],
        eligible_assets=eligible_assets,
        proceeds_lookup_label=proceeds_label,
        edit_mode=bool(row.get('sale_id') or sale_id),
        posted=posted,
        fa_nav_active='sale',
        fa_cost=total_cost,
        fa_accum=total_accum,
        fa_nbv=total_nbv,
        fa_proceeds=total_proceeds,
        fa_gain_loss=total_gain,
        fa_has_asset=bool(lines),
        **(save_nonce_kw if request.method == 'POST' else {}),
    )


@bp.route('/sales/post', methods=('POST',))
def fa_sale_post():
    redir = _require_login()
    if redir:
        return redir
    if not _allowed('fixed_assets.fa_sale_list'):
        abort(403)
    try:
        sid = int(request.form.get('sale_id') or 0)
    except ValueError:
        sid = 0
    try:
        with fa_post_action_guard():
            ok, err, vno = post_fa_sale(sid, user=_user())
    except FaSaveBlocked as ex:
        flash(str(ex), 'warning')
        ok = False
        err = str(ex)
        vno = None
    if ok:
        flash(f'Sale posted — voucher {vno}.', 'success')
        if sid:
            return redirect(url_for('fixed_assets.fa_sale_form', id=sid, pdf=1))
    else:
        flash(err or 'Post failed.', 'error')
    if sid:
        return redirect(url_for('fixed_assets.fa_sale_form', id=sid))
    return redirect(url_for('fixed_assets.fa_sale_list'))


@bp.route('/sales/pdf/<int:sale_id>', methods=('GET',))
def fa_sale_pdf(sale_id: int):
    redir = _require_login()
    if redir:
        return redir
    if not _allowed('fixed_assets.fa_sale_list'):
        abort(403)
    from addons.fixed_assets.fa_sale_pdf import build_fa_sale_pdf
    import io
    pdf_bytes, err = build_fa_sale_pdf(int(sale_id))
    if err or not pdf_bytes:
        flash(err or 'Could not build PDF.', 'error')
        return redirect(url_for('fixed_assets.fa_sale_form', id=sale_id))
    sale = get_fa_sale(int(sale_id)) or {}
    fname = f"FA_Sale_{sale.get('sale_no') or sale_id}.pdf"
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=False,
        download_name=fname,
    )


@bp.route('/transfers', methods=('GET',))
def fa_transfer_list():
    redir = _require_login()
    if redir:
        return redir
    if not _allowed('fixed_assets.fa_transfer_list'):
        abort(403)
    rows = list_fa_transfers()
    return render_template(
        'fixed_assets/transfer_list.html',
        rows=rows,
        fa_nav_active='transfer',
        fa_kpis=_transfer_kpis(rows),
    )


@bp.route('/transfers/form', methods=('GET', 'POST'))
def fa_transfer_form():
    redir = _require_login()
    if redir:
        return redir
    if not _allowed('fixed_assets.fa_transfer_list'):
        abort(403)
    row: dict = {}
    selected_asset = None
    if request.method == 'GET' and request.args.get('asset_id'):
        try:
            selected_asset = get_fa_asset(int(request.args.get('asset_id') or 0))
        except ValueError:
            selected_asset = None
        if selected_asset:
            row['asset_id'] = selected_asset.get('asset_id')
    elif request.method == 'POST':
        ok, err, tid = create_fa_transfer(
            asset_id=int(request.form.get('asset_id') or 0),
            transfer_date=request.form.get('transfer_date') or '',
            to_location_code=int(request.form.get('to_location_code') or 0) or None,
            to_custodian=request.form.get('to_custodian') or '',
            remarks=request.form.get('remarks') or '',
            user=_user(),
        )
        if ok and tid:
            flash('Transfer recorded.', 'success')
            return redirect(url_for('fixed_assets.fa_transfer_list'))
        flash(err or 'Transfer failed.', 'error')
        row = dict(request.form)
        selected_asset = get_fa_asset(int(request.form.get('asset_id') or 0)) if request.form.get('asset_id') else None
    eligible_assets = list_fa_assets_eligible(for_transfer=True)
    locations = get_locations_list() or []
    if selected_asset is None and row.get('asset_id'):
        selected_asset = get_fa_asset(int(row.get('asset_id') or 0))
    return render_template(
        'fixed_assets/transfer_form.html',
        row=row,
        eligible_assets=eligible_assets,
        selected_asset=selected_asset,
        locations=locations,
        fa_nav_active='transfer',
    )
