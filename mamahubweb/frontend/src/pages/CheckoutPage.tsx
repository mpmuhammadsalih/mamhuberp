import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { PAGE_CONTAINER } from '../components/layout/homeLayout'
import { SeoHead } from '../components/seo/SeoHead'
import { CartSummary } from '../components/CartSummary'
import { IconCashOnDelivery, OnlinePaymentBadges } from '../components/checkout/PaymentMethodIcons'
import { AddAddressForm } from '../components/checkout/AddAddressForm'
import { IconLock, IconMapPin, IconTicket, IconTruck } from '../components/icons/Icons'
import { useLocale } from '../i18n/LocaleContext'
import { useFormatMoney } from '../i18n/useFormatMoney'
import { getApiErrorMessage, getData, postData } from '../lib/api'
import { fetchCart, getCartItemCount, normalizeCart } from '../lib/queries/cart'
import { storage } from '../lib/storage'
import type {
  Address,
  CartData,
  CheckoutPricing,
  OrderSummary,
} from '../types/api'

interface CheckoutReview {
  cart: CartData
  fulfillment: Record<string, unknown>
  pricing: CheckoutPricing
  loyalty?: {
    points_balance: number
    max_redeemable_points: number
    points_redeemed: number
    loyalty_discount: number
  }
  payment_methods?: Array<{ code: string; label: string; description: string }>
  coupons_enabled?: boolean
}

type FulfillmentMode = 'delivery' | 'pickup'

