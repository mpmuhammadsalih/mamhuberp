"""Issue and verify JWTs compatible with flask-jwt-extended defaults (PyJWT HS256).

Existing mobile bearer tokens issued by Flask continue to validate after API swap.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from mobile_backend.config import Config

JWT_ALG = "HS256"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(identity: str, additional_claims: dict[str, Any] | None = None) -> str:
    now = _now_utc()
    expires = Config.JWT_ACCESS_TOKEN_EXPIRES
    if expires is None:
        raise RuntimeError("JWT_ACCESS_TOKEN_EXPIRES must be configured")
    data: dict[str, Any] = {
        "fresh": False,
        "iat": now,
        "jti": str(uuid.uuid4()),
        "type": "access",
        "sub": identity,
        "exp": now + expires,
    }
    if additional_claims:
        data.update(additional_claims)
    token = jwt.encode(data, Config.JWT_SECRET_KEY, algorithm=JWT_ALG)
    return token if isinstance(token, str) else token.decode()


def create_refresh_token(identity: str, additional_claims: dict[str, Any] | None = None) -> str:
    now = _now_utc()
    expires = Config.JWT_REFRESH_TOKEN_EXPIRES
    if expires is None:
        raise RuntimeError("JWT_REFRESH_TOKEN_EXPIRES must be configured")
    data: dict[str, Any] = {
        "fresh": False,
        "iat": now,
        "jti": str(uuid.uuid4()),
        "type": "refresh",
        "sub": identity,
        "exp": now + expires,
    }
    if additional_claims:
        data.update(additional_claims)
    token = jwt.encode(data, Config.JWT_SECRET_KEY, algorithm=JWT_ALG)
    return token if isinstance(token, str) else token.decode()


def decode_access_token(encoded: str) -> dict[str, Any]:
    decoded: dict[str, Any] = jwt.decode(
        encoded,
        Config.JWT_SECRET_KEY,
        algorithms=[JWT_ALG],
        options={"verify_aud": False},
    )
    tok_type = decoded.get("type") or "access"
    if tok_type != "access":
        raise jwt.InvalidTokenError("Not an access token")
    return decoded


def decode_refresh_token(encoded: str) -> dict[str, Any]:
    decoded: dict[str, Any] = jwt.decode(
        encoded,
        Config.JWT_SECRET_KEY,
        algorithms=[JWT_ALG],
        options={"verify_aud": False},
    )
    tok_type = decoded.get("type") or "access"
    if tok_type != "refresh":
        raise jwt.InvalidTokenError("Not a refresh token")
    return decoded


def jwt_identity(payload: dict[str, Any]) -> str:
    return str(payload.get("sub") or "")
