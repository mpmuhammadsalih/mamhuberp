"""
Restore missing open ITEMJOURNAL effect for STKADJ#15 when DTL has a current
line but every STOCK_ADJ is cancelled by a REVERSAL (one reverse too many).

Deletes the newest matching REVERSAL row(s) until open journal qty matches
STKADJDTL.BASEQTY for the item. Does not change ITEMMASTER.

Usage:
  python scripts/_restore_stkadj15_open_journal.py
  python scripts/_restore_stkadj15_open_journal.py --apply
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

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
    _get_connection,
    _is_itemjournal_reversal_transtype,
    _journal_cols_upper,
    _journal_row_fingerprint,
    _journal_rows_for_document,
    ensure_itemjournal_surrogate_pk,
)

ITEMS = (1633, 3092)
ADJ_NO = "15"
LOC = 1
RESET = 1


def _open_qty(cur, jcols: set, item: int) -> float:
    opens = _journal_rows_for_document(
        cur, "ITEMJOURNAL", jcols, LOC, RESET, "STKADJ", ADJ_NO, open_only=True
    )
    total = 0.0
    for r in opens:
        try:
            if int(float(r.get("ITEMCODE") or 0)) != item:
                continue
            total += float(r.get("QTY") or 0)
        except (TypeError, ValueError):
            continue
    return round(total, 3)


def _expected_from_dtl(cur, item: int) -> Optional[float]:
    cur.execute(
        """
        SELECT NVL(BASEQTY, ADJUSTQTY) AS bq
        FROM STKADJDTL
        WHERE LOCATIONCODE = :loc AND ADJNO = :a AND ITEMCODE = :ic
        ORDER BY SLNO
        """,
        {"loc": LOC, "a": int(ADJ_NO), "ic": item},
    )
    rows = cur.fetchall() or []
    if not rows:
        return None
    return round(sum(float(r[0] or 0) for r in rows), 3)


def _newest_reversal_id(
    cur,
    item: int,
    needed_open_delta: float,
    *,
    exclude_ids: Optional[set] = None,
) -> Optional[int]:
    """
    Find newest REVERSAL whose removal would move open qty toward needed_open_delta.
    Removing REVERSAL qty R changes open by -R.
    """
    exclude_ids = exclude_ids or set()
    cur.execute(
        """
        SELECT ITEMJOURNAL_ID, QTY
        FROM ITEMJOURNAL
        WHERE LOCATIONCODE = :loc
          AND RESETNO = :rn
          AND SOURCE_DOC = 'STKADJ'
          AND NVL(TO_CHAR(SOURCE_NO),'') = :sn
          AND ITEMCODE = :ic
          AND UPPER(NVL(TRANSTYPE,'')) = 'REVERSAL'
        ORDER BY CREATEDDATE DESC NULLS LAST, ITEMJOURNAL_ID DESC
        """,
        {"loc": LOC, "rn": RESET, "sn": ADJ_NO, "ic": item},
    )
    target_rev_qty = round(-needed_open_delta, 3)
    rows = cur.fetchall() or []
    for row in rows:
        jid, qty = int(row[0]), float(row[1] or 0)
        if jid in exclude_ids:
            continue
        if abs(round(qty, 3) - target_rev_qty) < 0.0005:
            return jid
    for row in rows:
        jid = int(row[0])
        if jid not in exclude_ids:
            return jid
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    delete_ids: List[int] = []
    with _get_connection() as conn:
        ensure_itemjournal_surrogate_pk(conn)
        with conn.cursor() as cur:
            jcols = _journal_cols_upper(cur, "ITEMJOURNAL")
            for item in ITEMS:
                expected = _expected_from_dtl(cur, item)
                open_q = _open_qty(cur, jcols, item)
                print(f"ITEM {item}: DTL expected open={expected}, journal open={open_q}")
                if expected is None:
                    print("  no STKADJDTL line — skip")
                    continue
                # iteratively delete newest matching REVERSAL until open matches expected
                guard = 0
                planned: set = set()
                while abs(open_q - expected) > 0.0005 and guard < 20:
                    guard += 1
                    need_delta = round(expected - open_q, 3)
                    jid = _newest_reversal_id(cur, item, need_delta, exclude_ids=planned)
                    if not jid:
                        print("  no REVERSAL left to remove; stop")
                        break
                    cur.execute(
                        "SELECT QTY FROM ITEMJOURNAL WHERE ITEMJOURNAL_ID = :id",
                        {"id": jid},
                    )
                    rq = cur.fetchone()
                    rev_qty = float((rq or [0])[0] or 0)
                    print(
                        f"  remove REVERSAL id={jid} qty={rev_qty} "
                        f"(open {open_q} -> {round(open_q - rev_qty, 3)})"
                    )
                    delete_ids.append(jid)
                    planned.add(jid)
                    if args.apply:
                        cur.execute(
                            "DELETE FROM ITEMJOURNAL WHERE ITEMJOURNAL_ID = :id",
                            {"id": jid},
                        )
                        open_q = _open_qty(cur, jcols, item)
                    else:
                        open_q = round(open_q - rev_qty, 3)
                print(f"  final open={open_q} expected={expected}")

            if not args.apply:
                print("Dry-run only. Re-run with --apply to delete REVERSAL rows:", delete_ids)
                return
            conn.commit()
            print(f"Applied. Deleted {len(delete_ids)} REVERSAL row(s): {delete_ids}")

    # verify vs itemmaster
    with _get_connection() as conn:
        with conn.cursor() as cur:
            for item in ITEMS:
                cur.execute(
                    "SELECT NVL(CURRENTSTOCK,0) FROM ITEMMASTER WHERE ITEMCODE=:c AND LOCATIONCODE=1",
                    {"c": item},
                )
                master = float((cur.fetchone() or [0])[0] or 0)
                cur.execute(
                    "SELECT NVL(SUM(QTY),0) FROM ITEMJOURNAL WHERE ITEMCODE=:c AND LOCATIONCODE=1",
                    {"c": item},
                )
                journal = float((cur.fetchone() or [0])[0] or 0)
                print(
                    f"VERIFY {item}: master={master} journal={journal} gap={round(journal - master, 4)}"
                )


if __name__ == "__main__":
    main()
