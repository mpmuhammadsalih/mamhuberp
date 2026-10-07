"""Expose models for ``temporary_collection`` blueprint."""
from __future__ import annotations
from addons.temporary_collection.models.temporary_collection_models import TenantTables, from_db
__all__ = ['TenantTables', 'from_db']
