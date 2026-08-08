"""Inventory value adjustment journals — correct item cost / average cost without qty movement."""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from db import (
    _get_connection,
    _safe_rows,
    _table_exists,
    get_item_by_code,
    get_item_store_inventory,
    get_item_store_rows_from_itemmaster,
    get_warehouse_master_store_picker_rows,
)

_LOG = logging.getLogger('nexa.inventory_value_adjustment')

HDR_TABLE = 'INVVALADJHDR'
DTL_TABLE = 'INVVALADJDTL'

STATUS_DRAFT = 'DRAFT'
STATUS_IN_PROGRESS = 'IN_PROGRESS'
STATUS_POSTED = 'POSTED'

ADJ_TYPES = ('VALUE', 'VALUE_ADJUSTMENT')
INV_MODELS = ('FIFO', 'WEIGHTED_AVG', 'AVERAGE')
ADJ_DIRS = ('INCREASE', 'DECREASE')
ADJ_REASONS = (
    'Price correction',
    'Landed cost update',
    'Revaluation',
    'Other',
)


def ensure_inventory_value_adjustment_tables() -> bool:
    if _table_exists(DTL_TABLE):
        return True
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM user_tables WHERE table_name = 'INVVALADJHDR'"
                )
                if int((cur.fetchone() or [0])[0] or 0) == 0:
                    cur.execute(
                        f"""
                        CREATE TABLE {HDR_TABLE} (
                            LOCATIONCODE      NUMBER(6) NOT NULL,
                            JOURNALNO         NUMBER(10) NOT NULL,
                            JOURNALNAME       VARCHAR2(50),
                            DESCRIPTION       VARCHAR2(500),
                            ADJUSTMENT_TYPE   VARCHAR2(30) DEFAULT 'VALUE',
                            INVENTORY_MODEL   VARCHAR2(20) DEFAULT 'FIFO',
                            JOURNAL_DATE      DATE,
                            POSTING_DATE      DATE,
                            WAREHOUSE_ID      NUMBER(10),
                            WAREHOUSE_CODE    VARCHAR2(30),
                            FIN_DIM           VARCHAR2(50),
                            STATUS            VARCHAR2(20) DEFAULT 'DRAFT',
                            POSTED            CHAR(1) DEFAULT 'N',
                            NOTES             VARCHAR2(2000),
                            REFERENCE         VARCHAR2(100),
                            ADJUSTMENT_REASON VARCHAR2(100),
                            CREATEDBY         VARCHAR2(50),
                            CREATEDDATE       DATE,
                            POSTEDBY          VARCHAR2(50),
                            POSTEDDATE        DATE,
                            RESETNO           NUMBER(2) DEFAULT 1,
                            CONSTRAINT PK_INVVALADJHDR PRIMARY KEY (LOCATIONCODE, JOURNALNO)
                        ) TABLESPACE USERS
                        """
                    )
                cur.execute(
                    "SELECT COUNT(*) FROM user_tables WHERE table_name = 'INVVALADJDTL'"
                )
                if int((cur.fetchone() or [0])[0] or 0) == 0:
                    cur.execute(
                        f"""
                        CREATE TABLE {DTL_TABLE} (
                            LOCATIONCODE       NUMBER(6) NOT NULL,
                            JOURNALNO          NUMBER(10) NOT NULL,
                            SLNO               NUMBER(4) NOT NULL,
                            ITEMCODE           NUMBER(12) NOT NULL,
                            ITEMNAME           VARCHAR2(250),
                            WAREHOUSE_ID       NUMBER(10),
                            WAREHOUSE_CODE     VARCHAR2(30),
                            ADJUSTMENT_DIR     VARCHAR2(10),
                            QUANTITY           NUMBER(14,3) DEFAULT 0,
                            UNITOFMEASUREMENT  VARCHAR2(20),
                            UNIT_COST          NUMBER(18,6),
                            ADJUSTMENT_AMOUNT  NUMBER(18,6),
                            NEW_AVERAGE_COST   NUMBER(18,6),
                            CURRENT_QTY        NUMBER(14,3),
                            CURRENT_AVG_COST   NUMBER(18,6),
                            CURRENT_INV_VALUE  NUMBER(18,6),
                            FIN_DIM            VARCHAR2(50),
                            LINEREMARKS        VARCHAR2(300),
                            CONSTRAINT PK_INVVALADJDTL PRIMARY KEY (LOCATIONCODE, JOURNALNO, SLNO)
                        ) TABLESPACE USERS
                        """
                    )
            conn.commit()
        return True
    except Exception as ex:
        _LOG.error('ensure_inventory_value_adjustment_tables: %s', ex)
        return False


