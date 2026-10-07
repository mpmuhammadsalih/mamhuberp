"""Online marketplace settlement routes (registered on accounts blueprint)."""
from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any, Dict, List, Optional

from nexa_http import Response, flash, jsonify, redirect, render_template, request, session, url_for

from save_nonce import (
    GLOBAL_SAVE_NONCE_SESSION_KEY,
    commit_form_save_nonce,
    extract_submitted_save_nonce,
    get_or_issue_global_save_nonce,
    issue_save_nonce,
    json_response_keep_global_nonce,
    json_response_rotate_global,
    reject_invalid_form_save_nonce,
    replay_blocked_response_global,
)

from addons.accounts.online_settlement_db import (
    STATUS_MATCHED,
    auto_match_batch,
    build_settlement_sample_csv,
    build_settlement_sample_xlsx,
    create_settlement_batch,
    ensure_online_settlement_tables,
    export_exception_rows,
    get_batch_header,
    get_marketplace_config,
    list_batch_lines,
    list_commission_report,
    list_exception_report,
    list_receipt_report,
    list_settlement_batches,
    parse_settlement_file,
    post_batch_lines,
    update_batch_line,
    upsert_marketplace_config,
    validate_batch,
)
from db import get_customer_open_invoices_for_payment

_ONLINE_SETTLEMENT_POST_SESSION_LOCK_UNTIL = '_online_settlement_post_session_lock_until'


def _os_try_acquire_post_lock(lock_seconds: float = 120.0) -> bool:
    now = datetime.now().timestamp()
    raw = session.get(_ONLINE_SETTLEMENT_POST_SESSION_LOCK_UNTIL)
    try:
        until = float(raw or 0)
    except (TypeError, ValueError):
        until = 0.0
    if until > now:
        return False
    session[_ONLINE_SETTLEMENT_POST_SESSION_LOCK_UNTIL] = now + float(lock_seconds)
    return True


def _os_release_post_lock() -> None:
    session.pop(_ONLINE_SETTLEMENT_POST_SESSION_LOCK_UNTIL, None)


def _loc_code() -> int:
    try:
        return int(session.get('location_code') or 1)
    except (TypeError, ValueError):
        return 1


def _user() -> str:
    return str(session.get('user') or 'web')


def _require_auth():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    from addons.accounts.controllers.routes import _apply_db

    if not _apply_db():
        return redirect(url_for('dashboard.index'))
    ensure_online_settlement_tables()
    return None


def _csv_response(rows: List[Dict[str, Any]], filename: str, fieldnames: List[str]) -> Response:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction='ignore')
    writer.writeheader()
    for row in rows or []:
        writer.writerow({k: row.get(k, '') for k in fieldnames})
    data = buf.getvalue()
    return Response(
        data,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )


def _page_form_defaults(hdr: Optional[Dict[str, Any]], saved_cfg: Optional[Dict[str, Any]]) -> Dict[str, str]:
    hdr = hdr or {}
    saved_cfg = saved_cfg or {}

    def pick(*keys: str) -> str:
        for key in keys:
            val = hdr.get(key)
            if val in (None, ''):
                val = saved_cfg.get(key)
            if val not in (None, ''):
                return str(val).strip()
        return ''

    try:
        from global_lookup import resolve_lookup_label
    except Exception:
        def resolve_lookup_label(_kind: str, code: str) -> str:
            return code or ''

    cc = pick('customer_code')
    bank = pick('bank_account')
    pm = pick('pm_commission_account')
    sc = pick('sales_commission_account')
    sp = pick('splus_account')
    oc = pick('other_charges_account')
    return {
        'customer_code': cc,
        'customer_label': resolve_lookup_label('customer', cc) if cc else '',
        'marketplace_name': pick('marketplace_name'),
        'bank_account': bank,
        'bank_label': resolve_lookup_label('cpv_petty', bank) if bank else '',
        'pm_commission_account': pm,
        'pm_label': resolve_lookup_label('gl_account', pm) if pm else '',
        'sales_commission_account': sc,
        'sc_label': resolve_lookup_label('gl_account', sc) if sc else '',
        'splus_account': sp,
        'sp_label': resolve_lookup_label('gl_account', sp) if sp else '',
        'other_charges_account': oc,
        'oc_label': resolve_lookup_label('gl_account', oc) if oc else '',
    }


