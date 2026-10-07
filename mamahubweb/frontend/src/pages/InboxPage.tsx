import { useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useInboxWidget } from '../context/InboxWidgetContext'

export function InboxPage() {
  const { openInbox } = useInboxWidget()
  const [params] = useSearchParams()
  const navigate = useNavigate()

  const tab = params.get('tab') === 'alerts' ? 'alerts' : 'chat'

  useEffect(() => {
    openInbox({ tab })
    navigate('/', { replace: true })
  }, [navigate, openInbox, tab])

  return null
}
