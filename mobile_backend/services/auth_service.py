from __future__ import annotations

from typing import Any, Dict, List

from mobile_backend.config import Config

PRIVILEGED_USERS = {"admin", "super"}


def _active_flag_clause(column: str = "active_flag") -> str:
    return f"NVL({column}, 'Y') IN ('Y', 'YES', '1', 'TRUE')"


def _is_privileged_username(username: str) -> bool:
    return str(username or "").strip().lower() in PRIVILEGED_USERS


def authenticate_user(username: str, password: str) -> Dict[str, Any] | None:
    """Authenticate using ERP auth DB (``login_users`` and ``pdt_users``)."""
    from db import (
        PRIVILEGED_USERS as ERP_PRIVILEGED,
        get_user_employeecode,
        get_user_role_id,
        get_user_tenant_id,
        get_username_by_employeecode,
        verify_user,
    )
    from db.pdt_auth import get_pdt_username_by_employeecode, verify_pdt_user

    login_input = (username or "").strip()
    pwd = password or ""
    if not login_input or not pwd:
        return None

    resolved = login_input
    authenticated = False

    if verify_user(resolved, pwd):
        authenticated = True
    else:
        for lookup in (get_username_by_employeecode, get_pdt_username_by_employeecode):
            alt = lookup(login_input)
            if alt and verify_user(str(alt).strip(), pwd):
                resolved = str(alt).strip()
                authenticated = True
                break
        if not authenticated and verify_pdt_user(login_input, pwd):
            authenticated = True
        elif not authenticated:
            alt = get_pdt_username_by_employeecode(login_input)
            if alt and verify_pdt_user(str(alt).strip(), pwd):
                resolved = str(alt).strip()
                authenticated = True

    if not authenticated:
        return None

    role_id = get_user_role_id(resolved) or ""
    tenant_id = get_user_tenant_id(resolved)
    privileged = _is_privileged_username(resolved) or resolved.lower() in {
        u.lower() for u in ERP_PRIVILEGED
    }

    if bool(Config.ENFORCE_TENANT_ASSIGNMENT) and not privileged and tenant_id in (None, ""):
        return None

    return {
        "username": resolved,
        "role_id": role_id,
        "employeecode": get_user_employeecode(resolved) or "",
        "tenant_id": tenant_id,
    }


def get_role_permissions(role_id: str) -> List[str]:
    """Load ERP role menus from ``role_permissions`` and ``pdt_role_permissions``."""
    from db import get_role_permissions as erp_get_role_permissions
    from db.pdt_auth import get_pdt_role_permissions, pdt_role_exists
    from permissions import expand_mobile_api_permission_aliases

    rid = (role_id or "").strip()
    if not rid:
        return []

    paths: List[str] = []
    try:
        paths.extend(erp_get_role_permissions(rid))
    except Exception:
        pass
    try:
        if pdt_role_exists(rid):
            paths.extend(get_pdt_role_permissions(rid))
    except Exception:
        pass

    merged: List[str] = []
    seen: set[str] = set()
    for raw in paths:
        p = str(raw or "").strip()
        if p and p not in seen:
            seen.add(p)
            merged.append(p)
    return expand_mobile_api_permission_aliases(merged)


def resolve_login_menu_context(user: Dict[str, Any]) -> Dict[str, Any]:
    """Permissions + mobile drawer menus (same source as ERP Roles & Permissions)."""
    from permissions import resolve_mobile_app_menus

    username = str(user.get("username") or "").strip()
    role_id = str(user.get("role_id") or "").strip()
    permissions = get_role_permissions(role_id) if role_id else []
    allow_all = (not role_id and _is_privileged_username(username)) or _is_privileged_username(
        username
    )
    mobile_menus = resolve_mobile_app_menus(permissions, allow_all=allow_all)
    return {
        "permissions": permissions,
        "mobile_menus": mobile_menus,
        "allow_all_permissions": allow_all,
    }


def change_user_password(username: str, old_password: str, new_password: str) -> None:
    """Update password for ERP or PDT auth user. Raises ValueError on validation failure."""
    from db import update_user_password, verify_user
    from db.pdt_auth import update_pdt_user_password, verify_pdt_user
    from mobile_backend.operation_lock import mobile_operation_lock

    resolved = str(username or "").strip()
    old_pwd = old_password or ""
    new_pwd = new_password or ""
    if not resolved or not old_pwd or not new_pwd:
        raise ValueError("Old password and new password are required")
    if len(new_pwd) < 6:
        raise ValueError("New password must be at least 6 characters long")
    if old_pwd == new_pwd:
        raise ValueError("New password must be different from old password")

    with mobile_operation_lock(
        "change_password",
        resolved.lower(),
        busy_message="Password change is already in progress. Please wait.",
    ):
        if verify_user(resolved, old_pwd):
            if not update_user_password(resolved, old_pwd, new_pwd):
                raise ValueError("Unable to update password")
            return
        if verify_pdt_user(resolved, old_pwd):
            if not update_pdt_user_password(resolved, old_pwd, new_pwd):
                raise ValueError("Unable to update password")
            return
        raise ValueError("Invalid old password")
