"""Period Closing routes (registered on accounts blueprint)."""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Dict, Optional

from nexa_http import jsonify, redirect, render_template, request, session, url_for

from addons.accounts.period_closing_db import (
    CLOSE_MONTHLY,
    CLOSE_YEAR_END,
    build_closing_preview,
    can_close_period,
    can_reopen_period,
    close_period,
    delete_temp_bill_drafts,
    ensure_period_closing_tables,
    ensure_periods_for_year,
    get_closing_log,
    get_period,
    header_cards,
    is_period_closed_for_date,
    is_period_closing_admin,
    list_closed_periods,
    list_closing_history,
    list_temp_bill_drafts,
    reopen_period,
    validate_period_for_closing,
)
from db import get_user_role_id
from save_nonce import (
    GLOBAL_SAVE_NONCE_SESSION_KEY,
    commit_form_save_nonce,
    extract_submitted_save_nonce,
    json_response_keep_global_nonce,
    json_response_rotate_global,
    reject_invalid_form_save_nonce,
    replay_blocked_response_global,
)

_PERIOD_CLOSE_SESSION_LOCK_UNTIL = '_period_close_session_lock_until'
_PERIOD_REOPEN_SESSION_LOCK_UNTIL = '_period_reopen_session_lock_until'


def _try_acquire_session_lock(lock_key: str, lock_seconds: float = 180.0) -> bool:
    now = time.time()
    raw = session.get(lock_key)
    try:
        until = float(raw)
        if until > now:
            return False
    except (TypeError, ValueError):
        pass
    session[lock_key] = now + float(lock_seconds)
    session.modified = True
    return True


def _release_session_lock(lock_key: str) -> None:
    session.pop(lock_key, None)
    session.modified = True


def _loc() -> int:
    try:
        return int(session.get('location_code') or 1)
    except (TypeError, ValueError):
        return 1


def _user() -> str:
    return str(session.get('user') or '').strip()


def _role_id() -> Optional[str]:
    try:
        return get_user_role_id(_user())
    except Exception:
        return session.get('role_id')


def _fy_options() -> list:
    years = []
    try:
        from addons.fiscal_year.fiscal_year_db import list_fiscal_years
        for r in list_fiscal_years(include_closed=True) or []:
            code = str(r.get('year_code') or r.get('YEAR_CODE') or '').strip()
            name = str(r.get('year_name') or r.get('YEAR_NAME') or code).strip()
            if code:
                years.append({'id': code, 'label': name or code})
    except Exception:
        pass
    if not years:
        y = datetime.now().year
        years = [{'id': str(y), 'label': f'FY {y}'}]
    return years


def _default_fy_month() -> tuple:
    opts = _fy_options()
    fy = opts[0]['id'] if opts else str(datetime.now().year)
    # Prefer current calendar month that exists in periods
    month = datetime.now().month
    return fy, month


def _caps() -> Dict[str, bool]:
    u, r = _user(), _role_id()
    admin = is_period_closing_admin(u, r)
    return {
        'is_admin': admin,
        'can_close': can_close_period(u, r),
        'can_reopen': can_reopen_period(u, r),
        'can_preview': True,  # menu permission gates page access
    }


