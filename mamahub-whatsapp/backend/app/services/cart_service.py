"""Shared WhatsApp cart: staff and customer pick products + qty."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.integrations.whatsapp.client import whatsapp_client
from app.models.conversation import Conversation, ConversationCartItem
from app.models.enums import MessageStatus, SenderType
from app.models.message import Message
from app.repositories.oracle.product_repository import OracleItemMasterProductRepository
from app.schemas.crm import CartItemIn, CartItemOut, CartOut, ProductPickIn
from app.utils.phones import normalize_whatsapp


def _clip(value: str, limit: int) -> str:
    text = " ".join((value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 1)] + "…"


def _money(value: float) -> str:
    currency = get_settings().company_currency or "QAR"
    return f"{currency} {float(value):.2f}"


def _unit_price(product: ProductPickIn) -> float:
    offer = float(product.offer_price or 0)
    retail = float(product.retailprice or 0)
    if offer > 0 and retail > 0 and offer < retail:
        return offer
    return retail


def _pick_from_row(row: dict[str, Any]) -> ProductPickIn:
    return ProductPickIn(
        itemcode=str(row.get("itemcode") or ""),
        itemname=str(row.get("itemname") or ""),
        retailprice=float(row.get("retailprice") or 0),
        offer_price=row.get("offer_price"),
        image_url=row.get("image_url"),
        currentstock=float(row.get("currentstock") or 0),
    )


def _offer_items(conversation: Conversation) -> List[dict[str, Any]]:
    raw = conversation.cart_offer_json or ""
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        rows = data.get("items") or []
        return [item for item in rows if isinstance(item, dict)]
    return []


def _find_offer(conversation: Conversation, itemcode: str) -> Optional[dict[str, Any]]:
    code = str(itemcode or "").strip()
    for item in _offer_items(conversation):
        if str(item.get("itemcode") or "") == code or str(item.get("id") or "") == f"p:{code}":
            return item
    return None


def _save_offer(conversation: Conversation, products: List[ProductPickIn]) -> None:
    packed = [
        {
            "id": f"p:{product.itemcode}",
            "itemcode": product.itemcode,
            "itemname": (product.itemname or product.itemcode)[:200],
            "unit_price": _unit_price(product),
            "image_url": (product.image_url or "")[:500] or None,
            "stock": float(product.currentstock or 0),
        }
        for product in products[:10]
    ]
    raw = json.dumps(packed, default=str)
    conversation.cart_offer_json = raw[:2000]


def cart_out(session: Session, conversation_id: int) -> CartOut:
    conversation = session.get(Conversation, conversation_id)
    rows = (
        session.query(ConversationCartItem)
        .filter(ConversationCartItem.conversation_id == conversation_id)
        .order_by(ConversationCartItem.cart_item_id.asc())
        .all()
    )
    items = [
        CartItemOut(
            itemcode=row.itemcode,
            itemname=row.itemname,
            quantity=float(row.quantity or 0),
            unit_price=float(row.unit_price or 0),
            image_url=row.image_url,
            line_total=float(row.quantity or 0) * float(row.unit_price or 0),
        )
        for row in rows
    ]
    return CartOut(
        conversation_id=conversation_id,
        items=items,
        total=sum(item.line_total for item in items),
        pending_sku=conversation.cart_pending_sku if conversation else None,
    )


def replace_cart(session: Session, conversation_id: int, items: List[CartItemIn]) -> CartOut:
    session.query(ConversationCartItem).filter(ConversationCartItem.conversation_id == conversation_id).delete()
    now = datetime.utcnow()
    for item in items:
        qty = max(1, float(item.quantity or 1))
        session.add(
            ConversationCartItem(
                conversation_id=conversation_id,
                itemcode=item.itemcode,
                itemname=item.itemname[:240],
                quantity=qty,
                unit_price=float(item.unit_price or 0),
                image_url=item.image_url,
                updated_at=now,
            )
        )
    session.flush()
    return cart_out(session, conversation_id)


def clear_cart(session: Session, conversation_id: int) -> CartOut:
    conversation = session.get(Conversation, conversation_id)
    session.query(ConversationCartItem).filter(ConversationCartItem.conversation_id == conversation_id).delete()
    if conversation:
        conversation.cart_pending_sku = None
    session.flush()
    return cart_out(session, conversation_id)


def add_item(
    session: Session,
    conversation_id: int,
    *,
    itemcode: str,
    itemname: str,
    quantity: float,
    unit_price: float,
    image_url: Optional[str] = None,
) -> ConversationCartItem:
    qty = max(1, float(quantity or 1))
    row = (
        session.query(ConversationCartItem)
        .filter(
            ConversationCartItem.conversation_id == conversation_id,
            ConversationCartItem.itemcode == itemcode,
        )
        .first()
    )
    now = datetime.utcnow()
    if row:
        row.quantity = float(row.quantity or 0) + qty
        row.unit_price = float(unit_price or row.unit_price or 0)
        row.itemname = itemname[:240]
        row.image_url = image_url or row.image_url
        row.updated_at = now
    else:
        row = ConversationCartItem(
            conversation_id=conversation_id,
            itemcode=itemcode,
            itemname=itemname[:240],
            quantity=qty,
            unit_price=float(unit_price or 0),
            image_url=image_url,
            updated_at=now,
        )
        session.add(row)
    session.flush()
    return row


def _store_bot(
    session: Session,
    conversation: Conversation,
    *,
    text: str,
    msg_type: str,
    wa_id: str,
    ok: bool,
    error: str = "",
    media_url: Optional[str] = None,
) -> Message:
    now = datetime.utcnow()
    row = Message(
        conversation_id=conversation.conversation_id,
        whatsapp_message_id=wa_id or None,
        sender_type=SenderType.SYSTEM.value,
        message_type=msg_type,
        message_text=text,
        media_url=media_url,
        status=MessageStatus.SENT.value if ok else MessageStatus.FAILED.value,
        error_message=(error or None) if not ok else None,
        sent_at=now if ok else None,
        created_at=now,
    )
    session.add(row)
    conversation.last_message_at = now
    conversation.last_message_text = (text or f"[{msg_type}]")[:480]
    conversation.updated_at = now
    session.flush()
    return row


def _send_interactive(session: Session, conversation: Conversation, interactive: Dict[str, Any], preview: str) -> bool:
    phone = normalize_whatsapp(conversation.whatsapp_number)
    ok, wa_id, _ = whatsapp_client.send_interactive_message(phone, interactive)
    _store_bot(
        session,
        conversation,
        text=preview,
        msg_type="interactive",
        wa_id="" if not ok else wa_id,
        ok=ok,
        error="" if ok else wa_id,
    )
    return ok


def _picker_body(products: List[ProductPickIn], *, compact: bool = False) -> str:
    if compact:
        return "Tap Choose items to add a product."
    lines = ["Tap Search catalog to find more items, or pick one below:"]
    for index, product in enumerate(products[:9], start=1):
        name = (product.itemname or product.itemcode or "").strip()
        line = f"{index}. {name} — {_money(product.retailprice)}"
        trial = "\n".join(lines + [line])
        if len(trial) > 1024:
            break
        lines.append(line)
    return "\n".join(lines)


def build_picker(products: List[ProductPickIn], *, compact: bool = False) -> tuple[Dict[str, Any], str]:
    search_row = {
        "id": "cart:search",
        "title": "Search catalog",
        "description": "Tap this, then type the name in the chat",
    }
    rows = []
    for product in products[:9]:
        name = (product.itemname or product.itemcode or "").strip()
        price = _money(product.retailprice)
        if len(name) <= 72:
            description = name if len(f"{name} · {price}") > 72 else f"{name} · {price}"
        else:
            description = _clip(name, 72)
        rows.append(
            {
                "id": f"p:{product.itemcode}"[:200],
                "title": _clip(name, 24),
                "description": description,
            }
        )
    body = _picker_body(products, compact=compact)
    sections = [{"title": "Search", "rows": [search_row]}]
    if rows:
        sections.append({"title": "Products", "rows": rows})
    interactive = {
        "type": "list",
        "header": {"type": "text", "text": "MamaHub catalog"},
        "body": {"text": body},
        "footer": {"text": "Search or tap a product."},
        "action": {
            "button": "Choose items",
            "sections": sections,
        },
    }
    return interactive, body


def _product_caption(product: ProductPickIn) -> str:
    price = _unit_price(product)
    line = f"{product.itemname}\n{_money(price)}"
    offer = float(product.offer_price or 0)
    retail = float(product.retailprice or 0)
    if offer > 0 and retail > 0 and offer < retail:
        line += f"  (was {_money(retail)})"
    return line


def _resolve_send_image(session: Session, product: ProductPickIn) -> Optional[str]:
    from app.utils.product_images import stage_whatsapp_image

    repo = OracleItemMasterProductRepository(session)
    found = repo.get_by_code(product.itemcode) or {}
    candidates = [
        product.image_url,
        found.get("image_url"),
        repo.gallery_image_url(product.itemcode),
    ]
    for raw in candidates:
        staged = stage_whatsapp_image(raw, product.itemcode)
        if staged:
            return staged
    staged = stage_whatsapp_image(None, product.itemcode)
    if staged:
        return staged
    logger.warning("No product photo for catalog item %s", product.itemcode)
    return None


def _send_product_images(
    session: Session,
    conversation: Conversation,
    picks: List[ProductPickIn],
    *,
    image_limit: int,
    cards: bool,
) -> int:
    phone = normalize_whatsapp(conversation.whatsapp_number)
    sent_images = 0
    if cards:
        from app.services.product_cards import save_catalog_cards

        for path, caption in save_catalog_cards(picks, limit=image_limit):
            ok, wa_id, _ = whatsapp_client.send_image_message(phone, path.name, caption)
            _store_bot(
                session,
                conversation,
                text=caption,
                msg_type="image",
                wa_id="" if not ok else wa_id,
                ok=ok,
                error="" if ok else wa_id,
                media_url=f"/api/media/{path.name}",
            )
            sent_images += 1
        if sent_images:
            return sent_images
    for product in picks:
        if sent_images >= image_limit:
            break
        image = _resolve_send_image(session, product)
        if not image:
            continue
        caption = _product_caption(product)
        ok, wa_id, _ = whatsapp_client.send_image_message(phone, image, caption)
        _store_bot(
            session,
            conversation,
            text=caption,
            msg_type="image",
            wa_id="" if not ok else wa_id,
            ok=ok,
            error="" if ok else wa_id,
            media_url=f"/api/media/{image}" if not str(image).startswith("http") else image,
        )
        sent_images += 1
    return sent_images


def send_picker(
    session: Session,
    conversation: Conversation,
    products: List[ProductPickIn],
    *,
    image_limit: int = 10,
    cards: bool = False,
    images_only: bool = False,
) -> str:
    picks = [product for product in products if product.itemcode][:10]
    if not picks:
        return ""
    _save_offer(conversation, picks)
    conversation.cart_pending_sku = None
    sent_images = 0
    if image_limit > 0:
        sent_images = _send_product_images(session, conversation, picks, image_limit=image_limit, cards=cards)
    if images_only:
        return "Sent product images."
    interactive, preview = build_picker(picks, compact=sent_images > 0)
    _send_interactive(session, conversation, interactive, preview)
    return preview


def _qty_buttons(item: dict[str, Any]) -> tuple[Dict[str, Any], str]:
    name = item.get("itemname") or item.get("itemcode") or "this item"
    price = float(item.get("unit_price") or 0)
    body = f"{name}\n{_money(price)}\nHow many? For more than 2, tap More or type a number."
    interactive = {
        "type": "button",
        "body": {"text": body[:1024]},
        "action": {
            "buttons": [
                {"type": "reply", "reply": {"id": "qty:1", "title": "Qty 1"}},
                {"type": "reply", "reply": {"id": "qty:2", "title": "Qty 2"}},
                {"type": "reply", "reply": {"id": "qty:more", "title": "More"}},
            ]
        },
    }
    return interactive, body


def _qty_more_list() -> tuple[Dict[str, Any], str]:
    rows = [{"id": f"qty:{n}", "title": f"Qty {n}", "description": f"Add {n} pieces"} for n in (3, 4, 5, 6, 7, 8, 9, 10)]
    body = "Choose a quantity, or type any number in the chat (example: 12)."
    interactive = {
        "type": "list",
        "header": {"type": "text", "text": "Quantity"},
        "body": {"text": body},
        "footer": {"text": "You can also type 11, 15, 20…"},
        "action": {"button": "More qty", "sections": [{"title": "Quantity", "rows": rows}]},
    }
    return interactive, body


def _cart_actions(summary: str) -> tuple[Dict[str, Any], str]:
    body = f"{summary}\nAdd more, edit qty / remove, or finish."
    interactive = {
        "type": "button",
        "body": {"text": body[:1024]},
        "action": {
            "buttons": [
                {"type": "reply", "reply": {"id": "cart:more", "title": "Add more"}},
                {"type": "reply", "reply": {"id": "cart:edit", "title": "Edit cart"}},
                {"type": "reply", "reply": {"id": "cart:done", "title": "Done"}},
            ]
        },
    }
    return interactive, body


def _edit_list(session: Session, conversation_id: int) -> tuple[Dict[str, Any], str]:
    data = cart_out(session, conversation_id)
    rows = []
    for item in data.items[:10]:
        rows.append(
            {
                "id": f"e:{item.itemcode}"[:200],
                "title": _clip(item.itemname, 24),
                "description": _clip(f"Qty {item.quantity:g} · {_money(item.line_total)} · {item.itemname}", 72),
            }
        )
    body = f"{cart_summary(session, conversation_id)}\nTap an item to change quantity or remove it."
    interactive = {
        "type": "list",
        "header": {"type": "text", "text": "Edit cart"},
        "body": {"text": body[:1024]},
        "footer": {"text": "Tap one line to edit."},
        "action": {"button": "Edit items", "sections": [{"title": "Cart", "rows": rows}]},
    }
    return interactive, body


def _edit_buttons(item: ConversationCartItem) -> tuple[Dict[str, Any], str]:
    body = f"{item.itemname}\nCurrent qty: {float(item.quantity):g} · {_money(float(item.quantity) * float(item.unit_price))}"
    interactive = {
        "type": "button",
        "body": {"text": body[:1024]},
        "action": {
            "buttons": [
                {"type": "reply", "reply": {"id": "adj:plus", "title": "+1"}},
                {"type": "reply", "reply": {"id": "adj:minus", "title": "−1"}},
                {"type": "reply", "reply": {"id": "adj:rm", "title": "Remove"}},
            ]
        },
    }
    return interactive, body


def cart_summary(session: Session, conversation_id: int) -> str:
    data = cart_out(session, conversation_id)
    if not data.items:
        return "Your cart is empty."
    lines = [f"Cart ({len(data.items)} item{'s' if len(data.items) != 1 else ''}):"]
    for item in data.items:
        lines.append(f"• {item.itemname} x {item.quantity:g} = {_money(item.line_total)}")
    lines.append(f"Total {_money(data.total)}")
    return "\n".join(lines)


def _resolve_product(session: Session, conversation: Conversation, itemcode: str) -> Optional[dict[str, Any]]:
    offered = _find_offer(conversation, itemcode)
    if offered:
        return offered
    found = OracleItemMasterProductRepository(session).get_by_code(itemcode)
    if not found:
        return None
    return {
        "itemcode": found["itemcode"],
        "itemname": found["itemname"],
        "unit_price": found["retailprice"],
        "image_url": found.get("image_url"),
    }


def _interactive_ids(payload: Any) -> tuple[Optional[str], Optional[str]]:
    if not isinstance(payload, dict):
        return None, None
    interactive = payload.get("interactive")
    if not isinstance(interactive, dict):
        for key in ("list_reply", "button_reply"):
            row = payload.get(key)
            if isinstance(row, dict) and (row.get("id") or row.get("title")):
                return row.get("id"), row.get("title")
        return None, None
    row = interactive.get("list_reply") or interactive.get("button_reply") or {}
    if isinstance(row, dict):
        return row.get("id"), row.get("title")
    return None, None


def _is_search_trigger(reply_id: Optional[str], title: Optional[str], text: str) -> bool:
    blob = " ".join(part for part in (reply_id, title, text) if part).lower()
    return reply_id == "cart:search" or "search catalog" in blob or blob.strip() in {"search", "search products"}


def _ask_for_search(session: Session, conversation: Conversation) -> bool:
    conversation.cart_pending_sku = "search:"
    phone = normalize_whatsapp(conversation.whatsapp_number)
    text_out = "Type the product name, brand, or code here in the chat — for example: Hot Wheels"
    ok, wa_id, _ = whatsapp_client.send_text_message(phone, text_out)
    _store_bot(session, conversation, text=text_out, msg_type="text", wa_id="" if not ok else wa_id, ok=ok, error="" if ok else wa_id)
    return True


def _latest_customer_message(session: Session, conversation_id: int) -> Optional[Message]:
    return (
        session.query(Message)
        .filter(Message.conversation_id == conversation_id, Message.sender_type == SenderType.CUSTOMER.value)
        .order_by(Message.created_at.desc())
        .first()
    )


def _catalog_auto_on(session: Session) -> bool:
    from app.models.content import Setting

    row = session.query(Setting).filter(Setting.setting_key == "ai_auto_reply").first()
    return str(row.setting_value or "0").strip().lower() in {"1", "true", "yes", "on"} if row else False


def handle_inbound(session: Session, conversation_id: int) -> bool:
    conversation = session.get(Conversation, conversation_id)
    message = _latest_customer_message(session, conversation_id)
    if not conversation or not message:
        return False

    payload: Any = {}
    if message.payload_json:
        try:
            payload = json.loads(message.payload_json)
        except json.JSONDecodeError:
            payload = {}
    reply_id, reply_title = _interactive_ids(payload)
    text = (message.message_text or "").strip()

    if _is_search_trigger(reply_id, reply_title, text):
        if reply_id != "cart:search" and not _catalog_auto_on(session):
            return False
        return _ask_for_search(session, conversation)

    if reply_id and str(reply_id).startswith("p:"):
        itemcode = str(reply_id)[2:]
        item = _resolve_product(session, conversation, itemcode)
        if not item:
            phone = normalize_whatsapp(conversation.whatsapp_number)
            ok, wa_id, _ = whatsapp_client.send_text_message(phone, "Sorry, I could not find that product. Please ask us to send the list again.")
            _store_bot(session, conversation, text="Product not found.", msg_type="text", wa_id="" if not ok else wa_id, ok=ok, error="" if ok else wa_id)
            return True
        conversation.cart_pending_sku = item.get("itemcode")
        interactive, preview = _qty_buttons(item)
        _send_interactive(session, conversation, interactive, preview)
        return True

    if reply_id == "qty:more":
        interactive, preview = _qty_more_list()
        _send_interactive(session, conversation, interactive, preview)
        return True

    if reply_id and str(reply_id).startswith("qty:"):
        try:
            qty = max(1, min(99, int(str(reply_id).split(":", 1)[1])))
        except ValueError:
            qty = 1
        return _add_pending(session, conversation, qty)

    if reply_id == "cart:more":
        products = [
            ProductPickIn(
                itemcode=str(item.get("itemcode") or ""),
                itemname=str(item.get("itemname") or ""),
                retailprice=float(item.get("unit_price") or 0),
                image_url=item.get("image_url"),
                currentstock=float(item.get("stock") or 0),
            )
            for item in _offer_items(conversation)
            if item.get("itemcode")
        ]
        if products:
            send_picker(session, conversation, products, image_limit=4, cards=False)
        else:
            phone = normalize_whatsapp(conversation.whatsapp_number)
            ok, wa_id, _ = whatsapp_client.send_text_message(phone, "Type a product name and I will send a catalog you can tap.")
            _store_bot(session, conversation, text="Ask for more products.", msg_type="text", wa_id="" if not ok else wa_id, ok=ok, error="" if ok else wa_id)
        return True

    if reply_id in {"cart:view", "cart:edit"}:
        return _send_cart_editor(session, conversation)

    if reply_id and str(reply_id).startswith("e:"):
        return _start_line_edit(session, conversation, str(reply_id)[2:])

    if reply_id in {"adj:plus", "adj:minus", "adj:rm"}:
        return _adjust_pending(session, conversation, str(reply_id))

    if reply_id == "cart:done":
        summary = cart_summary(session, conversation_id)
        phone = normalize_whatsapp(conversation.whatsapp_number)
        text_out = f"{summary}\nOur team will confirm your order shortly."
        ok, wa_id, _ = whatsapp_client.send_text_message(phone, text_out)
        _store_bot(session, conversation, text=text_out, msg_type="text", wa_id="" if not ok else wa_id, ok=ok, error="" if ok else wa_id)
        conversation.cart_pending_sku = None
        return True

    pending_kind, pending_sku = _pending_parts(conversation.cart_pending_sku)
    if pending_kind == "search" and len(text) >= 2:
        if not _catalog_auto_on(session):
            conversation.cart_pending_sku = None
            return False
        conversation.cart_pending_sku = None
        return _search_and_send(session, conversation, text)

    if pending_sku and pending_kind != "search" and re.fullmatch(r"[1-9]\d{0,1}", text):
        qty = min(99, int(text))
        if pending_kind == "edit":
            return _set_pending_qty(session, conversation, qty)
        return _add_pending(session, conversation, qty)

    if _is_short_product_query(text) and _catalog_auto_on(session):
        return _search_and_send(session, conversation, text)

    return False


_SEARCH_SKIP = re.compile(
    r"^(hi|hello|hey|ok|okay|yes|no|thanks|thank you|please|help|salaam|salam)$",
    re.I,
)
_SEARCH_SKIP_WORDS = re.compile(r"\b(order|bill|track|status|delivery|address|payment|invoice)\b", re.I)
_SEARCH_STOP = {
    "have", "please", "under", "qar", "the", "and", "you", "for", "this", "that",
    "with", "from", "your", "can", "how", "what", "when", "where", "need", "want",
    "types", "type", "kind", "kinds", "some", "any", "are",
    "much", "many", "about", "inside", "show", "send", "looking", "look",
}
_OFFER_WORDS = {"offer", "offers", "deal", "deals", "discount", "sale"}
_BROWSE_ASK = re.compile(
    r"\b(what|which).*\b(offer|have|sell|available|types?|kind|toys?|products?)\b"
    r"|\b(show|send|see).*\b(catalog|products?|toys?)\b"
    r"|\bdo you (have|sell|offer)\b",
    re.I,
)
_BROWSE_TERMS = ("car", "doll", "puzzle", "lego", "bike")


def _search_terms(text: str) -> List[str]:
    tokens = [
        token.lower()
        for token in re.findall(r"[A-Za-z0-9]{3,}", text or "")
        if token.lower() not in _SEARCH_STOP
    ]
    terms: List[str] = []
    for token in tokens:
        for piece in (token, token[:-1] if token.endswith("s") and len(token) > 4 else ""):
            if piece and piece not in terms and piece not in _SEARCH_STOP:
                terms.append(piece)
    lowered = (text or "").lower()
    if any(word in lowered for word in _OFFER_WORDS) and "offer" not in terms:
        terms.insert(0, "offer")
    if not terms and _BROWSE_ASK.search(text or ""):
        return ["offer", *_BROWSE_TERMS]
    if "toy" in terms or "toys" in lowered:
        extra = [word for word in _BROWSE_TERMS if word not in terms]
        terms.extend(extra[:3])
    return terms[:6]


def _looks_like_search(text: str) -> bool:
    value = (text or "").strip()
    if len(value) < 2:
        return False
    if re.fullmatch(r"[1-9]\d{0,1}", value):
        return False
    if _SEARCH_SKIP.fullmatch(value):
        return False
    if _SEARCH_SKIP_WORDS.search(value):
        return False
    if "search catalog" in value.lower():
        return False
    if _BROWSE_ASK.search(value):
        return True
    if _search_terms(value):
        return True
    return len(value.split()) <= 4


def _is_short_product_query(text: str) -> bool:
    value = (text or "").strip()
    if not value or _SEARCH_SKIP.fullmatch(value):
        return False
    if _SEARCH_SKIP_WORDS.search(value):
        return False
    if _BROWSE_ASK.search(value):
        return False
    if re.search(r"\b(what|which|how|can you|do you|please|thank|inside)\b", value, re.I):
        return False
    if len(value.split()) > 5:
        return False
    return bool(_search_terms(value)) or bool(re.fullmatch(r"\d{3,}", value))


def _search_and_send(session: Session, conversation: Conversation, query: str) -> bool:
    if _is_search_trigger(None, None, query):
        return _ask_for_search(session, conversation)
    repo = OracleItemMasterProductRepository(session)
    terms = _search_terms(query) or [query.strip()]
    found: dict[str, dict[str, Any]] = {}
    if any(term in _OFFER_WORDS for term in terms) or any(word in (query or "").lower() for word in _OFFER_WORDS):
        extras = [term for term in terms if term not in _OFFER_WORDS]
        for row in repo.list_offers(limit=30 if extras else 9):
            name = (row.get("itemname") or "").lower()
            if extras and not any(term in name or term in str(row.get("category") or "").lower() for term in extras):
                continue
            code = str(row.get("itemcode") or "")
            if code:
                found[code] = row
            if len(found) >= 9:
                break
        if not found:
            for row in repo.list_offers(limit=9):
                code = str(row.get("itemcode") or "")
                if code:
                    found[code] = row
    for term in terms:
        if term in _OFFER_WORDS:
            continue
        for row in repo.search(term, limit=9):
            code = str(row.get("itemcode") or "")
            if code and code not in found:
                found[code] = row
        if len(found) >= 9:
            break
    rows = list(found.values())[:9]
    phone = normalize_whatsapp(conversation.whatsapp_number)
    if not rows:
        shopping = bool(conversation.cart_offer_json or conversation.cart_pending_sku)
        if not shopping:
            return False
        text_out = "I could not find that exact item. Tell us a product name, brand, or age — for example: Hot Wheels, dolls, or 5 years."
        ok, wa_id, _ = whatsapp_client.send_text_message(phone, text_out)
        _store_bot(session, conversation, text=text_out, msg_type="text", wa_id="" if not ok else wa_id, ok=ok, error="" if ok else wa_id)
        return True
    products = [_pick_from_row(row) for row in rows if row.get("itemcode")]
    send_picker(session, conversation, products, image_limit=4, cards=False)
    return True


def _pending_parts(raw: Optional[str]) -> tuple[str, str]:
    value = (raw or "").strip()
    if value.startswith("edit:"):
        return "edit", value[5:]
    if value.startswith("search"):
        return "search", "1"
    return "qty", value


def _cart_line(session: Session, conversation_id: int, itemcode: str) -> Optional[ConversationCartItem]:
    return (
        session.query(ConversationCartItem)
        .filter(ConversationCartItem.conversation_id == conversation_id, ConversationCartItem.itemcode == itemcode)
        .first()
    )


def _send_cart_editor(session: Session, conversation: Conversation) -> bool:
    data = cart_out(session, conversation.conversation_id)
    if not data.items:
        phone = normalize_whatsapp(conversation.whatsapp_number)
        ok, wa_id, _ = whatsapp_client.send_text_message(phone, "Your cart is empty. Type a product name or tap Add more.")
        _store_bot(session, conversation, text="Cart is empty.", msg_type="text", wa_id="" if not ok else wa_id, ok=ok, error="" if ok else wa_id)
        return True
    interactive, preview = _edit_list(session, conversation.conversation_id)
    _send_interactive(session, conversation, interactive, preview)
    return True


def _start_line_edit(session: Session, conversation: Conversation, itemcode: str) -> bool:
    row = _cart_line(session, conversation.conversation_id, itemcode)
    if not row:
        return _send_cart_editor(session, conversation)
    conversation.cart_pending_sku = f"edit:{row.itemcode}"
    interactive, preview = _edit_buttons(row)
    _send_interactive(session, conversation, interactive, preview)
    return True


def _adjust_pending(session: Session, conversation: Conversation, action: str) -> bool:
    kind, itemcode = _pending_parts(conversation.cart_pending_sku)
    if kind != "edit" or not itemcode:
        return _send_cart_editor(session, conversation)
    row = _cart_line(session, conversation.conversation_id, itemcode)
    if not row:
        conversation.cart_pending_sku = None
        return _send_cart_editor(session, conversation)
    qty = float(row.quantity or 1)
    if action == "adj:plus":
        row.quantity = qty + 1
    elif action == "adj:minus":
        if qty <= 1:
            session.delete(row)
        else:
            row.quantity = qty - 1
    else:
        session.delete(row)
    session.flush()
    conversation.cart_pending_sku = None
    return _send_cart_editor(session, conversation)


def _set_pending_qty(session: Session, conversation: Conversation, quantity: int) -> bool:
    kind, itemcode = _pending_parts(conversation.cart_pending_sku)
    if kind != "edit" or not itemcode:
        return False
    row = _cart_line(session, conversation.conversation_id, itemcode)
    if not row:
        conversation.cart_pending_sku = None
        return _send_cart_editor(session, conversation)
    if quantity < 1:
        session.delete(row)
    else:
        row.quantity = quantity
    session.flush()
    conversation.cart_pending_sku = None
    return _send_cart_editor(session, conversation)


def _add_pending(session: Session, conversation: Conversation, quantity: int) -> bool:
    kind, itemcode = _pending_parts(conversation.cart_pending_sku)
    if kind == "edit":
        return _set_pending_qty(session, conversation, quantity)
    if not itemcode:
        return False
    item = _resolve_product(session, conversation, itemcode)
    if not item:
        return False
    add_item(
        session,
        conversation.conversation_id,
        itemcode=str(item.get("itemcode") or itemcode),
        itemname=str(item.get("itemname") or itemcode),
        quantity=quantity,
        unit_price=float(item.get("unit_price") or 0),
        image_url=item.get("image_url"),
    )
    conversation.cart_pending_sku = None
    added = f"Added {quantity} × {item.get('itemname') or itemcode}."
    summary = f"{added}\n{cart_summary(session, conversation.conversation_id)}"
    interactive, preview = _cart_actions(summary)
    _send_interactive(session, conversation, interactive, preview)
    return True
