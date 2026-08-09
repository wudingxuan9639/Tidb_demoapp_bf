"""One-time TiDB schema migration for the order-import-only demo."""

import asyncio

from sqlalchemy import inspect, text

from app.database import engine
from app.models import Base


async def migrate() -> None:
    async with engine.begin() as connection:
        table_names = await connection.run_sync(
            lambda sync_connection: inspect(sync_connection).get_table_names()
        )
        if "items" in table_names:
            await connection.execute(text("DROP TABLE `items`"))
            print("Dropped table: items")
        if "order_imports_archive" in table_names and "order_import_archive" not in table_names:
            await connection.execute(
                text("RENAME TABLE `order_imports_archive` TO `order_import_archive`")
            )
            print("Renamed table: order_imports_archive -> order_import_archive")
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(migrate())
