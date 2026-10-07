"""Application settings loaded from environment variables."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "MamaHub WhatsApp CRM"
    app_env: str = "production"
    app_host: str = "0.0.0.0"
    app_port: int = 8090
    frontend_url: str = "http://127.0.0.1:3090"
    cors_origins: str = "http://127.0.0.1:3090,http://localhost:3090"
    upload_dir: str = "uploads"

    db_username: str = ""
    db_password: str = ""
    db_dsn: str = ""
    oracle_pool_min: int = 2
    oracle_pool_max: int = 8
    oracle_tcp_connect_timeout: int = 15
    oracle_location_code: int = 1

    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_minutes: int = 5256000
    jwt_refresh_days: int = 3650

    bootstrap_admin_username: str = "admin"
    bootstrap_admin_password: str = "admin123"
    bootstrap_admin_email: str = "admin@mamahub.store"
    bootstrap_admin_name: str = "MamaHub Admin"

    whatsapp_access_token: str = Field(default="", validation_alias="WHATSAPP_ACCESS_TOKEN")
    whatsapp_phone_number_id: str = ""
    whatsapp_business_account_id: str = ""
    whatsapp_verify_token: str = ""
    whatsapp_api_version: str = "v21.0"
    whatsapp_display_number: str = ""
    meta_app_secret: str = ""

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    company_name: str = "MamaHub Trading"
    company_currency: str = "QAR"
    company_country: str = "Qatar"
    storefront_base_url: str = "https://www.mamahub.store"

    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_mailto: str = "mailto:admin@mamahub.store"

    @property
    def cors_origin_list(self) -> List[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def upload_path(self) -> Path:
        path = Path(self.upload_dir)
        if not path.is_absolute():
            path = ROOT_DIR / path
        path.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache
def get_settings() -> Settings:
    return Settings()
