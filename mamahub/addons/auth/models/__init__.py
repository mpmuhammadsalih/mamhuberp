"""Expose models for ``auth`` blueprint."""
from __future__ import annotations
from addons.auth.models.auth_models import TenantTables, from_db
__all__ = ['TenantTables', 'from_db']
