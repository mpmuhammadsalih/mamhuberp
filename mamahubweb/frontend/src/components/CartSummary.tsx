import { Link } from 'react-router-dom'
import { useLocale } from '../i18n/LocaleContext'
import { useFormatMoney } from '../i18n/useFormatMoney'
import type { CartData, CheckoutPricing } from '../types/api'
import { IconArrowRight, IconGift, IconList, IconLock, IconShield } from './icons/Icons'

interface Props {
  cart?: CartData
  pricing?: Partial<CheckoutPricing>
  showCheckoutLink?: boolean
  sticky?: boolean
}

export function CartSummary({ cart, pricing, showCheckoutLink = true, sticky = true }: Props) {
  const { t } = useLocale()
  const formatMoney = useFormatMoney()
  if (!cart) return null
  const s = cart.summary
  const currency = pricing?.currency_code ?? s.currency_code
  const subtotal = pricing?.subtotal ?? s.subtotal
  const discount = pricing?.discount_total ?? s.discount_total
  const loyaltyDiscount = pricing?.loyalty_discount ?? 0
  const tax = pricing?.tax_total ?? s.tax_total
  const deliveryFee = pricing?.delivery_fee ?? 0
  const giftWrapFee = pricing?.gift_wrap_fee ?? 0
  const total = pricing?.grand_total ?? s.grand_total

  return (
    <div
      className={`relative overflow-hidden rounded-3xl bg-white p-6 shadow-sm ring-1 ring-brand-border/50 ${
        sticky ? 'lg:sticky lg:top-24' : ''
      }`}
    >
      <span
        className="pointer-events-none absolute -right-1 -top-1 flex h-16 w-16 items-center justify-center rounded-full bg-brand-cream-alt text-brand-accent/35"
        aria-hidden
      >
        <IconGift size={28} />
      </span>

      <div className="relative mb-5 flex items-center gap-2.5">
        <span className="flex h-9 w-9 items-center justify-center rounded-full bg-brand-tint text-brand-accent">
          <IconList size={18} />
        </span>
        <h3 className="font-display text-lg font-bold text-[#1A1C2E]">{t.cart.orderSummary}</h3>
      </div>

      <dl className="relative space-y-3 font-catalog text-sm">
        <div className="flex justify-between text-gray-700">
          <dt>{t.shared.subtotal}</dt>
          <dd className="font-semibold text-[#1A1C2E]">{formatMoney(subtotal, currency)}</dd>
        </div>
        {discount > 0 && (
          <div className="flex justify-between text-green-600">
            <dt>{t.shared.discount}</dt>
            <dd className="font-semibold">- {formatMoney(discount, currency)}</dd>
          </div>
        )}
        {loyaltyDiscount > 0 && (
          <div className="flex justify-between text-green-600">
            <dt>{t.checkout.loyaltyPoints}</dt>
            <dd className="font-semibold">- {formatMoney(loyaltyDiscount, currency)}</dd>
          </div>
        )}
        {deliveryFee > 0 && (
          <div className="flex justify-between text-gray-700">
            <dt>{t.shared.delivery}</dt>
            <dd className="font-semibold text-[#1A1C2E]">{formatMoney(deliveryFee, currency)}</dd>
          </div>
        )}
        {giftWrapFee > 0 && (
          <div className="flex justify-between text-gray-700">
            <dt>{pricing?.gift_wrap_label || t.shared.giftWrap}</dt>
            <dd className="font-semibold text-[#1A1C2E]">{formatMoney(giftWrapFee, currency)}</dd>
          </div>
        )}
        <div className="flex justify-between text-gray-700">
          <dt>{t.shared.tax}</dt>
          <dd className="font-semibold text-[#1A1C2E]">{formatMoney(tax, currency)}</dd>
        </div>
        <div className="flex items-end justify-between border-t border-dashed border-gray-200 pt-4">
          <dt className="font-display text-base font-bold text-[#1A1C2E]">{t.shared.total}</dt>
          <dd className="font-display text-2xl font-bold text-brand-accent">
            {formatMoney(total, currency)}
          </dd>
        </div>
      </dl>

      <div className="relative mt-5 flex items-center gap-2.5 rounded-2xl bg-[#ECFDF5] px-4 py-3 ring-1 ring-[#BBF7D0]/80">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#D1FAE5] text-[#059669]">
          <IconShield size={16} />
        </span>
        <p className="text-[13px] font-medium leading-snug text-[#059669]">
          {t.cart.secureCheckout}
        </p>
      </div>

      {showCheckoutLink && cart.items.some((item) => !item.parent_item_code && !item.is_addon) && (
        <Link
          to="/checkout"
          className="relative mt-5 flex w-full items-center justify-center gap-2 rounded-full bg-brand-accent px-6 py-3.5 text-sm font-bold text-white shadow-md transition hover:bg-brand-accent-hover"
        >
          <IconLock size={16} />
          {t.cart.proceedCheckout}
          <IconArrowRight size={16} />
        </Link>
      )}
    </div>
  )
}
