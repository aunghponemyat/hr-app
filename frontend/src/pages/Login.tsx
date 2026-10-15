import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/context'
import { safeDestination } from '../auth/destination'
import { useAuthState } from '../auth/useAuthState'
import { loginSchema } from '../auth/validation'
import { FormField } from '../components/FormField'
import type { LoginInput } from '../types/auth'

export function Login() {
  const session = useAuth()
  const { profile, busy, error } = useAuthState()
  const location = useLocation()
  const from = safeDestination(
    (location.state as { from?: unknown } | null)?.from,
  )
  const {
    register,
    handleSubmit,
    resetField,
    formState: { errors, isSubmitting },
  } = useForm<LoginInput>({
    resolver: zodResolver(loginSchema),
    defaultValues: { username: '', password: '' },
  })
  if (profile)
    return (
      <Navigate
        to={profile.must_change_password ? '/change-password' : from}
        state={{ from }}
        replace
      />
    )
  return (
    <main className="auth-screen">
      <section className="card auth-card" aria-labelledby="login-heading">
        <p className="eyebrow">Your workplace, connected</p>
        <h1 id="login-heading">HR &amp; Attendance</h1>
        <p className="muted">Sign in with your employee ID and password.</p>
        <form
          onSubmit={handleSubmit(async (input) => {
            try {
              await session.login(input)
            } catch {
              /* The session exposes a safe error message. */
            } finally {
              resetField('password')
            }
          })}
          noValidate
          aria-busy={busy || isSubmitting}
        >
          <FormField
            id="employee-id"
            label="Employee ID"
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            {...register('username')}
            error={errors.username?.message}
          />
          <FormField
            id="password"
            label="Password"
            type="password"
            autoComplete="current-password"
            {...register('password')}
            error={errors.password?.message}
          />
          {error && (
            <p className="error-banner" role="alert">
              {error}
            </p>
          )}
          <button type="submit" disabled={busy || isSubmitting}>
            {busy || isSubmitting ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
        <p className="muted small">
          New account? Use the default password provided by HR. You’ll choose
          your own password after signing in.
        </p>
      </section>
    </main>
  )
}
