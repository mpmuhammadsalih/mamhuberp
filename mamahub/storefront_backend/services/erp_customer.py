"""Shared ERP CUSTOMER upsert for website registration."""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

from db import _get_connection, _get_table_columns, _safe_rows, _table_exists


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
    return incoming or "WEB"


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


def find_email_duplicate(
    email: str,
    *,
    location_code: int = 1,
    exclude_code: Optional[int] = None,
) -> Optional[int]:
    value = normalize_email(email)
    if not value or not _table_exists("CUSTOMER"):
        return None
    params: Dict[str, Any] = {"loc": int(location_code), "email": value}
    extra = ""
    if exclude_code:
        extra = " AND CUSTOMERCODE <> :exclude"
        params["exclude"] = int(exclude_code)
    rows = _safe_rows(
        f"""
        SELECT CUSTOMERCODE AS customercode
        FROM CUSTOMER
        WHERE LOCATIONCODE = :loc
          AND LOWER(TRIM(EMAIL)) = :email
          {extra}
        FETCH FIRST 1 ROWS ONLY
        """,
        params,
    )
    if not rows:
        return None
    try:
        return int(rows[0].get("customercode"))
    except (TypeError, ValueError):
        return None


def find_mobile_duplicate(
    mobile: str,
    *,
    location_code: int = 1,
    exclude_code: Optional[int] = None,
) -> Optional[int]:
    digits = _digits(mobile)
    last8 = digits[-8:] if len(digits) >= 8 else digits
    if not last8 or not _table_exists("CUSTOMER"):
        return None
    params: Dict[str, Any] = {"loc": int(location_code), "q": f"%{last8}%"}
    extra = ""
    if exclude_code:
        extra = " AND CUSTOMERCODE <> :exclude"
        params["exclude"] = int(exclude_code)
    rows = _safe_rows(
        f"""
        SELECT CUSTOMERCODE AS customercode
        FROM CUSTOMER
        WHERE LOCATIONCODE = :loc
          AND (
            REGEXP_REPLACE(NVL(MOBILE, ''), '[^0-9]', '') LIKE :q
            OR REGEXP_REPLACE(NVL(WHATSAPP, ''), '[^0-9]', '') LIKE :q
            OR REGEXP_REPLACE(NVL(TELEPHONE, ''), '[^0-9]', '') LIKE :q
          )
          {extra}
        FETCH FIRST 1 ROWS ONLY
        """,
        params,
    )
    if not rows:
        return None
    try:
        return int(rows[0].get("customercode"))
    except (TypeError, ValueError):
        return None


def _ensure_channel_column() -> None:
    if not _table_exists("CUSTOMER"):
        return
    cols = {str(c).upper() for c in (_get_table_columns("CUSTOMER") or [])}
    if "SOURCE_CHANNEL" in cols:
        return
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("ALTER TABLE CUSTOMER ADD (SOURCE_CHANNEL VARCHAR2(40))")
        conn.commit()


def upsert_erp_customer(
    *,
    channel: str,
    name: str,
    mobile: str,
    email: Optional[str] = None,
    address: Optional[str] = None,
    whatsapp: Optional[str] = None,
    location_code: int = 1,
) -> Optional[Dict[str, Any]]:
    if not _table_exists("CUSTOMER"):
        return None
    _ensure_channel_column()
    cols = {str(c).upper() for c in (_get_table_columns("CUSTOMER") or [])}
    loc = int(location_code or 1)
    phone = _digits(whatsapp or mobile)
    last8 = phone[-8:] if len(phone) >= 8 else phone
    if not last8:
        return None
    e164 = f"+{phone}" if phone.startswith("974") else (f"+974{last8}" if len(last8) == 8 else mobile)
    found = _safe_rows(
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
        """,
        {"loc": loc, "q": f"%{last8}%"},
    )
    clean_name = (name or "").strip() or e164
    existing = found[0] if found else None
    channel_value = merge_channel((existing or {}).get("source_channel"), channel)
    exclude = int(existing["customercode"]) if existing else None
    if email:
        ok_email, email_msg = validate_email(email)
        if not ok_email:
            raise DuplicateCustomerError(email_msg)
        email_dup = find_email_duplicate(email, location_code=loc, exclude_code=exclude)
        if email_dup:
            raise DuplicateCustomerError(f"Email already used by customer {email_dup}.")
    if existing:
        code = int(existing["customercode"])
        sets = ["SOURCE_CHANNEL = :channel"] if "SOURCE_CHANNEL" in cols else []
        params: Dict[str, Any] = {"loc": loc, "code": code, "channel": channel_value[:40]}
        if email and "EMAIL" in cols:
            sets.append("EMAIL = NVL(EMAIL, :email)")
            params["email"] = email[:150]
        if address and "ADDRESS" in cols:
            sets.append("ADDRESS = NVL(ADDRESS, :address)")
            params["address"] = address[:200]
        if "MOBILE" in cols:
            sets.append("MOBILE = NVL(MOBILE, :mobile)")
            params["mobile"] = e164[:15]
        if "WHATSAPP" in cols and whatsapp:
            sets.append("WHATSAPP = NVL(WHATSAPP, :wa)")
            params["wa"] = (whatsapp or e164)[:20]
        if sets:
            with _get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"UPDATE CUSTOMER SET {', '.join(sets)} WHERE LOCATIONCODE = :loc AND CUSTOMERCODE = :code",
                        params,
                    )
                conn.commit()
        return {"customer_code": str(code), "customer_name": clean_name, "source_channel": channel_value}

    mobile_dup = find_mobile_duplicate(e164, location_code=loc)
    if mobile_dup:
        raise DuplicateCustomerError(f"Mobile already used by customer {mobile_dup}.")

    nxt = _safe_rows(
        "SELECT NVL(MAX(CUSTOMERCODE), 0) + 1 AS n FROM CUSTOMER WHERE LOCATIONCODE = :loc",
        {"loc": loc},
    )
    code = int((nxt[0] or {}).get("n") or 1)
    if code == 90001:
        code = 90002
    row = {
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
        "EMAIL": (email or None),
        "ADDRESS": (address or None),
        "SOURCE_CHANNEL": channel_value[:40],
    }
    filtered = {k: v for k, v in row.items() if k in cols and v is not None}
    extra = ", CREATEDDATE" if "CREATEDDATE" in cols else ""
    extra_val = ", SYSDATE" if "CREATEDDATE" in cols else ""
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO CUSTOMER ({', '.join(filtered)}{extra}) VALUES ({', '.join(':' + k for k in filtered)}{extra_val})",
                filtered,
            )
        conn.commit()
    return {"customer_code": str(code), "customer_name": clean_name, "source_channel": channel_value}
