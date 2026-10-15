import { describe, expect, it } from 'vitest'
import { safeDestination } from './destination'
import { passwordSchema } from './validation'

describe('password policy', () => {
  it.each([
    'Password1',
    'ภาษาไทย๑๒',
    'Password²',
    '漢字漢字漢字１２',
    '𐐀'.repeat(7) + '1',
    'a'.repeat(1023) + '1',
  ])('accepts backend-compatible Unicode password %#', (value) => {
    expect(
      passwordSchema.safeParse({
        current_password: 'OldPassword1',
        new_password: value,
        confirmation: value,
      }).success,
    ).toBe(true)
  })
  it.each([
    'short1',
    '123456789',
    'onlyletters',
    'Password½',
    'a'.repeat(1024) + '1',
    '𐐀'.repeat(6) + '1',
  ])('rejects an invalid password %#', (value) => {
    expect(
      passwordSchema.safeParse({
        current_password: 'OldPassword1',
        new_password: value,
        confirmation: value,
      }).success,
    ).toBe(false)
  })
})

describe('safe post-login destinations', () => {
  it.each([
    null,
    '//example.com',
    'https://example.com',
    '/\\example.com',
    '/login',
    '/change-password',
    '/\n/example.com',
  ])('rejects %s', (value) => expect(safeDestination(value)).toBe('/'))
  it('preserves an internal path and query', () =>
    expect(safeDestination('/profile?view=month#export')).toBe(
      '/profile?view=month#export',
    ))
})
