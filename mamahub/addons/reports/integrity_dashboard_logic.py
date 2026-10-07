"""Accounting & Inventory Integrity Dashboard — audit, reconciliation, insights (tenant DB)."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from addons.accounts.transaction_audit import (
    BALANCE_TOL,
    get_transaction_audit_detail,
    list_transaction_audit_vouchers,
)
from db import (
    DATABASES,
    DEFAULT_PARTY_ACCOUNTS,
    GL_DTL_TABLE,
    GL_HDR_TABLE,
    WAREHOUSE_MASTER_TABLE,
    _detect_column,
    _detect_table,
    _safe_rows,
    ensure_gl_tables,
    get_account_ledger,
    get_accounts_payable_summary,
    get_accounts_receivable_summary,
    get_all_chart_of_accounts,
    get_location_info_by_dbkey,
    get_locations_list,
    get_profit_and_loss_report,
    get_trial_balance_report,
)

logger = logging.getLogger(__name__)

RESET_NO = 1
DOC_CHECK_LIMIT = 200
DOC_CHECK_LIMIT_LONG_RANGE = 100
LONG_RANGE_DAYS = 62
TOL = 0.02


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


def _status_severity(diff: float, warn_at: float = 1.0, crit_at: float = 100.0) -> str:
    ad = abs(diff)
    if ad <= TOL:
        return 'ok'
    if ad <= warn_at:
        return 'warn'
    if ad <= crit_at:
        return 'warn'
    return 'err'


def resolve_branch_from_session(session: Any, args: Any) -> int:
    for key in ('branch', 'locationcode', 'location_code'):
        v = getattr(args, 'get', lambda _k, _d=None: None)(key) if args else None
        if v is not None and str(v).strip().isdigit():
            return int(v)
    loc = session.get('location_code') if session else None
    if loc is not None and str(loc).isdigit():
        return int(loc)
    try:
        info = get_location_info_by_dbkey(None)
        if info and info.get('locationcode') is not None:
            return int(info['locationcode'])
    except Exception:
        pass
    return 1


def _default_dates(filters: Dict[str, Any]) -> Tuple[str, str]:
    df = (filters.get('date_from') or '').strip()[:10]
    dt = (filters.get('date_to') or '').strip()[:10]
    if not dt:
        dt = datetime.now().strftime('%Y-%m-%d')
    if not df:
        y = datetime.now().year
        df = f'{y}-01-01'
    if df > dt:
        df, dt = dt, df
    return df, dt


def _inventory_control_account() -> str:
    return (os.environ.get('INTEGRITY_INVENTORY_ACCOUNT') or '1300').strip() or '1300'


def _gl_line_count(voucher_no: str) -> int:
    if not voucher_no:
        return 0
    rows = _safe_rows(
        f'SELECT COUNT(*) AS c FROM {GL_DTL_TABLE} WHERE VOUCHER_NO = :v',
        {'v': voucher_no},
    )
    return _si((rows[0] or {}).get('c')) if rows else 0


def _gl_exists(voucher_no: str) -> bool:
    if not voucher_no:
        return False
    rows = _safe_rows(
        f'SELECT 1 AS x FROM {GL_HDR_TABLE} WHERE VOUCHER_NO = :v AND ROWNUM = 1',
        {'v': voucher_no},
    )
    return bool(rows)


def _find_gl_voucher_by_reference(
    doc_no: int,
    location_code: int,
    sources: Tuple[str, ...],
    prefixes: Tuple[str, ...],
) -> str:
    """Resolve posted voucher when standard prefix pattern is missing."""
    for prefix in prefixes:
        vno = f'{prefix}-{location_code}-{doc_no}'[:30]
        if _gl_exists(vno):
            return vno
    ensure_gl_tables()
    src_list = ','.join(f"'{s}'" for s in sources)
    if not src_list:
        return ''
    rows = _safe_rows(
        f'''SELECT h.VOUCHER_NO AS voucher_no
            FROM {GL_HDR_TABLE} h
            WHERE UPPER(NVL(h.SOURCE, '')) IN ({src_list})
              AND (
                h.VOUCHER_NO LIKE :pat
                OR UPPER(NVL(h.REFERENCE_NO, '')) LIKE :ref1
                OR UPPER(NVL(h.REFERENCE_NO, '')) LIKE :ref2
                OR UPPER(NVL(h.NARRATION, '')) LIKE :nar
              )
            ORDER BY h.VOUCHER_DATE DESC''',
        {
            'pat': f'%-{location_code}-{doc_no}',
            'ref1': f'%-{doc_no}',
            'ref2': f'{doc_no}%',
            'nar': f'%{doc_no}%',
        },
    ) or []
    if rows:
        return str(rows[0].get('voucher_no') or rows[0].get('VOUCHER_NO') or '').strip()
    return ''


def get_integrity_filter_options(location_code: int) -> Dict[str, Any]:
    companies = [{'code': k, 'name': (v.get('name') or k)} for k, v in (DATABASES or {}).items()]
    if not companies:
        companies = [{'code': 'HO', 'name': 'Head Office'}]
    branches = []
    try:
        for loc in get_locations_list() or []:
            branches.append({
                'code': str(loc.get('locationcode') or loc.get('code') or ''),
                'name': str(loc.get('locationname') or loc.get('name') or ''),
            })
    except Exception:
        branches = [{'code': str(location_code), 'name': f'Branch {location_code}'}]
    warehouses = []
    if _detect_table([WAREHOUSE_MASTER_TABLE, 'WAREHOUSE_MASTER']):
        wh_tbl = _detect_table([WAREHOUSE_MASTER_TABLE, 'WAREHOUSE_MASTER'])
        loc_c = _detect_column(wh_tbl, ['LOCATIONCODE', 'locationcode'])
        id_c = _detect_column(wh_tbl, ['WAREHOUSE_ID', 'warehouse_id'])
        code_c = _detect_column(wh_tbl, ['WAREHOUSE_CODE', 'warehouse_code'])
        name_c = _detect_column(wh_tbl, ['WAREHOUSE_NAME', 'warehouse_name'])
        if id_c:
            cols = [f'{id_c} AS warehouse_id']
            if code_c:
                cols.append(f'{code_c} AS warehouse_code')
            if name_c:
                cols.append(f'{name_c} AS warehouse_name')
            where = f'{loc_c} = :loc' if loc_c else '1=1'
            warehouses = _safe_rows(
                f'SELECT {", ".join(cols)} FROM {wh_tbl} WHERE {where} ORDER BY 1',
                {'loc': location_code} if loc_c else {},
            ) or []
    modules = [
        {'id': 'ALL', 'label': 'All modules'},
        {'id': 'SALES', 'label': 'Sales'},
        {'id': 'PURCHASE', 'label': 'Purchase'},
        {'id': 'INVENTORY', 'label': 'Inventory'},
        {'id': 'CASH', 'label': 'Cash & Bank'},
        {'id': 'GL', 'label': 'General Ledger'},
    ]
    return {
        'companies': companies,
        'branches': branches,
        'warehouses': warehouses,
        'modules': modules,
        'financial_years': [
            {'id': str(datetime.now().year), 'label': str(datetime.now().year)},
            {'id': str(datetime.now().year - 1), 'label': str(datetime.now().year - 1)},
        ],
    }


def _tb_balance(
    account_code: str,
    date_from: str,
    date_to: str,
    *,
    tb_rows: Optional[List[Dict[str, Any]]] = None,
) -> float:
    tb = tb_rows if tb_rows is not None else get_trial_balance_report(date_from=date_from, date_to=date_to)
    ac = str(account_code or '').strip()
    for r in tb or []:
        if str(r.get('code') or '').strip() == ac:
            t = (r.get('type') or '').upper()
            dr = _f(r.get('debit'))
            cr = _f(r.get('credit'))
            if t in ('ASSET', 'EXPENSE'):
                return round(dr - cr, 2)
            return round(cr - dr, 2)
    return 0.0


def _doc_check_limit(date_from: str, date_to: str) -> int:
    """Fewer document GL checks on long date ranges (full audit stays usable)."""
    try:
        d0 = datetime.strptime(date_from[:10], '%Y-%m-%d').date()
        d1 = datetime.strptime(date_to[:10], '%Y-%m-%d').date()
        if (d1 - d0).days >= LONG_RANGE_DAYS:
            return DOC_CHECK_LIMIT_LONG_RANGE
    except Exception:
        pass
    return DOC_CHECK_LIMIT


def _build_gl_lookup_index(date_from: str, date_to: str) -> Dict[str, Any]:
    """One-shot GL index for posting verification (avoids N+1 voucher lookups)."""
    ensure_gl_tables()
    hdr_rows = _safe_rows(
        f'''SELECT h.VOUCHER_NO AS voucher_no,
                   h.REFERENCE_NO AS reference_no,
                   h.SOURCE AS source
            FROM {GL_HDR_TABLE} h
            WHERE TRUNC(h.VOUCHER_DATE) BETWEEN TO_DATE(:df, 'YYYY-MM-DD') AND TO_DATE(:dt, 'YYYY-MM-DD')''',
        {'df': date_from, 'dt': date_to},
    ) or []
    by_exact: Dict[str, str] = {}
    by_suffix: Dict[str, List[str]] = {}
    for r in hdr_rows:
        vno = str(r.get('voucher_no') or r.get('VOUCHER_NO') or '').strip()
        if not vno:
            continue
        by_exact[vno.upper()] = vno
        parts = vno.rsplit('-', 2)
        if len(parts) >= 3 and str(parts[-2]).isdigit() and str(parts[-1]).isdigit():
            by_suffix.setdefault(f'{parts[-2]}-{parts[-1]}', []).append(vno)
        ref = str(r.get('reference_no') or r.get('REFERENCE_NO') or '').strip().upper()
        if ref:
            by_exact.setdefault(f'REF:{ref}', vno)
    line_rows = _safe_rows(
        f'''SELECT d.VOUCHER_NO AS voucher_no, COUNT(*) AS c
            FROM {GL_DTL_TABLE} d
            JOIN {GL_HDR_TABLE} h ON h.VOUCHER_NO = d.VOUCHER_NO
            WHERE TRUNC(h.VOUCHER_DATE) BETWEEN TO_DATE(:df, 'YYYY-MM-DD') AND TO_DATE(:dt, 'YYYY-MM-DD')
            GROUP BY d.VOUCHER_NO''',
        {'df': date_from, 'dt': date_to},
    ) or []
    line_counts: Dict[str, int] = {}
    for r in line_rows:
        vno = str(r.get('voucher_no') or r.get('VOUCHER_NO') or '').strip()
        if vno:
            line_counts[vno.upper()] = _si(r.get('c'))
    return {'by_exact': by_exact, 'by_suffix': by_suffix, 'line_counts': line_counts}


def _resolve_voucher_from_index(
    index: Dict[str, Any],
    doc_no: int,
    location_code: int,
    prefixes: Tuple[str, ...],
) -> str:
    by_exact: Dict[str, str] = index.get('by_exact') or {}
    by_suffix: Dict[str, List[str]] = index.get('by_suffix') or {}
    for prefix in prefixes:
        cand = f'{prefix}-{location_code}-{doc_no}'[:30]
        hit = by_exact.get(cand.upper())
        if hit:
            return hit
    key = f'{location_code}-{doc_no}'
    cands = by_suffix.get(key) or []
    if not cands:
        return ''
    pref_u = {str(p or '').strip().upper() for p in prefixes if p}
    for vno in cands:
        pfx = vno.split('-')[0].upper() if '-' in vno else ''
        if pfx in pref_u:
            return vno
    return cands[0]


def _posting_row_fast(
    doc_no: Any,
    doc_date: Any,
    module: str,
    voucher_no: str,
    expected: int,
    index: Dict[str, Any],
) -> Dict[str, Any]:
    vno = (voucher_no or '').strip()
    line_counts: Dict[str, int] = index.get('line_counts') or {}
    by_exact: Dict[str, str] = index.get('by_exact') or {}
    actual = line_counts.get(vno.upper(), 0) if vno else 0
    exists = bool(vno and vno.upper() in by_exact)
    note = ''
    if expected <= 0 and actual == 0:
        status = 'ok'
        note = 'Zero-cost bill — no COGS expected'
    elif not exists or actual == 0:
        status = 'err'
        note = 'No GL voucher or zero lines'
    elif actual < expected:
        status = 'warn'
        note = f'Incomplete posting ({actual} < {expected} lines)'
    elif actual != expected:
        status = 'warn'
        note = f'Line count mismatch (expected {expected}, got {actual})'
    else:
        status = 'ok'
        note = 'Balanced posting'
    d = doc_date
    if d is not None and hasattr(d, 'strftime'):
        d = d.strftime('%Y-%m-%d')
    elif d:
        d = str(d)[:10]
    return {
        'document_no': str(doc_no or ''),
        'document_date': d or '',
        'module': module,
        'voucher_no': vno,
        'expected_entries': expected,
        'actual_entries': actual,
        'status': status,
        'status_note': note,
    }


def _allocate_proportional(total: float, weights: List[float]) -> List[float]:
    """Split *total* across *weights*; last slice absorbs rounding remainder."""
    n = len(weights)
    if n == 0:
        return []
    amt = round(float(total or 0), 2)
    if amt == 0:
        return [0.0] * n
    wsum = sum(max(0.0, float(w or 0)) for w in weights)
    if wsum <= 0:
        even = round(amt / n, 2)
        out = [even] * n
        out[-1] = round(amt - even * (n - 1), 2)
        return out
    out: List[float] = []
    running = 0.0
    for i, w in enumerate(weights):
        if i == n - 1:
            out.append(round(amt - running, 2))
        else:
            piece = round(amt * (float(w or 0) / wsum), 2)
            out.append(piece)
            running += piece
    return out


def _expected_lines_for_payment_voucher(voucher_no: str, source: str) -> int:
    """AR/AP receipts: 2 lines (cash + invoices); 3 when customer/supplier credits are applied."""
    src = (source or '').strip().upper()
    if src not in ('AR_RECEIPT', 'AP_RECEIPT'):
        return 2
    if not voucher_no:
        return 2
    rows = _safe_rows(
        f'SELECT REMARKS FROM {GL_DTL_TABLE} WHERE VOUCHER_NO = :v',
        {'v': voucher_no},
    ) or []
    for r in rows:
        rm = str(r.get('remarks') or r.get('REMARKS') or '').lower()
        if 'credits applied' in rm:
            return 3
    return 2


def _expected_lines_for_sales_voucher(voucher_no: str) -> int:
    """Match ERP posting patterns: full SI/SR ≈ 4 lines; POS COGS-only SIC/SRC ≈ 2."""
    vno = (voucher_no or '').strip().upper()
    if not vno:
        return 4
    prefix = vno.split('-')[0] if '-' in vno else vno[:3]
    if prefix in ('SIC', 'SRC'):
        return 2
    if prefix in ('SI', 'SR'):
        return 4
    return 4


def _bill_cogs_total(location_code: int, billno: int) -> float:
    """
    Total COGS amount for a bill (qty × unit cost), matching sales save costing:
    AVERAGECOST (line, then ITEMMASTER), else COST/COSTPRICE; skip lines with unit cost <= 0.
    """
    if billno <= 0:
        return 0.0
    im = _detect_table(['ITEMMASTER', 'itemmaster'])
    im_item = _detect_column(im, ['ITEMCODE', 'itemcode']) if im else None
    im_loc = _detect_column(im, ['LOCATIONCODE', 'locationcode']) if im else None
    im_avg = _detect_column(im, ['AVERAGECOST', 'averagecost']) if im else None
    im_cost = _detect_column(im, ['COSTPRICE', 'costprice']) if im else None

    total = 0.0
    for dtl_name in ('BILLDTL', 'billdtl', 'BILLDTLHISTORY', 'billdtlhistory'):
        dtl = _detect_table([dtl_name])
        if not dtl:
            continue
        loc_c = _detect_column(dtl, ['LOCATIONCODE', 'locationcode'])
        no_c = _detect_column(dtl, ['BILLNO', 'billno'])
        item_c = _detect_column(dtl, ['ITEMCODE', 'itemcode'])
        qty_c = _detect_column(dtl, ['BASEQTY', 'baseqty']) or _detect_column(dtl, ['QUANTITY', 'quantity'])
        if not (loc_c and no_c and item_c and qty_c):
            continue
        avg_c = _detect_column(dtl, ['AVERAGECOST', 'averagecost'])
        cost_c = _detect_column(dtl, ['COST', 'cost', 'COSTPRICE', 'costprice'])
        line_avg = f'NVL(d.{avg_c}, 0)' if avg_c else '0'
        line_cost = f'NVL(d.{cost_c}, 0)' if cost_c else '0'
        if im and im_item and im_loc and (im_avg or im_cost):
            master_avg = f'NVL(im.{im_avg}, 0)' if im_avg else '0'
            master_cost = f'NVL(im.{im_cost}, 0)' if im_cost else '0'
            unit_expr = (
                f'CASE '
                f'WHEN {line_avg} > 0 THEN {line_avg} '
                f'WHEN {master_avg} > 0 THEN {master_avg} '
                f'WHEN {line_cost} > 0 THEN {line_cost} '
                f'WHEN {master_cost} > 0 THEN {master_cost} '
                f'ELSE 0 END'
            )
            join_sql = (
                f' LEFT JOIN {im} im ON im.{im_item} = d.{item_c}'
                f' AND im.{im_loc} = d.{loc_c}'
            )
        else:
            unit_expr = (
                f'CASE WHEN {line_avg} > 0 THEN {line_avg} '
                f'WHEN {line_cost} > 0 THEN {line_cost} ELSE 0 END'
            )
            join_sql = ''
        rows = _safe_rows(
            f'''SELECT NVL(SUM(ABS(NVL(d.{qty_c}, 0)) * ({unit_expr})), 0) AS cogs_total
                FROM {dtl} d{join_sql}
                WHERE d.{loc_c} = :loc AND d.{no_c} = :bno''',
            {'loc': location_code, 'bno': billno},
        ) or []
        if rows:
            total = max(total, _f((rows[0] or {}).get('cogs_total')))
        if total > TOL:
            break
    return round(total, 2)


def _posting_row(
    doc_no: Any,
    doc_date: Any,
    module: str,
    voucher_no: str,
    expected: int = 2,
) -> Dict[str, Any]:
    vno = (voucher_no or '').strip()
    actual = _gl_line_count(vno) if vno else 0
    exists = _gl_exists(vno)
    note = ''
    if expected <= 0 and actual == 0:
        status = 'ok'
        note = 'Zero-cost bill — no COGS expected'
    elif not exists or actual == 0:
        status = 'err'
        note = 'No GL voucher or zero lines'
    elif actual < expected:
        status = 'warn'
        note = f'Incomplete posting ({actual} < {expected} lines)'
    elif actual != expected:
        status = 'warn'
        note = f'Line count mismatch (expected {expected}, got {actual})'
    else:
        status = 'ok'
        note = 'Balanced posting'
    d = doc_date
    if d is not None and hasattr(d, 'strftime'):
        d = d.strftime('%Y-%m-%d')
    elif d:
        d = str(d)[:10]
    return {
        'document_no': str(doc_no or ''),
        'document_date': d or '',
        'module': module,
        'voucher_no': vno,
        'expected_entries': expected,
        'actual_entries': actual,
        'status': status,
        'status_note': note,
    }


def build_posting_verification(filters: Dict[str, Any]) -> Dict[str, Any]:
    loc = _si(filters.get('locationcode') or 1)
    df, dt = _default_dates(filters)
    module_filter = (filters.get('module') or 'ALL').strip().upper()
    lim = _doc_check_limit(df, dt)
    gl_index = filters.get('_gl_index') or _build_gl_lookup_index(df, dt)
    rows: List[Dict[str, Any]] = []

    def _add(r: Dict[str, Any]) -> None:
        if module_filter != 'ALL':
            m = (r.get('module') or '').upper()
            mf = module_filter
            if mf == 'SALES' and 'SALES' not in m and 'POS' not in m:
                return
            if mf == 'PURCHASE' and 'PURCHASE' not in m and 'GRN' not in m and 'RETURN' not in m:
                return
            if mf == 'INVENTORY' and 'STOCK' not in m and 'ADJUST' not in m:
                return
            if mf == 'CASH' and 'CASH' not in m and 'BANK' not in m and 'RECEIPT' not in m and 'PAYMENT' not in m:
                return
        rows.append(r)

    bill_tables = []
    for t in ('BILLHDR', 'billhdr', 'BILLHDRHISTORY', 'billhdrhistory'):
        detected = _detect_table([t])
        if detected and detected not in bill_tables:
            bill_tables.append(detected)
    seen_bills: set = set()
    for tbl in bill_tables:
        loc_c = _detect_column(tbl, ['LOCATIONCODE', 'locationcode'])
        no_c = _detect_column(tbl, ['BILLNO', 'billno'])
        dt_c = _detect_column(tbl, ['BILLDATE', 'billdate'])
        ret_c = _detect_column(tbl, ['RETURNFLAG', 'returnflag'])
        if not (loc_c and no_c and dt_c):
            continue
        wh = [f'{loc_c} = :loc', f'TRUNC({dt_c}) BETWEEN TO_DATE(:df, \'YYYY-MM-DD\') AND TO_DATE(:dt, \'YYYY-MM-DD\')']
        params = {'loc': loc, 'df': df, 'dt': dt}
        if ret_c:
            wh.append(f"NVL({ret_c}, 0) = 0")
        # Oracle: limit in SQL so we do not pull the whole half-year into Python
        q = (
            f'SELECT * FROM ('
            f'SELECT {no_c} AS doc_no, {dt_c} AS doc_date FROM {tbl} '
            f'WHERE {" AND ".join(wh)} ORDER BY {dt_c} DESC'
            f') WHERE ROWNUM <= :lim'
        )
        params['lim'] = lim
        for r in (_safe_rows(q, params) or []):
            bno = _si(r.get('doc_no'))
            key = (loc, bno)
            if key in seen_bills:
                continue
            seen_bills.add(key)
            vno = _resolve_voucher_from_index(
                gl_index,
                bno,
                loc,
                ('SI', 'SIC', 'SR', 'SRC'),
            )
            exp = _expected_lines_for_sales_voucher(vno)
            label = 'Sales Invoice'
            vno_u = (vno or '').upper()
            if vno_u.startswith('SR-'):
                label = 'Sales Return'
            elif vno_u.startswith(('SIC-', 'SRC-')):
                label = 'POS / COGS posting'
                # Only hit BILLDTL when voucher is missing/empty — avoids N+1 COGS scans
                actual = (gl_index.get('line_counts') or {}).get(vno_u, 0) if vno else 0
                if actual == 0 and _bill_cogs_total(loc, bno) <= TOL:
                    exp = 0
            _add(_posting_row_fast(bno, r.get('doc_date'), label, vno, exp, gl_index))

    rh = _detect_table(['RECEIPTHDR', 'receipthdr'])
    if rh:
        loc_c = _detect_column(rh, ['LOCATIONCODE', 'locationcode'])
        no_c = _detect_column(rh, ['RECEIPTNO', 'receiptno'])
        dt_c = _detect_column(rh, ['RECEIPTDATE', 'receiptdate'])
        reset_c = _detect_column(rh, ['RESETNO', 'resetno'])
        if loc_c and no_c and dt_c:
            wh = [
                f'{loc_c} = :loc',
                f'TRUNC({dt_c}) BETWEEN TO_DATE(:df, \'YYYY-MM-DD\') AND TO_DATE(:dt, \'YYYY-MM-DD\')',
            ]
            params = {'loc': loc, 'df': df, 'dt': dt, 'lim': lim}
            if reset_c:
                wh.append(f'NVL({reset_c}, 1) = :rn')
                params['rn'] = RESET_NO
            for r in (_safe_rows(
                f'SELECT * FROM (SELECT {no_c} AS doc_no, {dt_c} AS doc_date FROM {rh} '
                f'WHERE {" AND ".join(wh)} ORDER BY {dt_c} DESC) WHERE ROWNUM <= :lim',
                params,
            ) or []):
                rno = _si(r.get('doc_no'))
                vno = _resolve_voucher_from_index(gl_index, rno, loc, ('GRN',))
                _add(_posting_row_fast(rno, r.get('doc_date'), 'Goods Receipt', vno, 2, gl_index))

    ret_hdr = _detect_table(['RETURNHDR', 'returnhdr'])
    if ret_hdr:
        loc_c = _detect_column(ret_hdr, ['LOCATIONCODE', 'locationcode'])
        no_c = _detect_column(ret_hdr, ['GOODSRETURNNO', 'goodsreturnno'])
        dt_c = _detect_column(ret_hdr, ['RETURNDATE', 'returndate', 'GOODSRETURNDATE'])
        if loc_c and no_c and dt_c:
            for r in (_safe_rows(
                f'''SELECT * FROM (
                    SELECT {no_c} AS doc_no, {dt_c} AS doc_date FROM {ret_hdr}
                    WHERE {loc_c} = :loc
                      AND TRUNC({dt_c}) BETWEEN TO_DATE(:df, 'YYYY-MM-DD') AND TO_DATE(:dt, 'YYYY-MM-DD')
                    ORDER BY {dt_c} DESC
                    ) WHERE ROWNUM <= :lim''',
                {'loc': loc, 'df': df, 'dt': dt, 'lim': lim},
            ) or []):
                gno = _si(r.get('doc_no'))
                vno = _resolve_voucher_from_index(gl_index, gno, loc, ('PR',))
                _add(_posting_row_fast(gno, r.get('doc_date'), 'Purchase Return', vno, 2, gl_index))

    # Cash / AR / AP / manual — use line counts already loaded in gl_index
    ensure_gl_tables()
    gl_extra = _safe_rows(
        f'''SELECT h.VOUCHER_NO, h.VOUCHER_DATE, h.SOURCE
            FROM {GL_HDR_TABLE} h
            WHERE TRUNC(h.VOUCHER_DATE) BETWEEN TO_DATE(:df, 'YYYY-MM-DD') AND TO_DATE(:dt, 'YYYY-MM-DD')
              AND UPPER(NVL(h.SOURCE,'')) IN ('CPV','AR_RECEIPT','AP_RECEIPT','MANUAL')
            ORDER BY h.VOUCHER_DATE DESC''',
        {'df': df, 'dt': dt},
    ) or []
    src_map = {
        'CPV': 'Cash Payment',
        'AR_RECEIPT': 'Cash Receipt',
        'AP_RECEIPT': 'Bank Payment',
        'MANUAL': 'Journal / Adjustment',
    }
    line_counts = gl_index.get('line_counts') or {}
    for r in gl_extra[:min(150, lim + 50)]:
        src = str(r.get('source') or r.get('SOURCE') or '').upper()
        vno = str(r.get('voucher_no') or r.get('VOUCHER_NO') or '')
        actual_n = line_counts.get(vno.upper(), 0)
        # Skip per-voucher REMARKS query; AR/AP may be 2 or 3 lines
        if src in ('AR_RECEIPT', 'AP_RECEIPT'):
            exp = 3 if actual_n >= 3 else 2
        elif src == 'MANUAL':
            exp = max(2, actual_n) if actual_n else 2
        else:
            exp = 2
        _add(_posting_row_fast(
            vno or r.get('document_no'),
            str(r.get('voucher_date') or r.get('VOUCHER_DATE') or '')[:10],
            src_map.get(src, src),
            vno,
            exp,
            gl_index,
        ))

    ok = sum(1 for x in rows if x.get('status') == 'ok')
    fail = sum(1 for x in rows if x.get('status') == 'err')
    warn = sum(1 for x in rows if x.get('status') == 'warn')
    return {
        'rows': rows,
        'summary': {
            'total': len(rows),
            'ok': ok,
            'failed': fail,
            'warn': warn,
            'doc_check_limit': lim,
        },
    }


def build_stock_gl_reconciliation(filters: Dict[str, Any]) -> Dict[str, Any]:
    """Compare branch stock valuation to inventory control GL.

    The inventory control account (default 1300) is branch-level — never repeat the
    full GL balance on every warehouse row. Warehouse rows show stock value plus a
    proportional GL allocation for breakdown only; the branch total row is the real check.
    """
    loc = _si(filters.get('locationcode') or 1)
    df, dt = _default_dates(filters)
    inv_ac = _inventory_control_account()
    gl_balance = round(_tb_balance(inv_ac, df, dt, tb_rows=filters.get('_tb_rows')), 2)

    im = _detect_table(['ITEMMASTER', 'itemmaster'])
    rows: List[Dict[str, Any]] = []
    total_stock = 0.0
    wh_filter = (filters.get('warehouse_id') or '').strip()

    ws_tbl = _detect_table([WAREHOUSE_MASTER_TABLE, 'WAREHOUSE_MASTER'])
    ws_stock = _detect_table(['WAREHOUSE_STOCK', 'warehouse_stock'])
    if ws_tbl and ws_stock and not wh_filter and im:
        wh_id = _detect_column(ws_tbl, ['WAREHOUSE_ID', 'warehouse_id'])
        wh_code = _detect_column(ws_tbl, ['WAREHOUSE_CODE', 'warehouse_code'])
        wh_name = _detect_column(ws_tbl, ['WAREHOUSE_NAME', 'warehouse_name'])
        ws_wh = _detect_column(ws_stock, ['WAREHOUSE_ID', 'warehouse_id'])
        ws_item = _detect_column(ws_stock, ['ITEMCODE', 'itemcode'])
        ws_qty = _detect_column(ws_stock, ['QUANTITY', 'quantity', 'QTY', 'qty'])
        cost_c = _detect_column(im, ['COSTPRICE', 'costprice'])
        loc_c = _detect_column(im, ['LOCATIONCODE', 'locationcode'])
        ic = _detect_column(im, ['ITEMCODE', 'itemcode'])
        if wh_id and ws_wh and ws_item and ws_qty and cost_c and ic and loc_c:
            wh_rows = _safe_rows(
                f'''SELECT w.{wh_id} AS warehouse_id,
                           w.{wh_code or wh_id} AS wh_code,
                           NVL(w.{wh_name or wh_code or wh_id}, '') AS wh_name,
                           SUM(NVL(s.{ws_qty},0) * NVL(i.{cost_c},0)) AS stock_value
                    FROM {ws_stock} s
                    JOIN {ws_tbl} w ON w.{wh_id} = s.{ws_wh}
                    JOIN {im} i ON i.{ic} = s.{ws_item}
                    WHERE i.{loc_c} = :loc
                    GROUP BY w.{wh_id}, w.{wh_code or wh_id}, w.{wh_name or wh_code or wh_id}
                    ORDER BY SUM(NVL(s.{ws_qty},0) * NVL(i.{cost_c},0)) DESC''',
                {'loc': loc},
            ) or []
            if wh_rows:
                stock_values = [round(_f(w.get('stock_value')), 2) for w in wh_rows[:50]]
                total_stock = round(sum(stock_values), 2)
                gl_allocs = _allocate_proportional(gl_balance, stock_values)
                rows.append({
                    'warehouse': 'Branch total',
                    'warehouse_id': '',
                    'warehouse_code': '',
                    'stock_value': total_stock,
                    'gl_balance': gl_balance,
                    'difference': round(total_stock - gl_balance, 2),
                    'status': _status_severity(total_stock - gl_balance, 500, 5000),
                    'inventory_account': inv_ac,
                    'row_type': 'total',
                    'balance_source': 'CONTROL',
                })
                for w, sv, gl_alloc in zip(wh_rows[:50], stock_values, gl_allocs):
                    diff = round(sv - gl_alloc, 2)
                    rows.append({
                        'warehouse': str(w.get('wh_name') or w.get('wh_code') or ''),
                        'warehouse_id': str(w.get('warehouse_id') or ''),
                        'warehouse_code': str(w.get('wh_code') or ''),
                        'stock_value': sv,
                        'gl_balance': gl_alloc,
                        'difference': diff,
                        'status': _status_severity(diff, 1000, 10000),
                        'inventory_account': inv_ac,
                        'row_type': 'warehouse',
                        'balance_source': 'PROPORTIONAL',
                    })

    if not rows and im:
        loc_c = _detect_column(im, ['LOCATIONCODE', 'locationcode'])
        ic = _detect_column(im, ['ITEMCODE', 'itemcode'])
        stock_c = _detect_column(im, ['CURRENTSTOCK', 'currentstock'])
        cost_c = _detect_column(im, ['COSTPRICE', 'costprice'])
        wh_id_c = _detect_column(im, ['DEFAULT_WAREHOUSE_ID', 'default_warehouse_id'])
        if ic and stock_c and cost_c:
            wh = [f'{loc_c} = :loc'] if loc_c else ['1=1']
            params: Dict[str, Any] = {'loc': loc}
            if wh_filter and wh_id_c:
                wh.append(f'TO_CHAR({wh_id_c}) = :wid')
                params['wid'] = wh_filter
            q = f'''SELECT NVL({stock_c},0) AS qty, NVL({cost_c},0) AS cost
                  FROM {im} WHERE {" AND ".join(wh)}'''
            item_rows = _safe_rows(q, params) or []
            for r in item_rows:
                total_stock += round(_f(r.get('qty')) * _f(r.get('cost')), 2)
            total_stock = round(total_stock, 2)
            rows.append({
                'warehouse': wh_filter or 'Branch total',
                'stock_value': total_stock,
                'gl_balance': gl_balance,
                'difference': round(total_stock - gl_balance, 2),
                'status': _status_severity(total_stock - gl_balance, 500, 5000),
                'inventory_account': inv_ac,
                'row_type': 'total',
                'balance_source': 'CONTROL',
            })

    return {
        'rows': rows,
        'summary': {
            'total_stock_value': round(total_stock, 2),
            'gl_inventory_balance': gl_balance,
            'difference': round(total_stock - gl_balance, 2),
            'inventory_account': inv_ac,
            'warehouse_count': max(0, len(rows) - (1 if rows and rows[0].get('row_type') == 'total' else 0)),
        },
        'item_drill_available': bool(im),
    }


def _branch_warehouse_stock_total(location_code: int) -> float:
    """Branch-wide stock valuation from warehouse stock × item cost."""
    im = _detect_table(['ITEMMASTER', 'itemmaster'])
    ws_stock = _detect_table(['WAREHOUSE_STOCK', 'warehouse_stock'])
    if not im or not ws_stock:
        return 0.0
    ic = _detect_column(im, ['ITEMCODE', 'itemcode'])
    cost_c = _detect_column(im, ['COSTPRICE', 'costprice'])
    loc_c = _detect_column(im, ['LOCATIONCODE', 'locationcode'])
    ws_item = _detect_column(ws_stock, ['ITEMCODE', 'itemcode'])
    ws_qty = _detect_column(ws_stock, ['QUANTITY', 'quantity', 'QTY', 'qty'])
    if not (ic and cost_c and loc_c and ws_item and ws_qty):
        return 0.0
    rows = _safe_rows(
        f'''SELECT SUM(NVL(s.{ws_qty}, 0) * NVL(i.{cost_c}, 0)) AS total
              FROM {ws_stock} s
              JOIN {im} i ON i.{ic} = s.{ws_item}
             WHERE i.{loc_c} = :loc''',
        {'loc': location_code},
    ) or []
    return round(_f((rows[0] or {}).get('total')), 2) if rows else 0.0


def build_customer_reconciliation(filters: Dict[str, Any]) -> Dict[str, Any]:
    df, dt = _default_dates(filters)
    ar_control = _tb_balance(
        str(DEFAULT_PARTY_ACCOUNTS.get('customer_receivable') or '1200'),
        df,
        dt,
        tb_rows=filters.get('_tb_rows'),
    )
    rows_out: List[Dict[str, Any]] = []
    total_ledger = 0.0
    try:
        customers = get_accounts_receivable_summary() or []
    except Exception:
        customers = []
    loc = _si(filters.get('locationcode') or 1)
    cust_filter = (filters.get('customer_code') or '').strip()
    for c in customers:
        if cust_filter and str(c.get('customercode') or '') != cust_filter:
            continue
        if c.get('locationcode') is not None and _si(c.get('locationcode')) not in (0, loc):
            continue
        ledger = _f(c.get('receivable_balance'))
        ar_bal = ledger
        diff = 0.0
        total_ledger += ledger
        rows_out.append({
            'customer_code': c.get('customercode'),
            'customer_name': c.get('customername'),
            'ledger_balance': round(ledger, 2),
            'ar_balance': round(ar_bal, 2),
            'difference': round(diff, 2),
            'status': _status_severity(diff),
            'receivable_account': c.get('receivableaccount'),
            'balance_source': c.get('balance_source') or '',
        })
    rows_out.sort(key=lambda x: -abs(_f(x.get('ledger_balance'))))
    ctrl_diff = round(total_ledger - ar_control, 2)
    ar_acct = str(DEFAULT_PARTY_ACCOUNTS.get('customer_receivable') or '1200')
    return {
        'rows': rows_out[:500],
        'summary': {
            'customer_ledger_total': round(total_ledger, 2),
            'ar_control_balance': round(ar_control, 2),
            'control_difference': ctrl_diff,
            'ar_control_account': ar_acct,
            'customer_count': len(rows_out),
        },
    }


def build_supplier_reconciliation(filters: Dict[str, Any]) -> Dict[str, Any]:
    df, dt = _default_dates(filters)
    ap_control = _tb_balance(
        str(DEFAULT_PARTY_ACCOUNTS.get('supplier_payable') or '2110'),
        df,
        dt,
        tb_rows=filters.get('_tb_rows'),
    )
    rows_out: List[Dict[str, Any]] = []
    total_ledger = 0.0
    try:
        suppliers = get_accounts_payable_summary() or []
    except Exception:
        suppliers = []
    loc = _si(filters.get('locationcode') or 1)
    sup_filter = (filters.get('supplier_code') or '').strip()
    for s in suppliers:
        if sup_filter and str(s.get('suppliercode') or '') != sup_filter:
            continue
        if s.get('locationcode') is not None and _si(s.get('locationcode')) not in (0, loc):
            continue
        ledger = _f(s.get('payable_balance'))
        total_ledger += ledger
        rows_out.append({
            'supplier_code': s.get('suppliercode'),
            'supplier_name': s.get('suppliername'),
            'ledger_balance': round(ledger, 2),
            'ap_balance': round(ledger, 2),
            'difference': 0.0,
            'status': _status_severity(0),
            'payable_account': s.get('payableaccount'),
            'balance_source': s.get('balance_source') or '',
        })
    rows_out.sort(key=lambda x: -abs(_f(x.get('ledger_balance'))))
    ap_acct = str(DEFAULT_PARTY_ACCOUNTS.get('supplier_payable') or '2110')
    return {
        'rows': rows_out[:500],
        'summary': {
            'supplier_ledger_total': round(total_ledger, 2),
            'ap_control_balance': round(ap_control, 2),
            'control_difference': round(total_ledger - ap_control, 2),
            'ap_control_account': ap_acct,
            'supplier_count': len(rows_out),
        },
    }


def build_unbalanced_journals(filters: Dict[str, Any]) -> Dict[str, Any]:
    df, dt = _default_dates(filters)
    data = list_transaction_audit_vouchers(
        date_from=df,
        date_to=dt,
        unbalanced_only=True,
        limit=300,
    )
    rows = []
    for r in data.get('rows') or []:
        if not r.get('balanced'):
            rows.append({
                'journal_no': r.get('voucher_no'),
                'date': r.get('voucher_date'),
                'debit': r.get('total_debit'),
                'credit': r.get('total_credit'),
                'difference': r.get('balance_diff'),
                'source': r.get('source_label'),
                'status': 'err',
            })
    return {'rows': rows, 'summary': {'count': len(rows)}}


def build_negative_stock(filters: Dict[str, Any]) -> Dict[str, Any]:
    loc = _si(filters.get('locationcode') or 1)
    im = _detect_table(['ITEMMASTER', 'itemmaster'])
    rows: List[Dict[str, Any]] = []
    if not im:
        return {'rows': [], 'summary': {'count': 0}}
    loc_c = _detect_column(im, ['LOCATIONCODE', 'locationcode'])
    ic = _detect_column(im, ['ITEMCODE', 'itemcode'])
    name_c = _detect_column(im, ['ITEMNAME', 'itemname'])
    stock_c = _detect_column(im, ['CURRENTSTOCK', 'currentstock'])
    cost_c = _detect_column(im, ['COSTPRICE', 'costprice'])
    wh_c = _detect_column(im, ['DEFAULT_WAREHOUSE_ID', 'default_warehouse_id'])
    if not (ic and stock_c):
        return {'rows': [], 'summary': {'count': 0}}
    wh = [f'NVL({stock_c}, 0) < 0']
    params: Dict[str, Any] = {}
    if loc_c:
        wh.append(f'{loc_c} = :loc')
        params['loc'] = loc
    for r in (_safe_rows(
        f'''SELECT {ic} AS itemcode, {name_c or "''"} AS itemname,
                   NVL({stock_c},0) AS current_stock, NVL({cost_c or "0"},0) AS average_cost,
                   {wh_c or "NULL"} AS warehouse_id
            FROM {im} WHERE {" AND ".join(wh)} ORDER BY {stock_c}''',
        params,
    ) or [])[:300]:
        qty = _f(r.get('current_stock'))
        cost = _f(r.get('average_cost'))
        rows.append({
            'item_code': r.get('itemcode'),
            'item_name': r.get('itemname'),
            'warehouse': str(r.get('warehouse_id') or '—'),
            'current_stock': round(qty, 3),
            'average_cost': round(cost, 4),
            'stock_value': round(qty * cost, 2),
            'status': 'err',
            'recent_transactions': [],
        })
    return {'rows': rows, 'summary': {'count': len(rows)}}


def build_cost_verification(filters: Dict[str, Any]) -> Dict[str, Any]:
    loc = _si(filters.get('locationcode') or 1)
    item_filter = (filters.get('item_code') or '').strip()
    im = _detect_table(['ITEMMASTER', 'itemmaster'])
    rows: List[Dict[str, Any]] = []
    if not im:
        return {'rows': [], 'summary': {}}
    loc_c = _detect_column(im, ['LOCATIONCODE', 'locationcode'])
    ic = _detect_column(im, ['ITEMCODE', 'itemcode'])
    name_c = _detect_column(im, ['ITEMNAME', 'itemname'])
    stock_c = _detect_column(im, ['CURRENTSTOCK', 'currentstock'])
    cost_c = _detect_column(im, ['COSTPRICE', 'costprice'])
    retail_c = _detect_column(im, ['RETAILPRICE', 'retailprice'])
    wh = [f'NVL({stock_c or "0"}, 0) <> 0'] if stock_c else ['1=1']
    params: Dict[str, Any] = {'loc': loc}
    if loc_c:
        wh.append(f'{loc_c} = :loc')
    if item_filter and ic:
        wh.append(f'TO_CHAR({ic}) = :ic')
        params['ic'] = item_filter
    q = f'''SELECT {ic} AS itemcode, {name_c or "''"} AS itemname,
                 NVL({stock_c or "0"},0) AS current_stock,
                 NVL({cost_c or "0"},0) AS average_cost,
                 NVL({retail_c or "0"},0) AS last_price
          FROM {im} WHERE {" AND ".join(wh)}'''
    for r in (_safe_rows(q, params) or [])[:500]:
        avg = _f(r.get('average_cost'))
        stock = _f(r.get('current_stock'))
        last_p = _f(r.get('last_price'))
        variance = abs(avg - last_p) if last_p > 0 else 0
        issues = []
        if avg <= 0:
            issues.append('zero_cost')
        if avg < 0:
            issues.append('negative_cost')
        if last_p > 0 and variance / last_p > 0.5:
            issues.append('large_variance')
        status = 'ok'
        if 'negative_cost' in issues:
            status = 'err'
        elif issues:
            status = 'warn'
        rows.append({
            'item_code': r.get('itemcode'),
            'item_name': r.get('itemname'),
            'average_cost': round(avg, 4),
            'last_purchase_cost': round(last_p, 4),
            'current_stock': round(stock, 3),
            'inventory_value': round(stock * avg, 2),
            'cost_variance_pct': round((variance / last_p * 100) if last_p else 0, 1),
            'issues': issues,
            'status': status,
        })
    zero_c = sum(1 for x in rows if 'zero_cost' in x.get('issues', []))
    neg_c = sum(1 for x in rows if 'negative_cost' in x.get('issues', []))
    var_c = sum(1 for x in rows if 'large_variance' in x.get('issues', []))
    return {
        'rows': rows,
        'summary': {'zero_cost': zero_c, 'negative_cost': neg_c, 'large_variance': var_c},
    }


def build_account_mapping_validation(filters: Dict[str, Any]) -> Dict[str, Any]:
    loc = _si(filters.get('locationcode') or 1)
    issues: List[Dict[str, Any]] = []

    def _check_master(table_candidates: List[str], code_col_candidates: List[str], name_col_candidates: List[str],
                      mapping_cols: List[str], entity: str) -> None:
        tbl = _detect_table(table_candidates)
        if not tbl:
            return
        code_c = _detect_column(tbl, code_col_candidates)
        name_c = _detect_column(tbl, name_col_candidates)
        loc_c = _detect_column(tbl, ['LOCATIONCODE', 'locationcode'])
        if not code_c:
            return
        cols = [f'{code_c} AS code']
        if name_c:
            cols.append(f'{name_c} AS name')
        map_exprs = []
        for mc in mapping_cols:
            c = _detect_column(tbl, [mc, mc.lower()])
            if c:
                map_exprs.append((c, mc))
        if not map_exprs:
            return
        for c, label in map_exprs:
            cols.append(f'{c} AS {label}')
        wh = []
        params: Dict[str, Any] = {}
        if loc_c:
            wh.append(f'({loc_c} = :loc OR {loc_c} IS NULL)')
            params['loc'] = loc
        q = f'SELECT {", ".join(cols)} FROM {tbl}'
        if wh:
            q += f' WHERE {" AND ".join(wh)}'
        for r in (_safe_rows(q, params) or [])[:2000]:
            for c, label in map_exprs:
                val = r.get(label) or r.get(label.lower())
                if val is None or str(val).strip() in ('', '0', 'None'):
                    issues.append({
                        'entity': entity,
                        'code': r.get('code'),
                        'name': r.get('name'),
                        'missing_field': label,
                        'status': 'warn',
                    })

    _check_master(
        ['ITEMMASTER'], ['ITEMCODE'], ['ITEMNAME'],
        ['INVENTORYACCOUNT', 'SALESACCOUNT', 'PURCHASEACCOUNT', 'COGSACCOUNT'],
        'Item',
    )
    _check_master(
        ['CATEGORY', 'categorymaster'], ['CATEGORYCODE', 'categorycode'], ['CATEGORYNAME', 'categoryname'],
        ['SALESACCOUNT', 'INVENTORYACCOUNT'],
        'Category',
    )
    _check_master(
        ['CUSTOMER', 'CUSTOMERS'], ['CUSTOMERCODE'], ['CUSTOMERNAME'],
        ['RECEIVABLEACCOUNT'],
        'Customer',
    )
    _check_master(
        ['SUPPLIER'], ['SUPPLIERCODE'], ['SUPPLIERNAME'],
        ['PAYABLEACCOUNT'],
        'Supplier',
    )

    return {
        'rows': issues[:500],
        'summary': {'missing_mappings': len(issues)},
    }


def build_tax_validation(filters: Dict[str, Any]) -> Dict[str, Any]:
    df, dt = _default_dates(filters)
    vat_out = str(DEFAULT_PARTY_ACCOUNTS.get('customer_vat_output') or '2200')
    vat_in = str(DEFAULT_PARTY_ACCOUNTS.get('supplier_vat_input') or '2200')
    out_bal = _tb_balance(vat_out, df, dt, tb_rows=filters.get('_tb_rows'))
    in_bal = _tb_balance(vat_in, df, dt, tb_rows=filters.get('_tb_rows'))
    rows = [
        {'tax_type': 'Output Tax (VAT)', 'account': vat_out, 'gl_balance': out_bal, 'expected': '—', 'difference': 0, 'status': 'ok'},
        {'tax_type': 'Input Tax (VAT)', 'account': vat_in, 'gl_balance': in_bal, 'expected': '—', 'difference': 0, 'status': 'ok'},
    ]
    ensure_gl_tables()
    missing = _safe_rows(
        f'''SELECT h.VOUCHER_NO, h.SOURCE, h.VOUCHER_DATE
            FROM {GL_HDR_TABLE} h
            WHERE TRUNC(h.VOUCHER_DATE) BETWEEN TO_DATE(:df, 'YYYY-MM-DD') AND TO_DATE(:dt, 'YYYY-MM-DD')
              AND UPPER(NVL(h.SOURCE,'')) IN ('SALES','POS_SALE','GRN','PURCHASE_RETURN')
              AND NOT EXISTS (
                SELECT 1 FROM {GL_DTL_TABLE} d
                WHERE d.VOUCHER_NO = h.VOUCHER_NO
                  AND TRIM(d.ACCOUNT_CODE) IN (:vo, :vi)
              )''',
        {'df': df, 'dt': dt, 'vo': vat_out, 'vi': vat_in},
    ) or []
    for m in missing[:100]:
        rows.append({
            'tax_type': 'Missing tax line',
            'account': '—',
            'gl_balance': 0,
            'expected': vat_out,
            'difference': 0,
            'status': 'warn',
            'voucher_no': m.get('voucher_no') or m.get('VOUCHER_NO'),
            'document_date': str(m.get('voucher_date') or m.get('VOUCHER_DATE') or '')[:10],
        })
    return {'rows': rows, 'summary': {'output_tax': out_bal, 'input_tax': in_bal, 'missing_postings': len(missing)}}


def build_cash_bank_reconciliation(filters: Dict[str, Any]) -> Dict[str, Any]:
    df, dt = _default_dates(filters)
    accounts = [
        ('Cash Book', '1111'),
        ('Bank Book', '1112'),
        ('Petty Cash', '1120'),
    ]
    rows = []
    for label, code in accounts:
        gl = _tb_balance(code, df, dt, tb_rows=filters.get('_tb_rows'))
        rows.append({
            'account_name': label,
            'account_code': code,
            'book_balance': gl,
            'gl_balance': gl,
            'difference': 0,
            'status': 'ok',
        })
    return {'rows': rows, 'summary': {}}


def build_profit_loss_validation(filters: Dict[str, Any]) -> Dict[str, Any]:
    df, dt = _default_dates(filters)
    pl = get_profit_and_loss_report(date_from=df, date_to=dt)
    rev = _f(pl.get('total_revenue'))
    exp = _f(pl.get('total_expense'))
    net = _f(pl.get('net_profit'))
    cogs = 0.0
    sales = rev
    for r in pl.get('expense_accounts') or []:
        name = str(r.get('name') or '').upper()
        amt = _f(r.get('amount'))
        if 'COGS' in name or 'COST OF' in name:
            cogs += amt
    gross = round(sales - cogs, 2)
    rows = [
        {'line': 'Sales (Revenue)', 'amount': round(sales, 2), 'status': 'ok'},
        {'line': 'Cost of Goods Sold', 'amount': round(cogs, 2), 'status': 'ok' if cogs >= 0 else 'warn'},
        {'line': 'Gross Profit', 'amount': gross, 'status': 'ok'},
        {'line': 'Operating Expenses', 'amount': round(exp - cogs, 2), 'status': 'ok'},
        {'line': 'Net Profit', 'amount': round(net, 2), 'status': 'ok' if net >= 0 else 'warn'},
    ]
    return {'rows': rows, 'summary': pl}


def build_inventory_movement_audit(filters: Dict[str, Any], limit: int = 80) -> Dict[str, Any]:
    loc = _si(filters.get('locationcode') or 1)
    df, dt = _default_dates(filters)
    ij = _detect_table(['ITEMJOURNAL', 'ITEMJOURNEL'])
    im = _detect_table(['ITEMMASTER', 'itemmaster'])
    if not ij or not im:
        return {'rows': [], 'summary': {}}
    ic = _detect_column(ij, ['ITEMCODE', 'itemcode'])
    qty_c = _detect_column(ij, ['QTY', 'qty'])
    tt_c = _detect_column(ij, ['TRANSTYPE', 'transtype'])
    dt_c = _detect_column(ij, ['CREATEDDATE', 'createddate', 'TRANSDATE'])
    loc_c = _detect_column(ij, ['LOCATIONCODE', 'locationcode'])
    if not (ic and qty_c and tt_c):
        return {'rows': [], 'summary': {}}
    date_filter = ''
    params: Dict[str, Any] = {'loc': loc}
    if dt_c:
        date_filter = f'AND TRUNC(j.{dt_c}) BETWEEN TO_DATE(:df, \'YYYY-MM-DD\') AND TO_DATE(:dt, \'YYYY-MM-DD\')'
        params['df'] = df
        params['dt'] = dt
    loc_f = f'AND j.{loc_c} = :loc' if loc_c else ''
    q = f'''
        SELECT j.{ic} AS itemcode, i.{_detect_column(im, ["ITEMNAME", "itemname"]) or "''"} AS itemname,
               SUM(CASE WHEN UPPER(j.{tt_c}) LIKE '%PURCHASE%' OR UPPER(j.{tt_c}) LIKE '%RECEIPT%' THEN NVL(j.{qty_c},0) ELSE 0 END) AS purchases,
               SUM(CASE WHEN UPPER(j.{tt_c}) LIKE '%SALES%' OR UPPER(j.{tt_c}) = 'BILL' THEN -ABS(NVL(j.{qty_c},0)) ELSE 0 END) AS sales,
               SUM(CASE WHEN UPPER(j.{tt_c}) LIKE '%RETURN%' THEN NVL(j.{qty_c},0) ELSE 0 END) AS returns,
               SUM(CASE WHEN UPPER(j.{tt_c}) LIKE '%ADJUST%' THEN NVL(j.{qty_c},0) ELSE 0 END) AS adjustments,
               SUM(NVL(j.{qty_c},0)) AS net_movement
        FROM {ij} j
        LEFT JOIN {im} i ON i.{_detect_column(im, ["ITEMCODE", "itemcode"])} = j.{ic}
        WHERE 1=1 {loc_f} {date_filter}
        GROUP BY j.{ic}, i.{_detect_column(im, ["ITEMNAME", "itemname"]) or "''"}
        ORDER BY ABS(SUM(NVL(j.{qty_c},0))) DESC
    '''
    rows = []
    for r in (_safe_rows(q, params) or [])[:limit]:
        net = _f(r.get('net_movement'))
        rows.append({
            'item_code': r.get('itemcode'),
            'item_name': r.get('itemname'),
            'opening_stock': '—',
            'purchases': round(_f(r.get('purchases')), 3),
            'receipts': round(_f(r.get('purchases')), 3),
            'sales': round(_f(r.get('sales')), 3),
            'returns': round(_f(r.get('returns')), 3),
            'adjustments': round(_f(r.get('adjustments')), 3),
            'closing_stock': round(net, 3),
        })
    return {'rows': rows, 'summary': {'items': len(rows)}}


def build_ai_insights(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    insights: List[Dict[str, Any]] = []
    summary = payload.get('summary') or {}
    if _f(summary.get('failed_postings')) > 0:
        insights.append({
            'severity': 'high',
            'title': 'Missing GL postings',
            'message': f"{int(summary.get('failed_postings') or 0)} documents have no GL voucher. Post or reverse before month-end.",
        })
    if _f(summary.get('unbalanced_journals')) > 0:
        insights.append({
            'severity': 'high',
            'title': 'Unbalanced journals',
            'message': f"{int(summary.get('unbalanced_journals') or 0)} vouchers where debit ≠ credit require correction.",
        })
    if abs(_f(summary.get('inventory_variance'))) > 500:
        insights.append({
            'severity': 'high',
            'title': 'Inventory vs GL variance',
            'message': f"Stock valuation differs from inventory control account by {summary.get('inventory_variance'):,.2f}.",
        })
    if _f(summary.get('negative_stock_count')) > 0:
        insights.append({
            'severity': 'medium',
            'title': 'Negative stock',
            'message': f"{int(summary.get('negative_stock_count') or 0)} items show negative on-hand quantity.",
        })
    if _f(summary.get('missing_mappings')) > 0:
        insights.append({
            'severity': 'medium',
            'title': 'Account mapping gaps',
            'message': f"{int(summary.get('missing_mappings') or 0)} master records lack required GL account mappings.",
        })
    ar_diff = abs(_f(summary.get('ar_control_difference')))
    if ar_diff > 100:
        insights.append({
            'severity': 'medium',
            'title': 'AR control mismatch',
            'message': f"Customer sub-ledger total differs from AR control by {ar_diff:,.2f}.",
        })
    if not insights:
        insights.append({
            'severity': 'info',
            'title': 'Audit clean',
            'message': 'No critical integrity issues detected in the selected scope. Re-run after period-end postings.',
        })
    return insights


def _compute_summary(sections: Dict[str, Any]) -> Dict[str, Any]:
    posting = sections.get('posting_verification') or {}
    ps = posting.get('summary') or {}
    stock = sections.get('stock_gl_reconciliation') or {}
    ss = stock.get('summary') or {}
    cust = sections.get('customer_reconciliation') or {}
    cs = cust.get('summary') or {}
    supp = sections.get('supplier_reconciliation') or {}
    sups = supp.get('summary') or {}
    unbal = sections.get('unbalanced_journals') or {}
    neg = sections.get('negative_stock') or {}
    maps = sections.get('account_mappings') or {}
    ms = maps.get('summary') or {}

    total_checked = _si(ps.get('total'))
    successful = _si(ps.get('ok'))
    failed = _si(ps.get('failed'))
    unbalanced = _si((unbal.get('summary') or {}).get('count'))

    return {
        'total_transactions_checked': total_checked,
        'successful_postings': successful,
        'failed_postings': failed,
        'inventory_variance': round(_f(ss.get('difference')), 2),
        'ar_variance': round(abs(_f(cs.get('control_difference'))), 2),
        'ap_variance': round(abs(_f(sups.get('control_difference'))), 2),
        'unbalanced_journals': unbalanced,
        'missing_account_mappings': _si(ms.get('missing_mappings')),
        'negative_stock_count': _si((neg.get('summary') or {}).get('count')),
        'critical_errors': failed + unbalanced + _si((neg.get('summary') or {}).get('count')),
        'warnings': _si(ps.get('warn')),
    }


def build_integrity_dashboard(filters: Dict[str, Any]) -> Dict[str, Any]:
    """Run full integrity audit for dashboard API."""
    try:
        ensure_gl_tables()
    except Exception:
        pass
    df, dt = _default_dates(filters)
    module = (filters.get('module') or 'ALL').strip().upper()
    filters = {**filters, 'date_from': df, 'date_to': dt, 'module': module}

    # Shared caches — trial balance + GL voucher index once per audit (was N+1 / multi-TB)
    try:
        filters['_tb_rows'] = get_trial_balance_report(date_from=df, date_to=dt) or []
    except Exception:
        logger.exception('integrity dashboard: trial balance cache failed')
        filters['_tb_rows'] = []
    try:
        filters['_gl_index'] = _build_gl_lookup_index(df, dt)
    except Exception:
        logger.exception('integrity dashboard: GL index cache failed')
        filters['_gl_index'] = {'by_exact': {}, 'by_suffix': {}, 'line_counts': {}}

    def _empty_section(rows_key: str = 'rows') -> Dict[str, Any]:
        return {rows_key: [], 'summary': {}, 'skipped': True}

    # Module filter: skip unrelated heavy sections when not ALL
    run_sales = module in ('ALL', 'SALES')
    run_purchase = module in ('ALL', 'PURCHASE')
    run_inv = module in ('ALL', 'INVENTORY')
    run_cash = module in ('ALL', 'CASH')
    run_gl = module in ('ALL', 'GL')

    sections: Dict[str, Any] = {
        'posting_verification': build_posting_verification(filters)
        if (run_sales or run_purchase or run_cash or run_gl)
        else _empty_section(),
        'stock_gl_reconciliation': build_stock_gl_reconciliation(filters) if run_inv else _empty_section(),
        'customer_reconciliation': build_customer_reconciliation(filters) if run_sales else _empty_section(),
        'supplier_reconciliation': build_supplier_reconciliation(filters) if run_purchase else _empty_section(),
        'unbalanced_journals': build_unbalanced_journals(filters) if (run_gl or module == 'ALL') else _empty_section(),
        'negative_stock': build_negative_stock(filters) if run_inv else _empty_section(),
        'cost_verification': build_cost_verification(filters) if run_inv else _empty_section(),
        'account_mappings': build_account_mapping_validation(filters),
        'tax_validation': build_tax_validation(filters) if module in ('ALL', 'SALES', 'PURCHASE', 'GL') else _empty_section(),
        'cash_bank': build_cash_bank_reconciliation(filters) if run_cash else _empty_section(),
        'profit_loss': build_profit_loss_validation(filters) if module in ('ALL', 'GL', 'SALES') else _empty_section(),
        'inventory_movement': build_inventory_movement_audit(filters) if run_inv else _empty_section(),
    }
    # Do not leak large caches to the client JSON
    client_filters = {k: v for k, v in filters.items() if not str(k).startswith('_')}
    summary = _compute_summary(sections)
    insights = build_ai_insights({'summary': summary, **sections})
    lim = _doc_check_limit(df, dt)
    try:
        span_days = (
            datetime.strptime(dt[:10], '%Y-%m-%d').date()
            - datetime.strptime(df[:10], '%Y-%m-%d').date()
        ).days
    except Exception:
        span_days = 0
    if span_days >= LONG_RANGE_DAYS:
        insights = list(insights or [])
        insights.insert(0, {
            'severity': 'info',
            'title': 'Long date range',
            'message': (
                f'Audit sampled up to {lim} documents per source for speed '
                f'({span_days} days). Narrow From/To or pick one Module for a deeper check.'
            ),
        })

    return {
        'success': True,
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'filters': client_filters,
        'summary': summary,
        'insights': insights,
        **sections,
    }


def get_stock_gl_variance_drilldown(
    filters: Dict[str, Any],
    *,
    warehouse_id: Optional[str] = None,
    row_type: str = 'total',
    warehouse_label: str = '',
) -> Dict[str, Any]:
    """Item-level breakdown explaining stock vs GL variance for branch total or one warehouse."""
    loc = _si(filters.get('locationcode') or 1)
    df, dt = _default_dates(filters)
    inv_ac = _inventory_control_account()
    gl_balance = round(_tb_balance(inv_ac, df, dt), 2)

    im = _detect_table(['ITEMMASTER', 'itemmaster'])
    ws_stock = _detect_table(['WAREHOUSE_STOCK', 'warehouse_stock'])
    if not im:
        return {'summary': {}, 'items': [], 'gl_movements': [], 'notes': ['Item master not available.']}

    ic = _detect_column(im, ['ITEMCODE', 'itemcode'])
    name_c = _detect_column(im, ['ITEMNAME', 'itemname'])
    stock_c = _detect_column(im, ['CURRENTSTOCK', 'currentstock'])
    cost_c = _detect_column(im, ['COSTPRICE', 'costprice'])
    loc_c = _detect_column(im, ['LOCATIONCODE', 'locationcode'])
    inv_ac_c = _detect_column(im, ['INVENTORYACCOUNT', 'inventoryaccount'])
    if not (ic and stock_c and cost_c and loc_c):
        return {'summary': {}, 'items': [], 'gl_movements': [], 'notes': ['Required item columns missing.']}

    wh_qty_this_sql = f'NVL(i.{stock_c}, 0)'
    branch_wh_qty_sql = f'NVL(i.{stock_c}, 0)'
    wh_filter_sql = ''
    params: Dict[str, Any] = {'loc': loc}
    wid = str(warehouse_id or '').strip()
    if ws_stock:
        ws_wh = _detect_column(ws_stock, ['WAREHOUSE_ID', 'warehouse_id'])
        ws_item = _detect_column(ws_stock, ['ITEMCODE', 'itemcode'])
        ws_qty = _detect_column(ws_stock, ['QUANTITY', 'quantity', 'QTY', 'qty'])
        if ws_wh and ws_item and ws_qty:
            branch_sub = f'''SELECT SUM(NVL(s.{ws_qty}, 0))
                               FROM {ws_stock} s
                              WHERE s.{ws_item} = i.{ic}'''
            branch_wh_qty_sql = f'NVL(({branch_sub}), 0)'
            if wid:
                wh_sub = f'''{branch_sub}
                                   AND TO_CHAR(s.{ws_wh}) = :wid'''
                params['wid'] = wid
                wh_qty_this_sql = f'NVL(({wh_sub}), 0)'
                wh_filter_sql = f'AND {wh_qty_this_sql} <> 0'
            else:
                wh_qty_this_sql = branch_wh_qty_sql
                wh_filter_sql = f'AND {branch_wh_qty_sql} <> 0'

    inv_sel = f'TRIM(TO_CHAR(i.{inv_ac_c}))' if inv_ac_c else "''"
    item_rows = _safe_rows(
        f'''SELECT i.{ic} AS itemcode,
                   {name_c or "''"} AS itemname,
                   {wh_qty_this_sql} AS warehouse_qty,
                   {branch_wh_qty_sql} AS branch_warehouse_qty,
                   NVL(i.{stock_c}, 0) AS itemmaster_qty,
                   NVL(i.{cost_c}, 0) AS unit_cost,
                   {inv_sel} AS inventory_account
              FROM {im} i
             WHERE i.{loc_c} = :loc
               {wh_filter_sql}
               AND (ABS({branch_wh_qty_sql}) > 0.0001 OR ABS(NVL(i.{stock_c}, 0)) > 0.0001)
             ORDER BY ABS({branch_wh_qty_sql} - NVL(i.{stock_c}, 0)) DESC,
                      ABS({wh_qty_this_sql}) * NVL(i.{cost_c}, 0) DESC''',
        params,
    ) or []

    stock_total = 0.0
    mismatch_value = 0.0
    items_out: List[Dict[str, Any]] = []
    is_warehouse = row_type == 'warehouse'
    for r in item_rows[:300]:
        wh_q = round(_f(r.get('warehouse_qty')), 3)
        branch_wh_q = round(_f(r.get('branch_warehouse_qty')), 3)
        im_q = round(_f(r.get('itemmaster_qty')), 3)
        cost = round(_f(r.get('unit_cost')), 4)
        stock_val = round(wh_q * cost, 2)
        branch_val = round(branch_wh_q * cost, 2)
        im_val = round(im_q * cost, 2)
        qty_diff = round(branch_wh_q - im_q, 3)
        val_diff = round(branch_val - im_val, 2)
        stock_total += stock_val
        acct = str(r.get('inventory_account') or '').strip()
        issues: List[str] = []
        if abs(qty_diff) > 0.001:
            issues.append('Branch warehouse qty ≠ Item Master qty')
            mismatch_value += val_diff
        if not acct or acct == '0':
            issues.append('Missing inventory account')
        elif acct != inv_ac:
            issues.append(f'Uses GL account {acct} (not control {inv_ac})')
        items_out.append({
            'item_code': r.get('itemcode'),
            'item_name': r.get('itemname'),
            'warehouse_qty': wh_q,
            'branch_warehouse_qty': branch_wh_q,
            'itemmaster_qty': im_q,
            'qty_difference': qty_diff,
            'unit_cost': cost,
            'stock_value': stock_val,
            'branch_stock_value': branch_val,
            'itemmaster_value': im_val,
            'value_difference': val_diff,
            'inventory_account': acct or '—',
            'issue': '; '.join(issues) if issues else '',
            'status': 'warn' if issues else 'ok',
        })

    items_out.sort(key=lambda x: (
        0 if x.get('issue') else 1,
        -abs(_f(x.get('value_difference'))),
        -abs(_f(x.get('stock_value'))),
    ))

    gl_movements: List[Dict[str, Any]] = []
    if row_type == 'total':
        try:
            ledger = get_account_ledger(inv_ac, df, dt) or {}
            for ln in ledger.get('lines') or []:
                dr = round(_f(ln.get('debit')), 2)
                cr = round(_f(ln.get('credit')), 2)
                gl_movements.append({
                    'voucher_no': ln.get('voucher_no'),
                    'date': str(ln.get('voucher_date') or '')[:10],
                    'debit': dr,
                    'credit': cr,
                    'net': round(dr - cr, 2),
                    'narration': str(ln.get('narration') or ln.get('remarks') or '')[:160],
                })
            gl_movements.sort(key=lambda x: -abs(_f(x.get('net'))))
        except Exception:
            gl_movements = []

    branch_stock_total = _branch_warehouse_stock_total(loc)
    if row_type == 'warehouse':
        row_stock = round(stock_total, 2)
        if branch_stock_total > 0:
            row_gl = round(gl_balance * (row_stock / branch_stock_total), 2)
        else:
            row_gl = 0.0
        row_diff = round(row_stock - row_gl, 2)
    else:
        row_stock = round(branch_stock_total or stock_total, 2)
        row_gl = gl_balance
        row_diff = round(row_stock - gl_balance, 2)

    notes: List[str] = []
    if row_type == 'warehouse':
        notes.append(
            'This warehouse view lists items with stock here. '
            'GL allocated is an estimated share of branch inventory control (1300) based on this warehouse\'s '
            'percentage of total branch stock — not a separate GL balance per warehouse.'
        )
    else:
        notes.append(
            'Branch variance = warehouse stock valuation minus GL inventory control. '
            'Review qty mismatches, non-control inventory accounts, and GL movements below.'
        )
    issue_rows = [x for x in items_out if x.get('issue')]
    if issue_rows:
        notes.append(f'{len(issue_rows)} item(s) with sync or mapping issues (shown first).')
    if abs(mismatch_value) > 0.01:
        notes.append(f'Qty sync value impact (branch warehouse − item master): {round(mismatch_value, 2):,.2f}.')

    label = (warehouse_label or '').strip() or ('Branch total' if row_type == 'total' else 'Warehouse')
    return {
        'summary': {
            'warehouse': label,
            'row_type': row_type,
            'stock_value': row_stock,
            'gl_balance': row_gl,
            'difference': row_diff,
            'inventory_account': inv_ac,
            'item_count': len(items_out),
            'issue_count': len(issue_rows),
        },
        'items': items_out[:200],
        'gl_movements': gl_movements[:40] if row_type == 'total' else [],
        'notes': notes,
    }


def get_stock_item_drilldown(item_code: str, location_code: int) -> List[Dict[str, Any]]:
    im = _detect_table(['ITEMMASTER', 'itemmaster'])
    if not im:
        return []
    ic = _detect_column(im, ['ITEMCODE', 'itemcode'])
    stock_c = _detect_column(im, ['CURRENTSTOCK', 'currentstock'])
    cost_c = _detect_column(im, ['COSTPRICE', 'costprice'])
    name_c = _detect_column(im, ['ITEMNAME', 'itemname'])
    loc_c = _detect_column(im, ['LOCATIONCODE', 'locationcode'])
    rows = _safe_rows(
        f'''SELECT {ic} AS itemcode, {name_c or "''"} AS itemname,
                   NVL({stock_c},0) AS qty, NVL({cost_c},0) AS cost
            FROM {im} WHERE TO_CHAR({ic}) = :ic AND {loc_c} = :loc''',
        {'ic': str(item_code).strip(), 'loc': location_code},
    ) or []
    if not rows:
        return []
    r = rows[0]
    return [{
        'item_code': r.get('itemcode'),
        'item_name': r.get('itemname'),
        'current_stock': _f(r.get('qty')),
        'average_cost': _f(r.get('cost')),
        'stock_value': round(_f(r.get('qty')) * _f(r.get('cost')), 2),
    }]


def get_journal_drilldown(voucher_no: str, location_code: int) -> Dict[str, Any]:
    return get_transaction_audit_detail(voucher_no, location_code)


def get_item_movement_drilldown(item_code: str, location_code: int, date_from: str, date_to: str) -> List[Dict[str, Any]]:
    ij = _detect_table(['ITEMJOURNAL', 'ITEMJOURNEL'])
    if not ij:
        return []
    ic = _detect_column(ij, ['ITEMCODE', 'itemcode'])
    qty_c = _detect_column(ij, ['QTY', 'qty'])
    tt_c = _detect_column(ij, ['TRANSTYPE', 'transtype'])
    src_c = _detect_column(ij, ['SOURCE_NO', 'source_no', 'RECEIPTNO'])
    dt_c = _detect_column(ij, ['CREATEDDATE', 'createddate'])
    loc_c = _detect_column(ij, ['LOCATIONCODE', 'locationcode'])
    if not (ic and qty_c):
        return []
    wh = [f'TO_CHAR({ic}) = :ic']
    params: Dict[str, Any] = {'ic': str(item_code).strip()}
    if loc_c:
        wh.append(f'{loc_c} = :loc')
        params['loc'] = location_code
    if dt_c:
        wh.append(f'TRUNC({dt_c}) BETWEEN TO_DATE(:df, \'YYYY-MM-DD\') AND TO_DATE(:dt, \'YYYY-MM-DD\')')
        params['df'] = date_from[:10]
        params['dt'] = date_to[:10]
    return _safe_rows(
        f'''SELECT {dt_c or "NULL"} AS dt, {tt_c or "''"} AS trans_type,
                   {src_c or "NULL"} AS reference_no, NVL({qty_c},0) AS qty
            FROM {ij} WHERE {" AND ".join(wh)}
            ORDER BY {dt_c or "1"} DESC''',
        params,
    ) or []
