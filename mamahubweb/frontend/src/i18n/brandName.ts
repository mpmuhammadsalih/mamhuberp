import type { SupportedLocale } from './types'

type NamedBrand = {
  name?: string | null
  name_ar?: string | null
  brand_name?: string | null
  brand_name_ar?: string | null
}

export function brandDisplayName(brand: NamedBrand, locale: SupportedLocale): string {
  const en = (brand.brand_name ?? brand.name ?? '').trim()
  if (locale === 'ar') {
    const ar = (brand.brand_name_ar ?? brand.name_ar)?.trim()
    if (ar) return ar
  }
  return en
}
