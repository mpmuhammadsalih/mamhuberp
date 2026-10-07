"""Online marketplace settlement — upload, match, validate, GL post, audit."""
from __future__ import annotations

import csv
import io
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from db import (
    DEFAULT_PARTY_ACCOUNTS,
    _detect_column,
    _detect_table,
    _get_connection,
    _get_table_columns,
    _norm_gl_account_code,
    _safe_rows,
    _table_exists,
    create_gl_journal_entry,
    ensure_ar_payment_tables,
    ensure_gl_tables,
    get_all_chart_of_accounts,
    get_customer_master_by_code,
    get_customer_open_invoices_for_payment,
)

BATCH_TABLE = 'ONLINE_SETTLEMENT_BATCH'
LINE_TABLE = 'ONLINE_SETTLEMENT_LINE'
LINE_SEQ = 'ONLINE_SETTLEMENT_LINE_SEQ'
CONFIG_TABLE = 'ONLINE_SETTLEMENT_CONFIG'
POSTED_ORDER_TABLE = 'ONLINE_SETTLEMENT_POSTED_ORDER'

MAX_UPLOAD_ROWS = 15000
MAX_FILE_BYTES = 15 * 1024 * 1024
AMT_TOL = 0.02
BILLHDR_RESET_NO = 1

STATUS_MATCHED = 'Matched'
STATUS_ORDER_NOT_FOUND = 'Order Not Found'
STATUS_AMOUNT_MISMATCH = 'Amount Mismatch'
STATUS_ALREADY_SETTLED = 'Already Settled'
STATUS_DUPLICATE_ORDER = 'Duplicate Order ID'
STATUS_VALIDATION_ERROR = 'Validation Error'
STATUS_MANUAL_REVIEW = 'Manual Review Required'
STATUS_EXCLUDED = 'Excluded'
STATUS_POSTED = 'Posted'
STATUS_POST_FAILED = 'Post Failed'

EXPECTED_COLUMNS = {
    'order_id': ('orderid', 'order_id', 'orderno', 'ordernumber'),
    'invoice_amount': ('invoiceamount', 'invoice_amount', 'invoicenet', 'grossamount'),
    'total_amount': ('totalamount', 'total_amount', 'netamount', 'netreceived', 'amountreceived'),
    'pm_commission': ('paymentmethodcommission', 'payment_method_commission', 'pmcommission'),
    'sales_commission': ('salescommission', 'sales_commission'),
    'splus': ('spluscoveredbymerchant', 'splus_covered_by_merchant', 'splus', 'merchantcovered'),
    'other_charges': ('othercharges', 'other_charges', 'othercharge', 'other_charge'),
}

SETTLEMENT_IMPORT_HEADERS = [
    'OrderId',
    'InvoiceAmount',
    'TotalAmount',
    'PaymentMethodCommission',
    'SalesCommission',
    'SPlusCoveredByMerchant',
    'OtherCharges',
]
SETTLEMENT_SAMPLE_ROW = ['77546052', 66.00, 50.13, 1.65, 11.22, 3.00, 0.00]


def build_settlement_sample_csv() -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(SETTLEMENT_IMPORT_HEADERS)
    writer.writerow(SETTLEMENT_SAMPLE_ROW)
    return buf.getvalue()


def build_settlement_sample_xlsx() -> Optional[bytes]:
    try:
        from openpyxl import Workbook
    except ImportError:
        return None
    wb = Workbook()
    ws = wb.active
    ws.title = 'Settlement'
    ws.append(list(SETTLEMENT_IMPORT_HEADERS))
    ws.append(list(SETTLEMENT_SAMPLE_ROW))
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _norm_hdr(key: str) -> str:
    return re.sub(r'[^a-z0-9]', '', str(key or '').strip().lower())


def _cell(row: Dict[str, Any], *aliases: str) -> Any:
    norm_map = {_norm_hdr(k): v for k, v in (row or {}).items() if k}
    for alias in aliases:
        nk = _norm_hdr(alias)
        if nk in norm_map:
            return norm_map[nk]
    return None


def _parse_amount(raw: Any) -> Optional[float]:
    if raw is None:
        return None
    s = str(raw).strip().replace(',', '')
    if not s:
        return None
    try:
        return round(float(s), 2)
    except Exception:
        return None


def _positive_amount(value: Any) -> Optional[float]:
    """Normalize monetary values to positive amounts (2 dp)."""
    if value is None:
        return None
    try:
        return round(abs(float(value)), 2)
    except (TypeError, ValueError):
        return None


def _parse_positive_amount(raw: Any) -> Optional[float]:
    return _positive_amount(_parse_amount(raw))


_LINE_AMOUNT_KEYS = (
    'upload_invoice_amount',
    'total_amount',
    'pm_commission',
    'sales_commission',
    'splus_amount',
    'other_charges',
    'erp_invoice_amount',
    'net_amount_received',
    'amount_received',
    'invoice_amount',
    'difference',
)


def _apply_positive_line_amounts(row: Dict[str, Any]) -> Dict[str, Any]:
    for key in _LINE_AMOUNT_KEYS:
        if key in row and row.get(key) is not None:
            pos = _positive_amount(row.get(key))
            if pos is not None:
                row[key] = pos
    return row


def _parse_date_iso(raw: Any) -> str:
    if raw is None:
        return ''
    if hasattr(raw, 'strftime'):
        return raw.strftime('%Y-%m-%d')
    s = str(raw).strip()[:10]
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%m/%d/%Y'):
        try:
            return datetime.strptime(s, fmt).strftime('%Y-%m-%d')
        except Exception:
            continue
    return s


def _table_exists_cur(cur: Any, name: str) -> bool:
    cur.execute(
        "SELECT COUNT(*) FROM user_tables WHERE UPPER(table_name) = UPPER(:t)",
        {'t': name},
    )
    row = cur.fetchone()
    return bool(row and int(row[0] or 0) > 0)


