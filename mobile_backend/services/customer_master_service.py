"""Mobile Customer master — create / list aligned with ERP ``_customer_save``."""

from __future__ import annotations

from typing import Any

from mobile_backend.database.transaction import oracle_transaction
from mobile_backend.operation_lock import mobile_operation_lock
from mobile_backend.services.stock_transfer_service import _erp_session_scope


def _customer_mod():
    from addons.customer.controllers import routes as customer

    return customer


def _to_float(v: Any, default: float = 0.0) -> float:
    if v is None or (isinstance(v, str) and not str(v).strip()):
        return default
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return default


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
    """Defaults for the create form (next code + GL accounts + categories)."""
    with _erp_session_scope():
        c = _customer_mod()
        c._ensure_customer_account_columns()
        loc = c._resolve_location_code()
        defs = c._cached_default_accounts()
        try:
            from db import ensure_default_party_accounts

            ensure_default_party_accounts()
            defs = c._cached_default_accounts()
        except Exception:
            pass
        categories: list[dict[str, Any]] = []
        try:
            for raw in c._get_category_list(loc) or []:
                r = dict(raw or {})
                code = r.get("code")
                if code in (None, ""):
                    continue
                categories.append(
                    {
                        "code": str(code).strip(),
                        "name": str(r.get("name") or "").strip(),
                    }
                )
        except Exception:
            categories = []
        return {
            "location_code": loc,
            "next_customer_code": int(c._get_next_customer_code(loc) or 0),
            "categories": categories,
            "default_accounts": {
                "receivableaccount": _positive_account(defs.get("customer_receivable")) or 1200,
                "salesaccount": _positive_account(defs.get("customer_sales")) or 4100,
                "vatoutputaccount": _positive_account(defs.get("customer_vat_output")) or 2200,
                "advanceaccount": _positive_account(defs.get("customer_advance")) or 2130,
            },
            "default_credit_term": 2,
        }


def list_customers(*, search: str = "", limit: int = 100) -> dict[str, Any]:
    from db import get_customers_master_list

    lim = max(1, min(int(limit or 100), 300))
    q = (search or "").strip()
    with _erp_session_scope():
        rows = get_customers_master_list(
            for_picker=True,
            picker_search=q,
            picker_limit=lim,
        )
        out: list[dict[str, Any]] = []
        for raw in rows or []:
            r = dict(raw or {})
            code = r.get("customercode") or r.get("customer_code") or r.get("code")
            try:
                code_i = int(float(str(code))) if code not in (None, "") else 0
            except (TypeError, ValueError):
                code_i = 0
            billing = str(
                r.get("customer_billing_type") or r.get("billing_type") or r.get("billtype") or ""
            ).strip().upper()
            if billing in ("R", "CREDIT"):
                billing = "CREDIT"
            elif billing in ("C", "CASH"):
                billing = "CASH"
            out.append(
                {
                    "customer_code": code_i,
                    "customer_name": str(r.get("customername") or r.get("customer_name") or r.get("name") or "").strip(),
                    "mobile": str(r.get("mobile") or "").strip(),
                    "telephone": str(r.get("telephone") or "").strip(),
                    "customer_billing_type": billing or "CASH",
                    "credit_limit": _to_float(r.get("creditlimit") or r.get("credit_limit")),
                    "address": str(r.get("address") or "").strip(),
                }
            )
        return {"customers": out, "count": len(out)}


