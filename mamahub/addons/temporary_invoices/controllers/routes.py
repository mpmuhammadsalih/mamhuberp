"""Temporary invoices blueprint"""
import json
import os
import re
import threading
from pathlib import Path
from urllib.parse import urlencode
import io
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set, Tuple
from nexa_http import Blueprint, Response, flash, jsonify, redirect, render_template, request, send_file, session, url_for
from save_nonce import GLOBAL_SAVE_NONCE_SESSION_KEY, verify_consume_save_nonce
try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
from db import _TABLE_COLUMNS_CACHE, _detect_column as _db_detect_column, _fetch_rows, _get_connection, _get_scalar, _get_table_columns, _get_table_column_types_with_key, _table_exists, _pos_orderno_for_db, _sales_orderno_conflict_message, get_location_info_by_dbkey
_ADDON_ROOT = Path(__file__).resolve().parents[1]
bp = Blueprint('temporary_invoices', __name__, template_folder=str(_ADDON_ROOT / 'views' / 'templates'))

def _apply_active_connection(_location_code_or_tenant_id) -> None:
    """No-op: connection is set by g.current_tenant_id from session in app before_request."""
    pass

def _apply_session_tenant_connection_temporary_invoices() -> None:
    """Apply tenant/location session same as list page and invoice detail API."""
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    else:
        location_code = session.get('location_code')
        if location_code:
            _apply_active_connection(location_code)
        elif session.get('user') == 'admin':
            _apply_active_connection('HO')

def _resolve_location_code() -> int:
    """Resolve location_code as integer (single database)."""
    location_code_value = session.get('location_code')
    location_code_int = None
    if location_code_value is not None:
        try:
            if str(location_code_value).isdigit():
                location_code_int = int(location_code_value)
        except Exception:
            location_code_int = None
    if location_code_int is None:
        try:
            location_info = get_location_info_by_dbkey(None)
            if location_info and location_info.get('locationcode') is not None:
                location_code_int = int(location_info.get('locationcode'))
            if location_code_int is None:
                location_code_int = 1
        except Exception:
            location_code_int = 1
    return int(location_code_int)

def _ti_detection_cache() -> Optional[Dict[Any, Any]]:
    """Single-request cache: list route runs 3 fetchers that repeat the same detect_* work."""
    try:
        from nexa_http import g, has_request_context
    except ImportError:
        return None
    if not has_request_context():
        return None
    cache = getattr(g, '_temporary_invoices_detection_cache', None)
    if cache is None:
        cache = {}
        g._temporary_invoices_detection_cache = cache
    return cache

def _detect_table(candidates: List[str]) -> str:
    """Return first table name that exists."""
    cache = _ti_detection_cache()
    key = ('tbl', tuple(candidates))
    if cache is not None and key in cache:
        return str(cache[key])
    out = ''
    for table_name in candidates:
        try:
            if _get_table_columns(table_name):
                out = table_name
                break
        except Exception:
            continue
    if cache is not None:
        cache[key] = out
    return out

def _detect_column(table: str, candidates: List[str]) -> Optional[str]:
    """Same as db._detect_column but memoized per HTTP request for this blueprint."""
    if not table:
        return None
    cache = _ti_detection_cache()
    key = ('col', table.upper(), tuple((str(c).upper() for c in candidates)))
    if cache is not None and key in cache:
        return cache[key]
    resolved = _db_detect_column(table, candidates)
    if cache is not None:
        cache[key] = resolved
    return resolved
_TI_BILLHDR_INDEX_LOCK = threading.Lock()
_TI_BILLHDR_INDEX_DONE_KEYS: Set[str] = set()

def _ti_oracle_index_exists(cur: Any, index_name: str) -> bool:
    cur.execute('SELECT 1 FROM USER_INDEXES WHERE INDEX_NAME = UPPER(TRIM(:n))', {'n': index_name})
    return cur.fetchone() is not None

def _temporary_invoices_billhdr_index_specs() -> Tuple[str, List[Tuple[str, List[str]]]]:
    """Resolved BILLHDR table name and (index_name, columns) pairs for performance DDL."""
    hdr = _detect_table(['BILLHDR', 'billhdr'])
    if not hdr:
        return ('', [])
    loc = _detect_column(hdr, ['LOCATIONCODE', 'LOCATION_CODE', 'LOC_CODE', 'LOCCODE'])
    bdt = _detect_column(hdr, ['BILLDATE', 'BILL_DATE', 'TRANDATE', 'TRANS_DATE', 'TRANSDATE', 'INVDATE', 'INV_DATE', 'DOCDATE', 'DOC_DATE'])
    btyp = _detect_column(hdr, ['BILLTYPE', 'BILL_TYPE', 'TYPE'])
    billno = _detect_column(hdr, ['BILLNO', 'BILL_NO'])
    cust = _detect_column(hdr, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'CUSTCODE', 'CUST_CODE', 'CUSTNO', 'CUST_NO', 'CUSTOMERID', 'CUSTOMER_ID'])
    sm = _detect_column(hdr, ['SALESMANCODE', 'SALESMAN_CODE', 'SMCODE', 'SM_CODE', 'SALESMANID', 'SALESMAN_ID'])
    if not bdt:
        return (hdr, [])
    plans: List[Tuple[str, List[str]]] = []
    if loc and btyp:
        plans.append(('TI_BH_LOCTYPDT', [loc, btyp, bdt]))
    elif btyp:
        plans.append(('TI_BH_TYPDTBDT', [btyp, bdt]))
    if loc and billno:
        plans.append(('TI_BH_LOCDTBNO', [loc, bdt, billno]))
    elif billno:
        plans.append(('TI_BH_BDTBNO', [bdt, billno]))
    if loc and cust:
        plans.append(('TI_BH_LOCDTCUST', [loc, bdt, cust]))
    if loc and sm:
        plans.append(('TI_BH_LOCDTSMAN', [loc, bdt, sm]))
    return (hdr, plans)

def _ensure_temporary_invoices_billhdr_indexes(force: bool=False) -> None:
    """
    Create helpful Oracle indexes on BILLHDR for list + filter queries (idempotent).
    Skips silently if the DB user lacks CREATE INDEX or indexes already exist.
    Runs at most once per process per (tenant/session context key, current schema), unless force=True.
    """
    try:
        tenant_key = str(session.get('tenant_id') or session.get('location_code') or '').strip()
    except Exception:
        tenant_key = ''
    hdr, plans = _temporary_invoices_billhdr_index_specs()
    if not hdr or not plans:
        return
    try:
        with _get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT SYS_CONTEXT('USERENV','CURRENT_SCHEMA') FROM dual")
            schema_tag = str(cur.fetchone()[0] or '').strip().upper()
            cache_key = '{}|{}'.format(tenant_key, schema_tag)
            with _TI_BILLHDR_INDEX_LOCK:
                if not force and cache_key in _TI_BILLHDR_INDEX_DONE_KEYS:
                    return
            for idx_name, cols in plans:
                if not cols or not all(cols):
                    continue
                if _ti_oracle_index_exists(cur, idx_name):
                    continue
                col_sql = ', '.join(cols)
                try:
                    cur.execute('CREATE INDEX {} ON {} ({})'.format(idx_name, hdr, col_sql))
                except Exception as exc:
                    msg = str(exc)
                    if 'ORA-00955' in msg or 'ORA-01408' in msg or 'ORA-00957' in msg:
                        continue
                    print('[temporary_invoices] CREATE INDEX {} skipped: {}'.format(idx_name, msg))
            conn.commit()
        with _TI_BILLHDR_INDEX_LOCK:
            _TI_BILLHDR_INDEX_DONE_KEYS.add(cache_key)
    except Exception as exc:
        print('[temporary_invoices] billhdr performance indexes skipped: {}'.format(exc))

def _temporary_invoices_plan_index_ddls() -> List[str]:
    hdr, plans = _temporary_invoices_billhdr_index_specs()
    out: List[str] = []
    for idx_name, cols in plans:
        if cols and all(cols):
            out.append('CREATE INDEX {} ON {} ({})'.format(idx_name, hdr, ', '.join(cols)))
    return out

def _ti_sql_wrap_rownum_limit(inner_sql: str, limit: int=500) -> str:
    """Oracle: cap rows for safe preview execution."""
    lim = max(1, min(int(limit), 5000))
    return 'SELECT * FROM (\n{}\n) ti_cfg_wrapped WHERE ROWNUM <= {}'.format(inner_sql.strip(), lim)

def _fetch_lookup_list(table: str, code_col: str, name_col: str) -> List[Dict[str, Any]]:
    query = f'\n        SELECT {code_col} AS code, {name_col} AS name\n        FROM {table}\n        ORDER BY {name_col}\n    '
    _, rows = _fetch_rows(query, {})
    return rows

def _temporary_invoices_build_customer_dropdown_sql(date_from: str, date_to: str, location_code: Optional[int]=None) -> Tuple[Optional[str], Dict[str, Any]]:
    header_table = _detect_table(['BILLHDR', 'billhdr'])
    if not header_table:
        return (None, {})
    customer_table = _detect_table(['CUSTOMER', 'CUSTOMERS', 'customers', 'customer'])
    customercode_col = _detect_column(header_table, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'CUSTCODE', 'CUST_CODE', 'CUSTNO', 'CUST_NO', 'CUSTOMERID', 'CUSTOMER_ID'])
    billdate_col = _detect_column(header_table, ['BILLDATE', 'BILL_DATE', 'TRANDATE', 'TRANS_DATE', 'TRANSDATE', 'INVDATE', 'INV_DATE', 'DOCDATE', 'DOC_DATE'])
    locationcode_col = _detect_column(header_table, ['LOCATIONCODE', 'LOCATION_CODE', 'LOC_CODE', 'LOCCODE'])
    if not customercode_col or not billdate_col:
        return (None, {})
    customer_code_col = _detect_column(customer_table, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'CUSTCODE', 'CUST_CODE', 'CODE']) if customer_table else None
    customer_name_col = _detect_column(customer_table, ['CUSTOMERNAME', 'CUST_NAME', 'CUSTOMER_NAME', 'NAME']) if customer_table else None
    customer_join = ''
    name_sql = 'NULL AS name'
    order_by = 'code'
    if customer_table and customer_code_col and customer_name_col:
        customer_join = f'LEFT JOIN {customer_table} c ON h.{customercode_col} = c.{customer_code_col}'
        name_sql = f'c.{customer_name_col} AS name'
        order_by = 'name'
    where_clause = f"h.{billdate_col} >= TO_DATE(:date_from, 'YYYY-MM-DD') AND h.{billdate_col} < TO_DATE(:date_to, 'YYYY-MM-DD') + 1"
    params: Dict[str, Any] = {'date_from': date_from, 'date_to': date_to}
    if location_code is not None and locationcode_col:
        where_clause = f'{where_clause} AND h.{locationcode_col} = :location_code'
        params['location_code'] = location_code
    query = f'\n        SELECT DISTINCT\n            h.{customercode_col} AS code,\n            {name_sql}\n        FROM {header_table} h\n        {customer_join}\n        WHERE {where_clause}\n        ORDER BY {order_by}\n    '
    return (query.strip(), params)

def _fetch_customers_list_for_dates(date_from: str, date_to: str, location_code: Optional[int]=None) -> List[Dict[str, Any]]:
    q, p = _temporary_invoices_build_customer_dropdown_sql(date_from, date_to, location_code)
    if not q:
        return []
    _, rows = _fetch_rows(q, p)
    return rows

def _temporary_invoices_build_salesman_dropdown_sql(date_from: str, date_to: str, location_code: Optional[int]=None) -> Tuple[Optional[str], Dict[str, Any]]:
    header_table = _detect_table(['BILLHDR', 'billhdr'])
    if not header_table:
        return (None, {})
    salesman_table = _detect_table(['SALESMAN', 'SALESMANMASTER', 'SALESMEN', 'SALESMANMST'])
    salesmancode_col = _detect_column(header_table, ['SALESMANCODE', 'SALESMAN_CODE', 'SMCODE', 'SM_CODE', 'SALESMANID', 'SALESMAN_ID'])
    billdate_col = _detect_column(header_table, ['BILLDATE', 'BILL_DATE', 'TRANDATE', 'TRANS_DATE', 'TRANSDATE', 'INVDATE', 'INV_DATE', 'DOCDATE', 'DOC_DATE'])
    locationcode_col = _detect_column(header_table, ['LOCATIONCODE', 'LOCATION_CODE', 'LOC_CODE', 'LOCCODE'])
    if not salesmancode_col or not billdate_col:
        return (None, {})
    salesman_code_col = _detect_column(salesman_table, ['SALESMANCODE', 'SALESMAN_CODE', 'SMCODE', 'SM_CODE', 'CODE']) if salesman_table else None
    salesman_name_col = _detect_column(salesman_table, ['SALESMANNAME', 'SALESMAN_NAME', 'NAME']) if salesman_table else None
    salesman_join = ''
    name_sql = 'NULL AS name'
    order_by = 'code'
    if salesman_table and salesman_code_col and salesman_name_col:
        salesman_join = f'LEFT JOIN {salesman_table} s ON h.{salesmancode_col} = s.{salesman_code_col}'
        name_sql = f's.{salesman_name_col} AS name'
        order_by = 'name'
    where_clause = f"h.{billdate_col} >= TO_DATE(:date_from, 'YYYY-MM-DD') AND h.{billdate_col} < TO_DATE(:date_to, 'YYYY-MM-DD') + 1"
    params: Dict[str, Any] = {'date_from': date_from, 'date_to': date_to}
    if location_code is not None and locationcode_col:
        where_clause = f'{where_clause} AND h.{locationcode_col} = :location_code'
        params['location_code'] = location_code
    query = f'\n        SELECT DISTINCT\n            h.{salesmancode_col} AS code,\n            {name_sql}\n        FROM {header_table} h\n        {salesman_join}\n        WHERE {where_clause}\n        ORDER BY {order_by}\n    '
    return (query.strip(), params)

def _fetch_salesmen_list_for_dates(date_from: str, date_to: str, location_code: Optional[int]=None) -> List[Dict[str, Any]]:
    q, p = _temporary_invoices_build_salesman_dropdown_sql(date_from, date_to, location_code)
    if not q:
        return []
    _, rows = _fetch_rows(q, p)
    return rows

def _fetch_salesmen_list_all() -> List[Dict[str, Any]]:
    salesman_table = _detect_table(['SALESMAN', 'SALESMANMASTER', 'SALESMEN', 'SALESMANMST'])
    if not salesman_table:
        return []
    salesman_code_col = _detect_column(salesman_table, ['SALESMANCODE', 'SALESMAN_CODE', 'SMCODE', 'SM_CODE', 'CODE'])
    salesman_name_col = _detect_column(salesman_table, ['SALESMANNAME', 'SALESMAN_NAME', 'NAME'])
    if not salesman_code_col or not salesman_name_col:
        return []
    return _fetch_lookup_list(salesman_table, salesman_code_col, salesman_name_col)

