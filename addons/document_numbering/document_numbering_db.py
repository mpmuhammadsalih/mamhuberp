"""Document numbering series (tenant DB) — table DOC_NUMBER_SERIES."""
from __future__ import annotations

from datetime import datetime
import re
from typing import Any, Dict, List, Optional, Tuple

from db import (
    _detect_column,
    _detect_table,
    _get_connection,
    _safe_rows,
    _table_exists,
)

DOC_NUMBER_SERIES_TABLE = 'DOC_NUMBER_SERIES'
DOC_NUMBER_SERIES_SEQ = 'DOC_NUMBER_SERIES_SEQ'

# Document types for separate sales number pools (each has its own DOC_NUMBER_SERIES row).
DOC_TYPE_SALES_INVOICE = 'SALES_INVOICE'
DOC_TYPE_SALES_RETURN = 'SALES_RETURN'
DOC_TYPE_POS_INVOICE = 'POS_INVOICE'
DOC_TYPE_SALES_ORDER = 'SALES_ORDER'
DOC_TYPE_QUOTATION = 'QUOTATION'
# Legacy default when doc_type is omitted.
BILLNO_DOC_TYPE = DOC_TYPE_SALES_INVOICE

_SALES_SERIES_DEFAULT_PREFIXES: Dict[str, Tuple[str, int]] = {
    DOC_TYPE_SALES_INVOICE: ('SI-', 6),
    DOC_TYPE_SALES_RETURN: ('SR-', 6),
    DOC_TYPE_POS_INVOICE: ('POS-', 6),
    DOC_TYPE_SALES_ORDER: ('SO-', 6),
    DOC_TYPE_QUOTATION: ('QT-', 6),
}

_PURCHASE_SERIES_DEFAULT_PREFIXES: Dict[str, Tuple[str, int]] = {
    'LPO': ('PO-', 6),
    'GRN': ('GRN-', 6),
    'PURCHASE_INVOICE': ('PI-', 6),
    'RETURN_ORDER': ('PR-', 6),
    'PURCHASE_RETURN': ('PR-', 6),
}

# Default series seeded on first open (company-wide, RESETNO=1).
DEFAULT_DOCUMENT_SERIES: List[Dict[str, Any]] = [
    {'doc_type': DOC_TYPE_SALES_INVOICE, 'doc_label': 'Sales Invoice', 'module_name': 'Sales', 'prefix': 'SI-', 'padding': 6},
    {'doc_type': DOC_TYPE_SALES_ORDER, 'doc_label': 'Sales Order', 'module_name': 'Sales', 'prefix': 'SO-', 'padding': 6},
    {'doc_type': DOC_TYPE_SALES_RETURN, 'doc_label': 'Sales Return', 'module_name': 'Sales', 'prefix': 'SR-', 'padding': 6},
    {'doc_type': 'SALES_CREDIT_NOTE', 'doc_label': 'Credit Note', 'module_name': 'Sales', 'prefix': '', 'padding': 0},
    {'doc_type': DOC_TYPE_POS_INVOICE, 'doc_label': 'POS Invoice', 'module_name': 'Sales', 'prefix': 'POS-', 'padding': 6},
    {'doc_type': DOC_TYPE_QUOTATION, 'doc_label': 'Quotation', 'module_name': 'Sales', 'prefix': 'QT-', 'padding': 6},
    {'doc_type': 'LPO', 'doc_label': 'Purchase Order (LPO)', 'module_name': 'Purchase', 'prefix': 'PO-', 'padding': 6},
    {'doc_type': 'LPO_DRAFT', 'doc_label': 'LPO Draft Cart', 'module_name': 'Purchase', 'prefix': '', 'padding': 0},
    {'doc_type': 'GRN', 'doc_label': 'Goods Receipt (GRN)', 'module_name': 'Purchase', 'prefix': 'GRN-', 'padding': 6},
    {'doc_type': 'PURCHASE_INVOICE', 'doc_label': 'Purchase Invoice', 'module_name': 'Purchase', 'prefix': '', 'padding': 0},
    {'doc_type': 'PURCHASE_RETURN', 'doc_label': 'Purchase Return', 'module_name': 'Purchase', 'prefix': 'PR-', 'padding': 6},
    {'doc_type': 'RETURN_ORDER', 'doc_label': 'Return Order (Draft)', 'module_name': 'Purchase', 'prefix': 'PR-', 'padding': 6},
    {'doc_type': 'DEBIT_NOTE_REQUEST', 'doc_label': 'Debit Note Request', 'module_name': 'Purchase', 'prefix': '', 'padding': 0},
    {'doc_type': 'DEBIT_NOTE', 'doc_label': 'Debit Note', 'module_name': 'Purchase', 'prefix': '', 'padding': 0},
    {'doc_type': 'STOCK_ADJUSTMENT', 'doc_label': 'Stock Adjustment', 'module_name': 'Inventory', 'prefix': 'SA-', 'padding': 6},
    {'doc_type': 'STOCK_TRANSFER', 'doc_label': 'Stock Transfer', 'module_name': 'Inventory', 'prefix': 'ST-', 'padding': 6},
    {'doc_type': 'REPACK', 'doc_label': 'Repacking', 'module_name': 'Inventory', 'prefix': 'RP-', 'padding': 6},
    {'doc_type': 'STOCK_COUNT', 'doc_label': 'Stock Count', 'module_name': 'Inventory', 'prefix': '', 'padding': 0},
    {'doc_type': 'GL_JOURNAL', 'doc_label': 'GL Journal Voucher', 'module_name': 'Accounts', 'prefix': 'JV', 'padding': 4, 'use_date_prefix': 'Y'},
    {'doc_type': 'CASH_PAYMENT', 'doc_label': 'Cash Payment Voucher', 'module_name': 'Accounts', 'prefix': 'CPV', 'padding': 4, 'use_date_prefix': 'Y'},
    {'doc_type': 'RECEIPT_VOUCHER', 'doc_label': 'Receipt Voucher', 'module_name': 'Accounts', 'prefix': 'RV', 'padding': 4, 'use_date_prefix': 'Y'},
    {'doc_type': 'PAYMENT_VOUCHER', 'doc_label': 'Payment Voucher', 'module_name': 'Accounts', 'prefix': 'PV', 'padding': 4, 'use_date_prefix': 'Y'},
    {'doc_type': 'CONTRA_VOUCHER', 'doc_label': 'Contra Voucher', 'module_name': 'Accounts', 'prefix': 'CV', 'padding': 4, 'use_date_prefix': 'Y'},
    {'doc_type': 'SETTLEMENT', 'doc_label': 'Settlement Pending No.', 'module_name': 'Accounts', 'prefix': '', 'padding': 0},
]

