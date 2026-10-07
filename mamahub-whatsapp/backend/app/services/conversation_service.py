from __future__ import annotations

import json
import threading
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import AppError, NotFoundError
from app.core.logging import logger
from app.integrations.whatsapp.client import whatsapp_client
from app.repositories.oracle.customer_repository import OracleCrmCustomerRepository
from app.models.conversation import Conversation, ConversationAssignment, ConversationStar
from app.models.customer import Customer
from app.models.enums import ConversationStatus, MessageStatus, SenderType
from app.models.message import Message
from app.models.user import User
from app.schemas.crm import AdReferralOut, ConversationOut, MessageOut, SendMessageRequest
from app.services.audit_service import write_audit
from app.utils.phones import normalize_whatsapp


def _ad_referral_out(row: Conversation) -> Optional[AdReferralOut]:
    if not (row.ad_source_type or row.ad_headline or row.ad_image_url or row.ad_source_url):
        return None
    return AdReferralOut(
        source_type=row.ad_source_type,
        source_id=row.ad_source_id,
        headline=row.ad_headline,
        body=row.ad_body,
        image_url=row.ad_image_url,
        source_url=row.ad_source_url,
    )


def _referral_from_payload(payload: Any) -> Optional[AdReferralOut]:
    if not isinstance(payload, dict):
        return None
    raw = payload.get("referral")
    if not isinstance(raw, dict) or not raw:
        return None
    image = str(raw.get("image_url") or raw.get("thumbnail_url") or raw.get("media_url") or "").strip()
    return AdReferralOut(
        source_type=raw.get("source_type"),
        source_id=raw.get("source_id"),
        headline=raw.get("headline"),
        body=raw.get("body"),
        image_url=image or None,
        source_url=raw.get("source_url"),
    )


def _conversation_out(row: Conversation, starred_ids: Optional[set[int]] = None) -> ConversationOut:
    customer = row.customer
    assigned = row.assigned_user
    return ConversationOut(
        conversation_id=row.conversation_id,
        customer_id=row.customer_id,
        customer_name=customer.customer_name if customer else row.whatsapp_number,
        whatsapp_number=row.whatsapp_number,
        profile_image_url=customer.profile_image_url if customer else None,
        last_message_text=row.last_message_text,
        last_message_at=row.last_message_at,
        unread_count=int(row.unread_count or 0),
        assigned_user_id=row.assigned_user_id,
        assigned_user_name=assigned.full_name if assigned else None,
        status=row.status,
        is_starred=bool(starred_ids and row.conversation_id in starred_ids),
        ad_referral=_ad_referral_out(row),
    )


def _starred_ids(session: Session, user_id: Optional[int]) -> set[int]:
    if not user_id:
        return set()
    rows = session.query(ConversationStar.conversation_id).filter(ConversationStar.user_id == user_id).all()
    return {int(row[0]) for row in rows}


def list_conversations(
    session: Session,
    *,
    status: Optional[str] = None,
    unread: bool = False,
    assigned_to: Optional[int] = None,
    search: Optional[str] = None,
    starred: bool = False,
    user_id: Optional[int] = None,
) -> list[ConversationOut]:
    query = session.query(Conversation).options(
        joinedload(Conversation.customer),
        joinedload(Conversation.assigned_user),
    )
    if status and status.upper() != "ALL":
        query = query.filter(Conversation.status == status.upper())
    if unread:
        query = query.filter(Conversation.unread_count > 0)
    if assigned_to:
        query = query.filter(Conversation.assigned_user_id == assigned_to)
    if starred and user_id:
        query = query.join(ConversationStar, ConversationStar.conversation_id == Conversation.conversation_id).filter(
            ConversationStar.user_id == user_id
        )
    if search:
        like = f"%{search.strip()}%"
        query = query.join(Customer).filter(
            or_(
                Customer.customer_name.ilike(like),
                Conversation.whatsapp_number.like(like),
                Conversation.last_message_text.ilike(like),
            )
        )
    rows = query.order_by(Conversation.last_message_at.desc().nullslast()).all()
    starred_ids = _starred_ids(session, user_id)
    return [_conversation_out(row, starred_ids) for row in rows]


def get_conversation(session: Session, conversation_id: int) -> Conversation:
    row = session.get(Conversation, conversation_id)
    if not row:
        raise NotFoundError("Conversation not found")
    return row


