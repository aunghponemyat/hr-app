import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/context'
import { safeDestination } from '../auth/destination'
import { useAuthState } from '../auth/useAuthState'
import { passwordSchema } from '../auth/validation'
import type { PasswordForm } from '../auth/validation'
import { FormField } from '../components/FormField'

export function ChangePassword() {
  const session = useAuth()
  const { profile, busy, error } = useAuthState()
  const location = useLocation()
  const navigate = useNavigate()
  const from = safeDestination(
    (location.state as { from?: unknown } | null)?.from,
  )
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<PasswordForm>({
    resolver: zodResolver(passwordSchema),
    defaultValues: { current_password: '', new_password: '', confirmation: '' },
  })
  return (
    <section className="card auth-card" aria-labelledby="password-heading">
      <p className="eyebrow">Account security</p>
      <h1 id="password-heading">Change password</h1>
      {profile?.must_change_password && (
        <p>Choose your own password before continuing.</p>
      )}
      <p className="muted" id="password-policy">
        Use 8–1024 characters, including letters and digits. Choose a different
        password from your current one.
      </p>
      <form
        noValidate
        aria-describedby="password-policy"
        aria-busy={busy || isSubmitting}
        onSubmit={handleSubmit(async (input) => {
          try {
            await session.changePassword({
              current_password: input.current_password,
              new_password: input.new_password,
            })
            reset()
            navigate(from, { replace: true })
          } catch {
            reset()
          }
        })}
      >
        <FormField
          id="current-password"
          label="Current password"
          type="password"
          autoComplete="current-password"
          {...register('current_password')}
          error={errors.current_password?.message}
        />
        <FormField
          id="new-password"
          label="New password"
          type="password"
          autoComplete="new-password"
          {...register('new_password')}
          error={errors.new_password?.message}
        />
        <FormField
          id="confirm-password"
          label="Confirm new password"
          type="password"
          autoComplete="new-password"
          {...register('confirmation')}
          error={errors.confirmation?.message}
        />
        {error && (
          <p className="error-banner" role="alert">
            {error}
          </p>
        )}
        <button type="submit" disabled={busy || isSubmitting}>
          {busy || isSubmitting ? 'Saving…' : 'Save password'}
        </button>
        {!profile?.must_change_password && <Link to="/profile">Cancel</Link>}
      </form>
    </section>
  )
}
