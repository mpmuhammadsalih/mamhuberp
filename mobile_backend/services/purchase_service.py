from __future__ import annotations

import threading
from datetime import datetime
from typing import Any

from mobile_backend.request_context import get_jwt

from mobile_backend.config import Config
from mobile_backend.database.oracle_pool import get_connection
from mobile_backend.database.transaction import oracle_transaction
from mobile_backend.database.mobile_ext_schema import maybe_create_grn_mobile_line_ext
from mobile_backend.operation_lock import mobile_operation_lock

_CACHE_LOCK = threading.Lock()
_ORACLE_USER_BY_CONN_ID: dict[int, str] = {}
_TABLE_COLUMNS_CACHE: dict[tuple[str, str], frozenset[str]] = {}
_TABLE_EXISTS_CACHE: dict[tuple[str, str], bool] = {}


def _oracle_username_upper(cur: Any) -> str:
    cid = id(cur.connection)
    with _CACHE_LOCK:
        cached = _ORACLE_USER_BY_CONN_ID.get(cid)
    if cached is not None:
        return cached
    cur.execute("SELECT USER FROM DUAL")
    row = cur.fetchone()
    u = str((row or [""])[0] or "").strip().upper()
    with _CACHE_LOCK:
        _ORACLE_USER_BY_CONN_ID[cid] = u
    return u


def _pick_existing(columns: set[str], candidates: list[str]) -> str | None:
    for name in candidates:
        if name.upper() in columns:
            return name.upper()
    return None


def _table_exists(cur: Any, table_name: str) -> bool:
    t = table_name.upper()
    key = (_oracle_username_upper(cur), t)
    with _CACHE_LOCK:
        hit = _TABLE_EXISTS_CACHE.get(key)
    if hit is not None:
        return hit
    cur.execute(
        """
        SELECT COUNT(*)
        FROM user_tables
        WHERE table_name = :table_name
        """,
        {"table_name": t},
    )
    ok = int(cur.fetchone()[0] or 0) > 0
    with _CACHE_LOCK:
        _TABLE_EXISTS_CACHE[key] = ok
    return ok


def _table_columns(cur: Any, table_name: str) -> set[str]:
    t = table_name.upper()
    key = (_oracle_username_upper(cur), t)
    with _CACHE_LOCK:
        hit = _TABLE_COLUMNS_CACHE.get(key)
    if hit is not None:
        return set(hit)
    cur.execute(
        """
        SELECT column_name
        FROM user_tab_columns
        WHERE table_name = :table_name
        """,
        {"table_name": t},
    )
    cols = frozenset(str(row[0]).upper() for row in cur.fetchall() or [])
    with _CACHE_LOCK:
        _TABLE_COLUMNS_CACHE[key] = cols
    return set(cols)


def _first_existing_table(cur: Any, candidates: list[str]) -> str:
    for name in candidates:
        if _table_exists(cur, name):
            return name.upper()
    return ""


def _fetch_lpodtl_list_totals_batch(
    cur: Any,
    *,
    dtl_tbl: str,
    dtl_lpo_col: str,
    qty_col: str | None,
    rate_col: str | None,
    lp_keys: list[str],
) -> tuple[dict[str, float], dict[str, float]]:
    """Aggregate ordered-qty and extended amount per LP key for the GRN list screen (batched IN lists)."""
    qty_by: dict[str, float] = {}
    amt_by: dict[str, float] = {}
    keys = sorted({str(k).strip() for k in lp_keys if str(k).strip()})
    if not keys or not qty_col:
        return qty_by, amt_by
    chunk_size = 900
    amt_expr = (
        f"NVL(SUM(NVL(d.{qty_col}, 0) * NVL(d.{rate_col}, 0)), 0)"
        if rate_col
        else "CAST(0 AS NUMBER)"
    )
    for idx in range(0, len(keys), chunk_size):
        chunk = keys[idx : idx + chunk_size]
        binds = {f"k{i}": chunk[i] for i in range(len(chunk))}
        ph = ", ".join(f":k{i}" for i in range(len(chunk)))
        cur.execute(
            f"""
            SELECT TRIM(TO_CHAR(d.{dtl_lpo_col})),
                   NVL(SUM(NVL(d.{qty_col}, 0)), 0),
                   {amt_expr}
              FROM {dtl_tbl} d
             WHERE TRIM(TO_CHAR(d.{dtl_lpo_col})) IN ({ph})
             GROUP BY TRIM(TO_CHAR(d.{dtl_lpo_col}))
            """,
            binds,
        )
        for row in cur.fetchall() or []:
            lk = str(row[0] or "").strip()
            if not lk:
                continue
            qty_by[lk] = float(row[1] or 0)
            amt_by[lk] = float(row[2] or 0)
    return qty_by, amt_by


def _resolve_lpo_tables(cur: Any) -> tuple[str, str]:
    header_table = "LPOHDR" if _table_exists(cur, "LPOHDR") else ""
    detail_table = "LPODTL" if _table_exists(cur, "LPODTL") else ""
    if not header_table or not detail_table:
        raise ValueError("LPOHDR/LPODTL tables not found in this tenant database")
    return header_table, detail_table


def _resolve_receipt_tables(cur: Any) -> tuple[str, str]:
    header_table = "RECEIPTHDR" if _table_exists(cur, "RECEIPTHDR") else ""
    detail_table = "RECEIPTDTL" if _table_exists(cur, "RECEIPTDTL") else ""
    if not header_table or not detail_table:
        raise ValueError("RECEIPTHDR/RECEIPTDTL tables not found in this tenant database")
    return header_table, detail_table


def _pick_lpohdr_mobile_grn_status_col(hdr_cols: set[str]) -> str | None:
    custom = getattr(Config, "LPOHDR_GRN_STATUS_COLUMN", "") or ""
    custom = custom.strip().upper()
    candidates: list[str] = []
    if custom:
        candidates.append(custom)
    candidates.extend(["NEXA_GRN_STATUS", "MOBILE_GRN_STATUS"])
    return _pick_existing(hdr_cols, candidates)


def _mobile_grn_column_is_completed(raw: Any) -> bool:
    v = str(raw or "").strip().upper()
    return v in ("COMPLETED", "COMPLETE", "C", "DONE")


def _lpodtl_stable_order_exprs(dtl_item_col: str) -> tuple[str, str]:
    """ORDER BY snippets for deterministic line numbering (enumerate + PATCH)."""
    item_order = f"TO_CHAR(d.{dtl_item_col})"
    return item_order, f"{item_order}, d.ROWID"


def _pick_lpodtl_ordered_qty_col(dtl_cols: set[str]) -> str | None:
    """PO line ordered qty (not mobile/ERP received)."""
    return _pick_existing(
        dtl_cols,
        ["QUANTITY", "QTY", "ORDERQTY", "ORDER_QTY", "ORDEREDQTY", "POQTY", "BASEQTY"],
    )


def _pick_lpodtl_received_qty_col(dtl_cols: set[str]) -> str | None:
    """Qty already received on LPODTL (e.g. INQUANTITY)."""
    return _pick_existing(
        dtl_cols,
        [
            "INQUANTITY",
            "IN_INV_QTY",
            "ININV_QTY",
            "IN_QTY",
            "RECEIVEDQTY",
            "RECEIVED_QTY",
            "RCVQTY",
            "RCV_QTY",
            "GRNQTY",
            "GRN_QTY",
        ],
    )


_GRN_MOBILE_LINE_EXT_TBL = "GRN_MOBILE_LINE_EXT"


def _coerce_grn_mobile_ext_location_id(raw: Any) -> int:
    """Numeric LOCATIONCODE for GRN_MOBILE_LINE_EXT; 0 = unset / whole-number only."""
    if raw is None:
        return 0
    if isinstance(raw, bool):
        return 0
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        return int(raw)
    s = str(raw).strip()
    if not s:
        return 0
    try:
        if "." in s:
            return int(float(s))
        return int(s)
    except (TypeError, ValueError):
        return 0


def _oracle_date_value_to_mobile_str(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, datetime):
        m = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        return f"{m[val.month - 1]} {val.day}, {val.year}"
    return str(val)


def _apply_grn_mobile_line_ext_overlay(
    cur: Any,
    lpo_no: str,
    items: list[dict[str, Any]],
    *,
    overlay_claims_loc: Any = "",
    hdr_location_code: Any = "",
) -> None:
    """Merge GRN_MOBILE_LINE_EXT snapshots into LPODTL-backed item dicts."""
    if not items or not _table_exists(cur, _GRN_MOBILE_LINE_EXT_TBL):
        return
    ext_cols = _table_columns(cur, _GRN_MOBILE_LINE_EXT_TBL)
    loc_nm = _pick_existing(ext_cols, ["LOCATIONCODE", "LOCATION_CODE", "LOC_CODE"])
    eff_raw = overlay_claims_loc if str(overlay_claims_loc or "").strip() else hdr_location_code
    binds: dict[str, Any] = {"lpo": str(lpo_no)}
    location_filter_sql = ""
    if loc_nm:
        binds["ext_loc"] = _coerce_grn_mobile_ext_location_id(eff_raw)
        location_filter_sql = f" AND NVL(tgt.{loc_nm}, 0) = NVL(:ext_loc, 0)"

    loc_sel = f", tgt.{loc_nm}" if loc_nm else ""
    sql = f"""
        SELECT tgt.LINE_SEQ, NVL(tgt.RECEIVED_QTY, 0), NVL(tgt.BONUS_QTY, 0),
               NVL(TRIM(tgt.FOC_FLAG), 'N'), NVL(tgt.BONUS_BASE_UNIT, 0),
               tgt.BATCH_NO, tgt.EXPIRY_DATE, tgt.STORE_CODE, tgt.BIN_CODE
               {loc_sel}
          FROM {_GRN_MOBILE_LINE_EXT_TBL} tgt
         WHERE tgt.LPO_NO = :lpo
               {location_filter_sql}
        """
    cur.execute(sql, binds)
    by_seq: dict[int, tuple[Any, ...]] = {}
    for row in cur.fetchall() or []:
        seq = int(row[0] or 0)
        if seq > 0:
            by_seq[seq] = row

    loc_idx = 9 if loc_nm else None
    for it in items:
        seq = int(it.get("line_seq") or 0)
        row = by_seq.get(seq)
        if not row:
            continue
        foc = str(row[3] or "").strip().upper() in ("Y", "1", "T")
        it["mobile_received_qty"] = float(row[1] or 0)
        it["mobile_bonus_qty"] = float(row[2] or 0)
        it["mobile_foc"] = foc
        it["mobile_bonus_base_unit"] = float(row[4] or 0)
        it["mobile_batch_no"] = str(row[5] or "").strip()
        it["mobile_expiry"] = _oracle_date_value_to_mobile_str(row[6])
        it["mobile_store"] = str(row[7] or "").strip()
        it["mobile_bin"] = str(row[8] or "").strip()
        if loc_idx is not None:
            try:
                it["LOCATIONCODE"] = int(row[loc_idx] or 0)
            except (TypeError, ValueError):
                it["LOCATIONCODE"] = _coerce_grn_mobile_ext_location_id(row[loc_idx])


