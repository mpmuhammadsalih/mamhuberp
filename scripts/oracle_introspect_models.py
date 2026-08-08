"""
Introspect an Oracle schema and emit Python: ``TABLE_BUNDLE``, ``COLS_BY_TABLE``, ``cols_for_table()``, ``*Cols`` classes.

Reads ``.env`` (python-dotenv) unless ``--user`` / ``--dsn`` override.

Examples::
    python scripts/oracle_introspect_models.py
    python scripts/oracle_introspect_models.py --profile auth
    python scripts/oracle_introspect_models.py --profile central
    python scripts/oracle_introspect_models.py --profile rfim
    python scripts/oracle_introspect_models.py --profile rfim --dry-run

    RFIM shortcut (same as env RFIM_*): ``rfim/rfim@192.168.1.225:1521/rgc``::

        python scripts/oracle_introspect_models.py --user rfim --password rfim --dsn 192.168.1.225:1521/rgc

Default output: ``oracle_schema.py`` (or ``oracle_schema_rfim.py`` for ``--profile rfim``).

Also emits (unless ``--no-constraints``): primary keys, unique constraints, foreign keys
(referenced table/columns via data dictionary views), check constraints (condition text may be
truncated), and indexes — as Python constants plus ``primary_key_columns`` / ``foreign_keys_*`` /
``indexes_on_table`` helpers.

**Split packages** (default for ``--profile rfim`` unless ``--no-split-tables``): one ``*.py`` per Oracle
table under ``addons/core/schema/generated/oracle_<profile>_tables/``, with a short
``oracle_schema_*.py`` that imports that package and attaches constraint blocks. Use
``--no-split-tables`` for a single monolithic file as before.
"""
from __future__ import annotations
import argparse
import keyword
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

def load_settings() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(PROJECT_ROOT / '.env')
    except ImportError:
        pass

def conn_params(profile: str, user_o: str | None, pwd_o: str | None, dsn_o: str | None) -> tuple[str, str, str]:
    load_settings()
    from config.settings import get_auth_db_config, get_central_report_config, get_db_config, get_rfim_schema_config

    def _cfg():
        if profile == 'db':
            return get_db_config()
        if profile == 'auth':
            return get_auth_db_config()
        if profile == 'central':
            return get_central_report_config()
        if profile == 'rfim':
            return get_rfim_schema_config()
        raise ValueError(f'Unknown profile: {profile}')
    if user_o and dsn_o:
        if pwd_o is not None and str(pwd_o).strip():
            return (user_o.strip(), str(pwd_o), dsn_o.strip())
        c = _cfg()
        p = str(c.get('password') or '')
        return (user_o.strip(), p, dsn_o.strip())
    c = _cfg()
    u, p, d = (c.get('user') or '', c.get('password') or '', c.get('dsn') or '')
    if not u or not d:
        raise SystemExit(f'No credentials for --profile={profile}. Set env (.env), e.g. DB_* / AUTH_DB_* / CENTRAL_REPORT_* / RFIM_* and matching DSN.')
    return (u.strip(), str(p).strip(), d.strip())
BIN_PREFIX = 'BIN$'
RE_BAD_CLASS_CHARS = re.compile('[^0-9A-Za-z_]')

def _table_base_name(table_upper: str) -> str:
    parts = [p for p in table_upper.split('_') if p]
    return ''.join((p.capitalize() for p in parts)) or 'Tbl'

def _unique_class(table_upper: str, taken: set[str]) -> str:
    base = _table_base_name(table_upper)
    name = base + 'Cols'
    k = 1
    while name in taken:
        k += 1
        name = f'{base}{k}Cols'
    taken.add(name)
    return name

def _col_attr(column_upper: str) -> str:
    raw = column_upper.upper().strip()
    if not raw:
        return 'BLANK_COL'
    if keyword.iskeyword(raw.lower()):
        return raw + '_'
    attr = RE_BAD_CLASS_CHARS.sub('_', raw)
    if not attr[0].isalpha():
        attr = 'C_' + attr
    attr = attr.upper()
    if keyword.iskeyword(attr.lower()):
        return attr + '_'
    return attr

def snake_key(table_upper: str) -> str:
    return '_'.join((p.lower() for p in table_upper.split('_') if p)) or table_upper.lower()
RE_MOD_SAFE = re.compile('[^a-z0-9_]')

