"""Oracle engine and session factory."""
from __future__ import annotations

from collections.abc import Generator

import oracledb
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from fastapi import HTTPException, status

from app.core.config import get_settings
from app.core.logging import logger

_engine = None
_SessionLocal = None


def _creator():
    settings = get_settings()
    kwargs = {
        "user": settings.db_username,
        "password": settings.db_password,
        "dsn": settings.db_dsn,
    }
    if settings.oracle_tcp_connect_timeout:
        kwargs["tcp_connect_timeout"] = settings.oracle_tcp_connect_timeout
    return oracledb.connect(**kwargs)


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        if not settings.db_username or not settings.db_dsn:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Oracle credentials are missing. Set DB_USERNAME, DB_PASSWORD, and DB_DSN in mamahub-whatsapp/.env",
            )
        _engine = create_engine(
            "oracle+oracledb://",
            creator=_creator,
            pool_pre_ping=True,
            pool_size=settings.oracle_pool_min,
            max_overflow=max(0, settings.oracle_pool_max - settings.oracle_pool_min),
            pool_recycle=1800,
        )

        @event.listens_for(_engine, "connect")
        def _disable_parallel(dbapi_conn, _connection_record):  # noqa: ANN001
            try:
                cursor = dbapi_conn.cursor()
                cursor.execute("ALTER SESSION DISABLE PARALLEL DML")
                cursor.close()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not disable parallel DML: %s", exc)

    return _engine


def get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False, expire_on_commit=False)
    return _SessionLocal


def get_db() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