def _fetch_invoice_header_only(billno: str, transaction_date: Any=None, transaction_billdate_override: Any=None) -> Dict[str, Any]:
    """Load invoice header only (no line items). Faster initial Modify Invoice load."""
    header_table = _detect_table(['BILLHDR', 'billhdr'])
    if not header_table:
        return {}
    billno_col = _detect_column(header_table, ['BILLNO', 'BILL_NO'])
    billdate_col = _detect_column(header_table, ['BILLDATE', 'BILL_DATE', 'TRANDATE', 'TRANS_DATE', 'TRANSDATE', 'INVDATE', 'INV_DATE', 'DOCDATE', 'DOC_DATE'])
    customercode_col = _detect_column(header_table, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'CUSTCODE', 'CUST_CODE', 'CUSTNO', 'CUST_NO', 'CUSTOMERID', 'CUSTOMER_ID'])
    salesmancode_col = _detect_column(header_table, ['SALESMANCODE', 'SALESMAN_CODE', 'SMCODE', 'SM_CODE', 'SALESMANID', 'SALESMAN_ID'])
    netbill_col = _detect_column(header_table, ['NETBILLAMOUNT', 'NETAMOUNT', 'NETTOTAL', 'NET_TOTAL', 'BILLAMOUNT', 'BILL_AMOUNT'])
    billtype_col = _detect_column(header_table, ['BILLTYPE', 'BILL_TYPE', 'TYPE'])
    locationcode_col = _detect_column(header_table, ['LOCATIONCODE', 'LOCATION_CODE', 'LOC_CODE', 'LOCCODE'])
    orderno_col = _detect_column(header_table, ['ORDERNO', 'ORDER_NO', 'orderno'])
    if not billno_col:
        return {}
    customer_table = _detect_table(['CUSTOMER', 'CUSTOMERS', 'customers', 'customer'])
    salesman_table = _detect_table(['SALESMAN', 'SALESMANMASTER', 'SALESMEN', 'SALESMANMST'])
    customer_code_col = _detect_column(customer_table, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'CUSTCODE', 'CUST_CODE', 'CODE']) if customer_table else None
    customer_name_col = _detect_column(customer_table, ['CUSTOMERNAME', 'CUST_NAME', 'CUSTOMER_NAME', 'NAME']) if customer_table else None
    salesman_code_col = _detect_column(salesman_table, ['SALESMANCODE', 'SALESMAN_CODE', 'SMCODE', 'SM_CODE', 'CODE']) if salesman_table else None
    salesman_name_col = _detect_column(salesman_table, ['SALESMANNAME', 'SALESMAN_NAME', 'NAME']) if salesman_table else None
    customer_join = ''
    customer_name_sql = 'NULL AS customername'
    if customer_table and customercode_col and customer_code_col and customer_name_col:
        customer_join = f'LEFT JOIN {customer_table} c ON h.{customercode_col} = c.{customer_code_col}'
        customer_name_sql = f'c.{customer_name_col} AS customername'
    salesman_join = ''
    salesman_name_sql = 'NULL AS salesmanname'
    if salesman_table and salesmancode_col and salesman_code_col and salesman_name_col:
        salesman_join = f'LEFT JOIN {salesman_table} s ON h.{salesmancode_col} = s.{salesman_code_col}'
        salesman_name_sql = f's.{salesman_name_col} AS salesmanname'
    where_parts = [f'h.{billno_col} = :billno']
    params = {'billno': billno}
    if transaction_date and billdate_col:
        where_parts.append(f"TRUNC(h.{billdate_col}) = TRUNC(TO_DATE(:transaction_date, 'YYYY-MM-DD'))")
        if hasattr(transaction_date, 'strftime'):
            params['transaction_date'] = transaction_date.strftime('%Y-%m-%d')
        else:
            params['transaction_date'] = str(transaction_date)
    header_query = f"\n        SELECT\n            h.{billno_col} AS billno,\n            {(f'h.{billdate_col} AS billdate' if billdate_col else 'NULL AS billdate')},\n            {(f'h.{customercode_col} AS customercode' if customercode_col else 'NULL AS customercode')},\n            {customer_name_sql},\n            {(f'h.{salesmancode_col} AS salesmancode' if salesmancode_col else 'NULL AS salesmancode')},\n            {salesman_name_sql},\n            {(f'h.{netbill_col} AS netbillamount' if netbill_col else 'NULL AS netbillamount')},\n            {(f'h.{billtype_col} AS billtype' if billtype_col else 'NULL AS billtype')},\n            {(f'h.{locationcode_col} AS locationcode' if locationcode_col else 'NULL AS locationcode')},\n            {(f'h.{orderno_col} AS orderno' if orderno_col else 'NULL AS orderno')}\n        FROM {header_table} h\n        {customer_join}\n        {salesman_join}\n        WHERE {' AND '.join(where_parts)}\n    "
    _, header_rows = _fetch_rows(header_query, params)
    header = header_rows[0] if header_rows else {}
    if header and transaction_billdate_override:
        header['billdate'] = transaction_billdate_override
    elif header and (not transaction_billdate_override):
        location_code = None
        if 'locationcode' in header and header.get('locationcode'):
            try:
                location_code = int(header['locationcode'])
            except (ValueError, TypeError):
                pass
        if not location_code and session.get('location_code'):
            try:
                location_code = int(session['location_code'])
            except (ValueError, TypeError):
                pass
        if location_code:
            transaction_billdate = _get_transaction_billdate(location_code)
            if transaction_billdate:
                header['billdate'] = transaction_billdate
    return header

def _fetch_invoice_items_only(billno: str) -> List[Dict[str, Any]]:
    """Line items for a bill (detail + optional ITEMMASTER join)."""
    detail_table = _detect_table(['BILLDTL', 'billdtl'])
    item_table = _detect_table(['ITEMMASTER', 'itemmaster'])
    if not detail_table:
        return []
    detail_billno_col = _detect_column(detail_table, ['BILLNO', 'BILL_NO'])
    itemcode_col = _detect_column(detail_table, ['ITEMCODE', 'ITEM_CODE', 'ITEMID', 'ITEM_ID', 'ITEMNO', 'ITEM_NO'])
    qty_col = _detect_column(detail_table, ['QTY', 'QUANTITY', 'BILLQTY', 'BILL_QTY', 'QTY1', 'QTY_1', 'QTY2', 'QTY_2'])
    rate_col = _detect_column(detail_table, ['RATE', 'SELLRATE', 'PRICE', 'UNITPRICE', 'UNIT_PRICE', 'UNITRATE', 'UNIT_RATE'])
    amount_col = _detect_column(detail_table, ['AMOUNT', 'LINEAMOUNT', 'LINE_AMOUNT', 'NETAMOUNT', 'NET_AMOUNT', 'TOTALAMOUNT', 'TOTAL_AMOUNT', 'GROSSAMOUNT', 'GROSS_AMOUNT'])
    uom_col = _detect_column(detail_table, ['UOM', 'UNIT', 'UNITCODE', 'UOMCODE', 'UOM_CODE', 'UNIT_CODE', 'UNITOFMEASUREMENT'])
    if not detail_billno_col or not itemcode_col:
        return []
    item_code_col = _detect_column(item_table, ['ITEMCODE', 'ITEM_CODE', 'ITEMID', 'ITEM_ID', 'ITEMNO', 'ITEM_NO']) if item_table else None
    item_name_col = _detect_column(item_table, ['ITEMNAME', 'ITEM_NAME', 'DESCRIPTION', 'ITEMDESC', 'ITEM_DESC']) if item_table else None
    item_uom_col = _detect_column(item_table, ['UOM', 'UNIT', 'UNITCODE', 'UOMCODE', 'UOM_CODE', 'UNIT_CODE', 'UNITOFMEASUREMENT']) if item_table else None
    item_join = ''
    item_name_sql = 'NULL AS itemname'
    item_uom_sql = 'NULL AS uom'
    if item_table and item_code_col:
        item_join = f'LEFT JOIN {item_table} i ON d.{itemcode_col} = i.{item_code_col}'
        if item_name_col:
            item_name_sql = f'i.{item_name_col} AS itemname'
        if item_uom_col:
            item_uom_sql = f'i.{item_uom_col} AS uom'
    uom_sql = f'd.{uom_col} AS uom' if uom_col else item_uom_sql
    detail_query = f"\n        SELECT\n            d.{itemcode_col} AS itemcode,\n            {item_name_sql},\n            {uom_sql},\n            {(f'd.{qty_col} AS quantity' if qty_col else 'NULL AS quantity')},\n            {(f'd.{rate_col} AS rate' if rate_col else 'NULL AS rate')},\n            {(f'd.{amount_col} AS amount' if amount_col else 'NULL AS amount')}\n        FROM {detail_table} d\n        {item_join}\n        WHERE d.{detail_billno_col} = :billno\n        ORDER BY d.{itemcode_col}\n    "
    _, item_rows = _fetch_rows(detail_query, {'billno': billno})
    if item_rows:
        for row in item_rows:
            if row.get('amount') is None and row.get('quantity') is not None and (row.get('rate') is not None):
                try:
                    row['amount'] = float(row['quantity']) * float(row['rate'])
                except Exception:
                    pass
    return item_rows

