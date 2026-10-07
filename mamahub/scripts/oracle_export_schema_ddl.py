"""
Export ``CREATE TABLE`` (and optionally index) DDL from an Oracle schema using ``DBMS_METADATA``.

This produces **real SQL** you can review and run on an **empty** target schema/user to recreate
table structure. It does **not** copy data. For a full database clone, prefer Oracle Data Pump
(``expdp`` / ``impdp``) or DBA-provided tools.

Uses the same credentials as ``oracle_introspect_models.py`` (e.g. ``RFIM_*`` for ``--profile rfim``).

Examples::

    # .env with RFIM_USERNAME, RFIM_PASSWORD, RFIM_DSN
    python scripts/oracle_export_schema_ddl.py --profile rfim --out exports/rfim_tables.sql

    python scripts/oracle_export_schema_ddl.py --profile rfim --user rfim --password rfim \\
        --dsn 192.168.1.225:1521/rgc --out exports/rfim_tables.sql

    # First 5 tables only (smoke test)
    python scripts/oracle_export_schema_ddl.py --profile rfim --max-tables 5 --out exports/sample.sql

**FK order:** DDL is emitted in table-name order; if FK creation fails, run failed statements after
parents exist, or export with DBA help. For many schemas, running the whole file once works.

Optional: ``--indexes`` appends separate ``CREATE INDEX`` statements (normal indexes visible to metadata).

See ``oracle_apply_schema_ddl.py`` to **write remapped DDL and optionally execute it** on another
Oracle user (destructive — read that script's warnings first).
"""
from __future__ import annotations
import argparse
import importlib.util
import sys
from pathlib import Path
from typing import Any
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

