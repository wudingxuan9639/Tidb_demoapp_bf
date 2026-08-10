export interface ImportIssue {
  row: number | null
  field: string | null
  message: string
}

export interface ImportResult {
  status: 'success' | 'validation_failed' | 'write_failed'
  message: string
  total_rows: number
  inserted_rows: number
  errors: ImportIssue[]
  target_table: string | null
}

export interface DatabaseTableRows {
  table: string
  columns: string[]
  rows: Record<string, unknown>[]
}

export interface CreateOrderImportTableResult {
  database: string
  table: string
}
