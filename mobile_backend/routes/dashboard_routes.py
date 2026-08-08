from fastapi import APIRouter, Depends, Query

from mobile_backend.deps_auth import require_access_claims, require_permission
from mobile_backend.services.dashboard_service import get_dashboard_summary, get_kpi_detail
from mobile_backend.utils.response import failure, success

router = APIRouter(
    prefix="/api/v1/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(require_access_claims)],
)

_dash_perm = Depends(require_permission("dashboard.dashboard"))


@router.get("/summary", dependencies=[_dash_perm])
def dashboard_summary():
    return success(get_dashboard_summary())


@router.get("/kpi/{kpi_id}", dependencies=[_dash_perm])
def dashboard_kpi_detail(
    kpi_id: str,
    limit: int = Query(40, ge=1, le=100),
):
    try:
        data = get_kpi_detail(kpi_id, limit=limit)
    except ValueError as exc:
        return failure(str(exc), status_code=400)
    except Exception as exc:
        return failure(str(exc) or "Failed to load KPI detail.", status_code=400)
    return success(data)
