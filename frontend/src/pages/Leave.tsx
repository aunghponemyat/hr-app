import { useQuery } from '@tanstack/react-query'
import { useApi } from '../api/useApi'
import { usePermissions } from '../hooks/usePermissions'
import type { LeaveOptions } from '../types/domain'
import { QueryFeedback } from '../components/Feedback'
import { LeaveForm } from '../components/LeaveForm'
import { LeaveList } from '../components/LeaveList'
export function Leave() {
  const api = useApi(),
    can = usePermissions()
  const query = useQuery({
    queryKey: ['leave', 'options'],
    queryFn: ({ signal }) =>
      api.get<LeaveOptions>('/leave/options', undefined, signal),
    enabled: can('leave.create.self', 'leave.create.any'),
  })
  return (
    <div className="page-stack">
      <h1>Leave</h1>
      <div className="leave-layout">
        {can('leave.create.self', 'leave.create.any') && (
          <div>
            <QueryFeedback
              pending={query.isPending}
              error={query.error}
              retry={query.refetch}
            />
            {query.data && <LeaveForm options={query.data} />}
          </div>
        )}
        <LeaveList />
      </div>
    </div>
  )
}
