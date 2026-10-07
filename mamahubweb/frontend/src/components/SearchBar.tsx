import { useEffect, useId, useRef, useState, type ChangeEvent, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ProductImage } from './ProductImage'
import { IconCamera, IconClose, IconSearch } from './icons/Icons'
import { productDisplayName } from '../i18n/productName'
import { useFormatMoney } from '../i18n/useFormatMoney'
import { useLocale } from '../i18n/LocaleContext'
import { toTitleCase } from '../lib/textCase'
import { getApiErrorMessage, getDataWithMeta, postForm } from '../lib/api'
import { LIST_STALE_TIME } from '../lib/queryClient'
import type { Product } from '../types/api'

const MIN_QUERY = 2
const SUGGEST_LIMIT = 8
const DEBOUNCE_MS = 280

interface Props {
  className?: string
  placeholder?: string
}

function useDebouncedValue(value: string, delay: number) {
  const [debounced, setDebounced] = useState(value)

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delay)
    return () => window.clearTimeout(timer)
  }, [value, delay])

  return debounced
}

export function SearchBar({ className = '', placeholder }: Props) {
  const navigate = useNavigate()
  const { locale, t } = useLocale()
  const formatMoney = useFormatMoney()
  const panelId = useId()
  const rootRef = useRef<HTMLFormElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [visualBusy, setVisualBusy] = useState(false)
  const [visualError, setVisualError] = useState<string | null>(null)
  const [visualPreview, setVisualPreview] = useState<string | null>(null)
  const [visualProducts, setVisualProducts] = useState<Product[] | null>(null)
  const resolvedPlaceholder = placeholder ?? t.nav.searchPlaceholder
  const trimmed = query.trim()
  const debounced = useDebouncedValue(trimmed, DEBOUNCE_MS)
  const canSuggest = debounced.length >= MIN_QUERY && !visualBusy && visualProducts == null
  const panelOpen = open && (canSuggest || visualBusy || visualProducts != null || Boolean(visualError))
  const displayQuery = trimmed.toUpperCase()

  const { data, isFetching } = useQuery({
    queryKey: ['search-suggest', debounced],
    queryFn: ({ signal }) =>
      getDataWithMeta<Product[]>(
        '/products',
        { search: debounced, page: 1, page_size: SUGGEST_LIMIT },
        { signal },
      ),
    enabled: canSuggest && panelOpen,
    staleTime: LIST_STALE_TIME,
    placeholderData: (previous) => previous,
  })

  const products = data?.data ?? []

  useEffect(() => {
    return () => {
      if (visualPreview) URL.revokeObjectURL(visualPreview)
    }
  }, [visualPreview])

  useEffect(() => {
    function onPointerDown(event: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false)
      }
    }

    function onEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false)
    }

    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onEscape)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onEscape)
    }
  }, [])

  function goToResults(value = trimmed) {
    setOpen(false)
    if (value) navigate(`/products?q=${encodeURIComponent(value)}`)
    else navigate('/products')
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault()
    goToResults()
  }

  function clearVisual() {
    if (visualPreview) URL.revokeObjectURL(visualPreview)
    setVisualPreview(null)
    setVisualProducts(null)
    setVisualError(null)
    setVisualBusy(false)
    if (fileRef.current) fileRef.current.value = ''
  }

  function clearQuery() {
    setQuery('')
    setOpen(false)
    clearVisual()
  }

  async function searchByPhoto(file: File) {
    clearVisual()
    const preview = URL.createObjectURL(file)
    setVisualPreview(preview)
    setVisualBusy(true)
    setOpen(true)
    try {
      const form = new FormData()
      form.append('file', file)
      const result = await postForm<{ query: string; products: Product[] }>('/search/visual', form)
      setQuery(result.query || '')
      setVisualProducts(result.products ?? [])
      setVisualError(null)
    } catch (error) {
      setVisualProducts([])
      setVisualError(getApiErrorMessage(error) || t.nav.photoSearchFailed)
    } finally {
      setVisualBusy(false)
    }
  }

  function onPickPhoto(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (file) void searchByPhoto(file)
  }

  return (
    <form
      ref={rootRef}
      onSubmit={onSubmit}
      className={`relative z-50 flex-1 ${className}`}
      role="search"
    >
      <IconSearch
        size={18}
        className="pointer-events-none absolute start-4 top-1/2 z-10 -translate-y-1/2 text-slate-400"
      />
      <input
        type="search"
        value={query}
        onChange={(event) => {
          setQuery(event.target.value)
          if (visualPreview) URL.revokeObjectURL(visualPreview)
          setVisualPreview(null)
          setVisualProducts(null)
          setVisualError(null)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        placeholder={resolvedPlaceholder}
        aria-label={resolvedPlaceholder}
        aria-expanded={panelOpen}
        aria-controls={panelId}
        aria-autocomplete="list"
        autoComplete="off"
        role="combobox"
        className="w-full rounded-full border border-slate-200 bg-white py-3 ps-11 pe-[6.5rem] text-base text-slate-700 outline-none transition placeholder:text-slate-400 focus:border-brand-accent focus:ring-2 focus:ring-brand-tint [&::-webkit-search-cancel-button]:hidden md:py-3 md:text-sm"
      />
      <input
        ref={fileRef}
        type="file"
        accept="image/jpeg,image/png,image/webp,image/gif,.jpg,.jpeg,.png,.webp"
        className="sr-only"
        onChange={onPickPhoto}
      />
      <button
        type="button"
        onClick={() => fileRef.current?.click()}
        disabled={visualBusy}
        className="absolute end-[3.25rem] top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full text-slate-500 transition hover:bg-brand-tint hover:text-brand-accent disabled:opacity-50"
        aria-label={t.nav.searchByPhoto}
        title={t.nav.searchByPhoto}
      >
        <IconCamera size={18} />
      </button>
      {trimmed || visualPreview ? (
        <button
          type="button"
          onClick={clearQuery}
          className="absolute end-1.5 top-1/2 flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-full text-slate-400 transition hover:bg-slate-50 hover:text-slate-700"
          aria-label={t.nav.clearSearch}
        >
          <IconClose size={18} />
        </button>
      ) : (
        <button
          type="submit"
          className="absolute end-1.5 top-1/2 flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-full bg-brand-accent text-white transition hover:bg-brand-accent-hover"
          aria-label={t.nav.shop}
        >
          <IconSearch size={16} />
        </button>
      )}

      {panelOpen ? (
        <div
          id={panelId}
          role="listbox"
          aria-label={t.nav.productsFor.replace('{query}', displayQuery)}
          className="absolute inset-x-0 top-[calc(100%+10px)] z-[70] overflow-hidden rounded-2xl border border-slate-100 bg-white p-4 shadow-[0_16px_40px_rgba(15,23,42,0.12)] sm:p-5"
        >
          <p className="text-[13px] font-bold uppercase tracking-wide text-slate-900">
            {visualBusy
              ? t.nav.searchingPhoto
              : t.nav.productsFor.replace('{query}', displayQuery || t.nav.searchByPhoto)}
          </p>
          {visualPreview ? (
            <div className="mt-3 flex items-center gap-3">
              <img
                src={visualPreview}
                alt=""
                className="h-14 w-14 rounded-xl object-cover ring-1 ring-brand-border"
              />
              <p className="text-sm text-slate-500">
                {visualBusy ? t.nav.searchingPhoto : trimmed || t.nav.searchByPhoto}
              </p>
            </div>
          ) : null}
          {visualError ? <p className="mt-3 text-sm text-red-600">{visualError}</p> : null}

          {(visualBusy || (isFetching && products.length === 0 && visualProducts == null)) ? (
            <div className="-mx-1 mt-4 flex gap-3 overflow-hidden px-1">
              {Array.from({ length: 4 }).map((_, index) => (
                <div key={index} className="w-[132px] shrink-0 sm:w-[148px]">
                  <div className="aspect-square animate-pulse rounded-xl bg-slate-100" />
                  <div className="mt-2 h-3 w-5/6 animate-pulse rounded bg-slate-100" />
                  <div className="mt-2 h-3 w-1/2 animate-pulse rounded bg-slate-100" />
                </div>
              ))}
            </div>
          ) : (visualProducts ?? products).length === 0 ? (
            <p className="mt-4 text-sm text-slate-500">{t.nav.noSearchResults}</p>
          ) : (
            <div className="-mx-1 mt-4 flex gap-3 overflow-x-auto px-1 pb-1 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
              {(visualProducts ?? products).map((product) => (
                <SearchProductCard
                  key={product.item_code}
                  product={product}
                  locale={locale}
                  formatMoney={formatMoney}
                  itemLabel={t.common.item}
                  onPick={() => setOpen(false)}
                />
              ))}
            </div>
          )}

          {trimmed && !visualBusy ? (
            <Link
              to={`/products?q=${encodeURIComponent(trimmed)}`}
              onClick={() => setOpen(false)}
              className="mt-4 flex w-full items-center justify-center rounded-lg border border-brand-accent px-4 py-2.5 text-[13px] font-semibold uppercase tracking-wide text-slate-800 transition hover:bg-brand-cream-alt"
            >
              {t.nav.viewAllSearch.replace('{query}', displayQuery)}
            </Link>
          ) : null}
        </div>
      ) : null}
    </form>
  )
}

function SearchProductCard({
  product,
  locale,
  formatMoney,
  itemLabel,
  onPick,
}: {
  product: Product
  locale: 'en' | 'ar'
  formatMoney: (amount: number) => string
  itemLabel: string
  onPick: () => void
}) {
  const hasOffer =
    product.offer_price != null &&
    product.offer_price > 0 &&
    product.offer_price < (product.retail_price ?? 0)
  const unitPrice = hasOffer ? product.offer_price! : product.retail_price ?? 0
  const rawName = productDisplayName(product, locale)
  const name = locale === 'ar' ? rawName : toTitleCase(rawName || `${itemLabel} ${product.item_code}`)

  return (
    <Link
      to={`/products/${product.item_code}`}
      role="option"
      onClick={onPick}
      className="w-[132px] shrink-0 sm:w-[148px]"
    >
      <div className="flex aspect-square items-center justify-center rounded-xl bg-[#FAFAFA] p-2">
        <ProductImage src={product.primary_image_url} alt={name} className="max-h-full max-w-full" />
      </div>
      <p className="mt-2 line-clamp-2 min-h-10 text-[13px] leading-5 text-slate-800">{name}</p>
      <p className="mt-1 text-sm font-bold text-slate-900">{formatMoney(unitPrice)}</p>
    </Link>
  )
}
