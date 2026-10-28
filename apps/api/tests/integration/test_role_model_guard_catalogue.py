import os

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.role_model_guard import read_role_model, role_model_problems

# The production role-model refusal's catalogue read (`app/role_model_guard.py`) against a real database.
# The unit tests stub this read, so they cannot tell a query that sees the defects from one that never
# could. Here the real query runs as the request role (`renly_app`, as production runs it at startup) and
# must see the schema, and then on an admin connection it must see the two defects the refusal exists for:
# a policied table stripped of FORCE (inside a transaction that is rolled back) and a role that bypasses
# RLS (`renly_admin` is BYPASSRLS by design, so reading as it IS the privileged-request-role case).
#
# Gated on the same two vars as the other RLS suites.

APP_URL = os.getenv("RLS_TEST_DATABASE_URL")
ADMIN_URL = os.getenv("RLS_TEST_ADMIN_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not APP_URL or not ADMIN_URL,
    reason="set RLS_TEST_DATABASE_URL + RLS_TEST_ADMIN_DATABASE_URL (a real Postgres with the RLS schema) to run these",
)


@pytest_asyncio.fixture
async def app_connection():
    engine = create_async_engine(APP_URL)
    async with engine.connect() as connection:
        yield connection
    await engine.dispose()


@pytest_asyncio.fixture
async def admin_connection():
    engine = create_async_engine(ADMIN_URL)
    async with engine.connect() as connection:
        yield connection
        await connection.rollback()
    await engine.dispose()


class TestTheCatalogueReadAsTheRequestRole:
    # The request role can read everything the guard needs, and the derived population is the schema's:
    # the same tables pg_policies names, every one of them forced.
    @pytest.mark.asyncio
    async def test_it_sees_itself_and_every_policied_table(self, app_connection):
        facts = await read_role_model(app_connection)
        assert (facts.request_role.name, facts.request_role.superuser, facts.request_role.bypass_rls) == ("renly_app", False, False)
        policied_sql = text("SELECT DISTINCT 'public.' || tablename FROM pg_policies WHERE schemaname = 'public'")
        policied = (await app_connection.execute(policied_sql)).scalars()
        names = [table.name for table in facts.policied_tables]
        print(f"\nderived {len(names)} policied tables")
        assert len(names) > 20
        assert sorted(names) == sorted(policied)
        assert all(table.rls_enabled and table.rls_forced for table in facts.policied_tables)

    # The owner's attributes come from the catalogue, so they match what pg_tables and pg_roles say about
    # the real owner, whichever kind of owner this database has (a superuser locally, not in production).
    @pytest.mark.asyncio
    async def test_it_reports_the_real_owner_and_its_attributes(self, app_connection):
        facts = await read_role_model(app_connection)
        expected = (
            await app_connection.execute(
                text(
                    "SELECT t.schemaname || '.' || t.tablename, r.rolname, r.rolsuper, r.rolbypassrls"
                    " FROM pg_tables t JOIN pg_roles r ON r.rolname = t.tableowner WHERE t.schemaname = 'public'"
                )
            )
        ).all()
        by_name = {row[0]: tuple(row[1:]) for row in expected}
        for table in facts.policied_tables:
            assert (table.owner.name, table.owner.superuser, table.owner.bypass_rls) == by_name[table.name]
        owner_problem = [problem for problem in role_model_problems(facts) if "owner of the policied tables" in problem]
        owners = {table.owner for table in facts.policied_tables}
        assert bool(owner_problem) == any(owner.superuser or owner.bypass_rls for owner in owners)

    # The provisioned request role belongs to no privileged role and acts as the owner of no table
    # (00_roles.sql grants it privileges, never a membership), so on a production-shaped database — a
    # NOSUPERUSER owner — the read finds nothing to refuse; here the only problem it may report is the
    # owner's own attributes, which depend on how this database was provisioned.
    @pytest.mark.asyncio
    async def test_the_provisioned_request_role_has_no_membership_or_ownership_problem(self, app_connection):
        facts = await read_role_model(app_connection)
        assert facts.privileged_memberships == []
        assert not any(table.request_acts_as_owner for table in facts.policied_tables)
        assert all("owner of the policied tables" in problem for problem in role_model_problems(facts))


class TestTheCatalogueReadSeesTheDefects:
    @pytest.mark.asyncio
    async def test_a_table_stripped_of_force_is_named(self, admin_connection):
        await admin_connection.execute(text("ALTER TABLE accounts NO FORCE ROW LEVEL SECURITY"))
        facts = await read_role_model(admin_connection)
        [accounts] = [table for table in facts.policied_tables if table.name == "public.accounts"]
        assert (accounts.rls_enabled, accounts.rls_forced) == (True, False)
        assert any(problem.endswith(": public.accounts") and "lack FORCE" in problem for problem in role_model_problems(facts))

    @pytest.mark.asyncio
    async def test_a_table_with_rls_disabled_is_still_found_through_its_policies(self, admin_connection):
        await admin_connection.execute(text("ALTER TABLE accounts DISABLE ROW LEVEL SECURITY"))
        facts = await read_role_model(admin_connection)
        [accounts] = [table for table in facts.policied_tables if table.name == "public.accounts"]
        assert accounts.rls_enabled is False
        assert any("public.accounts" in problem and "disabled" in problem for problem in role_model_problems(facts))

    # renly_admin is BYPASSRLS, so a DATABASE_URL naming it is exactly the privileged request role.
    @pytest.mark.asyncio
    async def test_a_request_role_that_bypasses_rls_is_named(self, admin_connection):
        facts = await read_role_model(admin_connection)
        assert (facts.request_role.name, facts.request_role.bypass_rls) == ("renly_admin", True)
        assert any("request role behind DATABASE_URL (renly_admin) is BYPASSRLS" in problem for problem in role_model_problems(facts))

    # renly_admin is a member of the owner, so a DATABASE_URL naming it may also ALTER every policied table.
    @pytest.mark.asyncio
    async def test_a_member_of_the_owner_is_named_for_every_policied_table(self, admin_connection):
        facts = await read_role_model(admin_connection)
        assert facts.policied_tables and all(table.request_acts_as_owner for table in facts.policied_tables)
        assert any("(renly_admin) owns, or is a member of the owner of, policied tables" in problem for problem in role_model_problems(facts))

    # The owner is a member of renly_policy_definer (BYPASSRLS) per 00_roles.sql, so reading as the owner
    # (SET ROLE inside the rolled-back transaction) is a request role that can SET ROLE past every policy.
    @pytest.mark.asyncio
    async def test_membership_of_a_bypassrls_role_is_named(self, admin_connection):
        owner = (
            await admin_connection.execute(text("SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = current_database()"))
        ).scalar_one()
        await admin_connection.execute(text(f'SET LOCAL ROLE "{owner}"'))
        facts = await read_role_model(admin_connection)
        assert facts.request_role.name == owner
        assert "renly_policy_definer" in [role.name for role in facts.privileged_memberships]
        assert any(f"({owner}) is a member of renly_policy_definer, which is BYPASSRLS" in problem for problem in role_model_problems(facts))
