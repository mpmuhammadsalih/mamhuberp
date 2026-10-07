import { useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { IconChevronLeft, IconChevronRight, IconClose } from '../icons/Icons'
import { Logo } from '../Logo'
import { resolveMediaUrl } from '../../lib/media'
import { getCategoryDrawerQuickLinks } from '../layout/categoryNavLinks'
import { categoryDisplayName } from '../../i18n/categoryName'
import { ageGroupDisplayName } from '../../i18n/ageGroupName'
import { useLocale } from '../../i18n/LocaleContext'
import { useLocalizedLabel } from '../../i18n/useLocalizedLabel'
import { catalogQueries, type CategoryNode } from '../../lib/queries/catalog'
import { CategoryMenuIcon } from './CategoryMenuIcon'

interface Props {
  open: boolean
  onClose: () => void
}

type DrawerView =
  | { type: 'root' }
  | { type: 'main'; main: CategoryNode }

function CategoryThumbnail({
  name,
  code,
  imageUrl,
}: {
  name: string
  code: number
  imageUrl?: string | null
}) {
  const resolved = resolveMediaUrl(imageUrl)
  if (resolved) {
    return (
      <img
        src={resolved}
        alt=""
        className="h-10 w-10 shrink-0 rounded-lg bg-gray-100 object-cover"
      />
    )
  }

  return (
    <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-brand-cream-alt">
      <CategoryMenuIcon name={name} seed={code} />
    </span>
  )
}

function DrawerRow({
  label,
  thumbnail,
  hasChildren = false,
  onClick,
  to,
  onNavigate,
}: {
  label: string
  thumbnail?: ReactNode
  hasChildren?: boolean
  onClick?: () => void
  to?: string
  onNavigate: () => void
}) {
  const formatLabel = useLocalizedLabel()
  const content = (
    <>
      {thumbnail}
      <span className="min-w-0 flex-1 text-[15px] font-semibold text-gray-900">{formatLabel(label)}</span>
      {hasChildren ? <IconChevronRight size={18} className="shrink-0 text-gray-400 rtl:rotate-180" /> : null}
    </>
  )

  const className =
    'flex w-full items-center gap-3 border-b border-gray-100 px-4 py-3.5 text-start transition active:bg-gray-50'

  if (to) {
    return (
      <Link to={to} onClick={onNavigate} className={className}>
        {content}
      </Link>
    )
  }

  return (
    <button type="button" onClick={onClick} className={className}>
      {content}
    </button>
  )
}

export function CategoryMobileDrawer({ open, onClose }: Props) {
  const location = useLocation()
  const { locale, t } = useLocale()
  const formatLabel = useLocalizedLabel()
  const quickLinks = getCategoryDrawerQuickLinks(t)
  const [view, setView] = useState<DrawerView>({ type: 'root' })

  const { data: tree = [] } = useQuery({
    ...catalogQueries.categoryTree,
    enabled: open,
  })

  const { data: categoryMedia = [] } = useQuery({
    ...catalogQueries.categoryMedia,
    enabled: open,
  })

  const { data: ageGroups = [] } = useQuery({
    ...catalogQueries.ageGroups,
    enabled: open,
  })

  const imageMap = useMemo(() => {
    const map = new Map<string, string>()
    for (const item of categoryMedia) {
      const key = item.ref_key?.trim()
      if (key && item.image_url) map.set(key, item.image_url)
    }
    return map
  }, [categoryMedia])

  useEffect(() => {
    onClose()
  }, [location.pathname, location.search, onClose])

  useEffect(() => {
    if (!open) {
      setView({ type: 'root' })
      return undefined
    }

    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }

    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.body.style.overflow = previousOverflow
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open, onClose])

  function getCategoryImage(code: number, node?: CategoryNode) {
    return node?.image_url ?? imageMap.get(String(code)) ?? null
  }

  function handleBack() {
    setView({ type: 'root' })
  }

  const activeMain = view.type === 'main' ? view.main : null

  return (
    <>
      <button
        type="button"
        aria-label={t.categoryNav.closeCategories}
        aria-hidden={!open}
        tabIndex={open ? 0 : -1}
        className={`fixed inset-0 z-[75] bg-black/40 transition-opacity duration-300 md:hidden ${
          open ? 'opacity-100' : 'pointer-events-none opacity-0'
        }`}
        onClick={onClose}
      />

      <aside
        className={`fixed inset-y-0 start-0 z-[80] flex w-[min(100vw-2rem,340px)] max-w-[85vw] flex-col bg-white shadow-2xl transition-transform duration-300 ease-out md:hidden ${
          open ? 'translate-x-0' : '-translate-x-full rtl:translate-x-full pointer-events-none'
        }`}
        role="dialog"
        aria-modal={open}
        aria-hidden={!open}
        aria-label={t.categoryNav.shopByCategory}
      >
        <div className="flex shrink-0 items-center justify-between border-b border-gray-200 px-3 py-2.5">
          {view.type === 'main' ? (
            <button
              type="button"
              onClick={handleBack}
              className="flex items-center gap-1 rounded-full px-1 py-1 text-sm font-semibold text-gray-700 hover:bg-gray-100"
            >
              <IconChevronLeft size={18} className="rtl:rotate-180" />
              {t.categoryNav.back}
            </button>
          ) : (
            <Logo compact />
          )}

          <button
            type="button"
            onClick={onClose}
            className="flex h-9 w-9 items-center justify-center rounded-full text-gray-500 hover:bg-gray-100"
            aria-label={t.categoryNav.closeCategories}
          >
            <IconClose size={20} />
          </button>
        </div>

        {view.type === 'main' && activeMain ? (
          <div className="border-b border-gray-100 px-4 py-3">
            <p className="text-lg font-bold text-gray-900">
              {formatLabel(categoryDisplayName(activeMain, locale))}
            </p>
          </div>
        ) : null}

        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
          {view.type === 'root' ? (
            <>
              <DrawerRow
                label={t.categoryNav.allToys}
                thumbnail={
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-brand-tint text-lg">
                    🧸
                  </span>
                }
                to="/products"
                onNavigate={onClose}
              />

              {tree.map((main) => (
                <DrawerRow
                  key={main.code}
                  label={categoryDisplayName(main, locale)}
                  thumbnail={
                    <CategoryThumbnail
                      name={main.name}
                      code={main.code}
                      imageUrl={getCategoryImage(main.code, main)}
                    />
                  }
                  hasChildren={(main.children?.length ?? 0) > 0}
                  to={(main.children?.length ?? 0) === 0 ? `/products?main=${main.code}` : undefined}
                  onClick={
                    (main.children?.length ?? 0) > 0 ? () => setView({ type: 'main', main }) : undefined
                  }
                  onNavigate={onClose}
                />
              ))}

              <div className="px-4 pb-2 pt-4">
                <p className="text-[11px] font-bold uppercase tracking-wide text-gray-400">{t.categoryNav.quickLinks}</p>
              </div>

              {quickLinks.map((item) => (
                <DrawerRow
                  key={item.href}
                  label={item.label}
                  to={item.href}
                  onNavigate={onClose}
                />
              ))}

              {ageGroups.length > 0 ? (
                <>
                  <div className="px-4 pb-2 pt-4">
                    <p className="text-[11px] font-bold uppercase tracking-wide text-gray-400">{t.categoryNav.shopByAge}</p>
                  </div>
                  {ageGroups.map((group) => (
                    <DrawerRow
                      key={group.slug}
                      label={ageGroupDisplayName(group, locale, t)}
                      thumbnail={
                        group.image_url ? (
                          <CategoryThumbnail name={group.age_group_name} code={group.slug.length} imageUrl={group.image_url} />
                        ) : (
                          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-sky-50 text-lg">
                            👶
                          </span>
                        )
                      }
                      to={`/products?age=${group.slug}`}
                      onNavigate={onClose}
                    />
                  ))}
                </>
              ) : null}
            </>
          ) : activeMain ? (
            <>
              <DrawerRow
                label={`${t.categoryNav.allPrefix} ${categoryDisplayName(activeMain, locale)}`}
                to={`/products?main=${activeMain.code}`}
                onNavigate={onClose}
              />

              {(activeMain.children ?? []).map((dept) => (
                <div key={dept.code}>
                  <DrawerRow
                    label={categoryDisplayName(dept, locale)}
                    thumbnail={
                      <CategoryThumbnail
                        name={dept.name}
                        code={dept.code}
                        imageUrl={getCategoryImage(dept.code, dept)}
                      />
                    }
                    to={`/products?main=${activeMain.code}&dept=${dept.code}`}
                    onNavigate={onClose}
                  />

                  {(dept.children ?? []).map((micro) => (
                    <Link
                      key={micro.code}
                      to={`/products?main=${activeMain.code}&dept=${dept.code}&category=${micro.code}`}
                      onClick={onClose}
                      className="flex items-center gap-3 border-b border-gray-100 py-3 ps-14 pe-4 text-start text-[14px] font-medium text-gray-700 transition active:bg-gray-50"
                    >
                      {formatLabel(categoryDisplayName(micro, locale))}
                    </Link>
                  ))}
                </div>
              ))}
            </>
          ) : null}
        </div>
      </aside>
    </>
  )
}
