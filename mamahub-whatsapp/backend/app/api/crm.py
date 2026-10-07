from __future__ import annotations

from datetime import datetime
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import get_current_user, require_permission
from app.core.permissions import Permission
from app.database.session import get_db
from app.models.content import QuickReply, Setting, WhatsAppTemplate
from app.models.customer import Customer, CustomerNote
from app.models.message import Message
from app.models.user import User
from app.repositories.oracle.product_repository import OracleItemMasterProductRepository
from app.schemas.crm import (
    CustomerNoteIn,
    CustomerOut,
    CustomerUpdate,
    DashboardOut,
    OrderCreate,
    OrderOut,
    OrderUpdate,
    ProductOut,
    QuickReplyIn,
    QuickReplyOut,
    SuggestReplyRequest,
    SuggestReplyResponse,
    TemplateIn,
    TemplateOut,
)
from app.services import ai_service, customer_service, dashboard_service, order_service
from app.services.audit_service import write_audit

customers_router = APIRouter(prefix="/api/customers", tags=["customers"])
products_router = APIRouter(prefix="/api/products", tags=["products"])
orders_router = APIRouter(prefix="/api/orders", tags=["orders"])
replies_router = APIRouter(prefix="/api/quick-replies", tags=["quick-replies"])
templates_router = APIRouter(prefix="/api/templates", tags=["templates"])
ai_router = APIRouter(prefix="/api/ai", tags=["ai"])
dashboard_router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])
reports_router = APIRouter(prefix="/api/reports", tags=["reports"])
settings_router = APIRouter(prefix="/api/settings", tags=["settings"])


@customers_router.get("", response_model=List[CustomerOut])
def list_customers(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.CUSTOMERS_VIEW))],
    search: Optional[str] = None,
) -> List[CustomerOut]:
    query = db.query(Customer)
    if search:
        like = f"%{search}%"
        query = query.filter((Customer.customer_name.ilike(like)) | (Customer.whatsapp_number.like(like)))
    return [customer_service.to_out(db, row) for row in query.order_by(Customer.customer_name.asc()).all()]


@customers_router.get("/{customer_id}", response_model=CustomerOut)
def get_customer(
    customer_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.CUSTOMERS_VIEW))],
) -> CustomerOut:
    return customer_service.get_customer(db, customer_id)


@customers_router.put("/{customer_id}", response_model=CustomerOut)
def update_customer(
    customer_id: int,
    payload: CustomerUpdate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(Permission.CUSTOMERS_EDIT))],
) -> CustomerOut:
    return customer_service.update_customer(db, customer_id, payload, user)


@customers_router.post("/{customer_id}/photo", response_model=CustomerOut)
async def upload_customer_photo(
    customer_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(Permission.CUSTOMERS_EDIT))],
    file: UploadFile = File(...),
) -> CustomerOut:
    suffix = (file.filename or "photo.jpg").replace(" ", "_")
    name = f"customer_{customer_id}_{suffix}"
    path = get_settings().upload_path / name
    path.write_bytes(await file.read())
    return customer_service.set_profile_image(db, customer_id, f"/api/media/{name}", user)


@customers_router.get("/{customer_id}/notes")
def list_notes(
    customer_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.CUSTOMERS_VIEW))],
) -> list[dict]:
    rows = db.query(CustomerNote).filter(CustomerNote.customer_id == customer_id).order_by(CustomerNote.created_at.desc()).all()
    return [{"note_id": row.note_id, "note_text": row.note_text, "created_at": row.created_at} for row in rows]


@customers_router.post("/{customer_id}/notes")
def add_note(
    customer_id: int,
    payload: CustomerNoteIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(Permission.CUSTOMERS_EDIT))],
) -> dict[str, str]:
    customer_service.add_note(db, customer_id, payload.note_text, user)
    return {"status": "ok"}


@customers_router.put("/{customer_id}/notes/{note_id}")
def update_note(
    customer_id: int,
    note_id: int,
    payload: CustomerNoteIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(Permission.CUSTOMERS_EDIT))],
) -> dict[str, str]:
    customer_service.update_note(db, customer_id, note_id, payload.note_text, user)
    return {"status": "ok"}


@customers_router.delete("/{customer_id}/notes/{note_id}")
def delete_note(
    customer_id: int,
    note_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(Permission.CUSTOMERS_EDIT))],
) -> dict[str, str]:
    customer_service.delete_note(db, customer_id, note_id, user)
    return {"status": "ok"}


