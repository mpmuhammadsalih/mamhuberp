from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from db import _get_connection


def main() -> None:
    with _get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM ITEMMASTER")
        print("itemmaster total", cur.fetchone()[0])
        cur.execute(
            "SELECT LOCATIONCODE, COUNT(*) FROM ITEMMASTER GROUP BY LOCATIONCODE ORDER BY 1"
        )
        print("by loc", cur.fetchall())
        cur.execute(
            """
            SELECT column_name FROM user_tab_columns
            WHERE table_name='ITEMMASTER'
              AND (column_name LIKE '%SUPP%' OR column_name LIKE '%VENDOR%')
            """
        )
        print("supp cols", [r[0] for r in cur.fetchall()])
        cur.execute(
            "SELECT ITEMCODE, ITEMNAME, LOCATIONCODE FROM ITEMMASTER WHERE ROWNUM <= 5 ORDER BY ITEMCODE"
        )
        print("sample", cur.fetchall())
        # supplier 10001 filter if column exists
        cols = {r[0] for r in cur.execute(
            "SELECT column_name FROM user_tab_columns WHERE table_name='ITEMMASTER'"
        ).fetchall()}
        if "SUPPLIERCODE" in cols:
            cur.execute(
                "SELECT COUNT(*) FROM ITEMMASTER WHERE NVL(SUPPLIERCODE,0)=10001"
            )
            print("items for supplier 10001", cur.fetchone()[0])
            cur.execute(
                "SELECT COUNT(*) FROM ITEMMASTER WHERE NVL(SUPPLIERCODE,0)=0 OR SUPPLIERCODE IS NULL"
            )
            print("items with no/zero supplier", cur.fetchone()[0])


if __name__ == "__main__":
    main()
