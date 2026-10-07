import { useLocale } from '../i18n/LocaleContext'
import { IconChevronLeft, IconChevronRight, IconChevronDown } from './icons/Icons'

interface PaginationProps {
  page: number
  totalPages: number
  pageSize?: number
  pageSizeOptions?: number[]
  onPageChange: (page: number) => void
  onPageSizeChange?: (size: number) => void
}

export function Pagination({
  page,
  totalPages,
  pageSize = 24,
  pageSizeOptions = [12, 24, 48],
  onPageChange,
  onPageSizeChange,
}: PaginationProps) {
  const { t } = useLocale()

  if (totalPages <= 1 && !onPageSizeChange) return null

  const pages = Array.from({ length: Math.min(totalPages, 7) }, (_, i) => {
    if (totalPages <= 7) return i + 1
    if (page <= 4) return i + 1
    if (page >= totalPages - 3) return totalPages - 6 + i
    return page - 3 + i
  })

  return (
    <div className="mt-10 flex flex-col items-center justify-between gap-4 sm:flex-row">
      <div className="flex items-center gap-1.5">
        <button
          type="button"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
          aria-label={t.shared.previousPage}
          className="flex h-9 w-9 items-center justify-center rounded-full border border-gray-200 bg-white text-gray-700 transition hover:border-gray-300 disabled:opacity-40"
        >
          <IconChevronLeft size={18} />
        </button>

        {pages.map((p) => (
          <button
            key={p}
            type="button"
            onClick={() => onPageChange(p)}
            className={`flex h-9 min-w-9 items-center justify-center rounded-full px-2 text-sm font-semibold transition ${
              p === page
                ? 'bg-brand-accent text-white shadow-sm'
                : 'text-gray-700 hover:bg-pink-50'
            }`}
          >
            {p}
          </button>
        ))}

        <button
          type="button"
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
          aria-label={t.shared.nextPage}
          className="flex h-9 w-9 items-center justify-center rounded-full border border-gray-200 bg-white text-gray-700 transition hover:border-gray-300 disabled:opacity-40"
        >
          <IconChevronRight size={18} />
        </button>
      </div>

      {onPageSizeChange && (
        <div className="flex items-center gap-2 font-catalog text-sm text-gray-600">
          <span>{t.shared.show}</span>
          <div className="relative">
            <select
              value={pageSize}
              onChange={(e) => onPageSizeChange(Number(e.target.value))}
              className="appearance-none rounded-lg border border-gray-200 bg-white py-2 pl-3 pr-8 text-sm font-medium text-gray-800 outline-none focus:border-brand-accent"
            >
              {pageSizeOptions.map((size) => (
                <option key={size} value={size}>
                  {size}
                </option>
              ))}
            </select>
            <IconChevronDown
              size={14}
              className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400"
            />
          </div>
        </div>
      )}
    </div>
  )
}
