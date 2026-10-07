import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { GiftFinderDecor, GiftFinderPaperPlane } from '../components/gift-finder/GiftFinderDecor'
import {
  GiftFinderField,
  GiftFinderTrustBar,
  giftFinderInputClass,
  giftFinderSelectClass,
} from '../components/gift-finder/GiftFinderTrustBar'
import { HOME_CONTAINER, PRODUCT_GRID } from '../components/layout/homeLayout'
import { ProductCard } from '../components/ProductCard'
import { SeoHead } from '../components/seo/SeoHead'
import {
  IconArrowRight,
  IconBaby,
  IconCalendar,
  IconChevronDown,
  IconGift,
  IconHeart,
  IconTag,
} from '../components/icons/Icons'
import { useLocale } from '../i18n/LocaleContext'
import { ageGroupDisplayName } from '../i18n/ageGroupName'
import { catalogQueries } from '../lib/queries/catalog'
import { fetchGiftItems } from '../lib/queries/giftFinder'

const OCCASION_KEYS = [
  { value: 'birthday', labelKey: 'occasionBirthday' as const },
  { value: 'eid', labelKey: 'occasionEid' as const },
  { value: 'christmas', labelKey: 'occasionChristmas' as const },
  { value: 'new-baby', labelKey: 'occasionNewBaby' as const },
  { value: 'general', labelKey: 'occasionGeneral' as const },
]

function SelectField({
  value,
  onChange,
  children,
}: {
  value: string
  onChange: (value: string) => void
  children: React.ReactNode
}) {
  return (
    <div className="relative">
      <select value={value} onChange={(e) => onChange(e.target.value)} className={giftFinderSelectClass}>
        {children}
      </select>
      <IconChevronDown
        size={16}
        className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-gray-400"
      />
    </div>
  )
}

