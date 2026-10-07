import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { NewArrivalCard } from './NewArrivalCard'
import {
  ShowcaseMobileBanner,
  ShowcaseVerticalVideo,
  type ShowcaseBannerConfig,
} from './ShowcaseVerticalVideo'
import { CarouselNavControls } from './CarouselNavControls'
import { HOME_CONTAINER, HOME_GRID_GAP } from '../layout/homeLayout'
import { IconSparkle } from '../icons/Icons'
import { useLocale } from '../../i18n/LocaleContext'
import type { Product } from '../../types/api'

interface Props {
  products: Product[]
  banner: ShowcaseBannerConfig
  viewAllHref?: string
}

const SCROLL_STEP = 300

export function NewArrivalsSection({
  products,
  banner,
  viewAllHref = '/new-arrivals',
}: Props) {
  const { t } = useLocale()
  const scrollRef = useRef<HTMLDivElement>(null)
  const [canPrev, setCanPrev] = useState(false)
  const [canNext, setCanNext] = useState(true)

  const updateScrollState = useCallback(() => {
    const el = scrollRef.current
    if (!el) return
    setCanPrev(el.scrollLeft > 8)
    setCanNext(el.scrollLeft + el.clientWidth < el.scrollWidth - 8)
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
  }, [updateScrollState, products.length])

  function scrollBy(delta: number) {
    scrollRef.current?.scrollBy({ left: delta, behavior: 'smooth' })
  }

  if (products.length === 0) return null

  const productCards: ReactNode = products.slice(0, 4).map((product) => (
    <NewArrivalCard key={product.item_code} product={product} />
  ))

  return (
    <section className={`${HOME_CONTAINER} pb-12 pt-4 lg:pb-16 lg:pt-6`}>
      <div className="overflow-hidden rounded-[1.75rem] bg-gradient-to-br from-brand-tint/50 via-white to-brand-cream-alt ring-1 ring-brand-border/60 shadow-sm">
        <div className="border-b border-brand-border/40 bg-white/70 px-4 py-5 sm:px-6 lg:px-8">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <div className="mb-1 flex items-center gap-2">
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-yellow">
                  <IconSparkle size={18} className="text-brand-ink" />
                </span>
                <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-brand-orange">
                  {t.catalog.justLanded}
                </p>
              </div>
              <h2 className="font-display text-2xl font-bold text-brand-ink sm:text-[1.75rem]">
                {t.home.newArrivals}
              </h2>
              <p className="mt-1 max-w-md text-sm text-brand-cocoa">
                {t.catalog.freshPicks}
              </p>
            </div>

            <CarouselNavControls
              viewAllHref={viewAllHref}
              onPrev={() => scrollBy(-SCROLL_STEP)}
              onNext={() => scrollBy(SCROLL_STEP)}
              canPrev={canPrev}
              canNext={canNext}
            />
          </div>
        </div>

        <div className="p-4 sm:p-5 lg:p-6">
          <ShowcaseMobileBanner banner={banner} />

          <div className="lg:grid lg:grid-cols-[minmax(0,1fr)_240px] lg:gap-5 xl:grid-cols-[minmax(0,1fr)_280px]">
            <div className="-mx-1 min-w-0 px-1">
              <div
                ref={scrollRef}
                className={`flex ${HOME_GRID_GAP} overflow-x-auto pb-2 scroll-smooth [-ms-overflow-style:none] [scrollbar-width:none] lg:grid lg:grid-cols-4 lg:overflow-visible lg:pb-0 [&::-webkit-scrollbar]:hidden`}
              >
                {productCards}
              </div>
            </div>

            <ShowcaseVerticalVideo
              banner={banner}
              className="hidden min-h-[320px] lg:flex xl:min-h-[360px]"
            />
          </div>

          <div className="mt-4 flex justify-center lg:hidden">
            <Link
              to={viewAllHref}
              className="inline-flex items-center gap-1.5 rounded-full border border-brand-accent/30 bg-white px-5 py-2 text-sm font-semibold text-brand-accent shadow-sm transition hover:bg-brand-tint/50"
            >
              {t.catalog.viewAllNewArrivals}
              <span aria-hidden>→</span>
            </Link>
          </div>
        </div>
      </div>
    </section>
  )
}
