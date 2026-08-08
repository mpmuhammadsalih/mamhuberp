"""
Data layer for ``chat`` — DTOs / table–column registry / ``db`` adapters.
"""
from addons.chat.models.chat_models import C, TenantTables, chat, from_db
__all__ = ['TenantTables', 'chat', 'C', 'from_db']
