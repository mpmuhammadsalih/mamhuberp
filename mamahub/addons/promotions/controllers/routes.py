"""Promotions blueprint - discount, mix & match, retail, voucher promotions."""
from pathlib import Path
from typing import Any, Dict, List
from nexa_http import Blueprint, jsonify, redirect, render_template, request, session, url_for
_ADDON_ROOT = Path(__file__).resolve().parents[1]
bp = Blueprint('promotions', __name__, template_folder=str(_ADDON_ROOT / 'views' / 'templates'))

@bp.route('/promotions')
def promotions_page():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    return render_template('promotions/promotions.html')

@bp.route('/promotions/api/active', methods=['GET'])
def api_active_promotions():
    """Return active promotions (discount, mix & match, retail, voucher) for POS/Invoice."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    promotions_list: List[Dict[str, Any]] = []
    return jsonify({'success': True, 'promotions': promotions_list})

@bp.route('/promotions/api/apply-voucher', methods=['POST'])
def api_apply_voucher():
    """Apply voucher code to subtotal; return discount amount. Used by POS Billing and Sales Invoice."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    payload = request.get_json(silent=True) or {}
    code = (payload.get('code') or '').strip()
    try:
        subtotal = float(payload.get('subtotal') or 0)
    except (TypeError, ValueError):
        subtotal = 0
    if not code:
        return jsonify({'success': False, 'error': 'Voucher code required'}, 400)
    discount_amount = 0.0
    message = 'Voucher applied'
    code_upper = code.upper()
    if code_upper == 'SAVE10' and subtotal > 0:
        discount_amount = round(subtotal * 0.1, 2)
        message = '10% off'
    elif code_upper == 'SAVE20' and subtotal > 0:
        discount_amount = round(subtotal * 0.2, 2)
        message = '20% off'
    elif code_upper == 'FLAT50' and subtotal > 0:
        discount_amount = min(50, round(subtotal, 2))
        message = 'Flat 50 off'
    return jsonify({'success': True, 'code': code, 'discount_amount': discount_amount, 'message': message})
