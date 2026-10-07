from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import get_current_user
from app.database.session import get_db
from app.models.push import PushSubscription
from app.models.user import User
from app.services.push_service import send_push

router = APIRouter(prefix="/api/push", tags=["push"])


class PushSubscribeIn(BaseModel):
    endpoint: str = Field(min_length=8, max_length=2000)
    keys: dict[str, str]


@router.get("/public-key")
def public_key(_: Annotated[User, Depends(get_current_user)]) -> dict[str, str]:
    return {"public_key": get_settings().vapid_public_key}


@router.post("/subscribe")
def subscribe(
    payload: PushSubscribeIn,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    p256dh = (payload.keys.get("p256dh") or "").strip()
    auth = (payload.keys.get("auth") or "").strip()
    if not p256dh or not auth:
        return {"ok": False}
    row = db.query(PushSubscription).filter(PushSubscription.endpoint == payload.endpoint).first()
    if row:
        row.user_id = user.user_id
        row.p256dh = p256dh
        row.auth = auth
        row.user_agent = (request.headers.get("user-agent") or "")[:400]
    else:
        db.add(
            PushSubscription(
                user_id=user.user_id,
                endpoint=payload.endpoint,
                p256dh=p256dh,
                auth=auth,
                user_agent=(request.headers.get("user-agent") or "")[:400],
            )
        )
    db.commit()
    return {"ok": True}


@router.post("/renew")
def renew(payload: dict[str, Any], db: Annotated[Session, Depends(get_db)]) -> dict[str, bool]:
    old_endpoint = str(payload.get("old_endpoint") or "").strip()
    endpoint = str(payload.get("endpoint") or "").strip()
    keys = payload.get("keys") if isinstance(payload.get("keys"), dict) else {}
    p256dh = str(keys.get("p256dh") or "").strip()
    auth = str(keys.get("auth") or "").strip()
    if not endpoint or not p256dh or not auth:
        return {"ok": False}
    row = None
    if old_endpoint:
        row = db.query(PushSubscription).filter(PushSubscription.endpoint == old_endpoint).first()
    if not row:
        row = db.query(PushSubscription).filter(PushSubscription.endpoint == endpoint).first()
    if not row:
        return {"ok": False}
    row.endpoint = endpoint
    row.p256dh = p256dh
    row.auth = auth
    db.commit()
    return {"ok": True}


@router.post("/test")
def test_push(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    sent = send_push(
        db,
        {
            "title": "MamaHub WhatsApp",
            "body": "Alerts are on. You will get this when a customer writes.",
            "url": "/inbox",
        },
        user_id=user.user_id,
    )
    return {"ok": sent > 0, "sent": sent}


@router.delete("/subscribe")
def unsubscribe(
    payload: PushSubscribeIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, bool]:
    row = (
        db.query(PushSubscription)
        .filter(PushSubscription.endpoint == payload.endpoint, PushSubscription.user_id == user.user_id)
        .first()
    )
    if row:
        db.delete(row)
        db.commit()
    return {"ok": True}
