"""Create or update the shared ERP CUSTOMER master from WhatsApp."""
from __future__ import annotations

import re
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import logger


class DuplicateCustomerError(ValueError):
    """Email or mobile already belongs to another CUSTOMER."""


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _digits(raw: str) -> str:
    return re.sub(r"\D+", "", raw or "")


def normalize_email(email: Optional[str]) -> str:
    return str(email or "").strip().lower()


def validate_email(email: Optional[str], *, required: bool = False) -> tuple[bool, str]:
    value = normalize_email(email)
    if not value:
        return (not required, "Email is required." if required else "")
    if len(value) > 150 or not _EMAIL_RE.match(value):
        return False, "Enter a valid email address."
    return True, ""


def validate_mobile(mobile: Optional[str], *, required: bool = False) -> tuple[bool, str, str]:
    raw = str(mobile or "").strip()
    if not raw:
        return (not required, "Mobile number is required." if required else "", "")
    digits = _digits(raw)
    if digits.startswith("00"):
        digits = digits[2:]
    if len(digits) == 8:
        digits = "974" + digits
    if not digits.startswith("974") or len(digits) != 11:
        return False, "Enter a valid Qatar mobile number (8 digits or +974…).", ""
    return True, "", "+" + digits


def merge_channel(existing: Optional[str], incoming: str) -> str:
    parts: set[str] = set()
    for token in re.split(r"[+,/| ]+", str(existing or "").upper()):
        token = token.strip()
        if token == "BOTH":
            parts.update({"WHATSAPP", "WEB"})
        elif token == "ALL":
            parts.update({"WHATSAPP", "WEB", "POS"})
        elif token:
            parts.add(token)
    incoming = (incoming or "").strip().upper()
    if incoming == "BOTH":
        parts.update({"WHATSAPP", "WEB"})
    elif incoming:
        parts.add(incoming)
    if {"WHATSAPP", "WEB", "POS"} <= parts:
        return "ALL"
    if {"WHATSAPP", "WEB"} <= parts:
        return "BOTH"
    if "POS" in parts and "WHATSAPP" in parts:
        return "POS+WHATSAPP"
    if "POS" in parts and "WEB" in parts:
        return "POS+WEB"
    if "WHATSAPP" in parts:
        return "WHATSAPP"
    if "WEB" in parts:
        return "WEB"
    if "POS" in parts:
        return "POS"
    return incoming or "WHATSAPP"


class OracleErpCustomerRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _table_exists(self, table: str) -> bool:
        row = self.session.execute(
            text("SELECT COUNT(*) FROM USER_TABLES WHERE TABLE_NAME = :t"),
            {"t": table.upper()},
        ).scalar()
        return int(row or 0) > 0

    def _columns(self) -> set[str]:
        rows = self.session.execute(
            text("SELECT COLUMN_NAME FROM USER_TAB_COLUMNS WHERE TABLE_NAME = 'CUSTOMER'"),
        ).scalars().all()
        return {str(name).upper() for name in rows}

    def find_email_duplicate(self, email: str, loc: int, exclude_code: Optional[int] = None) -> Optional[int]:
        value = normalize_email(email)
        if not value:
            return None
        params: dict[str, Any] = {"loc": loc, "email": value}
        extra = ""
        if exclude_code:
            extra = " AND CUSTOMERCODE <> :exclude"
            params["exclude"] = int(exclude_code)
        row = self.session.execute(
            text(
                f"""
                SELECT CUSTOMERCODE FROM CUSTOMER
                WHERE LOCATIONCODE = :loc AND LOWER(TRIM(EMAIL)) = :email
                {extra}
                FETCH FIRST 1 ROWS ONLY
                """
            ),
            params,
        ).scalar()
        return int(row) if row is not None else None

    def find_mobile_duplicate(self, mobile: str, loc: int, exclude_code: Optional[int] = None) -> Optional[int]:
        last8 = _digits(mobile)[-8:]
        if len(last8) < 8:
            return None
        params: dict[str, Any] = {"loc": loc, "q": f"%{last8}%"}
        extra = ""
        if exclude_code:
            extra = " AND CUSTOMERCODE <> :exclude"
            params["exclude"] = int(exclude_code)
        row = self.session.execute(
            text(
                f"""
                SELECT CUSTOMERCODE FROM CUSTOMER
                WHERE LOCATIONCODE = :loc AND (
                    REGEXP_REPLACE(NVL(MOBILE, ''), '[^0-9]', '') LIKE :q
                    OR REGEXP_REPLACE(NVL(WHATSAPP, ''), '[^0-9]', '') LIKE :q
                    OR REGEXP_REPLACE(NVL(TELEPHONE, ''), '[^0-9]', '') LIKE :q
                )
                {extra}
                FETCH FIRST 1 ROWS ONLY
                """
            ),
            params,
        ).scalar()
        return int(row) if row is not None else None

    def ensure_channel_column(self) -> None:
        if not self._table_exists("CUSTOMER"):
            return
        if "SOURCE_CHANNEL" in self._columns():
            return
        self.session.execute(text("ALTER TABLE CUSTOMER ADD (SOURCE_CHANNEL VARCHAR2(40))"))
        logger.info("Added CUSTOMER.SOURCE_CHANNEL")

    def upsert(
        self,
        *,
        channel: str,
        name: str,
        mobile: str,
        email: Optional[str] = None,
        address: Optional[str] = None,
        whatsapp: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        if not self._table_exists("CUSTOMER"):
            return None
        self.ensure_channel_column()
        cols = self._columns()
        loc = int(get_settings().oracle_location_code or 1)
        phone = _digits(whatsapp or mobile)
        last8 = phone[-8:] if len(phone) >= 8 else phone
        if not last8:
            return None
        e164 = f"+{phone}" if phone.startswith("974") else (f"+974{last8}" if len(last8) == 8 else mobile)
        found = self.session.execute(
            text(
                """
                SELECT CUSTOMERCODE AS customercode, CUSTOMERNAME AS customername,
                       SOURCE_CHANNEL AS source_channel
                FROM CUSTOMER
                WHERE LOCATIONCODE = :loc AND (
                    REGEXP_REPLACE(NVL(WHATSAPP, ''), '[^0-9]', '') LIKE :q
                    OR REGEXP_REPLACE(NVL(MOBILE, ''), '[^0-9]', '') LIKE :q
                    OR REGEXP_REPLACE(NVL(TELEPHONE, ''), '[^0-9]', '') LIKE :q
                )
                FETCH FIRST 1 ROWS ONLY
                """
                if "SOURCE_CHANNEL" in cols
                else """
                SELECT CUSTOMERCODE AS customercode, CUSTOMERNAME AS customername,
                       NULL AS source_channel
                FROM CUSTOMER
                WHERE LOCATIONCODE = :loc AND (
                    REGEXP_REPLACE(NVL(WHATSAPP, ''), '[^0-9]', '') LIKE :q
                    OR REGEXP_REPLACE(NVL(MOBILE, ''), '[^0-9]', '') LIKE :q
                    OR REGEXP_REPLACE(NVL(TELEPHONE, ''), '[^0-9]', '') LIKE :q
                )
                FETCH FIRST 1 ROWS ONLY
                """
            ),
            {"loc": loc, "q": f"%{last8}%"},
        ).mappings().first()

        clean_name = (name or "").strip() or e164
        channel_value = merge_channel((found or {}).get("source_channel"), channel)
        exclude = int(found["customercode"]) if found else None
        if email:
            ok_email, email_msg = validate_email(email)
            if not ok_email:
                raise DuplicateCustomerError(email_msg)
            email_dup = self.find_email_duplicate(email, loc, exclude)
            if email_dup:
                raise DuplicateCustomerError(f"Email already used by customer {email_dup}.")

        if found:
            code = int(found["customercode"])
            sets = []
            params: dict[str, Any] = {"loc": loc, "code": code}
            if clean_name and str(found.get("customername") or "").strip() in {"", str(found.get("customercode"))}:
                sets.append("CUSTOMERNAME = :name")
                params["name"] = clean_name[:200]
            if email and "EMAIL" in cols:
                sets.append("EMAIL = NVL(EMAIL, :email)")
                params["email"] = email[:150]
            if address and "ADDRESS" in cols:
                sets.append("ADDRESS = NVL(ADDRESS, :address)")
                params["address"] = address[:200]
            if "WHATSAPP" in cols and whatsapp:
                sets.append("WHATSAPP = NVL(WHATSAPP, :wa)")
                params["wa"] = (whatsapp or e164)[:20]
            if "MOBILE" in cols:
                sets.append("MOBILE = NVL(MOBILE, :mobile)")
                params["mobile"] = e164[:15]
            if "SOURCE_CHANNEL" in cols:
                sets.append("SOURCE_CHANNEL = :channel")
                params["channel"] = channel_value[:40]
            if sets:
                self.session.execute(
                    text(f"UPDATE CUSTOMER SET {', '.join(sets)} WHERE LOCATIONCODE = :loc AND CUSTOMERCODE = :code"),
                    params,
                )
            return {
                "customer_code": str(code),
                "customer_name": clean_name,
                "source_channel": channel_value,
            }

        mobile_dup = self.find_mobile_duplicate(e164, loc)
        if mobile_dup:
            raise DuplicateCustomerError(f"Mobile already used by customer {mobile_dup}.")

        nxt = self.session.execute(
            text("SELECT NVL(MAX(CUSTOMERCODE), 0) + 1 FROM CUSTOMER WHERE LOCATIONCODE = :loc"),
            {"loc": loc},
        ).scalar()
        code = int(nxt or 1)
        if code == 90001:
            code = 90002
        row: dict[str, Any] = {
            "LOCATIONCODE": loc,
            "CUSTOMERCODE": code,
            "CUSTOMERNAME": clean_name[:200],
            "CREDITLIMIT": 0,
            "CREDITTERMS": 0,
            "SALESMANCODE": 0,
            "FLAG": "Y",
            "CUSTOMERCATEGORY": 0,
            "BYSALESMAN": 0,
            "ROUTENO": 0,
            "CREATEDSTATUS": "N",
            "TRANSFERBRANCH": "N",
            "PRINTSEPRATE": "N",
            "QID": 0,
            "ACTIVE": "Y",
            "COUNTERSALE": "Y",
            "DUEDAYS": 0,
            "MAINGROUP": 0,
            "CUSTOMER_BILLING_TYPE": "CASH",
            "MOBILE": e164[:15],
            "WHATSAPP": (whatsapp or e164)[:20],
            "EMAIL": (email or "")[:150] or None,
            "ADDRESS": (address or "")[:200] or None,
            "SOURCE_CHANNEL": channel_value[:40],
        }
        if "CREATEDDATE" in cols:
            # SYSDATE via SQL default — skip bind
            pass
        filtered = {k: v for k, v in row.items() if k in cols and v is not None}
        if "CREATEDDATE" in cols:
            col_sql = ", ".join(list(filtered) + ["CREATEDDATE"])
            bind_sql = ", ".join([f":{k}" for k in filtered] + ["SYSDATE"])
        else:
            col_sql = ", ".join(filtered)
            bind_sql = ", ".join(f":{k}" for k in filtered)
        self.session.execute(text(f"INSERT INTO CUSTOMER ({col_sql}) VALUES ({bind_sql})"), filtered)
        return {
            "customer_code": str(code),
            "customer_name": clean_name,
            "source_channel": channel_value,
        }
