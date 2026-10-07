export const SITE_NAME = 'MamaHub'
export const DEFAULT_TITLE = "MamaHub — Mom's Love"
export const DEFAULT_DESCRIPTION =
  'Shop quality toys, games, and gifts for children in Qatar. Fast delivery, secure checkout, and curated picks for every age at mamahub.store.'

/** Public site origin — set VITE_SITE_URL in production (e.g. https://www.mamahub.store). */
export function siteBaseUrl(): string {
  const fromEnv = import.meta.env.VITE_SITE_URL?.trim()
  if (fromEnv) return fromEnv.replace(/\/$/, '')
  if (typeof window !== 'undefined') return window.location.origin
  return 'https://www.mamahub.store'
}

export function absoluteUrl(path: string): string {
  const base = siteBaseUrl()
  if (!path) return base
  if (path.startsWith('http://') || path.startsWith('https://')) return path
  return `${base}${path.startsWith('/') ? path : `/${path}`}`
}

export function pageTitle(title?: string): string {
  const trimmed = title?.trim()
  if (!trimmed) return DEFAULT_TITLE
  if (trimmed.toLowerCase().includes('mamahub')) return trimmed
  return `${trimmed} | ${SITE_NAME}`
}

export function truncateDescription(text: string, max = 160): string {
  const cleaned = text.replace(/\s+/g, ' ').trim()
  if (cleaned.length <= max) return cleaned
  return `${cleaned.slice(0, max - 1).trim()}…`
}

export function productListingTitle(
  product: { seo_title?: string | null; item_name?: string } | null | undefined,
  fallbackName = '',
): string {
  const custom = product?.seo_title?.trim()
  if (custom) return custom
  return pageTitle(product?.item_name || fallbackName)
}

export function productListingDescription(
  product: {
    seo_description?: string | null
    description?: string | null
    item_name?: string
  } | null | undefined,
  fallbackName = '',
): string {
  const custom = product?.seo_description?.trim()
  if (custom) return custom
  const fromBody = product?.description?.replace(/\s+/g, ' ').trim()
  if (fromBody) return truncateDescription(fromBody)
  const name = product?.item_name?.trim() || fallbackName || 'this item'
  return `Buy ${name} online at MamaHub. Toys and gifts delivered in Qatar.`
}
