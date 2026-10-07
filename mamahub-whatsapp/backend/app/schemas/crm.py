from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field


class AdReferralOut(BaseModel):
    source_type: Optional[str] = None
    source_id: Optional[str] = None
    headline: Optional[str] = None
    body: Optional[str] = None
    image_url: Optional[str] = None
    source_url: Optional[str] = None


class ConversationOut(BaseModel):
    conversation_id: int
    customer_id: int
    customer_name: str
    whatsapp_number: str
    profile_image_url: Optional[str] = None
    last_message_text: Optional[str] = None
    last_message_at: Optional[datetime] = None
    unread_count: int = 0
    assigned_user_id: Optional[int] = None
    assigned_user_name: Optional[str] = None
    status: str
    is_starred: bool = False
    ad_referral: Optional[AdReferralOut] = None


class MessageOut(BaseModel):
    id: int
    conversation_id: int
    whatsapp_message_id: Optional[str] = None
    sender_type: str
    sender_id: Optional[int] = None
    message_type: str
    message_text: Optional[str] = None
    media_url: Optional[str] = None
    latitude: Optional[str] = None
    longitude: Optional[str] = None
    status: str
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    read_at: Optional[datetime] = None
    created_at: datetime
    payload: Optional[Any] = None
    error_message: Optional[str] = None
    referral: Optional[AdReferralOut] = None
    reply_to_id: Optional[int] = None
    reply_to_text: Optional[str] = None
    edited: bool = False


class StartConversationRequest(BaseModel):
    phone: str
    name: Optional[str] = None


class SendMessageRequest(BaseModel):
    text: Optional[str] = None
    message_type: str = "text"
    media_url: Optional[str] = None
    caption: Optional[str] = None
    template_name: Optional[str] = None
    language: str = "en"
    template_params: List[str] = Field(default_factory=list)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_name: Optional[str] = None
    location_address: Optional[str] = None
    product_text: Optional[str] = None
    interactive: Optional[dict] = None
    reply_to_id: Optional[int] = None


class EditMessageRequest(BaseModel):
    text: str


class StatusUpdateRequest(BaseModel):
    status: str


class AssignRequest(BaseModel):
    user_id: Optional[int] = None


class StarRequest(BaseModel):
    starred: Optional[bool] = None


class CustomerOut(BaseModel):
    customer_id: int
    customer_code: Optional[str] = None
    customer_name: str
    whatsapp_number: str
    email: Optional[str] = None
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_label: Optional[str] = None
    customer_type: str
    notes: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    total_orders: int = 0
    total_purchases: float = 0
    last_purchase_date: Optional[datetime] = None
    outstanding_balance: float = 0
    profile_image_url: Optional[str] = None
    erp_customer_code: Optional[str] = None
    source_channel: Optional[str] = None
    created_at: Optional[datetime] = None


class CustomerUpdate(BaseModel):
    customer_name: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_label: Optional[str] = None
    customer_type: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = None
    profile_image_url: Optional[str] = None


class CustomerNoteIn(BaseModel):
    note_text: str


class ProductOut(BaseModel):
    itemcode: str
    itemname: str
    barcode: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = None
    costprice: float = 0
    retailprice: float = 0
    wholesaleprice: float = 0
    offer_price: Optional[float] = None
    currentstock: float = 0
    image_url: Optional[str] = None
    active: bool = True
    currency: str = "QAR"


class OrderItemIn(BaseModel):
    itemcode: str
    itemname: str
    quantity: float = 1
    unit_price: float = 0


class OrderCreate(BaseModel):
    customer_id: int
    conversation_id: Optional[int] = None
    items: List[OrderItemIn]
    discount: float = 0
    delivery_charge: float = 0
    payment_method: str = "Cash"
    delivery_address: Optional[str] = None
    notes: Optional[str] = None
    send_confirmation: bool = True
    order_status: str = "Confirmed"


class OrderUpdate(BaseModel):
    order_status: Optional[str] = None
    payment_method: Optional[str] = None
    delivery_address: Optional[str] = None
    discount: Optional[float] = None
    delivery_charge: Optional[float] = None
    notes: Optional[str] = None


class OrderItemOut(BaseModel):
    item_id: int
    itemcode: str
    itemname: str
    quantity: float
    unit_price: float
    line_total: float


class OrderOut(BaseModel):
    order_id: int
    order_number: str
    customer_id: int
    conversation_id: Optional[int] = None
    order_date: datetime
    subtotal: float
    discount: float
    delivery_charge: float
    total_amount: float
    payment_method: str
    order_status: str
    delivery_address: Optional[str] = None
    notes: Optional[str] = None
    created_by: Optional[int] = None
    mh_order_id: Optional[int] = None
    erp_bill_no: Optional[str] = None
    erp_post_status: Optional[str] = None
    erp_post_error: Optional[str] = None
    items: List[OrderItemOut] = Field(default_factory=list)


class QuickReplyOut(BaseModel):
    reply_id: int
    shortcut: str
    title: str
    body: str
    is_active: bool


class QuickReplyIn(BaseModel):
    shortcut: str
    title: str
    body: str
    is_active: bool = True


class TemplateOut(BaseModel):
    template_id: int
    template_name: str
    category: Optional[str] = None
    language: str
    status: str
    header_text: Optional[str] = None
    body_text: Optional[str] = None
    footer_text: Optional[str] = None


class TemplateIn(BaseModel):
    template_name: str
    category: Optional[str] = None
    language: str = "en"
    status: str = "APPROVED"
    header_text: Optional[str] = None
    body_text: Optional[str] = None
    footer_text: Optional[str] = None


class SuggestReplyRequest(BaseModel):
    conversation_id: int
    latest_message: Optional[str] = None


class SuggestReplyResponse(BaseModel):
    suggestion: str
    products: List[ProductOut] = Field(default_factory=list)
    auto_send: bool = False


class DashboardOut(BaseModel):
    today_messages: int = 0
    active_conversations: int = 0
    unread_conversations: int = 0
    orders_today: int = 0
    whatsapp_orders_today: int = 0
    sales_today: float = 0
    pending_orders: int = 0
    resolved_conversations: int = 0
    conversations_by_day: List[dict] = Field(default_factory=list)
    orders_by_day: List[dict] = Field(default_factory=list)
    sales_by_day: List[dict] = Field(default_factory=list)
    top_products: List[dict] = Field(default_factory=list)
    agent_performance: List[dict] = Field(default_factory=list)


class CartItemOut(BaseModel):
    itemcode: str
    itemname: str
    quantity: float
    unit_price: float
    image_url: Optional[str] = None
    line_total: float = 0


class CartOut(BaseModel):
    conversation_id: int
    items: List[CartItemOut] = Field(default_factory=list)
    total: float = 0
    pending_sku: Optional[str] = None


class CartItemIn(BaseModel):
    itemcode: str
    itemname: str
    quantity: float = 1
    unit_price: float = 0
    image_url: Optional[str] = None


class CartPut(BaseModel):
    items: List[CartItemIn] = Field(default_factory=list)


class ProductPickIn(BaseModel):
    itemcode: str
    itemname: str
    retailprice: float = 0
    offer_price: Optional[float] = None
    image_url: Optional[str] = None
    currentstock: float = 0


class SendPickerRequest(BaseModel):
    products: List[ProductPickIn] = Field(default_factory=list)
    images_only: bool = False
