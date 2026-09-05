from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from starlette.requests import Request

from db import get_location_info_by_dbkey, get_role_permissions, get_user_role_id
from nexa_http.deps import inject_flask_route_names
from nexa_http.request_wrap import request as req_proxy
from nexa_http.session_wrap import session
from permissions import resolve_permission_targets


def _is_database_setup_route() -> bool:
    from nexa_http import has_request_context
    from nexa_http.request_wrap import request

    if not has_request_context():
        return False
    if (request.path or "").startswith("/database-setup"):
        return True
    ep = getattr(request, "endpoint", None) or ""
    return ep.startswith("database_setup.")


def apply_tenant_and_location_from_session(request: Request) -> None:
    """Session → ``g`` tenant + default location (Flask ``before_request`` parity)."""
    if _is_database_setup_route():
        return
    g = request.state.nexa_g
    if session.get("user"):
        tid = session.get("tenant_id")
        if isinstance(tid, str):
            stripped = tid.strip()
            g.current_tenant_id = stripped if stripped and stripped.lower() != "none" else None
        else:
            g.current_tenant_id = None
    else:
        g.current_tenant_id = None

    if not session.get("user"):
        return
    g.current_location_code = session.get("location_code")
    if session.get("location_code") is not None and (session.get("location_name") or "").strip():
        return
    try:
        loc_info = get_location_info_by_dbkey(None)
        if loc_info:
            loc_code = loc_info.get("locationcode")
            if loc_code is not None:
                session["location_code"] = int(loc_code) if isinstance(loc_code, (int, float)) else loc_code
            if loc_info.get("locationname"):
                session["location_name"] = (loc_info.get("locationname") or "").strip()
    except Exception as e:
        print(f"[DEBUG ensure_location_in_session] Error: {e}")
    g.current_location_code = session.get("location_code")
    try:
        from db import warm_core_schema_cache

        warm_core_schema_cache()
    except Exception:
        pass


