"""Reuse one Oracle connection per HTTP request (tenant + auth when multi-DB)."""
from __future__ import annotations

import os
from typing import Any, Callable, Tuple

_STATE_KEY = 'nexa_oracle_scope'


def scope_enabled() -> bool:
    return (os.getenv('NEXA_REQUEST_DB_SCOPE') or '1').strip().lower() not in (
        '0', 'false', 'no', 'off',
    )


def init_scope(request: Any) -> None:
    if scope_enabled():
        setattr(request.state, _STATE_KEY, {})


def close_scope(request: Any) -> None:
    blob = getattr(request.state, _STATE_KEY, None)
    if not isinstance(blob, dict):
        return
    seen: set[int] = set()
    for conn in blob.values():
        if conn is None:
            continue
        cid = id(conn)
        if cid in seen:
            continue
        seen.add(cid)
        try:
            conn.close()
        except Exception:
            pass
    try:
        delattr(request.state, _STATE_KEY)
    except AttributeError:
        pass


def _blob() -> dict[str, Any] | None:
    from nexa_http.context import get_current_request

    req = get_current_request()
    if req is None:
        return None
    blob = getattr(req.state, _STATE_KEY, None)
    return blob if isinstance(blob, dict) else None


def borrow_connection(kind: str, open_fn: Callable[[], Any]) -> Tuple[Any, bool]:
    """
    Return (connection, is_request_scoped).
    When scoped, caller must not close the connection — middleware closes at end of request.
    """
    if not scope_enabled():
        return open_fn(), False
    blob = _blob()
    if blob is None:
        return open_fn(), False
    try:
        from config.settings import is_multi_db_mode

        key = kind if is_multi_db_mode() else 'shared'
    except Exception:
        key = kind
    conn = blob.get(key)
    if conn is None:
        conn = open_fn()
        blob[key] = conn
    return conn, True
