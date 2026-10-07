"""Stock counting sessions (PDT upload + web accept → bin/warehouse stock update)."""
from __future__ import annotations

import logging
import os
from collections import defaultdict
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from db import (
    BIN_STOCK_TABLE,
    DEFAULT_PARTY_ACCOUNTS,
    GL_DTL_SEQ,
    GL_DTL_TABLE,
    GL_HDR_TABLE,
    WAREHOUSE_STOCK_TABLE,
    _TABLE_COLUMNS_CACHE,
    _detect_column,
    _detect_table,
    _get_connection,
    _journal_warehouse_fields_from_line,
    _norm_gl_account_code,
    _safe_rows,
    _table_exists,
    apply_bin_stock_delta_cur,
    apply_warehouse_stock_delta_cur,
    ensure_gl_tables,
    ensure_itemjournal_averagecost_column,
    ensure_itemjournal_batch_columns,
    ensure_itemjournal_storage_id_column,
    ensure_itemjournal_surrogate_pk,
    ensure_itemjournal_warehouse_columns,
    ensure_warehouse_stock_table_cur,
    get_all_chart_of_accounts,
    get_item_by_alternate_barcode,
    get_item_by_code,
    get_item_by_manufacturer_id,
    get_stk_adj_opening_stock_mode_enabled,
    get_warehouse_master_by_id,
    repost_itemjournal_stock_count,
    resolve_item_inventory_gl_account,
    resolve_stk_adj_variance_account_codes,
    resolve_warehouse_loc_key_for_location_code,
    resolve_warehouse_master_table,
    _journal_average_cost_for_line,
)

_LOG = logging.getLogger('nexa.stock_count')

STOCK_COUNT_HDR_TABLE = 'STOCK_COUNT_HDR'
STOCK_COUNT_DTL_TABLE = 'STOCK_COUNT_DTL'
STOCK_COUNT_JOURNAL_TABLE = 'STOCK_COUNT_JOURNAL'
STOCK_COUNT_JOURNAL_SEQ = 'STOCK_COUNT_JOURNAL_SEQ'
STOCK_COUNT_STATUSES = ('DRAFT', 'PENDING', 'POSTED', 'CANCELLED')
STOCK_COUNT_RESET_NO = 1


def _resolve_stock_count_table_columns(table: str) -> List[str]:
    """Column names for stock-count tables (owned table or synonym → ``all_tab_columns``)."""
    key = (table or '').strip().upper()
    if not key:
        return []
    cached = _TABLE_COLUMNS_CACHE.get(key)
    if cached is not None:
        return list(cached)
    cols: List[str] = []
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT column_name FROM user_tab_columns
                    WHERE table_name = :t ORDER BY column_id
                    """,
                    {'t': key},
                )
                cols = [str(row[0] or '').upper() for row in cur.fetchall() or []]
                if not cols:
                    cur.execute(
                        """
                        SELECT table_owner, table_name FROM user_synonyms
                        WHERE UPPER(synonym_name) = :s
                        """,
                        {'s': key},
                    )
                    syn = cur.fetchone()
                    if syn:
                        owner = str(syn[0] or '').strip().upper()
                        tname = str(syn[1] or key).strip().upper()
                        cur.execute(
                            """
                            SELECT column_name FROM all_tab_columns
                            WHERE owner = :o AND table_name = :t ORDER BY column_id
                            """,
                            {'o': owner, 't': tname},
                        )
                        cols = [str(row[0] or '').upper() for row in cur.fetchall() or []]
    except Exception as ex:
        _LOG.warning('_resolve_stock_count_table_columns %s: %s', key, ex)
    if cols:
        _TABLE_COLUMNS_CACHE[key] = cols
    else:
        _TABLE_COLUMNS_CACHE.pop(key, None)
    return cols


def stock_count_dtl_has_warehouse_id() -> bool:
    return 'WAREHOUSE_ID' in set(_resolve_stock_count_table_columns(STOCK_COUNT_DTL_TABLE))


def _stock_count_line_category_parts(im_tbl: str) -> Tuple[str, str]:
    """JOIN + SELECT fragments for main / department / micro category names on count lines."""
    null_select = (
        'CAST(NULL AS VARCHAR2(200)) AS main_category_name, '
        'CAST(NULL AS VARCHAR2(200)) AS category_name, '
        'CAST(NULL AS VARCHAR2(200)) AS micro_category_name'
    )
    cat_tbl = _detect_table(['CATEGORY', 'category'])
    if not cat_tbl or not _table_exists(cat_tbl):
        return '', null_select

    im_cols = {c.upper() for c in _resolve_stock_count_table_columns(im_tbl)}
    cat_name_col = _detect_column(cat_tbl, ['NAME', 'CATEGORYNAME', 'CATNAME']) or 'NAME'
    cat_loc_col = _detect_column(cat_tbl, ['LOCATIONCODE', 'LOCATION_CODE']) or 'LOCATIONCODE'
    cat_code_col = _detect_column(cat_tbl, ['CODE', 'CATEGORYCODE']) or 'CODE'
    cat_flag_col = _detect_column(cat_tbl, ['FLAG', 'CATEGORYFLAG']) or 'FLAG'

    joins: List[str] = []
    selects: List[str] = []
    pairs = (
        ('MAINCATEGORY', 'cat_m', 'M', 'main_category_name'),
        ('DEPARTMENTCODE', 'cat_d', 'D', 'category_name'),
        ('CATEGORYCODE', 'cat_c', 'C', 'micro_category_name'),
    )
    for im_col, alias, flag, out_name in pairs:
        if im_col in im_cols:
            joins.append(
                f"LEFT JOIN {cat_tbl} {alias} ON {alias}.{cat_flag_col} = '{flag}' "
                f"AND {alias}.{cat_code_col} = im.{im_col} "
                f"AND {alias}.{cat_loc_col} = im.LOCATIONCODE"
            )
            selects.append(f'{alias}.{cat_name_col} AS {out_name}')
        else:
            selects.append(f'CAST(NULL AS VARCHAR2(200)) AS {out_name}')
    return '\n        '.join(joins), ', '.join(selects)


def _stock_count_dtl_extra_columns() -> set:
    return set(_resolve_stock_count_table_columns(STOCK_COUNT_DTL_TABLE))


def ensure_stock_count_dtl_extra_columns() -> bool:
    """Add COUNTED_BY, AVERAGE_COST, STOCK_VALUE on STOCK_COUNT_DTL when missing."""
    if not _table_exists(STOCK_COUNT_DTL_TABLE):
        return False
    alters = (
        ('COUNTED_BY', 'ALTER TABLE STOCK_COUNT_DTL ADD (COUNTED_BY VARCHAR2(50))'),
        ('AVERAGE_COST', 'ALTER TABLE STOCK_COUNT_DTL ADD (AVERAGE_COST NUMBER(18,6))'),
        ('STOCK_VALUE', 'ALTER TABLE STOCK_COUNT_DTL ADD (STOCK_VALUE NUMBER(18,2))'),
    )
    try:
        cols = _stock_count_dtl_extra_columns()
        pending = [(c, sql) for c, sql in alters if c not in cols]
        if not pending:
            _backfill_stock_count_dtl_extra_fields()
            return True
        with _get_connection() as conn:
            with conn.cursor() as cur:
                for _col, sql in pending:
                    try:
                        cur.execute(sql)
                    except Exception as ex:
                        err = str(ex)
                        if 'ORA-01430' not in err and 'ORA-01442' not in err:
                            raise
            conn.commit()
        _TABLE_COLUMNS_CACHE.pop(STOCK_COUNT_DTL_TABLE.upper(), None)
        ok = all(c in _stock_count_dtl_extra_columns() for c, _ in alters)
        if ok:
            _backfill_stock_count_dtl_extra_fields()
        return ok
    except Exception as ex:
        _LOG.error('ensure_stock_count_dtl_extra_columns: %s', ex)
        try:
            with _get_connection() as conn:
                conn.rollback()
        except Exception:
            pass
        return False


def _backfill_stock_count_dtl_extra_fields() -> None:
    """Populate user/cost/value on lines counted before COUNTED_BY columns existed."""
    dtl_cols = _stock_count_dtl_extra_columns()
    if not {'COUNTED_BY', 'AVERAGE_COST', 'STOCK_VALUE'}.issubset(dtl_cols):
        return
    pending = _safe_rows(
        """
        SELECT COUNT(*) AS c FROM STOCK_COUNT_DTL
        WHERE COUNTED_BY IS NULL OR AVERAGE_COST IS NULL OR STOCK_VALUE IS NULL
        """,
        {},
    )
    if not pending or int(pending[0].get('c') or 0) == 0:
        return
    im_tbl = _detect_table(['ITEMMASTER', 'itemmaster']) or 'ITEMMASTER'
    im_avg_col = _detect_column(im_tbl, ['AVERAGECOST', 'AVERAGE_COST', 'averagecost'])
    im_avg_sub = (
        f'(SELECT NVL(im.{im_avg_col}, 0) FROM {im_tbl} im WHERE im.ITEMCODE = d.ITEMCODE)'
        if im_avg_col
        else '0'
    )
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    UPDATE STOCK_COUNT_DTL d SET
                        COUNTED_BY = NVL(
                            d.COUNTED_BY,
                            (SELECT h.CREATED_BY FROM STOCK_COUNT_HDR h
                             WHERE h.LOCATIONCODE = d.LOCATIONCODE AND h.COUNT_NO = d.COUNT_NO)
                        ),
                        AVERAGE_COST = NVL(d.AVERAGE_COST, {im_avg_sub}),
                        STOCK_VALUE = NVL(
                            d.STOCK_VALUE,
                            ROUND(NVL(d.COUNTED_QTY, 0) * NVL(d.AVERAGE_COST, {im_avg_sub}), 2)
                        )
                    WHERE d.COUNTED_BY IS NULL OR d.AVERAGE_COST IS NULL OR d.STOCK_VALUE IS NULL
                    """
                )
            conn.commit()
    except Exception as ex:
        _LOG.warning('_backfill_stock_count_dtl_extra_fields: %s', ex)
        try:
            with _get_connection() as conn:
                conn.rollback()
        except Exception:
            pass


