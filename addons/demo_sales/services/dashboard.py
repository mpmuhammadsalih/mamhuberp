"""Aggregations and rules for the Sales cockpit pages (demo)."""
from __future__ import annotations
from typing import Any, Dict
from addons.demo_sales.models import demo_orders_as_dicts

def get_dashboard_kpis() -> Dict[str, Any]:
    """Replace with real queries via models/ + db.py."""
    return {'open_quotes': 12, 'orders_today': 3, 'pipeline_value': 128500.0}

def get_orders_snapshot() -> Dict[str, Any]:
    return demo_orders_as_dicts()

def get_pipeline_stages() -> Dict[str, Any]:
    return {'stages': [{'name': 'New', 'count': 5}, {'name': 'Qualified', 'count': 8}, {'name': 'Proposal', 'count': 3}]}
