"""Conversation and assignment models."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Identity, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Conversation(Base):
    __tablename__ = "WA_CONVERSATIONS"

    conversation_id: Mapped[int] = mapped_column(Integer, Identity(start=1), primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("WA_CUSTOMERS.customer_id"), nullable=False, index=True)
    whatsapp_number: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    assigned_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("WA_USERS.user_id"), index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN", index=True)
    last_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime, index=True)
    last_message_text: Mapped[Optional[str]] = mapped_column(String(500))
    unread_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.sysdate(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.sysdate(), nullable=False)
    cart_pending_sku: Mapped[Optional[str]] = mapped_column(String(80))
    cart_offer_json: Mapped[Optional[str]] = mapped_column(String(2000))
    ad_source_type: Mapped[Optional[str]] = mapped_column(String(20))
    ad_source_id: Mapped[Optional[str]] = mapped_column(String(80))
    ad_headline: Mapped[Optional[str]] = mapped_column(String(240))
    ad_body: Mapped[Optional[str]] = mapped_column(String(500))
    ad_image_url: Mapped[Optional[str]] = mapped_column(String(2000))
    ad_source_url: Mapped[Optional[str]] = mapped_column(String(2000))

    customer = relationship("Customer")
    assigned_user = relationship("User")


class ConversationAssignment(Base):
    __tablename__ = "WA_CONV_ASSIGNMENTS"

    assignment_id: Mapped[int] = mapped_column(Integer, Identity(start=1), primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("WA_CONVERSATIONS.conversation_id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("WA_USERS.user_id"), nullable=False)
    assigned_by: Mapped[Optional[int]] = mapped_column(Integer)
    assigned_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.sysdate(), nullable=False)
    note: Mapped[Optional[str]] = mapped_column(String(400))


class ConversationStar(Base):
    __tablename__ = "WA_CONVERSATION_STARS"
    __table_args__ = (UniqueConstraint("conversation_id", "user_id", name="uq_wa_conv_star"),)

    star_id: Mapped[int] = mapped_column(Integer, Identity(start=1), primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("WA_CONVERSATIONS.conversation_id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("WA_USERS.user_id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.sysdate(), nullable=False)


class ConversationCartItem(Base):
    __tablename__ = "WA_CART_ITEMS"
    __table_args__ = (UniqueConstraint("conversation_id", "itemcode", name="uq_wa_cart_item"),)

    cart_item_id: Mapped[int] = mapped_column(Integer, Identity(start=1), primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("WA_CONVERSATIONS.conversation_id"), nullable=False, index=True)
    itemcode: Mapped[str] = mapped_column(String(80), nullable=False)
    itemname: Mapped[str] = mapped_column(String(240), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(18, 3), nullable=False, default=1)
    unit_price: Mapped[float] = mapped_column(Numeric(18, 3), nullable=False, default=0)
    image_url: Mapped[Optional[str]] = mapped_column(String(500))
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.sysdate(), nullable=False)
