"""Customer blueprint - Master data for CUSTOMER table."""
from pathlib import Path
from nexa_http import Blueprint, redirect, render_template, request, session, flash, url_for, Response, jsonify
from typing import List, Dict, Any, Optional
from datetime import datetime
import csv
import io
import os
import time
from save_nonce import GLOBAL_SAVE_NONCE_SESSION_KEY, issue_save_nonce, verify_consume_save_nonce
from master_name_duplicate import find_master_name_duplicate, master_name_duplicate_message
from master_activity_log import append_master_activity
from db import _get_connection, _fetch_rows, _detect_column, _table_exists, _get_table_columns, _TABLE_COLUMNS_CACHE, get_locations_list, get_location_info_by_dbkey, get_all_chart_of_accounts, ensure_default_party_accounts, DEFAULT_PARTY_ACCOUNTS, get_assignable_login_users
from addons.customer import missing_recovery as mcr
_ADDON_ROOT = Path(__file__).resolve().parents[1]
bp = Blueprint('customer', __name__, template_folder=str(_ADDON_ROOT / 'views' / 'templates'))
CUSTOMER_TABLE = 'CUSTOMER'
LOCATIONS_TABLE = 'LOCATIONMASTER'
_CUSTOMER_TIMING_ENABLED = (os.getenv('CUSTOMER_TIMING_LOG', '1').strip().lower() not in {'0', 'false', 'no'})
_CUSTOMER_CACHE_TTL_SECONDS = 300.0
_CUSTOMER_ROUTE_CACHE: Dict[Any, Any] = {}

def _customer_timing_log(label: str, start: float, **fields: Any) -> None:
    if not _CUSTOMER_TIMING_ENABLED:
        return
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    extras = ' '.join(f'{k}={v}' for k, v in fields.items())
    print(f'[TIMING customer] {label} elapsed_ms={elapsed_ms:.1f}' + (f' {extras}' if extras else ''))

def _customer_cache_key(name: str, *parts: Any) -> Any:
    tenant = ''
    try:
        tenant = str(session.get('tenant_id') or '').strip()
    except Exception:
        tenant = ''
    return (tenant, name) + tuple(parts)

def _customer_cache_get(key: Any) -> Any:
    cached = _CUSTOMER_ROUTE_CACHE.get(key)
    if not cached:
        return None
    ts, value = cached
    if (time.time() - ts) > _CUSTOMER_CACHE_TTL_SECONDS:
        _CUSTOMER_ROUTE_CACHE.pop(key, None)
        return None
    return value

def _customer_cache_set(key: Any, value: Any) -> Any:
    _CUSTOMER_ROUTE_CACHE[key] = (time.time(), value)
    if len(_CUSTOMER_ROUTE_CACHE) > 100:
        for k in list(_CUSTOMER_ROUTE_CACHE.keys())[:50]:
            _CUSTOMER_ROUTE_CACHE.pop(k, None)
    return value

def _sess_user_for_log() -> str:
    return str(session.get('user') or '').strip()

def _resolve_location_code() -> int:
    loc = session.get('location_code')
    try:
        if loc is not None and str(loc).isdigit():
            return int(loc)
    except Exception:
        pass
    try:
        info = get_location_info_by_dbkey(None)
        if info and info.get('locationcode') is not None:
            return int(info['locationcode'])
    except Exception:
        pass
    return 1

def _customer_table() -> Optional[str]:
    if _table_exists(CUSTOMER_TABLE):
        return CUSTOMER_TABLE
    if _table_exists('customer'):
        return 'customer'
    return None

def _norm_code(v: Any) -> str:
    s = str(v or '').strip()
    if not s:
        return ''
    try:
        f = float(s)
        if f.is_integer():
            return str(int(f))
    except Exception:
        pass
    return s

def _ensure_default_customer_accounts_in_list(chart_accounts: List[Dict[str, Any]], defaults: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = list(chart_accounts or [])
    have = {_norm_code(r.get('code')) for r in rows}
    inject = [('customer_receivable', 'Accounts Receivable', 'ASSET'), ('customer_sales', 'Sales Revenue', 'REVENUE'), ('customer_vat_output', 'VAT Payable', 'LIABILITY'), ('customer_advance', 'Customer Advances', 'LIABILITY')]
    for key, name, typ in inject:
        code = _norm_code((defaults or {}).get(key))
        if not code or code in have:
            continue
        rows.append({'code': code, 'name': name, 'type': typ})
        have.add(code)
    return rows

def _safe_int(value: Any, default: Any=0) -> Any:
    if value is None or str(value).strip() == '':
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default

def _ensure_customer_account_columns() -> None:
    tbl = _customer_table()
    if not tbl:
        return
    new_cols = [
        ('RECEIVABLEACCOUNT', 'NUMBER(10)'),
        ('SALESACCOUNT', 'NUMBER(10)'),
        ('VATOUTPUTACCOUNT', 'NUMBER(10)'),
        ('ADVANCEACCOUNT', 'NUMBER(10)'),
        ('EMAIL', 'VARCHAR2(150)'),
        ('QATARID', 'VARCHAR2(50)'),
        ('WHATSAPP', 'VARCHAR2(20)'),
        ('EMPLOYEECODE', 'NUMBER(10)'),
        ('REASON', 'VARCHAR2(500)'),
        ('OTHERREASON', 'VARCHAR2(500)'),
        ('CLOSEDREASON', 'VARCHAR2(500)'),
        ('COUNTERSALE', 'VARCHAR2(1)'),
        ('CUSTOMER_BILLING_TYPE', 'VARCHAR2(10)'),
        ('SOURCE_CHANNEL', 'VARCHAR2(40)'),
    ]
    want = {name for name, _ in new_cols}
    cols_cached = _get_table_columns(tbl)
    if want <= set(cols_cached):
        return
    _TABLE_COLUMNS_CACHE.pop(tbl.upper(), None)
    cols = set(_get_table_columns(tbl))
    with _get_connection() as conn:
        with conn.cursor() as cur:
            for col_name, col_type in new_cols:
                if col_name not in cols:
                    try:
                        cur.execute(f'ALTER TABLE {tbl} ADD {col_name} {col_type}')
                    except Exception:
                        pass
        conn.commit()
    _TABLE_COLUMNS_CACHE.pop(tbl.upper(), None)
    cols_after = set(_get_table_columns(tbl))
    inv_col = _detect_column(tbl, ['INVOICECODE', 'invoicecode'])
    if 'CUSTOMER_BILLING_TYPE' in cols_after and inv_col:
        try:
            with _get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"""
                        UPDATE {tbl}
                        SET CUSTOMER_BILLING_TYPE = CASE
                            WHEN {inv_col} = 2 THEN 'CREDIT'
                            ELSE 'CASH'
                        END
                        WHERE CUSTOMER_BILLING_TYPE IS NULL
                           OR TRIM(CUSTOMER_BILLING_TYPE) IS NULL
                        """
                    )
                conn.commit()
        except Exception:
            pass

