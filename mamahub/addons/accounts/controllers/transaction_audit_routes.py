"""Transaction accounts audit routes (registered on accounts blueprint)."""
from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any, Dict

from nexa_http import Response, jsonify, redirect, render_template, request, session, url_for

from addons.accounts.transaction_audit import (
    flatten_transaction_audit_export,
    get_transaction_audit_detail,
    list_transaction_audit_vouchers,
)
from db import ensure_gl_tables


def _loc_code() -> int:
    try:
        return int(session.get('location_code') or 1)
    except (TypeError, ValueError):
        return 1


def register(bp: Any) -> None:
    @bp.route('/accounts/transaction-audit')
    def transaction_audit():
        if not session.get('user'):
            return redirect(url_for('auth.login'))
        from addons.accounts.controllers.routes import _apply_db
        if not _apply_db():
            return redirect(url_for('dashboard.dashboard'))
        ensure_gl_tables()
        return render_template(
            'accounts/transaction_audit.html',
            session_location_code=_loc_code(),
        )

    @bp.route('/accounts/api/transaction-audit/vouchers')
    def api_transaction_audit_vouchers():
        if not session.get('user'):
            return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
        from addons.accounts.controllers.routes import _apply_db
        if not _apply_db():
            return jsonify({'success': False, 'error': 'Database unavailable'}, 503)
        ensure_gl_tables()
        date_from = (request.args.get('date_from') or '').strip()[:10] or None
        date_to = (request.args.get('date_to') or '').strip()[:10] or None
        source = (request.args.get('source') or 'ALL').strip()
        search = (request.args.get('search') or '').strip() or None
        unbalanced = (request.args.get('unbalanced') or '') in ('1', 'true', 'yes')
        try:
            limit = max(20, min(int(request.args.get('limit') or 200), 500))
        except (TypeError, ValueError):
            limit = 200
        try:
            payload = list_transaction_audit_vouchers(
                date_from=date_from,
                date_to=date_to,
                source=source,
                search=search,
                unbalanced_only=unbalanced,
                limit=limit,
            )
            payload['success'] = True
            return jsonify(payload)
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}, 500)

    @bp.route('/accounts/api/transaction-audit/detail')
    def api_transaction_audit_detail():
        if not session.get('user'):
            return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
        from addons.accounts.controllers.routes import _apply_db
        if not _apply_db():
            return jsonify({'success': False, 'error': 'Database unavailable'}, 503)
        ensure_gl_tables()
        vno = (request.args.get('voucher_no') or request.args.get('vno') or '').strip()
        if not vno:
            return jsonify({'success': False, 'error': 'voucher_no required'}, 400)
        try:
            detail = get_transaction_audit_detail(vno, _loc_code())
            return jsonify(detail)
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}, 500)

    @bp.route('/accounts/transaction-audit/export.csv')
    def transaction_audit_export_csv():
        if not session.get('user'):
            return redirect(url_for('auth.login'))
        from addons.accounts.controllers.routes import _apply_db
        if not _apply_db():
            return redirect(url_for('dashboard.dashboard'))
        ensure_gl_tables()
        date_from = (request.args.get('date_from') or '').strip()[:10] or None
        date_to = (request.args.get('date_to') or '').strip()[:10] or None
        source = (request.args.get('source') or 'ALL').strip()
        search = (request.args.get('search') or '').strip() or None
        unbalanced = (request.args.get('unbalanced') or '') in ('1', 'true', 'yes')
        payload = list_transaction_audit_vouchers(
            date_from=date_from,
            date_to=date_to,
            source=source,
            search=search,
            unbalanced_only=unbalanced,
            limit=500,
        )
        fields = (
            'voucher_no', 'voucher_date', 'source', 'source_label', 'reference_no',
            'narration', 'doc_type', 'doc_no', 'total_debit', 'total_credit',
            'balance_diff', 'status', 'created_by',
        )
        rows = flatten_transaction_audit_export(payload.get('rows') or [])
        buf = io.StringIO()
        wrt = csv.DictWriter(buf, fieldnames=list(fields))
        wrt.writeheader()
        for r in rows:
            wrt.writerow({k: r.get(k, '') for k in fields})
        fname = 'transaction-audit-%s.csv' % datetime.now().strftime('%Y%m%d-%H%M%S')
        return Response(
            buf.getvalue().encode('utf-8-sig'),
            headers={'Content-Disposition': 'attachment; filename="%s"' % fname},
            media_type='text/csv; charset=utf-8',
        )
