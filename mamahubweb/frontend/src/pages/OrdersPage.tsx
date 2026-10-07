import { useQuery } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { PAGE_CONTAINER } from '../components/layout/homeLayout'
import { useLocale } from '../i18n/LocaleContext'
import { getData } from '../lib/api'
import { useFormatMoney } from '../i18n/useFormatMoney'
import type { OrderSummary } from '../types/api'

const STATUS_LABELS: Record<string, string> = {
  CONFIRMED: 'Confirmed',
  PROCESSING: 'Preparing',
  PICKING: 'Preparing',
  PACKED: 'Ready',
  OUT_FOR_DELIVERY: 'Out for delivery',
  DELIVERED: 'Delivered',
  CANCELLED: 'Cancelled',
}

export function OrdersPage() {
  const { t } = useLocale()
  const formatMoney = useFormatMoney()
  const [params] = useSearchParams()
  const confirmed = params.get('confirmed')

  const { data: orders = [] } = useQuery({
    queryKey: ['orders'],
    queryFn: () => getData<OrderSummary[]>('/orders'),
    refetchInterval: 20000,
  })

  return (
    <div className={`${PAGE_CONTAINER} py-8`}>
      <h1 className="mb-6 text-3xl font-bold">{t.account.yourOrders}</h1>
      {confirmed && (
        <div className="mb-6 rounded-2xl bg-green-50 p-4 text-green-800 ring-1 ring-green-200">
          {t.account.orderPlacedSuccess}
        </div>
      )}
      <div className="space-y-4">
        {orders.map((o) => (
          <Link
            key={o.order_id}
            to={`/orders/${o.order_id}`}
            className="block rounded-2xl bg-white p-5 shadow-sm hover:ring-2 hover:ring-brand-accent/30"
          >
            <div className="flex items-center justify-between">
              <div>
                <p className="font-semibold">{o.order_number}</p>
                <p className="text-sm text-gray-500">{STATUS_LABELS[o.order_status] || o.order_status}</p>
              </div>
              <p className="font-bold text-brand-accent">
                {formatMoney(o.grand_total, o.currency_code)}
              </p>
            </div>
          </Link>
        ))}
        {!orders.length && <p className="text-gray-500">{t.account.noOrders}</p>}
      </div>
    </div>
  )
}