def safe_split_module_basename(table_upper: str) -> str:
    s = snake_key(table_upper).lower()
    s = RE_MOD_SAFE.sub('_', s)
    s = re.sub('_+', '_', s).strip('_') or 'table'
    if s[0].isdigit() or keyword.iskeyword(s):
        s = 't_' + s
    return s

def _unique_mod_name(base: str, taken: set[str]) -> str:
    name = base
    k = 1
    while name in taken:
        k += 1
        name = f'{base}_{k}'
    taken.add(name)
    return name

def _cols_body_lines(tn: str, cols_list: list[tuple[int, str, str]], cls_name: str) -> list[str]:
    lines: list[str] = []
    dt_summary = ', '.join((str(dt) for _, _, dt in cols_list[:5]))
    extra = ', ...' if len(cols_list) > 5 else ''
    lines.append(f'class {cls_name}:')
    lines.append(f'    """Oracle table ``{tn}`` ({len(cols_list)} columns). Types: {dt_summary}{extra}"""')
    lines.append('')
    lines.append(f'    TABLE = {repr(tn)}')
    seen_attrs: set[str] = set()
    for _, cn, _dt in cols_list:
        oracle_col = cn.upper()
        base_attr = _col_attr(oracle_col)
        attr = base_attr
        n = 2
        while attr in seen_attrs:
            attr = f'{base_attr}_{n}'
            n += 1
        seen_attrs.add(attr)
        lines.append(f'    {attr} = {repr(oracle_col)}')
    return lines
    tables_to_cols: dict[str, list[tuple[int, str, str]]] = defaultdict(list)
    cur = cx.cursor()
    if owner:
        own = owner.strip().upper()
        cur.execute("\n            SELECT tc.TABLE_NAME,\n                   tc.COLUMN_ID,\n                   tc.COLUMN_NAME,\n                   NVL(tc.DATA_TYPE, '?') AS DT\n              FROM ALL_TAB_COLUMNS tc\n              JOIN ALL_OBJECTS ao\n                ON ao.OWNER = tc.OWNER AND ao.OBJECT_NAME = tc.TABLE_NAME\n             WHERE tc.OWNER = :own\n               AND ao.OBJECT_TYPE IN ('TABLE', 'TABLE PARTITION')\n               AND tc.TABLE_NAME NOT LIKE 'BIN$%'\n             ORDER BY tc.TABLE_NAME, tc.COLUMN_ID\n            ", {'own': own})
        for row in cur.fetchall():
            tn, cid, cn, dt = (row[0], row[1], row[2], row[3])
            if tn and str(tn).startswith(BIN_PREFIX):
                continue
            tables_to_cols[str(tn).upper()].append((int(cid or 0), str(cn).upper(), str(dt)))
    else:
        cur.execute("\n            SELECT utc.TABLE_NAME,\n                   utc.COLUMN_ID,\n                   utc.COLUMN_NAME,\n                   NVL(utc.DATA_TYPE, '?') AS DT\n              FROM USER_TAB_COLUMNS utc\n              JOIN USER_TABLES ut\n                ON ut.TABLE_NAME = utc.TABLE_NAME\n             WHERE utc.TABLE_NAME NOT LIKE 'BIN$%'\n             ORDER BY utc.TABLE_NAME, utc.COLUMN_ID\n            ")
        for row in cur.fetchall():
            tn, cid, cn, dt = (row[0], row[1], row[2], row[3])
            if tn and str(tn).startswith(BIN_PREFIX):
                continue
            tables_to_cols[str(tn).upper()].append((int(cid or 0), str(cn).upper(), str(dt)))
    cur.close()
    filtered: dict[str, list[tuple[int, str, str]]] = {}
    for tn in sorted(tables_to_cols.keys()):
        filtered[tn] = sorted(tables_to_cols[tn], key=lambda x: x[0])
    return (list(filtered.keys()), filtered)

def _norm(s: Any) -> str:
    if s is None:
        return ''
    return str(s).strip().upper()

