import type { ApiResponse } from '../types/api'

export interface PaginationMeta {
  page: number
  page_size: number
  total_records: number
  total_pages: number
}

export function metaFromResponse<T>(response: { meta?: ApiResponse<T>['meta'] } | undefined): PaginationMeta {
  const meta = response?.meta
  return {
    page: meta?.page ?? 1,
    page_size: meta?.page_size ?? 20,
    total_records: meta?.total_records ?? 0,
    total_pages: meta?.total_pages ?? 1,
  }
}
