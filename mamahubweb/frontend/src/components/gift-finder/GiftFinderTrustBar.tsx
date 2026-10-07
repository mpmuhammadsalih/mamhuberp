import type { ReactNode } from 'react'
import { useLocale } from '../../i18n/LocaleContext'
import { IconAward, IconHeadset, IconShield, IconTruck } from '../icons/Icons'

export function GiftFinderTrustBar() {
  const { t } = useLocale()

  const trustItems = [
    {
      icon: IconShield,
      iconBg: 'bg-[#FEE2E2]',
      iconColor: 'text-[#EF4444]',
      title: t.giftFinder.trustSafe,
      subtitle: t.giftFinder.trustSafeSub,
    },
    {
      icon: IconTruck,
      iconBg: 'bg-[#EDE9FE]',
      iconColor: 'text-[#7C3AED]',
      title: t.giftFinder.trustFast,
      subtitle: t.giftFinder.trustFastSub,
    },
    {
      icon: IconAward,
      iconBg: 'bg-[#DCFCE7]',
      iconColor: 'text-[#16A34A]',
      title: t.giftFinder.trustQuality,
      subtitle: t.giftFinder.trustQualitySub,
    },
    {
      icon: IconHeadset,
      iconBg: 'bg-[#DBEAFE]',
      iconColor: 'text-[#2563EB]',
      title: t.giftFinder.trustHelp,
      subtitle: t.giftFinder.trustHelpSub,
    },
  ] as const

  return (
    <div className="mt-8 grid grid-cols-2 gap-4 border-t border-brand-border/70 pt-8 lg:grid-cols-4 lg:gap-0">
      {trustItems.map((item, index) => {
        const Icon = item.icon
        return (
          <div
            key={item.title}
            className={`flex items-center gap-3 ${index > 0 ? 'lg:border-l lg:border-brand-border/70 lg:pl-6' : ''} ${index === 2 ? 'lg:pl-8' : ''}`}
          >
            <span
              className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-full ${item.iconBg} ${item.iconColor}`}
            >
              <Icon size={20} />
            </span>
            <div>
              <p className="font-display text-sm font-bold text-[#1A1C2E]">{item.title}</p>
              <p className="text-[12px] text-slate-500">{item.subtitle}</p>
            </div>
          </div>
        )
      })}
    </div>
  )
}

interface FieldProps {
  icon: ReactNode
  iconBg: string
  label: string
  children: ReactNode
}

export function GiftFinderField({ icon, iconBg, label, children }: FieldProps) {
  return (
    <label className="block">
      <div className="mb-2 flex items-center gap-2.5">
        <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full ${iconBg}`}>
          {icon}
        </span>
        <span className="font-display text-sm font-bold text-[#1A1C2E]">{label}</span>
      </div>
      {children}
    </label>
  )
}

export const giftFinderSelectClass =
  'w-full appearance-none rounded-xl border border-gray-200 bg-white py-3 pl-4 pr-10 text-[14px] text-gray-800 outline-none focus:border-brand-orange focus:ring-2 focus:ring-brand-tint'

export const giftFinderInputClass =
  'w-full rounded-xl border border-gray-200 bg-white px-4 py-3 text-[14px] text-gray-800 outline-none placeholder:text-gray-400 focus:border-brand-orange focus:ring-2 focus:ring-brand-tint'
