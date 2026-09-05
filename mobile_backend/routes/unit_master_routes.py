"""Unit of Measurement master mobile APIs (ERP UNITOFMEASUREMENT)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, Query, Request

from mobile_backend.deps_auth import require_access_claims, require_any_permission
from mobile_backend.deps_save import require_save_nonce, success_after_mutation
from mobile_backend.mutation_errors import failure_from_mutation_exc
from mobile_backend.request_context import get_jwt
from mobile_backend.services import unit_master_service as ums
from mobile_backend.utils.response import failure, success

router = APIRouter(
    prefix="/api/v1",
    tags=["unit-master"],
    dependencies=[Depends(require_access_claims)],
)

_uom_perm = Depends(
    require_any_permission(
        "itemmaster.unit_of_measurement_list",
        "itemmaster.unit_of_measurement_save",
        "mobile.unit_master",
        "mobile.items",
    )
)


@router.get("/unit-master", dependencies=[_uom_perm])
def unit_master_list(q: str = Query("")):
    try:
        return success(ums.list_units(search=q))
    except Exception as exc:
        return failure(str(exc) or "Failed to list units.", status_code=400)


@router.post("/unit-master", dependencies=[_uom_perm, require_save_nonce])
def unit_master_create(request: Request, payload: dict[str, Any] = Body(default_factory=dict)):
    claims = get_jwt()
    username = str(claims.get("sub") or "mobile").strip() or "mobile"
    try:
        data = ums.create_unit(
            code=str(payload.get("code") or payload.get("unitcode") or ""),
            name=str(payload.get("name") or payload.get("unitname") or ""),
            username=username,
        )
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to save unit.")
    return success_after_mutation(
        request,
        data,
        message=data.get("message") or "Unit saved",
        status_code=201,
    )


@router.put("/unit-master/{code}", dependencies=[_uom_perm, require_save_nonce])
def unit_master_update(
    request: Request,
    code: str,
    payload: dict[str, Any] = Body(default_factory=dict),
):
    claims = get_jwt()
    username = str(claims.get("sub") or "mobile").strip() or "mobile"
    try:
        data = ums.update_unit(
            code=code,
            name=str(payload.get("name") or payload.get("unitname") or ""),
            username=username,
        )
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to update unit.")
    return success_after_mutation(
        request,
        data,
        message=data.get("message") or "Unit updated",
    )


@router.post("/unit-master/{code}/delete", dependencies=[_uom_perm, require_save_nonce])
def unit_master_delete(request: Request, code: str):
    claims = get_jwt()
    username = str(claims.get("sub") or "mobile").strip() or "mobile"
    try:
        data = ums.delete_unit(code=code, username=username)
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to delete unit.")
    return success_after_mutation(
        request,
        data,
        message=data.get("message") or "Unit deleted",
    )
