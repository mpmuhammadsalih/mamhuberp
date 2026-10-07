"""Inventory value adjustment — routes on purchase blueprint."""
from __future__ import annotations

import json
from datetime import date
from typing import Any, Dict, List

from nexa_http import abort, flash, jsonify, redirect, render_template, request, session, url_for

from addons.purchase.inventory_value_adjustment_db import (
    ADJ_DIRS,
    ADJ_REASONS,
    ADJ_TYPES,
    INV_MODELS,
    ensure_inventory_value_adjustment_tables,
    format_journal_name,
    get_item_line_context,
    get_journal_payload,
    list_journals,
    list_warehouse_options,
    next_journal_no,
    save_journal,
)


def register(bp) -> None:
    """Register inventory value adjustment routes."""

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

    def _apply_db() -> None:
        pass

    @bp.route('/purchase/inventory-value-adjustment')
    def inventory_value_adjustment():
        if not session.get('user'):
            return redirect(url_for('auth.login'))
        return redirect(url_for('purchase.inventory_value_adjustment_list'))

    @bp.route('/purchase/inventory-value-adjustment/list')
    def inventory_value_adjustment_list():
        if not session.get('user'):
            return redirect(url_for('auth.login'))
        _apply_db()
        ensure_inventory_value_adjustment_tables()
        search = (request.args.get('search') or '').strip()
        status = (request.args.get('status') or '').strip().upper()
        rows = list_journals(_loc(), search=search, status=status or '')
        total_adj = round(sum(float(r.get('total_adjustment') or 0) for r in rows), 2)
        return render_template(
            'purchase/inventory_value_adjustment_list.html',
            rows=rows,
            search=search,
            status_filter=status,
            total_adjustment=total_adj,
        )

    def _render_form(journal_no=None, *, query_mode: bool = False):
        _apply_db()
        ensure_inventory_value_adjustment_tables()
        loc = _loc()
        initial_data = None
        is_existing = journal_no is not None
        if is_existing:
            initial_data = get_journal_payload(loc, int(journal_no))
            if not initial_data:
                flash('Journal not found.', 'error')
                return redirect(url_for('purchase.inventory_value_adjustment_list'))
        next_no = int(journal_no) if is_existing else next_journal_no(loc)
        today = date.today().isoformat()
        warehouses = list_warehouse_options(loc)
        return render_template(
            'purchase/inventory_value_adjustment_form.html',
            next_journal_no=next_no,
            journal_name=format_journal_name(next_no),
            default_date=today,
            location_code=loc,
            query_mode=query_mode,
            is_existing=is_existing,
            initial_data=initial_data,
            warehouses=warehouses,
            adj_types=ADJ_TYPES,
            inv_models=INV_MODELS,
            adj_dirs=ADJ_DIRS,
            adj_reasons=ADJ_REASONS,
            api_items_url=url_for('purchase.inventory_value_adjustment_api_items'),
            api_item_context_url=url_for('purchase.inventory_value_adjustment_api_item_context'),
            api_save_url=url_for('purchase.inventory_value_adjustment_api_save'),
            list_url=url_for('purchase.inventory_value_adjustment_list'),
        )

    @bp.route('/purchase/inventory-value-adjustment/new')
    def inventory_value_adjustment_form():
        if not session.get('user'):
            return redirect(url_for('auth.login'))
        return _render_form(None, query_mode=False)

    @bp.route('/purchase/inventory-value-adjustment/view/<int:journal_no>')
    def inventory_value_adjustment_view(journal_no):
        if not session.get('user'):
            return redirect(url_for('auth.login'))
        return _render_form(journal_no, query_mode=True)

    @bp.route('/purchase/inventory-value-adjustment/api/items')
    def inventory_value_adjustment_api_items():
        if not session.get('user'):
            return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
        _apply_db()
        from addons.purchase.controllers.routes import (
            _get_items_for_location_filtered,
            _resolve_location_code,
            get_storeinventory_stock_summary_for_items,
        )
        search = (request.args.get('search') or '').strip()
        try:
            limit = min(max(int(request.args.get('limit') or 300), 50), 500)
        except (TypeError, ValueError):
            limit = 300
        rows = _get_items_for_location_filtered(search=search or None, limit=limit, supplier_code=None)
        loc = _resolve_location_code()
        codes: List[int] = []
        for r in rows or []:
            try:
                codes.append(int(float(str(r.get('code')).strip())))
            except (TypeError, ValueError):
                pass
        summary = get_storeinventory_stock_summary_for_items(loc, codes)
        items_out: List[Dict[str, Any]] = []
        for r in rows or []:
            try:
                ic = int(float(str(r.get('code')).strip()))
            except (TypeError, ValueError):
                ic = 0
            srow = summary.get(ic) if ic else None
            tot = float(srow.get('total') or 0) if srow else 0.0
            items_out.append({
                'code': r.get('code'),
                'name': r.get('name'),
                'uom': r.get('uom'),
                'cost': r.get('cost'),
                'averagecost': r.get('averagecost') or r.get('cost'),
                'stock': tot,
            })
        return jsonify({'success': True, 'items': items_out})

    @bp.route('/purchase/inventory-value-adjustment/api/item-context')
    def inventory_value_adjustment_api_item_context():
        if not session.get('user'):
            return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
        _apply_db()
        item_code = (request.args.get('item_code') or '').strip()
        wh = (request.args.get('warehouse_code') or '').strip()
        if not item_code.isdigit():
            return jsonify({'success': False, 'error': 'Invalid item code'}, 400)
        payload = get_item_line_context(_loc(), int(item_code), wh)
        return jsonify(payload)

    @bp.route('/purchase/inventory-value-adjustment/api/save', methods=['POST'])
    def inventory_value_adjustment_api_save():
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
            'view_url': url_for('purchase.inventory_value_adjustment_view', journal_no=saved_no),
        })