def _customer_list_filter_bundle(location_code: Optional[int]=None, search: Optional[str]=None, customer_status: Optional[str]=None, invoice_code: Optional[str]=None, date_from: Optional[str]=None, date_to: Optional[str]=None, category_code: Optional[str]=None, salesman_code: Optional[str]=None) -> Optional[Dict[str, Any]]:
    """Shared FROM / JOINs / WHERE / bind params for customer list rows and KPI aggregates."""
    tbl = _customer_table()
    if not tbl:
        return None
    loc_col = _detect_column(tbl, ['LOCATIONCODE', 'locationcode'])
    code_col = _detect_column(tbl, ['CUSTOMERCODE', 'customercode'])
    name_col = _detect_column(tbl, ['CUSTOMERNAME', 'customername'])
    salesman_col = _detect_column(tbl, ['SALESMANCODE', 'salesmancode'])
    billing_col = _detect_column(tbl, ['CUSTOMER_BILLING_TYPE', 'customer_billing_type', 'BILLING_TYPE'])
    invoicecode_col = _detect_column(tbl, ['INVOICECODE', 'invoicecode'])
    category_col = _detect_column(tbl, ['CUSTOMERCATEGORY', 'customercategory'])
    flag_col = _detect_column(tbl, ['FLAG', 'flag'])
    closed_col = _detect_column(tbl, ['CLOSED', 'closed'])
    if not code_col or not name_col:
        return None
    created_col = _detect_column(tbl, ['CREATEDDATE', 'createddate', 'CREATED_DATE', 'created_date'])
    sm_tbl = _salesman_table()
    cat_tbl = _category_table()
    from_clause = tbl + ' c'
    joins: List[str] = []
    if sm_tbl and salesman_col:
        sm_code = _detect_column(sm_tbl, ['SALESMANCODE', 'salesmancode', 'CODE', 'code'])
        if sm_code:
            joins.append(f' LEFT JOIN {sm_tbl} sm ON sm.{sm_code} = c.{salesman_col}')
    if cat_tbl and category_col:
        cat_code_col = _detect_column(cat_tbl, ['CATEGORYCODE', 'categorycode', 'CODE', 'code'])
        cat_loc_col = _detect_column(cat_tbl, ['LOCATIONCODE', 'locationcode', 'LOCATION_CODE', 'location_code'])
        if cat_code_col:
            join_on = f'cat.{cat_code_col} = c.{category_col}'
            if cat_loc_col and loc_col:
                join_on += f' AND cat.{cat_loc_col} = c.{loc_col}'
            joins.append(f' LEFT JOIN {cat_tbl} cat ON {join_on}')
    join_clause = ''.join(joins)
    where_parts = []
    params: Dict[str, Any] = {}
    if location_code is not None and loc_col:
        where_parts.append(f'c.{loc_col} = :location_code')
        params['location_code'] = location_code
    if search and search.strip():
        words = [w for w in search.strip().split() if w]
        if len(words) == 1:
            params['search_name'] = f'%{words[0]}%'
            params['search_code'] = f'%{words[0]}%'
            where_parts.append(f'(UPPER(c.{name_col}) LIKE UPPER(:search_name) OR TO_CHAR(c.{code_col}) LIKE :search_code)')
        else:
            word_clauses = []
            for i, w in enumerate(words):
                pname = f'sw_{i}'
                params[pname] = f'%{w}%'
                word_clauses.append(f'UPPER(c.{name_col}) LIKE UPPER(:{pname})')
            params['search_code'] = f'%{search.strip()}%'
            where_parts.append(f"(({' AND '.join(word_clauses)}) OR TO_CHAR(c.{code_col}) LIKE :search_code)")
    if customer_status and customer_status.strip() and flag_col:
        params['customer_status'] = customer_status.strip()
        where_parts.append(f'UPPER(TRIM(c.{flag_col})) = UPPER(TRIM(:customer_status))')
    ic_raw = str(invoice_code or '').strip().upper()
    if ic_raw and billing_col:
        if ic_raw in ('1', 'CASH'):
            params['billing_type'] = 'CASH'
        elif ic_raw in ('2', 'CREDIT'):
            params['billing_type'] = 'CREDIT'
        if params.get('billing_type'):
            where_parts.append(f'UPPER(TRIM(c.{billing_col})) = :billing_type')
    elif ic_raw and invoicecode_col:
        try:
            params['invoice_code'] = int(ic_raw)
            where_parts.append(f'c.{invoicecode_col} = :invoice_code')
        except (TypeError, ValueError):
            pass
    if category_code and str(category_code).strip() and category_col:
        params['filter_category'] = int(category_code)
        where_parts.append(f'c.{category_col} = :filter_category')
    if salesman_code and str(salesman_code).strip() and salesman_col:
        params['filter_salesman'] = int(salesman_code)
        where_parts.append(f'c.{salesman_col} = :filter_salesman')
    if date_from and date_from.strip() and created_col:
        try:
            datetime.strptime(date_from.strip(), '%Y-%m-%d')
            params['date_from'] = date_from.strip()
            where_parts.append(f"TRUNC(c.{created_col}) >= TO_DATE(:date_from, 'YYYY-MM-DD')")
        except ValueError:
            pass
    if date_to and date_to.strip() and created_col:
        try:
            datetime.strptime(date_to.strip(), '%Y-%m-%d')
            params['date_to'] = date_to.strip()
            where_parts.append(f"TRUNC(c.{created_col}) <= TO_DATE(:date_to, 'YYYY-MM-DD')")
        except ValueError:
            pass
    where_sql = ' WHERE ' + ' AND '.join(where_parts) if where_parts else ''
    return {
        'tbl': tbl,
        'from_clause': from_clause,
        'join_clause': join_clause,
        'where_sql': where_sql,
        'params': params,
        'loc_col': loc_col,
        'code_col': code_col,
        'name_col': name_col,
        'salesman_col': salesman_col,
        'billing_col': billing_col,
        'invoicecode_col': invoicecode_col,
        'category_col': category_col,
        'flag_col': flag_col,
        'closed_col': closed_col,
        'created_col': created_col,
        'sm_tbl': sm_tbl,
        'cat_tbl': cat_tbl,
    }


def _get_customer_list(location_code: Optional[int]=None, search: Optional[str]=None, customer_status: Optional[str]=None, invoice_code: Optional[str]=None, date_from: Optional[str]=None, date_to: Optional[str]=None, category_code: Optional[str]=None, salesman_code: Optional[str]=None, limit: int=100, page: Optional[int]=None, items_per_page: Optional[int]=None) -> List[Dict[str, Any]]:
    bundle = _customer_list_filter_bundle(location_code, search=search, customer_status=customer_status, invoice_code=invoice_code, date_from=date_from, date_to=date_to, category_code=category_code, salesman_code=salesman_code)
    if not bundle:
        return []
    from_clause = bundle['from_clause']
    join_clause = bundle['join_clause']
    where_sql = bundle['where_sql']
    params = dict(bundle['params'])
    loc_col = bundle['loc_col']
    code_col = bundle['code_col']
    name_col = bundle['name_col']
    billing_col = bundle['billing_col']
    invoicecode_col = bundle['invoicecode_col']
    category_col = bundle['category_col']
    flag_col = bundle['flag_col']
    closed_col = bundle['closed_col']
    created_col = bundle['created_col']
    cat_tbl = bundle['cat_tbl']
    tbl = bundle['tbl']
    creditlimit_col = _detect_column(tbl, ['CREDITLIMIT', 'creditlimit'])
    recv_col = _detect_column(tbl, ['RECEIVABLEACCOUNT', 'receivableaccount'])
    if billing_col:
        billing_sql = f'c.{billing_col}'
    elif invoicecode_col:
        billing_sql = (
            f"CASE WHEN c.{invoicecode_col} = 2 THEN 'CREDIT' "
            f"WHEN c.{invoicecode_col} = 1 THEN 'CASH' ELSE 'CASH' END"
        )
    else:
        billing_sql = "'CASH'"
    select_parts = [
        f'c.{loc_col} AS locationcode',
        f'c.{code_col} AS customercode',
        f'c.{name_col} AS customername',
        f'c.SOURCE_CHANNEL AS source_channel' if _column_exists(tbl, 'SOURCE_CHANNEL') else 'NULL AS source_channel',
        f'{billing_sql} AS customer_billing_type',
        f'c.{category_col} AS customercategory' if category_col else 'NULL AS customercategory',
        f'c.{flag_col} AS customerflag' if flag_col else 'NULL AS customerflag',
        f'c.{closed_col} AS customerclosed' if closed_col else 'NULL AS customerclosed',
        f'c.{created_col} AS createddate' if created_col else 'NULL AS createddate',
        f'NVL(c.{creditlimit_col}, 0) AS creditlimit' if creditlimit_col else '0 AS creditlimit',
        f'c.{recv_col} AS receivableaccount' if recv_col else 'NULL AS receivableaccount',
    ]
    if cat_tbl and category_col:
        cat_code_col = _detect_column(cat_tbl, ['CATEGORYCODE', 'categorycode', 'CODE', 'code'])
        cat_name_col = _detect_column(cat_tbl, ['CATEGORYNAME', 'categoryname', 'NAME', 'name'])
        if cat_code_col and cat_name_col:
            select_parts.append(f'cat.{cat_name_col} AS customercategoryname')
        else:
            select_parts.append('NULL AS customercategoryname')
    else:
        select_parts.append('NULL AS customercategoryname')
    inner_query = f"\n        SELECT {', '.join(select_parts)}\n        FROM {from_clause}\n        {join_clause}\n        {where_sql}\n        ORDER BY c.{loc_col} DESC, c.{code_col} DESC\n    "
    if page is not None and items_per_page is not None:
        page_val = max(1, int(page or 1))
        per_page = max(1, min(int(items_per_page or limit or 50), 500))
        offset = (page_val - 1) * per_page
        params['max_row'] = offset + per_page
        params['min_row'] = offset
        query = f'\n            SELECT * FROM (\n                SELECT a.*, ROWNUM rnum FROM (\n                    {inner_query}\n                ) a WHERE ROWNUM <= :max_row\n            ) WHERE rnum > :min_row\n        '
    else:
        limit_val = max(1, min(int(limit), 1000))
        params['row_limit'] = limit_val
        query = f'\n            SELECT * FROM (\n                {inner_query}\n            ) WHERE ROWNUM <= :row_limit\n        '
    try:
        _, rows = _fetch_rows(query, params)
        return _apply_gl_outstanding_to_customer_list_rows(rows)
    except Exception as e:
        print(f'[ERROR _get_customer_list] {e}')
        return []


def _get_customer_list_kpis(location_code: Optional[int]=None, search: Optional[str]=None, customer_status: Optional[str]=None, invoice_code: Optional[str]=None, date_from: Optional[str]=None, date_to: Optional[str]=None, category_code: Optional[str]=None, salesman_code: Optional[str]=None) -> Dict[str, int]:
    """Aggregate counts for current filters (full DB match; no row limit)."""
    zero = {'total': 0, 'active': 0, 'locked': 0, 'cash': 0, 'credit': 0}
    bundle = _customer_list_filter_bundle(location_code, search=search, customer_status=customer_status, invoice_code=invoice_code, date_from=date_from, date_to=date_to, category_code=category_code, salesman_code=salesman_code)
    if not bundle:
        return zero
    from_clause = bundle['from_clause']
    join_clause = bundle['join_clause']
    where_sql = bundle['where_sql']
    params = dict(bundle['params'])
    flag_col = bundle['flag_col']
    billing_col = bundle['billing_col']
    invoicecode_col = bundle['invoicecode_col']
    agg = ['COUNT(*) AS total_cnt']
    if flag_col:
        agg.append(f"SUM(CASE WHEN UPPER(TRIM(c.{flag_col})) = 'Y' THEN 1 ELSE 0 END) AS active_cnt")
        agg.append(f"SUM(CASE WHEN UPPER(TRIM(c.{flag_col})) = 'N' THEN 1 ELSE 0 END) AS locked_cnt")
    else:
        agg.append('0 AS active_cnt')
        agg.append('0 AS locked_cnt')
    if billing_col:
        agg.append(f"SUM(CASE WHEN UPPER(TRIM(c.{billing_col})) = 'CASH' THEN 1 ELSE 0 END) AS cash_cnt")
        agg.append(f"SUM(CASE WHEN UPPER(TRIM(c.{billing_col})) = 'CREDIT' THEN 1 ELSE 0 END) AS credit_cnt")
    elif invoicecode_col:
        agg.append(f'SUM(CASE WHEN c.{invoicecode_col} = 1 THEN 1 ELSE 0 END) AS cash_cnt')
        agg.append(f'SUM(CASE WHEN c.{invoicecode_col} = 2 THEN 1 ELSE 0 END) AS credit_cnt')
    else:
        agg.append('0 AS cash_cnt')
        agg.append('0 AS credit_cnt')
    query = f"\n        SELECT {', '.join(agg)}\n        FROM {from_clause}\n        {join_clause}\n        {where_sql}\n    "
    try:
        _, rows = _fetch_rows(query, params)
        if not rows:
            return zero
        r = rows[0]

        def _i(key: str) -> int:
            v = r.get(key)
            if v is None:
                return 0
            try:
                return int(v)
            except (TypeError, ValueError):
                return 0
        return {'total': _i('total_cnt'), 'active': _i('active_cnt'), 'locked': _i('locked_cnt'), 'cash': _i('cash_cnt'), 'credit': _i('credit_cnt')}
    except Exception as e:
        print(f'[ERROR _get_customer_list_kpis] {e}')
        return zero


