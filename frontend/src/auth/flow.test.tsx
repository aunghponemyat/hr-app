import { StrictMode } from 'react'
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it } from 'vitest'
import { AppRoutes } from '../routes'
import { AuthProvider } from './AuthProvider'
import { AuthSession } from './session'
import {
  adminPermissions,
  invalidToken,
  mockTransport,
  pair,
  profile,
  selfPermissions,
  deferred,
} from '../test/transport'
import type { Handler, Reply } from '../test/transport'

let restore: () => void
afterEach(() => restore?.())

function mount(
  handler: Handler,
  path: string | { pathname: string; state: unknown } = '/',
) {
  restore = mockTransport(handler)
  const session = new AuthSession()
  render(
    <StrictMode>
      <AuthProvider session={session}>
        <MemoryRouter initialEntries={[path]}>
          <AppRoutes />
        </MemoryRouter>
      </AuthProvider>
    </StrictMode>,
  )
  return session
}

function fillLogin() {
  fireEvent.change(screen.getByLabelText('Employee ID'), {
    target: { value: 'EMP0001' },
  })
  fireEvent.change(screen.getByLabelText('Password'), {
    target: { value: 'DefaultPass123' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
}

function fillPassword(
  current = 'DefaultPass123',
  next = 'FreshPassword456',
  confirmation = next,
) {
  fireEvent.change(screen.getByLabelText('Current password'), {
    target: { value: current },
  })
  fireEvent.change(screen.getByLabelText('New password'), {
    target: { value: next },
  })
  fireEvent.change(screen.getByLabelText('Confirm new password'), {
    target: { value: confirmation },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Save password' }))
}

describe('browser authentication flows', () => {
  it('redirects anonymous visits to login and restores the requested destination after login', async () => {
    const session = mount(
      (config) =>
        config.url === '/auth/refresh'
          ? invalidToken
          : { data: config.url === '/me' ? profile() : pair() },
      '/profile',
    )
    await screen.findByRole('heading', { name: 'HR & Attendance' })
    fillLogin()
    await screen.findByRole('heading', { name: 'Profile' })
    expect(session.getSnapshot().profile?.employee_id).toBe('EMP0001')
  })

  it('completes login → forced change → dashboard with fresh profile and cleared cached data', async () => {
    let forced = true
    let passwordBody: unknown
    const session = mount((config) => {
      if (config.url === '/auth/refresh') return invalidToken
      if (config.url === '/me')
        return { data: profile(selfPermissions, forced) }
      if (config.url === '/auth/change-password') {
        forced = false
        passwordBody = JSON.parse(config.data)
        return { data: pair('changed') }
      }
      return { data: pair('initial', true) }
    })
    await screen.findByRole('button', { name: 'Sign in' })
    fillLogin()
    await screen.findByRole('heading', { name: 'Change password' })
    expect(
      screen.queryByRole('link', { name: 'Dashboard' }),
    ).not.toBeInTheDocument()
    session.queryClient.setQueryData(['private-old-data'], 'old')
    fillPassword()
    await screen.findByRole('heading', { name: 'Dashboard' })
    expect(passwordBody).toEqual({
      current_password: 'DefaultPass123',
      new_password: 'FreshPassword456',
    })
    expect(
      session.queryClient.getQueryData(['private-old-data']),
    ).toBeUndefined()
    expect(session.getSnapshot().profile?.must_change_password).toBe(false)
  })

  it.each(['/', '/leave', '/team', '/profile', '/admin/employees', '/unknown'])(
    'forces password change before rendering %s',
    async (path) => {
      mount(
        (config) => ({
          data:
            config.url === '/me'
              ? profile(selfPermissions, true)
              : pair('initial', true),
        }),
        path,
      )
      await screen.findByRole('heading', { name: 'Change password' })
      expect(
        screen.queryByRole('link', { name: 'Leave' }),
      ).not.toBeInTheDocument()
    },
  )

  it('restores a cookie session once under StrictMode without showing login', async () => {
    let refreshes = 0
    mount((config) => {
      if (config.url === '/auth/refresh') refreshes++
      return { data: config.url === '/me' ? profile() : pair() }
    })
    expect(screen.getByRole('status')).toHaveTextContent(
      'Restoring your session',
    )
    await screen.findByRole('heading', { name: 'Dashboard' })
    expect(refreshes).toBe(1)
    expect(screen.queryByLabelText('Password')).not.toBeInTheDocument()
  })

  it('offers retry after an offline bootstrap and recovers', async () => {
    let offline = true
    mount((config) => {
      if (offline) throw new Error('offline')
      return { data: config.url === '/me' ? profile() : pair() }
    })
    await screen.findByRole('heading', { name: 'Connection unavailable' })
    offline = false
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    await screen.findByRole('heading', { name: 'Dashboard' })
  })

  it.each([
    ['INVALID_CREDENTIALS', 401, /employee ID or password is incorrect/],
    ['ACCOUNT_LOCKED', 429, /temporarily locked/],
    ['RATE_LIMITED', 429, /too many attempts/i],
    ['INTERNAL_ERROR', 500, /unable to complete/i],
  ] as const)(
    'shows safe %s login errors and clears the password',
    async (code, status, message) => {
      let refreshes = 0
      mount((config) => {
        if (config.url === '/auth/refresh') {
          refreshes++
          return invalidToken
        }
        return {
          status,
          data: { code, message: 'secret should not be displayed' },
        }
      })
      await screen.findByRole('button', { name: 'Sign in' })
      fillLogin()
      expect(await screen.findByRole('alert')).toHaveTextContent(message)
      expect(screen.getByLabelText('Password')).toHaveValue('')
      expect(refreshes).toBe(1)
      expect(screen.queryByText(/secret should/)).not.toBeInTheDocument()
    },
  )

  it('validates login fields before sending credentials', async () => {
    let logins = 0
    mount((config) => {
      if (config.url === '/auth/login') logins++
      return invalidToken
    })
    await screen.findByRole('button', { name: 'Sign in' })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByText(/enter your employee ID/i)).toBeVisible()
    expect(screen.getByLabelText('Employee ID')).toHaveAttribute(
      'aria-invalid',
      'true',
    )
    expect(logins).toBe(0)
  })

  it('validates password difference and confirmation before submitting', async () => {
    let changes = 0
    mount((config) => {
      if (config.url === '/auth/change-password') changes++
      return {
        data: config.url === '/me' ? profile(selfPermissions, true) : pair(),
      }
    })
    await screen.findByRole('heading', { name: 'Change password' })
    fillPassword('DefaultPass123', 'DefaultPass123', 'mismatch')
    expect(
      await screen.findByText(
        /choose a different password from your current one/i,
      ),
    ).toBeVisible()
    expect(screen.getByText(/passwords do not match/i)).toBeVisible()
    expect(changes).toBe(0)
  })

  it('keeps a wrong current password as a form error and allows retry', async () => {
    let attempts = 0
    let forced = true
    mount((config) => {
      if (config.url === '/auth/change-password') {
        attempts++
        if (attempts === 1)
          return { status: 401, data: { code: 'INVALID_CREDENTIALS' } }
        forced = false
      }
      return {
        data: config.url === '/me' ? profile(selfPermissions, forced) : pair(),
      }
    })
    await screen.findByRole('heading', { name: 'Change password' })
    fillPassword()
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The current password is incorrect.',
    )
    expect(screen.getByLabelText('Current password')).toHaveValue('')
    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: 'Save password' }),
      ).toBeEnabled(),
    )
    fillPassword()
    await screen.findByRole('heading', { name: 'Dashboard' })
  })

  it('disables login submission while credentials are in flight', async () => {
    const pending = deferred<Reply>()
    let logins = 0
    mount((config) => {
      if (config.url === '/auth/refresh') return invalidToken
      if (config.url === '/auth/login') {
        logins++
        return pending.promise
      }
      return { data: profile() }
    })
    await screen.findByRole('button', { name: 'Sign in' })
    fillLogin()
    expect(
      await screen.findByRole('button', { name: 'Signing in…' }),
    ).toBeDisabled()
    expect(logins).toBe(1)
    pending.resolve({ data: pair() })
    await screen.findByRole('heading', { name: 'Dashboard' })
  })

  it('logs out on a failed API refresh and clears private query data', async () => {
    let expired = false
    const session = mount((config) =>
      expired
        ? invalidToken
        : { data: config.url === '/me' ? profile() : pair() },
    )
    await screen.findByRole('heading', { name: 'Dashboard' })
    session.queryClient.setQueryData(['attendance'], 'private')
    expired = true
    await expect(
      session.http.api.get('/attendance/today'),
    ).rejects.toBeDefined()
    await screen.findByRole('button', { name: 'Sign in' })
    expect(session.queryClient.getQueryData(['attendance'])).toBeUndefined()
  })

  it('responds to a server password-change-required response', async () => {
    const session = mount((config) =>
      config.url === '/attendance/today'
        ? { status: 403, data: { code: 'PASSWORD_CHANGE_REQUIRED' } }
        : { data: config.url === '/me' ? profile() : pair() },
    )
    await screen.findByRole('heading', { name: 'Dashboard' })
    await expect(
      session.http.api.get('/attendance/today'),
    ).rejects.toBeDefined()
    await screen.findByRole('heading', { name: 'Change password' })
  })

  it('confirms logout, clears cached data and returns to login', async () => {
    const session = mount((config) => ({
      data: config.url === '/me' ? profile() : pair(),
    }))
    await screen.findByRole('heading', { name: 'Dashboard' })
    session.queryClient.setQueryData(['private'], 'private')
    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))
    await screen.findByRole('button', { name: 'Sign in' })
    expect(session.queryClient.getQueryCache().getAll()).toHaveLength(0)
  })

  it('keeps a failed server logout visible and retryable', async () => {
    let fail = true
    mount((config) =>
      config.url === '/auth/logout' && fail
        ? { status: 503 }
        : { data: config.url === '/me' ? profile() : pair() },
    )
    await screen.findByRole('heading', { name: 'Dashboard' })
    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Sign-out was not confirmed',
    )
    fail = false
    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))
    await screen.findByRole('button', { name: 'Sign in' })
  })

  it.each([
    ['employee', selfPermissions, ['Dashboard', 'Leave', 'Profile']],
    ['senior_staff', selfPermissions, ['Dashboard', 'Leave', 'Profile']],
    [
      'reporting_manager',
      [...selfPermissions, 'employee.read.team'],
      ['Dashboard', 'Leave', 'Team', 'Profile'],
    ],
    [
      'hr',
      [...selfPermissions, ...adminPermissions],
      [
        'Dashboard',
        'Leave',
        'Team',
        'Profile',
        'Employees',
        'Teams',
        'Work locations',
        'Reports',
        'All attendance',
      ],
    ],
    [
      'c_level',
      [...selfPermissions, ...adminPermissions],
      [
        'Dashboard',
        'Leave',
        'Team',
        'Profile',
        'Employees',
        'Teams',
        'Work locations',
        'Reports',
        'All attendance',
      ],
    ],
  ])(
    'shows the expected menu for %s grants',
    async (name, permissions, labels) => {
      mount((config) => {
        const employee = profile(permissions)
        employee.role.name = name
        return { data: config.url === '/me' ? employee : pair() }
      })
      await screen.findByRole('heading', { name: 'Dashboard' })
      expect(
        within(screen.getByRole('navigation'))
          .getAllByRole('link')
          .map((link) => link.textContent),
      ).toEqual(labels)
    },
  )

  it('uses permissions rather than the role name for navigation and direct URLs', async () => {
    mount((config) => {
      const employee = profile()
      employee.role.name = 'hr'
      return { data: config.url === '/me' ? employee : pair() }
    }, '/admin/employees')
    await screen.findByRole('heading', { name: 'Access denied' })
    expect(
      screen.queryByRole('link', { name: 'Employees' }),
    ).not.toBeInTheDocument()
  })

  it.each([
    '/team',
    '/admin/teams',
    '/admin/locations',
    '/admin/reports',
    '/admin/all-attendance',
  ])('denies an employee direct access to %s', async (path) => {
    mount(
      (config) => ({ data: config.url === '/me' ? profile() : pair() }),
      path,
    )
    await screen.findByRole('heading', { name: 'Access denied' })
  })

  it('lets a normal user visit password change from Profile', async () => {
    mount(
      (config) => ({ data: config.url === '/me' ? profile() : pair() }),
      '/profile',
    )
    fireEvent.click(
      await screen.findByRole('link', { name: 'Change password' }),
    )
    await screen.findByRole('heading', { name: 'Change password' })
    expect(screen.getByRole('link', { name: 'Cancel' })).toBeVisible()
  })

  it('rejects an external destination supplied to login', async () => {
    mount((config) => ({ data: config.url === '/me' ? profile() : pair() }), {
      pathname: '/login',
      state: { from: '//example.com' },
    })
    await screen.findByRole('heading', { name: 'Dashboard' })
  })

  it('places focus on the main content when navigating', async () => {
    mount((config) => ({ data: config.url === '/me' ? profile() : pair() }))
    await screen.findByRole('heading', { name: 'Dashboard' })
    fireEvent.click(screen.getByRole('link', { name: 'Profile' }))
    await waitFor(() => expect(screen.getByRole('main')).toHaveFocus())
    expect(screen.getByRole('link', { name: 'Profile' })).toHaveAttribute(
      'aria-current',
      'page',
    )
  })

  it('recovers a completed password change when the subsequent profile request fails', async () => {
    let changed = false
    let offline = false
    mount((config) => {
      if (config.url === '/auth/change-password') {
        changed = true
        offline = true
        return { data: pair('changed') }
      }
      if (config.url === '/me' && offline) return { status: 503 }
      return {
        data:
          config.url === '/me' ? profile(selfPermissions, !changed) : pair(),
      }
    })
    await screen.findByRole('heading', { name: 'Change password' })
    fillPassword()
    await screen.findByRole('heading', { name: 'Connection unavailable' })
    expect(screen.getByRole('alert')).toHaveTextContent(
      'Your password was changed',
    )
    offline = false
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    await screen.findByRole('heading', { name: 'Dashboard' })
  })
})
