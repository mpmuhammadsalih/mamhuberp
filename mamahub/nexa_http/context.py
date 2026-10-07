from __future__ import annotations

import contextvars
from contextlib import contextmanager
from typing import Any, Iterator, Optional

from starlette.requests import Request

from nexa_http.g_obj import NexaG

_EMPTY_G = NexaG()

_request_var: contextvars.ContextVar[Optional[Request]] = contextvars.ContextVar(
    "nexa_request", default=None
)
_app_var: contextvars.ContextVar[Optional[Any]] = contextvars.ContextVar("nexa_app", default=None)

# Single FastAPI/Starlette instance — visible in **all** threads (sync views use ``run_in_threadpool``).
_root_app_cell: list[Any] = []


def install_root_application(app: Any) -> None:
    """Register the ASGI app once from ``create_app``; used by ``url_for`` (contextvars are not always copied to worker threads)."""
    _root_app_cell.clear()
    if app is not None:
        _root_app_cell.append(app)


def get_root_application() -> Any:
    if not _root_app_cell:
        raise RuntimeError("Root application not installed (create_app did not run).")
    return _root_app_cell[0]


class _AppG:
    """Minimal app-level ``g`` for code that used ``with app.app_context()`` (bootstrap)."""

    __slots__ = ("current_tenant_id",)

    def __init__(self) -> None:
        self.current_tenant_id: Any = None

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def __bool__(self) -> bool:
        return self.current_tenant_id is not None


class _GProxy:
    """Request ``g`` when handling HTTP; falls back to app bootstrap ``g``."""

    def _resolve(self) -> Any:
        req = _request_var.get()
        if req is not None and hasattr(req.state, "nexa_g"):
            return req.state.nexa_g
        bg = _bootstrap_g.get()
        if bg is not None:
            return bg
        return _EMPTY_G

    def __getattr__(self, name: str) -> Any:
        return getattr(self._resolve(), name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            super().__setattr__(name, value)
            return
        setattr(self._resolve(), name, value)

    def __delattr__(self, name: str) -> None:
        delattr(self._resolve(), name)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self._resolve(), key, default)

    def __bool__(self) -> bool:
        return bool(self._resolve())


_bootstrap_g: contextvars.ContextVar[Optional[_AppG]] = contextvars.ContextVar(
    "nexa_bootstrap_g", default=None
)

g = _GProxy()


def has_request_context() -> bool:
    return _request_var.get() is not None


def get_current_request() -> Optional[Request]:
    return _request_var.get()


def set_current_app(app: Any) -> None:
    _app_var.set(app)


def get_current_app() -> Any:
    app = _app_var.get()
    if app is None:
        raise RuntimeError("No application context.")
    return app


@contextmanager
def app_context() -> Iterator[None]:
    """Compatibility shim for ``with app.app_context()`` (used by schema bootstrap)."""
    token = _bootstrap_g.set(_AppG())
    try:
        yield
    finally:
        _bootstrap_g.reset(token)


def bind_request(request: Request) -> contextvars.Token:
    return _request_var.set(request)


def reset_request(token: contextvars.Token) -> None:
    _request_var.reset(token)
