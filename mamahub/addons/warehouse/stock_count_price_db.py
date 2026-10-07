"""Stock count price batches — load from STOCK_COUNT_PRICE_UPDATE, apply to ITEMMASTER / ITEMALTERNATEUOMMAP."""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from db import (
    _TABLE_COLUMNS_CACHE,
    _get_connection,
    _safe_rows,
    _table_exists,
    get_item_alternate_uoms,
    get_item_by_code,
)

_LOG = logging.getLogger('nexa.stock_count_price')

STOCK_COUNT_PRICE_HDR_TABLE = 'STOCK_COUNT_PRICE_HDR'
STOCK_COUNT_PRICE_TABLE = 'STOCK_COUNT_PRICE_UPDATE'
PRICE_BATCH_STATUSES = ('DRAFT', 'PENDING', 'APPLIED', 'CANCELLED')
LINE_APPLY_STATUSES = ('PENDING', 'APPLIED', 'ERROR', 'SKIPPED')

_PRICE_KEYS = (
    ('cost_price', 'OLD_COSTPRICE', 'NEW_COSTPRICE', 'COSTPRICE'),
    ('retail_price', 'OLD_RETAILPRICE', 'NEW_RETAILPRICE', 'RETAILPRICE'),
    ('wholesale_price', 'OLD_WHOLESALEPRICE', 'NEW_WHOLESALEPRICE', 'WHOLESALEPRICE'),
    ('third_price', 'OLD_THIRDPRICE', 'NEW_THIRDPRICE', 'THIRDPRICE'),
    ('branch_price', 'OLD_BRANCHPRICE', 'NEW_BRANCHPRICE', 'BRANCHPRICE'),
)


def _resolve_table_columns(table: str) -> List[str]:
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
    except Exception as ex:
        _LOG.warning('_resolve_table_columns %s: %s', key, ex)
    if cols:
        _TABLE_COLUMNS_CACHE[key] = cols
    return cols


def _has_price_hdr_table() -> bool:
    return _table_exists(STOCK_COUNT_PRICE_HDR_TABLE)