def _fetch_invoice_header_and_items(billno: str, transaction_date: Any=None, transaction_billdate_override: Any=None) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Header + line items (legacy / PDF / detail API). Requires both header and detail tables."""
    header_table = _detect_table(['BILLHDR', 'billhdr'])
    detail_table = _detect_table(['BILLDTL', 'billdtl'])
    if not header_table or not detail_table:
        return ({}, [])
    header = _fetch_invoice_header_only(billno, transaction_date, transaction_billdate_override)
    items = _fetch_invoice_items_only(billno)
    return (header, items)

def _lookup_customer_name(customercode: str) -> str:
    if not customercode:
        return ''
    customer_table = _detect_table(['CUSTOMER', 'CUSTOMERS', 'customers', 'customer'])
    if not customer_table:
        return ''
    customer_code_col = _detect_column(customer_table, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'CUSTCODE', 'CUST_CODE', 'CODE'])
    customer_name_col = _detect_column(customer_table, ['CUSTOMERNAME', 'CUST_NAME', 'CUSTOMER_NAME', 'NAME'])
    if not customer_code_col or not customer_name_col:
        return ''
    query = f'\n        SELECT {customer_name_col} AS customername\n        FROM {customer_table}\n        WHERE {customer_code_col} = :customercode\n    '
    _, rows = _fetch_rows(query, {'customercode': customercode})
    if rows and rows[0].get('customername'):
        return str(rows[0]['customername']).strip()
    return ''

def _lookup_salesman_name(salesmancode: str) -> str:
    if not salesmancode:
        return ''
    salesman_table = _detect_table(['SALESMAN', 'SALESMANMASTER', 'SALESMEN', 'SALESMANMST'])
    if not salesman_table:
        return ''
    salesman_code_col = _detect_column(salesman_table, ['SALESMANCODE', 'SALESMAN_CODE', 'SMCODE', 'SM_CODE', 'CODE'])
    salesman_name_col = _detect_column(salesman_table, ['SALESMANNAME', 'SALESMAN_NAME', 'NAME'])
    if not salesman_code_col or not salesman_name_col:
        return ''
    query = f'\n        SELECT {salesman_name_col} AS salesmanname\n        FROM {salesman_table}\n        WHERE {salesman_code_col} = :salesmancode\n    '
    _, rows = _fetch_rows(query, {'salesmancode': salesmancode})
    if rows and rows[0].get('salesmanname'):
        return str(rows[0]['salesmanname']).strip()
    return ''

def _get_entryno_for_billno(header_table: str, billno_col: str, billno: str) -> str:
    entryno_col = _detect_column(header_table, ['ENTRYNO', 'ENTRY_NO', 'ENTRYNUMBER', 'ENTRY_NUM', 'ENTRYNUM'])
    if not entryno_col:
        return ''
    query = f'\n        SELECT {entryno_col} AS entryno\n        FROM {header_table}\n        WHERE {billno_col} = :billno\n    '
    _, rows = _fetch_rows(query, {'billno': billno})
    if rows and rows[0].get('entryno') is not None:
        return str(rows[0]['entryno']).strip()
    return ''

def _get_transaction_billdate(location_code: Any) -> Any:
    """Get billdate from TBLTRANSACTIONDATE where LocationCode = location_code, openflag='O', transactioncode=2"""
    if not location_code:
        return None
    transaction_table = _detect_table(['TBLTRANSACTIONDATE', 'tbltransactiondate', 'TRANSACTIONDATE', 'transactiondate'])
    if not transaction_table:
        return None
    locationcode_col = _detect_column(transaction_table, ['LOCATIONCODE', 'LOCATION_CODE', 'LOC_CODE', 'LOCCODE'])
    dateofopen_col = _detect_column(transaction_table, ['DATEOFOPEN', 'DATE_OF_OPEN', 'OPEN_DATE', 'OPENDATE'])
    openflag_col = _detect_column(transaction_table, ['OPENFLAG', 'OPEN_FLAG', 'FLAG', 'STATUS'])
    transactioncode_col = _detect_column(transaction_table, ['TRANSACTIONCODE', 'TRANSACTION_CODE', 'TRANSCODE', 'TRANS_CODE'])
    if not locationcode_col or not dateofopen_col or (not openflag_col) or (not transactioncode_col):
        return None
    try:
        location_code_int = int(location_code) if location_code else None
    except (ValueError, TypeError):
        return None
    if location_code_int is None:
        return None
    query = f"\n        SELECT {dateofopen_col} AS dateofopen\n        FROM {transaction_table}\n        WHERE {locationcode_col} = :location_code\n          AND {openflag_col} = 'O'\n          AND {transactioncode_col} = 2\n    "
    try:
        result = _get_scalar(query, {'location_code': location_code_int})
        return result
    except Exception as e:
        print(f'[DEBUG _get_transaction_billdate] Error: {e}')
        return None

def _update_invoice_header(
    billno: str,
    salesmancode: str,
    customercode: str,
    customername: str,
    salesmanname: str,
    billtype: str,
    orderno: str = '',
    conn: Optional[Any] = None,
) -> None:
    header_table = _detect_table(['BILLHDR', 'billhdr'])
    history_table = _detect_table(['BILLHDRHISTORY', 'billhdrhistory', 'BILL_HDR_HISTORY'])
    header_tables: List[str] = []
    if header_table:
        header_tables.append(header_table)
    if history_table and history_table not in header_tables:
        header_tables.append(history_table)

    def _run(connection: Any) -> None:
        with connection.cursor() as cur:
            for table_name in header_tables:
                if not table_name:
                    continue
                billno_col = _detect_column(table_name, ['BILLNO', 'BILL_NO', 'billno'])
                if not billno_col:
                    continue
                set_parts = []
                params: Dict[str, Any] = {'billno': billno}
                salesmancode_col = _detect_column(table_name, ['SALESMANCODE', 'SALESMAN_CODE', 'SMCODE', 'SM_CODE'])
                customercode_col = _detect_column(table_name, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'CUSTCODE', 'CUST_CODE'])
                customername_col = _detect_column(table_name, ['CUSTOMERNAME', 'CUST_NAME', 'CUSTOMER_NAME', 'NAME'])
                billtype_col = _detect_column(table_name, ['BILLTYPE', 'BILL_TYPE', 'TYPE'])
                orderno_col = _detect_column(table_name, ['ORDERNO', 'ORDER_NO', 'orderno'])
                if salesmancode and salesmancode_col:
                    set_parts.append(f'{salesmancode_col} = :salesmancode')
                    params['salesmancode'] = salesmancode
                if customercode and customercode_col:
                    set_parts.append(f'{customercode_col} = :customercode')
                    params['customercode'] = customercode
                if customername and customername_col:
                    set_parts.append(f'{customername_col} = :customername')
                    params['customername'] = customername
                if billtype and billtype_col:
                    set_parts.append(f'{billtype_col} = :billtype')
                    params['billtype'] = billtype
                if orderno_col and orderno is not None:
                    set_parts.append(f'{orderno_col} = :orderno')
                    params['orderno'] = orderno
                if set_parts:
                    query = f"\n                        UPDATE {table_name}\n                        SET {', '.join(set_parts)}\n                        WHERE {billno_col} = :billno\n                    "
                    cur.execute(query, params)
        if conn is None:
            connection.commit()
    if conn is not None:
        _run(conn)
    else:
        with _get_connection() as connection:
            _run(connection)
            connection.commit()

def _ti_allowed_bill_types(subset: Optional[List[str]]) -> List[str]:
    """Normalize bill type letters for WHERE IN — default Cash/Credit/Temporary."""
    allowed = ('C', 'R', 'T')
    if not subset:
        return list(allowed)
    out: List[str] = []
    for raw in subset:
        ch = str(raw or '').strip().upper()[:1]
        if ch in allowed and ch not in out:
            out.append(ch)
    return out if out else list(allowed)

def _ti_sql_like_pattern(fragment: str) -> str:
    """Build LIKE pattern with escapes for Oracle (use with ESCAPE '\\')."""
    s = (fragment or '').strip()
    if not s:
        return ''
    parts: List[str] = []
    for ch in s:
        if ch == '\\':
            parts.append('\\\\')
        elif ch == '%':
            parts.append('\\%')
        elif ch == '_':
            parts.append('\\_')
        else:
            parts.append(ch)
    return '%' + ''.join(parts) + '%'

def _build_filters(billtype_col: str, billdate_col: str, customercode_col: str, salesmancode_col: str, customer_code: str, salesman_code: str, date_from: str, date_to: str, bill_types: Optional[List[str]]=None) -> Tuple[str, Dict[str, Any]]:
    bt_list = _ti_allowed_bill_types(bill_types)
    in_list = ','.join((f"'{x}'" for x in bt_list))
    where_parts = [f'h.{billtype_col} IN ({in_list})']
    params: Dict[str, Any] = {}
    if customer_code:
        where_parts.append(f'h.{customercode_col} = :customer_code')
        params['customer_code'] = customer_code
    if salesmancode_col and salesman_code:
        where_parts.append(f'h.{salesmancode_col} = :salesman_code')
        params['salesman_code'] = salesman_code
    if date_from and billdate_col:
        where_parts.append(f"h.{billdate_col} >= TO_DATE(:date_from, 'YYYY-MM-DD')")
        params['date_from'] = date_from
    if date_to and billdate_col:
        where_parts.append(f"h.{billdate_col} < TO_DATE(:date_to, 'YYYY-MM-DD') + 1")
        params['date_to'] = date_to
    return (' AND '.join(where_parts), params)

def _temporary_invoices_build_main_list_sql(customer_code: str, salesman_code: str, date_from: str, date_to: str, location_code: Optional[int]=None, *, billno_search: str='', orderno_search: str='', bill_types: Optional[List[str]]=None, created_by_search: str='', net_min: Optional[str]=None, net_max: Optional[str]=None, txn_kind: str='', include_slno_row_number: bool=True) -> Tuple[Optional[str], Dict[str, Any]]:
    """Build the main Temporary Invoices grid SELECT (same as list/filter page). Returns (sql, binds) or (None, {})."""
    header_table = _detect_table(['BILLHDR', 'billhdr'])
    if not header_table:
        print('[DEBUG temporary_invoices] BILLHDR not found')
        return (None, {})
    customer_table = _detect_table(['CUSTOMER', 'CUSTOMERS', 'customers', 'customer'])
    billno_col = _detect_column(header_table, ['BILLNO', 'BILL_NO'])
    billdate_col = _detect_column(header_table, ['BILLDATE', 'BILL_DATE', 'TRANDATE', 'TRANS_DATE', 'TRANSDATE', 'INVDATE', 'INV_DATE', 'DOCDATE', 'DOC_DATE'])
    customercode_col = _detect_column(header_table, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'CUSTCODE', 'CUST_CODE', 'CUSTNO', 'CUST_NO', 'CUSTOMERID', 'CUSTOMER_ID'])
    salesmancode_col = _detect_column(header_table, ['SALESMANCODE', 'SALESMAN_CODE', 'SMCODE', 'SM_CODE', 'SALESMANID', 'SALESMAN_ID'])
    orderno_col = _detect_column(header_table, ['ORDERNO', 'ORDER_NO', 'orderno'])
    netbill_col = _detect_column(header_table, ['NETBILLAMOUNT', 'NETAMOUNT', 'NETTOTAL', 'NET_TOTAL', 'BILLAMOUNT', 'BILL_AMOUNT'])
    billtype_col = _detect_column(header_table, ['BILLTYPE', 'BILL_TYPE', 'TYPE'])
    locationcode_col = _detect_column(header_table, ['LOCATIONCODE', 'LOCATION_CODE', 'LOC_CODE', 'LOCCODE'])
    createdby_col = _detect_column(header_table, ['CREATEDBY', 'CREATED_BY', 'createdby', 'created_by', 'USERID', 'USERNAME', 'ENTEREDBY', 'ENTERED_BY'])
    if not billno_col or not billdate_col or (not customercode_col) or (not netbill_col) or (not billtype_col):
        print('[DEBUG temporary_invoices] Required columns missing in bill header table')
        return (None, {})
    customer_code_col = _detect_column(customer_table, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'CUSTCODE', 'CUST_CODE', 'CODE']) if customer_table else None
    customer_name_col = _detect_column(customer_table, ['CUSTOMERNAME', 'CUST_NAME', 'CUSTOMER_NAME', 'NAME']) if customer_table else None
    customer_loc_col = _detect_column(customer_table, ['LOCATIONCODE', 'LOCATION_CODE', 'LOCCODE', 'LOC_CODE']) if customer_table else None
    customer_join = ''
    customer_name_sql = 'NULL AS customername'
    orderno_sql = 'NULL AS orderno'
    if customer_table and customer_code_col and customer_name_col:
        join_on_parts = [f'h.{customercode_col} = c.{customer_code_col}']
        if locationcode_col and customer_loc_col:
            join_on_parts.append(f'h.{locationcode_col} = c.{customer_loc_col}')
        customer_join = f"LEFT JOIN {customer_table} c ON {' AND '.join(join_on_parts)}"
        customer_name_sql = f'c.{customer_name_col} AS customername'
    if orderno_col:
        orderno_sql = f'h.{orderno_col} AS orderno'
    where_clause, params = _build_filters(billtype_col=billtype_col, billdate_col=billdate_col, customercode_col=customercode_col, salesmancode_col=salesmancode_col or '', customer_code=customer_code, salesman_code=salesman_code, date_from=date_from, date_to=date_to, bill_types=bill_types)
    if location_code is not None and locationcode_col:
        where_clause = f'({where_clause}) AND h.{locationcode_col} = :location_code'
        params['location_code'] = location_code
    bn_pat = _ti_sql_like_pattern(billno_search)
    if bn_pat and billno_col:
        where_clause = f"({where_clause}) AND UPPER(TRIM(TO_CHAR(h.{billno_col}))) LIKE UPPER(:ti_billno_pat) ESCAPE '\\'"
        params['ti_billno_pat'] = bn_pat
    on_pat = _ti_sql_like_pattern(orderno_search)
    if on_pat and orderno_col:
        where_clause = f"({where_clause}) AND UPPER(TRIM(TO_CHAR(h.{orderno_col}))) LIKE UPPER(:ti_orderno_pat) ESCAPE '\\'"
        params['ti_orderno_pat'] = on_pat
    cb_pat = _ti_sql_like_pattern(created_by_search)
    if cb_pat and createdby_col:
        where_clause = f"({where_clause}) AND UPPER(TRIM(TO_CHAR(h.{createdby_col}))) LIKE UPPER(:ti_created_pat) ESCAPE '\\'"
        params['ti_created_pat'] = cb_pat
    if netbill_col:
        tk = (txn_kind or '').strip().lower()
        if tk in ('sale', 'sales', 's'):
            tk = 'sale'
        elif tk in ('salesreturn', 'sales_return', 'return', 'sr', 'r'):
            tk = 'salesreturn'
        else:
            tk = 'all'
        if tk == 'sale':
            where_clause = f'({where_clause}) AND NVL(h.{netbill_col}, 0) > 0'
        elif tk == 'salesreturn':
            where_clause = f'({where_clause}) AND NVL(h.{netbill_col}, 0) < 0'
        if net_min is not None and str(net_min).strip() != '':
            try:
                params['ti_net_min'] = Decimal(str(net_min).strip().replace(',', ''))
                where_clause = f'({where_clause}) AND h.{netbill_col} >= :ti_net_min'
            except Exception:
                pass
        if net_max is not None and str(net_max).strip() != '':
            try:
                params['ti_net_max'] = Decimal(str(net_max).strip().replace(',', ''))
                where_clause = f'({where_clause}) AND h.{netbill_col} <= :ti_net_max'
            except Exception:
                pass
    slno_select = f'ROW_NUMBER() OVER (ORDER BY h.{billno_col} DESC) AS slno' if include_slno_row_number else 'CAST(NULL AS NUMBER) AS slno'
    query = f"\n        SELECT\n            {slno_select},\n            h.{billno_col} AS billno,\n            h.{billdate_col} AS billdate,\n            h.{customercode_col} AS customercode,\n            {customer_name_sql},\n            {orderno_sql},\n            {(f'h.{createdby_col} AS createdby' if createdby_col else 'NULL AS createdby')},\n            h.{netbill_col} AS netbillamount,\n            h.{billtype_col} AS billtype\n        FROM {header_table} h\n        {customer_join}\n        WHERE {where_clause}\n        ORDER BY h.{billno_col} DESC\n    "
    return (query.strip(), params)
_TI_DEFAULT_PER_PAGE = 500
_TI_MIN_PER_PAGE = 50
_TI_MAX_PER_PAGE = 2000

def _fetch_temporary_invoices_page(customer_code: str, salesman_code: str, date_from: str, date_to: str, location_code: Optional[int]=None, *, page: int, per_page: int, billno_search: str='', orderno_search: str='', bill_types: Optional[List[str]]=None, created_by_search: str='', net_min: Optional[str]=None, net_max: Optional[str]=None, txn_kind: str='') -> Tuple[List[Dict[str, Any]], bool]:
    """Fetch one page of invoices (Oracle ROWNUM). Omits window ROW_NUMBER on inner query for speed."""
    inner_sql, params = _temporary_invoices_build_main_list_sql(customer_code, salesman_code, date_from, date_to, location_code, billno_search=billno_search, orderno_search=orderno_search, bill_types=bill_types, created_by_search=created_by_search, net_min=net_min, net_max=net_max, txn_kind=txn_kind, include_slno_row_number=False)
    if not inner_sql:
        return ([], False)
    page_i = max(1, int(page))
    per_i = max(_TI_MIN_PER_PAGE, min(_TI_MAX_PER_PAGE, int(per_page)))
    lo = (page_i - 1) * per_i
    hi = page_i * per_i + 1
    p = dict(params)
    p['ti_row_lo'] = lo
    p['ti_row_hi'] = hi
    wrapped = f'SELECT * FROM ( SELECT ti_inner.*, ROWNUM AS ti_rnum FROM ( {inner_sql} ) ti_inner WHERE ROWNUM <= :ti_row_hi) WHERE ti_rnum > :ti_row_lo'
    _, rows = _fetch_rows(wrapped, p)
    has_more = len(rows) > per_i
    if has_more:
        rows = rows[:per_i]
    for r in rows:
        r.pop('ti_rnum', None)
    return (rows, has_more)

def _temporary_invoices_list_query_params(*, customer_code: str, salesman_code: str, date_from: str, date_to: str, billno_search: str, orderno_search: str, bill_type_q: str, created_by_search: str, net_min: str, net_max: str, per_page: int, page: Optional[int]=None, txn_kind: str='') -> Dict[str, str]:
    q: Dict[str, str] = {}
    if customer_code:
        q['customercode'] = customer_code
    if salesman_code:
        q['salesmancode'] = salesman_code
    if date_from:
        q['date_from'] = date_from
    if date_to:
        q['date_to'] = date_to
    if billno_search:
        q['billno'] = billno_search
    if orderno_search:
        q['orderno'] = orderno_search
    if bill_type_q in ('C', 'R', 'T'):
        q['bill_type'] = bill_type_q
    if created_by_search:
        q['created_by'] = created_by_search
    if net_min:
        q['net_min'] = net_min
    if net_max:
        q['net_max'] = net_max
    tk = (txn_kind or '').strip().lower()
    if tk in ('sale', 'salesreturn'):
        q['txn_kind'] = tk
    q['per_page'] = str(per_page)
    if page is not None:
        q['page'] = str(page)
    return q
_ANALYSIS_ROW_LIMIT = 2500
_ANALYSIS_MAX_COLUMNS = 48
_ANALYSIS_MAX_EXTRA_FILTERS = 24
_ALLOWED_ANALYSIS_FILTER_OPS = frozenset({'=', '!=', '<>', '>', '<', '>=', '<=', 'LIKE', 'NOT LIKE', 'IN', 'IS NULL', 'IS NOT NULL'})
_SKIP_ANALYSIS_SQL_TYPES = frozenset({'LONG', 'LONG RAW', 'BLOB', 'CLOB', 'NCLOB', 'BFILE', 'XMLTYPE'})
_SA_ANALYSIS_SRC_TAB = 'SA_ANALYSIS_SRC'
_SA_ANALYSIS_COL_TAB = 'SA_ANALYSIS_COL'
_SA_ANALYSIS_CALC_TAB = 'SA_ANALYSIS_CALC'
_SA_CFG_ROLE_KEYS = ('hdr', 'dtl', 'im', 'cust', 'sch')
_SA_ROLE_TO_SQL_ALIAS = {'hdr': 'h', 'dtl': 'd', 'im': 'im', 'cust': 'cust', 'sch_hdr': 'tisch_hdr', 'sch_cust': 'tisch_cust'}
_SA_SQL_ALIAS_TO_ROLE = {'h': 'hdr', 'd': 'dtl', 'im': 'im', 'cust': 'cust', 'tisch_hdr': 'sch_hdr', 'tisch_cust': 'sch_cust'}
_SA_BODY_COLUMN_ROLES = frozenset({'hdr', 'dtl', 'im', 'cust', 'sch_hdr', 'sch_cust'})
_sa_config_tables_ready = False

def _sa_analysis_col_physical_columns() -> Set[str]:
    """Upper-case column names on SA_ANALYSIS_COL (legacy tables may omit DISPLAY_LABEL / SORT_ORD)."""
    try:
        if not _table_exists(_SA_ANALYSIS_COL_TAB):
            return set()
        return {str(c).upper() for c in _get_table_columns(_SA_ANALYSIS_COL_TAB) or []}
    except Exception:
        return set()

def _sa_insert_analysis_col_row(cur: Any, phy: Set[str], rk: str, cn: str, display_label: Optional[str], sort_ord: int) -> None:
    """INSERT selected column row; physical cols may be legacy (ROLE_KEY, COLUMN_NAME only)."""
    cols_ins = ['ROLE_KEY', 'COLUMN_NAME']
    ph_parts = [':r', ':c']
    params: Dict[str, Any] = {'r': rk, 'c': cn}
    if 'DISPLAY_LABEL' in phy:
        cols_ins.append('DISPLAY_LABEL')
        ph_parts.append(':l')
        params['l'] = display_label if display_label else None
    if 'SORT_ORD' in phy:
        cols_ins.append('SORT_ORD')
        ph_parts.append(':s')
        params['s'] = sort_ord
    cur.execute(f"INSERT INTO {_SA_ANALYSIS_COL_TAB} ({', '.join(cols_ins)}) VALUES ({', '.join(ph_parts)})", params)

def _ensure_sa_analysis_config_tables() -> None:
    """Create SA_ANALYSIS_SRC / SA_ANALYSIS_COL on tenant DB when missing (stores saved configuration)."""
    global _sa_config_tables_ready
    if _sa_config_tables_ready:
        _ensure_sa_analysis_calc_table()
        return
    try:
        if _table_exists(_SA_ANALYSIS_SRC_TAB) and _table_exists(_SA_ANALYSIS_COL_TAB):
            _sa_config_tables_ready = True
            _ensure_sa_analysis_calc_table()
            return
    except Exception:
        pass
    ddl_src = f'\n        CREATE TABLE {_SA_ANALYSIS_SRC_TAB} (\n            ROLE_KEY VARCHAR2(32) PRIMARY KEY,\n            OBJECT_NAME VARCHAR2(260),\n            OBJECT_KIND VARCHAR2(10)\n        )\n    '
    ddl_col = f'\n        CREATE TABLE {_SA_ANALYSIS_COL_TAB} (\n            ROLE_KEY VARCHAR2(32) NOT NULL,\n            COLUMN_NAME VARCHAR2(260) NOT NULL,\n            DISPLAY_LABEL VARCHAR2(512),\n            SORT_ORD NUMBER DEFAULT 0,\n            CONSTRAINT SA_ANALYSIS_COL_PK PRIMARY KEY (ROLE_KEY, COLUMN_NAME)\n        )\n    '
    try:
        with _get_connection() as conn:
            cur = conn.cursor()
            try:
                cur.execute(ddl_src)
            except Exception:
                pass
            try:
                cur.execute(ddl_col)
            except Exception:
                pass
            conn.commit()
        _TABLE_COLUMNS_CACHE.pop(_SA_ANALYSIS_SRC_TAB.upper(), None)
        _TABLE_COLUMNS_CACHE.pop(_SA_ANALYSIS_COL_TAB.upper(), None)
        _sa_config_tables_ready = True
    except Exception as exc:
        print(f'[temporary_invoices] SA analysis config DDL skipped: {exc}')
    _ensure_sa_analysis_calc_table()

def _ensure_sa_analysis_calc_table() -> None:
    """Create SA_ANALYSIS_CALC when missing."""
    try:
        if _table_exists(_SA_ANALYSIS_CALC_TAB):
            return
    except Exception:
        return
    ddl_calc = f'\n        CREATE TABLE {_SA_ANALYSIS_CALC_TAB} (\n            CALC_KEY VARCHAR2(64) PRIMARY KEY,\n            SORT_ORD NUMBER DEFAULT 0,\n            OUTPUT_ALIAS VARCHAR2(128),\n            EXPRESSION VARCHAR2(4000) NOT NULL\n        )\n    '
    try:
        with _get_connection() as conn:
            cur = conn.cursor()
            try:
                cur.execute(ddl_calc)
            except Exception:
                pass
            conn.commit()
        _TABLE_COLUMNS_CACHE.pop(_SA_ANALYSIS_CALC_TAB.upper(), None)
    except Exception as exc:
        print(f'[temporary_invoices] SA_ANALYSIS_CALC DDL skipped: {exc}')

def _sa_fetch_sa_analysis_col_rows() -> List[Dict[str, Any]]:
    """Rows from SA_ANALYSIS_COL ordered for UI / catalog."""
    _ensure_sa_analysis_config_tables()
    names = _sa_analysis_col_physical_columns()
    if not names or 'ROLE_KEY' not in names or 'COLUMN_NAME' not in names:
        return []
    sel = ['ROLE_KEY', 'COLUMN_NAME']
    if 'DISPLAY_LABEL' in names:
        sel.append('DISPLAY_LABEL')
    if 'SORT_ORD' in names:
        sel.append('SORT_ORD')
    order = 'ORDER BY SORT_ORD, COLUMN_NAME' if 'SORT_ORD' in names else 'ORDER BY COLUMN_NAME'
    try:
        _, rows = _fetch_rows(f"SELECT {', '.join(sel)} FROM {_SA_ANALYSIS_COL_TAB} {order}", {})
    except Exception:
        return []
    return list(rows or [])

def _sa_fetch_src_overrides() -> Dict[str, Tuple[str, str]]:
    """role_key -> (OBJECT_NAME upper or '', OBJECT_KIND)."""
    _ensure_sa_analysis_config_tables()
    try:
        _, rows = _fetch_rows(f'SELECT ROLE_KEY, OBJECT_NAME, OBJECT_KIND FROM {_SA_ANALYSIS_SRC_TAB}', {})
    except Exception:
        return {}
    out: Dict[str, Tuple[str, str]] = {}
    for r in rows or []:
        rk = str(r.get('role_key') or r.get('ROLE_KEY') or '').strip().lower()
        nm = str(r.get('object_name') or r.get('OBJECT_NAME') or '').strip()
        kd = str(r.get('object_kind') or r.get('OBJECT_KIND') or 'TABLE').strip().upper() or 'TABLE'
        if rk:
            out[rk] = (nm.upper() if nm else '', kd)
    return out

def _sa_fetch_column_allowlist() -> Optional[Dict[str, Set[str]]]:
    """role_key (hdr, dtl, …) -> set of upper column names. None = no restriction."""
    rows = _sa_fetch_sa_analysis_col_rows()
    if not rows:
        return None
    buckets: Dict[str, Set[str]] = {}
    for r in rows:
        role = str(r.get('role_key') or r.get('ROLE_KEY') or '').strip().lower()
        col = str(r.get('column_name') or r.get('COLUMN_NAME') or '').strip()
        if not role or not col:
            continue
        buckets.setdefault(role, set()).add(col.upper())
    return buckets if buckets else None

def _sa_fetch_sa_column_sort_and_labels() -> Tuple[Dict[Tuple[str, str], int], Dict[Tuple[str, str], str]]:
    """(role_lower, col_upper) -> sort_ord / display_label from SA_ANALYSIS_COL."""
    rows = _sa_fetch_sa_analysis_col_rows()
    sort_map: Dict[Tuple[str, str], int] = {}
    label_map: Dict[Tuple[str, str], str] = {}
    for r in rows:
        rk = str(r.get('role_key') or r.get('ROLE_KEY') or '').strip().lower()
        cn = str(r.get('column_name') or r.get('COLUMN_NAME') or '').strip().upper()
        if not rk or not cn:
            continue
        try:
            so = int(r.get('sort_ord') or r.get('SORT_ORD') or 0)
        except Exception:
            so = 0
        sort_map[rk, cn] = so
        lbl = str(r.get('display_label') or r.get('DISPLAY_LABEL') or '').strip()
        if lbl:
            label_map[rk, cn] = lbl
    return (sort_map, label_map)
_SA_CALC_TOKEN_RE = re.compile('@(?P<rk>[a-zA-Z_]+):(?P<cn>[A-Za-z0-9_]+)@')

def _invoice_analysis_role_table(meta: Dict[str, Any], role_key: str) -> str:
    rk = (role_key or '').strip().lower()
    if rk == 'hdr':
        return meta['hdr_tbl']
    if rk == 'dtl':
        return meta['dtl_tbl']
    if rk == 'im':
        return (meta.get('im_tbl') or '').strip()
    if rk == 'cust':
        return (meta.get('customer_tbl') or '').strip()
    if rk in ('sch_hdr', 'sch_cust'):
        return (meta.get('sch_tbl') or '').strip()
    return ''

def _invoice_analysis_resolve_calc_expression_sql(meta: Dict[str, Any], expr_raw: str, allowed_by_role: Optional[Dict[str, Set[str]]]) -> Tuple[Optional[str], Optional[str]]:
    """Turn @role:COL@ tokens into qualified SQL; validate arithmetic shell."""
    if not expr_raw or not str(expr_raw).strip():
        return (None, 'Expression is empty.')
    expr = str(expr_raw).strip()

    def replacer(m):
        rk = (m.group('rk') or '').strip().lower()
        cn_u = (m.group('cn') or '').strip().upper()
        tbl = _invoice_analysis_role_table(meta, rk)
        if not tbl:
            raise ValueError(f'No active join table for role {rk!r}.')
        canon = _invoice_analysis_canonical_column(tbl, cn_u)
        if not canon:
            raise ValueError(f'Unknown column {cn_u!r} for role {rk!r}.')
        if allowed_by_role is not None:
            al = allowed_by_role.get(rk)
            if not al or canon.upper() not in al:
                raise ValueError(f'Column {cn_u!r} is not enabled for role {rk!r}.')
        alias = _SA_ROLE_TO_SQL_ALIAS.get(rk)
        if not alias:
            raise ValueError(f'Unknown role {rk!r}.')
        return f'{alias}.{canon}'
    try:
        sql_frag = _SA_CALC_TOKEN_RE.sub(lambda m: replacer(m), expr)
    except ValueError as exc:
        return (None, str(exc))
    probe = _SA_CALC_TOKEN_RE.sub('1', expr)
    if not re.fullmatch('[0-9+\\-*/().\\s]+', probe):
        return (None, 'Expression may only use numbers, + - * / ( ) and @role:COL@ references.')
    return (sql_frag, None)

def _sa_fetch_calc_entries() -> List[Dict[str, Any]]:
    _ensure_sa_analysis_calc_table()
    try:
        _, rows = _fetch_rows(f'\n            SELECT CALC_KEY, SORT_ORD, OUTPUT_ALIAS, EXPRESSION\n            FROM {_SA_ANALYSIS_CALC_TAB}\n            ORDER BY SORT_ORD, CALC_KEY\n            ', {})
    except Exception:
        return []
    out: List[Dict[str, Any]] = []
    for r in rows or []:
        ck = str(r.get('calc_key') or r.get('CALC_KEY') or '').strip()
        if not ck:
            continue
        try:
            so = int(r.get('sort_ord') or r.get('SORT_ORD') or 0)
        except Exception:
            so = 0
        oa = str(r.get('output_alias') or r.get('OUTPUT_ALIAS') or '').strip()
        ex = str(r.get('expression') or r.get('EXPRESSION') or '').strip()
        out.append({'calc_key': ck, 'sort_ord': so, 'output_alias': oa, 'expression': ex})
    return out

def _invoice_analysis_sanitize_select_alias(raw: str, used: Set[str]) -> str:
    base = re.sub('[^A-Za-z0-9_]', '_', (raw or '').strip())[:26].upper() or 'CALC'
    out = base
    n = 2
    while out in used:
        suffix = f'_{n}'
        out = (base[:26 - len(suffix)] + suffix).upper()
        n += 1
    used.add(out)
    return out

def _invoice_analysis_recompute_secondary_joins(meta: Dict[str, Any]) -> None:
    """Rebuild customer + sales-channel joins from meta table pointers."""
    hdr_tbl = meta['hdr_tbl']
    customercode_col = meta.get('customercode_col') or ''
    locationcode_col = meta.get('locationcode_col') or ''
    customer_table = (meta.get('customer_tbl') or '').strip()
    sch_tbl = (meta.get('sch_tbl') or '').strip()
    cust_code_col = _detect_column(customer_table, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'CUSTCODE', 'CUST_CODE', 'CODE']) if customer_table else None
    cust_loc_col = _detect_column(customer_table, ['LOCATIONCODE', 'LOCATION_CODE', 'LOCCODE', 'LOC_CODE']) if customer_table else None
    customer_join_sql = ''
    if customer_table and cust_code_col and customercode_col:
        join_on_parts = [f'h.{customercode_col} = cust.{cust_code_col}']
        if locationcode_col and cust_loc_col:
            join_on_parts.append(f'h.{locationcode_col} = cust.{cust_loc_col}')
        customer_join_sql = f"LEFT JOIN {customer_table} cust ON {' AND '.join(join_on_parts)}"
    hdr_channel_col = _detect_column(hdr_tbl, ['CHANNELCODE', 'CHANNEL_CODE', 'SALESCHANNELCODE', 'SALES_CHANNEL', 'CHANNEL', 'channel'])
    sch_code = _detect_column(sch_tbl, ['CODE', 'code', 'CHANNELCODE', 'channelcode']) if sch_tbl else None
    sch_desc = _detect_column(sch_tbl, ['DESCRIPTION', 'description', 'NAME', 'name']) if sch_tbl else None
    sch_loc = _detect_column(sch_tbl, ['LOCATIONCODE', 'locationcode']) if sch_tbl else None
    sch_hdr_join_sql = ''
    if sch_tbl and hdr_channel_col and sch_code and sch_desc:
        if sch_loc and locationcode_col:
            sch_hdr_join_sql = f'LEFT JOIN {sch_tbl} tisch_hdr ON tisch_hdr.{sch_loc} = h.{locationcode_col} AND tisch_hdr.{sch_code} = h.{hdr_channel_col}'
        else:
            sch_hdr_join_sql = f'LEFT JOIN {sch_tbl} tisch_hdr ON tisch_hdr.{sch_code} = h.{hdr_channel_col}'
    channel_col_c = _detect_column(customer_table, ['CHANNELCODE', 'channelcode', 'SALESCHANNEL', 'SALESCHANNELCODE', 'SALES_CHANNEL', 'sales_channel']) if customer_table else None
    sch_cust_join_sql = ''
    if customer_join_sql and sch_tbl and channel_col_c and sch_code and sch_desc:
        if sch_loc and cust_loc_col:
            sch_cust_join_sql = f'LEFT JOIN {sch_tbl} tisch_cust ON tisch_cust.{sch_loc} = cust.{cust_loc_col} AND tisch_cust.{sch_code} = cust.{channel_col_c}'
        else:
            sch_cust_join_sql = f'LEFT JOIN {sch_tbl} tisch_cust ON tisch_cust.{sch_code} = cust.{channel_col_c}'
    meta['customer_join_sql'] = customer_join_sql
    meta['sch_hdr_join_sql'] = sch_hdr_join_sql
    meta['sch_cust_join_sql'] = sch_cust_join_sql

def _invoice_analysis_apply_sa_configuration(meta: Dict[str, Any]) -> None:
    """Apply saved table/view overrides (tenant SA_ANALYSIS_*). Invalid overrides are skipped."""
    overrides = _sa_fetch_src_overrides()
    if not overrides:
        return
    hov = overrides.get('hdr', ('', ''))[0]
    if hov and _get_table_columns(hov):
        bn = _detect_column(hov, ['BILLNO', 'BILL_NO'])
        bd = _detect_column(hov, ['BILLDATE', 'BILL_DATE', 'TRANDATE', 'TRANS_DATE', 'TRANSDATE', 'INVDATE', 'INV_DATE', 'DOCDATE', 'DOC_DATE'])
        bt = _detect_column(hov, ['BILLTYPE', 'BILL_TYPE', 'TYPE'])
        cc = _detect_column(hov, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'CUSTCODE', 'CUST_CODE', 'CUSTNO', 'CUST_NO', 'CUSTOMERID', 'CUSTOMER_ID'])
        sm = _detect_column(hov, ['SALESMANCODE', 'SALESMAN_CODE', 'SMCODE', 'SM_CODE', 'SALESMANID', 'SALESMAN_ID'])
        loc = _detect_column(hov, ['LOCATIONCODE', 'LOCATION_CODE', 'LOC_CODE', 'LOCCODE'])
        if bn and bd and bt and cc:
            meta['hdr_tbl'] = hov
            meta['billno_h'] = bn
            meta['billdate_col'] = bd
            meta['billtype_col'] = bt
            meta['customercode_col'] = cc
            meta['salesmancode_col'] = sm or ''
            meta['locationcode_col'] = loc or ''
    dov = overrides.get('dtl', ('', ''))[0]
    if dov and _get_table_columns(dov):
        bnd = _detect_column(dov, ['BILLNO', 'BILL_NO'])
        ic = _detect_column(dov, ['ITEMCODE', 'ITEM_CODE', 'ITMCODE'])
        if bnd and ic:
            meta['dtl_tbl'] = dov
            meta['billno_d'] = bnd
            meta['itemcode_d'] = ic
    iov = overrides.get('im', ('', ''))[0]
    if iov == '-' or iov == 'NONE':
        meta['im_tbl'] = ''
        meta['itemcode_im'] = ''
        meta['loc_im'] = ''
    elif iov and _get_table_columns(iov):
        iim = _detect_column(iov, ['ITEMCODE', 'ITEM_CODE', 'ITMCODE'])
        lim = _detect_column(iov, ['LOCATIONCODE', 'LOCATION_CODE', 'LOC_CODE', 'LOCCODE'])
        if iim:
            meta['im_tbl'] = iov
            meta['itemcode_im'] = iim
            meta['loc_im'] = lim or ''
    cov = overrides.get('cust', ('', ''))[0]
    if cov and _get_table_columns(cov):
        meta['customer_tbl'] = cov
    sov = overrides.get('sch', ('', ''))[0]
    if sov and _get_table_columns(sov):
        meta['sch_tbl'] = sov
    _invoice_analysis_recompute_secondary_joins(meta)

def _analysis_safe_columns(table: str) -> List[str]:
    cols = _get_table_columns(table) or []
    types = _get_table_column_types_with_key(table) or {}
    out: List[str] = []
    for c in cols:
        ct = str(types.get(c, '') or '').upper()
        if ct in _SKIP_ANALYSIS_SQL_TYPES:
            continue
        out.append(c)
    return sorted(out)

def _invoice_analysis_resolve_meta() -> Optional[Dict[str, Any]]:
    hdr_tbl = _detect_table(['BILLHDR', 'billhdr'])
    dtl_tbl = _detect_table(['BILLDTL', 'billdtl'])
    if not hdr_tbl or not dtl_tbl:
        return None
    billno_h = _detect_column(hdr_tbl, ['BILLNO', 'BILL_NO'])
    billno_d = _detect_column(dtl_tbl, ['BILLNO', 'BILL_NO'])
    itemcode_d = _detect_column(dtl_tbl, ['ITEMCODE', 'ITEM_CODE', 'ITMCODE'])
    billdate_col = _detect_column(hdr_tbl, ['BILLDATE', 'BILL_DATE', 'TRANDATE', 'TRANS_DATE', 'TRANSDATE', 'INVDATE', 'INV_DATE', 'DOCDATE', 'DOC_DATE'])
    billtype_col = _detect_column(hdr_tbl, ['BILLTYPE', 'BILL_TYPE', 'TYPE'])
    customercode_col = _detect_column(hdr_tbl, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'CUSTCODE', 'CUST_CODE', 'CUSTNO', 'CUST_NO', 'CUSTOMERID', 'CUSTOMER_ID'])
    salesmancode_col = _detect_column(hdr_tbl, ['SALESMANCODE', 'SALESMAN_CODE', 'SMCODE', 'SM_CODE', 'SALESMANID', 'SALESMAN_ID'])
    locationcode_col = _detect_column(hdr_tbl, ['LOCATIONCODE', 'LOCATION_CODE', 'LOC_CODE', 'LOCCODE'])
    im_tbl = _detect_table(['ITEMMASTERDETAILS', 'itemmasterdetails'])
    itemcode_im = None
    loc_im = None
    if im_tbl:
        itemcode_im = _detect_column(im_tbl, ['ITEMCODE', 'ITEM_CODE', 'ITMCODE'])
        loc_im = _detect_column(im_tbl, ['LOCATIONCODE', 'LOCATION_CODE', 'LOC_CODE', 'LOCCODE'])
    if not billno_h or not billno_d or (not itemcode_d):
        return None
    if not billdate_col or not billtype_col:
        return None
    if not customercode_col:
        return None
    customer_table = _detect_table(['CUSTOMER', 'CUSTOMERS', 'CUSTOMERVIEW', 'customerview', 'customers', 'customer'])
    sch_tbl = _detect_table(['TBLSALESCHANNEL', 'tblsaleschannel'])
    meta: Dict[str, Any] = {'hdr_tbl': hdr_tbl, 'dtl_tbl': dtl_tbl, 'im_tbl': im_tbl if im_tbl and itemcode_im else '', 'billno_h': billno_h, 'billno_d': billno_d, 'itemcode_d': itemcode_d, 'itemcode_im': itemcode_im or '', 'loc_im': loc_im or '', 'billdate_col': billdate_col, 'billtype_col': billtype_col, 'customercode_col': customercode_col or '', 'salesmancode_col': salesmancode_col or '', 'locationcode_col': locationcode_col or '', 'customer_tbl': customer_table or '', 'sch_tbl': sch_tbl or '', 'customer_join_sql': '', 'sch_hdr_join_sql': '', 'sch_cust_join_sql': ''}
    _invoice_analysis_recompute_secondary_joins(meta)
    _invoice_analysis_apply_sa_configuration(meta)
    return meta

def _invoice_analysis_catalog_and_map(meta: Dict[str, Any], allowed_by_role: Optional[Dict[str, Set[str]]]=None) -> Tuple[List[Dict[str, Any]], Dict[str, Tuple[str, str]]]:
    """Return UI groups and server-only map id -> (sql_expr, output_alias)."""
    catalog: Dict[str, Tuple[str, str]] = {}
    used_aliases: set = set()
    sort_map: Dict[Tuple[str, str], int] = {}
    label_map: Dict[Tuple[str, str], str] = {}
    if allowed_by_role is not None:
        sort_map, label_map = _sa_fetch_sa_column_sort_and_labels()

    def add_fields(group_key: str, title: str, sql_alias: str, table_name: str) -> List[Dict[str, str]]:
        fields_ui: List[Dict[str, str]] = []
        if not table_name:
            return fields_ui
        safe_cols = _analysis_safe_columns(table_name)
        if allowed_by_role is not None:
            role_allow = allowed_by_role.get(group_key)
            if not role_allow:
                return fields_ui
            safe_cols = [c for c in safe_cols if c.upper() in role_allow]

        def col_sort_key(c: str) -> Tuple[int, str]:
            ord_i = sort_map.get((group_key, c.upper()), 10 ** 9)
            return (ord_i, c)
        safe_cols = sorted(safe_cols, key=col_sort_key)
        for col in safe_cols:
            cid = f'{group_key}:{col}'
            expr = f'{sql_alias}.{col}'
            base = f'{group_key}_{col}'[:26].upper()
            out_alias = base
            n = 2
            while out_alias in used_aliases:
                suffix = f'_{n}'
                out_alias = (base[:26 - len(suffix)] + suffix).upper()
                n += 1
            used_aliases.add(out_alias)
            catalog[cid] = (expr, out_alias)
            lbl_custom = label_map.get((group_key, col.upper()))
            disp_lbl = lbl_custom if lbl_custom else f'{title}: {col}'
            fields_ui.append({'id': cid, 'label': disp_lbl})
        return fields_ui
    groups: List[Dict[str, Any]] = []
    hdr_fields = add_fields('hdr', 'Header', 'h', meta['hdr_tbl'])
    groups.append({'key': 'hdr', 'title': 'Bill header', 'fields': hdr_fields})
    dtl_fields = add_fields('dtl', 'Detail', 'd', meta['dtl_tbl'])
    groups.append({'key': 'dtl', 'title': 'Bill detail', 'fields': dtl_fields})
    cust_tbl = (meta.get('customer_tbl') or '').strip()
    if cust_tbl and meta.get('customer_join_sql'):
        cust_fields = add_fields('cust', 'Customer', 'cust', cust_tbl)
        groups.append({'key': 'cust', 'title': 'Customer', 'fields': cust_fields})
    sch_tbl = (meta.get('sch_tbl') or '').strip()
    if sch_tbl and meta.get('sch_hdr_join_sql'):
        sch_h_fields = add_fields('sch_hdr', 'Sales channel (header)', 'tisch_hdr', sch_tbl)
        groups.append({'key': 'sch_hdr', 'title': 'TBLSALESCHANNEL (header)', 'fields': sch_h_fields})
    if sch_tbl and meta.get('sch_cust_join_sql'):
        sch_c_fields = add_fields('sch_cust', 'Sales channel (customer)', 'tisch_cust', sch_tbl)
        groups.append({'key': 'sch_cust', 'title': 'TBLSALESCHANNEL (customer)', 'fields': sch_c_fields})
    im_tbl = meta.get('im_tbl') or ''
    if im_tbl:
        im_fields = add_fields('im', 'Item master', 'im', im_tbl)
        groups.append({'key': 'im', 'title': 'ITEMMASTERDETAILS', 'fields': im_fields})
    calc_entries = _sa_fetch_calc_entries()
    calc_fields: List[Dict[str, str]] = []
    for ent in sorted(calc_entries, key=lambda x: (x['sort_ord'], x['calc_key'])):
        sql_frag, err = _invoice_analysis_resolve_calc_expression_sql(meta, ent.get('expression') or '', allowed_by_role)
        if err or not sql_frag:
            continue
        ck = ent['calc_key']
        cid = f'calc:{ck}'
        out_alias = _invoice_analysis_sanitize_select_alias(ent.get('output_alias') or 'CALC', used_aliases)
        catalog[cid] = (sql_frag, out_alias)
        calc_fields.append({'id': cid, 'label': f"Calc · {(ent.get('output_alias') or out_alias).strip()}"})
    if calc_fields:
        groups.append({'key': 'calc', 'title': 'Calculated fields', 'fields': calc_fields})
    return (groups, catalog)

def _invoice_analysis_default_ids(meta: Dict[str, Any], catalog: Dict[str, Tuple[str, str]]) -> List[str]:
    billno_h = meta['billno_h'].upper()
    billdate_c = meta['billdate_col'].upper()
    itemcode_d = meta['itemcode_d'].upper()
    qty_col = _detect_column(meta['dtl_tbl'], ['QTY', 'QUANTITY', 'QTYORDERED', 'QTY_ORDERED'])
    picks: List[str] = []
    for cid in (f'hdr:{billno_h}', f'hdr:{billdate_c}', f'dtl:{itemcode_d}', f'dtl:{qty_col.upper()}' if qty_col else ''):
        if cid and cid in catalog:
            picks.append(cid)
    if picks:
        return picks
    return list(catalog.keys())[:min(8, len(catalog))]

def _invoice_analysis_select_parts(meta: Dict[str, Any], catalog: Dict[str, Tuple[str, str]], column_ids: List[str]) -> Tuple[List[str], List[str]]:
    """Build SELECT fragments and output keys (aliases)."""
    select_frags: List[str] = []
    keys: List[str] = []
    for cid in column_ids:
        entry = catalog.get(cid)
        if not entry:
            continue
        expr, out_alias = entry
        select_frags.append(f'{expr} AS "{out_alias}"')
        keys.append(out_alias.lower())
    return (select_frags, keys)

def _invoice_analysis_extra_joins(meta: Dict[str, Any]) -> str:
    parts = [meta.get('customer_join_sql') or '', meta.get('sch_hdr_join_sql') or '', meta.get('sch_cust_join_sql') or '']
    return ' '.join((p for p in parts if p))

def _invoice_analysis_im_join(meta: Dict[str, Any]) -> str:
    im_tbl = meta.get('im_tbl') or ''
    itemcode_im = meta.get('itemcode_im') or ''
    if not im_tbl or not itemcode_im:
        return ''
    itemcode_d = meta['itemcode_d']
    join_sql = f'LEFT JOIN {im_tbl} im ON d.{itemcode_d} = im.{itemcode_im}'
    loc_h = meta.get('locationcode_col') or ''
    loc_im = meta.get('loc_im') or ''
    if loc_h and loc_im:
        join_sql += f' AND (im.{loc_im} = h.{loc_h} OR im.{loc_im} IS NULL)'
    return join_sql

def _invoice_analysis_alias_tables(meta: Dict[str, Any]) -> Dict[str, str]:
    """SQL alias -> physical table name for filter/order validation."""
    out: Dict[str, str] = {'h': meta['hdr_tbl'], 'd': meta['dtl_tbl']}
    im_tbl = (meta.get('im_tbl') or '').strip()
    if im_tbl:
        out['im'] = im_tbl
    cust_tbl = (meta.get('customer_tbl') or '').strip()
    if cust_tbl and meta.get('customer_join_sql'):
        out['cust'] = cust_tbl
    sch_tbl = (meta.get('sch_tbl') or '').strip()
    if sch_tbl and meta.get('sch_hdr_join_sql'):
        out['tisch_hdr'] = sch_tbl
    if sch_tbl and meta.get('sch_cust_join_sql'):
        out['tisch_cust'] = sch_tbl
    return out

def _invoice_analysis_builder_join_lines(meta: Dict[str, Any]) -> List[str]:
    """Human-readable join snippets for the visual builder (fixed layout)."""
    hdr_tbl = meta['hdr_tbl']
    dtl_tbl = meta['dtl_tbl']
    billno_h = meta['billno_h']
    billno_d = meta['billno_d']
    lines = [f'FROM {hdr_tbl} h', f'LEFT JOIN {dtl_tbl} d ON h.{billno_h} = d.{billno_d}']
    im_join = (_invoice_analysis_im_join(meta) or '').strip()
    if im_join:
        lines.append(im_join)
    extra = (_invoice_analysis_extra_joins(meta) or '').strip()
    if extra:
        lines.append(extra)
    return lines

def _invoice_analysis_filter_builder_payload(meta: Dict[str, Any], allowed_by_role: Optional[Dict[str, Set[str]]]=None) -> Dict[str, Any]:
    """Sidebar metadata for Smart List–style filters / joins UI."""
    alias_tables = _invoice_analysis_alias_tables(meta)
    label_map = {'h': 'Bill header (h)', 'd': 'Bill detail (d)', 'im': 'Item master (im)', 'cust': 'Customer (cust)', 'tisch_hdr': 'Sales channel — header (tisch_hdr)', 'tisch_cust': 'Sales channel — customer (tisch_cust)'}
    order_keys = ['h', 'd', 'im', 'cust', 'tisch_hdr', 'tisch_cust']
    filter_aliases = [{'key': k, 'label': label_map.get(k, k)} for k in order_keys if k in alias_tables]
    columns_by_alias: Dict[str, List[str]] = {}
    for alias, tbl in alias_tables.items():
        cols = _analysis_safe_columns(tbl)
        rk = _SA_SQL_ALIAS_TO_ROLE.get(alias)
        if rk and allowed_by_role is not None:
            alset = allowed_by_role.get(rk)
            if not alset:
                cols = []
            else:
                cols = [c for c in cols if c.upper() in alset]
        columns_by_alias[alias] = cols
    return {'builder_joins': _invoice_analysis_builder_join_lines(meta), 'filter_aliases': filter_aliases, 'columns_by_alias': columns_by_alias}

def _invoice_analysis_canonical_column(table: str, col_input: str) -> Optional[str]:
    if not table or not col_input:
        return None
    safe = _analysis_safe_columns(table)
    if not safe:
        return None
    lu = {str(c).upper(): c for c in safe}
    return lu.get(str(col_input).strip().upper())

def _invoice_analysis_normalize_filter_op(raw: str) -> Optional[str]:
    s = (raw or '').strip()
    if not s:
        return '='
    key = s.upper()
    if key == '!=':
        return '<>'
    if key in _ALLOWED_ANALYSIS_FILTER_OPS:
        return key
    return None

def _invoice_analysis_apply_extra_filters(where_clause: str, params: Dict[str, Any], meta: Dict[str, Any], filters_raw: List[Any]) -> Tuple[str, Optional[str]]:
    """Append validated AND clauses; mutates params."""
    if not filters_raw:
        return (where_clause, None)
    if len(filters_raw) > _ANALYSIS_MAX_EXTRA_FILTERS:
        return (where_clause, f'At most {_ANALYSIS_MAX_EXTRA_FILTERS} extra filters allowed.')
    alias_tables = _invoice_analysis_alias_tables(meta)
    fragments: List[str] = []
    bind_i = 0
    for filt in filters_raw:
        if not isinstance(filt, dict):
            continue
        alias = str(filt.get('alias') or filt.get('table_alias') or '').strip().lower()
        table = alias_tables.get(alias)
        if not table:
            return (where_clause, f'Unknown filter alias: {alias!r}.')
        col_in = str(filt.get('column') or '').strip()
        canon = _invoice_analysis_canonical_column(table, col_in)
        if not col_in or not canon:
            return (where_clause, f'Unknown column {col_in!r} for alias {alias!r}.')
        rk_a = _SA_SQL_ALIAS_TO_ROLE.get(alias)
        col_allow_map = _sa_fetch_column_allowlist()
        if col_allow_map is not None and rk_a:
            alset = col_allow_map.get(rk_a)
            if alset is not None and canon.upper() not in alset:
                return (where_clause, f'Column {canon!r} is not enabled in Data Configuration ({rk_a}).')
        raw_op = str(filt.get('operator') or '=').strip()
        op = _invoice_analysis_normalize_filter_op(raw_op)
        if not op:
            return (where_clause, f'Unsupported operator: {raw_op!r}.')
        value = filt.get('value')
        col_expr = f'{alias}.{canon}'
        if op in ('IS NULL', 'IS NOT NULL'):
            fragments.append(f'{col_expr} {op}')
            continue
        if op == 'IN':
            raw_val = '' if value is None else str(value).strip()
            parts = [p.strip() for p in raw_val.split(',') if p.strip()]
            if not parts:
                return (where_clause, 'IN filter requires comma-separated values.')
            ph: List[str] = []
            for p in parts:
                bk = f'sa_ef_{bind_i}'
                bind_i += 1
                params[bk] = p
                ph.append(f':{bk}')
            fragments.append(f"{col_expr} IN ({', '.join(ph)})")
            continue
        if value is None or str(value).strip() == '':
            return (where_clause, f'A value is required for {col_expr} {op}.')
        bk = f'sa_ef_{bind_i}'
        bind_i += 1
        params[bk] = value if not isinstance(value, str) else value.strip()
        if op == 'NOT LIKE':
            fragments.append(f'{col_expr} NOT LIKE :{bk}')
        else:
            fragments.append(f'{col_expr} {op} :{bk}')
    if not fragments:
        return (where_clause, None)
    merged = '(' + where_clause + ') AND (' + ') AND ('.join(fragments) + ')'
    return (merged, None)

def _invoice_analysis_resolve_order_by(meta: Dict[str, Any], order_by: Optional[Dict[str, Any]], alias_tables: Dict[str, str]) -> str:
    billno_h = meta['billno_h']
    default = f'ORDER BY h.{billno_h} DESC, d.ROWID'
    if not order_by or not isinstance(order_by, dict):
        return default
    alias = str(order_by.get('alias') or order_by.get('table_alias') or '').strip().lower()
    col_in = str(order_by.get('column') or '').strip()
    if not alias or not col_in:
        return default
    direction = str(order_by.get('direction') or 'ASC').strip().upper()
    if direction not in ('ASC', 'DESC'):
        direction = 'ASC'
    table = alias_tables.get(alias)
    if not table:
        return default
    canon = _invoice_analysis_canonical_column(table, col_in)
    if not canon:
        return default
    return f'ORDER BY {alias}.{canon} {direction}'

def _invoice_analysis_build_inner_sql(meta: Dict[str, Any], catalog: Dict[str, Tuple[str, str]], column_ids: List[str], date_from: str, date_to: str, location_code: Optional[int], extra_filters: Optional[List[Dict[str, Any]]]=None, order_by: Optional[Dict[str, Any]]=None) -> Tuple[str, Dict[str, Any], List[str], Optional[str]]:
    """Build inner SELECT … FROM … WHERE … ORDER BY (before ROWNUM wrapper)."""
    select_frags, out_keys = _invoice_analysis_select_parts(meta, catalog, column_ids)
    if not select_frags:
        return ('', {}, [], 'No valid columns selected.')
    where_clause, params = _build_filters(billtype_col=meta['billtype_col'], billdate_col=meta['billdate_col'], customercode_col=meta['customercode_col'], salesmancode_col=meta['salesmancode_col'] or '', customer_code='', salesman_code='', date_from=date_from, date_to=date_to)
    if location_code is not None and meta.get('locationcode_col'):
        where_clause = f"({where_clause}) AND h.{meta['locationcode_col']} = :location_code"
        params['location_code'] = location_code
    where_clause, ferr = _invoice_analysis_apply_extra_filters(where_clause, params, meta, list(extra_filters or []))
    if ferr:
        return ('', {}, [], ferr)
    hdr_tbl = meta['hdr_tbl']
    dtl_tbl = meta['dtl_tbl']
    billno_h = meta['billno_h']
    billno_d = meta['billno_d']
    im_join = (_invoice_analysis_im_join(meta) or '').strip()
    extra_join = (_invoice_analysis_extra_joins(meta) or '').strip()
    inner_select = ', '.join(select_frags)
    join_lines = [f'FROM {hdr_tbl} h', f'LEFT JOIN {dtl_tbl} d ON h.{billno_h} = d.{billno_d}']
    if im_join:
        join_lines.append(im_join)
    if extra_join:
        join_lines.append(extra_join)
    alias_tables = _invoice_analysis_alias_tables(meta)
    order_sql = _invoice_analysis_resolve_order_by(meta, order_by, alias_tables)
    inner_sql = f'SELECT {inner_select}\n' + '\n'.join(join_lines) + f'\nWHERE {where_clause}\n' + order_sql
    return (inner_sql, dict(params), out_keys, None)

def _invoice_analysis_run_rows(meta: Dict[str, Any], catalog: Dict[str, Tuple[str, str]], column_ids: List[str], date_from: str, date_to: str, location_code: Optional[int], extra_filters: Optional[List[Dict[str, Any]]]=None, order_by: Optional[Dict[str, Any]]=None) -> Tuple[List[str], List[Dict[str, Any]], Optional[str]]:
    inner_sql, params, out_keys, err = _invoice_analysis_build_inner_sql(meta, catalog, column_ids, date_from, date_to, location_code, extra_filters=extra_filters, order_by=order_by)
    if err:
        return ([], [], err)
    query = f'\n        SELECT * FROM (\n            SELECT z.*, ROWNUM AS ti_analysis_rn FROM (\n                {inner_sql}\n            ) z WHERE ROWNUM <= :ti_lim\n        ) WHERE ti_analysis_rn >= 1\n    '
    params['ti_lim'] = _ANALYSIS_ROW_LIMIT
    try:
        _, rows = _fetch_rows(query, params)
    except Exception as exc:
        return ([], [], str(exc))
    cleaned: List[Dict[str, Any]] = []
    for raw in rows or []:
        row = _invoice_detail_serialize_mapping(raw)
        row.pop('ti_analysis_rn', None)
        cleaned.append(row)
    return (out_keys, cleaned, None)

def _invoice_detail_json_value(val: Any) -> Any:
    if val is None:
        return None
    if hasattr(val, 'strftime'):
        try:
            return val.strftime('%Y-%m-%d')
        except Exception:
            return str(val)
    if isinstance(val, bool):
        return val
    if isinstance(val, Decimal):
        try:
            if val % 1 == 0:
                return int(val)
            return format(val, 'f').rstrip('0').rstrip('.') or '0'
        except Exception:
            return str(val)
    if isinstance(val, int) and (not isinstance(val, bool)):
        return val
    if isinstance(val, float):
        return val
    if isinstance(val, str):
        return val
    try:
        return float(val)
    except (TypeError, ValueError):
        return str(val)

def _invoice_detail_serialize_mapping(row: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in row.items():
        key = str(k).lower() if k is not None else ''
        out[key] = _invoice_detail_json_value(v)
    return out

def _pdf_escape_html(text: Any) -> str:
    s = str(text if text is not None else '')
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')

def _billtype_label_for_pdf(code: Any) -> str:
    c = str(code or '').strip().upper()[:1]
    if c == 'C':
        return 'Cash'
    if c == 'R':
        return 'Credit'
    if c == 'T':
        return 'Temporary'
    raw = str(code or '').strip()
    return raw or '—'

def _format_pdf_scalar(val: Any) -> str:
    if val is None:
        return '—'
    if hasattr(val, 'strftime'):
        try:
            return val.strftime('%d-%b-%Y')
        except Exception:
            pass
    s = str(val).strip()
    if len(s) >= 10 and s[4] == '-' and (s[7] == '-'):
        try:
            return datetime.strptime(s[:10], '%Y-%m-%d').strftime('%d-%b-%Y')
        except ValueError:
            pass
    return s or '—'

def _pdf_money(val: Any) -> str:
    if val is None or val == '':
        return '—'
    try:
        return f'{float(val):,.2f}'
    except (TypeError, ValueError):
        return str(val)

def _pdf_plain_cell(val: Any) -> str:
    if val is None or val == '':
        return '—'
    s = str(val).strip().replace('\r', ' ').replace('\n', ' ')
    return s if s else '—'

def _generate_temporary_invoice_pdf_bytes(header: Dict[str, Any], items: List[Dict[str, Any]], location_name: str='') -> Optional[bytes]:
    """A4 invoice PDF: header block + line table."""
    if not REPORTLAB_AVAILABLE:
        return None
    try:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.45 * inch, bottomMargin=0.45 * inch, leftMargin=0.45 * inch, rightMargin=0.45 * inch)
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle('InvTitle', parent=styles['Heading1'], fontSize=16, textColor=colors.HexColor('#0f766e'), spaceAfter=10, alignment=TA_CENTER, fontName='Helvetica-Bold')
        meta_style = ParagraphStyle('InvMeta', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#475569'), alignment=TA_CENTER, spaceAfter=14)
        story = []
        story.append(Paragraph(_pdf_escape_html('INVOICE'), title_style))
        loc_line = (location_name or '').strip() or '—'
        story.append(Paragraph(_pdf_escape_html(loc_line), meta_style))
        bt = _billtype_label_for_pdf(header.get('billtype'))
        hdr_rows = [['Bill no.', _pdf_plain_cell(header.get('billno'))], ['Bill date', _pdf_plain_cell(_format_pdf_scalar(header.get('billdate')))], ['Bill type', _pdf_plain_cell(bt)], ['Customer code', _pdf_plain_cell(header.get('customercode'))], ['Customer', _pdf_plain_cell(header.get('customername'))], ['Salesman code', _pdf_plain_cell(header.get('salesmancode'))], ['Salesman', _pdf_plain_cell(header.get('salesmanname'))], ['Location', _pdf_plain_cell(header.get('locationcode'))], ['Net amount', _pdf_plain_cell(_pdf_money(header.get('netbillamount')))]]
        t_hdr = Table(hdr_rows, colWidths=[1.35 * inch, 5.9 * inch])
        t_hdr.setStyle(TableStyle([('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'), ('FONTNAME', (1, 0), (1, -1), 'Helvetica'), ('FONTSIZE', (0, 0), (-1, -1), 9), ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#1e293b')), ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')), ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#e2e8f0')), ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f1f5f9')), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('LEFTPADDING', (0, 0), (-1, -1), 8), ('RIGHTPADDING', (0, 0), (-1, -1), 8), ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]))
        story.append(t_hdr)
        story.append(Spacer(1, 0.22 * inch))
        story.append(Paragraph(_pdf_escape_html('Line items'), ParagraphStyle('LinesHdr', parent=styles['Heading2'], fontSize=11, textColor=colors.HexColor('#334155'), spaceAfter=8, fontName='Helvetica-Bold')))
        table_data: List[List[str]] = [['#', 'Item code', 'Item name', 'UOM', 'Qty', 'Rate', 'Amount']]
        for i, row in enumerate(items or [], start=1):
            table_data.append([str(i), _pdf_plain_cell(row.get('itemcode')), _pdf_plain_cell(row.get('itemname')), _pdf_plain_cell(row.get('uom')), _pdf_money(row.get('quantity')), _pdf_money(row.get('rate')), _pdf_money(row.get('amount'))])
        if len(table_data) == 1:
            table_data.append(['—', 'No line items', '', '', '', '', ''])
        col_w = [0.28 * inch, 0.82 * inch, 2.55 * inch, 0.52 * inch, 0.72 * inch, 0.82 * inch, 0.92 * inch]
        t_lines = Table(table_data, colWidths=col_w, repeatRows=1)
        t_lines.setStyle(TableStyle([('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, -1), 8), ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#1e293b')), ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#475569')), ('ALIGN', (4, 0), (-1, -1), TA_RIGHT), ('ALIGN', (0, 1), (0, -1), TA_CENTER), ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')), ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#e2e8f0')), ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f1f5f9')), ('LEFTPADDING', (0, 0), (-1, -1), 5), ('RIGHTPADDING', (0, 0), (-1, -1), 5), ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5)]))
        story.append(t_lines)
        story.append(Spacer(1, 0.35 * inch))
        gen = datetime.now().strftime('%d-%b-%Y %H:%M')
        story.append(Paragraph(_pdf_escape_html(f'Generated {gen}'), ParagraphStyle('Foot', parent=styles['Normal'], fontSize=7, textColor=colors.grey, alignment=TA_CENTER)))
        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()
    except Exception as e:
        print(f'[ERROR _generate_temporary_invoice_pdf_bytes] {e}')
        return None

@bp.route('/temporary-invoices/api/invoice-detail')
def api_invoice_detail():
    """JSON: header + line items for invoice detail panel (list row click)."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    _apply_session_tenant_connection_temporary_invoices()
    billno = request.args.get('billno', '').strip()
    if not billno:
        return jsonify({'success': False, 'error': 'Bill number is required'}, 400)
    header, items = _fetch_invoice_header_and_items(billno)
    if not header:
        return jsonify({'success': False, 'error': 'Invoice not found'}, 404)
    return jsonify({'success': True, 'header': _invoice_detail_serialize_mapping(header), 'items': [_invoice_detail_serialize_mapping(r) for r in items]})

