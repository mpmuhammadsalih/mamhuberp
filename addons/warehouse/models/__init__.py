"""
Data layer for ``warehouse`` — DTOs / table–column registry / ``db`` adapters.
"""
from addons.warehouse.models.warehouse_models import TenantTables, W, from_db, wh
__all__ = ['TenantTables', 'W', 'wh', 'from_db']
