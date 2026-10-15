import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm, useWatch } from 'react-hook-form'
import { DayPicker } from 'react-day-picker'
import { parseISO, subDays } from 'date-fns'
import { useApi } from '../api/useApi'
import { errorMessage } from '../api/errors'
import type { LeaveOptions, LeaveRequest } from '../types/domain'
import { dateString, leaveEnd, validDate } from '../utils/dates'
import { leaveSchema } from '../utils/leaveValidation'
import type { LeaveFormValues } from '../utils/leaveValidation'
import { FormField } from './FormField'
import { SelectField, TextAreaField } from './Fields'
import { StatusBanner } from './Feedback'

export function LeaveForm({ options }: { options: LeaveOptions }) {
  const api = useApi(),
    client = useQueryClient()
  const defaults: LeaveFormValues = {
    leave_type_id: 0,
    leave_reason_id: 0,
    reason_text: '',
    duration_type: 'full_days',
    half_day_period: '',
    num_days: 1,
    start_date: leaveEnd(options.today, 1, options.working_weekdays),
    reporting_manager_id: 0,
    remark: '',
  }
  const form = useForm<LeaveFormValues>({
    resolver: zodResolver(leaveSchema(options)),
    defaultValues: defaults,
  })
  const values = useWatch({ control: form.control })
  const half = values.duration_type === 'half_day'
  const requiresText = options.reasons.some(
    (reason) => reason.id === values.leave_reason_id && reason.requires_text,
  )
  const submit = useMutation({
    mutationFn: (input: LeaveFormValues) =>
      api.post<LeaveRequest>('/leave-requests', {
        ...input,
        num_days: input.duration_type === 'half_day' ? 0.5 : input.num_days,
        half_day_period:
          input.duration_type === 'half_day' ? input.half_day_period : null,
        reason_text: input.reason_text || null,
        remark: input.remark || null,
      }),
    onSuccess: () => {
      form.reset(defaults)
      void client.invalidateQueries({ queryKey: ['leave'] })
      void client.invalidateQueries({ queryKey: ['attendance'] })
    },
  })
  const errors = form.formState.errors
  return (
    <section className="card">
      <h2>Request leave</h2>
      {!options.managers.length && (
        <StatusBanner
          message="No reporting manager is available. Please contact HR."
          error
        />
      )}
      <form
        noValidate
        onSubmit={form.handleSubmit((input) => submit.mutate(input))}
        aria-busy={submit.isPending}
      >
        <SelectField
          id="leave-type"
          label="Leave type"
          {...form.register('leave_type_id', { valueAsNumber: true })}
          error={errors.leave_type_id?.message}
        >
          <option value="0">Choose type</option>
          {options.types.map((type) => (
            <option key={type.id} value={type.id}>
              {type.name}
            </option>
          ))}
        </SelectField>
        <SelectField
          id="leave-reason"
          label="Reason"
          {...form.register('leave_reason_id', { valueAsNumber: true })}
          error={errors.leave_reason_id?.message}
        >
          <option value="0">Choose reason</option>
          {options.reasons.map((reason) => (
            <option key={reason.id} value={reason.id}>
              {reason.name}
            </option>
          ))}
        </SelectField>
        {requiresText && (
          <TextAreaField
            id="reason-text"
            label="Describe your reason"
            maxLength={500}
            {...form.register('reason_text')}
            error={errors.reason_text?.message}
          />
        )}
        <fieldset>
          <legend>Duration</legend>
          <div className="actions">
            {(['full_days', 'half_day'] as const).map((duration) => (
              <label key={duration} className="radio-label">
                <input
                  type="radio"
                  value={duration}
                  {...form.register('duration_type', {
                    onChange: (event) => {
                      const isHalf = event.target.value === 'half_day'
                      form.setValue('num_days', isHalf ? 0.5 : 1)
                      form.setValue('half_day_period', '')
                    },
                  })}
                />
                {duration === 'half_day' ? 'Half day' : 'Full days'}
              </label>
            ))}
          </div>
        </fieldset>
        {half ? (
          <SelectField
            id="half-period"
            label="Half-day period"
            {...form.register('half_day_period')}
            error={errors.half_day_period?.message}
          >
            <option value="">Choose period</option>
            <option value="morning">Morning</option>
            <option value="afternoon">Afternoon</option>
          </SelectField>
        ) : (
          <FormField
            id="leave-days"
            label="Number of days"
            type="number"
            min={1}
            max={options.max_days_per_request}
            step={1}
            {...form.register('num_days', { valueAsNumber: true })}
            error={errors.num_days?.message}
          />
        )}
        <div>
          <FormField
            id="leave-start"
            label="Start date"
            type="date"
            min={dateString(
              subDays(parseISO(options.today), options.backdate_days),
            )}
            {...form.register('start_date')}
            error={errors.start_date?.message}
          />
          <DayPicker
            mode="single"
            selected={
              values.start_date && validDate(values.start_date)
                ? parseISO(values.start_date)
                : undefined
            }
            defaultMonth={parseISO(options.today)}
            onSelect={(date) => {
              if (date)
                form.setValue('start_date', dateString(date), {
                  shouldValidate: true,
                })
            }}
            disabled={[
              {
                before: subDays(parseISO(options.today), options.backdate_days),
              },
              (date) =>
                !options.working_weekdays.includes((date.getDay() + 6) % 7),
            ]}
            weekStartsOn={1}
            required
          />
        </div>
        <p>
          Expected end date:{' '}
          <output aria-label="Expected end date">
            {leaveEnd(
              values.start_date || '',
              half ? 0.5 : values.num_days || 0,
              options.working_weekdays,
            ) || 'Choose dates'}
          </output>
          <span className="muted small">
            {' '}
            · Working days only; confirmed by the server.
          </span>
        </p>
        <SelectField
          id="leave-manager"
          label="Reporting manager"
          {...form.register('reporting_manager_id', { valueAsNumber: true })}
          error={errors.reporting_manager_id?.message}
        >
          <option value="0">Choose manager</option>
          {options.managers.map((manager) => (
            <option key={manager.id} value={manager.id}>
              {manager.name}
            </option>
          ))}
        </SelectField>
        <TextAreaField
          id="leave-remark"
          label="Remark (optional)"
          maxLength={500}
          {...form.register('remark')}
          error={errors.remark?.message}
        />
        <StatusBanner
          message={
            submit.error
              ? errorMessage(submit.error)
              : submit.isSuccess
                ? 'Leave request submitted.'
                : null
          }
          error={!!submit.error}
        />
        <button disabled={submit.isPending || !options.managers.length}>
          {submit.isPending ? 'Submitting…' : 'Submit leave request'}
        </button>
      </form>
    </section>
  )
}
