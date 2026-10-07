"""Chat addon — table + column identifiers (see ``db.ensure_chat_tables``).

:data:`addons.core.schema.from_db` exposes full introspected schema when generated.
"""
from __future__ import annotations
from addons.core.schema import cols_chat as chat
from addons.core.schema.common_models import TenantTables, from_db
C = chat
__all__ = ['TenantTables', 'chat', 'C', 'from_db']
