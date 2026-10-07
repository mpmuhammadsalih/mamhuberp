"""Promotion admin services."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

from addons.ecommerce import promotions_db


def _parse_datetime_local(value: str) -> Optional[datetime]:
    text = (value or '').strip().replace('T', ' ')
    if not text:
        return None
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            return datetime.strptime(text[:19] if fmt != '%Y-%m-%d' else text[:10], fmt)
        except ValueError:
            continue
    return None


def _empty_form() -> Dict[str, Any]:
    now = datetime.now().replace(second=0, microsecond=0)
    end = now + timedelta(days=90)
    return {
        'promotion_code': '',
        'promotion_name': '',
        'promotion_type': 'PERCENTAGE',
        'discount_value': 10,
        'min_order_amount': 100,
        'max_discount_amount': '',
        'coupon_code': '',
        'start_date': now.strftime('%Y-%m-%dT%H:%M'),
        'end_date': end.strftime('%Y-%m-%dT%H:%M'),
        'usage_limit': '',
        'usage_per_customer': 1,
    }


def promotion_to_form(promo: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'promotion_code': promo.get('promotion_code') or '',
        'promotion_name': promo.get('promotion_name') or '',
        'promotion_type': promo.get('promotion_type') or 'PERCENTAGE',
        'discount_value': promo.get('discount_value') or 0,
        'min_order_amount': promo.get('min_order_amount') or 0,
        'max_discount_amount': promo.get('max_discount_amount') if promo.get('max_discount_amount') is not None else '',
        'coupon_code': promo.get('coupon_code') or '',
        'start_date': promotions_db.format_datetime_local(promo.get('start_date')),
        'end_date': promotions_db.format_datetime_local(promo.get('end_date')),
        'usage_limit': promo.get('usage_limit') if promo.get('usage_limit') is not None else '',
        'usage_per_customer': promo.get('usage_per_customer') or 1,
    }


def list_promotions_page(*, search: Optional[str] = None) -> Dict[str, Any]:
    rows, warning = promotions_db.list_promotions(search=search)
    for row in rows:
        row['is_live'] = (
            int(row.get('promotion_active') or 0) == 1
            and int(row.get('coupon_active') or 0) == 1
        )
    return {
        'promotions': rows,
        'warning': warning,
        'tables_ready': promotions_db.promotions_tables_ready(),
        'promotion_types': sorted(promotions_db.PROMOTION_TYPES),
    }


def get_create_form() -> Dict[str, Any]:
    return _empty_form()


def get_edit_form(promotion_id: int) -> Optional[Dict[str, Any]]:
    promo = promotions_db.get_promotion(promotion_id)
    if not promo:
        return None
    return promotion_to_form(promo)


def _optional_number(value: str) -> Optional[float]:
    text = (value or '').strip()
    if not text:
        return None
    return float(text)


def validate_create_payload(form: Dict[str, str]) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    promotion_code = (form.get('promotion_code') or '').strip()
    promotion_name = (form.get('promotion_name') or '').strip()
    coupon_code = (form.get('coupon_code') or '').strip()
    promotion_type = (form.get('promotion_type') or '').strip().upper()
    if not promotion_code or not promotion_name or not coupon_code:
        return False, 'Promotion code, name, and coupon code are required.', None
    if promotion_type not in promotions_db.PROMOTION_TYPES:
        return False, f'Invalid promotion type: {promotion_type}', None

    try:
        discount_value = float(form.get('discount_value') or 0)
        min_order_amount = float(form.get('min_order_amount') or 0)
    except ValueError:
        return False, 'Discount and min order must be numbers.', None

    if promotion_type == 'PERCENTAGE' and discount_value > 100:
        return False, 'Percentage discount cannot exceed 100.', None

    start_date = _parse_datetime_local(form.get('start_date') or '')
    end_date = _parse_datetime_local(form.get('end_date') or '')
    if not start_date or not end_date:
        return False, 'Start and end dates are required.', None
    if end_date <= start_date:
        return False, 'End date must be after start date.', None

    payload: Dict[str, Any] = {
        'promotion_code': promotion_code,
        'promotion_name': promotion_name,
        'coupon_code': coupon_code,
        'promotion_type': promotion_type,
        'discount_value': discount_value,
        'min_order_amount': min_order_amount,
        'max_discount_amount': _optional_number(form.get('max_discount_amount') or ''),
        'start_date': start_date,
        'end_date': end_date,
        'usage_limit': _optional_number(form.get('usage_limit') or ''),
        'usage_per_customer': int(form.get('usage_per_customer') or 1),
    }
    return True, '', payload


def validate_update_payload(form: Dict[str, str]) -> Tuple[bool, str, Dict[str, Any]]:
    promotion_name = (form.get('promotion_name') or '').strip()
    if not promotion_name:
        return False, 'Promotion name is required.', {}

    try:
        discount_value = float(form.get('discount_value') or 0)
        min_order_amount = float(form.get('min_order_amount') or 0)
    except ValueError:
        return False, 'Discount and min order must be numbers.', {}

    end_date = _parse_datetime_local(form.get('end_date') or '')
    if not end_date:
        return False, 'End date is required.', {}

    payload: Dict[str, Any] = {
        'promotion_name': promotion_name,
        'discount_value': discount_value,
        'min_order_amount': min_order_amount,
        'max_discount_amount': _optional_number(form.get('max_discount_amount') or ''),
        'end_date': end_date,
        'usage_limit': _optional_number(form.get('usage_limit') or ''),
    }
    return True, '', payload


def create_promotion(form: Dict[str, str]) -> Tuple[bool, str]:
    ok, message, payload = validate_create_payload(form)
    if not ok or not payload:
        return False, message
    success, result_message, _ = promotions_db.create_promotion_with_coupon(payload)
    return success, result_message


def update_promotion(promotion_id: int, form: Dict[str, str]) -> Tuple[bool, str]:
    existing = promotions_db.get_promotion(promotion_id)
    if not existing:
        return False, 'Promotion not found'
    ok, message, payload = validate_update_payload(form)
    if not ok:
        return False, message
    return promotions_db.update_promotion(
        promotion_id,
        coupon_id=int(existing['coupon_id']),
        data=payload,
    )


def toggle_promotion(promotion_id: int) -> Tuple[bool, str]:
    return promotions_db.toggle_promotion_active(promotion_id)
