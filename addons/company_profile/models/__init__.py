"""Expose models for ``company_profile`` blueprint."""
from __future__ import annotations
from addons.company_profile.models.company_profile_crud import CompanyProfile
from addons.company_profile.models.company_profile_models import TenantTables, from_db
__all__ = ['TenantTables', 'from_db', 'CompanyProfile']
