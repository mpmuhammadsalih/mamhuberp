from __future__ import annotations

import logging
from typing import Any

from db.oracle_driver import cx_Oracle
from mobile_backend.request_context import get_jwt

from mobile_backend.database.oracle_pool import get_connection
from mobile_backend.services.inventory_service import _pick_existing
from mobile_backend.services.purchase_service import list_formal_receipt_documents

logger = logging.getLogger(__name__)


def _to_float(v: Any) -> float:
    """Oracle NUMBER / Decimal → float."""
    if v is None:
        return 0.0
    if isinstance(v, float):
        return v
    if isinstance(v, int):
        return float(v)
    try:
        from decimal import Decimal

        if isinstance(v, Decimal):
            return float(v)
    except ImportError:
        pass
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _billhdr_column_names(cur: Any) -> frozenset[str]:
    """Columns for BILLHDR: owned table, then synonym → ALL_TAB_COLUMNS, then any accessible."""
    cols: set[str] = set()
    try:
        cur.execute(
            """
            SELECT column_name
            FROM user_tab_columns
            WHERE table_name = 'BILLHDR'
            """
        )
        cols.update(str(row[0]).upper() for row in cur.fetchall() or [])
    except cx_Oracle.DatabaseError:
        pass

    if cols:
        return frozenset(cols)

    ora_user = ""
    try:
        cur.execute("SELECT USER FROM dual")
        ora_user = str(cur.fetchone()[0] or "").strip().upper()
    except cx_Oracle.DatabaseError:
        pass

    if ora_user:
        try:
            cur.execute(
                """
                SELECT table_owner, table_name
                  FROM (
                        SELECT table_owner, table_name,
                               CASE WHEN owner = :ora_user THEN 1
                                    WHEN owner = 'PUBLIC' THEN 2
                                    ELSE 3 END AS pr
                          FROM all_synonyms
                         WHERE UPPER(synonym_name) = 'BILLHDR'
                           AND owner IN (:ora_user, 'PUBLIC')
                         ORDER BY pr
                       )
                 WHERE ROWNUM = 1
                """,
                {"ora_user": ora_user},
            )
            resolved = cur.fetchone()
            if resolved:
                towner = str(resolved[0] or "").upper()
                tname = str(resolved[1] or "").upper()
                cur.execute(
                    """
                    SELECT column_name
                      FROM all_tab_columns
                     WHERE owner = :own AND table_name = :tn
                    """,
                    {"own": towner, "tn": tname},
                )
                cols.update(str(row[0]).upper() for row in cur.fetchall() or [])
        except cx_Oracle.DatabaseError:
            pass

    if not cols:
        try:
            cur.execute(
                """
                SELECT DISTINCT column_name
                  FROM all_tab_columns
                 WHERE table_name = 'BILLHDR'
                """
            )
            cols.update(str(row[0]).upper() for row in cur.fetchall() or [])
        except cx_Oracle.DatabaseError:
            pass

    return frozenset(cols)


def _billhdr_history_column_names(cur: Any) -> frozenset[str]:
    """Columns for BILLHDRHISTORY (Nexa Dynamics dashboard source), same resolution pattern as BILLHDR."""
    cols: set[str] = set()
    for table_literal in ("BILLHDRHISTORY", "BILLHDR_HISTORY"):
        found: set[str] = set()
        try:
            cur.execute(
                """
                SELECT column_name
                FROM user_tab_columns
                WHERE table_name = :tn
                """,
                {"tn": table_literal},
            )
            found.update(str(row[0]).upper() for row in cur.fetchall() or [])
        except cx_Oracle.DatabaseError:
            pass
        if found:
            return frozenset(found)

    ora_user = ""
    try:
        cur.execute("SELECT USER FROM dual")
        ora_user = str(cur.fetchone()[0] or "").strip().upper()
    except cx_Oracle.DatabaseError:
        pass

    if ora_user:
        for syn in ("BILLHDRHISTORY", "BILLHDR_HISTORY"):
            try:
                cols.clear()
                cur.execute(
                    """
                    SELECT table_owner, table_name
                      FROM (
                            SELECT table_owner, table_name,
                                   CASE WHEN owner = :ora_user THEN 1
                                        WHEN owner = 'PUBLIC' THEN 2
                                        ELSE 3 END AS pr
                              FROM all_synonyms
                             WHERE UPPER(synonym_name) = :syn
                               AND owner IN (:ora_user, 'PUBLIC')
                             ORDER BY pr
                           )
                     WHERE ROWNUM = 1
                    """,
                    {"ora_user": ora_user, "syn": syn},
                )
                resolved = cur.fetchone()
                if resolved:
                    towner = str(resolved[0] or "").upper()
                    tname = str(resolved[1] or "").upper()
                    cur.execute(
                        """
                        SELECT column_name
                          FROM all_tab_columns
                         WHERE owner = :own AND table_name = :tn
                        """,
                        {"own": towner, "tn": tname},
                    )
                    cols.update(str(row[0]).upper() for row in cur.fetchall() or [])
                if cols:
                    return frozenset(cols)
            except cx_Oracle.DatabaseError:
                pass

    if not cols:
        try:
            cur.execute(
                """
                SELECT DISTINCT column_name
                  FROM all_tab_columns
                 WHERE UPPER(table_name) IN ('BILLHDRHISTORY', 'BILLHDR_HISTORY')
                """
            )
            cols.update(str(row[0]).upper() for row in cur.fetchall() or [])
        except cx_Oracle.DatabaseError:
            pass

    return frozenset(cols)


def _billhdr_history_from_clause(cur: Any) -> str | None:
    """Return usable FROM fragment (e.g. 'billhdrhistory b'); None if table not selectable."""
    for ident in ("billhdrhistory", "BILLHDRHISTORY"):
        try:
            cur.execute(f"SELECT 1 FROM {ident} b WHERE ROWNUM = 1")
            return f"{ident} b"
        except cx_Oracle.DatabaseError:
            continue
    return None


def _amount_column_candidates(bh_cols: set[str]) -> list[str]:
    """Prefer known ERP names, then other *AMOUNT* / *TOTAL* columns on billhdr."""
    priority = [
        "NETBILLAMOUNT",
        "NET_BILL_AMOUNT",
        "NET_BILL_AMT",
        "NETAMOUNT",
        "NET_AMOUNT",
        "TOTALAMOUNT",
        "TOTAL_AMOUNT",
        "BILLAMOUNT",
        "BILL_AMOUNT",
        "GROSSAMOUNT",
        "GROSS_AMOUNT",
        "INVOICEAMOUNT",
        "INVAMOUNT",
        "INV_AMT",
        "PAYABLEAMOUNT",
        "NETVALUE",
        "NET_VALUE",
        "FINALAMOUNT",
        "FINAL_AMOUNT",
        "GRANDTOTAL",
        "SUBTOTAL",
    ]
    ordered: list[str] = []
    seen: set[str] = set()
    for c in priority:
        if c in bh_cols and c not in seen:
            ordered.append(c)
            seen.add(c)
    for c in sorted(bh_cols):
        if c in seen:
            continue
        cu = c.upper()
        if cu.startswith("REDEMPT"):
            continue
        if "AMOUNT" in cu or cu.endswith("AMT") or "TOTAL" in cu or cu.endswith("VALUE"):
            ordered.append(c)
            seen.add(c)
    return ordered


def _sum_bill_first_nonzero_amt(
    cur: Any,
    bh_cols: set[str],
    from_clause: str,
    where_clause_sql: str | None,
) -> tuple[float, str]:
    """Try SUM(amount columns) FROM from_clause alias b until non-zero (same logic as legacy billhdr path)."""
    redemption_col = _pick_existing(
        bh_cols,
        ["REDEMPTIONAMOUNT", "REDEMPTION_AMOUNT", "REDEMPTION_AMT", "REDEMPTAMOUNT"],
    )
    red = f"NVL(b.{redemption_col}, 0)" if redemption_col else "0"
    suffix = ""
    if where_clause_sql:
        suffix = " WHERE " + where_clause_sql
    best_zero: tuple[float, str] | None = None
    for amt in _amount_column_candidates(bh_cols):
        if amt == redemption_col:
            continue
        exprs: list[tuple[str, str]] = []
        if redemption_col:
            exprs.append((f"NVL(b.{amt}, 0) + {red}", "plus_red"))
        exprs.append((f"NVL(b.{amt}, 0)", "amt_only"))
        for expr, _tag in exprs:
            sql = f"SELECT NVL(SUM({expr}), 0) FROM {from_clause}{suffix}"
            try:
                cur.execute(sql)
                v = _to_float((cur.fetchone() or [0])[0])
                logger.debug(
                    "dashboard SUM (%s) amt=%s where=%s -> %s",
                    from_clause.split()[0],
                    amt,
                    bool(where_clause_sql),
                    v,
                )
                if v != 0.0:
                    return v, amt
                if best_zero is None:
                    best_zero = (v, amt)
            except cx_Oracle.DatabaseError:
                continue
    if best_zero:
        return best_zero[0], best_zero[1]
    return 0.0, ""


def _sum_billhdr_first_nonzero_amt(
    cur: Any,
    bh_cols: set[str],
    where_clause_sql: str | None,
) -> tuple[float, str]:
    """SUM over amount columns on live BILLHDR (alias b)."""
    return _sum_bill_first_nonzero_amt(cur, bh_cols, "billhdr b", where_clause_sql)