def ensure_stock_count_price_tables() -> bool:
    """Create ``STOCK_COUNT_PRICE_HDR`` and ``STOCK_COUNT_PRICE_UPDATE`` when missing."""
    if _table_exists(STOCK_COUNT_PRICE_TABLE):
        return True
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM user_tables WHERE table_name = 'STOCK_COUNT_PRICE_HDR'"
                )
                if int((cur.fetchone() or [0])[0] or 0) == 0:
                    cur.execute(
                        """
                        CREATE TABLE STOCK_COUNT_PRICE_HDR (
                            LOCATIONCODE   NUMBER(6) NOT NULL,
                            BATCH_NO       NUMBER(10) NOT NULL,
                            BATCH_DATE     DATE DEFAULT TRUNC(SYSDATE) NOT NULL,
                            STATUS         VARCHAR2(20) DEFAULT 'DRAFT' NOT NULL,
                            REMARKS        VARCHAR2(500),
                            SOURCE_COUNT_NO NUMBER(10),
                            CREATED_BY     VARCHAR2(50),
                            CREATED_AT     TIMESTAMP(6) DEFAULT SYSTIMESTAMP,
                            APPLIED_BY     VARCHAR2(50),
                            APPLIED_AT     TIMESTAMP(6),
                            CONSTRAINT PK_STOCK_COUNT_PRICE_HDR PRIMARY KEY (LOCATIONCODE, BATCH_NO)
                        ) TABLESPACE USERS
                        """
                    )
                cur.execute(
                    "SELECT COUNT(*) FROM user_tables WHERE table_name = 'STOCK_COUNT_PRICE_UPDATE'"
                )
                if int((cur.fetchone() or [0])[0] or 0) == 0:
                    cur.execute(
                        """
                        CREATE TABLE STOCK_COUNT_PRICE_UPDATE (
                            LOCATIONCODE      NUMBER(6) NOT NULL,
                            BATCH_NO          NUMBER(10) NOT NULL,
                            LINE_NO           NUMBER(8) NOT NULL,
                            ITEMCODE          NUMBER(12) NOT NULL,
                            BARCODE           VARCHAR2(80),
                            UOM               VARCHAR2(20),
                            ALT_SLNO          NUMBER(8),
                            OLD_COSTPRICE     NUMBER(18,6),
                            NEW_COSTPRICE     NUMBER(18,6),
                            OLD_RETAILPRICE   NUMBER(18,6),
                            NEW_RETAILPRICE   NUMBER(18,6),
                            OLD_WHOLESALEPRICE NUMBER(18,6),
                            NEW_WHOLESALEPRICE NUMBER(18,6),
                            OLD_THIRDPRICE    NUMBER(18,6),
                            NEW_THIRDPRICE    NUMBER(18,6),
                            OLD_BRANCHPRICE   NUMBER(18,6),
                            NEW_BRANCHPRICE   NUMBER(18,6),
                            APPLY_STATUS      VARCHAR2(20) DEFAULT 'PENDING',
                            APPLY_MESSAGE     VARCHAR2(500),
                            APPLIED_AT        TIMESTAMP(6),
                            CONSTRAINT PK_STOCK_COUNT_PRICE_UPD PRIMARY KEY (LOCATIONCODE, BATCH_NO, LINE_NO)
                        ) TABLESPACE USERS
                        """
                    )
                cur.execute(
                    "SELECT COUNT(*) FROM user_indexes WHERE index_name = 'IX_SCP_HDR_STAT'"
                )
                if int((cur.fetchone() or [0])[0] or 0) == 0:
                    cur.execute(
                        "CREATE INDEX IX_SCP_HDR_STAT ON STOCK_COUNT_PRICE_HDR (STATUS, BATCH_DATE)"
                    )
                cur.execute(
                    "SELECT COUNT(*) FROM user_indexes WHERE index_name = 'IX_SCP_LINE_STAT'"
                )
                if int((cur.fetchone() or [0])[0] or 0) == 0:
                    cur.execute(
                        "CREATE INDEX IX_SCP_LINE_STAT ON STOCK_COUNT_PRICE_UPDATE (BATCH_NO, APPLY_STATUS)"
                    )
            conn.commit()
        return True
    except Exception as ex:
        _LOG.error('ensure_stock_count_price_tables: %s', ex)
        print(f'[ensure_stock_count_price_tables] {ex}')
        return False


def next_price_batch_no(location_code: int) -> int:
    ensure_stock_count_price_tables()
    lc = int(location_code)
    with _get_connection() as conn:
        with conn.cursor() as cur:
            if _has_price_hdr_table():
                cur.execute(
                    f'SELECT NVL(MAX(BATCH_NO), 0) + 1 FROM {STOCK_COUNT_PRICE_HDR_TABLE} WHERE LOCATIONCODE = :lc',
                    {'lc': lc},
                )
            else:
                cur.execute(
                    f'SELECT NVL(MAX(BATCH_NO), 0) + 1 FROM {STOCK_COUNT_PRICE_TABLE} WHERE LOCATIONCODE = :lc',
                    {'lc': lc},
                )
            row = cur.fetchone()
            return int((row[0] if row else 1) or 1)


