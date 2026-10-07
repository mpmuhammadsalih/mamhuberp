"""Background processing for incoming WhatsApp Cloud API events."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx
from sqlalchemy.orm import Session

from app.core.logging import logger
from app.integrations.whatsapp.client import whatsapp_client
from app.models.conversation import Conversation
from app.models.enums import ConversationStatus, MessageStatus, SenderType
from app.models.message import Message, MessageAttachment
from app.repositories.oracle.customer_repository import OracleCrmCustomerRepository
from app.utils.phones import normalize_whatsapp


def _ts(value: Any) -> datetime:
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).replace(tzinfo=None)
    except (TypeError, ValueError):
        return datetime.utcnow()


def _preview(message_type: str, text: Optional[str]) -> str:
    if text:
        return text[:480]
    return f"[{message_type}]"


def _extract_text(message: Dict[str, Any]) -> Optional[str]:
    msg_type = message.get("type")
    if msg_type == "text":
        return (message.get("text") or {}).get("body")
    if msg_type == "button":
        return (message.get("button") or {}).get("text")
    if msg_type == "interactive":
        interactive = message.get("interactive") or {}
        if interactive.get("type") == "button_reply":
            return (interactive.get("button_reply") or {}).get("title")
        if interactive.get("type") == "list_reply":
            return (interactive.get("list_reply") or {}).get("title")
    if msg_type in ("image", "video", "document", "audio"):
        media = message.get(msg_type) or {}
        return media.get("caption")
    if msg_type == "location":
        loc = message.get("location") or {}
        return loc.get("name") or loc.get("address") or "Location shared"
    if msg_type == "contacts":
        contacts = message.get("contacts") or []
        if contacts:
            name = ((contacts[0].get("name") or {}).get("formatted_name"))
            return name or "Contact shared"
    return None


def _referral(message: Dict[str, Any]) -> Dict[str, Any]:
    raw = message.get("referral")
    return raw if isinstance(raw, dict) else {}


def _referral_image_url(referral: Dict[str, Any]) -> str:
    return str(
        referral.get("image_url")
        or referral.get("thumbnail_url")
        or referral.get("media_url")
        or ""
    ).strip()


def _store_remote_image(url: str, stem: str) -> Optional[str]:
    if not url.startswith("http"):
        return None
    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            response = client.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
                },
            )
            if not response.is_success or not response.content:
                return None
            mime = (response.headers.get("content-type") or "image/jpeg").split(";")[0]
            ext = mime.split("/")[-1] if "/" in mime else "jpg"
            if ext in {"jpeg", "pjpeg"}:
                ext = "jpg"
            if ext not in {"jpg", "png", "webp", "gif"}:
                ext = "jpg"
            safe = re.sub(r"[^A-Za-z0-9_-]", "", stem)[:80] or "ad"
            from app.core.config import get_settings

            filename = f"ad_{safe}.{ext}"
            path = get_settings().upload_path / filename
            path.write_bytes(response.content)
            return f"/api/media/{filename}"
    except Exception:  # noqa: BLE001
        logger.exception("Failed to persist Facebook ad image")
        return None


def _apply_ad_referral(session: Session, conversation: Conversation, message: Dict[str, Any]) -> None:
    referral = _referral(message)
    if not referral:
        return
    source_type = str(referral.get("source_type") or "ad")[:20]
    source_id = str(referral.get("source_id") or "")[:80]
    headline = str(referral.get("headline") or "")[:240]
    body = str(referral.get("body") or "")[:500]
    source_url = str(referral.get("source_url") or "")[:500]
    remote = _referral_image_url(referral)
    local = None
    if remote:
        local = _store_remote_image(remote, f"{conversation.conversation_id}_{source_id or 'fb'}")
    conversation.ad_source_type = source_type or conversation.ad_source_type
    conversation.ad_source_id = source_id or conversation.ad_source_id
    conversation.ad_headline = headline or conversation.ad_headline
    conversation.ad_body = body or conversation.ad_body
    conversation.ad_source_url = source_url[:2000] if source_url else conversation.ad_source_url
    conversation.ad_image_url = local or conversation.ad_image_url or (remote[:2000] if remote else None)
    logger.info(
        "Stored Facebook ad referral for conversation %s source=%s image=%s",
        conversation.conversation_id,
        source_type,
        bool(conversation.ad_image_url),
    )
    session.flush()


def backfill_ad_referrals(session: Session) -> int:
    rows = (
        session.query(Message)
        .filter(Message.payload_json.isnot(None), Message.payload_json.like("%referral%"))
        .order_by(Message.id.asc())
        .all()
    )
    updated = 0
    for row in rows:
        conversation = session.get(Conversation, row.conversation_id)
        if not conversation or (conversation.ad_image_url or "").startswith("/api/media/"):
            continue
        try:
            payload = json.loads(row.payload_json or "{}")
        except json.JSONDecodeError:
            continue
        if not _referral(payload):
            continue
        before = conversation.ad_image_url
        _apply_ad_referral(session, conversation, payload)
        if conversation.ad_headline or conversation.ad_image_url != before:
            updated += 1
    return updated


def _payload_dict(row: Message) -> Dict[str, Any]:
    if not row.payload_json:
        return {}
    try:
        data = json.loads(row.payload_json)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _touch_last_message(session: Session, row: Message, text: Optional[str], msg_type: str) -> None:
    conversation = session.get(Conversation, row.conversation_id)
    if not conversation:
        return
    latest = (
        session.query(Message)
        .filter(Message.conversation_id == row.conversation_id)
        .order_by(Message.id.desc())
        .first()
    )
    if latest and latest.id == row.id:
        conversation.last_message_text = _preview(msg_type, text)
        conversation.last_message_at = datetime.utcnow()
    conversation.updated_at = datetime.utcnow()


def _apply_incoming_edit(session: Session, message: Dict[str, Any]) -> Optional[Message]:
    edit = message.get("edit") if isinstance(message.get("edit"), dict) else {}
    original_wamid = str(edit.get("original_message_id") or "")
    inner = edit.get("message") if isinstance(edit.get("message"), dict) else {}
    if not original_wamid:
        return None
    row = session.query(Message).filter(Message.whatsapp_message_id == original_wamid).first()
    if not row:
        return None
    new_text = _extract_text(inner) if inner else None
    extra = _payload_dict(row)
    extra["edited"] = True
    extra["edit_event"] = message
    if new_text:
        row.message_text = new_text
    if inner.get("type"):
        row.message_type = str(inner.get("type"))
    row.payload_json = json.dumps(extra, default=str)
    _touch_last_message(session, row, row.message_text, row.message_type)
    session.flush()
    return row


def _apply_incoming_revoke(session: Session, message: Dict[str, Any]) -> Optional[Message]:
    revoke = message.get("revoke") if isinstance(message.get("revoke"), dict) else {}
    original_wamid = str(revoke.get("original_message_id") or message.get("id") or "")
    if not original_wamid:
        return None
    row = session.query(Message).filter(Message.whatsapp_message_id == original_wamid).first()
    if not row:
        return None
    extra = _payload_dict(row)
    extra["deleted"] = True
    extra["deleted_text"] = row.message_text
    row.status = MessageStatus.DELETED.value
    row.message_text = None
    row.payload_json = json.dumps(extra, default=str)
    _touch_last_message(session, row, "This message was deleted", "text")
    session.flush()
    return row


def process_webhook_payload(session: Session, payload: Dict[str, Any]) -> Tuple[int, List[int]]:
    processed = 0
    inbound: List[int] = []
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            contacts = {item.get("wa_id"): item for item in (value.get("contacts") or []) if item.get("wa_id")}
            for message in value.get("messages") or []:
                row = _store_incoming(session, message, contacts)
                processed += 1
                if row and row.conversation_id:
                    inbound.append(int(row.conversation_id))
            for status in value.get("statuses") or []:
                _update_status(session, status)
                processed += 1
    session.flush()
    return processed, inbound


def _store_incoming(session: Session, message: Dict[str, Any], contacts: Dict[str, Any]) -> Optional[Message]:
    wa_id = normalize_whatsapp(str(message.get("from") or ""))
    wamid = str(message.get("id") or "")
    if not wa_id:
        return None
    existing = session.query(Message).filter(Message.whatsapp_message_id == wamid).first() if wamid else None
    if existing:
        return existing

    msg_type = str(message.get("type") or "unknown")
    if msg_type == "edit":
        return _apply_incoming_edit(session, message)
    if msg_type in ("revoke", "deleted"):
        return _apply_incoming_revoke(session, message)

    contact = contacts.get(message.get("from")) or contacts.get(wa_id) or {}
    profile_name = ((contact.get("profile") or {}).get("name")) or wa_id
    repo = OracleCrmCustomerRepository(session)
    customer = repo.create_from_whatsapp(wa_id, profile_name)

    conversation = (
        session.query(Conversation)
        .filter(Conversation.customer_id == customer.customer_id)
        .first()
    )
    if not conversation:
        conversation = Conversation(
            customer_id=customer.customer_id,
            whatsapp_number=wa_id,
            status=ConversationStatus.OPEN.value,
        )
        session.add(conversation)
        session.flush()

    text = _extract_text(message)
    media = message.get(msg_type) if msg_type in ("image", "video", "audio", "document", "sticker") else {}
    loc = message.get("location") or {}
    created = _ts(message.get("timestamp"))
    stored = dict(message)
    ctx = message.get("context") if isinstance(message.get("context"), dict) else {}
    quoted_wamid = str((ctx or {}).get("id") or "")
    if quoted_wamid:
        quoted = session.query(Message).filter(Message.whatsapp_message_id == quoted_wamid).first()
        if quoted:
            stored["reply_to_id"] = quoted.id
            preview = quoted.message_text or f"[{quoted.message_type}]"
            if quoted.status == MessageStatus.DELETED.value:
                preview = "This message was deleted"
            stored["reply_to_text"] = preview[:160]

    row = Message(
        conversation_id=conversation.conversation_id,
        whatsapp_message_id=wamid or None,
        sender_type=SenderType.CUSTOMER.value,
        sender_id=customer.customer_id,
        message_type=msg_type,
        message_text=text,
        media_url=(media or {}).get("id"),
        media_mime_type=(media or {}).get("mime_type"),
        latitude=str(loc.get("latitude")) if loc.get("latitude") is not None else None,
        longitude=str(loc.get("longitude")) if loc.get("longitude") is not None else None,
        payload_json=json.dumps(stored, default=str),
        status=MessageStatus.RECEIVED.value,
        sent_at=created,
        created_at=created,
    )
    session.add(row)
    session.flush()
    _apply_ad_referral(session, conversation, message)

    if media and media.get("id"):
        session.add(
            MessageAttachment(
                message_id=row.id,
                media_id=media.get("id"),
                file_name=media.get("filename"),
                mime_type=media.get("mime_type"),
            )
        )
        _maybe_store_media(session, row, str(media.get("id")))

    conversation.last_message_at = created
    conversation.last_message_text = _preview(msg_type, text)
    conversation.unread_count = int(conversation.unread_count or 0) + 1
    if conversation.status in (ConversationStatus.RESOLVED.value, ConversationStatus.CLOSED.value):
        conversation.status = ConversationStatus.OPEN.value
    conversation.updated_at = datetime.utcnow()
    return row


def _maybe_store_media(session: Session, message: Message, media_id: str) -> None:
    content, mime = whatsapp_client.download_media(media_id)
    if not content:
        return
    from app.core.config import get_settings

    settings = get_settings()
    ext = "bin"
    if mime and "/" in mime:
        ext = mime.split("/")[-1].split(";")[0][:8]
    filename = f"{media_id}.{ext}"
    path = settings.upload_path / filename
    try:
        path.write_bytes(content)
        message.media_url = f"/api/media/{filename}"
        if message.attachments:
            message.attachments[0].file_url = message.media_url
    except Exception:  # noqa: BLE001
        logger.exception("Failed to persist WhatsApp media")


def _update_status(session: Session, status: Dict[str, Any]) -> None:
    wamid = str(status.get("id") or "")
    if not wamid:
        return
    row = session.query(Message).filter(Message.whatsapp_message_id == wamid).first()
    if not row:
        return
    state = str(status.get("status") or "").lower()
    when = _ts(status.get("timestamp"))
    if state == "sent" and row.status == MessageStatus.SENT.value:
        row.sent_at = row.sent_at or when
    elif state == "delivered":
        row.status = MessageStatus.DELIVERED.value
        row.delivered_at = when
    elif state == "read":
        row.status = MessageStatus.READ.value
        row.read_at = when
        row.delivered_at = row.delivered_at or when
    elif state == "failed":
        row.status = MessageStatus.FAILED.value
        errors = status.get("errors") or []
        if errors:
            row.error_message = str(errors[0].get("message") or errors[0])[:500]