def _apply_gl_outstanding_to_customer_list_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Per-customer GL outstanding for list screens (not shared control-account balance)."""
    if not rows:
        return rows
    from db import (
        _customer_gl_receivable_context,
        _customer_list_gl_outstanding,
        _customer_open_documents_outstanding_totals,
    )

    gl_ctx = _customer_gl_receivable_context()
    doc_totals = _customer_open_documents_outstanding_totals() if gl_ctx else {}
    for row in rows:
        code = row.get('customercode')
        recv = row.get('receivableaccount')
        if gl_ctx and code not in (None, ''):
            row['gl_outstanding'] = _customer_list_gl_outstanding(
                code, recv, ctx=gl_ctx, doc_totals=doc_totals,
            )
        else:
            row['gl_outstanding'] = 0.0
    return rows


def _json_customer_row(row: Dict[str, Any]) -> Dict[str, Any]:
    created = row.get('createddate')
    if hasattr(created, 'strftime'):
        created_text = created.strftime('%d-%m-%Y')
    else:
        created_text = str(created or '').strip() or '-'
    return {
        'locationcode': row.get('locationcode'),
        'customercode': row.get('customercode'),
        'customername': row.get('customername') or '',
        'customer_billing_type': (row.get('customer_billing_type') or 'CASH').strip().upper(),
        'customerflag': row.get('customerflag') or '',
        'customerclosed': row.get('customerclosed') or '',
        'customercategory': row.get('customercategory'),
        'customercategoryname': row.get('customercategoryname') or '',
        'createddate': created_text,
        'creditlimit': float(row.get('creditlimit') or 0),
        'gl_outstanding': float(row.get('gl_outstanding') or 0),
    }


def _get_next_customer_code(location_code: int) -> int:
    tbl = _customer_table()
    if not tbl:
        return 1
    loc_col = _detect_column(tbl, ['LOCATIONCODE', 'locationcode'])
    code_col = _detect_column(tbl, ['CUSTOMERCODE', 'customercode'])
    if not loc_col or not code_col:
        return 1
    query = f'\n        SELECT NVL(MAX({code_col}), 0) + 1 AS nextcode\n        FROM {tbl}\n        WHERE {loc_col} = :location_code\n    '
    try:
        _, rows = _fetch_rows(query, {'location_code': location_code})
        if rows and rows[0].get('nextcode') is not None:
            return int(rows[0]['nextcode'])
    except Exception as e:
        print(f'[ERROR _get_next_customer_code] {e}')
    return 1

def _get_customer_by_code(location_code: int, customer_code: int) -> Optional[Dict[str, Any]]:
    tbl = _customer_table()
    if not tbl:
        return None
    loc_col = _detect_column(tbl, ['LOCATIONCODE', 'locationcode'])
    code_col = _detect_column(tbl, ['CUSTOMERCODE', 'customercode'])
    if not loc_col or not code_col:
        return None
    cols = _get_table_columns(tbl)
    select_parts = []
    for c in ['LOCATIONCODE', 'CUSTOMERCODE', 'CUSTOMERNAME', 'DESIGNATION', 'SEX', 'ADDRESS', 'NATIONALITY', 'TELEPHONE', 'FAX', 'MOBILE', 'CREDITLIMIT', 'CREDITTERMS', 'CURRENTCREDITAMOUNT', 'SALESMANCODE', 'CUSTOMER_BILLING_TYPE', 'FLAG', 'CLOSED', 'CUSTOMERCATEGORY', 'BYSALESMAN', 'ROUTENO', 'STREET', 'ZONE', 'POBOX', 'CRNO', 'RECEIVABLEACCOUNT', 'SALESACCOUNT', 'VATOUTPUTACCOUNT', 'ADVANCEACCOUNT', 'CREATEDDATE', 'EMAIL', 'QATARID', 'WHATSAPP', 'EMPLOYEECODE', 'REASON', 'OTHERREASON', 'CLOSEDREASON', 'COUNTERSALE', 'CCODE', 'POINTS']:
        if c in cols:
            select_parts.append(f'{c} AS {c.lower()}')
    if not select_parts:
        select_parts = [f'{loc_col} AS locationcode', f'{code_col} AS customercode', f"{_detect_column(tbl, ['CUSTOMERNAME', 'customername'])} AS customername"]
    query = f"\n        SELECT {', '.join(select_parts)}\n        FROM {tbl}\n        WHERE {loc_col} = :location_code AND {code_col} = :customer_code\n    "
    try:
        _, rows = _fetch_rows(query, {'location_code': location_code, 'customer_code': customer_code})
        if not rows:
            return None
        row = rows[0]
        from db import normalize_customer_billing_type
        row['customer_billing_type'] = normalize_customer_billing_type(
            row.get('customer_billing_type') or row.get('invoicecode')
        )
        return row
    except Exception as e:
        print(f'[ERROR _get_customer_by_code] {e}')
        return None

def _salesman_table() -> Optional[str]:
    for t in ['SALESMAN', 'salesman', 'SALESMEN', 'salesmen']:
        if _table_exists(t):
            return t
    return None

def _get_salesman_list(location_code: Optional[int]=None) -> List[Dict[str, Any]]:
    tbl = _salesman_table()
    if not tbl:
        return []
    code_col = _detect_column(tbl, ['SALESMANCODE', 'salesmancode', 'CODE', 'code'])
    name_col = _detect_column(tbl, ['SALESMANNAME', 'salesmanname', 'NAME', 'name'])
    loc_col = _detect_column(tbl, ['LOCATIONCODE', 'LOCATION_CODE', 'LOC_CODE', 'LOCCODE'])
    if not code_col:
        return []
    select_parts = [f'{code_col} AS code', f'{name_col} AS name' if name_col else 'NULL AS name']
    where = ''
    params: Dict[str, Any] = {}
    if location_code is not None and loc_col:
        where = f'WHERE {loc_col} = :location_code'
        params['location_code'] = location_code
    order = f'ORDER BY {(name_col if name_col else code_col)}'
    try:
        _, rows = _fetch_rows(f"SELECT {', '.join(select_parts)} FROM {tbl} {where} {order}", params)
        return rows
    except Exception as e:
        print(f'[ERROR _get_salesman_list] {e}')
        return []

def _get_salesman_name(salesman_code: Any) -> str:
    if salesman_code is None or str(salesman_code).strip() == '':
        return ''
    tbl = _salesman_table()
    if not tbl:
        return ''
    code_col = _detect_column(tbl, ['SALESMANCODE', 'salesmancode', 'CODE', 'code'])
    name_col = _detect_column(tbl, ['SALESMANNAME', 'salesmanname', 'NAME', 'name'])
    if not code_col or not name_col:
        return ''
    try:
        _, rows = _fetch_rows(f'SELECT {name_col} AS name FROM {tbl} WHERE {code_col} = :code', {'code': salesman_code})
        return (rows[0].get('name') or '').strip() if rows else ''
    except Exception:
        return ''

def _category_table() -> Optional[str]:
    for t in ['TBLCUSTOMERCATEGORY', 'tblcustomercategory', 'CUSTOMERCATEGORY', 'customercategory']:
        if _table_exists(t):
            return t
    return None

def _get_category_list(location_code: Optional[int]=None) -> List[Dict[str, Any]]:
    tbl = _category_table()
    if not tbl:
        return []
    code_col = _detect_column(tbl, ['CATEGORYCODE', 'categorycode', 'CODE', 'code'])
    name_col = _detect_column(tbl, ['CATEGORYNAME', 'categoryname', 'NAME', 'name'])
    loc_col = _detect_column(tbl, ['LOCATIONCODE', 'locationcode', 'LOCATION_CODE', 'location_code'])
    if not code_col:
        return []
    select_parts = [f'{code_col} AS code', f'{name_col} AS name' if name_col else 'NULL AS name']
    where = ''
    params: Dict[str, Any] = {}
    if location_code is not None and loc_col:
        where = f'WHERE {loc_col} = :location_code'
        params['location_code'] = location_code
    order = f'ORDER BY {(name_col if name_col else code_col)}'
    try:
        _, rows = _fetch_rows(f"SELECT {', '.join(select_parts)} FROM {tbl} {where} {order}", params)
        return rows
    except Exception as e:
        print(f'[ERROR _get_category_list] {e}')
        return []

def _get_category_name(category_code: Any) -> str:
    if category_code is None or str(category_code).strip() == '':
        return ''
    tbl = _category_table()
    if not tbl:
        return ''
    code_col = _detect_column(tbl, ['CATEGORYCODE', 'categorycode', 'CODE', 'code'])
    name_col = _detect_column(tbl, ['CATEGORYNAME', 'categoryname', 'NAME', 'name'])
    if not code_col or not name_col:
        return ''
    try:
        _, rows = _fetch_rows(f'SELECT {name_col} AS name FROM {tbl} WHERE {code_col} = :code', {'code': category_code})
        return (rows[0].get('name') or '').strip() if rows else ''
    except Exception:
        return ''

def _route_table() -> Optional[str]:
    for t in ['TBLROUTES', 'tblroutes', 'TBLROUTE', 'tblroute', 'ROUTES', 'routes']:
        if _table_exists(t):
            return t
    return None

def _get_route_list() -> List[Dict[str, Any]]:
    tbl = _route_table()
    if not tbl:
        return []
    code_col = _detect_column(tbl, ['ROUTENO', 'routeno', 'ROUTE_NO', 'route_no', 'CODE', 'code'])
    name_col = _detect_column(tbl, ['ROUTENAME', 'routename', 'ROUTE_NAME', 'route_name', 'NAME', 'name'])
    if not code_col:
        return []
    select_parts = [f'{code_col} AS code', f'{name_col} AS name' if name_col else 'NULL AS name']
    order = f'ORDER BY {(name_col if name_col else code_col)}'
    try:
        _, rows = _fetch_rows(f"SELECT {', '.join(select_parts)} FROM {tbl} {order}", {})
        return rows
    except Exception as e:
        print(f'[ERROR _get_route_list] {e}')
        return []

def _get_route_name(route_no: Any) -> str:
    if route_no is None or str(route_no).strip() == '':
        return ''
    tbl = _route_table()
    if not tbl:
        return ''
    code_col = _detect_column(tbl, ['ROUTENO', 'routeno', 'ROUTE_NO', 'route_no', 'CODE', 'code'])
    name_col = _detect_column(tbl, ['ROUTENAME', 'routename', 'ROUTE_NAME', 'route_name', 'NAME', 'name'])
    if not code_col or not name_col:
        return ''
    try:
        _, rows = _fetch_rows(f'SELECT {name_col} AS name FROM {tbl} WHERE {code_col} = :code', {'code': route_no})
        return (rows[0].get('name') or '').strip() if rows else ''
    except Exception:
        return ''

def _employee_table() -> Optional[str]:
    for t in ['EMPLOYEE', 'employee', 'EMPLOYEE1', 'employee1']:
        if _table_exists(t):
            return t
    return None

def _get_employee_list() -> List[Dict[str, Any]]:
    tbl = _employee_table()
    if not tbl:
        return []
    code_col = _detect_column(tbl, ['EMPLOYEECODE', 'employeecode', 'EMPCODE', 'empcode', 'CODE', 'code'])
    name_col = _detect_column(tbl, ['EMPLOYEENAME', 'employeename', 'EMPNAME', 'empname', 'NAME', 'name'])
    pending_col = _detect_column(tbl, ['PENDING', 'pending'])
    if not code_col:
        return []
    select_parts = [f'{code_col} AS code', f'{name_col} AS name' if name_col else 'NULL AS name']
    where = f"WHERE UPPER(TRIM({pending_col})) = 'Y'" if pending_col else ''
    order = f'ORDER BY {(name_col if name_col else code_col)}'
    try:
        _, rows = _fetch_rows(f"SELECT {', '.join(select_parts)} FROM {tbl} {where} {order}", {})
        return rows or []
    except Exception as e:
        print(f'[ERROR _get_employee_list] {e}')
        return []

def _get_employee_name(employee_code: Any) -> str:
    if employee_code is None or str(employee_code).strip() == '':
        return ''
    tbl = _employee_table()
    if not tbl:
        return ''
    code_col = _detect_column(tbl, ['EMPLOYEECODE', 'employeecode', 'EMPCODE', 'empcode', 'CODE', 'code'])
    name_col = _detect_column(tbl, ['EMPLOYEENAME', 'employeename', 'EMPNAME', 'empname', 'NAME', 'name'])
    if not code_col or not name_col:
        return ''
    try:
        _, rows = _fetch_rows(f'SELECT {name_col} AS name FROM {tbl} WHERE {code_col} = :code', {'code': employee_code})
        return (rows[0].get('name') or '').strip() if rows else ''
    except Exception:
        return ''

def _cached_salesman_list(location_code: Optional[int]=None) -> List[Dict[str, Any]]:
    key = _customer_cache_key('salesman_list', location_code)
    cached = _customer_cache_get(key)
    if cached is not None:
        return cached
    return _customer_cache_set(key, _get_salesman_list(location_code))

def _cached_category_list(location_code: Optional[int]=None) -> List[Dict[str, Any]]:
    key = _customer_cache_key('category_list', location_code)
    cached = _customer_cache_get(key)
    if cached is not None:
        return cached
    return _customer_cache_set(key, _get_category_list(location_code))

def _cached_route_list() -> List[Dict[str, Any]]:
    key = _customer_cache_key('route_list')
    cached = _customer_cache_get(key)
    if cached is not None:
        return cached
    return _customer_cache_set(key, _get_route_list())

def _cached_employee_list() -> List[Dict[str, Any]]:
    key = _customer_cache_key('employee_list')
    cached = _customer_cache_get(key)
    if cached is not None:
        return cached
    return _customer_cache_set(key, _get_employee_list())

def _cached_locations_list() -> List[Dict[str, Any]]:
    key = _customer_cache_key('locations_list')
    cached = _customer_cache_get(key)
    if cached is not None:
        return cached
    return _customer_cache_set(key, get_locations_list())

def _cached_location_name(location_code: int) -> str:
    key = _customer_cache_key('location_name', location_code)
    cached = _customer_cache_get(key)
    if cached is not None:
        return cached
    return _customer_cache_set(key, _location_name(location_code))

def _lookup_name_from_rows(rows: List[Dict[str, Any]], code: Any) -> str:
    if code is None or str(code).strip() == '':
        return ''
    want = _norm_code(code)
    for row in rows or []:
        if _norm_code(row.get('code')) == want:
            return str(row.get('name') or row.get('code') or '').strip()
    return ''

def _cached_salesman_name(salesman_code: Any, location_code: Optional[int]=None) -> str:
    return _lookup_name_from_rows(_cached_salesman_list(location_code), salesman_code)

def _cached_category_name(category_code: Any, location_code: Optional[int]=None) -> str:
    return _lookup_name_from_rows(_cached_category_list(location_code), category_code)

def _cached_route_name(route_no: Any) -> str:
    return _lookup_name_from_rows(_cached_route_list(), route_no)

def _cached_employee_name(employee_code: Any) -> str:
    return _lookup_name_from_rows(_cached_employee_list(), employee_code)

def _cached_default_accounts() -> Dict[str, Any]:
    key = _customer_cache_key('default_accounts')
    cached = _customer_cache_get(key)
    if cached is not None:
        return cached
    # Schema/default account creation runs during app bootstrap; form display should not
    # pay that setup cost on every open.
    return _customer_cache_set(key, dict(DEFAULT_PARTY_ACCOUNTS))

def _cached_customer_chart_accounts(default_accounts: Dict[str, Any]) -> List[Dict[str, Any]]:
    key = _customer_cache_key('chart_accounts')
    cached = _customer_cache_get(key)
    if cached is not None:
        return cached
    try:
        rows = get_all_chart_of_accounts()
    except Exception:
        rows = []
    return _customer_cache_set(key, _ensure_default_customer_accounts_in_list(rows, default_accounts))

def _location_name(location_code: int) -> str:
    try:
        loc_col = _detect_column(LOCATIONS_TABLE, ['LOCATIONCODE', 'locationcode'])
        name_col = _detect_column(LOCATIONS_TABLE, ['LOCATIONNAME', 'locationname'])
        if not loc_col or not name_col:
            return ''
        _, rows = _fetch_rows(f'SELECT {name_col} AS name FROM {LOCATIONS_TABLE} WHERE {loc_col} = :lc', {'lc': location_code})
        return rows[0].get('name') or '' if rows else ''
    except Exception:
        return ''

@bp.route('/master/customer')
def customer_list():
    _t0 = time.perf_counter()
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    _ensure_customer_account_columns()
    _step = time.perf_counter()
    location_code = None
    try:
        location_code = _resolve_location_code()
    except Exception:
        pass
    _customer_timing_log('list_location', _step, loc=location_code)
    search_term = request.args.get('search', '').strip()
    status_filter = request.args.get('status', '').strip()
    invoice_filter = request.args.get('invoice', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    category_filter = request.args.get('category', '').strip()
    salesman_filter = request.args.get('salesman', '').strip()
    customers: List[Dict[str, Any]] = []
    customer_kpis = {'total': 0, 'active': 0, 'locked': 0, 'cash': 0, 'credit': 0}
    salesman_list: List[Dict[str, Any]] = []
    category_list: List[Dict[str, Any]] = []
    items_per_page = 50
    _step = time.perf_counter()
    total_count = int((customer_kpis or {}).get('total') or 0)
    total_pages = (total_count + items_per_page - 1) // items_per_page if total_count > 0 else 1
    resp = render_template('customer/customer_list.html', customers=customers, customer_kpis=customer_kpis, search_term=search_term, status_filter=status_filter, invoice_filter=invoice_filter, date_from=date_from, date_to=date_to, category_filter=category_filter, salesman_filter=salesman_filter, salesman_list=salesman_list, category_list=category_list, current_page=1, total_pages=total_pages, items_per_page=items_per_page, total_count=total_count, customer_items_api_url=url_for('customer.customer_list_api_items'))
    _customer_timing_log('list_render', _step, rows=len(customers or []))
    _customer_timing_log('list_total', _t0, rows=0, total=0, shell=1)
    return resp


@bp.route('/master/customer/api/items')
def customer_list_api_items():
    _t0 = time.perf_counter()
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    try:
        location_code = _resolve_location_code()
    except Exception:
        location_code = None
    search_term = request.args.get('search', '').strip()
    status_filter = request.args.get('status', '').strip()
    invoice_filter = request.args.get('invoice', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    category_filter = request.args.get('category', '').strip()
    salesman_filter = request.args.get('salesman', '').strip()
    try:
        page = max(1, int(request.args.get('page') or 1))
    except (TypeError, ValueError):
        page = 1
    try:
        per_page = max(20, min(int(request.args.get('per_page') or 50), 500))
    except (TypeError, ValueError):
        per_page = 50
    rows = _get_customer_list(location_code, search=search_term or None, customer_status=status_filter or None, invoice_code=invoice_filter or None, date_from=date_from or None, date_to=date_to or None, category_code=category_filter or None, salesman_code=salesman_filter or None, page=page, items_per_page=per_page)
    try:
        total_count = max(0, int(request.args.get('total_count') or 0))
    except (TypeError, ValueError):
        total_count = 0
    kpis = None
    if total_count <= 0:
        kpis = _get_customer_list_kpis(location_code, search=search_term or None, customer_status=status_filter or None, invoice_code=invoice_filter or None, date_from=date_from or None, date_to=date_to or None, category_code=category_filter or None, salesman_code=salesman_filter or None)
        total_count = int((kpis or {}).get('total') or 0)
    total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 1
    _customer_timing_log('api_items', _t0, page=page, per_page=per_page, rows=len(rows or []), total=total_count)
    return jsonify({
        'success': True,
        'items': [_json_customer_row(r) for r in rows or []],
        'total_count': total_count,
        'page': page,
        'items_per_page': per_page,
        'total_pages': total_pages,
        'kpis': kpis,
    })


@bp.route('/master/customer/api/filter-options')
def customer_list_api_filter_options():
    _t0 = time.perf_counter()
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    try:
        location_code = _resolve_location_code()
    except Exception:
        location_code = None
    salesmen = _cached_salesman_list(location_code)
    categories = _cached_category_list(location_code)
    _customer_timing_log('api_filter_options', _t0, salesmen=len(salesmen or []), categories=len(categories or []))
    return jsonify({'success': True, 'salesmen': salesmen or [], 'categories': categories or []})

def _customer_dict_from_form(form: Any, location_code: int, customer_code: Optional[int] = None) -> Dict[str, Any]:
    """Rebuild customer dict from POST so validation errors can re-render the form without losing input."""
    from db import normalize_customer_billing_type

    sex_raw = (form.get('sex') or 'MALE').strip().upper()
    code = customer_code
    if code is None:
        code = _parse_int(form.get('customercode'), None)
    return {
        'locationcode': location_code,
        'customercode': code,
        'customername': (form.get('customername') or '').strip(),
        'designation': (form.get('designation') or '').strip(),
        'sex': 'M' if sex_raw in ('MALE', 'M') else 'F',
        'address': (form.get('address') or '').strip(),
        'nationality': (form.get('nationality') or '').strip(),
        'telephone': (form.get('telephone') or '').strip(),
        'fax': (form.get('fax') or '').strip(),
        'mobile': (form.get('mobile') or '').strip(),
        'creditlimit': _parse_decimal(form.get('creditlimit'), 0),
        'creditterms': _parse_decimal(form.get('creditterm'), 2),
        'currentcreditamount': _parse_decimal(form.get('currentcredit'), 0),
        'salesmancode': _parse_int(form.get('salesmancode'), 0) or None,
        'customer_billing_type': normalize_customer_billing_type(form.get('customer_billing_type')),
        'customercategory': _parse_int(form.get('customercategory'), 0) or None,
        'bysalesman': _parse_int(form.get('bysalesman'), 0) or None,
        'routeno': _parse_int(form.get('routeno'), 0) or None,
        'street': (form.get('street') or '').strip(),
        'zone': (form.get('zone') or '').strip(),
        'pobox': (form.get('pobox') or '').strip(),
        'crno': (form.get('crno') or '').strip(),
        'email': (form.get('email') or '').strip(),
        'qatarid': (form.get('qatarid') or '').strip(),
        'whatsapp': (form.get('whatsapp') or '').strip(),
        'flag': (form.get('flag') or 'Y').strip().upper()[:1],
        'closed': (form.get('closed') or 'N').strip().upper()[:1],
        'employeecode': _safe_int(form.get('employeecode'), None),
        'reason': (form.get('reason') or '').strip(),
        'otherreason': (form.get('otherreason') or '').strip(),
        'closedreason': (form.get('closedreason') or '').strip(),
        'countersale': 'Y' if form.get('countersale') == 'Y' else 'N',
        'receivableaccount': _parse_int(form.get('receivableaccount'), 0) or None,
        'salesaccount': _parse_int(form.get('salesaccount'), 0) or None,
        'vatoutputaccount': _parse_int(form.get('vatoutputaccount'), 0) or None,
        'advanceaccount': _parse_int(form.get('advanceaccount'), 0) or None,
        'ccode': (form.get('ccode') or '').strip(),
        'points': _parse_int(form.get('points'), 0) or None,
    }


def _render_customer_form_page(
    location_code: int,
    *,
    customer: Optional[Dict[str, Any]] = None,
    is_new: bool,
    customer_code: Optional[int] = None,
):
    location_name = _cached_location_name(location_code)
    locations = _cached_locations_list()
    default_accounts = _cached_default_accounts()
    chart_accounts = _cached_customer_chart_accounts(default_accounts)
    if is_new:
        next_code = (customer.get('customercode') if customer and customer.get('customercode') else None) or _get_next_customer_code(location_code)
    else:
        next_code = customer_code
    sm = customer.get('salesmancode') if customer else None
    by_sm = customer.get('bysalesman') if customer else None
    cat = customer.get('customercategory') if customer else None
    rt = customer.get('routeno') if customer else None
    emp = customer.get('employeecode') if customer else None
    salesman_name = _cached_salesman_name(sm, location_code) if sm else ''
    by_salesman_name = _cached_salesman_name(by_sm, location_code) if by_sm else ''
    category_name = _cached_category_name(cat, location_code) if cat else ''
    route_name = _cached_route_name(rt) if rt else ''
    employee_name = _cached_employee_name(emp) if emp else ''
    return render_template(
        'customer/customer_form.html',
        customer=customer,
        location_code=location_code,
        location_name=location_name,
        next_customer_code=next_code,
        locations=locations,
        chart_accounts=chart_accounts,
        default_accounts=default_accounts,
        is_edit=not is_new,
        salesman_name=salesman_name,
        by_salesman_name=by_salesman_name,
        category_name=category_name,
        route_name=route_name,
        employee_name=employee_name,
    )


def _customer_save_validation_error(
    message: str,
    form: Any,
    location_code: int,
    customer_code: Optional[int],
    is_new: bool,
):
    issue_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY)
    flash(message, 'error')
    customer = _customer_dict_from_form(form, location_code, customer_code)
    return _render_customer_form_page(
        location_code,
        customer=customer,
        is_new=is_new,
        customer_code=customer_code,
    )


@bp.route('/master/customer/new', methods=['GET', 'POST'])
def customer_create():
    _t0 = time.perf_counter()
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    _step = time.perf_counter()
    location_code = _resolve_location_code()
    _ensure_customer_account_columns()
    _customer_timing_log('form_new_location_schema', _step, loc=location_code)
    _step = time.perf_counter()
    location_name = _cached_location_name(location_code)
    next_code = _get_next_customer_code(location_code)
    locations = _cached_locations_list()
    _customer_timing_log('form_new_core_lookups', _step, locations=len(locations or []))
    _step = time.perf_counter()
    default_accounts = _cached_default_accounts()
    chart_accounts = _cached_customer_chart_accounts(default_accounts)
    _customer_timing_log('form_new_accounts', _step, accounts=len(chart_accounts or []))
    if request.method == 'POST':
        return _customer_save(location_code=location_code, customer_code=None, is_new=True)
    _step = time.perf_counter()
    resp = _render_customer_form_page(location_code, customer=None, is_new=True)
    _customer_timing_log('form_new_render', _step)
    _customer_timing_log('form_new_total', _t0, loc=location_code)
    return resp

@bp.route('/master/customer/<int:location_code>/<int:customer_code>/edit', methods=['GET', 'POST'])
def customer_edit(location_code: int, customer_code: int):
    _t0 = time.perf_counter()
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    _step = time.perf_counter()
    _ensure_customer_account_columns()
    customer = _get_customer_by_code(location_code, customer_code)
    _customer_timing_log('form_edit_customer', _step, loc=location_code, code=customer_code, found=1 if customer else 0)
    if not customer:
        flash('Customer not found.', 'error')
        return redirect(url_for('customer.customer_list'))
    _step = time.perf_counter()
    location_name = _cached_location_name(location_code)
    locations = _cached_locations_list()
    salesman_name = _cached_salesman_name(customer.get('salesmancode'), location_code) if customer.get('salesmancode') else ''
    by_salesman_name = _cached_salesman_name(customer.get('bysalesman'), location_code) if customer.get('bysalesman') else ''
    category_name = _cached_category_name(customer.get('customercategory'), location_code) if customer.get('customercategory') else ''
    route_name = _cached_route_name(customer.get('routeno')) if customer.get('routeno') else ''
    employee_name = _cached_employee_name(customer.get('employeecode')) if customer.get('employeecode') else ''
    _customer_timing_log('form_edit_labels', _step, locations=len(locations or []))
    _step = time.perf_counter()
    default_accounts = _cached_default_accounts()
    chart_accounts = _cached_customer_chart_accounts(default_accounts)
    _customer_timing_log('form_edit_accounts', _step, accounts=len(chart_accounts or []))
    if request.method == 'POST':
        return _customer_save(location_code=location_code, customer_code=customer_code, is_new=False)
    _step = time.perf_counter()
    resp = _render_customer_form_page(
        location_code,
        customer=customer,
        is_new=False,
        customer_code=customer_code,
    )
    _customer_timing_log('form_edit_render', _step)
    _customer_timing_log('form_edit_total', _t0, loc=location_code, code=customer_code)
    return resp

def _parse_positive_account_code(raw: Any) -> Optional[int]:
    """Chart account code from POST: positive int required; empty/zero/invalid → None."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        v = int(float(s))
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None