@bp.route('/temporary-invoices/api/invoice-pdf')
def invoice_pdf():
    """Download invoice as PDF (same data as detail API)."""
    if not session.get('user'):
        return Response('Not authenticated', status=401, mimetype='text/plain')
    _apply_session_tenant_connection_temporary_invoices()
    billno = (request.args.get('billno') or '').strip()
    if not billno:
        return Response('Bill number is required', status=400, mimetype='text/plain')
    if not REPORTLAB_AVAILABLE:
        return Response('PDF is not available (install reportlab).', status=500, mimetype='text/plain')
    header, items = _fetch_invoice_header_and_items(billno)
    if not header:
        return Response('Invoice not found', status=404, mimetype='text/plain')
    location_name = ''
    try:
        lc = header.get('locationcode')
        if lc is not None:
            info = get_location_info_by_dbkey(str(lc))
            if info:
                location_name = (info.get('locationname') or '').strip()
    except Exception:
        pass
    pdf_bytes = _generate_temporary_invoice_pdf_bytes(header, items or [], location_name=location_name)
    if not pdf_bytes:
        return Response('Failed to generate PDF', status=500, mimetype='text/plain')
    safe_bill = ''.join((c for c in str(billno) if c.isalnum() or c in ('-', '_')))[:48] or 'invoice'
    filename = f'invoice_{safe_bill}.pdf'
    return send_file(io.BytesIO(pdf_bytes), mimetype='application/pdf', as_attachment=True, download_name=filename)

