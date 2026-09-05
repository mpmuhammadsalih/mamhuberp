"""Per-session save lock and one-time nonce for fixed-assets form POSTs."""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator

from nexa_http import request, session
from save_nonce import (
    GLOBAL_SAVE_NONCE_SESSION_KEY,
    extract_submitted_save_nonce,
    issue_save_nonce,
    verify_consume_save_nonce,
)

_FA_SAVE_LOCK_KEY = '_fa_save_session_lock_until_v1'
_LOCK_SECONDS = 180.0


class FaSaveBlocked(Exception):
    """Another FA save is in progress for this browser session."""


class FaSaveReplay(Exception):
    """Duplicate or stale save token."""


def try_acquire_fa_save_lock(lock_seconds: float = _LOCK_SECONDS) -> bool:
    now = time.time()
    raw = session.get(_FA_SAVE_LOCK_KEY)
    if raw is not None:
        try:
            until = float(raw)
            if until <= now:
                session.pop(_FA_SAVE_LOCK_KEY, None)
                raw = None
        except (TypeError, ValueError):
            session.pop(_FA_SAVE_LOCK_KEY, None)
            raw = None
    if raw is not None:
        try:
            if float(raw) > now:
                return False
        except (TypeError, ValueError):
            return False
    session[_FA_SAVE_LOCK_KEY] = now + float(lock_seconds)
    session.modified = True
    return True


def release_fa_save_lock() -> None:
    session.pop(_FA_SAVE_LOCK_KEY, None)
    session.modified = True


def verify_fa_save_nonce() -> bool:
    return verify_consume_save_nonce(
        GLOBAL_SAVE_NONCE_SESSION_KEY,
        extract_submitted_save_nonce(request),
    )


def reissue_fa_save_nonce() -> str:
    return issue_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY)


@contextmanager
def fa_form_save_guard(*, require_nonce: bool = True) -> Iterator[None]:
    """Acquire session lock; optionally consume the one-time save nonce."""
    if not try_acquire_fa_save_lock():
        raise FaSaveBlocked(
            'Another fixed-assets save is already in progress for this session. Please wait.',
        )
    try:
        if require_nonce and not verify_fa_save_nonce():
            raise FaSaveReplay(
                'Duplicate or invalid save request. Refresh the page and try again.',
            )
        yield
    finally:
        release_fa_save_lock()


@contextmanager
def fa_post_action_guard() -> Iterator[None]:
    """Session lock for post-only actions (no nonce — idempotent post checks in DB)."""
    if not try_acquire_fa_save_lock():
        raise FaSaveBlocked(
            'Another fixed-assets action is already in progress for this session. Please wait.',
        )
    try:
        yield
    finally:
        release_fa_save_lock()
