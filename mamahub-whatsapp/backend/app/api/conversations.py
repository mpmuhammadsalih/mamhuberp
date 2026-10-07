from __future__ import annotations

from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import require_permission
from app.core.permissions import Permission
from app.database.session import get_db
from app.models.user import User
from app.schemas.crm import (
    AssignRequest,
    CartOut,
    CartPut,
    ConversationOut,
    EditMessageRequest,
    MessageOut,
    SendMessageRequest,
    SendPickerRequest,
    StarRequest,
    StartConversationRequest,
    StatusUpdateRequest,
)
from app.services import cart_service
from app.services import conversation_service as svc
from app.utils.realtime import manager

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("", response_model=List[ConversationOut])
def list_conversations(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(Permission.CHATS_MANAGE))],
    status: Optional[str] = None,
    unread: bool = False,
    assigned_to_me: bool = False,
    starred: bool = False,
    search: Optional[str] = None,
) -> List[ConversationOut]:
    assigned = user.user_id if assigned_to_me else None
    return svc.list_conversations(
        db,
        status=status,
        unread=unread,
        assigned_to=assigned,
        search=search,
        starred=starred,
        user_id=user.user_id,
    )


@router.post("", response_model=ConversationOut)
def start_conversation(
    payload: StartConversationRequest,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(Permission.CHATS_MANAGE))],
) -> ConversationOut:
    return svc.start_conversation(db, payload.phone, payload.name, user)


@router.get("/{conversation_id}", response_model=ConversationOut)
def get_conversation(
    conversation_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(Permission.CHATS_MANAGE))],
) -> ConversationOut:
    rows = svc.list_conversations(db, user_id=user.user_id)
    match = next((row for row in rows if row.conversation_id == conversation_id), None)
    if not match:
        conversation = svc.get_conversation(db, conversation_id)
        return svc._conversation_out(conversation, svc._starred_ids(db, user.user_id))
    return match


@router.get("/{conversation_id}/messages", response_model=List[MessageOut])
def get_messages(
    conversation_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.CHATS_MANAGE))],
) -> List[MessageOut]:
    svc.mark_read(db, conversation_id)
    return svc.list_messages(db, conversation_id)


@router.post("/{conversation_id}/messages", response_model=MessageOut)
async def send_message(
    conversation_id: int,
    payload: SendMessageRequest,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(Permission.CHATS_MANAGE))],
) -> MessageOut:
    message = svc.send_outbound(db, conversation_id, payload, user)
    await manager.broadcast("message.created", message.model_dump(mode="json"))
    return message


@router.patch("/{conversation_id}/messages/{message_id}", response_model=MessageOut)
async def edit_message(
    conversation_id: int,
    message_id: int,
    payload: EditMessageRequest,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(Permission.CHATS_MANAGE))],
) -> MessageOut:
    message = svc.edit_outbound(db, conversation_id, message_id, payload.text, user)
    await manager.broadcast("message.updated", message.model_dump(mode="json"))
    return message


@router.delete("/{conversation_id}/messages/{message_id}", response_model=MessageOut)
async def delete_message(
    conversation_id: int,
    message_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(Permission.CHATS_MANAGE))],
) -> MessageOut:
    message = svc.delete_outbound(db, conversation_id, message_id, user)
    await manager.broadcast("message.updated", message.model_dump(mode="json"))
    return message


@router.patch("/{conversation_id}/status", response_model=ConversationOut)
def patch_status(
    conversation_id: int,
    payload: StatusUpdateRequest,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(Permission.CHATS_MANAGE))],
) -> ConversationOut:
    svc.update_status(db, conversation_id, payload.status, user)
    return get_conversation(conversation_id, db, user)


@router.post("/{conversation_id}/assign", response_model=ConversationOut)
def assign(
    conversation_id: int,
    payload: AssignRequest,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(Permission.CHATS_MANAGE))],
) -> ConversationOut:
    svc.assign_conversation(db, conversation_id, payload.user_id, user)
    return get_conversation(conversation_id, db, user)


@router.post("/{conversation_id}/star", response_model=ConversationOut)
def star_conversation(
    conversation_id: int,
    payload: StarRequest,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(Permission.CHATS_MANAGE))],
) -> ConversationOut:
    svc.toggle_star(db, conversation_id, user, payload.starred)
    return get_conversation(conversation_id, db, user)


@router.post("/{conversation_id}/upload")
async def upload_media(
    conversation_id: int,
    _: Annotated[User, Depends(require_permission(Permission.CHATS_MANAGE))],
    file: UploadFile = File(...),
) -> dict[str, str]:
    settings = get_settings()
    suffix = (file.filename or "upload").replace(" ", "_")
    path = settings.upload_path / f"{conversation_id}_{suffix}"
    path.write_bytes(await file.read())
    return {"url": f"/api/media/{path.name}", "filename": path.name}


@router.get("/{conversation_id}/cart", response_model=CartOut)
def get_cart(
    conversation_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.CHATS_MANAGE))],
) -> CartOut:
    svc.get_conversation(db, conversation_id)
    return cart_service.cart_out(db, conversation_id)


@router.put("/{conversation_id}/cart", response_model=CartOut)
def put_cart(
    conversation_id: int,
    payload: CartPut,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.CHATS_MANAGE))],
) -> CartOut:
    svc.get_conversation(db, conversation_id)
    return cart_service.replace_cart(db, conversation_id, payload.items)


@router.delete("/{conversation_id}/cart", response_model=CartOut)
def delete_cart(
    conversation_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.CHATS_MANAGE))],
) -> CartOut:
    svc.get_conversation(db, conversation_id)
    return cart_service.clear_cart(db, conversation_id)


@router.post("/{conversation_id}/cart/send-picker", response_model=CartOut)
async def send_product_picker(
    conversation_id: int,
    payload: SendPickerRequest,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(Permission.CHATS_MANAGE))],
) -> CartOut:
    conversation = svc.get_conversation(db, conversation_id)
    if not payload.products:
        raise HTTPException(status_code=400, detail="Select at least one product")
    cart_service.send_picker(db, conversation, payload.products, images_only=payload.images_only)
    await manager.broadcast("message.created", {"conversation_id": conversation_id, "user_id": user.user_id})
    return cart_service.cart_out(db, conversation_id)
