import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { useInboxWidget } from '../context/InboxWidgetContext'
import { useLocale } from '../i18n/LocaleContext'
import { getData } from '../lib/api'
import { storage } from '../lib/storage'
import type { InboxUnread } from '../types/api'
import { InboxClearChatButton, InboxPanel } from './InboxPanel'
import { IconChat, IconClose } from './icons/Icons'

export function InboxWidget({
  aboveMobileNav = true,
  hideLauncher = false,
}: {
  aboveMobileNav?: boolean
  hideLauncher?: boolean
}) {
  const { t } = useLocale()
  const { isOpen, tab, toggleInbox, closeInbox } = useInboxWidget()
  const closeRef = useRef<HTMLButtonElement>(null)
  const loggedIn = storage.hasSession()

  const { data: unread } = useQuery({
    queryKey: ['inbox-unread'],
    queryFn: () => getData<InboxUnread>('/inbox/unread-count'),
    enabled: loggedIn,
    refetchInterval: 20_000,
  })
  const inboxCount = unread?.total ?? 0

  useEffect(() => {
    if (!isOpen) return undefined
    closeRef.current?.focus()
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') closeInbox()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [isOpen, closeInbox])

  if (typeof document === 'undefined') return null
  if (hideLauncher && !isOpen) return null

  const dockClass = aboveMobileNav
    ? 'bottom-[calc(11.25rem+env(safe-area-inset-bottom,0px))] end-3 md:bottom-6 md:end-4'
    : 'bottom-4 end-3 md:bottom-6 md:end-4'

  if (!isOpen) {
    return createPortal(
      <button
        type="button"
        onClick={() => toggleInbox()}
        className={`fixed z-[210] flex items-center gap-2 rounded-full bg-white py-1.5 ps-1.5 pe-3.5 text-slate-800 shadow-[0_8px_24px_rgba(15,23,42,0.16)] ring-1 ring-black/5 transition hover:shadow-[0_10px_28px_rgba(15,23,42,0.2)] ${dockClass}`}
        aria-label={`${t.inbox.title}${inboxCount ? `, ${inboxCount}` : ''}`}
      >
        <span className="relative flex h-9 w-9 items-center justify-center rounded-full bg-brand-accent text-white">
          <IconChat size={18} />
          {inboxCount > 0 ? (
            <span className="absolute -end-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-slate-800 px-1 text-[9px] font-bold text-white">
              {inboxCount > 99 ? '99+' : inboxCount}
            </span>
          ) : null}
        </span>
        <span className="text-sm font-semibold">{t.inbox.title}</span>
      </button>,
      document.body,
    )
  }

  return createPortal(
    <div
      className={`fixed z-[210] flex w-[min(20rem,calc(100vw-1.5rem))] flex-col overflow-hidden rounded-2xl bg-white shadow-[0_16px_40px_rgba(15,23,42,0.22)] ring-1 ring-brand-border ${
        aboveMobileNav
          ? 'bottom-[calc(6.25rem+env(safe-area-inset-bottom,0px))] end-3 h-[min(22rem,calc(100dvh-8.5rem))] md:bottom-6 md:end-4 md:h-80'
          : 'bottom-4 end-3 h-[min(22rem,calc(100dvh-2rem))] md:bottom-6 md:end-4 md:h-80'
      }`}
      role="dialog"
      aria-modal="false"
      aria-labelledby="inbox-widget-title"
    >
      <header className="flex shrink-0 items-center justify-between gap-2 bg-brand-accent px-3 py-2 text-white">
        <h2 id="inbox-widget-title" className="min-w-0 truncate text-sm font-semibold">
          {t.inbox.title}
        </h2>
        <div className="flex shrink-0 items-center gap-1">
          {tab === 'chat' ? (
            <InboxClearChatButton className="rounded-full px-2.5 py-1 text-[11px] font-semibold text-white hover:bg-white/15 disabled:opacity-50" />
          ) : null}
          <button
            ref={closeRef}
            type="button"
            onClick={closeInbox}
            className="flex h-8 w-8 items-center justify-center rounded-full bg-white/15 hover:bg-white/25"
            aria-label={t.inbox.popupClose}
          >
            <IconClose size={16} />
          </button>
        </div>
      </header>
      <InboxPanel />
    </div>,
    document.body,
  )
}
