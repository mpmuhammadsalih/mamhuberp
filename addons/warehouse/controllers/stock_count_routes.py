"""Stock counting — web UI and PDT upload API."""
from __future__ import annotations

import csv
import io
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from nexa_http import abort, flash, jsonify, redirect, render_template, request, Response, send_file, session, url_for

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

from addons.warehouse.stock_count_db import (
    STOCK_COUNT_STATUSES,
    create_stock_count,
    delete_stock_count,
    ensure_stock_count_tables,
    get_stock_count_header,
    get_stock_count_lines,
    list_stock_count_journal,
    list_stock_counts,
    post_stock_count_to_inventory,
    set_stock_count_status,
    update_stock_count_line,
    delete_stock_count_line,
    upsert_stock_count_lines,
)
from db import get_stk_adj_opening_stock_mode_enabled, get_warehouse_location_sites, get_warehouse_master_by_id


def _line_variance_amount(ln: Dict[str, Any]) -> float:
    try:
        v = float(ln.get('variance_qty') or 0)
        avg = float(ln.get('average_cost') or 0)
        return round(v * avg, 2)
    except (TypeError, ValueError):
        return 0.0


def _count_line_stats(lines: List[Dict[str, Any]]) -> Dict[str, Any]:
    variance_count = 0
    total_counted = 0.0
    total_system = 0.0
    total_stock_value = 0.0
    total_system_value = 0.0
    total_variance_amount = 0.0
    total_variance_qty = 0.0
    line_count = len(lines or [])
    for ln in lines or []:
        try:
            v = float(ln.get('variance_qty') or 0)
        except (TypeError, ValueError):
            v = 0.0
        total_variance_qty += v
        try:
            avg_cost = float(ln.get('average_cost') or 0)
        except (TypeError, ValueError):
            avg_cost = 0.0
        if abs(v) > 0.0005:
            variance_count += 1
        total_variance_amount += v * avg_cost
        try:
            counted = float(ln.get('counted_qty') or 0)
        except (TypeError, ValueError):
            counted = 0.0
        try:
            system = float(ln.get('system_qty') or 0)
        except (TypeError, ValueError):
            system = 0.0
        total_counted += counted
        total_system += system
        total_stock_value += round(counted * avg_cost, 2)
        total_system_value += round(system * avg_cost, 2)
    return {
        'line_count': line_count,
        'variance_count': variance_count,
        'total_counted': round(total_counted, 3),
        'total_system': round(total_system, 3),
        'total_stock_value': round(total_stock_value, 2),
        'total_system_value': round(total_system_value, 2),
        'total_variance_amount': round(total_variance_amount, 2),
        'total_variance_qty': round(total_variance_qty, 3),
    }


