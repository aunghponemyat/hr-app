import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useApi } from '../../api/useApi'
import { errorMessage } from '../../api/errors'
import type { Page, Team } from '../../types/domain'
import { DataTable, Pagination } from '../../components/DataTable'
import { QueryFeedback, StatusBanner } from '../../components/Feedback'
import { ConfirmDialog } from '../../components/Dialog'
import { TeamEditor } from './TeamEditor'
import { TeamAssociations } from './TeamAssociations'

export function Teams() {
  const api = useApi(),
    client = useQueryClient(),
    [page, setPage] = useState(1)
  const [editor, setEditor] = useState<Team | 'new' | null>(null),
    [manage, setManage] = useState<Team | null>(null),
    [remove, setRemove] = useState<Team | null>(null)
  const query = useQuery({
    queryKey: ['admin', 'teams', page],
    queryFn: ({ signal }) =>
      api.get<Page<Team>>('/admin/teams', { page, page_size: 25 }, signal),
  })
  const deletion = useMutation({
    mutationFn: (team: Team) => api.remove(`/admin/teams/${team.id}`),
    onSuccess: () => {
      setRemove(null)
      void client.invalidateQueries({ queryKey: ['admin'] })
    },
  })
  return (
    <div className="page-stack">
      <div className="section-heading">
        <h1>Teams</h1>
        <button onClick={() => setEditor('new')}>Create team</button>
      </div>
      <section className="card">
        <QueryFeedback
          pending={query.isPending}
          error={query.error}
          retry={query.refetch}
        />
        {query.data && (
          <>
            <DataTable
              caption="Teams"
              items={query.data.items}
              rowKey={(team) => team.id}
              columns={[
                { label: 'Team', render: (team) => team.name },
                {
                  label: 'Description',
                  render: (team) => team.description || '—',
                },
                {
                  label: 'Actions',
                  render: (team) => (
                    <div className="actions">
                      <button
                        className="secondary"
                        onClick={() => setEditor(team)}
                      >
                        Edit
                      </button>
                      <button
                        className="secondary"
                        onClick={() => setManage(team)}
                      >
                        Manage assignments
                      </button>
                      <button
                        className="secondary"
                        onClick={() => {
                          deletion.reset()
                          setRemove(team)
                        }}
                      >
                        Delete
                      </button>
                    </div>
                  ),
                },
              ]}
            />
            <Pagination
              page={page}
              total={query.data.total}
              onChange={setPage}
            />
          </>
        )}
      </section>
      {editor && (
        <TeamEditor
          team={editor === 'new' ? null : editor}
          onClose={() => setEditor(null)}
        />
      )}
      {manage && (
        <TeamAssociations team={manage} onClose={() => setManage(null)} />
      )}
      {remove && (
        <ConfirmDialog
          title={`Delete ${remove.name}?`}
          onClose={() => setRemove(null)}
          onConfirm={() => deletion.mutate(remove)}
          busy={deletion.isPending}
        >
          <span>
            Only teams without current links or membership/manager history can
            be deleted.
          </span>
          <StatusBanner
            message={deletion.error ? errorMessage(deletion.error) : null}
            error
          />
        </ConfirmDialog>
      )}
    </div>
  )
}
