from unittest.mock import AsyncMock

import pytest

from app.models.user import User
from app.models.user_settings import UserSettings
from app.services import settings_service

# Unit coverage for the onboarding_completed settings flag (first-run onboarding foundation): the
# read guard in _settings_to_response and the write round-trip through update_settings.

USER = User(id=1, email="user@test", password_hash="x", session_epoch=0)


class TestOnboardingFlagRead:
    def test_absent_flag_reads_as_none(self):
        assert settings_service._settings_to_response({})["onboarding_completed"] is None

    def test_true_flag_reads_true(self):
        assert settings_service._settings_to_response({"onboarding_completed": True})["onboarding_completed"] is True

    def test_non_bool_flag_is_guarded_to_none(self):
        # A malformed JSONB value must not leak through as a truthy string.
        assert settings_service._settings_to_response({"onboarding_completed": "yes"})["onboarding_completed"] is None


class TestOnboardingFlagWrite:
    @pytest.mark.asyncio
    async def test_update_sets_flag_and_preserves_other_keys(self, monkeypatch):
        row = UserSettings(user_id=1, settings={"primary_currency": "USD"})
        monkeypatch.setattr(settings_service.user_settings_repository, "get_by_user_id", AsyncMock(return_value=row))
        monkeypatch.setattr(settings_service.user_settings_repository, "save", AsyncMock())
        session = AsyncMock()

        result = await settings_service.update_settings(session, USER, onboarding_completed=True)

        assert result["onboarding_completed"] is True
        assert result["primary_currency"] == "USD"  # untouched keys survive the partial merge
        assert row.settings["onboarding_completed"] is True
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_without_flag_leaves_it_untouched(self, monkeypatch):
        row = UserSettings(user_id=1, settings={"onboarding_completed": True})
        monkeypatch.setattr(settings_service.user_settings_repository, "get_by_user_id", AsyncMock(return_value=row))
        monkeypatch.setattr(settings_service.user_settings_repository, "save", AsyncMock())

        result = await settings_service.update_settings(AsyncMock(), USER, primary_currency="ARS")

        assert result["onboarding_completed"] is True  # not passed → unchanged
