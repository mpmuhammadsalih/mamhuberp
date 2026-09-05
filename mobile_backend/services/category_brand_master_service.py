"""Mobile Category Master (M/D/C) and Brand Master (B/Z/L) — ERP CATEGORY table."""

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


def _code(v: Any) -> int:
    try:
        return int(float(str(v).strip()))
    except (TypeError, ValueError):
        return 0


def _norm_tree_node(node: dict[str, Any]) -> dict[str, Any]:
    children = [_norm_tree_node(dict(c or {})) for c in (node.get("children") or [])]
    return {
        "code": _code(node.get("code")),
        "id": _code(node.get("id")),
        "name": str(node.get("name") or "").strip(),
        "flag": str(node.get("flag") or "").strip().upper()[:1],
        "level_name": str(node.get("level_name") or "").strip(),
        "parent_main_code": _code(node.get("parent_main_code")) or None,
        "parent_category_code": _code(node.get("parent_category_code")) or None,
        "children": children,
    }


def _norm_flat_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "level": int(row.get("level") or 0),
        "flag": str(row.get("flag") or "").strip().upper()[:1],
        "level_name": str(row.get("level_name") or "").strip(),
        "code": _code(row.get("code")),
        "id": _code(row.get("id")),
        "name": str(row.get("name") or "").strip(),
        "parent_main_code": _code(row.get("parent_main_code")) or None,
        "parent_category_code": _code(row.get("parent_category_code")) or None,
    }


def list_category_master(*, search: str = "") -> dict[str, Any]:
    """Tree + flat rows for Category Master (same as ERP)."""
    from db import get_category_master_flat, get_category_master_tree

    q = (search or "").strip().upper()
    with _erp_session_scope():
        loc = _loc()
        tree_raw = get_category_master_tree(location_code=loc) or []
        tree = [_norm_tree_node(dict(n or {})) for n in tree_raw]
        flat = [_norm_flat_row(dict(r or {})) for r in (get_category_master_flat(tree_raw, location_code=loc) or [])]
        if q:
            flat = [
                r
                for r in flat
                if q in str(r.get("name") or "").upper()
                or q in str(r.get("code") or "")
                or q in str(r.get("level_name") or "").upper()
            ]
        return {
            "location_code": loc,
            "tree": tree,
            "rows": flat,
            "count": len(flat),
        }


def create_category(*, flag: str, name: str, main_code: Any = None, d_code: Any = None, username: str = "mobile") -> dict[str, Any]:
    """Create Main (M), Category (D), or Micro (C)."""
    from db import insert_category_dept, insert_category_main, insert_category_micro
    from master_activity_log import append_master_activity

    fl = str(flag or "").strip().upper()[:1]
    nm = str(name or "").strip()
    if not nm:
        raise ValueError("Name is required.")
    if len(nm) > 200:
        nm = nm[:200]
    if fl not in ("M", "D", "C"):
        raise ValueError("flag must be M, D, or C.")

    lock_key = f"{fl}:{nm.upper()}"
    with mobile_operation_lock(
        "category_master_create",
        lock_key,
        lock_seconds=60.0,
        busy_message="Category is already being saved. Please wait.",
    ), _erp_session_scope() as user:
        loc = _loc()
        if fl == "M":
            ok, err, new_code = insert_category_main(nm, loc)
        elif fl == "D":
            mc = _code(main_code)
            if mc <= 0:
                raise ValueError("Main category code is required.")
            ok, err, new_code = insert_category_dept(nm, mc, loc)
        else:
            dc = _code(d_code)
            if dc <= 0:
                raise ValueError("Category (D) code is required.")
            mc_opt = _code(main_code) or None
            ok, err, new_code = insert_category_micro(nm, dc, loc, mc_opt)
        if not ok:
            raise ValueError(err or "Failed to create category.")
        try:
            append_master_activity(
                username=str(username or user or "mobile").strip() or "mobile",
                action="CREATE",
                entity="item_category_master",
                summary=f"location={loc}, flag={fl}, code={new_code}, name={nm[:120]}",
                detail={"locationcode": loc, "flag": fl, "code": new_code, "name": nm},
            )
        except Exception:
            pass
        return {
            "code": int(new_code or 0),
            "name": nm.upper(),
            "flag": fl,
            "location_code": loc,
            "message": "Category created.",
        }


def update_category(*, code: int, flag: str, name: str, username: str = "mobile") -> dict[str, Any]:
    """Rename Category Master row (M/D/C)."""
    from db import update_category_master_name
    from master_activity_log import append_master_activity

    fl = str(flag or "").strip().upper()[:1]
    nm = str(name or "").strip()
    cd = int(code or 0)
    if cd <= 0:
        raise ValueError("Valid code is required.")
    if fl not in ("M", "D", "C"):
        raise ValueError("flag must be M, D, or C.")
    if not nm:
        raise ValueError("Name is required.")
    if len(nm) > 200:
        nm = nm[:200]

    with mobile_operation_lock(
        "category_master_update",
        f"{fl}:{cd}",
        lock_seconds=60.0,
        busy_message="Category is already being saved. Please wait.",
    ), _erp_session_scope() as user:
        loc = _loc()
        ok, err = update_category_master_name(cd, fl, nm, location_code=loc)
        if not ok:
            raise ValueError(err or "Failed to update category.")
        try:
            append_master_activity(
                username=str(username or user or "mobile").strip() or "mobile",
                action="UPDATE",
                entity="item_category_master",
                summary=f"location={loc}, flag={fl}, code={cd}, name={nm[:120]}",
                detail={"locationcode": loc, "flag": fl, "code": cd, "name": nm},
            )
        except Exception:
            pass
        return {
            "code": cd,
            "name": nm.upper(),
            "flag": fl,
            "location_code": loc,
            "message": "Category updated.",
        }


