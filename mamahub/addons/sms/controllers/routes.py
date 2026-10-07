"""SMS blueprint"""
from pathlib import Path
import os
import urllib.parse
import logging
from typing import Dict, List, Any, Tuple, Optional
import requests
from nexa_http import Blueprint, jsonify, redirect, render_template, request, session, url_for
logger = logging.getLogger(__name__)
_whatsapp_pdf_tokens = {}
from db import DATABASES, set_active_db_key, set_active_db_host, _fetch_rows, _fetch_rows_with_key, _detect_column, _get_connection, _get_table_columns, _table_exists
_ADDON_ROOT = Path(__file__).resolve().parents[1]
bp = Blueprint('sms', __name__, template_folder=str(_ADDON_ROOT / 'views' / 'templates'))

def _normalize_db_key(db_key: str) -> str:
    """Normalize db key values to known DATABASES keys."""
    if not db_key:
        return ''
    key = str(db_key).strip().upper()
    if key == 'TESTDB':
        return 'TESDB'
    return key

def _apply_active_connection(location_code: str) -> None:
    """Apply active database connection based on location_code"""
    normalized_code = _normalize_db_key(location_code)
    if normalized_code in DATABASES:
        db_config = DATABASES[normalized_code]
        print(f"[DEBUG _apply_active_connection] Connecting to {normalized_code}: {db_config['user']}@{db_config['dsn']}")
        set_active_db_key(normalized_code)
        set_active_db_host(None)
    else:
        set_active_db_key('HO')
        set_active_db_host(None)

def _normalize_phone(phone: str) -> str:
    """Normalize phone number - remove 974 prefix if present"""
    if not phone:
        return ''
    cleaned = phone.strip().replace(' ', '').replace('-', '')
    if cleaned.startswith('+974'):
        cleaned = cleaned[4:]
    elif cleaned.startswith('974'):
        cleaned = cleaned[3:]
    return cleaned

def send_sms(message: str, phone: str, mask: str=None) -> Tuple[bool, str]:
    """Send SMS via Vodafone Connect SMS API"""
    base_url = 'https://connectsms.vodafone.com.qa/SMSConnect/SendServlet'
    sms_mask = mask or os.getenv('SMS_MASK', 'RAWABI')
    params = {'application': os.getenv('SMS_APP_USERNAME', 'http_gw1238'), 'password': os.getenv('SMS_APP_PASSWORD', 'b6pz4gEp'), 'content': message, 'destination': _normalize_phone(phone), 'source': os.getenv('SMS_SOURCE', '97489'), 'mask': sms_mask}
    full_url = f'{base_url}?{urllib.parse.urlencode(params)}'
    try:
        response = requests.get(full_url, timeout=10)
        if response.status_code == 200:
            return (True, response.text)
        return (False, f'HTTP {response.status_code}: {response.text}')
    except Exception as exc:
        return (False, f'Error sending SMS: {exc}')

def get_masks_from_table() -> List[Dict[str, Any]]:
    """Get mask options from TBLSMS table MASK column"""
    try:
        sms_table = None
        for table_name in ['TBLSMS', 'tblsms', 'SMS', 'sms']:
            try:
                mask_col = _detect_column(table_name, ['MASK', 'MASKNAME', 'MASK_NAME'])
                if mask_col:
                    sms_table = table_name
                    break
            except Exception:
                continue
        if not sms_table:
            print('[DEBUG] Could not detect TBLSMS table, using default mask')
            return []
        mask_col = _detect_column(sms_table, ['MASK', 'MASKNAME', 'MASK_NAME'])
        if not mask_col:
            print('[DEBUG] Could not detect MASK column in TBLSMS table')
            return []
        query = f'\n            SELECT DISTINCT\n                {mask_col} AS mask\n            FROM {sms_table}\n            WHERE {mask_col} IS NOT NULL\n            ORDER BY {mask_col}\n        '
        _, rows = _fetch_rows(query, {})
        return rows
    except Exception as e:
        print(f'[ERROR get_masks_from_table] {e}')
        import traceback
        traceback.print_exc()
        return []

def get_contact_number_from_table(location_code: str=None) -> str:
    """Get contact number from tblsms table - using query: select mask,contactno from tblsms"""
    try:
        print(f'[DEBUG get_contact_number_from_table] Starting fetch, location_code: {location_code}')
        queries = ['SELECT TO_CHAR(CONTACTNO) AS contactno FROM tblsms WHERE CONTACTNO IS NOT NULL AND ROWNUM = 1', 'SELECT CONTACTNO AS contactno FROM tblsms WHERE CONTACTNO IS NOT NULL AND ROWNUM = 1', 'SELECT TO_CHAR(contactno) AS contactno FROM tblsms WHERE contactno IS NOT NULL AND ROWNUM = 1', 'SELECT contactno AS contactno FROM tblsms WHERE contactno IS NOT NULL AND ROWNUM = 1', 'SELECT TO_CHAR(CONTACTNO) AS contactno FROM tblsms WHERE ROWNUM = 1', 'SELECT CONTACTNO AS contactno FROM tblsms WHERE ROWNUM = 1']
        db_keys = []
        session_dbkey = _normalize_db_key(session.get('tenant_id'))
        session_location = _normalize_db_key(session.get('location_code'))
        if session_dbkey:
            db_keys.append(session_dbkey)
        if session_location and session_location not in db_keys:
            db_keys.append(session_location)
        if 'HO' not in db_keys:
            db_keys.append('HO')
        for db_key in db_keys:
            for query in queries:
                try:
                    print(f'[DEBUG get_contact_number_from_table] Executing query on {db_key}: {query}')
                    _, rows = _fetch_rows_with_key(db_key, query, {})
                    print(f'[DEBUG get_contact_number_from_table] Query returned {(len(rows) if rows else 0)} rows')
                    if rows and rows[0]:
                        contact_no = rows[0].get('contactno', '')
                        print(f'[DEBUG get_contact_number_from_table] Raw contact_no: {contact_no} (type: {type(contact_no)})')
                        if contact_no is not None:
                            contact_str = str(contact_no).strip()
                            if contact_str:
                                print(f"[DEBUG get_contact_number_from_table] Success! Found contact number: '{contact_str}'")
                                return contact_str
                except Exception as e:
                    print(f'[DEBUG get_contact_number_from_table] Query failed on {db_key}: {e}')
                    import traceback
                    traceback.print_exc()
                    continue
        print('[DEBUG get_contact_number_from_table] No contact number found, returning empty string')
        return ''
    except Exception as e:
        print(f'[ERROR get_contact_number_from_table] {e}')
        import traceback
        traceback.print_exc()
        return ''

