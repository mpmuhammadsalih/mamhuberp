"""Shared helpers for the ecommerce addon."""
from __future__ import annotations

from typing import Any

from db import get_location_info_by_dbkey
from nexa_http import session


def resolve_location_code() -> int:
    """Branch/location scope — same pattern as itemmaster."""
    v = session.get('location_code')
    if v is not None:
        try:
            if str(v).isdigit():
                return int(v)
        except (TypeError, ValueError):
            pass
    try:
        info = get_location_info_by_dbkey(None) or {}
        loc = info.get('locationcode')
        if loc is not None:
            return int(loc) if isinstance(loc, (int, float)) else int(str(loc).strip())
    except Exception:
        pass
    return 1


def fmt_money(value: Any) -> str:
    try:
        return f'{float(value or 0):,.2f}'
    except (TypeError, ValueError):
        return '0.00'
