"""FastAPI dependencies: Bearer access/refresh JWT and RBAC (Flask-compatible)."""

from __future__ import annotations

from typing import Annotated, Any

import jwt as pyjwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.requests import Request

from mobile_backend.jwt_compat import decode_access_token, decode_refresh_token
from mobile_backend.request_context import set_request_jwt_claims

bearer_scheme = HTTPBearer(auto_error=False)


def _require_bearer_credentials(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> str:
    if credentials is None or not (credentials.credentials or "").strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return credentials.credentials


def require_access_claims(
    request: Request,
    token: Annotated[str, Depends(_require_bearer_credentials)],
) -> dict[str, Any]:
    try:
        claims = decode_access_token(token)
    except pyjwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
        ) from exc
    set_request_jwt_claims(request, claims)
    tid = str(claims.get("tenant_id") or "").strip() or None
    if tid:
        from mobile_backend.database.oracle_pool import set_request_tenant_id

        set_request_tenant_id(tid)
    return claims


def require_refresh_claims(
    request: Request,
    token: Annotated[str, Depends(_require_bearer_credentials)],
) -> dict[str, Any]:
    try:
        claims = decode_refresh_token(token)
    except pyjwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        ) from exc
    set_request_jwt_claims(request, claims)
    tid = str(claims.get("tenant_id") or "").strip() or None
    if tid:
        from mobile_backend.database.oracle_pool import set_request_tenant_id

        set_request_tenant_id(tid)
    return claims


_ACCESS_DENIED_DETAIL = (
    "You do not have access to this menu or feature. "
    "Contact your administrator to assign the correct role permissions."
)


def require_any_permission(*permission_keys: str):
    """RBAC — allow if JWT permissions include any of [permission_keys]."""

    keys = tuple(permission_keys)

    async def verify(claims: Annotated[dict[str, Any], Depends(require_access_claims)]) -> None:
        username = str(claims.get("sub") or "").strip().lower()
        permissions = claims.get("permissions", []) or []

        if username in {"admin", "super"}:
            return
        if any(k in permissions for k in keys) or "admin.all" in permissions:
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_ACCESS_DENIED_DETAIL,
        )

    return verify


def require_permission(permission_key: str):
    """RBAC Depends — runs after Bearer access token is validated (cached shared with router deps)."""

    async def verify(claims: Annotated[dict[str, Any], Depends(require_access_claims)]) -> None:
        username = str(claims.get("sub") or "").strip().lower()
        role_id = str(claims.get("role_id") or "").strip()
        permissions = claims.get("permissions", []) or []

        if username in {"admin", "super"}:
            return
        if not role_id or not permissions:
            return
        if permission_key not in permissions and "admin.all" not in permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=_ACCESS_DENIED_DETAIL,
            )

    return verify
