"""Expose models for ``sales_summary`` blueprint."""
from __future__ import annotations
from addons.sales_summary.models.sales_summary_models import TenantTables, from_db
__all__ = ['TenantTables', 'from_db']
