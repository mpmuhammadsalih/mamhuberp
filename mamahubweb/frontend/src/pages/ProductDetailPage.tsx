import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { SimilarProductsCarousel } from '../components/catalog/SimilarProductsCarousel'
import { SuggestedProductsCarousel } from '../components/catalog/SuggestedProductsCarousel'
import { GiftWrapOptions } from '../components/checkout/GiftWrapOptions'
import { PAGE_CONTAINER } from '../components/layout/homeLayout'
import { AddToCartControl } from '../components/AddToCartControl'
import { Product3DViewer } from '../components/Product3DViewer'
import { ProductImage } from '../components/ProductImage'
import { StarRatingInput } from '../components/reviews/StarRatingInput'
import { SeoHead } from '../components/seo/SeoHead'
import {
  IconCheck,
  IconStar,
} from '../components/icons/Icons'
import { WishlistButton } from '../components/WishlistButton'
import { getData, postData } from '../lib/api'
import { syncCartCache } from '../lib/cartOptimistic'
import { fetchCart } from '../lib/queries/cart'
import { useFormatMoney } from '../i18n/useFormatMoney'
import { absoluteUrl, productListingDescription, productListingTitle } from '../lib/seo'
import { productDisplayName } from '../i18n/productName'
import { productDescription, productSpecifications } from '../i18n/productDescription'
import { brandDisplayName } from '../i18n/brandName'
import { useLocale } from '../i18n/LocaleContext'
import { storage } from '../lib/storage'
import { toSentenceCase, toTitleCase } from '../lib/textCase'
import type { CartData, GiftWrapOption, Product, Review } from '../types/api'

import type { TranslationTree } from '../i18n/types'

type DetailTab = 'description' | 'specifications'

const HIDDEN_SPEC_LABELS = new Set([
  'unit',
  'uom',
  'unitit',
  'manufacturerid',
  'manufacturer id',
  'manufacturer_id',
  'manufacturer',
  'وحده',
  'وحدة',
  'رقم المصنع',
  'معرف الشركة المصنعة',
  'معرف المصنع',
])

function isHiddenSpecLabel(label: string) {
  const key = label.toLowerCase().replace(/[\s_-]+/g, '')
  return HIDDEN_SPEC_LABELS.has(label.toLowerCase()) || HIDDEN_SPEC_LABELS.has(key)
}

function summaryBullets(description: string | null | undefined, t: TranslationTree): string[] {
  if (description?.trim()) {
    const parts = description
      .split(/(?:\.\s+|\n+)/)
      .map((s) => s.trim())
      .filter(Boolean)
    if (parts.length > 0) return parts.slice(0, 6)
  }
  return [t.product.defaultBullet1, t.product.defaultBullet2, t.product.defaultBullet3]
}

