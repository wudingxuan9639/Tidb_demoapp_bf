import type {
  CreateOrderImportTableResult,
  DatabaseTableRows,
  ImportResult,
  OrderInput,
  OrderUpdateInput,
  OrderWriteResult,
  PaginatedOrderRows,
} from './types'

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
  importOrders: (file: File, targetDatabase: string, targetTable: string, replaceExisting = false) => {
    const body = new FormData()
    body.append('file', file)
    body.append('target_database', targetDatabase)
    body.append('target_table', targetTable)
    body.append('replace_existing', String(replaceExisting))
    return request<ImportResult>('/api/order-import', { method: 'POST', body })
  },
  orderTemplateUrl: `${apiBase}/api/order-import/template`,
  listDatabaseTables: () => request<string[]>('/api/tables'),
  listTableRows: (table: string) => request<DatabaseTableRows>(`/api/tables/${encodeURIComponent(table)}/rows`),
  listDatabases: () => request<string[]>('/api/databases'),
  listSchemaTables: (database: string) => request<string[]>(`/api/databases/${encodeURIComponent(database)}/tables`),
  listSchemaTableRows: (database: string, table: string) => request<DatabaseTableRows>(
    `/api/databases/${encodeURIComponent(database)}/tables/${encodeURIComponent(table)}/rows`,
  ),
  listSchemaOrders: (database: string, table: string, page: number) => request<PaginatedOrderRows>(
    `/api/databases/${encodeURIComponent(database)}/tables/${encodeURIComponent(table)}/orders?page=${page}&page_size=100`,
  ),
  createOrder: (database: string, table: string, payload: OrderInput, replaceExisting = false) => request<OrderWriteResult>(
    `/api/databases/${encodeURIComponent(database)}/tables/${encodeURIComponent(table)}/orders`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...payload, replace_existing: replaceExisting }) },
  ),
  updateOrder: (database: string, table: string, orderId: string, payload: OrderUpdateInput) => request<OrderWriteResult>(
    `/api/databases/${encodeURIComponent(database)}/tables/${encodeURIComponent(table)}/orders/${encodeURIComponent(orderId)}`,
    { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) },
  ),
  deleteSchemaOrders: (database: string, table: string, orderIds: string[]) => request<{ deleted_rows: number }>(
    `/api/databases/${encodeURIComponent(database)}/tables/${encodeURIComponent(table)}/orders`,
    { method: 'DELETE', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ order_ids: orderIds }) },
  ),
  listAllOrders: (
    page: number,
    sortBy: 'order_id' | 'order_date',
    searchField: 'order_id' | 'customer_name' | 'amount',
    keyword: string,
  ) => request<PaginatedOrderRows>(
    `/api/orders?page=${page}&page_size=100&sort_by=${sortBy}&search_field=${searchField}&keyword=${encodeURIComponent(keyword)}`,
  ),
  createOrderImportTable: (database: string, tableName: string) => request<CreateOrderImportTableResult>(
    `/api/databases/${encodeURIComponent(database)}/tables`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ table_name: tableName }) },
  ),
  deleteTableRows: (table: string, ids: number[]) => request<{ deleted_rows: number }>(
    `/api/tables/${encodeURIComponent(table)}/rows`,
    { method: 'DELETE', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ids }) },
  ),
}
