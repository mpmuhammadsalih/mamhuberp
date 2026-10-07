"""Expose models for ``temporary_invoices`` blueprint."""
from __future__ import annotations
from addons.temporary_invoices.models.temporary_invoices_models import TenantTables, from_db
__all__ = ['TenantTables', 'from_db']
