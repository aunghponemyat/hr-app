import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useApi } from '../../api/useApi'
import { useAuthState } from '../../auth/useAuthState'
import { usePermissions } from '../../hooks/usePermissions'
import type {
  AttendanceTable,
  CalendarEntry,
  Employee,
} from '../../types/domain'
import {
  initialPeriod,
  periodBounds,
  periodParams,
  rangeError,
  officeTime,
} from '../../utils/dates'
import { PeriodFilter } from '../../components/PeriodFilter'
import { DataTable, Pagination } from '../../components/DataTable'
import { SelectField } from '../../components/Fields'
import { QueryFeedback } from '../../components/Feedback'
import { AttendanceOverview } from '../../components/AttendanceOverview'
import { AttendanceEditor } from '../../components/AttendanceEditor'
import { statusLabel } from '../../utils/status'

export function AllAttendance() {
  const api = useApi(),
    can = usePermissions(),
    { profile } = useAuthState()
  const [period, setPeriod] = useState(() => initialPeriod(profile!.app.today)),
    [page, setPage] = useState(1),
    [employee, setEmployee] = useState(''),
    [selected, setSelected] = useState<number | null>(null),
    [edit, setEdit] = useState<CalendarEntry | null>(null)
  const bounds = periodBounds(period),
    invalid = rangeError(
      bounds.from,
      bounds.to,
      profile!.app.max_report_range_days,
    )
  const employees = useQuery({
    queryKey: ['admin', 'employee-choices'],
    queryFn: ({ signal }) =>
      api.all<Employee>('/admin/employees', undefined, signal),
    enabled: can('employee.read.any'),
  })
  const query = useQuery({
    queryKey: ['attendance', 'all', period, page, employee],
    queryFn: ({ signal }) =>
      api.get<AttendanceTable>(
        '/attendance',
        {
          ...periodParams(period),
          page,
          page_size: 25,
          employee_id: employee ? Number(employee) : undefined,
        },
        signal,
      ),
    enabled: !invalid,
  })
  return (
    <div className="page-stack">
      <h1>All attendance</h1>
      <section className="card">
        <PeriodFilter
          value={period}
          onChange={(value) => {
            setPeriod(value)
            setPage(1)
          }}
          years={[]}
          maxDays={profile!.app.max_report_range_days}
        />
        {can('employee.read.any') && (
          <SelectField
            id="all-employee"
            label="Employee"
            value={employee}
            onChange={(event) => {
              setEmployee(event.target.value)
              setPage(1)
            }}
          >
            <option value="">All employees</option>
            {employees.data?.map((item) => (
              <option key={item.id} value={item.id}>
                {item.display_name || `${item.first_name} ${item.last_name}`} (
                {item.employee_id})
              </option>
            ))}
          </SelectField>
        )}
        {!invalid && (
          <>
            <QueryFeedback
              pending={query.isPending}
              error={query.error}
              retry={query.refetch}
            />
            {query.data && (
              <>
                <DataTable
                  caption="Company attendance"
                  items={query.data.items}
                  rowKey={(row) => `${row.employee.id}-${row.date}`}
                  columns={[
                    {
                      label: 'Employee',
                      render: (row) => (
                        <button
                          className="text-button"
                          onClick={() => setSelected(row.employee.id)}
                        >
                          {row.employee.name} ({row.employee.employee_id})
                        </button>
                      ),
                    },
                    {
                      label: 'Team',
                      render: (row) => row.employee.team?.name || 'Unassigned',
                    },
                    { label: 'Date', render: (row) => row.date },
                    {
                      label: 'Status',
                      render: (row) => statusLabel(row.display_status),
                    },
                    { label: 'Mode', render: (row) => row.work_mode || '—' },
                    {
                      label: 'Clock in',
                      render: (row) =>
                        officeTime(row.clock_in, profile!.app.timezone),
                    },
                    {
                      label: 'Clock out',
                      render: (row) =>
                        officeTime(row.clock_out, profile!.app.timezone),
                    },
                    {
                      label: 'Hours',
                      render: (row) => row.worked_hours.toFixed(2),
                    },
                    {
                      label: 'Actions',
                      render: (row) =>
                        row.attendance_id &&
                        can('attendance.update.any') && (
                          <button
                            className="secondary"
                            onClick={() => setEdit(row)}
                          >
                            Correct attendance
                          </button>
                        ),
                    },
                  ]}
                />
                <Pagination
                  page={page}
                  total={query.data.total}
                  onChange={setPage}
                />
              </>
            )}
          </>
        )}
      </section>
      {selected && (
        <>
          <button className="secondary" onClick={() => setSelected(null)}>
            Close employee view
          </button>
          <AttendanceOverview key={selected} employeeId={selected} />
        </>
      )}
      {edit && <AttendanceEditor entry={edit} onClose={() => setEdit(null)} />}
    </div>
  )
}