def next_journal_no(location_code: int) -> int:
    ensure_inventory_value_adjustment_tables()
    lc = int(location_code)
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f'SELECT NVL(MAX(JOURNALNO), 0) + 1 FROM {HDR_TABLE} WHERE LOCATIONCODE = :lc',
                {'lc': lc},
            )
            row = cur.fetchone()
            return int((row[0] if row else 1) or 1)


def format_journal_name(journal_no: int) -> str:
    try:
        n = int(journal_no)
    except (TypeError, ValueError):
        n = 0
    return f'IVAJ-{n:06d}'


def list_journals(
    location_code: int,
    *,
    search: str = '',
    status: str = '',
    limit: int = 200,
) -> List[Dict[str, Any]]:
    ensure_inventory_value_adjustment_tables()
    lc = int(location_code)
    where = ['h.LOCATIONCODE = :lc']
    params: Dict[str, Any] = {'lc': lc, 'lim': max(20, min(int(limit or 200), 500))}
    if status:
        where.append('UPPER(TRIM(h.STATUS)) = :st')
        params['st'] = status.strip().upper()
    if search:
        where.append(
            "(TO_CHAR(h.JOURNALNO) LIKE :s OR UPPER(NVL(h.JOURNALNAME,'')) LIKE :su "
            "OR UPPER(NVL(h.DESCRIPTION,'')) LIKE :su OR UPPER(NVL(h.REFERENCE,'')) LIKE :su)"
        )
        params['s'] = f'%{search.strip()}%'
        params['su'] = f'%{search.strip().upper()}%'
    q = f"""
        SELECT * FROM (
            SELECT
                h.JOURNALNO AS journalno,
                h.JOURNALNAME AS journalname,
                h.DESCRIPTION AS description,
                h.ADJUSTMENT_TYPE AS adjustment_type,
                h.INVENTORY_MODEL AS inventory_model,
                h.JOURNAL_DATE AS journal_date,
                h.POSTING_DATE AS posting_date,
                h.WAREHOUSE_CODE AS warehouse_code,
                h.STATUS AS status,
                h.POSTED AS posted,
                h.REFERENCE AS reference,
                h.CREATEDBY AS createdby,
                h.CREATEDDATE AS createddate,
                (SELECT NVL(SUM(d.ADJUSTMENT_AMOUNT), 0) FROM {DTL_TABLE} d
                 WHERE d.LOCATIONCODE = h.LOCATIONCODE AND d.JOURNALNO = h.JOURNALNO) AS total_adjustment,
                (SELECT COUNT(*) FROM {DTL_TABLE} d
                 WHERE d.LOCATIONCODE = h.LOCATIONCODE AND d.JOURNALNO = h.JOURNALNO) AS line_count
            FROM {HDR_TABLE} h
            WHERE {' AND '.join(where)}
            ORDER BY h.JOURNALNO DESC
        ) WHERE ROWNUM <= :lim
    """
    rows = _safe_rows(q, params) or []
    for r in rows:
        jno = r.get('journalno')
        if not r.get('journalname'):
            r['journalname'] = format_journal_name(jno)
    return rows


