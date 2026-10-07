import { QueryClient } from '@tanstack/react-query'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      gcTime: 10 * 60_000,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
})

/** Static catalog metadata — rarely changes during a shopping session. */
export const CATALOG_STALE_TIME = 30 * 60_000

/** Product lists / collections — moderate freshness. */
export const LIST_STALE_TIME = 5 * 60_000
