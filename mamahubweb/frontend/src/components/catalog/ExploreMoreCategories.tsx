import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { HOME_CONTAINER, HOME_GRID_GAP } from '../layout/homeLayout'
import { IconArrowUpRight } from '../icons/Icons'
import { useLocale } from '../../i18n/LocaleContext'
import { exploreTileDisplayName } from '../../i18n/exploreTileName'
import { resolveMediaUrl } from '../../lib/media'
import { catalogQueries } from '../../lib/queries/catalog'

interface CategoryTile {
  id: string
  name: string
  href: string
  image: string
}

const FALLBACK_TILES: CategoryTile[] = [
  { id: 'outdoor', name: 'Outdoor & Play', href: '/products?q=outdoor', image: '/demo-products/01-toys.jpg' },
  { id: 'lego', name: 'LEGO & Building', href: '/products?q=LEGO', image: '/demo-products/10.jpg' },
  { id: 'baby', name: 'Baby & Toddler', href: '/products?age=0-2', image: '/demo-products/20.jpg' },
  { id: 'games', name: 'Games & Puzzles', href: '/products?q=game', image: '/demo-products/12.jpg' },
  { id: 'gifts', name: 'Gifts & Party', href: '/gift-finder', image: '/demo-products/11-spices.jpg' },
]

function buildTilesFromMedia(
  media: Array<{
    ref_key?: string | null
    title?: string | null
    image_url?: string | null
    link_url?: string | null
    sort_order?: number
  }>,
): CategoryTile[] {
  const sorted = [...media].sort(
    (a, b) => Number(a.sort_order ?? 0) - Number(b.sort_order ?? 0),
  )

  const tiles: CategoryTile[] = []
  for (const item of sorted) {
    const image = resolveMediaUrl(item.image_url)
    if (!image) continue
    tiles.push({
      id: String(item.ref_key ?? item.title ?? tiles.length),
      name: item.title?.trim() || 'Category',
      href: item.link_url?.trim() || '/products',
      image,
    })
  }
  return tiles
}

function CategoryTileCard({
  tile,
  label,
  className = '',
}: {
  tile: CategoryTile
  label: string
  className?: string
}) {
  return (
    <Link
      to={tile.href}
      className={`group relative overflow-hidden rounded-2xl bg-gray-200 ${className}`}
    >
      <img
        key={tile.image}
        src={tile.image}
        alt=""
        className="absolute inset-0 h-full w-full object-cover transition duration-500 group-hover:scale-105"
        loading="lazy"
      />
      <div className="absolute inset-0 bg-gradient-to-t from-black/50 via-black/10 to-black/20" />

      <div className="relative flex h-full min-h-[140px] flex-col p-4 sm:p-5">
        <div className="flex items-start justify-between gap-2">
          <span className="font-catalog text-base font-bold leading-snug text-white sm:text-lg">
            {label}
          </span>
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-white/25 text-white backdrop-blur-sm transition group-hover:bg-white/40">
            <IconArrowUpRight size={16} />
          </span>
        </div>
      </div>
    </Link>
  )
}

export function ExploreMoreCategories() {
  const { locale, t } = useLocale()
  const { data: exploreMedia = [] } = useQuery(catalogQueries.exploreCategoryMedia)

  const tiles = useMemo(() => {
    const fromMedia = buildTilesFromMedia(exploreMedia)
    if (fromMedia.length >= 5) {
      return fromMedia.slice(0, 5)
    }
    const merged = [...fromMedia]
    for (const fallback of FALLBACK_TILES) {
      if (merged.length >= 5) break
      if (!merged.some((tile) => tile.id === fallback.id)) {
        merged.push(fallback)
      }
    }
    return merged.slice(0, 5)
  }, [exploreMedia])

  const [left, centerTop, bottomLeft, bottomRight, right] = tiles

  const tileLabel = (tile: CategoryTile) => exploreTileDisplayName(tile, locale, t)

  return (
    <section className={`${HOME_CONTAINER} py-8 lg:py-10`}>
      <h2 className="font-catalog mb-5 text-xl font-bold text-gray-900 sm:mb-6 sm:text-2xl">
        {t.home.exploreMoreCategories}
      </h2>

      <div className={`grid grid-cols-2 ${HOME_GRID_GAP} md:hidden`}>
        <CategoryTileCard tile={left} label={tileLabel(left)} className="col-span-2 min-h-[200px]" />
        <CategoryTileCard tile={centerTop} label={tileLabel(centerTop)} className="col-span-2 min-h-[160px]" />
        <CategoryTileCard tile={bottomLeft} label={tileLabel(bottomLeft)} className="min-h-[140px]" />
        <CategoryTileCard tile={bottomRight} label={tileLabel(bottomRight)} className="min-h-[140px]" />
        <CategoryTileCard tile={right} label={tileLabel(right)} className="col-span-2 min-h-[200px]" />
      </div>

      <div className={`hidden md:grid md:grid-cols-3 md:grid-rows-2 ${HOME_GRID_GAP} md:h-[460px] lg:h-[500px]`}>
        <CategoryTileCard tile={left} label={tileLabel(left)} className="row-span-2 min-h-0" />
        <CategoryTileCard tile={centerTop} label={tileLabel(centerTop)} className="min-h-0" />
        <CategoryTileCard tile={right} label={tileLabel(right)} className="col-start-3 row-span-2 row-start-1 min-h-0" />
        <div className={`col-start-2 row-start-2 grid grid-cols-2 ${HOME_GRID_GAP} min-h-0`}>
          <CategoryTileCard tile={bottomLeft} label={tileLabel(bottomLeft)} className="min-h-0" />
          <CategoryTileCard tile={bottomRight} label={tileLabel(bottomRight)} className="min-h-0" />
        </div>
      </div>
    </section>
  )
}