def _merge_grn_mobile_line_ext(
    cur: Any,
    *,
    po_no: str,
    line_seq: int,
    item_code: str,
    received_qty: float,
    bonus_qty: float,
    foc_enabled: bool,
    bonus_base_unit: float | None,
    batch_no: str,
    expiry_raw: str,
    store_code: str,
    bin_code: str,
    updated_by: str | None,
    location_code_hint: Any = "",
) -> None:
    ext_cols = _table_columns(cur, _GRN_MOBILE_LINE_EXT_TBL)
    loc_col = _pick_existing(ext_cols, ["LOCATIONCODE", "LOCATION_CODE", "LOC_CODE"])

    foc_flag_chr = "Y" if foc_enabled else "N"
    bb = bonus_base_unit
    raw_exp = str(expiry_raw or "").strip()
    expiry_dt = _parse_mobile_expiry(raw_exp) if raw_exp else None

    binds: dict[str, Any] = {
        "po_no": str(po_no).strip(),
        "line_seq": int(line_seq),
        "item_code": str(item_code).strip(),
        "received_qty": received_qty,
        "bonus_qty": bonus_qty,
        "foc_flag": foc_flag_chr,
        "bonus_base_unit": float(bb if bb is not None else 0),
        "batch_no": batch_no.strip() or None,
        "expiry_date": expiry_dt,
        "store_code": store_code.strip() or None,
        "bin_code": bin_code.strip() or None,
        "updated_by": updated_by,
    }

    if loc_col:
        binds["grn_mobile_loc"] = _coerce_grn_mobile_ext_location_id(location_code_hint)
        merge_sql = f"""
            MERGE INTO {_GRN_MOBILE_LINE_EXT_TBL} tgt
            USING (
                SELECT :po_no AS LPO_NO,
                       :grn_mobile_loc AS {loc_col},
                       :line_seq AS LINE_SEQ,
                       :item_code AS ITEM_CODE
                  FROM DUAL
            ) src
               ON (
                    tgt.LPO_NO = src.LPO_NO
                AND tgt.LINE_SEQ = src.LINE_SEQ
                AND NVL(tgt.{loc_col}, 0) = NVL(src.{loc_col}, 0)
               )
            WHEN MATCHED THEN
                UPDATE SET
                    tgt.ITEM_CODE = src.ITEM_CODE,
                    tgt.RECEIVED_QTY = :received_qty,
                    tgt.BONUS_QTY = :bonus_qty,
                    tgt.FOC_FLAG = :foc_flag,
                    tgt.BONUS_BASE_UNIT = :bonus_base_unit,
                    tgt.BATCH_NO = :batch_no,
                    tgt.EXPIRY_DATE = :expiry_date,
                    tgt.STORE_CODE = :store_code,
                    tgt.BIN_CODE = :bin_code,
                    tgt.UPDATED_BY = :updated_by,
                    tgt.UPDATED_AT = SYSDATE
            WHEN NOT MATCHED THEN
                INSERT (
                    LPO_NO, {loc_col}, LINE_SEQ, ITEM_CODE, RECEIVED_QTY, BONUS_QTY, FOC_FLAG,
                    BONUS_BASE_UNIT, BATCH_NO, EXPIRY_DATE, STORE_CODE, BIN_CODE,
                    UPDATED_BY, UPDATED_AT
                )
                VALUES (
                    :po_no,
                    :grn_mobile_loc,
                    :line_seq,
                    :item_code,
                    :received_qty,
                    :bonus_qty,
                    :foc_flag,
                    :bonus_base_unit,
                    :batch_no,
                    :expiry_date,
                    :store_code,
                    :bin_code,
                    :updated_by,
                    SYSDATE
                )
        """
        cur.execute(merge_sql, binds)
        return

    merge_sql = f"""
        MERGE INTO {_GRN_MOBILE_LINE_EXT_TBL} tgt
        USING (
            SELECT :po_no AS LPO_NO,
                   :line_seq AS LINE_SEQ,
                   :item_code AS ITEM_CODE
              FROM DUAL
        ) src
           ON (
                tgt.LPO_NO = src.LPO_NO
            AND tgt.LINE_SEQ = src.LINE_SEQ
           )
        WHEN MATCHED THEN
            UPDATE SET
                tgt.ITEM_CODE = src.ITEM_CODE,
                tgt.RECEIVED_QTY = :received_qty,
                tgt.BONUS_QTY = :bonus_qty,
                tgt.FOC_FLAG = :foc_flag,
                tgt.BONUS_BASE_UNIT = :bonus_base_unit,
                tgt.BATCH_NO = :batch_no,
                tgt.EXPIRY_DATE = :expiry_date,
                tgt.STORE_CODE = :store_code,
                tgt.BIN_CODE = :bin_code,
                tgt.UPDATED_BY = :updated_by,
                tgt.UPDATED_AT = SYSDATE
        WHEN NOT MATCHED THEN
            INSERT (
                LPO_NO, LINE_SEQ, ITEM_CODE, RECEIVED_QTY, BONUS_QTY, FOC_FLAG,
                BONUS_BASE_UNIT, BATCH_NO, EXPIRY_DATE, STORE_CODE, BIN_CODE,
                UPDATED_BY, UPDATED_AT
            )
            VALUES (
                :po_no,
                :line_seq,
                :item_code,
                :received_qty,
                :bonus_qty,
                :foc_flag,
                :bonus_base_unit,
                :batch_no,
                :expiry_date,
                :store_code,
                :bin_code,
                :updated_by,
                SYSDATE
            )
    """
    cur.execute(merge_sql, binds)


def _derive_po_status(del_flag: str, lr_flag: str, approval_status: str) -> str:
    """LPO row status from ERP header fields + approval (``R`` means received). Boost with LPOHDR mobile GRN column in list/detail/PATCH."""
    del_norm = (del_flag or "").strip().upper()
    lr_norm = (lr_flag or "").strip().upper()
    approval_norm = (approval_status or "").strip().upper()
    # Existing ERP behavior:
    # - cancelled from approval txn OR delflag
    # - completed when LRFLAG is R (received)
    # - otherwise pending/open
    if del_norm == "Y" or approval_norm == "CANCELLED":
        return "Cancelled"
    if lr_norm == "R":
        return "Completed"
    return "Pending"


def _started_receiving_lpo_keys(
    cur: Any,
    *,
    dtl_tbl: str,
    dtl_lpo_col: str | None,
    candidate_lp_keys: list[str],
) -> set[str]:
    """
    LP keys (trimmed receipt / LPO id as returned in list API) where receiving has visibly started:
    rows in GRN_MOBILE_LINE_EXT and/or LPODTL received qty > 0.
    """
    out: set[str] = set()
    keys = sorted({str(k).strip() for k in candidate_lp_keys if str(k).strip()})
    if not keys:
        return out
    chunk_size = 900
    binds: dict[str, Any]

    if _table_exists(cur, _GRN_MOBILE_LINE_EXT_TBL):
        ext_cols = _table_columns(cur, _GRN_MOBILE_LINE_EXT_TBL)
        lpo_ext_col = _pick_existing(ext_cols, ["LPO_NO"])
        if lpo_ext_col:
            for idx in range(0, len(keys), chunk_size):
                chunk = keys[idx : idx + chunk_size]
                binds = {f"p{i}": chunk[i] for i in range(len(chunk))}
                ph = ", ".join(f":p{i}" for i in range(len(chunk)))
                cur.execute(
                    f"""
                    SELECT DISTINCT TRIM(TO_CHAR(e.{lpo_ext_col}))
                      FROM {_GRN_MOBILE_LINE_EXT_TBL} e
                     WHERE TRIM(TO_CHAR(e.{lpo_ext_col})) IN ({ph})
                    """,
                    binds,
                )
                for row in cur.fetchall() or []:
                    k = str(row[0] or "").strip()
                    if k:
                        out.add(k)

    if dtl_tbl and dtl_lpo_col:
        d_cols = _table_columns(cur, dtl_tbl)
        recv_col = _pick_existing(
            d_cols,
            ["RECEIVEDQTY", "RECEIVED_QTY", "RCVQTY", "RCV_QTY", "GRNQTY", "GRN_QTY", "RCVDQTY"],
        )
        if recv_col:
            for idx in range(0, len(keys), chunk_size):
                chunk = keys[idx : idx + chunk_size]
                binds = {f"q{i}": chunk[i] for i in range(len(chunk))}
                ph = ", ".join(f":q{i}" for i in range(len(chunk)))
                cur.execute(
                    f"""
                    SELECT DISTINCT TRIM(TO_CHAR(d.{dtl_lpo_col}))
                      FROM {dtl_tbl} d
                     WHERE NVL(d.{recv_col}, 0) > 0
                       AND TRIM(TO_CHAR(d.{dtl_lpo_col})) IN ({ph})
                    """,
                    binds,
                )
                for row in cur.fetchall() or []:
                    k = str(row[0] or "").strip()
                    if k:
                        out.add(k)

        inq_col = _pick_existing(
            d_cols,
            ["INQUANTITY", "IN_INV_QTY", "ININV_QTY", "IN_QTY"],
        )
        if inq_col:
            for idx in range(0, len(keys), chunk_size):
                chunk = keys[idx : idx + chunk_size]
                binds_i = {f"i{i}": chunk[i] for i in range(len(chunk))}
                ph_i = ", ".join(f":i{i}" for i in range(len(chunk)))
                cur.execute(
                    f"""
                    SELECT DISTINCT TRIM(TO_CHAR(d.{dtl_lpo_col}))
                      FROM {dtl_tbl} d
                     WHERE NVL(d.{inq_col}, 0) > 0
                       AND TRIM(TO_CHAR(d.{dtl_lpo_col})) IN ({ph_i})
                    """,
                    binds_i,
                )
                for row in cur.fetchall() or []:
                    k = str(row[0] or "").strip()
                    if k:
                        out.add(k)

    return out


def _lr_flag_is_partial_receive(lr_flag: str) -> bool:
    """Header LRFLAG implies partial receipt (see Config.LRFLAG_PARTIAL_VALUES; never match generic Pending 'P')."""
    lr = (lr_flag or "").strip().upper()
    if not lr or lr == "R":
        return False
    return lr in Config.LRFLAG_PARTIAL_VALUES


def _aggregate_mobile_receiving_touch(
    cur: Any,
    *,
    dtl_tbl: str | None,
    dtl_lpo_col: str | None,
    lp_keys: list[str],
) -> dict[str, tuple[int, datetime | None]]:
    """
    Per LPO key: (lines touched max(ext distinct lines, dtl received lines), MAX(UPDATED_AT) from EXT).

    Lines = max(distinct LINE_SEQ on GRN_MOBILE_LINE_EXT, count of LPODTL rows with received qty > 0).
    """
    ext_counts: dict[str, int] = {}
    ext_dates: dict[str, datetime | None] = {}
    dtl_counts: dict[str, int] = {}

    keys = sorted({str(k).strip() for k in lp_keys if str(k).strip()})
    if not keys:
        return {}

    chunk_size = 900

    if _table_exists(cur, _GRN_MOBILE_LINE_EXT_TBL):
        ext_cols = _table_columns(cur, _GRN_MOBILE_LINE_EXT_TBL)
        lpo_col = _pick_existing(ext_cols, ["LPO_NO"])
        seq_col = _pick_existing(ext_cols, ["LINE_SEQ"])
        upd_col = _pick_existing(ext_cols, ["UPDATED_AT"])
        if lpo_col and seq_col:
            agg_max = f"MAX(e.{upd_col})" if upd_col else "CAST(NULL AS TIMESTAMP)"
            for idx in range(0, len(keys), chunk_size):
                chunk = keys[idx : idx + chunk_size]
                binds = {f"p{i}": chunk[i] for i in range(len(chunk))}
                ph = ", ".join(f":p{i}" for i in range(len(chunk)))
                cur.execute(
                    f"""
                    SELECT TRIM(TO_CHAR(e.{lpo_col})),
                           COUNT(DISTINCT e.{seq_col}),
                           {agg_max}
                      FROM {_GRN_MOBILE_LINE_EXT_TBL} e
                     WHERE TRIM(TO_CHAR(e.{lpo_col})) IN ({ph})
                     GROUP BY TRIM(TO_CHAR(e.{lpo_col}))
                    """,
                    binds,
                )
                for row in cur.fetchall() or []:
                    lk = str(row[0] or "").strip()
                    if not lk:
                        continue
                    ext_counts[lk] = max(ext_counts.get(lk, 0), int(row[1] or 0))
                    raw_dt = row[2]
                    if isinstance(raw_dt, datetime):
                        prev = ext_dates.get(lk)
                        if prev is None or raw_dt > prev:
                            ext_dates[lk] = raw_dt

    if dtl_tbl and dtl_lpo_col:
        d_cols = _table_columns(cur, dtl_tbl)
        recv_col = _pick_existing(
            d_cols,
            ["RECEIVEDQTY", "RECEIVED_QTY", "RCVQTY", "RCV_QTY", "GRNQTY", "GRN_QTY", "RCVDQTY"],
        )
        if recv_col:
            for idx in range(0, len(keys), chunk_size):
                chunk = keys[idx : idx + chunk_size]
                binds = {f"q{i}": chunk[i] for i in range(len(chunk))}
                ph = ", ".join(f":q{i}" for i in range(len(chunk)))
                cur.execute(
                    f"""
                    SELECT TRIM(TO_CHAR(d.{dtl_lpo_col})),
                           COUNT(*)
                      FROM {dtl_tbl} d
                     WHERE NVL(d.{recv_col}, 0) > 0
                       AND TRIM(TO_CHAR(d.{dtl_lpo_col})) IN ({ph})
                     GROUP BY TRIM(TO_CHAR(d.{dtl_lpo_col}))
                    """,
                    binds,
                )
                for row in cur.fetchall() or []:
                    lk = str(row[0] or "").strip()
                    if lk:
                        dtl_counts[lk] = max(dtl_counts.get(lk, 0), int(row[1] or 0))

        inq_col_dtl = _pick_existing(
            d_cols,
            ["INQUANTITY", "IN_INV_QTY", "ININV_QTY", "IN_QTY"],
        )
        if inq_col_dtl:
            for idx in range(0, len(keys), chunk_size):
                chunk = keys[idx : idx + chunk_size]
                binds_d = {f"n{i}": chunk[i] for i in range(len(chunk))}
                ph_d = ", ".join(f":n{i}" for i in range(len(chunk)))
                cur.execute(
                    f"""
                    SELECT TRIM(TO_CHAR(d.{dtl_lpo_col})),
                           COUNT(*)
                      FROM {dtl_tbl} d
                     WHERE NVL(d.{inq_col_dtl}, 0) > 0
                       AND TRIM(TO_CHAR(d.{dtl_lpo_col})) IN ({ph_d})
                     GROUP BY TRIM(TO_CHAR(d.{dtl_lpo_col}))
                    """,
                    binds_d,
                )
                for row in cur.fetchall() or []:
                    lk = str(row[0] or "").strip()
                    if lk:
                        dtl_counts[lk] = max(dtl_counts.get(lk, 0), int(row[1] or 0))

    out: dict[str, tuple[int, datetime | None]] = {}
    for lk in keys:
        n_ext = ext_counts.get(lk, 0)
        n_dtl = dtl_counts.get(lk, 0)
        out[lk] = (max(n_ext, n_dtl), ext_dates.get(lk))
    return out


