"""Settings page services."""
from __future__ import annotations

from typing import Any, Dict, Tuple

from addons.ecommerce import settings_db
from addons.ecommerce import settings_store


def get_settings_page(*, section: str = 'general') -> Dict[str, Any]:
    store = settings_store.load_store_settings()
    zones, delivery_warning = settings_db.list_delivery_zones(include_inactive=True)
    return {
        'section': section or 'general',
        'store': store,
        'delivery_zones': zones,
        'delivery_slots': settings_db.list_delivery_slots(include_inactive=True),
        'pickup_stores': settings_db.list_pickup_stores(include_inactive=True),
        'delivery_warning': delivery_warning,
        'delivery_ready': settings_db.delivery_tables_ready(),
    }


def save_general_settings(form: Dict[str, str]) -> Tuple[bool, str]:
    try:
        tax_rate = float(form.get('tax_rate') or 0)
    except ValueError:
        return False, 'Tax rate must be a number.'

    store_name = (form.get('store_name') or '').strip()
    if not store_name:
        return False, 'Store name is required.'

    settings_store.save_store_settings({
        'store_name': store_name,
        'store_email': (form.get('store_email') or '').strip(),
        'store_phone': (form.get('store_phone') or '').strip(),
        'store_address': (form.get('store_address') or '').strip(),
        'currency_code': (form.get('currency_code') or 'QAR').strip().upper(),
        'timezone': (form.get('timezone') or 'Asia/Qatar').strip(),
        'tax_rate': tax_rate,
        'checkout_enabled': _checkbox(form.get('checkout_enabled')),
        'pickup_enabled': _checkbox(form.get('pickup_enabled')),
        'delivery_enabled': _checkbox(form.get('delivery_enabled')),
        'coupons_enabled': _checkbox(form.get('coupons_enabled')),
    })
    return True, 'Store settings saved'


def save_web_catalog_settings(form: Dict[str, str]) -> Tuple[bool, str]:
    settings_store.save_store_settings({
        'show_all_items_on_web': _checkbox(form.get('show_all_items_on_web')),
    })
    if settings_store.show_all_items_on_web():
        message = 'Storefront will show all catalog items, including out of stock.'
    else:
        message = 'Storefront will show in-stock items only.'
    return True, message


def save_delivery_zone(zone_id: int, form: Dict[str, str]) -> Tuple[bool, str]:
    try:
        delivery_fee = float(form.get('delivery_fee') or 0)
        min_order_amount = float(form.get('min_order_amount') or 0)
        estimated_days = int(form.get('estimated_days') or 2)
        threshold_raw = (form.get('free_delivery_threshold') or '').strip()
        free_delivery_threshold = float(threshold_raw) if threshold_raw else None
    except ValueError:
        return False, 'Zone numeric fields must be valid numbers.'
    return settings_db.update_delivery_zone(
        zone_id,
        delivery_fee=delivery_fee,
        min_order_amount=min_order_amount,
        free_delivery_threshold=free_delivery_threshold,
        estimated_days=estimated_days,
        is_active=_checkbox(form.get('is_active')),
    )


def create_delivery_zone(form: Dict[str, str]) -> Tuple[bool, str]:
    try:
        delivery_fee = float(form.get('delivery_fee') or 0)
        min_order_amount = float(form.get('min_order_amount') or 0)
        estimated_days = int(form.get('estimated_days') or 2)
        threshold_raw = (form.get('free_delivery_threshold') or '').strip()
        free_delivery_threshold = float(threshold_raw) if threshold_raw else None
    except ValueError:
        return False, 'Zone numeric fields must be valid numbers.'
    return settings_db.create_delivery_zone(
        zone_code=(form.get('zone_code') or form.get('zone_name') or '').strip(),
        zone_name=(form.get('zone_name') or '').strip(),
        city=(form.get('city') or '').strip(),
        delivery_fee=delivery_fee,
        min_order_amount=min_order_amount,
        free_delivery_threshold=free_delivery_threshold,
        estimated_days=estimated_days,
        is_active=_checkbox(form.get('is_active', '1')),
    )


def create_delivery_slot(form: Dict[str, str]) -> Tuple[bool, str]:
    try:
        start_hour = int(form.get('start_hour') or 9)
        end_hour = int(form.get('end_hour') or 17)
        max_orders = int(form.get('max_orders') or 50)
    except ValueError:
        return False, 'Slot numeric fields must be valid numbers.'
    return settings_db.create_delivery_slot(
        slot_code=(form.get('slot_code') or form.get('slot_label') or '').strip(),
        slot_label=(form.get('slot_label') or '').strip(),
        start_hour=start_hour,
        end_hour=end_hour,
        max_orders=max_orders,
        is_active=_checkbox(form.get('is_active', '1')),
    )


def create_pickup_store(form: Dict[str, str]) -> Tuple[bool, str]:
    try:
        open_hour = int(form.get('open_hour') or 9)
        close_hour = int(form.get('close_hour') or 21)
    except ValueError:
        return False, 'Store hours must be valid numbers.'
    return settings_db.create_pickup_store(
        store_code=(form.get('store_code') or form.get('store_name') or '').strip(),
        store_name=(form.get('store_name') or '').strip(),
        address_line=(form.get('address_line') or '').strip(),
        city=(form.get('city') or '').strip(),
        open_hour=open_hour,
        close_hour=close_hour,
        is_active=_checkbox(form.get('is_active', '1')),
    )


def _checkbox(value: Any) -> bool:
    return str(value or '').lower() in ('1', 'true', 'on', 'yes')
