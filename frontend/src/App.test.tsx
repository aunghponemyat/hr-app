import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import App from './App'

describe('application shell', () => {
  it('provides a named main heading and communicates that sign-in is not ready', () => {
    render(<App />)

    expect(screen.getByRole('main')).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { level: 1, name: 'HR & Attendance' }),
    ).toBeVisible()
    expect(
      screen.getByText(/employee sign-in will be available/i),
    ).toBeVisible()
  })
})
