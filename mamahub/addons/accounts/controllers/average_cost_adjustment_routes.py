"""Average Cost Adjustment — routes on accounts blueprint."""
from __future__ import annotations

import json
from datetime import date
from typing import Any, Dict, List

from nexa_http import jsonify, redirect, render_template, request, session, url_for

from addons.accounts.average_cost_adjustment_db import (
    REASONS,
    ensure_average_cost_adjustment_tables,
    format_journal_name,
    get_item_line_context,
    get_journal_payload,
    list_journals,
    list_negative_stock_candidates,
    list_warehouse_options,
    next_journal_no,
    save_journal,
    search_items,
)


def register(bp) -> None:
    """Register Average Cost Adjustment routes."""

    def _loc() -> int:
        try:
            return int(session.get('location_code') or 1)
        except (TypeError, ValueError):
            return 1

    def _user() -> str:
        u = session.get('user')
        if isinstance(u, dict):
            return str(u.get('username') or u.get('name') or '')
        return str(u or '')

    def _apply_db() -> bool:
        try:
            from addons.accounts.controllers.routes import _apply_db as _adb
            return bool(_adb())
        except Exception:
            return True

    def _render_form(journal_no, *, query_mode: bool):
        ensure_average_cost_adjustment_tables()
        payload = None
        if journal_no is not None:
            payload = get_journal_payload(_loc(), int(journal_no))
            if not payload:
                return redirect(url_for('accounts.average_cost_adjustment_list'))
        else:
            jno = next_journal_no(_loc())
            payload = {
                'header': {
                    'journalno': jno,
                    'journalname': format_journal_name(jno),
                    'journal_date': date.today().isoformat(),
                    'posting_date': date.today().isoformat(),
                    'status': 'DRAFT',
                    'posted': 'N',
                },
                'lines': [],
            }
        warehouses = list_warehouse_options(_loc())
        return render_template(
            'accounts/average_cost_adjustment_form.html',
            payload=payload,
            payload_json=json.dumps(payload, default=str),
            warehouses=warehouses,
            reasons=REASONS,
            query_mode=query_mode,
            today=date.today().isoformat(),
        )

    @bp.route('/accounts/average-cost-adjustment')
    def average_cost_adjustment():
        if not session.get('user'):
            return redirect(url_for('auth.login'))
        return redirect(url_for('accounts.average_cost_adjustment_list'))

    @bp.route('/accounts/average-cost-adjustment/list')
    def average_cost_adjustment_list():
        if not session.get('user'):
            return redirect(url_for('auth.login'))
        if not _apply_db():
            return redirect(url_for('dashboard.dashboard'))
        ensure_average_cost_adjustment_tables()
        search = (request.args.get('search') or '').strip()
        status_filter = (request.args.get('status') or '').strip().upper()
        rows = list_journals(_loc(), search=search, status=status_filter)
        total_delta = sum(float(r.get('total_delta') or 0) for r in rows)
        return render_template(
            'accounts/average_cost_adjustment_list.html',
            rows=rows,
            search=search,
            status_filter=status_filter,
            total_delta=total_delta,
        )

    @bp.route('/accounts/average-cost-adjustment/new')
    def average_cost_adjustment_form():
        if not session.get('user'):
            return redirect(url_for('auth.login'))
        if not _apply_db():
            return redirect(url_for('dashboard.dashboard'))
        return _render_form(None, query_mode=False)

    @bp.route('/accounts/average-cost-adjustment/view/<int:journal_no>')
    def average_cost_adjustment_view(journal_no):
        if not session.get('user'):
            return redirect(url_for('auth.login'))
        if not _apply_db():
            return redirect(url_for('dashboard.dashboard'))
        return _render_form(journal_no, query_mode=True)

    @bp.route('/accounts/average-cost-adjustment/edit/<int:journal_no>')
    def average_cost_adjustment_edit(journal_no):
        if not session.get('user'):
            return redirect(url_for('auth.login'))
        if not _apply_db():
            return redirect(url_for('dashboard.dashboard'))
        payload = get_journal_payload(_loc(), int(journal_no))
        if payload and str(payload['header'].get('posted') or 'N').upper() == 'Y':
            return redirect(url_for('accounts.average_cost_adjustment_view', journal_no=journal_no))
        return _render_form(journal_no, query_mode=False)

    @bp.route('/accounts/average-cost-adjustment/api/items')
    def average_cost_adjustment_api_items():
        if not session.get('user'):
            return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
        _apply_db()
        search = (request.args.get('search') or '').strip()
        wh = (request.args.get('warehouse_code') or '').strip()
        try:
            limit = min(max(int(request.args.get('limit') or 50), 10), 200)
        except (TypeError, ValueError):
            limit = 50
        items = search_items(_loc(), search=search, warehouse_code=wh, limit=limit)
        return jsonify({'success': True, 'items': items})

    @bp.route('/accounts/average-cost-adjustment/api/item-context')
    def average_cost_adjustment_api_item_context():
        if not session.get('user'):
            return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
        _apply_db()
        item_code = (request.args.get('item_code') or '').strip()
        wh = (request.args.get('warehouse_code') or '').strip()
        if not item_code.isdigit():
            return jsonify({'success': False, 'error': 'Invalid item code'}, 400)
        payload = get_item_line_context(_loc(), int(item_code), wh)
        return jsonify(payload)

    @bp.route('/accounts/average-cost-adjustment/api/negative-stock')
    def average_cost_adjustment_api_negative_stock():
        if not session.get('user'):
            return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
        _apply_db()
        wh = (request.args.get('warehouse_code') or '').strip()
        try:
            limit = min(max(int(request.args.get('limit') or 100), 10), 300)
        except (TypeError, ValueError):
            limit = 100
        items = list_negative_stock_candidates(_loc(), warehouse_code=wh, limit=limit)
        return jsonify({'success': True, 'items': items})

    @bp.route('/accounts/average-cost-adjustment/api/save', methods=['POST'])
    def average_cost_adjustment_api_save():
        if not session.get('user'):
            return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
        _apply_db()
        data = request.get_json(silent=True) or {}
        try:
            jno_raw = data.get('journal_no')
            journal_no = int(jno_raw) if jno_raw not in (None, '', 0) else None
        except (TypeError, ValueError):
            journal_no = None
        header = data.get('header') or {}
        lines = data.get('lines') or []
        post = bool(data.get('post'))
        ok, msg, saved_no = save_journal(
            _loc(),
            journal_no=journal_no,
            user=_user(),
            header=header,
            lines=lines,
            post=post,
        )
        if not ok:
            return jsonify({'success': False, 'error': msg}, 400)
        return jsonify({
            'success': True,
            'message': msg,
            'journal_no': saved_no,
            'view_url': url_for('accounts.average_cost_adjustment_view', journal_no=saved_no),
        })