def ensure_online_settlement_tables() -> bool:
    ensure_gl_tables()
    ensure_ar_payment_tables()
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute('SELECT 1 FROM user_sequences WHERE sequence_name = :n', {'n': LINE_SEQ})
                    if cur.fetchone() is None:
                        cur.execute(f'CREATE SEQUENCE {LINE_SEQ} START WITH 1 INCREMENT BY 1 NOCACHE')
                except Exception:
                    pass
                if not _table_exists_cur(cur, CONFIG_TABLE):
                    cur.execute(
                        f"""
                        CREATE TABLE {CONFIG_TABLE} (
                            CUSTOMER_CODE VARCHAR2(50) NOT NULL,
                            MARKETPLACE_NAME VARCHAR2(100),
                            BANK_ACCOUNT VARCHAR2(20),
                            PM_COMMISSION_ACCOUNT VARCHAR2(20),
                            SALES_COMMISSION_ACCOUNT VARCHAR2(20),
                            SPLUS_ACCOUNT VARCHAR2(20),
                            OTHER_CHARGES_ACCOUNT VARCHAR2(20),
                            UPDATED_BY VARCHAR2(50),
                            UPDATED_AT TIMESTAMP,
                            CONSTRAINT PK_{CONFIG_TABLE} PRIMARY KEY (CUSTOMER_CODE)
                        )
                        """
                    )
                if not _table_exists_cur(cur, BATCH_TABLE):
                    cur.execute(
                        f"""
                        CREATE TABLE {BATCH_TABLE} (
                            BATCH_NO VARCHAR2(30) NOT NULL,
                            LOCATION_CODE NUMBER(10) NOT NULL,
                            CUSTOMER_CODE VARCHAR2(50) NOT NULL,
                            MARKETPLACE_NAME VARCHAR2(100),
                            SETTLEMENT_DATE DATE NOT NULL,
                            FILE_NAME VARCHAR2(255),
                            UPLOADED_BY VARCHAR2(50),
                            UPLOADED_AT TIMESTAMP DEFAULT SYSTIMESTAMP,
                            POSTED_BY VARCHAR2(50),
                            POSTED_AT TIMESTAMP,
                            STATUS VARCHAR2(20) DEFAULT 'DRAFT',
                            TOTAL_ROWS NUMBER(10) DEFAULT 0,
                            MATCHED_ROWS NUMBER(10) DEFAULT 0,
                            POSTED_ROWS NUMBER(10) DEFAULT 0,
                            FAILED_ROWS NUMBER(10) DEFAULT 0,
                            BANK_ACCOUNT VARCHAR2(20),
                            PM_COMMISSION_ACCOUNT VARCHAR2(20),
                            SALES_COMMISSION_ACCOUNT VARCHAR2(20),
                            SPLUS_ACCOUNT VARCHAR2(20),
                            OTHER_CHARGES_ACCOUNT VARCHAR2(20),
                            REMARKS VARCHAR2(500),
                            CONSTRAINT PK_{BATCH_TABLE} PRIMARY KEY (BATCH_NO)
                        )
                        """
                    )
                if not _table_exists_cur(cur, LINE_TABLE):
                    cur.execute(
                        f"""
                        CREATE TABLE {LINE_TABLE} (
                            LINE_ID NUMBER NOT NULL,
                            BATCH_NO VARCHAR2(30) NOT NULL,
                            LINE_NO NUMBER(10) NOT NULL,
                            ORDER_ID VARCHAR2(80),
                            UPLOAD_INVOICE_AMOUNT NUMBER(18,2),
                            TOTAL_AMOUNT NUMBER(18,2),
                            PM_COMMISSION NUMBER(18,2),
                            SALES_COMMISSION NUMBER(18,2),
                            SPLUS_AMOUNT NUMBER(18,2),
                            OTHER_CHARGES NUMBER(18,2),
                            ERP_BILLNO NUMBER(18),
                            ERP_INVOICE_DATE DATE,
                            ERP_INVOICE_AMOUNT NUMBER(18,2),
                            GL_VOUCHER_NO VARCHAR2(30),
                            STATUS VARCHAR2(40),
                            STATUS_MESSAGE VARCHAR2(500),
                            MANUAL_INVOICE_VOUCHER VARCHAR2(30),
                            EXCLUDED VARCHAR2(1) DEFAULT 'N',
                            POSTED_AT TIMESTAMP,
                            CONSTRAINT PK_{LINE_TABLE} PRIMARY KEY (LINE_ID)
                        )
                        """
                    )
                if not _table_exists_cur(cur, POSTED_ORDER_TABLE):
                    cur.execute(
                        f"""
                        CREATE TABLE {POSTED_ORDER_TABLE} (
                            ORDER_ID VARCHAR2(80) NOT NULL,
                            CUSTOMER_CODE VARCHAR2(50) NOT NULL,
                            BATCH_NO VARCHAR2(30),
                            GL_VOUCHER_NO VARCHAR2(30),
                            POSTED_AT TIMESTAMP DEFAULT SYSTIMESTAMP,
                            CONSTRAINT PK_{POSTED_ORDER_TABLE} PRIMARY KEY (ORDER_ID, CUSTOMER_CODE)
                        )
                        """
                    )
                for tbl, col, ddl in (
                    (CONFIG_TABLE, 'OTHER_CHARGES_ACCOUNT', f'ALTER TABLE {CONFIG_TABLE} ADD (OTHER_CHARGES_ACCOUNT VARCHAR2(20))'),
                    (BATCH_TABLE, 'OTHER_CHARGES_ACCOUNT', f'ALTER TABLE {BATCH_TABLE} ADD (OTHER_CHARGES_ACCOUNT VARCHAR2(20))'),
                    (LINE_TABLE, 'OTHER_CHARGES', f'ALTER TABLE {LINE_TABLE} ADD (OTHER_CHARGES NUMBER(18,2))'),
                ):
                    cols = {c.upper() for c in (_get_table_columns(tbl) or [])}
                    if col not in cols:
                        try:
                            cur.execute(ddl)
                        except Exception:
                            pass
            conn.commit()
        return True
    except Exception as exc:
        print(f'[ERROR ensure_online_settlement_tables] {exc}')
        return False


def parse_settlement_file(raw: bytes, filename: str) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    name = (filename or '').lower()
    if len(raw or b'') > MAX_FILE_BYTES:
        return ([], f'File too large (max {MAX_FILE_BYTES // (1024 * 1024)} MB).')
    if name.endswith('.csv'):
        return _parse_settlement_csv(raw)
    if name.endswith('.xlsx') or name.endswith('.xlsm'):
        return _parse_settlement_xlsx(raw)
    return ([], 'Upload .xlsx, .xlsm, or .csv only.')


def _parse_settlement_csv(raw: bytes) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    text = None
    for enc in ('utf-8-sig', 'cp1252', 'latin-1'):
        try:
            text = raw.decode(enc)
            break
        except Exception:
            continue
    if text is None:
        return ([], 'Could not decode CSV file.')
    reader = csv.DictReader(io.StringIO(text))
    out: List[Dict[str, Any]] = []
    for row in reader:
        if len(out) >= MAX_UPLOAD_ROWS:
            break
        if any(str(v or '').strip() for v in row.values()):
            out.append(dict(row))
    if not out:
        return ([], 'CSV has no data rows.')
    return (out, None)


def _parse_settlement_xlsx(raw: bytes) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    try:
        from openpyxl import load_workbook
    except ImportError:
        return ([], 'Excel import requires openpyxl (pip install openpyxl).')
    try:
        wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        try:
            ws = wb.active
            rows_it = ws.iter_rows(values_only=True)
            header_row = next(rows_it, None)
            if not header_row:
                return ([], 'Worksheet is empty.')
            headers = [str(c or '').strip() for c in header_row]
            out: List[Dict[str, Any]] = []
            for row in rows_it:
                if len(out) >= MAX_UPLOAD_ROWS:
                    break
                rd: Dict[str, Any] = {}
                empty = True
                for i, h in enumerate(headers):
                    if not h:
                        continue
                    v = row[i] if i < len(row) else None
                    if v is not None and str(v).strip() != '':
                        empty = False
                    rd[h] = v
                if not empty:
                    out.append(rd)
            if not out:
                return ([], 'Excel has no data rows.')
            return (out, None)
        finally:
            try:
                wb.close()
            except Exception:
                pass
    except Exception as exc:
        return ([], str(exc))


