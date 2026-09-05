"""Order list/detail services."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from addons.ecommerce import orders_db


def list_orders_page(
    *,
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    search: Optional[str] = None,
) -> Dict[str, Any]:
    rows, total, warning = orders_db.list_orders(
        page=page,
        page_size=page_size,
        status=status,
        search=search,
    )
    total_pages = max(1, (total + page_size - 1) // page_size) if total else 1
    return {
        'orders': rows,
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': total_pages,
        'warning': warning,
        'tables_ready': orders_db.orders_tables_ready(),
        'status_options': sorted(orders_db.ALLOWED_STATUSES),
    }


def get_order_detail(order_id: int) -> Optional[Dict[str, Any]]:
    return orders_db.get_order(order_id)


def change_order_status(
    order_id: int,
    status: str,
    *,
    notes: Optional[str] = None,
    updated_by: Optional[int] = None,
) -> Tuple[bool, str]:
    return orders_db.update_order_status(
        order_id,
        status,
        notes=notes,
        updated_by=updated_by,
    )
