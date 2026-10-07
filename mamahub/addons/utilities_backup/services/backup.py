"""Oracle backup helpers — schema DDL export and backup file storage."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from db.oracle_driver import oracle_connect

from config.settings import get_auth_db_config, get_db_config, is_multi_db_mode

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_BACKUP_DIR = _PROJECT_ROOT / 'exports' / 'backups'
_SAFE_NAME_RE = re.compile(r'^[A-Za-z0-9._-]+$')


def backup_dir() -> Path:
    _BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    return _BACKUP_DIR


def _mask_dsn(dsn: str) -> str:
    s = (dsn or '').strip()
    if not s:
        return '—'
    if '@' in s:
        return s.split('@', 1)[-1]
    return s


def _read_metadata_lob(value: Any) -> str:
    if value is None:
        return ''
    if hasattr(value, 'read'):
        raw = value.read()
        if isinstance(raw, bytes):
            return raw.decode('utf-8', errors='replace')
        return str(raw)
    return str(value)


def _run_metadata_setup(cur: Any) -> None:
    blocks = [
        """
        BEGIN
          DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'SQLTERMINATOR', TRUE);
          DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'PRETTY', TRUE);
        END;
        """,
        """
        BEGIN
          DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'SEGMENT_ATTRIBUTES', FALSE);
        EXCEPTION
          WHEN OTHERS THEN NULL;
        END;
        """,
        """
        BEGIN
          DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'STORAGE', FALSE);
        EXCEPTION
          WHEN OTHERS THEN NULL;
        END;
        """,
    ]
    for plsql in blocks:
        try:
            cur.execute(plsql)
        except Exception:
            pass


def resolve_backup_targets(session: Dict[str, Any]) -> List[Dict[str, str]]:
    """Return backup targets the current user may export (label + key)."""
    targets: List[Dict[str, str]] = []
    if is_multi_db_mode():
        tid = (session.get('tenant_id') or '').strip()
        if tid:
            try:
                from db import get_tenant_config
                cfg = get_tenant_config(tid)
                targets.append({
                    'key': 'tenant',
                    'label': f'Business DB ({tid})',
                    'user': (cfg.get('user') or '').strip(),
                    'dsn': _mask_dsn(cfg.get('dsn') or ''),
                })
            except Exception:
                targets.append({'key': 'tenant', 'label': f'Business DB ({tid})', 'user': '—', 'dsn': '—'})
        auth = get_auth_db_config()
        if auth.get('user') and auth.get('dsn'):
            targets.append({
                'key': 'auth',
                'label': 'Auth DB',
                'user': (auth.get('user') or '').strip(),
                'dsn': _mask_dsn(auth.get('dsn') or ''),
            })
    else:
        cfg = get_db_config()
        targets.append({
            'key': 'business',
            'label': 'Business DB',
            'user': (cfg.get('user') or '').strip(),
            'dsn': _mask_dsn(cfg.get('dsn') or ''),
        })
    return targets


def _resolve_credentials(target_key: str, session: Dict[str, Any]) -> Tuple[Dict[str, str], str]:
    """Return (user/password/dsn dict, owner schema label)."""
    key = (target_key or 'business').strip().lower()
    if key == 'auth':
        cfg = get_auth_db_config()
        if not cfg.get('user') or not cfg.get('dsn'):
            raise ValueError('Auth database is not configured.')
        return {
            'user': cfg['user'],
            'password': cfg.get('password') or '',
            'dsn': cfg['dsn'],
        }, 'auth'
    if key == 'tenant':
        tid = (session.get('tenant_id') or '').strip()
        if not tid:
            raise ValueError('No tenant is selected for this session.')
        from db import get_tenant_config
        cfg = get_tenant_config(tid)
        return cfg, tid
    cfg = get_db_config()
    if not cfg.get('user') or not cfg.get('dsn'):
        raise ValueError('Business database is not configured.')
    return cfg, 'business'


def export_schema_ddl(target_key: str, session: Dict[str, Any]) -> Tuple[str, str]:
    """Export CREATE TABLE DDL for the connected schema. Returns (sql_text, suggested_filename)."""
    cfg, tag = _resolve_credentials(target_key, session)
    conn = oracle_connect(
        user=cfg['user'],
        password=cfg.get('password') or '',
        dsn=cfg['dsn'],
    )
    cur = conn.cursor()
    try:
        _run_metadata_setup(cur)
        cur.execute('SELECT USER FROM DUAL')
        connected_user = str(cur.fetchone()[0]).strip()
        owner = connected_user.upper()
        cur.execute(
            """
            SELECT TABLE_NAME FROM USER_TABLES
             WHERE TABLE_NAME NOT LIKE 'BIN$%'
               AND TABLE_NAME NOT LIKE 'DR$%'
             ORDER BY TABLE_NAME
            """
        )
        tables = [str(r[0]) for r in cur.fetchall() if r[0]]
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        banner = (
            f'-- AUTO-GENERATED schema DDL backup\n'
            f'-- Target: {tag}, connected as: {connected_user}\n'
            f'-- Tables: {len(tables)}\n'
            f'-- Generated: {datetime.now().isoformat(timespec="seconds")}\n'
            f'-- Structure only — no data. For full data clone use Oracle Data Pump (expdp).\n\n'
        )
        chunks: List[str] = [banner]
        for tn in tables:
            try:
                cur.execute(
                    """
                    SELECT DBMS_METADATA.GET_DDL(
                             object_type => 'TABLE',
                             name           => :tname,
                             schema         => :own)
                      FROM DUAL
                    """,
                    {'tname': tn, 'own': owner},
                )
                row = cur.fetchone()
                if not row:
                    continue
                ddl = _read_metadata_lob(row[0]).strip()
                if ddl:
                    chunks.append(ddl)
                    if not ddl.rstrip().endswith(';'):
                        chunks.append(';')
                    chunks.append('\n\n')
            except Exception as ex:
                chunks.append(f'-- ERROR exporting {tn}: {ex}\n\n')
        sql_text = ''.join(chunks)
        fname = f'schema_{tag}_{connected_user.lower()}_{stamp}.sql'
        return sql_text, fname
    finally:
        cur.close()
        conn.close()


def save_backup_file(content: str, filename: str) -> Path:
    safe = Path(filename).name
    if not _SAFE_NAME_RE.match(safe):
        raise ValueError('Invalid backup filename.')
    path = backup_dir() / safe
    path.write_text(content, encoding='utf-8')
    return path


def list_backup_files() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    bdir = backup_dir()
    for p in sorted(bdir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if not p.is_file():
            continue
        if p.suffix.lower() not in ('.sql', '.dmp', '.log', '.zip'):
            continue
        st = p.stat()
        out.append({
            'name': p.name,
            'size_kb': round(st.st_size / 1024, 1),
            'modified': datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d %H:%M'),
            'kind': p.suffix.lower().lstrip('.').upper(),
        })
    return out


def resolve_download_path(filename: str) -> Optional[Path]:
    safe = Path(filename).name
    if not _SAFE_NAME_RE.match(safe):
        return None
    path = backup_dir() / safe
    if not path.is_file():
        return None
    return path


def datapump_command_hint(target_key: str, session: Dict[str, Any], oracle_directory: str = 'DATA_PUMP_DIR') -> str:
    """Return a copy-paste expdp command template (no password embedded)."""
    cfg, tag = _resolve_credentials(target_key, session)
    user = (cfg.get('user') or '').strip()
    dsn = (cfg.get('dsn') or '').strip()
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    schema = user.upper()
    dumpfile = f'{tag}_{schema.lower()}_{stamp}.dmp'
    logfile = f'{tag}_{schema.lower()}_{stamp}.log'
    dir_name = (oracle_directory or 'DATA_PUMP_DIR').strip() or 'DATA_PUMP_DIR'
    connect = f'{user}/<password>@{dsn}'
    return (
        f'expdp {connect} schemas={schema} directory={dir_name} '
        f'dumpfile={dumpfile} logfile={logfile} compression=all'
    )
