import type { TranslationTree } from '../../i18n/types'

interface LocationPermissionBannerProps {
  visible: boolean
  t: TranslationTree
  onAllow: () => void
}

export function LocationPermissionBanner({ visible, t, onAllow }: LocationPermissionBannerProps) {
  if (!visible) return null
  return (
    <div className="mb-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-3 text-sm text-amber-950">
      <p className="font-semibold">{t.delivery.locationBlocked}</p>
      <p className="mt-1 text-xs leading-5 text-amber-900/80">{t.delivery.locationBlockedHint}</p>
      <button
        type="button"
        onClick={onAllow}
        className="mt-3 inline-flex rounded-full bg-brand-accent px-4 py-2 text-xs font-bold text-white shadow-sm hover:bg-brand-accent-hover"
      >
        {t.delivery.allowLocation}
      </button>
    </div>
  )
}
