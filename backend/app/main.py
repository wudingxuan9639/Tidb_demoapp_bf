import asyncio
import io
import re
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Font
from sqlalchemy import bindparam, inspect, text
from sqlalchemy.exc import SQLAlchemyError

from .database import engine
from .excel_import import ExcelValidationError, parse_orders
from .events import broker
from .import_rules import ORDER_IMPORT_COLUMNS
from .models import Base, OrderImport, OrderImportArchive
from .schemas import (
    DatabaseTableRows,
    CreateOrderImportTableRequest,
    CreateOrderImportTableResult,
    DeleteRowsRequest,
    DeleteRowsResult,
    ImportIssue,
    ImportResult,
    ImportTarget,
)

IMPORT_TARGETS = {
    "order_imports": ("订单导入表", OrderImport),
    "order_import_archive": ("订单导入归档表", OrderImportArchive),
}

# These schemas are maintained by TiDB/MySQL rather than this application.
SYSTEM_DATABASE_NAMES = frozenset(
    {
        "information_schema",
        "inspection_schema",
        "metrics_schema",
        "mysql",
        "performance_schema",
        "sys",
    }
)
ORDER_IMPORT_REQUIRED_COLUMNS = frozenset({"order_id", "customer_name", "amount", "order_date"})
TABLE_NAME_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(title="Lightweight TiDB Demo", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:8517",
        "http://localhost:8517",
        "http://127.0.0.1:8518",
        "http://localhost:8518",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


async def database_table_names() -> list[str]:
    async with engine.connect() as connection:
        return await connection.run_sync(lambda sync_connection: inspect(sync_connection).get_table_names())


async def database_names() -> list[str]:
    async with engine.connect() as connection:
        schema_names = await connection.run_sync(lambda sync_connection: inspect(sync_connection).get_schema_names())
    return visible_database_names(schema_names)


def visible_database_names(schema_names: list[str], default_database: str | None = None) -> list[str]:
    """Return application schemas, placing the backend's default schema first."""
    if default_database is None:
        default_database = engine.url.database
    return sorted(
        (name for name in schema_names if name.casefold() not in SYSTEM_DATABASE_NAMES),
        key=lambda name: (name != default_database, name.casefold()),
    )


async def schema_table_names(database_name: str) -> list[str]:
    async with engine.connect() as connection:
        return await connection.run_sync(
            lambda sync_connection: inspect(sync_connection).get_table_names(schema=database_name)
        )


async def schema_table_column_names(database_name: str, table_name: str) -> set[str]:
    async with engine.connect() as connection:
        columns = await connection.run_sync(
            lambda sync_connection: inspect(sync_connection).get_columns(table_name, schema=database_name)
        )
    return {str(column["name"]).casefold() for column in columns}


def is_valid_table_name(table_name: str) -> bool:
    return TABLE_NAME_PATTERN.fullmatch(table_name) is not None


def is_order_import_compatible(column_names: set[str]) -> bool:
    return ORDER_IMPORT_REQUIRED_COLUMNS.issubset({column.casefold() for column in column_names})


async def import_target_error(database_name: str, table_name: str) -> str | None:
    if database_name not in await database_names():
        return "请选择页面提供的业务数据库"
    if table_name not in await schema_table_names(database_name):
        return "请选择当前数据库下的数据表，或先新建订单导入表"
    columns = await schema_table_column_names(database_name, table_name)
    if not is_order_import_compatible(columns):
        return "目标表缺少订单导入所需字段：order_id、customer_name、amount、order_date"
    return None


@app.get("/api/tables", response_model=list[str])
async def list_database_tables() -> list[str]:
    return await database_table_names()


@app.get("/api/databases", response_model=list[str])
async def list_databases() -> list[str]:
    return await database_names()


@app.get("/api/databases/{database_name}/tables", response_model=list[str])
async def list_schema_tables(database_name: str) -> list[str]:
    if database_name not in await database_names():
        raise HTTPException(status_code=404, detail="未找到指定的数据库")
    return await schema_table_names(database_name)


@app.post(
    "/api/databases/{database_name}/tables",
    response_model=CreateOrderImportTableResult,
    status_code=201,
)
async def create_order_import_table(
    database_name: str, payload: CreateOrderImportTableRequest
) -> CreateOrderImportTableResult:
    if database_name not in await database_names():
        raise HTTPException(status_code=404, detail="未找到指定的业务数据库")
    if not is_valid_table_name(payload.table_name):
        raise HTTPException(status_code=422, detail="表名只能使用字母、数字和下划线，且必须以字母或下划线开头")
    if payload.table_name in await schema_table_names(database_name):
        raise HTTPException(status_code=409, detail="该数据表已存在，请直接选择它")

    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    f"""
                    CREATE TABLE `{database_name}`.`{payload.table_name}` (
                        `id` BIGINT NOT NULL AUTO_INCREMENT,
                        `order_id` VARCHAR(64) NOT NULL,
                        `customer_name` VARCHAR(100) NOT NULL,
                        `amount` DECIMAL(12, 2) NOT NULL,
                        `order_date` DATE NOT NULL,
                        `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (`id`),
                        UNIQUE KEY `order_id_unique` (`order_id`)
                    )
                    """
                )
            )
    except SQLAlchemyError as error:
        raise HTTPException(status_code=500, detail=f"新建数据表失败：{error.__class__.__name__}") from error

    broker.publish("database_changed")
    return CreateOrderImportTableResult(database=database_name, table=payload.table_name)


