function envUrl(name: string, fallback: string): string {
  const value = String(import.meta.env[name] || '').trim()
  return value || fallback
}

export const SOCIAL_LINKS = [
  {
    id: 'facebook' as const,
    href: envUrl('VITE_SOCIAL_FACEBOOK', 'https://www.facebook.com/mamahub.store'),
  },
  {
    id: 'x' as const,
    href: envUrl('VITE_SOCIAL_X', 'https://x.com/mamahubstore'),
  },
  {
    id: 'instagram' as const,
    href: envUrl('VITE_SOCIAL_INSTAGRAM', 'https://www.instagram.com/mamahub.store'),
  },
  {
    id: 'youtube' as const,
    href: envUrl('VITE_SOCIAL_YOUTUBE', 'https://www.youtube.com/@mamahub.store'),
  },
  {
    id: 'tiktok' as const,
    href: envUrl('VITE_SOCIAL_TIKTOK', 'https://www.tiktok.com/@mamahub.store'),
  },
]
