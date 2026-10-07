import { Link } from 'react-router-dom'
import { IconChevronRight } from '../icons/Icons'
import { BrandLogo } from './BrandLogo'

interface Props {
  code: number
  name: string
  index: number
  logoUrl?: string | null
}

export function BrandCard({ code, name, index, logoUrl }: Props) {
  return (
    <Link
      to={`/products?brand=${code}`}
      className="group flex w-full min-w-0 flex-col items-center rounded-2xl bg-white px-2 pb-3 pt-4 shadow-sm ring-1 ring-black/[0.04] transition hover:-translate-y-0.5 hover:shadow-md sm:px-3 sm:pb-4 sm:pt-5"
    >
      <BrandLogo name={name} index={index} logoUrl={logoUrl} />

      <p className="mt-2 line-clamp-2 min-h-[2.25rem] text-center font-display text-xs font-bold leading-tight text-[#1A1C2E] sm:mt-3 sm:min-h-[2.5rem] sm:text-sm">
        {name}
      </p>

      <span className="mt-2 flex h-7 w-7 items-center justify-center rounded-full bg-[#FFD1DC] text-brand-accent transition group-hover:bg-brand-accent group-hover:text-white sm:mt-3 sm:h-8 sm:w-8">
        <IconChevronRight size={16} />
      </span>
    </Link>
  )
}
