import { useEffect } from 'react'

import { useStorefrontLogo } from '../context/StorefrontLogoContext'
import { applyStorefrontFavicon } from '../lib/favicon'

/** Keeps the browser tab icon in sync with the CMS storefront logo. */
export function StorefrontFavicon() {
  const { logoSrc } = useStorefrontLogo()

  useEffect(() => {
    applyStorefrontFavicon(logoSrc)
  }, [logoSrc])

  return null
}
