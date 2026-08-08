"""Register FastAPI routers from Odoo-style addons (__manifest__.py driven)."""
from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any, List, Tuple

from starlette.routing import Mount

from addons.core.manifest_loader import iter_installable_addons

if TYPE_CHECKING:
    from fastapi import FastAPI


def _import_router(bp_ref: str):
    """Import APIRouter from ``'package.module:attr'`` (``.`` or ``:`` style)."""
    mod_name, sep, attr = bp_ref.partition(":")
    mod_name = mod_name.strip()
    attr = (attr or "").strip() or "bp"
    if not mod_name:
        raise ValueError(f"Invalid blueprint_ref: {bp_ref!r}")
    module = importlib.import_module(mod_name)
    return getattr(module, attr)


def register_addon_routers(app: "FastAPI") -> List[Tuple[str, str]]:
    """
    Register each installable addon whose manifest lists ``flask.blueprint_ref``
    (legacy key; value is still ``module:bp`` pointing at the router object).

    Returns list of ``(technical_name, router_tags/name)`` registered.
    """
    done: List[Tuple[str, str]] = []
    for tech, _path, mf in iter_installable_addons():
        flask_cfg = mf.get("flask") or {}
        bp_ref = (flask_cfg.get("blueprint_ref") or "").strip()
        if not bp_ref:
            print(f"[addons] skip {tech}: manifest has no flask.blueprint_ref")
            continue
        try:
            router = _import_router(bp_ref)
            name = getattr(router, "_flask_blueprint_name", None) or getattr(router, "tags", [""])[0] or str(router)
            prefix = (getattr(router, "prefix", None) or "").rstrip("/")
            # FastAPI ``include_router`` does not copy ``Mount`` children; promote static mounts to the app.
            # Critical: remove Mounts from the router first. Leaving ``Mount("/static")`` on a prefixed
            # router still matches app-root ``/static/...`` and 404s before the real static mount.
            addon_mounts = [(r.path, r.app) for r in list(router.routes) if isinstance(r, Mount)]
            if addon_mounts:
                router.routes[:] = [r for r in router.routes if not isinstance(r, Mount)]
            app.include_router(router)
            for mi, (mpath, subapp) in enumerate(addon_mounts):
                mpath = (mpath or "/static").rstrip("/") or "/static"
                if not mpath.startswith("/"):
                    mpath = "/" + mpath
                mount_path = (prefix + mpath).replace("//", "/") if prefix else mpath
                if not mount_path.startswith("/"):
                    mount_path = "/" + mount_path
                app.mount(mount_path, subapp, name=f"addon_{name}_mount_{mi}")
            done.append((tech, str(name)))
            print(f"[addons] registered router {name} from {tech}")
        except Exception as e:
            print(f"[addons] ERROR registering {tech} ({bp_ref}): {e}")
    return done
