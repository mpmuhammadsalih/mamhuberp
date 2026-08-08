"""TBLTRANSACTIONDATE / TBLTRANSACTIONS helpers for setup screen.

Open window is a date range: DATEOFOPEN (from) … DATEOFTO (to), inclusive.
When DATEOFTO is null (legacy rows), the window is a single day (DATEOFOPEN).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from db import _TABLE_COLUMNS_CACHE, _get_connection, _get_table_columns, _safe_rows, _table_exists

TXN_DATE_MODULES: Tuple[Dict[str, Any], ...] = (
    {'key': 'sales', 'label': 'Sales', 'default_code': 1},
    {'key': 'sales_return', 'label': 'Sales Return', 'default_code': 3},
    {'key': 'purchase', 'label': 'Purchase', 'default_code': 2},
    {'key': 'purchase_return', 'label': 'Purchase Return', 'default_code': 4},
    {'key': 'grn', 'label': 'GRN', 'default_code': 5},
    {'key': 'transfer', 'label': 'Transfer', 'default_code': 6},
)

_DATEOFTO_ENSURED = False


def ensure_tbltransactiondate_dateofto_column() -> None:
    """Add DATEOFTO (range end) when missing; backfill from DATEOFOPEN."""
    global _DATEOFTO_ENSURED
    if _DATEOFTO_ENSURED:
        return
    if not _table_exists('TBLTRANSACTIONDATE'):
        return
    try:
        cols = {c.upper() for c in (_get_table_columns('TBLTRANSACTIONDATE') or [])}
        if 'DATEOFTO' not in cols:
            with _get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute('ALTER TABLE TBLTRANSACTIONDATE ADD (DATEOFTO DATE)')
                    try:
                        cur.execute(
                            'UPDATE TBLTRANSACTIONDATE SET DATEOFTO = DATEOFOPEN '
                            'WHERE DATEOFTO IS NULL AND DATEOFOPEN IS NOT NULL'
                        )
                    except Exception:
                        pass
                conn.commit()
            _TABLE_COLUMNS_CACHE.pop('TBLTRANSACTIONDATE', None)
        else:
            # Keep legacy null ends aligned with open day.
            try:
                with _get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            'UPDATE TBLTRANSACTIONDATE SET DATEOFTO = DATEOFOPEN '
                            'WHERE DATEOFTO IS NULL AND DATEOFOPEN IS NOT NULL'
                        )
                    conn.commit()
            except Exception:
                pass
        _DATEOFTO_ENSURED = True
    except Exception as exc:
        print(f'[ensure_tbltransactiondate_dateofto_column] {exc}')


def _module_by_key(key: str) -> Optional[Dict[str, Any]]:
    k = str(key or '').strip().lower()
    for m in TXN_DATE_MODULES:
        if m['key'] == k:
            return m
    return None


def _parse_ymd(raw: Any) -> Optional[date]:
    if raw is None:
        return None
    if isinstance(raw, date) and not isinstance(raw, datetime):
        return raw
    if isinstance(raw, datetime):
        return raw.date()
    s = str(raw).strip()[:10]
    if not s:
        return None
    try:
        return datetime.strptime(s, '%Y-%m-%d').date()
    except ValueError:
        return None


def _row_date_iso(raw: Any) -> Optional[str]:
    d = _parse_ymd(raw)
    return d.isoformat() if d else None


def _preferred_in_range(date_from: date, date_to: date) -> date:
    """Default document date inside an open window."""
    today = date.today()
    if date_from <= today <= date_to:
        return today
    if today < date_from:
        return date_from
    return date_to


def _has_dateofto() -> bool:
    ensure_tbltransactiondate_dateofto_column()
    try:
        cols = {c.upper() for c in (_get_table_columns('TBLTRANSACTIONDATE') or [])}
        return 'DATEOFTO' in cols
    except Exception:
        return False


def list_transaction_type_names(location_code: int) -> Dict[int, str]:
    """Map transaction code -> name from TBLTRANSACTIONS for this branch."""
    out: Dict[int, str] = {}
    if not _table_exists('TBLTRANSACTIONS'):
        return out
    rows = _safe_rows(
        """
        SELECT TRANSACTIONCODE AS tc, TRANSACTIONNAME AS tn
        FROM TBLTRANSACTIONS
        WHERE LOCATIONCODE = :lc
        ORDER BY TRANSACTIONCODE
        """,
        {'lc': int(location_code)},
    ) or []
    for r in rows:
        try:
            tc = int(r.get('tc') if r.get('tc') is not None else r.get('TRANSACTIONCODE'))
        except (TypeError, ValueError):
            continue
        nm = str(r.get('tn') or r.get('TRANSACTIONNAME') or '').strip()
        if nm:
            out[tc] = nm
    return out


def list_open_transaction_dates(location_code: int) -> List[Dict[str, Any]]:
    """All TBLTRANSACTIONDATE rows for a branch (open and closed)."""
    if not _table_exists('TBLTRANSACTIONDATE'):
        return []
    ensure_tbltransactiondate_dateofto_column()
    has_to = _has_dateofto()
    to_sel = 'DATEOFTO' if has_to else 'DATEOFOPEN AS DATEOFTO'
    rows = _safe_rows(
        f"""
        SELECT LOCATIONCODE, TRANSACTIONCODE, DATEOFOPEN, {to_sel}, OPENFLAG,
               OPENEDBY, OPENEDDATE, CLOSEDBY, CLOSEDDATE
        FROM TBLTRANSACTIONDATE
        WHERE LOCATIONCODE = :lc
        ORDER BY TRANSACTIONCODE
        """,
        {'lc': int(location_code)},
    ) or []
    out: List[Dict[str, Any]] = []
    for r in rows:
        rl = {str(k).lower(): v for k, v in r.items()}
        tc_raw = rl.get('transactioncode')
        try:
            tc = int(tc_raw)
        except (TypeError, ValueError):
            continue
        d_from = _row_date_iso(rl.get('dateofopen'))
        d_to = _row_date_iso(rl.get('dateofto')) or d_from
        out.append(
            {
                'transaction_code': tc,
                'date_of_open': d_from,
                'date_of_to': d_to,
                'date_from': d_from,
                'date_to': d_to,
                'open_flag': str(rl.get('openflag') or '').strip().upper(),
                'opened_by': str(rl.get('openedby') or '').strip(),
                'opened_date': rl.get('openeddate'),
                'closed_by': str(rl.get('closedby') or '').strip() or None,
                'closed_date': rl.get('closeddate'),
            }
        )
    return out


def get_transaction_date_row(
    location_code: int,
    transaction_code: int,
) -> Optional[Dict[str, Any]]:
    """Single TBLTRANSACTIONDATE row for branch + transaction code."""
    if not _table_exists('TBLTRANSACTIONDATE'):
        return None
    ensure_tbltransactiondate_dateofto_column()
    has_to = _has_dateofto()
    to_sel = 'DATEOFTO' if has_to else 'DATEOFOPEN AS DATEOFTO'
    rows = _safe_rows(
        f"""
        SELECT LOCATIONCODE, TRANSACTIONCODE, DATEOFOPEN, {to_sel}, OPENFLAG,
               OPENEDBY, OPENEDDATE, CLOSEDBY, CLOSEDDATE
        FROM TBLTRANSACTIONDATE
        WHERE LOCATIONCODE = :lc
          AND TRANSACTIONCODE = :tc
        """,
        {'lc': int(location_code), 'tc': int(transaction_code)},
    )
    if not rows:
        return None
    rl = {str(k).lower(): v for k, v in rows[0].items()}
    tc_raw = rl.get('transactioncode')
    try:
        tc = int(tc_raw)
    except (TypeError, ValueError):
        return None
    d_from = _row_date_iso(rl.get('dateofopen'))
    d_to = _row_date_iso(rl.get('dateofto')) or d_from
    flag = str(rl.get('openflag') or '').strip().upper()
    return {
        'transaction_code': tc,
        'date_of_open': d_from,
        'date_of_to': d_to,
        'date_from': d_from,
        'date_to': d_to,
        'open_flag': flag,
        'opened_by': str(rl.get('openedby') or '').strip(),
        'closed_by': str(rl.get('closedby') or '').strip() or None,
        'closed_date': _row_date_iso(rl.get('closeddate')),
    }


def get_min_allowed_transaction_date(
    location_code: int,
    transaction_code: int,
) -> date:
    """
    Earliest allowed DATEOFOPEN (range start) for setup.

    - Closed row: day after last closed range end (not before today).
    - Open row: cannot roll back before current open range start.
    - No row: today onward.
    """
    today = date.today()
    row = get_transaction_date_row(location_code, transaction_code)
    if not row:
        return today
    flag = str(row.get('open_flag') or '').strip().upper()
    open_from = _parse_ymd(row.get('date_from') or row.get('date_of_open'))
    open_to = _parse_ymd(row.get('date_to') or row.get('date_of_to')) or open_from
    if flag == 'C' and open_to is not None:
        return max(today, open_to + timedelta(days=1))
    if flag == 'O' and open_from is not None:
        return open_from
    return today


def _closed_accounting_period_overlap_error(
    location_code: int,
    date_from: date,
    date_to: date,
    *,
    module_label: str = '',
) -> str:
    """If [date_from, date_to] overlaps a CLOSED accounting period, return an error message."""
    prefix = f'{module_label}: ' if module_label else ''
    try:
        from addons.accounts.period_closing_db import list_closed_periods
    except Exception:
        return ''
    try:
        closed = list_closed_periods(int(location_code)) or []
    except Exception:
        return ''
    for p in closed:
        if not isinstance(p, dict):
            continue
        p_from = _parse_ymd(p.get('start_date'))
        p_to = _parse_ymd(p.get('end_date')) or p_from
        if p_from is None or p_to is None:
            continue
        if date_from <= p_to and date_to >= p_from:
            label = str(p.get('period_label') or '').strip() or (
                f"{p_from.isoformat()} → {p_to.isoformat()}"
            )
            return (
                f'{prefix}Cannot open {date_from.isoformat()} → {date_to.isoformat()}: '
                f'accounting period {label} is closed via Period Closing. '
                f'Reopen that period from Period Closing first.'
            )
    return ''


def validate_transaction_date_range_allowed(
    location_code: int,
    transaction_code: int,
    date_from: date,
    date_to: date,
    *,
    module_label: str = '',
    skip_restrictions: bool = False,
) -> Tuple[bool, str]:
    """Validate inclusive open window for setup save.

    Periods closed via Period Closing cannot be opened here (even for admin /
    ``skip_restrictions``). Unlock those months from Period Closing only.
    """
    prefix = f'{module_label}: ' if module_label else ''
    if not isinstance(date_from, date) or not isinstance(date_to, date):
        return (False, f'{prefix}Invalid date range.')
    if date_to < date_from:
        return (False, f'{prefix}To date must be on or after From date.')
    period_err = _closed_accounting_period_overlap_error(
        location_code, date_from, date_to, module_label=module_label,
    )
    if period_err:
        return (False, period_err)
    if skip_restrictions:
        return (True, '')
    min_dt = get_min_allowed_transaction_date(location_code, transaction_code)
    if date_from >= min_dt:
        return (True, '')
    row = get_transaction_date_row(location_code, transaction_code)
    if row and str(row.get('open_flag') or '').strip().upper() == 'C':
        closed_from = row.get('date_from') or row.get('date_of_open') or '—'
        closed_to = row.get('date_to') or row.get('date_of_to') or closed_from
        closed = closed_from if closed_from == closed_to else f'{closed_from} → {closed_to}'
        return (
            False,
            f'{prefix}Cannot use from {date_from.isoformat()}: range {closed} is closed. '
            f'Choose from {min_dt.isoformat()} or later.',
        )
    if row and str(row.get('open_flag') or '').strip().upper() == 'O':
        cur_from = row.get('date_from') or row.get('date_of_open') or '—'
        return (
            False,
            f'{prefix}Cannot roll back before the current open from-date ({cur_from}). '
            f'Choose from {min_dt.isoformat()} or later.',
        )
    return (
        False,
        f'{prefix}Cannot select a past from-date. Choose {min_dt.isoformat()} or later.',
    )


def validate_transaction_date_allowed(
    location_code: int,
    transaction_code: int,
    date_of_open: date,
    *,
    module_label: str = '',
    skip_restrictions: bool = False,
) -> Tuple[bool, str]:
    """Backward-compatible single-day validation (from = to = date_of_open)."""
    return validate_transaction_date_range_allowed(
        location_code,
        transaction_code,
        date_of_open,
        date_of_open,
        module_label=module_label,
        skip_restrictions=skip_restrictions,
    )


def upsert_open_transaction_date(
    location_code: int,
    transaction_code: int,
    date_of_open: date,
    opened_by: str,
    *,
    date_of_to: Optional[date] = None,
    module_label: str = '',
    skip_restrictions: bool = False,
) -> Tuple[bool, str]:
    """Open (or re-open) a transaction date range with OPENFLAG O."""
    if not _table_exists('TBLTRANSACTIONDATE'):
        return (False, 'TBLTRANSACTIONDATE table is not available.')
    ensure_tbltransactiondate_dateofto_column()
    ob = (opened_by or 'SYSTEM').strip()[:20] or 'SYSTEM'
    try:
        lc = int(location_code)
        tc = int(transaction_code)
    except (TypeError, ValueError):
        return (False, 'Invalid location or transaction code.')
    if not isinstance(date_of_open, date):
        return (False, 'Invalid from date.')
    end_dt = date_of_to if isinstance(date_of_to, date) else date_of_open
    ok, err = validate_transaction_date_range_allowed(
        lc, tc, date_of_open, end_dt, module_label=module_label, skip_restrictions=skip_restrictions,
    )
    if not ok:
        return (False, err)
    has_to = _has_dateofto()
    if has_to:
        merge_sql = """
            MERGE INTO TBLTRANSACTIONDATE t
            USING (SELECT :lc AS lc, :tc AS tc FROM dual) s
            ON (t.LOCATIONCODE = s.lc AND t.TRANSACTIONCODE = s.tc)
            WHEN MATCHED THEN UPDATE SET
                DATEOFOPEN = TRUNC(:dt_from),
                DATEOFTO = TRUNC(:dt_to),
                OPENFLAG = 'O',
                OPENEDBY = :ob,
                OPENEDDATE = TRUNC(SYSDATE),
                CLOSEDBY = NULL,
                CLOSEDDATE = NULL
            WHEN NOT MATCHED THEN INSERT (
                LOCATIONCODE, TRANSACTIONCODE, DATEOFOPEN, DATEOFTO, OPENFLAG,
                OPENEDBY, OPENEDDATE, CLOSEDBY, CLOSEDDATE
            ) VALUES (
                :lc, :tc, TRUNC(:dt_from), TRUNC(:dt_to), 'O',
                :ob, TRUNC(SYSDATE), NULL, NULL
            )
        """
        params = {'lc': lc, 'tc': tc, 'dt_from': date_of_open, 'dt_to': end_dt, 'ob': ob}
    else:
        merge_sql = """
            MERGE INTO TBLTRANSACTIONDATE t
            USING (SELECT :lc AS lc, :tc AS tc FROM dual) s
            ON (t.LOCATIONCODE = s.lc AND t.TRANSACTIONCODE = s.tc)
            WHEN MATCHED THEN UPDATE SET
                DATEOFOPEN = TRUNC(:dt),
                OPENFLAG = 'O',
                OPENEDBY = :ob,
                OPENEDDATE = TRUNC(SYSDATE),
                CLOSEDBY = NULL,
                CLOSEDDATE = NULL
            WHEN NOT MATCHED THEN INSERT (
                LOCATIONCODE, TRANSACTIONCODE, DATEOFOPEN, OPENFLAG,
                OPENEDBY, OPENEDDATE, CLOSEDBY, CLOSEDDATE
            ) VALUES (
                :lc, :tc, TRUNC(:dt), 'O',
                :ob, TRUNC(SYSDATE), NULL, NULL
            )
        """
        params = {'lc': lc, 'tc': tc, 'dt': date_of_open, 'ob': ob}
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(merge_sql, params)
            conn.commit()
        return (True, '')
    except Exception as exc:
        return (False, str(exc))


def close_transaction_date(
    location_code: int,
    transaction_code: int,
    closed_by: str,
    *,
    module_label: str = '',
) -> Tuple[bool, str]:
    """Mark an open TBLTRANSACTIONDATE row as closed (OPENFLAG C)."""
    if not _table_exists('TBLTRANSACTIONDATE'):
        return (False, 'TBLTRANSACTIONDATE table is not available.')
    cb = (closed_by or 'SYSTEM').strip()[:20] or 'SYSTEM'
    try:
        lc = int(location_code)
        tc = int(transaction_code)
    except (TypeError, ValueError):
        return (False, 'Invalid location or transaction code.')
    row = get_transaction_date_row(lc, tc)
    prefix = f'{module_label}: ' if module_label else ''
    if not row:
        return (False, f'{prefix}No transaction date row to close.')
    flag = str(row.get('open_flag') or '').strip().upper()
    if flag == 'C':
        d_from = row.get('date_from') or row.get('date_of_open') or '—'
        d_to = row.get('date_to') or row.get('date_of_to') or d_from
        label = d_from if d_from == d_to else f'{d_from} → {d_to}'
        return (False, f'{prefix}Business range {label} is already closed.')
    if flag != 'O':
        return (False, f'{prefix}Cannot close: status is not open.')
    update_sql = """
        UPDATE TBLTRANSACTIONDATE
        SET OPENFLAG = 'C',
            CLOSEDBY = :cb,
            CLOSEDDATE = TRUNC(SYSDATE)
        WHERE LOCATIONCODE = :lc
          AND TRANSACTIONCODE = :tc
          AND TRIM(OPENFLAG) = 'O'
    """
    params = {'lc': lc, 'tc': tc, 'cb': cb}
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(update_sql, params)
                updated = int(getattr(cur, 'rowcount', 0) or 0)
            conn.commit()
        if updated <= 0:
            return (False, f'{prefix}No open date was closed (row may have changed).')
        return (True, '')
    except Exception as exc:
        return (False, str(exc))


def close_transaction_date_setup(
    location_code: int,
    *,
    mode: str,
    module_keys: Optional[List[str]] = None,
    closed_by: str,
) -> Tuple[bool, str, List[str]]:
    """
    Close open business dates for configured modules.

    mode: 'all' | 'separate' (both close selected/all configured open rows)
    module_keys: optional subset of module keys; when omitted, all TXN_DATE_MODULES.
    """
    lc = int(location_code)
    keys_filter: Optional[set] = None
    if module_keys:
        keys_filter = {str(k).strip().lower() for k in module_keys if str(k).strip()}
    targets: List[Dict[str, Any]] = []
    for mod in TXN_DATE_MODULES:
        if keys_filter is not None and mod['key'] not in keys_filter:
            continue
        targets.append(mod)
    if not targets:
        return (False, 'No modules selected to close.', [])

    closed = 0
    errors: List[str] = []
    closed_labels: List[str] = []
    for mod in targets:
        tc = int(mod['default_code'])
        ok, err = close_transaction_date(
            lc, tc, closed_by, module_label=str(mod['label']),
        )
        if ok:
            closed += 1
            row = get_transaction_date_row(lc, tc)
            d_from = (row or {}).get('date_from') or (row or {}).get('date_of_open') or ''
            d_to = (row or {}).get('date_to') or (row or {}).get('date_of_to') or d_from
            label = str(mod['label'])
            if d_from and d_to and d_from != d_to:
                closed_labels.append(f'{label} ({d_from} → {d_to})')
            elif d_from:
                closed_labels.append(f'{label} ({d_from})')
            else:
                closed_labels.append(label)
        elif err:
            errors.append(err)
    if closed <= 0:
        return (False, errors[0] if errors else 'No open dates to close.', errors)
    msg = f'Closed {closed} transaction date(s).'
    if closed_labels and len(closed_labels) <= 4:
        msg += ' ' + ', '.join(closed_labels) + '.'
    if errors:
        msg += f' ({len(errors)} skipped.)'
    return (True, msg, errors)


def build_setup_payload(location_code: int, *, allow_any_date: bool = False) -> Dict[str, Any]:
    """Bootstrap data for the setup UI."""
    ensure_tbltransactiondate_dateofto_column()
    lc = int(location_code)
    type_names = list_transaction_type_names(lc)
    open_rows = list_open_transaction_dates(lc)
    by_code = {int(r['transaction_code']): r for r in open_rows}
    modules: List[Dict[str, Any]] = []
    open_froms: List[str] = []
    open_tos: List[str] = []
    min_dates: List[date] = []
    for mod in TXN_DATE_MODULES:
        tc = int(mod['default_code'])
        row = by_code.get(tc) or {}
        d_from = row.get('date_from') or row.get('date_of_open')
        d_to = row.get('date_to') or row.get('date_of_to') or d_from
        flag = str(row.get('open_flag') or '').strip().upper()
        min_dt = get_min_allowed_transaction_date(lc, tc)
        min_dates.append(min_dt)
        if d_from:
            open_froms.append(str(d_from))
        if d_to:
            open_tos.append(str(d_to))
        modules.append(
            {
                'key': mod['key'],
                'label': mod['label'],
                'transaction_code': tc,
                'transaction_name': type_names.get(tc) or mod['label'],
                'date_of_open': d_from,
                'date_of_to': d_to,
                'date_from': d_from,
                'date_to': d_to,
                'open_flag': flag,
                'opened_by': row.get('opened_by') or '',
                'min_date': '' if allow_any_date else min_dt.isoformat(),
                'is_closed': flag == 'C',
            }
        )
    mode = 'all'
    uniq_from = sorted({d for d in open_froms if d})
    uniq_to = sorted({d for d in open_tos if d})
    if len(uniq_from) > 1 or len(uniq_to) > 1:
        mode = 'separate'
    global_min = max(min_dates) if min_dates else date.today()
    if uniq_from:
        parsed = [_parse_ymd(d) for d in uniq_from]
        parsed = [d for d in parsed if d is not None]
        all_from = max(parsed).isoformat() if parsed else global_min.isoformat()
    else:
        all_from = global_min.isoformat()
    if uniq_to:
        parsed_to = [_parse_ymd(d) for d in uniq_to]
        parsed_to = [d for d in parsed_to if d is not None]
        all_to = max(parsed_to).isoformat() if parsed_to else all_from
    else:
        all_to = all_from
    if not allow_any_date and _parse_ymd(all_from) and _parse_ymd(all_from) < global_min:
        all_from = global_min.isoformat()
    if _parse_ymd(all_to) and _parse_ymd(all_from) and _parse_ymd(all_to) < _parse_ymd(all_from):
        all_to = all_from
    closed_periods: List[Dict[str, Any]] = []
    try:
        from addons.accounts.period_closing_db import list_closed_periods
        for p in list_closed_periods(lc) or []:
            if not isinstance(p, dict):
                continue
            sd = str(p.get('start_date') or '').strip()[:10]
            ed = str(p.get('end_date') or '').strip()[:10]
            if not sd:
                continue
            closed_periods.append({
                'period_label': str(p.get('period_label') or '').strip(),
                'start_date': sd,
                'end_date': ed or sd,
            })
    except Exception:
        closed_periods = []
    return {
        'location_code': lc,
        'mode': mode,
        'all_date': all_from,  # backward compatible alias (= from)
        'all_date_from': all_from,
        'all_date_to': all_to,
        'allow_any_date': allow_any_date,
        'min_date': '' if allow_any_date else global_min.isoformat(),
        'today': date.today().isoformat(),
        'modules': modules,
        'closed_periods': closed_periods,
        'transaction_types': [
            {'code': tc, 'name': nm} for tc, nm in sorted(type_names.items(), key=lambda x: x[0])
        ],
        'rows': open_rows,
    }


def _normalize_module_range(
    raw: Any,
    *,
    fallback_from: Optional[str] = None,
    fallback_to: Optional[str] = None,
) -> Tuple[Optional[date], Optional[date]]:
    """Accept string date, or dict with from/to keys."""
    if isinstance(raw, dict):
        d_from = _parse_ymd(raw.get('from') or raw.get('date_from') or raw.get('date_of_open') or fallback_from)
        d_to = _parse_ymd(raw.get('to') or raw.get('date_to') or raw.get('date_of_to') or fallback_to or d_from)
        return d_from, d_to
    d_from = _parse_ymd(raw if raw not in (None, '') else fallback_from)
    d_to = _parse_ymd(fallback_to) if fallback_to else d_from
    return d_from, d_to


def save_transaction_date_setup(
    location_code: int,
    *,
    mode: str,
    all_date: Optional[str] = None,
    all_date_from: Optional[str] = None,
    all_date_to: Optional[str] = None,
    module_dates: Optional[Dict[str, Any]] = None,
    module_date_from: Optional[Dict[str, str]] = None,
    module_date_to: Optional[Dict[str, str]] = None,
    module_codes: Optional[Dict[str, int]] = None,
    opened_by: str,
    skip_restrictions: bool = False,
) -> Tuple[bool, str, List[str]]:
    """
    Persist date ranges for configured modules.

    mode: 'all' | 'separate'
    """
    ensure_tbltransactiondate_dateofto_column()
    lc = int(location_code)
    mode_u = str(mode or '').strip().lower()
    errors: List[str] = []
    saved = 0
    module_codes = module_codes or {}
    module_dates = module_dates or {}
    module_date_from = module_date_from or {}
    module_date_to = module_date_to or {}

    if mode_u == 'all':
        d_from = _parse_ymd(all_date_from or all_date)
        d_to = _parse_ymd(all_date_to or all_date_from or all_date) or d_from
        if d_from is None or d_to is None:
            return (False, 'Enter a valid From / To date for all transactions.', errors)
        if not skip_restrictions:
            for mod in TXN_DATE_MODULES:
                tc = int(module_codes.get(mod['key']) or mod['default_code'])
                ok, err = validate_transaction_date_range_allowed(
                    lc, tc, d_from, d_to, module_label=str(mod['label']),
                )
                if not ok:
                    return (False, err, errors)
        for mod in TXN_DATE_MODULES:
            tc = int(module_codes.get(mod['key']) or mod['default_code'])
            ok, err = upsert_open_transaction_date(
                lc, tc, d_from, opened_by,
                date_of_to=d_to,
                module_label=str(mod['label']),
                skip_restrictions=skip_restrictions,
            )
            if ok:
                saved += 1
            elif err:
                errors.append(f"{mod['label']}: {err}")
        if saved <= 0:
            return (False, errors[0] if errors else 'Save failed.', errors)
        label = d_from.isoformat() if d_from == d_to else f'{d_from.isoformat()} → {d_to.isoformat()}'
        return (True, f'Updated {saved} transaction date range(s) ({label}).', errors)

    for mod in TXN_DATE_MODULES:
        key = mod['key']
        raw = module_dates.get(key)
        fb_from = module_date_from.get(key)
        fb_to = module_date_to.get(key)
        d_from, d_to = _normalize_module_range(raw, fallback_from=fb_from, fallback_to=fb_to)
        if d_from is None or d_to is None:
            errors.append(f"{mod['label']}: invalid or missing From / To date.")
            continue
        tc = int(module_codes.get(key) or mod['default_code'])
        if not skip_restrictions:
            ok, err = validate_transaction_date_range_allowed(
                lc, tc, d_from, d_to, module_label=str(mod['label']),
            )
            if not ok:
                errors.append(err)
                continue
        ok, err = upsert_open_transaction_date(
            lc, tc, d_from, opened_by,
            date_of_to=d_to,
            module_label=str(mod['label']),
            skip_restrictions=skip_restrictions,
        )
        if ok:
            saved += 1
        elif err:
            errors.append(f"{mod['label']}: {err}")
    if saved <= 0:
        return (False, errors[0] if errors else 'No dates saved.', errors)
    msg = f'Updated {saved} transaction date range(s).'
    if errors:
        msg += f' ({len(errors)} skipped.)'
    return (True, msg, errors)


def get_open_transaction_date_range(
    location_code: int,
    transaction_code: int,
) -> Optional[Dict[str, str]]:
    """
    Return open window for a branch + transaction code.

    Keys: date_from, date_to, preferred (YYYY-MM-DD). None when no open row.
    """
    if not _table_exists('TBLTRANSACTIONDATE'):
        return None
    ensure_tbltransactiondate_dateofto_column()
    has_to = _has_dateofto()
    to_sel = 'DATEOFTO AS dt_to' if has_to else 'DATEOFOPEN AS dt_to'
    rows = _safe_rows(
        f"""
        SELECT DATEOFOPEN AS dt_from, {to_sel}
        FROM TBLTRANSACTIONDATE
        WHERE LOCATIONCODE = :lc
          AND TRANSACTIONCODE = :tc
          AND TRIM(OPENFLAG) = 'O'
        """,
        {'lc': int(location_code), 'tc': int(transaction_code)},
    )
    if not rows:
        return None
    d_from = _parse_ymd(rows[0].get('dt_from'))
    d_to = _parse_ymd(rows[0].get('dt_to')) or d_from
    if d_from is None:
        return None
    if d_to < d_from:
        d_to = d_from
    preferred = _preferred_in_range(d_from, d_to)
    return {
        'date_from': d_from.isoformat(),
        'date_to': d_to.isoformat(),
        'preferred': preferred.isoformat(),
    }


def get_open_transaction_date(
    location_code: int,
    transaction_code: int,
) -> Optional[str]:
    """Return preferred YYYY-MM-DD inside the open range (backward compatible)."""
    rng = get_open_transaction_date_range(location_code, transaction_code)
    if not rng:
        return None
    return rng.get('preferred') or rng.get('date_from')


def is_date_in_open_transaction_range(
    location_code: int,
    transaction_code: int,
    doc_date: Any,
) -> Tuple[bool, str, Optional[Dict[str, str]]]:
    """
    True when doc_date falls inside the open inclusive range.

    Returns (ok, error_message, range_dict).
    """
    rng = get_open_transaction_date_range(location_code, transaction_code)
    if not rng:
        return (False, 'No open transaction date range.', None)
    d = _parse_ymd(doc_date)
    if d is None:
        return (True, '', rng)  # caller may default to preferred
    a = rng['date_from']
    b = rng['date_to']
    iso = d.isoformat()
    if a <= iso <= b:
        return (True, '', rng)
    if a == b:
        return (False, f'Date must be {a}.', rng)
    return (False, f'Date must be between {a} and {b}.', rng)
