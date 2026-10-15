import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useApi } from '../../api/useApi'
import { errorMessage } from '../../api/errors'
import { usePermissions } from '../../hooks/usePermissions'
import type {
  Employee,
  Location,
  Manager,
  Role,
  Team,
} from '../../types/domain'
import { Dialog, ConfirmDialog } from '../../components/Dialog'
import { DataTable, Pagination } from '../../components/DataTable'
import { QueryFeedback, StatusBanner } from '../../components/Feedback'
import { SelectField } from '../../components/Fields'
import { FormField } from '../../components/FormField'

type Kind = 'members' | 'managers' | 'locations'
interface Item {
  id: number
  name: string
}
export function TeamAssociations({
  team,
  onClose,
}: {
  team: Team
  onClose: () => void
}) {
  const [kind, setKind] = useState<Kind>('members')
  const [busy, setBusy] = useState(false)
  return (
    <Dialog
      title={`Manage team · ${team.name}`}
      onClose={onClose}
      busy={busy}
      drawer
    >
      <div className="actions" role="group" aria-label="Team assignments">
        {(['members', 'managers', 'locations'] as const).map((value) => (
          <button
            className={kind === value ? '' : 'secondary'}
            aria-pressed={kind === value}
            key={value}
            disabled={busy}
            onClick={() => setKind(value)}
          >
            {value[0].toUpperCase() + value.slice(1)}
          </button>
        ))}
      </div>
      <AssociationList key={kind} team={team} kind={kind} onBusy={setBusy} />
    </Dialog>
  )
}
function AssociationList({
  team,
  kind,
  onBusy,
}: {
  team: Team
  kind: Kind
  onBusy: (busy: boolean) => void
}) {
  const api = useApi(),
    client = useQueryClient(),
    can = usePermissions()
  const [choice, setChoice] = useState(''),
    [remove, setRemove] = useState<Item | null>(null)
  const [page, setPage] = useState(1)
  const path = `/admin/teams/${team.id}/${kind}`
  const current = useQuery({
    queryKey: ['admin', 'team', team.id, kind],
    queryFn: ({ signal }) =>
      api.all<Employee | Manager | Location>(path, undefined, signal),
  })
  const employees = useQuery({
    queryKey: ['admin', 'active-employee-choices'],
    queryFn: ({ signal }) =>
      api.all<Employee>('/admin/employees', { is_active: true }, signal),
    enabled: kind !== 'locations' && can('employee.read.any'),
  })
  const roles = useQuery({
    queryKey: ['admin', 'roles'],
    queryFn: ({ signal }) => api.all<Role>('/admin/roles', undefined, signal),
    enabled: kind === 'managers' && can('employee.read.any'),
  })
  const locations = useQuery({
    queryKey: ['admin', 'location-choices'],
    queryFn: ({ signal }) =>
      api.all<Location>('/admin/work-locations', undefined, signal),
    enabled: kind === 'locations' && can('location.manage.any'),
  })
  const linked =
    current.data?.map((item): Item => {
      if ('employee' in item)
        return {
          id: item.employee.id,
          name: `${item.employee.display_name || `${item.employee.first_name} ${item.employee.last_name}`} (${item.employee.employee_id})`,
        }
      if ('first_name' in item)
        return {
          id: item.id,
          name: `${item.display_name || `${item.first_name} ${item.last_name}`} (${item.employee_id})`,
        }
      return { id: item.id, name: `${item.name} · ${item.allowed_radius_m} m` }
    }) || []
  const permittedRoles = new Set(
    roles.data
      ?.filter((role) =>
        role.permissions.some((permission) =>
          ['attendance.read.team', 'attendance.read.any'].includes(permission),
        ),
      )
      .map((role) => role.id),
  )
  const candidates: Item[] =
    kind === 'locations'
      ? locations.data?.map((location) => ({
          id: location.id,
          name: location.name,
        })) || []
      : employees.data
          ?.filter(
            (employee) =>
              kind !== 'managers' || permittedRoles.has(employee.role.id),
          )
          .map((employee) => ({
            id: employee.id,
            name: `${employee.display_name || `${employee.first_name} ${employee.last_name}`} (${employee.employee_id})${kind === 'members' && employee.team && employee.team.id !== team.id ? ` · move from ${employee.team.name}` : ''}`,
          })) || []
  const refresh = () => {
    void client.invalidateQueries({ queryKey: ['admin'] })
    void client.invalidateQueries({ queryKey: ['team'] })
    void client.invalidateQueries({ queryKey: ['leave'] })
  }
  const add = useMutation({
    mutationFn: () =>
      api.post(path, {
        [kind === 'locations' ? 'work_location_id' : 'employee_id']:
          Number(choice),
      }),
    onSuccess: () => {
      setChoice('')
      refresh()
    },
  })
  const unlink = useMutation({
    mutationFn: (item: Item) => api.remove(`${path}/${item.id}`),
    onSuccess: () => {
      setRemove(null)
      refresh()
    },
  })
  useEffect(() => {
    onBusy(add.isPending || unlink.isPending)
  }, [add.isPending, unlink.isPending, onBusy])
  const hasChoices =
    kind === 'locations' ? can('location.manage.any') : can('employee.read.any')
  return (
    <section>
      <h3>
        {kind === 'members'
          ? 'Current members'
          : kind === 'managers'
            ? 'Active managers'
            : 'Linked work locations'}
      </h3>
      {kind === 'members' && (
        <p className="muted small">
          Adding an employee moves their current team and preserves membership
          history.
        </p>
      )}
      <QueryFeedback
        pending={current.isPending}
        error={current.error}
        retry={current.refetch}
      />
      {current.data && (
        <DataTable
          caption={`Team ${kind}`}
          items={linked.slice((page - 1) * 25, page * 25)}
          rowKey={(item) => item.id}
          columns={[
            { label: 'Name', render: (item) => item.name },
            {
              label: 'Actions',
              render: (item) => (
                <button
                  className="secondary"
                  disabled={add.isPending || unlink.isPending}
                  onClick={() => {
                    unlink.reset()
                    setRemove(item)
                  }}
                >
                  Remove
                </button>
              ),
            },
          ]}
        />
      )}
      {current.data && (
        <Pagination page={page} total={linked.length} onChange={setPage} />
      )}
      {hasChoices ? (
        <SelectField
          id={`assign-${kind}`}
          label={
            kind === 'locations'
              ? 'Work location to link'
              : kind === 'managers'
                ? 'Manager to assign'
                : 'Employee to add or move'
          }
          value={choice}
          onChange={(event) => setChoice(event.target.value)}
        >
          <option value="">Choose</option>
          {candidates
            .filter((item) => !linked.some((row) => row.id === item.id))
            .map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
        </SelectField>
      ) : (
        <FormField
          id={`assign-${kind}`}
          label={
            kind === 'locations'
              ? 'Work location internal ID'
              : 'Employee internal ID'
          }
          value={choice}
          type="number"
          min={1}
          onChange={(event) => setChoice(event.target.value)}
        />
      )}
      <StatusBanner
        message={add.error ? errorMessage(add.error) : null}
        error
      />
      <button
        disabled={
          !/^[1-9]\d*$/.test(choice) || add.isPending || unlink.isPending
        }
        onClick={() => add.mutate()}
      >
        {add.isPending
          ? 'Saving…'
          : kind === 'locations'
            ? 'Link location'
            : kind === 'managers'
              ? 'Assign manager'
              : 'Add member'}
      </button>
      {remove && (
        <ConfirmDialog
          title={`Remove ${remove.name}?`}
          busy={unlink.isPending}
          onClose={() => setRemove(null)}
          onConfirm={() => unlink.mutate(remove)}
        >
          <span>
            This removes the current link and preserves existing history.
          </span>
          <StatusBanner
            message={unlink.error ? errorMessage(unlink.error) : null}
            error
          />
        </ConfirmDialog>
      )}
    </section>
  )
}