export function ProductDetailPage() {
  const { itemCode } = useParams()
  const { locale, t } = useLocale()
  const formatMoney = useFormatMoney()
  const queryClient = useQueryClient()
  const [activeTab, setActiveTab] = useState<DetailTab>('description')
  const [selectedAddonCode, setSelectedAddonCode] = useState<number | null>(null)
  const [selectedImage, setSelectedImage] = useState(0)
  const [reviewRating, setReviewRating] = useState(5)
  const [reviewText, setReviewText] = useState('')

  const { data: product, isLoading } = useQuery({
    queryKey: ['product', itemCode],
    queryFn: () => getData<Product>(`/products/${itemCode}`),
    enabled: Boolean(itemCode),
  })

  const { data: cart } = useQuery({
    queryKey: ['cart'],
    queryFn: ({ signal }) => fetchCart({ signal }),
    staleTime: 60_000,
  })

  useEffect(() => {
    setSelectedImage(0)
    const child = queryClient.getQueryData<CartData>(['cart'])?.items.find(
      (item) => item.parent_item_code === Number(itemCode),
    )
    setSelectedAddonCode(child ? child.item_code : null)
  }, [itemCode, queryClient])

  const { data: reviewsData } = useQuery({
    queryKey: ['reviews', itemCode],
    queryFn: () =>
      getData<{ reviews: Review[]; summary: { avg_rating: number; review_count: number } }>(
        `/reviews/products/${itemCode}`,
      ),
    enabled: Boolean(itemCode),
  })

  const displayPrice = product
    ? product.offer_price != null &&
      product.offer_price > 0 &&
      product.offer_price < (product.retail_price ?? 0)
      ? product.offer_price
      : product.retail_price ?? 0
    : 0

  const wrapAddons = (product?.addons ?? []).filter(
    (addon) => !addon.addon_type || addon.addon_type === 'gift_wrap',
  )
  const selectedAddon = wrapAddons.find((addon) => addon.item_code === selectedAddonCode) ?? null
  const addonPrice = selectedAddon
    ? selectedAddon.offer_price != null &&
      selectedAddon.offer_price > 0 &&
      selectedAddon.offer_price < (selectedAddon.retail_price ?? 0)
      ? selectedAddon.offer_price
      : selectedAddon.retail_price ?? 0
    : 0
  const wrapOptions: GiftWrapOption[] = [
    { code: 'none', label: 'No gift wrap', fee: 0, enabled: true },
    ...wrapAddons.map((addon) => ({
      code: String(addon.item_code),
      label: productDisplayName(addon, locale) || addon.item_name || `Item ${addon.item_code}`,
      fee:
        addon.offer_price != null &&
        addon.offer_price > 0 &&
        addon.offer_price < (addon.retail_price ?? 0)
          ? addon.offer_price
          : addon.retail_price ?? 0,
      enabled: addon.addon_enabled !== false,
    })),
  ]
  const paidWrapLocked = wrapAddons.some((addon) => addon.addon_enabled === false)
  const selectedAddonAllowed = selectedAddon?.addon_enabled !== false
  const parentInCart = cart?.items.find(
    (item) => item.item_code === Number(itemCode) && !item.parent_item_code,
  )

  const syncAddon = useMutation({
    mutationFn: (addonItemCode: number | null) =>
      postData<CartData>('/cart/addon', {
        parent_item_code: Number(itemCode),
        addon_item_code: addonItemCode,
      }),
    onSuccess: (nextCart) => {
      syncCartCache(queryClient, nextCart)
    },
  })

  useEffect(() => {
    if (selectedAddonCode == null) return
    const selected = wrapAddons.find((addon) => addon.item_code === selectedAddonCode)
    if (selected && selected.addon_enabled === false) {
      setSelectedAddonCode(null)
    }
  }, [selectedAddonCode, wrapAddons])

  const submitReview = useMutation({
    mutationFn: () =>
      postData('/reviews', {
        item_code: Number(itemCode),
        rating: reviewRating,
        review_text: reviewText,
      }),
    onSuccess: () => {
      setReviewText('')
      queryClient.invalidateQueries({ queryKey: ['reviews', itemCode] })
    },
  })

  const galleryImages = useMemo(() => {
    if (!product) return []
    const urls: string[] = []
    const fromApi = product.images ?? []
    const sorted = [...fromApi].sort((a, b) => {
      if (a.primary && !b.primary) return -1
      if (!a.primary && b.primary) return 1
      return 0
    })
    for (const img of sorted) {
      if (img.image_url && !urls.includes(img.image_url)) urls.push(img.image_url)
    }
    const primary = product.primary_image_url
    if (primary && !urls.includes(primary)) urls.unshift(primary)
    return urls
  }, [product])

  const specificationRows = useMemo(() => {
    if (!product) return []
    return productSpecifications(product, locale)
  }, [product, locale])

  const { structuredSpecs, featureBullets } = useMemo(() => {
    const structured: Array<{ label: string; value: string }> = []
    const bullets: string[] = []
    for (const spec of specificationRows) {
      const label = spec.label.trim()
      const value = spec.value.trim()
      if (!value) continue
      if (isHiddenSpecLabel(label)) continue
      if (label.toLowerCase() === 'details' || label === '') {
        bullets.push(value)
      } else {
        structured.push({ label, value })
      }
    }
    return { structuredSpecs: structured, featureBullets: bullets }
  }, [specificationRows])

  if (isLoading || !product) {
    return (
      <div className="font-catalog bg-brand-cream pb-16">
        <div className={`${PAGE_CONTAINER} py-8`}>
          <div className="grid gap-8 lg:grid-cols-[minmax(0,420px)_minmax(0,1fr)]">
            <div className="aspect-square max-w-[420px] animate-pulse rounded-[28px] bg-brand-tint/70" />
            <div className="space-y-4">
              <div className="h-8 w-3/4 animate-pulse rounded-lg bg-brand-tint" />
              <div className="h-6 w-1/3 animate-pulse rounded-lg bg-brand-tint" />
              <div className="h-24 animate-pulse rounded-lg bg-brand-cream-alt" />
              <div className="h-11 w-40 animate-pulse rounded-lg bg-brand-border" />
            </div>
          </div>
        </div>
      </div>
    )
  }

  const hasOffer =
    product.offer_price != null &&
    product.offer_price > 0 &&
    product.offer_price < (product.retail_price ?? 0)

  const maxQty = Math.max(1, product.current_stock || 1)
  const displayDescription = productDescription(product, locale)
  const bullets = summaryBullets(displayDescription, t)
  const reviews = reviewsData?.reviews ?? []
  const mainImage = galleryImages[selectedImage]
  const unitPrice = hasOffer ? product.offer_price! : product.retail_price ?? 0
  const displayName = productDisplayName(product, locale)
  const displayBrand = brandDisplayName(product, locale)
  const listingTitle = productListingTitle(product, displayName || t.shared.product)
  const listingDescription = productListingDescription(product, displayName)
  const productUrl = absoluteUrl(`/products/${product.item_code}`)
  function selectWrap(code: string) {
    const next = code === 'none' ? null : Number(code)
    setSelectedAddonCode(next)
    if (!parentInCart) return
    const allowed =
      next == null ||
      wrapAddons.find((addon) => addon.item_code === next)?.addon_enabled !== false
    if (!allowed) return
    syncAddon.mutate(next)
  }

  const wrapSelectedCode =
    selectedAddonCode == null || !selectedAddonAllowed ? 'none' : String(selectedAddonCode)

  const wrapPanel = wrapAddons.length > 0 && (
    <>
      <GiftWrapOptions
        variant="plain"
        layout="fill"
        title={t.product.yourChoiceOf}
        options={wrapOptions}
        selectedCode={wrapSelectedCode}
        onSelect={selectWrap}
      />
      {paidWrapLocked ? (
        <p className="mt-2 text-[13px] text-gray-500">{t.product.freeWrapOnlyNote}</p>
      ) : null}
    </>
  )

  const productJsonLd = [
    {
      '@context': 'https://schema.org',
      '@type': 'Product',
      name: displayName,
      description: listingDescription || displayDescription || displayName,
      image: absoluteUrl(mainImage),
      sku: String(product.item_code),
      brand: displayBrand ? { '@type': 'Brand', name: displayBrand } : undefined,
      offers: {
        '@type': 'Offer',
        url: productUrl,
        priceCurrency: 'QAR',
        price: unitPrice,
        availability:
          (product.current_stock ?? 0) > 0
            ? 'https://schema.org/InStock'
            : 'https://schema.org/OutOfStock',
      },
    },
    {
      '@context': 'https://schema.org',
      '@type': 'BreadcrumbList',
      itemListElement: [
        { '@type': 'ListItem', position: 1, name: 'Home', item: absoluteUrl('/') },
        { '@type': 'ListItem', position: 2, name: 'Products', item: absoluteUrl('/products') },
        { '@type': 'ListItem', position: 3, name: displayName || listingTitle, item: productUrl },
      ],
    },
  ]

  return (
    <div className="font-catalog bg-brand-cream pb-16">
      <SeoHead
        title={listingTitle}
        description={listingDescription}
        image={mainImage}
        ogType="product"
        jsonLd={productJsonLd}
      />
      <div className={`${PAGE_CONTAINER} py-8 lg:py-10`}>
        <div
          className={`grid min-w-0 items-start gap-6 sm:gap-8 ${
            wrapAddons.length > 0
              ? 'lg:grid-cols-[minmax(0,auto)_minmax(0,1fr)] 2xl:grid-cols-[minmax(0,auto)_minmax(22rem,1fr)_minmax(16rem,22rem)]'
              : 'lg:grid-cols-[minmax(0,auto)_minmax(16rem,1fr)]'
          }`}
        >
          <div className="min-w-0">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:gap-4">
              {galleryImages.length > 1 && (
                <div className="hidden shrink-0 flex-col gap-3 lg:flex">
                  {galleryImages.map((url, index) => (
                    <button
                      key={`${url}-${index}`}
                      type="button"
                      onClick={() => setSelectedImage(index)}
                      className={`flex h-14 w-14 items-center justify-center overflow-hidden rounded-xl border bg-white p-1 transition ${
                        selectedImage === index
                          ? 'border-gray-900 ring-1 ring-gray-900'
                          : 'border-gray-200 hover:border-gray-400'
                      }`}
                    >
                      <img src={url} alt="" className="max-h-full max-w-full object-contain" />
                    </button>
                  ))}
                </div>
              )}

              <div className="mx-auto flex w-full min-w-0 max-w-[420px] flex-col gap-3 lg:mx-0">
                <div className="relative aspect-square w-full">
                  <WishlistButton itemCode={product.item_code} size={22} variant="detail" />
                  <Product3DViewer>
                    <ProductImage
                      src={mainImage}
                      alt={displayName || t.shared.product}
                      fit="contain"
                      className="h-full w-full p-4"
                    />
                  </Product3DViewer>
                </div>
                <p className="text-center text-[11px] font-medium text-slate-400 motion-reduce:hidden">
                  {t.product.viewIn3d}
                </p>

                {galleryImages.length > 1 && (
                  <div className="flex gap-2 overflow-x-auto pb-1 lg:hidden">
                    {galleryImages.map((url, index) => (
                      <button
                        key={`mobile-${url}-${index}`}
                        type="button"
                        onClick={() => setSelectedImage(index)}
                        className={`flex h-16 w-16 shrink-0 items-center justify-center overflow-hidden rounded-lg border bg-white p-1 ${
                          selectedImage === index
                            ? 'border-gray-900 ring-1 ring-gray-900'
                            : 'border-gray-200'
                        }`}
                      >
                        <img src={url} alt="" className="max-h-full max-w-full object-contain" />
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>

          {wrapAddons.length > 0 ? (
            <div className="hidden min-w-0 2xl:block">
              <GiftWrapOptions
                variant="plain"
                layout="fill"
                title={t.product.yourChoiceOf}
                options={wrapOptions}
                selectedCode={wrapSelectedCode}
                name="gift-wrap-desktop"
                onSelect={selectWrap}
              />
              {paidWrapLocked ? (
                <p className="mt-2 text-[13px] text-gray-500">{t.product.freeWrapOnlyNote}</p>
              ) : null}
            </div>
          ) : null}

          <div className="min-w-0 lg:pt-2">
            <h1 className="text-pretty text-[18px] font-bold leading-snug tracking-normal text-gray-900 sm:text-[20px]">
              {locale === 'ar' ? displayName : toTitleCase(displayName || `Item ${product.item_code}`)}
            </h1>

            <div className="mt-5 border-b border-gray-200 pb-5">
              {hasOffer ? (
                <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                  <p className="text-[26px] font-bold leading-none text-[#8B0000] sm:text-[28px]">
                    {formatMoney(displayPrice)}
                  </p>
                  <p className="text-[15px] text-gray-400 line-through">
                    {formatMoney(product.retail_price ?? 0)}
                  </p>
                  {product.discount_percent != null && (
                    <span className="rounded bg-red-50 px-2 py-0.5 text-[12px] font-semibold text-brand-cocoa">
                      {t.product.savePercent} {product.discount_percent}%
                    </span>
                  )}
                </div>
              ) : (
                <p className="text-[26px] font-bold leading-none text-[#8B0000] sm:text-[28px]">
                  {formatMoney(displayPrice)}
                </p>
              )}
            </div>

            <div className="mt-5 2xl:hidden">{wrapPanel}</div>

            <div className="mt-5">
              <AddToCartControl
                itemCode={product.item_code}
                unitPrice={displayPrice}
                variant="label"
                size="detail"
                max={maxQty}
                disabled={product.current_stock <= 0}
                addonItemCode={
                  selectedAddonCode && selectedAddonAllowed ? selectedAddonCode : undefined
                }
                addonUnitPrice={addonPrice}
              />
            </div>

            {product.current_stock <= 0 && (
              <p className="mt-3 text-[13px] text-brand-cocoa">{t.product.outOfStock}</p>
            )}
          </div>
        </div>

        <div className="mt-8 border-t border-gray-200 pt-6">
              <div className="flex gap-8 border-b border-gray-200">
                {(['description', 'specifications'] as DetailTab[]).map((tab) => (
                  <button
                    key={tab}
                    type="button"
                    onClick={() => setActiveTab(tab)}
                    className={`-mb-px border-b-2 pb-3 text-[15px] font-semibold capitalize transition ${
                      activeTab === tab
                        ? 'border-brand-cocoa text-brand-cocoa'
                        : 'border-transparent text-gray-400 hover:text-gray-600'
                    }`}
                  >
                    {tab === 'description' ? t.product.description : t.product.specifications}
                  </button>
                ))}
              </div>

              {activeTab === 'description' ? (
                <div className="pt-6">
                  {displayDescription ? (
                    <>
                      <h3 className="text-[15px] font-bold text-gray-900">{t.product.description}</h3>
                      <p className="mt-4 whitespace-pre-line text-[14px] leading-relaxed text-gray-600">
                        {locale === 'ar' ? displayDescription : toSentenceCase(displayDescription)}
                      </p>
                    </>
                  ) : (
                    <>
                      <h3 className="text-[15px] font-bold text-gray-900">{t.product.productSummary}</h3>
                      <ul className="mt-4 space-y-3">
                        {bullets.map((line) => (
                          <li key={line} className="flex gap-3 text-[14px] leading-relaxed text-gray-600">
                            <IconCheck size={16} className="mt-0.5 shrink-0 text-brand-cocoa" />
                            <span>{toSentenceCase(line)}</span>
                          </li>
                        ))}
                      </ul>
                    </>
                  )}
                </div>
              ) : structuredSpecs.length > 0 || featureBullets.length > 0 ? (
                <div className="pt-6">
                  {structuredSpecs.length > 0 && (
                    <dl className="grid gap-3 sm:grid-cols-2">
                      {structuredSpecs.map((spec, index) => (
                        <div
                          key={`${spec.label}-${index}`}
                          className="rounded-2xl bg-white px-4 py-3.5 shadow-[0_8px_24px_rgba(15,23,42,0.05)] ring-1 ring-slate-200/80"
                        >
                          <dt className="text-[12px] font-semibold tracking-normal text-slate-500">
                            {locale === 'ar' ? spec.label : toTitleCase(spec.label)}
                          </dt>
                          <dd className="mt-1 text-[15px] font-semibold tracking-normal text-slate-900">
                            {locale === 'ar' || /^\d+$/.test(spec.value) ? spec.value : toTitleCase(spec.value)}
                          </dd>
                        </div>
                      ))}
                    </dl>
                  )}

                  {featureBullets.length > 0 && (
                    <div className={structuredSpecs.length > 0 ? 'mt-6' : ''}>
                      <h3 className="text-[15px] font-bold text-gray-900">{t.product.highlights}</h3>
                      <ul className="mt-4 space-y-3">
                        {featureBullets.map((line, index) => (
                          <li
                            key={`highlight-${index}`}
                            className="flex gap-3 text-[14px] leading-relaxed text-gray-600"
                          >
                            <IconCheck size={16} className="mt-0.5 shrink-0 text-brand-cocoa" />
                            <span>{locale === 'ar' ? line : toSentenceCase(line)}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              ) : (
                <p className="mt-6 text-[14px] text-gray-500">{t.product.noSpecs}</p>
              )}
        </div>

        <SimilarProductsCarousel
          itemCode={product.item_code}
          categoryCode={product.category_code}
          viewAllHref={
            product.category_code
              ? `/products?category=${product.category_code}`
              : '/products'
          }
        />
        <SuggestedProductsCarousel
          itemCode={product.item_code}
          viewAllHref={
            product.brand_code ? `/products?brand=${product.brand_code}` : '/featured'
          }
        />

        {reviews.length > 0 && (
          <section className="mt-12 border-t border-gray-200 pt-10">
            <h2 className="text-lg font-bold text-gray-900">{t.product.customerReviews}</h2>
            <ul className="mt-5 space-y-4">
              {reviews.map((r) => (
                <li key={r.review_id} className="rounded-xl border border-gray-100 bg-gray-50 p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <div className="flex items-center gap-0.5" aria-label={`${r.rating} ${t.product.starsOutOf5}`}>
                      {Array.from({ length: 5 }, (_, i) => (
                        <IconStar
                          key={i}
                          size={16}
                          filled={i < r.rating}
                          className={i < r.rating ? 'text-amber-400' : 'text-gray-300'}
                        />
                      ))}
                    </div>
                    <p className="text-[14px] font-medium text-gray-900">{r.first_name}</p>
                  </div>
                  {r.review_text && (
                    <p className="mt-1 text-[14px] text-gray-600">{r.review_text}</p>
                  )}
                </li>
              ))}
            </ul>
          </section>
        )}

        {storage.hasSession() && (
          <form
            className="mt-8 rounded-xl border border-gray-200 bg-white p-5"
            onSubmit={(e) => {
              e.preventDefault()
              submitReview.mutate()
            }}
          >
            <h3 className="text-[15px] font-bold text-gray-900">{t.product.writeReview}</h3>
            <StarRatingInput value={reviewRating} onChange={setReviewRating} />
            <textarea
              value={reviewText}
              onChange={(e) => setReviewText(e.target.value)}
              placeholder={t.product.reviewPlaceholder}
              className="mt-3 w-full rounded-lg border border-gray-300 px-3 py-2 text-[13px]"
              rows={3}
            />
            <button
              type="submit"
              className="mt-3 rounded-lg bg-brand-cocoa px-5 py-2 text-[13px] font-semibold text-white hover:bg-brand-accent-hover"
            >
              {t.product.submitReview}
            </button>
          </form>
        )}
      </div>
    </div>
  )
}
