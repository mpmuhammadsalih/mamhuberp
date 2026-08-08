from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from db import _get_connection, get_location_info_by_dbkey


def main() -> None:
    info = get_location_info_by_dbkey(None)
    print("base location info", info)
    with _get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT LOCATIONCODE, LOCATIONNAME, BASELOCATIONFLAG FROM LOCATIONMASTER ORDER BY LOCATIONCODE"
        )
        print("locations", cur.fetchall())

    # Run item query mimicking picker with loc 28 and loc 1
    from db import _fetch_rows

    for loc in (28, 1):
        q = (
            "SELECT ITEMCODE AS code, ITEMNAME AS name, NVL(BASEUOM,'NOS') AS uom, "
            "NVL(COSTPRICE,0) AS cost FROM ITEMMASTER WHERE LOCATIONCODE = :loc "
            "AND ROWNUM <= 5 ORDER BY ITEMCODE"
        )
        # ORDER BY with ROWNUM is tricky — simplify
        q = (
            "SELECT * FROM ("
            " SELECT ITEMCODE AS code, ITEMNAME AS name, NVL(BASEUOM,'NOS') AS uom, "
            " NVL(COSTPRICE,0) AS cost FROM ITEMMASTER WHERE LOCATIONCODE = :loc ORDER BY ITEMCODE"
            ") WHERE ROWNUM <= 5"
        )
        try:
            _, rows = _fetch_rows(q, {"loc": loc})
            print(f"items loc={loc}", len(rows), rows[:2])
        except Exception as e:
            print(f"items loc={loc} ERR", e)


if __name__ == "__main__":
    main()
