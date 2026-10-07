"""Message and attachment models."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Identity, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Message(Base):
    __tablename__ = "WA_MESSAGES"

    id: Mapped[int] = mapped_column(Integer, Identity(start=1), primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("WA_CONVERSATIONS.conversation_id"), nullable=False, index=True)
    whatsapp_message_id: Mapped[Optional[str]] = mapped_column(String(80), unique=True, index=True)
    sender_type: Mapped[str] = mapped_column(String(20), nullable=False)
    sender_id: Mapped[Optional[int]] = mapped_column(Integer)
    message_type: Mapped[str] = mapped_column(String(30), nullable=False, default="text")
    message_text: Mapped[Optional[str]] = mapped_column(Text)
    media_url: Mapped[Optional[str]] = mapped_column(String(500))
    media_mime_type: Mapped[Optional[str]] = mapped_column(String(80))
    latitude: Mapped[Optional[str]] = mapped_column(String(40))
    longitude: Mapped[Optional[str]] = mapped_column(String(40))
    payload_json: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="SENT", index=True)
    error_message: Mapped[Optional[str]] = mapped_column(String(500))
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.sysdate(), nullable=False, index=True)

    attachments = relationship("MessageAttachment", back_populates="message", cascade="all, delete-orphan")


class MessageAttachment(Base):
    __tablename__ = "WA_MESSAGE_ATTACHMENTS"

    attachment_id: Mapped[int] = mapped_column(Integer, Identity(start=1), primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("WA_MESSAGES.id"), nullable=False, index=True)
    media_id: Mapped[Optional[str]] = mapped_column(String(80))
    file_name: Mapped[Optional[str]] = mapped_column(String(255))
    mime_type: Mapped[Optional[str]] = mapped_column(String(80))
    file_url: Mapped[Optional[str]] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.sysdate(), nullable=False)

    message = relationship("Message", back_populates="attachments")
