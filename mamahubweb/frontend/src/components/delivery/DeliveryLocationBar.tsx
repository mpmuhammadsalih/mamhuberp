import { IconChevronDown, IconMapPin } from '../icons/Icons'
import { useDeliveryLocation } from '../../context/DeliveryLocationContext'
import { useLocale } from '../../i18n/LocaleContext'
import { DEFAULT_ETA_MAX, DEFAULT_ETA_MIN } from '../../lib/deliveryStorage'

export function DeliveryLocationBar({ className = '' }: { className?: string }) {
  const { location, openPicker } = useDeliveryLocation()
  const { t } = useLocale()
  const etaMin = location?.etaMinMinutes || DEFAULT_ETA_MIN
  const etaMax = location?.etaMaxMinutes || DEFAULT_ETA_MAX
  const label = t.delivery.minutesDelivery
    .replace('{min}', String(etaMin))
    .replace('{max}', String(etaMax))

  return (
    <button
      type="button"
      onClick={openPicker}
      className={`flex max-w-[280px] items-center gap-2 rounded-xl px-2 py-1.5 text-left transition hover:bg-brand-tint/60 sm:max-w-none ${className}`}
      aria-label={label}
    >
      <IconMapPin size={18} className="shrink-0 text-brand-accent" />
      <p className="min-w-0 truncate text-xs font-bold text-slate-800 sm:text-sm">{label}</p>
      <IconChevronDown size={14} className="shrink-0 text-slate-400" />
    </button>
  )
}
