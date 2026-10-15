import { Route, Routes } from 'react-router-dom'
import { RequireAuth, RequirePermission, SessionGate } from './auth/guards'
import { Layout } from './components/Layout'
import { navigation } from './components/navigation'
import { ChangePassword } from './pages/ChangePassword'
import { FeaturePlaceholder } from './pages/FeaturePlaceholder'
import { Login } from './pages/Login'

export function AppRoutes() {
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
                  element={<FeaturePlaceholder title={item.label} />}
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
