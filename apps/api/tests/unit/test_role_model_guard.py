import pytest
from fastapi import FastAPI

from app import main as main_module
from app import role_model_guard
from app.config import Environment, Settings
from app.role_model_guard import PoliciedTable, RoleFacts, RoleModelFacts, UnsafeRoleModelError, role_model_problems, verify_role_model

# The production refusal of a database whose roles make RLS decorative (`app/role_model_guard.py`), with
# the catalogue read stubbed: every branch of the verdict, the development no-op, the message, and the
# lifespan wiring. The real catalogue query is driven in tests/integration/test_role_model_guard_catalogue.py.

_DB_URL = "postgresql+asyncpg://renly_app:hunter2-db-password@db.internal:5432/renly"
_SECRET = "x" * 32

_APP = RoleFacts(name="renly_app", superuser=False, bypass_rls=False)
_OWNER = RoleFacts(name="renly", superuser=False, bypass_rls=False)


def _settings(environment: Environment) -> Settings:
    return Settings(_env_file=None, database_url=_DB_URL, jwt_secret=_SECRET, environment=environment)


def _table(name: str, *, owner: RoleFacts = _OWNER, enabled: bool = True, forced: bool = True) -> PoliciedTable:
    return PoliciedTable(name=name, rls_enabled=enabled, rls_forced=forced, owner=owner)


def _sound(**overrides) -> RoleModelFacts:
    values = {"request_role": _APP, "policied_tables": [_table("public.accounts"), _table("public.pots")]}
    values.update(overrides)
    return RoleModelFacts(**values)


# An engine the guard may open a connection on; records whether it did.
class _FakeEngine:
    def __init__(self) -> None:
        self.connected = False

    def connect(self):
        engine = self

        class _Connection:
            async def __aenter__(self):
                engine.connected = True
                return object()

            async def __aexit__(self, *exc):
                return False

        return _Connection()


def _stub_catalogue(monkeypatch, facts: RoleModelFacts) -> None:
    async def fake_read(_connection):
        return facts

    monkeypatch.setattr(role_model_guard, "read_role_model", fake_read)


class TestTheVerdict:
    def test_the_provisioned_model_has_no_problem(self):
        assert role_model_problems(_sound()) == []

    @pytest.mark.parametrize(
        ("superuser", "bypass_rls", "named"),
        [(True, False, "is SUPERUSER,"), (False, True, "is BYPASSRLS,"), (True, True, "is SUPERUSER and BYPASSRLS,")],
    )
    def test_a_privileged_request_role_is_a_problem(self, superuser, bypass_rls, named):
        facts = _sound(request_role=RoleFacts(name="postgres", superuser=superuser, bypass_rls=bypass_rls))
        [problem] = role_model_problems(facts)
        assert "request role behind DATABASE_URL (postgres)" in problem
        assert named in problem

    @pytest.mark.parametrize(
        ("superuser", "bypass_rls", "named"),
        [(True, False, "is SUPERUSER,"), (False, True, "is BYPASSRLS,"), (True, True, "is SUPERUSER and BYPASSRLS,")],
    )
    def test_a_privileged_table_owner_is_a_problem(self, superuser, bypass_rls, named):
        owner = RoleFacts(name="postgres", superuser=superuser, bypass_rls=bypass_rls)
        facts = _sound(policied_tables=[_table("public.accounts", owner=owner)])
        [problem] = role_model_problems(facts)
        assert "owner of the policied tables (postgres)" in problem
        assert named in problem

    # Owners are checked one by one, not by sampling one table: a single privileged owner among sound
    # ones is still named, once, however many tables it owns.
    def test_every_owner_is_checked_and_each_named_once(self):
        stray = RoleFacts(name="platform_admin", superuser=True, bypass_rls=False)
        tables = [_table("public.accounts"), _table("public.pots", owner=stray), _table("public.groups", owner=stray)]
        [problem] = role_model_problems(_sound(policied_tables=tables))
        assert "(platform_admin)" in problem

    def test_a_table_without_force_is_a_problem_naming_it(self):
        tables = [_table("public.accounts"), _table("public.pots", forced=False)]
        [problem] = role_model_problems(_sound(policied_tables=tables))
        assert "lack FORCE ROW LEVEL SECURITY" in problem
        assert problem.endswith(": public.pots")

    # A policy on a table with RLS switched off binds nobody, FORCE or not.
    def test_a_policied_table_with_rls_disabled_is_a_problem_naming_it(self):
        tables = [_table("public.accounts"), _table("public.pots", enabled=False, forced=True)]
        [problem] = role_model_problems(_sound(policied_tables=tables))
        assert "row-level security disabled" in problem
        assert problem.endswith(": public.pots")

    # A database where the catalogue finds nothing policied isolates nobody; it fails closed.
    def test_no_policied_table_at_all_is_a_problem(self):
        [problem] = role_model_problems(_sound(policied_tables=[]))
        assert "no table has row-level security" in problem

    def test_every_problem_is_reported_together(self):
        owner = RoleFacts(name="postgres", superuser=True, bypass_rls=False)
        facts = RoleModelFacts(request_role=owner, policied_tables=[_table("public.pots", owner=owner, forced=False)])
        assert len(role_model_problems(facts)) == 3


class TestTheStartupRefusal:
    # Development keeps today's behaviour: the catalogue is never even read, so a superuser-owned local
    # database starts as before.
    @pytest.mark.asyncio
    async def test_development_never_reads_the_catalogue(self, monkeypatch):
        _stub_catalogue(monkeypatch, _sound(request_role=RoleFacts(name="renly", superuser=True, bypass_rls=True)))
        engine = _FakeEngine()
        await verify_role_model(_settings(Environment.development), engine)
        assert engine.connected is False

    @pytest.mark.asyncio
    async def test_production_with_a_sound_model_starts(self, monkeypatch):
        _stub_catalogue(monkeypatch, _sound())
        engine = _FakeEngine()
        await verify_role_model(_settings(Environment.production), engine)
        assert engine.connected is True

    @pytest.mark.asyncio
    async def test_production_with_a_problem_refuses_naming_it_without_the_connection_string(self, monkeypatch):
        _stub_catalogue(monkeypatch, _sound(policied_tables=[_table("public.pots", forced=False)]))
        with pytest.raises(UnsafeRoleModelError) as exc_info:
            await verify_role_model(_settings(Environment.production), _FakeEngine())
        message = str(exc_info.value)
        assert message.startswith("Refusing to start in production")
        assert "public.pots" in message
        assert "hunter2" not in message
        assert "db.internal" not in message

    # The refusal is wired into startup: entering the lifespan of a production app raises before the
    # scheduler starts.
    @pytest.mark.asyncio
    async def test_the_lifespan_refuses_before_starting_the_scheduler(self, monkeypatch):
        _stub_catalogue(monkeypatch, _sound(request_role=RoleFacts(name="postgres", superuser=True, bypass_rls=False)))
        monkeypatch.setattr(main_module, "engine", _FakeEngine())
        started = []
        monkeypatch.setattr(main_module, "start_scheduler", lambda: started.append(True))
        monkeypatch.setattr(main_module, "stop_scheduler", lambda: None)
        app = FastAPI()
        app.state.settings = _settings(Environment.production)
        with pytest.raises(UnsafeRoleModelError):
            async with main_module.lifespan(app):
                pass
        assert started == []

    def test_create_app_hands_its_settings_to_the_lifespan(self):
        app_settings = _settings(Environment.production)
        assert main_module.create_app(app_settings).state.settings is app_settings
