import { Link } from 'react-router-dom'
import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AdminPagination } from '../../components/admin/AdminPagination'
import { AdminState } from '../../components/admin/AdminState'
import {
  AdminAvatar,
  AdminButton,
  AdminPageTitle,
  AdminSearchInput,
  AdminTableWrap,
} from '../../components/admin/ui'
import { IconEdit, IconPlus } from '../../components/admin/AdminNavIcons'
import { getDataWithMeta } from '../../lib/api'
import { metaFromResponse } from '../../hooks/usePaginationMeta'

interface Customer {
  user_id: number
  email: string
  first_name: string
  last_name: string
  account_status: string
  created_at?: string
}

const thClass = 'px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-[#94a3b8]'
const tdClass = 'px-4 py-4 text-sm text-[#334155]'

export function AdminCustomersPage() {
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)

  const { data: response, isLoading, isError } = useQuery({
    queryKey: ['admin-customers', page, pageSize],
    queryFn: () => getDataWithMeta<Customer[]>('/admin/customers', { page, page_size: pageSize }),
  })

  const customers = response?.data ?? []
  const meta = metaFromResponse(response)

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return customers
    return customers.filter(
      (c) =>
        c.email.toLowerCase().includes(q) ||
        `${c.first_name} ${c.last_name}`.toLowerCase().includes(q),
    )
  }, [customers, search])

  return (
    <div>
      <AdminPageTitle
        title="Customers"
        description="View and manage registered customers."
        action={
          <AdminButton className="gap-2">
            <IconPlus size={16} />
            Add Customer
          </AdminButton>
        }
      />

      <div className="mb-4">
        <AdminSearchInput
          value={search}
          onChange={setSearch}
          placeholder="Search customers…"
          className="max-w-sm"
        />
      </div>

      <AdminState isLoading={isLoading} isError={isError} isEmpty={filtered.length === 0}>
        <AdminTableWrap>
          <table className="w-full min-w-[720px]">
            <thead className="bg-[#fafbfd]">
              <tr>
                <th className={thClass}>Customer</th>
                <th className={thClass}>Email</th>
                <th className={thClass}>Status</th>
                <th className={thClass}>Joined</th>
                <th className={thClass}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((c) => (
                <tr key={c.user_id} className="border-t border-[#eef1f6]">
                  <td className={tdClass}>
                    <div className="flex items-center gap-3">
                      <AdminAvatar name={`${c.first_name} ${c.last_name}`} />
                      <Link to={`/admin/customers/${c.user_id}`} className="font-medium text-[#0f172a] hover:text-[#E91E63]">
                        {c.first_name} {c.last_name}
                      </Link>
                    </div>
                  </td>
                  <td className={tdClass}>{c.email}</td>
                  <td className={tdClass}>{c.account_status}</td>
                  <td className={tdClass}>
                    {c.created_at ? new Date(c.created_at).toLocaleDateString() : '—'}
                  </td>
                  <td className={tdClass}>
                    <Link
                      to={`/admin/customers/${c.user_id}`}
                      className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-[#64748b] hover:bg-[#f8fafc] hover:text-[#E91E63]"
                    >
                      <IconEdit />
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </AdminTableWrap>

        {!search && (
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
        )}
      </AdminState>
    </div>
  )
}
