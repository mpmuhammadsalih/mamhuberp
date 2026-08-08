"""Oracle connection transaction helper — commit on success, rollback on error.

Use for all insert/update/delete in mobile_backend services.
See ``mobile_backend/MUTATIONS.md``.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator


@contextmanager
def oracle_transaction(conn: Any) -> Iterator[Any]:
    """Wrap insert/update/delete work in a single commit/rollback boundary."""
    try:
        yield conn
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