@bp.route('/temporary-invoices/analysis')
def invoice_analysis():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    else:
        location_code_sess = session.get('location_code')
        if location_code_sess:
            _apply_active_connection(location_code_sess)
        elif session.get('user') == 'admin':
            _apply_active_connection('HO')
    location_code = _resolve_location_code()
    today = date.today().isoformat()
    date_from = request.args.get('date_from', '').strip() or today
    date_to = request.args.get('date_to', '').strip() or today
    openai_key_set = bool((os.environ.get('OPENAI_API_KEY') or '').strip())
    return render_template('temporary_invoices/temporary_invoices_analysis.html', title='AI Reports', date_from=date_from, date_to=date_to, analysis_row_limit=_ANALYSIS_ROW_LIMIT, openai_configured=openai_key_set)

def _sa_normalize_columns_in(body: Dict[str, Any]) -> Tuple[Dict[str, List[str]], Dict[Tuple[str, str], str], Optional[str]]:
    """Parse selected_fields (preferred) or legacy columns dict."""
    selected_fields = body.get('selected_fields')
    columns_in: Dict[str, List[str]] = {}
    labels: Dict[Tuple[str, str], str] = {}
    if isinstance(selected_fields, list) and selected_fields:
        seen: Set[Tuple[str, str]] = set()
        for item in selected_fields:
            if not isinstance(item, dict):
                continue
            rk = str(item.get('role_key') or '').strip().lower()
            cn = str(item.get('column_name') or '').strip().upper()
            if not rk or not cn:
                continue
            if rk not in _SA_BODY_COLUMN_ROLES:
                return ({}, {}, f'Invalid role_key: {rk!r}.')
            if (rk, cn) in seen:
                continue
            seen.add((rk, cn))
            columns_in.setdefault(rk, []).append(cn)
            dl = str(item.get('display_label') or '').strip()
            if dl:
                labels[rk, cn] = dl[:512]
        return (columns_in, labels, None)
    raw_cols = body.get('columns')
    if isinstance(raw_cols, dict):
        for rk, lst in raw_cols.items():
            rkk = str(rk).strip().lower()
            if rkk not in _SA_BODY_COLUMN_ROLES:
                continue
            if not isinstance(lst, list):
                continue
            for c in lst:
                cn = str(c).strip().upper()
                if cn:
                    columns_in.setdefault(rkk, []).append(cn)
        return (columns_in, {}, None)
    return ({}, {}, None)

