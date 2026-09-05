"""Mobile GRN AI — wraps ERP goods-receipt AI extract + quick-create item."""

from __future__ import annotations

import json
import logging
from typing import Any

from mobile_backend.operation_lock import mobile_operation_lock
from mobile_backend.services.stock_transfer_service import _erp_session_scope

logger = logging.getLogger(__name__)


def _purchase_st() -> Any:
    from addons.purchase.controllers import routes as st

    return st


def _unwrap_erp_json(resp: Any) -> dict[str, Any]:
    """Normalize ERP jsonify / (jsonify, status) into a dict; raise ValueError on failure."""
    status = 200
    body = resp
    if isinstance(resp, tuple) and resp:
        body = resp[0]
        if len(resp) > 1 and isinstance(resp[1], int):
            status = resp[1]
    if hasattr(body, "status_code"):
        try:
            status = int(body.status_code)
        except (TypeError, ValueError):
            pass
    payload: Any = None
    if isinstance(body, dict):
        payload = body
    elif hasattr(body, "body"):
        raw = body.body
        if isinstance(raw, (bytes, bytearray)):
            payload = json.loads(raw.decode("utf-8") or "{}")
        elif isinstance(raw, memoryview):
            payload = json.loads(raw.tobytes().decode("utf-8") or "{}")
    elif hasattr(body, "content"):
        # Starlette JSONResponse may expose rendered content
        try:
            payload = json.loads(body.content.decode("utf-8") or "{}")
        except Exception:
            payload = None

    if not isinstance(payload, dict):
        raise RuntimeError("Unexpected AI response from ERP.")

    if status >= 400 or payload.get("success") is False:
        err = str(payload.get("error") or payload.get("message") or "AI request failed.")
        raise ValueError(err[:500])
    return payload


def extract_invoice() -> dict[str, Any]:
    """
    Run ERP ``api_receipt_ai_invoice_extract`` against the current multipart request
    (field name ``file``, same as ERP). Requires NexaHttpMiddleware form parse.
    """
    with mobile_operation_lock(
        "grn_ai_extract",
        "invoice",
        lock_seconds=300.0,
        busy_message="Invoice AI is already running. Please wait.",
    ), _erp_session_scope():
        st = _purchase_st()
        st._apply_db()
        payload = _unwrap_erp_json(st.api_receipt_ai_invoice_extract())
        # Drop heavy preview blobs for mobile
        payload.pop("invoice_preview_images", None)
        return {
            "header": payload.get("header") or {},
            "lines": payload.get("lines") or [],
            "warnings": payload.get("warnings") or [],
            "import_report": payload.get("import_report") or {},
            "extracted": payload.get("extracted") or {},
        }


def _itemmaster_st() -> Any:
    from addons.itemmaster.controllers import routes as im

    return im


def quick_item_lookups() -> dict[str, Any]:
    """ERP GET ``/purchase/receipt/api/grn-quick-item``."""
    from mobile_backend.request_context import get_current_request

    req = get_current_request()
    if req is not None:
        # Force GET semantics for ERP handler that branches on request.method
        req.scope["method"] = "GET"

    with _erp_session_scope():
        st = _purchase_st()
        st._apply_db()
        payload = _unwrap_erp_json(st.api_receipt_grn_quick_item())
        next_code = payload.get("next_item_code")
        suggested_barcode = ""
        try:
            from db import format_location_prefix_item_barcode

            loc = st._resolve_location_code()
            if next_code is not None and int(float(next_code)) > 0:
                suggested_barcode = str(
                    format_location_prefix_item_barcode(loc, int(float(next_code))) or ""
                ).strip()
        except Exception:
            suggested_barcode = ""
        return {
            "next_item_code": next_code,
            "suggested_barcode": suggested_barcode,
            "units": payload.get("units") or [],
            "main_categories": payload.get("main_categories") or [],
            "categories": payload.get("categories") or [],
            "micro_categories": payload.get("micro_categories") or [],
            "brands": payload.get("brands") or [],
            "suppliers": payload.get("suppliers") or [],
            "default_accounts": payload.get("default_accounts") or {},
        }


