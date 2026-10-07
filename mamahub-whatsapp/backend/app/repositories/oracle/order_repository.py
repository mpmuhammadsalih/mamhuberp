"""WhatsApp CRM orders stored in WA_ORDERS, posted as website MH_ORDER rows."""
from __future__ import annotations

import json
import re
import secrets
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import logger
from app.models.customer import Customer
from app.models.order import Order


class OracleCrmOrderRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def next_order_number(self) -> str:
        today = datetime.now().strftime("%Y%m%d")
        prefix = f"WA-{today}-"
        last = (
            self.session.query(func.max(Order.order_number))
            .filter(Order.order_number.like(f"{prefix}%"))
            .scalar()
        )
        seq = 1
        if last:
            try:
                seq = int(str(last).split("-")[-1]) + 1
            except ValueError:
                seq = 1
        return f"{prefix}{seq:04d}"

    def create(self, order: Order) -> Order:
        if not order.order_number:
            order.order_number = self.next_order_number()
        self.session.add(order)
        self.session.flush()
        return order

    def get(self, order_id: int) -> Optional[Order]:
        return self.session.get(Order, order_id)

    def list_for_customer(self, customer_id: int) -> list[Order]:
        return (
            self.session.query(Order)
            .filter(Order.customer_id == customer_id)
            .order_by(Order.order_date.desc())
            .all()
        )

    def _table_exists(self, table: str) -> bool:
        row = self.session.execute(
            text("SELECT COUNT(*) FROM USER_TABLES WHERE TABLE_NAME = :t"),
            {"t": table.upper()},
        ).scalar()
        return int(row or 0) > 0

    def _column_exists(self, table: str, column: str) -> bool:
        row = self.session.execute(
            text(
                """
                SELECT COUNT(*) FROM USER_TAB_COLUMNS
                WHERE TABLE_NAME = :t AND COLUMN_NAME = :c
                """
            ),
            {"t": table.upper(), "c": column.upper()},
        ).scalar()
        return int(row or 0) > 0

    def _ensure_created_by_name(self) -> None:
        if self._column_exists("MH_ORDER", "CREATED_BY_NAME"):
            return
        self.session.execute(text("ALTER TABLE MH_ORDER ADD (CREATED_BY_NAME VARCHAR2(40))"))
        logger.info("Added MH_ORDER.CREATED_BY_NAME")

    def _next_seq(self, sequence: str) -> int:
        row = self.session.execute(text(f"SELECT {sequence}.NEXTVAL FROM DUAL")).scalar()
        if not row:
            raise RuntimeError(f"Sequence {sequence} is missing")
        return int(row)

    def _phone_keys(self, raw: str) -> tuple[str, list[str]]:
        digits = re.sub(r"\D+", "", raw or "")
        if digits.startswith("00"):
            digits = digits[2:]
        variants: list[str] = []
        if digits:
            variants.append(digits)
        if len(digits) == 8:
            variants.append("974" + digits)
        if digits.startswith("974") and len(digits) > 8:
            variants.append(digits[3:])
        last8 = digits[-8:] if len(digits) >= 8 else digits
        if last8 and last8 not in variants:
            variants.append(last8)
        # unique, keep order
        seen: set[str] = set()
        unique = []
        for item in variants:
            if item and item not in seen:
                seen.add(item)
                unique.append(item)
        e164 = ""
        if digits.startswith("974") and len(digits) >= 11:
            e164 = "+" + digits
        elif len(digits) == 8:
            e164 = "+974" + digits
        elif digits:
            e164 = "+" + digits
        return e164, unique

    def _find_or_create_app_user(self, customer: Customer) -> int:
        if not self._table_exists("APP_USER"):
            raise RuntimeError("APP_USER is not available — website customer table is missing")
        e164, keys = self._phone_keys(customer.whatsapp_number)
        email = f"wa.{keys[0] if keys else customer.customer_id}@whatsapp.mamahub.store"
        found = None
        if keys:
            placeholders = ", ".join(f":p{i}" for i in range(len(keys)))
            binds = {f"p{i}": key for i, key in enumerate(keys)}
            binds["email"] = email.lower()
            found = self.session.execute(
                text(
                    f"""
                    SELECT USER_ID AS user_id
                    FROM APP_USER
                    WHERE IS_ACTIVE = 1 AND (
                        REGEXP_REPLACE(NVL(MOBILE, ''), '[^0-9]', '') IN ({placeholders})
                        OR LOWER(EMAIL) = :email
                    )
                    FETCH FIRST 1 ROWS ONLY
                    """
                ),
                binds,
            ).mappings().first()
        if found:
            return int(found["user_id"])

        parts = [part for part in str(customer.customer_name or "").strip().split() if part]
        first_name = (parts[0] if parts else "WhatsApp")[:100]
        last_name = (" ".join(parts[1:]) if len(parts) > 1 else "Customer")[:100]
        username_base = re.sub(r"[^a-z0-9]+", ".", f"wa.{keys[0] if keys else customer.customer_id}".lower()).strip(".") or "wa.customer"
        username = username_base[:100]
        suffix = 1
        while self.session.execute(
            text("SELECT USER_ID FROM APP_USER WHERE USERNAME = :u"),
            {"u": username},
        ).scalar():
            suffix += 1
            username = f"{username_base[:90]}{suffix}"

        user_id = self._next_seq("SEQ_USER_ID")
        self.session.execute(
            text(
                """
                INSERT INTO APP_USER (
                    USER_ID, USERNAME, EMAIL, MOBILE, PASSWORD_HASH,
                    FIRST_NAME, LAST_NAME, USER_TYPE, ACCOUNT_STATUS,
                    EMAIL_VERIFIED, MOBILE_VERIFIED, FAILED_LOGIN_COUNT,
                    PREFERRED_LANGUAGE, IS_ACTIVE, CREATED_AT
                ) VALUES (
                    :user_id, :username, :email, :mobile, :password_hash,
                    :first_name, :last_name, 'CUSTOMER', 'ACTIVE',
                    0, 1, 0, 'en', 1, SYSTIMESTAMP
                )
                """
            ),
            {
                "user_id": user_id,
                "username": username,
                "email": email[:255],
                "mobile": (e164 or customer.whatsapp_number)[:30],
                "password_hash": "!" + secrets.token_hex(32),
                "first_name": first_name,
                "last_name": last_name,
            },
        )
        if self._table_exists("USER_ROLE") and self._table_exists("ROLE"):
            try:
                self.session.execute(
                    text(
                        """
                        INSERT INTO USER_ROLE (USER_ROLE_ID, USER_ID, ROLE_ID, CREATED_AT)
                        SELECT SEQ_USER_ROLE_ID.NEXTVAL, :user_id, r.ROLE_ID, SYSTIMESTAMP
                        FROM ROLE r
                        WHERE r.ROLE_CODE = 'CUSTOMER'
                        """
                    ),
                    {"user_id": user_id},
                )
            except Exception:
                logger.exception("Could not assign CUSTOMER role to APP_USER %s", user_id)
        return user_id

    def post_to_erp(self, order: Order) -> dict[str, Any]:
        """Create the same MH_ORDER the website checkout writes. No thin BILLHDR."""
        return self.post_to_web_order(order)

    def post_to_web_order(self, order: Order) -> dict[str, Any]:
        if order.mh_order_id:
            return {
                "order_id": order.mh_order_id,
                "order_number": order.order_number,
                "status": "ORDERED",
                "already": True,
            }
        if not self._table_exists("MH_ORDER") or not self._table_exists("MH_ORDER_ITEM"):
            raise RuntimeError("MH_ORDER tables are not available — website orders cannot be created")
        self._ensure_created_by_name()

        if order.order_number and str(order.order_number).startswith("ORD-"):
            existing = self.session.execute(
                text("SELECT ORDER_ID FROM MH_ORDER WHERE ORDER_NUMBER = :n FETCH FIRST 1 ROWS ONLY"),
                {"n": order.order_number},
            ).scalar()
            if existing:
                order.mh_order_id = int(existing)
                order.erp_post_status = "ORDERED"
                order.erp_post_error = None
                order.erp_posted_at = datetime.now()
                self.session.flush()
                return {
                    "order_id": int(existing),
                    "order_number": order.order_number,
                    "status": "ORDERED",
                    "already": True,
                }

        customer = order.customer
        if not customer:
            raise RuntimeError("Order has no customer")
        if not order.items:
            raise RuntimeError("Order has no items")

        settings = get_settings()
        loc = int(settings.oracle_location_code or 1)
        currency = (settings.company_currency or "QAR")[:3]
        user_id = self._find_or_create_app_user(customer)
        pay = (order.payment_method or "Cash").strip()
        pay_lower = pay.lower()
        payment_status = "PAID" if pay_lower in {"card", "tap"} else "PENDING"
        fulfillment = "DELIVERY" if (order.delivery_address or "").strip() else "PICKUP"
        address_text = (order.delivery_address or "").strip()
        snapshot = json.dumps(
            {
                "street": address_text,
                "source": "whatsapp",
                "phone": customer.whatsapp_number,
            },
            ensure_ascii=False,
        )
        notes_bits = [
            f"WhatsApp {customer.whatsapp_number}",
            pay,
        ]
        if order.notes:
            notes_bits.append(str(order.notes)[:200])
        customer_notes = " · ".join(notes_bits)[:1000]

        lines: list[dict[str, Any]] = []
        for item in order.items:
            raw_code = str(item.itemcode or "").strip()
            try:
                item_code = int(float(raw_code))
            except (TypeError, ValueError):
                raise RuntimeError(f"Website orders need a numeric item code. Got {raw_code or '(blank)'}")
            qty = float(item.quantity or 0)
            if item_code <= 0 or qty <= 0:
                raise RuntimeError(f"Invalid item or quantity for {raw_code}")
            rate = float(item.unit_price or 0)
            line_total = float(item.line_total or (qty * rate))
            lines.append(
                {
                    "location_code": loc,
                    "item_code": item_code,
                    "item_name": (item.itemname or f"Item {item_code}")[:300],
                    "quantity": qty,
                    "unit_price": rate,
                    "discount_amount": 0,
                    "line_total": line_total,
                }
            )

        order_id = self._next_seq("SEQ_MH_ORDER_ID")
        order_number = f"ORD-{datetime.now().year}-{order_id:06d}"
        now = datetime.now()

        self.session.execute(
            text(
                """
                INSERT INTO MH_ORDER (
                    ORDER_ID, ORDER_NUMBER, USER_ID, CART_ID, LOCATION_CODE,
                    ORDER_STATUS, FULFILLMENT_TYPE, PAYMENT_STATUS,
                    SUBTOTAL, DISCOUNT_TOTAL, TAX_TOTAL, DELIVERY_FEE, GRAND_TOTAL,
                    CURRENCY_CODE, COUPON_CODE, DELIVERY_ZONE_ID, DELIVERY_SLOT_ID,
                    PICKUP_STORE_ID, ADDRESS_ID, ADDRESS_SNAPSHOT, CUSTOMER_NOTES,
                    CREATED_AT, CREATED_BY, CREATED_BY_NAME
                ) VALUES (
                    :order_id, :order_number, :user_id, NULL, :location_code,
                    :order_status, :fulfillment_type, :payment_status,
                    :subtotal, :discount_total, :tax_total, :delivery_fee, :grand_total,
                    :currency_code, NULL, NULL, NULL,
                    NULL, NULL, :address_snapshot, :customer_notes,
                    SYSTIMESTAMP, :created_by, :created_by_name
                )
                """
            ),
            {
                "order_id": order_id,
                "order_number": order_number,
                "user_id": user_id,
                "location_code": loc,
                "order_status": "CONFIRMED",
                "fulfillment_type": fulfillment,
                "payment_status": payment_status,
                "subtotal": float(order.subtotal or 0),
                "discount_total": float(order.discount or 0),
                "tax_total": 0,
                "delivery_fee": float(order.delivery_charge or 0),
                "grand_total": float(order.total_amount or 0),
                "currency_code": currency,
                "address_snapshot": snapshot,
                "customer_notes": customer_notes,
                "created_by": user_id,
                "created_by_name": "WhatsApp",
            },
        )

        for line in lines:
            item_id = self._next_seq("SEQ_MH_ORDER_ITEM_ID")
            self.session.execute(
                text(
                    """
                    INSERT INTO MH_ORDER_ITEM (
                        ORDER_ITEM_ID, ORDER_ID, LOCATION_CODE, ITEM_CODE, ITEM_NAME,
                        QUANTITY, UNIT_PRICE, DISCOUNT_AMOUNT, LINE_TOTAL, CREATED_AT
                    ) VALUES (
                        :order_item_id, :order_id, :location_code, :item_code, :item_name,
                        :quantity, :unit_price, :discount_amount, :line_total, SYSTIMESTAMP
                    )
                    """
                ),
                {"order_item_id": item_id, "order_id": order_id, **line},
            )

        history_id = self._next_seq("SEQ_MH_ORDER_STATUS_ID")
        self.session.execute(
            text(
                """
                INSERT INTO MH_ORDER_STATUS_HISTORY (
                    STATUS_HISTORY_ID, ORDER_ID, ORDER_STATUS, STATUS_NOTES,
                    CREATED_AT, CREATED_BY
                ) VALUES (
                    :history_id, :order_id, :status, :notes, SYSTIMESTAMP, :created_by
                )
                """
            ),
            {
                "history_id": history_id,
                "order_id": order_id,
                "status": "CONFIRMED",
                "notes": f"Order placed — WhatsApp {pay}",
                "created_by": user_id,
            },
        )

        order.order_number = order_number
        order.mh_order_id = order_id
        order.erp_location_code = loc
        order.erp_posted_at = now
        order.erp_post_status = "ORDERED"
        order.erp_post_error = None
        order.erp_bill_no = None
        self.session.flush()
        return {"order_id": order_id, "order_number": order_number, "status": "ORDERED", "already": False}

    def remove_web_order(self, order: Order) -> None:
        """Delete the matching MH_ORDER only when no BILLHDR exists."""
        if not self._table_exists("MH_ORDER"):
            return
        mh_id = order.mh_order_id
        order_number = str(order.order_number or "").strip()
        loc = order.erp_location_code or get_settings().oracle_location_code
        if not mh_id and order_number.startswith("ORD-"):
            mh_id = self.session.execute(
                text("SELECT ORDER_ID FROM MH_ORDER WHERE ORDER_NUMBER = :n FETCH FIRST 1 ROWS ONLY"),
                {"n": order_number},
            ).scalar()
        if not mh_id:
            return
        billed = self.session.execute(
            text(
                """
                SELECT ERP_BILLNO FROM MH_ORDER
                WHERE ORDER_ID = :oid FETCH FIRST 1 ROWS ONLY
                """
            ),
            {"oid": int(mh_id)},
        ).scalar()
        if billed:
            raise RuntimeError("This order already has a sales invoice and cannot be removed.")
        if self._table_exists("BILLHDR") and order_number:
            existing_bill = self.session.execute(
                text(
                    """
                    SELECT BILLNO FROM BILLHDR
                    WHERE NVL(DELFLAG, 'N') = 'N' AND ORDERNO = :orderno
                      AND (:loc = 0 OR LOCATIONCODE = :loc)
                    FETCH FIRST 1 ROWS ONLY
                    """
                ),
                {"orderno": order_number[:80], "loc": int(loc or 0)},
            ).scalar()
            if existing_bill:
                raise RuntimeError("This order already has a sales invoice and cannot be removed.")
        if self._table_exists("MH_INVENTORY_RESERVATION"):
            self.session.execute(
                text(
                    """
                    UPDATE MH_INVENTORY_RESERVATION
                    SET RESERVATION_STATUS = 'RELEASED', ORDER_ID = NULL
                    WHERE ORDER_ID = :oid
                    """
                ),
                {"oid": int(mh_id)},
            )
        self.session.execute(
            text("DELETE FROM MH_ORDER_STATUS_HISTORY WHERE ORDER_ID = :oid"),
            {"oid": int(mh_id)},
        )
        self.session.execute(
            text("DELETE FROM MH_ORDER_ITEM WHERE ORDER_ID = :oid"),
            {"oid": int(mh_id)},
        )
        deleted = self.session.execute(
            text("DELETE FROM MH_ORDER WHERE ORDER_ID = :oid"),
            {"oid": int(mh_id)},
        )
        if int(getattr(deleted, "rowcount", 0) or 0) == 0:
            raise RuntimeError("Website order was not found.")
        self.session.flush()
