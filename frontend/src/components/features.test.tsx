import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useState } from 'react'
import { ClockPanel } from './ClockPanel'
import { AttendanceOverview } from './AttendanceOverview'
import { PeriodFilter } from './PeriodFilter'
import { ConfirmDialog } from './Dialog'
import { Leave } from '../pages/Leave'
import { LeaveList } from './LeaveList'
import { Profile } from '../pages/Profile'
import { Employees } from '../pages/admin/Employees'
import { Teams } from '../pages/admin/Teams'
import { TeamAssociations } from '../pages/admin/TeamAssociations'
import { Locations } from '../pages/admin/Locations'
import { Reports } from '../pages/admin/Reports'
import { Team } from '../pages/Team'
import { AllAttendance } from '../pages/admin/AllAttendance'
import {
  renderFeature,
  attendance,
  calendar,
  entry,
  identity,
  summary,
  request,
  employee,
  page,
} from '../test/features'
import {
  adminPermissions,
  selfPermissions,
  deferred,
  profile,
} from '../test/transport'
import type { Reply } from '../test/transport'
import { initialPeriod } from '../utils/dates'

let cleanup: (() => void) | undefined
beforeEach(() => {
  vi.stubGlobal('isSecureContext', true)
})
afterEach(() => {
  cleanup?.()
  vi.unstubAllGlobals()
})
const admin = [...selfPermissions, ...adminPermissions]
function geolocation(failure?: number) {
  const get = vi.fn(
    (success: PositionCallback, error?: PositionErrorCallback | null) =>
      failure
        ? error?.({ code: failure } as GeolocationPositionError)
        : success({
            coords: { latitude: 13.7563, longitude: 100.5018, accuracy: 8 },
          } as GeolocationPosition),
  )
  Object.defineProperty(navigator, 'geolocation', {
    configurable: true,
    value: { getCurrentPosition: get },
  })
  return get
}
async function mount(...args: Parameters<typeof renderFeature>) {
  const result = await renderFeature(...args)
  cleanup = result.restore
  return result
}
async function confirmClock(label = 'Clock in') {
  fireEvent.click(await screen.findByRole('button', { name: label }))
  fireEvent.click(screen.getByRole('button', { name: 'Confirm' }))
}

