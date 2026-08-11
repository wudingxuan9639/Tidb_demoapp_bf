export interface OrderDisplayColumn {
  source: string
  label: string
}

const ORDER_COLUMN_LABELS = [
  { source: 'order_id', label: '订单ID' },
  { source: 'customer_name', label: '客户名称' },
  { source: 'amount', label: '订单金额' },
  { source: 'order_date', label: '下单日期' },
] as const

export function orderDisplayColumns(columns: string[]): OrderDisplayColumn[] {
  return ORDER_COLUMN_LABELS.flatMap(({ source, label }) => {
    const column = columns.find((candidate) => candidate.toLowerCase() === source)
    return column ? [{ source: column, label }] : []
  })
}