def normalize_upload_row(raw: Dict[str, Any], line_no: int) -> Dict[str, Any]:
    order_id = _normalize_order_id(_cell(raw, *EXPECTED_COLUMNS['order_id']))
    inv_amt = _parse_positive_amount(_cell(raw, *EXPECTED_COLUMNS['invoice_amount']))
    total_amt = _parse_positive_amount(_cell(raw, *EXPECTED_COLUMNS['total_amount']))
    pm = _parse_positive_amount(_cell(raw, *EXPECTED_COLUMNS['pm_commission']))
    sc = _parse_positive_amount(_cell(raw, *EXPECTED_COLUMNS['sales_commission']))
    sp = _parse_positive_amount(_cell(raw, *EXPECTED_COLUMNS['splus']))
    oc = _parse_positive_amount(_cell(raw, *EXPECTED_COLUMNS['other_charges']))
    return {
        'line_no': line_no,
        'order_id': order_id[:80],
        'upload_invoice_amount': inv_amt,
        'total_amount': total_amt,
        'pm_commission': pm if pm is not None else 0.0,
        'sales_commission': sc if sc is not None else 0.0,
        'splus_amount': sp if sp is not None else 0.0,
        'other_charges': oc if oc is not None else 0.0,
    }


def validate_row_formula(row: Dict[str, Any]) -> Tuple[bool, str]:
    inv = row.get('upload_invoice_amount')
    total = row.get('total_amount')
    if inv is None or total is None:
        return (False, 'InvoiceAmount and TotalAmount are required.')
    pm = abs(float(row.get('pm_commission') or 0))
    sc = abs(float(row.get('sales_commission') or 0))
    sp = abs(float(row.get('splus_amount') or 0))
    oc = abs(float(row.get('other_charges') or 0))
    expected = round(abs(float(total)) + pm + sc + sp + oc, 2)
    actual = round(abs(float(inv)), 2)
    if abs(expected - actual) > AMT_TOL:
        return (
            False,
            f'Formula mismatch: {actual:.2f} != {abs(float(total)):.2f} + {pm:.2f} + {sc:.2f} + {sp:.2f} + {oc:.2f}',
        )
    return (True, '')


def _next_batch_no(settlement_date: str) -> str:
    ensure_online_settlement_tables()
    tag = (_parse_date_iso(settlement_date) or datetime.now().strftime('%Y-%m-%d')).replace('-', '')
    prefix = f'OSB{tag}-'
    rows = _safe_rows(
        f"SELECT MAX(BATCH_NO) AS max_no FROM {BATCH_TABLE} WHERE BATCH_NO LIKE :pfx",
        {'pfx': f'{prefix}%'},
    )
    max_no = str((rows[0].get('max_no') if rows else '') or '')
    seq = 1
    if '-' in max_no:
        tail = max_no.rsplit('-', 1)[-1]
        if tail.isdigit():
            seq = int(tail) + 1
    return f'{prefix}{seq:04d}'


def get_marketplace_config(customer_code: str) -> Optional[Dict[str, Any]]:
    ensure_online_settlement_tables()
    cc = str(customer_code or '').strip()
    if not cc:
        return None
    rows = _safe_rows(
        f"""
        SELECT CUSTOMER_CODE, MARKETPLACE_NAME, BANK_ACCOUNT, PM_COMMISSION_ACCOUNT,
               SALES_COMMISSION_ACCOUNT, SPLUS_ACCOUNT, OTHER_CHARGES_ACCOUNT, UPDATED_BY, UPDATED_AT
        FROM {CONFIG_TABLE}
        WHERE CUSTOMER_CODE = :cc
        """,
        {'cc': cc[:50]},
    )
    return rows[0] if rows else None


def upsert_marketplace_config(payload: Dict[str, Any], user: str) -> Tuple[bool, str]:
    ensure_online_settlement_tables()
    cc = str(payload.get('customer_code') or '').strip()
    if not cc:
        return (False, 'Marketplace customer is required.')
    params = {
        'cc': cc[:50],
        'name': str(payload.get('marketplace_name') or '').strip()[:100] or None,
        'bank': _norm_gl_account_code(payload.get('bank_account') or '') or None,
        'pm': _norm_gl_account_code(payload.get('pm_commission_account') or '') or None,
        'sc': _norm_gl_account_code(payload.get('sales_commission_account') or '') or None,
        'sp': _norm_gl_account_code(payload.get('splus_account') or '') or None,
        'oc': _norm_gl_account_code(payload.get('other_charges_account') or '') or None,
        'usr': (user or '')[:50] or None,
    }
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                MERGE INTO {CONFIG_TABLE} t
                USING (SELECT :cc AS cc FROM dual) s
                ON (t.CUSTOMER_CODE = s.cc)
                WHEN MATCHED THEN UPDATE SET
                    MARKETPLACE_NAME = :name,
                    BANK_ACCOUNT = :bank,
                    PM_COMMISSION_ACCOUNT = :pm,
                    SALES_COMMISSION_ACCOUNT = :sc,
                    SPLUS_ACCOUNT = :sp,
                    OTHER_CHARGES_ACCOUNT = :oc,
                    UPDATED_BY = :usr,
                    UPDATED_AT = SYSTIMESTAMP
                WHEN NOT MATCHED THEN INSERT
                    (CUSTOMER_CODE, MARKETPLACE_NAME, BANK_ACCOUNT, PM_COMMISSION_ACCOUNT,
                     SALES_COMMISSION_ACCOUNT, SPLUS_ACCOUNT, OTHER_CHARGES_ACCOUNT, UPDATED_BY, UPDATED_AT)
                VALUES
                    (:cc, :name, :bank, :pm, :sc, :sp, :oc, :usr, SYSTIMESTAMP)
                """,
                params,
            )
        conn.commit()
    return (True, '')


def create_settlement_batch(
    *,
    location_code: int,
    customer_code: str,
    marketplace_name: str,
    settlement_date: str,
    file_name: str,
    uploaded_by: str,
    accounts: Dict[str, str],
    raw_rows: List[Dict[str, Any]],
) -> Tuple[bool, str, Optional[str]]:
    ensure_online_settlement_tables()
    if not raw_rows:
        return (False, 'No rows in file.', None)
    batch_no = _next_batch_no(settlement_date)
    lines: List[Dict[str, Any]] = []
    for idx, raw in enumerate(raw_rows, start=1):
        row = normalize_upload_row(raw, idx)
        row['status'] = STATUS_VALIDATION_ERROR if not row['order_id'] else 'Pending'
        row['status_message'] = 'Awaiting validation' if row['order_id'] else 'OrderId is required'
        lines.append(row)
    with _get_connection() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO {BATCH_TABLE}
                        (BATCH_NO, LOCATION_CODE, CUSTOMER_CODE, MARKETPLACE_NAME, SETTLEMENT_DATE,
                         FILE_NAME, UPLOADED_BY, STATUS, TOTAL_ROWS,
                         BANK_ACCOUNT, PM_COMMISSION_ACCOUNT, SALES_COMMISSION_ACCOUNT, SPLUS_ACCOUNT,
                         OTHER_CHARGES_ACCOUNT)
                    VALUES
                        (:bno, :loc, :cc, :mn, TO_DATE(:sd, 'YYYY-MM-DD'),
                         :fn, :usr, 'DRAFT', :cnt,
                         :bank, :pm, :sc, :sp, :oc)
                    """,
                    {
                        'bno': batch_no,
                        'loc': int(location_code),
                        'cc': str(customer_code)[:50],
                        'mn': str(marketplace_name or '')[:100] or None,
                        'sd': _parse_date_iso(settlement_date),
                        'fn': str(file_name or '')[:255] or None,
                        'usr': (uploaded_by or '')[:50] or None,
                        'cnt': len(lines),
                        'bank': _norm_gl_account_code(accounts.get('bank_account') or '') or None,
                        'pm': _norm_gl_account_code(accounts.get('pm_commission_account') or '') or None,
                        'sc': _norm_gl_account_code(accounts.get('sales_commission_account') or '') or None,
                        'sp': _norm_gl_account_code(accounts.get('splus_account') or '') or None,
                        'oc': _norm_gl_account_code(accounts.get('other_charges_account') or '') or None,
                    },
                )
                for ln in lines:
                    cur.execute(f'SELECT {LINE_SEQ}.NEXTVAL FROM DUAL')
                    lid = cur.fetchone()[0]
                    cur.execute(
                        f"""
                        INSERT INTO {LINE_TABLE}
                            (LINE_ID, BATCH_NO, LINE_NO, ORDER_ID, UPLOAD_INVOICE_AMOUNT, TOTAL_AMOUNT,
                             PM_COMMISSION, SALES_COMMISSION, SPLUS_AMOUNT, OTHER_CHARGES, STATUS, STATUS_MESSAGE, EXCLUDED)
                        VALUES
                            (:lid, :bno, :lno, :oid, :inv, :tot, :pm, :sc, :sp, :oc, :st, :msg, 'N')
                        """,
                        {
                            'lid': lid,
                            'bno': batch_no,
                            'lno': ln['line_no'],
                            'oid': ln['order_id'] or None,
                            'inv': ln.get('upload_invoice_amount'),
                            'tot': ln.get('total_amount'),
                            'pm': ln.get('pm_commission'),
                            'sc': ln.get('sales_commission'),
                            'sp': ln.get('splus_amount'),
                            'oc': ln.get('other_charges'),
                            'st': ln['status'],
                            'msg': ln['status_message'][:500],
                        },
                    )
            conn.commit()
            return (True, '', batch_no)
        except Exception as exc:
            conn.rollback()
            return (False, str(exc), None)