# Map doc_type → (table candidates, number column candidates, optional location/reset columns)
_DOC_MAX_SOURCES: Dict[str, Dict[str, Any]] = {
    'SALES_INVOICE': {'tables': ['BILLHDR'], 'no_cols': ['BILLNO']},
    'SALES_ORDER': {'tables': ['QUATATIONBILLHDR', 'QUATATIONHDR'], 'no_cols': ['BILLNO']},
    'SALES_RETURN': {'tables': ['BILLHDR'], 'no_cols': ['BILLNO']},
    'POS_INVOICE': {'tables': ['BILLHDR'], 'no_cols': ['BILLNO']},
    'QUOTATION': {'tables': ['QUATATIONBILLHDR'], 'no_cols': ['BILLNO']},
    'SALES_CREDIT_NOTE': {'tables': ['CRHDR'], 'no_cols': ['CRNO']},
    'LPO': {'tables': ['LPOHDR'], 'no_cols': ['LPONO']},
    'LPO_DRAFT': {'tables': ['TEMPLPOHDR'], 'no_cols': ['TEMPLPONO']},
    'GRN': {'tables': ['RECEIPTHDR'], 'no_cols': ['RECEIPTNO']},
    'PURCHASE_INVOICE': {'tables': ['PURCHASEINVOICEHDR'], 'no_cols': ['PURCHASEINVOICENO', 'INVOICENO']},
    'PURCHASE_RETURN': {'tables': ['RETURNHDR'], 'no_cols': ['GOODSRETURNNO']},
    'RETURN_ORDER': {'tables': ['TEMPRETURNHDR'], 'no_cols': ['GOODSRETURNNO']},
    'DEBIT_NOTE_REQUEST': {'tables': ['TEMPDNHDR'], 'no_cols': ['DNREQNO']},
    'DEBIT_NOTE': {'tables': ['DRHDR'], 'no_cols': ['DRNO']},
    'STOCK_ADJUSTMENT': {'tables': ['STKADJHDR'], 'no_cols': ['ADJNO']},
    'STOCK_TRANSFER': {'tables': ['STKTRFHDR', 'STOCKTRANSFERHDR'], 'no_cols': ['TRANSFERNO', 'STOCKTRANSFERNO']},
    'REPACK': {'tables': ['REPACKHDR'], 'no_cols': ['REPACKNO']},
    'SETTLEMENT': {'tables': ['TBLSETTLEMENT', 'SETTLEMENTHDR'], 'no_cols': ['PENDINGNO', 'SETTLEMENTNO']},
}


def _yn(val: Any, default: str = 'N') -> str:
    return 'Y' if str(val or '').strip().upper() in ('Y', '1', 'TRUE', 'YES', 'ON') else 'N'


