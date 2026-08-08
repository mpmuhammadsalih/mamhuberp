"""Guards for mobile database setup endpoints (pre-login configuration screen)."""

from __future__ import annotations

from fastapi import Header, HTTPException

from mobile_backend.config import Config


def require_config_setup_key(
    x_config_setup_key: str | None = Header(None, alias="X-Config-Setup-Key"),
) -> None:
    expected = Config.CONFIG_SETUP_KEY
    if expected:
        if (x_config_setup_key or "").strip() != expected:
            raise HTTPException(
                status_code=403,
                detail="Invalid or missing setup key (X-Config-Setup-Key). Set CONFIG_SETUP_KEY in erp_api/.env.",
            )
        return
    if not Config.DEBUG:
        raise HTTPException(
            status_code=403,
            detail=(
                "Database setup from the app is disabled. Set CONFIG_SETUP_KEY in erp_api/.env "
                "or enable FLASK_ENV=development."
            ),
        )
