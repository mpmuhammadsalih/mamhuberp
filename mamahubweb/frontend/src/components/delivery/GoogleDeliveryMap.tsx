import { useEffect, useRef } from 'react'
import { loadGoogleMapsScript } from '../../lib/googleMaps'
import type { SupportedLocale } from '../../i18n/types'
import { DOHA_CENTER } from './constants'

interface Props {
  latitude: number
  longitude: number
  onPositionChange: (lat: number, lng: number) => void
  locale: SupportedLocale
}

type LatLng = { lat: () => number; lng: () => number }

export function GoogleDeliveryMap({ latitude, longitude, onPositionChange, locale }: Props) {
  const hostRef = useRef<HTMLDivElement>(null)
  const onChangeRef = useRef(onPositionChange)
  const mapRef = useRef<{ panTo: (pos: { lat: number; lng: number }) => void } | null>(null)
  const markerRef = useRef<{ setPosition: (pos: { lat: number; lng: number }) => void } | null>(null)
  onChangeRef.current = onPositionChange

  useEffect(() => {
    const host = hostRef.current
    if (!host) return undefined
    let cancelled = false

    void loadGoogleMapsScript(locale).then(() => {
      if (cancelled || !hostRef.current || !window.google?.maps) return
      const center = {
        lat: latitude || DOHA_CENTER[0],
        lng: longitude || DOHA_CENTER[1],
      }
      const map = new window.google.maps.Map(hostRef.current, {
        center,
        zoom: 15,
        mapTypeControl: false,
        streetViewControl: false,
        fullscreenControl: false,
        clickableIcons: false,
      })
      const marker = new window.google.maps.Marker({
        position: center,
        map,
        draggable: true,
      })
      mapRef.current = map
      markerRef.current = marker
      window.google.maps.event.addListener(map, 'click', (event: { latLng?: LatLng }) => {
        const latLng = event.latLng
        if (!latLng) return
        const next = { lat: latLng.lat(), lng: latLng.lng() }
        marker.setPosition(next)
        onChangeRef.current(next.lat, next.lng)
      })
      window.google.maps.event.addListener(marker, 'dragend', () => {
        const pos = marker.getPosition?.()
        if (!pos) return
        onChangeRef.current(pos.lat(), pos.lng())
      })
    })

    return () => {
      cancelled = true
      mapRef.current = null
      markerRef.current = null
      host.replaceChildren()
    }
    // Recreate the map when language changes so Google loads language=en or language=ar.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- pin updates are handled below
  }, [locale])

  useEffect(() => {
    const pos = { lat: latitude || DOHA_CENTER[0], lng: longitude || DOHA_CENTER[1] }
    mapRef.current?.panTo(pos)
    markerRef.current?.setPosition(pos)
  }, [latitude, longitude])

  return <div ref={hostRef} className="h-full min-h-0 w-full" />
}
