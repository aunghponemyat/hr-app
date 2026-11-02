import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useApi } from '../api/useApi'
import { errorMessage } from '../api/errors'
import { useAuthState } from '../auth/useAuthState'
import { usePermissions } from '../hooks/usePermissions'
import type { LeaveRequest, LeaveStatus, Page } from '../types/domain'
import { Dialog } from './Dialog'
import { DataTable, Pagination } from './DataTable'
import { QueryFeedback, StatusBanner } from './Feedback'
import { statusLabel } from '../utils/status'
import { TextAreaField } from './Fields'

export function LeaveList({
  team = false,
  employeeId,
}: {
  team?: boolean
  employeeId?: number
}) {
  const api = useApi(),
    client = useQueryClient(),
    can = usePermissions(),
    { profile } = useAuthState()
  const [page, setPage] = useState(1),
    [status, setStatus] = useState<LeaveStatus | ''>(team ? 'pending' : '')
  const [decision, setDecision] = useState<{
    request: LeaveRequest
    action: 'approve' | 'reject' | 'cancel'
  } | null>(null)
  const [note, setNote] = useState('')
  const query = useQuery({
    queryKey: ['leave', team ? 'team' : 'self', status, page, employeeId],
    queryFn: ({ signal }) =>
      api.get<Page<LeaveRequest>>(
        team ? '/leave-requests/team' : '/leave-requests',
        {
          page,
          page_size: 25,
          status: status || undefined,
          ...(team && employeeId ? { employee_id: employeeId } : {}),
        },
        signal,
      ),
  })
  const mutate = useMutation({
    mutationFn: () =>
      api.post<LeaveRequest>(
        `/leave-requests/${decision!.request.id}/${decision!.action}`,
        decision!.action === 'cancel'
          ? undefined
          : { decision_note: note || null },
      ),
    onSuccess: () => {
      setDecision(null)
      setNote('')
      void client.invalidateQueries({ queryKey: ['leave'] })
      void client.invalidateQueries({ queryKey: ['attendance'] })
      void client.invalidateQueries({ queryKey: ['team'] })
    },
  })
  const open = (
    request: LeaveRequest,
    action: 'approve' | 'reject' | 'cancel',
  ) => {
    mutate.reset()
    setNote('')
    setDecision({ request, action })
  }
  return (
    <section className="card">
      <div className="section-heading">
        <h2>{team ? 'Leave requests in scope' : 'My leave requests'}</h2>
        <label className="field compact-filter">
          Status
          <select
            value={status}
            onChange={(event) => {
              setStatus(event.target.value as LeaveStatus | '')
              setPage(1)
            }}
          >
            <option value="">All statuses</option>
            {['pending', 'approved', 'rejected', 'cancelled'].map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
      </div>
      <QueryFeedback
        pending={query.isPending}
        error={query.error}
        retry={query.refetch}
      />
      {query.data && (
        <>
          <DataTable
            caption="Leave requests"
            items={query.data.items}
            rowKey={(request) => request.id}
            columns={[
              ...(team
                ? [
                    {
                      label: 'Employee',
                      render: (request: LeaveRequest) => request.employee.name,
                    },
                  ]
                : []),
              {
                label: 'Leave',
                render: (request) => (
                  <>
                    <strong>{request.leave_type.name}</strong>
                    <p className="small">
                      {request.leave_reason.name}
                      {request.reason_text ? ` · ${request.reason_text}` : ''}
                    </p>
                  </>
                ),
              },
              {
                label: 'Dates',
                render: (request) => (
                  <>
                    {request.start_date} — {request.end_date}
                    <p className="small">
                      {request.num_days} days {request.half_day_period || ''}
                    </p>
                  </>
                ),
              },
              {
                label: 'Manager',
                render: (request) => request.reporting_manager.name,
              },
              {
                label: 'Status',
                render: (request) => (
                  <>
                    <span className={`badge status-${request.status}`}>
                      {statusLabel(request.status)}
                    </span>
                    {request.decision_note && (
                      <p className="small">{request.decision_note}</p>
                    )}
                    {request.decided_by && (
                      <p className="small">By {request.decided_by.name}</p>
                    )}
                  </>
                ),
              },
              { label: 'Remark', render: (request) => request.remark || '—' },
              {
                label: 'Actions',
                render: (request) => (
                  <div className="actions">
                    {request.employee.id === profile!.id &&
                      (request.status === 'pending' ||
                        (request.status === 'approved' &&
                          request.start_date > profile!.app.today)) && (
                        <button
                          className="secondary"
                          onClick={() => open(request, 'cancel')}
                        >
                          Cancel request
                        </button>
                      )}
                    {team &&
                      request.status === 'pending' &&
                      request.employee.id !== profile!.id &&
                      (can('leave.decide.any') ||
                        (can('leave.decide.team') &&
                          request.reporting_manager.id === profile!.id)) && (
                        <>
                          <button onClick={() => open(request, 'approve')}>
                            Approve
                          </button>
                          <button
                            className="secondary"
                            onClick={() => open(request, 'reject')}
                          >
                            Reject
                          </button>
                        </>
                      )}
                  </div>
                ),
              },
            ]}
          />
          <Pagination page={page} total={query.data.total} onChange={setPage} />
        </>
      )}
      {decision && (
        <Dialog
          title={`${statusLabel(decision.action)} leave request?`}
          onClose={() => setDecision(null)}
          busy={mutate.isPending}
        >
          <p>
            {decision.request.employee.name} · {decision.request.start_date} —{' '}
            {decision.request.end_date}
          </p>
          {decision.action !== 'cancel' && (
            <TextAreaField
              id="decision-note"
              label="Decision note (optional)"
              value={note}
              maxLength={500}
              onChange={(event) => setNote(event.target.value)}
            />
          )}
          <StatusBanner
            message={mutate.error ? errorMessage(mutate.error) : null}
            error
          />
          <div className="actions dialog-actions">
            <button
              className="secondary"
              disabled={mutate.isPending}
              onClick={() => setDecision(null)}
            >
              Go back
            </button>
            <button disabled={mutate.isPending} onClick={() => mutate.mutate()}>
              {mutate.isPending ? 'Saving…' : 'Confirm'}
            </button>
          </div>
        </Dialog>
      )}
    </section>
  )
}
