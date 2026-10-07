from config.bootstrap_env import bootstrap_dotenv
bootstrap_dotenv()
from db import _get_connection

conn = _get_connection()
cur = conn.cursor()
cur.execute(
    """
    SELECT * FROM (
      SELECT VOUCHER_NO, VOUCHER_DATE, REFERENCE_NO, NARRATION, SOURCE, CREATED_BY
      FROM GL_VOUCHER_HDR
      WHERE SOURCE = 'GRN_COGS_ADJ'
         OR VOUCHER_NO LIKE 'GRN-CA-%'
         OR UPPER(NARRATION) LIKE '%CATCH-UP%'
      ORDER BY VOUCHER_NO DESC
    ) WHERE ROWNUM <= 20
    """
)
cols = [d[0].lower() for d in cur.description]
rows = [dict(zip(cols, r)) for r in cur.fetchall()]
print("HDR", rows)
for h in rows[:5]:
    cur.execute(
        """
        SELECT LINE_NO, ACCOUNT_CODE, DEBIT, CREDIT, REMARKS
        FROM GL_VOUCHER_DTL WHERE VOUCHER_NO = :v ORDER BY LINE_NO
        """,
        {"v": h["voucher_no"]},
    )
    print(h["voucher_no"], cur.fetchall())

# Also recent COGS debits
cur.execute(
    """
    SELECT * FROM (
      SELECT h.VOUCHER_NO, h.SOURCE, h.NARRATION, d.ACCOUNT_CODE, d.DEBIT, d.CREDIT, d.REMARKS
      FROM GL_VOUCHER_DTL d
      JOIN GL_VOUCHER_HDR h ON h.VOUCHER_NO = d.VOUCHER_NO
      WHERE d.ACCOUNT_CODE = '5100' AND d.DEBIT > 0
      ORDER BY h.VOUCHER_NO DESC
    ) WHERE ROWNUM <= 25
    """
)
cols = [d[0].lower() for d in cur.description]
print("RECENT COGS DR")
for r in cur.fetchall():
    print(dict(zip(cols, r)))