def _customer_save(location_code: int, customer_code: Optional[int], is_new: bool):
    submitted = (request.form.get('save_nonce') or '').strip()
    if not verify_consume_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY, submitted):
        issue_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY)
        flash('Duplicate or invalid submit. Reload the customer form and try again.', 'error')
        if is_new:
            return redirect(url_for('customer.customer_create'))
        return redirect(url_for('customer.customer_edit', location_code=location_code, customer_code=customer_code or 0))
    _ensure_customer_account_columns()
    tbl = _customer_table()
    if not tbl:
        flash('Customer table not found.', 'error')
        return redirect(url_for('customer.customer_list'))
    form = request.form
    customername = (form.get('customername') or '').strip().upper()
    if not customername:
        return _customer_save_validation_error('Customer name is required.', form, location_code, customer_code, is_new)
    designation = (form.get('designation') or '').strip()[:100] if form.get('designation') else ''
    sex = (form.get('sex') or 'MALE').strip().upper()
    cussex = 'M' if sex == 'MALE' else 'F'
    address = (form.get('address') or '').strip()[:200]
    nationality = (form.get('nationality') or '').strip()[:100]
    telephone = (form.get('telephone') or '').strip()[:15]
    fax = (form.get('fax') or '').strip()[:15]
    mobile = (form.get('mobile') or '').strip()[:15]
    creditlimit = _parse_decimal(form.get('creditlimit'), 0)
    creditterms = _parse_decimal(form.get('creditterm'), 2)
    duedays = creditterms
    currentcredit = _parse_decimal(form.get('currentcredit'), 0)
    salesmancode = _parse_int(form.get('salesmancode'), 0)
    from db import normalize_customer_billing_type

    billing_type = normalize_customer_billing_type(form.get('customer_billing_type'))
    customercategory = _parse_int(form.get('customercategory'), 0)
    bysalesman = _parse_int(form.get('bysalesman'), 0)
    routeno = _parse_int(form.get('routeno'), 0)
    street = (form.get('street') or '').strip()[:200]
    zone = (form.get('zone') or '').strip()[:100]
    pobox = (form.get('pobox') or '').strip()[:50]
    crno = (form.get('crno') or '').strip()[:250]
    email = (form.get('email') or '').strip()[:150]
    qatarid = (form.get('qatarid') or '').strip()[:50]
    whatsapp = (form.get('whatsapp') or '').strip()[:20]
    flag = (form.get('flag') or 'Y').strip().upper()[:1]
    closed = (form.get('closed') or 'N').strip().upper()[:1]
    employeecode = _safe_int(form.get('employeecode'), None)
    reason = (form.get('reason') or '').strip()[:500]
    otherreason = (form.get('otherreason') or '').strip()[:500]
    closedreason = (form.get('closedreason') or '').strip()[:500]
    countersale = 'Y' if form.get('countersale') == 'Y' else 'N'
    receivableaccount = _parse_positive_account_code(form.get('receivableaccount'))
    salesaccount = _parse_positive_account_code(form.get('salesaccount'))
    vatoutputaccount = _parse_positive_account_code(form.get('vatoutputaccount'))
    advanceaccount = _parse_positive_account_code(form.get('advanceaccount'))
    if str(session.get('user') or '').strip().lower() != 'admin':
        if not is_new and customer_code:
            existing = _get_customer_by_code(location_code, int(customer_code))
            if existing:
                receivableaccount = _parse_positive_account_code(existing.get('receivableaccount')) or receivableaccount
                salesaccount = _parse_positive_account_code(existing.get('salesaccount')) or salesaccount
                vatoutputaccount = _parse_positive_account_code(existing.get('vatoutputaccount')) or vatoutputaccount
                advanceaccount = _parse_positive_account_code(existing.get('advanceaccount')) or advanceaccount
        elif is_new:
            defs = _cached_default_accounts()
            receivableaccount = _parse_positive_account_code(defs.get('customer_receivable')) or receivableaccount
            salesaccount = _parse_positive_account_code(defs.get('customer_sales')) or salesaccount
            vatoutputaccount = _parse_positive_account_code(defs.get('customer_vat_output')) or vatoutputaccount
            advanceaccount = _parse_positive_account_code(defs.get('customer_advance')) or advanceaccount
    if billing_type not in ('CASH', 'CREDIT'):
        return _customer_save_validation_error('Customer type (Cash / Credit) is required.', form, location_code, customer_code, is_new)
    if receivableaccount is None or salesaccount is None or vatoutputaccount is None or (advanceaccount is None):
        return _customer_save_validation_error(
            'All four customer accounts are required: Receivable, Sales, Output VAT, and Advance. Select each on the Accounts tab (F1 / picker); values cannot be left blank or zero.',
            form,
            location_code,
            customer_code,
            is_new,
        )
    if not mobile and (not telephone):
        return _customer_save_validation_error('Mobile No or Telephone is required.', form, location_code, customer_code, is_new)
    from storefront_backend.services.erp_customer import (
        find_email_duplicate,
        find_mobile_duplicate,
        validate_email,
        validate_mobile,
    )
    if email:
        ok_email, email_msg = validate_email(email, required=False)
        if not ok_email:
            return _customer_save_validation_error(email_msg, form, location_code, customer_code, is_new)
        email_dup = find_email_duplicate(email, location_code=location_code, exclude_code=None if is_new else customer_code)
        if email_dup:
            return _customer_save_validation_error(
                f'Email already used by customer {email_dup}.',
                form,
                location_code,
                customer_code,
                is_new,
            )
    if mobile:
        ok_mobile, mobile_msg, _mobile_norm = validate_mobile(mobile, required=False)
        if not ok_mobile:
            return _customer_save_validation_error(mobile_msg, form, location_code, customer_code, is_new)
        mobile_dup = find_mobile_duplicate(mobile, location_code=location_code, exclude_code=None if is_new else customer_code)
        if mobile_dup:
            return _customer_save_validation_error(
                f'Mobile number already used by customer {mobile_dup}.',
                form,
                location_code,
                customer_code,
                is_new,
            )
    if whatsapp:
        wa_dup = find_mobile_duplicate(whatsapp, location_code=location_code, exclude_code=None if is_new else customer_code)
        if wa_dup:
            return _customer_save_validation_error(
                f'WhatsApp number already used by customer {wa_dup}.',
                form,
                location_code,
                customer_code,
                is_new,
            )
    if billing_type == 'CREDIT':
        if not creditlimit or creditlimit <= 0:
            return _customer_save_validation_error('Credit Limit is required for Credit customers.', form, location_code, customer_code, is_new)
        if not creditterms or creditterms <= 0:
            return _customer_save_validation_error('Credit Term (Days) is required for Credit customers.', form, location_code, customer_code, is_new)
    loc_col = _detect_column(tbl, ['LOCATIONCODE', 'locationcode'])
    code_col = _detect_column(tbl, ['CUSTOMERCODE', 'customercode'])
    name_col = _detect_column(tbl, ['CUSTOMERNAME', 'customername'])
    if not loc_col or not code_col:
        flash('Required columns not found.', 'error')
        return redirect(url_for('customer.customer_list'))
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                if name_col:
                    dup_code = find_master_name_duplicate(
                        cur,
                        table=tbl,
                        name_col=name_col,
                        name_value=customername,
                        loc_col=loc_col,
                        location_code=location_code,
                        code_col=code_col,
                        exclude_code=None if is_new else customer_code,
                    )
                    if dup_code is not None:
                        return _customer_save_validation_error(
                            master_name_duplicate_message(
                                'customer',
                                customername,
                                location_code=location_code,
                                existing_code=dup_code,
                            ),
                            form,
                            location_code,
                            customer_code,
                            is_new,
                        )

                def _sync_duedays_to_customertmp(code_value: Any) -> None:
                    """Best-effort mirror of due days to CUSTOMERTMP when available."""
                    if code_value in (None, ''):
                        return
                    tmp_tbl = None
                    if _table_exists('CUSTOMERTMP'):
                        tmp_tbl = 'CUSTOMERTMP'
                    elif _table_exists('customertmp'):
                        tmp_tbl = 'customertmp'
                    if not tmp_tbl:
                        return
                    tmp_loc_col = _detect_column(tmp_tbl, ['LOCATIONCODE', 'locationcode'])
                    tmp_code_col = _detect_column(tmp_tbl, ['CUSTOMERCODE', 'customercode'])
                    tmp_due_col = _detect_column(tmp_tbl, ['DUEDAYS', 'DUE_DAYS', 'duedays', 'due_days'])
                    if not tmp_loc_col or not tmp_code_col or (not tmp_due_col):
                        return
                    cur.execute(f'UPDATE {tmp_tbl} SET {tmp_due_col} = :dd WHERE {tmp_loc_col} = :loc AND {tmp_code_col} = :code', {'dd': duedays, 'loc': location_code, 'code': code_value})
                if is_new:
                    code = _parse_int(form.get('customercode'), None)
                    if code is None:
                        code = _get_next_customer_code(location_code)
                    if _get_customer_by_code(location_code, int(code)):
                        return _customer_save_validation_error(
                            f'Customer code {code} already exists for this branch. Reload the form and save again.',
                            form,
                            location_code,
                            customer_code,
                            is_new,
                        )
                    all_cols = [loc_col, code_col, 'CCODE', 'CUSTOMERNAME', 'DESIGNATION', 'SEX', 'ADDRESS', 'NATIONALITY', 'TELEPHONE', 'FAX', 'MOBILE', 'CREDITLIMIT', 'CREDITTERMS', 'DUEDAYS', 'CURRENTCREDITAMOUNT', 'SALESMANCODE', 'CUSTOMER_BILLING_TYPE', 'FLAG', 'CLOSED', 'CUSTOMERCATEGORY', 'BYSALESMAN', 'ROUTENO', 'STREET', 'ZONE', 'POBOX', 'CRNO', 'RECEIVABLEACCOUNT', 'SALESACCOUNT', 'VATOUTPUTACCOUNT', 'ADVANCEACCOUNT', 'EMAIL', 'QATARID', 'WHATSAPP', 'EMPLOYEECODE', 'REASON', 'OTHERREASON', 'CLOSEDREASON', 'COUNTERSALE']
                    col_list = [c for c in all_cols if _column_exists(tbl, c)]
                    if 'CREATEDDATE' in _get_table_columns(tbl):
                        col_list.append('CREATEDDATE')
                    all_params = {'loc': location_code, 'code': code, 'customername': customername, 'designation': designation, 'cussex': cussex, 'address': address, 'nationality': nationality, 'telephone': telephone, 'fax': fax, 'mobile': mobile, 'creditlimit': creditlimit, 'creditterms': creditterms, 'duedays': duedays, 'currentcredit': currentcredit, 'salesmancode': salesmancode, 'customer_billing_type': billing_type, 'customercategory': customercategory, 'bysalesman': bysalesman, 'routeno': routeno, 'street': street, 'zone': zone, 'pobox': pobox, 'crno': crno, 'receivableaccount': receivableaccount, 'salesaccount': salesaccount, 'vatoutputaccount': vatoutputaccount, 'advanceaccount': advanceaccount, 'email': email, 'qatarid': qatarid, 'whatsapp': whatsapp, 'flag': flag, 'closed': closed, 'employeecode': employeecode, 'reason': reason, 'otherreason': otherreason, 'closedreason': closedreason, 'countersale': countersale}
                    if 'CCODE' in col_list:
                        from addons.ho.controllers.routes import _cc_next_code
                        tid_s = session.get('tenant_id')
                        _, cc_ins = _cc_next_code(str(tid_s).strip() if tid_s else None)
                        cc_ins = str(cc_ins or '').strip()[:20]
                        if not cc_ins:
                            return _customer_save_validation_error(
                                'C Code (CCODE) could not be generated; customer was not saved.',
                                form,
                                location_code,
                                customer_code,
                                is_new,
                            )
                        all_params['ccode'] = cc_ins
                    ph_map = {loc_col: ':loc', code_col: ':code', 'CCODE': ':ccode', 'CUSTOMERNAME': ':customername', 'DESIGNATION': ':designation', 'SEX': ':cussex', 'ADDRESS': ':address', 'NATIONALITY': ':nationality', 'TELEPHONE': ':telephone', 'FAX': ':fax', 'MOBILE': ':mobile', 'CREDITLIMIT': ':creditlimit', 'CREDITTERMS': ':creditterms', 'DUEDAYS': ':duedays', 'CURRENTCREDITAMOUNT': ':currentcredit', 'SALESMANCODE': ':salesmancode', 'CUSTOMER_BILLING_TYPE': ':customer_billing_type', 'FLAG': ':flag', 'CLOSED': ':closed', 'CUSTOMERCATEGORY': ':customercategory', 'BYSALESMAN': ':bysalesman', 'ROUTENO': ':routeno', 'STREET': ':street', 'ZONE': ':zone', 'POBOX': ':pobox', 'CRNO': ':crno', 'RECEIVABLEACCOUNT': ':receivableaccount', 'SALESACCOUNT': ':salesaccount', 'VATOUTPUTACCOUNT': ':vatoutputaccount', 'ADVANCEACCOUNT': ':advanceaccount', 'CREATEDDATE': 'SYSDATE', 'EMAIL': ':email', 'QATARID': ':qatarid', 'WHATSAPP': ':whatsapp', 'EMPLOYEECODE': ':employeecode', 'REASON': ':reason', 'OTHERREASON': ':otherreason', 'CLOSEDREASON': ':closedreason', 'COUNTERSALE': ':countersale'}
                    placeholders = ', '.join((ph_map.get(c, 'NULL') for c in col_list))
                    cols_str = ', '.join(col_list)
                    insert_params = {}
                    for c in col_list:
                        ph = ph_map.get(c, 'NULL')
                        if ph.startswith(':'):
                            param_name = ph[1:].strip()
                            if param_name in all_params:
                                insert_params[param_name] = all_params[param_name]
                    ins_sql = f'INSERT INTO {tbl} ({cols_str}) VALUES ({placeholders})'
                    cur.execute(ins_sql, insert_params)
                    _sync_duedays_to_customertmp(code)
                    conn.commit()
                    flash('Customer saved successfully.', 'success')
                    nm = (customername or '').strip()[:120]
                    append_master_activity(username=_sess_user_for_log(), action='CREATE', entity='customer', summary=f'location={location_code}, customer_code={code}, name={nm}', detail={'locationcode': location_code, 'customercode': code, 'customername': nm})
                    return redirect(url_for('customer.customer_list'))
                else:
                    val_by_param = {'customername': customername, 'designation': designation, 'cussex': cussex, 'address': address, 'nationality': nationality, 'telephone': telephone, 'fax': fax, 'mobile': mobile, 'creditlimit': creditlimit, 'creditterms': creditterms, 'duedays': duedays, 'currentcredit': currentcredit, 'salesmancode': salesmancode, 'customer_billing_type': billing_type, 'customercategory': customercategory, 'bysalesman': bysalesman, 'routeno': routeno, 'street': street, 'zone': zone, 'pobox': pobox, 'crno': crno, 'receivableaccount': receivableaccount, 'salesaccount': salesaccount, 'vatoutputaccount': vatoutputaccount, 'advanceaccount': advanceaccount, 'email': email, 'qatarid': qatarid, 'whatsapp': whatsapp, 'flag': flag, 'closed': closed, 'employeecode': employeecode, 'reason': reason, 'otherreason': otherreason, 'closedreason': closedreason, 'countersale': countersale}
                    set_parts = []
                    upd_params = {'loc': location_code, 'code': customer_code}
                    for col, param in [('CUSTOMERNAME', 'customername'), ('DESIGNATION', 'designation'), ('SEX', 'cussex'), ('ADDRESS', 'address'), ('NATIONALITY', 'nationality'), ('TELEPHONE', 'telephone'), ('FAX', 'fax'), ('MOBILE', 'mobile'), ('CREDITLIMIT', 'creditlimit'), ('CREDITTERMS', 'creditterms'), ('DUEDAYS', 'duedays'), ('CURRENTCREDITAMOUNT', 'currentcredit'), ('SALESMANCODE', 'salesmancode'), ('CUSTOMER_BILLING_TYPE', 'customer_billing_type'), ('FLAG', 'flag'), ('CLOSED', 'closed'), ('CUSTOMERCATEGORY', 'customercategory'), ('BYSALESMAN', 'bysalesman'), ('ROUTENO', 'routeno'), ('STREET', 'street'), ('ZONE', 'zone'), ('POBOX', 'pobox'), ('CRNO', 'crno'), ('RECEIVABLEACCOUNT', 'receivableaccount'), ('SALESACCOUNT', 'salesaccount'), ('VATOUTPUTACCOUNT', 'vatoutputaccount'), ('ADVANCEACCOUNT', 'advanceaccount'), ('EMAIL', 'email'), ('QATARID', 'qatarid'), ('WHATSAPP', 'whatsapp'), ('EMPLOYEECODE', 'employeecode'), ('REASON', 'reason'), ('OTHERREASON', 'otherreason'), ('CLOSEDREASON', 'closedreason'), ('COUNTERSALE', 'countersale')]:
                        if _column_exists(tbl, col):
                            set_parts.append(f'{col} = :{param}')
                            upd_params[param] = val_by_param[param]
                    if not set_parts:
                        flash('No updatable columns found.', 'error')
                        return redirect(url_for('customer.customer_list'))
                    upd_sql = f"UPDATE {tbl} SET {', '.join(set_parts)} WHERE {loc_col} = :loc AND {code_col} = :code"
                    cur.execute(upd_sql, upd_params)
                    _sync_duedays_to_customertmp(customer_code)
                    conn.commit()
                    flash('Customer updated successfully.', 'success')
                    nm = (customername or '').strip()[:120]
                    append_master_activity(username=_sess_user_for_log(), action='UPDATE', entity='customer', summary=f'location={location_code}, customer_code={customer_code}, name={nm}', detail={'locationcode': location_code, 'customercode': customer_code, 'customername': nm})
                    return redirect(url_for('customer.customer_list'))
    except Exception as e:
        print(f'[ERROR _customer_save] {e}')
        import traceback
        traceback.print_exc()
        return _customer_save_validation_error(f'Error saving customer: {str(e)}', form, location_code, customer_code, is_new)