export function GiftFinderPage() {
  const { locale, t } = useLocale()
  const [params, setParams] = useSearchParams()
  const ageFromUrl = params.get('age') || ''
  const interestFromUrl = params.get('interest') || ''
  const priceFromUrl = params.get('max_price') || ''
  const occasionFromUrl = params.get('occasion') || ''
  const [age, setAge] = useState(ageFromUrl)
  const [interest, setInterest] = useState(interestFromUrl)
  const [maxPrice, setMaxPrice] = useState(priceFromUrl)
  const [occasion, setOccasion] = useState(occasionFromUrl)
  const [submitted, setSubmitted] = useState({
    age: ageFromUrl,
    interest: interestFromUrl,
    maxPrice: priceFromUrl,
    occasion: occasionFromUrl,
  })

  useEffect(() => {
    setAge(ageFromUrl)
    setInterest(interestFromUrl)
    setMaxPrice(priceFromUrl)
    setOccasion(occasionFromUrl)
    setSubmitted({
      age: ageFromUrl,
      interest: interestFromUrl,
      maxPrice: priceFromUrl,
      occasion: occasionFromUrl,
    })
  }, [ageFromUrl, interestFromUrl, priceFromUrl, occasionFromUrl])

  const { data: ageGroups = [] } = useQuery(catalogQueries.ageGroups)
  const { data: interests = [] } = useQuery(catalogQueries.interests)

  const { data: results = [], isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ['gift-finder', submitted.age, submitted.interest, submitted.maxPrice, submitted.occasion],
    queryFn: ({ signal }) => fetchGiftItems(submitted, signal),
  })

  function runSearch() {
    const next = new URLSearchParams()
    if (age) next.set('age', age)
    if (interest) next.set('interest', interest)
    if (maxPrice) next.set('max_price', maxPrice)
    if (occasion) next.set('occasion', occasion)
    setParams(next, { replace: true })
    setSubmitted({ age, interest, maxPrice, occasion })
  }

  return (
    <div className="bg-brand-cream pb-16">
      <SeoHead
        title={t.giftFinder.title}
        description={t.giftFinder.intro}
      />
      <div className={`${HOME_CONTAINER} py-8 lg:py-10`}>
        <div className="overflow-hidden rounded-3xl bg-gradient-to-br from-[#FFF3B0] via-[#FFE0C2] to-[#C8F5E4] px-5 py-8 sm:px-8 lg:px-10 lg:py-10">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="max-w-xl">
              <div className="flex items-start gap-3">
                <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-brand-yellow text-brand-ink shadow-sm">
                  <IconGift size={22} />
                </span>
                <div>
                  <h1 className="font-display text-3xl font-bold text-[#1A1C2E] sm:text-[2rem]">
                    {t.giftFinder.title}
                  </h1>
                  <p className="mt-2 font-catalog text-[15px] leading-relaxed text-slate-600">
                    {t.giftFinder.intro}
                  </p>
                </div>
              </div>
            </div>
            <GiftFinderDecor />
          </div>

          <form
            className="mt-8 rounded-3xl bg-white p-5 shadow-sm ring-1 ring-black/[0.04] sm:p-7 lg:p-8"
            onSubmit={(e) => {
              e.preventDefault()
              runSearch()
            }}
          >
            <div className="grid gap-6 sm:grid-cols-2 sm:gap-x-8 sm:gap-y-7">
              <GiftFinderField
                icon={<IconBaby size={20} className="text-brand-orange" />}
                iconBg="bg-[#FFF3C4]"
                label={t.giftFinder.childAge}
              >
                <SelectField value={age} onChange={setAge}>
                  <option value="">{t.giftFinder.anyAge}</option>
                  {ageGroups.map((g) => (
                    <option key={g.slug} value={g.slug}>
                      {ageGroupDisplayName(g, locale, t)}
                    </option>
                  ))}
                </SelectField>
              </GiftFinderField>

              <GiftFinderField
                icon={<IconHeart size={18} className="text-[#9333EA]" />}
                iconBg="bg-[#F3E8FF]"
                label={t.giftFinder.interest}
              >
                <SelectField value={interest} onChange={setInterest}>
                  <option value="">{t.giftFinder.anyInterest}</option>
                  {interests.map((i) => (
                    <option key={i.slug} value={i.slug}>
                      {i.interest_name}
                    </option>
                  ))}
                </SelectField>
              </GiftFinderField>

              <GiftFinderField
                icon={<IconCalendar size={18} className="text-brand-teal" />}
                iconBg="bg-[#CCFBF1]"
                label={t.giftFinder.occasion}
              >
                <SelectField value={occasion} onChange={setOccasion}>
                  <option value="">{t.home.occasion}</option>
                  {OCCASION_KEYS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {t.giftFinder[o.labelKey]}
                    </option>
                  ))}
                </SelectField>
              </GiftFinderField>

              <GiftFinderField
                icon={<IconTag size={18} className="text-[#16A34A]" />}
                iconBg="bg-[#DCFCE7]"
                label={t.giftFinder.maxBudget}
              >
                <input
                  type="number"
                  min="0"
                  value={maxPrice}
                  onChange={(e) => setMaxPrice(e.target.value)}
                  placeholder="e.g. 200"
                  className={giftFinderInputClass}
                />
              </GiftFinderField>
            </div>

            <div className="mt-8 flex flex-wrap items-center gap-4">
              <button
                type="submit"
                className="inline-flex items-center gap-2 rounded-full bg-brand-accent px-7 py-3.5 text-sm font-bold text-white shadow-md transition hover:bg-brand-accent-hover"
              >
                <IconGift size={18} />
                {t.giftFinder.findGifts}
                <IconArrowRight size={16} />
              </button>
              <GiftFinderPaperPlane />
            </div>
          </form>

          <GiftFinderTrustBar />
        </div>

        <div className="mt-10">
          {isLoading || isFetching ? (
            <p className="text-center font-catalog text-slate-500">{t.giftFinder.finding}</p>
          ) : isError ? (
            <div className="rounded-2xl bg-white px-6 py-12 text-center shadow-sm ring-1 ring-black/[0.04]">
              <p className="font-catalog text-slate-500">{t.errors.generic}</p>
              <button
                type="button"
                onClick={() => void refetch()}
                className="mt-4 rounded-full bg-brand-accent px-5 py-2 text-sm font-bold text-white"
              >
                {t.shared.retry}
              </button>
            </div>
          ) : (
            <>
              <h2 className="mb-1 font-display text-xl font-bold text-[#1A1C2E]">
                {t.giftFinder.suggestions}
              </h2>
              <p className="mb-6 font-catalog text-sm text-slate-500">
                {results.length} {results.length === 1 ? t.giftFinder.toy : t.giftFinder.toys}
              </p>
              {results.length > 0 ? (
                <div className={PRODUCT_GRID}>
                  {results.map((p) => (
                    <ProductCard key={p.item_code} product={p} badge={t.giftFinder.giftIdea} />
                  ))}
                </div>
              ) : (
                <div className="rounded-2xl bg-white px-6 py-12 text-center shadow-sm ring-1 ring-black/[0.04]">
                  <p className="font-catalog text-slate-500">
                    {t.giftFinder.noMatches}
                  </p>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
