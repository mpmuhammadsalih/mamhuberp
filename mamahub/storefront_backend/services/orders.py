"""Customer order queries."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from db import _get_connection, _safe_rows, _table_exists

from storefront_backend.services.cart import _lookup_cart_product_meta
from storefront_backend.services.schema_bootstrap import ensure_order_schema
from storefront_backend.services import gift_wrap as gift_wrap_svc

try:
    from addons.ecommerce.schema_bootstrap import ensure_order_erp_columns
except ImportError:  # pragma: no cover
    ensure_order_erp_columns = None

CANCELLABLE = frozenset({'PENDING', 'AWAITING_PAYMENT', 'PAYMENT_CONFIRMED', 'CONFIRMED'})
_ORDER_SCHEMA_OK: bool | None = None


def _orders_ready() -> bool:
    global _ORDER_SCHEMA_OK
    if _ORDER_SCHEMA_OK is True:
        return True
    ensure_order_schema()
    if ensure_order_erp_columns is not None:
        try:
            ensure_order_erp_columns()
        except Exception:
            pass
    ready = _table_exists('MH_ORDER')
    _ORDER_SCHEMA_OK = ready
    return ready


def _next_id(sequence: str) -> int:
    ensure_order_schema()
    rows = _safe_rows(f'SELECT {sequence}.NEXTVAL AS id FROM DUAL', {})
    if not rows:
        raise ValueError(
            f'Database sequence {sequence} is missing. '
            'Order tables could not be initialized on this database.'
        )
    return int(rows[0]['id'])


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def generate_order_number() -> Tuple[str, int]:
    order_id = _next_id('SEQ_MH_ORDER_ID')
    return format_order_number(order_id), order_id


def format_order_number(order_id: int) -> str:
    return f'ORD-{datetime.now().year}-{int(order_id):06d}'


def allocate_order_id() -> int:
    if not _orders_ready():
        raise ValueError('Order tables not available')
    return _next_id('SEQ_MH_ORDER_ID')


def create_order_header(
    *,
    order_id: int,
    order_number: str,
    user_id: int,
    data: Dict[str, Any],
) -> None:
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO MH_ORDER (
                    ORDER_ID, ORDER_NUMBER, USER_ID, CART_ID, LOCATION_CODE,
                    ORDER_STATUS, FULFILLMENT_TYPE, PAYMENT_STATUS,
                    SUBTOTAL, DISCOUNT_TOTAL, TAX_TOTAL, DELIVERY_FEE, GRAND_TOTAL,
                    CURRENCY_CODE, COUPON_CODE, DELIVERY_ZONE_ID, DELIVERY_SLOT_ID,
                    PICKUP_STORE_ID, ADDRESS_ID, ADDRESS_SNAPSHOT, CUSTOMER_NOTES,
                    CREATED_AT, CREATED_BY, CREATED_BY_NAME
                ) VALUES (
                    :order_id, :order_number, :user_id, :cart_id, :location_code,
                    :order_status, :fulfillment_type, :payment_status,
                    :subtotal, :discount_total, :tax_total, :delivery_fee, :grand_total,
                    :currency_code, :coupon_code, :delivery_zone_id, :delivery_slot_id,
                    :pickup_store_id, :address_id, :address_snapshot, :customer_notes,
                    SYSTIMESTAMP, :created_by, :created_by_name
                )
                """,
                {
                    'order_id': order_id,
                    'order_number': order_number,
                    'user_id': user_id,
                    'created_by': user_id,
                    'created_by_name': data.pop('created_by_name', None) or 'Website',
                    **data,
                },
            )
        conn.commit()


def add_order_item(order_id: int, item: Dict[str, Any]) -> None:
    item_id = _next_id('SEQ_MH_ORDER_ITEM_ID')
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO MH_ORDER_ITEM (
                    ORDER_ITEM_ID, ORDER_ID, LOCATION_CODE, ITEM_CODE, ITEM_NAME,
                    QUANTITY, UNIT_PRICE, DISCOUNT_AMOUNT, LINE_TOTAL, CREATED_AT
                ) VALUES (
                    :order_item_id, :order_id, :location_code, :item_code, :item_name,
                    :quantity, :unit_price, :discount_amount, :line_total, SYSTIMESTAMP
                )
                """,
                {'order_item_id': item_id, 'order_id': order_id, **item},
            )
        conn.commit()


def add_status_history(
    order_id: int,
    status: str,
    *,
    notes: Optional[str] = None,
    created_by: Optional[int] = None,
) -> None:
    history_id = _next_id('SEQ_MH_ORDER_STATUS_ID')
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO MH_ORDER_STATUS_HISTORY (
                    STATUS_HISTORY_ID, ORDER_ID, ORDER_STATUS, STATUS_NOTES,
                    CREATED_AT, CREATED_BY
                ) VALUES (
                    :history_id, :order_id, :status, :notes, SYSTIMESTAMP, :created_by
                )
                """,
                {
                    'history_id': history_id,
                    'order_id': order_id,
                    'status': status,
                    'notes': notes,
                    'created_by': created_by,
                },
            )
        conn.commit()


