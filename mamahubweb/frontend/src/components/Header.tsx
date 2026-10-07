import { useQuery } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { CartMiniPopover } from './cart/CartMiniPopover'
import { HOME_CONTAINER } from './layout/homeLayout'
import { DeliveryLocationBar } from './delivery/DeliveryLocationBar'
import { HeaderMascot } from './layout/HeaderMascot'
import { HeaderTrustBar } from './layout/HeaderTrustBar'
import { Logo } from './Logo'
import { SearchBar } from './SearchBar'
import { IconCart, IconChat, IconHeart, IconMapPin, IconMenu, IconUser } from './icons/Icons'
import { CategoryMobileDrawer } from './catalog/CategoryMobileDrawer'
import { LanguageSwitcher } from './layout/LanguageSwitcher'
import { useInboxWidget } from '../context/InboxWidgetContext'
import { useDeliveryLocation } from '../context/DeliveryLocationContext'
import { useLocale } from '../i18n/LocaleContext'
import { getData } from '../lib/api'
import { profileDisplayName } from '../lib/profileName'
import { fetchCart, getCartItemCount } from '../lib/queries/cart'
import { storage } from '../lib/storage'
import type { InboxUnread, UserProfile, WishlistItem } from '../types/api'

interface WishlistData {
  items: WishlistItem[]
}

