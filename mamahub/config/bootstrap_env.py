"""Load `.env` from the project root before other imports; normalize auth vs single-DB env."""
from __future__ import annotations
import os
from pathlib import Path
from dotenv import dotenv_values, load_dotenv
_APP_ROOT = Path(__file__).resolve().parents[1]
_ENV_PATH = _APP_ROOT / '.env'

_ORACLE_ENV_KEYS = (
    'DB_USERNAME', 'DB_PASSWORD', 'DB_DSN',
    'AUTH_DB_USERNAME', 'AUTH_DB_PASSWORD', 'AUTH_DB_DSN',
    'ORACLE_WALLET_DIR', 'ORACLE_CONFIG_DIR', 'ORACLE_WALLET_PASSWORD',
    'ORACLE_HOST', 'ORACLE_PORT', 'ORACLE_SERVICE_NAME', 'ORACLE_SERVICE',
    'ORACLE_SSL_SERVER_CERT_DN',
)


def _strip_surrounding_quotes(value: str) -> str:
    s = value.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "'\"":
        return s[1:-1].strip()
    return s


def _normalize_oracle_env_strings() -> None:
    """``.env`` users often wrap DSNs in quotes; ``oracledb`` needs a bare DSN / TNS alias string."""
    for k in _ORACLE_ENV_KEYS:
        v = os.environ.get(k)
        if v is not None and v != '':
            os.environ[k] = _strip_surrounding_quotes(v)


def _configure_oracle_wallet() -> None:
    """Point ``TNS_ADMIN`` at the Autonomous DB wallet when ``ORACLE_WALLET_DIR`` is set."""
    wallet = (os.environ.get('ORACLE_WALLET_DIR') or os.environ.get('ORACLE_CONFIG_DIR') or '').strip()
    if not wallet:
        return
    p = Path(wallet).expanduser()
    if p.is_dir():
        os.environ['TNS_ADMIN'] = str(p.resolve())


def _configure_oracle_client_network() -> None:
    """
    On Windows, Instant Client often ships sqlnet.ora with NTS enabled, which breaks
    oracledb username/password logins (ORA-12638 / ORA-12631). Point TNS_ADMIN at the
    project copy with AUTHENTICATION_SERVICES=(NONE). EZCONNECT DSNs still work.
    Skipped when ``ORACLE_WALLET_DIR`` is set (Autonomous DB wallet supplies sqlnet.ora).
    Set NEXA_ORACLE_KEEP_TNS_ADMIN=1 in .env to keep your existing TNS_ADMIN.
    """
    if wallet_dir := (os.environ.get('ORACLE_WALLET_DIR') or os.environ.get('ORACLE_CONFIG_DIR') or '').strip():
        if Path(wallet_dir).expanduser().is_dir():
            return
    if os.name != 'nt':
        return
    if os.environ.get('NEXA_ORACLE_KEEP_TNS_ADMIN', '').strip().lower() in ('1', 'true', 'yes', 'on'):
        return
    net_dir = _APP_ROOT / 'oracle_network'
    net_dir.mkdir(parents=True, exist_ok=True)
    sqlnet = net_dir / 'sqlnet.ora'
    if not sqlnet.is_file():
        sqlnet.write_text(
            '# Nexa ERP — password auth for oracledb on Windows (avoids ORA-12638 from NTS).\n'
            'SQLNET.AUTHENTICATION_SERVICES=(NONE)\n'
            'NAMES.DIRECTORY_PATH=(TNSNAMES, EZCONNECT)\n',
            encoding='ascii',
        )
    os.environ['TNS_ADMIN'] = str(net_dir)


def bootstrap_dotenv() -> None:
    """
    Apply project ``.env`` with override=True so values win over stale Windows/session env vars.

    If ``AUTH_DB_USERNAME`` / ``AUTH_DB_DSN`` keys are missing from ``.env`` (e.g. commented out),
    remove inherited ``AUTH_DB_*`` from ``os.environ`` so single-DB mode works. Defining the keys
    in ``.env`` (even as empty) uses the file as source of truth without clearing.
    """
    load_dotenv(_ENV_PATH, override=True)
    _normalize_oracle_env_strings()
    _configure_oracle_wallet()
    _configure_oracle_client_network()
    if not _ENV_PATH.is_file():
        return
    raw = dotenv_values(_ENV_PATH)
    auth_keys = ('AUTH_DB_USERNAME', 'AUTH_DB_PASSWORD', 'AUTH_DB_DSN')
    if any((k in raw for k in auth_keys)):
        return
    for k in auth_keys:
        os.environ.pop(k, None)
