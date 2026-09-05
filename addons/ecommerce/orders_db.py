"""MH_ORDER queries for the ecommerce addon."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from db import _get_connection, _safe_rows, _table_exists

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


def orders_tables_ready() -> bool:
    return _table_exists(ORDER_TABLE)


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


def list_orders(
    *,
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    search: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], int, Optional[str]]:
    if not orders_tables_ready():
        return [], 0, _table_missing_message()

    page = max(1, int(page or 1))
    page_size = max(1, min(int(page_size or 20), 100))
    offset = (page - 1) * page_size

    where = ['1=1']
    params: Dict[str, Any] = {
        'max_row': offset + page_size,
        'min_row': offset,
    }
    if status:
        where.append('o.ORDER_STATUS = :status')
        params['status'] = status.strip().upper()
    if search:
        where.append(
            "(UPPER(o.ORDER_NUMBER) LIKE :search OR UPPER(NVL(u.EMAIL, '')) LIKE :search)"
        )
        params['search'] = f'%{search.strip().upper()}%'

    where_sql = ' AND '.join(where)
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
                    u.EMAIL AS customer_email,
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
            o.CREATED_AT AS created_at,
            u.EMAIL AS customer_email,
            u.FIRST_NAME AS customer_first_name,
            u.LAST_NAME AS customer_last_name
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
        'SELECT ORDER_ID FROM MH_ORDER WHERE ORDER_ID = :order_id',
        {'order_id': int(order_id)},
    )
    if not existing:
        return False, 'Order not found'

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