def ensure_stock_count_dtl_warehouse_column() -> bool:
    """Add ``WAREHOUSE_ID`` to ``STOCK_COUNT_DTL`` when missing. Returns True if column is present."""
    cols = _resolve_stock_count_table_columns(STOCK_COUNT_DTL_TABLE)
    if not cols and not _table_exists(STOCK_COUNT_DTL_TABLE):
        return False
    if 'WAREHOUSE_ID' in cols:
        return True
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('ALTER TABLE STOCK_COUNT_DTL ADD (WAREHOUSE_ID NUMBER(12))')
            conn.commit()
        _TABLE_COLUMNS_CACHE.pop(STOCK_COUNT_DTL_TABLE.upper(), None)
        ok = stock_count_dtl_has_warehouse_id()
        if ok:
            _LOG.info('Added STOCK_COUNT_DTL.WAREHOUSE_ID')
        else:
            _LOG.error('STOCK_COUNT_DTL.WAREHOUSE_ID still missing after ALTER')
        return ok
    except Exception as ex:
        err = str(ex)
        if 'ORA-01430' in err or 'ORA-01442' in err:
            _TABLE_COLUMNS_CACHE.pop(STOCK_COUNT_DTL_TABLE.upper(), None)
            return stock_count_dtl_has_warehouse_id()
        _LOG.error('ensure_stock_count_dtl_warehouse_column: %s', ex)
        print(f'[ensure_stock_count_dtl_warehouse_column] {ex}')
        try:
            with _get_connection() as conn:
                conn.rollback()
        except Exception:
            pass
        return False


def ensure_stock_count_journal_cur(cur: Any) -> bool:
    """Create ``STOCK_COUNT_JOURNAL`` + sequence on the connection behind *cur*."""
    try:
        cur.execute(
            "SELECT COUNT(*) FROM user_sequences WHERE sequence_name = :n",
            {'n': STOCK_COUNT_JOURNAL_SEQ},
        )
        if int((cur.fetchone() or [0])[0] or 0) == 0:
            cur.execute(
                f'CREATE SEQUENCE {STOCK_COUNT_JOURNAL_SEQ} '
                'START WITH 1 INCREMENT BY 1 NOCACHE NOCYCLE'
            )
        cur.execute(
            "SELECT COUNT(*) FROM user_tables WHERE table_name = :t",
            {'t': STOCK_COUNT_JOURNAL_TABLE},
        )
        if int((cur.fetchone() or [0])[0] or 0) == 0:
            cur.execute(
                f"""
                CREATE TABLE {STOCK_COUNT_JOURNAL_TABLE} (
                    JOURNAL_ID        NUMBER NOT NULL,
                    LOCATIONCODE      NUMBER(6) NOT NULL,
                    COUNT_NO          NUMBER(10) NOT NULL,
                    LINE_NO           NUMBER(8),
                    ITEMCODE          NUMBER(12),
                    ACTION            VARCHAR2(20) NOT NULL,
                    OLD_COUNTED_QTY   NUMBER(18,6),
                    NEW_COUNTED_QTY   NUMBER(18,6),
                    OLD_SYSTEM_QTY    NUMBER(18,6),
                    NEW_SYSTEM_QTY    NUMBER(18,6),
                    OLD_VARIANCE_QTY  NUMBER(18,6),
                    NEW_VARIANCE_QTY  NUMBER(18,6),
                    BARCODE           VARCHAR2(80),
                    UOM               VARCHAR2(20),
                    WAREHOUSE_ID      NUMBER(12),
                    STORAGE_ID        NUMBER(12),
                    COUNTED_BY        VARCHAR2(50),
                    CHANGED_BY        VARCHAR2(50),
                    SOURCE            VARCHAR2(20) DEFAULT 'ERP',
                    PDT_DEVICE_ID     VARCHAR2(50),
                    REMARKS           VARCHAR2(500),
                    LOGGED_AT         TIMESTAMP(6) DEFAULT SYSTIMESTAMP NOT NULL,
                    CONSTRAINT PK_STOCK_COUNT_JOURNAL PRIMARY KEY (JOURNAL_ID)
                ) TABLESPACE USERS
                """
            )
        cur.execute(
            "SELECT COUNT(*) FROM user_indexes WHERE index_name = 'IX_STOCK_COUNT_JNL'"
        )
        if int((cur.fetchone() or [0])[0] or 0) == 0:
            cur.execute(
                f'CREATE INDEX IX_STOCK_COUNT_JNL ON {STOCK_COUNT_JOURNAL_TABLE} '
                '(LOCATIONCODE, COUNT_NO, LOGGED_AT)'
            )
        _TABLE_COLUMNS_CACHE.pop(STOCK_COUNT_JOURNAL_TABLE.upper(), None)
        return True
    except Exception as ex:
        _LOG.error('ensure_stock_count_journal_cur: %s', ex)
        return False


def ensure_stock_count_journal_table() -> bool:
    """Create journal table on the default tenant connection."""
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                ok = ensure_stock_count_journal_cur(cur)
            conn.commit()
        return ok
    except Exception as ex:
        _LOG.error('ensure_stock_count_journal_table: %s', ex)
        return False


def log_stock_count_journal(
    cur: Any,
    *,
    location_code: int,
    count_no: int,
    action: str,
    line_no: Optional[int] = None,
    itemcode: Optional[int] = None,
    old_counted_qty: Optional[float] = None,
    new_counted_qty: Optional[float] = None,
    old_system_qty: Optional[float] = None,
    new_system_qty: Optional[float] = None,
    old_variance_qty: Optional[float] = None,
    new_variance_qty: Optional[float] = None,
    barcode: str = '',
    uom: str = '',
    warehouse_id: Optional[int] = None,
    storage_id: Optional[int] = None,
    counted_by: str = '',
    changed_by: str = '',
    source: str = 'ERP',
    pdt_device_id: str = '',
    remarks: str = '',
) -> None:
    """Append one audit row for a stock count change (best-effort)."""
    if not ensure_stock_count_journal_cur(cur):
        return
    act = (action or '').strip().upper()[:20] or 'UPDATE'
    try:
        cur.execute(
            f"""
            INSERT INTO {STOCK_COUNT_JOURNAL_TABLE} (
                JOURNAL_ID, LOCATIONCODE, COUNT_NO, LINE_NO, ITEMCODE, ACTION,
                OLD_COUNTED_QTY, NEW_COUNTED_QTY, OLD_SYSTEM_QTY, NEW_SYSTEM_QTY,
                OLD_VARIANCE_QTY, NEW_VARIANCE_QTY, BARCODE, UOM,
                WAREHOUSE_ID, STORAGE_ID, COUNTED_BY, CHANGED_BY, SOURCE,
                PDT_DEVICE_ID, REMARKS, LOGGED_AT
            ) VALUES (
                {STOCK_COUNT_JOURNAL_SEQ}.NEXTVAL, :lc, :cn, :ln, :ic, :act,
                :ocq, :ncq, :osq, :nsq, :ovq, :nvq, :bc, :uom,
                :wid, :sid, :cb, :chby, :src, :pdt, :rmk, SYSTIMESTAMP
            )
            """,
            {
                'lc': int(location_code),
                'cn': int(count_no),
                'ln': int(line_no) if line_no else None,
                'ic': int(itemcode) if itemcode else None,
                'act': act,
                'ocq': old_counted_qty,
                'ncq': new_counted_qty,
                'osq': old_system_qty,
                'nsq': new_system_qty,
                'ovq': old_variance_qty,
                'nvq': new_variance_qty,
                'bc': (barcode or '')[:80],
                'uom': (uom or '')[:20],
                'wid': int(warehouse_id) if warehouse_id else None,
                'sid': int(storage_id) if storage_id else None,
                'cb': (counted_by or '')[:50],
                'chby': (changed_by or '')[:50],
                'src': (source or 'ERP')[:20],
                'pdt': (pdt_device_id or '')[:50],
                'rmk': (remarks or '')[:500],
            },
        )
    except Exception as ex:
        _LOG.warning('log_stock_count_journal %s/%s %s: %s', location_code, count_no, act, ex)


