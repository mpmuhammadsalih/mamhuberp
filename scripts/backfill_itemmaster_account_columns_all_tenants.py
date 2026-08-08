from pathlib import Path
import sys
from typing import Dict, List, Optional
from dotenv import load_dotenv
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / '.env')
from db.oracle_driver import oracle_connect
from config.settings import is_multi_db_mode
from db import DEFAULT_PARTY_ACCOUNTS, _get_connection, get_tenant_config, get_tenant_list

def _table_exists(cur, table_name: str) -> bool:
    cur.execute('SELECT COUNT(*) FROM user_tables WHERE table_name = :t', {'t': table_name.upper()})
    return int(cur.fetchone()[0] or 0) > 0

def _get_cols(cur, table_name: str) -> List[str]:
    cur.execute('SELECT COLUMN_NAME FROM USER_TAB_COLUMNS WHERE TABLE_NAME = :t', {'t': table_name.upper()})
    return [str(r[0]).upper() for r in cur.fetchall() or []]

def _backfill_itemmaster(conn, label: str) -> None:
    defaults: Dict[str, int] = {'SALESACCOUNT': int(DEFAULT_PARTY_ACCOUNTS.get('customer_sales') or 4100), 'PURCHASEACCOUNT': int(DEFAULT_PARTY_ACCOUNTS.get('supplier_purchase') or 5001), 'INVENTORYACCOUNT': 1300, 'COGSACCOUNT': 5100}
    with conn.cursor() as cur:
        if not _table_exists(cur, 'ITEMMASTER'):
            print(f'[{label}] ITEMMASTER not found')
            return
        cols = _get_cols(cur, 'ITEMMASTER')
        for col in defaults.keys():
            if col not in cols:
                cur.execute(f'ALTER TABLE ITEMMASTER ADD {col} NUMBER(10)')
        updated: Dict[str, int] = {}
        for col, val in defaults.items():
            cur.execute(f'\n                UPDATE ITEMMASTER\n                SET {col} = :v\n                WHERE {col} IS NULL OR NVL({col}, 0) = 0\n                ', {'v': val})
            updated[col] = int(cur.rowcount or 0)
        conn.commit()
    print(f'\n[{label}] ITEMMASTER backfill completed')
    for col, cnt in updated.items():
        print(f'  {col}: {cnt}')

def _run_single() -> None:
    with _get_connection() as conn:
        _backfill_itemmaster(conn, 'DEFAULT_DB')

def _run_multi() -> None:
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
            _backfill_itemmaster(conn, f'TENANT:{tid}')
if __name__ == '__main__':
    if is_multi_db_mode():
        _run_multi()
    else:
        _run_single()
