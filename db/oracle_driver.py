"""Oracle DB (python-oracledb): thin mode by default; wallet or TLS (no wallet) for Autonomous DB."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Optional, Tuple
from urllib.parse import parse_qs

import oracledb

_client_initialized = False
_pools: dict[str, oracledb.ConnectionPool] = {}


def _keep_parallel_dml() -> bool:
    return (os.getenv('ORACLE_KEEP_PARALLEL_DML') or '').strip().lower() in ('1', 'true', 'yes', 'on')


def _prepare_oltp_session(conn: oracledb.Connection, _requested_tag: Any = None) -> None:
    """Disable parallel DML on pooled sessions (avoids ORA-12838 on Autonomous high/medium)."""
    if _keep_parallel_dml() or conn is None:
        return
    try:
        with conn.cursor() as cur:
            cur.execute('ALTER SESSION DISABLE PARALLEL DML')
    except Exception as e:
        msg = str(e).lower()
        # Pool session_callback can run before a handle is fully live (DPY-1001).
        if 'dpy-1001' in msg or 'not connected' in msg:
            return
        print(f'[WARN oracle_connect] DISABLE PARALLEL DML: {e}')


def _oracle_tcp_connect_timeout_seconds() -> Optional[int]:
    raw = (os.getenv('ORACLE_TCP_CONNECT_TIMEOUT') or '').strip()
    if raw.isdigit():
        v = int(raw)
        return v if v > 0 else None
    return None


def wallet_dir() -> str:
    """Resolved wallet directory from ``ORACLE_WALLET_DIR`` / ``ORACLE_CONFIG_DIR``."""
    for key in ('ORACLE_WALLET_DIR', 'ORACLE_CONFIG_DIR'):
        v = (os.getenv(key) or '').strip()
        if v:
            p = Path(v).expanduser()
            if p.is_dir():
                return str(p.resolve())
    return ''


def _env_flag(name: str, *aliases: str) -> bool:
    for key in (name, *aliases):
        raw = (os.getenv(key) or '').strip().lower()
        if raw in ('1', 'true', 'yes', 'on', 'tcps', 'tls'):
            return True
        if raw in ('0', 'false', 'no', 'off', 'tcp'):
            return False
    return False


def _env_tcps_enabled() -> bool:
    return _env_flag('ORACLE_USE_TCPS', 'ORACLE_PROTOCOL', 'ORACLE_TLS')


def _ssl_server_dn_match() -> bool:
    raw = (os.getenv('ORACLE_SSL_SERVER_DN_MATCH') or '').strip().lower()
    if raw in ('0', 'false', 'no', 'off'):
        return False
    return True


def _is_tcps_dsn(dsn: str) -> bool:
    d = (dsn or '').strip().lower()
    if not d:
        return False
    if d.startswith('tcps://'):
        return True
    if 'protocol=tcps' in d:
        return True
    if re.search(r'\(\s*protocol\s*=\s*tcps\s*\)', d, re.I):
        return True
    return False


def _is_tns_descriptor(dsn: str) -> bool:
    d = (dsn or '').strip()
    return d.startswith('(') and 'description' in d.lower()


def _parse_ezconnect(dsn: str) -> Tuple[str, Optional[int], str]:
    """Parse ``host:port/service``, ``host/service``, or ``tcps://host:port/service``."""
    raw = (dsn or '').strip()
    query = ''
    if '?' in raw:
        raw, query = raw.split('?', 1)
    if raw.lower().startswith('tcps://'):
        raw = raw[7:]
    host = ''
    port: Optional[int] = None
    service = ''
    if '/' in raw:
        host_part, service = raw.rsplit('/', 1)
        service = service.strip()
    else:
        host_part = raw
    host_part = host_part.strip()
    if ':' in host_part:
        host, port_s = host_part.rsplit(':', 1)
        host = host.strip()
        if port_s.isdigit():
            port = int(port_s)
    else:
        host = host_part
    if not service and query:
        svc_vals = parse_qs(query).get('service_name') or parse_qs(query).get('service')
        if svc_vals:
            service = (svc_vals[0] or '').strip()
    return host, port, service


def _tcps_connect_parts(dsn: str) -> dict[str, Any]:
    """Build host/port/service TCPS kwargs from DSN or ``ORACLE_HOST`` env vars."""
    host = (os.getenv('ORACLE_HOST') or '').strip()
    service = (os.getenv('ORACLE_SERVICE_NAME') or os.getenv('ORACLE_SERVICE') or '').strip()
    port_raw = (os.getenv('ORACLE_PORT') or '').strip()
    port: Optional[int] = int(port_raw) if port_raw.isdigit() else None

    if dsn:
        h, p, s = _parse_ezconnect(dsn)
        host = host or h
        if port is None and p is not None:
            port = p
        service = service or s

    kw: dict[str, Any] = {'protocol': 'tcps'}
    if host:
        kw['host'] = host
    if port is not None:
        kw['port'] = port
    elif _env_tcps_enabled() and not _is_tns_descriptor(dsn):
        # Autonomous DB default TLS port when not specified.
        kw['port'] = 1522
    if service:
        kw['service_name'] = service
    return kw


