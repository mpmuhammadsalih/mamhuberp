import { getData } from '../api'
import { storage } from '../storage'
import type { CartData, CartLine } from '../../types/api'

export function isCartAddon(item: CartLine): boolean {
  return Boolean(item.parent_item_code || item.is_addon)
}

export function cartProductItems(items: CartLine[] | undefined): CartLine[] {
  return (items ?? []).filter((item) => !isCartAddon(item))
}

export function cartAddonsFor(items: CartLine[] | undefined, parentItemCode: number): CartLine[] {
  return (items ?? []).filter((item) => item.parent_item_code === parentItemCode)
}

export function cartLineCombinedTotal(item: CartLine, extras: CartLine[] = []): number {
  return extras.reduce((sum, extra) => sum + extra.line_total, item.line_total)
}

/** Keep summary.item_count aligned with product quantities, not wrap extras. */
export function normalizeCart(data: CartData): CartData {
  const items = data.items ?? []
  const itemCount = cartProductItems(items).reduce((sum, item) => sum + item.quantity, 0)
  return {
    ...data,
    items,
    summary: {
      ...data.summary,
      item_count: itemCount,
    },
  }
}

export function getCartItemCount(cart: CartData | undefined): number {
  if (!cart) return 0
  if (Array.isArray(cart.items)) {
    return cartProductItems(cart.items).reduce((sum, item) => sum + item.quantity, 0)
  }
  return cart.summary?.item_count ?? 0
}

/** Shared cart fetch — persists guest token and supports query cancellation. */
export async function fetchCart({ signal }: { signal?: AbortSignal } = {}): Promise<CartData> {
  const data = await getData<CartData>('/cart', undefined, { signal })
  const cart = normalizeCart(data)
  if (cart.guest_token) storage.setGuestCartToken(cart.guest_token)
  return cart
}
