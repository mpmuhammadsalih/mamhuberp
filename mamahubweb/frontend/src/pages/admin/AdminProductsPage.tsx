import { Link } from 'react-router-dom'
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
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
import { IconEdit, IconPlus } from '../../components/admin/AdminNavIcons'
import { IconTrash } from '../../components/icons/Icons'
import { ProductImage } from '../../components/ProductImage'
import { formatMoney } from '../../lib/currency'
import { getDataWithMeta } from '../../lib/api'
import { metaFromResponse } from '../../hooks/usePaginationMeta'
import type { Product } from '../../types/api'

const thClass = 'px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-[#94a3b8]'
const tdClass = 'px-4 py-4 text-sm text-[#334155]'

export function AdminProductsPage() {
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)

  const { data: response, isLoading, isError } = useQuery({
    queryKey: ['admin-products', search, page, pageSize],
    queryFn: () =>
      getDataWithMeta<Product[]>('/admin/products', {
        page,
        page_size: pageSize,
        search: search || undefined,
      }),
  })

  const products = response?.data ?? []
  const meta = metaFromResponse(response)

  const filtered = statusFilter
    ? products.filter((p) => {
        const active = (p.current_stock ?? 0) > 0
        return statusFilter === 'active' ? active : !active
      })
    : products

  return (
    <div>
      <AdminPageTitle
        title="Products"
        description="Manage your ERP product catalog."
        action={
          <AdminButton className="gap-2">
            <IconPlus size={16} />
            Add Product
          </AdminButton>
        }
      />

      <div className="mb-4 flex flex-wrap gap-3">
        <AdminSearchInput value={search} onChange={(v) => { setSearch(v); setPage(1) }} placeholder="Search products…" className="w-full max-w-sm" />
        <AdminSelect value={statusFilter} onChange={(v) => setStatusFilter(v)}>
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="inactive">Out of stock</option>
        </AdminSelect>
      </div>

      <AdminState isLoading={isLoading} isError={isError} isEmpty={filtered.length === 0}>
        <AdminTableWrap>
          <table className="w-full min-w-[880px]">
            <thead className="bg-[#fafbfd]">
              <tr>
                <th className={thClass}>Product</th>
                <th className={thClass}>Category</th>
                <th className={thClass}>Price</th>
                <th className={thClass}>Stock</th>
                <th className={thClass}>Status</th>
                <th className={thClass}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((p) => {
                const active = (p.current_stock ?? 0) > 0
                return (
                  <tr key={p.item_code} className="border-t border-[#eef1f6]">
                    <td className={tdClass}>
                      <div className="flex items-center gap-3">
                        <div className="h-12 w-12 overflow-hidden rounded-xl bg-[#f8fafc] ring-1 ring-[#eef1f6]">
                          <ProductImage src={p.primary_image_url} alt={p.item_name || ''} className="h-full w-full object-cover" />
                        </div>
                        <div>
                          <p className="font-medium text-[#0f172a]">{p.item_name}</p>
                          <p className="text-xs text-[#94a3b8]">#{p.item_code}</p>
                        </div>
                      </div>
                    </td>
                    <td className={tdClass}>{p.category_name || '—'}</td>
                    <td className={tdClass}>{formatMoney(p.retail_price ?? 0)}</td>
                    <td className={tdClass}>{p.current_stock}</td>
                    <td className={tdClass}>
                      <StatusBadge status={active ? 'ACTIVE' : 'INACTIVE'} />
                    </td>
                    <td className={tdClass}>
                      <div className="flex items-center gap-2">
                        <Link
                          to={`/admin/products/${p.item_code}`}
                          className="flex h-8 w-8 items-center justify-center rounded-lg text-[#64748b] hover:bg-[#f8fafc] hover:text-[#E91E63]"
                          aria-label="Edit product"
                        >
                          <IconEdit />
                        </Link>
                        <button type="button" className="flex h-8 w-8 items-center justify-center rounded-lg text-[#64748b] hover:bg-red-50 hover:text-red-500" aria-label="Delete product">
                          <IconTrash size={16} />
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}
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
