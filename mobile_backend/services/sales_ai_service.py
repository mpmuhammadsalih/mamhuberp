"""AI-Powered Interactive Sales Mode — OpenAI tool-calling over real catalog + session cart."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from mobile_backend.services.stock_transfer_service import _erp_session_scope

_MAX_TOOL_ROUNDS = 8


def openai_configured() -> bool:
    return bool((os.environ.get("OPENAI_API_KEY") or "").strip())


def _model() -> str:
    return (os.environ.get("OPENAI_MODEL") or "gpt-4o-mini").strip() or "gpt-4o-mini"


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def _sis():
    from mobile_backend.services import sales_invoice_service as sis

    return sis


def get_status() -> dict[str, Any]:
    return {
        "openai_configured": openai_configured(),
        "model": _model() if openai_configured() else "",
        "mode": "ai_sales",
        "languages": [
            {"code": "en", "name": "English"},
            {"code": "ml", "name": "Malayalam"},
            {"code": "hi", "name": "Hindi"},
            {"code": "ar", "name": "Arabic"},
        ],
    }


def _normalize_cart(raw: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not isinstance(raw, list):
        return out
    for row in raw:
        if not isinstance(row, dict):
            continue
        code = str(row.get("item_code") or row.get("itemCode") or "").strip()
        if not code:
            continue
        qty = _to_float(row.get("qty") or row.get("quantity"), 0)
        if abs(qty) < 0.0005:
            continue
        rate = _to_float(row.get("rate") or row.get("price"))
        discount = max(0.0, min(rate, _to_float(row.get("discount"))))
        name = str(row.get("item_name") or row.get("itemName") or "").strip()
        unit = str(row.get("unit") or row.get("uom") or "PCS").strip() or "PCS"
        stock = _to_float(row.get("stock"))
        brand = str(row.get("brand") or "").strip()
        out.append(
            {
                "item_code": code,
                "item_name": name,
                "unit": unit,
                "qty": round(qty, 3),
                "rate": round(rate, 4),
                "discount": round(discount, 4),
                "amount": round((qty * rate) - (qty * discount), 2),
                "stock": round(stock, 3),
                "brand": brand,
            }
        )
    return out


def _cart_line_amount(line: dict[str, Any]) -> float:
    qty = _to_float(line.get("qty"))
    rate = _to_float(line.get("rate"))
    discount = max(0.0, min(rate, _to_float(line.get("discount"))))
    return round((qty * rate) - (qty * discount), 2)


def _cart_total(cart: list[dict[str, Any]]) -> float:
    return round(sum(_cart_line_amount(x) for x in cart), 2)


def _product_card(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize catalog / lookup rows into a stable AI product card."""
    rate = _to_float(
        row.get("rate")
        if row.get("rate") not in (None, "")
        else None
    )
    if rate <= 0:
        rate = _to_float(
            row.get("retail_price")
            or row.get("retail")
            or row.get("RETAILPRICE")
            or row.get("price")
        )
    unit = str(
        row.get("unit")
        or row.get("base_uom")
        or row.get("uom")
        or row.get("BASEUOM")
        or "PCS"
    ).strip() or "PCS"
    stock = _to_float(
        row.get("stock")
        if row.get("stock") not in (None, "")
        else (row.get("current_stock") or row.get("CURRENTSTOCK") or 0)
    )
    return {
        "item_code": str(row.get("item_code") or row.get("ITEMCODE") or "").strip(),
        "item_name": str(row.get("item_name") or row.get("ITEMNAME") or "").strip(),
        "unit": unit,
        "rate": round(rate, 4),
        "stock": round(stock, 3),
        "brand": str(row.get("brand") or "").strip(),
        "barcode": str(
            row.get("barcode") or row.get("manufacturer_id") or row.get("MANUFACTURERID") or ""
        ).strip(),
        "uoms": list(row.get("uoms") or []) if isinstance(row.get("uoms"), list) else [],
    }


