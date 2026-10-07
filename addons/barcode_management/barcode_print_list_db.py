"""Persisted barcode print-list documents (BARCODE_PRINT_HDR / BARCODE_PRINT_DTL).

Mobile builds the list; ERP Barcode Management opens it by PRINT_NO into the QZ queue.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from db import _get_connection, _safe_rows, _table_exists

_LOG = logging.getLogger("nexa.barcode_print_list")

HDR_TABLE = "BARCODE_PRINT_HDR"
DTL_TABLE = "BARCODE_PRINT_DTL"

LIST_TYPE_PRODUCT = "PRODUCT"
LIST_TYPE_SHELF = "SHELF"
STATUS_DRAFT = "DRAFT"
STATUS_READY = "READY"
STATUS_PRINTED = "PRINTED"


def ensure_barcode_print_list_tables() -> bool:
    """Create print-list header/detail tables when missing."""
    if _table_exists(HDR_TABLE) and _table_exists(DTL_TABLE):
        return True
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM user_tables WHERE table_name = :t",
                    {"t": HDR_TABLE},
                )
                if int((cur.fetchone() or [0])[0] or 0) == 0:
                    cur.execute(
                        f"""
                        CREATE TABLE {HDR_TABLE} (
                            LOCATIONCODE   NUMBER(6) NOT NULL,
                            PRINT_NO       NUMBER(10) NOT NULL,
                            PRINT_DATE     DATE DEFAULT TRUNC(SYSDATE) NOT NULL,
                            LIST_TYPE      VARCHAR2(20) DEFAULT 'PRODUCT' NOT NULL,
                            STATUS         VARCHAR2(20) DEFAULT 'DRAFT' NOT NULL,
                            REMARKS        VARCHAR2(500),
                            SOURCE         VARCHAR2(40),
                            SOURCE_REF     VARCHAR2(80),
                            CREATED_BY     VARCHAR2(50),
                            CREATED_AT     TIMESTAMP(6) DEFAULT SYSTIMESTAMP,
                            UPDATED_BY     VARCHAR2(50),
                            UPDATED_AT     TIMESTAMP(6),
                            CONSTRAINT PK_BARCODE_PRINT_HDR PRIMARY KEY (LOCATIONCODE, PRINT_NO)
                        ) TABLESPACE USERS
                        """
                    )
                cur.execute(
                    "SELECT COUNT(*) FROM user_tables WHERE table_name = :t",
                    {"t": DTL_TABLE},
                )
                if int((cur.fetchone() or [0])[0] or 0) == 0:
                    cur.execute(
                        f"""
                        CREATE TABLE {DTL_TABLE} (
                            LOCATIONCODE   NUMBER(6) NOT NULL,
                            PRINT_NO       NUMBER(10) NOT NULL,
                            LINE_NO        NUMBER(8) NOT NULL,
                            ITEMCODE       NUMBER(12),
                            ITEMNAME       VARCHAR2(200),
                            BARCODE        VARCHAR2(80),
                            UOM            VARCHAR2(20),
                            RETAIL_PRICE   NUMBER(18,6) DEFAULT 0,
                            PRINT_QTY      NUMBER(8) DEFAULT 1 NOT NULL,
                            STORAGE_ID     NUMBER(12),
                            STORAGE_TYPE   VARCHAR2(20),
                            STORAGE_CODE   VARCHAR2(50),
                            STORAGE_NAME   VARCHAR2(200),
                            PATH_TEXT      VARCHAR2(300),
                            CONSTRAINT PK_BARCODE_PRINT_DTL PRIMARY KEY (LOCATIONCODE, PRINT_NO, LINE_NO)
                        ) TABLESPACE USERS
                        """
                    )
                cur.execute(
                    "SELECT COUNT(*) FROM user_indexes WHERE index_name = 'IX_BC_PRINT_HDR_STAT'"
                )
                if int((cur.fetchone() or [0])[0] or 0) == 0:
                    cur.execute(
                        f"CREATE INDEX IX_BC_PRINT_HDR_STAT ON {HDR_TABLE} (STATUS, PRINT_DATE)"
                    )
            conn.commit()
        return True
    except Exception as ex:
        _LOG.error("ensure_barcode_print_list_tables: %s", ex)
        print(f"[ensure_barcode_print_list_tables] {ex}")
        return False


def next_print_no(location_code: int) -> int:
    ensure_barcode_print_list_tables()
    rows = _safe_rows(
        f"""
        SELECT NVL(MAX(PRINT_NO), 0) + 1 AS nxt
        FROM {HDR_TABLE}
        WHERE LOCATIONCODE = :lc
        """,
        {"lc": int(location_code)},
    ) or []
    try:
        return int(rows[0].get("nxt") or 1)
    except (TypeError, ValueError, IndexError, AttributeError):
        return 1


def _clamp_print_qty(raw: Any) -> int:
    try:
        n = int(float(raw))
    except (TypeError, ValueError):
        n = 1
    return max(1, min(999, n))


def _print_list_average_cost(location_code: int, item_code: Any) -> float:
    try:
        from db import get_item_by_code

        ic = int(item_code)
        loc = int(location_code)
    except (TypeError, ValueError):
        return 0.0
    if ic <= 0 or loc <= 0:
        return 0.0
    item = get_item_by_code(ic, loc) or {}
    for key in ('averagecost', 'costprice', 'landingcost'):
        try:
            value = float(item.get(key) or 0)
        except (TypeError, ValueError):
            value = 0.0
        if value > 0:
            return value
    return 0.0


def _print_list_current_stock(location_code: int, item_code: Any) -> float:
    try:
        from db import get_item_by_code

        ic = int(item_code)
        loc = int(location_code)
    except (TypeError, ValueError):
        return 0.0
    if ic <= 0 or loc <= 0:
        return 0.0
    item = get_item_by_code(ic, loc) or {}
    for key in ('currentstock', 'CURRENTSTOCK', 'current_stock'):
        raw = item.get(key)
        if raw is None or raw == '':
            continue
        try:
            return float(raw)
        except (TypeError, ValueError):
            continue
    return 0.0


def list_print_lists(
    location_code: Optional[int] = None,
    *,
    list_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    ensure_barcode_print_list_tables()
    if not _table_exists(HDR_TABLE):
        return []
    try:
        lim = max(1, min(200, int(limit)))
    except (TypeError, ValueError):
        lim = 50
    params: Dict[str, Any] = {"lim": lim}
    where = ["1=1"]
    if location_code is not None and int(location_code) > 0:
        where.append("h.LOCATIONCODE = :lc")
        params["lc"] = int(location_code)
    if list_type:
        where.append("UPPER(TRIM(h.LIST_TYPE)) = :lt")
        params["lt"] = str(list_type).strip().upper()
    if status:
        where.append("UPPER(TRIM(h.STATUS)) = :st")
        params["st"] = str(status).strip().upper()
    where_sql = " AND ".join(where)
    q = f"""
        SELECT * FROM (
            SELECT h.LOCATIONCODE AS locationcode,
                   h.PRINT_NO AS print_no,
                   h.PRINT_DATE AS print_date,
                   h.LIST_TYPE AS list_type,
                   h.STATUS AS status,
                   h.REMARKS AS remarks,
                   h.SOURCE AS source,
                   h.SOURCE_REF AS source_ref,
                   h.CREATED_BY AS created_by,
                   h.CREATED_AT AS created_at,
                   h.UPDATED_BY AS updated_by,
                   h.UPDATED_AT AS updated_at,
                   (SELECT COUNT(*) FROM {DTL_TABLE} d
                     WHERE d.LOCATIONCODE = h.LOCATIONCODE
                       AND d.PRINT_NO = h.PRINT_NO) AS line_count,
                   (SELECT NVL(SUM(d.PRINT_QTY), 0) FROM {DTL_TABLE} d
                     WHERE d.LOCATIONCODE = h.LOCATIONCODE
                       AND d.PRINT_NO = h.PRINT_NO) AS label_count
            FROM {HDR_TABLE} h
            WHERE {where_sql}
            ORDER BY h.PRINT_NO DESC
        ) WHERE ROWNUM <= :lim
    """
    return _safe_rows(q, params) or []


def get_print_list(location_code: int, print_no: int) -> Optional[Dict[str, Any]]:
    """Return header + lines for one document."""
    ensure_barcode_print_list_tables()
    if not _table_exists(HDR_TABLE):
        return None
    try:
        loc = int(location_code)
        pno = int(print_no)
    except (TypeError, ValueError):
        return None
    if loc <= 0 or pno <= 0:
        return None
    hdr_rows = _safe_rows(
        f"""
        SELECT LOCATIONCODE AS locationcode,
               PRINT_NO AS print_no,
               PRINT_DATE AS print_date,
               LIST_TYPE AS list_type,
               STATUS AS status,
               REMARKS AS remarks,
               SOURCE AS source,
               SOURCE_REF AS source_ref,
               CREATED_BY AS created_by,
               CREATED_AT AS created_at,
               UPDATED_BY AS updated_by,
               UPDATED_AT AS updated_at
        FROM {HDR_TABLE}
        WHERE LOCATIONCODE = :lc AND PRINT_NO = :pno
        """,
        {"lc": loc, "pno": pno},
    ) or []
    if not hdr_rows:
        return None
    header = dict(hdr_rows[0])
    lines = _safe_rows(
        f"""
        SELECT LINE_NO AS line_no,
               ITEMCODE AS itemcode,
               ITEMNAME AS itemname,
               BARCODE AS barcode,
               UOM AS uom,
               NVL(RETAIL_PRICE, 0) AS retail_price,
               NVL(PRINT_QTY, 1) AS print_qty,
               STORAGE_ID AS storage_id,
               STORAGE_TYPE AS storage_type,
               STORAGE_CODE AS storage_code,
               STORAGE_NAME AS storage_name,
               PATH_TEXT AS path_text
        FROM {DTL_TABLE}
        WHERE LOCATIONCODE = :lc AND PRINT_NO = :pno
        ORDER BY LINE_NO
        """,
        {"lc": loc, "pno": pno},
    ) or []
    header["lines"] = [dict(r) for r in lines]
    header["line_count"] = len(lines)
    try:
        header["label_count"] = sum(int(r.get("print_qty") or 1) for r in lines)
    except (TypeError, ValueError):
        header["label_count"] = len(lines)
    return header


def get_print_list_label_rows(location_code: int, print_no: int) -> Dict[str, Any]:
    """Shape for ERP barcode-management queue (same keys as GRN load)."""
    doc = get_print_list(location_code, print_no)
    if not doc:
        return {
            "success": False,
            "error": f"Print list {print_no} was not found for this branch.",
            "header": None,
            "rows": [],
        }
    list_type = str(doc.get("list_type") or LIST_TYPE_PRODUCT).strip().upper()
    rows: List[Dict[str, Any]] = []
    for ln in doc.get("lines") or []:
        if list_type == LIST_TYPE_SHELF:
            barcode = str(ln.get("barcode") or ln.get("storage_code") or "").strip()
            if not barcode:
                continue
            rows.append(
                {
                    "itemcode": ln.get("storage_code") or ln.get("storage_id") or "",
                    "itemname": ln.get("storage_name") or ln.get("storage_code") or "",
                    "barcode": barcode,
                    "uom": str(ln.get("storage_type") or "SHELF").strip() or "SHELF",
                    "retailprice": 0,
                    "print_count": _clamp_print_qty(ln.get("print_qty")),
                    "source": "SHELF",
                    "storage_id": ln.get("storage_id"),
                    "path_text": ln.get("path_text") or "",
                }
            )
        else:
            barcode = str(ln.get("barcode") or "").strip()
            if not barcode:
                continue
            rows.append(
                {
                    "itemcode": ln.get("itemcode"),
                    "itemname": ln.get("itemname") or "",
                    "barcode": barcode,
                    "uom": str(ln.get("uom") or "PCS").strip() or "PCS",
                    "retailprice": float(ln.get("retail_price") or 0),
                    "averagecost": _print_list_average_cost(location_code, ln.get("itemcode")),
                    "currentstock": _print_list_current_stock(location_code, ln.get("itemcode")),
                    "print_count": _clamp_print_qty(ln.get("print_qty")),
                    "source": "PRINT_LIST",
                }
            )
    hdr = {
        "print_no": doc.get("print_no"),
        "print_date": doc.get("print_date"),
        "list_type": list_type,
        "status": doc.get("status"),
        "remarks": doc.get("remarks") or "",
        "source": doc.get("source") or "",
        "line_count": doc.get("line_count") or 0,
    }
    return {"success": True, "header": hdr, "rows": rows, "error": None}


def save_print_list(
    location_code: int,
    *,
    print_no: Optional[int] = None,
    list_type: str = LIST_TYPE_PRODUCT,
    status: str = STATUS_READY,
    remarks: str = "",
    source: str = "MOBILE",
    source_ref: str = "",
    created_by: str = "mobile",
    lines: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Insert or replace a print-list document. Returns saved header (+ lines)."""
    ensure_barcode_print_list_tables()
    if not _table_exists(HDR_TABLE) or not _table_exists(DTL_TABLE):
        raise RuntimeError("Barcode print list tables are not available.")

    loc = int(location_code)
    if loc <= 0:
        raise ValueError("locationcode is required.")

    lt = (list_type or LIST_TYPE_PRODUCT).strip().upper()
    if lt not in (LIST_TYPE_PRODUCT, LIST_TYPE_SHELF):
        lt = LIST_TYPE_PRODUCT
    st = (status or STATUS_READY).strip().upper()
    if st not in (STATUS_DRAFT, STATUS_READY, STATUS_PRINTED):
        st = STATUS_READY

    line_rows = list(lines or [])
    if not line_rows:
        raise ValueError("Add at least one line before saving the print list.")

    user = (created_by or "mobile").strip()[:50] or "mobile"
    rem = (remarks or "").strip()[:500]
    src = (source or "MOBILE").strip()[:40]
    sref = (source_ref or "").strip()[:80]

    is_new = print_no is None or int(print_no or 0) <= 0
    pno = next_print_no(loc) if is_new else int(print_no)  # type: ignore[arg-type]

    with _get_connection() as conn:
        with conn.cursor() as cur:
            if not is_new:
                cur.execute(
                    f"SELECT STATUS FROM {HDR_TABLE} WHERE LOCATIONCODE = :lc AND PRINT_NO = :pno",
                    {"lc": loc, "pno": pno},
                )
                existing = cur.fetchone()
                if not existing:
                    raise ValueError(f"Print list {pno} was not found.")
                cur.execute(
                    f"DELETE FROM {DTL_TABLE} WHERE LOCATIONCODE = :lc AND PRINT_NO = :pno",
                    {"lc": loc, "pno": pno},
                )
                cur.execute(
                    f"""
                    UPDATE {HDR_TABLE}
                       SET LIST_TYPE = :lt,
                           STATUS = :st,
                           REMARKS = :rem,
                           SOURCE = :src,
                           SOURCE_REF = :sref,
                           UPDATED_BY = :usr,
                           UPDATED_AT = SYSTIMESTAMP
                     WHERE LOCATIONCODE = :lc AND PRINT_NO = :pno
                    """,
                    {
                        "lt": lt,
                        "st": st,
                        "rem": rem or None,
                        "src": src or None,
                        "sref": sref or None,
                        "usr": user,
                        "lc": loc,
                        "pno": pno,
                    },
                )
            else:
                cur.execute(
                    f"""
                    INSERT INTO {HDR_TABLE} (
                        LOCATIONCODE, PRINT_NO, PRINT_DATE, LIST_TYPE, STATUS,
                        REMARKS, SOURCE, SOURCE_REF, CREATED_BY, CREATED_AT
                    ) VALUES (
                        :lc, :pno, TRUNC(SYSDATE), :lt, :st,
                        :rem, :src, :sref, :usr, SYSTIMESTAMP
                    )
                    """,
                    {
                        "lc": loc,
                        "pno": pno,
                        "lt": lt,
                        "st": st,
                        "rem": rem or None,
                        "src": src or None,
                        "sref": sref or None,
                        "usr": user,
                    },
                )

            for i, raw in enumerate(line_rows, start=1):
                itemcode = raw.get("itemcode")
                try:
                    ic = int(itemcode) if itemcode not in (None, "") else None
                except (TypeError, ValueError):
                    ic = None
                try:
                    sid = int(raw.get("storage_id") or 0) or None
                except (TypeError, ValueError):
                    sid = None
                try:
                    price = float(raw.get("retail_price") or raw.get("retailprice") or 0)
                except (TypeError, ValueError):
                    price = 0.0
                barcode = str(raw.get("barcode") or "").strip()[:80]
                if not barcode and lt == LIST_TYPE_SHELF:
                    barcode = str(raw.get("storage_code") or "").strip()[:80]
                if not barcode:
                    raise ValueError(f"Line {i}: barcode is required.")
                cur.execute(
                    f"""
                    INSERT INTO {DTL_TABLE} (
                        LOCATIONCODE, PRINT_NO, LINE_NO,
                        ITEMCODE, ITEMNAME, BARCODE, UOM, RETAIL_PRICE, PRINT_QTY,
                        STORAGE_ID, STORAGE_TYPE, STORAGE_CODE, STORAGE_NAME, PATH_TEXT
                    ) VALUES (
                        :lc, :pno, :ln,
                        :ic, :iname, :bc, :uom, :rp, :pq,
                        :sid, :stype, :scode, :sname, :path
                    )
                    """,
                    {
                        "lc": loc,
                        "pno": pno,
                        "ln": i,
                        "ic": ic,
                        "iname": str(raw.get("itemname") or "").strip()[:200] or None,
                        "bc": barcode,
                        "uom": str(raw.get("uom") or "PCS").strip()[:20] or "PCS",
                        "rp": price,
                        "pq": _clamp_print_qty(raw.get("print_qty") or raw.get("print_count") or 1),
                        "sid": sid,
                        "stype": str(raw.get("storage_type") or "").strip()[:20] or None,
                        "scode": str(raw.get("storage_code") or "").strip()[:50] or None,
                        "sname": str(raw.get("storage_name") or "").strip()[:200] or None,
                        "path": str(raw.get("path_text") or raw.get("path") or "").strip()[:300] or None,
                    },
                )
        conn.commit()

    saved = get_print_list(loc, pno)
    if not saved:
        raise RuntimeError("Print list was saved but could not be reloaded.")
    return saved


def mark_print_list_status(
    location_code: int,
    print_no: int,
    status: str,
    *,
    updated_by: str = "erp",
) -> bool:
    ensure_barcode_print_list_tables()
    st = (status or "").strip().upper()
    if st not in (STATUS_DRAFT, STATUS_READY, STATUS_PRINTED):
        return False
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    UPDATE {HDR_TABLE}
                       SET STATUS = :st,
                           UPDATED_BY = :usr,
                           UPDATED_AT = SYSTIMESTAMP
                     WHERE LOCATIONCODE = :lc AND PRINT_NO = :pno
                    """,
                    {
                        "st": st,
                        "usr": (updated_by or "erp")[:50],
                        "lc": int(location_code),
                        "pno": int(print_no),
                    },
                )
                ok = cur.rowcount > 0
            conn.commit()
        return ok
    except Exception as ex:
        _LOG.error("mark_print_list_status: %s", ex)
        return False
