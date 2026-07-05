# Data access for the restore-from-export flow. Restore is additive, so it only needs to insert; it
# reuses the model classes from the restore specs to stay generic (like export_repository), keeping the
# query in the repository layer without one bespoke method per entity.

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel


# Bulk-inserts freshly built rows and flushes so surrogate ids are assigned (needed to remap children).
async def bulk_insert(session: AsyncSession, rows: list[SQLModel]) -> None:
    if not rows:
        return
    session.add_all(rows)
    await session.flush()


# Namespace to call repository functions (e.g. restore_repository.bulk_insert).
class RestoreRepository:
    bulk_insert = staticmethod(bulk_insert)


# Singleton used by services to insert restored rows.
restore_repository = RestoreRepository()
