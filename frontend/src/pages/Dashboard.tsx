import { useAuthState } from '../auth/useAuthState'
import { ClockPanel } from '../components/ClockPanel'
import { AttendanceOverview } from '../components/AttendanceOverview'
export function Dashboard() {
  const { profile } = useAuthState()
  return (
    <div className="page-stack">
      <div>
        <p className="eyebrow">Your workday</p>
        <h1>Dashboard</h1>
        <p className="muted">
          Welcome, {profile!.display_name || profile!.first_name}.
        </p>
      </div>
      <ClockPanel />
      <AttendanceOverview employeeId={profile!.id} />
    </div>
  )
}
