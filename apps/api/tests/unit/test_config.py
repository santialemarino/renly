import pytest
from pydantic import ValidationError

from app.config import MIN_JWT_SECRET_LENGTH, Settings

_DB_URL = "postgresql+asyncpg://user:pass@localhost:5432/renly"


# --- jwt_secret validation ---


class TestJwtSecretValidation:
    def test_short_secret_rejected(self):
        # A secret below the minimum length fails fast at construction.
        with pytest.raises(ValidationError):
            Settings(database_url=_DB_URL, jwt_secret="short")

    def test_minimum_length_secret_accepted(self):
        secret = "x" * MIN_JWT_SECRET_LENGTH
        settings = Settings(database_url=_DB_URL, jwt_secret=secret)
        assert settings.jwt_secret == secret
