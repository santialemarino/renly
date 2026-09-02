from enum import StrEnum
from typing import Annotated

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

MIN_JWT_SECRET_LENGTH = 32


# Deployment environment; gates docs exposure and debug behavior (production locks both down).
class Environment(StrEnum):
    development = "development"
    production = "production"


# Transactional email provider (SHELL-3). console logs the message (local dev / tests); resend
# sends via the Resend HTTP API. Swappable behind the EmailService port without code changes.
class EmailProvider(StrEnum):
    console = "console"
    resend = "resend"


# Registration access mode. invite (default) gates POST /auth/register behind a valid admin invite —
# the access control for the invited beta; open skips the gate (the public-open flip + Turnstile are
# a later launch milestone). Only invite is built/used now.
class SignupMode(StrEnum):
    invite = "invite"
    open = "open"


# App configuration loaded from the environment (.env); imported app-wide via the settings singleton.
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Request connections use this URL — a restricted, NOBYPASSRLS, non-owner role subject to
    # Row-Level Security (SEC-15). Must NOT be the table owner/superuser or RLS is silently bypassed.
    database_url: str
    # Privileged connection for work with no user context (scheduler, migrations, auth bootstrap).
    # Connects as the table owner, which bypasses RLS. Falls back to database_url when unset (e.g.
    # single-role local setups and tests); production must set a distinct owner URL.
    database_admin_url: str | None = None
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    # Access token lifetime. Kept short (AUTH-7): the web silently exchanges the refresh token for a
    # new access token when this expires, so a stolen access token is only useful briefly.
    jwt_expire_minutes: int = 30
    # Refresh token lifetimes (AUTH-7). A "remember me" login gets the long window; an ordinary login
    # the short one — kept tight so an unchecked login on a shared computer doesn't outlive the visit
    # by much. Both slide on each rotation. When the refresh token itself expires, the user must
    # log in again.
    refresh_token_remember_days: int = 30
    refresh_token_default_hours: int = 2
    environment: Environment = Environment.development
    # Allowed CORS origins, comma-separated in the env (e.g. "https://app.renly.com,https://renly.com").
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]
    # Number of trusted reverse proxies in front of the app. 0 (default) means the app is reached
    # directly, so the peer address is the client. When > 0, the client IP used for rate limiting is
    # read from X-Forwarded-For counting this many hops from the right (the proxy-appended end), which
    # is spoof-resistant; set it to the real proxy/LB hop count in production or per-IP limits collapse
    # onto the proxy address. Must match the deployment — too high lets clients spoof their rate-limit key.
    trusted_proxy_count: int = 0
    # Sentry error-tracking DSN (INFRA-5). When unset (default), Sentry is not initialized and the
    # app sends nothing — so local dev, tests, and CI are unaffected. Set it (even on localhost) to
    # start capturing errors; the environment tag is taken from the environment setting above.
    sentry_dsn: str | None = None
    # Transactional email (SHELL-3). Provider selector + credentials; console (default) logs the
    # message for local dev, resend sends via the Resend API (api key + verified sender required).
    email_provider: EmailProvider = EmailProvider.console
    email_api_key: str | None = None
    email_from: str = "Renly <onboarding@resend.dev>"
    # Public base URL of the web app, used to build the links embedded in account emails
    # (verification, password reset, invite). No trailing slash.
    web_base_url: str = "http://localhost:3000"
    # Registration access mode (default invite): invite requires a valid admin invite to register,
    # open lets anyone register. Only invite is exercised at launch.
    signup_mode: SignupMode = SignupMode.invite
    # Web push (shared money — the notification layer). The base64url-encoded P-256 private key half
    # of a VAPID pair; unset (default) means this deployment sends no push at all, and the app says so
    # rather than offering a switch that does nothing. There is deliberately no public-key setting: the
    # applicationServerKey the browser subscribes with is DERIVED from this one, so a mismatched pair —
    # which fails silently, every browser subscribing happily and every send rejected — cannot exist.
    vapid_private_key: str | None = None
    # Contact the push service can reach about this deployment (a mailto: or https: URL, per RFC 8292).
    # Falls back to web_base_url, which is a valid subject and cannot go stale like a hard-coded address.
    vapid_subject: str | None = None

    # Rejects a missing or weak JWT secret at startup; a short/guessable secret makes every token forgeable.
    @field_validator("jwt_secret")
    @classmethod
    def _validate_jwt_secret(cls, value: str) -> str:
        if len(value) < MIN_JWT_SECRET_LENGTH:
            raise ValueError(f"jwt_secret must be at least {MIN_JWT_SECRET_LENGTH} characters.")
        return value

    # Splits the comma-separated CORS origins env string into a list (no-op when already a list default).
    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    # Rejects the resend email provider without an API key at startup; otherwise account emails
    # (verification, reset) would silently fail to send once the app is live.
    @model_validator(mode="after")
    def _validate_email_provider(self) -> "Settings":
        if self.email_provider == EmailProvider.resend and not self.email_api_key:
            raise ValueError("email_api_key is required when email_provider is 'resend'.")
        return self

    # Privileged DB URL for context-less work; falls back to the request URL when not configured.
    @property
    def admin_database_url(self) -> str:
        return self.database_admin_url or self.database_url

    # True when running in production; used to lock down docs and disable debug.
    @property
    def is_production(self) -> bool:
        return self.environment == Environment.production

    # Debug is enabled outside production only; never True in production (no tracebacks leaked).
    @property
    def debug(self) -> bool:
        return not self.is_production


settings = Settings()