def get_credit_customers_with_outstanding(date_from: str='', date_to: str='') -> List[Dict[str, Any]]:
    """Get credit customers with outstanding from TBLCREDITSETTLEMENT.
    Outstanding logic matches Credit Receipt invoice rows: SUM(balance) where flag = 'B' and balance <> 0.
    Date filters are used for collection amount only.
    """
    try:
        credit_table = None
        for t in ['TBLCREDITSETTLEMENT', 'tblcreditsettlement']:
            if _table_exists(t):
                credit_table = t
                break
        if not credit_table:
            print('[DEBUG get_credit_customers_with_outstanding] TBLCREDITSETTLEMENT not found')
            return []
        hdr_cust = _detect_column(credit_table, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'CUSTCODE'])
        hdr_billno = _detect_column(credit_table, ['BILLNO', 'BILL_NO', 'INVOICENO'])
        hdr_amount = _detect_column(credit_table, ['BILLAMOUNT', 'BILL_AMOUNT', 'AMOUNT'])
        hdr_balance = _detect_column(credit_table, ['BALANCE', 'OUTSTANDING', 'NETBALANCE'])
        hdr_flag = _detect_column(credit_table, ['FLAG', 'flag', 'FLAG_CODE', 'PFLAG', 'P_FLAG'])
        if not all([hdr_cust, hdr_billno, hdr_balance]):
            print('[DEBUG get_credit_customers_with_outstanding] Missing columns in TBLCREDITSETTLEMENT')
            return []
        hdr_billdate = _detect_column(credit_table, ['BILLDATE', 'BILL_DATE', 'INVOICEDATE', 'INVOICE_DATE'])
        cust_table = None
        cust_code_col = None
        cust_name_col = None
        cust_phone_col = None
        for t in ['CUSTOMER', 'CUSTOMERS', 'customer', 'customers']:
            try:
                cc = _detect_column(t, ['CUSTOMERCODE', 'CUST_CODE', 'CUSTOMER_CODE', 'CODE'])
                if not cc:
                    continue
                cust_table = t
                cust_code_col = cc
                cust_name_col = _detect_column(t, ['CUSTOMERNAME', 'CUST_NAME', 'CUSTOMER_NAME', 'NAME'])
                cust_phone_col = _detect_column(t, ['MOBILE', 'MOBILENO', 'PHONENO', 'PHONE_NO', 'PHONE'])
                break
            except Exception:
                continue
        if not cust_table or not cust_code_col:
            print('[DEBUG get_credit_customers_with_outstanding] Customer table not found')
            return []
        flag_filter = f"AND hdr.{hdr_flag} = 'B'" if hdr_flag else ''
        balance_filter = f'AND NVL(hdr.{hdr_balance}, 0) <> 0'
        date_filter = ''
        params = {}
        name_sql = f'c.{cust_name_col}' if cust_name_col else 'NULL'
        phone_sql = f'c.{cust_phone_col}' if cust_phone_col else 'NULL'
        billno_count_sql = f'COUNT(DISTINCT hdr.{hdr_billno})'
        last_billdate_sql = f'MAX(hdr.{hdr_billdate})' if hdr_billdate else 'NULL'
        query = f'\n            SELECT\n                ROW_NUMBER() OVER (ORDER BY hdr.{hdr_cust}) AS slno,\n                hdr.{hdr_cust} AS customercode,\n                {name_sql} AS customername,\n                {phone_sql} AS phoneno,\n                {billno_count_sql} AS invoicecount,\n                {last_billdate_sql} AS lastbilldate,\n                SUM(NVL(hdr.{hdr_balance}, 0)) AS outstandingamount\n            FROM {credit_table} hdr\n            LEFT JOIN {cust_table} c ON hdr.{hdr_cust} = c.{cust_code_col}\n            WHERE 1=1\n            {flag_filter}\n            {balance_filter}\n            {date_filter}\n            GROUP BY hdr.{hdr_cust}, {name_sql}, {phone_sql}\n            ORDER BY hdr.{hdr_cust}\n        '
        _, rows = _fetch_rows(query, params)
        collection_map: Dict[str, float] = {}
        try:
            cr_table = None
            for t in ['TBLCRSETTLEMENT', 'tblcrsettlement']:
                if _table_exists(t):
                    cr_table = t
                    break
            if cr_table:
                cr_cust = _detect_column(cr_table, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'CUSTCODE'])
                cr_paidamount = _detect_column(cr_table, ['PAIDAMOUNT', 'PAID_AMOUNT', 'PAIDAMT', 'PAID'])
                cr_paiddate = _detect_column(cr_table, ['PAIDDATE', 'PAIDATE', 'PAID_DATE', 'PAYMENTDATE', 'PAYMENT_DATE'])
                if cr_cust and cr_paidamount and cr_paiddate:
                    c_where = []
                    c_params: Dict[str, Any] = {}
                    if date_from:
                        c_where.append(f"cs.{cr_paiddate} >= TO_DATE(:date_from, 'YYYY-MM-DD')")
                        c_params['date_from'] = date_from
                    if date_to:
                        c_where.append(f"cs.{cr_paiddate} <= TO_DATE(:date_to, 'YYYY-MM-DD')")
                        c_params['date_to'] = date_to
                    where_sql = ' AND ' + ' AND '.join(c_where) if c_where else ''
                    c_query = f'\n                        SELECT\n                            UPPER(TRIM(cs.{cr_cust})) AS customercode,\n                            SUM(NVL(cs.{cr_paidamount}, 0)) AS collectionamount\n                        FROM {cr_table} cs\n                        WHERE 1=1\n                        {where_sql}\n                        GROUP BY UPPER(TRIM(cs.{cr_cust}))\n                    '
                    _, c_rows = _fetch_rows(c_query, c_params)
                    for cr in c_rows or []:
                        key = str(cr.get('customercode') or '').strip().upper()
                        if key:
                            collection_map[key] = float(cr.get('collectionamount') or 0)
        except Exception as ce:
            print(f'[DEBUG get_credit_customers_with_outstanding] collection fetch from tblcrsettlement failed: {ce}')
        for r in rows or []:
            r['pendingamount'] = 0.0
            cust_key = str(r.get('customercode') or '').strip().upper()
            r['collectionamount'] = float(collection_map.get(cust_key, 0.0))
        return rows or []
    except Exception as e:
        print(f'[ERROR get_credit_customers_with_outstanding] {e}')
        import traceback
        traceback.print_exc()
        return []

