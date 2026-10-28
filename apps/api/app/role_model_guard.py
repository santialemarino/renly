import logging
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.config import Settings

logger = logging.getLogger(__name__)

# The production refusal for a database whose roles make Row-Level Security decorative.
#
# Every policied table is FORCEd so that owning it is no exemption, and the request role is NOBYPASSRLS so
# the policies bind it. Both stop meaning anything against a SUPERUSER or a BYPASSRLS role: such a role
# skips every policy whatever the table says. A host that hands over a superuser-owned database, or a
# DATABASE_URL naming a privileged role, therefore runs with no isolation between users, and nothing else
# notices — every request still answers. So production reads the catalogue once at startup and refuses
# to boot. Development keeps running: a local owner is usually the superuser that created the cluster.
#
# The population is derived, not named: every table in a user schema that has RLS enabled OR carries a
# policy. Keyed on both, because a policy on a table with RLS switched off is also decoration.

# The role DATABASE_URL logs in as, and the attributes that would let it skip the policies.
_REQUEST_ROLE_SQL = text("SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")

# Every policied table, with its RLS switches and its owner's attributes.
_POLICIED_TABLES_SQL = text(
    "SELECT n.nspname || '.' || c.relname AS name, c.relrowsecurity, c.relforcerowsecurity,"
    " o.rolname, o.rolsuper, o.rolbypassrls"
    " FROM pg_class c"
    " JOIN pg_namespace n ON n.oid = c.relnamespace"
    " JOIN pg_roles o ON o.oid = c.relowner"
    " WHERE c.relkind IN ('r', 'p')"
    " AND n.nspname NOT IN ('pg_catalog', 'information_schema') AND n.nspname NOT LIKE 'pg\\_%'"
    " AND (c.relrowsecurity OR EXISTS (SELECT 1 FROM pg_policy p WHERE p.polrelid = c.oid))"
    " ORDER BY 1"
)


# A role as the catalogue describes it.
@dataclass(frozen=True)
class RoleFacts:
    name: str
    superuser: bool
    bypass_rls: bool


# A policied table: whether RLS is enabled and forced on it, and who owns it.
@dataclass(frozen=True)
class PoliciedTable:
    name: str
    rls_enabled: bool
    rls_forced: bool
    owner: RoleFacts


# What the guard reads from the catalogue, through the request role's own connection.
@dataclass(frozen=True)
class RoleModelFacts:
    request_role: RoleFacts
    policied_tables: list[PoliciedTable]


# Raised at startup when the database's roles cannot enforce the policies.
class UnsafeRoleModelError(RuntimeError):
    pass


# Reads the request role and every policied table from the catalogue.
async def read_role_model(connection: AsyncConnection) -> RoleModelFacts:
    role = (await connection.execute(_REQUEST_ROLE_SQL)).one()
    tables = (await connection.execute(_POLICIED_TABLES_SQL)).all()
    return RoleModelFacts(
        request_role=RoleFacts(name=role.rolname, superuser=role.rolsuper, bypass_rls=role.rolbypassrls),
        policied_tables=[
            PoliciedTable(
                name=row.name,
                rls_enabled=row.relrowsecurity,
                rls_forced=row.relforcerowsecurity,
                owner=RoleFacts(name=row.rolname, superuser=row.rolsuper, bypass_rls=row.rolbypassrls),
            )
            for row in tables
        ],
    )


# Names a role's policy-skipping attributes ("SUPERUSER", "BYPASSRLS" or both), empty when it has none.
def _bypass_attributes(role: RoleFacts) -> list[str]:
    return [name for name, held in (("SUPERUSER", role.superuser), ("BYPASSRLS", role.bypass_rls)) if held]


# Lists every way the facts leave the policies unenforced; empty when the model is sound.
def role_model_problems(facts: RoleModelFacts) -> list[str]:
    problems = []
    request_attributes = _bypass_attributes(facts.request_role)
    if request_attributes:
        problems.append(
            f"the request role behind DATABASE_URL ({facts.request_role.name}) is {' and '.join(request_attributes)}, so no policy applies to it"
        )
    if not facts.policied_tables:
        problems.append("no table has row-level security, so nothing isolates one user's rows from another's")
    owners = {table.owner for table in facts.policied_tables}
    for owner in sorted(owners, key=lambda role: role.name):
        owner_attributes = _bypass_attributes(owner)
        if owner_attributes:
            attributes = " and ".join(owner_attributes)
            problems.append(f"the owner of the policied tables ({owner.name}) is {attributes}, so FORCE ROW LEVEL SECURITY is inert")
    disabled = [table.name for table in facts.policied_tables if not table.rls_enabled]
    if disabled:
        problems.append(f"these tables carry policies with row-level security disabled, so every role skips them: {', '.join(disabled)}")
    unforced = [table.name for table in facts.policied_tables if table.rls_enabled and not table.rls_forced]
    if unforced:
        problems.append(f"these policied tables lack FORCE ROW LEVEL SECURITY, so their owner skips the policies: {', '.join(unforced)}")
    return problems


# Refuses to start in production when the database's roles cannot enforce the policies; a no-op elsewhere.
async def verify_role_model(app_settings: Settings, engine: AsyncEngine) -> None:
    if not app_settings.is_production:
        return
    async with engine.connect() as connection:
        facts = await read_role_model(connection)
    problems = role_model_problems(facts)
    if not problems:
        logger.info("Database role model verified: %d policied tables, all FORCEd, no privileged role.", len(facts.policied_tables))
        return
    message = (
        "Refusing to start in production: the database roles do not enforce row-level security. "
        + "; ".join(problems)
        + ". Provision the roles per docs/technical/deployment.md (Roles, Provisioning)."
    )
    logger.critical(message)
    raise UnsafeRoleModelError(message)
