"""Expose models for ``tenants`` blueprint."""
from __future__ import annotations
from addons.tenants.models.tenants_models import TenantTables, from_db
__all__ = ['TenantTables', 'from_db']
