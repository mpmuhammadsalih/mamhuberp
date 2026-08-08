import argparse
from typing import Dict, List, Optional, Tuple
from db.oracle_driver import oracle_connect
from dotenv import load_dotenv
import config.settings as s

def _table_exists(cur, table_name: str) -> bool:
    cur.execute('SELECT COUNT(*) FROM user_tables WHERE UPPER(table_name) = :t', {'t': table_name.upper()})
    return int(cur.fetchone()[0] or 0) > 0

def _detect_column(cur, table_name: str, candidates: List[str]) -> Optional[str]:
    cur.execute('SELECT column_name FROM user_tab_columns WHERE UPPER(table_name)=:t', {'t': table_name.upper()})
    cols = {r[0].upper() for r in cur.fetchall() or []}
    for c in candidates:
        if c.upper() in cols:
            return c.upper()
    return None

def _get_active_tenants() -> List[Tuple]:
    auth = s.get_auth_db_config()
    conn = oracle_connect(user=auth['user'], password=auth['password'], dsn=auth['dsn'])
    cur = conn.cursor()
    cur.execute("\n        SELECT tenant_id, ip, port, service_name, username, password\n        FROM tenant_databases\n        WHERE NVL(active_flag, 'Y') = 'Y'\n        ORDER BY tenant_id\n        ")
    rows = cur.fetchall() or []
    cur.close()
    conn.close()
    return rows

def _connect_tenant(row: Tuple):
    tid, ip, port, svc, user, pwd = row
    dsn = f'{str(ip).strip()}:{str(port).strip()}/{str(svc).strip()}'
    conn = oracle_connect(user=str(user).strip(), password=pwd or '', dsn=dsn)
    return (tid, conn)

def _find_tenant_with_receipt(receipt_no: int, location_code: int) -> Optional[Tuple]:
    for row in _get_active_tenants():
        try:
            tid, conn = _connect_tenant(row)
            cur = conn.cursor()
            if not _table_exists(cur, 'RECEIPTHDR'):
                cur.close()
                conn.close()
                continue
            loc_col = _detect_column(cur, 'RECEIPTHDR', ['LOCATIONCODE', 'LOCATION_CODE'])
            no_col = _detect_column(cur, 'RECEIPTHDR', ['RECEIPTNO', 'RECEIPT_NO'])
            if not loc_col or not no_col:
                cur.close()
                conn.close()
                continue
            q = f'SELECT COUNT(*) FROM RECEIPTHDR WHERE {loc_col} = :loc AND {no_col} = :rno'
            cur.execute(q, {'loc': location_code, 'rno': receipt_no})
            count = int(cur.fetchone()[0] or 0)
            cur.close()
            conn.close()
            if count > 0:
                return row
        except Exception:
            continue
    return None

