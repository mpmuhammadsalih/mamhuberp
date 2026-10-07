import os
from datetime import timedelta

from config.bootstrap_env import bootstrap_dotenv

bootstrap_dotenv()


class Config:
    FLASK_ENV = os.getenv("FLASK_ENV", "production")
    DEBUG = FLASK_ENV != "production"

    HOST = os.getenv("FLASK_HOST", "0.0.0.0")
    PORT = int(os.getenv("FLASK_PORT", "5051"))

    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "") or os.getenv("FLASK_SECRET_KEY", "")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=int(os.getenv("JWT_ACCESS_MINUTES", "20")))
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=int(os.getenv("JWT_REFRESH_DAYS", "30")))

    CORS_ORIGINS = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "*").split(",")]

    ORACLE_USER = os.getenv("ORACLE_USER") or os.getenv("AUTH_DB_USERNAME") or os.getenv("DB_USERNAME", "")
    ORACLE_PASSWORD = os.getenv("ORACLE_PASSWORD") or os.getenv("AUTH_DB_PASSWORD") or os.getenv("DB_PASSWORD", "")
    ORACLE_DSN = os.getenv("ORACLE_DSN") or os.getenv("AUTH_DB_DSN") or os.getenv("DB_DSN", "")
    ORACLE_POOL_MIN = int(os.getenv("ORACLE_POOL_MIN", "2"))
    ORACLE_POOL_MAX = int(os.getenv("ORACLE_POOL_MAX", "20"))
    ORACLE_POOL_INCREMENT = int(os.getenv("ORACLE_POOL_INCREMENT", "2"))
    ENFORCE_TENANT_ASSIGNMENT = os.getenv("ENFORCE_TENANT_ASSIGNMENT", "false").lower() == "true"

    AUTO_CREATE_GRN_MOBILE_EXT = os.getenv("AUTO_CREATE_GRN_MOBILE_EXT", "false").lower() == "true"
    CONFIG_SETUP_KEY = os.getenv("CONFIG_SETUP_KEY", "").strip()

    _lr_partial_raw = os.getenv("LRFLAG_PARTIAL_VALUES", "PR,PART,PARTIAL")
    LRFLAG_PARTIAL_VALUES: frozenset[str] = frozenset(x.strip().upper() for x in _lr_partial_raw.split(",") if x.strip())

    LPOHDR_GRN_STATUS_COLUMN = os.getenv("LPOHDR_GRN_STATUS_COLUMN", "NEXA_GRN_STATUS").strip().upper()
