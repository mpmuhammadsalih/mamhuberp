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
    Today sales and today's bill row count.

    **Primary (Nexa Dynamics parity)** when selectable: ``BILLHDRHISTORY``, same as ERP web —
    ``NVL(SUM(NVL(NETBILLAMOUNT,0)),0)`` with ``TRUNC(BILLDATE)=TRUNC(SYSDATE)``.

    Falls back to live **BILLHDR** probes and dynamic amount columns when history is unavailable.

    Returns:
        tuple of (today_sales_amount, rows_today, debug_dict).

    Oracle NUMBER aggregates are normalized with `_to_float` (Decimal-safe).
    """
    hist = _try_today_from_billhdrhistory(cur)
    if hist is not None:
        return hist

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


def get_dashboard_summary() -> dict:
    claims = get_jwt()
    tenant_id = claims.get("tenant_id")
    conn = get_connection(tenant_id=tenant_id)
    with conn.cursor() as cur:
        total_items, today_sales, customer_count, billhdr_rows_today, sales_debug = _core_counts(
            cur,
        )
        inv = _itemmaster_inventory_stats(cur)

    recent = _recent_receipts_payload(8)
    branch = _branch_info()

    return {
        "total_items": total_items,
        "today_sales": today_sales,
        "customer_count": customer_count,
        "billhdr_rows_today": billhdr_rows_today,
        # Kept for older clients / cache
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


def get_kpi_detail(kpi_id: str, *, limit: int = 40) -> dict[str, Any]:
    """Detail payload for a dashboard KPI card tap."""
    from datetime import datetime

    key = str(kpi_id or "").strip().lower().replace("-", "_")
    summary = get_dashboard_summary()
    today = datetime.now().strftime("%Y-%m-%d")
    lim = max(1, min(int(limit or 40), 100))

    meta: dict[str, dict[str, str]] = {
        "today_sales": {
            "title": "Today's sales",
            "description": "Net sales amount posted for today (BILLHDR / BILLHDRHISTORY).",
        },
        "bills_today": {
            "title": "Bills today",
            "description": "Number of sales invoices dated today.",
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
    }
    if key not in meta:
        raise ValueError(f"Unknown KPI: {kpi_id}")

    value_map = {
        "today_sales": summary.get("today_sales"),
        "bills_today": summary.get("billhdr_rows_today"),
        "items": summary.get("total_items"),
        "stock_qty": summary.get("total_stock_qty"),
        "stock_value": summary.get("stock_value"),
        "customers": summary.get("customer_count"),
        "out_of_stock": summary.get("out_of_stock_items"),
        "low_stock": summary.get("low_stock_items"),
    }

    rows: list[dict[str, Any]] = []
    row_kind = "none"
    related = {
        "today_sales": round(_to_float(summary.get("today_sales")), 2),
        "bills_today": int(summary.get("billhdr_rows_today") or 0),
        "total_items": int(summary.get("total_items") or 0),
        "customer_count": int(summary.get("customer_count") or 0),
        "total_stock_qty": round(_to_float(summary.get("total_stock_qty")), 3),
        "stock_value": round(_to_float(summary.get("stock_value")), 2),
        "out_of_stock_items": int(summary.get("out_of_stock_items") or 0),
        "low_stock_items": int(summary.get("low_stock_items") or 0),
        "branch_name": str(summary.get("branch_name") or ""),
    }

    if key in ("today_sales", "bills_today"):
        row_kind = "invoices"
        try:
            from mobile_backend.services import sales_invoice_service as sis

            invoices = sis.list_invoices(date_from=today, date_to=today, limit=lim) or []
            for inv in invoices:
                rows.append(
                    {
                        "bill_no": str(inv.get("billno") or "").strip(),
                        "bill_date": str(inv.get("billdate") or "")[:10],
                        "customer_name": str(inv.get("customer_name") or "").strip(),
                        "amount": round(_to_float(inv.get("net_amount")), 2),
                        "billing_type": str(inv.get("billing_type") or "").strip(),
                    }
                )
        except Exception as exc:
            logger.debug("dashboard kpi invoices: %s", exc)
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
        "branch_name": related["branch_name"],
        "related": related,
        "row_kind": row_kind,
        "rows": rows,
        "row_count": len(rows),
    }
