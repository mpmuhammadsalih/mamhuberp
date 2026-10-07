import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { ar } from './translations/ar'
import { en } from './translations/en'
import type { SupportedLocale, TranslationTree } from './types'

const STORAGE_KEY = 'mamahub_locale'

const catalogs: Record<SupportedLocale, TranslationTree> = { en, ar }

function readStoredLocale(): SupportedLocale {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'ar' || stored === 'en') return stored
  } catch {
    /* ignore */
  }
  return 'en'
}

function applyDocumentLocale(locale: SupportedLocale) {
  document.documentElement.lang = locale
  document.documentElement.dir = locale === 'ar' ? 'rtl' : 'ltr'
}

interface LocaleContextValue {
  locale: SupportedLocale
  setLocale: (locale: SupportedLocale) => void
  t: TranslationTree
  isRtl: boolean
}

const LocaleContext = createContext<LocaleContextValue | null>(null)

export function LocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<SupportedLocale>(() => readStoredLocale())

  const setLocale = useCallback((next: SupportedLocale) => {
    setLocaleState(next)
    try {
      localStorage.setItem(STORAGE_KEY, next)
    } catch {
      /* ignore */
    }
    applyDocumentLocale(next)
  }, [])

  useEffect(() => {
    applyDocumentLocale(locale)
  }, [locale])

  const value = useMemo(
    () => ({
      locale,
      setLocale,
      t: catalogs[locale],
      isRtl: locale === 'ar',
    }),
    [locale, setLocale],
  )

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>
}

export function useLocale() {
  const ctx = useContext(LocaleContext)
  if (!ctx) throw new Error('useLocale must be used within LocaleProvider')
  return ctx
}