def _sa_columns_dict_to_allow(columns_in: Dict[str, List[str]]) -> Optional[Dict[str, Set[str]]]:
    if not columns_in:
        return None
    buckets: Dict[str, Set[str]] = {}
    for rk, lst in columns_in.items():
        if not isinstance(lst, list):
            continue
        for c in lst:
            cn = str(c).strip().upper()
            if cn:
                buckets.setdefault(rk, set()).add(cn)
    return buckets if buckets else None

def _sa_persist_salesanalysis_config(body: Dict[str, Any]) -> Optional[str]:
    """Persist selected columns, source overrides, and calculations to SA_ANALYSIS_* (tenant DB)."""
    meta = _invoice_analysis_resolve_meta()
    if not meta:
        return 'Bill header/detail metadata could not be resolved.'
    columns_in, col_labels, norm_err = _sa_normalize_columns_in(body)
    if norm_err:
        return norm_err
    sources_in = body.get('sources') if isinstance(body.get('sources'), dict) else {}
    table_for_role = {'hdr': meta['hdr_tbl'], 'dtl': meta['dtl_tbl'], 'im': (meta.get('im_tbl') or '').strip(), 'cust': (meta.get('customer_tbl') or '').strip(), 'sch_hdr': (meta.get('sch_tbl') or '').strip(), 'sch_cust': (meta.get('sch_tbl') or '').strip()}
    for rk, tbl in table_for_role.items():
        cols_list = columns_in.get(rk)
        if not isinstance(cols_list, list) or not cols_list:
            continue
        if not tbl:
            return f'No active table for role {rk!r}; remove those columns or enable joins.'
        safe = {c.upper() for c in _analysis_safe_columns(tbl)}
        for c in cols_list:
            cn = str(c).strip().upper()
            if cn and cn not in safe:
                return f'Column {cn} is not allowed on {tbl} ({rk}).'
    for rk in _SA_CFG_ROLE_KEYS:
        pkg = sources_in.get(rk) if isinstance(sources_in.get(rk), dict) else {}
        nm = str(pkg.get('object_name') or '').strip().upper()
        if nm and (not _get_table_columns(nm)):
            return f'Table/view {nm!r} not found ({rk}).'
    calcs_raw = body.get('calculations')
    if not isinstance(calcs_raw, list):
        calcs_raw = []
    provisional_allow = _sa_columns_dict_to_allow(columns_in)
    calc_rows: List[Tuple[str, int, str, str]] = []
    seen_ck: Set[str] = set()
    seen_oa: Set[str] = set()
    slot = 0
    for idx, c in enumerate(calcs_raw):
        if not isinstance(c, dict):
            continue
        ck = str(c.get('calc_key') or '').strip()
        oa = str(c.get('output_alias') or '').strip()
        ex = str(c.get('expression') or '').strip()
        if not ck or not oa or (not ex):
            continue
        if len(ck) > 64:
            return 'calc_key too long (max 64 characters).'
        if ck in seen_ck:
            return f'Duplicate calc_key: {ck!r}.'
        seen_ck.add(ck)
        oau = re.sub('[^A-Za-z0-9_]', '_', oa).upper()
        if oau in seen_oa:
            return f'Duplicate output_alias: {oa!r}.'
        seen_oa.add(oau)
        _, cerr = _invoice_analysis_resolve_calc_expression_sql(meta, ex, provisional_allow)
        if cerr:
            return f'Calculation {oa!r}: {cerr}'
        calc_rows.append((ck, slot, oa[:128], ex[:4000]))
        slot += 1
    _ensure_sa_analysis_config_tables()
    _ensure_sa_analysis_calc_table()
    phy_col = _sa_analysis_col_physical_columns()
    try:
        with _get_connection() as conn:
            cur = conn.cursor()
            try:
                cur.execute(f'DELETE FROM {_SA_ANALYSIS_CALC_TAB}')
            except Exception:
                pass
            try:
                cur.execute(f'DELETE FROM {_SA_ANALYSIS_COL_TAB}')
            except Exception:
                pass
            merge_src = f'\n                MERGE INTO {_SA_ANALYSIS_SRC_TAB} t\n                USING (SELECT :a AS rk, :b AS obnm, :c AS oknd FROM dual) s\n                ON (t.ROLE_KEY = s.rk)\n                WHEN MATCHED THEN\n                    UPDATE SET t.OBJECT_NAME = s.obnm, t.OBJECT_KIND = s.oknd\n                WHEN NOT MATCHED THEN\n                    INSERT (ROLE_KEY, OBJECT_NAME, OBJECT_KIND) VALUES (s.rk, s.obnm, s.oknd)\n            '
            for rk in _SA_CFG_ROLE_KEYS:
                pkg = sources_in.get(rk) if isinstance(sources_in.get(rk), dict) else {}
                nm = str(pkg.get('object_name') or '').strip().upper()
                kd = str(pkg.get('object_kind') or 'TABLE').strip().upper() or 'TABLE'
                cur.execute(merge_src, {'a': rk, 'b': nm if nm else None, 'c': kd})
            ord_i = 0
            for rk in ('hdr', 'dtl', 'im', 'cust', 'sch_hdr', 'sch_cust'):
                cols_list = columns_in.get(rk)
                if not isinstance(cols_list, list):
                    continue
                for c in cols_list:
                    cn = str(c).strip().upper()
                    if not cn:
                        continue
                    dl_raw = col_labels.get((rk, cn))
                    _sa_insert_analysis_col_row(cur, phy_col, rk, cn, dl_raw if dl_raw else None, ord_i)
                    ord_i += 1
            for ck, idx, oa, ex in calc_rows:
                cur.execute(f'\n                    INSERT INTO {_SA_ANALYSIS_CALC_TAB} (CALC_KEY, SORT_ORD, OUTPUT_ALIAS, EXPRESSION)\n                    VALUES (:k, :o, :a, :e)\n                    ', {'k': ck, 'o': idx, 'a': oa, 'e': ex})
            conn.commit()
    except Exception as exc:
        return str(exc)
    _TABLE_COLUMNS_CACHE.pop(_SA_ANALYSIS_COL_TAB.upper(), None)
    return None

