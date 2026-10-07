from __future__ import annotations

from typing import Any, Dict


class NexaG:
    """Per-request namespace (Flask ``g``)."""

    __slots__ = ("_data",)

    def __init__(self) -> None:
        self._data: Dict[str, Any] = {}

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        if name in self._data:
            return self._data[name]
        raise AttributeError(name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "_data":
            super().__setattr__(name, value)
            return
        if name.startswith("_"):
            super().__setattr__(name, value)
            return
        self._data[name] = value

    def __delattr__(self, name: str) -> None:
        if name in self._data:
            del self._data[name]
        else:
            super().__delattr__(name)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def __bool__(self) -> bool:
        return bool(self._data)

    def __contains__(self, key: object) -> bool:
        return key in self._data