def list_price_batches(
    location_code: int,
    *,
    status: Optional[str] = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    ensure_stock_count_price_tables()
    lc = int(location_code)
    st = (status or '').strip().upper()
    params: Dict[str, Any] = {'lc': lc, 'lim': int(limit)}
    if _has_price_hdr_table():
        where = 'WHERE h.LOCATIONCODE = :lc'
        if st:
            where += ' AND UPPER(TRIM(h.STATUS)) = :st'
            params['st'] = st
        q = f"""
            SELECT
                h.LOCATIONCODE AS locationcode,
                h.BATCH_NO AS batch_no,
                h.BATCH_DATE AS batch_date,
                h.STATUS AS status,
                h.REMARKS AS remarks,
                h.SOURCE_COUNT_NO AS source_count_no,
                h.CREATED_BY AS created_by,
                h.CREATED_AT AS created_at,
                h.APPLIED_BY AS applied_by,
                h.APPLIED_AT AS applied_at,
                (SELECT COUNT(*) FROM {STOCK_COUNT_PRICE_TABLE} p
                 WHERE p.LOCATIONCODE = h.LOCATIONCODE AND p.BATCH_NO = h.BATCH_NO) AS line_count,
                (SELECT COUNT(*) FROM {STOCK_COUNT_PRICE_TABLE} p
                 WHERE p.LOCATIONCODE = h.LOCATIONCODE AND p.BATCH_NO = h.BATCH_NO
                   AND UPPER(TRIM(NVL(p.APPLY_STATUS, 'PENDING'))) = 'PENDING') AS pending_count
            FROM {STOCK_COUNT_PRICE_HDR_TABLE} h
            {where}
            ORDER BY h.BATCH_NO DESC
            FETCH FIRST :lim ROWS ONLY
        """
        return _safe_rows(q, params) or []
    having = ''
    if st:
        having = """
        HAVING CASE
            WHEN SUM(CASE WHEN UPPER(TRIM(NVL(p.APPLY_STATUS, 'PENDING'))) = 'PENDING' THEN 1 ELSE 0 END) > 0
            THEN 'PENDING' ELSE 'APPLIED'
        END = :st
        """
    q = f"""
        SELECT
            p.LOCATIONCODE AS locationcode,
            p.BATCH_NO AS batch_no,
            MAX(p.APPLIED_AT) AS batch_date,
            CASE
                WHEN SUM(CASE WHEN UPPER(TRIM(NVL(p.APPLY_STATUS, 'PENDING'))) = 'PENDING' THEN 1 ELSE 0 END) > 0
                THEN 'PENDING' ELSE 'APPLIED'
            END AS status,
            CAST(NULL AS VARCHAR2(500)) AS remarks,
            CAST(NULL AS NUMBER) AS source_count_no,
            CAST(NULL AS VARCHAR2(50)) AS created_by,
            MIN(p.APPLIED_AT) AS created_at,
            CAST(NULL AS VARCHAR2(50)) AS applied_by,
            MAX(p.APPLIED_AT) AS applied_at,
            COUNT(*) AS line_count,
            SUM(CASE WHEN UPPER(TRIM(NVL(p.APPLY_STATUS, 'PENDING'))) = 'PENDING' THEN 1 ELSE 0 END) AS pending_count
        FROM {STOCK_COUNT_PRICE_TABLE} p
        WHERE p.LOCATIONCODE = :lc
        GROUP BY p.LOCATIONCODE, p.BATCH_NO
        {having}
        ORDER BY p.BATCH_NO DESC
        FETCH FIRST :lim ROWS ONLY
    """
    return _safe_rows(q, params) or []


def get_price_batch_header(location_code: int, batch_no: int) -> Optional[Dict[str, Any]]:
    ensure_stock_count_price_tables()
    lc, bn = int(location_code), int(batch_no)
    if _has_price_hdr_table():
        rows = _safe_rows(
            f"""
            SELECT
                LOCATIONCODE AS locationcode,
                BATCH_NO AS batch_no,
                BATCH_DATE AS batch_date,
                STATUS AS status,
                REMARKS AS remarks,
                SOURCE_COUNT_NO AS source_count_no,
                CREATED_BY AS created_by,
                CREATED_AT AS created_at,
                APPLIED_BY AS applied_by,
                APPLIED_AT AS applied_at
            FROM {STOCK_COUNT_PRICE_HDR_TABLE}
            WHERE LOCATIONCODE = :lc AND BATCH_NO = :bn
            """,
            {'lc': lc, 'bn': bn},
        )
        if rows:
            return rows[0]
    rows = _safe_rows(
        f"""
        SELECT
            p.LOCATIONCODE AS locationcode,
            p.BATCH_NO AS batch_no,
            MAX(p.APPLIED_AT) AS batch_date,
            CASE
                WHEN SUM(CASE WHEN UPPER(TRIM(NVL(p.APPLY_STATUS, 'PENDING'))) = 'PENDING' THEN 1 ELSE 0 END) > 0
                THEN 'PENDING' ELSE 'APPLIED'
            END AS status,
            CAST(NULL AS VARCHAR2(500)) AS remarks,
            CAST(NULL AS NUMBER) AS source_count_no,
            CAST(NULL AS VARCHAR2(50)) AS created_by,
            MIN(p.APPLIED_AT) AS created_at,
            CAST(NULL AS VARCHAR2(50)) AS applied_by,
            MAX(p.APPLIED_AT) AS applied_at
        FROM {STOCK_COUNT_PRICE_TABLE} p
        WHERE p.LOCATIONCODE = :lc AND p.BATCH_NO = :bn
        GROUP BY p.LOCATIONCODE, p.BATCH_NO
        """,
        {'lc': lc, 'bn': bn},
    )
    return rows[0] if rows else None


def get_price_batch_lines(location_code: int, batch_no: int) -> List[Dict[str, Any]]:
    ensure_stock_count_price_tables()
    lc, bn = int(location_code), int(batch_no)
    rows = _safe_rows(
        f"""
        SELECT
            p.LINE_NO AS line_no,
            p.ITEMCODE AS itemcode,
            p.BARCODE AS barcode,
            p.UOM AS uom,
            p.ALT_SLNO AS alt_slno,
            p.OLD_COSTPRICE AS old_costprice,
            p.NEW_COSTPRICE AS new_costprice,
            p.OLD_RETAILPRICE AS old_retailprice,
            p.NEW_RETAILPRICE AS new_retailprice,
            p.OLD_WHOLESALEPRICE AS old_wholesaleprice,
            p.NEW_WHOLESALEPRICE AS new_wholesaleprice,
            p.OLD_THIRDPRICE AS old_thirdprice,
            p.NEW_THIRDPRICE AS new_thirdprice,
            p.OLD_BRANCHPRICE AS old_branchprice,
            p.NEW_BRANCHPRICE AS new_branchprice,
            p.APPLY_STATUS AS apply_status,
            p.APPLY_MESSAGE AS apply_message,
            p.APPLIED_AT AS applied_at,
            im.ITEMNAME AS item_name
        FROM {STOCK_COUNT_PRICE_TABLE} p
        LEFT JOIN ITEMMASTER im
          ON im.ITEMCODE = p.ITEMCODE AND im.LOCATIONCODE = p.LOCATIONCODE
        WHERE p.LOCATIONCODE = :lc AND p.BATCH_NO = :bn
        ORDER BY p.LINE_NO
        """,
        {'lc': lc, 'bn': bn},
    )
    return rows or []


def _float_or_none(v: Any) -> Optional[float]:
    if v is None or (isinstance(v, str) and not str(v).strip()):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _prices_from_line_row(row: Dict[str, Any]) -> Dict[str, float]:
    prices: Dict[str, float] = {}
    col_map = {
        'cost_price': 'new_costprice',
        'retail_price': 'new_retailprice',
        'wholesale_price': 'new_wholesaleprice',
        'third_price': 'new_thirdprice',
        'branch_price': 'new_branchprice',
    }
    for key, col in col_map.items():
        nv = _float_or_none(row.get(col) or row.get(key))
        if nv is not None:
            prices[key] = nv
    return prices


def _snapshot_prices_from_item(item_row: Dict[str, Any]) -> Dict[str, float]:
    return {
        'cost_price': float(item_row.get('costprice') or item_row.get('cost_price') or 0),
        'retail_price': float(item_row.get('retailprice') or item_row.get('retail_price') or 0),
        'wholesale_price': float(item_row.get('wholesaleprice') or item_row.get('wholesale_price') or 0),
        'third_price': float(item_row.get('thirdprice') or item_row.get('third_price') or 0),
        'branch_price': float(item_row.get('branchprice') or item_row.get('branch_price') or 0),
    }


def _snapshot_prices_from_alt(alt_row: Dict[str, Any]) -> Dict[str, float]:
    return {
        'cost_price': float(alt_row.get('costprice') or alt_row.get('cost_price') or 0),
        'retail_price': float(alt_row.get('retailprice') or alt_row.get('retail_price') or 0),
        'wholesale_price': float(alt_row.get('wholesaleprice') or alt_row.get('wholesale_price') or 0),
        'third_price': float(alt_row.get('thirdprice') or alt_row.get('third_price') or 0),
        'branch_price': float(alt_row.get('branchprice') or alt_row.get('branch_price') or 0),
    }


def _apply_line_prices_cur(
    cur: Any,
    location_code: int,
    line: Dict[str, Any],
    *,
    update_all_alternates: bool,
) -> Tuple[bool, str]:
    from db.itemmaster_core import (
        _find_base_alternate_slno,
        _update_alternate_uom_prices_cur,
        _update_itemmaster_prices_cur,
    )

    try:
        ic = int(line.get('itemcode') or 0)
    except (TypeError, ValueError):
        return (False, 'Invalid item code.')
    if ic <= 0:
        return (False, 'Invalid item code.')
    prices = _prices_from_line_row(line)
    if not prices:
        return (False, 'No new prices on line.')

    loc = int(location_code)
    item_row = get_item_by_code(ic, loc) or {}
    if not item_row:
        return (False, f'Item {ic} not found.')

    updated_master = _update_itemmaster_prices_cur(cur, loc, ic, prices)
    updated_alt = False
    try:
        slno = int(line.get('alt_slno') or line.get('ALT_SLNO') or 0)
    except (TypeError, ValueError):
        slno = 0
    uom = str(line.get('uom') or '').strip().upper()

    if update_all_alternates:
        for alt in get_item_alternate_uoms(loc, ic) or []:
            try:
                asn = int(alt.get('slno') or alt.get('SLNO') or 0)
            except (TypeError, ValueError):
                asn = 0
            if asn > 0 and _update_alternate_uom_prices_cur(cur, loc, ic, asn, prices):
                updated_alt = True
    elif slno > 0:
        updated_alt = _update_alternate_uom_prices_cur(cur, loc, ic, slno, prices)
    elif uom:
        for alt in get_item_alternate_uoms(loc, ic) or []:
            ac = str(alt.get('alternateuomcode') or alt.get('uom') or '').strip().upper()
            if ac != uom:
                continue
            try:
                asn = int(alt.get('slno') or 0)
            except (TypeError, ValueError):
                asn = 0
            if asn > 0 and _update_alternate_uom_prices_cur(cur, loc, ic, asn, prices):
                updated_alt = True
    else:
        base_slno = _find_base_alternate_slno(loc, ic, item_row)
        if base_slno:
            updated_alt = _update_alternate_uom_prices_cur(cur, loc, ic, base_slno, prices)

    if not updated_master and not updated_alt:
        return (False, 'No price columns updated (check item / alternate UOM).')
    parts = []
    if updated_master:
        parts.append('ITEMMASTER')
    if updated_alt:
        parts.append('ITEMALTERNATEUOMMAP')
    return (True, 'Updated ' + ' + '.join(parts))


def create_price_batch(
    location_code: int,
    *,
    remarks: str = '',
    source_count_no: Optional[int] = None,
    created_by: str = '',
) -> Tuple[bool, str, Optional[int]]:
    ensure_stock_count_price_tables()
    lc = int(location_code)
    bn = next_price_batch_no(lc)
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                if _has_price_hdr_table():
                    cur.execute(
                        f"""
                        INSERT INTO {STOCK_COUNT_PRICE_HDR_TABLE}
                            (LOCATIONCODE, BATCH_NO, BATCH_DATE, STATUS, REMARKS, SOURCE_COUNT_NO, CREATED_BY)
                        VALUES
                            (:lc, :bn, TRUNC(SYSDATE), 'DRAFT', :rm, :scn, :cb)
                        """,
                        {
                            'lc': lc,
                            'bn': bn,
                            'rm': (remarks or '')[:500],
                            'scn': int(source_count_no) if source_count_no else None,
                            'cb': (created_by or '')[:50],
                        },
                    )
            conn.commit()
        return (True, '', bn)
    except Exception as ex:
        return (False, str(ex), None)


def upsert_price_batch_lines(
    location_code: int,
    batch_no: int,
    lines: List[Dict[str, Any]],
) -> Tuple[bool, str, int]:
    """Insert or update price lines (by item+UOM+slno merge)."""
    ensure_stock_count_price_tables()
    hdr = get_price_batch_header(location_code, batch_no)
    if not hdr:
        return (False, 'Price batch not found.', 0)
    st = str(hdr.get('status') or '').strip().upper()
    if st in ('APPLIED', 'CANCELLED'):
        return (False, f'Cannot edit batch in status {st}.', 0)

    lc, bn = int(location_code), int(batch_no)
    existing = get_price_batch_lines(lc, bn)
    by_key: Dict[tuple, Dict[str, Any]] = {}
    for row in existing:
        try:
            ic = int(row.get('itemcode') or 0)
        except (TypeError, ValueError):
            continue
        uom = str(row.get('uom') or '').strip().upper()
        try:
            slno = int(row.get('alt_slno') or 0)
        except (TypeError, ValueError):
            slno = 0
        by_key[(ic, uom, slno)] = row
    next_line = max([int(r.get('line_no') or 0) for r in existing], default=0) + 1
    written = 0

    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                for raw in lines or []:
                    try:
                        ic = int(raw.get('itemcode') or raw.get('item_code') or 0)
                    except (TypeError, ValueError):
                        continue
                    if ic <= 0:
                        continue
                    uom = str(raw.get('uom') or 'NOS').strip().upper()[:20]
                    try:
                        slno = int(raw.get('alt_slno') or raw.get('slno') or 0)
                    except (TypeError, ValueError):
                        slno = 0
                    barcode = str(raw.get('barcode') or raw.get('manufacturerid') or '')[:80]
                    item_row = get_item_by_code(ic, lc) or {}
                    old_p = _snapshot_prices_from_item(item_row)
                    if slno > 0 or uom:
                        for alt in get_item_alternate_uoms(lc, ic) or []:
                            try:
                                asn = int(alt.get('slno') or 0)
                            except (TypeError, ValueError):
                                asn = 0
                            ac = str(alt.get('alternateuomcode') or alt.get('uom') or '').strip().upper()
                            if slno > 0 and asn == slno:
                                old_p = _snapshot_prices_from_alt(alt)
                                break
                            if uom and ac == uom:
                                old_p = _snapshot_prices_from_alt(alt)
                                slno = asn or slno
                                break

                    new_p: Dict[str, Optional[float]] = {}
                    for key, old_col, new_col, _ in _PRICE_KEYS:
                        nv = _float_or_none(raw.get(key) or raw.get(new_col.lower()))
                        new_p[key] = nv if nv is not None else old_p.get(key)

                    merge_key = (ic, uom, slno)
                    params = {
                        'lc': lc,
                        'bn': bn,
                        'ic': ic,
                        'bc': barcode,
                        'uom': uom,
                        'slno': slno if slno > 0 else None,
                        'oc': old_p.get('cost_price'),
                        'nc': new_p.get('cost_price'),
                        'or': old_p.get('retail_price'),
                        'nr': new_p.get('retail_price'),
                        'ow': old_p.get('wholesale_price'),
                        'nw': new_p.get('wholesale_price'),
                        'ot': old_p.get('third_price'),
                        'nt': new_p.get('third_price'),
                        'ob': old_p.get('branch_price'),
                        'nb': new_p.get('branch_price'),
                    }
                    if merge_key in by_key:
                        lno = int(by_key[merge_key].get('line_no') or 0)
                        cur.execute(
                            f"""
                            UPDATE {STOCK_COUNT_PRICE_TABLE} SET
                                BARCODE = :bc, UOM = :uom, ALT_SLNO = :slno,
                                OLD_COSTPRICE = :oc, NEW_COSTPRICE = :nc,
                                OLD_RETAILPRICE = :or, NEW_RETAILPRICE = :nr,
                                OLD_WHOLESALEPRICE = :ow, NEW_WHOLESALEPRICE = :nw,
                                OLD_THIRDPRICE = :ot, NEW_THIRDPRICE = :nt,
                                OLD_BRANCHPRICE = :ob, NEW_BRANCHPRICE = :nb,
                                APPLY_STATUS = 'PENDING', APPLY_MESSAGE = NULL, APPLIED_AT = NULL
                            WHERE LOCATIONCODE = :lc AND BATCH_NO = :bn AND LINE_NO = :ln
                            """,
                            {**params, 'ln': lno},
                        )
                    else:
                        cur.execute(
                            f"""
                            INSERT INTO {STOCK_COUNT_PRICE_TABLE} (
                                LOCATIONCODE, BATCH_NO, LINE_NO, ITEMCODE, BARCODE, UOM, ALT_SLNO,
                                OLD_COSTPRICE, NEW_COSTPRICE,
                                OLD_RETAILPRICE, NEW_RETAILPRICE,
                                OLD_WHOLESALEPRICE, NEW_WHOLESALEPRICE,
                                OLD_THIRDPRICE, NEW_THIRDPRICE,
                                OLD_BRANCHPRICE, NEW_BRANCHPRICE,
                                APPLY_STATUS
                            ) VALUES (
                                :lc, :bn, :ln, :ic, :bc, :uom, :slno,
                                :oc, :nc, :or, :nr, :ow, :nw, :ot, :nt, :ob, :nb, 'PENDING'
                            )
                            """,
                            {**params, 'ln': next_line},
                        )
                        by_key[merge_key] = {'line_no': next_line}
                        next_line += 1
                    written += 1
                if written and st == 'DRAFT' and _has_price_hdr_table():
                    cur.execute(
                        f"""
                        UPDATE {STOCK_COUNT_PRICE_HDR_TABLE}
                        SET STATUS = 'PENDING' WHERE LOCATIONCODE = :lc AND BATCH_NO = :bn
                        """,
                        {'lc': lc, 'bn': bn},
                    )
            conn.commit()
        return (True, '', written)
    except Exception as ex:
        return (False, str(ex), 0)


def apply_price_batch_lines(
    location_code: int,
    batch_no: int,
    *,
    line_nos: Optional[List[int]] = None,
    apply_all_pending: bool = False,
    update_all_alternates: bool = False,
    applied_by: str = '',
) -> Tuple[bool, str, Dict[str, Any]]:
    """Push new prices to ITEMMASTER (+ alternate UOM rows)."""
    ensure_stock_count_price_tables()
    hdr = get_price_batch_header(location_code, batch_no)
    if not hdr:
        return (False, 'Price batch not found.', {})
    st = str(hdr.get('status') or '').strip().upper()
    if st == 'CANCELLED':
        return (False, 'Cancelled batch cannot be applied.', {})

    lc, bn = int(location_code), int(batch_no)
    lines = get_price_batch_lines(lc, bn)
    if not lines:
        return (False, 'No lines in this batch.', {})

    want_lines: Optional[set] = None
    if line_nos:
        want_lines = set()
        for n in line_nos:
            try:
                want_lines.add(int(n))
            except (TypeError, ValueError):
                pass
        if not want_lines:
            return (False, 'No valid line numbers selected.', {})

    if not apply_all_pending and want_lines is None:
        return (False, 'Select lines or use bulk update.', {})

    applied = 0
    errors: List[str] = []
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                for ln in lines:
                    try:
                        lno = int(ln.get('line_no') or 0)
                    except (TypeError, ValueError):
                        continue
                    ast = str(ln.get('apply_status') or 'PENDING').strip().upper()
                    if want_lines is not None:
                        if lno not in want_lines:
                            continue
                    elif apply_all_pending:
                        if ast != 'PENDING':
                            continue
                    else:
                        continue

                    ok, msg = _apply_line_prices_cur(
                        cur, lc, ln, update_all_alternates=update_all_alternates,
                    )
                    if ok:
                        applied += 1
                        cur.execute(
                            f"""
                            UPDATE {STOCK_COUNT_PRICE_TABLE} SET
                                APPLY_STATUS = 'APPLIED',
                                APPLY_MESSAGE = :msg,
                                APPLIED_AT = SYSTIMESTAMP
                            WHERE LOCATIONCODE = :lc AND BATCH_NO = :bn AND LINE_NO = :ln
                            """,
                            {'msg': (msg or '')[:500], 'lc': lc, 'bn': bn, 'ln': lno},
                        )
                    else:
                        errors.append(f'Line {lno}: {msg}')
                        cur.execute(
                            f"""
                            UPDATE {STOCK_COUNT_PRICE_TABLE} SET
                                APPLY_STATUS = 'ERROR',
                                APPLY_MESSAGE = :msg
                            WHERE LOCATIONCODE = :lc AND BATCH_NO = :bn AND LINE_NO = :ln
                            """,
                            {'msg': (msg or '')[:500], 'lc': lc, 'bn': bn, 'ln': lno},
                        )

                pending = _safe_rows(
                    f"""
                    SELECT COUNT(*) AS c FROM {STOCK_COUNT_PRICE_TABLE}
                    WHERE LOCATIONCODE = :lc AND BATCH_NO = :bn
                      AND UPPER(TRIM(NVL(APPLY_STATUS, 'PENDING'))) = 'PENDING'
                    """,
                    {'lc': lc, 'bn': bn},
                )
                pend_n = int((pending[0].get('c') if pending else 0) or 0)
                if _has_price_hdr_table():
                    if applied > 0 and pend_n == 0:
                        cur.execute(
                            f"""
                            UPDATE {STOCK_COUNT_PRICE_HDR_TABLE} SET
                                STATUS = 'APPLIED',
                                APPLIED_BY = :ab,
                                APPLIED_AT = SYSTIMESTAMP
                            WHERE LOCATIONCODE = :lc AND BATCH_NO = :bn
                            """,
                            {'ab': (applied_by or '')[:50], 'lc': lc, 'bn': bn},
                        )
                    elif applied > 0 and str(hdr.get('status') or '').upper() == 'DRAFT':
                        cur.execute(
                            f"""
                            UPDATE {STOCK_COUNT_PRICE_HDR_TABLE} SET STATUS = 'PENDING'
                            WHERE LOCATIONCODE = :lc AND BATCH_NO = :bn
                            """,
                            {'lc': lc, 'bn': bn},
                        )
            conn.commit()
    except Exception as ex:
        _LOG.exception('apply_price_batch_lines: %s', ex)
        return (False, str(ex), {'applied': 0, 'errors': [str(ex)]})

    msg = f'Applied {applied} line(s) to ITEMMASTER / alternate UOM.'
    if errors:
        msg += f' {len(errors)} error(s).'
    return (True, msg, {'applied': applied, 'errors': errors[:20]})


def import_lines_from_stock_count(
    location_code: int,
    batch_no: int,
    count_no: int,
) -> Tuple[bool, str, int]:
    """Seed price batch lines from a stock count (items only, prices copied from item master)."""
    from addons.warehouse.stock_count_db import get_stock_count_lines

    lines_in = get_stock_count_lines(int(location_code), int(count_no))
    if not lines_in:
        return (False, 'Stock count has no lines.', 0)
    payload: List[Dict[str, Any]] = []
    for ln in lines_in:
        try:
            ic = int(ln.get('itemcode') or 0)
        except (TypeError, ValueError):
            continue
        if ic <= 0:
            continue
        payload.append({
            'itemcode': ic,
            'barcode': ln.get('barcode'),
            'uom': ln.get('uom') or 'NOS',
        })
    return upsert_price_batch_lines(location_code, batch_no, payload)


def delete_price_batch(location_code: int, batch_no: int) -> Tuple[bool, str]:
    hdr = get_price_batch_header(location_code, batch_no)
    if not hdr:
        return (False, 'Not found.')
    if str(hdr.get('status') or '').upper() == 'APPLIED':
        return (False, 'Applied batches cannot be deleted.')
    try:
        lc, bn = int(location_code), int(batch_no)
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f'DELETE FROM {STOCK_COUNT_PRICE_TABLE} WHERE LOCATIONCODE = :lc AND BATCH_NO = :bn',
                    {'lc': lc, 'bn': bn},
                )
                if _has_price_hdr_table():
                    cur.execute(
                        f'DELETE FROM {STOCK_COUNT_PRICE_HDR_TABLE} WHERE LOCATIONCODE = :lc AND BATCH_NO = :bn',
                        {'lc': lc, 'bn': bn},
                    )
            conn.commit()
        return (True, '')
    except Exception as ex:
        return (False, str(ex))
