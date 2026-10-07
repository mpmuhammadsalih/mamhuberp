export type AdReferral = {
  source_type?: string | null;
  source_id?: string | null;
  headline?: string | null;
  body?: string | null;
  image_url?: string | null;
  source_url?: string | null;
};

export type Conversation = {
  conversation_id: number;
  customer_id: number;
  customer_name: string;
  whatsapp_number: string;
  profile_image_url?: string | null;
  last_message_text?: string | null;
  last_message_at?: string | null;
  unread_count: number;
  assigned_user_id?: number | null;
  assigned_user_name?: string | null;
  status: string;
  is_starred?: boolean;
  ad_referral?: AdReferral | null;
};

export type Message = {
  id: number;
  conversation_id: number;
  whatsapp_message_id?: string | null;
  sender_type: string;
  message_type: string;
  message_text?: string | null;
  media_url?: string | null;
  latitude?: string | null;
  longitude?: string | null;
  status: string;
  created_at: string;
  error_message?: string | null;
  referral?: AdReferral | null;
  reply_to_id?: number | null;
  reply_to_text?: string | null;
  edited?: boolean;
};

export type Customer = {
  customer_id: number;
  customer_code?: string | null;
  customer_name: string;
  whatsapp_number: string;
  email?: string | null;
  address?: string | null;
  location_label?: string | null;
  customer_type: string;
  notes?: string | null;
  tags: string[];
  total_orders: number;
  total_purchases: number;
  last_purchase_date?: string | null;
  outstanding_balance: number;
  profile_image_url?: string | null;
  erp_customer_code?: string | null;
  source_channel?: string | null;
};

export type Product = {
  itemcode: string;
  itemname: string;
  barcode?: string | null;
  brand?: string | null;
  category?: string | null;
  retailprice: number;
  offer_price?: number | null;
  currentstock: number;
  image_url?: string | null;
  currency: string;
};

export type Order = {
  order_id: number;
  order_number: string;
  customer_id: number;
  order_date: string;
  subtotal: number;
  discount: number;
  delivery_charge: number;
  total_amount: number;
  payment_method: string;
  order_status: string;
  delivery_address?: string | null;
  mh_order_id?: number | null;
  erp_bill_no?: string | null;
  erp_post_status?: string | null;
  erp_post_error?: string | null;
  items: { item_id: number; itemcode: string; itemname: string; quantity: number; unit_price: number; line_total: number }[];
};

export type CartItem = {
  itemcode: string;
  itemname: string;
  quantity: number;
  unit_price: number;
  image_url?: string | null;
};

export type Agent = { user_id: number; full_name: string; role: string };
export type QuickReply = { reply_id: number; shortcut: string; title: string; body: string; is_active: boolean };
export type Template = { template_id: number; template_name: string; category?: string | null; language: string; status: string; body_text?: string | null };
export type Dashboard = {
  today_messages: number;
  active_conversations: number;
  unread_conversations: number;
  orders_today: number;
  whatsapp_orders_today: number;
  sales_today: number;
  pending_orders: number;
  resolved_conversations: number;
  conversations_by_day: { date: string; value: number }[];
  orders_by_day: { date: string; value: number }[];
  sales_by_day: { date: string; value: number }[];
  top_products: { itemname: string; qty: number }[];
  agent_performance: { name: string; messages_sent: number; assigned_chats: number }[];
};
