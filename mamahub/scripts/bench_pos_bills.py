import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))
from datetime import datetime
from db import list_pos_bills_posted, _safe_rows, _get_table_columns, _append_pos_posted_scope_filters, _pos_bills_date_filters

today = datetime.now().strftime('%Y-%m-%d')
cols = _get_table_columns('BILLHDR')
cols_u = {str(c).upper() for c in cols}
select_cols = [c for c in ['BILLNO', 'BILLDATE', 'COUNTERCODE', 'LOCATIONCODE'] if c in cols_u]

where_exists = ['LOCATIONCODE = :loc']
params = {'loc': 1, 'lim': 500}
if 'DELFLAG' in cols_u:
    where_exists.append("NVL(DELFLAG, 'N') <> 'Y'")
_append_pos_posted_scope_filters(where_exists, cols_u)
_pos_bills_date_filters(where_exists, params, cols_u, from_dt=today, to_dt=today)
q_exists = f"SELECT * FROM (SELECT {', '.join(select_cols)} FROM BILLHDR WHERE {' AND '.join(where_exists)} ORDER BY BILLDATE DESC, BILLNO DESC) WHERE ROWNUM <= :lim"

where_counter = ['LOCATIONCODE = :loc', 'NVL(COUNTERCODE, 0) > 0']
if 'DELFLAG' in cols_u:
    where_counter.append("NVL(DELFLAG, 'N') <> 'Y'")
_pos_bills_date_filters(where_counter, params, cols_u, from_dt=today, to_dt=today)
q_counter = f"SELECT * FROM (SELECT {', '.join(select_cols)} FROM BILLHDR WHERE {' AND '.join(where_counter)} ORDER BY BILLDATE DESC, BILLNO DESC) WHERE ROWNUM <= :lim"

for label, q in [('EXISTS', q_exists), ('COUNTER', q_counter)]:
    t0 = time.perf_counter()
    rows = _safe_rows(q, params) or []
    print(f'{label}: {len(rows)} rows in {(time.perf_counter()-t0)*1000:.0f}ms')

t0 = time.perf_counter()
rows = list_pos_bills_posted(1, limit=500, from_dt=today, to_dt=today, pos_only=True)
print(f'list_pos_bills_posted: {len(rows)} rows in {(time.perf_counter()-t0)*1000:.0f}ms')
