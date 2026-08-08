"""Expose models for ``ho`` blueprint."""
from __future__ import annotations
from addons.ho.models.ho_models import TenantTables, from_db
__all__ = ['TenantTables', 'from_db']
