import type { SupportedLocale } from '../i18n/types'

export const DEFAULT_CURRENCY = 'QAR'

const arQarFormatter = new Intl.NumberFormat('ar-QA', {
  style: 'currency',
  currency: 'QAR',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

const arNumberFormatter = new Intl.NumberFormat('ar-QA', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

export function formatMoney(
  amount: number,
  currency = DEFAULT_CURRENCY,
  locale: SupportedLocale = 'en',
): string {
  const safe = Number.isFinite(amount) ? amount : 0

  if (locale === 'ar') {
    if (currency === 'QAR') {
      return arQarFormatter.format(safe)
    }
    return `${arNumberFormatter.format(safe)} ${currency}`
  }

  return `${currency} ${safe.toFixed(2)}`
}
