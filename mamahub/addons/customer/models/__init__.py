"""Expose models for ``customer`` blueprint."""
from __future__ import annotations
from addons.customer.models.customer_models import TenantTables, from_db
__all__ = ['TenantTables', 'from_db']
