import { useEffect } from 'react'
import { getSortOptions } from '../../i18n/sortOptions'
import { useLocale } from '../../i18n/LocaleContext'
import { IconClose } from '../icons/Icons'

interface Props {
  open: boolean
  onClose: () => void
  sortValue: string
  onSortChange: (value: string) => void
}

export function CatalogSortSheet({ open, onClose, sortValue, onSortChange }: Props) {
  const { t } = useLocale()
  const sortOptions = getSortOptions(t)

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

  function handleSelect(value: string) {
    onSortChange(value)
    onClose()
  }

  return (
    <>
      <button
        type="button"
        aria-label={t.shared.sortBy}
        aria-hidden={!open}
        tabIndex={open ? 0 : -1}
        className={`fixed inset-0 z-[60] bg-black/40 transition-opacity duration-300 lg:hidden ${
          open ? 'opacity-100' : 'pointer-events-none opacity-0'
        }`}
        onClick={onClose}
      />

      <div
        className={`fixed inset-x-0 bottom-0 z-[70] rounded-t-2xl bg-white shadow-2xl transition-transform duration-300 ease-out lg:hidden ${
          open ? 'translate-y-0' : 'translate-y-full pointer-events-none'
        }`}
        style={{ paddingBottom: 'env(safe-area-inset-bottom, 0px)' }}
        role="dialog"
        aria-modal={open}
        aria-hidden={!open}
        aria-label={t.shared.sortProducts}
      >
        <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3">
          <h2 className="font-display text-base font-bold text-black">{t.shared.sortBy}</h2>
          <button
            type="button"
            onClick={onClose}
            className="flex h-9 w-9 items-center justify-center rounded-full text-gray-500 hover:bg-gray-100"
            aria-label={t.shared.cancel}
          >
            <IconClose size={20} />
          </button>
        </div>

        <ul className="max-h-[min(60vh,420px)] overflow-y-auto overscroll-contain py-1">
          {sortOptions.map((opt) => {
            const selected = sortValue === opt.value
            return (
              <li key={opt.value}>
                <button
                  type="button"
                  onClick={() => handleSelect(opt.value)}
                  className={`flex w-full items-center justify-between px-4 py-3.5 text-left text-[15px] transition ${
                    selected ? 'bg-pink-50 font-semibold text-[#E91E63]' : 'font-medium text-gray-900 hover:bg-gray-50'
                  }`}
                >
                  {opt.label}
                  {selected ? (
                    <span className="flex h-5 w-5 items-center justify-center rounded-full bg-brand-accent text-[11px] text-white">
                      ✓
                    </span>
                  ) : null}
                </button>
              </li>
            )
          })}
        </ul>
      </div>
    </>
  )
}