def create_confirmed_order_batch(
    *,
    order_id: int,
    order_number: str,
    user_id: int,
    header: Dict[str, Any],
    items: List[Dict[str, Any]],
    status_notes: str,
    finalize_cart_id: Optional[int] = None,
) -> Tuple[str, int]:
    """Insert order header, line items, status history, and finalize cart in one transaction."""
    if not _orders_ready():
        raise ValueError('Order tables not available')
    if not items:
        raise ValueError('Order has no items')

    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO MH_ORDER (
                    ORDER_ID, ORDER_NUMBER, USER_ID, CART_ID, LOCATION_CODE,
                    ORDER_STATUS, FULFILLMENT_TYPE, PAYMENT_STATUS,
                    SUBTOTAL, DISCOUNT_TOTAL, TAX_TOTAL, DELIVERY_FEE, GRAND_TOTAL,
                    CURRENCY_CODE, COUPON_CODE, DELIVERY_ZONE_ID, DELIVERY_SLOT_ID,
                    PICKUP_STORE_ID, ADDRESS_ID, ADDRESS_SNAPSHOT, CUSTOMER_NOTES,
                    CREATED_AT, CREATED_BY, CREATED_BY_NAME
                ) VALUES (
                    :order_id, :order_number, :user_id, :cart_id, :location_code,
                    :order_status, :fulfillment_type, :payment_status,
                    :subtotal, :discount_total, :tax_total, :delivery_fee, :grand_total,
                    :currency_code, :coupon_code, :delivery_zone_id, :delivery_slot_id,
                    :pickup_store_id, :address_id, :address_snapshot, :customer_notes,
                    SYSTIMESTAMP, :created_by, :created_by_name
                )
                """,
                {
                    'order_id': order_id,
                    'order_number': order_number,
                    'user_id': user_id,
                    'created_by': user_id,
                    'created_by_name': header.pop('created_by_name', None) or 'Website',
                    **header,
                },
            )

            for item in items:
                cur.execute('SELECT SEQ_MH_ORDER_ITEM_ID.NEXTVAL FROM DUAL')
                item_id = int((cur.fetchone() or [0])[0])
                cur.execute(
                    """
                    INSERT INTO MH_ORDER_ITEM (
                        ORDER_ITEM_ID, ORDER_ID, LOCATION_CODE, ITEM_CODE, ITEM_NAME,
                        QUANTITY, UNIT_PRICE, DISCOUNT_AMOUNT, LINE_TOTAL, CREATED_AT
                    ) VALUES (
                        :order_item_id, :order_id, :location_code, :item_code, :item_name,
                        :quantity, :unit_price, :discount_amount, :line_total, SYSTIMESTAMP
                    )
                    """,
                    {'order_item_id': item_id, 'order_id': order_id, **item},
                )

            cur.execute('SELECT SEQ_MH_ORDER_STATUS_ID.NEXTVAL FROM DUAL')
            history_id = int((cur.fetchone() or [0])[0])
            cur.execute(
                """
                INSERT INTO MH_ORDER_STATUS_HISTORY (
                    STATUS_HISTORY_ID, ORDER_ID, ORDER_STATUS, STATUS_NOTES,
                    CREATED_AT, CREATED_BY
                ) VALUES (
                    :history_id, :order_id, :status, :notes, SYSTIMESTAMP, :created_by
                )
                """,
                {
                    'history_id': history_id,
                    'order_id': order_id,
                    'status': 'CONFIRMED',
                    'notes': status_notes,
                    'created_by': user_id,
                },
            )

            if finalize_cart_id is not None:
                if _table_exists('MH_INVENTORY_RESERVATION'):
                    cur.execute(
                        """
                        UPDATE MH_INVENTORY_RESERVATION
                        SET RESERVATION_STATUS = 'CONVERTED', ORDER_ID = :order_id
                        WHERE CART_ID = :cart_id AND RESERVATION_STATUS = 'ACTIVE'
                        """,
                        {'cart_id': int(finalize_cart_id), 'order_id': int(order_id)},
                    )
                cur.execute(
                    """
                    UPDATE MH_CART
                    SET CART_STATUS = 'ABANDONED', MODIFIED_AT = SYSTIMESTAMP
                    WHERE CART_ID = :cart_id
                    """,
                    {'cart_id': int(finalize_cart_id)},
                )
        conn.commit()

    return order_number, order_id


def _is_placeholder_item_name(name: Optional[str], item_code: int) -> bool:
    if not name or not str(name).strip():
        return True
    normalized = str(name).strip()
    if normalized.lower() == f'item {item_code}'.lower():
        return True
    parts = normalized.split()
    return len(parts) == 2 and parts[0].lower() == 'item' and parts[1] == str(item_code)


def _enrich_order_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not items:
        return items
    default_loc = int(items[0].get('location_code') or 1)
    meta = _lookup_cart_product_meta(items, default_location_code=default_loc)
    enriched: List[Dict[str, Any]] = []
    for item in items:
        row = dict(item)
        loc = int(row.get('location_code') or 1)
        code = int(row.get('item_code') or 0)
        details = meta.get((loc, code), {})
        name = row.get('item_name')
        if _is_placeholder_item_name(str(name) if name is not None else None, code):
            name = details.get('item_name') or name
        row['item_name'] = str(name or '').strip() or f'Item {code}'
        image = details.get('primary_image_url')
        if image:
            row['primary_image_url'] = image
        enriched.append(row)
    return enriched


def _fetch_items(order_id: int) -> List[Dict[str, Any]]:
    items = _safe_rows(
        """
        SELECT
            ORDER_ITEM_ID AS order_item_id,
            LOCATION_CODE AS location_code,
            ITEM_CODE AS item_code,
            ITEM_NAME AS item_name,
            QUANTITY AS quantity,
            UNIT_PRICE AS unit_price,
            LINE_TOTAL AS line_total
        FROM MH_ORDER_ITEM
        WHERE ORDER_ID = :order_id
        ORDER BY ORDER_ITEM_ID
        """,
        {'order_id': int(order_id)},
    )
    return _enrich_order_items(items)


def _fetch_history(order_id: int) -> List[Dict[str, Any]]:
    rows = _safe_rows(
        """
        SELECT
            ORDER_STATUS AS order_status,
            STATUS_NOTES AS status_notes,
            CREATED_AT AS created_at
        FROM MH_ORDER_STATUS_HISTORY
        WHERE ORDER_ID = :order_id
        ORDER BY CREATED_AT ASC, STATUS_HISTORY_ID ASC
        """,
        {'order_id': int(order_id)},
    )
    for row in rows:
        row['created_at'] = _iso(row.get('created_at'))
    return rows


def _to_summary(row: Dict[str, Any], *, item_count: Optional[int] = None) -> Dict[str, Any]:
    items = row.get('items')
    count = item_count
    if count is None and items is not None:
        count = len(items)
    return {
        'order_id': int(row['order_id']),
        'order_number': row.get('order_number'),
        'order_status': row.get('order_status'),
        'payment_status': row.get('payment_status'),
        'fulfillment_type': row.get('fulfillment_type'),
        'grand_total': float(row.get('grand_total') or 0),
        'currency_code': row.get('currency_code') or 'QAR',
        'item_count': int(count or 0),
        'created_at': _iso(row.get('created_at')),
    }


def _to_detail(row: Dict[str, Any]) -> Dict[str, Any]:
    items = row.get('items') or _fetch_items(int(row['order_id']))
    history = row.get('status_history') or _fetch_history(int(row['order_id']))
    summary = _to_summary(row, item_count=len(items))
    wrap, remaining_notes = gift_wrap_svc.split_notes(row.get('customer_notes'))
    summary.update({
        'subtotal': float(row.get('subtotal') or 0),
        'discount_total': float(row.get('discount_total') or 0),
        'tax_total': float(row.get('tax_total') or 0),
        'delivery_fee': float(row.get('delivery_fee') or 0),
        'coupon_code': row.get('coupon_code'),
        'customer_notes': remaining_notes,
        'gift_wrap': wrap,
        'gift_wrap_fee': float((wrap or {}).get('fee') or 0),
        'items': [
            {
                'order_item_id': int(i['order_item_id']),
                'item_code': int(i['item_code']),
                'item_name': i.get('item_name'),
                'primary_image_url': i.get('primary_image_url'),
                'quantity': float(i.get('quantity') or 0),
                'unit_price': float(i.get('unit_price') or 0),
                'line_total': float(i.get('line_total') or 0),
            }
            for i in items
        ],
        'status_history': history,
    })
    return summary


def _get_order_header(user_id: int, *, order_id: Optional[int] = None, order_number: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if not _orders_ready():
        return None
    if order_id is not None:
        rows = _safe_rows(
            """
            SELECT
                ORDER_ID AS order_id,
                ORDER_NUMBER AS order_number,
                ORDER_STATUS AS order_status,
                PAYMENT_STATUS AS payment_status,
                FULFILLMENT_TYPE AS fulfillment_type,
                SUBTOTAL AS subtotal,
                DISCOUNT_TOTAL AS discount_total,
                TAX_TOTAL AS tax_total,
                DELIVERY_FEE AS delivery_fee,
                GRAND_TOTAL AS grand_total,
                CURRENCY_CODE AS currency_code,
                COUPON_CODE AS coupon_code,
                CUSTOMER_NOTES AS customer_notes,
                CREATED_AT AS created_at
            FROM MH_ORDER
            WHERE ORDER_ID = :order_id AND USER_ID = :user_id
            """,
            {'order_id': int(order_id), 'user_id': int(user_id)},
        )
    else:
        rows = _safe_rows(
            """
            SELECT
                ORDER_ID AS order_id,
                ORDER_NUMBER AS order_number,
                ORDER_STATUS AS order_status,
                PAYMENT_STATUS AS payment_status,
                FULFILLMENT_TYPE AS fulfillment_type,
                SUBTOTAL AS subtotal,
                DISCOUNT_TOTAL AS discount_total,
                TAX_TOTAL AS tax_total,
                DELIVERY_FEE AS delivery_fee,
                GRAND_TOTAL AS grand_total,
                CURRENCY_CODE AS currency_code,
                COUPON_CODE AS coupon_code,
                CUSTOMER_NOTES AS customer_notes,
                CREATED_AT AS created_at
            FROM MH_ORDER
            WHERE ORDER_NUMBER = :order_number AND USER_ID = :user_id
            """,
            {'order_number': order_number, 'user_id': int(user_id)},
        )
    if not rows:
        return None
    order = dict(rows[0])
    order['items'] = _fetch_items(int(order['order_id']))
    order['status_history'] = _fetch_history(int(order['order_id']))
    return order


def list_orders(
    user_id: int,
    *,
    page: int = 1,
    page_size: int = 20,
) -> Tuple[List[Dict[str, Any]], int]:
    if not _orders_ready():
        return [], 0
    page = max(1, int(page))
    page_size = max(1, min(int(page_size), 100))
    offset = (page - 1) * page_size
    count_rows = _safe_rows(
        'SELECT COUNT(*) AS cnt FROM MH_ORDER WHERE USER_ID = :user_id',
        {'user_id': int(user_id)},
    )
    total = int(count_rows[0]['cnt']) if count_rows else 0
    rows = _safe_rows(
        """
        SELECT * FROM (
            SELECT inner_q.*, ROWNUM rnum FROM (
                SELECT
                    o.ORDER_ID AS order_id,
                    o.ORDER_NUMBER AS order_number,
                    o.ORDER_STATUS AS order_status,
                    o.PAYMENT_STATUS AS payment_status,
                    o.FULFILLMENT_TYPE AS fulfillment_type,
                    o.GRAND_TOTAL AS grand_total,
                    o.CURRENCY_CODE AS currency_code,
                    o.CREATED_AT AS created_at,
                    (SELECT COUNT(*) FROM MH_ORDER_ITEM oi WHERE oi.ORDER_ID = o.ORDER_ID) AS item_count
                FROM MH_ORDER o
                WHERE o.USER_ID = :user_id
                ORDER BY o.ORDER_ID DESC
            ) inner_q
            WHERE ROWNUM <= :max_row
        )
        WHERE rnum > :min_row
        """,
        {
            'user_id': int(user_id),
            'max_row': offset + page_size,
            'min_row': offset,
        },
    )
    summaries = [_to_summary(row, item_count=int(row.get('item_count') or 0)) for row in rows]
    return summaries, total


def get_order(user_id: int, order_id: int) -> Optional[Dict[str, Any]]:
    order = _get_order_header(user_id, order_id=order_id)
    return _to_detail(order) if order else None


def track_order(user_id: int, order_number: str) -> Optional[Dict[str, Any]]:
    order = _get_order_header(user_id, order_number=order_number)
    return _to_detail(order) if order else None


def cancel_order(
    user_id: int,
    order_id: int,
    *,
    reason: Optional[str] = None,
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    order = _get_order_header(user_id, order_id=order_id)
    if not order:
        return False, 'Order not found', None
    status = str(order.get('order_status') or '').upper()
    if status not in CANCELLABLE:
        return False, 'Order cannot be cancelled at this stage', None
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE MH_ORDER
                    SET ORDER_STATUS = 'CANCELLED',
                        MODIFIED_AT = SYSTIMESTAMP,
                        MODIFIED_BY = :user_id
                    WHERE ORDER_ID = :order_id AND USER_ID = :user_id
                    """,
                    {'order_id': int(order_id), 'user_id': int(user_id)},
                )
        add_status_history(order_id, 'CANCELLED', notes=reason, created_by=user_id)
        updated = get_order(user_id, order_id)
        return True, 'Order cancelled', updated
    except Exception as exc:  # noqa: BLE001
        return False, str(exc), None
