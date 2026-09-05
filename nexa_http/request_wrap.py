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


class _FormView:
    """Flask ``request.form``-compatible view with ``to_dict()`` for Starlette ``FormData``."""

    __slots__ = ("_form",)

    def __init__(self, form: Union[FormData, ImmutableMultiDict[str, str], MultiDict[str, str], None]) -> None:
        self._form = form

    def get(self, key: str, default: Any = None) -> Any:
        if self._form is None or not hasattr(self._form, "get"):
            return default
        val = self._form.get(key, default)
        if isinstance(val, UploadFile):
            return default
        return val

    def getlist(self, key: str) -> List[Any]:
        if self._form is None:
            return []
        if hasattr(self._form, "getlist"):
            return [v for v in self._form.getlist(key) if not isinstance(v, UploadFile)]
        one = self.get(key)
        return [one] if one is not None else []

    def __getitem__(self, key: str) -> Any:
        val = self.get(key)
        if val is None:
            raise KeyError(key)
        return val

    def __iter__(self) -> Iterator[str]:
        if self._form is None or not hasattr(self._form, "keys"):
            return iter(())
        return iter(self._form.keys())

    def keys(self):
        if self._form is None or not hasattr(self._form, "keys"):
            return []
        return self._form.keys()

    def to_dict(self, flat: bool = True) -> Dict[str, Any]:
        if self._form is None:
            return {}
        if hasattr(self._form, "to_dict"):
            raw = self._form.to_dict(flat=flat)
            return {k: v for k, v in raw.items() if not isinstance(v, UploadFile)}
        out: Dict[str, Any] = {}
        if hasattr(self._form, "multi_items"):
            for key, value in self._form.multi_items():
                if isinstance(value, UploadFile):
                    continue
                if flat and key in out:
                    continue
                out[key] = value
            return out
        try:
            return dict(self._form)
        except (TypeError, ValueError):
            return {}


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


class _ArgsView:
    """Flask-compatible query string view (supports ``type=`` on ``get``)."""

    __slots__ = ("_params",)

    def __init__(self, params: ImmutableMultiDict[str, str]) -> None:
        self._params = params

    def get(self, key: str, default: Any = None, type: Any = None) -> Any:  # noqa: A002
        if key not in self._params:
            return default
        val = self._params.get(key, default)
        if val is None:
            return default
        if type is not None:
            try:
                return type(val)
            except (TypeError, ValueError):
                return default
        return val

    def getlist(self, key: str) -> List[str]:
        return list(self._params.getlist(key))

    def __getitem__(self, key: str) -> str:
        return self._params[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._params)

    def __len__(self) -> int:
        return len(self._params)

    def __contains__(self, key: object) -> bool:
        return key in self._params

    def keys(self):
        return self._params.keys()

    def values(self):
        return self._params.values()

    def items(self):
        return self._params.items()


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
    def args(self) -> _ArgsView:
        return _ArgsView(self._req.query_params)

    @property
    def form(self) -> _FormView:
        st = self._req.state
        f = getattr(st, "_nexa_form", None)
        return _FormView(f)

    @property
    def files(self) -> _FilesView:
        st = self._req.state
        raw = getattr(st, "_nexa_form", None)
        return _FilesView(raw)

    @property
    def values(self) -> _CombinedMulti:
        return _CombinedMulti(self._req.query_params, self.form.to_dict())

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
