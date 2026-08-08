"""Per-user / per-document save locks — same idea as ERP session locks.

Complements save-nonce (replay protection):
- save-nonce → one successful commit per token (save once)
- operation lock → serialize concurrent saves for the same user/doc

Uses an in-process TTL lock keyed by tenant + user + operation + document.
"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from typing import Iterator

from mobile_backend.request_context import get_jwt


class OperationBusyError(Exception):
    """Raised when another save/post for the same operation is already running."""

    def __init__(self, message: str | None = None):
        self.message = message or (
            "A save is already in progress for this document. Please wait until it completes."
        )
        super().__init__(self.message)


_LOCKS: dict[str, float] = {}
_GUARD = threading.Lock()


def _claims_key_parts() -> tuple[str, str]:
    try:
        claims = get_jwt()
    except Exception:
        return "anon", ""
    user = str(claims.get("sub") or "mobile").strip() or "mobile"
    tenant = str(claims.get("tenant_id") or "").strip()
    return user, tenant


def _lock_key(operation: str, document_id: str = "") -> str:
    user, tenant = _claims_key_parts()
    op = str(operation or "save").strip().lower() or "save"
    doc = str(document_id or "").strip() or "new"
    return f"{tenant}|{user}|{op}|{doc}"


def try_acquire(operation: str, document_id: str = "", *, lock_seconds: float = 90.0) -> bool:
    key = _lock_key(operation, document_id)
    now = time.time()
    until = now + max(5.0, float(lock_seconds or 90.0))
    with _GUARD:
        # Drop expired entries opportunistically.
        expired = [k for k, u in _LOCKS.items() if u <= now]
        for k in expired:
            _LOCKS.pop(k, None)
        current = _LOCKS.get(key)
        if current is not None and current > now:
            return False
        _LOCKS[key] = until
        return True


def release(operation: str, document_id: str = "") -> None:
    key = _lock_key(operation, document_id)
    with _GUARD:
        _LOCKS.pop(key, None)


@contextmanager
def mobile_operation_lock(
    operation: str,
    document_id: str = "",
    *,
    lock_seconds: float = 90.0,
    busy_message: str | None = None,
) -> Iterator[None]:
    """Acquire lock for the duration of a save/post; always release in finally."""
    if not try_acquire(operation, document_id, lock_seconds=lock_seconds):
        raise OperationBusyError(busy_message)
    try:
        yield
    finally:
        release(operation, document_id)
