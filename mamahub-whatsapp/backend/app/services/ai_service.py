from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional

from openai import OpenAI
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import logger
from app.integrations.whatsapp.client import whatsapp_client
from app.models.content import Setting
from app.models.conversation import Conversation
from app.models.customer import Customer
from app.models.enums import MessageStatus, SenderType
from app.models.message import Message
from app.models.order import Order
from app.repositories.oracle.product_repository import OracleItemMasterProductRepository
from app.schemas.crm import ProductOut, SuggestReplyResponse
from app.utils.phones import normalize_whatsapp


STOP_WORDS = {
    "have", "please", "under", "qar", "the", "and", "you", "for", "this", "that",
    "with", "from", "your", "can", "how", "what", "when", "where", "need", "want",
    "types", "type", "kind", "kinds", "some", "any", "are",
    "much", "many", "about", "inside", "show", "send",
}

PRODUCT_HINTS = {
    "toy", "toys", "car", "cars", "doll", "dolls", "bike", "ball", "puzzle", "lego",
    "hot", "wheels", "price", "stock", "available", "buy", "order", "show", "send",
    "looking", "have", "any", "item", "product", "gun", "baby", "squishy",
    "offer", "offers", "deal", "deals", "discount",
}


def _setting(session: Session, key: str, default: str = "") -> str:
    row = session.query(Setting).filter(Setting.setting_key == key).first()
    return (row.setting_value if row and row.setting_value is not None else default) or default


