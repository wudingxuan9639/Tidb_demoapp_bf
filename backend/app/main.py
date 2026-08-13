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
from .excel_import import ExcelValidationError, ParsedOrder, parse_orders, validate_order_values
from .events import broker
from .import_rules import ORDER_IMPORT_COLUMNS
from .models import Base, OrderImport, OrderImportArchive
from .schemas import (
    DatabaseTableRows,
    CreateOrderImportTableRequest,
    CreateOrderImportTableResult,
    CreateOrderRequest,
    DeleteRowsRequest,
    DeleteRowsResult,
    DeleteOrderRowsRequest,
    ImportIssue,
    ImportResult,
    ImportTarget,
    OrderUpdateInput,
    OrderWriteResult,
    PaginatedOrderRows,
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
PAGE_SIZE = 100


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


def order_id_sort_clause(column_names: set[str]) -> str:
    return " ORDER BY `order_id` ASC" if "order_id" in {name.casefold() for name in column_names} else ""


def page_offset(page: int, page_size: int = PAGE_SIZE) -> int:
    return (page - 1) * page_size


def order_sort_clause(sort_by: str) -> str:
    if sort_by == "order_id":
        return " ORDER BY `order_id` ASC"
    if sort_by == "order_date":
        return " ORDER BY `order_date` DESC, `order_id` ASC"
    raise HTTPException(status_code=422, detail="排序方式只能是 order_id 或 order_date")


def order_search_clause(search_field: str, keyword: str) -> tuple[str, dict[str, str]]:
    if not keyword.strip():
        return "", {}
    if search_field == "order_id":
        return " WHERE `order_id` LIKE :keyword", {"keyword": f"%{keyword.strip()}%"}
    if search_field == "customer_name":
        return " WHERE `customer_name` LIKE :keyword", {"keyword": f"%{keyword.strip()}%"}
    if search_field == "amount":
        return " WHERE CAST(`amount` AS CHAR) LIKE :keyword", {"keyword": f"%{keyword.strip()}%"}
    raise HTTPException(status_code=422, detail="查询字段只能是 order_id、customer_name 或 amount")


async def import_target_error(database_name: str, table_name: str) -> str | None:
    if database_name not in await database_names():
        return "请选择页面提供的业务数据库"
    if table_name not in await schema_table_names(database_name):
        return "请选择当前数据库下的数据表，或先新建订单导入表"
    columns = await schema_table_column_names(database_name, table_name)
    if not is_order_import_compatible(columns):
        return "目标表缺少订单导入所需字段：order_id、customer_name、amount、order_date"
    return None


async def validated_order_target(database_name: str, table_name: str) -> None:
    target_error = await import_target_error(database_name, table_name)
    if target_error is not None:
        raise HTTPException(status_code=422, detail=target_error)


def order_write_error(error: ExcelValidationError) -> HTTPException:
    detail = "; ".join(
        f"{issue.field or '数据'}：{issue.message}" for issue in error.errors
    ) or error.message
    return HTTPException(status_code=422, detail=detail)


def order_values(order: ParsedOrder) -> dict[str, object]:
    return {
        "order_id": order.order_id,
        "customer_name": order.customer_name,
        "amount": order.amount,
        "order_date": order.order_date,
    }


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
    sort_clause = order_id_sort_clause(await schema_table_column_names(database_name, table_name))
    async with engine.connect() as connection:
        result = await connection.execute(
            text(f"SELECT * FROM `{database_name}`.`{table_name}`{sort_clause} LIMIT 100")
        )
        columns = list(result.keys())
        rows = [dict(row._mapping) for row in result]
    return DatabaseTableRows(table=table_name, columns=columns, rows=rows)


@app.get("/api/databases/{database_name}/tables/{table_name}/orders", response_model=PaginatedOrderRows)
async def list_schema_orders(
    database_name: str, table_name: str, page: int = 1, page_size: int = PAGE_SIZE
) -> PaginatedOrderRows:
    if page < 1 or page_size != PAGE_SIZE:
        raise HTTPException(status_code=422, detail="页码必须从 1 开始，单页固定 100 条")
    await validated_order_target(database_name, table_name)
    async with engine.connect() as connection:
        total = int(
            (await connection.execute(text(f"SELECT COUNT(*) FROM `{database_name}`.`{table_name}`"))).scalar_one()
        )
        result = await connection.execute(
            text(
                f"SELECT `order_id`, `customer_name`, `amount`, `order_date` "
                f"FROM `{database_name}`.`{table_name}` ORDER BY `order_id` ASC "
                "LIMIT :limit OFFSET :offset"
            ),
            {"limit": page_size, "offset": page_offset(page, page_size)},
        )
        rows = [dict(row._mapping) for row in result]
    return PaginatedOrderRows(
        rows=rows,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=max(1, (total + page_size - 1) // page_size),
    )


@app.post("/api/databases/{database_name}/tables/{table_name}/orders", response_model=OrderWriteResult)
async def create_order(
    database_name: str, table_name: str, payload: CreateOrderRequest
) -> OrderWriteResult:
    await validated_order_target(database_name, table_name)
    try:
        order = validate_order_values(payload.order_id, payload.customer_name, payload.amount, payload.order_date)
    except ExcelValidationError as error:
        raise order_write_error(error) from error
    existing_statement = text(
        f"SELECT `order_id` FROM `{database_name}`.`{table_name}` WHERE `order_id` = :order_id"
    )
    try:
        async with engine.begin() as connection:
            exists = (await connection.execute(existing_statement, {"order_id": order.order_id})).scalar_one_or_none()
            if exists and not payload.replace_existing:
                return OrderWriteResult(
                    status="duplicate_conflict",
                    message="数据部分已经存在，是否要替换？",
                    order_id=order.order_id,
                    duplicate_order_ids=[order.order_id],
                )
            if exists:
                await connection.execute(
                    text(
                        f"UPDATE `{database_name}`.`{table_name}` SET `customer_name` = :customer_name, "
                        "`amount` = :amount, `order_date` = :order_date WHERE `order_id` = :order_id"
                    ),
                    order_values(order),
                )
                message = "订单已替换"
            else:
                await connection.execute(
                    text(
                        f"INSERT INTO `{database_name}`.`{table_name}` "
                        "(`order_id`, `customer_name`, `amount`, `order_date`) "
                        "VALUES (:order_id, :customer_name, :amount, :order_date)"
                    ),
                    order_values(order),
                )
                message = "订单已新增"
    except SQLAlchemyError as error:
        raise HTTPException(status_code=500, detail=f"写入数据库失败：{error.__class__.__name__}") from error
    broker.publish("database_changed")
    return OrderWriteResult(status="success", message=message, order_id=order.order_id)


@app.patch("/api/databases/{database_name}/tables/{table_name}/orders/{order_id}", response_model=OrderWriteResult)
async def update_order(
    database_name: str, table_name: str, order_id: str, payload: OrderUpdateInput
) -> OrderWriteResult:
    await validated_order_target(database_name, table_name)
    try:
        order = validate_order_values(order_id, payload.customer_name, payload.amount, payload.order_date)
    except ExcelValidationError as error:
        raise order_write_error(error) from error
    try:
        async with engine.begin() as connection:
            result = await connection.execute(
                text(
                    f"UPDATE `{database_name}`.`{table_name}` SET `customer_name` = :customer_name, "
                    "`amount` = :amount, `order_date` = :order_date WHERE `order_id` = :order_id"
                ),
                order_values(order),
            )
            if not result.rowcount:
                raise HTTPException(status_code=404, detail="未找到要修改的订单")
    except SQLAlchemyError as error:
        raise HTTPException(status_code=500, detail=f"写入数据库失败：{error.__class__.__name__}") from error
    broker.publish("database_changed")
    return OrderWriteResult(status="success", message="订单已修改", order_id=order_id)


@app.delete("/api/databases/{database_name}/tables/{table_name}/orders", response_model=DeleteRowsResult)
async def delete_schema_orders(
    database_name: str, table_name: str, payload: DeleteOrderRowsRequest
) -> DeleteRowsResult:
    await validated_order_target(database_name, table_name)
    statement = text(
        f"DELETE FROM `{database_name}`.`{table_name}` WHERE `order_id` IN :order_ids"
    ).bindparams(bindparam("order_ids", expanding=True))
    try:
        async with engine.begin() as connection:
            result = await connection.execute(statement, {"order_ids": payload.order_ids})
    except SQLAlchemyError as error:
        raise HTTPException(status_code=500, detail=f"删除数据失败：{error.__class__.__name__}") from error
    broker.publish("database_changed")
    return DeleteRowsResult(deleted_rows=result.rowcount or 0)


@app.get("/api/orders", response_model=PaginatedOrderRows)
async def list_all_orders(
    page: int = 1,
    page_size: int = PAGE_SIZE,
    sort_by: str = "order_id",
    search_field: str = "order_id",
    keyword: str = "",
) -> PaginatedOrderRows:
    if page < 1 or page_size != PAGE_SIZE:
        raise HTTPException(status_code=422, detail="页码必须从 1 开始，单页固定 100 条")
    sort_clause = order_sort_clause(sort_by)
    search_clause, search_params = order_search_clause(search_field, keyword)
    compatible_targets: list[tuple[str, str]] = []
    for database_name in await database_names():
        for table_name in await schema_table_names(database_name):
            if is_order_import_compatible(await schema_table_column_names(database_name, table_name)):
                compatible_targets.append((database_name, table_name))
    if not compatible_targets:
        return PaginatedOrderRows(rows=[], total=0, page=page, page_size=page_size, total_pages=1)
    union_query = " UNION ALL ".join(
        f"SELECT `order_id`, `customer_name`, `amount`, `order_date` FROM `{database_name}`.`{table_name}`"
        for database_name, table_name in compatible_targets
    )
    try:
        async with engine.connect() as connection:
            total = int(
                (
                    await connection.execute(
                        text(f"SELECT COUNT(*) FROM ({union_query}) AS orders{search_clause}"),
                        search_params,
                    )
                ).scalar_one()
            )
            result = await connection.execute(
                text(
                    f"SELECT * FROM ({union_query}) AS orders{search_clause}{sort_clause} "
                    "LIMIT :limit OFFSET :offset"
                ),
                {**search_params, "limit": page_size, "offset": page_offset(page, page_size)},
            )
            rows = [dict(row._mapping) for row in result]
    except SQLAlchemyError as error:
        raise HTTPException(status_code=500, detail=f"读取订单数据失败：{error.__class__.__name__}") from error
    return PaginatedOrderRows(
        rows=rows,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=max(1, (total + page_size - 1) // page_size),
    )


@app.get("/api/tables/{table_name}/rows", response_model=DatabaseTableRows)
async def list_database_table_rows(table_name: str) -> DatabaseTableRows:
    table_names = await database_table_names()
    if table_name not in table_names:
        raise HTTPException(status_code=404, detail="未找到指定的数据表")

    # table_name originates from database metadata, never directly from arbitrary client input.
    sort_clause = order_id_sort_clause(await schema_table_column_names(engine.url.database or "", table_name))
    async with engine.connect() as connection:
        result = await connection.execute(text(f"SELECT * FROM `{table_name}`{sort_clause} LIMIT 100"))
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
    replace_existing: bool = Form(False),
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
        update_statement = text(
            f"""
            UPDATE `{database_name}`.`{target_table}`
            SET `customer_name` = :customer_name, `amount` = :amount, `order_date` = :order_date
            WHERE `order_id` = :order_id
            """
        )
        replaced_rows = 0
        async with engine.begin() as connection:
            existing_result = await connection.execute(
                existing_statement, {"order_ids": [order.order_id for order in orders]}
            )
            existing_order_ids = {str(order_id) for order_id in existing_result.scalars()}
            if existing_order_ids and not replace_existing:
                return ImportResult(
                    status="duplicate_conflict",
                    message="数据部分已经存在，是否要替换？",
                    total_rows=total_rows,
                    target_table=f"{database_name}.{target_table}",
                    duplicate_order_ids=sorted(existing_order_ids),
                )
            existing_orders = [order for order in orders if order.order_id in existing_order_ids]
            new_orders = [order for order in orders if order.order_id not in existing_order_ids]
            if existing_orders:
                await connection.execute(
                    update_statement,
                    [
                        {
                            "order_id": order.order_id,
                            "customer_name": order.customer_name,
                            "amount": order.amount,
                            "order_date": order.order_date,
                        }
                        for order in existing_orders
                    ],
                )
                replaced_rows = len(existing_orders)
            if new_orders:
                await connection.execute(
                    insert_statement,
                    [
                        {
                            "order_id": order.order_id,
                            "customer_name": order.customer_name,
                            "amount": order.amount,
                            "order_date": order.order_date,
                        }
                        for order in new_orders
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
        message="解析并更新成功" if replaced_rows else "解析并写库成功",
        total_rows=total_rows,
        inserted_rows=len(orders),
        target_table=f"{database_name}.{target_table}",
        replaced_rows=replaced_rows,
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
