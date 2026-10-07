import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'

export type InboxWidgetTab = 'chat' | 'alerts'

export interface OpenInboxOptions {
  tab?: InboxWidgetTab
  conversationId?: number | null
}

interface InboxWidgetContextValue {
  isOpen: boolean
  tab: InboxWidgetTab
  conversationId: number | null
  openInbox: (options?: OpenInboxOptions) => void
  closeInbox: () => void
  toggleInbox: (options?: OpenInboxOptions) => void
  setTab: (tab: InboxWidgetTab) => void
  setConversationId: (id: number | null) => void
}

const InboxWidgetContext = createContext<InboxWidgetContextValue | null>(null)

export function InboxWidgetProvider({ children }: { children: ReactNode }) {
  const [isOpen, setIsOpen] = useState(false)
  const [tab, setTab] = useState<InboxWidgetTab>('chat')
  const [conversationId, setConversationId] = useState<number | null>(null)

  const openInbox = useCallback((options?: OpenInboxOptions) => {
    if (options?.tab) setTab(options.tab)
    if (options && 'conversationId' in options) {
      setConversationId(options.conversationId ?? null)
    }
    setIsOpen(true)
  }, [])

  const closeInbox = useCallback(() => setIsOpen(false), [])

  const toggleInbox = useCallback((options?: OpenInboxOptions) => {
    setIsOpen((open) => {
      if (open && !options?.tab && options?.conversationId == null) return false
      if (options?.tab) setTab(options.tab)
      if (options && 'conversationId' in options) {
        setConversationId(options.conversationId ?? null)
      }
      return true
    })
  }, [])

  const value = useMemo(
    () => ({
      isOpen,
      tab,
      conversationId,
      openInbox,
      closeInbox,
      toggleInbox,
      setTab,
      setConversationId,
    }),
    [isOpen, tab, conversationId, openInbox, closeInbox, toggleInbox],
  )

  return <InboxWidgetContext.Provider value={value}>{children}</InboxWidgetContext.Provider>
}

export function useInboxWidget() {
  const ctx = useContext(InboxWidgetContext)
  if (!ctx) {
    throw new Error('useInboxWidget must be used within InboxWidgetProvider')
  }
  return ctx
}