def get_cash_customers_with_outstanding(date_from: str='', date_to: str='') -> List[Dict[str, Any]]:
    """Get customers with outstanding balance from tblsettlement (all customers, not restricted to invoicecode=1)."""
    try:
        temp_table = None
        for table_name in ['TBLSETTLEMENT', 'tblsettlement']:
            try:
                temp_customer_col = _detect_column(table_name, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'CUSTCODE', 'CUST_CODE'])
                temp_balance_col = _detect_column(table_name, ['BALANCE', 'OUTSTANDING', 'NETBALANCE'])
                if temp_customer_col and temp_balance_col:
                    temp_table = table_name
                    print(f'[DEBUG] Using {temp_table} for invoice count and outstanding amount')
                    break
            except Exception:
                continue
        if not temp_table:
            print('[ERROR] Could not detect tblsettlement table or columns')
            return []
        customer_table = None
        customer_code_col = None
        customer_name_col = None
        customer_address_col = None
        customer_phone_col = None
        customer_invoice_col = None
        for table_name in ['CUSTOMER', 'CUSTOMERS', 'customers', 'customer']:
            try:
                code_col = _detect_column(table_name, ['CUSTOMERCODE', 'CUST_CODE', 'CUSTOMER_CODE', 'CODE'])
                if not code_col:
                    continue
                customer_table = table_name
                customer_code_col = code_col
                customer_name_col = _detect_column(table_name, ['CUSTOMERNAME', 'CUST_NAME', 'CUSTOMER_NAME', 'NAME'])
                customer_address_col = _detect_column(table_name, ['ADDRESS', 'ADDR', 'CUSTOMERADDRESS', 'CUST_ADDRESS'])
                customer_phone_col = _detect_column(table_name, ['MOBILE', 'MOBILENO', 'MOBILE_NO', 'PHONENO', 'PHONE_NO', 'PHONE'])
                customer_whatsapp_col = _detect_column(table_name, ['WHATSAPP', 'WHATSAPP_NO', 'WHATSAPPNO', 'whatsapp'])
                customer_invoice_col = _detect_column(table_name, ['INVOICECODE', 'INVOICE_CODE', 'INVOICETYPE', 'TYPECODE'])
                break
            except Exception as e:
                print(f'[DEBUG] Failed to detect columns in {table_name}: {e}')
                continue
        if not customer_table or not customer_code_col:
            print('[ERROR] Could not detect customer table or columns')
            return []
        temp_customer_col = _detect_column(temp_table, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'CUSTCODE', 'CUST_CODE'])
        temp_balance_col = _detect_column(temp_table, ['BALANCE', 'OUTSTANDING', 'NETBALANCE'])
        temp_billno_col = _detect_column(temp_table, ['BILLNO', 'BILL_NO', 'INVOICENO', 'INVOICE_NO', 'INVOICENUMBER'])
        temp_billdate_col = _detect_column(temp_table, ['BILLDATE', 'BILL_DATE', 'INVOICEDATE', 'INVOICE_DATE', 'BILLINGDATE'])
        temp_flag_col = _detect_column(temp_table, ['FLAG', 'FLAG_CODE', 'STATUS_FLAG'])
        temp_paidamount_col = _detect_column(temp_table, ['PAIDAMOUNT', 'PAID_AMOUNT', 'PAIDAMT', 'PAID'])
        temp_paidate_col = _detect_column(temp_table, ['PAIDATE', 'PAID_DATE', 'PAYMENTDATE', 'PAYMENT_DATE'])
        if not temp_customer_col or not temp_balance_col:
            print(f'[ERROR] Could not detect columns in {temp_table}')
            return []
        name_sql = f'c.{customer_name_col}' if customer_name_col else 'NULL'
        address_sql = f'c.{customer_address_col}' if customer_address_col else 'NULL'
        phone_sql = f'c.{customer_phone_col}' if customer_phone_col else 'NULL'
        whatsapp_sql = f'c.{customer_whatsapp_col}' if customer_whatsapp_col else phone_sql
        invoice_filter = ''
        billno_count_sql = f'COUNT(DISTINCT ts.{temp_billno_col})' if temp_billno_col else 'COUNT(*)'
        last_billdate_sql = f'MAX(ts.{temp_billdate_col})' if temp_billdate_col else 'NULL'
        collection_sql = '0'
        collection_table = None
        collection_customer_col = None
        collection_paidamount_col = None
        collection_paidate_col = None
        collection_flag_col = None
        for table_name in ['tbltempsettlement', 'TBLTEMPSETTLEMENT']:
            try:
                print(f'[DEBUG] Checking if table {table_name} exists...')
                table_exists = _table_exists(table_name)
                print(f'[DEBUG] Table {table_name} exists: {table_exists}')
                if not table_exists:
                    print(f'[DEBUG] Table {table_name} does not exist, trying next table name')
                    continue
                print(f'[DEBUG] Trying to detect columns in {table_name}')
                cust_col = _detect_column(table_name, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'CUSTCODE', 'CUST_CODE'])
                print(f'[DEBUG] {table_name} - customer column: {cust_col}')
                paidamt_col = _detect_column(table_name, ['PAIDAMOUNT', 'PAID_AMOUNT', 'PAIDAMT', 'PAID'])
                print(f'[DEBUG] {table_name} - paidamount column: {paidamt_col}')
                paidate_col = _detect_column(table_name, ['PAIDDATE', 'PAIDATE', 'PAID_DATE', 'PAYMENTDATE', 'PAYMENT_DATE'])
                print(f'[DEBUG] {table_name} - paidate column: {paidate_col}')
                flag_col = _detect_column(table_name, ['FLAG', 'FLAG_CODE', 'STATUS_FLAG'])
                print(f'[DEBUG] {table_name} - flag column: {flag_col}')
                if cust_col and paidamt_col and paidate_col:
                    collection_table = table_name
                    collection_customer_col = cust_col
                    collection_paidamount_col = paidamt_col
                    collection_paidate_col = paidate_col
                    collection_flag_col = flag_col
                    print(f'[DEBUG] Successfully detected collection table: {table_name} (for collection amount only)')
                    break
                else:
                    print(f'[DEBUG] {table_name} missing required columns: cust_col={cust_col}, paidamt_col={paidamt_col}, paidate_col={paidate_col}')
            except Exception as e:
                print(f'[DEBUG] Error detecting columns in {table_name}: {e}')
                import traceback
                traceback.print_exc()
                continue
        params = {}
        collection_date_filter = ''
        collection_flag_filter = ''
        collection_sql = '0'
        pending_table = None
        pending_customer_col = None
        pending_amount_col = None
        pending_billtype_col = None
        pending_billdate_col = None
        for table_name in ['BILLHDR', 'billhdr', 'BILL_HEADER', 'bill_header']:
            try:
                print(f'[DEBUG] Checking if table {table_name} exists...')
                table_exists = _table_exists(table_name)
                print(f'[DEBUG] Table {table_name} exists: {table_exists}')
                if not table_exists:
                    continue
                cust_col = _detect_column(table_name, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'CUSTCODE', 'CUST_CODE'])
                amount_col = _detect_column(table_name, ['NETBILLAMOUNT', 'NET_BILL_AMOUNT', 'NETAMOUNT', 'NET_AMOUNT', 'BILLAMOUNT', 'BILL_AMOUNT'])
                billtype_col = _detect_column(table_name, ['BILLTYPE', 'BILL_TYPE', 'TYPE', 'BILLTYPECODE'])
                billdate_col = _detect_column(table_name, ['BILLDATE', 'BILL_DATE', 'BILLINGDATE', 'BILLING_DATE'])
                if cust_col and amount_col and billtype_col and billdate_col:
                    pending_table = table_name
                    pending_customer_col = cust_col
                    pending_amount_col = amount_col
                    pending_billtype_col = billtype_col
                    pending_billdate_col = billdate_col
                    print(f'[DEBUG] Successfully detected pending table: {table_name}')
                    break
            except Exception as e:
                print(f'[DEBUG] Error detecting columns in {table_name}: {e}')
                continue
        if collection_table and collection_customer_col and collection_paidamount_col and collection_paidate_col:
            logger.info(f'[DEBUG] Collection table detected: {collection_table}')
            logger.info(f'[DEBUG] Collection columns: customer={collection_customer_col}, paidamount={collection_paidamount_col}, paidate={collection_paidate_col}, flag={collection_flag_col}')
            print(f'[DEBUG] Collection table detected: {collection_table}')
            print(f'[DEBUG] Collection columns: customer={collection_customer_col}, paidamount={collection_paidamount_col}, paidate={collection_paidate_col}, flag={collection_flag_col}')
            print(f"[DEBUG] Date filters received - date_from: '{date_from}', date_to: '{date_to}'")
            collection_date_filter = f' AND ts2.{collection_paidate_col} IS NOT NULL'
            if date_from and date_from.strip():
                try:
                    from datetime import datetime
                    date_obj = datetime.strptime(date_from.strip(), '%Y-%m-%d')
                    oracle_date_from = date_obj.strftime('%d/%b/%Y').lower()
                    oracle_date_from_escaped = oracle_date_from.replace("'", "''")
                    collection_date_filter += f" AND ts2.{collection_paidate_col} >= TO_DATE('{oracle_date_from_escaped}', 'DD/MON/YYYY')"
                    params['date_from'] = date_from.strip()
                    print(f'[DEBUG] Applied date_from filter: {date_from.strip()} -> Oracle format: {oracle_date_from}')
                except ValueError as ve:
                    print(f"[DEBUG] Invalid date_from format '{date_from}': {ve}. Skipping date_from filter.")
            else:
                print(f'[DEBUG] No date_from filter (empty or None)')
            if date_to and date_to.strip():
                try:
                    from datetime import datetime
                    date_obj = datetime.strptime(date_to.strip(), '%Y-%m-%d')
                    oracle_date_to = date_obj.strftime('%d/%b/%Y').lower()
                    oracle_date_to_escaped = oracle_date_to.replace("'", "''")
                    collection_date_filter += f" AND ts2.{collection_paidate_col} <= TO_DATE('{oracle_date_to_escaped}', 'DD/MON/YYYY')"
                    params['date_to'] = date_to.strip()
                    print(f'[DEBUG] Applied date_to filter: {date_to.strip()} -> Oracle format: {oracle_date_to}')
                except ValueError as ve:
                    print(f"[DEBUG] Invalid date_to format '{date_to}': {ve}. Skipping date_to filter.")
            else:
                print(f'[DEBUG] No date_to filter (empty or None)')
            collection_flag_filter = ''
            if collection_flag_col:
                collection_flag_filter = f" AND ts2.{collection_flag_col} = 'R'"
            else:
                print(f'[DEBUG] Warning: Flag column not detected in {collection_table}, collection query will not filter by flag')
            test_collection_query = f'\n                SELECT COUNT(*) AS cnt, NVL(SUM(NVL({collection_paidamount_col}, 0)), 0) AS total\n                FROM {collection_table}\n                WHERE 1=1\n                {collection_flag_filter}\n            '
            try:
                _, test_collection_rows = _fetch_rows(test_collection_query, {})
                if test_collection_rows:
                    test_collection_count = test_collection_rows[0].get('cnt', 0)
                    test_collection_total = test_collection_rows[0].get('total', 0)
                    logger.info(f"[DEBUG] Collection test: Found {test_collection_count} rows with flag='R', total amount = {test_collection_total}")
                    print(f"[DEBUG] Collection test: Found {test_collection_count} rows with flag='R', total amount = {test_collection_total}")
                    if test_collection_count > 0:
                        sample_date_filter = f' AND {collection_paidate_col} IS NOT NULL'
                        if date_from and date_to:
                            try:
                                from datetime import datetime
                                date_from_obj = datetime.strptime(date_from.strip(), '%Y-%m-%d')
                                date_to_obj = datetime.strptime(date_to.strip(), '%Y-%m-%d')
                                oracle_date_from = date_from_obj.strftime('%d/%b/%Y').lower()
                                oracle_date_to = date_to_obj.strftime('%d/%b/%Y').lower()
                                oracle_date_from_escaped = oracle_date_from.replace("'", "''")
                                oracle_date_to_escaped = oracle_date_to.replace("'", "''")
                                sample_date_filter += f" AND {collection_paidate_col} BETWEEN TO_DATE('{oracle_date_from_escaped}', 'DD/MON/YYYY') AND TO_DATE('{oracle_date_to_escaped}', 'DD/MON/YYYY')"
                            except ValueError:
                                pass
                        elif date_from:
                            try:
                                from datetime import datetime
                                date_from_obj = datetime.strptime(date_from.strip(), '%Y-%m-%d')
                                oracle_date_from = date_from_obj.strftime('%d/%b/%Y').lower()
                                oracle_date_from_escaped = oracle_date_from.replace("'", "''")
                                sample_date_filter += f" AND {collection_paidate_col} >= TO_DATE('{oracle_date_from_escaped}', 'DD/MON/YYYY')"
                            except ValueError:
                                pass
                        elif date_to:
                            try:
                                from datetime import datetime
                                date_to_obj = datetime.strptime(date_to.strip(), '%Y-%m-%d')
                                oracle_date_to = date_to_obj.strftime('%d/%b/%Y').lower()
                                oracle_date_to_escaped = oracle_date_to.replace("'", "''")
                                sample_date_filter += f" AND {collection_paidate_col} <= TO_DATE('{oracle_date_to_escaped}', 'DD/MON/YYYY')"
                            except ValueError:
                                pass
                        sample_customer_query = f'\n                            SELECT * FROM (\n                                SELECT {collection_customer_col} AS cust_code, \n                                       NVL(SUM(NVL({collection_paidamount_col}, 0)), 0) AS total\n                                FROM {collection_table}\n                                WHERE 1=1\n                                {collection_flag_filter}\n                                {sample_date_filter}\n                                GROUP BY {collection_customer_col}\n                            ) WHERE ROWNUM <= 5\n                        '
                        try:
                            _, sample_rows = _fetch_rows(sample_customer_query, {})
                            print(f'[DEBUG] Sample collection customers: {sample_rows}')
                        except Exception as sample_e:
                            print(f'[DEBUG] Sample customer query failed: {sample_e}')
                            import traceback
                            traceback.print_exc()
            except Exception as test_collection_e:
                print(f'[DEBUG] Collection test query failed: {test_collection_e}')
                import traceback
                traceback.print_exc()
            collection_sql = f'(\n                SELECT NVL(SUM(NVL(ts2.{collection_paidamount_col}, 0)), 0)\n                FROM {collection_table} ts2\n                WHERE ts2.{collection_customer_col} = NVL(c.{customer_code_col}, ts.{temp_customer_col})\n                {collection_date_filter}\n                {collection_flag_filter}\n            )'
            logger.info(f'[DEBUG] Collection SQL subquery: {collection_sql}')
            logger.info(f'[DEBUG] Collection date filter: {collection_date_filter}')
            logger.info(f'[DEBUG] Collection flag filter: {collection_flag_filter}')
            print(f'[DEBUG] Collection SQL subquery: {collection_sql}')
            print(f'[DEBUG] Collection date filter: {collection_date_filter}')
            print(f'[DEBUG] Collection flag filter: {collection_flag_filter}')
        else:
            print(f'[DEBUG] Collection table/columns not detected. collection_table={collection_table}, customer_col={collection_customer_col}, paidamount_col={collection_paidamount_col}, paidate_col={collection_paidate_col}')
        flag_filter = ''
        if temp_flag_col:
            flag_filter = f"AND ts.{temp_flag_col} = 'B'"
        query = f'\n            SELECT \n                ROW_NUMBER() OVER (ORDER BY NVL(c.{customer_code_col}, ts.{temp_customer_col})) AS slno,\n                NVL(c.{customer_code_col}, ts.{temp_customer_col}) AS customercode,\n                {name_sql} AS customername,\n                {address_sql} AS address,\n                {phone_sql} AS phoneno,\n                {whatsapp_sql} AS whatsappno,\n                {collection_sql} AS collectionamount,\n                {billno_count_sql} AS invoicecount,\n                {last_billdate_sql} AS lastbilldate,\n                SUM(NVL(ts.{temp_balance_col}, 0)) AS outstandingamount\n            FROM {temp_table} ts\n            LEFT JOIN {customer_table} c ON ts.{temp_customer_col} = c.{customer_code_col}\n            WHERE ts.{temp_balance_col} > 0\n            {flag_filter}\n            {invoice_filter}\n            GROUP BY NVL(c.{customer_code_col}, ts.{temp_customer_col}), {name_sql}, {address_sql}, {phone_sql}, {whatsapp_sql}\n            ORDER BY NVL(c.{customer_code_col}, ts.{temp_customer_col})\n        '
        print(f"[DEBUG] Executing query with date_from: '{date_from}', date_to: '{date_to}'")
        query_from_settlement = f'\n            SELECT \n                NVL(c.{customer_code_col}, ts.{temp_customer_col}) AS customercode,\n                {name_sql} AS customername,\n                {address_sql} AS address,\n                {phone_sql} AS phoneno,\n                {whatsapp_sql} AS whatsappno,\n                {billno_count_sql} AS invoicecount,\n                {last_billdate_sql} AS lastbilldate,\n                SUM(NVL(ts.{temp_balance_col}, 0)) AS outstandingamount\n            FROM {temp_table} ts\n            LEFT JOIN {customer_table} c ON ts.{temp_customer_col} = c.{customer_code_col}\n            WHERE ts.{temp_balance_col} > 0\n            {flag_filter}\n            {invoice_filter}\n            GROUP BY NVL(c.{customer_code_col}, ts.{temp_customer_col}), {name_sql}, {address_sql}, {phone_sql}, {whatsapp_sql}\n        '
        query_from_collection = ''
        if collection_table and collection_customer_col and collection_paidamount_col and collection_paidate_col and date_from and date_to:
            try:
                from datetime import datetime
                date_from_obj = datetime.strptime(date_from.strip(), '%Y-%m-%d')
                date_to_obj = datetime.strptime(date_to.strip(), '%Y-%m-%d')
                oracle_date_from = date_from_obj.strftime('%d/%b/%Y').lower()
                oracle_date_to = date_to_obj.strftime('%d/%b/%Y').lower()
                oracle_date_from_escaped = oracle_date_from.replace("'", "''")
                oracle_date_to_escaped = oracle_date_to.replace("'", "''")
                collection_customer_flag_filter = ''
                if collection_flag_col:
                    collection_customer_flag_filter = f" AND ts2.{collection_flag_col} = 'R'"
                name_col_sql = f'c2.{customer_name_col}' if customer_name_col else 'NULL'
                address_col_sql = f'c2.{customer_address_col}' if customer_address_col else 'NULL'
                phone_col_sql = f'c2.{customer_phone_col}' if customer_phone_col else 'NULL'
                whatsapp_col_sql = f'c2.{customer_whatsapp_col}' if customer_whatsapp_col else phone_col_sql
                query_from_collection = f"\n                    UNION ALL\n                    SELECT DISTINCT\n                        ts2.{collection_customer_col} AS customercode,\n                        {name_col_sql} AS customername,\n                        {address_col_sql} AS address,\n                        {phone_col_sql} AS phoneno,\n                        {whatsapp_col_sql} AS whatsappno,\n                        0 AS invoicecount,\n                        NULL AS lastbilldate,\n                        0 AS outstandingamount\n                    FROM {collection_table} ts2\n                    LEFT JOIN {customer_table} c2 ON ts2.{collection_customer_col} = c2.{customer_code_col}\n                    WHERE ts2.{collection_paidate_col} IS NOT NULL\n                    AND ts2.{collection_paidate_col} BETWEEN TO_DATE('{oracle_date_from_escaped}', 'DD/MON/YYYY') AND TO_DATE('{oracle_date_to_escaped}', 'DD/MON/YYYY')\n                    {collection_customer_flag_filter}\n                    AND ts2.{collection_customer_col} NOT IN (\n                        SELECT DISTINCT NVL(c.{customer_code_col}, ts.{temp_customer_col})\n                        FROM {temp_table} ts\n                        LEFT JOIN {customer_table} c ON ts.{temp_customer_col} = c.{customer_code_col}\n                        WHERE ts.{temp_balance_col} > 0\n                        {flag_filter}\n                        {invoice_filter}\n                    )\n                "
                print(f'[DEBUG] Added UNION query to include customers with collection but no outstanding balance')
            except ValueError as ve:
                print(f'[DEBUG] Failed to build UNION query for collection customers: {ve}')
        query_without_collection = f'\n            SELECT \n                ROW_NUMBER() OVER (ORDER BY customercode) AS slno,\n                customercode,\n                MAX(customername) AS customername,\n                MAX(address) AS address,\n                MAX(phoneno) AS phoneno,\n                MAX(whatsappno) AS whatsappno,\n                SUM(invoicecount) AS invoicecount,\n                MAX(lastbilldate) AS lastbilldate,\n                SUM(outstandingamount) AS outstandingamount,\n                0 AS collectionamount,\n                0 AS pendingamount\n            FROM (\n                {query_from_settlement}\n                {query_from_collection}\n            )\n            GROUP BY customercode\n            ORDER BY customercode\n        '
        rows = []
        try:
            _, rows = _fetch_rows(query_without_collection, {})
            print(f'[DEBUG] Main query returned {len(rows)} customers')
            if len(rows) == 0:
                print(f'[DEBUG] No customers found matching filters')
            elif collection_table and collection_customer_col and collection_paidamount_col and collection_paidate_col:
                if not (date_from or date_to):
                    print(f'[DEBUG] Skipping collection calculation: No date filters provided')
                    for row in rows:
                        row['collectionamount'] = 0.0
                else:
                    print(f'[DEBUG] Adding collection amounts for {len(rows)} customers (batch query)...')
                    print(f"[DEBUG] Date filters: date_from='{date_from}', date_to='{date_to}'")
                    try:
                        batch_date_filter = f' AND {collection_paidate_col} IS NOT NULL'
                        if date_from and date_from.strip() and date_to and date_to.strip():
                            try:
                                from datetime import datetime
                                date_from_obj = datetime.strptime(date_from.strip(), '%Y-%m-%d')
                                date_to_obj = datetime.strptime(date_to.strip(), '%Y-%m-%d')
                                oracle_date_from = date_from_obj.strftime('%d/%b/%Y').lower()
                                oracle_date_to = date_to_obj.strftime('%d/%b/%Y').lower()
                                oracle_date_from_escaped = oracle_date_from.replace("'", "''")
                                oracle_date_to_escaped = oracle_date_to.replace("'", "''")
                                batch_date_filter += f" AND {collection_paidate_col} BETWEEN TO_DATE('{oracle_date_from_escaped}', 'DD/MON/YYYY') AND TO_DATE('{oracle_date_to_escaped}', 'DD/MON/YYYY')"
                            except ValueError:
                                pass
                        elif date_from and date_from.strip():
                            try:
                                from datetime import datetime
                                date_from_obj = datetime.strptime(date_from.strip(), '%Y-%m-%d')
                                oracle_date_from = date_from_obj.strftime('%d/%b/%Y').lower()
                                oracle_date_from_escaped = oracle_date_from.replace("'", "''")
                                batch_date_filter += f" AND {collection_paidate_col} >= TO_DATE('{oracle_date_from_escaped}', 'DD/MON/YYYY')"
                            except ValueError:
                                pass
                        elif date_to and date_to.strip():
                            try:
                                from datetime import datetime
                                date_to_obj = datetime.strptime(date_to.strip(), '%Y-%m-%d')
                                oracle_date_to = date_to_obj.strftime('%d/%b/%Y').lower()
                                oracle_date_to_escaped = oracle_date_to.replace("'", "''")
                                batch_date_filter += f" AND {collection_paidate_col} <= TO_DATE('{oracle_date_to_escaped}', 'DD/MON/YYYY')"
                            except ValueError:
                                pass
                        batch_flag_filter = ''
                        if collection_flag_col:
                            batch_flag_filter = f" AND {collection_flag_col} = 'R'"
                        customer_codes = [str(row.get('customercode', '')).strip().upper() for row in rows if row.get('customercode')]
                        if customer_codes:
                            customer_codes_escaped = [code.replace("'", "''") for code in customer_codes]
                            batch_size = 1000
                            collection_dict = {}
                            for i in range(0, len(customer_codes_escaped), batch_size):
                                batch_codes = customer_codes_escaped[i:i + batch_size]
                                customer_codes_list = "', '".join(batch_codes)
                                batch_collection_query = f"\n                                        SELECT UPPER(TRIM({collection_customer_col})) AS customercode,\n                                               SUM(NVL({collection_paidamount_col}, 0)) AS COLLECTION\n                                        FROM {collection_table}\n                                        WHERE UPPER(TRIM({collection_customer_col})) IN ('{customer_codes_list}')\n                                        {batch_date_filter}\n                                        {batch_flag_filter}\n                                        GROUP BY UPPER(TRIM({collection_customer_col}))\n                                    "
                                try:
                                    if i == 0:
                                        print(f'[DEBUG] Executing batch collection query (batch {i // batch_size + 1}) for {len(batch_codes)} customers...')
                                        print(f'[DEBUG] Date filter: {batch_date_filter[:150]}...')
                                        print(f'[DEBUG] Flag filter: {batch_flag_filter}')
                                    _, batch_coll_rows = _fetch_rows(batch_collection_query, {})
                                    if batch_coll_rows:
                                        for coll_row in batch_coll_rows:
                                            cust_code_key = str(coll_row.get('customercode', '')).strip().upper()
                                            collection_value = float(coll_row.get('COLLECTION') or coll_row.get('collection') or 0)
                                            if cust_code_key:
                                                collection_dict[cust_code_key] = collection_value
                                    if i == 0:
                                        print(f'[DEBUG] Batch {i // batch_size + 1} returned {(len(batch_coll_rows) if batch_coll_rows else 0)} rows')
                                except Exception as batch_e:
                                    print(f'[DEBUG] ERROR: Batch collection query failed for batch {i // batch_size + 1}: {batch_e}')
                                    print(f'[DEBUG] Query was: {batch_collection_query[:500]}...')
                                    import traceback
                                    traceback.print_exc()
                            for row in rows:
                                cust_code = str(row.get('customercode', '')).strip().upper()
                                if cust_code in collection_dict:
                                    row['collectionamount'] = collection_dict[cust_code]
                                else:
                                    row['collectionamount'] = 0.0
                            print(f'[DEBUG] Batch collection query completed: {len(collection_dict)} customers have collection out of {len(customer_codes)} total')
                            if len(collection_dict) > 0:
                                sample_collections = list(collection_dict.items())[:3]
                                print(f'[DEBUG] Sample collections: {sample_collections}')
                            elif len(customer_codes) > 0:
                                print(f'[DEBUG] WARNING: No collection found for any customers. Check date filter and flag filter.')
                        else:
                            for row in rows:
                                row['collectionamount'] = 0.0
                        total_collection = sum((float(row.get('collectionamount', 0)) for row in rows))
                        customers_with_collection = sum((1 for row in rows if float(row.get('collectionamount', 0)) > 0))
                        print(f'[DEBUG] Collection calculation complete: {customers_with_collection} customers with collection, Total = {total_collection:.2f}')
                    except Exception as collection_batch_e:
                        print(f'[DEBUG] ERROR: Failed to add collection amounts: {collection_batch_e}')
                        import traceback
                        traceback.print_exc()
                        for row in rows:
                            row['collectionamount'] = 0.0
                if pending_table and pending_customer_col and pending_amount_col and pending_billtype_col and pending_billdate_col and (date_from or date_to):
                    print(f'[DEBUG] Adding pending amounts for {len(rows)} customers (batch query)...')
                    try:
                        pending_date_filter = f' AND {pending_billdate_col} IS NOT NULL'
                        if date_from and date_from.strip() and date_to and date_to.strip():
                            try:
                                from datetime import datetime
                                date_from_obj = datetime.strptime(date_from.strip(), '%Y-%m-%d')
                                date_to_obj = datetime.strptime(date_to.strip(), '%Y-%m-%d')
                                oracle_date_from = date_from_obj.strftime('%d/%b/%Y').lower()
                                oracle_date_to = date_to_obj.strftime('%d/%b/%Y').lower()
                                oracle_date_from_escaped = oracle_date_from.replace("'", "''")
                                oracle_date_to_escaped = oracle_date_to.replace("'", "''")
                                pending_date_filter += f" AND {pending_billdate_col} BETWEEN TO_DATE('{oracle_date_from_escaped}', 'DD/MON/YYYY') AND TO_DATE('{oracle_date_to_escaped}', 'DD/MON/YYYY')"
                            except ValueError:
                                pass
                        elif date_from and date_from.strip():
                            try:
                                from datetime import datetime
                                date_from_obj = datetime.strptime(date_from.strip(), '%Y-%m-%d')
                                oracle_date_from = date_from_obj.strftime('%d/%b/%Y').lower()
                                oracle_date_from_escaped = oracle_date_from.replace("'", "''")
                                pending_date_filter += f" AND {pending_billdate_col} >= TO_DATE('{oracle_date_from_escaped}', 'DD/MON/YYYY')"
                            except ValueError:
                                pass
                        elif date_to and date_to.strip():
                            try:
                                from datetime import datetime
                                date_to_obj = datetime.strptime(date_to.strip(), '%Y-%m-%d')
                                oracle_date_to = date_to_obj.strftime('%d/%b/%Y').lower()
                                oracle_date_to_escaped = oracle_date_to.replace("'", "''")
                                pending_date_filter += f" AND {pending_billdate_col} <= TO_DATE('{oracle_date_to_escaped}', 'DD/MON/YYYY')"
                            except ValueError:
                                pass
                        customer_codes = [str(row.get('customercode', '')).strip().upper() for row in rows if row.get('customercode')]
                        if customer_codes:
                            batch_size = 1000
                            pending_dict = {}
                            customer_codes_escaped = [code.replace("'", "''") for code in customer_codes]
                            for i in range(0, len(customer_codes_escaped), batch_size):
                                batch_codes = customer_codes_escaped[i:i + batch_size]
                                customer_codes_list = "', '".join(batch_codes)
                                batch_pending_query = f"\n                                        SELECT UPPER(TRIM({pending_customer_col})) AS customercode,\n                                               SUM(NVL({pending_amount_col}, 0)) AS PENDING\n                                        FROM {pending_table}\n                                        WHERE UPPER(TRIM({pending_customer_col})) IN ('{customer_codes_list}')\n                                        AND {pending_billtype_col} = 'T'\n                                        {pending_date_filter}\n                                        GROUP BY UPPER(TRIM({pending_customer_col}))\n                                    "
                                try:
                                    if i == 0:
                                        print(f'[DEBUG] Executing batch pending query (batch {i // batch_size + 1}) for {len(batch_codes)} customers...')
                                    _, batch_pending_rows = _fetch_rows(batch_pending_query, {})
                                    if batch_pending_rows:
                                        for pending_row in batch_pending_rows:
                                            cust_code_key = str(pending_row.get('customercode', '')).strip().upper()
                                            pending_value = float(pending_row.get('PENDING') or pending_row.get('pending') or 0)
                                            if cust_code_key:
                                                pending_dict[cust_code_key] = pending_value
                                    if i == 0:
                                        print(f'[DEBUG] Batch {i // batch_size + 1} returned {(len(batch_pending_rows) if batch_pending_rows else 0)} rows')
                                except Exception as pending_batch_e:
                                    print(f'[DEBUG] ERROR: Batch pending query failed for batch {i // batch_size + 1}: {pending_batch_e}')
                                    import traceback
                                    traceback.print_exc()
                            for row in rows:
                                cust_code = str(row.get('customercode', '')).strip().upper()
                                if cust_code in pending_dict:
                                    row['pendingamount'] = pending_dict[cust_code]
                                else:
                                    row['pendingamount'] = 0.0
                            print(f'[DEBUG] Pending calculation complete: {len(pending_dict)} customers have pending amounts')
                        else:
                            for row in rows:
                                row['pendingamount'] = 0.0
                    except Exception as pending_batch_e:
                        print(f'[DEBUG] ERROR: Failed to add pending amounts: {pending_batch_e}')
                        import traceback
                        traceback.print_exc()
                        for row in rows:
                            row['pendingamount'] = 0.0
                else:
                    for row in rows:
                        row['pendingamount'] = 0.0
        except Exception as query_e:
            print(f'[DEBUG] ERROR: Main query failed: {query_e}')
            import traceback
            traceback.print_exc()
            rows = []
        print(f'[DEBUG] Query execution complete: {len(rows)} customers')
        return rows
    except Exception as e:
        print(f'[ERROR get_cash_customers_with_outstanding] {e}')
        import traceback
        traceback.print_exc()
        return []

