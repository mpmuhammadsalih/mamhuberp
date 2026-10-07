import { useLocale } from '../../i18n/LocaleContext'
import { IconAward, IconShield, IconTruck } from '../icons/Icons'

const TRUST_ITEMS = [
  {
    icon: IconTruck,
    iconBg: 'bg-[#FFF3C4]',
    iconColor: 'text-[#F59E0B]',
    titleKey: 'trustFastDelivery' as const,
    subtitleKey: 'trustAcrossQatar' as const,
  },
  {
    icon: IconShield,
    iconBg: 'bg-[#EDE9FE]',
    iconColor: 'text-[#7C3AED]',
    titleKey: 'trustSecurePayment' as const,
    subtitleKey: 'trustSecureCheckout' as const,
  },
  {
    icon: IconAward,
    iconBg: 'bg-[#DCFCE7]',
    iconColor: 'text-[#16A34A]',
    titleKey: 'trustTopQuality' as const,
    subtitleKey: 'trustPremiumToys' as const,
  },
] as const

interface Props {
  variant?: 'sidebar' | 'full'
}

export function CartTrustBar({ variant = 'full' }: Props) {
  const { t } = useLocale()

  if (variant === 'sidebar') {
    return (
      <div className="rounded-3xl bg-white p-5 shadow-sm ring-1 ring-black/[0.04] sm:p-6">
        <div className="space-y-5">
          {TRUST_ITEMS.map((item) => {
            const Icon = item.icon
            return (
              <div key={item.titleKey} className="flex items-center gap-3">
                <span
                  className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-full ${item.iconBg} ${item.iconColor}`}
                >
                  <Icon size={20} />
                </span>
                <div>
                  <p className="font-display text-sm font-bold text-[#1A1C2E]">
                    {t.cart[item.titleKey]}
                  </p>
                  <p className="text-[12px] text-slate-500">{t.cart[item.subtitleKey]}</p>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    )
  }

  return (
    <div className="rounded-3xl bg-white px-4 py-6 shadow-sm ring-1 ring-black/[0.04] sm:px-6 lg:px-8">
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-3">
        {TRUST_ITEMS.map((item) => {
          const Icon = item.icon
          return (
            <div key={item.titleKey} className="flex items-center gap-3">
              <span
                className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-full ${item.iconBg} ${item.iconColor}`}
              >
                <Icon size={20} />
              </span>
              <div>
                <p className="font-display text-sm font-bold text-[#1A1C2E]">
                  {t.cart[item.titleKey]}
                </p>
                <p className="text-[12px] text-slate-500">{t.cart[item.subtitleKey]}</p>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
