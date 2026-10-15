import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useApi } from '../api/useApi'
import { useAuthState } from '../auth/useAuthState'
import { usePermissions } from '../hooks/usePermissions'
import type { CalendarEntry, CalendarResponse } from '../types/domain'
import {
  historyStart,
  initialPeriod,
  periodBounds,
  periodParams,
  rangeError,
} from '../utils/dates'
import { AttendanceCalendar } from './AttendanceCalendar'
import { AttendanceTable } from './AttendanceTable'
import { QueryFeedback } from './Feedback'
import { PeriodFilter } from './PeriodFilter'
import { SummaryCards } from './SummaryCards'
import { AttendanceEditor } from './AttendanceEditor'

export function AttendanceOverview({ employeeId }: { employeeId: number }) {
  const api = useApi(),
    can = usePermissions(),
    { profile } = useAuthState()
  const [period, setPeriod] = useState(() => initialPeriod(profile!.app.today))
  const [tab, setTab] = useState<'table' | 'calendar'>('table')
  const [edit, setEdit] = useState<CalendarEntry | null>(null)
  const [page, setPage] = useState(1)
  const bounds = periodBounds(period),
    earliest = can('attendance.read.any')
      ? undefined
      : historyStart(profile!.app.today)
  const error = rangeError(
    bounds.from,
    bounds.to,
    profile!.app.max_report_range_days,
    earliest,
  )
  const query = useQuery({
    queryKey: ['attendance', 'calendar', employeeId, period],
    queryFn: ({ signal }) =>
      api.get<CalendarResponse>(
        '/attendance/calendar',
        { ...periodParams(period), employee_id: employeeId },
        signal,
      ),
    enabled: !error,
  })
  return (
    <section className="card attendance-overview">
      <h2>Attendance overview</h2>
      <PeriodFilter
        value={period}
        onChange={(value) => {
          setPeriod(value)
          setPage(1)
        }}
        years={
          query.data?.available_years || [
            Number(profile!.app.today.slice(0, 4)),
          ]
        }
        maxDays={profile!.app.max_report_range_days}
        earliest={earliest}
      />
      {!error && (
        <>
          <QueryFeedback
            pending={query.isPending}
            error={query.error}
            retry={query.refetch}
          />
          {query.data && (
            <>
              <p className="muted small">
                {query.data.employee.name} · {query.data.period.from_date} —{' '}
                {query.data.period.to_date} · Times in {profile!.app.timezone}
              </p>
              <SummaryCards summary={query.data.summary} />
              <div
                className="actions"
                role="group"
                aria-label="Attendance display"
              >
                <button
                  className={tab === 'table' ? '' : 'secondary'}
                  aria-pressed={tab === 'table'}
                  onClick={() => setTab('table')}
                >
                  Table
                </button>
                <button
                  className={tab === 'calendar' ? '' : 'secondary'}
                  aria-pressed={tab === 'calendar'}
                  onClick={() => setTab('calendar')}
                >
                  Calendar
                </button>
              </div>
              {tab === 'calendar' ? (
                <AttendanceCalendar
                  entries={query.data.entries}
                  timezone={profile!.app.timezone}
                />
              ) : (
                <>
                  <AttendanceTable
                    entries={query.data.entries.slice(
                      (page - 1) * 31,
                      page * 31,
                    )}
                    timezone={profile!.app.timezone}
                    onEdit={
                      can('attendance.update.any', 'attendance.update.team')
                        ? setEdit
                        : undefined
                    }
                  />
                  <div className="pagination">
                    <button
                      className="secondary"
                      disabled={page === 1}
                      onClick={() => setPage(page - 1)}
                    >
                      Earlier dates
                    </button>
                    <span>
                      Page {page} of{' '}
                      {Math.max(1, Math.ceil(query.data.entries.length / 31))}
                    </span>
                    <button
                      className="secondary"
                      disabled={page * 31 >= query.data.entries.length}
                      onClick={() => setPage(page + 1)}
                    >
                      Later dates
                    </button>
                  </div>
                </>
              )}
            </>
          )}
        </>
      )}
      {edit && <AttendanceEditor entry={edit} onClose={() => setEdit(null)} />}
    </section>
  )
}
