import type { SupportedLocale } from './types'

type LocalizedMedia = {
  title?: string | null
  subtitle?: string | null
  title_ar?: string | null
  subtitle_ar?: string | null
  meta?: Record<string, unknown> | null
}

export function mediaTitle(item: LocalizedMedia, locale: SupportedLocale, fallback = ''): string {
  if (locale === 'ar') {
    const ar = item.title_ar?.trim()
    if (ar) return ar
  }
  return item.title?.trim() || fallback
}

export function mediaSubtitle(item: LocalizedMedia, locale: SupportedLocale, fallback = ''): string {
  if (locale === 'ar') {
    const ar = item.subtitle_ar?.trim()
    if (ar) return ar
  }
  return item.subtitle?.trim() || fallback
}

export function mediaCta(item: LocalizedMedia, locale: SupportedLocale, fallback: string): string {
  const meta = item.meta ?? {}
  if (locale === 'ar') {
    const ar = typeof meta.cta_ar === 'string' ? meta.cta_ar.trim() : ''
    if (ar) return ar
  }
  const en = typeof meta.cta === 'string' ? meta.cta.trim() : ''
  return en || fallback
}
