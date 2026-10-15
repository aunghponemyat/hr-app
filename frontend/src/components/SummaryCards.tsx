import type { Summary } from '../types/domain'
export function SummaryCards({ summary }: { summary: Summary }) {
  return (
    <dl className="summary-grid">
      {[
        ['Present', summary.present_days],
        ['Half-day', summary.half_day_days],
        ['Leave', summary.leave_days],
        ['Absent', summary.absent_days],
        ['Worked hours', summary.total_worked_hours.toFixed(2)],
      ].map(([label, value]) => (
        <div key={label} className="summary-card">
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  )
}
