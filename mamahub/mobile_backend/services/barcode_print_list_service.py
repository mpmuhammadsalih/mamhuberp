"""Mobile barcode print-list documents (shared BARCODE_PRINT_HDR / DTL with ERP)."""

from __future__ import annotations

from typing import Any

from mobile_backend.operation_lock import mobile_operation_lock
from mobile_backend.request_context import get_jwt
from mobile_backend.services.barcode_lookup_service import resolve_location_code
from mobile_backend.services.stock_transfer_service import _erp_session_scope


def _username() -> str:
    claims = get_jwt() or {}
    return str(claims.get("sub") or "").strip() or "mobile"


def list_documents(
    *,
    locationcode: int | None = None,
    list_type: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    from addons.barcode_management.barcode_print_list_db import list_print_lists

    with _erp_session_scope():
        loc = None if locationcode in (None, 0) else int(locationcode)
        return list_print_lists(loc, list_type=list_type, limit=limit)


def get_document(print_no: int, *, locationcode: int | None = None) -> dict[str, Any]:
    from addons.barcode_management.barcode_print_list_db import get_print_list

    with _erp_session_scope():
        loc = resolve_location_code(locationcode)
        doc = get_print_list(loc, int(print_no))
        if not doc:
            raise ValueError(f"Print list {print_no} was not found.")
        return doc


def save_document(payload: dict[str, Any]) -> dict[str, Any]:
    from addons.barcode_management.barcode_print_list_db import save_print_list

    loc = resolve_location_code(payload.get("locationcode"))
    try:
        pno_raw = payload.get("print_no")
        pno = int(pno_raw) if pno_raw not in (None, "", 0, "0") else None
    except (TypeError, ValueError):
        pno = None

    lines = payload.get("lines") or []
    if not isinstance(lines, list) or not lines:
        raise ValueError("Add at least one item before saving.")

    user = _username()
    with mobile_operation_lock(
        "barcode_print_list",
        f"{loc}:{pno or 'new'}",
        lock_seconds=60.0,
    ):
        with _erp_session_scope():
            return save_print_list(
                loc,
                print_no=pno,
                list_type=str(payload.get("list_type") or "PRODUCT"),
                status=str(payload.get("status") or "READY"),
                remarks=str(payload.get("remarks") or ""),
                source=str(payload.get("source") or "MOBILE"),
                source_ref=str(payload.get("source_ref") or ""),
                created_by=user,
                lines=lines,
            )