def get_customer_outstanding_details(customer_code: str) -> List[Dict[str, Any]]:
    """Get invoice-level outstanding details for one customer from tblsettlement (flag='B', balance <> 0)."""
    if not customer_code or not str(customer_code).strip():
        return []
    customer_code = str(customer_code).strip()
    try:
        for table_name in ['TBLSETTLEMENT', 'tblsettlement']:
            if not _table_exists(table_name):
                continue
            cust_col = _detect_column(table_name, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'CUSTCODE', 'CUST_CODE'])
            balance_col = _detect_column(table_name, ['BALANCE', 'OUTSTANDING', 'NETBALANCE'])
            flag_col = _detect_column(table_name, ['FLAG', 'FLAG_CODE', 'STATUS_FLAG'])
            billno_col = _detect_column(table_name, ['BILLNO', 'BILL_NO', 'INVOICENO', 'INVOICE_NO'])
            billdate_col = _detect_column(table_name, ['BILLDATE', 'BILL_DATE', 'INVOICEDATE', 'INVOICE_DATE'])
            billamount_col = _detect_column(table_name, ['BILLAMOUNT', 'BILL_AMOUNT', 'AMOUNT', 'INVOICEAMOUNT'])
            paidamount_col = _detect_column(table_name, ['PAIDAMOUNT', 'PAID_AMOUNT', 'PAIDAMT', 'PAID'])
            if not all([cust_col, balance_col, flag_col]):
                continue
            flag_filter = f"AND s.{flag_col} = 'B'" if flag_col else ''
            query = f'\n                SELECT\n                    s.{billno_col} AS billno,\n                    s.{billdate_col} AS billdate,\n                    NVL(s.{billamount_col}, 0) AS billamount,\n                    NVL(s.{paidamount_col}, 0) AS paidamount,\n                    NVL(s.{balance_col}, 0) AS outstanding\n                FROM {table_name} s\n                WHERE s.{cust_col} = :customer_code\n                  AND NVL(s.{balance_col}, 0) <> 0\n                  {flag_filter}\n                ORDER BY s.{billdate_col} DESC, s.{billno_col} DESC\n            '
            _, rows = _fetch_rows(query, {'customer_code': customer_code})
            return rows or []
    except Exception as e:
        print(f'[ERROR get_customer_outstanding_details] {e}')
        import traceback
        traceback.print_exc()
        return []
    return []