def _listing_status_from_derived(
    *,
    derived: str,
    lpo_key: str,
    started_keys: set[str],
    lr_flag: str = "",
) -> str:
    """Split open POs into Pending vs Progressing (mobile saves, ERP partial LR, LPODTL received)."""
    if derived != "Pending":
        return derived
    if _lr_flag_is_partial_receive(lr_flag):
        return "Progressing"
    if str(lpo_key or "").strip() in started_keys:
        return "Progressing"
    return "Pending"


def _get_po_approval_status_map(cur: Any, lpo_nos: list[int], loc_code: str | None) -> dict[int, str]:
    nos = sorted({int(x) for x in lpo_nos if int(x or 0) > 0})
    if not nos or not _table_exists(cur, "PURCHASE_APPROVAL_TXN"):
        return {}

    txn_cols = _table_columns(cur, "PURCHASE_APPROVAL_TXN")
    doc_type_col = _pick_existing(txn_cols, ["DOC_TYPE"])
    doc_no_col = _pick_existing(txn_cols, ["DOC_NO"])
    status_col = _pick_existing(txn_cols, ["STATUS"])
    loc_col = _pick_existing(txn_cols, ["LOCATIONCODE", "LOCATION_CODE"])
    if not doc_type_col or not doc_no_col or not status_col:
        return {}

    out: dict[int, str] = {}
    chunk_size = 900  # ORA-01795 limit is 1000.
    for idx in range(0, len(nos), chunk_size):
        chunk = nos[idx : idx + chunk_size]
        in_list = ", ".join(str(n) for n in chunk)
        where_parts = [f"{doc_type_col} = 'LPO'", f"{doc_no_col} IN ({in_list})"]
        binds: dict[str, Any] = {}
        if loc_col and loc_code not in (None, ""):
            where_parts.append(f"{loc_col} = :loc")
            binds["loc"] = loc_code

        cur.execute(
            f"""
            SELECT {doc_no_col} AS doc_no, {status_col} AS status
            FROM PURCHASE_APPROVAL_TXN
            WHERE {' AND '.join(where_parts)}
            """,
            binds,
        )
        rows = cur.fetchall() or []
        for row in rows:
            doc_no = int(row[0] or 0)
            if doc_no > 0:
                out[doc_no] = str(row[1] or "DRAFT").upper()
    return out


def _distinct_lpo_keys_on_formal_receipt_hdr(
    cur: Any,
    recv_hdr_tbl: str,
    hdr_lpo_col: str,
    hdr_loc_col: str | None,
    loc_value: Any,
) -> set[str]:
    """LPONO values that already have a RECEIPTHDR row (same location when column + claim present)."""
    where_parts = ["1=1"]
    binds: dict[str, Any] = {}
    if hdr_loc_col and loc_value not in (None, ""):
        where_parts.append(f"h.{hdr_loc_col} = :loc")
        binds["loc"] = loc_value
    where_sql = " AND ".join(where_parts)
    cur.execute(
        f"""
        SELECT DISTINCT TRIM(TO_CHAR(h.{hdr_lpo_col})) AS lk
          FROM {recv_hdr_tbl} h
         WHERE {where_sql}
           AND TRIM(TO_CHAR(h.{hdr_lpo_col})) IS NOT NULL
        """,
        binds,
    )
    out: set[str] = set()
    for row in cur.fetchall() or []:
        k = str(row[0] or "").strip()
        if k:
            out.add(k)
    return out


