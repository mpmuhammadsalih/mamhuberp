"""Mobile Item Master — create / list aligned with ERP ``itemmaster_save``."""

from __future__ import annotations

import base64
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from mobile_backend.operation_lock import mobile_operation_lock
from mobile_backend.services.stock_transfer_service import _erp_session_scope

_ALLOWED_ITEM_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
_MIME_TO_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
_MAX_ITEM_IMAGE_BYTES = 8 * 1024 * 1024


def _nova_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _item_image_static_dir() -> Path:
    return _nova_root() / "static" / "uploads" / "itemmaster"


def _normalize_image_rel(path: str) -> str:
    rel = str(path or "").strip().replace("\\", "/")
    if not rel:
        return ""
    if rel.startswith("/static/"):
        rel = rel[len("/static/") :]
    if rel.startswith("static/"):
        rel = rel[len("static/") :]
    return rel


def _item_image_abs_path(rel_path: str) -> Path | None:
    rel = _normalize_image_rel(rel_path)
    parts = rel.split("/")
    if len(parts) != 3 or parts[0] != "uploads" or parts[1] != "itemmaster":
        return None
    name = parts[2]
    if not name or name in (".", "..") or ".." in name:
        return None
    full = (_item_image_static_dir() / name).resolve()
    try:
        full.relative_to(_item_image_static_dir().resolve())
    except ValueError:
        return None
    return full


def _delete_item_image_file(rel_path: str) -> None:
    full = _item_image_abs_path(rel_path)
    if full is None or not full.is_file():
        return
    try:
        full.unlink()
    except Exception:
        pass


def _decode_image_payload(data: dict[str, Any]) -> tuple[bytes, str] | None:
    raw_b64 = str(data.get("image_base64") or data.get("item_image_base64") or "").strip()
    if not raw_b64:
        return None
    mime = str(data.get("image_mime") or data.get("mime") or "image/jpeg").strip().lower()
    if raw_b64.startswith("data:") and "," in raw_b64:
        header, raw_b64 = raw_b64.split(",", 1)
        m = re.match(r"data:([^;]+)", header.strip())
        if m:
            mime = m.group(1).strip().lower() or mime
    try:
        blob = base64.b64decode(raw_b64, validate=False)
    except Exception as exc:
        raise ValueError("Invalid image_base64.") from exc
    if not blob:
        raise ValueError("Empty image payload.")
    if len(blob) > _MAX_ITEM_IMAGE_BYTES:
        raise ValueError("Item image is too large (max 8 MB).")
    ext = _MIME_TO_EXT.get(mime)
    if not ext:
        raise ValueError("Item image must be PNG, JPG, WEBP, or GIF.")
    return blob, ext


def _save_item_image_bytes(
    blob: bytes, *, location_code: int, item_code: int, ext: str
) -> str:
    ext = (ext or ".jpg").lower()
    if ext not in _ALLOWED_ITEM_IMAGE_EXT:
        raise ValueError("Item image must be PNG, JPG, WEBP, or GIF.")
    ic = int(item_code)
    if ic <= 0:
        raise ValueError("Item code is required before uploading an image.")
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    filename = f"item_{int(location_code)}_{ic}_{stamp}{ext}"
    target_dir = _item_image_static_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    full_path = target_dir / filename
    full_path.write_bytes(blob)
    return f"uploads/itemmaster/{filename}"


def apply_item_image_from_payload(
    *,
    item_code: int,
    location_code: int,
    payload: dict[str, Any],
    existing_path: str = "",
) -> str:
    """Upload/remove item image from mobile JSON payload. Returns new relative path."""
    from db import ensure_itemmaster_image_path_column, set_item_image_path

    data = dict(payload or {})
    remove = str(data.get("remove_image") or data.get("remove_item_image") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "y",
        "on",
    )
    decoded = None if remove else _decode_image_payload(data)
    if not remove and decoded is None:
        return _normalize_image_rel(existing_path)

    ensure_itemmaster_image_path_column()
    existing = _normalize_image_rel(existing_path)
    new_path = ""
    if remove:
        new_path = ""
    else:
        assert decoded is not None
        blob, ext = decoded
        new_path = _save_item_image_bytes(
            blob, location_code=int(location_code), item_code=int(item_code), ext=ext
        )

    ok, err = set_item_image_path(
        int(item_code),
        int(location_code),
        new_path or None,
    )
    if not ok:
        if new_path:
            _delete_item_image_file(new_path)
        raise ValueError(err or "Could not save item image.")
    if (remove or decoded is not None) and existing and existing != new_path:
        _delete_item_image_file(existing)
    return new_path


def resolve_item_image_file(item_code: int) -> tuple[Path, str]:
    """Return (absolute file path, media type) for an item image."""
    from db import get_item_by_code

    code = _to_int(item_code, 0) or 0
    if code <= 0:
        raise ValueError("Item code is required.")
    with _erp_session_scope():
        im = _itemmaster_mod()
        loc = im._itemmaster_session_location_code()
        raw = get_item_by_code(int(code), loc)
        if not raw:
            raise ValueError(f"Item {code} not found.")
        rel = _normalize_image_rel(str(raw.get("image_path") or raw.get("imagepath") or ""))
        if not rel:
            raise FileNotFoundError("Item has no image.")
        full = _item_image_abs_path(rel)
        if full is None or not full.is_file():
            raise FileNotFoundError("Item image file is missing.")
        ext = full.suffix.lower()
        mime = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".gif": "image/gif",
        }.get(ext, "application/octet-stream")
        return full, mime


