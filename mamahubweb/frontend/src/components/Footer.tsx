import { Link } from 'react-router-dom'
import { HOME_CONTAINER } from './layout/homeLayout'
import { CartTrustBar } from './cart/CartTrustBar'
import { ToyRainbowBar } from './layout/ToyRainbowBar'
import { Logo } from './Logo'
import { useCmsPages, FALLBACK_CMS_LINKS } from '../lib/queries/cms'
import { SOCIAL_LINKS } from '../lib/social'
import { useLocale } from '../i18n/LocaleContext'
import { localizedCmsLinkLabel } from '../i18n/localizeCmsPage'
import {
  IconFacebook,
  IconInstagram,
  IconTikTok,
  IconX,
  IconYouTube,
} from './icons/Icons'

const SOCIAL_ICONS = {
  facebook: IconFacebook,
  x: IconX,
  instagram: IconInstagram,
  youtube: IconYouTube,
  tiktok: IconTikTok,
} as const

export function Footer() {
  const { data: cmsPages } = useCmsPages()
  const { t } = useLocale()

  const links = (cmsPages?.length ? cmsPages : FALLBACK_CMS_LINKS).map((page) => ({
    to: `/page/${page.slug}`,
    label: localizedCmsLinkLabel(page.slug, page.page_title, t),
  }))

  return (
    <footer className="mt-8 border-t border-brand-border bg-brand-cream">
      <div className={`${HOME_CONTAINER} flex flex-col gap-8 py-12 md:flex-row md:items-start md:justify-between`}>
        <div>
          <Logo compact />
          <p className="mt-3 max-w-xs text-sm text-brand-cocoa/80">{t.footer.tagline}</p>
        </div>
        <nav className="flex flex-wrap gap-x-6 gap-y-3 text-sm font-semibold text-brand-cocoa">
          {links.map((l) => (
            <Link key={l.to} to={l.to} className="hover:text-brand-tan-dark">
              {l.label}
            </Link>
          ))}
        </nav>
      </div>
      <div className={`${HOME_CONTAINER} pb-10`}>
        <CartTrustBar />
      </div>
      <div className="border-t border-brand-border/60 py-4 text-center text-xs text-brand-sage">
        © {new Date().getFullYear()} MamaHub. {t.footer.rights}
      </div>
      <ToyRainbowBar />
      <div className="bg-brand-yellow px-4 py-7 text-center text-brand-ink">
        <p className="mb-4 font-display text-base font-extrabold">{t.footer.social}</p>
        <nav className="flex flex-wrap items-center justify-center gap-3" aria-label={t.footer.social}>
          {SOCIAL_LINKS.map((item, index) => {
            const Icon = SOCIAL_ICONS[item.id]
            const colors = [
              'bg-brand-accent text-white',
              'bg-brand-orange text-white',
              'bg-brand-teal text-white',
              'bg-brand-purple text-white',
              'bg-white text-brand-ink',
            ]
            return (
              <a
                key={item.id}
                href={item.href}
                target="_blank"
                rel="noopener noreferrer"
                aria-label={t.footer[item.id]}
                className={`social-icon flex h-11 w-11 items-center justify-center rounded-full shadow-sm transition hover:scale-105 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-ink ${colors[index % colors.length]}`}
              >
                <Icon size={18} />
              </a>
            )
          })}
        </nav>
      </div>
    </footer>
  )
}
