"""Order list/detail services."""
from __future__ import annotations

import json
import logging
import threading
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

from addons.ecommerce import media_db
from addons.ecommerce import orders_db
from addons.ecommerce import settings_store
from addons.ecommerce.services import media as media_svc
from addons.ecommerce.services import order_invoice as order_invoice_svc
from addons.ecommerce.services import product_edit as product_edit_svc
from addons.ecommerce.services import receipt_qr
from addons.ecommerce.services.common import resolve_location_code
from db import _safe_rows
from storefront_backend.services import gift_wrap as gift_wrap_svc

_LIVE_BUCKETS = {
    'CONFIRMED': 'needs_action',
    'PROCESSING': 'preparing',
    'PICKING': 'preparing',
    'PACKED': 'ready',
}

def order_channel(created_by_name: Any) -> Dict[str, str]:
    raw = str(created_by_name or 'Website').strip() or 'Website'
    if 'whatsapp' in raw.lower():
        return {'channel': 'whatsapp', 'channel_label': 'WhatsApp'}
    return {'channel': 'web', 'channel_label': 'Web'}


_LIVE_BADGES = {
    'CONFIRMED': 'Needs action',
    'PROCESSING': 'Preparing',
    'PICKING': 'Preparing',
    'PACKED': 'Prepared',
}

_HISTORY_LABELS = {
    'CONFIRMED': 'Needs action',
    'PROCESSING': 'Preparing',
    'PICKING': 'Preparing',
    'PACKED': 'Ready',
    'OUT_FOR_DELIVERY': 'Out for delivery',
    'DELIVERED': 'Delivered',
    'CANCELLED': 'Cancelled',
}

_PAYMENT_LABELS = {
    'COD': ('Cash on delivery', 'الدفع عند الاستلام'),
    'CASH': ('Cash', 'نقداً'),
    'TAP': ('Card', 'بطاقة'),
    'CARD': ('Card', 'بطاقة'),
    'APPLEPAY': ('Apple Pay', 'Apple Pay'),
    'APPLE_PAY': ('Apple Pay', 'Apple Pay'),
}

_HISTORY_TONE = {
    'CONFIRMED': 'action',
    'PROCESSING': 'preparing',
    'PICKING': 'preparing',
    'PACKED': 'ready',
    'OUT_FOR_DELIVERY': 'preparing',
    'DELIVERED': 'delivered',
    'CANCELLED': 'cancelled',
}


