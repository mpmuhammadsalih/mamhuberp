from __future__ import annotations

from typing import Any, List, Tuple, Union

from nexa_http.session_wrap import session

_FLASH_KEY = "_flashes"


def flash(message: str, category: str = "message") -> None:
    bucket = session.get(_FLASH_KEY)
    if not isinstance(bucket, list):
        bucket = []
    bucket.append((str(category), str(message)))
    session[_FLASH_KEY] = bucket


def get_flashed_messages(
    with_categories: bool = False,
    category_filter: Union[str, Tuple[str, ...], List[str], None] = None,
) -> Union[List[str], List[Tuple[str, str]]]:
    raw = session.pop(_FLASH_KEY, None)
    if not isinstance(raw, list):
        raw = []
    if category_filter:
        if isinstance(category_filter, str):
            filt = {category_filter}
        else:
            filt = set(category_filter)
        raw = [(c, m) for c, m in raw if c in filt]
    if with_categories:
        return [(str(c), str(m)) for c, m in raw]
    return [str(m) for c, m in raw]
