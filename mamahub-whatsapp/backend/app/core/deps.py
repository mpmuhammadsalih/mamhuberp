"""FastAPI auth and permission dependencies."""
from __future__ import annotations

from typing import Annotated, Optional

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.permissions import Permission, has_permission
from app.core.security import decode_token
from app.database.session import get_db
from app.models.user import User

bearer = HTTPBearer(auto_error=False)


def _token_from_request(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials],
) -> str:
    if credentials and credentials.credentials:
        return credentials.credentials.strip()
    auth = request.headers.get("authorization") or request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    return ""


def get_current_user(
    request: Request,
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(bearer)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    token = _token_from_request(request, credentials)
    if not token:
        raise UnauthorizedError()
    try:
        payload = decode_token(token)
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Invalid or expired token") from exc
    if payload.get("type") != "access":
        raise UnauthorizedError("Invalid token type")
    try:
        user_id = int(payload.get("sub") or 0)
    except (TypeError, ValueError):
        user_id = 0
    user = db.get(User, user_id) if user_id else None
    if user is None and payload.get("username"):
        user = db.query(User).filter(User.username == str(payload.get("username"))).first()
    if not user or int(user.is_active or 0) != 1:
        raise UnauthorizedError("User is inactive or missing")
    return user


def require_permission(*required: Permission):
    def _inner(user: Annotated[User, Depends(get_current_user)]) -> User:
        if required and not has_permission(user.role, required):
            raise ForbiddenError()
        return user

    return _inner


def optional_user(
    request: Request,
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(bearer)],
    db: Annotated[Session, Depends(get_db)],
) -> Optional[User]:
    if not _token_from_request(request, credentials):
        return None
    try:
        return get_current_user(request, credentials, db)
    except HTTPException:
        return None
