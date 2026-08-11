from typing import Any, Literal

from pydantic import BaseModel, Field


class ImportIssue(BaseModel):
    row: int | None = None
    field: str | None = None
    message: str


class ImportResult(BaseModel):
    status: Literal["success", "validation_failed", "duplicate_conflict", "write_failed"]
    message: str
    total_rows: int = 0
    inserted_rows: int = 0
    errors: list[ImportIssue] = Field(default_factory=list)
    target_table: str | None = None
    duplicate_order_ids: list[str] = Field(default_factory=list)
    replaced_rows: int = 0


class ImportTarget(BaseModel):
    name: str
    label: str


class CreateOrderImportTableRequest(BaseModel):
    table_name: str = Field(min_length=1, max_length=64)


class CreateOrderImportTableResult(BaseModel):
    database: str
    table: str


class DatabaseTableRows(BaseModel):
    table: str
    columns: list[str]
    rows: list[dict[str, Any]]


class DeleteRowsRequest(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=100)


class DeleteRowsResult(BaseModel):
    deleted_rows: int