def list_messages(session: Session, conversation_id: int) -> list[MessageOut]:
    get_conversation(session, conversation_id)
    rows = (
        session.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc(), Message.id.asc())
        .all()
    )
    return [_message_out(row) for row in rows]


def _payload_dict(row: Message) -> dict[str, Any]:
    if not row.payload_json:
        return {}
    try:
        data = json.loads(row.payload_json)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _reply_fields(payload: Any) -> tuple[Optional[int], Optional[str], bool]:
    if not isinstance(payload, dict):
        return None, None, False
    raw_id = payload.get("reply_to_id")
    try:
        reply_to_id = int(raw_id) if raw_id is not None else None
    except (TypeError, ValueError):
        reply_to_id = None
    reply_to_text = payload.get("reply_to_text")
    if not isinstance(reply_to_text, str) or not reply_to_text.strip():
        reply_to_text = None
    return reply_to_id, reply_to_text, bool(payload.get("edited"))


def _quoted_preview(row: Message) -> str:
    if row.status == MessageStatus.DELETED.value:
        return "This message was deleted"
    return (row.message_text or f"[{row.message_type}]")[:160]


def _latest_message(session: Session, conversation_id: int) -> Optional[Message]:
    return (
        session.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.id.desc())
        .first()
    )


def _message_out(row: Message) -> MessageOut:
    payload = None
    if row.payload_json:
        try:
            payload = json.loads(row.payload_json)
        except json.JSONDecodeError:
            payload = None
    reply_to_id, reply_to_text, edited = _reply_fields(payload)
    return MessageOut(
        id=row.id,
        conversation_id=row.conversation_id,
        whatsapp_message_id=row.whatsapp_message_id,
        sender_type=row.sender_type,
        sender_id=row.sender_id,
        message_type=row.message_type,
        message_text=row.message_text,
        media_url=row.media_url,
        latitude=row.latitude,
        longitude=row.longitude,
        status=row.status,
        sent_at=row.sent_at,
        delivered_at=row.delivered_at,
        read_at=row.read_at,
        created_at=row.created_at,
        payload=payload,
        error_message=row.error_message,
        referral=_referral_from_payload(payload),
        reply_to_id=reply_to_id,
        reply_to_text=reply_to_text,
        edited=edited,
    )


def start_conversation(session: Session, phone: str, name: Optional[str], user: User) -> ConversationOut:
    number = normalize_whatsapp(phone)
    if not number:
        raise AppError("Enter a valid WhatsApp number")
    customer = OracleCrmCustomerRepository(session).create_from_whatsapp(number, (name or "").strip() or number)
    conversation = (
        session.query(Conversation)
        .options(joinedload(Conversation.customer), joinedload(Conversation.assigned_user))
        .filter(
            or_(
                Conversation.customer_id == customer.customer_id,
                Conversation.whatsapp_number == number,
            )
        )
        .first()
    )
    if not conversation:
        conversation = Conversation(
            customer_id=customer.customer_id,
            whatsapp_number=number,
            status=ConversationStatus.OPEN.value,
        )
        session.add(conversation)
        session.flush()
        write_audit(
            session,
            action="conversation.start",
            user_id=user.user_id,
            entity_type="conversation",
            entity_id=str(conversation.conversation_id),
            details=number,
        )
        conversation = (
            session.query(Conversation)
            .options(joinedload(Conversation.customer), joinedload(Conversation.assigned_user))
            .filter(Conversation.conversation_id == conversation.conversation_id)
            .one()
        )
    return _conversation_out(conversation)


def mark_read(session: Session, conversation_id: int) -> Conversation:
    conversation = get_conversation(session, conversation_id)
    conversation.unread_count = 0
    conversation.updated_at = datetime.utcnow()
    latest = (
        session.query(Message)
        .filter(
            Message.conversation_id == conversation_id,
            Message.sender_type == SenderType.CUSTOMER.value,
            Message.whatsapp_message_id.isnot(None),
        )
        .order_by(Message.created_at.desc(), Message.id.desc())
        .first()
    )
    if latest and latest.whatsapp_message_id:
        wamid = latest.whatsapp_message_id

        def _mark() -> None:
            try:
                whatsapp_client.mark_message_read(wamid)
            except Exception:  # noqa: BLE001
                logger.exception("Could not mark WhatsApp message as read")

        threading.Thread(target=_mark, daemon=True).start()
    return conversation


