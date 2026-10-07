import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { HOME_CONTAINER } from '../layout/homeLayout'
import { IconGrid } from '../icons/Icons'
import { resolveMediaUrl } from '../../lib/media'
import { categoryDisplayName } from '../../i18n/categoryName'
import { useLocale } from '../../i18n/LocaleContext'
import { toTitleCase } from '../../lib/textCase'
import type { CategoryNode } from '../../lib/queries/catalog'
import type { SupportedLocale, TranslationTree } from '../../i18n/types'

interface CategoryIconItem {
  name: string
  href: string
  emoji: string
  bgClass: string
  code?: number
  imageUrl?: string
}

const BG_CLASSES = [
  'bg-brand-tint ring-brand-border/60',
  'bg-orange-100 ring-orange-200/70',
  'bg-teal-100 ring-teal-200/70',
  'bg-purple-100 ring-purple-200/70',
  'bg-yellow-100 ring-yellow-200/70',
  'bg-sky-100 ring-sky-200/70',
  'bg-rose-100 ring-rose-200/70',
  'bg-emerald-100 ring-emerald-200/70',
]

const MAX_ITEMS = 10

function categoryEmoji(name: string): string {
  const n = name.toLowerCase()
  if (/ride|bike|scooter|vehicle|car|wheel/.test(n)) return '🚲'
  if (/doll|pretend|role|fashion/.test(n)) return '👗'
  if (/baby|toddler|infant|nursery/.test(n)) return '🍼'
  if (/game|puzzle|board/.test(n)) return '🎲'
  if (/outdoor|sport|playground|garden/.test(n)) return '⚽'
  if (/lego|build|block|construct/.test(n)) return '🧱'
  if (/book|learn|educat|stationery|school/.test(n)) return '📚'
  if (/art|craft|creative|paint/.test(n)) return '🎨'
  if (/music|instrument/.test(n)) return '🎵'
  if (/electronic|tech|robot/.test(n)) return '🤖'
  if (/gift|party/.test(n)) return '🎁'
  if (/plush|soft|teddy|stuffed/.test(n)) return '🧸'
  if (/action|figure|hero/.test(n)) return '🦸'
  return '🧸'
}

function buildCategoryIcons(tree: CategoryNode[], locale: SupportedLocale): CategoryIconItem[] {
  const items: CategoryIconItem[] = []

  for (const main of tree) {
    if (main.children?.length) {
      for (const dept of main.children) {
        const label = categoryDisplayName(dept, locale)
        items.push({
          name: label,
          href: `/products?main=${main.code}&dept=${dept.code}`,
          emoji: categoryEmoji(dept.name),
          bgClass: BG_CLASSES[items.length % BG_CLASSES.length],
          code: dept.code,
          imageUrl: dept.image_url ?? undefined,
        })
        if (items.length >= MAX_ITEMS) return items
      }
    } else {
      const label = categoryDisplayName(main, locale)
      items.push({
        name: label,
        href: `/products?main=${main.code}`,
        emoji: categoryEmoji(main.name),
        bgClass: BG_CLASSES[items.length % BG_CLASSES.length],
        code: main.code,
        imageUrl: main.image_url ?? undefined,
      })
      if (items.length >= MAX_ITEMS) return items
    }
  }

  return items
}

function buildFallbackIcons(t: TranslationTree): CategoryIconItem[] {
  const c = t.catalog.categoryTiles
  return [
    { name: c.rideOns, href: '/products?q=ride', emoji: '🚲', bgClass: BG_CLASSES[0] },
    { name: c.dolls, href: '/products?q=doll', emoji: '👸', bgClass: BG_CLASSES[1] },
    { name: c.building, href: '/products?q=lego', emoji: '🧱', bgClass: BG_CLASSES[2] },
    { name: c.outdoor, href: '/products?q=outdoor', emoji: '⚽', bgClass: BG_CLASSES[3] },
    { name: c.games, href: '/products?q=game', emoji: '🎲', bgClass: BG_CLASSES[4] },
    { name: c.baby, href: '/products?age=0-2', emoji: '🍼', bgClass: BG_CLASSES[5] },
    { name: c.artsCrafts, href: '/products?q=craft', emoji: '🎨', bgClass: BG_CLASSES[6] },
    { name: c.plush, href: '/products?q=plush', emoji: '🧸', bgClass: BG_CLASSES[7] },
    { name: c.gifts, href: '/gift-finder', emoji: '🎁', bgClass: BG_CLASSES[0] },
    { name: c.electronics, href: '/products?q=electronic', emoji: '🤖', bgClass: BG_CLASSES[1] },
  ]
}

function CategoryIconTile({ item, locale }: { item: CategoryIconItem; locale: SupportedLocale }) {
  const photo = resolveMediaUrl(item.imageUrl)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    setFailed(false)
  }, [photo])

  const showPhoto = Boolean(photo) && !failed

  return (
    <Link
      to={item.href}
      className="group flex w-full flex-col items-center gap-2"
    >
      <span
        className={`relative flex aspect-square w-full items-center justify-center overflow-hidden rounded-full text-[1.75rem] shadow-sm ring-2 transition duration-200 group-hover:-rotate-3 group-hover:scale-105 group-hover:shadow-md motion-reduce:transition-none motion-reduce:group-hover:rotate-0 motion-reduce:group-hover:scale-100 sm:text-[2rem] ${item.bgClass}`}
      >
        {showPhoto ? (
          <img
            key={photo}
            src={photo}
            alt=""
            className="h-full w-full object-cover object-center transition duration-500 group-hover:scale-[1.05]"
            loading="lazy"
            onError={() => setFailed(true)}
          />
        ) : (
          <span aria-hidden>{item.emoji}</span>
        )}
      </span>
      <span className="line-clamp-2 w-full text-center text-xs font-semibold leading-tight text-brand-ink group-hover:text-brand-accent sm:text-sm">
        {locale === 'ar' ? item.name : toTitleCase(item.name)}
      </span>
    </Link>
  )
}

interface Props {
  categories?: CategoryNode[]
}

export function ShopByCategoryIcons({ categories = [] }: Props) {
  const { locale, t } = useLocale()
  const icons = buildCategoryIcons(categories, locale)
  const items = (icons.length > 0 ? icons : buildFallbackIcons(t)).slice(0, MAX_ITEMS)

  return (
    <section className={`${HOME_CONTAINER} pb-2 pt-2 lg:pb-4`}>
      <h2 className="mb-5 flex items-center gap-2 font-display text-xl font-bold text-brand-ink sm:mb-6 sm:text-2xl">
        <IconGrid size={24} className="text-brand-orange" />
        {t.categoryNav.shopByCategory}
      </h2>

      <div className="grid grid-cols-3 gap-x-2 gap-y-6 sm:grid-cols-5 sm:gap-x-3 sm:gap-y-6">
        {items.map((item) => (
          <CategoryIconTile
            key={`${item.href}-${item.code ?? item.name}-${item.imageUrl ?? 'emoji'}`}
            item={item}
            locale={locale}
          />
        ))}
      </div>
    </section>
  )
}