def _apply_tcps_security(kw: dict[str, Any]) -> None:
    if _ssl_server_dn_match():
        kw['ssl_server_dn_match'] = True
    cert_dn = (os.getenv('ORACLE_SSL_SERVER_CERT_DN') or '').strip()
    if cert_dn:
        kw['ssl_server_cert_dn'] = cert_dn


def init_oracle_client() -> None:
    """Enable thick mode when ``ORACLE_CLIENT_MODE=thick`` or ``ORACLE_USE_THICK_MODE=1``."""
    global _client_initialized
    if _client_initialized:
        return
    mode = (os.getenv('ORACLE_CLIENT_MODE') or os.getenv('ORACLE_USE_THICK_MODE') or '').strip().lower()
    if mode in ('thick', '1', 'true', 'yes', 'on'):
        lib_dir = (os.getenv('ORACLE_CLIENT_LIB_DIR') or os.getenv('ORACLE_HOME') or '').strip()
        if lib_dir:
            oracledb.init_oracle_client(lib_dir=lib_dir)
        else:
            oracledb.init_oracle_client()
    _client_initialized = True


def _connect_kwargs(user: str, password: str, dsn: str) -> dict[str, Any]:
    kw: dict[str, Any] = {
        'user': (user or '').strip(),
        'password': password or '',
    }
    dsn = (dsn or '').strip()

    wallet = wallet_dir()
    if wallet:
        kw['dsn'] = dsn
        kw['config_dir'] = wallet
        kw['wallet_location'] = wallet
        wp = (os.getenv('ORACLE_WALLET_PASSWORD') or '').strip()
        if wp:
            kw['wallet_password'] = wp
        return kw

    use_tcps = _is_tcps_dsn(dsn) or _env_tcps_enabled()

    if use_tcps:
        if _is_tns_descriptor(dsn) or dsn.lower().startswith('tcps://') or 'protocol=tcps' in dsn.lower():
            # Full TLS connect descriptor from OCI console, or EZCONNECT ?protocol=tcps / tcps:// URL.
            kw['dsn'] = dsn
        else:
            parts = _tcps_connect_parts(dsn)
            kw.update(parts)
            if not parts.get('host') and dsn:
                kw['dsn'] = dsn
        _apply_tcps_security(kw)
        return kw

    kw['dsn'] = dsn
    return kw


def _pool_enabled() -> bool:
    raw = (os.getenv('ORACLE_POOL') or os.getenv('ORACLE_USE_POOL') or '1').strip().lower()
    return raw not in ('0', 'false', 'no', 'off')


def _pool_sizes() -> tuple[int, int, int]:
    def _int(name: str, default: int) -> int:
        raw = (os.getenv(name) or '').strip()
        return int(raw) if raw.isdigit() else default

    return (_int('ORACLE_POOL_MIN', 2), _int('ORACLE_POOL_MAX', 10), _int('ORACLE_POOL_INCREMENT', 1))


def _pool_key(user: str, password: str, dsn: str) -> str:
    return '|'.join([(user or '').strip(), (dsn or '').strip(), wallet_dir(), password or ''])


def _get_pool(user: str, password: str, dsn: str) -> oracledb.ConnectionPool:
    key = _pool_key(user, password, dsn)
    pool = _pools.get(key)
    if pool is not None:
        return pool
    kw = _connect_kwargs(user, password, dsn)
    tsec = _oracle_tcp_connect_timeout_seconds()
    if tsec is not None:
        kw['tcp_connect_timeout'] = tsec
    pool_min, pool_max, pool_inc = _pool_sizes()
    pool = oracledb.create_pool(
        min=pool_min,
        max=pool_max,
        increment=pool_inc,
        session_callback=_prepare_oltp_session,
        **kw,
    )
    _pools[key] = pool
    return pool


def oracle_connect(user: str, password: str, dsn: str) -> oracledb.Connection:
    """Open an Oracle connection (pooled by default; TLS or wallet via env / DSN)."""
    init_oracle_client()
    if _pool_enabled():
        # session_callback on the pool already runs _prepare_oltp_session on acquire.
        return _get_pool(user, password, dsn).acquire()
    kw = _connect_kwargs(user, password, dsn)
    tsec = _oracle_tcp_connect_timeout_seconds()
    if tsec is not None:
        try:
            conn = oracledb.connect(**kw, tcp_connect_timeout=tsec)
            _prepare_oltp_session(conn)
            return conn
        except TypeError:
            pass
    conn = oracledb.connect(**kw)
    _prepare_oltp_session(conn)
    return conn


# Backward-compatible alias used throughout the codebase.
cx_oracle_connect = oracle_connect


class _CxOracleCompat:
    """Drop-in shim so existing ``cx_Oracle`` call sites keep working."""

    connect = staticmethod(oracle_connect)
    DatabaseError = oracledb.DatabaseError
    Error = oracledb.Error
    InterfaceError = oracledb.InterfaceError
    OperationalError = oracledb.OperationalError
    IntegrityError = oracledb.IntegrityError
    CLOB = oracledb.DB_TYPE_CLOB
    NUMBER = oracledb.DB_TYPE_NUMBER
    Connection = oracledb.Connection


cx_Oracle = _CxOracleCompat()

DatabaseError = oracledb.DatabaseError
Error = oracledb.Error
