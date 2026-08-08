"""Missing customer recovery: lapsed buyers → assign → visit/feedback → recovered/closed.

Uses tenant DB only (BILLHDR/BILLHDRHISTORY + CUSTOMER + TBL_MISSING_CUSTOMER_RECOVERY).
"""
from __future__ import annotations
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from db import _detect_column, _fetch_rows, _get_connection, _table_exists
TBL_MISSING_CUSTOMER_RECOVERY = 'TBL_MISSING_CUSTOMER_RECOVERY'
STATUSES_OPEN = 'OPEN'
STATUSES_VISITED = 'VISITED'
STATUSES_RECOVERED = 'RECOVERED'
STATUSES_CLOSED = 'CLOSED'

def _hdr_table() -> Optional[str]:
    for cand in ('BILLHDRHISTORY', 'billhdrhistory', 'BILLHDR', 'billhdr'):
        if _table_exists(cand):
            return cand
    return None

def ensure_missing_customer_recovery_table() -> None:
    """Create recovery case table on tenant DB when missing."""
    try:
        if _table_exists(TBL_MISSING_CUSTOMER_RECOVERY):
            return
    except Exception:
        return
    ddl = f"\n    CREATE TABLE {TBL_MISSING_CUSTOMER_RECOVERY} (\n      CASE_ID VARCHAR2(36) NOT NULL,\n      CUSTOMER_CODE VARCHAR2(100) NOT NULL,\n      CUSTOMER_NAME VARCHAR2(500),\n      LAST_PURCHASE_DATE DATE,\n      BILL_COUNT NUMBER,\n      INACTIVE_DAYS_RULE NUMBER,\n      ASSIGNED_TO VARCHAR2(200),\n      STATUS VARCHAR2(30) DEFAULT '{STATUSES_OPEN}',\n      FEEDBACK VARCHAR2(4000),\n      VISIT_DATE DATE,\n      RECOVERED_AT DATE,\n      CLOSED_AT DATE,\n      CLOSE_REASON VARCHAR2(500),\n      CREATED_BY VARCHAR2(200),\n      CREATED_AT DATE DEFAULT SYSDATE,\n      UPDATED_AT DATE,\n      LOCATIONCODE NUMBER,\n      CONSTRAINT PK_TBL_MCR PRIMARY KEY (CASE_ID)\n    )\n    "
    idx1 = f'CREATE INDEX IDX_MCR_ASSIGNED ON {TBL_MISSING_CUSTOMER_RECOVERY} (ASSIGNED_TO, STATUS)'
    idx2 = f'CREATE INDEX IDX_MCR_CUST_ST ON {TBL_MISSING_CUSTOMER_RECOVERY} (CUSTOMER_CODE, STATUS)'
    try:
        with _get_connection() as conn:
            cur = conn.cursor()
            try:
                cur.execute(ddl)
            except Exception:
                pass
            for ix in (idx1, idx2):
                try:
                    cur.execute(ix)
                except Exception:
                    pass
            conn.commit()
    except Exception as exc:
        print(f'[missing_recovery] DDL skipped: {exc}')

