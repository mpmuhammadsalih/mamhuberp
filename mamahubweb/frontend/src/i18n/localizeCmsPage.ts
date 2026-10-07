import type { CmsContactCard, CmsFaqSection, CmsPage, CmsPageListItem } from '../types/api'
import type { SupportedLocale, TranslationTree } from './types'

type CmsSlug = keyof TranslationTree['cms']['pages']

function cmsSlugKey(slug: string): CmsSlug | null {
  if (slug in ({ faq: 1, contact: 1, terms: 1, privacy: 1, returns: 1 } as const)) {
    return slug as CmsSlug
  }
  return null
}

export function localizedCmsLinkLabel(slug: string, fallback: string, t: TranslationTree): string {
  const key = cmsSlugKey(slug)
  return key ? t.cms.pages[key].title : fallback
}

export function localizedCmsListItem(page: CmsPageListItem, t: TranslationTree): CmsPageListItem {
  const key = cmsSlugKey(page.slug)
  if (!key) return page
  const localized = t.cms.pages[key]
  return {
    ...page,
    page_title: localized.title,
    meta_description: localized.description ?? page.meta_description,
  }
}

export function localizedCmsPage(page: CmsPage, locale: SupportedLocale, t: TranslationTree): CmsPage {
  if (locale === 'en') return page

  const key = cmsSlugKey(page.slug)
  if (!key) return page

  const pageT = t.cms.pages[key]
  const pageType = (page.page_type || 'STATIC').toUpperCase()

  if (pageType === 'FAQ') {
    return {
      ...page,
      page_title: pageT.title,
      meta_description: pageT.description ?? page.meta_description,
      meta: { ...page.meta, sections: t.cms.faq.sections as unknown as CmsFaqSection[] },
    }
  }

  if (pageType === 'CONTACT') {
    return {
      ...page,
      page_title: pageT.title,
      meta_description: pageT.description ?? page.meta_description,
      content_html: 'intro' in pageT ? pageT.intro : page.content_html,
      meta: {
        ...page.meta,
        cards: t.cms.contact.cards as unknown as CmsContactCard[],
        form_subjects: [...t.cms.contact.subjects],
        success_message: t.cms.contact.successMessage,
      },
    }
  }

  return {
    ...page,
    page_title: pageT.title,
    meta_description: pageT.description ?? page.meta_description,
    content_html: 'html' in pageT ? pageT.html : page.content_html,
  }
}
