"""The fixed Excel template and the corresponding TiDB column mappings."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ImportColumn:
    header: str
    database_field: str
    description: str
    example: str | int | float


ORDER_IMPORT_COLUMNS = (
    ImportColumn("订单ID", "order_id", "不可重复；仅允许字母、数字、下划线和连字符", "ORD-10001"),
    ImportColumn("客户名称", "customer_name", "必填，最多 100 个字符", "上海示例客户"),
    ImportColumn("订单金额", "amount", "必填，大于 0，最多两位小数", 1288.50),
    ImportColumn("下单日期", "order_date", "必填，格式 YYYY-MM-DD", "2026-08-09"),
)

EXPECTED_HEADERS = tuple(column.header for column in ORDER_IMPORT_COLUMNS)
