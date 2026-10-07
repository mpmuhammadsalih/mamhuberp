"""Global typeahead lookup helpers (customer, category, supplier, …)."""
from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional

from db import (
    CHART_OF_ACCOUNTS_TABLE,
    DATABASES,
    DEFAULT_PARTY_ACCOUNTS,
    GL_DIMENSION_VALUE_TABLE,
    _detect_column,
    _detect_table,
    _safe_rows,
    _table_exists,
    ensure_chart_of_accounts_table,
    ensure_gl_dimension_value_table,
    get_all_chart_of_accounts,
    get_customers_master_list,
    get_location_info_by_dbkey,
    get_supplier_list,
    normalize_gl_dimension_type,
    set_active_db_host,
    set_active_db_key,
)

LookupFn = Callable[[str, int], List[Dict[str, Any]]]


def apply_session_db_connection() -> None:
    """Use tenant DB from session when multi-DB is enabled."""
    try:
        from nexa_http import session
    except RuntimeError:
        return
    tenant_id = session.get('tenant_id')
    if tenant_id and tenant_id in DATABASES:
        set_active_db_key(tenant_id)
        set_active_db_host(None)


def resolve_location_code() -> int:
    try:
        from nexa_http import session
    except RuntimeError:
        session = {}
    location_code_value = session.get('location_code')
    if location_code_value is not None and str(location_code_value).isdigit():
        try:
            return int(location_code_value)
        except (TypeError, ValueError):
            pass
    user_dbkey = session.get('tenant_id') or location_code_value or 'HO'
    try:
        location_info = get_location_info_by_dbkey(user_dbkey)
        loc = location_info.get('locationcode')
        if loc is not None:
            return int(loc)
    except Exception:
        pass
    return 1


def normalize_customer_code(raw: Optional[str]) -> str:
    cc = (raw or '').strip()
    if not cc or cc == '0':
        return ''
    return cc


def search_customers(q: str = '', limit: int = 8) -> List[Dict[str, Any]]:
    lim = min(max(int(limit or 8), 1), 30)
    qtxt = (q or '').strip()
    tbl = _detect_table(['CUSTOMER', 'CUSTOMERS', 'customer', 'customers'])
    if not tbl:
        return []
    code_col = _detect_column(
        tbl,
        ['CUSTOMERCODE', 'CUSTOMER_CODE', 'customercode', 'CUST_CODE', 'cust_code', 'CODE'],
    )
    name_col = _detect_column(
        tbl,
        ['CUSTOMERNAME', 'CUSTOMER_NAME', 'customername', 'CUST_NAME', 'cust_name', 'NAME', 'name'],
    )
    if not code_col:
        return []
    params: Dict[str, Any] = {'lim': lim}
    where_parts = ['1=1']
    if qtxt:
        words = [w for w in re.split(r'\s+', qtxt) if w] or [qtxt]
        for i, word in enumerate(words[:4]):
            key = f'cw{i}'
            params[key] = f'%{word}%'
            parts = [f'TO_CHAR(c.{code_col}) LIKE :{key}']
            if name_col:
                parts.append(f'UPPER(c.{name_col}) LIKE UPPER(:{key})')
            where_parts.append('(' + ' OR '.join(parts) + ')')
    name_sel = f'c.{name_col}' if name_col else "''"
    sql = f"""
        SELECT * FROM (
            SELECT TO_CHAR(c.{code_col}) AS customercode, {name_sel} AS customername
            FROM {tbl} c
            WHERE {' AND '.join(where_parts)}
            ORDER BY c.{code_col}
        )
        WHERE ROWNUM <= :lim
    """
    try:
        rows = _safe_rows(sql, params) or []
    except Exception:
        rows = get_customers_master_list(for_picker=True, picker_search=qtxt, picker_limit=lim) or []
    out: List[Dict[str, Any]] = []
    for r in rows:
        code = str(
            r.get('customercode') or r.get('CUSTOMERCODE') or r.get('code') or r.get('CODE') or ''
        ).strip()
        if not code:
            continue
        name = str(
            r.get('customername') or r.get('CUSTOMERNAME') or r.get('name') or r.get('NAME') or ''
        ).strip()
        label = f'{code} — {name}' if name else code
        out.append({'code': code, 'name': name, 'label': label})
    return out


