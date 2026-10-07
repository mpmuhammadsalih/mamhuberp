import { Link } from 'react-router-dom'
import { useLocale } from '../../i18n/LocaleContext'
import { IconChevronLeft, IconChevronRight } from '../icons/Icons'

interface Props {
  viewAllHref: string
  onPrev: () => void
  onNext: () => void
  canPrev?: boolean
  canNext?: boolean
}

export function CarouselNavControls({
  viewAllHref,
  onPrev,
  onNext,
  canPrev = true,
  canNext = true,
}: Props) {
  const { t } = useLocale()

  return (
    <div className="flex items-center gap-3 sm:gap-4">
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onPrev}
          disabled={!canPrev}
          aria-label={t.shared.previous}
          className="flex h-9 w-9 items-center justify-center rounded-full border border-gray-300 bg-white transition enabled:text-gray-800 enabled:hover:border-gray-400 disabled:cursor-default disabled:text-gray-300"
        >
          <IconChevronLeft size={18} />
        </button>
        <button
          type="button"
          onClick={onNext}
          disabled={!canNext}
          aria-label={t.shared.next}
          className="flex h-9 w-9 items-center justify-center rounded-full border border-gray-300 bg-white transition enabled:text-gray-900 enabled:hover:border-gray-400 disabled:cursor-default disabled:text-gray-300"
        >
          <IconChevronRight size={18} />
        </button>
      </div>

      <span className="hidden h-5 w-px bg-gray-300 sm:block" aria-hidden />

      <Link
        to={viewAllHref}
        className="font-catalog hidden items-center gap-1.5 text-[13px] font-semibold uppercase tracking-wide text-brand-accent hover:underline sm:inline-flex"
      >
        {t.shared.viewAll}
        <span aria-hidden>→</span>
      </Link>
    </div>
  )
}
