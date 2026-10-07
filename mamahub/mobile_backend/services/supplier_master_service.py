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


def _normalize_supplier_billing_type(raw: Any) -> str:
    s = str(raw or "").strip().upper()
    if s in ("R", "CREDIT", "CR"):
        return "CREDIT"
    if s in ("C", "CASH", "CA"):
        return "CASH"
    return ""


def _resolve_cash_account() -> int:
    """Default cash GL for cash suppliers (COA Cash Account)."""
    from db import _detect_column, _safe_rows, _table_exists

    if _table_exists("CHART_OF_ACCOUNTS"):
        code_col = _detect_column("CHART_OF_ACCOUNTS", ["CODE", "ACCOUNT_CODE", "ACCOUNTCODE"])
        name_col = _detect_column("CHART_OF_ACCOUNTS", ["NAME", "ACCOUNT_NAME", "ACCOUNTNAME"])
        status_col = _detect_column("CHART_OF_ACCOUNTS", ["STATUS", "status"])
        if code_col:
            where = [f"{code_col} = :c"]
            if status_col:
                where.append(f"UPPER(NVL({status_col}, 'ACTIVE')) = 'ACTIVE'")
            rows = _safe_rows(
                f"SELECT {code_col} AS code FROM CHART_OF_ACCOUNTS WHERE {' AND '.join(where)} AND ROWNUM = 1",
                {"c": "1111"},
            ) or []
            if rows:
                return _positive_account(rows[0].get("code")) or 1111
            if name_col:
                rows = _safe_rows(
                    f"SELECT {code_col} AS code FROM CHART_OF_ACCOUNTS "
                    f"WHERE UPPER({name_col}) LIKE '%CASH ACCOUNT%' "
                    + (f"AND UPPER(NVL({status_col}, 'ACTIVE')) = 'ACTIVE' " if status_col else "")
                    + "AND ROWNUM = 1",
                    {},
                ) or []
                if rows:
                    return _positive_account(rows[0].get("code")) or 1111
    return 1111


