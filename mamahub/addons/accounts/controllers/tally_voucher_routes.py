"""Tally ERP-style Receipt, Payment, and Contra vouchers (registered on accounts blueprint)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from nexa_http import flash, redirect, render_template, request, Response, session, url_for

from db import _get_connection, _safe_rows, create_gl_journal_entry, ensure_gl_tables, get_all_chart_of_accounts
from global_lookup import chart_accounts_by_code, is_cash_bank_account, validate_tally_voucher_account
from save_nonce import (
    GLOBAL_SAVE_NONCE_SESSION_KEY,
    commit_form_save_nonce,
    issue_save_nonce,
    reject_invalid_form_save_nonce,
)

from addons.accounts.controllers.routes import _parse_iso_date

_RECEIPT_LOCK = '_tally_receipt_submit_lock'
_PAYMENT_LOCK = '_tally_payment_submit_lock'
_CONTRA_LOCK = '_tally_contra_submit_lock'

VOUCHER_KINDS: Dict[str, Dict[str, Any]] = {
    'receipt': {
        'title': 'Receipt Voucher',
        'menu_label': 'Receipt',
        'hdr_table': 'RECEIPT_VOUCHER_HDR',
        'dtl_table': 'RECEIPT_VOUCHER_DTL',
        'prefix': 'RCP',
        'gl_source': 'RECEIPT',
        'lock_key': _RECEIPT_LOCK,
        'list_endpoint': 'accounts.receipt_voucher_list',
        'form_endpoint': 'accounts.receipt_voucher',
        'pdf_endpoint': 'accounts.receipt_voucher_pdf',
        'pdf_open_param': 'open_receipt_voucher_pdf',
        'pdf_party_label': 'Cash / Bank',
        'particulars_title': 'Credit Particulars (By)',
        'cash_label': 'Cash / Bank Account (Dr)',
        'audit_label': 'Receipt',
        'list_cash_col': 'Cash / Bank',
        'line_account_col': 'Ledger account',
        'cash_lookup_kind': 'cash_bank_strict',
        'line_lookup_kind': 'receipt_line',
    },
    'payment': {
        'title': 'Payment Voucher',
        'menu_label': 'Payment',
        'hdr_table': 'PAYMENT_VOUCHER_HDR',
        'dtl_table': 'PAYMENT_VOUCHER_DTL',
        'prefix': 'PAY',
        'gl_source': 'PAYMENT',
        'lock_key': _PAYMENT_LOCK,
        'list_endpoint': 'accounts.payment_voucher_list',
        'form_endpoint': 'accounts.payment_voucher',
        'pdf_endpoint': 'accounts.payment_voucher_pdf',
        'pdf_open_param': 'open_payment_voucher_pdf',
        'pdf_party_label': 'Cash / Bank',
        'particulars_title': 'Debit Particulars (To)',
        'cash_label': 'Cash / Bank Account (Cr)',
        'audit_label': 'Payment',
        'list_cash_col': 'Cash / Bank',
        'line_account_col': 'Ledger account',
        'cash_lookup_kind': 'cash_bank_strict',
        'line_lookup_kind': 'payment_line',
    },
    'contra': {
        'title': 'Contra Voucher',
        'menu_label': 'Contra',
        'hdr_table': 'CONTRA_VOUCHER_HDR',
        'dtl_table': 'CONTRA_VOUCHER_DTL',
        'prefix': 'CNTR',
        'gl_source': 'CONTRA',
        'lock_key': _CONTRA_LOCK,
        'list_endpoint': 'accounts.contra_voucher_list',
        'form_endpoint': 'accounts.contra_voucher',
        'pdf_endpoint': 'accounts.contra_voucher_pdf',
        'pdf_open_param': 'open_contra_voucher_pdf',
        'pdf_party_label': 'From Cash / Bank',
        'particulars_title': 'To Cash / Bank (Dr)',
        'cash_label': 'From Cash / Bank (Cr)',
        'audit_label': 'Contra',
        'list_cash_col': 'From A/c',
        'line_account_col': 'To Cash / Bank',
        'cash_lookup_kind': 'cash_bank_strict',
        'line_lookup_kind': 'cash_bank_strict',
    },
}


def _apply_db() -> bool:
    return True


def _kind_cfg(kind: str) -> Dict[str, Any]:
    cfg = VOUCHER_KINDS.get(str(kind or '').strip().lower())
    if not cfg:
        raise ValueError('Invalid voucher kind')
    return cfg


def _try_acquire_lock(lock_key: str, lock_seconds: float = 90.0) -> bool:
    now = datetime.now().timestamp()
    raw = session.get(lock_key)
    try:
        until = float(raw or 0)
    except (TypeError, ValueError):
        until = 0.0
    if until > now:
        return False
    session[lock_key] = now + float(lock_seconds)
    return True


def _release_lock(lock_key: str) -> None:
    session.pop(lock_key, None)


def _table_exists(cur: Any, table_name: str) -> bool:
    cur.execute(
        "SELECT COUNT(*) FROM user_tables WHERE UPPER(table_name) = UPPER(:t)",
        {'t': table_name},
    )
    row = cur.fetchone()
    return bool(row and int(row[0] or 0) > 0)


def _ensure_tables(cfg: Dict[str, Any]) -> None:
    hdr = cfg['hdr_table']
    dtl = cfg['dtl_table']
    ddl_hdr = f"""
        CREATE TABLE {hdr} (
            VOUCHER_NO VARCHAR2(30) NOT NULL,
            VOUCHER_DATE DATE NOT NULL,
            CASH_BANK_ACCOUNT VARCHAR2(20),
            REFERENCE_NO VARCHAR2(50),
            NARRATION VARCHAR2(1000),
            STATUS VARCHAR2(20) DEFAULT 'DRAFT',
            GL_VOUCHER_NO VARCHAR2(50),
            CREATED_BY VARCHAR2(50),
            CREATED_AT TIMESTAMP DEFAULT SYSTIMESTAMP,
            UPDATED_BY VARCHAR2(50),
            UPDATED_AT TIMESTAMP,
            POSTED_BY VARCHAR2(50),
            POSTED_AT TIMESTAMP,
            CONSTRAINT PK_{hdr} PRIMARY KEY (VOUCHER_NO)
        )
    """
    ddl_dtl = f"""
        CREATE TABLE {dtl} (
            VOUCHER_NO VARCHAR2(30) NOT NULL,
            LINE_NO NUMBER(10) NOT NULL,
            ACCOUNT_CODE VARCHAR2(20),
            DESCRIPTION VARCHAR2(500),
            AMOUNT NUMBER(18,2) DEFAULT 0,
            CONSTRAINT PK_{dtl} PRIMARY KEY (VOUCHER_NO, LINE_NO)
        )
    """
    with _get_connection() as conn:
        with conn.cursor() as cur:
            if not _table_exists(cur, hdr):
                cur.execute(ddl_hdr)
            if not _table_exists(cur, dtl):
                cur.execute(ddl_dtl)
        conn.commit()


def _next_voucher_no(cfg: Dict[str, Any], voucher_date: str) -> str:
    _ensure_tables(cfg)
    tag = (_parse_iso_date(voucher_date) or datetime.now().strftime('%Y-%m-%d')).replace('-', '')
    prefix = f"{cfg['prefix']}{tag}-"
    rows = _safe_rows(
        f"SELECT MAX(VOUCHER_NO) AS max_no FROM {cfg['hdr_table']} WHERE VOUCHER_NO LIKE :pfx",
        {'pfx': f'{prefix}%'},
    )
    max_no = str((rows[0].get('max_no') if rows else '') or '')
    seq = 1
    if '-' in max_no:
        tail = max_no.rsplit('-', 1)[-1]
        if tail.isdigit():
            seq = int(tail) + 1
    return f'{prefix}{seq:04d}'


def _default_cash_bank() -> str:
    accounts = get_all_chart_of_accounts() or []
    for acc in accounts:
        if not is_cash_bank_account(acc):
            continue
        name = str(acc.get('name') or '').upper()
        if 'PETTY CASH' in name or name == 'CASH ACCOUNT':
            return str(acc.get('code') or '')
    for acc in accounts:
        if is_cash_bank_account(acc):
            return str(acc.get('code') or '')
    return ''


def _default_bank_account(exclude_code: str = '') -> str:
    """Second cash/bank account for contra defaults (prefer bank over cash)."""
    exclude = str(exclude_code or '').strip()
    accounts = get_all_chart_of_accounts() or []
    candidates: List[str] = []
    for acc in accounts:
        if not is_cash_bank_account(acc):
            continue
        code = str(acc.get('code') or '').strip()
        if not code or code == exclude:
            continue
        candidates.append(code)
    for code in candidates:
        acc = next((a for a in accounts if str(a.get('code') or '').strip() == code), None)
        if acc and 'BANK' in str(acc.get('name') or '').upper():
            return code
    return candidates[0] if candidates else ''


def _parse_amount(raw: Any) -> float:
    try:
        return round(float(str(raw or '').replace(',', '').strip() or 0), 2)
    except Exception:
        return 0.0


def _parse_form(cfg: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[str]]:
    voucher_date = _parse_iso_date(request.form.get('voucher_date', '')) or datetime.now().strftime('%Y-%m-%d')
    voucher_no = (request.form.get('voucher_no') or '').strip() or _next_voucher_no(cfg, voucher_date)
    data = {
        'voucher_no': voucher_no[:30],
        'voucher_date': voucher_date,
        'cash_bank_account': (request.form.get('cash_bank_account') or '').strip()[:20],
        'reference_no': (request.form.get('reference_no') or '').strip()[:50],
        'narration': (request.form.get('narration') or '').strip()[:1000],
    }
    account_codes = request.form.getlist('ledger_account[]')
    descriptions = request.form.getlist('description[]')
    amounts = request.form.getlist('amount[]')
    lines: List[Dict[str, Any]] = []
    errors: List[str] = []
    is_contra = cfg['gl_source'] == 'CONTRA'
    gl_source = cfg['gl_source']
    by_code = chart_accounts_by_code()
    if not data['cash_bank_account']:
        errors.append('Select From Cash / Bank account.' if is_contra else 'Select Cash / Bank account.')
    else:
        cash_err = validate_tally_voucher_account(data['cash_bank_account'], 'cash_bank', by_code)
        if cash_err:
            errors.append(cash_err if not is_contra else f'From account: {cash_err}')
    line_role = 'cash_bank' if is_contra else ('receipt_line' if gl_source == 'RECEIPT' else 'payment_line')
    for idx in range(max(len(account_codes), len(amounts))):
        code = str(account_codes[idx] if idx < len(account_codes) else '').strip()
        desc = str(descriptions[idx] if idx < len(descriptions) else '').strip()[:500]
        amount = _parse_amount(amounts[idx] if idx < len(amounts) else 0)
        if not code and amount <= 0:
            continue
        if not code:
            errors.append(f'Line {idx + 1}: select a ledger account.' if not is_contra else f'Line {idx + 1}: select To Cash / Bank account.')
            continue
        if is_contra and code == data['cash_bank_account']:
            errors.append(f'Line {idx + 1}: From and To accounts must be different.')
            continue
        if amount <= 0:
            errors.append(f'Line {idx + 1}: enter amount greater than zero.')
            continue
        if not desc:
            errors.append(f'Line {idx + 1}: enter particulars.')
            continue
        acct_err = validate_tally_voucher_account(code, line_role, by_code)
        if acct_err:
            errors.append(f'Line {idx + 1}: {acct_err}')
            continue
        lines.append({
            'line_no': len(lines) + 1,
            'account_code': code,
            'description': desc,
            'amount': amount,
        })
    if not lines:
        errors.append('Add at least one ledger line with amount.')
    return data, lines, errors


def _get_voucher(cfg: Dict[str, Any], voucher_no: str) -> Optional[Dict[str, Any]]:
    vno = str(voucher_no or '').strip()
    if not vno:
        return None
    _ensure_tables(cfg)
    rows = _safe_rows(
        f"""
        SELECT VOUCHER_NO, VOUCHER_DATE, CASH_BANK_ACCOUNT, REFERENCE_NO, NARRATION,
               STATUS, GL_VOUCHER_NO, CREATED_BY, CREATED_AT, UPDATED_BY, UPDATED_AT,
               POSTED_BY, POSTED_AT
        FROM {cfg['hdr_table']}
        WHERE VOUCHER_NO = :vno
        """,
        {'vno': vno},
    )
    if not rows:
        return None
    header = rows[0]
    lines = _safe_rows(
        f"""
        SELECT LINE_NO, ACCOUNT_CODE, DESCRIPTION, AMOUNT
        FROM {cfg['dtl_table']}
        WHERE VOUCHER_NO = :vno
        ORDER BY LINE_NO
        """,
        {'vno': vno},
    )
    header['lines'] = lines or []
    return header


def _list_rows(cfg: Dict[str, Any], search: str = '', status: str = 'all', limit: int = 500) -> List[Dict[str, Any]]:
    _ensure_tables(cfg)
    q = (search or '').strip()
    st = (status or 'all').strip().upper()
    if st not in {'ALL', 'DRAFT', 'POSTED'}:
        st = 'ALL'
    limit = max(1, min(int(limit or 500), 2000))
    where_parts: List[str] = []
    params: Dict[str, Any] = {'max_rows': limit}
    if q:
        where_parts.append(
            "(UPPER(h.VOUCHER_NO) LIKE UPPER(:q) OR UPPER(NVL(h.REFERENCE_NO, '')) LIKE UPPER(:q) "
            "OR UPPER(NVL(h.NARRATION, '')) LIKE UPPER(:q) OR UPPER(NVL(h.GL_VOUCHER_NO, '')) LIKE UPPER(:q))"
        )
        params['q'] = f'%{q}%'
    if st != 'ALL':
        where_parts.append("UPPER(NVL(h.STATUS, 'DRAFT')) = :status")
        params['status'] = st
    where_sql = 'WHERE ' + ' AND '.join(where_parts) if where_parts else ''
    return _safe_rows(
        f"""
        SELECT *
        FROM (
            SELECT
                h.VOUCHER_NO AS voucher_no,
                h.VOUCHER_DATE AS voucher_date,
                h.CASH_BANK_ACCOUNT AS cash_bank_account,
                h.REFERENCE_NO AS reference_no,
                h.NARRATION AS narration,
                h.STATUS AS status,
                h.GL_VOUCHER_NO AS gl_voucher_no,
                h.CREATED_BY AS created_by,
                h.CREATED_AT AS created_at,
                h.POSTED_BY AS posted_by,
                h.POSTED_AT AS posted_at,
                NVL(SUM(d.AMOUNT), 0) AS total_amount,
                COUNT(d.LINE_NO) AS line_count
            FROM {cfg['hdr_table']} h
            LEFT JOIN {cfg['dtl_table']} d ON d.VOUCHER_NO = h.VOUCHER_NO
            {where_sql}
            GROUP BY h.VOUCHER_NO, h.VOUCHER_DATE, h.CASH_BANK_ACCOUNT, h.REFERENCE_NO,
                     h.NARRATION, h.STATUS, h.GL_VOUCHER_NO, h.CREATED_BY, h.CREATED_AT,
                     h.POSTED_BY, h.POSTED_AT
            ORDER BY h.VOUCHER_DATE DESC, h.VOUCHER_NO DESC
        )
        WHERE ROWNUM <= :max_rows
        """,
        params,
    ) or []


def _upsert(cur: Any, cfg: Dict[str, Any], data: Dict[str, Any], lines: List[Dict[str, Any]], status: str, user: str) -> None:
    vno = data['voucher_no']
    cur.execute(f"SELECT STATUS FROM {cfg['hdr_table']} WHERE VOUCHER_NO = :vno", {'vno': vno})
    existing = cur.fetchone()
    if existing and str(existing[0] or '').upper() == 'POSTED' and status != 'POSTED':
        raise ValueError('Posted voucher cannot be changed.')
    params = {
        'vno': vno,
        'vdate': data['voucher_date'],
        'cash': data['cash_bank_account'] or None,
        'ref': data['reference_no'] or None,
        'narr': data['narration'] or None,
        'status': status,
        'usr': (user or '')[:50] or None,
    }
    if existing:
        cur.execute(
            f"""
            UPDATE {cfg['hdr_table']}
               SET VOUCHER_DATE = TO_DATE(:vdate, 'YYYY-MM-DD'),
                   CASH_BANK_ACCOUNT = :cash,
                   REFERENCE_NO = :ref,
                   NARRATION = :narr,
                   STATUS = :status,
                   UPDATED_BY = :usr,
                   UPDATED_AT = SYSTIMESTAMP
             WHERE VOUCHER_NO = :vno
            """,
            params,
        )
    else:
        cur.execute(
            f"""
            INSERT INTO {cfg['hdr_table']}
                (VOUCHER_NO, VOUCHER_DATE, CASH_BANK_ACCOUNT, REFERENCE_NO, NARRATION,
                 STATUS, CREATED_BY, CREATED_AT, UPDATED_BY, UPDATED_AT)
            VALUES
                (:vno, TO_DATE(:vdate, 'YYYY-MM-DD'), :cash, :ref, :narr,
                 :status, :usr, SYSTIMESTAMP, :usr, SYSTIMESTAMP)
            """,
            params,
        )
    cur.execute(f"DELETE FROM {cfg['dtl_table']} WHERE VOUCHER_NO = :vno", {'vno': vno})
    for line in lines:
        cur.execute(
            f"""
            INSERT INTO {cfg['dtl_table']}
                (VOUCHER_NO, LINE_NO, ACCOUNT_CODE, DESCRIPTION, AMOUNT)
            VALUES (:vno, :lno, :acc, :descr, :amt)
            """,
            {
                'vno': vno,
                'lno': int(line['line_no']),
                'acc': line['account_code'],
                'descr': line.get('description') or None,
                'amt': line['amount'],
            },
        )


def _build_gl_lines(cfg: Dict[str, Any], data: Dict[str, Any], lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    total = round(sum(float(line['amount'] or 0) for line in lines), 2)
    cash = str(data.get('cash_bank_account') or '').strip()
    narration = data.get('narration') or data.get('voucher_no') or ''
    gl_source = cfg['gl_source']
    gl_lines: List[Dict[str, Any]] = []
    if gl_source == 'CONTRA':
        for line in lines:
            amount = float(line['amount'] or 0)
            gl_lines.append({
                'account_code': line['account_code'],
                'debit': amount,
                'credit': 0,
                'remarks': line.get('description') or narration,
            })
        if cash and total > 0:
            gl_lines.append({
                'account_code': cash,
                'debit': 0,
                'credit': total,
                'remarks': f"Contra transfer from {cash} — {data.get('voucher_no') or ''}".strip(),
            })
        return gl_lines
    is_receipt = gl_source == 'RECEIPT'
    for line in lines:
        amount = float(line['amount'] or 0)
        gl_lines.append({
            'account_code': line['account_code'],
            'debit': 0 if is_receipt else amount,
            'credit': amount if is_receipt else 0,
            'remarks': line.get('description') or narration,
        })
    if cash and total > 0:
        gl_lines.append({
            'account_code': cash,
            'debit': total if is_receipt else 0,
            'credit': 0 if is_receipt else total,
            'remarks': f"{cfg['title']} {data.get('voucher_no') or ''}".strip(),
        })
    return gl_lines


def _save_draft_voucher(cfg: Dict[str, Any], data: Dict[str, Any], lines: List[Dict[str, Any]], user: str) -> None:
    with _get_connection() as conn:
        try:
            with conn.cursor() as cur:
                _upsert(cur, cfg, data, lines, 'DRAFT', user)
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def _post_voucher(cfg: Dict[str, Any], data: Dict[str, Any], lines: List[Dict[str, Any]], user: str) -> str:
    """Save header/lines and post GL in one DB transaction (all commit or none)."""
    gl_lines = _build_gl_lines(cfg, data, lines)
    with _get_connection() as conn:
        try:
            with conn.cursor() as cur:
                _upsert(cur, cfg, data, lines, 'DRAFT', user)
                gl_voucher_no = create_gl_journal_entry(
                    voucher_date=data['voucher_date'],
                    reference_no=data['reference_no'] or data['voucher_no'],
                    narration=data['narration'] or f"{cfg['title']} {data['voucher_no']}",
                    lines=gl_lines,
                    created_by=user,
                    source=cfg['gl_source'],
                    conn=conn,
                    commit=False,
                )
                cur.execute(
                    f"""
                    UPDATE {cfg['hdr_table']}
                       SET STATUS = 'POSTED',
                           GL_VOUCHER_NO = :glv,
                           POSTED_BY = :usr,
                           POSTED_AT = SYSTIMESTAMP,
                           UPDATED_BY = :usr,
                           UPDATED_AT = SYSTIMESTAMP
                     WHERE VOUCHER_NO = :vno
                    """,
                    {'glv': gl_voucher_no, 'usr': user[:50] or None, 'vno': data['voucher_no']},
                )
            conn.commit()
            return gl_voucher_no
        except Exception:
            conn.rollback()
            raise


def _tally_voucher_date_str(raw: Any) -> str:
    if raw is None:
        return ''
    if hasattr(raw, 'strftime'):
        try:
            return raw.strftime('%Y-%m-%d')
        except Exception:
            pass
    return str(raw)[:10]


def _tally_build_pdf_payload(cfg: Dict[str, Any], voucher: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    accounts = get_all_chart_of_accounts() or []
    by_code = {str(a.get('code') or '').strip(): str(a.get('name') or '').strip() for a in accounts}
    norm_lines: List[Dict[str, Any]] = []
    for line in voucher.get('lines') or []:
        code = str(line.get('account_code') or '').strip()
        try:
            amount = round(float(line.get('amount') or 0), 2)
        except Exception:
            amount = 0.0
        if not code and amount <= 0:
            continue
        norm_lines.append({
            'account_code': code,
            'description': str(line.get('description') or '').strip(),
            'amount': amount,
        })
    data = {
        'voucher_no': str(voucher.get('voucher_no') or '').strip(),
        'voucher_date': _tally_voucher_date_str(voucher.get('voucher_date')),
        'cash_bank_account': str(voucher.get('cash_bank_account') or '').strip(),
        'reference_no': str(voucher.get('reference_no') or '').strip(),
        'narration': str(voucher.get('narration') or '').strip(),
        'gl_voucher_no': str(voucher.get('gl_voucher_no') or '').strip(),
    }
    gl_lines = _build_gl_lines(cfg, data, norm_lines)
    pdf_lines: List[Dict[str, Any]] = []
    for idx, ln in enumerate(gl_lines, start=1):
        code = str(ln.get('account_code') or '').strip()
        pdf_lines.append({
            'line_no': idx,
            'account_code': code,
            'account_name': by_code.get(code, ''),
            'debit': round(float(ln.get('debit') or 0), 2),
            'credit': round(float(ln.get('credit') or 0), 2),
            'remarks': str(ln.get('remarks') or '').strip(),
        })
    total = round(sum(float(ln.get('debit') or 0) for ln in gl_lines), 2)
    payload = dict(data)
    payload['source'] = cfg['gl_source']
    payload['lines'] = pdf_lines
    payload['total_debit'] = total
    payload['total_credit'] = total
    cash = data['cash_bank_account']
    cash_name = by_code.get(cash, '')
    party_label = f'{cash} — {cash_name}' if cash and cash_name else (cash or '—')
    return payload, party_label


def _tally_voucher_pdf(kind: str):
    if not session.get('user'):
        return Response('Not authenticated', status=401, mimetype='text/plain')
    if not _apply_db():
        return Response('Database/location not assigned.', status=403, mimetype='text/plain')
    cfg = _kind_cfg(kind)
    voucher_no = (request.args.get('voucher_no') or '').strip()
    if not voucher_no:
        return Response('voucher_no is required.', status=400, mimetype='text/plain')
    voucher = _get_voucher(cfg, voucher_no)
    if not voucher:
        return Response(f"{cfg['title']} not found.", status=404, mimetype='text/plain')
    if str(voucher.get('status') or '').strip().upper() != 'POSTED':
        return Response(f"{cfg['title']} PDF is available after posting.", status=400, mimetype='text/plain')
    from addons.accounts.controllers.routes import (
        _build_petty_cash_style_voucher_pdf,
        _pdf_date_mdy,
        _voucher_account_label,
        _voucher_account_summary_from_lines,
        _voucher_item_description,
        _voucher_party_from_lines,
    )

    accounts = get_all_chart_of_accounts() or []
    by_code = {str(a.get('code') or '').strip(): str(a.get('name') or '').strip() for a in accounts}
    vdate = _tally_voucher_date_str(voucher.get('voucher_date'))
    display_date = _pdf_date_mdy(vdate)
    item_lines: List[Dict[str, Any]] = []
    total = 0.0
    for line in voucher.get('lines') or []:
        try:
            amt = round(float(line.get('amount') or 0), 2)
        except Exception:
            amt = 0.0
        if amt <= 0:
            continue
        total += amt
        item_lines.append({
            'date': display_date,
            'description': _voucher_item_description(line, by_code),
            'amount': amt,
        })
    cash_code = str(voucher.get('cash_bank_account') or '').strip()
    line_accounts = _voucher_account_summary_from_lines(voucher.get('lines') or [], by_code)
    if kind == 'receipt':
        debit_label = 'Debit Account'
        debit_name = _voucher_account_label(cash_code, by_code)
        credit_label = 'Credit Account'
        credit_name = line_accounts
    elif kind == 'payment':
        debit_label = 'Debit Account'
        debit_name = line_accounts
        credit_label = 'Credit Account'
        credit_name = _voucher_account_label(cash_code, by_code)
    else:
        debit_label = 'Debit Account'
        debit_name = line_accounts
        credit_label = 'Credit Account'
        credit_name = _voucher_account_label(cash_code, by_code)
    pdf_bytes = _build_petty_cash_style_voucher_pdf(
        voucher_no=str(voucher.get('voucher_no') or ''),
        voucher_date=vdate,
        voucher_title=str(cfg.get('title') or 'Voucher'),
        party_field_label='Particulars',
        party_name=_voucher_party_from_lines(voucher.get('lines') or [], str(voucher.get('narration') or '')),
        item_lines=item_lines,
        total_amount=total,
        created_by=str(voucher.get('created_by') or ''),
        verified_by=str(voucher.get('posted_by') or ''),
        approved_by='',
        debit_account_label=debit_label,
        debit_account_name=debit_name,
        credit_account_label=credit_label,
        credit_account_name=credit_name,
        reference_no=str(voucher.get('reference_no') or ''),
    )
    if not pdf_bytes:
        return Response('PDF generation failed (reportlab not available).', status=500, mimetype='text/plain')
    safe_v = ''.join((c for c in voucher_no if c.isalnum() or c in ('-', '_')))[:44] or kind
    filename = f"{cfg['prefix'].lower()}_{safe_v}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return Response(pdf_bytes, mimetype='application/pdf', headers={'Content-Disposition': f'inline; filename="{filename}"'})


def _tally_voucher_list(kind: str):
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _apply_db():
        return redirect(url_for('dashboard.dashboard'))
    cfg = _kind_cfg(kind)
    search_term = (request.args.get('q') or '').strip()
    status_filter = (request.args.get('status') or 'all').strip().lower()
    rows = _list_rows(cfg, search=search_term, status=status_filter)
    return render_template(
        'accounts/tally_voucher_list.html',
        rows=rows,
        search_term=search_term,
        status_filter=status_filter,
        voucher_kind=kind,
        voucher_cfg=cfg,
    )


def _tally_voucher_form(kind: str):
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _apply_db():
        return redirect(url_for('dashboard.dashboard'))
    cfg = _kind_cfg(kind)
    if request.method == 'GET' and not (request.args.get('voucher_no') or '').strip() and (request.args.get('new') or '').strip() != '1':
        return redirect(url_for(cfg['list_endpoint']))
    ensure_gl_tables()
    _ensure_tables(cfg)
    user = str(session.get('user') or '')
    form_data: Optional[Dict[str, Any]] = None
    form_lines: Optional[List[Dict[str, Any]]] = None
    if request.method == 'POST':
        if not _try_acquire_lock(cfg['lock_key']):
            flash(f"{cfg['title']} is already being saved or posted. Please wait.", 'error')
            existing_vno = (request.form.get('voucher_no') or '').strip()
            if existing_vno:
                return redirect(url_for(cfg['form_endpoint'], voucher_no=existing_vno))
            return redirect(url_for(cfg['form_endpoint'], new=1))
        try:
            submitted_nonce = (request.form.get('save_nonce') or '').strip()
            if not reject_invalid_form_save_nonce(submitted_nonce):
                flash(
                    'Duplicate or expired submit token. The page was refreshed — try Save or Accept again.',
                    'error',
                )
                existing_vno = (request.form.get('voucher_no') or '').strip()
                if existing_vno:
                    return redirect(url_for(cfg['form_endpoint'], voucher_no=existing_vno))
                return redirect(url_for(cfg['form_endpoint'], new=1))
            action = (request.form.get('action') or 'save').strip().lower()
            data, lines, errors = _parse_form(cfg)
            if not errors:
                existing_hdr = _get_voucher(cfg, data['voucher_no'])
                status_u = str((existing_hdr or {}).get('status') or 'DRAFT').upper()
                if status_u == 'POSTED':
                    if action == 'post':
                        errors.append('This voucher is already posted.')
                    else:
                        errors.append('Posted voucher cannot be changed.')
            if errors:
                for msg in errors:
                    flash(msg, 'error')
                form_data = data
                form_data['status'] = 'DRAFT'
                form_lines = lines
            else:
                if not commit_form_save_nonce(submitted_nonce):
                    issue_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY)
                    flash(
                        'Duplicate or expired submit token. The page was refreshed — try Save or Accept again.',
                        'error',
                    )
                    existing_vno = (request.form.get('voucher_no') or '').strip()
                    if existing_vno:
                        return redirect(url_for(cfg['form_endpoint'], voucher_no=existing_vno))
                    return redirect(url_for(cfg['form_endpoint'], new=1))
                try:
                    if action == 'post':
                        gl_voucher_no = _post_voucher(cfg, data, lines, user)
                        flash(f"{cfg['title']} posted. GL Voucher No: {gl_voucher_no}", 'success')
                        return redirect(url_for(cfg['list_endpoint'], **{cfg['pdf_open_param']: data['voucher_no']}))
                    _save_draft_voucher(cfg, data, lines, user)
                    flash(f"{cfg['title']} saved as draft: {data['voucher_no']}", 'success')
                    return redirect(url_for(cfg['list_endpoint']))
                except Exception as exc:
                    issue_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY)
                    flash(str(exc), 'error')
                    form_data = data
                    form_data['status'] = 'DRAFT'
                    form_lines = lines
        finally:
            _release_lock(cfg['lock_key'])

    accounts = get_all_chart_of_accounts() or []
    # Contra: From/To pickers and labels — cash & bank ledgers only
    if kind == 'contra':
        accounts = [a for a in accounts if is_cash_bank_account(a)]
    active_accounts = [
        {
            'code': str(a.get('code') or '').strip(),
            'name': str(a.get('name') or '').strip(),
            'is_postable': bool(a.get('is_postable')),
            'status': str(a.get('status') or 'ACTIVE').strip().upper(),
        }
        for a in accounts
        if str(a.get('code') or '').strip()
    ]
    voucher_no = (request.args.get('voucher_no') or '').strip()
    loaded = _get_voucher(cfg, voucher_no) if voucher_no else None
    if form_data is None:
        if loaded:
            form_data = loaded
            form_lines = loaded.get('lines') or []
        else:
            today = datetime.now().strftime('%Y-%m-%d')
            default_from = _default_cash_bank()
            form_data = {
                'voucher_no': _next_voucher_no(cfg, today),
                'voucher_date': today,
                'cash_bank_account': default_from,
                'reference_no': '',
                'narration': '',
                'status': 'DRAFT',
                'gl_voucher_no': '',
                'created_by': user,
                'created_at': '',
                'posted_by': '',
                'posted_at': '',
            }
            if kind == 'contra':
                to_code = _default_bank_account(default_from)
                form_lines = [{'account_code': to_code, 'description': '', 'amount': ''}] if to_code else []
            else:
                form_lines = []
    try:
        from global_lookup import resolve_lookup_label
        cash_kind = cfg.get('cash_lookup_kind') or 'cash_bank_strict'
        form_data['cash_bank_label'] = resolve_lookup_label(
            cash_kind, str(form_data.get('cash_bank_account') or '')
        )
    except Exception:
        form_data.setdefault('cash_bank_label', '')

    return render_template(
        'accounts/tally_voucher_form.html',
        voucher=form_data,
        lines=form_lines or [],
        accounts=active_accounts,
        voucher_kind=kind,
        voucher_cfg=cfg,
        today=datetime.now().strftime('%Y-%m-%d'),
    )


def register(bp) -> None:
    @bp.route('/accounts/receipt-voucher/list')
    def receipt_voucher_list():
        return _tally_voucher_list('receipt')

    @bp.route('/accounts/receipt-voucher', methods=['GET', 'POST'])
    def receipt_voucher():
        return _tally_voucher_form('receipt')

    @bp.route('/accounts/payment-voucher/list')
    def payment_voucher_list():
        return _tally_voucher_list('payment')

    @bp.route('/accounts/payment-voucher', methods=['GET', 'POST'])
    def payment_voucher():
        return _tally_voucher_form('payment')

    @bp.route('/accounts/contra-voucher/list')
    def contra_voucher_list():
        return _tally_voucher_list('contra')

    @bp.route('/accounts/contra-voucher', methods=['GET', 'POST'])
    def contra_voucher():
        return _tally_voucher_form('contra')

    @bp.route('/accounts/receipt-voucher/pdf', methods=['GET'])
    def receipt_voucher_pdf():
        return _tally_voucher_pdf('receipt')

    @bp.route('/accounts/payment-voucher/pdf', methods=['GET'])
    def payment_voucher_pdf():
        return _tally_voucher_pdf('payment')

    @bp.route('/accounts/contra-voucher/pdf', methods=['GET'])
    def contra_voucher_pdf():
        return _tally_voucher_pdf('contra')
