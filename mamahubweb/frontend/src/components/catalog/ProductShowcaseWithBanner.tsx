import { Link } from 'react-router-dom'
import { ProductCard } from '../ProductCard'
import {
  ShowcaseMobileBanner,
  ShowcaseVerticalVideo,
  type ShowcaseBannerConfig,
} from './ShowcaseVerticalVideo'
import { HOME_CONTAINER, PRODUCT_GRID } from '../layout/homeLayout'
import type { Product } from '../../types/api'

export type { ShowcaseBannerConfig }

interface Props {
  sectionTitle: string
  viewAllHref: string
  products: Product[]
  banner: ShowcaseBannerConfig
  badge?: string
}

export function ProductShowcaseWithBanner({
  sectionTitle,
  viewAllHref,
  products,
  banner,
  badge,
}: Props) {
  if (products.length === 0) return null

  return (
    <section className={`${HOME_CONTAINER} pb-12 pt-2 lg:pb-14`}>
      <div className="mb-5 flex items-center justify-between lg:mb-6">
        <h2 className="font-display text-xl font-bold text-brand-ink sm:text-2xl">{sectionTitle}</h2>
        <Link
          to={viewAllHref}
          className="font-catalog flex items-center gap-1.5 text-[13px] font-semibold uppercase tracking-wide text-brand-accent hover:underline"
        >
          View all
          <span aria-hidden>→</span>
        </Link>
      </div>

      <ShowcaseMobileBanner banner={banner} />

      {/* Mobile / tablet: product grid + banner */}
      <div className={`${PRODUCT_GRID} lg:hidden`}>
        {products.slice(0, 6).map((p) => (
          <ProductCard key={p.item_code} product={p} badge={badge} variant="showcase" />
        ))}
      </div>

      {/* Desktop: 3 product cols + wider video (2 cols), video spans 2 rows */}
      <div className="hidden lg:grid lg:grid-cols-5 lg:items-stretch lg:gap-3">
        {products.slice(0, 6).map((p) => (
          <ProductCard key={p.item_code} product={p} badge={badge} variant="showcase" />
        ))}
        <ShowcaseVerticalVideo
          banner={banner}
          className="col-span-2 col-start-4 row-start-1 row-span-2 h-full min-h-0"
        />
      </div>
    </section>
  )
}
