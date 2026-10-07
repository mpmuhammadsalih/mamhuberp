"""Per-request helpers: JWT claims live on Starlette Request.state for thread-safe sync routes."""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Any

from starlette.requests import Request

_request_cv: ContextVar[Request | None] = ContextVar("_nexa_request_cv", default=None)


def bind_current_request(request: Request) -> Token:
    """Set the active Request for this async context / worker thread (paired with reset_current_request)."""
    return _request_cv.set(request)


def reset_current_request(token: Token) -> None:
    try:
        _request_cv.reset(token)
    except ValueError:
        _request_cv.set(None)


def get_current_request() -> Request | None:
    return _request_cv.get()


def get_jwt() -> dict[str, Any]:
    """Return access- or refresh-token claims set during dependency injection (stored on Request.state)."""
    req = get_current_request()
    if req is not None:
        claims = getattr(req.state, "jwt_claims", None)
        if claims is not None:
            return claims
    raise RuntimeError("JWT context not initialized for this request")


def set_request_jwt_claims(request: Request, claims: dict[str, Any]) -> None:
    """Used by auth dependencies to stash decoded claims."""
    request.state.jwt_claims = claims
