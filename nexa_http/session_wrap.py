from __future__ import annotations

from typing import Any, MutableMapping, Optional

from starlette.requests import Request

from nexa_http import context as ctx


class SessionProxy(MutableMapping[str, Any]):
    """Mutable proxy to Starlette session dict with a ``.modified`` flag."""

    @property
    def _m(self) -> MutableMapping[str, Any]:
        r = ctx.get_current_request()
        if r is None:
            raise RuntimeError("Working outside of request context.")
        return r.session

    @property
    def modified(self) -> bool:
        r = ctx.get_current_request()
        if r is None:
            return False
        return bool(getattr(r.state, "_nexa_session_modified", False))

    @modified.setter
    def modified(self, v: bool) -> None:
        r = ctx.get_current_request()
        if r is None:
            return
        r.state._nexa_session_modified = bool(v)

    def __getitem__(self, key: str) -> Any:
        return self._m[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._m[key] = value
        self.modified = True

    def __delitem__(self, key: str) -> None:
        del self._m[key]
        self.modified = True

    def __iter__(self):
        return iter(self._m)

    def __len__(self) -> int:
        return len(self._m)

    def get(self, key: str, default: Any = None) -> Any:
        return self._m.get(key, default)

    def clear(self) -> None:
        self._m.clear()
        self.modified = True

    def pop(self, key: str, default: Any = None) -> Any:
        self.modified = True
        return self._m.pop(key, default)

    def setdefault(self, key: str, default: Any = None) -> Any:
        if key not in self._m:
            self.modified = True
        return self._m.setdefault(key, default)

    @property
    def permanent(self) -> bool:
        return bool(self._m.get("_permanent"))

    @permanent.setter
    def permanent(self, v: bool) -> None:
        self._m["_permanent"] = bool(v)
        self.modified = True


session = SessionProxy()
