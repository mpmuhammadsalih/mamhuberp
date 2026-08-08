"""Expose models for ``notifications`` blueprint."""
from __future__ import annotations
from addons.notifications.models.notifications_models import TenantTables, from_db
__all__ = ['TenantTables', 'from_db']
