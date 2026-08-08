from __future__ import annotations

import shutil
from typing import Any, Dict, Iterator, List, Mapping, Optional, Union

from starlette.datastructures import FormData, ImmutableMultiDict, MultiDict, UploadFile
from starlette.requests import Request

from nexa_http import context as ctx


class _UploadAdapter:
    """Flask ``FileStorage``-like wrapper for Starlette ``UploadFile`` (sync ``save`` / ``read``)."""

    __slots__ = ("_upload",)

    def __init__(self, upload: UploadFile) -> None:
        self._upload = upload

    @property
    def filename(self) -> Optional[str]:
        return self._upload.filename

    @property
    def mimetype(self) -> str:
        ct = self._upload.content_type
        return (ct or "") if isinstance(ct, str) else ""

    def save(self, dst: str) -> None:
        self._upload.file.seek(0)
        with open(dst, "wb") as out:
            shutil.copyfileobj(self._upload.file, out)

    def read(self, size: int = -1) -> bytes:
        self._upload.file.seek(0)
        return self._upload.file.read(size)


class _FilesView:
    """Flask ``request.files``-like mapping: only ``UploadFile`` values are exposed."""

    __slots__ = ("_form",)

    def __init__(self, form: Union[FormData, ImmutableMultiDict[str, str], MultiDict[str, str], None]) -> None:
        self._form = form

    def _adapt_upload(self, val: Any) -> Any:
        if isinstance(val, UploadFile):
            return _UploadAdapter(val)
        return None

    def get(self, key: str, default: Any = None) -> Any:
        if self._form is None:
            return default
        if not hasattr(self._form, "get"):
            return default
        val: Any = self._form.get(key)
        if val is None:
            return default
        adapted = self._adapt_upload(val)
        return adapted if adapted is not None else default

    def getlist(self, key: str) -> List[Any]:
        """All uploads for a field (e.g. multiple ``file`` parts in multipart form)."""
        if self._form is None:
            return []
        if hasattr(self._form, "getlist"):
            raw_list = self._form.getlist(key)
        else:
            one = self.get(key)
            raw_list = [one] if one is not None else []
        out: List[Any] = []
        for val in raw_list:
            if isinstance(val, UploadFile):
                adapted = self._adapt_upload(val)
                if adapted is not None:
                    out.append(adapted)
            elif val is not None and hasattr(val, "read"):
                out.append(val)
        return out

    def __getitem__(self, key: str) -> Any:
        val = self.get(key)
        if val is None:
            raise KeyError(key)
        return val


class _CombinedMulti(Mapping[str, Any]):
    """Flask ``request.values``-like read-only merge of query + form (form wins)."""

    def __init__(self, args: Mapping[str, Any], form: Mapping[str, Any]) -> None:
        self._args = args
        self._form = form

    def __getitem__(self, key: str) -> Any:
        if key in self._form:
            return self._form[key]
        return self._args[key]

    def __iter__(self) -> Iterator[str]:
        seen = set(self._args.keys())
        yield from self._args
        for k in self._form:
            if k not in seen:
                yield k

    def __len__(self) -> int:
        return len(set(self._args.keys()) | set(self._form.keys()))

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._form:
            v = self._form.get(key)
            return default if v is None and key not in self._form else v
        return self._args.get(key, default)


class RequestProxy:
    """Flask-like ``request`` bound to the current Starlette ``Request``."""

    @property
    def _req(self) -> Request:
        r = ctx.get_current_request()
        if r is None:
            raise RuntimeError("Working outside of request context.")
        return r

    @property
    def method(self) -> str:
        return self._req.method

    @property
    def path(self) -> str:
        return self._req.url.path

    @property
    def url(self) -> str:
        return str(self._req.url)

    @property
    def args(self) -> ImmutableMultiDict[str, str]:
        return self._req.query_params

    @property
    def form(self) -> Union[FormData, ImmutableMultiDict[str, str], MultiDict[str, str]]:
        st = self._req.state
        f = getattr(st, "_nexa_form", None)
        if f is None:
            return ImmutableMultiDict()
        return f

    @property
    def files(self) -> _FilesView:
        st = self._req.state
        raw = getattr(st, "_nexa_form", None)
        return _FilesView(raw)

    @property
    def values(self) -> _CombinedMulti:
        return _CombinedMulti(self._req.query_params, dict(self.form))

    @property
    def is_json(self) -> bool:
        mt = (self._req.headers.get("content-type") or "").lower()
        return "application/json" in mt

    @property
    def referrer(self) -> Optional[str]:
        return self._req.headers.get("referer")

    @property
    def endpoint(self) -> Optional[str]:
        return getattr(self._req.state, "flask_endpoint", None)

    @property
    def blueprint(self) -> Optional[str]:
        return getattr(self._req.state, "flask_blueprint", None)

    @property
    def script_root(self) -> str:
        """Flask-compatible app root path (ASGI ``root_path``); use for URL building in templates."""
        rp = self._req.scope.get("root_path") or ""
        return (str(rp).rstrip("/") if rp else "")

    def get_json(self, force: bool = False, silent: bool = False) -> Any:
        st = self._req.state
        if hasattr(st, "_nexa_json"):
            return st._nexa_json
        if silent:
            return None
        raise BadRequestMessage("No JSON body")

    def __getattr__(self, name: str) -> Any:
        return getattr(self._req, name)


class BadRequestMessage(Exception):
    pass


request = RequestProxy()
