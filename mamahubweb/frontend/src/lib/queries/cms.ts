import { useQuery, type QueryClient } from '@tanstack/react-query'
import { getData } from '../api'
import { CATALOG_STALE_TIME } from '../queryClient'
import type { CmsPageListItem } from '../../types/api'

export const cmsPagesQueryKey = ['cms-pages'] as const

/** Shown in footer when the CMS API is unavailable. */
export const FALLBACK_CMS_LINKS: CmsPageListItem[] = [
  { slug: 'faq', page_title: 'Frequently Asked Questions' },
  { slug: 'contact', page_title: 'Contact Us' },
  { slug: 'terms', page_title: 'Terms and Conditions' },
  { slug: 'privacy', page_title: 'Privacy Policy' },
  { slug: 'returns', page_title: 'Return Policy' },
]

export function fetchCmsPages() {
  return getData<CmsPageListItem[]>('/cms/pages')
}

export function useCmsPages() {
  return useQuery({
    queryKey: cmsPagesQueryKey,
    queryFn: fetchCmsPages,
    staleTime: CATALOG_STALE_TIME,
    retry: 1,
  })
}

export function prefetchCmsPages(client: QueryClient) {
  return client.prefetchQuery({
    queryKey: cmsPagesQueryKey,
    queryFn: fetchCmsPages,
    staleTime: CATALOG_STALE_TIME,
  })
}
