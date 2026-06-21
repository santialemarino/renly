from app.config import Environment, Settings
from app.observability import init_sentry

_DB_URL = "postgresql+asyncpg://user:pass@localhost:5432/renly"
_SECRET = "x" * 32
_DSN = "https://examplePublicKey@o0.ingest.sentry.io/0"


def _settings(**overrides) -> Settings:
    return Settings(database_url=_DB_URL, jwt_secret=_SECRET, **overrides)


# Records sentry_sdk.init calls so tests can assert on initialization without sending events.
class _InitRecorder:
    def __init__(self):
        self.calls: list[dict] = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)


class TestSentryInit:
    # With no DSN configured (the default), Sentry must not initialize so dev/tests/CI send nothing.
    def test_no_dsn_does_not_initialize(self, monkeypatch):
        recorder = _InitRecorder()
        monkeypatch.setattr("app.observability.sentry_sdk.init", recorder)
        init_sentry(_settings(sentry_dsn=None))
        assert recorder.calls == []

    # An empty-string DSN (the .env default) is treated as disabled too.
    def test_empty_dsn_does_not_initialize(self, monkeypatch):
        recorder = _InitRecorder()
        monkeypatch.setattr("app.observability.sentry_sdk.init", recorder)
        init_sentry(_settings(sentry_dsn=""))
        assert recorder.calls == []

    # A configured DSN initializes Sentry with the DSN, the environment tag, and PII off.
    def test_dsn_initializes_with_environment(self, monkeypatch):
        recorder = _InitRecorder()
        monkeypatch.setattr("app.observability.sentry_sdk.init", recorder)
        init_sentry(_settings(sentry_dsn=_DSN, environment=Environment.production))
        assert len(recorder.calls) == 1
        assert recorder.calls[0]["dsn"] == _DSN
        assert recorder.calls[0]["environment"] == "production"
        assert recorder.calls[0]["send_default_pii"] is False
