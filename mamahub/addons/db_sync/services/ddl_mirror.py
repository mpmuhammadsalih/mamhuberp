"""Oracle DDL fetch + optional apply (source → target schema remap)."""
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
from db.oracle_driver import cx_Oracle, oracle_connect

def connect(user: str, password: str, dsn: str) -> cx_Oracle.Connection:
    return oracle_connect(user=(user or '').strip(), password=password or '', dsn=(dsn or '').strip())

def read_metadata_lob(value: Any) -> str:
    if value is None:
        return ''
    if hasattr(value, 'read'):
        raw = value.read()
        if isinstance(raw, bytes):
            return raw.decode('utf-8', errors='replace')
        return str(raw)
    return str(value)

def run_metadata_setup(cur: Any) -> None:
    blocks = ["\n        BEGIN\n          DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'SQLTERMINATOR', TRUE);\n          DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'PRETTY', TRUE);\n        END;\n        ", "\n        BEGIN\n          DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'SEGMENT_ATTRIBUTES', FALSE);\n        EXCEPTION\n          WHEN OTHERS THEN NULL;\n        END;\n        ", "\n        BEGIN\n          DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'STORAGE', FALSE);\n        EXCEPTION\n          WHEN OTHERS THEN NULL;\n        END;\n        "]
    for plsql in blocks:
        try:
            cur.execute(plsql)
        except Exception:
            pass

def remap_owner(ddl: str, from_owner: str, to_owner: str) -> str:
    fo = from_owner.strip().upper()
    to = to_owner.strip().upper()
    if fo == to:
        return ddl
    return ddl.replace(f'"{fo}"', f'"{to}"').replace(f'"{fo.lower()}"', f'"{to}"')

def _table_names(cur: Any) -> List[str]:
    cur.execute("\n        SELECT TABLE_NAME FROM USER_TABLES\n         WHERE TABLE_NAME NOT LIKE 'BIN$%'\n           AND TABLE_NAME NOT LIKE 'DR$%'\n         ORDER BY TABLE_NAME\n        ")
    return [str(r[0]) for r in cur.fetchall() if r and r[0]]

def _view_names(cur: Any) -> List[str]:
    cur.execute("\n        SELECT VIEW_NAME FROM USER_VIEWS\n         WHERE VIEW_NAME NOT LIKE 'BIN$%'\n           AND VIEW_NAME NOT LIKE 'DR$%'\n         ORDER BY VIEW_NAME\n        ")
    return [str(r[0]) for r in cur.fetchall() if r and r[0]]

def list_schema_objects(source_user: str, source_password: str, source_dsn: str) -> Tuple[List[str], List[str]]:
    """Return (table_names, view_names) for the logged-in source schema (``USER_*``)."""
    src = connect(source_user, source_password, source_dsn)
    cur = src.cursor()
    try:
        return (_table_names(cur), _view_names(cur))
    finally:
        try:
            cur.close()
        except Exception:
            pass
        try:
            src.close()
        except Exception:
            pass

def _existing_object_names_upper(cur: Any, kind: str) -> set[str]:
    """Names present in target schema (USER_*)."""
    if kind == 'TABLE':
        cur.execute("\n            SELECT TABLE_NAME FROM USER_TABLES\n             WHERE TABLE_NAME NOT LIKE 'BIN$%'\n            ")
    else:
        cur.execute("\n            SELECT VIEW_NAME FROM USER_VIEWS\n             WHERE VIEW_NAME NOT LIKE 'BIN$%'\n            ")
    return {str(r[0]).upper() for r in cur.fetchall() if r and r[0]}

def _fetch_tab_column_meta(cur: Any, table_upper: str) -> Dict[str, Dict[str, Any]]:
    """COLUMN_NAME (upper) -> metadata row dict for ``USER_TAB_COLUMNS``."""
    cur.execute('\n        SELECT COLUMN_NAME, DATA_TYPE, DATA_LENGTH, CHAR_LENGTH,\n               DATA_PRECISION, DATA_SCALE, NULLABLE\n          FROM USER_TAB_COLUMNS\n         WHERE TABLE_NAME = :t\n         ORDER BY COLUMN_ID\n        ', {'t': table_upper.upper()})
    cols: Dict[str, Dict[str, Any]] = {}
    for row in cur.fetchall() or []:
        cn = str(row[0] or '').strip().upper()
        if not cn:
            continue
        cols[cn] = {'COLUMN_NAME': cn, 'DATA_TYPE': str(row[1] or '').strip().upper(), 'DATA_LENGTH': row[2], 'CHAR_LENGTH': row[3], 'DATA_PRECISION': row[4], 'DATA_SCALE': row[5], 'NULLABLE': str(row[6] or 'Y').strip().upper()}
    return cols

