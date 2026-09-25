import os

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

# The three-role model and `FORCE ROW LEVEL SECURITY`, asserted against a real database because every
# one of these facts lives in the Postgres catalogue or in how Postgres answers a statement.
#
# ▸ WHAT FORCE BUYS. Before it, owning a table exempted you from its policies — so a connection string
# pointed at the owner disabled every policy silently. That is not hypothetical: local dev ran that way
# for months and `deployment.md` told operators to do the same for migrations. With FORCE, the owner
# reads nothing without a user context, so a wrong URL fails closed.
#
# ▸ WHAT FORCE COSTS, and why the third role exists. The scheduler, the pre-auth users lookup and
# several migration backfills legitimately span users, and all three relied on the owner's exemption.
# They move to `renly_admin`: BYPASSRLS, not a superuser, and a member of the owner so it can still
# alter owner-owned objects.
#
# ▸ THE SILENT FAILURE THIS FILE EXISTS TO PIN. Under FORCE, a backfill run by a role without
# BYPASSRLS matches nothing, reports `UPDATE 0` and exits 0 — a data migration that does nothing and
# says nothing. `migrations/env.py` sets `row_security = off` so that case raises instead. The last
# test drives both halves of that, because a guard nobody has watched fail is a guard nobody knows
# the direction of.
#
# ▸ WHAT THIS FILE DELIBERATELY DOES NOT ASSERT: that the OWNER is not a superuser. A superuser
# bypasses RLS whatever the table says, so `FORCE` is inert against one — which makes that the single
# most important fact in the model and the one least suited to a test here. It is cluster
# provisioning, not schema: on a developer machine the owner usually IS a superuser (it is the role
# that created the cluster), so asserting it would go red on a correct local setup, which is how
# people learn to route around a guard. It lives in `deployment.md` as a provisioning requirement
# instead. Measured locally for the record: with a non-superuser owner and FORCE, the owner reads 0;
# with a superuser owner it reads everything and none of the tests below can tell.
#
# Gated on the same two vars as the other RLS suites, so they run together.

APP_URL = os.getenv("RLS_TEST_DATABASE_URL")
ADMIN_URL = os.getenv("RLS_TEST_ADMIN_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not APP_URL or not ADMIN_URL,
    reason="set RLS_TEST_DATABASE_URL + RLS_TEST_ADMIN_DATABASE_URL (a real Postgres with the RLS schema) to run these",
)


@pytest_asyncio.fixture
async def admin():
    engine = create_async_engine(ADMIN_URL)
    async with AsyncSession(engine) as session:
        yield session
        await session.rollback()
    await engine.dispose()


class TestEveryPoliciedTableIsForced:
    @pytest.mark.asyncio
    async def test_no_table_has_rls_enabled_without_force(self, admin):
        # Derived from the catalogue, not from a list of table names: a table that gains a policy
        # without FORCE is one whose owner silently keeps the old exemption, and the whole point of
        # this unit is that owning a table stops being a way around its policies.
        rows = (
            await admin.execute(
                text(
                    "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace"
                    " WHERE n.nspname = 'public' AND c.relkind = 'r'"
                    "   AND c.relrowsecurity AND NOT c.relforcerowsecurity ORDER BY 1"
                )
            )
        ).scalars()
        assert list(rows) == []

    @pytest.mark.asyncio
    async def test_the_catalogue_query_finds_policied_tables_at_all(self, admin):
        # Anti-vacuity. The assertion above is satisfied perfectly by a database with no RLS anywhere,
        # which is also what a typo in the catalogue query produces.
        forced = (
            await admin.execute(
                text(
                    "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace"
                    " WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relforcerowsecurity"
                )
            )
        ).scalar_one()
        assert forced >= 39, f"only {forced} tables are FORCEd — the schema has lost coverage"


