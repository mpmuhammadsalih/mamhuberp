"""Bank reconciliation tables and data access (tenant DB)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from db import _get_connection, _safe_rows, _table_exists

BANK_RECON_HDR = 'BANK_RECON_HDR'
BANK_RECON_BANK_LINE = 'BANK_RECON_BANK_LINE'
BANK_RECON_MATCH = 'BANK_RECON_MATCH'
BANK_RECON_SEQ = 'BANK_RECON_SEQ'


def ensure_bank_recon_tables() -> bool:
    if _table_exists(BANK_RECON_HDR):
        return True
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    CREATE TABLE {BANK_RECON_HDR} (
                        RECON_NO          NUMBER NOT NULL,
                        LOCATIONCODE      NUMBER NOT NULL,
                        BANK_ACCOUNT_CODE VARCHAR2(30) NOT NULL,
                        DATE_FROM         DATE,
                        DATE_TO           DATE,
                        DESCRIPTION       VARCHAR2(500),
                        ERP_OPENING       NUMBER(18,3) DEFAULT 0,
                        ERP_RECEIPTS      NUMBER(18,3) DEFAULT 0,
                        ERP_PAYMENTS      NUMBER(18,3) DEFAULT 0,
                        ERP_CLOSING       NUMBER(18,3) DEFAULT 0,
                        BANK_OPENING      NUMBER(18,3) DEFAULT 0,
                        BANK_CREDITS      NUMBER(18,3) DEFAULT 0,
                        BANK_DEBITS       NUMBER(18,3) DEFAULT 0,
                        BANK_CLOSING      NUMBER(18,3) DEFAULT 0,
                        STATUS            VARCHAR2(20) DEFAULT 'DRAFT',
                        NOTES             VARCHAR2(2000),
                        CREATED_BY        VARCHAR2(100),
                        CREATED_DATE      DATE DEFAULT SYSDATE,
                        MODIFIED_BY       VARCHAR2(100),
                        MODIFIED_DATE     DATE,
                        CONSTRAINT PK_BANK_RECON_HDR PRIMARY KEY (RECON_NO, LOCATIONCODE)
                    )
                    """
                )
                cur.execute(
                    f"""
                    CREATE TABLE {BANK_RECON_BANK_LINE} (
                        RECON_NO       NUMBER NOT NULL,
                        LOCATIONCODE   NUMBER NOT NULL,
                        LINE_NO        NUMBER NOT NULL,
                        TXN_DATE       DATE,
                        REFERENCE_NO   VARCHAR2(80),
                        DESCRIPTION    VARCHAR2(500),
                        DEPOSIT        NUMBER(18,3) DEFAULT 0,
                        PAYMENT        NUMBER(18,3) DEFAULT 0,
                        BALANCE        NUMBER(18,3),
                        CONSTRAINT PK_BANK_RECON_BANK_LINE PRIMARY KEY (RECON_NO, LOCATIONCODE, LINE_NO)
                    )
                    """
                )
                cur.execute(
                    f"""
                    CREATE TABLE {BANK_RECON_MATCH} (
                        RECON_NO       NUMBER NOT NULL,
                        LOCATIONCODE   NUMBER NOT NULL,
                        MATCH_ID       NUMBER NOT NULL,
                        ERP_KEY        VARCHAR2(80) NOT NULL,
                        BANK_LINE_NO   NUMBER NOT NULL,
                        MATCH_AMOUNT   NUMBER(18,3) DEFAULT 0,
                        MATCH_TYPE     VARCHAR2(20) DEFAULT 'MANUAL',
                        CREATED_BY     VARCHAR2(100),
                        CREATED_DATE   DATE DEFAULT SYSDATE,
                        CONSTRAINT PK_BANK_RECON_MATCH PRIMARY KEY (MATCH_ID),
                        CONSTRAINT UQ_BANK_RECON_MATCH UNIQUE (RECON_NO, LOCATIONCODE, ERP_KEY, BANK_LINE_NO)
                    )
                    """
                )
                cur.execute(
                    f"CREATE SEQUENCE {BANK_RECON_SEQ} START WITH 1 INCREMENT BY 1 NOCACHE"
                )
                cur.execute(
                    f"CREATE SEQUENCE BANK_RECON_MATCH_SEQ START WITH 1 INCREMENT BY 1 NOCACHE"
                )
            conn.commit()
        return True
    except Exception as ex:
        print(f'[ensure_bank_recon_tables] {ex}')
        return False


