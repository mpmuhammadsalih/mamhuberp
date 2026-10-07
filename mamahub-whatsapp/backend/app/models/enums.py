"""Shared domain enumerations."""
from __future__ import annotations

from enum import Enum


class ConversationStatus(str, Enum):
    OPEN = "OPEN"
    PENDING = "PENDING"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class SenderType(str, Enum):
    CUSTOMER = "CUSTOMER"
    AGENT = "AGENT"
    SYSTEM = "SYSTEM"
    AI = "AI"


class MessageStatus(str, Enum):
    RECEIVED = "RECEIVED"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    READ = "READ"
    FAILED = "FAILED"
    DELETED = "DELETED"


class MessageType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"
    LOCATION = "location"
    CONTACTS = "contacts"
    INTERACTIVE = "interactive"
    TEMPLATE = "template"
    PRODUCT = "product"
    ORDER = "order"
    STICKER = "sticker"
    UNKNOWN = "unknown"


class OrderStatus(str, Enum):
    DRAFT = "Draft"
    CONFIRMED = "Confirmed"
    PROCESSING = "Processing"
    READY = "Ready"
    OUT_FOR_DELIVERY = "Out for Delivery"
    DELIVERED = "Delivered"
    CANCELLED = "Cancelled"


class PaymentMethod(str, Enum):
    CASH = "Cash"
    CARD = "Card"
    TAP = "Tap"
    BANK_TRANSFER = "Bank Transfer"
    OTHER = "Other"
