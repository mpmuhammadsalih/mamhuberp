import { useState } from 'react'
import { getBrandFallbackStyle, getBrandLogo } from '../../lib/brandLogos'
import { resolveMediaUrl } from '../../lib/media'

interface Props {
  name?: string | null
  index: number
  logoUrl?: string | null
  className?: string
}

export function BrandLogo({ name, index, logoUrl, className = '' }: Props) {
  const safeName = name?.trim() || 'Brand'
  const config = getBrandLogo(safeName)
  const fallback = getBrandFallbackStyle(safeName, index)
  const [apiFailed, setApiFailed] = useState(false)
  const [staticFailed, setStaticFailed] = useState(false)

  const circleClass = `flex h-[72px] w-[72px] items-center justify-center overflow-hidden rounded-full p-3 sm:h-[76px] sm:w-[76px] sm:p-3.5 ${config?.circleBg ?? fallback.circleBg}`

  const resolvedApi = resolveMediaUrl(logoUrl)
  if (resolvedApi && !apiFailed) {
    return (
      <div className={circleClass}>
        <img
          src={resolvedApi}
          alt=""
          className={`h-full w-full object-contain ${className}`}
          loading="lazy"
          onError={() => setApiFailed(true)}
        />
      </div>
    )
  }

  if (config && !staticFailed) {
    return (
      <div className={circleClass}>
        <img
          src={config.logoSrc}
          alt=""
          className={`h-full w-full object-contain ${className}`}
          loading="lazy"
          onError={() => setStaticFailed(true)}
        />
      </div>
    )
  }

  return (
    <div className={circleClass}>
      <span className={`font-display text-lg font-extrabold tracking-tight sm:text-xl ${fallback.textClass}`}>
        {fallback.initials}
      </span>
    </div>
  )
}
