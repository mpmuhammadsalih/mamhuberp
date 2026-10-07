"""User and role models."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Identity, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class User(Base):
    __tablename__ = "WA_USERS"

    user_id: Mapped[int] = mapped_column(Integer, Identity(start=1), primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(150))
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(40), nullable=False, default="SALES")
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.sysdate(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.sysdate(), nullable=False)


class RoleRecord(Base):
    __tablename__ = "WA_ROLES"

    role_id: Mapped[int] = mapped_column(Integer, Identity(start=1), primary_key=True)
    role_code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    role_name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(400))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.sysdate(), nullable=False)
