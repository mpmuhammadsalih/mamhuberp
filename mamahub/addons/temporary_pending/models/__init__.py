"""Expose models for ``temporary_pending`` blueprint."""
from __future__ import annotations
from addons.temporary_pending.models.temporary_pending_models import TenantTables, from_db
__all__ = ['TenantTables', 'from_db']
