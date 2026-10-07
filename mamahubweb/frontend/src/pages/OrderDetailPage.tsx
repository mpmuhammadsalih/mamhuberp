import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { PAGE_CONTAINER } from '../components/layout/homeLayout'
import { useLocale } from '../i18n/LocaleContext'
import { productDisplayName } from '../i18n/productName'
import { getApiErrorMessage, getData, postData } from '../lib/api'
import { useFormatMoney } from '../i18n/useFormatMoney'
import { resolveMediaUrl } from '../lib/media'
import { toTitleCase } from '../lib/textCase'
import type { OrderDetail } from '../types/api'

const STATUS_STYLES: Record<string, string> = {
  CONFIRMED: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
  PENDING: 'bg-amber-50 text-amber-700 ring-amber-200',
  AWAITING_PAYMENT: 'bg-amber-50 text-amber-700 ring-amber-200',
  PAYMENT_CONFIRMED: 'bg-sky-50 text-sky-700 ring-sky-200',
  PROCESSING: 'bg-sky-50 text-sky-700 ring-sky-200',
  PICKING: 'bg-sky-50 text-sky-700 ring-sky-200',
  PACKED: 'bg-orange-50 text-orange-700 ring-orange-200',
  OUT_FOR_DELIVERY: 'bg-indigo-50 text-indigo-700 ring-indigo-200',
  SHIPPED: 'bg-indigo-50 text-indigo-700 ring-indigo-200',
  DELIVERED: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
  CANCELLED: 'bg-red-50 text-red-700 ring-red-200',
}

const STATUS_LABELS: Record<string, string> = {
  CONFIRMED: 'Confirmed',
  PROCESSING: 'Preparing',
  PICKING: 'Preparing',
  PACKED: 'Ready',
  OUT_FOR_DELIVERY: 'Out for delivery',
  DELIVERED: 'Delivered',
  CANCELLED: 'Cancelled',
}

function statusLabel(status: string): string {
  return STATUS_LABELS[status] || status.replace(/_/g, ' ')
}

function formatOrderDate(value?: string): string | null {
  if (!value) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null
  return date.toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}