def auto_recover_cases_with_new_sales() -> int:
    """
    Set status RECOVERED when the customer has an invoice newer than the case snapshot
    ``LAST_PURCHASE_DATE`` (OPEN/VISITED only). Uses same header table as lapsed detection.

    Location: if the case row has ``LOCATIONCODE``, only invoices at that location count;
    if null, any invoice for the customer in the tenant DB counts.

    Returns number of cases updated.
    """
    ensure_missing_customer_recovery_table()
    hdr = _hdr_table()
    if not hdr:
        return 0
    cc = _detect_column(hdr, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'CUSTCODE', 'CUST_CODE'])
    bd = _detect_column(hdr, ['BILLDATE', 'BILL_DATE', 'billdate'])
    loc_col = _detect_column(hdr, ['LOCATIONCODE', 'LOCATION_CODE', 'LOCCODE'])
    delflag_col = _detect_column(hdr, ['DELFLAG', 'DEL_FLAG', 'delflag'])
    if not cc or not bd:
        return 0
    del_exist = ''
    if delflag_col:
        del_exist = f" AND (h.{delflag_col} IS NULL OR UPPER(TRIM(h.{delflag_col})) NOT IN ('Y','V'))"
    loc_exist = ''
    if loc_col:
        loc_exist = f' AND (r.LOCATIONCODE IS NULL OR h.{loc_col} = r.LOCATIONCODE)'
    fb_concat = "CASE WHEN r.FEEDBACK IS NULL OR LENGTH(TRIM(r.FEEDBACK)) = 0 THEN '[Auto] Recovered: new invoice after snapshot.' ELSE SUBSTR(TRIM(r.FEEDBACK) || ' [Auto: new sale.]', 1, 4000) END"
    sql = f"\n    UPDATE {TBL_MISSING_CUSTOMER_RECOVERY} r\n    SET STATUS = '{STATUSES_RECOVERED}',\n        RECOVERED_AT = SYSDATE,\n        UPDATED_AT = SYSDATE,\n        FEEDBACK = {fb_concat}\n    WHERE r.STATUS IN ('{STATUSES_OPEN}', '{STATUSES_VISITED}')\n      AND r.LAST_PURCHASE_DATE IS NOT NULL\n      AND EXISTS (\n        SELECT 1\n        FROM {hdr} h\n        WHERE TRIM(h.{cc}) = TRIM(r.CUSTOMER_CODE)\n          AND h.{bd} > r.LAST_PURCHASE_DATE\n          {del_exist}\n          {loc_exist}\n      )\n    "
    try:
        with _get_connection() as conn:
            cur = conn.cursor()
            cur.execute(sql)
            n = int(cur.rowcount or 0)
            conn.commit()
            return n
    except Exception as e:
        print(f'[missing_recovery] auto_recover_cases_with_new_sales: {e}')
        return 0

