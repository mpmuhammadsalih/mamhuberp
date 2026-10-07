"""
Audit Oracle **primary keys**, **unique**, and **foreign keys** for the connected (**USER**) schema.
Optionally emits **commented DDL stubs** and **same-name FK heuristics** — never executes DDL.

Full automatic FK/UNIQUE on every legacy ERP table is unsafe (orphan data, composites).
Use this output with a DBA, or on an empty schema after ``New Company setup``.

Examples::

    python scripts/oracle_constraint_audit.py --profile db
    python scripts/oracle_constraint_audit.py --profile db --suggest-fk --emit-sql exports/constraint_hints.sql

To **apply** heuristic foreign keys (dry-run by default; see ``oracle_apply_constraints.py``)::

    python scripts/oracle_apply_constraints.py --profile db
    python scripts/oracle_apply_constraints.py --profile db --execute --i-confirm
"""
from __future__ import annotations
import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

def conn_params(profile: str, user_o: str | None, pwd_o: str | None, dsn_o: str | None) -> tuple[str, str, str]:
    try:
        from dotenv import load_dotenv
        load_dotenv(PROJECT_ROOT / '.env')
    except ImportError:
        pass

    def _dbc():
        if profile == 'auth':
            from config.settings import get_auth_db_config
            return get_auth_db_config()
        if profile == 'rfim':
            from config.settings import get_rfim_schema_config
            return get_rfim_schema_config()
        from config.settings import get_db_config
        return get_db_config()
    if user_o and dsn_o:
        p = str(pwd_o) if pwd_o is not None else _dbc().get('password') or ''
        return (user_o.strip(), str(p).strip(), dsn_o.strip())
    c = _dbc()
    u, p, d = ((c.get('user') or '').strip(), str(c.get('password') or ''), (c.get('dsn') or '').strip())
    if not u or not d:
        raise SystemExit('Set credentials in .env or pass --user / --password / --dsn')
    return (u, p, d)

def _tables(cur: Any) -> list[str]:
    cur.execute("\n        SELECT TABLE_NAME FROM USER_TABLES\n         WHERE TABLE_NAME NOT LIKE 'BIN$%'\n           AND TABLE_NAME NOT LIKE 'DR$%'\n         ORDER BY TABLE_NAME\n        ")
    return [str(r[0]).upper() for r in cur.fetchall() if r and r[0]]

def _cons_columns_ordered(cur: Any, constraint_name: str) -> tuple[str, ...]:
    cur.execute('\n        SELECT COLUMN_NAME FROM USER_CONS_COLUMNS\n         WHERE CONSTRAINT_NAME = :c\n         ORDER BY POSITION\n        ', {'c': constraint_name})
    return tuple((str(r[0]).upper() for r in cur.fetchall() if r and r[0]))

def load_pk_map(cur: Any) -> dict[str, tuple[str, ...]]:
    cur.execute("\n        SELECT CONSTRAINT_NAME, TABLE_NAME FROM USER_CONSTRAINTS\n         WHERE CONSTRAINT_TYPE = 'P' AND TABLE_NAME NOT LIKE 'BIN$%'\n        ")
    out: dict[str, tuple[str, ...]] = {}
    for cn, tn in cur.fetchall() or []:
        cols = _cons_columns_ordered(cur, str(cn))
        if cols:
            out[str(tn).upper()] = cols
    return out

def load_existing_fk_sigs(cur: Any) -> set[tuple[str, tuple[str, ...], str, tuple[str, ...]]]:
    """(child_tbl, child_cols, parent_tbl, parent_cols)"""
    cur.execute("\n        SELECT c.CONSTRAINT_NAME, c.TABLE_NAME CHILD_T, r.TABLE_NAME PARENT_T,\n               c.R_CONSTRAINT_NAME\n          FROM USER_CONSTRAINTS c\n          JOIN USER_CONSTRAINTS r ON r.CONSTRAINT_NAME = c.R_CONSTRAINT_NAME\n         WHERE c.CONSTRAINT_TYPE = 'R'\n        ")
    sigs: set[tuple[str, tuple[str, ...], str, tuple[str, ...]]] = set()
    for fk_name, ch, pa, rcons in cur.fetchall() or []:
        ccols = _cons_columns_ordered(cur, str(fk_name))
        pcols = _cons_columns_ordered(cur, str(rcons))
        sigs.add((str(ch).upper(), ccols, str(pa).upper(), pcols))
    return sigs

