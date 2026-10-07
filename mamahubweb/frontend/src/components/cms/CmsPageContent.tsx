import type { CmsPage } from '../../types/api'
import { CmsContactPage } from './CmsContactPage'
import { CmsFaqSections } from './CmsFaqSections'

interface Props {
  page: CmsPage
}

export function CmsPageContent({ page }: Props) {
  const pageType = (page.page_type || 'STATIC').toUpperCase()

  if (pageType === 'FAQ') {
    return (
      <div className="mx-auto max-w-3xl space-y-6">
        {page.content_html ? (
          <article className="cms-content" dangerouslySetInnerHTML={{ __html: page.content_html }} />
        ) : null}
        <CmsFaqSections sections={page.meta?.sections} />
      </div>
    )
  }

  if (pageType === 'CONTACT') {
    return <CmsContactPage page={page} />
  }

  return (
    <article
      className="cms-content mx-auto max-w-3xl"
      dangerouslySetInnerHTML={{ __html: page.content_html || '' }}
    />
  )
}