def get_journal_payload(location_code: int, journal_no: int) -> Optional[Dict[str, Any]]:
    ensure_inventory_value_adjustment_tables()
    lc = int(location_code)
    jno = int(journal_no)
    hdr_rows = _safe_rows(
        f"""
        SELECT
            JOURNALNO AS journalno,
            JOURNALNAME AS journalname,
            DESCRIPTION AS description,
            ADJUSTMENT_TYPE AS adjustment_type,
            INVENTORY_MODEL AS inventory_model,
            JOURNAL_DATE AS journal_date,
            POSTING_DATE AS posting_date,
            WAREHOUSE_ID AS warehouse_id,
            WAREHOUSE_CODE AS warehouse_code,
            FIN_DIM AS fin_dim,
            STATUS AS status,
            POSTED AS posted,
            NOTES AS notes,
            REFERENCE AS reference,
            ADJUSTMENT_REASON AS adjustment_reason,
            CREATEDBY AS createdby,
            CREATEDDATE AS createddate,
            POSTEDBY AS postedby,
            POSTEDDATE AS posteddate
        FROM {HDR_TABLE}
        WHERE LOCATIONCODE = :lc AND JOURNALNO = :jno
        """,
        {'lc': lc, 'jno': jno},
    )
    if not hdr_rows:
        return None
    header = hdr_rows[0]
    if not header.get('journalname'):
        header['journalname'] = format_journal_name(jno)
    lines = _safe_rows(
        f"""
        SELECT
            SLNO AS slno,
            ITEMCODE AS itemcode,
            ITEMNAME AS itemname,
            WAREHOUSE_ID AS warehouse_id,
            WAREHOUSE_CODE AS warehouse_code,
            ADJUSTMENT_DIR AS adjustment_dir,
            QUANTITY AS quantity,
            UNITOFMEASUREMENT AS uom,
            UNIT_COST AS unit_cost,
            ADJUSTMENT_AMOUNT AS adjustment_amount,
            NEW_AVERAGE_COST AS new_average_cost,
            CURRENT_QTY AS current_qty,
            CURRENT_AVG_COST AS current_avg_cost,
            CURRENT_INV_VALUE AS current_inv_value,
            FIN_DIM AS fin_dim,
            LINEREMARKS AS lineremarks
        FROM {DTL_TABLE}
        WHERE LOCATIONCODE = :lc AND JOURNALNO = :jno
        ORDER BY SLNO
        """,
        {'lc': lc, 'jno': jno},
    ) or []
    return {'header': header, 'lines': lines}


def _item_inventory_snapshot(
    location_code: int,
    item_code: int,
    warehouse_code: str = '',
) -> Dict[str, Any]:
    ic = int(item_code)
    loc = int(location_code)
    wh = (warehouse_code or '').strip().upper()
    item = get_item_by_code(ic, loc) or {}
    rows = get_item_store_inventory(loc, ic) or []
    if not rows:
        try:
            rows = get_item_store_rows_from_itemmaster(ic, loc) or []
        except Exception:
            rows = []
    current_qty = 0.0
    if wh:
        for r in rows:
            rs = str(r.get('store') or r.get('itemlocation') or '').strip().upper()
            if rs == wh:
                current_qty = float(r.get('stock') or 0)
                break
    elif rows:
        current_qty = sum(float(r.get('stock') or 0) for r in rows)
    avg_cost = float(item.get('averagecost') or item.get('AVERAGECOST') or item.get('cost') or 0)
    inv_value = round(current_qty * avg_cost, 2)
    return {
        'itemcode': ic,
        'itemname': item.get('name') or item.get('ITEMNAME') or '',
        'uom': item.get('uom') or item.get('UNITOFMEASUREMENT') or '',
        'current_qty': current_qty,
        'current_avg_cost': avg_cost,
        'current_inv_value': inv_value,
        'warehouse_code': wh,
    }