def _oracle_column_type_sql(meta: Dict[str, Any]) -> str:
    """Build a single-column type fragment for ``ALTER TABLE ... ADD``."""
    dt = (meta.get('DATA_TYPE') or '').upper()
    prec = meta.get('DATA_PRECISION')
    scale = meta.get('DATA_SCALE')
    chlen = meta.get('CHAR_LENGTH')
    dlen = meta.get('DATA_LENGTH')
    if dt in ('VARCHAR2', 'CHAR', 'NVARCHAR2', 'NCHAR'):
        ln = chlen if chlen is not None else dlen
        if ln is None:
            ln = 4000
        return f'{dt}({int(ln)})'
    if dt == 'NUMBER':
        if prec is None:
            return 'NUMBER'
        if scale is None or int(scale or 0) == 0:
            return f'NUMBER({int(prec)})'
        return f'NUMBER({int(prec)},{int(scale)})'
    if dt == 'FLOAT':
        if prec is not None:
            return f'FLOAT({int(prec)})'
        return 'FLOAT'
    if dt.startswith('TIMESTAMP') or dt.startswith('INTERVAL'):
        return (meta.get('DATA_TYPE') or 'TIMESTAMP(6)').strip()
    if dt in ('CLOB', 'BLOB', 'NCLOB', 'LONG', 'DATE', 'RAW'):
        if dt == 'RAW' and dlen is not None:
            return f'RAW({int(dlen)})'
        return dt
    if dt == 'XMLTYPE':
        return 'XMLTYPE'
    return dt or 'VARCHAR2(4000)'

def _sync_missing_table_columns(scur: Any, tcur: Any, table_name: str, owner_tgt: str) -> Tuple[int, List[str]]:
    """
    For a table that already exists on target: ``ALTER TABLE ... ADD`` only columns
    that exist on source but not on target. Returns (statements_executed, log_lines).
    """
    t_u = table_name.upper()
    src_cols = _fetch_tab_column_meta(scur, t_u)
    tgt_cols = _fetch_tab_column_meta(tcur, t_u)
    missing = [src_cols[c] for c in src_cols if c not in tgt_cols]
    log: List[str] = []
    n = 0
    for meta in missing:
        cname = meta['COLUMN_NAME']
        typ = _oracle_column_type_sql(meta)
        nullable = meta.get('NULLABLE') == 'Y'
        if not nullable:
            log.append(f'  skip column {cname}: NOT NULL on source — add manually or with DEFAULT')
            continue
        stmt = f'ALTER TABLE "{owner_tgt}"."{t_u}" ADD ("{cname}" {typ} NULL)'
        try:
            tcur.execute(stmt)
            n += 1
            log.append(f'  ADD {cname} {typ}')
        except Exception as ex:
            log.append(f'  ADD {cname} FAILED: {ex}')
            raise
    return (n, log)

def _preview_missing_table_columns(scur: Any, tcur: Any, table_name: str) -> Tuple[List[str], List[str]]:
    """Non-executing preview: lines that would be ADD, and NOT NULL skip notes."""
    t_u = table_name.upper()
    src_cols = _fetch_tab_column_meta(scur, t_u)
    tgt_cols = _fetch_tab_column_meta(tcur, t_u)
    lines: List[str] = []
    notes: List[str] = []
    for c in src_cols:
        if c in tgt_cols:
            continue
        meta = src_cols[c]
        typ = _oracle_column_type_sql(meta)
        if meta.get('NULLABLE') == 'Y':
            lines.append(f'    would ADD {c} {typ} NULL')
        else:
            notes.append(f'    NOT NULL column {c} — add manually or with DEFAULT')
    return (lines, notes)

def fetch_ddls(cur: Any, owner: str, kind: str, only_names: Optional[List[str]]=None) -> Tuple[List[str], Dict[str, str]]:
    if only_names is not None:
        if len(only_names) == 0:
            return ([], {})
        names = list(only_names)
    else:
        names = _table_names(cur) if kind == 'TABLE' else _view_names(cur)
    out: Dict[str, str] = {}
    objs: List[str] = []
    obj_type = 'TABLE' if kind == 'TABLE' else 'VIEW'
    for nm in names:
        try:
            cur.execute('\n                SELECT DBMS_METADATA.GET_DDL(object_type => :oty,\n                                             name           => :oname,\n                                             schema         => :owner)\n                  FROM DUAL\n                ', {'oty': obj_type, 'oname': nm, 'owner': owner})
            row = cur.fetchone()
            if row:
                ddl = read_metadata_lob(row[0]).strip()
                out[nm] = ddl if ddl else f'-- empty DDL {obj_type} {nm}'
                objs.append(nm)
        except Exception as ex:
            objs.append(nm)
            out[nm] = f'-- ERROR GET_DDL {obj_type} {nm}: {ex}'
    return (objs, out)

