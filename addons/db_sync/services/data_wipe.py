"""Generate and optionally run Oracle TRUNCATE scripts for an empty-schema / new-company scenario."""
from __future__ import annotations
from typing import Any, Dict, List, Sequence, Tuple
from addons.db_sync.services.ddl_mirror import connect
DEFAULT_PROTECTED_TABLES = frozenset({'LOGIN_USERS', 'ROLES', 'ROLE_PERMISSIONS', 'TENANT_DATABASES'})

# Masters kept when clearing business data for a new company (fixed — no UI table picker).
NEW_COMPANY_DEFAULT_MASTER_TABLES: Tuple[str, ...] = (
    'CATEGORY',
    'CHART_OF_ACCOUNTS',
    'COMPANYPROFILE',
    'COUNTER',
    'POS_TENDER_TYPE',
    'CUSTOMER',
    'EMPLOYEE',
    'ITEMALTERNATEUOMMAP',
    'ITEMMASTER',
    'LOCATIONMASTER',
    'SUPPLIER',
    'UNITOFMEASUREMENT',
    'WAREHOUSE_MASTER',
)


def new_company_default_extra_protected_names() -> List[str]:
    """Uppercase table names always skipped during new-company data clear."""
    return sorted({str(n or '').strip().upper() for n in NEW_COMPANY_DEFAULT_MASTER_TABLES if str(n or '').strip()})


def new_company_default_protected_display_csv() -> str:
    return ', '.join(new_company_default_extra_protected_names())

# Reserved bill / doc numbers — often kept during wipe (see POS & counter setup group).
DOCUMENT_COUNTER_TABLES: Tuple[str, ...] = ('BILLNOTABLE', 'BILLNOTIME')

# Explicit sequence → (table, id column) when name does not match ``{TABLE}_SEQ`` + ``{TABLE}_ID``.
SEQUENCE_PK_HINTS: Dict[str, Tuple[str, str]] = {
    'GL_VOUCHER_DTL_SEQ': ('GL_VOUCHER_DTL', 'LINE_ID'),
    'WAREHOUSE_MASTER_SEQ': ('WAREHOUSE_MASTER', 'WAREHOUSE_ID'),
    'WAREHOUSE_STORAGE_SEQ': ('WAREHOUSE_STORAGE', 'STORAGE_ID'),
    'ITEM_LOT_SEQ': ('ITEM_LOT', 'LOT_ID'),
    'ITEM_LOT_MOVEMENT_SEQ': ('ITEM_LOT_MOVEMENT', 'MOV_ID'),
    'STOCK_BIN_TRANSFER_SEQ': ('STOCK_BIN_TRANSFER_HDR', 'TRANSFER_ID'),
    'AP_SUPPLIER_PAYMENT_ALLOC_SEQ': ('AP_SUPPLIER_PAYMENT_ALLOC', 'ALLOC_ID'),
    'AR_CUSTOMER_PAYMENT_ALLOC_SEQ': ('AR_CUSTOMER_PAYMENT_ALLOC', 'ALLOC_ID'),
    'PURCHASE_APPROVAL_LOG_SEQ': ('PURCHASE_APPROVAL_LOG', 'LOG_ID'),
    'TBLPAYMENTFOLLOWUP_SEQ': ('TBLPAYMENTFOLLOWUP', 'SLNO'),
    'PDCCHECK_SEQ': ('PDCCHECK', 'ID'),
    'PDCCHECK_AUDIT_SEQ': ('PDCCHECK_AUDIT', 'AUDIT_ID'),
    'POS_SETTLEMENT_DRAFT_SEQ': ('POS_SETTLEMENT_DRAFT_HDR', 'DRAFT_ID'),
    'POS_SAVE_QUEUE_SEQ': ('POS_SAVE_QUEUE', 'JOB_ID'),
    'ITEMJOURNAL_SEQ': ('ITEMJOURNAL', 'ITEMJOURNAL_ID'),
}

