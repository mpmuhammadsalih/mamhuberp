"""Diagnostic: Item Master vs Item Journal for one item code."""
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

from collections import defaultdict, deque
from typing import Any, Dict, List, Tuple

from db import (  # noqa: E402
    _detect_column,
    _detect_table,
    _fetch_rows,
    _get_connection,
    _is_itemjournal_reversal_transtype,
    _journal_cols_upper,
    _journal_row_fingerprint,
    _journal_rows_for_document,
    ensure_itemjournal_surrogate_pk,
    itemjournal_warehouse_code_column,
)


def main() -> None:
    item = int(sys.argv[1] if len(sys.argv) > 1 else 0)
    if item <= 0:
        print("Usage: python scripts/_diag_item_stock_gap.py <itemcode>")
        return

    ij = _detect_table(["ITEMJOURNAL", "itemjournal", "ITEMJOURNEL", "itemjournel"])
    im = _detect_table(["ITEMMASTER", "itemmaster"])
    ic = _detect_column(ij, ["ITEMCODE", "ITEM_CODE"])
    qty = _detect_column(ij, ["QTY", "QUANTITY"])
    loc = _detect_column(ij, ["LOCATIONCODE", "LOCATION_CODE"])
    tt = _detect_column(ij, ["TRANSTYPE", "TRANS_TYPE"])
    sd = _detect_column(ij, ["SOURCE_DOC", "SOURCEDOC"])
    sn = _detect_column(ij, ["SOURCE_NO", "SOURCENO"])
    created = _detect_column(ij, ["CREATEDDATE", "CREATED_DATE"])
    wh = itemjournal_warehouse_code_column(ij)

    im_code = _detect_column(im, ["ITEMCODE", "ITEM_CODE"])
    im_stock = _detect_column(im, ["CURRENTSTOCK", "CURRENT_STOCK", "STOCK"])
    im_loc = _detect_column(im, ["LOCATIONCODE", "LOCATION_CODE"])
    im_name = _detect_column(im, ["ITEMNAME", "ITEM_NAME"])

    _, im_rows = _fetch_rows(
        f"""
        SELECT {im_loc} AS loc, {im_code} AS itemcode, {im_name} AS itemname,
               NVL({im_stock},0) AS currentstock
        FROM {im}
        WHERE TO_CHAR({im_code}) = :c
        ORDER BY {im_loc}
        """,
        {"c": str(item)},
    )
    print("ITEMMASTER", im_rows)

    _, nets = _fetch_rows(
        f"""
        SELECT {loc} AS loc, NVL(SUM({qty}),0) AS net_qty, COUNT(*) AS lines
        FROM {ij}
        WHERE TO_CHAR({ic}) = :c
        GROUP BY {loc}
        ORDER BY {loc}
        """,
        {"c": str(item)},
    )
    print("JOURNAL_NET", nets)

    _, by_type = _fetch_rows(
        f"""
        SELECT {loc} AS loc,
               NVL({tt},'(none)') AS transtype,
               NVL({sd},'(none)') AS source_doc,
               NVL(SUM({qty}),0) AS net_qty,
               COUNT(*) AS lines
        FROM {ij}
        WHERE TO_CHAR({ic}) = :c
        GROUP BY {loc}, NVL({tt},'(none)'), NVL({sd},'(none)')
        ORDER BY 1,2,3
        """,
        {"c": str(item)},
    )
    print("BY_TYPE")
    for r in by_type or []:
        print(" ", r)

    _, by_src = _fetch_rows(
        f"""
        SELECT NVL({sd},'') AS source_doc,
               NVL(TO_CHAR({sn}),'') AS source_no,
               NVL({tt},'') AS transtype,
               COUNT(*) AS lines,
               NVL(SUM({qty}),0) AS net_qty
        FROM {ij}
        WHERE TO_CHAR({ic}) = :c
        GROUP BY NVL({sd},''), NVL(TO_CHAR({sn}),''), NVL({tt},'')
        ORDER BY 1,2,3
        """,
        {"c": str(item)},
    )
    print("BY_SOURCE")
    for r in by_src or []:
        print(" ", r)

    wh_sel = f", {wh} AS wh" if wh else ""
    _, recent = _fetch_rows(
        f"""
        SELECT * FROM (
          SELECT TO_CHAR({created}, 'YYYY-MM-DD HH24:MI:SS') AS createddate,
                 {loc} AS loc,
                 NVL({tt},'') AS transtype,
                 NVL({sd},'') AS source_doc,
                 NVL(TO_CHAR({sn}),'') AS source_no,
                 NVL({qty},0) AS qty
                 {wh_sel}
          FROM {ij}
          WHERE TO_CHAR({ic}) = :c
          ORDER BY {created} DESC NULLS LAST
        ) WHERE ROWNUM <= 30
        """,
        {"c": str(item)},
    )
    print("RECENT")
    for r in recent or []:
        print(" ", r)

    # Extra REVERSAL estimate (same logic as repair script, item-scoped)
    extra_qty = 0.0
    extra_n = 0
    with _get_connection() as conn:
        ensure_itemjournal_surrogate_pk(conn)
        with conn.cursor() as cur:
            jcols = _journal_cols_upper(cur, ij)
            cur.execute(
                f"""
                SELECT DISTINCT NVL(TO_CHAR({sn}),'') AS source_no, NVL({sd},'') AS source_doc
                FROM {ij}
                WHERE TO_CHAR({ic}) = :c AND UPPER(NVL({tt},'')) = 'REVERSAL'
                """,
                {"c": str(item)},
            )
            docs = [(str(r[0] or ""), str(r[1] or "")) for r in cur.fetchall() or []]
            for source_no, source_doc in docs:
                if not source_doc:
                    continue
                rows = _journal_rows_for_document(
                    cur, ij, jcols, 1, 1, source_doc, source_no, open_only=False
                )
                # Re-fetch all including REVERSAL for match — open_only=False returns only non-rev.
                # Use fingerprint match on full set manually.
                cur.execute(
                    f"""
                    SELECT * FROM (
                      SELECT {', '.join(sorted(jcols))}
                      FROM {ij}
                      WHERE LOCATIONCODE = 1 AND RESETNO = 1
                        AND SOURCE_DOC = :sd
                        AND NVL(TO_CHAR(SOURCE_NO),'@') = NVL(:sn,'@')
                      ORDER BY CREATEDDATE ASC NULLS LAST, ITEMJOURNAL_ID ASC
                    )
                    """,
                    {"sd": source_doc[:30], "sn": source_no[:50]},
                )
                if not cur.description:
                    continue
                names = [str(d[0] or "").upper() for d in cur.description]
                all_rows = [{names[i]: raw[i] for i in range(len(names))} for raw in (cur.fetchall() or [])]
                unused_rev: Dict[Tuple[Any, ...], deque] = defaultdict(deque)
                for row in all_rows:
                    if _is_itemjournal_reversal_transtype(row.get("TRANSTYPE")):
                        unused_rev[_journal_row_fingerprint(row, negate_qty=True)].append(row)
                for row in all_rows:
                    if _is_itemjournal_reversal_transtype(row.get("TRANSTYPE")):
                        continue
                    fp = _journal_row_fingerprint(row, negate_qty=False)
                    bucket = unused_rev.get(fp)
                    if bucket:
                        bucket.popleft()
                        if not bucket:
                            unused_rev.pop(fp, None)
                for bucket in unused_rev.values():
                    for er in bucket:
                        try:
                            if int(er.get("ITEMCODE") or 0) != item:
                                continue
                            q = float(er.get("QTY") or 0)
                        except (TypeError, ValueError):
                            continue
                        extra_n += 1
                        extra_qty += q
                        print(
                            " EXTRA_REVERSAL",
                            source_doc,
                            source_no,
                            "id=",
                            er.get("ITEMJOURNAL_ID"),
                            "qty=",
                            q,
                            "at",
                            er.get("CREATEDDATE"),
                        )

    im_qty = float((im_rows or [{}])[0].get("currentstock") or 0) if im_rows else 0.0
    j_qty = float((nets or [{}])[0].get("net_qty") or 0) if nets else 0.0
    print("SUMMARY")
    print(
        {
            "item": item,
            "name": (im_rows or [{}])[0].get("itemname") if im_rows else None,
            "itemmaster": im_qty,
            "journal_net": j_qty,
            "gap_journal_minus_master": round(j_qty - im_qty, 4),
            "extra_reversal_rows": extra_n,
            "extra_reversal_qty": extra_qty,
            "journal_after_removing_extras": round(j_qty - extra_qty, 4),
        }
    )


if __name__ == "__main__":
    main()
