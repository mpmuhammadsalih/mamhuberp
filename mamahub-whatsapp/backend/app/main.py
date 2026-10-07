"""MamaHub WhatsApp CRM API."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api.auth import router as auth_router
from app.api.auth import users_router
from app.api.conversations import router as conversations_router
from app.api.crm import (
    ai_router,
    customers_router,
    dashboard_router,
    orders_router,
    products_router,
    replies_router,
    reports_router,
    settings_router,
    templates_router,
)
from app.api.push import router as push_router
from app.api.whatsapp import router as whatsapp_router
from app.api.ws import router as ws_router
from app.core.config import get_settings
from app.core.logging import logger, setup_logging
from app.database.bootstrap import bootstrap_schema


@asynccontextmanager
async def lifespan(_app: FastAPI):
    setup_logging()
    settings = get_settings()
    logger.info("Starting %s", settings.app_name)
    if settings.db_username and settings.db_dsn:
        bootstrap_schema()
    else:
        logger.warning("Oracle credentials missing — schema bootstrap skipped")
    yield


settings = get_settings()
limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])

app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list or ["*"],
    allow_origin_regex=r"https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(conversations_router)
app.include_router(customers_router)
app.include_router(products_router)
app.include_router(orders_router)
app.include_router(replies_router)
app.include_router(templates_router)
app.include_router(ai_router)
app.include_router(dashboard_router)
app.include_router(reports_router)
app.include_router(settings_router)
app.include_router(push_router)
app.include_router(whatsapp_router)
app.include_router(ws_router)

app.mount("/api/media", StaticFiles(directory=str(settings.upload_path)), name="media")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name}


@app.get("/api/media-file/{name}")
def media_file(name: str) -> FileResponse:
    path = settings.upload_path / Path(name).name
    return FileResponse(path)
