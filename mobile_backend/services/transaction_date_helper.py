"""Resolve / enforce document dates from Transaction Date Setup (TBLTRANSACTIONDATE)."""

from __future__ import annotations

from typing import Any, Optional

# Same codes as ERP ``TXN_DATE_MODULES``.
MODULE_CODES: dict[str, int] = {
    "sales": 1,
    "purchase": 2,
    "sales_return": 3,
    "purchase_return": 4,
    "grn": 5,
    "transfer": 6,
    # Stock adjustment has no dedicated code — follow Purchase open window.
    "stock_adjustment": 2,
    # Sales orders follow Sales open window.
    "sales_order": 1,
}

MODULE_LABELS: dict[str, str] = {
    "sales": "Sales Invoice",
    "purchase": "Purchase Order",
    "sales_return": "Sales Return",
    "purchase_return": "Purchase Return",
    "grn": "GRN",
    "transfer": "Stock Transfer",
    "stock_adjustment": "Stock Adjustment",
    "sales_order": "Sales Order",
}


def module_code(module_key: str) -> int:
    key = str(module_key or "").strip().lower()
    if key not in MODULE_CODES:
        raise ValueError(f"Unknown transaction date module: {module_key}")
    return MODULE_CODES[key]


def resolve_location_code(override: int | None = None) -> int:
    if override is not None:
        try:
            lc = int(override)
            if lc > 0:
                return lc
        except (TypeError, ValueError):
            pass
    from mobile_backend.services.barcode_lookup_service import resolve_location_code as _resolve

    try:
        return int(_resolve(None))
    except Exception:
        return 1


def missing_setup_date_message(module_key: str | None = None) -> str:
    """User-facing error when Transaction Date Setup has no open From–To range."""
    key = str(module_key or "").strip().lower()
    label = MODULE_LABELS.get(key) if key else None
    if label:
        return (
            f"Setup date is missing for {label}. "
            "No open From–To date range in Transaction Date Setup. "
            "Open a date range in General Setup → Transaction Date Setup before posting."
        )
    return (
        "Setup date is missing. "
        "No open From–To date range in Transaction Date Setup. "
        "Open a date range in General Setup → Transaction Date Setup before posting."
    )


def _block_message(module_key: str) -> str:
    return missing_setup_date_message(module_key)


def get_open_range(
    module_key: str,
    *,
    location_code: int | None = None,
) -> Optional[dict[str, str]]:
    from addons.transaction_date_setup.transaction_date_db import get_open_transaction_date_range

    lc = resolve_location_code(location_code)
    tc = module_code(module_key)
    try:
        return get_open_transaction_date_range(lc, tc)
    except Exception:
        return None


def open_context(
    module_key: str,
    *,
    location_code: int | None = None,
) -> dict[str, Any]:
    """Bootstrap fields for mobile forms (preferred + From/To + blocked flag)."""
    lc = resolve_location_code(location_code)
    rng = get_open_range(module_key, location_code=lc)
    preferred = (rng or {}).get("preferred") or (rng or {}).get("date_from") or ""
    date_from = (rng or {}).get("date_from") or preferred
    date_to = (rng or {}).get("date_to") or date_from
    return {
        "location_code": lc,
        "module": str(module_key or "").strip().lower(),
        "preferred_date": preferred,
        "open_transaction_date": preferred,
        "open_date_from": date_from,
        "open_date_to": date_to,
        "bill_date": preferred,
        "bill_date_from": date_from,
        "bill_date_to": date_to,
        "transaction_date_open": bool(rng),
        "transaction_date_blocked": not bool(rng),
        "transaction_date_error": None if rng else _block_message(module_key),
    }


def preferred_date(
    module_key: str,
    *,
    location_code: int | None = None,
) -> str:
    ctx = open_context(module_key, location_code=location_code)
    return str(ctx.get("preferred_date") or "")[:10]


def resolve_doc_date(
    module_key: str,
    submitted: Any = None,
    *,
    location_code: int | None = None,
    snap_out_of_range: bool = True,
    required: bool = True,
) -> str:
    """
    Return YYYY-MM-DD inside the open Transaction Date Setup window.

    - Blank submitted → preferred date in range
    - Out of range → snap to preferred when ``snap_out_of_range`` (mobile default)
    - No open row → ValueError when ``required``
    """
    lc = resolve_location_code(location_code)
    rng = get_open_range(module_key, location_code=lc)
    if not rng:
        if required:
            raise ValueError(_block_message(module_key))
        return str(submitted or "").strip()[:10]

    preferred = str(rng.get("preferred") or rng.get("date_from") or "")[:10]
    date_from = str(rng.get("date_from") or preferred)[:10]
    date_to = str(rng.get("date_to") or date_from)[:10]
    sub = str(submitted or "").strip()[:10]
    if not sub:
        return preferred
    if date_from <= sub <= date_to:
        return sub
    if snap_out_of_range:
        return preferred
    if date_from == date_to:
        raise ValueError(f"Date must be {date_from}.")
    raise ValueError(f"Date must be between {date_from} and {date_to}.")
