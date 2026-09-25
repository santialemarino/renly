import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel

import app.models  # noqa: F401
from app.config import settings

config = context.config
target_metadata = SQLModel.metadata

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def run_migrations_offline() -> None:
    context.configure(
        url=settings.admin_database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    # `row_security = off` is a GUARD, not an optimisation, and it is the reason a wrong-role
    # migration fails loudly instead of silently.
    #
    # Since the policied tables are FORCEd, even the owner is subject to them — so a backfill like
    # `UPDATE users SET email_verified_at = NOW()` run with no user context matches no rows, reports
    # `UPDATE 0` and exits 0. Five migrations in this directory carry exactly that shape (0003, 0004,
    # 0017, 0019, 0026), and a data migration that silently does nothing is the worst kind.
    #
    # Asking for `row_security = off` cannot be satisfied by a role without BYPASSRLS: the first
    # statement touching a policied table raises "query would be affected by row-level security
    # policy", with a HINT naming the cause. So running these as the owner, or as the request role,
    # stops at the first statement instead of appearing to work. Verified both ways against a real
    # database before being relied on.
    #
    # ▸ The `commit()` is load-bearing and its absence is silent. `exec_driver_sql` opens an implicit
    # transaction; alembic's own `begin_transaction()` then NESTS inside it, so its commit is a no-op
    # and the outer transaction is rolled back when the connection closes. Observed exactly once:
    # alembic logged "Running upgrade 0028 -> 0029", exited 0, and the database came back unchanged
    # with the version table still reading 0028. `SET` without `LOCAL` is session-scoped, so it
    # survives the commit and still covers every migration that follows.
    connection.exec_driver_sql("SET row_security = off")
    connection.commit()
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()

    # Anything this migration created is owned by whoever ran it — `renly_admin`, not the owner — and
    # a table owned by a BYPASSRLS role is a table FORCE can never apply to. Reassigning after every
    # run keeps ownership in one place without asking each migration to remember, which is the kind of
    # per-file convention that goes missing exactly once and then stays missing.
    #
    # Guarded rather than assumed: a cluster with no `renly_admin` (a developer running as their own
    # superuser) has nothing to reassign and should not fail for it.
    connection.exec_driver_sql(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'renly_admin')
             AND CURRENT_USER = 'renly_admin' THEN
            EXECUTE 'REASSIGN OWNED BY renly_admin TO ' || quote_ident(
              (SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = current_database())
            );
          END IF;
        END $$
        """
    )
    connection.commit()


async def run_migrations_online() -> None:
    # Migrations run on the ADMIN url, which since the three-role model points at `renly_admin`:
    # BYPASSRLS (so backfills reach every user's rows under FORCE) and a member of the owner (so
    # ALTER TABLE / CREATE POLICY on owner-owned objects is permitted). The RLS-subject request role
    # can do neither.
    engine = create_async_engine(settings.admin_database_url)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
