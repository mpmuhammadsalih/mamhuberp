"""Review moderation services."""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from addons.ecommerce import reviews_db


def list_reviews_page(
    *,
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = 'PENDING',
    search: Optional[str] = None,
) -> Dict[str, Any]:
    status_filter = (status or '').strip().upper() or None
    rows, total, warning = reviews_db.list_reviews(
        page=page,
        page_size=page_size,
        status=status_filter,
        search=search,
    )
    total_pages = max(1, (total + page_size - 1) // page_size) if total else 1
    return {
        'reviews': rows,
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': total_pages,
        'warning': warning,
        'tables_ready': reviews_db.reviews_table_ready(),
        'status_filter': status_filter or '',
        'status_options': ['PENDING', 'APPROVED', 'REJECTED', 'HIDDEN'],
    }


def moderate_review(review_id: int, status: str) -> Tuple[bool, str]:
    return reviews_db.update_review_status(review_id, status)