def unique_counts(cur: Any) -> dict[str, int]:
    cur.execute("\n        SELECT TABLE_NAME, COUNT(*) FROM USER_CONSTRAINTS\n         WHERE CONSTRAINT_TYPE = 'U' AND TABLE_NAME NOT LIKE 'BIN$%'\n         GROUP BY TABLE_NAME\n        ")
    return {str(r[0]).upper(): int(r[1]) for r in cur.fetchall() if r}

def fk_outgoing_counts(cur: Any) -> dict[str, int]:
    cur.execute("\n        SELECT TABLE_NAME, COUNT(*) FROM USER_CONSTRAINTS\n         WHERE CONSTRAINT_TYPE = 'R' AND TABLE_NAME NOT LIKE 'BIN$%'\n         GROUP BY TABLE_NAME\n        ")
    return {str(r[0]).upper(): int(r[1]) for r in cur.fetchall() if r}

def tab_columns_upper(cur: Any, table_upper: str) -> list[str]:
    cur.execute('\n        SELECT COLUMN_NAME FROM USER_TAB_COLUMNS WHERE TABLE_NAME = :t ORDER BY COLUMN_ID\n        ', {'t': table_upper})
    return [str(r[0]).upper() for r in cur.fetchall() if r and r[0]]

def audit_schema(cur: Any, *, suggest_fk: bool, max_fk_hints: int, include_sql_chunks: bool) -> tuple[list[str], list[str]]:
    """
    Build audit report lines and optional DDL hint chunks for an open USER cursor.
    Returns ``(report_lines, sql_chunks)``. ``sql_chunks`` is empty if ``include_sql_chunks`` is False.
    """
    sql_chunks: list[str] = []
    tables = _tables(cur)
    pk_map = load_pk_map(cur)
    fk_sigs = load_existing_fk_sigs(cur)
    unc = unique_counts(cur)
    fk_out = fk_outgoing_counts(cur)
    missing_pk = [t for t in tables if t not in pk_map]
    lines: list[str] = []
    lines.append('Tables in USER schema: %s' % len(tables))
    lines.append('Missing PRIMARY KEY constraint: %s' % len(missing_pk))
    for t in missing_pk[:250]:
        lines.append('  NO_PK\t%s' % t)
    if len(missing_pk) > 250:
        lines.append('  … %s more' % (len(missing_pk) - 250))
    if include_sql_chunks:
        sql_chunks.append('\n-- %s tables have no PRIMARY KEY\n' % len(missing_pk))
        for t in missing_pk[:150]:
            short = ''.join((ch for ch in t if ch.isalnum()))[:26] or 'T'
            sql_chunks.append('-- ALTER TABLE "%s" ADD CONSTRAINT "PK_%s" PRIMARY KEY (/* columns */);' % (t, short))
    lines.append('')
    lines.append('Tables with UNIQUE (non-PK): %s (others may be PK-only — normal)' % sum((1 for t in tables if unc.get(t, 0) > 0)))
    lines.append('Tables with at least one outgoing FK: %s' % sum((1 for t in tables if fk_out.get(t, 0) > 0)))
    lines.append('Total FK constraints (type R): %s' % len(fk_sigs))
    hints = 0
    if suggest_fk:
        lines.append('')
        lines.append('Heuristic NEW FK hints (child column name == parent single-column PK; not already constrained):')
        if include_sql_chunks:
            sql_chunks.append('\n-- Heuristic FOREIGN KEY stubs (often many false positives; validate data first)\n')
        for tbl in tables:
            if hints >= max_fk_hints:
                break
            cols = tab_columns_upper(cur, tbl)
            for col in cols:
                if hints >= max_fk_hints:
                    break
                for parent_tbl, pktup in pk_map.items():
                    if parent_tbl == tbl:
                        continue
                    if pktup != (col,):
                        continue
                    sig = (tbl, (col,), parent_tbl, (col,))
                    if sig in fk_sigs:
                        continue
                    cons = 'FK_%s_%s' % (tbl[:14], parent_tbl[:14])
                    cons = ''.join((ch for ch in cons if ch.isalnum() or ch == '_'))[:30]
                    lines.append('  +\t%s.%s REFERENCES %s(%s)' % (tbl, col, parent_tbl, col))
                    if include_sql_chunks:
                        sql_chunks.append('-- ALTER TABLE "%s" ADD CONSTRAINT "%s" FOREIGN KEY ("%s") REFERENCES "%s" ("%s");' % (tbl, cons, col, parent_tbl, col))
                    hints += 1
    return (lines, sql_chunks)