export function CheckoutPage() {
  const { t } = useLocale()
  const formatMoney = useFormatMoney()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const loggedIn = storage.hasSession()
  const [mode, setMode] = useState<FulfillmentMode>('pickup')
  const [coupon, setCoupon] = useState('')
  const [paymentMethod, setPaymentMethod] = useState('COD')
  const [addressId, setAddressId] = useState<number | null>(null)
  const [storeId, setStoreId] = useState<number | null>(null)
  const [loyaltyPoints, setLoyaltyPoints] = useState('')
  const [checkoutError, setCheckoutError] = useState<string | null>(null)
  const [showAddAddress, setShowAddAddress] = useState(false)
  const pickupAutoAppliedRef = useRef(false)
  const orderPlacedRef = useRef(false)

  const { data: cart, isLoading: cartLoading } = useQuery({
    queryKey: ['cart'],
    queryFn: ({ signal }) => fetchCart({ signal }),
    refetchOnMount: 'always',
  })

  const cartCount = getCartItemCount(cart)

  const {
    data: review,
    refetch,
    isLoading: reviewLoading,
    isError: reviewError,
    error: reviewErrorDetail,
  } = useQuery({
    queryKey: ['checkout-review'],
    queryFn: async (): Promise<CheckoutReview> => {
      await postData('/checkout/start')
      return getData<CheckoutReview>('/checkout/review')
    },
    enabled: loggedIn && cartCount > 0,
  })

  const fulfillmentType = review?.fulfillment?.type as string | undefined

  useEffect(() => {
    if (orderPlacedRef.current || cartLoading || !cart) return
    if (cartCount === 0) navigate('/', { replace: true })
  }, [cart, cartCount, cartLoading, navigate])

  useEffect(() => {
    if (!reviewError || !reviewErrorDetail) return
    const message = getApiErrorMessage(reviewErrorDetail).toLowerCase()
    if (message.includes('cart is empty')) {
      void queryClient.invalidateQueries({ queryKey: ['cart'] })
    }
  }, [queryClient, reviewError, reviewErrorDetail])

  const { data: addresses = [], isLoading: addressesLoading } = useQuery({
    queryKey: ['addresses'],
    queryFn: () => getData<Address[]>('/addresses'),
    enabled: loggedIn,
  })

  const { data: zones = [] } = useQuery({
    queryKey: ['delivery-zones'],
    queryFn: () =>
      getData<Array<{ delivery_zone_id: number; zone_name: string; delivery_fee: number }>>(
        '/delivery/zones',
      ),
  })

  const { data: slots = [] } = useQuery({
    queryKey: ['delivery-slots'],
    queryFn: () =>
      getData<Array<{ delivery_slot_id: number; slot_label: string }>>('/delivery/slots'),
  })

  const {
    data: stores = [],
    isLoading: storesLoading,
    isError: storesError,
    error: storesErrorDetail,
    refetch: refetchStores,
  } = useQuery({
    queryKey: ['pickup-stores'],
    queryFn: () =>
      getData<
        Array<{
          pickup_store_id: number
          store_name: string
          address_line?: string | null
          city?: string | null
        }>
      >('/pickup/stores'),
    staleTime: 60_000,
  })

  const defaultAddress = addresses.find((a) => a.is_default) || addresses[0]
  const defaultZoneId = zones[0]?.delivery_zone_id
  const defaultSlotId = slots[0]?.delivery_slot_id

  const setDelivery = useMutation({
    mutationFn: (payload?: { address_id: number }) =>
      postData<{ fulfillment: CheckoutReview['fulfillment'] }>('/checkout/delivery', {
        address_id: payload?.address_id ?? addressId ?? defaultAddress?.address_id,
        delivery_zone_id: defaultZoneId,
        delivery_slot_id: defaultSlotId,
      }),
    onSuccess: (data) => {
      setCheckoutError(null)
      queryClient.setQueryData(['checkout-review'], (old: CheckoutReview | undefined) =>
        old ? { ...old, fulfillment: data.fulfillment } : old,
      )
      void refetch()
    },
    onError: (error) => setCheckoutError(getApiErrorMessage(error)),
  })

  const setPickup = useMutation({
    mutationFn: (pickup_store_id: number) =>
      postData<{ fulfillment: CheckoutReview['fulfillment'] }>('/checkout/pickup', {
        pickup_store_id,
      }),
    onSuccess: (data) => {
      setCheckoutError(null)
      queryClient.setQueryData(['checkout-review'], (old: CheckoutReview | undefined) =>
        old ? { ...old, fulfillment: data.fulfillment } : old,
      )
    },
    onError: (error) => setCheckoutError(getApiErrorMessage(error)),
  })

  useEffect(() => {
    pickupAutoAppliedRef.current = false
  }, [loggedIn, mode])

  useEffect(() => {
    if (
      !loggedIn ||
      mode !== 'pickup' ||
      stores.length === 0 ||
      fulfillmentType === 'PICKUP' ||
      pickupAutoAppliedRef.current
    ) {
      return
    }
    pickupAutoAppliedRef.current = true
    const firstStoreId = stores[0].pickup_store_id
    setStoreId(firstStoreId)
    setPickup.mutate(firstStoreId)
  }, [loggedIn, mode, stores, fulfillmentType, setPickup.mutate])

  useEffect(() => {
    if (mode === 'delivery' && !addressesLoading && addresses.length === 0) {
      setShowAddAddress(true)
    }
  }, [mode, addresses.length, addressesLoading])

  useEffect(() => {
    if (mode !== 'delivery' || fulfillmentType === 'DELIVERY') return
    if (defaultAddress && !addressId) setAddressId(defaultAddress.address_id)
  }, [mode, fulfillmentType, defaultAddress, addressId])

  const applyCoupon = useMutation({
    mutationFn: () => postData('/checkout/coupon', { coupon_code: coupon }),
    onSuccess: () => refetch(),
  })

  const applyLoyalty = useMutation({
    mutationFn: () => postData('/checkout/loyalty-points', { points: Number(loyaltyPoints) }),
    onSuccess: () => refetch(),
  })

  const confirm = useMutation({
    mutationFn: async () => {
      setCheckoutError(null)

      const body: Record<string, unknown> = {
        payment_method: paymentMethod,
      }

      if (mode === 'pickup') {
        const pickupId = storeId ?? stores[0]?.pickup_store_id
        if (!pickupId) throw new Error(t.checkout.errNoPickup)
        body.pickup_store_id = pickupId
      } else {
        const addr = addressId ?? defaultAddress?.address_id
        if (!addr) throw new Error(t.checkout.errNoAddress)
        if (!defaultZoneId) throw new Error(t.checkout.errNoZone)
        if (!defaultSlotId) throw new Error(t.checkout.errNoSlot)
        body.address_id = addr
        body.delivery_zone_id = defaultZoneId
        body.delivery_slot_id = defaultSlotId
      }

      if (paymentMethod === 'TAP') {
        const tap = await postData<{ redirect_url: string }>('/checkout/payment/tap/init', body)
        if (!tap.redirect_url) throw new Error(t.checkout.errPayment)
        window.location.href = tap.redirect_url
        return null
      }

      return postData<OrderSummary>('/checkout/confirm', body, 60_000)
    },
    onSuccess: (order) => {
      if (!order) return
      orderPlacedRef.current = true
      queryClient.removeQueries({ queryKey: ['checkout-review'] })
      navigate(`/order-success/${order.order_id}`, {
        replace: true,
        state: {
          orderNumber: order.order_number,
          grandTotal: order.grand_total,
          currencyCode: order.currency_code,
          itemCount: order.item_count,
          fulfillmentType: mode === 'pickup' ? 'PICKUP' : 'DELIVERY',
        },
      })
      queryClient.setQueryData(['cart'], (old: CartData | undefined) =>
        old
          ? normalizeCart({
              ...old,
              items: [],
              summary: {
                ...old.summary,
                item_count: 0,
                subtotal: 0,
                grand_total: 0,
                discount_total: 0,
              },
            })
          : old,
      )
    },
    onError: (error) => setCheckoutError(getApiErrorMessage(error)),
  })

  const methods = review?.payment_methods ?? [
    { code: 'COD', label: t.checkout.codLabel, description: t.checkout.codDesc },
    {
      code: 'TAP',
      label: t.checkout.tapLabel,
      description: t.checkout.tapDesc,
    },
  ]

  if (!loggedIn) {
    return (
      <CheckoutShell title={t.checkout.title}>
        <div className="mx-auto max-w-lg rounded-[2rem] bg-white px-6 py-10 text-center shadow-sm ring-1 ring-brand-border/50 sm:px-10">
          <p className="font-catalog text-[15px] leading-relaxed text-slate-600">{t.checkout.signInPrompt}</p>
          <Link
            to="/login?redirect=/checkout"
            className="mt-6 inline-flex h-12 items-center justify-center rounded-full bg-brand-accent px-8 text-sm font-bold text-white transition hover:bg-brand-accent-hover"
          >
            {t.checkout.signInToContinue}
          </Link>
          <Link to="/cart" className="mt-4 block text-sm font-semibold text-slate-500 hover:text-brand-accent">
            {t.shared.backToCart}
          </Link>
        </div>
        {cart && (
          <div className="mx-auto mt-8 max-w-lg">
            <CartSummary cart={cart} />
          </div>
        )}
      </CheckoutShell>
    )
  }

  if (cartLoading || (loggedIn && reviewLoading && !review)) {
    return (
      <CheckoutShell title={t.checkout.title}>
        <div className="mx-auto max-w-lg rounded-[2rem] bg-white px-6 py-12 text-center shadow-sm ring-1 ring-brand-border/50">
          <span className="mx-auto block h-12 w-12 animate-spin rounded-full border-4 border-brand-tint border-t-brand-accent" />
          <p className="mt-5 font-catalog text-slate-500">{t.checkout.loading}</p>
        </div>
      </CheckoutShell>
    )
  }

  if (reviewError) {
    return (
      <CheckoutShell title={t.checkout.title}>
        <div className="mx-auto max-w-lg rounded-[2rem] bg-white px-6 py-10 text-center shadow-sm ring-1 ring-brand-border/50">
          <p className="font-catalog text-sm leading-relaxed text-red-600">
            {getApiErrorMessage(reviewErrorDetail)}
          </p>
          <Link to="/cart" className="mt-5 inline-flex text-sm font-bold text-brand-accent hover:underline">
            {t.shared.backToCart}
          </Link>
        </div>
      </CheckoutShell>
    )
  }

  return (
    <CheckoutShell title={t.checkout.title} subtitle={t.checkout.subtitle}>
      <SeoHead title={t.checkout.title} noIndex />

      <div className="mb-6 flex justify-center lg:justify-start">
        <div className="inline-flex w-full max-w-md rounded-full bg-white p-1 shadow-sm ring-1 ring-brand-border/60 sm:w-auto">
          <button
            type="button"
            onClick={() => setMode('delivery')}
            className={`flex-1 rounded-full px-5 py-2.5 text-sm font-bold tracking-normal transition sm:flex-none ${
              mode === 'delivery' ? 'bg-brand-accent text-white shadow-sm' : 'text-slate-600 hover:text-brand-ink'
            }`}
          >
            {t.checkout.homeDelivery}
          </button>
          <button
            type="button"
            onClick={() => setMode('pickup')}
            className={`flex-1 rounded-full px-5 py-2.5 text-sm font-bold tracking-normal transition sm:flex-none ${
              mode === 'pickup' ? 'bg-brand-accent text-white shadow-sm' : 'text-slate-600 hover:text-brand-ink'
            }`}
          >
            {t.checkout.storePickup}
          </button>
        </div>
      </div>

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1.15fr)_minmax(20rem,0.85fr)] lg:gap-8">
        <div className="space-y-5">
          {mode === 'delivery' ? (
            <CheckoutCard>
              <SectionTitle icon={<IconTruck size={18} />}>{t.checkout.deliveryAddress}</SectionTitle>
              <div className="mt-5 space-y-4">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm text-slate-500">{t.checkout.delivery}</p>
                  {!showAddAddress && (
                    <button
                      type="button"
                      onClick={() => setShowAddAddress(true)}
                      className="text-sm font-bold text-brand-accent hover:underline"
                    >
                      {t.checkout.addNewAddress}
                    </button>
                  )}
                </div>
                {showAddAddress ? (
                  <AddAddressForm
                    defaultAsFirst={addresses.length === 0}
                    onSuccess={(address) => {
                      setAddressId(address.address_id)
                      setShowAddAddress(false)
                    }}
                    onCancel={() => setShowAddAddress(false)}
                  />
                ) : (
                  <select
                    value={addressId ?? defaultAddress?.address_id ?? ''}
                    onChange={(e) => setAddressId(Number(e.target.value))}
                    className="w-full rounded-2xl border border-brand-border bg-brand-cream/40 px-4 py-3 text-sm outline-none focus:border-brand-accent focus:ring-2 focus:ring-brand-tint"
                  >
                    <option value="">{t.checkout.selectAddress}</option>
                    {addresses.map((a) => (
                      <option key={a.address_id} value={a.address_id}>
                        {a.address_title} — {a.street}, {a.city}
                      </option>
                    ))}
                  </select>
                )}
                <button
                  type="button"
                  onClick={() => setDelivery.mutate(undefined)}
                  disabled={
                    (!addressId && !defaultAddress?.address_id) ||
                    showAddAddress ||
                    !defaultZoneId ||
                    !defaultSlotId
                  }
                  className="h-11 rounded-full bg-brand-accent px-5 text-sm font-bold text-white transition hover:bg-brand-accent-hover disabled:opacity-50"
                >
                  {t.checkout.applyDelivery}
                </button>
                {!addresses.length && !showAddAddress && (
                  <p className="text-sm text-slate-500">
                    {t.checkout.noAddresses}{' '}
                    <button
                      type="button"
                      onClick={() => setShowAddAddress(true)}
                      className="font-bold text-brand-accent hover:underline"
                    >
                      {t.checkout.addDeliveryAddress}
                    </button>
                  </p>
                )}
              </div>
            </CheckoutCard>
          ) : (
            <CheckoutCard>
              <SectionTitle icon={<IconMapPin size={18} />}>{t.checkout.pickupStore}</SectionTitle>
              <div className="mt-5 space-y-3">
                {storesLoading && (
                  <p className="text-sm text-slate-500">{t.checkout.loadingStores}</p>
                )}
                {storesError && (
                  <div className="rounded-2xl bg-red-50 px-4 py-3 text-sm text-red-700 ring-1 ring-red-100">
                    <p>{getApiErrorMessage(storesErrorDetail)}</p>
                    <button
                      type="button"
                      onClick={() => refetchStores()}
                      className="mt-2 font-bold text-red-800 underline"
                    >
                      {t.shared.retry}
                    </button>
                  </div>
                )}
                {!storesLoading && !storesError && stores.length === 0 && (
                  <p className="text-sm text-slate-500">{t.checkout.noPickupStores}</p>
                )}
                {stores.map((s) => (
                  <button
                    key={s.pickup_store_id}
                    type="button"
                    onClick={() => {
                      setStoreId(s.pickup_store_id)
                      setPickup.mutate(s.pickup_store_id)
                    }}
                    className={`block w-full rounded-2xl px-4 py-3.5 text-left ring-1 transition ${
                      storeId === s.pickup_store_id
                        ? 'bg-brand-tint/80 ring-2 ring-brand-accent'
                        : 'bg-brand-cream/40 ring-brand-border hover:bg-brand-cream-alt'
                    }`}
                  >
                    <span className="block font-bold tracking-normal text-brand-ink">{s.store_name}</span>
                    {(s.address_line || s.city) && (
                      <span className="mt-1 block text-sm tracking-normal text-slate-500">
                        {[s.address_line, s.city].filter(Boolean).join(' · ')}
                      </span>
                    )}
                  </button>
                ))}
              </div>
            </CheckoutCard>
          )}

          <CheckoutCard>
            <SectionTitle icon={<IconLock size={18} />}>{t.checkout.paymentMethod}</SectionTitle>
            <div className="mt-5 space-y-3">
              {methods.map((m) => (
                <label
                  key={m.code}
                  className={`flex cursor-pointer items-start gap-3 rounded-2xl px-4 py-3.5 ring-1 transition ${
                    paymentMethod === m.code
                      ? 'bg-brand-tint/80 ring-2 ring-brand-accent'
                      : 'bg-brand-cream/40 ring-brand-border hover:bg-brand-cream-alt'
                  }`}
                >
                  <input
                    type="radio"
                    name="payment"
                    value={m.code}
                    checked={paymentMethod === m.code}
                    onChange={() => setPaymentMethod(m.code)}
                    className="mt-1 accent-[#E91E63]"
                  />
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-2">
                      {m.code === 'COD' && (
                        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-emerald-50 text-emerald-600">
                          <IconCashOnDelivery className="h-5 w-5" />
                        </span>
                      )}
                      <span className="block font-bold tracking-normal text-brand-ink">{m.label}</span>
                    </span>
                    <span className="mt-1 block text-sm leading-relaxed tracking-normal text-slate-500">
                      {m.description}
                    </span>
                    {m.code === 'TAP' && <OnlinePaymentBadges />}
                  </span>
                </label>
              ))}
            </div>
          </CheckoutCard>

          <CheckoutCard>
            <SectionTitle icon={<IconTicket size={18} />}>{t.checkout.loyaltyPoints}</SectionTitle>
            {review?.loyalty ? (
              <div className="mt-5 space-y-3">
                <p className="text-sm tracking-normal text-slate-600">
                  {t.checkout.balance} {review.loyalty.points_balance} pts · {t.checkout.maxRedeem}{' '}
                  {review.loyalty.max_redeemable_points} pts
                </p>
                {review.loyalty.points_redeemed > 0 && (
                  <p className="text-sm font-semibold text-emerald-700">
                    {t.checkout.applied} {review.loyalty.points_redeemed} pts (−
                    {formatMoney(review.pricing.loyalty_discount ?? 0)})
                  </p>
                )}
                <div className="flex flex-col gap-2 sm:flex-row">
                  <input
                    type="number"
                    min="10"
                    value={loyaltyPoints}
                    onChange={(e) => setLoyaltyPoints(e.target.value)}
                    placeholder={t.checkout.pointsPlaceholder}
                    className="flex-1 rounded-full border border-brand-border bg-brand-cream/40 px-4 py-2.5 text-sm outline-none focus:border-brand-accent focus:ring-2 focus:ring-brand-tint"
                  />
                  <button
                    type="button"
                    onClick={() => applyLoyalty.mutate()}
                    disabled={!loyaltyPoints || review.loyalty.max_redeemable_points < 10}
                    className="h-11 rounded-full bg-brand-accent px-5 text-sm font-bold text-white disabled:opacity-50"
                  >
                    {t.shared.apply}
                  </button>
                </div>
              </div>
            ) : (
              <p className="mt-4 text-sm tracking-normal text-slate-500">{t.checkout.signInToRedeem}</p>
            )}
          </CheckoutCard>

          {review?.coupons_enabled && (
            <CheckoutCard>
              <SectionTitle icon={<IconTicket size={18} />}>{t.checkout.coupon}</SectionTitle>
              <div className="mt-5 flex flex-col gap-2 sm:flex-row">
                <input
                  value={coupon}
                  onChange={(e) => setCoupon(e.target.value)}
                  className="flex-1 rounded-full border border-brand-border bg-brand-cream/40 px-4 py-2.5 text-sm outline-none focus:border-brand-accent focus:ring-2 focus:ring-brand-tint"
                />
                <button
                  type="button"
                  onClick={() => applyCoupon.mutate()}
                  className="h-11 rounded-full bg-brand-accent px-5 text-sm font-bold text-white"
                >
                  {t.shared.apply}
                </button>
              </div>
            </CheckoutCard>
          )}
        </div>

        <div className="space-y-4 lg:sticky lg:top-24">
          <CartSummary
            cart={review?.cart ?? cart}
            pricing={review?.pricing}
            showCheckoutLink={false}
            sticky={false}
          />
          {(confirm.isError || checkoutError) && (
            <p className="rounded-2xl bg-red-50 px-4 py-3 text-sm text-red-600 ring-1 ring-red-100">
              {checkoutError ?? getApiErrorMessage(confirm.error)}
            </p>
          )}
          {fulfillmentType && (
            <p className="rounded-2xl bg-emerald-50 px-4 py-3 text-sm font-semibold text-emerald-700 ring-1 ring-emerald-100">
              {fulfillmentType === 'PICKUP'
                ? t.checkout.pickupSelected
                : t.checkout.deliverySelected}
            </p>
          )}
          <button
            type="button"
            onClick={() => confirm.mutate()}
            disabled={confirm.isPending || setPickup.isPending || setDelivery.isPending || reviewLoading}
            className="flex h-12 w-full items-center justify-center rounded-full bg-brand-accent text-sm font-bold tracking-normal text-white shadow-sm transition hover:bg-brand-accent-hover disabled:opacity-50"
          >
            {confirm.isPending
              ? paymentMethod === 'TAP'
                ? t.checkout.redirectingPayment
                : t.checkout.placingOrder
              : t.checkout.placeOrder}
          </button>
          <Link
            to="/cart"
            className="block text-center text-sm font-semibold tracking-normal text-slate-500 hover:text-brand-accent"
          >
            {t.shared.backToCart}
          </Link>
        </div>
      </div>
    </CheckoutShell>
  )
}

