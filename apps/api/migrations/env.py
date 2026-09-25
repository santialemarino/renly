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
    # ▸ The two `commit()` calls — this one and the one after the REASSIGN below — are load-bearing as a
    # PAIR, and removing both is silent. `exec_driver_sql` opens an implicit transaction; alembic's own
    # `begin_transaction()` then NESTS inside it, so alembic's commit is a no-op and whatever commits
    # the OUTER transaction is what makes the run real. Measured each way against a real database:
    #   * without this one, the final commit still commits everything — the run applies;
    #   * without the final one, this one has already ended the implicit transaction, so alembic's own
    #     commit is real and the migrations apply — but the REASSIGN runs in a fresh implicit
    #     transaction that is rolled back at close, leaving new objects owned by renly_admin, silently;
    #   * without BOTH, alembic logs "Running upgrade …", exits 0, and the database comes back
    #     unchanged with the version table where it was.
    # `SET` without `LOCAL` is session-scoped, so it survives this commit and still covers every
    # migration that follows.
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
    # The target is whoever owns `users`, not the DATABASE owner: those usually coincide, but when they
    # do not, reassigning to the database owner would hand this run's objects to a role that owns
    # nothing else — and the next no-op upgrade would still reach this statement after committing.
    # `users` is the anchor because every Renly database has it from its first revision; a database
    # without it is not one this chain can migrate, and says so rather than guessing.
    #
    # Guarded on the role rather than assumed: a cluster with no `renly_admin` (a developer running as
    # their own superuser) has nothing to reassign and should not fail for it.
    connection.exec_driver_sql(
        """
        DO $$
        DECLARE
          table_owner TEXT;
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'renly_admin') AND CURRENT_USER = 'renly_admin' THEN
            SELECT pg_get_userbyid(relowner) INTO table_owner FROM pg_class WHERE oid = to_regclass('public.users');
            IF table_owner IS NULL THEN
              RAISE EXCEPTION 'cannot reassign objects created by renly_admin: public.users does not exist, so the table owner is unknown';
            END IF;
            IF table_owner <> 'renly_admin' THEN
              EXECUTE format('REASSIGN OWNED BY renly_admin TO %I', table_owner);
            END IF;
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
