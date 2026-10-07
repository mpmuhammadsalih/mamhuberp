from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.models.enums import ConversationStatus, SenderType
from app.models.message import Message
from app.models.order import Order, OrderItem
from app.models.user import User
from app.schemas.crm import DashboardOut


def _day_start(days_ago: int = 0) -> datetime:
    now = datetime.utcnow()
    start = datetime(now.year, now.month, now.day)
    return start - timedelta(days=days_ago)


def dashboard(session: Session) -> DashboardOut:
    today = _day_start()
    week = _day_start(6)

    today_messages = session.query(func.count(Message.id)).filter(Message.created_at >= today).scalar() or 0
    active = (
        session.query(func.count(Conversation.conversation_id))
        .filter(Conversation.status.in_([ConversationStatus.OPEN.value, ConversationStatus.PENDING.value]))
        .scalar()
        or 0
    )
    unread = (
        session.query(func.count(Conversation.conversation_id))
        .filter(Conversation.unread_count > 0)
        .scalar()
        or 0
    )
    resolved = (
        session.query(func.count(Conversation.conversation_id))
        .filter(Conversation.status == ConversationStatus.RESOLVED.value)
        .scalar()
        or 0
    )
    orders_today = session.query(func.count(Order.order_id)).filter(Order.order_date >= today).scalar() or 0
    wa_orders_today = (
        session.query(func.count(Order.order_id))
        .filter(Order.order_date >= today, Order.conversation_id.isnot(None))
        .scalar()
        or 0
    )
    sales_today = (
        session.query(func.coalesce(func.sum(Order.total_amount), 0))
        .filter(Order.order_date >= today, Order.order_status != "Cancelled")
        .scalar()
        or 0
    )
    pending_orders = (
        session.query(func.count(Order.order_id))
        .filter(Order.order_status.in_(["Draft", "Confirmed", "Processing", "Ready"]))
        .scalar()
        or 0
    )

    conversations_by_day = _count_by_day(session, Message.created_at, week, Message.sender_type == SenderType.CUSTOMER.value)
    orders_by_day = _count_by_day(session, Order.order_date, week)
    sales_by_day = _sum_by_day(session, Order.order_date, Order.total_amount, week, Order.order_status != "Cancelled")

    top_products = [
        {"itemname": row[0], "qty": float(row[1] or 0)}
        for row in (
            session.query(OrderItem.itemname, func.sum(OrderItem.quantity))
            .group_by(OrderItem.itemname)
            .order_by(func.sum(OrderItem.quantity).desc())
            .limit(8)
            .all()
        )
    ]
    agent_performance = []
    agents = session.query(User).filter(User.is_active == 1).all()
    for agent in agents:
        sent = (
            session.query(func.count(Message.id))
            .filter(Message.sender_type == SenderType.AGENT.value, Message.sender_id == agent.user_id, Message.created_at >= week)
            .scalar()
            or 0
        )
        assigned = (
            session.query(func.count(Conversation.conversation_id))
            .filter(Conversation.assigned_user_id == agent.user_id)
            .scalar()
            or 0
        )
        agent_performance.append(
            {
                "user_id": agent.user_id,
                "name": agent.full_name,
                "messages_sent": int(sent),
                "assigned_chats": int(assigned),
            }
        )

    return DashboardOut(
        today_messages=int(today_messages),
        active_conversations=int(active),
        unread_conversations=int(unread),
        orders_today=int(orders_today),
        whatsapp_orders_today=int(wa_orders_today),
        sales_today=float(sales_today),
        pending_orders=int(pending_orders),
        resolved_conversations=int(resolved),
        conversations_by_day=conversations_by_day,
        orders_by_day=orders_by_day,
        sales_by_day=sales_by_day,
        top_products=top_products,
        agent_performance=agent_performance,
    )


def _count_by_day(session: Session, column, since: datetime, *filters):
    rows = (
        session.query(func.trunc(column), func.count())
        .filter(column >= since, *filters)
        .group_by(func.trunc(column))
        .order_by(func.trunc(column))
        .all()
    )
    return [{"date": str(row[0])[:10], "value": int(row[1])} for row in rows]


def _sum_by_day(session: Session, column, amount, since: datetime, *filters):
    rows = (
        session.query(func.trunc(column), func.coalesce(func.sum(amount), 0))
        .filter(column >= since, *filters)
        .group_by(func.trunc(column))
        .order_by(func.trunc(column))
        .all()
    )
    return [{"date": str(row[0])[:10], "value": float(row[1])} for row in rows]


def reports(
    session: Session,
    *,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    agent_id: int | None = None,
    status: str | None = None,
    order_status: str | None = None,
) -> dict:
    start = date_from or _day_start(30)
    end = date_to or datetime.utcnow()
    conv_q = session.query(Conversation).filter(Conversation.created_at >= start, Conversation.created_at <= end)
    if agent_id:
        conv_q = conv_q.filter(Conversation.assigned_user_id == agent_id)
    if status:
        conv_q = conv_q.filter(Conversation.status == status.upper())
    conversations = conv_q.count()
    unread = conv_q.filter(Conversation.unread_count > 0).count()

    order_q = session.query(Order).filter(Order.order_date >= start, Order.order_date <= end)
    if order_status:
        order_q = order_q.filter(Order.order_status == order_status)
    orders = order_q.count()
    sales = float(
        session.query(func.coalesce(func.sum(Order.total_amount), 0))
        .filter(Order.order_date >= start, Order.order_date <= end, Order.order_status != "Cancelled")
        .scalar()
        or 0
    )
    missed = (
        session.query(func.count(Conversation.conversation_id))
        .filter(Conversation.unread_count > 0, Conversation.last_message_at >= start)
        .scalar()
        or 0
    )
    top_customers = [
        {"customer_id": row[0], "orders": int(row[1]), "sales": float(row[2] or 0)}
        for row in (
            session.query(Order.customer_id, func.count(Order.order_id), func.sum(Order.total_amount))
            .filter(Order.order_date >= start, Order.order_date <= end)
            .group_by(Order.customer_id)
            .order_by(func.sum(Order.total_amount).desc())
            .limit(10)
            .all()
        )
    ]
    return {
        "conversations": conversations,
        "unread": unread,
        "orders": orders,
        "sales": sales,
        "missed_conversations": int(missed),
        "top_customers": top_customers,
        "agent_performance": dashboard(session).agent_performance,
        "top_products": dashboard(session).top_products,
    }
