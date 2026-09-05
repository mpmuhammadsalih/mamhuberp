"""Mobile POS Settlement Posting — wraps ERP pos_billing settlement helpers."""

from __future__ import annotations

from typing import Any

from mobile_backend.operation_lock import mobile_operation_lock
from mobile_backend.services.stock_transfer_service import _erp_session_scope


def _pos():
    from addons.pos_billing.controllers import routes as pos

    return pos


def _db():
    import db as dbmod

    return dbmod


def _to_int(v: Any, default: int = 0) -> int:
    try:
        if v is None or v == "":
            return default
        return int(float(str(v).strip()))
    except (TypeError, ValueError):
        return default


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def _fmt_date(v: Any) -> str:
    if v is None:
        return ""
    if hasattr(v, "strftime"):
        try:
            return v.strftime("%Y-%m-%d")
        except Exception:
            pass
    return str(v or "")[:10]


def _location_code(pos: Any) -> int:
    try:
        return int(pos._resolve_location_code())
    except Exception:
        return 1


def get_open_context() -> dict[str, Any]:
    with _erp_session_scope() as username:
        pos = _pos()
        db = _db()
        loc = _location_code(pos)
        # Prefer latest day that still has pending bills (BILLDATE). Closed POSDATE
        # from resolve_pos_settlement_default_date often has zero pending rows.
        default_date = ""
        try:
            pending_days = db.list_pos_settlement_pending_by_date(loc, limit_days=1) or []
            if pending_days:
                default_date = _fmt_date(pending_days[0].get("bill_date"))
        except Exception:
            default_date = ""
        if not default_date:
            default_date = _fmt_date(db.resolve_pos_settlement_default_date(loc))
        defs = db.get_pos_settlement_account_defaults_from_tenders() or {}
        tender_types = []
        try:
            for tr in db.list_pos_tender_types(active_only=True) or []:
                code = str(tr.get("tender_code") or "").strip().upper()
                if not code:
                    continue
                tender_types.append(
                    {
                        "code": code,
                        "name": str(tr.get("tender_name") or code).strip(),
                        "sort_order": _to_int(tr.get("sort_order")),
                    }
                )
        except Exception:
            tender_types = []
        counters = []
        try:
            for r in db.list_pos_counters_for_location(loc) or []:
                cc = _to_int(r.get("countercode"))
                if cc <= 0:
                    continue
                counters.append(
                    {
                        "counter_code": cc,
                        "counter_name": str(r.get("countername") or "").strip(),
                    }
                )
        except Exception:
            counters = []
        accounts = {
            "cash_acc": str(defs.get("cash_acc") or "").strip(),
            "card_acc": str(defs.get("card_acc") or "").strip(),
            "wallet_acc": str(defs.get("wallet_acc") or "").strip(),
            "credit_acc": str(defs.get("credit_acc") or "").strip(),
            "expense_acc": str(defs.get("expense_acc") or "").strip(),
            "short_acc": str(defs.get("short_acc") or "").strip(),
            "excess_acc": str(defs.get("excess_acc") or "").strip(),
            "sales_acc": str(defs.get("sales_acc") or "").strip(),
            "tax_acc": str(defs.get("tax_acc") or "").strip(),
        }
        return {
            "location_code": loc,
            "default_date": default_date,
            "created_by": username,
            "accounts": accounts,
            "tender_types": tender_types,
            "counters": counters,
        }


def list_pending_by_date(*, limit: int = 90) -> dict[str, Any]:
    with _erp_session_scope():
        pos = _pos()
        db = _db()
        loc = _location_code(pos)
        days = db.list_pos_settlement_pending_by_date(loc, limit_days=limit) or []
        return {"days": days, "location_code": loc, "count": len(days)}


def list_drafts(*, limit: int = 40) -> dict[str, Any]:
    with _erp_session_scope():
        pos = _pos()
        db = _db()
        loc = _location_code(pos)
        drafts = db.list_pos_settlement_drafts(loc, limit=limit) or []
        return {"drafts": drafts, "location_code": loc, "count": len(drafts)}


def list_bills(
    *,
    from_date: str = "",
    to_date: str = "",
    settlement_scope: str = "pending",
    limit: int = 500,
) -> dict[str, Any]:
    with _erp_session_scope():
        pos = _pos()
        db = _db()
        loc = _location_code(pos)
        scope = (settlement_scope or "pending").strip().lower()
        if scope not in ("all", "pending", "settled", "cancelled"):
            scope = "pending"
        from_dt = (from_date or "").strip()[:10]
        to_dt = (to_date or "").strip()[:10]
        try:
            db.ensure_billhdr_pos_settlement_columns()
        except Exception:
            pass
        # Use POSDATE (via POS_BILL_PAYMODE) when present so settlement day matches ERP.
        raw = pos._fetch_pos_settlement_candidate_bills(
            loc,
            limit=max(1, min(int(limit or 500), 500)),
            settlement_scope=scope,
            include_credit_sales=False,
            from_dt=from_dt,
            to_dt=to_dt,
            fast=False,
        )
        # Fallback: closed POS day may only match BILLDATE when paymode POSDATE is missing.
        if not raw and (from_dt or to_dt):
            raw = pos._fetch_pos_settlement_candidate_bills(
                loc,
                limit=max(1, min(int(limit or 500), 500)),
                settlement_scope=scope,
                include_credit_sales=False,
                from_dt=from_dt,
                to_dt=to_dt,
                fast=True,
            )
        bills: list[dict[str, Any]] = []
        for r in raw or []:
            if not isinstance(r, dict):
                continue
            bills.append(pos._billhdr_row_to_settlement_bill(r))
        return {
            "bills": bills,
            "location_code": loc,
            "settlement_scope": scope,
            "count": len(bills),
            "from": from_dt,
            "to": to_dt,
        }


