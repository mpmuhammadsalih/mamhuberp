"""
Apply heuristic **foreign key** constraints to an Oracle USER schema (optional ``NOVALIDATE``).

Companion to ``oracle_constraint_audit.py``. Does **not** add UNIQUE constraints (they fail on duplicate
historical rows without a cleanup pass).

Safety defaults::

    * Dry-run only unless you pass ``--execute`` and ``--i-confirm``.
    * By default, adds FK only when orphan check count is zero.
    * With ``--novalidate-orphans``: add ``NOVALIDATE`` so orphan rows remain until you fix data
      (constraint exists in catalogue but existing bad rows not checked).

Examples::

    # Print what would happen
    python scripts/oracle_apply_constraints.py --profile db

    # Apply safe FKs (no orphans)
    python scripts/oracle_apply_constraints.py --profile db --execute --i-confirm

    # Also add FK stubs when orphans exist (NOVALIDATE)
    python scripts/oracle_apply_constraints.py --profile db --execute --i-confirm --novalidate-orphans

    python scripts/oracle_apply_constraints.py --user scott --password tiger --dsn localhost:1521/orcdb \\
        --execute --i-confirm --max-fks 50
"""
from __future__ import annotations
import argparse
import re
import sys
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
RE_IDENT = re.compile('^[A-Z0-9_$#]+$')

def _assert_upper_ident(name: str, label: str) -> str:
    s = name.strip().upper()
    if not s or not RE_IDENT.match(s):
        raise ValueError(f'Unsafe {label}: {name!r}')
    return s

def _cons_columns_ordered(cur: Any, constraint_name: str) -> tuple[str, ...]:
    cur.execute('\n        SELECT COLUMN_NAME FROM USER_CONS_COLUMNS\n         WHERE CONSTRAINT_NAME = :c\n         ORDER BY POSITION\n        ', {'c': constraint_name.upper()})
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
    cur.execute("\n        SELECT c.TABLE_NAME CHILD_T, p.TABLE_NAME PARENT_T,\n               c.CONSTRAINT_NAME FK_NAME, c.R_CONSTRAINT_NAME R_NAME\n          FROM USER_CONSTRAINTS c\n          JOIN USER_CONSTRAINTS p ON p.CONSTRAINT_NAME = c.R_CONSTRAINT_NAME\n         WHERE c.CONSTRAINT_TYPE = 'R'\n        ")
    sigs: set[tuple[str, tuple[str, ...], str, tuple[str, ...]]] = set()
    for ch, pa, fk_name, rcons in cur.fetchall() or []:
        ccols = _cons_columns_ordered(cur, str(fk_name))
        pcols = _cons_columns_ordered(cur, str(rcons))
        sigs.add((str(ch).upper(), ccols, str(pa).upper(), pcols))
    return sigs

def _tables(cur: Any) -> list[str]:
    cur.execute("\n        SELECT TABLE_NAME FROM USER_TABLES\n         WHERE TABLE_NAME NOT LIKE 'BIN$%'\n           AND TABLE_NAME NOT LIKE 'DR$%'\n         ORDER BY TABLE_NAME\n        ")
    return [str(r[0]).upper() for r in cur.fetchall() if r and r[0]]

def tab_columns_upper(cur: Any, table_upper: str) -> list[str]:
    cur.execute('\n        SELECT COLUMN_NAME FROM USER_TAB_COLUMNS WHERE TABLE_NAME = :t ORDER BY COLUMN_ID\n        ', {'t': table_upper})
    return [str(r[0]).upper() for r in cur.fetchall() if r and r[0]]

def fk_constraint_exists(cur: Any, name_upper: str) -> bool:
    cur.execute('SELECT 1 FROM USER_CONSTRAINTS WHERE CONSTRAINT_NAME = :n', {'n': name_upper})
    return cur.fetchone() is not None

def orphan_count(cur: Any, child_tbl: str, col: str, parent_tbl: str) -> int:
    ct = _assert_upper_ident(child_tbl, 'child table')
    cc = _assert_upper_ident(col, 'column')
    pt = _assert_upper_ident(parent_tbl, 'parent table')
    sql = '\n    SELECT COUNT(*) FROM %(child)s ch\n     WHERE ch.%(col)s IS NOT NULL\n       AND NOT EXISTS (SELECT 1 FROM %(parent)s p WHERE p.%(col)s = ch.%(col)s)\n    ' % {'child': ct, 'col': cc, 'parent': pt}
    cur.execute(sql)
    row = cur.fetchone()
    return int(row[0]) if row and row[0] is not None else 0

