import { createContext, useContext } from 'react'
import type { AuthSession } from './session'

export const AuthContext = createContext<AuthSession | null>(null)

export function useAuth() {
  const session = useContext(AuthContext)
  if (!session) throw new Error('AuthProvider is required.')
  return session
}
