import type { QueryClient } from '@tanstack/react-query'
import type { CartData } from '../types/api'
import { normalizeCart } from './queries/cart'
import { storage } from './storage'

const EMPTY_CART: CartData = {
  cart_id: 0,
  items: [],
  summary: {
    subtotal: 0,
    discount_total: 0,
    tax_total: 0,
    grand_total: 0,
    item_count: 0,
    currency_code: 'QAR',
  },
}

export function syncCartCache(queryClient: QueryClient, cart: CartData) {
  const normalized = normalizeCart(cart)
  if (normalized.guest_token) storage.setGuestCartToken(normalized.guest_token)
  queryClient.setQueryData(['cart'], normalized)
}

export function applyOptimisticAddToCart(
  queryClient: QueryClient,
  itemCode: number,
  quantity: number,
  unitPrice: number,
  parentItemCode?: number,
): { previous: CartData | undefined } {
  const previous = queryClient.getQueryData<CartData>(['cart'])
  const base = previous ?? EMPTY_CART
  const parent = parentItemCode ?? null
  const existing = base.items.find(
    (item) => item.item_code === itemCode && (item.parent_item_code ?? null) === parent,
  )

  let items: CartData['items']
  if (existing) {
    const nextQty = existing.quantity + quantity
    items = base.items.map((item) =>
      item.item_code === itemCode && (item.parent_item_code ?? null) === parent
        ? { ...item, quantity: nextQty, line_total: item.unit_price * nextQty }
        : item,
    )
  } else {
    items = [
      ...base.items,
      {
        cart_item_id: -itemCode,
        item_code: itemCode,
        quantity,
        unit_price: unitPrice,
        line_total: unitPrice * quantity,
        parent_item_code: parent,
        is_addon: Boolean(parent),
      },
    ]
  }

  const subtotal = items.reduce((sum, item) => sum + item.line_total, 0)
  const discount = base.summary.discount_total
  const tax = base.summary.tax_total

  queryClient.setQueryData<CartData>(['cart'], normalizeCart({
    ...base,
    items,
    summary: {
      ...base.summary,
      subtotal,
      grand_total: Math.max(subtotal - discount + tax, 0),
      item_count: items.reduce((sum, item) => sum + item.quantity, 0),
    },
  }))

  return { previous }
}