def _normalize_order_id(raw: Any) -> str:
    """Normalize marketplace OrderId (Excel may send 435 as 435.0)."""
    if raw is None:
        return ''
    if isinstance(raw, bool):
        return ''
    if isinstance(raw, int):
        return str(raw).strip()[:80]
    if isinstance(raw, float):
        if raw == int(raw):
            return str(int(raw))[:80]
        text = str(raw).strip()
        if re.fullmatch(r'\d+\.0+', text):
            return text.split('.')[0][:80]
        return text[:80]
    text = str(raw).strip()
    if re.fullmatch(r'\d+\.0+', text):
        return text.split('.')[0][:80]
    return text[:80]


def _billhdr_order_lookup_meta() -> Optional[Dict[str, str]]:
    tbl = _detect_table(['BILLHDR', 'billhdr'])
    if not tbl:
        return None
    orderno_col = _detect_column(tbl, ['ORDERNO', 'ORDER_NO', 'orderno'])
    net_col = _detect_column(tbl, ['NETBILLAMOUNT', 'NETAMOUNT', 'NET_TOTAL', 'NETBILL', 'BILLAMOUNT'])
    loc_col = _detect_column(tbl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    cust_col = _detect_column(tbl, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'customercode'])
    billno_col = _detect_column(tbl, ['BILLNO', 'BILL_NO', 'billno'])
    billdate_col = _detect_column(tbl, ['BILLDATE', 'BILL_DATE', 'billdate'])
    reset_col = _detect_column(tbl, ['RESETNO', 'RESET_NO', 'resetno'])
    delflag_col = _detect_column(tbl, ['DELFLAG', 'DEL_FLAG', 'delflag'])
    if not orderno_col or not net_col or not loc_col or not billno_col:
        return None
    return {
        'table': tbl,
        'orderno_col': orderno_col,
        'net_col': net_col,
        'loc_col': loc_col,
        'cust_col': cust_col or '',
        'billno_col': billno_col,
        'billdate_col': billdate_col or '',
        'reset_col': reset_col or '',
        'delflag_col': delflag_col or '',
    }


def _find_billhdr_by_order(
    location_code: int,
    customer_code: str,
    order_id: str,
    invoice_amount: Optional[float] = None,
    *,
    require_customer: bool = True,
) -> List[Dict[str, Any]]:
    """Match sales invoice header by BILLHDR.ORDERNO (+ optional NETBILLAMOUNT)."""
    meta = _billhdr_order_lookup_meta()
    if not meta:
        return []
    oid = _normalize_order_id(order_id)
    if not oid:
        return []

    tbl = meta['table']
    orderno_col = meta['orderno_col']
    net_col = meta['net_col']
    loc_col = meta['loc_col']
    cust_col = meta['cust_col']
    billno_col = meta['billno_col']
    billdate_col = meta['billdate_col']
    reset_col = meta['reset_col']
    delflag_col = meta['delflag_col']

    date_sel = f'h.{billdate_col} AS billdate' if billdate_col else 'NULL AS billdate'
    cust_sel = f'h.{cust_col} AS customercode' if cust_col else 'NULL AS customercode'
    q = f"""
        SELECT h.{billno_col} AS billno,
               {date_sel},
               h.{net_col} AS netbillamount,
               {cust_sel},
               h.{orderno_col} AS orderno
          FROM {tbl} h
         WHERE h.{loc_col} = :loc
           AND UPPER(TRIM(TO_CHAR(h.{orderno_col}))) = UPPER(TRIM(:oid))
    """
    params: Dict[str, Any] = {'loc': int(location_code), 'oid': oid[:80]}
    cc = str(customer_code or '').strip()
    if require_customer and cc and cust_col:
        q += f' AND TO_CHAR(h.{cust_col}) = TO_CHAR(:cc)'
        params['cc'] = cc
    if reset_col:
        q += f' AND NVL(h.{reset_col}, {BILLHDR_RESET_NO}) = :rn'
        params['rn'] = BILLHDR_RESET_NO
    if delflag_col:
        q += f" AND NVL(h.{delflag_col}, 'N') <> 'Y'"
    q += f' ORDER BY h.{billno_col} DESC'

    rows = _safe_rows(q, params) or []
    if invoice_amount is not None:
        target = round(abs(float(invoice_amount)), 2)
        rows = [
            r for r in rows
            if abs(round(abs(float(r.get('netbillamount') or 0)), 2) - target) <= AMT_TOL
        ]
    if not rows and require_customer and cc and cust_col:
        return _find_billhdr_by_order(
            location_code,
            customer_code,
            order_id,
            invoice_amount,
            require_customer=False,
        )
    return rows


def _validate_line_against_billhdr(
    location_code: int,
    customer_code: str,
    order_id: str,
    upload_invoice_amount: Optional[float],
) -> Tuple[str, str]:
    """Return (status, message) using BILLHDR.ORDERNO and NETBILLAMOUNT."""
    oid = _normalize_order_id(order_id)
    if not oid:
        return (STATUS_VALIDATION_ERROR, 'OrderId is required')
    if upload_invoice_amount is None:
        return (STATUS_VALIDATION_ERROR, 'InvoiceAmount is required for BILLHDR match')

    hits = _find_billhdr_by_order(location_code, customer_code, oid, float(upload_invoice_amount))
    if hits:
        if len(hits) > 1:
            return (STATUS_MANUAL_REVIEW, f'Multiple BILLHDR rows ({len(hits)}) for OrderNo {oid}')
        hit = hits[0]
        erp_amt = round(abs(float(hit.get('netbillamount') or 0)), 2)
        return (
            'Validated',
            f"BILLHDR bill {hit.get('billno')} — OrderNo {oid}, NETBILLAMOUNT {erp_amt:.2f}",
        )

    all_by_order = _find_billhdr_by_order(location_code, customer_code, oid, invoice_amount=None)
    if not all_by_order:
        return (STATUS_ORDER_NOT_FOUND, f'No BILLHDR for OrderNo {oid} at location {location_code}')

    amounts = sorted({
        round(abs(float(r.get('netbillamount') or 0)), 2)
        for r in all_by_order
    })
    amt_hint = ', '.join(f'{a:.2f}' for a in amounts[:3])
    upload_amt = round(abs(float(upload_invoice_amount)), 2)
    return (
        STATUS_AMOUNT_MISMATCH,
        f'BILLHDR OrderNo {oid} found but NETBILLAMOUNT ({amt_hint}) != uploaded {upload_amt:.2f}',
    )


