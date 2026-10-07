import { getData } from '../api'
import { LOGO_FALLBACK_SRC } from '../brandAssets'
import { resolveMediaUrl } from '../media'
import type { MediaItem } from './storefront'

function logoCacheVersion(logo?: MediaItem | null): string {
  if (!logo?.image_url) return logo?.media_id != null ? String(logo.media_id) : '0'
  const file = logo.image_url.split('/').pop()?.split('?')[0] ?? ''
  return file || String(logo.media_id ?? '0')
}

export function resolveStorefrontLogoSrc(logo?: MediaItem | null): string {
  const resolved = resolveMediaUrl(logo?.image_url)
  if (resolved) {
    return `${resolved}${resolved.includes('?') ? '&' : '?'}v=${encodeURIComponent(logoCacheVersion(logo))}`
  }
  return LOGO_FALLBACK_SRC
}

export const storefrontLogoQuery = {
  queryKey: ['storefront-logo'] as const,
  queryFn: ({ signal }: { signal?: AbortSignal }) =>
    getData<MediaItem[]>('/media', { placement: 'storefront_logo' }, { signal }),
  staleTime: 5 * 60_000,
  gcTime: 30 * 60_000,
  refetchOnWindowFocus: false,
}
