"""
Period Closing — AccountingPeriod / ClosingLog + preview, validation, close, reopen.

Tenant DB tables (Oracle):
  ACCOUNTING_PERIOD — monthly periods for a financial year
  CLOSING_LOG       — audit history of closes / reopens
"""
from __future__ import annotations

import calendar
import logging
import os
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from db import (
    PRIVILEGED_USERS,
    _detect_column,
    _detect_table,
    _get_connection,
    _safe_rows,
    _table_exists,
    create_gl_journal_entry,
    get_account_ledger,
    get_all_chart_of_accounts,
    get_gl_voucher_detail,
    get_gl_voucher_reversal_no,
    get_item_store_inventory,
    get_item_store_rows_from_itemmaster,
    get_profit_and_loss_report,
    get_trial_balance_report,
    get_user_role_id,
    reverse_gl_journal_voucher,
)

logger = logging.getLogger(__name__)

ACCOUNTING_PERIOD_TABLE = 'ACCOUNTING_PERIOD'
ACCOUNTING_PERIOD_SEQ = 'ACCOUNTING_PERIOD_SEQ'
CLOSING_LOG_TABLE = 'CLOSING_LOG'
CLOSING_LOG_SEQ = 'CLOSING_LOG_SEQ'

STATUS_OPEN = 'OPEN'
STATUS_CLOSED = 'CLOSED'
STATUS_REOPENED = 'REOPENED'

CLOSE_MONTHLY = 'MONTHLY'
CLOSE_YEAR_END = 'YEAR_END'

RETAINED_EARNINGS_DEFAULT = (os.environ.get('RETAINED_EARNINGS_ACCOUNT') or '3200').strip() or '3200'
BALANCE_TOL = 0.02

MONTH_NAMES = (
    '', 'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
)


# ---------------------------------------------------------------------------
# Table ensure
# ---------------------------------------------------------------------------

