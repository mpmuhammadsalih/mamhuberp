"""MH_ORDER queries for the ecommerce addon."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from db import _get_connection, _safe_rows, _table_exists

from addons.ecommerce.schema_bootstrap import ensure_order_erp_columns
from storefront_backend.services import gift_wrap as gift_wrap_svc

ORDER_TABLE = 'MH_ORDER'
ITEM_TABLE = 'MH_ORDER_ITEM'
HISTORY_TABLE = 'MH_ORDER_STATUS_HISTORY'

ALLOWED_STATUSES = frozenset({
    'CONFIRMED',
    'PROCESSING',
    'PICKING',
    'PACKED',
    'OUT_FOR_DELIVERY',
    'DELIVERED',
    'CANCELLED',
})

LIVE_BOARD_STATUSES = ('CONFIRMED', 'PROCESSING', 'PICKING', 'PACKED')


def orders_tables_ready() -> bool:
    ready = _table_exists(ORDER_TABLE)
    if ready:
        ensure_order_erp_columns()
    return ready


def _table_missing_message() -> str:
    return (
        'MH_ORDER tables are not installed in this database. '
        'Run MamaHub schema script sql/02_tables/10_mh_orders.sql (create-if-missing) on the tenant DB.'
    )


def order_dashboard_stats() -> Dict[str, Any]:
    if not orders_tables_ready():
        return {'total_orders': 0, 'open_orders': 0, 'orders_today': 0}
    rows = _safe_rows(
        """
        SELECT
            COUNT(*) AS total_orders,
            SUM(CASE WHEN ORDER_STATUS NOT IN ('DELIVERED', 'CANCELLED') THEN 1 ELSE 0 END) AS open_orders,
            SUM(CASE WHEN TRUNC(CREATED_AT) = TRUNC(SYSTIMESTAMP) THEN 1 ELSE 0 END) AS orders_today
        FROM MH_ORDER
        """,
        {},
    )
    row = rows[0] if rows else {}
    return {
        'total_orders': int(row.get('total_orders') or 0),
        'open_orders': int(row.get('open_orders') or 0),
        'orders_today': int(row.get('orders_today') or 0),
    }


HISTORY_TAB_STATUSES = {
    'preparing': ('CONFIRMED', 'PROCESSING', 'PICKING', 'OUT_FOR_DELIVERY'),
    'ready': ('PACKED',),
    'delivered': ('DELIVERED',),
    'cancelled': ('CANCELLED',),
}


def _orders_where(
    *,
    status: Optional[str] = None,
    tab: Optional[str] = None,
    search: Optional[str] = None,
    period: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    channel: Optional[str] = None,
) -> Tuple[str, Dict[str, Any]]:
    where = ['1=1']
    params: Dict[str, Any] = {}
    period_sql = _history_period_sql(period, date_from, date_to, params)
    if period_sql:
        where.append(period_sql)
    tab_key = (tab or '').strip().lower()
    statuses = HISTORY_TAB_STATUSES.get(tab_key)
    if statuses:
        where.append(
            'o.ORDER_STATUS IN (' + ', '.join(f"'{item}'" for item in statuses) + ')'
        )
    elif status:
        where.append('o.ORDER_STATUS = :status')
        params['status'] = status.strip().upper()
    if search:
        where.append(
            "("
            "UPPER(o.ORDER_NUMBER) LIKE :search "
            "OR UPPER(NVL(u.EMAIL, '')) LIKE :search "
            "OR UPPER(NVL(u.FIRST_NAME, '')) LIKE :search "
            "OR UPPER(NVL(u.LAST_NAME, '')) LIKE :search"
            ")"
        )
        params['search'] = f'%{search.strip().upper()}%'
    channel_key = (channel or '').strip().lower()
    if channel_key == 'whatsapp':
        where.append("UPPER(NVL(o.CREATED_BY_NAME, 'Website')) LIKE '%WHATSAPP%'")
    elif channel_key == 'web':
        where.append("UPPER(NVL(o.CREATED_BY_NAME, 'Website')) NOT LIKE '%WHATSAPP%'")
    return ' AND '.join(where), params


def _history_period_sql(
    period: Optional[str],
    date_from: Optional[str],
    date_to: Optional[str],
    params: Dict[str, Any],
) -> Optional[str]:
    key = (period or 'today').strip().lower()
    col = 'TRUNC(o.CREATED_AT)'
    if key in ('all', 'any'):
        return None
    if key == 'yesterday':
        return f'{col} = TRUNC(SYSTIMESTAMP) - 1'
    if key in ('last_7', '7d', 'week'):
        return f'{col} >= TRUNC(SYSTIMESTAMP) - 6'
    if key in ('last_30', '30d', 'month'):
        return f'{col} >= TRUNC(SYSTIMESTAMP) - 29'
    if key in ('last_180', '6m', '6months'):
        return f'{col} >= ADD_MONTHS(TRUNC(SYSTIMESTAMP), -6)'
    if key == 'custom':
        parts: List[str] = []
        start = (date_from or '').strip()[:10]
        end = (date_to or '').strip()[:10]
        if start:
            params['date_from'] = start
            parts.append(f"{col} >= TO_DATE(:date_from, 'YYYY-MM-DD')")
        if end:
            params['date_to'] = end
            parts.append(f"{col} <= TO_DATE(:date_to, 'YYYY-MM-DD')")
        return ' AND '.join(parts) if parts else None
    return f'{col} = TRUNC(SYSTIMESTAMP)'


def order_history_stats(
    *,
    period: Optional[str] = 'today',
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    channel: Optional[str] = None,
) -> Dict[str, Any]:
    empty = {
        'total_orders': 0,
        'completed_orders': 0,
        'in_progress_orders': 0,
        'cancelled_orders': 0,
        'cancellation_rate': 0.0,
        'total_amount': 0.0,
        'completed_amount': 0.0,
        'in_progress_amount': 0.0,
        'cancelled_amount': 0.0,
    }
    if not orders_tables_ready():
        return empty
    where_sql, params = _orders_where(
        period=period,
        date_from=date_from,
        date_to=date_to,
        channel=channel,
    )
    rows = _safe_rows(
        f"""
        SELECT
            COUNT(*) AS total_orders,
            SUM(CASE WHEN o.ORDER_STATUS = 'DELIVERED' THEN 1 ELSE 0 END) AS completed_orders,
            SUM(CASE WHEN o.ORDER_STATUS NOT IN ('DELIVERED', 'CANCELLED') THEN 1 ELSE 0 END) AS in_progress_orders,
            SUM(CASE WHEN o.ORDER_STATUS = 'CANCELLED' THEN 1 ELSE 0 END) AS cancelled_orders,
            NVL(SUM(o.GRAND_TOTAL), 0) AS total_amount,
            NVL(SUM(CASE WHEN o.ORDER_STATUS = 'DELIVERED' THEN o.GRAND_TOTAL ELSE 0 END), 0) AS completed_amount,
            NVL(SUM(CASE WHEN o.ORDER_STATUS NOT IN ('DELIVERED', 'CANCELLED') THEN o.GRAND_TOTAL ELSE 0 END), 0) AS in_progress_amount,
            NVL(SUM(CASE WHEN o.ORDER_STATUS = 'CANCELLED' THEN o.GRAND_TOTAL ELSE 0 END), 0) AS cancelled_amount
        FROM MH_ORDER o
        WHERE {where_sql}
        """,
        params,
    )
    row = rows[0] if rows else {}
    total = int(row.get('total_orders') or 0)
    cancelled = int(row.get('cancelled_orders') or 0)
    rate = round((cancelled / total) * 100, 1) if total else 0.0

    def _amt(key: str) -> float:
        try:
            return round(float(row.get(key) or 0), 2)
        except (TypeError, ValueError):
            return 0.0

    return {
        'total_orders': total,
        'completed_orders': int(row.get('completed_orders') or 0),
        'in_progress_orders': int(row.get('in_progress_orders') or 0),
        'cancelled_orders': cancelled,
        'cancellation_rate': rate,
        'total_amount': _amt('total_amount'),
        'completed_amount': _amt('completed_amount'),
        'in_progress_amount': _amt('in_progress_amount'),
        'cancelled_amount': _amt('cancelled_amount'),
    }


def list_orders(
    *,
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    tab: Optional[str] = None,
    search: Optional[str] = None,
    period: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    channel: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], int, Optional[str]]:
    if not orders_tables_ready():
        return [], 0, _table_missing_message()

    page = max(1, int(page or 1))
    page_size = max(1, min(int(page_size or 20), 2000))
    offset = (page - 1) * page_size

    where_sql, params = _orders_where(
        status=status,
        tab=tab,
        search=search,
        period=period,
        date_from=date_from,
        date_to=date_to,
        channel=channel,
    )
    params['max_row'] = offset + page_size
    params['min_row'] = offset
    count_rows = _safe_rows(
        f"""
        SELECT COUNT(*) AS cnt
        FROM MH_ORDER o
        LEFT JOIN APP_USER u ON u.USER_ID = o.USER_ID
        WHERE {where_sql}
        """,
        params,
    )
    total = int(count_rows[0]['cnt']) if count_rows else 0

    rows = _safe_rows(
        f"""
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
                    NVL(o.CREATED_BY_NAME, 'Website') AS created_by_name,
                    o.ERP_BILLNO AS erp_billno,
                    o.LOCATION_CODE AS location_code,
                    u.EMAIL AS customer_email,
                    u.FIRST_NAME AS customer_first_name,
                    u.LAST_NAME AS customer_last_name,
                    (SELECT COUNT(*) FROM MH_ORDER_ITEM oi WHERE oi.ORDER_ID = o.ORDER_ID) AS item_count
                FROM MH_ORDER o
                LEFT JOIN APP_USER u ON u.USER_ID = o.USER_ID
                WHERE {where_sql}
                ORDER BY o.ORDER_ID DESC
            ) inner_q
            WHERE ROWNUM <= :max_row
        )
        WHERE rnum > :min_row
        """,
        params,
    )
    return rows, total, None


def latest_order_alert() -> Dict[str, Any]:
    """Newest unaccepted order for ERP sound. Alert stops when no CONFIRMED orders remain."""
    empty = {
        'latest_id': 0,
        'latest_number': '',
        'total': 0,
        'pending_count': 0,
        'alert_active': False,
    }
    if not orders_tables_ready():
        return empty
    rows = _safe_rows(
        """
        SELECT * FROM (
            SELECT ORDER_ID AS order_id, ORDER_NUMBER AS order_number
            FROM MH_ORDER
            WHERE UPPER(TRIM(ORDER_STATUS)) = 'CONFIRMED'
            ORDER BY ORDER_ID DESC
        ) WHERE ROWNUM = 1
        """,
        {},
    )
    count_rows = _safe_rows(
        """
        SELECT COUNT(*) AS cnt
        FROM MH_ORDER
        WHERE UPPER(TRIM(ORDER_STATUS)) = 'CONFIRMED'
        """,
        {},
    )
    pending = int(count_rows[0]['cnt']) if count_rows else 0
    row = rows[0] if rows else {}
    latest_id = int(row.get('order_id') or 0)
    return {
        'latest_id': latest_id,
        'latest_number': str(row.get('order_number') or ''),
        'total': pending,
        'pending_count': pending,
        'alert_active': pending > 0,
    }


def list_live_orders(*, search: Optional[str] = None, limit: int = 200) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Open kitchen-board orders: needs action, preparing, ready."""
    if not orders_tables_ready():
        return [], _table_missing_message()

    limit = max(1, min(int(limit or 200), 400))
    where = ["o.ORDER_STATUS IN ('CONFIRMED', 'PROCESSING', 'PICKING', 'PACKED')"]
    params: Dict[str, Any] = {'max_row': limit}
    if search:
        where.append(
            "("
            "UPPER(o.ORDER_NUMBER) LIKE :search "
            "OR UPPER(NVL(u.EMAIL, '')) LIKE :search "
            "OR UPPER(NVL(u.FIRST_NAME, '')) LIKE :search "
            "OR UPPER(NVL(u.LAST_NAME, '')) LIKE :search "
            "OR UPPER(NVL(u.MOBILE, '')) LIKE :search"
            ")"
        )
        params['search'] = f'%{search.strip().upper()}%'

    where_sql = ' AND '.join(where)
    rows = _safe_rows(
        f"""
        SELECT * FROM (
            SELECT
                o.ORDER_ID AS order_id,
                o.ORDER_NUMBER AS order_number,
                o.ORDER_STATUS AS order_status,
                o.PAYMENT_STATUS AS payment_status,
                o.FULFILLMENT_TYPE AS fulfillment_type,
                o.SUBTOTAL AS subtotal,
                o.DISCOUNT_TOTAL AS discount_total,
                o.TAX_TOTAL AS tax_total,
                o.DELIVERY_FEE AS delivery_fee,
                o.GRAND_TOTAL AS grand_total,
                o.CURRENCY_CODE AS currency_code,
                o.CUSTOMER_NOTES AS customer_notes,
                o.ADDRESS_SNAPSHOT AS address_snapshot,
                o.CREATED_AT AS created_at,
                NVL(o.CREATED_BY_NAME, 'Website') AS created_by_name,
                o.LOCATION_CODE AS location_code,
                u.EMAIL AS customer_email,
                u.FIRST_NAME AS customer_first_name,
                u.LAST_NAME AS customer_last_name,
                u.MOBILE AS customer_mobile,
                (SELECT COUNT(*) FROM MH_ORDER_ITEM oi WHERE oi.ORDER_ID = o.ORDER_ID) AS item_count
            FROM MH_ORDER o
            LEFT JOIN APP_USER u ON u.USER_ID = o.USER_ID
            WHERE {where_sql}
            ORDER BY o.ORDER_ID DESC
        )
        WHERE ROWNUM <= :max_row
        """,
        params,
    )
    if not rows:
        return [], None

    ids = [int(row['order_id']) for row in rows if row.get('order_id') is not None]
    if not ids:
        return rows, None

    placeholders = ','.join(f':oid{i}' for i in range(len(ids)))
    item_params = {f'oid{i}': ids[i] for i in range(len(ids))}
    items = _safe_rows(
        f"""
        SELECT
            ORDER_ID AS order_id,
            ORDER_ITEM_ID AS order_item_id,
            ITEM_CODE AS item_code,
            ITEM_NAME AS item_name,
            QUANTITY AS quantity,
            UNIT_PRICE AS unit_price,
            DISCOUNT_AMOUNT AS discount_amount,
            LINE_TOTAL AS line_total
        FROM MH_ORDER_ITEM
        WHERE ORDER_ID IN ({placeholders})
        ORDER BY ORDER_ITEM_ID
        """,
        item_params,
    )
    by_order: Dict[int, List[Dict[str, Any]]] = {oid: [] for oid in ids}
    for item in items:
        try:
            oid = int(item.get('order_id'))
        except (TypeError, ValueError):
            continue
        by_order.setdefault(oid, []).append(item)
    for row in rows:
        try:
            oid = int(row.get('order_id'))
        except (TypeError, ValueError):
            row['line_items'] = []
            continue
        row['line_items'] = by_order.get(oid, [])
    return rows, None


