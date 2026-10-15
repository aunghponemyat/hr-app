import type { ReactNode } from 'react'

export interface Column<T> {
  label: string
  render: (item: T) => ReactNode
}
export function DataTable<T>({
  caption,
  columns,
  items,
  rowKey,
}: {
  caption: string
  columns: Column<T>[]
  items: T[]
  rowKey: (item: T) => string | number
}) {
  return (
    <div
      className="table-scroll"
      tabIndex={0}
      role="region"
      aria-label={caption}
    >
      <table>
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            {columns.map((column) => (
              <th scope="col" key={column.label}>
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={rowKey(item)}>
              {columns.map((column) => (
                <td key={column.label}>{column.render(item)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {!items.length && <p className="empty">No records found.</p>}
    </div>
  )
}
export function Pagination({
  page,
  total,
  pageSize = 25,
  onChange,
}: {
  page: number
  total: number
  pageSize?: number
  onChange: (page: number) => void
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize))
  return (
    <nav className="pagination" aria-label="Pagination">
      <button
        className="secondary"
        disabled={page <= 1}
        onClick={() => onChange(page - 1)}
      >
        Previous
      </button>
      <span>
        Page {page} of {pages} · {total} records
      </span>
      <button
        className="secondary"
        disabled={page >= pages}
        onClick={() => onChange(page + 1)}
      >
        Next
      </button>
    </nav>
  )
}