describe('clocking and GPS', () => {
  it('waits for confirmation before requesting GPS or sending attendance', async () => {
    const gps = geolocation(),
      sent: unknown[] = []
    await mount(<ClockPanel />, (config) => {
      if (config.method === 'post') {
        sent.push(JSON.parse(config.data))
        return {
          data: { attendance, message: 'Clocked in at 09:00 (Onsite – HQ).' },
        }
      }
    })
    const button = await screen.findByRole('button', {
      name: 'Clock in',
    })
    fireEvent.click(button)
    expect(gps).not.toHaveBeenCalled()
    expect(sent).toHaveLength(0)
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(sent).toHaveLength(0)
    await confirmClock()
    await screen.findByText('Clocked in at 09:00 (Onsite – HQ).')
    expect(gps).toHaveBeenCalledWith(
      expect.any(Function),
      expect.any(Function),
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 },
    )
    expect(sent).toEqual([
      {
        work_mode: 'onsite',
        latitude: 13.7563,
        longitude: 100.5018,
        accuracy_m: 8,
      },
    ])
  })
  it('clocks remotely without requesting GPS and preserves the server message after remount', async () => {
    const gps = geolocation(),
      sent: unknown[] = []
    const mounted = await mount(<ClockPanel />, (config) => {
      if (config.method === 'post') {
        sent.push(JSON.parse(config.data))
        return {
          data: {
            attendance: { ...attendance, work_mode: 'remote' },
            message: 'Remote clock-in recorded.',
          },
        }
      }
    })
    fireEvent.click(await screen.findByLabelText('Remote'))
    await confirmClock()
    await screen.findByText('Remote clock-in recorded.')
    expect(gps).not.toHaveBeenCalled()
    expect(sent).toEqual([{ work_mode: 'remote' }])
    mounted.rerender(<></>)
    expect(
      mounted.session.queryClient.getQueryData([
        'clock-notice',
        1,
        '2026-10-15',
      ]),
    ).toEqual({ message: 'Remote clock-in recorded.', error: false })
  })
  it.each([
    [1, /permission was denied/],
    [2, /location is unavailable/i],
    [3, /location timed out/i],
  ] as const)(
    'blocks submission for GPS error %s and permits a fresh confirmed retry',
    async (code, message) => {
      geolocation(code)
      let posts = 0
      await mount(<ClockPanel />, (config) => {
        if (config.method === 'post') {
          posts++
          return { data: { attendance, message: 'Success' } }
        }
      })
      await confirmClock()
      expect(await screen.findByRole('alert')).toHaveTextContent(message)
      expect(posts).toBe(0)
      geolocation()
      fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
      expect(posts).toBe(0)
      fireEvent.click(screen.getByRole('button', { name: 'Confirm' }))
      await screen.findByText('Success')
      expect(posts).toBe(1)
    },
  )
  it('blocks location requests in an insecure context', async () => {
    vi.stubGlobal('isSecureContext', false)
    const gps = geolocation()
    await mount(<ClockPanel />)
    await confirmClock()
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'HTTPS or localhost',
    )
    expect(gps).not.toHaveBeenCalled()
  })
  it('displays the server perimeter distance without changing clock state', async () => {
    geolocation()
    await mount(<ClockPanel />, (config) =>
      config.method === 'post'
        ? {
            status: 403,
            data: {
              code: 'OUTSIDE_WORK_PERIMETER',
              details: { distance_m: 501, allowed_radius_m: 100 },
            },
          }
        : undefined,
    )
    await confirmClock()
    expect(await screen.findByRole('alert')).toHaveTextContent('501 m')
    expect(screen.getByRole('button', { name: 'Clock out' })).toBeDisabled()
  })
  it('uses the stored onsite mode at clock-out and disables duplicate submissions', async () => {
    const pending = deferred<Reply>(),
      gps = geolocation()
    let posts = 0
    await mount(<ClockPanel />, (config) =>
      config.url === '/attendance/today'
        ? { data: { date: '2026-10-15', attendance, next_action: 'clock_out' } }
        : config.method === 'post'
          ? (posts++, pending.promise)
          : undefined,
    )
    expect(await screen.findByLabelText('Remote')).toBeDisabled()
    await confirmClock('Clock out')
    expect(
      await screen.findByRole('button', { name: 'Please wait…' }),
    ).toBeDisabled()
    expect(posts).toBe(1)
    expect(gps).toHaveBeenCalledOnce()
    pending.resolve({ data: { attendance, message: 'Clocked out.' } })
    await screen.findByText('Clocked out.')
  })
  it('uses server next_action after completion', async () => {
    await mount(<ClockPanel />, (config) =>
      config.url === '/attendance/today'
        ? {
            data: {
              date: '2026-10-15',
              attendance: { ...attendance, clock_out: attendance.clock_in },
              next_action: 'none',
            },
          }
        : undefined,
    )
    await screen.findByText('You’re done for today.')
    expect(screen.getByRole('button', { name: 'Clock in' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Clock out' })).toBeDisabled()
  })
})

describe('attendance periods and corrections', () => {
  it('loads only the selected employee and shows office-local times and derived leave', async () => {
    const queries: unknown[] = []
    await mount(<AttendanceOverview employeeId={2} />, (config) => {
      if (config.url === '/attendance/calendar') {
        queries.push(config.params)
        return {
          data: {
            ...calendar,
            entries: [
              {
                ...entry,
                display_status: 'leave',
                leaves: [
                  {
                    id: 9,
                    leave_type: 'Annual',
                    duration_type: 'full_days',
                    half_day_period: null,
                    status: 'approved',
                  },
                ],
              },
            ],
          },
        }
      }
    })
    await screen.findByText('Annual')
    expect(screen.getByText('09:00')).toBeVisible()
    expect(queries[0]).toMatchObject({ view: 'month', employee_id: 2 })
    fireEvent.click(screen.getByRole('button', { name: 'Calendar' }))
    expect(screen.getByLabelText(/2026-10-15: Leave/)).toBeVisible()
  })
  it('blocks oversized custom periods before fetching and honors data years', async () => {
    let calls = 0
    await mount(<AttendanceOverview employeeId={1} />, (config) => {
      if (config.url === '/attendance/calendar') {
        calls++
        return { data: calendar }
      }
    })
    await screen.findByText('09:00')
    expect(
      within(screen.getByLabelText('Year with records'))
        .getAllByRole('option')
        .map((option) => option.textContent),
    ).toEqual(['Choose year', '2026', '2025'])
    fireEvent.change(screen.getByLabelText('View'), {
      target: { value: 'custom' },
    })
    await waitFor(() => expect(calls).toBe(2))
    fireEvent.change(screen.getByLabelText('From'), {
      target: { value: '2024-01-01' },
    })
    expect(screen.getByRole('alert')).toHaveTextContent('at most 366 days')
    expect(calls).toBe(2)
  })
  it('submits a reason and offset-bearing correction and refreshes attendance', async () => {
    let payload: unknown
    await mount(
      <AttendanceOverview employeeId={1} />,
      (config) =>
        config.method === 'patch'
          ? ((payload = JSON.parse(config.data)), { data: attendance })
          : undefined,
      admin,
    )
    fireEvent.click(
      await screen.findByRole('button', { name: 'Correct attendance' }),
    )
    fireEvent.change(screen.getByLabelText('Stored status'), {
      target: { value: 'absent' },
    })
    fireEvent.change(screen.getByLabelText('Reason for correction'), {
      target: { value: 'Approved correction' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save correction' }))
    await waitFor(() =>
      expect(payload).toEqual({
        status: 'absent',
        reason: 'Approved correction',
      }),
    )
  })
  it('closes a confirmation on Escape and restores focus', async () => {
    function Example() {
      const [open, setOpen] = useState(false)
      return (
        <>
          <button onClick={() => setOpen(true)}>Open</button>
          {open && (
            <ConfirmDialog
              title="Confirm action"
              onClose={() => setOpen(false)}
              onConfirm={() => undefined}
            />
          )}
        </>
      )
    }
    await mount(<Example />)
    const opener = screen.getByRole('button', { name: 'Open' })
    opener.focus()
    fireEvent.click(opener)
    fireEvent(
      screen.getByRole('dialog'),
      new Event('cancel', { bubbles: false, cancelable: true }),
    )
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument(),
    )
    expect(opener).toHaveFocus()
  })
  it('shifts a week across a year boundary', async () => {
    function Example() {
      const [value, change] = useState({
        ...initialPeriod('2026-01-01'),
        view: 'week' as const,
      })
      return (
        <PeriodFilter
          value={value}
          onChange={(next) => change({ ...next, view: 'week' })}
          years={[2026]}
          maxDays={366}
        />
      )
    }
    await mount(<Example />)
    expect(screen.getByText('2025-12-29 — 2026-01-04')).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Previous period' }))
    expect(screen.getByText('2025-12-22 — 2025-12-28')).toBeVisible()
  })
})

describe('leave and profile', () => {
  it('requires Other text and a half-day period before posting', async () => {
    const sent: unknown[] = []
    await mount(<Leave />, (config) =>
      config.method === 'post'
        ? (sent.push(JSON.parse(config.data)), { data: request })
        : undefined,
    )
    fireEvent.change(await screen.findByLabelText('Leave type'), {
      target: { value: '1' },
    })
    fireEvent.change(screen.getByLabelText('Reason', {}), {
      target: { value: '2' },
    })
    fireEvent.click(screen.getByLabelText('Half day'))
    expect(screen.queryByLabelText('Number of days')).not.toBeInTheDocument()
    fireEvent.click(
      screen.getByRole('button', { name: 'Submit leave request' }),
    )
    await screen.findByText('Describe your leave reason.')
    expect(sent).toHaveLength(0)
    fireEvent.change(screen.getByLabelText('Describe your reason'), {
      target: { value: 'Family appointment' },
    })
    fireEvent.change(screen.getByLabelText('Half-day period'), {
      target: { value: 'morning' },
    })
    fireEvent.change(screen.getByLabelText('Reporting manager'), {
      target: { value: '2' },
    })
    fireEvent.click(
      screen.getByRole('button', { name: 'Submit leave request' }),
    )
    await screen.findByText('Leave request submitted.')
    expect(sent[0]).toMatchObject({
      num_days: 0.5,
      half_day_period: 'morning',
      reporting_manager_id: 2,
      reason_text: 'Family appointment',
    })
  })
  it('previews full days skipping configured weekends and surfaces overlap failures', async () => {
    await mount(<Leave />, (config) =>
      config.method === 'post'
        ? { status: 409, data: { code: 'LEAVE_OVERLAP' } }
        : undefined,
    )
    fireEvent.change(await screen.findByLabelText('Leave type'), {
      target: { value: '1' },
    })
    fireEvent.change(screen.getByLabelText('Reason', {}), {
      target: { value: '1' },
    })
    fireEvent.change(screen.getByLabelText('Number of days'), {
      target: { value: '2' },
    })
    fireEvent.change(screen.getByLabelText('Start date'), {
      target: { value: '2026-10-16' },
    })
    fireEvent.change(screen.getByLabelText('Reporting manager'), {
      target: { value: '2' },
    })
    expect(screen.getByLabelText('Expected end date')).toHaveTextContent(
      '2026-10-19',
    )
    fireEvent.click(
      screen.getByRole('button', { name: 'Submit leave request' }),
    )
    expect(await screen.findByRole('alert')).toHaveTextContent('overlap')
  })
  it('allows cancellation only after confirmation', async () => {
    let calls = 0
    await mount(<LeaveList />, (config) =>
      config.method === 'post'
        ? (calls++, { data: { ...request, status: 'cancelled' } })
        : undefined,
    )
    fireEvent.click(
      await screen.findByRole('button', { name: 'Cancel request' }),
    )
    expect(calls).toBe(0)
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }))
    await waitFor(() => expect(calls).toBe(1))
  })
  it('shows decisions for the selected manager and never for self', async () => {
    const foreign = {
      ...request,
      employee: { ...identity, id: 3 },
      reporting_manager: identity,
    }
    let decision: unknown
    await mount(
      <LeaveList team />,
      (config) =>
        config.url === '/leave-requests/team'
          ? { data: page([request, { ...foreign, id: 10 }]) }
          : config.method === 'post'
            ? ((decision = JSON.parse(config.data)), { data: foreign })
            : undefined,
      [...selfPermissions, 'leave.read.team', 'leave.decide.team'],
    )
    const approve = await screen.findAllByRole('button', {
      name: 'Approve',
    })
    expect(approve).toHaveLength(1)
    fireEvent.click(approve[0])
    fireEvent.change(screen.getByLabelText('Decision note (optional)'), {
      target: { value: 'Approved for coverage' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }))
    await waitFor(() =>
      expect(decision).toEqual({ decision_note: 'Approved for coverage' }),
    )
  })
  it('updates display name with an immutable ID and updates the session', async () => {
    let payload: unknown
    const result = await mount(<Profile />, (config) =>
      config.method === 'patch'
        ? ((payload = JSON.parse(config.data)),
          { data: { ...profile(), display_name: 'Ada L' } })
        : undefined,
    )
    expect(screen.getByText('EMP0001')).toBeVisible()
    fireEvent.change(screen.getByLabelText('Display name', {}), {
      target: { value: 'Ada L' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save display name' }))
    await screen.findByText('Display name updated.')
    expect(payload).toEqual({ display_name: 'Ada L' })
    expect(result.session.getSnapshot().profile?.display_name).toBe('Ada L')
  })
})

describe('administration', () => {
  it('assigns eligible managers and links locations with the required internal IDs', async () => {
    const sent: { path: string; data: unknown }[] = []
    await mount(
      <TeamAssociations
        team={{ id: 1, name: 'Team A', description: null }}
        onClose={() => undefined}
      />,
      (config) => {
        if (config.url === '/admin/employees')
          return {
            data: page([
              employee,
              {
                ...employee,
                id: 2,
                employee_id: 'EMP0002',
                first_name: 'Grace',
                role: { id: 2, name: 'reporting_manager' },
              },
            ]),
          }
        if (config.url?.startsWith('/admin/teams/1/')) {
          if (config.method === 'post') {
            sent.push({ path: config.url, data: JSON.parse(config.data) })
            return { data: {} }
          }
          return { data: page([]) }
        }
      },
      admin,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Managers' }))
    await screen.findByRole('option', { name: /Grace.*EMP0002/ })
    expect(
      screen.queryByRole('option', { name: /Ada.*EMP0001/ }),
    ).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Manager to assign'), {
      target: { value: '2' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Assign manager' }))
    await waitFor(() =>
      expect(sent[0]).toEqual({
        path: '/admin/teams/1/managers',
        data: { employee_id: 2 },
      }),
    )
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Locations' })).toBeEnabled(),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Locations' }))
    await screen.findByRole('option', { name: 'HQ' })
    fireEvent.change(screen.getByLabelText('Work location to link'), {
      target: { value: '1' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Link location' }))
    await waitFor(() =>
      expect(sent[1]).toEqual({
        path: '/admin/teams/1/locations',
        data: { work_location_id: 1 },
      }),
    )
  })
  it('creates an employee, shows credentials once, and never caches the plaintext password', async () => {
    let body: Record<string, unknown> | undefined
    const result = await mount(
      <Employees />,
      (config) =>
        config.url === '/admin/employees' && config.method === 'post'
          ? ((body = JSON.parse(config.data)),
            {
              data: {
                ...employee,
                employee_id: 'EMP0099',
                default_password: 'CreatedPassword123',
              },
            })
          : undefined,
      admin,
    )
    fireEvent.click(
      await screen.findByRole('button', {
        name: 'Create employee',
      }),
    )
    fireEvent.change(screen.getByLabelText('First name'), {
      target: { value: 'New' },
    })
    fireEvent.change(screen.getByLabelText('Last name'), {
      target: { value: 'Person' },
    })
    await within(screen.getByRole('dialog')).findByRole('option', {
      name: 'employee',
    })
    fireEvent.change(
      screen.getByLabelText('Role', { selector: '#employee-role' }),
      { target: { value: '1' } },
    )
    fireEvent.change(screen.getByLabelText('Default password', {}), {
      target: { value: 'CreatedPassword123' },
    })
    fireEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', {
        name: 'Create employee',
      }),
    )
    await waitFor(() =>
      expect(screen.getByLabelText('Default password')).toHaveTextContent(
        'CreatedPassword123',
      ),
    )
    expect(body).not.toHaveProperty('employee_id')
    expect(
      JSON.stringify(result.session.queryClient.getMutationCache().getAll()),
    ).not.toContain('CreatedPassword123')
    fireEvent.click(screen.getByRole('button', { name: 'Done' }))
    expect(screen.queryByText('CreatedPassword123')).not.toBeInTheDocument()
  })
  it('handles last-admin failures without removing the employee', async () => {
    await mount(
      <Employees />,
      (config) =>
        config.method === 'patch'
          ? { status: 409, data: { code: 'LAST_ADMIN' } }
          : undefined,
      admin,
    )
    fireEvent.click(await screen.findByRole('button', { name: 'Deactivate' }))
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'final active administrator',
    )
  })
  it('validates work-location coordinates and the 50–100 m radius', async () => {
    let posts = 0
    await mount(
      <Locations />,
      (config) =>
        config.method === 'post' ? (posts++, { data: {} }) : undefined,
      admin,
    )
    fireEvent.click(
      await screen.findByRole('button', {
        name: 'Create location',
      }),
    )
    fireEvent.change(screen.getByLabelText('Location name'), {
      target: { value: 'Office' },
    })
    fireEvent.change(screen.getByLabelText('Latitude'), {
      target: { value: '91' },
    })
    fireEvent.change(screen.getByLabelText('Longitude'), {
      target: { value: '100.1234567' },
    })
    fireEvent.change(screen.getByLabelText('Allowed radius (m)'), {
      target: { value: '101' },
    })
    fireEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', {
        name: 'Create location',
      }),
    )
    await screen.findByText('Use a value between -90 and 90.')
    expect(posts).toBe(0)
  })
  it('creates teams and shows reference-preserving deletion errors', async () => {
    let created: unknown
    await mount(
      <Teams />,
      (config) =>
        config.method === 'post'
          ? ((created = JSON.parse(config.data)),
            { data: { id: 2, name: 'Team B' } })
          : config.method === 'delete'
            ? { status: 409, data: { code: 'TEAM_IN_USE' } }
            : undefined,
      admin,
    )
    fireEvent.click(await screen.findByRole('button', { name: 'Create team' }))
    fireEvent.change(screen.getByLabelText('Team name'), {
      target: { value: 'Team B' },
    })
    fireEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', {
        name: 'Create team',
      }),
    )
    await waitFor(() =>
      expect(created).toEqual({ name: 'Team B', description: null }),
    )
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument(),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('history')
  })
  it('opens a scoped team member dashboard and a company employee drilldown', async () => {
    await mount(
      <Team />,
      (config) =>
        config.url === '/team/members'
          ? { data: page([{ ...employee, today_status: 'present' }]) }
          : config.url === '/team/attendance'
            ? {
                data: {
                  ...page([{ employee: identity, summary }]),
                  period: calendar.period,
                },
              }
            : undefined,
      admin,
    )
    fireEvent.click(
      await screen.findByRole('button', { name: 'View attendance' }),
    )
    await screen.findByRole('heading', { name: 'Attendance overview' })
    cleanup?.()
    cleanup = undefined
    await mount(
      <AllAttendance />,
      (config) =>
        config.url === '/attendance'
          ? {
              data: {
                ...page([{ ...entry, employee: identity }]),
                period: calendar.period,
              },
            }
          : undefined,
      admin,
    )
    fireEvent.click(
      await screen.findByRole('button', { name: 'Ada Lovelace (EMP0001)' }),
    )
    await screen.findByRole('heading', { name: 'Attendance overview' })
  })
  it('loads every reference page and passes report filters to CSV requests', async () => {
    const referencePages: number[] = [],
      downloads: unknown[] = []
    const createUrl = vi.fn(() => 'blob:report'),
      revoke = vi.fn()
    Object.defineProperty(URL, 'createObjectURL', {
      configurable: true,
      value: createUrl,
    })
    Object.defineProperty(URL, 'revokeObjectURL', {
      configurable: true,
      value: revoke,
    })
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(
      () => undefined,
    )
    await mount(
      <Reports />,
      (config) => {
        if (config.url === '/admin/employees') {
          referencePages.push(config.params.page)
          return {
            data: {
              ...page([
                config.params.page === 1
                  ? employee
                  : { ...employee, id: 2, employee_id: 'EMP0002' },
              ]),
              total: 2,
            },
          }
        }
        if (config.url?.endsWith('.csv')) {
          downloads.push(config.params)
          return { data: new Blob(['\ufeffemployee_id\r\nEMP0001']) }
        }
      },
      admin,
    )
    await screen.findByRole('option', { name: /EMP0002/ })
    expect(referencePages).toEqual([1, 2])
    fireEvent.change(screen.getByLabelText('Employee', {}), {
      target: { value: '2' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Download leave CSV' }))
    await waitFor(() => expect(downloads).toHaveLength(1))
    expect(downloads[0]).toMatchObject({
      from: '2026-10-01',
      to: '2026-10-31',
      employee_id: 2,
    })
    expect(createUrl).toHaveBeenCalledOnce()
  })
})