@bp.route('/temporary-invoices/salesanalysis-data-config')
def salesanalysis_data_config():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    else:
        location_code_sess = session.get('location_code')
        if location_code_sess:
            _apply_active_connection(location_code_sess)
        elif session.get('user') == 'admin':
            _apply_active_connection('HO')
    return render_template('temporary_invoices/salesanalysis_data_config.html', title='Salesanalysis · Data configuration')

@bp.route('/temporary-invoices/api/salesanalysis-db-objects', methods=['GET'])
def api_salesanalysis_db_objects():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    _apply_session_tenant_connection_temporary_invoices()
    q = "\n        SELECT OBJECT_NAME AS name, OBJECT_TYPE AS obj_type\n        FROM USER_OBJECTS\n        WHERE OBJECT_TYPE IN ('TABLE', 'VIEW')\n        ORDER BY OBJECT_TYPE, OBJECT_NAME\n    "
    try:
        _, rows = _fetch_rows(q, {})
        items = [{'name': str(r.get('name') or ''), 'type': str(r.get('obj_type') or '')} for r in rows]
        return jsonify({'success': True, 'items': items})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}, 500)

@bp.route('/temporary-invoices/api/salesanalysis-table-columns', methods=['GET'])
def api_salesanalysis_table_columns():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    _apply_session_tenant_connection_temporary_invoices()
    table = (request.args.get('table') or '').strip().upper()
    if not table:
        return jsonify({'success': False, 'error': 'table query param required'}, 400)
    q = '\n        SELECT COLUMN_NAME, DATA_TYPE\n        FROM USER_TAB_COLUMNS\n        WHERE TABLE_NAME = :tbl\n        ORDER BY COLUMN_ID\n    '
    try:
        _, rows = _fetch_rows(q, {'tbl': table})
        cols = [{'name': str(r.get('column_name') or ''), 'type': str(r.get('data_type') or '')} for r in rows]
        return jsonify({'success': True, 'columns': cols})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}, 500)

@bp.route('/temporary-invoices/api/salesanalysis-config', methods=['GET', 'POST'])
def api_salesanalysis_config():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    _apply_session_tenant_connection_temporary_invoices()
    if request.method == 'POST':
        body = request.get_json(force=True, silent=True) or {}
        err = _sa_persist_salesanalysis_config(body)
        if err:
            return jsonify({'success': False, 'error': err}, 400)
        return jsonify({'success': True})
    meta = _invoice_analysis_resolve_meta()
    if not meta:
        return jsonify({'success': False, 'error': 'Bill header/detail tables or required columns were not found.'}, 400)
    overrides = _sa_fetch_src_overrides()
    rows_detail = _sa_fetch_sa_analysis_col_rows()
    saved_cols: Dict[str, List[str]] = {}
    selected_fields_out: List[Dict[str, Any]] = []
    for r in rows_detail:
        rk = str(r.get('role_key') or r.get('ROLE_KEY') or '').strip().lower()
        cn = str(r.get('column_name') or r.get('COLUMN_NAME') or '').strip()
        if rk and cn:
            saved_cols.setdefault(rk, []).append(cn)
            try:
                so = int(r.get('sort_ord') or r.get('SORT_ORD') or 0)
            except Exception:
                so = 0
            dl = str(r.get('display_label') or r.get('DISPLAY_LABEL') or '').strip()
            selected_fields_out.append({'role_key': rk, 'column_name': cn, 'display_label': dl, 'sort_ord': so})
    calculations_out = _sa_fetch_calc_entries()
    sch_tbl = (meta.get('sch_tbl') or '').strip()
    all_cols = {'hdr': _analysis_safe_columns(meta['hdr_tbl']), 'dtl': _analysis_safe_columns(meta['dtl_tbl']), 'im': _analysis_safe_columns(meta['im_tbl']) if meta.get('im_tbl') else [], 'cust': _analysis_safe_columns(meta['customer_tbl']) if meta.get('customer_tbl') else [], 'sch_hdr': _analysis_safe_columns(sch_tbl) if sch_tbl else [], 'sch_cust': _analysis_safe_columns(sch_tbl) if sch_tbl else []}
    sources_out: Dict[str, Any] = {}
    for rk in _SA_CFG_ROLE_KEYS:
        tup = overrides.get(rk, ('', 'TABLE'))
        sources_out[rk] = {'object_name': tup[0] or '', 'object_kind': tup[1] or 'TABLE'}
    return jsonify({'success': True, 'resolved': {'hdr_tbl': meta['hdr_tbl'], 'dtl_tbl': meta['dtl_tbl'], 'im_tbl': meta.get('im_tbl') or '', 'customer_tbl': meta.get('customer_tbl') or '', 'sch_tbl': meta.get('sch_tbl') or ''}, 'sources': sources_out, 'columns_saved': saved_cols, 'selected_fields': selected_fields_out, 'calculations': calculations_out, 'all_columns': all_cols, 'column_allowlist_active': _sa_fetch_column_allowlist() is not None})

