"""Mobile Unit of Measurement master — ERP UNITOFMEASUREMENT."""

from __future__ import annotations

from typing import Any

from mobile_backend.operation_lock import mobile_operation_lock
from mobile_backend.services.stock_transfer_service import _erp_session_scope


def _loc() -> int:
    from addons.itemmaster.controllers import routes as im

    try:
        return int(im._resolve_itemmaster_location_code())
    except Exception:
        return int(im._itemmaster_session_location_code() or 1)


def list_units(*, search: str = "") -> dict[str, Any]:
    from db import get_all_unit_of_measurement

    q = (search or "").strip().upper()
    with _erp_session_scope():
        loc = _loc()
        rows_raw = get_all_unit_of_measurement(location_code=loc) or []
        rows: list[dict[str, Any]] = []
        for r in rows_raw:
            code = str(r.get("unitcode") or r.get("UNITCODE") or "").strip().upper()
            name = str(r.get("unitname") or r.get("UNITNAME") or "").strip()
            if not code:
                continue
            if q and q not in code and q not in name.upper():
                continue
            rows.append({"code": code, "name": name})
        rows.sort(key=lambda x: x["code"])
        return {"location_code": loc, "rows": rows, "count": len(rows)}


def create_unit(*, code: str, name: str, username: str = "mobile") -> dict[str, Any]:
    from db import insert_unit_of_measurement
    from master_activity_log import append_master_activity

    code_u = str(code or "").strip().upper()
    name_s = str(name or "").strip()
    if not code_u:
        raise ValueError("Unit code is required.")
    if len(code_u) > 30:
        code_u = code_u[:30]
    if not name_s:
        raise ValueError("Unit name is required.")
    if len(name_s) > 200:
        name_s = name_s[:200]

    with mobile_operation_lock(
        "unit_master_create",
        code_u,
        lock_seconds=60.0,
        busy_message="Unit is already being saved. Please wait.",
    ), _erp_session_scope() as user:
        loc = _loc()
        ok, err = insert_unit_of_measurement(code_u, name_s)
        if not ok:
            raise ValueError(err or "Failed to create unit.")
        try:
            append_master_activity(
                username=str(username or user or "mobile").strip() or "mobile",
                action="CREATE",
                entity="unit_of_measurement",
                summary=f"location={loc}, code={code_u}, name={name_s[:120]}",
                detail={"locationcode": loc, "code": code_u, "name": name_s},
            )
        except Exception:
            pass
        return {
            "code": code_u,
            "name": name_s,
            "location_code": loc,
            "message": "Unit created.",
        }


def update_unit(*, code: str, name: str, username: str = "mobile") -> dict[str, Any]:
    from db import update_unit_of_measurement
    from master_activity_log import append_master_activity

    code_u = str(code or "").strip().upper()
    name_s = str(name or "").strip()
    if not code_u:
        raise ValueError("Unit code is required.")
    if not name_s:
        raise ValueError("Unit name is required.")
    if len(name_s) > 200:
        name_s = name_s[:200]

    with mobile_operation_lock(
        "unit_master_update",
        code_u,
        lock_seconds=60.0,
        busy_message="Unit is already being saved. Please wait.",
    ), _erp_session_scope() as user:
        loc = _loc()
        ok, err = update_unit_of_measurement(code_u, name_s)
        if not ok:
            raise ValueError(err or "Failed to update unit.")
        try:
            append_master_activity(
                username=str(username or user or "mobile").strip() or "mobile",
                action="UPDATE",
                entity="unit_of_measurement",
                summary=f"location={loc}, code={code_u}, name={name_s[:120]}",
                detail={"locationcode": loc, "code": code_u, "name": name_s},
            )
        except Exception:
            pass
        return {
            "code": code_u,
            "name": name_s,
            "location_code": loc,
            "message": "Unit updated.",
        }


def delete_unit(*, code: str, username: str = "mobile") -> dict[str, Any]:
    from db import delete_unit_of_measurement
    from master_activity_log import append_master_activity

    code_u = str(code or "").strip().upper()
    if not code_u:
        raise ValueError("Unit code is required.")

    with mobile_operation_lock(
        "unit_master_delete",
        code_u,
        lock_seconds=60.0,
        busy_message="Unit is already being deleted. Please wait.",
    ), _erp_session_scope() as user:
        loc = _loc()
        ok, err = delete_unit_of_measurement(code_u)
        if not ok:
            raise ValueError(err or "Failed to delete unit.")
        try:
            append_master_activity(
                username=str(username or user or "mobile").strip() or "mobile",
                action="DELETE",
                entity="unit_of_measurement",
                summary=f"location={loc}, code={code_u}",
                detail={"locationcode": loc, "code": code_u},
            )
        except Exception:
            pass
        return {
            "code": code_u,
            "location_code": loc,
            "message": "Unit deleted.",
        }
