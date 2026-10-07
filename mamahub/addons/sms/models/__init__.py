"""Expose models for ``sms`` blueprint."""
from __future__ import annotations
from addons.sms.models.sms_models import TenantTables, from_db
__all__ = ['TenantTables', 'from_db']
