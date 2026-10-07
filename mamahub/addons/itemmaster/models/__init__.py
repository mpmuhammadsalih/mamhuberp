"""Expose models for ``itemmaster`` blueprint."""
from __future__ import annotations
from addons.itemmaster.models.itemmaster_models import TenantTables, from_db
__all__ = ['TenantTables', 'from_db']
