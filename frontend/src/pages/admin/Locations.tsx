import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useApi } from '../../api/useApi'
import { errorMessage } from '../../api/errors'
import type { Location, Page } from '../../types/domain'
import { DataTable, Pagination } from '../../components/DataTable'
import { QueryFeedback, StatusBanner } from '../../components/Feedback'
import { ConfirmDialog } from '../../components/Dialog'
import { LocationEditor } from './LocationEditor'

export function Locations() {
  const api = useApi(),
    client = useQueryClient(),
    [page, setPage] = useState(1)
  const [editor, setEditor] = useState<Location | 'new' | null>(null),
    [remove, setRemove] = useState<Location | null>(null)
  const query = useQuery({
    queryKey: ['admin', 'locations', page],
    queryFn: ({ signal }) =>
      api.get<Page<Location>>(
        '/admin/work-locations',
        { page, page_size: 25 },
        signal,
      ),
  })
  const deletion = useMutation({
    mutationFn: (location: Location) =>
      api.remove(`/admin/work-locations/${location.id}`),
    onSuccess: () => {
      setRemove(null)
      void client.invalidateQueries({ queryKey: ['admin'] })
    },
  })
  return (
    <div className="page-stack">
      <div className="section-heading">
        <h1>Work locations</h1>
        <button onClick={() => setEditor('new')}>Create location</button>
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
              caption="Work locations"
              items={query.data.items}
              rowKey={(location) => location.id}
              columns={[
                { label: 'Name', render: (location) => location.name },
                { label: 'Latitude', render: (location) => location.latitude },
                {
                  label: 'Longitude',
                  render: (location) => location.longitude,
                },
                {
                  label: 'Radius',
                  render: (location) => `${location.allowed_radius_m} m`,
                },
                {
                  label: 'Actions',
                  render: (location) => (
                    <div className="actions">
                      <button
                        className="secondary"
                        onClick={() => setEditor(location)}
                      >
                        Edit
                      </button>
                      <button
                        className="secondary"
                        onClick={() => {
                          deletion.reset()
                          setRemove(location)
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
        <LocationEditor
          location={editor === 'new' ? null : editor}
          onClose={() => setEditor(null)}
        />
      )}
      {remove && (
        <ConfirmDialog
          title={`Delete ${remove.name}?`}
          onClose={() => setRemove(null)}
          onConfirm={() => deletion.mutate(remove)}
          busy={deletion.isPending}
        >
          <span>
            Locations linked to teams or attendance cannot be deleted.
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