def search_categories(q: str = '', limit: int = 8) -> List[Dict[str, Any]]:
    cat_tbl = _detect_table(['CATEGORY', 'category'])
    if not cat_tbl:
        return []
    code_col = _detect_column(cat_tbl, ['CODE', 'CATEGORYCODE', 'categorycode'])
    name_col = _detect_column(cat_tbl, ['NAME', 'CATEGORYNAME', 'categoryname'])
    flag_col = _detect_column(cat_tbl, ['FLAG', 'flag'])
    loc_col = _detect_column(cat_tbl, ['LOCATIONCODE', 'locationcode'])
    if not code_col:
        return []
    cap = min(max(int(limit or 8), 1), 30)
    params: Dict[str, Any] = {'lim': cap}
    where_parts = ['1=1']
    if flag_col:
        where_parts.append(f"cat.{flag_col} = 'C'")
    if loc_col:
        where_parts.append(f'cat.{loc_col} = :loc')
        params['loc'] = resolve_location_code()
    qtxt = (q or '').strip()
    if qtxt:
        params['sw'] = f'%{qtxt}%'
        parts = [f'TO_CHAR(cat.{code_col}) LIKE :sw']
        if name_col:
            parts.append(f'UPPER(cat.{name_col}) LIKE UPPER(:sw)')
        where_parts.append('(' + ' OR '.join(parts) + ')')
    name_sel = f'cat.{name_col}' if name_col else "''"
    sql = f"""
        SELECT * FROM (
            SELECT TO_CHAR(cat.{code_col}) AS categorycode, {name_sel} AS categoryname
            FROM {cat_tbl} cat
            WHERE {' AND '.join(where_parts)}
            ORDER BY cat.{code_col}
        )
        WHERE ROWNUM <= :lim
    """
    try:
        rows = _safe_rows(sql, params) or []
    except Exception:
        return []
    out: List[Dict[str, Any]] = []
    for r in rows:
        code = str(r.get('categorycode') or r.get('CATEGORYCODE') or '').strip()
        if not code:
            continue
        name = str(r.get('categoryname') or r.get('CATEGORYNAME') or '').strip()
        label = f'{code} - {name}' if name else code
        out.append({'code': code, 'name': name, 'label': label})
    return out


def search_suppliers(q: str = '', limit: int = 8) -> List[Dict[str, Any]]:
    tbl = _detect_table(['SUPPLIER', 'supplier'])
    if not tbl:
        return []
    code_col = _detect_column(tbl, ['SUPPLIERCODE', 'suppliercode', 'CODE', 'code'])
    name_col = _detect_column(tbl, ['SUPPLIERNAME', 'suppliername', 'NAME', 'name'])
    if not code_col:
        return []
    cap = min(max(int(limit or 8), 1), 30)
    params: Dict[str, Any] = {'lim': cap}
    where_parts = ['1=1']
    qtxt = (q or '').strip()
    if qtxt:
        params['sw'] = f'%{qtxt}%'
        parts = [f'TO_CHAR(s.{code_col}) LIKE :sw']
        if name_col:
            parts.append(f'UPPER(s.{name_col}) LIKE UPPER(:sw)')
        where_parts.append('(' + ' OR '.join(parts) + ')')
    name_sel = f's.{name_col}' if name_col else "''"
    sql = f"""
        SELECT * FROM (
            SELECT TO_CHAR(s.{code_col}) AS suppliercode, {name_sel} AS suppliername
            FROM {tbl} s
            WHERE {' AND '.join(where_parts)}
            ORDER BY s.{code_col}
        )
        WHERE ROWNUM <= :lim
    """
    try:
        rows = _safe_rows(sql, params) or []
    except Exception:
        return []
    out: List[Dict[str, Any]] = []
    for r in rows:
        code = str(r.get('suppliercode') or r.get('code') or r.get('CODE') or '').strip()
        if not code:
            continue
        name = str(r.get('suppliername') or r.get('name') or r.get('NAME') or '').strip()
        label = f'{code} — {name}' if name else code
        out.append({'code': code, 'name': name, 'label': label})
    return out


