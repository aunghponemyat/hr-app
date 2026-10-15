import {
  addDays,
  addMonths,
  addYears,
  differenceInCalendarDays,
  endOfMonth,
  endOfWeek,
  endOfYear,
  format,
  isValid,
  parseISO,
  startOfMonth,
  startOfWeek,
  startOfYear,
  subYears,
} from 'date-fns'
export type PeriodView = 'week' | 'month' | 'year' | 'custom'
export interface Period {
  view: PeriodView
  anchor: string
  from: string
  to: string
}
export const dateString = (value: Date) => format(value, 'yyyy-MM-dd')
export const validDate = (value: string) =>
  /^\d{4}-\d{2}-\d{2}$/.test(value) && isValid(parseISO(value))
export const initialPeriod = (today: string): Period => ({
  view: 'month',
  anchor: today,
  from: today,
  to: today,
})
export function periodBounds(period: Period): { from: string; to: string } {
  const anchor = parseISO(period.anchor)
  if (period.view === 'custom') return { from: period.from, to: period.to }
  const bounds =
    period.view === 'week'
      ? [
          startOfWeek(anchor, { weekStartsOn: 1 }),
          endOfWeek(anchor, { weekStartsOn: 1 }),
        ]
      : period.view === 'year'
        ? [startOfYear(anchor), endOfYear(anchor)]
        : [startOfMonth(anchor), endOfMonth(anchor)]
  return { from: dateString(bounds[0]), to: dateString(bounds[1]) }
}
export function periodParams(period: Period) {
  return period.view === 'custom'
    ? { view: 'custom', from: period.from, to: period.to }
    : { view: period.view, anchor: period.anchor }
}
export function shiftPeriod(period: Period, direction: number): Period {
  const date = parseISO(period.anchor)
  return {
    ...period,
    anchor: dateString(
      period.view === 'week'
        ? addDays(date, direction * 7)
        : period.view === 'year'
          ? addYears(date, direction)
          : addMonths(date, direction),
    ),
  }
}
export function rangeError(
  from: string,
  to: string,
  max: number,
  earliest?: string,
): string | null {
  if (!validDate(from) || !validDate(to))
    return 'Choose valid start and end dates.'
  if (to < from) return 'The end date must be on or after the start date.'
  if (differenceInCalendarDays(parseISO(to), parseISO(from)) + 1 > max)
    return `Select at most ${max} days.`
  if (earliest && to < earliest)
    return 'Attendance history is available for the past year.'
  return null
}
export const historyStart = (today: string) =>
  dateString(subYears(parseISO(today), 1))
export const officeTime = (value: string | null, timezone: string) =>
  value
    ? new Intl.DateTimeFormat('en-GB', {
        timeZone: timezone,
        hour: '2-digit',
        minute: '2-digit',
      }).format(new Date(value))
    : '—'
export function leaveEnd(
  start: string,
  days: number,
  weekdays: number[],
): string {
  if (
    !validDate(start) ||
    !Number.isFinite(days) ||
    days < 0.5 ||
    days > 99 ||
    !weekdays.length
  )
    return ''
  let cursor = parseISO(start),
    remaining = Math.ceil(days)
  for (let attempts = 0; attempts < 700; attempts++) {
    if (weekdays.includes((cursor.getDay() + 6) % 7) && --remaining === 0)
      return dateString(cursor)
    cursor = addDays(cursor, 1)
  }
  return ''
}
