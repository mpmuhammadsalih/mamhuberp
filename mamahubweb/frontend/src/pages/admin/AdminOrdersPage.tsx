import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { AdminPagination } from '../../components/admin/AdminPagination'
import { AdminState } from '../../components/admin/AdminState'
import {
  AdminButton,
  AdminPageTitle,
  AdminSearchInput,
  AdminSelect,
  AdminTableWrap,
  StatusBadge,
} from '../../components/admin/ui'
import { formatMoney } from '../../lib/currency'
import { getDataWithMeta } from '../../lib/api'
import { metaFromResponse } from '../../hooks/usePaginationMeta'

interface OrderRow {
  order_id: number
  order_number: string
  order_status: string
  payment_status: string
  grand_total: number
  currency_code?: string
  item_count: number
  created_at?: string
  customer_email?: string
}

const STATUS_OPTIONS = [
  '',
  'CONFIRMED',
  'PROCESSING',
  'PICKING',
  'PACKED',
  'OUT_FOR_DELIVERY',
  'DELIVERED',
  'CANCELLED',
] as const

const thClass = 'px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-[#94a3b8]'
const tdClass = 'px-4 py-4 text-sm text-[#334155]'

export function AdminOrdersPage() {
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [statusFilter, setStatusFilter] = useState('')
  const [search, setSearch] = useState('')

  const { data: response, isLoading, isError } = useQuery({
    queryKey: ['admin-orders', page, pageSize, statusFilter],
    queryFn: () =>
      getDataWithMeta<OrderRow[]>('/admin/orders', {
        page,
        page_size: pageSize,
        status: statusFilter || undefined,
      }),
  })

  const orders = response?.data ?? []
  const meta = metaFromResponse(response)

  const filtered = search.trim()
    ? orders.filter(
        (o) =>
          o.order_number.toLowerCase().includes(search.toLowerCase()) ||
          (o.customer_email ?? '').toLowerCase().includes(search.toLowerCase()),
      )
    : orders

  return (
    <div>
      <AdminPageTitle title="Orders" description="Track and manage customer orders." />

      <div className="mb-4 flex flex-wrap gap-3">
        <AdminSearchInput value={search} onChange={setSearch} placeholder="Search orders…" className="w-full max-w-xs" />
        <AdminSelect value={statusFilter} onChange={(v) => { setStatusFilter(v); setPage(1) }}>
          <option value="">All statuses</option>
          {STATUS_OPTIONS.filter(Boolean).map((s) => (
            <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>
          ))}
        </AdminSelect>
        <div className="flex items-center rounded-xl border border-[#e2e8f0] bg-white px-3 py-2 text-sm text-[#64748b]">
          Date range: Last 30 days
        </div>
      </div>

      <AdminState isLoading={isLoading} isError={isError} isEmpty={filtered.length === 0}>
        <AdminTableWrap>
          <table className="w-full min-w-[900px]">
            <thead className="bg-[#fafbfd]">
              <tr>
                <th className={thClass}>Order ID</th>
                <th className={thClass}>Customer</th>
                <th className={thClass}>Date</th>
                <th className={thClass}>Total</th>
                <th className={thClass}>Status</th>
                <th className={thClass}>Action</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((o) => (
                <tr key={o.order_id} className="border-t border-[#eef1f6]">
                  <td className={tdClass}>
                    <Link to={`/admin/orders/${o.order_id}`} className="font-medium text-[#E91E63] hover:underline">
                      {o.order_number}
                    </Link>
                  </td>
                  <td className={tdClass}>{o.customer_email ?? 'Guest'}</td>
                  <td className={tdClass}>{o.created_at ? new Date(o.created_at).toLocaleDateString() : '—'}</td>
                  <td className={tdClass}>{formatMoney(o.grand_total, o.currency_code)}</td>
                  <td className={tdClass}>
                    <StatusBadge status={o.order_status} />
                  </td>
                  <td className={tdClass}>
                    <Link to={`/admin/orders/${o.order_id}`}>
                      <AdminButton variant="secondary" size="sm">View</AdminButton>
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </AdminTableWrap>

        <AdminPagination
          page={page}
          totalPages={meta.total_pages}
          pageSize={pageSize}
          onPageChange={setPage}
          onPageSizeChange={(size) => { setPageSize(size); setPage(1) }}
        />
      </AdminState>
    </div>
  )
}