def update_status(session: Session, conversation_id: int, status: str, user: User) -> Conversation:
    conversation = get_conversation(session, conversation_id)
    conversation.status = ConversationStatus(status.upper()).value
    conversation.updated_at = datetime.utcnow()
    write_audit(
        session,
        action="conversation.status",
        user_id=user.user_id,
        entity_type="conversation",
        entity_id=str(conversation_id),
        details=conversation.status,
    )
    return conversation


def assign_conversation(session: Session, conversation_id: int, user_id: Optional[int], actor: User) -> Conversation:
    conversation = get_conversation(session, conversation_id)
    conversation.assigned_user_id = user_id
    conversation.updated_at = datetime.utcnow()
    session.add(
        ConversationAssignment(
            conversation_id=conversation_id,
            user_id=user_id or actor.user_id,
            assigned_by=actor.user_id,
        )
    )
    write_audit(
        session,
        action="conversation.assign",
        user_id=actor.user_id,
        entity_type="conversation",
        entity_id=str(conversation_id),
        details=str(user_id),
    )
    return conversation


def toggle_star(session: Session, conversation_id: int, user: User, starred: Optional[bool] = None) -> bool:
    get_conversation(session, conversation_id)
    existing = (
        session.query(ConversationStar)
        .filter(ConversationStar.conversation_id == conversation_id, ConversationStar.user_id == user.user_id)
        .first()
    )
    want = (existing is None) if starred is None else bool(starred)
    if want and not existing:
        session.add(ConversationStar(conversation_id=conversation_id, user_id=user.user_id))
    elif not want and existing:
        session.delete(existing)
    write_audit(
        session,
        action="conversation.star",
        user_id=user.user_id,
        entity_type="conversation",
        entity_id=str(conversation_id),
        details="on" if want else "off",
    )
    return want


def send_outbound(session: Session, conversation_id: int, payload: SendMessageRequest, user: User) -> MessageOut:
    conversation = get_conversation(session, conversation_id)
    to_phone = normalize_whatsapp(conversation.whatsapp_number)
    ok = False
    wa_id = ""
    error = ""
    text = payload.text or payload.caption or payload.product_text or ""
    msg_type = payload.message_type
    quoted = None
    reply_wamid = None
    if payload.reply_to_id:
        quoted = (
            session.query(Message)
            .filter(Message.id == payload.reply_to_id, Message.conversation_id == conversation_id)
            .first()
        )
        if quoted:
            reply_wamid = quoted.whatsapp_message_id

    if msg_type == "template" and payload.template_name:
        ok, wa_id, _ = whatsapp_client.send_template_message(
            to_phone, payload.template_name, payload.language, payload.template_params
        )
        text = text or f"Template: {payload.template_name}"
    elif msg_type == "image" and payload.media_url:
        ok, wa_id, _ = whatsapp_client.send_image_message(to_phone, payload.media_url, payload.caption or text)
    elif msg_type == "document" and payload.media_url:
        ok, wa_id, _ = whatsapp_client.send_document_message(to_phone, payload.media_url, caption=payload.caption)
    elif msg_type == "audio" and payload.media_url:
        ok, wa_id, _ = whatsapp_client.send_audio_message(to_phone, payload.media_url)
    elif msg_type == "location" and payload.latitude is not None and payload.longitude is not None:
        ok, wa_id, _ = whatsapp_client.send_location_message(
            to_phone,
            payload.latitude,
            payload.longitude,
            payload.location_name,
            payload.location_address,
        )
        text = text or payload.location_name or "Location"
    elif msg_type == "interactive" and payload.interactive:
        ok, wa_id, _ = whatsapp_client.send_interactive_message(to_phone, payload.interactive)
        text = text or "Interactive message"
    elif msg_type == "product":
        text = payload.product_text or text
        if payload.media_url:
            ok, wa_id, _ = whatsapp_client.send_image_message(to_phone, payload.media_url, text)
            msg_type = "image"
        else:
            ok, wa_id, _ = whatsapp_client.send_text_message(to_phone, text, reply_to_wamid=reply_wamid)
    else:
        ok, wa_id, _ = whatsapp_client.send_text_message(to_phone, text, reply_to_wamid=reply_wamid)
        msg_type = "text"

    if not ok:
        error = wa_id
        wa_id = ""

    stored = payload.model_dump()
    if quoted:
        stored["reply_to_id"] = quoted.id
        stored["reply_to_text"] = _quoted_preview(quoted)

    now = datetime.utcnow()
    row = Message(
        conversation_id=conversation_id,
        whatsapp_message_id=wa_id or None,
        sender_type=SenderType.AGENT.value,
        sender_id=user.user_id,
        message_type=msg_type,
        message_text=text,
        media_url=payload.media_url,
        latitude=str(payload.latitude) if payload.latitude is not None else None,
        longitude=str(payload.longitude) if payload.longitude is not None else None,
        payload_json=json.dumps(stored, default=str),
        status=MessageStatus.SENT.value if ok else MessageStatus.FAILED.value,
        error_message=error or None,
        sent_at=now if ok else None,
        created_at=now,
    )
    session.add(row)
    conversation.last_message_at = now
    conversation.last_message_text = (text or f"[{msg_type}]")[:480]
    conversation.unread_count = 0
    if conversation.status in (ConversationStatus.RESOLVED.value, ConversationStatus.CLOSED.value):
        conversation.status = ConversationStatus.OPEN.value
    conversation.updated_at = now
    write_audit(
        session,
        action="message.sent",
        user_id=user.user_id,
        entity_type="conversation",
        entity_id=str(conversation_id),
        details=msg_type if ok else f"failed:{error}",
    )
    session.flush()
    return _message_out(row)


