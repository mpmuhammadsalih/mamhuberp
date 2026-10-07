"""
Read ``DBMS_METADATA.GET_DDL`` from a **source** Oracle schema, optionally **remap** the owner in
the SQL, then either write a ``.sql`` file (default, safe) or **execute** each statement on a
**target** connection (destructive — empty target schema only).

This does **not** copy **data**, only metadata (``CREATE TABLE`` / ``CREATE INDEX``). For a full
clone use Data Pump.

**Safety**
  * Without ``--execute``: only builds remapped DDL and writes ``--out`` (default dry behaviour).
  * With ``--execute``: requires ``--target-user``, ``--target-password``, ``--target-dsn``, and
    ``--i-confirm`` (you must pass this flag explicitly).

Examples::

    # Preview only: write remapped SQL for review (uses RFIM_* from .env for source)
    python scripts/oracle_apply_schema_ddl.py --profile rfim --out exports/rfim_clone_preview.sql

    # Same + actually run on target (DESTRUCTIVE on target schema — must be empty / disposable)
    python scripts/oracle_apply_schema_ddl.py --profile rfim \\
        --target-user MY_TENANT --target-password secret --target-dsn localhost:1521/orcl \\
        --execute --i-confirm --out exports/rfim_clone_preview.sql

    # Smoke test: 2 tables only
    python scripts/oracle_apply_schema_ddl.py --profile rfim --max-tables 2 --out exports/t2.sql

``--remap-schema`` defaults to the **upper** ``--target-user`` so object names become
``CREATE TABLE "MY_TENANT"."BILLHDR" ...``.

If FK order errors occur, fix failed statements manually or run a second pass after parent tables exist.
"""
from __future__ import annotations
import argparse
import importlib.util
import sys
from pathlib import Path
from typing import Any, Iterator, List, Tuple
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