def create_customer_category(payload: dict[str, Any], *, username: str = "mobile") -> dict[str, Any]:
    """Create a row in ERP ``TBLCUSTOMERCATEGORY`` (same as Customer Category master)."""
    from db import _detect_column, _fetch_rows, _get_connection, _table_exists
    from master_activity_log import append_master_activity

    name = str(
        (payload or {}).get("categoryname")
        or (payload or {}).get("category_name")
        or (payload or {}).get("name")
        or ""
    ).strip()
    if not name:
        raise ValueError("Category name is required.")
    if len(name) > 150:
        name = name[:150]

    with mobile_operation_lock(
        "customer_category_create",
        name.upper(),
        lock_seconds=60.0,
        busy_message="Customer category is already being saved. Please wait.",
    ), _erp_session_scope() as user:
        c = _customer_mod()
        loc = c._resolve_location_code()
        tbl = None
        for t in ("TBLCUSTOMERCATEGORY", "tblcustomercategory", "CUSTOMERCATEGORY", "customercategory"):
            if _table_exists(t):
                tbl = t
                break
        if not tbl:
            raise ValueError("Customer category table (TBLCUSTOMERCATEGORY) not found.")

        loc_col = _detect_column(tbl, ["LOCATIONCODE", "LOCATION_CODE", "locationcode"])
        code_col = _detect_column(tbl, ["CATEGORYCODE", "categorycode", "CODE", "code"])
        name_col = _detect_column(tbl, ["CATEGORYNAME", "categoryname", "NAME", "name"])
        if not code_col or not name_col:
            raise ValueError("Category table is missing CATEGORYCODE or CATEGORYNAME.")

        next_code = 1
        try:
            if loc_col:
                _, rows = _fetch_rows(
                    f"SELECT NVL(MAX({code_col}), 0) + 1 AS nxt FROM {tbl} WHERE {loc_col} = :lc",
                    {"lc": loc},
                )
            else:
                _, rows = _fetch_rows(
                    f"SELECT NVL(MAX({code_col}), 0) + 1 AS nxt FROM {tbl}",
                    {},
                )
            if rows:
                next_code = int(rows[0].get("nxt") or 1)
        except Exception:
            next_code = 1

        # Reject duplicate name in the same branch (case-insensitive).
        try:
            if loc_col:
                _, dup = _fetch_rows(
                    f"SELECT {code_col} AS code FROM {tbl} "
                    f"WHERE {loc_col} = :lc AND UPPER({name_col}) = UPPER(:nm) AND ROWNUM = 1",
                    {"lc": loc, "nm": name},
                )
            else:
                _, dup = _fetch_rows(
                    f"SELECT {code_col} AS code FROM {tbl} "
                    f"WHERE UPPER({name_col}) = UPPER(:nm) AND ROWNUM = 1",
                    {"nm": name},
                )
            if dup:
                raise ValueError("A customer category with this name already exists.")
        except ValueError:
            raise
        except Exception:
            pass

        conn = _get_connection()
        with oracle_transaction(conn), conn.cursor() as cur:
            if loc_col:
                cur.execute(
                    f"INSERT INTO {tbl} ({loc_col}, {code_col}, {name_col}) "
                    f"VALUES (:lc, :cc, :nm)",
                    {"lc": loc, "cc": next_code, "nm": name},
                )
            else:
                cur.execute(
                    f"INSERT INTO {tbl} ({code_col}, {name_col}) VALUES (:cc, :nm)",
                    {"cc": next_code, "nm": name},
                )

        try:
            append_master_activity(
                username=str(username or user or "mobile").strip() or "mobile",
                action="CREATE",
                entity="customer_category",
                summary=f"location={loc}, category_code={next_code}, name={name}",
                detail={"locationcode": loc, "categorycode": next_code, "categoryname": name},
            )
        except Exception:
            pass

        return {
            "code": str(next_code),
            "name": name,
            "location_code": loc,
            "message": "Customer category created.",
        }


