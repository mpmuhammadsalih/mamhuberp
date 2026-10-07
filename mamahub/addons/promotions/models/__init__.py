"""Expose models for ``promotions`` blueprint."""
from __future__ import annotations
from addons.promotions.models.promotions_models import TenantTables, from_db
__all__ = ['TenantTables', 'from_db']
