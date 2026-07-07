from unittest.mock import AsyncMock

import pytest

from app.models.user import User
from app.services import onboarding_service

# Unit coverage for onboarding_service.get_status: each checklist step is derived from real data
# (an existence probe per entity + the stored primary-currency preference), OR-ing income/expense
# into a single "finances" step; plus first-run sample_mode (pristine account, never had data,
# samples not dismissed) and the lazy persist of the has_ever_had_data marker.

USER = User(id=1, email="user@test", password_hash="x", session_epoch=0)


def _patch(monkeypatch, *, investments, expenses, income, primary, has_ever=None, samples_dismissed=None):
    monkeypatch.setattr(onboarding_service.investment_repository, "exists_by_user", AsyncMock(return_value=investments))
    monkeypatch.setattr(onboarding_service.expense_repository, "exists_by_user", AsyncMock(return_value=expenses))
    monkeypatch.setattr(onboarding_service.income_repository, "exists_by_user", AsyncMock(return_value=income))
    settings = {"primary_currency": primary, "has_ever_had_data": has_ever, "samples_dismissed": samples_dismissed}
    monkeypatch.setattr(onboarding_service.settings_service, "get_settings", AsyncMock(return_value=settings))
    update_mock = AsyncMock()
    monkeypatch.setattr(onboarding_service.settings_service, "update_settings", update_mock)
    return update_mock


class TestOnboardingChecklist:
    @pytest.mark.asyncio
    async def test_fresh_user_has_nothing_done(self, monkeypatch):
        _patch(monkeypatch, investments=False, expenses=False, income=False, primary=None)

        result = await onboarding_service.get_status(AsyncMock(), USER)

        assert result == {
            "has_investments": False,
            "has_finances": False,
            "primary_currency_set": False,
            "sample_mode": True,
        }

    @pytest.mark.asyncio
    async def test_investment_step_reflects_existence(self, monkeypatch):
        _patch(monkeypatch, investments=True, expenses=False, income=False, primary=None)

        result = await onboarding_service.get_status(AsyncMock(), USER)

        assert result["has_investments"] is True

    @pytest.mark.asyncio
    async def test_finances_step_done_with_only_an_expense(self, monkeypatch):
        _patch(monkeypatch, investments=False, expenses=True, income=False, primary=None)

        result = await onboarding_service.get_status(AsyncMock(), USER)

        assert result["has_finances"] is True

    @pytest.mark.asyncio
    async def test_finances_step_done_with_only_income(self, monkeypatch):
        _patch(monkeypatch, investments=False, expenses=False, income=True, primary=None)

        result = await onboarding_service.get_status(AsyncMock(), USER)

        assert result["has_finances"] is True

    @pytest.mark.asyncio
    async def test_finances_step_not_done_without_income_or_expense(self, monkeypatch):
        _patch(monkeypatch, investments=True, expenses=False, income=False, primary="USD")

        result = await onboarding_service.get_status(AsyncMock(), USER)

        assert result["has_finances"] is False

    @pytest.mark.asyncio
    async def test_currency_step_reflects_stored_primary(self, monkeypatch):
        _patch(monkeypatch, investments=False, expenses=False, income=False, primary="USD")

        result = await onboarding_service.get_status(AsyncMock(), USER)

        assert result["primary_currency_set"] is True

    @pytest.mark.asyncio
    async def test_currency_step_not_done_when_primary_unset(self, monkeypatch):
        _patch(monkeypatch, investments=False, expenses=False, income=False, primary=None)

        result = await onboarding_service.get_status(AsyncMock(), USER)

        assert result["primary_currency_set"] is False


class TestSampleMode:
    @pytest.mark.asyncio
    async def test_pristine_account_is_in_sample_mode(self, monkeypatch):
        _patch(monkeypatch, investments=False, expenses=False, income=False, primary=None)

        result = await onboarding_service.get_status(AsyncMock(), USER)

        assert result["sample_mode"] is True

    @pytest.mark.asyncio
    async def test_account_with_data_is_not_in_sample_mode_and_marks_ever_had_data(self, monkeypatch):
        update_mock = _patch(monkeypatch, investments=True, expenses=False, income=False, primary=None)

        result = await onboarding_service.get_status(AsyncMock(), USER)

        assert result["sample_mode"] is False
        # The has_ever_had_data marker is persisted the first time real data is observed.
        update_mock.assert_awaited_once()
        assert update_mock.await_args.kwargs.get("has_ever_had_data") is True

    @pytest.mark.asyncio
    async def test_marker_not_rewritten_when_already_set(self, monkeypatch):
        update_mock = _patch(monkeypatch, investments=True, expenses=False, income=False, primary=None, has_ever=True)

        await onboarding_service.get_status(AsyncMock(), USER)

        update_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_emptied_account_stays_out_of_sample_mode(self, monkeypatch):
        # No data now, but has_ever_had_data is set → the user emptied the account, not a newbie.
        _patch(monkeypatch, investments=False, expenses=False, income=False, primary=None, has_ever=True)

        result = await onboarding_service.get_status(AsyncMock(), USER)

        assert result["sample_mode"] is False

    @pytest.mark.asyncio
    async def test_dismissed_samples_disable_sample_mode(self, monkeypatch):
        _patch(monkeypatch, investments=False, expenses=False, income=False, primary=None, samples_dismissed=True)

        result = await onboarding_service.get_status(AsyncMock(), USER)

        assert result["sample_mode"] is False