def list_goods_receipts(
    page: int,
    page_size: int,
    search: str = "",
    status: str = "",
    *,
    grn_hub_pending: bool = False,
) -> list[dict]:
    claims = get_jwt()
    tenant_id = claims.get("tenant_id")
    conn = get_connection(tenant_id=tenant_id)
    with conn.cursor() as cur:
        hdr_tbl, dtl_tbl = _resolve_lpo_tables(cur)
        hdr_cols = _table_columns(cur, hdr_tbl)
        dtl_cols = _table_columns(cur, dtl_tbl)

        lpo_no_col = _pick_existing(hdr_cols, ["LPONO", "LPO_NO"])
        lpo_date_col = _pick_existing(hdr_cols, ["LPODATE", "LPO_DATE"])
        supplier_col = _pick_existing(hdr_cols, ["SUPPLIERCODE", "SUPPLIER_CODE"])
        amount_col = _pick_existing(hdr_cols, ["LPOAMOUNT", "LPO_AMOUNT", "TOTALAMOUNT", "TOTAL_AMOUNT"])
        remarks_col = _pick_existing(hdr_cols, ["REMARKS"])
        lrflag_col = _pick_existing(hdr_cols, ["LRFLAG", "LR_FLAG"])
        loc_col = _pick_existing(hdr_cols, ["LOCATIONCODE", "LOCATION_CODE"])
        del_col = _pick_existing(hdr_cols, ["DELFLAG", "DEL_FLAG"])
        supp_tbl = _first_existing_table(cur, ["SUPPLIER", "SUPPLIERS", "SUPPLIERMASTER", "VENDOR", "VENDORS"])
        supp_cols = _table_columns(cur, supp_tbl) if supp_tbl else set()
        supp_code_col = _pick_existing(supp_cols, ["SUPPLIERCODE", "SUPPLIER_CODE"])
        supp_name_col = _pick_existing(supp_cols, ["SUPPLIERNAME", "SUPPLIER_NAME", "SUPPNAME", "VENDORNAME", "NAME"])
        supp_loc_col = _pick_existing(supp_cols, ["LOCATIONCODE", "LOCATION_CODE"])

        dtl_lpo_col = _pick_existing(dtl_cols, ["LPONO", "LPO_NO"])
        dtl_qty_col = _pick_existing(dtl_cols, ["QUANTITY", "QTY", "RECEIVEDQTY", "RECEIVED_QTY"])
        dtl_rate_col = _pick_existing(dtl_cols, ["RATE", "UNITRATE", "UNIT_RATE"])

        if not lpo_no_col:
            raise ValueError("LPOHDR does not have an LPO number column")

        select_date = f"h.{lpo_date_col}" if lpo_date_col else "CAST(NULL AS DATE)"
        select_supplier = f"TO_CHAR(h.{supplier_col})" if supplier_col else "''"
        select_supplier_name = "''"
        select_amount = f"NVL(h.{amount_col}, 0)" if amount_col else "0"
        select_remarks = f"TO_CHAR(h.{remarks_col})" if remarks_col else "''"
        select_lrflag = f"TO_CHAR(h.{lrflag_col})" if lrflag_col else "''"
        select_del = f"TO_CHAR(h.{del_col})" if del_col else "''"
        nexa_grn_col = _pick_lpohdr_mobile_grn_status_col(hdr_cols)
        pending_lit = "'Pending'"
        mobile_grn_expr = (
            f"NVL(NULLIF(TRIM(TO_CHAR(h.{nexa_grn_col})), ''), {pending_lit})"
            if nexa_grn_col
            else pending_lit
        )
        join_supplier = ""
        if supp_tbl and supplier_col and supp_code_col and supp_name_col:
            select_supplier_name = f"TO_CHAR(s.{supp_name_col})"
            join_parts = [f"s.{supp_code_col} = h.{supplier_col}"]
            if supp_loc_col and loc_col:
                join_parts.append(f"s.{supp_loc_col} = h.{loc_col}")
            join_supplier = f" LEFT JOIN {supp_tbl} s ON {' AND '.join(join_parts)} "

        loc_value = claims.get("loc_code") or claims.get("location_code")
        where_parts = ["1=1"]
        binds: dict[str, Any] = {}
        if loc_col and loc_value not in (None, ""):
            where_parts.append(f"h.{loc_col} = :loc")
            binds["loc"] = loc_value

        if search.strip():
            where_parts.append(
                (
                    f"(TO_CHAR(h.{lpo_no_col}) LIKE :search "
                    f"OR {select_supplier} LIKE :search)"
                )
            )
            binds["search"] = f"%{search.strip()}%"

        where_sql = " AND ".join(where_parts)

        sf = status.strip().lower()
        omit_lpo_keys: frozenset[str] | None = None
        if grn_hub_pending:
            sf = "completed"
            if _table_exists(cur, "RECEIPTHDR"):
                rh_cols = _table_columns(cur, "RECEIPTHDR")
                rh_lpo = _pick_existing(rh_cols, ["LPONO", "LPO_NO"])
                rh_loc = _pick_existing(rh_cols, ["LOCATIONCODE", "LOCATION_CODE"])
                if rh_lpo:
                    omit_lpo_keys = frozenset(
                        _distinct_lpo_keys_on_formal_receipt_hdr(
                            cur, "RECEIPTHDR", rh_lpo, rh_loc, loc_value
                        )
                    )

        qty_expr = "0"
        amount_expr = "0"
        if dtl_lpo_col and dtl_qty_col:
            qty_expr = f"NVL(SUM(d.{dtl_qty_col}), 0)"
            if dtl_rate_col:
                amount_expr = f"NVL(SUM(NVL(d.{dtl_qty_col},0) * NVL(d.{dtl_rate_col},0)), 0)"

        sql_hdr_windows = f"""
                SELECT
                    TO_CHAR(h.{lpo_no_col}) AS lpo_no,
                    {select_date} AS lpo_date,
                    {select_supplier} AS supplier_code,
                    {select_supplier_name} AS supplier_name,
                    {select_amount} AS lpo_amount,
                    {select_remarks} AS remarks,
                    {select_lrflag} AS lrflag,
                    {select_del} AS del_flag,
                    {mobile_grn_expr} AS mobile_grn_status
                FROM {hdr_tbl} h
                {join_supplier}
                WHERE {where_sql}
                ORDER BY h.{lpo_no_col} DESC
                OFFSET :rq_offset ROWS FETCH NEXT :rq_fetch ROWS ONLY
            """

        def hdr_batch_to_aggregate_rows(hdr_only: list[Any]) -> list[Any]:
            page_keys = [str(r[0] or "").strip() for r in hdr_only if str(r[0] or "").strip()]
            qty_map, amt_map = _fetch_lpodtl_list_totals_batch(
                cur,
                dtl_tbl=dtl_tbl,
                dtl_lpo_col=dtl_lpo_col,
                qty_col=dtl_qty_col,
                rate_col=dtl_rate_col,
                lp_keys=page_keys,
            )
            return [
                tuple(r)
                + (
                    qty_map.get(str(r[0] or "").strip(), 0.0),
                    amt_map.get(str(r[0] or "").strip(), 0.0),
                )
                for r in hdr_only
            ]

        def map_rows_to_entries(
            rows_in: list[Any],
            *,
            apply_tab_filter: bool,
            include_touch_agg: bool,
            skip_lpo_keys: frozenset[str] | None = None,
        ) -> list[dict[str, Any]]:
            lpo_nos = [int(str(row[0] or "0")) for row in rows_in if str(row[0] or "").isdigit()]
            approval_map = _get_po_approval_status_map(
                cur, lpo_nos, None if loc_value in (None, "") else str(loc_value)
            )

            staged: list[dict[str, Any]] = []
            for row in rows_in:
                lpo_no_text = str(row[0] or "")
                lpo_no_int = int(lpo_no_text) if lpo_no_text.isdigit() else 0
                approval_status = approval_map.get(lpo_no_int, "DRAFT")
                derived_base = _derive_po_status(
                    del_flag=str(row[7] or ""),
                    lr_flag=str(row[6] or ""),
                    approval_status=approval_status,
                )
                staged.append(
                    {
                        "row": row,
                        "lpo_no_text": lpo_no_text,
                        "derived_base": derived_base,
                        "approval_status": approval_status,
                        "lr_flag": str(row[6] or ""),
                        "mobile_grn_raw": str(row[8] or ""),
                    }
                )

            for s in staged:
                if s["derived_base"] == "Cancelled":
                    continue
                if _mobile_grn_column_is_completed(s.get("mobile_grn_raw")):
                    s["derived_base"] = "Completed"

            pending_keys = [
                str(s["lpo_no_text"]).strip()
                for s in staged
                if s["derived_base"] == "Pending" and str(s["lpo_no_text"]).strip()
            ]
            started_keys = _started_receiving_lpo_keys(
                cur,
                dtl_tbl=dtl_tbl,
                dtl_lpo_col=dtl_lpo_col,
                candidate_lp_keys=pending_keys,
            )

            progressing_stats_keys = [
                str(s["lpo_no_text"]).strip()
                for s in staged
                if _listing_status_from_derived(
                    derived=str(s["derived_base"]),
                    lpo_key=str(s["lpo_no_text"]).strip(),
                    started_keys=started_keys,
                    lr_flag=str(s.get("lr_flag") or ""),
                )
                == "Progressing"
            ]
            if include_touch_agg and progressing_stats_keys:
                touch_stats = _aggregate_mobile_receiving_touch(
                    cur,
                    dtl_tbl=dtl_tbl,
                    dtl_lpo_col=dtl_lpo_col,
                    lp_keys=progressing_stats_keys,
                )
            else:
                touch_stats = {}

            mapped_local: list[dict[str, Any]] = []
            for meta in staged:
                row = meta["row"]
                derived_base = meta["derived_base"]
                lpo_no_text = str(meta["lpo_no_text"] or "")
                approval_status = str(meta["approval_status"] or "")
                lr_flag_str = str(meta.get("lr_flag") or "")
                listing_status = _listing_status_from_derived(
                    derived=derived_base,
                    lpo_key=lpo_no_text.strip(),
                    started_keys=started_keys,
                    lr_flag=lr_flag_str,
                )
                if apply_tab_filter and sf in {"pending", "progressing", "completed", "cancelled"}:
                    if listing_status.lower() != sf:
                        continue

                lk = lpo_no_text.strip()
                if skip_lpo_keys is not None and lk in skip_lpo_keys:
                    continue
                touch_n, touch_dt = touch_stats.get(lk, (0, None))
                sort_mobile = touch_dt if touch_dt is not None else datetime.min

                lpo_amount = float(row[4] or 0)
                detail_amount = float(row[10] or 0)
                entry: dict[str, Any] = {
                    "receipt_no": lpo_no_text,
                    "supplier": str(row[3] or "") or str(row[2] or ""),
                    "po_no": lpo_no_text,
                    "invoice_no": "",
                    "receipt_date": row[1].strftime("%b %d, %Y") if row[1] else "",
                    "amount": lpo_amount if lpo_amount > 0 else detail_amount,
                    "remarks": str(row[5] or ""),
                    "total_qty": float(row[9] or 0),
                    "status": listing_status,
                    "approval_status": approval_status,
                    "lr_flag": lr_flag_str,
                    "mobile_lines_touched": touch_n,
                    "mobile_last_saved_at": touch_dt.isoformat()
                    if isinstance(touch_dt, datetime)
                    else None,
                }
                if listing_status == "Progressing":
                    entry["_sort_mobile"] = sort_mobile
                mapped_local.append(entry)

            if sf == "progressing":
                mapped_local.sort(key=lambda r: r.get("_sort_mobile", datetime.min), reverse=True)
            for r in mapped_local:
                r.pop("_sort_mobile", None)
            return mapped_local

        if sf == "progressing":
            sql = f"""
                SELECT
                    TO_CHAR(h.{lpo_no_col}) AS lpo_no,
                    {select_date} AS lpo_date,
                    {select_supplier} AS supplier_code,
                    {select_supplier_name} AS supplier_name,
                    {select_amount} AS lpo_amount,
                    {select_remarks} AS remarks,
                    {select_lrflag} AS lrflag,
                    {select_del} AS del_flag,
                    {mobile_grn_expr} AS mobile_grn_status,
                    {qty_expr} AS total_qty,
                    {amount_expr} AS detail_amount
                FROM {hdr_tbl} h
                {join_supplier}
                LEFT JOIN {dtl_tbl} d
                    ON {f'd.{dtl_lpo_col} = h.{lpo_no_col}' if dtl_lpo_col else '1=0'}
                WHERE {where_sql}
                GROUP BY
                    h.{lpo_no_col},
                    {select_date},
                    {select_supplier},
                    {select_supplier_name},
                    {select_amount},
                    {select_remarks},
                    {select_lrflag},
                    {select_del},
                    {mobile_grn_expr}
                ORDER BY h.{lpo_no_col} DESC
            """
            cur.execute(sql, binds)
            agg_rows = list(cur.fetchall() or [])
            return map_rows_to_entries(
                agg_rows,
                apply_tab_filter=True,
                include_touch_agg=True,
                skip_lpo_keys=omit_lpo_keys,
            )

        if sf == "":
            binds_pg = dict(binds)
            binds_pg["rq_offset"] = max((page - 1) * page_size, 0)
            binds_pg["rq_fetch"] = page_size
            cur.execute(sql_hdr_windows, binds_pg)
            hdr_only = cur.fetchall() or []
            rows = hdr_batch_to_aggregate_rows(hdr_only)
            return map_rows_to_entries(
                rows,
                apply_tab_filter=False,
                include_touch_agg=True,
                skip_lpo_keys=omit_lpo_keys,
            )

        target_end = page * page_size
        target_start = (page - 1) * page_size
        gathered: list[dict[str, Any]] = []
        hdr_skip = 0
        batch = max(page_size * 15, 300)
        scan_cap = max(100_000, target_end * 100)
        scanned = 0
        while len(gathered) < target_end and scanned < scan_cap:
            binds_w = dict(binds)
            binds_w["rq_offset"] = hdr_skip
            binds_w["rq_fetch"] = batch
            cur.execute(sql_hdr_windows, binds_w)
            hdr_only = cur.fetchall() or []
            if not hdr_only:
                break
            scanned += len(hdr_only)
            agg_rows = hdr_batch_to_aggregate_rows(hdr_only)
            part = map_rows_to_entries(
                agg_rows,
                apply_tab_filter=True,
                include_touch_agg=False,
                skip_lpo_keys=omit_lpo_keys,
            )
            gathered.extend(part)
            hdr_skip += len(hdr_only)

        return gathered[target_start:target_end]


def _grn_inventory_posted_filter_sql(cur: Any, hdr_alias: str, *, posted: bool) -> str:
    """SQL predicate: inventory posted (Y) vs draft (N, no GRN item journal)."""
    if not _table_exists(cur, "RECEIPTHDR"):
        return "1=1"
    hdr_cols = _table_columns(cur, "RECEIPTHDR")
    inv_col = _pick_existing(hdr_cols, ["INVENTORY_POSTED", "INVENTORYPOSTED"])
    no_col = _pick_existing(hdr_cols, ["RECEIPTNO", "RECEIPT_NO"])
    loc_col = _pick_existing(hdr_cols, ["LOCATIONCODE", "LOCATION_CODE"])
    if not (inv_col and no_col and loc_col):
        return "1=1"
    ij_tbl = _first_existing_table(cur, ["ITEMJOURNAL", "ITEMJOURNEL"])
    if not ij_tbl:
        if posted:
            return f"NVL({hdr_alias}.{inv_col}, 'N') = 'Y'"
        return f"NVL({hdr_alias}.{inv_col}, 'N') = 'N'"
    ij_cols = _table_columns(cur, ij_tbl)
    ij_loc = _pick_existing(ij_cols, ["LOCATIONCODE", "LOCATION_CODE"]) or "LOCATIONCODE"
    ij_sd = _pick_existing(ij_cols, ["SOURCE_DOC", "SOURCEDOC"]) or "SOURCE_DOC"
    ij_sn = _pick_existing(ij_cols, ["SOURCE_NO", "SOURCENO"]) or "SOURCE_NO"
    journal_exists = (
        f"EXISTS (SELECT 1 FROM {ij_tbl} ij WHERE ij.{ij_loc} = {hdr_alias}.{loc_col}"
        f" AND UPPER(TRIM(NVL(ij.{ij_sd}, ''))) = 'GRN'"
        f" AND TO_CHAR(ij.{ij_sn}) = TO_CHAR({hdr_alias}.{no_col}))"
    )
    if posted:
        return f"(NVL({hdr_alias}.{inv_col}, 'N') = 'Y' OR {journal_exists})"
    return f"(NVL({hdr_alias}.{inv_col}, 'N') = 'N' AND NOT ({journal_exists}))"


