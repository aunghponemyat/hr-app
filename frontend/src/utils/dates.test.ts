import { describe, expect, it } from 'vitest'
import {
  historyStart,
  initialPeriod,
  leaveEnd,
  officeTime,
  periodBounds,
  rangeError,
} from './dates'
import { leaveSchema } from './leaveValidation'
import { options } from '../test/features'
import { downloadFilename } from '../hooks/useDownload'

describe('dates and leave validation', () => {
  it('uses office time independently of browser timezone', () =>
    expect(officeTime('2026-10-15T02:00:00Z', 'Asia/Bangkok')).toBe('09:00'))
  it('clips the leap-day history boundary', () =>
    expect(historyStart('2024-02-29')).toBe('2023-02-28'))
  it('counts inclusive leap-year ranges', () => {
    expect(rangeError('2024-01-01', '2024-12-31', 366)).toBeNull()
    expect(rangeError('2024-01-01', '2025-01-01', 366)).toContain('366')
  })
  it('uses calendar month bounds', () =>
    expect(periodBounds(initialPeriod('2024-02-20'))).toEqual({
      from: '2024-02-01',
      to: '2024-02-29',
    }))
  it('supports the configured Saturday working week', () => {
    expect(leaveEnd('2026-10-16', 2, [0, 1, 2, 3, 4, 5])).toBe('2026-10-17')
    expect(leaveEnd('2026-10-16', 2, [0, 1, 2, 3, 4])).toBe('2026-10-19')
  })
  it.each(['2026-10-17', '2026-10-07', 'bad-date'])(
    'rejects invalid/backdated/nonworking start %s',
    (start_date) => {
      expect(
        leaveSchema(options).safeParse({
          leave_type_id: 1,
          leave_reason_id: 1,
          reason_text: '',
          duration_type: 'full_days',
          half_day_period: '',
          num_days: 1,
          start_date,
          reporting_manager_id: 2,
          remark: '',
        }).success,
      ).toBe(false)
    },
  )
  it.each([
    'attachment; filename="../../unsafe.csv"',
    'attachment; filename="bad.exe"',
    null,
  ])('rejects unsafe download filename %s', (header) =>
    expect(downloadFilename(header)).toBe('attendance-report.csv'),
  )
  it('uses safe filenames provided by the backend', () =>
    expect(
      downloadFilename(
        'attachment; filename="attendance_EMP0001_2026-10-01_2026-10-31.csv"',
      ),
    ).toBe('attendance_EMP0001_2026-10-01_2026-10-31.csv'))
})