def _norm_loc(val: Any) -> Optional[int]:
    if val is None or str(val).strip() == '':
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _norm_int(val: Any, default: int = 0) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def ensure_doc_number_series_table() -> bool:
    from db import _TABLE_EXISTS_CACHE, _get_count

    if _table_exists(DOC_NUMBER_SERIES_TABLE):
        return True
    try:
        exists = _get_count(
            'SELECT COUNT(*) AS cnt FROM user_tables WHERE table_name = :table_name',
            {'table_name': DOC_NUMBER_SERIES_TABLE},
        ) > 0
        if exists:
            _TABLE_EXISTS_CACHE[DOC_NUMBER_SERIES_TABLE] = True
            return True
    except Exception:
        pass
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    CREATE TABLE {DOC_NUMBER_SERIES_TABLE} (
                        SERIES_ID        NUMBER NOT NULL,
                        DOC_TYPE         VARCHAR2(40) NOT NULL,
                        DOC_LABEL        VARCHAR2(120) NOT NULL,
                        MODULE_NAME      VARCHAR2(40),
                        PREFIX           VARCHAR2(30),
                        SUFFIX           VARCHAR2(30),
                        STARTING_NO      NUMBER DEFAULT 1 NOT NULL,
                        LAST_NO_USED     NUMBER DEFAULT 0 NOT NULL,
                        INCREMENT_BY     NUMBER DEFAULT 1 NOT NULL,
                        PADDING          NUMBER DEFAULT 0 NOT NULL,
                        ALLOW_MANUAL     VARCHAR2(1) DEFAULT 'N' NOT NULL,
                        USE_DATE_PREFIX  VARCHAR2(1) DEFAULT 'N' NOT NULL,
                        DATE_FORMAT      VARCHAR2(20) DEFAULT 'YYYYMMDD',
                        LOCATIONCODE     NUMBER,
                        RESETNO          NUMBER DEFAULT 1,
                        IS_ACTIVE        VARCHAR2(1) DEFAULT 'Y' NOT NULL,
                        NOTES            VARCHAR2(500),
                        CREATED_BY       VARCHAR2(100),
                        CREATED_DATE     DATE DEFAULT SYSDATE,
                        MODIFIED_BY      VARCHAR2(100),
                        MODIFIED_DATE    DATE,
                        CONSTRAINT PK_DOC_NUMBER_SERIES PRIMARY KEY (SERIES_ID),
                        CONSTRAINT UQ_DOC_NUMBER_SERIES UNIQUE (DOC_TYPE, LOCATIONCODE, RESETNO)
                    )
                    """
                )
                try:
                    cur.execute(
                        f'CREATE SEQUENCE {DOC_NUMBER_SERIES_SEQ} START WITH 1 INCREMENT BY 1 NOCACHE'
                    )
                except Exception as seq_ex:
                    if 'ORA-00955' not in str(seq_ex).upper():
                        raise
            conn.commit()
        _TABLE_EXISTS_CACHE[DOC_NUMBER_SERIES_TABLE] = True
        return True
    except Exception as ex:
        if 'ORA-00955' in str(ex).upper():
            _TABLE_EXISTS_CACHE[DOC_NUMBER_SERIES_TABLE] = True
            return True
        print(f'[ensure_doc_number_series_table] {ex}')
        return False


def _next_series_id(cur: Any) -> int:
    cur.execute(f'SELECT {DOC_NUMBER_SERIES_SEQ}.NEXTVAL FROM DUAL')
    row = cur.fetchone()
    return int((row or [0])[0])


def seed_default_document_series(user: str = 'system') -> int:
    """Insert missing default rows; returns count inserted."""
    ensure_doc_number_series_table()
    if not _table_exists(DOC_NUMBER_SERIES_TABLE):
        return 0
    inserted = 0
    usr = (user or 'system')[:100]
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                for spec in DEFAULT_DOCUMENT_SERIES:
                    doc_type = str(spec['doc_type']).upper()
                    cur.execute(
                        f"""
                        SELECT COUNT(*) FROM {DOC_NUMBER_SERIES_TABLE}
                        WHERE DOC_TYPE = :dt AND LOCATIONCODE IS NULL AND RESETNO = 1
                        """,
                        {'dt': doc_type},
                    )
                    if int((cur.fetchone() or [0])[0] or 0) > 0:
                        continue
                    sid = _next_series_id(cur)
                    cur.execute(
                        f"""
                        INSERT INTO {DOC_NUMBER_SERIES_TABLE}
                        (SERIES_ID, DOC_TYPE, DOC_LABEL, MODULE_NAME, PREFIX, SUFFIX,
                         STARTING_NO, LAST_NO_USED, INCREMENT_BY, PADDING,
                         ALLOW_MANUAL, USE_DATE_PREFIX, DATE_FORMAT,
                         LOCATIONCODE, RESETNO, IS_ACTIVE, CREATED_BY, CREATED_DATE)
                        VALUES
                        (:id, :dt, :lbl, :module_nm, :pfx, :sfx,
                         1, 0, 1, :pad,
                         'N', :udp, 'YYYYMMDD',
                         NULL, 1, 'Y', :usr, SYSDATE)
                        """,
                        {
                            'id': sid,
                            'dt': doc_type,
                            'lbl': spec['doc_label'],
                            'module_nm': spec.get('module_name') or '',
                            'pfx': spec.get('prefix') or '',
                            'sfx': spec.get('suffix') or '',
                            'pad': _norm_int(spec.get('padding'), 0),
                            'udp': _yn(spec.get('use_date_prefix'), 'N'),
                            'usr': usr,
                        },
                    )
                    inserted += 1
            conn.commit()
    except Exception as ex:
        print(f'[seed_default_document_series] {ex}')
    ensure_distinct_sales_series_prefixes()
    ensure_distinct_purchase_series_prefixes()
    return inserted


def ensure_distinct_purchase_series_prefixes() -> int:
    """Set recommended prefixes on purchase series rows when PREFIX is still blank."""
    ensure_doc_number_series_table()
    if not _table_exists(DOC_NUMBER_SERIES_TABLE):
        return 0
    updated = 0
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                for doc_type, (pfx, pad) in _PURCHASE_SERIES_DEFAULT_PREFIXES.items():
                    cur.execute(
                        f"""
                        UPDATE {DOC_NUMBER_SERIES_TABLE}
                        SET PREFIX = :pfx, PADDING = :pad, MODIFIED_DATE = SYSDATE
                        WHERE DOC_TYPE = :dt
                          AND LOCATIONCODE IS NULL
                          AND RESETNO = 1
                          AND (PREFIX IS NULL OR TRIM(PREFIX) = '')
                        """,
                        {'dt': doc_type, 'pfx': pfx[:30], 'pad': max(0, int(pad))},
                    )
                    updated += int(cur.rowcount or 0)
            conn.commit()
    except Exception as ex:
        print(f'[ensure_distinct_purchase_series_prefixes] {ex}')
    return updated


def ensure_distinct_sales_series_prefixes() -> int:
    """Set recommended prefixes on sales series rows when PREFIX is still blank."""
    ensure_doc_number_series_table()
    if not _table_exists(DOC_NUMBER_SERIES_TABLE):
        return 0
    updated = 0
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                for doc_type, (pfx, pad) in _SALES_SERIES_DEFAULT_PREFIXES.items():
                    cur.execute(
                        f"""
                        UPDATE {DOC_NUMBER_SERIES_TABLE}
                        SET PREFIX = :pfx, PADDING = :pad, MODIFIED_DATE = SYSDATE
                        WHERE DOC_TYPE = :dt
                          AND LOCATIONCODE IS NULL
                          AND RESETNO = 1
                          AND (PREFIX IS NULL OR TRIM(PREFIX) = '')
                        """,
                        {'dt': doc_type, 'pfx': pfx[:30], 'pad': max(0, int(pad))},
                    )
                    updated += int(cur.rowcount or 0)
            conn.commit()
    except Exception as ex:
        print(f'[ensure_distinct_sales_series_prefixes] {ex}')
    return updated


def list_document_series(
    *,
    module_name: Optional[str] = None,
    location_code: Optional[int] = None,
    include_inactive: bool = True,
) -> List[Dict[str, Any]]:
    ensure_doc_number_series_table()
    seed_default_document_series()
    if not _table_exists(DOC_NUMBER_SERIES_TABLE):
        return []
    where = ['1=1']
    params: Dict[str, Any] = {}
    if module_name:
        where.append('UPPER(TRIM(MODULE_NAME)) = :module_nm')
        params['module_nm'] = str(module_name).strip().upper()
    if location_code is not None:
        where.append('(LOCATIONCODE IS NULL OR LOCATIONCODE = :loc)')
        params['loc'] = int(location_code)
    if not include_inactive:
        where.append("NVL(UPPER(TRIM(IS_ACTIVE)), 'Y') = 'Y'")
    rows = _safe_rows(
        f"""
        SELECT SERIES_ID, DOC_TYPE, DOC_LABEL, MODULE_NAME, PREFIX, SUFFIX,
               STARTING_NO, LAST_NO_USED, INCREMENT_BY, PADDING,
               ALLOW_MANUAL, USE_DATE_PREFIX, DATE_FORMAT,
               LOCATIONCODE, RESETNO, IS_ACTIVE, NOTES,
               CREATED_BY, MODIFIED_BY
        FROM {DOC_NUMBER_SERIES_TABLE}
        WHERE {' AND '.join(where)}
        ORDER BY MODULE_NAME, DOC_LABEL, LOCATIONCODE NULLS FIRST, RESETNO
        """,
        params,
    ) or []
    out: List[Dict[str, Any]] = []
    for r in rows:
        row = _row_to_dict(r)
        row['next_preview'] = format_document_no(row, row.get('next_no'))
        out.append(row)
    return out


def _row_to_dict(r: Dict[str, Any]) -> Dict[str, Any]:
    last = _norm_int(r.get('last_no_used'), 0)
    start = max(1, _norm_int(r.get('starting_no'), 1))
    inc = max(1, _norm_int(r.get('increment_by'), 1))
    next_no = last + inc if last >= start else start
    return {
        'series_id': _norm_int(r.get('series_id'), 0),
        'doc_type': str(r.get('doc_type') or '').strip().upper(),
        'doc_label': str(r.get('doc_label') or '').strip(),
        'module_name': str(r.get('module_name') or '').strip(),
        'prefix': str(r.get('prefix') or ''),
        'suffix': str(r.get('suffix') or ''),
        'starting_no': start,
        'last_no_used': last,
        'increment_by': inc,
        'padding': max(0, _norm_int(r.get('padding'), 0)),
        'allow_manual': _yn(r.get('allow_manual'), 'N'),
        'use_date_prefix': _yn(r.get('use_date_prefix'), 'N'),
        'date_format': str(r.get('date_format') or 'YYYYMMDD').strip() or 'YYYYMMDD',
        'locationcode': r.get('locationcode'),
        'resetno': _norm_int(r.get('resetno'), 1),
        'is_active': _yn(r.get('is_active'), 'Y'),
        'notes': str(r.get('notes') or ''),
        'next_no': next_no,
    }


def get_document_series(series_id: int) -> Optional[Dict[str, Any]]:
    ensure_doc_number_series_table()
    try:
        sid = int(series_id)
    except (TypeError, ValueError):
        return None
    rows = _safe_rows(
        f"""
        SELECT SERIES_ID, DOC_TYPE, DOC_LABEL, MODULE_NAME, PREFIX, SUFFIX,
               STARTING_NO, LAST_NO_USED, INCREMENT_BY, PADDING,
               ALLOW_MANUAL, USE_DATE_PREFIX, DATE_FORMAT,
               LOCATIONCODE, RESETNO, IS_ACTIVE, NOTES
        FROM {DOC_NUMBER_SERIES_TABLE}
        WHERE SERIES_ID = :id
        """,
        {'id': sid},
    )
    if not rows:
        return None
    row = _row_to_dict(rows[0])
    row['next_preview'] = format_document_no(row, row.get('next_no'))
    return row


def get_document_series_by_type(
    doc_type: str,
    *,
    location_code: Optional[int] = None,
    reset_no: int = 1,
) -> Optional[Dict[str, Any]]:
    ensure_doc_number_series_table()
    seed_default_document_series()
    dt = str(doc_type or '').strip().upper()
    if not dt:
        return None
    params: Dict[str, Any] = {'dt': dt, 'rn': int(reset_no or 1)}
    loc_clause = 'LOCATIONCODE IS NULL'
    if location_code is not None:
        loc_clause = '(LOCATIONCODE = :loc OR LOCATIONCODE IS NULL)'
        params['loc'] = int(location_code)
    rows = _safe_rows(
        f"""
        SELECT * FROM (
            SELECT SERIES_ID, DOC_TYPE, DOC_LABEL, MODULE_NAME, PREFIX, SUFFIX,
                   STARTING_NO, LAST_NO_USED, INCREMENT_BY, PADDING,
                   ALLOW_MANUAL, USE_DATE_PREFIX, DATE_FORMAT,
                   LOCATIONCODE, RESETNO, IS_ACTIVE, NOTES
            FROM {DOC_NUMBER_SERIES_TABLE}
            WHERE DOC_TYPE = :dt AND RESETNO = :rn AND {loc_clause}
              AND NVL(UPPER(TRIM(IS_ACTIVE)), 'Y') = 'Y'
            ORDER BY CASE WHEN LOCATIONCODE IS NOT NULL THEN 0 ELSE 1 END
        ) WHERE ROWNUM <= 1
        """,
        params,
    )
    if not rows:
        return None
    row = _row_to_dict(rows[0])
    row['next_preview'] = format_document_no(row, row.get('next_no'))
    return row


def format_document_no(series: Dict[str, Any], number: Any, *, doc_date: Optional[str] = None) -> str:
    """Build display number from series rules."""
    try:
        n = int(number)
    except (TypeError, ValueError):
        n = 0
    pad = max(0, _norm_int(series.get('padding'), 0))
    num_part = str(n).zfill(pad) if pad > 0 else str(n)
    prefix = str(series.get('prefix') or '')
    suffix = str(series.get('suffix') or '')
    if _yn(series.get('use_date_prefix')) == 'Y':
        fmt = str(series.get('date_format') or 'YYYYMMDD').strip().upper()
        dt = doc_date or datetime.now().strftime('%Y-%m-%d')
        try:
            d = datetime.strptime(dt[:10], '%Y-%m-%d')
        except ValueError:
            d = datetime.now()
        if fmt == 'YYYYMMDD':
            date_part = d.strftime('%Y%m%d')
        elif fmt == 'YYYYMM':
            date_part = d.strftime('%Y%m')
        elif fmt == 'YYYY':
            date_part = d.strftime('%Y')
        else:
            date_part = d.strftime('%Y%m%d')
        if prefix:
            return f'{prefix}{date_part}-{num_part}{suffix}'
        return f'{date_part}-{num_part}{suffix}'
    return f'{prefix}{num_part}{suffix}'


def save_document_series_bulk(
    rows: List[Dict[str, Any]],
    user: str,
) -> Tuple[bool, str, int]:
    """Update multiple series rows from setup form."""
    ensure_doc_number_series_table()
    if not _table_exists(DOC_NUMBER_SERIES_TABLE):
        return (False, 'DOC_NUMBER_SERIES table is not available.', 0)
    usr = (user or 'web')[:100]
    updated = 0
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                for data in rows or []:
                    sid = _norm_int(data.get('series_id'), 0)
                    if sid <= 0:
                        continue
                    start = max(1, _norm_int(data.get('starting_no'), 1))
                    last = max(0, _norm_int(data.get('last_no_used'), 0))
                    inc = max(1, _norm_int(data.get('increment_by'), 1))
                    if last > 0 and last < start:
                        last = start - inc
                    cur.execute(
                        f"""
                        UPDATE {DOC_NUMBER_SERIES_TABLE} SET
                            PREFIX = :prefix_val,
                            SUFFIX = :suffix_val,
                            STARTING_NO = :starting_no,
                            LAST_NO_USED = :last_no_used,
                            INCREMENT_BY = :increment_by,
                            PADDING = :padding_val,
                            ALLOW_MANUAL = :allow_manual,
                            USE_DATE_PREFIX = :use_date_prefix,
                            DATE_FORMAT = :date_format,
                            IS_ACTIVE = :is_active,
                            NOTES = :notes_val,
                            MODIFIED_BY = :modified_by,
                            MODIFIED_DATE = SYSDATE
                        WHERE SERIES_ID = :series_id
                        """,
                        {
                            'series_id': sid,
                            'prefix_val': str(data.get('prefix') or '')[:30],
                            'suffix_val': str(data.get('suffix') or '')[:30],
                            'starting_no': start,
                            'last_no_used': last,
                            'increment_by': inc,
                            'padding_val': max(0, _norm_int(data.get('padding'), 0)),
                            'allow_manual': _yn(data.get('allow_manual'), 'N'),
                            'use_date_prefix': _yn(data.get('use_date_prefix'), 'N'),
                            'date_format': (str(data.get('date_format') or 'YYYYMMDD').strip() or 'YYYYMMDD')[:20],
                            'is_active': _yn(data.get('is_active'), 'Y'),
                            'notes_val': str(data.get('notes') or '')[:500],
                            'modified_by': usr,
                        },
                    )
                    if cur.rowcount:
                        updated += 1
            conn.commit()
        return (True, '', updated)
    except Exception as ex:
        return (False, str(ex), 0)


def _max_from_source(
    doc_type: str,
    location_code: Optional[int] = None,
    reset_no: int = 1,
    *,
    prefix: Optional[str] = None,
) -> Optional[int]:
    spec = _DOC_MAX_SOURCES.get(str(doc_type or '').upper())
    if not spec:
        return None
    tbl = _detect_table(spec.get('tables') or [])
    if not tbl:
        return None
    no_col = _detect_column(tbl, spec.get('no_cols') or [])
    if not no_col:
        return None
    loc_col = _detect_column(tbl, ['LOCATIONCODE', 'LOCATION_CODE'])
    reset_col = _detect_column(tbl, ['RESETNO', 'RESET_NO'])
    where = ['1=1']
    params: Dict[str, Any] = {}
    if loc_col and location_code is not None:
        where.append(f'{loc_col} = :loc')
        params['loc'] = int(location_code)
    if reset_col:
        where.append(f'{reset_col} = :rn')
        params['rn'] = int(reset_no or 1)
    pfx = str(prefix or '').strip().upper()
    if not pfx:
        defaults = _SALES_SERIES_DEFAULT_PREFIXES.get(str(doc_type or '').upper())
        if defaults:
            pfx = str(defaults[0] or '').strip().upper()
    if pfx:
        where.append(f'UPPER(TO_CHAR({no_col})) LIKE :pfx')
        params['pfx'] = f'{pfx}%'
    rows = _safe_rows(
        f"""
        SELECT NVL(MAX(
            CASE
                WHEN REGEXP_LIKE(TO_CHAR({no_col}), '^[0-9]+$') THEN TO_NUMBER(TO_CHAR({no_col}))
                WHEN REGEXP_LIKE(TO_CHAR({no_col}), '[0-9]+$') THEN TO_NUMBER(REGEXP_SUBSTR(TO_CHAR({no_col}), '[0-9]+$'))
                ELSE 0
            END
        ), 0) AS mx
        FROM {tbl}
        WHERE {" AND ".join(where)}
        """,
        params,
    )
    if not rows:
        return None
    try:
        return int(rows[0].get('mx') or 0)
    except (TypeError, ValueError):
        return None


def sync_last_numbers_from_database(
    *,
    location_code: Optional[int] = None,
    reset_no: int = 1,
    user: str = 'system',
) -> Tuple[bool, str, int]:
    """Set LAST_NO_USED from MAX existing document numbers."""
    ensure_doc_number_series_table()
    seed_default_document_series()
    rows = list_document_series(location_code=location_code)
    usr = (user or 'system')[:100]
    synced = 0
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                for row in rows:
                    mx = _max_from_source(
                        row.get('doc_type') or '',
                        _norm_loc(row.get('locationcode')) if row.get('locationcode') is not None else location_code,
                        _norm_int(row.get('resetno'), reset_no),
                        prefix=str(row.get('prefix') or ''),
                    )
                    if mx is None:
                        continue
                    cur.execute(
                        f"""
                        UPDATE {DOC_NUMBER_SERIES_TABLE}
                        SET LAST_NO_USED = :mx, MODIFIED_BY = :usr, MODIFIED_DATE = SYSDATE
                        WHERE SERIES_ID = :id
                        """,
                        {'mx': int(mx), 'id': int(row['series_id']), 'usr': usr},
                    )
                    if cur.rowcount:
                        synced += 1
            conn.commit()
        return (True, '', synced)
    except Exception as ex:
        return (False, str(ex), 0)


def list_module_names() -> List[str]:
    rows = list_document_series()
    mods = sorted({str(r.get('module_name') or '').strip() for r in rows if r.get('module_name')})
    return mods


def peek_next_document_no(
    doc_type: str,
    *,
    location_code: Optional[int] = None,
    reset_no: int = 1,
    doc_date: Optional[str] = None,
) -> Optional[str]:
    series = get_document_series_by_type(doc_type, location_code=location_code, reset_no=reset_no)
    if not series:
        return None
    return format_document_no(series, series.get('next_no'), doc_date=doc_date)


def _compute_next_series_no(start: int, last: int, increment: int, *, floor_no: Optional[int] = None) -> int:
    start_n = max(1, int(start or 1))
    last_n = max(0, int(last or 0))
    inc_n = max(1, int(increment or 1))
    next_no = last_n + inc_n if last_n >= start_n else start_n
    if floor_no is not None:
        try:
            floor_i = int(floor_no)
        except (TypeError, ValueError):
            floor_i = 0
        if next_no <= floor_i:
            next_no = floor_i + inc_n
    return next_no


def bill_series_is_active(
    *,
    doc_type: str = BILLNO_DOC_TYPE,
    location_code: Optional[int] = None,
    reset_no: int = 1,
) -> bool:
    ensure_doc_number_series_table()
    seed_default_document_series()
    series = get_document_series_by_type(
        str(doc_type or BILLNO_DOC_TYPE).strip().upper(),
        location_code=location_code,
        reset_no=reset_no,
    )
    return bool(series and series.get('is_active') == 'Y')


def _resolve_series_id_for_update_cur(
    cur: Any,
    doc_type: str,
    *,
    location_code: Optional[int] = None,
    reset_no: int = 1,
) -> Optional[int]:
    dt = str(doc_type or '').strip().upper()
    if not dt:
        return None
    params: Dict[str, Any] = {'dt': dt, 'rn': int(reset_no or 1)}
    loc_clause = 'LOCATIONCODE IS NULL'
    if location_code is not None:
        loc_clause = '(LOCATIONCODE = :loc OR LOCATIONCODE IS NULL)'
        params['loc'] = int(location_code)
    cur.execute(
        f"""
        SELECT SERIES_ID FROM (
            SELECT SERIES_ID
            FROM {DOC_NUMBER_SERIES_TABLE}
            WHERE DOC_TYPE = :dt AND RESETNO = :rn AND {loc_clause}
              AND NVL(UPPER(TRIM(IS_ACTIVE)), 'Y') = 'Y'
            ORDER BY CASE WHEN LOCATIONCODE IS NOT NULL THEN 0 ELSE 1 END
        ) WHERE ROWNUM <= 1
        """,
        params,
    )
    row = cur.fetchone()
    if not row or row[0] is None:
        return None
    sid = int(row[0])
    cur.execute(
        f"""
        SELECT SERIES_ID
        FROM {DOC_NUMBER_SERIES_TABLE}
        WHERE SERIES_ID = :id
        FOR UPDATE
        """,
        {'id': sid},
    )
    lock_row = cur.fetchone()
    if not lock_row:
        return None
    return sid


def peek_document_no_int(
    doc_type: str,
    *,
    location_code: Optional[int] = None,
    reset_no: int = 1,
    floor_no: Optional[int] = None,
) -> Optional[int]:
    series = get_document_series_by_type(
        doc_type,
        location_code=location_code,
        reset_no=reset_no,
    )
    if not series or str(series.get('is_active') or 'Y').strip().upper() != 'Y':
        return None
    return _compute_next_series_no(
        series.get('starting_no', 1),
        series.get('last_no_used', 0),
        series.get('increment_by', 1),
        floor_no=floor_no,
    )


def allocate_document_no_cur(
    cur: Any,
    doc_type: str,
    *,
    location_code: Optional[int] = None,
    reset_no: int = 1,
    doc_date: Optional[str] = None,
    user: str = 'system',
    floor_no: Optional[int] = None,
) -> Tuple[Optional[int], Optional[str], str]:
    """
    Reserve next number inside an open transaction (SELECT FOR UPDATE on series row).
    Returns (numeric_part, formatted_no, error_message).
    """
    ensure_doc_number_series_table()
    seed_default_document_series()
    sid = _resolve_series_id_for_update_cur(
        cur,
        doc_type,
        location_code=location_code,
        reset_no=reset_no,
    )
    if not sid:
        return (None, None, f'No active series for {doc_type}')
    cur.execute(
        f"""
        SELECT STARTING_NO, LAST_NO_USED, INCREMENT_BY, PREFIX, SUFFIX,
               PADDING, USE_DATE_PREFIX, DATE_FORMAT
        FROM {DOC_NUMBER_SERIES_TABLE}
        WHERE SERIES_ID = :id
        """,
        {'id': sid},
    )
    row = cur.fetchone()
    if not row:
        return (None, None, 'Series row not found')
    start = max(1, int(row[0] or 1))
    last = max(0, int(row[1] or 0))
    inc = max(1, int(row[2] or 1))
    next_no = _compute_next_series_no(start, last, inc, floor_no=floor_no)
    cur.execute(
        f"""
        UPDATE {DOC_NUMBER_SERIES_TABLE}
        SET LAST_NO_USED = :n, MODIFIED_BY = :u, MODIFIED_DATE = SYSDATE
        WHERE SERIES_ID = :id
        """,
        {'n': next_no, 'id': sid, 'u': (user or 'system')[:100]},
    )
    series = {
        'prefix': str(row[3] or ''),
        'suffix': str(row[4] or ''),
        'padding': max(0, int(row[5] or 0)),
        'use_date_prefix': _yn(row[6], 'N'),
        'date_format': str(row[7] or 'YYYYMMDD').strip() or 'YYYYMMDD',
    }
    formatted = format_document_no(series, next_no, doc_date=doc_date)
    return (next_no, formatted, '')


def _saved_doc_numeric_part(val: Any) -> int:
    """Trailing numeric portion of a saved document number (SI-000050 -> 50)."""
    s = str(val or '').strip()
    if not s:
        return 0
    try:
        return max(0, abs(int(s)))
    except (TypeError, ValueError):
        pass
    m = re.search(r'(\d+)\s*$', s)
    if m:
        try:
            return max(0, abs(int(m.group(1))))
        except (TypeError, ValueError):
            pass
    return 0


def advance_document_series_after_save_cur(
    cur: Any,
    doc_type: str,
    saved_no: Any,
    *,
    location_code: Optional[int] = None,
    reset_no: int = 1,
    user: str = 'system',
) -> None:
    """Ensure LAST_NO_USED catches up when save reused a peeked number (no allocate on save)."""
    saved_n = _saved_doc_numeric_part(saved_no)
    if saved_n <= 0:
        return
    sid = _resolve_series_id_for_update_cur(
        cur,
        doc_type,
        location_code=location_code,
        reset_no=reset_no,
    )
    if not sid:
        return
    cur.execute(
        f"""
        SELECT LAST_NO_USED
        FROM {DOC_NUMBER_SERIES_TABLE}
        WHERE SERIES_ID = :id
        """,
        {'id': sid},
    )
    row = cur.fetchone()
    if not row:
        return
    last = max(0, int(row[0] or 0))
    if saved_n <= last:
        return
    cur.execute(
        f"""
        UPDATE {DOC_NUMBER_SERIES_TABLE}
        SET LAST_NO_USED = :n, MODIFIED_BY = :u, MODIFIED_DATE = SYSDATE
        WHERE SERIES_ID = :id
        """,
        {'n': saved_n, 'id': sid, 'u': (user or 'system')[:100]},
    )


def allocate_document_no(
    doc_type: str,
    *,
    location_code: Optional[int] = None,
    reset_no: int = 1,
    doc_date: Optional[str] = None,
    user: str = 'system',
    commit: bool = True,
    floor_no: Optional[int] = None,
) -> Tuple[Optional[int], Optional[str], str]:
    """
    Reserve next number for a document type.
    Returns (numeric_part, formatted_no, error_message).
    """
    ensure_doc_number_series_table()
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                result = allocate_document_no_cur(
                    cur,
                    doc_type,
                    location_code=location_code,
                    reset_no=reset_no,
                    doc_date=doc_date,
                    user=user,
                    floor_no=floor_no,
                )
            if commit:
                conn.commit()
            return result
    except Exception as ex:
        return (None, None, str(ex))