def run_audit_for_connection(user: str, password: str, dsn: str, *, suggest_fk: bool=True, max_fk_hints: int=400, include_sql_chunks: bool=True) -> tuple[list[str], list[str]]:
    """Connect with explicit credentials; returns ``(report_lines, sql_hint_lines)``."""
    from db.oracle_driver import oracle_connect
    conn = oracle_connect(user=user.strip(), password=password, dsn=dsn.strip())
    cur = conn.cursor()
    username_upper = user.strip().upper()
    try:
        lines_sql: list[str] = []
        if include_sql_chunks:
            lines_sql.extend(['-- Constraint audit DDL stubs — review & edit before running on Oracle', '-- Connected as %s\n' % username_upper])
        report, chunks = audit_schema(cur, suggest_fk=suggest_fk, max_fk_hints=max_fk_hints, include_sql_chunks=include_sql_chunks)
        if include_sql_chunks and chunks:
            lines_sql.extend(chunks)
        return (report, lines_sql if include_sql_chunks else [])
    finally:
        cur.close()
        conn.close()

def audit_main(args: argparse.Namespace) -> int:
    from db.oracle_driver import oracle_connect
    u, p, d = conn_params(args.profile, args.user, args.password, args.dsn)
    conn = oracle_connect(user=u, password=p, dsn=d)
    cur = conn.cursor()
    include_sql = bool(args.emit_sql)
    sql_chunks_hdr: list[str] = []
    if include_sql:
        sql_chunks_hdr.extend(['-- Constraint audit DDL stubs — review & edit before running on Oracle', '-- Connected as %s\n' % u.upper()])
    report, chunks = audit_schema(cur, suggest_fk=args.suggest_fk, max_fk_hints=args.max_fk_hints, include_sql_chunks=include_sql)
    lines_out = '\n'.join(report)
    print(lines_out)
    if args.emit_sql:
        outp = Path(args.emit_sql).resolve()
        outp.parent.mkdir(parents=True, exist_ok=True)
        full_sql = sql_chunks_hdr + chunks
        outp.write_text('\n'.join(full_sql) + '\n')
        print('\nWrote: %s' % outp)
    cur.close()
    conn.close()
    return 0

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description='Audit PK/UK/FK in Oracle USER schema.')
    ap.add_argument('--profile', choices=('db', 'auth', 'rfim'), default='db')
    ap.add_argument('--user', default=None)
    ap.add_argument('--password', default=None)
    ap.add_argument('--dsn', default=None)
    ap.add_argument('--emit-sql', default=None, metavar='PATH', help='Write commented DDL hints to file')
    ap.add_argument('--suggest-fk', action='store_true', help="Suggest FK when child column name matches another table's sole PK column")
    ap.add_argument('--max-fk-hints', type=int, default=800)
    return ap
if __name__ == '__main__':
    raise SystemExit(audit_main(build_parser().parse_args()))
