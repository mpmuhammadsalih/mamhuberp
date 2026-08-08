"""Mobile Supplier master — create / list aligned with ERP ``_supplier_save``."""

from __future__ import annotations

from typing import Any

from mobile_backend.database.transaction import oracle_transaction
from mobile_backend.operation_lock import mobile_operation_lock
from mobile_backend.services.stock_transfer_service import _erp_session_scope


def _supplier_mod():
    from addons.supplier.controllers import routes as supplier

    return supplier


def _to_int(v: Any, default: int | None = 0) -> int | None:
    if v is None or (isinstance(v, str) and not str(v).strip()):
        return default
    try:
        return int(float(str(v).strip()))
    except (TypeError, ValueError):
        return default


def _positive_account(v: Any) -> int | None:
    n = _to_int(v, None)
    return n if n is not None and n > 0 else None


def get_open_context() -> dict[str, Any]:
    """Defaults for the create form (next code + GL accounts)."""
    from db import DEFAULT_PARTY_ACCOUNTS, ensure_default_party_accounts, get_next_supplier_code

    with _erp_session_scope():
        s = _supplier_mod()
        try:
            from db import ensure_supplier_table

            ensure_supplier_table()
        except Exception:
            pass
        loc = s._resolve_location_code()
        defs = dict(DEFAULT_PARTY_ACCOUNTS)
        try:
            defs = ensure_default_party_accounts() or defs
        except Exception:
            pass
        return {
            "location_code": loc,
            "next_supplier_code": int(get_next_supplier_code(loc) or 0),
            "default_accounts": {
                "payableaccount": _positive_account(defs.get("supplier_payable")) or 2110,
                "purchaseaccount": _positive_account(defs.get("supplier_purchase")) or 5001,
                "vatinputaccount": _positive_account(defs.get("supplier_vat_input")) or 2200,
                "advanceaccount": _positive_account(defs.get("supplier_advance")) or 1230,
            },
            "supplier_types": ["LOCAL", "INTERNATIONAL"],
        }


def list_suppliers(*, search: str = "", limit: int = 100) -> dict[str, Any]:
    from db import get_supplier_list

    lim = max(1, min(int(limit or 100), 300))
    q = (search or "").strip()
    with _erp_session_scope():
        s = _supplier_mod()
        loc = s._resolve_location_code()
        try:
            from db import ensure_supplier_table

            ensure_supplier_table()
        except Exception:
            pass
        rows = get_supplier_list(
            location_code=loc,
            search=q or None,
            limit=lim,
        )
        out: list[dict[str, Any]] = []
        for raw in rows or []:
            r = dict(raw or {})
            code = r.get("suppliercode") or r.get("supplier_code") or r.get("code")
            try:
                code_i = int(float(str(code))) if code not in (None, "") else 0
            except (TypeError, ValueError):
                code_i = 0
            out.append(
                {
                    "supplier_code": code_i,
                    "supplier_name": str(
                        r.get("suppliername") or r.get("supplier_name") or r.get("name") or ""
                    ).strip(),
                    "supplier_type": str(r.get("suppliertype") or r.get("supplier_type") or "").strip(),
                    "mobile": str(r.get("mobile") or "").strip(),
                    "telephone": str(r.get("telephone") or "").strip(),
                    "contact_person": str(
                        r.get("contactperson") or r.get("contact_person") or ""
                    ).strip(),
                    "address": str(r.get("address") or "").strip(),
                    "email": str(r.get("emailid") or r.get("email") or "").strip(),
                }
            )
        return {"suppliers": out, "count": len(out)}