def _attach_uoms_and_rate(card: dict[str, Any], sis: Any) -> dict[str, Any]:
    """Fill retail rate + alternate UOM options (with per-UOM rates)."""
    code = str(card.get("item_code") or "").strip()
    if not code:
        return card
    unit = str(card.get("unit") or "PCS").strip() or "PCS"
    uom_opts: list[dict[str, Any]] = []
    try:
        for u in sis.list_item_uoms(code) or []:
            uc = str(u.get("code") or "").strip()
            if not uc:
                continue
            rate = 0.0
            try:
                pricing = sis.get_uom_pricing(code, uc, price_mode="retail") or {}
                rate = _to_float(pricing.get("rate"))
            except Exception:
                rate = 0.0
            uom_opts.append(
                {
                    "unit": uc,
                    "is_base": bool(u.get("is_base")),
                    "conversion_factor": _to_float(u.get("conversion_factor"), 1.0) or 1.0,
                    "rate": round(rate, 4),
                }
            )
    except Exception:
        uom_opts = []

    card["uoms"] = uom_opts

    # Prefer explicit UOM retail price when card rate is missing/zero.
    if _to_float(card.get("rate")) <= 0:
        for o in uom_opts:
            if str(o.get("unit") or "").upper() == unit.upper() and _to_float(o.get("rate")) > 0:
                card["rate"] = round(_to_float(o.get("rate")), 4)
                break
    if _to_float(card.get("rate")) <= 0:
        try:
            pricing = sis.get_uom_pricing(code, unit, price_mode="retail") or {}
            if _to_float(pricing.get("rate")) > 0:
                card["rate"] = round(_to_float(pricing.get("rate")), 4)
        except Exception:
            pass
    if _to_float(card.get("rate")) <= 0:
        for o in uom_opts:
            if _to_float(o.get("rate")) > 0:
                card["rate"] = round(_to_float(o.get("rate")), 4)
                card["unit"] = str(o.get("unit") or card.get("unit") or "PCS")
                break
    return card


def _rate_for_uom(sis: Any, item_code: str, unit: str, fallback: float = 0.0) -> float:
    code = (item_code or "").strip()
    uc = (unit or "").strip() or "PCS"
    if not code:
        return fallback
    try:
        pricing = sis.get_uom_pricing(code, uc, price_mode="retail") or {}
        rate = _to_float(pricing.get("rate"))
        if rate > 0:
            return rate
    except Exception:
        pass
    return fallback