def get_item_line_context(
    location_code: int,
    item_code: int,
    warehouse_code: str = '',
) -> Dict[str, Any]:
    snap = _item_inventory_snapshot(location_code, item_code, warehouse_code)
    return {'success': True, **snap}


def list_warehouse_options(location_code: int) -> List[Dict[str, Any]]:
    try:
        rows = get_warehouse_master_store_picker_rows(int(location_code)) or []
        out = []
        for r in rows:
            out.append({
                'id': r.get('warehouse_id') or r.get('id'),
                'code': r.get('store') or r.get('warehouse_code') or r.get('code'),
                'name': r.get('name') or r.get('warehouse_name') or '',
            })
        return out
    except Exception as ex:
        _LOG.warning('list_warehouse_options: %s', ex)
        return []


def _parse_date(val: Any) -> Optional[date]:
    if not val:
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    s = str(val).strip()[:10]
    if not s:
        return None
    try:
        return datetime.strptime(s, '%Y-%m-%d').date()
    except ValueError:
        return None


def _calc_new_avg(current_qty: float, current_avg: float, adj_amount: float, adj_dir: str) -> float:
    qty = float(current_qty or 0)
    if qty <= 0:
        return float(current_avg or 0)
    signed = float(adj_amount or 0)
    if str(adj_dir or '').upper() == 'DECREASE':
        signed = -abs(signed)
    else:
        signed = abs(signed)
    base_val = qty * float(current_avg or 0)
    return round((base_val + signed) / qty, 6)


