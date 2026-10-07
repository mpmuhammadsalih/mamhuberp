import { useEffect, useLayoutEffect, useState, type RefObject } from 'react'
import { Link } from 'react-router-dom'
import { IconChevronRight } from '../icons/Icons'
import { HOME_CONTAINER } from '../layout/homeLayout'
import { ToyRainbowBar } from '../layout/ToyRainbowBar'
import { categoryDisplayName } from '../../i18n/categoryName'
import { ageGroupDisplayName } from '../../i18n/ageGroupName'
import { useLocale } from '../../i18n/LocaleContext'
import { useLocalizedLabel } from '../../i18n/useLocalizedLabel'
import { resolveMediaUrl } from '../../lib/media'
import type { CategoryNode } from '../../lib/queries/catalog'
import { CategoryMenuIcon } from './CategoryMenuIcon'

interface Props {
  tree: CategoryNode[]
  ageGroups: Array<{ slug: string; age_group_name: string; image_url?: string | null }>
  activeMainCode: number
  onActiveMainChange: (code: number) => void
  onClose: () => void
  anchorRef: RefObject<HTMLElement | null>
}

const AGE_CHIP = [
  'bg-[#FFF3C4] text-[#C2410C]',
  'bg-[#D1FAE5] text-[#047857]',
  'bg-[#EDE9FE] text-[#6D28D9]',
  'bg-[#DBEAFE] text-[#1D4ED8]',
] as const