@app.get("/api/databases/{database_name}/tables/{table_name}/rows", response_model=DatabaseTableRows)
async def list_schema_table_rows(database_name: str, table_name: str) -> DatabaseTableRows:
    if database_name not in await database_names():
        raise HTTPException(status_code=404, detail="未找到指定的数据库")
    if table_name not in await schema_table_names(database_name):
        raise HTTPException(status_code=404, detail="未找到指定的数据表")

    # Both identifiers originate from TiDB metadata and are checked above before SQL is constructed.
    async with engine.connect() as connection:
        result = await connection.execute(text(f"SELECT * FROM `{database_name}`.`{table_name}` LIMIT 100"))
        columns = list(result.keys())
        rows = [dict(row._mapping) for row in result]
    return DatabaseTableRows(table=table_name, columns=columns, rows=rows)


@app.get("/api/tables/{table_name}/rows", response_model=DatabaseTableRows)
async def list_database_table_rows(table_name: str) -> DatabaseTableRows:
    table_names = await database_table_names()
    if table_name not in table_names:
        raise HTTPException(status_code=404, detail="未找到指定的数据表")

    # table_name originates from database metadata, never directly from arbitrary client input.
    async with engine.connect() as connection:
        result = await connection.execute(text(f"SELECT * FROM `{table_name}` LIMIT 100"))
        columns = list(result.keys())
        rows = [dict(row._mapping) for row in result]
    return DatabaseTableRows(table=table_name, columns=columns, rows=rows)


@app.delete("/api/tables/{table_name}/rows", response_model=DeleteRowsResult)
async def delete_database_table_rows(
    table_name: str, payload: DeleteRowsRequest
) -> DeleteRowsResult:
    if table_name not in IMPORT_TARGETS:
        raise HTTPException(status_code=403, detail="当前表不允许通过页面删除数据")

    # table_name is restricted to the fixed import-target mapping before SQL is constructed.
    statement = text(f"DELETE FROM `{table_name}` WHERE `id` IN :ids").bindparams(
        bindparam("ids", expanding=True)
    )
    async with engine.begin() as connection:
        result = await connection.execute(statement, {"ids": payload.ids})
    broker.publish("database_changed")
    return DeleteRowsResult(deleted_rows=result.rowcount or 0)


@app.get("/api/import-targets", response_model=list[ImportTarget])
async def list_import_targets() -> list[ImportTarget]:
    return [ImportTarget(name=name, label=label) for name, (label, _) in IMPORT_TARGETS.items()]


