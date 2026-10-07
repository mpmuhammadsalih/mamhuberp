import { useEffect, useRef, useState } from 'react'
import { useLocale } from '../../i18n/LocaleContext'
import type { SupportedLocale } from '../../i18n/types'
import { IconChevronDown } from '../icons/Icons'

const options: Array<{ value: SupportedLocale; label: string; short: string }> = [
  { value: 'en', label: 'English', short: 'EN' },
  { value: 'ar', label: 'العربية', short: 'ع' },
]

interface Props {
  className?: string
  variant?: 'pills' | 'menu'
  tone?: 'default' | 'onDark'
}

export function LanguageSwitcher({ className = '', variant = 'pills', tone = 'default' }: Props) {
  const { locale, setLocale, t } = useLocale()
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const active = options.find((option) => option.value === locale) ?? options[0]

  useEffect(() => {
    if (!open) return undefined

    function onPointerDown(event: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false)
      }
    }

    function onEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false)
    }

    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onEscape)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onEscape)
    }
  }, [open])

  if (variant === 'menu') {
    return (
      <div className={`relative z-[90] ${className}`} ref={rootRef}>
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          className={`inline-flex items-center gap-1 text-[13px] font-medium transition ${
            tone === 'onDark' ? 'text-white hover:text-white/80' : 'text-slate-700 hover:text-brand-accent'
          }`}
          aria-expanded={open}
          aria-haspopup="listbox"
          aria-label={t.language.label}
        >
          <span>{active.label}</span>
          <IconChevronDown
            size={14}
            className={`transition ${open ? 'rotate-180' : ''} ${tone === 'onDark' ? 'text-white/80' : 'text-slate-400'}`}
          />
        </button>
        {open ? (
          <ul
            role="listbox"
            className="absolute end-0 top-full z-[90] mt-1.5 min-w-[9rem] overflow-visible rounded-xl bg-white py-1 shadow-[0_12px_32px_rgba(15,23,42,0.18)] ring-1 ring-black/10"
          >
            {options.map((option) => (
              <li key={option.value} role="option" aria-selected={locale === option.value}>
                <button
                  type="button"
                  onClick={() => {
                    setLocale(option.value)
                    setOpen(false)
                  }}
                  className={`flex w-full px-3 py-2 text-start text-sm transition hover:bg-brand-cream-alt ${
                    locale === option.value ? 'font-semibold text-brand-accent' : 'text-slate-700'
                  }`}
                >
                  {option.label}
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    )
  }

  return (
    <div
      className={`inline-flex items-center rounded-full bg-brand-cream-alt p-0.5 ring-1 ring-brand-border/80 ${className}`}
      role="group"
      aria-label={t.language.label}
    >
      {options.map((option) => {
        const selected = locale === option.value
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => setLocale(option.value)}
            className={`min-w-[2.25rem] rounded-full px-2 py-1 text-xs font-bold transition ${
              selected ? 'bg-brand-accent text-white shadow-sm' : 'text-brand-cocoa hover:text-brand-accent'
            }`}
            aria-pressed={selected}
          >
            {option.short}
          </button>
        )
      })}
    </div>
  )
}