def _ensure_supplier_billing_column() -> None:
    """Add SUPPLIER_BILLING_TYPE when missing (Cash / Credit)."""
    from db import SUPPLIER_TABLE, _TABLE_COLUMNS_CACHE, _get_connection, _get_table_columns, ensure_supplier_table

    try:
        ensure_supplier_table()
    except Exception:
        pass
    cols = {str(c).upper() for c in (_get_table_columns(SUPPLIER_TABLE) or [])}
    if "SUPPLIER_BILLING_TYPE" in cols:
        return
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("ALTER TABLE SUPPLIER ADD SUPPLIER_BILLING_TYPE VARCHAR2(10)")
            conn.commit()
        _TABLE_COLUMNS_CACHE.pop(SUPPLIER_TABLE.upper(), None)
    except Exception:
        pass


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
        _ensure_supplier_billing_column()
        loc = s._resolve_location_code()
        defs = dict(DEFAULT_PARTY_ACCOUNTS)
        try:
            defs = ensure_default_party_accounts() or defs
        except Exception:
            pass
        cash_acc = _resolve_cash_account()
        payable_acc = _positive_account(defs.get("supplier_payable")) or 2110
        return {
            "location_code": loc,
            "next_supplier_code": int(get_next_supplier_code(loc) or 0),
            "default_accounts": {
                "cashaccount": cash_acc,
                "payableaccount": payable_acc,
                "purchaseaccount": _positive_account(defs.get("supplier_purchase")) or 5001,
                "vatinputaccount": _positive_account(defs.get("supplier_vat_input")) or 2200,
                "advanceaccount": _positive_account(defs.get("supplier_advance")) or 1230,
            },
            "supplier_types": ["LOCAL", "INTERNATIONAL"],
            "billing_types": ["CASH", "CREDIT"],
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
        _ensure_supplier_billing_column()
        rows = get_supplier_list(
            location_code=loc,
            search=q or None,
            limit=lim,
        )
        # Billing type may not be in get_supplier_list; enrich from SUPPLIER when column exists.
        billing_by_code: dict[int, str] = {}
        try:
            from db import SUPPLIER_TABLE, _detect_column, _safe_rows

            bill_col = _detect_column(
                SUPPLIER_TABLE,
                ["SUPPLIER_BILLING_TYPE", "supplier_billing_type", "BILLING_TYPE"],
            )
            code_col = _detect_column(SUPPLIER_TABLE, ["SUPPLIERCODE", "suppliercode"])
            loc_col = _detect_column(SUPPLIER_TABLE, ["LOCATIONCODE", "locationcode"])
            if bill_col and code_col and loc_col:
                brows = _safe_rows(
                    f"SELECT {code_col} AS code, {bill_col} AS bt FROM {SUPPLIER_TABLE} WHERE {loc_col} = :lc",
                    {"lc": loc},
                ) or []
                for br in brows:
                    ci = _to_int(br.get("code"), 0) or 0
                    bt = _normalize_supplier_billing_type(br.get("bt"))
                    if ci > 0 and bt:
                        billing_by_code[ci] = bt
        except Exception:
            billing_by_code = {}

        out: list[dict[str, Any]] = []
        for raw in rows or []:
            r = dict(raw or {})
            code = r.get("suppliercode") or r.get("supplier_code") or r.get("code")
            try:
                code_i = int(float(str(code))) if code not in (None, "") else 0
            except (TypeError, ValueError):
                code_i = 0
            billing = billing_by_code.get(code_i) or _normalize_supplier_billing_type(
                r.get("supplier_billing_type") or r.get("billing_type")
            )
            out.append(
                {
                    "supplier_code": code_i,
                    "supplier_name": str(
                        r.get("suppliername") or r.get("supplier_name") or r.get("name") or ""
                    ).strip(),
                    "supplier_type": str(r.get("suppliertype") or r.get("supplier_type") or "").strip(),
                    "supplier_billing_type": billing or "",
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
        _ensure_supplier_billing_column()

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

        billing_type = _normalize_supplier_billing_type(
            data.get("supplier_billing_type") or data.get("billing_type")
        )
        if billing_type not in ("CASH", "CREDIT"):
            raise ValueError("Supplier type (Cash / Credit) is required.")

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

        cashaccount = (
            _positive_account(data.get("cashaccount") or data.get("cash_account"))
            or _resolve_cash_account()
        )
        ap_account = (
            _positive_account(data.get("payableaccount") or data.get("payable_account"))
            or _positive_account(defs.get("supplier_payable"))
            or 2110
        )
        # Cash → cash GL; Credit → Accounts Payable (stored on PAYABLEACCOUNT for GRN posting).
        payableaccount = cashaccount if billing_type == "CASH" else ap_account
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
            raise ValueError(
                "Cash Account is required." if billing_type == "CASH" else "Payable Account is required."
            )
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
                    "SUPPLIER_BILLING_TYPE",
                    "ADDRESS",
                    "TELEPHONE",
                    "FAX",
                    "MOBILE",
                    "EMAILID",
                    "CONTACTPERSON",
                    "SUPPLIERID",
                    "ACCOUNTCODE",
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
                    "SUPPLIER_BILLING_TYPE": ":supplier_billing_type",
                    "ADDRESS": ":address",
                    "TELEPHONE": ":telephone",
                    "FAX": ":fax",
                    "MOBILE": ":mobile",
                    "EMAILID": ":emailid",
                    "CONTACTPERSON": ":contactperson",
                    "SUPPLIERID": ":supplierid",
                    "ACCOUNTCODE": ":accountcode",
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
                    "supplier_billing_type": billing_type,
                    "address": address or None,
                    "telephone": telephone or None,
                    "fax": fax or None,
                    "mobile": mobile or None,
                    "emailid": emailid or None,
                    "contactperson": contactperson or None,
                    "supplierid": supplierid or None,
                    "accountcode": payableaccount,
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
            "supplier_billing_type": billing_type,
            "payableaccount": payableaccount,
            "mobile": mobile,
            "telephone": telephone,
            "message": f"Supplier {suppliername} saved ({code}).",
        }


def _serialize_supplier_row(row: dict[str, Any], *, cash_account: int | None = None) -> dict[str, Any]:
    code = _to_int(row.get("suppliercode") or row.get("supplier_code"), 0) or 0
    payable = _positive_account(row.get("payableaccount") or row.get("accountcode"))
    cash_acc = cash_account or _resolve_cash_account()
    billing = _normalize_supplier_billing_type(
        row.get("supplier_billing_type") or row.get("billing_type")
    )
    if billing not in ("CASH", "CREDIT"):
        billing = "CASH" if payable and payable == cash_acc else "CREDIT"
    return {
        "supplier_code": code,
        "supplier_name": str(row.get("suppliername") or row.get("supplier_name") or "").strip(),
        "supplier_type": str(row.get("suppliertype") or row.get("supplier_type") or "").strip().upper(),
        "supplier_billing_type": billing,
        "mobile": str(row.get("mobile") or "").strip(),
        "telephone": str(row.get("telephone") or "").strip(),
        "fax": str(row.get("fax") or "").strip(),
        "email": str(row.get("emailid") or row.get("email") or "").strip(),
        "contact_person": str(row.get("contactperson") or row.get("contact_person") or "").strip(),
        "address": str(row.get("address") or "").strip(),
        "supplier_ref": str(row.get("supref") or row.get("supplier_ref") or "").strip(),
        "supplier_cr": str(row.get("suppliercr") or row.get("cr_no") or "").strip(),
        "supplier_location": str(row.get("supplierlocation") or "").strip(),
        "flag": str(row.get("flag") or "Y").strip() or "Y",
        "creation_flag": str(row.get("creationflag") or "B").strip() or "B",
        "payableaccount": payable,
        "cashaccount": cash_acc,
        "purchaseaccount": _positive_account(row.get("purchaseaccount")),
        "vatinputaccount": _positive_account(row.get("vatinputaccount")),
        "advanceaccount": _positive_account(row.get("advanceaccount")),
    }


def get_supplier(supplier_code: int) -> dict[str, Any]:
    """Load one supplier master row for detail / edit."""
    from db import get_supplier_by_code

    code = int(supplier_code or 0)
    if code <= 0:
        raise ValueError("Supplier code is required.")
    with _erp_session_scope():
        s = _supplier_mod()
        try:
            from db import ensure_supplier_table

            ensure_supplier_table()
        except Exception:
            pass
        _ensure_supplier_billing_column()
        loc = s._resolve_location_code()
        row = get_supplier_by_code(loc, code)
        if not row:
            raise ValueError(f"Supplier {code} was not found.")
        return _serialize_supplier_row(dict(row), cash_account=_resolve_cash_account())


def update_supplier(
    supplier_code: int,
    payload: dict[str, Any],
    *,
    username: str = "mobile",
) -> dict[str, Any]:
    """Update an existing supplier (same fields as ERP supplier edit + billing type)."""
    from master_activity_log import append_master_activity
    from master_name_duplicate import find_master_name_duplicate, master_name_duplicate_message
    from db import (
        SUPPLIER_TABLE,
        _detect_column,
        _get_connection,
        ensure_default_party_accounts,
        ensure_supplier_table,
        get_supplier_by_code,
    )

    code = int(supplier_code or 0)
    if code <= 0:
        raise ValueError("Supplier code is required.")

    data = dict(payload or {})
    name_key = str(data.get("suppliername") or data.get("supplier_name") or "").strip()

    with mobile_operation_lock(
        "supplier_update",
        str(code),
        lock_seconds=90.0,
        busy_message="Supplier is already being saved. Please wait.",
    ), _erp_session_scope() as user:
        s = _supplier_mod()
        try:
            ensure_supplier_table()
        except Exception:
            pass
        _ensure_supplier_billing_column()

        location_code = s._resolve_location_code()
        existing = get_supplier_by_code(location_code, code)
        if not existing:
            raise ValueError(f"Supplier {code} was not found.")
        existing = dict(existing)

        suppliername = name_key or str(existing.get("suppliername") or "").strip()
        if not suppliername:
            raise ValueError("Supplier name is required.")
        suppliername = suppliername[:40]

        suppliertype = str(
            data.get("suppliertype")
            if data.get("suppliertype") is not None
            else data.get("supplier_type")
            if data.get("supplier_type") is not None
            else existing.get("suppliertype")
            or "LOCAL"
        ).strip()[:25]
        if suppliertype.upper() not in ("LOCAL", "INTERNATIONAL"):
            suppliertype = "LOCAL"
        else:
            suppliertype = suppliertype.upper()

        cash_acc = (
            _positive_account(data.get("cashaccount") or data.get("cash_account"))
            or _resolve_cash_account()
        )
        existing_billing = _normalize_supplier_billing_type(
            existing.get("supplier_billing_type") or existing.get("billing_type")
        )
        existing_payable = _positive_account(existing.get("payableaccount") or existing.get("accountcode"))
        if existing_billing not in ("CASH", "CREDIT"):
            existing_billing = "CASH" if existing_payable and existing_payable == cash_acc else "CREDIT"

        billing_type = _normalize_supplier_billing_type(
            data.get("supplier_billing_type") or data.get("billing_type")
        ) or existing_billing
        if billing_type not in ("CASH", "CREDIT"):
            raise ValueError("Supplier type (Cash / Credit) is required.")

        address = str(
            data.get("address") if data.get("address") is not None else existing.get("address") or ""
        ).strip()[:200]
        telephone = str(
            data.get("telephone") if data.get("telephone") is not None else existing.get("telephone") or ""
        ).strip()[:15]
        fax = str(data.get("fax") if data.get("fax") is not None else existing.get("fax") or "").strip()[:15]
        mobile = str(
            data.get("mobile") if data.get("mobile") is not None else existing.get("mobile") or ""
        ).strip()[:15]
        emailid = str(
            data.get("emailid")
            if data.get("emailid") is not None
            else data.get("email")
            if data.get("email") is not None
            else existing.get("emailid")
            or ""
        ).strip()[:150]
        contactperson = str(
            data.get("contactperson")
            if data.get("contactperson") is not None
            else data.get("contact_person")
            if data.get("contact_person") is not None
            else existing.get("contactperson")
            or ""
        ).strip()[:40]
        supplierid = str(
            data.get("supplierid") if data.get("supplierid") is not None else existing.get("supplierid") or ""
        ).strip()[:3]
        flag = str(data.get("flag") or existing.get("flag") or "Y").strip()[:1] or "Y"
        supplierlocation = str(
            data.get("supplierlocation")
            if data.get("supplierlocation") is not None
            else existing.get("supplierlocation")
            or ""
        ).strip()[:30]
        supref = str(
            data.get("supref")
            if data.get("supref") is not None
            else data.get("supplier_ref")
            if data.get("supplier_ref") is not None
            else existing.get("supref")
            or ""
        ).strip()[:50]
        suppliercr = str(
            data.get("suppliercr")
            if data.get("suppliercr") is not None
            else data.get("cr_no")
            if data.get("cr_no") is not None
            else existing.get("suppliercr")
            or ""
        ).strip()[:250]
        creationflag = str(
            data.get("creationflag") or existing.get("creationflag") or "B"
        ).strip()[:1] or "B"

        defs: dict[str, Any] = {}
        try:
            defs = ensure_default_party_accounts() or {}
        except Exception:
            from db import DEFAULT_PARTY_ACCOUNTS

            defs = dict(DEFAULT_PARTY_ACCOUNTS)

        ap_account = (
            _positive_account(data.get("payableaccount") or data.get("payable_account"))
            or (
                existing_payable
                if existing_billing == "CREDIT" and existing_payable and existing_payable != cash_acc
                else None
            )
            or _positive_account(defs.get("supplier_payable"))
            or 2110
        )
        if billing_type == "CASH":
            payableaccount = (
                cash_acc
                if existing_billing != "CASH"
                else (existing_payable or cash_acc)
            )
            if data.get("cashaccount") is not None or data.get("cash_account") is not None:
                payableaccount = cash_acc
        else:
            payableaccount = ap_account

        purchaseaccount = (
            _positive_account(existing.get("purchaseaccount"))
            or _positive_account(data.get("purchaseaccount") or data.get("purchase_account"))
            or _positive_account(defs.get("supplier_purchase"))
        )
        vatinputaccount = (
            _positive_account(existing.get("vatinputaccount"))
            or _positive_account(data.get("vatinputaccount") or data.get("vat_input_account"))
            or _positive_account(defs.get("supplier_vat_input"))
        )
        advanceaccount = (
            _positive_account(existing.get("advanceaccount"))
            or _positive_account(data.get("advanceaccount") or data.get("advance_account"))
            or _positive_account(defs.get("supplier_advance"))
        )

        if not payableaccount:
            raise ValueError(
                "Cash Account is required." if billing_type == "CASH" else "Payable Account is required."
            )
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
                    exclude_code=code,
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

                val_by_param = {
                    "suppliername": suppliername,
                    "suppliertype": suppliertype or None,
                    "supplier_billing_type": billing_type,
                    "address": address or None,
                    "telephone": telephone or None,
                    "fax": fax or None,
                    "mobile": mobile or None,
                    "emailid": emailid or None,
                    "contactperson": contactperson or None,
                    "supplierid": supplierid or None,
                    "accountcode": payableaccount,
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
                set_parts: list[str] = []
                upd_params: dict[str, Any] = {"loc": location_code, "code": code}
                for col, param in [
                    ("SUPPLIERNAME", "suppliername"),
                    ("SUPPLIERTYPE", "suppliertype"),
                    ("SUPPLIER_BILLING_TYPE", "supplier_billing_type"),
                    ("ADDRESS", "address"),
                    ("TELEPHONE", "telephone"),
                    ("FAX", "fax"),
                    ("MOBILE", "mobile"),
                    ("EMAILID", "emailid"),
                    ("CONTACTPERSON", "contactperson"),
                    ("SUPPLIERID", "supplierid"),
                    ("ACCOUNTCODE", "accountcode"),
                    ("PAYABLEACCOUNT", "payableaccount"),
                    ("PURCHASEACCOUNT", "purchaseaccount"),
                    ("VATINPUTACCOUNT", "vatinputaccount"),
                    ("ADVANCEACCOUNT", "advanceaccount"),
                    ("FLAG", "flag"),
                    ("SUPPLIERLOCATION", "supplierlocation"),
                    ("SUPREF", "supref"),
                    ("SUPPLIERCR", "suppliercr"),
                    ("CREATIONFLAG", "creationflag"),
                ]:
                    if s._column_exists(SUPPLIER_TABLE, col):
                        set_parts.append(f"{col} = :{param}")
                        upd_params[param] = val_by_param[param]
                if not set_parts:
                    raise ValueError("No updatable columns found.")
                cur.execute(
                    f"UPDATE {SUPPLIER_TABLE} SET {', '.join(set_parts)} "
                    f"WHERE {loc_col} = :loc AND {code_col} = :code",
                    upd_params,
                )

        nm = suppliername[:120]
        try:
            append_master_activity(
                username=str(user or username or "mobile"),
                action="UPDATE",
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
            "supplier_billing_type": billing_type,
            "payableaccount": payableaccount,
            "mobile": mobile,
            "telephone": telephone,
            "message": f"Supplier {suppliername} updated ({code}).",
        }


def delete_supplier(
    supplier_code: int, *, password: str, username: str = "mobile"
) -> dict[str, Any]:
    """Delete supplier for the current location after password check."""
    from master_activity_log import append_master_activity
    from db import SUPPLIER_TABLE, _detect_column, _get_connection
    from mobile_backend.services.master_delete_auth import require_master_delete_password

    code = int(supplier_code or 0)
    if code <= 0:
        raise ValueError("Supplier code is required.")
    require_master_delete_password(password, username=username)

    with mobile_operation_lock(
        "supplier_delete",
        str(code),
        busy_message="Supplier delete is already running. Please wait.",
    ), _erp_session_scope() as user:
        from db import get_supplier_by_code

        s = _supplier_mod()
        location_code = s._resolve_location_code()
        row = get_supplier_by_code(location_code, code)
        if not row:
            raise ValueError(f"Supplier {code} not found.")
        existing = dict(row)
        name = str(
            existing.get("suppliername")
            or existing.get("supplier_name")
            or existing.get("name")
            or ""
        ).strip()[:200]

        loc_col = _detect_column(SUPPLIER_TABLE, ["LOCATIONCODE", "locationcode"])
        code_col = _detect_column(SUPPLIER_TABLE, ["SUPPLIERCODE", "suppliercode"])
        if not code_col:
            raise ValueError("Required supplier columns not found.")

        with _get_connection() as conn:
            with oracle_transaction(conn), conn.cursor() as cur:
                if loc_col:
                    cur.execute(
                        f"DELETE FROM {SUPPLIER_TABLE} WHERE {loc_col} = :loc AND {code_col} = :code",
                        {"loc": int(location_code), "code": code},
                    )
                else:
                    cur.execute(
                        f"DELETE FROM {SUPPLIER_TABLE} WHERE {code_col} = :code",
                        {"code": code},
                    )
                if int(cur.rowcount or 0) <= 0:
                    raise ValueError(f"Failed to delete supplier {code}.")

        try:
            append_master_activity(
                username=str(user or username or "mobile"),
                action="DELETE",
                entity="supplier",
                summary=f"location={location_code}, supplier_code={code}, name={name[:80]}",
                detail={
                    "locationcode": location_code,
                    "suppliercode": code,
                    "suppliername": name,
                    "source": "mobile",
                },
            )
        except Exception:
            pass

        return {
            "supplier_code": code,
            "supplier_name": name,
            "message": f"Supplier {name or code} deleted ({code}).",
        }
