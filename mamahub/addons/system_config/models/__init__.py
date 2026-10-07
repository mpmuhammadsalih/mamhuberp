"""Expose models for ``system_config`` blueprint."""
from __future__ import annotations
from addons.system_config.models.system_config_models import TenantTables, from_db
__all__ = ['TenantTables', 'from_db']