def list_formal_receipt_documents(
    page: int,
    page_size: int,
    search: str = "",
    *,
    inventory_tab: str = "posted",
) -> list[dict]:
    """
    Rows from RECEIPTHDR (+ RECEIPTDTL totals) for GRN hub tabs.
    ``inventory_tab``: ``draft`` (saved, not posted) or ``posted`` (stock posted).
    """
    claims = get_jwt()
    tenant_id = claims.get("tenant_id")
    conn = get_connection(tenant_id=tenant_id)
    with conn.cursor() as cur:
        try:
            hdr_tbl, dtl_tbl = _resolve_receipt_tables(cur)
        except ValueError:
            return []

        hdr_cols = _table_columns(cur, hdr_tbl)
        dtl_cols = _table_columns(cur, dtl_tbl)

        hdr_receipt_col = _pick_existing(hdr_cols, ["RECEIPTNO", "RECEIPT_NO"])
        hdr_date_col = _pick_existing(hdr_cols, ["RECEIPTDATE", "RECEIPT_DATE"])
        hdr_sup_col = _pick_existing(hdr_cols, ["SUPPLIERCODE", "SUPPLIER_CODE"])
        hdr_po_col = _pick_existing(hdr_cols, ["LPONO", "LPO_NO"])
        hdr_inv_col = _pick_existing(hdr_cols, ["INVOICENO", "INVOICE_NO"])
        hdr_amt_col = _pick_existing(hdr_cols, ["INVOICEAMOUNT", "TOTALAMOUNT", "INVOICE_AMOUNT", "TOTAL_AMOUNT"])
        hdr_rem_col = _pick_existing(hdr_cols, ["REMARKS", "NARRATION"])
        hdr_loc_col = _pick_existing(hdr_cols, ["LOCATIONCODE", "LOCATION_CODE"])
        hdr_del_col = _pick_existing(hdr_cols, ["DELFLAG", "DEL_FLAG"])

        dtl_recv_col = _pick_existing(dtl_cols, ["RECEIPTNO", "RECEIPT_NO"])
        dtl_qty_col = _pick_existing(dtl_cols, ["QUANTITY", "QTY", "RECEIVEDQTY", "RECEIVED_QTY"])

        if not hdr_receipt_col or not hdr_date_col:
            return []

        supp_tbl = _first_existing_table(cur, ["SUPPLIER", "SUPPLIERS", "SUPPLIERMASTER", "VENDOR", "VENDORS"])
        supp_cols = _table_columns(cur, supp_tbl) if supp_tbl else set()
        supp_code_col = _pick_existing(supp_cols, ["SUPPLIERCODE", "SUPPLIER_CODE"])
        supp_name_col = _pick_existing(supp_cols, ["SUPPLIERNAME", "SUPPLIER_NAME", "SUPPNAME", "VENDORNAME", "NAME"])
        join_supplier = ""
        select_sup_name = "''"
        if supp_tbl and hdr_sup_col and supp_code_col and supp_name_col:
            select_sup_name = f"TO_CHAR(s.{supp_name_col})"
            join_supplier = f"LEFT JOIN {supp_tbl} s ON s.{supp_code_col} = h.{hdr_sup_col}"

        loc_value = claims.get("loc_code") or claims.get("location_code")
        where_parts = ["1=1"]
        binds: dict[str, Any] = {}
        if hdr_loc_col and loc_value not in (None, ""):
            where_parts.append(f"h.{hdr_loc_col} = :loc")
            binds["loc"] = loc_value
        if hdr_del_col:
            where_parts.append(f"NVL(h.{hdr_del_col}, 'N') = 'N'")
        inv_tab = (inventory_tab or "posted").strip().lower()
        if inv_tab == "draft":
            where_parts.append(_grn_inventory_posted_filter_sql(cur, "h", posted=False))
        elif inv_tab == "posted":
            where_parts.append(_grn_inventory_posted_filter_sql(cur, "h", posted=True))
        if search.strip():
            search_lit_parts = [f"TO_CHAR(h.{hdr_receipt_col}) LIKE :search"]
            if hdr_po_col:
                search_lit_parts.append(f"TO_CHAR(h.{hdr_po_col}) LIKE :search")
            if hdr_sup_col:
                search_lit_parts.append(f"TO_CHAR(h.{hdr_sup_col}) LIKE :search")
            where_parts.append("(" + " OR ".join(search_lit_parts) + ")")
            binds["search"] = f"%{search.strip()}%"
        where_sql = " AND ".join(where_parts)

        select_po = f"TO_CHAR(h.{hdr_po_col})" if hdr_po_col else "''"
        select_sup_cd = f"TO_CHAR(h.{hdr_sup_col})" if hdr_sup_col else "''"
        select_inv = f"TO_CHAR(h.{hdr_inv_col})" if hdr_inv_col else "''"
        select_amt = f"NVL(h.{hdr_amt_col}, 0)" if hdr_amt_col else "0"
        select_rem = f"TO_CHAR(h.{hdr_rem_col})" if hdr_rem_col else "''"

        binds_pg = dict(binds)
        binds_pg["rq_off"] = max((page - 1) * page_size, 0)
        binds_pg["rq_need"] = page_size

        sql_hdr = f"""
            SELECT TO_CHAR(h.{hdr_receipt_col}) AS rn,
                   h.{hdr_date_col} AS rdt,
                   {select_po} AS lpo_no,
                   {select_sup_cd} AS sup_cd,
                   NVL(NULLIF(TRIM({select_sup_name}), ''), '') AS sup_nm,
                   {select_inv} AS inv_no,
                   {select_amt} AS inv_amt,
                   {select_rem} AS remarks
              FROM {hdr_tbl} h
              {join_supplier}
             WHERE {where_sql}
             ORDER BY h.{hdr_receipt_col} DESC
             OFFSET :rq_off ROWS FETCH NEXT :rq_need ROWS ONLY
        """
        cur.execute(sql_hdr, binds_pg)
        hdr_rows = cur.fetchall() or []
        keys = [str(r[0] or "").strip() for r in hdr_rows if str(r[0] or "").strip()]
        qty_by: dict[str, float] = {}
        if dtl_recv_col and dtl_qty_col and keys:
            chunk_size = 900
            for i in range(0, len(keys), chunk_size):
                chunk = keys[i : i + chunk_size]
                ph = ", ".join(f":k{j}" for j in range(len(chunk)))
                b2 = {f"k{j}": chunk[j] for j in range(len(chunk))}
                cur.execute(
                    f"""
                    SELECT TRIM(TO_CHAR(d.{dtl_recv_col})), NVL(SUM(NVL(d.{dtl_qty_col}, 0)), 0)
                      FROM {dtl_tbl} d
                     WHERE TRIM(TO_CHAR(d.{dtl_recv_col})) IN ({ph})
                     GROUP BY TRIM(TO_CHAR(d.{dtl_recv_col}))
                    """,
                    b2,
                )
                for row in cur.fetchall() or []:
                    k = str(row[0] or "").strip()
                    if k:
                        qty_by[k] = float(row[1] or 0)

        row_status = "Draft" if inv_tab == "draft" else "Posted"
        mapped: list[dict[str, Any]] = []
        for row in hdr_rows:
            rk = str(row[0] or "").strip()
            lpo_txt = str(row[2] or "").strip()
            sup_disp = str(row[4] or "").strip()
            if not sup_disp:
                sup_disp = str(row[3] or "").strip()
            rdt = row[1]
            mapped.append(
                {
                    "receipt_no": rk,
                    "supplier": sup_disp or str(row[3] or ""),
                    "po_no": lpo_txt,
                    "invoice_no": str(row[5] or ""),
                    "receipt_date": rdt.strftime("%b %d, %Y") if isinstance(rdt, datetime) else (str(rdt or "")),
                    "amount": float(row[6] or 0),
                    "remarks": str(row[7] or ""),
                    "total_qty": float(qty_by.get(rk, 0)),
                    "status": row_status,
                    "approval_status": "",
                    "lr_flag": "",
                    "mobile_lines_touched": 0,
                    "mobile_last_saved_at": None,
                }
            )
        return mapped


def _get_formal_receipt_details(cur: Any, receipt_key: str, loc_value: Any) -> dict[str, Any] | None:
    """Load RECEIPTHDR/RECEIPTDTL when [receipt_key] is a saved formal GRN number."""
    key = str(receipt_key or "").strip()
    if not key:
        return None
    try:
        hdr_tbl, dtl_tbl = _resolve_receipt_tables(cur)
    except ValueError:
        return None

    hdr_cols = _table_columns(cur, hdr_tbl)
    dtl_cols = _table_columns(cur, dtl_tbl)
    hdr_receipt_col = _pick_existing(hdr_cols, ["RECEIPTNO", "RECEIPT_NO"])
    hdr_date_col = _pick_existing(hdr_cols, ["RECEIPTDATE", "RECEIPT_DATE"])
    hdr_sup_col = _pick_existing(hdr_cols, ["SUPPLIERCODE", "SUPPLIER_CODE"])
    hdr_po_col = _pick_existing(hdr_cols, ["LPONO", "LPO_NO"])
    hdr_inv_col = _pick_existing(hdr_cols, ["INVOICENO", "INVOICE_NO"])
    hdr_inv_date_col = _pick_existing(hdr_cols, ["INVOICEDATE", "INVOICE_DATE"])
    hdr_amt_col = _pick_existing(hdr_cols, ["INVOICEAMOUNT", "TOTALAMOUNT", "INVOICE_AMOUNT", "TOTAL_AMOUNT"])
    hdr_rem_col = _pick_existing(hdr_cols, ["REMARKS", "NARRATION"])
    hdr_loc_col = _pick_existing(hdr_cols, ["LOCATIONCODE", "LOCATION_CODE"])
    if not hdr_receipt_col:
        return None

    supp_tbl = _first_existing_table(cur, ["SUPPLIER", "SUPPLIERS", "SUPPLIERMASTER", "VENDOR", "VENDORS"])
    supp_cols = _table_columns(cur, supp_tbl) if supp_tbl else set()
    supp_code_col = _pick_existing(supp_cols, ["SUPPLIERCODE", "SUPPLIER_CODE"])
    supp_name_col = _pick_existing(supp_cols, ["SUPPLIERNAME", "SUPPLIER_NAME", "SUPPNAME", "VENDORNAME", "NAME"])
    supplier_name_expr = "''"
    join_supplier = ""
    if supp_tbl and hdr_sup_col and supp_code_col and supp_name_col:
        supplier_name_expr = f"TO_CHAR(s.{supp_name_col})"
        join_supplier = f" LEFT JOIN {supp_tbl} s ON s.{supp_code_col} = h.{hdr_sup_col} "

    loc_tbl = "LOCATIONMASTER" if _table_exists(cur, "LOCATIONMASTER") else ""
    loc_cols = _table_columns(cur, loc_tbl) if loc_tbl else set()
    loc_code_col = _pick_existing(loc_cols, ["LOCATIONCODE", "LOCATION_CODE"])
    loc_name_col = _pick_existing(
        loc_cols,
        ["LOCATIONNAME", "LOCATION_NAME", "DESCRIPTION", "LOCATION", "LOCNAME", "NAME"],
    )
    location_name_expr = "''"
    join_location = ""
    if loc_tbl and hdr_loc_col and loc_code_col and loc_name_col:
        location_name_expr = f"TO_CHAR(lm.{loc_name_col})"
        join_location = f" LEFT JOIN {loc_tbl} lm ON lm.{loc_code_col} = h.{hdr_loc_col} "

    where_parts = [f"TO_CHAR(h.{hdr_receipt_col}) = :receipt_no"]
    binds: dict[str, Any] = {"receipt_no": key}
    if hdr_loc_col and loc_value not in (None, ""):
        where_parts.append(f"h.{hdr_loc_col} = :loc")
        binds["loc"] = loc_value

    header_sql = f"""
        SELECT
            TO_CHAR(h.{hdr_receipt_col}) AS receipt_no,
            {f"h.{hdr_date_col}" if hdr_date_col else "CAST(NULL AS DATE)"} AS receipt_date,
            {f"TO_CHAR(h.{hdr_sup_col})" if hdr_sup_col else "''"} AS supplier,
            {supplier_name_expr} AS supplier_name,
            {f"TO_CHAR(h.{hdr_po_col})" if hdr_po_col else "''"} AS po_no,
            {f"NVL(h.{hdr_amt_col},0)" if hdr_amt_col else "0"} AS amount,
            {f"TO_CHAR(h.{hdr_rem_col})" if hdr_rem_col else "''"} AS remarks,
            {f"TO_CHAR(h.{hdr_inv_col})" if hdr_inv_col else "''"} AS invoice_no,
            {f"h.{hdr_inv_date_col}" if hdr_inv_date_col else "CAST(NULL AS DATE)"} AS invoice_date,
            {f"TO_CHAR(h.{hdr_loc_col})" if hdr_loc_col else "''"} AS location_code,
            {location_name_expr} AS location_name
        FROM {hdr_tbl} h
        {join_supplier}
        {join_location}
        WHERE {" AND ".join(where_parts)}
    """
    cur.execute(header_sql, binds)
    header = cur.fetchone()
    if not header:
        return None

    dtl_receipt_col = _pick_existing(dtl_cols, ["RECEIPTNO", "RECEIPT_NO"])
    dtl_item_col = _pick_existing(dtl_cols, ["ITEMCODE", "ITEM_CODE"])
    dtl_qty_col = _pick_existing(dtl_cols, ["QUANTITY", "QTY", "RECEIVEDQTY", "RECEIVED_QTY"])
    dtl_rate_col = _pick_existing(dtl_cols, ["RATE", "UNITRATE", "UNIT_RATE"])
    dtl_uom_col = _pick_existing(dtl_cols, ["UOM", "UNITOFMEASUREMENT", "UNIT", "BASEUOM"])
    item_tbl = "ITEMMASTER" if _table_exists(cur, "ITEMMASTER") else ""
    item_cols = _table_columns(cur, item_tbl) if item_tbl else set()
    item_code_col = _pick_existing(item_cols, ["ITEMCODE", "ITEM_CODE", "CODE"])
    item_name_col = _pick_existing(item_cols, ["ITEMNAME", "ITEM_NAME", "ITEMDESC", "NAME"])

    rows: list[Any] = []
    if dtl_receipt_col and dtl_item_col and dtl_qty_col:
        qty_expr = f"NVL(d.{dtl_qty_col}, 0)"
        item_name_expr = "''"
        join_item = ""
        if item_tbl and item_code_col and item_name_col:
            item_name_expr = f"TO_CHAR(im.{item_name_col})"
            join_item = f" LEFT JOIN {item_tbl} im ON im.{item_code_col} = d.{dtl_item_col} "
        detail_sql = f"""
            SELECT
                TO_CHAR(d.{dtl_item_col}) AS item_code,
                {item_name_expr} AS item_name,
                {f"TO_CHAR(d.{dtl_uom_col})" if dtl_uom_col else "''"} AS unit,
                {qty_expr} AS qty,
                {qty_expr} AS erp_received_qty,
                {f"NVL(d.{dtl_rate_col},0)" if dtl_rate_col else "0"} AS rate
            FROM {dtl_tbl} d
            {join_item}
            WHERE TO_CHAR(d.{dtl_receipt_col}) = :receipt_no
            ORDER BY d.ROWID
        """
        cur.execute(detail_sql, {"receipt_no": key})
        rows = cur.fetchall() or []

    items = [
        {
            "line_seq": idx,
            "item_code": str(row[0] or ""),
            "item_name": str(row[1] or ""),
            "unit": str(row[2] or ""),
            "qty": float(row[3] or 0),
            "erp_received_qty": float(row[4] or 0),
            "rate": float(row[5] or 0),
        }
        for idx, row in enumerate(rows, start=1)
    ]

    inv_dt = header[8]
    rdt = header[1]
    draft_where = [f"TO_CHAR(h.{hdr_receipt_col}) = :receipt_no"]
    draft_binds: dict[str, Any] = {"receipt_no": key}
    if hdr_loc_col and loc_value not in (None, ""):
        draft_where.append(f"h.{hdr_loc_col} = :loc")
        draft_binds["loc"] = loc_value
    draft_where.append(_grn_inventory_posted_filter_sql(cur, "h", posted=False))
    cur.execute(
        f"SELECT 1 FROM {hdr_tbl} h WHERE {' AND '.join(draft_where)}",
        draft_binds,
    )
    doc_status = "Draft" if cur.fetchone() else "Posted"

    return {
        "receipt_no": str(header[0] or ""),
        "receipt_date": rdt.strftime("%b %d, %Y") if isinstance(rdt, datetime) else (str(rdt or "")),
        "supplier": str(header[2] or ""),
        "supplier_name": str(header[3] or ""),
        "po_no": str(header[4] or ""),
        "invoice_no": str(header[7] or ""),
        "amount": float(header[5] or 0),
        "remarks": str(header[6] or ""),
        "status": doc_status,
        "document_type": "formal_receipt",
        "approval_status": "",
        "lr_flag": "",
        "mobile_lines_touched": 0,
        "mobile_last_saved_at": None,
        "LOCATIONCODE": _coerce_grn_mobile_ext_location_id(header[9]),
        "location_code": str(header[9] or ""),
        "location_name": str(header[10] or ""),
        "grn_date": rdt.strftime("%b %d, %Y") if isinstance(rdt, datetime) else (str(rdt or "")),
        "po_date": rdt.strftime("%b %d, %Y") if isinstance(rdt, datetime) else (str(rdt or "")),
        "invoice_date": inv_dt.strftime("%b %d, %Y") if isinstance(inv_dt, datetime) else (str(inv_dt or "")),
        "total_items": len(items),
        "total_qty": sum(float(x.get("qty") or 0) for x in items),
        "items": items,
    }


