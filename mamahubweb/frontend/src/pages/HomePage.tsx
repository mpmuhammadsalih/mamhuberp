import { useQuery } from '@tanstack/react-query'
import { AgeGroupCard } from '../components/AgeGroupCard'
import { ExploreMoreCategories } from '../components/catalog/ExploreMoreCategories'
import { ShopByCategoryIcons } from '../components/catalog/ShopByCategoryIcons'
import { HomeHighlightSections } from '../components/home/HomeHighlightSections'
import { NewArrivalsSection } from '../components/catalog/NewArrivalsSection'
import { HOME_CONTAINER } from '../components/layout/homeLayout'
import { PromoBanners } from '../components/promo/PromoBanners'
import { ProductCard } from '../components/ProductCard'
import { SeoHead } from '../components/seo/SeoHead'
import { ProductCarousel } from '../components/ProductCarousel'
import { ProductCarouselSkeleton } from '../components/ProductCardSkeleton'
import { IconCake } from '../components/icons/Icons'
import { catalogQueries, collectionQuery } from '../lib/queries/catalog'
import { storefrontQueries } from '../lib/queries/storefront'
import { buildShowcaseBannerConfig, pickShowcaseMedia } from '../lib/showcaseBanner'
import { ageGroupDisplayName } from '../i18n/ageGroupName'
import { useLocale } from '../i18n/LocaleContext'
import { resolveMediaUrl } from '../lib/media'
import { SITE_NAME, absoluteUrl, DEFAULT_DESCRIPTION } from '../lib/seo'

export function HomePage() {
  const { locale, t } = useLocale()
  const { data: newArrivalsData, isLoading: newArrivalsLoading } = useQuery(
    collectionQuery('new-arrivals', 1, 6),
  )
  const { data: bestSellersData, isLoading: bestSellersLoading } = useQuery(
    collectionQuery('best-sellers', 1, 8),
  )
  const { data: featuredData } = useQuery(collectionQuery('featured', 1, 8))
  const { data: offersData, isLoading: offersLoading } = useQuery(collectionQuery('offers', 1, 8))
  const { data: ageGroups = [], isLoading: ageGroupsLoading } = useQuery(catalogQueries.ageGroups)
  const { data: categoryTree = [] } = useQuery(catalogQueries.categoryTree)
  const { data: storefront } = useQuery(storefrontQueries.home)

  const newArrivals = newArrivalsData?.data?.products ?? []
  const bestSellers = bestSellersData?.data?.products ?? []
  const featured = featuredData?.data?.products ?? []
  const offers = offersData?.data?.products ?? []
  const trendingProducts = featured.length > 0 ? featured : bestSellers
  const organizationLogo =
    resolveMediaUrl(storefront?.storefront_logo?.image_url) || '/mamahub-logo.png'
  const showcaseBanner = pickShowcaseMedia(storefront?.showcase_banners, 'new-arrivals')
  const newArrivalsShowcase = buildShowcaseBannerConfig(showcaseBanner, {
    title: t.home.discoverToys,
    href: '/new-arrivals',
    posterFallback: '/images/showcase-new-arrivals.jpg',
  })

  return (
    <div className="overflow-x-hidden bg-brand-cream">
      <SeoHead
        title={t.seo.homeTitle}
        description={t.seo.homeDescription}
        image={organizationLogo}
        jsonLd={[
          {
            '@context': 'https://schema.org',
            '@type': 'Organization',
            name: SITE_NAME,
            url: absoluteUrl('/'),
            logo: absoluteUrl(organizationLogo),
            email: 'mamahubtrading@gmail.com',
            telephone: '+97472352255',
            address: {
              '@type': 'PostalAddress',
              addressLocality: 'Doha',
              addressCountry: 'QA',
            },
          },
          {
            '@context': 'https://schema.org',
            '@type': 'WebSite',
            name: SITE_NAME,
            url: absoluteUrl('/'),
            description: t.seo.homeDescription || DEFAULT_DESCRIPTION,
            potentialAction: {
              '@type': 'SearchAction',
              target: `${absoluteUrl('/products')}?q={search_term_string}`,
              'query-input': 'required name=search_term_string',
            },
          },
        ]}
      />
      <PromoBanners />

      <ShopByCategoryIcons categories={categoryTree} />

      <HomeHighlightSections
        trending={trendingProducts}
        deal={offers[0] ?? featured[0] ?? null}
      />

      {newArrivalsLoading && newArrivals.length === 0 ? (
        <ProductCarouselSkeleton title={t.home.newArrivals} />
      ) : newArrivals.length > 0 ? (
          <NewArrivalsSection
            products={newArrivals}
            banner={newArrivalsShowcase}
            viewAllHref="/new-arrivals"
          />
      ) : null}

      {featured.length > 0 && bestSellersLoading && bestSellers.length === 0 ? (
        <ProductCarouselSkeleton title={t.home.bestSellers} />
      ) : featured.length > 0 && bestSellers.length > 0 ? (
        <ProductCarousel title={t.home.bestSellers} viewAllHref="/best-sellers" icon="sparkle">
          {bestSellers.map((p) => (
            <ProductCard key={p.item_code} product={p} badge={t.home.popular} variant="carousel" />
          ))}
        </ProductCarousel>
      ) : null}

      {offersLoading && offers.length === 0 ? (
        <ProductCarouselSkeleton title={t.home.offersDeals} />
      ) : offers.length > 0 ? (
        <ProductCarousel title={t.home.offersDeals} viewAllHref="/offers" icon="gift">
          {offers.map((p) => (
            <ProductCard
              key={p.item_code}
              product={p}
              badge={p.discount_percent ? `-${p.discount_percent}%` : t.home.deal}
              variant="carousel"
            />
          ))}
        </ProductCarousel>
      ) : null}

      <section className={`${HOME_CONTAINER} pb-2 pt-2 lg:pb-4`}>
        <h2 className="mb-5 flex items-center gap-2 font-display text-xl font-bold text-brand-ink sm:mb-6 sm:text-2xl">
          <IconCake size={24} className="text-brand-purple" />
          {t.home.shopByAge}
        </h2>
        <div className="grid w-full grid-cols-2 justify-items-center gap-x-6 gap-y-8 sm:gap-x-8 sm:gap-y-10 lg:grid-cols-4 lg:gap-x-10 lg:gap-y-8 xl:gap-x-12">
          {ageGroupsLoading && ageGroups.length === 0
            ? Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="flex w-full max-w-[220px] flex-col items-center gap-3 sm:max-w-[256px] lg:max-w-[300px] xl:max-w-[328px]">
                  <div className="aspect-square w-full animate-pulse rounded-2xl bg-brand-tint/70" />
                  <div className="h-3.5 w-3/4 animate-pulse rounded-full bg-brand-tint/60" />
                </div>
              ))
            : ageGroups.slice(0, 4).map((g, i) => (
                <AgeGroupCard
                  key={`${g.slug}-${g.image_url ?? 'fallback'}`}
                  slug={g.slug}
                  name={ageGroupDisplayName(g, locale, t)}
                  index={i}
                  imageUrl={g.image_url ?? undefined}
                />
              ))}
        </div>
      </section>

      <ExploreMoreCategories />
    </div>
  )
}
