import { useQuery } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { HOME_CONTAINER } from '../layout/homeLayout'
import { getCategoryNavQuickLinks } from '../layout/categoryNavLinks'
import { HeaderNavMenu } from '../layout/HeaderNavMenu'
import {
  IconChevronRight,
  IconGift,
  IconGraduation,
  IconHome,
  IconPercent,
  IconStar,
  IconTag,
  IconBabyFace,
  IconTree,
  IconWhatsApp,
} from '../icons/Icons'
import { useLocale } from '../../i18n/LocaleContext'
import { ageGroupDisplayName } from '../../i18n/ageGroupName'
import { brandDisplayName } from '../../i18n/brandName'
import { catalogQueries } from '../../lib/queries/catalog'
import { buildWhatsAppUrl, getWhatsAppNumber } from '../../lib/whatsapp'
import { CategoryMegaMenu } from './CategoryMegaMenu'

function isNavLinkActive(href: string, pathname: string, search: string): boolean {
  const [path, query = ''] = href.split('?')
  if (pathname !== path) return false

  const current = new URLSearchParams(search)
  if (!query) {
    if (path !== '/products') return !search
    const filterKeys = ['q', 'main', 'dept', 'category', 'age', 'brand', 'interest', 'min_price', 'max_price']
    return !filterKeys.some((key) => current.has(key))
  }

  const target = new URLSearchParams(query)
  for (const [key, value] of target.entries()) {
    if (current.get(key)?.toLowerCase() !== value.toLowerCase()) return false
  }
  return true
}

function navItemClass(active: boolean) {
  return `flex min-w-[3.5rem] flex-col items-center gap-1 rounded-2xl px-2 py-1.5 text-[12px] font-medium transition lg:min-w-[4.25rem] lg:px-3 lg:text-[13px] ${
    active ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-700 hover:bg-white/70 hover:text-slate-900'
  }`
}

function QuickLinkIcon({ kind }: { kind: 'learning' | 'outdoor' | 'deals' | 'new' }) {
  if (kind === 'learning') return <IconGraduation size={22} className="text-amber-500" />
  if (kind === 'outdoor') return <IconTree size={22} className="text-emerald-500" />
  if (kind === 'deals') return <IconPercent size={22} className="text-rose-500" />
  return <IconStar size={22} filled className="text-amber-400" />
}

