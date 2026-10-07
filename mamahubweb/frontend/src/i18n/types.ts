import type { en } from './translations/en'

export type SupportedLocale = 'en' | 'ar'

type DeepStringify<T> = {
  [K in keyof T]: T[K] extends string ? string : T[K] extends object ? DeepStringify<T[K]> : T[K]
}

export type TranslationTree = DeepStringify<typeof en>

export type TranslationKey = keyof TranslationTree