def _billhdr_rows_today_count(cur: Any) -> int:
    """Rows in BILLHDR for calendar today (preferred: TRUNC(BILLDATE) = TRUNC(SYSDATE))."""
    try:
        cur.execute(
            """
            SELECT COUNT(*) FROM billhdr b
             WHERE TRUNC(b.BILLDATE) = TRUNC(SYSDATE)
            """
        )
        return int(cur.fetchone()[0] or 0)
    except cx_Oracle.DatabaseError:
        pass
    bh_cols = set(_billhdr_column_names(cur))
    date_col = _pick_existing(
        bh_cols,
        ["BILLDATE", "BILL_DATE", "SALESDATE", "TRNDATE", "VDATE", "DOC_DATE"],
    )
    if not date_col:
        return 0
    try:
        cur.execute(
            "SELECT COUNT(*) FROM billhdr b WHERE TRUNC(b."
            + date_col
            + ") = TRUNC(SYSDATE)"
        )
        return int(cur.fetchone()[0] or 0)
    except cx_Oracle.DatabaseError:
        return 0


def _try_today_from_billhdrhistory(cur: Any) -> tuple[float, int, dict[str, Any]] | None:
    """
    Nexa Dynamics parity: today total = NVL(SUM(NETBILLAMOUNT)), filter TRUNC(BILLDATE) = TRUNC(SYSDATE).
    Rows today = COUNT on the same predicate. Returns None only when billhdrhistory is not usable.
    """
    from_fc = _billhdr_history_from_clause(cur)
    if not from_fc:
        return None
    hist_cols = set(_billhdr_history_column_names(cur))
    date_col_meta = _pick_existing(
        hist_cols,
        [
            "BILLDATE",
            "BILL_DATE",
            "SALESDATE",
            "SALES_DATE",
            "TRNDATE",
            "TXNDATE",
            "VDATE",
            "INVOICEDATE",
            "DOC_DATE",
            "ENTRYDATE",
        ],
    )

    diag: dict[str, Any] = {
        "primary_source": "billhdrhistory",
        "history_from_clause": from_fc,
        "history_column_count": len(hist_cols),
        "history_date_col_meta": date_col_meta,
    }

    variants: list[tuple[str, str]] = [
        (
            "history_trunc_netbillamount_only",
            f"SELECT NVL(SUM(NVL(b.NETBILLAMOUNT, 0)), 0) FROM {from_fc} "
            f"WHERE TRUNC(b.BILLDATE) = TRUNC(SYSDATE)",
        ),
        (
            "history_trunc_net_redemption",
            f"SELECT NVL(SUM(NVL(b.NETBILLAMOUNT, 0) + NVL(b.REDEMPTIONAMOUNT, 0)), 0) "
            f"FROM {from_fc} WHERE TRUNC(b.BILLDATE) = TRUNC(SYSDATE)",
        ),
        (
            "history_eq_date_netbillamount",
            f"SELECT NVL(SUM(NVL(b.NETBILLAMOUNT, 0)), 0) FROM {from_fc} "
            f"WHERE b.BILLDATE = TRUNC(SYSDATE)",
        ),
    ]

    total = 0.0
    hit_label = ""
    dated_ok = False
    for label, sql in variants:
        try:
            cur.execute(sql)
            total = _to_float((cur.fetchone() or [0])[0])
            dated_ok = True
            hit_label = label
            logger.debug("dashboard billhdrhistory: %s -> %s", label, total)
            break
        except cx_Oracle.DatabaseError as exc:
            logger.debug("dashboard billhdrhistory: %s failed (%s)", label, exc)
            continue

    if not dated_ok:
        netbill_col = _pick_existing(
            hist_cols,
            ["NETBILLAMOUNT", "NET_BILL_AMOUNT", "NETBILL_AMT", "NETAMOUNT", "NET_AMOUNT"],
        )
        redeem_col = _pick_existing(
            hist_cols,
            ["REDEMPTIONAMOUNT", "REDEMPTION_AMOUNT", "REDEMPTION_AMT", "REDEMPTAMOUNT"],
        )
        dc = date_col_meta
        if netbill_col and dc:
            red_sql = f"NVL(b.{redeem_col}, 0)" if redeem_col else "0"
            line_expr = f"NVL(b.{netbill_col}, 0) + {red_sql}"
            sql_fb = (
                f"SELECT NVL(SUM({line_expr}), 0) FROM {from_fc} "
                f"WHERE TRUNC(b.{dc}) = TRUNC(SYSDATE)"
            )
            try:
                cur.execute(sql_fb)
                total = _to_float((cur.fetchone() or [0])[0])
                dated_ok = True
                hit_label = "history_trunc_dynamic_net_cols"
                diag["history_fallback_net_col"] = netbill_col
                diag["history_fallback_date_col"] = dc
                logger.debug("dashboard billhdrhistory: fallback -> %s", total)
            except cx_Oracle.DatabaseError:
                pass

    if not dated_ok:
        return None

    diag["history_probe_hit"] = hit_label
    diag["history_probe_total_before_dynamic"] = total

    rows_today = 0
    tried_cols: list[str] = []
    if date_col_meta:
        tried_cols.append(date_col_meta)
    for extra in ("BILLDATE", "BILL_DATE"):
        if extra not in tried_cols:
            tried_cols.append(extra)
    for dcc in tried_cols:
        try:
            cur.execute(
                f"SELECT COUNT(*) FROM {from_fc} "
                f"WHERE TRUNC(b.{dcc}) = TRUNC(SYSDATE)",
            )
            rows_today = int((cur.fetchone() or [0])[0] or 0)
            diag["history_count_date_col_used"] = dcc
            break
        except cx_Oracle.DatabaseError:
            continue

    diag["rows_today"] = rows_today

    ddyn = (
        date_col_meta
        or diag.get("history_fallback_date_col")
        or diag.get("history_count_date_col_used")
    )
    if total == 0.0 and hist_cols and ddyn:
        wc = f"TRUNC(b.{ddyn}) = TRUNC(SYSDATE)"
        v_t, col_t = _sum_bill_first_nonzero_amt(cur, hist_cols, from_fc, wc)
        diag["history_dynamic_sum"] = v_t
        diag["history_dynamic_col"] = col_t
        if v_t != 0.0:
            total = v_t

    return total, rows_today, diag


