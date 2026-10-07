"""Expose models for ``dashboard`` blueprint."""
from __future__ import annotations
from addons.dashboard.models.dashboard_models import TenantTables, from_db
__all__ = ['TenantTables', 'from_db']