_SEQUENCE_ID_COLUMN_CANDIDATES: Tuple[str, ...] = (
    'ID', 'LINE_ID', 'ALLOC_ID', 'LOG_ID', 'AUDIT_ID', 'SLNO', 'DRAFT_ID', 'JOB_ID',
    'MOV_ID', 'MOVEMENT_ID', 'TRANSFER_ID', 'LOT_ID', 'WAREHOUSE_ID', 'STORAGE_ID',
    'ITEMJOURNAL_ID', 'QUEUE_ID',
)

# Nexus / RGC Oracle table names (same as db.py + oracle_schema_rfim TABLE_BUNDLE).
# Fetch resolves each name against USER_TABLES and returns the exact dictionary spelling.
SUGGESTED_PROTECTED_TABLE_GROUPS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ('Company & branches', (
        'COMPANYPROFILE',
        'LOCATIONMASTER',
        'FISCAL_YEAR',
        'INITIALSETTINGS',
        'TBLLOCATION',
    )),
    ('Chart of accounts & GL dimensions', (
        'CHART_OF_ACCOUNTS',
        'GL_DIMENSION_VALUE',
        'GL_ACCOUNT_DIMENSION_RULE',
    )),
    ('Items, category & pricing', (
        'ITEMMASTER',
        'ITEMALTERNATEUOMMAP',
        'CATEGORY',
        'UNITOFMEASUREMENT',
        'STOCKMASTER',
        'SYSTEMCONFIG',
        'PROMOTION',
        'TBLPROMOTIONS',
        'TBLPRICECHANGE',
    )),
    ('Customer, supplier & staff', (
        'CUSTOMER',
        'CUSTOMERLIMIT',
        'TBLCUSTOMERCATEGORY',
        'SUPPLIER',
        'TBLSUPPLIERTYPE',
        'EMPLOYEE',
        'SALESMAN',
        'TBLROUTES',
        'TBLROUTESMAIN',
    )),
    ('POS & counter setup', (
        'COUNTER',
        'POS_TENDER_TYPE',
        'POS_SETTLEMENT_ACCOUNT_CONFIG',
        'SHIFT',
        'SHIFT2',
        'BILLNOTABLE',
        'MACHINECOUNTERMAP',
    )),
    ('Warehouse, bins & lots', (
        'WAREHOUSE_STORAGE',
        'WAREHOUSE_MASTER',
        'WAREHOUSE_STOCK',
        'BIN_STOCK',
        'ITEM_LOT',
        'ITEM_LOT_BALANCE',
        'ITEM_LOT_BIN',
        'ITEM_LOT_MOVEMENT',
        'STOCK_BIN_TRANSFER_HDR',
        'STOCK_BIN_TRANSFER_DTL',
        'STKTRFAPPROVALSETUP',
    )),
    ('Other setup masters', (
        'CURRENCY',
        'PDCCHECK',
        'PRODUCTIONMASTER',
        'PURCHASESALES',
        'ROLEMENUMAP',
        'MENU',
        'MENUROLE',
    )),
)


def all_suggested_protect_names() -> List[str]:
    names: set[str] = set()
    for _label, group in SUGGESTED_PROTECTED_TABLE_GROUPS:
        for n in group:
            u = str(n or '').strip()
            if u:
                names.add(u)
    return sorted(names, key=lambda x: x.upper())


def default_suggested_protected_csv() -> str:
    return ', '.join(all_suggested_protect_names())


def _schema_table_map(cur: Any) -> Dict[str, str]:
    """Map uppercase name -> exact TABLE_NAME from USER_TABLES."""
    out: Dict[str, str] = {}
    for t in list_user_tables(cur):
        s = str(t or '').strip()
        if s:
            out[s.upper()] = s
    return out


def _resolve_tables_in_schema(candidates: Sequence[str], schema_map: Dict[str, str]) -> List[str]:
    found: List[str] = []
    seen: set[str] = set()
    for name in candidates:
        key = str(name or '').strip().upper()
        if not key or key in seen:
            continue
        actual = schema_map.get(key)
        if actual:
            found.append(actual)
            seen.add(key)
    return sorted(found, key=lambda x: x.upper())

