"""Menu labels for the ecommerce addon (documentation mirror)."""
from typing import Dict, List

MENU_PAGE_LABELS: Dict[str, str] = {
    'ecommerce.dashboard': 'Dashboard',
    'ecommerce.orders': 'Orders',
    'ecommerce.products': 'Products',
    'ecommerce.categories': 'Categories',
    'ecommerce.customers': 'Customers',
    'ecommerce.promotions': 'Promotions',
    'ecommerce.reviews': 'Reviews',
    'ecommerce.media': 'Media',
    'ecommerce.cms': 'CMS pages',
    'ecommerce.inventory': 'Inventory',
    'ecommerce.reports': 'Reports',
    'ecommerce.settings': 'Settings',
}


def menu_pages_ordered() -> List[str]:
    return list(MENU_PAGE_LABELS.keys())
