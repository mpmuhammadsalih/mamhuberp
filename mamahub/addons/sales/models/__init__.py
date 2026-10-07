"""Expose models for ``sales`` blueprint."""
from __future__ import annotations
from addons.sales.models.sales_models import TenantTables, from_db
__all__ = ['TenantTables', 'from_db']
