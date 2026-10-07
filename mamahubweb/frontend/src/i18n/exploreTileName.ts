import { toTitleCase } from '../lib/textCase'
import type { SupportedLocale, TranslationTree } from './types'

type ExploreTileKey = keyof TranslationTree['home']['exploreTiles']

const ENGLISH_TITLE_TO_KEY: Record<string, ExploreTileKey> = {
  'outdoor & play': 'outdoor',
  'lego & building': 'lego',
  'baby & toddler': 'baby',
  'games & puzzles': 'games',
  'gifts & party': 'gifts',
}

const KNOWN_TILE_KEYS = ['outdoor', 'lego', 'baby', 'games', 'gifts'] as const

function resolveTileKey(id: string, name: string): ExploreTileKey | null {
  if ((KNOWN_TILE_KEYS as readonly string[]).includes(id)) {
    return id as ExploreTileKey
  }
  const normalized = name.trim().toLowerCase()
  return ENGLISH_TITLE_TO_KEY[normalized] ?? null
}

export function exploreTileDisplayName(
  tile: { id: string; name: string },
  locale: SupportedLocale,
  t: TranslationTree,
): string {
  if (locale === 'ar') {
    const key = resolveTileKey(tile.id, tile.name)
    if (key && key !== 'category') {
      return t.home.exploreTiles[key]
    }
    return tile.name.trim() || t.home.exploreTiles.category
  }
  return toTitleCase(tile.name)
}
