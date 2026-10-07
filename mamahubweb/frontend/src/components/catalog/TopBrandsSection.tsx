import type { Brand } from '../../lib/queries/catalog'
import { brandDisplayName } from '../../i18n/brandName'
import { useLocale } from '../../i18n/LocaleContext'
import { HOME_CONTAINER } from '../layout/homeLayout'
import { IconStar } from '../icons/Icons'
import { BrandCard } from './BrandCard'
import { TopBrandsDecorLeft, TopBrandsDecorRight, TopBrandsWave } from './TopBrandsDecor'

interface Props {
  brands: Brand[]
  isLoading?: boolean
}

function SectionIcon() {
  return (
    <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-brand-accent shadow-sm">
      <IconStar size={18} className="text-white" filled />
    </span>
  )
}

export function TopBrandsSection({ brands, isLoading = false }: Props) {
  const { locale, t } = useLocale()

  if (!isLoading && brands.length === 0) return null

  const visible = brands.filter((b) => b?.code != null).slice(0, 12)

  return (
    <section className="relative overflow-hidden bg-gradient-to-b from-brand-cream-alt via-brand-cream to-brand-cream-alt pb-20 pt-10 lg:pb-24 lg:pt-12">
      <TopBrandsDecorLeft />
      <TopBrandsDecorRight />
      <TopBrandsWave />

      <div className={`${HOME_CONTAINER} relative z-10`}>
        <div className="mb-8 max-w-xl lg:mb-10">
          <div className="flex items-start gap-3">
            <SectionIcon />
            <div>
              <h2 className="font-display text-2xl font-bold text-brand-ink sm:text-[1.65rem]">
                {t.catalog.topBrands}
              </h2>
              <p className="mt-1 font-catalog text-sm text-slate-500 sm:text-[15px]">
                {t.catalog.topBrandsSubtitle}
              </p>
            </div>
          </div>
        </div>

        {isLoading && visible.length === 0 ? (
          <div className="grid grid-cols-4 gap-2.5 sm:grid-cols-6 sm:gap-3 md:gap-4">
            {Array.from({ length: 12 }).map((_, index) => (
              <div
                key={index}
                className="aspect-square animate-pulse rounded-2xl bg-brand-tint/70 ring-1 ring-brand-border"
              />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-4 gap-2.5 sm:grid-cols-6 sm:gap-3 md:gap-4">
            {visible.map((brand, index) => (
              <BrandCard
                key={`brand-${brand.code}-${index}`}
                code={brand.code}
                name={brandDisplayName(brand, locale) || t.catalog.brandFallback}
                index={index}
                logoUrl={brand.logo_url}
              />
            ))}
          </div>
        )}
      </div>
    </section>
  )
}
