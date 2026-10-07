"""Menu price & points — routes colocated under ``addons/menu_price_setup``."""
from __future__ import annotations
import io
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Tuple
from nexa_http import Blueprint, Response, flash, redirect, render_template, request, session, url_for
from db import get_menu_price_category_rows, save_menu_price_category_rows, update_itemmaster_retail_from_cost_by_menu_category
_ADDON_ROOT = Path(__file__).resolve().parents[1]
bp = Blueprint('menu_price_setup', __name__, template_folder=str(_ADDON_ROOT / 'views' / 'templates'))
_MENU_PRICE_IMPORT_MAX_ROWS = 5000
_MENU_PRICE_QUICK_LOAD_LIMIT = 300

def _location_code_int() -> int:
    loc = session.get('location_code') or 'HO'
    try:
        if str(loc).isdigit():
            return int(loc)
    except Exception:
        pass
    return 1

def _parse_menu_price_xlsx(raw: bytes) -> Tuple[List[Dict[str, Any]], str]:
    try:
        from openpyxl import load_workbook
    except ImportError:
        return ([], 'Excel upload requires openpyxl (pip install openpyxl).')
    try:
        wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        try:
            ws = wb.active
            rows = ws.iter_rows(values_only=True)
            header = next(rows, None)
            if not header:
                return ([], 'Excel sheet is empty.')
            keys = [str(c or '').strip().lower().replace(' ', '').replace('_', '') for c in header]
            out: List[Dict[str, Any]] = []
            for row in rows:
                if len(out) >= _MENU_PRICE_IMPORT_MAX_ROWS:
                    break
                rec: Dict[str, Any] = {}
                for idx, key in enumerate(keys):
                    if not key:
                        continue
                    val = row[idx] if idx < len(row) else None
                    if key in ('code', 'categorycode'):
                        rec['code'] = val
                    elif key in ('name', 'categoryname'):
                        rec['name'] = val
                    elif key in ('locationcode', 'loc'):
                        rec['locationcode'] = val
                    elif key == 'amount':
                        rec['amount'] = val
                    elif key == 'points':
                        rec['points'] = val
                    elif key in ('pricepercentage', 'pricepercent', 'pricepct', 'price%'):
                        rec['pricepercentage'] = val
                if any(v not in (None, '') for v in rec.values()):
                    out.append(rec)
            return (out, '')
        finally:
            try:
                wb.close()
            except Exception:
                pass
    except Exception as exc:
        return ([], str(exc) or 'Could not read Excel file.')

def _float_or_zero(v: Any) -> float:
    try:
        return float(str(v if v is not None else '').strip() or 0)
    except (TypeError, ValueError):
        return 0.0

@bp.route('/setup/menu-price-points', methods=['GET', 'POST'])
def menu_price_points_page():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    loc = _location_code_int()
    if request.method == 'POST':
        codes = request.form.getlist('code')
        amount_list = request.form.getlist('amount')
        points_list = request.form.getlist('points')
        pct_list = request.form.getlist('pricepercentage')
        row_locs = request.form.getlist('row_location')
        updates = []
        for i, c in enumerate(codes):
            try:
                code = int(float(str(c).strip()))
            except (TypeError, ValueError):
                continue
            amt_s = (amount_list[i] if i < len(amount_list) else '0') or '0'
            pts_s = (points_list[i] if i < len(points_list) else '0') or '0'
            pct_s = (pct_list[i] if i < len(pct_list) else '0') or '0'
            try:
                amt = float(str(amt_s).strip())
            except (TypeError, ValueError):
                amt = 0.0
            try:
                pts = float(str(pts_s).strip())
            except (TypeError, ValueError):
                pts = 0.0
            try:
                pctp = float(str(pct_s).strip())
            except (TypeError, ValueError):
                pctp = 0.0
            item = {'code': code, 'amount': amt, 'points': pts, 'pricepercentage': pctp}
            if i < len(row_locs):
                item['locationcode'] = row_locs[i]
            updates.append(item)
        ok, err = save_menu_price_category_rows(loc, updates)
        if ok:
            flash('Menu price and points saved.', 'success')
        else:
            flash(f'Save failed: {err}', 'error')
        return redirect(url_for('menu_price_setup.menu_price_points_page'))
    show_all = str(request.args.get('all') or '').strip() == '1'
    quick_limit = None if show_all else _MENU_PRICE_QUICK_LOAD_LIMIT + 1
    rows, list_was_fallback = get_menu_price_category_rows(loc, limit=quick_limit)
    quick_limited = bool((not show_all) and len(rows or []) > _MENU_PRICE_QUICK_LOAD_LIMIT)
    if quick_limited:
        rows = rows[:_MENU_PRICE_QUICK_LOAD_LIMIT]
    has_row_location = bool(rows and 'locationcode' in rows[0])
    return render_template(
        'menu_price_setup/menu_price_points.html',
        rows=rows,
        location_code=loc,
        list_was_fallback=list_was_fallback,
        has_row_location=has_row_location,
        quick_limited=quick_limited,
        quick_limit=_MENU_PRICE_QUICK_LOAD_LIMIT,
        show_all=show_all,
    )

