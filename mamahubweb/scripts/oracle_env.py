"""Load Oracle connection settings from environment for schema scripts."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore[assignment,misc]


@dataclass(frozen=True)
class OracleSettings:
    host: str
    port: int
    service_name: str
    username: str
    password: str

    @property
    def dsn(self) -> str:
        return f'{self.host}:{self.port}/{self.service_name}'


def load_oracle_settings() -> OracleSettings:
    repo_root = Path(__file__).resolve().parents[1]
    env_file = repo_root / '.env'
    if load_dotenv and env_file.is_file():
        load_dotenv(env_file)

    return OracleSettings(
        host=os.getenv('ORACLE_HOST', 'localhost'),
        port=int(os.getenv('ORACLE_PORT', '1521')),
        service_name=os.getenv('ORACLE_SERVICE_NAME', 'ORCL'),
        username=os.getenv('ORACLE_USERNAME', 'TOY_STORE'),
        password=os.getenv('ORACLE_PASSWORD', 'change_me'),
    )
