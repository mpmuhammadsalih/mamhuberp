"""Mobile Journal Entry — wraps ERP GL journal + draft helpers."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from mobile_backend.database.transaction import oracle_transaction
from mobile_backend.operation_lock import mobile_operation_lock
from mobile_backend.services.dashboard_service import _to_float
from mobile_backend.services.stock_transfer_service import _erp_session_scope


def _accounts():
    from addons.accounts.controllers import routes as accounts

    return accounts


def _fmt_date(v: Any) -> str:
    if v is None:
        return ""
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d")
    return str(v or "")[:10]


def _norm_code(raw: Any) -> str:
    s = str(raw or "").strip()
    if not s:
        return ""
    try:
        f = float(s)
        if f.is_integer():
            return str(int(f))
    except (TypeError, ValueError):
        pass
    return s


def _dash_clean(raw: Any) -> str:
    s = str(raw or "").strip()
    return "" if s in ("", "—", "-") else s


def _acc_scope():
    a = _accounts()
    a._apply_db()
    try:
        from db import ensure_gl_tables

        ensure_gl_tables()
    except Exception:
        pass
    a._je_ensure_draft_table()
    return a


def _normalize_line(raw: dict[str, Any]) -> dict[str, Any] | None:
    account_code = _norm_code(raw.get("account_code") or raw.get("account"))
    debit = max(0.0, round(_to_float(raw.get("debit")), 2))
    credit = max(0.0, round(_to_float(raw.get("credit")), 2))
    remarks = str(raw.get("remarks") or "").strip()[:250]
    party_type = str(raw.get("party_type") or "").strip().upper()[:20]
    if party_type not in ("CUSTOMER", "SUPPLIER", ""):
        party_type = ""
    party_code = _norm_code(raw.get("party_code"))[:50]
    cost_center = str(raw.get("cost_center") or "").strip()[:50]
    department = str(raw.get("department") or "").strip()[:50]
    project = str(raw.get("project") or "").strip()[:50]
    if not account_code and debit <= 0 and credit <= 0 and not remarks and not party_code:
        return None
    return {
        "account_code": account_code,
        "debit": debit,
        "credit": credit,
        "remarks": remarks,
        "party_type": party_type,
        "party_code": party_code,
        "cost_center": cost_center,
        "department": department,
        "project": project,
    }


def _parse_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    header = dict(payload.get("header") or payload)
    lines_in = list(payload.get("lines") or [])
    voucher_date = str(header.get("voucher_date") or "")[:10]
    if not voucher_date:
        voucher_date = datetime.now().strftime("%Y-%m-%d")
    data = {
        "draft_id": str(header.get("draft_id") or "").strip()[:30],
        "edit_voucher_no": str(
            header.get("edit_voucher_no") or header.get("voucher_no") or ""
        ).strip()[:30],
        "voucher_date": voucher_date,
        "reference_no": str(header.get("reference_no") or "").strip()[:50],
        "narration": str(header.get("narration") or "").strip()[:500],
        "default_cost_center": str(header.get("default_cost_center") or "").strip()[:50],
        "default_department": str(header.get("default_department") or "").strip()[:50],
        "default_project": str(header.get("default_project") or "").strip()[:50],
    }
    # When posting a new voucher, edit_voucher_no must not be confused with draft id.
    if data["edit_voucher_no"].upper().startswith("JED"):
        if not data["draft_id"]:
            data["draft_id"] = data["edit_voucher_no"]
        data["edit_voucher_no"] = ""

    lines: list[dict[str, Any]] = []
    for raw in lines_in:
        ln = _normalize_line(dict(raw or {}))
        if ln is not None:
            lines.append(ln)

    dim_defaults = {
        "cost_center": data["default_cost_center"] or None,
        "department": data["default_department"] or None,
        "project": data["default_project"] or None,
    }
    return data, lines, dim_defaults


def _line_totals(lines: list[dict[str, Any]]) -> tuple[float, float]:
    dr = round(sum(max(0.0, _to_float(x.get("debit"))) for x in lines), 2)
    cr = round(sum(max(0.0, _to_float(x.get("credit"))) for x in lines), 2)
    return dr, cr


def _normalize_list_row(row: dict[str, Any], *, status: str) -> dict[str, Any]:
    vno = str(row.get("voucher_no") or row.get("VOUCHER_NO") or row.get("draft_id") or "").strip()
    source = str(row.get("source") or row.get("SOURCE") or "").strip().upper()
    st = (status or str(row.get("status") or "")).strip().upper()
    if not st:
        st = "DRAFT" if source == "DRAFT" else "POSTED"
    draft_id = str(row.get("draft_id") or "").strip()
    if st == "DRAFT" and not draft_id:
        draft_id = vno
    return {
        "voucher_no": vno,
        "draft_id": draft_id,
        "voucher_date": _fmt_date(row.get("voucher_date") or row.get("VOUCHER_DATE")),
        "reference_no": str(row.get("reference_no") or row.get("REFERENCE_NO") or "").strip(),
        "narration": str(row.get("narration") or row.get("NARRATION") or "").strip(),
        "source": source or ("DRAFT" if st == "DRAFT" else "MANUAL"),
        "status": st,
        "created_by": str(row.get("created_by") or row.get("CREATED_BY") or "").strip(),
        "total_debit": round(_to_float(row.get("total_debit") or row.get("TOTAL_DEBIT")), 2),
        "total_credit": round(_to_float(row.get("total_credit") or row.get("TOTAL_CREDIT")), 2),
        "line_count": int(row.get("line_count") or row.get("LINE_COUNT") or 0),
        "can_edit": st == "DRAFT" or (st == "POSTED" and source == "MANUAL"),
        "can_post": st == "DRAFT",
        # Align with ERP: only Direct JV (MANUAL) and Cash Payment Voucher (CPV).
        "can_reverse": st == "POSTED" and source in ("MANUAL", "CPV"),
    }


def get_open_context() -> dict[str, Any]:
    with _erp_session_scope() as username:
        a = _acc_scope()
        period = a._accounts_closed_period_context()
        voucher_date = str(
            period.get("default_voucher_date") or datetime.now().strftime("%Y-%m-%d")
        )[:10]
        from db import DEFAULT_PARTY_ACCOUNTS

        return {
            "voucher_date": voucher_date,
            "created_by": username,
            "default_customer_receivable": str(
                DEFAULT_PARTY_ACCOUNTS.get("customer_receivable") or "1200"
            ).strip(),
            "default_supplier_payable": str(
                DEFAULT_PARTY_ACCOUNTS.get("supplier_payable") or "2110"
            ).strip(),
            "closed_periods": period.get("closed_periods") or [],
            "sources": a._je_source_filter_options(),
        }


def list_accounts(*, q: str = "", limit: int = 200) -> list[dict[str, Any]]:
    lim = max(1, min(int(limit or 200), 500))
    needle = (q or "").strip().lower()
    with _erp_session_scope():
        _acc_scope()
        from db import get_all_chart_of_accounts

        rows = get_all_chart_of_accounts() or []
        out: list[dict[str, Any]] = []
        for r in rows:
            code = _norm_code(r.get("code"))
            name = str(r.get("name") or "").strip()
            if not code:
                continue
            if not bool(r.get("is_postable")):
                continue
            if str(r.get("status") or "ACTIVE").upper() != "ACTIVE":
                continue
            if needle and needle not in code.lower() and needle not in name.lower():
                continue
            out.append(
                {
                    "code": code,
                    "name": name or code,
                    "type": str(r.get("type") or "").strip(),
                }
            )
            if len(out) >= lim:
                break
        return out


def list_customers(*, q: str = "", limit: int = 80) -> list[dict[str, Any]]:
    lim = max(1, min(int(limit or 80), 200))
    needle = (q or "").strip().lower()
    with _erp_session_scope():
        from db import get_customers_for_journal_party_select

        rows = get_customers_for_journal_party_select(limit=20000) or []
        out: list[dict[str, Any]] = []
        for r in rows:
            code = _norm_code(r.get("customercode"))
            name = str(r.get("customername") or "").strip()
            if not code:
                continue
            if needle and needle not in code.lower() and needle not in name.lower():
                continue
            out.append(
                {
                    "party_code": code,
                    "party_name": name or code,
                    "gl_account": _norm_code(r.get("receivableaccount")),
                    "party_type": "CUSTOMER",
                }
            )
            if len(out) >= lim:
                break
        return out


def list_suppliers(*, q: str = "", limit: int = 80) -> list[dict[str, Any]]:
    lim = max(1, min(int(limit or 80), 200))
    needle = (q or "").strip()
    with _erp_session_scope():
        from db import get_supplier_list

        rows = get_supplier_list(
            location_code=None, search=needle or None, limit=lim, row_cap=lim * 4
        ) or []
        out: list[dict[str, Any]] = []
        for r in rows:
            code = _norm_code(r.get("suppliercode"))
            name = str(r.get("suppliername") or "").strip()
            if not code:
                continue
            out.append(
                {
                    "party_code": code,
                    "party_name": name or code,
                    "gl_account": _norm_code(r.get("payableaccount")),
                    "party_type": "SUPPLIER",
                }
            )
            if len(out) >= lim:
                break
        return out


def list_journals(
    *,
    search: str = "",
    status: str = "all",
    source: str = "all",
    date_from: str = "",
    date_to: str = "",
    limit: int = 100,
) -> dict[str, Any]:
    lim = max(1, min(int(limit or 100), 500))
    st = (status or "all").strip().lower()
    src = (source or "all").strip().upper()
    if src in ("", "ALL", "*"):
        src = "all"
    q = (search or "").strip().lower()
    df = str(date_from or "").strip()[:10]
    dt = str(date_to or "").strip()[:10]

    with _erp_session_scope():
        a = _acc_scope()
        from db import list_gl_journal_entries

        drafts: list[dict[str, Any]] = []
        posted: list[dict[str, Any]] = []
        if st in ("all", "draft"):
            drafts = [
                _normalize_list_row(r, status="DRAFT")
                for r in (a._je_list_drafts(date_from=df or None, date_to=dt or None) or [])
            ]
        if st in ("all", "posted"):
            gl_source = None if src == "all" or src == "DRAFT" else src
            if src != "DRAFT":
                for r in list_gl_journal_entries(
                    date_from=df or None,
                    date_to=dt or None,
                    limit=lim,
                    source=gl_source,
                ) or []:
                    posted.append(_normalize_list_row(dict(r), status="POSTED"))

        rows = drafts + posted
        if q:
            rows = [
                r
                for r in rows
                if q in r["voucher_no"].lower()
                or q in r["reference_no"].lower()
                or q in r["narration"].lower()
                or q in r["source"].lower()
            ]
        if src != "all":
            rows = [r for r in rows if r["source"] == src or (src == "DRAFT" and r["status"] == "DRAFT")]

        def _sort_key(r: dict[str, Any]) -> tuple:
            return (r.get("voucher_date") or "", r.get("voucher_no") or "")

        rows.sort(key=_sort_key, reverse=True)
        rows = rows[:lim]
        return {"vouchers": rows}


def _detail_from_draft(draft: dict[str, Any]) -> dict[str, Any]:
    draft_id = str(draft.get("draft_id") or draft.get("DRAFT_ID") or "").strip()
    lines_raw = draft.get("lines") or []
    lines: list[dict[str, Any]] = []
    for i, raw in enumerate(lines_raw or [], start=1):
        ln = _normalize_line(dict(raw or {}))
        if ln is None:
            continue
        lines.append(
            {
                "line_no": i,
                "account_code": ln["account_code"],
                "account_name": "",
                "debit": ln["debit"],
                "credit": ln["credit"],
                "remarks": ln["remarks"],
                "party_type": ln["party_type"],
                "party_code": ln["party_code"],
                "party_name": "",
                "cost_center": ln["cost_center"],
                "department": ln["department"],
                "project": ln["project"],
            }
        )
    # Enrich account names
    try:
        from db import get_all_chart_of_accounts

        by_code = {
            _norm_code(r.get("code")): str(r.get("name") or "").strip()
            for r in (get_all_chart_of_accounts() or [])
        }
        for ln in lines:
            ln["account_name"] = by_code.get(ln["account_code"], "")
    except Exception:
        pass
    tdr, tcr = _line_totals(lines)
    return {
        "voucher_no": draft_id,
        "draft_id": draft_id,
        "edit_voucher_no": "",
        "voucher_date": _fmt_date(draft.get("voucher_date") or draft.get("VOUCHER_DATE")),
        "reference_no": str(draft.get("reference_no") or draft.get("REFERENCE_NO") or "").strip(),
        "narration": str(draft.get("narration") or draft.get("NARRATION") or "").strip(),
        "source": "DRAFT",
        "status": "DRAFT",
        "created_by": str(draft.get("created_by") or draft.get("CREATED_BY") or "").strip(),
        "default_cost_center": str(
            draft.get("default_cost_center") or draft.get("DEFAULT_COST_CENTER") or ""
        ).strip(),
        "default_department": str(
            draft.get("default_department") or draft.get("DEFAULT_DEPARTMENT") or ""
        ).strip(),
        "default_project": str(
            draft.get("default_project") or draft.get("DEFAULT_PROJECT") or ""
        ).strip(),
        "total_debit": tdr,
        "total_credit": tcr,
        "reversal_voucher_no": "",
        "can_edit": True,
        "can_post": True,
        "can_reverse": False,
        "lines": lines,
    }


def _detail_from_voucher(detail: dict[str, Any], a: Any) -> dict[str, Any]:
    from db import get_gl_voucher_reversal_no

    vno = str(detail.get("voucher_no") or "").strip()
    source = str(detail.get("source") or "").strip().upper()
    can_edit = bool(a._je_voucher_can_edit(detail))
    can_reverse = bool(a._je_voucher_can_reverse(detail))
    rev = ""
    try:
        rev = str(get_gl_voucher_reversal_no(vno) or "").strip()
    except Exception:
        rev = ""
    lines: list[dict[str, Any]] = []
    for ln in detail.get("lines") or []:
        lines.append(
            {
                "line_no": int(ln.get("line_no") or 0),
                "account_code": _norm_code(ln.get("account_code")),
                "account_name": _dash_clean(ln.get("account_name")),
                "debit": round(_to_float(ln.get("debit")), 2),
                "credit": round(_to_float(ln.get("credit")), 2),
                "remarks": _dash_clean(ln.get("remarks")),
                "party_type": _dash_clean(ln.get("party_type")).upper(),
                "party_code": _dash_clean(ln.get("party_code")),
                "party_name": _dash_clean(
                    ln.get("party_name") or ln.get("customer_name") or ln.get("supplier_name")
                ),
                "cost_center": _dash_clean(ln.get("cost_center")),
                "department": _dash_clean(ln.get("department")),
                "project": _dash_clean(ln.get("project")),
            }
        )
    return {
        "voucher_no": vno,
        "draft_id": "",
        "edit_voucher_no": vno if can_edit else "",
        "voucher_date": _fmt_date(detail.get("voucher_date")),
        "reference_no": str(detail.get("reference_no") or "").strip(),
        "narration": str(detail.get("narration") or "").strip(),
        "source": source,
        "status": "POSTED",
        "created_by": str(detail.get("created_by") or "").strip(),
        "default_cost_center": "",
        "default_department": "",
        "default_project": "",
        "total_debit": round(_to_float(detail.get("total_debit")), 2),
        "total_credit": round(_to_float(detail.get("total_credit")), 2),
        "reversal_voucher_no": rev,
        "can_edit": can_edit,
        "can_post": False,
        "can_reverse": can_reverse and not rev,
        "lines": lines,
    }


def get_detail(doc_id: str) -> dict[str, Any] | None:
    key = str(doc_id or "").strip()
    if not key:
        return None
    with _erp_session_scope():
        a = _acc_scope()
        from db import get_gl_voucher_detail

        # Prefer draft when id looks like JED… or exists in draft table.
        draft = a._je_get_draft(key)
        if draft and str(draft.get("status") or draft.get("STATUS") or "DRAFT").upper() == "DRAFT":
            return _detail_from_draft(draft)

        detail = get_gl_voucher_detail(key)
        if not detail:
            return None
        return _detail_from_voucher(detail, a)


def save_draft(payload: dict[str, Any], *, username: str = "mobile") -> dict[str, Any]:
    data, lines, _dims = _parse_payload(payload)
    doc = data.get("draft_id") or data.get("edit_voucher_no") or ""
    with mobile_operation_lock(
        "journal",
        doc,
        busy_message="Journal entry is already being saved. Please wait.",
    ):
        with _erp_session_scope() as user:
            a = _acc_scope()
            if data.get("edit_voucher_no") and not data.get("draft_id"):
                raise ValueError("Save as draft is not available while editing a posted voucher.")
            msgs = a._je_validate_lines_for_save(
                lines, "draft", voucher_date=data.get("voucher_date")
            )
            if msgs:
                raise ValueError("; ".join(msgs))
            draft_id = a._je_upsert_draft(data, lines, user or username)
            tdr, tcr = _line_totals(lines)
            return {
                "voucher_no": draft_id,
                "draft_id": draft_id,
                "status": "DRAFT",
                "total_debit": tdr,
                "total_credit": tcr,
                "message": f"Journal draft saved: {draft_id}",
            }


def _mark_draft_posted(a: Any, draft_id: str, voucher_no: str, username: str, conn: Any) -> None:
    if not draft_id:
        return
    table = a._JE_DRAFT_TABLE
    with conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE {table}
               SET STATUS = 'POSTED',
                   POSTED_VOUCHER_NO = :vno,
                   UPDATED_BY = :usr,
                   UPDATED_AT = SYSTIMESTAMP
             WHERE DRAFT_ID = :did
            """,
            {
                "vno": voucher_no,
                "usr": (username or "")[:50] or None,
                "did": draft_id,
            },
        )