def run_sync_tables(source_user: str, source_password: str, source_dsn: str, target_user: str, target_password: str, target_dsn: str, *, dry_run: bool, continue_on_error: bool, max_objects: int=0, only_names: Optional[List[str]]=None) -> Dict[str, Any]:
    return _run_sync(source_user, source_password, source_dsn, target_user, target_password, target_dsn, kind='TABLE', dry_run=dry_run, continue_on_error=continue_on_error, max_objects=max_objects, only_names=only_names)

def run_sync_views(source_user: str, source_password: str, source_dsn: str, target_user: str, target_password: str, target_dsn: str, *, dry_run: bool, continue_on_error: bool, max_objects: int=0, only_names: Optional[List[str]]=None) -> Dict[str, Any]:
    return _run_sync(source_user, source_password, source_dsn, target_user, target_password, target_dsn, kind='VIEW', dry_run=dry_run, continue_on_error=continue_on_error, max_objects=max_objects, only_names=only_names)

def run_structure_sync(source_user: str, source_password: str, source_dsn: str, target_user: str, target_password: str, target_dsn: str, *, include_tables: bool, include_views: bool, dry_run: bool, continue_on_error: bool, max_objects: int=0, only_table_names: Optional[List[str]]=None, only_view_names: Optional[List[str]]=None) -> Dict[str, Any]:
    kinds: List[str] = []
    if include_tables:
        kinds.append('TABLE')
    if include_views:
        kinds.append('VIEW')
    if not kinds:
        return {'ok': False, 'kind': '', 'dry_run': dry_run, 'messages': [], 'fetched': 0, 'executed_ok': 0, 'errors': ['Select at least one: Tables and/or Views.'], 'stopped_at': None, 'skipped_existing': 0, 'columns_added': 0}
    merged: Dict[str, Any] = {'ok': True, 'kind': '+'.join(kinds), 'dry_run': dry_run, 'messages': [], 'fetched': 0, 'executed_ok': 0, 'errors': [], 'stopped_at': None, 'skipped_existing': 0, 'columns_added': 0}
    for k in kinds:
        only_n = only_table_names if k == 'TABLE' else only_view_names
        r = _run_sync(source_user, source_password, source_dsn, target_user, target_password, target_dsn, kind=k, dry_run=dry_run, continue_on_error=continue_on_error, max_objects=max_objects, only_names=only_n)
        label = 'TABLE' if k == 'TABLE' else 'VIEW'
        merged['messages'].append(f'=== {label}s ===')
        merged['messages'].extend(r.get('messages') or [])
        merged['fetched'] += int(r.get('fetched') or 0)
        merged['executed_ok'] += int(r.get('executed_ok') or 0)
        merged['skipped_existing'] += int(r.get('skipped_existing') or 0)
        merged['columns_added'] += int(r.get('columns_added') or 0)
        merged['errors'].extend(r.get('errors') or [])
        if not r.get('ok', True):
            merged['ok'] = False
            if r.get('stopped_at'):
                merged['stopped_at'] = r['stopped_at']
            if not continue_on_error:
                break
    if dry_run:
        merged['ok'] = True
    return merged

