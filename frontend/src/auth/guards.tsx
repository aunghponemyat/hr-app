import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from './context'
import { useAuthState } from './useAuthState'

export function SessionGate({ children }: { children: React.ReactNode }) {
  const { status, error } = useAuthState()
  const session = useAuth()
  if (status === 'loading')
    return (
      <main className="session-screen" aria-busy="true">
        <p role="status">Restoring your session…</p>
      </main>
    )
  if (status === 'error')
    return (
      <main className="session-screen">
        <section className="card">
          <h1>Connection unavailable</h1>
          <p role="alert">{error}</p>
          <button onClick={() => void session.restore()}>Try again</button>
        </section>
      </main>
    )
  return children
}

export function RequireAuth() {
  const { profile } = useAuthState()
  const location = useLocation()
  const destination = location.pathname + location.search + location.hash
  if (!profile)
    return <Navigate to="/login" state={{ from: destination }} replace />
  if (profile.must_change_password && location.pathname !== '/change-password')
    return (
      <Navigate to="/change-password" state={{ from: destination }} replace />
    )
  return <Outlet />
}

export function RequirePermission({
  code,
}: {
  code: string | readonly string[]
}) {
  const { profile } = useAuthState()
  const codes = typeof code === 'string' ? [code] : code
  if (
    !profile ||
    !codes.some((candidate) => profile.permissions.includes(candidate))
  )
    return (
      <section className="card">
        <h1>Access denied</h1>
        <p>You do not have permission to view this page.</p>
      </section>
    )
  return <Outlet />
}