def _iso_date(val: Any) -> Optional[str]:
    if val is None or val == '':
        return None
    if hasattr(val, 'strftime'):
        return val.strftime('%Y-%m-%d')
    s = str(val).strip()[:10]
    if len(s) >= 10 and s[4] == '-':
        return s
    try:
        return datetime.strptime(s[:10], '%d/%m/%Y').strftime('%Y-%m-%d')
    except Exception:
        pass
    try:
        return datetime.strptime(s[:10], '%d-%b-%Y').strftime('%Y-%m-%d')
    except Exception:
        return s[:10] if s else None


def erp_line_key(voucher_no: str, line_no: Any) -> str:
    return f'{str(voucher_no or "").strip()}|{int(line_no or 0)}'


def next_recon_no(location_code: int) -> int:
    ensure_bank_recon_tables()
    rows = _safe_rows(
        f'SELECT NVL(MAX(RECON_NO), 0) + 1 AS n FROM {BANK_RECON_HDR} WHERE LOCATIONCODE = :loc',
        {'loc': int(location_code)},
    )
    return int((rows[0] or {}).get('n') or 1) if rows else 1


def list_recon_headers(location_code: int, limit: int = 50) -> List[Dict[str, Any]]:
    ensure_bank_recon_tables()
    lim = max(1, min(int(limit or 50), 200))
    rows = _safe_rows(
        f"""
        SELECT * FROM (
            SELECT RECON_NO, BANK_ACCOUNT_CODE, DATE_FROM, DATE_TO, STATUS, DESCRIPTION,
                   MODIFIED_DATE, CREATED_BY
            FROM {BANK_RECON_HDR}
            WHERE LOCATIONCODE = :loc
            ORDER BY RECON_NO DESC
        ) WHERE ROWNUM <= {lim}
        """,
        {'loc': int(location_code)},
    )
    out: List[Dict[str, Any]] = []
    for r in rows or []:
        out.append({
            'recon_no': int(r.get('recon_no') or 0),
            'bank_account_code': str(r.get('bank_account_code') or ''),
            'date_from': _iso_date(r.get('date_from')),
            'date_to': _iso_date(r.get('date_to')),
            'status': str(r.get('status') or 'DRAFT'),
            'description': str(r.get('description') or ''),
            'created_by': str(r.get('created_by') or ''),
        })
    return out


def get_recon_header(recon_no: int, location_code: int) -> Optional[Dict[str, Any]]:
    ensure_bank_recon_tables()
    rows = _safe_rows(
        f'SELECT * FROM {BANK_RECON_HDR} WHERE RECON_NO = :rno AND LOCATIONCODE = :loc',
        {'rno': int(recon_no), 'loc': int(location_code)},
    )
    if not rows:
        return None
    r = rows[0]
    return {
        'recon_no': int(r.get('recon_no') or 0),
        'locationcode': int(r.get('locationcode') or 0),
        'bank_account_code': str(r.get('bank_account_code') or ''),
        'date_from': _iso_date(r.get('date_from')),
        'date_to': _iso_date(r.get('date_to')),
        'description': str(r.get('description') or ''),
        'erp_opening': float(r.get('erp_opening') or 0),
        'erp_receipts': float(r.get('erp_receipts') or 0),
        'erp_payments': float(r.get('erp_payments') or 0),
        'erp_closing': float(r.get('erp_closing') or 0),
        'bank_opening': float(r.get('bank_opening') or 0),
        'bank_credits': float(r.get('bank_credits') or 0),
        'bank_debits': float(r.get('bank_debits') or 0),
        'bank_closing': float(r.get('bank_closing') or 0),
        'status': str(r.get('status') or 'DRAFT'),
        'notes': str(r.get('notes') or ''),
        'created_by': str(r.get('created_by') or ''),
        'created_date': _iso_date(r.get('created_date')),
        'modified_by': str(r.get('modified_by') or ''),
        'modified_date': _iso_date(r.get('modified_date')),
    }


def get_bank_lines(recon_no: int, location_code: int) -> List[Dict[str, Any]]:
    ensure_bank_recon_tables()
    rows = _safe_rows(
        f"""
        SELECT LINE_NO, TXN_DATE, REFERENCE_NO, DESCRIPTION, DEPOSIT, PAYMENT, BALANCE
        FROM {BANK_RECON_BANK_LINE}
        WHERE RECON_NO = :rno AND LOCATIONCODE = :loc
        ORDER BY LINE_NO
        """,
        {'rno': int(recon_no), 'loc': int(location_code)},
    )
    out: List[Dict[str, Any]] = []
    run = 0.0
    for r in rows or []:
        dep = float(r.get('deposit') or 0)
        pay = float(r.get('payment') or 0)
        bal = r.get('balance')
        if bal is not None and str(bal).strip() != '':
            run = float(bal)
        else:
            run = round(run + dep - pay, 2)
        out.append({
            'line_no': int(r.get('line_no') or 0),
            'txn_date': _iso_date(r.get('txn_date')),
            'reference_no': str(r.get('reference_no') or ''),
            'description': str(r.get('description') or ''),
            'deposit': round(dep, 2),
            'payment': round(pay, 2),
            'balance': round(run, 2),
        })
    return out