def _run_sync(source_user: str, source_password: str, source_dsn: str, target_user: str, target_password: str, target_dsn: str, *, kind: str, dry_run: bool, continue_on_error: bool, max_objects: int=0, only_names: Optional[List[str]]=None) -> Dict[str, Any]:
    result: Dict[str, Any] = {'ok': True, 'kind': kind, 'dry_run': dry_run, 'messages': [], 'fetched': 0, 'executed_ok': 0, 'errors': [], 'stopped_at': None, 'skipped_existing': 0, 'columns_added': 0}
    src = connect(source_user, source_password, source_dsn)
    scur = src.cursor()
    tgt: Optional[cx_Oracle.Connection] = None
    tcur: Any = None
    try:
        run_metadata_setup(scur)
        scur.execute('SELECT USER FROM DUAL')
        src_owner = str(scur.fetchone()[0]).strip().upper()
        objs, ddl_map = fetch_ddls(scur, src_owner, kind, only_names=only_names)
        result['fetched'] = len(objs)
        if max_objects > 0:
            objs = objs[:max_objects]
        tgt_preview = (target_user or '').strip().upper()
        tgto = tgt_preview or src_owner
        tgt_existing: Optional[set[str]] = None
        can_target_preview = dry_run and (target_password or '').strip() and (target_dsn or '').strip() and tgt_preview
        if not dry_run:
            tgt = connect(target_user, target_password, target_dsn)
            tcur = tgt.cursor()
            tcur.execute('SELECT USER FROM DUAL')
            tgto = str(tcur.fetchone()[0]).strip().upper()
            tgt_existing = _existing_object_names_upper(tcur, kind)
        elif can_target_preview:
            try:
                tgt = connect(target_user, target_password, target_dsn)
                tcur = tgt.cursor()
                tcur.execute('SELECT USER FROM DUAL')
                tgto = str(tcur.fetchone()[0]).strip().upper()
                tgt_existing = _existing_object_names_upper(tcur, kind)
            except Exception as ex:
                result['messages'].append(f'[preview] target connect failed — sizes only: {ex}')
                can_target_preview = False
        elif dry_run and tgt_preview:
            tgto = tgt_preview
        for nm in objs:
            raw = ddl_map.get(nm, '')
            mapped = remap_owner(raw, src_owner, tgto)
            nm_u = (nm or '').strip().upper()
            if raw.strip().startswith('-- ERROR'):
                result['errors'].append(f'{nm}: {raw[:500]}')
                if not continue_on_error:
                    result['stopped_at'] = nm
                    result['ok'] = False
                    break
                continue
            if dry_run:
                if tgt_existing is not None and kind == 'VIEW' and (nm_u in tgt_existing):
                    result['skipped_existing'] += 1
                    result['messages'].append(f'[preview] VIEW {nm}: skip (already on target)')
                elif tgt_existing is not None and kind == 'TABLE' and (nm_u in tgt_existing):
                    add_lines, nn_notes = _preview_missing_table_columns(scur, tcur, nm)
                    if add_lines or nn_notes:
                        result['messages'].append(f'[preview] TABLE {nm}: exists — column sync')
                        result['messages'].extend(add_lines)
                        result['messages'].extend(nn_notes)
                    else:
                        result['skipped_existing'] += 1
                        result['messages'].append(f'[preview] TABLE {nm}: exists — no missing columns')
                elif tgt_existing is not None and kind == 'TABLE':
                    result['messages'].append(f'[preview] TABLE {nm}: would CREATE ({len(mapped)} chars, remap → {tgto})')
                elif tgt_existing is not None and kind == 'VIEW':
                    result['messages'].append(f'[preview] VIEW {nm}: would CREATE ({len(mapped)} chars, remap → {tgto})')
                else:
                    result['messages'].append(f'[preview] {kind} {nm}: {len(mapped)} chars (remap → {tgto}; add target user+password+DSN for skip / column diff)')
                continue
            assert tcur is not None and tgt_existing is not None
            if kind == 'VIEW' and nm_u in tgt_existing:
                result['skipped_existing'] += 1
                result['messages'].append(f'VIEW {nm}: skip (already on target)')
                continue
            if kind == 'TABLE' and nm_u in tgt_existing:
                try:
                    n_add, log_lines = _sync_missing_table_columns(scur, tcur, nm, tgto)
                    result['columns_added'] += n_add
                    if log_lines:
                        result['messages'].append(f'TABLE {nm}: existing — column sync')
                        result['messages'].extend(log_lines)
                    else:
                        result['skipped_existing'] += 1
                        result['messages'].append(f'TABLE {nm}: exists — no nullable columns to add')
                except Exception as ex:
                    result['errors'].append(f'{nm} (columns): {ex}')
                    result['ok'] = False
                    if not continue_on_error:
                        result['stopped_at'] = nm
                        break
                continue
            stmt = mapped.strip().rstrip(';')
            if stmt.startswith('--'):
                continue
            try:
                tcur.execute(stmt)
                result['executed_ok'] += 1
            except Exception as ex:
                result['errors'].append(f'{nm}: {ex}')
                result['ok'] = False
                if not continue_on_error:
                    result['stopped_at'] = nm
                    break
        if dry_run:
            result['ok'] = True
        elif result['errors'] and (not continue_on_error) and result.get('stopped_at'):
            result['ok'] = False
    finally:
        scur.close()
        src.close()
        if tcur:
            try:
                tcur.close()
            except Exception:
                pass
        if tgt:
            try:
                tgt.close()
            except Exception:
                pass
    return result
