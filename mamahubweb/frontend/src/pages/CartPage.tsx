import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { CartLineItem } from '../components/cart/CartLineItem'
import { CartSummary } from '../components/CartSummary'
import { HOME_CONTAINER } from '../components/layout/homeLayout'
import { SeoHead } from '../components/seo/SeoHead'
import { IconCart, IconTicket } from '../components/icons/Icons'
import { useLocale } from '../i18n/LocaleContext'
import { deleteData, patchData, postData } from '../lib/api'
import { cartAddonsFor, cartProductItems, fetchCart, normalizeCart } from '../lib/queries/cart'
import { storefrontQueries } from '../lib/queries/storefront'
import { storage } from '../lib/storage'
import type { CartData } from '../types/api'

function syncCart(queryClient: ReturnType<typeof useQueryClient>, cart: CartData) {
  const normalized = normalizeCart(cart)
  if (normalized.guest_token) storage.setGuestCartToken(normalized.guest_token)
  queryClient.setQueryData(['cart'], normalized)
}

export function CartPage() {
  const { t } = useLocale()
  const queryClient = useQueryClient()
  const [coupon, setCoupon] = useState('')

  const { data: cart, isLoading } = useQuery({
    queryKey: ['cart'],
    queryFn: ({ signal }) => fetchCart({ signal }),
  })

  const { data: storefrontSettings } = useQuery(storefrontQueries.settings)

  const couponsEnabled = storefrontSettings?.coupons_enabled ?? false

  const updateQty = useMutation({
    mutationFn: ({ id, quantity }: { id: number; quantity: number }) =>
      patchData<CartData>(`/cart/items/${id}`, { quantity }),
    onMutate: async ({ id, quantity }) => {
      await queryClient.cancelQueries({ queryKey: ['cart'] })
      const previous = queryClient.getQueryData<CartData>(['cart'])
      if (previous) {
        const target = previous.items.find((item) => item.cart_item_id === id)
        const items = previous.items.map((item) => {
          const linked =
            item.cart_item_id === id ||
            Boolean(
              target &&
                !target.parent_item_code &&
                item.parent_item_code === target.item_code,
            )
          return linked
            ? { ...item, quantity, line_total: item.unit_price * quantity }
            : item
        })
        const subtotal = items.reduce((sum, item) => sum + item.line_total, 0)
        queryClient.setQueryData<CartData>(['cart'], {
          ...previous,
          items,
          summary: {
            ...previous.summary,
            subtotal,
            grand_total: subtotal - previous.summary.discount_total + previous.summary.tax_total,
            item_count: items.reduce((sum, item) => sum + item.quantity, 0),
          },
        })
      }
      return { previous }
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) queryClient.setQueryData(['cart'], context.previous)
    },
    onSuccess: (data) => {
      syncCart(queryClient, data)
    },
  })

  const removeItem = useMutation({
    mutationFn: (id: number) => deleteData<CartData>(`/cart/items/${id}`),
    onSuccess: (data) => {
      syncCart(queryClient, data)
    },
  })

  const applyCoupon = useMutation({
    mutationFn: (code: string) =>
      postData<{ cart: CartData }>('/cart/coupon', { coupon_code: code }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['cart'] })
    },
  })

  const updatingId = updateQty.isPending ? updateQty.variables?.id : null

  if (isLoading) {
    return (
      <div className={`${HOME_CONTAINER} py-16 text-center font-catalog text-slate-500`}>
        {t.cart.loading}
      </div>
    )
  }

  const currency = cart?.summary.currency_code
  const productItems = cartProductItems(cart?.items)
  const hasItems = productItems.length > 0

  return (
    <div className="min-h-screen bg-[#F8F8FA] pb-24 lg:pb-16">
      <SeoHead title={t.cart.title} noIndex />
      <div className={`${HOME_CONTAINER} py-5 lg:py-10`}>
        <div className="mb-5 flex items-start gap-3 lg:mb-8">
          <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-white text-brand-accent shadow-sm ring-1 ring-brand-accent/15">
            <IconCart size={24} />
          </span>
          <div>
            <h1 className="font-display text-2xl font-bold text-[#1A1C2E] sm:text-[2rem]">{t.cart.title}</h1>
            <p className="mt-0.5 hidden font-catalog text-[15px] text-slate-500 sm:block">
              {t.cart.subtitle}
            </p>
          </div>
        </div>

        <div className="grid gap-6 lg:grid-cols-3 lg:items-start lg:gap-8">
          <div className="space-y-4 lg:col-span-2">
            {!hasItems ? (
              <div className="rounded-3xl bg-white px-6 py-14 text-center shadow-sm ring-1 ring-black/[0.04]">
                <p className="font-catalog text-slate-500">{t.cart.empty}</p>
                <Link
                  to="/products"
                  className="mt-4 inline-flex rounded-full bg-brand-accent px-6 py-2.5 text-sm font-bold text-white transition hover:bg-brand-accent-hover"
                >
                  {t.shared.continueShopping}
                </Link>
              </div>
            ) : (
              <div className="overflow-hidden rounded-2xl shadow-sm ring-1 ring-black/[0.04] lg:rounded-3xl">
                {productItems.map((item, index) => (
                  <CartLineItem
                    key={item.cart_item_id}
                    item={item}
                    extras={cartAddonsFor(cart!.items, item.item_code)}
                    index={index}
                    currency={currency}
                    disabled={updatingId === item.cart_item_id || removeItem.isPending}
                    onUpdateQty={(quantity) => {
                      if (quantity !== item.quantity) {
                        updateQty.mutate({ id: item.cart_item_id, quantity })
                      }
                    }}
                    onRemove={() => removeItem.mutate(item.cart_item_id)}
                  />
                ))}

                {couponsEnabled && (
                  <form
                    className="flex flex-col gap-3 border-t border-gray-100 bg-white p-4 sm:flex-row sm:items-center sm:gap-3 sm:p-5"
                    onSubmit={(e) => {
                      e.preventDefault()
                      if (coupon.trim()) applyCoupon.mutate(coupon.trim())
                    }}
                  >
                    <div className="flex min-w-0 flex-1 items-center gap-3">
                      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-brand-cream-alt text-brand-accent">
                        <IconTicket size={20} />
                      </span>
                      <div className="min-w-0">
                        <p className="font-display text-sm font-bold text-[#1A1C2E]">{t.cart.couponPrompt}</p>
                        <input
                          value={coupon}
                          onChange={(e) => setCoupon(e.target.value)}
                          placeholder={t.cart.couponPlaceholder}
                          className="mt-0.5 w-full bg-transparent font-catalog text-sm text-gray-800 outline-none placeholder:text-gray-400"
                        />
                      </div>
                    </div>
                    <button
                      type="submit"
                      disabled={applyCoupon.isPending || !coupon.trim()}
                      className="shrink-0 rounded-full bg-brand-accent px-6 py-2.5 text-sm font-bold text-white transition hover:bg-brand-accent-hover disabled:opacity-50 sm:px-8"
                    >
                      {t.shared.apply}
                    </button>
                  </form>
                )}
              </div>
            )}
          </div>

          <div className="space-y-4">
            <CartSummary cart={cart} />
          </div>
        </div>
      </div>
    </div>
  )
}
