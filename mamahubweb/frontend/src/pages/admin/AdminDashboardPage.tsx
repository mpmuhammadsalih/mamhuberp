import { Link } from 'react-router-dom'
import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { CategoryDonutChart, SalesLineChart } from '../../components/admin/AdminCharts'
import { AdminCard, AdminKpiCard, AdminPageTitle, StatusBadge } from '../../components/admin/ui'
import { IconCart, IconUser } from '../../components/icons/Icons'
import { IconTrendUp } from '../../components/admin/AdminNavIcons'
import { AdminState } from '../../components/admin/AdminState'
import { DEFAULT_CURRENCY, formatMoney } from '../../lib/currency'
import { getData, getDataWithMeta } from '../../lib/api'
import type { Product } from '../../types/api'

interface Dashboard {
  total_orders: number
  total_revenue: number
  confirmed_orders: number
  cancelled_orders: number
  total_customers: number
  total_products: number
  active_promotions: number
  recent_orders: Array<{
    order_id: number
    order_number: string
    order_status: string
    grand_total: number
    currency_code?: string
    customer_email: string
    created_at?: string
  }>
}

interface OrderRow {
  order_id: number
  grand_total: number
  created_at?: string
}

const thClass = 'px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-[#94a3b8]'
const tdClass = 'px-4 py-4 text-sm text-[#334155]'

export function AdminDashboardPage() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['admin-dashboard'],
    queryFn: () => getData<Dashboard>('/admin/dashboard'),
  })

  const { data: ordersResponse } = useQuery({
    queryKey: ['admin-dashboard-orders-chart'],
    queryFn: () => getDataWithMeta<OrderRow[]>('/admin/orders', { page: 1, page_size: 100 }),
  })

  const { data: topProductsResponse } = useQuery({
    queryKey: ['admin-dashboard-top-products'],
    queryFn: () =>
      getData<{ products?: Product[] }>('/products/collections/best-sellers', { page_size: 5 }),
  })

  const topProducts = topProductsResponse?.products ?? []

  const salesChart = useMemo(() => {
    const orders = ordersResponse?.data ?? []
    const buckets = new Map<string, number>()
    for (const order of orders) {
      if (!order.created_at) continue
      const d = new Date(order.created_at)
      const key = d.toLocaleDateString('en-US', { weekday: 'short' })
      buckets.set(key, (buckets.get(key) ?? 0) + Number(order.grand_total ?? 0))
    }
    const labels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    return labels.map((label) => ({ label, value: buckets.get(label) ?? 0 }))
  }, [ordersResponse])

  const categorySlices = [
    { label: 'Toys', value: 35, color: '#E91E63' },
    { label: 'Kids Fashion', value: 28, color: '#60a5fa' },
    { label: 'Stationery', value: 22, color: '#34d399' },
    { label: 'Electronics', value: 15, color: '#fbbf24' },
  ]

  return (
    <div>
      <AdminPageTitle title="Dashboard" description="Welcome back! Here's what's happening with your store today." />

      <AdminState isLoading={isLoading} isError={isError} isEmpty={!data}>
        {data && (
          <>
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <AdminKpiCard
                label={`Total Sales (${DEFAULT_CURRENCY})`}
                value={formatMoney(data.total_revenue)}
                trend="+12.5% vs last week"
                accent="pink"
                icon={<IconTrendUp size={20} />}
              />
              <AdminKpiCard
                label="Orders"
                value={(data.total_orders ?? 0).toLocaleString()}
                trend={`${data.confirmed_orders} confirmed`}
                accent="blue"
                icon={<IconCart size={20} />}
              />
              <AdminKpiCard
                label="Customers"
                value={(data.total_customers ?? 0).toLocaleString()}
                trend="Registered accounts"
                accent="green"
                icon={<IconUser size={20} />}
              />
              <AdminKpiCard
                label="Products"
                value={(data.total_products ?? 0).toLocaleString()}
                trend={`${data.active_promotions} active coupons`}
                accent="orange"
                icon={<IconCart size={20} />}
              />
            </div>

            <div className="mt-6 grid gap-6 xl:grid-cols-3">
              <AdminCard className="xl:col-span-2">
                <div className="mb-4 flex items-center justify-between">
                  <h2 className="text-lg font-semibold text-[#0f172a]">Sales Overview</h2>
                  <span className="text-xs text-[#94a3b8]">Last 7 days</span>
                </div>
                <SalesLineChart data={salesChart} />
              </AdminCard>

              <AdminCard>
                <h2 className="mb-4 text-lg font-semibold text-[#0f172a]">Top Selling Products</h2>
                <ul className="space-y-4">
                  {topProducts.slice(0, 5).map((p) => (
                    <li key={p.item_code} className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-[#0f172a]">{p.item_name}</p>
                        <p className="text-xs text-[#94a3b8]">{formatMoney(p.retail_price)}</p>
                      </div>
                      <span className="shrink-0 text-xs font-semibold text-[#64748b]">
                        {p.units_sold ?? 0} sold
                      </span>
                    </li>
                  ))}
                  {!topProducts.length && <li className="text-sm text-[#94a3b8]">No sales data yet.</li>}
                </ul>
              </AdminCard>
            </div>

            <div className="mt-6 grid gap-6 xl:grid-cols-3">
              <AdminCard className="xl:col-span-2">
                <div className="mb-4 flex items-center justify-between">
                  <h2 className="text-lg font-semibold text-[#0f172a]">Recent Orders</h2>
                  <Link to="/admin/orders" className="text-sm font-medium text-[#E91E63] hover:underline">
                    View all
                  </Link>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[640px]">
                    <thead>
                      <tr className="border-b border-[#eef1f6]">
                        <th className={thClass}>Order ID</th>
                        <th className={thClass}>Customer</th>
                        <th className={thClass}>Date</th>
                        <th className={thClass}>Total</th>
                        <th className={thClass}>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(data.recent_orders ?? []).map((o) => (
                        <tr key={o.order_id ?? o.order_number} className="border-b border-[#f8fafc]">
                          <td className={tdClass}>
                            <Link to={`/admin/orders/${o.order_id}`} className="font-medium text-[#E91E63] hover:underline">
                              {o.order_number}
                            </Link>
                          </td>
                          <td className={tdClass}>{o.customer_email}</td>
                          <td className={tdClass}>
                            {o.created_at ? new Date(o.created_at).toLocaleDateString() : '—'}
                          </td>
                          <td className={tdClass}>{formatMoney(Number(o.grand_total), o.currency_code)}</td>
                          <td className={tdClass}>
                            <StatusBadge status={o.order_status} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </AdminCard>

              <AdminCard>
                <h2 className="mb-4 text-lg font-semibold text-[#0f172a]">Sales by Category</h2>
                <CategoryDonutChart slices={categorySlices} />
              </AdminCard>
            </div>
          </>
        )}
      </AdminState>
    </div>
  )
}
