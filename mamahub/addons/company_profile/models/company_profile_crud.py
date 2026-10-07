"""CRUD model for ``COMPANYPROFILE`` (tenant DB).

DDL stays in ``db.ensure_company_profile_table()``; use ``CompanyProfile`` for data operations::

    CompanyProfile.list_summary()
    CompanyProfile.get(1)
    CompanyProfile.create(data)
    CompanyProfile.upsert(1, data)
    CompanyProfile.delete(2)

Introspected RFIM column string constants (optional, after running the schema export script) live in
``addons.core.schema.generated.oracle_rfim_tables.companyprofile`` as ``CompanyprofileCols``.

To add another app-owned table, subclass ``OracleCrud`` / ``OracleCrudManualId`` in
``addons/core/crud/oracle_crud.py`` with ``FIELD_SPECS`` and ``ensure_table()``.
"""
from __future__ import annotations
from typing import Any, ClassVar, Dict, List, Tuple
from addons.core.crud.oracle_crud import FieldSpec, OracleCrudManualId

class CompanyProfile(OracleCrudManualId):
    """CRUD for COMPANYPROFILE."""
    TABLE_NAME: ClassVar[str] = 'COMPANYPROFILE'
    PRIMARY_KEY: ClassVar[str] = 'ID'
    USE_AUTH: ClassVar[bool] = False
    UPDATED_AT_SYSDATE: ClassVar[bool] = True
    FIELD_SPECS: ClassVar[Tuple[FieldSpec, ...]] = (('company_name', 'COMPANY_NAME', 200), ('legal_name', 'LEGAL_NAME', 200), ('address1', 'ADDRESS1', 300), ('address2', 'ADDRESS2', 300), ('city', 'CITY', 120), ('state_region', 'STATE_REGION', 120), ('country', 'COUNTRY', 120), ('postal_code', 'POSTAL_CODE', 40), ('phone', 'PHONE', 60), ('email', 'EMAIL', 150), ('website', 'WEBSITE', 250), ('tax_id', 'TAX_ID', 80), ('logo_mode', 'LOGO_MODE', 20), ('logo_path', 'LOGO_PATH', 500), ('logo_url', 'LOGO_URL', 500))

    @classmethod
    def ensure_table(cls) -> None:
        from db import ensure_company_profile_table
        ensure_company_profile_table()

    @classmethod
    def normalize_row(cls, row: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(row)
        for k, v in out.items():
            if v is None:
                lk = str(k).lower()
                if lk != 'updated_at':
                    out[k] = ''
        return out

    @classmethod
    def _bind_payload(cls, data: Dict[str, Any]) -> Dict[str, Any]:

        def _s(key: str, n: int) -> str:
            return str(data.get(key) or '').strip()[:n]
        logo_mode = (_s('logo_mode', 20) or 'none')[:20]
        logo_path = str(data.get('logo_path') or '').strip()[:500] or None
        logo_url = str(data.get('logo_url') or '').strip()[:500] or None
        return {'company_name': _s('company_name', 200), 'legal_name': _s('legal_name', 200), 'address1': _s('address1', 300), 'address2': _s('address2', 300), 'city': _s('city', 120), 'state_region': _s('state_region', 120), 'country': _s('country', 120), 'postal_code': _s('postal_code', 40), 'phone': _s('phone', 60), 'email': _s('email', 150), 'website': _s('website', 250), 'tax_id': _s('tax_id', 80), 'logo_mode': logo_mode, 'logo_path': logo_path, 'logo_url': logo_url}

    @classmethod
    def list_summary(cls) -> List[Dict[str, Any]]:
        cls.ensure_table()
        from db import _fetch_rows
        try:
            _, rows = _fetch_rows('\n                SELECT ID, COMPANY_NAME, LEGAL_NAME, CITY, PHONE, EMAIL,\n                       LOGO_MODE, LOGO_PATH, LOGO_URL, UPDATED_AT\n                FROM COMPANYPROFILE\n                ORDER BY ID\n                ', {})
        except Exception:
            return []
        return [cls.normalize_row(dict(r)) for r in rows or []]
__all__ = ['CompanyProfile']
