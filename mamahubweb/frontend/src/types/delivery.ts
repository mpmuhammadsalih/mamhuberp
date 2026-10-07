export interface DeliveryLocation {
  latitude: number
  longitude: number
  areaLabel: string
  city: string
  street: string
  country: string
  fullLabel: string
  deliveryZoneId?: number | null
  zoneName?: string | null
  deliveryFee?: number
  etaMinMinutes: number
  etaMaxMinutes: number
}

export interface GeocodeResult {
  label: string
  latitude: number
  longitude: number
  area: string
  city: string
  street: string
  country: string
}

export interface DeliveryEstimate extends GeocodeResult {
  area_label: string
  full_label: string
  delivery_zone_id?: number | null
  zone_name?: string | null
  delivery_fee?: number
  eta_min_minutes: number
  eta_max_minutes: number
  delivery_available: boolean
}
