import { getData, getDataWithMeta } from '../api'
import type { Product } from '../../types/api'

export interface GiftFinderFilters {
  age: string
  interest?: string
  maxPrice: string
  occasion: string
}

interface GiftFinderResult {
  filters: Record<string, unknown>
  results: Product[]
}

const OCCASION_SEARCH: Record<string, string | undefined> = {
  birthday: 'birthday',
  eid: 'eid',
  christmas: 'christmas',
  'new-baby': 'baby',
  general: undefined,
}

export function occasionSearch(occasion: string) {
  if (!occasion) return undefined
  return OCCASION_SEARCH[occasion] ?? occasion
}

export async function fetchGiftItems(
  filters: GiftFinderFilters,
  signal?: AbortSignal,
): Promise<Product[]> {
  try {
    const data = await getData<GiftFinderResult>(
      '/gift-finder',
      {
        age: filters.age || undefined,
        interest: filters.interest || undefined,
        max_price: filters.maxPrice ? Number(filters.maxPrice) : undefined,
        occasion: filters.occasion || undefined,
      },
      { signal },
    )
    if (data?.results?.length) return data.results
  } catch {
    /* fall through to catalog search */
  }

  const catalog = await getDataWithMeta<Product[]>(
    '/products',
    {
      age: filters.age || undefined,
      interest: filters.interest || undefined,
      search: occasionSearch(filters.occasion),
      max_price: filters.maxPrice || undefined,
      page: 1,
      page_size: 24,
      sort: 'retailprice',
      order: 'asc',
    },
    { signal },
  )
  if (catalog.data?.length) return catalog.data

  const allToys = await getDataWithMeta<Product[]>(
    '/products',
    {
      max_price: filters.maxPrice || undefined,
      page: 1,
      page_size: 24,
      sort: 'retailprice',
      order: 'asc',
    },
    { signal },
  )
  return allToys.data ?? []
}