def _today_sales_from_billhdr(cur: Any) -> tuple[float, int, dict[str, Any]]:
    """
    Today sales and today's bill row count from live **BILLHDR** only.

    Uses ``NETBILLAMOUNT`` (+ redemption when present) with
    ``TRUNC(BILLDATE)=TRUNC(SYSDATE)``, then dynamic amount-column fallbacks.

    Returns:
        tuple of (today_sales_amount, rows_today, debug_dict).

    Oracle NUMBER aggregates are normalized with `_to_float` (Decimal-safe).
    """
    rows_today = _billhdr_rows_today_count(cur)
    diag: dict[str, Any] = {"rows_today": rows_today, "primary_source": "billhdr"}

    no_date_variants: list[tuple[str, str]] = [
        (
            "no_date_net_redemption",
            """
            SELECT NVL(SUM(NVL(b.NETBILLAMOUNT, 0) + NVL(b.REDEMPTIONAMOUNT, 0)), 0)
              FROM billhdr b
            """,
        ),
        (
            "no_date_net_only",
            """
            SELECT NVL(SUM(NVL(b.NETBILLAMOUNT, 0)), 0)
              FROM billhdr b
            """,
        ),
    ]
    dated_variants: list[tuple[str, str]] = [
        (
            "trunc_billdate_net_redemption",
            """
            SELECT NVL(SUM(NVL(b.NETBILLAMOUNT, 0) + NVL(b.REDEMPTIONAMOUNT, 0)), 0)
              FROM billhdr b
             WHERE TRUNC(b.BILLDATE) = TRUNC(SYSDATE)
            """,
        ),
        (
            "trunc_billdate_net_only",
            """
            SELECT NVL(SUM(NVL(b.NETBILLAMOUNT, 0)), 0)
              FROM billhdr b
             WHERE TRUNC(b.BILLDATE) = TRUNC(SYSDATE)
            """,
        ),
        (
            "eq_midnight_net_redemption",
            """
            SELECT NVL(SUM(NVL(b.NETBILLAMOUNT, 0) + NVL(b.REDEMPTIONAMOUNT, 0)), 0)
              FROM billhdr b
             WHERE b.BILLDATE = TRUNC(SYSDATE)
            """,
        ),
    ]

    def _first_variant_hit(
        pairs: list[tuple[str, str]],
    ) -> tuple[bool, float, str]:
        for label, sql in pairs:
            try:
                cur.execute(sql)
                row = cur.fetchone()
                val = _to_float(row[0]) if row else 0.0
                logger.debug("dashboard today_sales: %s -> %s", label, val)
                return True, val, label
            except cx_Oracle.DatabaseError as exc:
                logger.debug("dashboard today_sales: %s failed (%s)", label, exc)
                continue
        return False, 0.0, ""

    no_date_ok, no_date_total, no_date_label = _first_variant_hit(no_date_variants)
    dated_ok, dated_total, dated_label = _first_variant_hit(dated_variants)
    diag["probe_no_date_hit"] = no_date_label if no_date_ok else None
    diag["probe_dated_hit"] = dated_label if dated_ok else None
    diag["probe_no_date_total"] = no_date_total
    diag["probe_dated_total"] = dated_total

    if dated_ok:
        total = dated_total
        variant_hit = True
    else:
        total = no_date_total if no_date_ok else 0.0
        variant_hit = no_date_ok

    if not variant_hit:
        bh_cols = set(_billhdr_column_names(cur))
        if not bh_cols:
            logger.debug("dashboard today_sales: no BILLHDR columns")
            diag["exit"] = "no_billhdr_columns"
            return 0.0, rows_today, diag

        netbill_col = _pick_existing(
            bh_cols,
            ["NETBILLAMOUNT", "NET_BILL_AMOUNT", "NETBILL_AMT", "NETAMOUNT", "NET_AMOUNT"],
        )
        redemption_col = _pick_existing(
            bh_cols,
            ["REDEMPTIONAMOUNT", "REDEMPTION_AMOUNT", "REDEMPTION_AMT", "REDEMPTAMOUNT"],
        )
        date_col = _pick_existing(
            bh_cols,
            [
                "BILLDATE",
                "BILL_DATE",
                "SALESDATE",
                "SALES_DATE",
                "TRNDATE",
                "TXNDATE",
                "VDATE",
                "INVOICEDATE",
                "DOC_DATE",
                "ENTRYDATE",
            ],
        )
        if not netbill_col or not date_col:
            logger.debug(
                "dashboard today_sales: fallback missing col (net=%s date=%s)",
                netbill_col,
                date_col,
            )
            diag["exit"] = "fallback_missing_cols"
            diag["fallback_netbill_col"] = netbill_col
            diag["fallback_date_col"] = date_col
            return 0.0, rows_today, diag

        red_sql = f"NVL(b.{redemption_col}, 0)" if redemption_col else "0"
        line_expr = f"NVL(b.{netbill_col}, 0) + {red_sql}"
        fallback_sql = f"""
            SELECT NVL(SUM({line_expr}), 0)
              FROM billhdr b
             WHERE TRUNC(b.{date_col}) = TRUNC(SYSDATE)
        """
        try:
            cur.execute(fallback_sql)
            row = cur.fetchone()
            total = _to_float(row[0]) if row else 0.0
            logger.debug(
                "dashboard today_sales: fallback net=%s red=%s date=%s -> %s",
                netbill_col,
                redemption_col,
                date_col,
                total,
            )
            diag["fallback_used"] = True
        except cx_Oracle.DatabaseError:
            logger.exception("dashboard today_sales: fallback failed (%s)", fallback_sql[:500])
            total = 0.0
            diag["fallback_used"] = False

    bh_cols_alt = set(_billhdr_column_names(cur))
    date_alt = _pick_existing(
        bh_cols_alt,
        [
            "BILLDATE",
            "BILL_DATE",
            "SALESDATE",
            "SALES_DATE",
            "TRNDATE",
            "TXNDATE",
            "VDATE",
            "INVOICEDATE",
            "DOC_DATE",
            "ENTRYDATE",
        ],
    )
    diag["date_alt"] = date_alt
    diag["billhdr_column_count"] = len(bh_cols_alt)
    try:
        cur.execute("SELECT COUNT(*) FROM billhdr")
        diag["billhdr_all_rows"] = int((cur.fetchone() or [0])[0] or 0)
    except cx_Oracle.DatabaseError:
        diag["billhdr_all_rows"] = None

    if total == 0.0 and bh_cols_alt:
        if date_alt:
            wc = f"TRUNC(b.{date_alt}) = TRUNC(SYSDATE)"
            v_t, col_t = _sum_billhdr_first_nonzero_amt(cur, bh_cols_alt, wc)
            diag["dynamic_today_sum"] = v_t
            diag["dynamic_today_col"] = col_t
            if v_t != 0.0:
                total = v_t
                logger.debug(
                    "dashboard today_sales: dynamic today sum col=%s -> %s",
                    col_t,
                    v_t,
                )
        if total == 0.0 and date_alt is None:
            v_a, col_a = _sum_billhdr_first_nonzero_amt(cur, bh_cols_alt, None)
            diag["dynamic_all_sum"] = v_a
            diag["dynamic_all_col"] = col_a
            if v_a != 0.0:
                total = v_a
                logger.debug(
                    "dashboard today_sales: dynamic all-rows sum (no date column) col=%s -> %s",
                    col_a,
                    v_a,
                )

    diag["probe_total_before_dynamic"] = (
        dated_total if dated_ok else (no_date_total if no_date_ok else 0.0)
    )
    return total, rows_today, diag


def _itemmaster_inventory_stats(cur: Any) -> dict[str, float | int]:
    """Aggregates from ITEMMASTER: on-hand qty and stock value = SUM(NVL(currentstock,0)*NVL(costprice,0))."""
    out: dict[str, float | int] = {
        "total_stock_qty": 0.0,
        "out_of_stock_items": 0,
        "low_stock_items": 0,
        "stock_value": 0.0,
    }
    try:
        cur.execute(
            """
            SELECT column_name
            FROM user_tab_columns
            WHERE table_name = 'ITEMMASTER'
            """
        )
        item_cols = {str(row[0]).upper() for row in cur.fetchall() or []}
    except cx_Oracle.DatabaseError:
        return out

    qty_col = _pick_existing(
        item_cols,
        [
            "CURRENTSTOCK",
            "CURRENT_STOCK",
            "QTY_ON_HAND",
            "STOCK",
            "QTY",
            "BALANCEQTY",
        ],
    )
    if not qty_col:
        return out

    reorder_col = _pick_existing(
        item_cols,
        ["REORDERLEVEL", "REORDER_LEVEL", "REORDERQTY", "MINQTY", "MIN_STOCK_LEVEL", "MINIMUMQTY"],
    )
    cost_col = _pick_existing(
        item_cols,
        [
            "COSTPRICE",
            "COST_PRICE",
            "UNITCOST",
            "UNIT_COST",
            "AVCOST",
            "AVERAGECOST",
            "STANDARDCOST",
            "COST",
        ],
    )

    q_expr = f"NVL(i.{qty_col}, 0)"
    sums = [
        f"NVL(SUM({q_expr}), 0)",
        f"NVL(SUM(CASE WHEN {q_expr} <= 0 THEN 1 ELSE 0 END), 0)",
    ]
    if reorder_col:
        r_expr = f"NVL(i.{reorder_col}, 0)"
        sums.append(
            f"NVL(SUM(CASE WHEN {r_expr} > 0 AND {q_expr} < {r_expr} AND {q_expr} >= 0 THEN 1 ELSE 0 END), 0)"
        )
    else:
        sums.append("CAST(0 AS NUMBER)")

    if cost_col:
        c_expr = f"NVL(i.{cost_col}, 0)"
        sums.append(f"NVL(SUM({q_expr} * {c_expr}), 0)")
    else:
        sums.append("CAST(0 AS NUMBER)")

    sql = f"SELECT {', '.join(sums)} FROM itemmaster i"
    try:
        cur.execute(sql)
        row = cur.fetchone()
        if row:
            out["total_stock_qty"] = _to_float(row[0])
            out["out_of_stock_items"] = int(row[1] or 0)
            out["low_stock_items"] = int(row[2] or 0)
            out["stock_value"] = _to_float(row[3])
    except cx_Oracle.DatabaseError:
        pass
    return out


def _core_counts(cur: Any) -> tuple[int, float, int, int, dict[str, Any]]:
    total_items = 0
    customer_count = 0
    try:
        cur.execute(
            """
            SELECT
                NVL((SELECT COUNT(*) FROM itemmaster), 0),
                NVL((SELECT COUNT(*) FROM customer), 0)
            FROM dual
            """
        )
        row = cur.fetchone()
        if row:
            total_items = int(row[0] or 0)
            customer_count = int(row[1] or 0)
    except cx_Oracle.DatabaseError:
        try:
            cur.execute("SELECT COUNT(*) FROM itemmaster")
            total_items = int(cur.fetchone()[0] or 0)
        except cx_Oracle.DatabaseError:
            pass
        try:
            cur.execute("SELECT COUNT(*) FROM customer")
            customer_count = int(cur.fetchone()[0] or 0)
        except cx_Oracle.DatabaseError:
            pass

    today_sales, billhdr_rows_today, sales_debug = _today_sales_from_billhdr(cur)
    return total_items, today_sales, customer_count, billhdr_rows_today, sales_debug


def _branch_info() -> dict[str, Any]:
    try:
        from db import get_location_info_by_dbkey

        info = get_location_info_by_dbkey(None) or {}
        name = str(info.get("locationname") or "").strip()
        code = info.get("locationcode")
        branch_code: int | None
        try:
            branch_code = int(code) if code is not None else None
        except (TypeError, ValueError):
            branch_code = None
        return {"branch_name": name, "branch_code": branch_code}
    except Exception:
        return {"branch_name": "", "branch_code": None}


def _recent_receipts_payload(limit: int = 8) -> list[dict[str, Any]]:
    try:
        rows = list_formal_receipt_documents(1, limit, "")
    except (cx_Oracle.DatabaseError, ValueError, RuntimeError):
        return []
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "receipt_no": str(r.get("receipt_no") or "").strip(),
                "po_no": str(r.get("po_no") or "").strip(),
                "supplier": str(r.get("supplier") or "").strip(),
                "invoice_no": str(r.get("invoice_no") or "").strip(),
                "receipt_date": str(r.get("receipt_date") or "").strip(),
                "amount": float(r.get("amount") or 0),
                "status": str(r.get("status") or "Posted"),
            }
        )
    return out


def _pct_change(today: float, yesterday: float) -> float:
    if abs(yesterday) < 1e-9:
        return 100.0 if abs(today) > 1e-9 else 0.0
    return round((today - yesterday) / abs(yesterday) * 100.0, 1)


def _parse_iso_date(raw: str | None):
    from datetime import datetime

    s = str(raw or "").strip()[:10]
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def _period_label(date_from, date_to) -> str:
    from datetime import date, timedelta

    today = date.today()
    if date_from == date_to:
        if date_from == today:
            return f"Today, {date_from.strftime('%d %b %Y')}"
        if date_from == today - timedelta(days=1):
            return f"Yesterday, {date_from.strftime('%d %b %Y')}"
        return date_from.strftime("%d %b %Y")
    return f"{date_from.strftime('%d %b %Y')} – {date_to.strftime('%d %b %Y')}"


