import type { ReactNode } from 'react'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { categoryDisplayName } from '../../i18n/categoryName'
import { ageGroupDisplayName } from '../../i18n/ageGroupName'
import { brandDisplayName } from '../../i18n/brandName'
import { useLocale } from '../../i18n/LocaleContext'
import { useLocalizedLabel } from '../../i18n/useLocalizedLabel'
import type { CategoryNode } from '../../lib/queries/catalog'
import { IconSearch } from '../icons/Icons'

const VISIBLE_LIMIT = 5
const ACTION =
  'text-[13px] font-normal text-brand-accent hover:text-brand-accent-hover hover:underline'
interface FilterSectionProps {
  title: string
  defaultOpen?: boolean
  children: ReactNode
}

function FilterSection({ title, defaultOpen = false, children }: FilterSectionProps) {
  const [open, setOpen] = useState(defaultOpen)
  const formatLabel = useLocalizedLabel()

  return (
    <div className="border-b border-gray-200 last:border-b-0">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between py-3.5 text-left"
      >
        <span className="text-[13px] font-bold text-black">{formatLabel(title)}</span>
        <span className="text-lg font-light leading-none text-gray-500" aria-hidden>
          {open ? '−' : '+'}
        </span>
      </button>
      {open && <div className="pb-4">{children}</div>}
    </div>
  )
}

interface FilterCheckboxProps {
  label: string
  checked: boolean
  onChange: () => void
  count?: number
}

