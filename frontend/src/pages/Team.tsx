import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useApi } from '../api/useApi'
import { useAuthState } from '../auth/useAuthState'
import { usePermissions } from '../hooks/usePermissions'
import type { Page, TeamMember, TeamSummary } from '../types/domain'
import {
  initialPeriod,
  periodBounds,
  periodParams,
  rangeError,
  historyStart,
} from '../utils/dates'
import { QueryFeedback } from '../components/Feedback'
import { DataTable, Pagination } from '../components/DataTable'
import { LeaveList } from '../components/LeaveList'
import { AttendanceOverview } from '../components/AttendanceOverview'
import { PeriodFilter } from '../components/PeriodFilter'
import { statusLabel } from '../utils/status'

export function Team() {
  const api = useApi(),
    can = usePermissions(),
    { profile } = useAuthState()
  const [tab, setTab] = useState<'members' | 'leave'>('members'),
    [page, setPage] = useState(1),
    [selected, setSelected] = useState<TeamMember | null>(null)
  const [period, setPeriod] = useState(() => initialPeriod(profile!.app.today))
  const earliest = can('attendance.read.any')
      ? undefined
      : historyStart(profile!.app.today),
    bounds = periodBounds(period)
  const invalid = rangeError(
    bounds.from,
    bounds.to,
    profile!.app.max_report_range_days,
    earliest,
  )
  const roster = useQuery({
    queryKey: ['team', 'members', page],
    queryFn: ({ signal }) =>
      api.get<Page<TeamMember>>(
        '/team/members',
        { page, page_size: 25 },
        signal,
      ),
    enabled: tab === 'members',
  })
  const summaries = useQuery({
    queryKey: ['team', 'summaries', page, period],
    queryFn: ({ signal }) =>
      api.get<TeamSummary>(
        '/team/attendance',
        { ...periodParams(period), page, page_size: 25 },
        signal,
      ),
    enabled:
      tab === 'members' &&
      can('attendance.read.team', 'attendance.read.any') &&
      !invalid,
  })
  const byId = new Map(
    summaries.data?.items.map((item) => [item.employee.id, item.summary]),
  )
  return (
    <div className="page-stack">
      <h1>Team</h1>
      <div className="actions" role="group" aria-label="Team views">
        <button
          className={tab === 'members' ? '' : 'secondary'}
          aria-pressed={tab === 'members'}
          onClick={() => setTab('members')}
        >
          Members
        </button>
        {can('leave.read.team', 'leave.read.any') && (
          <button
            className={tab === 'leave' ? '' : 'secondary'}
            aria-pressed={tab === 'leave'}
            onClick={() => setTab('leave')}
          >
            Leave approvals
          </button>
        )}
      </div>
      {tab === 'leave' ? (
        <LeaveList team />
      ) : (
        <>
          <section className="card">
            <h2>Members in scope</h2>
            <PeriodFilter
              value={period}
              onChange={setPeriod}
              years={[]}
              maxDays={profile!.app.max_report_range_days}
              earliest={earliest}
            />
            <QueryFeedback
              pending={roster.isPending}
              error={roster.error}
              retry={roster.refetch}
            />
            {summaries.isError && (
              <QueryFeedback
                pending={false}
                error={summaries.error}
                retry={summaries.refetch}
              />
            )}
            {roster.data && (
              <>
                <DataTable
                  caption="Team members"
                  items={roster.data.items}
                  rowKey={(member) => member.id}
                  columns={[
                    {
                      label: 'Employee',
                      render: (member) => (
                        <>
                          {member.display_name ||
                            `${member.first_name} ${member.last_name}`}
                          <p className="muted small">{member.employee_id}</p>
                        </>
                      ),
                    },
                    {
                      label: 'Team',
                      render: (member) => member.team?.name || 'Unassigned',
                    },
                    {
                      label: 'Today',
                      render: (member) => statusLabel(member.today_status),
                    },
                    {
                      label: 'Summary',
                      render: (member) => {
                        const summary = invalid
                          ? undefined
                          : byId.get(member.id)
                        return summary
                          ? `${summary.present_days} present · ${summary.half_day_days} half-day · ${summary.leave_days} leave · ${summary.absent_days} absent · ${summary.total_worked_hours.toFixed(2)} hours`
                          : '—'
                      },
                    },
                    {
                      label: 'Actions',
                      render: (member) =>
                        can('attendance.read.team', 'attendance.read.any') && (
                          <button
                            className="secondary"
                            onClick={() => setSelected(member)}
                          >
                            View attendance
                          </button>
                        ),
                    },
                  ]}
                />
                <Pagination
                  page={page}
                  total={roster.data.total}
                  onChange={setPage}
                />
              </>
            )}
          </section>
          {selected && (
            <section className="page-stack">
              <div className="section-heading">
                <h2>
                  {selected.display_name ||
                    `${selected.first_name} ${selected.last_name}`}
                </h2>
                <button className="secondary" onClick={() => setSelected(null)}>
                  Close member view
                </button>
              </div>
              <AttendanceOverview key={selected.id} employeeId={selected.id} />
            </section>
          )}
        </>
      )}
    </div>
  )
}
