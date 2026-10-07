from pathlib import Path
import sys
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / '.env')
from db.oracle_driver import oracle_connect
from config.settings import is_multi_db_mode
from db import DEFAULT_PARTY_ACCOUNTS, get_tenant_config, get_tenant_list, _get_connection

def _table_exists(cur, table_name: str) -> bool:
    cur.execute('SELECT COUNT(*) FROM user_tables WHERE table_name = :t', {'t': table_name.upper()})
    return int(cur.fetchone()[0] or 0) > 0

def _detect_table(cur, candidates: List[str]) -> Optional[str]:
    for t in candidates:
        if _table_exists(cur, t):
            return t.upper()
    return None

def _get_cols(cur, table_name: str) -> List[str]:
    cur.execute('SELECT COLUMN_NAME FROM USER_TAB_COLUMNS WHERE TABLE_NAME = :t', {'t': table_name.upper()})
    return [str(r[0]).upper() for r in cur.fetchall() or []]

def _ensure_col(cur, table_name: str, col_name: str) -> None:
    cols = _get_cols(cur, table_name)
    if col_name.upper() not in cols:
        cur.execute(f'ALTER TABLE {table_name} ADD {col_name} NUMBER(10)')

def _update_missing(cur, table_name: str, col_name: str, value: int) -> int:
    cur.execute(f'\n        UPDATE {table_name}\n        SET {col_name} = :v\n        WHERE {col_name} IS NULL OR NVL({col_name}, 0) = 0\n        ', {'v': int(value)})
    return int(cur.rowcount or 0)

def _backfill_on_conn(conn, label: str) -> Dict[str, Dict[str, int]]:
    result = {'supplier': {}, 'customer': {}}
    with conn.cursor() as cur:
        supplier = _detect_table(cur, ['SUPPLIER', 'supplier'])
        customer = _detect_table(cur, ['CUSTOMER', 'customer', 'CUSTOMERS', 'customers'])
        if supplier:
            for col in ['PAYABLEACCOUNT', 'PURCHASEACCOUNT', 'VATINPUTACCOUNT', 'ADVANCEACCOUNT']:
                _ensure_col(cur, supplier, col)
            result['supplier']['PAYABLEACCOUNT'] = _update_missing(cur, supplier, 'PAYABLEACCOUNT', int(DEFAULT_PARTY_ACCOUNTS.get('supplier_payable') or 2110))
            result['supplier']['PURCHASEACCOUNT'] = _update_missing(cur, supplier, 'PURCHASEACCOUNT', int(DEFAULT_PARTY_ACCOUNTS.get('supplier_purchase') or 5001))
            result['supplier']['VATINPUTACCOUNT'] = _update_missing(cur, supplier, 'VATINPUTACCOUNT', int(DEFAULT_PARTY_ACCOUNTS.get('supplier_vat_input') or 2200))
            result['supplier']['ADVANCEACCOUNT'] = _update_missing(cur, supplier, 'ADVANCEACCOUNT', int(DEFAULT_PARTY_ACCOUNTS.get('supplier_advance') or 1230))
        if customer:
            for col in ['RECEIVABLEACCOUNT', 'SALESACCOUNT', 'VATOUTPUTACCOUNT', 'ADVANCEACCOUNT']:
                _ensure_col(cur, customer, col)
            result['customer']['RECEIVABLEACCOUNT'] = _update_missing(cur, customer, 'RECEIVABLEACCOUNT', int(DEFAULT_PARTY_ACCOUNTS.get('customer_receivable') or 1200))
            result['customer']['SALESACCOUNT'] = _update_missing(cur, customer, 'SALESACCOUNT', int(DEFAULT_PARTY_ACCOUNTS.get('customer_sales') or 4100))
            result['customer']['VATOUTPUTACCOUNT'] = _update_missing(cur, customer, 'VATOUTPUTACCOUNT', int(DEFAULT_PARTY_ACCOUNTS.get('customer_vat_output') or 2200))
            result['customer']['ADVANCEACCOUNT'] = _update_missing(cur, customer, 'ADVANCEACCOUNT', int(DEFAULT_PARTY_ACCOUNTS.get('customer_advance') or 2130))
    conn.commit()
    print(f'\n[{label}] Backfill completed')
    for k, v in result.items():
        for col, cnt in v.items():
            print(f'  {k}.{col}: {cnt}')
    return result

def _run_single_db() -> None:
    with _get_connection() as conn:
        _backfill_on_conn(conn, 'DEFAULT_DB')

def _run_multi_tenant() -> None:
    tenants = get_tenant_list() or []
    if not tenants:
        print('No active tenants found.')
        return
    for t in tenants:
        tid = (t.get('tenant_id') or '').strip()
        if not tid:
            continue
        cfg = get_tenant_config(tid)
        with oracle_connect(user=cfg['user'], password=cfg['password'], dsn=cfg['dsn']) as conn:
            _backfill_on_conn(conn, f'TENANT:{tid}')
if __name__ == '__main__':
    if is_multi_db_mode():
        _run_multi_tenant()
    else:
        _run_single_db()
