"""MamaHub-compatible API response helpers."""
from __future__ import annotations

from math import ceil
from typing import Any, Dict, Optional


def build_pagination_meta(
    *,
    page: int,
    page_size: int,
    total_records: int,
) -> Dict[str, Any]:
    total_pages = ceil(total_records / page_size) if page_size > 0 else 0
    return {
        'page': page,
        'page_size': page_size,
        'total_records': total_records,
        'total_pages': total_pages,
    }


def success_response(
    data: Any = None,
    *,
    message: str = 'Success',
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        'success': True,
        'message': message,
        'data': data,
        'errors': None,
    }
    if meta is not None:
        payload['meta'] = meta
    return payload


def error_response(message: str, *, errors: Any = None) -> Dict[str, Any]:
    return {
        'success': False,
        'message': message,
        'data': None,
        'errors': errors,
    }
