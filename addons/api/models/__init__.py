"""Expose models for ``api`` blueprint."""
from __future__ import annotations
from addons.api.models.api_models import TenantTables, from_db
__all__ = ['TenantTables', 'from_db']
