import type { DatabaseTableRows, ImportResult, ImportTarget } from './types'

const apiBase = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8800'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, options)
  if (!response.ok) {
    throw new Error((await response.json().catch(() => null))?.detail ?? 'Request failed')
  }
  return response.status === 204 ? (undefined as T) : response.json() as Promise<T>
}

export const api = {
  apiBase,
  importOrders: (file: File, targetTable: string) => {
    const body = new FormData()
    body.append('file', file)
    body.append('target_table', targetTable)
    return request<ImportResult>('/api/order-import', { method: 'POST', body })
  },
  orderTemplateUrl: `${apiBase}/api/order-import/template`,
  listDatabaseTables: () => request<string[]>('/api/tables'),
  listTableRows: (table: string) => request<DatabaseTableRows>(`/api/tables/${encodeURIComponent(table)}/rows`),
  deleteTableRows: (table: string, ids: number[]) => request<{ deleted_rows: number }>(
    `/api/tables/${encodeURIComponent(table)}/rows`,
    { method: 'DELETE', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ids }) },
  ),
  listImportTargets: () => request<ImportTarget[]>('/api/import-targets'),
}
