"""Expose models for ``users`` blueprint."""
from __future__ import annotations
from addons.users.models.users_models import TenantTables, from_db
__all__ = ['TenantTables', 'from_db']