def _normalize_location_code(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    s = (value if isinstance(value, str) else str(value)).strip()
    if not s:
        return None
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return s


def nexa_security_after_route_match(request: Request) -> None:
    """Location param match + menu RBAC (needs matched route / endpoint)."""
    inject_flask_route_names(request)
    if _is_database_setup_route():
        return
    path_n = request.url.path or ""
    if path_n.startswith("/static") or "/static/" in path_n:
        return
    if path_n.startswith("/api/v1") or path_n == "/health":
        return
    if not session.get("user"):
        return

    endpoint = request.state.flask_endpoint or ""
    if endpoint.startswith("static") or endpoint.startswith("auth."):
        return
    if endpoint in {
        "reports.qz_certificate",
        "reports.qz_certificate_download",
        "reports.qz_certificate_regenerate",
        "reports.qz_cert_info",
        "reports.qz_sign",
    }:
        return
    if request.state.flask_blueprint == "tenants":
        return

    session_loc = _normalize_location_code(session.get("location_code"))
    req_loc = None
    rq = req_proxy
    if rq.args.get("location_code") is not None:
        req_loc = _normalize_location_code(rq.args.get("location_code"))
    elif rq.args.get("locationcode") is not None:
        req_loc = _normalize_location_code(rq.args.get("locationcode"))
    if req_loc is None and rq.is_json:
        try:
            data = rq.get_json(silent=True) or {}
            if isinstance(data, dict):
                if data.get("location_code") is not None:
                    req_loc = _normalize_location_code(data.get("location_code"))
                elif data.get("locationcode") is not None:
                    req_loc = _normalize_location_code(data.get("locationcode"))
        except Exception:
            pass
    if req_loc is None and rq.form:
        if rq.form.get("location_code") is not None:
            req_loc = _normalize_location_code(rq.form.get("location_code"))
        elif rq.form.get("locationcode") is not None:
            req_loc = _normalize_location_code(rq.form.get("locationcode"))
    if req_loc is not None and session_loc is not None and req_loc != session_loc:
        api_like = path_n.startswith("/api") or "/api/" in path_n
        if api_like:
            raise HTTPException(
                status_code=403,
                detail={"success": False, "error": "Location code does not match your assigned location."},
            )
        raise HTTPException(status_code=403)

    if not endpoint or endpoint.startswith("static"):
        return
    if endpoint.startswith("auth.") or endpoint.startswith("api."):
        return
    if endpoint in {
        "reports.qz_certificate",
        "reports.qz_certificate_download",
        "reports.qz_certificate_regenerate",
        "reports.qz_cert_info",
        "reports.qz_sign",
    }:
        return
    # Default landing after login — must not require a menu row (roles can omit it in DB).
    if endpoint in ("dashboard.dashboard", "dashboard.index"):
        return
    # HO customer request (list, form, APIs, alerts): access is gated inside the HO views
    # (login, tenant scope, customer-creation flag). Menu rows are often missing here.
    if endpoint.startswith("ho.customer_request"):
        return
    # Transaction recording capture APIs — any logged-in user may record their own session.
    if endpoint in {
        "transaction_recording_audit.api_start",
        "transaction_recording_audit.api_field_change",
        "transaction_recording_audit.api_before_screenshot",
        "transaction_recording_audit.api_complete",
    }:
        return

    role_id: Optional[str] = None
    menu_permissions: list[str] = []
    user = session.get("user")
    if user:
        from nexa_http.layout_cache import peek_layout_cache
        cached = peek_layout_cache(str(user))
        if cached:
            role_id = cached.get("role_id")
            menu_permissions = list(cached.get("menu_permissions") or [])
    if role_id is None:
        role_id = get_user_role_id(user)
    if not menu_permissions and role_id:
        menu_permissions = get_role_permissions(role_id)
    if not role_id:
        return
    if not menu_permissions:
        raise HTTPException(
            status_code=403,
            detail={
                "reason": "no_permissions",
                "endpoint": endpoint,
                "role_id": role_id,
            },
        )
    allowed_endpoints, allowed_blueprints = resolve_permission_targets(menu_permissions)
    if endpoint in allowed_endpoints:
        return
    bp = request.state.flask_blueprint
    if bp in allowed_blueprints:
        return
    raise HTTPException(
        status_code=403,
        detail={
            "reason": "menu_denied",
            "endpoint": endpoint,
            "role_id": role_id,
        },
    )


async def http403_handler(request: Request, exc: HTTPException) -> Any:
    if exc.status_code != 403:
        raise exc
    path_n = request.url.path or ""
    detail = exc.detail if isinstance(exc.detail, dict) else {}
    if isinstance(exc.detail, dict) and (
        "success" in exc.detail or "ok" in exc.detail or path_n.startswith("/api") or "/api/" in path_n
    ):
        return JSONResponse(exc.detail, status_code=403)
    if path_n.startswith("/api") or "/api/" in path_n:
        return JSONResponse(
            {"success": False, "error": "You do not have permission for this action."},
            status_code=403,
        )
    if "/data-config/" in path_n and request.method in ("POST", "GET"):
        return JSONResponse(
            {"ok": False, "error": "You do not have permission for this action."},
            status_code=403,
        )
    from nexa_http.templates_m import render_template

    denied_endpoint = str(detail.get("endpoint") or "")
    role_id = detail.get("role_id")
    deny_reason = detail.get("reason")
    try:
        denied_endpoint = denied_endpoint or (request.state.flask_endpoint or "")
    except Exception:
        pass
    if role_id is None:
        try:
            from db import get_user_role_id

            role_id = get_user_role_id(session.get("user"))
        except Exception:
            pass

    return render_template(
        "unauthorized.html",
        denied_endpoint=denied_endpoint,
        role_id=role_id,
        deny_reason=deny_reason,
    )
