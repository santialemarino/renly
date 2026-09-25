import os
import uuid

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
# with a superuser owner it reads everything.
#
# ▸ WHAT A SUPERUSER OWNER HIDES, and how this file still sees it. It also hid a defect: the SECURITY
# DEFINER policy helpers ran as the owner, which under FORCE is subject to the very policy that calls
# them, so on a production-shaped database every group, roster and pot read recursed until "stack depth
# limit exceeded" — while every suite here, run against a superuser owner, stayed green. The helpers now
# belong to `renly_policy_definer`, and TestThePolicyHelpersSurviveAnOwnerSubjectToRls reads them under
# a NON-superuser owner whichever kind this database has: directly when the owner already is one, and
# otherwise by re-owning the owner's objects to a throwaway NOSUPERUSER role inside a transaction that
# is rolled back.
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


_PUBLIC_TABLES = (
    "SELECT c.oid, c.relname, c.relrowsecurity, c.relforcerowsecurity"
    " FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace"
    " WHERE n.nspname = 'public' AND c.relkind = 'r'"
)
_POLICIED = "SELECT tablename FROM pg_policies WHERE schemaname = 'public'"
_HAS_SCOPE_COLUMN = "JOIN pg_attribute a ON a.attrelid = t.oid AND NOT a.attisdropped AND a.attname = ANY(:cols)"

# The columns that make a row somebody's: a user's own, a group's, or a pot's. A table carrying any of
# them holds per-tenant data and must be policied; one carrying none (exchange rates, asset prices,
# CEDEAR ratios, alembic's version row) is global reference data and needs no policy.
_SCOPE_COLUMNS = ["user_id", "group_id", "pot_id"]


class TestEveryPoliciedTableIsForced:
    @pytest.mark.asyncio
    async def test_every_table_with_a_policy_has_rls_enabled_and_forced(self, admin):
        # Keyed on pg_policies, not on relrowsecurity. A table can carry a policy with RLS switched off
        # entirely — then the policy is decoration and every role reads every row — and a guard that
        # starts from "tables with RLS enabled" never looks at it. Starting from the policies catches
        # both halves: the policy with no ENABLE, and the ENABLE with no FORCE.
        rows = (
            await admin.execute(
                text(
                    f"SELECT t.relname FROM ({_PUBLIC_TABLES}) t"
                    f" WHERE t.relname IN ({_POLICIED}) AND NOT (t.relrowsecurity AND t.relforcerowsecurity) ORDER BY 1"
                )
            )
        ).scalars()
        assert list(rows) == []

    @pytest.mark.asyncio
    async def test_every_table_holding_someones_rows_is_policied_and_forced(self, admin):
        # The other direction: a table that gained a user_id, group_id or pot_id and no policy at all is
        # invisible to the check above, and readable by every request connection. Derived from the
        # columns rather than from a list of names, so the next table is covered by default and the
        # exemption (global reference data) falls out of the catalogue instead of being maintained.
        rows = (
            await admin.execute(
                text(
                    f"SELECT DISTINCT t.relname FROM ({_PUBLIC_TABLES}) t {_HAS_SCOPE_COLUMN}"
                    f" WHERE NOT (t.relrowsecurity AND t.relforcerowsecurity) OR t.relname NOT IN ({_POLICIED})"
                    " ORDER BY 1"
                ),
                {"cols": _SCOPE_COLUMNS},
            )
        ).scalars()
        assert list(rows) == []

    @pytest.mark.asyncio
    async def test_the_catalogue_queries_find_policied_tables_at_all(self, admin):
        # Anti-vacuity. Both assertions above are satisfied perfectly by a database with no RLS and no
        # scoped column anywhere, which is also what a typo in either query produces.
        forced = (await admin.execute(text(f"SELECT count(*) FROM ({_PUBLIC_TABLES}) t WHERE t.relforcerowsecurity"))).scalar_one()
        assert forced >= 39, f"only {forced} tables are FORCEd — the schema has lost coverage"
        scoped = (
            await admin.execute(
                text(f"SELECT count(DISTINCT t.relname) FROM ({_PUBLIC_TABLES}) t {_HAS_SCOPE_COLUMN}"),
                {"cols": _SCOPE_COLUMNS},
            )
        ).scalar_one()
        assert scoped >= 30, f"only {scoped} tables carry a scope column — the column query has stopped matching"


