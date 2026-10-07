"""Helpers so mobile New screens show a free document number.

Peek helpers often return the series next value without skipping rows that already
exist (stuck series after a save that did not advance). Callers should use these
wrappers on open/context so New never reuses a taken number.
"""

from __future__ import annotations

from typing import Any, Callable


def fresh_doc_no(
    *,
    peek_fn: Callable[[], Any],
    exists_fn: Callable[[Any], bool],
    allocate_fn: Callable[[Any], Any],
    max_tries: int = 40,
) -> Any:
    """Return a free document number, allocating past collisions when needed."""
    n = peek_fn()
    for _ in range(max(1, int(max_tries or 40))):
        if n in (None, "", 0, "0"):
            n = allocate_fn(n)
            continue
        try:
            taken = bool(exists_fn(n))
        except Exception:
            taken = False
        if not taken:
            return n
        n = allocate_fn(n)
    return n
