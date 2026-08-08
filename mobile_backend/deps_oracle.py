"""Per-request Oracle connection scope for mobile API routes (sync-safe)."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request

from mobile_backend.database.oracle_pool import (
    close_oracle_scope,
    init_oracle_scope,
)
from mobile_backend.request_context import bind_current_request, reset_current_request


async def mobile_oracle_scope_dep(request: Request) -> AsyncIterator[None]:
    """Ensure Oracle scope exists when app middleware did not run (e.g. uvicorn reload)."""
    path = request.url.path or ""
    if not path.startswith("/api/v1"):
        yield
        return

    owned = not isinstance(getattr(request.state, "mobile_oracle_blob", None), dict)
    if owned:
        init_oracle_scope(request)
    rtok = bind_current_request(request)
    try:
        yield
    finally:
        reset_current_request(rtok)
        if owned:
            close_oracle_scope(request)
