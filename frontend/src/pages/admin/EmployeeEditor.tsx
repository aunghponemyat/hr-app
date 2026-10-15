import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { useState } from 'react'
import { z } from 'zod'
import { useApi } from '../../api/useApi'
import { errorMessage } from '../../api/errors'
import { passwordSchema } from '../../auth/validation'
import { usePermissions } from '../../hooks/usePermissions'
import type { Employee, EmployeeInput, Role, Team } from '../../types/domain'
import type { Handover } from '../../components/PasswordHandover'
import { Dialog } from '../../components/Dialog'
import { FormField } from '../../components/FormField'
import { SelectField } from '../../components/Fields'
import { StatusBanner } from '../../components/Feedback'

const name = z
  .string()
  .min(1, 'Required.')
  .max(100)
  .refine((value) => !!value.trim(), 'Use a nonblank value.')
const optionalName = z
  .string()
  .max(100)
  .refine(
    (value) => !value || !!value.trim(),
    'Use a nonblank value or clear it.',
  )
const schema = z.object({
  first_name: name,
  last_name: name,
  display_name: optionalName,
  position: optionalName,
  department: optionalName,
  role_id: z.number().int().positive('Choose a role.'),
  team_id: z
    .string()
    .refine(
      (value) => !value || /^[1-9]\d*$/.test(value),
      'Choose a valid team.',
    ),
  default_password: z.string(),
  is_active: z.boolean(),
})
type Values = z.infer<typeof schema>

export function EmployeeEditor({
  employee,
  roles,
  teams,
  onClose,
  onSaved,
}: {
  employee: Employee | null
  roles: Role[]
  teams: Team[]
  onClose: () => void
  onSaved: (handover?: Handover) => void
}) {
  const api = useApi(),
    can = usePermissions(),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<string | null>(null)
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      first_name: employee?.first_name || '',
      last_name: employee?.last_name || '',
      display_name: employee?.display_name || '',
      position: employee?.position || '',
      department: employee?.department || '',
      role_id: employee?.role.id || 0,
      team_id: employee?.team?.id.toString() || '',
      default_password: '',
      is_active: employee?.is_active ?? true,
    },
  })
  const errors = form.formState.errors
  return (
    <Dialog
      title={employee ? `Edit ${employee.employee_id}` : 'Create employee'}
      onClose={onClose}
      busy={busy}
      drawer
    >
      <form
        noValidate
        aria-busy={busy}
        onSubmit={form.handleSubmit(async (values) => {
          if (busy) return
          if (!employee) {
            const password = passwordSchema.shape.new_password.safeParse(
              values.default_password,
            )
            if (!password.success) {
              form.setError('default_password', {
                message: password.error.issues[0].message,
              })
              return
            }
          }
          setBusy(true)
          setError(null)
          const input: EmployeeInput = {
            first_name: values.first_name,
            last_name: values.last_name,
            display_name: values.display_name || null,
            position: values.position || null,
            department: values.department || null,
            role_id: values.role_id,
            team_id: values.team_id ? Number(values.team_id) : null,
          }
          try {
            if (employee) {
              await api.patch(`/admin/employees/${employee.id}`, {
                ...input,
                is_active: values.is_active,
              })
              form.reset()
              onSaved()
            } else {
              const result = await api.post<
                Employee & { default_password: string }
              >('/admin/employees', {
                ...input,
                default_password: values.default_password,
              })
              form.reset()
              onSaved({
                employee_id: result.employee_id,
                password: result.default_password,
              })
            }
          } catch (failure) {
            setError(errorMessage(failure))
            form.resetField('default_password')
          } finally {
            setBusy(false)
          }
        })}
      >
        {employee && (
          <p>
            Employee ID: <strong>{employee.employee_id}</strong> (immutable)
          </p>
        )}
        <FormField
          id="employee-first"
          label="First name"
          {...form.register('first_name')}
          error={errors.first_name?.message}
        />
        <FormField
          id="employee-last"
          label="Last name"
          {...form.register('last_name')}
          error={errors.last_name?.message}
        />
        <FormField
          id="employee-display"
          label="Display name (optional)"
          {...form.register('display_name')}
          error={errors.display_name?.message}
        />
        <FormField
          id="employee-position"
          label="Position (optional)"
          {...form.register('position')}
          error={errors.position?.message}
        />
        <FormField
          id="employee-department"
          label="Department (optional)"
          {...form.register('department')}
          error={errors.department?.message}
        />
        <SelectField
          id="employee-role"
          label="Role"
          {...form.register('role_id', { valueAsNumber: true })}
          error={errors.role_id?.message}
        >
          <option value="0">Choose role</option>
          {roles.map((role) => (
            <option value={role.id} key={role.id}>
              {role.name}
            </option>
          ))}
        </SelectField>
        {can('team.manage.any') ? (
          <SelectField
            id="employee-team"
            label="Team"
            {...form.register('team_id')}
            error={errors.team_id?.message}
          >
            <option value="">Unassigned</option>
            {teams.map((team) => (
              <option value={team.id} key={team.id}>
                {team.name}
              </option>
            ))}
          </SelectField>
        ) : (
          <FormField
            id="employee-team"
            label="Team internal ID (optional)"
            {...form.register('team_id')}
            error={errors.team_id?.message}
          />
        )}
        {employee ? (
          <label className="radio-label">
            <input type="checkbox" {...form.register('is_active')} />
            Active account
          </label>
        ) : (
          <>
            <FormField
              id="employee-default"
              label="Default password"
              type="password"
              autoComplete="new-password"
              {...form.register('default_password')}
              error={errors.default_password?.message}
            />
            <p className="muted small">
              Use 8–1024 characters with letters and digits.
            </p>
            <button
              type="button"
              className="secondary"
              disabled={busy}
              onClick={() => {
                setBusy(true)
                void api
                  .get<{ default_password: string }>(
                    '/admin/utils/generate-password',
                  )
                  .then((result) =>
                    form.setValue('default_password', result.default_password, {
                      shouldValidate: true,
                    }),
                  )
                  .catch((failure: unknown) => setError(errorMessage(failure)))
                  .finally(() => setBusy(false))
              }}
            >
              Generate password
            </button>
          </>
        )}
        <StatusBanner message={error} error />
        <button disabled={busy}>
          {busy ? 'Saving…' : employee ? 'Save employee' : 'Create employee'}
        </button>
      </form>
      {roles.length > 0 && (
        <details>
          <summary>Role permissions (read only)</summary>
          {roles.map((role) => (
            <section key={role.id}>
              <h3>{role.name}</h3>
              <p className="small">{role.permissions.join(', ')}</p>
            </section>
          ))}
        </details>
      )}
    </Dialog>
  )
}