class TestTheRolesCarryTheAttributesTheModelDependsOn:
    @pytest.mark.asyncio
    async def test_the_request_role_can_neither_bypass_nor_supersede(self, admin):
        row = (await admin.execute(text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'renly_app'"))).one_or_none()
        assert row is not None, "renly_app is missing — the schema provisions it"
        assert row.rolsuper is False
        assert row.rolbypassrls is False

    @pytest.mark.asyncio
    async def test_the_admin_role_bypasses_rls_but_is_not_a_superuser(self, admin):
        # Both halves matter and they fail differently. Without BYPASSRLS the scheduler, the pre-auth
        # lookup and every migration backfill read nothing. WITH superuser, FORCE is inert against it
        # and the role is a general-purpose skeleton key rather than a scoped one.
        row = (await admin.execute(text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'renly_admin'"))).one_or_none()
        assert row is not None, "renly_admin is missing — the schema and migration 0029 both provision it"
        assert row.rolbypassrls is True
        assert row.rolsuper is False

    @pytest.mark.asyncio
    async def test_the_admin_role_is_a_member_of_the_owner(self, admin):
        # Membership is what lets migrations ALTER owner-owned objects. It does NOT carry BYPASSRLS —
        # that is a role attribute and is not inherited — which is why the test above checks the
        # attribute directly rather than inferring it from this.
        owner = (await admin.execute(text("SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = current_database()"))).scalar_one()
        is_member = (
            await admin.execute(
                text(
                    "SELECT EXISTS (SELECT 1 FROM pg_auth_members m"
                    " JOIN pg_roles r ON r.oid = m.member JOIN pg_roles g ON g.oid = m.roleid"
                    " WHERE r.rolname = 'renly_admin' AND g.rolname = :owner)"
                ),
                {"owner": owner},
            )
        ).scalar_one()
        assert is_member, f"renly_admin is not a member of the owner role ({owner})"


_EMAIL = "force_guard@test.local"


# One user that definitely exists, because the assertions below are about a ZERO and a zero means
# nothing in an empty table. Seeded through the admin role and removed afterwards.
@pytest_asyncio.fixture
async def seeded_user(admin):
    await admin.execute(text("DELETE FROM users WHERE email = :e"), {"e": _EMAIL})
    await admin.execute(
        text("INSERT INTO users (name, email, password_hash) VALUES ('Force', :e, 'x')"),
        {"e": _EMAIL},
    )
    await admin.commit()
    yield
    await admin.execute(text("DELETE FROM users WHERE email = :e"), {"e": _EMAIL})
    await admin.commit()


class TestRowSecurityOffIsTheLoudGuard:
    @pytest.mark.asyncio
    async def test_the_admin_role_may_ask_for_it_and_still_sees_the_row(self, admin, seeded_user):
        # The positive control, and it has to be a row rather than `>= 0`: if this stopped working,
        # migrations would fail on every run while the negative case below still looked like a
        # passing guard. Asserting the seeded row is present is what tells the two apart.
        await admin.execute(text("SET row_security = off"))
        count = (await admin.execute(text("SELECT count(*) FROM users WHERE email = :e"), {"e": _EMAIL})).scalar_one()
        assert count == 1

    @pytest.mark.asyncio
    async def test_a_role_without_bypass_is_refused_rather_than_silently_filtered(self, seeded_user):
        # THE test. Without `row_security = off` this same statement returns 0 rows and SUCCEEDS,
        # which is how a backfill run by the wrong role does nothing and reports success. With it, the
        # statement raises — so `migrations/env.py` setting it converts a silent no-op into a stop.
        engine = create_async_engine(APP_URL)
        async with AsyncSession(engine) as session:
            await session.execute(text("SET row_security = off"))
            with pytest.raises(ProgrammingError) as exc:
                await session.execute(text("SELECT count(*) FROM users WHERE email = :e"), {"e": _EMAIL})
            assert "row-level security" in str(exc.value).lower()
            await session.rollback()
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_and_without_the_guard_that_same_role_is_silently_empty(self, seeded_user):
        # The other half of the same fact, and the reason the guard is needed at all: what it prevents
        # is not an error, it is a ZERO. The seeded user is what makes that zero mean something — an
        # empty table would satisfy this assertion without any policy being involved, which is the
        # version of this test that proves nothing.
        engine = create_async_engine(APP_URL)
        async with AsyncSession(engine) as session:
            count = (await session.execute(text("SELECT count(*) FROM users WHERE email = :e"), {"e": _EMAIL})).scalar_one()
            assert count == 0
            await session.rollback()
        await engine.dispose()
