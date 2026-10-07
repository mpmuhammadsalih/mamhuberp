import { useLocale } from '../i18n/LocaleContext'
import { IconMinus, IconPlus } from './icons/Icons'

interface Props {
  value: number
  onChange: (value: number) => void
  min?: number
  max?: number
  disabled?: boolean
  className?: string
  variant?: 'default' | 'card' | 'cart' | 'bar' | 'bar-compact' | 'bar-showcase' | 'bar-detail'
}

export function QuantitySelector({
  value,
  onChange,
  min = 1,
  max,
  disabled,
  className = '',
  variant = 'default',
}: Props) {
  const { t } = useLocale()
  const qty = Math.round(value)
  const atMin = qty <= min
  const atMax = max != null && qty >= max

  const isCard = variant === 'card'
  const isCart = variant === 'cart'
  const isBar = variant === 'bar' || variant === 'bar-compact' || variant === 'bar-showcase' || variant === 'bar-detail'
  const isBarCompact = variant === 'bar-compact'
  const isBarShowcase = variant === 'bar-showcase'
  const isBarDetail = variant === 'bar-detail'

  return (
    <div
      className={`inline-flex items-center ${
        isBarCompact
          ? 'h-7 w-full justify-between rounded-full bg-brand-tint px-0.5'
          : isBarShowcase
            ? 'h-9 w-full justify-between rounded-full bg-brand-tint px-1'
            : isBarDetail
              ? 'h-11 w-full justify-between rounded-full bg-brand-tint px-1'
            : isBar
              ? 'h-10 w-full justify-between rounded-full bg-brand-tint px-1'
            : isCart
            ? 'min-w-[108px] rounded-xl border-0 bg-brand-cream-alt px-2 py-1'
            : isCard
              ? 'min-w-[108px] rounded-full border border-gray-200 bg-white px-1 py-0.5 shadow-sm'
              : 'rounded-lg border border-gray-200 bg-white px-0.5 shadow-sm'
      } ${className}`}
      role="group"
      aria-label={t.controls.quantity}
    >
      <button
        type="button"
        disabled={disabled || atMin}
        onClick={(e) => {
          e.preventDefault()
          e.stopPropagation()
          onChange(Math.max(min, qty - 1))
        }}
        className={`flex items-center justify-center text-brand-accent transition hover:bg-brand-tint/80 disabled:cursor-default disabled:opacity-35 ${
          isBarCompact ? 'h-6 w-6 rounded-full' : isBarShowcase ? 'h-7 w-7 rounded-full' : isBarDetail ? 'h-9 w-9 rounded-full' : isBar ? 'h-8 w-8 rounded-full' : isCard || isCart ? 'h-8 w-8 rounded-full' : 'h-9 w-9'
        }`}
        aria-label={t.controls.decreaseQty}
      >
        <IconMinus
          size={isBarCompact ? 14 : isBarShowcase ? 15 : isCard || isBar ? 16 : 18}
          className="stroke-[2.5]"
        />
      </button>

      <span
        className={`min-w-[1.5rem] select-none text-center font-catalog font-bold tabular-nums text-brand-accent ${
          isCard || isBar || isBarCompact || isBarShowcase
            ? isBarCompact
              ? 'text-xs'
              : 'text-sm'
            : 'text-[15px]'
        }`}
      >
        {qty}
      </span>

      <button
        type="button"
        disabled={disabled || atMax}
        onClick={(e) => {
          e.preventDefault()
          e.stopPropagation()
          onChange(max != null ? Math.min(max, qty + 1) : qty + 1)
        }}
        className={`flex items-center justify-center text-brand-accent transition hover:bg-brand-tint/80 disabled:cursor-default disabled:opacity-35 ${
          isBarCompact ? 'h-6 w-6 rounded-full' : isBarShowcase ? 'h-7 w-7 rounded-full' : isBarDetail ? 'h-9 w-9 rounded-full' : isBar ? 'h-8 w-8 rounded-full' : isCard || isCart ? 'h-8 w-8 rounded-full' : 'h-9 w-9'
        }`}
        aria-label={t.controls.increaseQty}
      >
        <IconPlus
          size={isBarCompact ? 14 : isBarShowcase ? 15 : isCard || isBar ? 16 : 18}
          className="stroke-[2.5]"
        />
      </button>
    </div>
  )
}
