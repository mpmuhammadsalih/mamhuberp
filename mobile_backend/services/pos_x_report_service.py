"""Mobile Sales X Report — same totals as ERP POS X Report / POS Sales List summary."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

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


def _parse_iso(s: str | None) -> date | None:
    raw = str(s or "").strip()[:10]
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


def _location_code(pos: Any) -> int:
    try:
        return int(pos._resolve_location_code())
    except Exception:
        return 1


def _cashier_label(username: str) -> str:
    return (username or "").strip() or "mobile"


def get_open_context() -> dict[str, Any]:
    """Counters + default POS date for the X Report screen."""
    with _erp_session_scope() as username:
        pos = _pos()
        db = _db()
        loc = _location_code(pos)
        default_date = date.today().isoformat()
        try:
            pending = db.list_pos_settlement_pending_by_date(loc, limit_days=1) or []
            if pending:
                d = pending[0].get("bill_date")
                if hasattr(d, "isoformat"):
                    default_date = d.isoformat()[:10]
                elif d:
                    default_date = str(d)[:10]
        except Exception:
            pass
        if not default_date:
            try:
                default_date = str(db.resolve_pos_settlement_default_date(loc) or "")[:10]
            except Exception:
                default_date = date.today().isoformat()
        counters: list[dict[str, Any]] = [{"counter_code": 0, "counter_name": "All counters"}]
        try:
            for r in db.list_pos_counters_for_location(loc) or []:
                cc = _to_int(r.get("countercode"))
                if cc <= 0:
                    continue
                counters.append(
                    {
                        "counter_code": cc,
                        "counter_name": str(r.get("countername") or "").strip() or f"Counter {cc}",
                    }
                )
        except Exception:
            pass
        return {
            "location_code": loc,
            "default_date": default_date or date.today().isoformat(),
            "created_by": username,
            "counters": counters,
        }


def _enrich_list_summary(report: dict[str, Any], *, loc: int, cashier: str) -> dict[str, Any]:
    """Map POS sales-list summary into X Report shape (receipt/PDF compatible)."""
    db = _db()
    now_ts = datetime.now()
    fd = str(report.get("from_date") or "")[:10]
    td = str(report.get("to_date") or "")[:10]
    try:
        fd_d = datetime.strptime(fd, "%Y-%m-%d").date() if fd else date.today()
        date_disp = fd_d.strftime("%d/%b/%Y")
        if td and td != fd:
            td_d = datetime.strptime(td, "%Y-%m-%d").date()
            date_disp = f"{fd_d.strftime('%d/%b/%Y')} – {td_d.strftime('%d/%b/%Y')}"
    except ValueError:
        date_disp = fd or td or ""
    loc_info = {}
    try:
        loc_info = db.get_location_info_by_dbkey(None) or {}
    except Exception:
        loc_info = {}
    cc = report.get("counter_code")
    cn = ""
    if cc:
        try:
            cn = (db.get_counter_name_by_code(int(cc), db_key=None, location_code=loc) or "").strip()
        except Exception:
            cn = ""
    else:
        cn = "All counters"
    cash = float(report.get("cash_in_box") or 0)
    card = float(report.get("card_total") or 0)
    wallet = float(report.get("wallet_total") or 0)
    collection = round(cash + card + wallet, 2)
    out = dict(report)
    out.update(
        {
            "ok": True,
            "is_final": False,
            "location_code": loc,
            "location_name": str(loc_info.get("locationname") or "").strip(),
            "location_phones": str(loc_info.get("telephone") or loc_info.get("phone") or "").strip(),
            "counter_code": cc,
            "counter_name": cn,
            "pos_date": fd,
            "pos_date_display": date_disp,
            "check_time_display": now_ts.strftime("%d/%b/%Y %I:%M:%S %p").replace(" 0", " "),
            "cashier": cashier,
            "discount_lines": round(float(report.get("total_discount") or 0), 2),
            "credit_on_account": round(float(report.get("credit_sales") or 0), 2),
            "collection_total": collection,
            "payment_lines": report.get("payment_lines") or [],
        }
    )
    return out


def get_x_report(
    *,
    counter_code: int = 0,
    pos_date: str = "",
    date_from: str = "",
    date_to: str = "",
    is_final: bool = False,
) -> dict[str, Any]:
    """Build X Report payload (same numbers as ERP POS Counter Operations / Sales List)."""
    with _erp_session_scope() as username:
        pos = _pos()
        db = _db()
        loc = _location_code(pos)
        cashier = _cashier_label(username)
        cc = _to_int(counter_code)
        single = _parse_iso(pos_date) or _parse_iso(date_from) or date.today()
        d_from = _parse_iso(date_from) or single
        d_to = _parse_iso(date_to) or single
        if d_from > d_to:
            d_from, d_to = d_to, d_from

        # Classic POS X Report: one counter + one business day.
        if cc > 0 and d_from == d_to:
            report = db.build_pos_shift_preclose_report(
                loc,
                cc,
                d_from,
                db_key=None,
                cashier=cashier,
                is_final=bool(is_final),
            )
            if not report.get("ok"):
                raise ValueError(str(report.get("error") or "Failed to build X Report."))
        else:
            report = db.build_pos_sales_list_summary(
                loc,
                from_date=d_from,
                to_date=d_to,
                counter_code=cc if cc > 0 else None,
                shift_code=None,
                db_key=None,
            )
            if not report.get("ok"):
                raise ValueError(str(report.get("error") or "Failed to build X Report."))
            report = _enrich_list_summary(report, loc=loc, cashier=cashier)
            report["is_final"] = False

        receipt_text = ""
        try:
            receipt_text = pos._shift_preclose_to_plain_text(report) or ""
        except Exception:
            receipt_text = ""
        return {
            "report": report,
            "receipt_text": receipt_text,
            "location_code": loc,
        }


def build_x_report_pdf(
    *,
    counter_code: int = 0,
    pos_date: str = "",
    date_from: str = "",
    date_to: str = "",
    is_final: bool = False,
) -> tuple[bytes, str]:
    data = get_x_report(
        counter_code=counter_code,
        pos_date=pos_date,
        date_from=date_from,
        date_to=date_to,
        is_final=is_final,
    )
    report = data.get("report") or {}
    with _erp_session_scope():
        pos = _pos()
        pdf_bytes = pos._shift_preclose_pdf_bytes(report)
        if not pdf_bytes:
            raise ValueError("Failed to generate X Report PDF.")
    prefix = "shift_close" if report.get("is_final") else "x_report"
    day = str(report.get("pos_date") or date.today().isoformat())[:10].replace("-", "")
    cc = _to_int(report.get("counter_code"))
    suffix = f"c{cc}" if cc > 0 else "all"
    return pdf_bytes, f"{prefix}_{day}_{suffix}.pdf"
