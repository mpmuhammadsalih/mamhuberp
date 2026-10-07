"""Authentication blueprint - handles login and logout (single database)."""
from pathlib import Path
from nexa_http import Blueprint, jsonify, redirect, render_template, request, session, flash, url_for
from db import PRIVILEGED_USERS, verify_user, get_user_employeecode, get_user_tenant_id, get_location_info_by_dbkey, get_locationmaster_base_dbcode, get_user_multilocations_view, update_user_password, get_username_by_employeecode, _safe_rows_auth
from nexa_http.layout_cache import warm_layout_cache, invalidate_layout_cache
from config.settings import is_multi_db_mode
_ADDON_ROOT = Path(__file__).resolve().parents[1]
_LOGIN_LOGO_PATH = _ADDON_ROOT.parent.parent / 'static' / 'img' / 'nexus-erp-logo.png'
# Match addon manifest ``urls.prefix`` so ``/auth/login`` works (bookmarks, JS, old links).
bp = Blueprint('auth', __name__, url_prefix='/auth', template_folder=str(_ADDON_ROOT / 'views' / 'templates'))

def _login_logo_cache_key() -> str:
    """Bust browser caches when the login PNG on disk changes."""
    try:
        return str(int(_LOGIN_LOGO_PATH.stat().st_mtime))
    except OSError:
        return '1'


def _apply_login_no_cache_headers(response):
    headers = getattr(response, 'headers', None)
    if headers is None:
        return response
    headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    headers['Pragma'] = 'no-cache'
    headers['Expires'] = '0'
    return response


@bp.after_request
def _auth_login_page_no_cache(response):
    from nexa_http import context as nexa_ctx
    req = nexa_ctx.get_current_request()
    if req is None:
        return response
    path = (req.url.path or '').rstrip('/').lower()
    if not path.endswith('/auth/login'):
        return response
    media = (getattr(response, 'media_type', None) or '').lower()
    if 'html' in media or type(response).__name__ == 'TemplateResponse':
        return _apply_login_no_cache_headers(response)
    return response

def _safe_relative_next(raw: str | None) -> str | None:
    """Allow only relative same-origin paths for ?next= redirects (post-login)."""
    if not raw:
        return None
    s = raw.strip()
    if not s.startswith('/') or s.startswith('//'):
        return None
    return s

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        if session.get('user'):
            nxt = _safe_relative_next(request.args.get('next'))
            return redirect(nxt or url_for('dashboard.dashboard'))
        return render_template(
            'auth/login.html',
            next_url=_safe_relative_next(request.args.get('next')),
            login_logo_v=_login_logo_cache_key(),
        )

    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    next_post = _safe_relative_next(request.form.get('next'))

    if not verify_user(username, password):
        resolved = get_username_by_employeecode(username)
        if resolved and verify_user(resolved, password):
            username = resolved
        else:
            session.clear()
            flash('Invalid username or password.', 'error')
            return render_template('auth/login.html', next_url=next_post, login_logo_v=_login_logo_cache_key())
    # Store canonical username casing from DB (password updates match on exact row).
    canon_rows = _safe_rows_auth(
        'SELECT username FROM login_users WHERE UPPER(TRIM(username)) = UPPER(TRIM(:username))',
        {'username': username},
    )
    if canon_rows and canon_rows[0].get('username'):
        username = str(canon_rows[0]['username']).strip()
    if is_multi_db_mode():
        if username.lower() not in PRIVILEGED_USERS:
            tenant_id = get_user_tenant_id(username)
            if not tenant_id:
                session.clear()
                flash('No tenant assigned. Please contact IT.', 'error')
                return render_template('auth/login.html', next_url=next_post, login_logo_v=_login_logo_cache_key())
    session.clear()
    session.permanent = True
    session['user'] = username
    session['employeecode'] = get_user_employeecode(username)
    tenant_id = get_user_tenant_id(username) if is_multi_db_mode() else None
    if tenant_id:
        session['tenant_id'] = tenant_id
        try:
            from nexa_http import g
            g.current_tenant_id = tenant_id
        except RuntimeError:
            pass
    if is_multi_db_mode() and tenant_id:
        skip_branch_dbcode = username.lower() in PRIVILEGED_USERS or str(tenant_id).strip().upper() == 'HO' or get_user_multilocations_view(username) == 'Y'
        if not skip_branch_dbcode:
            base_dbcode = get_locationmaster_base_dbcode()
            if base_dbcode is not None and str(base_dbcode).strip():
                if str(tenant_id).strip().upper() != str(base_dbcode).strip().upper():
                    session.clear()
                    flash('Tenant ID does not match branch (LOCATIONMASTER.DBCODE). Contact IT.', 'error')
                    return render_template('auth/login.html', next_url=next_post, login_logo_v=_login_logo_cache_key())
    try:
        location_info = get_location_info_by_dbkey(None)
        if location_info:
            db_locationcode = location_info.get('locationcode')
            if db_locationcode is not None:
                try:
                    db_locationcode = int(db_locationcode) if isinstance(db_locationcode, (int, float)) else int(float(str(db_locationcode).strip()))
                except (TypeError, ValueError):
                    db_locationcode = None
            location_name = (location_info.get('locationname') or '').strip()
            if tenant_id:
                session['location_code'] = db_locationcode
                if location_name:
                    session['location_name'] = location_name
            else:
                if db_locationcode is not None:
                    session['location_code'] = db_locationcode
                if location_name:
                    session['location_name'] = location_name
    except Exception as e:
        print(f'[DEBUG login] Error fetching location: {e}')
    try:
        warm_layout_cache(session, username)
    except Exception as e:
        print(f'[DEBUG login] Error warming layout cache: {e}')
    nxt = _safe_relative_next(request.form.get('next'))
    return redirect(nxt or url_for('dashboard.dashboard'))

@bp.route('/logout')
def logout():
    invalidate_layout_cache(session)
    session.clear()
    return redirect('/auth/login')

@bp.route('/change-password', methods=['GET'])
def change_password():
    """Display password change page"""
    if not session.get('user'):
        flash('Please login first.', 'error')
        return redirect('/auth/login')
    return render_template('auth/change_password.html')

@bp.route('/api/change-password', methods=['POST'])
def update_password():
    """API endpoint to update user password"""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    username = session.get('user')
    data = request.get_json() or {}
    old_password = data.get('old_password', '').strip()
    new_password = data.get('new_password', '').strip()
    confirm_password = data.get('confirm_password', '').strip()
    if not old_password:
        return jsonify({'success': False, 'error': 'Old password is required'}, 400)
    if not new_password:
        return jsonify({'success': False, 'error': 'New password is required'}, 400)
    if len(new_password) < 6:
        return jsonify({'success': False, 'error': 'New password must be at least 6 characters long'}, 400)
    if new_password != confirm_password:
        return jsonify({'success': False, 'error': 'New password and confirm password do not match'}, 400)
    if old_password == new_password:
        return jsonify({'success': False, 'error': 'New password must be different from old password'}, 400)
    try:
        if update_user_password(username, old_password, new_password):
            return jsonify({'success': True, 'message': 'Password changed successfully'})
        else:
            return jsonify({'success': False, 'error': 'Invalid old password'}, 400)
    except Exception as e:
        print(f'[ERROR update_password] {e}')
        return jsonify({'success': False, 'error': 'An error occurred while updating password'}, 500)
