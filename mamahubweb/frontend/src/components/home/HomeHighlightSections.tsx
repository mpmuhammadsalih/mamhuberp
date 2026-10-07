import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ProductCard } from '../ProductCard'
import { ProductImage } from '../ProductImage'
import { IconArrowRight, IconBolt, IconChevronDown } from '../icons/Icons'
import { HOME_CONTAINER, PRODUCT_GRID } from '../layout/homeLayout'
import { ageGroupDisplayName } from '../../i18n/ageGroupName'
import { productDisplayName } from '../../i18n/productName'
import { useFormatMoney } from '../../i18n/useFormatMoney'
import { useLocale } from '../../i18n/LocaleContext'
import { toTitleCase } from '../../lib/textCase'
import { catalogQueries } from '../../lib/queries/catalog'
import { fetchGiftItems, type GiftFinderFilters } from '../../lib/queries/giftFinder'
import type { Product } from '../../types/api'

const BUDGETS = ['50', '100', '200', '500']

function msUntilQatarMidnight() {
  const now = new Date()
  const qatar = new Date(now.toLocaleString('en-US', { timeZone: 'Asia/Qatar' }))
  const next = new Date(qatar)
  next.setHours(24, 0, 0, 0)
  return Math.max(0, next.getTime() - qatar.getTime())
}

function splitCountdown(ms: number) {
  const total = Math.floor(ms / 1000)
  return {
    hours: String(Math.floor(total / 3600)).padStart(2, '0'),
    mins: String(Math.floor((total % 3600) / 60)).padStart(2, '0'),
    secs: String(total % 60).padStart(2, '0'),
  }
}

interface Props {
  trending: Product[]
  deal?: Product | null
}