@customers_router.get("/{customer_id}/history")
def conversation_history(
    customer_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.CUSTOMERS_VIEW))],
) -> list[dict]:
    from app.models.conversation import Conversation

    conversation_ids = [row[0] for row in db.query(Conversation.conversation_id).filter(Conversation.customer_id == customer_id)]
    if not conversation_ids:
        return []
    rows = (
        db.query(Message)
        .filter(Message.conversation_id.in_(conversation_ids))
        .order_by(Message.created_at.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "id": row.id,
            "sender_type": row.sender_type,
            "message_type": row.message_type,
            "message_text": row.message_text,
            "created_at": row.created_at,
        }
        for row in rows
    ]


@products_router.get("/filters")
def product_filters(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.PRODUCTS_SEARCH))],
) -> dict:
    return OracleItemMasterProductRepository(db).list_filters()


@products_router.get("/search", response_model=List[ProductOut])
def search_products(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.PRODUCTS_SEARCH))],
    q: str = "",
    category: Optional[str] = None,
    brand: Optional[str] = None,
    in_stock: bool = False,
    offers: bool = False,
    collection: Optional[str] = None,
    age: Optional[str] = None,
    limit: int = 60,
) -> List[ProductOut]:
    repo = OracleItemMasterProductRepository(db)
    return [
        ProductOut(**item)
        for item in repo.search(
            q,
            limit=limit,
            category=category,
            brand=brand,
            in_stock=in_stock,
            offers=offers,
            collection=collection,
            age=age,
        )
    ]


@orders_router.get("", response_model=List[OrderOut])
def list_orders(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.ORDERS_VIEW))],
    customer_id: Optional[int] = None,
) -> List[OrderOut]:
    return order_service.list_orders(db, customer_id=customer_id)


@orders_router.post("", response_model=OrderOut)
def create_order(
    payload: OrderCreate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(Permission.ORDERS_CREATE))],
) -> OrderOut:
    return order_service.create_order(db, payload, user)


@orders_router.get("/{order_id}", response_model=OrderOut)
def get_order(
    order_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.ORDERS_VIEW))],
) -> OrderOut:
    return order_service.get_order(db, order_id)


@orders_router.put("/{order_id}", response_model=OrderOut)
def update_order(
    order_id: int,
    payload: OrderUpdate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(Permission.ORDERS_CREATE))],
) -> OrderOut:
    return order_service.update_order(db, order_id, payload, user)


@orders_router.post("/{order_id}/remove", response_model=OrderOut)
def remove_order(
    order_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(Permission.ORDERS_CREATE))],
) -> OrderOut:
    return order_service.remove_uninvoiced_order(db, order_id, user)


@orders_router.post("/{order_id}/sync-erp", response_model=OrderOut)
def sync_order_erp(
    order_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(Permission.ORDERS_CREATE))],
) -> OrderOut:
    return order_service.sync_order_to_erp(db, order_id, user)


def _reply_out(row: QuickReply) -> QuickReplyOut:
    return QuickReplyOut(
        reply_id=row.reply_id,
        shortcut=row.shortcut,
        title=row.title,
        body=row.body,
        is_active=bool(row.is_active),
    )


@replies_router.get("", response_model=List[QuickReplyOut])
def list_replies(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.CHATS_MANAGE))],
) -> List[QuickReplyOut]:
    return [_reply_out(row) for row in db.query(QuickReply).order_by(QuickReply.shortcut.asc()).all()]


@replies_router.post("", response_model=QuickReplyOut)
def create_reply(
    payload: QuickReplyIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(Permission.TEMPLATES_MANAGE))],
) -> QuickReplyOut:
    row = QuickReply(shortcut=payload.shortcut, title=payload.title, body=payload.body, is_active=1 if payload.is_active else 0)
    db.add(row)
    db.flush()
    write_audit(db, action="quick_reply.create", user_id=user.user_id, entity_id=str(row.reply_id))
    return _reply_out(row)


@replies_router.put("/{reply_id}", response_model=QuickReplyOut)
def update_reply(
    reply_id: int,
    payload: QuickReplyIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(Permission.TEMPLATES_MANAGE))],
) -> QuickReplyOut:
    row = db.get(QuickReply, reply_id)
    if not row:
        from app.core.exceptions import NotFoundError

        raise NotFoundError("Quick reply not found")
    row.shortcut = payload.shortcut
    row.title = payload.title
    row.body = payload.body
    row.is_active = 1 if payload.is_active else 0
    write_audit(db, action="quick_reply.update", user_id=user.user_id, entity_id=str(reply_id))
    return _reply_out(row)


