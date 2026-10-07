"""Category Master + Brand Master mobile APIs (ERP CATEGORY)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, Query, Request

from mobile_backend.deps_auth import require_access_claims, require_any_permission
from mobile_backend.deps_save import require_save_nonce, success_after_mutation
from mobile_backend.mutation_errors import failure_from_mutation_exc
from mobile_backend.request_context import get_jwt
from mobile_backend.services import category_brand_master_service as cbs
from mobile_backend.utils.response import failure, success

router = APIRouter(
    prefix="/api/v1",
    tags=["category-brand-master"],
    dependencies=[Depends(require_access_claims)],
)

_cat_perm = Depends(
    require_any_permission(
        "itemmaster.category_master_list",
        "itemmaster.category_master_save",
        "mobile.category_master",
        "mobile.items",
    )
)

_brand_perm = Depends(
    require_any_permission(
        "itemmaster.brand_master_list",
        "itemmaster.brand_master_save",
        "mobile.brand_master",
        "mobile.items",
    )
)


@router.get("/category-master", dependencies=[_cat_perm])
def category_master_list(q: str = Query("")):
    try:
        return success(cbs.list_category_master(search=q))
    except Exception as exc:
        return failure(str(exc) or "Failed to list categories.", status_code=400)


@router.post("/category-master", dependencies=[_cat_perm, require_save_nonce])
def category_master_create(request: Request, payload: dict[str, Any] = Body(default_factory=dict)):
    claims = get_jwt()
    username = str(claims.get("sub") or "mobile").strip() or "mobile"
    try:
        data = cbs.create_category(
            flag=str(payload.get("flag") or ""),
            name=str(payload.get("name") or ""),
            main_code=payload.get("main_code"),
            d_code=payload.get("d_code") or payload.get("category_code"),
            username=username,
        )
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to save category.")
    return success_after_mutation(
        request,
        data,
        message=data.get("message") or "Category saved",
        status_code=201,
    )


@router.put("/category-master/{code}", dependencies=[_cat_perm, require_save_nonce])
def category_master_update(
    request: Request,
    code: int,
    payload: dict[str, Any] = Body(default_factory=dict),
):
    claims = get_jwt()
    username = str(claims.get("sub") or "mobile").strip() or "mobile"
    try:
        data = cbs.update_category(
            code=code,
            flag=str(payload.get("flag") or ""),
            name=str(payload.get("name") or ""),
            username=username,
        )
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to update category.")
    return success_after_mutation(
        request,
        data,
        message=data.get("message") or "Category updated",
    )


@router.get("/brand-master", dependencies=[_brand_perm])
def brand_master_list(
    flag: str = Query("all"),
    q: str = Query(""),
):
    try:
        return success(cbs.list_brand_master(flag=flag, search=q))
    except Exception as exc:
        return failure(str(exc) or "Failed to list brands.", status_code=400)


@router.post("/brand-master", dependencies=[_brand_perm, require_save_nonce])
def brand_master_create(request: Request, payload: dict[str, Any] = Body(default_factory=dict)):
    claims = get_jwt()
    username = str(claims.get("sub") or "mobile").strip() or "mobile"
    try:
        data = cbs.create_brand(
            flag=str(payload.get("flag") or "B"),
            name=str(payload.get("name") or ""),
            username=username,
        )
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to save brand.")
    return success_after_mutation(
        request,
        data,
        message=data.get("message") or "Saved",
        status_code=201,
    )


@router.put("/brand-master/{code}", dependencies=[_brand_perm, require_save_nonce])
def brand_master_update(
    request: Request,
    code: int,
    payload: dict[str, Any] = Body(default_factory=dict),
):
    claims = get_jwt()
    username = str(claims.get("sub") or "mobile").strip() or "mobile"
    try:
        data = cbs.update_brand(
            code=code,
            flag=str(payload.get("flag") or "B"),
            name=str(payload.get("name") or ""),
            username=username,
        )
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to update brand.")
    return success_after_mutation(
        request,
        data,
        message=data.get("message") or "Updated",
    )
