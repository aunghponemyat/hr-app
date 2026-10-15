import { z } from 'zod'
import { parseISO } from 'date-fns'
import type { LeaveOptions } from '../types/domain'
import { dateString, validDate } from './dates'
import { subDays } from 'date-fns'

const base = z.object({
  leave_type_id: z.number().int().positive('Choose a leave type.'),
  leave_reason_id: z.number().int().positive('Choose a reason.'),
  reason_text: z.string().max(500),
  duration_type: z.enum(['half_day', 'full_days']),
  half_day_period: z.enum(['', 'morning', 'afternoon']),
  num_days: z.number().min(0.5),
  start_date: z.string(),
  reporting_manager_id: z
    .number()
    .int()
    .positive('Choose a reporting manager.'),
  remark: z.string().max(500),
})
export type LeaveFormValues = z.infer<typeof base>
export function leaveSchema(options: LeaveOptions) {
  return base.superRefine((values, ctx) => {
    const error = (path: keyof LeaveFormValues, message: string) =>
      ctx.addIssue({ code: 'custom', path: [path], message })
    if (!options.types.some((choice) => choice.id === values.leave_type_id))
      error('leave_type_id', 'Choose an active leave type.')
    const reason = options.reasons.find(
      (choice) => choice.id === values.leave_reason_id,
    )
    if (!reason) error('leave_reason_id', 'Choose an active reason.')
    if (reason?.requires_text && !values.reason_text.trim())
      error('reason_text', 'Describe your leave reason.')
    if (values.duration_type === 'half_day') {
      if (!values.half_day_period)
        error('half_day_period', 'Choose morning or afternoon.')
      if (values.num_days !== 0.5)
        error('num_days', 'Half-day leave must be 0.5 days.')
    } else if (
      !Number.isInteger(values.num_days) ||
      values.num_days < 1 ||
      values.num_days > options.max_days_per_request
    )
      error('num_days', `Choose 1–${options.max_days_per_request} whole days.`)
    if (!validDate(values.start_date))
      error('start_date', 'Choose a valid start date.')
    else {
      if (
        values.start_date <
        dateString(subDays(parseISO(options.today), options.backdate_days))
      )
        error('start_date', 'The start date is too far in the past.')
      if (
        !options.working_weekdays.includes(
          (parseISO(values.start_date).getDay() + 6) % 7,
        )
      )
        error('start_date', 'Choose a working day.')
    }
    if (
      !options.managers.some(
        (manager) => manager.id === values.reporting_manager_id,
      )
    )
      error('reporting_manager_id', 'Choose an eligible reporting manager.')
  })
}
