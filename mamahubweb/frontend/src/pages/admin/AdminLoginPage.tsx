import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AdminButton, AdminCard, AdminField, AdminInput } from '../../components/admin/ui'
import { postData, getData } from '../../lib/api'
import { queryClient } from '../../lib/queryClient'
import { storage } from '../../lib/storage'

export function AdminLoginPage() {
  const navigate = useNavigate()
  const [email, setEmail] = useState('admin@mamahub.store')
  const [password, setPassword] = useState('Admin@123')
  const [error, setError] = useState('')

  const login = useMutation({
    mutationFn: async () => {
      const data = await postData<{ tokens: { access_token: string }; user: { roles: string[] } }>(
        '/admin/auth/login',
        { email, password },
      )
      storage.setToken(data.tokens.access_token)
      const profile = await getData<{ roles: string[] }>('/admin/auth/me')
      const ok = profile.roles.some((r: string) => ['ADMIN', 'SUPER_ADMIN'].includes(r))
      if (!ok) {
        storage.clearToken()
        throw new Error('This account does not have admin access')
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-profile'] })
      navigate('/admin')
    },
    onError: (e: Error) => setError(e.message || 'Login failed'),
  })

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#f4f6fb] px-4">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-[#E91E63] text-lg font-bold text-white shadow-lg">
            MH
          </div>
          <h1 className="text-2xl font-bold text-[#0f172a]">MamaHub Admin</h1>
          <p className="mt-1 text-sm text-[#64748b]">Sign in to manage your store</p>
        </div>

        <AdminCard>
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault()
              setError('')
              login.mutate()
            }}
          >
            <AdminField label="Email">
              <AdminInput type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
            </AdminField>
            <AdminField label="Password">
              <AdminInput type="password" required value={password} onChange={(e) => setPassword(e.target.value)} />
            </AdminField>
            {error && <p className="text-sm text-red-600">{error}</p>}
            <AdminButton type="submit" disabled={login.isPending} className="w-full">
              {login.isPending ? 'Signing in…' : 'Sign in'}
            </AdminButton>
          </form>
        </AdminCard>
      </div>
    </div>
  )
}
