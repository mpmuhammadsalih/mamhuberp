"""Expose models for ``reports`` blueprint."""
from __future__ import annotations
from addons.reports.models.reports_models import TenantTables, from_db
__all__ = ['TenantTables', 'from_db']
