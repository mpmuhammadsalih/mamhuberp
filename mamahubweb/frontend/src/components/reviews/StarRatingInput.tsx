import { useState } from 'react'
import { IconStar } from '../icons/Icons'

interface Props {
  value: number
  onChange: (rating: number) => void
  max?: number
  size?: number
  label?: string
}

export function StarRatingInput({ value, onChange, max = 5, size = 28, label = 'Rating' }: Props) {
  const [hover, setHover] = useState<number | null>(null)
  const active = hover ?? value

  return (
    <div className="mt-3">
      <p className="mb-1.5 text-[13px] font-medium text-gray-600">{label}</p>
      <div
        className="flex items-center gap-1"
        onMouseLeave={() => setHover(null)}
        role="radiogroup"
        aria-label={label}
      >
        {Array.from({ length: max }, (_, index) => {
          const star = index + 1
          const filled = star <= active
          return (
            <button
              key={star}
              type="button"
              role="radio"
              aria-checked={value === star}
              aria-label={`${star} star${star === 1 ? '' : 's'}`}
              onMouseEnter={() => setHover(star)}
              onFocus={() => setHover(star)}
              onBlur={() => setHover(null)}
              onClick={() => onChange(star)}
              className="rounded p-0.5 transition hover:scale-110 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-tint"
            >
              <IconStar
                size={size}
                filled={filled}
                className={filled ? 'text-amber-400' : 'text-gray-300'}
              />
            </button>
          )
        })}
        <span className="ml-2 text-[13px] font-semibold text-gray-700">
          {active} / {max}
        </span>
      </div>
    </div>
  )
}
