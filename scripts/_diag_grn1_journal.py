import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()
from config.bootstrap_env import bootstrap_dotenv
bootstrap_dotenv()
from db.oracle_driver import oracle_connect

user = os.getenv('DB_USERNAME', 'hayya')
pwd = os.getenv('DB_PASSWORD', 'hayya')
dsn = (os.getenv('DB_DSN') or '192.168.1.150:1521/dynamics').strip().strip("'\"")
loc, rno = 1, 1
conn = oracle_connect(user=user, password=pwd, dsn=dsn)
cur = conn.cursor()

print('=== RECEIPTDTL item 1002 ===')
cur.execute(
    """SELECT LINENO, QUANTITY, RECEIVEDQTY, BASEQTY, RATE, AMOUNT, LANDINGCOST,
              PREVIOUSAVGCOST, PREVIOUSLANDINGCOST
       FROM RECEIPTDTL WHERE LOCATIONCODE=:l AND RECEIPTNO=:r AND ITEMCODE=1002 ORDER BY LINENO""",
    {'l': loc, 'r': rno},
)
lines = cur.fetchall()
bq_sum = 0
for r in lines:
    print(' ', r)
    bq_sum += float(r[2] or r[3] or 0)
print(' baseqty/received sum:', bq_sum)

print('\n=== ITEMJOURNAL GRN receipt 1 ===')
for tbl, doc_col in [('ITEMJOURNAL', 'SOURCE_DOC'), ('ITEMJOURNEL', None)]:
    try:
        cur.execute("SELECT COUNT(*) FROM user_tables WHERE table_name = :t", {'t': tbl.upper()})
        if not cur.fetchone()[0]:
            continue
        cur.execute(f"SELECT column_name FROM user_tab_columns WHERE table_name = :t", {'t': tbl.upper()})
        cols = {r[0].upper() for r in cur.fetchall()}
        if 'SOURCE_DOC' in cols:
            cur.execute(
                f"""SELECT RECEIPTNO, LINENO, ITEMCODE, QTY, RATE, AMOUNT, TRANSTYPE, SOURCE_DOC, SOURCE_NO
                    FROM {tbl} WHERE LOCATIONCODE=:l AND ITEMCODE=1002
                      AND (SOURCE_DOC='GRN' AND SOURCE_NO=:sn OR RECEIPTNO=:r)
                    ORDER BY RECEIPTNO, LINENO""",
                {'l': loc, 'sn': str(rno), 'r': rno},
            )
        else:
            cur.execute(
                f"""SELECT RECEIPTNO, LINENO, ITEMCODE, QTY, RATE, AMOUNT, TRANSTYPE
                    FROM {tbl} WHERE LOCATIONCODE=:l AND RECEIPTNO=:r AND ITEMCODE=1002 ORDER BY LINENO""",
                {'l': loc, 'r': rno},
            )
        rows = cur.fetchall()
        if rows:
            print(f' Table {tbl}:')
            jq = 0
            for r in rows:
                print('  ', r)
                jq += float(r[3] or 0)
            print('  qty sum:', jq)
    except Exception as ex:
        print(f' {tbl}:', ex)

print('\n=== ITEMMASTER 1002 ===')
cur.execute(
    'SELECT CURRENTSTOCK, AVERAGECOST, LANDINGCOST, COSTPRICE FROM ITEMMASTER WHERE LOCATIONCODE=:l AND ITEMCODE=1002',
    {'l': loc},
)
print(' ', cur.fetchone())

cur.close()
conn.close()
