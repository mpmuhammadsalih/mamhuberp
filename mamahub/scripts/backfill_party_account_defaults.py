from pathlib import Path
import sys
from dotenv import load_dotenv
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / '.env')
from db import _detect_column, _detect_table, _get_connection, _get_table_columns, ensure_default_party_accounts, ensure_supplier_table

def _ensure_customer_account_columns(cur, customer_table: str) -> None:
    cols = _get_table_columns(customer_table)
    if 'RECEIVABLEACCOUNT' not in cols:
        cur.execute(f'ALTER TABLE {customer_table} ADD RECEIVABLEACCOUNT NUMBER(10)')
        if 'ACCOUNTCODE' in cols:
            cur.execute(f'\n                UPDATE {customer_table}\n                SET RECEIVABLEACCOUNT = ACCOUNTCODE\n                WHERE RECEIVABLEACCOUNT IS NULL\n                ')
    if 'SALESACCOUNT' not in cols:
        cur.execute(f'ALTER TABLE {customer_table} ADD SALESACCOUNT NUMBER(10)')
    if 'VATOUTPUTACCOUNT' not in cols:
        cur.execute(f'ALTER TABLE {customer_table} ADD VATOUTPUTACCOUNT NUMBER(10)')
    if 'ADVANCEACCOUNT' not in cols:
        cur.execute(f'ALTER TABLE {customer_table} ADD ADVANCEACCOUNT NUMBER(10)')

def _update_missing_accounts() -> None:
    defaults = ensure_default_party_accounts()
    ensure_supplier_table()
    supplier_table = _detect_table(['SUPPLIER', 'supplier'])
    customer_table = _detect_table(['CUSTOMER', 'customer', 'CUSTOMERS', 'customers'])
    if not supplier_table and (not customer_table):
        print('No supplier/customer tables found.')
        return
    summary = {'supplier': {}, 'customer': {}}
    with _get_connection() as conn:
        with conn.cursor() as cur:
            if supplier_table:
                s_cols = _get_table_columns(supplier_table)
                s_map = {_detect_column(supplier_table, ['PAYABLEACCOUNT', 'payableaccount']): int(defaults.get('supplier_payable') or 2110), _detect_column(supplier_table, ['PURCHASEACCOUNT', 'purchaseaccount']): int(defaults.get('supplier_purchase') or 5001), _detect_column(supplier_table, ['VATINPUTACCOUNT', 'vatinputaccount']): int(defaults.get('supplier_vat_input') or 2200), _detect_column(supplier_table, ['ADVANCEACCOUNT', 'advanceaccount']): int(defaults.get('supplier_advance') or 1230)}
                for col, value in s_map.items():
                    if not col or col.upper() not in s_cols:
                        continue
                    cur.execute(f'\n                        UPDATE {supplier_table}\n                        SET {col} = :v\n                        WHERE {col} IS NULL OR NVL({col}, 0) = 0\n                        ', {'v': value})
                    summary['supplier'][col] = int(cur.rowcount or 0)
            if customer_table:
                _ensure_customer_account_columns(cur, customer_table)
                c_cols = _get_table_columns(customer_table)
                c_map = {_detect_column(customer_table, ['RECEIVABLEACCOUNT', 'receivableaccount']): int(defaults.get('customer_receivable') or 1200), _detect_column(customer_table, ['SALESACCOUNT', 'salesaccount']): int(defaults.get('customer_sales') or 4100), _detect_column(customer_table, ['VATOUTPUTACCOUNT', 'vatoutputaccount']): int(defaults.get('customer_vat_output') or 2200), _detect_column(customer_table, ['ADVANCEACCOUNT', 'advanceaccount']): int(defaults.get('customer_advance') or 2130)}
                for col, value in c_map.items():
                    if not col or col.upper() not in c_cols:
                        continue
                    cur.execute(f'\n                        UPDATE {customer_table}\n                        SET {col} = :v\n                        WHERE {col} IS NULL OR NVL({col}, 0) = 0\n                        ', {'v': value})
                    summary['customer'][col] = int(cur.rowcount or 0)
        conn.commit()
    print('Backfill completed.')
    print(f"Supplier table: {supplier_table or '-'}")
    for col, cnt in summary['supplier'].items():
        print(f'  {col}: {cnt} rows updated')
    print(f"Customer table: {customer_table or '-'}")
    for col, cnt in summary['customer'].items():
        print(f'  {col}: {cnt} rows updated')
if __name__ == '__main__':
    _update_missing_accounts()
