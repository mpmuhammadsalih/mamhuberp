import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { getCollectionToolbarLinks } from '../layout/categoryNavLinks'
import { useLocale } from '../../i18n/LocaleContext'
import { IconChevronLeft, IconChevronRight } from '../icons/Icons'
import { toTitleCase } from '../../lib/textCase'
import { CatalogSortSelect } from './CatalogSortSelect'

interface Props {
  activeCollection: string
  totalCount?: number
  sortValue: string
  onSortChange: (value: string) => void
}

const SCROLL_STEP = 220

export function CatalogCollectionToolbar({
  activeCollection,
  totalCount,
  sortValue,
  onSortChange,
}: Props) {
  const { t } = useLocale()
  const collections = getCollectionToolbarLinks(t)
  const scrollRef = useRef<HTMLDivElement>(null)
  const [canPrev, setCanPrev] = useState(false)
  const [canNext, setCanNext] = useState(false)

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
  }, [updateScrollState])

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
          aria-label="Previous collections"
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-gray-300 bg-white transition enabled:text-gray-800 enabled:hover:border-gray-400 disabled:cursor-default disabled:text-gray-300"
        >
          <IconChevronLeft size={18} />
        </button>

        <div
          ref={scrollRef}
          className="flex min-w-0 flex-1 gap-2 overflow-x-auto scrollbar-hide py-0.5"
        >
          {collections.map((item) => {
            const active = activeCollection === item.slug
            const label =
              active && totalCount != null
                ? `${item.label} (${totalCount.toLocaleString()})`
                : item.label

            return (
              <Link
                key={item.slug}
                to={`/${item.slug}`}
                className={`shrink-0 rounded-full px-4 py-2 text-[13px] font-semibold transition ${
                  active
                    ? 'bg-brand-accent text-white shadow-sm'
                    : 'border border-gray-300 bg-white text-black hover:border-brand-border hover:bg-brand-cream-alt'
                }`}
              >
                {toTitleCase(label)}
              </Link>
            )
          })}
        </div>

        <button
          type="button"
          onClick={() => scrollBy(SCROLL_STEP)}
          disabled={!canNext}
          aria-label="Next collections"
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-gray-300 bg-white transition enabled:text-gray-900 enabled:hover:border-gray-400 disabled:cursor-default disabled:text-gray-300"
        >
          <IconChevronRight size={18} />
        </button>
      </div>

      <div className="hidden shrink-0 items-center gap-2 lg:flex lg:pl-4">
        <CatalogSortSelect sortValue={sortValue} onSortChange={onSortChange} />
      </div>
    </div>
  )
}