def _sales_amount_for_day(cur: Any, day) -> tuple[float, int]:
    """Net sales + invoice count for one calendar day from live BILLHDR only."""
    params = {"d": day}
    for tbl in ("billhdr", "BILLHDR"):
        try:
            cur.execute(
                f"""
                SELECT NVL(SUM(NVL(NETBILLAMOUNT, 0)), 0),
                       COUNT(*)
                  FROM {tbl}
                 WHERE TRUNC(BILLDATE) = TRUNC(:d)
                """,
                params,
            )
            row = cur.fetchone() or (0, 0)
            return _to_float(row[0]), int(row[1] or 0)
        except cx_Oracle.DatabaseError:
            continue
    return 0.0, 0


def _kpi_map(payload: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for k in payload.get("kpis") or []:
        if not isinstance(k, dict):
            continue
        kid = str(k.get("id") or "").strip()
        if not kid:
            continue
        out[kid] = _to_float(k.get("value"))
    return out


def _cpv_posted_total(date_from: str, date_to: str) -> float:
    """Sum posted Cash Payment Voucher amounts in [date_from, date_to] (YYYY-MM-DD)."""
    df = str(date_from or "").strip()[:10]
    dt = str(date_to or "").strip()[:10]
    if len(df) < 10 or len(dt) < 10:
        return 0.0
    try:
        from mobile_backend.services import cash_payment_voucher_service as cpvs

        payload = cpvs.list_vouchers(status="posted", limit=500) or {}
        total = 0.0
        for r in payload.get("vouchers") or []:
            vd = str(r.get("voucher_date") or "").strip()[:10]
            if len(vd) < 10:
                continue
            if df <= vd <= dt:
                total += _to_float(r.get("total_amount"))
        return round(total, 2)
    except Exception:
        logger.debug("dashboard CPV total failed", exc_info=True)
        return 0.0


def _sales_panel_enrichment(
    *,
    date_from=None,
    date_to=None,
) -> dict[str, Any]:
    """Cash/credit, collections, trends, top customers — reuse ERP sales + business summary."""
    from datetime import date, timedelta

    today = date.today()
    d_from = date_from or today
    d_to = date_to or d_from
    if d_from > d_to:
        d_from, d_to = d_to, d_from
    today_s = d_from.strftime("%Y-%m-%d")
    to_s = d_to.strftime("%Y-%m-%d")
    # Prior period of equal length for trend %
    span_days = (d_to - d_from).days + 1
    prior_to = d_from - timedelta(days=1)
    prior_from = prior_to - timedelta(days=span_days - 1)
    yday_s = prior_to.strftime("%Y-%m-%d")

    panel: dict[str, Any] = {
        "as_of": to_s,
        "date_from": today_s,
        "date_to": to_s,
        "period_label": _period_label(d_from, d_to),
        "yesterday_sales": 0.0,
        "sales_trend_pct": 0.0,
        "invoice_count": 0,
        "invoice_count_yesterday": 0,
        "invoice_trend_pct": 0.0,
        "cash_sales": 0.0,
        "credit_sales": 0.0,
        "amount_collected": 0.0,
        "outstanding_amount": 0.0,
        "collection_pct": 0.0,
        "sales_return": 0.0,
        "return_count": 0,
        "sales_orders_today": 0,
        "new_customers_today": 0,
        "top_customers": [],
    }

    # Single-day "today" relative helpers only when period is calendar today
    if d_from == d_to == today:
        try:
            from db import get_sales_dashboard_data

            dash = get_sales_dashboard_data() or {}
            panel["yesterday_sales"] = round(_to_float(dash.get("yesterday_sales")), 2)
            panel["invoice_count"] = int(_to_float(dash.get("today_billcount")))
            panel["invoice_count_yesterday"] = int(_to_float(dash.get("yesterday_billcount")))
            panel["sales_return"] = round(_to_float(dash.get("today_returns")), 2)
            tops = []
            for row in (dash.get("top_customers_today") or [])[:5]:
                if not isinstance(row, dict):
                    continue
                tops.append(
                    {
                        "code": str(row.get("code") or "").strip(),
                        "name": str(row.get("name") or "Customer").strip() or "Customer",
                        "sales": round(_to_float(row.get("today_amount")), 2),
                        "invoices": int(_to_float(row.get("bill_count") or row.get("invoices") or 0)),
                    }
                )
            panel["top_customers"] = tops
        except Exception:
            logger.debug("sales dashboard enrichment failed", exc_info=True)

    # ERP Summary KPIs (from Daily Business Summary)
    panel.update(
        {
            "purchases": 0.0,
            "expenses": 0.0,
            "gross_profit": 0.0,
            "net_profit": 0.0,
            "purchases_trend_pct": 0.0,
            "expenses_trend_pct": 0.0,
            "gross_profit_trend_pct": 0.0,
            "net_profit_trend_pct": 0.0,
            "inventory_value": 0.0,
            "items_in_stock": 0,
            "payables_total": 0.0,
            "payables_overdue": 0.0,
            "payables_not_due": 0.0,
            "receivables_overdue": 0.0,
            "receivables_not_due": 0.0,
            "cash_balance": 0.0,
            "bank_balance": 0.0,
            "cash_bank_total": 0.0,
            "currency": "",
            "recent_activity": [],
            "alerts": [],
            "return_count": 0,
            "visits_today": 0,
        }
    )

    try:
        from mobile_backend.services.business_summary_service import get_business_summary

        bs = get_business_summary(date_from=today_s, date_to=to_s) or {}
        kpis = _kpi_map(bs)
        # Prior period for trend %
        try:
            bs_prior = get_business_summary(
                date_from=prior_from.strftime("%Y-%m-%d"),
                date_to=prior_to.strftime("%Y-%m-%d"),
            ) or {}
            pk = _kpi_map(bs_prior)
            panel["yesterday_sales"] = round(
                _to_float(pk.get("net_sales") or pk.get("total_sales") or panel.get("yesterday_sales")),
                2,
            )
            panel["purchases_trend_pct"] = _pct_change(
                _to_float(kpis.get("net_purchases") or kpis.get("total_purchases")),
                _to_float(pk.get("net_purchases") or pk.get("total_purchases")),
            )
            panel["expenses_trend_pct"] = _pct_change(
                _to_float(kpis.get("expenses")),
                _to_float(pk.get("expenses")),
            )
            panel["gross_profit_trend_pct"] = _pct_change(
                _to_float(kpis.get("gross_profit")),
                _to_float(pk.get("gross_profit")),
            )
            prior_net = _to_float(pk.get("gross_profit")) - _to_float(pk.get("expenses"))
            cur_net = _to_float(kpis.get("gross_profit")) - _to_float(kpis.get("expenses"))
            panel["net_profit_trend_pct"] = _pct_change(cur_net, prior_net)
            if not panel.get("invoice_count_yesterday"):
                for t in bs_prior.get("transaction_summary") or []:
                    if isinstance(t, dict) and str(t.get("label") or "").strip().lower() == "sales":
                        panel["invoice_count_yesterday"] = int(_to_float(t.get("count") or t.get("qty")))
                        break
        except Exception:
            logger.debug("prior-period summary failed", exc_info=True)
        cash = _to_float(kpis.get("cash_sales"))
        credit = _to_float(kpis.get("credit_sales"))
        collected = _to_float(kpis.get("customer_receipts"))
        outstanding = _to_float(kpis.get("outstanding_receivables"))
        if cash or credit:
            panel["cash_sales"] = round(cash, 2)
            panel["credit_sales"] = round(credit, 2)
        panel["period_sales"] = round(
            _to_float(kpis.get("net_sales") or kpis.get("total_sales") or (cash + credit)),
            2,
        )
        panel["amount_collected"] = round(collected, 2)
        panel["outstanding_amount"] = round(outstanding, 2)
        denom = collected + outstanding
        panel["collection_pct"] = round((collected / denom * 100.0), 1) if denom > 1e-9 else 0.0
        panel["purchases"] = round(_to_float(kpis.get("net_purchases") or kpis.get("total_purchases")), 2)
        # P&L expenses (ledger) — used for net profit only; Expenses card set later from CPV.
        pl_expenses = round(_to_float(kpis.get("expenses")), 2)
        panel["gross_profit"] = round(_to_float(kpis.get("gross_profit")), 2)
        panel["net_profit"] = round(panel["gross_profit"] - pl_expenses, 2)
        panel["pl_expenses"] = pl_expenses
        panel["inventory_value"] = round(_to_float(kpis.get("inventory_value")), 2)
        panel["payables_total"] = round(_to_float(kpis.get("outstanding_payables")), 2)
        if kpis.get("sales_return") is not None:
            panel["sales_return"] = round(_to_float(kpis.get("sales_return")), 2)

        # Top customers from BS if sales dashboard empty
        if not panel["top_customers"]:
            charts = bs.get("charts") if isinstance(bs.get("charts"), dict) else {}
            tops = []
            for row in (charts.get("top_customers") or [])[:5]:
                if not isinstance(row, dict):
                    continue
                tops.append(
                    {
                        "code": str(row.get("code") or row.get("id") or "").strip(),
                        "name": str(row.get("name") or row.get("label") or "Customer").strip(),
                        "sales": round(_to_float(row.get("amount") or row.get("sales") or row.get("value")), 2),
                        "invoices": int(_to_float(row.get("count") or row.get("invoices") or 0)),
                    }
                )
            panel["top_customers"] = tops
        # Invoice / return counts from transaction summary
        for t in bs.get("transaction_summary") or []:
            if not isinstance(t, dict):
                continue
            label = str(t.get("label") or t.get("name") or "").strip().lower()
            cnt = int(_to_float(t.get("count") or t.get("qty")))
            if label == "sales" and not panel["invoice_count"]:
                panel["invoice_count"] = cnt
            if "return" in label:
                panel["return_count"] = cnt
    except Exception:
        logger.debug("business summary enrichment failed", exc_info=True)

    # Always show Expenses as posted CPV only (never P&L expense).
    panel["expenses"] = _cpv_posted_total(today_s, to_s)
    try:
        prior_cpv = _cpv_posted_total(
            prior_from.strftime("%Y-%m-%d"),
            prior_to.strftime("%Y-%m-%d"),
        )
        panel["expenses_trend_pct"] = _pct_change(panel["expenses"], prior_cpv)
    except Exception:
        panel["expenses_trend_pct"] = 0.0

    # AR / AP party totals (overdue split not always available — use total as not-due when unknown)
    try:
        from mobile_backend.services import ar_ap_service

        ar = ar_ap_service.list_receivables(balance="positive")
        ap = ar_ap_service.list_payables(balance="positive")
        ar_total = round(_to_float((ar.get("totals") or {}).get("outstanding")), 2)
        ap_total = round(_to_float((ap.get("totals") or {}).get("outstanding")), 2)
        if ar_total:
            panel["outstanding_amount"] = ar_total
        if ap_total:
            panel["payables_total"] = ap_total
        # Without aging buckets, treat all as not-due (UI still shows Overdue = 0)
        panel["receivables_not_due"] = panel["outstanding_amount"]
        panel["receivables_overdue"] = 0.0
        panel["payables_not_due"] = panel["payables_total"]
        panel["payables_overdue"] = 0.0
        overdue_customers = int((ar.get("totals") or {}).get("positive_count") or 0)
        if overdue_customers > 0 and panel["outstanding_amount"] > 0:
            panel["alerts"].append(
                {
                    "severity": "warning",
                    "title": f"{overdue_customers} customers with outstanding balance",
                    "subtitle": "Open Receivables for details",
                }
            )
    except Exception:
        logger.debug("AR/AP enrichment failed", exc_info=True)
        panel["receivables_not_due"] = panel["outstanding_amount"]
        panel["payables_not_due"] = panel["payables_total"]

    # Cash & Bank closing balances
    try:
        from db import get_gl_account_closing_balances
        from mobile_backend.services.ar_ap_service import list_cash_bank_accounts

        bals = get_gl_account_closing_balances() or {}
        accounts = list_cash_bank_accounts() or []
        cash_amt = 0.0
        bank_amt = 0.0
        for acc in accounts:
            code = str(acc.get("code") or "").strip().upper()
            name = str(acc.get("name") or "").strip().upper()
            bal = _to_float(bals.get(code))
            if "BANK" in name or code.startswith("11") and "CASH" not in name:
                bank_amt += bal
            else:
                cash_amt += bal
        # If heuristic empty but we have accounts, put all in bank/cash by name
        if abs(cash_amt) < 1e-9 and abs(bank_amt) < 1e-9 and accounts:
            for acc in accounts:
                code = str(acc.get("code") or "").strip().upper()
                name = str(acc.get("name") or "").strip().upper()
                bal = _to_float(bals.get(code))
                if "CASH" in name or "PETTY" in name:
                    cash_amt += bal
                else:
                    bank_amt += bal
        panel["cash_balance"] = round(cash_amt, 2)
        panel["bank_balance"] = round(bank_amt, 2)
        panel["cash_bank_total"] = round(cash_amt + bank_amt, 2)
    except Exception:
        logger.debug("cash/bank enrichment failed", exc_info=True)

    # Light counts: sales orders + new customers today
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")
        conn = get_connection(tenant_id=tenant_id)
        with conn.cursor() as cur:
            for tbl in ("QUATATIONBILLHDR", "QUOTATIONBILLHDR", "SALESORDERHDR"):
                try:
                    cur.execute(
                        """
                        SELECT COUNT(*) FROM user_tables WHERE table_name = :t
                        """,
                        {"t": tbl},
                    )
                    if int((cur.fetchone() or [0])[0] or 0) <= 0:
                        continue
                    cur.execute(
                        f"""
                        SELECT COUNT(*) FROM {tbl}
                         WHERE TRUNC(BILLDATE) BETWEEN TRUNC(:df) AND TRUNC(:dt)
                        """,
                        {"df": d_from, "dt": d_to},
                    )
                    panel["sales_orders_today"] = int((cur.fetchone() or [0])[0] or 0)
                    break
                except cx_Oracle.DatabaseError:
                    continue
            for tbl in ("CUSTOMER", "CUSTOMERS"):
                try:
                    cur.execute(
                        """
                        SELECT COUNT(*) FROM user_tables WHERE table_name = :t
                        """,
                        {"t": tbl},
                    )
                    if int((cur.fetchone() or [0])[0] or 0) <= 0:
                        continue
                    # Probe created column
                    cur.execute(
                        """
                        SELECT column_name FROM user_tab_columns
                         WHERE table_name = :t
                           AND column_name IN (
                             'CREATEDDATE','CREATED_DATE','CREATED_AT','CREATEDON','ENTRYDATE'
                           )
                        """,
                        {"t": tbl},
                    )
                    col_row = cur.fetchone()
                    if not col_row:
                        break
                    col = str(col_row[0])
                    cur.execute(
                        f"""
                        SELECT COUNT(*) FROM {tbl}
                         WHERE TRUNC({col}) BETWEEN TRUNC(:df) AND TRUNC(:dt)
                        """,
                        {"df": d_from, "dt": d_to},
                    )
                    panel["new_customers_today"] = int((cur.fetchone() or [0])[0] or 0)
                    break
                except cx_Oracle.DatabaseError:
                    continue
    except Exception:
        logger.debug("glance counts enrichment failed", exc_info=True)

    # Trends vs yesterday (sales amount from core today_sales applied by caller)
    panel["invoice_trend_pct"] = _pct_change(
        float(panel["invoice_count"]),
        float(panel["invoice_count_yesterday"]),
    )
    _ = yday_s
    return panel


def get_dashboard_summary(
    *,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    from datetime import date

    d_from = _parse_iso_date(date_from) or date.today()
    d_to = _parse_iso_date(date_to) or d_from
    if d_from > d_to:
        d_from, d_to = d_to, d_from

    claims = get_jwt()
    tenant_id = claims.get("tenant_id")
    conn = get_connection(tenant_id=tenant_id)
    with conn.cursor() as cur:
        total_items, today_sales, customer_count, billhdr_rows_today, sales_debug = _core_counts(
            cur,
        )
        inv = _itemmaster_inventory_stats(cur)
        # Override sales for selected period when not "today only"
        if not (d_from == d_to == date.today()):
            if d_from == d_to:
                today_sales, billhdr_rows_today = _sales_amount_for_day(cur, d_from)
                sales_debug = {"primary_source": "period_day", "date": d_from.isoformat()}
            else:
                # Sum each day is heavy — prefer business summary net_sales below
                sales_debug = {
                    "primary_source": "period_range",
                    "date_from": d_from.isoformat(),
                    "date_to": d_to.isoformat(),
                }

    recent = _recent_receipts_payload(8)
    branch = _branch_info()
    sales_panel = _sales_panel_enrichment(date_from=d_from, date_to=d_to)
    period_sales = _to_float(sales_panel.get("period_sales"))
    if period_sales > 0 and not (d_from == d_to == date.today()):
        today_sales = period_sales
    elif period_sales > 0 and today_sales <= 0:
        today_sales = period_sales

    # Authoritative period sales from live BILLHDR (invoices + sales returns).
    try:
        from mobile_backend.services import sales_invoice_service as sis
        from mobile_backend.services import sales_return_service as srs

        inv_rows = (
            sis.list_invoices(
                date_from=d_from.isoformat(),
                date_to=d_to.isoformat(),
                limit=100,
            )
            or []
        )
        ret_rows = (
            srs.list_returns(
                date_from=d_from.isoformat(),
                date_to=d_to.isoformat(),
                limit=100,
            )
            or []
        )
        list_invoice_sales = round(sum(_to_float(r.get("net_amount")) for r in inv_rows), 2)
        list_return_sales = round(sum(_to_float(r.get("net_amount")) for r in ret_rows), 2)
        # Returns are typically negative NETBILLAMOUNT — net sales = invoices + returns.
        list_sales = round(list_invoice_sales + list_return_sales, 2)
        list_count = len(inv_rows) + len(ret_rows)
        list_cash = round(
            sum(
                _to_float(r.get("net_amount"))
                for r in inv_rows
                if str(r.get("billing_type") or "").upper() != "CREDIT"
            )
            + sum(
                _to_float(r.get("net_amount"))
                for r in ret_rows
                if str(r.get("billing_type") or "").upper() != "CREDIT"
            ),
            2,
        )
        list_credit = round(
            sum(
                _to_float(r.get("net_amount"))
                for r in inv_rows
                if str(r.get("billing_type") or "").upper() == "CREDIT"
            )
            + sum(
                _to_float(r.get("net_amount"))
                for r in ret_rows
                if str(r.get("billing_type") or "").upper() == "CREDIT"
            ),
            2,
        )
        today_sales = list_sales
        billhdr_rows_today = list_count
        sales_debug = {
            **(sales_debug if isinstance(sales_debug, dict) else {}),
            "primary_source": "billhdr",
            "list_sales": list_sales,
            "list_invoice_sales": list_invoice_sales,
            "list_return_sales": list_return_sales,
            "list_count": list_count,
            "list_invoice_count": len(inv_rows),
            "list_return_count": len(ret_rows),
        }
        sales_panel["_list_cash"] = list_cash
        sales_panel["_list_credit"] = list_credit
        sales_panel["_list_invoice_count"] = list_count
        sales_panel["_list_return_sales"] = list_return_sales
        sales_panel["_list_return_count"] = len(ret_rows)
        sales_panel["_list_invoice_sales"] = list_invoice_sales
        # Absolute returns total for KPI / glance (stored positive when nets are negative).
        sales_panel["sales_return"] = round(abs(list_return_sales), 2)
        sales_panel["return_count"] = len(ret_rows)
    except Exception:
        logger.debug("dashboard BILLHDR list_invoices/returns reconcile failed", exc_info=True)

    y_sales = _to_float(sales_panel.get("yesterday_sales"))
    sales_trend = _pct_change(today_sales, y_sales)
    invoice_count = (
        int(sales_panel.get("_list_invoice_count") or 0)
        or int(sales_panel.get("invoice_count") or 0)
        or int(billhdr_rows_today or 0)
    )

    # If BS didn't fill cash/credit, use invoice+return list split (or all cash).
    cash = _to_float(sales_panel.get("cash_sales"))
    credit = _to_float(sales_panel.get("credit_sales"))
    if cash == 0 and credit == 0:
        list_cash = _to_float(sales_panel.get("_list_cash"))
        list_credit = _to_float(sales_panel.get("_list_credit"))
        if list_cash != 0 or list_credit != 0:
            cash, credit = list_cash, list_credit
        elif today_sales != 0:
            cash = today_sales

    inv_value = _to_float(sales_panel.get("inventory_value")) or _to_float(inv["stock_value"])
    in_stock = max(0, int(total_items) - int(inv["out_of_stock_items"] or 0))

    alerts = list(sales_panel.get("alerts") or [])
    if int(inv["low_stock_items"] or 0) > 0:
        alerts.append(
            {
                "severity": "warning",
                "title": f"{int(inv['low_stock_items'])} items below reorder level",
                "subtitle": "Check stock alerts",
            }
        )
    if int(inv["out_of_stock_items"] or 0) > 0:
        alerts.append(
            {
                "severity": "critical",
                "title": f"{int(inv['out_of_stock_items'])} SKUs out of stock",
                "subtitle": "Reorder required",
            }
        )

    # Recent activity from GRNs (+ optional sales stubs)
    activity: list[dict[str, Any]] = []
    for r in recent[:6]:
        activity.append(
            {
                "type": "GRN",
                "title": "Goods Receipt",
                "subtitle": str(r.get("supplier") or r.get("receipt_no") or "").strip(),
                "ref": str(r.get("receipt_no") or "").strip(),
                "time": str(r.get("receipt_date") or "").strip(),
                "amount": round(_to_float(r.get("amount")), 2),
                "signed": -1,
            }
        )
    if sales_panel.get("amount_collected"):
        activity.insert(
            0,
            {
                "type": "Receipt",
                "title": "Payment Received",
                "subtitle": "Customer receipts (today)",
                "ref": "",
                "time": sales_panel.get("as_of") or "",
                "amount": round(_to_float(sales_panel.get("amount_collected")), 2),
                "signed": 1,
            },
        )
    if today_sales:
        activity.insert(
            0,
            {
                "type": "Sales",
                "title": "Sales Invoice",
                "subtitle": f"{invoice_count} invoice(s) today",
                "ref": "",
                "time": sales_panel.get("as_of") or "",
                "amount": round(today_sales, 2),
                "signed": 1,
            },
        )

    return {
        "total_items": total_items,
        "today_sales": today_sales,
        "customer_count": customer_count,
        "billhdr_rows_today": billhdr_rows_today,
        "active_customers": customer_count,
        "total_stock_qty": inv["total_stock_qty"],
        "out_of_stock_items": inv["out_of_stock_items"],
        "low_stock_items": inv["low_stock_items"],
        "stock_value": inv["stock_value"],
        "recent_receipts": recent,
        "today_sales_debug": sales_debug,
        "branch_name": branch["branch_name"],
        "location_name": branch["branch_name"],
        "branch_code": branch["branch_code"],
        "as_of": sales_panel.get("as_of") or "",
        "date_from": d_from.isoformat(),
        "date_to": d_to.isoformat(),
        "period_label": sales_panel.get("period_label") or _period_label(d_from, d_to),
        "yesterday_sales": round(y_sales, 2),
        "sales_trend_pct": sales_trend,
        "invoice_count": invoice_count,
        "invoice_count_yesterday": int(sales_panel.get("invoice_count_yesterday") or 0),
        "invoice_trend_pct": _to_float(sales_panel.get("invoice_trend_pct")),
        "cash_sales": round(cash, 2),
        "credit_sales": round(credit, 2),
        "amount_collected": round(_to_float(sales_panel.get("amount_collected")), 2),
        "outstanding_amount": round(_to_float(sales_panel.get("outstanding_amount")), 2),
        "collection_pct": round(_to_float(sales_panel.get("collection_pct")), 1),
        "sales_return": round(_to_float(sales_panel.get("sales_return")), 2),
        "return_count": int(sales_panel.get("return_count") or 0),
        "sales_orders_today": int(sales_panel.get("sales_orders_today") or 0),
        "new_customers_today": int(sales_panel.get("new_customers_today") or 0),
        "top_customers": sales_panel.get("top_customers") or [],
        # ERP Summary panel
        "purchases": round(_to_float(sales_panel.get("purchases")), 2),
        "expenses": round(_to_float(sales_panel.get("expenses")), 2),
        "gross_profit": round(_to_float(sales_panel.get("gross_profit")), 2),
        "net_profit": round(_to_float(sales_panel.get("net_profit")), 2),
        "purchases_trend_pct": _to_float(sales_panel.get("purchases_trend_pct")),
        "expenses_trend_pct": _to_float(sales_panel.get("expenses_trend_pct")),
        "gross_profit_trend_pct": _to_float(sales_panel.get("gross_profit_trend_pct")),
        "net_profit_trend_pct": _to_float(sales_panel.get("net_profit_trend_pct")),
        "inventory_value": round(inv_value, 2),
        "items_in_stock": in_stock,
        "receivables_overdue": round(_to_float(sales_panel.get("receivables_overdue")), 2),
        "receivables_not_due": round(_to_float(sales_panel.get("receivables_not_due")), 2),
        "payables_total": round(_to_float(sales_panel.get("payables_total")), 2),
        "payables_overdue": round(_to_float(sales_panel.get("payables_overdue")), 2),
        "payables_not_due": round(_to_float(sales_panel.get("payables_not_due")), 2),
        "cash_balance": round(_to_float(sales_panel.get("cash_balance")), 2),
        "bank_balance": round(_to_float(sales_panel.get("bank_balance")), 2),
        "cash_bank_total": round(_to_float(sales_panel.get("cash_bank_total")), 2),
        "recent_activity": activity[:8],
        "alerts": alerts[:8],
        "visits_today": int(sales_panel.get("visits_today") or 0),
    }


def _itemmaster_cols(cur: Any) -> set[str]:
    try:
        cur.execute(
            """
            SELECT column_name
            FROM user_tab_columns
            WHERE table_name = 'ITEMMASTER'
            """
        )
        return {str(row[0]).upper() for row in cur.fetchall() or []}
    except cx_Oracle.DatabaseError:
        return set()


def _list_stock_alert_items(cur: Any, *, kind: str, limit: int = 40) -> list[dict[str, Any]]:
    """Return out-of-stock or below-reorder SKUs from ITEMMASTER."""
    item_cols = _itemmaster_cols(cur)
    if not item_cols:
        return []
    code_col = _pick_existing(item_cols, ["ITEMCODE", "ITEM_CODE", "CODE"])
    name_col = _pick_existing(item_cols, ["ITEMNAME", "ITEM_NAME", "DESCRIPTION", "ITEMDESC"])
    qty_col = _pick_existing(
        item_cols,
        ["CURRENTSTOCK", "CURRENT_STOCK", "QTY_ON_HAND", "STOCK", "QTY", "BALANCEQTY"],
    )
    if not code_col or not qty_col:
        return []
    reorder_col = _pick_existing(
        item_cols,
        ["REORDERLEVEL", "REORDER_LEVEL", "REORDERQTY", "MINQTY", "MIN_STOCK_LEVEL", "MINIMUMQTY"],
    )
    q_expr = f"NVL(i.{qty_col}, 0)"
    if kind == "out_of_stock":
        where = f"{q_expr} <= 0"
    elif kind == "low_stock":
        if not reorder_col:
            return []
        r_expr = f"NVL(i.{reorder_col}, 0)"
        where = f"{r_expr} > 0 AND {q_expr} < {r_expr} AND {q_expr} >= 0"
    else:
        return []

    name_sel = f"i.{name_col}" if name_col else "NULL"
    reorder_sel = f"NVL(i.{reorder_col}, 0)" if reorder_col else "CAST(0 AS NUMBER)"
    lim = max(1, min(int(limit or 40), 100))
    sql = f"""
        SELECT * FROM (
            SELECT TRIM(TO_CHAR(i.{code_col})) AS item_code,
                   {name_sel} AS item_name,
                   {q_expr} AS qty,
                   {reorder_sel} AS reorder_level
              FROM itemmaster i
             WHERE {where}
             ORDER BY {q_expr} ASC, TRIM(TO_CHAR(i.{code_col}))
        ) WHERE ROWNUM <= :lim
    """
    try:
        cur.execute(sql, {"lim": lim})
        rows = cur.fetchall() or []
    except cx_Oracle.DatabaseError:
        return []
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "item_code": str(r[0] or "").strip(),
                "item_name": str(r[1] or "").strip(),
                "qty": round(_to_float(r[2]), 3),
                "reorder_level": round(_to_float(r[3]), 3),
            }
        )
    return out


