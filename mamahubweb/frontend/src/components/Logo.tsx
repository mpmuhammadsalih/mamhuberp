import { Link } from 'react-router-dom'

import { useStorefrontLogo } from '../context/StorefrontLogoContext'

export function Logo({ compact = false }: { compact?: boolean }) {
  const { logoSrc, alt } = useStorefrontLogo()

  return (
    <Link to="/" className="group flex shrink-0 items-center justify-center md:justify-start">
      <img
        src={logoSrc}
        alt={alt}
        className={`object-contain object-center transition group-hover:opacity-90 md:object-left ${
          compact
            ? 'h-14 w-auto max-w-[200px] sm:h-16 sm:max-w-[260px] lg:h-[4.5rem] lg:max-w-[320px]'
            : 'h-16 w-auto max-w-[240px] sm:h-20 sm:max-w-[300px] lg:h-24 lg:max-w-[360px]'
        }`}
        decoding="async"
        loading="eager"
        fetchPriority="high"
      />
    </Link>
  )
}