def _tpl_out(row: WhatsAppTemplate) -> TemplateOut:
    return TemplateOut(
        template_id=row.template_id,
        template_name=row.template_name,
        category=row.category,
        language=row.language,
        status=row.status,
        header_text=row.header_text,
        body_text=row.body_text,
        footer_text=row.footer_text,
    )


@templates_router.get("", response_model=List[TemplateOut])
def list_templates(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.CHATS_MANAGE))],
) -> List[TemplateOut]:
    return [_tpl_out(row) for row in db.query(WhatsAppTemplate).order_by(WhatsAppTemplate.template_name.asc()).all()]


@templates_router.post("", response_model=TemplateOut)
def create_template(
    payload: TemplateIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(Permission.TEMPLATES_MANAGE))],
) -> TemplateOut:
    row = WhatsAppTemplate(**payload.model_dump())
    db.add(row)
    db.flush()
    write_audit(db, action="template.create", user_id=user.user_id, entity_id=str(row.template_id))
    return _tpl_out(row)


def _ai_flags(db: Session) -> dict:
    from app.core.config import get_settings as get_app_settings
    from app.models.content import Setting

    values = {row.setting_key: row.setting_value or "" for row in db.query(Setting).all()}
    return {
        "auto_reply": values.get("ai_auto_reply", "0") in {"1", "true", "yes", "on"},
        "pause_when_human": values.get("ai_pause_when_human", "0") in {"1", "true", "yes", "on"},
        "agent_name": values.get("ai_agent_name") or "MamaHub",
        "model": values.get("ai_model") or get_app_settings().openai_model,
        "openai_configured": bool(get_app_settings().openai_api_key),
    }


@ai_router.get("/status")
def ai_status(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.AI_USE))],
) -> dict:
    return _ai_flags(db)


@ai_router.patch("/settings")
def update_ai_settings(
    payload: dict,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(Permission.AI_USE))],
) -> dict:
    from app.models.content import Setting

    mapping = {
        "auto_reply": "ai_auto_reply",
        "pause_when_human": "ai_pause_when_human",
    }
    for field, key in mapping.items():
        if field not in payload:
            continue
        value = "1" if payload.get(field) in {True, 1, "1", "true", "yes", "on"} else "0"
        row = db.query(Setting).filter(Setting.setting_key == key).first()
        if row:
            row.setting_value = value
        else:
            db.add(Setting(setting_key=key, setting_value=value, setting_group="ai"))
    write_audit(db, action="ai.settings.update", user_id=user.user_id)
    db.flush()
    return _ai_flags(db)


@ai_router.post("/suggest-reply", response_model=SuggestReplyResponse)
def suggest_reply(
    payload: SuggestReplyRequest,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.AI_USE))],
) -> SuggestReplyResponse:
    return ai_service.suggest_reply(db, payload.conversation_id, payload.latest_message)


@dashboard_router.get("", response_model=DashboardOut)
def get_dashboard(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
) -> DashboardOut:
    return dashboard_service.dashboard(db)


@reports_router.get("")
def get_reports(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.REPORTS_VIEW))],
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    agent_id: Optional[int] = None,
    status: Optional[str] = None,
    order_status: Optional[str] = None,
) -> dict:
    return dashboard_service.reports(
        db,
        date_from=date_from,
        date_to=date_to,
        agent_id=agent_id,
        status=status,
        order_status=order_status,
    )


@settings_router.get("")
def get_settings(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.SETTINGS_MANAGE))],
) -> list[dict]:
    return [
        {"key": row.setting_key, "value": row.setting_value, "group": row.setting_group}
        for row in db.query(Setting).order_by(Setting.setting_group, Setting.setting_key).all()
    ]


@settings_router.put("")
def update_settings(
    payload: dict,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(Permission.SETTINGS_MANAGE))],
) -> dict[str, str]:
    items = payload.get("items") or []
    for item in items:
        row = db.query(Setting).filter(Setting.setting_key == item.get("key")).first()
        if row:
            row.setting_value = item.get("value")
        else:
            db.add(Setting(setting_key=item.get("key"), setting_value=item.get("value"), setting_group=item.get("group") or "general"))
    write_audit(db, action="settings.update", user_id=user.user_id)
    return {"status": "ok"}
