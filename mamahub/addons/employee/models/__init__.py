"""Expose models for ``employee`` blueprint."""
from __future__ import annotations
from addons.employee.models.employee_models import TenantTables, from_db
__all__ = ['TenantTables', 'from_db']
