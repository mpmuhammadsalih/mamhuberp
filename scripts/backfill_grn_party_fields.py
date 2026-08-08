from dotenv import load_dotenv
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
load_dotenv()
import db

def main() -> None:
    db.ensure_gl_tables()
    conn = db._get_connection()
    cur = conn.cursor()
    try:
        cur.execute("\n            SELECT d.LINE_ID, d.VOUCHER_NO, h.REFERENCE_NO\n            FROM GL_VOUCHER_DTL d\n            JOIN GL_VOUCHER_HDR h ON h.VOUCHER_NO = d.VOUCHER_NO\n            WHERE h.SOURCE = 'GRN'\n              AND (d.PARTY_TYPE IS NULL OR d.PARTY_CODE IS NULL)\n            ")
        rows = cur.fetchall() or []
        receipt_hdr = db._detect_table(['RECEIPTHDR', 'receipthdr'])
        loc_col = db._detect_column(receipt_hdr, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode']) if receipt_hdr else None
        rno_col = db._detect_column(receipt_hdr, ['RECEIPTNO', 'RECEIPT_NO', 'receiptno']) if receipt_hdr else None
        sup_col = db._detect_column(receipt_hdr, ['SUPPLIERCODE', 'SUPPLIER_CODE', 'suppliercode']) if receipt_hdr else None
        updated = 0
        for line_id, voucher_no, ref_no in rows:
            supplier_code = None
            vno = voucher_no or ''
            if vno.startswith('GRN-'):
                parts = vno.split('-')
                if len(parts) >= 3 and parts[-1].isdigit() and loc_col and rno_col and sup_col and receipt_hdr:
                    try:
                        loc = int(parts[-2]) if parts[-2].isdigit() else None
                        receipt_no = int(parts[-1])
                        if loc is not None:
                            q = f'SELECT {sup_col} FROM {receipt_hdr} WHERE {loc_col} = :loc AND {rno_col} = :rno'
                            cur.execute(q, {'loc': loc, 'rno': receipt_no})
                        else:
                            q = f'SELECT {sup_col} FROM {receipt_hdr} WHERE {rno_col} = :rno'
                            cur.execute(q, {'rno': receipt_no})
                        r = cur.fetchone()
                        if r and r[0] is not None:
                            supplier_code = str(r[0])
                    except Exception:
                        pass
            if supplier_code is None and isinstance(ref_no, str) and ref_no.startswith('GRN-') and ref_no.split('-')[-1].isdigit() and rno_col and sup_col and receipt_hdr:
                try:
                    receipt_no = int(ref_no.split('-')[-1])
                    q = f'SELECT {sup_col} FROM {receipt_hdr} WHERE {rno_col} = :rno AND ROWNUM = 1'
                    cur.execute(q, {'rno': receipt_no})
                    r = cur.fetchone()
                    if r and r[0] is not None:
                        supplier_code = str(r[0])
                except Exception:
                    pass
            if supplier_code is not None:
                cur.execute("UPDATE GL_VOUCHER_DTL SET PARTY_TYPE = 'SUPPLIER', PARTY_CODE = :pc WHERE LINE_ID = :lid", {'pc': supplier_code[:50], 'lid': line_id})
                updated += cur.rowcount or 0
        conn.commit()
        cur.execute("\n            SELECT COUNT(*)\n            FROM GL_VOUCHER_DTL d\n            JOIN GL_VOUCHER_HDR h ON h.VOUCHER_NO = d.VOUCHER_NO\n            WHERE h.SOURCE = 'GRN'\n              AND (d.PARTY_TYPE IS NULL OR d.PARTY_CODE IS NULL)\n            ")
        remaining = int(cur.fetchone()[0] or 0)
        print(f'UPDATED_ROWS={updated}')
        print(f'REMAINING_MISSING={remaining}')
    finally:
        cur.close()
        conn.close()
if __name__ == '__main__':
    main()
