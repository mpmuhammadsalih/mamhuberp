"""GL / accounts audit — affected accounts for all posted transactions."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from db import (
    GL_DTL_TABLE,
    GL_HDR_TABLE,
    _detect_column,
    _detect_table,
    _fetch_rows,
    _safe_rows,
    ensure_gl_tables,
    get_gl_voucher_detail,
)

RESET_NO = 1
BALANCE_TOL = 0.02

# GL SOURCE → display label
SOURCE_LABELS: Dict[str, str] = {
    'GRN': 'Goods Receipt (GRN)',
    'PURCHASE_RETURN': 'Purchase Return',
    'PURCHASE_DEBIT_NOTE': 'Purchase Debit Note',
    'SALES': 'Sales Invoice',
    'SALES_RETURN': 'Sales Return',
    'POS_SALE': 'POS Sale',
    'POS_RETURN': 'POS Return',
    'AP_RECEIPT': 'AP Payment',
    'AR_RECEIPT': 'AR Receipt',
    'CPV': 'Cash Payment Voucher',
    'RECEIPT': 'Receipt Voucher',
    'PAYMENT': 'Payment Voucher',
    'CONTRA': 'Contra Voucher',
    'MANUAL': 'Manual Journal',
    'JE_REV': 'Journal Reversal',
    'OB_IMPORT': 'Opening Balance',
    'CUST_OPEN_OUT': 'Customer Opening',
    'SUPP_OPEN_OUT': 'Supplier Opening',
    'POS_SETTLEMENT': 'POS Settlement',
    'POS_SETTLEMENT_REV': 'POS Settlement Reversal',
    'ONLINE_SETTLEMENT': 'Online Settlement',
}

VOUCHER_PREFIX_DOC: Dict[str, str] = {
    'GRN': 'GRN',
    'PR': 'PR',
    'DN': 'DN',
    'SI': 'SI',
    'SR': 'SR',
    'CPV': 'CPV',
    'RCP': 'Receipt',
    'PAY': 'Payment',
    'CNTR': 'Contra',
}


def _f(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _source_label(src: str) -> str:
    s = str(src or '').strip().upper()
    return SOURCE_LABELS.get(s, s or '—')


def _parse_voucher_doc(voucher_no: str) -> Dict[str, Any]:
    """Parse VOUCHER_NO like GRN-1-12345 into doc_type + doc_no."""
    vno = str(voucher_no or '').strip()
    m = re.match(r'^([A-Z]+)-(\d+)-(\d+)$', vno, re.I)
    if m:
        prefix, loc, doc_no = m.group(1).upper(), int(m.group(2)), int(m.group(3))
        return {
            'doc_type': VOUCHER_PREFIX_DOC.get(prefix, prefix),
            'doc_no': doc_no,
            'location_code': loc,
            'voucher_prefix': prefix,
        }
    return {'doc_type': '', 'doc_no': 0, 'location_code': 0, 'voucher_prefix': ''}


def _fetch_staging_posting_lines(
    doc_type: str,
    doc_no: int,
    location_code: int,
) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """TBLGRNPOSTING* / TBLPRPOSTING* lines when applicable."""
    dt = str(doc_type or '').strip().upper()
    if doc_no <= 0:
        return [], None
    hdr_tbl: Optional[str] = None
    dtl_tbl: Optional[str] = None
    doc_col = ''
    if dt in ('GRN', 'RECEIPT'):
        hdr_tbl = _detect_table(['TBLGRNPOSTINGHDR', 'tblgrnpostinghdr'])
        dtl_tbl = _detect_table(['TBLGRNPOSTINGDTL', 'tblgrnpostingdtl'])
        doc_col = 'RECEIPTNO'
    elif dt in ('PR', 'PURCHASE_RETURN', 'RETURN'):
        hdr_tbl = _detect_table(['TBLPRPOSTINGHDR', 'tblprpostinghdr'])
        dtl_tbl = _detect_table(['TBLPRPOSTINGDTL', 'tblprpostingdtl'])
        doc_col = 'GOODSRETURNNO'
    if not hdr_tbl or not dtl_tbl or not doc_col:
        return [], None
    h_loc = _detect_column(hdr_tbl, ['LOCATIONCODE', 'locationcode'])
    h_reset = _detect_column(hdr_tbl, ['RESETNO', 'resetno'])
    h_doc = _detect_column(hdr_tbl, [doc_col, doc_col.lower()])
    d_loc = _detect_column(dtl_tbl, ['LOCATIONCODE', 'locationcode'])
    d_reset = _detect_column(dtl_tbl, ['RESETNO', 'resetno'])
    d_doc = _detect_column(dtl_tbl, [doc_col, doc_col.lower()])
    d_ln = _detect_column(dtl_tbl, ['LINENO', 'LINE_NO', 'lineno'])
    d_acc = _detect_column(dtl_tbl, ['ACCOUNTCODE', 'ACCOUNT_CODE', 'accountcode'])
    d_dr = _detect_column(dtl_tbl, ['DRAMOUNT', 'DR_AMOUNT', 'dramount'])
    d_cr = _detect_column(dtl_tbl, ['CRAMOUNT', 'CR_AMOUNT', 'cramount'])
    d_nar = _detect_column(dtl_tbl, ['NARRATION', 'narration'])
    if not h_doc or not d_doc or not d_acc:
        return [], None
    hdr_where = [f'h.{h_doc} = :dno']
    params: Dict[str, Any] = {'dno': int(doc_no)}
    if h_loc:
        hdr_where.append(f'h.{h_loc} = :loc')
        params['loc'] = int(location_code)
    if h_reset:
        hdr_where.append(f'h.{h_reset} = :rn')
        params['rn'] = RESET_NO
    hdr_cols = [f'h.{h_doc} AS doc_no']
    h_sub = _detect_column(hdr_tbl, ['SUBTOTAL', 'subtotal'])
    h_vat = _detect_column(hdr_tbl, ['VATAMOUNT', 'VAT_AMOUNT', 'vatamount'])
    h_tot = _detect_column(hdr_tbl, ['TOTALAMOUNT', 'TOTAL_AMOUNT', 'totalamount'])
    if h_sub:
        hdr_cols.append(f'h.{h_sub} AS subtotal')
    if h_vat:
        hdr_cols.append(f'h.{h_vat} AS vatamount')
    if h_tot:
        hdr_cols.append(f'h.{h_tot} AS totalamount')
    hdr_row: Optional[Dict[str, Any]] = None
    try:
        _, hrows = _fetch_rows(
            f"SELECT {', '.join(hdr_cols)} FROM {hdr_tbl} h WHERE {' AND '.join(hdr_where)}",
            params,
        )
        if hrows:
            hdr_row = hrows[0]
    except Exception:
        pass
    d_where = [f'd.{d_doc} = :dno']
    d_params = dict(params)
    if d_loc:
        d_where.append(f'd.{d_loc} = :loc')
    if d_reset:
        d_where.append(f'd.{d_reset} = :rn')
    d_cols = [
        f'd.{d_ln} AS lineno' if d_ln else 'NULL AS lineno',
        f'd.{d_acc} AS account_code',
        f'NVL(d.{d_dr}, 0) AS debit' if d_dr else '0 AS debit',
        f'NVL(d.{d_cr}, 0) AS credit' if d_cr else '0 AS credit',
        f'd.{d_nar} AS narration' if d_nar else "'' AS narration",
    ]
    lines: List[Dict[str, Any]] = []
    try:
        _, drows = _fetch_rows(
            f"SELECT {', '.join(d_cols)} FROM {dtl_tbl} d WHERE {' AND '.join(d_where)} ORDER BY {d_ln or d_acc}",
            d_params,
        )
        lines = drows or []
    except Exception:
        pass
    return lines, hdr_row


def list_transaction_audit_vouchers(
    *,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    source: Optional[str] = None,
    search: Optional[str] = None,
    unbalanced_only: bool = False,
    limit: int = 200,
) -> Dict[str, Any]:
    """List GL vouchers with debit/credit totals and balance status."""
    ensure_gl_tables()
    where = ['1=1']
    params: Dict[str, Any] = {}
    if date_from:
        where.append("TRUNC(h.VOUCHER_DATE) >= TO_DATE(:df, 'YYYY-MM-DD')")
        params['df'] = date_from[:10]
    if date_to:
        where.append("TRUNC(h.VOUCHER_DATE) <= TO_DATE(:dt, 'YYYY-MM-DD')")
        params['dt'] = date_to[:10]
    src = (source or '').strip().upper()
    if src and src != 'ALL':
        where.append('UPPER(TRIM(h.SOURCE)) = :src')
        params['src'] = src
    if search:
        sp = search.strip().upper().replace('*', '%')
        if '%' not in sp:
            sp = f'%{sp}%'
        params['search'] = sp
        where.append(
            '(UPPER(h.VOUCHER_NO) LIKE :search OR UPPER(NVL(h.REFERENCE_NO, \'\')) LIKE :search '
            'OR UPPER(NVL(h.NARRATION, \'\')) LIKE :search)'
        )
    q = f"""
        SELECT h.VOUCHER_NO, h.VOUCHER_DATE, h.REFERENCE_NO, h.NARRATION, h.SOURCE,
               h.CREATED_BY,
               SUM(d.DEBIT) AS total_debit, SUM(d.CREDIT) AS total_credit,
               COUNT(*) AS line_count
          FROM {GL_HDR_TABLE} h
          JOIN {GL_DTL_TABLE} d ON d.VOUCHER_NO = h.VOUCHER_NO
         WHERE {' AND '.join(where)}
         GROUP BY h.VOUCHER_NO, h.VOUCHER_DATE, h.REFERENCE_NO, h.NARRATION, h.SOURCE, h.CREATED_BY
         ORDER BY h.VOUCHER_DATE DESC, h.VOUCHER_NO DESC
    """
    try:
        rows = _safe_rows(q, params) or []
    except Exception:
        rows = []
    out: List[Dict[str, Any]] = []
    ok_c = warn_c = err_c = 0
    for r in rows[: max(1, min(int(limit or 200), 500))]:
        tdr = _f(r.get('total_debit'))
        tcr = _f(r.get('total_credit'))
        diff = abs(tdr - tcr)
        balanced = diff <= BALANCE_TOL
        if unbalanced_only and balanced:
            continue
        src_v = str(r.get('source') or r.get('SOURCE') or '').strip().upper()
        vdt = r.get('voucher_date') or r.get('VOUCHER_DATE')
        if vdt is not None and hasattr(vdt, 'strftime'):
            vdt = vdt.strftime('%Y-%m-%d')
        elif vdt:
            vdt = str(vdt)[:10]
        vno = str(r.get('voucher_no') or r.get('VOUCHER_NO') or '')
        parsed = _parse_voucher_doc(vno)
        status = 'ok' if balanced else 'err'
        if balanced:
            ok_c += 1
        else:
            err_c += 1
        out.append({
            'voucher_no': vno,
            'voucher_date': vdt or '',
            'reference_no': str(r.get('reference_no') or r.get('REFERENCE_NO') or ''),
            'narration': str(r.get('narration') or r.get('NARRATION') or ''),
            'source': src_v,
            'source_label': _source_label(src_v),
            'created_by': str(r.get('created_by') or r.get('CREATED_BY') or ''),
            'total_debit': round(tdr, 2),
            'total_credit': round(tcr, 2),
            'balance_diff': round(diff, 2),
            'line_count': int(r.get('line_count') or 0),
            'balanced': balanced,
            'status': status,
            'doc_type': parsed.get('doc_type') or '',
            'doc_no': parsed.get('doc_no') or 0,
        })
    return {
        'rows': out,
        'summary': {
            'total': len(out),
            'ok': ok_c,
            'err': err_c,
            'warn': warn_c,
        },
        'sources': list_gl_source_options(),
    }


def list_gl_source_options() -> List[Dict[str, str]]:
    ensure_gl_tables()
    try:
        rows = _safe_rows(
            f"SELECT DISTINCT UPPER(TRIM(SOURCE)) AS src FROM {GL_HDR_TABLE} WHERE SOURCE IS NOT NULL ORDER BY 1",
            {},
        ) or []
    except Exception:
        rows = []
    opts = [{'value': 'ALL', 'label': 'All sources'}]
    seen = {'ALL'}
    for r in rows:
        s = str(r.get('src') or '').strip().upper()
        if s and s not in seen:
            seen.add(s)
            opts.append({'value': s, 'label': _source_label(s)})
    for k in sorted(SOURCE_LABELS.keys()):
        if k not in seen:
            opts.append({'value': k, 'label': SOURCE_LABELS[k]})
    return opts


def get_transaction_audit_detail(voucher_no: str, location_code: int) -> Dict[str, Any]:
    """Full GL detail + staging posting lines + audit issues."""
    vno = str(voucher_no or '').strip()
    detail = get_gl_voucher_detail(vno)
    if not detail:
        return {
            'success': False,
            'error': 'Voucher not found.',
            'voucher_no': vno,
        }
    issues: List[Dict[str, Any]] = []
    tdr = _f(detail.get('total_debit'))
    tcr = _f(detail.get('total_credit'))
    diff = abs(tdr - tcr)
    if diff > BALANCE_TOL:
        issues.append({
            'code': 'UNBALANCED',
            'severity': 'err',
            'message': f'Debit {tdr:.2f} ≠ Credit {tcr:.2f} (diff {diff:.2f}).',
        })
    parsed = _parse_voucher_doc(vno)
    doc_type = str(parsed.get('doc_type') or '')
    doc_no = int(parsed.get('doc_no') or 0)
    loc = int(parsed.get('location_code') or location_code or 1)
    staging_lines, staging_hdr = _fetch_staging_posting_lines(doc_type, doc_no, loc)
    src = str(detail.get('source') or '').strip().upper()
    if doc_type in ('GRN', 'PR') and not staging_lines:
        issues.append({
            'code': 'NO_STAGING',
            'severity': 'warn',
            'message': f'No TBL{"GRN" if doc_type == "GRN" else "PR"}POSTING lines for this document (GL may still be valid).',
        })
    elif staging_lines and detail.get('lines'):
        st_dr = sum(_f(x.get('debit')) for x in staging_lines)
        st_cr = sum(_f(x.get('credit')) for x in staging_lines)
        if abs(st_dr - tdr) > 0.05 or abs(st_cr - tcr) > 0.05:
            issues.append({
                'code': 'STAGING_GL_MISMATCH',
                'severity': 'warn',
                'message': f'Staging posting totals (Dr {st_dr:.2f} / Cr {st_cr:.2f}) differ from GL voucher.',
            })
    accounts_affected = []
    seen_acc: set = set()
    for ln in detail.get('lines') or []:
        ac = str(ln.get('account_code') or '').strip()
        if ac and ac not in seen_acc:
            seen_acc.add(ac)
            accounts_affected.append({
                'account_code': ac,
                'account_name': ln.get('account_name') or '—',
            })
    status = 'err' if any(i.get('severity') == 'err' for i in issues) else (
        'warn' if issues else 'ok'
    )
    return {
        'success': True,
        'voucher_no': vno,
        'status': status,
        'source': src,
        'source_label': _source_label(src),
        'doc_type': doc_type,
        'doc_no': doc_no,
        'location_code': loc,
        'gl': detail,
        'staging_header': staging_hdr,
        'staging_lines': staging_lines,
        'accounts_affected': accounts_affected,
        'issues': issues,
        'summary': {
            'line_count': len(detail.get('lines') or []),
            'account_count': len(accounts_affected),
            'total_debit': tdr,
            'total_credit': tcr,
            'balanced': diff <= BALANCE_TOL,
        },
    }


def flatten_transaction_audit_export(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in rows or []:
        out.append({
            'voucher_no': r.get('voucher_no'),
            'voucher_date': r.get('voucher_date'),
            'source': r.get('source'),
            'source_label': r.get('source_label'),
            'reference_no': r.get('reference_no'),
            'narration': r.get('narration'),
            'doc_type': r.get('doc_type'),
            'doc_no': r.get('doc_no'),
            'total_debit': r.get('total_debit'),
            'total_credit': r.get('total_credit'),
            'balance_diff': r.get('balance_diff'),
            'status': r.get('status'),
            'created_by': r.get('created_by'),
        })
    return out
