export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}
export interface Team {
  id: number
  name: string
  description: string | null
}
export interface Identity {
  id: number
  employee_id: string
  name: string
  team: { id: number; name: string } | null
}
export interface Employee {
  id: number
  employee_id: string
  first_name: string
  last_name: string
  display_name: string | null
  position: string | null
  department: string | null
  role: { id: number; name: string }
  team: { id: number; name: string } | null
  is_active: boolean
  must_change_password: boolean
  created_at: string
  updated_at: string
}
export interface Role {
  id: number
  name: string
  description: string | null
  permissions: string[]
}
export interface Location {
  id: number
  name: string
  latitude: string
  longitude: string
  allowed_radius_m: number
}
export interface Manager {
  employee: Employee
  assigned_at: string
}
export type WorkMode = 'onsite' | 'remote'
export type DisplayStatus =
  'present' | 'absent' | 'half-day' | 'leave' | 'weekend' | 'upcoming'
export interface GpsEvidence {
  latitude: string | null
  longitude: string | null
  accuracy_m: string | null
  distance_m: string | null
  verified: boolean | null
}
export interface Attendance {
  id: number
  employee_id: number
  attendance_date: string
  work_mode: WorkMode
  work_location_id: number | null
  work_location_name: string | null
  clock_in: string | null
  clock_out: string | null
  clock_in_gps: GpsEvidence
  clock_out_gps: GpsEvidence
  status: 'present' | 'absent' | 'half-day'
  updated_by: number | null
  worked_hours: number
  created_at: string
  updated_at: string
}
export interface Today {
  date: string
  attendance: Attendance | null
  next_action: 'clock_in' | 'clock_out' | 'none'
}
export interface ClockInput {
  work_mode: WorkMode
  latitude?: number
  longitude?: number
  accuracy_m?: number
}
export interface ClockResult {
  attendance: Attendance
  message: string
}
export type HalfDayPeriod = 'morning' | 'afternoon'
export type LeaveStatus = 'pending' | 'approved' | 'rejected' | 'cancelled'
export interface LeaveInfo {
  id: number
  leave_type: string
  duration_type: 'half_day' | 'full_days'
  half_day_period: HalfDayPeriod | null
  status: LeaveStatus
}
export interface CalendarEntry {
  date: string
  attendance_id: number | null
  display_status: DisplayStatus | null
  work_mode: WorkMode | null
  clock_in: string | null
  clock_out: string | null
  work_location_name: string | null
  worked_hours: number
  leave: LeaveInfo | null
  leaves: LeaveInfo[]
}
export interface Summary {
  present_days: number
  half_day_days: number
  leave_days: number
  absent_days: number
  total_worked_hours: number
}
export interface DateRange {
  from_date: string
  to_date: string
}
export interface CalendarResponse {
  employee: Identity
  period: DateRange
  entries: CalendarEntry[]
  summary: Summary
  available_years: number[]
}
export interface AttendanceTableRow extends CalendarEntry {
  employee: Identity
}
export interface AttendanceTable extends Page<AttendanceTableRow> {
  period: DateRange
}
export interface TeamSummary extends Page<{
  employee: Identity
  summary: Summary
}> {
  period: DateRange
}
export interface TeamMember extends Employee {
  today_status: DisplayStatus | null
}
export interface Choice {
  id: number
  code: string
  name: string
}
export interface ReasonChoice extends Choice {
  requires_text: boolean
}
export interface LeaveOptions {
  types: Choice[]
  reasons: ReasonChoice[]
  managers: Identity[]
  today: string
  working_weekdays: number[]
  max_days_per_request: number
  backdate_days: number
}
export interface LeaveRequest {
  id: number
  employee: Identity
  leave_type: Choice
  leave_reason: ReasonChoice
  reason_text: string | null
  duration_type: 'half_day' | 'full_days'
  half_day_period: HalfDayPeriod | null
  num_days: string
  start_date: string
  end_date: string
  reporting_manager: Identity
  remark: string | null
  status: LeaveStatus
  decided_by: Identity | null
  decided_at: string | null
  decision_note: string | null
  created_at: string
  updated_at: string
}
export interface LeaveInput {
  leave_type_id: number
  leave_reason_id: number
  reason_text: string | null
  duration_type: 'half_day' | 'full_days'
  half_day_period: HalfDayPeriod | null
  num_days: number
  start_date: string
  reporting_manager_id: number
  remark: string | null
}
export interface EmployeeInput {
  first_name: string
  last_name: string
  display_name: string | null
  position: string | null
  department: string | null
  role_id: number
  team_id: number | null
}
export interface AttendanceEdit {
  reason: string
  status?: 'present' | 'absent' | 'half-day'
  clock_in?: string | null
  clock_out?: string | null
}
