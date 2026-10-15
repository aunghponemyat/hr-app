import axios from 'axios'
import type { ApiErrorBody } from '../types/auth'

export class UserFacingError extends Error {}

export function errorCode(error: unknown): string | undefined {
  if (axios.isAxiosError<ApiErrorBody>(error)) {
    return error.response?.data?.code
  }
}

export function errorMessage(error: unknown): string {
  if (error instanceof UserFacingError) return error.message
  const messages: Record<string, string> = {
    PERMISSION_DENIED: 'You do not have permission to perform this action.',
    OUT_OF_SCOPE: 'This record is outside your permitted scope.',
    NOT_FOUND: 'This record is no longer available. Refresh and try again.',
    ALREADY_CLOCKED_IN: 'You have already clocked in today.',
    ALREADY_CLOCKED_OUT: 'You have already clocked out today.',
    NOT_CLOCKED_IN: 'Clock in before clocking out today.',
    ATTENDANCE_CONFLICT: 'Attendance changed. Refresh and try again.',
    CLOCK_TIME_CONFLICT:
      'The server clock precedes clock-in. Please retry later.',
    INVALID_CLOCK_TIMES:
      'Clock times must be ordered, on the attendance date, and not in the future.',
    GPS_REQUIRED: 'A valid location fix is required. Please try again.',
    LOW_GPS_ACCURACY:
      'GPS accuracy is too low. Try again outdoors or near a window.',
    NO_WORK_LOCATION_CONFIGURED:
      'No work location is configured for your team. Please contact HR.',
    OUTSIDE_WORK_PERIMETER:
      'You are outside your assigned work perimeter. Move closer to the office and try again.',
    LEAVE_OVERLAP: 'These dates overlap a pending or approved leave request.',
    LEAVE_CONFLICT: 'Leave changed. Refresh and try again.',
    INVALID_STATE:
      'This request has changed and the action is no longer available.',
    INELIGIBLE_MANAGER: 'Choose a currently eligible reporting manager.',
    NOT_SELECTED_MANAGER:
      'Only the selected reporting manager or HR can decide this request.',
    SELF_APPROVAL_FORBIDDEN: 'You cannot decide your own leave request.',
    NON_WORKING_DAY: 'Leave must start on a working day.',
    LEAVE_BACKDATE_LIMIT: 'The leave start date is too far in the past.',
    LEAVE_TOO_LONG: 'The leave request exceeds the allowed number of days.',
    INACTIVE_LEAVE_OPTION:
      'A leave option is no longer active. Refresh and choose again.',
    REASON_TEXT_REQUIRED: 'Please describe your leave reason.',
    LAST_ADMIN: 'The final active administrator must be retained.',
    INELIGIBLE_MANAGER_ROLE:
      'A manager must hold team or company attendance permissions.',
    INACTIVE_EMPLOYEE: 'Only active employees can be assigned.',
    TEAM_IN_USE: 'This team has links or history and cannot be deleted.',
    LOCATION_IN_USE:
      'This location is linked to a team or attendance and cannot be deleted.',
    CONFLICT: 'A duplicate or linked record prevents this change.',
    VALIDATION_ERROR: 'Check the form fields and try again.',
    INVALID_RANGE: 'Choose an ordered date range.',
    RANGE_TOO_LARGE: 'The selected period exceeds the report range limit.',
    HISTORY_LIMIT: 'Attendance history is available for the past year.',
  }
  const code = errorCode(error)
  if (
    code === 'OUTSIDE_WORK_PERIMETER' &&
    axios.isAxiosError<ApiErrorBody>(error)
  ) {
    const details = error.response?.data.details
    const distance = Number(details?.distance_m),
      radius = Number(details?.allowed_radius_m)
    if (
      details?.distance_m != null &&
      details?.allowed_radius_m != null &&
      Number.isFinite(distance) &&
      Number.isFinite(radius)
    )
      return `You are ${Math.round(distance)} m from the office; the allowed radius is ${radius} m. Move closer and try again.`
  }
  if (code && messages[code]) return messages[code]
  switch (errorCode(error)) {
    case 'INVALID_CREDENTIALS':
      return 'The employee ID or password is incorrect.'
    case 'ACCOUNT_LOCKED':
      return 'Your account is temporarily locked. Please try again later.'
    case 'RATE_LIMITED':
      return 'Too many attempts. Please wait before trying again.'
    case 'PASSWORD_CHANGE_REQUIRED':
      return 'Please change your password to continue.'
    case 'INVALID_TOKEN':
      return 'Your session has expired. Please sign in again.'
    default:
      // Do not display arbitrary payloads or Axios errors containing request secrets.
      return 'Unable to complete the request. Please try again.'
  }
}

export function isUnauthorized(error: unknown): boolean {
  return axios.isAxiosError(error) && error.response?.status === 401
}
