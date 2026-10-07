import L from 'leaflet'
import { useEffect, useMemo, useRef } from 'react'
import { MapContainer, Marker, TileLayer, useMap, useMapEvents } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { GoogleDeliveryMap } from './GoogleDeliveryMap'
import { DOHA_CENTER } from './constants'
import { googleMapsKey, googleTileUrl } from '../../lib/googleMaps'
import type { SupportedLocale } from '../../i18n/types'

export { DOHA_CENTER }

const pinIcon = L.divIcon({
  className: '',
  html: `<div style="width:28px;height:28px;background:#e53935;border:3px solid #fff;border-radius:50% 50% 50% 0;transform:rotate(-45deg);box-shadow:0 4px 10px rgba(0,0,0,.25);margin-left:-14px;margin-top:-28px;"></div>`,
  iconSize: [28, 28],
  iconAnchor: [14, 28],
})

function MapController({
  center,
  zoom,
}: {
  center: [number, number]
  zoom: number
}) {
  const map = useMap()
  useEffect(() => {
    map.invalidateSize()
    map.setView(center, zoom, { animate: true })
  }, [map, center, zoom])
  useEffect(() => {
    const timer = window.setTimeout(() => map.invalidateSize(), 80)
    return () => window.clearTimeout(timer)
  }, [map])
  return null
}

function DraggablePin({
  position,
  onDragEnd,
}: {
  position: [number, number]
  onDragEnd: (lat: number, lng: number) => void
}) {
  const markerRef = useRef<L.Marker>(null)
  const eventHandlers = useMemo(
    () => ({
      dragend() {
        const marker = markerRef.current
        if (!marker) return
        const { lat, lng } = marker.getLatLng()
        onDragEnd(lat, lng)
      },
    }),
    [onDragEnd],
  )

  return (
    <Marker
      draggable
      position={position}
      icon={pinIcon}
      ref={markerRef}
      eventHandlers={eventHandlers}
    />
  )
}

function MapClickHandler({
  onPositionChange,
}: {
  onPositionChange: (lat: number, lng: number) => void
}) {
  useMapEvents({
    click(e) {
      onPositionChange(e.latlng.lat, e.latlng.lng)
    },
  })
  return null
}

interface Props {
  latitude: number
  longitude: number
  onPositionChange: (lat: number, lng: number) => void
  locale?: SupportedLocale
}

export function DeliveryMap({ latitude, longitude, onPositionChange, locale = 'en' }: Props) {
  const center: [number, number] = [latitude || DOHA_CENTER[0], longitude || DOHA_CENTER[1]]

  return (
    <div className="delivery-map-root relative z-0 h-full w-full isolate overflow-hidden rounded-xl ring-1 ring-gray-200">
      {googleMapsKey() ? (
        <GoogleDeliveryMap
          key={locale}
          latitude={latitude}
          longitude={longitude}
          locale={locale}
          onPositionChange={onPositionChange}
        />
      ) : (
        <MapContainer
          key={locale}
          center={center}
          zoom={15}
          scrollWheelZoom
          className="h-full w-full"
          style={{ height: '100%', minHeight: 0 }}
        >
          <TileLayer
            key={locale}
            attribution="&copy; Google"
            url={googleTileUrl(locale)}
          />
          <MapController center={center} zoom={15} />
          <DraggablePin
            key={`${center[0]}-${center[1]}`}
            position={center}
            onDragEnd={onPositionChange}
          />
          <MapClickHandler onPositionChange={onPositionChange} />
        </MapContainer>
      )}
    </div>
  )
}
