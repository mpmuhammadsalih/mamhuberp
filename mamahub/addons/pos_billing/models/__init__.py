"""Expose models for ``pos_billing`` blueprint."""
from __future__ import annotations
from addons.pos_billing.models.pos_billing_models import TenantTables, from_db
__all__ = ['TenantTables', 'from_db']
