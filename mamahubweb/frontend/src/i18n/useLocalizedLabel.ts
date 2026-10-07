import { useLocale } from './LocaleContext'
import { toTitleCase } from '../lib/textCase'

/** Format labels for display — skip English title case in Arabic. */
export function useLocalizedLabel() {
  const { locale } = useLocale()
  return (label: string) => (locale === 'ar' ? label : toTitleCase(label))
}
