"""Re-export for addon ``models``: ``TenantTables`` + introspection (:mod:`from_db`).

Oracle **CREATE TABLE** for app-owned tables runs via ``db.bootstrap_application_schema()`` /
``ensure_*`` — see ``db.get_app_owned_extended_bootstrap_steps()`` — not via generated ``*Cols``.
"""
from __future__ import annotations
from addons.core.schema.tenant_tables import TenantTables
from . import from_db
__all__ = ['TenantTables', 'from_db']