def _invoice_analysis_filters_order_from_body(body: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    raw = body.get('filters')
    filters_out: List[Dict[str, Any]] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                filters_out.append(item)
    order_by: Optional[Dict[str, Any]] = None
    ob = body.get('order_by')
    if isinstance(ob, dict) and str(ob.get('column') or '').strip():
        order_by = ob
    return (filters_out, order_by)

@bp.route('/temporary-invoices/api/analysis-columns', methods=['GET'])
def api_invoice_analysis_columns():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    _apply_session_tenant_connection_temporary_invoices()
    meta = _invoice_analysis_resolve_meta()
    if not meta:
        return jsonify({'success': False, 'error': 'Bill header/detail tables or required columns were not found.'}, 400)
    allow = _sa_fetch_column_allowlist()
    groups, catalog = _invoice_analysis_catalog_and_map(meta, allow)
    defaults = _invoice_analysis_default_ids(meta, catalog)
    fb = _invoice_analysis_filter_builder_payload(meta, allow)
    return jsonify({'success': True, 'groups': groups, 'defaults': defaults, 'row_limit': _ANALYSIS_ROW_LIMIT, 'max_columns': _ANALYSIS_MAX_COLUMNS, 'max_extra_filters': _ANALYSIS_MAX_EXTRA_FILTERS, 'column_allowlist_active': allow is not None, **fb})

@bp.route('/temporary-invoices/api/analysis-run', methods=['POST'])
def api_invoice_analysis_run():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    _apply_session_tenant_connection_temporary_invoices()
    body = request.get_json(force=True, silent=True) or {}
    raw_cols = body.get('columns') or []
    if not isinstance(raw_cols, list):
        raw_cols = []
    column_ids = [str(x).strip() for x in raw_cols if str(x).strip()]
    if len(column_ids) > _ANALYSIS_MAX_COLUMNS:
        return jsonify({'success': False, 'error': f'Select at most {_ANALYSIS_MAX_COLUMNS} columns.'}, 400)
    meta = _invoice_analysis_resolve_meta()
    if not meta:
        return jsonify({'success': False, 'error': 'Bill header/detail tables or required columns were not found.'}, 400)
    allow = _sa_fetch_column_allowlist()
    _, catalog = _invoice_analysis_catalog_and_map(meta, allow)
    allowed = set(catalog.keys())
    picked = [c for c in column_ids if c in allowed]
    if not picked:
        picked = _invoice_analysis_default_ids(meta, catalog)
    location_code = _resolve_location_code()
    today_iso = date.today().isoformat()
    date_from = str(body.get('date_from') or '').strip() or today_iso
    date_to = str(body.get('date_to') or '').strip() or today_iso
    extra_filters, order_by = _invoice_analysis_filters_order_from_body(body)
    keys, rows, err = _invoice_analysis_run_rows(meta, catalog, picked, date_from, date_to, location_code, extra_filters=extra_filters, order_by=order_by)
    if err:
        return jsonify({'success': False, 'error': err}, 400)
    labels = [k.upper().replace('_', ' ') for k in keys]
    return jsonify({'success': True, 'columns': keys, 'column_labels': labels, 'rows': rows, 'row_limit': _ANALYSIS_ROW_LIMIT, 'truncated_hint': len(rows) >= _ANALYSIS_ROW_LIMIT, 'empty_hint': 'No rows matched bill types C/R/T with your bill dates, location, and filters. Try widening the date range; detail-only columns are blank when a bill has no lines.' if not rows else ''})

def _invoice_analysis_extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    """Parse JSON object from model output; tolerate markdown fences."""
    raw = (text or '').strip()
    if not raw:
        return None
    fence = re.search('```(?:json)?\\s*([\\s\\S]*?)```', raw, re.IGNORECASE)
    if fence:
        raw = fence.group(1).strip()
    try:
        out = json.loads(raw)
        return out if isinstance(out, dict) else None
    except Exception:
        pass
    i = raw.find('{')
    j = raw.rfind('}')
    if i >= 0 and j > i:
        try:
            out = json.loads(raw[i:j + 1])
            return out if isinstance(out, dict) else None
        except Exception:
            return None
    return None

def _invoice_analysis_catalog_lines_for_ai(groups: List[Dict[str, Any]], catalog: Dict[str, Tuple[str, str]], limit: int=260) -> str:
    lines: List[str] = []
    n = 0
    for g in groups:
        gtitle = str(g.get('title') or g.get('key') or '').strip()
        for f in g.get('fields') or []:
            fid = str(f.get('id') or '').strip()
            if not fid or fid not in catalog:
                continue
            lab = str(f.get('label') or fid).strip().replace('\n', ' ')
            lines.append(f'{fid}\t{gtitle}: {lab}')
            n += 1
            if n >= limit:
                return '\n'.join(lines) + '\n… (list truncated for AI context)'
    return '\n'.join(lines)
_AI_DATE_ISO_RE = re.compile('^\\d{4}-\\d{2}-\\d{2}$')

def _invoice_analysis_sanitize_ai_date_range(date_from: Optional[str], date_to: Optional[str]) -> Tuple[str, str]:
    today_iso = date.today().isoformat()
    df = str(date_from or '').strip()
    dt = str(date_to or '').strip()
    if not _AI_DATE_ISO_RE.match(df):
        df = today_iso
    if not _AI_DATE_ISO_RE.match(dt):
        dt = today_iso
    if df > dt:
        df, dt = (dt, df)
    return (df, dt)

def _invoice_analysis_sanitize_ai_filters_from_model(raw: Any, meta: Dict[str, Any], max_n: int) -> List[Dict[str, Any]]:
    """Filters shaped like the analysis-run JSON body (alias h/d/im/…, column, operator, value)."""
    out: List[Dict[str, Any]] = []
    if not isinstance(raw, list):
        return out
    alias_tables = _invoice_analysis_alias_tables(meta)
    col_allow_map = _sa_fetch_column_allowlist()
    for item in raw:
        if len(out) >= max_n:
            break
        if not isinstance(item, dict):
            continue
        alias = str(item.get('alias') or item.get('table_alias') or '').strip().lower()
        if alias not in alias_tables:
            continue
        table = alias_tables.get(alias) or ''
        col_in = str(item.get('column') or '').strip()
        canon = _invoice_analysis_canonical_column(table, col_in) if table else None
        if not canon:
            continue
        raw_op = str(item.get('operator') or '=').strip()
        op = _invoice_analysis_normalize_filter_op(raw_op)
        if not op:
            continue
        rk_a = _SA_SQL_ALIAS_TO_ROLE.get(alias)
        if col_allow_map is not None and rk_a:
            alset = col_allow_map.get(rk_a)
            if alset is not None and canon.upper() not in alset:
                continue
        if op in ('IS NULL', 'IS NOT NULL'):
            out.append({'alias': alias, 'column': canon, 'operator': op, 'value': ''})
            continue
        val = item.get('value')
        vs = '' if val is None else str(val).strip()
        if not vs:
            continue
        out.append({'alias': alias, 'column': canon, 'operator': op, 'value': vs})
    return out

def _invoice_analysis_sanitize_ai_order_from_model(raw: Any, meta: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    alias = str(raw.get('alias') or '').strip().lower()
    col_in = str(raw.get('column') or '').strip()
    if not alias or not col_in:
        return None
    alias_tables = _invoice_analysis_alias_tables(meta)
    table = alias_tables.get(alias)
    if not table:
        return None
    canon = _invoice_analysis_canonical_column(table, col_in)
    if not canon:
        return None
    rk_a = _SA_SQL_ALIAS_TO_ROLE.get(alias)
    col_allow_map = _sa_fetch_column_allowlist()
    if col_allow_map is not None and rk_a:
        alset = col_allow_map.get(rk_a)
        if alset is not None and canon.upper() not in alset:
            return None
    direction = str(raw.get('direction') or 'ASC').strip().upper()
    if direction not in ('ASC', 'DESC'):
        direction = 'ASC'
    return {'alias': alias, 'column': canon, 'direction': direction}

@bp.route('/temporary-invoices/api/analysis-ai-suggest', methods=['POST'])
def api_invoice_analysis_ai_suggest():
    """Suggest Invoice analysis column IDs from plain-language prompt (OpenAI)."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parents[3] / '.env', override=True)
    except ImportError:
        pass
    api_key = (os.environ.get('OPENAI_API_KEY') or '').strip()
    if not api_key:
        return jsonify({'success': False, 'error': 'OPENAI_API_KEY is not configured on the server (.env).'}, 503)
    _apply_session_tenant_connection_temporary_invoices()
    body = request.get_json(silent=True) or {}
    prompt = str(body.get('prompt') or '').strip()
    if len(prompt) < 3:
        return jsonify({'success': False, 'error': 'Enter at least 3 characters describing the columns you want.'}, 400)
    if len(prompt) > 2400:
        prompt = prompt[:2400]
    meta = _invoice_analysis_resolve_meta()
    if not meta:
        return jsonify({'success': False, 'error': 'Bill header/detail tables or required columns were not found.'}, 400)
    allow = _sa_fetch_column_allowlist()
    groups, catalog = _invoice_analysis_catalog_and_map(meta, allow)
    if not catalog:
        return jsonify({'success': False, 'error': 'No columns available in the catalog.'}, 400)
    catalog_text = _invoice_analysis_catalog_lines_for_ai(groups, catalog, limit=260)
    fb_ai = _invoice_analysis_filter_builder_payload(meta, allow)
    aliases_help = '\n'.join((f"- {a.get('key')}: {a.get('label')}" for a in fb_ai.get('filter_aliases') or []))
    today_iso = date.today().isoformat()
    system = f'You help users configure an Invoice analysis report in RGC Dynamics (Oracle). Header table alias h, detail d (LEFT JOIN so header-only bills still appear); optional im, cust, tisch_hdr, tisch_cust. Each catalog line: column id (e.g. hdr:BILLDATE), tab, label — ids must be copied exactly.\nRespond with ONE JSON object only, keys:\n- "column_ids": array of strings from the catalog (2–15), exact ids only.\n- "notes": one short sentence for the user.\n- "date_from", "date_to": optional strings YYYY-MM-DD (bill date range on header). If omitted, use {today_iso} for both.\n- "filters": optional array of {{ "alias", "column", "operator", "value" }}. alias MUST be an SQL alias key from the list below (e.g. h, d). column = Oracle column name. operator one of =, !=, >, <, >=, <=, LIKE, NOT LIKE, IN, IS NULL, IS NOT NULL. Skip filters unless the user asks; the app already limits bill types C,R,T and location.\n- "order_by": optional {{ "alias", "column", "direction" }} with direction ASC or DESC.\nIf the user asks for a complete report, fill dates, sensible columns, optional order_by; avoid redundant filters.'
    user_msg = f'User request:\n{prompt}\n\nSQL aliases for filters/order_by (use alias key exactly):\n{aliases_help}\n\nCatalog (id TAB label):\n{catalog_text}\n\nToday (server): {today_iso}'
    try:
        from openai import OpenAI
        try:
            _to_raw = (os.environ.get('OPENAI_TIMEOUT_SECONDS') or '120').strip()
            _openai_timeout = max(15.0, min(float(_to_raw), 600.0))
        except (ValueError, TypeError):
            _openai_timeout = 120.0
        client = OpenAI(api_key=api_key, timeout=_openai_timeout)
        model = (os.environ.get('OPENAI_MODEL') or 'gpt-4o-mini').strip()
        completion = client.chat.completions.create(model=model, messages=[{'role': 'system', 'content': system}, {'role': 'user', 'content': user_msg}], temperature=0.15, max_tokens=1600, response_format={'type': 'json_object'})
        raw = (completion.choices[0].message.content or '').strip()
    except Exception as exc:
        return jsonify({'success': False, 'error': f'AI request failed: {exc}'}, 502)
    parsed = _invoice_analysis_extract_json_object(raw)
    if not parsed:
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = {}
    if not isinstance(parsed, dict):
        return jsonify({'success': False, 'error': 'Could not parse AI response.', 'raw_preview': raw[:400]}, 502)
    raw_ids = parsed.get('column_ids')
    if not isinstance(raw_ids, list):
        raw_ids = []
    allowed = set(catalog.keys())
    picked: List[str] = []
    for cid in raw_ids:
        s = str(cid).strip()
        if s in allowed and s not in picked:
            picked.append(s)
        if len(picked) >= _ANALYSIS_MAX_COLUMNS:
            break
    notes = str(parsed.get('notes') or '').strip()
    df_s, dt_s = _invoice_analysis_sanitize_ai_date_range(parsed.get('date_from') if isinstance(parsed.get('date_from'), str) else None, parsed.get('date_to') if isinstance(parsed.get('date_to'), str) else None)
    filters_s = _invoice_analysis_sanitize_ai_filters_from_model(parsed.get('filters'), meta, _ANALYSIS_MAX_EXTRA_FILTERS)
    order_s = _invoice_analysis_sanitize_ai_order_from_model(parsed.get('order_by'), meta)
    report_options = {'date_from': df_s, 'date_to': dt_s, 'filters': filters_s, 'order_by': order_s}
    out: Dict[str, Any] = {'success': True, 'column_ids': picked, 'notes': notes, 'report_options': report_options}
    if not picked:
        out['warning'] = 'empty_selection'
        if not notes:
            out['notes'] = 'No catalog columns matched — try rephrasing. You can still apply suggested dates/filters below if any.'
    return jsonify(out)

@bp.route('/temporary-invoices/api/analysis-sql-preview', methods=['POST'])
def api_invoice_analysis_sql_preview():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    _apply_session_tenant_connection_temporary_invoices()
    body = request.get_json(force=True, silent=True) or {}
    raw_cols = body.get('columns') or []
    if not isinstance(raw_cols, list):
        raw_cols = []
    column_ids = [str(x).strip() for x in raw_cols if str(x).strip()]
    if len(column_ids) > _ANALYSIS_MAX_COLUMNS:
        return jsonify({'success': False, 'error': f'Select at most {_ANALYSIS_MAX_COLUMNS} columns.'}, 400)
    meta = _invoice_analysis_resolve_meta()
    if not meta:
        return jsonify({'success': False, 'error': 'Bill header/detail tables or required columns were not found.'}, 400)
    allow = _sa_fetch_column_allowlist()
    _, catalog = _invoice_analysis_catalog_and_map(meta, allow)
    allowed = set(catalog.keys())
    picked = [c for c in column_ids if c in allowed]
    if not picked:
        picked = _invoice_analysis_default_ids(meta, catalog)
    location_code = _resolve_location_code()
    today_iso = date.today().isoformat()
    date_from = str(body.get('date_from') or '').strip() or today_iso
    date_to = str(body.get('date_to') or '').strip() or today_iso
    extra_filters, order_by = _invoice_analysis_filters_order_from_body(body)
    inner_sql, params, _, err = _invoice_analysis_build_inner_sql(meta, catalog, picked, date_from, date_to, location_code, extra_filters=extra_filters, order_by=order_by)
    if err:
        return jsonify({'success': False, 'error': err}, 400)
    full_note = f'-- Run applies outer wrap: ROWNUM <= {_ANALYSIS_ROW_LIMIT} (:ti_lim)\n-- Bind names used below:\n'
    for k in sorted(params.keys()):
        full_note += f'--   :{k}\n'
    return jsonify({'success': True, 'sql': full_note + inner_sql, 'row_limit': _ANALYSIS_ROW_LIMIT})

def _ti_bind_preview_dict(params: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in (params or {}).items():
        if isinstance(v, Decimal):
            out[k] = str(v)
        elif hasattr(v, 'isoformat'):
            try:
                out[k] = v.isoformat()
            except Exception:
                out[k] = str(v)
        else:
            out[k] = v
    return out

@bp.route('/temporary-invoices/data-config', methods=['GET', 'POST'])
def temporary_invoices_data_config():
    """Show Temporary Invoices SQL + optional Execute preview / index DDL (tenant DB)."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if str(session.get('user') or '').strip().lower() != 'admin':
        flash('Data config is available only for the admin user.', 'warning')
        return redirect(url_for('temporary_invoices.temporary_invoices'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    else:
        loc_sess = session.get('location_code')
        if loc_sess:
            _apply_active_connection(loc_sess)
        elif session.get('user') == 'admin':
            _apply_active_connection('HO')
    location_code = _resolve_location_code()
    today = date.today().isoformat()
    date_from = (request.values.get('date_from') or '').strip() or today
    date_to = (request.values.get('date_to') or '').strip() or today
    try:
        row_limit = int((request.values.get('row_limit') or '500').strip())
    except (TypeError, ValueError):
        row_limit = 500
    row_limit = max(1, min(row_limit, 5000))
    exec_kind = (request.values.get('execute') or '').strip().lower()
    exec_rows: Optional[List[Dict[str, Any]]] = None
    exec_cols: Optional[List[str]] = None
    exec_label = ''
    exec_error: Optional[str] = None
    main_sql, main_params = _temporary_invoices_build_main_list_sql('', '', date_from, date_to, location_code)
    cust_sql, cust_params = _temporary_invoices_build_customer_dropdown_sql(date_from, date_to, location_code)
    sm_sql, sm_params = _temporary_invoices_build_salesman_dropdown_sql(date_from, date_to, location_code)
    index_ddls = _temporary_invoices_plan_index_ddls()
    if request.method == 'POST' and exec_kind:
        try:
            if exec_kind == 'main' and main_sql:
                exec_label = 'Main invoice grid (preview)'
                wrapped = _ti_sql_wrap_rownum_limit(main_sql, row_limit)
                exec_cols, exec_rows = _fetch_rows(wrapped, dict(main_params))
            elif exec_kind == 'customers' and cust_sql:
                exec_label = 'Customer dropdown (preview)'
                wrapped = _ti_sql_wrap_rownum_limit(cust_sql, row_limit)
                exec_cols, exec_rows = _fetch_rows(wrapped, dict(cust_params))
            elif exec_kind == 'salesmen' and sm_sql:
                exec_label = 'Salesman dropdown (preview)'
                wrapped = _ti_sql_wrap_rownum_limit(sm_sql, row_limit)
                exec_cols, exec_rows = _fetch_rows(wrapped, dict(sm_params))
            elif exec_kind == 'indexes':
                exec_label = 'Performance indexes (DDL)'
                _ensure_temporary_invoices_billhdr_indexes(force=True)
                flash('CREATE INDEX statements were attempted on this tenant schema (existing indexes skipped; privileges/errors logged server-side).', 'info')
            else:
                exec_error = 'Could not build SQL for this action.'
        except Exception as exc:
            exec_error = str(exc)
    if exec_cols is None and exec_rows and (len(exec_rows) > 0):
        exec_cols = list(exec_rows[0].keys())
    last_execute = exec_kind if request.method == 'POST' else ''
    return render_template('temporary_invoices/temporary_invoices_data_config.html', title='Sales Invoices · Data config', date_from=date_from, date_to=date_to, row_limit=row_limit, location_code=location_code, main_sql=main_sql or '', main_params_json=json.dumps(_ti_bind_preview_dict(main_params), indent=2), cust_sql=cust_sql or '', cust_params_json=json.dumps(_ti_bind_preview_dict(cust_params), indent=2), sm_sql=sm_sql or '', sm_params_json=json.dumps(_ti_bind_preview_dict(sm_params), indent=2), index_ddls=index_ddls, wrapped_preview_hint='Execute wraps your SELECT as SELECT * FROM ( … ) WHERE ROWNUM <= {}'.format(row_limit), exec_label=exec_label, exec_error=exec_error, exec_cols=exec_cols or [], exec_rows=exec_rows if exec_rows is not None else [], last_execute=last_execute)

@bp.route('/temporary-invoices')
def temporary_invoices():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    else:
        location_code = session.get('location_code')
        if location_code:
            _apply_active_connection(location_code)
        elif session.get('user') == 'admin':
            _apply_active_connection('HO')
    location_code = _resolve_location_code()
    customer_code = request.args.get('customercode', '').strip()
    salesman_code = request.args.get('salesmancode', '').strip()
    billno_search = request.args.get('billno', '').strip()
    orderno_search = request.args.get('orderno', '').strip()
    bill_type_q = request.args.get('bill_type', '').strip().upper()[:1]
    bill_types_kw = [bill_type_q] if bill_type_q in ('C', 'R', 'T') else None
    created_by_search = request.args.get('created_by', '').strip()
    net_min_arg = request.args.get('net_min', '').strip()
    net_max_arg = request.args.get('net_max', '').strip()
    txn_kind = (request.args.get('txn_kind') or 'all').strip().lower()
    if txn_kind not in ('all', 'sale', 'salesreturn'):
        txn_kind = 'all'
    today = date.today().isoformat()
    date_from = request.args.get('date_from', '').strip() or today
    date_to = request.args.get('date_to', '').strip() or today
    try:
        page = int((request.args.get('page') or '1').strip())
    except (TypeError, ValueError):
        page = 1
    page = max(1, page)
    try:
        per_page = int((request.args.get('per_page') or str(_TI_DEFAULT_PER_PAGE)).strip())
    except (TypeError, ValueError):
        per_page = _TI_DEFAULT_PER_PAGE
    per_page = max(_TI_MIN_PER_PAGE, min(_TI_MAX_PER_PAGE, per_page))
    invoices, has_more = _fetch_temporary_invoices_page(
        customer_code,
        salesman_code,
        date_from,
        date_to,
        location_code,
        page=page,
        per_page=per_page,
        billno_search=billno_search,
        orderno_search=orderno_search,
        bill_types=bill_types_kw,
        created_by_search=created_by_search,
        net_min=net_min_arg or None,
        net_max=net_max_arg or None,
        txn_kind=txn_kind,
    )
    ti_sl_base = (page - 1) * per_page
    list_base = url_for('temporary_invoices.temporary_invoices')
    q_common = _temporary_invoices_list_query_params(
        customer_code=customer_code,
        salesman_code=salesman_code,
        date_from=date_from,
        date_to=date_to,
        billno_search=billno_search,
        orderno_search=orderno_search,
        bill_type_q=bill_type_q,
        created_by_search=created_by_search,
        net_min=net_min_arg,
        net_max=net_max_arg,
        per_page=per_page,
        txn_kind=txn_kind,
    )
    ti_prev_url = None
    if page > 1:
        pq = dict(q_common)
        pq['page'] = str(page - 1)
        ti_prev_url = list_base + '?' + urlencode(pq)
    ti_next_url = None
    if has_more:
        nq = dict(q_common)
        nq['page'] = str(page + 1)
        ti_next_url = list_base + '?' + urlencode(nq)
    customers = _fetch_customers_list_for_dates(date_from, date_to, location_code)
    salesmen = _fetch_salesmen_list_for_dates(date_from, date_to, location_code)
    return render_template(
        'temporary_invoices/temporary_invoices.html',
        invoices=invoices,
        customers=customers,
        salesmen=salesmen,
        customer_code=customer_code,
        salesman_code=salesman_code,
        billno_search=billno_search,
        orderno_search=orderno_search,
        bill_type_filter=bill_type_q if bill_type_q in ('C', 'R', 'T') else '',
        created_by_search=created_by_search,
        net_min=net_min_arg,
        net_max=net_max_arg,
        txn_kind=txn_kind,
        date_from=date_from,
        date_to=date_to,
        ti_page=page,
        ti_per_page=per_page,
        ti_sl_base=ti_sl_base,
        ti_has_next=has_more,
        ti_prev_url=ti_prev_url,
        ti_next_url=ti_next_url,
    )

@bp.route('/temporary-invoices/modify/api/line-items')
def temporary_invoice_modify_line_items():
    """JSON line items for Modify Invoice (loaded after header via More button)."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    else:
        location_code_sess = session.get('location_code')
        if location_code_sess:
            _apply_active_connection(location_code_sess)
        elif session.get('user') == 'admin':
            _apply_active_connection('HO')
    location_code = _resolve_location_code()
    billno = request.args.get('billno', '').strip()
    if not billno:
        return jsonify({'success': False, 'error': 'Bill number is required'}, 400)
    transaction_date = _get_transaction_billdate(location_code)
    header = _fetch_invoice_header_only(billno, transaction_date, transaction_billdate_override=transaction_date)
    if not header:
        return jsonify({'success': False, 'error': 'Invoice not found'}, 404)
    items = _fetch_invoice_items_only(billno)
    return jsonify({'success': True, 'items': [_invoice_detail_serialize_mapping(r) for r in items]})

@bp.route('/temporary-invoices/modify', methods=['GET', 'POST'])
def temporary_invoice_modify():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    else:
        location_code = session.get('location_code')
        if location_code:
            _apply_active_connection(location_code)
        elif session.get('user') == 'admin':
            _apply_active_connection('HO')
    location_code = _resolve_location_code()
    message = ''
    billno = request.values.get('billno', '').strip()
    if request.method == 'POST' and billno:
        submitted_nonce = (request.form.get('save_nonce') or '').strip()
        if not verify_consume_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY, submitted_nonce):
            return redirect(url_for('temporary_invoices.temporary_invoice_modify', billno=billno, error='save_replay'))
        salesmancode = request.form.get('salesmancode', '').strip()
        customercode = request.form.get('customercode', '').strip()
        customername = request.form.get('customername', '').strip().upper()
        salesmanname = request.form.get('salesmanname', '').strip()
        billtype = request.form.get('billtype', '').strip()
        if not customername and customercode:
            customername = _lookup_customer_name(customercode)
        if not salesmanname and salesmancode:
            salesmanname = _lookup_salesman_name(salesmancode)
        order_no_raw = request.form.get('orderno', '').strip()
        if not order_no_raw:
            flash('Order No is required.', 'error')
            return redirect(url_for('temporary_invoices.temporary_invoice_modify', billno=billno))
        order_no_val = _pos_orderno_for_db({'orderno': order_no_raw}, max_len=80)
        try:
            exclude_billno = int(billno)
        except (TypeError, ValueError):
            exclude_billno = 0
        dup_err = _sales_orderno_conflict_message(
            location_code,
            order_no_val,
            exclude_invoice_billno=exclude_billno if exclude_billno > 0 else None,
        )
        if dup_err:
            flash(dup_err, 'error')
            return redirect(url_for('temporary_invoices.temporary_invoice_modify', billno=billno))
        with _get_connection() as conn:
            _update_invoice_header(
                billno=billno,
                salesmancode=salesmancode,
                customercode=customercode,
                customername=customername,
                salesmanname=salesmanname,
                billtype=billtype,
                orderno=order_no_val,
                conn=conn,
            )
            conn.commit()
        flash(f'Invoice {billno} modified successfully.', 'success')
        return redirect(url_for('temporary_invoices.temporary_invoices'))
    if request.method == 'GET' and request.args.get('success') == '1':
        # Legacy success redirect — send to list
        flash('Invoice modified successfully.', 'success')
        return redirect(url_for('temporary_invoices.temporary_invoices'))
    error_message = ''
    err_arg = request.args.get('error') or ''
    if err_arg == 'save_replay':
        error_message = 'Duplicate or invalid save. If this bill was already saved, search again. Otherwise reload the page once for a new save token, then try Modify once.'
    header = {}
    if billno:
        transaction_date = _get_transaction_billdate(location_code)
        header = _fetch_invoice_header_only(billno, transaction_date, transaction_billdate_override=transaction_date)
    salesmen = _fetch_salesmen_list_all() if header else []
    return render_template(
        'temporary_invoices/temporary_invoice_modify.html',
        billno=billno,
        header=header,
        line_items_api_url=url_for('temporary_invoices.temporary_invoice_modify_line_items'),
        message=message,
        error_message=error_message,
        salesmen=salesmen,
    )