def child_column_has_fk(cur: Any, child_tbl: str, col: str) -> bool:
    cur.execute("\n        SELECT 1 FROM USER_CONS_COLUMNS ucc\n        JOIN USER_CONSTRAINTS uc ON uc.CONSTRAINT_NAME = ucc.CONSTRAINT_NAME\n         AND uc.CONSTRAINT_TYPE = 'R'\n         AND uc.TABLE_NAME = ucc.TABLE_NAME\n         WHERE ucc.TABLE_NAME = :t AND ucc.COLUMN_NAME = :c\n          AND ROWNUM = 1\n        ", {'t': child_tbl.upper(), 'c': col.upper()})
    return cur.fetchone() is not None

def _read_tab_col_profile(cur: Any, table_upper: str, col_upper: str) -> tuple[Any, ...] | None:
    """Dictionary profile for FK type matching (ORA-02267 if child/parent mismatch)."""
    cur.execute('\n        SELECT DATA_TYPE, DATA_LENGTH, DATA_PRECISION, DATA_SCALE, CHAR_LENGTH, CHAR_USED\n          FROM USER_TAB_COLUMNS\n         WHERE TABLE_NAME = :t AND COLUMN_NAME = :c\n        ', {'t': table_upper, 'c': col_upper})
    row = cur.fetchone()
    if not row:
        return None
    dt, dl, dp, ds, cl, cu = row
    return (str(dt or '').strip().upper(), int(dl) if dl is not None else None, int(dp) if dp is not None else None, int(ds) if ds is not None else None, int(cl) if cl is not None else None, str(cu).strip().upper() if cu is not None else '')

def fk_column_profiles_match(cur: Any, child_tbl: str, col: str, parent_tbl: str, parent_col: str) -> bool:
    ct = _assert_upper_ident(child_tbl, 'child table')
    cc = _assert_upper_ident(col, 'column')
    pt = _assert_upper_ident(parent_tbl, 'parent table')
    pc = _assert_upper_ident(parent_col, 'parent column')
    a = _read_tab_col_profile(cur, ct, cc)
    b = _read_tab_col_profile(cur, pt, pc)
    if not a or not b:
        return False
    return a == b

def next_fk_name(cur: Any, child: str, parent: str) -> str:
    base = ('FK_' + child[:12] + '_' + parent[:12]).replace('__', '_')
    base = re.sub('[^A-Z0-9_]', '_', base)[:22] or 'FK'
    for i in range(0, 9999):
        candidate = ('%s_%s' % (base[:max(10, 30 - len(str(i)) - 1)], i))[:30]
        cu = candidate.upper().rstrip('_')
        if not fk_constraint_exists(cur, cu):
            return cu
    for j in range(1000000):
        cu = ('FKX_%s' % j)[:30]
        if not fk_constraint_exists(cur, cu):
            return cu
    return 'FK_FALLBACK_0'

