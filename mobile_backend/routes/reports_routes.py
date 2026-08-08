import logging

from db.oracle_driver import cx_Oracle
from fastapi import APIRouter, Depends, Query

from mobile_backend.deps_auth import require_access_claims, require_any_permission
from mobile_backend.services import business_summary_service
from mobile_backend.utils.response import failure, success

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/reports",
    tags=["reports"],
    dependencies=[Depends(require_access_claims)],
)

_BUSINESS_SUMMARY_PERMS = (
    "business_summary.dashboard",
    "business_summary.api_dashboard",
)


@router.get(
    "/business-summary",
    dependencies=[Depends(require_any_permission(*_BUSINESS_SUMMARY_PERMS))],
)
def business_summary_route(
    date_from: str = Query(""),
    date_to: str = Query(""),
    branch: str = Query(""),
):
    try:
        data = business_summary_service.get_business_summary(
            date_from=date_from,
            date_to=date_to,
            branch=branch,
        )
        return success(data)
    except (cx_Oracle.Error, RuntimeError) as exc:
        logger.exception("Business summary error")
        return failure(str(exc)[:500], status_code=503, error_code="BUSINESS_SUMMARY_ERROR")
    except Exception as exc:
        logger.exception("Business summary error")
        return failure(str(exc)[:500], status_code=500, error_code="BUSINESS_SUMMARY_ERROR")