def _lpo_lookup_key_variants(raw: str) -> list[str]:
    """UI/list may pass 000003 while LPONO is stored as PO-000003 (varchar series)."""
    s = str(raw or "").strip()
    out: list[str] = []
    if s:
        out.append(s)
    core = s
    up = s.upper()
    if up.startswith("PO-"):
        core = s[3:].strip()
        out.append(core)
    elif up.startswith("LPO-"):
        core = s[4:].strip()
        out.append(core)
    try:
        from db import billno_numeric_part

        n = billno_numeric_part(s) or billno_numeric_part(core)
        if n > 0:
            out.extend(
                [
                    str(n),
                    f"{n:06d}",
                    f"{n:05d}",
                    f"PO-{n:06d}",
                    f"PO-{n}",
                    f"LPO-{n:06d}",
                    f"LPO-{n}",
                ]
            )
    except Exception:
        pass
    # If caller already stripped PO-, still try the series form.
    if core and not up.startswith("PO-") and not up.startswith("LPO-"):
        out.append(f"PO-{core}")
        out.append(f"LPO-{core}")
    # de-dupe, preserve order
    seen: set[str] = set()
    uniq: list[str] = []
    for k in out:
        if k and k not in seen:
            seen.add(k)
            uniq.append(k)
    return uniq