def register(bp) -> None:
    """Attach online settlement routes to the accounts blueprint."""

    @bp.route('/accounts/online-settlement')
    def online_settlement_page():
        gate = _require_auth()
        if gate:
            return gate
        batch_no = (request.args.get('batch') or '').strip()
        batches = list_settlement_batches(limit=50)
        hdr = get_batch_header(batch_no) if batch_no else None
        lines = list_batch_lines(batch_no) if batch_no else []
        saved_cfg = None
        if hdr:
            saved_cfg = get_marketplace_config(str(hdr.get('customer_code') or ''))
        elif request.args.get('customer_code'):
            saved_cfg = get_marketplace_config(str(request.args.get('customer_code') or '').strip())
        form_defaults = _page_form_defaults(hdr, saved_cfg)
        issue_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY)
        closed_periods = []
        today = datetime.now().strftime('%Y-%m-%d')
        try:
            from addons.accounts.period_closing_db import list_closed_periods, resolve_open_voucher_date
            closed_periods = list_closed_periods(_loc_code())
            preferred = str((hdr or {}).get('settlement_date') or today)[:10]
            today = preferred if hdr else resolve_open_voucher_date(preferred, _loc_code())
        except Exception:
            closed_periods = []
        return render_template(
            'accounts/online_settlement.html',
            batch_no=batch_no,
            batch_header=hdr,
            batch_lines=lines,
            form_defaults=form_defaults,
            recent_batches=batches,
            location_code=_loc_code(),
            today=today,
            closed_periods=closed_periods,
            global_save_nonce=get_or_issue_global_save_nonce(),
        )

    @bp.route('/accounts/online-settlement/sample.csv', methods=['GET'])
    def online_settlement_sample_csv():
        if not session.get('user'):
            return Response('Not authenticated', status=401, mimetype='text/plain')
        sample = build_settlement_sample_csv()
        return Response(
            sample,
            mimetype='text/csv; charset=utf-8',
            headers={'Content-Disposition': 'attachment; filename="online_settlement_sample.csv"'},
        )

    @bp.route('/accounts/online-settlement/sample.xlsx', methods=['GET'])
    def online_settlement_sample_xlsx():
        if not session.get('user'):
            return Response('Not authenticated', status=401, mimetype='text/plain')
        xlsx_bytes = build_settlement_sample_xlsx()
        if xlsx_bytes is None:
            return Response(
                'Excel template requires openpyxl. Install with: pip install openpyxl',
                status=500,
                mimetype='text/plain',
            )
        return Response(
            xlsx_bytes,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={'Content-Disposition': 'attachment; filename="online_settlement_sample.xlsx"'},
        )

    @bp.route('/accounts/online-settlement/history')
    def online_settlement_history():
        gate = _require_auth()
        if gate:
            return gate
        batches = list_settlement_batches(limit=500)
        return render_template(
            'accounts/online_settlement_history.html',
            batches=batches,
        )

    @bp.route('/accounts/online-settlement/reports')
    def online_settlement_reports():
        gate = _require_auth()
        if gate:
            return gate
        batch_no = (request.args.get('batch') or '').strip()
        date_from = (request.args.get('date_from') or '')[:10]
        date_to = (request.args.get('date_to') or '')[:10]
        report = (request.args.get('report') or 'receipts').strip().lower()
        if report == 'commission':
            rows = list_commission_report(batch_no=batch_no, date_from=date_from, date_to=date_to)
        elif report == 'exceptions':
            rows = list_exception_report(batch_no=batch_no)
        else:
            rows = list_receipt_report(batch_no=batch_no, date_from=date_from, date_to=date_to)
        return render_template(
            'accounts/online_settlement_reports.html',
            report=report,
            rows=rows,
            batch_no=batch_no,
            date_from=date_from,
            date_to=date_to,
            batches=list_settlement_batches(limit=200),
        )

    @bp.route('/accounts/api/online-settlement/config', methods=['GET', 'POST'])
    def api_online_settlement_config():
        if not session.get('user'):
            return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
        ensure_online_settlement_tables()
        if request.method == 'GET':
            cc = (request.args.get('customer_code') or '').strip()
            cfg = get_marketplace_config(cc)
            if cfg:
                try:
                    from global_lookup import resolve_lookup_label
                    cfg = dict(cfg)
                    cfg['bank_label'] = resolve_lookup_label('cpv_petty', str(cfg.get('bank_account') or ''))
                    cfg['pm_label'] = resolve_lookup_label('gl_account', str(cfg.get('pm_commission_account') or ''))
                    cfg['sc_label'] = resolve_lookup_label('gl_account', str(cfg.get('sales_commission_account') or ''))
                    cfg['sp_label'] = resolve_lookup_label('gl_account', str(cfg.get('splus_account') or ''))
                    cfg['oc_label'] = resolve_lookup_label('gl_account', str(cfg.get('other_charges_account') or ''))
                except Exception:
                    pass
            return jsonify({'success': True, 'config': cfg})
        data = request.get_json(silent=True) or {}
        ok, msg = upsert_marketplace_config(data, _user())
        return jsonify({'success': ok, 'error': msg or None})

    @bp.route('/accounts/api/online-settlement/upload', methods=['POST'])
    def api_online_settlement_upload():
        if not session.get('user'):
            return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
        ensure_online_settlement_tables()
        f = request.files.get('file')
        if not f or not f.filename:
            return jsonify({'success': False, 'error': 'Settlement file is required.'}, 400)
        raw = f.read()
        rows, err = parse_settlement_file(raw, f.filename)
        if err:
            return jsonify({'success': False, 'error': err}, 400)
        customer_code = (request.form.get('customer_code') or '').strip()
        marketplace_name = (request.form.get('marketplace_name') or '').strip()
        settlement_date = (request.form.get('settlement_date') or '')[:10] or datetime.now().strftime('%Y-%m-%d')
        try:
            from addons.accounts.period_closing_db import is_period_closed_for_date
            _pc_msg = is_period_closed_for_date(settlement_date, _loc_code())
            if _pc_msg:
                return jsonify({'success': False, 'error': _pc_msg}, 400)
        except Exception:
            pass
        accounts = {
            'bank_account': (request.form.get('bank_account') or '').strip(),
            'pm_commission_account': (request.form.get('pm_commission_account') or '').strip(),
            'sales_commission_account': (request.form.get('sales_commission_account') or '').strip(),
            'splus_account': (request.form.get('splus_account') or '').strip(),
            'other_charges_account': (request.form.get('other_charges_account') or '').strip(),
        }
        if not customer_code:
            return jsonify({'success': False, 'error': 'Marketplace customer is required.'}, 400)
        if not accounts['bank_account']:
            return jsonify({'success': False, 'error': 'Bank / clearing account is required.'}, 400)
        ok, msg, batch_no = create_settlement_batch(
            location_code=_loc_code(),
            customer_code=customer_code,
            marketplace_name=marketplace_name,
            settlement_date=settlement_date,
            file_name=f.filename,
            uploaded_by=_user(),
            accounts=accounts,
            raw_rows=rows,
        )
        if not ok:
            return jsonify({'success': False, 'error': msg or 'Upload failed.'}, 400)
        upsert_marketplace_config(
            {
                'customer_code': customer_code,
                'marketplace_name': marketplace_name,
                **accounts,
            },
            _user(),
        )
        return jsonify({'success': True, 'batch_no': batch_no, 'row_count': len(rows)})

    @bp.route('/accounts/api/online-settlement/batch/<batch_no>')
    def api_online_settlement_batch(batch_no: str):
        if not session.get('user'):
            return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
        hdr = get_batch_header(batch_no)
        if not hdr:
            return jsonify({'success': False, 'error': 'Batch not found.'}, 404)
        lines = list_batch_lines(batch_no)
        return jsonify({'success': True, 'header': hdr, 'lines': lines})

    @bp.route('/accounts/api/online-settlement/validate', methods=['POST'])
    def api_online_settlement_validate():
        if not session.get('user'):
            return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
        data = request.get_json(silent=True) or {}
        batch_no = str(data.get('batch_no') or '').strip()
        if not batch_no:
            return jsonify({'success': False, 'error': 'Batch number is required.'}, 400)
        ok, msg = validate_batch(batch_no)
        if not ok:
            return jsonify({'success': False, 'error': msg}, 400)
        return jsonify({'success': True, 'lines': list_batch_lines(batch_no)})

    @bp.route('/accounts/api/online-settlement/auto-match', methods=['POST'])
    def api_online_settlement_auto_match():
        if not session.get('user'):
            return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
        data = request.get_json(silent=True) or {}
        batch_no = str(data.get('batch_no') or '').strip()
        if not batch_no:
            return jsonify({'success': False, 'error': 'Batch number is required.'}, 400)
        ok, msg = auto_match_batch(batch_no)
        if not ok:
            return jsonify({'success': False, 'error': msg}, 400)
        lines = list_batch_lines(batch_no)
        matched = sum(1 for ln in lines if str(ln.get('status') or '') == STATUS_MATCHED)
        return jsonify({'success': True, 'matched': matched, 'lines': lines})

    @bp.route('/accounts/api/online-settlement/post', methods=['POST'])
    def api_online_settlement_post():
        if not session.get('user'):
            return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
        if not _os_try_acquire_post_lock():
            return json_response_rotate_global(
                {
                    'success': False,
                    'error': 'An online settlement post is already in progress for this session. Please wait.',
                    'save_session_locked': True,
                },
                423,
            )
        try:
            submitted_nonce = extract_submitted_save_nonce(request)
            if not reject_invalid_form_save_nonce(submitted_nonce):
                return replay_blocked_response_global()
            data = request.get_json(silent=True) or {}
            batch_no = str(data.get('batch_no') or '').strip()
            if not batch_no:
                return json_response_keep_global_nonce(
                    {'success': False, 'error': 'Batch number is required.'},
                    400,
                )
            line_ids = [int(x) for x in (data.get('line_ids') or []) if str(x).strip().isdigit()]
            post_all = bool(data.get('post_all_matched'))
            if not commit_form_save_nonce(submitted_nonce):
                return replay_blocked_response_global()
            ok, msg, result = post_batch_lines(
                batch_no,
                line_ids=line_ids or None,
                post_all_matched=post_all,
                posted_by=_user(),
            )
            if not ok:
                return json_response_rotate_global({'success': False, 'error': msg}, 400)
            return json_response_rotate_global(
                {
                    'success': True,
                    **result,
                    'lines': list_batch_lines(batch_no),
                    'batch_no': batch_no,
                },
            )
        finally:
            _os_release_post_lock()

    @bp.route('/accounts/api/online-settlement/line/<int:line_id>', methods=['PATCH', 'POST'])
    def api_online_settlement_line(line_id: int):
        if not session.get('user'):
            return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
        data = request.get_json(silent=True) or {}
        manual = data.get('manual_invoice_voucher')
        excluded = data.get('excluded')
        ex_val: Optional[bool] = None
        if excluded is not None:
            ex_val = str(excluded).lower() in ('1', 'true', 'y', 'yes')
        ok, msg = update_batch_line(
            line_id,
            manual_invoice_voucher=str(manual or '') if manual is not None else '',
            excluded=ex_val,
        )
        if not ok:
            return jsonify({'success': False, 'error': msg}, 400)
        return jsonify({'success': True})

    @bp.route('/accounts/api/online-settlement/open-invoices')
    def api_online_settlement_open_invoices():
        if not session.get('user'):
            return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
        cc = (request.args.get('customer_code') or '').strip()
        if not cc:
            return jsonify({'success': False, 'error': 'Customer code required.'}, 400)
        rows = get_customer_open_invoices_for_payment(cc) or []
        return jsonify({'success': True, 'rows': rows})

    @bp.route('/accounts/api/online-settlement/export-exceptions')
    def api_online_settlement_export_exceptions():
        if not session.get('user'):
            return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
        batch_no = (request.args.get('batch_no') or '').strip()
        if not batch_no:
            return jsonify({'success': False, 'error': 'Batch number is required.'}, 400)
        rows = export_exception_rows(batch_no)
        fields = [
            'line_no', 'order_id', 'upload_invoice_amount', 'total_amount',
            'pm_commission', 'sales_commission', 'splus_amount', 'other_charges',
            'erp_invoice_no', 'erp_invoice_date', 'erp_invoice_amount',
            'difference', 'status', 'status_message',
        ]
        return _csv_response(rows, f'online_settlement_exceptions_{batch_no}.csv', fields)

    @bp.route('/accounts/api/online-settlement/export-report')
    def api_online_settlement_export_report():
        if not session.get('user'):
            return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
        report = (request.args.get('report') or 'receipts').strip().lower()
        batch_no = (request.args.get('batch_no') or '').strip()
        date_from = (request.args.get('date_from') or '')[:10]
        date_to = (request.args.get('date_to') or '')[:10]
        if report == 'commission':
            rows = list_commission_report(batch_no=batch_no, date_from=date_from, date_to=date_to)
            fields = [
                'batch_no', 'marketplace_name', 'customer_code', 'settlement_date',
                'order_id', 'pm_commission', 'sales_commission', 'splus_amount', 'other_charges',
                'total_expenses', 'gl_voucher_no',
            ]
            fname = 'online_settlement_commission.csv'
        elif report == 'exceptions':
            rows = list_exception_report(batch_no=batch_no)
            fields = [
                'batch_no', 'marketplace_name', 'upload_date', 'uploaded_by',
                'line_no', 'order_id', 'upload_invoice_amount', 'status', 'status_message',
            ]
            fname = 'online_settlement_exceptions.csv'
        else:
            rows = list_receipt_report(batch_no=batch_no, date_from=date_from, date_to=date_to)
            fields = [
                'batch_no', 'marketplace_name', 'settlement_date', 'order_id',
                'invoice_no', 'invoice_date', 'invoice_amount', 'amount_received',
                'receipt_no', 'posted_date',
            ]
            fname = 'online_settlement_receipts.csv'
        return _csv_response(rows, fname, fields)