def list_user_tables(cur: Any) -> List[str]:
    cur.execute("\n        SELECT TABLE_NAME FROM USER_TABLES\n         WHERE TABLE_NAME NOT LIKE 'BIN$%'\n           AND TABLE_NAME NOT LIKE 'DR$%'\n         ORDER BY TABLE_NAME\n        ")
    return [str(r[0]) for r in cur.fetchall() if r and r[0]]

def fetch_enabled_foreign_keys(cur: Any) -> List[Tuple[str, str]]:
    """(table_name, constraint_name) for enabled referential constraints in this schema."""
    cur.execute("\n        SELECT TABLE_NAME, CONSTRAINT_NAME\n          FROM USER_CONSTRAINTS\n         WHERE CONSTRAINT_TYPE = 'R'\n           AND STATUS = 'ENABLED'\n         ORDER BY TABLE_NAME, CONSTRAINT_NAME\n        ")
    return [(str(r[0]), str(r[1])) for r in cur.fetchall() if r and r[0] and r[1]]

def quoted_ident(name: str) -> str:
    """Quote Oracle identifier preserving case from data dictionary."""
    n = (name or '').strip()
    if not n:
        return '""'
    return '"' + n.replace('"', '""') + '"'

_ZERO_STOCK_TABLES: Tuple[str, ...] = ('ITEMMASTER', 'ITEMALTERNATEUOMMAP')
_ZERO_STOCK_COLUMN_CANDIDATES: Tuple[str, ...] = (
    'CURRENTSTOCK',
    'CURRENT_STOCK',
    'STOCK',
    'QTY',
    'QUANTITY',
    'BALANCE',
    'TOTALSTOCK',
    'STOCKQTY',
)
_ZERO_CUSTOMER_TABLES: Tuple[str, ...] = ('CUSTOMER',)
_ZERO_CREDIT_COLUMN_CANDIDATES: Tuple[str, ...] = (
    'CURRENTCREDITAMOUNT',
    'CURRENT_CREDIT_AMOUNT',
    'CURRENTCREDIT',
    'CURRENT_CREDIT',
    'CURRCREDIT',
    'CREDITBALANCE',
    'CREDITBAL',
)


def _columns_for_table(cur: Any, table_name: str) -> set[str]:
    cur.execute(
        """
        SELECT COLUMN_NAME FROM USER_TAB_COLUMNS
         WHERE UPPER(TABLE_NAME) = UPPER(:t)
        """,
        {'t': (table_name or '').strip()},
    )
    return {str(r[0] or '').strip().upper() for r in cur.fetchall() if r and r[0]}


def _pick_column_from_candidates(columns_upper: set[str], candidates: Sequence[str]) -> str | None:
    for cand in candidates:
        if cand in columns_upper:
            return cand
    return None


def _pick_stock_column(columns_upper: set[str]) -> str | None:
    return _pick_column_from_candidates(columns_upper, _ZERO_STOCK_COLUMN_CANDIDATES)


def _pick_credit_column(columns_upper: set[str]) -> str | None:
    return _pick_column_from_candidates(columns_upper, _ZERO_CREDIT_COLUMN_CANDIDATES)


def _build_zero_column_statements(
    cur: Any,
    schema_map: Dict[str, str],
    *,
    logical_tables: Sequence[str],
    pick_column,
    skip_missing_col_note: str,
) -> Tuple[List[str], List[str]]:
    lines: List[str] = []
    notes: List[str] = []
    for logical in logical_tables:
        tbl = schema_map.get(logical)
        if not tbl:
            notes.append('Skipped %s (table not in schema).' % logical)
            continue
        cols = _columns_for_table(cur, tbl)
        col_key = pick_column(cols)
        if not col_key:
            notes.append(skip_missing_col_note % logical)
            continue
        cur.execute(
            """
            SELECT COLUMN_NAME FROM USER_TAB_COLUMNS
             WHERE UPPER(TABLE_NAME) = UPPER(:t) AND UPPER(COLUMN_NAME) = :c
            """,
            {'t': tbl, 'c': col_key},
        )
        row = cur.fetchone()
        col_ident = str(row[0]) if row and row[0] else col_key
        lines.append(f'UPDATE {quoted_ident(tbl)} SET {quoted_ident(col_ident)} = 0')
        notes.append('Will zero %s.%s' % (tbl, col_ident))
    return lines, notes


