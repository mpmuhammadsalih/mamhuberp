import type { TranslationTree } from './types'

export const SORT_OPTION_DEFS = [
  { value: 'relevance', sort: undefined as string | undefined, order: undefined as string | undefined, labelKey: 'sortRelevance' as const },
  { value: 'price_asc', sort: 'retailprice', order: 'asc', labelKey: 'sortPriceAsc' as const },
  { value: 'price_desc', sort: 'retailprice', order: 'desc', labelKey: 'sortPriceDesc' as const },
  { value: 'name_asc', sort: 'itemname', order: 'asc', labelKey: 'sortNameAsc' as const },
  { value: 'name_desc', sort: 'itemname', order: 'desc', labelKey: 'sortNameDesc' as const },
  { value: 'newest', sort: 'itemcode', order: 'desc', labelKey: 'sortNewest' as const },
] as const

export type SortOptionValue = (typeof SORT_OPTION_DEFS)[number]['value']

export function getSortOptions(t: TranslationTree) {
  return SORT_OPTION_DEFS.map((option) => ({
    ...option,
    label: t.catalog[option.labelKey],
  }))
}

/** @deprecated Use getSortOptions(t) for localized labels */
export const SORT_OPTIONS = SORT_OPTION_DEFS.map((option) => ({
  value: option.value,
  sort: option.sort,
  order: option.order,
  label: option.labelKey,
}))