def _column_exists(table: str, col: str) -> bool:
    cols = _get_table_columns(table)
    return col.upper() in cols

def _parse_decimal(v: Any, default: float) -> float:
    if v is None or (isinstance(v, str) and (not v.strip())):
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default

def _parse_int(v: Any, default: int) -> int:
    if v is None or (isinstance(v, str) and (not v.strip())):
        return default
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default

@bp.route('/master/customer/<int:location_code>/<int:customer_code>/delete', methods=['POST'])
def customer_delete(location_code: int, customer_code: int):
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    submitted = (request.form.get('save_nonce') or '').strip()
    if not verify_consume_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY, submitted):
        flash('Duplicate or invalid submit. Reload the customer list and try again.', 'error')
        return redirect(url_for('customer.customer_list'))
    tbl = _customer_table()
    if not tbl:
        flash('Customer table not found.', 'error')
        return redirect(url_for('customer.customer_list'))
    loc_col = _detect_column(tbl, ['LOCATIONCODE', 'locationcode'])
    code_col = _detect_column(tbl, ['CUSTOMERCODE', 'customercode'])
    if not loc_col or not code_col:
        flash('Required columns not found.', 'error')
        return redirect(url_for('customer.customer_list'))
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f'DELETE FROM {tbl} WHERE {loc_col} = :loc AND {code_col} = :code', {'loc': location_code, 'code': customer_code})
                conn.commit()
        flash('Customer deleted.', 'success')
        append_master_activity(username=_sess_user_for_log(), action='DELETE', entity='customer', summary=f'location={location_code}, customer_code={customer_code}', detail={'locationcode': location_code, 'customercode': customer_code})
    except Exception as e:
        flash(f'Error deleting customer: {str(e)}', 'error')
    return redirect(url_for('customer.customer_list'))

