import { useEffect, useState, type MouseEvent } from 'react'
import { createPortal } from 'react-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { GiftWrapOptions, optionLabelKey } from '../checkout/GiftWrapOptions'
import { IconGift } from '../icons/Icons'
import { useLocale } from '../../i18n/LocaleContext'
import { productDisplayName } from '../../i18n/productName'
import { postData } from '../../lib/api'
import { syncCartCache } from '../../lib/cartOptimistic'
import { cartAddonsFor, fetchCart } from '../../lib/queries/cart'
import { catalogQueries } from '../../lib/queries/catalog'
import type { CartData, GiftWrapOption, Product } from '../../types/api'

function addonPrice(addon: Product) {
  if (
    addon.offer_price != null &&
    addon.offer_price > 0 &&
    addon.offer_price < (addon.retail_price ?? 0)
  ) {
    return addon.offer_price
  }
  return addon.retail_price ?? 0
}

function wrapOptionsFromAddons(addons: Product[], locale: string): GiftWrapOption[] {
  return [
    { code: 'none', label: 'No gift wrap', fee: 0, enabled: true },
    ...addons.map((addon) => ({
      code: String(addon.item_code),
      label: productDisplayName(addon, locale) || addon.item_name || `Item ${addon.item_code}`,
      fee: addonPrice(addon),
      enabled: addon.addon_enabled !== false,
    })),
  ]
}

interface Props {
  itemCode: number
  compact?: boolean
}

export function CardWrapControl({ itemCode, compact }: Props) {
  const { locale, t } = useLocale()
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)

  const { data: cart } = useQuery({
    queryKey: ['cart'],
    queryFn: ({ signal }) => fetchCart({ signal }),
    staleTime: 60_000,
  })
  const { data: addons = [] } = useQuery({
    ...catalogQueries.giftWrapAddons,
    enabled: true,
  })

  const currentWrap = cartAddonsFor(cart?.items, itemCode)[0] ?? null
  const options = wrapOptionsFromAddons(addons, locale)
  const selectedCode = currentWrap ? String(currentWrap.item_code) : 'none'
  const selectedOption = options.find((option) => option.code === selectedCode)
  const selectedKey = selectedOption ? optionLabelKey(selectedOption) : null
  const selectedLabel = selectedKey
    ? t.checkout[selectedKey]
    : selectedOption?.label || t.product.wrap

  const syncAddon = useMutation({
    mutationFn: (addonItemCode: number | null) =>
      postData<CartData>('/cart/addon', {
        parent_item_code: itemCode,
        addon_item_code: addonItemCode,
      }),
    onSuccess: (nextCart) => {
      syncCartCache(queryClient, nextCart)
      setOpen(false)
    },
  })

  useEffect(() => {
    if (!open) return undefined
    function onEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('keydown', onEscape)
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onEscape)
      document.body.style.overflow = previous
    }
  }, [open])

  if (addons.length === 0) return null

  function stopCardNav(event: MouseEvent) {
    event.preventDefault()
    event.stopPropagation()
  }

  const sheet = open
    ? createPortal(
        <div className="fixed inset-0 z-[90] flex items-end justify-center bg-black/40 p-0 sm:items-center sm:p-4">
          <button
            type="button"
            className="absolute inset-0 cursor-default"
            aria-label={t.delivery.close}
            onClick={() => setOpen(false)}
          />
          <div
            role="dialog"
            aria-modal="true"
            aria-label={t.shared.yourChoiceOf}
            className="relative z-10 w-full max-w-md rounded-t-3xl bg-white px-5 pb-[max(1.25rem,env(safe-area-inset-bottom))] pt-4 shadow-xl sm:rounded-3xl sm:pb-5"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="mx-auto mb-3 h-1 w-10 rounded-full bg-slate-200 sm:hidden" aria-hidden />
            <GiftWrapOptions
              variant="plain"
              name={`gift-wrap-${itemCode}`}
              title={t.shared.yourChoiceOf}
              options={options}
              selectedCode={selectedCode}
              disabled={syncAddon.isPending}
              onSelect={(code) => {
                const next = code === 'none' ? null : Number(code)
                if (next != null && addons.find((addon) => addon.item_code === next)?.addon_enabled === false) {
                  return
                }
                syncAddon.mutate(next)
              }}
            />
          </div>
        </div>,
        document.body,
      )
    : null

  return (
    <div className="mt-1.5" onClick={stopCardNav} onMouseDown={(event) => event.stopPropagation()}>
      <button
        type="button"
        onClick={(event) => {
          stopCardNav(event)
          setOpen(true)
        }}
        className={`inline-flex w-full items-center justify-center gap-1 rounded-full border font-semibold transition hover:border-brand-accent hover:text-brand-accent ${
          currentWrap
            ? 'border-brand-accent/40 bg-brand-tint/70 text-brand-accent'
            : 'border-brand-border bg-white text-slate-600'
        } ${compact ? 'px-2 py-1 text-[10px]' : 'px-2.5 py-1.5 text-[11px] sm:text-xs'}`}
      >
        <IconGift size={compact ? 12 : 14} />
        <span className="truncate">{currentWrap ? selectedLabel : t.product.wrap}</span>
      </button>
      {sheet}
    </div>
  )
}
