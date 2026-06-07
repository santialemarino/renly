from enum import StrEnum
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

MIN_JWT_SECRET_LENGTH = 32


# Deployment environment; gates docs exposure and debug behavior (production locks both down).
class Environment(StrEnum):
    development = "development"
    production = "production"


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
    jwt_expire_minutes: int = 10080
    environment: Environment = Environment.development
    # Allowed CORS origins, comma-separated in the env (e.g. "https://app.renly.com,https://renly.com").
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]
    # Number of trusted reverse proxies in front of the app. 0 (default) means the app is reached
    # directly, so the peer address is the client. When > 0, the client IP used for rate limiting is
    # read from X-Forwarded-For counting this many hops from the right (the proxy-appended end), which
    # is spoof-resistant; set it to the real proxy/LB hop count in production or per-IP limits collapse
    # onto the proxy address. Must match the deployment — too high lets clients spoof their rate-limit key.
    trusted_proxy_count: int = 0

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
