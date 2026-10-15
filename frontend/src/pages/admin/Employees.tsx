import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useApi } from '../../api/useApi'
import { errorMessage } from '../../api/errors'
import { useAuth } from '../../auth/context'
import { useAuthState } from '../../auth/useAuthState'
import { usePermissions } from '../../hooks/usePermissions'
import type { Employee, Page, Role, Team } from '../../types/domain'
import { DataTable, Pagination } from '../../components/DataTable'
import { QueryFeedback, StatusBanner } from '../../components/Feedback'
import { ConfirmDialog } from '../../components/Dialog'
import { PasswordHandover } from '../../components/PasswordHandover'
import type { Handover } from '../../components/PasswordHandover'
import { EmployeeEditor } from './EmployeeEditor'
import { PasswordReset } from './PasswordReset'

export function Employees() {
  const api = useApi(),
    client = useQueryClient(),
    can = usePermissions(),
    session = useAuth(),
    { profile } = useAuthState()
  const [page, setPage] = useState(1),
    [search, setSearch] = useState(''),
    [role, setRole] = useState(''),
    [team, setTeam] = useState(''),
    [active, setActive] = useState('')
  const [editor, setEditor] = useState<Employee | 'new' | null>(null),
    [reset, setReset] = useState<Employee | null>(null),
    [toggle, setToggle] = useState<Employee | null>(null),
    [handover, setHandover] = useState<Handover | null>(null)
  const roles = useQuery({
    queryKey: ['admin', 'roles'],
    queryFn: ({ signal }) => api.all<Role>('/admin/roles', undefined, signal),
  })
  const teams = useQuery({
    queryKey: ['admin', 'team-choices'],
    queryFn: ({ signal }) => api.all<Team>('/admin/teams', undefined, signal),
    enabled: can('team.manage.any'),
  })
  const query = useQuery({
    queryKey: ['admin', 'employees', page, search, role, team, active],
    queryFn: ({ signal }) =>
      api.get<Page<Employee>>(
        '/admin/employees',
        {
          page,
          page_size: 25,
          search: search || undefined,
          role_id: role ? Number(role) : undefined,
          team_id: team ? Number(team) : undefined,
          is_active: active ? active === 'true' : undefined,
        },
        signal,
      ),
  })
  const refresh = () => {
    void client.invalidateQueries({ queryKey: ['admin'] })
    void client.invalidateQueries({ queryKey: ['team'] })
  }
  const activation = useMutation({
    mutationFn: (employee: Employee) =>
      api.patch(`/admin/employees/${employee.id}`, {
        is_active: !employee.is_active,
      }),
    onSuccess: () => {
      if (toggle?.id === profile!.id) session.clearSession()
      setToggle(null)
      refresh()
    },
  })
  const saved = (value?: Handover) => {
    const selfEdited = typeof editor === 'object' && editor?.id === profile!.id
    setEditor(null)
    setReset(null)
    setHandover(value || null)
    if (!value || value.employee_id !== profile!.employee_id) refresh()
    if (selfEdited && !value) void session.reloadProfile()
  }
  return (
    <div className="page-stack">
      <div className="section-heading">
        <h1>Employees</h1>
        {can('employee.create.any') && (
          <button onClick={() => setEditor('new')}>Create employee</button>
        )}
      </div>
      <section className="card">
        <div className="filters">
          <label>
            Search
            <input
              type="search"
              value={search}
              maxLength={100}
              onChange={(event) => {
                setSearch(event.target.value)
                setPage(1)
              }}
              placeholder="ID or name"
            />
          </label>
          <label>
            Role
            <select
              value={role}
              onChange={(event) => {
                setRole(event.target.value)
                setPage(1)
              }}
            >
              <option value="">All roles</option>
              {roles.data?.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          {can('team.manage.any') && (
            <label>
              Team
              <select
                value={team}
                onChange={(event) => {
                  setTeam(event.target.value)
                  setPage(1)
                }}
              >
                <option value="">All teams</option>
                {teams.data?.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label>
            Account status
            <select
              value={active}
              onChange={(event) => {
                setActive(event.target.value)
                setPage(1)
              }}
            >
              <option value="">All accounts</option>
              <option value="true">Active</option>
              <option value="false">Inactive</option>
            </select>
          </label>
        </div>
        <QueryFeedback
          pending={query.isPending}
          error={query.error}
          retry={query.refetch}
        />
        {roles.isError && (
          <QueryFeedback
            pending={false}
            error={roles.error}
            retry={roles.refetch}
          />
        )}
        {query.data && (
          <>
            <DataTable
              caption="Employees"
              items={query.data.items}
              rowKey={(employee) => employee.id}
              columns={[
                {
                  label: 'Employee ID',
                  render: (employee) => employee.employee_id,
                },
                {
                  label: 'Name',
                  render: (employee) =>
                    employee.display_name ||
                    `${employee.first_name} ${employee.last_name}`,
                },
                { label: 'Role', render: (employee) => employee.role.name },
                {
                  label: 'Team',
                  render: (employee) => employee.team?.name || 'Unassigned',
                },
                {
                  label: 'Status',
                  render: (employee) =>
                    employee.is_active ? 'Active' : 'Inactive',
                },
                {
                  label: 'Actions',
                  render: (employee) =>
                    can('employee.update.any') && (
                      <div className="actions">
                        <button
                          className="secondary"
                          disabled={!roles.data}
                          onClick={() => setEditor(employee)}
                        >
                          Edit
                        </button>
                        <button
                          className="secondary"
                          onClick={() => setReset(employee)}
                        >
                          Reset password
                        </button>
                        <button
                          className="secondary"
                          onClick={() => {
                            activation.reset()
                            setToggle(employee)
                          }}
                        >
                          {employee.is_active ? 'Deactivate' : 'Activate'}
                        </button>
                      </div>
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
      </section>
      {editor && (
        <EmployeeEditor
          employee={editor === 'new' ? null : editor}
          roles={roles.data || []}
          teams={teams.data || []}
          onClose={() => setEditor(null)}
          onSaved={saved}
        />
      )}
      {reset && (
        <PasswordReset
          employee={reset}
          onClose={() => setReset(null)}
          onSaved={saved}
        />
      )}
      {handover && (
        <PasswordHandover
          value={handover}
          onClose={() => {
            const self = handover.employee_id === profile!.employee_id
            setHandover(null)
            if (self) session.clearSession()
          }}
        />
      )}
      {toggle && (
        <ConfirmDialog
          title={`${toggle.is_active ? 'Deactivate' : 'Activate'} ${toggle.employee_id}?`}
          onClose={() => setToggle(null)}
          onConfirm={() => activation.mutate(toggle)}
          busy={activation.isPending}
        >
          <span>
            {toggle.is_active
              ? 'The employee will lose access immediately; their history will be retained.'
              : 'The employee will be able to sign in again.'}
          </span>
          <StatusBanner
            message={activation.error ? errorMessage(activation.error) : null}
            error
          />
        </ConfirmDialog>
      )}
    </div>
  )
}
