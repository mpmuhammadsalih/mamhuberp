import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { CatalogPageHero } from '../components/catalog/CatalogPageHero'
import { PAGE_CONTAINER, PRODUCT_GRID, PRODUCT_GRID_SKELETON } from '../components/layout/homeLayout'
import { ProductCard } from '../components/ProductCard'
import { ProductCardSkeleton } from '../components/ProductCardSkeleton'
import { SeoHead } from '../components/seo/SeoHead'
import { useLocale } from '../i18n/LocaleContext'
import { getData } from '../lib/api'
import { storage } from '../lib/storage'
import type { Product, WishlistItem } from '../types/api'

interface WishlistData {
  items: WishlistItem[]
}

export function WishlistPage() {
  const { t } = useLocale()

  const { data, isLoading } = useQuery({
    queryKey: ['wishlist'],
    queryFn: () => getData<WishlistData>('/wishlist'),
    enabled: storage.hasSession(),
  })

  const products = (data?.items ?? [])
    .map((item) => item.product)
    .filter((product): product is Product => Boolean(product))

  if (!storage.hasSession()) {
    return (
      <div className={`${PAGE_CONTAINER} py-12 text-center`}>
        <SeoHead title={t.account.wishlist} />
        <p className="text-slate-600">{t.account.signInWishlist}</p>
        <Link
          to="/login?redirect=%2Fwishlist"
          className="mt-4 inline-block rounded-full bg-brand-accent px-5 py-2 text-sm font-semibold text-white hover:bg-brand-accent-hover"
        >
          {t.auth.signIn}
        </Link>
      </div>
    )
  }

  return (
    <div className={`${PAGE_CONTAINER} py-8 lg:py-10`}>
      <SeoHead title={t.account.wishlist} />
      <CatalogPageHero
        title={t.account.wishlist}
        subtitle={
          isLoading
            ? undefined
            : `${products.length.toLocaleString()} ${t.shared.productsCount}`
        }
      />
      {isLoading ? (
        <div className={PRODUCT_GRID_SKELETON}>
          {Array.from({ length: 5 }).map((_, index) => (
            <ProductCardSkeleton key={index} />
          ))}
        </div>
      ) : products.length === 0 ? (
        <p className="py-16 text-center text-slate-500">{t.account.wishlistEmpty}</p>
      ) : (
        <div className={PRODUCT_GRID}>
          {products.map((product) => (
            <ProductCard key={product.item_code} product={product} />
          ))}
        </div>
      )}
    </div>
  )
}
