import type { Product } from '../types/api'
import type { SupportedLocale } from './types'

type NamedProduct = Pick<Product, 'item_code' | 'item_name' | 'item_name_ar'>

export function productDisplayName(product: NamedProduct, locale: SupportedLocale): string {
  if (locale === 'ar') {
    const ar = product.item_name_ar?.trim()
    if (ar) return ar
  }
  const en = product.item_name?.trim()
  if (en) return en
  return `#${product.item_code}`
}
