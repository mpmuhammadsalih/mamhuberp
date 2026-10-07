"""CRM customers in WA_CUSTOMERS, with optional Oracle CUSTOMER master lookup."""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.repositories.oracle.erp_customer import OracleErpCustomerRepository
from app.utils.phones import normalize_whatsapp


class OracleCrmCustomerRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_whatsapp(self, whatsapp_number: str) -> Optional[Customer]:
        number = normalize_whatsapp(whatsapp_number)
        return (
            self.session.query(Customer)
            .filter(Customer.whatsapp_number == number)
            .first()
        )

    def get(self, customer_id: int) -> Optional[Customer]:
        return self.session.get(Customer, customer_id)

    def create_from_whatsapp(
        self,
        whatsapp_number: str,
        name: str,
        profile_image: Optional[str] = None,
    ) -> Customer:
        number = normalize_whatsapp(whatsapp_number)
        existing = self.get_by_whatsapp(number)
        display = (name or "").strip() or (existing.customer_name if existing else "") or number
        try:
            erp_row = OracleErpCustomerRepository(self.session).upsert(
                channel="WHATSAPP",
                name=display,
                mobile=number,
                whatsapp=number,
            )
        except Exception:
            erp_row = self.find_erp_by_mobile(number)
        if existing:
            if erp_row and not existing.erp_customer_code:
                existing.erp_customer_code = str(erp_row.get("customer_code") or "")
            if erp_row and erp_row.get("customer_code"):
                existing.customer_code = str(erp_row["customer_code"])
            if name and existing.customer_name in (existing.whatsapp_number, number, "") and name != existing.customer_name:
                existing.customer_name = name
            if profile_image and not existing.profile_image_url:
                existing.profile_image_url = profile_image
            return existing
        erp = erp_row or {}
        customer = Customer(
            customer_name=(erp or {}).get("customer_name") or display,
            whatsapp_number=number,
            email=(erp or {}).get("email"),
            address=(erp or {}).get("address"),
            customer_type=(erp or {}).get("customer_type") or "Retail",
            profile_image_url=profile_image,
            erp_customer_code=(erp or {}).get("customer_code"),
            outstanding_balance=float((erp or {}).get("outstanding") or 0),
        )
        self.session.add(customer)
        self.session.flush()
        customer.customer_code = str((erp or {}).get("customer_code") or f"WA{customer.customer_id:06d}")
        return customer

    def find_erp_by_mobile(self, mobile: str) -> Optional[dict[str, Any]]:
        """Best-effort lookup against Oracle CUSTOMER. Failures are ignored."""
        number = normalize_whatsapp(mobile)
        last8 = number[-8:] if len(number) >= 8 else number
        sql = text(
            """
            SELECT * FROM (
                SELECT
                    TO_CHAR(CUSTOMERCODE) AS customer_code,
                    CUSTOMERNAME AS customer_name,
                    EMAIL AS email,
                    ADDRESS AS address,
                    CUSTOMERTYPE AS customer_type,
                    NVL(CURRENTCREDITAMOUNT, 0) AS outstanding
                FROM CUSTOMER
                WHERE REPLACE(NVL(WHATSAPP, ' '), ' ', '') LIKE :q
                   OR REPLACE(NVL(MOBILE, ' '), ' ', '') LIKE :q
                   OR REPLACE(NVL(TELEPHONE, ' '), ' ', '') LIKE :q
            ) WHERE ROWNUM = 1
            """
        )
        try:
            row = self.session.execute(sql, {"q": f"%{last8}%"}).mappings().first()
        except Exception:
            return None
        if not row:
            return None
        return {
            "customer_code": str(row.get("customer_code") or ""),
            "customer_name": str(row.get("customer_name") or ""),
            "email": str(row.get("email") or "") or None,
            "address": str(row.get("address") or "") or None,
            "customer_type": str(row.get("customer_type") or "Retail"),
            "outstanding": float(row.get("outstanding") or 0),
        }
