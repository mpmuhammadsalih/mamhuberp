import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { resolveMediaUrl } from '../../lib/media'
import { useLocale } from '../../i18n/LocaleContext'
import {
  DEFAULT_DESCRIPTION,
  SITE_NAME,
  absoluteUrl,
  pageTitle,
  truncateDescription,
} from '../../lib/seo'

export interface SeoHeadProps {
  title?: string
  description?: string
  image?: string | null
  /** Open Graph type — use product on product detail pages. */
  ogType?: 'website' | 'product'
  noIndex?: boolean
  jsonLd?: Record<string, unknown> | Array<Record<string, unknown>>
}

function upsertMeta(attr: 'name' | 'property', key: string, content: string) {
  if (!content) return
  let el = document.head.querySelector(`meta[${attr}="${key}"]`) as HTMLMetaElement | null
  if (!el) {
    el = document.createElement('meta')
    el.setAttribute(attr, key)
    document.head.appendChild(el)
  }
  el.content = content
}

function upsertLink(rel: string, href: string) {
  if (!href) return
  let el = document.head.querySelector(`link[rel="${rel}"]`) as HTMLLinkElement | null
  if (!el) {
    el = document.createElement('link')
    el.rel = rel
    document.head.appendChild(el)
  }
  el.href = href
}

function upsertJsonLd(data: SeoHeadProps['jsonLd']) {
  const id = 'seo-jsonld'
  const existing = document.getElementById(id)
  if (existing) existing.remove()
  if (!data) return
  const script = document.createElement('script')
  script.id = id
  script.type = 'application/ld+json'
  script.textContent = JSON.stringify(data)
  document.head.appendChild(script)
}

export function SeoHead({
  title,
  description,
  image,
  ogType = 'website',
  noIndex = false,
  jsonLd,
}: SeoHeadProps) {
  const location = useLocation()
  const { locale } = useLocale()
  const fullTitle = pageTitle(title)
  const desc = truncateDescription(description?.trim() || DEFAULT_DESCRIPTION)
  const canonical = absoluteUrl(`${location.pathname}${location.search}`)
  const resolvedImage = resolveMediaUrl(image) || '/images/hero-banner.png'
  const ogImage = absoluteUrl(resolvedImage)

  const jsonLdKey = jsonLd ? JSON.stringify(jsonLd) : ''

  useEffect(() => {
    document.title = fullTitle

    upsertMeta('name', 'description', desc)
    upsertMeta('name', 'robots', noIndex ? 'noindex,nofollow' : 'index,follow')

    upsertLink('canonical', canonical)

    upsertMeta('property', 'og:title', fullTitle)
    upsertMeta('property', 'og:description', desc)
    upsertMeta('property', 'og:type', ogType)
    upsertMeta('property', 'og:url', canonical)
    upsertMeta('property', 'og:site_name', SITE_NAME)
    upsertMeta('property', 'og:image', ogImage)
    upsertMeta('property', 'og:locale', locale === 'ar' ? 'ar_QA' : 'en_QA')

    upsertMeta('name', 'twitter:card', 'summary_large_image')
    upsertMeta('name', 'twitter:title', fullTitle)
    upsertMeta('name', 'twitter:description', desc)
    upsertMeta('name', 'twitter:image', ogImage)

    upsertJsonLd(jsonLd)
  }, [fullTitle, desc, canonical, ogImage, ogType, noIndex, jsonLdKey, locale])

  return null
}
