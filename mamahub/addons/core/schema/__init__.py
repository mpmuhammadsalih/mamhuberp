"""Schema registry: table names delegated from ``db`` + ``cols_*`` + introspected DB models."""
from addons.core.schema import cols_chat
from addons.core.schema import cols_inventory
from addons.core.schema import cols_wh
from addons.core.schema import from_db
from addons.core.schema.tenant_tables import TenantTables
__all__ = ['TenantTables', 'cols_chat', 'cols_inventory', 'cols_wh', 'from_db']
