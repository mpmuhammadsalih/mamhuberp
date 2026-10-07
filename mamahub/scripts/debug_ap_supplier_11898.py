from pathlib import Path
import sys
from dotenv import load_dotenv
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
load_dotenv()
import db

def main() -> None:
    conn = db._get_connection()
    cur = conn.cursor()
    try:
        cur.execute('SELECT LOCATIONCODE, SUPPLIERCODE, SUPPLIERNAME, PAYABLEACCOUNT FROM SUPPLIER WHERE SUPPLIERCODE = :s', {'s': 11898})
        srows = cur.fetchall()
        cur.execute("SELECT ACCOUNT_CODE, SUM(DEBIT), SUM(CREDIT) FROM GL_VOUCHER_DTL WHERE PARTY_TYPE = 'SUPPLIER' AND PARTY_CODE = :pc GROUP BY ACCOUNT_CODE ORDER BY ACCOUNT_CODE", {'pc': '11898'})
        grows = cur.fetchall()
    finally:
        cur.close()
        conn.close()
    aps = [r for r in db.get_accounts_payable_summary() if str(r.get('suppliercode') or '').strip() == '11898']
    print('SUPPLIER_ROW', srows)
    print('GL_PARTY_ROWS', grows)
    print('AP_SUMMARY_ROW', aps[:3])
if __name__ == '__main__':
    main()
