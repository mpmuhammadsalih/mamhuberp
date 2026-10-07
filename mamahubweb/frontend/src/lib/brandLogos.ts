export interface BrandLogoConfig {
  logoSrc: string
  circleBg: string
}

/** Most specific keys first — partial match on normalized brand name. */
const BRAND_LOGO_ENTRIES: Array<{ keys: string[]; config: BrandLogoConfig }> = [
  { keys: ['disney stitch', 'stitch'], config: { logoSrc: '/brands/stitch.svg', circleBg: 'bg-[#EEF2FF]' } },
  { keys: ['lol surprise', 'l.o.l'], config: { logoSrc: '/brands/lol-surprise.svg', circleBg: 'bg-[#FAF5FF]' } },
  { keys: ['hot wheels'], config: { logoSrc: '/brands/hot-wheels.svg', circleBg: 'bg-[#FFF4ED]' } },
  { keys: ['fisher price', 'fisher-price'], config: { logoSrc: '/brands/fisher-price.svg', circleBg: 'bg-[#EFF6FF]' } },
  { keys: ['play-doh', 'playdoh'], config: { logoSrc: '/brands/play-doh.svg', circleBg: 'bg-[#F0FDF4]' } },
  { keys: ['lego'], config: { logoSrc: '/brands/lego.svg', circleBg: 'bg-[#FFF9E6]' } },
  { keys: ['disney'], config: { logoSrc: '/brands/disney.svg', circleBg: 'bg-[#EEF4FF]' } },
  { keys: ['barbie'], config: { logoSrc: '/brands/barbie.svg', circleBg: 'bg-[#FFF0F6]' } },
  { keys: ['pokemon', 'pokémon'], config: { logoSrc: '/brands/pokemon.svg', circleBg: 'bg-[#FEF9C3]' } },
  { keys: ['apple'], config: { logoSrc: '/brands/apple.svg', circleBg: 'bg-[#F8FAFC]' } },
  { keys: ['intex'], config: { logoSrc: '/brands/intex.svg', circleBg: 'bg-[#E0F2FE]' } },
  { keys: ['sony'], config: { logoSrc: '/brands/sony.svg', circleBg: 'bg-[#F8FAFC]' } },
  { keys: ['hasbro'], config: { logoSrc: '/brands/hasbro.svg', circleBg: 'bg-[#EFF6FF]' } },
  { keys: ['mattel'], config: { logoSrc: '/brands/mattel.svg', circleBg: 'bg-[#FFF1F2]' } },
  { keys: ['nerf'], config: { logoSrc: '/brands/nerf.svg', circleBg: 'bg-[#FFF7ED]' } },
  { keys: ['nickelodeon'], config: { logoSrc: '/brands/nickelodeon.svg', circleBg: 'bg-[#FFF7ED]' } },
]

const FALLBACK_CIRCLE_BGS = [
  'bg-[#FFF9E6]',
  'bg-[#EFF6FF]',
  'bg-[#FFF0F6]',
  'bg-[#F0FDF4]',
  'bg-[#F5F3FF]',
  'bg-[#FFF7ED]',
  'bg-[#EEF2FF]',
  'bg-[#FFF1F2]',
  'bg-[#F0FDFA]',
  'bg-[#FEF3C7]',
  'bg-[#FCE7F3]',
  'bg-[#ECFEFF]',
]

const FALLBACK_TEXT_COLORS = [
  'text-[#E91E63]',
  'text-[#2563EB]',
  'text-[#7C3AED]',
  'text-[#16A34A]',
  'text-[#EA580C]',
  'text-[#0891B2]',
  'text-[#DB2777]',
  'text-[#4F46E5]',
]

function normalizeBrandKey(name?: string | null): string {
  return (name ?? '').trim().toLowerCase().replace(/\s+/g, ' ')
}

export function getBrandLogo(name?: string | null): BrandLogoConfig | null {
  const key = normalizeBrandKey(name)
  if (!key) return null

  for (const entry of BRAND_LOGO_ENTRIES) {
    if (entry.keys.some((k) => key === k || key.includes(k))) {
      return entry.config
    }
  }

  return null
}

export function getBrandFallbackStyle(name?: string | null, index = 0) {
  const safeName = (name ?? '').trim() || 'Brand'
  const words = safeName.split(/\s+/).filter(Boolean)
  const initials =
    words.length >= 2
      ? `${words[0][0]}${words[1][0]}`.toUpperCase()
      : safeName.slice(0, 2).toUpperCase()

  return {
    initials,
    circleBg: FALLBACK_CIRCLE_BGS[index % FALLBACK_CIRCLE_BGS.length],
    textClass: FALLBACK_TEXT_COLORS[index % FALLBACK_TEXT_COLORS.length],
  }
}
