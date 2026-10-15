import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { passwordSchema } from '../../auth/validation'
import { useApi } from '../../api/useApi'
import { errorMessage } from '../../api/errors'
import { usePermissions } from '../../hooks/usePermissions'
import type { Employee } from '../../types/domain'
import type { Handover } from '../../components/PasswordHandover'
import { Dialog } from '../../components/Dialog'
import { FormField } from '../../components/FormField'
import { StatusBanner } from '../../components/Feedback'

const schema = z.object({ default_password: passwordSchema.shape.new_password })
export function PasswordReset({
  employee,
  onClose,
  onSaved,
}: {
  employee: Employee
  onClose: () => void
  onSaved: (handover: Handover) => void
}) {
  const api = useApi(),
    can = usePermissions(),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<string | null>(null)
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { default_password: '' },
  })
  return (
    <Dialog
      title={`Reset password · ${employee.employee_id}`}
      onClose={onClose}
      busy={busy}
    >
      <p>
        The employee’s sessions will end and they must change the new default
        password at the next sign-in.
      </p>
      <form
        noValidate
        onSubmit={form.handleSubmit(async (input) => {
          if (busy) return
          setBusy(true)
          setError(null)
          try {
            const result = await api.post<{ default_password: string }>(
              `/admin/employees/${employee.id}/reset-password`,
              input,
            )
            form.reset()
            onSaved({
              employee_id: employee.employee_id,
              password: result.default_password,
            })
          } catch (failure) {
            setError(errorMessage(failure))
            form.reset()
          } finally {
            setBusy(false)
          }
        })}
      >
        <FormField
          id="reset-default"
          label="New default password"
          type="password"
          autoComplete="new-password"
          {...form.register('default_password')}
          error={form.formState.errors.default_password?.message}
        />
        {can('employee.create.any') && (
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
                  form.setValue('default_password', result.default_password),
                )
                .catch((failure: unknown) => setError(errorMessage(failure)))
                .finally(() => setBusy(false))
            }}
          >
            Generate password
          </button>
        )}
        <StatusBanner message={error} error />
        <button disabled={busy}>Reset password</button>
      </form>
    </Dialog>
  )
}
