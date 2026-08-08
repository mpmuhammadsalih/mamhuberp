"""Expose models for ``roles`` blueprint."""
from __future__ import annotations
from addons.roles.models.roles_models import TenantTables, from_db
__all__ = ['TenantTables', 'from_db']
