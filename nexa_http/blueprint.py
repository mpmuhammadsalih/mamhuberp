from __future__ import annotations

import re
from functools import wraps
from pathlib import Path
from typing import Any, Callable, List, Optional, Sequence, TypeVar

from fastapi import APIRouter
from fastapi.staticfiles import StaticFiles

from nexa_http import static_registry
from nexa_http import templates_m

F = TypeVar("F", bound=Callable[..., Any])

_FLASK_CONVERTER = re.compile(r"<(\s*[^>]+?\s*)>")


def flask_rule_to_openapi_path(rule: str) -> str:
    """Translate Flask Werkzeug rules (``<int:id>``) to Starlette/FastAPI ``{id:int}``."""

    def repl(m: re.Match[str]) -> str:
        inner = m.group(1).strip()
        if ":" in inner:
            conv, name = inner.split(":", 1)
            conv = conv.strip().lower()
            name = name.strip()
            if conv == "int":
                return f"{{{name}:int}}"
            if conv == "float":
                return f"{{{name}:float}}"
            if conv == "path":
                return f"{{{name}:path}}"
            return f"{{{name}}}"
        return f"{{{inner}}}"

    return _FLASK_CONVERTER.sub(repl, rule)


class NexaAPIRouter(APIRouter):
    """APIRouter with Flask-like ``.route``, ``before_request``, ``after_request``, ``teardown_request``."""

    _flask_blueprint_name: str = ""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._before_request_hooks: List[Callable[[], Any]] = []
        self._after_request_hooks: List[Callable[[Any], Any]] = []
        self._teardown_request_hooks: List[Callable[[Any], None]] = []

    def before_request(self, fn: Callable[[], Any]) -> Callable[[], Any]:
        self._before_request_hooks.append(fn)
        return fn

    def after_request(self, fn: Callable[[Any], Any]) -> Callable[[Any], Any]:
        self._after_request_hooks.append(fn)
        return fn

    def teardown_request(self, fn: Callable[[Any], None]) -> Callable[[Any], None]:
        self._teardown_request_hooks.append(fn)
        return fn

    def route(self, rule: str, **options: Any) -> Callable[[F], F]:
        methods_raw = options.pop("methods", None)
        if methods_raw is None:
            methods: Sequence[str] = ("GET",)
        elif isinstance(methods_raw, str):
            methods = (methods_raw,)
        else:
            methods = tuple(methods_raw)
        endpoint_override: Optional[str] = options.pop("endpoint", None)
        options.pop("strict_slashes", None)
        options.pop("defaults", None)
        options.pop("subdomain", None)
        options.pop("provide_automatic_options", None)
        for k in list(options.keys()):
            if k not in ("response_class", "summary", "description", "deprecated", "tags"):
                options.pop(k, None)

        openapi_path = flask_rule_to_openapi_path(rule)
        before = tuple(self._before_request_hooks)
        after = tuple(self._after_request_hooks)
        teardown = tuple(self._teardown_request_hooks)

        def decorator(f: F) -> F:
            ep = endpoint_override or getattr(f, "__name__", "view")
            route_name = f"{self._flask_blueprint_name}__{ep}"

            @wraps(f)
            def wrapped(*args: Any, **kwargs: Any):
                exc: Any = None
                resp: Any = None
                try:
                    for h in before:
                        r = h()
                        if r is not None:
                            resp = r
                            break
                    if resp is None:
                        resp = f(*args, **kwargs)
                except BaseException as e:
                    exc = e
                    raise
                finally:
                    for h in teardown:
                        h(exc)
                if exc is None and resp is not None:
                    for h in after:
                        resp = h(resp) or resp
                return resp

            self.add_api_route(
                openapi_path,
                wrapped,
                methods=list(methods),
                name=route_name,
                **options,
            )
            return f

        return decorator


def Blueprint(
    name: str,
    import_name: str,
    url_prefix: Optional[str] = None,
    template_folder: Optional[str] = None,
    static_folder: Optional[str] = None,
    static_url_path: Optional[str] = None,
    **kwargs: Any,
) -> NexaAPIRouter:
    _ = import_name
    _ = kwargs
    prefix = (url_prefix or "").rstrip("/")
    if prefix and not prefix.startswith("/"):
        prefix = "/" + prefix
    rt_kw: dict[str, Any] = {"tags": [name]}
    if prefix:
        rt_kw["prefix"] = prefix
    router = NexaAPIRouter(**rt_kw)
    router._flask_blueprint_name = name
    if template_folder:
        templates_m.register_template_folder(template_folder)
    if static_folder:
        sf_path = Path(static_folder).resolve()
        if sf_path.is_dir():
            sub = (static_url_path or "static").strip("/") or "static"
            mount_path = f"/{sub}"
            router.mount(mount_path, StaticFiles(directory=str(sf_path)), name=f"{name}__static_mount")
            if prefix:
                base = f"{prefix}{mount_path}".replace("//", "/")
            else:
                base = mount_path
            static_registry.register_blueprint_static(name, base)
    return router