export function HomeHighlightSections({ trending, deal }: Props) {
  const { t } = useLocale()
  const [filters, setFilters] = useState<GiftFinderFilters | null>(null)
  const {
    data: giftProducts = [],
    isFetching,
    isError,
    refetch,
  } = useQuery({
    queryKey: ['home-gift-finder', filters?.age, filters?.maxPrice, filters?.occasion],
    queryFn: ({ signal }) => fetchGiftItems(filters!, signal),
    enabled: filters != null,
  })

  useEffect(() => {
    if (!filters) return
    document.getElementById('home-gift-results')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [filters, giftProducts, isFetching])

  return (
    <div className={`${HOME_CONTAINER} space-y-8 pb-10 pt-4 lg:space-y-10 lg:pb-12`}>
      {trending.length > 0 ? (
        <section>
          <div className="mb-5 flex items-center justify-between gap-4">
            <h2 className="font-display text-xl font-bold text-brand-ink sm:text-2xl">
              <span className="me-2 inline-block text-brand-orange" aria-hidden>★</span>
              {t.home.trendingNow}
            </h2>
            <Link
              to="/featured"
              className="text-sm font-semibold text-brand-accent hover:underline"
            >
              {t.common.viewAll} →
            </Link>
          </div>
          <div className="-mx-1 flex gap-3 overflow-x-auto px-1 pb-1 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden sm:grid sm:grid-cols-3 sm:overflow-visible lg:grid-cols-6">
            {trending.slice(0, 6).map((product) => (
              <ProductCard key={product.item_code} product={product} />
            ))}
          </div>
        </section>
      ) : null}

      <div className={`grid gap-4 lg:gap-5 ${deal ? 'lg:grid-cols-[1.4fr_1fr]' : ''}`}>
        <HomeGiftFinderPanel searching={isFetching} onSearch={setFilters} />
        {deal ? <HomeDealPanel product={deal} /> : null}
      </div>

      {filters ? (
        <section id="home-gift-results" className="scroll-mt-28">
          {isFetching ? (
            <p className="text-center text-sm text-slate-500">{t.giftFinder.finding}</p>
          ) : isError ? (
            <div className="rounded-2xl bg-white px-6 py-10 text-center shadow-sm ring-1 ring-black/[0.04]">
              <p className="text-sm text-slate-500">{t.errors.generic}</p>
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
              <div className="mb-5 flex items-end justify-between gap-4">
                <div>
                  <h2 className="font-display text-xl font-bold text-brand-ink sm:text-2xl">
                    {t.giftFinder.suggestions}
                  </h2>
                  <p className="mt-1 text-sm text-slate-500">
                    {giftProducts.length} {giftProducts.length === 1 ? t.giftFinder.toy : t.giftFinder.toys}
                  </p>
                </div>
              </div>
              {giftProducts.length > 0 ? (
                <div className={PRODUCT_GRID}>
                  {giftProducts.map((product) => (
                    <ProductCard key={product.item_code} product={product} badge={t.giftFinder.giftIdea} />
                  ))}
                </div>
              ) : (
                <div className="rounded-2xl bg-white px-6 py-10 text-center shadow-sm ring-1 ring-black/[0.04]">
                  <p className="text-sm text-slate-500">{t.giftFinder.noMatches}</p>
                </div>
              )}
            </>
          )}
        </section>
      ) : null}
    </div>
  )
}

function HomeGiftFinderPanel({
  onSearch,
  searching,
}: {
  onSearch: (filters: GiftFinderFilters) => void
  searching: boolean
}) {
  const { locale, t } = useLocale()
  const { data: ageGroups = [] } = useQuery(catalogQueries.ageGroups)
  const [age, setAge] = useState('')
  const [budget, setBudget] = useState('')
  const [occasion, setOccasion] = useState('')

  function onSubmit(event: FormEvent) {
    event.preventDefault()
    onSearch({
      age,
      interest: '',
      maxPrice: budget,
      occasion,
    })
  }

  return (
    <section className="relative overflow-hidden rounded-3xl bg-gradient-to-r from-[#FFF3B0] via-[#FFE0C2] to-[#C8F5E4] p-5 sm:p-6">
      <div
        className="pointer-events-none absolute -start-10 -top-12 h-36 w-36 rounded-full bg-[#FFE27A]/80 blur-2xl"
        aria-hidden
      />
      <div
        className="pointer-events-none absolute -end-8 bottom-0 h-40 w-40 rounded-full bg-[#7DD3FC]/50 blur-2xl"
        aria-hidden
      />
      <picture className="pointer-events-none absolute inset-y-0 end-0 z-0 w-[46%] min-w-[9.5rem] max-w-[18rem] sm:w-[42%] lg:max-w-[16rem]">
        <source srcSet="/decor/gift-finder-scene.webp" type="image/webp" />
        <img
          src="/decor/gift-finder-scene.png"
          alt=""
          width={640}
          height={640}
          loading="lazy"
          decoding="async"
          className="h-full w-full object-contain object-bottom [object-position:right_bottom] mix-blend-multiply rtl:[object-position:left_bottom]"
        />
      </picture>
      <div className="relative z-10 pe-[38%] sm:pe-[40%]">
        <div className="flex items-start gap-3">
          <picture>
            <source srcSet="/decor/gift-finder-icon.webp" type="image/webp" />
            <img
              src="/decor/gift-finder-icon.png"
              alt=""
              width={56}
              height={56}
              className="h-14 w-14 shrink-0 object-contain mix-blend-multiply drop-shadow-sm"
            />
          </picture>
          <div>
            <h3 className="font-display text-xl font-bold text-slate-900">{t.home.findPerfectGift}</h3>
            <p className="mt-1 max-w-md text-sm text-slate-600">{t.home.findPerfectGiftIntro}</p>
          </div>
        </div>
        <form onSubmit={onSubmit} className="relative mt-5 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
          <HomeSelect value={age} onChange={setAge} label={t.home.age}>
            <option value="">{t.home.age}</option>
            {ageGroups.map((group) => (
              <option key={group.slug} value={group.slug}>
                {ageGroupDisplayName(group, locale, t)}
              </option>
            ))}
          </HomeSelect>
          <HomeSelect value={budget} onChange={setBudget} label={t.home.budget}>
            <option value="">{t.home.budget}</option>
            {BUDGETS.map((amount) => (
              <option key={amount} value={amount}>
                QAR {amount}
              </option>
            ))}
          </HomeSelect>
          <HomeSelect value={occasion} onChange={setOccasion} label={t.home.occasion}>
            <option value="">{t.home.occasion}</option>
            <option value="birthday">{t.giftFinder.occasionBirthday}</option>
            <option value="eid">{t.giftFinder.occasionEid}</option>
            <option value="christmas">{t.giftFinder.occasionChristmas}</option>
            <option value="new-baby">{t.giftFinder.occasionNewBaby}</option>
            <option value="general">{t.giftFinder.occasionGeneral}</option>
          </HomeSelect>
          <button
            type="submit"
            disabled={searching}
            className="inline-flex items-center justify-center gap-1.5 rounded-full bg-brand-accent px-5 py-2.5 text-sm font-bold text-white shadow-sm transition hover:bg-brand-accent-hover disabled:opacity-70"
          >
            {searching ? t.giftFinder.finding : t.giftFinder.findGifts}
            <IconArrowRight size={16} />
          </button>
        </form>
      </div>
    </section>
  )
}

function HomeSelect({
  value,
  onChange,
  label,
  children,
}: {
  value: string
  onChange: (value: string) => void
  label: string
  children: ReactNode
}) {
  return (
    <label className="relative min-w-[8.5rem] flex-1">
      <span className="sr-only">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full appearance-none rounded-full border border-white/80 bg-white px-4 py-2.5 pe-9 text-sm text-slate-700 outline-none"
      >
        {children}
      </select>
      <IconChevronDown size={14} className="pointer-events-none absolute end-3 top-1/2 -translate-y-1/2 text-slate-400" />
    </label>
  )
}

function HomeDealPanel({ product }: { product: Product }) {
  const { locale, t } = useLocale()
  const formatMoney = useFormatMoney()
  const [remaining, setRemaining] = useState(msUntilQatarMidnight)
  const clock = useMemo(() => splitCountdown(remaining), [remaining])
  const hasOffer =
    product.offer_price != null &&
    product.offer_price > 0 &&
    product.offer_price < (product.retail_price ?? 0)
  const rawName = productDisplayName(product, locale)
  const name = locale === 'ar' ? rawName : toTitleCase(rawName || `${t.common.item} ${product.item_code}`)

  useEffect(() => {
    const id = window.setInterval(() => setRemaining(msUntilQatarMidnight()), 1000)
    return () => window.clearInterval(id)
  }, [])

  return (
    <section className="overflow-hidden rounded-3xl bg-gradient-to-br from-brand-orange to-[#ff7a1a] p-5 text-white sm:p-6">
      <div className="mb-4 flex items-start justify-between gap-3">
        <h3 className="flex items-center gap-2 font-display text-lg font-bold">
          <IconBolt size={20} className="text-brand-yellow" />
          {t.home.dealOfTheDay}
        </h3>
        <div className="flex gap-2 text-center">
          <TimeBox value={clock.hours} label={t.home.hours} />
          <TimeBox value={clock.mins} label={t.home.mins} />
          <TimeBox value={clock.secs} label={t.home.secs} />
        </div>
      </div>
      <div className="flex items-center gap-4 rounded-2xl bg-white p-3 text-slate-900">
        <Link to={`/products/${product.item_code}`} className="flex h-24 w-24 shrink-0 items-center justify-center rounded-xl bg-[#FAFAFA]">
          <ProductImage
            src={product.primary_image_url}
            alt={name}
            className="max-h-full max-w-full object-contain"
          />
        </Link>
        <div className="min-w-0 flex-1">
          <Link to={`/products/${product.item_code}`} className="line-clamp-2 font-semibold">
            {name}
          </Link>
          <div className="mt-1 flex items-baseline gap-2">
            {hasOffer ? (
              <>
                <span className="text-sm text-slate-400 line-through">{formatMoney(product.retail_price ?? 0)}</span>
                <span className="text-lg font-bold text-brand-accent">{formatMoney(product.offer_price!)}</span>
              </>
            ) : (
              <span className="text-lg font-bold text-brand-accent">{formatMoney(product.retail_price ?? 0)}</span>
            )}
          </div>
          <Link
            to={`/products/${product.item_code}`}
            className="mt-3 inline-flex rounded-full bg-brand-accent px-4 py-2 text-sm font-bold text-white transition hover:bg-brand-accent-hover"
          >
            {t.home.buyNow}
          </Link>
        </div>
      </div>
    </section>
  )
}

function TimeBox({ value, label }: { value: string; label: string }) {
  return (
    <div>
      <p className="min-w-[2.4rem] rounded-lg bg-white/15 px-1.5 py-1 font-mono text-sm font-bold">{value}</p>
      <p className="mt-0.5 text-[10px] uppercase tracking-wide text-white/80">{label}</p>
    </div>
  )
}
