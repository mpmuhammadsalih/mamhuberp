"""Customer auth against APP_USER."""
from __future__ import annotations

import hashlib
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

import bcrypt
from db import _get_connection, _safe_rows, _table_exists

import jwt as pyjwt
from mobile_backend.jwt_compat import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
)

from storefront_backend.services.email import send_password_reset_email, smtp_configured
from storefront_backend.services.whatsapp import phone_to_e164
from storefront_backend.services.schema_bootstrap import (
    _invalidate_app_user_cache,
    ensure_app_user_schema,
    ensure_password_reset_schema,
)

_RESET_TOKEN_TTL_MINUTES = 60
_FORGOT_PASSWORD_MESSAGE = (
    'If an account exists for that email, we sent password reset instructions.'
)


def _users_ready() -> bool:
    if _table_exists('APP_USER'):
        return True
    try:
        ensure_app_user_schema()
    except Exception:
        _invalidate_app_user_cache()
        return False
    return _table_exists('APP_USER')


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def _verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
    except ValueError:
        return False


def _profile_from_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'user_id': int(row['user_id']),
        'username': row.get('username'),
        'email': row.get('email'),
        'first_name': row.get('first_name'),
        'last_name': row.get('last_name'),
        'mobile': row.get('mobile'),
        'user_type': row.get('user_type') or 'CUSTOMER',
        'account_status': row.get('account_status') or 'ACTIVE',
        'email_verified': bool(int(row.get('email_verified') or 0)),
        'mobile_verified': bool(int(row.get('mobile_verified') or 0)),
        'preferred_language': row.get('preferred_language') or 'en',
        'roles': ['CUSTOMER'],
    }


def _issue_tokens(user_id: int, user_type: str = 'CUSTOMER') -> Dict[str, Any]:
    claims = {'user_type': user_type, 'roles': ['CUSTOMER']}
    access = create_access_token(str(user_id), additional_claims=claims)
    refresh = create_refresh_token(str(user_id), additional_claims=claims)
    minutes = int(os.getenv('JWT_ACCESS_MINUTES', '30'))
    return {
        'access_token': access,
        'refresh_token': refresh,
        'token_type': 'bearer',
        'expires_in': minutes * 60,
    }


def normalize_mobile(mobile: str) -> Tuple[bool, str, Optional[str]]:
    raw = (mobile or '').strip()
    if not raw:
        return False, 'Mobile number is required.', None
    e164 = phone_to_e164(raw)
    if not e164.startswith('+974') or len(e164) != 12:
        return False, 'Enter a valid Qatar mobile number (8 digits or +974…).', None
    local = e164[4:]
    if not local.isdigit() or len(local) != 8:
        return False, 'Enter a valid Qatar mobile number (8 digits or +974…).', None
    return True, '', e164