@bp.route('/master/customer/<int:location_code>/<int:customer_code>')
def customer_view(location_code: int, customer_code: int):
    _t0 = time.perf_counter()
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    _step = time.perf_counter()
    customer = _get_customer_by_code(location_code, customer_code)
    _customer_timing_log('view_customer', _step, loc=location_code, code=customer_code, found=1 if customer else 0)
    if not customer:
        flash('Customer not found.', 'error')
        return redirect(url_for('customer.customer_list'))
    _step = time.perf_counter()
    location_name = _cached_location_name(location_code)
    salesman_name = _cached_salesman_name(customer.get('salesmancode'), location_code) if customer.get('salesmancode') else ''
    by_salesman_name = _cached_salesman_name(customer.get('bysalesman'), location_code) if customer.get('bysalesman') else ''
    category_name = _cached_category_name(customer.get('customercategory'), location_code) if customer.get('customercategory') else ''
    route_name = _cached_route_name(customer.get('routeno')) if customer.get('routeno') else ''
    _customer_timing_log('view_labels', _step)
    _step = time.perf_counter()
    resp = render_template('customer/customer_view.html', customer=customer, location_code=location_code, location_name=location_name, salesman_name=salesman_name, by_salesman_name=by_salesman_name, category_name=category_name, route_name=route_name)
    _customer_timing_log('view_render', _step)
    _customer_timing_log('view_total', _t0, loc=location_code, code=customer_code)
    return resp

