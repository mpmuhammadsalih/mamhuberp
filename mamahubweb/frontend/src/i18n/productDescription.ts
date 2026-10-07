import type { Product } from '../types/api'
import type { SupportedLocale } from './types'

export function productDescription(product: Product, locale: SupportedLocale): string {
  if (locale === 'ar') {
    const ar = product.description_ar?.trim()
    if (ar) return ar
  }
  return product.description?.trim() || ''
}

export function productSpecifications(
  product: Product,
  locale: SupportedLocale,
): Array<{ label: string; value: string }> {
  if (locale === 'ar' && product.specifications_ar?.length) {
    return product.specifications_ar
  }
  return product.specifications ?? []
}
