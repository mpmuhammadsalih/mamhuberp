from __future__ import annotations

import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import HTTPConnection, Request
from starlette.responses import Response

from nexa_http import context as ctx
from nexa_http.g_obj import NexaG
from nexa_http.lifecycle import apply_tenant_and_location_from_session

# Starlette 1.x defaults max_part_size to 1 MB, which rejects bulk image ZIPs.
_MAX_FORM_PART_SIZE = 2 * 1024 * 1024 * 1024


class NexaHttpMiddleware(BaseHTTPMiddleware):
    """Bind request context, pre-parse form/JSON for sync view handlers."""

    async def dispatch(self, request: Request, call_next):
        token = ctx.bind_request(request)
        # Sync route handlers run in a thread pool; copy ``contextvars`` there. Re-bind the
        # real ASGI app so ``get_current_app()`` / ``url_for`` work (never trust a stale var).
        scoped = request.scope.get("app")
        if scoped is not None and not isinstance(scoped, HTTPConnection) and hasattr(scoped, "url_path_for"):
            ctx.set_current_app(scoped)
        request.state.nexa_g = NexaG()
        request.state._nexa_session_modified = False
        request.state._nexa_form = None
        request.state._nexa_json = None
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            ct = (request.headers.get("content-type") or "").lower()
            if "application/x-www-form-urlencoded" in ct or "multipart/form-data" in ct:
                try:
                    request.state._nexa_form = await request.form(max_part_size=_MAX_FORM_PART_SIZE)
                except Exception as exc:
                    logging.getLogger(__name__).warning('form parse failed: %s', exc)
                    request.state._nexa_form = None
            elif "application/json" in ct:
                try:
                    request.state._nexa_json = await request.json()
                except Exception:
                    request.state._nexa_json = None
        apply_tenant_and_location_from_session(request)
        from nexa_http.oracle_request_scope import close_scope, init_scope

        init_scope(request)
        try:
            return await call_next(request)
        finally:
            close_scope(request)
            ctx.reset_request(token)
