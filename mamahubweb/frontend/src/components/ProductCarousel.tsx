import type { ReactNode } from 'react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useLocale } from '../i18n/LocaleContext'
import { CarouselNavControls } from './catalog/CarouselNavControls'
import { HOME_CONTAINER, HOME_GRID_GAP } from './layout/homeLayout'
import { IconGift, IconSparkle } from './icons/Icons'

interface Props {
  title: string
  viewAllHref: string
  icon?: 'sparkle' | 'gift'
  children: ReactNode
}

const SCROLL_STEP = 280

export function ProductCarousel({ title, viewAllHref, icon = 'sparkle', children }: Props) {
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
  }, [updateScrollState, children])

  function scrollBy(delta: number) {
    scrollRef.current?.scrollBy({ left: delta, behavior: 'smooth' })
  }

  const TitleIcon = icon === 'gift' ? IconGift : IconSparkle

  return (
    <section className={`${HOME_CONTAINER} pb-12 pt-2 lg:pb-14`}>
      <div className="mb-6 flex items-center justify-between gap-4 lg:mb-7">
        <h2 className="flex items-center gap-2 font-display text-xl font-bold text-brand-ink sm:text-2xl">
          <TitleIcon size={22} className={icon === 'gift' ? 'text-brand-orange' : 'text-brand-yellow'} />
          {title}
        </h2>
        <CarouselNavControls
          viewAllHref={viewAllHref}
          onPrev={() => scrollBy(-SCROLL_STEP)}
          onNext={() => scrollBy(SCROLL_STEP)}
          canPrev={canPrev}
          canNext={canNext}
        />
      </div>

      <Link
        to={viewAllHref}
        className="font-catalog mb-4 inline-flex items-center gap-1.5 text-[13px] font-semibold uppercase tracking-wide text-brand-accent hover:underline sm:hidden"
      >
        {t.shared.viewAll}
        <span aria-hidden>→</span>
      </Link>

      <div className="-mx-1 px-1">
        <div
          ref={scrollRef}
          className={`flex ${HOME_GRID_GAP} overflow-x-auto pb-3 scroll-smooth [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden`}
        >
          {children}
        </div>
      </div>
    </section>
  )
}