def _fk_parent_detail(cx: Any, r_owner: str, r_constraint: str) -> tuple[str, tuple[str, ...]]:
    """Look up referenced table + column order via ``ALL_CONSTRAINTS`` / ``ALL_CONS_COLUMNS``."""
    ro = _norm(r_owner)
    rc = _norm(r_constraint)
    if not ro or not rc:
        return ('', ())
    cu = cx.cursor()
    cu.execute("\n        SELECT CONSTRAINT_TYPE, TABLE_NAME\n          FROM ALL_CONSTRAINTS\n         WHERE OWNER = :o AND CONSTRAINT_NAME = :n AND CONSTRAINT_TYPE IN ('P', 'U')\n        ", {'o': ro, 'n': rc})
    prow = cu.fetchone()
    if not prow:
        cu.close()
        return ('', ())
    pt = _norm(prow[1])
    cu.execute('\n        SELECT COLUMN_NAME, POSITION FROM ALL_CONS_COLUMNS\n         WHERE OWNER = :o AND CONSTRAINT_NAME = :n\n         ORDER BY POSITION\n        ', {'o': ro, 'n': rc})
    pcs: list[tuple[int, str]] = []
    for row in cu.fetchall():
        cn = _norm(row[0])
        po = int(row[1] or 0)
        if cn:
            pcs.append((po, cn))
    cu.close()
    cols = tuple((c for _, c in sorted(pcs, key=lambda x: x[0])))
    return (pt, cols)

