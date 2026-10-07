"""Shared FastAPI dependencies for the MamaHub storefront API."""
from __future__ import annotations

import os
from typing import Annotated, Any, Dict, Optional

import jwt as pyjwt
from fastapi import Depends, Header, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from mobile_backend.jwt_compat import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


def default_location_code() -> int:
    raw = os.getenv('DEFAULT_LOCATION_CODE', '1').strip()
    try:
        return int(raw)
    except ValueError:
        return 1


def resolve_location_code(location_code: Optional[int] = None) -> int:
    if location_code is not None:
        return int(location_code)
    return default_location_code()


def location_query(
    location_code: Optional[int] = Query(None, description='Branch LOCATIONCODE'),
) -> int:
    return resolve_location_code(location_code)


def guest_cart_token(
    x_guest_cart_token: Optional[str] = Header(default=None, alias='X-Guest-Cart-Token'),
) -> Optional[str]:
    token = (x_guest_cart_token or '').strip()
    return token or None


def _optional_bearer(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> Optional[str]:
    if credentials is None or not (credentials.credentials or '').strip():
        return None
    return credentials.credentials.strip()


def optional_customer(
    token: Annotated[Optional[str], Depends(_optional_bearer)],
) -> Optional[Dict[str, Any]]:
    if not token:
        return None
    try:
        claims = decode_access_token(token)
    except pyjwt.PyJWTError:
        # Expired/invalid token — treat as guest for optional-auth routes (cart, catalog).
        return None
    user_type = str(claims.get('user_type') or '').upper()
    if user_type and user_type not in ('CUSTOMER', 'STAFF', 'SYSTEM'):
        pass
    return claims


def require_customer(
    claims: Annotated[Optional[Dict[str, Any]], Depends(optional_customer)],
) -> Dict[str, Any]:
    if not claims:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Not authenticated')
    return claims


def customer_user_id(claims: Dict[str, Any]) -> int:
    try:
        return int(claims.get('sub') or claims.get('user_id') or 0)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token subject') from exc


def require_admin(
    claims: Annotated[Optional[Dict[str, Any]], Depends(optional_customer)],
) -> Dict[str, Any]:
    if not claims:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Not authenticated')
    roles = claims.get('roles') or []
    if isinstance(roles, str):
        roles = [roles]
    allowed = {'ADMIN', 'SUPER_ADMIN'}
    if not any(str(role).upper() in allowed for role in roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Admin access required')
    if str(claims.get('user_type') or '').upper() not in ('', 'STAFF', 'SYSTEM'):
        # Customer tokens must not access admin routes even if roles were spoofed.
        if str(claims.get('user_type') or '').upper() == 'CUSTOMER':
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Admin access required')
    return claims