def fetch_lapsed_customers(inactive_days: int, min_bills: int, location_code: Optional[int], exclude_open_cases: bool=True) -> List[Dict[str, Any]]:
    """
    Customers whose last invoice is older than ``inactive_days`` from today,
    with at least ``min_bills`` distinct bills in history.
    """
    ensure_missing_customer_recovery_table()
    hdr = _hdr_table()
    if not hdr:
        return []
    cc = _detect_column(hdr, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'CUSTCODE', 'CUST_CODE'])
    bd = _detect_column(hdr, ['BILLDATE', 'BILL_DATE', 'billdate'])
    bn = _detect_column(hdr, ['BILLNO', 'BILL_NO', 'billno'])
    cn = _detect_column(hdr, ['CUSTOMERNAME', 'CUSTOMER_NAME', 'CUST_NAME', 'NAME'])
    loc_col = _detect_column(hdr, ['LOCATIONCODE', 'LOCATION_CODE', 'LOCCODE'])
    delflag_col = _detect_column(hdr, ['DELFLAG', 'DEL_FLAG', 'delflag'])
    if not cc or not bd or (not bn):
        return []
    cust_tbl = None
    cust_code_col = None
    cust_name_col = None
    for t in ('CUSTOMER', 'CUSTOMERS', 'customers', 'customer'):
        if _table_exists(t):
            cust_tbl = t
            cust_code_col = _detect_column(t, ['CUST_CODE', 'CUSTOMERCODE', 'CUSTOMER_CODE', 'CODE'])
            cust_name_col = _detect_column(t, ['CUST_NAME', 'CUSTOMERNAME', 'CUSTOMER_NAME', 'NAME'])
            if cust_code_col:
                break
            cust_tbl = None
    del_clause = ''
    if delflag_col:
        del_clause = f" AND (h.{delflag_col} IS NULL OR UPPER(TRIM(h.{delflag_col})) NOT IN ('Y','V'))"
    loc_clause = ''
    params: Dict[str, Any] = {'inactive_days': max(1, int(inactive_days)), 'min_bills': max(1, int(min_bills))}
    if loc_col and location_code is not None:
        loc_clause = f' AND h.{loc_col} = :loc_code'
        params['loc_code'] = int(location_code)
    exclude_clause = ''
    if exclude_open_cases:
        exclude_clause = f"\n          AND NOT EXISTS (\n            SELECT 1 FROM {TBL_MISSING_CUSTOMER_RECOVERY} r\n            WHERE TRIM(r.CUSTOMER_CODE) = agg.customer_code\n              AND r.STATUS IN ('{STATUSES_OPEN}', '{STATUSES_VISITED}')\n          )\n        "
    cn_sel = f'MAX(h.{cn})' if cn else 'CAST(NULL AS VARCHAR2(500))'
    join_sql = ''
    name_expr = 'agg.NAME_FALLBACK'
    if cust_tbl and cust_code_col and cust_name_col:
        join_sql = f'\n        LEFT JOIN {cust_tbl} c ON TRIM(c.{cust_code_col}) = agg.customer_code\n        '
        name_expr = f"NVL(NULLIF(TRIM(c.{cust_name_col}), ''), agg.NAME_FALLBACK)"
    q = f'\n    SELECT agg.customer_code AS customer_code,\n           agg.last_purchase_date AS last_purchase_date,\n           agg.bill_count AS bill_count,\n           {name_expr} AS customer_name\n    FROM (\n      SELECT TRIM(h.{cc}) AS customer_code,\n             MAX(h.{bd}) AS last_purchase_date,\n             COUNT(DISTINCT h.{bn}) AS bill_count,\n             {cn_sel} AS NAME_FALLBACK\n      FROM {hdr} h\n      WHERE TRIM(h.{cc}) IS NOT NULL\n      {del_clause}\n      {loc_clause}\n      GROUP BY TRIM(h.{cc})\n      HAVING MAX(h.{bd}) < TRUNC(SYSDATE) - :inactive_days\n         AND COUNT(DISTINCT h.{bn}) >= :min_bills\n    ) agg\n    {join_sql}\n    WHERE 1 = 1\n    {exclude_clause}\n    ORDER BY agg.last_purchase_date ASC NULLS LAST\n    '
    try:
        _, rows = _fetch_rows(q, params)
        return list(rows or [])
    except Exception as e:
        print(f'[missing_recovery] fetch_lapsed_customers: {e}')
        return []

def snapshot_customer_header(customer_code: str, location_code: Optional[int]) -> Tuple[Optional[str], Optional[Any], int]:
    """Return (customer_name, last_purchase_date, bill_count) from header history."""
    hdr = _hdr_table()
    if not hdr:
        return (None, None, 0)
    cc = _detect_column(hdr, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'CUSTCODE'])
    bd = _detect_column(hdr, ['BILLDATE', 'BILL_DATE'])
    bn = _detect_column(hdr, ['BILLNO', 'BILL_NO'])
    cn = _detect_column(hdr, ['CUSTOMERNAME', 'CUSTOMER_NAME', 'CUST_NAME'])
    loc_col = _detect_column(hdr, ['LOCATIONCODE', 'LOCATION_CODE'])
    delflag_col = _detect_column(hdr, ['DELFLAG', 'DEL_FLAG'])
    if not cc or not bd or (not bn):
        return (None, None, 0)
    del_clause = ''
    if delflag_col:
        del_clause = f" AND (h.{delflag_col} IS NULL OR UPPER(TRIM(h.{delflag_col})) NOT IN ('Y','V'))"
    loc_clause = ''
    params: Dict[str, Any] = {'cust': str(customer_code).strip()}
    if loc_col and location_code is not None:
        loc_clause = f' AND h.{loc_col} = :loc_code'
        params['loc_code'] = int(location_code)
    cn_agg = f'MAX(h.{cn})' if cn else 'CAST(NULL AS VARCHAR2(500))'
    q = f'\n    SELECT MAX(h.{bd}) AS last_purchase_date,\n           COUNT(DISTINCT h.{bn}) AS bill_count,\n           {cn_agg} AS customer_name\n    FROM {hdr} h\n    WHERE TRIM(h.{cc}) = TRIM(:cust)\n    {del_clause}\n    {loc_clause}\n    '
    try:
        _, rows = _fetch_rows(q, params)
        if not rows:
            return (None, None, 0)
        r = rows[0]
        return (str(r.get('customer_name') or '').strip() or None, r.get('last_purchase_date'), int(r.get('bill_count') or 0))
    except Exception:
        return (None, None, 0)

