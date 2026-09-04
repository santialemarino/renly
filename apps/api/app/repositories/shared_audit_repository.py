# Data access for a group's audit trail.
#
# Scoped by the table's own RLS policy, never by a WHERE clause on the caller: an entry is readable by
# an active member of its group, and additionally only where the pot it names is one the reader may
# see. That second half lives in the policy rather than here for the reason every visibility rule in
# this schema does — a Python filter is a second copy of a rule the database already holds, and the
# copy is what eventually disagrees.

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.shared_audit import SharedAuditEntry


# A group's most recent entries, newest first. Bounded by the caller because the activity section shows
# a window rather than a history — an unbounded read of a table that only ever grows is SEC-11's shape.
async def list_by_group(session: AsyncSession, group_id: int, *, limit: int) -> list[SharedAuditEntry]:
    result = await session.execute(
        select(SharedAuditEntry)
        .where(SharedAuditEntry.group_id == group_id)
        .order_by(SharedAuditEntry.created_at.desc(), SharedAuditEntry.id.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


# Persists one entry. No flush: nothing reads the id back, and the entry rides the producer's own
# transaction so it lands with the write it describes or not at all.
def create(session: AsyncSession, entry: SharedAuditEntry) -> SharedAuditEntry:
    session.add(entry)
    return entry


# Namespace to call repository functions (e.g. shared_audit_repository.list_by_group).
class SharedAuditRepository:
    create = staticmethod(create)
    list_by_group = staticmethod(list_by_group)


# Singleton used by services to access audit-trail persistence.
shared_audit_repository = SharedAuditRepository()