def post_journal(payload: dict[str, Any], *, username: str = "mobile") -> dict[str, Any]:
    data, lines, dim_defaults = _parse_payload(payload)
    doc = data.get("edit_voucher_no") or data.get("draft_id") or ""
    with mobile_operation_lock(
        "journal",
        doc,
        lock_seconds=120.0,
        busy_message="Journal entry is already being posted. Please wait.",
    ):
        with _erp_session_scope() as user:
            a = _acc_scope()
            msgs = a._je_validate_lines_for_save(
                lines, "post", voucher_date=data.get("voucher_date")
            )
            if msgs:
                raise ValueError("; ".join(msgs))

            from db import (
                _get_connection,
                create_gl_journal_entry,
                get_gl_voucher_detail,
                update_gl_journal_entry,
            )

            edit_vno = data.get("edit_voucher_no") or ""
            if edit_vno:
                detail_chk = get_gl_voucher_detail(edit_vno)
                if not a._je_voucher_can_edit(detail_chk):
                    raise ValueError("This voucher cannot be edited.")
                with _get_connection() as conn:
                    with oracle_transaction(conn):
                        update_gl_journal_entry(
                            edit_vno,
                            voucher_date=data["voucher_date"],
                            reference_no=data["reference_no"],
                            narration=data["narration"],
                            lines=lines,
                            dimension_defaults=dim_defaults,
                            conn=conn,
                            commit=False,
                        )
                tdr, tcr = _line_totals(lines)
                return {
                    "voucher_no": edit_vno,
                    "draft_id": "",
                    "status": "POSTED",
                    "total_debit": tdr,
                    "total_credit": tcr,
                    "message": f"Journal updated successfully. Voucher No: {edit_vno}",
                }

            with _get_connection() as conn:
                with oracle_transaction(conn):
                    voucher_no = create_gl_journal_entry(
                        voucher_date=data["voucher_date"],
                        reference_no=data["reference_no"],
                        narration=data["narration"],
                        lines=lines,
                        created_by=user or username,
                        source="MANUAL",
                        dimension_defaults=dim_defaults,
                        conn=conn,
                        commit=False,
                    )
                    if data.get("draft_id"):
                        _mark_draft_posted(
                            a, data["draft_id"], voucher_no, user or username, conn
                        )
            tdr, tcr = _line_totals(lines)
            return {
                "voucher_no": voucher_no,
                "draft_id": data.get("draft_id") or "",
                "status": "POSTED",
                "total_debit": tdr,
                "total_credit": tcr,
                "message": f"Journal posted successfully. Voucher No: {voucher_no}",
            }


