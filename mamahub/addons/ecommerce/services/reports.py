"""Reports page services."""
from __future__ import annotations

from typing import Any, Dict

from addons.ecommerce import customers_db
from addons.ecommerce import orders_db
from addons.ecommerce import promotions_db
from addons.ecommerce import reports_db

from addons.ecommerce.services.common import resolve_location_code


def get_reports_data() -> Dict[str, Any]:
    loc = resolve_location_code()
    sales = reports_db.sales_summary(location_code=loc)
    weekly = reports_db.weekly_sales(location_code=loc, days=7)
    categories = reports_db.category_mix(location_code=loc, limit=8)
    top_products = reports_db.top_products(location_code=loc, limit=10)
    recent = reports_db.recent_orders(location_code=loc, limit=10)
    catalog = reports_db.catalog_stats(location_code=loc)

    max_weekly_revenue = max((row.get('revenue') or 0) for row in weekly) if weekly else 0
    if max_weekly_revenue <= 0:
        max_weekly_revenue = 1.0

    warning = None
    if not orders_db.orders_tables_ready():
        warning = (
            'MH_ORDER tables are not installed — sales reports will be empty until '
            'sql/02_tables/10_mh_orders.sql is applied.'
        )

    return {
        'location_code': loc,
        'sales': sales,
        'weekly_sales': weekly,
        'max_weekly_revenue': max_weekly_revenue,
        'category_mix': categories,
        'top_products': top_products,
        'recent_orders': recent,
        'catalog': catalog,
        'total_customers': customers_db.customer_count(),
        'active_promotions': promotions_db.active_promotion_count(),
        'warning': warning,
        'orders_ready': orders_db.orders_tables_ready(),
    }
