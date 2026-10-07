from __future__ import annotations

from typing import Optional

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, NotFoundError
from app.models.customer import Customer, CustomerNote, CustomerTag
from app.models.order import Order
from app.models.user import User
from app.repositories.oracle.erp_customer import DuplicateCustomerError, OracleErpCustomerRepository, validate_email
from app.schemas.crm import CustomerOut, CustomerUpdate
from app.services.audit_service import write_audit


def _stats(session: Session, customer_id: int) -> tuple[int, float, Optional[object]]:
    total_orders, total_purchases, last_purchase = (
        session.query(
            func.count(Order.order_id),
            func.coalesce(func.sum(Order.total_amount), 0),
            func.max(Order.order_date),
        )
        .filter(Order.customer_id == customer_id)
        .one()
    )
    return int(total_orders or 0), float(total_purchases or 0), last_purchase


def to_out(session: Session, customer: Customer) -> CustomerOut:
    total_orders, total_purchases, last_purchase = _stats(session, customer.customer_id)
    return CustomerOut(
        customer_id=customer.customer_id,
        customer_code=customer.customer_code,
        customer_name=customer.customer_name,
        whatsapp_number=customer.whatsapp_number,
        email=customer.email,
        address=customer.address,
        latitude=float(customer.latitude) if customer.latitude is not None else None,
        longitude=float(customer.longitude) if customer.longitude is not None else None,
        location_label=customer.location_label,
        customer_type=customer.customer_type or "Retail",
        notes=customer.notes,
        tags=[tag.tag_name for tag in customer.tags],
        total_orders=total_orders,
        total_purchases=total_purchases,
        last_purchase_date=last_purchase,
        outstanding_balance=float(customer.outstanding_balance or 0),
        profile_image_url=customer.profile_image_url,
        erp_customer_code=customer.erp_customer_code,
        source_channel=_source_channel(session, customer),
        created_at=customer.created_at,
    )


def _source_channel(session: Session, customer: Customer) -> Optional[str]:
    code = str(customer.erp_customer_code or customer.customer_code or "").strip()
    if not code or not code.isdigit():
        return "WHATSAPP"
    try:
        row = session.execute(
            text(
                """
                SELECT SOURCE_CHANNEL FROM CUSTOMER
                WHERE TO_CHAR(CUSTOMERCODE) = :code
                FETCH FIRST 1 ROWS ONLY
                """
            ),
            {"code": code},
        ).scalar()
        return str(row or "WHATSAPP")
    except Exception:
        return "WHATSAPP"


def get_customer(session: Session, customer_id: int) -> CustomerOut:
    customer = session.get(Customer, customer_id)
    if not customer:
        raise NotFoundError("Customer not found")
    return to_out(session, customer)


def update_customer(session: Session, customer_id: int, payload: CustomerUpdate, user: User) -> CustomerOut:
    customer = session.get(Customer, customer_id)
    if not customer:
        raise NotFoundError("Customer not found")
    data = payload.model_dump(exclude_unset=True)
    tags = data.pop("tags", None)
    if "email" in data:
        ok_email, email_msg = validate_email(data.get("email"), required=False)
        if not ok_email:
            raise AppError(email_msg)
    for key, value in data.items():
        setattr(customer, key, value)
    if tags is not None:
        session.query(CustomerTag).filter(CustomerTag.customer_id == customer_id).delete()
        for name in tags:
            if name.strip():
                session.add(CustomerTag(customer_id=customer_id, tag_name=name.strip()))
    try:
        OracleErpCustomerRepository(session).upsert(
            channel="WHATSAPP",
            name=customer.customer_name,
            mobile=customer.whatsapp_number,
            email=customer.email,
            address=customer.address,
            whatsapp=customer.whatsapp_number,
        )
    except DuplicateCustomerError as exc:
        raise AppError(str(exc)) from exc
    except Exception:
        pass
    write_audit(
        session,
        action="customer.update",
        user_id=user.user_id,
        entity_type="customer",
        entity_id=str(customer_id),
    )
    session.flush()
    session.refresh(customer)
    return to_out(session, customer)


def set_profile_image(session: Session, customer_id: int, image_url: str, user: User) -> CustomerOut:
    customer = session.get(Customer, customer_id)
    if not customer:
        raise NotFoundError("Customer not found")
    customer.profile_image_url = image_url
    write_audit(
        session,
        action="customer.photo",
        user_id=user.user_id,
        entity_type="customer",
        entity_id=str(customer_id),
    )
    session.flush()
    session.refresh(customer)
    return to_out(session, customer)


def add_note(session: Session, customer_id: int, note_text: str, user: User) -> None:
    if not session.get(Customer, customer_id):
        raise NotFoundError("Customer not found")
    session.add(CustomerNote(customer_id=customer_id, note_text=note_text, created_by=user.user_id))


def _get_note(session: Session, customer_id: int, note_id: int) -> CustomerNote:
    note = session.get(CustomerNote, note_id)
    if not note or note.customer_id != customer_id:
        raise NotFoundError("Note not found")
    return note


def update_note(session: Session, customer_id: int, note_id: int, note_text: str, user: User) -> None:
    note = _get_note(session, customer_id, note_id)
    note.note_text = note_text.strip()
    write_audit(
        session,
        action="customer.note.update",
        user_id=user.user_id,
        entity_type="customer_note",
        entity_id=str(note_id),
    )


def delete_note(session: Session, customer_id: int, note_id: int, user: User) -> None:
    note = _get_note(session, customer_id, note_id)
    session.delete(note)
    write_audit(
        session,
        action="customer.note.delete",
        user_id=user.user_id,
        entity_type="customer_note",
        entity_id=str(note_id),
    )