def get_order(order_id: int) -> Optional[Dict[str, Any]]:
    if not orders_tables_ready():
        return None
    headers = _safe_rows(
        """
        SELECT
            o.ORDER_ID AS order_id,
            o.ORDER_NUMBER AS order_number,
            o.ORDER_STATUS AS order_status,
            o.PAYMENT_STATUS AS payment_status,
            o.FULFILLMENT_TYPE AS fulfillment_type,
            o.SUBTOTAL AS subtotal,
            o.DISCOUNT_TOTAL AS discount_total,
            o.TAX_TOTAL AS tax_total,
            o.DELIVERY_FEE AS delivery_fee,
            o.GRAND_TOTAL AS grand_total,
            o.CURRENCY_CODE AS currency_code,
            o.COUPON_CODE AS coupon_code,
            o.CUSTOMER_NOTES AS customer_notes,
            o.LOCATION_CODE AS location_code,
            o.USER_ID AS user_id,
            o.ADDRESS_SNAPSHOT AS address_snapshot,
            o.CREATED_AT AS created_at,
            NVL(o.CREATED_BY_NAME, 'Website') AS created_by_name,
            o.ERP_BILLNO AS erp_billno,
            o.ERP_INVOICED_AT AS erp_invoiced_at,
            o.ERP_INVOICED_BY AS erp_invoiced_by,
            u.EMAIL AS customer_email,
            u.FIRST_NAME AS customer_first_name,
            u.LAST_NAME AS customer_last_name,
            u.MOBILE AS customer_mobile
        FROM MH_ORDER o
        LEFT JOIN APP_USER u ON u.USER_ID = o.USER_ID
        WHERE o.ORDER_ID = :order_id
        """,
        {'order_id': int(order_id)},
    )
    if not headers:
        return None
    order = dict(headers[0])
    order['line_items'] = _safe_rows(
        """
        SELECT
            ORDER_ITEM_ID AS order_item_id,
            ITEM_CODE AS item_code,
            ITEM_NAME AS item_name,
            QUANTITY AS quantity,
            UNIT_PRICE AS unit_price,
            DISCOUNT_AMOUNT AS discount_amount,
            LINE_TOTAL AS line_total
        FROM MH_ORDER_ITEM
        WHERE ORDER_ID = :order_id
        ORDER BY ORDER_ITEM_ID
        """,
        {'order_id': int(order_id)},
    )
    order['status_history'] = _safe_rows(
        """
        SELECT
            ORDER_STATUS AS order_status,
            STATUS_NOTES AS status_notes,
            CREATED_AT AS created_at
        FROM MH_ORDER_STATUS_HISTORY
        WHERE ORDER_ID = :order_id
        ORDER BY CREATED_AT DESC, STATUS_HISTORY_ID DESC
        """,
        {'order_id': int(order_id)},
    )
    wrap, remaining_notes = gift_wrap_svc.split_notes(order.get('customer_notes'))
    order['gift_wrap'] = wrap
    order['gift_wrap_fee'] = float((wrap or {}).get('fee') or 0)
    order['customer_notes'] = remaining_notes
    if not order.get('items'):
        order['items'] = order.get('line_items') or []
    return order


