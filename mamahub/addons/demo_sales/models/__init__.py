"""Expose models for ``demo_sales`` blueprint."""
from __future__ import annotations
from addons.demo_sales.models.demo_sales_models import TenantTables, from_db
from addons.demo_sales.models.sale_order import SaleOrderRow, demo_orders_as_dicts
__all__ = ['TenantTables', 'from_db', 'SaleOrderRow', 'demo_orders_as_dicts']
