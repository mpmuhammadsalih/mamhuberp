import type { CategoryNode } from '../lib/queries/catalog'
import type { SupportedLocale } from './types'

type NamedCategory = Pick<CategoryNode, 'name' | 'name_ar'>

export function categoryDisplayName(category: NamedCategory, locale: SupportedLocale): string {
  if (locale === 'ar') {
    const ar = category.name_ar?.trim()
    if (ar) return ar
  }
  return category.name?.trim() || ''
}
