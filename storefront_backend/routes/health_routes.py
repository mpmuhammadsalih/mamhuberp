"""Health endpoints."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from db import _safe_rows
from storefront_backend.utils.response import success_response

router = APIRouter(tags=['Health'])


@router.get('/health')
async def health_check():
    db_status = 'up'
    try:
        _safe_rows('SELECT 1 AS ok FROM DUAL', {})
    except Exception as exc:  # noqa: BLE001
        db_status = f'down: {exc}'
    overall = 'healthy' if db_status == 'up' else 'degraded'
    payload = success_response(
        data={
            'status': overall,
            'app_name': 'MamaHub Storefront API (Nova)',
            'environment': 'production',
            'api': {'status': 'up', 'timestamp': datetime.now(timezone.utc).isoformat()},
            'database': {'status': db_status},
        },
        message='Service is healthy' if overall == 'healthy' else 'Service is degraded',
    )
    code = status.HTTP_200_OK if overall == 'healthy' else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(status_code=code, content=payload)


@router.get('/health/live')
async def liveness():
    return success_response(data={'status': 'alive'}, message='Application is alive')


@router.get('/health/ready')
async def readiness():
    ready = True
    try:
        _safe_rows('SELECT 1 AS ok FROM DUAL', {})
    except Exception:  # noqa: BLE001
        ready = False
    payload = success_response(
        data={'status': 'ready' if ready else 'not_ready'},
        message='Application is ready' if ready else 'Application is not ready',
    )
    code = status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(status_code=code, content=payload)
