from collections import Counter
from db.oracle_driver import oracle_connect
from dotenv import load_dotenv
load_dotenv()
import config.settings as s

def norm(v):
    t = str(v or '').strip()
    if not t:
        return ''
    try:
        f = float(t)
        if f.is_integer():
            return str(int(f))
    except Exception:
        pass
    return t

def get_active_tenants():
    auth = s.get_auth_db_config()
    conn = oracle_connect(user=auth['user'], password=auth['password'], dsn=auth['dsn'])
    cur = conn.cursor()
    cur.execute("\n        SELECT tenant_id, ip, port, service_name, username, password\n        FROM tenant_databases\n        WHERE NVL(active_flag, 'Y') = 'Y'\n        ORDER BY tenant_id\n        ")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

def connect_tenant(tenant_row):
    tid, ip, port, svc, user, pwd = tenant_row
    dsn = f'{str(ip).strip()}:{str(port).strip()}/{str(svc).strip()}'
    return (tid, oracle_connect(user=str(user).strip(), password=pwd or '', dsn=dsn))

def pick_target_tenant(tenants):
    for row in tenants:
        try:
            tid, conn = connect_tenant(row)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM user_tables WHERE UPPER(table_name) IN ('SUPPLIER','GL_VOUCHER_DTL','CHART_OF_ACCOUNTS')")
            needed = int(cur.fetchone()[0] or 0)
            if needed < 3:
                cur.close()
                conn.close()
                continue
            cur.execute("SELECT COUNT(*) FROM supplier WHERE TRIM(TO_CHAR(suppliercode)) IN ('10001','10002','10003')")
            m = int(cur.fetchone()[0] or 0)
            cur.execute('SELECT COUNT(*) FROM supplier')
            total_sup = int(cur.fetchone()[0] or 0)
            cur.execute('SELECT COUNT(*) FROM gl_voucher_dtl')
            gl_rows = int(cur.fetchone()[0] or 0)
            cur.close()
            conn.close()
            if m > 0 and gl_rows > 0:
                return (row, total_sup, m)
        except Exception:
            continue
    return (None, 0, 0)

def run_diagnostic(target_row):
    tid, conn = connect_tenant(target_row)
    cur = conn.cursor()
    cur.execute('SELECT TRIM(TO_CHAR(locationcode)), TRIM(TO_CHAR(suppliercode)), suppliername, TRIM(TO_CHAR(payableaccount)) FROM supplier')
    sup_rows = cur.fetchall()
    cur.execute('SELECT TRIM(TO_CHAR(account_code)) acc, ROUND(SUM(NVL(credit,0)-NVL(debit,0)),2) bal FROM gl_voucher_dtl GROUP BY TRIM(TO_CHAR(account_code))')
    acc_bal = {norm(r[0]): float(r[1] or 0) for r in cur.fetchall()}
    cur.execute("\n        SELECT TRIM(TO_CHAR(party_code)) pcode, TRIM(TO_CHAR(account_code)) acc, ROUND(SUM(NVL(credit,0)-NVL(debit,0)),2) bal\n        FROM gl_voucher_dtl\n        WHERE UPPER(NVL(party_type,''))='SUPPLIER' AND party_code IS NOT NULL\n        GROUP BY TRIM(TO_CHAR(party_code)), TRIM(TO_CHAR(account_code))\n        ")
    party_rows = cur.fetchall()
    party_by_supplier = {}
    for pcode, acc, bal in party_rows:
        p = norm(pcode)
        a = norm(acc)
        party_by_supplier.setdefault(p, {})[a] = float(bal or 0)
    cur.execute("SELECT TRIM(TO_CHAR(code)), UPPER(NVL(type,'')) FROM chart_of_accounts")
    coa_type = {norm(code): typ or '' for code, typ in cur.fetchall()}
    out = []
    for loc, scode, sname, pac in sup_rows:
        sc = norm(scode)
        pa = norm(pac)
        bal = 0.0
        src = 'CONTROL_FALLBACK'
        if sc in party_by_supplier:
            liability = [b for acc, b in party_by_supplier[sc].items() if coa_type.get(norm(acc)) == 'LIABILITY']
            if liability:
                bal = round(sum(liability), 2)
                src = 'PARTY_LIABILITY'
            elif pa in party_by_supplier[sc]:
                bal = round(party_by_supplier[sc][pa], 2)
                src = 'PARTY_MAPPED_ACC'
            else:
                bal = round(sum(party_by_supplier[sc].values()), 2)
                src = 'PARTY_TOTAL'
        else:
            bal = round(acc_bal.get(pa, 0.0), 2)
            src = 'CONTROL_FALLBACK'
        out.append((str(loc or ''), sc, str(sname or ''), pa, bal, src))
    cur.close()
    conn.close()
    return (tid, out)

def main():
    tenants = get_active_tenants()
    target, total_sup, match_sup = pick_target_tenant(tenants)
    if not target:
        print('No matching tenant found for supplier codes 10001..10003.')
        return
    tid, rows = run_diagnostic(target)
    print(f'Target tenant: {tid} | suppliers: {total_sup} | matched 10001..10003: {match_sup}')
    repeated = [r for r in rows if abs(r[4] - -2570.85) < 0.001]
    fallback = [r for r in repeated if r[5] == 'CONTROL_FALLBACK']
    print(f'Rows with balance -2570.85: {len(repeated)}')
    print(f'Rows with balance -2570.85 using CONTROL_FALLBACK: {len(fallback)}')
    ctr = Counter([r[3] for r in fallback])
    print('Top fallback payable accounts:')
    for acc, cnt in ctr.most_common(5):
        print(f'  {acc}: {cnt}')
    print('Sample suppliers with -2570.85:')
    for r in repeated[:15]:
        print(f'  loc={r[0]} code={r[1]} name={r[2][:35]} payable={r[3]} bal={r[4]} src={r[5]}')
    want = {str(x) for x in range(10001, 10012)}
    subset = [r for r in rows if r[1] in want]
    print('Range 10001..10011:')
    for r in sorted(subset, key=lambda x: int(x[1])):
        print(f'  loc={r[0]} code={r[1]} name={r[2][:35]} payable={r[3]} bal={r[4]} src={r[5]}')
if __name__ == '__main__':
    main()