def _conn_params(profile: str, user_o: str | None, pwd_o: str | None, dsn_o: str | None):
    """Load ``conn_params`` from ``oracle_introspect_models.py`` (single source)."""
    path = SCRIPT_DIR / 'oracle_introspect_models.py'
    spec = importlib.util.spec_from_file_location('_oracle_introspect_models', path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Cannot load {path}')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.conn_params(profile, user_o, pwd_o, dsn_o)

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
    blocks = ["\n        BEGIN\n          DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'SQLTERMINATOR', TRUE);\n          DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'PRETTY', TRUE);\n        END;\n        ", "\n        BEGIN\n          DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'SEGMENT_ATTRIBUTES', FALSE);\n        EXCEPTION\n          WHEN OTHERS THEN NULL;\n        END;\n        ", "\n        BEGIN\n          DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'STORAGE', FALSE);\n        EXCEPTION\n          WHEN OTHERS THEN NULL;\n        END;\n        "]
    for plsql in blocks:
        try:
            cur.execute(plsql)
        except Exception:
            pass

def main() -> int:
    ap = argparse.ArgumentParser(description='Export Oracle CREATE TABLE DDL via DBMS_METADATA.')
    ap.add_argument('--profile', choices=('db', 'auth', 'central', 'rfim'), default='rfim', help='.env credential block')
    ap.add_argument('--user', help='Oracle user override')
    ap.add_argument('--password', default='', help='Password (omit with --user/--dsn to use .env)')
    ap.add_argument('--dsn', help='Host:port/service')
    ap.add_argument('--owner', help='Schema for ALL_OBJECTS (omit = connected user USER_* views)')
    ap.add_argument('--out', '-o', default=str(PROJECT_ROOT / 'exports' / 'rfim_schema_tables.sql'), help='Output .sql path')
    ap.add_argument('--max-tables', type=int, default=0, help='Limit number of tables (0 = all)')
    ap.add_argument('--tables', help='Comma-separated table names only')
    ap.add_argument('--indexes', action='store_true', help='Append CREATE INDEX for non-unusable indexes owned by schema')
    args = ap.parse_args()
    try:
        from db.oracle_driver import oracle_connect
    except ImportError as e:
        print('oracledb required:', e, file=sys.stderr)
        return 1
    pwd_in = (args.password or '').strip()
    user, password, dsn = _conn_params(args.profile, args.user.strip() if args.user else None, pwd_in if pwd_in else None, args.dsn.strip() if args.dsn else None)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    conn = oracle_connect(user=user, password=password, dsn=dsn)
    cur = conn.cursor()
    try:
        _run_metadata_setup(cur)
        cur.execute('SELECT USER FROM DUAL')
        connected_user = str(cur.fetchone()[0]).strip()
        owner = (args.owner or connected_user).strip().upper()
        want: set[str] | None = None
        if args.tables:
            want = {t.strip().upper() for t in args.tables.split(',') if t.strip()}
        if args.owner:
            cur.execute("\n                SELECT t.TABLE_NAME\n                  FROM ALL_TABLES t\n                 WHERE t.OWNER = :ow\n                   AND t.TABLE_NAME NOT LIKE 'BIN$%%'\n                   AND t.TABLE_NAME NOT LIKE 'DR$%%'\n                 ORDER BY t.TABLE_NAME\n                ", {'ow': owner})
        else:
            cur.execute("\n                SELECT TABLE_NAME FROM USER_TABLES\n                 WHERE TABLE_NAME NOT LIKE 'BIN$%%'\n                 AND TABLE_NAME NOT LIKE 'DR$%%'\n                 ORDER BY TABLE_NAME\n                ")
        tables = [str(r[0]) for r in cur.fetchall() if r[0]]
        if want:
            tables = [t for t in tables if t in want]
            missing = want - set(tables)
            if missing:
                print('Warning: tables not found in schema:', ', '.join(sorted(missing)), file=sys.stderr)
        if args.max_tables > 0:
            tables = tables[:args.max_tables]
        banner = f'-- AUTO-GENERATED DDL export\n-- Profile: {args.profile}, connected as: {connected_user}, owner: {owner}\n-- Tables: {len(tables)}\n-- Review before running; create target user/tablespace first.\n\n'
        chunks: list[str] = [banner]
        print(f'Exporting {len(tables)} tables...', file=sys.stderr)
        for i, tn in enumerate(tables, 1):
            try:
                cur.execute("\n                    SELECT DBMS_METADATA.GET_DDL(object_type => 'TABLE',\n                                                 name           => :tname,\n                                                 schema         => :own)\n                      FROM DUAL\n                    ", {'tname': tn, 'own': owner})
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
                print(f'Warning: {tn}: {ex}', file=sys.stderr)
            if i % 50 == 0:
                print(f'  ... {i}/{len(tables)}', file=sys.stderr)
        if args.indexes:
            chunks.append('\n-- ========== INDEXES ==========\n\n')
            if args.owner:
                cur.execute("\n                    SELECT i.INDEX_NAME\n                      FROM ALL_INDEXES i\n                     WHERE i.OWNER = :ow\n                       AND i.INDEX_TYPE IN ('NORMAL', 'BITMAP', 'FUNCTION-BASED NORMAL')\n                       AND i.TABLE_NAME NOT LIKE 'BIN$%%'\n                       AND i.TABLESPACE_NAME IS NOT NULL\n                     ORDER BY i.INDEX_NAME\n                    ", {'ow': owner})
            else:
                cur.execute("\n                    SELECT INDEX_NAME FROM USER_INDEXES\n                     WHERE INDEX_TYPE IN ('NORMAL', 'BITMAP', 'FUNCTION-BASED NORMAL')\n                     AND TABLESPACE_NAME IS NOT NULL\n                     ORDER BY INDEX_NAME\n                    ")
            idx_names = [str(r[0]) for r in cur.fetchall() if r[0]]
            for iname in idx_names:
                try:
                    cur.execute("\n                        SELECT DBMS_METADATA.GET_DDL('INDEX', :iname, :own) FROM DUAL\n                        ", {'iname': iname, 'own': owner})
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
                    chunks.append(f'-- ERROR index {iname}: {ex}\n\n')
        out_path.write_text(''.join(chunks))
        print(f'Wrote {out_path}', file=sys.stderr)
    finally:
        cur.close()
        conn.close()
    return 0
if __name__ == '__main__':
    raise SystemExit(main())
