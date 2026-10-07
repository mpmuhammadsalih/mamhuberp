"""Ecommerce reporting queries."""
from __future__ import annotations

from typing import Any, Dict, List

from addons.ecommerce import customers_db
from addons.ecommerce import orders_db
from addons.ecommerce import promotions_db
from db import _safe_rows, get_items_kpis


def _orders_ready() -> bool:
    return orders_db.orders_tables_ready()


def sales_summary(*, location_code: int) -> Dict[str, Any]:
    if not _orders_ready():
        return {
            'total_orders': 0,
            'total_revenue': 0.0,
            'confirmed_orders': 0,
            'cancelled_orders': 0,
            'orders_today': 0,
            'revenue_today': 0.0,
        }
    rows = _safe_rows(
        """
        SELECT
            COUNT(*) AS total_orders,
            NVL(SUM(CASE WHEN ORDER_STATUS <> 'CANCELLED' THEN GRAND_TOTAL ELSE 0 END), 0) AS total_revenue,
            SUM(CASE WHEN ORDER_STATUS = 'CONFIRMED' THEN 1 ELSE 0 END) AS confirmed_orders,
            SUM(CASE WHEN ORDER_STATUS = 'CANCELLED' THEN 1 ELSE 0 END) AS cancelled_orders,
            SUM(CASE WHEN TRUNC(CREATED_AT) = TRUNC(SYSTIMESTAMP) THEN 1 ELSE 0 END) AS orders_today,
            NVL(SUM(CASE
                WHEN TRUNC(CREATED_AT) = TRUNC(SYSTIMESTAMP) AND ORDER_STATUS <> 'CANCELLED'
                THEN GRAND_TOTAL ELSE 0
            END), 0) AS revenue_today
        FROM MH_ORDER
        WHERE LOCATION_CODE = :location_code
        """,
        {'location_code': int(location_code)},
    )
    row = rows[0] if rows else {}
    return {
        'total_orders': int(row.get('total_orders') or 0),
        'total_revenue': float(row.get('total_revenue') or 0),
        'confirmed_orders': int(row.get('confirmed_orders') or 0),
        'cancelled_orders': int(row.get('cancelled_orders') or 0),
        'orders_today': int(row.get('orders_today') or 0),
        'revenue_today': float(row.get('revenue_today') or 0),
    }


def weekly_sales(*, location_code: int, days: int = 7) -> List[Dict[str, Any]]:
    if not _orders_ready():
        return []
    rows = _safe_rows(
        """
        SELECT
            TRUNC(CREATED_AT) AS day_date,
            TO_CHAR(CREATED_AT, 'Dy', 'NLS_DATE_LANGUAGE=ENGLISH') AS day_label,
            COUNT(*) AS order_count,
            NVL(SUM(CASE WHEN ORDER_STATUS <> 'CANCELLED' THEN GRAND_TOTAL ELSE 0 END), 0) AS revenue
        FROM MH_ORDER
        WHERE CREATED_AT >= TRUNC(SYSTIMESTAMP) - :days_back + 1
          AND LOCATION_CODE = :location_code
        GROUP BY TRUNC(CREATED_AT), TO_CHAR(CREATED_AT, 'Dy', 'NLS_DATE_LANGUAGE=ENGLISH')
        ORDER BY day_date
        """,
        {'days_back': max(1, int(days)), 'location_code': int(location_code)},
    )
    return [
        {
            'day_date': r.get('day_date'),
            'day_label': str(r.get('day_label') or '').strip(),
            'order_count': int(r.get('order_count') or 0),
            'revenue': float(r.get('revenue') or 0),
        }
        for r in rows
    ]


def category_mix(*, location_code: int, limit: int = 8) -> List[Dict[str, Any]]:
    if not _orders_ready():
        return []
    rows = _safe_rows(
        """
        SELECT * FROM (
            SELECT
                NVL(cat.NAME, 'Uncategorized') AS category_name,
                NVL(SUM(oi.LINE_TOTAL), 0) AS total_amount
            FROM MH_ORDER_ITEM oi
            JOIN MH_ORDER o ON o.ORDER_ID = oi.ORDER_ID
            LEFT JOIN ITEMMASTER im
                ON im.ITEMCODE = oi.ITEM_CODE
               AND im.LOCATIONCODE = o.LOCATION_CODE
            LEFT JOIN CATEGORY cat
                ON cat.CODE = im.CATEGORYCODE
               AND cat.FLAG = 'C'
            WHERE o.ORDER_STATUS <> 'CANCELLED'
              AND o.LOCATION_CODE = :location_code
            GROUP BY NVL(cat.NAME, 'Uncategorized')
            ORDER BY total_amount DESC
        )
        WHERE ROWNUM <= :limit
        """,
        {'location_code': int(location_code), 'limit': max(1, int(limit))},
    )
    total = sum(float(r.get('total_amount') or 0) for r in rows) or 1.0
    palette = ['#E91E63', '#60a5fa', '#34d399', '#fbbf24', '#a78bfa', '#fb7185', '#38bdf8', '#4ade80']
    result = []
    for idx, row in enumerate(rows):
        amount = float(row.get('total_amount') or 0)
        result.append({
            'category_name': row.get('category_name') or 'Uncategorized',
            'total_amount': amount,
            'share_pct': round((amount / total) * 100, 1),
            'color': palette[idx % len(palette)],
        })
    return result


def top_products(*, location_code: int, limit: int = 10) -> List[Dict[str, Any]]:
    if not _orders_ready():
        return []
    return _safe_rows(
        """
        SELECT * FROM (
            SELECT
                oi.ITEM_CODE AS item_code,
                oi.ITEM_NAME AS item_name,
                SUM(oi.QUANTITY) AS qty_sold,
                NVL(SUM(oi.LINE_TOTAL), 0) AS revenue
            FROM MH_ORDER_ITEM oi
            JOIN MH_ORDER o ON o.ORDER_ID = oi.ORDER_ID
            WHERE o.ORDER_STATUS <> 'CANCELLED'
              AND o.LOCATION_CODE = :location_code
            GROUP BY oi.ITEM_CODE, oi.ITEM_NAME
            ORDER BY revenue DESC
        )
        WHERE ROWNUM <= :limit
        """,
        {'location_code': int(location_code), 'limit': max(1, int(limit))},
    )


def recent_orders(*, location_code: int, limit: int = 10) -> List[Dict[str, Any]]:
    if not _orders_ready():
        return []
    return _safe_rows(
        """
        SELECT * FROM (
            SELECT
                o.ORDER_ID AS order_id,
                o.ORDER_NUMBER AS order_number,
                o.ORDER_STATUS AS order_status,
                o.GRAND_TOTAL AS grand_total,
                o.CURRENCY_CODE AS currency_code,
                o.CREATED_AT AS created_at,
                u.EMAIL AS customer_email
            FROM MH_ORDER o
            LEFT JOIN APP_USER u ON u.USER_ID = o.USER_ID
            WHERE o.LOCATION_CODE = :location_code
            ORDER BY o.ORDER_ID DESC
        )
        WHERE ROWNUM <= :limit
        """,
        {'location_code': int(location_code), 'limit': max(1, int(limit))},
    )


def catalog_stats(*, location_code: int) -> Dict[str, Any]:
    kpis = get_items_kpis(location_code=location_code) or {}
    return {
        'total_products': int(kpis.get('total_items') or 0),
        'active_products': int(kpis.get('active_items') or 0),
        'low_stock': int(kpis.get('low_stock_items') or 0),
    }
