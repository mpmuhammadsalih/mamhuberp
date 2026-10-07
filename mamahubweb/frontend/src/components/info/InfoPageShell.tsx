import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useLocale } from '../../i18n/LocaleContext'
import { PAGE_CONTAINER } from '../layout/homeLayout'

interface Props {
  title: string
  subtitle?: string
  children: ReactNode
}

export function InfoPageShell({ title, subtitle, children }: Props) {
  const { t } = useLocale()

  return (
    <div className="pb-16">
      <div className="border-b border-brand-border/60 bg-gradient-to-br from-brand-tint via-brand-cream to-brand-cream-alt">
        <div className={`${PAGE_CONTAINER} py-10 lg:py-12`}>
          <nav className="mb-4 text-sm text-brand-sage">
            <Link to="/" className="hover:text-brand-tan-dark">
              {t.shared.home}
            </Link>
            <span className="mx-2">/</span>
            <span className="text-brand-cocoa">{title}</span>
          </nav>
          <h1 className="text-3xl font-extrabold tracking-tight text-brand-ink sm:text-4xl">{title}</h1>
          {subtitle ? <p className="mt-3 max-w-2xl text-base text-brand-sage">{subtitle}</p> : null}
        </div>
      </div>
      <div className={`${PAGE_CONTAINER} py-10 lg:py-12`}>{children}</div>
    </div>
  )
}
