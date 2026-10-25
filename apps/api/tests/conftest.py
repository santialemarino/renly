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
#     test transport does not, so tests that stub their HTTP keep working. Not every provider is
#     covered: yfinance fetches through its own client (curl_cffi), outside httpx.
#
# The assertion is made at TEARDOWN, like the unit suite's session guard (tests/unit/conftest.py), and
# for the same reason: the refusal raises inside code built to swallow it, so a raise alone would pass
# silently. A test that means to show a request being refused (tests/unit/test_no_real_providers.py)
# takes the recorder as a fixture and empties it.

import os

import httpx
import pytest

# ENVIRONMENT has no default (the app refuses to boot without it), and tests build Settings from the
# process environment, sometimes with the .env file switched off. Set before the app is imported, so the
# suite runs the same with or without a .env; CI sets it explicitly as well.
os.environ.setdefault("ENVIRONMENT", "development")

from app.config import EmailProvider, settings  # noqa: E402
from app.services import email_service  # noqa: E402


# Collects every request a test tried to send to the real network, refusing each one.
class OutboundRecorder:
    def __init__(self) -> None:
        self.attempts: list[str] = []

    def refuse(self, request: httpx.Request) -> None:
        self.attempts.append(f"{request.method} {request.url}")
        raise httpx.ConnectError("tests must not reach a real network service", request=request)


@pytest.fixture(autouse=True)
def no_real_provider(monkeypatch):
    recorder = OutboundRecorder()

    async def refuse_async(_transport, request: httpx.Request) -> httpx.Response:
        recorder.refuse(request)

    def refuse_sync(_transport, request: httpx.Request) -> httpx.Response:
        recorder.refuse(request)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", refuse_async)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse_sync)
    monkeypatch.setattr(settings, "email_provider", EmailProvider.console)
    monkeypatch.setattr(settings, "email_api_key", None)
    email_service.get_email_service.cache_clear()
    yield recorder
    email_service.get_email_service.cache_clear()
    assert not recorder.attempts, (
        f"This test tried to reach a real network service: {recorder.attempts}. Stub the provider (or the "
        "notification fan-out) in the test, or give its client a fake transport."
    )