def _journal_rows_json_safe(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalize journal rows for ``|tojson`` in templates (datetime/Decimal safe)."""
    out: List[Dict[str, Any]] = []
    for row in rows or []:
        item: Dict[str, Any] = {}
        for key, val in dict(row).items():
            if isinstance(val, datetime):
                item[key] = val.strftime('%Y-%m-%d %H:%M')
            elif isinstance(val, date):
                item[key] = val.strftime('%Y-%m-%d')
            elif isinstance(val, Decimal):
                item[key] = float(val)
            elif val is not None and hasattr(val, 'isoformat') and not isinstance(val, (str, int, float, bool)):
                try:
                    item[key] = val.isoformat()
                except Exception:
                    item[key] = str(val)
            else:
                item[key] = val
        out.append(item)
    return out


def _line_has_variance(ln: Dict[str, Any]) -> bool:
    try:
        v = float(ln.get('variance_qty') or 0)
    except (TypeError, ValueError):
        v = 0.0
    return abs(v) > 0.0005


def _line_search_blob(ln: Dict[str, Any]) -> str:
    parts = [
        ln.get('itemcode'),
        ln.get('item_name'),
        ln.get('barcode'),
        ln.get('main_category_name'),
        ln.get('category_name'),
        ln.get('micro_category_name'),
        ln.get('counted_by'),
        ln.get('warehouse_code'),
        ln.get('warehouse_name'),
    ]
    wh_id = ln.get('warehouse_id')
    if wh_id:
        parts.append(f'WH {wh_id}')
    return ' '.join(str(p).strip() for p in parts if p is not None and str(p).strip()).lower()


def _stock_count_line_filters_from_request(args) -> Dict[str, str]:
    return {
        'q': (args.get('q') or '').strip(),
        'variance': (args.get('variance') or '').strip().lower(),
        'main_category': (args.get('main_category') or '').strip(),
        'category': (args.get('category') or '').strip(),
        'micro_category': (args.get('micro_category') or '').strip(),
    }


def _filter_stock_count_lines(lines: List[Dict[str, Any]], filters: Dict[str, str]) -> List[Dict[str, Any]]:
    q = (filters.get('q') or '').strip().lower()
    variance = (filters.get('variance') or '').strip().lower()
    main_cat = (filters.get('main_category') or '').strip()
    category = (filters.get('category') or '').strip()
    micro_cat = (filters.get('micro_category') or '').strip()
    out: List[Dict[str, Any]] = []
    for ln in lines or []:
        if variance == 'variance' and not _line_has_variance(ln):
            continue
        if variance == 'match' and _line_has_variance(ln):
            continue
        if main_cat and str(ln.get('main_category_name') or '').strip() != main_cat:
            continue
        if category and str(ln.get('category_name') or '').strip() != category:
            continue
        if micro_cat and str(ln.get('micro_category_name') or '').strip() != micro_cat:
            continue
        if q and q not in _line_search_blob(ln):
            continue
        out.append(ln)
    return out


def _stock_count_line_filter_options(lines: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    main: set[str] = set()
    cat: set[str] = set()
    micro: set[str] = set()
    for ln in lines or []:
        mc = str(ln.get('main_category_name') or '').strip()
        c = str(ln.get('category_name') or '').strip()
        mic = str(ln.get('micro_category_name') or '').strip()
        if mc:
            main.add(mc)
        if c:
            cat.add(c)
        if mic:
            micro.add(mic)
    return {
        'main_categories': sorted(main),
        'categories': sorted(cat),
        'micro_categories': sorted(micro),
    }


def _line_warehouse_label(ln: Dict[str, Any]) -> str:
    code = str(ln.get('warehouse_code') or '').strip()
    name = str(ln.get('warehouse_name') or '').strip()
    if code and name:
        return f'{code} — {name}'
    if code or name:
        return code or name
    wh_id = ln.get('warehouse_id')
    return f'WH {wh_id}' if wh_id else ''


def _line_system_value(ln: Dict[str, Any]) -> float:
    """ERP book stock value at count time: system qty × average cost."""
    try:
        system = float(ln.get('system_qty') or 0)
        avg = float(ln.get('average_cost') or 0)
        return round(system * avg, 2)
    except (TypeError, ValueError):
        return 0.0


def _line_stock_value(ln: Dict[str, Any]) -> float:
    """Counted inventory value: counted qty × average cost."""
    try:
        counted = float(ln.get('counted_qty') or 0)
        avg = float(ln.get('average_cost') or 0)
        return round(counted * avg, 2)
    except (TypeError, ValueError):
        return 0.0


def _list_stock_count_stats(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(rows or [])
    open_count = 0
    posted = 0
    cancelled = 0
    total_lines = 0
    for r in rows or []:
        st = (r.get('status') or '').strip().upper()
        if st in ('DRAFT', 'PENDING'):
            open_count += 1
        elif st == 'POSTED':
            posted += 1
        elif st == 'CANCELLED':
            cancelled += 1
        try:
            total_lines += int(r.get('line_count') or 0)
        except (TypeError, ValueError):
            pass
    return {
        'total': total,
        'open': open_count,
        'posted': posted,
        'cancelled': cancelled,
        'total_lines': total_lines,
    }


def register(bp) -> None:
    """Register stock counting routes on the warehouse blueprint."""

    def _loc() -> int:
        try:
            return int(session.get('location_code') or 1)
        except (TypeError, ValueError):
            return 1

    def _user() -> str:
        u = session.get('user')
        if isinstance(u, dict):
            name = str(u.get('username') or u.get('name') or u.get('id') or '').strip()
            if name:
                return name[:50]
        elif u:
            return str(u).strip()[:50]
        ec = session.get('employeecode')
        return str(ec or '').strip()[:50]

    def _role_perms() -> List[str]:
        try:
            from db import get_user_role_id
            from permissions import get_role_permissions

            rid = get_user_role_id(_user())
            return list(get_role_permissions(rid) or []) if rid else []
        except Exception:
            return []

    def _allowed_desktop() -> bool:
        u = _user().strip().lower()
        if u in ('admin', 'super'):
            return True
        perms = _role_perms()
        return 'warehouse.warehouse_stock_counting' in perms

    def _allowed_api() -> bool:
        return _allowed_desktop()

    def _stock_count_opening_mode_enabled() -> bool:
        try:
            return bool(get_stk_adj_opening_stock_mode_enabled())
        except Exception:
            return False

    def _is_stock_count_reversal(row: Optional[Dict[str, Any]]) -> bool:
        return str((row or {}).get('remarks') or '').strip().upper().startswith('REVERSAL OF STOCK COUNT #')

    def _stock_count_reversal_of(loc: int, count_no: int) -> Optional[int]:
        needle = f'REVERSAL OF STOCK COUNT #{int(count_no)}'
        for row in list_stock_counts(int(loc), limit=500) or []:
            if str(row.get('remarks') or '').strip().upper().startswith(needle):
                try:
                    return int(row.get('count_no') or 0) or None
                except (TypeError, ValueError):
                    return None
        return None

    def _reverse_stock_count(loc: int, count_no: int, user: str) -> tuple:
        hdr = get_stock_count_header(int(loc), int(count_no))
        if not hdr:
            return (False, 'Stock count not found.', None)
        if _is_stock_count_reversal(hdr):
            return (False, 'This document is already a reversal document.', None)
        if str(hdr.get('status') or '').strip().upper() != 'POSTED':
            return (False, 'Only posted stock counts can be reversed.', None)
        existing = _stock_count_reversal_of(int(loc), int(count_no))
        if existing:
            return (False, f'Stock count #{count_no} is already reversed by count #{existing}.', existing)
        lines = get_stock_count_lines(int(loc), int(count_no))
        if not lines:
            return (False, 'No lines found to reverse.', None)
        ok, err, rev_no = create_stock_count(
            location_code=int(loc),
            count_date=date.today(),
            warehouse_id=hdr.get('warehouse_id'),
            storage_id=hdr.get('storage_id'),
            remarks=f'Reversal of stock count #{int(count_no)}',
            created_by=user,
        )
        if not ok or not rev_no:
            return (False, err or 'Could not create reversal count.', None)
        reverse_lines: List[Dict[str, Any]] = []
        for ln in lines:
            try:
                variance = float(ln.get('variance_qty') or 0)
                system_qty = float(ln.get('system_qty') or 0)
            except (TypeError, ValueError):
                continue
            if abs(variance) < 0.0005:
                continue
            reverse_lines.append({
                'item_code': ln.get('itemcode'),
                'barcode': ln.get('barcode') or '',
                'uom': ln.get('uom') or 'NOS',
                # upsert recalculates current system qty; this target reverses the original variance.
                'counted_qty': system_qty - variance,
                'warehouse_id': ln.get('warehouse_id') or hdr.get('warehouse_id'),
                'storage_id': ln.get('storage_id') or hdr.get('storage_id'),
            })
        if not reverse_lines:
            return (False, 'No variance lines found to reverse.', None)
        ok, err, _written = upsert_stock_count_lines(
            int(loc), int(rev_no), reverse_lines, merge_by_item=True, counted_by=user,
        )
        if not ok:
            return (False, err or 'Could not create reversal lines.', rev_no)
        ok, err, stats = post_stock_count_to_inventory(
            int(loc), int(rev_no), posted_by=user, only_nonzero_variance=True,
        )
        if not ok:
            return (False, err or 'Could not post reversal.', rev_no)
        return (True, err or 'Reversal posted.', int(rev_no))

    @bp.route('/warehouse/stock-counting/mobile')
    @bp.route('/warehouse/stock-counting/mobile/new', methods=('GET', 'POST'))
    def warehouse_stock_counting_mobile_redirect():
        if not session.get('user'):
            return redirect(url_for('auth.login'))
        if not _allowed_desktop():
            abort(403)
        return redirect(url_for('warehouse.warehouse_stock_counting_list'))

    @bp.route('/warehouse/stock-counting/mobile/<int:count_no>')
    def warehouse_stock_counting_mobile_scan_redirect(count_no: int):
        if not session.get('user'):
            return redirect(url_for('auth.login'))
        if not _allowed_desktop():
            abort(403)
        return redirect(url_for('warehouse.warehouse_stock_counting_detail', count_no=count_no))

    @bp.route('/warehouse/stock-counting')
    def warehouse_stock_counting_list():
        if not session.get('user'):
            return redirect(url_for('auth.login'))
        if not _allowed_desktop():
            abort(403)
        ensure_stock_count_tables()
        loc = _loc()
        status_filter = (request.args.get('status') or '').strip().upper()
        rows = list_stock_counts(loc, status=status_filter or None)
        for row in rows:
            try:
                cn = int(row.get('count_no') or 0)
            except (TypeError, ValueError):
                cn = 0
            row['is_reversal'] = _is_stock_count_reversal(row)
            row['reversal_no'] = _stock_count_reversal_of(loc, cn) if cn and not row['is_reversal'] else None
        return render_template(
            'warehouse/stock_count_list.html',
            rows=rows,
            statuses=STOCK_COUNT_STATUSES,
            status_filter=status_filter,
            location_code=loc,
            list_kpis=_list_stock_count_stats(rows),
            opening_stock_mode=_stock_count_opening_mode_enabled(),
            accounts_config_url=url_for('purchase.stock_adjustment_accounts_configuration_page', return_to='stock_count'),
        )

    @bp.route('/warehouse/stock-counting/new', methods=('GET', 'POST'))
    def warehouse_stock_counting_new():
        if not session.get('user'):
            return redirect(url_for('auth.login'))
        if not _allowed_desktop():
            abort(403)
        ensure_stock_count_tables()
        loc = _loc()
        sites = get_warehouse_location_sites() or []
        bins: List[Dict[str, Any]] = []
        if request.method == 'POST':
            try:
                wh = int(request.form.get('warehouse_id') or 0) or None
            except (TypeError, ValueError):
                wh = None
            try:
                sid = int(request.form.get('storage_id') or 0) or None
            except (TypeError, ValueError):
                sid = None
            raw_date = (request.form.get('count_date') or '').strip()
            try:
                cd = datetime.strptime(raw_date[:10], '%Y-%m-%d').date() if raw_date else date.today()
            except ValueError:
                cd = date.today()
            ok, err, cn = create_stock_count(
                location_code=loc,
                count_date=cd,
                warehouse_id=wh,
                storage_id=sid,
                remarks=(request.form.get('remarks') or '').strip(),
                created_by=_user(),
            )
            if not ok or cn is None:
                flash(err or 'Could not create count.', 'error')
            else:
                flash(f'Stock count #{cn} created.', 'success')
                return redirect(url_for('warehouse.warehouse_stock_counting_list'))
        return render_template(
            'warehouse/stock_count_new.html',
            location_code=loc,
            sites=sites,
            bins=bins,
            today=date.today().isoformat(),
        )

    @bp.route('/warehouse/stock-counting/<int:count_no>')
    def warehouse_stock_counting_detail(count_no: int):
        if not session.get('user'):
            return redirect(url_for('auth.login'))
        if not _allowed_desktop():
            abort(403)
        ensure_stock_count_tables()
        loc = _loc()
        hdr = get_stock_count_header(loc, count_no)
        if not hdr:
            flash('Stock count not found.', 'error')
            return redirect(url_for('warehouse.warehouse_stock_counting_list'))
        lines = get_stock_count_lines(loc, count_no)
        hdr_wh_label = ''
        if hdr.get('warehouse_id'):
            wh_row = get_warehouse_master_by_id(hdr.get('warehouse_id'))
            if wh_row:
                code = str(wh_row.get('warehouse_code') or wh_row.get('WAREHOUSE_CODE') or '').strip()
                name = str(wh_row.get('warehouse_name') or wh_row.get('WAREHOUSE_NAME') or '').strip()
                hdr_wh_label = f'{code} — {name}'.strip(' —') if code and name else (code or name)
            else:
                hdr_wh_label = f'WH {hdr.get("warehouse_id")}'
        sites = get_warehouse_location_sites() or []
        sc_kpis = _count_line_stats(lines)
        journal_rows = _journal_rows_json_safe(list_stock_count_journal(loc, count_no, limit=100))
        filter_options = _stock_count_line_filter_options(lines)
        return render_template(
            'warehouse/stock_count_detail.html',
            hdr=hdr,
            hdr_wh_label=hdr_wh_label,
            lines=lines,
            journal_rows=journal_rows,
            location_code=loc,
            count_no=count_no,
            sites=sites,
            sc_kpis=sc_kpis,
            filter_options=filter_options,
            export_excel_url=url_for('warehouse.warehouse_stock_counting_export_excel', count_no=count_no),
            export_pdf_url=url_for('warehouse.warehouse_stock_counting_export_pdf', count_no=count_no),
            opening_stock_mode=_stock_count_opening_mode_enabled(),
            accounts_config_url=url_for('purchase.stock_adjustment_accounts_configuration_page', return_to='stock_count'),
        )

    @bp.route('/warehouse/api/stock-count/list')
    def api_stock_count_list():
        if not session.get('user'):
            return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
        if not _allowed_api():
            return jsonify({'success': False, 'error': 'Forbidden'}, 403)
        ensure_stock_count_tables()
        st = (request.args.get('status') or '').strip().upper() or None
        rows = list_stock_counts(_loc(), status=st)
        return jsonify({'success': True, 'rows': rows})

    @bp.route('/warehouse/api/stock-count/<int:count_no>')
    def api_stock_count_get(count_no: int):
        if not session.get('user'):
            return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
        if not _allowed_api():
            return jsonify({'success': False, 'error': 'Forbidden'}, 403)
        loc = _loc()
        hdr = get_stock_count_header(loc, count_no)
        if not hdr:
            return jsonify({'success': False, 'error': 'Not found'}, 404)
        lines = get_stock_count_lines(loc, count_no)
        journal = _journal_rows_json_safe(list_stock_count_journal(loc, count_no, limit=200))
        return jsonify({'success': True, 'header': hdr, 'lines': lines, 'journal': journal})

    @bp.route('/warehouse/api/stock-count/pdt/upload', methods=['POST'])
    def api_stock_count_pdt_upload():
        """
        PDT batch upload (JSON).

        Body: ``count_no``, optional ``device_id``, ``lines``:
        ``[{barcode|item_code, qty|counted_qty, storage_id?, warehouse_id?}, ...]``
        """
        if not session.get('user'):
            return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
        if not _allowed_api():
            return jsonify({'success': False, 'error': 'Forbidden'}, 403)
        data = request.get_json(silent=True) or {}
        try:
            count_no = int(data.get('count_no') or 0)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'count_no required'}, 400)
        if count_no <= 0:
            return jsonify({'success': False, 'error': 'count_no required'}, 400)
        lines_in = data.get('lines')
        if not isinstance(lines_in, list) or not lines_in:
            return jsonify({'success': False, 'error': 'lines array required'}, 400)
        loc = _loc()
        ok, err, n = upsert_stock_count_lines(loc, count_no, lines_in, merge_by_item=True, counted_by=_user())
        if not ok:
            return jsonify({'success': False, 'error': err or 'Upload failed'}, 400)
        hdr = get_stock_count_header(loc, count_no)
        return jsonify({
            'success': True,
            'lines_written': n,
            'count_no': count_no,
            'status': (hdr or {}).get('status'),
        })

    @bp.route('/warehouse/api/stock-count/line', methods=['POST'])
    def api_stock_count_add_line():
        """Web: add one scanned line."""
        if not session.get('user'):
            return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
        if not _allowed_api():
            return jsonify({'success': False, 'error': 'Forbidden'}, 403)
        data = request.get_json(silent=True) or {}
        try:
            count_no = int(data.get('count_no') or 0)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'count_no required'}, 400)
        ok, err, n = upsert_stock_count_lines(_loc(), count_no, [data], merge_by_item=True, counted_by=_user())
        if not ok:
            return jsonify({'success': False, 'error': err or 'Failed'}, 400)
        lines = get_stock_count_lines(_loc(), count_no)
        return jsonify({'success': True, 'lines_written': n, 'lines': lines})

    @bp.route('/warehouse/api/stock-count/line/edit', methods=['POST'])
    def api_stock_count_edit_line():
        """Edit one count line (counted qty / bin)."""
        if not session.get('user'):
            return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
        if not _allowed_api():
            return jsonify({'success': False, 'error': 'Forbidden'}, 403)
        data = request.get_json(silent=True) or {}
        try:
            count_no = int(data.get('count_no') or 0)
            line_no = int(data.get('line_no') or 0)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'count_no and line_no required'}, 400)
        if count_no <= 0 or line_no <= 0:
            return jsonify({'success': False, 'error': 'count_no and line_no required'}, 400)
        try:
            counted_qty = float(data.get('counted_qty'))
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'counted_qty required'}, 400)
        storage_id = data.get('storage_id')
        sid: Optional[int] = None
        if storage_id is not None and str(storage_id).strip() != '':
            try:
                sid = int(storage_id)
            except (TypeError, ValueError):
                return jsonify({'success': False, 'error': 'Invalid storage_id'}, 400)
        ok, err = update_stock_count_line(
            _loc(),
            count_no,
            line_no,
            counted_qty=counted_qty,
            storage_id=sid,
            counted_by=_user(),
        )
        if not ok:
            return jsonify({'success': False, 'error': err or 'Update failed'}, 400)
        lines = get_stock_count_lines(_loc(), count_no)
        hdr = get_stock_count_header(_loc(), count_no)
        return jsonify({
            'success': True,
            'lines': lines,
            'status': (hdr or {}).get('status'),
        })

    @bp.route('/warehouse/api/stock-count/line/delete', methods=['POST'])
    def api_stock_count_delete_line():
        """Remove one line from an open stock count."""
        if not session.get('user'):
            return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
        if not _allowed_api():
            return jsonify({'success': False, 'error': 'Forbidden'}, 403)
        data = request.get_json(silent=True) or {}
        try:
            count_no = int(data.get('count_no') or 0)
            line_no = int(data.get('line_no') or 0)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'count_no and line_no required'}, 400)
        if count_no <= 0 or line_no <= 0:
            return jsonify({'success': False, 'error': 'count_no and line_no required'}, 400)
        ok, err = delete_stock_count_line(_loc(), count_no, line_no)
        if not ok:
            return jsonify({'success': False, 'error': err or 'Delete failed'}, 400)
        lines = get_stock_count_lines(_loc(), count_no)
        return jsonify({'success': True, 'lines': lines})

    @bp.route('/warehouse/api/stock-count/post', methods=['POST'])
    def api_stock_count_post():
        """Accept count — update stock from counted quantities."""
        if not session.get('user'):
            return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
        if not _allowed_api():
            return jsonify({'success': False, 'error': 'Forbidden'}, 403)
        data = request.get_json(silent=True) or {}
        try:
            count_no = int(data.get('count_no') or 0)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'count_no required'}, 400)
        only_var = bool(data.get('only_variance'))
        ok, err, stats = post_stock_count_to_inventory(
            _loc(),
            count_no,
            posted_by=_user(),
            only_nonzero_variance=only_var,
        )
        if not ok:
            return jsonify({'success': False, 'error': err, 'stats': stats}, 400)
        return jsonify({'success': True, 'message': err or 'Posted', 'stats': stats})

    @bp.route('/warehouse/api/stock-count/reverse', methods=['POST'])
    def api_stock_count_reverse():
        if not session.get('user'):
            return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
        if not _allowed_api():
            return jsonify({'success': False, 'error': 'Forbidden'}, 403)
        data = request.get_json(silent=True) or {}
        try:
            count_no = int(data.get('count_no') or 0)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'count_no required'}, 400)
        ok, err, rev_no = _reverse_stock_count(_loc(), int(count_no), _user())
        if not ok:
            return jsonify({'success': False, 'error': err or 'Reverse failed.', 'reversal_no': rev_no}, 400)
        return jsonify({
            'success': True,
            'message': f'Stock count reversed. Reversal count #{rev_no} was posted.',
            'reversal_no': rev_no,
            'list_url': url_for('warehouse.warehouse_stock_counting_list'),
            'detail_url': url_for('warehouse.warehouse_stock_counting_detail', count_no=rev_no),
        })

    @bp.route('/warehouse/api/stock-count/cancel', methods=['POST'])
    def api_stock_count_cancel():
        if not session.get('user'):
            return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
        if not _allowed_api():
            return jsonify({'success': False, 'error': 'Forbidden'}, 403)
        data = request.get_json(silent=True) or {}
        try:
            count_no = int(data.get('count_no') or 0)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'count_no required'}, 400)
        ok, err = set_stock_count_status(_loc(), count_no, 'CANCELLED')
        if not ok:
            return jsonify({'success': False, 'error': err}, 400)
        return jsonify({'success': True})

    @bp.route('/warehouse/api/stock-count/delete', methods=['POST'])
    def api_stock_count_delete():
        if not session.get('user'):
            return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
        if not _allowed_api():
            return jsonify({'success': False, 'error': 'Forbidden'}, 403)
        data = request.get_json(silent=True) or {}
        try:
            count_no = int(data.get('count_no') or 0)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'count_no required'}, 400)
        ok, err = delete_stock_count(_loc(), count_no)
        if not ok:
            return jsonify({'success': False, 'error': err}, 400)
        return jsonify({'success': True})

    @bp.route('/warehouse/stock-counting/<int:count_no>/export-excel')
    def warehouse_stock_counting_export_excel(count_no: int):
        if not session.get('user'):
            return redirect(url_for('auth.login'))
        if not _allowed_desktop():
            abort(403)
        ensure_stock_count_tables()
        loc = _loc()
        hdr = get_stock_count_header(loc, count_no)
        if not hdr:
            flash('Stock count not found.', 'error')
            return redirect(url_for('warehouse.warehouse_stock_counting_list'))
        lines = get_stock_count_lines(loc, count_no)
        filters = _stock_count_line_filters_from_request(request.args)
        rows = _filter_stock_count_lines(lines, filters)
        output = io.StringIO()
        output.write('\ufeff')
        writer = csv.writer(output)
        writer.writerow([
            'Line', 'Item', 'Name', 'Main category', 'Category', 'Micro category',
            'Barcode', 'Warehouse', 'System qty', 'System value', 'Counted qty',
            'Counted value', 'Variance qty', 'Variance amount', 'User', 'Avg cost', 'Bin',
        ])
        for ln in rows:
            writer.writerow([
                ln.get('line_no'),
                ln.get('itemcode'),
                ln.get('item_name'),
                ln.get('main_category_name'),
                ln.get('category_name'),
                ln.get('micro_category_name'),
                ln.get('barcode'),
                _line_warehouse_label(ln),
                ln.get('system_qty'),
                _line_system_value(ln),
                ln.get('counted_qty'),
                _line_stock_value(ln),
                ln.get('variance_qty'),
                _line_variance_amount(ln),
                ln.get('counted_by'),
                ln.get('average_cost'),
                ln.get('storage_id'),
            ])
        output.seek(0)
        fname = f'stock_count_{count_no}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        return Response(
            output.getvalue(),
            mimetype='text/csv; charset=utf-8',
            headers={'Content-Disposition': f'attachment; filename={fname}'},
        )

    @bp.route('/warehouse/stock-counting/<int:count_no>/export-pdf')
    def warehouse_stock_counting_export_pdf(count_no: int):
        if not session.get('user'):
            return redirect(url_for('auth.login'))
        if not _allowed_desktop():
            abort(403)
        if not REPORTLAB_AVAILABLE:
            flash('PDF export requires ReportLab.', 'warning')
            return redirect(url_for('warehouse.warehouse_stock_counting_detail', count_no=count_no, **request.args))
        ensure_stock_count_tables()
        loc = _loc()
        hdr = get_stock_count_header(loc, count_no)
        if not hdr:
            flash('Stock count not found.', 'error')
            return redirect(url_for('warehouse.warehouse_stock_counting_list'))
        lines = get_stock_count_lines(loc, count_no)
        filters = _stock_count_line_filters_from_request(request.args)
        rows = _filter_stock_count_lines(lines, filters)[:500]
        count_date = hdr.get('count_date')
        if isinstance(count_date, datetime):
            count_date_str = count_date.strftime('%Y-%m-%d')
        elif isinstance(count_date, date):
            count_date_str = count_date.strftime('%Y-%m-%d')
        else:
            count_date_str = str(count_date or '')
        status = str(hdr.get('status') or '').upper()
        stats = _count_line_stats(rows)
        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=landscape(A4),
            leftMargin=24,
            rightMargin=24,
            topMargin=24,
            bottomMargin=24,
        )
        styles = getSampleStyleSheet()
        story = [
            Paragraph(f'Stock Count #{count_no}', styles['Title']),
            Spacer(1, 8),
            Paragraph(
                f'Date {count_date_str} | Status {status} | Lines {stats.get("line_count", 0)} | '
                f'Variances {stats.get("variance_count", 0)} | Var amount {stats.get("total_variance_amount", 0):,.2f} | '
                f'Stock value {stats.get("total_stock_value", 0):,.2f}',
                styles['Normal'],
            ),
            Spacer(1, 12),
        ]
        table_data = [[
            '#', 'Item', 'Name', 'Sys qty', 'Sys value', 'Counted', 'Cnt value', 'Var qty', 'Var amt',
        ]]
        for ln in rows:
            table_data.append([
                str(ln.get('line_no') or ''),
                str(ln.get('itemcode') or ''),
                str(ln.get('itemname') or ln.get('item_name') or '')[:22],
                f'{float(ln.get("system_qty") or 0):.3f}',
                f'{_line_system_value(ln):,.2f}',
                f'{float(ln.get("counted_qty") or 0):.3f}',
                f'{_line_stock_value(ln):,.2f}',
                f'{float(ln.get("variance_qty") or 0):.3f}',
                f'{_line_variance_amount(ln):,.2f}',
            ])
        tbl = Table(table_data, repeatRows=1)
        tbl.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTSIZE', (0, 0), (-1, -1), 7),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        story.append(tbl)
        doc.build(story)
        buf.seek(0)
        fname = f'stock_count_{count_no}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
        return send_file(buf, mimetype='application/pdf', as_attachment=True, download_name=fname)
