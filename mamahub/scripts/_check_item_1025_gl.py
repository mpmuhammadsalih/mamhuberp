"""Check GL / accounts posted for item 1025 sales SI-000001 / SI-000003."""
from __future__ import annotations

from config.bootstrap_env import bootstrap_dotenv

bootstrap_dotenv()
from db import _get_connection  # noqa: E402


def main() -> None:
    conn = _get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT TABLE_NAME FROM USER_TABLES
        WHERE UPPER(TABLE_NAME) LIKE '%VOUCH%'
           OR UPPER(TABLE_NAME) LIKE 'GL%'
           OR UPPER(TABLE_NAME) LIKE '%JOURNAL%'
        ORDER BY 1
        """
    )
    tabs = [r[0] for r in cur.fetchall()]
    print("tables", tabs)

    for bill in ("SI-000003", "SI-000001", "SI-1-000003"):
        print("\n=== search", bill, "===")
        for t in tabs:
            cur.execute(
                "SELECT COLUMN_NAME FROM USER_TAB_COLUMNS WHERE TABLE_NAME=:t",
                {"t": t},
            )
            cols = [r[0].upper() for r in cur.fetchall()]
            cand = [
                c
                for c in cols
                if any(
                    x in c
                    for x in (
                        "VOUCH",
                        "REF",
                        "NARR",
                        "SOURCE",
                        "DOC",
                        "BILL",
                        "DESC",
                        "PARTIC",
                    )
                )
            ]
            for c in cand[:8]:
                try:
                    cur.execute(
                        f"""
                        SELECT * FROM (
                          SELECT * FROM {t}
                          WHERE UPPER(TO_CHAR({c})) LIKE :p
                        ) WHERE ROWNUM <= 5
                        """,
                        {"p": f"%{bill.upper()}%"},
                    )
                    rows = cur.fetchall()
                    if rows:
                        print("HIT", t, "via", c, "ncols", len(cols))
                        print("cols", cols)
                        for row in rows:
                            print(dict(zip(cols, row)))
                        break
                except Exception:
                    continue

    # Also show what COGS would be with current _line_costing_totals rule
    print("\n=== Costing check from BILLDTL ===")
    cur.execute(
        """
        SELECT BILLNO, QUANTITY, BASEQTY, RATE, AMOUNT, AVERAGECOST
        FROM BILLDTL WHERE ITEMCODE = 1025 ORDER BY BILLNO
        """
    )
    for r in cur.fetchall():
        billno, qty, base, rate, amt, avg = r
        qty = float(qty or 0)
        base = float(base or 0)
        avg = float(avg or 0)
        master_avg = 1.7
        print(
            {
                "bill": billno,
                "qty": qty,
                "baseqty": base,
                "sales_amount": float(amt or 0),
                "line_averagecost": avg,
                "cogs_if_base_x_line_avg": round(abs(base) * avg, 2),
                "cogs_correct_base_x_master_avg": round(abs(base) * master_avg, 2),
                "cogs_if_qty_x_alt_cost34": round(abs(qty) * 34.0, 2),
                "BUG": abs(base) * avg > abs(base) * master_avg * 1.5,
            }
        )


if __name__ == "__main__":
    main()