def list_stock_count_journal(
    location_code: int,
    count_no: int,
    *,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """Recent journal rows for one count session."""
    if not _table_exists(STOCK_COUNT_JOURNAL_TABLE):
        return []
    lim = max(1, min(int(limit), 500))
    return _safe_rows(
        f"""
        SELECT * FROM (
            SELECT JOURNAL_ID AS journal_id,
                   LOCATIONCODE AS locationcode,
                   COUNT_NO AS count_no,
                   LINE_NO AS line_no,
                   ITEMCODE AS itemcode,
                   ACTION AS action,
                   OLD_COUNTED_QTY AS old_counted_qty,
                   NEW_COUNTED_QTY AS new_counted_qty,
                   OLD_SYSTEM_QTY AS old_system_qty,
                   NEW_SYSTEM_QTY AS new_system_qty,
                   OLD_VARIANCE_QTY AS old_variance_qty,
                   NEW_VARIANCE_QTY AS new_variance_qty,
                   BARCODE AS barcode,
                   UOM AS uom,
                   WAREHOUSE_ID AS warehouse_id,
                   STORAGE_ID AS storage_id,
                   COUNTED_BY AS counted_by,
                   CHANGED_BY AS changed_by,
                   SOURCE AS source,
                   PDT_DEVICE_ID AS pdt_device_id,
                   REMARKS AS remarks,
                   LOGGED_AT AS logged_at
              FROM {STOCK_COUNT_JOURNAL_TABLE}
             WHERE LOCATIONCODE = :lc AND COUNT_NO = :cn
             ORDER BY LOGGED_AT DESC, JOURNAL_ID DESC
        ) WHERE ROWNUM <= :lim
        """,
        {'lc': int(location_code), 'cn': int(count_no), 'lim': lim},
    ) or []


def ensure_stock_count_tables() -> bool:
    """Create ``STOCK_COUNT_HDR`` / ``STOCK_COUNT_DTL`` in tenant DB when missing."""
    if _table_exists(STOCK_COUNT_HDR_TABLE) and _table_exists(STOCK_COUNT_DTL_TABLE):
        ensure_stock_count_dtl_warehouse_column()
        ensure_stock_count_dtl_extra_columns()
        ensure_stock_count_journal_table()
        return True
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM user_tables WHERE table_name = 'STOCK_COUNT_HDR'"
                )
                if int((cur.fetchone() or [0])[0] or 0) == 0:
                    cur.execute(
                        """
                        CREATE TABLE STOCK_COUNT_HDR (
                            LOCATIONCODE   NUMBER(6) NOT NULL,
                            COUNT_NO       NUMBER(10) NOT NULL,
                            COUNT_DATE     DATE DEFAULT TRUNC(SYSDATE) NOT NULL,
                            WAREHOUSE_ID   NUMBER(12),
                            STORAGE_ID     NUMBER(12),
                            STATUS         VARCHAR2(20) DEFAULT 'DRAFT' NOT NULL,
                            REMARKS        VARCHAR2(500),
                            PDT_DEVICE_ID  VARCHAR2(50),
                            CREATED_BY     VARCHAR2(50),
                            CREATED_AT     TIMESTAMP(6) DEFAULT SYSTIMESTAMP,
                            POSTED_BY      VARCHAR2(50),
                            POSTED_AT      TIMESTAMP(6),
                            CONSTRAINT PK_STOCK_COUNT_HDR PRIMARY KEY (LOCATIONCODE, COUNT_NO)
                        ) TABLESPACE USERS
                        """
                    )
                cur.execute(
                    "SELECT COUNT(*) FROM user_tables WHERE table_name = 'STOCK_COUNT_DTL'"
                )
                if int((cur.fetchone() or [0])[0] or 0) == 0:
                    cur.execute(
                        """
                        CREATE TABLE STOCK_COUNT_DTL (
                            LOCATIONCODE   NUMBER(6) NOT NULL,
                            COUNT_NO       NUMBER(10) NOT NULL,
                            LINE_NO        NUMBER(8) NOT NULL,
                            ITEMCODE       NUMBER(12) NOT NULL,
                            BARCODE        VARCHAR2(80),
                            UOM            VARCHAR2(20),
                            SYSTEM_QTY     NUMBER(18,6) DEFAULT 0,
                            COUNTED_QTY    NUMBER(18,6) DEFAULT 0,
                            VARIANCE_QTY   NUMBER(18,6) DEFAULT 0,
                            STORAGE_ID     NUMBER(12),
                            WAREHOUSE_ID   NUMBER(12),
                            PDT_SCAN_AT    TIMESTAMP(6),
                            CONSTRAINT PK_STOCK_COUNT_DTL PRIMARY KEY (LOCATIONCODE, COUNT_NO, LINE_NO)
                        ) TABLESPACE USERS
                        """
                    )
                cur.execute(
                    "SELECT COUNT(*) FROM user_indexes WHERE index_name = 'IX_STOCK_COUNT_HDR_STAT'"
                )
                if int((cur.fetchone() or [0])[0] or 0) == 0:
                    cur.execute(
                        "CREATE INDEX IX_STOCK_COUNT_HDR_STAT ON STOCK_COUNT_HDR (STATUS, COUNT_DATE)"
                    )
            conn.commit()
        ensure_stock_count_dtl_warehouse_column()
        ensure_stock_count_dtl_extra_columns()
        ensure_stock_count_journal_table()
        return True
    except Exception as ex:
        print(f'[ensure_stock_count_tables] {ex}')
        return False


def next_stock_count_no(location_code: int) -> int:
    ensure_stock_count_tables()
    rows = _safe_rows(
        """
        SELECT NVL(MAX(COUNT_NO), 0) + 1 AS nxt
        FROM STOCK_COUNT_HDR
        WHERE LOCATIONCODE = :lc
        """,
        {'lc': int(location_code)},
    )
    if rows and rows[0].get('nxt') is not None:
        try:
            return int(rows[0]['nxt'])
        except (TypeError, ValueError):
            pass
    return 1


