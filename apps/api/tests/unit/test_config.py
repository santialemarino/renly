import base64

import pytest
from pydantic import ValidationError

from app.config import MIN_JWT_SECRET_LENGTH, VAPID_PRIVATE_KEY_BYTES, Environment, Settings

_DB_URL = "postgresql+asyncpg://user:pass@localhost:5432/renly"


# --- environment (required) ---


class TestEnvironmentRequired:
    # Unset must refuse to boot (P7-A): a deployment that forgot ENVIRONMENT would otherwise run as
    # development, with /docs open and debug on. The .env file is switched off and the variable removed,
    # so the result does not depend on the machine the suite runs on.
    def test_unset_environment_refuses_to_boot(self, monkeypatch):
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        with pytest.raises(ValidationError, match="ENVIRONMENT must be set"):
            Settings(_env_file=None, database_url=_DB_URL, jwt_secret="x" * MIN_JWT_SECRET_LENGTH)

    # `ENVIRONMENT=` left blank in a .env is the same mistake as leaving it out.
    def test_blank_environment_refuses_to_boot(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "")
        with pytest.raises(ValidationError, match="ENVIRONMENT must be set"):
            Settings(_env_file=None, database_url=_DB_URL, jwt_secret="x" * MIN_JWT_SECRET_LENGTH)

    @pytest.mark.parametrize("value", list(Environment))
    def test_each_environment_is_accepted_from_the_process_env(self, monkeypatch, value):
        monkeypatch.setenv("ENVIRONMENT", value.value)
        settings = Settings(_env_file=None, database_url=_DB_URL, jwt_secret="x" * MIN_JWT_SECRET_LENGTH)
        assert settings.environment == value

    # A startup error must not echo the raw settings, which hold the JWT secret and DB passwords.
    def test_the_startup_error_does_not_print_secrets(self, monkeypatch):
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        secret = "s3cret-" + "x" * MIN_JWT_SECRET_LENGTH
        with pytest.raises(ValidationError) as exc_info:
            Settings(_env_file=None, database_url=_DB_URL, jwt_secret=secret)
        assert secret[-12:] not in str(exc_info.value)
        assert "pass@" not in str(exc_info.value)


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


# --- vapid_private_key validation ---


class TestVapidPrivateKeyValidation:
    # Unset is the DEFAULT and must stay valid: it is how a deployment says it sends no push at all.
    # Asserted on the FIELD and on an explicit None, never on a bare Settings() — this machine's own
    # .env carries a real key, so a constructed Settings would read it and the test would pass or fail
    # on whose machine it ran.
    def test_absent_key_is_the_supported_default(self):
        assert Settings.model_fields["vapid_private_key"].default is None
        settings = Settings(database_url=_DB_URL, jwt_secret="x" * MIN_JWT_SECRET_LENGTH, vapid_private_key=None)
        assert settings.vapid_private_key is None

    # An env var written but left blank (`VAPID_PRIVATE_KEY=`) is how a .env says "no push here", and it
    # reaches pydantic as "" rather than as None. Rejecting it would refuse to boot over a blank line.
    def test_an_empty_value_means_the_same_as_unset(self):
        settings = Settings(database_url=_DB_URL, jwt_secret="x" * MIN_JWT_SECRET_LENGTH, vapid_private_key="")
        assert settings.vapid_private_key == ""

    def test_a_base64url_scalar_is_accepted_with_or_without_padding(self):
        raw = bytes(range(VAPID_PRIVATE_KEY_BYTES))
        padded = base64.urlsafe_b64encode(raw).decode()
        for value in (padded, padded.rstrip("=")):
            settings = Settings(database_url=_DB_URL, jwt_secret="x" * MIN_JWT_SECRET_LENGTH, vapid_private_key=value)
            assert settings.vapid_private_key == value

    # The realistic mistake: a PEM pasted where the raw scalar belongs. Caught at startup, because the
    # alternative is a deployment that boots, reports push as available, and 500s the notifications page.
    @pytest.mark.parametrize(
        "value",
        [
            "-----BEGIN PRIVATE KEY-----\nMIGH\n-----END PRIVATE KEY-----",
            base64.urlsafe_b64encode(b"too short").decode(),
            base64.urlsafe_b64encode(bytes(65)).decode(),
            # Not decodable at all, which is a different branch: b64decode DISCARDS characters outside
            # the alphabet, so most junk reaches the length check — but a leftover character count that
            # cannot be a base64 string raises, and a raw binascii traceback out of config is not an
            # error message anybody can act on.
            "a",
        ],
        ids=["a PEM", "31 bytes short", "a 65-byte public point", "not decodable at all"],
    )
    def test_anything_that_is_not_a_p256_scalar_is_rejected(self, value):
        with pytest.raises(ValidationError):
            Settings(database_url=_DB_URL, jwt_secret="x" * MIN_JWT_SECRET_LENGTH, vapid_private_key=value)
