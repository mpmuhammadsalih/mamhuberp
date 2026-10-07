import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { ProductImage } from '../ProductImage'
import { IconTrash } from '../icons/Icons'
import { useLocale } from '../../i18n/LocaleContext'
import { productDisplayName } from '../../i18n/productName'
import { deleteData } from '../../lib/api'
import { useFormatMoney } from '../../i18n/useFormatMoney'
import { storage } from '../../lib/storage'
import { toTitleCase } from '../../lib/textCase'
import { cartAddonsFor, cartProductItems, getCartItemCount } from '../../lib/queries/cart'
import type { CartData } from '../../types/api'

interface Props {
  cart?: CartData
  onClose: () => void
}

export function CartMiniPopover({ cart, onClose }: Props) {
  const { locale, t } = useLocale()
  const formatMoney = useFormatMoney()
  const queryClient = useQueryClient()
  const items = cart?.items ?? []
  const productItems = cartProductItems(items)
  const itemCount = getCartItemCount(cart)
  const currency = cart?.summary.currency_code

  const removeItem = useMutation({
    mutationFn: (id: number) => deleteData<CartData>(`/cart/items/${id}`),
    onSuccess: (data) => {
      if (data.guest_token) storage.setGuestCartToken(data.guest_token)
      queryClient.invalidateQueries({ queryKey: ['cart'] })
    },
  })

  return (
    <div className="absolute end-0 top-[calc(100%+0.5rem)] z-[60] w-[min(100vw-2rem,380px)] overflow-hidden rounded-xl border border-gray-200 bg-white shadow-xl">
      <div className="border-b border-gray-200 px-4 py-3.5">
        <div className="flex items-baseline gap-2">
          <h2 className="font-catalog text-base font-bold text-gray-900">{t.cart.title}</h2>
          <span className="font-catalog text-sm text-gray-500">
            {itemCount} {itemCount === 1 ? t.shared.item : t.shared.items}
          </span>
        </div>
      </div>

      {productItems.length === 0 ? (
        <div className="px-4 py-8 text-center">
          <p className="font-catalog text-sm text-gray-500">{t.cart.empty}</p>
          <Link
            to="/products"
            onClick={onClose}
            className="font-catalog mt-3 inline-block text-sm font-semibold text-brand-accent hover:underline"
          >
            {t.shared.continueShopping}
          </Link>
        </div>
      ) : (
        <>
          <ul className="max-h-[320px] overflow-y-auto px-4 py-2">
            {productItems.map((item) => {
              const rawName = item.product
                ? productDisplayName(item.product, locale)
                : `${t.common.item} ${item.item_code}`
              const name = locale === 'ar' ? rawName : toTitleCase(rawName)
              const extras = cartAddonsFor(items, item.item_code)
              const combined = extras.reduce((sum, extra) => sum + extra.line_total, item.line_total)

              return (
                <li
                  key={item.cart_item_id}
                  className="flex gap-3 border-b border-gray-100 py-3 last:border-b-0"
                >
                  <div className="flex h-14 w-14 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-gray-100 bg-white">
                    <ProductImage
                      src={item.product?.primary_image_url}
                      alt=""
                      className="h-full w-full"
                    />
                  </div>

                  <div className="min-w-0 flex-1">
                    <p className="font-catalog line-clamp-2 text-[13px] leading-snug text-gray-800">
                      {name}
                    </p>
                    {extras.map((extra) => {
                      const extraName = extra.product
                        ? productDisplayName(extra.product, locale)
                        : t.shared.giftWrap
                      return (
                        <p
                          key={extra.cart_item_id}
                          className="font-catalog mt-0.5 text-[11px] text-slate-500"
                        >
                          {locale === 'ar' ? extraName : toTitleCase(extraName)}
                          {extra.unit_price > 0
                            ? `  +${formatMoney(extra.unit_price, currency)}`
                            : ''}
                        </p>
                      )
                    })}
                    <p className="font-catalog mt-1 text-[13px] font-semibold text-gray-900">
                      {formatMoney(combined, currency)}
                    </p>
                    <p className="font-catalog text-[12px] text-gray-500">
                      {item.quantity} {t.shared.qty}
                    </p>
                  </div>

                  <button
                    type="button"
                    onClick={() => removeItem.mutate(item.cart_item_id)}
                    disabled={removeItem.isPending}
                    className="shrink-0 self-start p-1 text-brand-accent transition hover:text-brand-accent-hover"
                    aria-label={t.cart.removeItem}
                  >
                    <IconTrash size={18} />
                  </button>
                </li>
              )
            })}
          </ul>

          <div className="flex items-center justify-between border-t border-gray-200 px-4 py-3.5">
            <p className="font-catalog text-lg font-bold text-brand-accent">
              {formatMoney(cart?.summary.grand_total ?? 0, currency)}
            </p>
            <Link
              to="/cart"
              onClick={onClose}
              className="font-catalog rounded-full bg-brand-accent px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-brand-accent-hover"
            >
              {t.cart.goToCart}
            </Link>
          </div>
        </>
      )}
    </div>
  )
}