def search_items(q: str = '', limit: int = 8) -> List[Dict[str, Any]]:
    im = _detect_table(['ITEMMASTER', 'itemmaster'])
    if not im:
        return []
    ic = _detect_column(im, ['ITEMCODE', 'ITEM_CODE', 'itemcode'])
    iname = _detect_column(im, ['ITEMNAME', 'ITEM_NAME', 'itemname'])
    iloc = _detect_column(im, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    imfg = _detect_column(im, ['MANUFACTURERID', 'MANUFACTURER_ID', 'manufacturerid', 'RAWABICODE', 'rawabicode'])
    if not ic:
        return []
    cap = min(max(int(limit or 8), 1), 30)
    params: Dict[str, Any] = {'lim': cap}
    where_parts = ['1=1']
    if iloc:
        where_parts.append(f'im.{iloc} = :loc')
        params['loc'] = resolve_location_code()
    qtxt = (q or '').strip()
    if qtxt:
        words = [w for w in re.split(r'\s+', qtxt) if w] or [qtxt]
        for i, word in enumerate(words[:4]):
            key = f'iw{i}'
            params[key] = f'%{word}%'
            parts = [f'TO_CHAR(im.{ic}) LIKE :{key}']
            if iname:
                parts.append(f'UPPER(im.{iname}) LIKE UPPER(:{key})')
            if imfg:
                parts.append(f'UPPER(TRIM(TO_CHAR(im.{imfg}))) LIKE UPPER(:{key})')
            where_parts.append('(' + ' OR '.join(parts) + ')')
    name_sel = f'im.{iname}' if iname else "''"
    sql = f"""
        SELECT * FROM (
            SELECT TO_CHAR(im.{ic}) AS itemcode, {name_sel} AS itemname
            FROM {im} im
            WHERE {' AND '.join(where_parts)}
            ORDER BY im.{ic}
        )
        WHERE ROWNUM <= :lim
    """
    try:
        rows = _safe_rows(sql, params) or []
    except Exception:
        return []
    out: List[Dict[str, Any]] = []
    for r in rows:
        code = str(r.get('itemcode') or r.get('ITEMCODE') or '').strip()
        if not code:
            continue
        name = str(r.get('itemname') or r.get('ITEMNAME') or '').strip()
        label = f'{code} — {name}' if name else code
        out.append({'code': code, 'name': name, 'label': label})
    return out


def search_gl_dimension(dim_type: str, q: str = '', limit: int = 8) -> List[Dict[str, Any]]:
    """Search GL dimension master (cost center, department, project)."""
    try:
        dt = normalize_gl_dimension_type(dim_type)
    except ValueError:
        return []
    ensure_gl_dimension_value_table()
    if not _table_exists(GL_DIMENSION_VALUE_TABLE):
        return []
    cap = min(max(int(limit or 8), 1), 30)
    params: Dict[str, Any] = {'dt': dt, 'lim': cap}
    where_parts = ["DIM_TYPE = :dt", "NVL(UPPER(TRIM(ACTIVE)), 'Y') = 'Y'"]
    qtxt = (q or '').strip()
    if qtxt:
        params['sw'] = f'%{qtxt}%'
        where_parts.append(
            "(UPPER(DIM_CODE) LIKE UPPER(:sw) OR UPPER(NVL(DIM_NAME, ' ')) LIKE UPPER(:sw))"
        )
    sql = f"""
        SELECT * FROM (
            SELECT DIM_CODE AS dim_code, DIM_NAME AS dim_name
            FROM {GL_DIMENSION_VALUE_TABLE}
            WHERE {' AND '.join(where_parts)}
            ORDER BY SORT_ORDER, DIM_CODE
        )
        WHERE ROWNUM <= :lim
    """
    try:
        rows = _safe_rows(sql, params) or []
    except Exception:
        rows = []
    out: List[Dict[str, Any]] = []
    for r in rows:
        code = str(r.get('dim_code') or r.get('DIM_CODE') or '').strip()
        if not code:
            continue
        name = str(r.get('dim_name') or r.get('DIM_NAME') or '').strip()
        label = f'{code} — {name}' if name else code
        out.append({'code': code, 'name': name, 'label': label})
    return out


def search_gl_accounts(q: str = '', limit: int = 8) -> List[Dict[str, Any]]:
    """Search chart of accounts (GL codes)."""
    ensure_chart_of_accounts_table()
    if not _table_exists(CHART_OF_ACCOUNTS_TABLE):
        return []
    tbl = CHART_OF_ACCOUNTS_TABLE
    code_col = _detect_column(tbl, ['CODE', 'ACCOUNT_CODE', 'ACCOUNTCODE'])
    name_col = _detect_column(tbl, ['NAME', 'ACCOUNT_NAME', 'ACCOUNTNAME'])
    type_col = _detect_column(tbl, ['TYPE', 'ACCOUNT_TYPE', 'ACCOUNTTYPE'])
    if not code_col:
        return []
    cap = min(max(int(limit or 8), 1), 30)
    params: Dict[str, Any] = {'lim': cap}
    where_parts = ['1=1']
    qtxt = (q or '').strip()
    if qtxt:
        params['sw'] = f'%{qtxt}%'
        parts = [f'TO_CHAR(a.{code_col}) LIKE :sw']
        if name_col:
            parts.append(f'UPPER(a.{name_col}) LIKE UPPER(:sw)')
        if type_col:
            parts.append(f'UPPER(a.{type_col}) LIKE UPPER(:sw)')
        where_parts.append('(' + ' OR '.join(parts) + ')')
    name_sel = f'a.{name_col}' if name_col else "''"
    type_sel = f'a.{type_col}' if type_col else "''"
    sql = f"""
        SELECT * FROM (
            SELECT TO_CHAR(a.{code_col}) AS account_code, {name_sel} AS account_name,
                   {type_sel} AS account_type
            FROM {tbl} a
            WHERE {' AND '.join(where_parts)}
            ORDER BY a.{code_col}
        )
        WHERE ROWNUM <= :lim
    """
    try:
        rows = _safe_rows(sql, params) or []
    except Exception:
        rows = []
    out: List[Dict[str, Any]] = []
    for r in rows:
        code = str(r.get('account_code') or r.get('code') or '').strip()
        if not code:
            continue
        name = str(r.get('account_name') or r.get('name') or '').strip()
        acc_type = str(r.get('account_type') or r.get('type') or '').strip().upper()
        label = f'{code} — {name} (GL)' if name else f'{code} (GL)'
        out.append({
            'code': code,
            'name': name,
            'label': label,
            'kind': 'GL',
            'party_type': '',
            'party_code': '',
            'account_type': acc_type,
        })
    return out


def search_journal_accounts(q: str = '', limit: int = 8) -> List[Dict[str, Any]]:
    """Journal line picker: GL accounts, suppliers (payable), customers (receivable)."""
    cap = min(max(int(limit or 8), 1), 30)
    qtxt = (q or '').strip()
    out: List[Dict[str, Any]] = []
    seen = set()

    def push(row: Dict[str, Any]) -> None:
        if len(out) >= cap:
            return
        code = str(row.get('code') or '').strip()
        if not code:
            return
        # Dedupe by kind + party + GL code so many suppliers/customers
        # sharing one payable/receivable account still appear separately.
        kind = str(row.get('kind') or row.get('party_type') or 'GL').strip().upper() or 'GL'
        party = str(row.get('party_code') or '').strip()
        key = f'{kind}|{party}|{code}'
        if key in seen:
            return
        seen.add(key)
        out.append(row)

    per = max(3, cap // 3 + 1)
    for row in search_gl_accounts(qtxt, limit=per):
        push(row)

    def_sup = str((DEFAULT_PARTY_ACCOUNTS or {}).get('supplier_payable') or '2110').strip()
    for s in get_supplier_list(search=qtxt or None, limit=per, row_cap=per) or []:
        if len(out) >= cap:
            break
        p_code = str(s.get('suppliercode') or '').strip()
        if not p_code:
            continue
        raw_pa = str(s.get('payableaccount') or '').strip()
        pa = raw_pa if raw_pa and raw_pa != '—' else def_sup
        name = str(s.get('suppliername') or '').strip()
        label = f'SUP: {p_code} — {name} (A/c {pa})' if name else f'SUP: {p_code} (A/c {pa})'
        push({
            'code': pa,
            'name': name,
            'label': label,
            'kind': 'SUPPLIER',
            'party_type': 'SUPPLIER',
            'party_code': p_code,
            'account_type': '',
        })

    def_recv = str((DEFAULT_PARTY_ACCOUNTS or {}).get('customer_receivable') or '1200').strip()
    tbl = _detect_table(['CUSTOMER', 'CUSTOMERS', 'customer', 'customers'])
    if tbl:
        code_col = _detect_column(tbl, ['CUSTOMERCODE', 'CUST_CODE', 'CUSTOMER_CODE', 'CODE', 'code'])
        name_col = _detect_column(tbl, ['CUSTOMERNAME', 'CUST_NAME', 'CUSTOMER_NAME', 'NAME', 'name'])
        recv_col = _detect_column(
            tbl,
            ['RECEIVABLEACCOUNT', 'receivableaccount', 'RECEIVABLE_AC', 'receivable_acct'],
        )
        if code_col and name_col:
            params: Dict[str, Any] = {'lim': per}
            where_parts = [f'c.{code_col} IS NOT NULL']
            if qtxt:
                params['sw'] = f'%{qtxt}%'
                where_parts.append(
                    f'(TO_CHAR(c.{code_col}) LIKE :sw OR UPPER(c.{name_col}) LIKE UPPER(:sw))'
                )
            recv_expr = f'TRIM(TO_CHAR(c.{recv_col}))' if recv_col else 'NULL'
            sql = f"""
                SELECT * FROM (
                    SELECT TO_CHAR(c.{code_col}) AS customercode, c.{name_col} AS customername,
                           {recv_expr} AS receivableaccount
                    FROM {tbl} c
                    WHERE {' AND '.join(where_parts)}
                    ORDER BY c.{code_col}
                )
                WHERE ROWNUM <= :lim
            """
            try:
                for r in _safe_rows(sql, params) or []:
                    if len(out) >= cap:
                        break
                    c_code = str(r.get('customercode') or '').strip()
                    if not c_code:
                        continue
                    ra = str(r.get('receivableaccount') or def_recv).strip() or def_recv
                    name = str(r.get('customername') or '').strip()
                    label = f'CUST: {c_code} — {name} (A/c {ra})' if name else f'CUST: {c_code} (A/c {ra})'
                    push({
                        'code': ra,
                        'name': name,
                        'label': label,
                        'kind': 'CUSTOMER',
                        'party_type': 'CUSTOMER',
                        'party_code': c_code,
                        'account_type': '',
                    })
            except Exception:
                pass

    return out


def _search_cost_center(q: str = '', limit: int = 8) -> List[Dict[str, Any]]:
    return search_gl_dimension('COST_CENTER', q, limit)


def _search_department(q: str = '', limit: int = 8) -> List[Dict[str, Any]]:
    return search_gl_dimension('DEPARTMENT', q, limit)


def _search_project(q: str = '', limit: int = 8) -> List[Dict[str, Any]]:
    return search_gl_dimension('PROJECT', q, limit)


def _cpv_coa_active(acc: Dict[str, Any]) -> bool:
    return str(acc.get('status') or 'ACTIVE').upper() == 'ACTIVE'


def _cpv_filter_coa(
    q: str,
    limit: int,
    predicate: Callable[[Dict[str, Any]], bool],
) -> List[Dict[str, Any]]:
    cap = min(max(int(limit or 8), 1), 30)
    qtxt = (q or '').strip().lower()
    out: List[Dict[str, Any]] = []
    for acc in get_all_chart_of_accounts() or []:
        if not _cpv_coa_active(acc):
            continue
        code = str(acc.get('code') or '').strip()
        if not code or not predicate(acc):
            continue
        name = str(acc.get('name') or '').strip()
        acc_type = str(acc.get('type') or '').strip().upper()
        if qtxt:
            hay = f'{code} {name} {acc_type}'.lower()
            if qtxt not in hay and not all(w in hay for w in qtxt.split()):
                continue
        label = f'{code} — {name}' if name else code
        out.append({'code': code, 'name': name, 'label': label, 'account_type': acc_type})
        if len(out) >= cap:
            break
    return out


def search_cpv_petty_accounts(q: str = '', limit: int = 8) -> List[Dict[str, Any]]:
    """Cash Payment Voucher: petty cash (postable asset/cash/bank)."""

    def ok(acc: Dict[str, Any]) -> bool:
        if not acc.get('is_postable'):
            return False
        acc_type = str(acc.get('type') or '').upper()
        txt = f"{acc.get('code') or ''} {acc.get('name') or ''}".upper()
        return acc_type in ('ASSET', 'CASH', 'BANK') or 'CASH' in txt

    return _cpv_filter_coa(q, limit, ok)


_PAYABLE_HINTS = ('PAYABLE', 'CREDITOR', 'SUPPLIER', ' A/P', 'ACCRUED', 'VAT PAYABLE', 'EMPLOYEE PAYABLE')
_RECEIVABLE_HINTS = ('RECEIVABLE', 'DEBTOR', 'DEBTORS', 'SUNDRY DEBTOR', ' A/R', 'TRADE RECEIV')


def _coa_active_postable(acc: Dict[str, Any]) -> bool:
    return str(acc.get('status') or 'ACTIVE').upper() == 'ACTIVE' and bool(acc.get('is_postable'))


def _coa_text(acc: Dict[str, Any]) -> str:
    return f"{acc.get('code') or ''} {acc.get('name') or ''} {acc.get('parent_name') or ''}".upper()


def chart_accounts_by_code() -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for acc in get_all_chart_of_accounts() or []:
        code = str(acc.get('code') or '').strip()
        if code:
            out[code] = acc
    return out


def get_chart_account(code: str) -> Optional[Dict[str, Any]]:
    cc = str(code or '').strip()
    if not cc:
        return None
    return chart_accounts_by_code().get(cc)


_CASH_BANK_FALSE_POSITIVES = (
    'BANK CHARGE', 'BANK CHARGES', 'BANK FEE', 'BANK FEES',
    'BANK INTEREST', 'BANK COMMISSION', 'FINANCE CHARGE',
    'INTEREST ON BANK', 'OD INTEREST',
)


def is_cash_bank_account(acc: Optional[Dict[str, Any]]) -> bool:
    """True for postable Cash / Bank asset ledgers only (not bank charges, loans, etc.)."""
    if not acc or not _coa_active_postable(acc):
        return False
    acc_type = str(acc.get('type') or '').upper()
    txt = _coa_text(acc)
    if any(x in txt for x in _CASH_BANK_FALSE_POSITIVES):
        return False
    if acc_type in ('CASH', 'BANK'):
        return True
    # Cash/bank fund accounts are assets — exclude expense/income/liability lookalikes
    if acc_type and acc_type != 'ASSET':
        return False
    parent_code = str(acc.get('parent_code') or '').strip()
    if parent_code == '1110':
        return True
    parent_txt = str(acc.get('parent_name') or '').upper()
    if any(k in parent_txt for k in ('CASH', 'BANK')):
        return True
    if any(k in txt for k in ('CASH', 'BANK', 'PETTY')):
        return True
    # Card / cash clearing only (not generic "clearing" accounts)
    if 'CLEARING' in txt and any(k in txt for k in ('CASH', 'BANK', 'CARD')):
        return True
    return False


def _is_receivable_asset(acc: Dict[str, Any]) -> bool:
    txt = _coa_text(acc)
    if any(h in txt for h in _RECEIVABLE_HINTS):
        return True
    code = str(acc.get('code') or '').strip()
    return code.startswith('12') and len(code) >= 4


def _is_payable_liability(acc: Dict[str, Any]) -> bool:
    txt = _coa_text(acc)
    if any(h in txt for h in _PAYABLE_HINTS):
        return True
    code = str(acc.get('code') or '').strip()
    return code.startswith(('21', '22', '25')) and len(code) >= 4


def is_receipt_line_gl_account(acc: Optional[Dict[str, Any]]) -> bool:
    """Receipt credit side: customer receivable, income, loan, capital — not cash/bank or payables."""
    if not acc or not _coa_active_postable(acc) or is_cash_bank_account(acc):
        return False
    acc_type = str(acc.get('type') or '').upper()
    if acc_type in ('REVENUE', 'EQUITY'):
        return True
    if acc_type == 'EXPENSE':
        return False
    if acc_type == 'LIABILITY':
        return not _is_payable_liability(acc)
    if acc_type == 'ASSET':
        return _is_receivable_asset(acc)
    return False


def is_payment_line_gl_account(acc: Optional[Dict[str, Any]]) -> bool:
    """Payment debit side: supplier payable, expense, loan, asset — not cash/bank, income, or receivables."""
    if not acc or not _coa_active_postable(acc) or is_cash_bank_account(acc):
        return False
    acc_type = str(acc.get('type') or '').upper()
    if acc_type in ('REVENUE', 'EQUITY'):
        return False
    if acc_type == 'EXPENSE':
        return True
    if acc_type == 'LIABILITY':
        return True
    if acc_type == 'ASSET':
        return not _is_receivable_asset(acc)
    return False


def validate_tally_voucher_account(code: str, role: str, by_code: Optional[Dict[str, Dict[str, Any]]] = None) -> Optional[str]:
    """Return an error message when account code is invalid for role, else None."""
    cc = str(code or '').strip()
    if not cc:
        return 'Account is required.'
    lookup = by_code if by_code is not None else chart_accounts_by_code()
    acc = lookup.get(cc)
    if not acc:
        return f'Account {cc} is not in Chart of Accounts.'
    role_u = str(role or '').strip().lower()
    if role_u in ('cash_bank', 'cash_bank_strict'):
        if not is_cash_bank_account(acc):
            return f'Account {cc} is not a Cash or Bank account.'
        return None
    if role_u == 'receipt_line':
        if not is_receipt_line_gl_account(acc):
            return (
                f'Account {cc} is not allowed on Receipt voucher '
                '(use Customer receivable, Income, Loan, Capital, or other Receivable).'
            )
        return None
    if role_u == 'payment_line':
        if not is_payment_line_gl_account(acc):
            return (
                f'Account {cc} is not allowed on Payment voucher '
                '(use Supplier payable, Expense, Loan, Asset, or other Payable).'
            )
        return None
    return f'Unknown account validation role: {role_u}.'


def search_cash_bank_strict_accounts(q: str = '', limit: int = 8) -> List[Dict[str, Any]]:
    """Postable Cash / Bank accounts only (Receipt/Payment/Contra header and Contra lines)."""
    return _cpv_filter_coa(q, limit, is_cash_bank_account)


def search_receipt_line_accounts(q: str = '', limit: int = 8) -> List[Dict[str, Any]]:
    """Receipt voucher credit lines: customers (receivable) + allowed GL accounts."""
    cap = min(max(int(limit or 8), 1), 30)
    qtxt = (q or '').strip()
    out: List[Dict[str, Any]] = []
    seen = set()

    def push(row: Dict[str, Any]) -> None:
        if len(out) >= cap:
            return
        code = str(row.get('code') or '').strip()
        if not code or code in seen:
            return
        seen.add(code)
        out.append(row)

    per = max(3, cap // 2 + 1)
    def_recv = str((DEFAULT_PARTY_ACCOUNTS or {}).get('customer_receivable') or '1200').strip()
    tbl = _detect_table(['CUSTOMER', 'CUSTOMERS', 'customer', 'customers'])
    if tbl:
        code_col = _detect_column(tbl, ['CUSTOMERCODE', 'CUST_CODE', 'CUSTOMER_CODE', 'CODE', 'code'])
        name_col = _detect_column(tbl, ['CUSTOMERNAME', 'CUST_NAME', 'CUSTOMER_NAME', 'NAME', 'name'])
        recv_col = _detect_column(
            tbl,
            ['RECEIVABLEACCOUNT', 'receivableaccount', 'RECEIVABLE_AC', 'receivable_acct'],
        )
        if code_col and name_col:
            params: Dict[str, Any] = {'lim': per}
            where_parts = [f'c.{code_col} IS NOT NULL']
            if qtxt:
                params['sw'] = f'%{qtxt}%'
                where_parts.append(
                    f'(TO_CHAR(c.{code_col}) LIKE :sw OR UPPER(c.{name_col}) LIKE UPPER(:sw))'
                )
            recv_expr = f'TRIM(TO_CHAR(c.{recv_col}))' if recv_col else 'NULL'
            sql = f"""
                SELECT * FROM (
                    SELECT TO_CHAR(c.{code_col}) AS customercode, c.{name_col} AS customername,
                           {recv_expr} AS receivableaccount
                    FROM {tbl} c
                    WHERE {' AND '.join(where_parts)}
                    ORDER BY c.{code_col}
                )
                WHERE ROWNUM <= :lim
            """
            try:
                for r in _safe_rows(sql, params) or []:
                    if len(out) >= cap:
                        break
                    c_code = str(r.get('customercode') or '').strip()
                    if not c_code:
                        continue
                    ra = str(r.get('receivableaccount') or def_recv).strip() or def_recv
                    acc = get_chart_account(ra)
                    if acc and not is_receipt_line_gl_account(acc):
                        continue
                    name = str(r.get('customername') or '').strip()
                    label = f'CUST: {c_code} — {name} (A/c {ra})' if name else f'CUST: {c_code} (A/c {ra})'
                    push({
                        'code': ra,
                        'name': name,
                        'label': label,
                        'kind': 'CUSTOMER',
                        'party_type': 'CUSTOMER',
                        'party_code': c_code,
                        'account_type': str((acc or {}).get('type') or ''),
                    })
            except Exception:
                pass

    for acc in get_all_chart_of_accounts() or []:
        if len(out) >= cap:
            break
        if not is_receipt_line_gl_account(acc):
            continue
        code = str(acc.get('code') or '').strip()
        if not code:
            continue
        name = str(acc.get('name') or '').strip()
        acc_type = str(acc.get('type') or '').strip().upper()
        if qtxt:
            hay = f'{code} {name} {acc_type}'.lower()
            if qtxt.lower() not in hay and not all(w in hay for w in qtxt.lower().split()):
                continue
        label = f'{code} — {name} ({acc_type})' if name else f'{code} ({acc_type})'
        push({
            'code': code,
            'name': name,
            'label': label,
            'kind': 'GL',
            'party_type': '',
            'party_code': '',
            'account_type': acc_type,
        })
    return out


def search_payment_line_accounts(q: str = '', limit: int = 8) -> List[Dict[str, Any]]:
    """Payment voucher debit lines: suppliers (payable) + allowed GL accounts."""
    cap = min(max(int(limit or 8), 1), 30)
    qtxt = (q or '').strip()
    out: List[Dict[str, Any]] = []
    seen = set()

    def push(row: Dict[str, Any]) -> None:
        if len(out) >= cap:
            return
        code = str(row.get('code') or '').strip()
        if not code or code in seen:
            return
        seen.add(code)
        out.append(row)

    per = max(3, cap // 2 + 1)
    def_sup = str((DEFAULT_PARTY_ACCOUNTS or {}).get('supplier_payable') or '2110').strip()
    for s in get_supplier_list(search=qtxt or None, limit=per, row_cap=per) or []:
        if len(out) >= cap:
            break
        p_code = str(s.get('suppliercode') or '').strip()
        if not p_code:
            continue
        raw_pa = str(s.get('payableaccount') or '').strip()
        pa = raw_pa if raw_pa and raw_pa != '—' else def_sup
        acc = get_chart_account(pa)
        if acc and not is_payment_line_gl_account(acc):
            continue
        name = str(s.get('suppliername') or '').strip()
        label = f'SUP: {p_code} — {name} (A/c {pa})' if name else f'SUP: {p_code} (A/c {pa})'
        push({
            'code': pa,
            'name': name,
            'label': label,
            'kind': 'SUPPLIER',
            'party_type': 'SUPPLIER',
            'party_code': p_code,
            'account_type': str((acc or {}).get('type') or ''),
        })

    for acc in get_all_chart_of_accounts() or []:
        if len(out) >= cap:
            break
        if not is_payment_line_gl_account(acc):
            continue
        code = str(acc.get('code') or '').strip()
        if not code:
            continue
        name = str(acc.get('name') or '').strip()
        acc_type = str(acc.get('type') or '').strip().upper()
        if qtxt:
            hay = f'{code} {name} {acc_type}'.lower()
            if qtxt.lower() not in hay and not all(w in hay for w in qtxt.lower().split()):
                continue
        label = f'{code} — {name} ({acc_type})' if name else f'{code} ({acc_type})'
        push({
            'code': code,
            'name': name,
            'label': label,
            'kind': 'GL',
            'party_type': '',
            'party_code': '',
            'account_type': acc_type,
        })
    return out


def search_cpv_expense_parent(q: str = '', limit: int = 8) -> List[Dict[str, Any]]:
    """Cash Payment Voucher: expense parent (non-postable EXPENSE)."""

    def ok(acc: Dict[str, Any]) -> bool:
        return str(acc.get('type') or '').upper() == 'EXPENSE' and not acc.get('is_postable')

    return _cpv_filter_coa(q, limit, ok)


def search_cpv_expense_line(
    q: str = '', limit: int = 8, parent_code: str = ''
) -> List[Dict[str, Any]]:
    """Cash Payment Voucher: postable child accounts under expense parent."""
    parent = str(parent_code or '').strip()
    if not parent:
        return []

    def ok(acc: Dict[str, Any]) -> bool:
        return bool(acc.get('is_postable')) and str(acc.get('parent_code') or '').strip() == parent

    return _cpv_filter_coa(q, limit, ok)


LOOKUP_HANDLERS: Dict[str, LookupFn] = {
    'customer': search_customers,
    'customers': search_customers,
    'category': search_categories,
    'categories': search_categories,
    'supplier': search_suppliers,
    'suppliers': search_suppliers,
    'item': search_items,
    'items': search_items,
    'cost_center': _search_cost_center,
    'costcenter': _search_cost_center,
    'department': _search_department,
    'dept': _search_department,
    'project': _search_project,
    'gl_account': search_journal_accounts,
    'gl_accounts': search_journal_accounts,
    'journal_account': search_journal_accounts,
    'account': search_journal_accounts,
    'accounts': search_gl_accounts,
    'cpv_petty': search_cpv_petty_accounts,
    'cpv_petty_cash': search_cpv_petty_accounts,
    'cash_bank_strict': search_cash_bank_strict_accounts,
    'cash_bank': search_cash_bank_strict_accounts,
    'receipt_line': search_receipt_line_accounts,
    'payment_line': search_payment_line_accounts,
    'cpv_expense_parent': search_cpv_expense_parent,
}

LOOKUP_KINDS = frozenset(LOOKUP_HANDLERS.keys()) | frozenset({'cpv_expense_line'})


def search_lookup(
    kind: str,
    q: str = '',
    limit: int = 8,
    parent_code: str = '',
) -> List[Dict[str, Any]]:
    k = (kind or '').strip().lower()
    if k == 'cpv_expense_line':
        return search_cpv_expense_line(q, limit=limit, parent_code=parent_code)
    fn = LOOKUP_HANDLERS.get(k)
    if not fn:
        return []
    return fn(q, limit=limit)


def resolve_customer_label(customer_code: str) -> str:
    cc = normalize_customer_code(customer_code)
    if not cc:
        return ''
    for row in search_customers(cc, limit=15):
        if str(row.get('code') or '').strip() == cc:
            return str(row.get('label') or cc)
    return cc


def resolve_category_label(category_code: str) -> str:
    cc = (category_code or '').strip()
    if not cc:
        return ''
    for row in search_categories(cc, limit=15):
        if str(row.get('code') or '').strip() == cc:
            return str(row.get('label') or cc)
    return cc


def resolve_item_label(item_code: str) -> str:
    cc = (item_code or '').strip()
    if not cc:
        return ''
    for row in search_items(cc, limit=15):
        if str(row.get('code') or '').strip() == cc:
            return str(row.get('label') or cc)
    return cc


def resolve_lookup_label(kind: str, code: str) -> str:
    k = (kind or '').strip().lower()
    if k in ('customer', 'customers'):
        return resolve_customer_label(code)
    if k in ('category', 'categories'):
        return resolve_category_label(code)
    if k in ('item', 'items'):
        return resolve_item_label(code)
    if k in ('supplier', 'suppliers'):
        cc = (code or '').strip()
        if not cc:
            return ''
        for row in search_suppliers(cc, limit=15):
            if str(row.get('code') or '').strip() == cc:
                return str(row.get('label') or cc)
        return cc
    if k in ('cost_center', 'costcenter'):
        for row in search_gl_dimension('COST_CENTER', code, limit=15):
            if str(row.get('code') or '').strip() == (code or '').strip():
                return str(row.get('label') or code)
        return (code or '').strip()
    if k in ('department', 'dept'):
        for row in search_gl_dimension('DEPARTMENT', code, limit=15):
            if str(row.get('code') or '').strip() == (code or '').strip():
                return str(row.get('label') or code)
        return (code or '').strip()
    if k in ('project',):
        for row in search_gl_dimension('PROJECT', code, limit=15):
            if str(row.get('code') or '').strip() == (code or '').strip():
                return str(row.get('label') or code)
        return (code or '').strip()
    if k in ('gl_account', 'gl_accounts', 'journal_account', 'account'):
        cc = (code or '').strip()
        if not cc:
            return ''
        for row in search_journal_accounts(cc, limit=20):
            if str(row.get('code') or '').strip() == cc:
                return str(row.get('label') or cc)
        return cc
    if k in ('cpv_petty', 'cpv_petty_cash'):
        for row in search_cpv_petty_accounts(code, limit=15):
            if str(row.get('code') or '').strip() == (code or '').strip():
                return str(row.get('label') or code)
        return (code or '').strip()
    if k in ('cash_bank_strict', 'cash_bank'):
        for row in search_cash_bank_strict_accounts(code, limit=15):
            if str(row.get('code') or '').strip() == (code or '').strip():
                return str(row.get('label') or code)
        return (code or '').strip()
    if k == 'receipt_line':
        for row in search_receipt_line_accounts(code, limit=20):
            if str(row.get('code') or '').strip() == (code or '').strip():
                return str(row.get('label') or code)
        return (code or '').strip()
    if k == 'payment_line':
        for row in search_payment_line_accounts(code, limit=20):
            if str(row.get('code') or '').strip() == (code or '').strip():
                return str(row.get('label') or code)
        return (code or '').strip()
    if k == 'cpv_expense_parent':
        for row in search_cpv_expense_parent(code, limit=15):
            if str(row.get('code') or '').strip() == (code or '').strip():
                return str(row.get('label') or code)
        return (code or '').strip()
    if k == 'cpv_expense_line':
        cc = (code or '').strip()
        if not cc:
            return ''
        for row in search_cpv_expense_line(cc, limit=15, parent_code=''):
            if str(row.get('code') or '').strip() == cc:
                return str(row.get('label') or cc)
        return cc
    return (code or '').strip()