def apply_heuristic_foreign_keys(conn: Any, cur: Any, *, execute: bool, i_confirm: bool, novalidate_orphans: bool, max_fks: int) -> tuple[dict[str, int], list[str]]:
    """Run heuristic FK audit/apply logic. Caller opens ``conn`` / ``cur``."""
    if execute and (not i_confirm):
        raise ValueError('execute=True requires i_confirm=True')
    lines: list[str] = []
    tables = _tables(cur)
    pk_map = load_pk_map(cur)
    fk_sigs = load_existing_fk_sigs(cur)
    stats: dict[str, int] = {'skipped_exists': 0, 'skipped_orphans': 0, 'skipped_incompatible': 0, 'dry_run_ok': 0, 'applied': 0, 'errors': 0}
    for tbl in tables:
        if stats['applied'] + stats['dry_run_ok'] >= max_fks:
            break
        tu = tbl
        cols = tab_columns_upper(cur, tu)
        if tu not in pk_map:
            pass
        for col in cols:
            if stats['applied'] + stats['dry_run_ok'] >= max_fks:
                break
            for parent_tbl, pktup in pk_map.items():
                if parent_tbl == tu:
                    continue
                if pktup != (col,):
                    continue
                sig = (tu, (col,), parent_tbl, (col,))
                if sig in fk_sigs:
                    stats['skipped_exists'] += 1
                    continue
                if child_column_has_fk(cur, tu, col):
                    stats['skipped_exists'] += 1
                    continue
                if not fk_column_profiles_match(cur, tu, col, parent_tbl, col):
                    stats['skipped_incompatible'] += 1
                    ca = _read_tab_col_profile(cur, tu.upper(), col.upper())
                    pb = _read_tab_col_profile(cur, parent_tbl.upper(), col.upper())
                    lines.append('[skip incompatible] %s.%s -> %s.%s | profile child=%s parent=%s (ORA-02267)' % (tu, col, parent_tbl, col, ca, pb))
                    continue
                n_or = orphan_count(cur, tu, col, parent_tbl)
                nv_suffix = ''
                if n_or > 0 and (not novalidate_orphans):
                    stats['skipped_orphans'] += 1
                    lines.append('[skip orphans=%s] %s.%s -> %s(%s)' % (n_or, tu, col, parent_tbl, col))
                    continue
                if n_or > 0:
                    nv_suffix = ' NOVALIDATE'
                cname = next_fk_name(cur, tu, parent_tbl)
                ddl_plain = 'ALTER TABLE %s ADD CONSTRAINT %s FOREIGN KEY (%s) REFERENCES %s (%s)%s' % (tu, cname, col, parent_tbl, col, nv_suffix)
                if not execute:
                    lines.append('[dry-run] ' + ddl_plain)
                    stats['dry_run_ok'] += 1
                else:
                    try:
                        cur.execute(ddl_plain)
                        conn.commit()
                        lines.append('[applied] ' + ddl_plain)
                        fk_sigs.add(sig)
                        stats['applied'] += 1
                    except Exception as ex:
                        conn.rollback()
                        msg = str(ex)
                        if 'ORA-02275' in msg or 'ORA-02261' in msg or '02264' in msg or ('already exists' in msg.lower()):
                            stats['skipped_exists'] += 1
                            lines.append('[skip dup/name] %s' % ddl_plain)
                        elif 'ORA-02267' in msg:
                            stats['skipped_incompatible'] += 1
                            lines.append('[skip ORA-02267] %s\n  %s' % (ddl_plain, msg))
                        else:
                            stats['errors'] += 1
                            lines.append('[error] %s\n  %s' % (ddl_plain, msg))
    lines.append('')
    lines.append('Done. skipped_exists=%s skipped_orphans=%s skipped_incompatible=%s dry_run_ok=%s applied=%s errors=%s' % (stats['skipped_exists'], stats['skipped_orphans'], stats['skipped_incompatible'], stats['dry_run_ok'], stats['applied'], stats['errors']))
    return (stats, lines)

def run_apply_for_connection(user: str, password: str, dsn: str, *, execute: bool, i_confirm: bool, novalidate_orphans: bool, max_fks: int) -> tuple[dict[str, int], list[str]]:
    """Connect with explicit credentials (e.g. New Company setup target schema)."""
    from db.oracle_driver import oracle_connect
    conn = oracle_connect(user=user.strip(), password=password, dsn=dsn.strip())
    cur = conn.cursor()
    try:
        return apply_heuristic_foreign_keys(conn, cur, execute=execute, i_confirm=i_confirm, novalidate_orphans=novalidate_orphans, max_fks=max_fks)
    finally:
        cur.close()
        conn.close()

def main() -> int:
    from db.oracle_driver import oracle_connect
    ap = argparse.ArgumentParser(description='Apply heuristic FK constraints (safe by default).')
    ap.add_argument('--profile', choices=('db', 'auth', 'rfim'), default='db')
    ap.add_argument('--user', default=None)
    ap.add_argument('--password', default=None)
    ap.add_argument('--dsn', default=None)
    ap.add_argument('--execute', action='store_true', help='Run DDL (otherwise dry-run)')
    ap.add_argument('--i-confirm', action='store_true', help='Required with --execute to acknowledge altering the database.')
    ap.add_argument('--novalidate-orphans', action='store_true', help='When orphan rows exist, add FK NOVALIDATE (otherwise skip those pairs).')
    ap.add_argument('--max-fks', type=int, default=2000)
    args = ap.parse_args()
    if args.execute and (not args.i_confirm):
        print('--execute requires --i-confirm', file=sys.stderr)
        return 2
    u, p, d = conn_params(args.profile, args.user, args.password, args.dsn)
    conn = oracle_connect(user=u, password=p, dsn=d)
    cur = conn.cursor()
    stats, lines = apply_heuristic_foreign_keys(conn, cur, execute=args.execute, i_confirm=args.i_confirm, novalidate_orphans=args.novalidate_orphans, max_fks=args.max_fks)
    for line in lines:
        print(line)
    cur.close()
    conn.close()
    return 0 if stats['errors'] == 0 else 1
if __name__ == '__main__':
    raise SystemExit(main())