@app.get("/api/order-import/template")
async def download_order_template() -> StreamingResponse:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "订单导入模板"
    sheet.append([column.header for column in ORDER_IMPORT_COLUMNS])
    sheet.append([column.example for column in ORDER_IMPORT_COLUMNS])
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    sheet.freeze_panes = "A2"
    for column, width in zip(("A", "B", "C", "D"), (20, 22, 16, 18), strict=True):
        sheet.column_dimensions[column].width = width
    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="order-import-template.xlsx"'},
    )


@app.post("/api/order-import", response_model=ImportResult)
async def import_orders(
    file: UploadFile = File(...),
    target_database: str = Form(""),
    target_table: str = Form("order_imports"),
) -> ImportResult:
    database_name = target_database or engine.url.database
    if not database_name:
        return ImportResult(
            status="validation_failed",
            message="未配置默认业务数据库",
            errors=[ImportIssue(field="写入目标数据库", message="请选择页面提供的业务数据库")],
        )
    filename = file.filename or ""
    content = await file.read()
    try:
        orders, total_rows = parse_orders(filename, content)
    except ExcelValidationError as error:
        return ImportResult(
            status="validation_failed",
            message=error.message,
            errors=error.errors,
        )

    target_error = await import_target_error(database_name, target_table)
    if target_error is not None:
        return ImportResult(
            status="validation_failed",
            message="写入目标校验失败，请按提示选择数据库和数据表",
            total_rows=total_rows,
            target_table=target_table,
            errors=[ImportIssue(field="写入目标", message=target_error)],
        )

    try:
        existing_statement = text(
            f"SELECT `order_id` FROM `{database_name}`.`{target_table}` WHERE `order_id` IN :order_ids"
        ).bindparams(bindparam("order_ids", expanding=True))
        insert_statement = text(
            f"""
            INSERT INTO `{database_name}`.`{target_table}`
                (`order_id`, `customer_name`, `amount`, `order_date`)
            VALUES (:order_id, :customer_name, :amount, :order_date)
            """
        )
        async with engine.begin() as connection:
            existing_result = await connection.execute(
                existing_statement, {"order_ids": [order.order_id for order in orders]}
            )
            existing_order_ids = {str(order_id) for order_id in existing_result.scalars()}
            if existing_order_ids:
                return ImportResult(
                    status="validation_failed",
                    message="Excel 数据校验失败，请按错误提示修改后重新上传",
                    total_rows=total_rows,
                    target_table=target_table,
                    errors=[
                        ImportIssue(field="订单ID", message=f"订单ID 已存在于数据库：{order_id}")
                        for order_id in sorted(existing_order_ids)
                    ],
                )
            await connection.execute(
                insert_statement,
                [
                    {
                        "order_id": order.order_id,
                        "customer_name": order.customer_name,
                        "amount": order.amount,
                        "order_date": order.order_date,
                    }
                    for order in orders
                ],
            )
    except SQLAlchemyError:
        return ImportResult(
            status="write_failed",
            message="写入数据库失败，数据未保存。请确认 TiDB 服务可用后重试。",
            total_rows=total_rows,
            target_table=target_table,
        )

    broker.publish("database_changed")
    return ImportResult(
        status="success",
        message="解析并写库成功",
        total_rows=total_rows,
        inserted_rows=len(orders),
        target_table=f"{database_name}.{target_table}",
    )


@app.get("/api/events")
async def item_events(request: Request) -> StreamingResponse:
    queue = broker.subscribe()

    async def stream() -> AsyncGenerator[str, None]:
        try:
            while not await request.is_disconnected():
                try:
                    event_name = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"event: {event_name}\\ndata: refresh\\n\\n"
                except TimeoutError:
                    yield ": keepalive\\n\\n"
        finally:
            broker.unsubscribe(queue)

    return StreamingResponse(stream(), media_type="text/event-stream")