@bp.route('/master/customer/export')
def customer_export():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    location_code = request.args.get('location', '').strip()
    loc_int = int(location_code) if location_code.isdigit() else _resolve_location_code()
    customers = _get_customer_list(loc_int, limit=10000)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Sl.No', 'Location', 'Customer Code', 'Customer Name', 'Customer Type', 'Credit Limit', 'Outstanding (GL)'])
    for idx, c in enumerate(customers, start=1):
        writer.writerow([
            idx,
            c.get('locationcode'),
            c.get('customercode'),
            c.get('customername') or '',
            c.get('customer_billing_type') or 'CASH',
            c.get('creditlimit') or 0,
            c.get('gl_outstanding') or 0,
        ])
    output.seek(0)
    filename = f"customer_list_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename={filename}'})

@bp.route('/master/customer/api/salesman-list', methods=['GET'])
def api_salesman_list():
    """API: Get list of salesmen from SALESMAN table for popup (filtered by session location if column exists)."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    try:
        location_code = _resolve_location_code()
        rows = _get_salesman_list(location_code)
        return jsonify({'success': True, 'salesmen': rows})
    except Exception as e:
        print(f'[ERROR api_salesman_list] {e}')
        return jsonify({'success': False, 'error': str(e)}, 500)

@bp.route('/master/customer/api/category-list', methods=['GET'])
def api_category_list():
    """API: Get list of customer categories from TBLCUSTOMERCATEGORY (filtered by session location if column exists)."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    try:
        location_code = _resolve_location_code()
        rows = _get_category_list(location_code)
        return jsonify({'success': True, 'categories': rows})
    except Exception as e:
        print(f'[ERROR api_category_list] {e}')
        return jsonify({'success': False, 'error': str(e)}, 500)