function FilterCheckbox({ label, checked, onChange, count }: FilterCheckboxProps) {
  const formatLabel = useLocalizedLabel()

  return (
    <button
      type="button"
      onClick={onChange}
      className={`flex w-full cursor-pointer items-center gap-2.5 rounded-lg py-2 pl-1 pr-2 text-left transition hover:bg-pink-50/50 ${
        checked ? 'bg-pink-50/80' : ''
      }`}
    >
      <span
        className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full ${
          checked ? 'bg-brand-accent' : 'bg-brand-tint'
        }`}
      >
        <span className={`h-1.5 w-1.5 rounded-full ${checked ? 'bg-white' : 'bg-[#E91E63]'}`} />
      </span>
      <span className="min-w-0 flex-1 text-[13px] leading-snug text-black">{formatLabel(label)}</span>
      {count != null && <span className="shrink-0 text-[12px] text-gray-400">{count}</span>}
    </button>
  )
}

interface Props {
  categoryTree: CategoryNode[]
  ageGroups: Array<{ slug: string; age_group_name: string }>
  brands: Array<{ code: number; name: string; name_ar?: string | null }>
  interests: Array<{ slug: string; interest_name: string }>
  selectedMain?: string
  selectedDept?: string
  selectedCategory?: string
  selectedAge?: string
  selectedBrand?: string
  selectedInterest?: string
  minPrice?: string
  maxPrice?: string
  showAllItems?: boolean
  onShowAllItemsChange?: (enabled: boolean) => void
  onSelect: (key: string, value: string | null) => void
  onPriceApply: (min: string, max: string) => void
  onClear: () => void
  className?: string
  showHeader?: boolean
}

function matchesQuery(label: string, query: string) {
  return label.toLowerCase().includes(query.trim().toLowerCase())
}

export function ProductFiltersSidebar({
  categoryTree,
  ageGroups,
  brands,
  interests,
  selectedMain,
  selectedDept,
  selectedCategory,
  selectedAge,
  selectedBrand,
  selectedInterest,
  minPrice = '',
  maxPrice = '',
  showAllItems = false,
  onShowAllItemsChange,
  onSelect,
  onPriceApply,
  onClear,
  className = '',
  showHeader = true,
}: Props) {
  const { locale, t } = useLocale()
  const [filterQuery, setFilterQuery] = useState('')
  const [showAllTypes, setShowAllTypes] = useState(false)
  const [showAllBrands, setShowAllBrands] = useState(false)
  const [showAllAge, setShowAllAge] = useState(false)
  const [localMin, setLocalMin] = useState(minPrice)
  const [localMax, setLocalMax] = useState(maxPrice)

  const activeMain = categoryTree.find((m) => String(m.code) === selectedMain)
  const departments = activeMain?.children ?? categoryTree.flatMap((m) => m.children ?? [])
  const subCategories =
    activeMain?.children?.find((d) => String(d.code) === selectedDept)?.children ??
    departments.flatMap((d) => d.children ?? [])

  const productTypes = useMemo(() => {
    if (subCategories.length > 0) {
      return subCategories.map((c) => ({
        key: 'category' as const,
        code: String(c.code),
        name: categoryDisplayName(c, locale),
      }))
    }
    return departments.map((d) => ({
      key: 'dept' as const,
      code: String(d.code),
      name: categoryDisplayName(d, locale),
    }))
  }, [subCategories, departments, locale])

  const brandOptions = useMemo(
    () =>
      brands.map((b) => ({
        ...b,
        label: brandDisplayName(b, locale),
      })),
    [brands, locale],
  )

  const filteredProductTypes = productTypes.filter((item) => matchesQuery(item.name, filterQuery))
  const filteredBrands = brandOptions.filter((b) => matchesQuery(b.label, filterQuery))
  const visibleTypes = showAllTypes ? filteredProductTypes : filteredProductTypes.slice(0, VISIBLE_LIMIT)
  const visibleBrands = showAllBrands ? filteredBrands : filteredBrands.slice(0, VISIBLE_LIMIT)
  const visibleAge = showAllAge ? ageGroups : ageGroups.slice(0, VISIBLE_LIMIT)

  function toggle(key: string, value: string, selected?: string) {
    onSelect(key, selected === value ? null : value)
  }

  function isTypeSelected(item: { key: 'category' | 'dept'; code: string }) {
    return item.key === 'category'
      ? selectedCategory === item.code
      : selectedDept === item.code
  }

  return (
    <aside
      className={`font-catalog rounded-2xl bg-white p-4 shadow-sm ring-1 ring-black/[0.04] sm:p-5 ${className}`}
    >
      {showHeader && (
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-display text-base font-bold text-black">{t.catalog.filters}</h2>
          <button type="button" onClick={onClear} className={ACTION}>
            {t.shared.clearAll}
          </button>
        </div>
      )}

      {!showHeader && (
        <div className="mb-4 flex justify-end">
          <button type="button" onClick={onClear} className={ACTION}>
            {t.shared.clearAll}
          </button>
        </div>
      )}

      <div className="relative mb-5">
        <IconSearch
          size={16}
          className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-[#E91E63]"
        />
        <input
          type="search"
          value={filterQuery}
          onChange={(e) => setFilterQuery(e.target.value)}
          placeholder={t.catalog.searchToys}
          className="w-full rounded-full border border-pink-200 bg-white py-2.5 pl-10 pr-4 text-[13px] text-black outline-none placeholder:text-gray-400 focus:border-[#E91E63] focus:ring-2 focus:ring-pink-100"
        />
      </div>

      {onShowAllItemsChange ? (
        <FilterSection title={t.catalog.availability} defaultOpen>
          <FilterCheckbox
            label={t.shared.showAllIncludeOos}
            checked={showAllItems}
            onChange={() => onShowAllItemsChange(!showAllItems)}
          />
        </FilterSection>
      ) : null}

      <FilterSection title={t.catalog.productType} defaultOpen>
        {visibleTypes.length === 0 ? (
          <p className="text-[13px] text-black">{t.catalog.noProductTypes}</p>
        ) : (
          <div>
            {visibleTypes.map((item) => (
              <FilterCheckbox
                key={`${item.key}-${item.code}`}
                label={item.name}
                checked={isTypeSelected(item)}
                onChange={() => toggle(item.key, item.code, isTypeSelected(item) ? item.code : undefined)}
              />
            ))}
          </div>
        )}
        {filteredProductTypes.length > VISIBLE_LIMIT && !showAllTypes && (
          <button type="button" onClick={() => setShowAllTypes(true)} className={`mt-1 ${ACTION}`}>
            {t.shared.viewAll}
          </button>
        )}
      </FilterSection>

      <FilterSection title={t.catalog.brand} defaultOpen>
        {visibleBrands.length === 0 ? (
          <p className="text-[13px] text-black">{t.catalog.noBrands}</p>
        ) : (
          <div>
            {visibleBrands.map((b) => (
              <FilterCheckbox
                key={b.code}
                label={b.label}
                checked={selectedBrand === String(b.code)}
                onChange={() => toggle('brand', String(b.code), selectedBrand)}
              />
            ))}
          </div>
        )}
        {filteredBrands.length > VISIBLE_LIMIT && !showAllBrands && (
          <button type="button" onClick={() => setShowAllBrands(true)} className={`mt-1 ${ACTION}`}>
            {t.shared.viewAll}
          </button>
        )}
      </FilterSection>

      <FilterSection title={t.catalog.age}>
        <div>
          {visibleAge.map((g) => (
            <FilterCheckbox
              key={g.slug}
              label={ageGroupDisplayName(g, locale, t)}
              checked={selectedAge === g.slug}
              onChange={() => toggle('age', g.slug, selectedAge)}
            />
          ))}
        </div>
        {ageGroups.length > VISIBLE_LIMIT && !showAllAge && (
          <button type="button" onClick={() => setShowAllAge(true)} className={`mt-1 ${ACTION}`}>
            {t.shared.viewAll}
          </button>
        )}
      </FilterSection>

      <FilterSection title={t.catalog.category}>
        <div className="max-h-44 overflow-y-auto">
          {categoryTree.map((main) => (
            <FilterCheckbox
              key={main.code}
              label={categoryDisplayName(main, locale)}
              checked={selectedMain === String(main.code)}
              onChange={() => toggle('main', String(main.code), selectedMain)}
            />
          ))}
        </div>
      </FilterSection>

      <FilterSection title={t.catalog.charactersThemes}>
        <div className="max-h-44 overflow-y-auto">
          {interests.map((i) => (
            <FilterCheckbox
              key={i.slug}
              label={i.interest_name}
              checked={selectedInterest === i.slug}
              onChange={() => toggle('interest', i.slug, selectedInterest)}
            />
          ))}
        </div>
      </FilterSection>

      <FilterSection title={t.catalog.offers}>
        <Link to="/offers" className={`inline-block ${ACTION}`}>
          {t.shared.viewAllOffers}
        </Link>
      </FilterSection>

      <FilterSection title={t.catalog.price}>
        <div className="flex items-center gap-2">
          <input
            type="number"
            min={0}
            placeholder={t.shared.min}
            value={localMin}
            onChange={(e) => setLocalMin(e.target.value)}
            className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-[13px] text-black outline-none focus:border-gray-400"
          />
          <span className="text-gray-400">–</span>
          <input
            type="number"
            min={0}
            placeholder={t.shared.max}
            value={localMax}
            onChange={(e) => setLocalMax(e.target.value)}
            className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-[13px] text-black outline-none focus:border-gray-400"
          />
        </div>
        <button
          type="button"
          onClick={() => onPriceApply(localMin, localMax)}
          className="mt-3 w-full rounded-lg border border-gray-300 bg-white py-2 text-[13px] font-semibold text-black hover:bg-gray-50"
        >
          {t.shared.apply}
        </button>
      </FilterSection>
    </aside>
  )
}