def ensure_period_closing_tables() -> bool:
    """Create ACCOUNTING_PERIOD and CLOSING_LOG if missing. Idempotent."""
    ok = True
    try:
        from db import _TABLE_EXISTS_CACHE  # invalidate after DDL
        created_period = False
        created_log = False
        with _get_connection() as conn:
            with conn.cursor() as cur:
                if not _table_exists(ACCOUNTING_PERIOD_TABLE):
                    cur.execute(
                        f"""
                        CREATE TABLE {ACCOUNTING_PERIOD_TABLE} (
                            PERIOD_ID        NUMBER NOT NULL,
                            FINANCIAL_YEAR   VARCHAR2(20) NOT NULL,
                            MONTH            NUMBER(2) NOT NULL,
                            START_DATE       DATE NOT NULL,
                            END_DATE         DATE NOT NULL,
                            STATUS           VARCHAR2(20) DEFAULT 'OPEN' NOT NULL,
                            CLOSED_BY        VARCHAR2(100),
                            CLOSED_DATE      DATE,
                            CLOSING_NUMBER   VARCHAR2(40),
                            CLOSING_TYPE     VARCHAR2(20),
                            LOCATIONCODE     NUMBER,
                            CREATED_DATE     DATE DEFAULT SYSDATE,
                            CONSTRAINT PK_ACCOUNTING_PERIOD PRIMARY KEY (PERIOD_ID),
                            CONSTRAINT UQ_ACCT_PERIOD UNIQUE (FINANCIAL_YEAR, MONTH, LOCATIONCODE)
                        )
                        """
                    )
                    created_period = True
                cur.execute(
                    "SELECT 1 FROM user_sequences WHERE sequence_name = :n",
                    {'n': ACCOUNTING_PERIOD_SEQ},
                )
                if not cur.fetchone():
                    cur.execute(
                        f"CREATE SEQUENCE {ACCOUNTING_PERIOD_SEQ} START WITH 1 INCREMENT BY 1 NOCACHE"
                    )

                if not _table_exists(CLOSING_LOG_TABLE):
                    cur.execute(
                        f"""
                        CREATE TABLE {CLOSING_LOG_TABLE} (
                            LOG_ID           NUMBER NOT NULL,
                            CLOSING_NUMBER   VARCHAR2(40) NOT NULL,
                            FINANCIAL_YEAR   VARCHAR2(20) NOT NULL,
                            PERIOD_LABEL     VARCHAR2(40) NOT NULL,
                            MONTH            NUMBER(2),
                            REVENUE          NUMBER(18,2) DEFAULT 0,
                            EXPENSES         NUMBER(18,2) DEFAULT 0,
                            PROFIT           NUMBER(18,2) DEFAULT 0,
                            GROSS_PROFIT     NUMBER(18,2) DEFAULT 0,
                            RETAINED_EARNINGS NUMBER(18,2) DEFAULT 0,
                            CLOSING_TYPE     VARCHAR2(20) NOT NULL,
                            CLOSED_BY        VARCHAR2(100),
                            CLOSED_DATE      DATE,
                            STATUS           VARCHAR2(20) DEFAULT 'CLOSED',
                            REOPEN_REASON    VARCHAR2(500),
                            REOPENED_BY      VARCHAR2(100),
                            REOPENED_DATE    DATE,
                            VOUCHER_NO       VARCHAR2(40),
                            LOCATIONCODE     NUMBER,
                            CREATED_DATE     DATE DEFAULT SYSDATE,
                            CONSTRAINT PK_CLOSING_LOG PRIMARY KEY (LOG_ID)
                        )
                        """
                    )
                    created_log = True
                cur.execute(
                    "SELECT 1 FROM user_sequences WHERE sequence_name = :n",
                    {'n': CLOSING_LOG_SEQ},
                )
                if not cur.fetchone():
                    cur.execute(
                        f"CREATE SEQUENCE {CLOSING_LOG_SEQ} START WITH 1 INCREMENT BY 1 NOCACHE"
                    )
            conn.commit()
        if created_period:
            _TABLE_EXISTS_CACHE.pop(ACCOUNTING_PERIOD_TABLE.upper(), None)
            _TABLE_EXISTS_CACHE[ACCOUNTING_PERIOD_TABLE.upper()] = True
        if created_log:
            _TABLE_EXISTS_CACHE.pop(CLOSING_LOG_TABLE.upper(), None)
            _TABLE_EXISTS_CACHE[CLOSING_LOG_TABLE.upper()] = True
    except Exception as ex:
        logger.exception('ensure_period_closing_tables failed: %s', ex)
        ok = False
    return ok


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _f(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _si(v: Any) -> int:
    try:
        return int(float(v or 0))
    except (TypeError, ValueError):
        return 0


def _iso(d: Any) -> str:
    if d is None:
        return ''
    if hasattr(d, 'strftime'):
        return d.strftime('%Y-%m-%d')
    s = str(d).strip()
    return s[:10] if s else ''


def period_label(year: int, month: int) -> str:
    m = MONTH_NAMES[month] if 1 <= month <= 12 else str(month)
    return f'{m} {year}'


def resolve_retained_earnings_code() -> str:
    """Prefer configured 3200; fall back to first EQUITY postable account."""
    preferred = [
        RETAINED_EARNINGS_DEFAULT,
        '3200', '3100', '3000',
    ]
    codes = {str(a.get('code') or '').strip().upper(): str(a.get('code') or '').strip()
             for a in (get_all_chart_of_accounts() or []) if (a.get('code') or '').strip()}
    for p in preferred:
        if p.upper() in codes:
            return codes[p.upper()]
    for a in get_all_chart_of_accounts() or []:
        if (a.get('type') or '').upper() == 'EQUITY' and a.get('is_postable'):
            c = str(a.get('code') or '').strip()
            if c:
                return c
    return RETAINED_EARNINGS_DEFAULT


def is_period_closing_admin(username: Optional[str] = None, role_id: Optional[str] = None) -> bool:
    """Administrator: privileged usernames or role_id admin/null (allow-all)."""
    u = str(username or '').strip().lower()
    if u in PRIVILEGED_USERS or u == 'admin':
        return True
    rid = str(role_id or '').strip().lower()
    if rid in ('admin', 'administrator', 'super', 'superadmin'):
        return True
    if role_id is None and u:
        # Mirror app.py: role_id None ⇒ allow_all for some deployments
        try:
            actual = get_user_role_id(username or '')
            if actual is None and u in PRIVILEGED_USERS:
                return True
            rid2 = str(actual or '').strip().lower()
            return rid2 in ('admin', 'administrator', 'super', 'superadmin')
        except Exception:
            pass
    return False


def can_close_period(username: Optional[str] = None, role_id: Optional[str] = None) -> bool:
    return is_period_closing_admin(username, role_id)


def can_reopen_period(username: Optional[str] = None, role_id: Optional[str] = None) -> bool:
    return is_period_closing_admin(username, role_id)


def can_preview_period(username: Optional[str] = None, role_id: Optional[str] = None) -> bool:
    """Account managers and admins can preview; callers also gate via menu permission."""
    if is_period_closing_admin(username, role_id):
        return True
    rid = str(role_id or '').strip().lower()
    if 'account' in rid or 'manager' in rid or 'accountant' in rid:
        return True
    try:
        actual = get_user_role_id(username or '')
        r = str(actual or '').strip().lower()
        return 'account' in r or 'manager' in r or 'accountant' in r or is_period_closing_admin(username, actual)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Period rows
# ---------------------------------------------------------------------------

def _month_bounds(year: int, month: int) -> Tuple[str, str]:
    last = calendar.monthrange(year, month)[1]
    return (f'{year:04d}-{month:02d}-01', f'{year:04d}-{month:02d}-{last:02d}')


def ensure_periods_for_year(financial_year: str, location_code: int = 1) -> List[Dict[str, Any]]:
    """Ensure 12 monthly period rows exist for a calendar/FY code (e.g. 2026 or 2025-2026)."""
    ensure_period_closing_tables()
    fy = (financial_year or '').strip()
    if not fy:
        fy = str(datetime.now().year)
    loc = int(location_code or 1)
    # Resolve calendar year for month generation
    year_num = _si(fy[:4]) or datetime.now().year
    # If FY like 2025-2026, months Apr–Mar style if DATE_FROM suggests it
    start_month = 1
    try:
        from addons.fiscal_year.fiscal_year_db import list_fiscal_years
        for row in list_fiscal_years(include_closed=True) or []:
            code = str(row.get('year_code') or row.get('YEAR_CODE') or '').strip()
            name = str(row.get('year_name') or row.get('YEAR_NAME') or '').strip()
            if code == fy or name == fy or code == fy.replace(' ', ''):
                df = _iso(row.get('date_from') or row.get('DATE_FROM'))
                if df and len(df) >= 7:
                    year_num = _si(df[:4]) or year_num
                    start_month = _si(df[5:7]) or 1
                break
    except Exception:
        pass

    months: List[Tuple[int, int]] = []
    y, m = year_num, start_month
    for _ in range(12):
        months.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1

    # Load existing months from DB (same connection path as inserts)
    existing_months: set = set()
    if _table_exists(ACCOUNTING_PERIOD_TABLE):
        rows = _safe_rows(
            f"""
            SELECT MONTH AS month
            FROM {ACCOUNTING_PERIOD_TABLE}
            WHERE FINANCIAL_YEAR = :fy
              AND NVL(LOCATIONCODE, :loc) = :loc
            """,
            {'fy': fy, 'loc': loc},
        ) or []
        existing_months = {_si(r.get('month')) for r in rows if _si(r.get('month')) > 0}

    with _get_connection() as conn:
        with conn.cursor() as cur:
            for cal_y, mon in months:
                if mon in existing_months:
                    continue
                sd, ed = _month_bounds(cal_y, mon)
                try:
                    # MERGE avoids ORA-00001 when rows already exist (cache races / double ensure)
                    cur.execute(
                        f"""
                        MERGE INTO {ACCOUNTING_PERIOD_TABLE} t
                        USING (
                            SELECT :fy AS FINANCIAL_YEAR, :m AS MONTH, :loc AS LOCATIONCODE FROM dual
                        ) s
                        ON (
                            t.FINANCIAL_YEAR = s.FINANCIAL_YEAR
                            AND t.MONTH = s.MONTH
                            AND NVL(t.LOCATIONCODE, -1) = NVL(s.LOCATIONCODE, -1)
                        )
                        WHEN NOT MATCHED THEN INSERT (
                            PERIOD_ID, FINANCIAL_YEAR, MONTH, START_DATE, END_DATE,
                            STATUS, LOCATIONCODE, CREATED_DATE
                        ) VALUES (
                            {ACCOUNTING_PERIOD_SEQ}.NEXTVAL, :fy2, :m2,
                            TO_DATE(:sd, 'YYYY-MM-DD'), TO_DATE(:ed, 'YYYY-MM-DD'),
                            :st, :loc2, SYSDATE
                        )
                        """,
                        {
                            'fy': fy, 'm': mon, 'loc': loc,
                            'fy2': fy, 'm2': mon, 'loc2': loc,
                            'sd': sd, 'ed': ed, 'st': STATUS_OPEN,
                        },
                    )
                    existing_months.add(mon)
                except Exception as ex:
                    # Ignore unique violations; re-raise anything else
                    msg = str(ex).upper()
                    if 'ORA-00001' in msg or 'UNIQUE CONSTRAINT' in msg:
                        existing_months.add(mon)
                        continue
                    raise
        conn.commit()
    return list_periods(fy, loc)


def list_periods(financial_year: str, location_code: int = 1) -> List[Dict[str, Any]]:
    ensure_period_closing_tables()
    if not _table_exists(ACCOUNTING_PERIOD_TABLE):
        return []
    rows = _safe_rows(
        f"""
        SELECT PERIOD_ID, FINANCIAL_YEAR, MONTH, START_DATE, END_DATE, STATUS,
               CLOSED_BY, CLOSED_DATE, CLOSING_NUMBER, CLOSING_TYPE, LOCATIONCODE
        FROM {ACCOUNTING_PERIOD_TABLE}
        WHERE FINANCIAL_YEAR = :fy
          AND (LOCATIONCODE IS NULL OR LOCATIONCODE = :loc)
        ORDER BY START_DATE, MONTH
        """,
        {'fy': (financial_year or '').strip(), 'loc': location_code},
    ) or []
    out: List[Dict[str, Any]] = []
    for r in rows:
        mon = _si(r.get('month'))
        sd = _iso(r.get('start_date'))
        y = _si(sd[:4]) if sd else datetime.now().year
        out.append({
            'period_id': r.get('period_id'),
            'financial_year': str(r.get('financial_year') or ''),
            'month': mon,
            'period_label': period_label(y, mon),
            'start_date': sd,
            'end_date': _iso(r.get('end_date')),
            'status': str(r.get('status') or STATUS_OPEN).upper(),
            'closed_by': r.get('closed_by') or '',
            'closed_date': _iso(r.get('closed_date')),
            'closing_number': r.get('closing_number') or '',
            'closing_type': r.get('closing_type') or '',
        })
    return out


def get_period(financial_year: str, month: int, location_code: int = 1) -> Optional[Dict[str, Any]]:
    for p in list_periods(financial_year, location_code):
        if _si(p.get('month')) == _si(month):
            return p
    return None


def get_period_by_id(period_id: int) -> Optional[Dict[str, Any]]:
    ensure_period_closing_tables()
    rows = _safe_rows(
        f"""
        SELECT PERIOD_ID, FINANCIAL_YEAR, MONTH, START_DATE, END_DATE, STATUS,
               CLOSED_BY, CLOSED_DATE, CLOSING_NUMBER, CLOSING_TYPE, LOCATIONCODE
        FROM {ACCOUNTING_PERIOD_TABLE}
        WHERE PERIOD_ID = :id
        """,
        {'id': period_id},
    ) or []
    if not rows:
        return None
    r = rows[0]
    mon = _si(r.get('month'))
    sd = _iso(r.get('start_date'))
    y = _si(sd[:4]) if sd else datetime.now().year
    return {
        'period_id': r.get('period_id'),
        'financial_year': str(r.get('financial_year') or ''),
        'month': mon,
        'period_label': period_label(y, mon),
        'start_date': sd,
        'end_date': _iso(r.get('end_date')),
        'status': str(r.get('status') or STATUS_OPEN).upper(),
        'closed_by': r.get('closed_by') or '',
        'closed_date': _iso(r.get('closed_date')),
        'closing_number': r.get('closing_number') or '',
        'closing_type': r.get('closing_type') or '',
        'locationcode': r.get('locationcode'),
    }


def _session_location_code(default: int = 1) -> int:
    try:
        from nexa_http import has_request_context, session
        if has_request_context():
            return int(session.get('location_code') or default)
    except Exception:
        pass
    return int(default or 1)


def is_period_closed_for_date(
    voucher_date: Optional[str],
    location_code: Optional[int] = None,
) -> Optional[str]:
    """
    Return error message if ``voucher_date`` falls in a CLOSED accounting period.
    Returns None if open / unknown / tables missing (fail-open for missing tables).

    When *location_code* is omitted, uses the current session branch.
    """
    d = _iso(voucher_date)
    if not d or len(d) < 10:
        return None
    if not _table_exists(ACCOUNTING_PERIOD_TABLE):
        return None
    loc = _session_location_code(1) if location_code is None else int(location_code)
    rows = _safe_rows(
        f"""
        SELECT FINANCIAL_YEAR, MONTH, STATUS, START_DATE, END_DATE
        FROM {ACCOUNTING_PERIOD_TABLE}
        WHERE TRUNC(TO_DATE(:d, 'YYYY-MM-DD')) BETWEEN TRUNC(START_DATE) AND TRUNC(END_DATE)
          AND UPPER(NVL(STATUS, 'OPEN')) = 'CLOSED'
          AND (LOCATIONCODE IS NULL OR LOCATIONCODE = :loc)
          AND ROWNUM = 1
        """,
        {'d': d, 'loc': loc},
    ) or []
    if not rows:
        return None
    r = rows[0]
    mon = _si(r.get('month'))
    sd = _iso(r.get('start_date'))
    y = _si(sd[:4]) if sd else _si(d[:4])
    return f'Accounting period {period_label(y, mon)} is closed. No transactions can be posted in this period.'


def list_closed_periods(
    location_code: Optional[int] = None,
    limit: int = 240,
) -> List[Dict[str, Any]]:
    """Closed period ranges for UI date guards (Journal Entry, etc.)."""
    ensure_period_closing_tables()
    if not _table_exists(ACCOUNTING_PERIOD_TABLE):
        return []
    loc = _session_location_code(1) if location_code is None else int(location_code)
    rows = _safe_rows(
        f"""
        SELECT * FROM (
            SELECT FINANCIAL_YEAR, MONTH, START_DATE, END_DATE, STATUS, LOCATIONCODE
              FROM {ACCOUNTING_PERIOD_TABLE}
             WHERE UPPER(NVL(STATUS, 'OPEN')) = 'CLOSED'
               AND (LOCATIONCODE IS NULL OR LOCATIONCODE = :loc)
             ORDER BY START_DATE DESC NULLS LAST, MONTH DESC
        ) WHERE ROWNUM <= :lim
        """,
        {'loc': loc, 'lim': max(1, min(int(limit or 240), 500))},
    ) or []
    out: List[Dict[str, Any]] = []
    for r in rows:
        mon = _si(r.get('month'))
        sd = _iso(r.get('start_date'))
        ed = _iso(r.get('end_date'))
        y = _si(sd[:4]) if sd else datetime.now().year
        out.append({
            'financial_year': str(r.get('financial_year') or ''),
            'month': mon,
            'period_label': period_label(y, mon),
            'start_date': sd,
            'end_date': ed,
            'status': STATUS_CLOSED,
        })
    return out


def resolve_open_voucher_date(
    preferred: Optional[str] = None,
    location_code: Optional[int] = None,
) -> str:
    """Return *preferred* (or today) if open; otherwise the next open calendar day."""
    loc = _session_location_code(1) if location_code is None else int(location_code)
    d = _iso(preferred) or datetime.now().strftime('%Y-%m-%d')
    if not is_period_closed_for_date(d, loc):
        return d[:10]
    try:
        cur = datetime.strptime(d[:10], '%Y-%m-%d').date()
    except ValueError:
        cur = datetime.now().date()
    for _ in range(400):
        cur = cur + timedelta(days=1)
        cand = cur.strftime('%Y-%m-%d')
        if not is_period_closed_for_date(cand, loc):
            return cand
    return datetime.now().strftime('%Y-%m-%d')


def next_closing_number(financial_year: str) -> str:
    ensure_period_closing_tables()
    fy = (financial_year or datetime.now().strftime('%Y')).strip()
    rows = _safe_rows(
        f"""
        SELECT NVL(MAX(TO_NUMBER(REGEXP_SUBSTR(CLOSING_NUMBER, '[0-9]+$'))), 0) AS n
        FROM {CLOSING_LOG_TABLE}
        WHERE FINANCIAL_YEAR = :fy
        """,
        {'fy': fy},
    ) or []
    n = _si((rows[0] or {}).get('n')) + 1 if rows else 1
    safe = ''.join(ch if ch.isalnum() else '' for ch in fy)[:12] or 'FY'
    return f'CL-{safe}-{n:04d}'


# ---------------------------------------------------------------------------
# Preview / P&L metrics
# ---------------------------------------------------------------------------

def _is_cogs_account(code: str, name: str) -> bool:
    c = (code or '').strip().upper()
    n = (name or '').strip().upper()
    if 'COGS' in n or 'COST OF GOODS' in n or 'COST OF SALES' in n:
        return True
    if c.startswith('51') or c.startswith('500') or c == '5100' or c == '5199':
        return True
    return False


def build_closing_preview(date_from: str, date_to: str) -> Dict[str, Any]:
    """KPI + P&L + journal preview for a period date range."""
    pl = get_profit_and_loss_report(date_from=date_from, date_to=date_to) or {}
    revenue = _f(pl.get('total_revenue'))
    expenses = _f(pl.get('total_expense'))
    net_profit = _f(pl.get('net_profit'))
    # Prefer P&L GP (Revenue − COGS − Inventory Adjustment); fall back to local split.
    if pl.get('gross_profit') is not None and (
        pl.get('total_cost_of_sales') is not None or pl.get('cost_of_sales_accounts') is not None
    ):
        cogs = _f(pl.get('total_cost_of_sales'))
        other_exp = _f(pl.get('total_operating_expense'))
        if not other_exp and not cogs:
            other_exp = expenses
        gross_profit = _f(pl.get('gross_profit'))
    else:
        cogs = 0.0
        other_exp = 0.0
        for r in pl.get('expense_accounts') or []:
            amt = _f(r.get('amount'))  # signed (inv. adj. may reduce cost of sales)
            if _is_cogs_account(str(r.get('code') or ''), str(r.get('name') or '')):
                cogs += amt
            else:
                other_exp += amt
        gross_profit = round(revenue - cogs, 2)

    re_code = resolve_retained_earnings_code()
    re_bal = 0.0
    try:
        led = get_account_ledger(re_code, date_from=None, date_to=date_to) or {}
        re_bal = _f(led.get('closing_balance'))
    except Exception:
        re_bal = 0.0

    # Closing journal preview (year-end style; shown for preview always)
    journal_lines: List[Dict[str, Any]] = []
    if abs(revenue) > BALANCE_TOL:
        journal_lines.append({
            'account': 'Revenue Accounts',
            'debit': round(abs(revenue), 2) if revenue >= 0 else 0.0,
            'credit': round(abs(revenue), 2) if revenue < 0 else 0.0,
        })
    if abs(expenses) > BALANCE_TOL:
        journal_lines.append({
            'account': 'Expense Accounts',
            'debit': round(abs(expenses), 2) if expenses < 0 else 0.0,
            'credit': round(abs(expenses), 2) if expenses >= 0 else 0.0,
        })
    if abs(net_profit) > BALANCE_TOL:
        journal_lines.append({
            'account': f'Retained Earnings ({re_code})',
            'debit': round(abs(net_profit), 2) if net_profit < 0 else 0.0,
            'credit': round(abs(net_profit), 2) if net_profit >= 0 else 0.0,
        })

    return {
        'date_from': date_from,
        'date_to': date_to,
        'revenue': round(revenue, 2),
        'expenses': round(expenses, 2),
        'cogs': round(cogs, 2),
        'other_expenses': round(other_exp, 2),
        'gross_profit': gross_profit,
        'net_profit': round(net_profit, 2),
        'retained_earnings_code': re_code,
        'retained_earnings_balance': round(re_bal, 2),
        'revenue_accounts': pl.get('revenue_accounts') or [],
        'expense_accounts': pl.get('expense_accounts') or [],
        'journal_preview': journal_lines,
        'narration': f'Period closing entry for {date_from} to {date_to} (P&L → Retained Earnings)',
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _check_trial_balance(date_from: str, date_to: str) -> Dict[str, Any]:
    rows = get_trial_balance_report(date_from=date_from, date_to=date_to) or []
    tdr = round(sum(_f(r.get('debit')) for r in rows), 2)
    tcr = round(sum(_f(r.get('credit')) for r in rows), 2)
    ok = abs(tdr - tcr) <= BALANCE_TOL
    return {
        'key': 'trial_balance',
        'label': 'Trial Balance is balanced',
        'ok': ok,
        'detail': f'Total debit {tdr:,.2f} vs credit {tcr:,.2f}' + ('' if ok else f' (diff {abs(tdr - tcr):,.2f})'),
    }


def list_temp_bill_drafts(limit: int = 200) -> List[Dict[str, Any]]:
    """List draft sales invoices in TEMPBILLHDR (hold bills)."""
    tbl = _detect_table(['TEMPBILLHDR', 'tempbillhdr'])
    if not tbl:
        return []
    loc_c = _detect_column(tbl, ['LOCATIONCODE', 'locationcode'])
    no_c = _detect_column(tbl, ['BILLNO', 'billno'])
    if not (loc_c and no_c):
        return []
    dt_c = _detect_column(tbl, ['BILLDATE', 'billdate'])
    amt_c = _detect_column(tbl, ['NETBILLAMOUNT', 'netbillamount', 'BILLAMOUNT', 'billamount'])
    cust_c = _detect_column(tbl, ['CUSTOMERCODE', 'customercode'])
    user_c = _detect_column(tbl, ['CREATEDBY', 'createdby', 'USERNAME', 'username'])
    cols = [
        f'{loc_c} AS locationcode',
        f'{no_c} AS billno',
        f'{dt_c} AS billdate' if dt_c else "CAST(NULL AS DATE) AS billdate",
        f'NVL({amt_c}, 0) AS amount' if amt_c else '0 AS amount',
        f'{cust_c} AS customercode' if cust_c else "CAST(NULL AS NUMBER) AS customercode",
        f'{user_c} AS created_by' if user_c else "CAST(NULL AS VARCHAR2(100)) AS created_by",
    ]
    rows = _safe_rows(
        f"""
        SELECT * FROM (
            SELECT {', '.join(cols)}
            FROM {tbl}
            ORDER BY {no_c} DESC
        ) WHERE ROWNUM <= :lim
        """,
        {'lim': int(limit)},
    ) or []
    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append({
            'locationcode': _si(r.get('locationcode')),
            'billno': _si(r.get('billno')),
            'billdate': _iso(r.get('billdate')),
            'amount': _f(r.get('amount')),
            'customercode': r.get('customercode'),
            'created_by': str(r.get('created_by') or '').strip(),
        })
    return out


def delete_temp_bill_drafts(
    items: Optional[List[Dict[str, Any]]] = None,
    *,
    delete_all: bool = False,
) -> Dict[str, Any]:
    """
    Delete draft sales from TEMPBILLHDR / TEMPBILLDTL.

    ``items`` = list of {locationcode, billno}. If ``delete_all``, clears every temp bill.
    """
    hdr = _detect_table(['TEMPBILLHDR', 'tempbillhdr'])
    dtl = _detect_table(['TEMPBILLDTL', 'tempbilldtl'])
    if not hdr:
        return {'success': False, 'error': 'TEMPBILLHDR not found', 'deleted': 0}
    loc_c = _detect_column(hdr, ['LOCATIONCODE', 'locationcode'])
    no_c = _detect_column(hdr, ['BILLNO', 'billno'])
    if not (loc_c and no_c):
        return {'success': False, 'error': 'TEMPBILLHDR missing LOCATIONCODE/BILLNO', 'deleted': 0}

    targets: List[Tuple[int, int]] = []
    if delete_all:
        for r in list_temp_bill_drafts(limit=5000):
            targets.append((_si(r.get('locationcode')), _si(r.get('billno'))))
    else:
        for it in items or []:
            loc = _si(it.get('locationcode') if isinstance(it, dict) else 0)
            bno = _si(it.get('billno') if isinstance(it, dict) else 0)
            if loc > 0 and bno > 0:
                targets.append((loc, bno))
    # de-dupe
    seen = set()
    uniq: List[Tuple[int, int]] = []
    for t in targets:
        if t in seen or t[1] <= 0:
            continue
        seen.add(t)
        uniq.append(t)
    if not uniq:
        return {'success': False, 'error': 'No draft bills selected.', 'deleted': 0}

    dtl_loc = _detect_column(dtl, ['LOCATIONCODE', 'locationcode']) if dtl else None
    dtl_no = _detect_column(dtl, ['BILLNO', 'billno']) if dtl else None
    deleted = 0
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                for loc, bno in uniq:
                    if dtl and dtl_loc and dtl_no:
                        cur.execute(
                            f'DELETE FROM {dtl} WHERE {dtl_loc} = :loc AND {dtl_no} = :bno',
                            {'loc': loc, 'bno': bno},
                        )
                    cur.execute(
                        f'DELETE FROM {hdr} WHERE {loc_c} = :loc AND {no_c} = :bno',
                        {'loc': loc, 'bno': bno},
                    )
                    deleted += max(cur.rowcount or 0, 0)
            conn.commit()
    except Exception as ex:
        logger.exception('delete_temp_bill_drafts: %s', ex)
        return {'success': False, 'error': str(ex), 'deleted': deleted}
    return {'success': True, 'deleted': deleted, 'requested': len(uniq)}


def _check_draft_sales() -> Dict[str, Any]:
    """TEMPBILLHDR rows count as draft sales invoices."""
    tbl = _detect_table(['TEMPBILLHDR', 'tempbillhdr'])
    if not tbl:
        return {
            'key': 'draft_sales',
            'label': 'No draft sales invoices',
            'ok': True,
            'detail': 'Temp sales table not present',
            'count': 0,
            'items': [],
            'can_delete': False,
        }
    rows = _safe_rows(f'SELECT COUNT(*) AS c FROM {tbl}', {}) or []
    n = _si((rows[0] or {}).get('c'))
    items = list_temp_bill_drafts(limit=50) if n > 0 else []
    return {
        'key': 'draft_sales',
        'label': 'No draft sales invoices',
        'ok': n == 0,
        'detail': 'No draft sales in TEMPBILLHDR' if n == 0 else f'{n} draft sales invoice(s) in TEMPBILLHDR',
        'count': n,
        'items': items,
        'can_delete': n > 0,
    }


def _check_draft_purchase() -> Dict[str, Any]:
    """Unposted GRN (INVENTORY_POSTED = N) as draft purchase receipts."""
    tbl = _detect_table(['RECEIPTHDR', 'receipthdr'])
    if not tbl:
        return {'key': 'draft_purchase', 'label': 'No draft purchase invoices', 'ok': True, 'detail': 'Receipt header not present'}
    inv_c = _detect_column(tbl, ['INVENTORY_POSTED', 'inventory_posted'])
    if not inv_c:
        return {'key': 'draft_purchase', 'label': 'No draft purchase invoices', 'ok': True, 'detail': 'INVENTORY_POSTED column not present'}
    rows = _safe_rows(
        f"SELECT COUNT(*) AS c FROM {tbl} WHERE NVL(UPPER(TRIM({inv_c})), 'N') = 'N'",
        {},
    ) or []
    n = _si((rows[0] or {}).get('c'))
    return {
        'key': 'draft_purchase',
        'label': 'No draft purchase invoices',
        'ok': n == 0,
        'detail': 'No unposted GRN receipts' if n == 0 else f'{n} unposted GRN / draft purchase receipt(s)',
    }


def _check_unposted_journals() -> Dict[str, Any]:
    tbl = _detect_table(['JOURNAL_ENTRY_DRAFT', 'journal_entry_draft'])
    if not tbl:
        return {'key': 'unposted_journals', 'label': 'No unposted journal entries', 'ok': True, 'detail': 'Draft journal table not present'}
    st = _detect_column(tbl, ['STATUS', 'status'])
    if st:
        rows = _safe_rows(
            f"SELECT COUNT(*) AS c FROM {tbl} WHERE UPPER(NVL({st}, 'DRAFT')) = 'DRAFT'",
            {},
        ) or []
    else:
        rows = _safe_rows(f'SELECT COUNT(*) AS c FROM {tbl}', {}) or []
    n = _si((rows[0] or {}).get('c'))
    return {
        'key': 'unposted_journals',
        'label': 'No unposted journal entries',
        'ok': n == 0,
        'detail': 'No journal drafts' if n == 0 else f'{n} draft / unposted journal entry(ies)',
    }


def list_zero_cost_stock_items(limit: int = 100) -> List[Dict[str, Any]]:
    """Stocked ITEMMASTER rows with zero AVERAGECOST / COSTPRICE."""
    im = _detect_table(['ITEMMASTER', 'itemmaster'])
    if not im:
        return []
    qty = _detect_column(im, ['CURRENTSTOCK', 'currentstock'])
    avg = _detect_column(im, ['AVERAGECOST', 'averagecost'])
    cost = _detect_column(im, ['COSTPRICE', 'costprice'])
    item_c = _detect_column(im, ['ITEMCODE', 'itemcode'])
    name_c = _detect_column(im, ['ITEMNAME', 'itemname'])
    loc_c = _detect_column(im, ['LOCATIONCODE', 'locationcode'])
    if not (qty and item_c):
        return []
    unit_avg = f'NVL({avg}, 0)' if avg else '0'
    unit_cost = f'NVL({cost}, 0)' if cost else '0'
    # Fail when both average and cost are zero (same rule as posting)
    cost_ok = f'({unit_avg} > 0 OR {unit_cost} > 0)'
    cols = [
        f'{item_c} AS itemcode',
        f'{name_c} AS itemname' if name_c else "CAST(NULL AS VARCHAR2(200)) AS itemname",
        f'{loc_c} AS locationcode' if loc_c else '0 AS locationcode',
        f'NVL({qty}, 0) AS qty',
        f'{unit_avg} AS averagecost',
        f'{unit_cost} AS costprice',
    ]
    rows = _safe_rows(
        f"""
        SELECT * FROM (
            SELECT {', '.join(cols)}
            FROM {im}
            WHERE NVL({qty}, 0) <> 0
              AND NOT {cost_ok}
            ORDER BY ABS(NVL({qty}, 0)) DESC, {item_c}
        ) WHERE ROWNUM <= :lim
        """,
        {'lim': int(limit)},
    ) or []
    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append({
            'itemcode': r.get('itemcode'),
            'itemname': str(r.get('itemname') or '').strip(),
            'locationcode': _si(r.get('locationcode')),
            'qty': _f(r.get('qty')),
            'averagecost': _f(r.get('averagecost')),
            'costprice': _f(r.get('costprice')),
        })
    return out


def list_negative_stock_items(
    limit: int = 100,
    location_code: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """ITEMMASTER rows with CURRENTSTOCK < 0 (optionally for one branch)."""
    im = _detect_table(['ITEMMASTER', 'itemmaster'])
    if not im:
        return []
    qty = _detect_column(im, ['CURRENTSTOCK', 'currentstock'])
    item_c = _detect_column(im, ['ITEMCODE', 'itemcode'])
    name_c = _detect_column(im, ['ITEMNAME', 'itemname'])
    loc_c = _detect_column(im, ['LOCATIONCODE', 'locationcode'])
    uom_c = _detect_column(im, ['BASEUOM', 'baseuom', 'UNITOFMEASUREMENT', 'uom'])
    avg = _detect_column(im, ['AVERAGECOST', 'averagecost'])
    cost = _detect_column(im, ['COSTPRICE', 'costprice'])
    if not (qty and item_c):
        return []
    cols = [
        f'{item_c} AS itemcode',
        f'{name_c} AS itemname' if name_c else "CAST(NULL AS VARCHAR2(200)) AS itemname",
        f'{loc_c} AS locationcode' if loc_c else '0 AS locationcode',
        f'{uom_c} AS baseuom' if uom_c else "'NOS' AS baseuom",
        f'NVL({qty}, 0) AS qty',
        f'NVL({avg}, 0) AS averagecost' if avg else '0 AS averagecost',
        f'NVL({cost}, 0) AS costprice' if cost else '0 AS costprice',
    ]
    where = [f'NVL({qty}, 0) < 0']
    params: Dict[str, Any] = {'lim': int(limit)}
    if location_code is not None and loc_c:
        where.append(f'{loc_c} = :loc')
        params['loc'] = int(location_code)
    rows = _safe_rows(
        f"""
        SELECT * FROM (
            SELECT {', '.join(cols)}
            FROM {im}
            WHERE {' AND '.join(where)}
            ORDER BY NVL({qty}, 0) ASC, {item_c}
        ) WHERE ROWNUM <= :lim
        """,
        params,
    ) or []
    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append({
            'itemcode': r.get('itemcode'),
            'itemname': str(r.get('itemname') or '').strip(),
            'locationcode': _si(r.get('locationcode')),
            'baseuom': str(r.get('baseuom') or 'NOS').strip() or 'NOS',
            'qty': _f(r.get('qty')),
            'averagecost': _f(r.get('averagecost')),
            'costprice': _f(r.get('costprice')),
        })
    return out


def _resolve_store_for_negative_item(location_code: int, item_code: int) -> str:
    """Best warehouse/store label for a negative-stock item (most negative / lowest qty)."""
    rows: List[Dict[str, Any]] = []
    try:
        rows = list(get_item_store_inventory(location_code, item_code) or [])
    except Exception:
        rows = []
    if not rows:
        try:
            rows = list(get_item_store_rows_from_itemmaster(item_code, location_code) or [])
        except Exception:
            rows = []
    if not rows:
        return ''
    best = min(rows, key=lambda x: float(x.get('stock') or 0))
    return str(best.get('store') or best.get('itemlocation') or best.get('code') or '').strip()


def build_negative_stock_adjustment_prefill(
    location_code: int,
    *,
    limit: int = 500,
    adj_date: Optional[str] = None,
) -> Dict[str, Any]:
    """New stock-adjustment payload: lines that bring each negative item back to zero."""
    loc = int(location_code or 1)
    items = list_negative_stock_items(limit=limit, location_code=loc)
    today = (adj_date or datetime.now().strftime('%Y-%m-%d'))[:10]
    lines: List[Dict[str, Any]] = []
    for it in items:
        try:
            ic = int(it.get('itemcode') or 0)
        except (TypeError, ValueError):
            continue
        if ic <= 0:
            continue
        cur = round(_f(it.get('qty')), 3)
        if cur >= 0:
            continue
        adj = round(-cur, 3)  # positive receipt to clear negative
        cost = _f(it.get('averagecost')) or _f(it.get('costprice'))
        store = _resolve_store_for_negative_item(loc, ic)
        lines.append({
            'item_code': ic,
            'item_name': str(it.get('itemname') or ''),
            'uom': str(it.get('baseuom') or 'NOS'),
            'store': store,
            'current_qty': cur,
            'adjust_qty': adj,
            'new_qty': 0.0,
            'base_qty': adj,
            'cost': round(cost, 4),
        })
    return {
        'header': {
            'adj_date': today,
            'remarks': f'Period closing — clear {len(lines)} negative stock item(s) to zero',
        },
        'lines': lines,
        'from_negative_stock': True,
        'count': len(lines),
    }


def _check_inventory_valuation() -> Dict[str, Any]:
    """ITEMMASTER stocked items must have AVERAGECOST or COSTPRICE > 0."""
    im = _detect_table(['ITEMMASTER', 'itemmaster'])
    if not im:
        return {
            'key': 'inventory_valuation',
            'label': 'Inventory valuation completed',
            'ok': True,
            'detail': 'ITEMMASTER not present',
            'count': 0,
            'items': [],
            'hint': '',
        }
    qty = _detect_column(im, ['CURRENTSTOCK', 'currentstock'])
    avg = _detect_column(im, ['AVERAGECOST', 'averagecost'])
    cost = _detect_column(im, ['COSTPRICE', 'costprice'])
    if not qty:
        return {
            'key': 'inventory_valuation',
            'label': 'Inventory valuation completed',
            'ok': True,
            'detail': 'Stock column not present',
            'count': 0,
            'items': [],
            'hint': '',
        }
    unit_avg = f'NVL({avg}, 0)' if avg else '0'
    unit_cost = f'NVL({cost}, 0)' if cost else '0'
    if unit_avg == '0' and unit_cost == '0':
        return {
            'key': 'inventory_valuation',
            'label': 'Inventory valuation completed',
            'ok': True,
            'detail': 'Cost columns not present',
            'count': 0,
            'items': [],
            'hint': '',
        }
    rows = _safe_rows(
        f"""
        SELECT COUNT(*) AS c FROM {im}
        WHERE NVL({qty}, 0) <> 0
          AND NOT ({unit_avg} > 0 OR {unit_cost} > 0)
        """,
        {},
    ) or []
    n = _si((rows[0] or {}).get('c'))
    items = list_zero_cost_stock_items(limit=80) if n > 0 else []
    hint = (
        'How to clear: open Item Master for each item and set Cost Price / Average Cost '
        '(or post a GRN so average cost is calculated). '
        'If the item is a service and should not hold stock, set Current Stock to 0.'
        if n > 0 else ''
    )
    return {
        'key': 'inventory_valuation',
        'label': 'Inventory valuation completed',
        'ok': n == 0,
        'detail': 'Stock items have cost prices' if n == 0 else f'{n} stocked item(s) with zero cost / average cost',
        'count': n,
        'items': items,
        'hint': hint,
    }


def _check_negative_stock(location_code: int = 1) -> Dict[str, Any]:
    im = _detect_table(['ITEMMASTER', 'itemmaster'])
    if not im:
        return {
            'key': 'negative_stock',
            'label': 'Stock negative validation',
            'ok': True,
            'detail': 'ITEMMASTER not present',
            'count': 0,
            'items': [],
            'hint': '',
        }
    qty = _detect_column(im, ['CURRENTSTOCK', 'currentstock'])
    loc_c = _detect_column(im, ['LOCATIONCODE', 'locationcode'])
    if not qty:
        return {
            'key': 'negative_stock',
            'label': 'Stock negative validation',
            'ok': True,
            'detail': 'Stock column not present',
            'count': 0,
            'items': [],
            'hint': '',
        }
    where = [f'NVL({qty}, 0) < 0']
    params: Dict[str, Any] = {}
    if loc_c:
        where.append(f'{loc_c} = :loc')
        params['loc'] = int(location_code or 1)
    rows = _safe_rows(
        f'SELECT COUNT(*) AS c FROM {im} WHERE {" AND ".join(where)}',
        params,
    ) or []
    n = _si((rows[0] or {}).get('c'))
    items = list_negative_stock_items(limit=80, location_code=int(location_code or 1)) if n > 0 else []
    hint = (
        'How to clear: use Adjust negative stock to open Stock Adjustment with these items '
        'pre-filled (qty set to zero), or post a GRN / inventory receipt. '
        'Also check oversold items (sales without prior receipts).'
        if n > 0 else ''
    )
    return {
        'key': 'negative_stock',
        'label': 'Stock negative validation',
        'ok': n == 0,
        'detail': 'No negative stock items' if n == 0 else f'{n} item(s) with negative stock',
        'count': n,
        'items': items,
        'hint': hint,
    }


def validate_period_for_closing(
    financial_year: str,
    month: int,
    location_code: int = 1,
) -> Dict[str, Any]:
    """Run all pre-close checks. ``ok`` is True only if every check passes."""
    ensure_periods_for_year(financial_year, location_code)
    period = get_period(financial_year, month, location_code)
    checks: List[Dict[str, Any]] = []
    if not period:
        return {'ok': False, 'checks': [{'key': 'period', 'label': 'Period exists', 'ok': False, 'detail': 'Period not found'}], 'period': None}

    already = {
        'key': 'not_closed',
        'label': 'Period not already closed',
        'ok': str(period.get('status') or '').upper() != STATUS_CLOSED,
        'detail': 'Period is open' if str(period.get('status') or '').upper() != STATUS_CLOSED else 'Period is already closed',
    }
    checks.append(already)
    df, dt = period['start_date'], period['end_date']
    checks.append(_check_trial_balance(df, dt))
    checks.append(_check_draft_sales())
    checks.append(_check_draft_purchase())
    checks.append(_check_unposted_journals())
    checks.append(_check_inventory_valuation())
    checks.append(_check_negative_stock(location_code))
    ok = all(bool(c.get('ok')) for c in checks)
    return {'ok': ok, 'checks': checks, 'period': period}


# ---------------------------------------------------------------------------
# Close / reopen
# ---------------------------------------------------------------------------

def _build_period_closing_lines(
    date_from: str,
    date_to: str,
    *,
    closing_type: str = CLOSE_YEAR_END,
) -> Tuple[List[Dict[str, Any]], float, str]:
    """Build GL lines to zero P&L into Retained Earnings. Returns (lines, net_profit, re_code)."""
    pl = get_profit_and_loss_report(date_from=date_from, date_to=date_to) or {}
    re_code = resolve_retained_earnings_code()
    tag = 'Year-end' if (closing_type or '').upper() == CLOSE_YEAR_END else 'Monthly'
    lines: List[Dict[str, Any]] = []
    for r in pl.get('revenue_accounts') or []:
        amt = _f(r.get('amount'))
        code = str(r.get('code') or '').strip()
        if not code or abs(amt) <= BALANCE_TOL:
            continue
        # Revenue credit balance → debit to close
        if amt >= 0:
            lines.append({'account_code': code, 'debit': round(amt, 2), 'credit': 0.0, 'remarks': f'{tag} close revenue'})
        else:
            lines.append({'account_code': code, 'debit': 0.0, 'credit': round(abs(amt), 2), 'remarks': f'{tag} close revenue'})
    for r in pl.get('expense_accounts') or []:
        amt = _f(r.get('amount'))
        code = str(r.get('code') or '').strip()
        if not code or abs(amt) <= BALANCE_TOL:
            continue
        # Expense debit balance → credit to close
        if amt >= 0:
            lines.append({'account_code': code, 'debit': 0.0, 'credit': round(amt, 2), 'remarks': f'{tag} close expense'})
        else:
            lines.append({'account_code': code, 'debit': round(abs(amt), 2), 'credit': 0.0, 'remarks': f'{tag} close expense'})
    net = _f(pl.get('net_profit'))
    if abs(net) > BALANCE_TOL:
        if net >= 0:
            lines.append({'account_code': re_code, 'debit': 0.0, 'credit': round(net, 2), 'remarks': 'Transfer net profit to retained earnings'})
        else:
            lines.append({'account_code': re_code, 'debit': round(abs(net), 2), 'credit': 0.0, 'remarks': 'Transfer net loss to retained earnings'})
    return (lines, net, re_code)


def _build_year_end_closing_lines(date_from: str, date_to: str) -> Tuple[List[Dict[str, Any]], float, str]:
    """Backward-compatible alias for period P&L close lines (year-end tag)."""
    return _build_period_closing_lines(date_from, date_to, closing_type=CLOSE_YEAR_END)


def _create_next_fiscal_year(financial_year: str, period_end: str, username: str) -> Optional[str]:
    """Create next FY master row if fiscal_year module is available."""
    try:
        from datetime import timedelta

        from addons.fiscal_year.fiscal_year_db import (
            ensure_fiscal_year_table,
            list_fiscal_years,
            save_fiscal_year,
        )
        ensure_fiscal_year_table()
        end = datetime.strptime(period_end[:10], '%Y-%m-%d').date()
        # Prefer next day after current FY's DATE_TO when we can resolve it
        ns = end + timedelta(days=1)
        for row in list_fiscal_years(include_closed=True) or []:
            code0 = str(row.get('year_code') or row.get('YEAR_CODE') or '').strip()
            if code0 == financial_year:
                dt = _iso(row.get('date_to') or row.get('DATE_TO'))
                if dt:
                    ns = datetime.strptime(dt[:10], '%Y-%m-%d').date() + timedelta(days=1)
                break
        ne = date(ns.year + 1, ns.month, ns.day) - timedelta(days=1)
        code = f'{ns.year}-{ne.year}' if ns.year != ne.year else str(ns.year)
        name = f'FY {code}'
        for row in list_fiscal_years(include_closed=True) or []:
            c = str(row.get('year_code') or row.get('YEAR_CODE') or '').strip()
            if c.upper() == code.upper():
                return c
        ok, err, _fid = save_fiscal_year(
            {
                'year_code': code,
                'year_name': name,
                'date_from': ns.strftime('%Y-%m-%d'),
                'date_to': ne.strftime('%Y-%m-%d'),
                'is_current': 'N',
                'is_closed': 'N',
            },
            username,
        )
        if not ok:
            logger.warning('create next fiscal year: %s', err)
            return None
        return code
    except Exception as ex:
        logger.warning('create next fiscal year skipped: %s', ex)
        return None


def close_period(
    financial_year: str,
    month: int,
    closing_type: str,
    username: str,
    location_code: int = 1,
    *,
    skip_validation: bool = False,
) -> Dict[str, Any]:
    """
    Close a period.

    Monthly and Year-end both post a P&L → Retained Earnings closing journal for the
    selected month, then lock the period.

    Year-end additionally locks any remaining open months in the FY and creates the next FY.
    """
    ensure_periods_for_year(financial_year, location_code)
    ctype = (closing_type or CLOSE_MONTHLY).strip().upper()
    if ctype not in (CLOSE_MONTHLY, CLOSE_YEAR_END):
        ctype = CLOSE_MONTHLY

    validation = validate_period_for_closing(financial_year, month, location_code)
    if not skip_validation and not validation.get('ok'):
        return {'success': False, 'error': 'Validation failed', 'validation': validation}

    period = validation.get('period') or get_period(financial_year, month, location_code)
    if not period:
        return {'success': False, 'error': 'Period not found'}
    if str(period.get('status') or '').upper() == STATUS_CLOSED:
        return {'success': False, 'error': 'Period is already closed', 'validation': validation}

    preview = build_closing_preview(period['start_date'], period['end_date'])
    closing_no = next_closing_number(financial_year)
    voucher_no = ''
    next_fy = None
    closing_lines, _net, _re = _build_period_closing_lines(
        period['start_date'],
        period['end_date'],
        closing_type=ctype,
    )
    # Year-end requires a transferable P&L; monthly may lock with no activity (no journal).
    if ctype == CLOSE_YEAR_END and len(closing_lines) < 2:
        return {'success': False, 'error': 'No revenue/expense balances to close for year-end.'}

    # Single DB transaction: row lock → closing journal (no nested commit) → status + log → commit once
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT UPPER(NVL(STATUS, 'OPEN'))
                      FROM {ACCOUNTING_PERIOD_TABLE}
                     WHERE PERIOD_ID = :pid
                     FOR UPDATE
                    """,
                    {'pid': period['period_id']},
                )
                lock_row = cur.fetchone()
                if not lock_row:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    return {'success': False, 'error': 'Period not found', 'validation': validation}
                if str(lock_row[0] or '').upper() == STATUS_CLOSED:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    return {
                        'success': False,
                        'error': 'Period is already closed (or was closed by another session).',
                        'validation': validation,
                    }

            if len(closing_lines) >= 2:
                close_label = 'Year-end' if ctype == CLOSE_YEAR_END else 'Monthly'
                try:
                    voucher_no = create_gl_journal_entry(
                        voucher_date=period['end_date'],
                        reference_no=closing_no[:50],
                        narration=(
                            f'{close_label} closing {period["period_label"]} '
                            '— transfer P&L to Retained Earnings'
                        ),
                        lines=closing_lines,
                        created_by=username,
                        source='PERIOD_CLOSE',
                        conn=conn,
                        commit=False,
                    )
                except Exception as ex:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    return {'success': False, 'error': f'Closing journal failed: {ex}'}

            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    UPDATE {ACCOUNTING_PERIOD_TABLE}
                    SET STATUS = :st,
                        CLOSED_BY = :closed_by,
                        CLOSED_DATE = SYSDATE,
                        CLOSING_NUMBER = :cno,
                        CLOSING_TYPE = :ctype
                    WHERE PERIOD_ID = :pid
                    """,
                    {
                        'st': STATUS_CLOSED,
                        'closed_by': (username or '')[:100],
                        'cno': closing_no[:40],
                        'ctype': ctype[:20],
                        'pid': period['period_id'],
                    },
                )
                # Year-end: close all remaining open months in this FY
                if ctype == CLOSE_YEAR_END:
                    cur.execute(
                        f"""
                        UPDATE {ACCOUNTING_PERIOD_TABLE}
                        SET STATUS = :st,
                            CLOSED_BY = NVL(CLOSED_BY, :closed_by),
                            CLOSED_DATE = NVL(CLOSED_DATE, SYSDATE),
                            CLOSING_NUMBER = NVL(CLOSING_NUMBER, :cno),
                            CLOSING_TYPE = NVL(CLOSING_TYPE, :ctype)
                        WHERE FINANCIAL_YEAR = :fy
                          AND UPPER(NVL(STATUS, 'OPEN')) <> 'CLOSED'
                          AND (LOCATIONCODE IS NULL OR LOCATIONCODE = :loc)
                        """,
                        {
                            'st': STATUS_CLOSED,
                            'closed_by': (username or '')[:100],
                            'cno': closing_no[:40],
                            'ctype': ctype[:20],
                            'fy': financial_year,
                            'loc': location_code,
                        },
                    )
                cur.execute(
                    f"""
                    INSERT INTO {CLOSING_LOG_TABLE}
                        (LOG_ID, CLOSING_NUMBER, FINANCIAL_YEAR, PERIOD_LABEL, MONTH,
                         REVENUE, EXPENSES, PROFIT, GROSS_PROFIT, RETAINED_EARNINGS,
                         CLOSING_TYPE, CLOSED_BY, CLOSED_DATE, STATUS, VOUCHER_NO, LOCATIONCODE, CREATED_DATE)
                    VALUES
                        ({CLOSING_LOG_SEQ}.NEXTVAL, :cno, :fy, :plabel, :m,
                         :rev, :exp, :profit, :gp, :re,
                         :ctype, :closed_by, SYSDATE, :st, :vno, :loc, SYSDATE)
                    """,
                    {
                        'cno': closing_no[:40],
                        'fy': financial_year[:20],
                        'plabel': period['period_label'][:40],
                        'm': month,
                        'rev': preview['revenue'],
                        'exp': preview['expenses'],
                        'profit': preview['net_profit'],
                        'gp': preview['gross_profit'],
                        're': preview['retained_earnings_balance'],
                        'ctype': ctype[:20],
                        'closed_by': (username or '')[:100],
                        'st': STATUS_CLOSED,
                        'vno': (voucher_no or '')[:40],
                        'loc': location_code,
                    },
                )
            conn.commit()
    except Exception as ex:
        logger.exception('period close transaction failed')
        return {'success': False, 'error': f'Close transaction failed: {ex}'}

    if ctype == CLOSE_YEAR_END:
        next_fy = _create_next_fiscal_year(financial_year, period['end_date'], username)
        try:
            from addons.fiscal_year.fiscal_year_db import list_fiscal_years, save_fiscal_year
            for row in list_fiscal_years(include_closed=True) or []:
                code = str(row.get('year_code') or '').strip()
                if code == financial_year:
                    fid = int(row.get('fiscal_year_id') or 0)
                    save_fiscal_year(
                        {
                            'year_code': code,
                            'year_name': row.get('year_name'),
                            'date_from': _iso(row.get('date_from')),
                            'date_to': _iso(row.get('date_to')),
                            'is_current': row.get('is_current') or 'N',
                            'is_closed': 'Y',
                            'locationcode': row.get('locationcode'),
                        },
                        username,
                        fiscal_year_id=fid or None,
                    )
                    break
        except Exception as ex:
            logger.warning('mark FY closed: %s', ex)

    return {
        'success': True,
        'closing_number': closing_no,
        'voucher_no': voucher_no,
        'closing_type': ctype,
        'period': get_period(financial_year, month, location_code),
        'preview': preview,
        'next_financial_year': next_fy,
        'validation': validation,
    }


def _latest_closing_log_voucher(
    financial_year: str,
    month: int,
    location_code: int = 1,
) -> Dict[str, Any]:
    """Latest CLOSED closing-log row for period (voucher_no / log_id), if any."""
    ensure_period_closing_tables()
    if not _table_exists(CLOSING_LOG_TABLE):
        return {}
    rows = _safe_rows(
        f"""
        SELECT * FROM (
            SELECT LOG_ID, VOUCHER_NO, CLOSING_NUMBER, CLOSING_TYPE, CLOSED_DATE
              FROM {CLOSING_LOG_TABLE}
             WHERE FINANCIAL_YEAR = :fy AND MONTH = :m
               AND (LOCATIONCODE IS NULL OR LOCATIONCODE = :loc)
               AND UPPER(NVL(STATUS, 'CLOSED')) = 'CLOSED'
             ORDER BY CLOSED_DATE DESC NULLS LAST, LOG_ID DESC
        ) WHERE ROWNUM = 1
        """,
        {'fy': financial_year, 'm': int(month), 'loc': int(location_code)},
    ) or []
    if not rows:
        return {}
    r = rows[0]
    return {
        'log_id': r.get('log_id') or r.get('LOG_ID'),
        'voucher_no': str(r.get('voucher_no') or r.get('VOUCHER_NO') or '').strip(),
        'closing_number': str(r.get('closing_number') or r.get('CLOSING_NUMBER') or '').strip(),
        'closing_type': str(r.get('closing_type') or r.get('CLOSING_TYPE') or '').strip(),
    }


def reopen_period(
    financial_year: str,
    month: int,
    username: str,
    reason: str,
    location_code: int = 1,
    *,
    reverse_closing_journal: bool = False,
) -> Dict[str, Any]:
    """Admin-only reopen. Reason is mandatory.

    Single DB transaction: row lock → unlock period + closing log → optional reverse
    of the PERIOD_CLOSE voucher (same connection, one commit).
    """
    reason = (reason or '').strip()
    if not reason:
        return {'success': False, 'error': 'Reopen reason is mandatory.'}
    period = get_period(financial_year, month, location_code)
    if not period:
        ensure_periods_for_year(financial_year, location_code)
        period = get_period(financial_year, month, location_code)
    if not period:
        return {'success': False, 'error': 'Period not found'}
    if str(period.get('status') or '').upper() != STATUS_CLOSED:
        return {'success': False, 'error': 'Period is not closed.'}

    close_meta = _latest_closing_log_voucher(financial_year, month, location_code)
    close_vno = str(close_meta.get('voucher_no') or '').strip()
    reversal_no = ''
    reverse_note = ''

    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT UPPER(NVL(STATUS, 'OPEN'))
                      FROM {ACCOUNTING_PERIOD_TABLE}
                     WHERE PERIOD_ID = :pid
                     FOR UPDATE
                    """,
                    {'pid': period['period_id']},
                )
                lock_row = cur.fetchone()
                if not lock_row:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    return {'success': False, 'error': 'Period not found'}
                if str(lock_row[0] or '').upper() != STATUS_CLOSED:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    return {
                        'success': False,
                        'error': 'Period is not closed (or was reopened by another session).',
                    }

                cur.execute(
                    f"""
                    UPDATE {ACCOUNTING_PERIOD_TABLE}
                    SET STATUS = :st,
                        CLOSED_BY = NULL,
                        CLOSED_DATE = NULL,
                        CLOSING_NUMBER = NULL,
                        CLOSING_TYPE = NULL
                    WHERE PERIOD_ID = :pid
                    """,
                    {'st': STATUS_OPEN, 'pid': period['period_id']},
                )
                cur.execute(
                    f"""
                    UPDATE {CLOSING_LOG_TABLE}
                    SET STATUS = :st,
                        REOPEN_REASON = :reason,
                        REOPENED_BY = :reopened_by,
                        REOPENED_DATE = SYSDATE
                    WHERE LOG_ID = (
                        SELECT LOG_ID FROM (
                            SELECT LOG_ID FROM {CLOSING_LOG_TABLE}
                            WHERE FINANCIAL_YEAR = :fy AND MONTH = :m
                              AND (LOCATIONCODE IS NULL OR LOCATIONCODE = :loc)
                              AND UPPER(NVL(STATUS, 'CLOSED')) = 'CLOSED'
                            ORDER BY CLOSED_DATE DESC NULLS LAST, LOG_ID DESC
                        ) WHERE ROWNUM = 1
                    )
                    """,
                    {
                        'st': STATUS_REOPENED,
                        'reason': reason[:500],
                        'reopened_by': (username or '')[:100],
                        'fy': financial_year,
                        'm': month,
                        'loc': location_code,
                    },
                )

            if reverse_closing_journal:
                if not close_vno:
                    reverse_note = (
                        'No closing journal on file for this period '
                        '(lock-only close or missing voucher).'
                    )
                else:
                    existing_rev = ''
                    try:
                        existing_rev = get_gl_voucher_reversal_no(close_vno) or ''
                    except Exception:
                        existing_rev = ''
                    if existing_rev:
                        reversal_no = existing_rev
                        reverse_note = (
                            f'Closing journal {close_vno} was already reversed ({existing_rev}).'
                        )
                    else:
                        detail = get_gl_voucher_detail(close_vno) or {}
                        rev_date = str(detail.get('voucher_date') or period.get('end_date') or '')[:10]
                        try:
                            reversal_no = reverse_gl_journal_voucher(
                                close_vno,
                                voucher_date=rev_date or None,
                                remarks=f'Reopen {period.get("period_label") or ""}: {reason}'[:250],
                                created_by=username or '',
                                conn=conn,
                                commit=False,
                                skip_period_lock=True,
                            )
                            reverse_note = f'Closing journal {close_vno} reversed as {reversal_no}.'
                        except Exception as ex:
                            try:
                                conn.rollback()
                            except Exception:
                                pass
                            logger.exception(
                                'reopen: reverse closing journal failed for %s', close_vno
                            )
                            return {
                                'success': False,
                                'error': (
                                    f'Reopen aborted: closing journal {close_vno} '
                                    f'could not be reversed: {ex}'
                                ),
                            }

            conn.commit()
    except Exception as ex:
        logger.exception('period reopen transaction failed')
        return {'success': False, 'error': f'Reopen transaction failed: {ex}'}

    if reverse_closing_journal:
        msg = f'Period reopened. {reverse_note}'.strip()
    else:
        msg = (
            'Period reopened. Closing journal was left in place '
            '(not reversed). You can reverse it manually if needed.'
        )

    return {
        'success': True,
        'period': get_period(financial_year, month, location_code),
        'message': msg,
        'closing_voucher_no': close_vno,
        'reversal_voucher_no': reversal_no,
        'reverse_closing_journal': bool(reverse_closing_journal),
    }


def list_closing_history(
    financial_year: Optional[str] = None,
    location_code: int = 1,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    ensure_period_closing_tables()
    if not _table_exists(CLOSING_LOG_TABLE):
        return []
    where = ['(LOCATIONCODE IS NULL OR LOCATIONCODE = :loc)']
    params: Dict[str, Any] = {'loc': location_code, 'lim': int(limit)}
    if financial_year:
        where.append('FINANCIAL_YEAR = :fy')
        params['fy'] = financial_year.strip()
    rows = _safe_rows(
        f"""
        SELECT * FROM (
            SELECT LOG_ID, CLOSING_NUMBER, FINANCIAL_YEAR, PERIOD_LABEL, MONTH,
                   REVENUE, EXPENSES, PROFIT, GROSS_PROFIT, RETAINED_EARNINGS,
                   CLOSING_TYPE, CLOSED_BY, CLOSED_DATE, STATUS,
                   REOPEN_REASON, REOPENED_BY, REOPENED_DATE, VOUCHER_NO
            FROM {CLOSING_LOG_TABLE}
            WHERE {' AND '.join(where)}
            ORDER BY CLOSED_DATE DESC NULLS LAST, LOG_ID DESC
        ) WHERE ROWNUM <= :lim
        """,
        params,
    ) or []
    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append({
            'log_id': r.get('log_id'),
            'closing_number': r.get('closing_number') or '',
            'financial_year': r.get('financial_year') or '',
            'period': r.get('period_label') or '',
            'month': _si(r.get('month')),
            'revenue': _f(r.get('revenue')),
            'expenses': _f(r.get('expenses')),
            'profit': _f(r.get('profit')),
            'gross_profit': _f(r.get('gross_profit')),
            'retained_earnings': _f(r.get('retained_earnings')),
            'closing_type': r.get('closing_type') or '',
            'closed_by': r.get('closed_by') or '',
            'closed_date': _iso(r.get('closed_date')),
            'status': str(r.get('status') or '').upper(),
            'reopen_reason': r.get('reopen_reason') or '',
            'reopened_by': r.get('reopened_by') or '',
            'reopened_date': _iso(r.get('reopened_date')),
            'voucher_no': r.get('voucher_no') or '',
        })
    return out


def get_closing_log(log_id: int) -> Optional[Dict[str, Any]]:
    rows = list_closing_history(limit=500)
    for r in rows:
        if _si(r.get('log_id')) == _si(log_id):
            return r
    ensure_period_closing_tables()
    found = _safe_rows(
        f"""
        SELECT LOG_ID, CLOSING_NUMBER, FINANCIAL_YEAR, PERIOD_LABEL, MONTH,
               REVENUE, EXPENSES, PROFIT, GROSS_PROFIT, RETAINED_EARNINGS,
               CLOSING_TYPE, CLOSED_BY, CLOSED_DATE, STATUS,
               REOPEN_REASON, REOPENED_BY, REOPENED_DATE, VOUCHER_NO
        FROM {CLOSING_LOG_TABLE}
        WHERE LOG_ID = :id
        """,
        {'id': log_id},
    ) or []
    if not found:
        return None
    r = found[0]
    return {
        'log_id': r.get('log_id'),
        'closing_number': r.get('closing_number') or '',
        'financial_year': r.get('financial_year') or '',
        'period': r.get('period_label') or '',
        'month': _si(r.get('month')),
        'revenue': _f(r.get('revenue')),
        'expenses': _f(r.get('expenses')),
        'profit': _f(r.get('profit')),
        'gross_profit': _f(r.get('gross_profit')),
        'retained_earnings': _f(r.get('retained_earnings')),
        'closing_type': r.get('closing_type') or '',
        'closed_by': r.get('closed_by') or '',
        'closed_date': _iso(r.get('closed_date')),
        'status': str(r.get('status') or '').upper(),
        'reopen_reason': r.get('reopen_reason') or '',
        'reopened_by': r.get('reopened_by') or '',
        'reopened_date': _iso(r.get('reopened_date')),
        'voucher_no': r.get('voucher_no') or '',
    }


def header_cards(financial_year: str, month: int, location_code: int = 1) -> Dict[str, Any]:
    ensure_periods_for_year(financial_year, location_code)
    periods = list_periods(financial_year, location_code)
    current = get_period(financial_year, month, location_code)
    last_closed = None
    for p in sorted(periods, key=lambda x: x.get('end_date') or '', reverse=True):
        if str(p.get('status') or '').upper() == STATUS_CLOSED:
            last_closed = p
            break
    return {
        'financial_year': financial_year,
        'current_period': (current or {}).get('period_label') or period_label(datetime.now().year, month),
        'status': (current or {}).get('status') or STATUS_OPEN,
        'last_closed_by': (last_closed or {}).get('closed_by') or '—',
        'last_closed_date': (last_closed or {}).get('closed_date') or '—',
        'current': current,
        'periods': periods,
    }
