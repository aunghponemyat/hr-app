import {
  eachDayOfInterval,
  eachMonthOfInterval,
  endOfMonth,
  endOfWeek,
  format,
  parseISO,
  startOfMonth,
  startOfWeek,
} from 'date-fns'
import type { CalendarEntry } from '../types/domain'
import { dateString, officeTime } from '../utils/dates'

import { statusLabel } from '../utils/status'

export function AttendanceCalendar({
  entries,
  timezone,
}: {
  entries: CalendarEntry[]
  timezone: string
}) {
  if (!entries.length) return <p>No dates to display.</p>
  const lookup = new Map(entries.map((entry) => [entry.date, entry]))
  const months = eachMonthOfInterval({
    start: parseISO(entries[0].date),
    end: parseISO(entries.at(-1)!.date),
  })
  return (
    <div>
      <p className="calendar-legend">
        {['present', 'half-day', 'leave', 'absent', 'weekend', 'upcoming'].map(
          (status) => (
            <span className={`badge status-${status}`} key={status}>
              {statusLabel(status)}
            </span>
          ),
        )}
      </p>
      <div className="calendar-months">
        {months.map((month) => (
          <section
            key={dateString(month)}
            className="calendar-month"
            aria-label={format(month, 'MMMM yyyy')}
          >
            <h3>{format(month, 'MMMM yyyy')}</h3>
            <div className="calendar-grid">
              {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((day) => (
                <span className="weekday" key={day}>
                  {day}
                </span>
              ))}
              {eachDayOfInterval({
                start: startOfWeek(startOfMonth(month), { weekStartsOn: 1 }),
                end: endOfWeek(endOfMonth(month), { weekStartsOn: 1 }),
              }).map((date) => {
                const key = dateString(date),
                  entry = lookup.get(key),
                  within = date.getMonth() === month.getMonth()
                const detail = entry
                  ? `${key}: ${statusLabel(entry.display_status)}${entry.work_mode ? `, ${entry.work_mode}` : ''}, ${officeTime(entry.clock_in, timezone)} – ${officeTime(entry.clock_out, timezone)}${entry.leaves.map((leave) => `, ${leave.leave_type}${leave.half_day_period ? ` (${leave.half_day_period})` : ''}`).join('')}`
                  : key
                return (
                  <span
                    key={key}
                    className={`calendar-day ${entry && within ? `status-${entry.display_status || 'empty'}` : 'outside'}`}
                    tabIndex={entry && within ? 0 : undefined}
                    title={detail}
                    aria-label={detail}
                  >
                    {within ? date.getDate() : ''}
                  </span>
                )
              })}
            </div>
          </section>
        ))}
      </div>
    </div>
  )
}
