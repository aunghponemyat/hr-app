import { useEffect, useRef } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/context'
import { useAuthState } from '../auth/useAuthState'
import { navigation } from './navigation'

export function Layout() {
  const session = useAuth()
  const { profile, busy, error } = useAuthState()
  const { pathname } = useLocation()
  const main = useRef<HTMLElement>(null)
  useEffect(() => {
    main.current?.focus()
  }, [pathname])
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <header className="app-header">
        <Link className="brand" to="/">
          HR &amp; Attendance
        </Link>
        <div className="account">
          <span>
            {profile?.display_name ||
              `${profile?.first_name} ${profile?.last_name}`}{' '}
            <span className="muted small">{profile?.employee_id}</span>
          </span>
          <button
            className="secondary"
            disabled={busy}
            onClick={() => {
              void session.logout().catch(() => undefined)
            }}
          >
            {busy ? 'Please wait…' : 'Sign out'}
          </button>
        </div>
      </header>
      <div className="app-body">
        <nav className="app-nav" aria-label="Main navigation">
          {profile?.must_change_password ? (
            <span className="muted">Password change required</span>
          ) : (
            navigation
              .filter((item) =>
                item.permissions.some((permission) =>
                  profile?.permissions.includes(permission),
                ),
              )
              .map((item) => (
                <NavLink key={item.path} to={item.path} end={item.path === '/'}>
                  {item.label}
                </NavLink>
              ))
          )}
        </nav>
        <main
          className="app-content"
          id="main-content"
          ref={main}
          tabIndex={-1}
        >
          {error && pathname !== '/change-password' && (
            <p className="error-banner" role="alert">
              {error}
            </p>
          )}
          <Outlet />
        </main>
      </div>
    </div>
  )
}
