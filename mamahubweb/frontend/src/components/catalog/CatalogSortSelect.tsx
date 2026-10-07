import { getSortOptions } from '../../i18n/sortOptions'
import { useLocale } from '../../i18n/LocaleContext'
import { IconChevronDown } from '../icons/Icons'

interface Props {
  sortValue: string
  onSortChange: (value: string) => void
  className?: string
  showLabel?: boolean
}

export function CatalogSortSelect({
  sortValue,
  onSortChange,
  className = '',
  showLabel = true,
}: Props) {
  const { t } = useLocale()
  const sortOptions = getSortOptions(t)

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      {showLabel ? (
        <span className="text-[13px] font-bold text-gray-900">{t.shared.sortedBy}</span>
      ) : null}
      <div className="relative">
        <select
          value={sortValue}
          onChange={(e) => onSortChange(e.target.value)}
          className="appearance-none rounded-lg border border-gray-300 bg-white py-2 pl-3 pr-9 text-[13px] font-medium text-gray-800 outline-none focus:border-gray-400"
          aria-label={t.shared.sortProducts}
        >
          {sortOptions.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        <IconChevronDown
          size={14}
          className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-gray-500"
        />
      </div>
    </div>
  )
}
