import { useCallback, useEffect, useRef, useState } from 'react'
import { categoryDisplayName } from '../../i18n/categoryName'
import { useLocale } from '../../i18n/LocaleContext'
import { useLocalizedLabel } from '../../i18n/useLocalizedLabel'
import type { CategoryNode } from '../../lib/queries/catalog'
import type { SupportedLocale } from '../../i18n/types'
import { IconChevronLeft, IconChevronRight } from '../icons/Icons'
import { CatalogSortSelect } from './CatalogSortSelect'

export interface CategoryPill {
  key: string
  paramKey: 'main' | 'dept' | 'category' | 'all'
  value: string | null
  label: string
  active: boolean
}

export function buildCategoryPills(
  categoryTree: CategoryNode[],
  selectedMain?: string,
  selectedDept?: string,
  selectedCategory?: string,
  allProductsLabel = 'All Products',
  locale: SupportedLocale = 'en',
): CategoryPill[] {
  const activeMain = categoryTree.find((m) => String(m.code) === selectedMain)
  const activeDept = activeMain?.children?.find((d) => String(d.code) === selectedDept)
  const subCategories = activeDept?.children ?? []

  if (selectedDept && subCategories.length > 0) {
    return [
      {
        key: 'all',
        paramKey: 'all',
        value: null,
        label: allProductsLabel,
        active: !selectedCategory,
      },
      ...subCategories.map((c) => ({
        key: `category-${c.code}`,
        paramKey: 'category' as const,
        value: String(c.code),
        label: categoryDisplayName(c, locale),
        active: selectedCategory === String(c.code),
      })),
    ]
  }

  if (selectedMain && activeMain?.children?.length) {
    return [
      {
        key: 'all',
        paramKey: 'all',
        value: null,
        label: allProductsLabel,
        active: !selectedDept && !selectedCategory,
      },
      ...activeMain.children.map((d) => ({
        key: `dept-${d.code}`,
        paramKey: 'dept' as const,
        value: String(d.code),
        label: categoryDisplayName(d, locale),
        active: selectedDept === String(d.code),
      })),
    ]
  }

  return [
    {
      key: 'all',
      paramKey: 'all',
      value: null,
      label: allProductsLabel,
      active: !selectedMain,
    },
    ...categoryTree.map((m) => ({
      key: `main-${m.code}`,
      paramKey: 'main' as const,
      value: String(m.code),
      label: categoryDisplayName(m, locale),
      active: selectedMain === String(m.code),
    })),
  ]
}

interface Props {
  categoryTree: CategoryNode[]
  selectedMain?: string
  selectedDept?: string
  selectedCategory?: string
  totalCount?: number
  sortValue: string
  showAllItems?: boolean
  onShowAllItemsChange?: (enabled: boolean) => void
  onCategorySelect: (pill: CategoryPill) => void
  onSortChange: (value: string) => void
}

const SCROLL_STEP = 220

export function CatalogCategoryToolbar({
  categoryTree,
  selectedMain,
  selectedDept,
  selectedCategory,
  totalCount,
  sortValue,
  showAllItems = false,
  onShowAllItemsChange,
  onCategorySelect,
  onSortChange,
}: Props) {
  const { locale, t } = useLocale()
  const formatLabel = useLocalizedLabel()
  const scrollRef = useRef<HTMLDivElement>(null)
  const [canPrev, setCanPrev] = useState(false)
  const [canNext, setCanNext] = useState(false)

  const pills = buildCategoryPills(
    categoryTree,
    selectedMain,
    selectedDept,
    selectedCategory,
    t.shared.allProducts,
    locale,
  )

  const updateScrollState = useCallback(() => {
    const el = scrollRef.current
    if (!el) return
    setCanPrev(el.scrollLeft > 4)
    setCanNext(el.scrollLeft + el.clientWidth < el.scrollWidth - 4)
  }, [])

  useEffect(() => {
    updateScrollState()
    const el = scrollRef.current
    if (!el) return undefined

    el.addEventListener('scroll', updateScrollState, { passive: true })
    window.addEventListener('resize', updateScrollState)
    return () => {
      el.removeEventListener('scroll', updateScrollState)
      window.removeEventListener('resize', updateScrollState)
    }
  }, [updateScrollState, pills])

  function scrollBy(delta: number) {
    scrollRef.current?.scrollBy({ left: delta, behavior: 'smooth' })
  }

  return (
    <div className="mb-5 flex flex-col gap-4 lg:mb-6 lg:flex-row lg:items-center lg:justify-between">
      <div className="flex min-w-0 flex-1 items-center gap-2">
        <button
          type="button"
          onClick={() => scrollBy(-SCROLL_STEP)}
          disabled={!canPrev}
          aria-label={t.shared.previousCategories}
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-gray-300 bg-white transition enabled:text-gray-800 enabled:hover:border-gray-400 disabled:cursor-default disabled:text-gray-300"
        >
          <IconChevronLeft size={18} />
        </button>

        <div
          ref={scrollRef}
          className="flex min-w-0 flex-1 gap-2 overflow-x-auto scrollbar-hide py-0.5"
        >
          {pills.map((pill) => {
            const showCount = pill.paramKey === 'all' && pill.active && totalCount != null
            const label = showCount
              ? `${pill.label} (${totalCount})`
              : pill.label

            return (
              <button
                key={pill.key}
                type="button"
                onClick={() => onCategorySelect(pill)}
                className={`shrink-0 rounded-full px-4 py-2 text-[13px] font-semibold transition ${
                  pill.active
                    ? 'bg-brand-accent text-white shadow-sm'
                    : 'border border-gray-300 bg-white text-black hover:border-brand-border hover:bg-brand-cream-alt'
                }`}
              >
                {formatLabel(label)}
              </button>
            )
          })}
        </div>

        <button
          type="button"
          onClick={() => scrollBy(SCROLL_STEP)}
          disabled={!canNext}
          aria-label={t.shared.nextCategories}
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-gray-300 bg-white transition enabled:text-gray-900 enabled:hover:border-gray-400 disabled:cursor-default disabled:text-gray-300"
        >
          <IconChevronRight size={18} />
        </button>
      </div>

      <div className="hidden shrink-0 flex-wrap items-center gap-3 lg:flex lg:pl-4">
        {onShowAllItemsChange ? (
          <label className="flex cursor-pointer items-center gap-2 rounded-lg border border-gray-300 bg-white px-3 py-2 text-[13px] font-medium text-gray-800">
            <input
              type="checkbox"
              checked={showAllItems}
              onChange={(e) => onShowAllItemsChange(e.target.checked)}
              className="h-4 w-4 rounded border-gray-300 text-brand-accent focus:ring-brand-tint"
            />
            {t.shared.showAllItems}
          </label>
        ) : null}

        <CatalogSortSelect sortValue={sortValue} onSortChange={onSortChange} />
      </div>
    </div>
  )
}
