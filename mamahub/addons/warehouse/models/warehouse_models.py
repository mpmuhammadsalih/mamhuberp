"""Warehouse addon — physical table + column names for SQL and DTOs.

Use :class:`addons.core.schema.cols_wh.WarehouseStorageCols` (etc.) for identifiers;
:data:`addons.core.schema.from_db` supplies full Oracle introspection when generated.
"""
from __future__ import annotations
from addons.core.schema import cols_wh as wh
from addons.core.schema.common_models import TenantTables, from_db
W = wh
__all__ = ['TenantTables', 'W', 'wh', 'from_db']