def _tool_schemas() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "search_products",
                "description": (
                    "STEP 1 — Identify products. Search catalog by name, brand, barcode, or keywords. "
                    "Call this first for any product request. Results are shown immediately in Matched products."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_product_details",
                "description": (
                    "STEP 1 — Resolve one product by item code, barcode, or exact name. "
                    "Returns price and UOMs. Matched products updates immediately."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_item_uoms",
                "description": (
                    "STEP 3 — After the product is identified, list sellable UOMs with QR rates. "
                    "Ask the customer ONLY when there is more than one UOM."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {"item_code": {"type": "string"}},
                    "required": ["item_code"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_cart",
                "description": "Return the current shopping cart lines and total.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "add_to_cart",
                "description": (
                    "STEP 4 — Add to cart only after product is identified, "
                    "UOM chosen (or only one UOM exists), and qty is known. "
                    "Pass unit when non-base UOM was selected."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "item_code": {"type": "string"},
                        "qty": {"type": "number", "minimum": 0.001},
                        "unit": {"type": "string"},
                    },
                    "required": ["item_code", "qty"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "update_cart_item",
                "description": "Set absolute quantity for a cart line. Use qty=0 to remove.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "item_code": {"type": "string"},
                        "qty": {"type": "number", "minimum": 0},
                    },
                    "required": ["item_code", "qty"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "remove_from_cart",
                "description": "Remove a product from the cart.",
                "parameters": {
                    "type": "object",
                    "properties": {"item_code": {"type": "string"}},
                    "required": ["item_code"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "clear_cart",
                "description": "Remove all items from the cart.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_alternatives",
                "description": "Find similar/alternative products for a given item using catalog search on its name/brand.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "item_code": {"type": "string"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 12},
                    },
                    "required": ["item_code"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "reorder_last_sale",
                "description": (
                    "Reorder the customer's most recent sales invoice lines into the cart. "
                    "Use when they say last order / last sale / reorder previous items / add what I bought last time. "
                    "Requires a real customer on the session (not walk-in). "
                    "Shows items in Matched products and adds them to the cart with last qtys/UOMs."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "replace_cart": {
                            "type": "boolean",
                            "description": "If true, clear the cart first. Default false (merge/add).",
                        }
                    },
                },
            },
        },
    ]


_SYSTEM = """You are an expert AI salesperson inside a real ERP sales app.
Use ONLY real catalog data from tools. Never invent products, prices, stock, or promotions.

Identification order (strict — ask only when there are multiple options):
1) PRODUCT — Always search/lookup first (search_products / get_product_details). As soon as catalog matches exist, they appear in Matched products automatically. Do not skip this step.
2) BRAND / WHICH ITEM — Ask ONLY if several different products matched (different item codes). If one clear product, skip.
3) UOM — After the product is identified, call list_item_uoms (or use uoms on the product). Ask ONLY if that item has more than one UOM. If only one UOM, use it silently.
4) QTY — Ask ONLY if the customer did not clearly state a quantity (number, or one/a/an/single). Never invent qty.

Then add_to_cart with the resolved item_code + unit + qty.

Other rules:
- If the customer asks to reorder / add last ordered items / last sale / previous bill items, call reorder_last_sale (needs a selected customer, not walk-in). Confirm bill no, count, and QR total briefly.
- If multiple products match and confidence is low, ask a short clarification (name/brand). Do NOT add to cart until the product is clear.
- Multi-item voice orders: for each line, follow the same order (product → brand if needed → uom if needed → qty if needed).
- Prefer add_to_cart / update_cart_item / remove_from_cart for cart changes. Confirm briefly (qty, unit, QR price).
- Keep replies concise (1-3 short sentences) for text-to-speech. Ask one clarifying question at a time.
- Maintain conversation context (pronouns like "that", "add five more", "remove it").
- You may suggest related products with get_alternatives after a firm selection.
- Currency: always QR (Qatari Riyal), never $ / USD / dollars. Format prices like "QR 12.50".
- Product names/SKUs stay as stored in the catalog; explain them in the customer's language.
"""

_LANGUAGE_NAMES = {
    "en": "English",
    "ml": "Malayalam",
    "hi": "Hindi",
    "ar": "Arabic",
}


def _normalize_language(raw: str | None) -> str:
    code = (raw or "en").strip().lower().replace("_", "-")
    if code.startswith("ml"):
        return "ml"
    if code.startswith("hi"):
        return "hi"
    if code.startswith("ar"):
        return "ar"
    if code.startswith("en"):
        return "en"
    return "en" if code not in _LANGUAGE_NAMES else code


def _system_prompt(language: str) -> str:
    lang = _normalize_language(language)
    name = _LANGUAGE_NAMES.get(lang, "English")
    return (
        f"{_SYSTEM}\n"
        f"- Reply entirely in {name} ({lang}). Match the customer's language when they switch mid-chat.\n"
    )


def _run_tool(
    name: str,
    args: dict[str, Any],
    *,
    cart: list[dict[str, Any]],
    warehouse_id: str,
    customer_code: str,
    username: str,
    suggestions: list[dict[str, Any]],
    found_this_turn: list[dict[str, Any]],
) -> Any:
    def _remember(cards: list[dict[str, Any]]) -> None:
        for c in cards:
            code = str(c.get("item_code") or "").strip()
            if not code:
                continue
            if not any(str(x.get("item_code") or "") == code for x in found_this_turn):
                found_this_turn.append(c)
            if not any(str(x.get("item_code") or "") == code for x in suggestions):
                suggestions.append(c)

    sis = _sis()
    if name == "search_products":
        q = str(args.get("query") or "").strip()
        lim = max(1, min(int(args.get("limit") or 10), 20))
        rows = sis.list_catalog_items(
            search=q,
            warehouse_id=warehouse_id or None,
            customer_code=customer_code or None,
            limit=lim,
            username=username,
        )
        cards = [_attach_uoms_and_rate(_product_card(r), sis) for r in rows or [] if isinstance(r, dict)]
        cards = [c for c in cards if c.get("item_code")]
        # Latest search should drive Matched products for this turn.
        found_this_turn.clear()
        _remember(cards)
        return {"count": len(cards), "products": cards}

    if name == "get_product_details":
        q = str(args.get("query") or "").strip()
        item = None
        if q:
            try:
                item = sis.lookup_item(q)
            except Exception:
                item = None
        if not item:
            rows = sis.list_catalog_items(
                search=q,
                warehouse_id=warehouse_id or None,
                customer_code=customer_code or None,
                limit=5,
                username=username,
            )
            cards = [_attach_uoms_and_rate(_product_card(r), sis) for r in rows or [] if isinstance(r, dict)]
            cards = [c for c in cards if c.get("item_code")]
            _remember(cards)
            return {"found": False, "matches": cards}
        card = _attach_uoms_and_rate(_product_card(item if isinstance(item, dict) else {}), sis)
        if card.get("item_code"):
            _remember([card])
        return {"found": bool(card.get("item_code")), "product": card}

    if name == "list_item_uoms":
        code = str(args.get("item_code") or "").strip()
        if not code:
            return {"ok": False, "error": "item_code required"}
        card = {"item_code": code, "unit": "PCS", "rate": 0.0, "item_name": "", "stock": 0.0}
        try:
            item = sis.lookup_item(code)
            if isinstance(item, dict):
                card = _product_card(item)
        except Exception:
            pass
        card = _attach_uoms_and_rate(card, sis)
        _remember([card])
        return {
            "ok": True,
            "item_code": code,
            "item_name": card.get("item_name"),
            "default_unit": card.get("unit"),
            "default_rate": card.get("rate"),
            "uoms": card.get("uoms") or [],
        }

    if name == "get_cart":
        return {"lines": cart, "count": len(cart), "total": _cart_total(cart)}

    if name == "clear_cart":
        cart.clear()
        return {"ok": True, "lines": [], "total": 0.0}

    if name == "remove_from_cart":
        code = str(args.get("item_code") or "").strip()
        before = len(cart)
        cart[:] = [x for x in cart if str(x.get("item_code")) != code]
        return {"ok": True, "removed": before - len(cart), "lines": cart, "total": _cart_total(cart)}

    if name == "update_cart_item":
        code = str(args.get("item_code") or "").strip()
        qty = _to_float(args.get("qty"), 0)
        if qty <= 0.0005:
            cart[:] = [x for x in cart if str(x.get("item_code")) != code]
            return {"ok": True, "removed": True, "lines": cart, "total": _cart_total(cart)}
        for line in cart:
            if str(line.get("item_code")) == code:
                line["qty"] = round(qty, 3)
                line["amount"] = _cart_line_amount(line)
                return {"ok": True, "line": line, "lines": cart, "total": _cart_total(cart)}
        return {"ok": False, "error": "Item not in cart. Use add_to_cart first."}

    if name == "add_to_cart":
        code = str(args.get("item_code") or "").strip()
        qty = _to_float(args.get("qty"), 0)
        unit = str(args.get("unit") or "").strip()
        if not code or qty <= 0:
            return {"ok": False, "error": "item_code and positive qty required"}
        item = None
        try:
            item = sis.lookup_item(code)
        except Exception:
            item = None
        card = None
        if isinstance(item, dict) and item.get("item_code"):
            card = _product_card(item)
            if unit:
                card["unit"] = unit
        if card is None:
            rows = sis.list_catalog_items(
                search=code,
                warehouse_id=warehouse_id or None,
                customer_code=customer_code or None,
                limit=5,
                username=username,
            )
            for r in rows or []:
                if str(r.get("item_code") or "").strip() == code:
                    card = _product_card(r)
                    if unit:
                        card["unit"] = unit
                    break
        if card is None:
            return {"ok": False, "error": f"Product {code} not found in catalog"}
        card = _attach_uoms_and_rate(card, sis)
        if unit:
            card["unit"] = unit
        card["rate"] = round(
            _rate_for_uom(sis, card["item_code"], str(card.get("unit") or "PCS"), _to_float(card.get("rate"))),
            4,
        )
        for line in cart:
            if str(line.get("item_code")) == card["item_code"] and str(line.get("unit")) == card["unit"]:
                line["qty"] = round(_to_float(line.get("qty")) + qty, 3)
                line["rate"] = card["rate"]
                line["amount"] = _cart_line_amount(line)
                _remember([card])
                return {"ok": True, "merged": True, "line": line, "lines": cart, "total": _cart_total(cart)}
        line = {
            "item_code": card["item_code"],
            "item_name": card.get("item_name") or "",
            "unit": card.get("unit") or "PCS",
            "qty": round(qty, 3),
            "rate": card["rate"],
            "discount": 0.0,
            "amount": round(qty * _to_float(card.get("rate")), 2),
            "stock": card.get("stock") or 0,
            "brand": card.get("brand") or "",
        }
        cart.append(line)
        _remember([card])
        return {"ok": True, "merged": False, "line": line, "lines": cart, "total": _cart_total(cart)}

    if name == "get_alternatives":
        code = str(args.get("item_code") or "").strip()
        lim = max(1, min(int(args.get("limit") or 6), 12))
        item = None
        if code:
            try:
                item = sis.lookup_item(code)
            except Exception:
                item = None
        seed = ""
        if isinstance(item, dict):
            seed = str(item.get("brand") or item.get("item_name") or item.get("ITEMNAME") or "").strip()
        if not seed:
            seed = code
        # Use first meaningful token(s)
        tokens = [t for t in re.split(r"\s+", seed) if len(t) > 2][:2]
        q = " ".join(tokens) if tokens else seed
        rows = sis.list_catalog_items(
            search=q,
            warehouse_id=warehouse_id or None,
            customer_code=customer_code or None,
            limit=lim + 3,
            username=username,
        )
        cards = []
        for r in rows or []:
            c = _attach_uoms_and_rate(_product_card(r), sis)
            if c["item_code"] and c["item_code"] != code:
                cards.append(c)
            if len(cards) >= lim:
                break
        _remember(cards)
        return {"count": len(cards), "products": cards, "based_on": code, "query": q}

    if name == "reorder_last_sale":
        cust = (customer_code or "").strip()
        if not cust or cust in ("0", "00"):
            return {
                "ok": False,
                "error": "Select a customer on the setup page first (walk-in has no last order).",
            }
        replace = bool(args.get("replace_cart"))
        try:
            last = sis.get_customer_last_sale(customer_code=cust)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception as exc:
            return {"ok": False, "error": f"Could not load last sale: {exc}"}
        if not last:
            return {"ok": False, "error": f"No previous sales found for customer {cust}."}

        if replace:
            cart.clear()

        added: list[dict[str, Any]] = []
        found_this_turn.clear()
        for ln in last.get("lines") or []:
            code = str(ln.get("item_code") or "").strip()
            qty = _to_float(ln.get("qty"))
            if not code or qty <= 0:
                continue
            unit = str(ln.get("uom") or "PCS").strip() or "PCS"
            card = {
                "item_code": code,
                "item_name": str(ln.get("item_name") or "").strip(),
                "unit": unit,
                "rate": _to_float(ln.get("rate")),
                "stock": 0.0,
                "brand": "",
                "barcode": "",
            }
            # Prefer live catalog name/rate when available.
            try:
                item = sis.lookup_item(code)
                if isinstance(item, dict):
                    card = _product_card(item)
                    card["unit"] = unit
            except Exception:
                pass
            card = _attach_uoms_and_rate(card, sis)
            card["unit"] = unit
            card["rate"] = round(
                _rate_for_uom(sis, code, unit, _to_float(card.get("rate")) or _to_float(ln.get("rate"))),
                4,
            )
            if _to_float(card.get("rate")) <= 0:
                card["rate"] = round(_to_float(ln.get("rate")), 4)

            merged = False
            for line in cart:
                if str(line.get("item_code")) == code and str(line.get("unit")) == unit:
                    line["qty"] = round(_to_float(line.get("qty")) + qty, 3)
                    line["rate"] = card["rate"]
                    line["amount"] = _cart_line_amount(line)
                    if not line.get("item_name") and card.get("item_name"):
                        line["item_name"] = card["item_name"]
                    merged = True
                    added.append(line)
                    break
            if not merged:
                line = {
                    "item_code": code,
                    "item_name": card.get("item_name") or "",
                    "unit": unit,
                    "qty": round(qty, 3),
                    "rate": card["rate"],
                    "discount": 0.0,
                    "amount": round(qty * _to_float(card.get("rate")), 2),
                    "stock": card.get("stock") or 0,
                    "brand": card.get("brand") or "",
                }
                cart.append(line)
                added.append(line)
            _remember([card])

        return {
            "ok": True,
            "billno": last.get("billno"),
            "billdate": last.get("billdate"),
            "customer_code": last.get("customer_code"),
            "customer_name": last.get("customer_name"),
            "added_count": len(added),
            "lines": added,
            "products": list(found_this_turn),
            "cart": cart,
            "total": _cart_total(cart),
            "replaced": replace,
        }

    return {"ok": False, "error": f"Unknown tool {name}"}


def chat(
    *,
    message: str,
    history: list[dict[str, Any]] | None = None,
    cart: list[dict[str, Any]] | None = None,
    warehouse_id: str = "",
    customer_code: str = "",
    username: str = "mobile",
    language: str = "en",
) -> dict[str, Any]:
    """One conversational turn with tool-calling; mutates and returns cart."""
    text = (message or "").strip()
    if not text:
        raise ValueError("Message is required.")
    if not openai_configured():
        raise ValueError("OPENAI_API_KEY is not configured on the server.")

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ValueError("openai package is not installed on the server.") from exc

    working_cart = _normalize_cart(cart)
    suggestions: list[dict[str, Any]] = []
    found_this_turn: list[dict[str, Any]] = []
    wh = (warehouse_id or "").strip()
    cust = (customer_code or "").strip()
    lang = _normalize_language(language)

    messages: list[dict[str, Any]] = [{"role": "system", "content": _system_prompt(lang)}]
    for h in (history or [])[-20:]:
        if not isinstance(h, dict):
            continue
        role = str(h.get("role") or "").strip().lower()
        content = str(h.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    cart_hint = json.dumps(
        {"cart": working_cart, "cart_total": _cart_total(working_cart), "warehouse_id": wh, "customer_code": cust},
        ensure_ascii=False,
    )
    messages.append(
        {
            "role": "user",
            "content": f"{text}\n\n[SESSION_STATE]{cart_hint}[/SESSION_STATE]",
        }
    )

    client = OpenAI(api_key=(os.environ.get("OPENAI_API_KEY") or "").strip())
    tools = _tool_schemas()
    assistant_text = ""
    status_notes: list[str] = []

    with _erp_session_scope() as uname:
        user = (username or uname or "mobile").strip() or "mobile"
        for _ in range(_MAX_TOOL_ROUNDS):
            completion = client.chat.completions.create(
                model=_model(),
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=0.2,
            )
            choice = completion.choices[0].message
            tool_calls = getattr(choice, "tool_calls", None) or []
            if not tool_calls:
                assistant_text = (choice.content or "").strip()
                break
            messages.append(
                {
                    "role": "assistant",
                    "content": choice.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments or "{}",
                            },
                        }
                        for tc in tool_calls
                    ],
                }
            )
            for tc in tool_calls:
                fname = tc.function.name
                try:
                    fargs = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    fargs = {}
                if not isinstance(fargs, dict):
                    fargs = {}
                status_notes.append(fname)
                result = _run_tool(
                    fname,
                    fargs,
                    cart=working_cart,
                    warehouse_id=wh,
                    customer_code=cust,
                    username=user,
                    suggestions=suggestions,
                    found_this_turn=found_this_turn,
                )
                if fname in (
                    "search_products",
                    "get_product_details",
                    "get_alternatives",
                    "list_item_uoms",
                    "reorder_last_sale",
                ):
                    n = len(found_this_turn)
                    if n:
                        status_notes.append(f"found_{n}_products")
                    if fname == "reorder_last_sale":
                        status_notes.append("reordered_last_sale")
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result, ensure_ascii=False, default=str)[:12000],
                    }
                )
        else:
            # Max rounds — ask model for a final spoken reply
            completion = client.chat.completions.create(
                model=_model(),
                messages=messages
                + [
                    {
                        "role": "user",
                        "content": "Give a brief final answer to the customer now.",
                    }
                ],
                temperature=0.2,
            )
            assistant_text = (completion.choices[0].message.content or "").strip()

    if not assistant_text:
        if working_cart:
            assistant_text = f"Cart updated. {len(working_cart)} item(s), total {_cart_total(working_cart):.2f}."
        else:
            assistant_text = "How can I help you find products today?"

    # Strip session leakage if model echoes it
    assistant_text = re.sub(r"\[SESSION_STATE\][\s\S]*?\[/SESSION_STATE\]", "", assistant_text).strip()

    # Prefer products found this turn so Matched products always reflects latest finds.
    matched = found_this_turn if found_this_turn else suggestions

    return {
        "reply": assistant_text,
        "speak": assistant_text,
        "cart": working_cart,
        "cart_total": _cart_total(working_cart),
        "suggestions": matched[:24],
        "status": status_notes[-6:],
        "language": lang,
        "openai_configured": True,
        "model": _model(),
    }
