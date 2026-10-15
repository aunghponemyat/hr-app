import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useApi } from '../api/useApi'
import { errorMessage } from '../api/errors'
import { useAuthState } from '../auth/useAuthState'
import { useGeolocation } from '../hooks/useGeolocation'
import { usePermissions } from '../hooks/usePermissions'
import type { ClockResult, Today, WorkMode } from '../types/domain'
import { officeTime } from '../utils/dates'
import { ConfirmDialog } from './Dialog'
import { QueryFeedback, StatusBanner } from './Feedback'

interface Notice {
  message: string
  error: boolean
}
export function ClockPanel() {
  const api = useApi(),
    client = useQueryClient(),
    can = usePermissions()
  const { profile } = useAuthState()
  const { permission, locate } = useGeolocation()
  const [mode, setMode] = useState<WorkMode>('onsite')
  const [confirm, setConfirm] = useState<'clock_in' | 'clock_out' | null>(null)
  const today = useQuery({
    queryKey: ['attendance', 'today'],
    queryFn: ({ signal }) =>
      api.get<Today>('/attendance/today', undefined, signal),
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
  })
  const date = today.data?.date || profile!.app.today
  const noticeKey = ['clock-notice', profile!.id, date]
  const notice = useQuery<Notice | null>({
    queryKey: noticeKey,
    queryFn: async () => null,
    enabled: false,
    gcTime: Infinity,
  })
  const workMode = today.data?.attendance?.clock_in
    ? today.data.attendance.work_mode
    : mode
  const clock = useMutation({
    mutationFn: async (action: 'clock_in' | 'clock_out') => {
      const coordinates = workMode === 'onsite' ? await locate() : {}
      return api.post<ClockResult>(`/attendance/${action.replace('_', '-')}`, {
        work_mode: workMode,
        ...coordinates,
      })
    },
    onSuccess: (result) => {
      client.setQueryData(
        ['clock-notice', profile!.id, result.attendance.attendance_date],
        { message: result.message, error: false },
      )
    },
    onError: (error) => {
      client.setQueryData(noticeKey, {
        message: errorMessage(error),
        error: true,
      })
    },
    onSettled: () => {
      setConfirm(null)
      void client.invalidateQueries({ queryKey: ['attendance'] })
      void client.invalidateQueries({ queryKey: ['team'] })
    },
  })
  const disabled =
    clock.isPending ||
    today.isFetching ||
    !can('attendance.create.self', 'attendance.create.any')
  return (
    <section className="card clock-panel" aria-labelledby="clock-heading">
      <div className="section-heading">
        <div>
          <p className="eyebrow">
            {date} · {profile!.app.timezone}
          </p>
          <h2 id="clock-heading">Today’s attendance</h2>
        </div>
        <span className="badge">
          {today.data?.next_action === 'none'
            ? 'Completed'
            : today.data?.attendance
              ? 'Clocked in'
              : 'Not clocked in'}
        </span>
      </div>
      <QueryFeedback
        pending={today.isPending}
        error={today.error}
        retry={today.refetch}
      />
      {today.data && (
        <>
          <div className="clock-times">
            <p>
              Clock in{' '}
              <strong>
                {officeTime(
                  today.data.attendance?.clock_in || null,
                  profile!.app.timezone,
                )}
              </strong>
            </p>
            <p>
              Clock out{' '}
              <strong>
                {officeTime(
                  today.data.attendance?.clock_out || null,
                  profile!.app.timezone,
                )}
              </strong>
            </p>
          </div>
          <fieldset disabled={disabled || !!today.data.attendance?.clock_in}>
            <legend>Work mode</legend>
            <div className="actions">
              {(['onsite', 'remote'] as const).map((value) => (
                <label className="radio-label" key={value}>
                  <input
                    type="radio"
                    name="work-mode"
                    value={value}
                    checked={workMode === value}
                    onChange={() => setMode(value)}
                  />
                  {value === 'onsite' ? 'Onsite' : 'Remote'}
                </label>
              ))}
            </div>
          </fieldset>
          {workMode === 'onsite' && (
            <p className="muted small">
              Location permission: {permission}. Your location is requested
              after confirmation.
            </p>
          )}
          <div className="actions">
            <button
              disabled={disabled || today.data.next_action !== 'clock_in'}
              onClick={() => setConfirm('clock_in')}
            >
              Clock in
            </button>
            <button
              className="secondary"
              disabled={disabled || today.data.next_action !== 'clock_out'}
              onClick={() => setConfirm('clock_out')}
            >
              Clock out
            </button>
          </div>
          {today.data.next_action === 'none' && <p>You’re done for today.</p>}
        </>
      )}
      <StatusBanner
        message={notice.data?.message || null}
        error={notice.data?.error}
      />
      {notice.data?.error && today.data?.next_action !== 'none' && (
        <button
          className="secondary"
          disabled={disabled}
          onClick={() => {
            if (today.data)
              setConfirm(
                today.data.next_action === 'clock_out'
                  ? 'clock_out'
                  : 'clock_in',
              )
          }}
        >
          Try again
        </button>
      )}
      {confirm && (
        <ConfirmDialog
          title={`Clock ${confirm === 'clock_in' ? 'in' : 'out'} now as ${workMode === 'onsite' ? 'Onsite' : 'Remote'}?`}
          busy={clock.isPending}
          onClose={() => setConfirm(null)}
          onConfirm={() => clock.mutate(confirm)}
        >
          {workMode === 'onsite'
            ? 'Your current location will be checked against your assigned office perimeter.'
            : 'This will record your remote attendance using the server time.'}
        </ConfirmDialog>
      )}
    </section>
  )
}