def _load_export_module():
    path = SCRIPT_DIR / 'oracle_export_schema_ddl.py'
    spec = importlib.util.spec_from_file_location('_oracle_export_schema_ddl', path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Cannot load {path}')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def remap_owner_in_ddl(ddl: str, from_owner: str, to_owner: str) -> str:
    """Replace quoted schema ``"SOURCE"`` with ``"TARGET"`` in metadata DDL."""
    fo = from_owner.strip().upper()
    to = to_owner.strip().upper()
    if fo == to:
        return ddl
    out = ddl.replace(f'"{fo}"', f'"{to}"')
    out = out.replace(f'"{fo.lower()}"', f'"{to}"')
    return out

def _list_tables(cur: Any, owner: str, owner_arg: str | None, want: set[str] | None, max_tables: int) -> List[str]:
    if owner_arg:
        cur.execute("\n            SELECT t.TABLE_NAME\n              FROM ALL_TABLES t\n             WHERE t.OWNER = :ow\n               AND t.TABLE_NAME NOT LIKE 'BIN$%%'\n               AND t.TABLE_NAME NOT LIKE 'DR$%%'\n             ORDER BY t.TABLE_NAME\n            ", {'ow': owner})
    else:
        cur.execute("\n            SELECT TABLE_NAME FROM USER_TABLES\n             WHERE TABLE_NAME NOT LIKE 'BIN$%%'\n             AND TABLE_NAME NOT LIKE 'DR$%%'\n             ORDER BY TABLE_NAME\n            ")
    tables = [str(r[0]) for r in cur.fetchall() if r[0]]
    if want:
        tables = [t for t in tables if t in want]
    if max_tables > 0:
        tables = tables[:max_tables]
    return tables

def _index_names(cur: Any, owner: str, owner_arg: str | None) -> List[str]:
    if owner_arg:
        cur.execute("\n            SELECT i.INDEX_NAME\n              FROM ALL_INDEXES i\n             WHERE i.OWNER = :ow\n               AND i.INDEX_TYPE IN ('NORMAL', 'BITMAP', 'FUNCTION-BASED NORMAL')\n               AND i.TABLE_NAME NOT LIKE 'BIN$%%'\n               AND i.TABLESPACE_NAME IS NOT NULL\n             ORDER BY i.INDEX_NAME\n            ", {'ow': owner})
    else:
        cur.execute("\n            SELECT INDEX_NAME FROM USER_INDEXES\n             WHERE INDEX_TYPE IN ('NORMAL', 'BITMAP', 'FUNCTION-BASED NORMAL')\n             AND TABLESPACE_NAME IS NOT NULL\n             ORDER BY INDEX_NAME\n            ")
    return [str(r[0]) for r in cur.fetchall() if r[0]]

def _yield_ddls(exp: Any, cur: Any, owner: str, owner_arg: str | None, tables: List[str], include_indexes: bool) -> Iterator[Tuple[str, str, str]]:
    """Yield (kind, name, raw_ddl_from_get_ddl)."""
    for tn in tables:
        try:
            cur.execute("\n                SELECT DBMS_METADATA.GET_DDL(object_type => 'TABLE',\n                                             name           => :tname,\n                                             schema         => :own)\n                  FROM DUAL\n                ", {'tname': tn, 'own': owner})
            row = cur.fetchone()
            if not row:
                continue
            ddl = exp._read_metadata_lob(row[0]).strip()
            if ddl:
                yield ('TABLE', tn, ddl)
        except Exception as ex:
            yield ('TABLE', tn, f'-- ERROR GET_DDL TABLE {tn}: {ex}\n')
    if include_indexes:
        for iname in _index_names(cur, owner, owner_arg):
            try:
                cur.execute("\n                    SELECT DBMS_METADATA.GET_DDL('INDEX', :iname, :own) FROM DUAL\n                    ", {'iname': iname, 'own': owner})
                row = cur.fetchone()
                if not row:
                    continue
                ddl = exp._read_metadata_lob(row[0]).strip()
                if ddl:
                    yield ('INDEX', iname, ddl)
            except Exception as ex:
                yield ('INDEX', iname, f'-- ERROR GET_DDL INDEX {iname}: {ex}\n')

def main() -> int:
    ap = argparse.ArgumentParser(description='Remap RFIM DDL and optionally EXECUTE on a target Oracle user (destructive).')
    ap.add_argument('--profile', choices=('db', 'auth', 'central', 'rfim'), default='rfim', help='.env credential block for the source connection')
    ap.add_argument('--user', help='Source Oracle user override')
    ap.add_argument('--password', default='', help='Source password (.env if omitted)')
    ap.add_argument('--dsn', help='Source DSN host:port/service')
    ap.add_argument('--owner', help='Source schema (omit = USER_TABLES mode)')
    ap.add_argument('--tables', help='Comma-separated table names only')
    ap.add_argument('--max-tables', type=int, default=0, help='Limit tables (0 = all)')
    ap.add_argument('--indexes', action='store_true', help='Include CREATE INDEX after tables')
    ap.add_argument('--out', '-o', default=str(PROJECT_ROOT / 'exports' / 'schema_clone_remapped.sql'), help='Write remapped DDL to this file (always written unless --stdout-only)')
    ap.add_argument('--stdout-only', action='store_true', help='Print remapped DDL to stdout instead of --out')
    ap.add_argument('--remap-schema', default='', help='Quoted owner to substitute in DDL (default: uppercase --target-user, or source user if dry-run)')
    ap.add_argument('--target-user', help='Target Oracle user for --execute (required)')
    ap.add_argument('--target-password', default='', help='Target password')
    ap.add_argument('--target-dsn', help='Target DSN')
    ap.add_argument('--execute', action='store_true', help='Run DDL on target (requires --target-* and --i-confirm)')
    ap.add_argument('--i-confirm', action='store_true', help='Must pass with --execute to acknowledge destructive apply on target')
    ap.add_argument('--continue-on-error', action='store_true', help='On execute: keep going after Oracle errors (default: stop at first failure)')
    args = ap.parse_args()
    try:
        from db.oracle_driver import oracle_connect
    except ImportError as e:
        print('oracledb required:', e, file=sys.stderr)
        return 1
    if args.execute:
        missing = []
        if not args.target_user:
            missing.append('--target-user')
        if not (args.target_password or '').strip():
            missing.append('--target-password (non-empty)')
        if not (args.target_dsn or '').strip():
            missing.append('--target-dsn')
        if not args.i_confirm:
            missing.append('--i-confirm (required with --execute)')
        if missing:
            print('Refusing --execute without: ' + ', '.join(missing), file=sys.stderr)
            return 2
    exp = _load_export_module()
    pwd_in = (args.password or '').strip()
    s_user, s_password, s_dsn = exp._conn_params(args.profile, args.user.strip() if args.user else None, pwd_in if pwd_in else None, args.dsn.strip() if args.dsn else None)
    want: set[str] | None = None
    if args.tables:
        want = {t.strip().upper() for t in args.tables.split(',') if t.strip()}
    src = oracle_connect(user=s_user, password=s_password, dsn=s_dsn)
    cur = src.cursor()
    try:
        exp._run_metadata_setup(cur)
        cur.execute('SELECT USER FROM DUAL')
        connected_user = str(cur.fetchone()[0]).strip()
        owner = (args.owner or connected_user).strip().upper()
        tables = _list_tables(cur, owner, args.owner, want, args.max_tables)
        if want:
            missing = want - set(tables)
            if missing:
                print('Warning: source tables not found:', ', '.join(sorted(missing)), file=sys.stderr)
        remap_dest = args.remap_schema.strip().upper() if (args.remap_schema or '').strip() else args.target_user.strip().upper() if args.execute else owner
        ddl_items: List[Tuple[str, str, str]] = []
        for kind, name, ddl in _yield_ddls(exp, cur, owner, args.owner, tables, args.indexes):
            ddl_items.append((kind, name, remap_owner_in_ddl(ddl, owner, remap_dest)))
        lines_out: List[str] = ['-- Remapped DDL (source owner -> remap target quoted schema)\n', f'-- Source: {connected_user} / owner objects: {owner}\n', f'-- Remap to: {remap_dest}\n\n']
        for kind, name, rddl in ddl_items:
            lines_out.append(f'-- {kind} {name}\n')
            chunk = rddl.strip()
            if chunk and (not chunk.endswith(';')):
                chunk += ';'
            lines_out.append(chunk)
            lines_out.append('\n\n')
        text_body = ''.join(lines_out)
        if args.stdout_only:
            print(text_body, end='')
        else:
            out_path = Path(args.out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(text_body)
            print(f'Wrote remapped DDL: {out_path}', file=sys.stderr)
        if args.execute:
            assert args.target_user
            tgt = oracle_connect(user=args.target_user.strip(), password=args.target_password.strip(), dsn=args.target_dsn.strip())
            tcur = tgt.cursor()
            ok = 0
            errors = 0
            print('Executing DDL on TARGET (this may CREATE objects — target must allow it)...', file=sys.stderr)
            try:
                for kind, name, rddl in ddl_items:
                    if rddl.strip().startswith('--'):
                        print(f'[skip comment/error stub] {kind} {name}', file=sys.stderr)
                        continue
                    stmt = rddl.strip().rstrip(';')
                    if not stmt:
                        continue
                    try:
                        tcur.execute(stmt)
                        ok += 1
                        if ok % 20 == 0:
                            print(f'  ... executed {ok} statements', file=sys.stderr)
                    except Exception as ex:
                        errors += 1
                        print(f'ERROR {kind} {name}: {ex}', file=sys.stderr)
                        if not args.continue_on_error:
                            print('Stopping (--continue-on-error to keep going).', file=sys.stderr)
                            return 3
            finally:
                tcur.close()
                tgt.close()
            print(f'Done. Executed OK: {ok}, errors: {errors}', file=sys.stderr)
            if errors:
                return 4
    finally:
        cur.close()
        src.close()
    return 0
if __name__ == '__main__':
    raise SystemExit(main())
