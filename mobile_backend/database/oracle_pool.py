"""Oracle connections via Nexa Dynamics db layer (oracledb, multi-DB auth + tenant)."""
from __future__ import annotations

import logging
from contextvars import ContextVar, Token
from typing import Any, Optional

from db.oracle_driver import cx_Oracle

from config.settings import is_multi_db_mode
from db import _get_connection_auth, _get_tenant_connection, set_active_db_key

from mobile_backend.request_context import get_current_request

_oracle_cv: ContextVar[dict[str, Any] | None] = ContextVar("_mobile_api_oracle_blob", default=None)
_tenant_cv: ContextVar[str | None] = ContextVar("_mobile_api_tenant_id", default=None)

_logger = logging.getLogger(__name__)
_STATE_KEY = "mobile_oracle_blob"


def init_oracle_scope(request) -> dict[str, Any]:
    """Initialize per-request Oracle connection bag (safe for sync routes in thread pool)."""
    blob: dict[str, Any] = {}
    request.state.__setattr__(_STATE_KEY, blob)
    return blob


def close_oracle_scope(request) -> None:
    blob = getattr(request.state, _STATE_KEY, None)
    if not isinstance(blob, dict):
        return
    for key in ("db_conn", "auth_db_conn"):
        conn = blob.pop(key, None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                _logger.debug("Oracle connection close failed", exc_info=True)
    try:
        delattr(request.state, _STATE_KEY)
    except AttributeError:
        pass
    set_active_db_key(None)


def oracle_request_enter() -> Token:
    blob: dict[str, Any] = {}
    return _oracle_cv.set(blob)


def oracle_request_leave(token: Token) -> None:
    blob = _oracle_cv.get()
    if isinstance(blob, dict):
        for key in ("db_conn", "auth_db_conn"):
            conn = blob.pop(key, None)
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    _logger.debug("Oracle connection close failed", exc_info=True)
    try:
        _oracle_cv.reset(token)
    except ValueError:
        pass


def _blob() -> dict[str, Any]:
    req = get_current_request()
    if req is not None:
        blob = getattr(req.state, _STATE_KEY, None)
        if isinstance(blob, dict):
            return blob
    b = _oracle_cv.get()
    if isinstance(b, dict):
        return b
    raise RuntimeError(
        "Mobile API Oracle scope is not active — ensure mobile API middleware wraps this request."
    )


def init_oracle_pool() -> None:
    """No-op — Dynamics db layer manages Oracle connections."""
    return


def set_request_tenant_id(tenant_id: str | None) -> None:
    tid = (tenant_id or "").strip() or None
    _tenant_cv.set(tid)
    set_active_db_key(tid)


def get_request_tenant_id() -> Optional[str]:
    return _tenant_cv.get()


def invalidate_tenant_pool(tenant_id: str) -> None:
    tid = (tenant_id or "").strip()
    if not tid:
        return
    try:
        from db import _tenant_config_cache

        _tenant_config_cache.pop(tid, None)
    except Exception:
        pass


def get_auth_connection() -> cx_Oracle.Connection:
    blob = _blob()
    if "auth_db_conn" not in blob:
        blob["auth_db_conn"] = _get_connection_auth()
    return blob["auth_db_conn"]


def get_connection(tenant_id: str | None = None) -> cx_Oracle.Connection:
    blob = _blob()
    if "db_conn" not in blob:
        tid = (tenant_id or get_request_tenant_id() or "").strip() or None
        if is_multi_db_mode() and tid:
            blob["db_conn"] = _get_tenant_connection(tid)
        else:
            blob["db_conn"] = _get_connection_auth()
    return blob["db_conn"]


def close_connection(_: object | None = None) -> None:
    blob = _blob()
    for key in ("db_conn", "auth_db_conn"):
        conn = blob.pop(key, None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                _logger.debug("Oracle connection close failed", exc_info=True)
