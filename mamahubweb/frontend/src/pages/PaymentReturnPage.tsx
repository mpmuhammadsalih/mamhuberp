import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { PAGE_CONTAINER } from '../components/layout/homeLayout'
import { IconClose } from '../components/icons/Icons'
import { useLocale } from '../i18n/LocaleContext'
import { getApiErrorMessage, postData } from '../lib/api'
import { normalizeCart } from '../lib/queries/cart'
import type { CartData, OrderSummary } from '../types/api'

function classifyPaymentError(message: string | null) {
  if (!message) return null
  const lower = message.toLowerCase()
  if (lower.includes('missing')) return 'missing' as const
  if (lower.includes('cancel')) return 'cancelled' as const
  return 'failed' as const
}

export function PaymentReturnPage() {
  const { t } = useLocale()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [searchParams] = useSearchParams()
  const tapId = searchParams.get('tap_id') || searchParams.get('charge_id') || ''
  const [error, setError] = useState<string | null>(null)

  const complete = useMutation({
    mutationFn: () => postData<OrderSummary>('/checkout/payment/tap/complete', { tap_id: tapId }),
    onSuccess: (order) => {
      queryClient.removeQueries({ queryKey: ['checkout-review'] })
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
      navigate(`/order-success/${order.order_id}`, {
        replace: true,
        state: {
          orderNumber: order.order_number,
          grandTotal: order.grand_total,
          currencyCode: order.currency_code,
          itemCount: order.item_count,
          fulfillmentType: order.fulfillment_type,
        },
      })
    },
    onError: (err) => setError(getApiErrorMessage(err)),
  })

  useEffect(() => {
    if (!tapId) {
      setError(t.paymentReturn.missingRef)
      return
    }
    complete.mutate()
  }, [tapId, t.paymentReturn.missingRef])

  const kind = classifyPaymentError(error)
  const title = kind === 'cancelled'
    ? t.paymentReturn.cancelledTitle
    : kind === 'missing' || kind === 'failed'
      ? t.paymentReturn.failedTitle
      : t.paymentReturn.processing
  const body = kind === 'cancelled'
    ? t.paymentReturn.cancelledBody
    : kind === 'missing'
      ? t.paymentReturn.missingRef
      : kind === 'failed'
        ? t.paymentReturn.failedBody
        : t.paymentReturn.confirming

  return (
    <div className="min-h-[calc(100vh-8rem)] bg-brand-cream px-4 py-10 sm:py-16">
      <div className={`${PAGE_CONTAINER} mx-auto max-w-lg`}>
        <div className="relative overflow-hidden rounded-[2rem] bg-white px-6 py-10 text-center shadow-[0_18px_50px_rgba(15,23,42,0.08)] ring-1 ring-brand-border/50 sm:px-10 sm:py-12">
          <div
            className="pointer-events-none absolute -end-10 -top-10 h-32 w-32 rounded-full bg-brand-yellow/50 blur-2xl"
            aria-hidden
          />
          <div
            className="pointer-events-none absolute -bottom-12 -start-8 h-36 w-36 rounded-full bg-brand-tint blur-2xl"
            aria-hidden
          />

          <div className="relative">
            {kind ? (
              <span
                className={`mx-auto flex h-16 w-16 items-center justify-center rounded-full ${
                  kind === 'cancelled' ? 'bg-brand-yellow text-brand-ink' : 'bg-brand-tint text-brand-accent'
                }`}
              >
                <IconClose size={28} className="stroke-[2.5]" />
              </span>
            ) : (
              <span
                className="mx-auto block h-14 w-14 animate-spin rounded-full border-4 border-brand-tint border-t-brand-accent"
                aria-hidden
              />
            )}

            <p className="mt-5 text-[11px] font-bold uppercase tracking-[0.18em] text-brand-orange">
              {kind === 'cancelled' ? t.shared.payment : t.paymentReturn.processing}
            </p>
            <h1 className="mt-2 font-display text-2xl font-extrabold tracking-normal text-brand-ink sm:text-[1.75rem]">
              {title}
            </h1>
            <p className="mx-auto mt-3 max-w-sm text-[15px] leading-relaxed tracking-normal text-slate-600">
              {body}
            </p>

            {kind ? (
              <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:justify-center">
                <Link
                  to="/checkout"
                  className="inline-flex h-12 items-center justify-center rounded-full bg-brand-accent px-6 text-sm font-bold tracking-normal text-white shadow-sm transition hover:bg-brand-accent-hover"
                >
                  {t.paymentReturn.backToCheckout}
                </Link>
                <Link
                  to="/orders"
                  className="inline-flex h-12 items-center justify-center rounded-full bg-brand-cream-alt px-6 text-sm font-bold tracking-normal text-brand-ink ring-1 ring-brand-border transition hover:bg-brand-tint"
                >
                  {t.paymentReturn.viewOrders}
                </Link>
              </div>
            ) : (
              <p className="mt-8 text-sm font-medium tracking-normal text-slate-400">
                {t.paymentReturn.confirming}
              </p>
            )}

            {kind ? (
              <Link
                to="/"
                className="mt-5 inline-block text-sm font-semibold tracking-normal text-brand-accent hover:underline"
              >
                {t.paymentReturn.keepShopping}
              </Link>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  )
}
