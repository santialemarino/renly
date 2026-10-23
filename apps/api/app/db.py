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
# The two privileged pools split by caller: the admin pool serves the scheduler (each job runs on one
# connection of its own, dispatch included, and the hourly jobs start at distinct minutes) and the
# authenticated admin surface; the auth pool serves only the
# pre-auth paths (login, register, refresh, email verification, password reset, invite preview,
# API-key verification), so a job holding every admin connection can never queue a login or the
# refresh every session makes twice an hour. Per process: 20 + 5 + 5 = 30 connections at most.
REQUEST_POOL_SIZE = 10
REQUEST_MAX_OVERFLOW = 10
ADMIN_POOL_SIZE = 2
ADMIN_MAX_OVERFLOW = 3
AUTH_POOL_SIZE = 2
AUTH_MAX_OVERFLOW = 3
POOL_RECYCLE_SECONDS = 1800
# Wait for a free connection before raising. User-facing pools (request, auth) give up after 10s: a
# checkout queued that long means the pool is saturated, and failing then frees the worker instead of
# stacking requests behind the default 30s while the browser has long since given up on them; the
# auth pool's callers each hold a connection for one or two short queries (the bcrypt runs after the
# release), so 10s is hundreds of queued turns. The admin pool keeps 30s: its scheduler callers are
# background work with no user waiting, where a late run is cheaper than a failed one.
REQUEST_POOL_TIMEOUT_SECONDS = 10
AUTH_POOL_TIMEOUT_SECONDS = 10
ADMIN_POOL_TIMEOUT_SECONDS = 30

# Request engine: connects as the restricted, RLS-subject role (SEC-15).
engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_size=REQUEST_POOL_SIZE,
    max_overflow=REQUEST_MAX_OVERFLOW,
    pool_timeout=REQUEST_POOL_TIMEOUT_SECONDS,
    pool_pre_ping=True,
    pool_recycle=POOL_RECYCLE_SECONDS,
)

# Privileged engine for context-less work (scheduler, auth bootstrap). Connects as renly_admin,
# which bypasses RLS by attribute (BYPASSRLS), not by owning the tables — the owner is subject to the
# FORCEd policies. Same URL as the request engine when no admin URL is configured.
# Small pool: the scheduler and the authenticated routes that need cross-user access borrow from it.
admin_engine = create_async_engine(
    settings.admin_database_url,
    echo=False,
    pool_size=ADMIN_POOL_SIZE,
    max_overflow=ADMIN_MAX_OVERFLOW,
    pool_timeout=ADMIN_POOL_TIMEOUT_SECONDS,
    pool_pre_ping=True,
    pool_recycle=POOL_RECYCLE_SECONDS,
)

# Auth engine: the same renly_admin URL as the admin engine, in its own pool, reserved for the
# pre-auth paths so authentication never queues behind a scheduler job.
auth_engine = create_async_engine(
    settings.admin_database_url,
    echo=False,
    pool_size=AUTH_POOL_SIZE,
    max_overflow=AUTH_MAX_OVERFLOW,
    pool_timeout=AUTH_POOL_TIMEOUT_SECONDS,
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

AuthSessionLocal = sessionmaker(
    auth_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# Re-applies the RLS user GUC at the start of every transaction. SET LOCAL is scoped to the
# current transaction and cleared on COMMIT/ROLLBACK; services commit mid-request and then read
# again, and pooled connections are reused across requests — so binding the GUC to after_begin
# (rather than setting it once) keeps each transaction correctly scoped and never leaks the value
# to another request. Sessions with no stashed user id (scheduler, auth bootstrap) are left alone
# so the admin role keeps its RLS-bypassing, cross-user access.
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


# Privileged session: renly_admin, bypasses RLS. For authenticated work that must see across users
# (the admin surface, group/pot bootstrap, account cleanup). Never use for normal user-scoped request
# work, nor for a pre-auth path — those take get_auth_session.
async def get_admin_session() -> AsyncGenerator[AsyncSession]:
    async with AdminSessionLocal() as session:
        yield session


# Privileged session on the auth pool: renly_admin, bypasses RLS. For the pre-auth lookups (login,
# register, refresh, verification, password reset, API-key verification) that have no user context yet.
async def get_auth_session() -> AsyncGenerator[AsyncSession]:
    async with AuthSessionLocal() as session:
        yield session
