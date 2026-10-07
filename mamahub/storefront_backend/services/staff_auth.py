"""Staff/admin authentication against APP_USER + USER_ROLE."""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

import bcrypt
from db import _safe_rows, _table_exists

from mobile_backend.jwt_compat import create_access_token, create_refresh_token

from storefront_backend.services.schema_bootstrap import (
    _invalidate_app_user_cache,
    ensure_app_user_schema,
)

ADMIN_ROLES = frozenset({'ADMIN', 'SUPER_ADMIN'})


def _users_ready() -> bool:
    if _table_exists('APP_USER'):
        return True
    try:
        ensure_app_user_schema()
    except Exception:
        _invalidate_app_user_cache()
        return False
    return _table_exists('APP_USER')


def _roles_ready() -> bool:
    return _table_exists('ROLE') and _table_exists('USER_ROLE')


def _verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
    except ValueError:
        return False


def _user_roles(user_id: int) -> List[str]:
    if not _roles_ready():
        return []
    rows = _safe_rows(
        """
        SELECT r.ROLE_CODE AS role_code
        FROM USER_ROLE ur
        JOIN ROLE r ON r.ROLE_ID = ur.ROLE_ID
        WHERE ur.USER_ID = :user_id
          AND r.IS_ACTIVE = 1
        ORDER BY r.ROLE_CODE
        """,
        {'user_id': int(user_id)},
    )
    return [str(row['role_code']) for row in rows if row.get('role_code')]


def _profile_from_row(row: Dict[str, Any], roles: List[str]) -> Dict[str, Any]:
    return {
        'user_id': int(row['user_id']),
        'username': row.get('username'),
        'email': row.get('email'),
        'first_name': row.get('first_name'),
        'last_name': row.get('last_name'),
        'user_type': row.get('user_type') or 'STAFF',
        'account_status': row.get('account_status') or 'ACTIVE',
        'roles': roles,
    }


def _issue_tokens(user_id: int, roles: List[str]) -> Dict[str, Any]:
    claims = {'user_type': 'STAFF', 'roles': roles}
    access = create_access_token(str(user_id), additional_claims=claims)
    refresh = create_refresh_token(str(user_id), additional_claims=claims)
    minutes = int(os.getenv('JWT_ACCESS_MINUTES', '30'))
    return {
        'access_token': access,
        'refresh_token': refresh,
        'token_type': 'bearer',
        'expires_in': minutes * 60,
    }


def login_staff(*, email: str, password: str) -> Tuple[bool, str, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    if not _users_ready():
        return False, 'APP_USER table not available', None, None
    email_norm = email.strip().lower()
    rows = _safe_rows(
        """
        SELECT
            USER_ID AS user_id,
            USERNAME AS username,
            EMAIL AS email,
            PASSWORD_HASH AS password_hash,
            FIRST_NAME AS first_name,
            LAST_NAME AS last_name,
            USER_TYPE AS user_type,
            ACCOUNT_STATUS AS account_status
        FROM APP_USER
        WHERE LOWER(EMAIL) = :email AND IS_ACTIVE = 1
        """,
        {'email': email_norm},
    )
    if not rows:
        return False, 'Invalid email or password', None, None
    row = rows[0]
    if str(row.get('account_status') or '').upper() == 'LOCKED':
        return False, 'Account is locked. Try again later.', None, None
    if not _verify_password(password, str(row.get('password_hash') or '')):
        return False, 'Invalid email or password', None, None

    roles = _user_roles(int(row['user_id']))
    if not any(role in ADMIN_ROLES for role in roles):
        return False, 'This account does not have admin access', None, None

    profile = _profile_from_row(row, roles)
    tokens = _issue_tokens(int(row['user_id']), roles)
    return True, 'Login successful', tokens, profile


def get_staff_profile(user_id: int) -> Optional[Dict[str, Any]]:
    rows = _safe_rows(
        """
        SELECT
            USER_ID AS user_id,
            USERNAME AS username,
            EMAIL AS email,
            FIRST_NAME AS first_name,
            LAST_NAME AS last_name,
            USER_TYPE AS user_type,
            ACCOUNT_STATUS AS account_status
        FROM APP_USER
        WHERE USER_ID = :user_id AND IS_ACTIVE = 1
        """,
        {'user_id': int(user_id)},
    )
    if not rows:
        return None
    roles = _user_roles(int(user_id))
    return _profile_from_row(rows[0], roles)