def register(bp) -> None:
    """Attach Period Closing routes to the accounts blueprint."""

    @bp.route('/accounts/period-closing', methods=['GET'])
    def period_closing_page():
        if not session.get('user'):
            return redirect(url_for('auth.login'))
        from addons.accounts.controllers.routes import _apply_db
        if not _apply_db():
            return redirect(url_for('dashboard.dashboard'))
        ensure_period_closing_tables()
        fy_opts = _fy_options()
        fy = (request.args.get('financial_year') or '').strip() or (fy_opts[0]['id'] if fy_opts else str(datetime.now().year))
        try:
            month = int(request.args.get('month') or datetime.now().month)
        except (TypeError, ValueError):
            month = datetime.now().month
        month = max(1, min(12, month))
        closing_type = (request.args.get('closing_type') or CLOSE_MONTHLY).strip().upper()
        if closing_type not in (CLOSE_MONTHLY, CLOSE_YEAR_END):
            closing_type = CLOSE_MONTHLY
        loc = _loc()
        cards = header_cards(fy, month, loc)
        period = cards.get('current') or get_period(fy, month, loc)
        preview = None
        if period:
            preview = build_closing_preview(period['start_date'], period['end_date'])
        validation = validate_period_for_closing(fy, month, loc)
        return render_template(
            'accounts/period_closing.html',
            fy_options=fy_opts,
            financial_year=fy,
            month=month,
            closing_type=closing_type,
            cards=cards,
            periods=cards.get('periods') or [],
            preview=preview,
            validation=validation,
            caps=_caps(),
            close_monthly=CLOSE_MONTHLY,
            close_year_end=CLOSE_YEAR_END,
        )

    @bp.route('/accounts/period-closing/history', methods=['GET'])
    def period_closing_history_page():
        if not session.get('user'):
            return redirect(url_for('auth.login'))
        from addons.accounts.controllers.routes import _apply_db
        if not _apply_db():
            return redirect(url_for('dashboard.dashboard'))
        ensure_period_closing_tables()
        fy = (request.args.get('financial_year') or '').strip() or None
        rows = list_closing_history(fy, _loc())
        return render_template(
            'accounts/period_closing_history.html',
            rows=rows,
            financial_year=fy or '',
            fy_options=_fy_options(),
            caps=_caps(),
        )

    @bp.route('/accounts/api/period-closing/preview', methods=['GET'])
    def api_period_closing_preview():
        if not session.get('user'):
            return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
        fy = (request.args.get('financial_year') or '').strip()
        try:
            month = int(request.args.get('month') or 0)
        except (TypeError, ValueError):
            month = 0
        if not fy or month < 1 or month > 12:
            return jsonify({'success': False, 'error': 'financial_year and month are required'})
        loc = _loc()
        ensure_periods_for_year(fy, loc)
        period = get_period(fy, month, loc)
        if not period:
            return jsonify({'success': False, 'error': 'Period not found'})
        preview = build_closing_preview(period['start_date'], period['end_date'])
        validation = validate_period_for_closing(fy, month, loc)
        cards = header_cards(fy, month, loc)
        return jsonify({
            'success': True,
            'period': period,
            'preview': preview,
            'validation': validation,
            'cards': cards,
            'periods': cards.get('periods') or [],
        })

    @bp.route('/accounts/api/period-closing/validate', methods=['GET'])
    def api_period_closing_validate():
        if not session.get('user'):
            return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
        fy = (request.args.get('financial_year') or '').strip()
        try:
            month = int(request.args.get('month') or 0)
        except (TypeError, ValueError):
            month = 0
        if not fy or month < 1 or month > 12:
            return jsonify({'success': False, 'error': 'financial_year and month are required'})
        return jsonify({'success': True, **validate_period_for_closing(fy, month, _loc())})

    @bp.route('/accounts/api/period-closing/closed-periods', methods=['GET'])
    def api_period_closing_closed_periods():
        """Closed period ranges for voucher date guards (Journal Entry, etc.)."""
        if not session.get('user'):
            return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
        d = (request.args.get('date') or '').strip()
        rows = list_closed_periods(_loc())
        payload: Dict[str, Any] = {'success': True, 'closed_periods': rows}
        if d:
            msg = is_period_closed_for_date(d, _loc())
            payload['date'] = d[:10]
            payload['closed'] = bool(msg)
            payload['message'] = msg or ''
        return jsonify(payload)

    @bp.route('/accounts/api/period-closing/close', methods=['POST'])
    def api_period_closing_close():
        """Confirm close: session lock → save-once nonce → single DB transaction."""
        if not session.get('user'):
            return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
        if not can_close_period(_user(), _role_id()):
            return jsonify({'success': False, 'error': 'Only administrators can close periods.'}, 403)
        if not _try_acquire_session_lock(_PERIOD_CLOSE_SESSION_LOCK_UNTIL, 180.0):
            return json_response_keep_global_nonce({
                'success': False,
                'error': 'Period closing is already in progress for this session. Please wait until it completes.',
                'save_session_locked': True,
            }, 423)
        try:
            submitted_nonce = extract_submitted_save_nonce(request)
            if not reject_invalid_form_save_nonce(submitted_nonce, session_key=GLOBAL_SAVE_NONCE_SESSION_KEY):
                return replay_blocked_response_global()
            data = request.get_json(silent=True) or {}
            fy = (data.get('financial_year') or request.form.get('financial_year') or '').strip()
            try:
                month = int(data.get('month') or request.form.get('month') or 0)
            except (TypeError, ValueError):
                month = 0
            ctype = (data.get('closing_type') or request.form.get('closing_type') or CLOSE_MONTHLY).strip().upper()
            if not fy or month < 1 or month > 12:
                return json_response_keep_global_nonce({
                    'success': False,
                    'error': 'financial_year and month are required',
                }, 400)
            # Consume token before DB work so double-submit cannot post twice.
            if not commit_form_save_nonce(submitted_nonce, session_key=GLOBAL_SAVE_NONCE_SESSION_KEY):
                return replay_blocked_response_global()
            result = close_period(fy, month, ctype, _user(), _loc())
            # Always rotate after consume (success or failure) so client can retry safely.
            if not result.get('success'):
                return json_response_rotate_global(result, 400)
            return json_response_rotate_global(result, 200)
        finally:
            _release_session_lock(_PERIOD_CLOSE_SESSION_LOCK_UNTIL)

    @bp.route('/accounts/api/period-closing/reopen', methods=['POST'])
    def api_period_closing_reopen():
        """Confirm reopen: session lock → save-once nonce → DB work."""
        if not session.get('user'):
            return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
        if not can_reopen_period(_user(), _role_id()):
            return jsonify({'success': False, 'error': 'Only administrators can reopen periods.'}, 403)
        if not _try_acquire_session_lock(_PERIOD_REOPEN_SESSION_LOCK_UNTIL, 120.0):
            return json_response_keep_global_nonce({
                'success': False,
                'error': 'Period reopen is already in progress for this session. Please wait until it completes.',
                'save_session_locked': True,
            }, 423)
        try:
            submitted_nonce = extract_submitted_save_nonce(request)
            if not reject_invalid_form_save_nonce(submitted_nonce, session_key=GLOBAL_SAVE_NONCE_SESSION_KEY):
                return replay_blocked_response_global()
            data = request.get_json(silent=True) or {}
            fy = (data.get('financial_year') or '').strip()
            try:
                month = int(data.get('month') or 0)
            except (TypeError, ValueError):
                month = 0
            reason = (data.get('reason') or '').strip()
            rev_raw = data.get('reverse_closing_journal')
            if rev_raw is None:
                rev_raw = data.get('reverse_journal')
            reverse_closing_journal = str(rev_raw).strip().lower() in (
                '1', 'true', 'yes', 'y', 'on',
            ) if not isinstance(rev_raw, bool) else bool(rev_raw)
            if not fy or month < 1 or month > 12:
                return json_response_keep_global_nonce({
                    'success': False,
                    'error': 'financial_year and month are required',
                }, 400)
            if not reason:
                return json_response_keep_global_nonce({
                    'success': False,
                    'error': 'Reason is mandatory to reopen a period.',
                }, 400)
            if not commit_form_save_nonce(submitted_nonce, session_key=GLOBAL_SAVE_NONCE_SESSION_KEY):
                return replay_blocked_response_global()
            result = reopen_period(
                fy,
                month,
                _user(),
                reason,
                _loc(),
                reverse_closing_journal=reverse_closing_journal,
            )
            if not result.get('success'):
                return json_response_rotate_global(result, 400)
            return json_response_rotate_global(result, 200)
        finally:
            _release_session_lock(_PERIOD_REOPEN_SESSION_LOCK_UNTIL)

    @bp.route('/accounts/api/period-closing/draft-sales', methods=['GET'])
    def api_period_closing_draft_sales():
        if not session.get('user'):
            return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
        rows = list_temp_bill_drafts(limit=500)
        return jsonify({'success': True, 'count': len(rows), 'rows': rows})

    @bp.route('/accounts/api/period-closing/draft-sales/delete', methods=['POST'])
    def api_period_closing_draft_sales_delete():
        """Delete TEMPBILLHDR/DTL draft sales (admin / closer only)."""
        if not session.get('user'):
            return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
        if not can_close_period(_user(), _role_id()):
            return jsonify({'success': False, 'error': 'Only administrators can delete draft sales.'}, 403)
        data = request.get_json(silent=True) or {}
        delete_all = bool(data.get('delete_all'))
        items = data.get('items') or []
        if not delete_all and not items:
            # single bill shortcut
            loc = data.get('locationcode')
            bno = data.get('billno')
            if loc is not None and bno is not None:
                items = [{'locationcode': loc, 'billno': bno}]
        result = delete_temp_bill_drafts(items=items, delete_all=delete_all)
        status = 200 if result.get('success') else 400
        return jsonify(result, status)

    @bp.route('/accounts/api/period-closing/history', methods=['GET'])
    def api_period_closing_history():
        if not session.get('user'):
            return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
        fy = (request.args.get('financial_year') or '').strip() or None
        return jsonify({'success': True, 'rows': list_closing_history(fy, _loc())})

    @bp.route('/accounts/api/period-closing/history/<int:log_id>', methods=['GET'])
    def api_period_closing_history_detail(log_id: int):
        if not session.get('user'):
            return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
        row = get_closing_log(log_id)
        if not row:
            return jsonify({'success': False, 'error': 'Not found'}, 404)
        return jsonify({'success': True, 'row': row})