def get_kpi_detail(
    kpi_id: str,
    *,
    limit: int = 40,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    """Detail payload for a dashboard KPI card tap."""
    from datetime import date, datetime

    key = str(kpi_id or "").strip().lower().replace("-", "_")
    d_from = _parse_iso_date(date_from) or date.today()
    d_to = _parse_iso_date(date_to) or d_from
    if d_from > d_to:
        d_from, d_to = d_to, d_from
    df_s = d_from.isoformat()
    dt_s = d_to.isoformat()
    summary = get_dashboard_summary(date_from=df_s, date_to=dt_s)
    period_label = str(summary.get("period_label") or _period_label(d_from, d_to))
    today = datetime.now().strftime("%Y-%m-%d")
    lim = max(1, min(int(limit or 40), 100))

    meta: dict[str, dict[str, str]] = {
        "today_sales": {
            "title": "Sales",
            "description": (
                f"Sales invoices and sales returns for {period_label}."
            ),
        },
        "purchases": {
            "title": "Purchase",
            "description": (
                f"GRN receipts and purchase returns for {period_label}."
            ),
        },
        "expenses": {
            "title": "Cash Payment",
            "description": (
                f"Posted cash payment voucher amounts for {period_label}."
            ),
        },
        "bills_today": {
            "title": "Bills",
            "description": f"Number of sales invoices and returns for {period_label}.",
        },
        "items": {
            "title": "Items (SKU)",
            "description": "Total SKUs in ITEMMASTER for this branch database.",
        },
        "stock_qty": {
            "title": "Stock on hand",
            "description": "Sum of on-hand quantity across ITEMMASTER.",
        },
        "stock_value": {
            "title": "Stock value",
            "description": "Estimated value = on-hand qty × cost price (ITEMMASTER).",
        },
        "customers": {
            "title": "Customers",
            "description": "Customer master count for this branch database.",
        },
        "out_of_stock": {
            "title": "Out of stock",
            "description": "SKUs with on-hand quantity at or below zero.",
        },
        "low_stock": {
            "title": "Below reorder",
            "description": "SKUs where reorder level is set and on-hand qty is below it.",
        },
        "inventory": {
            "title": "Inventory",
            "description": "Stock value, SKU counts, and stock alerts.",
        },
        "receivables": {
            "title": "Receivables",
            "description": "Customer outstanding balances (AR).",
        },
        "payables": {
            "title": "Payables",
            "description": "Supplier outstanding balances (AP).",
        },
        "cash_bank": {
            "title": "Cash & Bank",
            "description": "Cash and bank account closing balances.",
        },
    }
    if key not in meta:
        raise ValueError(f"Unknown KPI: {kpi_id}")

    value_map = {
        "today_sales": summary.get("today_sales"),
        "purchases": summary.get("purchases"),
        "expenses": summary.get("expenses"),
        "bills_today": summary.get("billhdr_rows_today"),
        "items": summary.get("total_items"),
        "stock_qty": summary.get("total_stock_qty"),
        "stock_value": summary.get("inventory_value") or summary.get("stock_value"),
        "customers": summary.get("customer_count"),
        "out_of_stock": summary.get("out_of_stock_items"),
        "low_stock": summary.get("low_stock_items"),
        "inventory": summary.get("inventory_value") or summary.get("stock_value"),
        "receivables": summary.get("outstanding_amount"),
        "payables": summary.get("payables_total"),
        "cash_bank": summary.get("cash_bank_total"),
    }

    rows: list[dict[str, Any]] = []
    row_kind = "none"
    related = {
        "today_sales": round(_to_float(summary.get("today_sales")), 2),
        "cash_sales": round(_to_float(summary.get("cash_sales")), 2),
        "credit_sales": round(_to_float(summary.get("credit_sales")), 2),
        "sales_return": round(_to_float(summary.get("sales_return")), 2),
        "return_count": int(summary.get("return_count") or 0),
        "purchases": round(_to_float(summary.get("purchases")), 2),
        "purchase_return": 0.0,
        "grn_total": 0.0,
        "expenses": round(_to_float(summary.get("expenses")), 2),
        "cpv_total": 0.0,
        "cpv_count": 0,
        "bills_today": int(summary.get("billhdr_rows_today") or 0),
        "total_items": int(summary.get("total_items") or 0),
        "items_in_stock": int(summary.get("items_in_stock") or 0),
        "customer_count": int(summary.get("customer_count") or 0),
        "total_stock_qty": round(_to_float(summary.get("total_stock_qty")), 3),
        "stock_value": round(_to_float(summary.get("inventory_value") or summary.get("stock_value")), 2),
        "out_of_stock_items": int(summary.get("out_of_stock_items") or 0),
        "low_stock_items": int(summary.get("low_stock_items") or 0),
        "outstanding_amount": round(_to_float(summary.get("outstanding_amount")), 2),
        "receivables_overdue": round(_to_float(summary.get("receivables_overdue")), 2),
        "receivables_not_due": round(_to_float(summary.get("receivables_not_due")), 2),
        "payables_total": round(_to_float(summary.get("payables_total")), 2),
        "payables_overdue": round(_to_float(summary.get("payables_overdue")), 2),
        "payables_not_due": round(_to_float(summary.get("payables_not_due")), 2),
        "cash_balance": round(_to_float(summary.get("cash_balance")), 2),
        "bank_balance": round(_to_float(summary.get("bank_balance")), 2),
        "cash_bank_total": round(_to_float(summary.get("cash_bank_total")), 2),
        "branch_name": str(summary.get("branch_name") or ""),
    }

    def _date_in_range(raw: Any) -> bool:
        d = str(raw or "").strip()[:10]
        if len(d) < 10:
            return False
        return df_s <= d <= dt_s

    if key in ("today_sales", "bills_today"):
        row_kind = "invoices"
        cash_total = 0.0
        credit_total = 0.0
        cash_count = 0
        credit_count = 0
        return_total = 0.0
        return_count = 0
        sales_invoice_total = 0.0
        try:
            from mobile_backend.services import sales_invoice_service as sis
            from mobile_backend.services import sales_return_service as srs

            # Pull enough rows to split cash/credit/returns; UI still shows up to lim per type.
            fetch_lim = max(lim * 2, 80)
            invoices = sis.list_invoices(date_from=df_s, date_to=dt_s, limit=fetch_lim) or []
            returns = srs.list_returns(date_from=df_s, date_to=dt_s, limit=fetch_lim) or []
            for inv in invoices:
                amt = round(_to_float(inv.get("net_amount") or inv.get("netbillamount")), 2)
                sales_invoice_total += amt
                raw_bt = str(inv.get("billing_type") or inv.get("billtype") or "").strip().upper()
                if raw_bt in ("R", "CREDIT") or raw_bt.startswith("R"):
                    billing = "CREDIT"
                    credit_total += amt
                    credit_count += 1
                else:
                    billing = "CASH"
                    cash_total += amt
                    cash_count += 1
                rows.append(
                    {
                        "bill_no": str(inv.get("billno") or "").strip(),
                        "bill_date": str(inv.get("billdate") or "")[:10],
                        "customer_name": str(inv.get("customer_name") or inv.get("customername") or "").strip(),
                        "amount": amt,
                        "billing_type": billing,
                        "doc_kind": "invoice",
                        "status": str(inv.get("status") or inv.get("billstatus") or "").strip(),
                    }
                )
            for ret in returns:
                amt = round(_to_float(ret.get("net_amount") or ret.get("netbillamount")), 2)
                raw_bt = str(ret.get("billing_type") or ret.get("billtype") or "").strip().upper()
                if raw_bt in ("R", "CREDIT") or raw_bt.startswith("R"):
                    billing = "CREDIT"
                else:
                    billing = "CASH"
                return_total += amt
                return_count += 1
                rows.append(
                    {
                        "bill_no": str(ret.get("billno") or "").strip(),
                        "bill_date": str(ret.get("billdate") or "")[:10],
                        "customer_name": str(ret.get("customer_name") or ret.get("customername") or "").strip(),
                        "amount": amt,
                        "billing_type": billing,
                        "doc_kind": "return",
                        "status": str(ret.get("status") or ret.get("billstatus") or "RETURN").strip() or "RETURN",
                    }
                )
        except Exception as exc:
            logger.debug("dashboard kpi invoices/returns: %s", exc)

        # Prefer live invoice split when summary cash/credit is empty or incomplete.
        if cash_total or credit_total or return_total:
            if related["cash_sales"] == 0 and related["credit_sales"] == 0:
                related["cash_sales"] = round(cash_total, 2)
                related["credit_sales"] = round(credit_total, 2)
            elif abs((related["cash_sales"] + related["credit_sales"]) - related["today_sales"]) > 0.05:
                # Keep summary totals if present; still expose invoice-derived counts.
                pass
        related["cash_invoice_count"] = cash_count
        related["credit_invoice_count"] = credit_count
        related["sales_invoice_total"] = round(sales_invoice_total, 2)
        related["sales_return"] = round(abs(return_total), 2) if return_total else related["sales_return"]
        related["return_count"] = return_count or related["return_count"]
        related["return_sales_net"] = round(return_total, 2)
        if key == "today_sales" and related["today_sales"] == 0 and (cash_total or credit_total or return_total):
            related["today_sales"] = round(cash_total + credit_total, 2)
            value_map["today_sales"] = related["today_sales"]
        # Sort newest first (returns + invoices mixed).
        rows.sort(key=lambda r: (str(r.get("bill_date") or ""), str(r.get("bill_no") or "")), reverse=True)
    elif key == "purchases":
        row_kind = "purchases"
        grn_total = 0.0
        grn_count = 0
        pr_total = 0.0
        pr_count = 0
        try:
            from mobile_backend.services import grn_service as grns
            from mobile_backend.services import purchase_return_service as prs

            fetch_lim = max(lim * 2, 80)
            grns_rows = grns.list_receipt_documents(1, fetch_lim, "", inventory_tab="posted") or []
            # Also include draft GRNs so the period is useful while posting.
            try:
                draft_rows = grns.list_receipt_documents(1, fetch_lim, "", inventory_tab="draft") or []
            except Exception:
                draft_rows = []
            for r in list(grns_rows) + list(draft_rows):
                rd = str(r.get("receipt_date") or "")[:10]
                if not _date_in_range(rd):
                    continue
                amt = round(_to_float(r.get("amount")), 2)
                grn_total += amt
                grn_count += 1
                rows.append(
                    {
                        "doc_no": str(r.get("receipt_no") or "").strip(),
                        "doc_date": rd,
                        "party_name": str(r.get("supplier") or "").strip(),
                        "amount": amt,
                        "doc_kind": "grn",
                        "status": str(r.get("status") or "").strip(),
                    }
                )
            pr = prs.list_returns(tab="all", page=1, page_size=fetch_lim) or {}
            for r in pr.get("returns") or []:
                rd = str(r.get("return_date") or "")[:10]
                if not _date_in_range(rd):
                    continue
                amt = round(_to_float(r.get("amount")), 2)
                pr_total += amt
                pr_count += 1
                rows.append(
                    {
                        "doc_no": str(r.get("return_no") or "").strip(),
                        "doc_date": rd,
                        "party_name": str(r.get("supplier_name") or r.get("supplier_code") or "").strip(),
                        "amount": amt,
                        "doc_kind": "purchase_return",
                        "status": str(r.get("approval_status") or "").strip(),
                    }
                )
        except Exception as exc:
            logger.debug("dashboard kpi purchases: %s", exc)

        related["grn_total"] = round(grn_total, 2)
        related["grn_count"] = grn_count
        related["purchase_return"] = round(abs(pr_total), 2)
        related["purchase_return_count"] = pr_count
        if related["purchases"] == 0 and grn_total:
            related["purchases"] = round(grn_total, 2)
            value_map["purchases"] = related["purchases"]
        rows.sort(key=lambda r: (str(r.get("doc_date") or ""), str(r.get("doc_no") or "")), reverse=True)
    elif key == "expenses":
        row_kind = "vouchers"
        cpv_total = 0.0
        cpv_count = 0
        try:
            from mobile_backend.services import cash_payment_voucher_service as cpvs

            payload = cpvs.list_vouchers(status="posted", limit=max(lim * 3, 120)) or {}
            for r in payload.get("vouchers") or []:
                vd = str(r.get("voucher_date") or "")[:10]
                if not _date_in_range(vd):
                    continue
                amt = round(_to_float(r.get("total_amount")), 2)
                cpv_total += amt
                cpv_count += 1
                rows.append(
                    {
                        "doc_no": str(r.get("voucher_no") or "").strip(),
                        "doc_date": vd,
                        "party_name": str(r.get("narration") or r.get("reference_no") or "").strip(),
                        "amount": amt,
                        "doc_kind": "cpv",
                        "status": str(r.get("status") or "").strip(),
                    }
                )
        except Exception as exc:
            logger.debug("dashboard kpi expenses/cpv: %s", exc)

        related["cpv_total"] = round(cpv_total, 2)
        related["cpv_count"] = cpv_count
        related["expenses"] = round(cpv_total, 2)
        value_map["expenses"] = related["expenses"]
        rows.sort(key=lambda r: (str(r.get("doc_date") or ""), str(r.get("doc_no") or "")), reverse=True)
    elif key == "inventory":
        row_kind = "stock_alerts"
        try:
            claims = get_jwt()
            conn = get_connection(tenant_id=claims.get("tenant_id"))
            with conn.cursor() as cur:
                alert_rows = _list_stock_alert_items(cur, kind="low_stock", limit=lim) or []
                for r in alert_rows:
                    rows.append(
                        {
                            "doc_no": str(r.get("item_code") or "").strip(),
                            "doc_date": "",
                            "party_name": str(r.get("item_name") or "").strip(),
                            "amount": _to_float(r.get("qty") or 0),
                            "doc_kind": "stock_alert",
                            "status": "LOW",
                        }
                    )
                if not alert_rows:
                    out_rows = _list_stock_alert_items(cur, kind="out_of_stock", limit=lim) or []
                    for r in out_rows:
                        rows.append(
                            {
                                "doc_no": str(r.get("item_code") or "").strip(),
                                "doc_date": "",
                                "party_name": str(r.get("item_name") or "").strip(),
                                "amount": _to_float(r.get("qty") or 0),
                                "doc_kind": "stock_alert",
                                "status": "OUT",
                            }
                        )
        except Exception as exc:
            logger.debug("dashboard kpi inventory alerts: %s", exc)
        value_map["inventory"] = related["stock_value"]
    elif key == "receivables":
        row_kind = "parties"
        try:
            from mobile_backend.services import ar_ap_service

            ar = ar_ap_service.list_receivables(balance="positive") or {}
            for p in (ar.get("rows") or [])[:lim]:
                if not isinstance(p, dict):
                    continue
                amt = round(_to_float(p.get("balance")), 2)
                rows.append(
                    {
                        "doc_no": str(p.get("party_code") or "").strip(),
                        "doc_date": "",
                        "party_name": str(p.get("party_name") or "").strip(),
                        "amount": amt,
                        "doc_kind": "ar",
                        "status": "OUTSTANDING",
                    }
                )
            totals = ar.get("totals") or {}
            if totals:
                related["outstanding_amount"] = round(
                    _to_float(totals.get("outstanding") or related["outstanding_amount"]),
                    2,
                )
        except Exception as exc:
            logger.debug("dashboard kpi receivables: %s", exc)
        value_map["receivables"] = related["outstanding_amount"]
    elif key == "payables":
        row_kind = "parties"
        try:
            from mobile_backend.services import ar_ap_service

            ap = ar_ap_service.list_payables(balance="positive") or {}
            for p in (ap.get("rows") or [])[:lim]:
                if not isinstance(p, dict):
                    continue
                amt = round(_to_float(p.get("balance")), 2)
                rows.append(
                    {
                        "doc_no": str(p.get("party_code") or "").strip(),
                        "doc_date": "",
                        "party_name": str(p.get("party_name") or "").strip(),
                        "amount": amt,
                        "doc_kind": "ap",
                        "status": "OUTSTANDING",
                    }
                )
            totals = ap.get("totals") or {}
            if totals:
                related["payables_total"] = round(
                    _to_float(totals.get("outstanding") or related["payables_total"]),
                    2,
                )
        except Exception as exc:
            logger.debug("dashboard kpi payables: %s", exc)
        value_map["payables"] = related["payables_total"]
    elif key == "cash_bank":
        row_kind = "accounts"
        try:
            from db import get_gl_account_closing_balances
            from mobile_backend.services.ar_ap_service import list_cash_bank_accounts

            bals = get_gl_account_closing_balances() or {}
            accounts = list_cash_bank_accounts() or []
            for acc in accounts[:lim]:
                code = str(acc.get("code") or "").strip()
                name = str(acc.get("name") or "").strip()
                bal = round(_to_float(bals.get(code.upper()) if code else 0), 2)
                rows.append(
                    {
                        "doc_no": code,
                        "doc_date": "",
                        "party_name": name,
                        "amount": bal,
                        "doc_kind": "gl_account",
                        "status": "BALANCE",
                    }
                )
        except Exception as exc:
            logger.debug("dashboard kpi cash_bank: %s", exc)
        value_map["cash_bank"] = related["cash_bank_total"]
    elif key in ("out_of_stock", "low_stock"):
        row_kind = "items"
        claims = get_jwt()
        conn = get_connection(tenant_id=claims.get("tenant_id"))
        with conn.cursor() as cur:
            rows = _list_stock_alert_items(cur, kind=key, limit=lim)
    elif key == "items":
        row_kind = "stats"
        rows = [
            {"label": "Total SKUs", "value": related["total_items"]},
            {"label": "Out of stock", "value": related["out_of_stock_items"]},
            {"label": "Below reorder", "value": related["low_stock_items"]},
            {"label": "Stock on hand (qty)", "value": related["total_stock_qty"]},
        ]
    elif key in ("stock_qty", "stock_value"):
        row_kind = "stats"
        rows = [
            {"label": "Stock on hand (qty)", "value": related["total_stock_qty"]},
            {"label": "Stock value (est.)", "value": related["stock_value"]},
            {"label": "Total SKUs", "value": related["total_items"]},
            {"label": "Out of stock SKUs", "value": related["out_of_stock_items"]},
            {"label": "Below reorder SKUs", "value": related["low_stock_items"]},
        ]
    elif key == "customers":
        row_kind = "stats"
        rows = [
            {"label": "Customers", "value": related["customer_count"]},
            {"label": "Today's sales", "value": related["today_sales"]},
            {"label": "Bills today", "value": related["bills_today"]},
        ]

    return {
        "kpi_id": key,
        "title": meta[key]["title"],
        "description": meta[key]["description"],
        "value": value_map[key],
        "as_of": today,
        "date_from": df_s,
        "date_to": dt_s,
        "period_label": period_label,
        "branch_name": related["branch_name"],
        "related": related,
        "row_kind": row_kind,
        "rows": rows,
        "row_count": len(rows),
    }
