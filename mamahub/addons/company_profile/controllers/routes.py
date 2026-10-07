"""Company profile: org details and logo (tenant DB)."""
from pathlib import Path
import os
import secrets
from datetime import datetime
from nexa_http import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from werkzeug.utils import secure_filename
from db import delete_company_profile_row, get_company_profile_by_id, insert_company_profile_row, list_company_profiles, save_company_profile_row
_ADDON_ROOT = Path(__file__).resolve().parents[1]
bp = Blueprint('company_profile', __name__, template_folder=str(_ADDON_ROOT / 'views' / 'templates'))
_ALLOWED_LOGO_EXT = {'.png', '.jpg', '.jpeg', '.webp', '.gif'}
_COMPANY_PROFILE_NEW_NONCE_KEY = '_company_profile_new_nonce'


def _company_list_kpis(rows):
    """Aggregate KPIs for the companies list (full result set, not client-side search)."""
    rows = rows or []
    total = len(rows)
    with_email = with_phone = with_city = with_logo = 0
    for r in rows:
        if str(r.get('email') or '').strip():
            with_email += 1
        if str(r.get('phone') or '').strip():
            with_phone += 1
        if str(r.get('city') or '').strip():
            with_city += 1
        lm = str(r.get('logo_mode') or '').strip().lower()
        if lm == 'url' and str(r.get('logo_url') or '').strip():
            with_logo += 1
        elif lm == 'upload' and str(r.get('logo_path') or '').strip():
            with_logo += 1
    return {'total': total, 'with_email': with_email, 'with_phone': with_phone, 'with_city': with_city, 'with_logo': with_logo}


def _save_logo_file(upload) -> str:
    """Save under static/uploads/company_profile; return path for static url_for (e.g. uploads/company_profile/x.png)."""
    if not upload or not getattr(upload, 'filename', ''):
        return ''
    original = str(upload.filename or '').strip()
    ext = os.path.splitext(original)[1].lower()
    if ext not in _ALLOWED_LOGO_EXT:
        raise ValueError('Logo must be PNG, JPG, JPEG, WEBP, or GIF.')
    tid = session.get('tenant_id') or 'default'
    if isinstance(tid, str):
        safe_tid = secure_filename(tid.strip()) or 'default'
    else:
        safe_tid = 'default'
    stamp = datetime.now().strftime('%Y%m%d%H%M%S')
    filename = f'logo_{safe_tid}_{stamp}{ext}'
    target_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'company_profile')
    os.makedirs(target_dir, exist_ok=True)
    full_path = os.path.join(target_dir, filename)
    upload.save(full_path)
    return f'uploads/company_profile/{filename}'

def _gather_profile_form(base: dict) -> tuple:
    logo_mode = (request.form.get('logo_mode') or 'none').strip().lower()
    if logo_mode not in ('none', 'upload', 'url'):
        logo_mode = 'none'
    next_data = {'company_name': (request.form.get('company_name') or '').strip(), 'legal_name': (request.form.get('legal_name') or '').strip(), 'address1': (request.form.get('address1') or '').strip(), 'address2': (request.form.get('address2') or '').strip(), 'city': (request.form.get('city') or '').strip(), 'state_region': (request.form.get('state_region') or '').strip(), 'country': (request.form.get('country') or '').strip(), 'postal_code': (request.form.get('postal_code') or '').strip(), 'phone': (request.form.get('phone') or '').strip(), 'email': (request.form.get('email') or '').strip(), 'website': (request.form.get('website') or '').strip(), 'tax_id': (request.form.get('tax_id') or '').strip(), 'logo_mode': logo_mode}
    next_data['logo_path'] = None
    next_data['logo_url'] = None
    existing_path = (base.get('logo_path') or base.get('LOGO_PATH') or '').strip()
    if logo_mode == 'url':
        next_data['logo_url'] = (request.form.get('logo_url') or '').strip()[:500]
    elif logo_mode == 'upload':
        up = request.files.get('logo_file')
        if up and str(getattr(up, 'filename', '') or '').strip():
            next_data['logo_path'] = _save_logo_file(up)
        else:
            next_data['logo_path'] = existing_path or None
    else:
        next_data['logo_path'] = None
        next_data['logo_url'] = None
    return (next_data, logo_mode)

@bp.route('/setup/companies', methods=['GET'])
def company_list():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    rows = list_company_profiles()
    kpis = _company_list_kpis(rows)
    return render_template('company_profile/company_profiles_list.html', companies=rows, company_kpis=kpis)

