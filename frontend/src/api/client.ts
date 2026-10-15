import axios, { CanceledError } from 'axios'
import type {
  ChangePasswordInput,
  LoginInput,
  TokenResponse,
} from '../types/auth'
import { errorCode, isUnauthorized } from './errors'

declare module 'axios' {
  interface InternalAxiosRequestConfig {
    sessionGeneration?: number
    sentToken?: string | null
    authRetried?: boolean
  }
}

interface SessionEvents {
  expired: () => void
  passwordRequired: () => void
}

export function createApiClient(events: SessionEvents) {
  const options = {
    baseURL:
      import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1',
    withCredentials: true,
    timeout: 20_000,
  }
  const api = axios.create(options)
  // Refresh and credential requests must not recursively invoke the 401 interceptor.
  const credentials = axios.create(options)
  let token: string | null = null
  let generation = 0
  let refreshFlight: Promise<TokenResponse> | null = null
  let signingOut = false
  let changingPassword = false

  function clear() {
    generation += 1
    token = null
    refreshFlight = null
  }

  function accept(pair: TokenResponse, expected: number) {
    if (expected !== generation) throw new CanceledError('Session changed.')
    token = pair.access_token
    if (pair.pwd_change_required) events.passwordRequired()
    return pair
  }

  function expire(expected: number) {
    if (expected === generation) {
      clear()
      events.expired()
    }
  }

  function refresh(): Promise<TokenResponse> {
    if (signingOut || changingPassword)
      return Promise.reject(new CanceledError('Session update in progress.'))
    if (refreshFlight) return refreshFlight
    const expected = generation
    const flight = credentials
      .post<TokenResponse>('/auth/refresh')
      .then(({ data }) => accept(data, expected))
      .catch((error: unknown) => {
        if (expected === generation) expire(expected)
        throw error
      })
      .finally(() => {
        if (refreshFlight === flight) refreshFlight = null
      })
    refreshFlight = flight
    return flight
  }

  api.interceptors.request.use((config) => {
    config.sessionGeneration ??= generation
    if (
      config.sessionGeneration !== generation ||
      signingOut ||
      changingPassword
    ) {
      throw new CanceledError('Session changed.')
    }
    config.sentToken = token
    if (token) config.headers.set('Authorization', `Bearer ${token}`)
    else config.headers.delete('Authorization')
    return config
  })

  api.interceptors.response.use(
    (response) => {
      if (response.config.sessionGeneration !== generation) {
        throw new CanceledError('Session changed.')
      }
      return response
    },
    async (error: unknown) => {
      if (!axios.isAxiosError(error) || !error.config) throw error
      // CSV downloads request blobs; normalize JSON failures before auth handling.
      if (error.response?.data instanceof Blob) {
        try {
          error.response.data = JSON.parse(await error.response.data.text())
        } catch {
          /* Keep a safe generic error for non-JSON failures. */
        }
      }
      const config = error.config
      if (config.sessionGeneration !== generation) {
        throw new CanceledError('Session changed.')
      }
      // A wrong current password is an actionable form error, not an expired session.
      if (isUnauthorized(error) && errorCode(error) !== 'INVALID_CREDENTIALS') {
        if (config.authRetried) {
          expire(generation)
          throw error
        }
        config.authRetried = true
        // A delayed 401 may belong to the token that another request already refreshed.
        if (config.sentToken === token) await refresh()
        return api.request(config)
      }
      if (errorCode(error) === 'PASSWORD_CHANGE_REQUIRED')
        events.passwordRequired()
      throw error
    },
  )

  return {
    api,
    clear,
    refresh,
    async login(input: LoginInput) {
      const expected = generation
      const body = new URLSearchParams({ ...input, grant_type: 'password' })
      const { data } = await credentials.post<TokenResponse>(
        '/auth/login',
        body,
      )
      return accept(data, expected)
    },
    async changePassword(input: ChangePasswordInput) {
      if (changingPassword || signingOut)
        throw new CanceledError('Session update in progress.')
      changingPassword = true
      try {
        // Do not let an earlier rotating response overwrite the new password cookie.
        if (refreshFlight) await refreshFlight
        const expected = generation
        const send = () =>
          credentials.post<TokenResponse>('/auth/change-password', input, {
            headers: { Authorization: `Bearer ${token}` },
          })
        let response
        try {
          response = await send()
        } catch (error) {
          if (
            !isUnauthorized(error) ||
            errorCode(error) === 'INVALID_CREDENTIALS'
          )
            throw error
          changingPassword = false
          await refresh()
          changingPassword = true
          try {
            response = await send()
          } catch (retryError) {
            if (
              isUnauthorized(retryError) &&
              errorCode(retryError) !== 'INVALID_CREDENTIALS'
            )
              expire(expected)
            throw retryError
          }
        }
        if (expected !== generation) throw new CanceledError('Session changed.')
        clear()
        return accept(response.data, generation)
      } finally {
        changingPassword = false
      }
    },
    async logout() {
      if (signingOut) throw new CanceledError('Signing out.')
      signingOut = true
      try {
        // Rotation must complete before revoking the session whose cookie it set.
        if (refreshFlight) await refreshFlight
        try {
          await credentials.post('/auth/logout', undefined, {
            headers: { Authorization: `Bearer ${token}` },
          })
        } catch (error) {
          if (!isUnauthorized(error)) throw error
          // An expired access token can still have a valid refresh session.
          signingOut = false
          await refresh()
          signingOut = true
          await credentials.post('/auth/logout', undefined, {
            headers: { Authorization: `Bearer ${token}` },
          })
        }
        clear()
      } finally {
        signingOut = false
      }
    },
  }
}

export type ApiClient = ReturnType<typeof createApiClient>
