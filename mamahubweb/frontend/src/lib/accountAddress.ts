import { getData, patchData, postData } from './api'
import { storage } from './storage'
import type { Address } from '../types/api'
import type { DeliveryLocation } from '../types/delivery'

export function deliveryLocationToAddressPayload(location: DeliveryLocation) {
  const street =
    location.street?.trim() ||
    location.fullLabel?.trim() ||
    location.areaLabel?.trim() ||
    'Selected location'
  const city = location.city?.trim() || 'Doha'
  const title = location.areaLabel?.trim() || 'Home'

  return {
    address_title: title.slice(0, 100),
    address_type: 'HOME' as const,
    street: street.slice(0, 200),
    city: city.slice(0, 100),
    country: (location.country?.trim() || 'Qatar').slice(0, 100),
    zone: location.zoneName?.slice(0, 100) || location.areaLabel?.slice(0, 100) || undefined,
    area: location.areaLabel?.slice(0, 100) || undefined,
    latitude: location.latitude,
    longitude: location.longitude,
  }
}

export function applyDeliveryLocationToForm<T extends Record<string, unknown>>(
  prev: T,
  location: DeliveryLocation,
) {
  const payload = deliveryLocationToAddressPayload(location)
  return {
    ...prev,
    street: payload.street,
    city: payload.city,
    country: payload.country,
    zone: payload.zone || '',
    area: payload.area || '',
    latitude: location.latitude,
    longitude: location.longitude,
  }
}

function samePin(
  address: { latitude?: number | null; longitude?: number | null },
  location: DeliveryLocation,
) {
  if (address.latitude == null || address.longitude == null) return false
  return (
    Math.abs(address.latitude - location.latitude) < 0.0005 &&
    Math.abs(address.longitude - location.longitude) < 0.0005
  )
}

export async function persistDeliveryLocationToAccount(
  location: DeliveryLocation,
): Promise<Address | null> {
  if (!storage.hasSession()) return null

  const payload = deliveryLocationToAddressPayload(location)
  const existing = (await getData<Address[]>('/addresses')) ?? []
  const match =
    existing.find((address) => samePin(address, location)) ??
    (existing.length === 1 && existing[0].latitude != null ? existing[0] : undefined) ??
    existing.find((address) => address.is_default && address.latitude != null)

  if (match) {
    return patchData<Address>(`/addresses/${match.address_id}`, {
      ...payload,
      is_default: match.is_default || existing.length === 1,
    })
  }

  return postData<Address>('/addresses', {
    ...payload,
    is_default: existing.length === 0,
  })
}
