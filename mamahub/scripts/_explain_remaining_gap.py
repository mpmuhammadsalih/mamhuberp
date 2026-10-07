"""Explain remaining Item Master vs Item Journal gap after duplicate REVERSAL cleanup."""
from __future__ import annotations

import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
for line in (root / ".env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    os.environ.setdefault(k.strip(), v.strip().strip("'\""))
os.chdir(root)
sys.path.insert(0, str(root))

from db import (  # noqa: E402
    _fetch_rows,
    _get_connection,
    _journal_cols_upper,
    _journal_rows_for_document,
    ensure_itemjournal_surrogate_pk,
)


def analyze(item: int) -> None:
    print("=" * 60)
    print("ITEM", item)
    _, im = _fetch_rows(
        "SELECT CURRENTSTOCK, ITEMNAME FROM ITEMMASTER WHERE ITEMCODE=:c AND LOCATIONCODE=1",
        {"c": item},
    )
    master = float((im or [{}])[0].get("currentstock") or 0)
    print("MASTER", im)
    _, jnet = _fetch_rows(
        "SELECT NVL(SUM(QTY),0) AS net, COUNT(*) AS n FROM ITEMJOURNAL WHERE ITEMCODE=:c AND LOCATIONCODE=1",
        {"c": item},
    )
    journal = float((jnet or [{}])[0].get("net") or 0)
    print("JOURNAL_NET", jnet)
    print("GAP journal-master =", round(journal - master, 4))

    open_total = 0.0
    print("OPEN journal lines (current effective movements):")
    with _get_connection() as conn:
        ensure_itemjournal_surrogate_pk(conn)
        with conn.cursor() as cur:
            jcols = _journal_cols_upper(cur, "ITEMJOURNAL")
            cur.execute(
                """
                SELECT DISTINCT NVL(TO_CHAR(SOURCE_NO),''), NVL(SOURCE_DOC,'')
                FROM ITEMJOURNAL
                WHERE ITEMCODE=:c AND LOCATIONCODE=1
                """,
                {"c": item},
            )
            docs = sorted(
                [(str(a or ""), str(b or "")) for a, b in (cur.fetchall() or [])],
                key=lambda x: (x[1], x[0]),
            )
            for sn, sd in docs:
                if not sd:
                    continue
                opens = _journal_rows_for_document(
                    cur, "ITEMJOURNAL", jcols, 1, 1, sd, sn, open_only=True
                )
                opens = [r for r in opens if int(float(r.get("ITEMCODE") or 0)) == item]
                if not opens:
                    continue
                for r in opens:
                    q = float(r.get("QTY") or 0)
                    open_total += q
                    print(
                        f"  {sd}#{sn} {r.get('TRANSTYPE')} qty={q} "
                        f"wh={r.get('WAREHOUSE_CODE') or r.get('WAREHOUSE_ID')} "
                        f"created={r.get('CREATEDDATE')}"
                    )
    print("OPEN_TOTAL", open_total)

    _, dtl = _fetch_rows(
        """
        SELECT ADJNO, SLNO, ADJUSTQTY, BASEQTY, STORE, NEWQTY, CURRENTQTY
        FROM STKADJDTL
        WHERE LOCATIONCODE=1 AND ITEMCODE=:c
        ORDER BY ADJNO, SLNO
        """,
        {"c": item},
    )
    print("CURRENT STKADJDTL (what documents say now):")
    dtl_sum = 0.0
    for r in dtl or []:
        bq = float(r.get("baseqty") if r.get("baseqty") is not None else r.get("adjustqty") or 0)
        dtl_sum += bq
        print(" ", r)
    print("STKADJDTL baseqty sum", dtl_sum)

    _, sales = _fetch_rows(
        """
        SELECT SOURCE_NO, QTY, TO_CHAR(CREATEDDATE,'YYYY-MM-DD HH24:MI') AS dt
        FROM ITEMJOURNAL
        WHERE LOCATIONCODE=1 AND ITEMCODE=:c AND UPPER(SOURCE_DOC)='BILL'
        ORDER BY CREATEDDATE
        """,
        {"c": item},
    )
    sales_sum = sum(float(r.get("qty") or 0) for r in (sales or []))
    print("SALES_JOURNAL", sales, "sum", sales_sum)

    print("NOTE: Item Master was updated by stock DELTAS on each save.")
    print("Journal open lines are the surviving movements after reverse matching.")
    print("If they differ, stock deltas from re-edits of STKADJ#15 did not equal final open journal.")


if __name__ == "__main__":
    for item in (1633, 3092):
        analyze(item)