def build_zero_item_stock_statements(cur: Any, schema_map: Dict[str, str]) -> Tuple[List[str], List[str]]:
    """
    UPDATE statements to zero stock on preserved item master tables (not truncated during clear).
    Returns (sql_lines, notes).
    """
    return _build_zero_column_statements(
        cur,
        schema_map,
        logical_tables=_ZERO_STOCK_TABLES,
        pick_column=_pick_stock_column,
        skip_missing_col_note='Skipped %s (no stock column found).',
    )


def build_zero_customer_credit_statements(cur: Any, schema_map: Dict[str, str]) -> Tuple[List[str], List[str]]:
    """
    UPDATE statements to zero customer outstanding credit on preserved CUSTOMER master.
    Returns (sql_lines, notes).
    """
    return _build_zero_column_statements(
        cur,
        schema_map,
        logical_tables=_ZERO_CUSTOMER_TABLES,
        pick_column=_pick_credit_column,
        skip_missing_col_note='Skipped %s (no current credit column found).',
    )


def build_clear_data_statements(tables_to_truncate: Sequence[str], fk_pairs: Sequence[Tuple[str, str]]) -> Tuple[List[str], List[str], List[str]]:
    """
    Returns three lists: disable_fk_sql, truncate_sql, enable_fk_sql.
    """
    disable_lines: List[str] = []
    enable_lines_reversed: List[str] = []
    for table_name, cons_name in fk_pairs:
        qt = quoted_ident(table_name)
        qc = quoted_ident(cons_name)
        disable_lines.append(f'ALTER TABLE {qt} DISABLE CONSTRAINT {qc}')
        enable_lines_reversed.append(f'ALTER TABLE {qt} ENABLE CONSTRAINT {qc}')
    enable_lines = list(reversed(enable_lines_reversed))
    trunc_lines: List[str] = []
    for t in tables_to_truncate:
        trunc_lines.append(f'TRUNCATE TABLE {quoted_ident(t)}')
    return (disable_lines, trunc_lines, enable_lines)

def _is_system_managed_sequence(seq_name: str) -> bool:
    """Oracle identity-column sequences (ISEQ$$_*) cannot be ALTER/DROP (ORA-32793)."""
    u = str(seq_name or '').strip().upper()
    return u.startswith('ISEQ$$')


def list_user_sequences(cur: Any, *, include_system_managed: bool = False) -> List[Dict[str, Any]]:
    cur.execute(
        "\n        SELECT sequence_name, min_value, max_value, increment_by,\n"
        "               cycle_flag, order_flag, cache_size, last_number\n"
        "          FROM user_sequences\n"
        "         ORDER BY sequence_name\n        "
    )
    out: List[Dict[str, Any]] = []
    for row in cur.fetchall() or []:
        if not row or not row[0]:
            continue
        seq_name = str(row[0])
        if not include_system_managed and _is_system_managed_sequence(seq_name):
            continue
        out.append({
            'sequence_name': seq_name,
            'min_value': int(row[1] or 1),
            'max_value': int(row[2] or 999999999999999999),
            'increment_by': int(row[3] or 1),
            'cycle_flag': str(row[4] or 'N').upper(),
            'order_flag': str(row[5] or 'N').upper(),
            'cache_size': int(row[6] or 0),
            'last_number': int(row[7] or 0),
        })
    return out


