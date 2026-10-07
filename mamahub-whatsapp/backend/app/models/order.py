"""Order and order-item models."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Identity, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Order(Base):
    __tablename__ = "WA_ORDERS"

    order_id: Mapped[int] = mapped_column(Integer, Identity(start=1), primary_key=True)
    order_number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("WA_CUSTOMERS.customer_id"), nullable=False, index=True)
    conversation_id: Mapped[Optional[int]] = mapped_column(ForeignKey("WA_CONVERSATIONS.conversation_id"))
    order_date: Mapped[datetime] = mapped_column(DateTime, server_default=func.sysdate(), nullable=False)
    subtotal: Mapped[float] = mapped_column(Numeric(18, 3), default=0)
    discount: Mapped[float] = mapped_column(Numeric(18, 3), default=0)
    delivery_charge: Mapped[float] = mapped_column(Numeric(18, 3), default=0)
    total_amount: Mapped[float] = mapped_column(Numeric(18, 3), default=0)
    payment_method: Mapped[str] = mapped_column(String(40), default="Cash")
    order_status: Mapped[str] = mapped_column(String(40), default="Draft", index=True)
    delivery_address: Mapped[Optional[str]] = mapped_column(String(400))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.sysdate(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.sysdate(), nullable=False)
    mh_order_id: Mapped[Optional[int]] = mapped_column(Integer)
    erp_bill_no: Mapped[Optional[str]] = mapped_column(String(30))
    erp_location_code: Mapped[Optional[int]] = mapped_column(Integer)
    erp_reset_no: Mapped[Optional[int]] = mapped_column(Integer)
    erp_posted_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    erp_post_status: Mapped[Optional[str]] = mapped_column(String(20))
    erp_post_error: Mapped[Optional[str]] = mapped_column(String(500))

    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    customer = relationship("Customer")


class OrderItem(Base):
    __tablename__ = "WA_ORDER_ITEMS"

    item_id: Mapped[int] = mapped_column(Integer, Identity(start=1), primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("WA_ORDERS.order_id"), nullable=False, index=True)
    itemcode: Mapped[str] = mapped_column(String(40), nullable=False)
    itemname: Mapped[str] = mapped_column(String(250), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(18, 3), nullable=False, default=1)
    unit_price: Mapped[float] = mapped_column(Numeric(18, 3), nullable=False, default=0)
    line_total: Mapped[float] = mapped_column(Numeric(18, 3), nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.sysdate(), nullable=False)

    order = relationship("Order", back_populates="items")
