import axios from 'axios'
import type { ApiErrorBody } from '../types/auth'

export function errorCode(error: unknown): string | undefined {
  if (axios.isAxiosError<ApiErrorBody>(error)) {
    return error.response?.data?.code
  }
}

export function errorMessage(error: unknown): string {
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
