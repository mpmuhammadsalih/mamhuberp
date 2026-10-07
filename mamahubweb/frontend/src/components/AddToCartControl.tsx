import { useLocale } from '../i18n/LocaleContext'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type MouseEvent } from 'react'
import { CardWrapControl } from './cart/CardWrapControl'
import { IconCart } from './icons/Icons'
import { QuantitySelector } from './QuantitySelector'
import { deleteData, getApiErrorMessage, patchData, postDataWithRetry } from '../lib/api'
import { fetchCart } from '../lib/queries/cart'
import { applyOptimisticAddToCart, syncCartCache } from '../lib/cartOptimistic'
import { normalizeCart } from '../lib/queries/cart'
import type { CartData } from '../types/api'

interface Props {
  itemCode: number
  unitPrice?: number
  className?: string
  variant?: 'default' | 'card' | 'bar' | 'label' | 'outline'
  size?: 'default' | 'compact' | 'showcase' | 'detail'
  addonItemCode?: number
  addonUnitPrice?: number
  max?: number
  disabled?: boolean
}

export function AddToCartControl({
  itemCode,
  unitPrice = 0,
  className = '',
  variant = 'default',
  size = 'default',
  addonItemCode,
  addonUnitPrice = 0,
  max,
  disabled = false,
}: Props) {
  const { t } = useLocale()
  const queryClient = useQueryClient()
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const { data: cart } = useQuery({
    queryKey: ['cart'],
    queryFn: ({ signal }) => fetchCart({ signal }),
    staleTime: 60_000,
  })

  const cartItem = cart?.items.find((item) => item.item_code === itemCode && !item.parent_item_code)

  const addItem = useMutation({
    mutationFn: () =>
      postDataWithRetry<CartData>('/cart/items', {
        item_code: itemCode,
        quantity: 1,
        ...(addonItemCode ? { addon_item_code: addonItemCode } : {}),
      }),
    onMutate: async () => {
      setErrorMessage(null)
      await queryClient.cancelQueries({ queryKey: ['cart'] })
      const result = applyOptimisticAddToCart(queryClient, itemCode, 1, unitPrice)
      if (addonItemCode) {
        applyOptimisticAddToCart(queryClient, addonItemCode, 1, addonUnitPrice, itemCode)
      }
      return result
    },
    onSuccess: (data) => {
      syncCartCache(queryClient, data)
    },
    onError: (error, _vars, context) => {
      if (context?.previous) queryClient.setQueryData(['cart'], context.previous)
      setErrorMessage(getApiErrorMessage(error))
    },
  })

  const updateQty = useMutation({
    mutationFn: (quantity: number) =>
      patchData<CartData>(`/cart/items/${cartItem!.cart_item_id}`, { quantity }),
    onMutate: async (quantity) => {
      await queryClient.cancelQueries({ queryKey: ['cart'] })
      const previous = queryClient.getQueryData<CartData>(['cart'])
      if (previous) {
        const items = previous.items.map((item) =>
          item.item_code === itemCode || item.parent_item_code === itemCode
            ? { ...item, quantity, line_total: item.unit_price * quantity }
            : item,
        )
        const subtotal = items.reduce((sum, item) => sum + item.line_total, 0)
        queryClient.setQueryData<CartData>(['cart'], normalizeCart({
          ...previous,
          items,
          summary: {
            ...previous.summary,
            subtotal,
            grand_total: subtotal - previous.summary.discount_total + previous.summary.tax_total,
          },
        }))
      }
      return { previous }
    },
    onError: (_err, _qty, context) => {
      if (context?.previous) queryClient.setQueryData(['cart'], context.previous)
    },
    onSuccess: (data) => {
      syncCartCache(queryClient, data)
    },
  })

  const removeItem = useMutation({
    mutationFn: () => deleteData<CartData>(`/cart/items/${cartItem!.cart_item_id}`),
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: ['cart'] })
      const previous = queryClient.getQueryData<CartData>(['cart'])
      if (previous) {
        const items = previous.items.filter(
          (item) => item.item_code !== itemCode && item.parent_item_code !== itemCode,
        )
        const subtotal = items.reduce((sum, item) => sum + item.line_total, 0)
        queryClient.setQueryData<CartData>(['cart'], {
          ...previous,
          items,
          summary: {
            ...previous.summary,
            subtotal,
            grand_total: subtotal - previous.summary.discount_total + previous.summary.tax_total,
            item_count: items.reduce((sum, item) => sum + item.quantity, 0),
          },
        })
      }
      return { previous }
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) queryClient.setQueryData(['cart'], context.previous)
    },
    onSuccess: (data) => {
      syncCartCache(queryClient, data)
    },
  })

  const busy = updateQty.isPending || removeItem.isPending

  const stopNav = (e: MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
  }

  const iconButtonSize =
    size === 'compact' ? 'h-7 w-7' : size === 'showcase' ? 'h-8 w-8' : 'h-9 w-9'
  const iconSize = size === 'compact' ? 14 : size === 'showcase' ? 16 : 18
  const addIconButtonClass = `relative z-20 flex ${iconButtonSize} shrink-0 items-center justify-center rounded-full bg-brand-accent text-white shadow-md transition hover:bg-brand-accent-hover active:scale-95`
  const cannotAdd = disabled || addItem.isPending

  if (variant === 'outline' && !cartItem) {
    const outlineClass =
      size === 'compact'
        ? 'h-9 text-[13px]'
        : size === 'showcase'
          ? 'h-10 text-[14px]'
          : 'h-11 text-[15px]'
    return (
      <div className={`relative w-full text-center ${className}`}>
        <button
          type="button"
          className={`inline-flex w-full items-center justify-center rounded-full border-2 border-brand-accent bg-white font-display font-semibold tracking-normal text-slate-900 transition hover:bg-brand-tint disabled:opacity-60 ${outlineClass}`}
          disabled={cannotAdd}
          onClick={(e) => {
            stopNav(e)
            if (!cannotAdd) addItem.mutate()
          }}
        >
          {t.product.add}
        </button>
        {errorMessage ? (
          <p className="mt-1 text-[10px] font-medium tracking-normal text-red-600" role="status">
            {errorMessage}
          </p>
        ) : null}
      </div>
    )
  }

  if (variant === 'label' && !cartItem) {
    const labelClass =
      size === 'compact'
        ? 'gap-1 px-2 py-1.5 text-[11px]'
        : size === 'showcase'
          ? 'gap-1.5 px-2.5 py-2 text-[13px]'
          : size === 'detail'
            ? 'h-11 gap-2 px-5 text-sm'
            : 'gap-2 px-3 py-2.5 text-sm'
    const labelIcon = size === 'compact' ? 13 : size === 'detail' ? 18 : 16
    return (
      <div className={`relative ${className}`}>
        <button
          type="button"
          className={`inline-flex w-full items-center justify-center rounded-full bg-brand-accent font-bold text-white shadow-sm transition hover:bg-brand-accent-hover disabled:opacity-60 ${labelClass}`}
          disabled={cannotAdd}
          onClick={(e) => {
            stopNav(e)
            if (!cannotAdd) addItem.mutate()
          }}
        >
          <IconCart size={labelIcon} />
          {t.product.add}
        </button>
        {errorMessage ? (
          <p className="mt-1 text-center text-[10px] font-medium text-red-600" role="status">
            {errorMessage}
          </p>
        ) : null}
      </div>
    )
  }

  if (cartItem) {
    return (
      <div
        className={`relative z-20 ${className}`}
        onClick={stopNav}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <QuantitySelector
          variant={
            variant === 'bar' || variant === 'label' || variant === 'outline'
              ? size === 'compact'
                ? 'bar-compact'
                : size === 'showcase'
                  ? 'bar-showcase'
                  : size === 'detail'
                    ? 'bar-detail'
                    : 'bar'
              : variant === 'card'
                ? 'card'
                : 'default'
          }
          className={
            variant === 'outline'
              ? 'w-full'
              : variant === 'bar' || variant === 'label'
                ? 'w-full min-w-[88px]'
                : ''
          }
          min={0}
          max={max}
          value={Math.round(cartItem.quantity)}
          disabled={busy}
          onChange={(quantity) => {
            if (quantity === cartItem.quantity) return
            if (quantity <= 0) {
              removeItem.mutate()
              return
            }
            updateQty.mutate(quantity)
          }}
        />
        {size !== 'detail' ? (
          <CardWrapControl itemCode={itemCode} compact={size === 'compact'} />
        ) : null}
      </div>
    )
  }

  if (variant === 'bar') {
    return (
      <>
        <button
          type="button"
          className={`${addIconButtonClass} ${className}`}
          disabled={cannotAdd}
          onClick={(e) => {
            stopNav(e)
            if (!cannotAdd) addItem.mutate()
          }}
          title={errorMessage ?? t.product.addToCart}
          aria-label={t.product.addToCart}
        >
          <IconCart size={iconSize} />
        </button>
        {errorMessage && (
          <p className="mt-1 max-w-[140px] text-center text-[10px] font-medium leading-tight text-red-600" role="status">
            {errorMessage}
          </p>
        )}
      </>
    )
  }

  return (
    <div className="relative">
      <button
        type="button"
        className={`${addIconButtonClass} ${className}`}
        disabled={cannotAdd}
        onClick={(e) => {
          stopNav(e)
          if (!cannotAdd) addItem.mutate()
        }}
        aria-label={t.product.addToCart}
        title={errorMessage ?? t.product.addToCart}
      >
        <IconCart size={iconSize} />
      </button>
      {errorMessage && (
        <p className="absolute left-1/2 top-full z-30 mt-1 w-max max-w-[140px] -translate-x-1/2 rounded bg-red-600 px-2 py-0.5 text-center text-[10px] font-medium leading-tight text-white shadow" role="status">
          {errorMessage}
        </p>
      )}
    </div>
  )
}