def _table_has_column(cur: Any, table_upper: str, column_upper: str) -> bool:
    cur.execute(
        'SELECT COUNT(*) FROM user_tab_columns WHERE table_name = :t AND column_name = :c',
        {'t': table_upper.upper(), 'c': column_upper.upper()},
    )
    return int((cur.fetchone() or [0])[0] or 0) > 0


def _max_numeric_column(cur: Any, table_name: str, column_name: str) -> int:
    qt = quoted_ident(table_name)
    qc = quoted_ident(column_name)
    cur.execute(f'SELECT NVL(MAX({qc}), 0) FROM {qt}')
    return int((cur.fetchone() or [0])[0] or 0)


def _guess_sequence_source(cur: Any, seq_name: str, schema_map: Dict[str, str]) -> Tuple[Optional[str], Optional[str]]:
    """Return (table_name, id_column) for syncing a sequence from remaining table data."""
    key = str(seq_name or '').strip().upper()
    if not key:
        return (None, None)
    hint = SEQUENCE_PK_HINTS.get(key)
    if hint:
        table_key, col = hint[0].upper(), hint[1].upper()
        actual = schema_map.get(table_key)
        if actual and _table_has_column(cur, actual.upper(), col):
            return (actual, col)
    if not key.endswith('_SEQ') or len(key) <= 4:
        return (None, None)
    base = key[:-4]
    table = schema_map.get(base)
    if not table:
        return (None, None)
    candidates: List[str] = [f'{base}_ID']
    candidates.extend(_SEQUENCE_ID_COLUMN_CANDIDATES)
    seen: set[str] = set()
    for col in candidates:
        cu = col.upper()
        if cu in seen:
            continue
        seen.add(cu)
        if _table_has_column(cur, table.upper(), cu):
            return (table, cu)
    return (None, None)


def _sequence_restart_start(cur: Any, seq_name: str, schema_map: Dict[str, str]) -> int:
    """Next safe START WITH: 1 when source table is empty, else MAX(id)+1."""
    table, col = _guess_sequence_source(cur, seq_name, schema_map)
    if table and col:
        return max(1, _max_numeric_column(cur, table, col) + 1)
    return 1


def _sequence_restart_sql(seq_name: str, start_with: int, meta: Dict[str, Any]) -> List[str]:
    qn = quoted_ident(seq_name)
    start = max(1, int(start_with))
    lines = [f'-- {seq_name}: restart at {start}']
    lines.append(f'ALTER SEQUENCE {qn} RESTART START WITH {start}')
    min_v = int(meta.get('min_value') or 1)
    max_v = int(meta.get('max_value') or 999999999999999999)
    inc = int(meta.get('increment_by') or 1)
    cyc = 'CYCLE' if str(meta.get('cycle_flag') or 'N').upper() == 'Y' else 'NOCYCLE'
    cache_size = int(meta.get('cache_size') or 0)
    cache = 'NOCACHE' if cache_size <= 0 else f'CACHE {cache_size}'
    lines.append(
        f'-- Fallback (Oracle 11g / if RESTART unsupported): DROP + CREATE\n'
        f'DROP SEQUENCE {qn};\n'
        f'CREATE SEQUENCE {qn} MINVALUE {min_v} MAXVALUE {max_v} '
        f'START WITH {start} INCREMENT BY {inc} {cyc} {cache};'
    )
    return lines


