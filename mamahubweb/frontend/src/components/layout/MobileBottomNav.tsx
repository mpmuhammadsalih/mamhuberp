import { useQuery } from '@tanstack/react-query'
import { Link, useLocation } from 'react-router-dom'
import { IconCart, IconGrid, IconHeart, IconHome, IconUser } from '../icons/Icons'
import { fetchCart, getCartItemCount } from '../../lib/queries/cart'
import { getData } from '../../lib/api'
import { profileDisplayName } from '../../lib/profileName'
import { storage } from '../../lib/storage'
import { useLocale } from '../../i18n/LocaleContext'
import { getCollectionQuickLinks } from './collectionQuickLinks'
import type { UserProfile, WishlistItem } from '../../types/api'

interface Tab {
  label: string
  href: string
  icon: typeof IconHome
  match: (pathname: string) => boolean
  badge?: number
}

function isShopRoute(pathname: string) {
  return (
    pathname.startsWith('/products') ||
    pathname.startsWith('/new-arrivals') ||
    pathname.startsWith('/best-sellers') ||
    pathname.startsWith('/offers') ||
    pathname.startsWith('/featured') ||
    pathname.startsWith('/collections') ||
    pathname.startsWith('/gift-finder')
  )
}

function isAccountRoute(pathname: string) {
  return (
    pathname.startsWith('/profile') ||
    pathname.startsWith('/orders') ||
    pathname.startsWith('/addresses') ||
    pathname.startsWith('/loyalty') ||
    pathname.startsWith('/inbox') ||
    pathname === '/login'
  )
}

export function MobileBottomNav() {
  const location = useLocation()
  const loggedIn = storage.hasSession()
  const { t } = useLocale()
  const collectionQuickLinks = getCollectionQuickLinks(t)

  const { data: cart } = useQuery({
    queryKey: ['cart'],
    queryFn: ({ signal }) => fetchCart({ signal }),
    staleTime: 30_000,
  })

  const { data: wishlist } = useQuery({
    queryKey: ['wishlist'],
    queryFn: () => getData<{ items: WishlistItem[] }>('/wishlist'),
    enabled: loggedIn,
    staleTime: 30_000,
  })

  const { data: profile } = useQuery({
    queryKey: ['profile'],
    queryFn: () => getData<UserProfile>('/customer/auth/me'),
    enabled: loggedIn,
    staleTime: 60_000,
  })

  const cartCount = getCartItemCount(cart)
  const wishlistCount = wishlist?.items?.length ?? 0
  const profileName = profileDisplayName(profile)

  const tabs: Tab[] = [
    {
      label: t.nav.home,
      href: '/',
      icon: IconHome,
      match: (pathname) => pathname === '/',
    },
    {
      label: t.nav.shop,
      href: '/products',
      icon: IconGrid,
      match: isShopRoute,
    },
    {
      label: t.nav.cart,
      href: '/cart',
      icon: IconCart,
      match: (pathname) => pathname.startsWith('/cart'),
      badge: cartCount,
    },
    {
      label: t.nav.wishlist,
      href: '/wishlist',
      icon: IconHeart,
      match: (pathname) => pathname.startsWith('/wishlist'),
      badge: wishlistCount,
    },
    {
      label: loggedIn ? profileName || t.nav.account : t.nav.signIn,
      href: loggedIn ? '/profile' : '/login',
      icon: IconUser,
      match: isAccountRoute,
    },
  ]

  return (
    <nav
      className="mobile-bottom-nav fixed inset-x-0 bottom-0 z-50 border-t border-brand-border/90 bg-brand-cream shadow-[0_-4px_24px_rgba(92,74,58,0.08)] md:hidden"
      aria-label="Mobile app navigation"
    >
      <div className="scrollbar-hide flex gap-1.5 overflow-x-auto border-b border-brand-border/60 px-2 py-2">
        {collectionQuickLinks.map((item) => {
          const active = location.pathname === item.href
          return (
            <Link
              key={item.href}
              to={item.href}
              className={`shrink-0 rounded-full px-3 py-1.5 text-[11px] font-semibold transition active:scale-95 ${
                active
                  ? 'bg-brand-accent text-white'
                  : 'bg-brand-cream-alt text-brand-cocoa ring-1 ring-brand-border/80'
              }`}
              aria-current={active ? 'page' : undefined}
            >
              {item.label}
            </Link>
          )
        })}
      </div>

      <div className="mx-auto flex max-w-lg items-stretch justify-around px-1 pt-1.5">
        {tabs.map((tab) => {
          const active = tab.match(location.pathname)
          const Icon = tab.icon
          return (
            <Link
              key={tab.href}
              to={tab.href}
              className={`relative flex min-w-0 flex-1 flex-col items-center gap-0.5 rounded-xl px-1 py-1.5 transition active:scale-95 ${
                active ? 'text-brand-accent' : 'text-slate-500'
              }`}
              aria-current={active ? 'page' : undefined}
            >
              <span className="relative flex h-7 w-7 items-center justify-center">
                <Icon size={22} className={active ? 'text-brand-accent' : 'text-slate-500'} />
                {(tab.badge ?? 0) > 0 && (
                  <span className="absolute -right-1.5 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-brand-cocoa px-0.5 text-[9px] font-bold text-white">
                    {tab.badge! > 99 ? '99+' : tab.badge}
                  </span>
                )}
              </span>
              <span
                className={`max-w-full truncate text-[10px] font-semibold leading-none ${
                  active ? 'text-brand-accent' : 'text-slate-500'
                }`}
              >
                {tab.label}
              </span>
              {active && (
                <span className="absolute -bottom-0.5 h-0.5 w-5 rounded-full bg-brand-accent" aria-hidden />
              )}
            </Link>
          )
        })}
      </div>
    </nav>
  )
}
