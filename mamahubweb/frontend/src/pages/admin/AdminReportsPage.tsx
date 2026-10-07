import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { CategoryDonutChart, SalesLineChart } from '../../components/admin/AdminCharts'
import { AdminCard, AdminKpiCard, AdminPageTitle } from '../../components/admin/ui'
import { IconTrendUp } from '../../components/admin/AdminNavIcons'
import { IconCart } from '../../components/icons/Icons'
import { AdminState } from '../../components/admin/AdminState'
import { DEFAULT_CURRENCY, formatMoney } from '../../lib/currency'
import { getData, getDataWithMeta } from '../../lib/api'

interface Dashboard {
  total_orders: number
  total_revenue: number
  cancelled_orders: number
  total_customers: number
}

interface OrderRow {
  grand_total: number
  created_at?: string
}

export function AdminReportsPage() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['admin-reports-dashboard'],
    queryFn: () => getData<Dashboard>('/admin/dashboard'),
  })

  const { data: ordersResponse } = useQuery({
    queryKey: ['admin-reports-orders'],
    queryFn: () => getDataWithMeta<OrderRow[]>('/admin/orders', { page: 1, page_size: 100 }),
  })

  const salesChart = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((label) => ({
    label,
    value: (ordersResponse?.data ?? [])
      .filter((o) => o.created_at && new Date(o.created_at).toLocaleDateString('en-US', { weekday: 'short' }) === label)
      .reduce((sum, o) => sum + Number(o.grand_total ?? 0), 0),
  }))

  const categorySlices = [
    { label: 'Toys', value: 35, color: '#E91E63' },
    { label: 'Kids Fashion', value: 28, color: '#60a5fa' },
    { label: 'Stationery', value: 22, color: '#34d399' },
    { label: 'Electronics', value: 15, color: '#fbbf24' },
  ]

  return (
    <div>
      <AdminPageTitle title="Reports" description="Sales analytics and store performance summaries." />

      <AdminState isLoading={isLoading} isError={isError} isEmpty={!data}>
        {data && (
          <>
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <AdminKpiCard label="Total Revenue" value={formatMoney(data.total_revenue)} accent="pink" icon={<IconTrendUp />} />
              <AdminKpiCard label="Total Orders" value={data.total_orders} accent="blue" icon={<IconCart size={20} />} />
              <AdminKpiCard label="Customers" value={data.total_customers} accent="green" icon={<IconCart size={20} />} />
              <AdminKpiCard label="Cancelled" value={data.cancelled_orders} accent="orange" icon={<IconCart size={20} />} />
            </div>

            <div className="mt-6 grid gap-6 xl:grid-cols-2">
              <AdminCard>
                <h2 className="mb-4 text-lg font-semibold text-[#0f172a]">Weekly Sales ({DEFAULT_CURRENCY})</h2>
                <SalesLineChart data={salesChart} />
              </AdminCard>
              <AdminCard>
                <h2 className="mb-4 text-lg font-semibold text-[#0f172a]">Category Mix</h2>
                <CategoryDonutChart slices={categorySlices} />
              </AdminCard>
            </div>

            <AdminCard className="mt-6">
              <h2 className="mb-3 text-lg font-semibold text-[#0f172a]">Quick links</h2>
              <div className="flex flex-wrap gap-3">
                <Link to="/admin/orders" className="rounded-xl bg-[#f8fafc] px-4 py-2 text-sm font-medium text-[#334155] hover:bg-[#fff0f5] hover:text-[#E91E63]">
                  Order reports
                </Link>
                <Link to="/admin/inventory" className="rounded-xl bg-[#f8fafc] px-4 py-2 text-sm font-medium text-[#334155] hover:bg-[#fff0f5] hover:text-[#E91E63]">
                  Inventory report
                </Link>
                <Link to="/admin/customers" className="rounded-xl bg-[#f8fafc] px-4 py-2 text-sm font-medium text-[#334155] hover:bg-[#fff0f5] hover:text-[#E91E63]">
                  Customer report
                </Link>
              </div>
            </AdminCard>
          </>
        )}
      </AdminState>
    </div>
  )
}
