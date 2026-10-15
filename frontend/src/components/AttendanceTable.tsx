import type { CalendarEntry } from '../types/domain'
import { officeTime } from '../utils/dates'
import { DataTable } from './DataTable'
import { statusLabel } from '../utils/status'

export function AttendanceTable({
  entries,
  timezone,
  onEdit,
}: {
  entries: CalendarEntry[]
  timezone: string
  onEdit?: (entry: CalendarEntry) => void
}) {
  return (
    <DataTable
      caption="Attendance records"
      items={entries}
      rowKey={(entry) => entry.date}
      columns={[
        { label: 'Date', render: (entry) => entry.date },
        {
          label: 'Status',
          render: (entry) => (
            <span className={`badge status-${entry.display_status}`}>
              {statusLabel(entry.display_status)}
            </span>
          ),
        },
        { label: 'Work mode', render: (entry) => statusLabel(entry.work_mode) },
        {
          label: 'Location',
          render: (entry) => entry.work_location_name || '—',
        },
        {
          label: 'Clock in',
          render: (entry) => officeTime(entry.clock_in, timezone),
        },
        {
          label: 'Clock out',
          render: (entry) => officeTime(entry.clock_out, timezone),
        },
        { label: 'Hours', render: (entry) => entry.worked_hours.toFixed(2) },
        {
          label: 'Leave',
          render: (entry) =>
            entry.leaves
              .map(
                (leave) =>
                  `${leave.leave_type}${leave.half_day_period ? ` (${leave.half_day_period})` : ''}`,
              )
              .join(', ') || '—',
        },
        ...(onEdit
          ? [
              {
                label: 'Actions',
                render: (entry: CalendarEntry) =>
                  entry.attendance_id && (
                    <button className="secondary" onClick={() => onEdit(entry)}>
                      Correct attendance
                    </button>
                  ),
              },
            ]
          : []),
      ]}
    />
  )
}
