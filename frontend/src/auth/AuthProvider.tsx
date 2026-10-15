import { QueryClientProvider } from '@tanstack/react-query'
import { useEffect } from 'react'
import type { ReactNode } from 'react'
import { AuthContext } from './context'
import type { AuthSession } from './session'

export function AuthProvider({
  session,
  children,
}: {
  session: AuthSession
  children: ReactNode
}) {
  useEffect(() => {
    void session.restore()
  }, [session])

  return (
    <QueryClientProvider client={session.queryClient}>
      <AuthContext.Provider value={session}>{children}</AuthContext.Provider>
    </QueryClientProvider>
  )
}
