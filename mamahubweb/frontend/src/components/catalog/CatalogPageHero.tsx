import { IconStar } from '../icons/Icons'
import { GiftFinderDecor } from '../gift-finder/GiftFinderDecor'

interface Props {
  title: string
  subtitle?: string
}

export function CatalogPageHero({ title, subtitle }: Props) {
  return (
    <div className="relative mb-6 overflow-hidden rounded-3xl bg-gradient-to-r from-brand-cream-alt via-brand-cream to-brand-tint px-5 py-6 sm:px-8 sm:py-7 lg:mb-8">
      <div className="relative z-10 flex items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-brand-accent text-white shadow-sm">
            <IconStar size={20} filled />
          </span>
          <div>
            <h1 className="font-display text-2xl font-bold capitalize text-brand-ink sm:text-3xl">
              {title}
            </h1>
            {subtitle && (
              <p className="mt-1 font-catalog text-sm text-brand-sage sm:text-[15px]">{subtitle}</p>
            )}
          </div>
        </div>
        <GiftFinderDecor />
      </div>
    </div>
  )
}