def register_customer(
    *,
    email: str,
    password: str,
    first_name: str,
    last_name: str,
    mobile: str,
    preferred_language: str = 'en',
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    if not _users_ready():
        return False, 'APP_USER table not available', None
    email_norm = email.strip().lower()
    if not email_norm or not password:
        return False, 'Email and password are required', None
    ok_mobile, mobile_msg, mobile_norm = normalize_mobile(mobile)
    if not ok_mobile or not mobile_norm:
        return False, mobile_msg, None
    from storefront_backend.services.erp_customer import (
        DuplicateCustomerError,
        find_email_duplicate,
        find_mobile_duplicate,
        validate_email,
    )
    ok_email, email_msg = validate_email(email_norm, required=True)
    if not ok_email:
        return False, email_msg, None
    existing = _safe_rows(
        'SELECT USER_ID FROM APP_USER WHERE LOWER(EMAIL) = :email',
        {'email': email_norm},
    )
    if existing:
        return False, 'Email is already registered', None
    mobile_digits = re.sub(r'\D+', '', mobile_norm)
    mobile_last8 = mobile_digits[-8:] if len(mobile_digits) >= 8 else mobile_digits
    if mobile_last8:
        taken_mobile = _safe_rows(
            """
            SELECT USER_ID FROM APP_USER
            WHERE REGEXP_REPLACE(NVL(MOBILE, ''), '[^0-9]', '') LIKE :q
            FETCH FIRST 1 ROWS ONLY
            """,
            {'q': f'%{mobile_last8}%'},
        )
        if taken_mobile:
            return False, 'Mobile number is already registered', None
    try:
        from storefront_backend.deps import resolve_location_code
        loc = resolve_location_code()
    except Exception:
        loc = 1
    email_dup = find_email_duplicate(email_norm, location_code=loc)
    mobile_dup = find_mobile_duplicate(mobile_norm, location_code=loc)
    if email_dup and email_dup != mobile_dup:
        return False, f'Email already used by customer {email_dup}.', None
    username_base = re.sub(r'[^a-z0-9]+', '.', email_norm.split('@')[0]).strip('.') or 'customer'
    username = username_base
    suffix = 1
    while _safe_rows('SELECT USER_ID FROM APP_USER WHERE USERNAME = :u', {'u': username}):
        username = f'{username_base}{suffix}'
        suffix += 1
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT SEQ_USER_ID.NEXTVAL AS id FROM DUAL')
                user_id = int((cur.fetchone() or [0])[0])
                cur.execute(
                    """
                    INSERT INTO APP_USER (
                        USER_ID, USERNAME, EMAIL, MOBILE, PASSWORD_HASH,
                        FIRST_NAME, LAST_NAME, USER_TYPE, ACCOUNT_STATUS,
                        EMAIL_VERIFIED, MOBILE_VERIFIED, PREFERRED_LANGUAGE, IS_ACTIVE, CREATED_AT
                    ) VALUES (
                        :user_id, :username, :email, :mobile, :password_hash,
                        :first_name, :last_name, 'CUSTOMER', 'ACTIVE',
                        0, 0, :preferred_language, 1, SYSTIMESTAMP
                    )
                    """,
                    {
                        'user_id': user_id,
                        'username': username,
                        'email': email_norm,
                        'mobile': mobile_norm,
                        'password_hash': _hash_password(password),
                        'first_name': first_name.strip(),
                        'last_name': last_name.strip(),
                        'preferred_language': preferred_language or 'en',
                    },
                )
            conn.commit()
        try:
            from storefront_backend.services.erp_customer import upsert_erp_customer
            from storefront_backend.deps import resolve_location_code
            upsert_erp_customer(
                channel='WEB',
                name=f'{first_name.strip()} {last_name.strip()}'.strip(),
                mobile=mobile_norm,
                email=email_norm,
                location_code=resolve_location_code(),
            )
        except DuplicateCustomerError as exc:
            return False, str(exc), None
        except Exception:
            pass
        profile = get_profile(user_id)
        return True, 'Registration successful', profile
    except Exception as exc:  # noqa: BLE001
        return False, str(exc), None


def login_customer(*, email: str, password: str) -> Tuple[bool, str, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    if not _users_ready():
        return False, 'APP_USER table not available', None, None
    rows = _safe_rows(
        """
        SELECT
            USER_ID AS user_id,
            USERNAME AS username,
            EMAIL AS email,
            PASSWORD_HASH AS password_hash,
            FIRST_NAME AS first_name,
            LAST_NAME AS last_name,
            MOBILE AS mobile,
            USER_TYPE AS user_type,
            ACCOUNT_STATUS AS account_status,
            EMAIL_VERIFIED AS email_verified,
            MOBILE_VERIFIED AS mobile_verified,
            PREFERRED_LANGUAGE AS preferred_language
        FROM APP_USER
        WHERE LOWER(EMAIL) = :email AND IS_ACTIVE = 1
        """,
        {'email': email.strip().lower()},
    )
    if not rows:
        return False, 'Invalid email or password', None, None
    row = rows[0]
    if str(row.get('account_status') or '').upper() == 'LOCKED':
        return False, 'Account is locked. Try again later.', None, None
    if not _verify_password(password, str(row.get('password_hash') or '')):
        return False, 'Invalid email or password', None, None
    profile = _profile_from_row(row)
    tokens = _issue_tokens(int(row['user_id']), str(row.get('user_type') or 'CUSTOMER'))
    return True, 'Login successful', tokens, profile


def refresh_customer_session(refresh_token: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """Issue new access + refresh tokens from a valid customer refresh token."""
    raw = (refresh_token or '').strip()
    if not raw:
        return False, 'Refresh token is required.', None
    if not _users_ready():
        return False, 'Account service is unavailable.', None
    try:
        claims = decode_refresh_token(raw)
    except pyjwt.PyJWTError:
        return False, 'Session expired. Please sign in again.', None

    user_type = str(claims.get('user_type') or '').upper()
    if user_type and user_type != 'CUSTOMER':
        return False, 'Invalid session.', None

    try:
        user_id = int(claims.get('sub') or 0)
    except (TypeError, ValueError):
        return False, 'Invalid session.', None
    if user_id <= 0:
        return False, 'Invalid session.', None

    rows = _safe_rows(
        """
        SELECT
            USER_ID AS user_id,
            USER_TYPE AS user_type,
            ACCOUNT_STATUS AS account_status,
            IS_ACTIVE AS is_active
        FROM APP_USER
        WHERE USER_ID = :user_id
        """,
        {'user_id': user_id},
    )
    if not rows:
        return False, 'Account not found.', None
    row = rows[0]
    if not int(row.get('is_active') or 0):
        return False, 'Account is not active.', None
    if str(row.get('account_status') or '').upper() == 'LOCKED':
        return False, 'Account is locked.', None
    if str(row.get('user_type') or '').upper() != 'CUSTOMER':
        return False, 'Invalid session.', None

    tokens = _issue_tokens(user_id, 'CUSTOMER')
    return True, 'Session refreshed.', tokens


def update_customer_profile(*, user_id: int, mobile: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    if not _users_ready():
        return False, 'APP_USER table not available', None
    ok_mobile, mobile_msg, mobile_norm = normalize_mobile(mobile)
    if not ok_mobile or not mobile_norm:
        return False, mobile_msg, None
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE APP_USER
                    SET MOBILE = :mobile
                    WHERE USER_ID = :user_id AND IS_ACTIVE = 1
                    """,
                    {'mobile': mobile_norm, 'user_id': int(user_id)},
                )
                if cur.rowcount == 0:
                    return False, 'User not found', None
            conn.commit()
        profile = get_profile(user_id)
        return True, 'Profile updated successfully', profile
    except Exception as exc:  # noqa: BLE001
        return False, str(exc), None


def get_profile(user_id: int) -> Optional[Dict[str, Any]]:
    rows = _safe_rows(
        """
        SELECT
            USER_ID AS user_id,
            USERNAME AS username,
            EMAIL AS email,
            FIRST_NAME AS first_name,
            LAST_NAME AS last_name,
            MOBILE AS mobile,
            USER_TYPE AS user_type,
            ACCOUNT_STATUS AS account_status,
            EMAIL_VERIFIED AS email_verified,
            MOBILE_VERIFIED AS mobile_verified,
            PREFERRED_LANGUAGE AS preferred_language
        FROM APP_USER
        WHERE USER_ID = :user_id AND IS_ACTIVE = 1
        """,
        {'user_id': int(user_id)},
    )
    return _profile_from_row(rows[0]) if rows else None


def _storefront_base_url() -> str:
    base = (os.getenv('STOREFRONT_BASE_URL') or 'http://localhost:5173').strip().rstrip('/')
    return base or 'http://localhost:5173'


def _hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def _password_reset_ready() -> bool:
    if _table_exists('MH_PASSWORD_RESET'):
        return True
    try:
        ensure_password_reset_schema()
    except Exception:
        return False
    return _table_exists('MH_PASSWORD_RESET')


def request_password_reset(*, email: str) -> Tuple[bool, str]:
    """Send a password reset email if the customer account exists."""
    if not _users_ready():
        return False, 'Account service is unavailable.'
    if not smtp_configured():
        return False, (
            'Password reset email is not configured. '
            'Set SMTP_USER and SMTP_PASSWORD (Gmail App Password) in Nova .env, then restart the server.'
        )

    email_norm = email.strip().lower()
    if not email_norm:
        return False, 'Email is required.'

    rows = _safe_rows(
        """
        SELECT
            USER_ID AS user_id,
            EMAIL AS email,
            FIRST_NAME AS first_name,
            USER_TYPE AS user_type,
            ACCOUNT_STATUS AS account_status
        FROM APP_USER
        WHERE LOWER(EMAIL) = :email AND IS_ACTIVE = 1
        """,
        {'email': email_norm},
    )
    if not rows:
        return True, _FORGOT_PASSWORD_MESSAGE

    row = rows[0]
    if str(row.get('user_type') or '').upper() != 'CUSTOMER':
        return True, _FORGOT_PASSWORD_MESSAGE
    if str(row.get('account_status') or '').upper() == 'LOCKED':
        return True, _FORGOT_PASSWORD_MESSAGE

    if not _password_reset_ready():
        return False, 'Password reset is unavailable. Try again later.'

    user_id = int(row['user_id'])
    token = secrets.token_urlsafe(32)
    token_hash = _hash_reset_token(token)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=_RESET_TOKEN_TTL_MINUTES)

    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE MH_PASSWORD_RESET
                    SET USED_AT = SYSTIMESTAMP
                    WHERE USER_ID = :user_id AND USED_AT IS NULL
                    """,
                    {'user_id': user_id},
                )
                cur.execute('SELECT SEQ_MH_PASSWORD_RESET_ID.NEXTVAL AS id FROM DUAL')
                reset_id = int((cur.fetchone() or [0])[0])
                cur.execute(
                    """
                    INSERT INTO MH_PASSWORD_RESET (
                        RESET_ID, USER_ID, TOKEN_HASH, EXPIRES_AT, CREATED_AT
                    ) VALUES (
                        :reset_id, :user_id, :token_hash, :expires_at, SYSTIMESTAMP
                    )
                    """,
                    {
                        'reset_id': reset_id,
                        'user_id': user_id,
                        'token_hash': token_hash,
                        'expires_at': expires_at,
                    },
                )
            conn.commit()
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)

    reset_url = f'{_storefront_base_url()}/reset-password?token={token}'
    ok, err = send_password_reset_email(
        to=str(row.get('email') or email_norm),
        reset_url=reset_url,
        first_name=str(row.get('first_name') or ''),
    )
    if not ok:
        return False, err or 'Could not send reset email.'
    return True, _FORGOT_PASSWORD_MESSAGE


def reset_password_with_token(*, token: str, password: str) -> Tuple[bool, str]:
    """Set a new password using a valid reset token."""
    if not _users_ready() or not _password_reset_ready():
        return False, 'Password reset is unavailable.'
    raw_token = (token or '').strip()
    if not raw_token:
        return False, 'Reset token is required.'
    if len(password) < 6:
        return False, 'Password must be at least 6 characters.'
    if not re.search(r'[A-Za-z]', password) or not re.search(r'\d', password):
        return False, 'Password must contain at least one letter and one number.'

    token_hash = _hash_reset_token(raw_token)
    rows = _safe_rows(
        """
        SELECT
            r.RESET_ID AS reset_id,
            r.USER_ID AS user_id,
            r.EXPIRES_AT AS expires_at,
            u.IS_ACTIVE AS is_active,
            u.USER_TYPE AS user_type
        FROM MH_PASSWORD_RESET r
        JOIN APP_USER u ON u.USER_ID = r.USER_ID
        WHERE r.TOKEN_HASH = :token_hash
          AND r.USED_AT IS NULL
        ORDER BY r.CREATED_AT DESC
        FETCH FIRST 1 ROWS ONLY
        """,
        {'token_hash': token_hash},
    )
    if not rows:
        return False, 'This reset link is invalid or has already been used.'

    row = rows[0]
    if str(row.get('user_type') or '').upper() != 'CUSTOMER':
        return False, 'This reset link is invalid.'
    if not int(row.get('is_active') or 0):
        return False, 'This account is not active.'

    expires_at = row.get('expires_at')
    if expires_at is not None:
        exp = expires_at
        if getattr(exp, 'tzinfo', None) is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < datetime.now(timezone.utc):
            return False, 'This reset link has expired. Request a new one.'

    user_id = int(row['user_id'])
    reset_id = int(row['reset_id'])
    password_hash = _hash_password(password)

    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE APP_USER
                    SET PASSWORD_HASH = :password_hash,
                        FAILED_LOGIN_COUNT = 0,
                        LOCKED_UNTIL = NULL,
                        ACCOUNT_STATUS = 'ACTIVE',
                        MODIFIED_AT = SYSTIMESTAMP
                    WHERE USER_ID = :user_id AND IS_ACTIVE = 1
                    """,
                    {'password_hash': password_hash, 'user_id': user_id},
                )
                if cur.rowcount == 0:
                    conn.rollback()
                    return False, 'Account not found.'
                cur.execute(
                    """
                    UPDATE MH_PASSWORD_RESET
                    SET USED_AT = SYSTIMESTAMP
                    WHERE RESET_ID = :reset_id
                    """,
                    {'reset_id': reset_id},
                )
                cur.execute(
                    """
                    UPDATE MH_PASSWORD_RESET
                    SET USED_AT = SYSTIMESTAMP
                    WHERE USER_ID = :user_id AND USED_AT IS NULL
                    """,
                    {'user_id': user_id},
                )
            conn.commit()
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)

    return True, 'Password updated. You can sign in with your new password.'
