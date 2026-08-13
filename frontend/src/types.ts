export interface ImportIssue {
  row: number | null
  field: string | null
  message: string
}

export interface ImportResult {
  status: 'success' | 'validation_failed' | 'duplicate_conflict' | 'write_failed'
  message: string
  total_rows: number
  inserted_rows: number
  errors: ImportIssue[]
  target_table: string | null
  duplicate_order_ids: string[]
  replaced_rows: number
}

export interface DatabaseTableRows {
  table: string
  columns: string[]
  rows: Record<string, unknown>[]
}

export interface PaginatedOrderRows {
  rows: OrderRow[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface OrderRow {
  order_id: string
  customer_name: string
  amount: string | number
  order_date: string
}

export interface OrderInput {
  order_id: string
  customer_name: string
  amount: string
  order_date: string
}

export interface OrderUpdateInput {
  customer_name: string
  amount: string
  order_date: string
}

export interface OrderWriteResult {
  status: 'success' | 'duplicate_conflict'
  message: string
  order_id: string
  duplicate_order_ids: string[]
}

export interface CreateOrderImportTableResult {
  database: string
  table: string
}