def main():
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument('--receipt', type=int, required=True)
    parser.add_argument('--location', type=int, required=True)
    args = parser.parse_args()
    receipt_no = args.receipt
    location_code = args.location
    voucher_no = f'GRN-{location_code}-{receipt_no}'
    tenant_row = _find_tenant_with_receipt(receipt_no, location_code)
    if not tenant_row:
        print(f'Receipt {receipt_no} (location {location_code}) not found in active tenants.')
        return
    tid, conn = _connect_tenant(tenant_row)
    cur = conn.cursor()
    print(f'Tenant: {tid}')
    print(f'Voucher: {voucher_no}')
    loc_col = _detect_column(cur, 'RECEIPTHDR', ['LOCATIONCODE', 'LOCATION_CODE'])
    no_col = _detect_column(cur, 'RECEIPTHDR', ['RECEIPTNO', 'RECEIPT_NO'])
    date_col = _detect_column(cur, 'RECEIPTHDR', ['RECEIPTDATE', 'RECEIPT_DATE'])
    sup_col = _detect_column(cur, 'RECEIPTHDR', ['SUPPLIERCODE', 'SUPPLIER_CODE'])
    inv_no_col = _detect_column(cur, 'RECEIPTHDR', ['INVOICENO', 'INVOICE_NO'])
    inv_date_col = _detect_column(cur, 'RECEIPTHDR', ['INVOICEDATE', 'INVOICE_DATE'])
    inv_amt_col = _detect_column(cur, 'RECEIPTHDR', ['INVOICEAMOUNT', 'INVOICE_AMOUNT'])
    disc_col = _detect_column(cur, 'RECEIPTHDR', ['DISCOUNT'])
    mode_col = _detect_column(cur, 'RECEIPTHDR', ['APPROVE_MODE', 'POSTMODE', 'SAVE_MODE'])
    rem_col = _detect_column(cur, 'RECEIPTHDR', ['REMARKS'])
    hdr_cols = [c for c in [date_col, sup_col, inv_no_col, inv_date_col, inv_amt_col, disc_col, mode_col, rem_col] if c]
    cur.execute(f"SELECT {', '.join(hdr_cols)} FROM RECEIPTHDR WHERE {loc_col}=:loc AND {no_col}=:rno", {'loc': location_code, 'rno': receipt_no})
    hdr = cur.fetchone()
    print('\nRECEIPTHDR:')
    if hdr:
        for i, c in enumerate(hdr_cols):
            print(f'  {c}: {hdr[i]}')
    else:
        print('  not found')
    d_loc = _detect_column(cur, 'RECEIPTDTL', ['LOCATIONCODE', 'LOCATION_CODE'])
    d_no = _detect_column(cur, 'RECEIPTDTL', ['RECEIPTNO', 'RECEIPT_NO'])
    d_amt = _detect_column(cur, 'RECEIPTDTL', ['AMOUNT'])
    d_rate = _detect_column(cur, 'RECEIPTDTL', ['RATE'])
    d_qty = _detect_column(cur, 'RECEIPTDTL', ['QUANTITY'])
    if d_amt:
        cur.execute(f'SELECT COUNT(*), ROUND(SUM(NVL({d_amt},0)),3) FROM RECEIPTDTL WHERE {d_loc}=:loc AND {d_no}=:rno', {'loc': location_code, 'rno': receipt_no})
        line_count, dtl_amount_sum = cur.fetchone()
    else:
        cur.execute(f'SELECT COUNT(*), ROUND(SUM(NVL({d_rate},0)*NVL({d_qty},0)),3) FROM RECEIPTDTL WHERE {d_loc}=:loc AND {d_no}=:rno', {'loc': location_code, 'rno': receipt_no})
        line_count, dtl_amount_sum = cur.fetchone()
    print('\nRECEIPTDTL:')
    print(f'  lines: {int(line_count or 0)}')
    print(f'  amount_sum: {float(dtl_amount_sum or 0):.3f}')
    if _table_exists(cur, 'TBLGRNPOSTINGHDR'):
        cur.execute('\n            SELECT SUBTOTAL, VATAMOUNT, TOTALAMOUNT, SUPPLIERCODE, RECEIPTDATE\n            FROM TBLGRNPOSTINGHDR\n            WHERE LOCATIONCODE=:loc AND RECEIPTNO=:rno\n            ', {'loc': location_code, 'rno': receipt_no})
        ph = cur.fetchone()
        print('\nTBLGRNPOSTINGHDR:')
        if ph:
            print(f'  subtotal: {float(ph[0] or 0):.3f}')
            print(f'  vatamount: {float(ph[1] or 0):.3f}')
            print(f'  totalamount: {float(ph[2] or 0):.3f}')
            print(f'  suppliercode: {ph[3]}')
            print(f'  receiptdate: {ph[4]}')
        else:
            print('  no posting hdr row')
    if _table_exists(cur, 'TBLGRNPOSTINGDTL'):
        cur.execute('\n            SELECT ROUND(SUM(NVL(DRAMOUNT,0)),3), ROUND(SUM(NVL(CRAMOUNT,0)),3), COUNT(*)\n            FROM TBLGRNPOSTINGDTL\n            WHERE LOCATIONCODE=:loc AND RECEIPTNO=:rno\n            ', {'loc': location_code, 'rno': receipt_no})
        dr, cr, cnt = cur.fetchone()
        print('\nTBLGRNPOSTINGDTL:')
        print(f'  lines: {int(cnt or 0)}')
        print(f'  total_dr: {float(dr or 0):.3f}')
        print(f'  total_cr: {float(cr or 0):.3f}')
    if _table_exists(cur, 'GL_VOUCHER_HDR'):
        cur.execute('\n            SELECT VOUCHER_DATE, REFERENCE_NO, NARRATION, SOURCE, CREATED_BY\n            FROM GL_VOUCHER_HDR\n            WHERE VOUCHER_NO = :vno\n            ', {'vno': voucher_no})
        gh = cur.fetchone()
        print('\nGL_VOUCHER_HDR:')
        if gh:
            print(f'  voucher_date: {gh[0]}')
            print(f'  reference_no: {gh[1]}')
            print(f'  narration: {gh[2]}')
            print(f'  source: {gh[3]}')
            print(f'  created_by: {gh[4]}')
        else:
            print('  no gl hdr row')
    if _table_exists(cur, 'GL_VOUCHER_DTL'):
        cur.execute('\n            SELECT ROUND(SUM(NVL(DEBIT,0)),2), ROUND(SUM(NVL(CREDIT,0)),2), COUNT(*)\n            FROM GL_VOUCHER_DTL\n            WHERE VOUCHER_NO = :vno\n            ', {'vno': voucher_no})
        dr, cr, cnt = cur.fetchone()
        print('\nGL_VOUCHER_DTL:')
        print(f'  lines: {int(cnt or 0)}')
        print(f'  total_debit: {float(dr or 0):.2f}')
        print(f'  total_credit: {float(cr or 0):.2f}')
        cur.execute('\n            SELECT LINE_NO, ACCOUNT_CODE, DEBIT, CREDIT, REMARKS, PARTY_TYPE, PARTY_CODE\n            FROM GL_VOUCHER_DTL\n            WHERE VOUCHER_NO = :vno\n            ORDER BY LINE_NO\n            ', {'vno': voucher_no})
        print('  detail:')
        for r in cur.fetchall() or []:
            print(f'    ln={r[0]} acc={r[1]} dr={float(r[2] or 0):.2f} cr={float(r[3] or 0):.2f} party={r[5]}/{r[6]} rem={r[4]}')
    cur.close()
    conn.close()
if __name__ == '__main__':
    main()