def edit_outbound(session: Session, conversation_id: int, message_id: int, text: str, user: User) -> MessageOut:
    conversation = get_conversation(session, conversation_id)
    row = (
        session.query(Message)
        .filter(Message.id == message_id, Message.conversation_id == conversation_id)
        .first()
    )
    if not row:
        raise NotFoundError("Message not found")
    if row.status == MessageStatus.DELETED.value:
        raise AppError("This message was deleted")
    if row.sender_type == SenderType.CUSTOMER.value:
        raise AppError("You can only edit your own messages")
    if row.message_type != "text":
        raise AppError("Only text messages can be edited")
    body = (text or "").strip()
    if not body:
        raise AppError("Enter a message")
    extra = _payload_dict(row)
    to_phone = normalize_whatsapp(conversation.whatsapp_number)
    previous_wamid = row.whatsapp_message_id
    if previous_wamid:
        whatsapp_client.revoke_message(previous_wamid, to_phone)
    ok, wa_id, _ = whatsapp_client.send_text_message(to_phone, body)
    if not ok:
        raise AppError(wa_id or "WhatsApp could not send the edited message.")
    extra["edited"] = True
    if previous_wamid:
        extra["replaced_wamid"] = previous_wamid
    if wa_id and wa_id != "sent":
        row.whatsapp_message_id = wa_id
    row.status = MessageStatus.SENT.value
    row.sent_at = datetime.utcnow()
    row.error_message = None
    row.message_text = body
    row.payload_json = json.dumps(extra, default=str)
    latest = _latest_message(session, conversation_id)
    if latest and latest.id == row.id:
        conversation.last_message_text = body[:480]
    conversation.updated_at = datetime.utcnow()
    write_audit(
        session,
        action="message.edited",
        user_id=user.user_id,
        entity_type="conversation",
        entity_id=str(conversation_id),
        details=str(message_id),
    )
    session.flush()
    return _message_out(row)


def delete_outbound(session: Session, conversation_id: int, message_id: int, user: User) -> MessageOut:
    conversation = get_conversation(session, conversation_id)
    row = (
        session.query(Message)
        .filter(Message.id == message_id, Message.conversation_id == conversation_id)
        .first()
    )
    if not row:
        raise NotFoundError("Message not found")
    if row.status == MessageStatus.DELETED.value:
        return _message_out(row)
    mine = row.sender_type != SenderType.CUSTOMER.value
    if mine and row.whatsapp_message_id:
        ok, err, _ = whatsapp_client.delete_message(row.whatsapp_message_id)
        if not ok:
            raise AppError(err or "WhatsApp could not delete this message.")
    extra = _payload_dict(row)
    extra["deleted"] = True
    extra["deleted_text"] = row.message_text
    row.status = MessageStatus.DELETED.value
    row.message_text = None
    latest = _latest_message(session, conversation_id)
    if latest and latest.id == row.id:
        conversation.last_message_text = "This message was deleted"
    conversation.updated_at = datetime.utcnow()
    write_audit(
        session,
        action="message.deleted",
        user_id=user.user_id,
        entity_type="conversation",
        entity_id=str(conversation_id),
        details=str(message_id),
    )
    session.flush()
    return _message_out(row)