def upsert_open_case(customer_code: str, assignee: str, inactive_days_rule: int, created_by: str, location_code: Optional[int]) -> Tuple[bool, str]:
    """Create or refresh an OPEN/VISITED assignment for this customer."""
    ensure_missing_customer_recovery_table()
    code = str(customer_code or '').strip()
    if not code or not str(assignee or '').strip():
        return (False, 'Customer and assignee are required.')
    name, last_dt, bill_cnt = snapshot_customer_header(code, location_code)
    now = datetime.now()
    with _get_connection() as conn:
        cur = conn.cursor()
        cur.execute(f'\n            SELECT CASE_ID FROM {TBL_MISSING_CUSTOMER_RECOVERY}\n            WHERE TRIM(CUSTOMER_CODE) = TRIM(:c)\n              AND STATUS IN (:s1, :s2)\n            ', {'c': code, 's1': STATUSES_OPEN, 's2': STATUSES_VISITED})
        row = cur.fetchone()
        if row and row[0]:
            cur.execute(f'\n                UPDATE {TBL_MISSING_CUSTOMER_RECOVERY}\n                SET ASSIGNED_TO = :a,\n                    LAST_PURCHASE_DATE = :lp,\n                    CUSTOMER_NAME = :nm,\n                    BILL_COUNT = :bc,\n                    INACTIVE_DAYS_RULE = :idr,\n                    UPDATED_AT = :ua,\n                    LOCATIONCODE = :loc\n                WHERE CASE_ID = :cid\n                ', {'a': assignee.strip(), 'lp': last_dt, 'nm': name or '', 'bc': bill_cnt, 'idr': inactive_days_rule, 'ua': now, 'loc': location_code, 'cid': row[0]})
        else:
            cid = str(uuid.uuid4())
            cur.execute(f'\n                INSERT INTO {TBL_MISSING_CUSTOMER_RECOVERY} (\n                  CASE_ID, CUSTOMER_CODE, CUSTOMER_NAME, LAST_PURCHASE_DATE, BILL_COUNT,\n                  INACTIVE_DAYS_RULE, ASSIGNED_TO, STATUS, CREATED_BY, CREATED_AT, UPDATED_AT, LOCATIONCODE\n                ) VALUES (\n                  :cid, :cc, :nm, :lp, :bc, :idr, :a, :st, :cb, :ca, :ua, :loc\n                )\n                ', {'cid': cid, 'cc': code, 'nm': name or '', 'lp': last_dt, 'bc': bill_cnt, 'idr': inactive_days_rule, 'a': assignee.strip(), 'st': STATUSES_OPEN, 'cb': created_by, 'ca': now, 'ua': now, 'loc': location_code})
        conn.commit()
    return (True, '')

