from __future__ import annotations

import json
from typing import List

from mobile_backend.database.oracle_pool import get_auth_connection
from mobile_backend.services.auth_service import PRIVILEGED_USERS, _active_flag_clause


def _get_user_row(username: str):
    conn = get_auth_connection()
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT username, role_id, tenant_id, multilocations_view, allowed_tenant_ids
              FROM login_users
             WHERE UPPER(TRIM(username)) = UPPER(TRIM(:username))
               AND {_active_flag_clause()}
            """,
            {"username": username},
        )
        return cur.fetchone()


def _get_tenants() -> List[dict]:
    conn = get_auth_connection()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT tenant_id, display_name
              FROM tenant_databases
             WHERE NVL(active_flag, 'Y') IN ('Y', 'YES', '1', 'TRUE')
             ORDER BY tenant_id
            """
        )
        rows = cur.fetchall()
        return [
            {
                "tenant_id": str(row[0]),
                "display_name": str(row[1] or row[0]),
            }
            for row in rows
            if row and row[0] is not None
        ]


def _parse_allowed_tenant_ids(raw_value) -> set[str]:
    if raw_value is None:
        return set()
    raw = str(raw_value).strip()
    if not raw:
        return set()
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return {str(v).strip().lower() for v in parsed if str(v).strip()}
    except Exception:
        pass
    return {v.strip().lower() for v in raw.split(",") if v.strip()}


def get_user_tenant_scope(username: str) -> dict:
    row = _get_user_row(username)
    if not row:
        raise ValueError("User not found")

    user = str(row[0] or "").strip()
    role_id = str(row[1] or "").strip()
    current_tenant = str(row[2]).strip() if row[2] is not None else None
    multilocations_view = str(row[3] or "N").strip().upper()
    allowed_raw = row[4]

    all_tenants = _get_tenants()
    is_privileged = user.lower() in PRIVILEGED_USERS
    can_switch = is_privileged or multilocations_view == "Y"

    if not can_switch:
        visible = [t for t in all_tenants if t["tenant_id"].lower() == (current_tenant or "").lower()]
    elif is_privileged:
        visible = all_tenants
    else:
        allowed = _parse_allowed_tenant_ids(allowed_raw)
        visible = [t for t in all_tenants if t["tenant_id"].lower() in allowed] if allowed else all_tenants

    return {
        "username": user,
        "role_id": role_id,
        "current_tenant_id": current_tenant,
        "can_switch": can_switch,
        "tenants": visible,
    }
