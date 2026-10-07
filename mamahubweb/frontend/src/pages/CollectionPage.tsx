import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { CatalogCollectionToolbar } from '../components/catalog/CatalogCollectionToolbar'
import { CatalogLayout } from '../components/catalog/CatalogLayout'
import { CatalogPageHero } from '../components/catalog/CatalogPageHero'
import { PRODUCT_GRID, PRODUCT_GRID_SKELETON } from '../components/layout/homeLayout'
import { Pagination } from '../components/Pagination'
import { ProductCard } from '../components/ProductCard'
import { SeoHead } from '../components/seo/SeoHead'
import { IconGift } from '../components/icons/Icons'
import { useLocale } from '../i18n/LocaleContext'
import { getData } from '../lib/api'
import { catalogQueries, collectionQuery } from '../lib/queries/catalog'
import type { Product } from '../types/api'

interface Coupon {
  coupon_code: string
  promotion_name: string
  promotion_type: string
  discount_value: number
}

function productPrice(product: Product): number {
  return product.offer_price ?? product.retail_price ?? 0
}

function sortProducts(products: Product[], sortValue: string): Product[] {
  const sorted = [...products]
  switch (sortValue) {
    case 'price_asc':
      return sorted.sort((a, b) => productPrice(a) - productPrice(b))
    case 'price_desc':
      return sorted.sort((a, b) => productPrice(b) - productPrice(a))
    case 'name_asc':
      return sorted.sort((a, b) =>
        (a.item_name ?? '').localeCompare(b.item_name ?? '', undefined, { sensitivity: 'base' }),
      )
    case 'name_desc':
      return sorted.sort((a, b) =>
        (b.item_name ?? '').localeCompare(a.item_name ?? '', undefined, { sensitivity: 'base' }),
      )
    case 'newest':
      return sorted.sort((a, b) => b.item_code - a.item_code)
    default:
      return sorted
  }
}

export function CollectionPage() {
  const { t } = useLocale()
  const { collection: paramCollection } = useParams<{ collection: string }>()
  const location = useLocation()
  const navigate = useNavigate()
  const collection =
    paramCollection || location.pathname.replace(/^\//, '').split('/')[0] || 'new-arrivals'
  const [params, setParams] = useSearchParams()
  const page = Number(params.get('page') || '1')
  const sortValue = params.get('sort') || 'relevance'
  const [copied, setCopied] = useState<string | null>(null)

  const { data: categoryTree = [] } = useQuery(catalogQueries.categoryTree)
  const { data: ageGroups = [] } = useQuery(catalogQueries.ageGroups)
  const { data: interests = [] } = useQuery(catalogQueries.interests)
  const { data: brands = [] } = useQuery(catalogQueries.brands)

  const { data, isLoading } = useQuery(collectionQuery(collection, page, 24))

  const { data: coupons = [] } = useQuery({
    queryKey: ['public-coupons'],
    queryFn: () => getData<Coupon[]>('/promotions/coupons'),
    enabled: collection === 'offers',
  })

  const products = useMemo(
    () => sortProducts(data?.data?.products ?? [], sortValue),
    [data?.data?.products, sortValue],
  )
  const info = data?.data?.info
  const meta = data?.meta
  const totalPages = meta?.total_pages ?? 1

  function goToPage(p: number) {
    const next = new URLSearchParams(params)
    next.set('page', String(p))
    setParams(next)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  function handleSortChange(value: string) {
    const next = new URLSearchParams(params)
    if (value === 'relevance') next.delete('sort')
    else next.set('sort', value)
    setParams(next)
  }

  function navigateToProducts(nextParams: URLSearchParams) {
    navigate(`/products?${nextParams.toString()}`)
  }

  function updateParam(key: string, value: string | null) {
    const next = new URLSearchParams()
    if (value) next.set(key, value)
    if (key === 'main') {
      next.delete('dept')
      next.delete('category')
    }
    if (key === 'dept') next.delete('category')
    navigateToProducts(next)
  }

  function handlePriceApply(min: string, max: string) {
    const next = new URLSearchParams()
    if (min) next.set('min_price', min)
    if (max) next.set('max_price', max)
    navigateToProducts(next)
  }

  const title = info?.title ?? t.shared.collection
  const subtitle =
    meta?.total_records != null
      ? `${meta.total_records.toLocaleString()} ${t.shared.productsCount}`
      : undefined

  const pageHeader = <CatalogPageHero title={title} subtitle={subtitle} />

  const toolbar = (
    <CatalogCollectionToolbar
      activeCollection={collection}
      totalCount={meta?.total_records}
      sortValue={sortValue}
      onSortChange={handleSortChange}
    />
  )

  return (
    <CatalogLayout
      pageHeader={pageHeader}
      toolbar={toolbar}
      sortValue={sortValue}
      onSortChange={handleSortChange}
      filterProps={{
        categoryTree,
        ageGroups,
        brands,
        interests,
        onSelect: updateParam,
        onPriceApply: handlePriceApply,
        onClear: () => navigate('/products'),
      }}
    >
      <SeoHead
        title={info?.title ?? t.shared.collection}
        description={
          info?.description ??
          `Browse ${info?.title ?? 'our collection'} at MamaHub — toys and gifts for children in Qatar.`
        }
      />
      {collection === 'offers' && coupons.length > 0 && (
        <div className="mb-8">
          <h2 className="mb-4 flex items-center gap-2 font-display text-xl font-bold text-brand-ink">
            <IconGift size={20} className="text-brand-accent" />
            {t.catalog.activeCoupons}
          </h2>
          <div className="grid gap-3 md:grid-cols-2">
            {coupons.map((c) => (
              <div
                key={c.coupon_code}
                className="flex items-center justify-between rounded-3xl border-2 border-dashed border-brand-border bg-brand-cream-alt p-5"
              >
                <div>
                  <p className="font-mono text-lg font-bold text-brand-accent">{c.coupon_code}</p>
                  <p className="text-sm text-brand-sage">{c.promotion_name}</p>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    navigator.clipboard.writeText(c.coupon_code)
                    setCopied(c.coupon_code)
                    setTimeout(() => setCopied(null), 2000)
                  }}
                  className="rounded-full bg-brand-accent px-5 py-2 text-sm font-semibold text-white shadow-sm hover:bg-brand-accent-hover"
                >
                  {copied === c.coupon_code ? t.shared.copied : t.shared.copy}
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {isLoading ? (
        <div className={PRODUCT_GRID_SKELETON}>
          {Array.from({ length: 10 }).map((_, i) => (
            <div key={i} className="min-h-[320px] animate-pulse rounded-2xl bg-brand-tint/70" />
          ))}
        </div>
      ) : products.length === 0 ? (
        <p className="py-16 text-center text-brand-sage">{t.shared.noProductsInCollection}</p>
      ) : (
        <>
          <div className={PRODUCT_GRID}>
            {products.map((p) => (
              <ProductCard
                key={p.item_code}
                product={p}
                badge={
                  collection === 'new-arrivals'
                    ? t.shared.new
                    : collection === 'best-sellers'
                      ? t.home.popular
                      : collection === 'featured'
                        ? t.home.featuredBadge
                        : p.discount_percent
                          ? `-${p.discount_percent}%`
                          : undefined
                }
              />
            ))}
          </div>
          <Pagination page={page} totalPages={totalPages} onPageChange={goToPage} />
        </>
      )}
    </CatalogLayout>
  )
}