def _execute_sequence_restart(cur: Any, seq_name: str, start_with: int, meta: Dict[str, Any]) -> None:
    if _is_system_managed_sequence(seq_name):
        raise ValueError('ORA-32793: system-generated identity sequence (skipped)')
    qn = quoted_ident(seq_name)
    start = max(1, int(start_with))
    try:
        cur.execute(f'ALTER SEQUENCE {qn} RESTART START WITH {start}')
        return
    except Exception as ex:
        err = str(ex)
        if 'ORA-32793' in err:
            raise ValueError(err) from ex
        if 'RESTART' not in err.upper() and 'ORA-00905' not in err and 'ORA-02289' not in err:
            raise
    min_v = int(meta.get('min_value') or 1)
    max_v = int(meta.get('max_value') or 999999999999999999)
    inc = int(meta.get('increment_by') or 1)
    cyc = 'CYCLE' if str(meta.get('cycle_flag') or 'N').upper() == 'Y' else 'NOCYCLE'
    cache_size = int(meta.get('cache_size') or 0)
    cache = 'NOCACHE' if cache_size <= 0 else f'CACHE {cache_size}'
    try:
        cur.execute(f'DROP SEQUENCE {qn}')
    except Exception as ex2:
        if 'ORA-02289' not in str(ex2):
            raise
    cur.execute(
        f'CREATE SEQUENCE {qn} MINVALUE {min_v} MAXVALUE {max_v} '
        f'START WITH {start} INCREMENT BY {inc} {cyc} {cache}'
    )


def build_reset_sequences_and_counters_script(cur: Any) -> Tuple[List[str], List[str], List[Tuple[str, int]]]:
    """Returns (script_lines, messages, sequence_plan) where plan is [(seq_name, start_with), ...]."""
    schema_map = _schema_table_map(cur)
    script_lines: List[str] = []
    messages: List[str] = []
    plan: List[Tuple[str, int]] = []
    script_lines.append('-- Reset document counters & Oracle sequences (new company / fresh numbering)')
    counter_tables: List[str] = []
    for name in DOCUMENT_COUNTER_TABLES:
        actual = schema_map.get(name.upper())
        if actual:
            counter_tables.append(actual)
            script_lines.append(f'TRUNCATE TABLE {quoted_ident(actual)};')
    if counter_tables:
        messages.append('Document counter tables to clear: %s' % ', '.join(counter_tables))
    else:
        messages.append('No BILLNOTABLE/BILLNOTIME in schema (skipped counter table truncate).')
    seqs = list_user_sequences(cur)
    skipped_identity = 0
    try:
        cur.execute(
            "SELECT COUNT(*) FROM user_sequences WHERE sequence_name LIKE 'ISEQ$$%'"
        )
        skipped_identity = int((cur.fetchone() or [0])[0] or 0)
    except Exception:
        skipped_identity = 0
    if skipped_identity:
        script_lines.append(
            f'-- Skipped {skipped_identity} system identity sequence(s) (ISEQ$$*; ORA-32793 if altered)'
        )
        messages.append(
            'Skipped %s Oracle identity sequence(s) (ISEQ$$*). '
            'Reset identity columns separately after truncate if needed.'
            % skipped_identity
        )
    if not seqs:
        if skipped_identity:
            messages.append('No user-defined sequences to restart (identity sequences excluded).')
        else:
            messages.append('No USER_SEQUENCES in schema.')
        script_lines.append('-- (no user-defined sequences)')
        return (script_lines, messages, plan)
    script_lines.append('-- User-defined sequences (START WITH = 1 when source table empty, else MAX(id)+1)')
    for meta in seqs:
        seq_name = meta['sequence_name']
        start = _sequence_restart_start(cur, seq_name, schema_map)
        plan.append((seq_name, start))
        script_lines.extend(_sequence_restart_sql(seq_name, start, meta))
    messages.append('Sequences to restart: %s' % len(plan))
    script_lines.append('COMMIT;')
    return (script_lines, messages, plan)


