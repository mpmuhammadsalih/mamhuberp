from typing import Any

from fastapi import APIRouter, Body, Depends, Query, Request

from mobile_backend.deps_auth import require_access_claims, require_any_permission
from mobile_backend.deps_save import require_save_nonce, success_after_mutation
from mobile_backend.mutation_errors import failure_from_mutation_exc
from mobile_backend.request_context import get_jwt
from mobile_backend.services import customer_master_service as cust
from mobile_backend.utils.response import failure, success

router = APIRouter(
    prefix="/api/v1/customer",
    tags=["customer"],
    dependencies=[Depends(require_access_claims)],
)

_master_perm = Depends(
    require_any_permission(
        "customer.customer_list",
        "customer.customer_create",
        "mobile.customers",
        "mobile.customer",
    )
)


@router.get("/ledger", dependencies=[Depends(require_any_permission("accounts.customer_ledger_page", "mobile.customer_ledger"))])
def customer_ledger():
    return success({"message": "Customer ledger endpoints scaffold ready"})


@router.get("/masters/open", dependencies=[_master_perm])
def customer_masters_open():
    try:
        data = cust.get_open_context()
    except Exception as exc:
        return failure(str(exc) or "Failed to open customer form.", status_code=400)
    return success(data)


@router.get("/masters", dependencies=[_master_perm])
def customer_masters_list(
    q: str = Query(""),
    limit: int = Query(100, ge=1, le=300),
):
    try:
        data = cust.list_customers(search=q, limit=limit)
    except Exception as exc:
        return failure(str(exc) or "Failed to list customers.", status_code=400)
    return success(data)


@router.post("/masters", dependencies=[_master_perm, require_save_nonce])
def customer_masters_create(request: Request, payload: dict[str, Any] = Body(default_factory=dict)):
    claims = get_jwt()
    username = str(claims.get("sub") or "mobile").strip() or "mobile"
    try:
        data = cust.create_customer(payload, username=username)
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to save customer.")
    return success_after_mutation(
        request,
        data,
        message=data.get("message") or "Customer saved",
        status_code=201,
    )


@router.post("/categories", dependencies=[_master_perm, require_save_nonce])
def customer_category_create(request: Request, payload: dict[str, Any] = Body(default_factory=dict)):
    """Create ERP customer category (TBLCUSTOMERCATEGORY) for use on New Customer."""
    claims = get_jwt()
    username = str(claims.get("sub") or "mobile").strip() or "mobile"
    try:
        data = cust.create_customer_category(payload, username=username)
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to save customer category.")
    return success_after_mutation(
        request,
        data,
        message=data.get("message") or "Customer category created",
        status_code=201,
    )