def fetch_constraint_index_meta(cx: Any, owner: str | None, table_filter: set[str] | None) -> dict[str, Any]:
    """
    Read PK, UK, FK, check constraints and indexes from Oracle data dictionary.
    ``table_filter`` (upper table names): only emit metadata for these tables when set;
    FK rows where the **child** table is in the filter (``ref_table`` / parent columns may
    point outside the filtered set).
    """
    cur = cx.cursor()
    own = owner.strip().upper() if owner else None
    cur.execute('SELECT USER FROM DUAL')
    current_user_upper = _norm(cur.fetchone()[0])
    if own:
        cur.execute("\n            SELECT CONSTRAINT_NAME, CONSTRAINT_TYPE, TABLE_NAME,\n                   R_OWNER, R_CONSTRAINT_NAME, DELETE_RULE,\n                   SEARCH_CONDITION\n              FROM ALL_CONSTRAINTS\n             WHERE OWNER = :ow\n               AND CONSTRAINT_TYPE IN ('P', 'U', 'R', 'C')\n               AND TABLE_NAME NOT LIKE 'BIN$%'\n            ", {'ow': own})
    else:
        cur.execute("\n            SELECT CONSTRAINT_NAME, CONSTRAINT_TYPE, TABLE_NAME,\n                   R_OWNER, R_CONSTRAINT_NAME, DELETE_RULE,\n                   SEARCH_CONDITION\n              FROM USER_CONSTRAINTS\n             WHERE CONSTRAINT_TYPE IN ('P', 'U', 'R', 'C')\n               AND TABLE_NAME NOT LIKE 'BIN$%'\n            ")
    raw_cons: list[tuple[Any, ...]] = []
    for row in cur.fetchall():
        cname, ctype, tname = (row[0], row[1], row[2])
        r_own, r_cons, del_rule, search_cond = (row[3], row[4], row[5], row[6])
        raw_cons.append((_norm(cname), str(ctype or '').strip().upper(), _norm(tname), _norm(r_own) if r_own else '', _norm(r_cons) if r_cons else '', str(del_rule or '').strip().upper(), search_cond))
    if own:
        cur.execute('\n            SELECT CONSTRAINT_NAME, TABLE_NAME, COLUMN_NAME, POSITION\n              FROM ALL_CONS_COLUMNS\n             WHERE OWNER = :ow\n             ORDER BY CONSTRAINT_NAME, POSITION\n            ', {'ow': own})
    else:
        cur.execute('\n            SELECT CONSTRAINT_NAME, TABLE_NAME, COLUMN_NAME, POSITION\n              FROM USER_CONS_COLUMNS\n             ORDER BY CONSTRAINT_NAME, POSITION\n            ')
    cols_by_cons: dict[str, list[str]] = {}
    for row in cur.fetchall():
        cname, tname, col, pos = (row[0], row[1], row[2], row[3])
        ckey = _norm(cname)
        if not ckey:
            continue
        cn = _norm(col)
        if not cn:
            continue
        cols_by_cons.setdefault(ckey, []).append((int(pos or 0), cn))
    for ckey in cols_by_cons:
        cols_by_cons[ckey] = [c for _, c in sorted(cols_by_cons[ckey], key=lambda x: x[0])]
    if own:
        cur.execute("\n            SELECT i.INDEX_NAME, i.TABLE_NAME, i.UNIQUENESS, i.INDEX_TYPE,\n                   ic.COLUMN_NAME, ic.COLUMN_POSITION\n              FROM ALL_INDEXES i\n              JOIN ALL_IND_COLUMNS ic\n                ON ic.INDEX_OWNER = i.OWNER\n               AND ic.INDEX_NAME = i.INDEX_NAME\n             WHERE i.OWNER = :ow\n               AND i.TABLE_NAME NOT LIKE 'BIN$%'\n               AND ic.COLUMN_NAME IS NOT NULL\n             ORDER BY i.TABLE_NAME, i.INDEX_NAME, ic.COLUMN_POSITION\n            ", {'ow': own})
    else:
        cur.execute("\n            SELECT i.INDEX_NAME, i.TABLE_NAME, i.UNIQUENESS, i.INDEX_TYPE,\n                   ic.COLUMN_NAME, ic.COLUMN_POSITION\n              FROM USER_INDEXES i\n              JOIN USER_IND_COLUMNS ic\n                ON ic.INDEX_OWNER = i.OWNER\n               AND ic.INDEX_NAME = i.INDEX_NAME\n             WHERE i.TABLE_NAME NOT LIKE 'BIN$%'\n               AND ic.COLUMN_NAME IS NOT NULL\n             ORDER BY i.TABLE_NAME, i.INDEX_NAME, ic.COLUMN_POSITION\n            ")
    index_rows: list[tuple[str, str, str, str, str, int]] = []
    for row in cur.fetchall():
        iname, tname, uniq, itype, cname, cpos = (row[0], row[1], row[2], row[3], row[4], row[5])
        index_rows.append((_norm(iname), _norm(tname), str(uniq or '').strip().upper(), str(itype or '').strip().upper(), _norm(cname), int(cpos or 0)))
    cur.close()
    tf = {_norm(t) for t in table_filter} if table_filter else None

    def table_ok(t: str) -> bool:
        if not tf:
            return True
        return _norm(t) in tf
    primary_key: dict[str, tuple[str, ...]] = {}
    unique_out: list[dict[str, Any]] = []
    fk_out: list[dict[str, Any]] = []
    check_out: list[dict[str, Any]] = []

    def cons_key(cname: str) -> str:
        return _norm(cname)
    ref_table_cache: dict[str, str] = {}
    for tup in raw_cons:
        cname, ctype, tnam, _, _, _, _ = tup
        ck = cons_key(cname)
        if ctype in ('P', 'U'):
            ref_table_cache[ck] = tnam
    parent_resolved: dict[tuple[str, str], tuple[str, tuple[str, ...]]] = {}

    def resolve_fk_parent(r_own: str, r_cons: str) -> tuple[str, tuple[str, ...]]:
        rc = cons_key(r_cons) if r_cons else ''
        if not rc:
            return ('', ())
        ro = _norm(r_own) if r_own else own if own else current_user_upper
        key = (ro, rc)
        if key in parent_resolved:
            return parent_resolved[key]
        ptab, pcols = _fk_parent_detail(cx, ro, rc)
        parent_resolved[key] = (ptab, pcols)
        return (ptab, pcols)
    for tup in raw_cons:
        cname, ctype, tnam, r_own, r_cons, del_rule, search_cond = tup
        if not table_ok(tnam):
            continue
        ck = cons_key(cname)
        cols = tuple(cols_by_cons.get(ck, ()))
        if ctype == 'P' and cols:
            primary_key[tnam] = cols
        elif ctype == 'U' and cols:
            unique_out.append({'name': cname, 'table': tnam, 'columns': cols})
        elif ctype == 'C':
            cond = ''
            if search_cond is not None:
                cond = str(search_cond).strip()
                if len(cond) > 4000:
                    cond = cond[:3997] + '...'
            check_out.append({'name': cname, 'table': tnam, 'condition': cond})
        elif ctype == 'R':
            pch = cons_key(r_cons) if r_cons else ''
            pcols = tuple(cols_by_cons.get(pch, ()))
            ptab = ref_table_cache.get(pch, '')
            if (not pcols or not ptab) and r_cons:
                xtab, xcols = resolve_fk_parent(r_own, r_cons)
                if xtab:
                    ptab = xtab
                if xcols:
                    pcols = xcols
            if not cols:
                continue
            fk_out.append({'name': cname, 'table': tnam, 'columns': cols, 'ref_owner': _norm(r_own) or (own if own else current_user_upper), 'ref_table': ptab, 'ref_constraint': pch, 'ref_columns': pcols, 'delete_rule': del_rule or 'NO ACTION'})
    indexes_by_sig: dict[tuple[str, str], dict[str, Any]] = {}
    for iname, tnam, uniq, itype, cname, cpos in index_rows:
        if not table_ok(tnam):
            continue
        try:
            is_unique = uniq == 'UNIQUE'
        except Exception:
            is_unique = 'UNIQUE' in str(uniq).upper()
        sig = (tnam, iname)
        if sig not in indexes_by_sig:
            indexes_by_sig[sig] = {'name': iname, 'table': tnam, 'unique': is_unique, 'index_type': itype or 'NORMAL', 'columns': []}
        indexes_by_sig[sig]['columns'].append((cpos, cname))
    index_out: list[dict[str, Any]] = []
    for _sig, meta in sorted(indexes_by_sig.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        cols = [c for _, c in sorted(meta['columns'], key=lambda x: x[0])]
        meta = dict(meta)
        meta['columns'] = tuple(cols)
        index_out.append(meta)
    return {'primary_key': primary_key, 'unique_constraints': unique_out, 'foreign_keys': fk_out, 'check_constraints': check_out, 'indexes': index_out}

def split_package_dir_name(profile: str) -> str:
    return f'oracle_{profile}_tables'

def write_split_tables_package(tables: list[str], table_cols: dict[str, list[tuple[int, str, str]]], meta_comment: str, package_dir: Path) -> tuple[list[str], str]:
    """
    Write one ``.py`` per Oracle table under ``package_dir`` and an ``__init__.py`` that defines
    ``TABLE_BUNDLE``, ``COLS_BY_TABLE``, and ``cols_for_table``.

    Returns ``(all_cols_class_names, fq_import)`` e.g.
    ``(["CompanyprofileCols", ...], "addons.core.schema.generated.oracle_rfim_tables")``.
    """
    if package_dir.exists():
        shutil.rmtree(package_dir)
    package_dir.mkdir(parents=True)
    fq_import = f'addons.core.schema.generated.{package_dir.name}'
    snake_used: dict[str, int] = {}
    mod_taken: set[str] = set()
    taken_classes: set[str] = set()
    rows: list[tuple[str, str, str, str, list[tuple[int, str, str]]]] = []
    for tn in tables:
        cols_list = table_cols.get(tn) or []
        base_key = snake_key(tn)
        key = base_key
        n = snake_used.get(base_key, 0)
        snake_used[base_key] = n + 1
        if n:
            key = f'{base_key}_{n + 1}'
        cls = _unique_class(tn, taken_classes)
        mod_base = _unique_mod_name(safe_split_module_basename(tn), mod_taken)
        rows.append((key, mod_base, tn, cls, cols_list))
    import_lines: list[str] = []
    cols_by_lines: list[str] = []
    bun_lines: list[str] = []
    all_class_names: list[str] = []
    for bundle_key, mod_base, tn, cls, cols_list in rows:
        all_class_names.append(cls)
        import_lines.append(f'from .{mod_base} import {cls}')
        cols_by_lines.append(f'    {repr(tn.upper())}: {cls},')
        bun_lines.append(f'    {bundle_key}={repr(tn)},')
        tbl_lines: list[str] = ['"""AUTO-GENERATED by scripts/oracle_introspect_models.py — do not hand-edit."""', 'from __future__ import annotations', '', f'# {meta_comment}', '', *[f'{ln}' for ln in _cols_body_lines(tn, cols_list, cls)], '']
        (package_dir / f'{mod_base}.py').write_text('\n'.join(tbl_lines))
    init_lines: list[str] = ['"""AUTO-GENERATED by scripts/oracle_introspect_models.py — do not hand-edit."""', 'from __future__ import annotations', '', 'from types import SimpleNamespace', '', f'# {meta_comment}', '# Aggregated Oracle table/col classes (one module per logical table).', '', *import_lines, '', 'TABLE_BUNDLE = SimpleNamespace(', *bun_lines, ')', '', 'COLS_BY_TABLE: dict[str, type] = {', *cols_by_lines, '}', '', '', 'def cols_for_table(name: str):', '    """Resolved *Cols class for Oracle table ``name`` (any case); ``None`` if missing."""', '    k = (name or "").strip().upper()', '    return COLS_BY_TABLE.get(k)', '', '__all__ = [', '    "TABLE_BUNDLE",', '    "COLS_BY_TABLE",', '    "cols_for_table",']
    for c in sorted(all_class_names):
        init_lines.append(f'    {repr(c)},')
    init_lines.extend([']', ''])
    (package_dir / '__init__.py').write_text('\n'.join(init_lines))
    return (all_class_names, fq_import)

def _emit_constraint_block_lines(constraint_index_meta: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Return (lines, extra_export_names) for PK/FK/index helpers."""
    pk_map = constraint_index_meta.get('primary_key') or {}
    unique_list = constraint_index_meta.get('unique_constraints') or []
    fk_list = constraint_index_meta.get('foreign_keys') or []
    check_list = constraint_index_meta.get('check_constraints') or []
    idx_list = constraint_index_meta.get('indexes') or []
    lines: list[str] = ['# --- Constraints & indexes (USER_/ALL_* dictionary views) ---', '', 'PRIMARY_KEY_BY_TABLE: dict[str, tuple[str, ...]] = {']
    for k in sorted(pk_map.keys()):
        lines.append(f'    {repr(k)}: {repr(pk_map[k])},')
    lines.append('}')
    lines.append('')
    lines.append('UNIQUE_CONSTRAINTS: tuple[dict[str, object], ...] = (')
    for u in unique_list:
        lines.append(f'    {repr(u)},')
    lines.append(')')
    lines.append('')
    lines.append('FOREIGN_KEYS: tuple[dict[str, object], ...] = (')
    for fk in fk_list:
        lines.append(f'    {repr(fk)},')
    lines.append(')')
    lines.append('')
    lines.append('CHECK_CONSTRAINTS: tuple[dict[str, object], ...] = (')
    for ck in check_list:
        lines.append(f'    {repr(ck)},')
    lines.append(')')
    lines.append('')
    lines.append('INDEXES: tuple[dict[str, object], ...] = (')
    for ix in idx_list:
        lines.append(f'    {repr(ix)},')
    lines.append(')')
    lines.append('')
    lines.append('')
    lines.append('def primary_key_columns(name: str) -> tuple[str, ...] | None:')
    lines.append('    """Ordered PK column names for ``name``, or ``None``."""')
    lines.append('    k = (name or "").strip().upper()')
    lines.append('    return PRIMARY_KEY_BY_TABLE.get(k)')
    lines.append('')
    lines.append('def foreign_keys_from_table(name: str) -> tuple[dict[str, object], ...]:')
    lines.append('    """FK constraints where this table is the **child** (referencing) side."""')
    lines.append('    k = (name or "").strip().upper()')
    lines.append("    return tuple(fk for fk in FOREIGN_KEYS if fk.get('table') == k)")
    lines.append('')
    lines.append('def foreign_keys_to_table(name: str) -> tuple[dict[str, object], ...]:')
    lines.append('    """FK constraints referencing this table (parent / referenced side)."""')
    lines.append('    k = (name or "").strip().upper()')
    lines.append("    return tuple(fk for fk in FOREIGN_KEYS if fk.get('ref_table') == k)")
    lines.append('')
    lines.append('def indexes_on_table(name: str) -> tuple[dict[str, object], ...]:')
    lines.append('    """Indexes defined on ``name``."""')
    lines.append('    k = (name or "").strip().upper()')
    lines.append("    return tuple(ix for ix in INDEXES if ix.get('table') == k)")
    lines.append('')
    extra = ['PRIMARY_KEY_BY_TABLE', 'UNIQUE_CONSTRAINTS', 'FOREIGN_KEYS', 'CHECK_CONSTRAINTS', 'INDEXES', 'primary_key_columns', 'foreign_keys_from_table', 'foreign_keys_to_table', 'indexes_on_table']
    return (lines, extra)

def emit_python(tables: list[str], table_cols: dict[str, list[tuple[int, str, str]]], meta_comment: str, constraint_index_meta: dict[str, Any] | None=None, split_package_dir: Path | None=None) -> tuple[str, list[str]]:
    if split_package_dir is not None:
        all_classes, fq_import = write_split_tables_package(tables, table_cols, meta_comment, split_package_dir)
        pkg_name = split_package_dir.name
        lines: list[str] = ['"""AUTO-GENERATED by scripts/oracle_introspect_models.py — do not hand-edit."""', 'from __future__ import annotations', '', f'# {meta_comment}', '#', f'# Per-table ``*Cols`` classes live under ``addons/core/schema/generated/{pkg_name}/``.', "# App: set ORACLE_SCHEMA_MODULE to this file's basename without .py", '# (e.g. oracle_schema_rfim) so addons.core.schema.from_db can load TABLE_BUNDLE.', '#', f'import {fq_import} as _split_pkg', '', 'TABLE_BUNDLE = _split_pkg.TABLE_BUNDLE', 'COLS_BY_TABLE = _split_pkg.COLS_BY_TABLE', 'cols_for_table = _split_pkg.cols_for_table', '', '# Re-export *Cols for compatibility with imports from this module:', 'for _sym in _split_pkg.__all__:', '    if str(_sym).endswith("Cols"):', '        globals()[_sym] = getattr(_split_pkg, _sym)', '']
        all_exports_ordered: list[str] = ['TABLE_BUNDLE', 'COLS_BY_TABLE', 'cols_for_table', *sorted(all_classes)]
        if constraint_index_meta:
            c_lines, extra = _emit_constraint_block_lines(constraint_index_meta)
            lines.extend(c_lines)
            for x in extra:
                if x not in all_exports_ordered:
                    all_exports_ordered.append(x)
        lines.append('__all__ = [')
        for sym in all_exports_ordered:
            lines.append(f'    {repr(sym)},')
        lines.append(']')
        lines.append('')
        return ('\n'.join(lines), all_classes)
    snake_used: dict[str, int] = {}
    bun_body: list[str] = []
    for tn in tables:
        base_key = snake_key(tn)
        key = base_key
        n = snake_used.get(base_key, 0)
        snake_used[base_key] = n + 1
        if n:
            key = f'{base_key}_{n + 1}'
        bun_body.append(f'    {key}={repr(tn)},')
    lines = ['"""AUTO-GENERATED by scripts/oracle_introspect_models.py — do not hand-edit."""', 'from __future__ import annotations', '', 'from types import SimpleNamespace', '', f'# {meta_comment}', '#', "# App: set ORACLE_SCHEMA_MODULE in .env to this file's basename without .py", '# (e.g. oracle_schema_rfim) so addons.core.schema.from_db can import TABLE_BUNDLE.', '#']
    lines.extend(['TABLE_BUNDLE = SimpleNamespace('] + bun_body + [')', ''])
    taken_classes: set[str] = set()
    all_classes: list[str] = []
    for tn in tables:
        cols_list = table_cols.get(tn) or []
        cls = _unique_class(tn, taken_classes)
        all_classes.append(cls)
        lines.append('')
        lines.extend(_cols_body_lines(tn, cols_list, cls))
    lines.append('')
    lines.append('COLS_BY_TABLE: dict[str, type] = {')
    for tn, cn in zip(tables, all_classes):
        lines.append(f'    {repr(tn.upper())}: {cn},')
    lines.append('}')
    lines.append('')
    lines.append('')
    lines.append('def cols_for_table(name: str):')
    lines.append('    """Resolved *Cols class for Oracle table ``name`` (any case); ``None`` if missing."""')
    lines.append('    k = (name or "").strip().upper()')
    lines.append('    return COLS_BY_TABLE.get(k)')
    lines.append('')
    all_exports = ['TABLE_BUNDLE', 'COLS_BY_TABLE', 'cols_for_table']
    if constraint_index_meta:
        c_lines, extra = _emit_constraint_block_lines(constraint_index_meta)
        lines.extend(c_lines)
        all_exports.extend(extra)
    lines.append('__all__ = [')
    for sym in all_exports:
        lines.append(f'    {repr(sym)},')
    for c in all_classes:
        lines.append(f'    {repr(c)},')
    lines.append(']')
    lines.append('')
    return ('\n'.join(lines), all_classes)

def main() -> int:
    ap = argparse.ArgumentParser(description='Emit Python models from Oracle metadata.')
    ap.add_argument('--profile', choices=('db', 'auth', 'central', 'rfim'), default='db', help='Which .env block: db|auth|central|rfim (RFIM_* for schema copy)')
    ap.add_argument('--user', help='Oracle user override')
    ap.add_argument('--password', default='', help='Password (omit to use password from profile with --user/--dsn)')
    ap.add_argument('--dsn', help='DSN override (host:port/service)')
    ap.add_argument('--owner', help='Schema name for ALL_TAB_* introspection (default: USER_* for connected user)')
    ap.add_argument('--tables', help='Comma-separated Oracle table names to include only')
    ap.add_argument('--max-tables', type=int, default=0, help='Cap number of tables (0 = unlimited)')
    ap.add_argument('--out', default=None, help='Output .py (default: oracle_schema.py or oracle_schema_rfim.py for rfim)')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--no-constraints', action='store_true', help='Emit columns/TABLE_BUNDLE/*.Cols only (skip PK, FK, checks, indexes).')
    ap.add_argument('--split-tables', action='store_true', help='Emit one .py file per Oracle table under generated/oracle_<profile>_tables/.')
    ap.add_argument('--no-split-tables', action='store_true', help='Emit a single monolithic oracle_schema_*.py (disables RFIM default splitting).')
    args = ap.parse_args()
    gen_dir = PROJECT_ROOT / 'addons' / 'core' / 'schema' / 'generated'
    if not args.out:
        name = 'oracle_schema_rfim.py' if args.profile == 'rfim' else 'oracle_schema.py'
        args.out = str(gen_dir / name)
    try:
        from db.oracle_driver import oracle_connect
    except ImportError as e:
        print('oracledb required:', e, file=sys.stderr)
        return 1
    pwd_in = (args.password or '').strip()
    user, password, dsn = conn_params(args.profile, args.user.strip() if args.user else None, pwd_in if pwd_in else None, args.dsn.strip() if args.dsn else None)
    meta = f'user={user!r} profile={args.profile!r} owner={args.owner!r}'
    conn = oracle_connect(user=user, password=password, dsn=dsn)
    try:
        owner_arg = args.owner.strip() if args.owner else None
        tables, table_cols = fetch_schema(conn, owner_arg)
    finally:
        conn.close()
    if args.tables:
        want = {t.strip().upper() for t in args.tables.split(',') if t.strip()}
        tables = [t for t in tables if t in want]
        table_cols = {k: v for k, v in table_cols.items() if k in want}
        missing = want - set(tables)
        if missing:
            print('Warning: not found:', ', '.join(sorted(missing)), file=sys.stderr)
    if args.max_tables > 0:
        tables = tables[:args.max_tables]
        table_cols = {k: table_cols[k] for k in tables}
    print(f'Tables: {len(tables)}', file=sys.stderr)
    if args.dry_run:
        for t in tables[:50]:
            n = len(table_cols.get(t) or ())
            print(f'  {t} ({n} cols)')
        if len(tables) > 50:
            print(f'  ... +{len(tables) - 50} tables', file=sys.stderr)
        return 0
    cmeta: dict[str, Any] | None = None
    if not args.no_constraints:
        conn2 = oracle_connect(user=user, password=password, dsn=dsn)
        try:
            owner_arg = args.owner.strip() if args.owner else None
            cmeta = fetch_constraint_index_meta(conn2, owner_arg, set(tables))
        finally:
            conn2.close()
        if cmeta:
            print('Constraints: PK tables=%s unique=%s fk=%s check=%s indexes=%s' % (len(cmeta.get('primary_key') or {}), len(cmeta.get('unique_constraints') or ()), len(cmeta.get('foreign_keys') or ()), len(cmeta.get('check_constraints') or ()), len(cmeta.get('indexes') or ())), file=sys.stderr)
    use_split = False if args.no_split_tables else True if args.split_tables else args.profile == 'rfim'
    split_pkg_dir = gen_dir / split_package_dir_name(args.profile) if use_split else None
    text, class_names = emit_python(tables, table_cols, meta, cmeta, split_package_dir=split_pkg_dir)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text)
    print(f'Wrote {out_path} ({len(class_names)} Cols classes)', file=sys.stderr)
    if split_pkg_dir:
        print(f'Split package: {split_pkg_dir} ({len(tables)} table modules)', file=sys.stderr)
    return 0
if __name__ == '__main__':
    raise SystemExit(main())
