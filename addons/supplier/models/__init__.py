"""Expose models for ``supplier`` blueprint."""
from __future__ import annotations
from addons.supplier.models.supplier_models import TenantTables, from_db
__all__ = ['TenantTables', 'from_db']
