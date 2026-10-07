import { useLocale } from '../../i18n/LocaleContext'
import { useFormatMoney } from '../../i18n/useFormatMoney'
import type { GiftWrapOption } from '../../types/api'

const LABEL_KEYS = {
  none: 'noGiftWrap',
  free: 'wrapFree',
  'classic-boys': 'wrapClassicBoys',
  'classic-girls': 'wrapClassicGirls',
  'premium-boys': 'wrapPremiumBoys',
  'premium-girls': 'wrapPremiumGirls',
  newborn: 'wrapNewborn',
  birthday: 'wrapBirthday',
} as const

const LABEL_BY_NAME: Record<string, keyof typeof LABEL_KEYS> = {
  'no gift wrap': 'none',
  'free gift wrap': 'free',
  'classic gift wrap for boys': 'classic-boys',
  'classic gift wrap for girls': 'classic-girls',
  'premium gift wrap for boys': 'premium-boys',
  'premium gift wrap for girls': 'premium-girls',
  'newborn gift wrap': 'newborn',
  'birthday gift wrap': 'birthday',
}

const ROW_TONE: Record<string, string> = {
  none: 'bg-[#EAF4FF]',
  free: 'bg-[#E7FBF3]',
  'classic-boys': 'bg-[#EEF0FF]',
  'classic-girls': 'bg-[#FFE9F4]',
  'premium-boys': 'bg-[#E6F3FF]',
  'premium-girls': 'bg-[#FFF0F7]',
  newborn: 'bg-[#FFF3F6]',
  birthday: 'bg-[#EEF5FF]',
  other: 'bg-[#FFF8EE]',
}

interface Props {
  options: GiftWrapOption[]
  selectedCode: string
  currencyCode?: string
  disabled?: boolean
  variant?: 'card' | 'plain'
  layout?: 'list' | 'fill'
  title?: string
  name?: string
  onSelect: (code: string) => void
}

export function optionLabelKey(option: GiftWrapOption) {
  if (option.code in LABEL_KEYS) {
    return LABEL_KEYS[option.code as keyof typeof LABEL_KEYS]
  }
  const fromName = LABEL_BY_NAME[option.label.trim().toLowerCase()]
  return fromName ? LABEL_KEYS[fromName] : null
}

function wrapKind(option: GiftWrapOption): keyof typeof LABEL_KEYS | 'other' {
  if (option.code in LABEL_KEYS) return option.code as keyof typeof LABEL_KEYS
  return LABEL_BY_NAME[option.label.trim().toLowerCase()] ?? 'other'
}

function GiftBoxArt({ kind }: { kind: string }) {
  const look =
    kind === 'none'
      ? { box: '#FFF7ED', lid: '#FFE4E6', ribbon: '#E91E63', tag: '#F9A8D4' }
      : kind === 'free'
        ? { box: '#93C5FD', lid: '#60A5FA', ribbon: '#2563EB', tag: '#FFFFFF' }
        : kind === 'classic-boys'
          ? { box: '#3B82F6', lid: '#2563EB', ribbon: '#1D4ED8', tag: '#DBEAFE' }
          : kind === 'classic-girls'
            ? { box: '#F9A8D4', lid: '#F472B6', ribbon: '#E91E63', tag: '#FFFFFF' }
            : kind === 'premium-boys'
              ? { box: '#1D4ED8', lid: '#1E3A8A', ribbon: '#93C5FD', tag: '#DBEAFE' }
              : kind === 'premium-girls'
                ? { box: '#FCE7F3', lid: '#FBCFE8', ribbon: '#E91E63', tag: '#FFFFFF' }
                : kind === 'newborn'
                  ? { box: '#FFF7ED', lid: '#FED7AA', ribbon: '#F59E0B', tag: '#FFFFFF' }
                  : kind === 'birthday'
                    ? { box: '#FEF3C7', lid: '#FDE68A', ribbon: '#F59E0B', tag: '#FFFFFF' }
                    : { box: '#FDE68A', lid: '#FBBF24', ribbon: '#E91E63', tag: '#FFFFFF' }

  return (
    <svg viewBox="0 0 64 56" className="h-12 w-14 shrink-0" aria-hidden>
      <rect x="12" y="22" width="40" height="28" rx="4" fill={look.box} />
      <rect x="10" y="16" width="44" height="10" rx="3" fill={look.lid} />
      <rect x="29" y="16" width="6" height="34" fill={look.ribbon} />
      <path d="M32 16c-6-8-14-6-14 0 5-2 10 0 14 6 4-6 9-8 14-6 0-6-8-8-14 0z" fill={look.ribbon} />
      <rect x="38" y="26" width="12" height="8" rx="1.5" fill={look.tag} />
    </svg>
  )
}