def _invoice_gl_voucher_no(location_code: int, billno: Any, *, is_return: bool = False) -> str:
    prefix = 'SR' if is_return else 'SI'
    try:
        bno = int(billno)
    except Exception:
        bno = billno
    return f'{prefix}-{int(location_code)}-{bno}'[:30]


def _order_already_posted(order_id: str, customer_code: str) -> bool:
    ensure_online_settlement_tables()
    rows = _safe_rows(
        f"""
        SELECT COUNT(*) AS cnt FROM {POSTED_ORDER_TABLE}
        WHERE ORDER_ID = :oid AND CUSTOMER_CODE = :cc
        """,
        {'oid': str(order_id).strip()[:80], 'cc': str(customer_code).strip()[:50]},
    )
    return bool(rows and int(rows[0].get('cnt') or 0) > 0)


def _invoice_open_amount(customer_code: str, invoice_voucher_no: str) -> Optional[float]:
    open_rows = get_customer_open_invoices_for_payment(customer_code) or []
    key = str(invoice_voucher_no or '').strip().upper()
    for r in open_rows:
        if str(r.get('voucher_no') or '').strip().upper() == key:
            return round(float(r.get('open_amount') or 0), 2)
    return None


def get_batch_header(batch_no: str) -> Optional[Dict[str, Any]]:
    ensure_online_settlement_tables()
    rows = _safe_rows(
        f"""
        SELECT BATCH_NO, LOCATION_CODE, CUSTOMER_CODE, MARKETPLACE_NAME,
               TO_CHAR(SETTLEMENT_DATE, 'YYYY-MM-DD') AS settlement_date,
               FILE_NAME, UPLOADED_BY, UPLOADED_AT, POSTED_BY, POSTED_AT, STATUS,
               TOTAL_ROWS, MATCHED_ROWS, POSTED_ROWS, FAILED_ROWS,
               BANK_ACCOUNT, PM_COMMISSION_ACCOUNT, SALES_COMMISSION_ACCOUNT, SPLUS_ACCOUNT,
               OTHER_CHARGES_ACCOUNT, REMARKS
        FROM {BATCH_TABLE}
        WHERE BATCH_NO = :bno
        """,
        {'bno': str(batch_no).strip()},
    )
    return rows[0] if rows else None


def list_batch_lines(batch_no: str) -> List[Dict[str, Any]]:
    ensure_online_settlement_tables()
    rows = _safe_rows(
        f"""
        SELECT LINE_ID, BATCH_NO, LINE_NO, ORDER_ID,
               UPLOAD_INVOICE_AMOUNT, TOTAL_AMOUNT, PM_COMMISSION, SALES_COMMISSION, SPLUS_AMOUNT,
               OTHER_CHARGES,
               ERP_BILLNO,
               TO_CHAR(ERP_INVOICE_DATE, 'YYYY-MM-DD') AS erp_invoice_date,
               ERP_INVOICE_AMOUNT, GL_VOUCHER_NO, STATUS, STATUS_MESSAGE,
               MANUAL_INVOICE_VOUCHER, EXCLUDED, POSTED_AT
        FROM {LINE_TABLE}
        WHERE BATCH_NO = :bno
        ORDER BY LINE_NO
        """,
        {'bno': str(batch_no).strip()},
    )
    out: List[Dict[str, Any]] = []
    for r in rows or []:
        inv_vno = r.get('manual_invoice_voucher') or ''
        if not inv_vno and r.get('erp_billno') is not None:
            hdr = get_batch_header(batch_no) or {}
            inv_vno = _invoice_gl_voucher_no(int(hdr.get('location_code') or 0), r.get('erp_billno'))
        item = dict(r)
        item['erp_invoice_no'] = inv_vno
        item['difference'] = None
        u = r.get('upload_invoice_amount')
        e = r.get('erp_invoice_amount')
        u_pos = _positive_amount(u)
        e_pos = _positive_amount(e)
        if u_pos is not None and e_pos is not None:
            item['difference'] = round(u_pos - e_pos, 2)
        item['net_amount_received'] = _positive_amount(r.get('total_amount'))
        _apply_positive_line_amounts(item)
        out.append(item)
    return out


def list_settlement_batches(limit: int = 100) -> List[Dict[str, Any]]:
    ensure_online_settlement_tables()
    return _safe_rows(
        f"""
        SELECT BATCH_NO, MARKETPLACE_NAME, CUSTOMER_CODE,
               TO_CHAR(SETTLEMENT_DATE, 'YYYY-MM-DD') AS settlement_date,
               FILE_NAME, UPLOADED_BY, UPLOADED_AT, POSTED_BY, POSTED_AT, STATUS,
               TOTAL_ROWS, MATCHED_ROWS, POSTED_ROWS, FAILED_ROWS
        FROM {BATCH_TABLE}
        ORDER BY UPLOADED_AT DESC NULLS LAST
        FETCH FIRST :lim ROWS ONLY
        """,
        {'lim': max(1, int(limit or 100))},
    ) or []


def validate_batch(batch_no: str) -> Tuple[bool, str]:
    hdr = get_batch_header(batch_no)
    if not hdr:
        return (False, 'Batch not found.')
    cc = str(hdr.get('customer_code') or '')
    loc = int(hdr.get('location_code') or 0)
    order_counts: Dict[str, int] = {}
    lines = list_batch_lines(batch_no)
    for ln in lines:
        oid = _normalize_order_id(ln.get('order_id'))
        if oid:
            order_counts[oid] = order_counts.get(oid, 0) + 1
    with _get_connection() as conn:
        try:
            with conn.cursor() as cur:
                for ln in lines:
                    if str(ln.get('excluded') or 'N').upper() == 'Y':
                        continue
                    status = STATUS_VALIDATION_ERROR
                    msg = ''
                    oid = _normalize_order_id(ln.get('order_id'))
                    if not oid:
                        msg = 'OrderId is required'
                    elif order_counts.get(oid, 0) > 1:
                        status = STATUS_DUPLICATE_ORDER
                        msg = 'Duplicate OrderId in upload file'
                    else:
                        ok, fmsg = validate_row_formula({
                            'upload_invoice_amount': ln.get('upload_invoice_amount'),
                            'total_amount': ln.get('total_amount'),
                            'pm_commission': ln.get('pm_commission'),
                            'sales_commission': ln.get('sales_commission'),
                            'splus_amount': ln.get('splus_amount'),
                            'other_charges': ln.get('other_charges'),
                        })
                        if not ok:
                            status = STATUS_VALIDATION_ERROR
                            msg = fmsg
                        else:
                            status, msg = _validate_line_against_billhdr(
                                loc,
                                cc,
                                oid,
                                ln.get('upload_invoice_amount'),
                            )
                    cur.execute(
                        f"""
                        UPDATE {LINE_TABLE}
                           SET STATUS = :st, STATUS_MESSAGE = :msg
                         WHERE LINE_ID = :lid
                        """,
                        {'st': status, 'msg': msg[:500], 'lid': int(ln['line_id'])},
                    )
                cur.execute(
                    f"UPDATE {BATCH_TABLE} SET STATUS = 'VALIDATED' WHERE BATCH_NO = :bno",
                    {'bno': batch_no},
                )
            conn.commit()
            return (True, '')
        except Exception as exc:
            conn.rollback()
            return (False, str(exc))