def _itemmaster_mod():
    from addons.itemmaster.controllers import routes as itemmaster

    return itemmaster


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


def _lookup_rows(
    rows: list[Any] | None,
    *,
    code_keys: tuple[str, ...] = ("code",),
    name_keys: tuple[str, ...] = ("name",),
    parent_keys: tuple[str, ...] = ("id", "ID", "parent_id", "parentid"),
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in rows or []:
        r = dict(raw or {})
        code = ""
        for k in code_keys:
            if r.get(k) not in (None, ""):
                code = str(r.get(k)).strip()
                break
        name = ""
        for k in name_keys:
            if r.get(k) not in (None, ""):
                name = str(r.get(k)).strip()
                break
        if not code and not name:
            continue
        parent_id = ""
        for k in parent_keys:
            if r.get(k) not in (None, ""):
                parent_id = str(r.get(k)).strip()
                break
        row: dict[str, Any] = {"code": code, "name": name}
        if parent_id:
            row["parent_id"] = parent_id
        out.append(row)
    return out


def _flag_categories(flag: str, loc: int) -> list[dict[str, Any]]:
    """
    CATEGORY lookups for Item Master open form.

    ERP Item Master popup loads M/B/Z/L with ``get_categories(flag)`` (no location
    filter). Filtering by LOCATIONCODE often returns only one main category when
    the rest of the master is shared / under another location — so M/B match ERP
    and stay unscoped. D/C prefer the session location, then merge any missing
    codes from the unscoped list so cascading still sees the full tree.
    """
    from db import get_categories

    fl = (flag or "").strip().upper()[:1] or "C"

    def _fetch(*, with_loc: bool) -> list[Any]:
        try:
            if with_loc:
                return list(get_categories(fl, location_code=int(loc)) or [])
            return list(get_categories(fl) or [])
        except Exception:
            return []

    def _code_key(row: Any) -> str:
        r = dict(row or {})
        for k in ("code", "CODE"):
            if r.get(k) not in (None, ""):
                try:
                    return str(int(float(str(r.get(k)).strip())))
                except (TypeError, ValueError):
                    return str(r.get(k)).strip()
        return ""

    def _merge(primary: list[Any], secondary: list[Any]) -> list[Any]:
        out: list[Any] = []
        seen: set[str] = set()
        for src in (primary, secondary):
            for row in src:
                ck = _code_key(row)
                if not ck or ck in seen:
                    continue
                seen.add(ck)
                out.append(row)
        return out

    # Same as ERP ``_itemmaster_lookup_rows`` for main/brand/size/color
    if fl in ("M", "B", "Z", "L"):
        rows = _fetch(with_loc=False)
        if not rows:
            rows = _fetch(with_loc=True)
    else:
        loc_rows = _fetch(with_loc=True)
        all_rows = _fetch(with_loc=False)
        # Location-first, but never hide masters that exist only outside this loc
        rows = _merge(loc_rows, all_rows) if (loc_rows or all_rows) else []

    return _lookup_rows(
        rows,
        code_keys=("code", "CODE"),
        name_keys=("name", "NAME"),
        # ID is parent code for D/C (main CODE / dept CODE); omit for M/B
        parent_keys=("id", "ID", "parent_id", "parentid") if fl in ("D", "C") else (),
    )


def get_open_context() -> dict[str, Any]:
    """Defaults for create form: next code, barcode, UOMs, categories, GL."""
    from db import (
        format_location_prefix_item_barcode,
        get_next_item_code,
        get_suppliers,
        get_units_for_itemmaster_dropdown,
    )

    with _erp_session_scope():
        im = _itemmaster_mod()
        loc = im._itemmaster_session_location_code()
        next_code = int(get_next_item_code(loc) or 0)
        suggested_barcode = ""
        if next_code > 0:
            # Same ERP rule: 12 + zero pad + item code (13 digits), e.g. 1200000001000
            suggested_barcode = str(
                format_location_prefix_item_barcode(loc, next_code) or ""
            ).strip()

        try:
            acct_defs = im._grn_new_item_default_account_fields(None)
        except Exception:
            acct_defs = {
                "sales_code": "4100",
                "purchase_code": "5001",
                "inventory_code": "1300",
                "cogs_code": "5100",
            }

        uoms = _lookup_rows(
            get_units_for_itemmaster_dropdown(loc),
            code_keys=("code", "unitcode"),
            name_keys=("name", "unitname"),
        )
        categories = _flag_categories("C", loc)
        brand_rows = _flag_categories("B", loc)
        main_categories = _flag_categories("M", loc)
        departments = _flag_categories("D", loc)
        try:
            suppliers = _lookup_rows(
                get_suppliers(),
                code_keys=("code", "CODE", "suppliercode", "SUPPLIERCODE"),
                name_keys=("name", "NAME", "suppliername", "SUPPLIERNAME"),
            )
        except Exception:
            suppliers = []

        return {
            "location_code": loc,
            "next_item_code": next_code,
            "suggested_barcode": suggested_barcode,
            "uoms": uoms,
            "categories": categories,
            "brands": brand_rows,
            "main_categories": main_categories,
            "departments": departments,
            "suppliers": suppliers,
            "default_accounts": {
                "sales_account": str(acct_defs.get("sales_code") or "4100"),
                "purchase_account": str(acct_defs.get("purchase_code") or "5001"),
                "inventory_account": str(acct_defs.get("inventory_code") or "1300"),
                "cogs_account": str(acct_defs.get("cogs_code") or "5100"),
            },
        }


def list_items(
    *,
    search: str = "",
    limit: int = 100,
    category_code: int | None = None,
    brand_code: int | None = None,
    supplier_code: int | None = None,
    stock_filter: str = "",
) -> dict[str, Any]:
    from db import get_items_list

    lim = max(1, min(int(limit or 100), 300))
    q = (search or "").strip()
    stock = (stock_filter or "").strip().lower()
    if stock not in ("", "notzero", "greater", "less", "instock", "low", "out", "zero"):
        stock = ""
    cat = _to_int(category_code, None)
    brand = _to_int(brand_code, None)
    sup = _to_int(supplier_code, None)
    with _erp_session_scope():
        im = _itemmaster_mod()
        loc = im._itemmaster_session_location_code()
        rows, total = get_items_list(
            location_code=loc,
            search=q or None,
            limit=lim,
            page=1,
            items_per_page=lim,
            stock_filter=stock or None,
            brand_code=brand if brand and brand > 0 else None,
            category_code=cat if cat and cat > 0 else None,
            supplier_code=str(sup) if sup and sup > 0 else None,
            include_lookup_names=True,
        )
        out: list[dict[str, Any]] = []
        for raw in rows or []:
            r = dict(raw or {})
            code = r.get("itemcode") or r.get("item_code") or r.get("code")
            try:
                code_i = int(float(str(code))) if code not in (None, "") else 0
            except (TypeError, ValueError):
                code_i = 0
            out.append(
                {
                    "item_code": code_i,
                    "item_name": str(r.get("itemname") or r.get("item_name") or r.get("name") or "").strip(),
                    "barcode": str(
                        r.get("manufacturerid") or r.get("manufacturer_id") or r.get("barcode") or ""
                    ).strip(),
                    "base_uom": str(r.get("baseuom") or r.get("base_uom") or "").strip(),
                    "cost_price": _to_float(r.get("costprice") or r.get("cost_price")),
                    "average_cost": (
                        _to_float(
                            r.get("averagecost") or r.get("average_cost") or r.get("AVERAGECOST")
                        )
                        or _to_float(r.get("costprice") or r.get("cost_price"))
                    ),
                    "retail_price": _to_float(r.get("retailprice") or r.get("retail_price")),
                    "current_stock": _to_float(r.get("currentstock") or r.get("current_stock")),
                    "category_code": _to_int(r.get("categorycode") or r.get("category_code"), 0) or 0,
                    "category_name": str(r.get("categoryname") or r.get("category_name") or "").strip(),
                    "brand_name": str(r.get("brandname") or r.get("brand_name") or "").strip(),
                    "supplier_name": str(r.get("suppliername") or r.get("supplier_name") or "").strip(),
                }
            )
        return {
            "items": out,
            "count": len(out),
            "total": int(total or len(out)),
            "filters": {
                "q": q,
                "category_code": cat if cat and cat > 0 else 0,
                "brand_code": brand if brand and brand > 0 else 0,
                "supplier_code": sup if sup and sup > 0 else 0,
                "stock_filter": stock,
            },
        }


def _alt_row_is_base(alt: dict[str, Any], base_uom: str) -> bool:
    if str(alt.get("is_base") or alt.get("IS_BASE") or "").strip().upper() in ("Y", "1", "TRUE"):
        return True
    uom = str(alt.get("alternateuomcode") or alt.get("alternate_uom_code") or "").strip()
    factor = _to_float(alt.get("conversionfactor") or alt.get("conversion_factor"), 0)
    return bool(uom) and uom.upper() == (base_uom or "").strip().upper() and abs(factor - 1.0) < 0.0001


def get_item_ledger(
    *,
    item_code: int | None = None,
    barcode: str = "",
    tab: str = "purchase",
    limit: int = 400,
) -> dict[str, Any]:
    """ERP Item Master ledger tabs (GRN / PR / sale / sale return / stock adj)."""
    from db import get_item_by_code, get_item_by_manufacturer_id, get_item_ledger_tab

    tab_n = str(tab or "purchase").strip().lower().replace("-", "_") or "purchase"
    lim = max(1, min(int(limit or 400), 2000))
    bc = str(barcode or "").strip()

    with _erp_session_scope():
        im = _itemmaster_mod()
        loc = im._itemmaster_session_location_code()
        code = _to_int(item_code, 0) or 0
        item_name = ""
        resolved_barcode = bc

        if code <= 0 and bc:
            item = None
            try:
                item = get_item_by_manufacturer_id(bc, loc)
            except Exception:
                item = None
            if not item:
                try:
                    from db import get_item_by_alternate_barcode

                    item = get_item_by_alternate_barcode(bc, loc)
                except Exception:
                    item = None
            if not item:
                raise ValueError(f"No item found for barcode {bc}")
            code = _to_int(item.get("itemcode") or item.get("ITEMCODE"), 0) or 0
            item_name = str(item.get("itemname") or item.get("ITEMNAME") or "").strip()
            if code <= 0:
                raise ValueError(f"Item for barcode {bc} has no valid item code")

        if code <= 0:
            raise ValueError("item_code or barcode is required.")

        if not item_name:
            try:
                hdr = get_item_by_code(int(code), loc)
                if hdr:
                    item_name = str(hdr.get("itemname") or hdr.get("ITEMNAME") or "").strip()
                    if not resolved_barcode:
                        resolved_barcode = str(
                            hdr.get("manufacturerid") or hdr.get("manufacturer_id") or ""
                        ).strip()
            except Exception:
                pass

        rows = get_item_ledger_tab(loc, int(code), tab_n, limit=lim) or []
        out_rows: list[dict[str, Any]] = []
        for raw in rows:
            r = dict(raw or {})
            out_rows.append(
                {
                    "doc_no": str(r.get("doc_no") or r.get("docno") or "").strip(),
                    "doc_date": str(r.get("doc_date") or r.get("docdate") or "").strip(),
                    "party_code": str(r.get("party_code") or r.get("partycode") or "").strip(),
                    "party_name": str(r.get("party_name") or r.get("partyname") or "").strip(),
                    "qty": _to_float(r.get("qty") or r.get("quantity")),
                    "uom": str(r.get("uom") or "").strip(),
                    "rate": _to_float(r.get("rate")),
                    "bonus": _to_float(r.get("bonus")),
                    "foc": r.get("foc"),
                    "discount": _to_float(r.get("discount")),
                    "amount": _to_float(r.get("amount")),
                }
            )
        return {
            "tab": tab_n,
            "item_code": int(code),
            "item_name": item_name,
            "barcode": resolved_barcode,
            "rows": out_rows,
            "count": len(out_rows),
        }


def get_item_journal(
    *,
    item_code: int | None = None,
    barcode: str = "",
    date_from: str = "",
    date_to: str = "",
    limit: int = 500,
) -> dict[str, Any]:
    """ITEMJOURNAL stock movements for one item (same source as ERP stock ledger detail)."""
    from datetime import date, timedelta

    from db import get_item_by_alternate_barcode, get_item_by_code, get_item_by_manufacturer_id
    from mobile_backend.services.inventory_reports_service import stock_ledger

    with _erp_session_scope():
        im = _itemmaster_mod()
        loc = im._itemmaster_session_location_code()
        code = _to_int(item_code, 0) or 0
        item_name = ""
        resolved_barcode = str(barcode or "").strip()
        if code <= 0 and resolved_barcode:
            item = None
            try:
                item = get_item_by_manufacturer_id(resolved_barcode, loc)
            except Exception:
                item = None
            if not item:
                try:
                    item = get_item_by_alternate_barcode(resolved_barcode, loc)
                except Exception:
                    item = None
            if not item:
                raise ValueError(f"No item found for barcode {resolved_barcode}")
            code = _to_int(item.get("itemcode") or item.get("ITEMCODE"), 0) or 0
            item_name = str(item.get("itemname") or item.get("ITEMNAME") or "").strip()
        if code <= 0:
            raise ValueError("item_code or barcode is required.")
        if not item_name:
            try:
                hdr = get_item_by_code(int(code), loc) or {}
                item_name = str(hdr.get("itemname") or hdr.get("ITEMNAME") or "").strip()
                if not resolved_barcode:
                    resolved_barcode = str(
                        hdr.get("manufacturerid") or hdr.get("manufacturer_id") or ""
                    ).strip()
            except Exception:
                pass

    df = (date_from or "").strip()
    dt = (date_to or "").strip()
    if not df or not dt:
        today = date.today()
        dt = dt or today.isoformat()
        df = df or (today - timedelta(days=729)).isoformat()

    payload = stock_ledger(
        date_from=df,
        date_to=dt,
        search="",
        item_code=str(code),
        report_mode="detail",
        limit=limit,
    )

    rows_out: list[dict[str, Any]] = []
    for raw in payload.get("rows") or []:
        r = dict(raw or {})
        rows_out.append(
            {
                "stock_date": str(r.get("stock_date") or r.get("date") or "").strip(),
                "stock_time": str(r.get("stock_time") or r.get("time") or "").strip(),
                "transtype": str(r.get("transtype") or r.get("trans_type") or r.get("type") or "").strip(),
                "source_doc": str(r.get("source_doc") or r.get("sourcedoc") or "").strip(),
                "source_no": str(r.get("source_no") or r.get("sourceno") or "").strip(),
                "qty_in": _to_float(r.get("qty_in")),
                "qty_out": _to_float(r.get("qty_out")),
                "net_qty": _to_float(r.get("net_qty") or r.get("qty") or r.get("quantity")),
                "uom": str(r.get("uom") or "").strip(),
                "rate": _to_float(r.get("rate") or r.get("costprice")),
                "amount": _to_float(r.get("amount") or r.get("line_value")),
                "warehouse_code": str(
                    r.get("warehouse_code") or r.get("warehouse") or r.get("warehouse_name") or ""
                ).strip(),
            }
        )
    return {
        "item_code": code,
        "item_name": item_name,
        "barcode": resolved_barcode,
        "date_from": payload.get("date_from") or df,
        "date_to": payload.get("date_to") or dt,
        "rows": rows_out,
        "count": len(rows_out),
    }


def get_item_detail(item_code: int) -> dict[str, Any]:
    """Full item header + non-base alternate UOM rows for mobile detail/edit."""
    from db import (
        get_category_lookup_label,
        get_item_alternate_uoms,
        get_item_by_code,
        get_supplier_by_code,
    )

    code = _to_int(item_code, 0) or 0
    if code <= 0:
        raise ValueError("Item code is required.")

    with _erp_session_scope():
        im = _itemmaster_mod()
        loc = im._itemmaster_session_location_code()
        raw = get_item_by_code(int(code), loc)
        if not raw:
            raise ValueError(f"Item {code} not found.")
        r = dict(raw)
        base_uom = str(r.get("baseuom") or r.get("base_uom") or "").strip()
        item_name = str(r.get("itemname") or r.get("item_name") or "").strip()
        barcode = str(r.get("manufacturerid") or r.get("manufacturer_id") or "").strip()
        category_code = _to_int(r.get("categorycode") or r.get("category_code"), 0) or 0
        brand_code = _to_int(r.get("brandcode") or r.get("brand_code"), 0) or 0
        main_category = _to_int(r.get("maincategory") or r.get("main_category"), 0) or 0
        department_code = _to_int(r.get("departmentcode") or r.get("department_code"), 0) or 0
        sup_code = _to_int(r.get("supcode") or r.get("sup_code"), 0) or 0
        cost_price = _to_float(r.get("costprice") or r.get("cost_price"))
        average_cost = _to_float(
            r.get("averagecost") or r.get("average_cost") or r.get("AVERAGECOST")
        )
        if average_cost <= 0:
            average_cost = cost_price

        supplier_name = str(r.get("suppliername") or r.get("supplier_name") or "").strip()
        if not supplier_name and sup_code > 0:
            try:
                sup = get_supplier_by_code(loc, int(sup_code)) or {}
                supplier_name = str(
                    sup.get("suppliername") or sup.get("SUPPLIERNAME") or ""
                ).strip()
            except Exception:
                supplier_name = ""

        def _lbl(flag: str, c: int) -> str:
            if c <= 0:
                return ""
            try:
                return str(get_category_lookup_label(flag, c, loc) or "").strip()
            except Exception:
                return str(c)

        alts_raw = get_item_alternate_uoms(loc, int(code)) or []
        alts: list[dict[str, Any]] = []
        for araw in alts_raw:
            a = dict(araw or {})
            if _alt_row_is_base(a, base_uom):
                continue
            factor = _to_float(a.get("conversionfactor") or a.get("conversion_factor"))
            alt_cost = _to_float(a.get("costprice") or a.get("cost_price"))
            if alt_cost <= 0 and factor > 0:
                alt_cost = round(factor * cost_price, 3)
            alts.append(
                {
                    "slno": str(a.get("slno") or "").strip(),
                    "alternate_uom_code": str(
                        a.get("alternateuomcode") or a.get("alternate_uom_code") or ""
                    ).strip(),
                    "manufacturer_id": str(
                        a.get("manufacturerid") or a.get("manufacturer_id") or ""
                    ).strip(),
                    "conversion_factor": factor,
                    "cost_price": alt_cost,
                    "retail_price": _to_float(a.get("retailprice") or a.get("retail_price")),
                    "wholesale_price": _to_float(
                        a.get("wholesaleprice") or a.get("wholesale_price")
                    ),
                }
            )

        return {
            "item_code": int(code),
            "item_name": item_name,
            "manufacturer_id": barcode,
            "barcode": barcode,
            "base_uom": base_uom,
            "category_code": category_code,
            "category_name": str(r.get("categoryname") or "").strip() or _lbl("C", category_code),
            "brand_code": brand_code,
            "brand_name": _lbl("B", brand_code),
            "main_category": main_category,
            "main_category_name": _lbl("M", main_category),
            "department_code": department_code,
            "department_name": _lbl("D", department_code),
            "sup_code": sup_code,
            "supplier_name": supplier_name,
            "cost_price": cost_price,
            "average_cost": average_cost,
            "retail_price": _to_float(r.get("retailprice") or r.get("retail_price")),
            "wholesale_price": _to_float(r.get("wholesaleprice") or r.get("wholesale_price")),
            "vat_percent": _to_float(r.get("vatpercent") or r.get("vat_percent")),
            "current_stock": _to_float(r.get("currentstock") or r.get("current_stock")),
            "description": str(r.get("description") or "").strip(),
            "sales_account": str(r.get("sales_account") or r.get("salesaccount") or "").strip(),
            "purchase_account": str(
                r.get("purchase_account") or r.get("purchaseaccount") or ""
            ).strip(),
            "inventory_account": str(
                r.get("inventory_account") or r.get("inventoryaccount") or ""
            ).strip(),
            "cogs_account": str(r.get("cogs_account") or r.get("cogsaccount") or "").strip(),
            "alternate_uoms": alts,
            "image_path": _normalize_image_rel(
                str(r.get("image_path") or r.get("imagepath") or "")
            ),
            "has_image": bool(
                _normalize_image_rel(str(r.get("image_path") or r.get("imagepath") or ""))
            ),
            "image_url": f"/api/v1/item/masters/{int(code)}/image",
        }


def _build_alternate_uom_payloads(
    *,
    loc: int,
    item_code: int,
    base_uom: str,
    master_cost: float,
    description: str,
    rows: list[Any] | None,
    exclude_item_code: int | None = None,
) -> list[dict[str, Any]]:
    """Normalize mobile ``alternate_uoms`` into ERP save payloads."""
    from db import barcode_taken_in_location, get_next_alternate_barcode

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    base_key = (base_uom or "").strip().upper()
    for idx, raw in enumerate(rows or [], start=1):
        if not isinstance(raw, dict):
            continue
        vr = dict(raw)
        alt_uom = str(vr.get("alternate_uom_code") or vr.get("uom") or "").strip()
        if not alt_uom:
            continue
        alt_key = alt_uom.upper()
        if alt_key == base_key:
            raise ValueError(f"Alternate UOM cannot match base UOM ({base_uom}).")
        if alt_key in seen:
            raise ValueError(f"Duplicate alternate UOM: {alt_uom}.")
        seen.add(alt_key)

        factor = _to_float(vr.get("conversion_factor") or vr.get("factor"), 0)
        if factor <= 0:
            raise ValueError(f"Conversion factor must be greater than 0 for UOM {alt_uom}.")

        barcode = str(vr.get("manufacturer_id") or vr.get("barcode") or "").strip()
        if not barcode:
            try:
                barcode = str(get_next_alternate_barcode(loc, int(item_code)) or "").strip()
            except Exception:
                barcode = ""
        if not barcode:
            barcode = f"{item_code}-{alt_uom}-{idx}"

        if barcode_taken_in_location(barcode, loc, exclude_item_code=exclude_item_code):
            raise ValueError(
                f"Alternate barcode already exists ({barcode}). Use another barcode."
            )

        alt_cost = round(factor * float(master_cost or 0), 3)
        retail = _to_float(vr.get("retail_price") or vr.get("retailprice"), 0)
        out.append(
            {
                "location_code": loc,
                "item_code": int(item_code),
                "slno": str(vr.get("slno") or idx).strip(),
                "alternate_uom_code": alt_uom,
                "manufacturer_id": barcode,
                "base_uom": base_uom,
                "conversion_factor": factor,
                "cost_price": alt_cost,
                "wholesale_price": _to_float(vr.get("wholesale_price"), 0),
                "retail_price": retail,
                "third_price": _to_float(vr.get("third_price"), 0),
                "branch_price": _to_float(vr.get("branch_price"), retail),
                "description": str(vr.get("description") or description or "")[:500],
                "is_base": False,
            }
        )
    return out


def _persist_item(
    payload: dict[str, Any],
    *,
    is_new: bool,
    username: str = "mobile",
    fixed_item_code: int | None = None,
) -> dict[str, Any]:
    """Create or update an item via ERP ``save_itemmaster_with_alternate_uoms``."""
    from master_activity_log import append_master_activity
    from db import (
        _clip_itemmaster_item_name,
        barcode_taken_in_location,
        format_location_prefix_item_barcode,
        get_item_by_code,
        get_next_item_code,
        save_itemmaster_with_alternate_uoms,
    )

    data = dict(payload or {})
    name_raw = str(data.get("item_name") or data.get("itemname") or "").strip()
    name_key = name_raw.upper()
    lock_key = (
        str(fixed_item_code)
        if fixed_item_code and fixed_item_code > 0
        else (name_key or "new")
    )

    with mobile_operation_lock(
        "item_save",
        lock_key,
        lock_seconds=90.0,
        busy_message="Item is already being saved. Please wait.",
    ), _erp_session_scope() as user:
        im = _itemmaster_mod()
        loc = im._itemmaster_session_location_code()

        item_name = _clip_itemmaster_item_name(name_key)
        if not item_name:
            raise ValueError("Item name is required.")

        base_uom = str(data.get("base_uom") or data.get("baseuom") or "").strip()
        if not base_uom:
            raise ValueError("Base UOM is required.")

        category_code = _to_int(data.get("category_code") or data.get("categorycode"), 0) or 0
        if category_code <= 0:
            raise ValueError("Category is required.")

        if is_new:
            item_code = _to_int(data.get("item_code") or data.get("itemcode"), None)
            if item_code is None or item_code <= 0:
                item_code = int(get_next_item_code(loc))
            else:
                try:
                    if get_item_by_code(int(item_code), loc):
                        item_code = int(get_next_item_code(loc))
                except Exception:
                    item_code = int(get_next_item_code(loc))
            exclude_code = None
        else:
            item_code = _to_int(fixed_item_code or data.get("item_code") or data.get("itemcode"), 0) or 0
            if item_code <= 0:
                raise ValueError("Item code is required for update.")
            existing = get_item_by_code(int(item_code), loc)
            if not existing:
                raise ValueError(f"Item {item_code} not found.")
            exclude_code = int(item_code)

        barcode = str(
            data.get("manufacturer_id") or data.get("barcode") or data.get("manufacturerid") or ""
        ).strip()
        if not barcode:
            barcode = str(format_location_prefix_item_barcode(loc, int(item_code)) or item_code).strip()
        if barcode_taken_in_location(barcode, loc, exclude_item_code=exclude_code):
            raise ValueError(
                "Barcode already exists in Itemmaster or alternate UOM. Please use another barcode."
            )

        try:
            acct_defs = im._grn_new_item_default_account_fields(None)
        except Exception:
            acct_defs = {}

        existing_sales = ""
        existing_purchase = ""
        existing_inventory = ""
        existing_cogs = ""
        if not is_new:
            ex = dict(existing or {})
            existing_sales = str(ex.get("sales_account") or ex.get("salesaccount") or "").strip()
            existing_purchase = str(
                ex.get("purchase_account") or ex.get("purchaseaccount") or ""
            ).strip()
            existing_inventory = str(
                ex.get("inventory_account") or ex.get("inventoryaccount") or ""
            ).strip()
            existing_cogs = str(ex.get("cogs_account") or ex.get("cogsaccount") or "").strip()

        sales_account = str(
            data.get("sales_account")
            or existing_sales
            or acct_defs.get("sales_code")
            or "4100"
        ).strip() or "4100"
        purchase_account = str(
            data.get("purchase_account")
            or existing_purchase
            or acct_defs.get("purchase_code")
            or "5001"
        ).strip() or "5001"
        inventory_account = str(
            data.get("inventory_account")
            or existing_inventory
            or acct_defs.get("inventory_code")
            or "1300"
        ).strip() or "1300"
        cogs_account = str(
            data.get("cogs_account")
            or existing_cogs
            or acct_defs.get("cogs_code")
            or "5100"
        ).strip() or "5100"

        brand_code = _to_int(data.get("brand_code") or data.get("brandcode"), 0) or 0
        sup_code = _to_int(data.get("sup_code") or data.get("supplier_code"), 0) or 0
        cost_price = _to_float(data.get("cost_price") or data.get("costprice"), 0)
        retail_price = _to_float(data.get("retail_price") or data.get("retailprice"), 0)
        vat_percent = _to_float(data.get("vat_percent") or data.get("vatpercent"), 0)
        description = str(data.get("description") or item_name).strip()

        item_data: dict[str, Any] = {
            "location_code": loc,
            "item_code": str(item_code),
            "manufacturer_id": barcode,
            "item_name": item_name,
            "category_code": category_code,
            "brand_code": brand_code,
            "base_uom": base_uom,
            "sup_code": sup_code,
            "cost_price": cost_price,
            "retail_price": retail_price,
            "wholesale_price": _to_float(data.get("wholesale_price"), 0),
            "third_price": _to_float(data.get("third_price"), 0),
            "branch_price": _to_float(data.get("branch_price"), retail_price),
            "vat_percent": vat_percent,
            "description": description,
            "item_name_ara": str(data.get("item_name_ara") or "").strip(),
            "discount_flag": "N",
            "item_flag": "Y",
            "main_category": _to_int(
                data.get("main_category") or data.get("maincategory"), 0
            )
            or 0,
            "department_code": _to_int(
                data.get("department_code") or data.get("departmentcode"), 0
            )
            or 0,
            "sales_account": sales_account,
            "purchase_account": purchase_account,
            "inventory_account": inventory_account,
            "cogs_account": cogs_account,
        }

        alt_rows = data.get("alternate_uoms") or data.get("alternate_uom_payloads") or []
        if not isinstance(alt_rows, list):
            raise ValueError("alternate_uoms must be a list.")
        alternate_payloads = _build_alternate_uom_payloads(
            loc=loc,
            item_code=int(item_code),
            base_uom=base_uom,
            master_cost=cost_price,
            description=description,
            rows=alt_rows,
            exclude_item_code=exclude_code,
        )

        saved_code, err = save_itemmaster_with_alternate_uoms(
            item_data, is_new, alternate_payloads
        )
        if err:
            raise ValueError(str(err))
        if saved_code in (None, ""):
            raise ValueError("Item save failed.")

        try:
            code_i = int(float(str(saved_code).strip()))
        except (TypeError, ValueError):
            code_i = int(item_code)

        existing_image = ""
        if not is_new:
            try:
                existing_image = _normalize_image_rel(
                    str(
                        (existing or {}).get("image_path")
                        or (existing or {}).get("imagepath")
                        or ""
                    )
                )
            except Exception:
                existing_image = ""

        image_path = existing_image
        try:
            image_path = apply_item_image_from_payload(
                item_code=code_i,
                location_code=loc,
                payload=data,
                existing_path=existing_image,
            )
        except ValueError:
            raise
        except Exception as img_exc:
            raise ValueError(str(img_exc) or "Could not save item image.") from img_exc

        action = "CREATE" if is_new else "UPDATE"
        try:
            append_master_activity(
                username=str(user or username or "mobile"),
                action=action,
                entity="itemmaster",
                summary=f"location={loc}, item_code={code_i}, name={item_name[:80]}",
                detail={
                    "locationcode": loc,
                    "itemcode": code_i,
                    "itemname": item_name[:120],
                    "barcode": barcode,
                    "alternate_uom_count": len(alternate_payloads),
                    "has_image": bool(image_path),
                    "source": "mobile",
                },
            )
        except Exception:
            pass

        verb = "saved" if is_new else "updated"
        return {
            "item_code": code_i,
            "item_name": item_name,
            "barcode": barcode,
            "base_uom": base_uom,
            "category_code": category_code,
            "alternate_uom_count": len(alternate_payloads),
            "has_image": bool(image_path),
            "image_url": f"/api/v1/item/masters/{code_i}/image",
            "message": f"Item {item_name} {verb} ({code_i}).",
        }


def create_item(payload: dict[str, Any], *, username: str = "mobile") -> dict[str, Any]:
    """Create an item using ERP itemmaster save rules (optional alternate UOM rows)."""
    return _persist_item(payload, is_new=True, username=username)


def update_item(
    item_code: int, payload: dict[str, Any], *, username: str = "mobile"
) -> dict[str, Any]:
    """Update an existing item master row (+ alternate UOMs)."""
    data = dict(payload or {})
    data["item_code"] = int(item_code)
    return _persist_item(
        data, is_new=False, username=username, fixed_item_code=int(item_code)
    )


def delete_item(
    item_code: int, *, password: str, username: str = "mobile"
) -> dict[str, Any]:
    """Delete ITEMMASTER (+ alternate UOMs) for the current location after password check."""
    from master_activity_log import append_master_activity
    from db import _get_connection, get_item_by_code
    from mobile_backend.database.transaction import oracle_transaction
    from mobile_backend.services.master_delete_auth import require_master_delete_password

    code = int(item_code or 0)
    if code <= 0:
        raise ValueError("Item code is required.")
    require_master_delete_password(password, username=username)

    with mobile_operation_lock(
        "item_delete",
        str(code),
        busy_message="Item delete is already running. Please wait.",
    ), _erp_session_scope() as user:
        im = _itemmaster_mod()
        loc = im._itemmaster_session_location_code()
        existing = get_item_by_code(code, loc)
        if not existing:
            raise ValueError(f"Item {code} not found.")
        item_name = str(
            existing.get("itemname") or existing.get("item_name") or ""
        ).strip()[:200]

        with _get_connection() as conn:
            with oracle_transaction(conn), conn.cursor() as cur:
                # Drop alternates first (same order as HO central delete)
                try:
                    cur.execute(
                        "SELECT COUNT(*) FROM user_tables WHERE table_name = 'ITEMALTERNATEUOMMAP'"
                    )
                    has_alt = int((cur.fetchone() or [0])[0] or 0) > 0
                except Exception:
                    has_alt = False
                if has_alt:
                    cur.execute(
                        "DELETE FROM ITEMALTERNATEUOMMAP WHERE LOCATIONCODE = :loc AND ITEMCODE = :icode",
                        {"loc": int(loc), "icode": code},
                    )
                cur.execute(
                    "DELETE FROM ITEMMASTER WHERE LOCATIONCODE = :loc AND ITEMCODE = :icode",
                    {"loc": int(loc), "icode": code},
                )
                deleted = int(cur.rowcount or 0)
                if deleted <= 0:
                    raise ValueError(f"Failed to delete item {code}.")
                # Optional audit table (HO has ITEMDELETED; ignore if missing)
                try:
                    cur.execute(
                        """
                        INSERT INTO ITEMDELETED (ITEMCODE, ITEMNAME, DELETEDUSER, DELETEDDATE)
                        VALUES (:icode, :iname, :u, SYSDATE)
                        """,
                        {
                            "icode": code,
                            "iname": item_name,
                            "u": str(user or username or "mobile")[:100],
                        },
                    )
                except Exception:
                    pass

        try:
            append_master_activity(
                username=str(user or username or "mobile"),
                action="DELETE",
                entity="item",
                summary=f"location={loc}, item_code={code}, name={item_name[:80]}",
                detail={
                    "locationcode": loc,
                    "itemcode": code,
                    "itemname": item_name,
                    "source": "mobile",
                },
            )
        except Exception:
            pass

        return {
            "item_code": code,
            "item_name": item_name,
            "message": f"Item {item_name or code} deleted ({code}).",
        }