def save_journal(
    location_code: int,
    *,
    journal_no: Optional[int],
    user: str,
    header: Dict[str, Any],
    lines: List[Dict[str, Any]],
    post: bool = False,
) -> Tuple[bool, str, Optional[int]]:
    ensure_inventory_value_adjustment_tables()
    lc = int(location_code)
    if not lines:
        return (False, 'Add at least one journal line.', None)
    is_new = not journal_no
    jno = int(journal_no) if journal_no else next_journal_no(lc)
    jname = (header.get('journalname') or '').strip() or format_journal_name(jno)
    desc = (header.get('description') or '').strip()[:500]
    adj_type = (header.get('adjustment_type') or 'VALUE').strip()[:30]
    inv_model = (header.get('inventory_model') or 'FIFO').strip()[:20]
    journal_date = _parse_date(header.get('journal_date')) or date.today()
    posting_date = _parse_date(header.get('posting_date')) or journal_date
    wh_id = header.get('warehouse_id')
    wh_code = (header.get('warehouse_code') or '').strip()[:30]
    fin_dim = (header.get('fin_dim') or '').strip()[:50]
    notes = (header.get('notes') or '').strip()[:2000]
    reference = (header.get('reference') or '').strip()[:100]
    adj_reason = (header.get('adjustment_reason') or '').strip()[:100]
    status = STATUS_POSTED if post else STATUS_IN_PROGRESS
    posted_flag = 'Y' if post else 'N'

    existing = get_journal_payload(lc, jno)
    if existing and str(existing['header'].get('posted') or 'N').upper() == 'Y':
        return (False, 'Posted journals cannot be changed.', jno)

    norm_lines: List[Dict[str, Any]] = []
    for i, ln in enumerate(lines, start=1):
        try:
            ic = int(ln.get('itemcode') or ln.get('item_code') or 0)
        except (TypeError, ValueError):
            return (False, f'Line {i}: invalid item code.', jno)
        if ic <= 0:
            return (False, f'Line {i}: item is required.', jno)
        snap = _item_inventory_snapshot(
            lc, ic, (ln.get('warehouse_code') or wh_code or '').strip()
        )
        cur_qty = float(ln.get('current_qty') if ln.get('current_qty') is not None else snap['current_qty'])
        cur_avg = float(ln.get('current_avg_cost') if ln.get('current_avg_cost') is not None else snap['current_avg_cost'])
        cur_val = round(cur_qty * cur_avg, 2)
        adj_dir = (ln.get('adjustment_dir') or 'INCREASE').strip().upper()
        if adj_dir not in ADJ_DIRS:
            adj_dir = 'INCREASE'
        try:
            adj_amt = abs(float(ln.get('adjustment_amount') or 0))
        except (TypeError, ValueError):
            return (False, f'Line {i}: invalid adjustment amount.', jno)
        if adj_amt <= 0:
            return (False, f'Line {i}: adjustment amount must be greater than zero.', jno)
        unit_cost = float(ln.get('unit_cost') or cur_avg or 0)
        new_avg = float(ln.get('new_average_cost') or 0)
        if new_avg <= 0:
            new_avg = _calc_new_avg(cur_qty, cur_avg, adj_amt, adj_dir)
        norm_lines.append({
            'slno': int(ln.get('slno') or i),
            'itemcode': ic,
            'itemname': (ln.get('itemname') or snap['itemname'] or '')[:250],
            'warehouse_id': ln.get('warehouse_id') or wh_id,
            'warehouse_code': (ln.get('warehouse_code') or wh_code or snap.get('warehouse_code') or '')[:30],
            'adjustment_dir': adj_dir,
            'quantity': float(ln.get('quantity') or 0),
            'uom': (ln.get('uom') or snap.get('uom') or '')[:20],
            'unit_cost': unit_cost,
            'adjustment_amount': adj_amt,
            'new_average_cost': new_avg,
            'current_qty': cur_qty,
            'current_avg_cost': cur_avg,
            'current_inv_value': cur_val,
            'fin_dim': (ln.get('fin_dim') or fin_dim or '')[:50],
            'lineremarks': (ln.get('lineremarks') or '')[:300],
        })

    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                if existing:
                    cur.execute(
                        f'DELETE FROM {DTL_TABLE} WHERE LOCATIONCODE = :lc AND JOURNALNO = :jno',
                        {'lc': lc, 'jno': jno},
                    )
                    cur.execute(
                        f"""
                        UPDATE {HDR_TABLE} SET
                            JOURNALNAME = :jname,
                            DESCRIPTION = :desc,
                            ADJUSTMENT_TYPE = :adj_type,
                            INVENTORY_MODEL = :inv_model,
                            JOURNAL_DATE = :jdate,
                            POSTING_DATE = :pdate,
                            WAREHOUSE_ID = :wh_id,
                            WAREHOUSE_CODE = :wh_code,
                            FIN_DIM = :fin_dim,
                            STATUS = :status,
                            POSTED = :posted,
                            NOTES = :notes,
                            REFERENCE = :ref,
                            ADJUSTMENT_REASON = :reason
                        WHERE LOCATIONCODE = :lc AND JOURNALNO = :jno
                        """,
                        {
                            'jname': jname, 'desc': desc, 'adj_type': adj_type, 'inv_model': inv_model,
                            'jdate': journal_date, 'pdate': posting_date,
                            'wh_id': wh_id, 'wh_code': wh_code, 'fin_dim': fin_dim,
                            'status': status, 'posted': posted_flag,
                            'notes': notes, 'ref': reference, 'reason': adj_reason,
                            'lc': lc, 'jno': jno,
                        },
                    )
                else:
                    cur.execute(
                        f"""
                        INSERT INTO {HDR_TABLE} (
                            LOCATIONCODE, JOURNALNO, JOURNALNAME, DESCRIPTION,
                            ADJUSTMENT_TYPE, INVENTORY_MODEL, JOURNAL_DATE, POSTING_DATE,
                            WAREHOUSE_ID, WAREHOUSE_CODE, FIN_DIM, STATUS, POSTED,
                            NOTES, REFERENCE, ADJUSTMENT_REASON,
                            CREATEDBY, CREATEDDATE, RESETNO
                        ) VALUES (
                            :lc, :jno, :jname, :desc,
                            :adj_type, :inv_model, :jdate, :pdate,
                            :wh_id, :wh_code, :fin_dim, :status, :posted,
                            :notes, :ref, :reason,
                            :user, SYSDATE, 1
                        )
                        """,
                        {
                            'lc': lc, 'jno': jno, 'jname': jname, 'desc': desc,
                            'adj_type': adj_type, 'inv_model': inv_model,
                            'jdate': journal_date, 'pdate': posting_date,
                            'wh_id': wh_id, 'wh_code': wh_code, 'fin_dim': fin_dim,
                            'status': status, 'posted': posted_flag,
                            'notes': notes, 'ref': reference, 'reason': adj_reason,
                            'user': (user or 'web')[:50],
                        },
                    )
                for ln in norm_lines:
                    cur.execute(
                        f"""
                        INSERT INTO {DTL_TABLE} (
                            LOCATIONCODE, JOURNALNO, SLNO, ITEMCODE, ITEMNAME,
                            WAREHOUSE_ID, WAREHOUSE_CODE, ADJUSTMENT_DIR, QUANTITY,
                            UNITOFMEASUREMENT, UNIT_COST, ADJUSTMENT_AMOUNT, NEW_AVERAGE_COST,
                            CURRENT_QTY, CURRENT_AVG_COST, CURRENT_INV_VALUE, FIN_DIM, LINEREMARKS
                        ) VALUES (
                            :lc, :jno, :sl, :ic, :iname,
                            :wh_id, :wh_code, :dir, :qty,
                            :uom, :uc, :adj, :new_avg,
                            :cq, :ca, :cv, :fd, :rmk
                        )
                        """,
                        {
                            'lc': lc, 'jno': jno, 'sl': ln['slno'], 'ic': ln['itemcode'],
                            'iname': ln['itemname'], 'wh_id': ln['warehouse_id'],
                            'wh_code': ln['warehouse_code'], 'dir': ln['adjustment_dir'],
                            'qty': ln['quantity'], 'uom': ln['uom'], 'uc': ln['unit_cost'],
                            'adj': ln['adjustment_amount'], 'new_avg': ln['new_average_cost'],
                            'cq': ln['current_qty'], 'ca': ln['current_avg_cost'],
                            'cv': ln['current_inv_value'], 'fd': ln['fin_dim'], 'rmk': ln['lineremarks'],
                        },
                    )
                if post:
                    _apply_post_cur(cur, lc, jno, norm_lines, user)
                    cur.execute(
                        f"""
                        UPDATE {HDR_TABLE}
                        SET STATUS = :st, POSTED = 'Y', POSTEDBY = :user, POSTEDDATE = SYSDATE
                        WHERE LOCATIONCODE = :lc AND JOURNALNO = :jno
                        """,
                        {'st': STATUS_POSTED, 'user': (user or 'web')[:50], 'lc': lc, 'jno': jno},
                    )
            conn.commit()
        return (True, 'Posted successfully.' if post else 'Saved successfully.', jno)
    except Exception as ex:
        _LOG.exception('save_journal failed')
        return (False, str(ex), jno)


def _apply_post_cur(cur, location_code: int, journal_no: int, lines: List[Dict[str, Any]], user: str) -> None:
    """Update ITEMMASTER average cost for each line."""
    for ln in lines:
        ic = int(ln['itemcode'])
        new_avg = float(ln['new_average_cost'] or 0)
        if new_avg <= 0:
            continue
        cur.execute(
            """
            SELECT COUNT(*) FROM user_tab_columns
            WHERE table_name = 'ITEMMASTER' AND column_name = 'AVERAGECOST'
            """
        )
        if int((cur.fetchone() or [0])[0] or 0) == 0:
            continue
        cur.execute(
            """
            UPDATE ITEMMASTER
            SET AVERAGECOST = :avg
            WHERE ITEMCODE = :ic
            """,
            {'avg': new_avg, 'ic': ic},
        )