def get_goods_receipt_details(receipt_no: str) -> dict:
    claims = get_jwt()
    tenant_id = claims.get("tenant_id")
    loc_value = claims.get("loc_code") or claims.get("location_code")
    conn = get_connection(tenant_id=tenant_id)
    with conn.cursor() as cur:
        key_variants = _lpo_lookup_key_variants(str(receipt_no).strip())
        formal = None
        for k in key_variants:
            formal = _get_formal_receipt_details(cur, k, loc_value)
            if formal is not None:
                return formal
        maybe_create_grn_mobile_line_ext(cur, conn)
        hdr_tbl, dtl_tbl = _resolve_lpo_tables(cur)
        hdr_cols = _table_columns(cur, hdr_tbl)
        dtl_cols = _table_columns(cur, dtl_tbl)

        hdr_receipt_col = _pick_existing(hdr_cols, ["LPONO", "LPO_NO"])
        hdr_date_col = _pick_existing(hdr_cols, ["LPODATE", "LPO_DATE"])
        hdr_supplier_col = _pick_existing(hdr_cols, ["SUPPLIERCODE", "SUPPLIER_CODE"])
        hdr_amount_col = _pick_existing(hdr_cols, ["LPOAMOUNT", "LPO_AMOUNT", "TOTALAMOUNT", "TOTAL_AMOUNT"])
        hdr_remarks_col = _pick_existing(hdr_cols, ["REMARKS"])
        hdr_lpo_col = _pick_existing(hdr_cols, ["LPONO", "LPO_NO"])
        hdr_lrflag_col = _pick_existing(hdr_cols, ["LRFLAG", "LR_FLAG"])
        hdr_del_col = _pick_existing(hdr_cols, ["DELFLAG", "DEL_FLAG"])
        hdr_loc_col = _pick_existing(hdr_cols, ["LOCATIONCODE", "LOCATION_CODE"])
        supp_tbl = _first_existing_table(cur, ["SUPPLIER", "SUPPLIERS", "SUPPLIERMASTER", "VENDOR", "VENDORS"])
        supp_cols = _table_columns(cur, supp_tbl) if supp_tbl else set()
        supp_code_col = _pick_existing(supp_cols, ["SUPPLIERCODE", "SUPPLIER_CODE"])
        supp_name_col = _pick_existing(supp_cols, ["SUPPLIERNAME", "SUPPLIER_NAME", "SUPPNAME", "VENDORNAME", "NAME"])
        supp_loc_col = _pick_existing(supp_cols, ["LOCATIONCODE", "LOCATION_CODE"])

        loc_tbl = "LOCATIONMASTER" if _table_exists(cur, "LOCATIONMASTER") else ""
        loc_cols = _table_columns(cur, loc_tbl) if loc_tbl else set()
        loc_code_col = _pick_existing(loc_cols, ["LOCATIONCODE", "LOCATION_CODE"])
        loc_name_col = _pick_existing(
            loc_cols,
            ["LOCATIONNAME", "LOCATION_NAME", "DESCRIPTION", "LOCATION", "LOCNAME", "NAME"],
        )

        dtl_receipt_col = _pick_existing(dtl_cols, ["LPONO", "LPO_NO"])
        dtl_item_col = _pick_existing(dtl_cols, ["ITEMCODE", "ITEM_CODE"])
        dtl_ordered_qty_col = _pick_lpodtl_ordered_qty_col(dtl_cols)
        dtl_received_qty_col = _pick_lpodtl_received_qty_col(dtl_cols)
        dtl_rate_col = _pick_existing(dtl_cols, ["RATE", "UNITRATE", "UNIT_RATE"])
        dtl_uom_col = _pick_existing(dtl_cols, ["UOM", "UNITOFMEASUREMENT", "UNIT", "BASEUOM"])
        item_tbl = "ITEMMASTER" if _table_exists(cur, "ITEMMASTER") else ""
        item_cols = _table_columns(cur, item_tbl) if item_tbl else set()
        item_code_col = _pick_existing(item_cols, ["ITEMCODE", "ITEM_CODE", "CODE"])
        item_name_col = _pick_existing(item_cols, ["ITEMNAME", "ITEM_NAME", "ITEMDESC", "NAME"])

        if not hdr_receipt_col:
            raise ValueError("LPOHDR does not have an LPO number column")

        supplier_name_expr = "''"
        join_supplier = ""
        if supp_tbl and hdr_supplier_col and supp_code_col and supp_name_col:
            supplier_name_expr = f"TO_CHAR(s.{supp_name_col})"
            join_parts = [f"s.{supp_code_col} = h.{hdr_supplier_col}"]
            if supp_loc_col and hdr_loc_col:
                join_parts.append(f"s.{supp_loc_col} = h.{hdr_loc_col}")
            join_supplier = f" LEFT JOIN {supp_tbl} s ON {' AND '.join(join_parts)} "

        location_name_expr = "''"
        join_location = ""
        if loc_tbl and hdr_loc_col and loc_code_col and loc_name_col:
            location_name_expr = f"TO_CHAR(lm.{loc_name_col})"
            join_location = f" LEFT JOIN {loc_tbl} lm ON lm.{loc_code_col} = h.{hdr_loc_col} "

        hdr_nexa_col = _pick_lpohdr_mobile_grn_status_col(hdr_cols)
        pending_lit_detail = "'Pending'"
        mobile_grn_detail_expr = (
            f"NVL(NULLIF(TRIM(TO_CHAR(h.{hdr_nexa_col})), ''), {pending_lit_detail})"
            if hdr_nexa_col
            else pending_lit_detail
        )

        header_sql = f"""
            SELECT
                TO_CHAR(h.{hdr_receipt_col}) AS receipt_no,
                {f"h.{hdr_date_col}" if hdr_date_col else "CAST(NULL AS DATE)"} AS receipt_date,
                {f"TO_CHAR(h.{hdr_supplier_col})" if hdr_supplier_col else "''"} AS supplier,
                {supplier_name_expr} AS supplier_name,
                {f"TO_CHAR(h.{hdr_lpo_col})" if hdr_lpo_col else "''"} AS po_no,
                {f"NVL(h.{hdr_amount_col},0)" if hdr_amount_col else "0"} AS amount,
                {f"TO_CHAR(h.{hdr_remarks_col})" if hdr_remarks_col else "''"} AS remarks,
                {f"TO_CHAR(h.{hdr_lrflag_col})" if hdr_lrflag_col else "''"} AS lrflag,
                {f"TO_CHAR(h.{hdr_del_col})" if hdr_del_col else "''"} AS delflag,
                {f"TO_CHAR(h.{hdr_loc_col})" if hdr_loc_col else "''"} AS location_code,
                {location_name_expr} AS location_name,
                {mobile_grn_detail_expr} AS nexa_mobile_grn_status
            FROM {hdr_tbl} h
            {join_supplier}
            {join_location}
            WHERE TO_CHAR(h.{hdr_receipt_col}) = :receipt_no
               OR LTRIM(TO_CHAR(h.{hdr_receipt_col}), '0') = LTRIM(:receipt_no, '0')
        """
        header = None
        resolved_key = str(receipt_no).strip()
        for k in key_variants:
            cur.execute(header_sql, {"receipt_no": k})
            header = cur.fetchone()
            if header:
                resolved_key = str(header[0] or k).strip() or k
                break
        if not header:
            raise ValueError("Goods receipt not found")
        # Detail queries below use the resolved document key from the header row.
        receipt_no = resolved_key

        supplier_name_fallback = ""
        supplier_code_text = str(header[2] or "").strip()
        if not str(header[3] or "").strip() and supp_tbl and supp_code_col and supp_name_col and supplier_code_text:
            fallback_where = [f"TO_CHAR({supp_code_col}) = :scode"]
            fallback_binds: dict[str, Any] = {"scode": supplier_code_text}
            if supp_loc_col and hdr_loc_col:
                header_loc_text = str(header[9] or "").strip()
                if header_loc_text:
                    fallback_where.append(f"TO_CHAR({supp_loc_col}) = :sloc")
                    fallback_binds["sloc"] = header_loc_text
            cur.execute(
                f"""
                SELECT TO_CHAR({supp_name_col})
                FROM {supp_tbl}
                WHERE {' AND '.join(fallback_where)}
                """,
                fallback_binds,
            )
            sup_row = cur.fetchone()
            supplier_name_fallback = str((sup_row or [""])[0] or "")

        loc_value = claims.get("loc_code") or claims.get("location_code")
        approval_map = _get_po_approval_status_map(
            cur,
            [int(str(header[0] or "0"))] if str(header[0] or "").isdigit() else [],
            None if loc_value in (None, "") else str(loc_value),
        )
        approval_status = approval_map.get(int(str(header[0] or "0")) if str(header[0] or "").isdigit() else 0, "DRAFT")
        lr_hdr = str(header[7] or "")
        derived_base = _derive_po_status(
            del_flag=str(header[8] or ""),
            lr_flag=lr_hdr,
            approval_status=approval_status,
        )
        mobile_detail_raw = str(header[11] or "") if len(header) > 11 else ""
        if derived_base != "Cancelled" and _mobile_grn_column_is_completed(mobile_detail_raw):
            derived_base = "Completed"
        started_keys_detail = (
            _started_receiving_lpo_keys(
                cur,
                dtl_tbl=dtl_tbl,
                dtl_lpo_col=dtl_receipt_col,
                candidate_lp_keys=[str(header[0] or "").strip()],
            )
            if derived_base == "Pending"
            else set()
        )
        derived_status = _listing_status_from_derived(
            derived=derived_base,
            lpo_key=str(header[0] or "").strip(),
            started_keys=started_keys_detail,
            lr_flag=lr_hdr,
        )
        lk_detail = str(header[0] or "").strip()
        touch_detail = (
            _aggregate_mobile_receiving_touch(
                cur,
                dtl_tbl=dtl_tbl,
                dtl_lpo_col=dtl_receipt_col,
                lp_keys=[lk_detail],
            )
            if derived_status == "Progressing"
            else {}
        )
        _t_n = 0
        _t_d: datetime | None = None
        if touch_detail.get(lk_detail):
            _t_n, _t_d = touch_detail[lk_detail]

        if dtl_receipt_col and dtl_item_col:
            ordered_expr = f"NVL(d.{dtl_ordered_qty_col}, 0)" if dtl_ordered_qty_col else "0"
            received_expr = f"NVL(d.{dtl_received_qty_col}, 0)" if dtl_received_qty_col else "0"
            item_name_expr = "''"
            join_item = ""
            if item_tbl and item_code_col and item_name_col:
                item_name_expr = f"TO_CHAR(im.{item_name_col})"
                join_item = f" LEFT JOIN {item_tbl} im ON im.{item_code_col} = d.{dtl_item_col} "
            _, order_stable = _lpodtl_stable_order_exprs(dtl_item_col)
            detail_sql = f"""
                SELECT
                    TO_CHAR(d.{dtl_item_col}) AS item_code,
                    {item_name_expr} AS item_name,
                    {f"TO_CHAR(d.{dtl_uom_col})" if dtl_uom_col else "''"} AS unit,
                    {ordered_expr} AS qty,
                    {received_expr} AS erp_received_qty,
                    {f"NVL(d.{dtl_rate_col},0)" if dtl_rate_col else "0"} AS rate
                FROM {dtl_tbl} d
                {join_item}
                WHERE TO_CHAR(d.{dtl_receipt_col}) = :receipt_no
                ORDER BY {order_stable}
            """
            cur.execute(detail_sql, {"receipt_no": str(receipt_no)})
            rows = cur.fetchall() or []
        else:
            rows = []

        items = [
            {
                "line_seq": idx,
                "item_code": str(row[0] or ""),
                "item_name": str(row[1] or ""),
                "unit": str(row[2] or ""),
                "qty": float(row[3] or 0),
                "erp_received_qty": float(row[4] or 0),
                "rate": float(row[5] or 0),
            }
            for idx, row in enumerate(rows, start=1)
        ]

        if item_tbl and item_code_col and item_name_col:
            missing_codes = [str(x["item_code"]).strip() for x in items if not str(x.get("item_name") or "").strip()]
            missing_codes = [c for c in missing_codes if c]
            if missing_codes:
                code_to_name: dict[str, str] = {}
                chunk_size = 900
                for idx in range(0, len(missing_codes), chunk_size):
                    chunk = missing_codes[idx : idx + chunk_size]
                    binds: dict[str, Any] = {}
                    placeholders: list[str] = []
                    for i, code in enumerate(chunk):
                        key = f"c{i}"
                        placeholders.append(f":{key}")
                        binds[key] = code
                    cur.execute(
                        f"""
                        SELECT TO_CHAR({item_code_col}) AS code, TO_CHAR({item_name_col}) AS name
                        FROM {item_tbl}
                        WHERE TO_CHAR({item_code_col}) IN ({", ".join(placeholders)})
                        """,
                        binds,
                    )
                    for irow in cur.fetchall() or []:
                        code_to_name[str(irow[0] or "").strip()] = str(irow[1] or "")
                for itm in items:
                    if not str(itm.get("item_name") or "").strip():
                        itm["item_name"] = code_to_name.get(str(itm.get("item_code") or "").strip(), "")

        _apply_grn_mobile_line_ext_overlay(
            cur,
            str(receipt_no),
            items,
            overlay_claims_loc=loc_value if str(loc_value or "").strip() else "",
            hdr_location_code=header[9],
        )

        total_qty = sum(float(x.get("qty") or 0) for x in items)
        total_items = len(items)

        remarks_text = str(header[6] or "")

        return {
            "receipt_no": str(header[0] or ""),
            "receipt_date": header[1].strftime("%b %d, %Y") if header[1] else "",
            "supplier": str(header[2] or ""),
            "supplier_name": str(header[3] or "") or supplier_name_fallback,
            "po_no": str(header[4] or ""),
            "invoice_no": "",
            "amount": float(header[5] or 0),
            "remarks": remarks_text,
            "status": derived_status,
            "approval_status": approval_status,
            "lr_flag": lr_hdr,
            "mobile_lines_touched": _t_n,
            "mobile_last_saved_at": _t_d.isoformat() if isinstance(_t_d, datetime) else None,
            "LOCATIONCODE": _coerce_grn_mobile_ext_location_id(header[9]),
            "location_code": str(header[9] or ""),
            "location_name": str(header[10] or ""),
            "grn_date": header[1].strftime("%b %d, %Y") if header[1] else "",
            "po_date": header[1].strftime("%b %d, %Y") if header[1] else "",
            "invoice_date": "",
            "total_items": total_items,
            "total_qty": total_qty,
            "items": items,
        }


def _invalidate_table_columns_cache(cur: Any, table_name: str) -> None:
    key = (_oracle_username_upper(cur), table_name.upper())
    with _CACHE_LOCK:
        _TABLE_COLUMNS_CACHE.pop(key, None)


def _ensure_lpohdr_nexa_grn_status_column(cur: Any) -> str | None:
    """Ensure LPOHDR.NEXA_GRN_STATUS exists; return resolved column name."""
    lpo_hdr = "LPOHDR" if _table_exists(cur, "LPOHDR") else ""
    if not lpo_hdr:
        return None
    cols = _table_columns(cur, lpo_hdr)
    existing = _pick_lpohdr_mobile_grn_status_col(cols)
    if existing:
        return existing
    try:
        cur.execute(
            "ALTER TABLE LPOHDR ADD (NEXA_GRN_STATUS VARCHAR2(40) DEFAULT 'Pending' NOT NULL)"
        )
    except Exception as exc:
        _invalidate_table_columns_cache(cur, lpo_hdr)
        cols = _table_columns(cur, lpo_hdr)
        existing = _pick_lpohdr_mobile_grn_status_col(cols)
        if existing:
            return existing
        raise ValueError(
            "LPOHDR is missing NEXA_GRN_STATUS (or MOBILE_GRN_STATUS). "
            "Run scripts/run_install_lpohdr_nexa_grn_status.py on the tenant database."
        ) from exc
    _invalidate_table_columns_cache(cur, lpo_hdr)
    cols = _table_columns(cur, lpo_hdr)
    return _pick_lpohdr_mobile_grn_status_col(cols) or "NEXA_GRN_STATUS"


def finalize_goods_receiving_without_formal_document(po_no: str) -> dict[str, Any]:
    """
    Mark mobile / shop-floor receiving as finished (NEXA_GRN_STATUS Completed) without inserting RECEIPTHDR.
    Use after Goods Receiving wizard; formal GRN is posted separately via create_goods_receipt.
    """
    claims = get_jwt()
    tenant_id = claims.get("tenant_id")
    po_key = str(po_no or "").strip()
    if not po_key:
        raise ValueError("po_no is required")

    with mobile_operation_lock(
        "po_receive_finalize",
        po_key,
        busy_message="Receiving is already being finalized. Please wait.",
    ):
        conn = get_connection(tenant_id=tenant_id)
        with oracle_transaction(conn):
            with conn.cursor() as cur:
                lpo_hdr = "LPOHDR" if _table_exists(cur, "LPOHDR") else ""
                if not lpo_hdr:
                    raise ValueError("LPOHDR not found")
                grn_st_col = _ensure_lpohdr_nexa_grn_status_column(cur)
                cols = _table_columns(cur, lpo_hdr)
                lpo_pk = _pick_existing(cols, ["LPONO", "LPO_NO"])
                if not lpo_pk:
                    raise ValueError("LPOHDR is missing LPONO / LPO_NO column")
                if not grn_st_col:
                    raise ValueError(
                        "LPOHDR is missing NEXA_GRN_STATUS (or MOBILE_GRN_STATUS). "
                        "Run scripts/run_install_lpohdr_nexa_grn_status.py on the tenant database."
                    )
                cur.execute(
                    f"UPDATE {lpo_hdr} SET {grn_st_col} = :st WHERE TO_CHAR({lpo_pk}) = :po",
                    {"st": "Completed", "po": po_key},
                )
                if cur.rowcount == 0:
                    raise ValueError("Purchase order not found")
    return {"po_no": po_key, "mobile_grn_status": "Completed"}