export function GiftWrapOptions({
  options,
  selectedCode,
  currencyCode = 'QAR',
  disabled,
  variant = 'card',
  layout = 'list',
  title,
  name = 'gift-wrap',
  onSelect,
}: Props) {
  const { t } = useLocale()
  const formatMoney = useFormatMoney()
  const heading = title ?? t.shared.yourChoiceOf
  const fill = layout === 'fill'

  return (
    <section
      className={
        fill
          ? '@container/wrap h-full min-w-0'
          : variant === 'card'
            ? 'rounded-2xl bg-white p-5 shadow-sm'
            : 'mt-5 border-b border-gray-200 pb-5'
      }
    >
      {fill ? (
        <div className="mb-3 flex flex-col items-start gap-1 @min-[28rem]/wrap:flex-row @min-[28rem]/wrap:items-start @min-[28rem]/wrap:justify-between @min-[28rem]/wrap:gap-3">
          <h2 className="text-pretty font-display text-[1.35rem] font-extrabold leading-tight tracking-normal text-[#1E3A8A] @min-[28rem]/wrap:text-[1.65rem] @min-[28rem]/wrap:leading-none">
            {heading}
            <span className="ms-1 text-brand-accent" aria-hidden>
              *
            </span>
          </h2>
          <p className="max-w-none text-start text-[12px] font-medium leading-5 tracking-normal text-slate-500 @min-[28rem]/wrap:max-w-[14rem] @min-[28rem]/wrap:text-end">
            {t.product.wrapAreaSubtitle}
          </p>
        </div>
      ) : (
        <h2 className={variant === 'card' ? 'font-semibold' : 'text-[14px] font-semibold text-gray-900'}>
          {heading}
        </h2>
      )}
      <fieldset className={fill ? 'mt-1' : 'mt-3'} disabled={disabled}>
        <legend className="sr-only">{heading}</legend>
        <div className={fill ? 'grid grid-cols-1 gap-2 @min-[32rem]/wrap:grid-cols-2' : 'divide-y divide-slate-100'}>
          {options.map((option) => {
            const kind = wrapKind(option)
            const labelKey = optionLabelKey(option)
            const label = labelKey ? t.checkout[labelKey] : option.label
            const selected = selectedCode === option.code
            const optionDisabled = option.enabled === false
            return (
              <label
                key={option.code}
                className={
                  fill
                    ? `flex min-w-0 items-center gap-2.5 rounded-[1.35rem] px-3 py-2 ${ROW_TONE[kind] ?? ROW_TONE.other} ${
                        selected ? 'ring-2 ring-brand-accent' : 'ring-1 ring-transparent'
                      } ${optionDisabled ? 'cursor-not-allowed opacity-45' : 'cursor-pointer'}`
                    : `flex items-center justify-between gap-4 py-3 first:pt-0 last:pb-0 ${
                        optionDisabled ? 'cursor-not-allowed opacity-45' : 'cursor-pointer'
                      }`
                }
              >
                {fill ? <GiftBoxArt kind={kind} /> : null}
                <span className={`min-w-0 flex-1 break-words tracking-normal ${fill ? 'text-[13px] font-semibold leading-5 text-slate-800' : 'text-sm text-slate-800'}`}>
                  {label}
                  {kind === 'none' && fill ? (
                    <span className="mt-0.5 block text-[11px] font-medium text-slate-500">
                      {t.product.wrapNoneHint}
                    </span>
                  ) : option.fee > 0 ? (
                    <span className={`block ${fill ? 'mt-0.5 text-[12px] font-medium text-slate-600' : 'text-slate-700'}`}>
                      +{formatMoney(option.fee, currencyCode)}
                    </span>
                  ) : null}
                </span>
                <input
                  type="radio"
                  name={name}
                  value={option.code}
                  checked={selected}
                  disabled={optionDisabled}
                  onChange={() => {
                    if (!optionDisabled) onSelect(option.code)
                  }}
                  className="h-5 w-5 shrink-0 accent-[#E91E63] disabled:cursor-not-allowed"
                />
              </label>
            )
          })}
        </div>
      </fieldset>
    </section>
  )
}