export function CategoryMegaMenu({
  tree,
  ageGroups,
  activeMainCode,
  onActiveMainChange,
  onClose,
  anchorRef,
}: Props) {
  const { locale, t } = useLocale()
  const formatLabel = useLocalizedLabel()
  const [panelTop, setPanelTop] = useState(160)
  const activeMain = tree.find((m) => m.code === activeMainCode) ?? tree[0]
  const departments = activeMain?.children ?? []
  const activeLabel = activeMain ? formatLabel(categoryDisplayName(activeMain, locale)) : ''

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  useLayoutEffect(() => {
    function fitToViewport() {
      const nav = anchorRef.current
      const top = nav ? nav.getBoundingClientRect().bottom + 8 : 160
      setPanelTop(Math.max(72, Math.floor(top)))
    }
    fitToViewport()
    window.addEventListener('resize', fitToViewport)
    window.visualViewport?.addEventListener('resize', fitToViewport)
    window.visualViewport?.addEventListener('scroll', fitToViewport)
    window.addEventListener('scroll', fitToViewport, true)
    return () => {
      window.removeEventListener('resize', fitToViewport)
      window.visualViewport?.removeEventListener('resize', fitToViewport)
      window.visualViewport?.removeEventListener('scroll', fitToViewport)
      window.removeEventListener('scroll', fitToViewport, true)
    }
  }, [anchorRef])

  useEffect(() => {
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = prev
    }
  }, [])

  return (
    <>
      <button
        type="button"
        aria-label={t.categoryNav.closeMenu}
        className="fixed inset-0 z-40 bg-slate-900/30 backdrop-blur-[2px]"
        onClick={onClose}
      />

      <div
        style={{
          top: panelTop,
          bottom: 'max(0.75rem, env(safe-area-inset-bottom, 0px))',
        }}
        className="fixed inset-x-0 z-50"
        role="dialog"
        aria-label={t.categoryNav.shopByCategory}
      >
        <div className={`${HOME_CONTAINER} h-full`}>
          <div className="@container/mega font-nav flex h-full w-full min-h-0 flex-col overflow-hidden rounded-3xl bg-white text-brand-ink shadow-[0_24px_60px_rgba(15,23,42,0.16)] ring-1 ring-brand-border/50">
        <ToyRainbowBar />
        <div className="flex min-h-0 flex-1 flex-col @min-[640px]/mega:flex-row">
          <aside className="shrink-0 overflow-x-auto overflow-y-auto border-b border-brand-border/50 bg-brand-cream-alt/80 py-3 @min-[640px]/mega:w-[min(13.5rem,32%)] @min-[640px]/mega:overflow-x-hidden @min-[640px]/mega:border-b-0 @min-[640px]/mega:border-e @min-[640px]/mega:py-5">
            <p className="mb-2 px-4 text-[11px] font-bold uppercase tracking-[0.16em] text-brand-orange @min-[640px]/mega:mb-3">
              {t.categoryNav.shopByCategory}
            </p>
            <ul className="flex gap-1 px-3 @min-[640px]/mega:block @min-[640px]/mega:space-y-1">
              {tree.map((main) => {
                const active = main.code === activeMain?.code
                const mainLabel = formatLabel(categoryDisplayName(main, locale))
                return (
                  <li key={main.code} className="shrink-0 @min-[640px]/mega:shrink">
                    <button
                      type="button"
                      onMouseEnter={() => onActiveMainChange(main.code)}
                      onFocus={() => onActiveMainChange(main.code)}
                      onClick={() => onActiveMainChange(main.code)}
                      className={`flex w-full items-center gap-2 rounded-2xl px-3 py-2 text-start text-sm font-bold tracking-normal transition @min-[640px]/mega:gap-2.5 @min-[640px]/mega:py-2.5 ${
                        active
                          ? 'bg-white text-brand-ink shadow-sm ring-2 ring-brand-orange'
                          : 'text-slate-700 hover:bg-white/80'
                      }`}
                    >
                      <CategoryMenuIcon name={main.name} seed={main.code} />
                      <span className="min-w-0 truncate">{mainLabel}</span>
                      <IconChevronRight
                        size={12}
                        className={`hidden shrink-0 rtl:rotate-180 @min-[640px]/mega:block ${
                          active ? 'text-brand-orange' : 'text-slate-300'
                        }`}
                      />
                    </button>
                  </li>
                )
              })}
            </ul>
          </aside>

          <div className="flex min-h-0 min-w-0 flex-1 flex-col bg-brand-cream/40">
            <div className="flex shrink-0 items-center justify-between gap-3 px-4 py-2.5 sm:px-5">
              <h3 className="min-w-0 truncate font-display text-base font-extrabold tracking-normal text-brand-ink sm:text-lg">
                {activeLabel || t.categoryNav.shopByCategory}
              </h3>
              {activeMain && (
                <Link
                  to={`/products?main=${activeMain.code}`}
                  onClick={onClose}
                  className="shrink-0 text-xs font-bold tracking-normal text-brand-accent hover:underline sm:text-sm"
                >
                  {t.categoryNav.browseAll} {activeLabel}
                </Link>
              )}
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-3 pb-2 sm:px-4 [scrollbar-gutter:stable]">
              {departments.length > 0 ? (
                <div className="grid grid-cols-3 gap-1.5 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 xl:grid-cols-7">
                  {departments.map((dept) => (
                    <CategoryTile
                      key={dept.code}
                      href={`/products?main=${activeMain?.code}&dept=${dept.code}`}
                      name={dept.name}
                      label={formatLabel(categoryDisplayName(dept, locale))}
                      seed={dept.code}
                      imageUrl={dept.image_url}
                      onClose={onClose}
                    />
                  ))}
                </div>
              ) : activeMain ? (
                <div className="flex h-28 items-center justify-center">
                  <Link
                    to={`/products?main=${activeMain.code}`}
                    onClick={onClose}
                    className="rounded-full bg-brand-accent px-5 py-2.5 text-sm font-bold text-white"
                  >
                    {t.categoryNav.browseAll} {activeLabel}
                  </Link>
                </div>
              ) : null}
            </div>

            {ageGroups.length > 0 && (
              <div className="shrink-0 border-t border-brand-border/50 px-4 py-2.5 sm:px-5">
                <p className="mb-2 text-[11px] font-bold uppercase tracking-[0.16em] text-brand-orange">
                  {t.categoryNav.shopByAge}
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {ageGroups.map((group, index) => (
                    <Link
                      key={group.slug}
                      to={`/products?age=${group.slug}`}
                      onClick={onClose}
                      className={`rounded-full px-3 py-1 text-[13px] font-bold tracking-normal transition hover:scale-[1.03] ${
                        AGE_CHIP[index % AGE_CHIP.length]
                      }`}
                    >
                      {ageGroupDisplayName(group, locale, t)}
                    </Link>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
          </div>
        </div>
      </div>
    </>
  )
}

function CategoryTile({
  href,
  name,
  label,
  seed,
  imageUrl,
  onClose,
}: {
  href: string
  name: string
  label: string
  seed: number
  imageUrl?: string | null
  onClose: () => void
}) {
  const photo = resolveMediaUrl(imageUrl)

  return (
    <Link
      to={href}
      onClick={onClose}
      className="group flex flex-col items-center gap-1 rounded-2xl bg-white px-1 py-1.5 text-center shadow-sm ring-1 ring-brand-border/40 transition hover:-translate-y-0.5 hover:shadow-md hover:ring-brand-orange/50 motion-reduce:transform-none"
    >
      {photo ? (
        <span className="flex h-9 w-9 overflow-hidden rounded-full bg-brand-cream ring-2 ring-brand-border/60">
          <img src={photo} alt="" className="h-full w-full object-cover" />
        </span>
      ) : (
        <CategoryMenuIcon name={name} seed={seed} />
      )}
      <span className="line-clamp-2 min-h-7 text-[11px] font-bold leading-tight tracking-normal text-slate-800 group-hover:text-brand-accent sm:text-[12px]">
        {label}
      </span>
    </Link>
  )
}