def create_supplier(payload: dict[str, Any], *, username: str = "mobile") -> dict[str, Any]:
    """Create a supplier using the same rules as ERP master Supplier New."""
    from master_activity_log import append_master_activity
    from master_name_duplicate import find_master_name_duplicate, master_name_duplicate_message
    from db import (
        SUPPLIER_TABLE,
        _detect_column,
        _get_connection,
        ensure_default_party_accounts,
        ensure_supplier_table,
        get_next_supplier_code,
        get_supplier_by_code,
    )

    data = dict(payload or {})
    name_key = str(data.get("suppliername") or data.get("supplier_name") or "").strip()

    with mobile_operation_lock(
        "supplier_create",
        name_key.upper() or "new",
        lock_seconds=90.0,
        busy_message="Supplier is already being saved. Please wait.",
    ), _erp_session_scope() as user:
        s = _supplier_mod()
        try:
            ensure_supplier_table()
        except Exception:
            pass

        location_code = s._resolve_location_code()
        suppliername = name_key
        if not suppliername:
            raise ValueError("Supplier name is required.")
        suppliername = suppliername[:40]

        suppliertype = str(data.get("suppliertype") or data.get("supplier_type") or "LOCAL").strip()[:25]
        if suppliertype.upper() not in ("LOCAL", "INTERNATIONAL"):
            suppliertype = "LOCAL"
        else:
            suppliertype = suppliertype.upper()

        address = str(data.get("address") or "").strip()[:200]
        telephone = str(data.get("telephone") or "").strip()[:15]
        fax = str(data.get("fax") or "").strip()[:15]
        mobile = str(data.get("mobile") or "").strip()[:15]
        emailid = str(data.get("emailid") or data.get("email") or "").strip()[:150]
        contactperson = str(
            data.get("contactperson") or data.get("contact_person") or ""
        ).strip()[:40]
        supplierid = str(data.get("supplierid") or data.get("supplier_id") or "").strip()[:3]
        flag = str(data.get("flag") or "Y").strip()[:1] or "Y"
        supplierlocation = str(
            data.get("supplierlocation") or data.get("supplier_location") or ""
        ).strip()[:30]
        supref = str(data.get("supref") or data.get("supplier_ref") or "").strip()[:50]
        suppliercr = str(data.get("suppliercr") or data.get("cr_no") or "").strip()[:250]
        creationflag = str(data.get("creationflag") or "B").strip()[:1] or "B"

        defs: dict[str, Any] = {}
        try:
            defs = ensure_default_party_accounts() or {}
        except Exception:
            from db import DEFAULT_PARTY_ACCOUNTS

            defs = dict(DEFAULT_PARTY_ACCOUNTS)

        payableaccount = (
            _positive_account(data.get("payableaccount") or data.get("payable_account"))
            or _positive_account(defs.get("supplier_payable"))
        )
        purchaseaccount = (
            _positive_account(data.get("purchaseaccount") or data.get("purchase_account"))
            or _positive_account(defs.get("supplier_purchase"))
        )
        vatinputaccount = (
            _positive_account(data.get("vatinputaccount") or data.get("vat_input_account"))
            or _positive_account(defs.get("supplier_vat_input"))
        )
        advanceaccount = (
            _positive_account(data.get("advanceaccount") or data.get("advance_account"))
            or _positive_account(defs.get("supplier_advance"))
        )

        if not payableaccount:
            raise ValueError("Payable Account is required.")
        if not purchaseaccount:
            raise ValueError("Purchase Account is required.")
        if not vatinputaccount:
            raise ValueError("Input VAT Account is required.")
        if not advanceaccount:
            raise ValueError("Advance Account is required.")

        loc_col = _detect_column(SUPPLIER_TABLE, ["LOCATIONCODE", "locationcode"])
        code_col = _detect_column(SUPPLIER_TABLE, ["SUPPLIERCODE", "suppliercode"])
        name_col = _detect_column(SUPPLIER_TABLE, ["SUPPLIERNAME", "suppliername"])
        if not loc_col or not code_col or not name_col:
            raise ValueError("Supplier table structure error.")

        with _get_connection() as conn:
            with oracle_transaction(conn), conn.cursor() as cur:
                dup_code = find_master_name_duplicate(
                    cur,
                    table=SUPPLIER_TABLE,
                    name_col=name_col,
                    name_value=suppliername,
                    loc_col=loc_col,
                    location_code=location_code,
                    code_col=code_col,
                    exclude_code=None,
                )
                if dup_code is not None:
                    raise ValueError(
                        master_name_duplicate_message(
                            "supplier",
                            suppliername,
                            location_code=location_code,
                            existing_code=dup_code,
                        )
                    )

                code = int(get_next_supplier_code(location_code))
                if get_supplier_by_code(location_code, code):
                    code = int(get_next_supplier_code(location_code))
                    if get_supplier_by_code(location_code, code):
                        raise ValueError(
                            f"Supplier code {code} already exists for this branch. Try again."
                        )

                all_cols = [
                    loc_col,
                    code_col,
                    "SUPPLIERNAME",
                    "SUPPLIERTYPE",
                    "ADDRESS",
                    "TELEPHONE",
                    "FAX",
                    "MOBILE",
                    "EMAILID",
                    "CONTACTPERSON",
                    "SUPPLIERID",
                    "PAYABLEACCOUNT",
                    "PURCHASEACCOUNT",
                    "VATINPUTACCOUNT",
                    "ADVANCEACCOUNT",
                    "FLAG",
                    "SUPPLIERLOCATION",
                    "SUPREF",
                    "SUPPLIERCR",
                    "CREATIONFLAG",
                ]
                col_list = [col for col in all_cols if s._column_exists(SUPPLIER_TABLE, col)]
                ph_map = {
                    loc_col: ":loc",
                    code_col: ":code",
                    "SUPPLIERNAME": ":suppliername",
                    "SUPPLIERTYPE": ":suppliertype",
                    "ADDRESS": ":address",
                    "TELEPHONE": ":telephone",
                    "FAX": ":fax",
                    "MOBILE": ":mobile",
                    "EMAILID": ":emailid",
                    "CONTACTPERSON": ":contactperson",
                    "SUPPLIERID": ":supplierid",
                    "PAYABLEACCOUNT": ":payableaccount",
                    "PURCHASEACCOUNT": ":purchaseaccount",
                    "VATINPUTACCOUNT": ":vatinputaccount",
                    "ADVANCEACCOUNT": ":advanceaccount",
                    "FLAG": ":flag",
                    "SUPPLIERLOCATION": ":supplierlocation",
                    "SUPREF": ":supref",
                    "SUPPLIERCR": ":suppliercr",
                    "CREATIONFLAG": ":creationflag",
                }
                placeholders = ", ".join(ph_map.get(col, "NULL") for col in col_list)
                cols_str = ", ".join(col_list)
                all_insert_params = {
                    "loc": location_code,
                    "code": code,
                    "suppliername": suppliername,
                    "suppliertype": suppliertype or None,
                    "address": address or None,
                    "telephone": telephone or None,
                    "fax": fax or None,
                    "mobile": mobile or None,
                    "emailid": emailid or None,
                    "contactperson": contactperson or None,
                    "supplierid": supplierid or None,
                    "payableaccount": payableaccount,
                    "purchaseaccount": purchaseaccount,
                    "vatinputaccount": vatinputaccount,
                    "advanceaccount": advanceaccount,
                    "flag": flag,
                    "supplierlocation": supplierlocation or None,
                    "supref": supref or None,
                    "suppliercr": suppliercr or None,
                    "creationflag": creationflag,
                }
                bind_names = {
                    (ph_map.get(col, "") or "").replace(":", "").strip()
                    for col in col_list
                    if (ph_map.get(col, "") or "").startswith(":")
                }
                insert_params = {k: v for k, v in all_insert_params.items() if k in bind_names}
                cur.execute(
                    f"INSERT INTO {SUPPLIER_TABLE} ({cols_str}) VALUES ({placeholders})",
                    insert_params,
                )

        nm = suppliername[:120]
        try:
            append_master_activity(
                username=str(user or username or "mobile"),
                action="CREATE",
                entity="supplier",
                summary=f"location={location_code}, supplier_code={code}, name={nm}",
                detail={
                    "locationcode": location_code,
                    "suppliercode": code,
                    "suppliername": nm,
                    "source": "mobile",
                },
            )
        except Exception:
            pass

        return {
            "supplier_code": int(code),
            "supplier_name": suppliername,
            "supplier_type": suppliertype,
            "mobile": mobile,
            "telephone": telephone,
            "message": f"Supplier {suppliername} saved ({code}).",
        }
