import { useCallback } from 'react'
import { formatMoney } from '../lib/currency'
import { useLocale } from './LocaleContext'

export function useFormatMoney() {
  const { locale } = useLocale()

  return useCallback(
    (amount: number, currency?: string) => formatMoney(amount, currency, locale),
    [locale],
  )
}
