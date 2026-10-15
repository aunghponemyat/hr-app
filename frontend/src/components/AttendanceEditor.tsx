import { useMutation, useQueryClient } from '@tanstack/react-query'
import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { useApi } from '../api/useApi'
import { errorMessage } from '../api/errors'
import type { AttendanceEdit, CalendarEntry } from '../types/domain'
import { Dialog } from './Dialog'
import { StatusBanner } from './Feedback'
import { FormField } from './FormField'
import { SelectField, TextAreaField } from './Fields'

const offsetTime = z
  .string()
  .refine(
    (value) =>
      !value ||
      (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})$/.test(
        value,
      ) &&
        Number.isFinite(Date.parse(value))),
    'Enter an ISO date/time including Z or an offset, or leave blank to clear.',
  )
const schema = z.object({
  status: z.enum(['', 'present', 'absent', 'half-day']),
  clock_in: offsetTime,
  clock_out: offsetTime,
  edit_times: z.boolean(),
  reason: z.string().trim().min(1, 'A reason is required.').max(500),
})
type Values = z.infer<typeof schema>

export function AttendanceEditor({
  entry,
  onClose,
}: {
  entry: CalendarEntry
  onClose: () => void
}) {
  const api = useApi(),
    client = useQueryClient()
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      status: '',
      clock_in: entry.clock_in || '',
      clock_out: entry.clock_out || '',
      edit_times: false,
      reason: '',
    },
  })
  const update = useMutation({
    mutationFn: (data: AttendanceEdit) =>
      api.patch(`/attendance/${entry.attendance_id}`, data),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['attendance'] })
      void client.invalidateQueries({ queryKey: ['team'] })
      onClose()
    },
  })
  return (
    <Dialog
      title={`Correct attendance · ${entry.date}`}
      busy={update.isPending}
      onClose={onClose}
    >
      <p className="muted">
        Corrections require a reason and are recorded for audit. Changing a
        clock time clears its GPS verification.
      </p>
      <form
        noValidate
        onSubmit={form.handleSubmit((values) => {
          if (!values.status && !values.edit_times) {
            form.setError('status', {
              message: 'Choose a status or enable clock-time corrections.',
            })
            return
          }
          const data: AttendanceEdit = { reason: values.reason }
          if (values.status) data.status = values.status
          if (values.edit_times) {
            data.clock_in = values.clock_in || null
            data.clock_out = values.clock_out || null
          }
          update.mutate(data)
        })}
      >
        <SelectField
          id="edit-status"
          label="Stored status"
          {...form.register('status')}
          error={form.formState.errors.status?.message}
        >
          <option value="">Keep current status</option>
          {['present', 'absent', 'half-day'].map((status) => (
            <option key={status}>{status}</option>
          ))}
        </SelectField>
        <label className="radio-label">
          <input type="checkbox" {...form.register('edit_times')} />
          Correct clock times
        </label>
        <FormField
          id="edit-clock-in"
          label="Clock in (ISO date/time with offset)"
          {...form.register('clock_in')}
          error={form.formState.errors.clock_in?.message}
        />
        <FormField
          id="edit-clock-out"
          label="Clock out (ISO date/time with offset)"
          {...form.register('clock_out')}
          error={form.formState.errors.clock_out?.message}
        />
        <TextAreaField
          id="edit-reason"
          label="Reason for correction"
          maxLength={500}
          {...form.register('reason')}
          error={form.formState.errors.reason?.message}
        />
        <StatusBanner
          message={update.error ? errorMessage(update.error) : null}
          error
        />
        <button disabled={update.isPending}>Save correction</button>
      </form>
    </Dialog>
  )
}
