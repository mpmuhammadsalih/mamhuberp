"""Wire mobile JWT API into the main Nexa Dynamics FastAPI app."""
from __future__ import annotations

import logging

import jwt as pyjwt
from db.oracle_driver import cx_Oracle
from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import (
    http_exception_handler as default_http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from mobile_backend.config import Config
from mobile_backend.database.oracle_pool import (
    close_oracle_scope,
    init_oracle_pool,
    init_oracle_scope,
)
from mobile_backend.request_context import bind_current_request, reset_current_request
from mobile_backend.deps_save import SaveNonceReplayError
from mobile_backend.utils.response import http_error_content

logger = logging.getLogger(__name__)


def install_mobile_api(app: FastAPI) -> None:
    if getattr(app.state, "mobile_api_installed", False):
        return
    app.state.mobile_api_installed = True

    init_oracle_pool()

    origins = [o.strip() for o in getattr(Config, "CORS_ORIGINS", ["*"]) if o.strip()] or ["*"]
    allow_all = origins == ["*"] or (len(origins) == 1 and origins[0] == "*")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins if not allow_all else ["*"],
        allow_credentials=not allow_all,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def mobile_api_oracle_scope(request: Request, call_next):
        path = request.url.path or ""
        if not (path.startswith("/api/v1") or path == "/health"):
            return await call_next(request)
        init_oracle_scope(request)
        rtok = bind_current_request(request)
        try:
            return await call_next(request)
        finally:
            close_oracle_scope(request)
            reset_current_request(rtok)

    @app.get("/health", include_in_schema=False)
    def mobile_health():
        return JSONResponse(content={"success": True, "message": "OK", "data": {"status": "healthy"}})

    @app.exception_handler(SaveNonceReplayError)
    async def mobile_save_nonce_replay_handler(request: Request, exc: SaveNonceReplayError):
        if not (request.url.path or "").startswith("/api/v1"):
            raise exc
        return JSONResponse(
            status_code=409,
            content={
                "success": False,
                "message": exc.message,
                "replay_blocked": True,
                "save_nonce": exc.save_nonce,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def mobile_validation_error_handler(request: Request, exc: RequestValidationError):
        path = request.url.path or ""
        if not (path.startswith("/api/v1") or path == "/health"):
            return await request_validation_exception_handler(request, exc)
        lines = []
        for err in exc.errors():
            loc = err.get("loc") or ()
            path = ".".join(str(p) for p in loc if p != "body")
            lines.append(f"{path}: {err.get('msg')}" if path else str(err.get("msg")))
        msg = "; ".join(lines) if lines else "Validation error"
        return JSONResponse(status_code=422, content=http_error_content(msg))

    @app.exception_handler(HTTPException)
    async def mobile_http_exception_handler(request: Request, exc: HTTPException):
        if not (request.url.path or "").startswith("/api/v1"):
            return await default_http_exception_handler(request, exc)
        detail = exc.detail
        msg = detail if isinstance(detail, str) else str(detail)
        return JSONResponse(status_code=exc.status_code, content=http_error_content(msg))

    @app.exception_handler(cx_Oracle.DatabaseError)
    async def mobile_oracle_error_handler(request: Request, exc: cx_Oracle.DatabaseError):
        if not (request.url.path or "").startswith("/api/v1"):
            raise exc
        err = exc.args[0] if exc.args else exc
        msg = getattr(err, "message", None) or str(exc)
        if Config.DEBUG:
            logger.exception("Mobile API Oracle error")
        else:
            logger.warning("Mobile API Oracle error: %s", msg)
        return JSONResponse(status_code=400, content=http_error_content(msg))

    @app.exception_handler(ValueError)
    async def mobile_value_error_handler(request: Request, exc: ValueError):
        if not (request.url.path or "").startswith("/api/v1"):
            raise exc
        if Config.DEBUG:
            logger.exception("Mobile API validation error")
        else:
            logger.warning("Mobile API validation error: %s", exc)
        return JSONResponse(status_code=400, content=http_error_content(str(exc)))

    @app.exception_handler(pyjwt.PyJWTError)
    async def mobile_jwt_error_handler(request: Request, exc: pyjwt.PyJWTError):
        if not (request.url.path or "").startswith("/api/v1"):
            raise exc
        return JSONResponse(status_code=401, content=http_error_content("Invalid or expired token"))

    if not (Config.JWT_SECRET_KEY or "").strip():
        logger.warning(
            "JWT_SECRET_KEY is not set — mobile API /api/v1/auth will fail until you set JWT_SECRET_KEY in .env"
        )
