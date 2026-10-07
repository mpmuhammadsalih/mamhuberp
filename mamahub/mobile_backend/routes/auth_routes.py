import logging

from db.oracle_driver import cx_Oracle
from fastapi import APIRouter, Body, Depends, Query, Request
from pydantic import BaseModel

from mobile_backend.deps_auth import require_access_claims, require_refresh_claims
from mobile_backend.deps_save import require_save_nonce, success_after_mutation
from mobile_backend.jwt_compat import create_access_token, create_refresh_token, jwt_identity
from mobile_backend.mutation_errors import failure_from_mutation_exc
from mobile_backend.request_context import get_jwt
from mobile_backend.save_guard import clear_save_nonce, issue_save_nonce
from mobile_backend.services.auth_service import (
    authenticate_user,
    change_user_password,
    get_role_permissions,
    resolve_login_menu_context,
)
from mobile_backend.services.config_service import resolve_login_tenant
from mobile_backend.utils.response import failure, success

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
logger = logging.getLogger(__name__)


class LoginBody(BaseModel):
    username: str = ""
    password: str = ""
    tenant_id: str | None = None


class ChangePasswordBody(BaseModel):
    old_password: str = ""
    new_password: str = ""
    confirm_password: str = ""


@router.post("/login")
def login_route(body: LoginBody):
    username = (body.username or "").strip()
    password = body.password or ""
    if not username or not password:
        return failure("Username or employee code and password are required", status_code=400)

    try:
        user = authenticate_user(username, password)
    except (cx_Oracle.Error, RuntimeError):
        logger.exception("Login database error")
        return failure(
            "Authentication database unavailable. Check Oracle DSN, credentials, and login_users table.",
            status_code=503,
            error_code="AUTH_DB_ERROR",
        )

    if not user:
        return failure("Invalid credentials", status_code=401, error_code="INVALID_CREDENTIALS")

    try:
        effective_tenant = resolve_login_tenant(user, body.tenant_id)
    except ValueError as exc:
        return failure(str(exc), status_code=400, error_code="INVALID_TENANT")

    user = {**user, "tenant_id": effective_tenant}

    menu_ctx = resolve_login_menu_context(user)
    claims = {
        "role_id": user["role_id"],
        "tenant_id": effective_tenant,
        "permissions": menu_ctx["permissions"],
    }
    access_token = create_access_token(identity=str(user["username"]).strip(), additional_claims=claims)
    refresh_token = create_refresh_token(identity=str(user["username"]).strip(), additional_claims=claims)
    save_nonce = issue_save_nonce(str(user["username"]).strip(), effective_tenant)

    def _json_scalar(val):
        if val is None:
            return None
        return str(val).strip() or None

    return success(
        {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": {
                "username": str(user["username"] or "").strip(),
                "role_id": _json_scalar(user["role_id"]) or "",
                "employeecode": _json_scalar(user["employeecode"]) or "",
                "tenant_id": _json_scalar(user["tenant_id"]),
            },
            "permissions": menu_ctx["permissions"],
            "mobile_menus": menu_ctx["mobile_menus"],
            "allow_all_permissions": menu_ctx["allow_all_permissions"],
            "save_nonce": save_nonce,
        },
        message="Login successful",
    )


@router.get("/save-nonce", dependencies=[Depends(require_access_claims)])
def save_nonce_route():
    claims = get_jwt()
    username = jwt_identity(claims)
    tenant_id = str(claims.get("tenant_id") or "")
    return success({"save_nonce": issue_save_nonce(username, tenant_id)})


@router.post("/refresh", dependencies=[Depends(require_refresh_claims)])
def refresh_route():
    identity = jwt_identity(get_jwt())
    claims = get_jwt()
    tenant_id = str(claims.get("tenant_id") or "")
    access_token = create_access_token(
        identity=identity,
        additional_claims={
            "role_id": claims.get("role_id"),
            "tenant_id": tenant_id,
            "permissions": claims.get("permissions", []),
        },
    )
    save_nonce = issue_save_nonce(identity, tenant_id)
    return success({"access_token": access_token, "save_nonce": save_nonce})


@router.post("/logout", dependencies=[Depends(require_access_claims)])
def logout_route():
    claims = get_jwt()
    clear_save_nonce(jwt_identity(claims), str(claims.get("tenant_id") or ""))
    return success(message="Logout successful")


@router.post(
    "/change-password",
    dependencies=[Depends(require_access_claims), require_save_nonce],
)
def change_password_route(request: Request, body: ChangePasswordBody):
    old_password = body.old_password or ""
    new_password = body.new_password or ""
    confirm_password = body.confirm_password or ""
    if not old_password.strip():
        return failure("Old password is required", status_code=400)
    if not new_password.strip():
        return failure("New password is required", status_code=400)
    if new_password != confirm_password:
        return failure("New password and confirm password do not match", status_code=400)

    username = jwt_identity(get_jwt())
    try:
        change_user_password(username, old_password, new_password)
    except ValueError as exc:
        return failure(str(exc), status_code=400, error_code="INVALID_PASSWORD")
    except (cx_Oracle.Error, RuntimeError):
        logger.exception("Change password database error")
        return failure(
            "Authentication database unavailable. Try again later.",
            status_code=503,
            error_code="AUTH_DB_ERROR",
        )
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to change password.")
    return success_after_mutation(request, {}, message="Password changed successfully")
