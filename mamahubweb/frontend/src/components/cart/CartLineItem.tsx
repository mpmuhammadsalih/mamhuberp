import { ProductImage } from '../ProductImage'
import { QuantitySelector } from '../QuantitySelector'
import { CardWrapControl } from './CardWrapControl'
import { IconClose, IconPlus, IconTrash } from '../icons/Icons'
import { useLocale } from '../../i18n/LocaleContext'
import { productDisplayName } from '../../i18n/productName'
import { useFormatMoney } from '../../i18n/useFormatMoney'
import { cartLineCombinedTotal } from '../../lib/queries/cart'
import { toTitleCase } from '../../lib/textCase'
import type { CartLine } from '../../types/api'

interface Props {
  item: CartLine
  extras?: CartLine[]
  index?: number
  currency?: string
  onUpdateQty: (quantity: number) => void
  onRemove: () => void
  disabled?: boolean
}

function extraLabel(extra: CartLine, locale: string, fallback: string) {
  const rawName = extra.product
    ? productDisplayName(extra.product, locale)
    : fallback
  return locale === 'ar' ? rawName : toTitleCase(rawName)
}

export function CartLineItem({
  item,
  extras = [],
  index = 0,
  currency,
  onUpdateQty,
  onRemove,
  disabled,
}: Props) {
  const { locale, t } = useLocale()
  const formatMoney = useFormatMoney()
  const rawName = item.product
    ? productDisplayName(item.product, locale)
    : `${t.common.item} ${item.item_code}`
  const name = locale === 'ar' ? rawName : toTitleCase(rawName)
  const qty = Math.round(item.quantity)
  const combinedTotal = cartLineCombinedTotal(item, extras)

  return (
    <div
      className={`relative ${
        index % 2 === 1 ? 'bg-[#F5F5F7]' : 'bg-white'
      } px-3 py-3 sm:px-4 sm:py-4 lg:bg-transparent`}
    >
      <button
        type="button"
        disabled={disabled}
        onClick={onRemove}
        className="absolute right-2 top-2 z-10 p-0.5 text-gray-300 transition hover:text-gray-500 disabled:opacity-50 lg:hidden"
        aria-label={t.cart.removeItem}
      >
        <IconClose size={14} />
      </button>

      {/* Mobile */}
      <div className="flex gap-3 lg:hidden">
        <div className="flex h-[72px] w-[72px] shrink-0 items-center justify-center overflow-hidden rounded-md bg-[#F5F5F5]">
          <ProductImage
            src={item.product?.primary_image_url}
            alt=""
            className="h-full w-full object-contain p-1"
          />
        </div>

        <div className="flex min-w-0 flex-1 flex-col pr-4">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0 flex-1">
              <p className="line-clamp-2 text-[13px] font-semibold leading-snug text-[#334155]">
                {name}
              </p>
              {extras.map((extra) => (
                <p
                  key={extra.cart_item_id}
                  className="mt-1 text-[12px] leading-snug text-slate-500"
                >
                  {extraLabel(extra, locale, t.shared.giftWrap)}
                  {extra.unit_price > 0
                    ? `  +${formatMoney(extra.unit_price, currency)}`
                    : ''}
                </p>
              ))}
              <div className="mt-2 max-w-[12rem]">
                <CardWrapControl itemCode={item.item_code} compact />
              </div>
            </div>
            <p className="shrink-0 text-[14px] font-bold leading-tight text-[#1A1C2E]">
              {formatMoney(combinedTotal, currency)}
            </p>
          </div>

          <div className="mt-auto flex items-center justify-end gap-2.5 pt-3">
            <button
              type="button"
              disabled={disabled}
              onClick={() => {
                if (qty > 1) onUpdateQty(qty - 1)
                else onRemove()
              }}
              className="flex h-9 w-9 items-center justify-center rounded-full bg-[#ECECEC] text-[#94A3B8] transition hover:bg-[#E2E2E2] disabled:opacity-50"
              aria-label={t.cart.removeItem}
            >
              <IconTrash size={16} />
            </button>
            <span className="min-w-[1.25rem] select-none text-center text-[15px] font-semibold tabular-nums text-[#334155]">
              {qty}
            </span>
            <button
              type="button"
              disabled={disabled}
              onClick={() => onUpdateQty(qty + 1)}
              className="flex h-9 w-9 items-center justify-center rounded-full bg-brand-accent text-white shadow-sm transition hover:bg-brand-accent-hover disabled:opacity-50"
              aria-label="Increase quantity"
            >
              <IconPlus size={16} className="stroke-[2.5]" />
            </button>
          </div>
        </div>
      </div>

      {/* Desktop */}
      <div className="hidden grid-cols-[88px_minmax(0,1fr)_auto_auto] items-center gap-5 lg:grid lg:gap-6">
        <div className="flex h-[88px] w-[88px] shrink-0 items-center justify-center overflow-hidden rounded-2xl bg-[#F5F5F5]">
          <ProductImage
            src={item.product?.primary_image_url}
            alt=""
            className="h-full w-full object-contain p-1.5"
          />
        </div>

        <div className="min-w-0">
          <p className="font-display text-[17px] font-bold text-[#1A1C2E]">{name}</p>
          {extras.map((extra) => (
            <p
              key={extra.cart_item_id}
              className="mt-1 font-catalog text-sm text-slate-500"
            >
              {extraLabel(extra, locale, t.shared.giftWrap)}
              {extra.unit_price > 0 ? `  +${formatMoney(extra.unit_price, currency)}` : ''}
            </p>
          ))}
          <div className="mt-2 max-w-[13rem]">
            <CardWrapControl itemCode={item.item_code} />
          </div>
          <p className="mt-1 font-catalog text-sm font-semibold text-brand-accent">
            {formatMoney(item.unit_price, currency)} each
          </p>
        </div>

        <div
          className="relative z-10 justify-self-center"
          onClick={(e) => e.preventDefault()}
          onMouseDown={(e) => e.stopPropagation()}
        >
          <QuantitySelector
            variant="cart"
            value={qty}
            disabled={disabled}
            onChange={onUpdateQty}
          />
        </div>

        <div className="text-right">
          <p className="font-display text-xl font-bold text-[#1A1C2E]">
            {formatMoney(combinedTotal, currency)}
          </p>
          <button
            type="button"
            disabled={disabled}
            onClick={onRemove}
            className="mt-1.5 inline-flex items-center gap-1 font-catalog text-sm font-semibold text-brand-accent transition hover:text-brand-accent-hover disabled:opacity-50"
          >
            <IconTrash size={14} />
            {t.cart.removeItem}
          </button>
        </div>
      </div>
    </div>
  )
}