export function OrderDetailPage() {
  const { locale, t } = useLocale()
  const formatMoney = useFormatMoney()
  const { orderId } = useParams()
  const queryClient = useQueryClient()

  const { data: order, isLoading, isError, error } = useQuery({
    queryKey: ['order', orderId],
    queryFn: () => getData<OrderDetail>(`/orders/${orderId}`),
    enabled: Boolean(orderId),
    refetchInterval: 15000,
  })

  const cancel = useMutation({
    mutationFn: () => postData(`/orders/${orderId}/cancel`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['order', orderId] })
      void queryClient.invalidateQueries({ queryKey: ['orders'] })
    },
  })

  if (isLoading) {
    return (
      <div className={`${PAGE_CONTAINER} py-16 font-catalog text-brand-sage`}>
        {t.account.loadingOrder}
      </div>
    )
  }

  if (isError || !order) {
    return (
      <div className={`${PAGE_CONTAINER} py-16 font-catalog`}>
        <Link to="/orders" className="text-sm font-semibold text-brand-accent hover:underline">
          ← {t.shared.backToOrders}
        </Link>
        <div className="mt-6 rounded-2xl bg-red-50 px-5 py-4 text-sm text-red-700 ring-1 ring-red-100">
          {isError ? getApiErrorMessage(error) : t.account.orderNotFound}
        </div>
      </div>
    )
  }

  const statusClass =
    STATUS_STYLES[order.order_status] ?? 'bg-brand-cream text-brand-ink ring-brand-border'
  const canCancel = order.order_status === 'CONFIRMED'
  const placedAt = formatOrderDate(order.created_at)

  return (
    <div className="font-catalog min-h-[calc(100vh-4rem)] bg-gradient-to-b from-brand-cream via-white to-brand-cream-alt pb-16 pt-8">
      <div className={`${PAGE_CONTAINER} mx-auto max-w-5xl`}>
        <Link
          to="/orders"
          className="inline-flex items-center text-sm font-semibold text-brand-accent hover:underline"
        >
          ← {t.shared.backToOrders}
        </Link>

        <div className="mt-6 overflow-hidden rounded-3xl bg-white shadow-[0_20px_60px_rgba(255,75,139,0.08)] ring-1 ring-brand-border/40">
          <div className="border-b border-brand-border/40 bg-gradient-to-r from-brand-cream/80 to-white px-6 py-6 sm:px-8">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="text-xs font-bold uppercase tracking-[0.18em] text-brand-sage">
                  {t.account.order}
                </p>
                <h1 className="mt-1 font-display text-2xl font-bold text-brand-ink sm:text-3xl">
                  {order.order_number}
                </h1>
                {placedAt && (
                  <p className="mt-2 text-sm text-brand-sage">
                    {t.account.placed} {placedAt}
                  </p>
                )}
              </div>
              <span
                className={`inline-flex rounded-full px-3 py-1 text-xs font-bold uppercase tracking-wide ring-1 ${statusClass}`}
              >
                {statusLabel(order.order_status)}
              </span>
            </div>
          </div>

          <div className="grid gap-0 lg:grid-cols-[1fr_320px] lg:divide-x lg:divide-brand-border/40">
            <section className="px-6 py-6 sm:px-8">
              <h2 className="font-display text-lg font-bold text-brand-ink">{t.orderSuccess.items}</h2>
              <ul className="mt-4 divide-y divide-brand-border/30">
                {(order.items ?? []).map((item) => {
                  const imageUrl = resolveMediaUrl(item.primary_image_url)
                  const rawName = item.item_name
                    ? productDisplayName(
                        { item_code: item.item_code, item_name: item.item_name },
                        locale,
                      )
                    : `${t.common.item} ${item.item_code}`
                  const name = locale === 'ar' ? rawName : toTitleCase(rawName)
                  return (
                    <li
                      key={item.order_item_id ?? item.item_code}
                      className="flex gap-4 py-4 first:pt-0 last:pb-0"
                    >
                      <div className="h-16 w-16 shrink-0 overflow-hidden rounded-xl bg-brand-cream ring-1 ring-brand-border/50">
                        {imageUrl ? (
                          <img
                            src={imageUrl}
                            alt=""
                            className="h-full w-full object-cover"
                            loading="lazy"
                          />
                        ) : (
                          <div className="flex h-full w-full items-center justify-center text-[10px] font-semibold uppercase tracking-wide text-brand-sage">
                            {t.shared.noImage}
                          </div>
                        )}
                      </div>
                      <div className="min-w-0 flex-1">
                        <Link
                          to={`/products/${item.item_code}`}
                          className="font-semibold text-brand-ink hover:text-brand-accent"
                        >
                          {name}
                        </Link>
                        <p className="mt-1 text-sm text-brand-sage">
                          {formatMoney(item.unit_price, order.currency_code)} {t.shared.eachQty}{' '}
                          {item.quantity}
                        </p>
                      </div>
                      <p className="shrink-0 text-sm font-bold text-brand-ink">
                        {formatMoney(item.line_total, order.currency_code)}
                      </p>
                    </li>
                  )
                })}
              </ul>
            </section>

            <aside className="bg-brand-cream/30 px-6 py-6 sm:px-8 lg:py-8">
              <h2 className="font-display text-lg font-bold text-brand-ink">{t.shared.summary}</h2>
              <dl className="mt-4 space-y-2 text-sm">
                {order.subtotal != null && (
                  <div className="flex justify-between text-brand-sage">
                    <dt>{t.shared.subtotal}</dt>
                    <dd>{formatMoney(order.subtotal, order.currency_code)}</dd>
                  </div>
                )}
                {!!order.discount_total && order.discount_total > 0 && (
                  <div className="flex justify-between text-emerald-700">
                    <dt>{t.shared.discount}</dt>
                    <dd>-{formatMoney(order.discount_total, order.currency_code)}</dd>
                  </div>
                )}
                {!!order.delivery_fee && order.delivery_fee > 0 && (
                  <div className="flex justify-between text-brand-sage">
                    <dt>{t.shared.delivery}</dt>
                    <dd>{formatMoney(order.delivery_fee, order.currency_code)}</dd>
                  </div>
                )}
                {!!order.gift_wrap && (
                  <div className="flex justify-between text-brand-sage">
                    <dt>{order.gift_wrap.label || t.shared.giftWrap}</dt>
                    <dd>
                      {(order.gift_wrap_fee ?? order.gift_wrap.fee ?? 0) > 0
                        ? formatMoney(
                            order.gift_wrap_fee ?? order.gift_wrap.fee ?? 0,
                            order.currency_code,
                          )
                        : t.checkout.wrapFree}
                    </dd>
                  </div>
                )}
                {order.tax_total != null && (
                  <div className="flex justify-between text-brand-sage">
                    <dt>{t.shared.tax}</dt>
                    <dd>{formatMoney(order.tax_total, order.currency_code)}</dd>
                  </div>
                )}
                <div className="flex justify-between border-t border-brand-border/40 pt-3 text-base font-bold text-brand-ink">
                  <dt>{t.shared.total}</dt>
                  <dd className="text-brand-accent">
                    {formatMoney(order.grand_total, order.currency_code)}
                  </dd>
                </div>
              </dl>

              {order.fulfillment_type && (
                <p className="mt-4 text-xs font-semibold uppercase tracking-wide text-brand-sage">
                  {order.fulfillment_type === 'PICKUP' ? t.shared.pickup : t.shared.delivery}
                </p>
              )}

              {order.payment_status && (
                <p className="mt-1 text-sm text-brand-sage">
                  {t.shared.payment}: {statusLabel(order.payment_status)}
                </p>
              )}
            </aside>
          </div>
        </div>

        <div className="mt-6 grid gap-6 lg:grid-cols-2">
          <section className="rounded-3xl bg-white p-6 shadow-sm ring-1 ring-brand-border/40 sm:p-8">
            <h2 className="font-display text-lg font-bold text-brand-ink">{t.account.statusHistory}</h2>
            {(order.status_history ?? []).length > 0 ? (
              <ol className="mt-4 space-y-4">
                {(order.status_history ?? []).map((entry, index) => {
                  const label = entry.order_status ?? entry.status ?? 'Update'
                  const note = entry.status_notes ?? entry.notes
                  const when = formatOrderDate(entry.created_at)
                  return (
                    <li key={`${label}-${index}`} className="flex gap-3">
                      <span
                        className="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full bg-brand-accent"
                        aria-hidden
                      />
                      <div>
                        <p className="font-semibold text-brand-ink">{statusLabel(label)}</p>
                        {note && <p className="mt-0.5 text-sm text-brand-sage">{note}</p>}
                        {when && <p className="mt-1 text-xs text-brand-sage/80">{when}</p>}
                      </div>
                    </li>
                  )
                })}
              </ol>
            ) : (
              <p className="mt-4 text-sm text-brand-sage">{t.account.noStatusUpdates}</p>
            )}
          </section>

          {canCancel && (
            <section className="flex flex-col justify-center rounded-3xl bg-white p-6 shadow-sm ring-1 ring-brand-border/40 sm:p-8">
              <h2 className="font-display text-lg font-bold text-brand-ink">{t.account.needCancel}</h2>
              <p className="mt-2 text-sm leading-relaxed text-brand-sage">
                You can cancel this order while it is still confirmed and not yet being prepared.
              </p>
              <button
                type="button"
                onClick={() => cancel.mutate()}
                disabled={cancel.isPending}
                className="mt-6 w-full rounded-full border border-red-200 bg-red-50 px-5 py-3 text-sm font-bold text-red-600 transition hover:bg-red-100 disabled:opacity-60 sm:w-auto"
              >
                {cancel.isPending ? t.account.cancelling : t.account.cancelOrder}
              </button>
            </section>
          )}
        </div>
      </div>
    </div>
  )
}
