import type { SupportedLocale, TranslationTree } from './types'

type AgeGroupLike = { slug: string; age_group_name: string }

type AgeGroupKey = keyof TranslationTree['ageGroups']

const SLUG_ALIASES: Record<string, AgeGroupKey> = {
  '0-12': '0-12-months',
  '0-12m': '0-12-months',
  '0-12-months': '0-12-months',
  '1-2': '1-2-years',
  '1-2y': '1-2-years',
  '1-2-years': '1-2-years',
  '3-5': '3-5-years',
  '3-5y': '3-5-years',
  '3-5-years': '3-5-years',
  '6-8': '6-8-years',
  '6-8y': '6-8-years',
  '6-8-years': '6-8-years',
  '9-12': '9-12-years',
  '9-12y': '9-12-years',
  '9-12-years': '9-12-years',
  '13-plus': '13-plus-years',
  '13-plus-years': '13-plus-years',
}

const NAME_ALIASES: Record<string, AgeGroupKey> = {
  '0-12 months': '0-12-months',
  'months 0-12': '0-12-months',
  '0–12 months': '0-12-months',
  '1-2 years': '1-2-years',
  'years 1-2': '1-2-years',
  '1–2 years': '1-2-years',
  '3-5 years': '3-5-years',
  'years 3-5': '3-5-years',
  '3–5 years': '3-5-years',
  '6-8 years': '6-8-years',
  'years 6-8': '6-8-years',
  '6–8 years': '6-8-years',
  '9-12 years': '9-12-years',
  'years 9-12': '9-12-years',
  '9–12 years': '9-12-years',
  '13+ years': '13-plus-years',
  'years 13+': '13-plus-years',
}

function resolveAgeGroupKey(group: AgeGroupLike): AgeGroupKey | null {
  const slug = group.slug.trim().toLowerCase()
  if (slug in SLUG_ALIASES) return SLUG_ALIASES[slug]

  const name = group.age_group_name.trim().toLowerCase()
  if (name in NAME_ALIASES) return NAME_ALIASES[name]

  return null
}

export function ageGroupDisplayName(group: AgeGroupLike, _locale: SupportedLocale, t: TranslationTree): string {
  const key = resolveAgeGroupKey(group)
  if (key) {
    return t.ageGroups[key]
  }
  return group.age_group_name
}