def list_recovery_cases(assigned_to: Optional[str]=None, statuses: Optional[List[str]]=None, limit: int=500) -> List[Dict[str, Any]]:
    ensure_missing_customer_recovery_table()
    where = []
    params: Dict[str, Any] = {}
    if assigned_to:
        where.append('UPPER(TRIM(ASSIGNED_TO)) = UPPER(TRIM(:asg))')
        params['asg'] = assigned_to.strip()
    if statuses:
        ph = ','.join([f':st{i}' for i in range(len(statuses))])
        for i, s in enumerate(statuses):
            params[f'st{i}'] = s
        where.append(f'STATUS IN ({ph})')
    wh = 'WHERE ' + ' AND '.join(where) if where else ''
    params['lim'] = max(1, min(limit, 2000))
    q = f"\n    SELECT CASE_ID, CUSTOMER_CODE, CUSTOMER_NAME, LAST_PURCHASE_DATE, BILL_COUNT,\n           INACTIVE_DAYS_RULE, ASSIGNED_TO, STATUS, FEEDBACK, VISIT_DATE,\n           RECOVERED_AT, CLOSED_AT, CLOSE_REASON, CREATED_BY, CREATED_AT, UPDATED_AT, LOCATIONCODE\n    FROM (\n      SELECT x.*,\n             ROW_NUMBER() OVER (\n               ORDER BY DECODE(STATUS, '{STATUSES_OPEN}', 1, '{STATUSES_VISITED}', 2, 3),\n                        NVL(UPDATED_AT, CREATED_AT) DESC\n             ) AS mcr_rn\n      FROM {TBL_MISSING_CUSTOMER_RECOVERY} x\n      {wh}\n    )\n    WHERE mcr_rn <= :lim\n    "
    try:
        _, rows = _fetch_rows(q, params)
        return list(rows or [])
    except Exception as e:
        print(f'[missing_recovery] list_recovery_cases: {e}')
        return []

def update_recovery_case(case_id: str, actor_username: str, feedback: str, visit_date_raw: Optional[str], action: str, close_reason: str='') -> Tuple[bool, str]:
    """action: visit | recover | close"""
    ensure_missing_customer_recovery_table()
    cid = str(case_id or '').strip()
    if not cid:
        return (False, 'Missing case.')
    act = (action or '').strip().lower()
    if act not in ('visit', 'recover', 'close'):
        return (False, 'Invalid action.')
    _, rows_q = _fetch_rows(f'\n        SELECT CASE_ID, ASSIGNED_TO, STATUS FROM {TBL_MISSING_CUSTOMER_RECOVERY}\n        WHERE CASE_ID = :cid\n        ', {'cid': cid})
    target = rows_q[0] if rows_q else None
    if not target:
        return (False, 'Case not found.')
    assigned = str(target.get('assigned_to') or '').strip()
    actor = str(actor_username or '').strip()
    if assigned and actor and (assigned.upper() != actor.upper()):
        return (False, 'You can only update cases assigned to you.')
    status = str(target.get('status') or '').upper()
    if status in (STATUSES_RECOVERED, STATUSES_CLOSED):
        return (False, 'Case is already closed or recovered.')
    now = datetime.now()
    visit_dt = None
    if visit_date_raw and str(visit_date_raw).strip():
        try:
            visit_dt = datetime.strptime(str(visit_date_raw).strip()[:10], '%Y-%m-%d')
        except ValueError:
            return (False, 'Invalid visit date.')
    fb = (feedback or '').strip()[:4000]
    cr = (close_reason or '').strip()[:500]
    new_status = status
    recovered_at = None
    closed_at = None
    if act == 'visit':
        new_status = STATUSES_VISITED
    elif act == 'recover':
        new_status = STATUSES_RECOVERED
        recovered_at = now
    elif act == 'close':
        new_status = STATUSES_CLOSED
        closed_at = now
    with _get_connection() as conn:
        cur = conn.cursor()
        cur.execute(f"\n            UPDATE {TBL_MISSING_CUSTOMER_RECOVERY}\n            SET STATUS = :st,\n                FEEDBACK = :fb,\n                VISIT_DATE = :vd,\n                RECOVERED_AT = NVL(:ra, RECOVERED_AT),\n                CLOSED_AT = NVL(:ca, CLOSED_AT),\n                CLOSE_REASON = CASE WHEN :st = '{STATUSES_CLOSED}' THEN :cr ELSE CLOSE_REASON END,\n                UPDATED_AT = :ua\n            WHERE CASE_ID = :cid\n            ", {'st': new_status, 'fb': fb, 'vd': visit_dt, 'ra': recovered_at, 'ca': closed_at, 'cr': cr, 'ua': now, 'cid': cid})
        conn.commit()
    return (True, '')