@bp.route('/setup/company-profile/<int:company_id>/delete', methods=('POST',))
def company_profile_delete(company_id: int):
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    cid = int(company_id)
    profile = get_company_profile_by_id(cid)
    if not profile:
        flash('Company not found.', 'error')
        return redirect(url_for('company_profile.company_list'))
    label = profile.get('company_name') or profile.get('COMPANY_NAME') or profile.get('legal_name') or profile.get('LEGAL_NAME') or ''
    try:
        deleted = delete_company_profile_row(cid)
    except Exception as exc:
        flash(f'Delete failed: {exc}', 'error')
        return redirect(url_for('company_profile.company_list'))
    if deleted < 1:
        flash('Company not found (nothing deleted).', 'error')
        return redirect(url_for('company_profile.company_list'))
    msg = 'Company #%s%s deleted.' % (cid, ' (%s)' % str(label).strip()[:80] if str(label or '').strip() else '')
    if cid == 1:
        msg += ' Warning: integrations that assume company ID 1 may need attention.'
    flash(msg, 'success')
    return redirect(url_for('company_profile.company_list'))

@bp.route('/setup/company-profile/new', methods=['GET', 'POST'])
def company_profile_new():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if request.method == 'POST':
        posted_nonce = (request.form.get('cp_new_nonce') or '').strip()
        expected_nonce = session.get(_COMPANY_PROFILE_NEW_NONCE_KEY)
        if not posted_nonce or not expected_nonce or posted_nonce != expected_nonce:
            flash('This create form expired or was already used. Refresh the page and try again.', 'error')
            return redirect(url_for('company_profile.company_profile_new'))
        try:
            next_data, _logo_mode = _gather_profile_form({})
        except ValueError as exc:
            flash(str(exc), 'error')
            nonce = secrets.token_hex(16)
            session[_COMPANY_PROFILE_NEW_NONCE_KEY] = nonce
            return render_template('company_profile/company_profile.html', profile={}, company_id=None, is_new=True, cp_new_nonce=nonce)
        try:
            insert_company_profile_row(next_data)
        except Exception as exc:
            flash(f'Save failed: {exc}', 'error')
            nonce = secrets.token_hex(16)
            session[_COMPANY_PROFILE_NEW_NONCE_KEY] = nonce
            return render_template('company_profile/company_profile.html', profile=next_data, company_id=None, is_new=True, cp_new_nonce=nonce)
        session.pop(_COMPANY_PROFILE_NEW_NONCE_KEY, None)
        flash('Company created.', 'success')
        return redirect(url_for('company_profile.company_list'))
    nonce = secrets.token_hex(16)
    session[_COMPANY_PROFILE_NEW_NONCE_KEY] = nonce
    return render_template('company_profile/company_profile.html', profile={}, company_id=None, is_new=True, cp_new_nonce=nonce)

@bp.route('/setup/company-profile/<int:company_id>', methods=['GET', 'POST'])
def company_profile_edit(company_id: int):
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    cid = int(company_id)
    profile = get_company_profile_by_id(cid)
    if request.method == 'GET' and (not profile) and (cid != 1):
        flash('Company not found.', 'error')
        return redirect(url_for('company_profile.company_list'))
    if request.method == 'POST':
        profile = get_company_profile_by_id(cid) or {}
        try:
            next_data, logo_mode = _gather_profile_form(profile)
        except ValueError as exc:
            flash(str(exc), 'error')
            merged = {**profile, **next_data, 'logo_mode': logo_mode}
            return render_template('company_profile/company_profile.html', profile=merged, company_id=cid, is_new=False)
        try:
            save_company_profile_row(next_data, company_id=cid)
        except Exception as exc:
            flash(f'Save failed: {exc}', 'error')
            return render_template('company_profile/company_profile.html', profile=get_company_profile_by_id(cid), company_id=cid, is_new=False)
        flash('Company profile saved.', 'success')
        return redirect(url_for('company_profile.company_profile_edit', company_id=cid))
    return render_template('company_profile/company_profile.html', profile=profile, company_id=cid, is_new=False)

@bp.route('/setup/company-profile', methods=['GET', 'POST'])
def company_profile_page():
    """Legacy bookmark: GET shows company list; POST still saves primary company (ID=1)."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if request.method == 'GET':
        return redirect(url_for('company_profile.company_list'))
    return company_profile_edit(company_id=1)
