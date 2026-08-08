import logging

from db.oracle_driver import cx_Oracle
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from mobile_backend.deps_config import require_config_setup_key
from mobile_backend.services import config_service as cfg
from mobile_backend.utils.response import failure, success

router = APIRouter(prefix="/api/v1/config", tags=["config"])
logger = logging.getLogger(__name__)


class TenantConnectionBody(BaseModel):
    host: str = Field(..., min_length=1)
    port: int = Field(1521, ge=1, le=65535)
    service_name: str = Field(..., min_length=1)
    username: str = Field(..., min_length=1)
    password: str = ""


class TenantUpsertBody(TenantConnectionBody):
    tenant_id: str = Field(..., min_length=1, max_length=64)
    display_name: str | None = Field(None, max_length=200)
    active: bool = True


@router.get("/app")
def get_app_config():
    """Public bootstrap: auth catalog connectivity + active tenants (no secrets)."""
    try:
        data = cfg.get_app_config()
        return success(data, message="App configuration")
    except (cx_Oracle.Error, RuntimeError):
        logger.exception("Config load failed")
        return failure(
            "Configuration database unavailable. Check API .env Oracle settings.",
            status_code=503,
            error_code="CONFIG_DB_ERROR",
        )


@router.post("/test-connection")
def test_tenant_connection(body: TenantConnectionBody):
    """Test ERP Oracle credentials (does not save)."""
    try:
        data = cfg.test_oracle_connection(
            host=body.host,
            port=body.port,
            service_name=body.service_name,
            username=body.username,
            password=body.password,
        )
        return success(data, message="Connection successful")
    except ValueError as exc:
        return failure(str(exc), status_code=400, error_code="INVALID_INPUT")
    except cx_Oracle.Error as exc:
        logger.warning("Tenant connection test failed: %s", exc)
        return failure(
            f"Connection failed: {exc}",
            status_code=400,
            error_code="DB_CONNECTION_FAILED",
        )


@router.post("/tenant", dependencies=[Depends(require_config_setup_key)])
def upsert_tenant(body: TenantUpsertBody):
    """Create or update a row in TENANT_DATABASES (auth catalog)."""
    try:
        data = cfg.upsert_tenant_database(
            tenant_id=body.tenant_id,
            display_name=body.display_name,
            host=body.host,
            port=body.port,
            service_name=body.service_name,
            username=body.username,
            password=body.password or None,
            active=body.active,
        )
        return success(data, message="Tenant database saved")
    except ValueError as exc:
        return failure(str(exc), status_code=400, error_code="INVALID_INPUT")
    except cx_Oracle.Error as exc:
        logger.exception("Tenant upsert failed")
        return failure(
            f"Could not save tenant: {exc}",
            status_code=503,
            error_code="CONFIG_DB_ERROR",
        )
