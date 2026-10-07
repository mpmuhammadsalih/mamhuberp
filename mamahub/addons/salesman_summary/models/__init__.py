"""Expose models for ``salesman_summary`` blueprint."""
from __future__ import annotations
from addons.salesman_summary.models.salesman_summary_models import TenantTables, from_db
__all__ = ['TenantTables', 'from_db']