def auto_match_batch(batch_no: str) -> Tuple[bool, str]:
    hdr = get_batch_header(batch_no)
    if not hdr:
        return (False, 'Batch not found.')
    loc = int(hdr.get('location_code') or 0)
    cc = str(hdr.get('customer_code') or '')
    matched = 0
    with _get_connection() as conn:
        try:
            with conn.cursor() as cur:
                for ln in list_batch_lines(batch_no):
                    if str(ln.get('excluded') or 'N').upper() == 'Y':
                        continue
                    if ln.get('status') in (STATUS_DUPLICATE_ORDER, STATUS_VALIDATION_ERROR):
                        continue
                    if ln.get('status') in (STATUS_ORDER_NOT_FOUND, STATUS_AMOUNT_MISMATCH, STATUS_MANUAL_REVIEW):
                        continue
                    oid = _normalize_order_id(ln.get('order_id'))
                    status = STATUS_ORDER_NOT_FOUND
                    msg = 'No ERP invoice for OrderId + InvoiceAmount'
                    erp_billno = None
                    erp_date = None
                    erp_amt = None
                    manual_vno = str(ln.get('manual_invoice_voucher') or '').strip()
                    if manual_vno:
                        open_amt = _invoice_open_amount(cc, manual_vno)
                        if open_amt is None:
                            status = STATUS_MANUAL_REVIEW
                            msg = 'Manual invoice not found in open AR'
                        elif open_amt <= 0:
                            status = STATUS_ALREADY_SETTLED
                            msg = 'Manual invoice already fully settled'
                        else:
                            status = STATUS_MATCHED
                            msg = 'Manual match'
                            erp_amt = open_amt
                    elif oid:
                        if _order_already_posted(oid, cc):
                            status = STATUS_ALREADY_SETTLED
                            msg = 'OrderId already posted in prior settlement'
                        else:
                            inv_val = ln.get('upload_invoice_amount')
                            hits = _find_billhdr_by_order(
                                loc,
                                cc,
                                oid,
                                float(inv_val) if inv_val is not None else None,
                            )
                            if not hits:
                                status = STATUS_ORDER_NOT_FOUND
                                msg = f'No BILLHDR for OrderNo {oid}'
                            elif len(hits) > 1:
                                status = STATUS_MANUAL_REVIEW
                                msg = f'Multiple ERP invoices ({len(hits)}) — select manually'
                            else:
                                hit = hits[0]
                                erp_billno = hit.get('billno')
                                erp_amt = round(abs(float(hit.get('netbillamount') or 0)), 2)
                                erp_date = hit.get('billdate')
                                vno = _invoice_gl_voucher_no(loc, erp_billno)
                                open_amt = _invoice_open_amount(cc, vno)
                                if open_amt is None:
                                    status = STATUS_MANUAL_REVIEW
                                    msg = 'Invoice GL voucher not in open AR'
                                elif open_amt <= 0:
                                    status = STATUS_ALREADY_SETTLED
                                    msg = 'Invoice already fully settled'
                                elif inv_val is not None and abs(float(inv_val) - erp_amt) > AMT_TOL:
                                    status = STATUS_AMOUNT_MISMATCH
                                    msg = f'BILLHDR NETBILLAMOUNT {erp_amt:.2f} != uploaded {float(inv_val):.2f}'
                                else:
                                    status = STATUS_MATCHED
                                    msg = f'Matched bill {erp_billno}'
                    cur.execute(
                        f"""
                        UPDATE {LINE_TABLE}
                           SET STATUS = :st,
                               STATUS_MESSAGE = :msg,
                               ERP_BILLNO = :bno,
                               ERP_INVOICE_DATE = CASE WHEN :dte IS NOT NULL THEN TO_DATE(:dte, 'YYYY-MM-DD') ELSE NULL END,
                               ERP_INVOICE_AMOUNT = :eamt
                         WHERE LINE_ID = :lid
                        """,
                        {
                            'st': status,
                            'msg': msg[:500],
                            'bno': erp_billno,
                            'dte': _parse_date_iso(erp_date) if erp_date else None,
                            'eamt': erp_amt,
                            'lid': int(ln['line_id']),
                        },
                    )
                    if status == STATUS_MATCHED:
                        matched += 1
                cur.execute(
                    f"UPDATE {BATCH_TABLE} SET MATCHED_ROWS = :m, STATUS = 'MATCHED' WHERE BATCH_NO = :bno",
                    {'m': matched, 'bno': batch_no},
                )
            conn.commit()
            return (True, '')
        except Exception as exc:
            conn.rollback()
            return (False, str(exc))


def update_batch_line(line_id: int, *, manual_invoice_voucher: str = '', excluded: Optional[bool] = None) -> Tuple[bool, str]:
    ensure_online_settlement_tables()
    sets = []
    params: Dict[str, Any] = {'lid': int(line_id)}
    if manual_invoice_voucher is not None:
        sets.append('MANUAL_INVOICE_VOUCHER = :mv')
        params['mv'] = str(manual_invoice_voucher or '').strip()[:30] or None
    if excluded is not None:
        sets.append("EXCLUDED = :ex")
        params['ex'] = 'Y' if excluded else 'N'
        if excluded:
            sets.append("STATUS = :st")
            params['st'] = STATUS_EXCLUDED
    if not sets:
        return (True, '')
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE {LINE_TABLE} SET {', '.join(sets)} WHERE LINE_ID = :lid", params)
        conn.commit()
    return (True, '')


def _receivable_account(customer_code: str) -> str:
    cust = get_customer_master_by_code(customer_code) or {}
    return _norm_gl_account_code(
        cust.get('receivableaccount') or DEFAULT_PARTY_ACCOUNTS.get('customer_receivable') or '1200'
    )