def run_reset_sequences_and_document_counters(
    target_user: str,
    target_password: str,
    target_dsn: str,
    *,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """
    Clear BILLNOTABLE (reserved bill numbers) and restart USER_SEQUENCES.

    Sequence restart values follow remaining table data: empty tables → 1;
    preserved masters (e.g. WAREHOUSE_MASTER) → MAX(id)+1.
    """
    messages: List[str] = []
    errors: List[str] = []
    script_lines: List[str] = []
    conn = connect(target_user, target_password, target_dsn)
    cur = conn.cursor()
    sequences_reset = 0
    counter_tables_cleared: List[str] = []
    try:
        script_lines, build_msgs, plan = build_reset_sequences_and_counters_script(cur)
        messages.extend(build_msgs)
        if dry_run:
            messages.append('Preview only — no sequence/counter changes were executed.')
            return {
                'ok': True,
                'dry_run': True,
                'messages': messages,
                'errors': errors,
                'script_lines': script_lines,
                'sequences_reset': len(plan),
                'counter_tables_cleared': [],
            }
        schema_map = _schema_table_map(cur)
        seq_meta = {m['sequence_name']: m for m in list_user_sequences(cur)}
        for name in DOCUMENT_COUNTER_TABLES:
            actual = schema_map.get(name.upper())
            if not actual:
                continue
            try:
                cur.execute(f'TRUNCATE TABLE {quoted_ident(actual)}')
                counter_tables_cleared.append(actual)
            except Exception as ex:
                errors.append(f'TRUNCATE {actual}: {ex}')
        skipped_system: List[str] = []
        for seq_name, start in plan:
            meta = seq_meta.get(seq_name) or {}
            try:
                _execute_sequence_restart(cur, seq_name, start, meta)
                sequences_reset += 1
            except Exception as ex:
                err = str(ex)
                if 'ORA-32793' in err or _is_system_managed_sequence(seq_name):
                    skipped_system.append(seq_name)
                    continue
                errors.append(f'Sequence {seq_name}: {ex}')
        if skipped_system:
            messages.append(
                'Skipped %s system identity sequence(s): %s'
                % (len(skipped_system), ', '.join(skipped_system[:5]) + ('…' if len(skipped_system) > 5 else ''))
            )
        if errors:
            conn.rollback()
            return {
                'ok': False,
                'dry_run': False,
                'messages': messages,
                'errors': errors,
                'script_lines': script_lines,
                'sequences_reset': 0,
                'counter_tables_cleared': [],
            }
        conn.commit()
        messages.append(
            'Executed: cleared %s counter table(s), restarted %s sequence(s).'
            % (len(counter_tables_cleared), sequences_reset)
        )
        return {
            'ok': True,
            'dry_run': False,
            'messages': messages,
            'errors': errors,
            'script_lines': script_lines,
            'sequences_reset': sequences_reset,
            'counter_tables_cleared': counter_tables_cleared,
        }
    finally:
        try:
            cur.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass


def run_clear_target_data(target_user: str, target_password: str, target_dsn: str, *, preserve_auth_tables: bool=True, dry_run: bool=True, extra_protected: Sequence[str] | None=None) -> Dict[str, Any]:
    """
    Disable FKs, TRUNCATE user tables (optional auth protect), re-enable FKs.

    When dry_run is True, no DDL is executed; ``script_lines`` holds the full script.
    """
    messages: List[str] = []
    errors: List[str] = []
    script_lines: List[str] = []
    protected: set[str] = set()
    if preserve_auth_tables:
        protected |= set(DEFAULT_PROTECTED_TABLES)
    if extra_protected:
        protected |= {x.strip().upper() for x in extra_protected if (x or '').strip()}
    conn = connect(target_user, target_password, target_dsn)
    cur = conn.cursor()
    try:
        all_tables = list_user_tables(cur)
        fk_pairs = fetch_enabled_foreign_keys(cur)
        to_clear = [t for t in all_tables if t.upper() not in protected]
        if not to_clear:
            return {'ok': False, 'dry_run': dry_run, 'messages': messages, 'errors': ['No tables left to truncate (all are protected or schema has no tables).'], 'script_lines': script_lines, 'protected': sorted(protected), 'truncated_count': 0}
        schema_map = _schema_table_map(cur)
        disable_sql, trunc_sql, enable_sql = build_clear_data_statements(to_clear, fk_pairs)
        zero_stock_sql, zero_stock_notes = build_zero_item_stock_statements(cur, schema_map)
        zero_credit_sql, zero_credit_notes = build_zero_customer_credit_statements(cur, schema_map)
        zero_sql = zero_stock_sql + zero_credit_sql
        zero_notes = zero_stock_notes + zero_credit_notes
        script_lines.append('-- Clear data script (new company / empty business data)')
        script_lines.append(f"-- Schema user: {(target_user or '').strip()}")
        script_lines.append('-- Step 1: disable foreign keys')
        script_lines.extend(disable_sql)
        script_lines.append('-- Step 2: truncate tables')
        script_lines.extend(trunc_sql)
        script_lines.append('-- Step 3: re-enable foreign keys')
        script_lines.extend(enable_sql)
        script_lines.append('-- Step 4: zero stock/credit on preserved masters (ITEMMASTER, ITEMALTERNATEUOMMAP, CUSTOMER)')
        if zero_sql:
            script_lines.extend(zero_sql)
        else:
            script_lines.append('-- (no preserved master stock/credit updates — tables/columns missing)')
        script_lines.append('COMMIT;')
        messages.append('Tables in schema: %s' % len(all_tables))
        messages.append('Protected (skipped): %s' % (', '.join(sorted(protected)) if protected else '(none)'))
        messages.append('Will truncate: %s' % len(to_clear))
        messages.append('Foreign keys to disable/enable: %s' % len(fk_pairs))
        for zn in zero_notes:
            messages.append(zn)
        if dry_run:
            messages.append('Preview only — no changes were executed.')
            return {'ok': True, 'dry_run': True, 'messages': messages, 'errors': errors, 'script_lines': script_lines, 'protected': sorted(protected), 'truncated_count': len(to_clear)}
        try:
            for sql in disable_sql:
                cur.execute(sql)
            for sql in trunc_sql:
                cur.execute(sql)
            for sql in enable_sql:
                cur.execute(sql)
            for sql in zero_sql:
                cur.execute(sql)
            conn.commit()
            msg = 'Executed: disabled %s FKs, truncated %s tables, re-enabled FKs.' % (len(fk_pairs), len(to_clear))
            if zero_sql:
                msg += ' Zeroed stock/credit on %s preserved table(s).' % len(zero_sql)
            messages.append(msg)
            return {'ok': True, 'dry_run': False, 'messages': messages, 'errors': errors, 'script_lines': script_lines, 'protected': sorted(protected), 'truncated_count': len(to_clear)}
        except Exception as ex:
            conn.rollback()
            errors.append(str(ex))
            for table_name, cons_name in reversed(fk_pairs):
                try:
                    cur.execute('ALTER TABLE %s ENABLE CONSTRAINT %s' % (quoted_ident(table_name), quoted_ident(cons_name)))
                except Exception as ex2:
                    errors.append('Re-enable failed %s.%s: %s' % (table_name, cons_name, ex2))
            try:
                conn.commit()
            except Exception:
                pass
            return {'ok': False, 'dry_run': False, 'messages': messages, 'errors': errors, 'script_lines': script_lines, 'protected': sorted(protected), 'truncated_count': 0}
    finally:
        try:
            cur.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass


def fetch_suggested_protected_tables(target_user: str, target_password: str, target_dsn: str) -> Dict[str, Any]:
    """Return important setup/master tables present in the target schema (exact USER_TABLES names)."""
    conn = connect(target_user, target_password, target_dsn)
    cur = conn.cursor()
    try:
        schema_map = _schema_table_map(cur)
        groups: List[Dict[str, Any]] = []
        found: set[str] = set()
        for label, names in SUGGESTED_PROTECTED_TABLE_GROUPS:
            present = _resolve_tables_in_schema(names, schema_map)
            if present:
                groups.append({'label': label, 'tables': present})
                found.update(present)
        tables = sorted(found, key=lambda x: x.upper())
        return {
            'ok': True,
            'tables': tables,
            'groups': groups,
            'csv': ', '.join(tables),
            'schema_table_count': len(schema_map),
            'default_protected': sorted(DEFAULT_PROTECTED_TABLES),
        }
    finally:
        try:
            cur.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
