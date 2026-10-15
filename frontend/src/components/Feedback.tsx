import { errorMessage } from '../api/errors'

export function StatusBanner({
  message,
  error = false,
}: {
  message: string | null
  error?: boolean
}) {
  return message ? (
    <p
      className={error ? 'error-banner' : 'success-banner'}
      role={error ? 'alert' : 'status'}
    >
      {message}
    </p>
  ) : null
}
export function QueryFeedback({
  pending,
  error,
  retry,
}: {
  pending: boolean
  error: unknown
  retry: () => unknown
}) {
  if (pending) return <p role="status">Loading…</p>
  if (error)
    return (
      <div>
        <StatusBanner message={errorMessage(error)} error />
        <button className="secondary" onClick={() => void retry()}>
          Try again
        </button>
      </div>
    )
  return null
}
