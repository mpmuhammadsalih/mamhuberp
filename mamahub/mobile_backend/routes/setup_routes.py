from typing import Any

from fastapi import APIRouter, Body, Depends, Query, Request

from mobile_backend.deps_auth import require_access_claims, require_any_permission
from mobile_backend.deps_save import require_save_nonce, success_after_mutation
from mobile_backend.mutation_errors import failure_from_mutation_exc
from mobile_backend.services import transaction_date_setup_service as tds
from mobile_backend.utils.response import failure, success

router = APIRouter(
    prefix="/api/v1/setup",
    tags=["setup"],
    dependencies=[Depends(require_access_claims)],
)

_txn_date_perm = Depends(
    require_any_permission(
        "setup.transaction_date_setup",
        "mobile.transaction_date_setup",
    )
)


@router.get("/transaction-date", dependencies=[_txn_date_perm])
def transaction_date_bootstrap(
    location_code: int = Query(0, ge=0, description="Branch location code; 0 = session default"),
):
    try:
        data = tds.get_bootstrap(location_code if location_code > 0 else None)
        return success(data)
    except Exception as exc:
        return failure(str(exc) or "Failed to load transaction date setup.", status_code=400)


@router.post("/transaction-date", dependencies=[_txn_date_perm, require_save_nonce])
def transaction_date_save(request: Request, payload: dict[str, Any] = Body(default_factory=dict)):
    try:
        data = tds.save_setup(payload)
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to save transaction date setup.")
    return success_after_mutation(
        request,
        data,
        message=data.get("message") or "Transaction dates saved",
    )


@router.post("/transaction-date/close", dependencies=[_txn_date_perm, require_save_nonce])
def transaction_date_close(request: Request, payload: dict[str, Any] = Body(default_factory=dict)):
    try:
        data = tds.close_setup(payload)
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to close transaction dates.")
    return success_after_mutation(
        request,
        data,
        message=data.get("message") or "Transaction dates closed",
    )
