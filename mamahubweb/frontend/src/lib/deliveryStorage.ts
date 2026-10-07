import type { DeliveryLocation } from '../types/delivery'

const KEY = 'mamahub_delivery_location'

export const DEFAULT_ETA_MIN = 60
export const DEFAULT_ETA_MAX = 75

export function loadDeliveryLocation(): DeliveryLocation | null {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return null
    return JSON.parse(raw) as DeliveryLocation
  } catch {
    return null
  }
}

export function saveDeliveryLocation(location: DeliveryLocation): void {
  localStorage.setItem(KEY, JSON.stringify(location))
}

export function clearDeliveryLocation(): void {
  localStorage.removeItem(KEY)
}

export function fallbackDeliveryLocation(
  lat: number,
  lng: number,
  locale: string = 'en',
): DeliveryLocation {
  const arabic = locale === 'ar'
  const city = arabic ? 'الدوحة' : 'Doha'
  const area = arabic ? 'موقع محدد' : 'Selected location'
  return {
    latitude: lat,
    longitude: lng,
    areaLabel: area,
    city,
    street: area,
    country: arabic ? 'قطر' : 'Qatar',
    fullLabel: `${area}, ${city}`,
    etaMinMinutes: 60,
    etaMaxMinutes: 75,
  }
}

export function mapEstimateToLocation(data: {
  latitude: number
  longitude: number
  area_label: string
  city: string
  street: string
  country: string
  full_label: string
  delivery_zone_id?: number | null
  zone_name?: string | null
  delivery_fee?: number
  eta_min_minutes: number
  eta_max_minutes: number
}): DeliveryLocation {
  return {
    latitude: data.latitude,
    longitude: data.longitude,
    areaLabel: data.area_label,
    city: data.city,
    street: data.street,
    country: data.country,
    fullLabel: data.full_label,
    deliveryZoneId: data.delivery_zone_id,
    zoneName: data.zone_name,
    deliveryFee: data.delivery_fee,
    etaMinMinutes: data.eta_min_minutes,
    etaMaxMinutes: data.eta_max_minutes,
  }
}
