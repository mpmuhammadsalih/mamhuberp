import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { AdminState } from '../../components/admin/AdminState'
import { AdminPageTitle } from '../../components/admin/ui'
import { AdminPagination } from '../../components/admin/AdminPagination'
import { getData, getDataWithMeta, postData } from '../../lib/api'
import { metaFromResponse } from '../../hooks/usePaginationMeta'

interface StaffUser {
  user_id: number
  email: string
  first_name: string
  last_name: string
  roles: string[]
}

interface Role {
  role_id: number
  role_code: string
  role_name: string
}

export function AdminUsersPage() {
  const queryClient = useQueryClient()
  const [selectedUser, setSelectedUser] = useState<number | null>(null)
  const [roleCode, setRoleCode] = useState('ADMIN')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)

  const { data: usersData, isLoading, isError } = useQuery({
    queryKey: ['admin-users', page, pageSize],
    queryFn: () => getDataWithMeta<StaffUser[]>('/admin/users', { page, page_size: pageSize }),
  })

  const { data: roles = [] } = useQuery({
    queryKey: ['admin-roles'],
    queryFn: () => getData<Role[]>('/admin/roles'),
  })

  const assignRole = useMutation({
    mutationFn: () => postData(`/admin/users/${selectedUser}/roles`, { role_code: roleCode }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin-users'] }),
  })

  const users = usersData?.data ?? []
  const meta = metaFromResponse(usersData)

  return (
    <div>
      <AdminPageTitle title="Users & roles" description="Staff accounts and role assignments." />

      <AdminState isLoading={isLoading} isError={isError} isEmpty={users.length === 0}>
        <div className="overflow-x-auto rounded-2xl bg-white shadow-sm ring-1 ring-slate-200">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-slate-500">
              <tr>
                <th className="px-4 py-3">User</th>
                <th className="px-4 py-3">Email</th>
                <th className="px-4 py-3">Roles</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.user_id} className="border-t border-slate-100">
                  <td className="px-4 py-3">
                    {u.first_name} {u.last_name}
                  </td>
                  <td className="px-4 py-3">{u.email}</td>
                  <td className="px-4 py-3">{u.roles?.join(', ') || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

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

      <section className="mt-8 rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
        <h2 className="font-semibold text-slate-900">Assign role</h2>
        <div className="mt-3 flex flex-wrap gap-3">
          <select
            value={selectedUser ?? ''}
            onChange={(e) => setSelectedUser(Number(e.target.value))}
            className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
          >
            <option value="">Select user</option>
            {users.map((u) => (
              <option key={u.user_id} value={u.user_id}>
                {u.email}
              </option>
            ))}
          </select>
          <select
            value={roleCode}
            onChange={(e) => setRoleCode(e.target.value)}
            className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
          >
            {roles.map((r) => (
              <option key={r.role_id} value={r.role_code}>
                {r.role_name}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => assignRole.mutate()}
            disabled={!selectedUser || assignRole.isPending}
            className="rounded-xl bg-brand-accent px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          >
            Assign
          </button>
        </div>
      </section>
    </div>
  )
}
