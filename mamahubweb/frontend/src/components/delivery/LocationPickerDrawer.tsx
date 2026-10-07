import { useCallback, useEffect, useState } from 'react'
import { DOHA_CENTER } from './constants'
import { DeliveryMap } from './DeliveryMap'
import { IconClose, IconLocate } from '../icons/Icons'
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

export function LocationPickerDrawer() {
  const { locale, t } = useLocale()
  const { pickerOpen, closePicker, saveLocation, location } = useDeliveryLocation()

  const [query, setQuery] = useState('')
  const [suggestions, setSuggestions] = useState<GeocodeResult[]>([])
  const [pin, setPin] = useState<{ lat: number; lng: number }>({
    lat: location?.latitude ?? DOHA_CENTER[0],
    lng: location?.longitude ?? DOHA_CENTER[1],
  })
  const [draft, setDraft] = useState<DeliveryLocation | null>(location)
  const [error, setError] = useState('')
  const [searchHint, setSearchHint] = useState('')
  const [loading, setLoading] = useState(false)
  const [pinMoved, setPinMoved] = useState(Boolean(location))
  const [locationBlocked, setLocationBlocked] = useState(false)

  const updatePin = useCallback(async (lat: number, lng: number) => {
    setPin({ lat, lng })
    setPinMoved(true)
    setError('')
    setLoading(true)
    try {
      const estimate = await fetchDeliveryEstimate(lat, lng, undefined, locale)
      if (!estimate) throw new Error('empty estimate')
      setDraft(mapEstimateToLocation(estimate))
    } catch {
      setDraft(fallbackDeliveryLocation(lat, lng, locale))
    } finally {
      setLoading(false)
    }
  }, [locale])

  useEffect(() => {
    if (!pickerOpen) return
    setDraft(location)
    setPin({
      lat: location?.latitude ?? DOHA_CENTER[0],
      lng: location?.longitude ?? DOHA_CENTER[1],
    })
    setPinMoved(Boolean(location))
    setError('')
    setLocationBlocked(false)
    setQuery('')
    setSuggestions([])
    setSearchHint('')
    let timer = 0
    if (!location) {
      timer = window.setTimeout(async () => {
        const permission = await geolocationPermissionState()
        if (permission === 'denied') {
          setLocationBlocked(true)
          return
        }
        useMyLocation()
      }, 0)
    }
    return () => window.clearTimeout(timer)
    // Reset only when the drawer opens so a language refresh does not clear search.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- location/updatePin are read at open time
  }, [pickerOpen])

  useEffect(() => {
    if (!pickerOpen || !pinMoved) return
    void updatePin(pin.lat, pin.lng)
  }, [locale]) // re-label the current pin when the shop language changes

  useEffect(() => {
    if (!pickerOpen || query.trim().length < 2) {
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
      } catch (error) {
        if (isRequestAborted(error)) return
        setSuggestions([])
        setSearchHint(t.delivery.errSearchFailed)
      }
    }, 350)
    return () => {
      controller.abort()
      window.clearTimeout(timer)
    }
  }, [query, pickerOpen, locale, t.delivery.errSearchFailed, t.delivery.noSearchResults])

  function geolocationMessage(error?: GeolocationPositionError) {
    if (!window.isSecureContext) return t.delivery.errGeolocationInsecure
    if (!error) return t.delivery.errGeolocationDenied
    if (error.code === error.TIMEOUT) return t.delivery.errGeolocationTimeout
    if (error.code === error.POSITION_UNAVAILABLE) return t.delivery.errGeolocationUnavailable
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
        setLoading(false)
      },
      (error) => {
        const blocked = isGeolocationDenied(error)
        setLocationBlocked(blocked)
        setError(blocked ? '' : geolocationMessage(error))
        setLoading(false)
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 60_000 },
    )
  }, [t.delivery.errGeolocationInsecure, t.delivery.errGeolocationUnsupported, updatePin])

  useEffect(() => {
    if (!pickerOpen) return
    return watchGeolocationPermission((state) => {
      if (state === 'denied') {
        if (!location) setLocationBlocked(true)
        return
      }
      if (state === 'granted' && locationBlocked) {
        useMyLocation()
      }
    })
  }, [location, locationBlocked, pickerOpen, useMyLocation])

  async function selectSuggestion(item: GeocodeResult) {
    setQuery(item.label)
    setSuggestions([])
    await updatePin(item.latitude, item.longitude)
  }

  function handleSave() {
    if (!pinMoved || !draft) {
      setError(t.delivery.errSelectLocation)
      return
    }
    saveLocation(draft)
  }

  if (!pickerOpen) return null

  return (
    <>
      <button
        type="button"
        aria-label={t.delivery.closePicker}
        className="fixed inset-0 z-[70] bg-black/40"
        onClick={closePicker}
      />

      <aside className="fixed inset-x-0 bottom-0 z-[80] flex h-[92dvh] max-h-dvh w-full flex-col overflow-hidden rounded-t-2xl bg-white shadow-2xl sm:inset-y-0 sm:start-auto sm:end-0 sm:h-dvh sm:max-w-md sm:rounded-none lg:max-w-lg">
        <div className="flex shrink-0 items-center justify-between border-b border-gray-200 px-4 py-3 sm:px-5 sm:py-4">
          <h2 className="text-lg font-bold text-slate-800">{t.delivery.selectLocation}</h2>
          <button
            type="button"
            onClick={closePicker}
            className="flex h-9 w-9 items-center justify-center rounded-full text-slate-500 hover:bg-gray-100"
            aria-label={t.delivery.close}
          >
            <IconClose size={20} />
          </button>
        </div>

        <div className="relative z-20 shrink-0 border-b border-gray-100 px-4 py-3 sm:px-5 sm:py-4">
          <label className="mb-2 block text-xs font-semibold uppercase tracking-wide text-slate-500">
            {t.delivery.location}
          </label>
          <div className="relative">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t.delivery.searchPlaceholder}
              className="w-full rounded-xl border border-gray-200 px-4 py-3 pe-16 text-sm outline-none focus:border-brand-accent focus:ring-2 focus:ring-pink-100"
            />
            {query && (
              <button
                type="button"
                onClick={() => {
                  setQuery('')
                  setSuggestions([])
                  setSearchHint('')
                }}
                className="absolute end-3 top-1/2 -translate-y-1/2 text-xs font-semibold text-brand-accent"
              >
                {t.delivery.clear}
              </button>
            )}
          </div>

          {suggestions.length > 0 && (
            <ul className="absolute inset-x-4 top-full z-30 mt-1 max-h-40 overflow-y-auto rounded-xl border border-gray-100 bg-white shadow-lg sm:inset-x-5">
              {suggestions.map((item) => (
                <li key={`${item.latitude}-${item.longitude}-${item.label}`}>
                  <button
                    type="button"
                    onClick={() => void selectSuggestion(item)}
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

        <div className="relative min-h-0 flex-1 px-4 py-3 sm:px-5 sm:py-4">
          <div className="pointer-events-none absolute inset-x-6 top-6 z-10 mx-auto max-w-[260px] rounded-xl bg-white px-3 py-2 text-center text-xs font-medium text-slate-700 shadow-lg ring-1 ring-black/5 sm:top-8 sm:px-4 sm:py-3">
            {t.delivery.mapHint}
            <br />
            {t.delivery.movePin}
          </div>

          <div className="h-full min-h-0">
            <DeliveryMap
              latitude={pin.lat}
              longitude={pin.lng}
              locale={locale}
              onPositionChange={(lat, lng) => void updatePin(lat, lng)}
            />
          </div>

          <button
            type="button"
            onClick={useMyLocation}
            className="absolute bottom-6 end-6 z-10 flex h-11 w-11 items-center justify-center rounded-full bg-white shadow-lg ring-1 ring-black/5 hover:bg-gray-50 sm:bottom-8 sm:end-8"
            aria-label={t.delivery.useMyLocation}
          >
            <IconLocate size={20} className="text-slate-700" />
          </button>
        </div>

        <div className="shrink-0 border-t border-gray-200 bg-white px-4 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] sm:px-5 sm:py-4">
          {draft && pinMoved && (
            <p className="mb-2 truncate text-sm font-semibold text-slate-800 sm:mb-3">
              {draft.areaLabel}, {draft.city}
            </p>
          )}
          <LocationPermissionBanner visible={locationBlocked} t={t} onAllow={useMyLocation} />
          {error && <p className="mb-2 text-sm text-red-500 sm:mb-3">{error}</p>}
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between sm:gap-3">
            <p className="text-xs text-slate-500">
              {loading ? t.delivery.findingAddress : pinMoved ? t.delivery.tapSave : ''}
            </p>
            <button
              type="button"
              disabled={!pinMoved || !draft || loading}
              onClick={handleSave}
              className="w-full rounded-full bg-brand-accent px-8 py-3 text-sm font-bold text-white shadow-sm transition hover:bg-brand-accent-hover disabled:cursor-not-allowed disabled:bg-pink-200 sm:w-auto"
            >
              {t.delivery.save}
            </button>
          </div>
        </div>
      </aside>
    </>
  )
}
