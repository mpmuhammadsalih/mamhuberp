import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { useInboxWidget } from '../context/InboxWidgetContext'
import { getData } from '../lib/api'
import { storage } from '../lib/storage'
import type { InboxLatest } from '../types/api'

const POLL_MS = 8_000

export function InboxAlertPopup() {
  const queryClient = useQueryClient()
  const { isOpen } = useInboxWidget()
  const loggedIn = storage.hasSession()

  const { data } = useQuery({
    queryKey: ['inbox-latest'],
    queryFn: () => getData<InboxLatest>('/inbox/latest'),
    enabled: loggedIn && !isOpen,
    staleTime: 4_000,
    refetchInterval: POLL_MS,
    refetchOnWindowFocus: true,
  })

  useEffect(() => {
    if (data?.unread) queryClient.setQueryData(['inbox-unread'], data.unread)
  }, [data, queryClient])

  return null
}