def list_stock_counts(
    location_code: int,
    *,
    status: Optional[str] = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    ensure_stock_count_tables()
    lim = max(1, min(int(limit), 500))
    params: Dict[str, Any] = {'lc': int(location_code), 'lim': lim}
    where = 'WHERE h.LOCATIONCODE = :lc'
    st = (status or '').strip().upper()
    if st:
        where += ' AND UPPER(TRIM(h.STATUS)) = :st'
        params['st'] = st
    q = f"""
        SELECT * FROM (
            SELECT h.LOCATIONCODE AS locationcode,
                   h.COUNT_NO AS count_no,
                   h.COUNT_DATE AS count_date,
                   h.WAREHOUSE_ID AS warehouse_id,
                   h.STORAGE_ID AS storage_id,
                   h.STATUS AS status,
                   h.REMARKS AS remarks,
                   h.PDT_DEVICE_ID AS pdt_device_id,
                   h.CREATED_BY AS created_by,
                   h.CREATED_AT AS created_at,
                   h.POSTED_BY AS posted_by,
                   h.POSTED_AT AS posted_at,
                   (SELECT COUNT(*) FROM STOCK_COUNT_DTL d
                    WHERE d.LOCATIONCODE = h.LOCATIONCODE AND d.COUNT_NO = h.COUNT_NO) AS line_count
            FROM STOCK_COUNT_HDR h
            {where}
            ORDER BY h.COUNT_NO DESC
        ) WHERE ROWNUM <= :lim
    """
    return _safe_rows(q, params) or []


def get_stock_count_header(location_code: int, count_no: int) -> Optional[Dict[str, Any]]:
    ensure_stock_count_tables()
    rows = _safe_rows(
        """
        SELECT LOCATIONCODE AS locationcode, COUNT_NO AS count_no, COUNT_DATE AS count_date,
               WAREHOUSE_ID AS warehouse_id, STORAGE_ID AS storage_id, STATUS AS status,
               REMARKS AS remarks, PDT_DEVICE_ID AS pdt_device_id,
               CREATED_BY AS created_by, CREATED_AT AS created_at,
               POSTED_BY AS posted_by, POSTED_AT AS posted_at
        FROM STOCK_COUNT_HDR
        WHERE LOCATIONCODE = :lc AND COUNT_NO = :cn
        """,
        {'lc': int(location_code), 'cn': int(count_no)},
    )
    return rows[0] if rows else None


def get_stock_count_lines(location_code: int, count_no: int) -> List[Dict[str, Any]]:
    ensure_stock_count_tables()
    im_tbl = _detect_table(['ITEMMASTER', 'itemmaster']) or 'ITEMMASTER'
    name_col = _detect_column(im_tbl, ['ITEMNAME', 'ITEMNAMEENG', 'NAME', 'DESCRIPTION'])
    name_sql = f'im.{name_col}' if name_col else 'NULL'
    im_avg_col = _detect_column(im_tbl, ['AVERAGECOST', 'AVERAGE_COST', 'averagecost'])
    im_avg_sql = f'NVL(im.{im_avg_col}, 0)' if im_avg_col else '0'
    dtl_cols = _stock_count_dtl_extra_columns()
    counted_by_sql = (
        'NVL(d.COUNTED_BY, h.CREATED_BY) AS counted_by'
        if 'COUNTED_BY' in dtl_cols
        else 'h.CREATED_BY AS counted_by'
    )
    avg_cost_expr = (
        f'NVL(d.AVERAGE_COST, {im_avg_sql})'
        if 'AVERAGE_COST' in dtl_cols
        else im_avg_sql
    )
    avg_cost_sql = f'{avg_cost_expr} AS average_cost'
    stock_val_sql = f'ROUND(NVL(d.COUNTED_QTY, 0) * NVL({avg_cost_expr}, 0), 2) AS stock_value'
    system_val_sql = f'ROUND(NVL(d.SYSTEM_QTY, 0) * NVL({avg_cost_expr}, 0), 2) AS system_value'
    has_wh_col = stock_count_dtl_has_warehouse_id()
    wm_tbl = resolve_warehouse_master_table() if has_wh_col else None
    wh_join = ''
    wh_cols = (
        'CAST(NULL AS NUMBER) AS warehouse_id, '
        'CAST(NULL AS VARCHAR2(30)) AS warehouse_code, '
        'CAST(NULL AS VARCHAR2(100)) AS warehouse_name'
    )
    if has_wh_col:
        wh_cols = (
            'd.WAREHOUSE_ID AS warehouse_id, '
            'CAST(NULL AS VARCHAR2(30)) AS warehouse_code, '
            'CAST(NULL AS VARCHAR2(100)) AS warehouse_name'
        )
        if wm_tbl:
            wh_join = f' LEFT JOIN {wm_tbl} wh ON wh.WAREHOUSE_ID = d.WAREHOUSE_ID'
            wh_cols = (
                'd.WAREHOUSE_ID AS warehouse_id, wh.WAREHOUSE_CODE AS warehouse_code, '
                'wh.WAREHOUSE_NAME AS warehouse_name'
            )
    cat_join_sql, cat_select_sql = _stock_count_line_category_parts(im_tbl)
    im_loc_col = _detect_column(im_tbl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    im_join = f'LEFT JOIN {im_tbl} im ON im.ITEMCODE = d.ITEMCODE'
    if im_loc_col:
        im_join += f' AND im.{im_loc_col} = d.LOCATIONCODE'
    return _safe_rows(
        f"""
        SELECT d.LINE_NO AS line_no, d.ITEMCODE AS itemcode, d.BARCODE AS barcode,
               d.UOM AS uom, d.SYSTEM_QTY AS system_qty, d.COUNTED_QTY AS counted_qty,
               d.VARIANCE_QTY AS variance_qty, d.STORAGE_ID AS storage_id,
               {wh_cols},
               d.PDT_SCAN_AT AS pdt_scan_at,
               {counted_by_sql},
               {avg_cost_sql},
               {stock_val_sql},
               {system_val_sql},
               {name_sql} AS item_name,
               {cat_select_sql}
        FROM STOCK_COUNT_DTL d
        INNER JOIN STOCK_COUNT_HDR h
          ON h.LOCATIONCODE = d.LOCATIONCODE AND h.COUNT_NO = d.COUNT_NO
        {im_join}
        {cat_join_sql}
        {wh_join}
        WHERE d.LOCATIONCODE = :lc AND d.COUNT_NO = :cn
        ORDER BY d.LINE_NO
        """,
        {'lc': int(location_code), 'cn': int(count_no)},
    ) or []


def _itemmaster_current_stock_qty(location_code: int, itemcode: int) -> float:
    """Location-level on-hand qty from ITEMMASTER when no warehouse/bin scope."""
    im_tbl = _detect_table(['ITEMMASTER', 'itemmaster', 'ITEM_MASTER'])
    if not im_tbl:
        return 0.0
    im_code = _detect_column(im_tbl, ['ITEMCODE', 'ITEM_CODE', 'itemcode'])
    im_loc = _detect_column(im_tbl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    im_stock = _detect_column(
        im_tbl,
        ['CURRENTSTOCK', 'CURRENT_STOCK', 'currentstock', 'STOCK'],
    )
    if not im_code or not im_loc or not im_stock:
        return 0.0
    rows = _safe_rows(
        f"""
        SELECT NVL(im.{im_stock}, 0) AS q
        FROM {im_tbl} im
        WHERE im.{im_code} = :i AND im.{im_loc} = :lc
        """,
        {'i': int(itemcode), 'lc': int(location_code)},
    )
    if rows:
        return float(rows[0].get('q') or 0)
    return 0.0


def _system_qty(
    location_code: int,
    itemcode: int,
    *,
    warehouse_id: Optional[int],
    storage_id: Optional[int],
) -> float:
    ic = int(itemcode)
    if storage_id and int(storage_id) > 0 and _table_exists(BIN_STOCK_TABLE):
        rows = _safe_rows(
            f'SELECT NVL(QTY, 0) AS q FROM {BIN_STOCK_TABLE} WHERE STORAGE_ID = :s AND ITEMCODE = :i',
            {'s': int(storage_id), 'i': ic},
        )
        if rows:
            return float(rows[0].get('q') or 0)
        return 0.0
    if warehouse_id and int(warehouse_id) > 0 and _table_exists(WAREHOUSE_STOCK_TABLE):
        rows = _safe_rows(
            f"""
            SELECT NVL(QTY, 0) AS q FROM {WAREHOUSE_STOCK_TABLE}
            WHERE WAREHOUSE_ID = :w AND ITEMCODE = :i AND LOCATIONCODE = :lc
            """,
            {'w': int(warehouse_id), 'i': ic, 'lc': int(location_code)},
        )
        if rows:
            return float(rows[0].get('q') or 0)
        return 0.0
    return _itemmaster_current_stock_qty(int(location_code), ic)


def resolve_item_from_scan(
    scan_value: str,
    location_code: int,
) -> Optional[Dict[str, Any]]:
    """Resolve item from barcode / manufacturer id / numeric item code."""
    raw = (scan_value or '').strip()
    if not raw:
        return None
    item = get_item_by_alternate_barcode(raw, location_code)
    if not item:
        item = get_item_by_manufacturer_id(raw, location_code)
    if not item and raw.isdigit():
        item = get_item_by_code(int(raw), location_code)
    if not item:
        return None
    try:
        ic = int(item.get('itemcode') or item.get('ITEMCODE') or 0)
    except (TypeError, ValueError):
        return None
    if ic <= 0:
        return None
    name = str(item.get('itemname') or item.get('ITEMNAME') or item.get('itemnameeng') or '')
    uom = str(item.get('unitofmeasurement') or item.get('UNITOFMEASUREMENT') or item.get('uom') or '')
    return {'itemcode': ic, 'item_name': name, 'uom': uom, 'barcode': raw}


def create_stock_count(
    *,
    location_code: int,
    count_date: Optional[date] = None,
    warehouse_id: Optional[int] = None,
    storage_id: Optional[int] = None,
    remarks: str = '',
    pdt_device_id: str = '',
    created_by: str = '',
) -> Tuple[bool, str, Optional[int]]:
    ensure_stock_count_tables()
    lc = int(location_code)
    cn = next_stock_count_no(lc)
    cd = count_date or date.today()
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO STOCK_COUNT_HDR (
                        LOCATIONCODE, COUNT_NO, COUNT_DATE, WAREHOUSE_ID, STORAGE_ID,
                        STATUS, REMARKS, PDT_DEVICE_ID, CREATED_BY, CREATED_AT
                    ) VALUES (
                        :lc, :cn, :cd, :wid, :sid, 'DRAFT', :rmk, :pdt, :cb, SYSTIMESTAMP
                    )
                    """,
                    {
                        'lc': lc,
                        'cn': cn,
                        'cd': cd,
                        'wid': int(warehouse_id) if warehouse_id else None,
                        'sid': int(storage_id) if storage_id else None,
                        'rmk': (remarks or '')[:500],
                        'pdt': (pdt_device_id or '')[:50],
                        'cb': (created_by or '')[:50],
                    },
                )
                log_stock_count_journal(
                    cur,
                    location_code=lc,
                    count_no=cn,
                    action='CREATE',
                    changed_by=(created_by or '')[:50],
                    source='ERP',
                    warehouse_id=int(warehouse_id) if warehouse_id else None,
                    storage_id=int(storage_id) if storage_id else None,
                    pdt_device_id=(pdt_device_id or '')[:50],
                    remarks=(remarks or '')[:500],
                )
            conn.commit()
        return (True, '', cn)
    except Exception as ex:
        return (False, str(ex), None)


def upsert_stock_count_lines(
    location_code: int,
    count_no: int,
    lines: List[Dict[str, Any]],
    *,
    merge_by_item: bool = True,
    counted_by: Optional[str] = None,
) -> Tuple[bool, str, int]:
    """Add or update count lines (PDT batch). Returns (ok, err, lines_written)."""
    ensure_stock_count_tables()
    _TABLE_COLUMNS_CACHE.pop(STOCK_COUNT_DTL_TABLE.upper(), None)
    hdr = get_stock_count_header(location_code, count_no)
    if not hdr:
        return (False, 'Stock count not found.', 0)
    st = str(hdr.get('status') or '').strip().upper()
    if st in ('POSTED', 'CANCELLED'):
        return (False, f'Cannot edit count in status {st}.', 0)
    lc = int(location_code)
    cn = int(count_no)
    wh_id = hdr.get('warehouse_id')
    try:
        wh_id = int(wh_id) if wh_id is not None else None
    except (TypeError, ValueError):
        wh_id = None
    hdr_sid = hdr.get('storage_id')
    try:
        hdr_sid = int(hdr_sid) if hdr_sid is not None else None
    except (TypeError, ValueError):
        hdr_sid = None

    existing = get_stock_count_lines(lc, cn)
    by_item: Dict[tuple, Dict[str, Any]] = {}

    def _line_merge_key(itemcode: int, warehouse_id: Optional[int], storage_id: Optional[int]) -> tuple:
        try:
            wh_k = int(warehouse_id) if warehouse_id is not None else 0
        except (TypeError, ValueError):
            wh_k = 0
        try:
            sid_k = int(storage_id) if storage_id is not None else 0
        except (TypeError, ValueError):
            sid_k = 0
        return (int(itemcode), wh_k, sid_k)

    if merge_by_item:
        for row in existing:
            try:
                ic = int(row.get('itemcode') or 0)
            except (TypeError, ValueError):
                continue
            if ic <= 0:
                continue
            by_item[_line_merge_key(ic, row.get('warehouse_id'), row.get('storage_id'))] = row
    next_line = max([int(r.get('line_no') or 0) for r in existing], default=0) + 1
    written = 0
    has_wh_col = stock_count_dtl_has_warehouse_id()
    dtl_cols = _stock_count_dtl_extra_columns()
    has_counted_by = 'COUNTED_BY' in dtl_cols
    has_avg_cost = 'AVERAGE_COST' in dtl_cols
    has_stock_val = 'STOCK_VALUE' in dtl_cols
    user_label = (counted_by or '').strip()[:50] or None

    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                for raw in lines or []:
                    if not isinstance(raw, dict):
                        continue
                    scan = str(
                        raw.get('barcode')
                        or raw.get('scan')
                        or raw.get('manufacturer_id')
                        or ''
                    ).strip()
                    itemcode = raw.get('itemcode') or raw.get('item_code')
                    resolved = None
                    if itemcode:
                        try:
                            ic = int(itemcode)
                            resolved = {'itemcode': ic, 'barcode': scan, 'uom': str(raw.get('uom') or '')}
                        except (TypeError, ValueError):
                            resolved = None
                    if not resolved and scan:
                        resolved = resolve_item_from_scan(scan, lc)
                    if not resolved:
                        continue
                    ic = int(resolved['itemcode'])
                    try:
                        counted = float(raw.get('counted_qty') or raw.get('qty') or raw.get('quantity') or 0)
                    except (TypeError, ValueError):
                        counted = 0.0
                    sid = raw.get('storage_id') or hdr_sid
                    try:
                        sid_i = int(sid) if sid is not None and str(sid).strip() != '' else None
                    except (TypeError, ValueError):
                        sid_i = hdr_sid
                    line_wh = raw.get('warehouse_id')
                    if line_wh is None or str(line_wh).strip() == '':
                        line_wh = wh_id
                    try:
                        line_wh_i = int(line_wh) if line_wh is not None and str(line_wh).strip() != '' else None
                    except (TypeError, ValueError):
                        line_wh_i = wh_id
                    sys_q = _system_qty(lc, ic, warehouse_id=line_wh_i, storage_id=sid_i)
                    var_q = round(counted - sys_q, 6)
                    avg_cost = round(
                        float(_journal_average_cost_for_line(cur, lc, {'itemcode': ic}) or 0),
                        6,
                    )
                    stock_value = round(counted * avg_cost, 2)
                    barcode = str(resolved.get('barcode') or scan or '')[:80]
                    uom = str(resolved.get('uom') or raw.get('uom') or '')[:20]
                    merge_key = _line_merge_key(ic, line_wh_i, sid_i)
                    is_update = merge_by_item and merge_key in by_item
                    old_row = by_item.get(merge_key) if is_update else None

                    if is_update:
                        lno = int(by_item[merge_key].get('line_no') or 0)
                        upd_sets = [
                            'COUNTED_QTY = :cq',
                            'SYSTEM_QTY = :sq',
                            'VARIANCE_QTY = :vq',
                            'BARCODE = :bc',
                            'UOM = :uom',
                            'STORAGE_ID = :sid',
                            'PDT_SCAN_AT = SYSTIMESTAMP',
                        ]
                        upd_params: Dict[str, Any] = {
                            'cq': counted,
                            'sq': sys_q,
                            'vq': var_q,
                            'bc': barcode,
                            'uom': uom,
                            'sid': sid_i,
                            'lc': lc,
                            'cn': cn,
                            'ln': lno,
                        }
                        if has_wh_col:
                            upd_sets.insert(-1, 'WAREHOUSE_ID = :wid')
                            upd_params['wid'] = line_wh_i
                        if has_counted_by and user_label:
                            upd_sets.insert(-1, 'COUNTED_BY = :cb')
                            upd_params['cb'] = user_label
                        if has_avg_cost:
                            upd_sets.insert(-1, 'AVERAGE_COST = :ac')
                            upd_params['ac'] = avg_cost
                        if has_stock_val:
                            upd_sets.insert(-1, 'STOCK_VALUE = :sv')
                            upd_params['sv'] = stock_value
                        cur.execute(
                            f"""
                            UPDATE STOCK_COUNT_DTL SET {', '.join(upd_sets)}
                            WHERE LOCATIONCODE = :lc AND COUNT_NO = :cn AND LINE_NO = :ln
                            """,
                            upd_params,
                        )
                        log_stock_count_journal(
                            cur,
                            location_code=lc,
                            count_no=cn,
                            action='UPDATE',
                            line_no=lno,
                            itemcode=ic,
                            old_counted_qty=float(old_row.get('counted_qty') or 0) if old_row else None,
                            new_counted_qty=counted,
                            old_system_qty=float(old_row.get('system_qty') or 0) if old_row else None,
                            new_system_qty=sys_q,
                            old_variance_qty=float(old_row.get('variance_qty') or 0) if old_row else None,
                            new_variance_qty=var_q,
                            barcode=barcode,
                            uom=uom,
                            warehouse_id=line_wh_i,
                            storage_id=sid_i,
                            counted_by=user_label or '',
                            changed_by=user_label or '',
                            source='PDT',
                        )
                    else:
                        lno = next_line
                        next_line += 1
                        ins_cols = [
                            'LOCATIONCODE', 'COUNT_NO', 'LINE_NO', 'ITEMCODE', 'BARCODE', 'UOM',
                            'SYSTEM_QTY', 'COUNTED_QTY', 'VARIANCE_QTY', 'STORAGE_ID',
                        ]
                        ins_vals = [
                            ':lc', ':cn', ':ln', ':ic', ':bc', ':uom',
                            ':sq', ':cq', ':vq', ':sid',
                        ]
                        ins_params: Dict[str, Any] = {
                            'lc': lc,
                            'cn': cn,
                            'ln': lno,
                            'ic': ic,
                            'bc': barcode,
                            'uom': uom,
                            'sq': sys_q,
                            'cq': counted,
                            'vq': var_q,
                            'sid': sid_i,
                        }
                        if has_wh_col:
                            ins_cols.append('WAREHOUSE_ID')
                            ins_vals.append(':wid')
                            ins_params['wid'] = line_wh_i
                        if has_counted_by and user_label:
                            ins_cols.append('COUNTED_BY')
                            ins_vals.append(':cb')
                            ins_params['cb'] = user_label
                        if has_avg_cost:
                            ins_cols.append('AVERAGE_COST')
                            ins_vals.append(':ac')
                            ins_params['ac'] = avg_cost
                        if has_stock_val:
                            ins_cols.append('STOCK_VALUE')
                            ins_vals.append(':sv')
                            ins_params['sv'] = stock_value
                        ins_cols.append('PDT_SCAN_AT')
                        ins_vals.append('SYSTIMESTAMP')
                        cur.execute(
                            f"""
                            INSERT INTO STOCK_COUNT_DTL ({', '.join(ins_cols)})
                            VALUES ({', '.join(ins_vals)})
                            """,
                            ins_params,
                        )
                        by_item[merge_key] = {'line_no': lno}
                        log_stock_count_journal(
                            cur,
                            location_code=lc,
                            count_no=cn,
                            action='INSERT',
                            line_no=lno,
                            itemcode=ic,
                            new_counted_qty=counted,
                            new_system_qty=sys_q,
                            new_variance_qty=var_q,
                            barcode=barcode,
                            uom=uom,
                            warehouse_id=line_wh_i,
                            storage_id=sid_i,
                            counted_by=user_label or '',
                            changed_by=user_label or '',
                            source='PDT',
                        )
                    written += 1
                if written and st == 'DRAFT':
                    cur.execute(
                        """
                        UPDATE STOCK_COUNT_HDR SET STATUS = 'PENDING'
                        WHERE LOCATIONCODE = :lc AND COUNT_NO = :cn AND STATUS = 'DRAFT'
                        """,
                        {'lc': lc, 'cn': cn},
                    )
            conn.commit()
        return (True, '', written)
    except Exception as ex:
        return (False, str(ex), 0)


def update_stock_count_line(
    location_code: int,
    count_no: int,
    line_no: int,
    *,
    counted_qty: float,
    storage_id: Optional[int] = None,
    counted_by: Optional[str] = None,
) -> Tuple[bool, str]:
    """Update one count line by line number."""
    ensure_stock_count_tables()
    _TABLE_COLUMNS_CACHE.pop(STOCK_COUNT_DTL_TABLE.upper(), None)
    hdr = get_stock_count_header(location_code, count_no)
    if not hdr:
        return (False, 'Stock count not found.')
    st = str(hdr.get('status') or '').strip().upper()
    if st in ('POSTED', 'CANCELLED'):
        return (False, f'Cannot edit count in status {st}.')
    lc = int(location_code)
    cn = int(count_no)
    lno = int(line_no)
    if lno <= 0:
        return (False, 'Invalid line number.')
    dtl_cols = _stock_count_dtl_extra_columns()
    has_counted_by = 'COUNTED_BY' in dtl_cols
    has_avg_cost = 'AVERAGE_COST' in dtl_cols
    has_stock_val = 'STOCK_VALUE' in dtl_cols
    has_wh_col = stock_count_dtl_has_warehouse_id()
    user_label = (counted_by or '').strip()[:50] or None
    counted_by_sel = ', COUNTED_BY' if has_counted_by else ''
    try:
        counted = float(counted_qty)
    except (TypeError, ValueError):
        return (False, 'Invalid counted quantity.')
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT ITEMCODE, STORAGE_ID, WAREHOUSE_ID, BARCODE, UOM,
                           COUNTED_QTY, SYSTEM_QTY, VARIANCE_QTY{counted_by_sel}
                    FROM STOCK_COUNT_DTL
                    WHERE LOCATIONCODE = :lc AND COUNT_NO = :cn AND LINE_NO = :ln
                    """,
                    {'lc': lc, 'cn': cn, 'ln': lno},
                )
                row = cur.fetchone()
                if not row:
                    return (False, 'Line not found.')
                ic = int(row[0])
                sid_i = storage_id
                if sid_i is not None and sid_i <= 0:
                    sid_i = None
                line_wh_i = int(row[2]) if row[2] is not None else None
                old_barcode = str(row[3] or '')
                old_uom = str(row[4] or '')
                old_counted = float(row[5] or 0)
                old_system = float(row[6] or 0)
                old_variance = float(row[7] or 0)
                old_counted_by = str(row[8] or '') if has_counted_by and len(row) > 8 else ''
                sys_q = _system_qty(lc, ic, warehouse_id=line_wh_i, storage_id=sid_i)
                var_q = round(counted - sys_q, 6)
                avg_cost = round(
                    float(_journal_average_cost_for_line(cur, lc, {'itemcode': ic}) or 0),
                    6,
                )
                stock_value = round(counted * avg_cost, 2)
                upd_sets = [
                    'COUNTED_QTY = :cq',
                    'SYSTEM_QTY = :sq',
                    'VARIANCE_QTY = :vq',
                    'STORAGE_ID = :sid',
                    'PDT_SCAN_AT = SYSTIMESTAMP',
                ]
                upd_params: Dict[str, Any] = {
                    'cq': counted,
                    'sq': sys_q,
                    'vq': var_q,
                    'sid': sid_i,
                    'lc': lc,
                    'cn': cn,
                    'ln': lno,
                }
                if has_counted_by and user_label:
                    upd_sets.append('COUNTED_BY = :cb')
                    upd_params['cb'] = user_label
                if has_avg_cost:
                    upd_sets.append('AVERAGE_COST = :ac')
                    upd_params['ac'] = avg_cost
                if has_stock_val:
                    upd_sets.append('STOCK_VALUE = :sv')
                    upd_params['sv'] = stock_value
                cur.execute(
                    f"""
                    UPDATE STOCK_COUNT_DTL SET {', '.join(upd_sets)}
                    WHERE LOCATIONCODE = :lc AND COUNT_NO = :cn AND LINE_NO = :ln
                    """,
                    upd_params,
                )
                log_stock_count_journal(
                    cur,
                    location_code=lc,
                    count_no=cn,
                    action='UPDATE',
                    line_no=lno,
                    itemcode=ic,
                    old_counted_qty=old_counted,
                    new_counted_qty=counted,
                    old_system_qty=old_system,
                    new_system_qty=sys_q,
                    old_variance_qty=old_variance,
                    new_variance_qty=var_q,
                    barcode=old_barcode,
                    uom=old_uom,
                    warehouse_id=line_wh_i,
                    storage_id=sid_i,
                    counted_by=user_label or old_counted_by,
                    changed_by=user_label or '',
                    source='ERP',
                )
                if st == 'DRAFT':
                    cur.execute(
                        """
                        UPDATE STOCK_COUNT_HDR SET STATUS = 'PENDING'
                        WHERE LOCATIONCODE = :lc AND COUNT_NO = :cn AND STATUS = 'DRAFT'
                        """,
                        {'lc': lc, 'cn': cn},
                    )
            conn.commit()
        return (True, '')
    except Exception as ex:
        return (False, str(ex))


def delete_stock_count_line(
    location_code: int,
    count_no: int,
    line_no: int,
) -> Tuple[bool, str]:
    """Remove one line from an open stock count."""
    ensure_stock_count_tables()
    hdr = get_stock_count_header(location_code, count_no)
    if not hdr:
        return (False, 'Stock count not found.')
    st = str(hdr.get('status') or '').strip().upper()
    if st in ('POSTED', 'CANCELLED'):
        return (False, f'Cannot edit count in status {st}.')
    lc = int(location_code)
    cn = int(count_no)
    lno = int(line_no)
    if lno <= 0:
        return (False, 'Invalid line number.')
    dtl_cols = _stock_count_dtl_extra_columns()
    has_counted_by = 'COUNTED_BY' in dtl_cols
    counted_by_sel = ', COUNTED_BY' if has_counted_by else ''
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT ITEMCODE, BARCODE, UOM, COUNTED_QTY, SYSTEM_QTY, VARIANCE_QTY,
                           WAREHOUSE_ID, STORAGE_ID{counted_by_sel}
                    FROM STOCK_COUNT_DTL
                    WHERE LOCATIONCODE = :lc AND COUNT_NO = :cn AND LINE_NO = :ln
                    """,
                    {'lc': lc, 'cn': cn, 'ln': lno},
                )
                old = cur.fetchone()
                if not old:
                    return (False, 'Line not found.')
                log_stock_count_journal(
                    cur,
                    location_code=lc,
                    count_no=cn,
                    action='DELETE',
                    line_no=lno,
                    itemcode=int(old[0]),
                    old_counted_qty=float(old[3] or 0),
                    old_system_qty=float(old[4] or 0),
                    old_variance_qty=float(old[5] or 0),
                    barcode=str(old[1] or ''),
                    uom=str(old[2] or ''),
                    warehouse_id=int(old[6]) if old[6] is not None else None,
                    storage_id=int(old[7]) if old[7] is not None else None,
                    counted_by=str(old[8] or '') if has_counted_by and len(old) > 8 else '',
                    source='ERP',
                )
                cur.execute(
                    """
                    DELETE FROM STOCK_COUNT_DTL
                    WHERE LOCATIONCODE = :lc AND COUNT_NO = :cn AND LINE_NO = :ln
                    """,
                    {'lc': lc, 'cn': cn, 'ln': lno},
                )
                if int(cur.rowcount or 0) == 0:
                    return (False, 'Line not found.')
            conn.commit()
        return (True, '')
    except Exception as ex:
        return (False, str(ex))


def _item_inventory_column_maps() -> Dict[str, Any]:
    im_tbl = _detect_table(['ITEMMASTER', 'itemmaster', 'ITEM_MASTER'])
    return {
        'im_tbl': im_tbl,
        'im_code': _detect_column(im_tbl, ['ITEMCODE', 'ITEM_CODE', 'itemcode']) if im_tbl else None,
        'im_loc': _detect_column(im_tbl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode']) if im_tbl else None,
        'im_stock': _detect_column(im_tbl, ['CURRENTSTOCK', 'CURRENT_STOCK', 'currentstock']) if im_tbl else None,
    }


def _stock_count_gl_variance_account() -> str:
    """Offset GL account for inventory count variances (contra to inventory asset)."""
    raw = (os.getenv('STOCK_COUNT_VARIANCE_GL_ACCOUNT') or '').strip()
    if raw:
        return raw[:20]
    try:
        configured = resolve_stk_adj_variance_account_codes() or {}
        if get_stk_adj_opening_stock_mode_enabled():
            opening = str(configured.get('opening') or '').strip()
            if opening:
                return opening[:20]
        variance = str(configured.get('decrease') or configured.get('increase') or '').strip()
        if variance:
            return variance[:20]
    except Exception:
        pass
    return str(DEFAULT_PARTY_ACCOUNTS.get('inventory_adjustment') or '5199')[:20]


def _stock_count_gl_mode_label() -> str:
    try:
        if get_stk_adj_opening_stock_mode_enabled():
            return 'Opening stock'
    except Exception:
        pass
    return 'Stock count'


def _stock_count_gl_code_set() -> set:
    out = set()
    try:
        for row in get_all_chart_of_accounts() or []:
            code = _norm_gl_account_code(row.get('code'))
            if code:
                out.add(code)
    except Exception:
        return set()
    return out


def _validate_stock_count_gl_codes(gl_rows: List[Tuple[str, float, float, str]]) -> Optional[str]:
    coa_codes = _stock_count_gl_code_set()
    if not coa_codes:
        return 'Chart of Accounts is not available. Please open Accounts Configuration and bootstrap GL accounts.'
    missing = []
    for acc, _dr, _cr, _rm in gl_rows or []:
        norm = _norm_gl_account_code(acc)
        if not norm or norm not in coa_codes:
            missing.append(str(acc or '').strip() or '(blank)')
    if missing:
        uniq = ', '.join(sorted(set(missing)))
        return f'Stock count GL account(s) missing from Chart of Accounts: {uniq}.'
    return None


def _item_inventory_account_cur(
    cur: Any,
    location_code: int,
    item_code: int,
    cols: Dict[str, Any],
) -> str:
    im_tbl = cols.get('im_tbl')
    im_code = cols.get('im_code')
    im_loc = cols.get('im_loc')
    im_inv = _detect_column(im_tbl, ['INVENTORYACCOUNT', 'INVENTORY_ACCOUNT', 'inventoryaccount']) if im_tbl else None
    if not im_tbl or not im_code or not im_inv:
        return '1300'
    where_parts = [f'{im_code} = :icode']
    params: Dict[str, Any] = {'icode': int(item_code)}
    if im_loc:
        where_parts.append(f'{im_loc} = :loc')
        params['loc'] = int(location_code)
    try:
        cur.execute(
            f"SELECT TRIM(TO_CHAR(NVL(NULLIF({im_inv}, 0), 1300))) FROM {im_tbl} WHERE {' AND '.join(where_parts)}",
            params,
        )
        row = cur.fetchone()
        if row and row[0] is not None:
            return resolve_item_inventory_gl_account(row[0])
    except Exception:
        pass
    return '1300'


def _post_stock_count_gl_cur(
    cur: Any,
    *,
    location_code: int,
    count_no: int,
    count_date: Any,
    posted_details: List[Dict[str, Any]],
    posted_by: str,
) -> Optional[str]:
    """GL voucher: Dr/Cr inventory accounts vs stock-count variance account."""
    if not ensure_gl_tables():
        return 'GL tables are not available.'
    try:
        from db import ensure_inventory_chart_of_accounts
        ensure_inventory_chart_of_accounts()
    except Exception:
        pass
    inv_value: Dict[str, float] = defaultdict(float)
    cols = _item_inventory_column_maps()
    for row in posted_details:
        try:
            ic = int(row.get('itemcode') or 0)
            var_q = float(row.get('variance') or 0)
        except (TypeError, ValueError):
            continue
        if abs(var_q) < 1e-07:
            continue
        inv_acc = _item_inventory_account_cur(cur, int(location_code), ic, cols)
        avg_cost = float(row.get('average_cost') or 0)
        if avg_cost <= 0:
            from db import _journal_average_cost_for_line
            avg_cost = _journal_average_cost_for_line(cur, int(location_code), row)
        inv_value[inv_acc] += var_q * avg_cost

    total_dr = 0.0
    total_cr = 0.0
    gl_rows: List[Tuple[str, float, float, str]] = []
    for acc, amt in inv_value.items():
        if abs(amt) < 0.005:
            continue
        mode_label = _stock_count_gl_mode_label()
        if amt > 0:
            gl_rows.append((acc, round(amt, 2), 0.0, f'{mode_label} #{count_no} inventory increase'))
            total_dr += amt
        else:
            gl_rows.append((acc, 0.0, round(abs(amt), 2), f'{mode_label} #{count_no} inventory decrease'))
            total_cr += abs(amt)

    variance_acc = _stock_count_gl_variance_account()
    diff = round(total_dr - total_cr, 2)
    if diff > 0.005:
        gl_rows.append((variance_acc, 0.0, diff, f'{_stock_count_gl_mode_label()} #{count_no} offset'))
        total_cr += diff
    elif diff < -0.005:
        gl_rows.append((variance_acc, abs(diff), 0.0, f'{_stock_count_gl_mode_label()} #{count_no} offset'))
        total_dr += abs(diff)

    if not gl_rows:
        return None
    gl_err = _validate_stock_count_gl_codes(gl_rows)
    if gl_err:
        return gl_err

    cd = count_date
    if hasattr(cd, 'strftime'):
        date_fmt = cd.strftime('%d-%b-%Y').upper()
    else:
        date_fmt = datetime.now().strftime('%d-%b-%Y').upper()
    gl_voucher_no = f'SC-{int(location_code)}-{int(count_no)}'[:30]
    gl_ref_no = f'SC-{int(count_no)}'[:50]
    gl_narration = f'{_stock_count_gl_mode_label()} #{count_no} posting'[:500]
    gl_user = (posted_by or '')[:50]
    cur.execute(f'DELETE FROM {GL_DTL_TABLE} WHERE VOUCHER_NO = :vno', {'vno': gl_voucher_no})
    cur.execute(f'DELETE FROM {GL_HDR_TABLE} WHERE VOUCHER_NO = :vno', {'vno': gl_voucher_no})
    cur.execute(
        f"""
        INSERT INTO {GL_HDR_TABLE}
            (VOUCHER_NO, VOUCHER_DATE, REFERENCE_NO, NARRATION, SOURCE, CREATED_BY)
        VALUES
            (:vno, TO_DATE(:vdate, 'DD-MON-YYYY'), :ref, :nar, 'STOCK_COUNT', :usr)
        """,
        {
            'vno': gl_voucher_no,
            'vdate': date_fmt,
            'ref': gl_ref_no,
            'nar': gl_narration,
            'usr': gl_user,
        },
    )
    gl_line_no = 1
    for acc, dr, cr, rm in gl_rows:
        cur.execute(f'SELECT {GL_DTL_SEQ}.NEXTVAL FROM DUAL')
        gl_line_id = cur.fetchone()[0]
        cur.execute(
            f"""
            INSERT INTO {GL_DTL_TABLE}
                (LINE_ID, VOUCHER_NO, LINE_NO, ACCOUNT_CODE, DEBIT, CREDIT, REMARKS)
            VALUES
                (:lid, :vno, :ln, :acc, :dr, :cr, :rm)
            """,
            {
                'lid': gl_line_id,
                'vno': gl_voucher_no,
                'ln': gl_line_no,
                'acc': (acc or '1300')[:20],
                'dr': dr,
                'cr': cr,
                'rm': rm[:250],
            },
        )
        gl_line_no += 1
    return None


def _post_stock_count_accounting_cur(
    cur: Any,
    conn: Any,
    *,
    location_code: int,
    count_no: int,
    hdr: Dict[str, Any],
    posted_details: List[Dict[str, Any]],
    posted_by: str,
) -> Optional[str]:
    """ITEMJOURNAL + GL for a posted stock count."""
    if not posted_details:
        return None
    ensure_itemjournal_surrogate_pk(conn)
    ensure_itemjournal_storage_id_column()
    ensure_itemjournal_warehouse_columns()
    ensure_itemjournal_batch_columns()
    ensure_itemjournal_averagecost_column()
    try:
        repost_itemjournal_stock_count(
            cur, conn, int(location_code), STOCK_COUNT_RESET_NO, int(count_no), posted_details,
        )
    except Exception as ex:
        return f'Item journal: {ex}'
    return _post_stock_count_gl_cur(
        cur,
        location_code=int(location_code),
        count_no=int(count_no),
        count_date=hdr.get('count_date'),
        posted_details=posted_details,
        posted_by=posted_by,
    )


def _apply_itemmaster_and_alternate_from_count_post_cur(
    cur: Any,
    location_code: int,
    posted_lines: List[Dict[str, Any]],
) -> List[str]:
    """
    After bin/warehouse post: apply line variances to ITEMMASTER.CURRENTSTOCK.
    """
    cols = _item_inventory_column_maps()
    im_tbl = cols.get('im_tbl')
    im_code = cols.get('im_code')
    im_stock = cols.get('im_stock')
    if not im_tbl or not im_code or not im_stock:
        return []

    item_delta: Dict[int, float] = defaultdict(float)
    for row in posted_lines:
        try:
            ic = int(row.get('itemcode') or 0)
        except (TypeError, ValueError):
            continue
        if ic <= 0:
            continue
        try:
            var_q = float(row.get('variance') or 0)
        except (TypeError, ValueError):
            var_q = 0.0
        if abs(var_q) < 1e-07:
            continue
        item_delta[ic] += var_q

    if not item_delta:
        return []

    lc = int(location_code)
    errors: List[str] = []
    im_loc = cols.get('im_loc')
    for item_code, delta_qty in item_delta.items():
        where_im = [f'{im_code} = :icode']
        im_params: Dict[str, Any] = {'icode': int(item_code)}
        if im_loc:
            where_im.append(f'{im_loc} = :loc')
            im_params['loc'] = lc
        cur.execute(
            f'SELECT NVL({im_stock}, 0) FROM {im_tbl} WHERE {" AND ".join(where_im)}',
            im_params,
        )
        row = cur.fetchone()
        if not row:
            errors.append(f'Item {item_code}: not found in ITEMMASTER.')
            continue
        new_stock = float(row[0] or 0) + float(delta_qty)
        up = dict(im_params)
        up['nstock'] = new_stock
        cur.execute(
            f'UPDATE {im_tbl} SET {im_stock} = :nstock WHERE {" AND ".join(where_im)}',
            up,
        )
    return errors


def _apply_itemmaster_and_alternate_from_count_post(
    location_code: int,
    posted_lines: List[Dict[str, Any]],
    *,
    cur: Optional[Any] = None,
) -> List[str]:
    if cur is not None:
        return _apply_itemmaster_and_alternate_from_count_post_cur(cur, location_code, posted_lines)
    try:
        with _get_connection() as conn:
            with conn.cursor() as c:
                errs = _apply_itemmaster_and_alternate_from_count_post_cur(c, location_code, posted_lines)
            conn.commit()
        return errs
    except Exception as ex:
        _LOG.error('_apply_itemmaster_and_alternate_from_count_post: %s', ex)
        return [str(ex)]


def set_stock_count_status(
    location_code: int,
    count_no: int,
    status: str,
    *,
    posted_by: str = '',
) -> Tuple[bool, str]:
    ensure_stock_count_tables()
    st = (status or '').strip().upper()
    if st not in STOCK_COUNT_STATUSES:
        return (False, 'Invalid status.')
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                if st == 'POSTED':
                    cur.execute(
                        """
                        UPDATE STOCK_COUNT_HDR SET
                            STATUS = 'POSTED', POSTED_BY = :pb, POSTED_AT = SYSTIMESTAMP
                        WHERE LOCATIONCODE = :lc AND COUNT_NO = :cn
                        """,
                        {'pb': (posted_by or '')[:50], 'lc': int(location_code), 'cn': int(count_no)},
                    )
                else:
                    cur.execute(
                        """
                        UPDATE STOCK_COUNT_HDR SET STATUS = :st
                        WHERE LOCATIONCODE = :lc AND COUNT_NO = :cn
                        """,
                        {'st': st, 'lc': int(location_code), 'cn': int(count_no)},
                    )
            conn.commit()
        return (True, '')
    except Exception as ex:
        return (False, str(ex))


def post_stock_count_to_inventory(
    location_code: int,
    count_no: int,
    *,
    posted_by: str = '',
    only_nonzero_variance: bool = False,
) -> Tuple[bool, str, Dict[str, Any]]:
    """Post count: bin/warehouse stock, ITEMMASTER, alternate UOM, ITEMJOURNAL, GL; mark POSTED."""
    ensure_stock_count_tables()
    hdr = get_stock_count_header(location_code, count_no)
    if not hdr:
        return (False, 'Stock count not found.', {})
    st = str(hdr.get('status') or '').strip().upper()
    if st == 'POSTED':
        return (False, 'This count is already posted.', {})
    if st == 'CANCELLED':
        return (False, 'Cancelled count cannot be posted.', {})
    lines = get_stock_count_lines(int(location_code), int(count_no))
    if not lines:
        return (False, 'No lines to post.', {})

    lc = int(location_code)
    cn = int(count_no)
    try:
        hdr_wh_id = int(hdr.get('warehouse_id') or 0)
    except (TypeError, ValueError):
        hdr_wh_id = 0
    hdr_wh_id = hdr_wh_id if hdr_wh_id > 0 else None
    loc_key = resolve_warehouse_loc_key_for_location_code(lc) or str(lc)
    user = (posted_by or '')[:200]
    updated = 0
    errors: List[str] = []
    posted_lines: List[Dict[str, Any]] = []
    posted_details: List[Dict[str, Any]] = []

    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                ensure_warehouse_stock_table_cur(cur)
                for ln in lines:
                    try:
                        ic = int(ln.get('itemcode') or 0)
                    except (TypeError, ValueError):
                        continue
                    if ic <= 0:
                        continue
                    try:
                        counted = float(ln.get('counted_qty') or 0)
                    except (TypeError, ValueError):
                        counted = 0.0
                    try:
                        variance = float(ln.get('variance_qty') or 0)
                    except (TypeError, ValueError):
                        variance = 0.0
                    sid = ln.get('storage_id') or hdr.get('storage_id')
                    try:
                        sid_i = int(sid) if sid is not None and str(sid).strip() != '' else 0
                    except (TypeError, ValueError):
                        sid_i = 0
                    line_wh = ln.get('warehouse_id') or hdr_wh_id
                    try:
                        line_wh_i = int(line_wh) if line_wh is not None and str(line_wh).strip() != '' else 0
                    except (TypeError, ValueError):
                        line_wh_i = 0
                    stock_err: Optional[str] = None
                    effective_variance = variance
                    if sid_i > 0:
                        cur.execute(
                            f'SELECT NVL(QTY, 0) FROM {BIN_STOCK_TABLE} WHERE STORAGE_ID = :s AND ITEMCODE = :i',
                            {'s': sid_i, 'i': ic},
                        )
                        brow = cur.fetchone()
                        cur_q = float(brow[0] or 0) if brow else 0.0
                        effective_variance = counted - cur_q
                        if only_nonzero_variance and abs(effective_variance) < 0.0005:
                            continue
                        if abs(effective_variance) < 1e-09:
                            continue
                        stock_err = apply_bin_stock_delta_cur(
                            cur, loc_key, sid_i, ic, effective_variance, lc, updated_by=user,
                        )
                    elif line_wh_i > 0:
                        if only_nonzero_variance and abs(variance) < 0.0005:
                            continue
                        if abs(variance) < 0.0005:
                            continue
                        effective_variance = variance
                        stock_err = apply_warehouse_stock_delta_cur(
                            cur, lc, line_wh_i, ic, effective_variance, updated_by=user,
                        )
                    else:
                        errors.append(f'Item {ic}: no warehouse or bin on count.')
                        continue
                    if stock_err:
                        errors.append(f'Item {ic}: {stock_err}')
                        continue
                    updated += 1
                    try:
                        line_no = int(ln.get('line_no') or 0)
                    except (TypeError, ValueError):
                        line_no = 0
                    wh_code = ''
                    if line_wh_i > 0:
                        try:
                            wh_row = get_warehouse_master_by_id(line_wh_i)
                            if wh_row:
                                wh_code = str(wh_row.get('warehouse_code') or '').strip()[:30]
                        except Exception:
                            pass
                    row_detail = {
                        'line_no': line_no,
                        'lineno': line_no,
                        'itemcode': ic,
                        'variance': effective_variance,
                        'uom': ln.get('uom') or 'NOS',
                        'warehouse_id': line_wh_i if line_wh_i > 0 else None,
                        'storage_id': sid_i if sid_i > 0 else None,
                        'warehouse_code': wh_code,
                    }
                    posted_lines.append({
                        'itemcode': ic,
                        'variance': effective_variance,
                        'uom': row_detail['uom'],
                    })
                    posted_details.append(row_detail)

                if errors and updated == 0:
                    conn.rollback()
                    return (False, '; '.join(errors[:5]), {'updated': 0, 'errors': errors})

                if posted_lines:
                    im_errors = _apply_itemmaster_and_alternate_from_count_post_cur(cur, lc, posted_lines)
                    if im_errors:
                        conn.rollback()
                        return (False, '; '.join(im_errors[:5]), {'updated': 0, 'errors': im_errors})

                if posted_details:
                    acct_err = _post_stock_count_accounting_cur(
                        cur,
                        conn,
                        location_code=lc,
                        count_no=cn,
                        hdr=hdr,
                        posted_details=posted_details,
                        posted_by=user,
                    )
                    if acct_err:
                        conn.rollback()
                        return (False, acct_err, {'updated': 0, 'errors': [acct_err]})

                cur.execute(
                    """
                    UPDATE STOCK_COUNT_HDR SET
                        STATUS = 'POSTED', POSTED_BY = :pb, POSTED_AT = SYSTIMESTAMP
                    WHERE LOCATIONCODE = :lc AND COUNT_NO = :cn
                    """,
                    {'pb': user[:50], 'lc': lc, 'cn': cn},
                )
                log_stock_count_journal(
                    cur,
                    location_code=lc,
                    count_no=cn,
                    action='POST',
                    changed_by=user[:50],
                    source='ERP',
                    remarks=f'Posted {updated} line(s)',
                )
            conn.commit()
    except Exception as ex:
        _LOG.exception('post_stock_count_to_inventory: %s', ex)
        return (False, str(ex), {'updated': 0, 'errors': [str(ex)]})

    msg = (
        f'Posted {updated} line(s): stock, ITEMMASTER, alternate UOM, item journal, and GL.'
    )
    if errors:
        msg = f'{msg} Some line errors: {"; ".join(errors[:3])}'
    return (True, msg, {'updated': updated, 'errors': errors})


def update_stock_count_pdt_device(
    location_code: int,
    count_no: int,
    device_id: str,
) -> None:
    """Record PDT device id on header (best-effort)."""
    d = (device_id or '').strip()[:50]
    if not d:
        return
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE STOCK_COUNT_HDR SET PDT_DEVICE_ID = :d
                    WHERE LOCATIONCODE = :lc AND COUNT_NO = :cn
                    """,
                    {'d': d, 'lc': int(location_code), 'cn': int(count_no)},
                )
            conn.commit()
    except Exception:
        pass


def delete_stock_count(location_code: int, count_no: int) -> Tuple[bool, str]:
    hdr = get_stock_count_header(location_code, count_no)
    if not hdr:
        return (False, 'Not found.')
    st = str(hdr.get('status') or '').strip().upper()
    if st == 'POSTED':
        return (False, 'Posted counts cannot be deleted.')
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                log_stock_count_journal(
                    cur,
                    location_code=int(location_code),
                    count_no=int(count_no),
                    action='DELETE_HDR',
                    changed_by=str(hdr.get('created_by') or '')[:50],
                    source='ERP',
                    remarks='Stock count session deleted',
                )
                cur.execute(
                    'DELETE FROM STOCK_COUNT_DTL WHERE LOCATIONCODE = :lc AND COUNT_NO = :cn',
                    {'lc': int(location_code), 'cn': int(count_no)},
                )
                cur.execute(
                    'DELETE FROM STOCK_COUNT_HDR WHERE LOCATIONCODE = :lc AND COUNT_NO = :cn',
                    {'lc': int(location_code), 'cn': int(count_no)},
                )
            conn.commit()
        return (True, '')
    except Exception as ex:
        return (False, str(ex))
