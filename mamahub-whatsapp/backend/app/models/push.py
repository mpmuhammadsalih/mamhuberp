"""Web Push subscriptions for installed CRM apps."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Identity, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class PushSubscription(Base):
    __tablename__ = "WA_PUSH_SUBSCRIPTIONS"
    __table_args__ = (UniqueConstraint("endpoint", name="uq_wa_push_endpoint"),)

    subscription_id: Mapped[int] = mapped_column(Integer, Identity(start=1), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("WA_USERS.user_id"), nullable=False, index=True)
    endpoint: Mapped[str] = mapped_column(String(2000), nullable=False)
    p256dh: Mapped[str] = mapped_column(String(255), nullable=False)
    auth: Mapped[str] = mapped_column(String(255), nullable=False)
    user_agent: Mapped[Optional[str]] = mapped_column(String(400))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.sysdate(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.sysdate(), nullable=False)
