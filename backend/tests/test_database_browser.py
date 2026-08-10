import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.main import (
    import_target_error,
    is_order_import_compatible,
    is_valid_table_name,
    list_schema_table_rows,
    list_schema_tables,
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