def suggest_item_fields(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    ERP Item Master AI helpers used by GRN quick-create:
    - barcode web lookup (when barcode provided)
    - similar-item general fill (categories / UOM / description / Arabic)
    """
    from mobile_backend.request_context import get_current_request

    body = dict(payload or {})
    barcode = str(body.get("barcode") or body.get("manufacturer_id") or "").strip()
    item_name = str(body.get("item_name") or body.get("itemname") or "").strip()

    req = get_current_request()
    out: dict[str, Any] = {
        "found": False,
        "source": "",
        "general": {},
        "product": {},
        "matched_item_code": None,
        "matched_item_name": None,
        "match_score": None,
        "message": "",
        "already_exists": False,
        "already_in_master": False,
    }

    with _erp_session_scope():
        im = _itemmaster_st()

        if barcode:
            if req is not None:
                req.scope["method"] = "POST"
                req.state._nexa_json = {"barcode": barcode}
            web = _unwrap_erp_json(im.itemmaster_ai_barcode_web())
            out["already_exists"] = bool(web.get("already_exists") or web.get("already_in_master"))
            out["already_in_master"] = bool(web.get("already_in_master"))
            if web.get("item_code") is not None:
                out["matched_item_code"] = web.get("item_code")
            if web.get("item_name"):
                out["matched_item_name"] = web.get("item_name")
            product = web.get("product") or {}
            if isinstance(product, dict):
                out["product"] = product
                if not item_name:
                    item_name = str(product.get("item_name") or "").strip()
            if web.get("found") and web.get("general"):
                out["found"] = True
                out["source"] = str(web.get("source") or "web")
                out["general"] = web.get("general") or {}
                out["message"] = str(web.get("message") or "Loaded from barcode lookup.")
                # Master hit already has full general; skip second match.
                if out["already_in_master"]:
                    return out
            elif web.get("already_exists"):
                out["found"] = False
                out["source"] = "master"
                out["message"] = str(
                    web.get("message")
                    or f"Barcode already exists in Item Master ({out.get('matched_item_code') or barcode})."
                )
                return out

        if not item_name:
            if not out["message"]:
                out["message"] = "Item name is required for AI fill."
            return out

        if req is not None:
            req.scope["method"] = "POST"
            req.state._nexa_json = {"item_name": item_name}
        fill = _unwrap_erp_json(im.itemmaster_ai_general_fill())
        if fill.get("found") and fill.get("general"):
            g = dict(fill.get("general") or {})
            # Prefer web product name/desc when empty in template general
            prod = out.get("product") or {}
            if isinstance(prod, dict):
                if not str(g.get("description") or "").strip() and prod.get("description"):
                    g["description"] = prod.get("description")
                if not str(g.get("item_name_ara") or "").strip() and prod.get("item_name_ara"):
                    g["item_name_ara"] = prod.get("item_name_ara")
            out["found"] = True
            out["source"] = out["source"] or "similar_item"
            out["general"] = g
            out["matched_item_code"] = fill.get("matched_item_code") or out.get("matched_item_code")
            out["matched_item_name"] = fill.get("matched_item_name") or out.get("matched_item_name")
            out["match_score"] = fill.get("match_score")
            out["message"] = str(fill.get("message") or "Filled from similar item.")
            if not str(g.get("item_name_ara") or "").strip():
                if req is not None:
                    req.state._nexa_json = {"item_name": item_name}
                try:
                    ar = _unwrap_erp_json(im.itemmaster_ai_arabic_name())
                    if ar.get("arabic_name"):
                        g["item_name_ara"] = ar.get("arabic_name")
                        out["general"] = g
                except Exception:
                    pass
            # Surface product name from web when we only had barcode
            if isinstance(prod, dict) and prod.get("item_name"):
                out["product"] = prod
            return out

        out["match_score"] = fill.get("match_score")
        if not out["message"]:
            out["message"] = str(fill.get("message") or "No similar item found.")
        # Still try Arabic suggest when name present
        if req is not None:
            req.state._nexa_json = {"item_name": item_name}
        try:
            ar = _unwrap_erp_json(im.itemmaster_ai_arabic_name())
            if ar.get("arabic_name"):
                out["general"] = {"item_name_ara": ar.get("arabic_name")}
        except Exception:
            pass
        return out


def create_quick_item(payload: dict[str, Any]) -> dict[str, Any]:
    """ERP POST quick-create item (barcode + name + retail required)."""
    from mobile_backend.request_context import get_current_request
    from db import format_location_prefix_item_barcode, get_next_item_code

    body = dict(payload or {})
    barcode = str(body.get("barcode") or body.get("manufacturer_id") or "").strip()

    req = get_current_request()
    with mobile_operation_lock(
        "grn_ai_quick_item",
        barcode or "new",
        busy_message="Item create is already running. Please wait.",
    ), _erp_session_scope():
        st = _purchase_st()
        st._apply_db()
        loc = st._resolve_location_code()
        # If AI/web did not return a barcode, generate Item Master style 12…itemcode (13 digits).
        if not barcode:
            try:
                next_code = int(get_next_item_code(loc) or 0)
            except Exception:
                next_code = 0
            if next_code > 0:
                barcode = str(format_location_prefix_item_barcode(loc, next_code) or "").strip()
            if not barcode:
                raise ValueError("Barcode is required")
            body["barcode"] = barcode
            body["manufacturer_id"] = barcode

        if req is not None:
            req.scope["method"] = "POST"
            req.state._nexa_json = body

        data = _unwrap_erp_json(st.api_receipt_grn_quick_item())
        return {
            "itemcode": str(data.get("itemcode") or "").strip(),
            "itemname": str(data.get("itemname") or "").strip(),
            "barcode": str(data.get("barcode") or barcode).strip(),
            "uom": str(data.get("uom") or "").strip(),
            "retail": float(data.get("retail") or 0),
            "cost": float(data.get("cost") or 0),
            "already_existed": bool(data.get("already_existed")),
        }


def barcode_check(barcode: str) -> dict[str, Any]:
    """ERP barcode existence check for quick-item modal."""
    bc = (barcode or "").strip()
    if not bc:
        raise ValueError("Barcode is required")
    with _erp_session_scope():
        st = _purchase_st()
        st._apply_db()
        loc_code = st._resolve_location_code()
        row = st._grn_quick_item_barcode_lookup(bc, loc_code)
        if not row:
            return {"exists": False, "barcode": bc}
        return {
            "exists": True,
            "itemcode": row.get("code"),
            "itemname": row.get("name") or row.get("itemname"),
            "barcode": row.get("barcode") or bc,
            "uom": row.get("uom"),
            "barcode_source": row.get("barcode_source") or "master",
        }
