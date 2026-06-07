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

    database_url: str
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 10080
    environment: Environment = Environment.development
    # Allowed CORS origins, comma-separated in the env (e.g. "https://app.renly.com,https://renly.com").
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

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

    # True when running in production; used to lock down docs and disable debug.
    @property
    def is_production(self) -> bool:
        return self.environment == Environment.production

    # Debug is enabled outside production only; never True in production (no tracebacks leaked).
    @property
    def debug(self) -> bool:
        return not self.is_production


settings = Settings()
