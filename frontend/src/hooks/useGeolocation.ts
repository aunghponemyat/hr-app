import { useEffect, useState } from 'react'
import { UserFacingError } from '../api/errors'

export function useGeolocation() {
  const [permission, setPermission] = useState<PermissionState | 'unknown'>(
    'unknown',
  )
  useEffect(() => {
    let active = true,
      status: PermissionStatus | undefined
    const update = () => {
      if (active && status) setPermission(status.state)
    }
    if (navigator.permissions?.query) {
      void navigator.permissions
        .query({ name: 'geolocation' })
        .then((result) => {
          if (!active) return
          status = result
          update()
          status.addEventListener?.('change', update)
        })
        .catch(() => undefined)
    }
    return () => {
      active = false
      status?.removeEventListener?.('change', update)
    }
  }, [])
  function locate(): Promise<{
    latitude: number
    longitude: number
    accuracy_m: number
  }> {
    if (!window.isSecureContext)
      return Promise.reject(
        new UserFacingError(
          'Location requires HTTPS or localhost. Open this app using a secure connection.',
        ),
      )
    if (!navigator.geolocation)
      return Promise.reject(
        new UserFacingError(
          'Your browser does not support location. Use a browser with location services enabled.',
        ),
      )
    return new Promise((resolve, reject) =>
      navigator.geolocation.getCurrentPosition(
        ({ coords }) =>
          resolve({
            latitude: coords.latitude,
            longitude: coords.longitude,
            accuracy_m: coords.accuracy,
          }),
        (error) =>
          reject(
            new UserFacingError(
              error.code === 1
                ? 'Location permission was denied. Open this site’s settings using the address-bar lock or site icon, allow Location, and enable location services on your phone or computer. Then try again.'
                : error.code === 3
                  ? 'Location timed out. Move near a window or outdoors and try again.'
                  : 'Location is unavailable. Check your device location services and try again.',
            ),
          ),
        { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 },
      ),
    )
  }
  return { permission, locate }
}
