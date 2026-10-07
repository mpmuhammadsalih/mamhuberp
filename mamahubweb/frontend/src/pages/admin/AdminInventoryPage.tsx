import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { AdminPagination } from '../../components/admin/AdminPagination'
import { AdminState } from '../../components/admin/AdminState'
import { AdminPageTitle, AdminSearchInput, AdminTableWrap } from '../../components/admin/ui'
import { getDataWithMeta } from '../../lib/api'
import { formatMoney } from '../../lib/currency'
import { metaFromResponse } from '../../hooks/usePaginationMeta'

interface InventoryRow {
  item_code: number
  item_name: string
  current_stock: number
  retail_price: number
}

const thClass = 'px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-[#94a3b8]'
const tdClass = 'px-4 py-4 text-sm text-[#334155]'

export function AdminInventoryPage() {
  const [lowOnly, setLowOnly] = useState(false)
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)

  const { data: response, isLoading, isError } = useQuery({
    queryKey: ['admin-inventory', lowOnly, search, page, pageSize],
    queryFn: () =>
      getDataWithMeta<InventoryRow[]>('/admin/inventory', {
        low_stock_only: lowOnly,
        search: search || undefined,
        page,
        page_size: pageSize,
      }),
  })

  const rows = response?.data ?? []
  const meta = metaFromResponse(response)

  return (
    <div>
      <AdminPageTitle title="Inventory" description="Monitor stock levels and low-inventory alerts." />

      <div className="mb-4 flex flex-wrap gap-3">
        <AdminSearchInput
          value={search}
          onChange={(v) => {
            setSearch(v)
            setPage(1)
          }}
          placeholder="Search inventory…"
          className="max-w-sm"
        />
        <label className="flex items-center gap-2 rounded-xl border border-[#e2e8f0] bg-white px-3 py-2 text-sm text-[#64748b]">
          <input type="checkbox" checked={lowOnly} onChange={(e) => { setLowOnly(e.target.checked); setPage(1) }} />
          Low stock only (≤5)
        </label>
      </div>

      <AdminState isLoading={isLoading} isError={isError} isEmpty={rows.length === 0}>
        <AdminTableWrap>
          <table className="w-full min-w-[640px]">
            <thead className="bg-[#fafbfd]">
              <tr>
                <th className={thClass}>Code</th>
                <th className={thClass}>Name</th>
                <th className={thClass}>Stock</th>
                <th className={thClass}>Price</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.item_code} className="border-t border-[#eef1f6]">
                  <td className={tdClass}>
                    <Link to={`/admin/products/${r.item_code}`} className="font-medium text-[#E91E63] hover:underline">
                      {r.item_code}
                    </Link>
                  </td>
                  <td className={tdClass}>{r.item_name}</td>
                  <td className={`${tdClass} ${r.current_stock <= 5 ? 'font-bold text-red-600' : ''}`}>
                    {r.current_stock}
                  </td>
                  <td className={tdClass}>{formatMoney(r.retail_price)}</td>
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
          onPageSizeChange={(size) => {
            setPageSize(size)
            setPage(1)
          }}
        />
      </AdminState>
    </div>
  )
}
