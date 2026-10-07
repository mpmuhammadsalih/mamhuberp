from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import AppError, NotFoundError
from app.integrations.whatsapp.client import whatsapp_client
from app.models.conversation import Conversation
from app.models.customer import Customer
from app.models.enums import MessageStatus, SenderType
from app.models.message import Message
from app.models.order import Order, OrderItem
from app.models.user import User
from app.repositories.oracle.order_repository import OracleCrmOrderRepository
from app.schemas.crm import OrderCreate, OrderItemOut, OrderOut, OrderUpdate
from app.services.audit_service import write_audit


def _to_out(order: Order) -> OrderOut:
    return OrderOut(
        order_id=order.order_id,
        order_number=order.order_number,
        customer_id=order.customer_id,
        conversation_id=order.conversation_id,
        order_date=order.order_date,
        subtotal=float(order.subtotal or 0),
        discount=float(order.discount or 0),
        delivery_charge=float(order.delivery_charge or 0),
        total_amount=float(order.total_amount or 0),
        payment_method=order.payment_method,
        order_status=order.order_status,
        delivery_address=order.delivery_address,
        notes=order.notes,
        created_by=order.created_by,
        mh_order_id=order.mh_order_id,
        erp_bill_no=order.erp_bill_no,
        erp_post_status=order.erp_post_status,
        erp_post_error=order.erp_post_error,
        items=[
            OrderItemOut(
                item_id=item.item_id,
                itemcode=item.itemcode,
                itemname=item.itemname,
                quantity=float(item.quantity),
                unit_price=float(item.unit_price),
                line_total=float(item.line_total),
            )
            for item in order.items
        ],
    )


def create_order(session: Session, payload: OrderCreate, user: User) -> OrderOut:
    customer = session.get(Customer, payload.customer_id)
    if not customer:
        raise NotFoundError("Customer not found")
    repo = OracleCrmOrderRepository(session)
    items: list[OrderItem] = []
    subtotal = 0.0
    for line in payload.items:
        line_total = float(line.quantity) * float(line.unit_price)
        subtotal += line_total
        items.append(
            OrderItem(
                itemcode=line.itemcode,
                itemname=line.itemname,
                quantity=line.quantity,
                unit_price=line.unit_price,
                line_total=line_total,
            )
        )
    total = max(0.0, subtotal - float(payload.discount) + float(payload.delivery_charge))
    order = Order(
        order_number=repo.next_order_number(),
        customer_id=payload.customer_id,
        conversation_id=payload.conversation_id,
        subtotal=subtotal,
        discount=payload.discount,
        delivery_charge=payload.delivery_charge,
        total_amount=total,
        payment_method=payload.payment_method,
        order_status=payload.order_status,
        delivery_address=payload.delivery_address,
        notes=payload.notes,
        created_by=user.user_id,
        items=items,
    )
    repo.create(order)
    write_audit(
        session,
        action="order.create",
        user_id=user.user_id,
        entity_type="order",
        entity_id=str(order.order_id),
        details=order.order_number,
    )
    order.customer = customer
    _try_post_erp(session, order, user)
    if payload.send_confirmation and payload.conversation_id:
        _send_confirmation(session, order, customer, payload.conversation_id, user)
    session.flush()
    return _to_out(order)


def _try_post_erp(session: Session, order: Order, user: User) -> None:
    if order.mh_order_id:
        return
    repo = OracleCrmOrderRepository(session)
    nested = session.begin_nested()
    try:
        result = repo.post_to_web_order(order)
        nested.commit()
        write_audit(
            session,
            action="order.web_post",
            user_id=user.user_id,
            entity_type="order",
            entity_id=str(order.order_id),
            details=str(result.get("order_number") or ""),
        )
    except Exception as exc:  # noqa: BLE001
        nested.rollback()
        order.erp_post_status = "FAILED"
        order.erp_post_error = str(exc)[:500]
        write_audit(
            session,
            action="order.web_post_failed",
            user_id=user.user_id,
            entity_type="order",
            entity_id=str(order.order_id),
            details=str(exc)[:400],
        )