def post_batch_lines(
    batch_no: str,
    *,
    line_ids: Optional[List[int]] = None,
    post_all_matched: bool = False,
    posted_by: str,
) -> Tuple[bool, str, Dict[str, Any]]:
    hdr = get_batch_header(batch_no)
    if not hdr:
        return (False, 'Batch not found.', {})
    cc = str(hdr.get('customer_code') or '')
    loc = int(hdr.get('location_code') or 0)
    settlement_date = str(hdr.get('settlement_date') or datetime.now().strftime('%Y-%m-%d'))
    try:
        from addons.accounts.period_closing_db import is_period_closed_for_date
        _pc_msg = is_period_closed_for_date(settlement_date, loc or None)
        if _pc_msg:
            return (False, _pc_msg, {})
    except Exception:
        pass
    bank = _norm_gl_account_code(hdr.get('bank_account') or '')
    pm_acc = _norm_gl_account_code(hdr.get('pm_commission_account') or '')
    sc_acc = _norm_gl_account_code(hdr.get('sales_commission_account') or '')
    sp_acc = _norm_gl_account_code(hdr.get('splus_account') or '')
    oc_acc = _norm_gl_account_code(hdr.get('other_charges_account') or '')
    recv = _receivable_account(cc)
    if not bank:
        return (False, 'Bank / clearing account is required on batch.', {})
    if not pm_acc or not sc_acc or not sp_acc:
        return (False, 'All commission expense accounts are required on batch.', {})
    id_set = {int(x) for x in (line_ids or []) if int(x or 0) > 0}
    lines = list_batch_lines(batch_no)
    targets = []
    for ln in lines:
        if str(ln.get('excluded') or 'N').upper() == 'Y':
            continue
        if ln.get('status') != STATUS_MATCHED:
            if post_all_matched:
                continue
            if int(ln.get('line_id') or 0) not in id_set:
                continue
            return (False, f"Line {ln.get('line_no')} is not Matched — cannot post.", {})
        if id_set and int(ln.get('line_id') or 0) not in id_set and not post_all_matched:
            continue
        if post_all_matched or int(ln.get('line_id') or 0) in id_set:
            targets.append(ln)
    if not targets:
        return (False, 'No matched lines selected for posting.', {})
    if any(round(abs(float(ln.get('other_charges') or 0)), 2) > 0 for ln in targets) and not oc_acc:
        return (False, 'Other charges expense account is required on batch.', {})
    posted = 0
    failed = 0
    receipt_nos: List[str] = []
    errors: List[str] = []
    party_line = {'party_type': 'CUSTOMER', 'party_code': cc[:50]}
    with _get_connection() as conn:
        try:
            for ln in targets:
                lid = int(ln['line_id'])
                oid = str(ln.get('order_id') or '').strip()
                inv_amt = round(float(ln.get('upload_invoice_amount') or 0), 2)
                net_amt = round(float(ln.get('total_amount') or 0), 2)
                pm = round(abs(float(ln.get('pm_commission') or 0)), 2)
                sc = round(abs(float(ln.get('sales_commission') or 0)), 2)
                sp = round(abs(float(ln.get('splus_amount') or 0)), 2)
                oc = round(abs(float(ln.get('other_charges') or 0)), 2)
                inv_vno = str(ln.get('manual_invoice_voucher') or ln.get('erp_invoice_no') or '').strip()
                if not inv_vno and ln.get('erp_billno') is not None:
                    inv_vno = _invoice_gl_voucher_no(loc, ln.get('erp_billno'))
                if _order_already_posted(oid, cc):
                    failed += 1
                    errors.append(f'{oid}: already settled')
                    with conn.cursor() as cur:
                        cur.execute(
                            f"UPDATE {LINE_TABLE} SET STATUS = :st, STATUS_MESSAGE = :msg WHERE LINE_ID = :lid",
                            {'st': STATUS_ALREADY_SETTLED, 'msg': 'Duplicate settlement blocked', 'lid': lid},
                        )
                    continue
                gl_lines: List[Dict[str, Any]] = []
                if net_amt > 0:
                    gl_lines.append({'account_code': bank, 'debit': net_amt, 'credit': 0, 'remarks': f'Online settlement {oid}'})
                if pm > 0:
                    gl_lines.append({'account_code': pm_acc, 'debit': pm, 'credit': 0, 'remarks': f'PM commission {oid}'})
                if sc > 0:
                    gl_lines.append({'account_code': sc_acc, 'debit': sc, 'credit': 0, 'remarks': f'Sales commission {oid}'})
                if sp > 0:
                    gl_lines.append({'account_code': sp_acc, 'debit': sp, 'credit': 0, 'remarks': f'SPlus merchant {oid}'})
                if oc > 0:
                    gl_lines.append({'account_code': oc_acc, 'debit': oc, 'credit': 0, 'remarks': f'Other charges {oid}'})
                if inv_amt > 0:
                    gl_lines.append({'account_code': recv, 'debit': 0, 'credit': inv_amt, 'remarks': f'Settle invoice {inv_vno}', **party_line})
                try:
                    vno = create_gl_journal_entry(
                        voucher_date=settlement_date,
                        reference_no=f'OS-{oid}'[:50],
                        narration=f'Online settlement {hdr.get("marketplace_name") or cc} order {oid}'[:500],
                        lines=gl_lines,
                        created_by=posted_by,
                        source='ONLINE_SETTLEMENT',
                        conn=conn,
                        commit=False,
                    )
                    with conn.cursor() as cur:
                        cur.execute(
                            f"""
                            INSERT INTO AR_CUSTOMER_PAYMENT_ALLOC
                                (ALLOC_ID, PAYMENT_VOUCHER_NO, CUSTOMER_CODE, INVOICE_VOUCHER_NO, ALLOCATED_AMOUNT, CREATED_BY)
                            VALUES
                                (AR_CUSTOMER_PAYMENT_ALLOC_SEQ.NEXTVAL, :pmt, :ccode, :inv, :amt, :usr)
                            """,
                            {
                                'pmt': vno[:30],
                                'ccode': cc[:50],
                                'inv': inv_vno[:30],
                                'amt': inv_amt,
                                'usr': (posted_by or '')[:50] or None,
                            },
                        )
                        cur.execute(
                            f"""
                            INSERT INTO {POSTED_ORDER_TABLE} (ORDER_ID, CUSTOMER_CODE, BATCH_NO, GL_VOUCHER_NO)
                            VALUES (:oid, :cc, :bno, :vno)
                            """,
                            {'oid': oid[:80], 'cc': cc[:50], 'bno': batch_no, 'vno': vno},
                        )
                        cur.execute(
                            f"""
                            UPDATE {LINE_TABLE}
                               SET STATUS = :st, STATUS_MESSAGE = :msg, GL_VOUCHER_NO = :vno, POSTED_AT = SYSTIMESTAMP
                             WHERE LINE_ID = :lid
                            """,
                            {'st': STATUS_POSTED, 'msg': 'Posted', 'vno': vno, 'lid': lid},
                        )
                    posted += 1
                    receipt_nos.append(vno)
                except Exception as row_exc:
                    failed += 1
                    errors.append(f'{oid}: {row_exc}')
                    with conn.cursor() as cur:
                        cur.execute(
                            f"""
                            UPDATE {LINE_TABLE}
                               SET STATUS = :st, STATUS_MESSAGE = :msg
                             WHERE LINE_ID = :lid
                            """,
                            {'st': STATUS_POST_FAILED, 'msg': str(row_exc)[:500], 'lid': lid},
                        )
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    UPDATE {BATCH_TABLE}
                       SET POSTED_ROWS = :p, FAILED_ROWS = :f, POSTED_BY = :usr, POSTED_AT = SYSTIMESTAMP,
                           STATUS = CASE WHEN :p > 0 AND :f = 0 THEN 'POSTED' WHEN :p > 0 THEN 'PARTIAL' ELSE STATUS END
                     WHERE BATCH_NO = :bno
                    """,
                    {'p': posted, 'f': failed, 'usr': (posted_by or '')[:50], 'bno': batch_no},
                )
            conn.commit()
        except Exception as exc:
            conn.rollback()
            return (False, str(exc), {})
    return (True, '', {'posted': posted, 'failed': failed, 'receipt_vouchers': receipt_nos, 'errors': errors})


def export_exception_rows(batch_no: str) -> List[Dict[str, Any]]:
    lines = list_batch_lines(batch_no)
    bad_statuses = {
        STATUS_ORDER_NOT_FOUND,
        STATUS_AMOUNT_MISMATCH,
        STATUS_ALREADY_SETTLED,
        STATUS_DUPLICATE_ORDER,
        STATUS_VALIDATION_ERROR,
        STATUS_MANUAL_REVIEW,
        STATUS_POST_FAILED,
    }
    return [ln for ln in lines if str(ln.get('status') or '') in bad_statuses]


def list_receipt_report(*, batch_no: str = '', date_from: str = '', date_to: str = '', limit: int = 5000) -> List[Dict[str, Any]]:
    ensure_online_settlement_tables()
    q = f"""
        SELECT l.ORDER_ID, l.ERP_BILLNO,
               TO_CHAR(l.ERP_INVOICE_DATE, 'YYYY-MM-DD') AS invoice_date,
               l.GL_VOUCHER_NO AS receipt_no, l.TOTAL_AMOUNT AS amount_received,
               l.ERP_INVOICE_AMOUNT AS invoice_amount,
               b.BATCH_NO, b.MARKETPLACE_NAME, b.CUSTOMER_CODE,
               TO_CHAR(b.SETTLEMENT_DATE, 'YYYY-MM-DD') AS settlement_date,
               TO_CHAR(l.POSTED_AT, 'YYYY-MM-DD') AS posted_date
        FROM {LINE_TABLE} l
        JOIN {BATCH_TABLE} b ON b.BATCH_NO = l.BATCH_NO
        WHERE l.STATUS = :posted
    """
    params: Dict[str, Any] = {'posted': STATUS_POSTED, 'lim': max(1, int(limit or 5000))}
    if batch_no:
        q += ' AND b.BATCH_NO = :bno'
        params['bno'] = str(batch_no).strip()
    if date_from:
        q += ' AND b.SETTLEMENT_DATE >= TO_DATE(:df, \'YYYY-MM-DD\')'
        params['df'] = _parse_date_iso(date_from)
    if date_to:
        q += ' AND b.SETTLEMENT_DATE <= TO_DATE(:dt, \'YYYY-MM-DD\')'
        params['dt'] = _parse_date_iso(date_to)
    q += ' ORDER BY l.POSTED_AT DESC NULLS LAST FETCH FIRST :lim ROWS ONLY'
    rows = _safe_rows(q, params) or []
    for r in rows:
        if r.get('erp_billno') is not None and not r.get('invoice_no'):
            loc_rows = _safe_rows(
                f'SELECT LOCATION_CODE FROM {BATCH_TABLE} WHERE BATCH_NO = :bno',
                {'bno': r.get('batch_no')},
            )
            loc = int((loc_rows[0].get('location_code') if loc_rows else 0) or 0)
            r['invoice_no'] = _invoice_gl_voucher_no(loc, r.get('erp_billno'))
        else:
            r.setdefault('invoice_no', '')
        _apply_positive_line_amounts(r)
    return rows


def list_commission_report(*, batch_no: str = '', date_from: str = '', date_to: str = '', limit: int = 5000) -> List[Dict[str, Any]]:
    ensure_online_settlement_tables()
    q = f"""
        SELECT l.ORDER_ID, b.BATCH_NO, b.MARKETPLACE_NAME, b.CUSTOMER_CODE,
               TO_CHAR(b.SETTLEMENT_DATE, 'YYYY-MM-DD') AS settlement_date,
               ABS(NVL(l.PM_COMMISSION, 0)) AS pm_commission,
               ABS(NVL(l.SALES_COMMISSION, 0)) AS sales_commission,
               ABS(NVL(l.SPLUS_AMOUNT, 0)) AS splus_amount,
               ABS(NVL(l.OTHER_CHARGES, 0)) AS other_charges,
               (ABS(NVL(l.PM_COMMISSION, 0)) + ABS(NVL(l.SALES_COMMISSION, 0)) + ABS(NVL(l.SPLUS_AMOUNT, 0))
                + ABS(NVL(l.OTHER_CHARGES, 0))) AS total_expenses,
               l.GL_VOUCHER_NO
        FROM {LINE_TABLE} l
        JOIN {BATCH_TABLE} b ON b.BATCH_NO = l.BATCH_NO
        WHERE l.STATUS = :posted
    """
    params: Dict[str, Any] = {'posted': STATUS_POSTED, 'lim': max(1, int(limit or 5000))}
    if batch_no:
        q += ' AND b.BATCH_NO = :bno'
        params['bno'] = str(batch_no).strip()
    if date_from:
        q += ' AND b.SETTLEMENT_DATE >= TO_DATE(:df, \'YYYY-MM-DD\')'
        params['df'] = _parse_date_iso(date_from)
    if date_to:
        q += ' AND b.SETTLEMENT_DATE <= TO_DATE(:dt, \'YYYY-MM-DD\')'
        params['dt'] = _parse_date_iso(date_to)
    q += ' ORDER BY b.SETTLEMENT_DATE DESC, l.LINE_NO FETCH FIRST :lim ROWS ONLY'
    return _safe_rows(q, params) or []


def list_exception_report(*, batch_no: str = '', limit: int = 5000) -> List[Dict[str, Any]]:
    ensure_online_settlement_tables()
    bad = (
        STATUS_ORDER_NOT_FOUND,
        STATUS_AMOUNT_MISMATCH,
        STATUS_ALREADY_SETTLED,
        STATUS_DUPLICATE_ORDER,
        STATUS_VALIDATION_ERROR,
        STATUS_MANUAL_REVIEW,
        STATUS_POST_FAILED,
    )
    placeholders = ', '.join(f':s{i}' for i in range(len(bad)))
    q = f"""
        SELECT l.LINE_NO, l.ORDER_ID, l.UPLOAD_INVOICE_AMOUNT, l.TOTAL_AMOUNT,
               l.STATUS, l.STATUS_MESSAGE, b.BATCH_NO, b.MARKETPLACE_NAME,
               TO_CHAR(b.UPLOADED_AT, 'YYYY-MM-DD') AS upload_date, b.UPLOADED_BY
        FROM {LINE_TABLE} l
        JOIN {BATCH_TABLE} b ON b.BATCH_NO = l.BATCH_NO
        WHERE l.STATUS IN ({placeholders})
          AND NVL(l.EXCLUDED, 'N') <> 'Y'
    """
    params: Dict[str, Any] = {f's{i}': s for i, s in enumerate(bad)}
    params['lim'] = max(1, int(limit or 5000))
    if batch_no:
        q += ' AND b.BATCH_NO = :bno'
        params['bno'] = str(batch_no).strip()
    q += ' ORDER BY b.UPLOADED_AT DESC, l.LINE_NO FETCH FIRST :lim ROWS ONLY'
    rows = _safe_rows(q, params) or []
    return [_apply_positive_line_amounts(dict(r)) for r in rows]


def list_coa_postable() -> List[Dict[str, Any]]:
    rows = get_all_chart_of_accounts() or []
    return [
        {'code': str(r.get('code') or '').strip(), 'name': str(r.get('name') or '').strip()}
        for r in rows
        if str(r.get('status') or 'ACTIVE').upper() == 'ACTIVE' and r.get('is_postable') and str(r.get('code') or '').strip()
    ]