def get_matches(recon_no: int, location_code: int) -> List[Dict[str, Any]]:
    ensure_bank_recon_tables()
    rows = _safe_rows(
        f"""
        SELECT ERP_KEY, BANK_LINE_NO, MATCH_AMOUNT, MATCH_TYPE
        FROM {BANK_RECON_MATCH}
        WHERE RECON_NO = :rno AND LOCATIONCODE = :loc
        ORDER BY MATCH_ID
        """,
        {'rno': int(recon_no), 'loc': int(location_code)},
    )
    return [
        {
            'erp_key': str(r.get('erp_key') or ''),
            'bank_line_no': int(r.get('bank_line_no') or 0),
            'match_amount': float(r.get('match_amount') or 0),
            'match_type': str(r.get('match_type') or 'MANUAL'),
        }
        for r in rows or []
    ]


def save_recon(
    recon_no: int,
    location_code: int,
    bank_account_code: str,
    date_from: str,
    date_to: str,
    description: str,
    erp_totals: Dict[str, float],
    bank_totals: Dict[str, float],
    status: str,
    notes: str,
    bank_lines: List[Dict[str, Any]],
    matches: List[Dict[str, Any]],
    user: str,
    is_new: bool,
) -> int:
    ensure_bank_recon_tables()
    rno = int(recon_no or 0)
    loc = int(location_code)
    if rno <= 0:
        rno = next_recon_no(loc)
    ac = (bank_account_code or '').strip()[:30]
    st = (status or 'DRAFT').strip().upper()[:20] or 'DRAFT'
    usr = (user or 'web')[:100]
    df = date_from[:10] if date_from else None
    dt = date_to[:10] if date_to else None
    with _get_connection() as conn:
        with conn.cursor() as cur:
            if is_new:
                cur.execute(
                    f"""
                    INSERT INTO {BANK_RECON_HDR}
                    (RECON_NO, LOCATIONCODE, BANK_ACCOUNT_CODE, DATE_FROM, DATE_TO, DESCRIPTION,
                     ERP_OPENING, ERP_RECEIPTS, ERP_PAYMENTS, ERP_CLOSING,
                     BANK_OPENING, BANK_CREDITS, BANK_DEBITS, BANK_CLOSING,
                     STATUS, NOTES, CREATED_BY, CREATED_DATE)
                    VALUES
                    (:rno, :loc, :ac,
                     TO_DATE(:df, 'YYYY-MM-DD'), TO_DATE(:dt, 'YYYY-MM-DD'), :descr,
                     :eop, :erc, :epy, :ecl, :bop, :bcr, :bde, :bcl,
                     :st, :notes, :usr, SYSDATE)
                    """,
                    {
                        'rno': rno, 'loc': loc, 'ac': ac, 'df': df, 'dt': dt,
                        'descr': (description or '')[:500],
                        'eop': float(erp_totals.get('opening', 0)),
                        'erc': float(erp_totals.get('receipts', 0)),
                        'epy': float(erp_totals.get('payments', 0)),
                        'ecl': float(erp_totals.get('closing', 0)),
                        'bop': float(bank_totals.get('opening', 0)),
                        'bcr': float(bank_totals.get('credits', 0)),
                        'bde': float(bank_totals.get('debits', 0)),
                        'bcl': float(bank_totals.get('closing', 0)),
                        'st': st, 'notes': (notes or '')[:2000], 'usr': usr,
                    },
                )
            else:
                cur.execute(
                    f"""
                    UPDATE {BANK_RECON_HDR} SET
                        BANK_ACCOUNT_CODE = :ac,
                        DATE_FROM = TO_DATE(:df, 'YYYY-MM-DD'),
                        DATE_TO = TO_DATE(:dt, 'YYYY-MM-DD'),
                        DESCRIPTION = :descr,
                        ERP_OPENING = :eop, ERP_RECEIPTS = :erc, ERP_PAYMENTS = :epy, ERP_CLOSING = :ecl,
                        BANK_OPENING = :bop, BANK_CREDITS = :bcr, BANK_DEBITS = :bde, BANK_CLOSING = :bcl,
                        STATUS = :st, NOTES = :notes,
                        MODIFIED_BY = :usr, MODIFIED_DATE = SYSDATE
                    WHERE RECON_NO = :rno AND LOCATIONCODE = :loc
                    """,
                    {
                        'rno': rno, 'loc': loc, 'ac': ac, 'df': df, 'dt': dt,
                        'descr': (description or '')[:500],
                        'eop': float(erp_totals.get('opening', 0)),
                        'erc': float(erp_totals.get('receipts', 0)),
                        'epy': float(erp_totals.get('payments', 0)),
                        'ecl': float(erp_totals.get('closing', 0)),
                        'bop': float(bank_totals.get('opening', 0)),
                        'bcr': float(bank_totals.get('credits', 0)),
                        'bde': float(bank_totals.get('debits', 0)),
                        'bcl': float(bank_totals.get('closing', 0)),
                        'st': st, 'notes': (notes or '')[:2000], 'usr': usr,
                    },
                )
            cur.execute(
                f'DELETE FROM {BANK_RECON_BANK_LINE} WHERE RECON_NO = :rno AND LOCATIONCODE = :loc',
                {'rno': rno, 'loc': loc},
            )
            cur.execute(
                f'DELETE FROM {BANK_RECON_MATCH} WHERE RECON_NO = :rno AND LOCATIONCODE = :loc',
                {'rno': rno, 'loc': loc},
            )
            ln = 0
            for bl in bank_lines or []:
                ln += 1
                td = (bl.get('txn_date') or '')[:10] or None
                bind_bl = {
                    'rno': rno, 'loc': loc, 'ln': ln,
                    'ref': str(bl.get('reference_no') or '')[:80],
                    'dsc': str(bl.get('description') or '')[:500],
                    'dep': float(bl.get('deposit') or 0),
                    'pay': float(bl.get('payment') or 0),
                    'bal': float(bl.get('balance') or 0) if bl.get('balance') not in (None, '') else None,
                }
                if td:
                    bind_bl['td'] = td
                    cur.execute(
                        f"""
                        INSERT INTO {BANK_RECON_BANK_LINE}
                        (RECON_NO, LOCATIONCODE, LINE_NO, TXN_DATE, REFERENCE_NO, DESCRIPTION, DEPOSIT, PAYMENT, BALANCE)
                        VALUES (:rno, :loc, :ln, TO_DATE(:td, 'YYYY-MM-DD'), :ref, :dsc, :dep, :pay, :bal)
                        """,
                        bind_bl,
                    )
                else:
                    cur.execute(
                        f"""
                        INSERT INTO {BANK_RECON_BANK_LINE}
                        (RECON_NO, LOCATIONCODE, LINE_NO, TXN_DATE, REFERENCE_NO, DESCRIPTION, DEPOSIT, PAYMENT, BALANCE)
                        VALUES (:rno, :loc, :ln, NULL, :ref, :dsc, :dep, :pay, :bal)
                        """,
                        bind_bl,
                    )
            for m in matches or []:
                ek = str(m.get('erp_key') or '').strip()[:80]
                bln = int(m.get('bank_line_no') or 0)
                if not ek or bln <= 0:
                    continue
                cur.execute('SELECT BANK_RECON_MATCH_SEQ.NEXTVAL FROM DUAL')
                mid = int((cur.fetchone() or [0])[0])
                cur.execute(
                    f"""
                    INSERT INTO {BANK_RECON_MATCH}
                    (MATCH_ID, RECON_NO, LOCATIONCODE, ERP_KEY, BANK_LINE_NO, MATCH_AMOUNT, MATCH_TYPE, CREATED_BY)
                    VALUES (:mid, :rno, :loc, :ek, :bln, :amt, :mt, :usr)
                    """,
                    {
                        'mid': mid, 'rno': rno, 'loc': loc, 'ek': ek, 'bln': bln,
                        'amt': float(m.get('match_amount') or 0),
                        'mt': str(m.get('match_type') or 'MANUAL')[:20],
                        'usr': usr,
                    },
                )
        conn.commit()
    return rno


def delete_recon(recon_no: int, location_code: int) -> bool:
    ensure_bank_recon_tables()
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f'DELETE FROM {BANK_RECON_MATCH} WHERE RECON_NO = :rno AND LOCATIONCODE = :loc',
                {'rno': int(recon_no), 'loc': int(location_code)},
            )
            cur.execute(
                f'DELETE FROM {BANK_RECON_BANK_LINE} WHERE RECON_NO = :rno AND LOCATIONCODE = :loc',
                {'rno': int(recon_no), 'loc': int(location_code)},
            )
            cur.execute(
                f'DELETE FROM {BANK_RECON_HDR} WHERE RECON_NO = :rno AND LOCATIONCODE = :loc',
                {'rno': int(recon_no), 'loc': int(location_code)},
            )
        conn.commit()
    return True
