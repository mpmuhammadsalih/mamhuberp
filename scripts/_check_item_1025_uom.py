"""Diagnose item 1025 alternate-UOM sales vs inventory posting value."""
from __future__ import annotations

from config.bootstrap_env import bootstrap_dotenv

bootstrap_dotenv()

from db import _get_connection  # noqa: E402


def main() -> None:
    conn = _get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT COLUMN_NAME FROM USER_TAB_COLUMNS
        WHERE TABLE_NAME = 'ITEMMASTER'
          AND UPPER(COLUMN_NAME) IN (
            'LOCATIONCODE','ITEMCODE','ITEMNAME','BASEUOM','CURRENTSTOCK',
            'AVERAGECOST','COSTPRICE','RETAIL','RETAILPRICE','MRP',
            'COGSACCOUNT','INVENTORYACCOUNT','COGS_ACCOUNT','INVENTORY_ACCOUNT'
          )
        ORDER BY COLUMN_NAME
        """
    )
    im_cols = {r[0].upper() for r in cur.fetchall()}
    print("ITEMMASTER cols found:", sorted(im_cols))

    select_bits = [
        "LOCATIONCODE",
        "ITEMCODE",
        "ITEMNAME",
        "BASEUOM",
        "CURRENTSTOCK",
        "AVERAGECOST",
        "COSTPRICE",
    ]
    for opt in ("RETAIL", "RETAILPRICE", "MRP", "COGSACCOUNT", "INVENTORYACCOUNT"):
        if opt in im_cols:
            select_bits.append(opt)
    cur.execute(
        f"SELECT {', '.join(select_bits)} FROM ITEMMASTER WHERE ITEMCODE = :c ORDER BY LOCATIONCODE",
        {"c": 1025},
    )
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    print("=== ITEMMASTER 1025 ===")
    for r in rows:
        print(r)
    if not rows:
        print("Item 1025 not found")
        return

    loc = int(rows[0]["LOCATIONCODE"])
    avg = float(rows[0].get("AVERAGECOST") or 0)
    cost = float(rows[0].get("COSTPRICE") or 0)
    base_uom = str(rows[0].get("BASEUOM") or "").strip()
    unit_cost = avg if avg > 0 else cost
    print(f"\nUsing LOCATIONCODE={loc} BASEUOM={base_uom} unit_cost(for COGS)={unit_cost}")

    cur.execute(
        """
        SELECT *
        FROM ITEMALTERNATEUOMMAP
        WHERE ITEMCODE = :c
          AND (LOCATIONCODE = :l OR LOCATIONCODE IS NULL)
        """,
        {"c": 1025, "l": loc},
    )
    acols = [d[0] for d in cur.description]
    alts = [dict(zip(acols, r)) for r in cur.fetchall()]
    print("\n=== ITEMALTERNATEUOMMAP ===")
    for a in alts:
        print(a)

    # Detect factor column
    factor_keys = [k for k in acols if "FACTOR" in k.upper() or "CONV" in k.upper()]
    print("factor cols:", factor_keys)

    print("\n=== Expected posting math (per 1 alt unit sold) ===")
    for a in alts:
        uom = str(
            a.get("ALTERNATEUOMCODE")
            or a.get("alternateuomcode")
            or a.get("ALTERNATE_UOM_CODE")
            or ""
        ).strip()
        factor = 1.0
        for fk in ("UOMFACTOR", "CONVERSIONFACTOR", "FACTOR", "CONVERSION_FACTOR"):
            if a.get(fk) is not None:
                try:
                    factor = float(a.get(fk) or 1)
                    break
                except Exception:
                    pass
        base_qty = round(1.0 * factor, 6)
        inv_value = round(base_qty * unit_cost, 2)
        print(
            f"  sell 1 {uom}: factor={factor} -> base_qty={base_qty} {base_uom} "
            f"-> inventory/COGS GL={inv_value} (base_qty x {unit_cost})"
        )

    # Recent bill lines — discover columns first
    cur.execute(
        """
        SELECT COLUMN_NAME FROM USER_TAB_COLUMNS
        WHERE TABLE_NAME = 'BILLDTL'
          AND UPPER(COLUMN_NAME) IN (
            'BILLNO','LOCATIONCODE','ITEMCODE','QUANTITY','BASEQTY','QTY',
            'UOM','UNIT','RATE','AMOUNT','AVERAGECOST','COSTPRICE','UNITCODE'
          )
        ORDER BY COLUMN_NAME
        """
    )
    dtl_cols = {r[0].upper() for r in cur.fetchall()}
    print("\nBILLDTL cols:", sorted(dtl_cols))
    qty_col = "QUANTITY" if "QUANTITY" in dtl_cols else ("QTY" if "QTY" in dtl_cols else None)
    base_col = "BASEQTY" if "BASEQTY" in dtl_cols else None
    uom_col = "UOM" if "UOM" in dtl_cols else ("UNIT" if "UNIT" in dtl_cols else ("UNITCODE" if "UNITCODE" in dtl_cols else None))
    select_dtl = ["h.BILLNO", "h.BILLDATE", "d.ITEMCODE"]
    aliases = {}
    if qty_col:
        select_dtl.append(f"d.{qty_col} AS QUANTITY")
        aliases["QUANTITY"] = qty_col
    if base_col:
        select_dtl.append(f"d.{base_col} AS BASEQTY")
    if uom_col:
        select_dtl.append(f"d.{uom_col} AS UOM")
    for c in ("RATE", "AMOUNT", "AVERAGECOST", "COSTPRICE"):
        if c in dtl_cols:
            select_dtl.append(f"d.{c}")
    cur.execute(
        f"""
        SELECT * FROM (
          SELECT {', '.join(select_dtl)}
          FROM BILLDTL d
          JOIN BILLHDR h
            ON TO_CHAR(h.BILLNO) = TO_CHAR(d.BILLNO)
           AND h.LOCATIONCODE = d.LOCATIONCODE
          WHERE d.ITEMCODE = :c
          ORDER BY h.BILLDATE DESC NULLS LAST, h.BILLNO DESC
        ) WHERE ROWNUM <= 20
        """,
        {"c": 1025},
    )
    bcols = [d[0] for d in cur.description]
    bills = [dict(zip(bcols, r)) for r in cur.fetchall()]
    print("\n=== Recent BILLDTL for 1025 ===")
    for b in bills:
        qty = float(b.get("QUANTITY") or 0)
        base = float(b.get("BASEQTY") or 0)
        rate = float(b.get("RATE") or 0)
        amt = float(b.get("AMOUNT") or 0)
        line_avg = float(b.get("AVERAGECOST") or 0) or unit_cost
        expected_base = None
        # infer factor from map matching UOM
        uom = str(b.get("UOM") or "").strip().upper()
        for a in alts:
            au = str(
                a.get("ALTERNATEUOMCODE") or a.get("alternateuomcode") or ""
            ).strip().upper()
            if au == uom:
                fac = 1.0
                for fk in ("UOMFACTOR", "CONVERSIONFACTOR", "FACTOR"):
                    if a.get(fk) is not None:
                        fac = float(a.get(fk) or 1)
                        break
                expected_base = round(abs(qty) * fac, 6)
                break
        if expected_base is None and uom == base_uom.upper():
            expected_base = abs(qty)
        cogs = round(abs(base) * line_avg, 2) if base and line_avg else None
        print(
            {
                **{k: b[k] for k in bcols},
                "_expected_base": expected_base,
                "_base_ok": (expected_base is None) or abs((expected_base or 0) - abs(base)) < 0.001,
                "_inventory_posting_value": cogs,
                "_sales_amount": amt if amt else round(qty * rate, 2),
            }
        )

    # ITEMJOURNAL recent
    try:
        cur.execute(
            """
            SELECT * FROM (
              SELECT DOCNO, DOCDATE, ITEMCODE, QTY, AMOUNT, AVERAGECOST, UOM, TRANSTYPE
              FROM ITEMJOURNAL
              WHERE ITEMCODE = :c
              ORDER BY DOCDATE DESC NULLS LAST, DOCNO DESC
            ) WHERE ROWNUM <= 15
            """,
            {"c": 1025},
        )
        jcols = [d[0] for d in cur.description]
        print("\n=== Recent ITEMJOURNAL 1025 ===")
        for r in cur.fetchall():
            print(dict(zip(jcols, r)))
    except Exception as exc:
        print("\nITEMJOURNAL query failed:", exc)

    cur.close()
    try:
        conn.close()
    except Exception:
        pass


if __name__ == "__main__":
    main()
