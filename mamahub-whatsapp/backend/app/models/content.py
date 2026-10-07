"""Quick replies, templates, settings, and audit logs."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Identity, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class QuickReply(Base):
    __tablename__ = "WA_QUICK_REPLIES"

    reply_id: Mapped[int] = mapped_column(Integer, Identity(start=1), primary_key=True)
    shortcut: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.sysdate(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.sysdate(), nullable=False)


class WhatsAppTemplate(Base):
    __tablename__ = "WA_WHATSAPP_TEMPLATES"

    template_id: Mapped[int] = mapped_column(Integer, Identity(start=1), primary_key=True)
    template_name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(40))
    language: Mapped[str] = mapped_column(String(20), default="en")
    status: Mapped[str] = mapped_column(String(40), default="APPROVED")
    header_text: Mapped[Optional[str]] = mapped_column(String(200))
    body_text: Mapped[Optional[str]] = mapped_column(Text)
    footer_text: Mapped[Optional[str]] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.sysdate(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.sysdate(), nullable=False)


class Setting(Base):
    __tablename__ = "WA_SETTINGS"

    setting_id: Mapped[int] = mapped_column(Integer, Identity(start=1), primary_key=True)
    setting_key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    setting_value: Mapped[Optional[str]] = mapped_column(Text)
    setting_group: Mapped[str] = mapped_column(String(40), default="general")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.sysdate(), nullable=False)


class AuditLog(Base):
    __tablename__ = "WA_AUDIT_LOGS"

    log_id: Mapped[int] = mapped_column(Integer, Identity(start=1), primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_type: Mapped[Optional[str]] = mapped_column(String(80))
    entity_id: Mapped[Optional[str]] = mapped_column(String(80))
    details: Mapped[Optional[str]] = mapped_column(Text)
    ip_address: Mapped[Optional[str]] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.sysdate(), nullable=False, index=True)
