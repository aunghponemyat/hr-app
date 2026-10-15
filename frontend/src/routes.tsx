import { Route, Routes } from 'react-router-dom'
import { RequireAuth, RequirePermission, SessionGate } from './auth/guards'
import { Layout } from './components/Layout'
import { navigation } from './components/navigation'
import { ChangePassword } from './pages/ChangePassword'
import { Suspense, lazy } from 'react'
import { Dashboard } from './pages/Dashboard'
import { Profile } from './pages/Profile'
const Leave = lazy(() =>
  import('./pages/Leave').then((module) => ({ default: module.Leave })),
)
const Team = lazy(() =>
  import('./pages/Team').then((module) => ({ default: module.Team })),
)
const Employees = lazy(() =>
  import('./pages/admin/Employees').then((module) => ({
    default: module.Employees,
  })),
)
const Teams = lazy(() =>
  import('./pages/admin/Teams').then((module) => ({ default: module.Teams })),
)
const Locations = lazy(() =>
  import('./pages/admin/Locations').then((module) => ({
    default: module.Locations,
  })),
)
const Reports = lazy(() =>
  import('./pages/admin/Reports').then((module) => ({
    default: module.Reports,
  })),
)
const AllAttendance = lazy(() =>
  import('./pages/admin/AllAttendance').then((module) => ({
    default: module.AllAttendance,
  })),
)
import { Login } from './pages/Login'

export function AppRoutes() {
  const pages = {
    '/': <Dashboard />,
    '/leave': <Leave />,
    '/profile': <Profile />,
    '/team': <Team />,
    '/admin/employees': <Employees />,
    '/admin/teams': <Teams />,
    '/admin/locations': <Locations />,
    '/admin/reports': <Reports />,
    '/admin/all-attendance': <AllAttendance />,
  }
  return (
    <SessionGate>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<RequireAuth />}>
          <Route element={<Layout />}>
            <Route path="/change-password" element={<ChangePassword />} />
            {navigation.map((item) => (
              <Route
                key={item.path}
                element={<RequirePermission code={item.permissions} />}
              >
                <Route
                  path={item.path}
                  element={
                    <Suspense fallback={<p role="status">Loading page…</p>}>
                      {pages[item.path]}
                    </Suspense>
                  }
                />
              </Route>
            ))}
            <Route
              path="*"
              element={
                <section className="card">
                  <h1>Page not found</h1>
                  <p>Choose a page from the navigation.</p>
                </section>
              }
            />
          </Route>
        </Route>
      </Routes>
    </SessionGate>
  )
}
