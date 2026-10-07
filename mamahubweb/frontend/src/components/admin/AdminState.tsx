import type { ReactNode } from 'react'
import { AdminCard } from './ui'

interface Props {
  isLoading?: boolean
  isError?: boolean
  isEmpty?: boolean
  loadingText?: string
  errorText?: string
  emptyText?: string
  children: ReactNode
}

export function AdminState({
  isLoading,
  isError,
  isEmpty,
  loadingText = 'Loading…',
  errorText = 'Something went wrong. Please try again.',
  emptyText = 'No records found.',
  children,
}: Props) {
  if (isLoading) {
    return (
      <AdminCard>
        <p className="text-sm text-[#64748b]">{loadingText}</p>
      </AdminCard>
    )
  }
  if (isError) {
    return (
      <AdminCard className="border-red-100 bg-red-50">
        <p className="text-sm text-red-600">{errorText}</p>
      </AdminCard>
    )
  }
  if (isEmpty) {
    return (
      <AdminCard>
        <p className="text-sm text-[#64748b]">{emptyText}</p>
      </AdminCard>
    )
  }
  return <>{children}</>
}

export { AdminPageTitle as AdminPageHeader } from './ui'
