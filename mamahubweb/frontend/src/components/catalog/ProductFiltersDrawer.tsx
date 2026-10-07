import { useEffect } from 'react'
import { useLocale } from '../../i18n/LocaleContext'
import { IconClose } from '../icons/Icons'
import type { CatalogFilterState } from './CatalogLayout'
import { ProductFiltersSidebar } from './ProductFiltersSidebar'

interface Props extends CatalogFilterState {
  open: boolean
  onClose: () => void
}

export function ProductFiltersDrawer({ open, onClose, ...filterProps }: Props) {
  const { t } = useLocale()

  useEffect(() => {
    if (!open) return undefined

    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }

    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.body.style.overflow = previousOverflow
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open, onClose])

  return (
    <>
      <button
        type="button"
        aria-label={t.shared.cancel}
        aria-hidden={!open}
        tabIndex={open ? 0 : -1}
        className={`fixed inset-0 z-[60] bg-black/40 transition-opacity duration-300 lg:hidden ${
          open ? 'opacity-100' : 'pointer-events-none opacity-0'
        }`}
        onClick={onClose}
      />

      <aside
        className={`fixed inset-y-0 left-0 z-[70] flex w-[min(100vw-2.5rem,320px)] max-w-full flex-col bg-white shadow-2xl transition-transform duration-300 ease-out lg:hidden ${
          open ? 'translate-x-0' : '-translate-x-full pointer-events-none'
        }`}
        role="dialog"
        aria-modal={open}
        aria-hidden={!open}
        aria-label={t.catalog.filters}
      >
        <div className="flex shrink-0 items-center justify-between border-b border-gray-200 px-4 py-3">
          <h2 className="font-display text-base font-bold text-black">{t.catalog.filters}</h2>
          <button
            type="button"
            onClick={onClose}
            className="flex h-9 w-9 items-center justify-center rounded-full text-gray-500 hover:bg-gray-100"
            aria-label={t.shared.cancel}
          >
            <IconClose size={20} />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-3 py-3">
          <ProductFiltersSidebar
            {...filterProps}
            showHeader={false}
            className="rounded-none bg-transparent p-0 shadow-none ring-0"
          />
        </div>

        <div className="shrink-0 border-t border-gray-200 p-4">
          <button
            type="button"
            onClick={onClose}
            className="w-full rounded-full bg-brand-accent py-3 text-sm font-bold text-white hover:bg-brand-accent-hover"
          >
            {t.shared.showResults}
          </button>
        </div>
      </aside>
    </>
  )
}
