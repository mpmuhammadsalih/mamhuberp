export interface ApiResponse<T> {
  success: boolean
  message: string
  data: T
  meta?: {
    page?: number
    page_size?: number
    total_records?: number
    total_pages?: number
  }
}

export interface Product {
  item_code: number
  item_name?: string
  item_name_ar?: string | null
  description?: string
  description_ar?: string | null
  retail_price: number
  offer_price?: number | null
  discount_percent?: number | null
  wholesale_price?: number
  current_stock: number
  brand_name?: string
  brand_name_ar?: string | null
  brand_code?: number
  category_code?: number
  category_name?: string
  primary_image_url?: string | null
  units_sold?: number
  images?: Array<{ id?: number; image_url?: string | null; image_path?: string | null; primary?: boolean }>
  specifications?: Array<{ label: string; value: string }>
  specifications_ar?: Array<{ label: string; value: string }> | null
  warehouse_stock?: Array<{ warehouse_id: number; qty: number }>
  seo_title?: string | null
  seo_description?: string | null
  show_on_web?: boolean
  is_featured?: boolean
  is_addon?: boolean
  addon_type?: string | null
  addon_code?: string | null
  addon_enabled?: boolean
  addons?: Product[]
}

export interface CartLine {
  cart_item_id: number
  item_code: number
  quantity: number
  unit_price: number
  line_total: number
  parent_item_code?: number | null
  is_addon?: boolean
  product?: Product
}

export interface CartData {
  cart_id: number
  guest_token?: string
  items: CartLine[]
  summary: {
    subtotal: number
    discount_total: number
    tax_total: number
    grand_total: number
    item_count: number
    currency_code: string
  }
}

export interface OrderSummary {
  order_id: number
  order_number: string
  order_status: string
  grand_total: number
  currency_code: string
  item_count?: number
  fulfillment_type?: string
  payment_status?: string
  created_at?: string
}

export interface GiftWrapOption {
  code: string
  label: string
  fee: number
  enabled?: boolean
}

export interface GiftWrapSelection {
  options: GiftWrapOption[]
  selected_code: string
  label: string
  fee: number
}

export interface CheckoutPricing {
  subtotal: number
  discount_total: number
  loyalty_discount?: number
  delivery_fee: number
  gift_wrap_fee?: number
  gift_wrap_code?: string
  gift_wrap_label?: string
  tax_total: number
  grand_total: number
  currency_code: string
}

export interface OrderDetail extends OrderSummary {
  subtotal?: number
  discount_total?: number
  tax_total?: number
  delivery_fee?: number
  gift_wrap_fee?: number
  gift_wrap?: { label?: string; fee?: number } | null
  coupon_code?: string | null
  customer_notes?: string | null
  items?: Array<{
    order_item_id?: number
    item_code: number
    item_name?: string
    primary_image_url?: string | null
    quantity: number
    unit_price: number
    line_total: number
  }>
  fulfillment_type?: string
  payment_status?: string
  status_history?: Array<{
    order_status?: string
    status?: string
    status_notes?: string | null
    notes?: string | null
    created_at?: string
  }>
  address_snapshot?: Record<string, string>
}

export interface Address {
  address_id: number
  address_title: string
  address_type: string
  street: string
  city: string
  country: string
  zone?: string
  area?: string
  latitude?: number | null
  longitude?: number | null
  is_default: boolean
}

export interface UserProfile {
  user_id: number
  email: string
  first_name: string
  last_name: string
  mobile?: string
  preferred_language?: string
  roles?: string[]
}

export interface WishlistItem {
  wishlist_item_id: number
  item_code: number
  product?: Product
}

export interface ReviewSummary {
  avg_rating: number
  review_count: number
}

export interface Review {
  review_id: number
  rating: number
  title?: string
  review_text?: string
  first_name?: string
  last_name?: string
  is_verified_purchase?: number
  created_at?: string
}

export interface CmsFaqItem {
  question: string
  answer: string
}

export interface CmsFaqSection {
  title: string
  items: CmsFaqItem[]
}

export interface CmsContactCard {
  title: string
  lines: string[]
}

export interface CmsPageMeta {
  sections?: CmsFaqSection[]
  cards?: CmsContactCard[]
  form_enabled?: boolean
  form_subjects?: string[]
  success_message?: string
}

export interface CmsPageListItem {
  page_title: string
  slug: string
  page_type?: string
  meta_description?: string
  sort_order?: number
}

export interface CmsPage {
  page_title: string
  slug: string
  page_type?: string
  content_html?: string
  meta_description?: string
  meta?: CmsPageMeta
}

export interface NotificationItem {
  notification_id: number
  notification_type?: string
  title: string
  body?: string
  is_read: number | boolean
  created_at?: string
  ref_entity?: string
  ref_entity_id?: number | null
}

export interface InboxConversation {
  conversation_id: number
  display_name: string
  last_text?: string
  unread_count: number
  updated_at?: string | null
}

export interface InboxMessage {
  message_id: number
  conversation_id: number
  is_own: boolean
  from_support: boolean
  message_text: string
  image_url?: string | null
  file_url?: string | null
  file_name?: string | null
  file_mime?: string | null
  edited?: boolean
  created_at?: string | null
}

export interface InboxUnread {
  chat: number
  notifications: number
  total: number
}

export interface InboxLatest {
  unread: InboxUnread
  notification?: {
    notification_id: number
    title: string
    body?: string
    notification_type?: string
    is_read?: boolean
  } | null
  chat?: {
    conversation_id: number
    last_text?: string
    updated_at?: string | null
    unread_count?: number
  } | null
}
