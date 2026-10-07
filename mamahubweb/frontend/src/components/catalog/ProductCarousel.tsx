import { useCallback, useEffect, useRef, useState } from 'react'
import { ProductCard } from '../ProductCard'
import { CarouselNavControls } from './CarouselNavControls'
import { HOME_GRID_GAP } from '../layout/homeLayout'
import type { Product } from '../../types/api'

const SCROLL_STEP = 280

interface Props {
  title: string
  products: Product[]
  viewAllHref?: string
}

export function ProductCarousel({ title, products, viewAllHref = '/products' }: Props) {
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
    if (products.length === 0) return undefined
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

  if (products.length === 0) return null

  function scrollBy(delta: number) {
    scrollRef.current?.scrollBy({ left: delta, behavior: 'smooth' })
  }

  return (
    <section className="mt-14 border-t border-gray-200 pt-10">
      <div className="mb-5 flex items-center justify-between gap-4">
        <h2 className="font-catalog text-lg font-bold text-gray-900">{title}</h2>
        <CarouselNavControls
          viewAllHref={viewAllHref}
          onPrev={() => scrollBy(-SCROLL_STEP)}
          onNext={() => scrollBy(SCROLL_STEP)}
          canPrev={canPrev}
          canNext={canNext}
        />
      </div>

      <div
        ref={scrollRef}
        className={`flex ${HOME_GRID_GAP} overflow-x-auto pb-2 scroll-smooth [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden`}
      >
        {products.map((product) => (
          <div key={product.item_code} className="w-[168px] shrink-0 sm:w-[184px]">
            <ProductCard product={product} variant="grid" />
          </div>
        ))}
      </div>
    </section>
  )
}