def _truthy(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _clean_reply(text: str) -> str:
    value = (text or "").strip()
    value = re.sub(r"^(agent|ai|assistant)\s*:\s*", "", value, flags=re.I)
    return value.strip() or "Hi! How can I help you today?"


@dataclass
class AgentTurn:
    reply: str
    products: List[ProductOut] = field(default_factory=list)
    send_products: bool = False
    intent: str = "other"


def _search_products(session: Session, query: str, limit: int = 6) -> List[ProductOut]:
    from app.services.cart_service import _OFFER_WORDS, _search_terms

    q = (query or "").strip()
    if len(q) < 2:
        return []
    repo = OracleItemMasterProductRepository(session)
    terms = _search_terms(q) or [q]
    found: dict[str, ProductOut] = {}
    if any(term in _OFFER_WORDS for term in terms) or any(word in q.lower() for word in _OFFER_WORDS):
        for item in repo.list_offers(limit=limit):
            code = str(item.get("itemcode") or "")
            if code and code not in found:
                found[code] = ProductOut(**item)
    for term in terms:
        if term in _OFFER_WORDS:
            continue
        for item in repo.search(term, limit=limit):
            code = str(item.get("itemcode") or "")
            if code and code not in found:
                found[code] = ProductOut(**item)
        if len(found) >= limit:
            break
    return list(found.values())[:limit]


def _extract_query(text: str) -> str:
    from app.services.cart_service import _search_terms

    terms = _search_terms(text)
    return " ".join(terms[:5]) or (text or "").strip()


def _guess_intent(text: str) -> str:
    value = (text or "").lower()
    if re.search(r"\b(hi|hello|hey|hlo|salam|good morning|good evening)\b", value):
        return "greeting"
    if re.search(r"\b(deliver|delivery|shipping|location|doha|qatar|address)\b", value):
        return "delivery"
    if re.search(r"\b(pay|payment|cash|card|tap|transfer)\b", value):
        return "payment"
    if re.search(r"\b(order|bill|track|status)\b", value):
        return "order"
    if any(word in value for word in PRODUCT_HINTS):
        return "product"
    return "other"


def plan_agent_turn(session: Session, conversation_id: int, latest_message: str | None) -> AgentTurn:
    settings = get_settings()
    conversation = session.get(Conversation, conversation_id)
    if not conversation:
        return AgentTurn(reply="Conversation not found.")
    customer = session.get(Customer, conversation.customer_id)
    history = (
        session.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(12)
        .all()
    )
    history = list(reversed(history))
    latest = latest_message or next((row.message_text for row in reversed(history) if row.message_text), "")
    intent = _guess_intent(latest)
    search_query = _extract_query(latest)
    products = _search_products(session, search_query) if search_query else []

    orders = (
        session.query(Order)
        .filter(Order.customer_id == conversation.customer_id)
        .order_by(Order.order_date.desc())
        .limit(5)
        .all()
    )
    company = _setting(session, "company_name", settings.company_name)
    currency = _setting(session, "company_currency", settings.company_currency)
    agent_name = _setting(session, "ai_agent_name", "MamaHub")
    transcript = "\n".join(
        f"{row.sender_type}: {row.message_text or '[' + row.message_type + ']'}" for row in history
    )
    product_lines = "\n".join(
        f"{item.itemname} — {currency} {item.retailprice:.2f} (stock {item.currentstock:g})"
        for item in products
    ) or "No matching products found."
    order_lines = "\n".join(
        f"{order.order_number} {order.order_status} {currency} {float(order.total_amount):.2f}"
        for order in orders
    ) or "No previous WhatsApp orders."
    ad_line = ""
    if conversation.ad_headline or conversation.ad_body:
        ad_line = f"Facebook ad they clicked: {conversation.ad_headline or ''} {conversation.ad_body or ''}".strip()

    fallback = _fallback_suggestion(latest, products, currency, intent)
    planned = AgentTurn(
        reply=fallback,
        products=products,
        send_products=bool(products) and intent in {"product", "price", "stock", "other"},
        intent=intent,
    )
    if not settings.openai_api_key:
        return planned

    prompt = f"""You are {agent_name}, a real sales person at {company}, a toy shop in Qatar.
Reply on WhatsApp like a helpful human: short, warm, natural English. Never say you are an AI.
Never invent stock or prices. Use {currency} only. Do not use labels like AGENT:.
If they greet, greet back and ask what toy they need.
If they ask products/price/stock and matches exist, mention 2-3 options with price and ask which they want.
If they ask about offers, deals, or "what do you offer", use the website Offers list and mention sale prices.
If they came from a Facebook ad, you already know the product they saw — mention it naturally.
If delivery: we deliver across Qatar, ask for area/location.
If payment: cash on delivery, card, and Tap.
If nothing matches, ask for age, brand, or a clearer product name.

Return JSON only:
{{"reply":"...","search_query":"...","send_products":true,"intent":"product"}}

Customer: {customer.customer_name if customer else conversation.whatsapp_number}
Latest request: {latest}

Conversation:
{transcript}

Matching products:
{product_lines}

Order history:
{order_lines}

{ad_line}
"""
    try:
        client = OpenAI(api_key=settings.openai_api_key)
        response = client.chat.completions.create(
            model=_setting(session, "ai_model", settings.openai_model) or settings.openai_model,
            messages=[
                {"role": "system", "content": "You are a WhatsApp sales agent. Reply as JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.5,
            max_tokens=400,
            response_format={"type": "json_object"},
        )
        raw = (response.choices[0].message.content or "").strip()
        data = json.loads(raw) if raw else {}
        query = str(data.get("search_query") or search_query).strip()
        if query and query != search_query:
            extra = _search_products(session, query)
            if extra:
                products = extra
        planned.reply = _clean_reply(str(data.get("reply") or fallback))
        planned.products = products
        planned.send_products = bool(data.get("send_products")) and bool(products)
        planned.intent = str(data.get("intent") or intent)
    except Exception:
        logger.exception("AI agent plan failed")
        planned.reply = fallback
    return planned


def suggest_reply(session: Session, conversation_id: int, latest_message: str | None) -> SuggestReplyResponse:
    turn = plan_agent_turn(session, conversation_id, latest_message)
    return SuggestReplyResponse(
        suggestion=turn.reply,
        products=turn.products,
        auto_send=_truthy(_setting(session, "ai_auto_reply", "0")),
    )


def _fallback_suggestion(latest: str, products: List[ProductOut], currency: str, intent: str) -> str:
    if intent == "greeting":
        return "Hi! Welcome to MamaHub. What toy are you looking for today?"
    if intent == "delivery":
        return "Yes, we deliver across Qatar. Share your area or location and I will confirm delivery."
    if intent == "payment":
        return "We accept cash on delivery, card, and Tap. Would you like me to place an order?"
    if products:
        lines = "\n".join(f"{item.itemname} — {currency} {item.retailprice:.2f}" for item in products[:3])
        return f"Yes, we have these:\n\n{lines}\n\nWhich one would you like?"
    if latest:
        return "Thanks, I am checking that for you. Can you share the product name, brand, or age?"
    return "Hi! How can I help you today?"


def _should_auto_reply(session: Session, conversation_id: int) -> bool:
    if not _truthy(_setting(session, "ai_auto_reply", "0")):
        return False
    last_ai = (
        session.query(Message)
        .filter(Message.conversation_id == conversation_id, Message.sender_type == SenderType.AI.value)
        .order_by(Message.created_at.desc())
        .first()
    )
    if last_ai and last_ai.created_at and datetime.utcnow() - last_ai.created_at < timedelta(seconds=4):
        return False
    if _truthy(_setting(session, "ai_pause_when_human", "0")):
        recent_human = (
            session.query(Message)
            .filter(
                Message.conversation_id == conversation_id,
                Message.sender_type == SenderType.AGENT.value,
                Message.created_at >= datetime.utcnow() - timedelta(minutes=15),
            )
            .first()
        )
        if recent_human:
            return False
    return True


def _store_outbound(
    session: Session,
    conversation: Conversation,
    *,
    text: str,
    msg_type: str,
    media_url: Optional[str],
    wa_id: str,
    ok: bool,
    error: str = "",
) -> Message:
    now = datetime.utcnow()
    row = Message(
        conversation_id=conversation.conversation_id,
        whatsapp_message_id=wa_id or None,
        sender_type=SenderType.AI.value,
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


def auto_reply_conversation(session: Session, conversation_id: int, latest_message: str | None = None) -> None:
    if not _should_auto_reply(session, conversation_id):
        return
    conversation = session.get(Conversation, conversation_id)
    if not conversation:
        return
    turn = plan_agent_turn(session, conversation_id, latest_message)
    phone = normalize_whatsapp(conversation.whatsapp_number)
    ok, wa_id, _ = whatsapp_client.send_text_message(phone, turn.reply)
    _store_outbound(
        session,
        conversation,
        text=turn.reply,
        msg_type="text",
        media_url=None,
        wa_id="" if not ok else wa_id,
        ok=ok,
        error="" if ok else wa_id,
    )
    if not turn.send_products or not turn.products:
        return
    from app.schemas.crm import ProductPickIn
    from app.services import cart_service

    cart_service.send_picker(
        session,
        conversation,
        [
            ProductPickIn(
                itemcode=product.itemcode,
                itemname=product.itemname,
                retailprice=product.retailprice,
                offer_price=product.offer_price,
                image_url=product.image_url,
                currentstock=product.currentstock,
            )
            for product in turn.products[:10]
        ],
        image_limit=4,
        cards=False,
    )
    session.flush()


def run_auto_replies(session: Session, conversation_ids: List[int]) -> None:
    seen: set[int] = set()
    for conversation_id in conversation_ids:
        if conversation_id in seen:
            continue
        seen.add(conversation_id)
        try:
            auto_reply_conversation(session, conversation_id)
        except Exception:
            logger.exception("AI auto-reply failed for conversation %s", conversation_id)
