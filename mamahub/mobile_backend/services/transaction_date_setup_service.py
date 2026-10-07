"""Transaction Date Setup — wraps ERP ``transaction_date_setup`` for mobile."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from mobile_backend.operation_lock import mobile_operation_lock
from mobile_backend.request_context import get_jwt
from mobile_backend.services.stock_transfer_service import _erp_session_scope


def _claims_user() -> str:
    claims = get_jwt()
    return str(claims.get("sub") or "mobile").strip() or "mobile"


def _is_txn_date_admin() -> bool:
    claims = get_jwt()
    username = str(claims.get("sub") or "").strip().lower()
    if username in {"admin", "super"}:
        return True
    permissions = claims.get("permissions") or []
    if "admin.all" in permissions:
        return True
    return "setup.transaction_date_change_any" in permissions


def _json_safe(value: Any) -> Any:
    """Make ERP payload JSON-serializable for Starlette JSONResponse."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    return str(value)


def _location_options() -> list[dict[str, Any]]:
    from db import list_location_master_rows

    rows = list_location_master_rows() or []
    out: list[dict[str, Any]] = []
    for r in rows:
        rl = {str(k).lower(): v for k, v in (r or {}).items()}
        lc = rl.get("locationcode")
        nm = str(rl.get("locationname") or "").strip()
        if lc is None or str(lc).strip() == "":
            continue
        try:
            code = int(lc)
        except (TypeError, ValueError):
            continue
        out.append({"code": code, "label": f"{code} — {nm}" if nm else str(code), "name": nm})
    return out


def _default_location_code(override: int | None = None) -> int:
    if override is not None and int(override) > 0:
        return int(override)
    from mobile_backend.services.barcode_lookup_service import resolve_location_code

    try:
        return resolve_location_code(None)
    except Exception:
        return 1


def _enrich_payload(payload: dict[str, Any]) -> dict[str, Any]:
    out = dict(payload or {})
    try:
        out["locations"] = _location_options()
    except Exception:
        out["locations"] = out.get("locations") or []
    out["can_change_any_date"] = _is_txn_date_admin()
    return _json_safe(out)


def get_bootstrap(location_code: int | None = None) -> dict[str, Any]:
    from addons.transaction_date_setup.transaction_date_db import build_setup_payload

    with _erp_session_scope():
        lc = _default_location_code(location_code)
        payload = build_setup_payload(lc, allow_any_date=_is_txn_date_admin())
        return _enrich_payload(payload)


def save_setup(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    from addons.transaction_date_setup.transaction_date_db import (
        TXN_DATE_MODULES,
        build_setup_payload,
        save_transaction_date_setup,
    )

    data = payload or {}
    try:
        lc = int(data.get("location_code") or _default_location_code(None))
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid location.") from exc

    mode = str(data.get("mode") or "all").strip().lower()
    if mode not in ("all", "separate"):
        raise ValueError("Mode must be all or separate.")

    all_date = str(data.get("all_date") or "").strip()
    all_date_from = str(data.get("all_date_from") or data.get("all_from") or all_date or "").strip()
    all_date_to = str(data.get("all_date_to") or data.get("all_to") or all_date_from or "").strip()
    module_dates = data.get("module_dates") if isinstance(data.get("module_dates"), dict) else {}
    module_date_from = data.get("module_date_from") if isinstance(data.get("module_date_from"), dict) else {}
    module_date_to = data.get("module_date_to") if isinstance(data.get("module_date_to"), dict) else {}
    module_codes = {mod["key"]: int(mod["default_code"]) for mod in TXN_DATE_MODULES}
    opened_by = _claims_user()

    with mobile_operation_lock("transaction_date_setup_save", str(lc)):
        with _erp_session_scope():
            ok, msg, warnings = save_transaction_date_setup(
                lc,
                mode=mode,
                all_date=all_date or all_date_from,
                all_date_from=all_date_from,
                all_date_to=all_date_to,
                module_dates=module_dates,
                module_date_from={str(k): str(v) for k, v in module_date_from.items()},
                module_date_to={str(k): str(v) for k, v in module_date_to.items()},
                module_codes=module_codes,
                opened_by=opened_by,
                skip_restrictions=_is_txn_date_admin(),
            )
            if not ok:
                raise ValueError(msg or "Failed to save transaction date setup.")
            out = _enrich_payload(build_setup_payload(lc, allow_any_date=_is_txn_date_admin()))
            out["message"] = msg
            out["warnings"] = warnings or []
            return out


def close_setup(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    from addons.transaction_date_setup.transaction_date_db import (
        build_setup_payload,
        close_transaction_date_setup,
    )

    data = payload or {}
    try:
        lc = int(data.get("location_code") or _default_location_code(None))
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid location.") from exc

    mode = str(data.get("mode") or "all").strip().lower()
    if mode not in ("all", "separate"):
        raise ValueError("Mode must be all or separate.")

    raw_keys = data.get("module_keys")
    module_keys: list[str] | None = None
    if isinstance(raw_keys, list):
        module_keys = [str(k).strip() for k in raw_keys if str(k).strip()]
    closed_by = _claims_user()

    with mobile_operation_lock("transaction_date_setup_close", str(lc)):
        with _erp_session_scope():
            ok, msg, warnings = close_transaction_date_setup(
                lc,
                mode=mode,
                module_keys=module_keys,
                closed_by=closed_by,
            )
            if not ok:
                raise ValueError(msg or "Failed to close transaction dates.")
            out = _enrich_payload(build_setup_payload(lc, allow_any_date=_is_txn_date_admin()))
            out["message"] = msg
            out["warnings"] = warnings or []
            return out
