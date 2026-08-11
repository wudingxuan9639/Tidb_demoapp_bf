import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.schemas import ImportResult
from app.main import (
    import_target_error,
    is_order_import_compatible,
    is_valid_table_name,
    list_schema_table_rows,
    list_schema_tables,
    order_id_sort_clause,
    visible_database_names,
)


class DatabaseBrowserTest(unittest.IsolatedAsyncioTestCase):
    def test_system_databases_are_hidden_and_default_database_is_first(self) -> None:
        databases = visible_database_names(
            ["mysql", "other_app", "demo_app", "information_schema", "performance_schema"],
            default_database="demo_app",
        )

        self.assertEqual(databases, ["demo_app", "other_app"])

    def test_new_table_name_must_be_a_safe_sql_identifier(self) -> None:
        self.assertTrue(is_valid_table_name("orders_august_2026"))
        self.assertFalse(is_valid_table_name("orders-august"))
        self.assertFalse(is_valid_table_name("orders; DROP TABLE order_imports"))

    def test_import_target_requires_order_template_fields(self) -> None:
        self.assertTrue(
            is_order_import_compatible({"id", "order_id", "customer_name", "amount", "order_date"})
        )
        self.assertFalse(is_order_import_compatible({"id", "order_id", "customer_name", "amount"}))

    def test_duplicate_import_result_includes_order_ids_without_replacements(self) -> None:
        result = ImportResult(
            status="duplicate_conflict",
            message="数据部分已经存在，是否要替换？",
            duplicate_order_ids=["ORD-10001", "ORD-10002"],
        )

        self.assertEqual(result.duplicate_order_ids, ["ORD-10001", "ORD-10002"])
        self.assertEqual(result.replaced_rows, 0)

    def test_order_id_sort_is_used_only_for_tables_with_order_id(self) -> None:
        self.assertEqual(order_id_sort_clause({"id", "order_id"}), " ORDER BY `order_id` ASC")
        self.assertEqual(order_id_sort_clause({"id", "customer_name"}), "")

    async def test_import_target_reports_missing_required_columns(self) -> None:
        with patch("app.main.database_names", new=AsyncMock(return_value=["demo_app"])):
            with patch("app.main.schema_table_names", new=AsyncMock(return_value=["legacy_orders"])):
                with patch(
                    "app.main.schema_table_column_names",
                    new=AsyncMock(return_value={"id", "order_id", "customer_name", "amount"}),
                ):
                    error = await import_target_error("demo_app", "legacy_orders")

        self.assertEqual(error, "目标表缺少订单导入所需字段：order_id、customer_name、amount、order_date")

    async def test_unknown_database_is_rejected_before_table_lookup(self) -> None:
        with patch("app.main.database_names", new=AsyncMock(return_value=["demo_app"])):
            with self.assertRaises(HTTPException) as error:
                await list_schema_tables("unknown_database")

        self.assertEqual(error.exception.status_code, 404)
        self.assertEqual(error.exception.detail, "未找到指定的数据库")

    async def test_unknown_table_is_rejected_before_row_query(self) -> None:
        with patch("app.main.database_names", new=AsyncMock(return_value=["demo_app"])):
            with patch("app.main.schema_table_names", new=AsyncMock(return_value=["order_imports"])):
                with self.assertRaises(HTTPException) as error:
                    await list_schema_table_rows("demo_app", "unknown_table")

        self.assertEqual(error.exception.status_code, 404)
        self.assertEqual(error.exception.detail, "未找到指定的数据表")
