from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel

from mobile_backend.deps_auth import require_access_claims
from mobile_backend.jwt_compat import create_access_token, create_refresh_token, jwt_identity
from mobile_backend.request_context import get_jwt
from mobile_backend.services.auth_service import get_role_permissions
from mobile_backend.save_guard import issue_save_nonce
from mobile_backend.services.tenant_service import get_user_tenant_scope
from mobile_backend.utils.response import failure, success

router = APIRouter(
    prefix="/api/v1/tenant",
    tags=["tenant"],
    dependencies=[Depends(require_access_claims)],
)


class SwitchTenantBody(BaseModel):
    tenant_id: str = ""


@router.get("/list")
def list_tenants():
    username = jwt_identity(get_jwt())
    scope = get_user_tenant_scope(username)
    return success(
        {
            "can_switch": scope["can_switch"],
            "current_tenant_id": scope["current_tenant_id"],
            "tenants": scope["tenants"],
        }
    )


@router.post("/switch")
def switch_tenant(body: SwitchTenantBody):
    username = jwt_identity(get_jwt())
    new_tenant_id = (body.tenant_id or "").strip()
    if not new_tenant_id:
        return failure("tenant_id is required", status_code=400)

    scope = get_user_tenant_scope(username)
    if not scope["can_switch"]:
        return failure("Tenant switching is not allowed for this user", status_code=403, error_code="FORBIDDEN")

    allowed_ids = {str(t["tenant_id"]).strip().lower() for t in scope["tenants"]}
    if new_tenant_id.lower() not in allowed_ids:
        return failure("Requested tenant is not allowed", status_code=403, error_code="FORBIDDEN")

    permissions = get_role_permissions(scope["role_id"])
    claims = {
        "role_id": scope["role_id"],
        "tenant_id": new_tenant_id,
        "permissions": permissions,
    }
    access_token = create_access_token(identity=scope["username"], additional_claims=claims)
    refresh_token = create_refresh_token(identity=scope["username"], additional_claims=claims)
    save_nonce = issue_save_nonce(scope["username"], new_tenant_id)
    return success(
        {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "tenant_id": new_tenant_id,
            "save_nonce": save_nonce,
        },
        message="Tenant switched successfully",
    )
