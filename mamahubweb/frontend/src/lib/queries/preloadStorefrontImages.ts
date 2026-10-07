import type { StorefrontHome } from './storefront'
import { isVideoMediaUrl, resolveMediaUrl } from '../media'

function preloadImage(url: string, id: string) {
  if (!url) return
  if (document.querySelector(`link[data-preload-id="${id}"]`)) return
  const link = document.createElement('link')
  link.rel = 'preload'
  link.as = 'image'
  link.href = url
  link.setAttribute('data-preload-id', id)
  document.head.appendChild(link)
}

export function preloadStorefrontImages(home?: StorefrontHome | null) {
  if (!home) return

  const logoUrl = resolveMediaUrl(home.storefront_logo?.image_url)
  if (logoUrl) preloadImage(logoUrl, 'storefront-logo')

  const heroPoster =
    resolveMediaUrl(home.hero_slides?.[0]?.image_url) ??
    resolveMediaUrl(home.hero_background?.image_url)
  if (heroPoster) preloadImage(heroPoster, 'hero-poster')

  for (const [index, promo] of (home.promos ?? []).slice(0, 3).entries()) {
    const promoUrl = resolveMediaUrl(promo.image_url)
    if (promoUrl && !isVideoMediaUrl(promoUrl)) preloadImage(promoUrl, `promo-${index}`)
  }
}
