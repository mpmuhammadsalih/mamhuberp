"""Expose models for ``accounts`` blueprint."""
from __future__ import annotations
from addons.accounts.models.accounts_models import TenantTables, from_db
__all__ = ['TenantTables', 'from_db']