class TestTheRolesCarryTheAttributesTheModelDependsOn:
    @pytest.mark.asyncio
    async def test_the_request_role_can_neither_bypass_nor_supersede(self, admin):
        row = (await admin.execute(text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'renly_app'"))).one_or_none()
        assert row is not None, "renly_app is missing — apps/api/database/00_roles.sql provisions it"
        assert row.rolsuper is False
        assert row.rolbypassrls is False

    @pytest.mark.asyncio
    async def test_the_admin_role_bypasses_rls_but_is_not_a_superuser(self, admin):
        # Both halves matter and they fail differently. Without BYPASSRLS the scheduler, the pre-auth
        # lookup and every migration backfill read nothing. WITH superuser, FORCE is inert against it
        # and the role is a general-purpose skeleton key rather than a scoped one.
        row = (await admin.execute(text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'renly_admin'"))).one_or_none()
        assert row is not None, "renly_admin is missing — apps/api/database/00_roles.sql provisions it"
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


_DEFINER = "renly_policy_definer"
_HELPERS = {"app_can_view_pot", "app_can_write_pot", "app_is_group_member"}
_HELPER_READS = {"pots", "group_members", "pot_member_permissions"}


class TestThePolicyHelpersRunAsTheDefinerRole:
    @pytest.mark.asyncio
    async def test_every_security_definer_function_is_owned_by_the_definer_role(self, admin):
        # Derived from prosecdef rather than from the three names, so a NEW helper created by a later
        # migration — owned by renly_admin at creation and by the table owner after env.py's REASSIGN,
        # i.e. by exactly the role that recurses under FORCE — fails here until it is handed over.
        rows = (
            await admin.execute(
                text(
                    "SELECT p.proname, pg_get_userbyid(p.proowner) FROM pg_proc p"
                    " JOIN pg_namespace n ON n.oid = p.pronamespace WHERE n.nspname = 'public' AND p.prosecdef"
                )
            )
        ).all()
        owners = {name: owner for name, owner in rows}
        assert _HELPERS <= set(owners), f"the policy helpers are missing or no longer SECURITY DEFINER: {owners}"
        assert {name: owner for name, owner in owners.items() if owner != _DEFINER} == {}

    @pytest.mark.asyncio
    async def test_the_definer_role_bypasses_rls_but_can_neither_log_in_nor_supersede(self, admin):
        # BYPASSRLS is the point: it is what stops a helper re-entering the policy that called it.
        # NOLOGIN and NOSUPERUSER are what keep that bypass from being usable as anything else.
        row = (
            await admin.execute(text("SELECT rolsuper, rolbypassrls, rolcanlogin FROM pg_roles WHERE rolname = :r"), {"r": _DEFINER})
        ).one_or_none()
        assert row is not None, f"{_DEFINER} is missing — apps/api/database/00_roles.sql provisions it"
        assert row.rolbypassrls is True
        assert row.rolsuper is False
        assert row.rolcanlogin is False

    @pytest.mark.asyncio
    async def test_the_definer_role_may_read_exactly_what_the_helpers_read_and_nothing_else(self, admin):
        # The bypass reaches as far as the grants do. SELECT on these three is what the bodies need; any
        # other table or verb would make the role a general reader with RLS switched off. It must own no
        # relation (a table it owned would be exempt from FORCE) and keep no CREATE on the schema, which
        # it holds only for the length of the ownership handover.
        grants = (
            await admin.execute(
                text(
                    "SELECT c.relname, a.privilege_type FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace,"
                    " aclexplode(c.relacl) a WHERE n.nspname = 'public' AND a.grantee = CAST(:r AS regrole)"
                ),
                {"r": _DEFINER},
            )
        ).all()
        assert {(table, verb) for table, verb in grants} == {(table, "SELECT") for table in _HELPER_READS}
        owned = (await admin.execute(text("SELECT count(*) FROM pg_class WHERE relowner = CAST(:r AS regrole)"), {"r": _DEFINER})).scalar_one()
        assert owned == 0
        may_create = (await admin.execute(text("SELECT has_schema_privilege(:r, 'public', 'CREATE')"), {"r": _DEFINER})).scalar_one()
        assert may_create is False


_DEFINER_EMAILS = ["force_definer_member@test.local", "force_definer_peer@test.local"]
_DEFINER_GROUP = "force_definer_group"


# Removes everything seeded_group creates, children first.
async def _cleanup_definer_seed(s: AsyncSession) -> None:
    pots = f"SELECT id FROM pots WHERE group_id IN (SELECT id FROM groups WHERE name = '{_DEFINER_GROUP}')"
    await s.execute(text(f"DELETE FROM investments WHERE pot_id IN ({pots})"))
    await s.execute(text(f"DELETE FROM pots WHERE id IN ({pots})"))
    await s.execute(text("DELETE FROM groups WHERE name = :g"), {"g": _DEFINER_GROUP})
    await s.execute(text("DELETE FROM users WHERE email = ANY(:e)"), {"e": _DEFINER_EMAILS})


# One group with two seats, a pot the first member may write, and a pot-scoped holding — so each of the
# three helpers is on the path of at least one read: groups and group_members through
# app_is_group_member, the holding through app_can_view_pot, and app_can_write_pot called directly.
@pytest_asyncio.fixture
async def seeded_group(admin):
    await _cleanup_definer_seed(admin)
    users = []
    for email in _DEFINER_EMAILS:
        users.append(
            (
                await admin.execute(text("INSERT INTO users (name, email, password_hash) VALUES ('Definer', :e, 'x') RETURNING id"), {"e": email})
            ).scalar_one()
        )
    group = (
        await admin.execute(
            text("INSERT INTO groups (name, kind, created_by) VALUES (:n, 'household', :u) RETURNING id"),
            {"n": _DEFINER_GROUP, "u": users[0]},
        )
    ).scalar_one()
    seats = []
    for user in users:
        seats.append(
            (
                await admin.execute(
                    text(
                        "INSERT INTO group_members (group_id, user_id, display_name, role, joined_at)"
                        " VALUES (:g, :u, 'seat', 'member', NOW()) RETURNING id"
                    ),
                    {"g": group, "u": user},
                )
            ).scalar_one()
        )
    pot = (
        await admin.execute(text("INSERT INTO pots (group_id, base_currency, is_default) VALUES (:g, 'USD', TRUE) RETURNING id"), {"g": group})
    ).scalar_one()
    await admin.execute(
        text("INSERT INTO pot_member_permissions (pot_id, member_id, can_view, can_write) VALUES (:p, :m, TRUE, TRUE)"),
        {"p": pot, "m": seats[0]},
    )
    await admin.execute(
        text("INSERT INTO investments (pot_id, created_by, name, category, base_currency) VALUES (:p, :u, 'definer', 'stocks', 'USD')"),
        {"p": pot, "u": users[0]},
    )
    await admin.commit()
    yield {"user": users[0], "group": group, "pot": pot}
    await admin.rollback()
    await _cleanup_definer_seed(admin)
    await admin.commit()


# What the first member must see: every row seeded for them, and write access to the pot.
_EXPECTED_READS = {"groups": 1, "group_members": 2, "pots": 1, "investments": 1, "can_write": True}


# Reads, as the first seeded member, one figure per helper-guarded path, for comparison with _EXPECTED_READS.
async def _member_reads(session: AsyncSession, seeded: dict) -> dict:
    await session.execute(text("SELECT set_config('app.current_user_id', :u, true)"), {"u": str(seeded["user"])})
    ids = {"g": seeded["group"], "p": seeded["pot"]}
    reads = {
        "groups": "SELECT count(*) FROM groups WHERE id = :g",
        "group_members": "SELECT count(*) FROM group_members WHERE group_id = :g",
        "pots": "SELECT count(*) FROM pots WHERE group_id = :g",
        "investments": "SELECT count(*) FROM investments WHERE pot_id = :p",
        "can_write": "SELECT app_can_write_pot(:p)",
    }
    return {name: (await session.execute(text(sql), ids)).scalar_one() for name, sql in reads.items()}


class TestThePolicyHelpersSurviveAnOwnerSubjectToRls:
    @pytest.mark.asyncio
    async def test_a_member_reads_their_group_and_pot_as_the_request_role(self, admin, seeded_group):
        # THE regression. Against a superuser owner the helpers work whoever owns them, so the rest of
        # the RLS suites cannot see this; it only shows once the owner is what production requires.
        owner, owner_is_superuser = (
            await admin.execute(
                text("SELECT r.rolname, r.rolsuper FROM pg_class c JOIN pg_roles r ON r.oid = c.relowner WHERE c.oid = 'public.users'::regclass")
            )
        ).one()
        if owner_is_superuser:
            reads = await self._reads_under_a_nosuperuser_owner(admin, owner, seeded_group)
        else:
            engine = create_async_engine(APP_URL)
            async with AsyncSession(engine) as session:
                reads = await _member_reads(session, seeded_group)
                await session.rollback()
            await engine.dispose()
        assert reads == _EXPECTED_READS

    # Builds the production shape inside one transaction and rolls it back. renly_admin is a member of
    # the owner, so it can take the owner's identity — a superuser one here — create a NOSUPERUSER,
    # NOBYPASSRLS role, and hand it every table and function the owner holds, which is what a
    # production owner is. It then becomes renly_app (granting itself that membership, inside the same
    # transaction) and reads as a request would. Nothing survives the rollback: roles, ownership and
    # membership are all transactional in Postgres, and no other session sees them meanwhile.
    async def _reads_under_a_nosuperuser_owner(self, admin: AsyncSession, owner: str, seeded: dict) -> dict:
        probe = f"rls_owner_probe_{uuid.uuid4().hex[:12]}"
        try:
            await admin.execute(text(f'SET LOCAL ROLE "{owner}"'))
            await admin.execute(text(f"CREATE ROLE {probe} NOLOGIN NOSUPERUSER NOBYPASSRLS"))
            handovers = (
                await admin.execute(
                    text(
                        "SELECT format('ALTER TABLE %s OWNER TO %I', c.oid::regclass, CAST(:probe AS text))"
                        " FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace"
                        " WHERE n.nspname = 'public' AND c.relkind = 'r' AND pg_get_userbyid(c.relowner) = :owner"
                        " UNION ALL"
                        " SELECT format('ALTER FUNCTION %s OWNER TO %I', p.oid::regprocedure, CAST(:probe AS text))"
                        " FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace"
                        " WHERE n.nspname = 'public' AND pg_get_userbyid(p.proowner) = :owner"
                    ),
                    {"probe": probe, "owner": owner},
                )
            ).scalars()
            for statement in list(handovers):
                await admin.execute(text(statement))
            await admin.execute(text("GRANT renly_app TO SESSION_USER"))
            await admin.execute(text("SET LOCAL ROLE renly_app"))
            return await _member_reads(admin, seeded)
        finally:
            await admin.rollback()


class TestTablesAMigrationCreatesReachTheRequestRole:
    @pytest.mark.asyncio
    async def test_a_table_created_by_the_admin_role_is_granted_to_renly_app(self, admin):
        # Migrations run as renly_admin, so a table one creates is renly_admin's until env.py reassigns it
        # to the owner — and reassignment moves ownership without adding a single privilege. Only
        # renly_admin's OWN default privileges put renly_app's grants on it, and only at creation. This
        # does what a migration plus env.py does to one table, in a transaction that is rolled back.
        who = (await admin.execute(text("SELECT CURRENT_USER"))).scalar_one()
        assert who == "renly_admin", f"RLS_TEST_ADMIN_DATABASE_URL must name renly_admin, not {who}"
        owner = (await admin.execute(text("SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid = 'public.users'::regclass"))).scalar_one()
        try:
            await admin.execute(text("CREATE TABLE rls_default_privilege_probe (id BIGSERIAL PRIMARY KEY)"))
            await admin.execute(text(f'ALTER TABLE rls_default_privilege_probe OWNER TO "{owner}"'))
            checks = {
                verb: (
                    await admin.execute(text("SELECT has_table_privilege('renly_app', 'rls_default_privilege_probe', :v)"), {"v": verb})
                ).scalar_one()
                for verb in ("SELECT", "INSERT", "UPDATE", "DELETE")
            }
            checks |= {
                f"sequence {verb}": (
                    await admin.execute(text("SELECT has_sequence_privilege('renly_app', 'rls_default_privilege_probe_id_seq', :v)"), {"v": verb})
                ).scalar_one()
                for verb in ("USAGE", "SELECT")
            }
        finally:
            await admin.rollback()
        assert checks == dict.fromkeys(checks, True)
