"""
Dry-run / apply: delete duplicate ITEMJOURNAL REVERSAL rows caused by re-edit
re-reversing already-reversed stock adjustment lines.

Usage:
  python scripts/_repair_stkadj_duplicate_reversals.py           # dry-run
  python scripts/_repair_stkadj_duplicate_reversals.py --apply   # delete extras
  python scripts/_repair_stkadj_duplicate_reversals.py --item 1633 --apply
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
    _detect_column,
    _detect_table,
    _get_connection,
    _is_itemjournal_reversal_transtype,
    _journal_row_fingerprint,
)


def _fetch_doc_rows(cur, tbl: str, loc: int, source_no: str, item_code: Optional[int]) -> List[Dict[str, Any]]:
    cols = [
        "ITEMJOURNAL_ID", "LINENO", "ITEMCODE", "QTY", "UOM", "TRANSTYPE",
        "SOURCE_DOC", "SOURCE_NO", "CREATEDDATE", "WAREHOUSE_CODE", "WAREHOUSE_ID",
    ]
    # Keep only existing columns
    cur.execute(
        """
        SELECT column_name FROM user_tab_columns
        WHERE table_name = :t
        """,
        {"t": tbl.upper()},
    )
    existing = {str(r[0] or "").upper() for r in cur.fetchall() or []}
    use = [c for c in cols if c in existing]
    if "INVENTORYLOCATION" in existing and "WAREHOUSE_CODE" not in existing:
        use.append("INVENTORYLOCATION")
    where = ["LOCATIONCODE = :loc", "UPPER(NVL(SOURCE_DOC,'')) = 'STKADJ'", "NVL(TO_CHAR(SOURCE_NO),'') = :sn"]
    params: Dict[str, Any] = {"loc": loc, "sn": str(source_no)}
    if item_code is not None and "ITEMCODE" in existing:
        where.append("ITEMCODE = :ic")
        params["ic"] = int(item_code)
    order = []
    if "CREATEDDATE" in existing:
        order.append("CREATEDDATE ASC NULLS LAST")
    if "ITEMJOURNAL_ID" in existing:
        order.append("ITEMJOURNAL_ID ASC")
    sql = f"SELECT {', '.join(use)} FROM {tbl} WHERE {' AND '.join(where)}"
    if order:
        sql += " ORDER BY " + ", ".join(order)
    cur.execute(sql, params)
    names = [str(d[0] or "").upper() for d in cur.description]
    return [{names[i]: row[i] for i in range(len(names))} for row in (cur.fetchall() or [])]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Delete duplicate REVERSAL rows")
    ap.add_argument("--item", type=int, default=None, help="Limit to one item code")
    ap.add_argument("--loc", type=int, default=1)
    args = ap.parse_args()

    tbl = _detect_table(["ITEMJOURNAL", "itemjournal", "ITEMJOURNEL", "itemjournel"])
    if not tbl:
        print("No ITEMJOURNAL table")
        return
    id_col = _detect_column(tbl, ["ITEMJOURNAL_ID"])
    if not id_col:
        print("ITEMJOURNAL_ID required for safe delete")
        return

    delete_ids: List[int] = []
    impact_by_item: Dict[int, float] = defaultdict(float)

    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT DISTINCT NVL(TO_CHAR(SOURCE_NO),'') AS source_no
                FROM {tbl}
                WHERE LOCATIONCODE = :loc
                  AND UPPER(NVL(SOURCE_DOC,'')) = 'STKADJ'
                  AND UPPER(NVL(TRANSTYPE,'')) = 'REVERSAL'
                """,
                {"loc": args.loc},
            )
            source_nos = [str(r[0] or "") for r in cur.fetchall() or [] if str(r[0] or "").strip()]
            for sn in sorted(source_nos, key=lambda x: (len(x), x)):
                rows = _fetch_doc_rows(cur, tbl, args.loc, sn, args.item)
                if not rows:
                    continue
                unused_rev: Dict[Tuple[Any, ...], deque] = defaultdict(deque)
                for row in rows:
                    if _is_itemjournal_reversal_transtype(row.get("TRANSTYPE")):
                        unused_rev[_journal_row_fingerprint(row, negate_qty=True)].append(row)
                for row in rows:
                    if _is_itemjournal_reversal_transtype(row.get("TRANSTYPE")):
                        continue
                    fp = _journal_row_fingerprint(row, negate_qty=False)
                    bucket = unused_rev.get(fp)
                    if bucket:
                        bucket.popleft()
                        if not bucket:
                            unused_rev.pop(fp, None)
                # Remaining REVERSAL rows in unused_rev are duplicates (never matched to a non-rev)
                # Wait - unused_rev keys are fingerprints of NON-REV (negate_qty=True on rev).
                # Values are REVERSAL rows that weren't consumed... actually we consume when matching non-rev.
                # Leftover in unused_rev = REVERSAL that had no matching non-rev? 
                # No: we put ALL rev into unused_rev first, then consume when walking non-rev.
                # Leftover = extra REVERSAL beyond non-rev count for that fingerprint.
                extras = []
                for bucket in unused_rev.values():
                    extras.extend(list(bucket))
                # Also: REVERSAL that matched are removed. Correct.
                # But wait - if we have MORE non-rev than rev, leftovers empty and open non-rev remain - good.
                # If MORE rev than non-rev, leftovers are extra rev - DELETE those.
                for er in extras:
                    try:
                        jid = int(er.get("ITEMJOURNAL_ID") or 0)
                    except (TypeError, ValueError):
                        continue
                    if jid <= 0:
                        continue
                    delete_ids.append(jid)
                    try:
                        ic = int(er.get("ITEMCODE") or 0)
                        q = float(er.get("QTY") or 0)
                    except (TypeError, ValueError):
                        continue
                    impact_by_item[ic] += q
                    print(
                        f"EXTRA_REVERSAL id={jid} STKADJ#{sn} item={ic} qty={q} "
                        f"created={er.get('CREATEDDATE')}"
                    )

            print("---")
            print(f"Extra REVERSAL rows: {len(delete_ids)}")
            print("Qty impact by item (journal net change if deleted = -these qtys):")
            for ic, q in sorted(impact_by_item.items()):
                print(f"  item {ic}: remove REVERSAL sum {q} => journal net delta {-q}")

            if not args.apply:
                print("Dry-run only. Re-run with --apply to delete.")
                return

            if not delete_ids:
                print("Nothing to delete.")
                return
            # Delete in chunks
            n = 0
            for i in range(0, len(delete_ids), 50):
                chunk = delete_ids[i : i + 50]
                binds = {f"id{j}": chunk[j] for j in range(len(chunk))}
                in_list = ", ".join(f":id{j}" for j in range(len(chunk)))
                cur.execute(
                    f"DELETE FROM {tbl} WHERE {id_col} IN ({in_list})",
                    binds,
                )
                n += int(cur.rowcount or 0)
            conn.commit()
            print(f"Deleted {n} duplicate REVERSAL rows.")


if __name__ == "__main__":
    main()
