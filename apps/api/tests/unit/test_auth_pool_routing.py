import ast
import inspect
import typing
from pathlib import Path

from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute

from app import db
from app.db import get_admin_session, get_auth_session
from app.main import create_app
from app.models.user import User

# Pins which code paths borrow which privileged pool (U18). The auth pool exists so a scheduler job
# holding every admin connection cannot queue a login or a token refresh; that only holds while every
# pre-auth path stays on it and nothing else borrows from it. Nothing here is a hand-kept list: the
# populations are derived from the app's real dependency graph and from the source tree.
#
# - A PRE-AUTH route is one whose dependency graph resolves no user (no dependency returning `User`
#   that takes a credential) — login, register, refresh, verification, reset, invite preview.
# - A USER RESOLVER is a dependency annotated to return `User` that reads a session directly
#   (get_current_user, get_jwt_or_api_key_user): the authentication step of an authenticated route.

_APP_DIR = Path(__file__).resolve().parents[2] / "app"
_PRIVILEGED_SESSIONS = {get_admin_session, get_auth_session}


# Every callable in a dependant's graph, the dependant itself included.
def _calls(dependant: Dependant) -> list:
    out = [dependant.call]
    for sub in dependant.dependencies:
        out.extend(_calls(sub))
    return out


# Every dependant node in the graph, the root included.
def _nodes(dependant: Dependant) -> list[Dependant]:
    out = [dependant]
    for sub in dependant.dependencies:
        out.extend(_nodes(sub))
    return out


# Whether an annotation names User, through Optional/Union and Annotated wrappers.
def _names_user(annotation: object) -> bool:
    if annotation is User:
        return True
    return any(_names_user(arg) for arg in typing.get_args(annotation))


# A dependency that resolves the caller: annotated to return User (bare, Optional or Annotated) and
# reading a session itself.
def _is_user_resolver(node: Dependant) -> bool:
    if node.call is None or not callable(node.call):
        return False
    try:
        returns = inspect.signature(node.call).return_annotation
    except (TypeError, ValueError):
        return False
    if not _names_user(returns):
        return False
    return any(sub.call in {db.get_session, *_PRIVILEGED_SESSIONS} for sub in node.dependencies)


# The app's API routes.
def _routes() -> list[APIRoute]:
    return [route for route in create_app().routes if isinstance(route, APIRoute)]


# The route's label for failure messages.
def _label(route: APIRoute) -> str:
    return f"{','.join(sorted(route.methods))} {route.path}"


# The route's graph with each user resolver's own subtree removed: the work the route does after
# authentication.
def _calls_after_auth(dependant: Dependant) -> list:
    out = [dependant.call]
    for sub in dependant.dependencies:
        if _is_user_resolver(sub):
            continue
        out.extend(_calls_after_auth(sub))
    return out


class TestPreAuthRoutesUseTheAuthPool:
    # No route that runs before a user is known may borrow from the scheduler's admin pool.
    def test_no_pre_auth_route_touches_the_admin_pool(self):
        pre_auth = []
        offenders = []
        for route in _routes():
            nodes = _nodes(route.dependant)
            if any(_is_user_resolver(node) for node in nodes):
                continue
            calls = {node.call for node in nodes}
            if calls & _PRIVILEGED_SESSIONS:
                pre_auth.append(_label(route))
            if get_admin_session in calls:
                offenders.append(_label(route))
        print(f"pre-auth routes on a privileged session: {sorted(pre_auth)}")
        for expected in ("POST /auth/login", "POST /auth/refresh", "POST /auth/register", "POST /auth/reset-password"):
            assert expected in pre_auth, f"{expected} is no longer derived as pre-auth, so this check proves nothing for it"
        assert offenders == [], f"pre-auth routes on the admin pool (use AuthSessionDep): {offenders}"

    # The authentication step itself (API-key verification) runs on the auth pool, not the admin pool,
    # even when it sits inside an otherwise authenticated route.
    def test_no_user_resolver_reads_the_admin_pool(self):
        resolvers = {}
        for route in _routes():
            for node in _nodes(route.dependant):
                if _is_user_resolver(node):
                    resolvers[node.call.__qualname__] = {sub.call for sub in node.dependencies}
        print(f"user resolvers: {sorted(resolvers)}")
        assert {"get_current_user", "get_jwt_or_api_key_user"} <= set(resolvers)
        offenders = sorted(name for name, deps in resolvers.items() if get_admin_session in deps)
        assert offenders == [], f"user resolvers on the admin pool (use AuthSessionDep): {offenders}"


class TestTheAuthPoolIsReservedForAuthentication:
    # Once a user is resolved, the route's own work never borrows from the auth pool: authenticated
    # cross-user work belongs on the admin pool, so a busy authenticated surface cannot starve logins.
    def test_no_authenticated_route_works_on_the_auth_pool(self):
        authenticated = []
        offenders = []
        for route in _routes():
            if not any(_is_user_resolver(node) for node in _nodes(route.dependant)):
                continue
            authenticated.append(_label(route))
            if get_auth_session in _calls_after_auth(route.dependant):
                offenders.append(_label(route))
        assert len(authenticated) > 50
        assert offenders == [], f"authenticated routes on the auth pool: {offenders}"

    # Outside the session factories and the FastAPI dependency, nothing in app/ names the auth pool —
    # so the scheduler, a service, or a script cannot open an auth session of its own.
    def test_only_db_and_the_dependency_name_the_auth_pool(self):
        names = {"auth_engine", "AuthSessionLocal", "get_auth_session"}
        allowed = {_APP_DIR / "db.py", _APP_DIR / "deps" / "db.py"}
        offenders = []
        for path in sorted(_APP_DIR.rglob("*.py")):
            if path in allowed:
                continue
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Name) and node.id in names or isinstance(node, ast.alias) and node.name in names:
                    offenders.append(f"{path.relative_to(_APP_DIR)}:{node.lineno}")
        assert offenders == [], f"the auth pool is named outside app/db.py and app/deps/db.py: {offenders}"


class TestPoolConfiguration:
    # The auth pool is its own pool on the admin role's URL, and every engine sets its checkout timeout
    # explicitly rather than inheriting SQLAlchemy's 30s default.
    def test_three_distinct_pools_with_explicit_timeouts(self):
        assert db.auth_engine.pool is not db.admin_engine.pool
        assert db.auth_engine.url == db.admin_engine.url
        expected = {
            db.engine: (db.REQUEST_POOL_SIZE, db.REQUEST_POOL_TIMEOUT_SECONDS),
            db.admin_engine: (db.ADMIN_POOL_SIZE, db.ADMIN_POOL_TIMEOUT_SECONDS),
            db.auth_engine: (db.AUTH_POOL_SIZE, db.AUTH_POOL_TIMEOUT_SECONDS),
        }
        for engine, (size, timeout) in expected.items():
            assert engine.pool.size() == size
            assert engine.pool.timeout() == timeout

    # The admin timeout equals SQLAlchemy's default, so its value alone cannot show it was set: every
    # engine in app/ must pass pool_timeout explicitly.
    def test_every_engine_passes_pool_timeout(self):
        engines = []
        for path in sorted(_APP_DIR.rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "create_async_engine":
                    engines.append((f"{path.relative_to(_APP_DIR)}:{node.lineno}", {kw.arg for kw in node.keywords}))
        assert len(engines) == 3
        offenders = [where for where, kwargs in engines if "pool_timeout" not in kwargs]
        assert offenders == [], f"engines without an explicit pool_timeout: {offenders}"
