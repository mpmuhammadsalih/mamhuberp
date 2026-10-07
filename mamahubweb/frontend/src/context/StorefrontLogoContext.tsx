import { createContext, useContext, useEffect, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'

import { LOGO_FALLBACK_SRC } from '../lib/brandAssets'
import { resolveStorefrontLogoSrc } from '../lib/queries/logo'
import { preloadStorefrontImages } from '../lib/queries/preloadStorefrontImages'
import { storefrontQueries, type MediaItem } from '../lib/queries/storefront'

type StorefrontLogoContextValue = {
  logo?: MediaItem
  logoSrc: string
  alt: string
}

const StorefrontLogoContext = createContext<StorefrontLogoContextValue>({
  logoSrc: LOGO_FALLBACK_SRC,
  alt: "MamaHub — Mom's Love — حب الأم",
})

export function StorefrontLogoProvider({ children }: { children: ReactNode }) {
  const { data: home } = useQuery(storefrontQueries.home)
  const logo = home?.storefront_logo ?? undefined
  const logoSrc = resolveStorefrontLogoSrc(logo)

  useEffect(() => {
    preloadStorefrontImages(home)
  }, [home])

  return (
    <StorefrontLogoContext.Provider
      value={{
        logo,
        logoSrc,
        alt: logo?.alt_text?.trim() || "MamaHub — Mom's Love — حب الأم",
      }}
    >
      {children}
    </StorefrontLogoContext.Provider>
  )
}

export function useStorefrontLogo() {
  return useContext(StorefrontLogoContext)
}
