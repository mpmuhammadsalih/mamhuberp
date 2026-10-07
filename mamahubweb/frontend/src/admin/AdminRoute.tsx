import { Navigate, Outlet } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { getData } from '../lib/api'
import { storage } from '../lib/storage'

interface Profile {
  email: string
  roles: string[]
  first_name: string
}

export function AdminRoute() {
  const token = storage.getToken()

  const { data: profile, isLoading, isError } = useQuery({
    queryKey: ['admin-profile'],
    queryFn: () => getData<Profile>('/admin/auth/me'),
    enabled: Boolean(token),
    retry: false,
  })

  if (!token) return <Navigate to="/admin/login" replace />
  if (isLoading) return <div className="p-8 text-gray-500">Loading admin...</div>
  if (isError || !profile) return <Navigate to="/admin/login" replace />

  const isAdmin = (profile.roles ?? []).some((r) => ['ADMIN', 'SUPER_ADMIN'].includes(r))
  if (!isAdmin) return <Navigate to="/admin/login" replace />

  return <Outlet />
}