@bp.route('/setup/menu-price-points/export.xlsx')
def menu_price_points_export():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    try:
        from openpyxl import Workbook
    except ImportError:
        flash('Excel export requires openpyxl.', 'error')
        return redirect(url_for('menu_price_setup.menu_price_points_page'))
    loc = _location_code_int()
    rows, _fallback = get_menu_price_category_rows(loc)
    wb = Workbook()
    ws = wb.active
    ws.title = 'Menu Price Points'
    ws.append(['Code', 'Name', 'LocationCode', 'Amount', 'Points', 'PricePercentage'])
    for r in rows or []:
        ws.append([
            r.get('code'),
            r.get('name') or '',
            r.get('locationcode') if 'locationcode' in r else '',
            float(r.get('amount') or 0),
            float(r.get('points') or 0),
            float(r.get('pricepercentage') or 0),
        ])
    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    fname = f"menu_price_points_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return Response(bio.getvalue(), mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers={'Content-Disposition': f'attachment; filename="{fname}"'})

@bp.route('/setup/menu-price-points/upload', methods=['POST'])
def menu_price_points_upload():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    fobj = request.files.get('excel_file') or request.files.get('file')
    if not fobj or not getattr(fobj, 'filename', None):
        flash('Choose an Excel file to upload.', 'error')
        return redirect(url_for('menu_price_setup.menu_price_points_page'))
    fname = str(fobj.filename or '').lower()
    if not fname.endswith(('.xlsx', '.xlsm')):
        flash('Please upload .xlsx or .xlsm file.', 'error')
        return redirect(url_for('menu_price_setup.menu_price_points_page'))
    rows, err = _parse_menu_price_xlsx(fobj.read())
    if err:
        flash(err, 'error')
        return redirect(url_for('menu_price_setup.menu_price_points_page'))
    updates: List[Dict[str, Any]] = []
    for row in rows:
        try:
            code = int(float(str(row.get('code', '')).strip()))
        except (TypeError, ValueError):
            continue
        upd = {
            'code': code,
            'amount': _float_or_zero(row.get('amount')),
            'points': _float_or_zero(row.get('points')),
            'pricepercentage': _float_or_zero(row.get('pricepercentage')),
        }
        if 'locationcode' in row:
            upd['locationcode'] = row.get('locationcode')
        updates.append(upd)
    ok, save_err = save_menu_price_category_rows(_location_code_int(), updates)
    if ok:
        flash(f'Uploaded {len(updates)} row(s).', 'success')
    else:
        flash(f'Upload failed: {save_err}', 'error')
    return redirect(url_for('menu_price_setup.menu_price_points_page'))

@bp.route('/setup/menu-price-points/update-retail', methods=['POST'])
def menu_price_points_update_retail():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    raw_categories = request.form.getlist('category_codes')
    category_codes: List[int] = []
    if raw_categories and 'all' not in {str(x).strip().lower() for x in raw_categories}:
        for raw in raw_categories:
            try:
                code = int(float(str(raw).strip()))
            except (TypeError, ValueError):
                continue
            if code > 0 and code not in category_codes:
                category_codes.append(code)
    percentage = _float_or_zero(request.form.get('percentage'))
    price_kind = (request.form.get('price_kind') or 'retail').strip().lower()
    if price_kind not in {'retail', 'wholesale', 'third'}:
        price_kind = 'retail'
    ok, err, count = update_itemmaster_retail_from_cost_by_menu_category(
        _location_code_int(),
        category_codes or None,
        percentage,
        price_kind,
        str(session.get('user') or '').strip() or None,
    )
    if ok:
        price_label = {'retail': 'retail price', 'wholesale': 'wholesale price', 'third': 'third price'}.get(price_kind, 'retail price')
        label = 'all categories' if not category_codes else f"{len(category_codes)} selected categor{'y' if len(category_codes) == 1 else 'ies'}"
        flash(f'Updated {price_label} for {count} item(s) in {label}, and saved the percentage in Category.', 'success')
    else:
        flash(f'Price update failed: {err}', 'error')
    return redirect(url_for('menu_price_setup.menu_price_points_page'))
