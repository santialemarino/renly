from collections.abc import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

# Key under which the request's user id is stashed on the session so the RLS listener can read it.
RLS_USER_INFO_KEY = "rls_user_id"

# Pool sizing (deliberate constants, not env — see docs/internal decision log): a page view fans
# out 4-7 parallel API calls, each borrowing a connection, so the request pool must absorb a few
# concurrent navigations; pre_ping revalidates pooled connections dropped by DB restarts/failovers
# (otherwise they surface as 500s) and recycle retires connections before typical idle timeouts.
REQUEST_POOL_SIZE = 10
REQUEST_MAX_OVERFLOW = 10
ADMIN_POOL_SIZE = 2
ADMIN_MAX_OVERFLOW = 3
POOL_RECYCLE_SECONDS = 1800

# Request engine: connects as the restricted, RLS-subject role (SEC-15).
engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_size=REQUEST_POOL_SIZE,
    max_overflow=REQUEST_MAX_OVERFLOW,
    pool_pre_ping=True,
    pool_recycle=POOL_RECYCLE_SECONDS,
)

# Privileged engine for context-less work (scheduler, auth bootstrap). Connects as the table
# owner, which bypasses RLS. Same URL as the request engine when no admin URL is configured.
# Small pool: only the scheduler and pre-auth lookups borrow from it.
admin_engine = create_async_engine(
    settings.admin_database_url,
    echo=False,
    pool_size=ADMIN_POOL_SIZE,
    max_overflow=ADMIN_MAX_OVERFLOW,
    pool_pre_ping=True,
    pool_recycle=POOL_RECYCLE_SECONDS,
)

AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

AdminSessionLocal = sessionmaker(
    admin_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# Re-applies the RLS user GUC at the start of every transaction. SET LOCAL is scoped to the
# current transaction and cleared on COMMIT/ROLLBACK; services commit mid-request and then read
# again, and pooled connections are reused across requests — so binding the GUC to after_begin
# (rather than setting it once) keeps each transaction correctly scoped and never leaks the value
# to another request. Sessions with no stashed user id (scheduler, auth bootstrap) are left alone
# so the owner role keeps its RLS-bypassing, cross-user access.
@event.listens_for(Session, "after_begin")
def _apply_rls_user_context(session: Session, transaction, connection) -> None:
    user_id = session.info.get(RLS_USER_INFO_KEY)
    if user_id is not None:
        connection.exec_driver_sql(f"SET LOCAL app.current_user_id = {int(user_id)}")


# Stashes the authenticated user id on the session so every transaction sets the RLS GUC.
def set_session_user(session: AsyncSession, user_id: int) -> None:
    session.info[RLS_USER_INFO_KEY] = user_id


# Request session: restricted role, subject to RLS once a user context is set.
async def get_session() -> AsyncGenerator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session


# Privileged session: owner role, bypasses RLS. For pre-auth lookups (login, register, API-key
# verification) that have no user context yet. Never use for normal user-scoped request work.
async def get_admin_session() -> AsyncGenerator[AsyncSession]:
    async with AdminSessionLocal() as session:
        yield session
