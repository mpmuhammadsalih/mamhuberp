"""Customer, notes, and tags."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Identity, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Customer(Base):
    __tablename__ = "WA_CUSTOMERS"

    customer_id: Mapped[int] = mapped_column(Integer, Identity(start=1), primary_key=True)
    customer_code: Mapped[Optional[str]] = mapped_column(String(40), unique=True)
    customer_name: Mapped[str] = mapped_column(String(200), nullable=False)
    whatsapp_number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(150))
    address: Mapped[Optional[str]] = mapped_column(String(400))
    latitude: Mapped[Optional[float]] = mapped_column(Numeric(12, 8))
    longitude: Mapped[Optional[float]] = mapped_column(Numeric(12, 8))
    location_label: Mapped[Optional[str]] = mapped_column(String(200))
    customer_type: Mapped[str] = mapped_column(String(40), default="Retail")
    notes: Mapped[Optional[str]] = mapped_column(Text)
    profile_image_url: Mapped[Optional[str]] = mapped_column(String(500))
    erp_customer_code: Mapped[Optional[str]] = mapped_column(String(40))
    outstanding_balance: Mapped[float] = mapped_column(Numeric(18, 3), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.sysdate(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.sysdate(), nullable=False)

    notes_list = relationship("CustomerNote", back_populates="customer", cascade="all, delete-orphan")
    tags = relationship("CustomerTag", back_populates="customer", cascade="all, delete-orphan")


class CustomerNote(Base):
    __tablename__ = "WA_CUSTOMER_NOTES"

    note_id: Mapped[int] = mapped_column(Integer, Identity(start=1), primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("WA_CUSTOMERS.customer_id"), nullable=False, index=True)
    note_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.sysdate(), nullable=False)

    customer = relationship("Customer", back_populates="notes_list")


class CustomerTag(Base):
    __tablename__ = "WA_CUSTOMER_TAGS"

    tag_id: Mapped[int] = mapped_column(Integer, Identity(start=1), primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("WA_CUSTOMERS.customer_id"), nullable=False, index=True)
    tag_name: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.sysdate(), nullable=False)

    customer = relationship("Customer", back_populates="tags")
