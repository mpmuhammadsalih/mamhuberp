export type GeoPermission = 'granted' | 'denied' | 'prompt' | 'unknown'

export async function geolocationPermissionState(): Promise<GeoPermission> {
  try {
    const permissions = navigator.permissions
    if (!permissions?.query) return 'unknown'
    const status = await permissions.query({ name: 'geolocation' })
    if (status.state === 'granted' || status.state === 'denied' || status.state === 'prompt') {
      return status.state
    }
    return 'unknown'
  } catch {
    return 'unknown'
  }
}

export function isGeolocationDenied(error?: GeolocationPositionError | Error | null): boolean {
  if (!error) return false
  if ('code' in error && typeof error.code === 'number') {
    return error.code === 1
  }
  return /denied|permission/i.test(error.message || '')
}

export function watchGeolocationPermission(onChange: (state: GeoPermission) => void): () => void {
  let cancelled = false
  let status: PermissionStatus | null = null
  const handleChange = () => {
    if (!status || cancelled) return
    if (status.state === 'granted' || status.state === 'denied' || status.state === 'prompt') {
      onChange(status.state)
    }
  }
  void (async () => {
    const state = await geolocationPermissionState()
    if (!cancelled) onChange(state)
    try {
      const permissions = navigator.permissions
      if (!permissions?.query) return
      status = await permissions.query({ name: 'geolocation' })
      status.addEventListener('change', handleChange)
    } catch {
      /* Safari and some WebViews do not expose geolocation permission status. */
    }
  })()
  return () => {
    cancelled = true
    status?.removeEventListener('change', handleChange)
  }
}

export function getBrowserCoordinates(
  options: PositionOptions = {
    enableHighAccuracy: false,
    timeout: 12_000,
    maximumAge: 60_000,
  },
): Promise<{ lat: number; lng: number }> {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error('unsupported'))
      return
    }
    if (!window.isSecureContext) {
      reject(new Error('insecure'))
      return
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
      (error) => reject(error),
      options,
    )
  })
}