export function Header() {
  const location = useLocation()
  const loggedIn = storage.hasSession()
  const { t } = useLocale()
  const { toggleInbox } = useInboxWidget()
  void location
  const cartRef = useRef<HTMLDivElement>(null)
  const [cartOpen, setCartOpen] = useState(false)
  const [categoryMenuOpen, setCategoryMenuOpen] = useState(false)
  const closeCategoryMenu = useCallback(() => setCategoryMenuOpen(false), [])
  const { location: deliveryLocation, openPicker } = useDeliveryLocation()

  const { data: cart } = useQuery({
    queryKey: ['cart'],
    queryFn: ({ signal }) => fetchCart({ signal }),
    staleTime: 30_000,
  })

  const { data: wishlist } = useQuery({
    queryKey: ['wishlist'],
    queryFn: () => getData<WishlistData>('/wishlist'),
    enabled: loggedIn,
    staleTime: 30_000,
  })

  const { data: profile } = useQuery({
    queryKey: ['profile'],
    queryFn: () => getData<UserProfile>('/customer/auth/me'),
    enabled: loggedIn,
    staleTime: 60_000,
  })

  const { data: inboxUnread } = useQuery({
    queryKey: ['inbox-unread'],
    queryFn: () => getData<InboxUnread>('/inbox/unread-count'),
    enabled: loggedIn,
    refetchInterval: 20_000,
  })

  const itemCount = getCartItemCount(cart)
  const wishlistCount = wishlist?.items?.length ?? 0
  const inboxCount = inboxUnread?.total ?? 0
  const profileName = profileDisplayName(profile)

  useEffect(() => {
    if (!cartOpen) return undefined

    function onPointerDown(event: MouseEvent) {
      if (cartRef.current && !cartRef.current.contains(event.target as Node)) {
        setCartOpen(false)
      }
    }

    function onEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') setCartOpen(false)
    }

    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onEscape)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onEscape)
    }
  }, [cartOpen])

  return (
    <header className="relative z-[80] overflow-visible bg-white">
      <CategoryMobileDrawer open={categoryMenuOpen} onClose={closeCategoryMenu} />
      <HeaderTrustBar />

      <div className={`${HOME_CONTAINER} py-2.5 md:py-3.5`}>
        <div className="flex flex-wrap items-center gap-3 lg:flex-nowrap lg:gap-5">
          <div className="relative flex min-h-10 w-full items-center justify-center md:w-auto md:min-h-0 md:justify-start">
            <div className="absolute start-0 flex items-center gap-1.5 md:hidden">
              <button
                type="button"
                onClick={() => setCategoryMenuOpen(true)}
                className="flex h-10 w-10 items-center justify-center rounded-full text-slate-700 transition hover:bg-slate-50"
                aria-label={t.nav.openCategories}
              >
                <IconMenu size={22} />
              </button>
              <LanguageSwitcher />
            </div>
            <div className="flex flex-col items-center gap-0.5 md:items-start">
              <Logo compact />
              <p className="hidden text-[13px] font-extrabold tracking-normal text-slate-800 xl:block">
                {t.headerBar.taglinePlay} {t.headerBar.taglineLearn} {t.headerBar.taglineGrow}
                <span className="ms-0.5 text-brand-accent" aria-hidden>
                  ♥
                </span>
              </p>
            </div>
            <div className="absolute end-0 flex items-center gap-1 md:hidden">
              <button
                type="button"
                onClick={openPicker}
                className="relative flex h-10 w-10 items-center justify-center rounded-full text-slate-700 transition hover:bg-slate-50"
                aria-label={
                  deliveryLocation
                    ? t.delivery.minutesDelivery
                        .replace('{min}', String(deliveryLocation.etaMinMinutes || 60))
                        .replace('{max}', String(deliveryLocation.etaMaxMinutes || 75))
                    : t.delivery.minutesDelivery.replace('{min}', '60').replace('{max}', '75')
                }
              >
                <IconMapPin size={22} />
                {!deliveryLocation ? (
                  <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-brand-accent" aria-hidden />
                ) : null}
              </button>
              {loggedIn ? (
                <button
                  type="button"
                  onClick={() => toggleInbox()}
                  className="relative flex h-10 w-10 items-center justify-center rounded-full text-slate-700 transition hover:bg-slate-50"
                  aria-label={`${t.nav.messagesLabel}${inboxCount ? `, ${inboxCount}` : ''}`}
                >
                  <IconChat size={22} />
                  {inboxCount > 0 ? <CountBadge count={inboxCount} /> : null}
                </button>
              ) : null}
              <Link
                to={loggedIn ? '/profile' : '/login'}
                className="flex h-10 w-10 items-center justify-center rounded-full text-slate-700 transition hover:bg-slate-50"
                aria-label={loggedIn ? profileName || t.nav.account : t.nav.signIn}
              >
                <IconUser size={22} />
              </Link>
            </div>
          </div>

          <DeliveryLocationBar className="hidden max-w-[200px] shrink-0 md:flex lg:max-w-[240px]" />
          <SearchBar className="hidden min-w-0 flex-1 md:block" />

          <nav className="ms-auto hidden items-center gap-5 md:flex lg:gap-7" aria-label={t.nav.account}>
            <HeaderAction
              to={loggedIn ? '/profile' : '/login'}
              label={t.nav.account}
              ariaLabel={loggedIn ? profileName || t.nav.account : t.nav.signIn}
            >
              <IconUser size={22} />
            </HeaderAction>

            {loggedIn ? (
              <HeaderAction
                onClick={() => toggleInbox()}
                label={t.nav.messages}
                ariaLabel={`${t.nav.messagesLabel}${inboxCount ? `, ${inboxCount}` : ''}`}
                badge={inboxCount || undefined}
              >
                <IconChat size={22} />
              </HeaderAction>
            ) : null}

            <HeaderAction
              to="/wishlist"
              label={t.nav.wishlist}
              ariaLabel={`${t.nav.wishlistLabel}${wishlistCount ? `, ${wishlistCount} ${t.shared.items}` : ''}`}
              badge={wishlistCount}
            >
              <IconHeart size={22} />
            </HeaderAction>

            <div className="relative" ref={cartRef}>
              <button
                type="button"
                onClick={() => setCartOpen((open) => !open)}
                className="relative flex flex-col items-center gap-0.5 text-slate-800 transition hover:text-brand-accent"
                aria-label={`${t.nav.cartLabel}${itemCount ? `, ${itemCount} ${t.shared.items}` : ''}`}
                aria-expanded={cartOpen}
                aria-haspopup="dialog"
              >
                <span className="relative">
                  <IconCart size={24} />
                  <CountBadge count={itemCount} />
                </span>
                <span className="text-[12px] font-medium">{t.nav.cart}</span>
              </button>
              {cartOpen && <CartMiniPopover cart={cart} onClose={() => setCartOpen(false)} />}
            </div>
          </nav>
          <HeaderMascot className="hidden h-[5.5rem] w-[8.5rem] shrink-0 xl:block" />
        </div>

        <SearchBar className="mt-2 w-full md:hidden" />
      </div>
    </header>
  )
}

function HeaderAction({
  to,
  onClick,
  label,
  ariaLabel,
  badge,
  children,
}: {
  to?: string
  onClick?: () => void
  label: string
  ariaLabel: string
  badge?: number
  children: ReactNode
}) {
  const className =
    'relative flex flex-col items-center gap-0.5 text-slate-800 transition hover:text-brand-accent'
  const inner = (
    <>
      <span className="relative">
        {children}
        {badge != null ? <CountBadge count={badge} /> : null}
      </span>
      <span className="text-[12px] font-medium">{label}</span>
    </>
  )
  if (onClick) {
    return (
      <button type="button" onClick={onClick} className={className} aria-label={ariaLabel}>
        {inner}
      </button>
    )
  }
  return (
    <Link to={to || '/'} className={className} aria-label={ariaLabel}>
      {inner}
    </Link>
  )
}

function CountBadge({ count }: { count: number }) {
  return (
    <span className="absolute -end-2 -top-1.5 flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-brand-accent px-1 text-[10px] font-bold leading-none text-white">
      {count > 99 ? '99+' : count}
    </span>
  )
}
