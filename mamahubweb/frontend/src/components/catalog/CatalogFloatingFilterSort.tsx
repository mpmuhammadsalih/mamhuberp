import { useState } from 'react'
import { useLocale } from '../../i18n/LocaleContext'
import { IconFilter, IconSort } from '../icons/Icons'
import { CatalogSortSheet } from './CatalogSortSheet'

interface Props {
  sortValue: string
  onSortChange: (value: string) => void
  onOpenFilters: () => void
  activeFilterCount?: number
}

export function CatalogFloatingFilterSort({
  sortValue,
  onSortChange,
  onOpenFilters,
  activeFilterCount = 0,
}: Props) {
  const { t } = useLocale()
  const [sortOpen, setSortOpen] = useState(false)

  return (
    <>
      <CatalogSortSheet
        open={sortOpen}
        onClose={() => setSortOpen(false)}
        sortValue={sortValue}
        onSortChange={onSortChange}
      />

      <div
        className="pointer-events-none fixed inset-x-0 z-[55] flex justify-center lg:hidden"
        style={{ bottom: 'calc(4.75rem + env(safe-area-inset-bottom, 0px) + 0.625rem)' }}
      >
        <div className="pointer-events-auto flex items-stretch overflow-hidden rounded-full bg-[rgba(28,28,28,0.9)] shadow-[0_6px_28px_rgba(0,0,0,0.28)] backdrop-blur-md">
          <button
            type="button"
            onClick={onOpenFilters}
            className="relative flex items-center gap-2 px-5 py-3 text-sm font-semibold text-white transition active:bg-white/10"
          >
            <IconFilter size={17} />
            {t.shared.filter}
            {activeFilterCount > 0 ? (
              <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-[#E91E63]" aria-hidden />
            ) : null}
          </button>

          <div className="my-2.5 w-px shrink-0 bg-white/25" aria-hidden />

          <button
            type="button"
            onClick={() => setSortOpen(true)}
            className="flex items-center gap-2 px-5 py-3 text-sm font-semibold text-white transition active:bg-white/10"
          >
            <IconSort size={17} />
            {t.shared.sort}
          </button>
        </div>
      </div>
    </>
  )
}
