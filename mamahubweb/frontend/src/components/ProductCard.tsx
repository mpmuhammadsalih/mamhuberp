import { useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { ProductImage } from './ProductImage'
import { AddToCartControl } from './AddToCartControl'
import { WishlistButton } from './WishlistButton'
import { useFormatMoney } from '../i18n/useFormatMoney'
import { productDisplayName } from '../i18n/productName'
import { useLocale } from '../i18n/LocaleContext'
import { toTitleCase } from '../lib/textCase'
import { getData } from '../lib/api'
import type { Product } from '../types/api'

interface Props {
  product: Product
  badge?: string
  variant?: 'grid' | 'carousel' | 'compact' | 'showcase'
  showWishlist?: boolean
}

function resolveDiscountBadge(
  product: Product,
  badge: string | undefined,
  hasOffer: boolean,
): string | undefined {
  if (badge) return badge
  if (product.discount_percent && product.discount_percent > 0) {
    return `-${Math.round(product.discount_percent)}%`
  }
  if (hasOffer && product.retail_price && product.offer_price) {
    const pct = Math.round((1 - product.offer_price / product.retail_price) * 100)
    if (pct > 0) return `-${pct}%`
  }
  return undefined
}

function prefetchProduct(
  queryClient: ReturnType<typeof useQueryClient>,
  itemCode: number,
) {
  void queryClient.prefetchQuery({
    queryKey: ['product', itemCode],
    queryFn: ({ signal }) => getData(`/products/${itemCode}`, undefined, { signal }),
    staleTime: 60_000,
  })
}

export function ProductCard({
  product,
  badge,
  variant = 'grid',
  showWishlist = true,
}: Props) {
  const queryClient = useQueryClient()
  const { locale, t } = useLocale()
  const formatMoney = useFormatMoney()
  const isCompact = variant === 'compact'
  const isShowcase = variant === 'showcase'
  const hasOffer =
    product.offer_price != null &&
    product.offer_price > 0 &&
    product.offer_price < (product.retail_price ?? 0)

  const discountBadge = resolveDiscountBadge(product, badge, hasOffer)
  const productHref = `/products/${product.item_code}`
  const rawName = productDisplayName(product, locale)
  const productName = locale === 'ar' ? rawName : toTitleCase(rawName || `${t.common.item} ${product.item_code}`)
  const unitPrice = hasOffer ? product.offer_price! : product.retail_price ?? 0
  const addSize = isCompact ? 'compact' : isShowcase ? 'showcase' : 'default'

  const widthClass =
    variant === 'carousel'
      ? 'w-[176px] shrink-0 sm:w-[196px] lg:w-[214px]'
      : 'h-full min-w-[168px] sm:min-w-0'

  return (
    <article
      className={`@container/card font-display group flex flex-col overflow-hidden rounded-[32px] bg-white p-1.5 shadow-[0_10px_28px_rgba(15,23,42,0.07)] ring-1 ring-slate-200/80 transition hover:shadow-[0_14px_32px_rgba(15,23,42,0.1)] [perspective:40rem] ${widthClass}`}
      onMouseEnter={() => prefetchProduct(queryClient, product.item_code)}
    >
      <div
        className={`relative w-full shrink-0 overflow-hidden rounded-[22px] bg-[#f3f4f6] [transform:rotateX(0deg)_rotateY(0deg)] scale-100 transition duration-300 motion-safe:group-hover:scale-[1.03] motion-safe:group-hover:[transform:rotateX(7deg)_rotateY(-9deg)] ${
          isCompact ? 'aspect-[5/4]' : isShowcase ? 'aspect-[4/3]' : 'aspect-square'
        }`}
      >
        {discountBadge ? (
          <span
            className={`absolute z-10 rounded-full bg-brand-orange font-bold tracking-normal text-white shadow-sm ${
              isCompact
                ? 'start-1.5 top-1.5 px-1.5 py-px text-[8px]'
                : 'start-3 top-3 px-2.5 py-0.5 text-[10px]'
            }`}
          >
            {discountBadge}
          </span>
        ) : null}
        {showWishlist ? (
          <WishlistButton
            itemCode={product.item_code}
            variant="card"
            size={isCompact ? 12 : 16}
            className={isCompact ? 'end-1.5 top-1.5 !h-6 !w-6 shadow-none' : 'end-3 top-3'}
          />
        ) : null}
        <Link to={productHref} className="absolute inset-0">
          <ProductImage
            src={product.primary_image_url}
            alt={productName}
            fit="cover"
            className="h-full w-full"
          />
        </Link>
      </div>

      <div className={`flex min-h-0 flex-1 flex-col text-start ${isCompact ? 'pt-1.5' : 'pt-2'}`}>
        <div className={`shrink-0 ${isCompact ? 'px-1' : 'px-1.5'}`}>
          {hasOffer ? (
            <>
              <p
                className={`font-bold tracking-normal text-brand-accent ${
                  isCompact ? 'text-[13px]' : isShowcase ? 'text-[15px]' : 'text-[17px] @min-[200px]/card:text-lg'
                }`}
              >
                {formatMoney(product.offer_price!)}
              </p>
              <p
                className={`mt-0.5 tracking-normal text-slate-400 line-through ${
                  isCompact ? 'text-[10px]' : 'text-[13px]'
                }`}
              >
                {formatMoney(product.retail_price ?? 0)}
              </p>
            </>
          ) : (
            <p
              className={`font-bold tracking-normal text-brand-accent ${
                isCompact ? 'text-[13px]' : isShowcase ? 'text-[15px]' : 'text-[17px] @min-[200px]/card:text-lg'
              }`}
            >
              {formatMoney(product.retail_price ?? 0)}
            </p>
          )}
        </div>

        <Link to={productHref} className={`mt-2 block min-h-0 ${isCompact ? 'px-1' : 'px-1.5'}`}>
          <h3
            className={`line-clamp-2 font-medium tracking-normal text-slate-800 group-hover:text-brand-ink ${
              isCompact
                ? 'min-h-8 text-[11px] leading-4'
                : isShowcase
                  ? 'min-h-9 text-[13px] leading-5'
                  : 'min-h-10 text-[14px] leading-5'
            }`}
          >
            {productName}
          </h3>
        </Link>

        <div className={`mt-auto w-full ${isCompact ? 'pt-3' : 'pt-5'}`}>
          <AddToCartControl
            itemCode={product.item_code}
            unitPrice={unitPrice}
            variant="outline"
            size={addSize}
          />
        </div>
      </div>
    </article>
  )
}
