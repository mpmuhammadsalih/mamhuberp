import { getData } from '../api'
import { LIST_STALE_TIME } from '../queryClient'
export interface MediaItem {
  media_id?: number | null
  placement: string
  ref_key?: string | null
  title?: string | null
  subtitle?: string | null
  title_ar?: string | null
  subtitle_ar?: string | null
  image_url?: string | null
  link_url?: string | null
  alt_text?: string | null
  sort_order?: number
  meta?: Record<string, unknown>
}

export interface StorefrontSettings {
  coupons_enabled: boolean
  free_gift_wrap?: boolean
  checkout_enabled?: boolean
  pickup_enabled?: boolean
  delivery_enabled?: boolean
  header_trust_delivery?: string
  header_trust_original?: string
  header_trust_returns?: string
  header_trust_delivery_ar?: string
  header_trust_original_ar?: string
  header_trust_returns_ar?: string
}

export interface StorefrontHome {
  storefront_logo?: MediaItem | null
  hero_background?: MediaItem | null
  hero_slides: MediaItem[]
  promos: MediaItem[]
  showcase_banners: Record<string, MediaItem>
}

export const storefrontQueries = {
  settings: {
    queryKey: ['storefront-settings'] as const,
    queryFn: ({ signal }: { signal?: AbortSignal }) =>
      getData<StorefrontSettings>('/storefront/settings', undefined, { signal }),
    staleTime: LIST_STALE_TIME,
  },
  home: {
    queryKey: ['storefront-home'] as const,
    queryFn: ({ signal }: { signal?: AbortSignal }) =>
      getData<StorefrontHome>('/storefront/home', undefined, { signal }),
    staleTime: LIST_STALE_TIME,
    refetchOnMount: true,
  },
}