def reverse_journal(
    voucher_no: str,
    *,
    voucher_date: str = "",
    remarks: str = "",
    username: str = "mobile",
) -> dict[str, Any]:
    vno = str(voucher_no or "").strip()
    if not vno:
        raise ValueError("Voucher number is required.")
    with mobile_operation_lock(
        "journal_reverse",
        vno,
        lock_seconds=120.0,
        busy_message="Journal reversal is already in progress. Please wait.",
    ):
        with _erp_session_scope() as user:
            a = _acc_scope()
            from db import (
                _get_connection,
                get_gl_voucher_detail,
                reverse_gl_journal_voucher,
            )

            detail = get_gl_voucher_detail(vno)
            if not detail:
                raise ValueError("Voucher not found.")
            if not a._je_voucher_can_reverse(detail):
                raise ValueError("This voucher cannot be reversed.")
            vdate = str(voucher_date or detail.get("voucher_date") or "")[:10]
            with _get_connection() as conn:
                with oracle_transaction(conn):
                    rev_no = reverse_gl_journal_voucher(
                        vno,
                        voucher_date=vdate or None,
                        remarks=str(remarks or "").strip()[:250],
                        created_by=user or username,
                        conn=conn,
                        commit=False,
                    )
                    if str(detail.get("source") or "").strip().upper() == "CPV":
                        a._cpv_mark_reversed_for_gl(vno, user or username, conn=conn)
            return {
                "voucher_no": vno,
                "reversal_voucher_no": rev_no,
                "status": "REVERSED",
                "message": f"Journal reversed. Reversal voucher: {rev_no}",
            }


def build_pdf(voucher_no: str) -> tuple[bytes, str]:
    vno = str(voucher_no or "").strip()
    if not vno:
        raise ValueError("Voucher number is required.")
    with _erp_session_scope():
        a = _acc_scope()
        from db import get_gl_voucher_detail

        if vno.upper().startswith("JED"):
            raise ValueError("PDF is available after posting the journal.")
        detail = get_gl_voucher_detail(vno)
        if not detail:
            raise ValueError("Voucher not found.")
        pdf_bytes = a._build_journal_voucher_pdf(detail)
        if not pdf_bytes:
            raise ValueError("PDF generation failed (reportlab not available).")
        safe = "".join(c for c in vno if c.isalnum() or c in ("-", "_"))[:44] or "journal"
        return pdf_bytes, f"Journal_{safe}.pdf"
