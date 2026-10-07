from typing import Any

from fastapi import APIRouter, Body, Depends, Query, Request

from mobile_backend.deps_auth import require_access_claims, require_any_permission
from mobile_backend.deps_save import require_save_nonce, success_after_mutation
from mobile_backend.mutation_errors import failure_from_mutation_exc
from mobile_backend.request_context import get_jwt
from mobile_backend.services import supplier_master_service as sup
from mobile_backend.utils.response import failure, success

router = APIRouter(
    prefix="/api/v1/supplier",
    tags=["supplier"],
    dependencies=[Depends(require_access_claims)],
)

_master_perm = Depends(
    require_any_permission(
        "supplier.supplier_list",
        "supplier.supplier_create",
        "mobile.suppliers",
        "mobile.supplier",
    )
)


@router.get("/masters/open", dependencies=[_master_perm])
def supplier_masters_open():
    try:
        data = sup.get_open_context()
    except Exception as exc:
        return failure(str(exc) or "Failed to open supplier form.", status_code=400)
    return success(data)


@router.get("/masters", dependencies=[_master_perm])
def supplier_masters_list(
    q: str = Query(""),
    limit: int = Query(100, ge=1, le=300),
):
    try:
        data = sup.list_suppliers(search=q, limit=limit)
    except Exception as exc:
        return failure(str(exc) or "Failed to list suppliers.", status_code=400)
    return success(data)


@router.post("/masters", dependencies=[_master_perm, require_save_nonce])
def supplier_masters_create(request: Request, payload: dict[str, Any] = Body(default_factory=dict)):
    claims = get_jwt()
    username = str(claims.get("sub") or "mobile").strip() or "mobile"
    try:
        data = sup.create_supplier(payload, username=username)
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to save supplier.")
    return success_after_mutation(
        request,
        data,
        message=data.get("message") or "Supplier saved",
        status_code=201,
    )


@router.get("/masters/{supplier_code}", dependencies=[_master_perm])
def supplier_masters_get(supplier_code: int):
    try:
        data = sup.get_supplier(supplier_code)
    except Exception as exc:
        return failure(str(exc) or "Failed to load supplier.", status_code=400)
    return success(data)


@router.put("/masters/{supplier_code}", dependencies=[_master_perm, require_save_nonce])
def supplier_masters_update(
    request: Request,
    supplier_code: int,
    payload: dict[str, Any] = Body(default_factory=dict),
):
    claims = get_jwt()
    username = str(claims.get("sub") or "mobile").strip() or "mobile"
    try:
        data = sup.update_supplier(supplier_code, payload, username=username)
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to update supplier.")
    return success_after_mutation(
        request,
        data,
        message=data.get("message") or "Supplier updated",
    )


@router.post("/masters/{supplier_code}/delete", dependencies=[_master_perm, require_save_nonce])
def supplier_masters_delete(
    request: Request,
    supplier_code: int,
    payload: dict[str, Any] = Body(default_factory=dict),
):
    claims = get_jwt()
    username = str(claims.get("sub") or "mobile").strip() or "mobile"
    try:
        data = sup.delete_supplier(
            supplier_code,
            password=str((payload or {}).get("password") or ""),
            username=username,
        )
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to delete supplier.")
    return success_after_mutation(
        request,
        data,
        message=data.get("message") or "Supplier deleted",
    )