def create_goods_receipt(payload: dict[str, Any]) -> dict:
    """Legacy GRN create — delegates to ERP-aligned ``grn_service.save_receipt``."""
    from mobile_backend.services import grn_service

    merged = dict(payload or {})
    merged.setdefault("save_mode", "grn_only")
    data = grn_service.save_receipt(merged)
    receipt_no = data.get("receipt_no") or data.get("receiptno") or data.get("receiptNo")
    items = merged.get("items") or []
    return {
        "receipt_no": str(receipt_no or ""),
        "total_amount": float(data.get("total_amount") or data.get("invoice_amount") or 0),
        "items_count": int(data.get("items_count") or (len(items) if isinstance(items, list) else 0)),
    }


def _parse_mobile_expiry(raw: str) -> datetime | None:
    cleaned = str(raw or "").strip()
    if not cleaned:
        return None
    cleaned = cleaned.replace(",", "")
    for fmt in ("%b %d %Y", "%d %b %Y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    return None


def update_lpo_line_snapshot(po_no: str, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Persist receiving details for one LPODTL line.

    Behaviour:
    - If ``GRN_MOBILE_LINE_EXT`` exists (DDL in ``erp_api/sql/grn_mobile_line_ext.sql``), mobile fields are
      MERGEd into that table (bonus, batch, expiry, store, bin, FOC, received qty there).
    - LPODTL: updates **only** ``INQUANTITY`` with the entered ``received_qty``.
    - ``line_seq``: optional row index from ``GET …/grn/<po>`` (1-based, same ORDER BY as list).
      Omit or send 0 when missing: then the LPODTL row is resolved by ``item_code`` (unique per PO — if duplicates exist, ``line_seq`` is required).
    - ``GRN_MOBILE_LINE_EXT`` remains optional for bonus/batch/FOC; those are not written to LPODTL.
    """
    claims = get_jwt()
    tenant_id = claims.get("tenant_id")

    po_no_txt = str(po_no or "").strip()
    item_code_txt = str(payload.get("item_code") or "").strip()

    ls_raw = payload.get("line_seq")
    try:
        if ls_raw is None or (isinstance(ls_raw, str) and not str(ls_raw).strip()):
            line_seq = 0
        else:
            line_seq = int(float(ls_raw))
    except (TypeError, ValueError) as exc:
        raise ValueError("line_seq must be an integer when supplied") from exc

    if not po_no_txt or not item_code_txt:
        raise ValueError("po_no and item_code are required")

    try:
        received_qty = float(payload.get("received_qty") or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("received_qty must be numeric") from exc

    bonus_qty_raw = payload.get("bonus_qty", 0)
    try:
        bonus_qty_val = float(bonus_qty_raw or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("bonus_qty must be numeric") from exc

    foc_enabled = bool(payload.get("foc_enabled", False))

    conn = get_connection(tenant_id=tenant_id)
    with mobile_operation_lock(
        "po_receive_line",
        f"{po_no_txt}:{item_code_txt}:{line_seq}",
        busy_message="This receiving line is already being saved. Please wait.",
    ), oracle_transaction(conn):
        with conn.cursor() as cur:
            maybe_create_grn_mobile_line_ext(cur, conn)
            hdr_tbl, dtl_tbl = _resolve_lpo_tables(cur)
            hdr_cols = _table_columns(cur, hdr_tbl)
            dtl_cols = _table_columns(cur, dtl_tbl)

            hdr_receipt_col = _pick_existing(hdr_cols, ["LPONO", "LPO_NO"])
            hdr_lrflag_col = _pick_existing(hdr_cols, ["LRFLAG", "LR_FLAG"])
            hdr_del_col = _pick_existing(hdr_cols, ["DELFLAG", "DEL_FLAG"])
            hdr_loc_col = _pick_existing(hdr_cols, ["LOCATIONCODE", "LOCATION_CODE"])
            hdr_grn_status_col = _pick_lpohdr_mobile_grn_status_col(hdr_cols)
            pending_lit_patch = "'Pending'"
            mobile_grn_patch_expr = (
            f"NVL(NULLIF(TRIM(TO_CHAR(h.{hdr_grn_status_col})), ''), {pending_lit_patch})"
            if hdr_grn_status_col
            else pending_lit_patch
            )

            dtl_receipt_col = _pick_existing(dtl_cols, ["LPONO", "LPO_NO"])
            dtl_item_col = _pick_existing(dtl_cols, ["ITEMCODE", "ITEM_CODE"])
            if not hdr_receipt_col or not dtl_receipt_col or not dtl_item_col:
                raise ValueError("LPOHDR/LPODTL key columns missing")

                loc_value = claims.get("loc_code") or claims.get("location_code")

                header_sql = f"""
                SELECT
                TO_CHAR(h.{hdr_receipt_col}),
                {f"TO_CHAR(h.{hdr_lrflag_col})" if hdr_lrflag_col else "''"} AS lrflag,
                {f"TO_CHAR(h.{hdr_del_col})" if hdr_del_col else "''"} AS delflag,
                {f"TO_CHAR(h.{hdr_loc_col})" if hdr_loc_col else "''"} AS location_code,
                {mobile_grn_patch_expr} AS mobile_grn_status
                FROM {hdr_tbl} h
                WHERE TO_CHAR(h.{hdr_receipt_col}) = :po_no
                """
                cur.execute(header_sql, {"po_no": po_no_txt})
                hdr_row = cur.fetchone()
                if not hdr_row:
                    raise ValueError("Purchase order not found")

                    hdr_loc_txt = str(hdr_row[3] or "").strip()
                    if loc_value not in (None, "") and hdr_loc_col:
                        jwt_loc = str(loc_value).strip()
                        if jwt_loc and hdr_loc_txt and hdr_loc_txt != jwt_loc:
                            raise ValueError("Location mismatch for this purchase order")

                            lpo_int = int(str(hdr_row[0] or "0")) if str(hdr_row[0] or "").strip().isdigit() else 0
                            approval_map = _get_po_approval_status_map(
                            cur,
                            [lpo_int] if lpo_int > 0 else [],
                            None if loc_value in (None, "") else str(loc_value),
                            )
                            approval_status = approval_map.get(lpo_int, "DRAFT")
                            derived_status = _derive_po_status(
                            del_flag=str(hdr_row[2] if len(hdr_row) > 2 else ""),
                            lr_flag=str(hdr_row[1] if len(hdr_row) > 1 else ""),
                            approval_status=approval_status,
                            )
                            mobile_patch_raw = str(hdr_row[4] or "") if len(hdr_row) > 4 else ""
                            if derived_status != "Cancelled" and _mobile_grn_column_is_completed(mobile_patch_raw):
                                derived_status = "Completed"
                                if derived_status != "Pending":
                                    raise ValueError("Only Pending purchase orders can save line-item changes")

                                    ext_present = _table_exists(cur, _GRN_MOBILE_LINE_EXT_TBL)

                                    inquantity_col = _pick_existing(dtl_cols, ["INQUANTITY", "IN_INV_QTY", "ININV_QTY", "IN_QTY"])
                                    if not inquantity_col:
                                        raise ValueError(
                                        "LPODTL.INQUANTITY is required for receiving line snapshots. "
                                        f"(Optional extras still use {_GRN_MOBILE_LINE_EXT_TBL} when that table exists.)"
                                        )

                                        _, order_stable = _lpodtl_stable_order_exprs(dtl_item_col)

                                        bind_po = {"po_no": po_no_txt, "icode": item_code_txt}
                                        if line_seq >= 1:
                                            rid_sql = f"""
                                            SELECT rid FROM (
                                            SELECT d.ROWID AS rid,
                                            ROW_NUMBER() OVER (ORDER BY {order_stable}) AS rn
                                            FROM {dtl_tbl} d
                                            WHERE TO_CHAR(d.{dtl_receipt_col}) = :po_no
                                            )
                                            WHERE rn = :line_seq
                                            """
                                            cur.execute(rid_sql, {"po_no": po_no_txt, "line_seq": line_seq})
                                            rid_row = cur.fetchone()
                                            if not rid_row:
                                                raise ValueError("Line row not found for this PO and line_seq")
                                                row_rid = rid_row[0]
                                                verify_sql = f"SELECT TO_CHAR(d.{dtl_item_col}) FROM {dtl_tbl} d WHERE d.ROWID = :rid"
                                                cur.execute(verify_sql, {"rid": row_rid})
                                                code_chk = cur.fetchone()
                                                if not code_chk or str(code_chk[0] or "").strip().upper() != item_code_txt.upper():
                                                    raise ValueError("item_code does not match line_seq row on this PO")
                                                else:
                                                    cnt_sql = f"""
                                                    SELECT COUNT(*)
                                                    FROM {dtl_tbl} d
                                                    WHERE TO_CHAR(d.{dtl_receipt_col}) = :po_no
                                                    AND TRIM(UPPER(TO_CHAR(d.{dtl_item_col}))) = TRIM(UPPER(:icode))
                                                    """
                                                    cur.execute(cnt_sql, bind_po)
                                                    n_match = int((cur.fetchone() or [0])[0] or 0)
                                                    if n_match == 0:
                                                        raise ValueError(f"No LPODTL line for PO {po_no_txt} with item_code {item_code_txt}")
                                                        if n_match > 1:
                                                            raise ValueError(
                                                            "Multiple LPODTL lines match this item on the PO — open item details "
                                                            "from a list load that includes line_seq, or consolidate duplicate lines."
                                                            )
                                                            rid_by_item_sql = f"""
                                                            SELECT rid FROM (
                                                            SELECT d.ROWID AS rid,
                                                            ROW_NUMBER() OVER (ORDER BY {order_stable}) AS rn
                                                            FROM {dtl_tbl} d
                                                            WHERE TO_CHAR(d.{dtl_receipt_col}) = :po_no
                                                            AND TRIM(UPPER(TO_CHAR(d.{dtl_item_col}))) = TRIM(UPPER(:icode))
                                                            )
                                                            WHERE rn = 1
                                                            """
                                                            cur.execute(rid_by_item_sql, bind_po)
                                                            rid_row = cur.fetchone()
                                                            if not rid_row:
                                                                raise ValueError("Unable to resolve LPODTL ROWID for this item")
                                                                row_rid = rid_row[0]

                                                                updated_by = str(claims.get("sub") or claims.get("username") or "").strip() or None

                                                                bb_merge = 0.0
                                                                if payload.get("bonus_base_unit") is not None:
                                                                    try:
                                                                        bb_merge = float(payload.get("bonus_base_unit") or 0)
                                                                    except (TypeError, ValueError) as exc:
                                                                        raise ValueError("bonus_base_unit must be numeric") from exc

                                                                        payload_hint = payload.get("LOCATIONCODE")
                                                                        if payload_hint is None:
                                                                            payload_hint = payload.get("location_code")
                                                                            if payload_hint is not None and str(payload_hint).strip():
                                                                                loc_hint = payload_hint
                                                                            elif str(loc_value or "").strip():
                                                                                loc_hint = loc_value
                                                                            else:
                                                                                loc_hint = hdr_loc_txt

                                                                                if ext_present:
                                                                                    _merge_grn_mobile_line_ext(
                                                                                    cur,
                                                                                    po_no=po_no_txt,
                                                                                    line_seq=line_seq,
                                                                                    item_code=item_code_txt,
                                                                                    received_qty=received_qty,
                                                                                    bonus_qty=bonus_qty_val,
                                                                                    foc_enabled=foc_enabled,
                                                                                    bonus_base_unit=bb_merge,
                                                                                    batch_no=str(payload.get("batch_no") or ""),
                                                                                    expiry_raw=str(payload.get("expiry_date") or ""),
                                                                                    store_code=str(payload.get("store_code") or ""),
                                                                                    bin_code=str(payload.get("bin_code") or ""),
                                                                                    updated_by=updated_by,
                                                                                    location_code_hint=loc_hint,
                                                                                    )

                                                                                    cur.execute(
                                                                                    f"UPDATE {dtl_tbl} SET {inquantity_col} = :received_qty WHERE ROWID = :row_rid",
                                                                                    {"received_qty": received_qty, "row_rid": row_rid},
                                                                                    )

                                                                                    return {
                                                                                    "po_no": po_no_txt,
                                                                                    "item_code": item_code_txt,
                                                                                    "line_seq": line_seq,
                                                                                    "saved_mobile_ext": bool(ext_present),
                                                                                    }
