import { Link, useParams } from 'react-router-dom'
import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AdminState } from '../../components/admin/AdminState'
import {
  AdminAvatar,
  AdminCard,
  AdminKpiCard,
  AdminPageTitle,
  AdminTableWrap,
  StatusBadge,
} from '../../components/admin/ui'
import { IconCart } from '../../components/icons/Icons'
import { formatMoney } from '../../lib/currency'
import { getData, getDataWithMeta } from '../../lib/api'

interface Customer {
  user_id: number
  email: string
  first_name: string
  last_name: string
  account_status: string
  created_at?: string
}

interface OrderRow {
  order_id: number
  order_number: string
  order_status: string
  grand_total: number
  currency_code?: string
  created_at?: string
  customer_email?: string
}

const thClass = 'px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-[#94a3b8]'
const tdClass = 'px-4 py-4 text-sm text-[#334155]'

export function AdminCustomerDetailPage() {
  const { userId } = useParams()

  const { data: customers = [] } = useQuery({
    queryKey: ['admin-customers-lookup'],
    queryFn: () => getData<Customer[]>('/admin/customers', { page_size: 100 }),
  })

  const customer = customers.find((c) => String(c.user_id) === userId)

  const { data: ordersResponse, isLoading } = useQuery({
    queryKey: ['admin-customer-orders', customer?.email],
    queryFn: () => getDataWithMeta<OrderRow[]>('/admin/orders', { page: 1, page_size: 100 }),
    enabled: Boolean(customer?.email),
  })

  const customerOrders = useMemo(() => {
    if (!customer?.email) return []
    return (ordersResponse?.data ?? []).filter((o) => o.customer_email === customer.email)
  }, [ordersResponse, customer?.email])

  const totalSpent = customerOrders.reduce((sum, o) => sum + Number(o.grand_total ?? 0), 0)
  const lastOrder = customerOrders[0]

  return (
    <div>
      <Link to="/admin/customers" className="text-sm font-medium text-[#E91E63] hover:underline">
        ← Back to customers
      </Link>

      <AdminState isLoading={isLoading && !customer} isEmpty={!customer} emptyText="Customer not found.">
        {customer && (
          <>
            <AdminCard className="mt-4">
              <div className="flex flex-wrap items-start gap-5">
                <AdminAvatar name={`${customer.first_name} ${customer.last_name}`} size="lg" />
                <div className="flex-1">
                  <div className="flex flex-wrap items-center gap-3">
                    <h1 className="text-2xl font-bold text-[#0f172a]">
                      {customer.first_name} {customer.last_name}
                    </h1>
                    <span className="rounded-full bg-[#fce7f3] px-3 py-1 text-xs font-semibold text-[#E91E63]">
                      {customer.account_status === 'ACTIVE' ? 'VIP Customer' : customer.account_status}
                    </span>
                  </div>
                  <p className="mt-2 text-sm text-[#64748b]">{customer.email}</p>
                  <p className="text-sm text-[#64748b]">
                    Registered on {customer.created_at ? new Date(customer.created_at).toLocaleDateString() : '—'}
                  </p>
                </div>
              </div>
            </AdminCard>

            <div className="mt-6 grid gap-4 sm:grid-cols-3">
              <AdminKpiCard label="Total Orders" value={customerOrders.length} accent="pink" icon={<IconCart size={20} />} />
              <AdminKpiCard label="Total Spent" value={formatMoney(totalSpent)} accent="blue" icon={<IconCart size={20} />} />
              <AdminKpiCard
                label="Last Order"
                value={lastOrder?.created_at ? new Date(lastOrder.created_at).toLocaleDateString() : '—'}
                accent="green"
                icon={<IconCart size={20} />}
              />
            </div>

            <AdminCard className="mt-6">
              <AdminPageTitle title="Order History" />
              <AdminTableWrap>
                <table className="w-full min-w-[640px]">
                  <thead className="bg-[#fafbfd]">
                    <tr>
                      <th className={thClass}>Order</th>
                      <th className={thClass}>Date</th>
                      <th className={thClass}>Total</th>
                      <th className={thClass}>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {customerOrders.map((o) => (
                      <tr key={o.order_id} className="border-t border-[#eef1f6]">
                        <td className={tdClass}>
                          <Link to={`/admin/orders/${o.order_id}`} className="font-medium text-[#E91E63] hover:underline">
                            {o.order_number}
                          </Link>
                        </td>
                        <td className={tdClass}>{o.created_at ? new Date(o.created_at).toLocaleDateString() : '—'}</td>
                        <td className={tdClass}>{formatMoney(o.grand_total, o.currency_code)}</td>
                        <td className={tdClass}>
                          <StatusBadge status={o.order_status} />
                        </td>
                      </tr>
                    ))}
                    {!customerOrders.length && (
                      <tr>
                        <td colSpan={4} className="px-4 py-8 text-center text-sm text-[#94a3b8]">
                          No orders yet for this customer.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </AdminTableWrap>
            </AdminCard>
          </>
        )}
      </AdminState>
    </div>
  )
}
