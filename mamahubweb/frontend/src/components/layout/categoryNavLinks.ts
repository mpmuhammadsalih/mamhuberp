import type { TranslationTree } from '../../i18n/types'

/** Desktop category nav quick links (CategoryNavBar). */
export function getCategoryNavQuickLinks(t: TranslationTree) {
  return [
    { label: t.headerBar.learning, href: '/products?q=learning', icon: 'learning' as const },
    { label: t.headerBar.outdoorToys, href: '/products?q=outdoor', icon: 'outdoor' as const },
    { label: t.headerBar.deals, href: '/offers', icon: 'deals' as const },
    { label: t.headerBar.newArrivals, href: '/new-arrivals', icon: 'new' as const },
  ] as const
}

/** Mobile drawer quick links. */
export function getCategoryDrawerQuickLinks(t: TranslationTree) {
  return [
    { label: t.collections.newArrivals, href: '/new-arrivals' },
    { label: t.collections.bestSellers, href: '/best-sellers' },
    { label: t.collections.featured, href: '/featured' },
    { label: t.categoryNav.offersDeals, href: '/offers' },
    { label: t.collections.giftFinder, href: '/gift-finder' },
    { label: t.categoryNav.lego, href: '/products?q=LEGO' },
  ] as const
}

/** Collection page toolbar tabs. */
export function getCollectionToolbarLinks(t: TranslationTree) {
  return [
    { slug: 'new-arrivals', label: t.collections.newArrivals },
    { slug: 'best-sellers', label: t.collections.bestSellers },
    { slug: 'featured', label: t.collections.featured },
    { slug: 'offers', label: t.categoryNav.offersDeals },
  ] as const
}
