import { useSyncExternalStore } from 'react'
import { useAuth } from './context'

export function useAuthState() {
  const session = useAuth()
  return useSyncExternalStore(session.subscribe, session.getSnapshot)
}