@bp.route('/master/customer/api/route-list', methods=['GET'])
def api_route_list():
    """API: Get list of routes from TBLROUTES for popup."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    try:
        rows = _get_route_list()
        return jsonify({'success': True, 'routes': rows})
    except Exception as e:
        print(f'[ERROR api_route_list] {e}')
        return jsonify({'success': False, 'error': str(e)}, 500)

@bp.route('/master/customer/api/employee-list', methods=['GET'])
def api_employee_list():
    """API: Get list of employees from EMPLOYEE1 where PENDING='Y' for popup."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    try:
        rows = _get_employee_list()
        return jsonify({'success': True, 'employees': rows})
    except Exception as e:
        print(f'[ERROR api_employee_list] {e}')
        return jsonify({'success': False, 'error': str(e)}, 500)

def _missing_recovery_redirect_login():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    return None

@bp.route('/master/customer/missing-recovery', methods=['GET', 'POST'])
def missing_customer_recovery():
    """Find lapsed customers (no purchase in N days), assign to a user for visits."""
    bad = _missing_recovery_redirect_login()
    if bad:
        return bad
    mcr.ensure_missing_customer_recovery_table()
    n_auto = mcr.auto_recover_cases_with_new_sales()
    location_code = _resolve_location_code()
    lapsed_rows: Optional[List[Dict[str, Any]]] = None
    inactive_days = 90
    min_bills = 1
    if request.method == 'POST' and request.form.get('action') == 'find':
        try:
            inactive_days = max(1, int(request.form.get('inactive_days') or 90))
        except (TypeError, ValueError):
            inactive_days = 90
        try:
            min_bills = max(1, int(request.form.get('min_bills') or 1))
        except (TypeError, ValueError):
            min_bills = 1
        lapsed_rows = mcr.fetch_lapsed_customers(inactive_days=inactive_days, min_bills=min_bills, location_code=location_code, exclude_open_cases=True)
    assign_users: List[Dict[str, Any]] = []
    if lapsed_rows is not None and len(lapsed_rows) > 0:
        assign_users = get_assignable_login_users(session.get('user'), session.get('tenant_id'))
    return render_template('customer/missing_customer_recovery.html', assign_users=assign_users, lapsed_rows=lapsed_rows, inactive_days=inactive_days, min_bills=min_bills, location_code=location_code, auto_recovered_count=n_auto)

@bp.route('/master/customer/missing-recovery/assign', methods=['POST'])
def missing_customer_recovery_assign():
    bad = _missing_recovery_redirect_login()
    if bad:
        return bad
    submitted_nonce = (request.form.get('save_nonce') or '').strip()
    if not verify_consume_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY, submitted_nonce):
        flash('Duplicate or invalid save. Reload the page and try again.', 'error')
        return redirect(url_for('customer.missing_customer_recovery'))
    assignee = (request.form.get('assignee') or '').strip()
    picks = request.form.getlist('cust_pick')
    try:
        inactive_days_rule = max(1, int(request.form.get('inactive_days_rule') or 90))
    except (TypeError, ValueError):
        inactive_days_rule = 90
    creator = str(session.get('user') or '').strip()
    location_code = _resolve_location_code()
    if not assignee:
        flash('Select a user to assign.', 'error')
        return redirect(url_for('customer.missing_customer_recovery'))
    allowed_names = {str(u.get('username') or '').strip().upper() for u in get_assignable_login_users(session.get('user'), session.get('tenant_id'))}
    if assignee.upper() not in allowed_names:
        flash('Selected user is not allowed for assignment from your login.', 'error')
        return redirect(url_for('customer.missing_customer_recovery'))
    if not picks:
        flash('Select at least one customer.', 'error')
        return redirect(url_for('customer.missing_customer_recovery'))
    n_ok = 0
    for code in picks:
        code = str(code or '').strip()
        if not code:
            continue
        ok, err = mcr.upsert_open_case(customer_code=code, assignee=assignee, inactive_days_rule=inactive_days_rule, created_by=creator, location_code=location_code)
        if ok:
            n_ok += 1
        elif err:
            flash(err, 'error')
    if n_ok:
        flash(f'Assigned {n_ok} customer(s) to {assignee}.', 'success')
    return redirect(url_for('customer.missing_customer_recovery'))

@bp.route('/master/customer/missing-recovery/tasks', methods=['GET'])
def missing_customer_recovery_tasks():
    """Cases assigned to the current user (visit / recover / close)."""
    bad = _missing_recovery_redirect_login()
    if bad:
        return bad
    mcr.ensure_missing_customer_recovery_table()
    n_auto = mcr.auto_recover_cases_with_new_sales()
    me = str(session.get('user') or '').strip()
    active_cases = mcr.list_recovery_cases(assigned_to=me, statuses=[mcr.STATUSES_OPEN, mcr.STATUSES_VISITED], limit=500)
    closed_cases = mcr.list_recovery_cases(assigned_to=me, statuses=[mcr.STATUSES_RECOVERED, mcr.STATUSES_CLOSED], limit=100)
    return render_template('customer/missing_customer_recovery_tasks.html', active_cases=active_cases, closed_cases=closed_cases, auto_recovered_count=n_auto)

@bp.route('/master/customer/missing-recovery/case-update', methods=['POST'])
def missing_customer_recovery_case_update():
    bad = _missing_recovery_redirect_login()
    if bad:
        return bad
    submitted_nonce = (request.form.get('save_nonce') or '').strip()
    if not verify_consume_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY, submitted_nonce):
        flash('Duplicate or invalid save. Reload the page and try again.', 'error')
        return redirect(url_for('customer.missing_customer_recovery_tasks'))
    case_id = (request.form.get('case_id') or '').strip()
    feedback = (request.form.get('feedback') or '').strip()
    visit_date = (request.form.get('visit_date') or '').strip()
    action = (request.form.get('action') or '').strip().lower()
    close_reason = (request.form.get('close_reason') or '').strip()
    ok, err = mcr.update_recovery_case(case_id=case_id, actor_username=str(session.get('user') or ''), feedback=feedback, visit_date_raw=visit_date or None, action=action, close_reason=close_reason)
    if ok:
        flash('Case updated.', 'success')
    else:
        flash(err or 'Update failed.', 'error')
    return redirect(url_for('customer.missing_customer_recovery_tasks'))
