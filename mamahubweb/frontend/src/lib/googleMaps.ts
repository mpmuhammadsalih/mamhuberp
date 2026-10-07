import type { SupportedLocale } from '../i18n/types'

declare global {
  interface Window {
    google?: {
      maps?: {
        Map: new (el: HTMLElement, opts: Record<string, unknown>) => GoogleMapInstance
        Marker: new (opts: Record<string, unknown>) => GoogleMarkerInstance
        event: { addListener: (instance: object, name: string, handler: () => void) => void }
      }
    }
    __mamahubGoogleMapsLanguage?: string
  }
}

interface GoogleMapInstance {
  setCenter: (pos: { lat: number; lng: number }) => void
  setZoom: (zoom: number) => void
  panTo: (pos: { lat: number; lng: number }) => void
}

interface GoogleMarkerInstance {
  setPosition: (pos: { lat: number; lng: number }) => void
  getPosition: () => { lat: () => number; lng: () => number } | null
}

export function mapsLanguage(locale: SupportedLocale | string) {
  return locale === 'ar' ? 'ar' : 'en'
}

export function googleMapsKey() {
  return String(import.meta.env.VITE_GOOGLE_MAPS_API_KEY ?? '').trim()
}

export function googleTileUrl(locale: SupportedLocale | string) {
  return `https://mt1.google.com/vt/lyrs=m&hl=${mapsLanguage(locale)}&x={x}&y={y}&z={z}`
}

export function loadGoogleMapsScript(locale: SupportedLocale | string): Promise<void> {
  const key = googleMapsKey()
  const language = mapsLanguage(locale)
  if (!key) return Promise.reject(new Error('Missing VITE_GOOGLE_MAPS_API_KEY'))

  if (window.google?.maps && window.__mamahubGoogleMapsLanguage === language) {
    return Promise.resolve()
  }

  document.querySelectorAll('script[data-google-maps="1"]').forEach((node) => node.remove())
  delete window.google
  window.__mamahubGoogleMapsLanguage = language

  return new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.dataset.googleMaps = '1'
    script.dataset.language = language
    script.async = true
    script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(key)}&language=${language}&region=QA`
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('Google Maps failed to load'))
    document.head.appendChild(script)
  })
}