def create_customer(payload: dict[str, Any], *, username: str = "mobile") -> dict[str, Any]:
    """Create a customer using the same rules as ERP master Customer New."""
    from master_activity_log import append_master_activity
    from master_name_duplicate import find_master_name_duplicate, master_name_duplicate_message
    from db import (
        _detect_column,
        _get_connection,
        _get_table_columns,
        _table_exists,
        normalize_customer_billing_type,
    )

    data = dict(payload or {})
    name_key = str(data.get("customername") or data.get("customer_name") or "").strip().upper()

    with mobile_operation_lock(
        "customer_create",
        name_key or "new",
        lock_seconds=90.0,
        busy_message="Customer is already being saved. Please wait.",
    ), _erp_session_scope() as user:
        c = _customer_mod()
        c._ensure_customer_account_columns()
        tbl = c._customer_table()
        if not tbl:
            raise ValueError("Customer table not found.")

        location_code = c._resolve_location_code()
        customername = name_key
        if not customername:
            raise ValueError("Customer name is required.")

        designation = str(data.get("designation") or "").strip()[:100]
        sex_raw = str(data.get("sex") or "MALE").strip().upper()
        cussex = "M" if sex_raw in ("MALE", "M") else "F"
        address = str(data.get("address") or "").strip()[:200]
        nationality = str(data.get("nationality") or "").strip()[:100]
        telephone = str(data.get("telephone") or "").strip()[:15]
        fax = str(data.get("fax") or "").strip()[:15]
        mobile = str(data.get("mobile") or "").strip()[:15]
        creditlimit = _to_float(data.get("creditlimit") or data.get("credit_limit"), 0)
        creditterms = _to_float(
            data.get("creditterm") if data.get("creditterm") is not None else data.get("credit_term"),
            2,
        )
        duedays = creditterms
        currentcredit = _to_float(data.get("currentcredit") or data.get("current_credit"), 0)
        salesmancode = _to_int(data.get("salesmancode") or data.get("salesman_code"), 0) or 0
        billing_type = normalize_customer_billing_type(
            data.get("customer_billing_type") or data.get("billing_type")
        )
        customercategory = _to_int(data.get("customercategory") or data.get("customer_category"), 0) or 0
        bysalesman = _to_int(data.get("bysalesman") or data.get("by_salesman"), 0) or 0
        routeno = _to_int(data.get("routeno") or data.get("route_no"), 0) or 0
        street = str(data.get("street") or "").strip()[:200]
        zone = str(data.get("zone") or "").strip()[:100]
        pobox = str(data.get("pobox") or data.get("po_box") or "").strip()[:50]
        crno = str(data.get("crno") or data.get("cr_no") or "").strip()[:250]
        email = str(data.get("email") or "").strip()[:150]
        qatarid = str(data.get("qatarid") or data.get("qatar_id") or "").strip()[:50]
        whatsapp = str(data.get("whatsapp") or "").strip()[:20]
        flag = str(data.get("flag") or "Y").strip().upper()[:1] or "Y"
        closed = str(data.get("closed") or "N").strip().upper()[:1] or "N"
        employeecode = _to_int(data.get("employeecode") or data.get("employee_code"), None)
        reason = str(data.get("reason") or "").strip()[:500]
        otherreason = str(data.get("otherreason") or "").strip()[:500]
        closedreason = str(data.get("closedreason") or "").strip()[:500]
        countersale = "Y" if str(data.get("countersale") or "").strip().upper() == "Y" else "N"

        defs = c._cached_default_accounts()
        receivableaccount = (
            _positive_account(data.get("receivableaccount") or data.get("receivable_account"))
            or _positive_account(defs.get("customer_receivable"))
        )
        salesaccount = (
            _positive_account(data.get("salesaccount") or data.get("sales_account"))
            or _positive_account(defs.get("customer_sales"))
        )
        vatoutputaccount = (
            _positive_account(data.get("vatoutputaccount") or data.get("vat_output_account"))
            or _positive_account(defs.get("customer_vat_output"))
        )
        advanceaccount = (
            _positive_account(data.get("advanceaccount") or data.get("advance_account"))
            or _positive_account(defs.get("customer_advance"))
        )

        if billing_type not in ("CASH", "CREDIT"):
            raise ValueError("Customer type (Cash / Credit) is required.")
        if (
            receivableaccount is None
            or salesaccount is None
            or vatoutputaccount is None
            or advanceaccount is None
        ):
            raise ValueError(
                "Default customer GL accounts are not configured. Set them in ERP, then try again."
            )
        if not mobile and not telephone:
            raise ValueError("Mobile No or Telephone is required.")
        if billing_type == "CREDIT":
            if not creditlimit or creditlimit <= 0:
                raise ValueError("Credit Limit is required for Credit customers.")
            if not creditterms or creditterms <= 0:
                raise ValueError("Credit Term (Days) is required for Credit customers.")

        loc_col = _detect_column(tbl, ["LOCATIONCODE", "locationcode"])
        code_col = _detect_column(tbl, ["CUSTOMERCODE", "customercode"])
        name_col = _detect_column(tbl, ["CUSTOMERNAME", "customername"])
        if not loc_col or not code_col:
            raise ValueError("Required customer columns not found.")

        with _get_connection() as conn:
            with oracle_transaction(conn), conn.cursor() as cur:
                if name_col:
                    dup_code = find_master_name_duplicate(
                        cur,
                        table=tbl,
                        name_col=name_col,
                        name_value=customername,
                        loc_col=loc_col,
                        location_code=location_code,
                        code_col=code_col,
                        exclude_code=None,
                    )
                    if dup_code is not None:
                        raise ValueError(
                            master_name_duplicate_message(
                                "customer",
                                customername,
                                location_code=location_code,
                                existing_code=dup_code,
                            )
                        )

                code = _to_int(data.get("customercode") or data.get("customer_code"), None)
                if code is None:
                    code = int(c._get_next_customer_code(location_code))
                if c._get_customer_by_code(location_code, int(code)):
                    code = int(c._get_next_customer_code(location_code))
                    if c._get_customer_by_code(location_code, int(code)):
                        raise ValueError(
                            f"Customer code {code} already exists for this branch. Try again."
                        )

                all_cols = [
                    loc_col,
                    code_col,
                    "CCODE",
                    "CUSTOMERNAME",
                    "DESIGNATION",
                    "SEX",
                    "ADDRESS",
                    "NATIONALITY",
                    "TELEPHONE",
                    "FAX",
                    "MOBILE",
                    "CREDITLIMIT",
                    "CREDITTERMS",
                    "DUEDAYS",
                    "CURRENTCREDITAMOUNT",
                    "SALESMANCODE",
                    "CUSTOMER_BILLING_TYPE",
                    "FLAG",
                    "CLOSED",
                    "CUSTOMERCATEGORY",
                    "BYSALESMAN",
                    "ROUTENO",
                    "STREET",
                    "ZONE",
                    "POBOX",
                    "CRNO",
                    "RECEIVABLEACCOUNT",
                    "SALESACCOUNT",
                    "VATOUTPUTACCOUNT",
                    "ADVANCEACCOUNT",
                    "EMAIL",
                    "QATARID",
                    "WHATSAPP",
                    "EMPLOYEECODE",
                    "REASON",
                    "OTHERREASON",
                    "CLOSEDREASON",
                    "COUNTERSALE",
                ]
                col_list = [col for col in all_cols if c._column_exists(tbl, col)]
                if "CREATEDDATE" in _get_table_columns(tbl):
                    col_list.append("CREATEDDATE")

                all_params: dict[str, Any] = {
                    "loc": location_code,
                    "code": code,
                    "customername": customername,
                    "designation": designation,
                    "cussex": cussex,
                    "address": address,
                    "nationality": nationality,
                    "telephone": telephone,
                    "fax": fax,
                    "mobile": mobile,
                    "creditlimit": creditlimit,
                    "creditterms": creditterms,
                    "duedays": duedays,
                    "currentcredit": currentcredit,
                    "salesmancode": salesmancode,
                    "customer_billing_type": billing_type,
                    "customercategory": customercategory,
                    "bysalesman": bysalesman,
                    "routeno": routeno,
                    "street": street,
                    "zone": zone,
                    "pobox": pobox,
                    "crno": crno,
                    "receivableaccount": receivableaccount,
                    "salesaccount": salesaccount,
                    "vatoutputaccount": vatoutputaccount,
                    "advanceaccount": advanceaccount,
                    "email": email,
                    "qatarid": qatarid,
                    "whatsapp": whatsapp,
                    "flag": flag,
                    "closed": closed,
                    "employeecode": employeecode,
                    "reason": reason,
                    "otherreason": otherreason,
                    "closedreason": closedreason,
                    "countersale": countersale,
                }
                if "CCODE" in col_list:
                    from addons.ho.controllers.routes import _cc_next_code
                    from nexa_http import session as erp_session

                    tid_s = erp_session.get("tenant_id")
                    _, cc_ins = _cc_next_code(str(tid_s).strip() if tid_s else None)
                    cc_ins = str(cc_ins or "").strip()[:20]
                    if not cc_ins:
                        raise ValueError("C Code (CCODE) could not be generated; customer was not saved.")
                    all_params["ccode"] = cc_ins

                ph_map = {
                    loc_col: ":loc",
                    code_col: ":code",
                    "CCODE": ":ccode",
                    "CUSTOMERNAME": ":customername",
                    "DESIGNATION": ":designation",
                    "SEX": ":cussex",
                    "ADDRESS": ":address",
                    "NATIONALITY": ":nationality",
                    "TELEPHONE": ":telephone",
                    "FAX": ":fax",
                    "MOBILE": ":mobile",
                    "CREDITLIMIT": ":creditlimit",
                    "CREDITTERMS": ":creditterms",
                    "DUEDAYS": ":duedays",
                    "CURRENTCREDITAMOUNT": ":currentcredit",
                    "SALESMANCODE": ":salesmancode",
                    "CUSTOMER_BILLING_TYPE": ":customer_billing_type",
                    "FLAG": ":flag",
                    "CLOSED": ":closed",
                    "CUSTOMERCATEGORY": ":customercategory",
                    "BYSALESMAN": ":bysalesman",
                    "ROUTENO": ":routeno",
                    "STREET": ":street",
                    "ZONE": ":zone",
                    "POBOX": ":pobox",
                    "CRNO": ":crno",
                    "RECEIVABLEACCOUNT": ":receivableaccount",
                    "SALESACCOUNT": ":salesaccount",
                    "VATOUTPUTACCOUNT": ":vatoutputaccount",
                    "ADVANCEACCOUNT": ":advanceaccount",
                    "CREATEDDATE": "SYSDATE",
                    "EMAIL": ":email",
                    "QATARID": ":qatarid",
                    "WHATSAPP": ":whatsapp",
                    "EMPLOYEECODE": ":employeecode",
                    "REASON": ":reason",
                    "OTHERREASON": ":otherreason",
                    "CLOSEDREASON": ":closedreason",
                    "COUNTERSALE": ":countersale",
                }
                placeholders = ", ".join(ph_map.get(col, "NULL") for col in col_list)
                cols_str = ", ".join(col_list)
                insert_params: dict[str, Any] = {}
                for col in col_list:
                    ph = ph_map.get(col, "NULL")
                    if ph.startswith(":"):
                        param_name = ph[1:].strip()
                        if param_name in all_params:
                            insert_params[param_name] = all_params[param_name]
                cur.execute(
                    f"INSERT INTO {tbl} ({cols_str}) VALUES ({placeholders})",
                    insert_params,
                )

                # Mirror due days to CUSTOMERTMP when present (same as ERP).
                try:
                    tmp_tbl = None
                    if _table_exists("CUSTOMERTMP"):
                        tmp_tbl = "CUSTOMERTMP"
                    elif _table_exists("customertmp"):
                        tmp_tbl = "customertmp"
                    if tmp_tbl:
                        tmp_loc_col = _detect_column(tmp_tbl, ["LOCATIONCODE", "locationcode"])
                        tmp_code_col = _detect_column(tmp_tbl, ["CUSTOMERCODE", "customercode"])
                        tmp_due_col = _detect_column(
                            tmp_tbl, ["DUEDAYS", "DUE_DAYS", "duedays", "due_days"]
                        )
                        if tmp_loc_col and tmp_code_col and tmp_due_col:
                            cur.execute(
                                f"UPDATE {tmp_tbl} SET {tmp_due_col} = :dd "
                                f"WHERE {tmp_loc_col} = :loc AND {tmp_code_col} = :code",
                                {"dd": duedays, "loc": location_code, "code": code},
                            )
                except Exception:
                    pass

        nm = customername[:120]
        try:
            append_master_activity(
                username=str(user or username or "mobile"),
                action="CREATE",
                entity="customer",
                summary=f"location={location_code}, customer_code={code}, name={nm}",
                detail={
                    "locationcode": location_code,
                    "customercode": code,
                    "customername": nm,
                    "source": "mobile",
                },
            )
        except Exception:
            pass

        return {
            "customer_code": int(code),
            "customer_name": customername,
            "customer_billing_type": billing_type,
            "mobile": mobile,
            "telephone": telephone,
            "message": f"Customer {customername} saved ({code}).",
        }
