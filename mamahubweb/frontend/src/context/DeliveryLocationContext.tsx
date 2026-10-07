import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import type { DeliveryLocation } from '../types/delivery'
import { useLocale } from '../i18n/LocaleContext'
import { persistDeliveryLocationToAccount } from '../lib/accountAddress'
import { fetchDeliveryEstimate } from '../lib/geocoding'
import {
  clearDeliveryLocation,
  fallbackDeliveryLocation,
  loadDeliveryLocation,
  mapEstimateToLocation,
  saveDeliveryLocation,
} from '../lib/deliveryStorage'
import { queryClient } from '../lib/queryClient'

interface DeliveryLocationContextValue {
  location: DeliveryLocation | null
  pickerOpen: boolean
  openPicker: () => void
  closePicker: () => void
  saveLocation: (location: DeliveryLocation) => void
  clearLocation: () => void
  resolveCoordinates: (lat: number, lng: number) => Promise<DeliveryLocation>
}

const DeliveryLocationContext = createContext<DeliveryLocationContextValue | null>(null)

export function DeliveryLocationProvider({ children }: { children: ReactNode }) {
  const { locale } = useLocale()
  const [location, setLocation] = useState<DeliveryLocation | null>(() => loadDeliveryLocation())
  const [pickerOpen, setPickerOpen] = useState(false)
  const locationRef = useRef(location)
  locationRef.current = location

  const resolveCoordinates = useCallback(async (lat: number, lng: number) => {
    try {
      const estimate = await fetchDeliveryEstimate(lat, lng, undefined, locale)
      return mapEstimateToLocation(estimate)
    } catch {
      return fallbackDeliveryLocation(lat, lng, locale)
    }
  }, [locale])

  useEffect(() => {
    const current = locationRef.current
    if (!current) return
    let cancelled = false
    void fetchDeliveryEstimate(current.latitude, current.longitude, undefined, locale)
      .then((estimate) => {
        if (cancelled) return
        const next = mapEstimateToLocation(estimate)
        saveDeliveryLocation(next)
        setLocation(next)
      })
      .catch(() => {
        /* Keep the stored label if refresh fails. */
      })
    return () => {
      cancelled = true
    }
  }, [locale])

  const saveLocation = useCallback((next: DeliveryLocation) => {
    saveDeliveryLocation(next)
    setLocation(next)
    setPickerOpen(false)
    void persistDeliveryLocationToAccount(next)
      .then(() => {
        void queryClient.invalidateQueries({ queryKey: ['addresses'] })
      })
      .catch(() => {
        /* Addresses page can retry if the account save fails. */
      })
  }, [])

  const clearLocation = useCallback(() => {
    clearDeliveryLocation()
    setLocation(null)
  }, [])

  const value = useMemo(
    () => ({
      location,
      pickerOpen,
      openPicker: () => setPickerOpen(true),
      closePicker: () => setPickerOpen(false),
      saveLocation,
      clearLocation,
      resolveCoordinates,
    }),
    [location, pickerOpen, saveLocation, clearLocation, resolveCoordinates],
  )

  return (
    <DeliveryLocationContext.Provider value={value}>{children}</DeliveryLocationContext.Provider>
  )
}

export function useDeliveryLocation() {
  const ctx = useContext(DeliveryLocationContext)
  if (!ctx) throw new Error('useDeliveryLocation must be used within DeliveryLocationProvider')
  return ctx
}