def list_orders_page(
    *,
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    tab: Optional[str] = None,
    search: Optional[str] = None,
    period: Optional[str] = 'today',
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    channel: Optional[str] = None,
) -> Dict[str, Any]:
    period = (period or 'today').strip().lower() or 'today'
    tab = (tab or 'all').strip().lower() or 'all'
    rows, total, warning = orders_db.list_orders(
        page=page,
        page_size=page_size,
        status=status,
        tab=tab if tab != 'all' else None,
        search=search,
        period=period,
        date_from=date_from,
        date_to=date_to,
        channel=channel,
    )
    settings = settings_store.load_store_settings()
    branch_name = str(settings.get('store_name') or 'MamaHub')
    try:
        from db import get_location_info_by_dbkey
        info = get_location_info_by_dbkey(None) or {}
        loc_name = str(info.get('locationname') or info.get('location_name') or '').strip()
        if loc_name:
            branch_name = loc_name
    except Exception:
        pass
    branch_name = str(branch_name or 'MamaHub').strip().title()
    decorated = [_decorate_history_row(row, branch_name) for row in rows]
    total_pages = max(1, (total + page_size - 1) // page_size) if total else 1
    stats = orders_db.order_history_stats(
        period=period,
        date_from=date_from,
        date_to=date_to,
        channel=channel,
    )
    return {
        'orders': decorated,
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': total_pages,
        'warning': warning,
        'tables_ready': orders_db.orders_tables_ready(),
        'status_options': sorted(orders_db.ALLOWED_STATUSES),
        'stats': stats,
        'period': period,
        'tab': tab,
        'search': search or '',
        'date_from': date_from or '',
        'date_to': date_to or '',
        'channel': (channel or 'all').strip().lower() or 'all',
        'branch_name': branch_name,
    }


def _decorate_history_row(row: Dict[str, Any], branch_name: str) -> Dict[str, Any]:
    item = dict(row)
    status = str(item.get('order_status') or '').upper()
    first = str(item.get('customer_first_name') or '').strip()
    last = str(item.get('customer_last_name') or '').strip()
    name = f'{first} {last}'.strip()
    item['display_status'] = _HISTORY_LABELS.get(status, status.replace('_', ' ').title() or '—')
    item['status_tone'] = _HISTORY_TONE.get(status, 'other')
    item['branch_name'] = str(branch_name or '').strip().title() or '—'
    item['customer_name'] = name or str(item.get('customer_email') or '').split('@', 1)[0] or 'Guest'
    item.update(order_channel(item.get('created_by_name')))
    return item


def get_order_detail(order_id: int) -> Optional[Dict[str, Any]]:
    order = orders_db.get_order(order_id)
    if not order:
        return None
    status = str(order.get('order_status') or '').upper()
    first = str(order.get('customer_first_name') or '').strip()
    last = str(order.get('customer_last_name') or '').strip()
    name = f'{first} {last}'.strip()
    order['display_status'] = _HISTORY_LABELS.get(status, status.replace('_', ' ').title() or '—')
    order['status_tone'] = _HISTORY_TONE.get(status, 'other')
    order['customer_name'] = name.title() if name else (str(order.get('customer_email') or '').split('@', 1)[0] or 'Guest')
    order.update(order_channel(order.get('created_by_name')))
    order['customer_phone'] = str(order.get('customer_mobile') or '').strip()
    order['delivery'] = _parse_delivery(order.get('address_snapshot'))
    order['delivery_address'] = order_invoice_svc._format_address(order.get('address_snapshot'))
    for row in order.get('status_history') or []:
        hs = str(row.get('order_status') or '').upper()
        row['display_status'] = _HISTORY_LABELS.get(hs, hs.replace('_', ' ').title() or '—')
        row['status_tone'] = _HISTORY_TONE.get(hs, 'other')
    return order


def _parse_delivery(raw: Any) -> Dict[str, str]:
    if isinstance(raw, dict):
        data = raw
    else:
        text = str(raw or '').strip()
        if not text:
            return {}
        try:
            data = json.loads(text)
        except (TypeError, ValueError):
            return {'street': text[:240]}
        if not isinstance(data, dict):
            return {'street': text[:240]}
    return {
        'title': str(data.get('address_title') or '').strip(),
        'street': str(data.get('street') or '').strip(),
        'area': str(data.get('area') or '').strip(),
        'zone': str(data.get('zone') or '').strip(),
        'city': str(data.get('city') or '').strip(),
        'country': str(data.get('country') or '').strip(),
        'landmark': str(data.get('landmark') or '').strip(),
    }


def get_order_receipt(order_id: int) -> Optional[Dict[str, Any]]:
    order = get_order_detail(order_id)
    if not order:
        return None
    settings = settings_store.load_store_settings()
    store_name = str(settings.get('store_name') or 'MamaHub').strip() or 'MamaHub'
    store_address = str(settings.get('store_address') or '').strip()
    loc_name = _receipt_location_name()
    fulfill = str(order.get('fulfillment_type') or '').upper()
    items = list(order.get('line_items') or [])
    arabic = _item_arabic_names([str(item.get('item_code') or '') for item in items])
    for item in items:
        qty = _money(item.get('quantity'))
        item['quantity'] = int(qty) if qty == int(qty) else qty
        item['unit_price'] = _money(item.get('unit_price'))
        item['line_total'] = _money(item.get('line_total'))
        item['item_name_ar'] = arabic.get(str(item.get('item_code') or '').strip(), '')
    item_count = sum(int(item.get('quantity') or 0) or 1 for item in items) or len(items)
    pay_en, pay_ar = _receipt_payment_labels(order)
    order['receipt_store'] = store_name
    order['receipt_location'] = loc_name or store_address
    order['receipt_store_line'] = _receipt_store_line(store_name, loc_name or store_address)
    order['receipt_when'] = _when(order.get('created_at'))
    order['receipt_fulfillment'] = 'Delivery Order' if fulfill == 'DELIVERY' else 'Pickup Order'
    order['receipt_fulfillment_ar'] = 'طلب توصيل' if fulfill == 'DELIVERY' else 'طلب استلام'
    order['receipt_payment'] = pay_en
    order['receipt_payment_ar'] = pay_ar
    order['receipt_item_count'] = item_count
    order['receipt_item_count_ar'] = f'{item_count} عنصر' if item_count == 1 else f'{item_count} عناصر'
    order['receipt_qr'] = receipt_qr.qr_svg(str(order.get('order_number') or order_id))
    order['receipt_logo'] = _receipt_logo_url()
    order['line_items'] = items
    return order


def _receipt_store_line(store_name: str, location: str) -> str:
    store = (store_name or 'MamaHub').strip()
    loc = (location or '').strip()
    if loc and loc.lower() not in store.lower():
        return f'{store} - {loc}'
    return store


def _receipt_location_name() -> str:
    try:
        from db import get_location_info_by_dbkey
        info = get_location_info_by_dbkey(None) or {}
        return str(info.get('locationname') or info.get('location_name') or '').strip()
    except Exception:
        return ''


def _receipt_logo_url() -> str:
    try:
        rows, _ = media_db.list_media(placement='storefront_logo', active_only=True)
        if not rows:
            rows, _ = media_db.list_media(placement='storefront_logo', active_only=False)
    except Exception:
        rows = []
    url = str((rows[0] or {}).get('image_url') or '').strip() if rows else ''
    filename = media_svc.preview_filename(url)
    if filename:
        return f'/ecommerce/media/files/{filename}'
    if url.lower().startswith(('http://', 'https://')):
        return url
    return ''


def _receipt_payment_labels(order: Dict[str, Any]) -> Tuple[str, str]:
    method = ''
    for row in order.get('status_history') or []:
        notes = str(row.get('status_notes') or '')
        if 'order placed' not in notes.lower():
            continue
        rest = notes.replace('—', '-').split('-', 1)[-1].strip()
        token = rest.split()[0].strip().upper() if rest else ''
        if token:
            method = token
            break
    if method in _PAYMENT_LABELS:
        return _PAYMENT_LABELS[method]
    if method:
        label = method.replace('_', ' ').title()
        return label, label
    status = str(order.get('payment_status') or '').upper()
    if status == 'PAID':
        return _PAYMENT_LABELS['TAP']
    if status == 'PENDING':
        return _PAYMENT_LABELS['COD']
    return (status.replace('_', ' ').title() or '—', '')


def _item_arabic_names(codes: List[str]) -> Dict[str, str]:
    ints: List[int] = []
    for raw in codes:
        try:
            ints.append(int(raw))
        except (TypeError, ValueError):
            continue
    ints = list(dict.fromkeys(ints))
    if not ints:
        return {}
    loc = resolve_location_code()
    names: Dict[str, str] = {}
    chunk_size = 80
    for start in range(0, len(ints), chunk_size):
        chunk = ints[start:start + chunk_size]
        placeholders = ','.join(f':c{i}' for i in range(len(chunk)))
        params: Dict[str, Any] = {f'c{i}': chunk[i] for i in range(len(chunk))}
        params['loc'] = loc
        found = []
        for sql in (
            f"""
            SELECT ITEMCODE AS item_code, ITEMNAMEARA AS item_name_ar
            FROM ITEMMASTER
            WHERE LOCATIONCODE = :loc AND ITEMCODE IN ({placeholders})
            """,
            f"""
            SELECT ITEMCODE AS item_code, CAST(NULL AS VARCHAR2(500)) AS item_name_ar
            FROM ITEMMASTER
            WHERE LOCATIONCODE = :loc AND ITEMCODE IN ({placeholders})
            """,
        ):
            try:
                found = _safe_rows(sql, params)
                break
            except Exception:
                found = []
        for row in found:
            code = str(row.get('item_code') or '').strip()
            name = str(row.get('item_name_ar') or '').strip()
            if code and name:
                names[code] = name
    return names


def change_order_status(
    order_id: int,
    status: str,
    *,
    notes: Optional[str] = None,
    updated_by: Optional[int] = None,
) -> Tuple[bool, str]:
    before = orders_db.get_order(order_id)
    ok, message = orders_db.update_order_status(
        order_id,
        status,
        notes=notes,
        updated_by=updated_by,
    )
    if ok and before:
        previous = str(before.get('order_status') or '').upper()
        new_status = (status or '').strip().upper()
        if previous != new_status:
            snapshot = dict(before)
            threading.Thread(
                target=_notify_status_later,
                args=(snapshot, new_status),
                daemon=True,
            ).start()
    return ok, message


def _notify_status_later(order: Dict[str, Any], new_status: str) -> None:
    try:
        from storefront_backend.services import order_notifications as notify_svc
        notify_svc.send_order_status_notifications(order, new_status)
    except Exception:
        logger.exception('Background order status notify failed')


def remove_uninvoiced_order(order_id: int) -> Tuple[bool, str]:
    return orders_db.delete_uninvoiced_order(order_id)


def create_sales_invoice(
    order_id: int,
    *,
    created_by: Optional[str] = None,
    updated_by: Optional[int] = None,
) -> Dict[str, Any]:
    return order_invoice_svc.create_sales_invoice_for_order(
        order_id,
        created_by=created_by,
        updated_by=updated_by,
    )


def live_orders_payload(*, search: Optional[str] = None) -> Dict[str, Any]:
    rows, warning = orders_db.list_live_orders(search=search)
    catalog = _live_item_catalog(rows)
    orders = [_serialize_live_order(row, catalog) for row in rows]
    counts = {'needs_action': 0, 'preparing': 0, 'ready': 0}
    for order in orders:
        bucket = str(order.get('bucket') or '')
        if bucket in counts:
            counts[bucket] += 1
    settings = settings_store.load_store_settings()
    alert = orders_db.latest_order_alert()
    return {
        'orders': orders,
        'counts': counts,
        'store_name': str(settings.get('store_name') or 'MamaHub'),
        'accepting_orders': bool(settings.get('checkout_enabled', True)),
        'latest_id': int(alert.get('latest_id') or 0),
        'latest_number': str(alert.get('latest_number') or ''),
        'tables_ready': orders_db.orders_tables_ready(),
        'warning': warning,
    }


def _money(value: Any) -> float:
    try:
        if isinstance(value, Decimal):
            return float(round(value, 2))
        return round(float(value or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def _when(value: Any) -> str:
    if value is None:
        return ''
    if hasattr(value, 'strftime'):
        try:
            return value.strftime('%Y-%m-%d %H:%M:%S')
        except (TypeError, ValueError):
            pass
    return str(value)[:19].replace('T', ' ')


def _customer_display_name(order: Dict[str, Any]) -> str:
    name = ' '.join(
        part
        for part in (
            str(order.get('customer_first_name') or '').strip(),
            str(order.get('customer_last_name') or '').strip(),
        )
        if part
    ).strip()
    if name:
        return name
    email = str(order.get('customer_email') or '').strip()
    if email and '@' in email:
        return email.split('@', 1)[0]
    return email or 'Guest'


def _live_actions(order: Dict[str, Any]) -> List[Dict[str, str]]:
    status = str(order.get('order_status') or '').upper()
    fulfill = str(order.get('fulfillment_type') or 'DELIVERY').upper()
    actions: List[Dict[str, str]] = []
    if status == 'CONFIRMED':
        actions.append({'label': 'Accept order', 'status': 'PROCESSING', 'kind': 'primary'})
    elif status in ('PROCESSING', 'PICKING'):
        actions.append({'label': 'Mark ready', 'status': 'PACKED', 'kind': 'primary'})
    elif status == 'PACKED':
        if fulfill == 'PICKUP':
            actions.append({'label': 'Handed over', 'status': 'DELIVERED', 'kind': 'primary'})
        else:
            actions.append({'label': 'Out for delivery', 'status': 'OUT_FOR_DELIVERY', 'kind': 'primary'})
    if status not in ('CANCELLED', 'DELIVERED'):
        actions.append({
            'label': 'Out of stock',
            'status': 'CANCELLED',
            'kind': 'danger',
            'notes': 'Out of stock',
        })
        actions.append({'label': 'Cancel', 'status': 'CANCELLED', 'kind': 'ghost'})
    return actions


def _live_item_catalog(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    codes: List[int] = []
    for row in rows:
        for item in row.get('line_items') or []:
            raw = item.get('item_code')
            try:
                codes.append(int(raw))
            except (TypeError, ValueError):
                continue
    codes = list(dict.fromkeys(codes))
    if not codes:
        return {}
    loc = resolve_location_code()
    catalog: Dict[str, Dict[str, Any]] = {}
    chunk_size = 80
    for start in range(0, len(codes), chunk_size):
        chunk = codes[start:start + chunk_size]
        placeholders = ','.join(f':c{i}' for i in range(len(chunk)))
        params: Dict[str, Any] = {f'c{i}': chunk[i] for i in range(len(chunk))}
        params['loc'] = loc
        found = []
        queries = (
            f"""
            SELECT ITEMCODE AS item_code, IMAGE_PATH AS image_path, MANUFACTURERID AS barcode
            FROM ITEMMASTER
            WHERE LOCATIONCODE = :loc AND ITEMCODE IN ({placeholders})
            """,
            f"""
            SELECT ITEMCODE AS item_code, IMAGE_PATH AS image_path, CAST(NULL AS VARCHAR2(50)) AS barcode
            FROM ITEMMASTER
            WHERE LOCATIONCODE = :loc AND ITEMCODE IN ({placeholders})
            """,
            f"""
            SELECT ITEMCODE AS item_code, CAST(NULL AS VARCHAR2(500)) AS image_path, CAST(NULL AS VARCHAR2(50)) AS barcode
            FROM ITEMMASTER
            WHERE LOCATIONCODE = :loc AND ITEMCODE IN ({placeholders})
            """,
        )
        for sql in queries:
            try:
                found = _safe_rows(sql, params)
                break
            except Exception:
                found = []
        for row in found:
            code = str(row.get('item_code') or '').strip()
            if not code:
                continue
            image_path = str(row.get('image_path') or '').strip()
            catalog[code] = {
                'image_url': product_edit_svc.product_image_public_url(image_path) if image_path else None,
                'barcode': str(row.get('barcode') or '').strip(),
            }
    return catalog


def _serialize_live_order(row: Dict[str, Any], catalog: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    status = str(row.get('order_status') or '').upper()
    fulfill = str(row.get('fulfillment_type') or 'DELIVERY').upper()
    wrap, remaining_notes = gift_wrap_svc.split_notes(row.get('customer_notes'))
    items: List[Dict[str, Any]] = []
    for item in row.get('line_items') or []:
        code = str(item.get('item_code') or '').strip()
        extra = catalog.get(code) or {}
        qty = _money(item.get('quantity'))
        items.append({
            'order_item_id': item.get('order_item_id'),
            'item_code': code,
            'item_name': str(item.get('item_name') or 'Item'),
            'quantity': int(qty) if qty == int(qty) else qty,
            'unit_price': _money(item.get('unit_price')),
            'line_total': _money(item.get('line_total')),
            'image_url': extra.get('image_url'),
            'barcode': extra.get('barcode') or code,
        })
    return {
        'order_id': int(row.get('order_id') or 0),
        'order_number': str(row.get('order_number') or ''),
        'order_status': status,
        'bucket': _LIVE_BUCKETS.get(status, ''),
        'badge': _LIVE_BADGES.get(status, status.replace('_', ' ').title()),
        'payment_status': str(row.get('payment_status') or '').upper(),
        'fulfillment_type': fulfill,
        'fulfillment_label': 'Pickup order' if fulfill == 'PICKUP' else 'Delivery order',
        'currency_code': str(row.get('currency_code') or 'QAR'),
        'subtotal': _money(row.get('subtotal')),
        'discount_total': _money(row.get('discount_total')),
        'tax_total': _money(row.get('tax_total')),
        'delivery_fee': _money(row.get('delivery_fee')),
        'grand_total': _money(row.get('grand_total')),
        'item_count': int(row.get('item_count') or len(items) or 0),
        'created_at': _when(row.get('created_at')),
        'created_by_name': str(row.get('created_by_name') or 'Website'),
        **order_channel(row.get('created_by_name')),
        'customer_name': _customer_display_name(row),
        'customer_email': str(row.get('customer_email') or ''),
        'customer_phone': str(row.get('customer_mobile') or '').strip(),
        'address': order_invoice_svc._format_address(row.get('address_snapshot')),
        'customer_notes': remaining_notes,
        'gift_wrap': wrap,
        'items': items,
        'actions': _live_actions(row),
        'driver_label': 'Looking for a driver…' if fulfill == 'DELIVERY' else '',
    }
