import pytest

from app.config import EmailProvider, Settings
from app.services import email_service, email_templates
from app.services.email_service import ConsoleEmailService, ResendEmailService, get_email_service

# SHELL-3: transactional email port + adapters + selector, plus the account-email templates.

_DB_URL = "postgresql+asyncpg://user:pass@localhost:5432/renly"
_SECRET = "x" * 32


def _settings(**overrides) -> Settings:
    # _env_file=None keeps these hermetic — independent of the developer's local apps/api/.env
    # (which may set EMAIL_PROVIDER=resend), so the provider-selector tests assert the code defaults.
    return Settings(_env_file=None, database_url=_DB_URL, jwt_secret=_SECRET, **overrides)


# --- Provider selector ---


class TestGetEmailService:
    def test_console_is_default(self, monkeypatch):
        monkeypatch.setattr(email_service, "settings", _settings())
        get_email_service.cache_clear()
        assert isinstance(get_email_service(), ConsoleEmailService)
        get_email_service.cache_clear()

    def test_resend_selected_when_configured(self, monkeypatch):
        monkeypatch.setattr(
            email_service,
            "settings",
            _settings(email_provider=EmailProvider.resend, email_api_key="re_test_key", email_from="Renly <x@y.com>"),
        )
        get_email_service.cache_clear()
        service = get_email_service()
        assert isinstance(service, ResendEmailService)
        get_email_service.cache_clear()


# --- Resend adapter ---


class _FakeResponse:
    def raise_for_status(self) -> None:
        return None


def _make_fake_client(captured: dict):
    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc) -> bool:
            return False

        async def post(self, url, headers=None, json=None) -> _FakeResponse:
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return _FakeResponse()

    return _FakeAsyncClient


class TestResendEmailService:
    @pytest.mark.asyncio
    async def test_send_posts_to_resend_api(self, monkeypatch):
        captured: dict = {}
        monkeypatch.setattr(email_service.httpx, "AsyncClient", _make_fake_client(captured))
        service = ResendEmailService(api_key="re_test_key", sender="Renly <noreply@renly.app>")

        await service.send(email_templates.verification_email("user@example.com", "https://app/verify?token=abc"))

        assert captured["url"] == ResendEmailService._API_URL
        assert captured["headers"]["Authorization"] == "Bearer re_test_key"
        assert captured["json"]["from"] == "Renly <noreply@renly.app>"
        assert captured["json"]["to"] == ["user@example.com"]
        assert "abc" in captured["json"]["text"]


# --- Console adapter ---


class TestConsoleEmailService:
    @pytest.mark.asyncio
    async def test_send_does_not_raise(self):
        await ConsoleEmailService().send(email_templates.verification_email("user@example.com", "https://app/verify?token=abc"))


# --- Templates ---


class TestTemplates:
    def test_verification_email_carries_link_and_recipient(self):
        msg = email_templates.verification_email("user@example.com", "https://app/verify?token=tok123")
        assert msg.to == "user@example.com"
        assert "tok123" in msg.text
        assert "tok123" in msg.html

    def test_account_exists_email_does_not_leak_a_token(self):
        msg = email_templates.account_exists_email("user@example.com", "https://app/login")
        assert msg.to == "user@example.com"
        assert "already have" in msg.text.lower()
        assert "token=" not in msg.text

    def test_password_reset_email_carries_link(self):
        msg = email_templates.password_reset_email("user@example.com", "https://app/reset-password?token=r1")
        assert "r1" in msg.text

    def test_feedback_notification_email_carries_category_submitter_and_message(self):
        msg = email_templates.feedback_notification_email("admin@example.com", "user@example.com", "bug", "It broke")
        assert msg.to == "admin@example.com"
        assert "bug" in msg.subject
        assert "user@example.com" in msg.text and "It broke" in msg.text

    def test_feedback_notification_email_escapes_html_in_the_message(self):
        # The feedback message is user-controlled free text; it must not inject HTML into the admin's
        # inbox. The plain-text body keeps the raw characters; the HTML body escapes them.
        msg = email_templates.feedback_notification_email("admin@example.com", "user@example.com", "bug", "<script>alert(1)</script>")
        assert "<script>" not in msg.html
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in msg.html
        assert "<script>alert(1)</script>" in msg.text
