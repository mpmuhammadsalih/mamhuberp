import { useQuery } from '@tanstack/react-query'
import { Link, useLocation, useParams } from 'react-router-dom'
import { PAGE_CONTAINER } from '../components/layout/homeLayout'
import { IconCheck, IconGift, IconTruck } from '../components/icons/Icons'
import { useLocale } from '../i18n/LocaleContext'
import { getData } from '../lib/api'
import { useFormatMoney } from '../i18n/useFormatMoney'
import type { OrderDetail } from '../types/api'

type SuccessState = {
  orderNumber?: string
  grandTotal?: number
  currencyCode?: string
  fulfillmentType?: string
  itemCount?: number
}

export function OrderSuccessPage() {
  const { t } = useLocale()
  const formatMoney = useFormatMoney()
  const { orderId } = useParams()
  const location = useLocation()
  const state = (location.state as SuccessState | null) ?? {}

  const { data: order } = useQuery({
    queryKey: ['order', orderId],
    queryFn: () => getData<OrderDetail>(`/orders/${orderId}`),
    enabled: Boolean(orderId),
    staleTime: 60_000,
  })

  const orderNumber = state.orderNumber ?? order?.order_number ?? `#${orderId}`
  const grandTotal = state.grandTotal ?? order?.grand_total ?? 0
  const currency = state.currencyCode ?? order?.currency_code ?? 'QAR'
  const itemCount = state.itemCount ?? order?.items?.length ?? 0
  const fulfillment = (state.fulfillmentType ?? order?.fulfillment_type ?? 'DELIVERY').toUpperCase()
  const isPickup = fulfillment === 'PICKUP'

  return (
    <div className="font-catalog min-h-[calc(100vh-4rem)] bg-gradient-to-b from-brand-cream via-white to-brand-cream-alt pb-16 pt-8 sm:pt-12">
      <div className={`${PAGE_CONTAINER} mx-auto max-w-5xl`}>
        <div className="relative overflow-hidden rounded-3xl bg-white shadow-[0_20px_60px_rgba(255,75,139,0.12)] ring-1 ring-brand-border/40">
          <div
            className="pointer-events-none absolute -right-8 -top-8 h-32 w-32 rounded-full bg-brand-accent/10 blur-2xl"
            aria-hidden
          />
          <div
            className="pointer-events-none absolute -bottom-10 -left-10 h-36 w-36 rounded-full bg-brand-tint blur-2xl"
            aria-hidden
          />

          <div className="relative grid grid-cols-1 lg:grid-cols-2 lg:divide-x lg:divide-brand-border/40">
            <div className="flex flex-col px-6 py-10 text-center sm:px-10 sm:py-12 lg:text-left">
              <div className="mx-auto flex h-20 w-20 items-center justify-center rounded-full bg-gradient-to-br from-brand-accent to-brand-accent-hover shadow-lg shadow-brand-accent/30 animate-[success-pop_0.5s_ease-out] lg:mx-0">
                <IconCheck size={40} className="text-white stroke-[3]" />
              </div>

              <p className="mt-6 text-xs font-bold uppercase tracking-[0.2em] text-brand-accent">
                {t.orderSuccess.thankYou}
              </p>
              <h1 className="mt-2 font-display text-2xl font-bold text-brand-ink sm:text-3xl">
                {t.orderSuccess.placed}
              </h1>
              <p className="mt-3 text-sm leading-relaxed text-brand-sage">
                {isPickup ? t.orderSuccess.pickupMessage : t.orderSuccess.deliveryMessage}
              </p>

              <div className="mt-8 rounded-2xl bg-brand-cream-alt/80 px-5 py-4 ring-1 ring-brand-border/50 lg:mt-auto">
                <p className="text-xs font-semibold uppercase tracking-wide text-brand-sage">
                  {t.orderSuccess.orderNumber}
                </p>
                <p className="mt-1 font-display text-xl font-bold text-brand-ink">{orderNumber}</p>
                <div className="mt-4 grid grid-cols-3 gap-4 border-t border-brand-border/40 pt-4">
                  <div>
                    <p className="text-xs text-brand-sage">{t.shared.total}</p>
                    <p className="text-lg font-bold text-brand-accent">
                      {formatMoney(grandTotal, currency)}
                    </p>
                  </div>
                  {itemCount > 0 && (
                    <div>
                      <p className="text-xs text-brand-sage">{t.orderSuccess.items}</p>
                      <p className="text-lg font-bold text-brand-ink">{itemCount}</p>
                    </div>
                  )}
                  <div>
                    <p className="text-xs text-brand-sage">{t.orderSuccess.method}</p>
                    <p className="text-sm font-semibold text-brand-ink">
                      {isPickup ? t.shared.pickup : t.shared.delivery}
                    </p>
                  </div>
                </div>
              </div>
            </div>

            <div className="flex flex-col px-6 py-10 sm:px-10 sm:py-12 lg:py-12">
              <ul className="grid flex-1 grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-1">
                <li className="flex items-start gap-3 rounded-xl bg-[#ECFDF5] px-4 py-3 ring-1 ring-[#BBF7D0]/60 sm:col-span-2 lg:col-span-1">
                  <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#D1FAE5] text-[#059669]">
                    <IconCheck size={16} />
                  </span>
                  <div>
                    <p className="font-semibold text-[#065F46]">{t.orderSuccess.stepConfirmed}</p>
                    <p className="text-xs text-[#047857]">
                      Your payment method is saved with this order.
                    </p>
                  </div>
                </li>
                <li className="flex items-start gap-3 rounded-xl bg-brand-cream px-4 py-3 ring-1 ring-brand-border/30">
                  <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-white text-brand-accent shadow-sm">
                    <IconGift size={16} />
                  </span>
                  <div>
                    <p className="font-semibold text-brand-ink">{t.orderSuccess.stepPreparing}</p>
                    <p className="text-xs text-brand-sage">
                      Our team is getting everything ready for you.
                    </p>
                  </div>
                </li>
                <li className="flex items-start gap-3 rounded-xl bg-brand-cream px-4 py-3 ring-1 ring-brand-border/30">
                  <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-white text-brand-accent shadow-sm">
                    <IconTruck size={16} />
                  </span>
                  <div>
                    <p className="font-semibold text-brand-ink">
                      {isPickup ? t.orderSuccess.stepReadyPickup : t.orderSuccess.stepOutForDelivery}
                    </p>
                    <p className="text-xs text-brand-sage">
                      {isPickup
                        ? 'You will receive an update when your order is ready.'
                        : 'We will deliver to your selected address.'}
                    </p>
                  </div>
                </li>
              </ul>

              <div className="mt-8 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:mt-10">
                <Link
                  to="/products"
                  className="inline-flex items-center justify-center rounded-full bg-brand-accent px-8 py-3.5 text-sm font-bold text-white shadow-md transition hover:bg-brand-accent-hover active:scale-[0.98]"
                >
                  {t.orderSuccess.continueShopping}
                </Link>
                <Link
                  to={`/orders/${orderId}`}
                  className="inline-flex items-center justify-center rounded-full border-2 border-brand-border bg-white px-8 py-3.5 text-sm font-bold text-brand-ink transition hover:border-brand-accent hover:text-brand-accent"
                >
                  {t.orderSuccess.viewOrder}
                </Link>
              </div>
            </div>
          </div>
        </div>

        <p className="mt-6 text-center text-xs text-brand-sage">
          {t.orderSuccess.questions}{' '}
          <Link to="/profile" className="font-semibold text-brand-accent hover:underline">
            {t.orderSuccess.contactSupport}
          </Link>{' '}
          from your account.
        </p>
      </div>

      <style>{`
        @keyframes success-pop {
          0% { transform: scale(0.6); opacity: 0; }
          70% { transform: scale(1.08); }
          100% { transform: scale(1); opacity: 1; }
        }
      `}</style>
    </div>
  )
}
