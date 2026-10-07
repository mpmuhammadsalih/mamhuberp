import { useCallback, useEffect, useState } from 'react'
import { DOHA_CENTER } from './constants'
import { DeliveryMap } from './DeliveryMap'
import { IconLocate } from '../icons/Icons'
import { useDeliveryLocation } from '../../context/DeliveryLocationContext'
import { useLocale } from '../../i18n/LocaleContext'
import { LocationPermissionBanner } from './LocationPermissionBanner'
import { fallbackDeliveryLocation, mapEstimateToLocation } from '../../lib/deliveryStorage'
import {
  geolocationPermissionState,
  isGeolocationDenied,
  watchGeolocationPermission,
} from '../../lib/browserGeolocation'
import { fetchDeliveryEstimate, isRequestAborted, searchPlaces } from '../../lib/geocoding'
import type { DeliveryLocation, GeocodeResult } from '../../types/delivery'

interface AddressMapPickerProps {
  latitude?: number | null
  longitude?: number | null
  onResolved: (location: DeliveryLocation) => void
}

export function AddressMapPicker({ latitude, longitude, onResolved }: AddressMapPickerProps) {
  const { locale, t } = useLocale()
  const { location } = useDeliveryLocation()
  const [query, setQuery] = useState('')
  const [suggestions, setSuggestions] = useState<GeocodeResult[]>([])
  const [searchHint, setSearchHint] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [locationBlocked, setLocationBlocked] = useState(false)
  const [pin, setPin] = useState({
    lat: latitude ?? location?.latitude ?? DOHA_CENTER[0],
    lng: longitude ?? location?.longitude ?? DOHA_CENTER[1],
  })

  const updatePin = useCallback(
    async (lat: number, lng: number) => {
      setPin({ lat, lng })
      setError('')
      setLoading(true)
      try {
        const estimate = await fetchDeliveryEstimate(lat, lng, undefined, locale)
        if (!estimate) throw new Error('empty estimate')
        onResolved(mapEstimateToLocation(estimate))
      } catch {
        onResolved(fallbackDeliveryLocation(lat, lng, locale))
      } finally {
        setLoading(false)
      }
    },
    [locale, onResolved],
  )

  useEffect(() => {
    if (latitude != null && longitude != null) return
    if (location) {
      void updatePin(location.latitude, location.longitude)
      return
    }
    const timer = window.setTimeout(async () => {
      const permission = await geolocationPermissionState()
      if (permission === 'denied') {
        setLocationBlocked(true)
        return
      }
      useMyLocation()
    }, 0)
    return () => window.clearTimeout(timer)
    // Resolve once when the form map mounts.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (query.trim().length < 2) {
      setSuggestions([])
      setSearchHint('')
      return
    }
    const controller = new AbortController()
    const timer = window.setTimeout(async () => {
      try {
        const results = await searchPlaces(query, controller.signal, locale)
        const rows = Array.isArray(results) ? results : []
        setSuggestions(rows)
        setSearchHint(rows.length ? '' : t.delivery.noSearchResults)
      } catch (searchError) {
        if (isRequestAborted(searchError)) return
        setSuggestions([])
        setSearchHint(t.delivery.errSearchFailed)
      }
    }, 350)
    return () => {
      controller.abort()
      window.clearTimeout(timer)
    }
  }, [query, locale, t.delivery.errSearchFailed, t.delivery.noSearchResults])

  function geolocationMessage(geoError?: GeolocationPositionError) {
    if (!window.isSecureContext) return t.delivery.errGeolocationInsecure
    if (!geoError) return t.delivery.errGeolocationDenied
    if (geoError.code === geoError.TIMEOUT) return t.delivery.errGeolocationTimeout
    if (geoError.code === geoError.POSITION_UNAVAILABLE) return t.delivery.errGeolocationUnavailable
    return t.delivery.errGeolocationDenied
  }

  const useMyLocation = useCallback(() => {
    if (!navigator.geolocation) {
      setError(t.delivery.errGeolocationUnsupported)
      return
    }
    if (!window.isSecureContext) {
      setError(t.delivery.errGeolocationInsecure)
      return
    }
    setError('')
    setLoading(true)
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        setLocationBlocked(false)
        await updatePin(pos.coords.latitude, pos.coords.longitude)
      },
      (geoError) => {
        const blocked = isGeolocationDenied(geoError)
        setLocationBlocked(blocked)
        setError(blocked ? '' : geolocationMessage(geoError))
        setLoading(false)
      },
      { enableHighAccuracy: false, timeout: 10_000, maximumAge: 60_000 },
    )
  }, [t.delivery.errGeolocationInsecure, t.delivery.errGeolocationUnsupported, updatePin])

  useEffect(() => {
    return watchGeolocationPermission((state) => {
      if (state === 'denied') {
        if (latitude == null && longitude == null && !location) setLocationBlocked(true)
        return
      }
      if (state === 'granted' && locationBlocked) {
        useMyLocation()
      }
    })
  }, [latitude, location, locationBlocked, longitude, useMyLocation])

  return (
    <fieldset className="space-y-3 rounded-2xl border border-pink-100 bg-pink-50/40 p-3 sm:p-4">
      <legend className="px-1 text-sm font-semibold text-slate-800">{t.delivery.selectLocation}</legend>
      <p className="text-xs text-slate-500">{t.account.mapFillHint}</p>

      <div className="relative">
        <label htmlFor="address-map-search" className="mb-1.5 block text-xs font-semibold text-slate-600">
          {t.delivery.location}
        </label>
        <input
          id="address-map-search"
          name="address-map-search"
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t.delivery.searchPlaceholder}
          autoComplete="off"
          className="w-full rounded-xl border border-gray-200 bg-white px-4 py-3 text-base outline-none focus-visible:border-brand-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-accent"
        />
        {suggestions.length > 0 && (
          <ul className="absolute inset-x-0 top-full z-20 mt-1 max-h-40 overflow-y-auto rounded-xl border border-gray-100 bg-white shadow-lg">
            {suggestions.map((item) => (
              <li key={`${item.latitude}-${item.longitude}-${item.label}`}>
                <button
                  type="button"
                  onClick={() => {
                    setQuery(item.label)
                    setSuggestions([])
                    void updatePin(item.latitude, item.longitude)
                  }}
                  className="w-full px-4 py-3 text-start text-sm text-slate-700 hover:bg-pink-50"
                >
                  {item.label}
                </button>
              </li>
            ))}
          </ul>
        )}
        {searchHint && suggestions.length === 0 && (
          <p className="mt-2 text-sm text-slate-500">{searchHint}</p>
        )}
      </div>

      <div className="relative z-0 isolate h-64 min-h-64 overflow-hidden rounded-xl">
        <DeliveryMap
          latitude={pin.lat}
          longitude={pin.lng}
          locale={locale}
          onPositionChange={(lat, lng) => void updatePin(lat, lng)}
        />
        <button
          type="button"
          onClick={useMyLocation}
          className="absolute bottom-3 end-3 z-10 flex h-11 w-11 items-center justify-center rounded-full bg-white shadow-lg ring-1 ring-black/5 hover:bg-gray-50"
          aria-label={t.delivery.useMyLocation}
        >
          <IconLocate size={20} className="text-slate-700" />
        </button>
      </div>

      <p className="text-xs text-slate-500" aria-live="polite">
        {loading ? t.delivery.findingAddress : t.delivery.movePin}
      </p>
      <LocationPermissionBanner visible={locationBlocked} t={t} onAllow={useMyLocation} />
      {error && <p className="text-sm text-red-600">{error}</p>}
    </fieldset>
  )
}
