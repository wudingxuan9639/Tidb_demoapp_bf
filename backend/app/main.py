import asyncio
import io
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Font
from sqlalchemy import bindparam, inspect, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from .database import SessionLocal, engine
from .excel_import import ExcelValidationError, parse_orders
from .events import broker
from .import_rules import ORDER_IMPORT_COLUMNS
from .models import Base, OrderImport, OrderImportArchive
from .schemas import (
    DatabaseTableRows,
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


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(title="Lightweight TiDB Demo", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8517", "http://localhost:8517"],
    allow_methods=["*"],
    allow_headers=["*"],
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


async def database_table_names() -> list[str]:
    async with engine.connect() as connection:
        return await connection.run_sync(lambda sync_connection: inspect(sync_connection).get_table_names())


@app.get("/api/tables", response_model=list[str])
async def list_database_tables() -> list[str]:
    return await database_table_names()


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
    target_table: str = Form("order_imports"),
    session: AsyncSession = Depends(get_session),
) -> ImportResult:
    target = IMPORT_TARGETS.get(target_table)
    if target is None:
        return ImportResult(
            status="validation_failed",
            message="不允许写入指定的数据表",
            errors=[ImportIssue(field="写入目标表", message="请选择页面提供的订单导入目标表")],
        )
    _, target_model = target
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

    existing_result = await session.scalars(
        select(target_model.order_id).where(target_model.order_id.in_([order.order_id for order in orders]))
    )
    existing_order_ids = set(existing_result)
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

    try:
        session.add_all(
            [
                target_model(
                    order_id=order.order_id,
                    customer_name=order.customer_name,
                    amount=order.amount,
                    order_date=order.order_date,
                )
                for order in orders
            ]
        )
        await session.commit()
    except SQLAlchemyError:
        await session.rollback()
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
        target_table=target_table,
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