function CheckoutShell({
  title,
  subtitle,
  children,
}: {
  title: string
  subtitle?: string
  children: ReactNode
}) {
  return (
    <div className="min-h-[calc(100vh-6rem)] bg-brand-cream pb-16 pt-8">
      <div className={`${PAGE_CONTAINER}`}>
        <header className="mb-8 text-center lg:text-start">
          <h1 className="font-display text-3xl font-extrabold tracking-normal text-brand-ink">{title}</h1>
          {subtitle ? (
            <p className="mt-2 text-[15px] leading-relaxed tracking-normal text-slate-500">{subtitle}</p>
          ) : null}
        </header>
        {children}
      </div>
    </div>
  )
}

function CheckoutCard({ children }: { children: ReactNode }) {
  return (
    <section className="rounded-[1.75rem] bg-white p-5 shadow-sm ring-1 ring-brand-border/50 sm:p-6">
      {children}
    </section>
  )
}

function SectionTitle({ icon, children }: { icon: ReactNode; children: ReactNode }) {
  return (
    <h2 className="flex items-center gap-2.5 font-display text-lg font-bold tracking-normal text-brand-ink">
      <span className="flex h-9 w-9 items-center justify-center rounded-full bg-brand-tint text-brand-accent">
        {icon}
      </span>
      {children}
    </h2>
  )
}
