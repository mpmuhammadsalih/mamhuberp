"""Compare ITEMJOURNEL / ITEMJOURNAL columns to Nexa app expectations."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / '.env')

from db import _get_connection, _get_table_columns, _table_exists

EXPECTED = {
    'core (required)': [
        'LOCATIONCODE', 'RESETNO', 'RECEIPTNO', 'LINENO', 'ITEMCODE', 'UOM', 'QTY',
        'RATE', 'AMOUNT', 'WAREHOUSE_CODE', 'WAREHOUSE_ID', 'CREATEDDATE',
    ],
    'vat / totals': ['VATPERCENT', 'VATAMOUNT', 'TOTALAMOUNT', 'AVERAGECOST'],
    'document trace': ['TOTALINVENTORY', 'TRANSTYPE', 'SOURCE_DOC', 'SOURCE_NO'],
    'GRN / warehouse': ['SUPPLIERCODE', 'SUPPLIERNAME', 'STORAGE_ID', 'WAREHOUSE_ID'],
    'surrogate PK': ['ITEMJOURNAL_ID'],
    'optional (reports/UI)': ['ITEMNAME'],
    'batch / lot (not wired in GRN save yet)': [
        'BATCH_NO', 'BATCHNO', 'MFG_DATE', 'EXPIRY_DATE', 'LOT_ID',
    ],
}


def main() -> None:
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM user_tables WHERE UPPER(table_name) LIKE '%ITEMJOURN%' ORDER BY 1"
            )
            tables = [r[0] for r in cur.fetchall()]
    print('Tables in schema:', ', '.join(tables) if tables else '(none)')

    for tbl in ('ITEMJOURNEL', 'ITEMJOURNAL'):
        print('\n' + '=' * 60)
        print(tbl)
        print('=' * 60)
        if not _table_exists(tbl):
            print('  Not present in this database.')
            continue
        cols = sorted({str(c).upper() for c in (_get_table_columns(tbl) or [])})
        print(f'  Total columns: {len(cols)}')
        all_expected = {n for names in EXPECTED.values() for n in names}
        for grp, names in EXPECTED.items():
            miss = [n for n in names if n not in cols]
            if miss:
                print(f'  {grp}: MISSING -> {", ".join(miss)}')
            else:
                print(f'  {grp}: OK')
        extra = sorted(c for c in cols if c not in all_expected)
        if extra:
            print('  Extra columns (not in app checklist):', ', '.join(extra))
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f'SELECT COUNT(*) FROM {tbl}')
                print(f'  Row count: {cur.fetchone()[0]}')


if __name__ == '__main__':
    main()
