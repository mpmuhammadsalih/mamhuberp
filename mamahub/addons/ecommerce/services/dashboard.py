"""Dashboard KPIs for Ecommerce admin."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List

from addons.ecommerce import customers_db
from addons.ecommerce import orders_db
from addons.ecommerce import media_db
from addons.ecommerce import promotions_db
from addons.ecommerce import reports_db
from addons.ecommerce import reviews_db
from db import get_items_kpis

from addons.ecommerce.services.common import resolve_location_code


def _weekly_orders_chart(*, location_code: int, days: int = 7) -> List[Dict[str, Any]]:
    """Last N calendar days with order counts (zero-filled gaps)."""
    raw = reports_db.weekly_sales(location_code=location_code, days=days)
    by_date: Dict[str, int] = {}
    for row in raw:
        day_val = row.get('day_date')
        if hasattr(day_val, 'strftime'):
            key = day_val.strftime('%Y-%m-%d')
        else:
            key = str(day_val or '')[:10]
        if key:
            by_date[key] = int(row.get('order_count') or 0)

    today = date.today()
    chart: List[Dict[str, Any]] = []
    for offset in range(days - 1, -1, -1):
        d = today - timedelta(days=offset)
        key = d.strftime('%Y-%m-%d')
        chart.append({
            'day_date': key,
            'day_label': d.strftime('%b %d'),
            'order_count': by_date.get(key, 0),
        })
    return chart


def get_dashboard_data() -> Dict[str, Any]:
    loc = resolve_location_code()
    kpis = get_items_kpis(location_code=loc) or {}
    order_stats = orders_db.order_dashboard_stats()
    total = int(kpis.get('total_items') or 0)
    low_stock = int(kpis.get('low_stock_items') or 0)
    active = int(kpis.get('active_items') or 0)
    in_stock = max(0, active - low_stock)
    weekly_orders = _weekly_orders_chart(location_code=loc, days=7)
    recent_orders = reports_db.recent_orders(location_code=loc, limit=5)
    max_weekly_orders = max((int(r.get('order_count') or 0) for r in weekly_orders), default=0)
    if max_weekly_orders < 1:
        max_weekly_orders = 1
    return {
        'kpi': {
            'location_code': loc,
            'total_products': total,
            'in_stock': in_stock,
            'out_of_stock': low_stock,
            'open_orders': int(order_stats.get('open_orders') or 0),
            'orders_today': int(order_stats.get('orders_today') or 0),
            'total_orders': int(order_stats.get('total_orders') or 0),
            'total_customers': customers_db.customer_count(),
            'active_promotions': promotions_db.active_promotion_count(),
            'pending_reviews': reviews_db.pending_review_count(),
            'active_media': media_db.active_media_count(),
            'storefront_status': 'Active',
            'orders_table_ready': orders_db.orders_tables_ready(),
        },
        'weekly_orders': weekly_orders,
        'recent_orders': recent_orders,
        'max_weekly_orders': max_weekly_orders,
    }
