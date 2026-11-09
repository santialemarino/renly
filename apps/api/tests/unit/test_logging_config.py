import logging

import pytest

from app.config import Settings
from app.main import create_app
from app.observability import APP_LOGGER_NAME
from app.services import email_service, email_templates
from app.services.email_service import ConsoleEmailService, ResendEmailService

# The app's own log lines reach the terminal: nothing but create_app configures the `app` logger, and
# without it Python's fallback prints WARNING and up, so the console provider's emails never showed.

_DB_URL = "postgresql+asyncpg://user:pass@localhost:5432/renly"
_SECRET = "x" * 32
_RESET_LINK = "http://localhost:3000/reset-password?token=raw-reset-token"


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, database_url=_DB_URL, jwt_secret=_SECRET, environment="development", **overrides)


# Leaves the `app` logger as an unconfigured process would have it, and puts back whatever the module
# import's own create_app set once the test ends.
@pytest.fixture(autouse=True)
def _bare_app_logger():
    app_logger = logging.getLogger(APP_LOGGER_NAME)
    saved_handlers, saved_level = list(app_logger.handlers), app_logger.level
    app_logger.handlers = []
    app_logger.setLevel(logging.NOTSET)
    yield
    app_logger.handlers = saved_handlers
    app_logger.setLevel(saved_level)


class TestConsoleEmailVisibility:
    # The default level prints a console email, link and all, the way `pnpm dev` runs the app.
    @pytest.mark.asyncio
    async def test_console_email_is_printed_at_the_default_level(self, capsys):
        create_app(_settings())

        await ConsoleEmailService().send(email_templates.password_reset_email("user@example.com", _RESET_LINK))

        err = capsys.readouterr().err
        assert "[email:console] to=user@example.com" in err
        assert _RESET_LINK in err
        assert "INFO:" in err

    # A second create_app (tests, reload) replaces the handler instead of printing every line twice.
    @pytest.mark.asyncio
    async def test_repeated_setup_prints_each_line_once(self, capsys):
        create_app(_settings())
        create_app(_settings())

        await ConsoleEmailService().send(email_templates.password_reset_email("user@example.com", _RESET_LINK))

        assert capsys.readouterr().err.count("[email:console]") == 1

    # LOG_LEVEL raises the bar (and is read in any case): at warning the email line is not printed.
    @pytest.mark.asyncio
    async def test_log_level_hides_info_lines(self, capsys):
        create_app(_settings(log_level="warning"))

        await ConsoleEmailService().send(email_templates.password_reset_email("user@example.com", _RESET_LINK))

        assert "[email:console]" not in capsys.readouterr().err

    # Only the app's loggers are configured: the root (and so httpx's request log, whose URLs can carry a
    # provider key) is left exactly as it was.
    def test_root_logger_is_left_alone(self):
        root = logging.getLogger()
        handlers_before, level_before = list(root.handlers), root.level

        create_app(_settings())

        assert root.handlers == handlers_before
        assert root.level == level_before


class _FakeResponse:
    def raise_for_status(self) -> None:
        return None


class _FakeAsyncClient:
    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    async def post(self, url, headers=None, json=None) -> _FakeResponse:
        return _FakeResponse()


class TestResendNeverLogsBodies:
    # A real provider sends the email and logs nothing of it, even at DEBUG: the reset token stays out of logs.
    @pytest.mark.asyncio
    async def test_resend_send_logs_no_body(self, monkeypatch, caplog, capsys):
        monkeypatch.setattr(email_service.httpx, "AsyncClient", _FakeAsyncClient)
        create_app(_settings(log_level="debug"))
        caplog.set_level(logging.DEBUG)

        await ResendEmailService(api_key="re_test_key", sender="Renly <noreply@renly.app>").send(
            email_templates.password_reset_email("user@example.com", _RESET_LINK)
        )

        assert "raw-reset-token" not in caplog.text
        assert "raw-reset-token" not in capsys.readouterr().err
