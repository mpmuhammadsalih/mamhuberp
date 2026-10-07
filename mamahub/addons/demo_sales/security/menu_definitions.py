"""
Menu labels and permission identifiers for ``demo_sales`` addon.

Actual **role grants** live in ``permissions.py`` (`MENU_GROUPS` → ``menu_path`` endpoints).
Duplicate only what you need for documentation or future tooling.

Sidebar wiring: ``templates/base.html`` checks ``has_menu_permission('demo_sales.dashboard')``.
"""
from typing import Dict, List
MENU_PAGE_LABELS: Dict[str, str] = {'demo_sales.dashboard': 'Sales cockpit', 'demo_sales.orders': 'Orders', 'demo_sales.pipeline': 'Pipeline'}

def menu_pages_ordered() -> List[str]:
    return ['demo_sales.dashboard', 'demo_sales.orders', 'demo_sales.pipeline']
