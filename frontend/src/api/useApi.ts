import { useMemo } from 'react'
import { useAuth } from '../auth/context'
import type { Page } from '../types/domain'

export type Params = Record<string, string | number | boolean | undefined>

export function useApi() {
  const { http } = useAuth()
  return useMemo(
    () => ({
      get: async <T>(
        url: string,
        params?: Params,
        signal?: AbortSignal,
      ): Promise<T> => (await http.api.get<T>(url, { params, signal })).data,
      post: async <T>(url: string, data?: unknown): Promise<T> =>
        (await http.api.post<T>(url, data)).data,
      patch: async <T>(url: string, data: unknown): Promise<T> =>
        (await http.api.patch<T>(url, data)).data,
      remove: async (url: string): Promise<void> => {
        await http.api.delete(url)
      },
      all: async <T>(
        url: string,
        params?: Params,
        signal?: AbortSignal,
      ): Promise<T[]> => {
        const items: T[] = []
        for (let page = 1; ; page++) {
          const { data } = await http.api.get<Page<T>>(url, {
            params: { ...params, page, page_size: 100 },
            signal,
          })
          items.push(...data.items)
          if (items.length >= data.total || data.items.length === 0)
            return items
        }
      },
    }),
    [http],
  )
}
