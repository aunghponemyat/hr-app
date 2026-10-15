import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import type { ReactNode } from 'react'
import { AuthProvider } from '../auth/AuthProvider'
import { AuthSession } from '../auth/session'
import { profile, pair, mockTransport, selfPermissions } from './transport'
import type { Handler, Reply } from './transport'
import type {
  Attendance,
  CalendarEntry,
  CalendarResponse,
  Employee,
  LeaveOptions,
  LeaveRequest,
  Role,
} from '../types/domain'

export const identity = {
  id: 1,
  employee_id: 'EMP0001',
  name: 'Ada Lovelace',
  team: { id: 1, name: 'Team A' },
}
export const summary = {
  present_days: 1,
  half_day_days: 0,
  leave_days: 0,
  absent_days: 0,
  total_worked_hours: 8,
}
export const entry: CalendarEntry = {
  date: '2026-10-15',
  attendance_id: 5,
  display_status: 'present',
  work_mode: 'onsite',
  clock_in: '2026-10-15T09:00:00+07:00',
  clock_out: '2026-10-15T17:00:00+07:00',
  work_location_name: 'HQ',
  worked_hours: 8,
  leave: null,
  leaves: [],
}
export const calendar: CalendarResponse = {
  employee: identity,
  period: { from_date: '2026-10-01', to_date: '2026-10-31' },
  entries: [entry],
  summary,
  available_years: [2026, 2025],
}
const gps = {
  latitude: null,
  longitude: null,
  accuracy_m: null,
  distance_m: null,
  verified: null,
}
export const attendance: Attendance = {
  id: 5,
  employee_id: 1,
  attendance_date: '2026-10-15',
  work_mode: 'onsite',
  work_location_id: 1,
  work_location_name: 'HQ',
  clock_in: '2026-10-15T09:00:00+07:00',
  clock_out: null,
  clock_in_gps: gps,
  clock_out_gps: gps,
  status: 'present',
  updated_by: null,
  worked_hours: 0,
  created_at: '2026-10-15T09:00:00+07:00',
  updated_at: '2026-10-15T09:00:00+07:00',
}
export const options: LeaveOptions = {
  types: [{ id: 1, code: 'annual', name: 'Annual' }],
  reasons: [
    { id: 1, code: 'vacation', name: 'Vacation', requires_text: false },
    { id: 2, code: 'other', name: 'Other', requires_text: true },
  ],
  managers: [
    { ...identity, id: 2, name: 'Grace Manager', employee_id: 'EMP0002' },
  ],
  today: '2026-10-15',
  working_weekdays: [0, 1, 2, 3, 4],
  max_days_per_request: 30,
  backdate_days: 7,
}
export const request: LeaveRequest = {
  id: 9,
  employee: identity,
  leave_type: options.types[0],
  leave_reason: options.reasons[0],
  reason_text: null,
  duration_type: 'full_days',
  half_day_period: null,
  num_days: '2.0',
  start_date: '2026-10-16',
  end_date: '2026-10-19',
  reporting_manager: options.managers[0],
  remark: null,
  status: 'pending',
  decided_by: null,
  decided_at: null,
  decision_note: null,
  created_at: '2026-10-15T09:00:00+07:00',
  updated_at: '2026-10-15T09:00:00+07:00',
}
export const employee: Employee = {
  ...profile(),
  is_active: true,
  created_at: '2026-10-15T09:00:00+07:00',
  updated_at: '2026-10-15T09:00:00+07:00',
}
export const roles: Role[] = [
  { id: 1, name: 'employee', description: null, permissions: selfPermissions },
  {
    id: 2,
    name: 'reporting_manager',
    description: null,
    permissions: [...selfPermissions, 'attendance.read.team'],
  },
]
export const page = <T,>(items: T[]) => ({
  items,
  total: items.length,
  page: 1,
  page_size: 25,
})

export async function renderFeature(
  children: ReactNode,
  handler: (
    config: Parameters<Handler>[0],
  ) => Reply | undefined | Promise<Reply | undefined> = () => undefined,
  permissions = selfPermissions,
) {
  const restore = mockTransport(async (config) => {
    if (config.url?.startsWith('/auth/')) return { data: pair() }
    const reply = await handler(config)
    if (reply) return reply
    switch (config.url) {
      case '/auth/refresh':
        return { data: pair() }
      case '/me':
        return { data: profile(permissions) }
      case '/attendance/today':
        return {
          data: {
            date: '2026-10-15',
            attendance: null,
            next_action: 'clock_in',
          },
        }
      case '/attendance/calendar':
        return { data: calendar }
      case '/leave/options':
        return { data: options }
      case '/leave-requests':
      case '/leave-requests/team':
        return { data: page([request]) }
      case '/admin/employees':
        return { data: page([employee]) }
      case '/admin/roles':
        return { data: page(roles) }
      case '/admin/teams':
        return { data: page([{ id: 1, name: 'Team A', description: null }]) }
      case '/admin/work-locations':
        return {
          data: page([
            {
              id: 1,
              name: 'HQ',
              latitude: '13.756300',
              longitude: '100.501800',
              allowed_radius_m: 100,
            },
          ]),
        }
      default:
        throw new Error(`Unhandled test endpoint: ${config.url}`)
    }
  })
  const session = new AuthSession()
  await session.restore()
  const view = render(
    <AuthProvider session={session}>
      <MemoryRouter>{children}</MemoryRouter>
    </AuthProvider>,
  )
  return {
    session,
    restore: () => {
      view.unmount()
      session.queryClient.clear()
      restore()
    },
    ...view,
  }
}
