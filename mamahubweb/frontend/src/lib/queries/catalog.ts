import { CATALOG_STALE_TIME, LIST_STALE_TIME } from '../queryClient'
import { getData, getDataWithMeta } from '../api'
import type { Product } from '../../types/api'

export interface CategoryNode {
  code: number
  name: string
  name_ar?: string | null
  image_url?: string | null
  children?: CategoryNode[]
}

export interface CategoryMediaItem {
  ref_key?: string | null
  image_url?: string | null
}

export interface AgeGroup {
  slug: string
  age_group_name: string
  image_url?: string | null
}

export interface Brand {
  code: number
  name: string
  name_ar?: string | null
  logo_url?: string | null
}

/** Nova storefront returns brand_id / brand_name — map to UI shape. */
function mapBrand(raw: Record<string, unknown>): Brand {
  const codeRaw = raw.brand_id ?? raw.code ?? raw.brand_code
  const code =
    typeof codeRaw === 'number'
      ? codeRaw
      : typeof codeRaw === 'string' && /^\d+$/.test(codeRaw)
        ? Number(codeRaw)
        : Number(raw.brand_id ?? 0)

  return {
    code,
    name: String(raw.brand_name ?? raw.name ?? 'Brand'),
    name_ar: (raw.name_ar as string | null | undefined) ?? null,
    logo_url: (raw.logo_url as string | null | undefined) ?? null,
  }
}

export interface Interest {
  slug: string
  interest_name: string
}

export interface CollectionResponse {
  collection: string
  info: { title: string; description: string }
  products: Product[]
}

export const catalogQueries = {
  categoryTree: {
    queryKey: ['category-tree'] as const,
    queryFn: ({ signal }: { signal?: AbortSignal }) =>
      getData<CategoryNode[]>('/categories/tree', undefined, { signal }),
    staleTime: CATALOG_STALE_TIME,
  },
  categoryMedia: {
    queryKey: ['category-media'] as const,
    queryFn: ({ signal }: { signal?: AbortSignal }) =>
      getData<CategoryMediaItem[]>('/media', { placement: 'category' }, { signal }),
    staleTime: CATALOG_STALE_TIME,
  },
  exploreCategoryMedia: {
    queryKey: ['explore-category-media'] as const,
    queryFn: ({ signal }: { signal?: AbortSignal }) =>
      getData<CategoryMediaItem[]>('/media', { placement: 'explore_category' }, { signal }),
    staleTime: CATALOG_STALE_TIME,
  },
  ageGroups: {
    queryKey: ['age-groups'] as const,
    queryFn: ({ signal }: { signal?: AbortSignal }) =>
      getData<AgeGroup[]>('/age-groups', undefined, { signal }),
    staleTime: CATALOG_STALE_TIME,
  },
  brands: {
    queryKey: ['brands'] as const,
    queryFn: async ({ signal }: { signal?: AbortSignal }) => {
      const rows = await getData<Record<string, unknown>[]>('/brands', undefined, { signal })
      return rows.map(mapBrand)
    },
    staleTime: CATALOG_STALE_TIME,
  },
  interests: {
    queryKey: ['interests'] as const,
    queryFn: ({ signal }: { signal?: AbortSignal }) =>
      getData<Interest[]>('/interests', undefined, { signal }),
    staleTime: CATALOG_STALE_TIME,
  },
  giftWrapAddons: {
    queryKey: ['product-addons', 'gift_wrap'] as const,
    queryFn: ({ signal }: { signal?: AbortSignal }) =>
      getData<Product[]>('/products/addons', { addon_type: 'gift_wrap' }, { signal }),
    staleTime: CATALOG_STALE_TIME,
  },
}

export function collectionQuery(slug: string, page = 1, pageSize = 24) {
  return {
    queryKey: ['collection', slug, page, pageSize] as const,
    queryFn: ({ signal }: { signal?: AbortSignal }) =>
      getDataWithMeta<CollectionResponse>(
        `/products/collections/${slug}`,
        { page, page_size: pageSize },
        { signal },
      ),
    staleTime: LIST_STALE_TIME,
  }
}

export function prefetchCatalogMetadata(client: import('@tanstack/react-query').QueryClient) {
  void client.prefetchQuery(catalogQueries.categoryTree)
  void client.prefetchQuery(catalogQueries.exploreCategoryMedia)
  void client.prefetchQuery(catalogQueries.ageGroups)
  void client.prefetchQuery(catalogQueries.brands)
}
