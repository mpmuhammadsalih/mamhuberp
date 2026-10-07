import { useQuery } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { CmsPageContent } from '../components/cms/CmsPageContent'
import { InfoPageShell } from '../components/info/InfoPageShell'
import { PAGE_CONTAINER } from '../components/layout/homeLayout'
import { SeoHead } from '../components/seo/SeoHead'
import { useLocale } from '../i18n/LocaleContext'
import { localizedCmsPage } from '../i18n/localizeCmsPage'
import { getData, getApiErrorMessage } from '../lib/api'
import type { CmsPage as CmsPageData } from '../types/api'

export function CmsPage() {
  const { slug } = useParams()
  const { locale, t } = useLocale()

  const { data: page, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ['cms', slug],
    queryFn: () => getData<CmsPageData>(`/cms/pages/${slug}`),
    enabled: Boolean(slug),
    retry: 1,
    refetchOnMount: 'always',
    staleTime: 30_000,
  })

  if (isLoading) {
    return <div className={`${PAGE_CONTAINER} py-12`}>{t.cms.shell.loading}</div>
  }

  if (isError || !page) {
    const message = getApiErrorMessage(error)
    const backendDown =
      message.includes('5055') ||
      message.includes('Backend unavailable') ||
      message.includes('Could not reach') ||
      message.includes('Network Error')

    return (
      <div className={`${PAGE_CONTAINER} py-12`}>
        <h1 className="text-2xl font-bold text-brand-ink">{t.cms.shell.notFound}</h1>
        <p className="mt-3 text-brand-sage">
          {backendDown
            ? 'The storefront API is not reachable. Start Nova from d:\\webapps\\Nova with python app.py (port 5055), then try again.'
            : `${t.cms.shell.loadFailed} ${message}`}
        </p>
        <button
          type="button"
          onClick={() => refetch()}
          disabled={isFetching}
          className="mt-6 rounded-xl bg-brand-tan px-5 py-2.5 text-sm font-bold text-white hover:bg-brand-tan-dark disabled:opacity-60"
        >
          {isFetching ? t.cms.shell.retrying : t.cms.shell.tryAgain}
        </button>
      </div>
    )
  }

  const localized = localizedCmsPage(page, locale, t)

  return (
    <>
      <SeoHead
        title={localized.page_title}
        description={localized.meta_description || localized.page_title}
      />
      <InfoPageShell title={localized.page_title} subtitle={localized.meta_description}>
        <CmsPageContent page={localized} />
      </InfoPageShell>
    </>
  )
}