def _format_pdf_date(value: Any) -> str:
    """Format date for PDF (dd/mmm/yyyy)."""
    if value is None:
        return ''
    if hasattr(value, 'strftime'):
        return value.strftime('%d/%b/%Y').upper()
    s = str(value).strip()
    if not s:
        return ''
    try:
        from datetime import datetime
        if 'GMT' in s or (',' in s and len(s) > 15):
            try:
                s_clean = s.replace(' GMT', '').replace(' UTC', '').strip()
                dt = datetime.strptime(s_clean, '%a, %d %b %Y %H:%M:%S')
                return dt.strftime('%d/%b/%Y').upper()
            except ValueError:
                pass
        if '-' in s and len(s) >= 10:
            dt = datetime.strptime(s[:10], '%Y-%m-%d')
            return dt.strftime('%d/%b/%Y').upper()
    except Exception:
        pass
    return s

def _generate_outstanding_pdf(customer_code: str, customer_name: str, rows: List[Dict[str, Any]], location_name: str='') -> Optional[bytes]:
    """Generate PDF report of outstanding invoice details for one customer."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    except ImportError:
        print('[WARNING] reportlab not available, skipping PDF generation')
        return None
    import io
    try:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5 * inch, bottomMargin=0.5 * inch)
        story = []
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontSize=16, textColor=colors.HexColor('#1f2937'), spaceAfter=12, alignment=TA_CENTER)
        story.append(Paragraph('Outstanding Invoice Details', title_style))
        story.append(Spacer(1, 0.2 * inch))
        details = [['Customer Code:', customer_code], ['Customer Name:', (customer_name or '').strip() or 'N/A'], ['Location:', location_name or 'N/A']]
        t = Table(details, colWidths=[2 * inch, 4 * inch])
        t.setStyle(TableStyle([('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, -1), 10), ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]))
        story.append(t)
        story.append(Spacer(1, 0.25 * inch))
        headers = ['Bill No', 'Bill Date', 'Bill Amount', 'Paid Amount', 'Outstanding']
        table_data = [headers]
        total_outstanding = 0.0
        for r in rows:
            billno = r.get('billno') or 'N/A'
            billdate = _format_pdf_date(r.get('billdate'))
            billamount = float(r.get('billamount') or 0)
            paidamount = float(r.get('paidamount') or 0)
            outstanding = float(r.get('outstanding') or 0)
            total_outstanding += outstanding
            table_data.append([str(billno), billdate, f'{billamount:.2f}', f'{paidamount:.2f}', f'{outstanding:.2f}'])
        table_data.append(['TOTAL', '', '', '', f'{total_outstanding:.2f}'])
        tbl = Table(table_data, colWidths=[1.2 * inch, 1.4 * inch, 1.2 * inch, 1.2 * inch, 1.2 * inch])
        tbl.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e5e7eb')), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'), ('ALIGN', (0, 0), (-1, -1), 'LEFT'), ('ALIGN', (2, 0), (-1, -1), 'RIGHT'), ('FONTSIZE', (0, 0), (-1, -1), 9), ('BOTTOMPADDING', (0, 0), (-1, -1), 6), ('TOPPADDING', (0, 0), (-1, -1), 6), ('GRID', (0, 0), (-1, -2), 1, colors.HexColor('#d1d5db')), ('LINEBELOW', (0, -1), (-1, -1), 2, colors.HexColor('#374151'))]))
        story.append(tbl)
        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()
    except Exception as e:
        print(f'[ERROR _generate_outstanding_pdf] {e}')
        import traceback
        traceback.print_exc()
        return None

@bp.route('/sms')
def sms_page():
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
    from db import get_location_info_by_dbkey
    current_dbkey = user_dbkey or session.get('location_code') or 'HO'
    if not session.get('location_name'):
        try:
            location_info = get_location_info_by_dbkey(current_dbkey)
            if location_info:
                location_name = location_info.get('locationname', '') or ''
                if location_name:
                    session['location_name'] = location_name
                    print(f'[DEBUG sms_page] Location name set: {location_name}')
        except Exception as e:
            print(f'[DEBUG sms_page] Error fetching location name: {e}')
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    has_filter = 'date_from' in request.args or 'date_to' in request.args
    if has_filter and (date_from or date_to):
        customers = get_cash_customers_with_outstanding(date_from=date_from, date_to=date_to)
    else:
        customers = []
    masks = get_masks_from_table()
    current_location_code = session.get('location_code') or user_dbkey
    contact_number = get_contact_number_from_table(location_code=current_location_code)
    print(f"[DEBUG sms_page] Contact number fetched: '{contact_number}' (type: {type(contact_number)}, length: {(len(contact_number) if contact_number else 0)})")
    location_name = session.get('location_name') or ''
    return render_template('sms/sms.html', customers=customers, date_from=date_from, date_to=date_to, masks=masks, contact_number=contact_number, location_name=location_name, has_filter=has_filter)

@bp.route('/sms-credit')
def sms_credit_page():
    """Send SMS Credit: list credit customers with outstanding (TBLCREDITSETTLEMENT + BILLHDR date filter), same UI as Send SMS."""
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
    from db import get_location_info_by_dbkey
    current_dbkey = user_dbkey or session.get('location_code') or 'HO'
    if not session.get('location_name'):
        try:
            location_info = get_location_info_by_dbkey(current_dbkey)
            if location_info and location_info.get('locationname'):
                session['location_name'] = (location_info.get('locationname') or '').strip()
        except Exception:
            pass
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    has_filter = 'date_from' in request.args or 'date_to' in request.args
    if has_filter and (date_from or date_to):
        customers = get_credit_customers_with_outstanding(date_from=date_from, date_to=date_to)
    else:
        customers = []
    masks = get_masks_from_table()
    current_location_code = session.get('location_code') or user_dbkey
    contact_number = get_contact_number_from_table(location_code=current_location_code)
    location_name = session.get('location_name') or ''
    return render_template('sms/sms_credit.html', customers=customers, date_from=date_from, date_to=date_to, masks=masks, contact_number=contact_number, location_name=location_name, has_filter=has_filter)

@bp.route('/sms/whatsapp')
def whatsapp_page():
    """WhatsApp page: list customers with outstanding; generate PDF and open WhatsApp to their phone."""
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
    from db import get_location_info_by_dbkey
    current_dbkey = user_dbkey or session.get('location_code') or 'HO'
    location_name = session.get('location_name') or ''
    if not location_name:
        try:
            location_info = get_location_info_by_dbkey(current_dbkey)
            if location_info:
                location_name = (location_info.get('locationname') or '').strip()
                if location_name:
                    session['location_name'] = location_name
        except Exception:
            pass
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    has_filter = 'date_from' in request.args or 'date_to' in request.args
    if has_filter and (date_from or date_to):
        customers = get_cash_customers_with_outstanding(date_from=date_from, date_to=date_to)
    else:
        customers = []
    return render_template('sms/whatsapp.html', customers=customers, date_from=date_from, date_to=date_to, has_filter=has_filter, location_name=location_name)

@bp.route('/sms/whatsapp/outstanding-pdf')
def whatsapp_outstanding_pdf():
    """Generate PDF of outstanding invoice details for a customer; return as download."""
    if not session.get('user'):
        return jsonify({'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    else:
        location_code = session.get('location_code')
        if location_code:
            _apply_active_connection(location_code)
        elif session.get('user') == 'admin':
            _apply_active_connection('HO')
    customer_code = (request.args.get('customer_code') or '').strip()
    if not customer_code:
        return jsonify({'error': 'customer_code required'}, 400)
    customers = get_cash_customers_with_outstanding()
    customer = next((c for c in customers if str(c.get('customercode')) == customer_code), None)
    if not customer:
        return jsonify({'error': 'Customer not found'}, 404)
    rows = get_customer_outstanding_details(customer_code)
    if not rows:
        return jsonify({'error': 'No outstanding invoices for this customer'}, 404)
    location_name = session.get('location_name') or ''
    pdf_bytes = _generate_outstanding_pdf(customer_code=customer_code, customer_name=customer.get('customername') or customer_code, rows=rows, location_name=location_name)
    if not pdf_bytes:
        return jsonify({'error': 'Failed to generate PDF'}, 500)
    from nexa_http import send_file
    import io
    safe_name = f"outstanding_{customer_code}_{request.args.get('date_from', '') or 'report'}.pdf".replace(' ', '_')
    return send_file(io.BytesIO(pdf_bytes), mimetype='application/pdf', as_attachment=True, download_name=safe_name)

def _phone_to_whatsapp_e164(phone: str) -> str:
    """Normalize phone to E.164 for Twilio WhatsApp (e.g. +974XXXXXXXX)."""
    if not phone:
        return ''
    cleaned = str(phone).strip().replace(' ', '').replace('-', '').replace('+', '')
    if cleaned.startswith('974'):
        return '+' + cleaned
    if len(cleaned) == 8 and cleaned.isdigit():
        return '+974' + cleaned
    if cleaned.isdigit():
        return '+' + cleaned
    return '+' + cleaned

def send_whatsapp_twilio(to_phone: str, body: str, media_url: Optional[str]=None) -> Tuple[bool, str]:
    """Send WhatsApp message (and optional media) via Twilio. Returns (success, message_or_error)."""
    account_sid = os.getenv('TWILIO_ACCOUNT_SID', '').strip()
    auth_token = os.getenv('TWILIO_AUTH_TOKEN', '').strip()
    from_number = os.getenv('TWILIO_WHATSAPP_FROM', 'whatsapp:+14155238886').strip()
    if not from_number.startswith('whatsapp:'):
        from_number = 'whatsapp:' + from_number
    if not account_sid or not auth_token:
        return (False, 'Twilio not configured (TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN)')
    to_wa = _phone_to_whatsapp_e164(to_phone)
    if not to_wa or len(to_wa) < 10:
        return (False, 'Invalid phone number')
    to_wa = 'whatsapp:' + to_wa.lstrip('+')
    try:
        from twilio.rest import Client
        client = Client(account_sid, auth_token)
        params = {'body': body or 'Your outstanding invoice report is attached.'}
        if media_url:
            params['media_url'] = [media_url]
        msg = client.messages.create(to=to_wa, from_=from_number, **params)
        return (True, str(msg.sid))
    except Exception as e:
        return (False, str(e))

@bp.route('/sms/whatsapp/outstanding-pdf/<token>')
def whatsapp_pdf_by_token(token: str):
    """Serve PDF by one-time token (used by Twilio when sending media). No auth required."""
    import io
    import time
    from nexa_http import send_file
    global _whatsapp_pdf_tokens
    ttl = 1800
    now = time.time()
    _whatsapp_pdf_tokens = {k: v for k, v in _whatsapp_pdf_tokens.items() if now - v.get('created', 0) < ttl}
    data = _whatsapp_pdf_tokens.pop(token, None)
    if not data or not data.get('pdf'):
        return jsonify({'error': 'Link expired or invalid'}, 404)
    return send_file(io.BytesIO(data['pdf']), mimetype='application/pdf', as_attachment=True, download_name=data.get('filename', 'outstanding_report.pdf'))

@bp.route('/sms/whatsapp/send-twilio', methods=['POST'])
def whatsapp_send_twilio():
    """Send outstanding PDF to customer's WhatsApp via Twilio. Generates PDF, caches by token, sends message with media URL."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    else:
        location_code = session.get('location_code')
        if location_code:
            _apply_active_connection(location_code)
        elif session.get('user') == 'admin':
            _apply_active_connection('HO')
    payload = request.get_json(silent=True) or {}
    customer_code = (payload.get('customer_code') or '').strip()
    if not customer_code:
        return jsonify({'success': False, 'error': 'customer_code required'}, 400)
    customers = get_cash_customers_with_outstanding()
    customer = next((c for c in customers if str(c.get('customercode')) == customer_code), None)
    if not customer:
        return jsonify({'success': False, 'error': 'Customer not found'}, 404)
    phone = customer.get('whatsappno') or customer.get('phoneno') or ''
    if not phone:
        return jsonify({'success': False, 'error': 'No WhatsApp/phone number for this customer'}, 400)
    phone = str(phone).strip()
    rows = get_customer_outstanding_details(customer_code)
    if not rows:
        return jsonify({'success': False, 'error': 'No outstanding invoices for this customer'}, 404)
    location_name = session.get('location_name') or ''
    pdf_bytes = _generate_outstanding_pdf(customer_code=customer_code, customer_name=customer.get('customername') or customer_code, rows=rows, location_name=location_name)
    if not pdf_bytes:
        return jsonify({'success': False, 'error': 'Failed to generate PDF'}, 500)
    import secrets
    import time
    token = secrets.token_urlsafe(32)
    _whatsapp_pdf_tokens[token] = {'pdf': pdf_bytes, 'filename': f'outstanding_{customer_code}.pdf', 'created': time.time()}
    pdf_url = url_for('sms.whatsapp_pdf_by_token', token=token, _external=True)
    customer_name = (customer.get('customername') or customer_code) or 'Customer'
    body = f'Dear {customer_name},\n\nPlease find attached your outstanding invoice details report.\n\nThank you.'
    ok, result = send_whatsapp_twilio(phone, body, media_url=pdf_url)
    if not ok:
        _whatsapp_pdf_tokens.pop(token, None)
        return jsonify({'success': False, 'error': result}, 500)
    return jsonify({'success': True, 'message_sid': result})

