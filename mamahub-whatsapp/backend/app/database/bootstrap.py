"""Create WA_* tables and seed roles, admin, settings, and sample content."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import logger
from app.core.security import hash_password
from app.database.base import Base
from app.database.session import get_engine, get_session_factory
from app.models import (  # noqa: F401
    AuditLog,
    Conversation,
    ConversationAssignment,
    ConversationCartItem,
    ConversationStar,
    Customer,
    CustomerNote,
    CustomerTag,
    Message,
    MessageAttachment,
    Order,
    OrderItem,
    PushSubscription,
    QuickReply,
    RoleRecord,
    Setting,
    User,
    WhatsAppTemplate,
)

SEED_ROLES = [
    ("SUPER_ADMIN", "Super Admin", "Full access"),
    ("ADMIN", "Admin", "Users, settings, templates, reports"),
    ("SALES", "Sales", "Chats, products, orders, customers"),
    ("CUSTOMER_SERVICE", "Customer Service", "Chats, customers, product search"),
]

SEED_REPLIES = [
    ("/location", "Location", "Please share your location so we can confirm delivery."),
    ("/delivery", "Delivery", "Yes, we provide delivery across Qatar. Please share your location."),
    ("/payment", "Payment", "We accept cash on delivery and card payments."),
    ("/price", "Price", "Please share the product name or barcode and I will check the price and stock."),
    ("/thanks", "Thanks", "Thank you for contacting MamaHub! We are happy to help."),
]


def _column_exists(session: Session, table_name: str, column_name: str) -> bool:
    row = session.execute(
        text(
            """
            SELECT COUNT(*) AS CNT FROM USER_TAB_COLUMNS
            WHERE TABLE_NAME = :table_name AND COLUMN_NAME = :column_name
            """
        ),
        {"table_name": table_name.upper(), "column_name": column_name.upper()},
    ).scalar()
    return int(row or 0) > 0


def _ensure_column(session: Session, table_name: str, column_name: str, ddl: str) -> None:
    if not _table_exists(session, table_name) or _column_exists(session, table_name, column_name):
        return
    session.execute(text(f"ALTER TABLE {table_name} ADD {ddl}"))
    logger.info("Added %s.%s", table_name, column_name)


def _table_exists(session: Session, table_name: str) -> bool:
    row = session.execute(
        text("SELECT COUNT(*) AS CNT FROM USER_TABLES WHERE TABLE_NAME = :name"),
        {"name": table_name.upper()},
    ).scalar()
    return int(row or 0) > 0


def _upsert_setting(session: Session, key: str, value: str, group: str) -> None:
    existing = session.execute(
        text("SELECT SETTING_ID FROM WA_SETTINGS WHERE SETTING_KEY = :key"),
        {"key": key},
    ).scalar()
    if existing:
        return
    session.execute(
        text(
            """
            INSERT INTO WA_SETTINGS (SETTING_KEY, SETTING_VALUE, SETTING_GROUP, UPDATED_AT)
            VALUES (:key, :value, :grp, SYSDATE)
            """
        ),
        {"key": key, "value": value, "grp": group},
    )


def bootstrap_schema() -> None:
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    logger.info("Oracle schema ensure complete for WA_* tables")

    settings = get_settings()
    factory = get_session_factory()
    session = factory()
    try:
        if _table_exists(session, "WA_ROLES"):
            for code, name, desc in SEED_ROLES:
                exists = session.execute(
                    text("SELECT ROLE_ID FROM WA_ROLES WHERE ROLE_CODE = :code"),
                    {"code": code},
                ).scalar()
                if not exists:
                    session.execute(
                        text(
                            """
                            INSERT INTO WA_ROLES (ROLE_CODE, ROLE_NAME, DESCRIPTION, CREATED_AT)
                            VALUES (:code, :name, :desc, SYSDATE)
                            """
                        ),
                        {"code": code, "name": name, "desc": desc},
                    )

        admin_count = session.execute(text("SELECT COUNT(*) FROM WA_USERS")).scalar()
        if int(admin_count or 0) == 0:
            session.execute(
                text(
                    """
                    INSERT INTO WA_USERS (
                        USERNAME, EMAIL, FULL_NAME, PASSWORD_HASH, ROLE, IS_ACTIVE, CREATED_AT, UPDATED_AT
                    ) VALUES (
                        :username, :email, :full_name, :password_hash, 'SUPER_ADMIN', 1, SYSDATE, SYSDATE
                    )
                    """
                ),
                {
                    "username": settings.bootstrap_admin_username,
                    "email": settings.bootstrap_admin_email,
                    "full_name": settings.bootstrap_admin_name,
                    "password_hash": hash_password(settings.bootstrap_admin_password),
                },
            )
            logger.info("Seeded bootstrap SUPER_ADMIN user")

        for shortcut, title, body in SEED_REPLIES:
            exists = session.execute(
                text("SELECT REPLY_ID FROM WA_QUICK_REPLIES WHERE SHORTCUT = :shortcut"),
                {"shortcut": shortcut},
            ).scalar()
            if not exists:
                session.execute(
                    text(
                        """
                        INSERT INTO WA_QUICK_REPLIES (SHORTCUT, TITLE, BODY, IS_ACTIVE, CREATED_AT, UPDATED_AT)
                        VALUES (:shortcut, :title, :body, 1, SYSDATE, SYSDATE)
                        """
                    ),
                    {"shortcut": shortcut, "title": title, "body": body},
                )

        exists_tpl = session.execute(
            text("SELECT TEMPLATE_ID FROM WA_WHATSAPP_TEMPLATES WHERE TEMPLATE_NAME = :n"),
            {"n": "order_confirmed"},
        ).scalar()
        if not exists_tpl:
            session.execute(
                text(
                    """
                    INSERT INTO WA_WHATSAPP_TEMPLATES (
                        TEMPLATE_NAME, CATEGORY, LANGUAGE, STATUS, HEADER_TEXT, BODY_TEXT, FOOTER_TEXT, CREATED_AT, UPDATED_AT
                    ) VALUES (
                        'order_confirmed', 'UTILITY', 'en', 'APPROVED',
                        'Order confirmed',
                        'Hi {{1}}! Your MamaHub order {{2}} is confirmed. Total: {{3}}. Track: {{4}}',
                        'MamaHub Trading',
                        SYSDATE, SYSDATE
                    )
                    """
                )
            )

        _ensure_column(session, "WA_ORDERS", "MH_ORDER_ID", "MH_ORDER_ID NUMBER")
        _ensure_column(session, "WA_ORDERS", "ERP_BILL_NO", "ERP_BILL_NO VARCHAR2(30)")
        _ensure_column(session, "WA_ORDERS", "ERP_LOCATION_CODE", "ERP_LOCATION_CODE NUMBER")
        _ensure_column(session, "WA_ORDERS", "ERP_RESET_NO", "ERP_RESET_NO NUMBER")
        _ensure_column(session, "WA_ORDERS", "ERP_POSTED_AT", "ERP_POSTED_AT DATE")
        _ensure_column(session, "WA_ORDERS", "ERP_POST_STATUS", "ERP_POST_STATUS VARCHAR2(20)")
        _ensure_column(session, "WA_ORDERS", "ERP_POST_ERROR", "ERP_POST_ERROR VARCHAR2(500)")
        _ensure_column(session, "WA_CONVERSATIONS", "CART_PENDING_SKU", "CART_PENDING_SKU VARCHAR2(80)")
        _ensure_column(session, "WA_CONVERSATIONS", "CART_OFFER_JSON", "CART_OFFER_JSON VARCHAR2(2000)")
        _ensure_column(session, "WA_CONVERSATIONS", "AD_SOURCE_TYPE", "AD_SOURCE_TYPE VARCHAR2(20)")
        _ensure_column(session, "WA_CONVERSATIONS", "AD_SOURCE_ID", "AD_SOURCE_ID VARCHAR2(80)")
        _ensure_column(session, "WA_CONVERSATIONS", "AD_HEADLINE", "AD_HEADLINE VARCHAR2(240)")
        _ensure_column(session, "WA_CONVERSATIONS", "AD_BODY", "AD_BODY VARCHAR2(500)")
        _ensure_column(session, "WA_CONVERSATIONS", "AD_IMAGE_URL", "AD_IMAGE_URL VARCHAR2(2000)")
        _ensure_column(session, "WA_CONVERSATIONS", "AD_SOURCE_URL", "AD_SOURCE_URL VARCHAR2(2000)")
        from app.integrations.whatsapp.processor import backfill_ad_referrals

        filled = backfill_ad_referrals(session)
        if filled:
            logger.info("Backfilled Facebook ad referrals on %s chats", filled)

        _upsert_setting(session, "company_name", settings.company_name, "company")
        _upsert_setting(session, "company_currency", settings.company_currency, "company")
        _upsert_setting(session, "company_country", settings.company_country, "company")
        _upsert_setting(session, "ai_auto_reply", "0", "ai")
        _upsert_setting(session, "ai_pause_when_human", "0", "ai")
        _upsert_setting(session, "ai_agent_name", "MamaHub", "ai")
        _upsert_setting(session, "ai_model", settings.openai_model, "ai")
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