export function CategoryNavBar() {
  const location = useLocation()
  const { locale, t } = useLocale()
  const quickLinks = getCategoryNavQuickLinks(t)
  const navRef = useRef<HTMLElement>(null)
  const homeHoverRef = useRef(0)
  const [menuOpen, setMenuOpen] = useState(false)
  const [activeMainCode, setActiveMainCode] = useState<number | null>(null)

  const whatsappNumber = getWhatsAppNumber()
  const whatsappHref = whatsappNumber ? buildWhatsAppUrl(whatsappNumber, t.shared.whatsappMessage) : null

  const { data: tree = [] } = useQuery(catalogQueries.categoryTree)
  const { data: ageGroups = [] } = useQuery(catalogQueries.ageGroups)
  const { data: brands = [] } = useQuery(catalogQueries.brands)

  const closeMenu = useCallback(() => setMenuOpen(false), [])

  const openMenu = useCallback(
    (mainCode?: number) => {
      const code = mainCode ?? tree[0]?.code ?? null
      if (code == null) return
      setActiveMainCode(code)
      setMenuOpen(true)
    },
    [tree],
  )

  useEffect(() => {
    closeMenu()
  }, [location.pathname, closeMenu])

  useEffect(() => {
    if (!menuOpen) return
    function onPointerDown(e: MouseEvent) {
      if (navRef.current && !navRef.current.contains(e.target as Node)) {
        setMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', onPointerDown)
    return () => document.removeEventListener('mousedown', onPointerDown)
  }, [menuOpen])

  const resolvedMainCode = activeMainCode ?? tree[0]?.code ?? 0
  const homeActive = location.pathname === '/' && !location.search
  const ageItems = ageGroups.map((group) => ({
    href: `/products?age=${group.slug}`,
    label: ageGroupDisplayName(group, locale, t),
  }))
  const brandItems = brands
    .filter((brand) => brand.code)
    .slice(0, 20)
    .map((brand) => ({
      href: `/products?brand=${brand.code}`,
      label: brandDisplayName(brand, locale),
    }))

  return (
    <nav
      ref={navRef}
      className="font-nav relative z-40 hidden overflow-visible bg-white text-slate-800 md:block"
      aria-label={t.nav.shop}
    >
      <div className={`${HOME_CONTAINER} flex items-center gap-2 py-2`}>
        <div className="flex min-w-0 flex-1 items-center gap-1.5 overflow-visible rounded-full bg-[#FFF1F5] px-1.5 py-1.5 lg:gap-2 lg:px-3">
          <div className="scrollbar-hide flex min-w-0 flex-1 items-end justify-evenly overflow-x-auto overflow-y-visible">
            <button
              type="button"
              onMouseEnter={() => {
                window.clearTimeout(homeHoverRef.current)
                homeHoverRef.current = window.setTimeout(() => openMenu(), 280)
              }}
              onMouseLeave={() => window.clearTimeout(homeHoverRef.current)}
              onClick={() => (menuOpen ? closeMenu() : openMenu())}
              aria-current={homeActive ? 'page' : undefined}
              aria-expanded={menuOpen}
              aria-haspopup="dialog"
              className={`shrink-0 ${navItemClass(homeActive || menuOpen)}`}
            >
              <IconHome size={22} className="text-brand-accent" />
              <span className="leading-none">{t.nav.home}</span>
            </button>

            <HeaderNavMenu
              icon={<IconBabyFace size={22} className="text-sky-400" />}
              label={t.headerBar.age}
              items={ageItems}
              footerHref="/products"
              footerLabel={t.headerBar.viewAllAges}
              active={location.search.includes('age=')}
              onHover={closeMenu}
            />
            <HeaderNavMenu
              icon={<IconTag size={22} className="text-brand-purple" />}
              label={t.headerBar.brands}
              items={brandItems}
              footerHref="/products"
              footerLabel={t.headerBar.viewAllBrands}
              active={location.search.includes('brand=')}
              onHover={closeMenu}
            />

            {quickLinks.map((item) => {
              const active = isNavLinkActive(item.href, location.pathname, location.search)
              return (
                <Link
                  key={item.href}
                  to={item.href}
                  onMouseEnter={closeMenu}
                  onClick={closeMenu}
                  aria-current={active ? 'page' : undefined}
                  className={`shrink-0 ${navItemClass(active)}`}
                >
                  <QuickLinkIcon kind={item.icon} />
                  <span className="whitespace-nowrap leading-none">{item.label}</span>
                </Link>
              )
            })}
          </div>

          <Link
            to="/gift-finder"
            onMouseEnter={closeMenu}
            onClick={closeMenu}
            aria-label={t.headerBar.giftIdeas}
            aria-current={location.pathname.startsWith('/gift-finder') ? 'page' : undefined}
            className="inline-flex shrink-0 items-center gap-2 rounded-full bg-white px-3 py-2.5 text-[13px] font-semibold text-slate-800 shadow-[0_4px_16px_rgba(233,30,99,0.10)] transition hover:text-brand-accent lg:px-5 lg:py-3 lg:text-[14px]"
          >
            <IconGift size={20} className="text-brand-accent" />
            <span className="hidden whitespace-nowrap lg:inline">{t.headerBar.giftIdeas}</span>
            <IconChevronRight size={16} className="text-slate-400 rtl:rotate-180" />
          </Link>
        </div>

        {whatsappHref ? (
          <a
            href={whatsappHref}
            target="_blank"
            rel="noopener noreferrer"
            aria-label={t.headerBar.whatsappUs}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-[#25D366] px-2.5 py-2.5 text-[14px] font-semibold text-white shadow-sm transition hover:bg-[#20BD5A] lg:px-3.5"
          >
            <IconWhatsApp size={16} />
            <span className="hidden whitespace-nowrap xl:inline">{t.headerBar.whatsappUs}</span>
          </a>
        ) : null}
      </div>

      {menuOpen && tree.length > 0 && (
        <CategoryMegaMenu
          tree={tree}
          ageGroups={ageGroups}
          activeMainCode={resolvedMainCode}
          onActiveMainChange={setActiveMainCode}
          onClose={closeMenu}
          anchorRef={navRef}
        />
      )}
    </nav>
  )
}
