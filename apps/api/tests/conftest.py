# One autouse guard for the WHOLE suite, unit and integration alike: no test can reach a real email or
# push provider.
#
# A worktree's copied `.env` (and a developer's own) sets `EMAIL_PROVIDER=resend` with a live key and a
# VAPID key, and `settings` reads that file at import. A test that drove a real dispatch therefore sent
# REAL email through Resend — it happened once (U20), and nothing failed, because the notification layer
# swallows send failures by design. So this guard works at two levels:
#
#   * the email provider is forced to the console adapter for every test, and the cached adapter is
#     rebuilt around it, so a dispatch that gets as far as sending only logs;
#   * underneath that, httpx's REAL network transports are replaced with a recorder that refuses every
#     request. Resend and web push go through one of them; a fake client, `MockTransport` or the ASGI
#     test transport does not, so tests that stub their HTTP keep working;
#   * and yfinance, which fetches through its own client (curl_cffi) outside httpx, has that client's
#     request methods refused and recorded the same way, so a test that reaches Yahoo by accident fails
#     rather than depending on the network.
#
# The assertion is made at TEARDOWN, like the unit suite's session guard (tests/unit/conftest.py), and
# for the same reason: the refusal raises inside code built to swallow it, so a raise alone would pass
# silently. A test that means to show a request being refused (tests/unit/test_no_real_providers.py)
# takes the recorder as a fixture and empties it.

import asyncio
import os

import asyncpg
import httpx
import pytest
from curl_cffi import requests as curl_requests
from sqlalchemy.engine import URL, make_url

# ENVIRONMENT has no default (the app refuses to boot without it), and tests build Settings from the
# process environment, sometimes with the .env file switched off. Set before the app is imported, so the
# suite runs the same with or without a .env; CI sets it explicitly as well. A process variable beats
# .env, so a .env saying `production` still runs the suite as development unless the shell sets it.
os.environ.setdefault("ENVIRONMENT", "development")

# Under pytest-xdist (`-n`), every worker gets a database of its own: the integration suites seed fixed
# accounts, count queries and read whole tables, so two workers on one database would trip over each
# other. A worker (`PYTEST_XDIST_WORKER` = gw0, gw1, …) points every database variable at `<name>_<worker>`,
# a copy of the configured database made beforehand (`CREATE DATABASE renly_gw0 TEMPLATE renly`, as
# `ci.api.yml` does), rewritten here before the app or any suite reads it. `pytest_configure` below
# refuses a parallel run whose copies are missing: the suites would otherwise skip themselves as
# "database unusable", and a run that quietly skipped them would look green.
_DATABASE_VARS = (
    "DATABASE_URL",
    "DATABASE_ADMIN_URL",
    "RLS_TEST_DATABASE_URL",
    "RLS_TEST_ADMIN_DATABASE_URL",
    "LEDGER_TEST_DATABASE_URL",
    "GROUPS_TEST_DATABASE_URL",
)


# The URL a database variable names for one worker.
def _worker_url(url: str, worker: str) -> URL:
    parsed = make_url(url)
    return parsed.set(database=f"{parsed.database}_{worker}")


_xdist_worker = os.environ.get("PYTEST_XDIST_WORKER")
if _xdist_worker:
    for _var in _DATABASE_VARS:
        if _url := os.environ.get(_var):
            os.environ[_var] = _worker_url(_url, _xdist_worker).render_as_string(hide_password=False)


# The worker databases a parallel run needs and cannot connect to because they do not exist. A server that
# refuses or cannot be reached is not reported here: the suites report that themselves, as without -n.
async def _missing_worker_databases(workers: int) -> list[str]:
    urls = {
        _worker_url(url, f"gw{index}").set(drivername="postgresql")
        for var in _DATABASE_VARS
        if (url := os.environ.get(var))
        for index in range(workers)
    }
    missing = []
    for url in sorted(urls, key=lambda u: u.database or ""):
        try:
            connection = await asyncpg.connect(url.render_as_string(hide_password=False), timeout=10)
        except asyncpg.InvalidCatalogNameError:
            missing.append(url.database or "")
            continue
        except (OSError, asyncpg.PostgresError):
            continue
        await connection.close()
    return sorted(set(missing))


# On the xdist controller only (a worker has `workerinput`): with N workers, gw0 … gw(N-1) must each have
# their copy before any worker starts.
def pytest_configure(config: pytest.Config) -> None:
    workers = len(getattr(config.option, "tx", None) or [])
    if hasattr(config, "workerinput") or getattr(config.option, "dist", "no") == "no" or not workers:
        return
    missing = asyncio.run(_missing_worker_databases(workers))
    if missing:
        raise pytest.UsageError(
            f"a run with {workers} workers needs one database copy per worker, and these do not exist: {', '.join(missing)}. "
            "Create each from the database it copies (CREATE DATABASE <name>_gw0 TEMPLATE <name>, …), or run without -n."
        )


from app.config import EmailProvider, settings  # noqa: E402
from app.services import email_service  # noqa: E402


# Collects every request a test tried to send to the real network, refusing each one.
class OutboundRecorder:
    def __init__(self) -> None:
        self.attempts: list[str] = []

    def refuse(self, request: httpx.Request) -> None:
        self.attempts.append(f"{request.method} {request.url}")
        raise httpx.ConnectError("tests must not reach a real network service", request=request)

    def refuse_curl(self, method: str, url: str) -> None:
        self.attempts.append(f"{method} {url}")
        raise curl_requests.exceptions.ConnectionError("tests must not reach a real network service")


@pytest.fixture(autouse=True)
def no_real_provider(monkeypatch):
    recorder = OutboundRecorder()

    async def refuse_async(_transport, request: httpx.Request) -> httpx.Response:
        recorder.refuse(request)

    def refuse_sync(_transport, request: httpx.Request) -> httpx.Response:
        recorder.refuse(request)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", refuse_async)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse_sync)

    def refuse_curl(_session, method, url, *_args, **_kwargs):
        recorder.refuse_curl(method, url)

    async def refuse_curl_async(_session, method, url, *_args, **_kwargs):
        recorder.refuse_curl(method, url)

    monkeypatch.setattr(curl_requests.Session, "request", refuse_curl)
    monkeypatch.setattr(curl_requests.AsyncSession, "request", refuse_curl_async)
    monkeypatch.setattr(settings, "email_provider", EmailProvider.console)
    monkeypatch.setattr(settings, "email_api_key", None)
    email_service.get_email_service.cache_clear()
    yield recorder
    email_service.get_email_service.cache_clear()
    assert not recorder.attempts, (
        f"This test tried to reach a real network service: {recorder.attempts}. Stub the provider (or the "
        "notification fan-out) in the test, or give its client a fake transport."
    )
