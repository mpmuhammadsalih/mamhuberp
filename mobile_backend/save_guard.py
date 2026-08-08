"""One-time save tokens for mobile JWT API (prevents duplicate POST/PUT/PATCH/DELETE)."""
from __future__ import annotations

import threading
import uuid
from typing import Optional

_lock = threading.Lock()
_store: dict[str, str] = {}


def _user_key(username: str, tenant_id: str | None) -> str:
    return f"{(username or '').strip().lower()}|{(tenant_id or '').strip()}"


def issue_save_nonce(username: str, tenant_id: str | None) -> str:
    nonce = uuid.uuid4().hex
    key = _user_key(username, tenant_id)
    with _lock:
        _store[key] = nonce
    return nonce


def get_save_nonce(username: str, tenant_id: str | None) -> Optional[str]:
    with _lock:
        return _store.get(_user_key(username, tenant_id))


def peek_save_nonce(username: str, tenant_id: str | None, submitted: Optional[str]) -> bool:
    expected = get_save_nonce(username, tenant_id)
    got = (submitted or "").strip()
    return bool(expected and got and got == expected)


def reject_invalid_save_nonce(username: str, tenant_id: str | None, submitted: Optional[str]) -> tuple[bool, str]:
    """Return (valid, current_or_fresh_nonce). On failure, issue a fresh token for the client."""
    if peek_save_nonce(username, tenant_id, submitted):
        current = get_save_nonce(username, tenant_id) or ""
        return True, current
    fresh = issue_save_nonce(username, tenant_id)
    return False, fresh


def commit_save_nonce(username: str, tenant_id: str | None, submitted: Optional[str]) -> bool:
    """Consume the one-time token after a successful mutation."""
    key = _user_key(username, tenant_id)
    got = (submitted or "").strip()
    with _lock:
        expected = _store.get(key)
        if not (expected and got and got == expected):
            return False
        _store.pop(key, None)
        return True


def rotate_save_nonce(username: str, tenant_id: str | None) -> str:
    return issue_save_nonce(username, tenant_id)


def clear_save_nonce(username: str, tenant_id: str | None) -> None:
    key = _user_key(username, tenant_id)
    with _lock:
        _store.pop(key, None)
