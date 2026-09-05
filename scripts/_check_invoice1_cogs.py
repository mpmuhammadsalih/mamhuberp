"""Inspect COGS for sales invoice billno 1."""
from __future__ import annotations

from config.bootstrap_env import bootstrap_dotenv

bootstrap_dotenv()
from db import _base_unit_inventory_cost_from_maps, _get_connection, get_item_by_code  # noqa: E402


def main() -> None:
    conn = _get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT * FROM (
          SELECT BILLNO, BILLDATE, LOCATIONCODE, NETBILLAMOUNT, CUSTOMERCODE, RETURNFLAG
          FROM BILLHDR
          WHERE TRIM(TO_CHAR(BILLNO)) IN ('1', '000001', 'SI-000001', 'SI-1-000001')
             OR TRIM(TO_CHAR(BILLNO)) LIKE '%000001'
          ORDER BY BILLDATE DESC NULLS LAST
        ) WHERE ROWNUM <= 15
        """
    )
    cols = [d[0].lower() for d in cur.description]
    hdrs = [dict(zip(cols, r)) for r in cur.fetchall()]
    print("HEADERS", hdrs)

    if not hdrs:
        cur.execute(
            """
            SELECT * FROM (
              SELECT BILLNO, BILLDATE, LOCATIONCODE, NETBILLAMOUNT, CUSTOMERCODE, RETURNFLAG
              FROM BILLHDR
              ORDER BY CREATEDDATE DESC NULLS LAST, BILLDATE DESC
            ) WHERE ROWNUM <= 8
            """
        )
        cols = [d[0].lower() for d in cur.description]
        hdrs = [dict(zip(cols, r)) for r in cur.fetchall()]
        print("LATEST HEADERS", hdrs)

    for h in hdrs[:3]:
        bn = h["billno"]
        loc = int(h.get("locationcode") or 1)
        print(f"\n==== BILL {bn!r} loc={loc} net={h.get('netbillamount')} return={h.get('returnflag')} ====")
        cur.execute(
            """
            SELECT SLNO, ITEMCODE, QUANTITY, BASEQTY, UNITOFMEASUREMENT AS UOM,
                   RATE, AMOUNT, COST, AVERAGECOST, LANDINGCOST
            FROM BILLDTL
            WHERE BILLNO = :bn AND LOCATIONCODE = :lc
            ORDER BY SLNO
            """,
            {"bn": bn, "lc": loc},
        )
        dcols = [d[0].lower() for d in cur.description]
        lines = [dict(zip(dcols, r)) for r in cur.fetchall()]
        if not lines:
            cur.execute(
                """
                SELECT SLNO, ITEMCODE, QUANTITY, BASEQTY, UNITOFMEASUREMENT AS UOM,
                       RATE, AMOUNT, COST, AVERAGECOST, LANDINGCOST
                FROM BILLDTL
                WHERE BILLNO = :bn
                ORDER BY SLNO
                """,
                {"bn": bn},
            )
            dcols = [d[0].lower() for d in cur.description]
            lines = [dict(zip(dcols, r)) for r in cur.fetchall()]

        total = 0.0
        for ln in lines:
            ic = int(float(ln.get("itemcode") or 0))
            qty = float(ln.get("quantity") or 0)
            base = float(ln.get("baseqty") or qty or 0)
            stored_avg = float(ln.get("averagecost") or 0)
            cost = float(ln.get("cost") or 0)
            item = get_item_by_code(ic, loc) or {}
            master_avg = float(item.get("averagecost") or 0)
            master_cost = float(item.get("costprice") or item.get("COSTPRICE") or 0)
            unit = _base_unit_inventory_cost_from_maps(
                {
                    "item_code": ic,
                    "quantity": qty,
                    "base_qty": base,
                    "averagecost": stored_avg,
                    "costprice": cost,
                    "cost": cost,
                },
                item,
            )
            cogs = round(abs(base) * unit, 2)
            total += cogs
            print(
                f"  SL{ln.get('slno')} item={ic} uom={ln.get('uom')} "
                f"qty={qty} base={base} rate={ln.get('rate')} amt={ln.get('amount')}"
            )
            print(
                f"    stored COST={cost} AVERAGECOST={stored_avg} | "
                f"master AVG={master_avg} COST={master_cost} baseuom={item.get('baseuom') or item.get('BASEUOM')}"
            )
            print(f"    unit_cost_used={unit}  COGS=base*unit={cogs}")
            if stored_avg > 0:
                print(f"    stored_avg*base={round(abs(base) * stored_avg, 2)}  stored_avg*qty={round(abs(qty) * stored_avg, 2)}")

        print("TOTAL_COGS_RECALC", round(total, 2))

        # GL for this bill
        patterns = [
            f"%{bn}%",
            f"% {bn} %",
            f"%INVOICE {bn}%",
            f"%Sales Invoice {bn}%",
        ]
        seen = set()
        for p in patterns:
            cur.execute(
                """
                SELECT VOUCHER_NO, VOUCHER_DATE, REFERENCE_NO, NARRATION, SOURCE
                FROM GL_VOUCHER_HDR
                WHERE UPPER(NVL(REFERENCE_NO,' ')) LIKE UPPER(:p)
                   OR UPPER(NVL(NARRATION,' ')) LIKE UPPER(:p)
                """,
                {"p": p},
            )
            gcols = [d[0].lower() for d in cur.description]
            for g in [dict(zip(gcols, r)) for r in cur.fetchall()]:
                vno = g["voucher_no"]
                if vno in seen:
                    continue
                seen.add(vno)
                print("GL_HDR", g)
                cur.execute(
                    """
                    SELECT LINE_NO, ACCOUNT_CODE, DEBIT, CREDIT, REMARKS
                    FROM GL_VOUCHER_DTL
                    WHERE VOUCHER_NO = :v
                    ORDER BY LINE_NO
                    """,
                    {"v": vno},
                )
                for row in cur.fetchall():
                    print("  GL_DTL", row)

        # ITEMJOURNAL
        for jt in ("ITEMJOURNAL", "ITEMJOURNEL"):
            try:
                cur.execute(
                    f"""
                    SELECT * FROM (
                      SELECT RECEIPTNO, LINENO, ITEMCODE, QUANTITY, RATE, AVERAGECOST,
                             SOURCE_DOC, SOURCE_NO
                      FROM {jt}
                      WHERE TRIM(TO_CHAR(SOURCE_NO)) = TRIM(TO_CHAR(:bn))
                      ORDER BY LINENO
                    ) WHERE ROWNUM <= 30
                    """,
                    {"bn": bn},
                )
                jcols = [d[0].lower() for d in cur.description]
                rows = [dict(zip(jcols, r)) for r in cur.fetchall()]
                if rows:
                    print(jt, rows)
            except Exception as ex:
                print(jt, "err", ex)


if __name__ == "__main__":
    main()
