"""Customer list/detail services."""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from addons.ecommerce import customers_db


def list_customers_page(
    *,
    page: int = 1,
    page_size: int = 20,
    search: Optional[str] = None,
) -> Dict[str, Any]:
    rows, total = customers_db.list_customers(
        page=page,
        page_size=page_size,
        search=search,
    )
    total_pages = max(1, (total + page_size - 1) // page_size) if total else 1
    return {
        'customers': rows,
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': total_pages,
        'tables_ready': customers_db.customers_table_ready(),
    }


def get_customer_detail(user_id: int) -> Optional[Dict[str, Any]]:
    customer = customers_db.get_customer(user_id)
    if not customer:
        return None
    summary = customers_db.customer_order_summary(user_id)
    orders = customers_db.list_customer_orders(user_id)
    return {
        **customer,
        **summary,
        'orders': orders,
    }


def change_customer_account_status(user_id: int, status: str) -> Tuple[bool, str]:
    return customers_db.update_customer_account_status(user_id, status)
