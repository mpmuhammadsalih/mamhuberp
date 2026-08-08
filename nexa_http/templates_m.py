from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from jinja2 import ChoiceLoader, Environment, FileSystemLoader, select_autoescape
from starlette.templating import Jinja2Templates

from nexa_http import context as ctx
from nexa_http.flash import get_flashed_messages
from nexa_http.request_wrap import request as request_proxy
from nexa_http.session_wrap import session as session_proxy
from nexa_http.shortcuts import url_for

_extra_template_paths: List[str] = []
_templates: Optional[Jinja2Templates] = None
_context_processors: List[Callable[[], Dict[str, Any]]] = []


def register_template_folder(path: str) -> None:
    abs_p = str(Path(path).resolve())
    if abs_p not in _extra_template_paths:
        _extra_template_paths.append(abs_p)


def register_context_processor(fn: Callable[[], Dict[str, Any]]) -> None:
    _context_processors.append(fn)


def init_templates(root_templates: str) -> None:
    global _templates
    paths = [str(Path(root_templates).resolve())] + list(_extra_template_paths)
    loaders = [FileSystemLoader(p) for p in paths]
    env = Environment(
        loader=ChoiceLoader(loaders),
        autoescape=select_autoescape(["html", "xml"]),
    )
    env.globals["url_for"] = url_for
    env.globals["get_flashed_messages"] = get_flashed_messages
    _templates = Jinja2Templates(env=env)


def render_template(template_name: str, **context: Any):
    templates = _templates
    if templates is None:
        raise RuntimeError("Templates not initialised (call init_templates).")
    req = ctx.get_current_request()
    if req is None:
        raise RuntimeError("render_template outside request context.")
    merged: Dict[str, Any] = {}
    for fn in _context_processors:
        try:
            chunk = fn() or {}
            if isinstance(chunk, dict):
                merged.update(chunk)
        except Exception:
            pass
    merged.update(context)
    merged.setdefault("session", session_proxy)
    merged.setdefault("menu_permissions", [])
    merged.setdefault("allow_all_permissions", False)
    merged.setdefault("has_menu_permission", lambda menu_path: False)
    merged.setdefault("has_any_menu_permission", lambda menu_paths: False)
    merged.setdefault("quick_access_items", [])
    merged.setdefault("outstanding_due_count", 0)
    merged.setdefault("user_transit_only", False)
    merged.setdefault("user_customer_creation", False)
    # Jinja ``request`` must be Flask-compatible (``.args``, ``.form``, ``.values``). Starlette's
    # ``TemplateResponse`` would otherwise inject the raw ASGI request, which has no ``.args``.
    merged.setdefault("request", request_proxy)
    return templates.TemplateResponse(req, template_name, merged, status_code=200)
