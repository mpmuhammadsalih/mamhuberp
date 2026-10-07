import type { TranslationTree } from '../../i18n/types'

/** Shared storefront links for offers, collections, and gift finder. */
export function getCollectionQuickLinks(t: TranslationTree) {
  return [
    { label: t.collections.offers, href: '/offers' },
    { label: t.collections.newArrivals, href: '/new-arrivals' },
    { label: t.collections.bestSellers, href: '/best-sellers' },
    { label: t.collections.featured, href: '/featured' },
    { label: t.collections.giftFinder, href: '/gift-finder' },
  ] as const
}