def list_brand_master(*, flag: str = "all", search: str = "") -> dict[str, Any]:
    """Brand (B) / Shelf (Z) / Color (L) lists."""
    from db import get_categories

    fl = str(flag or "all").strip().upper()
    q = (search or "").strip().upper()
    wanted = ("B", "Z", "L") if fl in ("", "ALL", "*") else (fl[:1],)
    if wanted[0] not in ("B", "Z", "L") and fl not in ("", "ALL", "*"):
        raise ValueError("flag must be B, Z, L, or all.")

    def _rows(f: str) -> list[dict[str, Any]]:
        raw = get_categories(f, location_code=loc) or get_categories(f) or []
        out: list[dict[str, Any]] = []
        for r in raw:
            row = {
                "code": _code(r.get("code") or r.get("CODE")),
                "name": str(r.get("name") or r.get("NAME") or "").strip(),
                "flag": f,
                "id": _code(r.get("id") or r.get("ID")),
            }
            if row["code"] <= 0:
                continue
            if q and q not in row["name"].upper() and q not in str(row["code"]):
                continue
            out.append(row)
        out.sort(key=lambda x: x["code"])
        return out

    with _erp_session_scope():
        loc = _loc()
        brands = _rows("B") if "B" in wanted else []
        shelves = _rows("Z") if "Z" in wanted else []
        colors = _rows("L") if "L" in wanted else []
        return {
            "location_code": loc,
            "brands": brands,
            "shelves": shelves,
            "colors": colors,
            "rows": brands + shelves + colors if fl in ("", "ALL", "*") else (brands or shelves or colors),
        }


def create_brand(*, flag: str, name: str, username: str = "mobile") -> dict[str, Any]:
    """Create Brand (B), Shelf (Z), or Color (L)."""
    from db import insert_category_lookup
    from master_activity_log import append_master_activity

    fl = str(flag or "B").strip().upper()[:1]
    nm = str(name or "").strip()
    if fl not in ("B", "Z", "L"):
        raise ValueError("flag must be B, Z, or L.")
    if not nm:
        raise ValueError("Name is required.")
    if len(nm) > 200:
        nm = nm[:200]

    with mobile_operation_lock(
        "brand_master_create",
        f"{fl}:{nm.upper()}",
        lock_seconds=60.0,
        busy_message="Brand master is already being saved. Please wait.",
    ), _erp_session_scope() as user:
        loc = _loc()
        ok, err, new_code = insert_category_lookup(nm, loc, fl)
        if not ok:
            raise ValueError(err or "Failed to create.")
        lbl = {"B": "brand", "Z": "shelf", "L": "color"}.get(fl, fl)
        try:
            append_master_activity(
                username=str(username or user or "mobile").strip() or "mobile",
                action="CREATE",
                entity="item_brand_master",
                summary=f"location={loc}, type={lbl}, code={new_code}, name={nm[:120]}",
                detail={"locationcode": loc, "flag": fl, "code": new_code, "name": nm},
            )
        except Exception:
            pass
        return {
            "code": int(new_code or 0),
            "name": nm.upper(),
            "flag": fl,
            "location_code": loc,
            "message": f"{lbl.title()} created.",
        }


def update_brand(*, code: int, flag: str, name: str, username: str = "mobile") -> dict[str, Any]:
    """Rename Brand / Shelf / Color row."""
    from db import update_category_master_name
    from master_activity_log import append_master_activity

    fl = str(flag or "B").strip().upper()[:1]
    nm = str(name or "").strip()
    cd = int(code or 0)
    if cd <= 0:
        raise ValueError("Valid code is required.")
    if fl not in ("B", "Z", "L"):
        raise ValueError("flag must be B, Z, or L.")
    if not nm:
        raise ValueError("Name is required.")
    if len(nm) > 200:
        nm = nm[:200]

    with mobile_operation_lock(
        "brand_master_update",
        f"{fl}:{cd}",
        lock_seconds=60.0,
        busy_message="Brand master is already being saved. Please wait.",
    ), _erp_session_scope() as user:
        loc = _loc()
        ok, err = update_category_master_name(cd, fl, nm, location_code=loc)
        if not ok:
            raise ValueError(err or "Failed to update.")
        lbl = {"B": "brand", "Z": "shelf", "L": "color"}.get(fl, fl)
        try:
            append_master_activity(
                username=str(username or user or "mobile").strip() or "mobile",
                action="UPDATE",
                entity="item_brand_master",
                summary=f"location={loc}, type={lbl}, code={cd}, name={nm[:120]}",
                detail={"locationcode": loc, "flag": fl, "code": cd, "name": nm},
            )
        except Exception:
            pass
        return {
            "code": cd,
            "name": nm.upper(),
            "flag": fl,
            "location_code": loc,
            "message": f"{lbl.title()} updated.",
        }
