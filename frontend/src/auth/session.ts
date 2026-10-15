import { QueryClient } from '@tanstack/react-query'
import { createApiClient } from '../api/client'
import { errorCode, errorMessage, isUnauthorized } from '../api/errors'
import type { ChangePasswordInput, LoginInput, Profile } from '../types/auth'

export interface AuthState {
  status: 'loading' | 'anonymous' | 'authenticated' | 'error'
  profile: Profile | null
  busy: boolean
  error: string | null
}

export class AuthSession {
  readonly queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
  })
  readonly http = createApiClient({
    expired: () => this.end(),
    passwordRequired: () => {
      if (this.state.profile) {
        this.set({
          profile: { ...this.state.profile, must_change_password: true },
        })
      }
    },
  })
  private state: AuthState = {
    status: 'loading',
    profile: null,
    busy: false,
    error: null,
  }
  private listeners = new Set<() => void>()
  private restoreFlight: Promise<void> | null = null
  private started = false
  private revision = 0

  getSnapshot = () => this.state
  subscribe = (listener: () => void) => {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  private set(patch: Partial<AuthState>) {
    this.state = { ...this.state, ...patch }
    this.listeners.forEach((listener) => listener())
  }

  private end() {
    this.revision += 1
    this.queryClient.clear()
    this.set({ status: 'anonymous', profile: null, error: null, busy: false })
  }

  private async loadProfile(expected: number) {
    const profile = await this.queryClient.fetchQuery({
      queryKey: ['me'],
      queryFn: async () => (await this.http.api.get<Profile>('/me')).data,
      staleTime: 0,
    })
    if (expected !== this.revision) return
    this.set({ status: 'authenticated', profile, error: null })
  }

  restore = (): Promise<void> => {
    if (this.restoreFlight) return this.restoreFlight
    if (this.started && this.state.status !== 'error') return Promise.resolve()
    this.started = true
    const expected = ++this.revision
    this.set({ status: 'loading', error: null })
    const flight = (async () => {
      try {
        await this.http.refresh()
        await this.loadProfile(expected)
      } catch (error) {
        if (isUnauthorized(error)) {
          this.end()
        } else {
          this.http.clear()
          this.queryClient.clear()
          this.set({
            status: 'error',
            profile: null,
            error:
              'Unable to restore your session. Check your connection and try again.',
          })
        }
      }
    })().finally(() => {
      if (this.restoreFlight === flight) this.restoreFlight = null
    })
    this.restoreFlight = flight
    return flight
  }

  login = async (input: LoginInput) => {
    if (this.state.busy) return
    this.http.clear()
    this.queryClient.clear()
    const expected = ++this.revision
    this.set({ busy: true, error: null })
    try {
      await this.http.login(input)
      await this.loadProfile(expected)
    } catch (error) {
      this.http.clear()
      this.queryClient.clear()
      this.set({
        status: 'anonymous',
        profile: null,
        error: errorMessage(error),
      })
      throw error
    } finally {
      this.set({ busy: false })
    }
  }

  changePassword = async (input: ChangePasswordInput) => {
    if (this.state.busy) return
    this.set({ busy: true, error: null })
    let changed = false
    try {
      await this.http.changePassword(input)
      changed = true
      this.queryClient.clear()
      await this.loadProfile(++this.revision)
    } catch (error) {
      if (changed) {
        this.http.clear()
        this.queryClient.clear()
        this.set({
          status: 'error',
          profile: null,
          error:
            'Your password was changed. Reconnect to continue with your updated account.',
        })
        // The mutation succeeded; let the page retain its intended destination.
        // SessionGate keeps that destination covered until restoration succeeds.
        return
      }
      this.set({
        error:
          errorCode(error) === 'INVALID_CREDENTIALS'
            ? 'The current password is incorrect.'
            : errorMessage(error),
      })
      throw error
    } finally {
      this.set({ busy: false })
    }
  }

  logout = async () => {
    if (this.state.busy) return
    this.set({ busy: true, error: null })
    try {
      await this.http.logout()
      this.end()
    } catch (error) {
      if (this.state.profile) {
        this.set({
          error: 'Sign-out was not confirmed. Please try signing out again.',
        })
      }
      throw error
    } finally {
      this.set({ busy: false })
    }
  }
}
