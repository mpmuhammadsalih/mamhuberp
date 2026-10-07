import { useQuery } from '@tanstack/react-query'
import { LanguageSwitcher } from './LanguageSwitcher'
import { IconChevronDown, IconQatarFlag, IconRefresh, IconShield, IconTruck } from '../icons/Icons'
import { useDeliveryLocation } from '../../context/DeliveryLocationContext'
import { useLocale } from '../../i18n/LocaleContext'
import { storefrontQueries } from '../../lib/queries/storefront'
import { HOME_CONTAINER } from './homeLayout'

function locationLabel(
  location: { street?: string | null; areaLabel?: string | null; city?: string | null; fullLabel?: string } | null,
  fallback: string,
) {
  if (!location) return fallback
  const parts = [location.areaLabel, location.city]
    .map((part) => part?.trim())
    .filter((part, index, all): part is string => Boolean(part) && all.indexOf(part) === index)
  return parts.join(', ') || location.street?.trim() || location.fullLabel || fallback
}

function pickTrustText(locale: string, localized?: string | null, english?: string | null, fallback = '') {
  const ar = localized?.trim()
  const en = english?.trim()
  if (locale === 'ar') return ar || en || fallback
  return en || fallback
}

export function HeaderTrustBar() {
  const { locale, t } = useLocale()
  const { location, openPicker } = useDeliveryLocation()
  const { data: settings } = useQuery(storefrontQueries.settings)
  const place = locationLabel(location, t.headerBar.countryQatar)
  const deliveryText = pickTrustText(
    locale,
    settings?.header_trust_delivery_ar,
    settings?.header_trust_delivery,
    t.headerBar.freeDelivery,
  )
  const originalText = pickTrustText(
    locale,
    settings?.header_trust_original_ar,
    settings?.header_trust_original,
    t.headerBar.originalToys,
  )
  const returnsText = pickTrustText(
    locale,
    settings?.header_trust_returns_ar,
    settings?.header_trust_returns,
    t.headerBar.easyReturns,
  )

  return (
    <div className="relative z-[80] hidden overflow-visible bg-brand-yellow text-[13px] font-semibold text-brand-ink md:block">
      <div className={`${HOME_CONTAINER} flex items-center justify-between gap-4 py-2`}>
        <ul className="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-1">
          <li className="inline-flex items-center gap-1.5">
            <IconTruck size={16} className="shrink-0 text-brand-teal" />
            <span>{deliveryText}</span>
          </li>
          <li className="hidden h-3.5 w-px bg-brand-ink/15 lg:block" aria-hidden />
          <li className="hidden items-center gap-1.5 lg:inline-flex">
            <IconShield size={16} className="shrink-0 text-brand-accent" />
            <span>{originalText}</span>
          </li>
          <li className="hidden h-3.5 w-px bg-brand-ink/15 xl:block" aria-hidden />
          <li className="hidden items-center gap-1.5 xl:inline-flex">
            <IconRefresh size={16} className="shrink-0 text-brand-orange" />
            <span>{returnsText}</span>
          </li>
        </ul>

        <div className="flex shrink-0 items-center gap-4">
          <LanguageSwitcher variant="menu" />
          <button
            type="button"
            onClick={openPicker}
            className="inline-flex max-w-[16rem] items-center gap-1.5 text-[13px] font-semibold text-brand-ink transition hover:text-brand-accent"
            aria-label={
              location
                ? `${t.nav.deliveryLocation}: ${place}`
                : t.nav.setDelivery
            }
          >
            <IconQatarFlag size={18} />
            <span className="truncate">{place}</span>
            <IconChevronDown size={12} className="shrink-0 text-brand-ink/70" />
          </button>
        </div>
      </div>
    </div>
  )
}
