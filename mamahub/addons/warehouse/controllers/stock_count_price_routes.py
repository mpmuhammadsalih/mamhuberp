"""Stock count price update — bulk apply to ITEMMASTER / ITEMALTERNATEUOMMAP."""
from __future__ import annotations

from typing import Any, Dict, List

from nexa_http import abort, jsonify, redirect, render_template, request, session, url_for

from addons.warehouse.stock_count_price_db import (
    PRICE_BATCH_STATUSES,
    apply_price_batch_lines,
    create_price_batch,
    delete_price_batch,
    ensure_stock_count_price_tables,
    get_price_batch_header,
    get_price_batch_lines,
    import_lines_from_stock_count,
    list_price_batches,
    upsert_price_batch_lines,
)


def register(bp) -> None:
    """Register price-update routes on the warehouse blueprint."""

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

    def _allowed() -> bool:
        u = _user().strip().lower()
        if u in ('admin', 'super'):
            return True
        try:
            from db import get_user_role_id
            from permissions import get_role_permissions

            rid = get_user_role_id(_user())
            perms = list(get_role_permissions(rid) or []) if rid else []
            return 'warehouse.warehouse_stock_count_price' in perms
        except Exception:
            return False

    @bp.route('/warehouse/stock-count-price')
    def warehouse_stock_count_price_list():
        if not session.get('user'):
            return redirect(url_for('auth.login'))
        if not _allowed():
            abort(403)
        ensure_stock_count_price_tables()
        loc = _loc()
        status_filter = (request.args.get('status') or '').strip().upper()
        rows = list_price_batches(loc, status=status_filter or None)
        return render_template(
            'warehouse/stock_count_price_list.html',
            rows=rows,
            statuses=PRICE_BATCH_STATUSES,
            status_filter=status_filter,
            location_code=loc,
        )

    @bp.route('/warehouse/stock-count-price/new', methods=['GET', 'POST'])
    def warehouse_stock_count_price_new():
        if not session.get('user'):
            return redirect(url_for('auth.login'))
        if not _allowed():
            abort(403)
        ensure_stock_count_price_tables()
        loc = _loc()
        if request.method == 'POST':
            remarks = (request.form.get('remarks') or '').strip()
            scn_raw = (request.form.get('source_count_no') or '').strip()
            source_count_no = None
            if scn_raw.isdigit():
                source_count_no = int(scn_raw)
            ok, err, bn = create_price_batch(
                loc, remarks=remarks, source_count_no=source_count_no, created_by=_user(),
            )
            if not ok or bn is None:
                return render_template(
                    'warehouse/stock_count_price_new.html',
                    error=err or 'Could not create batch.',
                    location_code=loc,
                )
            if source_count_no:
                import_lines_from_stock_count(loc, bn, source_count_no)
            return redirect(url_for('warehouse.warehouse_stock_count_price_detail', batch_no=bn))
        return render_template('warehouse/stock_count_price_new.html', location_code=loc)

    @bp.route('/warehouse/stock-count-price/<int:batch_no>')
    def warehouse_stock_count_price_detail(batch_no: int):
        if not session.get('user'):
            return redirect(url_for('auth.login'))
        if not _allowed():
            abort(403)
        ensure_stock_count_price_tables()
        loc = _loc()
        hdr = get_price_batch_header(loc, batch_no)
        if not hdr:
            return redirect(url_for('warehouse.warehouse_stock_count_price_list'))
        lines = get_price_batch_lines(loc, batch_no)
        return render_template(
            'warehouse/stock_count_price_detail.html',
            hdr=hdr,
            lines=lines,
            batch_no=batch_no,
            location_code=loc,
        )

    @bp.route('/warehouse/stock-count-price/api/batches')
    def api_stock_count_price_batches():
        if not session.get('user'):
            return jsonify({'ok': False, 'error': 'Unauthorized'}), 401
        if not _allowed():
            return jsonify({'ok': False, 'error': 'Forbidden'}), 403
        ensure_stock_count_price_tables()
        st = (request.args.get('status') or '').strip().upper() or None
        rows = list_price_batches(_loc(), status=st)
        return jsonify({'ok': True, 'rows': rows})

    @bp.route('/warehouse/stock-count-price/api/batch/<int:batch_no>')
    def api_stock_count_price_get(batch_no: int):
        if not session.get('user'):
            return jsonify({'ok': False, 'error': 'Unauthorized'}), 401
        if not _allowed():
            return jsonify({'ok': False, 'error': 'Forbidden'}), 403
        loc = _loc()
        hdr = get_price_batch_header(loc, batch_no)
        if not hdr:
            return jsonify({'ok': False, 'error': 'Not found'}), 404
        lines = get_price_batch_lines(loc, batch_no)
        return jsonify({'ok': True, 'header': hdr, 'lines': lines})

    @bp.route('/warehouse/stock-count-price/api/lines', methods=['POST'])
    def api_stock_count_price_lines():
        if not session.get('user'):
            return jsonify({'ok': False, 'error': 'Unauthorized'}), 401
        if not _allowed():
            return jsonify({'ok': False, 'error': 'Forbidden'}), 403
        data = request.get_json(silent=True) or {}
        try:
            batch_no = int(data.get('batch_no') or 0)
        except (TypeError, ValueError):
            return jsonify({'ok': False, 'error': 'Invalid batch_no'}), 400
        lines_in = data.get('lines') or []
        if not isinstance(lines_in, list):
            return jsonify({'ok': False, 'error': 'lines must be an array'}), 400
        ok, err, n = upsert_price_batch_lines(_loc(), batch_no, lines_in)
        if not ok:
            return jsonify({'ok': False, 'error': err or 'Save failed'}), 400
        return jsonify({'ok': True, 'lines_written': n, 'lines': get_price_batch_lines(_loc(), batch_no)})

    @bp.route('/warehouse/stock-count-price/api/apply', methods=['POST'])
    def api_stock_count_price_apply():
        if not session.get('user'):
            return jsonify({'ok': False, 'error': 'Unauthorized'}), 401
        if not _allowed():
            return jsonify({'ok': False, 'error': 'Forbidden'}), 403
        data = request.get_json(silent=True) or {}
        try:
            batch_no = int(data.get('batch_no') or 0)
        except (TypeError, ValueError):
            return jsonify({'ok': False, 'error': 'Invalid batch_no'}), 400
        line_nos: List[int] = []
        for x in data.get('line_nos') or []:
            try:
                line_nos.append(int(x))
            except (TypeError, ValueError):
                pass
        apply_all = bool(data.get('apply_all_pending'))
        update_all_alts = bool(data.get('update_all_alternates'))
        ok, msg, stats = apply_price_batch_lines(
            _loc(),
            batch_no,
            line_nos=line_nos if line_nos else None,
            apply_all_pending=apply_all,
            update_all_alternates=update_all_alts,
            applied_by=_user(),
        )
        if not ok:
            return jsonify({'ok': False, 'error': msg, 'stats': stats}), 400
        hdr = get_price_batch_header(_loc(), batch_no)
        return jsonify({
            'ok': True,
            'message': msg,
            'stats': stats,
            'header': hdr,
            'lines': get_price_batch_lines(_loc(), batch_no),
        })

    @bp.route('/warehouse/stock-count-price/api/delete', methods=['POST'])
    def api_stock_count_price_delete():
        if not session.get('user'):
            return jsonify({'ok': False, 'error': 'Unauthorized'}), 401
        if not _allowed():
            return jsonify({'ok': False, 'error': 'Forbidden'}), 403
        data = request.get_json(silent=True) or {}
        try:
            batch_no = int(data.get('batch_no') or 0)
        except (TypeError, ValueError):
            return jsonify({'ok': False, 'error': 'Invalid batch_no'}), 400
        ok, err = delete_price_batch(_loc(), batch_no)
        if not ok:
            return jsonify({'ok': False, 'error': err}), 400
        return jsonify({'ok': True})