def remove_uninvoiced_order(session: Session, order_id: int, user: User) -> OrderOut:
    order = (
        session.query(Order)
        .options(joinedload(Order.items), joinedload(Order.customer))
        .filter(Order.order_id == order_id)
        .first()
    )
    if not order:
        raise NotFoundError("Order not found")
    if order.erp_bill_no:
        raise AppError("This order already has a sales invoice and cannot be removed.")
    repo = OracleCrmOrderRepository(session)
    if order.mh_order_id or str(order.order_number or "").startswith("ORD-"):
        try:
            repo.remove_web_order(order)
        except RuntimeError as exc:
            raise AppError(str(exc)) from exc
    order.order_status = "Cancelled"
    order.mh_order_id = None
    order.erp_post_status = "REMOVED"
    order.erp_post_error = None
    order.updated_at = datetime.utcnow()
    write_audit(
        session,
        action="order.remove",
        user_id=user.user_id,
        entity_type="order",
        entity_id=str(order.order_id),
        details=order.order_number,
    )
    session.flush()
    return _to_out(order)


def sync_order_to_erp(session: Session, order_id: int, user: User) -> OrderOut:
    order = (
        session.query(Order)
        .options(joinedload(Order.items), joinedload(Order.customer))
        .filter(Order.order_id == order_id)
        .first()
    )
    if not order:
        raise NotFoundError("Order not found")
    _try_post_erp(session, order, user)
    session.flush()
    return _to_out(order)


def _send_confirmation(session: Session, order: Order, customer: Customer, conversation_id: int, user: User) -> None:
    fulfillment = "delivery" if (order.delivery_address or "").strip() else "pickup"
    lines = "\n".join(f"- {item.itemname} x {item.quantity:g} = QAR {float(item.line_total):.2f}" for item in order.items)
    body = (
        f"Hi {customer.customer_name}! Your MamaHub order {order.order_number} is confirmed.\n"
        f"{lines}\n"
        f"Total: QAR {float(order.total_amount):.2f} ({fulfillment}).\n"
        f"Payment: {order.payment_method}"
    )
    ok, wa_id, _ = whatsapp_client.send_text_message(customer.whatsapp_number, body)
    now = datetime.utcnow()
    session.add(
        Message(
            conversation_id=conversation_id,
            whatsapp_message_id=wa_id if ok else None,
            sender_type=SenderType.SYSTEM.value,
            sender_id=user.user_id,
            message_type="order",
            message_text=body,
            status=MessageStatus.SENT.value if ok else MessageStatus.FAILED.value,
            sent_at=now if ok else None,
            created_at=now,
        )
    )
    conversation = session.get(Conversation, conversation_id)
    if conversation:
        conversation.last_message_at = now
        conversation.last_message_text = f"Order {order.order_number} confirmed"
        conversation.updated_at = now


def get_order(session: Session, order_id: int) -> OrderOut:
    order = session.get(Order, order_id)
    if not order:
        raise NotFoundError("Order not found")
    return _to_out(order)


def update_order(session: Session, order_id: int, payload: OrderUpdate, user: User) -> OrderOut:
    order = session.get(Order, order_id)
    if not order:
        raise NotFoundError("Order not found")
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(order, key, value)
    if "discount" in data or "delivery_charge" in data:
        order.total_amount = max(0.0, float(order.subtotal or 0) - float(order.discount or 0) + float(order.delivery_charge or 0))
    order.updated_at = datetime.utcnow()
    write_audit(
        session,
        action="order.update",
        user_id=user.user_id,
        entity_type="order",
        entity_id=str(order_id),
        details=order.order_status,
    )
    return _to_out(order)


def list_orders(session: Session, customer_id: Optional[int] = None) -> list[OrderOut]:
    query = session.query(Order).options(joinedload(Order.items))
    if customer_id:
        query = query.filter(Order.customer_id == customer_id)
    return [_to_out(row) for row in query.order_by(Order.order_date.desc()).all()]
