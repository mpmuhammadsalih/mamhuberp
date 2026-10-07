import { useState } from 'react'

import { useStorefrontLogo } from '../context/StorefrontLogoContext'
import { resolveMediaUrl } from '../lib/media'

interface ProductImageProps {
  src?: string | null
  alt?: string
  className?: string
  fit?: 'contain' | 'cover'
}

export function ProductImage({
  src,
  alt = 'Product',
  className = '',
  fit = 'contain',
}: ProductImageProps) {
  const [primaryFailed, setPrimaryFailed] = useState(false)
  const { logoSrc } = useStorefrontLogo()

  const trimmedSrc = resolveMediaUrl(src)
  const fitClass = fit === 'cover' ? 'object-cover' : 'object-contain'

  if (trimmedSrc && !primaryFailed) {
    return (
      <img
        src={trimmedSrc}
        alt={alt}
        className={`${fitClass} ${className}`}
        loading="lazy"
        onError={() => setPrimaryFailed(true)}
      />
    )
  }

  return (
    <img
      src={logoSrc}
      alt={alt}
      data-fallback="logo"
      className={`object-contain opacity-40 ${className}`}
      loading="lazy"
    />
  )
}