@bp.route('/sms/send', methods=['POST'])
def sms_send():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    else:
        location_code = session.get('location_code')
        if location_code:
            _apply_active_connection(location_code)
        elif session.get('user') == 'admin':
            _apply_active_connection('HO')
    payload = request.get_json(silent=True) or {}
    customer_code = payload.get('customer_code', '').strip()
    message = payload.get('message', '').strip()
    mask = payload.get('mask', '').strip()
    send_all = payload.get('send_all', False)
    if not message:
        return jsonify({'success': False, 'error': 'Message is required'}, 400)
    results = []
    if send_all:
        customers = get_cash_customers_with_outstanding()
        for customer in customers:
            phone = customer.get('phoneno') or ''
            if not phone:
                results.append({'customer_code': customer.get('customercode'), 'customer_name': customer.get('customername'), 'success': False, 'error': 'Phone number not available'})
                continue
            ok, text = send_sms(message, phone, mask)
            results.append({'customer_code': customer.get('customercode'), 'customer_name': customer.get('customername'), 'phone': phone, 'success': ok, 'response': text})
    else:
        if not customer_code:
            return jsonify({'success': False, 'error': 'Customer code is required'}, 400)
        customers = get_cash_customers_with_outstanding()
        customer = next((c for c in customers if str(c.get('customercode')) == customer_code), None)
        if not customer:
            return jsonify({'success': False, 'error': 'Customer not found'}, 404)
        phone = customer.get('phoneno') or ''
        if not phone:
            return jsonify({'success': False, 'error': 'Phone number not available'}, 400)
        ok, text = send_sms(message, phone, mask)
        results.append({'customer_code': customer_code, 'customer_name': customer.get('customername'), 'phone': phone, 'success': ok, 'response': text})
    success_count = sum((1 for r in results if r.get('success')))
    return jsonify({'success': True, 'results': results, 'total': len(results), 'success_count': success_count, 'failed_count': len(results) - success_count})

