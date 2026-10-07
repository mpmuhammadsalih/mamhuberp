import { getData } from './api'
import type { DeliveryEstimate, GeocodeResult } from '../types/delivery'
import type { SupportedLocale } from '../i18n/types'

function localeParam(lang?: SupportedLocale | string) {
  return lang === 'ar' ? 'ar' : 'en'
}

export async function searchPlaces(
  query: string,
  signal?: AbortSignal,
  lang?: SupportedLocale | string,
) {
  return getData<GeocodeResult[]>(
    '/delivery/geocode/search',
    { q: query, lang: localeParam(lang) },
    { signal },
  )
}

export async function reverseGeocode(
  lat: number,
  lng: number,
  signal?: AbortSignal,
  lang?: SupportedLocale | string,
) {
  return getData<DeliveryEstimate>(
    '/delivery/geocode/reverse',
    { lat, lng, lang: localeParam(lang) },
    { signal },
  )
}

export async function fetchDeliveryEstimate(
  lat: number,
  lng: number,
  signal?: AbortSignal,
  lang?: SupportedLocale | string,
) {
  return getData<DeliveryEstimate>(
    '/delivery/estimate',
    { lat, lng, lang: localeParam(lang) },
    { signal },
  )
}

export function isRequestAborted(error: unknown) {
  if (!error || typeof error !== 'object') return false
  const code = 'code' in error ? String((error as { code?: string }).code) : ''
  const name = 'name' in error ? String((error as { name?: string }).name) : ''
  return code === 'ERR_CANCELED' || name === 'CanceledError' || name === 'AbortError'
}
