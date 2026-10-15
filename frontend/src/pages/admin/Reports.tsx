import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useApi } from '../../api/useApi'
import { useAuthState } from '../../auth/useAuthState'
import { usePermissions } from '../../hooks/usePermissions'
import { useDownload } from '../../hooks/useDownload'
import type { Employee, Team } from '../../types/domain'
import { initialPeriod, periodBounds, rangeError } from '../../utils/dates'
import { PeriodFilter } from '../../components/PeriodFilter'
import { SelectField } from '../../components/Fields'
import { FormField } from '../../components/FormField'
import { StatusBanner } from '../../components/Feedback'

export function Reports() {
  const { profile } = useAuthState(),
    api = useApi(),
    can = usePermissions(),
    { download, busy, error } = useDownload()
  const [period, setPeriod] = useState(() => initialPeriod(profile!.app.today)),
    [team, setTeam] = useState(''),
    [employee, setEmployee] = useState('')
  const employees = useQuery({
    queryKey: ['admin', 'employee-choices'],
    queryFn: ({ signal }) =>
      api.all<Employee>('/admin/employees', undefined, signal),
    enabled: can('employee.read.any'),
  })
  const teams = useQuery({
    queryKey: ['admin', 'team-choices'],
    queryFn: ({ signal }) => api.all<Team>('/admin/teams', undefined, signal),
    enabled: can('team.manage.any'),
  })
  const bounds = periodBounds(period),
    invalid = rangeError(
      bounds.from,
      bounds.to,
      profile!.app.max_report_range_days,
    )
  return (
    <div className="page-stack">
      <h1>Reports</h1>
      <section className="card">
        <h2>Company exports</h2>
        <p className="muted">
          Download attendance or leave as a UTF-8 CSV for the selected period.
          Leave reports include all statuses overlapping these dates.
        </p>
        <PeriodFilter
          value={period}
          onChange={setPeriod}
          years={[]}
          maxDays={profile!.app.max_report_range_days}
        />
        <div className="filters">
          {can('team.manage.any') ? (
            <SelectField
              id="report-team"
              label="Team"
              value={team}
              onChange={(event) => {
                setTeam(event.target.value)
                setEmployee('')
              }}
            >
              <option value="">All teams</option>
              {teams.data?.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </SelectField>
          ) : (
            <FormField
              id="report-team"
              label="Team internal ID (optional)"
              type="number"
              min={1}
              value={team}
              onChange={(event) => setTeam(event.target.value)}
            />
          )}
          {can('employee.read.any') ? (
            <SelectField
              id="report-employee"
              label="Employee"
              value={employee}
              onChange={(event) => setEmployee(event.target.value)}
            >
              <option value="">All employees</option>
              {employees.data
                ?.filter((item) => !team || item.team?.id === Number(team))
                .map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.display_name ||
                      `${item.first_name} ${item.last_name}`}{' '}
                    ({item.employee_id})
                  </option>
                ))}
            </SelectField>
          ) : (
            <FormField
              id="report-employee"
              label="Employee internal ID (optional)"
              type="number"
              min={1}
              value={employee}
              onChange={(event) => setEmployee(event.target.value)}
            />
          )}
        </div>
        <StatusBanner message={error} error />
        <div className="actions">
          {['attendance', 'leave'].map((kind) => (
            <button
              key={kind}
              disabled={busy || !!invalid}
              onClick={() =>
                void download(`/admin/reports/${kind}.csv`, {
                  ...bounds,
                  team_id: team ? Number(team) : undefined,
                  employee_id: employee ? Number(employee) : undefined,
                })
              }
            >
              {busy ? 'Preparing download…' : `Download ${kind} CSV`}
            </button>
          ))}
        </div>
      </section>
    </div>
  )
}
