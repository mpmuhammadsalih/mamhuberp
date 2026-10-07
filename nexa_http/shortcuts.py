from __future__ import annotations

import sys
from typing import Any, Callable, Sequence, TypeVar
from urllib.parse import urlencode

from fastapi import HTTPException
from fastapi.responses import RedirectResponse
from starlette.datastructures import URLPath
from starlette.requests import Request
from starlette.routing import Mount, NoMatchFound, WebSocketRoute

from nexa_http import context as ctx
from nexa_http import static_registry

F = TypeVar("F", bound=Callable[..., Any])

# Flask-style endpoints → paths (no path params). Used before ``url_path_for`` and as a safe fallback.
_KNOWN_STATIC_PATHS: dict[str, str] = {
    "dashboard.dashboard": "/dashboard",
    "dashboard.index": "/",
    "auth.login": "/auth/login",
    "auth.logout": "/auth/logout",
    "auth.change_password": "/auth/change-password",
    "ho.itemmaster_central": "/ho/itemmaster-central",
    "accounts.receipt_voucher": "/accounts/receipt-voucher",
    "accounts.receipt_voucher_list": "/accounts/receipt-voucher/list",
    "accounts.receipt_voucher_pdf": "/accounts/receipt-voucher/pdf",
    "accounts.payment_voucher": "/accounts/payment-voucher",
    "accounts.payment_voucher_list": "/accounts/payment-voucher/list",
    "accounts.payment_voucher_pdf": "/accounts/payment-voucher/pdf",
    "accounts.contra_voucher": "/accounts/contra-voucher",
    "accounts.contra_voucher_list": "/accounts/contra-voucher/list",
    "accounts.contra_voucher_pdf": "/accounts/contra-voucher/pdf",
    "itemmaster.itemmaster_data_config_store_stock_import_map": "/itemmaster/data-config/store-stock-import-map",
    "itemmaster.itemmaster_data_config_store_stock_import": "/itemmaster/data-config/store-stock-import",
    "purchase.inventory_value_adjustment": "/purchase/inventory-value-adjustment",
    "purchase.inventory_value_adjustment_list": "/purchase/inventory-value-adjustment/list",
    "purchase.inventory_value_adjustment_form": "/purchase/inventory-value-adjustment/new",
    "purchase.stock_transfer_approval_setup": "/purchase/stock-transfer/approval-setup",
    "purchase.stock_transfer_approval_setup_init": "/purchase/stock-transfer/approval-setup/api/init",
    "purchase.stock_transfer_approval_setup_load": "/purchase/stock-transfer/approval-setup/api/load",
    "purchase.stock_transfer_approval_setup_save": "/purchase/stock-transfer/approval-setup/api/save",
    "ecommerce.products": "/ecommerce/products",
    "ecommerce.products_web_catalog": "/ecommerce/products/web-catalog",
    "ecommerce.products_image_import_template": "/ecommerce/products/images/template.xlsx",
    "ecommerce.products_image_import": "/ecommerce/products/images/import",
    "ecommerce.products_image_import_progress": "/ecommerce/products/images/import/progress",
    "ecommerce.products_image_fetch_web": "/ecommerce/products/images/fetch-web",
    "ecommerce.compare_stores": "/ecommerce/compare-stores",
    "ecommerce.compare_store_new": "/ecommerce/compare-stores/new",
}


def _append_query(path: str, query: dict[str, Any]) -> str:
    """Append ``?a=1&b=2`` for extra ``url_for`` kwargs (Flask-compatible)."""
    if not query:
        return path
    pairs: list[tuple[str, Any]] = []
    for key, val in query.items():
        if val is None:
            continue
        if isinstance(val, (list, tuple)):
            for v in val:
                pairs.append((key, v))
        else:
            pairs.append((key, val))
    if not pairs:
        return path
    qs = urlencode(pairs, doseq=True)
    joiner = "&" if "?" in path else "?"
    return f"{path}{joiner}{qs}"


def _routes_sequence(root: object) -> Sequence[Any]:
    """Prefer FastAPI ``app.routes`` (flattened); fall back to ``app.router.routes``."""
    r = getattr(root, "routes", None)
    if r is not None:
        return r
    router = getattr(root, "router", None)
    if router is None:
        return ()
    return getattr(router, "routes", None) or ()


def _is_named_http_route(route: Any) -> bool:
    """Skip WebSocket routes so ``url_for`` resolves HTTP ``APIRoute`` / ``Route``."""
    if isinstance(route, WebSocketRoute):
        return False
    if not getattr(route, "name", None):
        return False
    return hasattr(route, "param_convertors")


def _nested_routes(route: Any) -> Sequence[Any] | None:
    """Child routes to recurse into: ``Mount`` children and FastAPI ``_IncludedRouter`` wrappers.

    Newer FastAPI wraps ``include_router`` results in an ``_IncludedRouter`` (routes live on
    ``original_router.routes``) instead of copying them into ``app.routes``. Without recursing
    here, ``url_for`` cannot see included-addon routes and misclassifies query kwargs as path
    params, raising ``NoMatchFound``.
    """
    if isinstance(route, Mount):
        return getattr(route, "routes", None)
    original = getattr(route, "original_router", None)
    if original is not None:
        return getattr(original, "routes", None)
    return None


def _find_route_by_name(routes: Sequence[Any], name: str) -> Any | None:
    for route in routes or ():
        if _is_named_http_route(route) and route.name == name:
            return route
        inner = _nested_routes(route)
        if inner:
            found = _find_route_by_name(inner, name)
            if found is not None:
                return found
    return None


def _path_param_names_for_route(root: object, route_name: str) -> set[str] | None:
    hit = _find_route_by_name(_routes_sequence(root), route_name)
    if hit is None:
        return None
    return set(getattr(hit, "param_convertors", None) or {})