def update_order_status(
    order_id: int,
    status: str,
    *,
    notes: Optional[str] = None,
    updated_by: Optional[int] = None,
) -> Tuple[bool, str]:
    if not orders_tables_ready():
        return False, _table_missing_message()
    status_up = (status or '').strip().upper()
    if status_up not in ALLOWED_STATUSES:
        return False, f'Invalid status: {status_up}'

    existing = _safe_rows(
        'SELECT ORDER_ID AS order_id, ORDER_STATUS AS order_status FROM MH_ORDER WHERE ORDER_ID = :order_id',
        {'order_id': int(order_id)},
    )
    if not existing:
        return False, 'Order not found'
    previous = str(existing[0].get('order_status') or '').upper()
    if previous == status_up:
        return True, 'Order status updated'

    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE MH_ORDER
                    SET ORDER_STATUS = :status,
                        MODIFIED_AT = SYSTIMESTAMP,
                        MODIFIED_BY = :updated_by
                    WHERE ORDER_ID = :order_id
                    """,
                    {
                        'status': status_up,
                        'order_id': int(order_id),
                        'updated_by': updated_by,
                    },
                )
                cur.execute('SELECT SEQ_MH_ORDER_STATUS_ID.NEXTVAL AS id FROM DUAL')
                history_id = int((cur.fetchone() or [0])[0])
                cur.execute(
                    """
                    INSERT INTO MH_ORDER_STATUS_HISTORY (
                        STATUS_HISTORY_ID, ORDER_ID, ORDER_STATUS, STATUS_NOTES,
                        CREATED_AT, CREATED_BY
                    ) VALUES (
                        :history_id, :order_id, :status, :notes,
                        SYSTIMESTAMP, :created_by
                    )
                    """,
                    {
                        'history_id': history_id,
                        'order_id': int(order_id),
                        'status': status_up,
                        'notes': (notes or '').strip() or None,
                        'created_by': updated_by,
                    },
                )
            conn.commit()
        return True, 'Order status updated'
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def delete_uninvoiced_order(order_id: int) -> Tuple[bool, str]:
    """Permanently remove an MH_ORDER that has not been posted to BILLHDR."""
    if not orders_tables_ready():
        return False, _table_missing_message()
    order = get_order(int(order_id))
    if not order:
        return False, 'Order not found.'
    order_number = str(order.get('order_number') or '').strip()
    if str(order.get('erp_billno') or '').strip():
        return False, 'This order already has a sales invoice and cannot be removed.'
    loc = order.get('location_code')
    try:
        loc_int = int(loc) if loc is not None else 0
    except (TypeError, ValueError):
        loc_int = 0
    if loc_int and find_invoice_billno_for_order(loc_int, order_number):
        return False, 'This order already has a sales invoice and cannot be removed.'

    oid = int(order_id)
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                if _table_exists('MH_INVENTORY_RESERVATION'):
                    cur.execute(
                        """
                        UPDATE MH_INVENTORY_RESERVATION
                        SET RESERVATION_STATUS = 'RELEASED', ORDER_ID = NULL
                        WHERE ORDER_ID = :order_id
                        """,
                        {'order_id': oid},
                    )
                for table, sql in (
                    (
                        'MH_LOYALTY_TRANSACTION',
                        'UPDATE MH_LOYALTY_TRANSACTION SET ORDER_ID = NULL WHERE ORDER_ID = :order_id',
                    ),
                    (
                        'MH_COUPON_USAGE',
                        'UPDATE MH_COUPON_USAGE SET ORDER_ID = NULL WHERE ORDER_ID = :order_id',
                    ),
                    (
                        'MH_REVIEW',
                        'UPDATE MH_REVIEW SET ORDER_ID = NULL WHERE ORDER_ID = :order_id',
                    ),
                ):
                    if _table_exists(table):
                        try:
                            cur.execute(sql, {'order_id': oid})
                        except Exception:
                            pass
                cur.execute(
                    'DELETE FROM MH_ORDER_STATUS_HISTORY WHERE ORDER_ID = :order_id',
                    {'order_id': oid},
                )
                cur.execute(
                    'DELETE FROM MH_ORDER_ITEM WHERE ORDER_ID = :order_id',
                    {'order_id': oid},
                )
                cur.execute(
                    'DELETE FROM MH_ORDER WHERE ORDER_ID = :order_id',
                    {'order_id': oid},
                )
                if cur.rowcount == 0:
                    return False, 'Order not found.'
            conn.commit()
        return True, f'Removed order {order_number or oid}.'
    except Exception as exc:  # noqa: BLE001
        return False, str(exc) or 'Could not remove order.'


def find_invoice_billno_for_order(location_code: int, order_number: str) -> Optional[str]:
    """Look up an existing BILLHDR posted with this web order number."""
    order_no = str(order_number or '').strip()[:80]
    if not order_no:
        return None
    rows = _safe_rows(
        """
        SELECT BILLNO AS billno
        FROM BILLHDR
        WHERE LOCATIONCODE = :loc
          AND ORDERNO = :orderno
          AND NVL(DELFLAG, 'N') = 'N'
        ORDER BY BILLNO DESC
        FETCH FIRST 1 ROWS ONLY
        """,
        {'loc': int(location_code), 'orderno': order_no},
    )
    if not rows:
        return None
    billno = str(rows[0].get('billno') or rows[0].get('BILLNO') or '').strip()
    return billno or None


def mark_order_invoiced(
    order_id: int,
    billno: str,
    *,
    updated_by: Optional[int] = None,
    created_by_name: Optional[str] = None,
) -> Tuple[bool, str]:
    """Store ERP bill number on the web order and append status history."""
    if not orders_tables_ready():
        return False, _table_missing_message()
    invoice_no = str(billno or '').strip()[:40]
    if not invoice_no:
        return False, 'Invoice number is empty.'
    existing = get_order(int(order_id))
    if not existing:
        return False, 'Order not found'
    status_up = str(existing.get('order_status') or 'PROCESSING').strip().upper()
    note = f'Posted to ERP sales invoice {invoice_no}'
    by_name = str(created_by_name or '').strip()[:100] or None
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE MH_ORDER
                    SET ERP_BILLNO = :billno,
                        ERP_INVOICED_AT = SYSTIMESTAMP,
                        ERP_INVOICED_BY = :invoiced_by,
                        MODIFIED_AT = SYSTIMESTAMP,
                        MODIFIED_BY = :updated_by
                    WHERE ORDER_ID = :order_id
                    """,
                    {
                        'billno': invoice_no,
                        'invoiced_by': by_name,
                        'updated_by': updated_by,
                        'order_id': int(order_id),
                    },
                )
                cur.execute('SELECT SEQ_MH_ORDER_STATUS_ID.NEXTVAL AS id FROM DUAL')
                history_id = int((cur.fetchone() or [0])[0])
                cur.execute(
                    """
                    INSERT INTO MH_ORDER_STATUS_HISTORY (
                        STATUS_HISTORY_ID, ORDER_ID, ORDER_STATUS, STATUS_NOTES,
                        CREATED_AT, CREATED_BY
                    ) VALUES (
                        :history_id, :order_id, :status, :notes,
                        SYSTIMESTAMP, :created_by
                    )
                    """,
                    {
                        'history_id': history_id,
                        'order_id': int(order_id),
                        'status': status_up,
                        'notes': note,
                        'created_by': updated_by,
                    },
                )
            conn.commit()
        return True, note
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
