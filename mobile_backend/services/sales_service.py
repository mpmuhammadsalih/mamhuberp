"""Mobile sales analytics from BILLHDR / BILLDTL (ERP parity)."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from db.oracle_driver import cx_Oracle

from mobile_backend.database.oracle_pool import get_connection
from mobile_backend.request_context import get_jwt
from mobile_backend.services.dashboard_service import (
    _billhdr_column_names,
    _billhdr_history_column_names,
    _billhdr_history_from_clause,
    _to_float,
)
from mobile_backend.services.inventory_service import _pick_existing

logger = logging.getLogger(__name__)

_DATE_CANDIDATES = [
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
]

_AMT_CANDIDATES = [
    "NETBILLAMOUNT",
    "NET_BILL_AMOUNT",
    "NETAMOUNT",
    "NET_AMOUNT",
    "TOTALAMOUNT",
    "BILLAMOUNT",
    "GROSSAMOUNT",
    "INVOICEAMOUNT",
]

_REDEMPTION_CANDIDATES = [
    "REDEMPTIONAMOUNT",
    "REDEMPTION_AMOUNT",
    "REDEMPTION_AMT",
    "REDEMPTAMOUNT",
]


def _table_columns(cur: Any, table: str) -> frozenset[str]:
    cols: set[str] = set()
    try:
        cur.execute(
            """
            SELECT column_name
              FROM user_tab_columns
             WHERE table_name = :tn
            """,
            {"tn": table.upper()},
        )
        cols.update(str(row[0]).upper() for row in cur.fetchall() or [])
    except cx_Oracle.DatabaseError:
        pass
    if cols:
        return frozenset(cols)
    try:
        cur.execute(
            """
            SELECT DISTINCT column_name
              FROM all_tab_columns
             WHERE table_name = :tn
            """,
            {"tn": table.upper()},
        )
        cols.update(str(row[0]).upper() for row in cur.fetchall() or [])
    except cx_Oracle.DatabaseError:
        pass
    return frozenset(cols)


def _resolve_bill_source(cur: Any) -> tuple[str, frozenset[str]]:
    """Prefer BILLHDRHISTORY when selectable (ERP dashboard parity), else BILLHDR."""
    hist_from = _billhdr_history_from_clause(cur)
    if hist_from:
        hist_cols = _billhdr_history_column_names(cur)
        if hist_cols:
            return hist_from, hist_cols
    bh_cols = _billhdr_column_names(cur)
    return "billhdr b", bh_cols


def _amount_expr(cols: frozenset[str]) -> str | None:
    amt = _pick_existing(cols, _AMT_CANDIDATES)
    if not amt:
        return None
    red = _pick_existing(cols, _REDEMPTION_CANDIDATES)
    if red:
        return f"NVL(b.{amt}, 0) + NVL(b.{red}, 0)"
    return f"NVL(b.{amt}, 0)"


def _resolve_schema(cur: Any) -> dict[str, Any] | None:
    from_clause, cols = _resolve_bill_source(cur)
    date_col = _pick_existing(cols, _DATE_CANDIDATES)
    amt_expr = _amount_expr(cols)
    billno_col = _pick_existing(cols, ["BILLNO", "BILL_NO"])
    cust_col = _pick_existing(cols, ["CUSTOMERCODE", "CUSTOMER_CODE", "CUSTCODE", "CUST_CODE"])
    if not date_col or not amt_expr:
        return None
    return {
        "from_clause": from_clause,
        "cols": cols,
        "date_col": date_col,
        "amt_expr": amt_expr,
        "billno_col": billno_col or "BILLNO",
        "cust_col": cust_col,
    }


def _date_range(days: int) -> tuple[date, date, date, date]:
    """Current period [start, end] and previous period of equal length."""
    end = date.today()
    start = end - timedelta(days=max(1, days) - 1)
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=max(1, days) - 1)
    return start, end, prev_start, prev_end


def _period_aggregate(
    cur: Any,
    schema: dict[str, Any],
    start: date,
    end: date,
) -> dict[str, float | int]:
    amt = schema["amt_expr"]
    dc = schema["date_col"]
    fc = schema["from_clause"]
    sql = f"""
        SELECT NVL(SUM({amt}), 0),
               NVL(COUNT(*), 0),
               NVL(SUM(CASE WHEN {amt} < 0 THEN {amt} ELSE 0 END), 0)
          FROM {fc}
         WHERE TRUNC(b.{dc}) >= :d_from
           AND TRUNC(b.{dc}) <= :d_to
    """
    try:
        cur.execute(sql, {"d_from": start, "d_to": end})
        row = cur.fetchone()
        total = _to_float(row[0]) if row else 0.0
        invoices = int(row[1] or 0) if row else 0
        returns = _to_float(row[2]) if row else 0.0
        avg = total / invoices if invoices else 0.0
        return {
            "total_sales": total,
            "invoice_count": invoices,
            "return_amount": returns,
            "avg_ticket": round(avg, 2),
        }
    except cx_Oracle.DatabaseError as exc:
        logger.debug("sales period aggregate failed: %s", exc)
        return {"total_sales": 0.0, "invoice_count": 0, "return_amount": 0.0, "avg_ticket": 0.0}


def _parse_iso_date(raw: str) -> date | None:
    text = (raw or "").strip()[:10]
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _resolve_report_period(
    days: int,
    date_from: str = "",
    date_to: str = "",
) -> tuple[date, date, date, date, int]:
    """Current period, previous period of equal length, and inclusive day count."""
    start = _parse_iso_date(date_from)
    end = _parse_iso_date(date_to)
    if start and end:
        if start > end:
            start, end = end, start
        span = (end - start).days + 1
        span = max(1, min(span, 366))
        end = start + timedelta(days=span - 1)
        prev_end = start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=span - 1)
        return start, end, prev_start, prev_end, span

    start, end, prev_start, prev_end = _date_range(days)
    return start, end, prev_start, prev_end, max(1, min(int(days or 30), 90))


def _daily_trend(
    cur: Any,
    schema: dict[str, Any],
    start: date,
    end: date,
) -> list[dict[str, Any]]:
    amt = schema["amt_expr"]
    dc = schema["date_col"]
    fc = schema["from_clause"]
    sql = f"""
        SELECT TRUNC(b.{dc}) AS sale_date,
               NVL(SUM({amt}), 0) AS amount,
               COUNT(*) AS invoices
          FROM {fc}
         WHERE TRUNC(b.{dc}) >= :d_from
           AND TRUNC(b.{dc}) <= :d_to
         GROUP BY TRUNC(b.{dc})
         ORDER BY sale_date
    """
    out: list[dict[str, Any]] = []
    try:
        cur.execute(sql, {"d_from": start, "d_to": end})
        for row in cur.fetchall() or []:
            d = row[0]
            if hasattr(d, "strftime"):
                ds = d.strftime("%Y-%m-%d")
            else:
                ds = str(d)[:10]
            out.append(
                {
                    "date": ds,
                    "amount": _to_float(row[1]),
                    "invoices": int(row[2] or 0),
                }
            )
    except cx_Oracle.DatabaseError as exc:
        logger.debug("sales daily trend failed: %s", exc)
    return out


def _week_comparison(cur: Any, schema: dict[str, Any]) -> list[dict[str, Any]]:
    """Last 7 calendar days vs the 7 days before that, aligned Mon–Sun labels."""
    amt = schema["amt_expr"]
    dc = schema["date_col"]
    fc = schema["from_clause"]
    sql = f"""
        SELECT TRUNC(b.{dc}) AS sale_date,
               NVL(SUM({amt}), 0) AS amount
          FROM {fc}
         WHERE TRUNC(b.{dc}) >= TRUNC(SYSDATE) - 13
         GROUP BY TRUNC(b.{dc})
    """
    by_date: dict[str, float] = {}
    try:
        cur.execute(sql)
        for row in cur.fetchall() or []:
            d = row[0]
            if hasattr(d, "strftime"):
                ds = d.strftime("%Y-%m-%d")
            else:
                ds = str(d)[:10]
            by_date[ds] = _to_float(row[1])
    except cx_Oracle.DatabaseError as exc:
        logger.debug("sales week comparison failed: %s", exc)
        return []

    labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    today = date.today()
    out: list[dict[str, Any]] = []
    for offset in range(6, -1, -1):
        cur_day = today - timedelta(days=offset)
        prev_day = cur_day - timedelta(days=7)
        out.append(
            {
                "day": labels[cur_day.weekday()],
                "date": cur_day.isoformat(),
                "current": by_date.get(cur_day.isoformat(), 0.0),
                "previous": by_date.get(prev_day.isoformat(), 0.0),
            }
        )
    return out


def _top_customers(
    cur: Any,
    schema: dict[str, Any],
    start: date,
    end: date,
    limit: int = 5,
) -> list[dict[str, Any]]:
    cust_col = schema.get("cust_col")
    if not cust_col:
        return []

    amt = schema["amt_expr"]
    dc = schema["date_col"]
    fc = schema["from_clause"]

    cust_cols = _table_columns(cur, "CUSTOMER")
    if not cust_cols:
        cust_cols = _table_columns(cur, "CUSTOMERS")
        cust_table = "customers" if cust_cols else None
    else:
        cust_table = "customer"

    if not cust_table or not cust_cols:
        sql = f"""
            SELECT TO_CHAR(b.{cust_col}) AS name,
                   NVL(SUM({amt}), 0) AS amount,
                   COUNT(*) AS invoices
              FROM {fc}
             WHERE TRUNC(b.{dc}) >= :d_from
               AND TRUNC(b.{dc}) <= :d_to
               AND b.{cust_col} IS NOT NULL
             GROUP BY b.{cust_col}
             ORDER BY amount DESC
             FETCH FIRST :lim ROWS ONLY
        """
    else:
        cc = _pick_existing(cust_cols, ["CUSTOMERCODE", "CUSTOMER_CODE", "CUSTCODE", "CODE"])
        name_col = _pick_existing(
            cust_cols,
            ["CUSTOMERNAME", "CUST_NAME", "CUSTOMER_NAME", "NAME"],
        )
        if not cc:
            return []
        name_expr = f"NVL(c.{name_col}, TO_CHAR(b.{cust_col}))" if name_col else f"TO_CHAR(b.{cust_col})"
        sql = f"""
            SELECT {name_expr} AS name,
                   NVL(SUM({amt}), 0) AS amount,
                   COUNT(*) AS invoices
              FROM {fc}
              LEFT JOIN {cust_table} c ON c.{cc} = b.{cust_col}
             WHERE TRUNC(b.{dc}) >= :d_from
               AND TRUNC(b.{dc}) <= :d_to
             GROUP BY {name_expr}
             HAVING NVL(SUM({amt}), 0) > 0
             ORDER BY amount DESC
             FETCH FIRST :lim ROWS ONLY
        """

    out: list[dict[str, Any]] = []
    try:
        cur.execute(sql, {"d_from": start, "d_to": end, "lim": limit})
        for row in cur.fetchall() or []:
            out.append(
                {
                    "name": str(row[0] or "—").strip() or "—",
                    "amount": _to_float(row[1]),
                    "invoices": int(row[2] or 0),
                }
            )
    except cx_Oracle.DatabaseError as exc:
        logger.debug("sales top customers failed: %s", exc)
    return out


def _top_items(
    cur: Any,
    schema: dict[str, Any],
    start: date,
    end: date,
    limit: int = 5,
) -> list[dict[str, Any]]:
    dtl_cols = _table_columns(cur, "BILLDTL")
    if not dtl_cols:
        dtl_cols = _table_columns(cur, "BILLDTLHISTORY")
        dtl_table = "billdtlhistory" if dtl_cols else None
    else:
        dtl_table = "billdtl"

    if not dtl_table or not dtl_cols:
        return []

    hdr_from, hdr_cols = schema["from_clause"], schema["cols"]
    dc = schema["date_col"]
    billno_hdr = _pick_existing(hdr_cols, ["BILLNO", "BILL_NO"])
    billno_dtl = _pick_existing(dtl_cols, ["BILLNO", "BILL_NO"])
    item_col = _pick_existing(dtl_cols, ["ITEMCODE", "ITEM_CODE", "CODE"])
    qty_col = _pick_existing(dtl_cols, ["QTY", "QUANTITY", "BILLQTY", "BILL_QTY"])
    rate_col = _pick_existing(dtl_cols, ["RATE", "SELLRATE", "PRICE", "UNITPRICE"])
    net_col = _pick_existing(
        dtl_cols,
        ["NETAMOUNT", "NET_AMOUNT", "LINEAMOUNT", "AMOUNT", "TOTAL"],
    )

    if not billno_hdr or not billno_dtl or not item_col:
        return []

    if net_col:
        line_amt = f"NVL(d.{net_col}, 0)"
    elif qty_col and rate_col:
        line_amt = f"NVL(d.{qty_col}, 0) * NVL(d.{rate_col}, 0)"
    else:
        line_amt = "0"

    qty_expr = f"NVL(d.{qty_col}, 0)" if qty_col else "0"

    item_cols = _table_columns(cur, "ITEMMASTER")
    item_table = "itemmaster" if item_cols else None
    if item_table and item_cols:
        ic = _pick_existing(item_cols, ["ITEMCODE", "ITEM_CODE", "CODE"])
        name_col = _pick_existing(item_cols, ["ITEMNAME", "ITEMDESC", "ITEM_NAME", "NAME"])
        if ic and name_col:
            name_expr = f"NVL(i.{name_col}, TO_CHAR(d.{item_col}))"
            join_item = f"LEFT JOIN {item_table} i ON i.{ic} = d.{item_col}"
            group_expr = name_expr
        else:
            name_expr = f"TO_CHAR(d.{item_col})"
            join_item = ""
            group_expr = name_expr
    else:
        name_expr = f"TO_CHAR(d.{item_col})"
        join_item = ""
        group_expr = name_expr

    sql = f"""
        SELECT {name_expr} AS name,
               NVL(SUM({qty_expr}), 0) AS qty,
               NVL(SUM({line_amt}), 0) AS amount
          FROM {dtl_table} d
         INNER JOIN {hdr_from} ON d.{billno_dtl} = b.{billno_hdr}
         {join_item}
         WHERE TRUNC(b.{dc}) >= :d_from
           AND TRUNC(b.{dc}) <= :d_to
         GROUP BY {group_expr}
         HAVING NVL(SUM({line_amt}), 0) > 0
         ORDER BY amount DESC
         FETCH FIRST :lim ROWS ONLY
    """

    out: list[dict[str, Any]] = []
    try:
        cur.execute(sql, {"d_from": start, "d_to": end, "lim": limit})
        for row in cur.fetchall() or []:
            out.append(
                {
                    "name": str(row[0] or "—").strip() or "—",
                    "qty": _to_float(row[1]),
                    "amount": _to_float(row[2]),
                }
            )
    except cx_Oracle.DatabaseError as exc:
        logger.debug("sales top items failed: %s", exc)
    return out


def _pct_change(current: float, previous: float) -> float | None:
    if previous == 0:
        return None if current == 0 else 100.0
    return round(((current - previous) / abs(previous)) * 100.0, 1)


def get_sales_reports(
    days: int = 30,
    date_from: str = "",
    date_to: str = "",
) -> dict[str, Any]:
    """Aggregate sales analytics for mobile charts."""
    start, end, prev_start, prev_end, period_days = _resolve_report_period(days, date_from, date_to)

    claims = get_jwt()
    tenant_id = claims.get("tenant_id")
    conn = get_connection(tenant_id=tenant_id)

    with conn.cursor() as cur:
        schema = _resolve_schema(cur)
        if not schema:
            return {
                "period_days": period_days,
                "date_from": start.isoformat(),
                "date_to": end.isoformat(),
                "error": "Sales tables not available for this tenant.",
                "summary": {},
                "daily_trend": [],
                "week_comparison": [],
                "top_customers": [],
                "top_items": [],
            }

        current = _period_aggregate(cur, schema, start, end)
        previous = _period_aggregate(cur, schema, prev_start, prev_end)
        today_start = date.today()
        today = _period_aggregate(cur, schema, today_start, today_start)

        summary = {
            **current,
            "today_sales": today["total_sales"],
            "today_invoices": today["invoice_count"],
            "prev_period_sales": previous["total_sales"],
            "prev_invoice_count": previous["invoice_count"],
            "sales_change_pct": _pct_change(current["total_sales"], previous["total_sales"]),
            "invoice_change_pct": _pct_change(
                float(current["invoice_count"]),
                float(previous["invoice_count"]),
            ),
        }

        return {
            "period_days": period_days,
            "date_from": start.isoformat(),
            "date_to": end.isoformat(),
            "prev_date_from": prev_start.isoformat(),
            "prev_date_to": prev_end.isoformat(),
            "summary": summary,
            "daily_trend": _daily_trend(cur, schema, start, end),
            "week_comparison": _week_comparison(cur, schema),
            "top_customers": _top_customers(cur, schema, start, end, 5),
            "top_items": _top_items(cur, schema, start, end, 5),
        }
