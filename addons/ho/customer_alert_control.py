"""HO customer-request alert control (CR_ALERT_CONTROL table)."""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Dict, Iterator

from db import _get_connection, _get_tenant_connection
from config.settings import is_multi_db_mode

CUSTOMER_ALERT_TABLE = 'CR_ALERT_CONTROL'
_SCHEMA_ENSURE_TTL_SEC = 300
_schema_ensure_cache: Dict[str, float] = {}


@contextmanager
def _alert_db_connection(tenant_id: str) -> Iterator:
    """Tenant DB in multi-DB mode; default business DB in single-DB mode."""
    if is_multi_db_mode():
        with _alert_db_connection(tenant_id) as conn:
            yield conn
    else:
        with _get_connection() as conn:
            yield conn


def _should_skip_schema_ensure(cache_key: str) -> bool:
    last_ok = _schema_ensure_cache.get(cache_key, 0.0)
    return time.time() - last_ok < _SCHEMA_ENSURE_TTL_SEC


def _mark_schema_ensure_ok(cache_key: str) -> None:
    _schema_ensure_cache[cache_key] = time.time()


def ensure_customer_alert_control_table(tenant_id: str) -> None:
    """Create or extend the single-row alert control table in the HO tenant DB."""
    cache_key = f'{tenant_id}:alert_control'
    if _should_skip_schema_ensure(cache_key):
        return
    with _alert_db_connection(tenant_id) as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT COUNT(*) FROM user_tables WHERE table_name = :t', {'t': CUSTOMER_ALERT_TABLE})
            exists = (cur.fetchone() or [0])[0] > 0
            if not exists:
                cur.execute(
                    f"""
                    CREATE TABLE {CUSTOMER_ALERT_TABLE} (
                        ID NUMBER PRIMARY KEY,
                        LAST_ACK_CODE NUMBER DEFAULT 0 NOT NULL,
                        UPDATEDBY VARCHAR2(50),
                        UPDATEDDATE DATE
                    )
                    """
                )
            cur.execute(f'SELECT COUNT(*) FROM {CUSTOMER_ALERT_TABLE} WHERE ID = 1')
            has_row = (cur.fetchone() or [0])[0] > 0
            if not has_row:
                cur.execute(
                    f"""
                    INSERT INTO {CUSTOMER_ALERT_TABLE} (ID, LAST_ACK_CODE, UPDATEDBY, UPDATEDDATE)
                    VALUES (1, 0, 'SYSTEM', SYSDATE)
                    """
                )
            for col_name, col_def in (
                ('AI_AUTO_CONVERT', "CHAR(1) DEFAULT 'N' NOT NULL"),
                ('ALERT_POLL_ENABLED', "CHAR(1) DEFAULT 'Y' NOT NULL"),
                ('TX_RECORDING_ENABLED', "CHAR(1) DEFAULT 'Y' NOT NULL"),
            ):
                cur.execute(
                    "SELECT COUNT(*) FROM user_tab_columns WHERE table_name = :t AND column_name = :c",
                    {'t': CUSTOMER_ALERT_TABLE, 'c': col_name},
                )
                if (cur.fetchone() or [0])[0] == 0:
                    try:
                        cur.execute(f'ALTER TABLE {CUSTOMER_ALERT_TABLE} ADD ( {col_name} {col_def} )')
                    except Exception:
                        pass
        conn.commit()
    _mark_schema_ensure_ok(cache_key)


def _read_flag(tenant_id: str, column: str, default: bool = False) -> bool:
    try:
        ensure_customer_alert_control_table(tenant_id)
        with _alert_db_connection(tenant_id) as conn:
            with conn.cursor() as cur:
                cur.execute(f'SELECT {column} FROM {CUSTOMER_ALERT_TABLE} WHERE ID = 1')
                row = cur.fetchone()
        if not row or row[0] is None:
            return default
        return str(row[0]).strip().upper() == 'Y'
    except Exception as exc:
        print(f'[customer_alert_control._read_flag {column}] ERROR: {exc}')
        return default


def _write_flag(tenant_id: str, column: str, enabled: bool, username: str) -> None:
    v = 'Y' if enabled else 'N'
    ensure_customer_alert_control_table(tenant_id)
    with _alert_db_connection(tenant_id) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f'UPDATE {CUSTOMER_ALERT_TABLE} SET {column} = :v, UPDATEDBY = :u, UPDATEDDATE = SYSDATE WHERE ID = 1',
                {'v': v, 'u': (username or 'SYSTEM')[:50]},
            )
        conn.commit()


def get_cr_ai_auto_convert_enabled(tenant_id: str) -> bool:
    return _read_flag(tenant_id, 'AI_AUTO_CONVERT', default=False)


def set_cr_ai_auto_convert_enabled(tenant_id: str, enabled: bool, username: str) -> None:
    _write_flag(tenant_id, 'AI_AUTO_CONVERT', enabled, username)


def get_customer_request_alert_poll_enabled(tenant_id: str) -> bool:
    return _read_flag(tenant_id, 'ALERT_POLL_ENABLED', default=True)


def set_customer_request_alert_poll_enabled(tenant_id: str, enabled: bool, username: str) -> None:
    _write_flag(tenant_id, 'ALERT_POLL_ENABLED', enabled, username)


def get_transaction_recording_enabled(tenant_id: str) -> bool:
    """Organization-wide transaction screen recording (``/audit/recording`` capture)."""
    return _read_flag(tenant_id, 'TX_RECORDING_ENABLED', default=True)


def set_transaction_recording_enabled(tenant_id: str, enabled: bool, username: str) -> None:
    _write_flag(tenant_id, 'TX_RECORDING_ENABLED', enabled, username)
