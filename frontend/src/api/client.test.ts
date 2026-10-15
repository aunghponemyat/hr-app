import axios from 'axios'
import type { InternalAxiosRequestConfig } from 'axios'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApiClient } from './client'
import { deferred, invalidToken, mockTransport, pair } from '../test/transport'
import type { Reply } from '../test/transport'

let restore: () => void
afterEach(() => restore?.())
const events = () => ({ expired: vi.fn(), passwordRequired: vi.fn() })

describe('credentialed API client', () => {
  it('encodes OAuth2 login, keeps the token in memory and attaches it to API requests', async () => {
    const requests: InternalAxiosRequestConfig[] = []
    restore = mockTransport((config) => {
      requests.push(config)
      return { data: pair() }
    })
    const client = createApiClient(events())
    const local = vi.spyOn(Storage.prototype, 'setItem')
    await client.login({ username: 'EMP0001', password: 'Test+Pass123&' })
    await client.api.get('/me')
    expect(new URLSearchParams(requests[0].data).get('password')).toBe(
      'Test+Pass123&',
    )
    expect(requests[0].headers.get('Content-Type')).toBe(
      'application/x-www-form-urlencoded;charset=utf-8',
    )
    expect(requests.every((config) => config.withCredentials)).toBe(true)
    expect(requests[1].headers.get('Authorization')).toBe('Bearer test-access')
    expect(local).not.toHaveBeenCalled()
  })

  it('coalesces concurrent 401s and retries both with the fresh token', async () => {
    const refresh = deferred<Reply>()
    let refreshCount = 0
    let success = 0
    restore = mockTransport((config) => {
      if (config.url === '/auth/login') return { data: pair('old') }
      if (config.url === '/auth/refresh') {
        refreshCount++
        return refresh.promise
      }
      if (config.headers.get('Authorization') === 'Bearer old')
        return invalidToken
      success++
      return { data: 'ok' }
    })
    const client = createApiClient(events())
    await client.login({ username: 'EMP0001', password: 'Password123' })
    const first = client.api.get('/one')
    const second = client.api.get('/two')
    await vi.waitFor(() => expect(refreshCount).toBe(1))
    refresh.resolve({ data: pair('fresh') })
    await Promise.all([first, second])
    expect(refreshCount).toBe(1)
    expect(success).toBe(2)
  })

  it('reuses a completed refresh for a delayed old-token 401', async () => {
    const delayed = deferred<Reply>()
    let refreshCount = 0
    restore = mockTransport((config) => {
      if (config.url === '/auth/login') return { data: pair('old') }
      if (config.url === '/auth/refresh') {
        refreshCount++
        return { data: pair('fresh') }
      }
      if (config.headers.get('Authorization') === 'Bearer old')
        return config.url === '/slow' ? delayed.promise : invalidToken
      return { data: 'ok' }
    })
    const client = createApiClient(events())
    await client.login({ username: 'EMP0001', password: 'Password123' })
    const slow = client.api.get('/slow')
    await client.api.get('/fast')
    delayed.resolve(invalidToken)
    await slow
    expect(refreshCount).toBe(1)
  })

  it.each(['refresh failure', 'retry failure'])(
    'expires the session after %s without looping',
    async (mode) => {
      let count = 0
      restore = mockTransport((config) => {
        if (config.url === '/auth/refresh') {
          count++
          return mode === 'refresh failure' ? invalidToken : { data: pair() }
        }
        return invalidToken
      })
      const handlers = events()
      const client = createApiClient(handlers)
      await expect(client.api.get('/me')).rejects.toBeDefined()
      expect(count).toBe(1)
      expect(handlers.expired).toHaveBeenCalledOnce()
    },
  )

  it('does not refresh or expire the session for a wrong current password or ordinary 403', async () => {
    const seen: string[] = []
    restore = mockTransport((config) => {
      seen.push(config.url!)
      return config.url === '/auth/change-password'
        ? { status: 401, data: { code: 'INVALID_CREDENTIALS' } }
        : { status: 403, data: { code: 'OUT_OF_SCOPE' } }
    })
    const handlers = events()
    const client = createApiClient(handlers)
    await expect(
      client.changePassword({
        current_password: 'bad',
        new_password: 'NewPass123',
      }),
    ).rejects.toBeDefined()
    await expect(client.api.get('/forbidden')).rejects.toBeDefined()
    expect(seen).toEqual(['/auth/change-password', '/forbidden'])
    expect(handlers.expired).not.toHaveBeenCalled()
  })

  it('signals a server-forced password change', async () => {
    restore = mockTransport(() => ({
      status: 403,
      data: { code: 'PASSWORD_CHANGE_REQUIRED' },
    }))
    const handlers = events()
    await expect(
      createApiClient(handlers).api.get('/attendance/today'),
    ).rejects.toBeDefined()
    expect(handlers.passwordRequired).toHaveBeenCalledOnce()
  })

  it.each(['refresh', 'request'])(
    'ignores a late %s response after the local session changes',
    async (mode) => {
      const pending = deferred<Reply>()
      restore = mockTransport((config) =>
        config.url === '/auth/login'
          ? { data: pair('new-account') }
          : pending.promise,
      )
      const handlers = events()
      const client = createApiClient(handlers)
      const old = mode === 'refresh' ? client.refresh() : client.api.get('/me')
      const result = old.catch((error: unknown) => error)
      await Promise.resolve()
      client.clear()
      await client.login({ username: 'EMP0002', password: 'Password123' })
      pending.resolve({
        data: mode === 'refresh' ? pair('obsolete') : 'old-account',
      })
      expect(axios.isCancel(await result)).toBe(true)
      expect(handlers.expired).not.toHaveBeenCalled()
    },
  )

  it('waits for refresh before logout and sends the rotated access token', async () => {
    const pending = deferred<Reply>()
    let logoutToken: unknown
    restore = mockTransport((config) => {
      if (config.url === '/auth/refresh') return pending.promise
      logoutToken = config.headers.get('Authorization')
      return { data: { message: 'Logged out.' } }
    })
    const client = createApiClient(events())
    const refresh = client.refresh()
    const logout = client.logout()
    expect(logoutToken).toBeUndefined()
    pending.resolve({ data: pair('rotated') })
    await Promise.all([refresh, logout])
    expect(logoutToken).toBe('Bearer rotated')
  })

  it('refreshes an expired access token before retrying logout', async () => {
    let attempts = 0
    restore = mockTransport((config) => {
      if (config.url === '/auth/refresh') return { data: pair('fresh') }
      attempts++
      return attempts === 1
        ? invalidToken
        : { data: { message: 'Logged out.' } }
    })
    await createApiClient(events()).logout()
    expect(attempts).toBe(2)
  })

  it('finishes a pending refresh before changing the password and replaces the old token', async () => {
    const pending = deferred<Reply>()
    let passwordToken: unknown
    let profileToken: unknown
    restore = mockTransport((config) => {
      if (config.url === '/auth/refresh') return pending.promise
      if (config.url === '/auth/change-password') {
        passwordToken = config.headers.get('Authorization')
        return { data: pair('password-changed') }
      }
      profileToken = config.headers.get('Authorization')
      return { data: 'ok' }
    })
    const client = createApiClient(events())
    const refresh = client.refresh()
    const change = client.changePassword({
      current_password: 'OldPassword1',
      new_password: 'NewPassword2',
    })
    expect(passwordToken).toBeUndefined()
    pending.resolve({ data: pair('rotated') })
    await Promise.all([refresh, change])
    await client.api.get('/me')
    expect(passwordToken).toBe('Bearer rotated')
    expect(profileToken).toBe('Bearer password-changed')
  })

  it('refreshes an expired access token before retrying a password change once', async () => {
    let attempts = 0
    restore = mockTransport((config) => {
      if (config.url === '/auth/refresh') return { data: pair('refreshed') }
      attempts++
      return attempts === 1 ? invalidToken : { data: pair('changed') }
    })
    const result = await createApiClient(events()).changePassword({
      current_password: 'OldPassword1',
      new_password: 'NewPassword2',
    })
    expect(attempts).toBe(2)
    expect(result.access_token).toBe('changed')
  })

  it('blocks new protected requests and refreshes during password replacement', async () => {
    const pending = deferred<Reply>()
    let calls = 0
    restore = mockTransport(() => {
      calls++
      return pending.promise
    })
    const client = createApiClient(events())
    const change = client.changePassword({
      current_password: 'OldPassword1',
      new_password: 'NewPassword2',
    })
    await expect(client.api.get('/private')).rejects.toSatisfy(axios.isCancel)
    await expect(client.refresh()).rejects.toSatisfy(axios.isCancel)
    pending.resolve({ data: pair('changed') })
    await change
    expect(calls).toBe(1)
  })
})
