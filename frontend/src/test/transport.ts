import axios, { AxiosError, AxiosHeaders } from 'axios'
import type { InternalAxiosRequestConfig } from 'axios'
import type { Profile, TokenResponse } from '../types/auth'

export type Reply = { status?: number; data?: unknown }
export type Handler = (
  config: InternalAxiosRequestConfig,
) => Reply | Promise<Reply>

export function mockTransport(handler: Handler) {
  const original = axios.defaults.adapter
  axios.defaults.adapter = async (config) => {
    const reply = await handler(config)
    const response = {
      data: reply.data,
      status: reply.status ?? 200,
      statusText: '',
      headers: new AxiosHeaders(),
      config,
    }
    if (response.status >= 400)
      throw new AxiosError(
        'Request failed.',
        undefined,
        config,
        undefined,
        response,
      )
    return response
  }
  return () => {
    axios.defaults.adapter = original
  }
}

export function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

export const invalidToken: Reply = {
  status: 401,
  data: { code: 'INVALID_TOKEN' },
}
export const pair = (token = 'test-access', forced = false): TokenResponse => ({
  access_token: token,
  token_type: 'bearer',
  expires_in: 1800,
  pwd_change_required: forced,
})
export const selfPermissions = [
  'profile.read.self',
  'profile.update.self',
  'attendance.create.self',
  'attendance.read.self',
  'leave.create.self',
  'leave.read.self',
  'report.export.self',
]
export const adminPermissions = [
  'attendance.read.any',
  'attendance.update.any',
  'leave.read.any',
  'leave.decide.any',
  'employee.read.any',
  'employee.create.any',
  'employee.update.any',
  'team.manage.any',
  'location.manage.any',
  'report.export.any',
]
export function profile(
  permissions = selfPermissions,
  forced = false,
): Profile {
  return {
    id: 1,
    employee_id: 'EMP0001',
    first_name: 'Ada',
    last_name: 'Lovelace',
    display_name: null,
    position: null,
    department: null,
    role: { id: 1, name: 'employee' },
    team: null,
    permissions,
    must_change_password: forced,
  }
}