def _split_path_and_query_kwargs(root: object, route_name: str, values: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Path kwargs for Starlette ``url_path_for`` vs query-string kwargs (Flask behavior)."""
    expected = _path_param_names_for_route(root, route_name)
    if expected is not None:
        path_kw = {k: values[k] for k in expected if k in values}
        query_kw = {k: v for k, v in values.items() if k not in expected}
        return path_kw, query_kw
    # Route metadata missing (unusual): if this endpoint has no path params, treat all kwargs as query.
    try:
        root.url_path_for(route_name)
        return {}, dict(values)
    except NoMatchFound:
        return dict(values), {}


def _finalize_url_path(
    request: Request,
    rel_path: str,
    *,
    external: bool,
    scheme: str | None,
    anchor: str | None,
) -> str:
    """Apply Flask-style ``_external``, ``_scheme``, ``_anchor`` using the current request host (LAN-safe)."""
    want_absolute = bool(external or scheme)
    base = request.base_url
    if scheme:
        base = base.replace(scheme=str(scheme))
    if want_absolute:
        body = str(URLPath(rel_path).make_absolute_url(base_url=base))
    else:
        body = rel_path
    if anchor:
        body = f"{body}#{anchor}"
    return body


def redirect(location: str, code: int = 302) -> RedirectResponse:
    return RedirectResponse(location, status_code=code)


def abort(code: int, *args: Any, **kwargs: Any) -> None:
    detail = None
    if args and isinstance(args[0], str):
        detail = args[0]
    raise HTTPException(status_code=code, detail=detail)


def url_for(endpoint: str, **values: Any) -> str:
    request = ctx.get_current_request()
    if request is None:
        raise RuntimeError("url_for called outside request context.")
    external = bool(values.pop("_external", False))
    scheme = values.pop("_scheme", None)
    anchor = values.pop("_anchor", None)
    values.pop("_method", None)

    if endpoint == "static":
        fn_raw = values.pop("filename", None) or values.pop("path", None) or ""
        fn = str(fn_raw).replace("\\", "/").lstrip("/")
        path = f"/static/{fn}" if fn else "/static/"
        path = _append_query(path, values)
        return _finalize_url_path(request, path, external=external, scheme=scheme, anchor=anchor)
    if endpoint != "static":
        _bp, _dot, _tail = endpoint.rpartition(".")
        if _tail == "static" and _bp:
            static_base = static_registry.blueprint_static_base(_bp)
            if static_base is not None:
                fn_raw = values.pop("filename", None) or values.pop("path", None) or ""
                fn = str(fn_raw).replace("\\", "/").lstrip("/")
                path = f"{static_base.rstrip('/')}/{fn}" if fn else static_base.rstrip("/") + "/"
                path = _append_query(path, values)
                return _finalize_url_path(request, path, external=external, scheme=scheme, anchor=anchor)
    hard = _KNOWN_STATIC_PATHS.get(endpoint)
    if hard is not None:
        path = _append_query(hard, dict(values))
        return _finalize_url_path(request, path, external=external, scheme=scheme, anchor=anchor)
    name = endpoint.replace(".", "__")

    def _is_request_like(obj: object) -> bool:
        """Treat any Starlette ``HTTPConnection`` (Request, ``_CachedRequest``, WebSocket) as non-app."""
        if obj is request:
            return True
        for c in type(obj).__mro__:
            mod = getattr(c, "__module__", "") or ""
            if c.__name__ == "HTTPConnection" and "starlette.requests" in mod:
                return True
        cls_name = type(obj).__name__
        return cls_name in ("Request", "_CachedRequest", "WebSocket")

    def _class_url_path_for(obj: object) -> Any:
        return getattr(type(obj), "url_path_for", None)

    def _url_provider(obj: object | None) -> object | None:
        if obj is None or _is_request_like(obj):
            return None
        upf = _class_url_path_for(obj)
        if upf is None or not callable(upf):
            return None
        return obj

    # Try several ASGI roots: ``scope["app"]`` / ``get_current_app()`` may be a wrapper without
    # addon routes, which makes ``_split_path_and_query_kwargs`` fall through to ``url_path_for``
    # with all kwargs as path params (Flask would put them in the query string). The root
    # installed in ``install_root_application`` always has the full route table.
    candidates: list[object] = []
    seen_ids: set[int] = set()

    def _push_root(obj: object | None) -> None:
        prov = _url_provider(obj)
        if prov is None or _is_request_like(prov):
            return
        i = id(prov)
        if i in seen_ids:
            return
        seen_ids.add(i)
        candidates.append(prov)

    try:
        _push_root(ctx.get_root_application())
    except RuntimeError:
        pass
    amod = sys.modules.get("app")
    if amod is not None:
        _push_root(getattr(amod, "app", None))
    try:
        _push_root(ctx.get_current_app())
    except RuntimeError:
        pass
    _push_root(request.scope.get("router"))
    _push_root(request.scope.get("app"))
    if not candidates:
        raise RuntimeError("Cannot resolve ASGI application for url_for.")
    last_nm: NoMatchFound | None = None
    for root in candidates:
        path_kw, query_kw = _split_path_and_query_kwargs(root, name, values)
        try:
            rel = str(root.url_path_for(name, **path_kw))
        except NoMatchFound as e:
            last_nm = e
            continue
        rel = _append_query(rel, query_kw)
        return _finalize_url_path(request, rel, external=external, scheme=scheme, anchor=anchor)
    if last_nm is not None:
        raise last_nm
    raise RuntimeError(f"Cannot build URL for route {name!r}.")


def stream_with_context(generator: F) -> F:
    """Flask compatibility; Starlette keeps generator scope without extra wrapping."""
    return generator