@bp.route('/sms-credit/send', methods=['POST'])
def sms_credit_send():
    """Send SMS to credit customers (uses get_credit_customers_with_outstanding with date_from/date_to from payload)."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    else:
        location_code = session.get('location_code')
        if location_code:
            _apply_active_connection(location_code)
        elif session.get('user') == 'admin':
            _apply_active_connection('HO')
    payload = request.get_json(silent=True) or {}
    customer_code = payload.get('customer_code', '').strip()
    message = payload.get('message', '').strip()
    mask = payload.get('mask', '').strip()
    send_all = payload.get('send_all', False)
    date_from = payload.get('date_from', '').strip()
    date_to = payload.get('date_to', '').strip()
    if not message:
        return jsonify({'success': False, 'error': 'Message is required'}, 400)
    customers = get_credit_customers_with_outstanding(date_from=date_from, date_to=date_to)
    results = []
    if send_all:
        for customer in customers:
            phone = customer.get('phoneno') or ''
            if not phone:
                results.append({'customer_code': customer.get('customercode'), 'customer_name': customer.get('customername'), 'success': False, 'error': 'Phone number not available'})
                continue
            ok, text = send_sms(message, phone, mask)
            results.append({'customer_code': customer.get('customercode'), 'customer_name': customer.get('customername'), 'phone': phone, 'success': ok, 'response': text})
    else:
        if not customer_code:
            return jsonify({'success': False, 'error': 'Customer code is required'}, 400)
        customer = next((c for c in customers if str(c.get('customercode')) == customer_code), None)
        if not customer:
            return jsonify({'success': False, 'error': 'Customer not found'}, 404)
        phone = customer.get('phoneno') or ''
        if not phone:
            return jsonify({'success': False, 'error': 'Phone number not available'}, 400)
        ok, text = send_sms(message, phone, mask)
        results.append({'customer_code': customer_code, 'customer_name': customer.get('customername'), 'phone': phone, 'success': ok, 'response': text})
    success_count = sum((1 for r in results if r.get('success')))
    return jsonify({'success': True, 'results': results, 'total': len(results), 'success_count': success_count, 'failed_count': len(results) - success_count})

@bp.route('/sms/debug-collection', methods=['GET'])
def sms_debug_collection():
    """Debug endpoint to test collection query"""
    if not session.get('user'):
        return jsonify({'error': 'Not authenticated'}, 401)
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    else:
        location_code = session.get('location_code')
        if location_code:
            _apply_active_connection(location_code)
        elif session.get('user') == 'admin':
            _apply_active_connection('HO')
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    debug_info = {'date_from': date_from, 'date_to': date_to, 'collection_table_detected': False, 'collection_columns': {}, 'test_results': {}, 'sample_customers': []}
    collection_table = None
    collection_customer_col = None
    collection_paidamount_col = None
    collection_paidate_col = None
    collection_flag_col = None
    for table_name in ['TBLTEMPSETTLEMENT', 'tbltempsettlement']:
        try:
            cust_col = _detect_column(table_name, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'CUSTCODE', 'CUST_CODE'])
            paidamt_col = _detect_column(table_name, ['PAIDAMOUNT', 'PAID_AMOUNT', 'PAIDAMT', 'PAID'])
            paidate_col = _detect_column(table_name, ['PAIDATE', 'PAID_DATE', 'PAYMENTDATE', 'PAYMENT_DATE'])
            flag_col = _detect_column(table_name, ['FLAG', 'FLAG_CODE', 'STATUS_FLAG'])
            if cust_col and paidamt_col and paidate_col:
                collection_table = table_name
                collection_customer_col = cust_col
                collection_paidamount_col = paidamt_col
                collection_paidate_col = paidate_col
                collection_flag_col = flag_col
                break
        except Exception as e:
            debug_info['error'] = str(e)
            continue
    if collection_table:
        debug_info['collection_table_detected'] = True
        debug_info['collection_columns'] = {'table': collection_table, 'customer': collection_customer_col, 'paidamount': collection_paidamount_col, 'paidate': collection_paidate_col, 'flag': collection_flag_col}
        collection_flag_filter = ''
        if collection_flag_col:
            collection_flag_filter = f" AND {collection_flag_col} = 'R'"
        test_query = f'\n            SELECT COUNT(*) AS cnt, NVL(SUM(NVL({collection_paidamount_col}, 0)), 0) AS total\n            FROM {collection_table}\n            WHERE 1=1\n            {collection_flag_filter}\n        '
        try:
            _, test_rows = _fetch_rows(test_query, {})
            if test_rows:
                debug_info['test_results'] = {'row_count': test_rows[0].get('cnt', 0), 'total_amount': float(test_rows[0].get('total', 0))}
                sample_date_filter = ''
                if date_from:
                    sample_date_filter += f" AND {collection_paidate_col} >= TO_DATE('{date_from}', 'YYYY-MM-DD')"
                if date_to:
                    sample_date_filter += f" AND {collection_paidate_col} <= TO_DATE('{date_to}', 'YYYY-MM-DD')"
                sample_query = f'\n                    SELECT * FROM (\n                        SELECT {collection_customer_col} AS cust_code, \n                               NVL(SUM(NVL({collection_paidamount_col}, 0)), 0) AS total\n                        FROM {collection_table}\n                        WHERE 1=1\n                        {collection_flag_filter}\n                        {sample_date_filter}\n                        GROUP BY {collection_customer_col}\n                    ) WHERE ROWNUM <= 5\n                '
                try:
                    _, sample_rows = _fetch_rows(sample_query, {})
                    debug_info['sample_customers'] = [{'customer_code': str(row.get('cust_code', '')), 'total': float(row.get('total', 0))} for row in sample_rows]
                except Exception as sample_e:
                    debug_info['sample_error'] = str(sample_e)
        except Exception as test_e:
            debug_info['test_error'] = str(test_e)
    else:
        debug_info['error'] = 'Collection table not detected'
    return jsonify(debug_info)
