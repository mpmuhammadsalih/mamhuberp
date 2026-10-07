"""In-memory checkout session storage per customer."""
from __future__ import annotations

import os
import threading
import time
from typing import Any, Dict, Optional

_memory_store: dict[int, tuple[dict[str, Any], float]] = {}
_memory_lock = threading.Lock()


def _ttl_seconds() -> int:
    raw = os.getenv('CHECKOUT_SESSION_TTL_SECONDS', '1800').strip()
    try:
        return max(60, int(raw))
    except ValueError:
        return 1800


def get_session(user_id: int) -> Optional[dict[str, Any]]:
    with _memory_lock:
        entry = _memory_store.get(int(user_id))
        if not entry:
            return None
        value, expires_at = entry
        if expires_at <= time.time():
            _memory_store.pop(int(user_id), None)
            return None
        return dict(value)
    return None


def set_session(user_id: int, data: dict[str, Any]) -> None:
    with _memory_lock:
        _memory_store[int(user_id)] = (dict(data), time.time() + _ttl_seconds())


def update_session(user_id: int, updates: dict[str, Any]) -> None:
    current = get_session(user_id) or {}
    current.update(updates)
    set_session(user_id, current)


def delete_session(user_id: int) -> None:
    with _memory_lock:
        _memory_store.pop(int(user_id), None)
