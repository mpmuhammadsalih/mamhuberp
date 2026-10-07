"""Send Web Push alerts for inbound WhatsApp chats."""
from __future__ import annotations

import json
from typing import Iterable

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import logger
from app.models.conversation import Conversation
from app.models.push import PushSubscription


def _preview(session: Session, conversation_id: int) -> tuple[str, str]:
    row = session.get(Conversation, conversation_id)
    if not row:
        return "MamaHub WhatsApp", "New WhatsApp message"
    name = ""
    if row.customer is not None:
        name = (row.customer.customer_name or "").strip()
    title = name or row.whatsapp_number or "New chat"
    body = (row.last_message_text or "New WhatsApp message").strip()[:140]
    return title, body or "New WhatsApp message"


def send_push(session: Session, payload: dict, user_id: int | None = None) -> int:
    settings = get_settings()
    if not settings.vapid_private_key or not settings.vapid_public_key:
        logger.warning("Phone push skipped: VAPID keys missing")
        return 0
    query = session.query(PushSubscription)
    if user_id:
        query = query.filter(PushSubscription.user_id == user_id)
    subs = query.all()
    if not subs:
        logger.info("Phone push skipped: no device subscriptions")
        return 0
    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        logger.warning("pywebpush is not installed — phone alerts skipped")
        return 0

    claims = {"sub": settings.vapid_mailto or "mailto:admin@mamahub.store"}
    data = json.dumps(payload)
    stale: list[PushSubscription] = []
    sent = 0
    for sub in subs:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                },
                data=data,
                vapid_private_key=settings.vapid_private_key,
                vapid_claims=claims,
                ttl=86400,
                headers={"Urgency": "high"},
            )
            sent += 1
        except WebPushException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in {404, 410}:
                stale.append(sub)
            else:
                logger.warning("Web push failed for subscription %s: %s", sub.subscription_id, exc)
        except Exception:
            logger.exception("Web push failed for subscription %s", sub.subscription_id)
    for row in stale:
        session.delete(row)
    if stale:
        session.commit()
    logger.info("Phone push sent to %s device(s)", sent)
    return sent


def notify_inbound(session: Session, conversation_ids: Iterable[int]) -> None:
    ids = [int(item) for item in conversation_ids if int(item or 0) > 0]
    if not ids:
        return
    for conversation_id in ids:
        title, body = _preview(session, conversation_id)
        send_push(
            session,
            {
                "title": title,
                "body": body,
                "conversation_id": conversation_id,
                "url": f"/inbox?c={conversation_id}",
            },
        )
