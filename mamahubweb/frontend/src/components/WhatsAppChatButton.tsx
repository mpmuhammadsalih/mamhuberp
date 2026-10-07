import { IconWhatsApp } from './icons/Icons'
import { useInboxWidget } from '../context/InboxWidgetContext'
import { useLocale } from '../i18n/LocaleContext'
import { buildWhatsAppUrl, getWhatsAppNumber } from '../lib/whatsapp'

interface Props {
  /** Lift above mobile bottom nav when true */
  aboveMobileNav?: boolean
}

export function WhatsAppChatButton({ aboveMobileNav = true }: Props) {
  const { t } = useLocale()
  const { isOpen } = useInboxWidget()
  const number = getWhatsAppNumber()
  if (!number || isOpen) return null

  const href = buildWhatsAppUrl(number, t.shared.whatsappMessage)

  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className={`fixed right-4 z-40 flex h-14 w-14 items-center justify-center rounded-full bg-[#25D366] text-white shadow-[0_8px_24px_rgba(37,211,102,0.45)] ring-4 ring-white/90 transition hover:scale-105 hover:bg-[#20BD5A] active:scale-95 md:hidden ${
        aboveMobileNav
          ? 'bottom-[calc(5.75rem+env(safe-area-inset-bottom,0px))]'
          : 'bottom-[calc(1.25rem+env(safe-area-inset-bottom,0px))]'
      }`}
      aria-label={t.shared.chatOnWhatsApp}
    >
      <IconWhatsApp size={28} />
    </a>
  )
}
