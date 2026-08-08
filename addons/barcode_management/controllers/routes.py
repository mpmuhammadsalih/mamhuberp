"""Barcode management — product lookup + shelf/storage labels (WAREHOUSE_STORAGE.STORAGE_BARCODE)."""
from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List

from nexa_http import Blueprint, jsonify, redirect, render_template, request, session, url_for
from db import (
    get_goods_receipt_barcode_label_rows,
    get_item_barcode_uom_variants,
    get_location_info_by_dbkey,
    get_warehouse_location_sites,
    get_warehouse_storage_flat,
    get_warehouse_storage_tree,
    search_barcode_management_item_picker,
    search_barcode_management_products,
    update_warehouse_storage_barcode,
)

_ADDON_ROOT = Path(__file__).resolve().parents[1]
bp = Blueprint('barcode_management', __name__, url_prefix='/barcode-management', template_folder=str(_ADDON_ROOT / 'views' / 'templates'))

def _session_location_code() -> int:
    v = session.get('location_code')
    if v is not None:
        try:
            if str(v).isdigit():
                return int(v)
        except (TypeError, ValueError):
            pass
    try:
        info = get_location_info_by_dbkey(None) or {}
        loc = info.get('locationcode')
        if loc is not None:
            return int(loc) if isinstance(loc, (int, float)) else int(str(loc).strip())
    except Exception:
        pass
    return 1

def _site_key_allowed(sites: List[Dict[str, Any]], key: str) -> bool:
    k = (key or '').strip()
    if not k or not sites:
        return False
    for s in sites:
        if str(s.get('key', '')).strip() == k:
            return True
    return False

def _pick_location_site(sites: List[Dict[str, Any]]) -> tuple[str, str, str]:
    if not sites:
        return ('', '', '')
    loc_param = (request.args.get('loc') or '').strip()
    if loc_param and _site_key_allowed(sites, loc_param):
        for s in sites:
            if str(s.get('key', '')).strip() == loc_param:
                return (str(s['key']).strip(), str(s.get('name') or '').strip() or str(s['key']), str(s.get('source') or ''))
    sess = _session_location_code()
    sess_s = str(sess).strip()
    for s in sites:
        if str(s.get('key', '')).strip() == sess_s:
            return (str(s['key']).strip(), str(s.get('name') or '').strip() or sess_s, str(s.get('source') or ''))
    s0 = sites[0]
    return (str(s0.get('key', '')).strip(), str(s0.get('name') or '').strip() or str(s0.get('key')), str(s0.get('source') or ''))

@bp.before_request
def _login():
    if not session.get('user'):
        return redirect(url_for('auth.login'))

@bp.route('/', methods=['GET'])
def barcode_management_page():
    tab = (request.args.get('tab') or 'product').strip().lower()
    if tab not in ('product', 'shelf'):
        tab = 'product'
    sites = get_warehouse_location_sites()
    loc_key, loc_name, loc_src = _pick_location_site(sites)
    shelf_rows: List[Dict[str, Any]] = []
    if loc_key:
        tree = get_warehouse_storage_tree(loc_key)
        flat = get_warehouse_storage_flat(loc_key, tree=tree)
        st_ok = frozenset({'SHELF', 'BIN', 'STAGING'})
        shelf_rows = [r for r in (flat or []) if str(r.get('storage_type') or '').upper() in st_ok]
        for r in shelf_rows:
            seg: List[str] = []
            pr = r.get('parent_rack_code')
            ps = r.get('parent_shelf_code')
            if pr is not None and str(pr).strip():
                seg.append(str(pr).strip())
            if ps is not None and str(ps).strip():
                seg.append(str(ps).strip())
            r['path_text'] = ' › '.join(seg)
    return render_template('barcode_management/barcode_management.html', title='Barcode management', tab=tab, location_sites=sites or [], selected_loc_key=loc_key, selected_loc_name=loc_name, location_source=loc_src, shelf_rows=shelf_rows, session_location_code=_session_location_code())

@bp.route('/api/products', methods=['GET'])
def barcode_products_api():
    """Search ITEMMASTER + alternate UOM barcodes (read-only helper)."""
    q = (request.args.get('q') or '').strip()
    rows = search_barcode_management_products(_session_location_code(), q, limit=200)
    return jsonify({'success': True, 'rows': rows})

@bp.route('/api/items', methods=['GET'])
def barcode_items_api():
    """Searchable item list for popup — one row per UOM variant."""
    search = (request.args.get('search') or '').strip()
    try:
        limit = int(request.args.get('limit') or 200)
    except (TypeError, ValueError):
        limit = 200
    items = search_barcode_management_item_picker(_session_location_code(), search, limit=limit)
    return jsonify({'success': True, 'items': items})

@bp.route('/api/grn-lines', methods=['GET'])
def barcode_grn_lines_api():
    """Load GRN receipt lines as product label rows for the print queue."""
    try:
        receipt_no = int(request.args.get('receiptno') or request.args.get('grn') or 0)
    except (TypeError, ValueError):
        receipt_no = 0
    if receipt_no <= 0:
        return jsonify({'success': False, 'error': 'receiptno is required.'}, 400)
    result = get_goods_receipt_barcode_label_rows(_session_location_code(), receipt_no)
    return jsonify(result)

@bp.route('/api/item-uoms', methods=['GET'])
def barcode_item_uoms_api():
    """UOM variants (barcode + retail price) for one item — used when changing unit on a row."""
    try:
        item_code = int(request.args.get('itemcode') or 0)
    except (TypeError, ValueError):
        item_code = 0
    if item_code <= 0:
        return jsonify({'success': False, 'error': 'itemcode is required.'}, 400)
    variants = get_item_barcode_uom_variants(_session_location_code(), item_code)
    if not variants:
        return jsonify({'success': False, 'error': 'Item not found.'}, 404)
    return jsonify({'success': True, 'variants': variants})

@bp.route('/api/storage-barcode', methods=['POST'])
def barcode_storage_save_api():
    data = request.get_json(silent=True) or {}
    try:
        sid = int(data.get('storage_id') or 0)
    except (TypeError, ValueError):
        sid = 0
    raw = data.get('storage_barcode')
    if sid <= 0:
        return jsonify({'success': False, 'error': 'storage_id is required.'}, 400)
    ok, err = update_warehouse_storage_barcode(sid, raw if raw is None else str(raw))
    if not ok:
        return jsonify({'success': False, 'error': err or 'Save failed.'}, 400)
    return jsonify({'success': True})
