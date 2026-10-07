from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import get_current_user
from app.core.logging import logger
from app.database.session import get_db, get_session_factory
from app.integrations.whatsapp.client import whatsapp_client
from app.integrations.whatsapp.processor import process_webhook_payload
from app.models.user import User
from app.utils.realtime import manager

router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])
_last_webhook: dict[str, Any] = {}


def _verify_signature(raw_body: bytes, signature: str | None) -> bool:
    secret = get_settings().meta_app_secret
    if not secret:
        return True
    if not signature or not signature.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature.split("=", 1)[1], expected)


def _process_later(payload: dict[str, Any]) -> None:
    session = get_session_factory()()
    inbound: list[int] = []
    try:
        count, inbound = process_webhook_payload(session, payload)
        session.commit()
        logger.info("Processed %s WhatsApp webhook events", count)
    except Exception:
        session.rollback()
        logger.exception("WhatsApp webhook processing failed")
        raise
    try:
        if inbound:
            try:
                from app.services.push_service import notify_inbound

                logger.info("Sending phone push for conversations %s", inbound)
                notify_inbound(session, inbound)
            except Exception:
                logger.exception("Phone push alerts failed")
            import asyncio

            try:
                from app.services.push_service import _preview

                alerts = []
                for conversation_id in inbound:
                    title, body = _preview(session, conversation_id)
                    alerts.append(
                        {
                            "conversation_id": conversation_id,
                            "title": title,
                            "body": body,
                            "url": f"/inbox?c={conversation_id}",
                        }
                    )
                asyncio.run(
                    manager.broadcast(
                        "message.created",
                        {"conversation_ids": inbound, "alerts": alerts},
                    )
                )
            except Exception:
                logger.exception("Realtime chat broadcast failed")
            from app.services import cart_service
            from app.services.ai_service import run_auto_replies

            leftover: list[int] = []
            for conversation_id in inbound:
                try:
                    if cart_service.handle_inbound(session, conversation_id):
                        continue
                except Exception:
                    logger.exception("Cart reply failed for conversation %s", conversation_id)
                leftover.append(conversation_id)
            if leftover:
                run_auto_replies(session, leftover)
            session.commit()
    except Exception:
        session.rollback()
        logger.exception("AI auto-reply failed")
    finally:
        session.close()


@router.get("/webhook")
def verify_webhook(
    hub_mode: str = Query(default="", alias="hub.mode"),
    hub_verify_token: str = Query(default="", alias="hub.verify_token"),
    hub_challenge: str = Query(default="", alias="hub.challenge"),
) -> Response:
    settings = get_settings()
    if hub_mode == "subscribe" and hub_verify_token and hub_verify_token == settings.whatsapp_verify_token:
        return Response(content=hub_challenge, media_type="text/plain")
    raise HTTPException(status_code=403, detail="Webhook verification failed")


@router.post("/webhook")
async def receive_webhook(
    request: Request,
    background: BackgroundTasks,
    x_hub_signature_256: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    raw = await request.body()
    if not _verify_signature(raw, x_hub_signature_256):
        raise HTTPException(status_code=403, detail="Invalid webhook signature")
    try:
        payload = json.loads(raw.decode("utf-8") or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc
    message_count = 0
    status_count = 0
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            message_count += len(value.get("messages") or [])
            status_count += len(value.get("statuses") or [])
    _last_webhook.update(
        {
            "at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "object": payload.get("object"),
            "messages": message_count,
            "statuses": status_count,
        }
    )
    logger.info(
        "WhatsApp webhook POST object=%s messages=%s statuses=%s",
        payload.get("object"),
        message_count,
        status_count,
    )
    background.add_task(_process_later, payload)
    background.add_task(_notify, payload)
    return {"status": "accepted"}


async def _notify(payload: dict[str, Any]) -> None:
    await manager.broadcast("whatsapp.event", {"received": True, "object": payload.get("object")})


@router.get("/health")
def whatsapp_health(db: Annotated[Session, Depends(get_db)]) -> dict[str, Any]:
    settings = get_settings()
    profile = whatsapp_client.get_phone_profile()
    return {
        "configured": bool(settings.whatsapp_access_token and settings.whatsapp_phone_number_id),
        "phone_number_id_set": bool(settings.whatsapp_phone_number_id),
        "verify_token_set": bool(settings.whatsapp_verify_token),
        "display_phone_number": profile.get("display_phone_number") or "",
        "verified_name": profile.get("verified_name") or "",
        "last_webhook_at": _last_webhook.get("at"),
        "last_webhook_messages": _last_webhook.get("messages"),
        "db": "ok" if db else "missing",
    }


@router.get("/setup")
def whatsapp_setup(_: Annotated[User, Depends(get_current_user)]) -> dict[str, Any]:
    settings = get_settings()
    profile = whatsapp_client.get_phone_profile()
    return {
        "callback_url": "https://whatsapp.mamahub.store/api/whatsapp/webhook",
        "verify_token": settings.whatsapp_verify_token,
        "display_phone_number": profile.get("display_phone_number") or "",
        "verified_name": profile.get("verified_name") or "",
        "last_webhook_at": _last_webhook.get("at"),
        "last_webhook_messages": _last_webhook.get("messages") or 0,
        "inbound_ready": bool(_last_webhook.get("at")),
    }
