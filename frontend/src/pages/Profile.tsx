import { useMutation } from '@tanstack/react-query'
import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { Link } from 'react-router-dom'
import { z } from 'zod'
import { useAuth } from '../auth/context'
import { useAuthState } from '../auth/useAuthState'
import { useApi } from '../api/useApi'
import { errorMessage } from '../api/errors'
import { usePermissions } from '../hooks/usePermissions'
import type { Profile as ProfileResponse } from '../types/auth'
import { ExportPanel } from '../components/ExportPanel'
import { FormField } from '../components/FormField'
import { StatusBanner } from '../components/Feedback'

const schema = z.object({
  display_name: z
    .string()
    .max(100, 'Use at most 100 characters.')
    .refine(
      (value) => !value || !!value.trim(),
      'Use a nonblank name or clear it.',
    ),
})
export function Profile() {
  const session = useAuth(),
    { profile } = useAuthState(),
    api = useApi(),
    can = usePermissions()
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { display_name: profile!.display_name || '' },
  })
  const save = useMutation({
    mutationFn: (display_name: string) =>
      api.patch<ProfileResponse>('/me', { display_name: display_name || null }),
    onSuccess: (data) => {
      session.updateProfile(data)
      form.reset({ display_name: data.display_name || '' })
    },
  })
  return (
    <div className="page-stack">
      <h1>Profile</h1>
      <section className="card">
        <h2>Account details</h2>
        <dl className="detail-grid">
          <div>
            <dt>Employee ID</dt>
            <dd>{profile!.employee_id}</dd>
          </div>
          <div>
            <dt>Name</dt>
            <dd>
              {profile!.first_name} {profile!.last_name}
            </dd>
          </div>
          <div>
            <dt>Role</dt>
            <dd>{profile!.role.name}</dd>
          </div>
          <div>
            <dt>Team</dt>
            <dd>{profile!.team?.name || 'Unassigned'}</dd>
          </div>
          <div>
            <dt>Position</dt>
            <dd>{profile!.position || '—'}</dd>
          </div>
          <div>
            <dt>Department</dt>
            <dd>{profile!.department || '—'}</dd>
          </div>
        </dl>
        {can('profile.update.self', 'profile.update.any') && (
          <form
            noValidate
            onSubmit={form.handleSubmit((values) =>
              save.mutate(values.display_name),
            )}
          >
            <FormField
              id="display-name"
              label="Display name"
              {...form.register('display_name')}
              error={form.formState.errors.display_name?.message}
            />
            <StatusBanner
              message={
                save.error
                  ? errorMessage(save.error)
                  : save.isSuccess
                    ? 'Display name updated.'
                    : null
              }
              error={!!save.error}
            />
            <button disabled={save.isPending}>Save display name</button>
          </form>
        )}
        <Link to="/change-password">Change password</Link>
      </section>
      {can('report.export.self', 'report.export.any') && <ExportPanel />}
    </div>
  )
}
