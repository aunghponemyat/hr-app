import { useState } from 'react'
import { useAuthState } from '../auth/useAuthState'
import { usePermissions } from '../hooks/usePermissions'
import { useDownload } from '../hooks/useDownload'
import {
  historyStart,
  initialPeriod,
  periodBounds,
  rangeError,
} from '../utils/dates'
import { PeriodFilter } from './PeriodFilter'
import { StatusBanner } from './Feedback'

export function ExportPanel() {
  const { profile } = useAuthState(),
    can = usePermissions(),
    { download, busy, error } = useDownload()
  const [period, setPeriod] = useState(() => initialPeriod(profile!.app.today))
  const bounds = periodBounds(period),
    earliest = can('report.export.any')
      ? undefined
      : historyStart(profile!.app.today)
  const invalid = rangeError(
    bounds.from,
    bounds.to,
    profile!.app.max_report_range_days,
    earliest,
  )
  return (
    <section className="card">
      <h2>Export my attendance</h2>
      <PeriodFilter
        value={period}
        onChange={setPeriod}
        years={[]}
        maxDays={profile!.app.max_report_range_days}
        earliest={earliest}
      />
      <StatusBanner message={error} error />
      <button
        disabled={busy || !!invalid}
        onClick={() =>
          void download('/attendance/export', {
            from: earliest && bounds.from < earliest ? earliest : bounds.from,
            to: bounds.to,
          })
        }
      >
        {busy ? 'Preparing download…' : 'Download CSV'}
      </button>
    </section>
  )
}