def payment_mode_summary(bill_nos: list[Any]) -> dict[str, Any]:
    with _erp_session_scope():
        pos = _pos()
        db = _db()
        loc = _location_code(pos)
        return db.compute_pos_settlement_payment_mode_summary(loc, bill_nos or [])


def get_draft(draft_id: int) -> dict[str, Any]:
    with _erp_session_scope():
        pos = _pos()
        db = _db()
        loc = _location_code(pos)
        detail = db.get_pos_settlement_draft_detail(int(draft_id), loc)
        if not detail:
            raise ValueError("Settlement draft not found for this branch.")
        bill_nos = detail.get("bill_nos") if isinstance(detail.get("bill_nos"), list) else []
        bills: list[dict[str, Any]] = []
        try:
            raw_rows = db._fetch_billhdr_rows_by_billnos(loc, bill_nos)
            for r in raw_rows or []:
                if isinstance(r, dict):
                    bills.append(pos._billhdr_row_to_settlement_bill(r))
        except Exception:
            bills = []
        return {
            "detail": detail,
            "bills": bills,
            "bill_nos": bill_nos,
            "location_code": loc,
        }


def generate_draft(payload: dict[str, Any], *, username: str = "mobile") -> dict[str, Any]:
    bill_nos = payload.get("bill_nos") if isinstance(payload.get("bill_nos"), list) else []
    accounts = payload.get("accounts") if isinstance(payload.get("accounts"), dict) else {}
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    lock_key = f"{(username or 'mobile').strip().upper()}|{len(bill_nos)}"
    with mobile_operation_lock(
        "pos_settlement_generate",
        lock_key,
        lock_seconds=120.0,
        busy_message="A settlement draft is already being created. Please wait.",
    ), _erp_session_scope() as user:
        pos = _pos()
        db = _db()
        loc = _location_code(pos)
        ok, err, draft_id = db.create_pos_settlement_draft(
            loc,
            bill_nos,
            accounts=accounts,
            meta=meta,
            created_by=str(username or user or "mobile").strip()[:100] or "mobile",
        )
        if not ok:
            raise ValueError(err or "Failed to create settlement draft.")
        detail = db.get_pos_settlement_draft_detail(int(draft_id or 0), loc)
        return {
            "draft_id": int(draft_id or 0),
            "detail": detail,
            "location_code": loc,
            "message": "Settlement draft created.",
        }


def verify_draft(draft_id: int) -> dict[str, Any]:
    with mobile_operation_lock(
        "pos_settlement",
        str(int(draft_id)),
        lock_seconds=60.0,
        busy_message="Settlement is already being updated. Please wait.",
    ), _erp_session_scope():
        pos = _pos()
        db = _db()
        loc = _location_code(pos)
        ok, err = db.verify_pos_settlement_draft(int(draft_id), loc)
        if not ok:
            raise ValueError(err or "Failed to verify settlement draft.")
        detail = db.get_pos_settlement_draft_detail(int(draft_id), loc)
        return {"detail": detail, "message": "Settlement verified."}


def cancel_draft(draft_id: int) -> dict[str, Any]:
    with mobile_operation_lock(
        "pos_settlement",
        str(int(draft_id)),
        lock_seconds=60.0,
        busy_message="Settlement is already being updated. Please wait.",
    ), _erp_session_scope():
        pos = _pos()
        db = _db()
        loc = _location_code(pos)
        ok, err = db.cancel_pos_settlement_draft(int(draft_id), loc)
        if not ok:
            raise ValueError(err or "Failed to cancel settlement draft.")
        detail = db.get_pos_settlement_draft_detail(int(draft_id), loc)
        return {"detail": detail, "message": "Settlement cancelled."}


def post_draft(payload: dict[str, Any], *, username: str = "mobile") -> dict[str, Any]:
    draft_id = _to_int(payload.get("draft_id"))
    if draft_id <= 0:
        raise ValueError("Invalid draft_id.")
    voucher_date = str(payload.get("voucher_date") or "").strip()[:10] or None
    narration_extra = str(payload.get("narration_extra") or "").strip()[:500]
    remarks = str(payload.get("remarks") or payload.get("remarks_bills") or "").strip()[:500]
    with mobile_operation_lock(
        "pos_settlement_post",
        str(draft_id),
        lock_seconds=180.0,
        busy_message="A settlement post is already in progress. Please wait.",
    ), _erp_session_scope() as user:
        pos = _pos()
        db = _db()
        loc = _location_code(pos)
        try:
            from addons.accounts.period_closing_db import is_period_closed_for_date

            pc_msg = is_period_closed_for_date(voucher_date, loc)
            if pc_msg:
                raise ValueError(pc_msg)
        except ValueError:
            raise
        except Exception:
            pass
        ok, err, voucher_no = db.post_pos_settlement_draft(
            draft_id,
            loc,
            voucher_date=voucher_date,
            narration_extra=narration_extra,
            remarks_bills=remarks,
            created_by=str(username or user or "mobile").strip()[:50] or "mobile",
        )
        if not ok:
            raise ValueError(err or "Failed to post settlement.")
        detail = db.get_pos_settlement_draft_detail(draft_id, loc)
        return {
            "draft_id": draft_id,
            "voucher_no": str(voucher_no or ""),
            "detail": detail,
            "location_code": loc,
            "message": "Settlement posted.",
        }
