import { useState } from 'react'
import { useAuth } from '../auth/context'
import { errorMessage } from '../api/errors'
import type { Params } from '../api/useApi'

export function downloadFilename(header: unknown): string {
  const name =
    typeof header === 'string'
      ? /filename="?([A-Za-z0-9_.-]+\.csv)"?(?:;|$)/i.exec(header)?.[1]
      : undefined
  return name || 'attendance-report.csv'
}
export function useDownload() {
  const { http } = useAuth()
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<string | null>(null)
  async function download(path: string, params: Params) {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      const response = await http.api.get<Blob>(path, {
        params,
        responseType: 'blob',
      })
      const url = URL.createObjectURL(response.data),
        link = document.createElement('a')
      link.href = url
      link.download = downloadFilename(response.headers['content-disposition'])
      document.body.append(link)
      link.click()
      link.remove()
      setTimeout(() => URL.revokeObjectURL(url), 0)
    } catch (failure) {
      setError(errorMessage(failure))
    } finally {
      setBusy(false)
    }
  }
  return { download, busy, error }
}
