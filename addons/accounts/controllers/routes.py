"""Accounts module: Chart of Accounts (uses model from Accountsmanagement)."""
from pathlib import Path
import csv
import io
import json
import logging
import os
import secrets
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from nexa_http import Blueprint, Response, flash, jsonify, redirect, render_template, request, session, url_for
from werkzeug.utils import secure_filename
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import inch
    from reportlab.platypus import Image as RLImage
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, KeepTogether
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    REPORTLAB_AVAILABLE = True
except ImportError:
    RLImage = None
    REPORTLAB_AVAILABLE = False
from db import ACCOUNT_TYPES, COA_CODE_MAX_LEN, DEFAULT_PARTY_ACCOUNTS, create_gl_journal_entry, update_gl_journal_entry, ensure_ap_payment_tables, ensure_ar_payment_tables, ensure_default_party_accounts, ensure_gl_tables, get_account_ledger, get_supplier_ledger, get_customer_ledger, get_supplier_list, get_customers_for_journal_party_select, get_supplier_master_by_code, get_customer_master_by_code, get_gl_voucher_detail, get_gl_voucher_reversal_no, reverse_gl_journal_voucher, get_accounts_payable_summary, get_accounts_receivable_summary, get_ap_payment_allocations_by_payment_voucher, get_ar_payment_allocations_by_payment_voucher, get_balance_sheet_report, get_cash_flow_report, get_profit_and_loss_comparative, get_supplier_open_invoices_for_payment, get_customer_open_invoices_for_payment, get_supplier_by_code, get_gl_account_closing_balances, get_gl_party_balances_for_journal, get_trial_balance_report, list_gl_journal_entries, list_gl_journal_sources, list_gl_dimension_values, normalize_gl_dimension_type, parse_open_document_payment_allocations, save_supplier_payment_allocations, save_customer_payment_allocations, ap_receipt_voucher_totals, ar_receipt_voucher_totals, get_ar_discount_allowed_account, get_ap_discount_received_account, get_chart_of_account_by_code, _norm_gl_account_code, ensure_pdc_table, get_pdc_list, get_pdc_by_id, get_pdc_summary, save_pdc, update_pdc_status, delete_pdc, get_pdc_audit_log, is_cash_bank_family_account, get_tenant_by_id, get_main_account_ledger_data, get_all_chart_of_accounts, chart_of_account_code_exists, suggest_next_chart_of_account_code, suggest_next_chart_of_account_code_after, normalize_coa_code, _sync_chart_of_accounts_sequence, _detect_column, _detect_table, _get_connection, _get_table_columns, _safe_rows
from models.chart_of_accounts import ChartOfAccounts
from save_nonce import GLOBAL_SAVE_NONCE_SESSION_KEY, get_or_issue_global_save_nonce, issue_save_nonce, verify_consume_save_nonce
_ADDON_ROOT = Path(__file__).resolve().parents[1]
bp = Blueprint('accounts', __name__, template_folder=str(_ADDON_ROOT / 'views' / 'templates'))
_COA_CREATE_ONCE = '_coa_create_once'
_LOG_COA = logging.getLogger('nexa.coa')


def _coa_oracle_is_pk_violation(err: str) -> bool:
    low = (err or '').lower()
    return 'ora-00001' in low and ('chart_of_accounts_pk' in low or '_pk)' in low or 'primary key' in low)


def _coa_oracle_is_code_violation(err: str) -> bool:
    low = (err or '').lower()
    if 'ora-00001' not in low and 'unique constraint' not in low:
        return False
    if _coa_oracle_is_pk_violation(err):
        return False
    return 'code' in low or 'uk_' in low or 'unique' in low


def _coa_log_api_fail(endpoint: str, status: int, error: str, **ctx: Any) -> None:
    """Log chart API failures to terminal (uvicorn console) and app log file."""
    parts = [f'[COA {endpoint}] HTTP {status}: {error}']
    for key, val in ctx.items():
        if val is not None and val != '':
            parts.append(f'{key}={val!r}')
    msg = ' | '.join(parts)
    print(msg, flush=True)
    _LOG_COA.warning(msg)
_CUSTOMER_OPENING_POST_SESSION_LOCK_UNTIL = '_customer_opening_post_session_lock_until'
_SUPPLIER_OPENING_POST_SESSION_LOCK_UNTIL = '_supplier_opening_post_session_lock_until'
_CPV_SUBMIT_SESSION_LOCK_UNTIL = '_cpv_submit_session_lock_until'
_JE_REVERSE_SESSION_LOCK_UNTIL = '_je_reverse_session_lock_until'
_JE_SUBMIT_SESSION_LOCK_UNTIL = '_je_submit_session_lock_until'
_CPV_HDR_TABLE = 'CASH_PAYMENT_VOUCHER_HDR'
_CPV_DTL_TABLE = 'CASH_PAYMENT_VOUCHER_DTL'
_JE_DRAFT_TABLE = 'JOURNAL_ENTRY_DRAFT'
_ACCOUNTS_CACHE_TTL_SECONDS = 300.0
_ACCOUNTS_ROUTE_CACHE: Dict[Any, Any] = {}

def _accounts_cache_key(name: str, *parts: Any) -> Any:
    tenant = ''
    try:
        tenant = str(session.get('tenant_id') or '').strip()
    except Exception:
        tenant = ''
    return (tenant, name) + tuple(parts)

def _accounts_cache_get(key: Any) -> Any:
    cached = _ACCOUNTS_ROUTE_CACHE.get(key)
    if not cached:
        return None
    ts, value = cached
    if (time.time() - ts) > _ACCOUNTS_CACHE_TTL_SECONDS:
        _ACCOUNTS_ROUTE_CACHE.pop(key, None)
        return None
    return value

def _accounts_cache_set(key: Any, value: Any) -> Any:
    _ACCOUNTS_ROUTE_CACHE[key] = (time.time(), value)
    if len(_ACCOUNTS_ROUTE_CACHE) > 100:
        for k in list(_ACCOUNTS_ROUTE_CACHE.keys())[:50]:
            _ACCOUNTS_ROUTE_CACHE.pop(k, None)
    return value

def _coa_issue_create_once_token() -> str:
    t = secrets.token_urlsafe(24)
    session[_COA_CREATE_ONCE] = t
    session.modified = True
    return t

def _coa_verify_create_once(submitted: str | None) -> bool:
    """Check create-once token without consuming (allows retry after validation/duplicate errors)."""
    sub = (submitted or '').strip()
    stored = session.get(_COA_CREATE_ONCE)
    return bool(stored and sub and sub == stored)


def _coa_consume_create_once() -> None:
    session.pop(_COA_CREATE_ONCE, None)
    session.modified = True


def _coa_verify_and_consume_create_once(submitted: str | None) -> bool:
    if not _coa_verify_create_once(submitted):
        return False
    _coa_consume_create_once()
    return True


def _coa_resolve_create_code(
    code: str,
    account_type: str,
    parent_id: Optional[int],
) -> Tuple[str, Optional[str]]:
    """Return code to insert; auto-bump to next free code when *code* is already used."""
    resolved = normalize_coa_code(code)
    if not resolved:
        return '', None
    if not chart_of_account_code_exists(resolved):
        return resolved, None
    suggested = suggest_next_chart_of_account_code_after(resolved, account_type, parent_id)
    bumped = normalize_coa_code(suggested)
    if bumped and bumped != resolved and not chart_of_account_code_exists(bumped):
        return bumped, resolved
    return resolved, resolved

def _customer_opening_try_acquire_session_lock(lock_seconds: float=120.0) -> bool:
    """Best-effort session lock so one customer opening post runs at a time per browser session."""
    now = time.time()
    raw = session.get(_CUSTOMER_OPENING_POST_SESSION_LOCK_UNTIL)
    try:
        until = float(raw)
        if until > now:
            return False
    except (TypeError, ValueError):
        pass
    session[_CUSTOMER_OPENING_POST_SESSION_LOCK_UNTIL] = now + float(lock_seconds)
    session.modified = True
    return True

def _customer_opening_release_session_lock() -> None:
    session.pop(_CUSTOMER_OPENING_POST_SESSION_LOCK_UNTIL, None)
    session.modified = True

def _supplier_opening_try_acquire_session_lock(lock_seconds: float=120.0) -> bool:
    now = time.time()
    raw = session.get(_SUPPLIER_OPENING_POST_SESSION_LOCK_UNTIL)
    try:
        until = float(raw)
        if until > now:
            return False
    except (TypeError, ValueError):
        pass
    session[_SUPPLIER_OPENING_POST_SESSION_LOCK_UNTIL] = now + float(lock_seconds)
    session.modified = True
    return True

def _supplier_opening_release_session_lock() -> None:
    session.pop(_SUPPLIER_OPENING_POST_SESSION_LOCK_UNTIL, None)
    session.modified = True

def _cpv_try_acquire_session_lock(lock_seconds: float=90.0) -> bool:
    """Best-effort lock to prevent duplicate CPV save/post requests per browser session."""
    now = time.time()
    raw = session.get(_CPV_SUBMIT_SESSION_LOCK_UNTIL)
    try:
        until = float(raw)
        if until > now:
            return False
    except (TypeError, ValueError):
        pass
    session[_CPV_SUBMIT_SESSION_LOCK_UNTIL] = now + float(lock_seconds)
    session.modified = True
    return True

def _cpv_release_session_lock() -> None:
    session.pop(_CPV_SUBMIT_SESSION_LOCK_UNTIL, None)
    session.modified = True

def _je_reverse_try_acquire_session_lock(lock_seconds: float = 90.0) -> bool:
    """Best-effort lock to prevent duplicate journal reversal posts per browser session."""
    now = time.time()
    raw = session.get(_JE_REVERSE_SESSION_LOCK_UNTIL)
    try:
        until = float(raw)
        if until > now:
            return False
    except (TypeError, ValueError):
        pass
    session[_JE_REVERSE_SESSION_LOCK_UNTIL] = now + float(lock_seconds)
    session.modified = True
    return True

def _je_reverse_release_session_lock() -> None:
    session.pop(_JE_REVERSE_SESSION_LOCK_UNTIL, None)
    session.modified = True

def _je_voucher_can_reverse(detail: Optional[Dict[str, Any]]) -> bool:
    """Only Direct JV (MANUAL) and Cash Payment Voucher (CPV) may be reversed from GL."""
    if not detail or not detail.get('lines'):
        return False
    src = str(detail.get('source') or '').strip().upper()
    if src == 'JE_REV' or src.endswith('_REV'):
        return False
    if src not in ('MANUAL', 'CPV'):
        return False
    if get_gl_voucher_reversal_no(str(detail.get('voucher_no') or '')):
        return False
    return len(detail.get('lines') or []) >= 2

def _je_voucher_can_edit(detail: Optional[Dict[str, Any]]) -> bool:
    if not detail or not detail.get('lines'):
        return False
    src = str(detail.get('source') or '').strip().upper()
    if src != 'MANUAL':
        return False
    if src == 'JE_REV' or src.endswith('_REV'):
        return False
    if get_gl_voucher_reversal_no(str(detail.get('voucher_no') or '')):
        return False
    return len(detail.get('lines') or []) >= 2


def _accounts_session_is_admin() -> bool:
    """True for privileged admin usernames / admin roles (period-closing admin gate)."""
    try:
        from addons.accounts.period_closing_db import is_period_closing_admin
        from db import get_user_role_id
        username = str(session.get('user') or '').strip()
        role_id = session.get('role_id')
        if role_id is None and username:
            try:
                role_id = get_user_role_id(username)
            except Exception:
                role_id = None
        return bool(is_period_closing_admin(username, role_id))
    except Exception:
        return str(session.get('user') or '').strip().lower() in ('admin', 'super')


def _change_gl_voucher_posting_date(voucher_no: str, new_date: str) -> Tuple[bool, Optional[str]]:
    """Update GL_VOUCHER_HDR.VOUCHER_DATE for a posted voucher. Returns (ok, error)."""
    vno = str(voucher_no or '').strip()
    nd = _parse_iso_date(new_date or '')
    if not vno:
        return (False, 'Voucher number is required.')
    if not nd:
        return (False, 'New posting date must be YYYY-MM-DD.')
    detail = get_gl_voucher_detail(vno)
    if not detail:
        return (False, 'Voucher not found.')
    old_pd = str(detail.get('voucher_date') or '')[:10]
    old_pd = _parse_iso_date(old_pd) or old_pd
    if old_pd and old_pd == nd:
        return (True, None)
    # Closed-period guards (new date must be open; do not re-date docs sitting in a closed period).
    for label, d in (('new posting date', nd), ('current posting date', old_pd)):
        if not d:
            continue
        msg = _accounts_period_closed_error(d)
        if msg:
            return (False, f'Cannot change date ({label}): {msg}')
    try:
        ensure_gl_tables()
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE GL_VOUCHER_HDR
                       SET VOUCHER_DATE = TO_DATE(:nd, 'YYYY-MM-DD')
                     WHERE VOUCHER_NO = :vno
                    """,
                    {'nd': nd, 'vno': vno},
                )
                if int(cur.rowcount or 0) <= 0:
                    return (False, 'Voucher not found or date was not updated.')
            conn.commit()
    except Exception as exc:
        return (False, f'Could not change posting date: {exc}')
    return (True, None)

def _je_try_acquire_submit_session_lock(lock_seconds: float = 90.0) -> bool:
    now = time.time()
    raw = session.get(_JE_SUBMIT_SESSION_LOCK_UNTIL)
    try:
        until = float(raw)
        if until > now:
            return False
    except (TypeError, ValueError):
        pass
    session[_JE_SUBMIT_SESSION_LOCK_UNTIL] = now + float(lock_seconds)
    session.modified = True
    return True

def _je_release_submit_session_lock() -> None:
    session.pop(_JE_SUBMIT_SESSION_LOCK_UNTIL, None)
    session.modified = True

def _je_gl_detail_to_form_lines(detail: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for ln in detail.get('lines') or []:
        if not isinstance(ln, dict):
            continue
        ac = str(ln.get('account_code') or '').strip()
        name = str(ln.get('account_name') or '').strip()
        if name in ('', '—'):
            name = ''
        display = f'{ac} - {name}' if ac and name else ac
        pt = str(ln.get('party_type') or '').strip()
        pc = str(ln.get('party_code') or '').strip()
        if pt in ('', '—'):
            pt = ''
        if pc in ('', '—'):
            pc = ''
        cc = str(ln.get('cost_center') or '').strip()
        dp = str(ln.get('department') or '').strip()
        pj = str(ln.get('project') or '').strip()
        out.append({
            'account_code': ac,
            'account_display': display,
            'debit': ln.get('debit') or 0,
            'credit': ln.get('credit') or 0,
            'remarks': str(ln.get('remarks') or '').replace('—', '').strip(),
            'party_type': pt,
            'party_code': pc,
            'cost_center': cc if cc not in ('', '—') else '',
            'department': dp if dp not in ('', '—') else '',
            'project': pj if pj not in ('', '—') else '',
        })
    return out

def _apply_db() -> bool:
    """Single database: always allow."""
    return True

def _cached_cash_bank_accounts() -> List[Dict[str, Any]]:
    key = _accounts_cache_key('cash_bank_accounts')
    cached = _accounts_cache_get(key)
    if cached is not None:
        return cached
    rows = _safe_rows(
        """
        SELECT
            a.ACCOUNT_ID AS account_id,
            a.CODE AS code,
            a.NAME AS name,
            a.TYPE AS type,
            a.PARENT_ID AS parent_id,
            a.IS_POSTABLE AS is_postable,
            a.CURRENCY AS currency,
            a.STATUS AS status,
            a.LOCATIONCODE AS locationcode,
            p.CODE AS parent_code,
            p.NAME AS parent_name
        FROM CHART_OF_ACCOUNTS a
        LEFT JOIN CHART_OF_ACCOUNTS p ON p.ACCOUNT_ID = a.PARENT_ID
        WHERE UPPER(NVL(a.TYPE, '')) = 'ASSET'
          AND NVL(a.IS_POSTABLE, 0) = 1
          AND UPPER(NVL(a.STATUS, 'ACTIVE')) = 'ACTIVE'
          AND (
                UPPER(NVL(p.NAME, '')) LIKE '%CASH%'
             OR UPPER(NVL(p.NAME, '')) LIKE '%BANK%'
             OR UPPER(NVL(a.NAME, '')) LIKE '%CASH%'
             OR UPPER(NVL(a.NAME, '')) LIKE '%BANK%'
             OR UPPER(NVL(a.NAME, '')) LIKE '%CARD CLEARING%'
          )
        ORDER BY a.CODE
        """,
        {},
    )
    cash_bank_accounts = list(rows or [])
    cash_bank_accounts.sort(key=lambda x: str(x.get('code') or ''))
    return _accounts_cache_set(key, cash_bank_accounts)

def _coa_exclude_ids_for_parent_picker(all_rows: List[Dict[str, Any]], edit_account_id: Optional[int]) -> set:
    """When editing, exclude this account and all descendants to avoid a parent/child cycle."""
    if edit_account_id is None:
        return set()
    from collections import defaultdict
    children: Dict[int, List[int]] = defaultdict(list)
    for a in all_rows or []:
        aid, p = (a.get('account_id'), a.get('parent_id'))
        if aid is None or p is None:
            continue
        try:
            children[int(p)].append(int(aid))
        except (TypeError, ValueError):
            continue
    ex: set = {int(edit_account_id)}
    stack = [int(edit_account_id)]
    while stack:
        k = stack.pop()
        for c in children.get(k, []):
            if c not in ex:
                ex.add(c)
                stack.append(c)
    return ex

def _flatten_coa_tree_for_parent_select(nodes: List[Dict[str, Any]], excluded: set, depth: int=0, out: Optional[List[Dict[str, Any]]]=None) -> List[Dict[str, Any]]:
    """Indent labels to reflect hierarchy; used by Chart of Accounts create/edit form."""
    if out is None:
        out = []
    for n in sorted(nodes, key=lambda x: (str(x.get('code') or ''), str(x.get('name') or ''))):
        aid = n.get('account_id')
        if aid is None:
            continue
        try:
            ai = int(aid)
        except (TypeError, ValueError):
            continue
        if ai in excluded:
            continue
        code = (n.get('code') or '').strip()
        name = (n.get('name') or '').strip()
        prefix = '·   ' * depth
        out.append({'account_id': ai, 'label': f'{prefix}{code} – {name}' if prefix else f'{code} – {name}'})
        ch = n.get('children') or []
        if ch:
            _flatten_coa_tree_for_parent_select(ch, excluded, depth + 1, out)
    return out

def _parse_iso_date(raw: str) -> str:
    s = (raw or '').strip()
    if not s:
        return ''
    try:
        return datetime.strptime(s[:10], '%Y-%m-%d').strftime('%Y-%m-%d')
    except Exception:
        return ''


def _accounts_closed_period_context(preferred_date: Optional[str] = None) -> Dict[str, Any]:
    """Closed periods + suggested open voucher/payment date for AR/AP/JE forms."""
    today = datetime.now().strftime('%Y-%m-%d')
    preferred = _parse_iso_date(preferred_date or '') or today
    try:
        from addons.accounts.period_closing_db import list_closed_periods, resolve_open_voucher_date
        closed = list_closed_periods()
        open_date = resolve_open_voucher_date(preferred)
        return {
            'closed_periods': closed,
            'payment_date': open_date,
            'default_voucher_date': open_date,
        }
    except Exception:
        return {
            'closed_periods': [],
            'payment_date': preferred,
            'default_voucher_date': preferred,
        }


def _accounts_period_closed_error(voucher_date: Optional[str]) -> str:
    """Return closed-period error message, or empty string if open/unknown."""
    try:
        from addons.accounts.period_closing_db import is_period_closed_for_date
        return str(is_period_closed_for_date(voucher_date) or '').strip()
    except Exception:
        return ''


_MAX_CUSTOMER_OPENING_CSV = 1024 * 1024

def _customer_opening_account_options() -> List[Dict[str, Any]]:
    rows = get_all_chart_of_accounts() or []
    return sorted([r for r in rows if str(r.get('code') or '').strip()], key=lambda r: str(r.get('code') or '').upper())

def _customer_opening_default_balance_account(accounts: List[Dict[str, Any]]) -> str:
    """Default opening outstanding credit side; do not default to sales revenue."""
    for preferred in ('3200', '3100', '3000'):
        for acc in accounts or []:
            if str(acc.get('code') or '').strip() == preferred:
                return preferred
    for acc in accounts or []:
        if str(acc.get('type') or '').strip().upper() == 'EQUITY' and str(acc.get('code') or '').strip():
            return str(acc.get('code') or '').strip()
    return ''

def _customer_opening_customer_options() -> List[Dict[str, Any]]:
    try:
        return get_customers_for_journal_party_select(limit=20000) or []
    except Exception:
        return []

def _customer_opening_norm_amount(v: Any) -> float:
    s = str(v or '').strip().replace(',', '')
    if not s:
        return 0.0
    try:
        return round(float(s), 2)
    except Exception:
        return 0.0

def _customer_opening_normalize_row(row: Dict[str, Any], rowno: int) -> Dict[str, Any]:

    def pick(*keys: str) -> str:
        for k in keys:
            v = row.get(k)
            if v is not None and str(v).strip():
                return str(v).strip()
        return ''
    return {'rowno': rowno, 'customercode': pick('customercode', 'customer_code', 'cust_code', 'customer'), 'customername': pick('customername', 'customer_name', 'cust_name', 'name'), 'invoiceno': pick('invoiceno', 'invoice_no', 'billno', 'bill_no'), 'invoicedate': _parse_iso_date(pick('invoicedate', 'invoice_date', 'billdate', 'bill_date')), 'invoiceamount': _customer_opening_norm_amount(pick('invoiceamount', 'invoice_amount', 'billamount', 'bill_amount', 'amount')), 'remarks': pick('narration', 'narration_remarks', 'remarks', 'remark', 'description')}

def _customer_opening_parse_csv(data: bytes) -> Tuple[List[Dict[str, Any]], List[str]]:
    try:
        text = data.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = data.decode('latin1', errors='replace')
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return ([], ['CSV header row is missing.'])
    out: List[Dict[str, Any]] = []
    for rowno, raw in enumerate(reader, start=2):
        normalized = {str(k or '').strip().lower().replace(' ', '_').replace('/', '_'): v for k, v in (raw or {}).items()}
        if not any((str(v or '').strip() for v in normalized.values())):
            continue
        out.append(_customer_opening_normalize_row(normalized, rowno))
    return (out, [])

def _customer_opening_validate_rows(rows: List[Dict[str, Any]], balance_account: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    acc_codes = {str(a.get('code') or '').strip() for a in _customer_opening_account_options()}
    bal = str(balance_account or '').strip()
    errors: List[str] = []
    if not bal:
        errors.append('Opening / suspense account is required.')
    elif bal not in acc_codes:
        errors.append(f'Opening / suspense account {bal!r} is not in Chart of Accounts.')
    valid: List[Dict[str, Any]] = []
    seen = set()
    for r in rows:
        rowno = r.get('rowno') or '?'
        cc = str(r.get('customercode') or '').strip()
        inv = str(r.get('invoiceno') or '').strip()
        inv_date = str(r.get('invoicedate') or '').strip()
        amt = float(r.get('invoiceamount') or 0)
        if not cc:
            errors.append(f'Row {rowno}: customer code is required.')
            continue
        cust = get_customer_master_by_code(cc)
        if not cust:
            errors.append(f'Row {rowno}: customer code {cc} not found.')
            continue
        recv = str(cust.get('receivableaccount') or DEFAULT_PARTY_ACCOUNTS.get('customer_receivable') or '1200').strip()
        if recv not in acc_codes:
            errors.append(f'Row {rowno}: receivable account {recv!r} for customer {cc} is not in Chart of Accounts.')
            continue
        if not inv:
            errors.append(f'Row {rowno}: invoice no is required.')
            continue
        if not inv_date:
            errors.append(f'Row {rowno}: invoice date is invalid or missing.')
            continue
        if amt <= 0:
            errors.append(f'Row {rowno}: invoice amount must be greater than zero.')
            continue
        key = (cc.upper(), inv.upper())
        if key in seen:
            errors.append(f'Row {rowno}: duplicate invoice {inv} for customer {cc} in this file/entry.')
            continue
        seen.add(key)
        r['customername'] = str(cust.get('customername') or r.get('customername') or '').strip()
        r['receivableaccount'] = recv
        valid.append(r)
    return (valid, errors)

def _customer_opening_post_rows(rows: List[Dict[str, Any]], balance_account: str) -> List[str]:
    """Post all opening invoices in one DB transaction (all vouchers commit or none)."""
    user = str(session.get('user') or '')
    bal = str(balance_account or '').strip()
    vouchers: List[str] = []
    with _get_connection() as conn:
        try:
            for r in rows:
                cc = str(r.get('customercode') or '').strip()
                inv = str(r.get('invoiceno') or '').strip()
                amount = float(r.get('invoiceamount') or 0)
                remarks = str(r.get('remarks') or '').strip()
                cust_name = str(r.get('customername') or '').strip()
                narration = f'Customer opening outstanding {inv} - {cc}'
                if cust_name:
                    narration += f' {cust_name}'
                if remarks:
                    narration += f' - {remarks}'
                vno = create_gl_journal_entry(voucher_date=str(r.get('invoicedate') or ''), reference_no=inv[:50], narration=narration[:500], source='CUST_OPEN_OUT', created_by=user, lines=[{'account_code': r.get('receivableaccount'), 'debit': amount, 'credit': 0, 'remarks': (remarks or f'Opening outstanding invoice {inv}')[:250], 'party_type': 'CUSTOMER', 'party_code': cc}, {'account_code': bal, 'debit': 0, 'credit': amount, 'remarks': f'Opening outstanding contra {inv}'[:250]}], conn=conn, commit=False)
                vouchers.append(vno)
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
    return vouchers

_MAX_SUPPLIER_OPENING_CSV = _MAX_CUSTOMER_OPENING_CSV

def _supplier_opening_supplier_options() -> List[Dict[str, Any]]:
    default_pay = str(DEFAULT_PARTY_ACCOUNTS.get('supplier_payable') or '2110').strip()
    rows = get_supplier_list(location_code=None, search=None, limit=15000, row_cap=20000) or []
    out: List[Dict[str, Any]] = []
    seen: set = set()
    for r in rows:
        sc = str(r.get('suppliercode') or '').strip()
        if not sc or sc in seen:
            continue
        seen.add(sc)
        pa = str(r.get('payableaccount') or default_pay).strip() or default_pay
        out.append({'suppliercode': sc, 'suppliername': str(r.get('suppliername') or '').strip(), 'payableaccount': pa[:COA_CODE_MAX_LEN]})
    return sorted(out, key=lambda x: str(x.get('suppliercode') or ''))

def _supplier_opening_default_balance_account(accounts: List[Dict[str, Any]]) -> str:
    return _customer_opening_default_balance_account(accounts)

def _supplier_opening_normalize_row(row: Dict[str, Any], rowno: int) -> Dict[str, Any]:

    def pick(*keys: str) -> str:
        for k in keys:
            v = row.get(k)
            if v is not None and str(v).strip():
                return str(v).strip()
        return ''
    return {'rowno': rowno, 'suppliercode': pick('suppliercode', 'supplier_code', 'sup_code', 'supplier'), 'suppliername': pick('suppliername', 'supplier_name', 'sup_name', 'name'), 'invoiceno': pick('invoiceno', 'invoice_no', 'billno', 'bill_no'), 'invoicedate': _parse_iso_date(pick('invoicedate', 'invoice_date', 'billdate', 'bill_date')), 'invoiceamount': _customer_opening_norm_amount(pick('invoiceamount', 'invoice_amount', 'billamount', 'bill_amount', 'amount')), 'remarks': pick('narration', 'narration_remarks', 'remarks', 'remark', 'description')}

def _supplier_opening_parse_csv(data: bytes) -> Tuple[List[Dict[str, Any]], List[str]]:
    try:
        text = data.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = data.decode('latin1', errors='replace')
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return ([], ['CSV header row is missing.'])
    out: List[Dict[str, Any]] = []
    for rowno, raw in enumerate(reader, start=2):
        normalized = {str(k or '').strip().lower().replace(' ', '_').replace('/', '_'): v for k, v in (raw or {}).items()}
        if not any((str(v or '').strip() for v in normalized.values())):
            continue
        out.append(_supplier_opening_normalize_row(normalized, rowno))
    return (out, [])

def _supplier_opening_validate_rows(rows: List[Dict[str, Any]], balance_account: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    acc_codes = {str(a.get('code') or '').strip() for a in _customer_opening_account_options()}
    bal = str(balance_account or '').strip()
    errors: List[str] = []
    if not bal:
        errors.append('Opening / suspense account is required.')
    elif bal not in acc_codes:
        errors.append(f'Opening / suspense account {bal!r} is not in Chart of Accounts.')
    valid: List[Dict[str, Any]] = []
    seen = set()
    for r in rows:
        rowno = r.get('rowno') or '?'
        sc = str(r.get('suppliercode') or '').strip()
        inv = str(r.get('invoiceno') or '').strip()
        inv_date = str(r.get('invoicedate') or '').strip()
        amt = float(r.get('invoiceamount') or 0)
        if not sc:
            errors.append(f'Row {rowno}: supplier code is required.')
            continue
        sup = get_supplier_master_by_code(sc)
        if not sup:
            errors.append(f'Row {rowno}: supplier code {sc} not found.')
            continue
        pay = str(sup.get('payableaccount') or DEFAULT_PARTY_ACCOUNTS.get('supplier_payable') or '2110').strip()
        if pay not in acc_codes:
            errors.append(f'Row {rowno}: payable account {pay!r} for supplier {sc} is not in Chart of Accounts.')
            continue
        if not inv:
            errors.append(f'Row {rowno}: invoice no is required.')
            continue
        if not inv_date:
            errors.append(f'Row {rowno}: invoice date is invalid or missing.')
            continue
        if amt <= 0:
            errors.append(f'Row {rowno}: invoice amount must be greater than zero.')
            continue
        key = (sc.upper(), inv.upper())
        if key in seen:
            errors.append(f'Row {rowno}: duplicate invoice {inv} for supplier {sc} in this file/entry.')
            continue
        seen.add(key)
        r['suppliername'] = str(sup.get('suppliername') or r.get('suppliername') or '').strip()
        r['payableaccount'] = pay
        valid.append(r)
    return (valid, errors)

def _supplier_opening_post_rows(rows: List[Dict[str, Any]], balance_account: str) -> List[str]:
    """Post all opening invoices in one DB transaction (all vouchers commit or none)."""
    user = str(session.get('user') or '')
    bal = str(balance_account or '').strip()
    vouchers: List[str] = []
    with _get_connection() as conn:
        try:
            for r in rows:
                sc = str(r.get('suppliercode') or '').strip()
                inv = str(r.get('invoiceno') or '').strip()
                amount = float(r.get('invoiceamount') or 0)
                remarks = str(r.get('remarks') or '').strip()
                sup_name = str(r.get('suppliername') or '').strip()
                narration = f'Supplier opening outstanding {inv} - {sc}'
                if sup_name:
                    narration += f' {sup_name}'
                if remarks:
                    narration += f' - {remarks}'
                vno = create_gl_journal_entry(voucher_date=str(r.get('invoicedate') or ''), reference_no=inv[:50], narration=narration[:500], source='SUPP_OPEN_OUT', created_by=user, lines=[{'account_code': r.get('payableaccount'), 'debit': 0, 'credit': amount, 'remarks': (remarks or f'Opening outstanding invoice {inv}')[:250], 'party_type': 'SUPPLIER', 'party_code': sc}, {'account_code': bal, 'debit': amount, 'credit': 0, 'remarks': f'Opening outstanding contra {inv}'[:250]}], conn=conn, commit=False)
                vouchers.append(vno)
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
    return vouchers

def _accounts_payable_party_tagged_rows(
    *,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Supplier AP rows from party-tagged GL only; avoids rebuilding full AP summary."""
    return _party_tagged_balance_rows(
        party_type='SUPPLIER',
        master_tables=['SUPPLIER', 'supplier'],
        code_candidates=['SUPPLIERCODE', 'suppliercode'],
        name_candidates=['SUPPLIERNAME', 'suppliername'],
        account_candidates=['PAYABLEACCOUNT', 'payableaccount'],
        location_candidates=['LOCATIONCODE', 'locationcode'],
        account_type='LIABILITY',
        balance_mode='credit_minus_debit',
        code_out='suppliercode',
        name_out='suppliername',
        account_out='payableaccount',
        balance_out='payable_balance',
        date_from=date_from,
        date_to=date_to,
    )

def _accounts_receivable_party_tagged_rows(
    *,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Customer AR rows from party-tagged GL only; avoids rebuilding full AR summary."""
    return _party_tagged_balance_rows(
        party_type='CUSTOMER',
        master_tables=['CUSTOMER', 'CUSTOMERS', 'customer', 'customers'],
        code_candidates=['CUSTOMERCODE', 'CUST_CODE', 'CUSTOMER_CODE', 'CODE', 'code'],
        name_candidates=['CUSTOMERNAME', 'CUST_NAME', 'CUSTOMER_NAME', 'NAME', 'name'],
        account_candidates=['RECEIVABLEACCOUNT', 'receivableaccount', 'RECEIVABLE_AC', 'receivable_acct'],
        location_candidates=['LOCATIONCODE', 'locationcode'],
        account_type='ASSET',
        balance_mode='debit_minus_credit',
        code_out='customercode',
        name_out='customername',
        account_out='receivableaccount',
        balance_out='receivable_balance',
        date_from=date_from,
        date_to=date_to,
    )


def _ap_ar_list_date_args() -> Tuple[str, str]:
    """Parse optional date_from / date_to query params (YYYY-MM-DD)."""
    df = _parse_iso_date(request.args.get('date_from') or '') or ''
    dt = _parse_iso_date(request.args.get('date_to') or '') or ''
    if df and dt and df > dt:
        df, dt = dt, df
    return df, dt

def _norm_party_code(value: Any) -> str:
    s = str(value or '').strip()
    if not s:
        return ''
    try:
        f = float(s)
        if f.is_integer():
            return str(int(f))
    except Exception:
        pass
    return s

def _party_tagged_balance_rows(
    *,
    party_type: str,
    master_tables: List[str],
    code_candidates: List[str],
    name_candidates: List[str],
    account_candidates: List[str],
    location_candidates: List[str],
    account_type: str,
    balance_mode: str,
    code_out: str,
    name_out: str,
    account_out: str,
    balance_out: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> List[Dict[str, Any]]:
    t0 = time.perf_counter()
    try:
        ensure_gl_tables()
    except Exception:
        pass
    master_table = _detect_table(master_tables)
    if not master_table:
        return []
    code_col = _detect_column(master_table, code_candidates)
    name_col = _detect_column(master_table, name_candidates)
    acc_col = _detect_column(master_table, account_candidates)
    loc_col = _detect_column(master_table, location_candidates)
    if not code_col or not name_col:
        return []
    df = (date_from or '').strip()[:10]
    dt = (date_to or '').strip()[:10]
    date_join = ''
    date_where = ''
    params: Dict[str, Any] = {'party_type': party_type.upper(), 'account_type': account_type.upper()}
    if df or dt:
        date_join = 'JOIN GL_VOUCHER_HDR h ON h.VOUCHER_NO = d.VOUCHER_NO'
        if df:
            date_where += " AND TRUNC(h.VOUCHER_DATE) >= TO_DATE(:df, 'YYYY-MM-DD')"
            params['df'] = df
        if dt:
            date_where += " AND TRUNC(h.VOUCHER_DATE) <= TO_DATE(:dt, 'YYYY-MM-DD')"
            params['dt'] = dt
    party_rows = _safe_rows(
        f"""
        SELECT TRIM(TO_CHAR(d.PARTY_CODE)) AS party_code,
               d.ACCOUNT_CODE AS account_code,
               SUM(d.DEBIT) AS debit,
               SUM(d.CREDIT) AS credit
        FROM GL_VOUCHER_DTL d
        {date_join}
        JOIN CHART_OF_ACCOUNTS c
          ON TRIM(TO_CHAR(c.CODE)) = TRIM(TO_CHAR(d.ACCOUNT_CODE))
        WHERE UPPER(NVL(d.PARTY_TYPE, '')) = :party_type
          AND d.PARTY_CODE IS NOT NULL
          AND UPPER(NVL(c.TYPE, '')) = :account_type
          {date_where}
        GROUP BY TRIM(TO_CHAR(d.PARTY_CODE)), d.ACCOUNT_CODE
        """,
        params,
    )
    balances: Dict[str, float] = {}
    for r in party_rows or []:
        party_code = _norm_party_code(r.get('party_code'))
        account_code = _norm_party_code(r.get('account_code'))
        if not party_code or not account_code:
            continue
        debit = float(r.get('debit') or 0)
        credit = float(r.get('credit') or 0)
        amount = credit - debit if balance_mode == 'credit_minus_debit' else debit - credit
        balances[party_code] = round(balances.get(party_code, 0.0) + amount, 2)
    if not balances:
        return []

    party_codes = sorted(balances.keys(), key=lambda x: (len(x), x))
    master_map: Dict[str, Dict[str, Any]] = {}
    select_cols = [f'{code_col} AS party_code', f'{name_col} AS party_name']
    if loc_col:
        select_cols.append(f'{loc_col} AS locationcode')
    else:
        select_cols.append('NULL AS locationcode')
    if acc_col:
        select_cols.append(f'{acc_col} AS account_code')
    else:
        select_cols.append('NULL AS account_code')
    for offset in range(0, len(party_codes), 900):
        chunk = party_codes[offset:offset + 900]
        binds = {f'p{i}': code for i, code in enumerate(chunk)}
        placeholders = ', '.join(f':p{i}' for i in range(len(chunk)))
        rows = _safe_rows(
            f"""
            SELECT {', '.join(select_cols)}
            FROM {master_table}
            WHERE TRIM(TO_CHAR({code_col})) IN ({placeholders})
            """,
            binds,
        )
        for row in rows or []:
            master_map[_norm_party_code(row.get('party_code'))] = row

    out: List[Dict[str, Any]] = []
    for party_code in party_codes:
        master = master_map.get(party_code)
        if not master:
            continue
        out.append({
            'locationcode': master.get('locationcode'),
            code_out: master.get('party_code'),
            name_out: master.get('party_name'),
            account_out: _norm_party_code(master.get('account_code')),
            balance_out: round(balances.get(party_code, 0.0), 2),
            'party_code_in_gl_dtl': party_code,
            'balance_source': f'PARTY_{account_type.upper()}',
        })
    print(f"[TIMING accounts] {party_type.lower()}_party_tagged_rows elapsed_ms={(time.perf_counter() - t0) * 1000.0:.1f} rows={len(out)} party_codes={len(party_codes)}")
    return out

def _filter_party_balance_rows(rows: List[Dict[str, Any]], *, search: str='', balance_filter: str='all', party: str='supplier') -> List[Dict[str, Any]]:
    q = (search or '').strip().lower()
    balance_filter = (balance_filter or 'all').strip().lower()
    if balance_filter not in {'all', 'positive', 'negative', 'zero', 'nonzero'}:
        balance_filter = 'all'
    code_key = 'suppliercode' if party == 'supplier' else 'customercode'
    name_key = 'suppliername' if party == 'supplier' else 'customername'
    bal_key = 'payable_balance' if party == 'supplier' else 'receivable_balance'
    out: List[Dict[str, Any]] = []
    for row in rows or []:
        bal = float(row.get(bal_key) or 0)
        if balance_filter == 'positive' and not (bal > 0):
            continue
        if balance_filter == 'negative' and not (bal < 0):
            continue
        if balance_filter == 'zero' and abs(bal) > 0.00001:
            continue
        if balance_filter == 'nonzero' and abs(bal) <= 0.00001:
            continue
        if q:
            text = ' '.join([
                str(row.get('locationcode') or ''),
                str(row.get(code_key) or ''),
                str(row.get(name_key) or ''),
                str(row.get('party_code_in_gl_dtl') or ''),
            ]).lower()
            if q not in text:
                continue
        out.append(row)
    return out

def _build_ap_payable_summary_excel(rows: List[Dict[str, Any]]) -> Optional[bytes]:
    """Payable summary table as .xlsx (matches on-screen / PDF columns)."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    except ImportError:
        return None
    thin = Side(style='thin', color='CCCCCC')
    box = Border(left=thin, right=thin, top=thin, bottom=thin)
    hdr_fill = PatternFill(start_color='1a56a4', end_color='1a56a4', fill_type='solid')
    hdr_font = Font(bold=True, color='FFFFFF', size=10)
    total_fill = PatternFill(start_color='E8EEF5', end_color='E8EEF5', fill_type='solid')
    total_font = Font(bold=True, size=10)
    wb = Workbook()
    ws = wb.active
    ws.title = 'Payable Summary'
    loc_name = str(session.get('location_name') or 'Location')
    ws['A1'] = loc_name
    ws['A1'].font = Font(bold=True, size=13, color='1e3a5f')
    ws.merge_cells('A1:E1')
    ws['A2'] = 'Payable Summary'
    ws['A2'].font = Font(bold=True, size=11)
    ws.merge_cells('A2:E2')
    ws['A3'] = f"Generated by: {session.get('user') or 'web'} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    ws.merge_cells('A3:E3')
    total = sum((float(r.get('payable_balance') or 0) for r in rows or []))
    ws['A4'] = f'Total outstanding: {total:.2f}'
    ws['A4'].font = Font(bold=True, size=10)
    ws.merge_cells('A4:E4')
    headers = ['Location', 'Supplier Code', 'Supplier Name', 'PartyCode', 'Balance']
    hrow = 6
    for c, h in enumerate(headers, 1):
        cell = ws.cell(row=hrow, column=c, value=h)
        cell.fill = hdr_fill
        cell.font = hdr_font
        cell.border = box
        cell.alignment = Alignment(horizontal='center' if c != 3 else 'left', wrap_text=True)
    r = hrow + 1
    for row in rows or []:
        ws.cell(row=r, column=1, value=row.get('locationcode'))
        ws.cell(row=r, column=2, value=row.get('suppliercode'))
        ws.cell(row=r, column=3, value=row.get('suppliername'))
        ws.cell(row=r, column=4, value=row.get('party_code_in_gl_dtl'))
        bal_cell = ws.cell(row=r, column=5, value=round(float(row.get('payable_balance') or 0), 2))
        bal_cell.alignment = Alignment(horizontal='right')
        for c in range(1, 6):
            ws.cell(row=r, column=c).border = box
            ws.cell(row=r, column=c).font = Font(size=10)
        r += 1
    ws.cell(row=r, column=1, value='')
    ws.cell(row=r, column=2, value='')
    ws.cell(row=r, column=3, value='')
    ws.cell(row=r, column=4, value='Total')
    ws.cell(row=r, column=5, value=round(total, 2))
    for c in range(1, 6):
        cell = ws.cell(row=r, column=c)
        cell.border = box
        cell.font = total_font
        cell.fill = total_fill
        if c == 5:
            cell.alignment = Alignment(horizontal='right')
    ws.column_dimensions['A'].width = 12
    ws.column_dimensions['B'].width = 14
    ws.column_dimensions['C'].width = 36
    ws.column_dimensions['D'].width = 14
    ws.column_dimensions['E'].width = 14
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

def _build_ap_payment_summary_pdf(rows: list) -> bytes:
    if not REPORTLAB_AVAILABLE:
        return b''
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.45 * inch, bottomMargin=0.45 * inch, leftMargin=0.35 * inch, rightMargin=0.35 * inch)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('ApTitle', parent=styles['Heading2'], fontSize=15, textColor=colors.HexColor('#1e3a5f'), alignment=TA_CENTER, spaceAfter=8)
    sub_style = ParagraphStyle('ApSub', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#4b5563'), alignment=TA_CENTER, spaceAfter=8)
    num_style = ParagraphStyle('ApNum', parent=styles['Normal'], fontSize=8.5, alignment=TA_RIGHT)
    txt_style = ParagraphStyle('ApTxt', parent=styles['Normal'], fontSize=8.5)
    story = []
    story.append(Paragraph(session.get('location_name') or 'Location', sub_style))
    story.append(Paragraph('Payable Summary', title_style))
    story.append(Paragraph(f"Generated by: {session.get('user') or 'web'} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", sub_style))
    story.append(Spacer(1, 4))
    total = sum((float(r.get('payable_balance') or 0) for r in rows or []))
    story.append(Paragraph(f'<b>Total Outstanding: {total:.2f}</b>', txt_style))
    story.append(Spacer(1, 6))
    table_data = [['Location', 'Supplier Code', 'Supplier Name', 'PartyCode', 'Balance']]
    for r in rows or []:
        table_data.append([Paragraph(str(r.get('locationcode') or ''), txt_style), Paragraph(str(r.get('suppliercode') or ''), txt_style), Paragraph(str(r.get('suppliername') or ''), txt_style), Paragraph(str(r.get('party_code_in_gl_dtl') or ''), txt_style), Paragraph(f"{float(r.get('payable_balance') or 0):.2f}", num_style)])
    table_data.append(['', '', '', Paragraph('<b>Total</b>', txt_style), Paragraph(f'<b>{total:.2f}</b>', num_style)])
    tbl = Table(table_data, colWidths=[0.8 * inch, 1.0 * inch, 2.6 * inch, 1.1 * inch, 1.2 * inch], repeatRows=1)
    tbl.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e5e7eb')), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('GRID', (0, 0), (-1, -1), 0.35, colors.HexColor('#d1d5db')), ('ALIGN', (4, 1), (4, -1), 'RIGHT'), ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f3f4f6'))]))
    story.append(tbl)
    doc.build(story)
    return buffer.getvalue()

def _build_ar_receivable_summary_excel(rows: List[Dict[str, Any]]) -> Optional[bytes]:
    """Receivable summary table as .xlsx (matches on-screen / PDF columns)."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    except ImportError:
        return None
    thin = Side(style='thin', color='CCCCCC')
    box = Border(left=thin, right=thin, top=thin, bottom=thin)
    hdr_fill = PatternFill(start_color='1a56a4', end_color='1a56a4', fill_type='solid')
    hdr_font = Font(bold=True, color='FFFFFF', size=10)
    total_fill = PatternFill(start_color='E8EEF5', end_color='E8EEF5', fill_type='solid')
    total_font = Font(bold=True, size=10)
    wb = Workbook()
    ws = wb.active
    ws.title = 'Receivable Summary'
    loc_name = str(session.get('location_name') or 'Location')
    ws['A1'] = loc_name
    ws['A1'].font = Font(bold=True, size=13, color='1e3a5f')
    ws.merge_cells('A1:E1')
    ws['A2'] = 'Receivable Summary'
    ws['A2'].font = Font(bold=True, size=11)
    ws.merge_cells('A2:E2')
    ws['A3'] = f"Generated by: {session.get('user') or 'web'} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    ws.merge_cells('A3:E3')
    total = sum((float(r.get('receivable_balance') or 0) for r in rows or []))
    ws['A4'] = f'Total outstanding: {total:.2f}'
    ws['A4'].font = Font(bold=True, size=10)
    ws.merge_cells('A4:E4')
    headers = ['Location', 'Customer Code', 'Customer Name', 'PartyCode', 'Balance']
    hrow = 6
    for c, h in enumerate(headers, 1):
        cell = ws.cell(row=hrow, column=c, value=h)
        cell.fill = hdr_fill
        cell.font = hdr_font
        cell.border = box
        cell.alignment = Alignment(horizontal='center' if c != 3 else 'left', wrap_text=True)
    r = hrow + 1
    for row in rows or []:
        ws.cell(row=r, column=1, value=row.get('locationcode'))
        ws.cell(row=r, column=2, value=row.get('customercode'))
        ws.cell(row=r, column=3, value=row.get('customername'))
        ws.cell(row=r, column=4, value=row.get('party_code_in_gl_dtl'))
        bal_cell = ws.cell(row=r, column=5, value=round(float(row.get('receivable_balance') or 0), 2))
        bal_cell.alignment = Alignment(horizontal='right')
        for c in range(1, 6):
            ws.cell(row=r, column=c).border = box
            ws.cell(row=r, column=c).font = Font(size=10)
        r += 1
    ws.cell(row=r, column=1, value='')
    ws.cell(row=r, column=2, value='')
    ws.cell(row=r, column=3, value='')
    ws.cell(row=r, column=4, value='Total')
    ws.cell(row=r, column=5, value=round(total, 2))
    for c in range(1, 6):
        cell = ws.cell(row=r, column=c)
        cell.border = box
        cell.font = total_font
        cell.fill = total_fill
        if c == 5:
            cell.alignment = Alignment(horizontal='right')
    ws.column_dimensions['A'].width = 12
    ws.column_dimensions['B'].width = 14
    ws.column_dimensions['C'].width = 36
    ws.column_dimensions['D'].width = 14
    ws.column_dimensions['E'].width = 14
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

def _build_ar_receivable_summary_pdf(rows: list) -> bytes:
    if not REPORTLAB_AVAILABLE:
        return b''
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.45 * inch, bottomMargin=0.45 * inch, leftMargin=0.35 * inch, rightMargin=0.35 * inch)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('ArTitle', parent=styles['Heading2'], fontSize=15, textColor=colors.HexColor('#1e3a5f'), alignment=TA_CENTER, spaceAfter=8)
    sub_style = ParagraphStyle('ArSub', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#4b5563'), alignment=TA_CENTER, spaceAfter=8)
    num_style = ParagraphStyle('ArNum', parent=styles['Normal'], fontSize=8.5, alignment=TA_RIGHT)
    txt_style = ParagraphStyle('ArTxt', parent=styles['Normal'], fontSize=8.5)
    story = []
    story.append(Paragraph(session.get('location_name') or 'Location', sub_style))
    story.append(Paragraph('Receivable Summary', title_style))
    story.append(Paragraph(f"Generated by: {session.get('user') or 'web'} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", sub_style))
    story.append(Spacer(1, 4))
    total = sum((float(r.get('receivable_balance') or 0) for r in rows or []))
    story.append(Paragraph(f'<b>Total Outstanding: {total:.2f}</b>', txt_style))
    story.append(Spacer(1, 6))
    table_data = [['Location', 'Customer Code', 'Customer Name', 'PartyCode', 'Balance']]
    for r in rows or []:
        table_data.append([Paragraph(str(r.get('locationcode') or ''), txt_style), Paragraph(str(r.get('customercode') or ''), txt_style), Paragraph(str(r.get('customername') or ''), txt_style), Paragraph(str(r.get('party_code_in_gl_dtl') or ''), txt_style), Paragraph(f"{float(r.get('receivable_balance') or 0):.2f}", num_style)])
    table_data.append(['', '', '', Paragraph('<b>Total</b>', txt_style), Paragraph(f'<b>{total:.2f}</b>', num_style)])
    tbl = Table(table_data, colWidths=[0.8 * inch, 1.0 * inch, 2.6 * inch, 1.1 * inch, 1.2 * inch], repeatRows=1)
    tbl.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e5e7eb')), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('GRID', (0, 0), (-1, -1), 0.35, colors.HexColor('#d1d5db')), ('ALIGN', (4, 1), (4, -1), 'RIGHT'), ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f3f4f6'))]))
    story.append(tbl)
    doc.build(story)
    return buffer.getvalue()


def _pdf_date_mdy(raw: Any) -> str:
    s = str(raw or '').strip()
    if not s:
        return '—'
    try:
        return datetime.strptime(s[:10], '%Y-%m-%d').strftime('%m/%d/%Y')
    except Exception:
        return s[:12]


def _voucher_line_account_code(line: Dict[str, Any]) -> str:
    return str(line.get('account_code') or line.get('ACCOUNT_CODE') or '').strip()


def _voucher_party_from_lines(lines: List[Dict[str, Any]], narration: str = '', fallback: str = '—') -> str:
    descs = [
        str(ln.get('description') or ln.get('DESCRIPTION') or '').strip()
        for ln in lines or []
        if round(float(ln.get('amount') or ln.get('AMOUNT') or 0), 2) > 0
        and str(ln.get('description') or ln.get('DESCRIPTION') or '').strip()
    ]
    if len(descs) == 1:
        return descs[0]
    if len(descs) > 1:
        return f'{descs[0]} (+ {len(descs) - 1} more)'
    nar = str(narration or '').strip()
    return nar or fallback


def _voucher_account_label(code: str, account_names: Dict[str, str]) -> str:
    acode = str(code or '').strip()
    if not acode:
        return ''
    name = str(account_names.get(acode) or '').strip()
    return f'{acode} — {name}' if name else acode


def _voucher_account_summary_from_lines(
    lines: List[Dict[str, Any]],
    account_names: Dict[str, str],
    *,
    fallback: str = '—',
) -> str:
    labels: List[str] = []
    seen: set[str] = set()
    for ln in lines or []:
        try:
            amt = round(float(ln.get('amount') or ln.get('AMOUNT') or 0), 2)
        except Exception:
            amt = 0.0
        if amt <= 0:
            continue
        code = _voucher_line_account_code(ln)
        if not code or code in seen:
            continue
        seen.add(code)
        labels.append(_voucher_account_label(code, account_names))
    if not labels:
        return fallback
    if len(labels) == 1:
        return labels[0]
    if len(labels) <= 3:
        return '; '.join(labels)
    return f'{labels[0]} (+ {len(labels) - 1} more accounts)'


def _voucher_item_description(line: Dict[str, Any], account_names: Dict[str, str]) -> str:
    desc = str(line.get('description') or line.get('DESCRIPTION') or '').strip()
    code = _voucher_line_account_code(line)
    return _voucher_account_label(code, account_names) if not desc else (
        f'{desc} ({_voucher_account_label(code, account_names)})'
        if code else desc
    ) or '—'


def _build_petty_cash_style_voucher_pdf(
    *,
    voucher_no: str,
    voucher_date: str,
    voucher_title: str,
    party_field_label: str,
    party_name: str,
    item_lines: List[Dict[str, Any]],
    total_amount: float,
    created_by: str = '',
    verified_by: str = '',
    approved_by: str = '',
    debit_account_label: str = '',
    debit_account_name: str = '',
    credit_account_label: str = '',
    credit_account_name: str = '',
    reference_no: str = '',
) -> bytes:
    """Receipt / Payment / Cash Payment voucher PDF — petty-cash voucher layout."""
    if not REPORTLAB_AVAILABLE:
        return b''
    from addons.purchase.controllers.routes import _get_company_profile

    company = _get_company_profile()
    company_name = str(company.get('name') or session.get('location_name') or 'Company')
    company_address = str(company.get('address') or '').strip()
    company_phone = str(company.get('phone') or '').strip()
    company_email = str(company.get('email') or '').strip()
    created_by = str(created_by or session.get('user') or '—').strip() or '—'
    verified_by = str(verified_by or '—').strip() or '—'
    approved_by = str(approved_by or '—').strip() or '—'

    NAVY = colors.HexColor('#1e4a63')
    TEAL = colors.HexColor('#9ecfd4')
    TEAL_LINE = colors.HexColor('#8ab8bd')
    BAR = colors.HexColor('#4a5f52')
    BANNER_BG = colors.HexColor('#eef3f4')
    ZEBRA = colors.HexColor('#f4f8f9')
    BORDER = colors.HexColor('#c5d3d6')
    MUTED = colors.HexColor('#5a6a72')
    PAD = 6
    W = 7.47 * inch
    FOOTER_RESERVE = 1.35 * inch

    styles = getSampleStyleSheet()

    def _s(name: str, **kw: Any):
        base = kw.pop('parent', styles['Normal'])
        return ParagraphStyle(name, parent=base, **kw)

    CO_NAME = _s('pcvCo', fontSize=14, leading=17, alignment=TA_CENTER, textColor=NAVY, fontName='Helvetica-Bold')
    CO_SUB = _s('pcvSub', fontSize=9, leading=11, alignment=TA_CENTER, textColor=MUTED)
    TITLE = _s('pcvTitle', fontSize=16, leading=19, alignment=TA_CENTER, textColor=NAVY, fontName='Helvetica-Bold')
    LBL = _s('pcvLbl', fontSize=9, leading=11, textColor=NAVY, fontName='Helvetica-Bold')
    VAL = _s('pcvVal', fontSize=9, leading=11, textColor=colors.HexColor('#222222'))
    SEC = _s('pcvSec', fontSize=10, leading=12, textColor=NAVY, fontName='Helvetica-Bold')
    N9 = _s('pcvN9', fontSize=9, leading=11, textColor=colors.HexColor('#222222'))
    N9R = _s('pcvN9r', fontSize=9, leading=11, alignment=TA_RIGHT, textColor=colors.HexColor('#222222'))
    HDR = _s('pcvHdr', fontSize=9, leading=11, alignment=TA_CENTER, textColor=NAVY, fontName='Helvetica-Bold')

    footer_names = (created_by, verified_by, approved_by)

    def _draw_voucher_footer(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        page_w, _page_h = doc.pagesize
        left = doc.leftMargin
        right = page_w - doc.rightMargin
        col_w = (right - left) / 3.0
        navy = (0.118, 0.290, 0.388)
        muted = (0.353, 0.416, 0.447)
        line_color = (0.533, 0.533, 0.533)

        y_rule = doc.bottomMargin + 1.02 * inch
        y_label = doc.bottomMargin + 0.82 * inch
        y_name = doc.bottomMargin + 0.64 * inch
        y_sig = doc.bottomMargin + 0.48 * inch
        y_line = doc.bottomMargin + 0.28 * inch
        y_note = doc.bottomMargin + 0.08 * inch

        canvas.setStrokeColorRGB(*line_color)
        canvas.setLineWidth(0.5)
        canvas.line(left, y_rule, right, y_rule)

        labels = ('Created By', 'Verified By', 'Approved By')
        for i, (label, name) in enumerate(zip(labels, footer_names)):
            cx = left + col_w * i + col_w / 2.0
            sig_left = left + col_w * i + 0.25 * inch
            sig_right = left + col_w * (i + 1) - 0.25 * inch
            canvas.setFillColorRGB(*navy)
            canvas.setFont('Helvetica-Bold', 9)
            canvas.drawCentredString(cx, y_label, label)
            canvas.setFillColorRGB(0.133, 0.133, 0.133)
            canvas.setFont('Helvetica', 9)
            canvas.drawCentredString(cx, y_name, _trunc_pdf_text(name, 28))
            canvas.setFillColorRGB(*muted)
            canvas.setFont('Helvetica', 8)
            canvas.drawCentredString(cx, y_sig, 'Signature')
            canvas.setStrokeColorRGB(*line_color)
            canvas.line(sig_left, y_line, sig_right, y_line)

        canvas.setFillColorRGB(*muted)
        canvas.setFont('Helvetica', 8)
        canvas.drawCentredString(page_w / 2.0, y_note, 'This is a computer-generated voucher.')
        canvas.restoreState()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=0.5 * inch,
        bottomMargin=FOOTER_RESERVE,
        leftMargin=0.55 * inch,
        rightMargin=0.55 * inch,
    )
    elements: List[Any] = []

    elements.append(Paragraph(f'<b>{_trunc_pdf_text(company_name, 80)}</b>', CO_NAME))
    if company_address:
        elements.append(Paragraph(_trunc_pdf_text(company_address, 120), CO_SUB))
    contact_parts = [p for p in [company_phone, company_email] if p]
    if contact_parts:
        elements.append(Paragraph(' | '.join(contact_parts), CO_SUB))
    elements.append(Spacer(1, 6))
    rule = Table([['']], colWidths=[W], rowHeights=[1.5], hAlign='CENTER')
    rule.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), TEAL_LINE)]))
    elements.append(rule)
    elements.append(Spacer(1, 10))

    banner = Table(
        [[Paragraph(f'<b>{voucher_title.upper()}</b>', TITLE)]],
        colWidths=[W],
        hAlign='CENTER',
    )
    banner.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), BANNER_BG),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
    ]))
    elements.append(banner)
    bar = Table([['']], colWidths=[W], rowHeights=[4], hAlign='CENTER')
    bar.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), BAR)]))
    elements.append(bar)
    elements.append(Spacer(1, 14))

    vno = str(voucher_no or '—').strip() or '—'
    vdt = _pdf_date_mdy(voucher_date)
    meta_rows: List[List[Any]] = [
        [Paragraph('Voucher #', LBL), Paragraph(vno, VAL), Paragraph('Date', LBL), Paragraph(vdt, VAL)],
    ]
    meta = Table(
        meta_rows,
        colWidths=[0.95 * inch, 2.55 * inch, 0.75 * inch, 3.22 * inch],
        hAlign='LEFT',
    )
    meta.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
    ]))
    elements.append(meta)
    elements.append(Spacer(1, 14))
    elements.append(Paragraph('<b>Items</b>', SEC))
    elements.append(Spacer(1, 6))

    rows: List[Any] = [[Paragraph('<b>Date</b>', HDR), Paragraph('<b>Item / Description</b>', HDR), Paragraph('<b>Amount</b>', HDR)]]
    line_total = 0.0
    body_count = 0
    for ln in item_lines or []:
        try:
            amt = round(float(ln.get('amount') or 0), 2)
        except Exception:
            amt = 0.0
        if amt <= 0:
            continue
        line_total += amt
        body_count += 1
        dt = str(ln.get('date') or vdt)
        desc = _trunc_pdf_text(ln.get('description'), 90)
        rows.append([Paragraph(dt, N9), Paragraph(desc, N9), Paragraph(f'{amt:,.2f}', N9R)])

    if body_count == 0:
        rows.append([Paragraph(vdt, N9), Paragraph('—', N9), Paragraph('0.00', N9R)])

    tbl_w = [1.15 * inch, 4.72 * inch, 1.6 * inch]
    tbl = Table(rows, colWidths=tbl_w, repeatRows=1, hAlign='LEFT')
    tbl_style = [
        ('BACKGROUND', (0, 0), (-1, 0), TEAL),
        ('GRID', (0, 0), (-1, -1), 0.4, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), PAD),
        ('BOTTOMPADDING', (0, 0), (-1, -1), PAD),
        ('LEFTPADDING', (0, 0), (-1, -1), PAD),
        ('RIGHTPADDING', (0, 0), (-1, -1), PAD),
        ('ALIGN', (2, 1), (2, -1), 'RIGHT'),
    ]
    if body_count > 1:
        tbl_style.append(('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, ZEBRA]))
    tbl.setStyle(TableStyle(tbl_style))
    elements.append(tbl)
    elements.append(Spacer(1, 8))

    total_val = round(float(total_amount or line_total), 2)
    total_tbl = Table(
        [
            ['', Paragraph('<b>Total Amount</b>', _s('pcvTotLbl', parent=N9, fontName='Helvetica-Bold', alignment=TA_RIGHT)), Paragraph(f'<b>{total_val:,.2f}</b>', _s('pcvTotVal', parent=N9R, fontName='Helvetica-Bold'))],
        ],
        colWidths=tbl_w,
        hAlign='LEFT',
    )
    total_tbl.setStyle(TableStyle([
        ('ALIGN', (1, 0), (2, 0), 'RIGHT'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LINEABOVE', (1, 0), (2, 0), 0.6, BORDER),
    ]))
    elements.append(total_tbl)

    doc.build(elements, onFirstPage=_draw_voucher_footer, onLaterPages=_draw_voucher_footer)
    return buffer.getvalue()


def _build_supplier_payment_voucher_pdf(voucher: Dict[str, Any], *, supplier_label: str, allocations: List[Dict[str, Any]], voucher_title: str='SUPPLIER PAYMENT VOUCHER', party_field_label: str='Supplier') -> bytes:
    """Standard supplier payment voucher PDF (company header, meta, GL lines, optional invoice allocations)."""
    if not REPORTLAB_AVAILABLE:
        return b''
    from addons.purchase.controllers.routes import _get_company_profile

    def _dmy(raw: str) -> str:
        s = (raw or '').strip()
        if not s:
            return '—'
        try:
            return datetime.strptime(s[:10], '%Y-%m-%d').strftime('%d-%m-%Y')
        except Exception:
            return s[:12]
    company = _get_company_profile()
    company_name = str(company.get('name') or session.get('location_name') or '')
    company_address = str(company.get('address') or '')
    company_phone = str(company.get('phone') or '')
    company_email = str(company.get('email') or '')
    username = str(session.get('user') or '')
    styles = getSampleStyleSheet()
    BLUE = colors.HexColor('#1a56a4')
    BLUE_LIGHT = colors.HexColor('#e8f0fb')
    BORDER = colors.HexColor('#b0b8c4')
    GRAY_ROW = colors.HexColor('#f7f8fa')
    TEXT = colors.HexColor('#1a1a1a')
    PAD = 4
    W = 7.47 * inch

    def _s(st_name: str, **kw: Any):
        base = kw.pop('parent', styles['Normal'])
        kw.setdefault('textColor', TEXT)
        return ParagraphStyle(st_name, parent=base, **kw)
    N8 = _s('pv8', fontSize=8, leading=10)
    N8R = _s('pv8r', fontSize=8, leading=10, alignment=TA_RIGHT)
    N8C = _s('pv8c', fontSize=8, leading=10, alignment=TA_CENTER)
    LBL = _s('pvlbl', fontSize=8, leading=10, textColor=colors.HexColor('#555f6b'))
    SUB = _s('pvsub', fontSize=8, leading=10, alignment=TA_CENTER, textColor=colors.HexColor('#555f6b'))
    WHT = _s('pvwht', fontSize=8, leading=10, alignment=TA_CENTER, textColor=colors.white)
    FOOT = _s('pvft', fontSize=7, leading=9, textColor=colors.HexColor('#888'))
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.45 * inch, bottomMargin=0.35 * inch, leftMargin=0.4 * inch, rightMargin=0.4 * inch)
    elements = []
    clines = [Paragraph(f'<b>{company_name}</b>', _s('pvcn', fontSize=11, leading=13.5, alignment=TA_CENTER, textColor=BLUE))]
    if company_address:
        clines.append(Paragraph(company_address, SUB))
    if company_phone:
        clines.append(Paragraph(f'Tel: {company_phone}', SUB))
    if company_email:
        clines.append(Paragraph(f'Email: {company_email}', SUB))
    elements.append(Table([[clines]], colWidths=[W], hAlign='LEFT'))
    elements.append(Spacer(1, 4))
    elements.append(Paragraph(f'<b>{voucher_title}</b>', _s('pvtitle', fontSize=12, leading=15, alignment=TA_CENTER, textColor=BLUE)))
    elements.append(Spacer(1, 4))
    _rule = Table([['']], colWidths=[W], rowHeights=[2], hAlign='LEFT')
    _rule.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), BLUE)]))
    elements.append(_rule)
    elements.append(Spacer(1, 8))
    vno = str(voucher.get('voucher_no') or '')
    vdt = _dmy(str(voucher.get('voucher_date') or ''))
    ref = str(voucher.get('reference_no') or '').strip() or '—'
    nar = _trunc_pdf_text(voucher.get('narration'), 120)
    ap_totals = {}
    src = str(voucher.get('source') or '').strip().upper()
    if src == 'AP_RECEIPT':
        ap_totals = ap_receipt_voucher_totals(voucher)
        amt_label = 'Net payment'
        inv_cleared_label = 'Invoices cleared'
        pdf_footer = 'Computer-generated supplier payment voucher from GL. No signature is required.'
    elif src == 'AR_RECEIPT':
        ap_totals = ar_receipt_voucher_totals(voucher)
        amt_label = 'Net receipt'
        inv_cleared_label = 'Invoices collected'
        pdf_footer = 'Computer-generated customer receipt voucher from GL. No signature is required.'
    else:
        amt_label = 'Amount'
        inv_cleared_label = 'Invoices cleared'
        pdf_footer = 'Computer-generated payment voucher from GL. No signature is required.'
    invoice_ap = float(ap_totals.get('invoice_total') or 0)
    credit_ap = float(ap_totals.get('credit_total') or 0)
    discount_ap = float(ap_totals.get('discount_total') or 0)
    net_ap = float(ap_totals.get('net_cash') or 0)
    if ap_totals:
        amt = net_ap
    else:
        amt = float(voucher.get('total_debit') or voucher.get('total_credit') or 0)
    inf_rows = [
        [Paragraph('Voucher No', LBL), Paragraph(vno, N8), Paragraph('Payment Date', LBL), Paragraph(vdt, N8)],
        [Paragraph('Reference', LBL), Paragraph(ref, N8), Paragraph(amt_label, LBL), Paragraph(f'{amt:.2f}', N8R)],
        [Paragraph(party_field_label, LBL), Paragraph(_trunc_pdf_text(supplier_label, 72), N8), Paragraph('Prepared By', LBL), Paragraph(username or '—', N8)],
        [Paragraph('Narration', LBL), Paragraph(nar, N8), Paragraph('Source', LBL), Paragraph(str(voucher.get('source') or '—'), N8)],
    ]
    if ap_totals and (invoice_ap > 0 or credit_ap > 0 or discount_ap > 0):
        inf_rows.append([Paragraph(inv_cleared_label, LBL), Paragraph(f'{invoice_ap:.2f}', N8R), Paragraph('Credits applied', LBL), Paragraph(f'{credit_ap:.2f}', N8R)])
        if discount_ap > 0.009:
            inf_rows.append([Paragraph('Settlement discount', LBL), Paragraph(f'{discount_ap:.2f}', N8R), Paragraph(amt_label, LBL), Paragraph(f'{net_ap:.2f}', N8R)])
    inf = Table(inf_rows, colWidths=[1.05 * inch, 2.65 * inch, 1.05 * inch, 2.72 * inch], hAlign='LEFT')
    inf.setStyle(TableStyle([('BOX', (0, 0), (-1, -1), 0.5, BORDER), ('BACKGROUND', (0, 0), (-1, -1), BLUE_LIGHT), ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), PAD), ('RIGHTPADDING', (0, 0), (-1, -1), PAD), ('TOPPADDING', (0, 0), (-1, -1), PAD), ('BOTTOMPADDING', (0, 0), (-1, -1), PAD), ('LINEBELOW', (0, 0), (-1, -1), 0.3, colors.HexColor('#dde3ea'))]))
    elements.append(inf)
    elements.append(Spacer(1, 10))

    def _hw(txt: str) -> Paragraph:
        return Paragraph(f'<b>{txt}</b>', WHT)
    hdr_gl = ['Ln', 'Account', 'Account name', 'Party', 'Debit', 'Credit', 'Remarks']
    rows_gl: List[Any] = [[_hw(c) for c in hdr_gl]]
    for ln in voucher.get('lines') or []:
        try:
            lno = int(ln.get('line_no') or 0)
        except Exception:
            lno = 0
        ac = str(ln.get('account_code') or '')
        an = _trunc_pdf_text(ln.get('account_name'), 28)
        party_cell = _trunc_pdf_text(_party_display_label(ln), 22)
        dr = float(ln.get('debit') or 0)
        cr = float(ln.get('credit') or 0)
        rm = _trunc_pdf_text(ln.get('remarks'), 26)
        rows_gl.append([Paragraph(str(lno), N8C), Paragraph(ac, N8), Paragraph(str(an or ''), N8), Paragraph(str(party_cell), N8), Paragraph(f'{dr:.2f}' if dr else '—', N8R), Paragraph(f'{cr:.2f}' if cr else '—', N8R), Paragraph(str(rm or ''), N8)])
    td = float(voucher.get('total_debit') or 0)
    tc = float(voucher.get('total_credit') or 0)
    b = _s('pvb', parent=N8, fontName='Helvetica-Bold', alignment=TA_RIGHT)
    rows_gl.append([Paragraph('', N8), Paragraph('', N8), Paragraph('', N8), Paragraph('<b>Total</b>', _s('pvtot', parent=N8, fontName='Helvetica-Bold')), Paragraph(f'<b>{td:.2f}</b>', b), Paragraph(f'<b>{tc:.2f}</b>', b), Paragraph('', N8)])
    cw_gl = [0.38 * inch, 0.82 * inch, 1.85 * inch, 1.05 * inch, 0.85 * inch, 0.85 * inch, 1.67 * inch]
    tbl_gl = Table(rows_gl, repeatRows=1, colWidths=cw_gl, hAlign='LEFT')
    tbl_gl.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), BLUE), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('GRID', (0, 0), (-1, -1), 0.4, BORDER), ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, GRAY_ROW]), ('BACKGROUND', (0, -1), (-1, -1), BLUE_LIGHT), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('TOPPADDING', (0, 0), (-1, -1), PAD), ('BOTTOMPADDING', (0, 0), (-1, -1), PAD), ('LEFTPADDING', (0, 0), (-1, -1), PAD), ('RIGHTPADDING', (0, 0), (-1, -1), PAD)]))
    elements.append(tbl_gl)
    if allocations:
        elements.append(Spacer(1, 10))
        elements.append(Paragraph('<b>Invoice allocation</b>', _s('pvh2', fontSize=9, leading=11, textColor=BLUE)))
        elements.append(Spacer(1, 4))
        hdr_a = ['Document voucher', 'Type', 'Allocated amount']
        rows_a: List[Any] = [[_hw(c) for c in hdr_a]]
        inv_alloc_total = 0.0
        credit_alloc_total = 0.0
        for ar in allocations:
            inv_no = str(ar.get('invoice_voucher_no') or ar.get('INVOICE_VOUCHER_NO') or '').strip()
            try:
                aamt = round(float(ar.get('allocated_amount') or ar.get('ALLOCATED_AMOUNT') or 0), 2)
            except Exception:
                aamt = 0.0
            is_credit_alloc = bool(ar.get('is_credit'))
            if is_credit_alloc:
                credit_alloc_total += aamt
                kind = 'Credit'
            else:
                inv_alloc_total += aamt
                kind = 'Invoice'
            rows_a.append([Paragraph(inv_no, N8), Paragraph(kind, N8), Paragraph(f'{aamt:.2f}', N8R)])
        rows_a.append([Paragraph('<b>Invoices allocated</b>', _s('pvb2', parent=N8, fontName='Helvetica-Bold')), Paragraph('', N8), Paragraph(f'<b>{inv_alloc_total:.2f}</b>', b)])
        rows_a.append([Paragraph('<b>Credits applied</b>', _s('pvb2', parent=N8, fontName='Helvetica-Bold')), Paragraph('', N8), Paragraph(f'<b>{credit_alloc_total:.2f}</b>', b)])
        net_alloc = round(max(0.0, inv_alloc_total - credit_alloc_total), 2)
        rows_a.append([Paragraph('<b>Net cash (invoices − credits)</b>', _s('pvb2', parent=N8, fontName='Helvetica-Bold')), Paragraph('', N8), Paragraph(f'<b>{net_alloc:.2f}</b>', b)])
        tbl_a = Table(rows_a, repeatRows=1, colWidths=[3.4 * inch, 1.4 * inch, 2.67 * inch], hAlign='LEFT')
        tbl_a.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), BLUE), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('GRID', (0, 0), (-1, -1), 0.4, BORDER), ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, GRAY_ROW]), ('BACKGROUND', (0, -1), (-1, -1), BLUE_LIGHT), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('TOPPADDING', (0, 0), (-1, -1), PAD), ('BOTTOMPADDING', (0, 0), (-1, -1), PAD), ('LEFTPADDING', (0, 0), (-1, -1), PAD), ('RIGHTPADDING', (0, 0), (-1, -1), PAD)]))
        elements.append(tbl_a)
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(pdf_footer, FOOT))
    doc.build(elements)
    return buffer.getvalue()


def _build_journal_voucher_pdf(voucher: Dict[str, Any]) -> bytes:
    """Journal Entry / GL voucher PDF (company header, meta, Dr/Cr lines, totals)."""
    if not REPORTLAB_AVAILABLE:
        return b''
    from addons.purchase.controllers.routes import _get_company_profile

    def _dmy(raw: str) -> str:
        s = (raw or '').strip()
        if not s:
            return '—'
        try:
            return datetime.strptime(s[:10], '%Y-%m-%d').strftime('%d-%m-%Y')
        except Exception:
            return s[:12]

    company = _get_company_profile()
    company_name = str(company.get('name') or session.get('location_name') or 'Company')
    company_address = str(company.get('address') or '').strip()
    company_phone = str(company.get('phone') or '').strip()
    company_email = str(company.get('email') or '').strip()
    username = str(voucher.get('created_by') or session.get('user') or '').strip()
    styles = getSampleStyleSheet()
    BLUE = colors.HexColor('#1a56a4')
    BLUE_LIGHT = colors.HexColor('#e8f0fb')
    BORDER = colors.HexColor('#b0b8c4')
    GRAY_ROW = colors.HexColor('#f7f8fa')
    TEXT = colors.HexColor('#1a1a1a')
    PAD = 4
    LEFT_M = 0.4 * inch
    RIGHT_M = 0.4 * inch
    W = A4[0] - LEFT_M - RIGHT_M

    def _s(st_name: str, **kw: Any):
        base = kw.pop('parent', styles['Normal'])
        kw.setdefault('textColor', TEXT)
        return ParagraphStyle(st_name, parent=base, **kw)

    N8 = _s('jv8', fontSize=8, leading=10)
    N8R = _s('jv8r', fontSize=8, leading=10, alignment=TA_RIGHT)
    N8C = _s('jv8c', fontSize=8, leading=10, alignment=TA_CENTER)
    LBL = _s('jvlbl', fontSize=8, leading=10, textColor=colors.HexColor('#555f6b'))
    SUB = _s('jvsub', fontSize=8, leading=10, alignment=TA_CENTER, textColor=colors.HexColor('#555f6b'))
    WHT = _s('jvwht', fontSize=8, leading=10, alignment=TA_CENTER, textColor=colors.white)
    FOOT = _s('jvft', fontSize=7, leading=9, textColor=colors.HexColor('#888'))

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=0.45 * inch,
        bottomMargin=0.45 * inch,
        leftMargin=LEFT_M,
        rightMargin=RIGHT_M,
    )
    elements: List[Any] = []

    clines = [Paragraph(f'<b>{company_name}</b>', _s('jvcn', fontSize=11, leading=13.5, alignment=TA_CENTER, textColor=BLUE))]
    if company_address:
        clines.append(Paragraph(company_address, SUB))
    if company_phone:
        clines.append(Paragraph(f'Tel: {company_phone}', SUB))
    if company_email:
        clines.append(Paragraph(f'Email: {company_email}', SUB))
    elements.append(Table([[clines]], colWidths=[W], hAlign='LEFT'))
    elements.append(Spacer(1, 4))
    elements.append(Paragraph('<b>JOURNAL VOUCHER</b>', _s('jvtitle', fontSize=12, leading=15, alignment=TA_CENTER, textColor=BLUE)))
    elements.append(Spacer(1, 4))
    rule = Table([['']], colWidths=[W], rowHeights=[2], hAlign='LEFT')
    rule.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), BLUE)]))
    elements.append(rule)
    elements.append(Spacer(1, 8))

    vno = str(voucher.get('voucher_no') or '')
    vdt = _dmy(str(voucher.get('voucher_date') or ''))
    ref = str(voucher.get('reference_no') or '').strip() or '—'
    nar = _trunc_pdf_text(voucher.get('narration'), 140)
    src = str(voucher.get('source') or 'MANUAL').strip() or 'MANUAL'
    inf_rows = [
        [Paragraph('Voucher No', LBL), Paragraph(vno, N8), Paragraph('Voucher Date', LBL), Paragraph(vdt, N8)],
        [Paragraph('Reference', LBL), Paragraph(ref, N8), Paragraph('Prepared By', LBL), Paragraph(username or '—', N8)],
        [Paragraph('Narration', LBL), Paragraph(nar or '—', N8), Paragraph('Source', LBL), Paragraph(src, N8)],
    ]
    col_meta = [W * 0.14, W * 0.36, W * 0.14, W * 0.36]
    inf = Table(inf_rows, colWidths=col_meta, hAlign='LEFT')
    inf.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.5, BORDER),
        ('BACKGROUND', (0, 0), (-1, -1), BLUE_LIGHT),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), PAD),
        ('RIGHTPADDING', (0, 0), (-1, -1), PAD),
        ('TOPPADDING', (0, 0), (-1, -1), PAD),
        ('BOTTOMPADDING', (0, 0), (-1, -1), PAD),
        ('LINEBELOW', (0, 0), (-1, -1), 0.3, colors.HexColor('#dde3ea')),
    ]))
    elements.append(inf)
    elements.append(Spacer(1, 10))

    def _hw(txt: str) -> Paragraph:
        return Paragraph(f'<b>{txt}</b>', WHT)

    hdr_gl = ['Ln', 'Account', 'Account name', 'Party', 'Debit', 'Credit', 'Remarks']
    rows_gl: List[Any] = [[_hw(c) for c in hdr_gl]]
    for ln in voucher.get('lines') or []:
        try:
            lno = int(ln.get('line_no') or 0)
        except Exception:
            lno = 0
        ac = str(ln.get('account_code') or '')
        an = _trunc_pdf_text(ln.get('account_name'), 28)
        party_cell = _trunc_pdf_text(_party_display_label(ln), 22)
        dr = float(ln.get('debit') or 0)
        cr = float(ln.get('credit') or 0)
        rm = str(ln.get('remarks') or '').strip()
        if rm in ('—', '-'):
            rm = ''
        rm = _trunc_pdf_text(rm, 26)
        rows_gl.append([
            Paragraph(str(lno), N8C),
            Paragraph(ac, N8),
            Paragraph(str(an or ''), N8),
            Paragraph(str(party_cell), N8),
            Paragraph(f'{dr:.2f}' if dr else '—', N8R),
            Paragraph(f'{cr:.2f}' if cr else '—', N8R),
            Paragraph(str(rm or ''), N8),
        ])
    td = float(voucher.get('total_debit') or 0)
    tc = float(voucher.get('total_credit') or 0)
    bold_r = _s('jvb', parent=N8, fontName='Helvetica-Bold', alignment=TA_RIGHT)
    rows_gl.append([
        Paragraph('', N8), Paragraph('', N8), Paragraph('', N8),
        Paragraph('<b>Total</b>', _s('jvtot', parent=N8, fontName='Helvetica-Bold')),
        Paragraph(f'<b>{td:.2f}</b>', bold_r),
        Paragraph(f'<b>{tc:.2f}</b>', bold_r),
        Paragraph('', N8),
    ])
    frac = [0.05, 0.11, 0.25, 0.14, 0.115, 0.115, 0.22]
    cw_gl = [W * f for f in frac]
    cw_gl[-1] = W - sum(cw_gl[:-1])
    tbl_gl = Table(rows_gl, repeatRows=1, colWidths=cw_gl, hAlign='LEFT')
    tbl_gl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), BLUE),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.4, BORDER),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, GRAY_ROW]),
        ('BACKGROUND', (0, -1), (-1, -1), BLUE_LIGHT),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), PAD),
        ('BOTTOMPADDING', (0, 0), (-1, -1), PAD),
        ('LEFTPADDING', (0, 0), (-1, -1), PAD),
        ('RIGHTPADDING', (0, 0), (-1, -1), PAD),
    ]))
    elements.append(tbl_gl)
    elements.append(Spacer(1, 14))

    sig = Table(
        [[
            Paragraph('Prepared By', LBL),
            Paragraph('Verified By', LBL),
            Paragraph('Approved By', LBL),
        ], [
            Paragraph(username or '______________', N8),
            Paragraph('______________', N8),
            Paragraph('______________', N8),
        ]],
        colWidths=[W / 3.0] * 3,
        hAlign='LEFT',
    )
    sig.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(sig)
    elements.append(Spacer(1, 10))
    elements.append(Paragraph('Computer-generated journal voucher from GL.', FOOT))
    doc.build(elements)
    return buffer.getvalue()


def _trunc_pdf_text(s: object, max_len: int=48) -> str:
    t = str(s or '').strip()
    if len(t) <= max_len:
        return t
    return t[:max_len - 1] + '…'

def _party_display_label(ln: Dict[str, Any]) -> str:
    name = str((ln or {}).get('party_name') or '').strip()
    if name:
        return name
    pt = str((ln or {}).get('party_type') or '').strip()
    pc = str((ln or {}).get('party_code') or '').strip()
    if pt in ('', '—', '-'):
        pt = ''
    if pc in ('', '—', '-'):
        pc = ''
    if pt or pc:
        return f'{pt} {pc}'.strip()
    return '—'

def _build_account_ledger_pdf(account: dict, ledger: dict, date_from: str, date_to: str) -> bytes:
    """GL account ledger PDF — same layout system as purchase GRN (company header, blue bar, boxed meta, grid table)."""
    if not REPORTLAB_AVAILABLE:
        return b''
    from xml.sax.saxutils import escape as _xml_esc
    from addons.purchase.controllers.routes import _get_company_profile

    def _dmy(raw: str) -> str:
        s = (raw or '').strip()
        if not s or s == '—':
            return '—'
        try:
            return datetime.strptime(s[:10], '%Y-%m-%d').strftime('%d-%m-%Y')
        except Exception:
            return s[:12]
    company = _get_company_profile()
    code = str(account.get('code') or '')
    name = str(account.get('name') or '')
    acc_type = str(account.get('type') or '—')
    curr = str(account.get('currency') or 'QAR')
    company_name = str(company.get('name') or session.get('location_name') or '')
    company_address = str(company.get('address') or '')
    company_phone = str(company.get('phone') or '')
    company_email = str(company.get('email') or '')
    username = str(session.get('user') or '')
    tenant_logo_abs = ''
    if RLImage is not None:
        try:
            tid = str(session.get('tenant_id') or '').strip()
            if tid:
                t = get_tenant_by_id(tid) or {}
                logo_rel = str(t.get('logo_path') or '').strip()
                if logo_rel:
                    candidate = os.path.abspath(os.path.join(bp.root_path, '..', 'static', logo_rel))
                    if os.path.exists(candidate):
                        tenant_logo_abs = candidate
        except Exception:
            tenant_logo_abs = ''
    styles = getSampleStyleSheet()
    BLUE = colors.HexColor('#1a56a4')
    BLUE_LIGHT = colors.HexColor('#e8f0fb')
    BORDER = colors.HexColor('#b0b8c4')
    GRAY_ROW = colors.HexColor('#f7f8fa')
    TEXT = colors.HexColor('#1a1a1a')
    PAD = 5

    def _s(st_name, **kw):
        base = kw.pop('parent', styles['Normal'])
        kw.setdefault('textColor', TEXT)
        return ParagraphStyle(st_name, parent=base, **kw)
    N9 = _s('al9', fontSize=7.5, leading=9.5)
    N9R = _s('al9r', fontSize=7.5, leading=9.5, alignment=TA_RIGHT)
    N9C = _s('al9c', fontSize=7.5, leading=9.5, alignment=TA_CENTER)
    LBL = _s('albl', fontSize=7.5, leading=9.5, textColor=colors.HexColor('#555f6b'))
    SUB = _s('alsub', fontSize=7.5, leading=9.5, alignment=TA_CENTER, textColor=colors.HexColor('#555f6b'))
    WHT = _s('alwht', fontSize=7.5, leading=9.5, alignment=TA_CENTER, textColor=colors.white)
    FOOT = _s('alft', fontSize=6.5, leading=9, textColor=colors.HexColor('#888'))
    N8I = _s('al8i', fontSize=7, leading=9, fontName='Helvetica-Oblique')
    N9W = _s('al9w', fontSize=7.5, leading=9.5)
    W = 7.47 * inch
    LEFT_W = W * 0.57
    RIGHT_W = W - LEFT_W
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.45 * inch, bottomMargin=0.35 * inch, leftMargin=0.4 * inch, rightMargin=0.4 * inch)
    elements = []
    logo_cell: Any = ''
    if tenant_logo_abs and RLImage is not None:
        try:
            logo = RLImage(tenant_logo_abs)
            max_h = 0.75 * inch
            if getattr(logo, 'drawHeight', 0) and getattr(logo, 'drawWidth', 0):
                scale = min(max_h / float(logo.drawHeight), 2.0)
                logo.drawHeight = float(logo.drawHeight) * scale
                logo.drawWidth = float(logo.drawWidth) * scale
            logo.hAlign = 'LEFT'
            logo_cell = logo
        except Exception:
            logo_cell = ''
    company_lines = [Paragraph(f'<b>{company_name}</b>', _s('alcn', fontSize=10, leading=12.5, alignment=TA_CENTER, textColor=BLUE))]
    if company_address:
        company_lines.append(Paragraph(company_address, SUB))
    if company_phone:
        company_lines.append(Paragraph(f'Tel: {company_phone}', SUB))
    if company_email:
        company_lines.append(Paragraph(f'Email: {company_email}', SUB))
    if logo_cell:
        title_row = [[logo_cell, company_lines, '']]
        title_tbl = Table(title_row, colWidths=[0.95 * inch, W - 0.95 * inch, 0.01], hAlign='LEFT')
        title_tbl.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('ALIGN', (1, 0), (1, 0), 'CENTER'), ('LEFTPADDING', (0, 0), (-1, -1), PAD), ('RIGHTPADDING', (0, 0), (-1, -1), PAD), ('TOPPADDING', (0, 0), (-1, -1), PAD), ('BOTTOMPADDING', (0, 0), (-1, -1), PAD)]))
    else:
        title_tbl = Table([[company_lines]], colWidths=[W], hAlign='LEFT')
        title_tbl.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('ALIGN', (0, 0), (0, 0), 'CENTER'), ('TOPPADDING', (0, 0), (-1, -1), PAD), ('BOTTOMPADDING', (0, 0), (-1, -1), PAD), ('LEFTPADDING', (0, 0), (-1, -1), PAD), ('RIGHTPADDING', (0, 0), (-1, -1), PAD)]))
    elements.append(title_tbl)
    elements.append(Spacer(1, 2))
    elements.append(Paragraph('<b>ACCOUNT LEDGER</b>', _s('algt', fontSize=11, leading=14, alignment=TA_CENTER, textColor=BLUE)))
    elements.append(Spacer(1, 4))
    rule_tbl = Table([['']], colWidths=[W], rowHeights=[2], hAlign='LEFT')
    rule_tbl.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), BLUE)]))
    elements.append(rule_tbl)
    elements.append(Spacer(1, 6))

    def _info_row(label, value):
        return [Paragraph(label, LBL), Paragraph(str(value or ''), N9)]
    gen_ts = datetime.now().strftime('%d-%m-%Y %H:%M')
    acc_rows = [_info_row('Account Code', code), _info_row('Account Name', name), _info_row('Type', acc_type), _info_row('Currency', curr)]
    meta_right = [_info_row('Period From', _dmy(date_from)), _info_row('Period To', _dmy(date_to)), _info_row('Generated', gen_ts), _info_row('Prepared By', username or '—')]
    LBL_W = 1.1 * inch
    VAL_W = LEFT_W - LBL_W - 0.1 * inch
    LBL_W2 = 1.1 * inch
    VAL_W2 = RIGHT_W - LBL_W2 - 0.1 * inch
    sup_tbl = Table(acc_rows, colWidths=[LBL_W, VAL_W])
    sup_tbl.setStyle(TableStyle([('FONTSIZE', (0, 0), (-1, -1), 7.5), ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LINEBELOW', (0, 0), (-1, -2), 0.3, colors.HexColor('#dde3ea')), ('TOPPADDING', (0, 0), (-1, -1), PAD), ('BOTTOMPADDING', (0, 0), (-1, -1), PAD), ('LEFTPADDING', (0, 0), (-1, -1), PAD), ('RIGHTPADDING', (0, 0), (-1, -1), PAD)]))
    grn_meta_tbl = Table(meta_right, colWidths=[LBL_W2, VAL_W2])
    grn_meta_tbl.setStyle(TableStyle([('FONTSIZE', (0, 0), (-1, -1), 7.5), ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LINEBELOW', (0, 0), (-1, -2), 0.3, colors.HexColor('#dde3ea')), ('TOPPADDING', (0, 0), (-1, -1), PAD), ('BOTTOMPADDING', (0, 0), (-1, -1), PAD), ('LEFTPADDING', (0, 0), (-1, -1), PAD), ('RIGHTPADDING', (0, 0), (-1, -1), PAD)]))
    info_outer = Table([[sup_tbl, grn_meta_tbl]], colWidths=[LEFT_W, RIGHT_W], hAlign='LEFT')
    info_outer.setStyle(TableStyle([('BOX', (0, 0), (-1, -1), 0.5, BORDER), ('LINEBEFORE', (1, 0), (1, 0), 0.5, BORDER), ('BACKGROUND', (0, 0), (-1, -1), BLUE_LIGHT), ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), PAD), ('RIGHTPADDING', (0, 0), (-1, -1), PAD), ('TOPPADDING', (0, 0), (-1, -1), PAD), ('BOTTOMPADDING', (0, 0), (-1, -1), PAD)]))
    elements.append(info_outer)
    elements.append(Spacer(1, 8))

    def _hcell(txt):
        return Paragraph(f'<b>{txt}</b>', WHT)

    def _dcell(txt, align='LEFT'):
        st = N9R if align == 'RIGHT' else N9C if align == 'CENTER' else N9
        return Paragraph(str(txt), st)

    def _wrap_cell(txt):
        safe = _xml_esc(str(txt or '')).replace('\n', '<br/>')
        return Paragraph(safe or '—', N9W)

    ob = float(ledger.get('opening_balance') or 0)
    header_text = ['Date', 'Voucher', 'Reference', 'Narration', 'Source', 'Remarks', 'Debit', 'Credit', 'Balance']
    ob_row = ['—', '—', '—', 'Opening balance (before period)', '—', '—', '—', '—', f'{ob:.2f}']
    body_text_rows: list = [ob_row]
    for row in ledger.get('lines') or []:
        dr = float(row.get('debit') or 0)
        cr = float(row.get('credit') or 0)
        bal = float(row.get('running_balance') or 0)
        body_text_rows.append([
            str(row.get('voucher_date') or '')[:12],
            _trunc_pdf_text(row.get('voucher_no'), 22),
            _trunc_pdf_text(row.get('reference_no'), 12),
            str(row.get('narration') or ''),
            _trunc_pdf_text(row.get('source'), 14),
            str(row.get('remarks') or ''),
            f'{dr:.2f}' if dr else '—',
            f'{cr:.2f}' if cr else '—',
            f'{bal:.2f}',
        ])
    td = float(ledger.get('total_debit') or 0)
    tc = float(ledger.get('total_credit') or 0)
    cl = float(ledger.get('closing_balance') or 0)
    body_text_rows.append(['—', '—', '—', 'Period totals / closing balance', '—', '—', f'{td:.2f}', f'{tc:.2f}', f'{cl:.2f}'])
    pt_rows = [[_hcell(c) for c in header_text]]
    n_body = len(body_text_rows)
    for i, row in enumerate(body_text_rows):
        is_opening = i == 0
        is_closing = i == n_body - 1
        if is_opening:
            pt_rows.append([
                _dcell(row[0], 'CENTER'), _dcell(row[1], 'CENTER'), _dcell(row[2], 'CENTER'),
                Paragraph(str(row[3]), N8I), _dcell(row[4], 'CENTER'), _dcell(row[5], 'CENTER'),
                _dcell(row[6], 'RIGHT'), _dcell(row[7], 'RIGHT'), _dcell(row[8], 'RIGHT'),
            ])
        elif is_closing:
            b = _s('alb', parent=styles['Normal'], fontSize=7.5, leading=9.5, fontName='Helvetica-Bold', alignment=TA_RIGHT)
            pt_rows.append([
                _dcell(row[0], 'CENTER'), _dcell(row[1], 'CENTER'), _dcell(row[2], 'CENTER'),
                Paragraph(f'<b>{_xml_esc(str(row[3]))}</b>', _s('albd2', parent=N9, fontName='Helvetica-Bold')),
                _dcell(row[4], 'CENTER'), _dcell(row[5], 'CENTER'),
                Paragraph(f'<b>{str(row[6])}</b>', b), Paragraph(f'<b>{str(row[7])}</b>', b), Paragraph(f'<b>{str(row[8])}</b>', b),
            ])
        else:
            pt_rows.append([
                _dcell(row[0], 'CENTER'), _dcell(row[1], 'CENTER'), _dcell(row[2], 'CENTER'),
                _wrap_cell(row[3]), _dcell(row[4], 'CENTER'), _wrap_cell(row[5]),
                _dcell(row[6], 'RIGHT'), _dcell(row[7], 'RIGHT'), _dcell(row[8], 'RIGHT'),
            ])
    cw = [0.48, 0.85, 0.42, 1.85, 0.72, 1.35, 0.58, 0.58, 0.64]
    cw = [c * inch for c in cw]
    pt = Table(pt_rows, repeatRows=1, colWidths=cw, hAlign='LEFT')
    ts = [('BACKGROUND', (0, 0), (-1, 0), BLUE), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white), ('FONTSIZE', (0, 0), (-1, -1), 7.5), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('GRID', (0, 0), (-1, -1), 0.4, BORDER), ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, GRAY_ROW]), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('TOPPADDING', (0, 0), (-1, -1), PAD), ('BOTTOMPADDING', (0, 0), (-1, -1), PAD), ('LEFTPADDING', (0, 0), (-1, -1), PAD), ('RIGHTPADDING', (0, 0), (-1, -1), PAD)]
    nrows = len(pt_rows)
    ts.append(('BACKGROUND', (0, 1), (-1, 1), BLUE_LIGHT))
    if nrows > 2:
        ts.append(('BACKGROUND', (0, nrows - 1), (-1, nrows - 1), BLUE_LIGHT))
    pt.setStyle(TableStyle(ts))
    elements.append(pt)
    elements.append(Spacer(1, 8))
    elements.append(Paragraph('This is a computer-generated document. Amounts in functional currency. Balance is running after each line. No signature is required.', FOOT))
    doc.build(elements)
    return buffer.getvalue()

def _flatten_main_ledger_tree(node: Any, depth: int=0) -> list:
    """Rows for export: one dict per account node with depth, rollup, lines ref."""
    if not node:
        return []
    rows = []
    ru = node.get('rollup') or {}
    rows.append({'depth': depth, 'code': (node.get('code') or '').strip(), 'name': (node.get('name') or '').strip(), 'type': (node.get('type') or '').strip(), 'is_postable': bool(node.get('is_postable')), 'opening': float(ru.get('opening') or 0), 'debit': float(ru.get('debit') or 0), 'credit': float(ru.get('credit') or 0), 'closing': float(ru.get('closing') or 0)})
    for ch in node.get('children') or []:
        rows.extend(_flatten_main_ledger_tree(ch, depth + 1))
    return rows

def _collect_postable_ledger_nodes(node: Any, acc: list) -> None:
    if not node:
        return
    if node.get('is_postable') and (node.get('lines') or []):
        acc.append(node)
    for ch in node.get('children') or []:
        _collect_postable_ledger_nodes(ch, acc)

def _build_main_account_ledger_pdf(root: Any, date_from: str, date_to: str, root_code: str, root_name: str) -> bytes:
    """Main account ledger: tree rollups + GL detail for postable accounts (A4, same family as account ledger)."""
    if not REPORTLAB_AVAILABLE:
        return b''
    from xml.sax.saxutils import escape as _xml_esc
    from addons.purchase.controllers.routes import _get_company_profile
    _QATTR = {'"': '&quot;'}

    def _dmy(raw: str) -> str:
        s = (raw or '').strip()
        if not s or s == '—':
            return '—'
        try:
            return datetime.strptime(s[:10], '%Y-%m-%d').strftime('%d-%m-%Y')
        except Exception:
            return s[:12]
    company = _get_company_profile()
    company_name = str(company.get('name') or session.get('location_name') or '')
    company_address = str(company.get('address') or '')
    company_phone = str(company.get('phone') or '')
    company_email = str(company.get('email') or '')
    username = str(session.get('user') or '')
    tenant_logo_abs = ''
    if RLImage is not None:
        try:
            tid = str(session.get('tenant_id') or '').strip()
            if tid:
                t = get_tenant_by_id(tid) or {}
                logo_rel = str(t.get('logo_path') or '').strip()
                if logo_rel:
                    candidate = os.path.abspath(os.path.join(bp.root_path, '..', 'static', logo_rel))
                    if os.path.exists(candidate):
                        tenant_logo_abs = candidate
        except Exception:
            tenant_logo_abs = ''
    styles = getSampleStyleSheet()
    BLUE = colors.HexColor('#1a56a4')
    BLUE_LIGHT = colors.HexColor('#e8f0fb')
    BORDER = colors.HexColor('#b0b8c4')
    GRAY_ROW = colors.HexColor('#f7f8fa')
    TEXT = colors.HexColor('#1a1a1a')
    PAD = 4

    def _s(st_name, **kw):
        base = kw.pop('parent', styles['Normal'])
        kw.setdefault('textColor', TEXT)
        return ParagraphStyle(st_name, parent=base, **kw)
    N8 = _s('mal8', fontSize=7, leading=9)
    N8R = _s('mal8r', fontSize=7, leading=9, alignment=TA_RIGHT)
    N8B = _s('mal8b', fontSize=7, leading=9, fontName='Helvetica-Bold')
    WHT = _s('malw', fontSize=7, leading=9, textColor=colors.white, alignment=TA_CENTER, fontName='Helvetica-Bold')
    SUB = _s('malsub', fontSize=7, leading=9, alignment=TA_CENTER, textColor=colors.HexColor('#555f6b'))
    FOOT = _s('malft', fontSize=6.5, leading=9, textColor=colors.HexColor('#888'))
    TIT = _s('maltit', fontSize=11, leading=14, alignment=TA_CENTER, textColor=BLUE, fontName='Helvetica-Bold')
    N7 = _s('mal7', fontSize=6.5, leading=8.5)
    N7R = _s('mal7r', fontSize=6.5, leading=8.5, alignment=TA_RIGHT)
    W = 7.47 * inch
    LEFT_W = W * 0.56
    RIGHT_W = W - LEFT_W
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.45 * inch, bottomMargin=0.4 * inch, leftMargin=0.4 * inch, rightMargin=0.4 * inch)
    elements: list = []
    logo_cell: Any = ''
    if tenant_logo_abs and RLImage is not None:
        try:
            logo = RLImage(tenant_logo_abs)
            max_h = 0.7 * inch
            if getattr(logo, 'drawHeight', 0) and getattr(logo, 'drawWidth', 0):
                scale = min(max_h / float(logo.drawHeight), 2.0)
                logo.drawHeight = float(logo.drawHeight) * scale
                logo.drawWidth = float(logo.drawWidth) * scale
            logo.hAlign = 'LEFT'
            logo_cell = logo
        except Exception:
            logo_cell = ''
    company_lines = [Paragraph(f'<b>{_xml_esc(company_name, _QATTR)}</b>', _s('malc', fontSize=10, leading=12.5, alignment=TA_CENTER, textColor=BLUE))]
    if company_address:
        company_lines.append(Paragraph(_xml_esc(company_address, _QATTR), SUB))
    if company_phone:
        company_lines.append(Paragraph(f'Tel: {_xml_esc(company_phone, _QATTR)}', SUB))
    if company_email:
        company_lines.append(Paragraph(f'Email: {_xml_esc(company_email, _QATTR)}', SUB))
    if logo_cell:
        title_tbl = Table([[logo_cell, company_lines, '']], colWidths=[0.9 * inch, W - 0.9 * inch, 0.01], hAlign='LEFT')
        title_tbl.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('ALIGN', (1, 0), (1, 0), 'CENTER'), ('TOPPADDING', (0, 0), (-1, -1), PAD), ('BOTTOMPADDING', (0, 0), (-1, -1), PAD), ('LEFTPADDING', (0, 0), (-1, -1), PAD)]))
    else:
        title_tbl = Table([[company_lines]], colWidths=[W], hAlign='LEFT')
        title_tbl.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('ALIGN', (0, 0), (0, 0), 'CENTER'), ('TOPPADDING', (0, 0), (-1, -1), PAD)]))
    elements.append(title_tbl)
    elements.append(Spacer(1, 2))
    elements.append(Paragraph('MAIN ACCOUNT LEDGER (TREE)', TIT))
    elements.append(Spacer(1, 2))
    rule = Table([['']], colWidths=[W], rowHeights=[2], hAlign='LEFT')
    rule.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), BLUE)]))
    elements.append(rule)
    elements.append(Spacer(1, 5))

    def _info_row(lbl, val):
        return [Paragraph(f'<b>{_xml_esc(lbl, _QATTR)}</b>', _s('mall', fontSize=7, textColor=colors.HexColor('#555f6b'))), Paragraph(_xml_esc(str(val or '—'), _QATTR), N8)]
    gen_ts = datetime.now().strftime('%d-%m-%Y %H:%M')
    l_rows = [_info_row('Root account (code)', root_code), _info_row('Root name', root_name)]
    r_rows = [_info_row('Period from', _dmy(str(date_from or ''))), _info_row('Period to', _dmy(str(date_to or ''))), _info_row('Generated', gen_ts), _info_row('Prepared by', username or '—')]
    LBL_W, LBL_W2 = (1.05 * inch, 1.05 * inch)
    VAL_W = LEFT_W - LBL_W - 0.08 * inch
    VAL_W2 = RIGHT_W - LBL_W2 - 0.08 * inch
    t_left = Table(l_rows, colWidths=[LBL_W, VAL_W])
    t_left.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LINEBELOW', (0, 0), (-1, -2), 0.25, colors.HexColor('#dde3ea')), ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3)]))
    t_right = Table(r_rows, colWidths=[LBL_W2, VAL_W2])
    t_right.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LINEBELOW', (0, 0), (-1, -2), 0.25, colors.HexColor('#dde3ea')), ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3)]))
    box = Table([[t_left, t_right]], colWidths=[LEFT_W, RIGHT_W], hAlign='LEFT')
    box.setStyle(TableStyle([('BOX', (0, 0), (-1, -1), 0.5, BORDER), ('LINEBEFORE', (1, 0), (1, 0), 0.5, BORDER), ('BACKGROUND', (0, 0), (-1, -1), BLUE_LIGHT), ('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    elements.append(box)
    elements.append(Spacer(1, 8))
    elements.append(Paragraph('<b>Account tree — roll-up balances (debit − credit)</b>', _s('malh2', parent=N8, fontName='Helvetica-Bold', fontSize=8.5, textColor=BLUE)))
    elements.append(Spacer(1, 4))
    htree = ['Account', 'Type', 'Kind', 'Opening', 'Debit', 'Credit', 'Closing']
    tr_pdf: list = [[Paragraph(f'<b>{_xml_esc(c, _QATTR)}</b>', WHT) for c in htree]]

    def _tree_rows(n: Any, d: int) -> None:
        nonlocal tr_pdf
        ru = n.get('rollup') or {}
        kind = 'Postable' if n.get('is_postable') else 'Group'
        c = (n.get('code') or '').strip()
        nm = (n.get('name') or '').strip()
        typ = (n.get('type') or '—').strip()
        ind = '· ' * d
        ac_text = f'{ind}<b>{_xml_esc(c, _QATTR)}</b>  {_xml_esc(nm, _QATTR)}  <i>({kind})</i>'
        tr_pdf.append([Paragraph(ac_text, N7), Paragraph(_xml_esc(typ, _QATTR), N7), Paragraph(_xml_esc(kind, _QATTR), N7), Paragraph(f"{float(ru.get('opening') or 0):.2f}", N7R), Paragraph(f"{float(ru.get('debit') or 0):.2f}", N7R), Paragraph(f"{float(ru.get('credit') or 0):.2f}", N7R), Paragraph(f"{float(ru.get('closing') or 0):.2f}", N7R)])
        for ch in n.get('children') or []:
            _tree_rows(ch, d + 1)
    _tree_rows(root, 0)
    ctw = [2.85, 0.7, 0.62, 0.8, 0.75, 0.75, 0.8]
    ctw = [c * inch for c in ctw]
    tt = Table(tr_pdf, repeatRows=1, colWidths=ctw, hAlign='LEFT')
    ts_tree = [('BACKGROUND', (0, 0), (-1, 0), BLUE), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white), ('FONTSIZE', (0, 0), (-1, -1), 6.5), ('GRID', (0, 0), (-1, -1), 0.3, BORDER), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, GRAY_ROW]), ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2)]
    tt.setStyle(TableStyle(ts_tree))
    elements.append(tt)
    post_nodes: list = []
    _collect_postable_ledger_nodes(root, post_nodes)
    if post_nodes:
        elements.append(Spacer(1, 10))
        elements.append(Paragraph('<b>GL line detail (postable accounts, selected period)</b>', _s('malh3', parent=N8, fontName='Helvetica-Bold', fontSize=8.5, textColor=BLUE)))
        elements.append(Spacer(1, 4))
        for pn in post_nodes:
            code_p = (pn.get('code') or '').strip()
            name_p = (pn.get('name') or '').strip()
            elements.append(Spacer(1, 3))
            elements.append(Paragraph(f"<b>{_xml_esc(code_p, _QATTR)}</b>  {_xml_esc(name_p, _QATTR)} &nbsp; <i>({len(pn.get('lines') or [])} lines)</i>", N8B))
            elements.append(Spacer(1, 2))
            det_h = ['Date', 'Voucher', 'Ref', 'Narration', 'Source', 'Dr', 'Cr', 'Balance']
            drows: list = [[Paragraph(f'<b>{_xml_esc(x, _QATTR)}</b>', WHT) for x in det_h]]
            for ln in pn.get('lines') or []:
                dr = float(ln.get('debit') or 0)
                cr = float(ln.get('credit') or 0)
                bal = float(ln.get('running_balance') or 0)
                drows.append([Paragraph(_xml_esc(str(ln.get('voucher_date') or '')[:12], _QATTR), N7), Paragraph(_xml_esc(_trunc_pdf_text(ln.get('voucher_no'), 18), _QATTR), N7), Paragraph(_xml_esc(_trunc_pdf_text(ln.get('reference_no'), 10), _QATTR), N7), Paragraph(_xml_esc(_trunc_pdf_text(ln.get('narration'), 34), _QATTR), N7), Paragraph(_xml_esc(_trunc_pdf_text(ln.get('source'), 12), _QATTR), N7), Paragraph(f'{dr:.2f}' if dr else '—', N7R), Paragraph(f'{cr:.2f}' if cr else '—', N7R), Paragraph(f'{bal:.2f}', N7R)])
            cvd = [0.5, 0.85, 0.42, 2.5, 0.75, 0.62, 0.62, 0.71]
            cvd = [c * inch for c in cvd]
            dtbl = Table(drows, repeatRows=1, colWidths=cvd, hAlign='LEFT')
            dtbl.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a56a4')), ('FONTSIZE', (0, 0), (-1, -1), 6.5), ('GRID', (0, 0), (-1, -1), 0.3, BORDER), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, GRAY_ROW]), ('TOPPADDING', (0, 0), (-1, -1), 1)]))
            elements.append(dtbl)
    elements.append(Spacer(1, 8))
    elements.append(Paragraph("Computer-generated main account ledger. Group rows aggregate descendant postable accounts. Postable rows show that account's own GL in the period. No signature is required.", FOOT))
    doc.build(elements)
    return buffer.getvalue()

def _build_main_account_ledger_excel(root: Any, date_from: str, date_to: str, root_code: str, root_name: str) -> Optional[bytes]:
    """XLSX: sheets Tree summary and GL lines (all postable detail)."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
    except ImportError:
        return None
    wb = Workbook()
    thin = Side(style='thin', color='CCCCCC')
    box = Border(left=thin, right=thin, top=thin, bottom=thin)
    hdr_fill = PatternFill(start_color='1a56a4', end_color='1a56a4', fill_type='solid')
    hdr_font = Font(bold=True, color='FFFFFF', size=10)
    ws = wb.active
    ws.title = 'Tree summary'
    ws['A1'] = 'Main account ledger — tree (roll-up balances)'
    ws['A1'].font = Font(bold=True, size=12, color='1a56a4')
    ws.merge_cells('A1:I1')
    ws['A2'] = f'Root: {root_code} — {root_name}'
    ws['A3'] = f"Period: {date_from or '—'} to {date_to or '—'}"
    ws['A4'] = f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    hrow = 6
    headers = ['Level', 'Code', 'Name', 'Type', 'Kind', 'Opening', 'Debit', 'Credit', 'Closing']
    for c, h in enumerate(headers, 1):
        cell = ws.cell(row=hrow, column=c, value=h)
        cell.fill = hdr_fill
        cell.font = hdr_font
        cell.alignment = Alignment(horizontal='center' if c >= 4 else 'left', wrap_text=True)
        cell.border = box
    flat = _flatten_main_ledger_tree(root, 0)
    for i, r in enumerate(flat, start=hrow + 1):
        ws.cell(row=i, column=1, value=r.get('depth', 0))
        ws.cell(row=i, column=2, value=r.get('code', ''))
        ws.cell(row=i, column=3, value=r.get('name', ''))
        ws.cell(row=i, column=4, value=r.get('type', ''))
        ws.cell(row=i, column=5, value='Postable' if r.get('is_postable') else 'Group')
        ws.cell(row=i, column=6, value=round(r.get('opening', 0), 2))
        ws.cell(row=i, column=7, value=round(r.get('debit', 0), 2))
        ws.cell(row=i, column=8, value=round(r.get('credit', 0), 2))
        ws.cell(row=i, column=9, value=round(r.get('closing', 0), 2))
        for c in range(1, 10):
            ws.cell(row=i, column=c).border = box
            if c >= 6:
                ws.cell(row=i, column=c).alignment = Alignment(horizontal='right')
    for col in range(1, 10):
        ws.column_dimensions[get_column_letter(col)].width = 14 if col == 3 else 11
    ws.column_dimensions['C'].width = 28
    w2 = wb.create_sheet('GL lines', 1)
    w2['A1'] = 'All GL lines — postable accounts under root (selected period)'
    w2['A1'].font = Font(bold=True, size=12, color='1a56a4')
    w2.merge_cells('A1:J1')
    w2h = ['Account code', 'Account name', 'Date', 'Voucher', 'Reference', 'Narration', 'Source', 'Debit', 'Credit', 'Running balance']
    hr2 = 3
    for c, h in enumerate(w2h, 1):
        cell = w2.cell(row=hr2, column=c, value=h)
        cell.fill = hdr_fill
        cell.font = hdr_font
        cell.border = box
    rr = hr2 + 1
    post_n: list = []
    _collect_postable_ledger_nodes(root, post_n)
    for pn in post_n:
        ac = (pn.get('code') or '').strip()
        anm = (pn.get('name') or '').strip()
        for ln in pn.get('lines') or []:
            w2.cell(row=rr, column=1, value=ac)
            w2.cell(row=rr, column=2, value=anm)
            w2.cell(row=rr, column=3, value=str(ln.get('voucher_date') or ''))
            w2.cell(row=rr, column=4, value=str(ln.get('voucher_no') or ''))
            w2.cell(row=rr, column=5, value=str(ln.get('reference_no') or ''))
            w2.cell(row=rr, column=6, value=str(ln.get('narration') or ''))
            w2.cell(row=rr, column=7, value=str(ln.get('source') or ''))
            w2.cell(row=rr, column=8, value=round(float(ln.get('debit') or 0), 2))
            w2.cell(row=rr, column=9, value=round(float(ln.get('credit') or 0), 2))
            w2.cell(row=rr, column=10, value=round(float(ln.get('running_balance') or 0), 2))
            for c in range(1, 11):
                w2.cell(row=rr, column=c).border = box
            w2.cell(row=rr, column=8).alignment = Alignment(horizontal='right')
            w2.cell(row=rr, column=9).alignment = Alignment(horizontal='right')
            w2.cell(row=rr, column=10).alignment = Alignment(horizontal='right')
            rr += 1
    for col in range(1, 11):
        w2.column_dimensions[get_column_letter(col)].width = 18 if col in (2, 6) else 12
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

def _build_supplier_ledger_pdf(supplier: dict, ledger: dict, date_from: str, date_to: str) -> bytes:
    """Supplier GL sub-ledger PDF (party-tagged lines) — same layout as :func:`_build_account_ledger_pdf` with an Account column."""
    if not REPORTLAB_AVAILABLE:
        return b''
    from addons.purchase.controllers.routes import _get_company_profile

    def _dmy(raw: str) -> str:
        s = (raw or '').strip()
        if not s or s == '—':
            return '—'
        try:
            return datetime.strptime(s[:10], '%Y-%m-%d').strftime('%d-%m-%Y')
        except Exception:
            return s[:12]
    company = _get_company_profile()
    s_code = str(supplier.get('suppliercode') or supplier.get('code') or '')
    s_name = str(supplier.get('suppliername') or supplier.get('name') or '—')
    s_pay = str(supplier.get('payableaccount') or '—')
    s_loc = str(supplier.get('locationcode') or '')
    company_name = str(company.get('name') or session.get('location_name') or '')
    company_address = str(company.get('address') or '')
    company_phone = str(company.get('phone') or '')
    company_email = str(company.get('email') or '')
    username = str(session.get('user') or '')
    tenant_logo_abs = ''
    if RLImage is not None:
        try:
            tid = str(session.get('tenant_id') or '').strip()
            if tid:
                t = get_tenant_by_id(tid) or {}
                logo_rel = str(t.get('logo_path') or '').strip()
                if logo_rel:
                    candidate = os.path.abspath(os.path.join(bp.root_path, '..', 'static', logo_rel))
                    if os.path.exists(candidate):
                        tenant_logo_abs = candidate
        except Exception:
            tenant_logo_abs = ''
    styles = getSampleStyleSheet()
    BLUE = colors.HexColor('#1a56a4')
    BLUE_LIGHT = colors.HexColor('#e8f0fb')
    BORDER = colors.HexColor('#b0b8c4')
    GRAY_ROW = colors.HexColor('#f7f8fa')
    TEXT = colors.HexColor('#1a1a1a')
    PAD = 5

    def _s(st_name, **kw):
        base = kw.pop('parent', styles['Normal'])
        kw.setdefault('textColor', TEXT)
        return ParagraphStyle(st_name, parent=base, **kw)
    N9 = _s('sl9', fontSize=7.5, leading=9.5)
    N9R = _s('sl9r', fontSize=7.5, leading=9.5, alignment=TA_RIGHT)
    N9C = _s('sl9c', fontSize=7.5, leading=9.5, alignment=TA_CENTER)
    LBL = _s('slbl', fontSize=7.5, leading=9.5, textColor=colors.HexColor('#555f6b'))
    SUB = _s('slsub', fontSize=7.5, leading=9.5, alignment=TA_CENTER, textColor=colors.HexColor('#555f6b'))
    WHT = _s('slwht', fontSize=7.5, leading=9.5, alignment=TA_CENTER, textColor=colors.white)
    FOOT = _s('slft', fontSize=6.5, leading=9, textColor=colors.HexColor('#888'))
    N8I = _s('sl8i', fontSize=7, leading=9, fontName='Helvetica-Oblique')
    W = 7.47 * inch
    LEFT_W = W * 0.57
    RIGHT_W = W - LEFT_W
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.45 * inch, bottomMargin=0.35 * inch, leftMargin=0.4 * inch, rightMargin=0.4 * inch)
    elements = []
    logo_cell: Any = ''
    if tenant_logo_abs and RLImage is not None:
        try:
            logo = RLImage(tenant_logo_abs)
            max_h = 0.75 * inch
            if getattr(logo, 'drawHeight', 0) and getattr(logo, 'drawWidth', 0):
                scale = min(max_h / float(logo.drawHeight), 2.0)
                logo.drawHeight = float(logo.drawHeight) * scale
                logo.drawWidth = float(logo.drawWidth) * scale
            logo.hAlign = 'LEFT'
            logo_cell = logo
        except Exception:
            logo_cell = ''
    company_lines = [Paragraph(f'<b>{company_name}</b>', _s('slcn', fontSize=10, leading=12.5, alignment=TA_CENTER, textColor=BLUE))]
    if company_address:
        company_lines.append(Paragraph(company_address, SUB))
    if company_phone:
        company_lines.append(Paragraph(f'Tel: {company_phone}', SUB))
    if company_email:
        company_lines.append(Paragraph(f'Email: {company_email}', SUB))
    if logo_cell:
        title_row = [[logo_cell, company_lines, '']]
        title_tbl = Table(title_row, colWidths=[0.95 * inch, W - 0.95 * inch, 0.01], hAlign='LEFT')
        title_tbl.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('ALIGN', (1, 0), (1, 0), 'CENTER'), ('LEFTPADDING', (0, 0), (-1, -1), PAD), ('RIGHTPADDING', (0, 0), (-1, -1), PAD), ('TOPPADDING', (0, 0), (-1, -1), PAD), ('BOTTOMPADDING', (0, 0), (-1, -1), PAD)]))
    else:
        title_tbl = Table([[company_lines]], colWidths=[W], hAlign='LEFT')
        title_tbl.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('ALIGN', (0, 0), (0, 0), 'CENTER'), ('TOPPADDING', (0, 0), (-1, -1), PAD), ('BOTTOMPADDING', (0, 0), (-1, -1), PAD), ('LEFTPADDING', (0, 0), (-1, -1), PAD), ('RIGHTPADDING', (0, 0), (-1, -1), PAD)]))
    elements.append(title_tbl)
    elements.append(Spacer(1, 2))
    elements.append(Paragraph('<b>SUPPLIER LEDGER</b>', _s('slgt', fontSize=11, leading=14, alignment=TA_CENTER, textColor=BLUE)))
    elements.append(Spacer(1, 4))
    rule_tbl = Table([['']], colWidths=[W], rowHeights=[2], hAlign='LEFT')
    rule_tbl.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), BLUE)]))
    elements.append(rule_tbl)
    elements.append(Spacer(1, 6))

    def _info_row(label, value):
        return [Paragraph(label, LBL), Paragraph(str(value or ''), N9)]
    gen_ts = datetime.now().strftime('%d-%m-%Y %H:%M')
    acc_rows = [_info_row('Supplier Code', s_code or '—'), _info_row('Supplier Name', s_name or '—'), _info_row('Payable Account', s_pay or '—')]
    acc_rows.append(_info_row('GL lines shown', 'Liability accounts only (same basis as Accounts Payable list balance)'))
    if s_loc:
        acc_rows.append(_info_row('Location', s_loc))
    meta_right = [_info_row('Period From', _dmy(date_from)), _info_row('Period To', _dmy(date_to)), _info_row('Generated', gen_ts), _info_row('Prepared By', username or '—')]
    LBL_W = 1.1 * inch
    VAL_W = LEFT_W - LBL_W - 0.1 * inch
    LBL_W2 = 1.1 * inch
    VAL_W2 = RIGHT_W - LBL_W2 - 0.1 * inch
    sup_tbl = Table(acc_rows, colWidths=[LBL_W, VAL_W])
    sup_tbl.setStyle(TableStyle([('FONTSIZE', (0, 0), (-1, -1), 7.5), ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LINEBELOW', (0, 0), (-1, -2), 0.3, colors.HexColor('#dde3ea')), ('TOPPADDING', (0, 0), (-1, -1), PAD), ('BOTTOMPADDING', (0, 0), (-1, -1), PAD), ('LEFTPADDING', (0, 0), (-1, -1), PAD), ('RIGHTPADDING', (0, 0), (-1, -1), PAD)]))
    grn_meta_tbl = Table(meta_right, colWidths=[LBL_W2, VAL_W2])
    grn_meta_tbl.setStyle(TableStyle([('FONTSIZE', (0, 0), (-1, -1), 7.5), ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LINEBELOW', (0, 0), (-1, -2), 0.3, colors.HexColor('#dde3ea')), ('TOPPADDING', (0, 0), (-1, -1), PAD), ('BOTTOMPADDING', (0, 0), (-1, -1), PAD), ('LEFTPADDING', (0, 0), (-1, -1), PAD), ('RIGHTPADDING', (0, 0), (-1, -1), PAD)]))
    info_outer = Table([[sup_tbl, grn_meta_tbl]], colWidths=[LEFT_W, RIGHT_W], hAlign='LEFT')
    info_outer.setStyle(TableStyle([('BOX', (0, 0), (-1, -1), 0.5, BORDER), ('LINEBEFORE', (1, 0), (1, 0), 0.5, BORDER), ('BACKGROUND', (0, 0), (-1, -1), BLUE_LIGHT), ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), PAD), ('RIGHTPADDING', (0, 0), (-1, -1), PAD), ('TOPPADDING', (0, 0), (-1, -1), PAD), ('BOTTOMPADDING', (0, 0), (-1, -1), PAD)]))
    elements.append(info_outer)
    elements.append(Spacer(1, 8))

    def _hcell(txt):
        return Paragraph(f'<b>{txt}</b>', WHT)

    def _dcell(txt, align='LEFT'):
        st = N9R if align == 'RIGHT' else N9C if align == 'CENTER' else N9
        return Paragraph(str(txt), st)
    ob = float(ledger.get('opening_balance') or 0)
    header_text = ['Date', 'Voucher', 'Ref', 'GL A/c', 'Narration', 'Source', 'Debit', 'Credit', 'Balance']
    ob_row = ['—', '—', '—', '—', 'Opening balance (before period)', '—', '—', '—', f'{ob:.2f}']
    body_text_rows: list = [ob_row]
    for row in ledger.get('lines') or []:
        dr = float(row.get('debit') or 0)
        cr = float(row.get('credit') or 0)
        bal = float(row.get('running_balance') or 0)
        body_text_rows.append([str(row.get('voucher_date') or '')[:12], _trunc_pdf_text(row.get('voucher_no'), 18), _trunc_pdf_text(row.get('reference_no'), 10), _trunc_pdf_text(row.get('account_code'), 8), _trunc_pdf_text(row.get('narration'), 28), _trunc_pdf_text(row.get('source'), 10), f'{dr:.2f}' if dr else '—', f'{cr:.2f}' if cr else '—', f'{bal:.2f}'])
    td = float(ledger.get('total_debit') or 0)
    tc = float(ledger.get('total_credit') or 0)
    cl = float(ledger.get('closing_balance') or 0)
    body_text_rows.append(['—', '—', '—', '—', 'Period totals / closing balance', '—', f'{td:.2f}', f'{tc:.2f}', f'{cl:.2f}'])
    pt_rows = [[_hcell(c) for c in header_text]]
    n_body = len(body_text_rows)
    for i, row in enumerate(body_text_rows):
        is_opening = i == 0
        is_closing = i == n_body - 1
        if is_opening:
            pt_rows.append([_dcell(row[0], 'CENTER'), _dcell(row[1], 'CENTER'), _dcell(row[2], 'CENTER'), _dcell(row[3], 'CENTER'), Paragraph(str(row[4]), N8I), _dcell(row[5], 'CENTER'), _dcell(row[6], 'RIGHT'), _dcell(row[7], 'RIGHT'), _dcell(row[8], 'RIGHT')])
        elif is_closing:
            b = _s('slb', parent=styles['Normal'], fontSize=7.5, leading=9.5, fontName='Helvetica-Bold', alignment=TA_RIGHT)
            pt_rows.append([_dcell(row[0], 'CENTER'), _dcell(row[1], 'CENTER'), _dcell(row[2], 'CENTER'), _dcell(row[3], 'CENTER'), Paragraph(f'<b>{str(row[4])}</b>', _s('slbd2', parent=N9, fontName='Helvetica-Bold')), _dcell(row[5], 'CENTER'), Paragraph(f'<b>{str(row[6])}</b>', b), Paragraph(f'<b>{str(row[7])}</b>', b), Paragraph(f'<b>{str(row[8])}</b>', b)])
        else:
            pt_rows.append([_dcell(row[0], 'CENTER'), _dcell(row[1], 'CENTER'), _dcell(row[2], 'CENTER'), _dcell(row[3], 'CENTER'), _dcell(row[4]), _dcell(row[5], 'CENTER'), _dcell(row[6], 'RIGHT'), _dcell(row[7], 'RIGHT'), _dcell(row[8], 'RIGHT')])
    cw = [0.4, 0.75, 0.4, 0.5, 3.1, 0.46, 0.6, 0.6, 0.66]
    cw = [c * inch for c in cw]
    pt = Table(pt_rows, repeatRows=1, colWidths=cw, hAlign='LEFT')
    ts = [('BACKGROUND', (0, 0), (-1, 0), BLUE), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white), ('FONTSIZE', (0, 0), (-1, -1), 7.5), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('GRID', (0, 0), (-1, -1), 0.4, BORDER), ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, GRAY_ROW]), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('TOPPADDING', (0, 0), (-1, -1), PAD), ('BOTTOMPADDING', (0, 0), (-1, -1), PAD), ('LEFTPADDING', (0, 0), (-1, -1), PAD), ('RIGHTPADDING', (0, 0), (-1, -1), PAD)]
    nrows = len(pt_rows)
    ts.append(('BACKGROUND', (0, 1), (-1, 1), BLUE_LIGHT))
    if nrows > 2:
        ts.append(('BACKGROUND', (0, nrows - 1), (-1, nrows - 1), BLUE_LIGHT))
    pt.setStyle(TableStyle(ts))
    elements.append(pt)
    elements.append(Spacer(1, 8))
    elements.append(Paragraph('This is a computer-generated document. Lines are GL_VOUCHER_DTL with PARTY_TYPE=SUPPLIER. Balance is running (credit − debit) after each line. No signature is required.', FOOT))
    doc.build(elements)
    return buffer.getvalue()

def _build_customer_ledger_pdf(customer: dict, ledger: dict, date_from: str, date_to: str) -> bytes:
    """Customer GL sub-ledger PDF (party-tagged ASSET lines) — same layout as supplier ledger with Dr−Cr balance."""
    if not REPORTLAB_AVAILABLE:
        return b''
    from addons.purchase.controllers.routes import _get_company_profile

    def _dmy(raw: str) -> str:
        s = (raw or '').strip()
        if not s or s == '—':
            return '—'
        try:
            return datetime.strptime(s[:10], '%Y-%m-%d').strftime('%d-%m-%Y')
        except Exception:
            return s[:12]
    company = _get_company_profile()
    c_code = str(customer.get('customercode') or customer.get('code') or '')
    c_name = str(customer.get('customername') or customer.get('name') or '—')
    c_recv = str(customer.get('receivableaccount') or '—')
    company_name = str(company.get('name') or session.get('location_name') or '')
    company_address = str(company.get('address') or '')
    company_phone = str(company.get('phone') or '')
    company_email = str(company.get('email') or '')
    username = str(session.get('user') or '')
    tenant_logo_abs = ''
    if RLImage is not None:
        try:
            tid = str(session.get('tenant_id') or '').strip()
            if tid:
                t = get_tenant_by_id(tid) or {}
                logo_rel = str(t.get('logo_path') or '').strip()
                if logo_rel:
                    candidate = os.path.abspath(os.path.join(bp.root_path, '..', 'static', logo_rel))
                    if os.path.exists(candidate):
                        tenant_logo_abs = candidate
        except Exception:
            tenant_logo_abs = ''
    styles = getSampleStyleSheet()
    BLUE = colors.HexColor('#1a56a4')
    BLUE_LIGHT = colors.HexColor('#e8f0fb')
    BORDER = colors.HexColor('#b0b8c4')
    GRAY_ROW = colors.HexColor('#f7f8fa')
    TEXT = colors.HexColor('#1a1a1a')
    PAD = 5

    def _s(st_name, **kw):
        base = kw.pop('parent', styles['Normal'])
        kw.setdefault('textColor', TEXT)
        return ParagraphStyle(st_name, parent=base, **kw)
    N9 = _s('cl9', fontSize=7.5, leading=9.5)
    N9R = _s('cl9r', fontSize=7.5, leading=9.5, alignment=TA_RIGHT)
    N9C = _s('cl9c', fontSize=7.5, leading=9.5, alignment=TA_CENTER)
    LBL = _s('clbl', fontSize=7.5, leading=9.5, textColor=colors.HexColor('#555f6b'))
    SUB = _s('clsub', fontSize=7.5, leading=9.5, alignment=TA_CENTER, textColor=colors.HexColor('#555f6b'))
    WHT = _s('clwht', fontSize=7.5, leading=9.5, alignment=TA_CENTER, textColor=colors.white)
    FOOT = _s('clft', fontSize=6.5, leading=9, textColor=colors.HexColor('#888'))
    N8I = _s('cl8i', fontSize=7, leading=9, fontName='Helvetica-Oblique')
    W = 7.47 * inch
    LEFT_W = W * 0.57
    RIGHT_W = W - LEFT_W
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.45 * inch, bottomMargin=0.35 * inch, leftMargin=0.4 * inch, rightMargin=0.4 * inch)
    elements = []
    logo_cell: Any = ''
    if tenant_logo_abs and RLImage is not None:
        try:
            logo = RLImage(tenant_logo_abs)
            max_h = 0.75 * inch
            if getattr(logo, 'drawHeight', 0) and getattr(logo, 'drawWidth', 0):
                scale = min(max_h / float(logo.drawHeight), 2.0)
                logo.drawHeight = float(logo.drawHeight) * scale
                logo.drawWidth = float(logo.drawWidth) * scale
            logo.hAlign = 'LEFT'
            logo_cell = logo
        except Exception:
            logo_cell = ''
    company_lines = [Paragraph(f'<b>{company_name}</b>', _s('clcn', fontSize=10, leading=12.5, alignment=TA_CENTER, textColor=BLUE))]
    if company_address:
        company_lines.append(Paragraph(company_address, SUB))
    if company_phone:
        company_lines.append(Paragraph(f'Tel: {company_phone}', SUB))
    if company_email:
        company_lines.append(Paragraph(f'Email: {company_email}', SUB))
    if logo_cell:
        title_row = [[logo_cell, company_lines, '']]
        title_tbl = Table(title_row, colWidths=[0.95 * inch, W - 0.95 * inch, 0.01], hAlign='LEFT')
        title_tbl.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('ALIGN', (1, 0), (1, 0), 'CENTER'), ('LEFTPADDING', (0, 0), (-1, -1), PAD), ('RIGHTPADDING', (0, 0), (-1, -1), PAD), ('TOPPADDING', (0, 0), (-1, -1), PAD), ('BOTTOMPADDING', (0, 0), (-1, -1), PAD)]))
    else:
        title_tbl = Table([[company_lines]], colWidths=[W], hAlign='LEFT')
        title_tbl.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('ALIGN', (0, 0), (0, 0), 'CENTER'), ('TOPPADDING', (0, 0), (-1, -1), PAD), ('BOTTOMPADDING', (0, 0), (-1, -1), PAD), ('LEFTPADDING', (0, 0), (-1, -1), PAD), ('RIGHTPADDING', (0, 0), (-1, -1), PAD)]))
    elements.append(title_tbl)
    elements.append(Spacer(1, 2))
    elements.append(Paragraph('<b>CUSTOMER LEDGER</b>', _s('clgt', fontSize=11, leading=14, alignment=TA_CENTER, textColor=BLUE)))
    elements.append(Spacer(1, 4))
    rule_tbl = Table([['']], colWidths=[W], rowHeights=[2], hAlign='LEFT')
    rule_tbl.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), BLUE)]))
    elements.append(rule_tbl)
    elements.append(Spacer(1, 6))

    def _info_row(label, value):
        return [Paragraph(label, LBL), Paragraph(str(value or ''), N9)]
    gen_ts = datetime.now().strftime('%d-%m-%Y %H:%M')
    acc_rows = [_info_row('Customer Code', c_code or '—'), _info_row('Customer Name', c_name or '—'), _info_row('Receivable Account', c_recv or '—')]
    acc_rows.append(_info_row('GL lines shown', 'Asset accounts only (receivables / AR-style sub-ledger)'))
    meta_right = [_info_row('Period From', _dmy(date_from)), _info_row('Period To', _dmy(date_to)), _info_row('Generated', gen_ts), _info_row('Prepared By', username or '—')]
    LBL_W = 1.1 * inch
    VAL_W = LEFT_W - LBL_W - 0.1 * inch
    LBL_W2 = 1.1 * inch
    VAL_W2 = RIGHT_W - LBL_W2 - 0.1 * inch
    cust_tbl = Table(acc_rows, colWidths=[LBL_W, VAL_W])
    cust_tbl.setStyle(TableStyle([('FONTSIZE', (0, 0), (-1, -1), 7.5), ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LINEBELOW', (0, 0), (-1, -2), 0.3, colors.HexColor('#dde3ea')), ('TOPPADDING', (0, 0), (-1, -1), PAD), ('BOTTOMPADDING', (0, 0), (-1, -1), PAD), ('LEFTPADDING', (0, 0), (-1, -1), PAD), ('RIGHTPADDING', (0, 0), (-1, -1), PAD)]))
    cl_meta_tbl = Table(meta_right, colWidths=[LBL_W2, VAL_W2])
    cl_meta_tbl.setStyle(TableStyle([('FONTSIZE', (0, 0), (-1, -1), 7.5), ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LINEBELOW', (0, 0), (-1, -2), 0.3, colors.HexColor('#dde3ea')), ('TOPPADDING', (0, 0), (-1, -1), PAD), ('BOTTOMPADDING', (0, 0), (-1, -1), PAD), ('LEFTPADDING', (0, 0), (-1, -1), PAD), ('RIGHTPADDING', (0, 0), (-1, -1), PAD)]))
    info_outer = Table([[cust_tbl, cl_meta_tbl]], colWidths=[LEFT_W, RIGHT_W], hAlign='LEFT')
    info_outer.setStyle(TableStyle([('BOX', (0, 0), (-1, -1), 0.5, BORDER), ('LINEBEFORE', (1, 0), (1, 0), 0.5, BORDER), ('BACKGROUND', (0, 0), (-1, -1), BLUE_LIGHT), ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), PAD), ('RIGHTPADDING', (0, 0), (-1, -1), PAD), ('TOPPADDING', (0, 0), (-1, -1), PAD), ('BOTTOMPADDING', (0, 0), (-1, -1), PAD)]))
    elements.append(info_outer)
    elements.append(Spacer(1, 8))

    def _hcell(txt):
        return Paragraph(f'<b>{txt}</b>', WHT)

    def _dcell(txt, align='LEFT'):
        st = N9R if align == 'RIGHT' else N9C if align == 'CENTER' else N9
        return Paragraph(str(txt), st)
    ob = float(ledger.get('opening_balance') or 0)
    header_text = ['Date', 'Voucher', 'Ref', 'GL A/c', 'Narration', 'Source', 'Debit', 'Credit', 'Balance (Dr−Cr)']
    ob_row = ['—', '—', '—', '—', 'Opening balance (before period)', '—', '—', '—', f'{ob:.2f}']
    body_text_rows: list = [ob_row]
    for row in ledger.get('lines') or []:
        dr = float(row.get('debit') or 0)
        cr = float(row.get('credit') or 0)
        bal = float(row.get('running_balance') or 0)
        body_text_rows.append([str(row.get('voucher_date') or '')[:12], _trunc_pdf_text(row.get('voucher_no'), 18), _trunc_pdf_text(row.get('reference_no'), 10), _trunc_pdf_text(row.get('account_code'), 8), _trunc_pdf_text(row.get('narration'), 28), _trunc_pdf_text(row.get('source'), 10), f'{dr:.2f}' if dr else '—', f'{cr:.2f}' if cr else '—', f'{bal:.2f}'])
    td = float(ledger.get('total_debit') or 0)
    tc = float(ledger.get('total_credit') or 0)
    cl = float(ledger.get('closing_balance') or 0)
    body_text_rows.append(['—', '—', '—', '—', 'Period totals / closing balance', '—', f'{td:.2f}', f'{tc:.2f}', f'{cl:.2f}'])
    pt_rows = [[_hcell(c) for c in header_text]]
    n_body = len(body_text_rows)
    for i, row in enumerate(body_text_rows):
        is_opening = i == 0
        is_closing = i == n_body - 1
        if is_opening:
            pt_rows.append([_dcell(row[0], 'CENTER'), _dcell(row[1], 'CENTER'), _dcell(row[2], 'CENTER'), _dcell(row[3], 'CENTER'), Paragraph(str(row[4]), N8I), _dcell(row[5], 'CENTER'), _dcell(row[6], 'RIGHT'), _dcell(row[7], 'RIGHT'), _dcell(row[8], 'RIGHT')])
        elif is_closing:
            b = _s('clb', parent=styles['Normal'], fontSize=7.5, leading=9.5, fontName='Helvetica-Bold', alignment=TA_RIGHT)
            pt_rows.append([_dcell(row[0], 'CENTER'), _dcell(row[1], 'CENTER'), _dcell(row[2], 'CENTER'), _dcell(row[3], 'CENTER'), Paragraph(f'<b>{str(row[4])}</b>', _s('clbd2', parent=N9, fontName='Helvetica-Bold')), _dcell(row[5], 'CENTER'), Paragraph(f'<b>{str(row[6])}</b>', b), Paragraph(f'<b>{str(row[7])}</b>', b), Paragraph(f'<b>{str(row[8])}</b>', b)])
        else:
            pt_rows.append([_dcell(row[0], 'CENTER'), _dcell(row[1], 'CENTER'), _dcell(row[2], 'CENTER'), _dcell(row[3], 'CENTER'), _dcell(row[4]), _dcell(row[5], 'CENTER'), _dcell(row[6], 'RIGHT'), _dcell(row[7], 'RIGHT'), _dcell(row[8], 'RIGHT')])
    cw = [0.4, 0.75, 0.4, 0.5, 2.8, 0.46, 0.6, 0.6, 0.8]
    cw = [c * inch for c in cw]
    pt = Table(pt_rows, repeatRows=1, colWidths=cw, hAlign='LEFT')
    ts = [('BACKGROUND', (0, 0), (-1, 0), BLUE), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white), ('FONTSIZE', (0, 0), (-1, -1), 7.5), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('GRID', (0, 0), (-1, -1), 0.4, BORDER), ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, GRAY_ROW]), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('TOPPADDING', (0, 0), (-1, -1), PAD), ('BOTTOMPADDING', (0, 0), (-1, -1), PAD), ('LEFTPADDING', (0, 0), (-1, -1), PAD), ('RIGHTPADDING', (0, 0), (-1, -1), PAD)]
    nrows = len(pt_rows)
    ts.append(('BACKGROUND', (0, 1), (-1, 1), BLUE_LIGHT))
    if nrows > 2:
        ts.append(('BACKGROUND', (0, nrows - 1), (-1, nrows - 1), BLUE_LIGHT))
    pt.setStyle(TableStyle(ts))
    elements.append(pt)
    elements.append(Spacer(1, 8))
    elements.append(Paragraph('This is a computer-generated document. Lines are GL_VOUCHER_DTL with PARTY_TYPE=CUSTOMER on ASSET (chart) accounts. Balance is running (debit − credit) after each line. No signature is required.', FOOT))
    doc.build(elements)
    return buffer.getvalue()

def _request_exclude_closing() -> bool:
    """True when query asks to omit PERIOD_CLOSE journals and their JE_REV reopen reversals."""
    raw = (request.args.get('exclude_closing') or request.args.get('exclude_close') or '').strip().lower()
    return raw in ('1', 'true', 'yes', 'on', 'y')


def _request_pl_pdf_mode() -> str:
    """P&L PDF layout: ``single`` (selected period only) or ``comparison`` (3 columns)."""
    raw = (
        request.args.get('pdf_mode')
        or request.args.get('mode')
        or request.args.get('pl_mode')
        or ''
    ).strip().lower()
    if raw in ('single', 'period', 'one', 'month', '1'):
        return 'single'
    if raw in ('comparison', 'comparative', 'compare', 'multi', '3'):
        return 'comparison'
    return 'comparison'


def _get_profit_loss_report_context() -> Dict[str, Any]:
    """P&L comparative data for the HTML page and PDF/Excel (uses query ``date_from`` / ``date_to``)."""
    date_from = _parse_iso_date(request.args.get('date_from', ''))
    date_to = _parse_iso_date(request.args.get('date_to', ''))
    exclude_closing = _request_exclude_closing()
    search_term = (request.args.get('q') or '').strip()
    status_filter = (request.args.get('status') or 'all').strip().lower()
    from addons.purchase.controllers.routes import _get_company_profile
    company = _get_company_profile()
    company_name = str(company.get('name') or session.get('location_name') or 'Company')
    report = get_profit_and_loss_comparative(
        date_from=date_from or None,
        date_to=date_to or None,
        exclude_closing=exclude_closing,
    )
    dfa = (report.get('date_from') or date_from) or ''
    dta = (report.get('date_to') or date_to) or ''

    def _pl_fmt(iso: str) -> str:
        if not (iso or '').strip():
            return ''
        try:
            return datetime.strptime(iso.strip()[:10], '%Y-%m-%d').strftime('%d %B %Y')
        except Exception:
            return iso
    return {
        'company_name': company_name,
        'period_labels': report.get('period_labels') or ['', '', ''],
        'period_ranges': report.get('period_ranges') or [],
        'revenue_rows': report.get('revenue_rows') or [],
        'expense_rows': report.get('expense_rows') or [],
        'cost_of_sales_rows': report.get('cost_of_sales_rows') or [],
        'operating_expense_rows': report.get('operating_expense_rows') or [],
        'total_revenue': report.get('total_revenue') or [0, 0, 0],
        'total_expense': report.get('total_expense') or [0, 0, 0],
        'total_cost_of_sales': report.get('total_cost_of_sales') or [0, 0, 0],
        'total_operating_expense': report.get('total_operating_expense') or [0, 0, 0],
        'gross_profit': report.get('gross_profit') or [0, 0, 0],
        'net_profit': report.get('net_profit') or [0, 0, 0],
        'date_from': dfa,
        'date_to': dta,
        'date_from_display': _pl_fmt(dfa),
        'date_to_display': _pl_fmt(dta),
        'exclude_closing': exclude_closing,
    }

def _build_profit_loss_pdf(ctx: Dict[str, Any], *, mode: str = 'comparison') -> bytes:
    """P&L PDF — ``single`` = selected period only; ``comparison`` = 3 comparative columns."""
    if not REPORTLAB_AVAILABLE:
        return b''
    single = str(mode or '').strip().lower() in ('single', 'period', 'one', 'month', '1')
    company_name = str(ctx.get('company_name') or '')
    df_disp = str(ctx.get('date_from_display') or '')
    dt_disp = str(ctx.get('date_to_display') or '')
    labels: List[str] = list(ctx.get('period_labels') or ['', '', ''])
    while len(labels) < 3:
        labels.append('')
    revenue_rows: List[Dict[str, Any]] = list(ctx.get('revenue_rows') or [])
    cos_rows: List[Dict[str, Any]] = list(ctx.get('cost_of_sales_rows') or [])
    opex_rows: List[Dict[str, Any]] = list(ctx.get('operating_expense_rows') or ctx.get('expense_rows') or [])
    tr: List[float] = list(ctx.get('total_revenue') or [0, 0, 0])
    tcos: List[float] = list(ctx.get('total_cost_of_sales') or [0, 0, 0])
    topex: List[float] = list(ctx.get('total_operating_expense') or [0, 0, 0])
    gp_vals: List[float] = list(ctx.get('gross_profit') or [0, 0, 0])
    net_vals: List[float] = list(ctx.get('net_profit') or [0, 0, 0])
    for _lst in (tr, tcos, topex, gp_vals, net_vals):
        while len(_lst) < 3:
            _lst.append(0.0)

    def _m(v: float) -> str:
        return f'{float(v):,.2f}'

    def _a(row: Optional[Dict[str, Any]], i: int) -> float:
        if not row:
            return 0.0
        ams = row.get('amounts') or []
        try:
            return float(ams[i]) if i < len(ams) else 0.0
        except Exception:
            return 0.0

    styles = getSampleStyleSheet()
    MAROON = colors.HexColor('#6b0f1a')
    GRAY = colors.HexColor('#e8e8e8')
    BORDER = colors.HexColor('#333333')
    TEXT = colors.HexColor('#1a1a1a')
    PAD = 5
    W = 7.47 * inch

    def _s(name: str, **kw: Any) -> ParagraphStyle:
        base = kw.pop('parent', styles['Normal'])
        tc = kw.pop('textColor', TEXT)
        return ParagraphStyle(name, parent=base, textColor=tc, **kw)

    N8 = _s('pl8', fontName='Times-Roman', fontSize=8, leading=10)
    N8B = _s('pl8b', fontName='Times-Bold', fontSize=8, leading=10)
    N8R = _s('pl8r', fontName='Times-Roman', fontSize=8, leading=10, alignment=TA_RIGHT)
    N8i = _s('pl8i', fontName='Times-Italic', fontSize=8, leading=10, textColor=colors.HexColor('#444'))
    N9B = _s('pl9b', fontName='Times-Bold', fontSize=9, leading=11, textColor=MAROON, alignment=TA_CENTER)
    FOOT = _s('plft', fontName='Times-Roman', fontSize=6.5, leading=9, textColor=colors.HexColor('#666666'))
    h_center = _s('plhc', fontName='Times-Bold', fontSize=7, leading=9, textColor=colors.white, alignment=TA_CENTER)
    h_right = _s('plhr', fontName='Times-Bold', fontSize=7, leading=9, textColor=colors.white, alignment=TA_RIGHT)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=0.5 * inch, bottomMargin=0.4 * inch,
        leftMargin=0.45 * inch, rightMargin=0.45 * inch,
    )
    from xml.sax.saxutils import escape as _xml_esc_pl
    elements: List[Any] = []
    elements.append(Paragraph(
        f"<b>{_xml_esc_pl(str(company_name or 'Company'))}</b>",
        _s('plco2', fontName='Times-Bold', fontSize=11, leading=14, alignment=TA_CENTER),
    ))
    if df_disp and dt_disp:
        if single:
            period_txt = (
                f'<i>Statement of profit or loss for the period from '
                f'{_xml_esc_pl(df_disp)} to {_xml_esc_pl(dt_disp)}.</i>'
            )
        else:
            period_txt = (
                f'<i>Consolidated statement of profit or loss for the period from '
                f'{_xml_esc_pl(df_disp)} to {_xml_esc_pl(dt_disp)} '
                f'(and comparative periods of equal length).</i>'
            )
        elements.append(Paragraph(
            period_txt,
            _s('plper', fontName='Times-Italic', fontSize=8.5, leading=11, alignment=TA_CENTER, textColor=TEXT),
        ))
    if ctx.get('exclude_closing'):
        elements.append(Paragraph(
            '<i>Period closing journals and reopen reversals excluded.</i>', N8i,
        ))
    elements.append(Paragraph('<i>(All amounts in reporting currency unless otherwise stated.)</i>', N8i))
    elements.append(Spacer(1, 6))
    title = 'STATEMENT OF PROFIT OR LOSS' if single else 'CONSOLIDATED STATEMENT OF PROFIT OR LOSS'
    elements.append(Paragraph(f'<b>{title}</b>', N9B))
    elements.append(Spacer(1, 2))
    line = Table([['']], colWidths=[W], rowHeights=[2], hAlign='CENTER')
    line.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), MAROON)]))
    elements.append(line)
    elements.append(Spacer(1, 6))

    amt_cols = 1 if single else 3
    h0 = str(labels[0] or (dt_disp or 'Period'))
    if single:
        head = [
            Paragraph('<b>Description</b>', h_center),
            Paragraph('<b>Ref.</b>', h_center),
            Paragraph(f'<b>{_xml_esc_pl(h0)}</b>', h_right),
        ]
        empty_tail: List[Any] = ['']
        cw = [4.2 * inch, 0.7 * inch, 2.0 * inch]
    else:
        h1 = str(labels[1] or 'Comparative')
        h2 = str(labels[2] or 'Comparative')
        head = [
            Paragraph('<b>Description</b>', h_center),
            Paragraph('<b>Ref.</b>', h_center),
            Paragraph(f'<b>{_xml_esc_pl(h0)}</b>', h_right),
            Paragraph(f'<b>{_xml_esc_pl(h1)}</b>', h_right),
            Paragraph(f'<b>{_xml_esc_pl(h2)}</b>', h_right),
        ]
        empty_tail = ['', '', '']
        cw = [2.5 * inch, 0.55 * inch, 0.95 * inch, 0.95 * inch, 0.95 * inch]

    data: List[List[Any]] = [head]

    def add_row(cells: List[Any]) -> None:
        data.append(cells)

    def amt_cells(vals: List[float], *, bold: bool = False) -> List[Any]:
        sty = N8B if bold else N8R
        out: List[Any] = []
        for i in range(amt_cols):
            txt = _m(vals[i] if i < len(vals) else 0.0)
            out.append(Paragraph(f'<b>{txt}</b>' if bold else txt, sty))
        return out

    def line_cells(name: str, code: str, row: Optional[Dict[str, Any]]) -> List[Any]:
        cells: List[Any] = [
            Paragraph(_xml_esc_pl(name)[:200], N8),
            Paragraph(_xml_esc_pl(code), N8),
        ]
        for i in range(amt_cols):
            cells.append(Paragraph(_m(_a(row, i)), N8R))
        return cells

    def section_header(label: str) -> None:
        add_row([Paragraph(f'<b>{label}</b>', N8B), ''] + list(empty_tail))

    def total_row(label: str, vals: List[float]) -> None:
        add_row([Paragraph(f'<b>{label}</b>', N8B), ''] + amt_cells(vals, bold=True))

    section_header('REVENUE')
    for r in revenue_rows:
        add_row(line_cells(str(r.get('name') or ''), str(r.get('code') or ''), r))
    if not revenue_rows:
        add_row([Paragraph('<i>No revenue postings in this period.</i>', N8i), ''] + list(empty_tail))
    total_row('Total revenue', tr)
    add_row([''] * (2 + amt_cols))
    section_header('COST OF SALES')
    for r in cos_rows:
        add_row(line_cells(str(r.get('name') or ''), str(r.get('code') or ''), r))
    if not cos_rows:
        add_row([Paragraph('<i>No cost of sales postings in this period.</i>', N8i), ''] + list(empty_tail))
    total_row('Total cost of sales', tcos)
    total_row('Gross profit', gp_vals)
    add_row([''] * (2 + amt_cols))
    section_header('OPERATING EXPENSES')
    for r in opex_rows:
        add_row(line_cells(str(r.get('name') or ''), str(r.get('code') or ''), r))
    if not opex_rows:
        add_row([Paragraph('<i>No operating expense postings in this period.</i>', N8i), ''] + list(empty_tail))
    total_row('Total operating expenses', topex)
    total_row('Net profit / (loss)', net_vals)

    t = Table(data, colWidths=cw, repeatRows=1, hAlign='LEFT')
    nrows = len(data)
    nrev_lines = len(revenue_rows) if revenue_rows else 1
    row_tr = 2 + nrev_lines
    ncos_lines = len(cos_rows) if cos_rows else 1
    row_tcos = row_tr + 3 + ncos_lines
    row_gp = row_tcos + 1
    nopex_lines = len(opex_rows) if opex_rows else 1
    row_topex = row_gp + 3 + nopex_lines
    row_net = nrows - 1
    ts = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1a1a')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Times-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 7),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LINEABOVE', (0, 0), (-1, 0), 0.5, BORDER),
        ('LINEBELOW', (0, 0), (-1, 0), 0.5, BORDER),
        ('LEFTPADDING', (0, 0), (-1, -1), PAD),
        ('RIGHTPADDING', (0, 0), (-1, -1), PAD),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]
    for r_i in (row_tr, row_tcos, row_topex):
        ts.append(('LINEABOVE', (0, r_i), (-1, r_i), 0.5, BORDER))
    ts.append(('LINEABOVE', (0, row_gp), (-1, row_gp), 0.75, BORDER))
    ts.append(('LINEBELOW', (0, row_gp), (-1, row_gp), 0.75, BORDER))
    ts.append(('BACKGROUND', (0, row_gp), (-1, row_gp), colors.HexColor('#f8fafc')))
    ts.append(('LINEABOVE', (0, row_net), (-1, row_net), 1.0, colors.black))
    ts.append(('LINEBELOW', (0, row_net), (-1, row_net), 1.0, colors.black))
    amt_col0 = 2
    for r_i in range(1, nrows):
        ts.append(('BACKGROUND', (amt_col0, r_i), (amt_col0, r_i), GRAY))
    t.setStyle(TableStyle(ts))
    elements.append(t)
    elements.append(Spacer(1, 10))
    if single:
        foot = (
            'Computer-generated from the general ledger for the selected period only. '
            'No signature is required.'
        )
    else:
        foot = (
            'Computer-generated from the general ledger. Two equal-length comparative periods '
            'precede the selected range. No signature is required.'
        )
    elements.append(Paragraph(foot, FOOT))
    doc.build(elements)
    return buffer.getvalue()

def _build_profit_loss_excel(ctx: Dict[str, Any]) -> Optional[bytes]:
    """P&L comparative as a single-sheet .xlsx."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
    except ImportError:
        return None
    labels: List[str] = list(ctx.get('period_labels') or ['', '', ''])
    while len(labels) < 3:
        labels.append('')
    revenue_rows = list(ctx.get('revenue_rows') or [])
    cos_rows = list(ctx.get('cost_of_sales_rows') or [])
    opex_rows = list(ctx.get('operating_expense_rows') or ctx.get('expense_rows') or [])
    tr = list(ctx.get('total_revenue') or [0, 0, 0])
    tcos = list(ctx.get('total_cost_of_sales') or [0, 0, 0])
    topex = list(ctx.get('total_operating_expense') or [0, 0, 0])
    gp = list(ctx.get('gross_profit') or [0, 0, 0])
    nv = list(ctx.get('net_profit') or [0, 0, 0])
    for L in (tr, tcos, topex, gp, nv):
        while len(L) < 3:
            L.append(0.0)
    thin = Side(style='thin', color='CCCCCC')
    box = Border(left=thin, right=thin, top=thin, bottom=thin)
    hdr_fill = PatternFill(start_color='1a1a1a', end_color='1a1a1a', fill_type='solid')
    hdr_font = Font(bold=True, color='FFFFFF', size=10)
    cur_fill = PatternFill(start_color='E8E8E8', end_color='E8E8E8', fill_type='solid')
    sec_font = Font(bold=True, size=10)
    wb = Workbook()
    ws = wb.active
    ws.title = 'P&L'
    co = str(ctx.get('company_name') or 'Company')
    ws['A1'] = co
    ws['A1'].font = Font(bold=True, size=13)
    ws.merge_cells('A1:E1')
    df = str(ctx.get('date_from_display') or '')
    dt = str(ctx.get('date_to_display') or '')
    ws['A2'] = f'Profit or loss (and comparatives): {df} to {dt}' if df and dt else 'Profit or loss'
    ws.merge_cells('A2:E2')
    ws['A3'] = f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    ws.merge_cells('A3:E3')
    r = 5
    headers = ['Description', 'Ref.', labels[0] or 'Current', labels[1] or 'Prior 1', labels[2] or 'Prior 2']
    for c, h in enumerate(headers, 1):
        cell = ws.cell(row=r, column=c, value=h)
        cell.fill = hdr_fill
        cell.font = hdr_font
        cell.border = box
        cell.alignment = Alignment(horizontal='center' if c >= 3 else 'left', wrap_text=True)
    if len(headers) >= 3:
        ws.cell(row=r, column=3).fill = hdr_fill
    r += 1

    def wr_row(desc: str, ref: str, a0: float, a1: float, a2: float, bold: bool=False, cur_gray: bool=True) -> None:
        nonlocal r
        f = sec_font if bold else Font(size=10)
        ws.cell(row=r, column=1, value=desc).font = f
        ws.cell(row=r, column=2, value=ref).font = f
        ws.cell(row=r, column=3, value=round(float(a0), 2)).font = f
        ws.cell(row=r, column=4, value=round(float(a1), 2)).font = f
        ws.cell(row=r, column=5, value=round(float(a2), 2)).font = f
        for c in range(1, 6):
            ws.cell(row=r, column=c).border = box
            if c >= 3:
                ws.cell(row=r, column=c).alignment = Alignment(horizontal='right')
                if cur_gray and c == 3:
                    ws.cell(row=r, column=c).fill = cur_fill
        r += 1
    wr_row('REVENUE', '', 0, 0, 0, bold=True, cur_gray=False)
    if revenue_rows:
        for row in revenue_rows:
            am = row.get('amounts') or [0, 0, 0]
            while len(am) < 3:
                am.append(0)
            wr_row(str(row.get('name') or ''), str(row.get('code') or ''), float(am[0]), float(am[1]), float(am[2]))
    else:
        wr_row('No revenue postings', '', 0, 0, 0)
    wr_row('Total revenue', '', tr[0], tr[1], tr[2], bold=True)
    r += 1
    wr_row('COST OF SALES', '', 0, 0, 0, bold=True, cur_gray=False)
    if cos_rows:
        for row in cos_rows:
            am = row.get('amounts') or [0, 0, 0]
            while len(am) < 3:
                am.append(0)
            wr_row(str(row.get('name') or ''), str(row.get('code') or ''), float(am[0]), float(am[1]), float(am[2]))
    else:
        wr_row('No cost of sales postings', '', 0, 0, 0)
    wr_row('Total cost of sales', '', tcos[0], tcos[1], tcos[2], bold=True)
    wr_row('Gross profit', '', gp[0], gp[1], gp[2], bold=True)
    r += 1
    wr_row('OPERATING EXPENSES', '', 0, 0, 0, bold=True, cur_gray=False)
    if opex_rows:
        for row in opex_rows:
            am = row.get('amounts') or [0, 0, 0]
            while len(am) < 3:
                am.append(0)
            wr_row(str(row.get('name') or ''), str(row.get('code') or ''), float(am[0]), float(am[1]), float(am[2]))
    else:
        wr_row('No operating expense postings', '', 0, 0, 0)
    wr_row('Total operating expenses', '', topex[0], topex[1], topex[2], bold=True)
    wr_row('Net profit / (loss)', '', nv[0], nv[1], nv[2], bold=True)
    for col in range(1, 6):
        ws.column_dimensions[get_column_letter(col)].width = 36 if col == 1 else 10 if col == 2 else 16
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _get_balance_sheet_report_context() -> Dict[str, Any]:
    """Balance sheet data for HTML, PDF, and Excel (uses query ``as_of_date``)."""
    as_of_date = _parse_iso_date(request.args.get('as_of_date', '')) or datetime.now().strftime('%Y-%m-%d')
    from addons.purchase.controllers.routes import _get_company_profile
    company = _get_company_profile()
    company_name = str(company.get('name') or session.get('location_name') or 'Company')
    report = get_balance_sheet_report(as_of_date=as_of_date)

    def _bs_fmt(iso: str) -> str:
        if not (iso or '').strip():
            return ''
        try:
            return datetime.strptime(iso.strip()[:10], '%Y-%m-%d').strftime('%d %B %Y')
        except Exception:
            return iso

    def _title_account_names(rows: Any) -> List[Dict[str, Any]]:
        """Title-case account names for HTML / PDF / Excel (e.g. Ajmal Salary)."""
        out: List[Dict[str, Any]] = []
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            r = dict(row)
            r['name'] = _balance_sheet_display_name(r.get('name'))
            out.append(r)
        return out

    total_assets = float(report.get('total_assets') or 0)
    lpe = float(report.get('liabilities_plus_equity') or 0)
    return {
        'company_name': company_name,
        'as_of_date': as_of_date,
        'as_of_date_display': _bs_fmt(as_of_date),
        'asset_accounts': _title_account_names(report.get('assets')),
        'liability_accounts': _title_account_names(report.get('liabilities')),
        'equity_accounts': _title_account_names(report.get('equities')),
        'total_assets': report.get('total_assets') or 0,
        'total_liabilities': report.get('total_liabilities') or 0,
        'total_equity': report.get('total_equity') or 0,
        'liabilities_plus_equity': report.get('liabilities_plus_equity') or 0,
        'difference': round(total_assets - lpe, 2),
    }


def _balance_sheet_display_name(name: Any) -> str:
    """First letter of each word capital, rest small (Title Case)."""
    return str(name or '').strip().title()


def _balance_sheet_row_label(row: Dict[str, Any]) -> str:
    depth = int(row.get('depth') or 0)
    indent = '    ' * max(0, depth)
    marker = '▸ ' if row.get('is_group') else ''
    name = _balance_sheet_display_name(row.get('name'))
    return f'{indent}{marker}{name}'


def _normalize_balance_sheet_pdf_layout(layout: Optional[str]) -> str:
    """``single`` = stacked sections; ``two_column`` = assets | liabilities+equity."""
    v = (layout or 'single').strip().lower().replace('-', '_')
    if v in ('two', 'two_column', '2', '2col', 'dual', 'double', 'twocol'):
        return 'two_column'
    return 'single'


def _build_balance_sheet_pdf(ctx: Dict[str, Any], layout: str = 'single') -> bytes:
    """Statement-style balance sheet PDF (single- or two-column layout)."""
    if _normalize_balance_sheet_pdf_layout(layout) == 'two_column':
        return _build_balance_sheet_pdf_two_column(ctx)
    return _build_balance_sheet_pdf_single_column(ctx)


def _build_balance_sheet_pdf_single_column(ctx: Dict[str, Any]) -> bytes:
    """Balance sheet PDF: Assets, then Liabilities, then Equity (one column)."""
    if not REPORTLAB_AVAILABLE:
        return b''
    from xml.sax.saxutils import escape as _xml_esc_bs

    pack = _balance_sheet_pdf_style_pack()
    company_name = str(ctx.get('company_name') or '')
    as_of_disp = str(ctx.get('as_of_date_display') or '')
    assets = list(ctx.get('asset_accounts') or [])
    liabilities = list(ctx.get('liability_accounts') or [])
    equities = list(ctx.get('equity_accounts') or [])
    total_assets = float(ctx.get('total_assets') or 0)
    total_liabilities = float(ctx.get('total_liabilities') or 0)
    total_equity = float(ctx.get('total_equity') or 0)
    lpe = float(ctx.get('liabilities_plus_equity') or 0)
    diff = float(ctx.get('difference') or 0)
    _m = pack['_m']
    N8 = pack['N8']
    N8B = pack['N8B']
    N8R = pack['N8R']
    N8i = pack['N8i']
    h_center = pack['h_center']
    h_right = pack['h_right']
    FOOT = pack['FOOT']
    W = pack['W']

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=0.5 * inch,
        bottomMargin=0.4 * inch,
        leftMargin=0.45 * inch,
        rightMargin=0.45 * inch,
    )
    elements: List[Any] = []
    _balance_sheet_pdf_append_header(elements, pack, company_name, as_of_disp, layout_label='Single column')
    data: List[List[Any]] = [
        [
            Paragraph('<b>Ref.</b>', h_center),
            Paragraph('<b>Description</b>', h_center),
            Paragraph('<b>Amount</b>', h_right),
        ],
    ]
    _balance_sheet_pdf_fill_section_data(
        data, pack, _xml_esc_bs,
        [
            ('ASSETS', assets, 'Total assets', total_assets),
            ('LIABILITIES', liabilities, 'Total liabilities', total_liabilities),
            ('EQUITY', equities, 'Total equity', total_equity),
        ],
        extra_totals=[('Total liabilities and equity', lpe)],
        difference=diff,
    )
    cw = [0.75 * inch, 4.72 * inch, 1.0 * inch]
    elements.append(_balance_sheet_pdf_styled_table(data, cw, pack))
    _balance_sheet_pdf_append_footer(elements, FOOT)
    doc.build(elements)
    return buffer.getvalue()


def _build_balance_sheet_pdf_two_column(ctx: Dict[str, Any]) -> bytes:
    """Balance sheet PDF: Assets (left) | Liabilities + Equity (right).

    One flat table (accounts + totals + difference + footer) so ReportLab can
    split by row across pages without KeepTogether blank-page gaps.
    """
    if not REPORTLAB_AVAILABLE:
        return b''
    from xml.sax.saxutils import escape as _xml_esc_bs

    pack = _balance_sheet_pdf_style_pack()
    company_name = str(ctx.get('company_name') or '')
    as_of_disp = str(ctx.get('as_of_date_display') or '')
    assets = list(ctx.get('asset_accounts') or [])
    liabilities = list(ctx.get('liability_accounts') or [])
    equities = list(ctx.get('equity_accounts') or [])
    total_assets = float(ctx.get('total_assets') or 0)
    total_liabilities = float(ctx.get('total_liabilities') or 0)
    total_equity = float(ctx.get('total_equity') or 0)
    lpe = float(ctx.get('liabilities_plus_equity') or 0)
    diff = float(ctx.get('difference') or 0)
    _m = pack['_m']
    N8B = pack['N8B']
    FOOT = pack['FOOT']
    # Must not exceed frame width — pack['W'] (7.47") was wider than A4−margins (~7.37")
    # and contributed to odd page breaks / near-blank pages.
    left_m = 0.45 * inch
    right_m = 0.45 * inch
    top_m = 0.5 * inch
    bottom_m = 0.4 * inch
    W = float(A4[0]) - left_m - right_m
    GAP = 0.10 * inch
    half_w = (W - GAP) / 2.0
    # Left: Ref / Description / Amount | gap | Right: Ref / Description / Amount
    col_cw = [
        half_w * 0.14, half_w * 0.64, half_w * 0.22,
        GAP,
        half_w * 0.14, half_w * 0.64, half_w * 0.22,
    ]

    left_data: List[List[Any]] = []
    _balance_sheet_pdf_fill_section_data(left_data, pack, _xml_esc_bs, [('ASSETS', assets, 'Total assets', total_assets)])

    right_data: List[List[Any]] = []
    _balance_sheet_pdf_fill_section_data(
        right_data, pack, _xml_esc_bs,
        [
            ('LIABILITIES', liabilities, 'Total liabilities', total_liabilities),
            ('EQUITY', equities, 'Total equity', total_equity),
        ],
        extra_totals=[('Total liabilities and equity', lpe)],
    )

    def _pad3(row: Optional[List[Any]]) -> List[Any]:
        out = list(row or [])
        while len(out) < 3:
            out.append('')
        return out[:3]

    empty3 = ['', '', '']
    # Keep grand totals on the same final row so "Total assets" is not left
    # floating mid-page while equity continues on the right.
    left_total = _pad3(left_data[-1]) if left_data else list(empty3)
    right_total = _pad3(right_data[-1]) if right_data else list(empty3)
    left_body = [_pad3(r) for r in left_data[:-1]] if len(left_data) > 1 else []
    right_body = [_pad3(r) for r in right_data[:-1]] if len(right_data) > 1 else []

    header = [
        Paragraph('<b>Ref.</b>', pack['h_center']),
        Paragraph('<b>Description</b>', pack['h_center']),
        Paragraph('<b>Amount</b>', pack['h_right']),
        '',
        Paragraph('<b>Ref.</b>', pack['h_center']),
        Paragraph('<b>Description</b>', pack['h_center']),
        Paragraph('<b>Amount</b>', pack['h_right']),
    ]
    nrows = max(len(left_body), len(right_body))
    combined: List[List[Any]] = [header]
    for i in range(nrows):
        left_row = left_body[i] if i < len(left_body) else list(empty3)
        right_row = right_body[i] if i < len(right_body) else list(empty3)
        combined.append(left_row + [''] + right_row)

    totals_row_idx = len(combined)
    combined.append(left_total + [''] + right_total)
    diff_row_idx = len(combined)
    combined.append([
        Paragraph('<b>Difference (assets − liabilities and equity)</b>', N8B),
        '', '', '', '', '',
        Paragraph(f'<b>{_m(diff)}</b>', N8B),
    ])

    # Footer must NOT be a table row: with repeatRows=1 it created a near-blank
    # last page that only showed the black column headers + disclaimer.
    tbl = _balance_sheet_pdf_styled_two_column_table(
        combined,
        col_cw,
        pack,
        highlight_last=False,
        show_header=True,
        totals_row_index=totals_row_idx,
        span_rows=((diff_row_idx, 0, 5),),
    )

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=top_m,
        bottomMargin=bottom_m,
        leftMargin=left_m,
        rightMargin=right_m,
    )
    elements: List[Any] = []
    # Header line uses pack W; override temporarily for correct rule width.
    pack_w = dict(pack)
    pack_w['W'] = W
    _balance_sheet_pdf_append_header(elements, pack_w, company_name, as_of_disp, layout_label='Two column')
    elements.append(tbl)
    elements.append(Spacer(1, 8))
    elements.append(Paragraph(
        'Computer-generated from the general ledger and chart of accounts. '
        'Current period earnings are included in equity when applicable. No signature is required.',
        FOOT,
    ))
    doc.build(elements)
    return buffer.getvalue()


def _balance_sheet_pdf_style_pack() -> Dict[str, Any]:
    """Shared ReportLab styles and helpers for balance sheet PDFs."""
    from xml.sax.saxutils import escape as _xml_esc_bs

    styles = getSampleStyleSheet()
    MAROON = colors.HexColor('#6b0f1a')
    GRAY = colors.HexColor('#e8e8e8')
    BORDER = colors.HexColor('#333333')
    TEXT = colors.HexColor('#1a1a1a')
    PAD = 5
    W = 7.47 * inch

    def _s(name: str, **kw: Any) -> ParagraphStyle:
        base = kw.pop('parent', styles['Normal'])
        tc = kw.pop('textColor', TEXT)
        return ParagraphStyle(name, parent=base, textColor=tc, **kw)

    def _m(v: float) -> str:
        return f'{float(v):,.2f}'

    return {
        '_xml_esc_bs': _xml_esc_bs,
        '_m': _m,
        '_s': _s,
        'MAROON': MAROON,
        'GRAY': GRAY,
        'BORDER': BORDER,
        'TEXT': TEXT,
        'PAD': PAD,
        'W': W,
        'N8': _s('bs8', fontName='Times-Roman', fontSize=8, leading=10),
        'N8B': _s('bs8b', fontName='Times-Bold', fontSize=8, leading=10),
        'N8R': _s('bs8r', fontName='Times-Roman', fontSize=8, leading=10, alignment=TA_RIGHT),
        'N8i': _s('bs8i', fontName='Times-Italic', fontSize=8, leading=10, textColor=colors.HexColor('#444444')),
        'N9B': _s('bs9b', fontName='Times-Bold', fontSize=9, leading=11, textColor=MAROON, alignment=TA_CENTER),
        'FOOT': _s('bsft', fontName='Times-Roman', fontSize=6.5, leading=9, textColor=colors.HexColor('#666666')),
        'h_center': _s('bshc', fontName='Times-Bold', fontSize=7, leading=9, textColor=colors.white, alignment=TA_CENTER),
        'h_right': _s('bshr', fontName='Times-Bold', fontSize=7, leading=9, textColor=colors.white, alignment=TA_RIGHT),
    }


def _balance_sheet_pdf_append_header(
    elements: List[Any],
    pack: Dict[str, Any],
    company_name: str,
    as_of_disp: str,
    layout_label: str = '',
) -> None:
    _xml_esc_bs = pack['_xml_esc_bs']
    _s = pack['_s']
    N9B = pack['N9B']
    MAROON = pack['MAROON']
    W = pack['W']
    elements.append(Paragraph(
        f"<b>{_xml_esc_bs(company_name or 'Company')}</b>",
        _s('bsco', fontName='Times-Bold', fontSize=11, leading=14, alignment=TA_CENTER),
    ))
    if as_of_disp:
        elements.append(Paragraph(
            f'<i>Consolidated balance sheet as at {_xml_esc_bs(as_of_disp)}.</i>',
            _s('bsper', fontName='Times-Italic', fontSize=8.5, leading=11, alignment=TA_CENTER, textColor=pack['TEXT']),
        ))
    if layout_label:
        elements.append(Paragraph(
            f'<i>Layout: {_xml_esc_bs(layout_label)}</i>',
            _s('bslay', fontName='Times-Italic', fontSize=7.5, leading=9, alignment=TA_CENTER, textColor=colors.HexColor('#555555')),
        ))
    elements.append(Spacer(1, 6))
    elements.append(Paragraph('<b>CONSOLIDATED BALANCE SHEET</b>', N9B))
    elements.append(Spacer(1, 2))
    line = Table([['']], colWidths=[W], rowHeights=[2], hAlign='CENTER')
    line.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), MAROON)]))
    elements.append(line)
    elements.append(Spacer(1, 6))


def _balance_sheet_pdf_fill_section_data(
    data: List[List[Any]],
    pack: Dict[str, Any],
    _xml_esc_bs: Any,
    sections: List[Tuple[str, List[Dict[str, Any]], str, float]],
    *,
    extra_totals: Optional[List[Tuple[str, float]]] = None,
    difference: Optional[float] = None,
) -> None:
    N8 = pack['N8']
    N8B = pack['N8B']
    N8R = pack['N8R']
    N8i = pack['N8i']
    _m = pack['_m']

    def add_section(title: str) -> None:
        # Put section title in the Description column (not Ref) so words like
        # LIABILITIES stay on one line in the two-column PDF layout.
        data.append(['', Paragraph(f'<b>{_xml_esc_bs(title)}</b>', N8B), ''])

    def add_lines(rows: List[Dict[str, Any]]) -> None:
        if not rows:
            data.append(['', Paragraph('<i>No accounts in this section.</i>', N8i), ''])
            return
        for row in rows:
            amt = float(row.get('amount') or 0)
            if row.get('is_group') and amt == 0:
                amt_txt = ''
            else:
                amt_txt = _m(amt)
            data.append([
                Paragraph(_xml_esc_bs(str(row.get('code') or '')), N8),
                Paragraph(_xml_esc_bs(_balance_sheet_row_label(row))[:220], N8B if row.get('is_group') else N8),
                Paragraph(amt_txt, N8R if amt_txt else N8),
            ])

    def add_total(label: str, amount: float) -> None:
        data.append([
            '',
            Paragraph(f'<b>{_xml_esc_bs(label)}</b>', N8B),
            Paragraph(f'<b>{_m(amount)}</b>', N8B),
        ])

    for i, (title, rows, total_label, total_amount) in enumerate(sections):
        if i > 0:
            data.append(['', '', ''])
        add_section(title)
        add_lines(rows)
        add_total(total_label, total_amount)
    for label, amount in extra_totals or []:
        data.append(['', '', ''])
        add_total(label, amount)
    if difference is not None:
        data.append(['', '', ''])
        data.append([
            '',
            Paragraph('<b>Difference (assets − liabilities and equity)</b>', N8B),
            Paragraph(f'<b>{_m(difference)}</b>', N8B),
        ])


def _balance_sheet_pdf_styled_table(
    data: List[List[Any]],
    col_widths: List[float],
    pack: Dict[str, Any],
    halign: str = 'LEFT',
) -> Table:
    BORDER = pack['BORDER']
    GRAY = pack['GRAY']
    PAD = pack['PAD']
    t = Table(data, colWidths=col_widths, repeatRows=1, hAlign=halign)
    nrows = len(data)
    ts = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1a1a')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Times-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 7),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LINEABOVE', (0, 0), (-1, 0), 0.5, BORDER),
        ('LINEBELOW', (0, 0), (-1, 0), 0.5, BORDER),
        ('LEFTPADDING', (0, 0), (-1, -1), PAD),
        ('RIGHTPADDING', (0, 0), (-1, -1), PAD),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]
    for r_i in range(1, nrows):
        ts.append(('BACKGROUND', (2, r_i), (2, r_i), GRAY))
    if nrows > 1:
        ts.append(('LINEABOVE', (0, nrows - 1), (-1, nrows - 1), 1.0, colors.black))
        ts.append(('LINEBELOW', (0, nrows - 1), (-1, nrows - 1), 1.0, colors.black))
    t.setStyle(TableStyle(ts))
    return t


def _balance_sheet_pdf_styled_two_column_table(
    data: List[List[Any]],
    col_widths: List[float],
    pack: Dict[str, Any],
    *,
    highlight_last: bool = True,
    show_header: bool = True,
    totals_row_index: Optional[int] = None,
    span_rows: Optional[Tuple[Tuple[int, int, int], ...]] = None,
) -> Table:
    """Styled splittable 7-col table: left 3 + gap + right 3."""
    BORDER = pack['BORDER']
    GRAY = pack['GRAY']
    PAD = pack['PAD']
    repeat = 1 if show_header and data else 0
    t = Table(data, colWidths=col_widths, repeatRows=repeat, hAlign='LEFT')
    nrows = len(data)
    span_row_idxs = {s[0] for s in (span_rows or ())}
    ts: List[Any] = [
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), PAD),
        ('RIGHTPADDING', (0, 0), (-1, -1), PAD),
        ('LEFTPADDING', (3, 0), (3, -1), 0),
        ('RIGHTPADDING', (3, 0), (3, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]
    # Divider only on non-spanned body rows (skip footer/difference spans).
    for r_i in range(nrows):
        if r_i in span_row_idxs:
            continue
        if show_header and r_i == 0:
            continue
        ts.append(('LINEBEFORE', (4, r_i), (4, r_i), 0.4, colors.HexColor('#cccccc')))
    if show_header and nrows > 0:
        ts.extend([
            ('BACKGROUND', (0, 0), (2, 0), colors.HexColor('#1a1a1a')),
            ('BACKGROUND', (4, 0), (6, 0), colors.HexColor('#1a1a1a')),
            ('TEXTCOLOR', (0, 0), (2, 0), colors.white),
            ('TEXTCOLOR', (4, 0), (6, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Times-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 7),
            ('LINEABOVE', (0, 0), (2, 0), 0.5, BORDER),
            ('LINEABOVE', (4, 0), (6, 0), 0.5, BORDER),
            ('LINEBELOW', (0, 0), (2, 0), 0.5, BORDER),
            ('LINEBELOW', (4, 0), (6, 0), 0.5, BORDER),
        ])
        body_start = 1
    else:
        body_start = 0

    def _cell_has_content(cell: Any) -> bool:
        if cell is None or cell == '':
            return False
        if isinstance(cell, Paragraph):
            return bool(str(getattr(cell, 'text', '') or '').strip())
        return bool(str(cell).strip())

    for r_i in range(body_start, nrows):
        if r_i in span_row_idxs:
            continue
        row = data[r_i] if r_i < len(data) else []
        # Skip gray amount fill on fully empty padded sides (avoids a gray bar in the gap).
        if any(_cell_has_content(row[c]) for c in (0, 1, 2) if c < len(row)):
            ts.append(('BACKGROUND', (2, r_i), (2, r_i), GRAY))
        if any(_cell_has_content(row[c]) for c in (4, 5, 6) if c < len(row)):
            ts.append(('BACKGROUND', (6, r_i), (6, r_i), GRAY))

    hl = totals_row_index if totals_row_index is not None else (nrows - 1 if highlight_last and nrows > 0 else None)
    if hl is not None and 0 <= hl < nrows:
        ts.append(('LINEABOVE', (0, hl), (2, hl), 1.0, colors.black))
        ts.append(('LINEBELOW', (0, hl), (2, hl), 1.0, colors.black))
        ts.append(('LINEABOVE', (4, hl), (6, hl), 1.0, colors.black))
        ts.append(('LINEBELOW', (4, hl), (6, hl), 1.0, colors.black))
        ts.append(('TOPPADDING', (0, hl), (-1, hl), 5))
        ts.append(('BOTTOMPADDING', (0, hl), (-1, hl), 5))
        ts.append(('BACKGROUND', (2, hl), (2, hl), GRAY))
        ts.append(('BACKGROUND', (6, hl), (6, hl), GRAY))

    for row_idx, c0, c1 in span_rows or ():
        if 0 <= row_idx < nrows:
            ts.append(('SPAN', (c0, row_idx), (c1, row_idx)))
            ts.append(('TOPPADDING', (0, row_idx), (-1, row_idx), 6))
            ts.append(('BOTTOMPADDING', (0, row_idx), (-1, row_idx), 4))
            if c1 < 6:
                # Difference row: amount stays in last column.
                ts.append(('ALIGN', (6, row_idx), (6, row_idx), 'RIGHT'))
                ts.append(('LINEABOVE', (0, row_idx), (6, row_idx), 0.8, BORDER))
            else:
                ts.append(('TOPPADDING', (0, row_idx), (-1, row_idx), 8))

    t.setStyle(TableStyle(ts))
    return t


def _balance_sheet_pdf_append_footer(elements: List[Any], foot_style: ParagraphStyle) -> None:
    elements.append(Spacer(1, 10))
    elements.append(Paragraph(
        'Computer-generated from the general ledger and chart of accounts. '
        'Current period earnings are included in equity when applicable. No signature is required.',
        foot_style,
    ))


def _build_balance_sheet_excel(ctx: Dict[str, Any]) -> Optional[bytes]:
    """Balance sheet as a single-sheet .xlsx."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
    except ImportError:
        return None

    assets = list(ctx.get('asset_accounts') or [])
    liabilities = list(ctx.get('liability_accounts') or [])
    equities = list(ctx.get('equity_accounts') or [])
    total_assets = float(ctx.get('total_assets') or 0)
    total_liabilities = float(ctx.get('total_liabilities') or 0)
    total_equity = float(ctx.get('total_equity') or 0)
    lpe = float(ctx.get('liabilities_plus_equity') or 0)
    diff = float(ctx.get('difference') or 0)

    thin = Side(style='thin', color='CCCCCC')
    box = Border(left=thin, right=thin, top=thin, bottom=thin)
    hdr_fill = PatternFill(start_color='1a1a1a', end_color='1a1a1a', fill_type='solid')
    hdr_font = Font(bold=True, color='FFFFFF', size=10)
    amt_fill = PatternFill(start_color='E8E8E8', end_color='E8E8E8', fill_type='solid')
    sec_font = Font(bold=True, size=10)
    grp_font = Font(bold=True, size=10)
    wb = Workbook()
    ws = wb.active
    ws.title = 'Balance Sheet'
    co = str(ctx.get('company_name') or 'Company')
    ws['A1'] = co
    ws['A1'].font = Font(bold=True, size=13)
    ws.merge_cells('A1:C1')
    as_of = str(ctx.get('as_of_date_display') or ctx.get('as_of_date') or '')
    ws['A2'] = f'Balance sheet as at {as_of}' if as_of else 'Balance sheet'
    ws.merge_cells('A2:C2')
    ws['A3'] = f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    ws.merge_cells('A3:C3')
    r = 5
    for c, h in enumerate(['Ref.', 'Description', 'Amount'], 1):
        cell = ws.cell(row=r, column=c, value=h)
        cell.fill = hdr_fill
        cell.font = hdr_font
        cell.border = box
        cell.alignment = Alignment(horizontal='right' if c == 3 else 'left', wrap_text=True)
    r += 1

    def wr_row(ref: str, desc: str, amt: Optional[float], bold: bool = False, group: bool = False) -> None:
        nonlocal r
        f = sec_font if bold else (grp_font if group else Font(size=10))
        ws.cell(row=r, column=1, value=ref).font = f
        ws.cell(row=r, column=2, value=desc).font = f
        if amt is None:
            ws.cell(row=r, column=3, value='')
        else:
            ws.cell(row=r, column=3, value=round(float(amt), 2)).font = f
        for c in range(1, 4):
            ws.cell(row=r, column=c).border = box
            if c == 3:
                ws.cell(row=r, column=c).alignment = Alignment(horizontal='right')
                ws.cell(row=r, column=c).fill = amt_fill
        r += 1

    def wr_section(title: str) -> None:
        wr_row('', title.upper(), None, bold=True)

    def wr_lines(rows: List[Dict[str, Any]]) -> None:
        if not rows:
            wr_row('', 'No accounts in this section', None)
            return
        for row in rows:
            amt = float(row.get('amount') or 0)
            show_amt = None if (row.get('is_group') and amt == 0) else amt
            wr_row(
                str(row.get('code') or ''),
                _balance_sheet_row_label(row),
                show_amt,
                group=bool(row.get('is_group')),
            )

    wr_section('Assets')
    wr_lines(assets)
    wr_row('', 'Total assets', total_assets, bold=True)
    r += 1
    wr_section('Liabilities')
    wr_lines(liabilities)
    wr_row('', 'Total liabilities', total_liabilities, bold=True)
    r += 1
    wr_section('Equity')
    wr_lines(equities)
    wr_row('', 'Total equity', total_equity, bold=True)
    r += 1
    wr_row('', 'Total liabilities and equity', lpe, bold=True)
    r += 1
    wr_row('', 'Difference (assets − liabilities and equity)', diff, bold=True)
    ws.column_dimensions['A'].width = 14
    ws.column_dimensions['B'].width = 48
    ws.column_dimensions['C'].width = 18
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

@bp.route('/accounts')
def chart_of_accounts_list():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _apply_db():
        return redirect(url_for('dashboard.dashboard'))
    return render_template('accounts/chart_of_accounts_list.html', account_types=ChartOfAccounts.ACCOUNT_TYPES)


def _build_chart_of_accounts_excel(accounts: List[Dict[str, Any]]) -> Optional[bytes]:
    """Flat Chart of Accounts list as .xlsx (matches list-view columns)."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
    except ImportError:
        return None
    wb = Workbook()
    ws = wb.active
    ws.title = 'Chart of Accounts'
    header_font = Font(bold=True, color='FFFFFF')
    header_fill = PatternFill('solid', fgColor='1A56A4')
    thin = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1'),
    )
    headers = [
        'Sl.No', 'Code', 'Name', 'Type', 'Parent Code', 'Parent Name',
        'Postable', 'Currency', 'Status', 'Account ID',
    ]
    ws['A1'] = 'Chart of Accounts'
    ws['A1'].font = Font(bold=True, size=14, color='1A56A4')
    ws.merge_cells('A1:J1')
    ws['A2'] = f"Generated by: {session.get('user') or 'web'} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    ws.merge_cells('A2:J2')
    for col, h in enumerate(headers, start=1):
        cell = ws.cell(row=4, column=col, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = thin
    rows = sorted(
        [a for a in (accounts or []) if (a.get('code') or '').strip()],
        key=lambda a: str(a.get('code') or '').upper(),
    )
    for i, a in enumerate(rows, start=1):
        r = 4 + i
        postable = a.get('is_postable')
        if postable is True or str(postable).strip() in ('1', 'Y', 'YES', 'TRUE'):
            postable_s = 'Yes'
        elif postable is False or str(postable).strip() in ('0', 'N', 'NO', 'FALSE'):
            postable_s = 'No'
        else:
            postable_s = 'Yes' if postable else 'No'
        values = [
            i,
            str(a.get('code') or '').strip(),
            str(a.get('name') or '').strip(),
            str(a.get('type') or '').strip().upper(),
            str(a.get('parent_code') or '').strip(),
            str(a.get('parent_name') or '').strip(),
            postable_s,
            str(a.get('currency') or '').strip(),
            str(a.get('status') or '').strip().upper(),
            a.get('account_id'),
        ]
        for col, val in enumerate(values, start=1):
            cell = ws.cell(row=r, column=col, value=val)
            cell.border = thin
            if col in (1, 7, 8, 10):
                cell.alignment = Alignment(horizontal='center')
    widths = [8, 14, 42, 12, 14, 32, 10, 10, 12, 12]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.auto_filter.ref = f'A4:J{4 + len(rows)}'
    ws.freeze_panes = 'A5'
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@bp.route('/accounts/chart-of-accounts/export-excel', methods=['GET'])
def chart_of_accounts_excel():
    """Chart of Accounts .xlsx download."""
    if not session.get('user'):
        return Response('Not authenticated', status=401, mimetype='text/plain')
    if not _apply_db():
        return Response('Database/location not assigned.', status=403, mimetype='text/plain')
    try:
        accounts = get_all_chart_of_accounts(db_key=None, raise_on_error=True) or []
    except Exception as e:
        return Response(f'Failed to load accounts: {e}', status=500, mimetype='text/plain')
    xlsx_bytes = _build_chart_of_accounts_excel(accounts)
    if xlsx_bytes is None:
        return Response('Excel export requires openpyxl. Install with: pip install openpyxl', status=500, mimetype='text/plain')
    filename = f"chart_of_accounts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return Response(
        xlsx_bytes,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )


def _parse_account_ledger_party_filter() -> Tuple[Optional[str], Optional[str]]:
    """Optional party filter from query string (SUPPLIER/CUSTOMER + code)."""
    pt = (request.args.get('party_type') or '').strip().upper()
    pc = (request.args.get('party_code') or '').strip()
    if pt not in ('SUPPLIER', 'CUSTOMER'):
        pt = ''
    if not pc:
        return None, None
    return (pt or None), pc


def _account_ledger_party_display(
    party_type: Optional[str],
    party_code: Optional[str],
    suppliers: List[Dict[str, Any]],
    customers: List[Dict[str, Any]],
) -> str:
    if not party_code:
        return ''
    pt = (party_type or '').upper()
    code = str(party_code).strip()
    if pt == 'SUPPLIER':
        for s in suppliers or []:
            if str(s.get('suppliercode') or '').strip() == code:
                return f"{code} — {str(s.get('suppliername') or '').strip()}"
    elif pt == 'CUSTOMER':
        for c in customers or []:
            if str(c.get('customercode') or '').strip() == code:
                return f"{code} — {str(c.get('customername') or '').strip()}"
    label = pt.title() if pt else 'Party'
    return f'{label} {code}'.strip()


@bp.route('/accounts/account-ledger', methods=['GET'])
def account_ledger_page():
    """Account ledger: choose any chart account and view GL lines for a date range."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _apply_db():
        return redirect(url_for('dashboard.dashboard'))
    try:
        ensure_default_party_accounts()
    except Exception:
        pass
    try:
        ensure_gl_tables()
    except Exception:
        pass
    all_accounts = ChartOfAccounts.get_all(limit=10000) or []
    all_accounts = sorted([a for a in all_accounts if (a.get('code') or '').strip()], key=lambda a: str(a.get('code') or '').upper())
    try:
        all_suppliers = get_supplier_list(location_code=None, search=None, limit=15000, row_cap=20000) or []
    except Exception:
        all_suppliers = []
    all_suppliers = sorted(all_suppliers, key=lambda s: str(s.get('suppliercode') or ''))
    try:
        all_customers = get_customers_for_journal_party_select(limit=20000) or []
    except Exception:
        all_customers = []
    all_customers = sorted(all_customers, key=lambda c: str(c.get('customercode') or ''))
    _aid = (request.args.get('account_id') or '').strip()
    account_id = None
    if _aid:
        try:
            account_id = int(_aid)
        except ValueError:
            account_id = None
    date_from = _parse_iso_date(request.args.get('date_from', ''))
    date_to = _parse_iso_date(request.args.get('date_to', ''))
    party_type, party_code = _parse_account_ledger_party_filter()
    selected_party_display = _account_ledger_party_display(party_type, party_code, all_suppliers, all_customers)
    account = None
    ledger_error = None
    ledger = {'account_code': '', 'date_from': None, 'date_to': None, 'opening_balance': 0.0, 'total_debit': 0.0, 'total_credit': 0.0, 'closing_balance': 0.0, 'lines': []}
    if account_id:
        account = ChartOfAccounts.get_by_id(account_id)
        if not account:
            flash('Account not found.', 'error')
        else:
            code = (account.get('code') or '').strip()
            if not code:
                flash('Account has no code.', 'error')
                account = None
            else:
                try:
                    ledger = get_account_ledger(
                        code,
                        date_from=date_from or None,
                        date_to=date_to or None,
                        party_type=party_type,
                        party_code=party_code,
                    )
                except Exception as e:
                    ledger_error = str(e)
    return render_template(
        'accounts/account_ledger.html',
        account=account,
        ledger=ledger,
        all_accounts=all_accounts,
        all_suppliers=all_suppliers,
        all_customers=all_customers,
        date_from=ledger.get('date_from') or date_from,
        date_to=ledger.get('date_to') or date_to,
        selected_account_id=account_id,
        selected_party_type=party_type or '',
        selected_party_code=party_code or '',
        selected_party_display=selected_party_display,
        ledger_error=ledger_error,
    )

@bp.route('/accounts/main-account-ledger', methods=['GET'])
def main_account_ledger():
    """Tree-style GL under a selected root account: group rollups and postable detail lines."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _apply_db():
        return redirect(url_for('dashboard.dashboard'))
    try:
        ensure_gl_tables()
    except Exception:
        pass
    coa_rows = get_all_chart_of_accounts() or []
    coa_list = sorted([a for a in coa_rows if (a.get('status') or 'ACTIVE') == 'ACTIVE' and (a.get('code') or '').strip()], key=lambda a: str(a.get('code') or '').upper())
    _aid = (request.args.get('account_id') or '').strip()
    account_id = None
    if _aid:
        try:
            account_id = int(_aid)
        except ValueError:
            account_id = None
    date_from = _parse_iso_date(request.args.get('date_from', ''))
    date_to = _parse_iso_date(request.args.get('date_to', ''))
    root = None
    report_error = None
    dfn, dtn = (date_from, date_to)
    if account_id:
        res = get_main_account_ledger_data(account_id, date_from=date_from, date_to=date_to)
        report_error = res.get('error')
        root = res.get('root')
        dfn = res.get('date_from')
        dtn = res.get('date_to')
    selected_root_display = ''
    if account_id is not None:
        for _a in coa_list:
            try:
                if int(_a.get('account_id') or 0) == int(account_id):
                    selected_root_display = f"{(_a.get('code') or '').strip()} — {(_a.get('name') or '').strip()}"
                    break
            except (TypeError, ValueError):
                continue
    return render_template('accounts/main_account_ledger.html', coa_list=coa_list, selected_account_id=account_id, selected_root_display=selected_root_display, root=root, date_from=dfn, date_to=dtn, report_error=report_error)

def _parse_main_ledger_request():
    """Shared query args for main account ledger PDF/Excel."""
    _aid = (request.args.get('account_id') or '').strip()
    account_id = None
    if _aid:
        try:
            account_id = int(_aid)
        except ValueError:
            account_id = None
    date_from = _parse_iso_date(request.args.get('date_from', ''))
    date_to = _parse_iso_date(request.args.get('date_to', ''))
    return (account_id, date_from, date_to)

@bp.route('/accounts/main-account-ledger/pdf', methods=['GET'])
def main_account_ledger_pdf():
    """Main account ledger PDF (A4): tree rollups and postable GL detail sections."""
    if not session.get('user'):
        return Response('Not authenticated', status=401, mimetype='text/plain')
    if not _apply_db():
        return Response('Database/location not assigned.', status=403, mimetype='text/plain')
    if not REPORTLAB_AVAILABLE:
        return Response('PDF is not available (install reportlab).', status=500, mimetype='text/plain')
    try:
        ensure_gl_tables()
    except Exception:
        pass
    account_id, date_from, date_to = _parse_main_ledger_request()
    if not account_id:
        return Response('account_id is required.', status=400, mimetype='text/plain')
    acc = ChartOfAccounts.get_by_id(account_id)
    if not acc:
        return Response('Account not found.', status=404, mimetype='text/plain')
    root_code = (acc.get('code') or '').strip()
    root_name = (acc.get('name') or '').strip()
    res = get_main_account_ledger_data(account_id, date_from=date_from, date_to=date_to)
    if res.get('error'):
        return Response(str(res.get('error')), status=400, mimetype='text/plain')
    root = res.get('root')
    if not root:
        return Response('No tree data.', status=400, mimetype='text/plain')
    dfn = str(res.get('date_from') or '')
    dtn = str(res.get('date_to') or '')
    pdf_bytes = _build_main_account_ledger_pdf(root, dfn, dtn, root_code, root_name)
    if not pdf_bytes:
        return Response('Failed to generate PDF.', status=500, mimetype='text/plain')
    safe = ''.join((c for c in root_code if c.isalnum() or c in ('-', '_')))[:24] or 'main'
    filename = f"main_account_ledger_{safe}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return Response(pdf_bytes, mimetype='application/pdf', headers={'Content-Disposition': f'inline; filename="{filename}"'})

@bp.route('/accounts/main-account-ledger/export-excel', methods=['GET'])
def main_account_ledger_excel():
    """Main account ledger as .xlsx (tree sheet + GL lines sheet)."""
    if not session.get('user'):
        return Response('Not authenticated', status=401, mimetype='text/plain')
    if not _apply_db():
        return Response('Database/location not assigned.', status=403, mimetype='text/plain')
    try:
        ensure_gl_tables()
    except Exception:
        pass
    account_id, date_from, date_to = _parse_main_ledger_request()
    if not account_id:
        return Response('account_id is required.', status=400, mimetype='text/plain')
    acc = ChartOfAccounts.get_by_id(account_id)
    if not acc:
        return Response('Account not found.', status=404, mimetype='text/plain')
    root_code = (acc.get('code') or '').strip()
    root_name = (acc.get('name') or '').strip()
    res = get_main_account_ledger_data(account_id, date_from=date_from, date_to=date_to)
    if res.get('error'):
        return Response(str(res.get('error')), status=400, mimetype='text/plain')
    root = res.get('root')
    if not root:
        return Response('No tree data.', status=400, mimetype='text/plain')
    dfn = str(res.get('date_from') or '')
    dtn = str(res.get('date_to') or '')
    xlsx_bytes = _build_main_account_ledger_excel(root, dfn, dtn, root_code, root_name)
    if xlsx_bytes is None:
        return Response('Excel export requires openpyxl. Install with: pip install openpyxl', status=500, mimetype='text/plain')
    safe = ''.join((c for c in root_code if c.isalnum() or c in ('-', '_')))[:24] or 'main'
    filename = f"main_account_ledger_{safe}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return Response(xlsx_bytes, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers={'Content-Disposition': f'attachment; filename="{filename}"'})

@bp.route('/accounts/ledger/<int:account_id>', methods=['GET'])
def account_ledger(account_id: int):
    """Back-compat: same as Account ledger page with account pre-selected."""
    rkw: dict = {'account_id': account_id}
    df = (request.args.get('date_from') or '').strip()
    dt = (request.args.get('date_to') or '').strip()
    if df:
        rkw['date_from'] = df
    if dt:
        rkw['date_to'] = dt
    pt, pc = _parse_account_ledger_party_filter()
    if pc:
        if pt:
            rkw['party_type'] = pt
        rkw['party_code'] = pc
    return redirect(url_for('accounts.account_ledger_page', **rkw))

@bp.route('/accounts/account-ledger/pdf', methods=['GET'])
def account_ledger_pdf():
    """Account ledger as PDF (portrait A4, same visual system as GRN). Opens inline in the browser."""
    if not session.get('user'):
        return Response('Not authenticated', status=401, mimetype='text/plain')
    if not _apply_db():
        return Response('Database/location not assigned.', status=403, mimetype='text/plain')
    if not REPORTLAB_AVAILABLE:
        return Response('PDF is not available (install reportlab).', status=500, mimetype='text/plain')
    try:
        ensure_gl_tables()
    except Exception:
        pass
    _aid = (request.args.get('account_id') or '').strip()
    account_id = None
    if _aid:
        try:
            account_id = int(_aid)
        except ValueError:
            account_id = None
    if not account_id:
        return Response('account_id is required.', status=400, mimetype='text/plain')
    account = ChartOfAccounts.get_by_id(account_id)
    if not account:
        return Response('Account not found.', status=404, mimetype='text/plain')
    code = (account.get('code') or '').strip()
    if not code:
        return Response('Account has no code.', status=400, mimetype='text/plain')
    date_from = _parse_iso_date(request.args.get('date_from', ''))
    date_to = _parse_iso_date(request.args.get('date_to', ''))
    party_type, party_code = _parse_account_ledger_party_filter()
    try:
        ledger = get_account_ledger(
            code,
            date_from=date_from or None,
            date_to=date_to or None,
            party_type=party_type,
            party_code=party_code,
        )
    except Exception as e:
        return Response(f'Could not load ledger: {e}', status=500, mimetype='text/plain')
    df = str(ledger.get('date_from') or date_from or '—')
    dt = str(ledger.get('date_to') or date_to or '—')
    pdf_bytes = _build_account_ledger_pdf(account, ledger, df, dt)
    if not pdf_bytes:
        return Response('Failed to generate PDF.', status=500, mimetype='text/plain')
    safe = ''.join((c for c in code if c.isalnum() or c in ('-', '_')))[:28] or 'account'
    filename = f"account_ledger_{safe}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return Response(pdf_bytes, mimetype='application/pdf', headers={'Content-Disposition': f'inline; filename="{filename}"'})


def _build_account_ledger_excel(account: dict, ledger: dict, date_from: str, date_to: str) -> Optional[bytes]:
    """XLSX for a single GL account ledger (opening, lines, period totals)."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
    except ImportError:
        return None
    wb = Workbook()
    thin = Side(style='thin', color='CCCCCC')
    box = Border(left=thin, right=thin, top=thin, bottom=thin)
    hdr_fill = PatternFill(start_color='1a56a4', end_color='1a56a4', fill_type='solid')
    hdr_font = Font(bold=True, color='FFFFFF', size=10)
    sum_fill = PatternFill(start_color='EFF6FF', end_color='EFF6FF', fill_type='solid')
    open_fill = PatternFill(start_color='F8FAFC', end_color='F8FAFC', fill_type='solid')
    ws = wb.active
    ws.title = 'Account ledger'
    code = str(account.get('code') or '')
    name = str(account.get('name') or '')
    ws['A1'] = 'Account ledger'
    ws['A1'].font = Font(bold=True, size=12, color='1a56a4')
    ws.merge_cells('A1:K1')
    ws['A2'] = f'Account: {code} — {name}'
    ws['A3'] = f"Type: {account.get('type') or '—'} | Currency: {account.get('currency') or 'QAR'}"
    ws['A4'] = f"Period: {date_from or '—'} to {date_to or '—'}"
    ws['A5'] = f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    headers = [
        'Sl.No', 'Date', 'Voucher', 'Reference', 'Narration', 'Source',
        'Remarks (line)', 'Party', 'Debit', 'Credit', 'Balance',
    ]
    hrow = 7
    for c, h in enumerate(headers, 1):
        cell = ws.cell(row=hrow, column=c, value=h)
        cell.fill = hdr_fill
        cell.font = hdr_font
        cell.alignment = Alignment(horizontal='center' if c in (1, 9, 10, 11) else 'left', wrap_text=True)
        cell.border = box
    rr = hrow + 1
    opening = round(float(ledger.get('opening_balance') or 0), 2)
    ws.cell(row=rr, column=1, value='')
    ws.cell(row=rr, column=2, value=f'Opening balance (before {date_from or ""})')
    ws.merge_cells(start_row=rr, start_column=2, end_row=rr, end_column=8)
    ws.cell(row=rr, column=11, value=opening)
    for c in range(1, 12):
        cell = ws.cell(row=rr, column=c)
        cell.border = box
        cell.fill = open_fill
        if c >= 9:
            cell.alignment = Alignment(horizontal='right')
    rr += 1
    for idx, ln in enumerate(ledger.get('lines') or [], start=1):
        party_parts = []
        pn = str(ln.get('party_name') or '').strip()
        if pn:
            party = pn
        else:
            pt = str(ln.get('party_type') or '').strip()
            pc = str(ln.get('party_code') or '').strip()
            if pt:
                party_parts.append(pt)
            if pc:
                party_parts.append(pc)
            party = ' '.join(party_parts)
        ws.cell(row=rr, column=1, value=idx)
        ws.cell(row=rr, column=2, value=str(ln.get('voucher_date') or ''))
        ws.cell(row=rr, column=3, value=str(ln.get('voucher_no') or ''))
        ws.cell(row=rr, column=4, value=str(ln.get('reference_no') or ''))
        ws.cell(row=rr, column=5, value=str(ln.get('narration') or ''))
        ws.cell(row=rr, column=6, value=str(ln.get('source') or ''))
        ws.cell(row=rr, column=7, value=str(ln.get('remarks') or ''))
        ws.cell(row=rr, column=8, value=party)
        ws.cell(row=rr, column=9, value=round(float(ln.get('debit') or 0), 2))
        ws.cell(row=rr, column=10, value=round(float(ln.get('credit') or 0), 2))
        ws.cell(row=rr, column=11, value=round(float(ln.get('running_balance') or 0), 2))
        for c in range(1, 12):
            cell = ws.cell(row=rr, column=c)
            cell.border = box
            if c in (1, 9, 10, 11):
                cell.alignment = Alignment(horizontal='right' if c > 1 else 'center')
        rr += 1
    if ledger.get('lines'):
        ws.cell(row=rr, column=1, value='')
        ws.cell(row=rr, column=2, value='Period totals / closing')
        ws.merge_cells(start_row=rr, start_column=2, end_row=rr, end_column=8)
        ws.cell(row=rr, column=9, value=round(float(ledger.get('total_debit') or 0), 2))
        ws.cell(row=rr, column=10, value=round(float(ledger.get('total_credit') or 0), 2))
        ws.cell(row=rr, column=11, value=round(float(ledger.get('closing_balance') or 0), 2))
        for c in range(1, 12):
            cell = ws.cell(row=rr, column=c)
            cell.border = box
            cell.fill = sum_fill
            cell.font = Font(bold=True, size=10)
            if c >= 9:
                cell.alignment = Alignment(horizontal='right')
    widths = {1: 8, 2: 12, 3: 16, 4: 14, 5: 28, 6: 12, 7: 18, 8: 16, 9: 12, 10: 12, 11: 12}
    for col, w in widths.items():
        ws.column_dimensions[get_column_letter(col)].width = w
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@bp.route('/accounts/account-ledger/export-excel', methods=['GET'])
def account_ledger_excel():
    """Account ledger as .xlsx download for the selected account and date range."""
    if not session.get('user'):
        return Response('Not authenticated', status=401, mimetype='text/plain')
    if not _apply_db():
        return Response('Database/location not assigned.', status=403, mimetype='text/plain')
    try:
        ensure_gl_tables()
    except Exception:
        pass
    _aid = (request.args.get('account_id') or '').strip()
    account_id = None
    if _aid:
        try:
            account_id = int(_aid)
        except ValueError:
            account_id = None
    if not account_id:
        return Response('account_id is required.', status=400, mimetype='text/plain')
    account = ChartOfAccounts.get_by_id(account_id)
    if not account:
        return Response('Account not found.', status=404, mimetype='text/plain')
    code = (account.get('code') or '').strip()
    if not code:
        return Response('Account has no code.', status=400, mimetype='text/plain')
    date_from = _parse_iso_date(request.args.get('date_from', ''))
    date_to = _parse_iso_date(request.args.get('date_to', ''))
    party_type, party_code = _parse_account_ledger_party_filter()
    try:
        ledger = get_account_ledger(
            code,
            date_from=date_from or None,
            date_to=date_to or None,
            party_type=party_type,
            party_code=party_code,
        )
    except Exception as e:
        return Response(f'Could not load ledger: {e}', status=500, mimetype='text/plain')
    df = str(ledger.get('date_from') or date_from or '—')
    dt = str(ledger.get('date_to') or date_to or '—')
    xlsx_bytes = _build_account_ledger_excel(account, ledger, df, dt)
    if xlsx_bytes is None:
        return Response('Excel export requires openpyxl. Install with: pip install openpyxl', status=500, mimetype='text/plain')
    safe = ''.join((c for c in code if c.isalnum() or c in ('-', '_')))[:28] or 'account'
    filename = f"account_ledger_{safe}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return Response(
        xlsx_bytes,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )


@bp.route('/accounts/supplier-ledger', methods=['GET'])
def supplier_ledger_page():
    """Supplier sub-ledger: LIABILITY GL lines with supplier party (same basis as AP), running balance (Cr−Dr)."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _apply_db():
        return redirect(url_for('dashboard.dashboard'))
    try:
        ensure_gl_tables()
    except Exception:
        pass
    all_suppliers = get_supplier_list(location_code=None, search=None, limit=15000, row_cap=20000) or []
    all_suppliers = sorted(all_suppliers, key=lambda s: str(s.get('suppliercode') or ''))
    raw_code = (request.args.get('supplier_code') or '').strip()
    date_from = _parse_iso_date(request.args.get('date_from', ''))
    date_to = _parse_iso_date(request.args.get('date_to', ''))
    supplier = None
    ledger_error = None
    ledger = {'supplier_code': '', 'date_from': None, 'date_to': None, 'gl_account_filter': None, 'liability_only': False, 'opening_balance': 0.0, 'total_debit': 0.0, 'total_credit': 0.0, 'closing_balance': 0.0, 'lines': []}
    if raw_code:
        supplier = get_supplier_master_by_code(raw_code)
        if not supplier:
            supplier = {'suppliercode': raw_code, 'suppliername': '— (not in supplier master)', 'payableaccount': '—'}
        try:
            ledger = get_supplier_ledger(raw_code, date_from=date_from or None, date_to=date_to or None, gl_account_code=None, liability_accounts_only=True)
        except Exception as e:
            ledger_error = str(e)
    return render_template('accounts/supplier_ledger.html', supplier=supplier, ledger=ledger, all_suppliers=all_suppliers, date_from=ledger.get('date_from') or date_from, date_to=ledger.get('date_to') or date_to, selected_supplier_code=raw_code, ledger_error=ledger_error)

@bp.route('/accounts/supplier-ledger/pdf', methods=['GET'])
def supplier_ledger_pdf():
    """Supplier ledger PDF (portrait A4, GRN-style). Opens inline."""
    if not session.get('user'):
        return Response('Not authenticated', status=401, mimetype='text/plain')
    if not _apply_db():
        return Response('Database/location not assigned.', status=403, mimetype='text/plain')
    if not REPORTLAB_AVAILABLE:
        return Response('PDF is not available (install reportlab).', status=500, mimetype='text/plain')
    try:
        ensure_gl_tables()
    except Exception:
        pass
    raw_code = (request.args.get('supplier_code') or '').strip()
    if not raw_code:
        return Response('supplier_code is required.', status=400, mimetype='text/plain')
    sup = get_supplier_master_by_code(raw_code) or {'suppliercode': raw_code, 'suppliername': '—', 'payableaccount': '—'}
    date_from = _parse_iso_date(request.args.get('date_from', ''))
    date_to = _parse_iso_date(request.args.get('date_to', ''))
    try:
        ledger = get_supplier_ledger(raw_code, date_from=date_from or None, date_to=date_to or None, gl_account_code=None, liability_accounts_only=True)
    except Exception as e:
        return Response(f'Could not load supplier ledger: {e}', status=500, mimetype='text/plain')
    df = str(ledger.get('date_from') or date_from or '—')
    dt = str(ledger.get('date_to') or date_to or '—')
    pdf_bytes = _build_supplier_ledger_pdf(sup, ledger, df, dt)
    if not pdf_bytes:
        return Response('Failed to generate PDF.', status=500, mimetype='text/plain')
    sc = str(sup.get('suppliercode') or raw_code)[:20]
    safe = ''.join((c for c in sc if c.isalnum() or c in ('-', '_')))[:28] or 'supplier'
    filename = f"supplier_ledger_{safe}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return Response(pdf_bytes, mimetype='application/pdf', headers={'Content-Disposition': f'inline; filename="{filename}"'})

@bp.route('/accounts/customer-ledger', methods=['GET'])
def customer_ledger_page():
    """Customer sub-ledger: ASSET GL lines with customer party, running balance (Dr−Cr)."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _apply_db():
        return redirect(url_for('dashboard.dashboard'))
    try:
        ensure_gl_tables()
    except Exception:
        pass
    all_customers = get_customers_for_journal_party_select(limit=20000) or []
    all_customers = sorted(all_customers, key=lambda c: str(c.get('customercode') or ''))
    raw_code = (request.args.get('customer_code') or '').strip()
    date_from = _parse_iso_date(request.args.get('date_from', ''))
    date_to = _parse_iso_date(request.args.get('date_to', ''))
    customer = None
    ledger_error = None
    ledger = {'customer_code': '', 'date_from': None, 'date_to': None, 'gl_account_filter': None, 'asset_only': False, 'opening_balance': 0.0, 'total_debit': 0.0, 'total_credit': 0.0, 'closing_balance': 0.0, 'lines': []}
    if raw_code:
        customer = get_customer_master_by_code(raw_code)
        if not customer:
            customer = {'customercode': raw_code, 'customername': '— (not in customer master)', 'receivableaccount': '—'}
        try:
            ledger = get_customer_ledger(raw_code, date_from=date_from or None, date_to=date_to or None, gl_account_code=None, asset_accounts_only=True)
        except Exception as e:
            ledger_error = str(e)
    return render_template('accounts/customer_ledger.html', customer=customer, ledger=ledger, all_customers=all_customers, date_from=ledger.get('date_from') or date_from, date_to=ledger.get('date_to') or date_to, selected_customer_code=raw_code, ledger_error=ledger_error)

@bp.route('/accounts/customer-ledger/pdf', methods=['GET'])
def customer_ledger_pdf():
    """Customer ledger PDF (portrait A4). Opens inline."""
    if not session.get('user'):
        return Response('Not authenticated', status=401, mimetype='text/plain')
    if not _apply_db():
        return Response('Database/location not assigned.', status=403, mimetype='text/plain')
    if not REPORTLAB_AVAILABLE:
        return Response('PDF is not available (install reportlab).', status=500, mimetype='text/plain')
    try:
        ensure_gl_tables()
    except Exception:
        pass
    raw_code = (request.args.get('customer_code') or '').strip()
    if not raw_code:
        return Response('customer_code is required.', status=400, mimetype='text/plain')
    cust = get_customer_master_by_code(raw_code) or {'customercode': raw_code, 'customername': '—', 'receivableaccount': '—'}
    date_from = _parse_iso_date(request.args.get('date_from', ''))
    date_to = _parse_iso_date(request.args.get('date_to', ''))
    try:
        ledger = get_customer_ledger(raw_code, date_from=date_from or None, date_to=date_to or None, gl_account_code=None, asset_accounts_only=True)
    except Exception as e:
        return Response(f'Could not load customer ledger: {e}', status=500, mimetype='text/plain')
    df = str(ledger.get('date_from') or date_from or '—')
    dt = str(ledger.get('date_to') or date_to or '—')
    pdf_bytes = _build_customer_ledger_pdf(cust, ledger, df, dt)
    if not pdf_bytes:
        return Response('Failed to generate PDF.', status=500, mimetype='text/plain')
    cc = str(cust.get('customercode') or raw_code)[:20]
    safe = ''.join((c for c in cc if c.isalnum() or c in ('-', '_')))[:28] or 'customer'
    filename = f"customer_ledger_{safe}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return Response(pdf_bytes, mimetype='application/pdf', headers={'Content-Disposition': f'inline; filename="{filename}"'})

@bp.route('/accounts/api/chart')
def api_chart_list():
    """JSON list of all accounts (reference model: account_id, code, name, type, parent_id, is_postable, currency, status)."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    if not _apply_db():
        return jsonify({'success': False, 'error': 'Database/location not assigned. Please contact IT.'}, 403)
    try:
        accounts = get_all_chart_of_accounts(db_key=None, raise_on_error=True)
        return jsonify({'success': True, 'accounts': accounts})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}, 500)

@bp.route('/accounts/api/chart/suggest-code', methods=['GET'])
def api_chart_suggest_code():
    """Suggest next free account code from database (type + optional parent)."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    if not _apply_db():
        return jsonify({'success': False, 'error': 'Database/location not assigned. Please contact IT.'}, 403)
    account_type = (request.args.get('type') or '').strip().upper()
    if not account_type:
        return jsonify({'success': False, 'error': 'Account type is required.'}, 400)
    parent_id = None
    raw_parent = (request.args.get('parent_id') or '').strip()
    if raw_parent:
        try:
            parent_id = int(raw_parent)
        except (TypeError, ValueError):
            parent_id = None
    suggested = suggest_next_chart_of_account_code(account_type, parent_id)
    if suggested and chart_of_account_code_exists(suggested):
        suggested = suggest_next_chart_of_account_code_after(suggested, account_type, parent_id)
    return jsonify({'success': True, 'code': suggested})


@bp.route('/accounts/api/chart/create-once', methods=['GET'])
def api_chart_create_once():
    """Issue a fresh create-once token (e.g. when opening New / Sub-account modal)."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    if not _apply_db():
        return jsonify({'success': False, 'error': 'Database/location not assigned. Please contact IT.'}, 403)
    return jsonify({'success': True, 'create_once': _coa_issue_create_once_token()})


@bp.route('/accounts/api/chart/<int:account_id>')
def api_chart_get(account_id: int):
    """JSON single account by account_id."""
    if not session.get('user'):
        return jsonify({'error': 'Not authenticated'}, 401)
    if not _apply_db():
        return jsonify({'success': False, 'error': 'Database/location not assigned. Please contact IT.'}, 403)
    account = ChartOfAccounts.get_by_id(account_id)
    if not account:
        return jsonify({'error': 'Account not found'}, 404)
    return jsonify({'success': True, 'account': account})

@bp.route('/accounts/api/chart', methods=['POST'])
def api_chart_create():
    """Create account from JSON (reference model: code, name, type, parent_id, is_postable, currency, status)."""
    if not session.get('user'):
        return jsonify({'error': 'Not authenticated'}, 401)
    if not _apply_db():
        return jsonify({'success': False, 'error': 'Database/location not assigned. Please contact IT.'}, 403)
    data = request.get_json(silent=True) or {}
    code = normalize_coa_code(data.get('code') or '')
    name = (data.get('name') or '').strip()
    account_type = (data.get('type') or '').strip().upper()
    parent_id = data.get('parent_id')
    if parent_id is not None and parent_id != '':
        try:
            parent_id = int(parent_id)
        except (TypeError, ValueError):
            parent_id = None
    else:
        parent_id = None
    is_postable = data.get('is_postable', True)
    if isinstance(is_postable, str):
        is_postable = is_postable.upper() in ('Y', '1', 'YES', 'TRUE')
    currency = (data.get('currency') or 'USD').strip()[:3]
    status = (data.get('status') or ChartOfAccounts.STATUS_ACTIVE).strip().upper()
    coa_log_ctx = {'code': code, 'name': name, 'type': account_type, 'parent_id': parent_id, 'user': session.get('user')}
    if not code or not name or (not account_type):
        err = 'Code, name, and account type are required.'
        _coa_log_api_fail('POST /accounts/api/chart', 400, err, **coa_log_ctx)
        return jsonify({'success': False, 'error': err}, 400)
    if not _coa_verify_create_once(data.get('coa_once')):
        fresh = _coa_issue_create_once_token()
        err = 'Create form expired (coa_once invalid or missing).'
        _coa_log_api_fail('POST /accounts/api/chart', 400, err, coa_once_sent=bool((data.get('coa_once') or '').strip()), **coa_log_ctx)
        return jsonify({
            'success': False,
            'error': 'This create form expired (already used or opened in another tab). Close the dialog and open New account or + Sub-account again, then save once.',
            'create_once': fresh,
        }, 400)
    code, bumped_from = _coa_resolve_create_code(code, account_type, parent_id)
    coa_log_ctx['code'] = code
    if bumped_from:
        coa_log_ctx['bumped_from'] = bumped_from
    if chart_of_account_code_exists(code):
        suggested = suggest_next_chart_of_account_code_after(code, account_type, parent_id)
        err = f'Account code "{bumped_from or code}" already exists.'
        _coa_log_api_fail('POST /accounts/api/chart', 400, err, suggested_code=suggested, **coa_log_ctx)
        return jsonify({
            'success': False,
            'error': f'Account code "{bumped_from or code}" already exists. Use the suggested code or pick another.',
            'suggested_code': suggested,
            'create_once': session.get(_COA_CREATE_ONCE) or _coa_issue_create_once_token(),
        }, 400)
    try:
        account_id = ChartOfAccounts.create({'code': code, 'name': name, 'type': account_type, 'parent_id': parent_id, 'is_postable': is_postable, 'currency': currency, 'status': status})
        _coa_consume_create_once()
        fresh = _coa_issue_create_once_token()
        resp: Dict[str, Any] = {'success': True, 'account_id': account_id, 'code': code, 'create_once': fresh}
        if bumped_from:
            resp['message'] = f'Account created as {code} (code {bumped_from} was already in use).'
        print(f'[COA POST /accounts/api/chart] HTTP 200: created account_id={account_id!r} code={code!r} parent_id={parent_id!r}', flush=True)
        return jsonify(resp)
    except ValueError as e:
        err = str(e)
        _coa_log_api_fail('POST /accounts/api/chart', 400, err, exc='ValueError', **coa_log_ctx)
        return jsonify({
            'success': False,
            'error': err,
            'create_once': session.get(_COA_CREATE_ONCE) or _coa_issue_create_once_token(),
        }, 400)
    except Exception as e:
        err = str(e)
        if _coa_oracle_is_pk_violation(err):
            _sync_chart_of_accounts_sequence()
            pk_err = 'Could not assign a new account id (database sequence was out of sync). Please save again.'
            _coa_log_api_fail('POST /accounts/api/chart', 400, pk_err, exc=type(e).__name__, detail=err, **coa_log_ctx)
            try:
                account_id = ChartOfAccounts.create({'code': code, 'name': name, 'type': account_type, 'parent_id': parent_id, 'is_postable': is_postable, 'currency': currency, 'status': status})
                _coa_consume_create_once()
                fresh = _coa_issue_create_once_token()
                print(f'[COA POST /accounts/api/chart] HTTP 200: created after seq sync account_id={account_id!r} code={code!r}', flush=True)
                return jsonify({'success': True, 'account_id': account_id, 'code': code, 'create_once': fresh})
            except Exception as retry_exc:
                err = str(retry_exc)
                _coa_log_api_fail('POST /accounts/api/chart', 500, str(retry_exc), exc=type(retry_exc).__name__, detail=err, **coa_log_ctx)
                return jsonify({
                    'success': False,
                    'error': f'{pk_err} ({retry_exc})',
                    'create_once': session.get(_COA_CREATE_ONCE) or _coa_issue_create_once_token(),
                }, 500)
        if _coa_oracle_is_code_violation(err) or 'duplicate' in err.lower():
            suggested = suggest_next_chart_of_account_code_after(code, account_type, parent_id)
            bumped = normalize_coa_code(suggested)
            if bumped and bumped != code and not chart_of_account_code_exists(bumped):
                try:
                    account_id = ChartOfAccounts.create({'code': bumped, 'name': name, 'type': account_type, 'parent_id': parent_id, 'is_postable': is_postable, 'currency': currency, 'status': status})
                    _coa_consume_create_once()
                    fresh = _coa_issue_create_once_token()
                    print(f'[COA POST /accounts/api/chart] HTTP 200: created after bump account_id={account_id!r} code={bumped!r} (was {code!r})', flush=True)
                    return jsonify({
                        'success': True,
                        'account_id': account_id,
                        'code': bumped,
                        'message': f'Account created as {bumped} (code {code} was already in use).',
                        'create_once': fresh,
                    })
                except Exception as retry_exc:
                    err = str(retry_exc)
            dup_err = f'Account code "{code}" already exists.'
            _coa_log_api_fail('POST /accounts/api/chart', 400, dup_err, suggested_code=suggested, exc=type(e).__name__, detail=err, **coa_log_ctx)
            return jsonify({
                'success': False,
                'error': f'Account code "{code}" already exists. Use the suggested code or pick another.',
                'suggested_code': suggested,
                'create_once': session.get(_COA_CREATE_ONCE) or _coa_issue_create_once_token(),
            }, 400)
        _coa_log_api_fail('POST /accounts/api/chart', 500, err, exc=type(e).__name__, **coa_log_ctx)
        return jsonify({
            'success': False,
            'error': err,
            'create_once': session.get(_COA_CREATE_ONCE) or _coa_issue_create_once_token(),
        }, 500)

@bp.route('/accounts/api/chart/<int:account_id>', methods=['PUT', 'POST'])
def api_chart_update(account_id: int):
    """Update account from JSON by account_id."""
    if not session.get('user'):
        return jsonify({'error': 'Not authenticated'}, 401)
    if not _apply_db():
        return jsonify({'success': False, 'error': 'Database/location not assigned. Please contact IT.'}, 403)
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    account_type = (data.get('type') or '').strip().upper()
    parent_id = data.get('parent_id')
    if parent_id is not None and parent_id != '':
        try:
            parent_id = int(parent_id)
        except (TypeError, ValueError):
            parent_id = None
    else:
        parent_id = None
    is_postable = data.get('is_postable')
    if is_postable is not None and isinstance(is_postable, str):
        is_postable = is_postable.upper() in ('Y', '1', 'YES', 'TRUE')
    currency = (data.get('currency') or '').strip()[:3] or None
    status = (data.get('status') or '').strip().upper() or None
    try:
        ChartOfAccounts.update(account_id, {'name': name, 'type': account_type, 'parent_id': parent_id, 'is_postable': is_postable, 'currency': currency, 'status': status})
        return jsonify({'success': True})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}, 400)

@bp.route('/accounts/api/chart/<int:account_id>/delete', methods=['POST'])
def api_chart_delete(account_id: int):
    """Delete account by account_id."""
    if not session.get('user'):
        return jsonify({'error': 'Not authenticated'}, 401)
    if not _apply_db():
        return jsonify({'success': False, 'error': 'Database/location not assigned. Please contact IT.'}, 403)
    try:
        ChartOfAccounts.delete(account_id)
        return jsonify({'success': True})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}, 400)

@bp.route('/accounts/chart/new', methods=['GET', 'POST'])
def chart_of_accounts_create():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _apply_db():
        return redirect(url_for('dashboard.dashboard'))
    all_rows = ChartOfAccounts.get_all(limit=0, offset=0)
    tree = ChartOfAccounts.get_tree()
    parent_options = _flatten_coa_tree_for_parent_select(tree, _coa_exclude_ids_for_parent_picker(all_rows, None))
    if request.method == 'POST':
        code = (request.form.get('code') or '').strip()
        name = (request.form.get('name') or '').strip()
        account_type = (request.form.get('type') or '').strip().upper()
        parent_id = request.form.get('parent_id')
        parent_id = int(parent_id) if parent_id else None
        is_postable = request.form.get('is_postable') == 'Y'
        currency = (request.form.get('currency') or 'USD').strip()[:3]
        status = (request.form.get('status') or ChartOfAccounts.STATUS_ACTIVE).strip().upper()
        do_create = True
        if not code or not name or (not account_type):
            flash('Code, name, and account type are required.', 'error')
            do_create = False
        elif not _coa_verify_create_once(request.form.get('coa_once')):
            flash('That save was skipped (duplicate submit or session lock). Reload the page and submit once.', 'warning')
            do_create = False
        if do_create:
            code = normalize_coa_code(code)
            code, bumped_from = _coa_resolve_create_code(code, account_type, parent_id)
            try:
                ChartOfAccounts.create({'code': code, 'name': name, 'type': account_type, 'parent_id': parent_id, 'is_postable': is_postable, 'currency': currency, 'status': status})
                _coa_consume_create_once()
                if bumped_from:
                    flash(f'Account created as {code} (code {bumped_from} was already in use).', 'success')
                else:
                    flash('Account created.', 'success')
                return redirect(url_for('accounts.chart_of_accounts_list'))
            except ValueError as e:
                flash(str(e), 'error')
    coa_html_once = _coa_issue_create_once_token()
    return render_template('accounts/chart_of_accounts_form.html', account=None, parent_options=parent_options, account_types=ChartOfAccounts.ACCOUNT_TYPES, coa_html_once=coa_html_once)

@bp.route('/accounts/chart/<int:account_id>/edit', methods=['GET', 'POST'])
def chart_of_accounts_edit(account_id: int):
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _apply_db():
        return redirect(url_for('dashboard.dashboard'))
    account = ChartOfAccounts.get_by_id(account_id)
    if not account:
        flash('Account not found.', 'error')
        return redirect(url_for('accounts.chart_of_accounts_list'))
    all_rows = ChartOfAccounts.get_all(limit=0, offset=0)
    tree = ChartOfAccounts.get_tree()
    parent_options = _flatten_coa_tree_for_parent_select(tree, _coa_exclude_ids_for_parent_picker(all_rows, account_id))
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        account_type = (request.form.get('type') or '').strip().upper()
        parent_id = request.form.get('parent_id')
        parent_id = int(parent_id) if parent_id else None
        is_postable = request.form.get('is_postable') == 'Y'
        currency = (request.form.get('currency') or 'USD').strip()[:3]
        status = (request.form.get('status') or ChartOfAccounts.STATUS_ACTIVE).strip().upper()
        try:
            ChartOfAccounts.update(account_id, {'name': name, 'type': account_type, 'parent_id': parent_id, 'is_postable': is_postable, 'currency': currency, 'status': status})
            flash('Account updated.', 'success')
            return redirect(url_for('accounts.chart_of_accounts_list'))
        except ValueError as e:
            flash(str(e), 'error')
    return render_template('accounts/chart_of_accounts_form.html', account=account, parent_options=parent_options, account_types=ChartOfAccounts.ACCOUNT_TYPES)

@bp.route('/accounts/chart/<int:account_id>/delete', methods=['POST'])
def chart_of_accounts_delete(account_id: int):
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _apply_db():
        return redirect(url_for('dashboard.dashboard'))
    try:
        ChartOfAccounts.delete(account_id)
        flash('Account deleted.', 'success')
    except ValueError as e:
        flash(str(e), 'error')
    return redirect(url_for('accounts.chart_of_accounts_list'))

@bp.route('/accounts/payables')
def accounts_payable():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _apply_db():
        return redirect(url_for('dashboard.dashboard'))
    search_term = (request.args.get('q') or '').strip()
    balance_filter = (request.args.get('balance') or 'all').strip().lower()
    date_from, date_to = _ap_ar_list_date_args()
    rows = _filter_party_balance_rows(
        _accounts_payable_party_tagged_rows(date_from=date_from or None, date_to=date_to or None),
        search=search_term,
        balance_filter=balance_filter,
        party='supplier',
    )
    return render_template(
        'accounts/accounts_payable.html',
        rows=rows,
        search_term=search_term,
        balance_filter=balance_filter,
        date_from=date_from,
        date_to=date_to,
    )

@bp.route('/accounts/payables/payment-summary-voucher-pdf')
def accounts_payable_payment_summary_voucher_pdf():
    if not session.get('user'):
        return Response('Not authenticated', status=401, mimetype='text/plain')
    if not _apply_db():
        return Response('Database/location not assigned.', status=403, mimetype='text/plain')
    date_from, date_to = _ap_ar_list_date_args()
    rows = _filter_party_balance_rows(
        _accounts_payable_party_tagged_rows(date_from=date_from or None, date_to=date_to or None),
        search=(request.args.get('q') or '').strip(),
        balance_filter=(request.args.get('balance') or 'all').strip(),
        party='supplier',
    )
    if not rows:
        return Response('No payable summary rows found.', status=404, mimetype='text/plain')
    pdf_bytes = _build_ap_payment_summary_pdf(rows)
    if not pdf_bytes:
        return Response('PDF generation failed (reportlab not available).', status=500, mimetype='text/plain')
    filename = f"payable_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return Response(pdf_bytes, mimetype='application/pdf', headers={'Content-Disposition': f'inline; filename={filename}'})

@bp.route('/accounts/payables/payment-summary-excel')
def accounts_payable_payment_summary_excel():
    if not session.get('user'):
        return Response('Not authenticated', status=401, mimetype='text/plain')
    if not _apply_db():
        return Response('Database/location not assigned.', status=403, mimetype='text/plain')
    date_from, date_to = _ap_ar_list_date_args()
    rows = _filter_party_balance_rows(
        _accounts_payable_party_tagged_rows(date_from=date_from or None, date_to=date_to or None),
        search=(request.args.get('q') or '').strip(),
        balance_filter=(request.args.get('balance') or 'all').strip(),
        party='supplier',
    )
    if not rows:
        return Response('No payable summary rows found.', status=404, mimetype='text/plain')
    xlsx_bytes = _build_ap_payable_summary_excel(rows)
    if xlsx_bytes is None:
        return Response('Excel export requires openpyxl. Install with: pip install openpyxl', status=500, mimetype='text/plain')
    filename = f"payable_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return Response(xlsx_bytes, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers={'Content-Disposition': f'attachment; filename="{filename}"'})

@bp.route('/accounts/payables/supplier-payment-voucher-pdf')
def accounts_payable_supplier_payment_voucher_pdf():
    """PDF payment voucher for a supplier receipt posted with SOURCE = AP_RECEIPT."""
    if not session.get('user'):
        return Response('Not authenticated', status=401, mimetype='text/plain')
    if not _apply_db():
        return Response('Database/location not assigned.', status=403, mimetype='text/plain')
    voucher_no = (request.args.get('voucher_no') or '').strip()
    if not voucher_no:
        return Response('voucher_no is required.', status=400, mimetype='text/plain')
    try:
        ensure_gl_tables()
    except Exception:
        pass
    detail = get_gl_voucher_detail(voucher_no)
    if not detail:
        return Response('Voucher not found.', status=404, mimetype='text/plain')
    if str(detail.get('source') or '').strip().upper() != 'AP_RECEIPT':
        return Response('Not a supplier payment receipt voucher.', status=404, mimetype='text/plain')
    supplier_code = ''
    for ln in detail.get('lines') or []:
        if str(ln.get('party_type') or '').strip().upper() == 'SUPPLIER':
            supplier_code = str(ln.get('party_code') or '').strip()
            break
    supplier_label = supplier_code or '—'
    if supplier_code:
        sm = get_supplier_master_by_code(supplier_code)
        nm = (sm or {}).get('suppliername') or ''
        if nm:
            supplier_label = f'{supplier_code} — {nm}'
    alloc_rows = get_ap_payment_allocations_by_payment_voucher(voucher_no, supplier_code=supplier_code)
    pdf_bytes = _build_supplier_payment_voucher_pdf(detail, supplier_label=supplier_label, allocations=alloc_rows)
    if not pdf_bytes:
        return Response('PDF generation failed (reportlab not available).', status=500, mimetype='text/plain')
    safe_v = ''.join((c for c in voucher_no if c.isalnum() or c in ('-', '_')))[:44] or 'payment'
    filename = f"supplier_payment_{safe_v}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return Response(pdf_bytes, mimetype='application/pdf', headers={'Content-Disposition': f'inline; filename={filename}'})

def _accounts_form_wants_ajax() -> bool:
    return (request.headers.get('X-Nexa-Form-Ajax') or '').strip() == '1'


def _accounts_ajax_error(message: str, status: int = 400):
    issue_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY)
    return jsonify({
        'success': False,
        'error': str(message or 'Save failed')[:500],
        'save_nonce': get_or_issue_global_save_nonce(),
    }), status


def _accounts_ajax_ok(redirect_url: str, **extra: Any):
    issue_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY)
    body: Dict[str, Any] = {
        'success': True,
        'redirect': redirect_url,
        'save_nonce': get_or_issue_global_save_nonce(),
    }
    body.update(extra)
    return jsonify(body)


@bp.route('/accounts/payables/receipt/new', methods=['GET', 'POST'])
def accounts_payable_receipt_new():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _apply_db():
        return redirect(url_for('dashboard.dashboard'))
    location_code = request.args.get('locationcode') or request.form.get('locationcode') or ''
    supplier_code = request.args.get('suppliercode') or request.form.get('suppliercode') or ''
    try:
        location_code_int = int(location_code)
    except Exception:
        location_code_int = 0
    try:
        supplier_code_int = int(supplier_code)
    except Exception:
        supplier_code_int = 0
    post_form_error = False
    last_ap_error = ''
    supplier_name = ''
    payable_account = ''
    open_invoices: List[Dict[str, Any]] = []
    total_open = 0.0
    cash_bank_accounts: List[Dict[str, Any]] = []
    try:
        supplier = get_supplier_by_code(location_code_int, supplier_code_int) if location_code_int and supplier_code_int else None
        payable_account = _norm_gl_account_code((supplier or {}).get('payableaccount'))
        supplier_name = (supplier or {}).get('suppliername') or ''
        open_invoices = get_supplier_open_invoices_for_payment(supplier_code_int) if supplier_code_int else []
        total_open = round(sum((float(r.get('open_amount') or 0) for r in open_invoices if r.get('is_payable'))), 2)
        cash_bank_accounts = _cached_cash_bank_accounts()
    except Exception as e:
        _LOG_COA.exception('AP receipt page load failed supplier=%s', supplier_code_int)
        err_msg = f'Could not load supplier payment screen: {e}'
        if _accounts_form_wants_ajax():
            return _accounts_ajax_error(err_msg, 500)
        flash(err_msg, 'error')
        return redirect(url_for('accounts.accounts_payable'))
    if request.method == 'POST':
        submitted_nonce = (request.form.get('save_nonce') or '').strip()
        payment_date = _parse_iso_date(request.form.get('payment_date', '')) or datetime.now().strftime('%Y-%m-%d')
        amount_raw = (request.form.get('amount') or '0').strip()
        credit_account = (request.form.get('credit_account') or '').strip()
        remarks = (request.form.get('remarks') or '').strip()
        reference_no = (request.form.get('reference_no') or '').strip()
        invoice_vouchers = request.form.getlist('invoice_voucher_no[]')
        allocate_amounts = request.form.getlist('allocate_amount[]')
        try:
            amount = round(float(amount_raw), 2)
        except Exception:
            amount = 0.0
        try:
            discount_amount = round(max(0.0, float((request.form.get('discount_amount') or '0').strip() or 0)), 2)
        except Exception:
            discount_amount = 0.0
        allocations, invoice_total, credit_total, alloc_errors = parse_open_document_payment_allocations(open_invoices, invoice_vouchers, allocate_amounts)
        max_discount = round(max(0.0, invoice_total - credit_total), 2)
        net_cash = round(max(0.0, invoice_total - credit_total - discount_amount), 2)
        if amount <= 0 and (invoice_total > 0 or credit_total > 0 or discount_amount > 0):
            amount = net_cash
        discount_account = get_ap_discount_received_account() if discount_amount > 0.009 else ''

        def _ap_fail(msg: str) -> None:
            nonlocal post_form_error, last_ap_error
            last_ap_error = str(msg or 'Save failed')
            flash(last_ap_error, 'error')
            post_form_error = True

        period_err = _accounts_period_closed_error(payment_date)
        if not supplier_code_int:
            _ap_fail('Supplier is required.')
        elif period_err:
            _ap_fail(period_err)
        elif not payable_account:
            _ap_fail('Supplier payable account is missing.')
        elif alloc_errors:
            _ap_fail(alloc_errors[0])
        elif invoice_total <= 0 and credit_total <= 0:
            _ap_fail('Select at least one open invoice or supplier credit to apply.')
        elif credit_total > invoice_total + 0.009:
            _ap_fail('Credits applied cannot exceed total selected on invoices.')
        elif discount_amount > max_discount + 0.009:
            _ap_fail(f'Settlement discount cannot exceed net after credits ({max_discount:.2f}).')
        elif discount_amount > 0.009 and (not discount_account or not get_chart_of_account_by_code(discount_account)):
            _ap_fail(
                'Discount Received account is not configured. Set AP_DISCOUNT_RECEIVED_ACCOUNT '
                f'(default {DEFAULT_PARTY_ACCOUNTS.get("ap_discount_received") or "4010"}) in Chart of Accounts.'
            )
        elif net_cash > 0 and not credit_account:
            _ap_fail('Cash/Bank account is required when net payment is greater than zero.')
        elif round(amount, 2) != net_cash:
            _ap_fail(f'Payment amount must equal net cash after credits and discount ({net_cash:.2f}).')
        else:
            try:
                if not verify_consume_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY, submitted_nonce):
                    _ap_fail(
                        'Duplicate or invalid submit. This payment may already be posted — reload the page '
                        'or open a fresh Supplier Payment Receipt, then try again.'
                    )
                else:
                    ensure_gl_tables()
                    ensure_ap_payment_tables()
                    alloc_note = ''
                    if allocations:
                        alloc_note = ' | Applied: ' + ', '.join((f"{a['invoice_voucher_no']}:{a['allocated_amount']:.2f}" for a in allocations))
                    if discount_amount > 0.009:
                        alloc_note += f' | Discount: {discount_amount:.2f}'
                    party_line = {'party_type': 'SUPPLIER', 'party_code': str(supplier_code_int)}
                    gl_lines = []
                    if invoice_total > 0:
                        gl_lines.append({'account_code': payable_account, 'debit': invoice_total, 'credit': 0, 'remarks': f'Supplier {supplier_code_int} invoices', **party_line})
                    if credit_total > 0:
                        gl_lines.append({'account_code': payable_account, 'debit': 0, 'credit': credit_total, 'remarks': f'Supplier {supplier_code_int} credits applied', **party_line})
                    if discount_amount > 0.009:
                        gl_lines.append({'account_code': discount_account, 'debit': 0, 'credit': discount_amount, 'remarks': f'Supplier {supplier_code_int} settlement discount'})
                    if net_cash > 0:
                        gl_lines.append({'account_code': _norm_gl_account_code(credit_account), 'debit': 0, 'credit': net_cash, 'remarks': f'Supplier {supplier_code_int} payment'})
                    voucher_no = create_gl_journal_entry(
                        voucher_date=payment_date,
                        reference_no=reference_no or f'AP-{supplier_code_int}',
                        narration=(remarks or f'Supplier payment {supplier_code_int}') + alloc_note,
                        lines=gl_lines,
                        created_by=str(session.get('user') or ''),
                        source='AP_RECEIPT',
                    )
                    if allocations:
                        save_supplier_payment_allocations(
                            payment_voucher_no=voucher_no,
                            supplier_code=supplier_code_int,
                            allocations=allocations,
                            created_by=str(session.get('user') or ''),
                        )
                    redirect_url = url_for('accounts.accounts_payable', open_payment_voucher_pdf=voucher_no)
                    if _accounts_form_wants_ajax():
                        return _accounts_ajax_ok(redirect_url, voucher_no=voucher_no, message=f'Payment posted. Voucher: {voucher_no}')
                    flash(f'Payment receipt posted to GL. Voucher: {voucher_no}', 'success')
                    return redirect(redirect_url)
            except Exception as e:
                _LOG_COA.exception('AP receipt save failed supplier=%s', supplier_code_int)
                _ap_fail(str(e))
        if _accounts_form_wants_ajax():
            return _accounts_ajax_error(last_ap_error or 'Save failed.', 400)
    if request.method == 'GET' or post_form_error:
        issue_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY)
    period_ctx = _accounts_closed_period_context(
        request.form.get('payment_date') if post_form_error else None,
    )
    ap_payment_date = period_ctx['payment_date']
    if post_form_error:
        ap_payment_date = (
            _parse_iso_date(request.form.get('payment_date', '')) or period_ctx['payment_date']
        )
    return render_template(
        'accounts/accounts_payable_receipt_form.html',
        location_code=location_code_int,
        supplier_code=supplier_code_int,
        supplier_name=supplier_name,
        payable_account=payable_account,
        cash_bank_accounts=cash_bank_accounts,
        open_invoices=open_invoices,
        total_open=total_open,
        payment_date=ap_payment_date,
        closed_periods=period_ctx['closed_periods'],
        global_save_nonce=get_or_issue_global_save_nonce(),
    )

@bp.route('/accounts/receivables')
def accounts_receivable():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _apply_db():
        return redirect(url_for('dashboard.dashboard'))
    search_term = (request.args.get('q') or '').strip()
    balance_filter = (request.args.get('balance') or 'all').strip().lower()
    date_from, date_to = _ap_ar_list_date_args()
    rows = _filter_party_balance_rows(
        _accounts_receivable_party_tagged_rows(date_from=date_from or None, date_to=date_to or None),
        search=search_term,
        balance_filter=balance_filter,
        party='customer',
    )
    return render_template(
        'accounts/accounts_receivable.html',
        rows=rows,
        search_term=search_term,
        balance_filter=balance_filter,
        date_from=date_from,
        date_to=date_to,
    )

@bp.route('/accounts/receivables/receipt-summary-voucher-pdf')
def accounts_receivable_receipt_summary_voucher_pdf():
    if not session.get('user'):
        return Response('Not authenticated', status=401, mimetype='text/plain')
    if not _apply_db():
        return Response('Database/location not assigned.', status=403, mimetype='text/plain')
    date_from, date_to = _ap_ar_list_date_args()
    rows = _filter_party_balance_rows(
        _accounts_receivable_party_tagged_rows(date_from=date_from or None, date_to=date_to or None),
        search=(request.args.get('q') or '').strip(),
        balance_filter=(request.args.get('balance') or 'all').strip(),
        party='customer',
    )
    if not rows:
        return Response('No receivable summary rows found.', status=404, mimetype='text/plain')
    pdf_bytes = _build_ar_receivable_summary_pdf(rows)
    if not pdf_bytes:
        return Response('PDF generation failed (reportlab not available).', status=500, mimetype='text/plain')
    filename = f"receivable_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return Response(pdf_bytes, mimetype='application/pdf', headers={'Content-Disposition': f'inline; filename={filename}'})

@bp.route('/accounts/receivables/receipt-summary-excel')
def accounts_receivable_receipt_summary_excel():
    if not session.get('user'):
        return Response('Not authenticated', status=401, mimetype='text/plain')
    if not _apply_db():
        return Response('Database/location not assigned.', status=403, mimetype='text/plain')
    date_from, date_to = _ap_ar_list_date_args()
    rows = _filter_party_balance_rows(
        _accounts_receivable_party_tagged_rows(date_from=date_from or None, date_to=date_to or None),
        search=(request.args.get('q') or '').strip(),
        balance_filter=(request.args.get('balance') or 'all').strip(),
        party='customer',
    )
    if not rows:
        return Response('No receivable summary rows found.', status=404, mimetype='text/plain')
    xlsx_bytes = _build_ar_receivable_summary_excel(rows)
    if xlsx_bytes is None:
        return Response('Excel export requires openpyxl. Install with: pip install openpyxl', status=500, mimetype='text/plain')
    filename = f"receivable_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return Response(xlsx_bytes, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers={'Content-Disposition': f'attachment; filename="{filename}"'})

@bp.route('/accounts/receivables/customer-receipt-voucher-pdf')
def accounts_receivable_customer_receipt_voucher_pdf():
    """PDF receipt voucher for a customer collection posted with SOURCE = AR_RECEIPT."""
    if not session.get('user'):
        return Response('Not authenticated', status=401, mimetype='text/plain')
    if not _apply_db():
        return Response('Database/location not assigned.', status=403, mimetype='text/plain')
    voucher_no = (request.args.get('voucher_no') or '').strip()
    if not voucher_no:
        return Response('voucher_no is required.', status=400, mimetype='text/plain')
    try:
        ensure_gl_tables()
    except Exception:
        pass
    detail = get_gl_voucher_detail(voucher_no)
    if not detail:
        return Response('Voucher not found.', status=404, mimetype='text/plain')
    if str(detail.get('source') or '').strip().upper() != 'AR_RECEIPT':
        return Response('Not a customer receipt voucher.', status=404, mimetype='text/plain')
    customer_code = ''
    for ln in detail.get('lines') or []:
        if str(ln.get('party_type') or '').strip().upper() == 'CUSTOMER':
            customer_code = str(ln.get('party_code') or '').strip()
            break
    customer_label = customer_code or '—'
    if customer_code:
        cm = get_customer_master_by_code(customer_code)
        nm = (cm or {}).get('customername') or ''
        if nm:
            customer_label = f'{customer_code} — {nm}'
    alloc_rows = get_ar_payment_allocations_by_payment_voucher(voucher_no, customer_code=customer_code)
    pdf_bytes = _build_supplier_payment_voucher_pdf(detail, supplier_label=customer_label, allocations=alloc_rows, voucher_title='CUSTOMER RECEIPT VOUCHER', party_field_label='Customer')
    if not pdf_bytes:
        return Response('PDF generation failed (reportlab not available).', status=500, mimetype='text/plain')
    safe_v = ''.join((c for c in voucher_no if c.isalnum() or c in ('-', '_')))[:44] or 'receipt'
    filename = f"customer_receipt_{safe_v}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return Response(pdf_bytes, mimetype='application/pdf', headers={'Content-Disposition': f'inline; filename={filename}'})

@bp.route('/accounts/receivables/receipt/new', methods=['GET', 'POST'])
def accounts_receivable_receipt_new():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _apply_db():
        return redirect(url_for('dashboard.dashboard'))
    customer_code_raw = request.args.get('customercode') or request.form.get('customercode') or ''
    customer_code = str(customer_code_raw).strip()
    post_form_error = False
    cust = None
    receivable_account = _norm_gl_account_code(DEFAULT_PARTY_ACCOUNTS.get('customer_receivable') or '1200')
    customer_name = ''
    open_invoices: List[Dict[str, Any]] = []
    total_open = 0.0
    cash_bank_accounts: List[Dict[str, Any]] = []
    try:
        if customer_code:
            cust = get_customer_master_by_code(customer_code)
            receivable_account = _norm_gl_account_code((cust or {}).get('receivableaccount') or DEFAULT_PARTY_ACCOUNTS.get('customer_receivable') or '1200')
            customer_name = (cust or {}).get('customername') or ''
            open_invoices = get_customer_open_invoices_for_payment(customer_code) or []
            total_open = round(sum((float(r.get('open_amount') or 0) for r in open_invoices if r.get('is_payable'))), 2)
        cash_bank_accounts = _cached_cash_bank_accounts()
    except Exception as e:
        _LOG_COA.exception('AR receipt page load failed for customer %s', customer_code)
        flash(f'Could not load customer receipt: {e}', 'error')
        return redirect(url_for('accounts.accounts_receivable'))
    if request.method == 'POST':
        submitted_nonce = (request.form.get('save_nonce') or '').strip()
        payment_date = _parse_iso_date(request.form.get('payment_date', '')) or datetime.now().strftime('%Y-%m-%d')
        amount_raw = (request.form.get('amount') or '0').strip()
        collected_raw = (request.form.get('collected_amount') or '').strip()
        debit_account = (request.form.get('debit_account') or '').strip()
        remarks = (request.form.get('remarks') or '').strip()
        reference_no = (request.form.get('reference_no') or '').strip()
        invoice_vouchers = request.form.getlist('invoice_voucher_no[]')
        allocate_amounts = request.form.getlist('allocate_amount[]')
        try:
            amount = round(float(amount_raw), 2)
        except Exception:
            amount = 0.0
        try:
            collected_amount = round(float(collected_raw), 2) if collected_raw != '' else None
        except Exception:
            collected_amount = None
        try:
            discount_amount = round(max(0.0, float((request.form.get('discount_amount') or '0').strip() or 0)), 2)
        except Exception:
            discount_amount = 0.0
        allocations, invoice_total, credit_total, alloc_errors = parse_open_document_payment_allocations(open_invoices, invoice_vouchers, allocate_amounts)
        max_discount = round(max(0.0, invoice_total - credit_total), 2)
        net_cash = round(max(0.0, invoice_total - credit_total - discount_amount), 2)
        if amount <= 0 and (invoice_total > 0 or credit_total > 0 or discount_amount > 0):
            amount = net_cash
        discount_account = get_ar_discount_allowed_account() if discount_amount > 0.009 else ''
        period_err = _accounts_period_closed_error(payment_date)
        if not customer_code:
            flash('Customer is required.', 'error')
            post_form_error = True
        elif period_err:
            flash(period_err, 'error')
            post_form_error = True
        elif not receivable_account:
            flash('Customer receivable account is missing.', 'error')
            post_form_error = True
        elif collected_amount is None:
            flash('Collected Amount is required.', 'error')
            post_form_error = True
        elif collected_amount < 0:
            flash('Collected Amount cannot be negative.', 'error')
            post_form_error = True
        elif alloc_errors:
            flash(alloc_errors[0], 'error')
            post_form_error = True
        elif invoice_total <= 0 and credit_total <= 0:
            flash('Select at least one open invoice or customer credit to apply.', 'error')
            post_form_error = True
        elif credit_total > invoice_total + 0.009:
            flash('Credits applied cannot exceed total selected on invoices.', 'error')
            post_form_error = True
        elif discount_amount > max_discount + 0.009:
            flash(f'Settlement discount cannot exceed net after credits ({max_discount:.2f}).', 'error')
            post_form_error = True
        elif discount_amount > 0.009 and (not discount_account or not get_chart_of_account_by_code(discount_account)):
            flash(
                'Discount Allowed account is not configured. Set AR_DISCOUNT_ALLOWED_ACCOUNT '
                f'(default {DEFAULT_PARTY_ACCOUNTS.get("ar_discount_allowed") or "5010"}) in Chart of Accounts.',
                'error',
            )
            post_form_error = True
        elif net_cash > 0 and not debit_account:
            flash('Cash/Bank account is required when net receipt is greater than zero.', 'error')
            post_form_error = True
        elif round(amount, 2) != net_cash:
            flash(f'Receipt amount must equal net cash after credits and discount ({net_cash:.2f}).', 'error')
            post_form_error = True
        elif round(float(collected_amount), 2) != net_cash:
            flash(
                f'Collected Amount ({float(collected_amount):.2f}) must equal Net Cash Receipt ({net_cash:.2f}).',
                'error',
            )
            post_form_error = True
        else:
            try:
                if not verify_consume_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY, submitted_nonce):
                    flash('Duplicate or invalid submit. This receipt may already be posted — reload the page or open a fresh Customer Receipt, then try again.', 'error')
                    post_form_error = True
                else:
                    alloc_note = ''
                    if allocations:
                        alloc_note = ' | Applied: ' + ', '.join((f"{a['invoice_voucher_no']}:{a['allocated_amount']:.2f}" for a in allocations))
                    if discount_amount > 0.009:
                        alloc_note += f' | Discount: {discount_amount:.2f}'
                    party_line = {'party_type': 'CUSTOMER', 'party_code': str(customer_code)}
                    gl_lines = []
                    if net_cash > 0:
                        gl_lines.append({'account_code': _norm_gl_account_code(debit_account), 'debit': net_cash, 'credit': 0, 'remarks': f'Customer {customer_code} receipt'})
                    if discount_amount > 0.009:
                        gl_lines.append({'account_code': discount_account, 'debit': discount_amount, 'credit': 0, 'remarks': f'Customer {customer_code} settlement discount'})
                    if invoice_total > 0:
                        gl_lines.append({'account_code': receivable_account, 'debit': 0, 'credit': invoice_total, 'remarks': f'Customer {customer_code} invoices', **party_line})
                    if credit_total > 0:
                        gl_lines.append({'account_code': receivable_account, 'debit': credit_total, 'credit': 0, 'remarks': f'Customer {customer_code} credits applied', **party_line})
                    voucher_no = create_gl_journal_entry(voucher_date=payment_date, reference_no=reference_no or f'AR-{customer_code}', narration=(remarks or f'Customer receipt {customer_code}') + alloc_note, lines=gl_lines, created_by=str(session.get('user') or ''), source='AR_RECEIPT')
                    if allocations:
                        save_customer_payment_allocations(payment_voucher_no=voucher_no, customer_code=customer_code, allocations=allocations, created_by=str(session.get('user') or ''))
                    flash(f'Customer receipt posted to GL. Voucher: {voucher_no}', 'success')
                    return redirect(url_for('accounts.accounts_receivable', open_receipt_voucher_pdf=voucher_no))
            except Exception as e:
                flash(str(e), 'error')
                post_form_error = True
    if request.method == 'GET' or post_form_error:
        issue_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY)
    period_ctx = _accounts_closed_period_context(
        request.form.get('payment_date') if post_form_error else None,
    )
    collected_amount_display = None
    if post_form_error:
        try:
            collected_amount_display = round(float((request.form.get('collected_amount') or '').strip()), 2)
        except Exception:
            collected_amount_display = (request.form.get('collected_amount') or '').strip() or None
    return render_template(
        'accounts/accounts_receivable_receipt_form.html',
        customer_code=customer_code,
        customer_name=customer_name,
        receivable_account=receivable_account,
        cash_bank_accounts=cash_bank_accounts,
        open_invoices=open_invoices,
        total_open=total_open,
        collected_amount=collected_amount_display,
        payment_date=period_ctx['payment_date'] if not post_form_error else (
            _parse_iso_date(request.form.get('payment_date', '')) or period_ctx['payment_date']
        ),
        closed_periods=period_ctx['closed_periods'],
        global_save_nonce=get_or_issue_global_save_nonce(),
    )

def _cf_section_title(section: str) -> str:
    key = str(section or 'operating').strip().lower()
    return {
        'operating': 'Operating Activities',
        'investing': 'Investing Activities',
        'financing': 'Financing Activities',
    }.get(key, key.title() if key else 'Operating')


def _cf_format_voucher_date(value: Any) -> str:
    if value is None:
        return ''
    if hasattr(value, 'strftime'):
        try:
            return value.strftime('%Y-%m-%d')
        except Exception:
            pass
    return str(value).strip()[:10]


def _get_cash_flow_report_context() -> Dict[str, Any]:
    """Cash flow data for HTML, PDF, and Excel (uses query ``date_from`` / ``date_to``)."""
    date_from = _parse_iso_date(request.args.get('date_from', ''))
    date_to = _parse_iso_date(request.args.get('date_to', ''))
    from addons.purchase.controllers.routes import _get_company_profile
    company = _get_company_profile()
    company_name = str(company.get('name') or session.get('location_name') or 'Company')
    report = get_cash_flow_report(date_from=date_from or None, date_to=date_to or None)

    def _cf_fmt(iso: str) -> str:
        if not (iso or '').strip():
            return ''
        try:
            return datetime.strptime(iso.strip()[:10], '%Y-%m-%d').strftime('%d %B %Y')
        except Exception:
            return iso

    df_disp = _cf_fmt(date_from) if date_from else ''
    dt_disp = _cf_fmt(date_to) if date_to else ''
    if df_disp and dt_disp:
        period_display = f'{df_disp} to {dt_disp}'
    elif dt_disp:
        period_display = f'Up to {dt_disp}'
    elif df_disp:
        period_display = f'From {df_disp}'
    else:
        period_display = 'All dates'

    return {
        'company_name': company_name,
        'date_from': date_from,
        'date_to': date_to,
        'period_display': period_display,
        'rows': report.get('rows') or [],
        'opening_balance': report.get('opening_balance') or 0,
        'total_inflow': report.get('total_inflow') or 0,
        'total_outflow': report.get('total_outflow') or 0,
        'net_change': report.get('net_change') or 0,
        'closing_balance': report.get('closing_balance') or 0,
        'section_totals': report.get('section_totals') or {},
    }


def _build_cash_flow_pdf(ctx: Dict[str, Any]) -> bytes:
    """Statement-style cash flow PDF (summary, sections, transactions)."""
    if not REPORTLAB_AVAILABLE:
        return b''
    from xml.sax.saxutils import escape as _xml_esc_cf

    company_name = str(ctx.get('company_name') or '')
    period_disp = str(ctx.get('period_display') or '')
    opening_balance = float(ctx.get('opening_balance') or 0)
    total_inflow = float(ctx.get('total_inflow') or 0)
    total_outflow = float(ctx.get('total_outflow') or 0)
    net_change = float(ctx.get('net_change') or 0)
    closing_balance = float(ctx.get('closing_balance') or 0)
    section_totals = ctx.get('section_totals') or {}
    rows = list(ctx.get('rows') or [])

    def _m(v: float) -> str:
        return f'{float(v):,.2f}'

    styles = getSampleStyleSheet()
    MAROON = colors.HexColor('#6b0f1a')
    GRAY = colors.HexColor('#e8e8e8')
    BORDER = colors.HexColor('#333333')
    TEXT = colors.HexColor('#1a1a1a')
    PAD = 4
    page = landscape(A4)
    W = page[0] - 0.9 * inch

    def _s(name: str, **kw: Any) -> ParagraphStyle:
        base = kw.pop('parent', styles['Normal'])
        tc = kw.pop('textColor', TEXT)
        return ParagraphStyle(name, parent=base, textColor=tc, **kw)

    N7 = _s('cf7', fontName='Times-Roman', fontSize=7, leading=9)
    N7B = _s('cf7b', fontName='Times-Bold', fontSize=7, leading=9)
    N7R = _s('cf7r', fontName='Times-Roman', fontSize=7, leading=9, alignment=TA_RIGHT)
    N7i = _s('cf7i', fontName='Times-Italic', fontSize=7, leading=9, textColor=colors.HexColor('#444444'))
    N9B = _s('cf9b', fontName='Times-Bold', fontSize=9, leading=11, textColor=MAROON, alignment=TA_CENTER)
    FOOT = _s('cfft', fontName='Times-Roman', fontSize=6.5, leading=9, textColor=colors.HexColor('#666666'))
    h_center = _s('cfhc', fontName='Times-Bold', fontSize=6.5, leading=8, textColor=colors.white, alignment=TA_CENTER)
    h_right = _s('cfhr', fontName='Times-Bold', fontSize=6.5, leading=8, textColor=colors.white, alignment=TA_RIGHT)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=page,
        topMargin=0.45 * inch,
        bottomMargin=0.4 * inch,
        leftMargin=0.4 * inch,
        rightMargin=0.4 * inch,
    )
    elements: List[Any] = []
    elements.append(Paragraph(f"<b>{_xml_esc_cf(company_name or 'Company')}</b>", _s('cfco', fontName='Times-Bold', fontSize=11, leading=14, alignment=TA_CENTER)))
    if period_disp:
        elements.append(Paragraph(
            f'<i>Statement of cash flows for the period: {_xml_esc_cf(period_disp)} (cash and bank accounts).</i>',
            _s('cfper', fontName='Times-Italic', fontSize=8.5, leading=11, alignment=TA_CENTER, textColor=TEXT),
        ))
    elements.append(Paragraph('<i>(All amounts in reporting currency unless otherwise stated.)</i>', N7i))
    elements.append(Spacer(1, 6))
    elements.append(Paragraph('<b>STATEMENT OF CASH FLOWS</b>', N9B))
    elements.append(Spacer(1, 2))
    line = Table([['']], colWidths=[W], rowHeights=[2], hAlign='CENTER')
    line.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), MAROON)]))
    elements.append(line)
    elements.append(Spacer(1, 6))

    sum_head = [
        Paragraph('<b>Summary</b>', h_center),
        Paragraph('<b>Opening</b>', h_right),
        Paragraph('<b>Inflow</b>', h_right),
        Paragraph('<b>Outflow</b>', h_right),
        Paragraph('<b>Net</b>', h_right),
        Paragraph('<b>Closing</b>', h_right),
    ]
    sum_data = [
        sum_head,
        [
            Paragraph('<b>Selected period</b>', N7B),
            Paragraph(f'<b>{_m(opening_balance)}</b>', N7B),
            Paragraph(f'<b>{_m(total_inflow)}</b>', N7B),
            Paragraph(f'<b>{_m(total_outflow)}</b>', N7B),
            Paragraph(f'<b>{_m(net_change)}</b>', N7B),
            Paragraph(f'<b>{_m(closing_balance)}</b>', N7B),
        ],
    ]
    sum_cw = [1.8 * inch, 0.95 * inch, 0.95 * inch, 0.95 * inch, 0.95 * inch, 0.95 * inch]
    sum_t = Table(sum_data, colWidths=sum_cw, hAlign='LEFT')
    sum_t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1a1a')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), PAD),
        ('RIGHTPADDING', (0, 0), (-1, -1), PAD),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LINEABOVE', (0, 1), (-1, 1), 0.5, BORDER),
    ]))
    elements.append(sum_t)
    elements.append(Spacer(1, 8))

    sec_head = [
        Paragraph('<b>Section</b>', h_center),
        Paragraph('<b>Inflow</b>', h_right),
        Paragraph('<b>Outflow</b>', h_right),
        Paragraph('<b>Net</b>', h_right),
    ]
    sec_data = [sec_head]
    for key in ('operating', 'investing', 'financing'):
        st = section_totals.get(key) or {}
        sec_data.append([
            Paragraph(_xml_esc_cf(_cf_section_title(key)), N7),
            Paragraph(_m(float(st.get('inflow') or 0)), N7R),
            Paragraph(_m(float(st.get('outflow') or 0)), N7R),
            Paragraph(_m(float(st.get('net') or 0)), N7R),
        ])
    sec_data.append([
        Paragraph('<b>Total</b>', N7B),
        Paragraph(f'<b>{_m(total_inflow)}</b>', N7B),
        Paragraph(f'<b>{_m(total_outflow)}</b>', N7B),
        Paragraph(f'<b>{_m(net_change)}</b>', N7B),
    ])
    sec_cw = [2.5 * inch, 1.1 * inch, 1.1 * inch, 1.1 * inch]
    sec_t = Table(sec_data, colWidths=sec_cw, hAlign='LEFT')
    sec_t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1a1a')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), PAD),
        ('RIGHTPADDING', (0, 0), (-1, -1), PAD),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LINEABOVE', (0, len(sec_data) - 1), (-1, len(sec_data) - 1), 0.5, BORDER),
    ]))
    elements.append(Paragraph('<b>Cash flow by activity</b>', N7B))
    elements.append(Spacer(1, 4))
    elements.append(sec_t)
    elements.append(Spacer(1, 10))

    txn_head = [
        Paragraph('<b>#</b>', h_center),
        Paragraph('<b>Date</b>', h_center),
        Paragraph('<b>Voucher</b>', h_center),
        Paragraph('<b>Section</b>', h_center),
        Paragraph('<b>Account</b>', h_center),
        Paragraph('<b>Reference</b>', h_center),
        Paragraph('<b>Narration</b>', h_center),
        Paragraph('<b>Inflow</b>', h_right),
        Paragraph('<b>Outflow</b>', h_right),
        Paragraph('<b>Net</b>', h_right),
        Paragraph('<b>Balance</b>', h_right),
    ]
    txn_data: List[List[Any]] = [txn_head]
    if not rows:
        txn_data.append([Paragraph('<i>No cash flow transactions in this period.</i>', N7i)] + [''] * 10)
    else:
        for idx, row in enumerate(rows, start=1):
            acct = f"{row.get('account_code') or ''} - {row.get('account_name') or ''}".strip(' -')
            txn_data.append([
                Paragraph(str(idx), N7),
                Paragraph(_xml_esc_cf(_cf_format_voucher_date(row.get('voucher_date'))), N7),
                Paragraph(_xml_esc_cf(str(row.get('voucher_no') or '')[:24]), N7),
                Paragraph(_xml_esc_cf(_cf_section_title(row.get('section'))), N7),
                Paragraph(_xml_esc_cf(acct[:42]), N7),
                Paragraph(_xml_esc_cf(str(row.get('reference_no') or '')[:16]), N7),
                Paragraph(_xml_esc_cf(str(row.get('narration') or '')[:36]), N7),
                Paragraph(_m(float(row.get('inflow') or 0)), N7R),
                Paragraph(_m(float(row.get('outflow') or 0)), N7R),
                Paragraph(_m(float(row.get('net_movement') or 0)), N7R),
                Paragraph(_m(float(row.get('running_balance') or 0)), N7R),
            ])
        txn_data.append([
            Paragraph('<b>Totals</b>', N7B),
            '', '', '', '', '', '',
            Paragraph(f'<b>{_m(total_inflow)}</b>', N7B),
            Paragraph(f'<b>{_m(total_outflow)}</b>', N7B),
            Paragraph(f'<b>{_m(net_change)}</b>', N7B),
            Paragraph(f'<b>{_m(closing_balance)}</b>', N7B),
        ])
    txn_cw = [0.28, 0.55, 0.65, 0.75, 1.35, 0.55, 1.35, 0.6, 0.6, 0.6, 0.65]
    txn_cw = [c * inch for c in txn_cw]
    txn_t = Table(txn_data, colWidths=txn_cw, repeatRows=1, hAlign='LEFT')
    ntxn = len(txn_data)
    txn_style = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1a1a')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('FONTSIZE', (0, 0), (-1, -1), 6.5),
    ]
    if ntxn > 2:
        txn_style.append(('LINEABOVE', (0, ntxn - 1), (-1, ntxn - 1), 0.5, BORDER))
    for r_i in range(1, ntxn):
        if r_i % 2 == 0:
            txn_style.append(('BACKGROUND', (0, r_i), (-1, r_i), GRAY))
    txn_t.setStyle(TableStyle(txn_style))
    elements.append(Paragraph('<b>Cash and bank transactions</b>', N7B))
    elements.append(Spacer(1, 4))
    elements.append(txn_t)
    elements.append(Spacer(1, 8))
    elements.append(Paragraph(
        'Computer-generated from general ledger cash and bank accounts. Section classification follows counterparty account type on each voucher.',
        FOOT,
    ))
    doc.build(elements)
    return buffer.getvalue()


def _build_cash_flow_excel(ctx: Dict[str, Any]) -> Optional[bytes]:
    """Cash flow report as .xlsx (summary, sections, transactions)."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
    except ImportError:
        return None

    opening_balance = float(ctx.get('opening_balance') or 0)
    total_inflow = float(ctx.get('total_inflow') or 0)
    total_outflow = float(ctx.get('total_outflow') or 0)
    net_change = float(ctx.get('net_change') or 0)
    closing_balance = float(ctx.get('closing_balance') or 0)
    section_totals = ctx.get('section_totals') or {}
    rows = list(ctx.get('rows') or [])

    thin = Side(style='thin', color='CCCCCC')
    box = Border(left=thin, right=thin, top=thin, bottom=thin)
    hdr_fill = PatternFill(start_color='1a1a1a', end_color='1a1a1a', fill_type='solid')
    hdr_font = Font(bold=True, color='FFFFFF', size=10)
    amt_fill = PatternFill(start_color='E8E8E8', end_color='E8E8E8', fill_type='solid')
    sec_font = Font(bold=True, size=10)

    wb = Workbook()
    ws = wb.active
    ws.title = 'Cash Flow'
    co = str(ctx.get('company_name') or 'Company')
    period = str(ctx.get('period_display') or '')
    ws['A1'] = co
    ws['A1'].font = Font(bold=True, size=13)
    ws.merge_cells('A1:K1')
    ws['A2'] = f'Cash flow: {period}' if period else 'Cash flow'
    ws.merge_cells('A2:K2')
    ws['A3'] = f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    ws.merge_cells('A3:K3')
    r = 5

    def hdr_row(cols: List[str]) -> None:
        nonlocal r
        for c, h in enumerate(cols, 1):
            cell = ws.cell(row=r, column=c, value=h)
            cell.fill = hdr_fill
            cell.font = hdr_font
            cell.border = box
            cell.alignment = Alignment(horizontal='right' if c >= 2 else 'left', wrap_text=True)
        r += 1

    def num_row(label: str, vals: List[float], bold: bool = False) -> None:
        nonlocal r
        f = sec_font if bold else Font(size=10)
        ws.cell(row=r, column=1, value=label).font = f
        for i, v in enumerate(vals, 2):
            cell = ws.cell(row=r, column=i, value=round(float(v), 2))
            cell.font = f
            cell.alignment = Alignment(horizontal='right')
            cell.fill = amt_fill
            cell.border = box
        r += 1

    ws.cell(row=r, column=1, value='Period summary').font = sec_font
    r += 1
    hdr_row(['', 'Opening', 'Inflow', 'Outflow', 'Net', 'Closing'])
    num_row('Selected period', [opening_balance, total_inflow, total_outflow, net_change, closing_balance], bold=True)
    r += 1
    ws.cell(row=r, column=1, value='Cash flow by activity').font = sec_font
    r += 1
    hdr_row(['Section', 'Inflow', 'Outflow', 'Net'])
    for key in ('operating', 'investing', 'financing'):
        st = section_totals.get(key) or {}
        num_row(_cf_section_title(key), [float(st.get('inflow') or 0), float(st.get('outflow') or 0), float(st.get('net') or 0)])
    num_row('Total', [total_inflow, total_outflow, net_change], bold=True)
    r += 2
    ws.cell(row=r, column=1, value='Transactions').font = sec_font
    r += 1
    txn_cols = ['Sl.No', 'Date', 'Voucher', 'Section', 'Account Code', 'Account Name', 'Reference', 'Narration', 'Inflow', 'Outflow', 'Net', 'Running balance']
    hdr_row(txn_cols)
    for idx, row in enumerate(rows, start=1):
        f = Font(size=10)
        data = [
            idx,
            _cf_format_voucher_date(row.get('voucher_date')),
            str(row.get('voucher_no') or ''),
            _cf_section_title(row.get('section')),
            str(row.get('account_code') or ''),
            str(row.get('account_name') or ''),
            str(row.get('reference_no') or ''),
            str(row.get('narration') or ''),
            round(float(row.get('inflow') or 0), 2),
            round(float(row.get('outflow') or 0), 2),
            round(float(row.get('net_movement') or 0), 2),
            round(float(row.get('running_balance') or 0), 2),
        ]
        for c, val in enumerate(data, 1):
            cell = ws.cell(row=r, column=c, value=val)
            cell.font = f
            cell.border = box
            if c >= 9:
                cell.alignment = Alignment(horizontal='right')
                cell.fill = amt_fill
        r += 1
    if rows:
        totals = ['Totals', '', '', '', '', '', '', '', total_inflow, total_outflow, net_change, closing_balance]
        for c, val in enumerate(totals, 1):
            cell = ws.cell(row=r, column=c, value=val)
            cell.font = sec_font
            cell.border = box
            if c >= 9:
                cell.alignment = Alignment(horizontal='right')
                cell.fill = amt_fill
        r += 1
    widths = [6, 12, 14, 16, 12, 28, 14, 36, 12, 12, 12, 14]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@bp.route('/accounts/cash-flow')
def cash_flow():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _apply_db():
        return redirect(url_for('dashboard.dashboard'))
    ctx = _get_cash_flow_report_context()
    return render_template('accounts/cash_flow.html', **ctx)


@bp.route('/accounts/cash-flow/pdf', methods=['GET'])
def cash_flow_pdf():
    """Cash flow as PDF (inline)."""
    if not session.get('user'):
        return Response('Not authenticated', status=401, mimetype='text/plain')
    if not _apply_db():
        return Response('Database/location not assigned.', status=403, mimetype='text/plain')
    if not REPORTLAB_AVAILABLE:
        return Response('PDF is not available (install reportlab).', status=500, mimetype='text/plain')
    ctx = _get_cash_flow_report_context()
    pdf_bytes = _build_cash_flow_pdf(ctx)
    if not pdf_bytes:
        return Response('Failed to generate PDF.', status=500, mimetype='text/plain')
    filename = f"cash_flow_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return Response(pdf_bytes, mimetype='application/pdf', headers={'Content-Disposition': f'inline; filename="{filename}"'})


@bp.route('/accounts/cash-flow/export-excel', methods=['GET'])
def cash_flow_excel():
    """Cash flow as .xlsx download."""
    if not session.get('user'):
        return Response('Not authenticated', status=401, mimetype='text/plain')
    if not _apply_db():
        return Response('Database/location not assigned.', status=403, mimetype='text/plain')
    ctx = _get_cash_flow_report_context()
    xlsx_bytes = _build_cash_flow_excel(ctx)
    if xlsx_bytes is None:
        return Response('Excel export requires openpyxl. Install with: pip install openpyxl', status=500, mimetype='text/plain')
    filename = f"cash_flow_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return Response(
        xlsx_bytes,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )

def _build_journal_vouchers_summary_pdf(entries: list, date_from: str, date_to: str) -> bytes:
    """Summary list of GL vouchers in date range (GRN-style header, grid table)."""
    if not REPORTLAB_AVAILABLE:
        return b''
    from addons.purchase.controllers.routes import _get_company_profile

    def _dmy(raw: str) -> str:
        s = (raw or '').strip()
        if not s or s == '—':
            return 'All dates'
        try:
            return datetime.strptime(s[:10], '%Y-%m-%d').strftime('%d-%m-%Y')
        except Exception:
            return s[:16]

    def _dmy2(val: Any) -> str:
        if val is None:
            return '—'
        if hasattr(val, 'strftime'):
            try:
                return val.strftime('%d-%m-%Y')
            except Exception:
                pass
        s = str(val)[:10]
        try:
            return datetime.strptime(s, '%Y-%m-%d').strftime('%d-%m-%Y')
        except Exception:
            return s

    def _f(r: dict, *keys) -> Any:
        for k in keys:
            if not k:
                continue
            if r.get(k) is not None:
                return r.get(k)
        return None
    company = _get_company_profile()
    company_name = str(company.get('name') or session.get('location_name') or '')
    company_address = str(company.get('address') or '')
    company_phone = str(company.get('phone') or '')
    company_email = str(company.get('email') or '')
    username = str(session.get('user') or '')
    styles = getSampleStyleSheet()
    BLUE = colors.HexColor('#1a56a4')
    BLUE_LIGHT = colors.HexColor('#e8f0fb')
    BORDER = colors.HexColor('#b0b8c4')
    GRAY_ROW = colors.HexColor('#f7f8fa')
    TEXT = colors.HexColor('#1a1a1a')
    PAD = 4

    def _s(st_name, **kw):
        base = kw.pop('parent', styles['Normal'])
        kw.setdefault('textColor', TEXT)
        return ParagraphStyle(st_name, parent=base, **kw)
    N8 = _s('je8', fontSize=7.5, leading=9.5)
    N8R = _s('je8r', fontSize=7.5, leading=9.5, alignment=TA_RIGHT)
    N8C = _s('je8c', fontSize=7.5, leading=9.5, alignment=TA_CENTER)
    LBL = _s('jelbl', fontSize=7.5, leading=9.5, textColor=colors.HexColor('#555f6b'))
    SUB = _s('jesub', fontSize=7.5, leading=9.5, alignment=TA_CENTER, textColor=colors.HexColor('#555f6b'))
    WHT = _s('jewht', fontSize=7.5, leading=9.5, alignment=TA_CENTER, textColor=colors.white)
    FOOT = _s('jeft', fontSize=6.5, leading=9, textColor=colors.HexColor('#888'))
    W = 7.47 * inch
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.45 * inch, bottomMargin=0.35 * inch, leftMargin=0.4 * inch, rightMargin=0.4 * inch)
    elements = []
    clines = [Paragraph(f'<b>{company_name}</b>', _s('jecn', fontSize=10, leading=12.5, alignment=TA_CENTER, textColor=BLUE))]
    if company_address:
        clines.append(Paragraph(company_address, SUB))
    if company_phone:
        clines.append(Paragraph(f'Tel: {company_phone}', SUB))
    if company_email:
        clines.append(Paragraph(f'Email: {company_email}', SUB))
    elements.append(Table([[clines]], colWidths=[W], hAlign='LEFT'))
    elements.append(Spacer(1, 2))
    elements.append(Paragraph('<b>GL VOUCHERS SUMMARY (ALL SOURCES)</b>', _s('jeti', fontSize=11, leading=14, alignment=TA_CENTER, textColor=BLUE)))
    elements.append(Spacer(1, 4))
    _rule = Table([['']], colWidths=[W], rowHeights=[2], hAlign='LEFT')
    _rule.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), BLUE)]))
    elements.append(_rule)
    elements.append(Spacer(1, 6))
    dfa = (date_from or '').strip() or '—'
    dta = (date_to or '').strip() or '—'
    gen_ts = datetime.now().strftime('%d-%m-%Y %H:%M')
    inf = Table([[Paragraph('Period From', LBL), Paragraph(_dmy(dfa), N8), Paragraph('Period To', LBL), Paragraph(_dmy(dta), N8)], [Paragraph('Generated', LBL), Paragraph(gen_ts, N8), Paragraph('Prepared By', LBL), Paragraph(username or '—', N8)]], colWidths=[1.0 * inch, 2.72 * inch, 1.0 * inch, 2.75 * inch], hAlign='LEFT')
    inf.setStyle(TableStyle([('BOX', (0, 0), (-1, -1), 0.5, BORDER), ('BACKGROUND', (0, 0), (-1, -1), BLUE_LIGHT), ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), PAD), ('RIGHTPADDING', (0, 0), (-1, -1), PAD), ('TOPPADDING', (0, 0), (-1, -1), PAD), ('BOTTOMPADDING', (0, 0), (-1, -1), PAD), ('LINEBELOW', (0, 0), (-1, -1), 0.3, colors.HexColor('#dde3ea'))]))
    elements.append(inf)
    elements.append(Spacer(1, 8))

    def _h(txt):
        return Paragraph(f'<b>{txt}</b>', WHT)
    hdr = ['Voucher No', 'Date', 'Reference', 'Narration', 'Source', 'Lines', 'Debit', 'Credit']
    rows_pdf = [[_h(c) for c in hdr]]
    tdr, tcr = (0.0, 0.0)
    for r in entries or []:
        vno = str(_f(r, 'voucher_no', 'VOUCHER_NO') or '')
        vdt = _dmy2(_f(r, 'voucher_date', 'VOUCHER_DATE'))
        ref = _trunc_pdf_text(_f(r, 'reference_no', 'REFERENCE_NO'), 20)
        nar = _trunc_pdf_text(_f(r, 'narration', 'NARRATION'), 36)
        src = _trunc_pdf_text(_f(r, 'source', 'SOURCE'), 10)
        try:
            lc = int(float(_f(r, 'line_count', 'LINE_COUNT') or 0))
        except Exception:
            lc = 0
        try:
            drf = float(_f(r, 'total_debit', 'TOTAL_DEBIT') or 0)
        except Exception:
            drf = 0.0
        try:
            crf = float(_f(r, 'total_credit', 'TOTAL_CREDIT') or 0)
        except Exception:
            crf = 0.0
        tdr += drf
        tcr += crf
        rows_pdf.append([Paragraph(vno, N8C), Paragraph(vdt, N8C), Paragraph(str(ref or ''), N8), Paragraph(str(nar or ''), N8), Paragraph(str(src or '—'), N8C), Paragraph(str(lc), N8C), Paragraph(f'{drf:.2f}' if drf else '—', N8R), Paragraph(f'{crf:.2f}' if crf else '—', N8R)])
    b = _s('jeb', parent=styles['Normal'], fontSize=7.5, leading=9.5, fontName='Helvetica-Bold', alignment=TA_RIGHT)
    rows_pdf.append([Paragraph('', N8), Paragraph('', N8), Paragraph('', N8), Paragraph('<b>Total</b>', _s('jet', parent=N8, fontName='Helvetica-Bold')), Paragraph('', N8), Paragraph('', N8), Paragraph(f'<b>{tdr:.2f}</b>', b), Paragraph(f'<b>{tcr:.2f}</b>', b)])
    cwide = [0.85 * inch, 0.68 * inch, 0.85 * inch, 2.9 * inch, 0.55 * inch, 0.4 * inch, 0.62 * inch, 0.62 * inch]
    tbl = Table(rows_pdf, repeatRows=1, colWidths=cwide, hAlign='LEFT')
    ts = [('BACKGROUND', (0, 0), (-1, 0), BLUE), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white), ('FONTSIZE', (0, 0), (-1, -1), 7.5), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('GRID', (0, 0), (-1, -1), 0.4, BORDER), ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, GRAY_ROW]), ('BACKGROUND', (0, -1), (-1, -1), BLUE_LIGHT), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('TOPPADDING', (0, 0), (-1, -1), PAD), ('BOTTOMPADDING', (0, 0), (-1, -1), PAD), ('LEFTPADDING', (0, 0), (-1, -1), PAD), ('RIGHTPADDING', (0, 0), (-1, -1), PAD)]
    tbl.setStyle(TableStyle(ts))
    elements.append(tbl)
    elements.append(Spacer(1, 6))
    elements.append(Paragraph('Computer-generated summary of GL voucher headers. No signature is required.', FOOT))
    doc.build(elements)
    return buffer.getvalue()
_MAX_OPENING_CSV = 2000000
_MAX_OPENING_LINES = 2000

def _norm_csv_header(h: str) -> str:
    s = (h or '').replace('\ufeff', '').strip().lower()
    return s.replace(' ', '_')

def _coa_code_lookup() -> Dict[str, str]:
    m: Dict[str, str] = {}
    for r in get_all_chart_of_accounts() or []:
        c = (r.get('code') or '').strip()
        if c:
            m[c.upper()] = c
    return m

def _parse_opening_amount(val: object) -> float:
    if val is None:
        return 0.0
    t = str(val).strip()
    if not t:
        return 0.0
    t = t.replace(',', '').replace(' ', '')
    try:
        return float(t)
    except Exception:
        return float('nan')

def _parse_opening_row_dicts(rows: List[Dict[str, Any]], fieldnames: List[str]) -> Tuple[List[Dict[str, Any]], List[str], float, float]:
    """Validate opening-balance rows (CSV or Excel) into journal line dicts."""
    coa = _coa_code_lookup()
    if not coa:
        return ([], ['Chart of accounts is empty or not loaded.'], 0.0, 0.0)
    if not fieldnames:
        return ([], ['File has no header row.'], 0.0, 0.0)
    nmap: Dict[str, str] = {}
    for o in fieldnames:
        nmap[_norm_csv_header(str(o))] = str(o)

    def get_cell(row: Dict[str, Any], *norm_names: str) -> str:
        for n in norm_names:
            k = nmap.get(n)
            if k and k in row and (row[k] is not None):
                return str(row[k]).strip()
        return ''

    out: List[Dict[str, Any]] = []
    err: List[str] = []
    for row_num, row in enumerate(rows, start=2):
        if not any((str(v or '').strip() for v in (row or {}).values())):
            continue
        if len(out) >= _MAX_OPENING_LINES:
            err.append(f'Stopped at {_MAX_OPENING_LINES} data rows (limit).')
            break
        ac_raw = get_cell(row, 'account_code', 'code', 'gl_account', 'account', 'acct', 'glcode')
        if not ac_raw:
            # Skip informational blank-amount rows (e.g. COA template with empty debit/credit)
            dr0 = _parse_opening_amount(get_cell(row, 'debit', 'dr', 'd'))
            cr0 = _parse_opening_amount(get_cell(row, 'credit', 'cr', 'c'))
            if (dr0 == 0 or dr0 != dr0) and (cr0 == 0 or cr0 != cr0):
                continue
            err.append(f'Line {row_num}: missing account code.')
            continue
        canon = coa.get(ac_raw.strip().upper())
        if not canon:
            err.append(f'Line {row_num}: account {ac_raw!r} is not in the chart of accounts.')
            continue
        dr = _parse_opening_amount(get_cell(row, 'debit', 'dr', 'd'))
        cr = _parse_opening_amount(get_cell(row, 'credit', 'cr', 'c'))
        if dr != dr or cr != cr:
            err.append(f'Line {row_num}: invalid number for {canon}.')
            continue
        if dr < 0 or cr < 0:
            err.append(f'Line {row_num}: use non-negative amounts only; put the amount on the correct debit/credit column.')
            continue
        if dr > 0 and cr > 0:
            err.append(f'Line {row_num}: enter either debit or credit for {canon}, not both.')
            continue
        if dr == 0 and cr == 0:
            continue
        rec: Dict[str, Any] = {'account_code': canon, 'debit': round(dr, 2), 'credit': round(cr, 2)}
        rem = get_cell(row, 'remarks', 'remark', 'description', 'desc', 'narration')
        if rem:
            rec['remarks'] = rem[:250]
        pt = get_cell(row, 'party_type', 'partytype', 'p_type')
        pc = get_cell(row, 'party_code', 'partycode', 'p_code', 'customer_code', 'supplier_code')
        if pt:
            rec['party_type'] = pt[:20]
        if pc:
            rec['party_code'] = pc[:50]
        out.append(rec)
    tdr = round(sum((float(x.get('debit') or 0) for x in out)), 2)
    tcr = round(sum((float(x.get('credit') or 0) for x in out)), 2)
    return (out, err, tdr, tcr)

def _parse_opening_csv(data: bytes) -> Tuple[List[Dict[str, Any]], List[str], float, float]:
    """
    Build journal line dicts for :func:`create_gl_journal_entry`.
    Expected columns: account code + debit and/or credit.
    Optional: remarks, party_type, party_code.
    """
    try:
        text = data.decode('utf-8-sig')
    except Exception:
        try:
            text = data.decode('cp1252')
        except Exception:
            return ([], ['File could not be read as UTF-8 or Windows-1252.'], 0.0, 0.0)
    rdr = csv.DictReader(io.StringIO(text))
    if not rdr.fieldnames:
        return ([], ['CSV has no header row.'], 0.0, 0.0)
    rows = [dict(row) for row in rdr]
    return _parse_opening_row_dicts(rows, list(rdr.fieldnames or []))

def _parse_opening_excel(data: bytes) -> Tuple[List[Dict[str, Any]], List[str], float, float]:
    """Parse opening-balance .xlsx (same columns as CSV / Chart of Accounts template)."""
    try:
        from openpyxl import load_workbook
    except ImportError:
        return ([], ['Excel import requires openpyxl. Install with: pip install openpyxl'], 0.0, 0.0)
    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as ex:
        return ([], [f'Could not read Excel file: {ex}'], 0.0, 0.0)
    try:
        ws = wb.active
        header_aliases = {
            'account_code', 'code', 'gl_account', 'account', 'acct', 'glcode',
            'debit', 'dr', 'd', 'credit', 'cr', 'c',
            'remarks', 'remark', 'description', 'desc', 'narration',
            'party_type', 'partytype', 'p_type', 'party_code', 'partycode',
            'p_code', 'customer_code', 'supplier_code', 'name', 'type',
        }
        header_row_idx = None
        headers: List[str] = []
        for i, row in enumerate(ws.iter_rows(min_row=1, max_row=15, values_only=True), start=1):
            cells = [str(c).strip() if c is not None else '' for c in row]
            norms = [_norm_csv_header(c) for c in cells if c]
            if not norms:
                continue
            if any(n in ('account_code', 'code', 'gl_account', 'account') for n in norms) and any(
                n in ('debit', 'dr', 'credit', 'cr') for n in norms
            ):
                header_row_idx = i
                headers = cells
                break
            if sum(1 for n in norms if n in header_aliases) >= 3 and any(
                n in ('account_code', 'code') for n in norms
            ):
                header_row_idx = i
                headers = cells
                break
        if header_row_idx is None or not headers:
            return ([], ['Excel has no header row with Code / Debit / Credit columns.'], 0.0, 0.0)
        # Trim trailing empty header cells
        while headers and not str(headers[-1] or '').strip():
            headers.pop()
        fieldnames = [str(h).strip() if h is not None else f'col{i}' for i, h in enumerate(headers)]
        rows: List[Dict[str, Any]] = []
        for row in ws.iter_rows(min_row=header_row_idx + 1, values_only=True):
            cells = list(row or ())
            if not any(c is not None and str(c).strip() for c in cells):
                continue
            rec: Dict[str, Any] = {}
            for i, name in enumerate(fieldnames):
                if not name:
                    continue
                val = cells[i] if i < len(cells) else None
                rec[name] = '' if val is None else val
            rows.append(rec)
        return _parse_opening_row_dicts(rows, fieldnames)
    finally:
        try:
            wb.close()
        except Exception:
            pass

def _parse_opening_upload(filename: str, data: bytes) -> Tuple[List[Dict[str, Any]], List[str], float, float]:
    name = (filename or '').strip().lower()
    if name.endswith(('.xlsx', '.xlsm', '.xls')):
        return _parse_opening_excel(data)
    return _parse_opening_csv(data)

def _build_opening_balance_excel(accounts: Optional[List[Dict[str, Any]]]=None, *, sample: bool=False) -> Optional[bytes]:
    """
    Opening-balance Excel in the same style as Chart of Accounts export.
    When ``sample`` is True, two example rows; otherwise all chart accounts with empty Debit/Credit.
    """
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
    except ImportError:
        return None
    wb = Workbook()
    ws = wb.active
    ws.title = 'Opening Balances'
    header_font = Font(bold=True, color='FFFFFF')
    header_fill = PatternFill('solid', fgColor='1A56A4')
    thin = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1'),
    )
    headers = [
        'Code', 'Name', 'Type', 'Debit', 'Credit', 'Remarks', 'Party Type', 'Party Code',
    ]
    ws['A1'] = 'Opening Balance Import'
    ws['A1'].font = Font(bold=True, size=14, color='1A56A4')
    ws.merge_cells('A1:H1')
    ws['A2'] = (
        f"Generated by: {session.get('user') or 'web'} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
        'Fill Debit or Credit (not both). Leave blank rows with zero amounts — they are skipped on upload.'
    )
    ws.merge_cells('A2:H2')
    for col, h in enumerate(headers, start=1):
        cell = ws.cell(row=4, column=col, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = thin

    data_rows: List[Tuple[Any, ...]] = []
    if sample:
        data_rows = [
            ('1000', 'Example Cash / Bank', 'ASSET', 5000, None, 'Example — replace with your chart codes', '', ''),
            ('2000', 'Example Liability / Equity', 'LIABILITY', None, 5000, '', '', ''),
        ]
    else:
        rows = sorted(
            [a for a in (accounts or []) if (a.get('code') or '').strip()],
            key=lambda a: str(a.get('code') or '').upper(),
        )
        for a in rows:
            # Prefer postable accounts for opening lines; still include all so user can see hierarchy
            data_rows.append((
                str(a.get('code') or '').strip(),
                str(a.get('name') or '').strip(),
                str(a.get('type') or '').strip().upper(),
                None,
                None,
                '',
                '',
                '',
            ))

    for i, vals in enumerate(data_rows, start=1):
        r = 4 + i
        for col, val in enumerate(vals, start=1):
            cell = ws.cell(row=r, column=col, value=val)
            cell.border = thin
            if col in (4, 5):
                cell.alignment = Alignment(horizontal='right')
                if val is not None:
                    cell.number_format = '#,##0.00'

    widths = [14, 42, 12, 14, 14, 32, 12, 14]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    last = 4 + max(len(data_rows), 1)
    ws.auto_filter.ref = f'A4:H{last}'
    ws.freeze_panes = 'A5'
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

def _apply_opening_balance_line(lines: List[Dict[str, Any]], tdr: float, tcr: float, balance_account: str, coa: Dict[str, str]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """If debits != credits, append one line on ``balance_account`` to square the entry."""
    diff = round(tdr - tcr, 2)
    if abs(diff) < 0.01:
        return (lines, [])
    e: List[str] = []
    raw = (balance_account or '').strip()
    if not raw:
        e.append('Debits and credits are not equal. Set a balance account to post the difference, or fix the file.')
        return (lines, e)
    canon = coa.get(raw.upper())
    if not canon:
        e.append(f'Balance account {raw!r} is not in the chart of accounts.')
        return (lines, e)
    auto = 'Opening import auto-balance'
    if diff > 0.0:
        lines = lines + [{'account_code': canon, 'debit': 0.0, 'credit': abs(diff), 'remarks': auto[:250]}]
    else:
        lines = lines + [{'account_code': canon, 'debit': abs(diff), 'credit': 0.0, 'remarks': auto[:250]}]
    return (lines, e)

@bp.route('/accounts/opening-balance-import/sample.csv', methods=['GET'])
def opening_balance_sample_csv():
    if not session.get('user'):
        return Response('Not authenticated', status=401, mimetype='text/plain')
    sample = 'account_code,debit,credit,remarks,party_type,party_code\n1000,5000,0,Example — replace with your chart codes,,\n2000,0,5000,,\n'
    return Response(sample, mimetype='text/csv; charset=utf-8', headers={'Content-Disposition': 'inline; filename="opening_balance_sample.csv"'})

@bp.route('/accounts/opening-balance-import/sample.xlsx', methods=['GET'])
def opening_balance_sample_excel():
    """Sample or Chart-of-Accounts Excel template for opening balance import."""
    if not session.get('user'):
        return Response('Not authenticated', status=401, mimetype='text/plain')
    if not _apply_db():
        return Response('Database/location not assigned.', status=403, mimetype='text/plain')
    from_coa = (request.args.get('from_coa') or request.args.get('coa') or '').strip().lower() in (
        '1', 'y', 'yes', 'true', 'coa',
    )
    accounts = None
    if from_coa:
        try:
            accounts = get_all_chart_of_accounts(db_key=None, raise_on_error=True) or []
        except Exception as e:
            return Response(f'Failed to load chart of accounts: {e}', status=500, mimetype='text/plain')
    xlsx_bytes = _build_opening_balance_excel(accounts, sample=not from_coa)
    if xlsx_bytes is None:
        return Response('Excel export requires openpyxl. Install with: pip install openpyxl', status=500, mimetype='text/plain')
    filename = (
        f"opening_balance_from_coa_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        if from_coa
        else f"opening_balance_sample_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    )
    return Response(
        xlsx_bytes,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )

@bp.route('/accounts/customer-opening-outstanding/sample.csv', methods=['GET'])
def customer_opening_outstanding_sample_csv():
    if not session.get('user'):
        return Response('Not authenticated', status=401, mimetype='text/plain')
    sample = 'customercode,customername,invoiceno,invoicedate,invoiceamount,remarks\n101,Example Customer,INV-OPEN-001,2026-01-01,1250.00,Opening outstanding\n'
    return Response(sample, mimetype='text/csv; charset=utf-8', headers={'Content-Disposition': 'inline; filename="customer_opening_outstanding_sample.csv"'})

@bp.route('/accounts/customer-opening-outstanding', methods=['GET', 'POST'])
def customer_opening_outstanding():
    """Accounts-only customer opening outstanding: posts GL vouchers, no tblsettlement writes."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _apply_db():
        return redirect(url_for('dashboard.dashboard'))
    try:
        ensure_gl_tables()
    except Exception:
        pass
    customers = _customer_opening_customer_options()
    accounts = _customer_opening_account_options()
    last_rows: List[Dict[str, Any]] = []
    last_total = 0.0
    default_balance = _customer_opening_default_balance_account(accounts)
    selected_balance = default_balance
    if request.method == 'POST':
        mode = (request.form.get('mode') or 'manual').strip().lower()
        dry_run = request.form.get('dry_run') == '1'
        rows: List[Dict[str, Any]] = []
        parse_errors: List[str] = []
        if mode == 'csv':
            f = request.files.get('csv_file')
            if not f or not (f.filename or '').strip():
                parse_errors.append('Please choose a CSV file.')
            else:
                data = f.read()
                if len(data) > _MAX_CUSTOMER_OPENING_CSV:
                    parse_errors.append('CSV file is too large (max 1 MB).')
                else:
                    rows, parse_errors = _customer_opening_parse_csv(data)
        else:
            codes = request.form.getlist('customercode')
            names = request.form.getlist('customername')
            invoice_nos = request.form.getlist('invoiceno')
            invoice_dates = request.form.getlist('invoicedate')
            amounts = request.form.getlist('invoiceamount')
            remarks_list = request.form.getlist('remarks')
            row_count = max(len(codes), len(names), len(invoice_nos), len(invoice_dates), len(amounts), len(remarks_list), 1)
            rows = []
            for idx in range(row_count):
                raw_row = {'customercode': codes[idx] if idx < len(codes) else '', 'customername': names[idx] if idx < len(names) else '', 'invoiceno': invoice_nos[idx] if idx < len(invoice_nos) else '', 'invoicedate': invoice_dates[idx] if idx < len(invoice_dates) else '', 'invoiceamount': amounts[idx] if idx < len(amounts) else '', 'remarks': remarks_list[idx] if idx < len(remarks_list) else ''}
                if not any((str(v or '').strip() for v in raw_row.values())):
                    continue
                rows.append(_customer_opening_normalize_row(raw_row, idx + 1))
        valid_rows: List[Dict[str, Any]] = []
        errors = list(parse_errors)
        if not rows and (not errors):
            errors.append('No outstanding rows to post.')
        if not errors:
            valid_rows, errors = _customer_opening_validate_rows(rows, selected_balance)
        last_rows = valid_rows if valid_rows else rows
        last_total = round(sum((float(r.get('invoiceamount') or 0) for r in last_rows)), 2)
        if errors:
            for err in errors[:30]:
                flash(err, 'error')
            if len(errors) > 30:
                flash(f'... and {len(errors) - 30} more errors.', 'error')
        elif dry_run:
            flash(f'Dry run OK - {len(valid_rows)} invoice(s), total {last_total:.2f}.', 'success')
        elif not _customer_opening_try_acquire_session_lock():
            flash('A customer opening outstanding post is already in progress for this session. Please wait until it completes.', 'warning')
        else:
            submitted_nonce = (request.form.get('save_nonce') or '').strip()
            if not verify_consume_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY, submitted_nonce):
                _customer_opening_release_session_lock()
                issue_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY)
                flash('Duplicate or invalid submit. Reload the page and post once.', 'warning')
            else:
                try:
                    vouchers = _customer_opening_post_rows(valid_rows, selected_balance)
                    flash(f'Posted {len(vouchers)} customer opening outstanding voucher(s).', 'success')
                    if len(vouchers) <= 8:
                        flash('Voucher(s): ' + ', '.join(vouchers), 'success')
                except Exception as exc:
                    flash(str(exc), 'error')
                finally:
                    _customer_opening_release_session_lock()
    selected_balance_label = ''
    if selected_balance:
        for a in accounts:
            if str(a.get('code') or '').strip() == selected_balance:
                selected_balance_label = f"{selected_balance} - {str(a.get('name') or '').strip()}"
                break
    issue_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY)
    return render_template('accounts/customer_opening_outstanding.html', customers=customers, accounts=accounts, last_rows=last_rows, last_total=last_total, selected_balance=selected_balance, selected_balance_label=selected_balance_label, default_invoice_date=datetime.now().strftime('%Y-%m-%d'))

@bp.route('/accounts/supplier-opening-outstanding/sample.csv', methods=['GET'])
def supplier_opening_outstanding_sample_csv():
    if not session.get('user'):
        return Response('Not authenticated', status=401, mimetype='text/plain')
    sample = 'suppliercode,suppliername,invoiceno,invoicedate,invoiceamount,remarks\n101,Example Supplier,INV-OPEN-001,2026-01-01,1250.00,Opening outstanding\n'
    return Response(sample, mimetype='text/csv; charset=utf-8', headers={'Content-Disposition': 'inline; filename="supplier_opening_outstanding_sample.csv"'})

@bp.route('/accounts/supplier-opening-outstanding', methods=['GET', 'POST'])
def supplier_opening_outstanding():
    """Accounts-only supplier opening outstanding: posts GL vouchers, no purchase/settlement tables."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _apply_db():
        return redirect(url_for('dashboard.dashboard'))
    try:
        ensure_gl_tables()
    except Exception:
        pass
    suppliers = _supplier_opening_supplier_options()
    accounts = _customer_opening_account_options()
    last_rows: List[Dict[str, Any]] = []
    last_total = 0.0
    default_balance = _supplier_opening_default_balance_account(accounts)
    selected_balance = default_balance
    if request.method == 'POST':
        mode = (request.form.get('mode') or 'manual').strip().lower()
        dry_run = request.form.get('dry_run') == '1'
        rows: List[Dict[str, Any]] = []
        parse_errors: List[str] = []
        if mode == 'csv':
            f = request.files.get('csv_file')
            if not f or not (f.filename or '').strip():
                parse_errors.append('Please choose a CSV file.')
            else:
                data = f.read()
                if len(data) > _MAX_SUPPLIER_OPENING_CSV:
                    parse_errors.append('CSV file is too large (max 1 MB).')
                else:
                    rows, parse_errors = _supplier_opening_parse_csv(data)
        else:
            codes = request.form.getlist('suppliercode')
            names = request.form.getlist('suppliername')
            invoice_nos = request.form.getlist('invoiceno')
            invoice_dates = request.form.getlist('invoicedate')
            amounts = request.form.getlist('invoiceamount')
            remarks_list = request.form.getlist('remarks')
            row_count = max(len(codes), len(names), len(invoice_nos), len(invoice_dates), len(amounts), len(remarks_list), 1)
            rows = []
            for idx in range(row_count):
                raw_row = {'suppliercode': codes[idx] if idx < len(codes) else '', 'suppliername': names[idx] if idx < len(names) else '', 'invoiceno': invoice_nos[idx] if idx < len(invoice_nos) else '', 'invoicedate': invoice_dates[idx] if idx < len(invoice_dates) else '', 'invoiceamount': amounts[idx] if idx < len(amounts) else '', 'remarks': remarks_list[idx] if idx < len(remarks_list) else ''}
                if not any((str(v or '').strip() for v in raw_row.values())):
                    continue
                rows.append(_supplier_opening_normalize_row(raw_row, idx + 1))
        valid_rows: List[Dict[str, Any]] = []
        errors = list(parse_errors)
        if not rows and (not errors):
            errors.append('No outstanding rows to post.')
        if not errors:
            valid_rows, errors = _supplier_opening_validate_rows(rows, selected_balance)
        last_rows = valid_rows if valid_rows else rows
        last_total = round(sum((float(r.get('invoiceamount') or 0) for r in last_rows)), 2)
        if errors:
            for err in errors[:30]:
                flash(err, 'error')
            if len(errors) > 30:
                flash(f'... and {len(errors) - 30} more errors.', 'error')
        elif dry_run:
            flash(f'Dry run OK - {len(valid_rows)} invoice(s), total {last_total:.2f}.', 'success')
        elif not _supplier_opening_try_acquire_session_lock():
            flash('A supplier opening outstanding post is already in progress for this session. Please wait until it completes.', 'warning')
        else:
            submitted_nonce = (request.form.get('save_nonce') or '').strip()
            if not verify_consume_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY, submitted_nonce):
                _supplier_opening_release_session_lock()
                issue_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY)
                flash('Duplicate or invalid submit. Reload the page and post once.', 'warning')
            else:
                try:
                    vouchers = _supplier_opening_post_rows(valid_rows, selected_balance)
                    flash(f'Posted {len(vouchers)} supplier opening outstanding voucher(s).', 'success')
                    if len(vouchers) <= 8:
                        flash('Voucher(s): ' + ', '.join(vouchers), 'success')
                except Exception as exc:
                    flash(str(exc), 'error')
                finally:
                    _supplier_opening_release_session_lock()
    selected_balance_label = ''
    if selected_balance:
        for a in accounts:
            if str(a.get('code') or '').strip() == selected_balance:
                selected_balance_label = f"{selected_balance} - {str(a.get('name') or '').strip()}"
                break
    issue_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY)
    return render_template('accounts/supplier_opening_outstanding.html', suppliers=suppliers, accounts=accounts, last_rows=last_rows, last_total=last_total, selected_balance=selected_balance, selected_balance_label=selected_balance_label, default_invoice_date=datetime.now().strftime('%Y-%m-%d'))

@bp.route('/accounts/opening-balance-import', methods=['GET', 'POST'])
def opening_balance_import():
    """Upload a CSV/Excel to post one balanced GL journal (e.g. migration opening balances)."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _apply_db():
        return redirect(url_for('dashboard.dashboard'))
    try:
        ensure_gl_tables()
    except Exception:
        pass
    coa = _coa_code_lookup()
    accounts = ChartOfAccounts.get_all(limit=10000) or []
    acc_opts = sorted([a for a in accounts if (a.get('code') or '').strip()], key=lambda a: str(a.get('code') or '').upper())
    last_preview: List[Dict[str, Any]] = []
    last_tdr: float = 0.0
    last_tcr: float = 0.0
    if request.method == 'POST':
        voucher_date = _parse_iso_date(request.form.get('voucher_date', '')) or datetime.now().strftime('%Y-%m-%d')
        reference_no = (request.form.get('reference_no') or '').strip() or 'OB-IMPORT'
        narration = (request.form.get('narration') or '').strip() or 'Opening balances import'
        balance_acct = (request.form.get('balance_account') or '').strip()
        dry_run = request.form.get('dry_run') == '1'
        f = request.files.get('csv_file')
        if not f or not (f.filename or '').strip():
            flash('Please choose a CSV or Excel file.', 'error')
        else:
            data = f.read()
            if len(data) > _MAX_OPENING_CSV:
                flash('File is too large (max 2 MB).', 'error')
            else:
                raw_lines, parse_err, tdr0, tcr0 = _parse_opening_upload(f.filename or '', data)
                all_err: List[str] = list(parse_err)
                if not raw_lines and (not all_err):
                    all_err.append('No data rows with amounts in the file.')
                lines = list(raw_lines)
                if not all_err:
                    lines, bal_err = _apply_opening_balance_line(lines, tdr0, tcr0, balance_acct, coa)
                    all_err.extend(bal_err)
                tdr2 = round(sum((float(x.get('debit') or 0) for x in lines)), 2)
                tcr2 = round(sum((float(x.get('credit') or 0) for x in lines)), 2)
                last_preview = list(lines)
                last_tdr, last_tcr = (tdr2, tcr2)
                if all_err:
                    for x in all_err[:30]:
                        flash(x, 'error')
                    if len(all_err) > 30:
                        flash(f'… and {len(all_err) - 30} more errors.', 'error')
                elif tdr2 != tcr2:
                    flash(f'Not balanced: total debit {tdr2} != total credit {tcr2}. Set a valid balance account.', 'error')
                elif len(lines) < 2:
                    flash('A journal must have at least two lines (or one data row plus auto-balance).', 'error')
                elif dry_run:
                    flash(f'Dry run OK — would post {len(lines)} lines, debit {tdr2}, credit {tcr2}.', 'success')
                else:
                    try:
                        vno = create_gl_journal_entry(voucher_date=voucher_date, reference_no=reference_no[:50], narration=narration[:500], lines=lines, created_by=str(session.get('user') or ''), source='OB_IMPORT')
                        flash(f'Posted opening journal. Voucher: {vno}', 'success')
                    except Exception as ex:
                        flash(str(ex), 'error')
    last_balance_code = ''
    last_balance_label = ''
    if request.method == 'POST':
        b = (request.form.get('balance_account') or '').strip()
        last_balance_code = b
        if b:
            for a in acc_opts:
                c = (a.get('code') or '').strip()
                if c == b:
                    nm = (a.get('name') or '').strip()
                    last_balance_label = f'{c} — {nm}' if nm else c
                    break
    return render_template('accounts/opening_balance_import.html', acc_opts=acc_opts, default_voucher_date=datetime.now().strftime('%Y-%m-%d'), last_lines=last_preview, last_total_dr=last_tdr, last_total_cr=last_tcr, last_balance_code=last_balance_code, last_balance_label=last_balance_label)

@bp.route('/accounts/journal-entry/api/history-suggest', methods=['GET'])
def journal_entry_history_suggest():
    """Return posted GL journals similar to the query (narration, line remarks, account names)."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'})
    if not _apply_db():
        return jsonify({'success': False, 'error': 'DB unavailable'})
    q = (request.args.get('q') or '').strip()
    limit = min(int(request.args.get('limit') or 5), 20)
    if not q:
        return jsonify({'success': True, 'items': []})
    import re as _re
    _STOP = {
        'the', 'and', 'for', 'paid', 'pay', 'with', 'from', 'into', 'this', 'that',
        'are', 'was', 'been', 'have', 'has', 'had', 'its', 'our', 'per', 'via',
        'cash', 'bank', 'amount', 'total', 'by', 'on', 'in', 'at', 'to', 'of', 'a', 'an', 'or',
        'jun', 'jan', 'feb', 'mar', 'apr', 'may', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec',
    }
    tokens = [
        t for t in _re.split(r'[\s,;.]+', q.lower())
        if len(t) >= 3 and t not in _STOP and not _re.match(r'^\d+\.?\d*$', t)
    ]
    if not tokens:
        return jsonify({'success': True, 'items': []})

    coa_names: Dict[str, str] = {}
    try:
        for row in get_all_chart_of_accounts() or []:
            code = str(row.get('code') or '').strip()
            if code:
                coa_names[code] = str(row.get('name') or '').strip()
    except Exception:
        coa_names = {}

    # Match if any keyword appears in header narration/reference OR line remarks/account code
    where_parts: List[str] = []
    params: Dict[str, Any] = {'lim': min(80, limit * 12)}
    for i, tok in enumerate(tokens[:6]):
        key = f'tok{i}'
        params[key] = f'%{tok}%'
        where_parts.append(f"""(
            UPPER(NVL(h.NARRATION,'')) LIKE UPPER(:{key})
            OR UPPER(NVL(h.REFERENCE_NO,'')) LIKE UPPER(:{key})
            OR EXISTS (
                SELECT 1 FROM GL_VOUCHER_DTL d
                 WHERE d.VOUCHER_NO = h.VOUCHER_NO
                   AND (
                        UPPER(NVL(d.REMARKS,'')) LIKE UPPER(:{key})
                     OR UPPER(NVL(d.ACCOUNT_CODE,'')) LIKE UPPER(:{key})
                   )
            )
        )""")
    where_sql = ' OR '.join(where_parts)
    try:
        hdr_rows = _safe_rows(f"""
            SELECT DISTINCT h.VOUCHER_NO, h.VOUCHER_DATE, h.NARRATION, h.REFERENCE_NO, h.SOURCE, h.CREATED_BY
              FROM GL_VOUCHER_HDR h
             WHERE ({where_sql})
               AND UPPER(NVL(h.SOURCE,'')) NOT LIKE '%\\_REV' ESCAPE '\\'
               AND UPPER(NVL(h.SOURCE,'')) <> 'JE_REV'
             ORDER BY h.VOUCHER_DATE DESC, h.VOUCHER_NO DESC
             FETCH FIRST :lim ROWS ONLY
        """, params)
    except Exception:
        hdr_rows = []

    if not hdr_rows:
        return jsonify({'success': True, 'items': []})

    vnos = [str(r.get('voucher_no') or r.get('VOUCHER_NO') or '').strip() for r in hdr_rows]
    vnos = [v for v in vnos if v]
    lines_by_vno: Dict[str, List[Dict[str, Any]]] = {}
    if vnos:
        placeholders = ','.join([f':v{i}' for i in range(len(vnos))])
        lparams = {f'v{i}': v for i, v in enumerate(vnos)}
        try:
            line_rows = _safe_rows(f"""
                SELECT VOUCHER_NO, LINE_NO, ACCOUNT_CODE, DEBIT, CREDIT, REMARKS, PARTY_TYPE, PARTY_CODE
                  FROM GL_VOUCHER_DTL
                 WHERE VOUCHER_NO IN ({placeholders})
                 ORDER BY VOUCHER_NO, LINE_NO
            """, lparams)
        except Exception:
            line_rows = []
        for lr in (line_rows or []):
            vno = str(lr.get('voucher_no') or lr.get('VOUCHER_NO') or '').strip()
            if not vno:
                continue
            ac = str(lr.get('account_code') or lr.get('ACCOUNT_CODE') or '').strip()
            lines_by_vno.setdefault(vno, []).append({
                'account_code': ac,
                'account_name': coa_names.get(ac, ''),
                'debit': float(lr.get('debit') or lr.get('DEBIT') or 0),
                'credit': float(lr.get('credit') or lr.get('CREDIT') or 0),
                'remarks': str(lr.get('remarks') or lr.get('REMARKS') or '').strip(),
                'party_type': str(lr.get('party_type') or lr.get('PARTY_TYPE') or '').strip(),
                'party_code': str(lr.get('party_code') or lr.get('PARTY_CODE') or '').strip(),
            })

    def _voucher_blob(hdr: Dict[str, Any], lines: List[Dict[str, Any]]) -> str:
        parts = [
            str(hdr.get('narration') or hdr.get('NARRATION') or ''),
            str(hdr.get('reference_no') or hdr.get('REFERENCE_NO') or ''),
        ]
        for ln in lines:
            ac = str(ln.get('account_code') or '')
            parts.extend([
                ac,
                str(ln.get('account_name') or coa_names.get(ac, '')),
                str(ln.get('remarks') or ''),
            ])
        return ' '.join(parts).lower()

    def _score_voucher(hdr: Dict[str, Any], lines: List[Dict[str, Any]]) -> float:
        if len(lines) < 2:
            return 0.0
        blob = _voucher_blob(hdr, lines)
        narr = str(hdr.get('narration') or hdr.get('NARRATION') or '').lower()
        score = 0.0
        matched = 0
        for tok in tokens:
            if tok in blob:
                matched += 1
            if tok in narr:
                score += 18.0
            for ln in lines:
                ac = str(ln.get('account_code') or '').lower()
                name = str(ln.get('account_name') or coa_names.get(ln.get('account_code') or '', '')).lower()
                rem = str(ln.get('remarks') or '').lower()
                if tok in name:
                    score += 28.0
                elif tok in ac:
                    score += 12.0
                if tok in rem:
                    score += 14.0
        if matched:
            score += (matched / len(tokens)) * 40.0
        if matched == len(tokens):
            score += 25.0
        strong_narr = any(tok in narr for tok in tokens)
        strong_acct = False
        for ln in lines:
            name = str(ln.get('account_name') or coa_names.get(ln.get('account_code') or '', '')).lower()
            if any(tok in name for tok in tokens):
                strong_acct = True
                break
        if strong_acct:
            score += 15.0
        if not strong_narr and not strong_acct:
            score *= 0.45
        src = str(hdr.get('source') or hdr.get('SOURCE') or '').strip().upper()
        if src == 'MANUAL':
            score += 8.0
        if src.endswith('_REV') or src == 'JE_REV':
            score -= 50.0
        return score

    scored: List[Tuple[float, Dict[str, Any]]] = []
    for r in hdr_rows:
        vno = str(r.get('voucher_no') or r.get('VOUCHER_NO') or '').strip()
        if not vno:
            continue
        lines = lines_by_vno.get(vno, [])
        sc = _score_voucher(r, lines)
        if sc >= 25.0:
            scored.append((sc, r))

    scored.sort(key=lambda x: x[0], reverse=True)
    items: List[Dict[str, Any]] = []
    for sc, r in scored[:limit]:
        vno = str(r.get('voucher_no') or r.get('VOUCHER_NO') or '').strip()
        vdt = r.get('voucher_date') or r.get('VOUCHER_DATE')
        if vdt is not None and not isinstance(vdt, str):
            try:
                vdt = vdt.strftime('%Y-%m-%d')
            except Exception:
                vdt = str(vdt)[:10]
        items.append({
            'voucher_no': vno,
            'voucher_date': str(vdt or '')[:10],
            'narration': str(r.get('narration') or r.get('NARRATION') or '').strip(),
            'reference_no': str(r.get('reference_no') or r.get('REFERENCE_NO') or '').strip(),
            'source': str(r.get('source') or r.get('SOURCE') or '').strip(),
            'match_score': round(sc, 1),
            'lines': lines_by_vno.get(vno, []),
        })
    return jsonify({'success': True, 'items': items, 'tokens': tokens})


@bp.route('/accounts/journal-entry/api/dimension-values', methods=['GET'])
def journal_entry_dimension_values():
    """JSON list of GL dimension codes from GL_DIMENSION_VALUE (for F1 picker on Journal Entry)."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    if not _apply_db():
        return jsonify({'success': False, 'error': 'Database not available'}, 403)
    raw = (request.args.get('dim_type') or '').strip()
    try:
        dt = normalize_gl_dimension_type(raw)
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}, 400)
    rows = list_gl_dimension_values(dim_type=dt, include_inactive=False) or []
    items = []
    for r in rows:
        code = str(r.get('dim_code') or r.get('DIM_CODE') or '').strip()
        if not code:
            continue
        items.append({'code': code, 'name': str(r.get('dim_name') or r.get('DIM_NAME') or '').strip(), 'dim_type': dt})
    return jsonify({'success': True, 'dim_type': dt, 'items': items})

def _je_ensure_draft_table() -> None:
    """Ensure JOURNAL_ENTRY_DRAFT exists; query user_tables directly (cache may be stale)."""
    from db import _TABLE_EXISTS_CACHE
    tbl_key = _JE_DRAFT_TABLE.upper()
    ddl = f"""
                CREATE TABLE {_JE_DRAFT_TABLE} (
                    DRAFT_ID VARCHAR2(30) PRIMARY KEY,
                    VOUCHER_DATE DATE,
                    REFERENCE_NO VARCHAR2(50),
                    NARRATION VARCHAR2(500),
                    DEFAULT_COST_CENTER VARCHAR2(30),
                    DEFAULT_DEPARTMENT VARCHAR2(30),
                    DEFAULT_PROJECT VARCHAR2(30),
                    LINES_JSON CLOB,
                    STATUS VARCHAR2(20) DEFAULT 'DRAFT' NOT NULL,
                    POSTED_VOUCHER_NO VARCHAR2(30),
                    CREATED_BY VARCHAR2(50),
                    CREATED_AT TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
                    UPDATED_BY VARCHAR2(50),
                    UPDATED_AT TIMESTAMP
                )
            """
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT COUNT(*) FROM user_tables WHERE table_name = :t', {'t': tbl_key})
            if int((cur.fetchone() or [0])[0] or 0) > 0:
                _TABLE_EXISTS_CACHE[tbl_key] = True
                return
            try:
                cur.execute(ddl)
            except Exception as exc:
                err = str(exc).upper()
                if 'ORA-00955' not in err and '00955' not in err and getattr(exc, 'code', None) != 955:
                    raise
            conn.commit()
    _TABLE_EXISTS_CACHE[tbl_key] = True

def _je_next_draft_id(voucher_date: str) -> str:
    _je_ensure_draft_table()
    tag = (_parse_iso_date(voucher_date) or datetime.now().strftime('%Y-%m-%d')).replace('-', '')
    prefix = f'JED{tag}-'
    rows = _safe_rows(f"SELECT MAX(DRAFT_ID) AS max_id FROM {_JE_DRAFT_TABLE} WHERE DRAFT_ID LIKE :pfx", {'pfx': f'{prefix}%'}) or []
    seq = 1
    if rows and rows[0].get('max_id'):
        try:
            seq = int(str(rows[0].get('max_id')).split('-')[-1]) + 1
        except Exception:
            seq = 1
    return f'{prefix}{seq:04d}'

def _je_amount(value: Any) -> float:
    try:
        return round(float(str(value or '0').replace(',', '').strip() or 0), 2)
    except Exception:
        return 0.0

def _je_parse_form_payload() -> Tuple[Dict[str, Any], List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    voucher_date = _parse_iso_date(request.form.get('voucher_date', '')) or datetime.now().strftime('%Y-%m-%d')
    data = {
        'draft_id': (request.form.get('draft_id') or '').strip()[:30],
        'edit_voucher_no': (request.form.get('edit_voucher_no') or '').strip()[:30],
        'voucher_date': voucher_date,
        'reference_no': (request.form.get('reference_no') or '').strip()[:50],
        'narration': (request.form.get('narration') or '').strip()[:500],
        'default_cost_center': (request.form.get('default_cost_center') or '').strip()[:30],
        'default_department': (request.form.get('default_department') or '').strip()[:30],
        'default_project': (request.form.get('default_project') or '').strip()[:30],
    }
    dimension_defaults = None
    if data['default_cost_center'] or data['default_department'] or data['default_project']:
        dimension_defaults = {'cost_center': data['default_cost_center'] or None, 'department': data['default_department'] or None, 'project': data['default_project'] or None}
    account_codes = request.form.getlist('account_code[]')
    account_displays = request.form.getlist('account_display[]')
    debits = request.form.getlist('debit[]')
    credits = request.form.getlist('credit[]')
    remarks = request.form.getlist('remarks[]')
    party_types = request.form.getlist('party_type[]')
    party_codes = request.form.getlist('party_code[]')
    cost_centers = request.form.getlist('cost_center[]')
    departments = request.form.getlist('department[]')
    projects = request.form.getlist('project[]')
    n = max(len(account_codes), len(account_displays), len(debits), len(credits), len(remarks), len(party_types), len(party_codes), len(cost_centers), len(departments), len(projects), 0)
    lines: List[Dict[str, Any]] = []
    for i in range(n):
        rec = {
            'account_code': (account_codes[i] if i < len(account_codes) else '').strip(),
            'account_display': (account_displays[i] if i < len(account_displays) else '').strip(),
            'debit': debits[i] if i < len(debits) else '0',
            'credit': credits[i] if i < len(credits) else '0',
            'remarks': remarks[i] if i < len(remarks) else '',
            'party_type': (party_types[i] if i < len(party_types) else '').strip(),
            'party_code': (party_codes[i] if i < len(party_codes) else '').strip(),
            'cost_center': (cost_centers[i] if i < len(cost_centers) else '').strip(),
            'department': (departments[i] if i < len(departments) else '').strip(),
            'project': (projects[i] if i < len(projects) else '').strip(),
        }
        has_non_amount_data = any(str(rec.get(k) or '').strip() for k in ('account_code', 'account_display', 'remarks', 'party_type', 'party_code', 'cost_center', 'department', 'project'))
        has_amount_data = _je_amount(rec.get('debit')) != 0 or _je_amount(rec.get('credit')) != 0
        if has_non_amount_data or has_amount_data:
            lines.append(rec)
    return data, lines, dimension_defaults

def _je_validate_lines_for_save(
    lines: List[Dict[str, Any]],
    action: str,
    *,
    voucher_date: Optional[str] = None,
) -> List[str]:
    messages: List[str] = []
    if voucher_date:
        try:
            from addons.accounts.period_closing_db import is_period_closed_for_date
            lock_msg = is_period_closed_for_date(voucher_date)
            if lock_msg:
                messages.append(lock_msg)
        except Exception:
            pass
    valid_line_count = 0
    total_debit = 0.0
    total_credit = 0.0
    for idx, line in enumerate(lines or [], start=1):
        account_code = str(line.get('account_code') or '').strip()
        debit = _je_amount(line.get('debit'))
        credit = _je_amount(line.get('credit'))
        has_amount = debit > 0 or credit > 0
        if has_amount and not account_code:
            messages.append(f'Line {idx}: select an account or party.')
        if account_code and not has_amount:
            messages.append(f'Line {idx}: enter either Debit or Credit.')
        if debit < 0 or credit < 0:
            messages.append(f'Line {idx}: Debit and Credit cannot be negative.')
        if debit > 0 and credit > 0:
            messages.append(f'Line {idx}: enter Debit or Credit, not both.')
        if account_code and has_amount and not (debit > 0 and credit > 0):
            valid_line_count += 1
            total_debit += max(0.0, debit)
            total_credit += max(0.0, credit)
    if action == 'draft':
        if valid_line_count < 1:
            messages.append('Add at least one journal line with account and non-zero amount before saving draft.')
    else:
        if valid_line_count < 2:
            messages.append('Journal entry requires at least two valid lines.')
        elif round(total_debit, 2) != round(total_credit, 2):
            messages.append(f'Total Debit must equal Total Credit. Debit: {total_debit:.2f}, Credit: {total_credit:.2f}.')
    return messages

def _je_upsert_draft(data: Dict[str, Any], lines: List[Dict[str, Any]], user: str) -> str:
    _je_ensure_draft_table()
    draft_id = data.get('draft_id') or _je_next_draft_id(str(data.get('voucher_date') or ''))
    payload = json.dumps(lines or [], ensure_ascii=True)
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT 1 FROM {_JE_DRAFT_TABLE} WHERE DRAFT_ID = :did AND STATUS = 'DRAFT'", {'did': draft_id})
            exists = cur.fetchone() is not None
            params = {'did': draft_id, 'vdt': data.get('voucher_date'), 'ref': data.get('reference_no') or None, 'nar': data.get('narration') or None, 'dcc': data.get('default_cost_center') or None, 'ddp': data.get('default_department') or None, 'dpj': data.get('default_project') or None, 'lines': payload, 'usr': (user or '')[:50] or None}
            if exists:
                cur.execute(f"""
                    UPDATE {_JE_DRAFT_TABLE}
                       SET VOUCHER_DATE = TO_DATE(:vdt, 'YYYY-MM-DD'), REFERENCE_NO = :ref, NARRATION = :nar,
                           DEFAULT_COST_CENTER = :dcc, DEFAULT_DEPARTMENT = :ddp, DEFAULT_PROJECT = :dpj,
                           LINES_JSON = :lines, UPDATED_BY = :usr, UPDATED_AT = SYSTIMESTAMP
                     WHERE DRAFT_ID = :did
                """, params)
            else:
                cur.execute(f"""
                    INSERT INTO {_JE_DRAFT_TABLE}
                        (DRAFT_ID, VOUCHER_DATE, REFERENCE_NO, NARRATION, DEFAULT_COST_CENTER, DEFAULT_DEPARTMENT, DEFAULT_PROJECT, LINES_JSON, CREATED_BY)
                    VALUES
                        (:did, TO_DATE(:vdt, 'YYYY-MM-DD'), :ref, :nar, :dcc, :ddp, :dpj, :lines, :usr)
                """, params)
        conn.commit()
    return draft_id

def _je_json_text(value: Any) -> str:
    if value is None:
        return ''
    if hasattr(value, 'read'):
        try:
            return str(value.read() or '')
        except Exception:
            return ''
    return str(value or '')

def _je_get_draft(draft_id: str) -> Optional[Dict[str, Any]]:
    _je_ensure_draft_table()
    rows = _safe_rows(f"""
        SELECT DRAFT_ID, VOUCHER_DATE, REFERENCE_NO, NARRATION, DEFAULT_COST_CENTER,
               DEFAULT_DEPARTMENT, DEFAULT_PROJECT, LINES_JSON, STATUS, POSTED_VOUCHER_NO
          FROM {_JE_DRAFT_TABLE}
         WHERE DRAFT_ID = :did
    """, {'did': (draft_id or '').strip()}) or []
    if not rows:
        return None
    row = rows[0]
    try:
        row['lines'] = json.loads(_je_json_text(row.get('lines_json') or row.get('LINES_JSON')) or '[]')
    except Exception:
        row['lines'] = []
    return row

_JE_SOURCE_LABELS: Dict[str, str] = {
    'MANUAL': 'Manual journal',
    'DRAFT': 'Journal draft',
    'GRN': 'Goods receipt (GRN)',
    'PURCHASE_RETURN': 'Purchase return',
    'SALES': 'Sales invoice',
    'POS_SALE': 'POS sale',
    'POS_RETURN': 'POS return',
    'POS_COGS': 'POS COGS',
    'POS_RETURN_COGS': 'POS return COGS',
    'POS_SETTLEMENT': 'POS settlement',
    'POS_SETTLEMENT_REV': 'POS settlement reversal',
    'AR_RECEIPT': 'Customer receipt (AR)',
    'AP_RECEIPT': 'Supplier payment (AP)',
    'CPV': 'Cash payment voucher',
    'CONTRA': 'Contra voucher',
    'PAYMENT': 'Payment voucher',
    'RECEIPT': 'Receipt voucher',
    'JE_REV': 'Journal reversal',
    'OB_IMPORT': 'Opening balance import',
    'CUST_OPEN_OUT': 'Customer opening outstanding',
    'SUPP_OPEN_OUT': 'Supplier opening outstanding',
    'PERIOD_CLOSE': 'Period closing',
    'ONLINE_SETTLEMENT': 'Online settlement',
    'STKADJ': 'Stock adjustment',
    'FA_ACQ': 'Fixed asset acquisition',
    'FA_DEP': 'Fixed asset depreciation',
    'FA_DIS': 'Fixed asset disposal',
    'FA_SALE': 'Fixed asset sale',
}


def _je_source_filter_options() -> List[Dict[str, str]]:
    """Dropdown options for journal list Source filter (code + label)."""
    known = list(_JE_SOURCE_LABELS.keys())
    try:
        from_db = list_gl_journal_sources() or []
    except Exception:
        from_db = []
    codes: List[str] = []
    seen = set()
    for c in known + from_db + ['DRAFT']:
        u = str(c or '').strip().upper()
        if not u or u in seen:
            continue
        seen.add(u)
        codes.append(u)
    codes.sort(key=lambda x: (_JE_SOURCE_LABELS.get(x) or x).lower())
    return [{'id': c, 'label': _JE_SOURCE_LABELS.get(c) or c} for c in codes]


def _je_list_drafts(date_from: Optional[str]=None, date_to: Optional[str]=None) -> List[Dict[str, Any]]:
    _je_ensure_draft_table()
    where = ["STATUS = 'DRAFT'"]
    params: Dict[str, Any] = {}
    if date_from:
        where.append("TRUNC(VOUCHER_DATE) >= TO_DATE(:df, 'YYYY-MM-DD')")
        params['df'] = date_from
    if date_to:
        where.append("TRUNC(VOUCHER_DATE) <= TO_DATE(:dt, 'YYYY-MM-DD')")
        params['dt'] = date_to
    rows = _safe_rows(f"""
        SELECT DRAFT_ID, VOUCHER_DATE, REFERENCE_NO, NARRATION, CREATED_BY, CREATED_AT, LINES_JSON
          FROM {_JE_DRAFT_TABLE}
         WHERE {' AND '.join(where)}
         ORDER BY VOUCHER_DATE DESC, DRAFT_ID DESC
    """, params) or []
    out: List[Dict[str, Any]] = []
    for row in rows:
        try:
            lines = json.loads(_je_json_text(row.get('lines_json') or row.get('LINES_JSON')) or '[]')
        except Exception:
            lines = []
        total_dr = total_cr = 0.0
        count = 0
        for ln in lines or []:
            try:
                dr = float(ln.get('debit') or 0)
            except Exception:
                dr = 0.0
            try:
                cr = float(ln.get('credit') or 0)
            except Exception:
                cr = 0.0
            if ln.get('account_code') or dr > 0 or cr > 0:
                count += 1
            total_dr += max(dr, 0)
            total_cr += max(cr, 0)
        out.append({'voucher_no': row.get('draft_id'), 'voucher_date': row.get('voucher_date'), 'reference_no': row.get('reference_no'), 'narration': row.get('narration'), 'source': 'DRAFT', 'created_by': row.get('created_by'), 'created_at': row.get('created_at'), 'total_debit': round(total_dr, 2), 'total_credit': round(total_cr, 2), 'line_count': count, 'status': 'DRAFT', 'draft_id': row.get('draft_id'), 'line_id': row.get('draft_id')})
    return out


def _je_entry_sort_key(row: Dict[str, Any]) -> int:
    """Latest vouchers/drafts first (LINE_ID or DRAFT_ID)."""
    for key in ('line_id', 'draft_id', 'LINE_ID', 'DRAFT_ID'):
        try:
            val = int(row.get(key) or 0)
            if val > 0:
                return val
        except (TypeError, ValueError):
            continue
    return 0


def _je_sort_entries_latest_first(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(entries or [], key=_je_entry_sort_key, reverse=True)

def _cpv_is_ora_955(exc: BaseException) -> bool:
    msg = str(exc).upper()
    if 'ORA-00955' in msg or '00955' in msg or 'NAME IS ALREADY USED' in msg:
        return True
    code = getattr(exc, 'code', None)
    return code == 955


def _cpv_user_table_exists(cur: Any, table_name: str) -> bool:
    t = str(table_name or '').strip().upper()
    if not t:
        return False
    cur.execute('SELECT COUNT(*) FROM user_tables WHERE table_name = :t', {'t': t})
    return int((cur.fetchone() or [0])[0] or 0) > 0


def _cpv_ensure_tables() -> None:
    """Tenant DB tables for Cash Payment Voucher draft/status metadata."""
    hdr_ddl = f"""
        CREATE TABLE {_CPV_HDR_TABLE} (
            VOUCHER_NO VARCHAR2(30) PRIMARY KEY,
            VOUCHER_DATE DATE NOT NULL,
            PETTY_CASH_ACCOUNT VARCHAR2(20) NOT NULL,
            EXPENSE_PARENT_ACCOUNT VARCHAR2(20) NOT NULL,
            REFERENCE_NO VARCHAR2(50),
            NARRATION VARCHAR2(1000),
            STATUS VARCHAR2(20) DEFAULT 'DRAFT' NOT NULL,
            GL_VOUCHER_NO VARCHAR2(30),
            ATTACHMENT_PATH VARCHAR2(500),
            CREATED_BY VARCHAR2(50),
            CREATED_AT TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
            UPDATED_BY VARCHAR2(50),
            UPDATED_AT TIMESTAMP,
            POSTED_BY VARCHAR2(50),
            POSTED_AT TIMESTAMP
        )
    """
    dtl_ddl = f"""
        CREATE TABLE {_CPV_DTL_TABLE} (
            VOUCHER_NO VARCHAR2(30) NOT NULL,
            LINE_NO NUMBER NOT NULL,
            ACCOUNT_CODE VARCHAR2(20) NOT NULL,
            DESCRIPTION VARCHAR2(250),
            AMOUNT NUMBER(18,2) DEFAULT 0 NOT NULL,
            CONSTRAINT PK_CPV_DTL PRIMARY KEY (VOUCHER_NO, LINE_NO)
        )
    """
    with _get_connection() as conn:
        with conn.cursor() as cur:
            if not _cpv_user_table_exists(cur, _CPV_HDR_TABLE):
                try:
                    cur.execute(hdr_ddl)
                except Exception as exc:
                    if not _cpv_is_ora_955(exc):
                        raise
            if not _cpv_user_table_exists(cur, _CPV_DTL_TABLE):
                try:
                    cur.execute(dtl_ddl)
                except Exception as exc:
                    if not _cpv_is_ora_955(exc):
                        raise
        conn.commit()

def _cpv_mark_reversed_for_gl(gl_voucher_no: str, user: str='', *, conn: Any=None) -> int:
    """Mark Cash Payment Voucher(s) linked to *gl_voucher_no* as REVERSED. Returns rows updated."""
    glv = str(gl_voucher_no or '').strip()
    if not glv:
        return 0
    _cpv_ensure_tables()
    params = {'glv': glv, 'usr': (user or '')[:50] or None}
    sql = f"""
        UPDATE {_CPV_HDR_TABLE}
           SET STATUS = 'REVERSED',
               UPDATED_BY = :usr,
               UPDATED_AT = SYSTIMESTAMP
         WHERE GL_VOUCHER_NO = :glv
           AND UPPER(NVL(STATUS, 'DRAFT')) = 'POSTED'
    """
    if conn is not None:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return int(cur.rowcount or 0)
    with _get_connection() as own:
        try:
            with own.cursor() as cur:
                cur.execute(sql, params)
                n = int(cur.rowcount or 0)
            own.commit()
            return n
        except Exception:
            own.rollback()
            raise


def _cpv_next_voucher_no(voucher_date: str) -> str:
    _cpv_ensure_tables()
    tag = (_parse_iso_date(voucher_date) or datetime.now().strftime('%Y-%m-%d')).replace('-', '')
    prefix = f'CPV{tag}-'
    rows = _safe_rows(f"SELECT MAX(VOUCHER_NO) AS max_no FROM {_CPV_HDR_TABLE} WHERE VOUCHER_NO LIKE :pfx", {'pfx': f'{prefix}%'})
    max_no = str((rows[0].get('max_no') if rows else '') or '')
    seq = 1
    if '-' in max_no:
        tail = max_no.rsplit('-', 1)[-1]
        if tail.isdigit():
            seq = int(tail) + 1
    return f'{prefix}{seq:04d}'

def _cpv_account_context() -> Dict[str, Any]:
    accounts = get_all_chart_of_accounts() or []
    active_accounts: List[Dict[str, Any]] = []
    for acc in accounts:
        code = str(acc.get('code') or '').strip()
        if not code:
            continue
        active_accounts.append({
            'code': code,
            'name': str(acc.get('name') or '').strip(),
            'type': str(acc.get('type') or '').strip().upper(),
            'parent_code': str(acc.get('parent_code') or '').strip(),
            'parent_name': str(acc.get('parent_name') or '').strip(),
            'is_postable': bool(acc.get('is_postable')),
            'status': str(acc.get('status') or 'ACTIVE').strip().upper(),
        })

    def is_active(acc: Dict[str, Any]) -> bool:
        return str(acc.get('status') or 'ACTIVE').upper() == 'ACTIVE'

    def find_petty() -> str:
        for exact in active_accounts:
            if is_active(exact) and exact.get('is_postable') and str(exact.get('name') or '').strip().upper() == 'PETTY CASH':
                return str(exact.get('code') or '')
        for acc in active_accounts:
            txt = f"{acc.get('code') or ''} {acc.get('name') or ''}".upper()
            if is_active(acc) and acc.get('is_postable') and 'PETTY CASH' in txt:
                return str(acc.get('code') or '')
        for acc in active_accounts:
            txt = str(acc.get('name') or '').upper()
            if is_active(acc) and acc.get('is_postable') and acc.get('type') == 'ASSET' and 'CASH' in txt:
                return str(acc.get('code') or '')
        return ''

    def find_expense_parent() -> str:
        for acc in active_accounts:
            if is_active(acc) and str(acc.get('name') or '').strip().upper() in ('EXPENSES', 'EXPENSE'):
                return str(acc.get('code') or '')
        for acc in active_accounts:
            if is_active(acc) and acc.get('type') == 'EXPENSE' and not acc.get('is_postable'):
                return str(acc.get('code') or '')
        for acc in active_accounts:
            if is_active(acc) and acc.get('type') == 'EXPENSE':
                return str(acc.get('parent_code') or acc.get('code') or '')
        return ''

    petty_accounts = [a for a in active_accounts if is_active(a) and a.get('is_postable') and (a.get('type') in ('ASSET', 'CASH', 'BANK') or 'CASH' in str(a.get('name') or '').upper())]
    if not petty_accounts:
        petty_accounts = [a for a in active_accounts if is_active(a) and a.get('is_postable')]
    expense_parent_accounts = [a for a in active_accounts if is_active(a) and a.get('type') == 'EXPENSE' and not a.get('is_postable')]
    if not expense_parent_accounts:
        parent_codes = {str(a.get('parent_code') or '') for a in active_accounts if is_active(a) and a.get('type') == 'EXPENSE' and a.get('parent_code')}
        expense_parent_accounts = [a for a in active_accounts if a.get('code') in parent_codes]
    return {
        'accounts': active_accounts,
        'petty_accounts': petty_accounts,
        'expense_parent_accounts': expense_parent_accounts,
        'default_petty_cash': find_petty(),
        'default_expense_parent': find_expense_parent(),
    }

def _cpv_get_voucher(voucher_no: str) -> Optional[Dict[str, Any]]:
    vno = str(voucher_no or '').strip()
    if not vno:
        return None
    _cpv_ensure_tables()
    rows = _safe_rows(f"""
        SELECT VOUCHER_NO, VOUCHER_DATE, PETTY_CASH_ACCOUNT, EXPENSE_PARENT_ACCOUNT,
               REFERENCE_NO, NARRATION, STATUS, GL_VOUCHER_NO, ATTACHMENT_PATH,
               CREATED_BY, CREATED_AT, UPDATED_BY, UPDATED_AT, POSTED_BY, POSTED_AT
        FROM {_CPV_HDR_TABLE}
        WHERE VOUCHER_NO = :vno
    """, {'vno': vno})
    if not rows:
        return None
    header = rows[0]
    lines = _safe_rows(f"""
        SELECT LINE_NO, ACCOUNT_CODE, DESCRIPTION, AMOUNT
        FROM {_CPV_DTL_TABLE}
        WHERE VOUCHER_NO = :vno
        ORDER BY LINE_NO
    """, {'vno': vno})
    header['lines'] = lines or []
    return header

def _cpv_list_rows(search: str='', status: str='all', limit: int=500) -> List[Dict[str, Any]]:
    _cpv_ensure_tables()
    q = (search or '').strip()
    st = (status or 'all').strip().upper()
    if st not in {'ALL', 'DRAFT', 'POSTED', 'REVERSED'}:
        st = 'ALL'
    limit = max(1, min(int(limit or 500), 2000))
    where_parts: List[str] = []
    params: Dict[str, Any] = {'max_rows': limit}
    if q:
        where_parts.append("(UPPER(h.VOUCHER_NO) LIKE UPPER(:q) OR UPPER(NVL(h.REFERENCE_NO, '')) LIKE UPPER(:q) OR UPPER(NVL(h.NARRATION, '')) LIKE UPPER(:q) OR UPPER(NVL(h.GL_VOUCHER_NO, '')) LIKE UPPER(:q))")
        params['q'] = f'%{q}%'
    if st != 'ALL':
        where_parts.append("UPPER(NVL(h.STATUS, 'DRAFT')) = :status")
        params['status'] = st
    where_sql = 'WHERE ' + ' AND '.join(where_parts) if where_parts else ''
    return _safe_rows(f"""
        SELECT *
        FROM (
            SELECT
                h.VOUCHER_NO AS voucher_no,
                h.VOUCHER_DATE AS voucher_date,
                h.PETTY_CASH_ACCOUNT AS petty_cash_account,
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
            FROM {_CPV_HDR_TABLE} h
            LEFT JOIN {_CPV_DTL_TABLE} d ON d.VOUCHER_NO = h.VOUCHER_NO
            {where_sql}
            GROUP BY h.VOUCHER_NO, h.VOUCHER_DATE, h.PETTY_CASH_ACCOUNT, h.REFERENCE_NO, h.NARRATION, h.STATUS, h.GL_VOUCHER_NO, h.CREATED_BY, h.CREATED_AT, h.POSTED_BY, h.POSTED_AT
            ORDER BY h.VOUCHER_DATE DESC, h.VOUCHER_NO DESC
        )
        WHERE ROWNUM <= :max_rows
    """, params) or []

def _cpv_build_payment_voucher_payload(voucher: Dict[str, Any]) -> Dict[str, Any]:
    accounts = get_all_chart_of_accounts() or []
    by_code = {str(a.get('code') or '').strip(): str(a.get('name') or '').strip() for a in accounts}
    lines_in = voucher.get('lines') or []
    gl_lines: List[Dict[str, Any]] = []
    total = 0.0
    for idx, line in enumerate(lines_in, start=1):
        code = str(line.get('account_code') or '').strip()
        try:
            amount = round(float(line.get('amount') or 0), 2)
        except Exception:
            amount = 0.0
        if not code or amount <= 0:
            continue
        total += amount
        gl_lines.append({
            'line_no': idx,
            'account_code': code,
            'account_name': by_code.get(code, ''),
            'debit': amount,
            'credit': 0,
            'remarks': str(line.get('description') or '').strip(),
        })
    petty = str(voucher.get('petty_cash_account') or '').strip()
    if petty and total > 0:
        gl_lines.append({
            'line_no': len(gl_lines) + 1,
            'account_code': petty,
            'account_name': by_code.get(petty, ''),
            'debit': 0,
            'credit': round(total, 2),
            'remarks': f"Cash payment {voucher.get('voucher_no') or ''}".strip(),
        })
    out = dict(voucher)
    out['source'] = 'CPV'
    out['lines'] = gl_lines
    out['total_debit'] = round(total, 2)
    out['total_credit'] = round(total, 2)
    return out

def _cpv_parse_amount(raw: Any) -> float:
    try:
        return round(float(str(raw or '').replace(',', '').strip() or 0), 2)
    except Exception:
        return 0.0

def _cpv_parse_form() -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[str]]:
    voucher_date = _parse_iso_date(request.form.get('voucher_date', '')) or datetime.now().strftime('%Y-%m-%d')
    voucher_no = (request.form.get('voucher_no') or '').strip() or _cpv_next_voucher_no(voucher_date)
    data = {
        'voucher_no': voucher_no[:30],
        'voucher_date': voucher_date,
        'petty_cash_account': (request.form.get('petty_cash_account') or '').strip()[:20],
        'expense_parent_account': (request.form.get('expense_parent_account') or '').strip()[:20],
        'reference_no': (request.form.get('reference_no') or '').strip()[:50],
        'narration': (request.form.get('narration') or '').strip()[:1000],
        'attachment_path': (request.form.get('existing_attachment_path') or '').strip()[:500],
    }
    account_codes = request.form.getlist('expense_account[]')
    descriptions = request.form.getlist('description[]')
    amounts = request.form.getlist('amount[]')
    n = max(len(account_codes), len(descriptions), len(amounts))
    lines: List[Dict[str, Any]] = []
    for i in range(n):
        code = (account_codes[i] if i < len(account_codes) else '').strip()[:20]
        desc = (descriptions[i] if i < len(descriptions) else '').strip()[:250]
        amount = _cpv_parse_amount(amounts[i] if i < len(amounts) else '')
        if not code and amount <= 0 and not desc:
            continue
        lines.append({'line_no': len(lines) + 1, 'account_code': code, 'description': desc, 'amount': amount})
    errors: List[str] = []
    if not data['petty_cash_account']:
        errors.append('Petty Cash Account is required.')
    if not data['expense_parent_account']:
        errors.append('Expense Parent Account is required.')
    if not lines:
        errors.append('At least one expense line is required.')

    account_ctx = _cpv_account_context()
    account_by_code = {a['code']: a for a in account_ctx['accounts']}
    expense_children = {
        a['code'] for a in account_ctx['accounts']
        if a.get('parent_code') == data['expense_parent_account']
        and a.get('is_postable')
        and a.get('status') == 'ACTIVE'
    }
    if data['petty_cash_account'] and data['petty_cash_account'] not in account_by_code:
        errors.append('Selected Petty Cash Account is not in Chart of Accounts.')
    for line in lines:
        if not line['account_code']:
            errors.append(f"Line {line['line_no']}: Expense Sub Account is required.")
        elif line['account_code'] not in expense_children:
            errors.append(f"Line {line['line_no']}: Select only a child account under the selected Expense Parent Account.")
        if line['amount'] <= 0:
            errors.append(f"Line {line['line_no']}: Amount must be greater than zero.")
    return data, lines, errors

def _cpv_save_attachment(voucher_no: str) -> str:
    upload = request.files.get('attachment')
    if not upload or not str(getattr(upload, 'filename', '') or '').strip():
        return ''
    original = secure_filename(str(upload.filename or 'attachment'))
    if not original:
        return ''
    stamp = datetime.now().strftime('%Y%m%d%H%M%S')
    safe_vno = secure_filename(voucher_no or 'CPV') or 'CPV'
    filename = f'{safe_vno}_{stamp}_{original}'[:180]
    target_dir = _ADDON_ROOT.parents[1] / 'static' / 'uploads' / 'cash_payment_vouchers'
    target_dir.mkdir(parents=True, exist_ok=True)
    upload.save(str(target_dir / filename))
    return f'uploads/cash_payment_vouchers/{filename}'

def _cpv_upsert(cur: Any, data: Dict[str, Any], lines: List[Dict[str, Any]], status: str, user: str) -> None:
    vno = data['voucher_no']
    cur.execute(f"SELECT STATUS FROM {_CPV_HDR_TABLE} WHERE VOUCHER_NO = :vno", {'vno': vno})
    existing = cur.fetchone()
    existing_status = str(existing[0] if existing else '').strip().upper()
    if existing_status == 'POSTED' and status != 'POSTED':
        raise ValueError('Posted cash payment vouchers cannot be edited.')
    params = {
        'vno': vno,
        'vdate': data['voucher_date'],
        'petty': data['petty_cash_account'],
        'parent': data['expense_parent_account'],
        'ref': data['reference_no'] or None,
        'nar': data['narration'] or None,
        'status': status,
        'att': data.get('attachment_path') or None,
        'usr': user[:50] or None,
    }
    if existing:
        cur.execute(f"""
            UPDATE {_CPV_HDR_TABLE}
               SET VOUCHER_DATE = TO_DATE(:vdate, 'YYYY-MM-DD'),
                   PETTY_CASH_ACCOUNT = :petty,
                   EXPENSE_PARENT_ACCOUNT = :parent,
                   REFERENCE_NO = :ref,
                   NARRATION = :nar,
                   STATUS = :status,
                   ATTACHMENT_PATH = :att,
                   UPDATED_BY = :usr,
                   UPDATED_AT = SYSTIMESTAMP
             WHERE VOUCHER_NO = :vno
        """, params)
    else:
        cur.execute(f"""
            INSERT INTO {_CPV_HDR_TABLE}
                (VOUCHER_NO, VOUCHER_DATE, PETTY_CASH_ACCOUNT, EXPENSE_PARENT_ACCOUNT,
                 REFERENCE_NO, NARRATION, STATUS, ATTACHMENT_PATH, CREATED_BY, CREATED_AT)
            VALUES
                (:vno, TO_DATE(:vdate, 'YYYY-MM-DD'), :petty, :parent,
                 :ref, :nar, :status, :att, :usr, SYSTIMESTAMP)
        """, params)
    cur.execute(f"DELETE FROM {_CPV_DTL_TABLE} WHERE VOUCHER_NO = :vno", {'vno': vno})
    for line in lines:
        cur.execute(f"""
            INSERT INTO {_CPV_DTL_TABLE}
                (VOUCHER_NO, LINE_NO, ACCOUNT_CODE, DESCRIPTION, AMOUNT)
            VALUES
                (:vno, :lno, :ac, :descr, :amt)
        """, {
            'vno': vno,
            'lno': int(line['line_no']),
            'ac': line['account_code'],
            'descr': line.get('description') or None,
            'amt': float(line.get('amount') or 0),
        })

def _cpv_save_draft_voucher(data: Dict[str, Any], lines: List[Dict[str, Any]], user: str) -> None:
    with _get_connection() as conn:
        try:
            with conn.cursor() as cur:
                _cpv_upsert(cur, data, lines, 'DRAFT', user)
            conn.commit()
        except Exception:
            conn.rollback()
            raise

def _cpv_post_voucher(data: Dict[str, Any], lines: List[Dict[str, Any]], user: str) -> str:
    total = round(sum(float(line['amount'] or 0) for line in lines), 2)
    gl_lines = [
        {'account_code': line['account_code'], 'debit': line['amount'], 'credit': 0, 'remarks': line.get('description') or data['narration'] or data['voucher_no']}
        for line in lines
    ]
    gl_lines.append({'account_code': data['petty_cash_account'], 'debit': 0, 'credit': total, 'remarks': f"Cash payment {data['voucher_no']}"})
    with _get_connection() as conn:
        try:
            with conn.cursor() as cur:
                _cpv_upsert(cur, data, lines, 'DRAFT', user)
                gl_voucher_no = create_gl_journal_entry(
                    voucher_date=data['voucher_date'],
                    reference_no=data['reference_no'] or data['voucher_no'],
                    narration=data['narration'] or f"Cash Payment Voucher {data['voucher_no']}",
                    lines=gl_lines,
                    created_by=user,
                    source='CPV',
                    conn=conn,
                    commit=False,
                )
                cur.execute(f"""
                    UPDATE {_CPV_HDR_TABLE}
                       SET STATUS = 'POSTED',
                           GL_VOUCHER_NO = :glv,
                           POSTED_BY = :usr,
                           POSTED_AT = SYSTIMESTAMP,
                           UPDATED_BY = :usr,
                           UPDATED_AT = SYSTIMESTAMP
                     WHERE VOUCHER_NO = :vno
                """, {'glv': gl_voucher_no, 'usr': user[:50] or None, 'vno': data['voucher_no']})
            conn.commit()
            return gl_voucher_no
        except Exception:
            conn.rollback()
            raise

@bp.route('/accounts/cash-payment-voucher/list', methods=['GET'])
def cash_payment_voucher_list():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _apply_db():
        return redirect(url_for('dashboard.dashboard'))
    search_term = (request.args.get('q') or '').strip()
    status_filter = (request.args.get('status') or 'all').strip().lower()
    rows = _cpv_list_rows(search=search_term, status=status_filter)
    return render_template('accounts/cash_payment_voucher_list.html', rows=rows, search_term=search_term, status_filter=status_filter)

@bp.route('/accounts/cash-payment-voucher', methods=['GET', 'POST'])
def cash_payment_voucher():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _apply_db():
        return redirect(url_for('dashboard.dashboard'))
    if request.method == 'GET' and not (request.args.get('voucher_no') or '').strip() and (request.args.get('new') or '').strip() != '1':
        return cash_payment_voucher_list()
    ensure_gl_tables()
    _cpv_ensure_tables()
    user = str(session.get('user') or '')
    form_data: Optional[Dict[str, Any]] = None
    form_lines: Optional[List[Dict[str, Any]]] = None
    if request.method == 'POST':
        if not _cpv_try_acquire_session_lock():
            flash('Cash Payment Voucher is already being saved or posted in this session. Please wait.', 'error')
            existing_vno = (request.form.get('voucher_no') or '').strip()
            if existing_vno:
                return redirect(url_for('accounts.cash_payment_voucher', voucher_no=existing_vno))
            return redirect(url_for('accounts.cash_payment_voucher'))
        try:
            submitted_nonce = (request.form.get('save_nonce') or '').strip()
            if not verify_consume_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY, submitted_nonce):
                issue_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY)
                flash('Duplicate or invalid submit. Reload the Cash Payment Voucher page and try again.', 'error')
                existing_vno = (request.form.get('voucher_no') or '').strip()
                if existing_vno:
                    return redirect(url_for('accounts.cash_payment_voucher', voucher_no=existing_vno))
                return redirect(url_for('accounts.cash_payment_voucher'))
            action = (request.form.get('action') or 'save').strip().lower()
            data, lines, errors = _cpv_parse_form()
            attachment_path = _cpv_save_attachment(data['voucher_no'])
            if attachment_path:
                data['attachment_path'] = attachment_path
            period_err = _accounts_period_closed_error(data.get('voucher_date'))
            if period_err:
                errors.append(period_err)
            if not errors:
                existing_hdr = _cpv_get_voucher(data['voucher_no'])
                status_u = str((existing_hdr or {}).get('status') or 'DRAFT').upper()
                if status_u == 'POSTED':
                    if action == 'post':
                        errors.append('This cash payment voucher is already posted.')
                    else:
                        errors.append('Posted cash payment vouchers cannot be edited.')
            if errors:
                issue_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY)
                for msg in errors:
                    flash(msg, 'error')
                form_data = data
                form_data['status'] = 'DRAFT'
                form_lines = lines
            else:
                try:
                    if action == 'post':
                        gl_voucher_no = _cpv_post_voucher(data, lines, user)
                        flash(f'Cash Payment Voucher posted. GL Voucher No: {gl_voucher_no}', 'success')
                        return redirect(url_for(
                            'accounts.cash_payment_voucher_list',
                            open_cash_payment_voucher_pdf=data['voucher_no'],
                        ))
                    _cpv_save_draft_voucher(data, lines, user)
                    flash(f'Cash Payment Voucher saved as draft: {data["voucher_no"]}', 'success')
                    return redirect(url_for('accounts.cash_payment_voucher', voucher_no=data['voucher_no']))
                except Exception as exc:
                    issue_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY)
                    flash(str(exc), 'error')
                    form_data = data
                    form_data['status'] = 'DRAFT'
                    form_lines = lines
        finally:
            _cpv_release_session_lock()

    account_ctx = _cpv_account_context()
    voucher_no = (request.args.get('voucher_no') or '').strip()
    loaded = _cpv_get_voucher(voucher_no) if voucher_no else None
    if form_data is None:
        if loaded:
            form_data = loaded
            form_lines = loaded.get('lines') or []
        else:
            period_ctx_new = _accounts_closed_period_context()
            today = period_ctx_new['default_voucher_date']
            form_data = {
                'voucher_no': _cpv_next_voucher_no(today),
                'voucher_date': today,
                'petty_cash_account': account_ctx['default_petty_cash'],
                'expense_parent_account': account_ctx['default_expense_parent'],
                'reference_no': '',
                'narration': '',
                'status': 'DRAFT',
                'gl_voucher_no': '',
                'attachment_path': '',
                'created_by': user,
                'created_at': '',
                'posted_by': '',
                'posted_at': '',
            }
            form_lines = []
    try:
        from global_lookup import resolve_lookup_label
        form_data['petty_cash_label'] = resolve_lookup_label(
            'cpv_petty', str(form_data.get('petty_cash_account') or '')
        )
        form_data['expense_parent_label'] = resolve_lookup_label(
            'cpv_expense_parent', str(form_data.get('expense_parent_account') or '')
        )
    except Exception:
        form_data.setdefault('petty_cash_label', '')
        form_data.setdefault('expense_parent_label', '')

    period_ctx = _accounts_closed_period_context(str(form_data.get('voucher_date') or ''))
    return render_template(
        'accounts/cash_payment_voucher.html',
        voucher=form_data,
        lines=form_lines or [],
        accounts=account_ctx['accounts'],
        petty_accounts=account_ctx['petty_accounts'],
        expense_parent_accounts=account_ctx['expense_parent_accounts'],
        today=period_ctx['default_voucher_date'],
        closed_periods=period_ctx['closed_periods'],
    )

@bp.route('/accounts/cash-payment-voucher/pdf', methods=['GET'])
def cash_payment_voucher_pdf():
    if not session.get('user'):
        return Response('Not authenticated', status=401, mimetype='text/plain')
    if not _apply_db():
        return Response('Database/location not assigned.', status=403, mimetype='text/plain')
    voucher_no = (request.args.get('voucher_no') or '').strip()
    if not voucher_no:
        return Response('voucher_no is required.', status=400, mimetype='text/plain')
    voucher = _cpv_get_voucher(voucher_no)
    if not voucher:
        return Response('Cash Payment Voucher not found.', status=404, mimetype='text/plain')
    if str(voucher.get('status') or '').strip().upper() != 'POSTED':
        return Response('Cash Payment Voucher PDF is available after posting.', status=400, mimetype='text/plain')
    accounts = get_all_chart_of_accounts() or []
    by_code = {str(a.get('code') or '').strip(): str(a.get('name') or '').strip() for a in accounts}
    vdate = str(voucher.get('voucher_date') or '')[:10]
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
    petty_code = str(voucher.get('petty_cash_account') or '').strip()
    pdf_bytes = _build_petty_cash_style_voucher_pdf(
        voucher_no=str(voucher.get('voucher_no') or ''),
        voucher_date=vdate,
        voucher_title='Cash Payment Voucher',
        party_field_label='Particulars',
        party_name=_voucher_party_from_lines(voucher.get('lines') or [], str(voucher.get('narration') or '')),
        item_lines=item_lines,
        total_amount=total,
        created_by=str(voucher.get('created_by') or ''),
        verified_by=str(voucher.get('posted_by') or ''),
        approved_by='',
        debit_account_label='Debit Account',
        debit_account_name=_voucher_account_summary_from_lines(voucher.get('lines') or [], by_code),
        credit_account_label='Credit Account',
        credit_account_name=_voucher_account_label(petty_code, by_code),
        reference_no=str(voucher.get('reference_no') or ''),
    )
    if not pdf_bytes:
        return Response('PDF generation failed (reportlab not available).', status=500, mimetype='text/plain')
    safe_v = ''.join((c for c in voucher_no if c.isalnum() or c in ('-', '_')))[:44] or 'cash_payment'
    filename = f"cash_payment_{safe_v}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return Response(pdf_bytes, mimetype='application/pdf', headers={'Content-Disposition': f'inline; filename="{filename}"'})

@bp.route('/accounts/journal-entry', methods=['GET', 'POST'])
def journal_entry():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _apply_db():
        return redirect(url_for('dashboard.dashboard'))
    ensure_gl_tables()
    _je_ensure_draft_table()
    draft_id_arg = (request.args.get('draft_id') or '').strip()
    edit_vno_arg = (request.args.get('edit') or '').strip()
    show_form = request.method == 'POST' or (request.args.get('new') or '').strip() == '1' or bool(draft_id_arg) or bool(edit_vno_arg)
    journal_data: Dict[str, Any] = {}
    journal_lines: List[Dict[str, Any]] = []
    if request.method == 'POST':
        submitted_nonce = (request.form.get('save_nonce') or '').strip()
        if not verify_consume_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY, submitted_nonce):
            flash('Duplicate or invalid submit. Reload the Journal Entry page and try again.', 'error')
            rkw_je: Dict[str, Any] = {}
            djf = request.args.get('date_from') or ''
            djt = request.args.get('date_to') or ''
            if djf:
                rkw_je['date_from'] = djf
            if djt:
                rkw_je['date_to'] = djt
            return redirect(url_for('accounts.journal_entry', **rkw_je))
        action = (request.form.get('action') or 'post').strip().lower()
        ret_df = _parse_iso_date(request.form.get('return_date_from', ''))
        ret_dt = _parse_iso_date(request.form.get('return_date_to', ''))
        data, lines, dimension_defaults = _je_parse_form_payload()
        edit_vno = (data.get('edit_voucher_no') or '').strip()
        if edit_vno and action == 'draft':
            flash('Save as draft is not available while editing a posted voucher. Use Update journal.', 'warning')
            journal_data = data
            journal_lines = lines
        elif not _je_try_acquire_submit_session_lock():
            flash('Journal entry is already being saved in this session. Please wait.', 'error')
            journal_data = data
            journal_lines = lines
        else:
            try:
                validation_messages = _je_validate_lines_for_save(
                    lines, action, voucher_date=data.get('voucher_date'),
                )
                if validation_messages:
                    for msg in validation_messages:
                        flash(msg, 'error')
                    journal_data = data
                    journal_lines = lines
                elif action == 'draft':
                    did = _je_upsert_draft(data, lines, str(session.get('user') or ''))
                    flash(f'Journal draft saved: {did}', 'success')
                    return redirect(url_for('accounts.journal_entry'))
                elif edit_vno:
                    detail_chk = get_gl_voucher_detail(edit_vno)
                    if not _je_voucher_can_edit(detail_chk):
                        flash('This voucher cannot be edited.', 'error')
                        journal_data = data
                        journal_lines = lines
                    else:
                        with _get_connection() as conn:
                            update_gl_journal_entry(
                                edit_vno,
                                voucher_date=data['voucher_date'],
                                reference_no=data['reference_no'],
                                narration=data['narration'],
                                lines=lines,
                                dimension_defaults=dimension_defaults,
                                conn=conn,
                                commit=False,
                            )
                            conn.commit()
                        flash(f'Journal updated successfully. Voucher No: {edit_vno}', 'success')
                        rkw_up: dict = {
                            'open_journal_voucher_pdf': edit_vno,
                        }
                        if ret_df:
                            rkw_up['date_from'] = ret_df
                        if ret_dt:
                            rkw_up['date_to'] = ret_dt
                        return redirect(url_for('accounts.journal_voucher_view', voucher_no=edit_vno, **rkw_up))
                else:
                    voucher_no = create_gl_journal_entry(voucher_date=data['voucher_date'], reference_no=data['reference_no'], narration=data['narration'], lines=lines, created_by=str(session.get('user') or ''), source='MANUAL', dimension_defaults=dimension_defaults)
                    if data.get('draft_id'):
                        with _get_connection() as conn:
                            with conn.cursor() as cur:
                                cur.execute(f"""
                                    UPDATE {_JE_DRAFT_TABLE}
                                       SET STATUS = 'POSTED',
                                           POSTED_VOUCHER_NO = :vno,
                                           UPDATED_BY = :usr,
                                           UPDATED_AT = SYSTIMESTAMP
                                     WHERE DRAFT_ID = :did
                                """, {'vno': voucher_no, 'usr': str(session.get('user') or '')[:50] or None, 'did': data['draft_id']})
                            conn.commit()
                    flash(f'Journal posted successfully. Voucher No: {voucher_no}', 'success')
                    rkw: dict = {
                        'open_journal_voucher_pdf': voucher_no,
                    }
                    if ret_df:
                        rkw['date_from'] = ret_df
                    if ret_dt:
                        rkw['date_to'] = ret_dt
                    return redirect(url_for('accounts.journal_entry', **rkw))
            except Exception as e:
                flash(str(e), 'error')
                journal_data = data
                journal_lines = lines
            finally:
                _je_release_submit_session_lock()
    date_from = _parse_iso_date(request.args.get('date_from', ''))
    date_to = _parse_iso_date(request.args.get('date_to', ''))
    search_term = (request.args.get('q') or '').strip()
    status_filter = (request.args.get('status') or 'all').strip().lower()
    source_filter = (request.args.get('source') or 'all').strip().upper()
    if source_filter in ('', 'ALL', '*'):
        source_filter = 'all'
    if show_form and not journal_data and draft_id_arg:
        draft = _je_get_draft(draft_id_arg)
        if draft:
            journal_data = {
                'draft_id': draft.get('draft_id') or draft.get('DRAFT_ID') or draft_id_arg,
                'voucher_date': str(draft.get('voucher_date') or draft.get('VOUCHER_DATE') or '')[:10],
                'reference_no': draft.get('reference_no') or draft.get('REFERENCE_NO') or '',
                'narration': draft.get('narration') or draft.get('NARRATION') or '',
                'default_cost_center': draft.get('default_cost_center') or draft.get('DEFAULT_COST_CENTER') or '',
                'default_department': draft.get('default_department') or draft.get('DEFAULT_DEPARTMENT') or '',
                'default_project': draft.get('default_project') or draft.get('DEFAULT_PROJECT') or '',
            }
            journal_lines = draft.get('lines') or []
        else:
            flash('Journal draft not found.', 'error')
            return redirect(url_for('accounts.journal_entry'))
    if show_form and not journal_data and edit_vno_arg:
        detail_edit = get_gl_voucher_detail(edit_vno_arg)
        if not detail_edit:
            flash('Voucher not found.', 'error')
            return redirect(url_for('accounts.journal_entry'))
        if not _je_voucher_can_edit(detail_edit):
            flash('Only posted manual journals that are not reversed can be edited.', 'error')
            return redirect(url_for('accounts.journal_voucher_view', voucher_no=edit_vno_arg))
        journal_data = {
            'edit_voucher_no': edit_vno_arg,
            'voucher_date': str(detail_edit.get('voucher_date') or '')[:10],
            'reference_no': detail_edit.get('reference_no') or '',
            'narration': detail_edit.get('narration') or '',
            'default_cost_center': '',
            'default_department': '',
            'default_project': '',
        }
        journal_lines = _je_gl_detail_to_form_lines(detail_edit)
    accounts = ChartOfAccounts.get_all(limit=10000) if show_form else []
    je_account_balances: Dict[str, float] = {}
    je_party_balances: Dict[str, Dict[str, float]] = {'SUPPLIER': {}, 'CUSTOMER': {}}
    if show_form:
        try:
            je_account_balances = get_gl_account_closing_balances() or {}
        except Exception:
            je_account_balances = {}
        try:
            je_party_balances = get_gl_party_balances_for_journal() or {'SUPPLIER': {}, 'CUSTOMER': {}}
        except Exception:
            je_party_balances = {'SUPPLIER': {}, 'CUSTOMER': {}}
    je_suppliers = []
    je_customers = []
    def_sup = str((DEFAULT_PARTY_ACCOUNTS or {}).get('supplier_payable') or '2110').strip()
    def_cust = str((DEFAULT_PARTY_ACCOUNTS or {}).get('customer_receivable') or '1200').strip()
    src_arg = None if source_filter == 'all' else source_filter
    # Drafts are listed with source DRAFT — skip DB source filter when only drafts are wanted
    posted_source = None if source_filter == 'DRAFT' else src_arg
    posted_entries = list_gl_journal_entries(
        date_from=date_from or None,
        date_to=date_to or None,
        limit=500,
        source=posted_source,
    )
    draft_entries = _je_list_drafts(date_from=date_from or None, date_to=date_to or None)
    if source_filter == 'DRAFT':
        entries = _je_sort_entries_latest_first(draft_entries)[:500]
    elif source_filter != 'all':
        entries = _je_sort_entries_latest_first(posted_entries)[:500]
    else:
        entries = _je_sort_entries_latest_first(draft_entries + posted_entries)[:500]
    if status_filter in {'draft', 'posted'}:
        entries = [row for row in entries if (str(row.get('status') or 'POSTED').strip().lower() == status_filter)]
    else:
        status_filter = 'all'
    if search_term:
        needle = search_term.lower()
        entries = [
            row for row in entries
            if needle in ' '.join([
                str(row.get('voucher_no') or ''),
                str(row.get('reference_no') or ''),
                str(row.get('narration') or ''),
                str(row.get('source') or ''),
                str(row.get('status') or 'POSTED'),
            ]).lower()
        ]
    source_options = _je_source_filter_options()
    source_filter_label = 'All sources'
    if source_filter != 'all':
        source_filter_label = next(
            (str(o.get('label') or o.get('id')) for o in source_options if str(o.get('id') or '').upper() == source_filter),
            source_filter,
        )
    closed_periods: List[Dict[str, Any]] = []
    default_voucher_date = datetime.now().strftime('%Y-%m-%d')
    try:
        from addons.accounts.period_closing_db import list_closed_periods, resolve_open_voucher_date
        closed_periods = list_closed_periods()
        preferred = str((journal_data or {}).get('voucher_date') or default_voucher_date)[:10]
        default_voucher_date = resolve_open_voucher_date(preferred)
        if journal_data and not (journal_data.get('voucher_date') or '').strip():
            journal_data['voucher_date'] = default_voucher_date
        elif journal_data and (journal_data.get('voucher_date') or '').strip():
            # Keep edit/draft date as-is; client + save validation block closed dates.
            pass
        else:
            default_voucher_date = resolve_open_voucher_date(default_voucher_date)
    except Exception:
        closed_periods = []
    return render_template(
        'accounts/journal_entry.html',
        accounts=accounts,
        je_account_balances=je_account_balances,
        je_party_balances=je_party_balances,
        je_suppliers=je_suppliers,
        je_customers=je_customers,
        default_supplier_payable=def_sup,
        default_customer_receivable=def_cust,
        entries=entries,
        default_voucher_date=default_voucher_date,
        date_from=date_from,
        date_to=date_to,
        show_form=show_form,
        journal_data=journal_data,
        journal_lines=journal_lines,
        search_term=search_term,
        status_filter=status_filter,
        source_filter=source_filter,
        source_options=source_options,
        source_filter_label=source_filter_label,
        je_closed_periods=closed_periods,
    )

@bp.route('/accounts/journal-entry/voucher/<voucher_no>', methods=['GET'])
def journal_voucher_view(voucher_no: str):
    """View one GL voucher (header + lines)."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _apply_db():
        return redirect(url_for('dashboard.dashboard'))
    ensure_gl_tables()
    v = (voucher_no or '').strip()
    detail = get_gl_voucher_detail(v)
    if not detail:
        flash('Voucher not found.', 'error')
        return redirect(url_for('accounts.journal_entry'))
    rdf = (request.args.get('date_from') or '').strip()
    rdt = (request.args.get('date_to') or '').strip()
    reversal_vno = get_gl_voucher_reversal_no(v)
    can_reverse = _je_voucher_can_reverse(detail)
    can_edit = _je_voucher_can_edit(detail)
    can_change_posting_date = _accounts_session_is_admin()
    default_reversal_date = datetime.now().strftime('%Y-%m-%d')
    period_ctx = _accounts_closed_period_context(detail.get('voucher_date'))
    return render_template(
        'accounts/journal_voucher_view.html',
        v=detail,
        date_from=rdf,
        date_to=rdt,
        can_reverse=can_reverse,
        can_edit=can_edit,
        can_change_posting_date=can_change_posting_date,
        reversal_vno=reversal_vno,
        default_reversal_date=default_reversal_date,
        closed_periods=period_ctx.get('closed_periods') or [],
        default_posting_date=period_ctx.get('default_voucher_date') or default_reversal_date,
    )


@bp.route('/accounts/journal-entry/voucher/<path:voucher_no>/pdf', methods=['GET'])
def journal_voucher_pdf(voucher_no: str):
    """PDF voucher for a posted Journal Entry / GL voucher."""
    if not session.get('user'):
        return Response('Not authenticated', status=401, mimetype='text/plain')
    if not _apply_db():
        return Response('Database/location not assigned.', status=403, mimetype='text/plain')
    if not REPORTLAB_AVAILABLE:
        return Response('PDF is not available (install reportlab).', status=500, mimetype='text/plain')
    ensure_gl_tables()
    v = (voucher_no or '').strip()
    if not v:
        return Response('voucher_no is required.', status=400, mimetype='text/plain')
    detail = get_gl_voucher_detail(v)
    if not detail:
        return Response('Voucher not found.', status=404, mimetype='text/plain')
    try:
        pdf_bytes = _build_journal_voucher_pdf(detail)
    except Exception as exc:
        return Response(f'Could not build PDF: {exc}', status=500, mimetype='text/plain')
    if not pdf_bytes:
        return Response('Could not build PDF.', status=500, mimetype='text/plain')
    safe_name = ''.join(ch if ch.isalnum() or ch in ('-', '_', '.') else '_' for ch in v) or 'journal'
    return Response(
        pdf_bytes,
        mimetype='application/pdf',
        headers={'Content-Disposition': f'inline; filename="JV_{safe_name}.pdf"'},
    )


@bp.route('/accounts/journal-entry/voucher/<voucher_no>/reverse', methods=['POST'])
def journal_entry_reverse(voucher_no: str):
    """Post a reversing journal entry for a posted GL voucher (single DB transaction)."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _apply_db():
        return redirect(url_for('dashboard.dashboard'))
    ensure_gl_tables()
    orig = (voucher_no or '').strip()
    rdf = (request.form.get('return_date_from') or request.args.get('date_from') or '').strip()
    rdt = (request.form.get('return_date_to') or request.args.get('date_to') or '').strip()
    redirect_kw: Dict[str, Any] = {}
    if rdf:
        redirect_kw['date_from'] = rdf
    if rdt:
        redirect_kw['date_to'] = rdt

    def _redirect_view(msg: Optional[str] = None, category: str = 'error') -> Any:
        if msg:
            flash(msg, category)
        return redirect(url_for('accounts.journal_voucher_view', voucher_no=orig, **redirect_kw))

    if not _je_reverse_try_acquire_session_lock():
        return _redirect_view('A journal reversal is already in progress in this session. Please wait.')

    try:
        submitted_nonce = (request.form.get('save_nonce') or '').strip()
        if not verify_consume_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY, submitted_nonce):
            issue_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY)
            return _redirect_view('Duplicate or invalid submit. Reload the voucher page and try again.')

        detail = get_gl_voucher_detail(orig)
        if not detail:
            return _redirect_view('Voucher not found.')
        if not _je_voucher_can_reverse(detail):
            existing = get_gl_voucher_reversal_no(orig)
            if existing:
                return _redirect_view(f'This voucher was already reversed as {existing}.', 'warning')
            return _redirect_view('This voucher cannot be reversed.')

        rev_date = _parse_iso_date(request.form.get('reversal_date', '')) or datetime.now().strftime('%Y-%m-%d')
        remarks = (request.form.get('reversal_remarks') or '').strip()
        user = str(session.get('user') or '')

        try:
            with _get_connection() as conn:
                rev_vno = reverse_gl_journal_voucher(
                    orig,
                    voucher_date=rev_date,
                    remarks=remarks,
                    created_by=user,
                    conn=conn,
                    commit=False,
                )
                # Keep Cash Payment Voucher in sync when its posted GL is reversed.
                if str(detail.get('source') or '').strip().upper() == 'CPV':
                    _cpv_mark_reversed_for_gl(orig, user, conn=conn)
                conn.commit()
            flash(f'Journal reversed successfully. Reversal voucher: {rev_vno}', 'success')
            return redirect(url_for('accounts.journal_voucher_view', voucher_no=rev_vno, **redirect_kw))
        except Exception as exc:
            return _redirect_view(str(exc))
    finally:
        _je_reverse_release_session_lock()


@bp.route('/accounts/journal-entry/voucher/<voucher_no>/change-posting-date', methods=['POST'])
def journal_entry_change_posting_date(voucher_no: str):
    """Admin-only: change posting date (VOUCHER_DATE) on a posted GL voucher."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _apply_db():
        return redirect(url_for('dashboard.dashboard'))
    orig = (voucher_no or '').strip()
    rdf = (request.form.get('return_date_from') or request.args.get('date_from') or '').strip()
    rdt = (request.form.get('return_date_to') or request.args.get('date_to') or '').strip()
    redirect_kw: Dict[str, Any] = {}
    if rdf:
        redirect_kw['date_from'] = rdf
    if rdt:
        redirect_kw['date_to'] = rdt

    def _redirect_view(msg: Optional[str] = None, category: str = 'error') -> Any:
        if msg:
            flash(msg, category)
        return redirect(url_for('accounts.journal_voucher_view', voucher_no=orig, **redirect_kw))

    if not _accounts_session_is_admin():
        return _redirect_view('Only administrators can change the journal posting date.')

    submitted_nonce = (request.form.get('save_nonce') or '').strip()
    if not verify_consume_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY, submitted_nonce):
        issue_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY)
        return _redirect_view('Duplicate or invalid submit. Reload the voucher page and try again.')

    new_date = (request.form.get('new_posting_date') or request.form.get('posting_date') or '').strip()
    ok, err = _change_gl_voucher_posting_date(orig, new_date)
    if not ok:
        issue_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY)
        return _redirect_view(err or 'Could not change posting date.')
    issue_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY)
    flash(f'Posting date updated to {(_parse_iso_date(new_date) or new_date)[:10]} for voucher {orig}.', 'success')
    return redirect(url_for('accounts.journal_voucher_view', voucher_no=orig, **redirect_kw))


@bp.route('/accounts/journal-entry/summary-pdf', methods=['GET'])
def journal_entry_summary_pdf():
    """Summary PDF of GL vouchers in optional date range (all sources, not only manual)."""
    if not session.get('user'):
        return Response('Not authenticated', status=401, mimetype='text/plain')
    if not _apply_db():
        return Response('Database/location not assigned.', status=403, mimetype='text/plain')
    if not REPORTLAB_AVAILABLE:
        return Response('PDF is not available (install reportlab).', status=500, mimetype='text/plain')
    try:
        ensure_gl_tables()
    except Exception:
        pass
    date_from = _parse_iso_date(request.args.get('date_from', ''))
    date_to = _parse_iso_date(request.args.get('date_to', ''))
    source_filter = (request.args.get('source') or 'all').strip().upper()
    if source_filter in ('', 'ALL', '*', 'DRAFT'):
        source_filter = 'all'
    try:
        entries = list_gl_journal_entries(
            date_from=date_from or None,
            date_to=date_to or None,
            limit=2000,
            source=None if source_filter == 'all' else source_filter,
        )
    except Exception as e:
        return Response(f'Could not load vouchers: {e}', status=500, mimetype='text/plain')
    df = str(date_from or '—')
    dt = str(date_to or '—')
    pdf_bytes = _build_journal_vouchers_summary_pdf(entries, df, dt)
    if not pdf_bytes:
        return Response('Failed to generate PDF.', status=500, mimetype='text/plain')
    filename = f"gl_vouchers_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return Response(pdf_bytes, mimetype='application/pdf', headers={'Content-Disposition': f'inline; filename="{filename}"'})

@bp.route('/accounts/tax')
def tax_accounts():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _apply_db():
        return redirect(url_for('dashboard.dashboard'))
    date_from = _parse_iso_date(request.args.get('date_from', ''))
    date_to = _parse_iso_date(request.args.get('date_to', ''))
    tb = get_trial_balance_report(date_from=date_from or None, date_to=date_to or None)
    rows = [r for r in tb if any((k in (r.get('name') or '').upper() for k in ('VAT', 'GST', 'TAX'))) or any((k in (r.get('code') or '').upper() for k in ('VAT', 'GST', 'TAX')))]
    return render_template('accounts/tax_accounts.html', rows=rows, date_from=date_from, date_to=date_to)

def _enrich_trial_balance_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Attach chart ``account_id`` for drill-down links."""
    id_by_code: Dict[str, int] = {}
    try:
        for acc in ChartOfAccounts.get_all(limit=10000) or []:
            c = str(acc.get('code') or '').strip().upper()
            if c:
                try:
                    id_by_code[c] = int(acc.get('account_id') or 0)
                except (TypeError, ValueError):
                    pass
    except Exception:
        pass
    out: List[Dict[str, Any]] = []
    for r in rows or []:
        row = dict(r)
        code = str(row.get('code') or '').strip()
        aid = id_by_code.get(code.upper())
        if aid:
            row['account_id'] = aid
        out.append(row)
    return out


def _get_trial_balance_report_context() -> Dict[str, Any]:
    """Trial balance for HTML, PDF, Excel (query ``date_from`` / ``date_to``)."""
    date_from = _parse_iso_date(request.args.get('date_from', ''))
    date_to = _parse_iso_date(request.args.get('date_to', ''))
    exclude_closing = _request_exclude_closing()
    from addons.purchase.controllers.routes import _get_company_profile
    company = _get_company_profile()
    company_name = str(company.get('name') or session.get('location_name') or 'Company')
    raw = get_trial_balance_report(
        date_from=date_from or None,
        date_to=date_to or None,
        exclude_closing=exclude_closing,
    )
    rows = _enrich_trial_balance_rows(raw)
    total_debit = round(sum((float(r.get('debit') or 0) for r in rows)), 2)
    total_credit = round(sum((float(r.get('credit') or 0) for r in rows)), 2)

    def _tb_fmt(iso: str) -> str:
        if not (iso or '').strip():
            return ''
        try:
            return datetime.strptime(iso.strip()[:10], '%Y-%m-%d').strftime('%d %B %Y')
        except Exception:
            return iso

    df_disp = _tb_fmt(date_from) if date_from else ''
    dt_disp = _tb_fmt(date_to) if date_to else ''
    if df_disp and dt_disp:
        period_display = f'{df_disp} to {dt_disp}'
    elif dt_disp:
        period_display = f'Up to {dt_disp}'
    elif df_disp:
        period_display = f'From {df_disp}'
    else:
        period_display = 'All dates'
    if exclude_closing:
        period_display = f'{period_display} (excluding period closing & reopen reversals)'
    return {
        'company_name': company_name,
        'period_display': period_display,
        'date_from': date_from,
        'date_to': date_to,
        'rows': rows,
        'total_debit': total_debit,
        'total_credit': total_credit,
        'exclude_closing': exclude_closing,
    }


def _build_trial_balance_pdf(ctx: Dict[str, Any]) -> bytes:
    """Trial balance PDF (portrait, Times/maroon style)."""
    if not REPORTLAB_AVAILABLE:
        return b''
    from xml.sax.saxutils import escape as _xml_esc_tb

    company_name = str(ctx.get('company_name') or '')
    period_display = str(ctx.get('period_display') or '')
    rows = list(ctx.get('rows') or [])
    total_debit = float(ctx.get('total_debit') or 0)
    total_credit = float(ctx.get('total_credit') or 0)

    def _m(v: float) -> str:
        return f'{float(v):,.2f}'

    styles = getSampleStyleSheet()
    MAROON = colors.HexColor('#6b0f1a')
    GRAY = colors.HexColor('#e8e8e8')
    BORDER = colors.HexColor('#333333')
    TEXT = colors.HexColor('#1a1a1a')
    PAD = 5
    W = 7.47 * inch

    def _s(name: str, **kw: Any) -> ParagraphStyle:
        base = kw.pop('parent', styles['Normal'])
        tc = kw.pop('textColor', TEXT)
        return ParagraphStyle(name, parent=base, textColor=tc, **kw)

    N8 = _s('tb8', fontName='Times-Roman', fontSize=8, leading=10)
    N8B = _s('tb8b', fontName='Times-Bold', fontSize=8, leading=10)
    N8R = _s('tb8r', fontName='Times-Roman', fontSize=8, leading=10, alignment=TA_RIGHT)
    N8i = _s('tb8i', fontName='Times-Italic', fontSize=8, leading=10, textColor=colors.HexColor('#444444'))
    N9B = _s('tb9b', fontName='Times-Bold', fontSize=9, leading=11, textColor=MAROON, alignment=TA_CENTER)
    FOOT = _s('tbft', fontName='Times-Roman', fontSize=6.5, leading=9, textColor=colors.HexColor('#666666'))
    h_center = _s('tbhc', fontName='Times-Bold', fontSize=7, leading=9, textColor=colors.white, alignment=TA_CENTER)
    h_right = _s('tbhr', fontName='Times-Bold', fontSize=7, leading=9, textColor=colors.white, alignment=TA_RIGHT)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=0.5 * inch,
        bottomMargin=0.4 * inch,
        leftMargin=0.45 * inch,
        rightMargin=0.45 * inch,
    )
    elements: List[Any] = []
    elements.append(Paragraph(f"<b>{_xml_esc_tb(company_name or 'Company')}</b>", _s('tbco', fontName='Times-Bold', fontSize=11, leading=14, alignment=TA_CENTER)))
    if period_display:
        elements.append(Paragraph(
            f'<i>Trial balance — {_xml_esc_tb(period_display)}.</i>',
            _s('tbper', fontName='Times-Italic', fontSize=8.5, leading=11, alignment=TA_CENTER, textColor=TEXT),
        ))
    elements.append(Paragraph('<i>(All amounts in reporting currency.)</i>', N8i))
    elements.append(Spacer(1, 6))
    elements.append(Paragraph('<b>TRIAL BALANCE</b>', N9B))
    elements.append(Spacer(1, 2))
    line = Table([['']], colWidths=[W], rowHeights=[2], hAlign='CENTER')
    line.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), MAROON)]))
    elements.append(line)
    elements.append(Spacer(1, 6))

    head = [
        Paragraph('<b>Code</b>', h_center),
        Paragraph('<b>Account name</b>', h_center),
        Paragraph('<b>Type</b>', h_center),
        Paragraph('<b>Debit</b>', h_right),
        Paragraph('<b>Credit</b>', h_right),
        Paragraph('<b>Closing</b>', h_right),
    ]
    data: List[List[Any]] = [head]
    if not rows:
        data.append([Paragraph('<i>No trial balance data for this period.</i>', N8i), '', '', '', '', ''])
    else:
        for row in rows:
            data.append([
                Paragraph(_xml_esc_tb(str(row.get('code') or '')), N8),
                Paragraph(_xml_esc_tb(str(row.get('name') or ''))[:120], N8),
                Paragraph(_xml_esc_tb(str(row.get('type') or '')), N8),
                Paragraph(_m(float(row.get('debit') or 0)), N8R),
                Paragraph(_m(float(row.get('credit') or 0)), N8R),
                Paragraph(_m(float(row.get('balance') or 0)), N8R),
            ])
    data.append([
        Paragraph('<b>Total</b>', N8B),
        '', '',
        Paragraph(f'<b>{_m(total_debit)}</b>', N8B),
        Paragraph(f'<b>{_m(total_credit)}</b>', N8B),
        '',
    ])
    cw = [0.85 * inch, 2.55 * inch, 0.9 * inch, 0.95 * inch, 0.95 * inch, 0.95 * inch]
    t = Table(data, colWidths=cw, repeatRows=1, hAlign='LEFT')
    nrows = len(data)
    ts = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1a1a')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Times-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 7),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LINEABOVE', (0, 0), (-1, 0), 0.5, BORDER),
        ('LINEBELOW', (0, 0), (-1, 0), 0.5, BORDER),
        ('LEFTPADDING', (0, 0), (-1, -1), PAD),
        ('RIGHTPADDING', (0, 0), (-1, -1), PAD),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]
    for r_i in range(1, nrows - 1):
        for c_i in range(3, 6):
            ts.append(('BACKGROUND', (c_i, r_i), (c_i, r_i), GRAY))
    ts.append(('LINEABOVE', (0, nrows - 1), (-1, nrows - 1), 1.0, colors.black))
    ts.append(('LINEBELOW', (0, nrows - 1), (-1, nrows - 1), 1.0, colors.black))
    t.setStyle(TableStyle(ts))
    elements.append(t)
    elements.append(Spacer(1, 10))
    elements.append(Paragraph('Computer-generated from the general ledger. No signature is required.', FOOT))
    doc.build(elements)
    return buffer.getvalue()


def _build_trial_balance_excel(ctx: Dict[str, Any]) -> Optional[bytes]:
    """Trial balance as .xlsx."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
    except ImportError:
        return None

    rows = list(ctx.get('rows') or [])
    total_debit = float(ctx.get('total_debit') or 0)
    total_credit = float(ctx.get('total_credit') or 0)
    thin = Side(style='thin', color='CCCCCC')
    box = Border(left=thin, right=thin, top=thin, bottom=thin)
    hdr_fill = PatternFill(start_color='1a1a1a', end_color='1a1a1a', fill_type='solid')
    hdr_font = Font(bold=True, color='FFFFFF', size=10)
    num_fill = PatternFill(start_color='E8E8E8', end_color='E8E8E8', fill_type='solid')
    wb = Workbook()
    ws = wb.active
    ws.title = 'Trial Balance'
    ws['A1'] = str(ctx.get('company_name') or 'Company')
    ws['A1'].font = Font(bold=True, size=13)
    ws.merge_cells('A1:F1')
    ws['A2'] = f"Trial balance — {ctx.get('period_display') or ''}"
    ws.merge_cells('A2:F2')
    ws['A3'] = f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    ws.merge_cells('A3:F3')
    r = 5
    headers = ['Code', 'Account name', 'Type', 'Debit', 'Credit', 'Closing']
    for c, h in enumerate(headers, 1):
        cell = ws.cell(row=r, column=c, value=h)
        cell.fill = hdr_fill
        cell.font = hdr_font
        cell.border = box
        cell.alignment = Alignment(horizontal='right' if c >= 4 else 'left', wrap_text=True)
    r += 1
    for row in rows:
        ws.cell(row=r, column=1, value=str(row.get('code') or '')).border = box
        ws.cell(row=r, column=2, value=str(row.get('name') or '')).border = box
        ws.cell(row=r, column=3, value=str(row.get('type') or '')).border = box
        for c, key in ((4, 'debit'), (5, 'credit'), (6, 'balance')):
            cell = ws.cell(row=r, column=c, value=round(float(row.get(key) or 0), 2))
            cell.border = box
            cell.alignment = Alignment(horizontal='right')
            cell.fill = num_fill
        r += 1
    if not rows:
        ws.cell(row=r, column=1, value='No trial balance data for this period.')
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=6)
        r += 1
    for c, val in enumerate((None, 'Total', None, total_debit, total_credit, None), 1):
        if val is not None:
            cell = ws.cell(row=r, column=c, value=val if c == 2 else round(float(val), 2))
            cell.font = Font(bold=True, size=10)
            cell.border = box
            if c >= 4:
                cell.alignment = Alignment(horizontal='right')
    for col, w in enumerate([14, 40, 14, 14, 14, 14], 1):
        ws.column_dimensions[get_column_letter(col)].width = w
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@bp.route('/accounts/trial-balance')
def trial_balance():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _apply_db():
        return redirect(url_for('dashboard.dashboard'))
    ctx = _get_trial_balance_report_context()
    return render_template('accounts/trial_balance.html', **ctx)


def _account_ledger_api_json(
    code: str,
    date_from: Optional[str],
    date_to: Optional[str],
    *,
    empty_means: str = 'ytd',
    exclude_closing: bool = False,
):
    """Shared JSON payload for account GL drill-down (trial balance, balance sheet)."""
    if not code:
        return jsonify({'success': False, 'error': 'account_code is required'}, 400)
    try:
        ledger = get_account_ledger(
            code,
            date_from=date_from or None,
            date_to=date_to or None,
            empty_means=empty_means,
            exclude_closing=exclude_closing,
        )
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}, 500)
    acc = ChartOfAccounts.get_by_code(code) or {}
    account_id = None
    try:
        if acc.get('account_id'):
            account_id = int(acc.get('account_id'))
    except (TypeError, ValueError):
        account_id = None
    return jsonify({
        'success': True,
        'account': {
            'code': code,
            'name': acc.get('name') or ledger.get('account_code') or code,
            'type': acc.get('type') or '',
            'account_id': account_id,
        },
        'ledger': ledger,
    })


@bp.route('/accounts/trial-balance/api/ledger', methods=['GET'])
def trial_balance_ledger_api():
    """GL lines for one account (trial balance drill-down)."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    if not _apply_db():
        return jsonify({'success': False, 'error': 'Database/location not assigned.'}, 403)
    code = (request.args.get('account_code') or '').strip()
    date_from = _parse_iso_date(request.args.get('date_from', ''))
    date_to = _parse_iso_date(request.args.get('date_to', ''))
    # Blank From/To must mean all dates — same as get_trial_balance_report
    return _account_ledger_api_json(
        code,
        date_from,
        date_to,
        empty_means='all',
        exclude_closing=_request_exclude_closing(),
    )


@bp.route('/accounts/balance-sheet/api/ledger', methods=['GET'])
def balance_sheet_ledger_api():
    """GL lines for one account (balance sheet drill-down, cumulative to as-of date)."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    if not _apply_db():
        return jsonify({'success': False, 'error': 'Database/location not assigned.'}, 403)
    code = (request.args.get('account_code') or '').strip()
    date_from = _parse_iso_date(request.args.get('date_from', ''))
    date_to = _parse_iso_date(request.args.get('date_to', '') or request.args.get('as_of_date', ''))
    return _account_ledger_api_json(code, date_from, date_to)


@bp.route('/accounts/trial-balance/pdf', methods=['GET'])
def trial_balance_pdf():
    """Trial balance PDF (inline)."""
    if not session.get('user'):
        return Response('Not authenticated', status=401, mimetype='text/plain')
    if not _apply_db():
        return Response('Database/location not assigned.', status=403, mimetype='text/plain')
    if not REPORTLAB_AVAILABLE:
        return Response('PDF is not available (install reportlab).', status=500, mimetype='text/plain')
    ctx = _get_trial_balance_report_context()
    pdf_bytes = _build_trial_balance_pdf(ctx)
    if not pdf_bytes:
        return Response('Failed to generate PDF.', status=500, mimetype='text/plain')
    filename = f"trial_balance_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return Response(pdf_bytes, mimetype='application/pdf', headers={'Content-Disposition': f'inline; filename="{filename}"'})


@bp.route('/accounts/trial-balance/export-excel', methods=['GET'])
def trial_balance_excel():
    """Trial balance .xlsx download."""
    if not session.get('user'):
        return Response('Not authenticated', status=401, mimetype='text/plain')
    if not _apply_db():
        return Response('Database/location not assigned.', status=403, mimetype='text/plain')
    ctx = _get_trial_balance_report_context()
    xlsx_bytes = _build_trial_balance_excel(ctx)
    if xlsx_bytes is None:
        return Response('Excel export requires openpyxl.', status=500, mimetype='text/plain')
    filename = f"trial_balance_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return Response(
        xlsx_bytes,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )

@bp.route('/accounts/profit-loss')
def profit_loss():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _apply_db():
        return redirect(url_for('dashboard.dashboard'))
    ctx = _get_profit_loss_report_context()
    return render_template('accounts/profit_loss.html', **ctx)

@bp.route('/accounts/profit-loss/pdf', methods=['GET'])
def profit_loss_pdf():
    """P&L PDF (inline). Query ``pdf_mode=single|comparison`` (default comparison)."""
    if not session.get('user'):
        return Response('Not authenticated', status=401, mimetype='text/plain')
    if not _apply_db():
        return Response('Database/location not assigned.', status=403, mimetype='text/plain')
    if not REPORTLAB_AVAILABLE:
        return Response('PDF is not available (install reportlab).', status=500, mimetype='text/plain')
    pdf_mode = _request_pl_pdf_mode()
    ctx = _get_profit_loss_report_context()
    pdf_bytes = _build_profit_loss_pdf(ctx, mode=pdf_mode)
    if not pdf_bytes:
        return Response('Failed to generate PDF.', status=500, mimetype='text/plain')
    suffix = 'period' if pdf_mode == 'single' else 'comparison'
    filename = f"profit_loss_{suffix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return Response(pdf_bytes, mimetype='application/pdf', headers={'Content-Disposition': f'inline; filename="{filename}"'})

@bp.route('/accounts/profit-loss/export-excel', methods=['GET'])
def profit_loss_excel():
    """P&L comparative as .xlsx download."""
    if not session.get('user'):
        return Response('Not authenticated', status=401, mimetype='text/plain')
    if not _apply_db():
        return Response('Database/location not assigned.', status=403, mimetype='text/plain')
    ctx = _get_profit_loss_report_context()
    xlsx_bytes = _build_profit_loss_excel(ctx)
    if xlsx_bytes is None:
        return Response('Excel export requires openpyxl. Install with: pip install openpyxl', status=500, mimetype='text/plain')
    filename = f"profit_loss_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return Response(xlsx_bytes, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers={'Content-Disposition': f'attachment; filename="{filename}"'})

@bp.route('/accounts/balance-sheet')
def balance_sheet():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _apply_db():
        return redirect(url_for('dashboard.dashboard'))
    ctx = _get_balance_sheet_report_context()
    return render_template('accounts/balance_sheet.html', **ctx)


@bp.route('/accounts/balance-sheet/pdf', methods=['GET'])
def balance_sheet_pdf():
    """Balance sheet as PDF (inline)."""
    if not session.get('user'):
        return Response('Not authenticated', status=401, mimetype='text/plain')
    if not _apply_db():
        return Response('Database/location not assigned.', status=403, mimetype='text/plain')
    if not REPORTLAB_AVAILABLE:
        return Response('PDF is not available (install reportlab).', status=500, mimetype='text/plain')
    ctx = _get_balance_sheet_report_context()
    layout = _normalize_balance_sheet_pdf_layout(request.args.get('layout', ''))
    pdf_bytes = _build_balance_sheet_pdf(ctx, layout=layout)
    if not pdf_bytes:
        return Response('Failed to generate PDF.', status=500, mimetype='text/plain')
    layout_slug = '2col' if layout == 'two_column' else '1col'
    filename = f"balance_sheet_{layout_slug}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return Response(pdf_bytes, mimetype='application/pdf', headers={'Content-Disposition': f'inline; filename="{filename}"'})


@bp.route('/accounts/balance-sheet/export-excel', methods=['GET'])
def balance_sheet_excel():
    """Balance sheet as .xlsx download."""
    if not session.get('user'):
        return Response('Not authenticated', status=401, mimetype='text/plain')
    if not _apply_db():
        return Response('Database/location not assigned.', status=403, mimetype='text/plain')
    ctx = _get_balance_sheet_report_context()
    xlsx_bytes = _build_balance_sheet_excel(ctx)
    if xlsx_bytes is None:
        return Response('Excel export requires openpyxl. Install with: pip install openpyxl', status=500, mimetype='text/plain')
    filename = f"balance_sheet_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return Response(
        xlsx_bytes,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )

def _pdc_bank_accounts_coa() -> List[Dict[str, Any]]:
    """Postable ASSET accounts under cash/bank COA subtree — same rule as Supplier Payment cash/bank picker."""
    coa_accounts = ChartOfAccounts.get_all(limit=10000, offset=0) or []
    by_id = {a.get('account_id'): a for a in coa_accounts}
    rows: List[Dict[str, Any]] = []
    for a in coa_accounts:
        if (a.get('type') or '').upper() != 'ASSET':
            continue
        if not bool(a.get('is_postable')):
            continue
        if not is_cash_bank_family_account(a, by_id):
            continue
        code = (a.get('code') or '').strip()
        if not code:
            continue
        rows.append({'account_id': a.get('account_id'), 'code': code, 'name': (a.get('name') or '').strip()})
    rows.sort(key=lambda x: str(x.get('code') or ''))
    return rows

def _pdc_party_picklists() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Customers and suppliers for PDC add/edit party pick list (tenant DB)."""
    customers = list(get_customers_for_journal_party_select(limit=20000) or [])
    customers.sort(key=lambda c: str(c.get('customercode') or ''))
    loc = session.get('location_code')
    suppliers = list(get_supplier_list(location_code=loc, limit=5000, row_cap=5000) or [])
    suppliers.sort(key=lambda s: str(s.get('suppliercode') or ''))
    return (customers, suppliers)

@bp.route('/accounts/pdc')
def pdc_tracker():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    filters = {'pdc_type': request.args.get('pdc_type', ''), 'status': request.args.get('status', ''), 'party_type': request.args.get('party_type', ''), 'date_from': _parse_iso_date(request.args.get('date_from', '')), 'date_to': _parse_iso_date(request.args.get('date_to', '')), 'search': request.args.get('search', '').strip()}
    rows = get_pdc_list(**{k: v or None for k, v in filters.items()})
    summary = get_pdc_summary()
    pdc_party_customers, pdc_party_suppliers = _pdc_party_picklists()
    pdc_bank_accounts = _pdc_bank_accounts_coa()
    return render_template('accounts/pdc_tracker.html', rows=rows, summary=summary, filters=filters, today=datetime.now().strftime('%Y-%m-%d'), pdc_party_customers=pdc_party_customers, pdc_party_suppliers=pdc_party_suppliers, pdc_bank_accounts=pdc_bank_accounts)

@bp.route('/accounts/pdc/add', methods=['GET', 'POST'])
def pdc_add():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if request.method == 'POST':
        try:
            pdc_id = save_pdc(pdc_type=request.form.get('pdc_type', '').strip().upper(), cheque_no=request.form.get('cheque_no', '').strip(), cheque_date=request.form.get('cheque_date', '').strip(), bank_name=request.form.get('bank_name', '').strip(), branch_name=request.form.get('branch_name', '').strip(), amount=float(request.form.get('amount') or 0), party_type=request.form.get('party_type', '').strip().upper(), party_code=request.form.get('party_code', '').strip(), party_name=request.form.get('party_name', '').strip(), narration=request.form.get('narration', '').strip(), remarks=request.form.get('remarks', '').strip(), locationcode=session.get('location_code'), created_by=str(session.get('user') or ''))
            flash(f'PDC #{pdc_id} added successfully.', 'success')
        except Exception as e:
            flash(f'Error saving PDC: {e}', 'error')
        return redirect(url_for('accounts.pdc_tracker'))
    pdc_party_customers, pdc_party_suppliers = _pdc_party_picklists()
    pdc_bank_accounts = _pdc_bank_accounts_coa()
    return render_template('accounts/pdc_tracker.html', rows=[], summary=get_pdc_summary(), filters={}, today=datetime.now().strftime('%Y-%m-%d'), show_form=True, edit_data=None, pdc_party_customers=pdc_party_customers, pdc_party_suppliers=pdc_party_suppliers, pdc_bank_accounts=pdc_bank_accounts)

@bp.route('/accounts/pdc/<int:pdc_id>/edit', methods=['GET', 'POST'])
def pdc_edit(pdc_id: int):
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    record = get_pdc_by_id(pdc_id)
    if not record:
        flash('PDC record not found.', 'error')
        return redirect(url_for('accounts.pdc_tracker'))
    if request.method == 'POST':
        try:
            save_pdc(pdc_type=request.form.get('pdc_type', '').strip().upper(), cheque_no=request.form.get('cheque_no', '').strip(), cheque_date=request.form.get('cheque_date', '').strip(), bank_name=request.form.get('bank_name', '').strip(), branch_name=request.form.get('branch_name', '').strip(), amount=float(request.form.get('amount') or 0), party_type=request.form.get('party_type', '').strip().upper(), party_code=request.form.get('party_code', '').strip(), party_name=request.form.get('party_name', '').strip(), narration=request.form.get('narration', '').strip(), remarks=request.form.get('remarks', '').strip(), locationcode=session.get('location_code'), created_by=str(session.get('user') or ''), pdc_id=pdc_id)
            flash('PDC updated successfully.', 'success')
        except Exception as e:
            flash(f'Error updating PDC: {e}', 'error')
        return redirect(url_for('accounts.pdc_tracker'))
    filters = {}
    summary = get_pdc_summary()
    rows = get_pdc_list()
    pdc_party_customers, pdc_party_suppliers = _pdc_party_picklists()
    pdc_bank_accounts = _pdc_bank_accounts_coa()
    return render_template('accounts/pdc_tracker.html', rows=rows, summary=summary, filters=filters, today=datetime.now().strftime('%Y-%m-%d'), show_form=True, edit_data=record, pdc_party_customers=pdc_party_customers, pdc_party_suppliers=pdc_party_suppliers, pdc_bank_accounts=pdc_bank_accounts)

@bp.route('/accounts/pdc/<int:pdc_id>/status', methods=['POST'])
def pdc_update_status(pdc_id: int):
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    data = request.get_json() or {}
    new_status = str(data.get('status') or '').strip().upper()
    action_date = str(data.get('action_date') or '').strip() or None
    if new_status not in ('PENDING', 'DEPOSITED', 'CLEARED', 'BOUNCED', 'CANCELLED'):
        return jsonify({'success': False, 'error': 'Invalid status'}, 400)
    ok = update_pdc_status(pdc_id, new_status, str(session.get('user') or ''), action_date)
    return jsonify({'success': ok})

@bp.route('/accounts/pdc/<int:pdc_id>/delete', methods=['POST'])
def pdc_delete(pdc_id: int):
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    ok = delete_pdc(pdc_id, str(session.get('user') or ''))
    if request.is_json:
        return jsonify({'success': ok})
    flash('PDC deleted.' if ok else 'Cannot delete: only Pending/Cancelled records can be deleted.', 'success' if ok else 'error')
    return redirect(url_for('accounts.pdc_tracker'))

@bp.route('/accounts/api/pdc/audit-log')
def api_pdc_audit_log():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    _pid = (request.args.get('pdc_id') or '').strip()
    pdc_id = None
    if _pid:
        try:
            pdc_id = int(_pid)
        except ValueError:
            pdc_id = None
    _lim_raw = request.args.get('limit')
    lim = 2000
    if _lim_raw is not None and str(_lim_raw).strip() != '':
        try:
            lim = int(str(_lim_raw).strip())
        except ValueError:
            lim = 2000
    if not lim:
        lim = 2000
    rows = get_pdc_audit_log(pdc_id=pdc_id, limit=lim)
    return jsonify({'success': True, 'rows': rows})

@bp.route('/accounts/api/pdc')
def api_pdc_list():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    filters = {'pdc_type': request.args.get('pdc_type', '') or None, 'status': request.args.get('status', '') or None, 'party_type': request.args.get('party_type', '') or None, 'date_from': _parse_iso_date(request.args.get('date_from', '')) or None, 'date_to': _parse_iso_date(request.args.get('date_to', '')) or None, 'search': request.args.get('search', '').strip() or None}
    rows = get_pdc_list(**filters)
    summary = get_pdc_summary()
    return jsonify({'success': True, 'rows': rows, 'summary': summary})


from addons.accounts.controllers.bank_recon_routes import register as _register_bank_recon_routes
_register_bank_recon_routes(bp)

from addons.accounts.controllers.transaction_audit_routes import register as _register_transaction_audit_routes
_register_transaction_audit_routes(bp)

from addons.accounts.controllers.tally_voucher_routes import register as _register_tally_voucher_routes
_register_tally_voucher_routes(bp)

from addons.accounts.controllers.online_settlement_routes import register as _register_online_settlement_routes
_register_online_settlement_routes(bp)

from addons.accounts.controllers.period_closing_routes import register as _register_period_closing_routes
_register_period_closing_routes(bp)

from addons.accounts.controllers.average_cost_adjustment_routes import register as _register_average_cost_adjustment_routes
_register_average_cost_adjustment_routes(bp)
